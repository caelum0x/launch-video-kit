# Working in Launch Video Kit

Read README.md, then `skills/launch-film/SKILL.md`. This repo turns a website into a brand kit and makes product launch films in that brand: a hook (the story before the cut) on a shared body (the name, hero words, the product at close range, the logo).

- The canonical skills are in `skills/`. `.agents/skills` and `.claude/skills` point to that folder. Update `skills/catalog.json` when a skill's name or description changes.
- Start every film from `brand/brand.json`. If it is missing, still the Acme example, or `"reviewed": false`, run the `launch-brand` skill first and show the reader `brand/preview.png`.
- The film's words come from the reader's own website and copy. Keep their lines verbatim, and never invent a number, customer or claim. Unknown facts stay unknown: ask.
- Show frames before building. A contact sheet or snapshots of every new beat come before a full render, and a free render (scratch voice, scratch bed, synthesised sound) comes before any paid generation.
- Paid generation (Higgsfield or any other provider) runs only on the reader's own account, and only after you state the cost of the job and the reader says yes. Never write an API key into the repo.
- Scratch voices are for timing only and are never published (`docs/rights.md`). Generated people are fictional; no famous people, lookalikes, real films or third-party brands.
- Edit `film/film.json`, `film/hooks/*/hook.json` and `film/templates/body.html`; never a generated file in `film/compositions/`. Every beat stays a pure function of time.
- Before committing changes to this template, run `python3 scripts/check-template.py`. Check a changed helper with a real run on the Acme example.
