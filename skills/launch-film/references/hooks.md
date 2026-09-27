# Hooks

A hook is the story before the cut to your brand. It lives in `film/hooks/<name>/` and is described by `hook.json`. Nothing in the body changes for it.

## hook.json

```json
{
  "duration": 5.0,
  "video": "hooks/demo/hook.mp4",
  "ground": "dark",
  "push": true,
  "voice": {"file": "hooks/demo/voice.wav", "at": 0.15, "text": "You built the product. Now launch it."},
  "text": [{"words": [["You", 0.3], ["built", 0.5], ["the", 0.7], ["*product.", 0.85]], "out": 2.2, "y": 470, "size": 110}],
  "sfx": [{"t": 0.0, "sound": "air", "gain_db": -18}]
}
```

| Key | What |
|---|---|
| `duration` | Seconds until the cut. The music's drop and the spoken brand name land there. |
| `video` | The hook's picture, 1920x1080, exactly `duration` long, path from `film/`. `null` makes a type-only hook. |
| `ground` | For a type-only hook: `dark`, `accent` or `light` from the brand. |
| `push` | `true` pushes in and blurs the last 0.16 s into the cut. |
| `voice` | `{file, at, text}`: the hook's narrator line, or `null`. |
| `text` | Optional lines written word by word over the picture: `[{"words": [[word, seconds], ...], "out": s, "y": px, "size": px}]`, `*` marks key words. Set in the brand's display font with the highlight. |
| `sfx` | Sound cues in hook time (the `sfx_forge.py` cue format), including a music bed for long hooks. A `file` cue is relative to the hook's folder. |
| `from` | Optional: seconds into `video` where the hook starts. |

Then from `film/`: `./render.sh <name>`.

## Rules that hold for every hook

- **Music.** The track is placed so its drop lands on the cut. A hook up to about 4 s starts inside the track's intro. A longer hook must bring a bed (the track's own intro bars looped on its grid, or a matching take), or it plays in silence.
- **The drop.** Land the last word or the last picture change on the cut; a push, a power-off or a flash into the brand ground carries it.
- **The narrator.** A hook may have its own voice (a character, a vintage record), but a narrator line in a hook should be the body's narrator, so the film has 1 voice.
- **Legal.** Generated or owned footage. Fictional people and places, no famous faces or lookalikes, no real film or actor, no third-party brands. Keep the prompts beside the footage as provenance (`docs/rights.md`).
- **Length.** 4 to 10 s works best. Long story hooks (16 to 18 s) need a strong voice to carry them.

## Hook styles that worked

| Style | Idea | How |
|---|---|---|
| Type only | 2 lines of the problem in the owner's words, then the cut. | `"video": null`, a dark or accent ground, `text` lines timed to the voice. Free, and a good first hook. |
| Screen in a room | Moments playing on an old TV or a laptop in a calm set. | Generate the set with a flat chroma-green screen, key it and map the footage onto it with a homography; a slow push and a power-off into the cut. |
| Era footage | "Remember when everything felt possible?" on 90s camcorder or 16mm. | Keyframes of fictional people in the era's look (Soul 2), then 1 multi-shot video job per line so the shots share a look; date stamps and a tape or film grade. |
| The old way | A sales floor, a paper office, a manual process in its era, then the modern line. | 2 anchor frames (the room, the character), every other keyframe an edit of them, then animate; a lip-synced line when a character speaks. |
| Stylised character | A solo founder launches to silence, refreshes a flat chart. | A 3D animated character (photoreal people looked fake), the screens projected onto the laptop in the body's grammar. |
| The switch | "Being a founder is hard. Your launch doesn't have to be." | Era or everyday footage cut faster toward the drop, the body's switch pays it off. |

## Ways to make a hook's picture

- **Generated live action:** keyframes first (Soul 2 or GPT Image 2.5), then 1 multi-shot Seedance 2.5 job per line so the shots share a look. Cut inside the generated shots.
- **A set with a screen:** generate the set with a flat chroma-green screen, key it and map the footage on with a homography.
- **Consistency across shots:** 1 or 2 anchor frames, every other keyframe an edit of them (Qwen Image edit), then animate.
- **Stylised character:** when photoreal people look fake, redraw the layouts in a 3D animated style and animate those.
- **UI in the hook:** in the body's grammar (hero words, close range, glass), never flat grey mock-ups; project it onto a screen in the scene when the story is in a room.
- **Type only:** fine and free. Story hooks usually need a narrator to land; drawn stand-ins for footage do not.

Show 3 to 5 keyframes before any video job. Costs and recipes: `generation.md`.
