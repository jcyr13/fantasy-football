"""Regenerate the projection regression fixture.

Run by hand whenever the projection model *intentionally* changes:

    uv run python scripts/gen_projection_fixtures.py

It writes ``tests/fixtures/projection/regression.json`` from the scenarios in
``tests/projection_cases.py``. ``test_projection_regression.py`` then pins every
number in that file, so an *unintended* change to ``project`` fails CI with a
diff instead of silently shifting the golden values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[1] / "tests"
sys.path.insert(0, str(_TESTS))

from projection_cases import CASES, expected_payload  # noqa: E402

FIXTURE = _TESTS / "fixtures" / "projection" / "regression.json"


def main() -> None:
    cases = [{"name": case.name, "expected": expected_payload(case)} for case in CASES]
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases -> {FIXTURE.relative_to(_TESTS.parent)}")


if __name__ == "__main__":
    main()
