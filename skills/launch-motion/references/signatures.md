# Signature moves

Each move is derived from a HyperFrames motion rule (named at the end of each move) and written brand-neutral: the colours come from `brand/brand.json`, the material from your world (`launch-world`). Numbers are starting points inside each rule's documented range. Pick 2 or 3 per film.

## 1. Logo build (sting and lockup, replaces the stock logo-outro)

The logo comes into being in a way that fits its shape.

- A core element (a dot, a letter, the icon) scales from 0 with a baked spring (damping 1.0, response 0.35, about 0.5 s).
- An outline draws in (stroke-dashoffset, 0.7 s, `power2.out`, starts +0.15 s), or the icon's parts land one by one on a rising pitch.
- Each secondary part lands the moment the drawing front reaches it: scale 0 to 1 over 0.35 s `power3.out`. Causality: a drawn line lands on something.
- Optional settle: a small rotation or shift over 1.2 s `power2.inOut`, then dead still for at least 1 s.
- The wordmark rises per word, blur to sharp; no bounce, no glow, no URL pill, no white flash.
- Or: an object in the film becomes the logo (a switch closes into it, blocks collapse into it). That is stronger than any build.
- Sound: `logo_sting`, with the score dropped out or faded.
- Rules: `svg-path-draw`, the `logo-assemble-lockup` blueprint.

## 2. World pass (the primary transition)

Your brand's material crosses the seam: haze, paper, light, glass, grain. The default is a soft haze in the `ground` and `accent` colours.

- A layer larger than the frame (2400 px or more) drifts laterally across the seam while the outgoing scene blurs to 20 to 30 px and the incoming resolves from it.
- 0.8 to 1.2 s total; hold at peak 0.3 to 0.5 s; the incoming resolves over 0.6 s `power1.out`.
- With plates: a plate that goes from the brand ground to the world is itself the pass.
- Sound: `air` at about -12 dB, never a whoosh.
- Rules: blur-crossfade (calm register), light-leak sizing.

## 3. Branch and pulse (connectors and flows)

- Every connector is a smooth cubic bezier drawn with stroke-dashoffset; multi-segment paths start each segment at 70 to 80 % of the previous one's duration; `power2.out`; never bounce.
- An `accent` dot travels the path at constant speed (`ease: "none"`), and the node it reaches wakes in that frame: ink from 18 % to 100 %, scale 0.98 to 1 on `settle`.
- Use for workflow edges, sequence steps, request to task to result chains.
- Sound: `grow` for the draw, `arrive` or `lock` when the node wakes.
- Rules: `svg-path-draw`, `tracing-beam`, `offset-path-traveler`.

## 4. Waterfall fill (tables, lists and enrichment)

- Rows and cells arrive by the waterfall law: binary opacity, `power4.out`, each starts within 1 to 2 frames of the previous settling, gaps shrink across the cascade.
- A miss drops a short 12 to 20 px step (0.13 to 0.16 s, `power4.out`) to the next source until a value lands; the landed value is the 1 accent element.
- Skeleton cells sit at 18 % ink and ink to full as they resolve.
- Sound: `wood_knock` per landed value, alternating pan; `lock` on the last.
- Rules: `waterfall-entry`, `grid-card-assemble` (tabular), `state-chip-rail`, `control-target-sync`.

## 5. Identity morph (1 object through the funnel)

- A card holds 0.6 to 1.5 s, then morphs into the next state (a request into a task, a task into a shipped result, a comment into a message into a meeting): uniform scale plus `borderRadius / END_SCALE`, 0.6 to 1.2 s `power2.inOut`, never back.
- Old content fades over the first 30 to 50 % of the morph, new content over the last 30 to 50 %.
- The funnel reads as 1 continuous identity, not 3 screens.
- Sound: `arrive` at the start, `lock` when the result lands.
- Rules: `card-morph-anchor`, rectangle morph mechanics.

## 6. Macro pull-back (the 1 big reveal)

- Open on a macro (a single cell, a character, a texture of your world) with live micro-motion; 1 `expo.out` pull-back over about 4 s until the macro registers as part of the product inside a window; lock the frame; the product keeps working.
- Build at 1x and open scaled in (4 to 12x); never scale the world down to a speck.
- No zoom-in anywhere in the same shot.
- Sound: `sub_drop` under the pull, `arrive` on the lock.
- Rules: `zoom-out-workspace-reveal`, `viewport-change`, `depth-of-field-blur`.

## 7. Rise (accent transition)

- A vertical push upward only, 0.5 s `power3.inOut`.
- Use for topic changes inside the product sequence.

## Pacing reminders

- The hero is visible by 0.5 s; payoffs hold at least 1 s; the logo lockup gets 20 to 30 % of a short film's runtime.
- Group staggers stay within 0.5 s total (`min(0.06, 0.5 / N)`).
- Beats every 1.2 to 1.8 s in kinetic sections.
