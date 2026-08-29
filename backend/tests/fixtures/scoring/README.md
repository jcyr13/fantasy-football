# Scoring golden fixtures

Two files land here from the **one-off** 2025 Yahoo capture — see
`docs/scoring-oracle-capture.md`:

- `yahoo_2025_oracle.json` — Yahoo's own weekly fantasy-point total per scoring
  entity (the oracle).
- `nflverse_2025_stat_rows.json` — the counting-stat rows the engine scores.

Until both exist, `tests/test_scoring_gate.py` skips (loudly). Once committed
they are frozen golden data; regenerate only on a Yahoo restatement or a
league-settings correction.
