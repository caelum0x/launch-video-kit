# HyperFrames notes

The HyperFrames contract the `film/` template relies on, written for HyperFrames 0.8.77 (Apache-2.0, by HeyGen). For the full docs, install the official skills: `npx skills add heygen-com/hyperframes` (entry skill `hyperframes`, the composition contract in `hyperframes-core`, motion in `hyperframes-animation`, the CLI in `hyperframes-cli`).

## What a composition is

- An HTML file whose DOM declares timing with `data-*` attributes and whose animation is seekable. The renderer seeks every frame and screenshots it in headless Chrome, so the page must draw the same pixels for the same time, every time.
- The root element carries `data-composition-id`, `data-width`, `data-height`, `data-start` and `data-duration`. Sub-compositions are loaded with `data-composition-src` and sit in a `<template>` in their own file.
- Media (`<video>`, `<img>`, audio) is placed with `data-start`, `data-duration`, `data-media-start` and `data-track-index`. The framework owns playback; never call `play()` or set `currentTime` yourself.

## Seek-safety (non-negotiable)

- 1 paused GSAP timeline per composition, registered as `window.__timelines["<composition-id>"] = gsap.timeline({ paused: true })`. The id matches the element's `data-composition-id`.
- No `Math.random`, `Date`, timers, `requestAnimationFrame`, CSS transitions, CSS animations or `repeat: -1`. Use a seeded hash for anything that looks random.
- Every tween is a pure function of time. `fromTo` with explicit from-states, and `immediateRender: false` on `fromTo` that start later.
- Canvas, WebGL and Three.js draw from the seek time, with a fixed canvas size and no render loop.

## How this template draws

- **Initial states live in CSS.** Never `tl.set(...)` at time 0: it can vanish in renders. Hidden things start `opacity: 0` or `visibility: hidden` in the stylesheet.
- **1 `onUpdate` driver.** The timeline holds 1 long tween whose `onUpdate` calls `apply(t)`, and `apply(t)` sets every beat's state from `t`. Each beat is a pure function of the film time, so any frame can be rendered alone.
- **Transform-only motion** (`transform`, `opacity`, `filter`, masks). Never animate `font-size`, `letter-spacing`, `width` or layout properties.
- **Text as markup.** Write words into the HTML at build time (`build.py` does this). Text created by script at render time can fall back to a serif before the web font loads.
- **Fonts as local files.** `@font-face` rules point at files in `assets/brand/fonts/`, so renders never depend on the network.

## Glass and blend gotchas

- `backdrop-filter` needs something behind it inside the same stacking root. A `filter` or `opacity < 1` on an ancestor of the glass flattens it to nothing.
- A soft-light bloom needs its own solid background under it, or it greys the frame.
- Motion blur (the `motion-blur` component, `data-hf-motion-blur='{"shutterAngle": 360}'`) only for 1 to 3 slams per film, never on text meant to be read.

## Commands (0.8.77)

```bash
npx -y hyperframes@0.8.77 render -c index-<hook>.html --quality looks --output renders/<hook>-picture.mp4
npx -y hyperframes@0.8.77 snapshot --at 5.2,5.6,9.0 --describe false    # stills of chosen seconds; uses index.html
npx -y hyperframes@0.8.77 lint
npx -y hyperframes@0.8.77 preview                                         # Studio: timeline and keyframe editor
```

- `snapshot` has no `-c` flag and reads `index.html` (the last hook built). Build the hook you want to inspect first.
- `lint` reports "multiple root compositions" because of the per-hook `index-<hook>.html` files. Expected.
- The first render downloads a headless Chrome into the HyperFrames cache. A 45 s film renders in a few minutes on a recent laptop.
- Render the picture silent. Sound is built by `film/audio.py` and muxed onto the render, because the renderer has no master bus.

## Pin the version

The template is tested on 0.8.77. A newer HyperFrames may change flags or behaviour; upgrade on purpose, render 1 hook, compare the contact sheet, then update the version in `film/render.sh` and these notes.
