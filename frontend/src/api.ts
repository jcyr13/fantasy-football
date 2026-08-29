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
