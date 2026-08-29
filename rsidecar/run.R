#!/usr/bin/env Rscript
#
# rsidecar one-shot: run ffanalytics for the current NFL week and drop ONE
# JSON file of raw consensus stat projections into the shared data volume, then
# exit. It is NOT long-running (spec issue #8) — a host timer runs it weekly
# (see rsidecar/README.md).
#
# It deliberately does NOT score to RIP TIDE rules. Per docs/adr/0003 the
# validated Python scoring engine is the single source of truth for points; the
# backend re-scores this payload with RIP_TIDE_RULESET
# (deadparrots.consensus.normalize). This script's only job is to emit a clean,
# stably-keyed consensus stat line per player.
#
# Payload contract (payload_version 1) — keep in lockstep with
# deadparrots/consensus/normalize.py::_FFANALYTICS_STAT_MAP and
# deadparrots/consensus/sources.py::RSIDECAR_PAYLOAD_VERSION:
#
#   {
#     "source": "ffanalytics",
#     "payload_version": 1,
#     "season": <int>, "week": <int>,
#     "generated_at": "<UTC ISO-8601>",
#     "players": [
#       { "name","team","position","gsis_id","source_points",
#         "stats": { "<canonical key>": <number>, ... } }
#     ]
#   }

suppressPackageStartupMessages({
  library(ffanalytics)
  library(jsonlite)
})

PAYLOAD_VERSION <- 1L

# local null-coalesce so we do not depend on rlang being on the search path
`%||%` <- function(a, b) if (is.null(a) || length(a) == 0 || all(is.na(a))) b else a

data_dir <- Sys.getenv("DEADPARROTS_DATA_DIR", unset = "/data")
out_dir <- file.path(data_dir, "consensus", "rsidecar")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

season <- as.integer(Sys.getenv("DEADPARROTS_CONSENSUS_SEASON",
                                unset = format(Sys.Date(), "%Y")))
week_env <- Sys.getenv("DEADPARROTS_CONSENSUS_WEEK", unset = "")
week <- if (nzchar(week_env)) as.integer(week_env) else ffanalytics:::current_week()

message(sprintf("rsidecar: ffanalytics scrape for season %d week %d", season, week))

scrape <- scrape_data(
  src = c("CBS", "ESPN", "FantasyPros", "NFL", "NumberFire"),
  pos = c("QB", "RB", "WR", "TE", "K", "DST", "DL", "LB", "DB"),
  season = season,
  week = week
)

# projections_table() aggregates the sources; we only read its stat columns, not
# its points (that is the engine's job).
proj <- projections_table(scrape)
proj <- add_player_info(proj)

# --- ffanalytics column -> canonical engine stat key ------------------------
# Left = a column projections_table() may emit; right = the key the Python
# normalizer's _FFANALYTICS_STAT_MAP expects. Unmapped columns are ignored.
STAT_COLS <- c(
  pass_yds = "pass_yds", pass_tds = "pass_tds", pass_int = "pass_int",
  pass_sacked = "sacks", two_pts = "two_pts",
  rush_yds = "rush_yds", rush_tds = "rush_tds",
  rec_yds = "rec_yds", rec_tds = "rec_tds",
  return_yds = "return_yds", fumbles_lost = "fumbles_lost",
  fg_0019 = "fg_0019", fg_2029 = "fg_2029", fg_3039 = "fg_3039",
  fg_4049 = "fg_4049", fg_50 = "fg_50", fg_miss = "fg_miss_0019",
  xp = "xp", xp_miss = "xp_miss",
  dst_sacks = "dst_sacks", dst_int = "dst_int", dst_fum_rec = "dst_fum_rec",
  dst_td = "dst_td", dst_ret_tds = "dst_ret_tds", dst_safety = "dst_safety",
  dst_blk = "dst_blk", dst_tackles_for_loss = "dst_tfl",
  dst_ret_yds = "dst_ret_yds", dst_pts_allowed = "dst_pts_allowed",
  idp_solo = "idp_solo", idp_asst = "idp_asst", idp_pd = "idp_pd",
  idp_sack = "idp_sack", idp_int = "idp_int", idp_fum_force = "idp_fum_force",
  idp_fum_rec = "idp_fum_rec", idp_td = "idp_td", idp_safety = "idp_safety",
  idp_blk = "idp_blk", idp_tfl = "idp_tfl", idp_int_return_yds = "idp_ret_yds"
)

num <- function(x) {
  v <- suppressWarnings(as.numeric(x))
  if (length(v) == 0 || is.na(v)) 0 else v
}

players <- lapply(seq_len(nrow(proj)), function(i) {
  row <- proj[i, ]
  stats <- list()
  for (src_col in names(STAT_COLS)) {
    if (src_col %in% names(row)) {
      val <- num(row[[src_col]])
      if (val != 0) stats[[STAT_COLS[[src_col]]]] <- val
    }
  }
  list(
    name = as.character(row$player %||% row$name %||% ""),
    team = as.character(row$team %||% NA),
    position = as.character(row$pos %||% row$position %||% ""),
    gsis_id = as.character(row$id %||% row$gsis_id %||% NA),
    source_points = if ("points" %in% names(row)) num(row$points) else NULL,
    stats = stats
  )
})

payload <- list(
  source = "ffanalytics",
  payload_version = PAYLOAD_VERSION,
  season = season,
  week = week,
  generated_at = format(as.POSIXlt(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ"),
  players = players
)

stamp <- format(as.POSIXlt(Sys.time(), tz = "UTC"), "%Y%m%dT%H%M%SZ")
out_path <- file.path(out_dir, paste0(stamp, ".json"))
write_json(payload, out_path, auto_unbox = TRUE, null = "null", digits = 4)
message(sprintf("rsidecar: wrote %d players -> %s", length(players), out_path))
