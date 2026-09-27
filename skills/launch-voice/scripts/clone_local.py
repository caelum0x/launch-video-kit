#!/usr/bin/env python3
"""A narrator line on your own machine, free, when a paid voice provider is not available.

  uv run -q --python 3.11 --with chatterbox-tts --with "transformers==4.46.3" --with "torchvision==0.21.0" --with soundfile python skills/launch-voice/scripts/clone_local.py \
      REF.wav OUT_PREFIX "The line." [takes]

Resemble AI's open Chatterbox (MIT) clones the voice in REF.wav (8 to 10 s of your approved narrator) zero-shot
and writes OUT_PREFIX-<n>.wav, 1 take per seed. Treat it as a stand-in: replace the line with a take from the
narrator's own provider when you can, then re-align it (force_align.py). Only clone a voice you have the rights to.
"""
import os
import sys

import soundfile as sf
import torch
from chatterbox.tts import ChatterboxTTS

ref, out, text = sys.argv[1], sys.argv[2], sys.argv[3]
takes = int(sys.argv[4]) if len(sys.argv) > 4 else 3
dev = "mps" if torch.backends.mps.is_available() else "cpu"
model = ChatterboxTTS.from_pretrained(device=dev)
for k in range(takes):
    torch.manual_seed(int(os.environ.get("CB_SEED", 100)) + k)
    wav = model.generate(text, audio_prompt_path=ref, exaggeration=float(os.environ.get("CB_EXAG", 0.5)), cfg_weight=float(os.environ.get("CB_CFG", 0.35)), temperature=0.7)
    sf.write(f"{out}-{k}.wav", wav.squeeze(0).cpu().numpy(), model.sr)
    print(f"{out}-{k}.wav", round(wav.shape[-1] / model.sr, 2), "s")
