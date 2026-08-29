# Scoring golden fixtures

The 2025 Yahoo scoring **oracle** — the ground truth the engine is validated
against by `tests/test_scoring_gate.py` (`pytest -m gate`).

| File | Role |
| --- | --- |
| `yahoo_2025_box_scores.raw.json` | raw scrape of the archived 2025 league's per-team weekly box scores: `{"<name>\|<week>": [yahoo_total, [[stat label, count], …]]}` |
| `yahoo_2025_oracle.json` | Yahoo's own weekly total per scoring entity — **derived** from the raw file |
| `yahoo_2025_stat_rows.json` | the matching stat lines the engine scores — **derived** from the raw file |

Regenerate the two derived files from the raw one:

```bash
cd backend && uv run python -m deadparrots.scoring.oracle build
```

Scope: weeks 1 / 5 / 9 / 13, all 12 teams (starters + bench), offense + kicker +
team defense. To widen it, add box-score entries to the raw file and re-run
`build`. Full procedure and rationale: `docs/scoring-oracle-capture.md`.
