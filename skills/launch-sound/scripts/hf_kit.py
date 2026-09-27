#!/usr/bin/env python3
"""Sound kits from Higgsfield (Seed Audio, Mirelo): one prompt, several separated hits, sliced into one-shots.

  python3 skills/launch-sound/scripts/hf_kit.py generate KITS.json OUT_DIR   # each kit once (skips kits on disk), slice, measure
  python3 skills/launch-sound/scripts/hf_kit.py slice OUT_DIR                # re-slice the raw takes without spending credits

Start from skills/launch-sound/references/kits.example.json. OUT_DIR/kits.json must exist for `slice`.

KITS.json: {"kits": [{"name": "glass", "model": "seed_audio", "prompt": "...", "hits": 6, "pitched": true, "max_len": 1.5},
                     {"name": "air", "model": "mirelo_text_to_audio", "duration": 3, "prompt": "...", "hits": 1}]}

Writes OUT_DIR/raw/<name>.wav (the take as delivered), OUT_DIR/<name>-NN.wav (trimmed one-shots, 48 kHz mono)
and OUT_DIR/kit.json: per hit its duration, peak, and for pitched kits its fundamental in Hz, so
sfx_forge can pitch each hit into the film's key ("f0" plus "degree" on a file cue).
Why kits: Seed Audio bills per job (about 1.7 to 2.1 credits in 2026-09, whatever the quote says), so 6 hits per
job is 6 variations for the price of 1, and variations keep repeated events from sounding cloned.
"""
import json
import os
import subprocess
import sys
import urllib.request

import numpy as np
import soundfile as sf

SR = 48000
CLI = "higgsfield"


def run_kit(k, raw):
    args = [CLI, "generate", "create", k["model"], "--prompt", k["prompt"], "--wait", "--json"]
    if k["model"] == "seed_audio":
        args += ["--sample_rate", "48000", "--format", "wav"]
    if k.get("duration"):
        args += ["--duration", str(k["duration"])]
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        job = json.loads(r.stdout)[0]
    except Exception:
        sys.exit(f"{k['name']}: {(r.stdout + r.stderr).strip()[:300]}")
    if job.get("status") != "completed":
        sys.exit(f"{k['name']}: {job.get('status')}")
    tmp = raw + ".download"
    urllib.request.urlretrieve(job["result_url"], tmp)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ar", str(SR), "-ac", "1", raw], check=True)
    os.remove(tmp)
    return job["id"]


def envelope(x, hop):
    n = len(x) // hop
    return 20 * np.log10(np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9)


def slice_hits(x, hits, max_len=1.5):
    """Split a take into its events at detected onsets (notes that ring into each other still
    split). A hit runs to the next onset, to the take's noise floor (+6 dB) or to max_len
    seconds, whichever comes first; onsets weaker than 30 dB under the loudest are dropped."""
    import librosa
    if hits <= 1:
        on = np.nonzero(np.abs(x) > np.max(np.abs(x)) * 10 ** (-40 / 20))[0]
        return [x[max(0, on[0] - 240): min(on[-1] + 1, on[0] + int(max_len * SR))]] if len(on) else []
    hop = int(0.005 * SR)
    env = envelope(x, hop)
    noise = np.percentile(env, 10)
    ons = librosa.onset.onset_detect(y=x.astype(np.float32), sr=SR, hop_length=hop, backtrack=True, units="samples",
                                     pre_max=6, post_max=6, delta=0.08, wait=30)
    peaks = [envelope(x[o: o + int(0.08 * SR)], hop).max() if o + hop < len(x) else -120 for o in ons]
    top = max(peaks) if peaks else 0
    ons = [o for o, p in zip(ons, peaks) if p > top - 30 and p > noise + 12]
    out = []
    for i, o in enumerate(ons):
        s = max(0, o - int(0.003 * SR))
        limit = min(ons[i + 1] if i + 1 < len(ons) else len(x), s + int(max_len * SR))
        pk = envelope(x[s: s + int(0.08 * SR)], hop).max()
        stop = max(pk - 48, noise + 6)
        e = s + int(0.03 * SR)
        while e < limit - hop and envelope(x[e: e + hop], hop)[0] > stop:
            e += hop
        seg = x[s:e].copy()
        if len(seg) < int(0.03 * SR):
            continue
        f_in, f_out = int(0.002 * SR), min(int(0.03 * SR), len(seg) // 3)
        seg[:f_in] *= np.linspace(0, 1, f_in)
        seg[-f_out:] *= np.linspace(1, 0, f_out)
        out.append(seg)
    return out


def fundamental(seg):
    import librosa
    y = librosa.resample(seg[: int(0.4 * SR)], orig_sr=SR, target_sr=22050)
    f0, vf, _ = librosa.pyin(y, fmin=80, fmax=2000, sr=22050, frame_length=2048)
    f0 = f0[vf & ~np.isnan(f0)]
    if len(f0):
        return float(np.median(f0))
    spec = np.abs(np.fft.rfft(seg[: 8192] * np.hanning(min(8192, len(seg))), n=8192))
    freqs = np.fft.rfftfreq(8192, 1 / SR)
    band = (freqs > 80) & (freqs < 4000)
    return float(freqs[band][np.argmax(spec[band])])


def do_slice(spec, out):
    kit = {}
    for k in spec["kits"]:
        raw = os.path.join(out, "raw", k["name"] + ".wav")
        if not os.path.exists(raw):
            continue
        x, _ = sf.read(raw)
        hits = slice_hits(x, k.get("hits", 1), k.get("max_len", 1.5))
        for f in os.listdir(out):
            if f.startswith(k["name"] + "-") and f.endswith(".wav"):
                os.remove(os.path.join(out, f))
        rows = []
        for i, h in enumerate(hits, 1):
            h = h / (np.max(np.abs(h)) + 1e-9) * 0.9
            fn = f"{k['name']}-{i:02d}.wav"
            sf.write(os.path.join(out, fn), h, SR, subtype="PCM_24")
            row = {"file": fn, "dur": round(len(h) / SR, 3)}
            if k.get("pitched"):
                row["f0"] = round(fundamental(h), 1)
            rows.append(row)
        kit[k["name"]] = {"prompt": k["prompt"], "model": k["model"], "asked": k.get("hits", 1), "got": len(rows), "hits": rows}
        print(f"{k['name']}: {len(rows)} of {k.get('hits', 1)} hits")
    old = json.load(open(os.path.join(out, "kit.json"))) if os.path.exists(os.path.join(out, "kit.json")) else {}
    for n, v in kit.items():
        v["job"] = old.get(n, {}).get("job", v.get("job"))
    old.update(kit)
    json.dump(old, open(os.path.join(out, "kit.json"), "w"), indent=1)


def generate(spec_path, out):
    spec = json.load(open(spec_path))
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    if os.path.abspath(spec_path) != os.path.abspath(os.path.join(out, "kits.json")):
        json.dump(spec, open(os.path.join(out, "kits.json"), "w"), indent=1)  # so `slice OUT_DIR` works later
    jobs = {}
    for k in spec["kits"]:
        raw = os.path.join(out, "raw", k["name"] + ".wav")
        if os.path.exists(raw):
            continue
        jobs[k["name"]] = run_kit(k, raw)
        print(f"{k['name']}: generated", file=sys.stderr)
    do_slice(spec, out)
    kit = json.load(open(os.path.join(out, "kit.json")))
    for n, j in jobs.items():
        kit[n]["job"] = j
    json.dump(kit, open(os.path.join(out, "kit.json"), "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "generate":
        generate(sys.argv[2], sys.argv[3])
    elif cmd == "slice":
        spec = json.load(open(os.path.join(sys.argv[2], "kits.json")))
        do_slice(spec, sys.argv[2])
    else:
        sys.exit(__doc__)
