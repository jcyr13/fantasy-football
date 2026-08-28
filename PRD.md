# RIP TIDE Fantasy Football Management Dashboard — PRD

*Draft for sign-off. Not yet built beyond initial technical scoping (noted below).*

## Problem

Weekly decision support for John's RIP TIDE League (Yahoo, ID# 735806, 12 teams, H2H, 2 divisions): read the opponent, know whether he's favored or underdog, build floor vs. ceiling lineup options accordingly, and identify free-agent/waiver targets — plus the standing strategic layers below (built together with v1, not deferred).

## Success criteria

Given a week, the dashboard answers:
- Who's the opponent, what's their likely starting lineup, and what is Yahoo/the model projecting for both sides?
- Favored or underdog, by roughly how much, and which players are driving the gap?
- Best floor lineup vs. best ceiling lineup for John's team, with the tradeoff named — leaning safe when favored, boom-or-bust when underdog (per the win-probability-adjusts-risk-tolerance logic John cited).
- Ranked free-agent/waiver targets against bench needs and upcoming byes.
- Ongoing: team-strength read (points scored, not record) and a contend/rebuild signal from ~Week 5 on; bye-week roster-crunch map; buy-low/sell-high trade candidates; a flag for the post-cuts waiver window.

## Scope

**In:** RIP TIDE League only. Weekly lineup planning + all four strategic layers (team-strength/contend-rebuild, bye-week crunch, buy-low/sell-high, waiver-window timing) built together, not phased behind separate sign-offs.

**Out:** Draft-day support (explicitly declined — draft is Sun Aug 30, this tool starts after). Executing any Yahoo transaction — add/drop, waiver claim, trade — ever. This produces recommendations only; any actual roster move gets shown to John and requires his explicit go-ahead in the moment, every time.

## Data sources (confirmed)

**Yahoo** (via the built-in browser on the linked desktop, authenticated session) — three pages, John-provided:
1. `/f1/735806/matchup` — opponent roster, opponent's starting lineup, **and Yahoo's own weekly projections** (useful as a cross-check against the model below).
2. `/f1/735806/players` — free agents / waiver-eligible players.
3. `/f1/735806/injuries` — injury report.

Open gap: none of these three surface **waiver priority** (reverse-order-of-standings). Likely lives on the Standings page — will check there when building that piece and confirm with John if it's not visible.

**League scoring & settings** (from John's PDF, now hardcoded into spec): Head-to-head, roster = QB, 2WR, 2RB, TE, W/R/T flex, K, DEF, **D (individual defender)**, 5 BN, 2 IR. Fractional points on, negative points on. Offense: 25/10/10 yards-per-point, 6-pt TDs across the board, -1 INT, -1 sack taken, 2-pt conversions = 2. Kicker: distance-tiered (3/3/3/4/5), -1 missed 0-19, PAT 1/-1. Team DEF: sack 2, INT 2, fumble recovery 1, TD 6, safety 2, block kick 2, points-allowed tiers (10/7/4/1/0/-1/-4), TFL 1. Individual defender (D slot): solo tackle 1, assist 0.5, sack 2, INT 2, forced fumble 1, fumble recovery 1, TD 6, safety 2, pass defended 1, block kick 2, TFL 1, turnover-return yards 25/pt. Waivers: reverse order of standings, 2-day clock, Sun–Tue weekly window. Trade deadline Nov 28; playoffs = 6 teams, weeks 15–17, reseeded, division winners get top seeds.

**nflverse** (cloud workspace, not device-dependent) — historical play-by-play and weekly stats, pulled via `nfl_data_py`. This is the analytics backbone for floor/ceiling, matchup adjustment, and the strategic layers.

## Phase 3 — Strategic layers (detail)

Built alongside v1, on the same data model, per "Phase 3 now." Four features, drawn from the frameworks John sent:

**1. Win-probability-adjusted risk tolerance.** Not really a separate phase — this is core v1 logic (favored → high-floor lineup, underdog → boom-or-bust). Noted here because it's the thread the other three hang off of.

**2. Bye-week / trade-window process (Pianowski's approach).** Starting ~Week 5, run weekly: assess true team strength using points-scored trend rather than win-loss record; use that to decide whether John's team should play for now (contend) or for the future (rebuild); map the bye-week distribution across his roster to flag upcoming positional crunches before they hit; surface trade leverage opportunities — teams that look "desperate" (bad record, aging roster, or a bye-week crunch of their own) as sell-star targets, or, when John's team is deep, packaging bench depth to offer a losing team in exchange for one of their stars. Also flag the 24–48 hours right after final roster cuts (typically late August/early September and after in-season practice-squad churn) as a prime waiver window, since other managers get forced into drops. **Data note:** points-scored trend and bye-week mapping are straightforward from nflverse + league rosters; "which teams look desperate" requires opponent roster/record context I don't have a clean source for yet beyond what's visible per-matchup on Yahoo — likely needs the Standings/League page added to the Yahoo pull list.

**3. Data-driven start/sit (Joyner's approach).** Early each week: check positional needs and flag waiver fills before the win/loss projection step; use the favored/underdog read to set floor-vs-ceiling lean (v1 logic); layer in injury reports (Yahoo `/injuries`) and matchup context; for genuinely close start/sit calls between comparable players, run a simple internal simulation (Monte Carlo over each player's historical scoring distribution under this league's scoring rules) as a lightweight stand-in for the commercial "which of these two should I start" tools Joyner uses — those tools themselves aren't accessible to me, so this is a build-it-ourselves approximation, not a real substitute, and I'll say so in any output rather than implying equivalent rigor. Weather and TE-route-specific data are stretch items — not committing to those as v1-of-Phase-3 unless a clean nflverse-accessible source turns up.

**4. Buy-low/sell-high trade evaluation (Giuffra's approach).** Separate recent fantasy-point results from underlying opportunity (target share, snap %, red-zone usage trend) using nflverse weekly data. Buy-low candidates: players whose opportunity metrics are rising or shifted favorably (e.g., a QB change, a role change) but whose fantasy output hasn't caught up yet. Sell-high candidates: players riding a scoring peak that their underlying usage doesn't support, especially with injury risk, a tough upcoming matchup, or inconsistent target share as the reason the market (i.e., other RIP TIDE managers) may be overvaluing them right now. Treat the weeks before the Nov 28 trade deadline as a hard cutoff — the tool should flag "trade window closing" as that date approaches.

## Constraints

- Yahoo pulls remain session- and desktop-online-dependent (three pages, narrow surface — much smaller than originally scoped).
- nflverse gives **historical** stats, not forward projections — floor/ceiling will be a model John and I define (trailing variance, opportunity share, matchup adjustment), not a lookup. I'll be explicit about methodology and confidence rather than presenting it as ground truth. Yahoo's own projections (from the matchup page) can serve as a cross-check.
- **Technical finding from initial scoping (not yet resolved):** `nfl_data_py`'s pinned data URL for weekly player stats returns a 404 for the 2025 season specifically (2024 and earlier pull fine). This needs to be root-caused before Phase 1 build starts for real — either the package is stale relative to nflverse's current release naming, or 2025 season data lives under a different asset name. Flagging now rather than assuming it'll just work.
- IDP scoring (the "D" slot) is real added modeling surface — nflverse has player-level defensive stats, but solo/assist tackles, TFL, and pass-defended tracking are less standardized than offensive box scores and need their own validation pass.
- Building all four strategic layers alongside v1 (per "Phase 3 now") is a meaningfully larger build than lineup-only — flagging so the timeline expectation is set correctly, not because it's off the table.

## Plan (once signed off)

1. Resolve the nflverse data-access issue; pull rosters/weekly stats/schedules/injuries into the cloud workspace.
2. Build the scoring engine implementing the exact rules above (offense/kicker/DEF/IDP), validate against real 2025 box scores before trusting it for anything else.
3. Define and document the floor/ceiling methodology for John's review before it drives any recommendation.
4. Build the weekly pull from the three Yahoo pages; resolve the waiver-priority gap.
5. Compute favored/underdog, floor/ceiling lineups, waiver rankings.
6. Build the four strategic-layer modules (team-strength/contend-rebuild, bye-week crunch, buy-low/sell-high, waiver-window timing) on the same data model.
7. Package as a persisted, revisitable dashboard.

## Open questions

1. Waiver priority — is it visible somewhere I'm not seeing yet, or should I just check the Standings page myself when I get there?
2. OK to spend the first real build session on step 1–2 (data + scoring engine) before showing you anything else, given that's the foundation everything else depends on?
