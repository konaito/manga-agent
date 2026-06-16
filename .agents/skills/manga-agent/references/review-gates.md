# Review Gates

Use this reference when reviewing manga ideas, scripts, names, or storyboards before image generation.

## Required Reading

- `agents/manga_editor_agent.md` for the editor behavior and output shape.
- `docs/knowledge/INDEX.md` first, then only the relevant linked craft docs.
- `templates/script_review_checklist.md` for `script.md`.
- `templates/name_review_checklist.md` for `name_v2.md`.
- `templates/series_review_checklist.md` for whole-series review.

## Gate Order

Do not skip gates:

```text
source material -> adaptation design -> script.md -> script_review.md -> name_v2.md -> name_review.md -> storyboard.json -> lint/review/gen/qa
```

Only move forward when the review verdict is `ship`.

## Script Review

Review `production/spec/script.md` before any name/storyboard work. Write `production/spec/script_review.md`.

Check:

- Important decisions are dialogue exchanges, not one-line explanations.
- Each key line has a visible reaction beat from the other character.
- Internal state is translated into gaze, hands, distance, posture, silence, or props.
- Non-dialogue lines are classified as `caption`, `monologue`, `sfx`, or UI text.
- The page intent and page-ending hook are clear enough to hand to name work.

Use verdicts:

- `ship`: proceed to name.
- `revise`: revise script and review again.
- `blocked`: return to story bible or adaptation design.

## Name Review

Review `production/spec/name_v2.md` before `storyboard.json`. Write `production/spec/name_review.md`.

Check:

- Required script lines are not dropped.
- The name does not add explanation dialogue that the script avoided.
- Each page has a hook and manageable text load.
- Question -> answer beats are not split into two side-by-side panels in the same row.
- Caption/monologue/sfx containers are decided before generation.
- Motifs and props are traceable across pages.

Use verdicts:

- `ship`: proceed to storyboard.
- `revise`: revise name and review again.
- `blocked`: return to script.

## Human-Facing Review Shape

Lead with the highest-impact issues, not a long summary.

For each issue, include:

- Problem.
- Reader impact.
- Concrete fix at page, panel, or dialogue level.

End with 3-7 next actions. Do not say only "make it more interesting" or "strengthen the character"; describe the manga-visible change.
