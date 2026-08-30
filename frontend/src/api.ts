// The frontend's view of the Dead Parrots API. Types mirror the backend's
// stable Pydantic response contracts (backend `api/schemas.py`, ADR-0013 §5):
// additive-only, so an unknown extra field is ignored, never a runtime error.
// All numeric and projection logic lives in the backend (ADR-0003) — this file
// only shuttles JSON.

const API_BASE = "/api";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

// --- health (scaffold; kept for the deployment smoke check) -------------

export interface HealthResponse {
  status: "ok" | "degraded";
  sqlite: "ok" | "error";
  duckdb: "ok" | "error";
  scheduler: "running" | "stopped";
  time: string;
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJSON<HealthResponse>("/health");
}

// --- This Week (GET /api/weekly) --------------------------------------

export type RecommendationEngine = "max-p-win" | "threshold-rule";

export interface LineupSlotProjection {
  player_id: string;
  name: string;
  position: string;
  slot: string;
  mean: number;
  floor: number;
  ceiling: number;
  low_confidence: boolean;
  reasons: string[];
  resolved: boolean;
}

export interface SideTotals {
  mean: number;
  floor: number;
  projection: number;
  ceiling: number;
  stdev: number;
  yahoo_projected_total: number | null;
}

export interface GapDriver {
  slot: string;
  dead_parrots_player: string;
  opponent_player: string;
  dead_parrots_mean: number;
  opponent_mean: number;
  contribution: number;
}

export interface SwingPlayer {
  player_id: string;
  name: string;
  position: string;
  variance_share: number;
  rank: number;
}

export interface NamedLineup {
  label: string;
  player_ids: string[];
  win_probability: number;
  expected_points: number;
  floor: number;
  ceiling: number;
}

export interface ThresholdRule {
  branch: string;
  situation_p_win: number;
  favored_threshold: number;
  underdog_threshold: number;
  player_ids: string[];
}

export interface WeeklyView {
  season: number;
  week: number;
  rng_seed: number;
  as_of_date: string;
  dead_parrots_team: string;
  opponent_team: string;
  opponent_assumption: string;
  opponent_notes: string[];
  opponent_likely_lineup: LineupSlotProjection[];
  dead_parrots_totals: SideTotals;
  dead_parrots_current_totals: SideTotals | null;
  dead_parrots_current_lineup: LineupSlotProjection[];
  opponent_totals: SideTotals;
  favored: boolean;
  win_probability: number;
  current_win_probability: number | null;
  recommended_lineup_is_current: boolean;
  mean_margin: number;
  gap_drivers: GapDriver[];
  swing_players: SwingPlayer[];
  recommended_lineup: LineupSlotProjection[];
  recommendation_engine: RecommendationEngine;
  named_lineups: NamedLineup[];
  threshold_rule: ThresholdRule;
  caveats: string[];
}

export function fetchWeeklyView(
  engine?: RecommendationEngine,
): Promise<WeeklyView> {
  const q = engine ? `?engine=${encodeURIComponent(engine)}` : "";
  return getJSON<WeeklyView>(`/weekly${q}`);
}

// --- Lineup Lab (POST /api/weekly/lineup-lab, GET .../auto) ----------

export interface LineupLabResult {
  starter_ids: string[];
  legal: boolean;
  reason: string | null;
  total: number;
  floor: number;
  ceiling: number;
  win_probability: number;
  caveats: string[];
}

export interface AutoFill {
  floor: string[];
  ceiling: string[];
  max_p_win: string[];
  max_ev: string[];
  roster: LineupSlotProjection[];
  caveats: string[];
}

export function computeLineupLab(
  starterIds: string[],
  irIds: string[] = [],
): Promise<LineupLabResult> {
  return postJSON<LineupLabResult>("/weekly/lineup-lab", {
    starter_ids: starterIds,
    ir_ids: irIds,
  });
}

export function fetchAutoFill(): Promise<AutoFill> {
  return getJSON<AutoFill>("/weekly/lineup-lab/auto");
}

// --- news ticker (GET /api/news) ------------------------------------

export interface NewsTag {
  player_name: string;
  bucket: string;
  matched_text: string;
}

export interface NewsItem {
  title: string;
  url: string;
  summary: string | null;
  source: string;
  published_at: string;
  buckets: string[];
  tags: NewsTag[];
}

export interface NewsResponse {
  fetched_at: string;
  window_hours: number;
  all_sources_failed: boolean;
  items: NewsItem[];
}

export function fetchNews(): Promise<NewsResponse> {
  return getJSON<NewsResponse>("/news");
}

// --- data-freshness header (GET /api/freshness) ---------------------

export type FreshnessState = "ok" | "failed" | "never";

export interface SourceFreshness {
  source: string;
  last_success: string | null;
  age_seconds: number | null;
  state: FreshnessState;
  detail: string | null;
}

export interface FreshnessResponse {
  sources: SourceFreshness[];
  yahoo_reminder: string | null;
  yahoo_stale_pages: string[];
  waiver_priority_needs_manual_entry: boolean | null;
}

export function fetchFreshness(): Promise<FreshnessResponse> {
  return getJSON<FreshnessResponse>("/freshness");
}

// --- Waiver / Free Agents (GET /api/free-agents) -------------------

export interface FreeAgent {
  player_id: string;
  name: string;
  position: string;
  ros_projected_points: number;
  value_over_replacement: number;
  positional_rank: number;
  need_fit: string;
  own_bye: string;
  priority_verdict: string;
  reasons: string[];
}

export interface Streamer {
  player_id: string;
  name: string;
  position: string;
  hole_role: string;
  next_week_ceiling: number;
  need_fit: string;
  priority_verdict: string;
  reasons: string[];
}

export interface WaiverPriority {
  current_priority: number;
  team_count: number;
  is_last: boolean;
  drops_to_on_claim: number;
  note: string;
}

export interface CutdownWindow {
  window_name: string;
  opens: string;
  closes: string;
  is_open: boolean;
  is_upcoming: boolean;
  days_until_open: number;
  note: string;
}

export interface FreeAgentsResponse {
  season: number;
  week: number;
  rest_of_season: FreeAgent[];
  streamers: Streamer[];
  hole_roles: string[];
  waiver_priority: WaiverPriority;
  cutdown_window: CutdownWindow;
  caveats: string[];
}

export function fetchFreeAgents(): Promise<FreeAgentsResponse> {
  return getJSON<FreeAgentsResponse>("/free-agents");
}

// --- Team Outlook (GET /api/team-outlook) -------------------------

export interface TeamStrength {
  decay_weighted_points_for: number;
  percentile: number;
  weeks_counted: number;
  rank: number;
}

export interface ExpectedWins {
  expected_wins: number;
  actual_wins: number;
  luck: number;
  weeks_counted: number;
}

export interface Signal {
  signal: string;
  week: number;
  signal_start_week: number;
  points_for_percentile: number;
  playoff_odds: number;
  contend_percentile_threshold: number;
  rebuild_percentile_threshold: number;
  rationale: string[];
  recommends_transaction: boolean;
}

export interface ByePosition {
  role: string;
  starters_on_bye: number;
  starter_names: string[];
}

export interface ByeCrunchWeek {
  week: number;
  grade: string;
  max_at_one_position: number;
  can_field_legal_lineup: boolean;
  per_position: ByePosition[];
  reasons: string[];
}

export interface TeamOutlookResponse {
  season: number;
  week: number;
  team_strength: TeamStrength;
  expected_wins: ExpectedWins;
  playoff_odds: number;
  signal: Signal;
  bye_crunch: ByeCrunchWeek[];
  caveats: string[];
}

export function fetchTeamOutlook(): Promise<TeamOutlookResponse> {
  return getJSON<TeamOutlookResponse>("/team-outlook");
}

// --- Trade Desk (GET /api/trade-desk) ----------------------------

export interface Opportunity {
  player_id: string;
  position: string;
  opportunity_index: number;
  opportunity_trend: number;
  output_index: number;
  output_trend: number;
  games_counted: number;
}

export interface TradeCandidate {
  player_id: string;
  name: string;
  position: string;
  side: string;
  market_rank: number;
  model_rank: number;
  trade_edge: number;
  priority: number;
  reasons: string[];
}

export interface DesperateTeam {
  team_id: string;
  team_name: string;
  score: number;
  rank: number;
  reasons: string[];
}

export interface Countdown {
  target_date: string;
  as_of: string;
  days_remaining: number;
  is_past: boolean;
}

export interface TradeDeskResponse {
  season: number;
  week: number;
  opportunity: Opportunity[];
  buy_low: TradeCandidate[];
  sell_high: TradeCandidate[];
  desperate_teams: DesperateTeam[];
  countdown: Countdown;
  caveats: string[];
}

export function fetchTradeDesk(): Promise<TradeDeskResponse> {
  return getJSON<TradeDeskResponse>("/trade-desk");
}

// --- History (GET /api/history) ---------------------------------

export interface PlayerActual {
  player_id: string;
  name: string;
  projected_points: number;
  actual_points: number;
  delta: number;
}

export interface SnapshotOutcome {
  backfilled_at: string;
  dead_parrots_total: number;
  opponent_total: number;
  result: string;
  player_actuals: PlayerActual[];
}

// The frozen JSON of the four screen contracts for the week (backend
// `build_captured_payload`, ADR-0014 §1). History only reads the `weekly` slice.
export interface HistoryCaptured {
  weekly: WeeklyView;
  team_outlook: TeamOutlookResponse;
  trade_desk: TradeDeskResponse;
  free_agents: FreeAgentsResponse;
}

export interface HistoryRecord {
  snapshot_id: string;
  season: number;
  week: number;
  created_at: string;
  rng_seed: number;
  captured: HistoryCaptured;
  outcome: SnapshotOutcome | null;
}

export interface HistoryResponse {
  pending: boolean;
  reason: string;
  snapshots: HistoryRecord[];
}

export function fetchHistory(): Promise<HistoryResponse> {
  return getJSON<HistoryResponse>("/history");
}
