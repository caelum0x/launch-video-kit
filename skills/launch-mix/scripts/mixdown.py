#!/usr/bin/env python3
"""Mix and master a launch film: music bus, SFX bus, voice bus -> -14 LUFS, -1 dBTP.

  python3 skills/launch-mix/scripts/mixdown.py MIX.json      (from your venv: numpy, soundfile, pedalboard, pyloudnorm)

MIX.json
{
  "duration": 20.7,
  "out": "out/audio/master.wav",
  "music": {"file": "score/take-1.wav", "gain_db": -2, "start": 0.0, "offset": 0.0, "fade_out": 1.5},
  "sfx":   {"file": "sfx/sfx.wav", "gain_db": -3},
  "voice": {"file": "vo/vo.wav", "gain_db": 0, "start": 0.4},
  "duck":  {"depth_db": 9, "attack": 0.08, "release": 0.35},
  "drop_out": [{"start": 18.9, "end": 20.7}],
  "target_lufs": -14.0, "ceiling_dbtp": -1.0,
  "video": "out/film.mp4", "video_out": "out/film-mixed.mp4"
}

Why these moves: the bed ducks from the voice's real envelope (not a fixed volume),
a 2.5 kHz dip opens space for consonants, the SFX bus is glued by a gentle compressor
and shares nothing with the bed, and `drop_out` mutes the music for a logo that lands
in silence (strong launch films drop the music just before the logo). Loudness is set after the
limiter with pyloudnorm and checked again with ffmpeg ebur128 (true peak).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from pedalboard import Compressor, Gain, HighpassFilter, HighShelfFilter, Limiter, LowShelfFilter, PeakFilter, Pedalboard
from pedalboard.io import AudioFile

SR = 48000


def load(path: str, dur: float, start: float = 0.0, offset: float = 0.0) -> np.ndarray:
    with AudioFile(path).resampled_to(SR) as f:
        x = f.read(f.frames)
    if x.shape[0] == 1:
        x = np.repeat(x, 2, axis=0)
    x = x[:2, int(offset * SR) :]
    out = np.zeros((2, int(dur * SR)), dtype=np.float32)
    s = int(start * SR)
    n = min(out.shape[1] - s, x.shape[1])
    if n > 0:
        out[:, s : s + n] = x[:, :n]
    return out


def envelope(x: np.ndarray, attack: float, release: float) -> np.ndarray:
    """Peak follower on the mono sum, in linear units 0..1."""
    mono = np.abs(x).mean(axis=0)
    a = np.exp(-1 / (attack * SR))
    r = np.exp(-1 / (release * SR))
    env = np.zeros_like(mono)
    acc = 0.0
    # Vectorised enough for 1-minute films; process in blocks of 64 samples.
    blk = 64
    for i in range(0, len(mono), blk):
        v = mono[i : i + blk].max()
        acc = a * acc + (1 - a) * v if v > acc else r * acc + (1 - r) * v
        env[i : i + blk] = acc
    return env / (env.max() + 1e-9)


def db(x: float) -> float:
    return 10 ** (x / 20)


def main(cfg_path: str) -> None:
    cfg = json.load(open(cfg_path))
    base = os.path.dirname(os.path.abspath(cfg_path))
    P = lambda p: p if os.path.isabs(p) else os.path.join(base, p)  # noqa: E731
    dur = float(cfg["duration"])
    mix = np.zeros((2, int(dur * SR)), dtype=np.float32)

    voice = None
    if cfg.get("voice"):
        v = cfg["voice"]
        voice = load(P(v["file"]), dur, v.get("start", 0.0)) * db(v.get("gain_db", 0))
        voice = Pedalboard([HighpassFilter(80), Compressor(threshold_db=-20, ratio=3, attack_ms=5, release_ms=80), PeakFilter(3200, 2.0, 1.0)])(voice, SR)

    if cfg.get("music"):
        m = cfg["music"]
        bed = load(P(m["file"]), dur, m.get("start", 0.0), m.get("offset", 0.0)) * db(m.get("gain_db", 0))
        bed = Pedalboard([HighpassFilter(28), LowShelfFilter(90, 1.0, 0.7), HighShelfFilter(9000, 0.5, 0.7)])(bed, SR)
        gain = np.ones(bed.shape[1], dtype=np.float32)
        if voice is not None:
            d = cfg.get("duck", {})
            env = envelope(voice, d.get("attack", 0.08), d.get("release", 0.35))
            gain *= 1 - (1 - db(-d.get("depth_db", 9))) * np.clip(env * 1.6, 0, 1)
            # Presence carve under speech: a static dip blended by the same envelope.
            carved = Pedalboard([PeakFilter(2500, -4.0, 0.8)])(bed, SR)
            k = np.clip(env * 1.6, 0, 1)
            bed = bed * (1 - k) + carved * k
        fade_out = m.get("fade_out", 1.2)
        n = int(fade_out * SR)
        gain[-n:] *= np.linspace(1, 0, n)
        for w in cfg.get("drop_out", []):
            s, e = int(w["start"] * SR), int(w["end"] * SR)
            ramp = int(0.08 * SR)
            gain[s : s + ramp] *= np.linspace(1, 0, ramp)[: max(0, min(ramp, len(gain) - s))]
            gain[s + ramp : e] = 0
        mix += bed * gain

    if cfg.get("sfx"):
        s = cfg["sfx"]
        fx = load(P(s["file"]), dur, s.get("start", 0.0)) * db(s.get("gain_db", 0))
        fx = Pedalboard([HighpassFilter(40), Compressor(threshold_db=-18, ratio=2.5, attack_ms=2, release_ms=120)])(fx, SR)
        mix += fx

    if voice is not None:
        mix += voice

    # Pedalboard's Limiter behaves like a maximiser (its output level barely follows the input),
    # so the ceiling is a look-ahead brickwall written here: per-millisecond block peaks, one
    # block of look-ahead, exponential release, then a hard safety clip at the ceiling.
    def limit(x: np.ndarray, ceiling_db: float, release_s: float = 0.08) -> np.ndarray:
        c = db(ceiling_db)
        B = 48
        n = x.shape[1]
        nb = -(-n // B)
        pad = np.zeros((x.shape[0], nb * B), dtype=np.float64)
        pad[:, :n] = x
        peaks = np.abs(pad).max(axis=0).reshape(nb, B).max(axis=1)
        g_raw = np.minimum(1.0, c / np.maximum(peaks, 1e-9))
        g_la = np.minimum(g_raw, np.append(g_raw[1:], 1.0))
        rel = 1 - np.exp(-B / (release_s * SR))
        g = np.empty(nb)
        prev = 1.0
        for i in range(nb):
            prev = min(g_la[i], prev + (1 - prev) * rel)
            g[i] = prev
        gs = np.interp(np.arange(n), np.arange(nb) * B + B / 2, g)
        return np.clip(x * gs, -c, c).astype(np.float32)

    master = Pedalboard([Compressor(threshold_db=-14, ratio=1.8, attack_ms=25, release_ms=180)])(mix, SR)
    meter = pyln.Meter(SR)
    target = cfg.get("target_lufs", -14.0)
    ceil_db = cfg.get("ceiling_dbtp", -1.0) - 0.3  # margin for inter-sample peaks
    for _ in range(3):  # gain to target, limit, re-measure: converges in 2 or 3 passes
        loud = meter.integrated_loudness(np.ascontiguousarray(master.T, dtype=np.float64))
        print(f"  pass: {loud:.2f} LUFS, peak {20 * np.log10(np.abs(master).max() + 1e-12):.2f} dBFS, shape {master.shape}, dtype {master.dtype}")
        if abs(loud - target) < 0.1:
            break
        master = limit(master * db(target - loud), ceil_db)
    out = P(cfg.get("out", "master.wav"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sf.write(out, master.T, SR, subtype="PCM_24")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    summ = r[r.rfind("Summary:") :]
    print(f"wrote {out}\n{summ.strip()}")
    if cfg.get("video"):
        vout = P(cfg.get("video_out", cfg["video"].replace(".mp4", "-mixed.mp4")))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", P(cfg["video"]), "-i", out, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", vout], check=True)
        print(f"muxed {vout}")


if __name__ == "__main__":
    main(sys.argv[1])
