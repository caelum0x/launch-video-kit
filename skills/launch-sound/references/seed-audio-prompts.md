# Seed Audio prompts (Higgsfield `seed_audio`)

Tested 2026-09 at `--sample_rate 48000 --format wav`. The real charge per clip was about 1.7 to 2.1 credits although `generate cost` quoted 0.4. Check current pricing.

| Texture | Result | Prompt |
|---|---|---|
| Laptop typing, hero moment | Good. 6 s, clear dry keystrokes, a firm Enter at the end, about -27 LUFS | "Close-miked typing on a quiet premium low-profile laptop keyboard: a short burst of confident fast typing, about fifteen soft keystrokes and one spacebar, ending with a single firm Enter key press. Dry studio recording, no room echo, no voices, no music." |
| Outdoor morning bed | Weak. 17.8 s, about -59 LUFS, mostly low rumble, birds barely present | "Calm morning ambience deep inside a misty pine forest. Soft steady wind moving through tall pine needles, two or three distant songbirds far away, faint dripping water, very still and spacious. No voices, no music, no traffic, no insects buzzing close to the microphone. 20 seconds, even level, seamless." |

What the results suggest:

- Name concrete, close sources ("close-miked", "dry studio recording", counts of events). Seed Audio renders them well.
- "Very still", "distant" and "far away" push the level toward silence. For a bed, ask for "clearly audible", name the distance as "mid-distance", and normalise afterwards anyway.
- Always measure a texture (`ffmpeg -af ebur128`) and look at its spectrum before placing it; the forge places files at their normalised peak, so a near-silent file turns into amplified noise.
- A bed inside the music (pads, room tone) often does the job. Try that before generating one.
- For kits of separate hits, ask for a count of hits with "every hit followed by one full second of silence", so onset slicing can cut them apart (`kits.example.json`).
