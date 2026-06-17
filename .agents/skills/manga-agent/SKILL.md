---
name: manga-agent
description: Manga editor and mangagen production workflow support for reviewing manga plans, scripts, names, storyboards, series episodes, X ad carousels, and AI-generated page QA. Use when Codex is asked to critique manga drafts, enforce script/name/storyboard gates, operate tools/mangagen.py, write review.json/page_XX.json/series_review.json, or create/update manga production specs.
---

# Manga Agent

## Overview

Use this skill to act as the manga editor agent and production harness operator for this repository. Keep the cheap checks left: script/name review before storyboard, `lint` and `review` before paid image generation, and agent image QA before `fix`.

## First Steps

1. Locate the repository root and read the nearest `AGENTS.md`.
2. Read `docs/knowledge/INDEX.md` before task work. Follow only the linked documents relevant to the task.
3. Protect unrelated work. Do not edit or delete `output/` artifacts unless the user explicitly asks.
4. Identify the task lane:
   - Manga draft or plan review: use [review-gates.md](references/review-gates.md).
   - `storyboard.json`, image generation, or hosted provider work: use [mangagen-workflows.md](references/mangagen-workflows.md).
   - Generated review or page QA requests: use [agent-qa.md](references/agent-qa.md).

## Core Rules

- Do not collapse the creative gates. Novel/source material -> adaptation design -> `script.md` -> `script_review.md` ship -> `name_v2.md` -> `name_review.md` ship -> `storyboard.json` -> `lint/review/gen/qa`.
- Treat `storyboard.json` as the source for image generation, not as a substitute for manga script or name work.
- Use deterministic checks before paid generation. `lint`, `review`, `qa`, `prompts`, and `series-review` do not require OpenRouter.
- `gen`, `fix`, and `charsheet` are paid image-output operations and require `OPENROUTER_API_KEY` or the hosted provider.
- For reviews, lead with concrete fixes: problem, reader impact, and what to change on the page.
- For QA, compare the generated image to the request and spec. The verdict alone is not enough; include concrete defects that `fix` can feed back into regeneration.
- For `format: series-episode`, evaluate episode delta, continuity, and cliffhanger. Do not require one-shot completion satisfaction.
- For `format: x-carousel`, evaluate hook -> body -> cta, square mobile readability, and carousel constraints.

## Command Preference

Prefer the repository tools:

```bash
python3 tools/build_prompt.py --mode name-review path/to/draft.md
python3 tools/mangagen.py lint --spec path/to/storyboard.json
python3 tools/mangagen.py review --spec path/to/storyboard.json
python3 tools/mangagen.py qa --spec path/to/storyboard.json
uv run manga gen path/to/storyboard.json -page 1 2
uv run pytest
```

Use `uv run pytest` for code changes. For documentation-only skill updates, run the skill validator instead.

## Output Discipline

- When writing `review.json`, `page_XX.json`, or `series_review.json`, follow the JSON schema in the generated request and do not add Markdown around it.
- When giving human-facing review, write in Japanese unless the user requests otherwise.
- Do not present general manga theory as absolute. Tie each suggestion to reader comprehension, character appeal, page turn, or production risk.
