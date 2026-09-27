# Costs

A full launch film can cost nothing, or a few dollars of generation, or more when you generate footage. You choose per step. Prices below are approximate, dated 2026-09, and change often: check current pricing before you spend (`higgsfield generate cost <model> ...`, `higgsfield account status`).

## Free

| Step | Free route |
|---|---|
| Brand kit from your website | `tools/brand-from-url.mjs` (runs locally) |
| Picture | HyperFrames render on your machine; type-only hooks; your own screenshots and screen recordings |
| Voice | Scratch takes with macOS `say` or `espeak-ng`; Chatterbox local clone |
| Music | The scratch bed on the grid; ACE-Step 1.5 locally |
| Sound effects | The synthesised `sfx_forge.py` palette |
| Mix, master, review | `mixdown.py`, `review.py` |
| 3D | Blender |

## Paid (your own Higgsfield account, 2026-09)

| Job | Approximate credits |
|---|---|
| Cast a narrator across about 110 preset voices (`hf_voice.py cast`) | about 34 |
| 1 voice-over line (`text2speech_v2`) | about 0.3 |
| 1 Seed Audio clip (a narrator line, a texture) | about 1.7 to 2.1 (quoted 0.4) |
| A generated sound kit, 10 materials | about 20 |
| 1 Sonilo music take, 30 s | about 1.9 |
| 1 image (GPT Image 2.5, Soul 2) | about 0.1 to 0.25 |
| 1 image (Nano Banana Pro, 2K or 4K) | about 2 or 4 |
| Seedance 2.5 video, per second at 480p, 720p, 1080p | about 3, 7, 12 |
| A generated 10 s hook at 1080p, drafted at 480p first | about 150 to 300 |

At a Plus plan in 2026-09, 1 credit was about $0.05. Credits on subscription plans can expire each billing cycle, and agent (CLI or API) jobs bill at standard rates.

A typical first film with a real narrator, a real music take and a generated sound kit, over a type-only hook, costs about 30 to 60 credits. A generated live-action hook adds about 150 to 300.

## The cost rule

- State the cost of every paid video job before running it and wait for a yes. Images and single audio clips can run without asking; a batch over about 20 credits waits for a yes.
- Draft cheap (480p, 5 s, 1 take), render the approved direction once at full resolution.
- Log what each job actually charged (`higgsfield account transactions`): quotes and charges can differ.
- Never retry a failed paid job on another account or provider without saying so.
