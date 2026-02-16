"""
Quran data: XML parser (Tanzil), Quran Enc API (East African translations).
"""

import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from config import (
    ARABIC_XML_PATH,
    DATA_DIR,
    QURANENC_BASE,
    QURANENC_TRANSLATIONS,
    ARABIC_XML_URL,
)


def ensure_arabic_xml():
    """Download Arabic XML if not present. Handle BOM if present."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ARABIC_XML_PATH):
        print("Downloading Arabic Quran XML...")
        r = requests.get(ARABIC_XML_URL, timeout=30)
        r.raise_for_status()
        content = r.content.decode("utf-8-sig")  # strips BOM if present
        with open(ARABIC_XML_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print("Downloaded.")


def normalize_arabic(text: str) -> str:
    """Strip tashkeel (diacritics) and normalize whitespace for matching."""
    if not text:
        return ""
    try:
        from pyarabic import strip_tashkeel
        stripped = strip_tashkeel(text)
    except ImportError:
        nfd = unicodedata.normalize("NFD", text)
        stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
        stripped = unicodedata.normalize("NFC", stripped)
    return " ".join(stripped.split())


# --- Tanzil XML ---
_arabic_tree = None
_arabic_verses = {}  # (chapter_id, verse_id) -> text


def _load_arabic():
    global _arabic_tree, _arabic_verses
    if _arabic_tree is not None:
        return
    ensure_arabic_xml()
    _arabic_tree = ET.parse(ARABIC_XML_PATH)
    root = _arabic_tree.getroot()
    ns = {}  # Tanzil has no namespace in this file
    for chapter in root.findall("Chapter"):
        cid = int(chapter.get("ChapterID", 0))
        for verse in chapter.findall("Verse"):
            vid = int(verse.get("VerseID", 0))
            text = (verse.text or "").strip()
            _arabic_verses[(cid, vid)] = text
    return


def get_verse(chapter_id: int, verse_id: int) -> str:
    """Return Arabic verse text. 1-indexed chapter/verse."""
    _load_arabic()
    return _arabic_verses.get((chapter_id, verse_id), "")


def get_chapter(chapter_id: int) -> dict:
    """Return chapter info: {id, name, verses}."""
    _load_arabic()
    verses = {vid: text for (cid, vid), text in _arabic_verses.items() if cid == chapter_id}
    root = _arabic_tree.getroot()
    for ch in root.findall("Chapter"):
        if int(ch.get("ChapterID", 0)) == chapter_id:
            return {"id": chapter_id, "name": ch.get("ChapterName", ""), "verses": verses}
    return {"id": chapter_id, "name": "", "verses": {}}


def list_chapters() -> list:
    """Return list of {id, name} for all 114 chapters."""
    _load_arabic()
    root = _arabic_tree.getroot()
    return [
        {"id": int(ch.get("ChapterID", 0)), "name": ch.get("ChapterName", "")}
        for ch in root.findall("Chapter")
    ]


def search_verses(query: str) -> list:
    """Simple substring search in Arabic verses. Returns [(chapter_id, verse_id), ...]."""
    _load_arabic()
    norm_query = normalize_arabic(query)
    if not norm_query:
        return []
    results = []
    for (cid, vid), text in _arabic_verses.items():
        if norm_query in normalize_arabic(text):
            results.append((cid, vid))
    return results


# --- Tanzil English (optional, simplified) ---
# For now we use a single English source if available; can extend later.
# Tanzil English XML has different structure - we skip for MVP and rely on Quran Enc for extra langs.

# --- Quran Enc API (Somali, Amharic, Swahili) ---
_quranenc_cache = {}  # lang -> {(sura, aya): translation}

# Quran Enc returns "7. Translation text..." - strip leading verse numbers
_RE_VERSE_NUM = re.compile(r"^\d+\.\s*")
# Footnote refs like [1], [4], [10] in translation text
_RE_FOOTNOTE = re.compile(r"\[\d+\]")


def _clean_quranenc_translation(text: str) -> str:
    """Remove leading verse numbers (e.g. 7.) and footnote refs (e.g. [4]) from Quran Enc API text."""
    if not text:
        return text
    t = _RE_VERSE_NUM.sub("", text).strip()
    t = _RE_FOOTNOTE.sub("", t)
    return " ".join(t.split())  # normalize spaces


def load_quranenc_translation(lang: str) -> bool:
    """Fetch all 114 suras from Quran Enc API, cache in memory. Returns True on success."""
    if lang not in QURANENC_TRANSLATIONS:
        return False
    if lang in _quranenc_cache:
        return True
    key = QURANENC_TRANSLATIONS[lang]
    cache = {}
    base = f"{QURANENC_BASE}/{key}"
    for sura in range(1, 115):
        try:
            r = requests.get(f"{base}/{sura}", timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("result", []):
                s = int(item.get("sura", sura))
                a = int(item.get("aya", 0))
                trans = _clean_quranenc_translation(item.get("translation") or "")
                cache[(s, a)] = trans
        except Exception as e:
            print(f"Quran Enc fetch error (sura {sura}, {lang}): {e}")
    _quranenc_cache[lang] = cache
    return True


def load_quranenc_sura(lang: str, sura: int, retries: int = 2) -> bool:
    """Lazy load: fetch one sura only. Retries on failure."""
    if lang not in QURANENC_TRANSLATIONS:
        return False
    if lang not in _quranenc_cache:
        _quranenc_cache[lang] = {}
    cache = _quranenc_cache[lang]
    key = QURANENC_TRANSLATIONS[lang]
    url = f"{QURANENC_BASE}/{key}/{sura}"
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            data = r.json()
            for item in data.get("result", []):
                s = int(item.get("sura", sura))
                a = int(item.get("aya", 0))
                trans = _clean_quranenc_translation(item.get("translation") or "")
                cache[(s, a)] = trans
            return True
        except Exception as e:
            if attempt < retries:
                continue
            print(f"Quran Enc fetch error (sura {sura}, {lang}): {e}")
            return False
    return False


def _normalize_trans_lang(lang: str) -> str:
    """Map display names ('Somali') to API keys ('somali')."""
    if not lang:
        return lang
    low = lang.strip().lower()
    for key in QURANENC_TRANSLATIONS:
        if key == low or key.replace("_", " ") == low:
            return key
    return lang


def get_translation(chapter_id: int, verse_id: int, lang: str) -> str:
    """
    Get translation for verse. lang: 'ar' (Arabic from Tanzil),
    'en', 'somali', 'amharic', 'swahili' (from Quran Enc API).
    """
    if not lang:
        return ""
    if lang == "ar":
        return get_verse(chapter_id, verse_id)
    lang = _normalize_trans_lang(lang)
    if lang in QURANENC_TRANSLATIONS:
        cache = _quranenc_cache.get(lang, {})
        key = (chapter_id, verse_id)
        if key not in cache:
            load_quranenc_sura(lang, chapter_id)
            cache = _quranenc_cache.get(lang, {})
        return cache.get(key, "")
    return ""
