#!/usr/bin/env python3
"""Fit voice lines into the film's frames: tighten pauses, place, speed a run up only when it must.

  fit_lines.py PLAN.json TAKES_DIR OUT_DIR

PLAN.json: {"duration": 27.541, "max_tempo": 1.12, "lines": [
  {"line": "01", "start": 0.30, "end_by": 3.80},          # earliest start; a hard end closes a run
  {"line": "02", "start": 4.05, "gap": 0.20}, ...,          # gap: breath after the previous line
  {"line": "06", "start": 15.6, "gap": 0.25, "end_by": 19.45}]}

For each line in TAKES_DIR/line-NN.wav: pauses longer than 0.25 s inside the line shrink to 0.22 s.
Lines between two hard ends form a run; a run that overflows is sped up as one (atempo, same
factor for every line, so the voice keeps one pace) up to max_tempo; beyond that the line
must be rewritten and the script says so. Writes OUT_DIR/line-NN.wav and OUT_DIR/placement.json
(stitch.py and align_lines.py read it).
"""
import json
import os
import subprocess
import sys


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)


def process(src, dst, tempo):
    af = "silenceremove=stop_periods=-1:stop_duration=0.25:stop_threshold=-45dB:stop_silence=0.22"
    if abs(tempo - 1) > 0.001:
        af += f",atempo={tempo:.4f}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", dst], check=True)
    return dur(dst)


def main():
    plan_p, takes, out = sys.argv[1:4]
    plan = json.load(open(plan_p))
    os.makedirs(out, exist_ok=True)
    lines = plan["lines"]
    maxt = plan.get("max_tempo", 1.12)
    tempo = {l["line"]: 1.0 for l in lines}
    D = {l["line"]: process(f"{takes}/line-{l['line']}.wav", f"{out}/line-{l['line']}.wav", 1.0) for l in lines}

    # runs: consecutive lines closed by a line with end_by
    runs, cur = [], []
    for l in lines:
        cur.append(l)
        if "end_by" in l:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)

    placed, prev_end, notes = [], 0.0, []

    def lay(run, prev_end, tight):
        """Preferred starts where they fit; tight packs every line after the first onto its gap."""
        pos, e = [], prev_end
        for i, l in enumerate(run):
            gap = l.get("gap", 0.2) if (i or prev_end) else 0.0
            s = e + gap if (tight and i) else max(l["start"], e + gap)
            pos.append((l["line"], s, D[l["line"]]))
            e = s + D[l["line"]]
        return pos, e

    for run in runs:
        end_by = run[-1].get("end_by", plan["duration"])
        pos, e = lay(run, prev_end, False)
        if e > end_by:
            pos, e = lay(run, prev_end, True)
        if e > end_by:
            speech = sum(D[l["line"]] for l in run)
            avail = end_by - pos[0][1] - sum(l.get("gap", 0.2) for l in run[1:])
            t = speech / avail * 1.005
            if t > maxt:
                notes.append(f"run {run[0]['line']}-{run[-1]['line']} needs tempo {t:.3f} > {maxt}: rewrite a line")
                t = maxt
            for l in run:
                D[l["line"]] = process(f"{takes}/line-{l['line']}.wav", f"{out}/line-{l['line']}.wav", t)
                tempo[l["line"]] = t
            pos, e = lay(run, prev_end, False)
            if e > end_by:
                pos, e = lay(run, prev_end, True)
        placed += pos
        prev_end = e

    res = {"duration": plan["duration"], "source": os.path.abspath(takes),
           "lines": [{"line": n, "start": round(s, 3), "end": round(s + d, 3), "tempo": round(tempo[n], 3)} for n, s, d in placed]}
    json.dump(res, open(f"{out}/placement.json", "w"), indent=1)
    for r in res["lines"]:
        print(f"line {r['line']}: {r['start']:6.2f} to {r['end']:6.2f}  tempo {r['tempo']}")
    for n in notes:
        print("WARN", n)


if __name__ == "__main__":
    main()
