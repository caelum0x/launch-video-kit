#!/usr/bin/env python3
"""Score a launch film with Higgsfield Sonilo Music, fitted to the film's act map.

  python3 skills/launch-score/scripts/hf_score.py SCORE.json OUT_DIR [--takes 3]
  python3 skills/launch-score/scripts/hf_score.py SCORE.json OUT_DIR --analyse-only

SCORE.json is launch-score's format (caption, bpm, key, sections with tag, note, bars).
Sonilo takes a prompt and a duration, not a bar map, so the arrangement is written into the
prompt in seconds and each take is then measured and fitted:

  1. tempo (librosa); a take within 4 % of the plan is time-stretched to the exact BPM,
  2. the offset into the take whose loudness curve best matches the planned section energy
     (Intro 1, Build 2, Drop 3, Breakdown 1.5, Outro 1), searched on the take's own beats
     so film cuts stay on its downbeats,
  3. the fitted section loudness, written to score.meta.json with the chosen take and offset.

Output: OUT_DIR/sonilo-N.wav (as delivered), OUT_DIR/take-N.wav (stretched, 48 kHz stereo),
OUT_DIR/score.meta.json. launch-mix reads music.file and music.offset from the meta.
Cost: about 1.9 credits per 30 s take (quoted 2026-09); check `higgsfield account transactions`.
In 2026-09 tests Sonilo wrote at 120 BPM whatever the prompt asked (3 of 3 takes); a stretch to 122 is 1.7 % and inaudible.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

import numpy as np

SR = 48000
ENERGY = {"intro": 1.0, "build": 2.0, "drop": 3.0, "breakdown": 1.5, "outro": 1.0}


def plan(score):
    bar = 60 / score["bpm"] * 4
    t, out = 0.0, []
    for s in score["sections"]:
        out.append({"tag": s["tag"], "note": s.get("note", ""), "start": round(t, 3), "end": round(t + s["bars"] * bar, 3)})
        t += s["bars"] * bar
    return out, t


def prompt(score, secs):
    arr = "; ".join(f"{s['start']:.0f} to {s['end']:.0f} s {s['tag'].lower()}: {s['note']}" for s in secs)
    return f"{score['caption']}. {score['bpm']} BPM, {score['key']}, steady tempo, 4/4. Arrangement: {arr}. Instrumental only, no vocals."


def generate(score, secs, total, out, n):
    p = prompt(score, secs)
    dur = int(np.ceil(total + 4))
    for i in range(1, n + 1):
        raw = os.path.join(out, f"sonilo-{i}.wav")
        if os.path.exists(raw):
            continue
        r = subprocess.run(["higgsfield", "generate", "create", "sonilo_music", "--prompt", p, "--duration", str(dur), "--wait", "--json"],
                           capture_output=True, text=True)
        try:
            job = json.loads(r.stdout)[0]
            assert job["status"] == "completed"
        except Exception:
            sys.exit(f"take {i}: {(r.stdout + r.stderr).strip()[:300]}")
        tmp = raw + ".download"
        urllib.request.urlretrieve(job["result_url"], tmp)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ar", str(SR), "-ac", "2", raw], check=True)
        os.remove(tmp)
        json.dump({"job": job["id"], "prompt": p, "duration": dur}, open(raw[:-4] + ".json", "w"), indent=1)
        print(f"take {i}: generated", file=sys.stderr)
    return p


def fine_tempo(mono, bpm):
    """Autocorrelation of the onset envelope with a parabolic peak: librosa's beat_track tempo
    snaps to coarse bins (a 120 BPM take reads as 117.5), which would stretch the take wrongly."""
    import librosa
    fps = 22050 / 256
    oenv = librosa.onset.onset_strength(y=mono, sr=22050, hop_length=256)
    ac = librosa.autocorrelate(oenv, max_size=len(oenv))
    lags = np.arange(len(ac))
    cand = 60 * fps / np.maximum(lags, 1)
    sel = (cand > bpm * 0.8) & (cand < bpm * 1.2)
    lag = int(lags[sel][np.argmax(ac[sel])])
    a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
    return float(60 * fps / (lag + 0.5 * (a - c) / (a - 2 * b + c)))


def fit(path, score, secs, total, out, i):
    import librosa
    import pedalboard
    import soundfile as sf
    y, _ = sf.read(path, always_2d=True)
    mono = librosa.resample(y.mean(axis=1), orig_sr=SR, target_sr=22050)
    tempo = fine_tempo(mono, score["bpm"])
    ratio = score["bpm"] / tempo
    stretched = abs(ratio - 1) <= 0.04
    if stretched and abs(ratio - 1) > 0.002:
        y = pedalboard.time_stretch(y.T.astype(np.float32), SR, stretch_factor=ratio).T
    take = os.path.join(out, f"take-{i}.wav")
    sf.write(take, y, SR, subtype="PCM_24")
    mono = librosa.resample(y.mean(axis=1), orig_sr=SR, target_sr=22050)
    _, beats = librosa.beat.beat_track(y=mono, sr=22050, start_bpm=score["bpm"], units="time", tightness=400)
    hop = 0.25
    n = int(len(mono) / 22050 / hop)
    rms = np.array([np.sqrt(np.mean(mono[int(k * hop * 22050): int((k + 1) * hop * 22050)] ** 2)) + 1e-9 for k in range(n)])
    db = 20 * np.log10(rms)
    want = np.array([ENERGY.get(next((s["tag"].lower() for s in secs if s["start"] <= k * hop < s["end"]), "outro"), 1.0) for k in range(int(total / hop))])
    best = (-2, 0.0)
    for b in beats:
        k0 = int(round(b / hop))
        if k0 + len(want) > len(db):
            break
        seg = db[k0: k0 + len(want)]
        c = float(np.corrcoef(seg, want)[0, 1])
        if c > best[0]:
            best = (c, float(b))
    corr, off = best
    per = []
    for s in secs:
        a, e = int((off + s["start"]) / hop), int((off + s["end"]) / hop)
        per.append({"tag": s["tag"], "lufs_proxy_db": round(float(np.mean(db[a:e])), 1)})
    return {"take": i, "file": os.path.basename(take), "tempo_found": round(tempo, 1), "stretched": stretched,
            "offset": round(off, 3), "energy_fit": round(corr, 3), "sections": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("score"); ap.add_argument("out")
    ap.add_argument("--takes", type=int, default=3); ap.add_argument("--analyse-only", action="store_true")
    a = ap.parse_args()
    score = json.load(open(a.score))
    secs, total = plan(score)
    os.makedirs(a.out, exist_ok=True)
    p = prompt(score, secs) if a.analyse_only else generate(score, secs, total, a.out, a.takes)
    takes = sorted(f for f in os.listdir(a.out) if f.startswith("sonilo-") and f.endswith(".wav"))
    res = [fit(os.path.join(a.out, f), score, secs, total, a.out, int(f[7:-4])) for f in takes]
    res.sort(key=lambda r: (not r["stretched"], -r["energy_fit"]))
    meta = {"provider": "higgsfield sonilo_music", "prompt": p, "bpm": score["bpm"], "key": score["key"], "sections": secs,
            "takes": res, "chosen": res[0]["file"] if res else None, "offset": res[0]["offset"] if res else 0}
    json.dump(meta, open(os.path.join(a.out, "score.meta.json"), "w"), indent=1)
    for r in res:
        print(f"take {r['take']}: {r['tempo_found']} BPM{' (stretched)' if r['stretched'] else ''}, offset {r['offset']} s, energy fit {r['energy_fit']}")


if __name__ == "__main__":
    main()
