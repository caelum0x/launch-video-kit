# Brand core for launch films

How `brand/brand.json` maps onto the film. The template reads these values at build time; this page says what each role is for and what to do when the brand is thin. When this page and `brand.json` disagree on a value, `brand.json` wins.

## Colour roles

| Role (`colors.*`) | Use in the film |
|---|---|
| `ground` | The ground of every statement scene: the name beat, light hero cards, product windows, the end lockup. |
| `surface` | Cards on the ground: feature blocks, the switch card, chips, product window frames. |
| `ink` | Headlines, key words on light grounds, a single-colour logo. |
| `ink_secondary` | Supporting words, the tagline, the non-key words of a line. |
| `accent` | Accent hero grounds and the 1 element per shot that matters (the done state, the switch when on, a travelling signal). |
| `accent_ink` | Type on accent grounds. |
| `dark` | Dark hero cards and dark scenes. |
| `dark_ink` | Type on dark grounds. |
| `highlight` | The soft marker that sweeps in behind 1 or 2 key words on light grounds. |
| `success`, `danger` | Ticks and confirmations; a single failure word. Nothing else. |

Rules that hold for any brand:

- The ground can carry a soft bloom (large, slow, blurred blobs of `accent` at low alpha) and a fine grain, so it reads warm and alive, not flat. Keep it subtle enough that type stays crisp.
- Strong accent colour belongs to grounds and single elements. Long runs of accent-coloured type read loud and cheap.
- Dark grounds are tinted toward the brand (a very dark `accent` or the site's own dark), with a soft glow, never pure black plates with crushed blacks.
- 1 accent element per shot. If everything is accent, nothing is.

## When the brand is thin

The extractor fills every role; check `preview.png` and fix what reads wrong. Defaults that work:

- No dark colour on the site: `dark` = `accent` darkened to about 10 to 14 % lightness, `dark_ink` = `ground`.
- No highlight: `highlight` = `accent` at 20 % alpha.
- A dark-mode site (`"mode": "dark"`): swap the roles. `ground` is the site's dark background, `ink` its light text, light hero cards become `surface` cards. Test the lockup on both.
- A grey or black-and-white brand: pick the 1 colour the site uses for its primary button or links as `accent`; if there is none, the film can be monochrome with motion carrying the energy.

## Type

- Hero type is `fonts.display` at its weight (500 to 700), tracking about -0.04 to -0.055em, line height about 1.04.
- Hero words: 1 to 4 words, centred, huge (about 110 to 150 px at 1080p), `ink` on light and `dark_ink` on dark.
- Key words (`*` in `film.json`): the `highlight` marker on light grounds; an accent-to-light gradient or plain `accent` on dark grounds; `danger` only for a failure word.
- `fonts.mono` only where it is real: terminals, emails, URLs, code. Never as decoration.
- A serif only when the brand uses one. Never mix in a display font the site does not use.
- Check the font licence covers video (`docs/rights.md`). If the site's font cannot be used, pick the closest open font and write it into `brand.json`.

## Logo and lockup

- `logo.file` as it appears on the site. `logo.on_dark` on dark grounds; if there is none, the build inverts a single-colour logo, and a multi-colour logo sits on a `surface` chip.
- `logo.mark` (the icon alone) for small spots: an avatar, a chip, the sonic logo moment.
- The lockup: logo, name, `tagline` under it in `ink_secondary`, the domain in small mono under that. It holds quiet for about 4 s at the end.

## Materials

- **Glass** for floating surfaces: white gradients from 26 % to 8 %, `backdrop-filter: blur(24px) saturate(1.35)`, a 1 px white edge at about 38 %, an inset top highlight. It needs something moving behind it (a bloom, a plate, drifting light), or the blur has nothing to show. Never strong white cards on flat grey.
- **Your product UI** is shown as it ships: real screenshots or screen recordings. Never restyle it; animate on top of it (camera, cursor, zooms, chips).
- **Characters** (optional): a density ramp ` .,:;-=+*#%@` in the mono font that builds or dissolves a shape, then resolves into the crisp object with a wipe. Good for a transition that means "being built". Textures only where they carry meaning; random texture reads as filler.

## Motion

- Hero cards cut in hard on the word: the first word snaps from 2.4x with a blur, the rest step in from 1.3x. They leave by a dive through the words into the next beat, a collapse into the product window, or a hard cut.
- Grounds change on hard cuts, on the beat.
- One object becomes the next: a card becomes a window, blocks become a bar, a switch becomes the logo.
- The product at close range: push into the part the voice names. The whole app window at tiny size is out.
- Eases: out-cubic and out-quartic for arrivals, in-out cubic for morphs. No bounce, no elastic.
- Fast, but every beat readable: a hero word holds at least about 0.6 s; the end holds quiet for about 4 s.

## Sound

- Music: 1 track at a steady tempo with a clean kick on the drop, placed so the drop lands on the cut; looped on its bar grid until the logo forms, faded over the last 2 s.
- Effects: 1 palette (the synthesised forge or your generated kit), 1 sound per meaningful event, varied so repeats never sound cloned. No whooshes as decoration, no swells or risers.
- Narrator: 1 voice, brisk and clear, not performed (2.2 to 2.7 words a second).
- Mix: voice on top with the music ducked about 9 dB under it, -14 LUFS integrated, -1 dBTP ceiling, the logo in near silence.
