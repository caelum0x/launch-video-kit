#!/usr/bin/env python3
"""Word timestamps for a voice-over, so key words can land on their visuals.

  python3 vo_words.py VO.wav OUT.json [--offset 0.4] [--model models/ggml-base.en.bin]

Runs whisper.cpp (`whisper-cli`, brew install whisper-cpp) with one word per
segment and writes [{"word": "Workflows", "start": 1.23, "end": 1.61}, ...].
`--offset` shifts every time by the clip's start on the film timeline, so the
JSON reads in film seconds. Words keep their punctuation; match on
`word.strip(".,!?").lower()` when you anchor a visual.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

# The repo root, resolved through the .claude/skills and .agents/skills symlinks.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL") or os.path.join(REPO, "models", "ggml-base.en.bin")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()
    if not os.path.exists(a.model):
        raise SystemExit(f"whisper model not found: {a.model}. Download it (docs/setup.md) or set WHISPER_MODEL.")
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "in.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.audio, "-ac", "1", "-ar", "16000", wav], check=True)
        base = os.path.join(tmp, "words")
        subprocess.run(["whisper-cli", "-m", a.model, "-f", wav, "-ml", "1", "-sow", "-oj", "-of", base], check=True, capture_output=True)
        data = json.load(open(base + ".json"))
    words = []
    for seg in data.get("transcription", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        off = seg["offsets"]
        words.append({"word": text, "start": round(off["from"] / 1000 + a.offset, 3), "end": round(off["to"] / 1000 + a.offset, 3)})
    json.dump(words, open(a.out, "w"), indent=1)
    print(f"{len(words)} words -> {a.out}; first: {words[:3]}")


if __name__ == "__main__":
    main()
