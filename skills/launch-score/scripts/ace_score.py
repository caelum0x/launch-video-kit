#!/usr/bin/env python3
"""Score a launch film with ACE-Step 1.5 (MIT, local, Apple Silicon via MLX).

Run with ACE-Step's own interpreter (install ACE-Step 1.5 anywhere, point ACE_STEP_ROOT at it):
  $ACE_STEP_ROOT/.venv/bin/python skills/launch-score/scripts/ace_score.py SCORE.json OUT_DIR

SCORE.json
{
  "caption": "warm modern house, felt piano, soft sub bass, airy pads, no vocals",
  "bpm": 122, "key": "A minor", "timesignature": "4",
  "sections": [
    {"tag": "Intro", "note": "felt piano and air only", "bars": 4},
    {"tag": "Build", "note": "kick enters, hats open", "bars": 8},
    {"tag": "Drop", "note": "full groove, bass up", "bars": 8},
    {"tag": "Breakdown", "note": "drums out, pads", "bars": 4},
    {"tag": "Outro", "note": "one sustained chord, then silence", "bars": 2}
  ],
  "takes": 2, "seed": 122, "model": "acestep-v15-turbo", "steps": 8
}

Duration is derived from the bars and BPM so the arrangement sits on the edit's
beat grid (bar = 4 beats). Section tags go into the lyrics field as the energy
map; `instrumental` is forced on. Output: OUT_DIR/take-N.wav plus score.meta.json
with the section start times in seconds, for the edit and the sound design.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.expanduser(os.environ.get("ACE_STEP_ROOT", "~/ACE-Step-1.5"))
sys.path.insert(0, ROOT)


def plan(score: dict) -> tuple[str, float, list[dict]]:
    bpm = float(score.get("bpm", 122))
    beats_per_bar = int(str(score.get("timesignature", "4")).split("/")[0])
    bar_s = 60.0 / bpm * beats_per_bar
    t = 0.0
    marks = []
    lines = []
    for s in score["sections"]:
        dur = s["bars"] * bar_s
        marks.append({"tag": s["tag"], "start_s": round(t, 3), "end_s": round(t + dur, 3), "bars": s["bars"]})
        note = f" - {s['note']}" if s.get("note") else ""
        lines.append(f"[{s['tag']}{note}]")
        t += dur
    return "\n\n".join(lines), round(t, 3), marks


def main() -> None:
    score_path, out_dir = sys.argv[1], sys.argv[2]
    score = json.load(open(score_path))
    os.makedirs(out_dir, exist_ok=True)
    lyrics, duration, marks = plan(score)
    meta = {"bpm": score.get("bpm", 122), "key": score.get("key", "A minor"), "duration_s": duration, "sections": marks, "caption": score["caption"]}
    json.dump(meta, open(os.path.join(out_dir, "score.meta.json"), "w"), indent=2)
    print(f"plan: {duration:.2f} s, {len(marks)} sections -> {out_dir}/score.meta.json")
    if os.environ.get("ACE_DRY_RUN"):
        print(lyrics)
        return

    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ROOT, config_path=score.get("model", "acestep-v15-turbo"), device="auto")
    if not ok:
        sys.exit(f"DiT init failed: {msg}")
    llm = LLMHandler()
    msg, ok = llm.initialize(checkpoint_dir=os.path.join(ROOT, "checkpoints"), lm_model_path=score.get("lm", "acestep-5Hz-lm-0.6B"), backend=score.get("backend", "mlx"), device="auto")
    if not ok:
        print(f"warning: LM init failed ({msg}); generating without thinking", file=sys.stderr)

    params = GenerationParams(
        caption=score["caption"],
        lyrics=lyrics,
        instrumental=True,
        bpm=int(score.get("bpm", 122)),
        keyscale=score.get("key", "A minor"),
        timesignature=str(score.get("timesignature", "4")),
        duration=duration,
        inference_steps=int(score.get("steps", 8)),
        shift=float(score.get("shift", 3.0)),
        thinking=bool(ok) and score.get("thinking", True),
    )
    takes = int(score.get("takes", 2))
    seed = int(score.get("seed", 122))
    config = GenerationConfig(batch_size=takes, audio_format="wav", use_random_seed=False, seeds=[seed + i for i in range(takes)])
    result = generate_music(dit, llm, params, config, save_dir=out_dir)
    if not result.success:
        sys.exit(f"generation failed: {result.error}")
    for i, a in enumerate(result.audios):
        dst = os.path.join(out_dir, f"take-{i + 1}.wav")
        if a["path"] != dst:
            os.replace(a["path"], dst)
        print(f"take {i + 1}: {dst} (seed {a['params'].get('seed')}, key {a.get('key')})")


if __name__ == "__main__":
    main()
