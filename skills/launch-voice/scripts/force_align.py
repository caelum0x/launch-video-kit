#!/usr/bin/env python3
"""Word times by forced alignment: the known script matched to the audio, frame by frame.

  uv run -q --with torch --with torchaudio --with soundfile python skills/launch-voice/scripts/force_align.py LINE.wav "the exact words" [out.json]

Prints (or writes) [[word, start, end], ...] in seconds. Uses torchaudio's MMS_FA wav2vec2 aligner
(1.2 GB, cached in ~/.cache/torch after the first run). Use it instead of whisper's word offsets for
anything that must land on a word: whisper.cpp can glue part of one word onto the next and put a key
word about 0.3 s late, which viewers read as the type being off beat. Words are matched by their letters (a to z and '); digits
must be spelled out in the text.
"""
import json
import re
import sys

import numpy as np
import soundfile as sf
import torch
import torchaudio
from torchaudio.pipelines import MMS_FA as bundle

path, text = sys.argv[1], sys.argv[2]
y, sr = sf.read(path, always_2d=True)
wav = torch.tensor(y.T.mean(0, keepdims=True), dtype=torch.float32)
wav = torchaudio.functional.resample(wav, sr, bundle.sample_rate)
words = text.split()
keys = [re.sub(r"[^a-z']", "", w.lower()) for w in words]
model, tok, aligner = bundle.get_model(with_star=False), bundle.get_tokenizer(), bundle.get_aligner()
with torch.inference_mode():
    em, _ = model(wav)
    spans = aligner(em[0], tok([k for k in keys if k]))
ratio = wav.size(1) / em.size(1) / bundle.sample_rate
out, si = [], 0
for w, k in zip(words, keys):
    if not k:
        continue
    s = spans[si]; si += 1
    out.append([w, round(s[0].start * ratio, 3), round(s[-1].end * ratio, 3)])
if len(sys.argv) > 3:
    json.dump(out, open(sys.argv[3], "w"), indent=1)
print(json.dumps(out))
