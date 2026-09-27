#!/usr/bin/env python3
"""Free placeholder voice for every line in film.json, so the film can be timed and reviewed before a real take.

  python3 skills/launch-voice/scripts/scratch_voice.py film/film.json [--voice Samantha] [--rate 185] [--hook film/hooks/<name>]

Uses macOS `say`, else `espeak-ng` or `espeak` on Linux. Writes <voice_dir>/line-<id>.wav (48 kHz mono,
silence trimmed) for every line, and with --hook the hook's voice.wav from hook.json voice.text.
It is a scratch: label every review "scratch voice" and never publish it (system voices are licensed for
personal, non-commercial use), then replace the takes with the real narrator
(hf_voice.py lines, or your own recording) and run prep_lines.py again. The picture re-times itself.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

TRIM = "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse"


def speak(text, out, voice, rate):
    with tempfile.TemporaryDirectory() as tmp:
        if shutil.which("say"):
            raw = os.path.join(tmp, "raw.aiff")
            cmd = ["say", "-r", str(rate), "-o", raw, text]
            if voice:
                cmd[1:1] = ["-v", voice]
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            raw = os.path.join(tmp, "raw.wav")
            cmd = [shutil.which("espeak-ng") or shutil.which("espeak"), "-v", "en-us", "-s", str(int(rate * 0.9)), "-w", raw, text]
        else:
            sys.exit("no local speech engine: macOS has `say`; on Linux install espeak-ng (apt install espeak-ng)")
        subprocess.run(cmd, check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", TRIM, "-ar", "48000", "-ac", "1", out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("film")
    ap.add_argument("--voice", default="Samantha" if sys.platform == "darwin" else "")
    ap.add_argument("--rate", type=int, default=185)
    ap.add_argument("--hook", help="a hook folder whose hook.json has voice.text")
    a = ap.parse_args()
    film = json.load(open(a.film))
    root = os.path.dirname(os.path.abspath(a.film))
    vdir = os.path.join(root, film.get("voice_dir", "vo/body"))
    os.makedirs(vdir, exist_ok=True)
    if shutil.which("say") and a.voice:
        voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        if not any(line.split()[0] == a.voice for line in voices.splitlines() if line.strip()):
            print(f"voice {a.voice} not installed; using the system default", file=sys.stderr)
            a.voice = ""
    for lid, text in film["lines"].items():
        speak(text, os.path.join(vdir, f"line-{lid}.wav"), a.voice, a.rate)
        print(f"line {lid}: {text}")
    json.dump({"voice": "scratch", "engine": "say" if shutil.which("say") else "espeak", "name": a.voice or "default"},
              open(os.path.join(vdir, "takes.json"), "w"), indent=1)
    if a.hook:
        hook = json.load(open(os.path.join(a.hook, "hook.json")))
        v = hook.get("voice") or {}
        if v.get("text"):
            out = os.path.join(root, v["file"]) if v.get("file") else os.path.join(a.hook, "voice.wav")
            speak(v["text"], out, a.voice, a.rate)
            print(f"hook: {v['text']} -> {os.path.relpath(out)}")
    print(f"scratch voice written to {os.path.relpath(vdir)}. Next: prep_lines.py {a.film}")


if __name__ == "__main__":
    main()
