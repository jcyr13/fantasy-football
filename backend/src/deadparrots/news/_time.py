from __future__ import annotations

from datetime import UTC, datetime

# One home for the "make this datetime tz-aware UTC" idiom the news package
# needs in three places (parsing feed dates, replaying a manifest, reading the
# SQLite cache). ``news_pull_status`` keeps its own private ``_parse`` to stay
# byte-for-byte with ``consensus/status.py``.


def ensure_utc(value: datetime) -> datetime:
    """``value`` as an aware UTC datetime — naive input is assumed to be UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def parse_utc(text: str) -> datetime:
    """Parse an ISO-8601 string (trailing ``Z`` allowed) to an aware UTC
    datetime, converting any offset to UTC. Raises ``ValueError`` on anything
    unparseable.
    """
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return ensure_utc(parsed).astimezone(UTC)
