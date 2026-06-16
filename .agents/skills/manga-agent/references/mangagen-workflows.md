# Mangagen Workflows

Use this reference when operating `tools/mangagen.py`, the hosted provider CLI, or a `storyboard.json`.

## Required Reading

- `docs/harness.md` for the current harness design and failure modes.
- `docs/knowledge/INDEX.md` before selecting craft documents.
- `docs/hosted-provider.md` when using `uv run manga ...`.
- `docs/x_ads_manga_principles.md` for `format: x-carousel`.
- `docs/series_principles.md` for `format: series-episode`.

## Standard Pipeline

```bash
SPEC=examples/demo-product/manga/production/spec/storyboard.json

python3 tools/mangagen.py lint --spec "$SPEC"
python3 tools/mangagen.py review --spec "$SPEC"
python3 tools/mangagen.py prompts --spec "$SPEC"
python3 tools/mangagen.py gen --spec "$SPEC" --pages 1,8
python3 tools/mangagen.py qa --spec "$SPEC"
python3 tools/mangagen.py fix --spec "$SPEC"
python3 tools/mangagen.py assemble --spec "$SPEC"
```

Keep this order unless the user has a specific reason. `gen` internally runs `lint`, but explicit `lint` and `review` catch problems before paid work.

## Cost Boundary

Free and deterministic or agent-request commands:

- `lint`
- `review`
- `prompts`
- `qa`
- `series-review`
- `assemble`

Paid image output commands:

- `gen`
- `fix`
- `charsheet`

Paid commands require `OPENROUTER_API_KEY` or `OPENROUTER`, unless the hosted provider is configured.

## Hosted Provider

Use when the user wants generation through the operator server rather than their own OpenRouter key:

```bash
uv run manga login https://hosted-api-url
uv run manga token
uv run manga gen "$SPEC" -page 1 2
```

Check `MANGA_API_URL`, `MANGA_SUPABASE_URL`, and `MANGA_SUPABASE_ANON_KEY` only when hosted-provider setup is in scope.

## Series Episode

For `format: "series-episode"`:

```bash
python3 tools/mangagen.py lint --series-root projects/onibaku/manga/production/spec
python3 tools/mangagen.py review --spec "$SPEC"
python3 tools/mangagen.py series-review --series-root projects/onibaku/manga/production/spec
```

Evaluate episode-level `emotional_delta`, previous-episode continuity, next-episode hook, and series bible consistency. Do not demand one-shot closure.

## X Carousel

For `format: "x-carousel"`:

- Treat each page as a square card, not a book page.
- Evaluate hook -> body -> cta.
- Check 2-6 cards, mobile readability, 280 weighted ad copy, and final-card CTA.
- Inside each card, panel reading remains Japanese RTL unless the spec says otherwise.

## New Project

1. Copy `examples/demo-product/` into a new project folder.
2. Create or review script first; do not jump directly from prose to storyboard.
3. Copy `templates/pro_panel_craft_base.md` into the spec directory as `pro_panel_craft.md` and adapt acting/craft notes for the work.
4. Run `lint`, `review`, and `prompts` before `gen`.
5. Generate first-page and climax-page samples before all pages when style/character consistency is unproven.

## Failure Modes To Watch

- `max_tokens` too low: image may not return while still costing money.
- Right-left panel reversal in adjacent question/answer panels.
- Screen content drawn on the back of a laptop or phone.
- Character-sheet defects propagating into every page.
- `review` or `qa` verdict used without reading the concrete errors.
