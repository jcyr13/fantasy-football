from __future__ import annotations

import argparse
import logging
import sys

from ..config import get_settings
from ..db import init_sqlite
from .raw import ConsensusRawStore
from .runner import run_consensus_pull
from .sources import StaticConsensusSource, build_consensus_source, current_season_week


def main(argv: list[str] | None = None) -> int:
    """Run one consensus-feed pull now. Exit non-zero if it failed."""
    parser = argparse.ArgumentParser(prog="python -m deadparrots.consensus")
    parser.add_argument("--season", type=int, default=None, help="NFL season (default: current)")
    parser.add_argument("--week", type=int, default=None, help="NFL week (default: current)")
    parser.add_argument(
        "--source",
        choices=["auto", "sleeper", "rsidecar"],
        default=None,
        help="override DEADPARROTS_CONSENSUS_SOURCE for this run",
    )
    parser.add_argument(
        "--replay",
        metavar="PULL_ID",
        help="re-normalize an archived payload instead of fetching",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    if args.source is not None:
        settings = settings.model_copy(update={"consensus_source": args.source})

    raw_store = ConsensusRawStore(settings.data_dir)
    sqlite_conn = init_sqlite(settings.sqlite_path)

    if args.replay:
        payload = raw_store.load_payload(args.replay)
        if payload is None:
            print(f"no archived consensus payload for pull {args.replay}")
            return 2
        source = StaticConsensusSource(payload.body)
        season = args.season or payload.season
        week = args.week or payload.week
    else:
        source = build_consensus_source(settings)
        season, week = current_season_week(settings)
        season = args.season or season
        week = args.week or week

    try:
        run = run_consensus_pull(
            source=source,
            raw_store=raw_store,
            conn=sqlite_conn,
            season=season,
            week=week,
        )
    finally:
        sqlite_conn.close()

    r = run.result
    count = r.projection_count if r.projection_count is not None else "-"
    print(f"consensus pull {run.pull_id} (season {season}, week {week})")
    print(f"  {r.status:6} source={r.source} projections={count} {r.error or ''}".rstrip())
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())
