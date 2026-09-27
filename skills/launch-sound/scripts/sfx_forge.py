#!/usr/bin/env python3
"""Sound forge: a synthesised, key-locked SFX palette and a cue-sheet renderer. Free, no account.

Every sound is built from first principles (modal, FM and filtered-noise synthesis),
seeded, so the same cue sheet always renders the same stem. One shared plate bus gives
every event the same acoustic space. No stock library clips and no whooshes or swells:
they are what makes a launch film sound like a template.

Usage
  python3 skills/launch-sound/scripts/sfx_forge.py palette OUT_DIR [--key A]
  python3 skills/launch-sound/scripts/sfx_forge.py render CUES.json OUT.wav [--duration S] [--key A]

Cue sheet JSON: {"duration": 20.7, "key": "A", "cues": [{"t": 1.23, "sound": "glass_tick", "gain_db": -6, "pan": 0.2, "args": {"degree": 2}}]}
A cue can also be {"t": 0, "file": "textures/room-bed.wav", "gain_db": -24, "dur": 20}: a real recording, a
generated texture or a kit hit, placed through the same plate bus. `verb_db` sets each cue's send (default -10).
A file cue with "f0" (the hit's measured fundamental, from hf_kit.py's kit.json) and "degree" is
varispeeded onto that pentatonic degree of the key, nearest octave, like a sampler; "semitones" shifts freely.
Sounds: glass_tick, felt_thump, wood_knock, key_tap, typing, press, arrive, grow, orbit_tick, logo_sting, air, sub_drop, lock
(mark_sting is an alias of logo_sting).
Shared space: the Dragonfly Plate VST3 when REVERB_VST3 points at it (or it sits in the default macOS
plug-in folder), else pedalboard's built-in reverb, else dry with a warning.
Python: your venv (numpy, scipy, soundfile, pedalboard).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import soundfile as sf

SR = 48000
REVERB_VST3 = os.path.expanduser(os.environ.get("REVERB_VST3", "~/Library/Audio/Plug-Ins/VST3/DragonflyPlateReverb.vst3"))
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
# Minor pentatonic keeps every event consonant with most scores in the same key.
PENTA = [0, 3, 5, 7, 10]


def hz(key: str, degree: int, octave: int = 5) -> float:
    """Frequency of a pentatonic degree (can exceed 4 to climb octaves) in `key`."""
    oct_shift, idx = divmod(degree, len(PENTA))
    midi = 12 * (octave + 1 + oct_shift) + NOTE[key] + PENTA[idx]
    return 440.0 * 2 ** ((midi - 69) / 12)


def t_axis(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def env_exp(dur: float, tau: float, attack: float = 0.002) -> np.ndarray:
    t = t_axis(dur)
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / tau)


def onepole_lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    from scipy.signal import lfilter

    a = math.exp(-2 * math.pi * cutoff / SR)
    return lfilter([1 - a], [1, -a], x)


def bandnoise(dur: float, lo: float, hi: float, rng: np.random.Generator) -> np.ndarray:
    n = rng.standard_normal(int(dur * SR))
    spec = np.fft.rfft(n)
    f = np.fft.rfftfreq(len(n), 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    out = np.fft.irfft(spec, len(n))
    return out / (np.max(np.abs(out)) + 1e-9)


def modal(freqs, decays, amps, dur: float) -> np.ndarray:
    t = t_axis(dur)
    out = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps):
        out += a * np.sin(2 * math.pi * f * t) * np.exp(-t / d)
    return out


def norm(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-9) * 10 ** (peak_db / 20)


# ---------------------------------------------------------------- the palette

def glass_tick(key="A", degree=2, octave=6, seed=1, **_):
    """Struck glass: inharmonic partials (free-bar ratios), bright, 0.6 s."""
    f0 = hz(key, degree, octave)
    ratios = [1.0, 2.756, 5.404, 8.933]
    x = modal([f0 * r for r in ratios], [0.35, 0.16, 0.08, 0.04], [1.0, 0.45, 0.22, 0.1], 0.7)
    click = bandnoise(0.7, 3000, 12000, np.random.default_rng(seed)) * env_exp(0.7, 0.003)
    return norm(x + 0.25 * click)


def felt_thump(seed=2, **_):
    """Soft landing: pitch-dropping sine body + felted noise. UI arrival weight."""
    dur = 0.35
    t = t_axis(dur)
    f = 150 * np.exp(-t / 0.05) + 55
    body = np.sin(2 * math.pi * np.cumsum(f) / SR) * env_exp(dur, 0.09, 0.004)
    felt = onepole_lp(bandnoise(dur, 80, 2500, np.random.default_rng(seed)), 900) * env_exp(dur, 0.02)
    return norm(body + 0.35 * felt)


def wood_knock(key="A", degree=0, seed=3, **_):
    """Hollow wood block: few damped modes around 700 to 2k Hz."""
    f0 = hz(key, degree, 5)
    x = modal([f0, f0 * 2.02, f0 * 3.9, f0 * 5.3], [0.05, 0.03, 0.018, 0.01], [1.0, 0.5, 0.3, 0.15], 0.25)
    tick = bandnoise(0.25, 2000, 9000, np.random.default_rng(seed)) * env_exp(0.25, 0.002)
    return norm(x + 0.3 * tick)


def key_tap(seed=4, **_):
    """One soft key: short filtered click with a tiny body, randomised per seed."""
    rng = np.random.default_rng(seed)
    dur = 0.09
    click = bandnoise(dur, 1500 + rng.uniform(-300, 300), 7000, rng) * env_exp(dur, 0.006 + rng.uniform(0, 0.003))
    body = np.sin(2 * math.pi * rng.uniform(180, 260) * t_axis(dur)) * env_exp(dur, 0.012)
    return norm(click + 0.35 * body, -6 + rng.uniform(-3, 0))


def typing(chars=24, cps=16.0, seed=5, **_):
    """A typed phrase: `chars` taps at `cps` with human jitter; spaces are heavier."""
    rng = np.random.default_rng(seed)
    dur = chars / cps + 0.2
    out = np.zeros(int(dur * SR))
    t = 0.0
    for i in range(chars):
        tap = key_tap(seed=seed * 100 + i)
        if rng.random() < 0.15:
            tap = tap * 1.4
        s = int(t * SR)
        out[s : s + len(tap)] += tap[: len(out) - s]
        t += (1 / cps) * rng.uniform(0.7, 1.35)
    return norm(out, -3)


def press(seed=6, **_):
    """Cursor press: high micro-click over a small felt body."""
    hi = bandnoise(0.12, 4000, 14000, np.random.default_rng(seed)) * env_exp(0.12, 0.0025)
    lo = felt_thump(seed=seed)[: int(0.12 * SR)] * 0.5
    return norm(hi + lo)


def arrive(key="A", degree=4, **_):
    """An element lands: felt body + a quiet glass note on top (pitched to the key)."""
    a = felt_thump()
    g = glass_tick(key=key, degree=degree, octave=6)
    n = max(len(a), len(g))
    out = np.zeros(n)
    out[: len(a)] += a
    out[: len(g)] += 0.35 * g
    return norm(out)


def grow(key="A", dur=1.2, seed=7, **_):
    """A connection grows: ascending pentatonic glass grains, like a branch extending."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((dur + 0.8) * SR))
    steps = max(4, int(dur * 9))
    for i in range(steps):
        t0 = dur * i / steps + rng.uniform(0, 0.01)
        deg = int(i * 7 / steps)
        g = glass_tick(key=key, degree=deg, octave=6, seed=seed + i) * (0.3 + 0.7 * i / steps)
        s = int(t0 * SR)
        out[s : s + len(g)] += g[: len(out) - s]
    return norm(out, -2)


def orbit_tick(key="A", degree=0, **_):
    """One element locking into place (a dot, a tile, a step): glass over a small wood knock."""
    g = glass_tick(key=key, degree=degree, octave=6)
    w = wood_knock(key=key, degree=degree)
    out = g * 0.8
    out[: len(w)] += 0.4 * w
    return norm(out)


def logo_sting(key="A", seed=8, **_):
    """Sonic logo: 6 glass ticks rise through the key, then a low bell lands with a long
    glass shimmer. Use it on every logo, always the same, so the sound becomes the brand's.
    Shape it after your logo when you can (a count of ticks, a rise, a landing)."""
    out = np.zeros(int(3.2 * SR))
    for i, deg in enumerate([0, 2, 3, 4, 5, 7]):
        g = glass_tick(key=key, degree=deg, octave=6, seed=seed + i) * (0.55 + 0.06 * i)
        s = int((i * 0.075) * SR)
        out[s : s + len(g)] += g[: len(out) - s]
    t = t_axis(2.8)
    f0 = hz(key, 0, 3)
    bell = modal([f0, f0 * 2.0, f0 * 3.01, f0 * 4.2, f0 * 5.4], [1.6, 1.1, 0.7, 0.45, 0.3], [1.0, 0.5, 0.35, 0.2, 0.12], 2.8)
    shimmer = sum(np.sin(2 * math.pi * hz(key, d, 7) * t + d) * np.exp(-t / 1.4) * 0.08 for d in [0, 2, 4])
    s = int(0.5 * SR)
    land = bell + shimmer + 0.6 * np.pad(felt_thump(), (0, len(t) - len(felt_thump())))
    out[s : s + len(land)] += land[: len(out) - s]
    return norm(out, -1)


def air(dur=1.0, seed=9, **_):
    """Very quiet moving air for fog passes. Not a whoosh: no pitch sweep, no swell peak."""
    rng = np.random.default_rng(seed)
    n = bandnoise(dur, 300, 5000, rng)
    t = t_axis(dur)
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return norm(onepole_lp(n, 2200) * e, -12)


def sub_drop(**_):
    """Low sine drop under a big reveal (felt, not heard on phones)."""
    dur = 1.2
    t = t_axis(dur)
    f = 70 * np.exp(-t / 0.4) + 38
    return norm(np.sin(2 * math.pi * np.cumsum(f) / SR) * env_exp(dur, 0.45, 0.01), -3)


def lock(key="A", **_):
    """Confirmation: wood knock + fifth-apart glass pair. Publish, live, done."""
    a = wood_knock(key=key, degree=0)
    g1 = glass_tick(key=key, degree=0, octave=6)
    g2 = glass_tick(key=key, degree=3, octave=6)
    out = np.zeros(len(g2) + int(0.06 * SR))
    out[: len(a)] += a
    out[: len(g1)] += 0.5 * g1
    s = int(0.06 * SR)
    out[s : s + len(g2)] += 0.5 * g2
    return norm(out)


SOUNDS = {f.__name__: f for f in [glass_tick, felt_thump, wood_knock, key_tap, typing, press, arrive, grow, orbit_tick, logo_sting, air, sub_drop, lock]}
ALIASES = {"mark_sting": "logo_sting"}


# ---------------------------------------------------------------- rendering

def pan_stereo(x: np.ndarray, pan: float) -> np.ndarray:
    th = (pan + 1) * math.pi / 4
    return np.stack([x * math.cos(th), x * math.sin(th)])


_PLUGIN = {}


def plate_bus(stereo: np.ndarray, decay=1.4, predelay=18.0, wet=100.0) -> np.ndarray:
    """Shared space, fully wet, returned for mixing under the dry signal: Dragonfly Plate if installed,
    else pedalboard's built-in reverb, else nothing (dry stem, with a warning)."""
    try:
        from pedalboard import load_plugin

        if "plate" not in _PLUGIN:  # 1 plug-in instance per process; several print harmless warnings
            _PLUGIN["plate"] = load_plugin(REVERB_VST3)
        p = _PLUGIN["plate"]
        p.reset()
        p.dry_level, p.wet_level, p.decay_s, p.predelay_ms = 0.0, wet, decay, predelay
        p.low_cut_hz, p.high_cut_hz, p.width = 180.0, 11000.0, 120.0
        return p(stereo.astype(np.float32), SR)
    except Exception as e:
        try:  # no Dragonfly: pedalboard's own reverb, band-limited like the plate
            from pedalboard import HighpassFilter, LowpassFilter, Pedalboard, Reverb

            board = Pedalboard([Reverb(room_size=0.45, damping=0.5, wet_level=1.0, dry_level=0.0, width=1.0),
                                HighpassFilter(180), LowpassFilter(11000)])
            return board(stereo.astype(np.float32), SR)
        except Exception as e2:  # nothing available: a dry stem, loudly
            print(f"warning: no reverb available ({e}; {e2}); rendering dry", file=sys.stderr)
            return np.zeros_like(stereo)


def render(cue_path: str, out_path: str, duration: float | None, key: str | None) -> None:
    sheet = json.load(open(cue_path))
    key = key or sheet.get("key", "A")
    dur = duration or sheet.get("duration") or (max(c["t"] for c in sheet["cues"]) + 4)
    dry = np.zeros((2, int(dur * SR) + SR * 3))
    send = np.zeros_like(dry)
    base = os.path.dirname(os.path.abspath(cue_path))
    for c in sheet["cues"]:
        if "file" in c:  # a real texture (Higgsfield Seed Audio, a recording): mono-summed, placed like any cue
            path = c["file"] if os.path.isabs(c["file"]) else os.path.join(base, c["file"])
            data, fsr = sf.read(path, always_2d=True)
            x = data.mean(axis=1)
            if fsr != SR:
                from scipy.signal import resample_poly

                x = resample_poly(x, SR, fsr)
            if c.get("f0") and "degree" in c:  # sampler-style: pitch the hit onto a key degree, nearest octave
                st = min((12 * math.log2(hz(key, c["degree"], o) / c["f0"]) for o in range(2, 8)), key=abs)
                st += c.get("octave_shift", 0) * 12
                if abs(st) > 0.05:
                    from scipy.signal import resample
                    x = resample(x, max(16, int(len(x) / 2 ** (st / 12))))
            elif c.get("semitones"):
                from scipy.signal import resample
                x = resample(x, max(16, int(len(x) / 2 ** (c["semitones"] / 12))))
            if c.get("dur"):
                x = x[: int(c["dur"] * SR)]
                fade = min(len(x), int(0.25 * SR))
                x[-fade:] *= np.linspace(1, 0, fade)
            x = norm(x)
        else:
            x = SOUNDS[ALIASES.get(c["sound"], c["sound"])](key=key, **c.get("args", {}))
        g = 10 ** (c.get("gain_db", -8) / 20)
        st = pan_stereo(x * g, c.get("pan", 0.0))
        s = int(c["t"] * SR)
        e = min(dry.shape[1], s + st.shape[1])
        dry[:, s:e] += st[:, : e - s]
        send[:, s:e] += st[:, : e - s] * 10 ** (c.get("verb_db", -10) / 20)
    wet = plate_bus(send)
    mix = dry + wet
    mix = mix[:, : int(dur * SR)]
    peak = np.max(np.abs(mix))
    if peak > 0.98:
        mix *= 0.98 / peak
    sf.write(out_path, mix.T, SR, subtype="PCM_24")
    print(f"wrote {out_path}: {len(sheet['cues'])} cues, {dur:.2f} s, key {key}, peak {20*np.log10(peak+1e-9):.1f} dBFS")


def palette(out_dir: str, key: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn(key=key)
        st = pan_stereo(x * 0.7, 0.0)
        wet = plate_bus(st * 0.3)
        sf.write(os.path.join(out_dir, f"{name}.wav"), (st + wet[:, : st.shape[1]]).T, SR, subtype="PCM_24")
    print(f"wrote {len(SOUNDS)} sounds to {out_dir} in {key}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("palette")
    p1.add_argument("out_dir")
    p1.add_argument("--key", default="A")
    p2 = sub.add_parser("render")
    p2.add_argument("cues")
    p2.add_argument("out")
    p2.add_argument("--duration", type=float)
    p2.add_argument("--key")
    a = ap.parse_args()
    if a.cmd == "palette":
        palette(a.out_dir, a.key)
    else:
        render(a.cues, a.out, a.duration, a.key)
