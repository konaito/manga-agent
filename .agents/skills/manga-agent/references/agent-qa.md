# Agent Review And QA

Use this reference when `mangagen` has generated an agent request and Codex must write the result JSON.

## Storyboard Review Request

Command:

```bash
python3 tools/mangagen.py review --spec "$SPEC"
```

Inputs:

- `output/latest/qa/review_request.md`
- `output/latest/qa/review_payload.json`

Output:

- `output/latest/qa/review.json`

Write JSON only, matching the request schema:

```json
{
  "overall": {
    "hook": "...",
    "change": "...",
    "character": "...",
    "page_allocation": "...",
    "hiki_mekuri": "...",
    "big_panel_distribution": "...",
    "reader_cost": "..."
  },
  "page_notes": [{"page": 1, "notes": ["..."]}],
  "top_fixes": [{"priority": 1, "page": 3, "issue": "...", "fix": "..."}],
  "verdict": "ship"
}
```

Use `verdict: "revise"` only when there is a structure issue that should be fixed before image generation. Rank `top_fixes` by production impact.

## Series Review Request

Command:

```bash
python3 tools/mangagen.py series-review --series-root "$SERIES_ROOT"
```

Inputs:

- `manga/production/output/latest/qa/series_review_request.md`
- `manga/production/output/latest/qa/series_review_payload.json`

Output:

- `manga/production/output/latest/qa/series_review.json`

Evaluate arc, motif tracking, episode continuity, and hook connection. Use `verdict: "revise"` only when the whole series has a pre-generation structural problem.

## Page Image QA Request

Command:

```bash
python3 tools/mangagen.py qa --spec "$SPEC"
```

Inputs per page:

- `output/latest/qa/page_XX_request.md`
- `output/latest/qa/page_XX_payload.json`
- `output/latest/pages/page_XX.png`

Output per page:

- `output/latest/qa/page_XX.json`

Process:

1. Open the generated page image and the request.
2. Transcribe the actual grid row by row.
3. Walk reader order: top to bottom, and right before left inside each row for Japanese RTL.
4. Check every expected text string, meaningful invented text, character identity, forbidden UI, hands, and screen physics.
5. Keep layout-slot deviations as `warn` if reader order is still correct.
6. Use `fail` only for missing/wrong expected text, non-ascending reader sequence, main character identity swap/unidentifiable character, forbidden UI, or hard screen-physics defects.

Write JSON only:

```json
{
  "grid": "r1: full=P1 / r2: right=P2, left=P3",
  "reader_sequence": [1, 2, 3],
  "text_errors": [],
  "extra_text": [],
  "order_ok": true,
  "order_notes": "",
  "identity_errors": [],
  "forbidden_found": [],
  "verdict": "pass"
}
```

## Fix Loop

`fix` reads failed page JSON and injects feedback into regeneration. Make errors specific enough to be useful:

- Bad: `"text issue"`
- Good: `"panel p04_02 missing expected string '...'"`
- Good: `"reader order is P1,P3,P2 because row2 right/left panels are swapped"`
- Good: `"laptop UI appears on the back of the lid in p06_03"`
