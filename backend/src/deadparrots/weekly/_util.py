from __future__ import annotations

# Small shared helpers for the weekly-assembly modules.

__all__ = ["to_float"]


def to_float(value: object) -> float:
    """Coerce a raw frame cell (``None``, ``"NA"``, a numpy scalar, …) to a
    plain float; anything uncoercible reads as ``0.0``. The one place the
    assembly tolerates dirty nflverse cells."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
