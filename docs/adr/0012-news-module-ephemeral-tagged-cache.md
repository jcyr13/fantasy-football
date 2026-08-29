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
2.0 feed (the ESPN NFL and Yahoo Sports NFL feeds are both RSS 2.0 — the parser
handles `<channel>/<item>` and nothing else); `StaticNewsSource` serves captured
bodies for replay and tests. The HTTP GET is `# pragma: no cover` and never
unit-tested. `normalize_payload` is pure — a recorded JSON or XML body in, a
list of `ParsedArticle` out — and is the seam the recorded-payload test drives
(acceptance criterion 5).

**2. A poll fans out per feed; a feed failure is isolated and never emails.**
The runner iterates the configured feeds, archives each raw payload under
`<data>/news/<pull_id>/<source>.<ext>`, and writes one `news_pull_status` row
per feed (`ok` / `failed`, article count, error). This mirrors the Yahoo
assisted pull's per-page isolation. News is a convenience strip, not analysis
input, so — like Yahoo and consensus and unlike nflverse — a failure is logged,
surfaces in the data-freshness header, and (when *every* feed fails) hides the
ticker via `latest_pull_all_failed`. It never sends an alert.

**3. The target lists are an input, resolved by a provider the poll calls each
fire.** `NewsTargets` carries three name tuples — `my_roster`, `opponent`,
`free_agents` — a deliberate sibling input shape, resolved upstream exactly as
`WaiverState` is for the waiver layer (ADR-0011). `register_news_poll` takes a
zero-arg `targets_provider` so a running poll picks up a roster change without a
restart. The shipped provider (`targets_from_latest_yahoo_pull`) reads the Dead
Parrots and current-opponent rosters straight off the newest archived Yahoo
matchup payload; the **free-agent shortlist stays empty until issue #16**, which
owns free-agent ranking and is where the shortlist is a computed subset rather
than a raw page. Before the first Yahoo pull the provider returns empty targets
and the poll archives payloads and records feed status but tags — and therefore
retains — nothing.

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

**6. Dedupe by normalized URL *or* normalized title.** Two articles collapse
when their normalized URLs match **or** their normalized titles match. URL
normalization drops the scheme, `www.`, the query string, the fragment, and a
trailing slash — feeds differ on `http`/`https` and append per-feed tracking
params to the same canonical article. The title path (title reduced to
alphanumeric tokens) additionally catches the same story published by two feeds
under different canonical URLs — the reading "deduped by title/URL" (acceptance
criterion 1) wants. Within a dedupe group the kept item takes the earliest
`published_at`, the first non-empty summary, and a `+`-joined sorted `source`
label (`"espn-api+espn-rss"`).

**7. Retention: `[now − 48h, now + 60m]`.** The upper bound tolerates a small
clock skew between a feed's timestamps and ours before an item is treated as
bogus and dropped; `future_skew_minutes` (60) is the tolerance. The identical
bounds are applied on ingest (`build_news_feed`) and on read
(`load_cached_news` / `cached_articles`).

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

**10. Ephemeral SQLite, fully rebuilt each poll, never a snapshot.**
`news_items` is application state keyed by dedupe key with the poll's
`fetched_at` on every row (acceptance criterion 4). `replace_cached_news` clears
the table and writes the current feed in one transaction — a true rebuild, so an
item the feeds stopped carrying or one whose player left every target list does
not linger. Because upstream feeds only expose their latest headlines, the poll
first carries the still-fresh cached rows back in as untagged `ParsedArticle`
(`cached_articles`) and lets `build_news_feed` re-tag every article against the
*current* targets — so a story that scrolled off a feed but is still inside 48
hours survives, while a stale tag cannot. `news_items` is never read into a
`WeeklySnapshot` (acceptance criterion 6; CONTEXT.md "News ticker": "Ephemeral —
not part of a weekly snapshot"); the exclusion is structural — no snapshot code
references this module.

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
  `test_news_params.py`, tunable without a code change. `__main__` and
  `register_news_poll` both build `NewsParams` from `Settings`.
- The carry-forward means the cache size is bounded by the 48-hour window across
  *all* feeds' tagged output, not by one feed's page size — a story stays until
  it ages out, not until it scrolls off upstream.
- One `news/_time.py` holds the "make it aware UTC" helper the package needs in
  `normalize` / `raw` / `cache`; `news_pull_status` keeps its own `_parse` to
  stay identical to `consensus/status.py`.

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
- **Ship with an empty-targets provider and wait for #16 to supply a real
  one.** Rejected as the default: #15's acceptance criteria (tag, bucket, cache)
  would then never exercise in the running app. Instead a thin
  `targets_from_latest_yahoo_pull` reads the two rosters off the newest archived
  matchup payload — enough to make the ticker real today. It lives in its own
  `news/targets.py`, not the module core, and `register_news_poll` still takes
  any `targets_provider`, so #16 swaps in an assembled-view provider (which also
  contributes the free-agent shortlist) without touching the poll.
- **Compute the free-agent shortlist here too.** Rejected: the shortlist is a
  *ranked* subset of the free-agent universe, which is the Waiver / Free Agents
  layer's and #16's job; duplicating that ranking in the news module would be a
  second source of truth.
