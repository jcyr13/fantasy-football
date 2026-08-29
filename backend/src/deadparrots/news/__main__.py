from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..config import get_settings
from ..db import init_sqlite
from .params import NewsParams
from .raw import NewsRawStore
from .runner import run_news_pull
from .sources import StaticNewsSource, build_news_sources
from .tagging import NewsTargets


def _load_targets(path: str | None) -> NewsTargets:
    if not path:
        return NewsTargets.empty()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return NewsTargets(
        my_roster=tuple(data.get("my_roster", ())),
        opponent=tuple(data.get("opponent", ())),
        free_agents=tuple(data.get("free_agents", ())),
    )


def main(argv: list[str] | None = None) -> int:
    """Run one news poll now. Exit non-zero if every feed failed."""
    parser = argparse.ArgumentParser(prog="python -m deadparrots.news")
    parser.add_argument(
        "--targets",
        metavar="PATH",
        help="JSON file with my_roster / opponent / free_agents name lists",
    )
    parser.add_argument(
        "--no-throttle",
        action="store_true",
        help="ignore the ~30-minute poll throttle for this run",
    )
    parser.add_argument(
        "--replay",
        metavar="PULL_ID",
        help="re-normalize an archived pull's payloads instead of fetching",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    raw_store = NewsRawStore(settings.data_dir)
    conn = init_sqlite(settings.sqlite_path)

    if args.replay:
        payloads = raw_store.load_payloads(args.replay)
        if not payloads:
            print(f"no archived news payloads for pull {args.replay}")
            return 2
        sources = [StaticNewsSource(payloads)]
    else:
        sources = list(build_news_sources(settings))

    params = NewsParams(
        window_hours=settings.news_window_hours,
        min_poll_interval_minutes=settings.news_poll_interval_minutes,
    )
    try:
        run = run_news_pull(
            sources=sources,
            raw_store=raw_store,
            conn=conn,
            targets=_load_targets(args.targets),
            params=params,
            throttle=not args.no_throttle,
        )
    finally:
        conn.close()

    if run.skipped:
        print("news poll skipped (within the throttle window)")
        return 0

    print(f"news poll {run.pull_id}")
    for result in run.results:
        count = result.article_count if result.article_count is not None else "-"
        print(
            f"  {result.status:6} {result.source:10} articles={count} "
            f"{result.error or ''}".rstrip()
        )
    retained = len(run.feed) if run.feed is not None else 0
    print(f"  retained {retained} item(s) in the {run.feed.window_hours}h window"
          if run.feed is not None else "  no feed built")
    return 0 if run.any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
