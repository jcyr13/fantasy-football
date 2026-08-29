from __future__ import annotations

import argparse
import logging
import sys

from ..config import get_settings
from ..db import init_sqlite
from .raw import YahooRawStore
from .reminders import due_reminder
from .runner import run_yahoo_pull
from .source import ReplayYahooSource


def main(argv: list[str] | None = None) -> int:
    """Run one assisted pull now. Exit non-zero if any page failed.

    v1 has no headless browser (docs/adr/0001), so this entry point either
    replays a previously archived pull (``--replay <pull_id>``, for developing
    the layers built on top) or reports that no assisted-pull source is wired
    for an unattended run.
    """
    parser = argparse.ArgumentParser(prog="python -m deadparrots.yahoo")
    parser.add_argument("--replay", metavar="PULL_ID", help="re-normalize an archived pull")
    parser.add_argument("--week", type=int, default=None, help="matchup week to pull")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    raw_store = YahooRawStore(settings.data_dir)
    sqlite_conn = init_sqlite(settings.sqlite_path)

    try:
        if not args.replay:
            from datetime import datetime

            reminder = due_reminder(sqlite_conn, now=datetime.now().astimezone())
            print(
                "No assisted-pull source is wired for an unattended run. "
                "Trigger the pull from the dashboard's signed-in browser session, "
                "or pass --replay <pull_id> to re-normalize an archived pull."
            )
            if reminder is not None:
                print(f"reminder: {reminder.reason}")
            return 2

        source = ReplayYahooSource(raw_store, args.replay)
        run = run_yahoo_pull(
            source=source, raw_store=raw_store, conn=sqlite_conn, week=args.week
        )
    finally:
        sqlite_conn.close()

    print(f"yahoo pull {run.pull_id} (replay of {args.replay})")
    for result in run.results:
        print(f"  {result.status:6} {result.page.value:10} {result.error or ''}".rstrip())
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())
