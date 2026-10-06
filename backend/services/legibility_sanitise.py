"""ONE deny-by-default sanitiser for every C19 legibility payload (review F1/F8, 2026-10-07).

Every payload leaves the router through `sanitise(payload, SPEC[kind])`:

* **Keys are allow-listed per payload type.** A key not in the spec is DROPPED, at every
  depth. A new field a writer adds never reaches a browser until someone lists it here.
* **Leaves are scalars or lists of scalars.** A dict or a list of dicts where the spec
  expects a leaf is dropped (it would carry fields nobody reviewed).
* **Free-keyed maps** (`MapOf`) are allowed only where the keys are names (families,
  states, horizons); their values are still spec-checked.
* **A deny-set of key names is removed everywhere**, even inside a `MapOf`: dollar equity,
  cash, start capital, P&L, account numbers, buying power, credentials. Returns and
  percentages are served; dollars never are.
* **Every string (and every map key) is scrubbed**: URLs keep their path and lose their
  host; absolute paths become repo-relative; process ids, command lines and local ports
  go; credential env-var names go; broker-style account ids go; the names and page counts
  of a paywalled publisher's reader go.
"""
from __future__ import annotations

import re
from typing import Any

# ───────────────────────────────────────────────────────────── spec language

LEAF = "leaf"


class ListOf:
    def __init__(self, spec: Any):
        self.spec = spec


class MapOf:
    def __init__(self, spec: Any):
        self.spec = spec


DENY_KEYS = frozenset({
    "equity", "cash", "last_equity", "start_capital", "sum_equity", "sum_start_capital", "pnl",
    "account_number", "buying_power", "portfolio_value", "market_value", "unrealized_pl",
    "api_key", "secret", "secret_key", "password", "token", "key_id",
})
_DENY_KEY_RE = re.compile(r"(?i)(secret|password|passwd|api_?key|token|credential)")

# ───────────────────────────────────────────────────────────── value scrubbing

_URL = re.compile(r"\bhttps?://[^\s'\"<>|)\]]+")
_ENV_NOTE = re.compile(r"\s*\([^()]*\.env[^()]*\)")
_ABS_WIN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s'\"<>|,;)\]]*")
_ABS_NIX = re.compile(r"(?<![\w.:/])/(?:home|Users|root|mnt|tmp|var|opt|srv)/[^\s'\"<>|,;)\]]*")
_PID_CMD = re.compile(r"\bpid \d+ cmdline contains (\S+)")
_PID = re.compile(r"\b(p?pid)[ =:]*\d+")
_LOCAL_HOST = re.compile(r"\b(?:127\.0\.0\.1|0\.0\.0\.0|localhost|\[::1\])(?::\d{2,5})?")
_PORT = re.compile(r"(?i)\bport[ =:]*\d{2,5}\b")
_ENV_GLOB = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_\*")
_SNAKE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_CRED_PARTS = frozenset({"KEY", "KEYS", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "CREDENTIALS",
                         "AUTH", "APCA", "ALPACA"})


def _cred_env(m: re.Match) -> str:
    """An UPPER_SNAKE name with a credential component is an env-var name: replaced."""
    return "[credential env var]" if set(m.group(0).split("_")) & _CRED_PARTS else m.group(0)
_ACCOUNT_ID = re.compile(r"\bPA[0-9A-Z]{8,}\b")
_PUBLISHER = re.compile(r"(?i)(?:dow ?jones|\bwsj\b|barron'?s|marketwatch|factiva)")
_BARE_PORT = re.compile(r"(?<![\w:]):\d{2,5}(?=/|\b)")
_PAGE_COUNT = re.compile(r"(?i)\b\d[\d,]*\s+(?:new\s+)?page[ -]?loads?\b(?:\s+total)?")


def _path_tail(raw: str) -> str:
    norm = raw.replace("\\\\", "\\").replace("\\", "/")
    for anchor in ("/backend/", "/docs/", "/scripts/", "/frontend/", "/nn_lab/", "/ft_lab/"):
        i = norm.find(anchor)
        if i >= 0:
            return norm[i + 1:]
    return norm.rsplit("/", 1)[-1]


def _url_path(m: re.Match) -> str:
    u = m.group(0)
    rest = u.split("://", 1)[1]
    host, _, path = rest.partition("/")
    if host.split(":")[0] in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]"):
        return "local /" + path if path else "local"
    return "/" + path if path else "(url)"


def scrub_str(s: str) -> str:
    s = _ENV_NOTE.sub("", s)
    s = _URL.sub(_url_path, s)
    s = _ABS_WIN.sub(lambda m: _path_tail(m.group(0)), s)
    s = _ABS_NIX.sub(lambda m: _path_tail(m.group(0)), s)
    s = _PID_CMD.sub(lambda m: f"a live process answers as {m.group(1)}", s)
    s = _PID.sub(lambda m: f"{m.group(1)} [n]", s)
    s = _LOCAL_HOST.sub("local", s)
    s = _PORT.sub("port [n]", s)
    s = _BARE_PORT.sub("", s)
    s = _ENV_GLOB.sub("[env var]", s)
    s = _SNAKE.sub(_cred_env, s)
    s = _ACCOUNT_ID.sub("[account]", s)
    s = _PAGE_COUNT.sub("page loads", s)
    s = _PUBLISHER.sub("publisher", s)
    return s


def _scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _leaf(v: Any) -> Any:
    if isinstance(v, str):
        return scrub_str(v)
    if _scalar(v):
        return v
    if isinstance(v, (list, tuple)) and all(_scalar(x) for x in v):
        return [scrub_str(x) if isinstance(x, str) else x for x in v]
    return None                       # a structure where a leaf was declared: dropped


def _denied(k: str) -> bool:
    return k in DENY_KEYS or bool(_DENY_KEY_RE.search(k))


def sanitise(v: Any, spec: Any) -> Any:
    """Return only what `spec` allows, scrubbed."""
    if spec == LEAF:
        return _leaf(v)
    if isinstance(spec, ListOf):
        if not isinstance(v, list):
            return None if v is None else []
        return [sanitise(x, spec.spec) for x in v]
    if isinstance(spec, MapOf):
        if not isinstance(v, dict):
            return None
        return {scrub_str(str(k)): sanitise(x, spec.spec) for k, x in v.items() if not _denied(str(k))}
    if isinstance(spec, dict):
        if not isinstance(v, dict):
            return None
        return {k: sanitise(v.get(k), s) for k, s in spec.items() if k in v and not _denied(k)}
    raise TypeError(f"bad spec {spec!r}")


def keys(*names: str) -> dict:
    return {n: LEAF for n in names}


# ───────────────────────────────────────────────────────────── the allow-lists

RECEIPT = keys("kind", "file", "stamp_utc", "age_hours", "stale_after_hours", "status", "line",
               "missing_because", "sha256", "role", "note")
BASE = {**keys("schema", "page", "served_utc", "status"), "receipts": ListOf(RECEIPT),
        "missing_because": MapOf(LEAF)}

BOOK = {**keys("account", "family", "category", "twin_kind", "twin_of", "strategy", "book_id", "status",
               "mark_status", "mark_age_days", "inception", "last_mark", "sessions_graded", "return_pct",
               "spy_same_window_pct", "vs_spy_pp", "spy_base", "evidence_label", "evidence_rung", "evidence_n",
               "evidence_why", "n_holdings", "holdings_source", "beta_vs_spy", "beta_n_obs", "cash_fraction",
               "one_name_why", "subwindows_status", "subwindows_n_positive", "manager_last_run", "note",
               "source", "error_type", "error_why"),
        "holdings": ListOf(keys("ticker", "weight")),
        "subwindows": ListOf(keys("from", "to", "excess_pp")),
        "decomposition": MapOf(LEAF),
        "missing_because": MapOf(LEAF)}

ARENA = {**BASE,
         "evidence_ladder": LEAF,
         "top": keys("top_line", "collapse_line", "evidence_density_line", "honest_sentence", "read_me_first",
                     "book_dna_read_me_first", "label_ceiling", "licence"),
         "numbers": {**keys("n_rows", "n_ahead_raw", "n_behind_spy", "n_ahead_twins", "n_ahead_controls",
                            "n_ahead_strategy", "n_holdings_clusters_ahead", "effective_bets_exante",
                            "effective_bets_exante_spy_residual", "exante_window", "exante_n_books",
                            "collapse_factor_twins_controls", "collapse_factor_holdings_overlap",
                            "collapse_factor_exante", "n_ahead_dense", "jaccard_threshold", "exante_construction",
                            "exante_top_eigen_share_raw", "exante_median_pairwise_corr_raw", "min_sessions_to_rank",
                            "n_strategy_ge_min_sessions", "n_owner_personal_dropped"),
                     "cluster_count_sensitivity": MapOf(LEAF),
                     "most_frequent_names": ListOf(keys("ticker", "n_books", "of")),
                     "tilt": keys("ticker", "n_books", "of", "median_exante_beta_of_its_books", "sector"),
                     "status_counts": MapOf(LEAF), "mark_status_counts": MapOf(LEAF)},
         "by_family": MapOf(keys("n", "n_priced", "roi_pct")),
         "broker_read": {**keys("performed", "n_accounts", "n_priced", "read_utc"), "errors": MapOf(LEAF)},
         "receipt_choice": keys("served", "served_is_nobroker", "line", "newest_broker_file", "newest_broker_age_hours"),
         "clusters": ListOf(keys("cluster_id", "n", "members", "families", "shared_basket", "excess_pp_mean",
                                 "excess_pp_median", "excess_pp_total", "tied_for_largest")),
         "winners": ListOf(BOOK), "short_lived": ListOf(BOOK), "losers": ListOf(BOOK), "books": ListOf(BOOK),
         "filters": {"families": MapOf(LEAF), "labels": MapOf(LEAF), "categories": MapOf(LEAF)},
         "links": MapOf(LEAF)}

STORIES = {**BASE, **keys("month", "n_decisions", "scope"),
           "stories": ListOf({**keys("decision_id", "session", "asof", "ticker", "action", "state", "cohort",
                                     "acting", "abstention", "target_weight", "held_weight", "plan_full_weight",
                                     "selector_rank", "reason", "refused", "policy_version", "mode",
                                     "replay_matches_actual", "order_or_abstention_id", "order_link", "built_utc"),
                              "alternatives": ListOf(keys("alt", "target_weight", "status", "why"))}),
           "regret": {**keys("run_id", "asof", "line", "status", "missing_because"),
                      "h5_table": ListOf(keys("cohort", "mean_names", "book_scaled_gross",
                                              "mean_net_excess_vs_spy_bps", "vs_band_control_bps", "t_vs_spy",
                                              "n_date_blocks", "mde_bps"))}}

CALIB_BIN = keys("arm_prefix", "horizon", "observable", "bin", "n", "p_mean", "p_lo", "p_hi", "base_rate",
                 "wilson_lo", "wilson_hi", "n_dates", "n_date_blocks", "thin", "blocks_missing_because")
FORECAST = {**BASE,
            "house_finding": {**keys("claim", "reading"),
                              "evidence": ListOf(keys("what", "value", "unit", "baseline", "n", "receipt",
                                                      "sanity_check"))},
            "calibration": MapOf(ListOf(CALIB_BIN)),
            "calibration_note": LEAF,
            "skill": {**keys("split", "baseline", "n_graded", "n_ledger", "made_at_range"),
                      "by_kind_horizon": ListOf(keys("kind", "horizon_days", "n_arms", "n_arms_scored",
                                                     "n_arms_positive", "n_rows_heldout", "best_arm", "best_skill",
                                                     "worst_arm", "worst_skill")),
                      "arms_by_observable": ListOf(keys("arm", "observable", "horizon_days", "kind", "n",
                                                        "n_total", "skill", "disc")),
                      "arms": ListOf(keys("arm", "family", "n", "n_total", "brier", "clim", "skill", "disc",
                                          "calib_gap", "weight")),
                      "tuned": MapOf(LEAF)},
            "sigma_prior": ListOf(keys("horizon", "observable", "formula", "split", "baseline", "status", "n_rows",
                                       "n_heldout", "heldout_from", "heldout_to", "climatology_base_rate",
                                       "skill_llm", "skill_prior", "skill_llm_own_prior", "winner",
                                       "days_prior_wins", "n_days")),
            "closing": keys("works", "does_not", "next_experiment"),
            "grades": {**keys("headline", "date", "n_records", "graded_after_this_run", "newly_resolved",
                              "health_status", "problems", "n_overdue", "distinct_specialists"),
                       "totals": MapOf(LEAF)},
            "trust": {**keys("rule", "min_graded_dates"),
                      "news": ListOf(keys("arm", "control", "n_dates", "n_rows", "mean_improvement", "se",
                                          "posterior_mean", "trust", "below_min_dates")),
                      "nn_lab": ListOf(keys("arm", "horizon", "graded_dates", "trust", "source",
                                            "walk_forward_mean_ic_reported"))},
            "regime": {**keys("note", "n_fields", "trust", "pooled_note", "baselines", "news_tilt_line"),
                       "vs_persistence": MapOf(LEAF), "vs_base_rate": MapOf(LEAF),
                       "fields": MapOf(MapOf(LEAF)), "regime_write": MapOf(LEAF)},
            "tournament": {**keys("rule", "nightly_table_receipt", "nightly_table_written_utc", "nightly_table_note",
                                  "survivorship_caveat", "per_model", "status", "earned_forward_weight", "sentence",
                                  "cited_run", "cited_missing_because"),
                           "nightly_table": MapOf(MapOf(MapOf(LEAF))),
                           "cited_models": ListOf(keys("model", "horizon", "rank_ic", "rank_ic_t", "rank_ic_loyo_worst",
                                                       "top20_minus_random_net", "top20_t", "n_blocks", "verdict",
                                                       "brier_skill")),
                           "cited_magnitude": ListOf(keys("horizon", "predictor", "ic_with_abs_y", "t", "n_blocks"))},
            "review_rerun": {**keys("run_id", "label"),
                             "models": ListOf(keys("model", "horizon", "rank_ic", "rank_ic_t", "rank_ic_loyo_worst",
                                                   "top20_minus_random_net", "top20_t", "n_blocks", "verdict",
                                                   "brier_skill"))},
            "analyst_reputation": {**keys("asof", "month", "limits", "n_firms", "n_sectors"),
                                   "pit": MapOf(LEAF), "constants": MapOf(LEAF),
                                   "top_firms_by_claims": ListOf(keys("firm", "n_claims", "weight_mean", "raw_edge"))}}

THEORY_ROW = keys("hyp_id", "title", "family", "family_raw", "target", "status", "verdict", "powered", "state",
                  "state_rule", "confirm_mean", "confirm_t", "confirm_mde", "reason", "reread_of",
                  "declaration_sha256", "run_id", "receipts", "created_utc", "refutation", "mechanism", "precursor")
TWIN_ROW = {**keys("rule", "family", "status", "reason", "turnover", "rule_cost_bps", "twin_cost_bps",
                   "sticky_turnover_ok", "source_run", "superseded_in", "superseded_why"),
            "columns": MapOf(MapOf(keys("mean_monthly", "t", "mde_monthly")))}
BOARD = {**keys("twin_kind", "run_id", "summary_file", "rows_file", "cost_convention", "four_columns",
                "upper_bound_note", "other_boards_not_served", "rows_served", "n_rows"),
         "summary": MapOf(LEAF), "windows": MapOf(LEAF), "sticky_declaration": MapOf(LEAF),
         "supersessions_applied": ListOf(keys("supplement_run", "rules", "why", "file")),
         "rows": ListOf(TWIN_ROW)}
THEORY = {**BASE, **keys("states", "powered_rule", "n_negative", "n_uninformative", "family_prior", "board_served"),
          "state_counts": MapOf(LEAF),
          "state_map": ListOf(keys("input", "state")),
          "theories": ListOf(THEORY_ROW),
          "families": ListOf(keys("family", "n_rows", "CONDITIONAL_POSITIVE", "FAILED_VARIANT", "CANNOT_DISTINGUISH",
                                  "REFUSED", "failed_powered", "positive_weighted", "rereads", "p_positive",
                                  "budget_weight")),
          "theory_cells": ListOf({**keys("cell", "run", "hyp_id", "family", "title", "declaration_file",
                                         "declaration_sha256", "declared_utc", "honesty", "refutation", "primary",
                                         "results_file", "result_utc", "result_declaration_sha256", "verdict",
                                         "reason", "powered"),
                                  "splits": MapOf(LEAF), "primary_stats": MapOf(MapOf(LEAF))}),
          "boards": {"sticky": BOARD, "basket": BOARD},
          "crsp": {**keys("sentence", "source", "missing_because"),
                   "counts_from_board": MapOf(LEAF)},
          "links": MapOf(LEAF)}

HEALTH_ROW = keys("name", "probe", "where", "verdict", "state", "cadence_s", "evidence", "evidence_utc",
                  "age_s_at_probe", "age_s_now", "detail", "proof", "same_output", "missing_because")
HEALTH = {**BASE, **keys("generated_utc", "health_line", "exit_code", "read_me_first", "source", "same_output_rule"),
          "counts": MapOf(LEAF), "state_counts": MapOf(LEAF),
          "groups": ListOf({**keys("verdict", "n"), "states": MapOf(LEAF), "rows": ListOf(HEALTH_ROW)}),
          "process_census": ListOf(HEALTH_ROW), "same_output_rows": ListOf(HEALTH_ROW),
          "task_owners": ListOf(keys("task", "receipt", "cadence_h", "session_only", "retired", "registered_only",
                                     "hash_rule_off", "state", "verdict", "detail", "missing_because"))}

SPEC = {"arena": ARENA, "arena_stories": STORIES, "forecast_lab": FORECAST, "theory_lab": THEORY,
        "system_health": HEALTH}

__all__ = ["DENY_KEYS", "LEAF", "ListOf", "MapOf", "SPEC", "sanitise", "scrub_str"]
