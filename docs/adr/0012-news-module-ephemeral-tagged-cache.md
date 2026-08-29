# News module: an ephemeral tagged cache behind the source interface, targets resolved upstream

Spec issue #15 asks for a `news` module that polls ESPN's keyless NFL news
endpoint plus one or two RSS feeds (ESPN NFL, Yahoo Sports NFL) at most every
~30 minutes, tags each item to players by name-matching against the Dead Parrots
roster, the current opponent's roster, and a free-agent shortlist, dedupes by
title/URL, keeps only the last 48 hours, labels each item by bucket, and caches
results to SQLite with `fetched_at`. News is **not** part of any weekly
snapshot. `docs/methodology.md` says nothing about news — it is not a model
input — so every numeric knob here is a build choice. Vocabulary is CONTEXT.md's
("News ticker", "News bucket").

## Decision

**1. Same source-interface shape as every other ingestion path.**
`deadparrots.news.sources.NewsSource` is the swappable fetch seam, exactly like
`LiveNflverseSource` / `BrowserYahooSource` / `SleeperConsensusSource`.
`EspnNewsApiSource` hits the keyless endpoint; `RssNewsSource` fetches one RSS
2.0 feed; `StaticNewsSource` serves captured bodies for replay and tests. The
HTTP GET is `# pragma: no cover` and never unit-tested. `normalize_payload` is
pure — a recorded JSON or XML body in, a list of `ParsedArticle` out — and is
the seam the recorded-payload test drives (acceptance criterion 5).

**2. A poll fans out per feed; a feed failure is isolated and never emails.**
The runner iterates the configured feeds, archives each raw payload under
`<data>/news/<pull_id>/<source>.<ext>`, and writes one `news_pull_status` row
per feed (`ok` / `failed`, article count, error). This mirrors the Yahoo
assisted pull's per-page isolation. News is a convenience strip, not analysis
input, so — like Yahoo and consensus and unlike nflverse — a failure is logged,
surfaces in the data-freshness header, and (when *every* feed fails) hides the
ticker via `latest_pull_all_failed`. It never sends an alert.

**3. The target lists are an input, not something the module computes.**
`NewsTargets` carries three name tuples — `my_roster`, `opponent`,
`free_agents`. Whoever assembles the weekly view (issue #16) turns the latest
Yahoo pull's rosters and the free-agent shortlist into a `NewsTargets`, the same
way `WaiverState` is resolved upstream of the waiver layer (ADR-0011). This is a
deliberate sibling input shape: issue #15 ships independently of #16, which is
the merge point. Until #16 wires a real provider, `app.py` passes
`NewsTargets.empty` and the scheduled poll archives payloads and records feed
status but tags — and therefore retains — nothing.

**4. Name matching is normalize-both-sides, word-boundary, suffix-insensitive.**
Both the target name and the article's title + summary are casefolded, stripped
of accents (`unicodedata` NFKD), reduced to alphanumeric tokens on any
non-alphanumeric run, and stripped of trailing name suffixes (`jr`, `sr`, `ii`,
`iii`, `iv`, `v`). `"A.J. Brown"`, `"AJ  Brown"`, and `"A. J. Brown"` all
normalize to `aj brown`; `"Odell Beckham Jr."` in a headline matches a roster
entry of `"Odell Beckham"`. The match is a word-boundary regex on the
normalized haystack, so `"Josh Allen"` does not match `"Josh Allendale"`. Only
the title and the feed's own summary are searched — not the article body, which
these feeds do not carry.

**5. Bucket precedence `my_roster > opponent > free_agent`; a player is tagged
once.** A player who appears on two target lists (a roster player mistakenly
also on the shortlist) is claimed by the highest-precedence bucket only. An item
that matches players in several buckets carries one `PlayerTag` per distinct
player and reports `buckets` in precedence order (user story #38).

**6. Dedupe by normalized URL, falling back to normalized title.** URL
normalization drops the scheme, `www.`, the query string, the fragment, and a
trailing slash — feeds differ on `http`/`https` and append per-feed tracking
params to the same canonical article. When an item has no usable URL its key is
its title reduced to alphanumeric tokens. Within a dedupe group the kept item
takes the earliest `published_at`, the first non-empty summary, and a
`+`-joined sorted `source` label (`"espn-api+espn-rss"`).

**7. Retention: `[now − 48h, now + 60m]`.** The upper bound tolerates a small
clock skew between a feed's timestamps and ours before an item is treated as
bogus and dropped; `future_skew_minutes` (60) is the tolerance. The window is
applied on ingest (`build_news_feed`) and again on read (`load_cached_news`),
and `replace_cached_news` prunes rows below the lower bound every poll.

**8. Untagged items are dropped, not stored.** Acceptance criterion 3 —
"Each retained item is tagged to a player and labelled with its bucket" — is
read as: an item with no player tag is not retained. The cache only ever holds
relevant items (user story #37).

**9. The ~30-minute cap is enforced in the runner, not only the trigger.**
`run_news_pull(throttle=True)` returns early with `skipped=True` when the last
successful poll (`last_successful_pull_at`) was under
`min_poll_interval_minutes` ago, so a shortened `IntervalTrigger`, a coalesced
misfire, or a manual "refresh now" all still respect the cap. A poll where every
feed failed writes no `ok` row, so the next attempt is not throttled and retries
promptly.

**10. Ephemeral SQLite, never a snapshot.** `news_items` is application state
keyed by dedupe key with the poll's `fetched_at` on every row (acceptance
criterion 4). It is replaced each poll and is explicitly excluded from
`WeeklySnapshot` (acceptance criterion 6; CONTEXT.md "News ticker": "Ephemeral —
not part of a weekly snapshot").

## Why

- **Reusing the source-interface / recorded-payload split** keeps news on the
  same test seam as every other ingestion path and keeps live HTTP out of CI.
- **Targets as an input** lets #15 land before #16 without inventing a
  roster-resolution path the module would then have to unlearn.
- **Normalize-both-sides matching** is the cheapest approach that survives the
  punctuation and accent noise real feeds carry, without a fuzzy matcher whose
  false-positive rate would put the wrong player's news on the ticker.
- **Drop untagged items** keeps the cache small and the ticker 100% relevant;
  nothing downstream wants league-wide news.

## Consequences

- Two payload formats (`espn-api-json`, `rss`) are hand-parsed. Malformed
  structure raises `NewsNormalizationError`; an empty-but-valid feed is not an
  error (a 48-hour window can be quiet). ESPN or Yahoo changing their payload
  shape is caught by the recorded-payload tests, not in production.
- `NewsTargets` is a third roster-carrying input shape alongside `LeagueState`
  (ADR-0009), `TradeDeskState` (ADR-0010), and `WaiverState` (ADR-0011);
  issue #16 reconciles all four.
- Name matching can still mistag two players who share a normalized full name
  (rare in one 12-team league's target set). Acceptable; the alternative is
  carrying player IDs through feeds that publish only prose.
- Every knob (`window_hours` 48, `min_poll_interval_minutes` 30,
  `future_skew_minutes` 60) lives in `NewsParams`, pinned by
  `test_news_params.py`, tunable without a code change.

## Considered alternatives

- **Score / rank news items.** Rejected: out of scope. The ticker shows the
  last 48 hours in reverse-chronological order; relevance is binary (tagged or
  not).
- **A fuzzy name matcher (token-set ratio, nicknames).** Rejected for v1: the
  false-positive cost (wrong player's news, shown prominently) outweighs the
  handful of stylized headlines it would additionally catch. Revisit if real
  feeds prove it necessary.
- **Keep untagged items too, tagged "league".** Rejected: contradicts user
  story #37 and bloats an ephemeral cache.
- **One `news_pull_status` row per poll instead of per feed.** Rejected: the
  freshness header and the hide-the-ticker rule both need per-feed state.
- **Fold news into the weekly snapshot.** Rejected by the spec outright.
- **Resolve rosters inside the news module from the Yahoo raw store.**
  Rejected: couples news to Yahoo's storage layout and duplicates the
  roster-assembly #16 already owns.
