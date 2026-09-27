#!/usr/bin/env python3
"""Make a clean voice line sound like an old documentary played from vinyl.

  vintage.py IN.wav OUT.wav [--crackle crackle.wav] [--crackle-db -34] [--amount 1.0]

Chain: high-pass 150 Hz and low-pass 5.8 kHz (tape and vinyl bandwidth), a small 2 kHz
presence lift, parallel tape saturation, a slow 0.6 Hz wow (about 0.3 % pitch), gentle
compression, then a vinyl surface bed (a real crackle recording, looped) under the voice.
Leading and trailing silence are trimmed first. Output 48 kHz mono, peak -1 dBFS.
"""
import argparse
import subprocess

import numpy as np
import soundfile as sf
from pedalboard import Compressor, Distortion, HighpassFilter, LowpassFilter, Pedalboard, PeakFilter

SR = 48000


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af",
                          "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                          "-ar", str(SR), "-ac", "1", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def wow(x, depth=0.003, rate=0.6):
    t = np.arange(len(x)) / SR
    # time-varying read position: a slow sine drift of the playback speed
    pos = t + depth / (2 * np.pi * rate) * np.sin(2 * np.pi * rate * t)
    return np.interp(pos * SR, np.arange(len(x)), x).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--crackle"); ap.add_argument("--crackle-db", type=float, default=-34.0)
    ap.add_argument("--amount", type=float, default=1.0)
    a = ap.parse_args()
    x = load(a.inp)
    x = np.concatenate([np.zeros(int(0.08 * SR), np.float32), x, np.zeros(int(0.25 * SR), np.float32)])
    band = Pedalboard([HighpassFilter(150), LowpassFilter(5800), PeakFilter(2000, 2.5, 0.9)])(x, SR)
    sat = Pedalboard([Distortion(drive_db=10)])(band, SR)
    y = band * (1 - 0.35 * a.amount) + sat * 0.35 * a.amount * 0.5
    y = wow(y, 0.003 * a.amount)
    y = Pedalboard([Compressor(threshold_db=-20, ratio=3, attack_ms=8, release_ms=120)])(y, SR)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.8
    if a.crackle:
        c, csr = sf.read(a.crackle, always_2d=True)
        c = c.mean(axis=1)
        if csr != SR:
            from scipy.signal import resample_poly
            c = resample_poly(c, SR, csr)
        c = np.tile(c, int(np.ceil(len(y) / len(c))))[: len(y)]
        c = c / (np.sqrt(np.mean(c ** 2)) + 1e-9) * 10 ** (a.crackle_db / 20)
        y = y + c.astype(np.float32)
    y = y / (np.max(np.abs(y)) + 1e-9) * 10 ** (-1 / 20)
    sf.write(a.out, y, SR, subtype="PCM_24")
    print(f"wrote {a.out}: {len(y) / SR:.2f} s")


if __name__ == "__main__":
    main()
