#!/usr/bin/env python3
"""
Iqra AI - Gradio app with Transcribe, Iqra, Letter Practice, Batch tabs.
"""

import json
import os
import threading

import gradio as gr

from asr_engine import transcribe as asr_transcribe
from config import DEFAULT_ASR_MODEL, QURANENC_TRANSLATIONS, TRANSLATION_LANGS
from matcher import match_and_analyze, render_alignment_html
from quran_data import get_verse, get_translation, list_chapters, load_quranenc_translation


def _preload_translations():
    """Load all Surah/ayah for all Quran Enc languages in background."""
    for lang in QURANENC_TRANSLATIONS:
        try:
            load_quranenc_translation(lang)
            print(f"Preloaded {lang} translations.")
        except Exception as e:
            print(f"Preload {lang} failed: {e}")

# Translation display names
TRANS_NAMES = {
    "ar": "Arabic",
    "en": "English",
    "somali": "Somali",
    "amharic": "Amharic",
    "swahili": "Swahili",
}

_hijaiyah_pipe = None


def _get_hijaiyah_pipe():
    global _hijaiyah_pipe
    if _hijaiyah_pipe is None:
        from transformers import pipeline
        _hijaiyah_pipe = pipeline(
            "audio-classification",
            model="ojisetyawan/whisper-base-ar-quran-ft-hijaiyah-2",
        )
    return _hijaiyah_pipe


def _transcribe_tab(audio, with_match, history):
    if audio is None:
        return "Please record or upload audio.", "", history or [], "No history yet"
    try:
        result = asr_transcribe(audio, model_id=DEFAULT_ASR_MODEL)
        text = result["text"]
        parts = [text]
        match_html = ""
        if with_match and text.strip():
            analysis = match_and_analyze(text)
            if analysis["chapter_id"]:
                parts.append(f"\n--- Match ---")
                vid_end = analysis.get("verse_id_end", analysis["verse_id"])
                ayah = f"{analysis['verse_id']}-{vid_end}" if vid_end != analysis["verse_id"] else str(analysis["verse_id"])
                parts.append(f"Surah {analysis['chapter_id']}:Ayah {ayah} | Accuracy: {analysis['accuracy_pct']}%")
                match_html = render_alignment_html(analysis["word_alignment"])
            else:
                parts.append("\n--- Match ---\nNo verse match found.")
        # Session history: last 5
        new_history = [text] + (history or [])[:4]
        hist_display = "\n".join(f"- {h[:80]}..." if len(h) > 80 else f"- {h}" for h in new_history) if new_history else "No history yet"
        return "\n".join(parts), match_html, new_history, hist_display
    except Exception as e:
        return f"Error: {e}", "", history or [], "No history yet"


def _iqra_tab(audio, surah_num, ayah_num, trans_lang):
    if audio is None:
        return "", "", ""
    try:
        result = asr_transcribe(audio, model_id=DEFAULT_ASR_MODEL)
        text = result["text"]
        analysis = match_and_analyze(text)
        html = render_alignment_html(analysis["word_alignment"]) if analysis["word_alignment"] else text
        trans = ""
        if trans_lang and trans_lang != "ar":
            cid = analysis.get("chapter_id")
            vid = analysis.get("verse_id")
            if cid and vid:
                trans = get_translation(cid, vid, trans_lang)
        return text, html, trans
    except Exception as e:
        return f"Error: {e}", "", ""


def _iqra_verse(surah_num, ayah_num, trans_lang):
    """Show canonical verse and translation for selected Surah:Ayah. RTL for Arabic."""
    if not surah_num or not ayah_num:
        return "Select Surah and Ayah.", ""
    try:
        cid = int(surah_num)
        vid = int(ayah_num)
        verse = get_verse(cid, vid)
        if not verse:
            return "Verse not found.", ""
        trans = get_translation(cid, vid, trans_lang) if trans_lang and trans_lang != "ar" else ""
        safe = verse.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        verse_html = f'<div dir="rtl" style="text-align: right; font-size: 1.2em;">{safe}</div>'
        return verse_html, trans
    except Exception as e:
        return f"Error: {e}", ""


def _letter_practice(audio):
    if audio is None:
        return "Please record a short clip (one letter)."
    try:
        pipe = _get_hijaiyah_pipe()
        preds = pipe(audio, top_k=3)
        lines = [f"{p['label']}: {p['score']*100:.1f}%" for p in preds]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _batch_tab(files):
    """Transcribe batch, return table data and ZIP path for export."""
    files = files if isinstance(files, list) else ([files] if files else [])
    if not files:
        return [], "Upload audio files.", None
    results = []
    table_rows = []
    for f in files:
        if f is None:
            continue
        path = f if isinstance(f, str) else (getattr(f, "name", None) or getattr(f, "path", str(f)))
        if not path or not os.path.isfile(path):
            continue
        try:
            r = asr_transcribe(path)
            results.append({"file": os.path.basename(path), "text": r["text"]})
            table_rows.append([os.path.basename(path), r["text"][:200] + ("..." if len(r["text"]) > 200 else "")])
        except Exception as e:
            results.append({"file": os.path.basename(path), "text": f"Error: {e}"})
            table_rows.append([os.path.basename(path), f"Error: {e}"])
    if not results:
        return [], "No valid files.", None
    # Create ZIP
    zip_path = None
    try:
        import tempfile
        import zipfile
        fd, zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for row in results:
                base = os.path.splitext(row["file"])[0]
                zf.writestr(f"{base}.txt", row["text"], zipfile.ZIP_DEFLATED)
            zf.writestr("batch_results.json", json.dumps(results, ensure_ascii=False, indent=2), zipfile.ZIP_DEFLATED)
    except Exception:
        zip_path = None
    return table_rows, json.dumps(results, ensure_ascii=False, indent=2), zip_path


# Build UI
chapters = list_chapters()
surah_choices = [f"{c['id']}. {c['name']}" for c in chapters]

with gr.Blocks(title="Iqra AI") as app:
    gr.Markdown("# Iqra AI")

    with gr.Tabs():
        with gr.TabItem("Transcribe"):
            with gr.Row():
                trans_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Audio")
                trans_out = gr.Textbox(label="Transcription", lines=10)
            trans_match_html = gr.HTML(label="Verse match (RTL)")
            trans_match = gr.Checkbox(label="Verse match", value=True)
            trans_btn = gr.Button("Transcribe")
            trans_history_state = gr.State([])
            trans_history_display = gr.Textbox(label="Session history (last 5)", lines=4, interactive=False)
            trans_btn.click(
                fn=_transcribe_tab,
                inputs=[trans_audio, trans_match, trans_history_state],
                outputs=[trans_out, trans_match_html, trans_history_state, trans_history_display],
            )

        with gr.TabItem("Iqra Mode"):
            trans_lang = gr.Dropdown(
                choices=[(TRANS_NAMES.get(l, l), l) for l in TRANSLATION_LANGS],
                value="ar",
                label="Translation language",
            )
            with gr.Row():
                iqra_surah = gr.Dropdown(choices=[str(c["id"]) for c in chapters], value="1", label="Surah")
                iqra_ayah = gr.Number(value=1, minimum=1, maximum=286, label="Ayah")
            iqra_verse_btn = gr.Button("Show verse")
            iqra_canon = gr.HTML(label="Canonical verse (Arabic, RTL)")
            iqra_trans = gr.Textbox(label="Translation", lines=5)
            iqra_verse_btn.click(
                fn=_iqra_verse,
                inputs=[iqra_surah, iqra_ayah, trans_lang],
                outputs=[iqra_canon, iqra_trans],
            )
            iqra_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record/Upload recitation")
            iqra_btn = gr.Button("Transcribe and compare")
            iqra_recited = gr.Textbox(label="Your recitation", lines=2)
            iqra_compare = gr.HTML(label="Mistake highlight")
            iqra_trans_out = gr.Textbox(label="Translation", lines=5)
            iqra_btn.click(
                fn=_iqra_tab,
                inputs=[iqra_audio, iqra_surah, iqra_ayah, trans_lang],
                outputs=[iqra_recited, iqra_compare, iqra_trans_out],
            )

        with gr.TabItem("Letter Practice"):
            lp_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Say one hijaiyah letter")
            lp_out = gr.Textbox(label="Top predictions", lines=5)
            lp_btn = gr.Button("Classify")
            lp_btn.click(fn=_letter_practice, inputs=lp_audio, outputs=lp_out)

        with gr.TabItem("Batch"):
            batch_files = gr.File(file_count="multiple", label="Upload audio files")
            batch_btn = gr.Button("Transcribe all")
            batch_table = gr.Dataframe(headers=["File", "Transcription"], label="Results (table)")
            batch_out = gr.Textbox(label="Results (JSON)", lines=10)
            batch_download = gr.File(label="Export ZIP", visible=True)
            batch_btn.click(
                fn=_batch_tab,
                inputs=batch_files,
                outputs=[batch_table, batch_out, batch_download],
            )

# Preload all translations in background so every surah/ayah is available for all lang
threading.Thread(target=_preload_translations, daemon=True).start()

# Allow Gradio to serve temp audio files (fixes red 404 on /gradio_api/file=...)
import tempfile
_temp = tempfile.gettempdir()
_temp_real = os.path.realpath(_temp)
app.launch(allowed_paths=[_temp, _temp_real])
