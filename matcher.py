"""
Verse matching and mistake detection (Tarteel-style).
"""

from difflib import SequenceMatcher

from quran_data import get_verse, list_chapters, normalize_arabic

# Status: correct, missed (in canonical, not recited), incorrect, extra (recited, not in canonical)
STATUS_CORRECT = "correct"
STATUS_MISSED = "missed"
STATUS_INCORRECT = "incorrect"
STATUS_EXTRA = "extra"


def align_words(recited_words: list, canonical_words: list) -> list:
    """
    Align recited vs canonical using SequenceMatcher.
    Returns list of {"word": str, "status": str, "canonical": str|None}.
    """
    recited = " ".join(recited_words) if isinstance(recited_words, list) else recited_words
    canonical = " ".join(canonical_words) if isinstance(canonical_words, list) else canonical_words
    rec_list = recited_words if isinstance(recited_words, list) else recited.split()
    can_list = canonical_words if isinstance(canonical_words, list) else canonical.split()
    if not rec_list and not can_list:
        return []
    matcher = SequenceMatcher(None, can_list, rec_list)
    alignment = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                alignment.append({"word": can_list[i1 + k], "status": STATUS_CORRECT, "canonical": can_list[i1 + k]})
        elif tag == "replace":
            for k in range(i2 - i1):
                alignment.append({"word": can_list[i1 + k], "status": STATUS_MISSED, "canonical": can_list[i1 + k]})
            for k in range(j2 - j1):
                alignment.append({"word": rec_list[j1 + k], "status": STATUS_EXTRA, "canonical": None})
        elif tag == "delete":
            for k in range(i2 - i1):
                alignment.append({"word": can_list[i1 + k], "status": STATUS_MISSED, "canonical": can_list[i1 + k]})
        elif tag == "insert":
            for k in range(j2 - j1):
                alignment.append({"word": rec_list[j1 + k], "status": STATUS_EXTRA, "canonical": None})
    return alignment


def find_best_verse(transcription: str) -> tuple:
    """
    Find best matching verse (or verse range) for transcription.
    Supports multi-verse recitation (e.g. full An-Nas); tries 1–6 verse windows.
    Returns (chapter_id, verse_id, end_verse_id, score).
    """
    if not transcription or not transcription.strip():
        return (None, None, None, 0.0)
    norm_trans = normalize_arabic(transcription)
    norm_words = norm_trans.split()
    if not norm_words:
        return (None, None, None, 0.0)
    best = (None, None, None, 0.0)
    for ch in list_chapters():
        cid = ch["id"]
        for vid in range(1, 300):
            base = get_verse(cid, vid)
            if not base:
                break
            # Try 1–6 verse windows (handles full surah recitation)
            for k in range(6):
                end = vid + k
                texts = [get_verse(cid, v) for v in range(vid, end + 1)]
                if not all(text for text in texts):
                    break
                combined = " ".join(texts)
                norm_verse = normalize_arabic(combined)
                if not norm_verse:
                    continue
                ratio = SequenceMatcher(None, norm_verse, norm_trans).ratio()
                if ratio > best[3]:
                    best = (cid, vid, end, ratio)
                    if ratio > 0.95:
                        return best  # Near-perfect match, no need to search further
    return best


def match_and_analyze(transcription: str) -> dict:
    """
    Match transcription to verse, compute alignment and accuracy.
    Returns {matched_verse, chapter_id, verse_id, accuracy_pct, word_alignment}.
    """
    cid, vid, end_vid, score = find_best_verse(transcription)
    if cid is None:
        return {"matched_verse": "", "chapter_id": None, "verse_id": None, "accuracy_pct": 0, "word_alignment": []}
    # Build canonical from verse range
    end_vid = end_vid if end_vid is not None else vid
    canonical = " ".join(get_verse(cid, v) for v in range(vid, end_vid + 1))
    rec_list = normalize_arabic(transcription).split()
    can_list = normalize_arabic(canonical).split()
    alignment = align_words(rec_list, can_list)
    correct = sum(1 for a in alignment if a["status"] == STATUS_CORRECT)
    total = len(can_list)  # accuracy = correct / canonical words
    accuracy = (correct / total * 100) if total else 0
    return {
        "matched_verse": canonical,
        "chapter_id": cid,
        "verse_id": vid,
        "verse_id_end": end_vid,
        "accuracy_pct": round(accuracy, 1),
        "word_alignment": alignment,
    }


def render_alignment_html(alignment: list, rtl: bool = True) -> str:
    """Render word alignment as HTML with Tarteel-style colors. RTL for Arabic."""
    colors = {
        STATUS_CORRECT: "#22c55e",   # green
        STATUS_MISSED: "#ef4444",    # red
        STATUS_INCORRECT: "#ef4444", # red
        STATUS_EXTRA: "#f59e0b",     # amber
    }
    parts = []
    for a in alignment:
        c = colors.get(a["status"], "#6b7280")
        w = a["word"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f'<span style="color:{c};font-weight:bold;">{w}</span>')
    inner = " ".join(parts)
    if rtl:
        return f'<div dir="rtl" style="text-align: right;">{inner}</div>'
    return inner
