# Generation recipes

What worked for launch films in 2026-09. Costs are approximate and dated; check current pricing before you spend (`higgsfield generate cost <model> ...`, `docs/costs.md`). For exact commands and model ids, install Higgsfield's own skills: `npx skills add higgsfield-ai/skills`.

## Accounts

- **Your own Higgsfield account.** The `higgsfield` CLI (log in with `higgsfield auth login`) runs image, video and the audio models (Seed Audio, Sonilo music, `text2speech_v2`, Mirelo). The platform API (`https://platform.higgsfield.ai`, the `higgsfield-client` Python package, an API key) runs image and video jobs from scripts; in 2026-09 it had no audio models. The CLI and the API can bill separate balances.
- **Keys stay out of the repo.** Keep an API key in an environment variable or a secret manager and inject it at run time. Never write it into a script, a log or a commit.
- **Fallbacks.** fal or OpenRouter for volume video (often cheaper per second), and the free local tools below. Never retry a failed paid job on another account without saying so.

## Cost rule

State the credit cost of every video job and wait for a yes. Images and single audio clips can run without asking. Draft cheap, render the approved direction once at full resolution.

| Job (2026-09) | Approximate cost |
|---|---|
| Seedance 2.5 video | about 3, 7 and 12 credits a second at 480p, 720p and 1080p |
| GPT Image 2.5 image | about 0.25 credits |
| Nano Banana Pro image, 2K or 4K | about 2 or 4 credits |
| Soul 2 image | about 0.12 credits |
| Seed Audio clip (a sound, a narrator line) | quoted 0.4, charged about 1.7 to 2.1 credits |
| `text2speech_v2` line | about 0.3 credits |
| Sonilo music, 30 s take | about 1.9 credits |

A disciplined 15 s generated hook fits in about 300 credits. Marketing Studio presets cap at 720p: use them as mood drafts, never masters.

## Recipes

| Need | Recipe | Notes |
|---|---|---|
| Photoreal keyframes | Soul 2 with a shared look prefix in every prompt; fictional people, no text or brands unless stated. | Generate 3 or 4 candidates, pick 1. |
| Clean plates and graphic stills | GPT Image 2.5 (16:9, 2K). Ask for text-free images; set every word in HyperFrames. | Generated letters get swapped. |
| Edits that keep a character or room | Qwen Image edit from 1 or 2 anchor frames. | It sometimes answers "temporarily unavailable"; retry. |
| Video, several shots in 1 look | Seedance 2.5 `reference-to-video`: up to 5 keyframes as `image_urls`, a prompt with a global style block and 1 timed line per shot, integer duration, `generate_audio` off unless needed. | 1 generation is about 1 scene of up to 15 s. |
| A character speaking on camera | The same job with the line in the prompt and `generate_audio` on; lip sync comes with it. | Check the words with whisper. |
| The narrator, same voice every time | Seed Audio on the CLI with a fixed prompt, the narrator's earlier lines as audio references and a fixed speech rate. If that is unavailable: Seedance 2.5 with the narrator's own lines as `audio_urls`, any still as the image, the line as off-screen voice-over; keep only the sound (5 s at 480p is about 15 credits). | Same prompt, same references, every line. |
| Casting a voice | `skills/launch-voice/scripts/hf_voice.py cast` speaks 1 line with every preset voice (`text2speech_v2`). | About 0.3 credits a voice. |
| Music | Sonilo via `skills/launch-score/scripts/hf_score.py`, fitted to the act map. | |
| Sound effects kit | `skills/launch-sound/scripts/hf_kit.py` from `skills/launch-sound/references/kits.example.json`. | 6 hits per job, sliced into one-shots. |

Prompting that holds up:

- Write the visible, not the mood: 1 camera move with a start and an end, 1 action, 1 named light source, what drifts and how fast, then short exclusions ("no people, no text, no cuts").
- Seedance 2.5 order: GLOBAL STYLE, SCENE, CHARACTERS, LOCATION, FIRST FRAME, numbered shots ending in "Hard cut", OPTICS/CAMERA, LIGHTING, AUDIO. Put "Total: 10s / 4 shots / 16:9" on top.
- Hand the model keyframes, or first and last frames at the same aspect ratio. A storyboard grid is only a loose guide. Pass your brand frame as the last frame when a shot must land on it.
- Block a hard camera move with a grey-box Blender playblast passed as a video reference.
- Change 1 variable per test. 4 failed takes out of 4 means rewrite the prompt; 1 failure is a re-roll.

## Free fallbacks

| Need | Free route |
|---|---|
| Voice | macOS `say` or `espeak-ng` scratch takes (`skills/launch-voice/scripts/scratch_voice.py`); Chatterbox local clone from your narrator (`clone_local.py`). Label every review "scratch voice". |
| Music | The scratch bed (`skills/launch-score/scripts/scratch_bed.py`) to cut against; ACE-Step 1.5 locally for a real take (`ace_score.py`). |
| Sound effects | The synthesised palette in `skills/launch-sound/scripts/sfx_forge.py`, key-locked and seeded. |
| Hook picture | A type-only hook on a brand ground, or your own footage. |
| 3D | Blender (`skills/launch-world/scripts/blender_glass_object.py`). |

## Picking a take

- **Words:** whisper must read the line exactly (use the small or larger model for product names).
- **Same voice:** median pitch and timbre inside the range of the narrator's other lines; a take that sounds like another person is out even when clear.
- **Pace:** trim silence, speed up at most 1.1x (`atempo`), match loudness to a neighbouring line, then align with `skills/launch-voice/scripts/force_align.py`.
- **Faces:** check for likeness to anyone famous; regenerate rather than "fix".
- **Small AI tells** (misspelled props, odd signs, extra fingers): list them with the re-roll cost, never leave them silently.
- **Provenance:** save each prompt, model, seed and job id beside the file it made.
