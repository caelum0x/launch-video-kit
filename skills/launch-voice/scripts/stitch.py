#!/usr/bin/env python3
"""Stitch voice lines onto the film timeline: python3 stitch.py placement.json <dir-with-line-NN.wav> vo.wav"""
import json, subprocess, sys
p = json.load(open(sys.argv[1])); d = sys.argv[2]; out = sys.argv[3]
args, parts = [], []
for i, l in enumerate(p["lines"]):
    args += ["-i", f"{d}/line-{l['line']}.wav"]
    ms = int(l["start"] * 1000)
    parts.append(f"[{i}:a]adelay={ms}|{ms},apad[a{i}]")
mix = "".join(f"[a{i}]" for i in range(len(p["lines"])))
fc = ";".join(parts) + f";{mix}amix=inputs={len(p['lines'])}:normalize=0,atrim=0:{p['duration']}[out]"
subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "1", out], check=True)
print("wrote", out)
