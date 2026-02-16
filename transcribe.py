#!/usr/bin/env python3
"""
Transcribe Quranic Arabic audio. Supports multiple models, batch, verse matching, export.
"""

import argparse
import json
import os

from asr_engine import get_device, transcribe as asr_transcribe
from config import DEFAULT_ASR_MODEL
from matcher import match_and_analyze


def main():
    parser = argparse.ArgumentParser(description="Transcribe Quran audio with Whisper")
    parser.add_argument("audio_path", nargs="?", help="Path to audio file")
    parser.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto", help="Device")
    parser.add_argument("--batch", metavar="DIR", help="Batch transcribe all audio in directory")
    parser.add_argument("--export-dir", metavar="DIR", help="Output directory for batch export")
    parser.add_argument("--match", action="store_true", help="Run verse matcher, print Surah:Ayah + accuracy")
    parser.add_argument("--export", choices=["txt", "json", "srt"], help="Export format")
    parser.add_argument("--timestamps", action="store_true", help="Include timestamps")
    args = parser.parse_args()

    if args.batch:
        _batch(args)
        return

    if not args.audio_path or not os.path.isfile(args.audio_path):
        parser.error("Provide a valid audio file path (or --batch DIR)")

    print(f"Using device: {get_device()}")
    print(f"Transcribing: {args.audio_path}")

    result = asr_transcribe(args.audio_path, model_id=DEFAULT_ASR_MODEL, return_timestamps=args.timestamps)
    text = result["text"]
    chunks = result.get("chunks", [])

    print("\n--- Transcription ---")
    print(text)

    if args.match:
        analysis = match_and_analyze(text)
        if analysis["chapter_id"]:
            print(f"\n--- Match ---")
            vid_end = analysis.get("verse_id_end", analysis["verse_id"])
            ayah = f"{analysis['verse_id']}-{vid_end}" if vid_end != analysis["verse_id"] else str(analysis["verse_id"])
            print(f"Surah {analysis['chapter_id']}:Ayah {ayah} | Accuracy: {analysis['accuracy_pct']}%")
        else:
            print("\n--- Match ---\nNo verse match found.")

    if args.export:
        base = os.path.splitext(args.audio_path)[0]
        if args.export == "txt":
            path = base + ".txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\nExported: {path}")
        elif args.export == "json":
            path = base + ".json"
            data = {"text": text, "chunks": chunks}
            if args.match:
                data["match"] = match_and_analyze(text)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\nExported: {path}")
        elif args.export == "srt":
            path = base + ".srt"
            lines = []
            for i, c in enumerate(chunks, 1):
                ts = c.get("timestamp", (0, 0))
                start = _ts_to_srt(ts[0])
                end = _ts_to_srt(ts[1]) if len(ts) > 1 else start
                lines.append(f"{i}\n{start} --> {end}\n{c.get('text','')}\n")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"\nExported: {path}")


def _ts_to_srt(sec):
    if isinstance(sec, (int, float)):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
    return "00:00:00,000"


def _batch(args):
    import glob
    exts = "*.wav *.mp3 *.flac *.m4a *.ogg *.webm".split()
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(args.batch, ext)))
    files = sorted(set(files))
    if not files:
        print(f"No audio files in {args.batch}")
        return
    out_dir = args.export_dir or args.batch
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for fp in files:
        result = asr_transcribe(fp, model_id=DEFAULT_ASR_MODEL, return_timestamps=args.timestamps)
        analysis = match_and_analyze(result["text"]) if args.match else {}
        results.append({"file": os.path.basename(fp), "text": result["text"], "match": analysis})
        out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(fp))[0] + ".txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result["text"])
    if args.export_dir:
        jpath = os.path.join(out_dir, "batch_results.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Batch done. {len(files)} files -> {out_dir}")


if __name__ == "__main__":
    main()
