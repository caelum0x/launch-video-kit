# Rights

Plain guidance for making launch films you can publish. It is not legal advice. When a film carries real legal risk (a famous likeness, a real film, a claim a competitor could challenge), ask a lawyer in the countries where it will run.

## People

- Use generated, fictional people, or real people who have agreed in writing (you, your team, customers with a signed release).
- Never use famous people, or generated people who look like them, to advertise a product. It reads as an endorsement, and publicity and likeness rights protect it in many places.
- Check every generated face for a likeness to anyone famous. Regenerate rather than "fix".
- Only clone a voice you own or have written permission to use.
- The scratch voice is for timing only. System voices (macOS `say`) are licensed for personal, non-commercial use, so never publish a film with a scratch take in it; record or generate the real narrator first.

## Footage, films and music

- The era and genre of a famous film are free to use; the film itself, its scenes, its characters and its actors are not.
- Archival footage is rarely public domain just because it is old. Check each reel's licence before a public release.
- Use music you generated on a plan that grants commercial use, a track you licensed for this use, or music you made. A reference film's soundtrack is never yours to use.
- Reference films are for study. Keep their downloads out of your repository.

## Logos, brands and product UI

- Show third-party logos only to name a platform your product works with, as they appear in your own product. Never imply a partnership or endorsement you do not have.
- Your own product UI is yours to show. Blur or replace any customer data that appears in it, unless the customer has cleared it for public use.
- Brand extraction (`tools/brand-from-url.mjs`) is meant for your own website. Do not use another company's brand, logo or fonts in your film.

## Fonts

- A web font licence does not always cover video. Check the licence of every font you render, especially commercial ones. Open fonts (the SIL Open Font License) are fine for video.
- If your site's font is not licensed for video, pick the closest open font and write it into `brand/brand.json`.

## Claims

- Every number and claim in the film must be true and provable today. Keep the source of each number beside the script.
- Generated images of results (dashboards, charts, messages) must not suggest results you do not have. Label sample data as sample in any review copy.

## Provenance

- Keep every prompt, model, seed and job id beside the file it produced. It shows how each shot was made if anyone asks.
- Check the generator's terms for commercial use on your plan before you publish.
