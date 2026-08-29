# Waiver / Free Agents layer: rank-vs-next-best replacement level, a qualitative priority verdict, and a date-driven cutdown window

Issue #14 asks for a pure function over an assembled weekly league state
producing two ranked free-agent lists — **rest-of-season value over
replacement** (methodology §4.10) and **this-week streamers** by next-week
ceiling scoped to a current hole (§4.11) — each entry annotated with a
**bench-need fit**, the player's **own upcoming bye**, and a
**worth-the-priority verdict** (§4.12), plus the current **waiver-priority**
slot and a flag for the **post-roster-cutdown / practice-squad-churn** window.
`docs/methodology.md` §4.10–§4.12 defines the three formulas; the §5 parameter
table stops at the Trade Desk (rows 11–12) and puts no row on the free-agent
lists, so every numeric knob here is a build choice this ADR records.
Vocabulary is CONTEXT.md's ("Projection", "Bye-week crunch").

## Decision

**1. The layer is pure over an assembled `WaiverState`, a sibling input shape.**
The free-agent universe carries a resolved rest-of-season projected-points
number and a resolved next-week ceiling (P90) per player — the projection model
produces both upstream, exactly as `project` consumes a resolved
`consensus_points` rather than the feed (methodology §2). The Dead Parrots
roster carries NFL bye / starter flag / season availability for the bench-need
and hole computation, and the state carries the current waiver-priority slot and
the snapshot date. No I/O, no nflverse column names, no import of the projection
package. Like `TradeDeskState` (ADR-0010) and `LeagueState` (ADR-0009) this is a
deliberate sibling of the other layers' inputs — issue #14 ships independently
of #16, which reconciles the shapes behind the API.

**2. Replacement level is the best _other_ free agent at the role, not a fixed
per-position baseline.** Methodology §4.10 defines the replacement as "the best
player at that position currently on waivers". Read literally that is a single
per-position number and the best available player scores exactly 0, tying with
one such zero per position at the top of the list — a degenerate ranking. Read
here as *the best alternative Dead Parrots could take instead*: the best
available player is measured against the runner-up at the role, everyone else
against the best. `value_over_replacement = ros_projected_points −
replacement.points` is then a genuine "how much do I gain over the next-best
free option", it is strictly ordered, and only a true position-leader shows a
positive number — which is also what §4.12's "size of the value-over-replacement
gain" needs to mean something. A role with a single free agent has no
alternative: replacement is that player's own number and the value over
replacement is 0. The list is sorted by descending value over replacement, then
descending projected points, then `player_id`; `positional_rank` is the order
within the role.

**3. The streamer list reuses the annotations and is scoped by an actual
hole.** "Positions with a current bye/injury hole" (§4.11) is derived: a role
has a hole in `current_week` when its healthy rostered count (available, not on
bye that week) is below the number of **non-flex** starting slots that must be
that role (QB 1, RB 2, WR 2, TE 1, K 1, DEF 1, IDP 1 under `RIP_TIDE_SLOTS`).
The flex is excluded from the need count — a role is thin when its own fixed
slots are uncovered, and the flex only makes that worse. K / DEF / IDP dominate
in practice because those slots are rostered one deep. `WaiverState.hole_roles`
can override the derived set (issue #16 may compute it from the full assembled
lineup). The streamer list is those free agents whose role is in the hole set,
sorted by descending next-week ceiling, then descending projected points, then
`player_id`. Each streamer carries the same `BenchNeedFit` / `OwnByeNote` /
`WaiverPriorityVerdict` the rest-of-season entries carry, reusing the numbers
already computed for that list.

**4. The bench-need fit blends roster depth with the §4.4 bye-crunch logic.**
Per role: `depth` is `hole` (a slot uncovered this week) / `thin` (healthy
rostered depth only just covers the fixed slots) / `adequate` (one spare) /
`deep` (two or more spare), and `bye_crunch_weeks` is every upcoming week with
at least `bye_crunch_warn_count` (2, mirroring methodology §5 row 10) available
*starters* at the role on bye. This is the "roster construction plus the
bye-crunch map" of §4.10 as one small per-role read; it deliberately does not
run the Team Outlook layer's full legal-lineup check — the free-agent lists ask
"is there a need at this role", not "can a legal lineup be fielded".

**5. The worth-the-priority verdict is a three-way qualitative flag.**
§4.12: no FAAB, a successful claim drops Dead Parrots to last, and the flag is
"driven by the size of the value-over-replacement gain and the team's current
queue position". The rule:

| verdict | condition |
| --- | --- |
| `hold-priority` | no gain (`vor ≤ 0`); **or** `vor < marginal_upgrade_points` while priority ≤ `protect_priority_rank` |
| `worth-it` | already last (a claim costs no slot); **or** `vor ≥ big_upgrade_points` |
| `marginal` | anything between the two bars, or a sub-marginal gain from an already-unprotected slot |

Defaults: `big_upgrade_points` 20.0, `marginal_upgrade_points` 8.0,
`protect_priority_rank` 6 (the top half of a 12-team queue). All three are
build magnitudes in `WaiverParams`, pinned by behaviour tests, tunable without a
code change — the same treatment ADR-0010 gives the Trade Desk's trend slopes.
The current queue slot is surfaced once on the layer as
`WaiverPriorityStanding`.

**6. The post-cutdown window is a whole-day date range off the last Tuesday of
August.** The NFL 53-man roster-cutdown deadline has sat on the last Tuesday of
August every recent season; `WaiverParams.roster_cutdown_date` overrides it when
a season differs. The churn window runs from that day through
`cutdown_window_days` (2 — the "24–48h" of the ticket) after it, extending past
the cutdown day itself because practice squads form the next day. `is_open` is
true when the snapshot date is in `[opens, closes]`; `is_upcoming` is true when
`opens` is within `cutdown_window_lookahead_days` (7) ahead. The flag is a
plain date computation — there is no game-week trigger and no per-player data in
it.

## Why

- **Rank-vs-next-best replacement** is the reading that makes both the ordering
  (acceptance criterion 1) and the §4.12 "gain" non-degenerate. The literal
  single-baseline reading is recoverable by a caller that wants it — pass a
  free-agent universe with one entry per position — but it is not the useful
  default.
- **Fixed-slot need count, flex excluded**, keeps hole detection honest: the
  W/R/T flex can always be filled from a surplus at another role, so counting it
  toward a role's need would hide real holes.
- **A qualitative verdict, not a number**, is what §4.12 asks for
  ("a qualitative flag"). Turning "worth a waiver claim" into a false-precision
  score would over-state what a 12-team reverse-standings queue with no FAAB can
  tell you.
- **Date-only cutdown window.** The ticket wants the 24–48h post-cutdown /
  practice-squad-churn period flagged "for the relevant dates" — it is a
  calendar fact, independent of the projection model or the roster.

## Consequences

- Pure functions, no I/O, no numpy. Reuses `deadparrots.lineup` (`role_of`, the
  RIP TIDE slot rules) so "role" and "starting slot" mean one thing across the
  app.
- `WaiverState` duplicates roster / bye fields that also live on `LeagueState`
  and `TradeDeskState`. Deliberate for an independently-shippable ticket; issue
  #16 is the explicit merge point.
- Every knob except `bye_crunch_warn_count` (which tracks methodology §5 row 10)
  is a placeholder magnitude pinned by `test_waiver_params.py`; a tuning pass
  changes the defaults there without touching the layer.
- The rest-of-season number and the next-week ceiling are trusted inputs — a
  thin or optimistic projection universe yields a thin or optimistic list, the
  same dependency `project`'s callers already carry.

## Considered alternatives

- **Literal §4.10 replacement (best available as a single per-position
  baseline).** Rejected as the default: the position-leader scores 0 and the
  list degenerates to raw points within a position; "value over replacement
  gain" (§4.12) loses its meaning. Still reachable by a one-per-position
  universe.
- **A numeric worth-the-priority score.** Rejected: §4.12 says "qualitative
  flag"; a score implies a calibration the league's no-FAAB queue does not
  support.
- **Running the Team Outlook layer's `bye_crunch_map` / `can_field_legal_lineup`
  for the bench-need fit.** Rejected: that answers "is a legal lineup
  fieldable", a stricter and different question than "does this role need
  depth". The per-role warn-count check is the right granularity for a
  free-agent annotation, and it avoids a dependency on `LeagueState`.
- **A game-week trigger for the cutdown window** (e.g. "Week 1 ± n days").
  Rejected: cutdown is a fixed calendar date each year and the ticket asks for
  "the relevant dates", so a date range keyed off the last Tuesday of August is
  both simpler and correct.
- **Sharing `LeagueState` / `TradeDeskState`.** Rejected for the same reason
  ADR-0010 rejected it: independent tickets, reconciled by #16.
