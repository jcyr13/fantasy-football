from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..config import get_settings
from ..db import init_sqlite
from .importer import YahooImportError, import_yahoo_pages, read_import_dir
from .raw import YahooRawStore
from .reminders import due_reminder
from .runner import run_yahoo_pull
from .source import ReplayYahooSource


def main(argv: list[str] | None = None) -> int:
    """Run one assisted pull now. Exit non-zero if any page failed.

    v1 has no headless browser (docs/adr/0001), so this entry point either
    replays a previously archived pull (``--replay <pull_id>``, for developing
    the layers built on top), imports page files captured outside the app
    (``--import <dir>``, issue #55; docs/yahoo-import.md), or reports that no
    assisted-pull source is wired for an unattended run.
    """
    parser = argparse.ArgumentParser(prog="python -m deadparrots.yahoo")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--replay", metavar="PULL_ID", help="re-normalize an archived pull")
    modes.add_argument(
        "--import",
        dest="import_dir",
        metavar="DIR",
        type=Path,
        help="import <page>.json files captured outside the app",
    )
    parser.add_argument("--week", type=int, default=None, help="matchup week to pull")
    args = parser.parse_args(argv)
    if args.import_dir is not None and args.week is not None:
        parser.error("--week does not apply to --import (the matchup payload carries its week)")

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    raw_store = YahooRawStore(settings.data_dir)
    sqlite_conn = init_sqlite(settings.sqlite_path)

    try:
        if args.import_dir is not None:
            try:
                bodies = read_import_dir(args.import_dir)
            except YahooImportError as exc:
                print(f"nothing to import: {exc}")
                return 2
            run = import_yahoo_pages(bodies, raw_store=raw_store, conn=sqlite_conn)
            run_label = f"import of {args.import_dir}"
        elif not args.replay:
            from datetime import datetime

            reminder = due_reminder(sqlite_conn, now=datetime.now().astimezone())
            print(
                "No assisted-pull source is wired for an unattended run. "
                "Trigger the pull from the dashboard's signed-in browser session, "
                "pass --import <dir> to load page files captured outside the app, "
                "or pass --replay <pull_id> to re-normalize an archived pull."
            )
            if reminder is not None:
                print(f"reminder: {reminder.reason}")
            return 2
        else:
            source = ReplayYahooSource(raw_store, args.replay)
            run = run_yahoo_pull(
                source=source, raw_store=raw_store, conn=sqlite_conn, week=args.week
            )
            run_label = f"replay of {args.replay}"
    finally:
        sqlite_conn.close()

    print(f"yahoo pull {run.pull_id} ({run_label})")
    for result in run.results:
        print(f"  {result.status:6} {result.page.value:10} {result.error or ''}".rstrip())
    if run.waiver_priority_needs_manual_entry:
        print("  waiver priority not on the standings page - flagged for manual entry")
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())
