from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

# The stable response contracts the frontend (issues #18, #19) codes against
# (ADR-0013 §5). Additive-only from here: fields may be added, never removed or
# retyped, without a new ADR.


class LineupSlotProjection(BaseModel):
    player_id: str
    name: str
    position: str
    slot: str
    mean: float
    floor: float
    ceiling: float
    low_confidence: bool
    reasons: list[str]
    resolved: bool


class SideTotals(BaseModel):
    mean: float
    floor: float
    projection: float
    ceiling: float
    stdev: float
    yahoo_projected_total: float | None


class GapDriverOut(BaseModel):
    slot: str
    dead_parrots_player: str
    opponent_player: str
    dead_parrots_mean: float
    opponent_mean: float
    contribution: float


class SwingPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    variance_share: float
    rank: int


class NamedLineup(BaseModel):
    label: str
    player_ids: list[str]
    win_probability: float
    expected_points: float
    floor: float
    ceiling: float


class ThresholdRuleOut(BaseModel):
    branch: str
    situation_p_win: float
    favored_threshold: float
    underdog_threshold: float
    player_ids: list[str]


class WeeklyViewResponse(BaseModel):
    season: int
    week: int
    rng_seed: int
    as_of_date: date
    dead_parrots_team: str
    opponent_team: str
    opponent_assumption: str
    opponent_notes: list[str]
    opponent_likely_lineup: list[LineupSlotProjection]
    # `dead_parrots_totals` / `favored` / `win_probability` / `mean_margin` are
    # for the *recommended* lineup. `dead_parrots_current_totals` /
    # `current_win_probability` are the Yahoo-set lineup as it stands now (null
    # when it is not a legal 10); `recommended_lineup_is_current` is true when
    # the two are the same ten players.
    dead_parrots_totals: SideTotals
    dead_parrots_current_totals: SideTotals | None
    # The Dead Parrots lineup Yahoo currently has set, per-slot with projections
    # — frozen alongside the recommendation so a weekly snapshot (issue #17) can
    # score both "what the model said" and "what John actually started".
    dead_parrots_current_lineup: list[LineupSlotProjection]
    opponent_totals: SideTotals
    favored: bool
    win_probability: float
    current_win_probability: float | None
    recommended_lineup_is_current: bool
    mean_margin: float
    gap_drivers: list[GapDriverOut]
    swing_players: list[SwingPlayerOut]
    recommended_lineup: list[LineupSlotProjection]
    recommendation_engine: str
    named_lineups: list[NamedLineup]
    threshold_rule: ThresholdRuleOut
    caveats: list[str]


class LineupLabRequest(BaseModel):
    starter_ids: list[str]
    # Roster ids the scenario has on IR. A starter also listed here is an
    # illegal placement; bench ids need not be sent (they are the roster
    # remainder).
    ir_ids: list[str] = []


class LineupLabResponse(BaseModel):
    starter_ids: list[str]
    legal: bool
    reason: str | None
    total: float
    floor: float
    ceiling: float
    win_probability: float
    caveats: list[str]


class AutoFillResponse(BaseModel):
    floor: list[str]
    ceiling: list[str]
    max_p_win: list[str]
    max_ev: list[str]
    roster: list[LineupSlotProjection]
    caveats: list[str]


class FreeAgentOut(BaseModel):
    player_id: str
    name: str
    position: str
    ros_projected_points: float
    value_over_replacement: float
    positional_rank: int
    need_fit: str
    own_bye: str
    priority_verdict: str
    reasons: list[str]


class StreamerOut(BaseModel):
    player_id: str
    name: str
    position: str
    hole_role: str
    next_week_ceiling: float
    need_fit: str
    priority_verdict: str
    reasons: list[str]


class WaiverPriorityOut(BaseModel):
    current_priority: int
    team_count: int
    is_last: bool
    drops_to_on_claim: int
    note: str


class CutdownWindowOut(BaseModel):
    window_name: str
    opens: date
    closes: date
    is_open: bool
    is_upcoming: bool
    days_until_open: int
    note: str


class FreeAgentsResponse(BaseModel):
    season: int
    week: int
    rest_of_season: list[FreeAgentOut]
    streamers: list[StreamerOut]
    hole_roles: list[str]
    waiver_priority: WaiverPriorityOut
    cutdown_window: CutdownWindowOut
    caveats: list[str]


class TeamStrengthOut(BaseModel):
    decay_weighted_points_for: float
    percentile: float
    weeks_counted: int
    rank: int


class ExpectedWinsOut(BaseModel):
    expected_wins: float
    actual_wins: float
    luck: float
    weeks_counted: int


class SignalOut(BaseModel):
    signal: str
    week: int
    signal_start_week: int
    points_for_percentile: float
    playoff_odds: float
    contend_percentile_threshold: float
    rebuild_percentile_threshold: float
    rationale: list[str]
    recommends_transaction: bool


class ByePositionOut(BaseModel):
    role: str
    starters_on_bye: int
    starter_names: list[str]


class ByeCrunchWeekOut(BaseModel):
    week: int
    grade: str
    max_at_one_position: int
    can_field_legal_lineup: bool
    per_position: list[ByePositionOut]
    reasons: list[str]


class TeamOutlookResponse(BaseModel):
    season: int
    week: int
    team_strength: TeamStrengthOut
    expected_wins: ExpectedWinsOut
    playoff_odds: float
    signal: SignalOut
    bye_crunch: list[ByeCrunchWeekOut]
    caveats: list[str]


class OpportunityOut(BaseModel):
    player_id: str
    position: str
    opportunity_index: float
    opportunity_trend: float
    output_index: float
    output_trend: float
    games_counted: int


class TradeCandidateOut(BaseModel):
    player_id: str
    name: str
    position: str
    side: str
    market_rank: int
    model_rank: int
    trade_edge: int
    priority: float
    reasons: list[str]


class DesperateTeamOut(BaseModel):
    team_id: str
    team_name: str
    score: float
    rank: int
    reasons: list[str]


class CountdownOut(BaseModel):
    target_date: date
    as_of: date
    days_remaining: int
    is_past: bool


class TradeDeskResponse(BaseModel):
    season: int
    week: int
    opportunity: list[OpportunityOut]
    buy_low: list[TradeCandidateOut]
    sell_high: list[TradeCandidateOut]
    desperate_teams: list[DesperateTeamOut]
    countdown: CountdownOut
    caveats: list[str]


class NewsTagOut(BaseModel):
    player_name: str
    bucket: str
    matched_text: str


class NewsItemOut(BaseModel):
    title: str
    url: str
    summary: str | None
    source: str
    published_at: datetime
    buckets: list[str]
    tags: list[NewsTagOut]


class NewsResponse(BaseModel):
    fetched_at: datetime
    window_hours: int
    all_sources_failed: bool
    items: list[NewsItemOut]


class PlayerActualOut(BaseModel):
    player_id: str
    name: str
    projected_points: float
    actual_points: float
    delta: float


class SnapshotOutcomeOut(BaseModel):
    backfilled_at: datetime
    dead_parrots_total: float
    opponent_total: float
    result: str
    player_actuals: list[PlayerActualOut]


class HistoryRecordOut(BaseModel):
    snapshot_id: str
    season: int
    week: int
    created_at: datetime
    rng_seed: int
    # The frozen JSON of GET /api/weekly + /api/team-outlook + /api/trade-desk +
    # /api/free-agents for the week, keyed weekly / team_outlook / trade_desk /
    # free_agents (ADR-0014 §1).
    captured: dict
    outcome: SnapshotOutcomeOut | None


class OutcomeBackfillRequest(BaseModel):
    dead_parrots_total: float
    opponent_total: float
    # Dead Parrots player_id -> RIP TIDE points he actually scored. Players in
    # the frozen recommended lineup that are omitted here score 0.0.
    player_actuals: dict[str, float] = {}


class HistoryResponse(BaseModel):
    # ``pending`` was ``true`` with an empty list until issue #17 (ADR-0014 §5);
    # it is now always ``false`` and ``snapshots`` carries the real records.
    pending: bool
    reason: str
    snapshots: list[HistoryRecordOut]


class CaptureResponse(BaseModel):
    # ``created`` is false when the week already had a snapshot — the original
    # is returned unchanged.
    created: bool
    record: HistoryRecordOut


class SourceFreshnessOut(BaseModel):
    source: str
    last_success: datetime | None
    age_seconds: float | None
    state: str
    detail: str | None = None


class FreshnessResponse(BaseModel):
    sources: list[SourceFreshnessOut]
    yahoo_reminder: str | None
    yahoo_stale_pages: list[str]
    waiver_priority_needs_manual_entry: bool | None


class RefreshOutcomeOut(BaseModel):
    source: str
    ok: bool
    detail: str


class RefreshResponse(BaseModel):
    outcomes: list[RefreshOutcomeOut]
