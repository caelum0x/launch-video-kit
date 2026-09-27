#!/usr/bin/env python3
"""Measure a rendered launch film the way a picky editor would, without listening.

  python3 skills/launch-review/scripts/review.py FILM.mp4 OUT_DIR [--bpm 122] [--words vo-words.json]

Writes into OUT_DIR:
  filmstrip.jpg     2 fps grid, the rhythm read (look for runs of identical frames)
  contact.jpg       12 evenly spaced frames at 480 px
  report.md         numbers with pass/warn against the launch-film targets
Measures: duration, cuts and soft transitions (scene score), longest static run,
loudness (integrated LUFS, true peak, LRA), onset density per 4 s window,
cut-to-beat offsets on the given BPM grid, silence before the end, and, with
--words, voice-over pace in words per second.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

import numpy as np


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("film")
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, default=122.0)
    ap.add_argument("--words")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.film], capture_output=True, text=True).stdout)

    rows = int(np.ceil(dur * 2 / 8))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.film, "-vf", f"fps=2,scale=320:-1,tile=8x{rows}", "-frames:v", "1", os.path.join(a.out, "filmstrip.jpg")])
    step = dur / 12
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.film, "-vf", f"fps=1/{step:.3f},scale=480:-1,tile=4x3", "-frames:v", "1", os.path.join(a.out, "contact.jpg")])

    def scenes(th: float) -> list[float]:
        s = run(["ffmpeg", "-hide_banner", "-i", a.film, "-vf", f"select='gt(scene,{th})',showinfo", "-an", "-f", "null", "-"])
        return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", s)]

    hard, soft = scenes(0.28), scenes(0.08)
    # Static runs: frame differences at 4 fps below a small threshold.
    s = run(["ffmpeg", "-hide_banner", "-i", a.film, "-vf", "fps=4,scale=320:-1,signalstats,metadata=print:key=lavfi.signalstats.YDIF", "-an", "-f", "null", "-"])
    ydif = [float(x) for x in re.findall(r"YDIF=([0-9.]+)", s)]
    longest, cur = 0, 0
    for v in ydif:
        cur = cur + 1 if v < 0.35 else 0
        longest = max(longest, cur)
    static_s = longest / 4

    e = run(["ffmpeg", "-hide_banner", "-i", a.film, "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = e[e.rfind("Summary:") :]
    I = float(re.search(r"I:\s+(-?[0-9.]+) LUFS", summ).group(1))
    LRA = float(re.search(r"LRA:\s+([0-9.]+) LU", summ).group(1))
    TP = float(re.search(r"Peak:\s+(-?[0-9.]+) dBFS", summ).group(1))

    onset_line, beat_line, tail_silence = "", "", 0.0
    try:
        import librosa

        wav = os.path.join(a.out, "_a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.film, "-ac", "1", "-ar", "22050", wav], check=True)
        y, sr = librosa.load(wav, sr=22050)
        on = librosa.onset.onset_detect(y=y, sr=sr, units="time")
        wins = [int(((on >= t) & (on < t + 4)).sum()) / 4 for t in np.arange(0, dur, 4)]
        onset_line = " ".join(f"{w:.1f}" for w in wins)
        beat = 60 / a.bpm
        offs = [min(abs(c - round(c / beat) * beat), beat) for c in soft]
        beat_line = ", ".join(f"{c:.2f}s:{o*1000:.0f}ms" for c, o in zip(soft, offs))
        rms = librosa.feature.rms(y=y)[0]
        t = librosa.times_like(rms, sr=sr)
        loud = t[rms > 0.05 * rms.max()]
        tail_silence = max(0.0, dur - float(loud.max())) if len(loud) else dur
        os.remove(wav)
    except Exception as ex:  # librosa missing: skip the audio-rhythm section
        onset_line = f"(skipped: {ex})"

    pace = ""
    if a.words:
        w = json.load(open(a.words))
        span = w[-1]["end"] - w[0]["start"]
        pace = f"{len(w)} words over {span:.1f} s = {len(w)/span:.2f} words/s (target 2.2 to 2.7)"

    def flag(ok: bool) -> str:
        return "pass" if ok else "WARN"

    report = f"""# Review: {os.path.basename(a.film)}

| Check | Value | Target | |
|---|---|---|---|
| Duration | {dur:.2f} s | per brief | |
| Hard cuts | {len(hard)} | few; continuity carries the film | {flag(len(hard) <= max(3, dur / 8))} |
| Soft transitions | {len(soft)} | 1 per 3 to 6 s | {flag(dur / 7 <= len(soft) + 1)} |
| Longest static run | {static_s:.2f} s | under 1.5 s outside the end card | {flag(static_s < 1.5)} |
| Integrated loudness | {I:.1f} LUFS | -14 ± 1 | {flag(abs(I + 14) <= 1)} |
| True peak | {TP:.1f} dBFS | ≤ -1.0 | {flag(TP <= -1.0)} |
| Loudness range | {LRA:.1f} LU | 1.5 to 6 (social launches run compressed) | {flag(1.5 <= LRA <= 6)} |
| Silence before end | {tail_silence:.2f} s | logo lands in near silence, 0.5 to 3 s | {flag(0.3 <= tail_silence <= 3.5)} |

- Onsets per second, 4 s windows: {onset_line} (action sections 2 to 4, statements under 1.5)
- Transition offsets from the {a.bpm:g} BPM grid: {beat_line or 'n/a'} (under 60 ms reads as on the beat)
- Hard cuts at: {', '.join(f'{c:.2f}' for c in hard) or 'none'}
{('- Voice-over pace: ' + pace) if pace else ''}

Look at filmstrip.jpg for rhythm and contact.jpg for composition. Numbers flag problems; only eyes pass a film.
"""
    open(os.path.join(a.out, "report.md"), "w").write(report)
    print(report)


if __name__ == "__main__":
    main()
