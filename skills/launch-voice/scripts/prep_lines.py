#!/usr/bin/env python3
"""Word times for every voice line in film.json, so the picture lands on the words.

  python3 skills/launch-voice/scripts/prep_lines.py film/film.json [--align auto|force|whisper|estimate]

Reads <voice_dir>/line-<id>.wav for every line in film.json and writes <voice_dir>/lines.json:
  {"02": {"text": "...", "dur": 2.61, "words": [["Acme", 0.08, 0.41], ...], "aligned": "force"}, "_meta": {...}}

Aligners, best first:
  force     torchaudio's MMS forced aligner (force_align.py): the known script matched to the audio. The
            only one precise enough for type that lands on the beat. Needs torch; with `uv` installed it
            runs in a throwaway environment (about 2 GB on the first run).
  whisper   whisper.cpp word times (vo_words.py), matched to the script in order. Up to 0.3 s late.
  estimate  words spread over the voiced part of the take by length. For scratch voices only.
auto picks force when torch imports or --align force is given, whisper when whisper-cli and its model
exist, else estimate. Run it again after every new take; build.py re-times the film from the result.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", os.path.join(REPO, "models", "ggml-base.en.bin"))


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def voiced(path):
    """Start and end of the voiced part (first and last 20 ms frame above -40 dB of the peak)."""
    y, sr = sf.read(path, always_2d=True)
    m = np.abs(y.mean(axis=1))
    hop = int(0.02 * sr)
    n = max(1, len(m) // hop)
    env = np.array([m[i * hop:(i + 1) * hop].max() if i * hop < len(m) else 0 for i in range(n)])
    on = np.nonzero(env > env.max() * 10 ** (-40 / 20))[0]
    dur = len(m) / sr
    return (on[0] * hop / sr, min(dur, (on[-1] + 1) * hop / sr), dur) if len(on) else (0.0, dur, dur)


def estimate(path, text):
    a, b, dur = voiced(path)
    ws = text.split()
    k = [len(re.sub(r"\W", "", w)) + 2 for w in ws]
    total, t, out = sum(k), a, []
    for w, kk in zip(ws, k):
        d = (b - a) * kk / total
        out.append([w, round(t, 3), round(t + d * 0.92, 3)])
        t += d
    return out


def assign(text, found):
    """Map aligner words [(word, start, end)] onto the script's words in order; gaps are interpolated."""
    ws = text.split()
    out, j = [None] * len(ws), 0
    for i, w in enumerate(ws):
        k = norm(w)
        for jj in range(j, min(len(found), j + 4)):
            f = norm(found[jj][0])
            if k and f and (f.startswith(k[:4]) or k.startswith(f[:4])):
                out[i] = [w, round(found[jj][1], 3), round(found[jj][2], 3)]
                j = jj + 1
                break
    for i in range(len(ws)):   # fill unmatched words between their neighbours
        if out[i] is None:
            prev = next((out[p] for p in range(i - 1, -1, -1) if out[p]), None)
            nxt = next((out[q] for q in range(i + 1, len(ws)) if out[q]), None)
            s = prev[2] if prev else (nxt[1] - 0.3 if nxt else 0.0)
            e = nxt[1] if nxt else s + 0.3
            out[i] = [ws[i], round(max(0.0, s), 3), round(max(s + 0.05, e), 3)]
    return out


def force(path, text):
    script = os.path.join(HERE, "force_align.py")
    try:
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        cmd = [sys.executable, script, path, text]
    except ImportError:
        if not shutil.which("uv"):
            raise RuntimeError("force alignment needs torch and torchaudio (pip install torch torchaudio) or uv")
        cmd = ["uv", "run", "-q", "--with", "torch", "--with", "torchaudio", "--with", "soundfile", "--with", "numpy", "python", script, path, text]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "force_align failed")
    return assign(text, json.loads(r.stdout.strip().splitlines()[-1]))


def whisper(path, text):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "w.json")
        subprocess.run([sys.executable, os.path.join(HERE, "vo_words.py"), path, out, "--model", WHISPER_MODEL], check=True, capture_output=True)
        found = [(w["word"], w["start"], w["end"]) for w in json.load(open(out))]
    return assign(text, found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("film")
    ap.add_argument("--align", default="auto", choices=["auto", "force", "whisper", "estimate"])
    a = ap.parse_args()
    film = json.load(open(a.film))
    vdir = os.path.join(os.path.dirname(os.path.abspath(a.film)), film.get("voice_dir", "vo/body"))
    meta_path = os.path.join(vdir, "takes.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    mode = a.align
    if mode == "auto":
        try:
            import torch  # noqa: F401
            import torchaudio  # noqa: F401
            mode = "force"
        except ImportError:
            mode = "whisper" if shutil.which("whisper-cli") and os.path.exists(WHISPER_MODEL) else "estimate"
    lines = {"_meta": {**meta, "aligned": mode}}
    for lid, text in film["lines"].items():
        path = os.path.join(vdir, f"line-{lid}.wav")
        if not os.path.exists(path):
            sys.exit(f"missing take {os.path.relpath(path)}: record line {lid} ({text!r}) or run scratch_voice.py")
        how = mode
        try:
            words = {"force": force, "whisper": whisper, "estimate": estimate}[mode](path, text)
        except Exception as e:
            print(f"line {lid}: {mode} alignment failed ({e}); estimating instead", file=sys.stderr)
            words, how = estimate(path, text), "estimate"
        lines[lid] = {"text": text, "dur": round(voiced(path)[2], 3), "words": words, "aligned": how}
        print(f"line {lid} ({how}): " + " ".join(f"{w[0]}@{w[1]:.2f}" for w in words))
    json.dump(lines, open(os.path.join(vdir, "lines.json"), "w"), indent=1)
    print(f"wrote {os.path.relpath(os.path.join(vdir, 'lines.json'))} ({mode}{', scratch voice' if meta.get('voice') == 'scratch' else ''})")
    if mode == "estimate":
        print("word times are estimates: fine for a first look; for type that lands on the beat run again with --align force "
              "(uv fetches torch once, about 2 GB) or install whisper.cpp and its model (docs/setup.md)")


if __name__ == "__main__":
    main()
