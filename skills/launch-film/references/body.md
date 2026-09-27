# The body

The body is everything after the cut. It is the same in every film; only its start time moves with the hook's length (`D`, the hook's `duration`). It lives in `film/film.json` and is drawn by `film/templates/body.html`.

## How it is built

| Part | File (in `film/`) | Notes |
|---|---|---|
| Script and beats | `film.json` | The voice lines by id, the music, the sound, and the beats in order. |
| Composition | `templates/body.html` | 1 HyperFrames composition. CSS holds every initial state; 1 GSAP `onUpdate` driver draws each beat as a pure function of time. |
| Timings | `build.py <hook>` | Reads `hooks/<hook>/hook.json`, `film.json`, `vo/body/lines.json` and `brand.json`; places the lines, resolves every word key to a film time, writes `compositions/film-<hook>.html`, `index-<hook>.html` and `timing-<hook>.json`. Copies the brand assets into `assets/brand/`. |
| Voice | `vo/body/line-<id>.wav`, `vo/body/lines.json` | 1 take per line plus its aligned words (`launch-voice`). |
| Sound | `audio.py <hook>` | Places the music so its drop lands on the cut, stitches the voice, writes the SFX cue sheet from the timings, mixes and muxes. |
| Everything at once | `render.sh [hooks]` | Build, render and mix per hook. |

## film.json

```json
{
  "brand": "../brand",
  "voice_dir": "vo/body",
  "gap": 0.3,
  "lines": {"02": "Acme is your feedback inbox.", "03": "Every request lands in one place, tagged for you."},
  "music": {"file": "score/bed.wav", "bpm": 120, "drop": 4.0, "gain_db": -3},
  "sound": {"kit": null, "key": "A"},
  "beats": [
    {"type": "name", "line": "02", "tagline": "is your *feedback *inbox."},
    {"type": "hero", "line": "03", "ground": "dark", "text": "Every *request.", "exit": "dive", "until": "request+0.4"},
    {"type": "product", "line": "03", "src": "assets/screens/inbox.png", "focus": [0.52, 0.18, 0.42, 0.36], "push_at": "tagged",
     "cursor": {"at": "tagged", "x": 0.71, "y": 0.29}, "chip": {"text": "Tagged", "at": "tagged"}},
    {"type": "blocks", "line": "06", "items": ["Inbox", "Tags", "Roadmap"], "merge_at": "one", "label": "One *place."},
    {"type": "switch", "line": "07", "text": "Feedback, on *autopilot.", "flip_at": "autopilot"},
    {"type": "end", "hold": 3.5}
  ]
}
```

- `lines`: the narrator's script, 1 line per beat or pair of beats, 6 to 20 words each. The ids are stable names; the take files use them.
- `gap`: seconds of breath between lines (0.25 to 0.5 reads natural).
- `music.drop`: seconds into the music file where the drop (the first clean kick after the intro) sits. It lands on the cut.
- `lockup` (optional): `mark+name` (the icon mark beside the name in the display font, the default when `brand.json` has a `logo.mark`), `logo` (the full logo file alone, the default otherwise) or `name` (type only).
- `sound.kit`: a folder made by `hf_kit.py` to voice the events with generated hits, or `null` for the synthesised palette. `key` is the score's key, so tonal sounds agree with it.

## Beat types

Every beat but `end` names the voice `line` it plays under. Consecutive beats may share a line: the earlier one ends at its `until` (`"word"`, `"word+0.4"` or `"word-0.1"`), the next starts there. Word keys match the line's aligned words by prefix, lowercase, punctuation stripped, in speaking order. `*` marks a key word.

| Type | Picture | Fields |
|---|---|---|
| `name` | On the cut the logo and name punch in from 4x; the tagline writes in word by word under it, key words taking the highlight. | `line`, `tagline` |
| `hero` | Full-frame hero words on a ground, each word snapping in on its spoken word (the first from 2.4x with a blur, the rest from 1.3x). | `line`, `text`, `ground` (`dark`, `accent`, `light`, or `clear`: no card, the words ride at the top of the frame over whatever beat is playing and take no slot of their own), `exit` (`dive`, `collapse`, `cut`), `until`, `size` (px, optional) |
| `product` | Your product (png, jpg, mp4 or webm under `film/assets/`) in a window on the ground. The camera starts on the whole window and pushes into `focus` at `push_at`. Optional cursor click and a chip that pops on its word. | `line`, `src`, `focus` ([x, y, w, h] as fractions of the source), `push_at`, `cursor` (`at`, `x`, `y` as fractions), `chip` (`text`, `at`, optional `x`, `y`), `width` (share of the frame, default 0.8), `max_zoom` (default 3), `from` (seconds into a video source) |
| `blocks` | 2 to 5 feature blocks, each landing on the spoken word that matches its label, then closing into 1 bar at `merge_at`, with `label` written in. | `line`, `items` (labels, or `{"label", "icon"}` with an svg or png under `film/`), `merge_at`, `label` |
| `switch` | A card with the text and an on and off switch that flips on `flip_at`; the track fills with the accent and the key words take the highlight. | `line`, `text`, `flip_at` |
| `end` | The logo lockup (logo, name, tagline, domain) on the ground, then a quiet hold. | `hold` (seconds, default 3.5), `plate` (an optional still behind the lockup), `tagline`, `url` (override the brand's) |

A typical 45 s body: `name`, 3 or 4 pairs of `hero` plus `product`, `blocks`, `switch`, `end`. Keep 1 idea per beat.

## Timing

- The hook runs from 0 to `D`. The name line starts about 0.02 s before `D`, so the brand name is spoken on the cut.
- Each later line starts after the previous one ends plus `gap` plus its beat's `pad` (defaults: `name` 0.15, `product` 0.35, `blocks` 0.7, `switch` 0.45 s). Give a beat more room with `"pad": 1.0`.
- `build.py` warns when a beat is shorter than 0.35 s.
- No `vo/body/lines.json` yet: `build.py` estimates the timing from the text at 2.6 words a second and renders a silent animatic, enough to judge the story.
- Every picture cue is a word time from the aligned voice. Nothing is timed by hand, so a new take or a new voice re-times the film on the next build.
- The end starts after the last line plus about 0.3 s and holds `hold` seconds. The music fades over the last 2 s.

## Commands

From `film/`, with the repo's Python venv active (`source ../.venv/bin/activate`):

```bash
python3 build.py <hook>
npx -y hyperframes@0.8.77 render -c index-<hook>.html --quality looks --output renders/<hook>-picture.mp4
python3 audio.py <hook>
./render.sh [hooks...]          # the 3 steps above for each hook, or for every hook in hooks/
```

## Changing a beat

- **A word, a line:** change the line in `film.json`, record it in the narrator's voice (`launch-voice`), re-run the voice prep so its words are re-aligned, rebuild. The cues move with the words.
- **A hero card:** its `text`, `ground`, `exit` and `until` in `film.json`.
- **A camera move:** the product beat's `focus`, `push_at` and `cursor`. For a longer move, record a screen capture and pass the video as `src`.
- **A new kind of moment:** add a function to `templates/body.html` driven by timing keys you add in `build.py`, plus its sound cues in `audio.py`. Keep it a pure function of `t`.
- **Then:** snapshot the changed seconds, look, and run `render.sh`.

## HyperFrames gotchas

See `hyperframes-notes.md`. The ones that bite this template most: initial states live in CSS (never `tl.set` at 0), 1 `onUpdate` driver, text written as markup (script-created text falls back to a serif), and glass needs something behind it inside the same stacking root.
