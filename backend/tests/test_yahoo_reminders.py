from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.yahoo.pages import ALL_PAGES
from deadparrots.yahoo.reminders import due_reminder, most_recent_checkpoint
from deadparrots.yahoo.status import YahooPullStatus, record_yahoo_pull_status

# Stale Yahoo data produces a reminder, not a failure alert (spec issue #7,
# acceptance criterion 5; docs/adr/0001). 2026-09-26 is a Saturday, so the most
# recent checkpoint for a Saturday-morning `now` is 08:00 that same day.
SATURDAY_10AM = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


def _seed_pull(conn, finished_at, *, pages=ALL_PAGES, status="ok"):
    for page in pages:
        record_yahoo_pull_status(
            conn,
            YahooPullStatus(
                pull_id=finished_at.strftime("%Y%m%dT%H%M%SZ"),
                source=page.source,
                page=page.value,
                status=status,
                raw_path="/x" if status == "ok" else None,
                error=None if status == "ok" else "boom",
                started_at=finished_at - timedelta(seconds=5),
                finished_at=finished_at,
            ),
        )


def test_most_recent_checkpoint_picks_the_last_wed_sat_or_sun_morning():
    assert most_recent_checkpoint(SATURDAY_10AM) == datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
    # a Thursday afternoon falls back to Wednesday 08:00
    thursday = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)
    assert most_recent_checkpoint(thursday) == datetime(2026, 9, 23, 8, 0, tzinfo=UTC)


def test_no_reminder_when_every_page_was_pulled_after_the_checkpoint(sqlite_conn):
    _seed_pull(sqlite_conn, datetime(2026, 9, 26, 9, 0, tzinfo=UTC))

    assert due_reminder(sqlite_conn, now=SATURDAY_10AM) is None


def test_reminder_when_the_last_full_pull_predates_the_checkpoint(sqlite_conn):
    _seed_pull(sqlite_conn, datetime(2026, 9, 25, 12, 0, tzinfo=UTC))  # Friday

    reminder = due_reminder(sqlite_conn, now=SATURDAY_10AM)

    assert reminder is not None
    assert set(reminder.stale_pages) == {p.value for p in ALL_PAGES}
    assert "Run an assisted pull" in reminder.reason
    assert reminder.checkpoint == datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


def test_reminder_names_only_the_stale_pages_on_a_partial_refresh(sqlite_conn):
    fresh = [p for p in ALL_PAGES if p.value != "injuries"]
    _seed_pull(sqlite_conn, datetime(2026, 9, 26, 9, 0, tzinfo=UTC), pages=fresh)
    _seed_pull(
        sqlite_conn,
        datetime(2026, 9, 23, 8, 30, tzinfo=UTC),  # injuries last ok on Wednesday
        pages=[p for p in ALL_PAGES if p.value == "injuries"],
    )

    reminder = due_reminder(sqlite_conn, now=SATURDAY_10AM)

    assert reminder is not None
    assert reminder.stale_pages == ("injuries",)


def test_reminder_when_there_has_never_been_a_pull(sqlite_conn):
    reminder = due_reminder(sqlite_conn, now=SATURDAY_10AM)

    assert reminder is not None
    assert reminder.last_successful_pull is None
    assert reminder.reason.startswith("No Yahoo assisted pull on record")
