#!/usr/bin/env python3
"""Voice-over through the Higgsfield CLI (text2speech_v2: elevenlabs, minimax, seed_speech, vibe_voice, cozy_voice).

  hf_voice.py cast "<line>" OUT_DIR [--engines elevenlabs,minimax] [--jobs 6] [--only Name,Name]
      Speaks one line with every preset voice (first engine each voice supports), keeps
      the take plus its metadata, and measures it. Writes OUT_DIR/catalog.json and
      OUT_DIR/ranking.md. About 0.3 credits per voice; a refused engine costs nothing.

  hf_voice.py lines SCRIPT_LINES.json OUT_DIR --voice NAME [--engine elevenlabs] [--takes 1]
      One file per script line: OUT_DIR/line-NN.wav (48 kHz mono, silence trimmed) and
      OUT_DIR/lines.json with the exact text, voice, engine and job ids.
      SCRIPT_LINES.json: {"lines": [{"line": "01", "text": "..."}]}

Measurements (cast): words per second at natural speed, pitch movement in semitones
(too flat reads robotic, too wide reads performed), and whether whisper hears the
exact words. Names and ranks only; a person casts by watching the film.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import urllib.request

CLI = "higgsfield"
# The repo root, resolved through the .claude/skills and .agents/skills symlinks.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL") or os.path.join(REPO, "models", "ggml-base.en.bin")


def voices():
    out = subprocess.run([CLI, "voices", "list", "--size", "100", "--json"], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    items, cur = d["items"], d.get("cursor")
    while cur:
        d = json.loads(subprocess.run([CLI, "voices", "list", "--size", "100", "--cursor", cur, "--json"], capture_output=True, text=True, check=True).stdout)
        items += d["items"]
        cur = d.get("cursor")
    return [v for v in items if v.get("status") == "completed"]


def speak(text, voice_id, engine, voice_type="preset"):
    """One TTS job. Returns (job dict, None) or (None, error text)."""
    r = subprocess.run([CLI, "generate", "create", "text2speech_v2", "--prompt", text, "--variant", engine,
                        "--voice_id", voice_id, "--voice_type", voice_type, "--wait", "--json"], capture_output=True, text=True)
    txt = (r.stdout or "") + (r.stderr or "")
    try:
        job = json.loads(r.stdout)[0]
        if job.get("status") == "completed" and job.get("result_url"):
            return job, None
        return None, job.get("status", "failed")
    except Exception:
        return None, txt.strip().splitlines()[0] if txt.strip() else "no output"


def to_wav(url, wav):
    mp3 = wav[:-4] + ".mp3"
    urllib.request.urlretrieve(url, mp3)
    # 48 kHz mono, leading and trailing silence trimmed at -50 dB.
    af = "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-af", af, "-ar", "48000", "-ac", "1", wav], check=True)
    return wav


def measure(wav, text):
    import librosa
    import numpy as np
    y, sr = librosa.load(wav, sr=16000, mono=True)
    dur = len(y) / sr
    words = len(re.findall(r"[A-Za-z']+", text))
    f0, vf, _ = librosa.pyin(y, fmin=60, fmax=400, sr=sr, frame_length=1024)
    f0 = f0[vf & ~np.isnan(f0)]
    med = float(np.median(f0)) if len(f0) else 0.0
    semis = 12 * np.log2(f0 / med) if len(f0) and med else np.array([0.0])
    heard = ""
    if os.path.exists(WHISPER_MODEL):
        w16 = wav[:-4] + ".16k.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-ar", "16000", "-ac", "1", w16], check=True)
        heard = subprocess.run(["whisper-cli", "-m", WHISPER_MODEL, "-f", w16, "-nt", "-np"], capture_output=True, text=True).stdout.strip()
        os.remove(w16)
    norm = lambda s: re.sub(r"[^a-z ]", "", s.lower()).split()
    exact = norm(heard) == norm(text)
    return {"dur": round(dur, 2), "wps": round(words / dur, 2), "f0_hz": round(med), "pitch_sd_st": round(float(np.std(semis)), 2),
            "pitch_range_st": round(float(np.percentile(semis, 95) - np.percentile(semis, 5)), 1), "heard": heard, "exact": exact}


def cast(a):
    os.makedirs(a.out, exist_ok=True)
    engines = a.engines.split(",")
    vs = voices()
    if a.only:
        keep = {n.strip().lower() for n in a.only.split(",")}
        vs = [v for v in vs if v["name"].lower() in keep]
    print(f"{len(vs)} voices, engines {engines}", file=sys.stderr)

    def one(v):
        path = os.path.join(a.out, re.sub(r"\W", "", v["name"]) + ".wav")
        meta = os.path.join(a.out, re.sub(r"\W", "", v["name"]) + ".json")
        if os.path.exists(meta):
            return json.load(open(meta))
        for eng in engines:
            job, err = speak(a.line, v["id"], eng, v.get("voice_type", "preset"))
            if job:
                pv = job["params"].get("voice", {})
                rec = {"name": v["name"], "id": v["id"], "engine": eng, "gender": pv.get("gender"), "age": pv.get("age"),
                       "supports": pv.get("supported_models"), "preview": pv.get("source"), "job": job["id"], "url": job["result_url"],
                       "file": os.path.basename(path)}
                to_wav(job["result_url"], path)
                rec.update(measure(path, a.line))
                json.dump(rec, open(meta, "w"), indent=1)
                return rec
            if "not available" not in err.lower() and "not supported" not in err.lower():
                return {"name": v["name"], "id": v["id"], "error": err}
        return {"name": v["name"], "id": v["id"], "error": "no requested engine supports this voice"}

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        recs = list(ex.map(one, vs))
    ok = [r for r in recs if "error" not in r]
    json.dump({"line": a.line, "voices": recs}, open(os.path.join(a.out, "catalog.json"), "w"), indent=1)

    # Rank: exact words first, pace nearest 2.5 w/s, pitch movement nearest 2.2 st (conversational, not performed).
    def score(r):
        return (0 if r["exact"] else 1, abs(r["wps"] - 2.5) / 0.4 + abs(r["pitch_sd_st"] - 2.2) / 1.0)
    ok.sort(key=score)
    rows = ["| # | Voice | Engine | Gender, age | w/s | Pitch SD st | Heard exactly |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ok, 1):
        rows.append(f"| {i} | {r['name']} | {r['engine']} | {r['gender']}, {r['age']} | {r['wps']} | {r['pitch_sd_st']} | {'yes' if r['exact'] else 'no'} |")
    open(os.path.join(a.out, "ranking.md"), "w").write(f"# Cast: {a.line}\n\n" + "\n".join(rows) + "\n\nTakes and metadata: catalog.json (Higgsfield text2speech_v2).\n")
    print(f"{len(ok)} takes, {len(recs) - len(ok)} skipped; ranking.md written")


def lines(a):
    os.makedirs(a.out, exist_ok=True)
    spec = json.load(open(a.script))
    vs = {v["name"].lower(): v for v in voices()}
    v = vs[a.voice.lower()]
    done = []
    for l in spec["lines"]:
        text = l.get("say", l["text"])  # "say" holds a phonetic respelling when needed
        for k in range(a.takes):
            job, err = speak(text, v["id"], a.engine, v.get("voice_type", "preset"))
            if not job:
                sys.exit(f"line {l['line']}: {err}")
            suffix = "" if a.takes == 1 else f"-t{k + 1}"
            to_wav(job["result_url"], os.path.join(a.out, f"line-{l['line']}{suffix}.wav"))
            done.append({"line": l["line"], "take": k + 1, "text": text, "voice": v["name"], "voice_id": v["id"], "engine": a.engine, "job": job["id"]})
            print(f"line {l['line']} take {k + 1}: ok", file=sys.stderr)
    json.dump({"provider": "higgsfield text2speech_v2", "lines": done}, open(os.path.join(a.out, "lines.json"), "w"), indent=1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("cast"); c.add_argument("line"); c.add_argument("out"); c.add_argument("--engines", default="elevenlabs,minimax"); c.add_argument("--jobs", type=int, default=6); c.add_argument("--only", default="")
    l = s.add_parser("lines"); l.add_argument("script"); l.add_argument("out"); l.add_argument("--voice", required=True); l.add_argument("--engine", default="elevenlabs"); l.add_argument("--takes", type=int, default=1)
    a = p.parse_args()
    {"cast": cast, "lines": lines}[a.cmd](a)
