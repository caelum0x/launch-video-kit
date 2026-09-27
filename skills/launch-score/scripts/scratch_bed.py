#!/usr/bin/env python3
"""A free scratch music bed on the film's bar grid: a quiet intro, a drop that lands on the cut, a groove, a held end.

  python3 skills/launch-score/scripts/scratch_bed.py film/score/bed.wav [--bpm 120] [--key A] [--intro-bars 2] [--bars 28]

Synthesised and seeded (numpy only), so it costs nothing and always renders the same. It exists to cut
against: the drop sits at intro-bars bars and the script prints it, ready for film.json
"music": {"file": "score/bed.wav", "bpm": 120, "drop": 4.0}. Replace it with a real score before
anyone judges the music (launch-score: Higgsfield Sonilo or ACE-Step, placed the same way).
"""
import argparse
import json
import math
import os

import numpy as np
import soundfile as sf

SR = 48000
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n, a, r):
    t = np.arange(n) / SR
    return np.clip(t / max(a, 1e-4), 0, 1) * np.exp(-t / r)


def kick(n):
    t = np.arange(n) / SR
    f = 42 + 90 * np.exp(-t / 0.045)
    return np.sin(2 * math.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.22)


def hat(n, rng):
    x = rng.standard_normal(n)
    x = np.diff(np.concatenate([[0], x]))                 # a rough high-pass
    return x * env(n, 0.001, 0.03) * 0.25


def clap(n, rng):
    x = rng.standard_normal(n)
    from scipy.signal import butter, lfilter
    b, a = butter(2, [900 / (SR / 2), 3200 / (SR / 2)], btype="band")
    return lfilter(b, a, x) * env(n, 0.002, 0.09) * 0.6


def pad(freqs, n, rng):
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            ph = rng.uniform(0, 2 * math.pi)
            ff = f * 2 ** (det / 12)
            x += sum(np.sin(2 * math.pi * ff * h * t + ph) / h ** 1.6 for h in range(1, 6))
    a = np.minimum(1, t / 0.35) * np.minimum(1, (t[::-1]) / 0.3)
    return x * a / (len(freqs) * 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--key", default="A")
    ap.add_argument("--intro-bars", type=int, default=2)
    ap.add_argument("--bars", type=int, default=28)
    a = ap.parse_args()
    rng = np.random.default_rng(122)
    beat, bar = 60 / a.bpm, 240 / a.bpm
    n = int((a.bars * bar + 3) * SR)
    L, R = np.zeros(n), np.zeros(n)
    root = 45 + NOTE[a.key]                                 # A2 for A
    prog = [0, 8, 3, 10]                                    # i, VI, III, VII (natural minor)
    minor = {0: [0, 3, 7], 8: [0, 4, 7], 3: [0, 4, 7], 10: [0, 4, 7]}

    def put(x, t, gl=1.0, gr=1.0):
        s = int(t * SR)
        e = min(n, s + len(x))
        if e > s:
            L[s:e] += x[: e - s] * gl
            R[s:e] += x[: e - s] * gr

    for b in range(a.bars):
        t0 = b * bar
        step = prog[b % 4]
        chord = [hz(root + 12 + step + i) for i in minor[step]]
        last = b >= a.bars - 2
        groove = a.intro_bars <= b < a.bars - 2
        p = pad(chord, int(bar * SR) + int(0.3 * SR), rng) * (0.2 if groove else 0.34)
        put(p, t0, 1.0, 0.9)
        if last:
            continue
        for q in range(4):
            tb = t0 + q * beat
            if groove:
                put(kick(int(0.4 * SR)) * 0.9, tb)
                put(hat(int(0.06 * SR), rng), tb + beat / 2, 0.7, 1.0)
                if q in (1, 3):
                    put(clap(int(0.2 * SR), rng) * 0.35, tb, 1.0, 0.8)
                bass = hz(root + step - 12 + (7 if q == 3 and b % 2 else 0))
                bn = int(beat * 0.9 * SR)
                bt = np.arange(bn) / SR
                put(np.tanh(2.2 * np.sin(2 * math.pi * bass * bt)) * env(bn, 0.004, 0.25) * 0.32, tb + beat / 2)
            else:                                            # the intro: soft offbeat hats under the pad
                put(hat(int(0.05 * SR), rng) * (0.5 if b == a.intro_bars - 1 else 0.3), tb + beat / 2)
    mix = np.stack([L, R], axis=1)
    mix = mix[: int((a.bars * bar + 1.5) * SR)]
    mix *= 10 ** (-3 / 20) / (np.max(np.abs(mix)) + 1e-9)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sf.write(a.out, mix, SR, subtype="PCM_24")
    drop = round(a.intro_bars * bar, 3)
    meta = {"file": os.path.basename(a.out), "bpm": a.bpm, "key": f"{a.key} minor", "drop": drop, "bars": a.bars, "source": "scratch_bed.py (placeholder)"}
    json.dump(meta, open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"wrote {a.out}: {a.bars} bars at {a.bpm:g} BPM in {a.key} minor, drop at {drop} s")
    print(f'film.json: "music": {{"file": "score/{os.path.basename(a.out)}", "bpm": {a.bpm:g}, "drop": {drop}, "gain_db": -3}}')


if __name__ == "__main__":
    main()
