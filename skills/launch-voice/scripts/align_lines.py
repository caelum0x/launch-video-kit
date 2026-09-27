#!/usr/bin/env python3
"""Word timestamps line by line, which is far more precise than one pass over the whole film.

  python3 align_lines.py placement.json <dir-with-line-NN.wav> words.json

placement.json: {"duration": 27.5, "lines": [{"line": "01", "start": 0.30}, ...]}
Each line is transcribed on its own (whisper.cpp, via vo_words.py) and offset by its start,
so words.json reads in film seconds. Whole-film passes drift near line ends (one test put a
word 1.3 s after its line had ended). For words that must land on a visual, prefer force_align.py.
"""
import json
import os
import subprocess
import sys
import tempfile

here = os.path.dirname(os.path.abspath(__file__))
placement, line_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
p = json.load(open(placement))
words = []
with tempfile.TemporaryDirectory() as tmp:
    for l in p["lines"]:
        dst = os.path.join(tmp, f"w-{l['line']}.json")
        subprocess.run([sys.executable, os.path.join(here, "vo_words.py"), os.path.join(line_dir, f"line-{l['line']}.wav"), dst, "--offset", str(l["start"])], check=True, capture_output=True)
        for w in json.load(open(dst)):
            w["line"] = l["line"]
            words.append(w)
json.dump(words, open(out, "w"), indent=1)
print(f"{len(words)} words -> {out}")
