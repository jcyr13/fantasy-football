# Dead Parrots Dashboard

A single-user decision-support dashboard for managing the **Dead Parrots** fantasy team in the **RIP TIDE League** (Yahoo, 12-team H2H). It produces recommendations only; it never executes a roster move.

## Language

### League & teams

**RIP TIDE League**:
The specific Yahoo league this tool serves (ID 735806, 12 teams, 2 divisions, head-to-head). The tool models this league and no other.
_Avoid_: "the league" without qualification when another league could be meant.

**Dead Parrots**:
John's team in the RIP TIDE League. The subject of every recommendation.
_Avoid_: "my team", "our team" in code and docs.

**Manager**:
A human who controls a team in the league. The other 11 are relevant only as opponents and trade partners.
_Avoid_: owner, player (a player is an NFL athlete).

### Scoring

**Scoring engine**:
The one pure function `(stat rows, league ruleset) → points per player-week`. No I/O. Covers offense, kicker, team **DEF**, and the **IDP / D slot** as its own `ScoringUnit` distinct from team DEF. RIP TIDE also scores individual defensive plays (tackles, passes defended) for *any* player who records them, using the same shared values. Fractional and negative points are on — nothing is rounded to an integer or floored at zero.

**League ruleset**:
The RIP TIDE scoring values (`RIP_TIDE_RULESET`) transcribed field-for-field from the league settings and reconciled against Yahoo's own 2025 box scores: 25/10/10 offensive yards-per-point, return yards at 1 per 25, 6-point TDs, distance-tiered field goals, shared individual-defense values, the team-DEF points-allowed schedule, and so on.

**Scoring oracle**:
Real 2025 Yahoo per-player weekly fantasy points for the archived RIP TIDE league (2025 id `195010`), scraped from Yahoo's own weekly box scores (the Fantasy API is not reachable for this account) and frozen as golden fixtures. Sample: weeks 1 / 5 / 9 / 13, all 12 teams. The ground truth the engine is checked against.

**Validation gate**:
The hard requirement that the engine reproduce the scoring oracle *exactly* (0.00) for every offense/kicker/DEF player-week before anything is built on it. The highest-weight test in the repo, run as its own CI step (`pytest -m gate`). The **IDP gate** is the parallel check for the D slot, held to ±1.0 with every out-of-tolerance player-week listed in a committed **outlier catalogue** (`yahoo_2025_idp_outliers.json`) with a stated cause — never silently accepted.

### Matchup & win probability

**Matchup**:
One week's head-to-head pairing of Dead Parrots against one opponent team.

**Win probability**:
`P(Dead Parrots weekly total > opponent weekly total)`, estimated by head-to-head Monte Carlo over both lineups' correlated scoring distributions.

**Favored / Underdog**:
Dead Parrots are favored when win probability is above 50%, underdog below. Magnitude matters, not just the side.

**Gap drivers**:
The per-roster-slot decomposition of the difference in expected points between the two lineups — which slots explain why one side is ahead.

**Swing player**:
An opponent's starter contributing an outsized share of the *variance* in the matchup outcome, i.e. the player most able to change the result.

### Lineup construction

**Projection**:
A player's simulated weekly fantasy-point distribution under RIP TIDE scoring, summarised as **floor (P10) / projection (P50) / ceiling (P90)**.

**Floor lineup / Ceiling lineup**:
The legal lineup that maximises P10 / maximises P90 respectively. Comparison views, not the primary recommendation.

**Max-P(win) lineup**:
The legal lineup that maximises win probability against this week's opponent. The primary recommendation. Leans low-variance when favored and high-variance when underdog as a mathematical consequence, not a rule.

**Max-EV lineup**:
The legal lineup that maximises expected points, ignoring the opponent. Shown alongside Max-P(win) to expose when they disagree.

**Opponent likely lineup**:
The opponent's projected starters: their Yahoo-set lineup when available, otherwise last week's starters adjusted for injury, bye, and obvious bench upgrades. Never assumed optimal.

### Projections & modeling

**Opportunity score**:
A player's role-and-usage signal from nflverse (snap share, target share, route participation, red-zone touches), exponentially decay-weighted toward recent games. Distinct from fantasy output.

**Fantasy points allowed to position**:
A defense's matchup strength, measured as the fantasy points (RIP TIDE scoring) it has surrendered to a given position, decay-weighted. The input to the capped matchup adjustment.

**Consensus feed**:
An external weekly projection source used as a cross-check against the model's number and as the fallback projection when a player has too little current-season history. `ffanalytics` runs in the one-shot `rsidecar` and emits raw stat projections; the backend re-scores them with `RIP_TIDE_RULESET` through the same scoring engine the model uses (never a second implementation — ADR-0005). The Sleeper public API is the Week-1 stopgap and the automatic fallback when the sidecar has no fresh drop.
_Avoid_: treating the consensus number as independently RIP-TIDE-scored, or as the source of a player's floor/ceiling shape (that is the model's positional residuals).

### Strategic layers

**Team strength**:
Dead Parrots' rolling points-for (decay-weighted) as a percentile against the other 11 teams. The health signal — deliberately *not* win/loss record.

**Expected wins**:
How many of the season's weeks Dead Parrots' scores would have won against a randomly drawn league opponent. Compared to actual wins to expose luck.

**Contend / Rebuild / Hold signal**:
A weekly advisory (from ~Week 5) derived from team-strength percentile and playoff odds. States the signal and the numbers behind it; recommends no specific action.

**Bye-week crunch**:
A future week where Dead Parrots have multiple rostered starters on bye at one position. **Warn** at 2 at a position; **critical** at 3+ or any week a legal healthy lineup can't be fielded.

**Buy-low candidate**:
A player whose opportunity score is trending up while fantasy output lags — undervalued by the market.

**Sell-high candidate**:
A player whose fantasy output is spiking while opportunity is flat or declining — overvalued by the market, more so with injury risk or a hard upcoming schedule.

**Market-value proxy**:
External consensus rest-of-season rank, used as a stand-in for what leaguemates believe a player is worth (there is no real trade market to observe).

**Desperate-team read**:
A ranking of the other 11 managers by willingness to deal, from sub-.500 record, low points-for, roster age, and their own bye-week crunch.

### Roster mechanics & value

**IDP / D slot**:
The individual-defensive-player starting slot in RIP TIDE (tackle, sack, INT, pass-defended, etc. scored per player). Modeled separately from **DEF** (team defense/special teams).

**Value over replacement**:
A player's projected points minus the projected points of a freely-available replacement at the same position. The basis for rest-of-season free-agent ranking.

**Rest-of-season value**:
Free-agent ranking for hold-and-start adds, by value over replacement across remaining weeks.

**This-week streamer**:
Free-agent ranking for a bye/injury hole in the current week, by next-week ceiling (P90), especially at K / DEF / IDP.

**Waiver priority**:
Dead Parrots' position in the reverse-standings waiver queue. No FAAB. A successful claim drops the team to last priority, so a claim has a cost.

**Waiver window**:
The Sun–Tue weekly claim period. Also the flagged 24–48h after NFL roster cutdowns and practice-squad churn, when forced drops make the pool unusually deep.

### Data & operations

**Assisted pull**:
The way Yahoo data is retrieved in v1: John signs into Yahoo in the browser, then one click runs a browser-scrape (matchup, players, injuries, standings) against that live session. It ingests through a source interface designed so the official API can replace it later without changes downstream.

**News ticker**:
The top-pinned horizontal scrolling strip of NFL news items from the last 48 hours that mention a Dead Parrots player, a current opponent's player, or a free-agent shortlist player. Sourced from free feeds, tagged by name match, labelled by bucket. Ephemeral — not part of a weekly snapshot.

**Weekly snapshot**:
An immutable per-week record of projections, lineups, recommendations, and — backfilled after games — the actual outcome. Retained for the whole season for "what did the model say, and what happened?".

**Data-freshness header**:
The always-visible per-source status strip (last successful pull, age, current ok/failed state). Backed by an email alert on failure.
