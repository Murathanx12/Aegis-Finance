"""CH-47 — the insider copy book, tested as the owner states it (historical backtest).

    python -m scripts.insider_copy_backtest declare --out <dir>   # BEFORE any return is read
    python -m scripts.insider_copy_backtest run     --out <dir>   # refuses without the declaration

Licence ``PRODUCT_EXPERIMENT``. $0, no LLM, no network. Reads the live data
folder (Form 4 events, CRSP daily, delistings, FF daily market) and writes ONLY
into ``--out``; the file counts of every live folder read are printed before
and after. ``TRIAL-INSIDER-IC`` / ``TRIAL-CMP-INSIDER-IC`` are forward trials:
their files are not opened.

The owner (2026-11-14): "some of the insiders made 300% ... copying their
portfolio after the SEC filings you could have made at least double the S&P".
The question asked here is the ex-ante one: at each filing date, rank the
filing insider by his record KNOWN THEN (prior code-P purchases whose outcome
window had closed strictly before the filing date), copy the filing from the
first session after the filing date, hold 21 / 63 / 126 sessions, and compare
with (a) the market (SPY is not in the CRSP pull; the CRSP value-weighted
market from the FF daily file stands in), (b) insiders with poor records then,
(c) every purchase unranked, (d) five random same-date, same-size-decile names.
Costs on (``INSIDER_COPY_COST_BANDS``), delistings folded in (CRSP delisting
return; Shumway -30% on a missing performance delisting; cash afterwards).
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as CFG  # noqa: E402
from backend.services import insider_copy as IC  # noqa: E402

OPT = CFG.OPTIMUS_LEDGER_DIR
EVENTS = OPT / "sec_insider" / "insider_events_v1.parquet"
WRDS = OPT / "wrds"
DELIST = WRDS / "bulk" / "crsp__dsedelist.parquet"
FF = WRDS / "ff_factors_daily.parquet"
LIVE_DIRS = (OPT / "sec_insider", WRDS, WRDS / "bulk")
DECL_NAME = "insider_copy_DECLARATION.json"
RECEIPT_NAME = "insider_copy_receipt.json"

#: The variants, declared before the run. V1 is the primary; the others are
#: counted and reported, never chosen among after the fact.
VARIANTS: dict[str, dict] = {
    "V1_primary": {"entry": "next_open", "roles": "all", "min_prior": CFG.INSIDER_COPY_MIN_PRIOR,
                   "score": "shrunk_mean", "record_h": "same"},
    "V2_next_close": {"entry": "next_close", "roles": "all", "min_prior": CFG.INSIDER_COPY_MIN_PRIOR,
                      "score": "shrunk_mean", "record_h": "same"},
    "V3_officer_director_only": {"entry": "next_open", "roles": "officer_or_director",
                                 "min_prior": CFG.INSIDER_COPY_MIN_PRIOR, "score": "shrunk_mean",
                                 "record_h": "same"},
    "V4_min_prior_5": {"entry": "next_open", "roles": "all", "min_prior": 5, "score": "shrunk_mean",
                       "record_h": "same"},
    "V5_hit_rate": {"entry": "next_open", "roles": "all", "min_prior": CFG.INSIDER_COPY_MIN_PRIOR,
                    "score": "hit_rate", "record_h": "same"},
    "V6_record_on_21": {"entry": "next_open", "roles": "all", "min_prior": CFG.INSIDER_COPY_MIN_PRIOR,
                        "score": "shrunk_mean", "record_h": 21},
}

T_BAR = 2.0


def say(msg: str) -> None:
    print(msg, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _write(p: Path, body: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=1, default=_json_default), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, p)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return str(o)
    return str(o)


def _clean(o):
    """NaN -> None recursively, so the receipt is valid JSON."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def count_live() -> dict[str, int]:
    return {str(d): sum(1 for _ in d.iterdir()) for d in LIVE_DIRS if d.exists()}


# ─────────────────────────── declare ─────────────────────────────────────


def declaration_body() -> dict:
    return {
        "schema": "ch47/insider_copy_declaration/1",
        "licence": "PRODUCT_EXPERIMENT (historical backtest; no claim, no book, no order)",
        "owner_claim": ("some of the insiders made 300% ... copying their portfolio after the SEC filings "
                        "you could have made at least double the S&P (2026-11-14)"),
        "written_before_any_return_was_read": True,
        "forward_trials_untouched": ["TRIAL-INSIDER-IC", "TRIAL-CMP-INSIDER-IC"],
        "universe": ("SEC Form 4 bulk, event_type insider_open_market_buy (code P, acquired, non-derivative, "
                     "not 10b5-1; plan flag UNKNOWN before 2023q2 is kept), linked to a CRSP permno, filing "
                     f"date {CFG.INSIDER_COPY_FIRST_FILING}..{CFG.INSIDER_COPY_LAST_FILING}; one copy trade "
                     "per (insider CIK, permno, filing date)"),
        "public_bound": ("FILING_DATE 22:00 America/New_York (the bulk SUBMISSION table has no acceptance "
                         "time; parsed acceptance_datetime_utc is null)"),
        "entry_primary": "OPEN of the first CRSP session strictly after the filing date; missing open -> that session's close",
        "price_floor_usd": CFG.INSIDER_COPY_MIN_PRICE,
        "horizons_sessions": list(CFG.INSIDER_COPY_HORIZONS),
        "prior_record": ("for each trade, the same insider's earlier copy trades whose exit session date is "
                         "strictly before this filing date; excess = gross raw return minus the market over the "
                         "same sessions, at the same horizon H (V6: at 21); score = sum/(n+K), K="
                         f"{CFG.INSIDER_COPY_SHRINK_K}; eligible iff n >= min_prior"),
        "ranking_rule": (f"top = score >= the {CFG.INSIDER_COPY_TOP_PCT:.0f}th percentile, poor = score <= the "
                         f"{CFG.INSIDER_COPY_POOR_PCT:.0f}th percentile of the scores of eligible trades filed in "
                         f"[month start - {CFG.INSIDER_COPY_CUTOFF_LOOKBACK_DAYS}d, month start); no label when "
                         f"fewer than {CFG.INSIDER_COPY_CUTOFF_MIN_SCORES} such scores"),
        "controls": {
            "a_market": "FF daily mktrf+rf (CRSP VW market); SPY is not in the CRSP pull",
            "b_poor": "the poor-record sleeve, same H-session blocks",
            "c_all": "every copy trade unranked, same blocks",
            "d_random": (f"{CFG.INSIDER_COPY_CONTROLS_PER_TRADE} names per trade, same size decile (market cap "
                         "on the session before entry), alive on the entry session, not the issuer, same "
                         f"entry/exit/cost rules, seed {CFG.INSIDER_COPY_SEED}"),
        },
        "costs": {"round_trip_bps_by_median_dollar_volume": [list(b) for b in CFG.INSIDER_COPY_COST_BANDS],
                  "lookback_sessions": CFG.INSIDER_COPY_DV_LOOKBACK, "zero_cost": "refused"},
        "delisting": (f"CRSP dlret applied on the session after the last price; missing dlret on codes 500-599 "
                      f"-> {CFG.INSIDER_COPY_PERF_DELIST_RET}; otherwise 0; cash (0) to the window end"),
        "statistics": ("trades grouped into blocks of H sessions by entry session; t over blocks and over "
                       "alternate blocks (strictly non-overlapping windows); MDE = 2.8 x the alternate-block SE; "
                       "by entry year; leave-one-year-out; top-date and top-name share of the summed result"),
        "verdict_rule": ("per horizon, V1 top sleeve: OBSERVED iff net excess vs market, vs poor and vs random "
                         f"control all > 0, alternate-block t >= {T_BAR} vs poor AND vs control, worst "
                         "leave-one-year-out mean > 0 and a strict majority of entry years > 0; FAILED_VARIANT iff "
                         f"net excess vs control < 0 with t <= -{T_BAR}; else CANNOT_DISTINGUISH"),
        "variants": VARIANTS,
        "variants_count": len(VARIANTS),
        "variants_max": CFG.INSIDER_COPY_MAX_VARIANTS,
        "primary": "V1_primary",
        "owner_question": (f"of insiders with >= {CFG.INSIDER_COPY_MIN_PRIOR} closed prior purchases, the share "
                           f"whose later purchase reached raw >= +{CFG.INSIDER_COPY_OWNER_MULTIPLE*100:.0f}% at 126 "
                           f"or {CFG.INSIDER_COPY_OWNER_LONG_HORIZON} sessions; ex-post-selected vs ex-ante copy, "
                           "with the arithmetic printed"),
    }


def part_declare(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    p = out / DECL_NAME
    if p.exists():
        say(f"REFUSED: {p} exists (a declaration is written once)")
        return 2
    if len(VARIANTS) > CFG.INSIDER_COPY_MAX_VARIANTS:
        say("REFUSED: more variants than the declared maximum")
        return 2
    body = declaration_body()
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p} sha {body['sha16']} at {body['written_utc']}")
    return 0


# ─────────────────────────── load ────────────────────────────────────────


def load_trades() -> tuple[pd.DataFrame, dict]:
    cols = ["permno", "event_type", "event_time_utc", "observed_at_utc", "insider_cik", "insider_is_officer",
            "insider_is_director", "insider_is_tenpercent", "insider_dollar_value", "insider_cluster_buyers",
            "symbol"]
    B = pd.read_parquet(EVENTS, columns=cols, filters=[("event_type", "=", "insider_open_market_buy")])
    info = {"buy_rows_all": int(len(B)), "buy_rows_with_permno": int(B["permno"].notna().sum())}
    Cl = pd.read_parquet(EVENTS, columns=["permno", "event_type", "event_time_utc", "observed_at_utc", "insider_cik"],
                         filters=[("event_type", "in", ["insider_opportunistic_buy", "insider_routine_buy"])])
    Cl["cmp_class"] = Cl["event_type"].map({"insider_opportunistic_buy": "opportunistic",
                                            "insider_routine_buy": "routine"})
    Cl = (Cl.sort_values("cmp_class")      # 'opportunistic' < 'routine': keep the stronger label
          .drop_duplicates(["insider_cik", "permno", "event_time_utc", "observed_at_utc"])
          .drop(columns=["event_type"]))
    B = B.merge(Cl, on=["insider_cik", "permno", "event_time_utc", "observed_at_utc"], how="left")
    B["cmp_class"] = B["cmp_class"].fillna("unclassifiable")
    B = B.dropna(subset=["permno", "observed_at_utc", "insider_cik"])
    B["filing_date"] = (B["observed_at_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None)
                        .dt.normalize())
    B = B[(B["filing_date"] >= pd.Timestamp(CFG.INSIDER_COPY_FIRST_FILING))
          & (B["filing_date"] <= pd.Timestamp(CFG.INSIDER_COPY_LAST_FILING))]
    B["permno"] = B["permno"].astype("int64")
    sym = B.groupby("permno")["symbol"].agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else "")
    B = B.rename(columns={"insider_is_officer": "is_officer", "insider_is_director": "is_director",
                          "insider_is_tenpercent": "is_tenpercent", "insider_dollar_value": "dollar_value",
                          "insider_cluster_buyers": "cluster_buyers"})
    info["buy_rows_in_window_linked"] = int(len(B))
    T = IC.aggregate_trades(B[["insider_cik", "permno", "filing_date", "cmp_class", "cluster_buyers",
                               "is_officer", "is_director", "is_tenpercent", "dollar_value"]],
                            cluster_min=CFG.INSIDER_COPY_CLUSTER_MIN)
    T["symbol"] = T["permno"].map(sym).fillna("")
    info["copy_trades"] = int(len(T))
    info["cmp_class_counts"] = T["cmp_class"].value_counts().to_dict()
    info["cluster_trades"] = int(T["cluster"].sum())
    info["filing_span"] = [str(T["filing_date"].min().date()), str(T["filing_date"].max().date())]
    del B, Cl
    gc.collect()
    return T, info


def load_crsp(years: range) -> dict:
    """Session calendar, permno columns and the daily matrices, filled year by year."""
    dates, perms = set(), set()
    for y in years:
        f = WRDS / f"crsp_dsf_{y}.parquet"
        d = pd.read_parquet(f, columns=["permno", "date"])
        dates.update(pd.to_datetime(d["date"]).unique().tolist())
        perms.update(pd.to_numeric(d["permno"]).astype("int64").unique().tolist())
        del d
    sessions = np.array(sorted(dates), dtype="datetime64[D]")
    permnos = np.array(sorted(perms), dtype=np.int64)
    Tn, Nn = len(sessions), len(permnos)
    say(f"  CRSP sessions {Tn} ({sessions[0]}..{sessions[-1]}), permnos {Nn}")
    R = np.full((Tn, Nn), np.nan, dtype=np.float32)
    G = np.full((Tn, Nn), np.nan, dtype=np.float32)
    P = np.full((Tn, Nn), np.nan, dtype=np.float32)
    CAP = np.full((Tn, Nn), np.nan, dtype=np.float32)
    DV = np.full((Tn, Nn), np.nan, dtype=np.float32)
    rows = 0
    for y in years:
        t0 = time.time()
        X = pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet",
                            columns=["permno", "date", "ret", "prc", "openprc", "vol", "shrout"])
        ti = np.searchsorted(sessions, pd.to_datetime(X["date"]).to_numpy(dtype="datetime64[D]"))
        ci = np.searchsorted(permnos, pd.to_numeric(X["permno"]).astype("int64").to_numpy())
        prc = np.abs(pd.to_numeric(X["prc"], errors="coerce").to_numpy(dtype=float))
        prc[prc == 0] = np.nan
        opn = np.abs(pd.to_numeric(X["openprc"], errors="coerce").to_numpy(dtype=float))
        opn[opn == 0] = np.nan
        ret = pd.to_numeric(X["ret"], errors="coerce").to_numpy(dtype=float)
        vol = pd.to_numeric(X["vol"], errors="coerce").to_numpy(dtype=float)
        sh = pd.to_numeric(X["shrout"], errors="coerce").to_numpy(dtype=float)
        R[ti, ci] = ret
        P[ti, ci] = prc
        with np.errstate(divide="ignore", invalid="ignore"):
            G[ti, ci] = np.log(prc / opn)
        CAP[ti, ci] = prc * sh * 1000.0
        DV[ti, ci] = prc * vol
        rows += len(X)
        del X, ti, ci, prc, opn, ret, vol, sh
        gc.collect()
        say(f"    dsf {y} {time.time()-t0:.0f}s")
    return {"sessions": sessions, "permnos": permnos, "R": R, "G": G, "P": P, "CAP": CAP, "DV": DV,
            "rows": rows}


def fold_delistings(M: dict) -> dict:
    """CRSP delisting return on the session after the last price; cash afterwards."""
    dl = pd.read_parquet(DELIST, columns=["permno", "dlstdt", "dlstcd", "dlret"])
    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    s, perm = M["sessions"], M["permnos"]
    dl = dl[(dl["dlstcd"] != 100) & (dl["dlstdt"] >= pd.Timestamp(str(s[0])))
            & (dl["dlstdt"] <= pd.Timestamp(str(s[-1]))) & dl["permno"].isin(perm)]
    R, P = M["R"], M["P"]
    n_applied = n_shumway = n_zero = n_end = 0
    for row in dl.itertuples(index=False):
        c = int(np.searchsorted(perm, int(row.permno)))
        valid = np.flatnonzero(np.isfinite(P[:, c]))
        if not len(valid):
            continue
        last = int(valid[-1])
        if last + 1 >= len(s):
            n_end += 1
            continue
        if np.isfinite(row.dlret):
            r = float(row.dlret)
        elif 500 <= int(row.dlstcd) < 600:
            r = CFG.INSIDER_COPY_PERF_DELIST_RET
            n_shumway += 1
        else:
            r = 0.0
            n_zero += 1
        R[last + 1, c] = r
        n_applied += 1
    return {"delist_records_in_span": int(len(dl)), "applied": n_applied,
            "shumway_imputed": n_shumway, "zero_imputed_nonperformance": n_zero, "at_panel_end": n_end}


def market_series(sessions: np.ndarray) -> tuple[np.ndarray, int]:
    ff = pd.read_parquet(FF, columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    m = (ff.set_index("date")["mktrf"] + ff.set_index("date")["rf"]).astype(float)
    m = m.reindex(pd.DatetimeIndex(sessions.astype("datetime64[ns]")))
    missing = int(m.isna().sum())
    return m.fillna(0.0).to_numpy(), missing


# ─────────────────────────── evaluate ────────────────────────────────────


def _sleeve_report(name: str, d: pd.DataFrame, H: int) -> dict:
    """Everything the brief asks for, for one sleeve at one horizon."""
    ei = d["entry_idx"].to_numpy()
    yrs = d["entry_year"].to_numpy()
    dates = d["entry_date"].astype(str).to_numpy()
    out = {"sleeve": name, "n_trades": int(len(d)), "n_dates": int(d["entry_date"].nunique()),
           "n_insiders": int(d["insider_cik"].nunique()), "n_names": int(d["permno"].nunique()),
           "mean_raw_net": float(d["net"].mean()) if len(d) else float("nan"),
           "mean_market": float(d["r_mkt"].mean()) if len(d) else float("nan"),
           "vs_market_net": IC.stats(d["ex_mkt_net"].to_numpy(), ei, H),
           "vs_random_control_net": IC.stats(d["ex_ctrl_net"].to_numpy(), ei, H),
           "control_coverage": float(d["ex_ctrl_net"].notna().mean()) if len(d) else float("nan")}
    if len(d):
        out["by_year_vs_market_net"] = IC.by_year(d["ex_mkt_net"].to_numpy(), ei, yrs, H, dates)
        out["by_year_vs_control_net"] = IC.by_year(d["ex_ctrl_net"].to_numpy(), ei, yrs, H, dates)
        out["loo_vs_market_net"] = IC.leave_one_year_out(d["ex_mkt_net"].to_numpy(), ei, yrs, H)
        out["loo_vs_control_net"] = IC.leave_one_year_out(d["ex_ctrl_net"].to_numpy(), ei, yrs, H)
        out["concentration_vs_market_net"] = IC.concentration(d["ex_mkt_net"].to_numpy(), dates,
                                                              d["symbol"].to_numpy())
        out["concentration_vs_control_net"] = IC.concentration(d["ex_ctrl_net"].to_numpy(), dates,
                                                               d["symbol"].to_numpy())
        out["delisted_in_window"] = int(d["delisted_in_window"].sum())
        out["open_missing_entered_at_close"] = int(d["open_missing"].sum())
        out["cost_mean_round_trip"] = float(d["cost"].mean())
    return out


def _split(d: pd.DataFrame, col: str, H: int) -> dict:
    res = {}
    for k, g in d.groupby(col):
        ei = g["entry_idx"].to_numpy()
        res[str(k)] = {"n_trades": int(len(g)), "n_dates": int(g["entry_date"].nunique()),
                       "n_insiders": int(g["insider_cik"].nunique()),
                       "vs_market_net": IC.stats(g["ex_mkt_net"].to_numpy(), ei, H),
                       "vs_random_control_net": IC.stats(g["ex_ctrl_net"].to_numpy(), ei, H)}
    return res


def _compound(d: pd.DataFrame, H: int) -> dict:
    """Approximate rolling-cohort compounding: each H-session block holds the
    equal-weight cohort that entered in it; product over consecutive blocks."""
    if d.empty:
        return {}
    b = d["entry_idx"].to_numpy() // H
    g = pd.DataFrame({"b": b, "net": d["net"].to_numpy(), "mkt": d["r_mkt"].to_numpy()}).groupby("b").mean()
    yrs = len(g) * H / 252.0
    book = float(np.prod(1 + g["net"].to_numpy()))
    mkt = float(np.prod(1 + g["mkt"].to_numpy()))
    ann_b = book ** (1 / yrs) - 1 if yrs > 0 and book > 0 else float("nan")
    ann_m = mkt ** (1 / yrs) - 1 if yrs > 0 and mkt > 0 else float("nan")
    return {"blocks": int(len(g)), "years_spanned_by_blocks": yrs, "growth_book": book, "growth_market": mkt,
            "annualised_book_net": ann_b, "annualised_market": ann_m,
            "ratio_annualised": ann_b / ann_m if ann_m and np.isfinite(ann_m) and ann_m != 0 else float("nan"),
            "note": ("approximate: windows inside a block start on different sessions; blocks without a trade "
                     "are skipped (cash periods not counted), which flatters a sparse sleeve")}


def part_run(out: Path) -> int:
    t_start = _now()
    dp = out / DECL_NAME
    if not dp.exists():
        say(f"REFUSED: no declaration at {dp}; run `declare` first")
        return 2
    decl = json.loads(dp.read_text(encoding="utf-8"))
    if _sha({k: v for k, v in decl.items() if k not in ("sha16", "written_utc")}) != decl["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    if _sha(declaration_body()) != decl["sha16"]:
        say("REFUSED: the code's declaration no longer matches the file (rule changed after declaring)")
        return 2
    if not decl["written_utc"] < t_start:
        say("REFUSED: declaration is not older than the run")
        return 2
    rp = out / RECEIPT_NAME
    if rp.exists():
        say(f"REFUSED: {rp} exists")
        return 2
    live_before = count_live()
    say(f"live folder file counts before: {live_before}")
    t0 = time.time()
    trades, tinfo = load_trades()
    say(f"  copy trades {len(trades):,} ({time.time()-t0:.0f}s) {tinfo}")
    first_y = pd.Timestamp(CFG.INSIDER_COPY_FIRST_FILING).year - 1
    M = load_crsp(range(first_y, 2025))
    dinfo = fold_delistings(M)
    say(f"  delistings {dinfo}")
    sessions, permnos = M["sessions"], M["permnos"]
    mk, mk_missing = market_series(sessions)
    Mc = IC.cumulative_log(mk)
    alive = np.isfinite(M["P"])
    last_valid = np.where(alive.any(axis=0), alive.shape[0] - 1 - np.argmax(alive[::-1], axis=0), -1)
    # size buckets on each session (deciles of market cap among priced names)
    cap = pd.DataFrame(M["CAP"])
    pct = cap.rank(axis=1, pct=True).to_numpy(dtype=np.float32)
    del cap
    bucket = np.where(np.isfinite(pct), np.minimum((pct * CFG.INSIDER_COPY_SIZE_BUCKETS).astype(np.int16),
                                                   CFG.INSIDER_COPY_SIZE_BUCKETS - 1), -1).astype(np.int8)
    del pct
    gc.collect()
    dvmed = (pd.DataFrame(M["DV"]).rolling(CFG.INSIDER_COPY_DV_LOOKBACK, min_periods=10).median()
             .shift(1).to_numpy(dtype=np.float32))
    del M["DV"]
    gc.collect()
    C = IC.cumulative_log(M["R"])
    del M["R"]
    gc.collect()
    G = M["G"]
    say(f"  matrices ready {time.time()-t0:.0f}s")

    # map trades to columns and entry sessions
    trades = trades[trades["permno"].isin(permnos)].copy()
    col = np.searchsorted(permnos, trades["permno"].to_numpy())
    fdates = trades["filing_date"].to_numpy(dtype="datetime64[D]")
    entry = IC.entry_session_index(fdates, sessions)
    n_entry_checked = IC.assert_entry_after_public(fdates, sessions, entry)
    trades["col"], trades["entry_idx"] = col, entry
    ok = (entry > 0)
    prev_px = np.where(ok, M["P"][np.where(ok, entry - 1, 0), col], np.nan)
    alive_entry = np.where(ok, alive[np.where(ok, entry, 0), col], False)
    n0 = len(trades)
    keep = ok & alive_entry & (prev_px >= CFG.INSIDER_COPY_MIN_PRICE)
    funnel = {"copy_trades_linked": int(n0), "with_entry_session": int(ok.sum()),
              "alive_on_entry": int((ok & alive_entry).sum()), "price_floor_pass": int(keep.sum())}
    trades = trades[keep].reset_index(drop=True)
    col, entry = trades["col"].to_numpy(), trades["entry_idx"].to_numpy()
    trades["entry_date"] = pd.to_datetime(sessions[entry])
    trades["entry_year"] = trades["entry_date"].dt.year
    trades["cap_prev"] = M["CAP"][entry - 1, col]
    trades["large_cap"] = trades["cap_prev"] >= CFG.INSIDER_COPY_LARGE_CAP_USD
    trades["cost"] = IC.round_trip_cost(dvmed[entry, col], CFG.INSIDER_COPY_COST_BANDS)
    say(f"  funnel {funnel}; entry checked on {n_entry_checked:,} rows")

    ctrl = IC.sample_controls(entry, col, bucket, alive, CFG.INSIDER_COPY_CONTROLS_PER_TRADE,
                              CFG.INSIDER_COPY_SEED)
    say(f"  controls sampled {time.time()-t0:.0f}s, coverage {(ctrl[:, 0] >= 0).mean():.3f}")
    del bucket
    gc.collect()

    # outcomes per (mode, H)
    horizons = sorted(set(CFG.INSIDER_COPY_HORIZONS) | {CFG.INSIDER_COPY_OWNER_LONG_HORIZON, 21})
    outc: dict[tuple[str, int], pd.DataFrame] = {}
    for mode in ("next_open", "next_close"):
        for H in horizons:
            if mode == "next_close" and H not in CFG.INSIDER_COPY_HORIZONS:
                continue
            w = IC.window_returns(entry, col, H, C, G, mode)
            rm = IC.market_returns(entry, H, Mc, mode)
            cr = []
            for k in range(ctrl.shape[1]):
                ck = ctrl[:, k]
                has = ck >= 0
                wk = IC.window_returns(entry, np.where(has, ck, 0), H, C, G, mode)
                ck_cost = IC.round_trip_cost(dvmed[entry, np.where(has, ck, 0)], CFG.INSIDER_COPY_COST_BANDS)
                cr.append(np.where(has & wk["valid"], wk["r"] - ck_cost, np.nan))
            cr = np.vstack(cr)
            with np.errstate(invalid="ignore"):
                cmean = np.where(np.isfinite(cr).sum(axis=0) > 0, np.nanmean(np.where(np.isfinite(cr), cr, np.nan), axis=0), np.nan)
            ex_idx = w["exit_idx"]
            net = w["r"] - trades["cost"].to_numpy()
            outc[(mode, H)] = pd.DataFrame({
                "r": w["r"], "net": net, "r_mkt": rm, "ex_mkt_gross": w["r"] - rm, "ex_mkt_net": net - rm,
                "ex_ctrl_net": net - cmean, "valid": w["valid"], "open_missing": w["open_missing"],
                "exit_day": np.where(ex_idx >= 0, sessions[np.maximum(ex_idx, 0)].astype(np.int64), -1),
                "delisted_in_window": w["valid"] & (last_valid[col] < np.where(ex_idx >= 0, ex_idx, 0))})
            say(f"    outcomes {mode} H={H} valid {w['valid'].mean():.3f} {time.time()-t0:.0f}s")
    del C, G
    gc.collect()

    base = trades[["insider_cik", "permno", "symbol", "filing_date", "entry_idx", "entry_date", "entry_year",
                   "cmp_class", "cluster", "is_officer", "is_director", "is_tenpercent", "large_cap", "cost"]]
    filing_day = trades["filing_date"].to_numpy(dtype="datetime64[D]").astype(np.int64)
    receipt: dict = {"schema": "ch47/insider_copy_receipt/1", "declaration_sha16": decl["sha16"],
                     "declaration_written_utc": decl["written_utc"], "run_started_utc": t_start,
                     "licence": decl["licence"], "inputs": {}, "funnel": funnel, "trade_info": tinfo,
                     "delistings": dinfo, "market_missing_sessions": mk_missing, "variants": {},
                     "variants_tried": list(VARIANTS), "variants_count": len(VARIANTS)}
    for vname, v in VARIANTS.items():
        vres: dict = {"spec": v, "horizons": {}}
        roles_ok = np.ones(len(base), dtype=bool)
        if v["roles"] == "officer_or_director":
            roles_ok = (base["is_officer"] | base["is_director"]).to_numpy()
        for H in CFG.INSIDER_COPY_HORIZONS:
            o = outc[(v["entry"], H)]
            rh = H if v["record_h"] == "same" else int(v["record_h"])
            orec = outc[(v["entry"], rh)]
            sel = roles_ok
            ins = base["insider_cik"].to_numpy()[sel]
            rec = IC.prior_record(ins, filing_day[sel], orec["exit_day"].to_numpy()[sel],
                                  orec["ex_mkt_gross"].to_numpy()[sel])
            audit = IC.audit_prior_record(ins, filing_day[sel], orec["exit_day"].to_numpy()[sel],
                                          orec["ex_mkt_gross"].to_numpy()[sel], rec, sample_n=2000,
                                          seed=CFG.INSIDER_COPY_SEED + H)
            sc = IC.score(rec, v["score"], CFG.INSIDER_COPY_SHRINK_K, v["min_prior"])
            lab = IC.rank_labels(base["filing_date"].to_numpy()[sel], sc, CFG.INSIDER_COPY_TOP_PCT,
                                 CFG.INSIDER_COPY_POOR_PCT, CFG.INSIDER_COPY_CUTOFF_LOOKBACK_DAYS,
                                 CFG.INSIDER_COPY_CUTOFF_MIN_SCORES)
            d = pd.concat([base[sel].reset_index(drop=True), o[sel].reset_index(drop=True)], axis=1)
            d["label"], d["score"], d["n_prior"] = lab, sc, rec["n_prior"].to_numpy()
            d = d[d["valid"]]
            top, poor, allt = d[d["label"] == "top"], d[d["label"] == "poor"], d
            hres = {"label_counts": d["label"].value_counts().to_dict(), "audit": audit,
                    "top": _sleeve_report("top", top, H), "poor": _sleeve_report("poor", poor, H),
                    "all_unranked": _sleeve_report("all", allt, H),
                    "top_minus_poor_vs_market_net": IC.diff_stats(
                        top["ex_mkt_net"].to_numpy(), top["entry_idx"].to_numpy(),
                        poor["ex_mkt_net"].to_numpy(), poor["entry_idx"].to_numpy(), H),
                    "top_minus_all_vs_market_net": IC.diff_stats(
                        top["ex_mkt_net"].to_numpy(), top["entry_idx"].to_numpy(),
                        allt["ex_mkt_net"].to_numpy(), allt["entry_idx"].to_numpy(), H),
                    "top_by_cmp_class": _split(top, "cmp_class", H),
                    "top_by_cluster": _split(top, "cluster", H),
                    "top_large_cap": _sleeve_report("top_large_cap", top[top["large_cap"]], H),
                    "all_large_cap": _sleeve_report("all_large_cap", allt[allt["large_cap"]], H),
                    "top_compounding": _compound(top, H), "all_compounding": _compound(allt, H)}
            yrs = hres["top"].get("by_year_vs_control_net", [])
            share_pos = (np.mean([r["mean_block"] > 0 for r in yrs]) if yrs else 0.0)
            hres["share_years_positive_vs_control"] = float(share_pos)
            hres["verdict"] = IC.verdict(hres["top"]["vs_market_net"], hres["top_minus_poor_vs_market_net"],
                                         hres["top"]["vs_random_control_net"],
                                         hres["top"].get("loo_vs_control_net", {}).get("loo_worst_mean_block", -1),
                                         share_pos, T_BAR)
            vres["horizons"][str(H)] = hres
            tm = hres["top"]["vs_market_net"]
            say(f"  {vname} H={H}: top n {hres['top']['n_trades']} vs mkt {tm['mean_block']:+.4f} "
                f"t_no {tm['t_nonoverlap']:+.2f} | vs ctrl {hres['top']['vs_random_control_net']['mean_block']:+.4f} "
                f"t_no {hres['top']['vs_random_control_net']['t_nonoverlap']:+.2f} | top-poor "
                f"{hres['top_minus_poor_vs_market_net']['mean_block']:+.4f} "
                f"t_no {hres['top_minus_poor_vs_market_net']['t_nonoverlap']:+.2f} -> {hres['verdict']}")
            if vname == "V1_primary" and H == 126:
                receipt["_v1_126_frame"] = d          # for the owner question; removed before writing
        receipt["variants"][vname] = vres

    receipt["owner_question"] = owner_question(base, outc, receipt.pop("_v1_126_frame"))
    receipt["inputs"] = inputs_table(trades, sessions, permnos, dinfo, tinfo)
    receipt["live_file_counts_before"] = live_before
    receipt["live_file_counts_after"] = count_live()
    receipt["finished_utc"] = _now()
    _write(rp, _clean(receipt))
    say(f"live folder file counts after: {receipt['live_file_counts_after']}")
    say(f"-> {rp} ({time.time()-t0:.0f}s)")
    return 0


def owner_question(base: pd.DataFrame, outc: dict, d126: pd.DataFrame) -> dict:
    """'Some insiders made 300%': how many, found when, and what copying them earned."""
    mult = CFG.INSIDER_COPY_OWNER_MULTIPLE
    res: dict = {"multiple": mult, "definition": "raw return >= +300% (r >= 3.0) from the next-open entry"}
    o126, o252 = outc[("next_open", 126)], outc[("next_open", CFG.INSIDER_COPY_OWNER_LONG_HORIZON)]
    df = base[["insider_cik", "permno", "symbol", "filing_date", "entry_idx", "entry_year"]].copy()
    df["r126"], df["r252"] = o126["r"].to_numpy(), o252["r"].to_numpy()
    df["ex126"], df["v126"] = o126["ex_mkt_net"].to_numpy(), o126["valid"].to_numpy()
    df["exit126"] = o126["exit_day"].to_numpy()
    df["hit126"], df["hit252"] = df["r126"] >= mult, df["r252"] >= mult
    res["purchases_measured_126"] = int(df["v126"].sum())
    res["purchases_hit_126"] = int(df["hit126"].sum())
    res["purchases_hit_252"] = int(df["hit252"].sum())
    res["share_purchases_hit_126"] = float(df.loc[df["v126"], "hit126"].mean())
    allins = df["insider_cik"].nunique()
    hit_ins_126 = df.loc[df["hit126"], "insider_cik"].nunique()
    hit_ins_252 = df.loc[df["hit252"], "insider_cik"].nunique()
    res["insiders_all"] = int(allins)
    res["insiders_with_any_hit_126"] = int(hit_ins_126)
    res["insiders_with_any_hit_252"] = int(hit_ins_252)
    # eligible = had >= MIN_PRIOR closed prior purchases at some filing; "later" = a hit on a purchase
    # filed while eligible
    el = d126[d126["n_prior"] >= CFG.INSIDER_COPY_MIN_PRIOR]
    el_ins = el["insider_cik"].nunique()
    res["insiders_ever_eligible_126"] = int(el_ins)
    later = el[el["r"] >= mult]
    res["eligible_insiders_with_a_later_hit_126"] = int(later["insider_cik"].nunique())
    res["share_eligible_insiders_later_hit_126"] = float(later["insider_cik"].nunique() / el_ins) if el_ins else None
    # survivor arithmetic at H=126
    hitters = set(df.loc[df["hit126"], "insider_cik"])
    S = df[df["insider_cik"].isin(hitters) & df["v126"]]
    res["expost_selected_mean_net_excess_126_all_their_trades"] = float(S["ex126"].mean())
    res["expost_selected_n_trades"] = int(len(S))
    Sx = S[~S["hit126"]]
    res["expost_selected_mean_net_excess_126_excluding_the_hits"] = float(Sx["ex126"].mean())
    first_close = df[df["hit126"]].groupby("insider_cik")["exit126"].min()
    S2 = S[S["filing_date"].to_numpy(dtype="datetime64[D]").astype(np.int64)
           > S["insider_cik"].map(first_close).to_numpy()]
    res["after_discovery_n_trades"] = int(len(S2))
    res["after_discovery_n_insiders"] = int(S2["insider_cik"].nunique())
    res["after_discovery_mean_net_excess_126"] = float(S2["ex126"].mean()) if len(S2) else None
    res["after_discovery_share_hit_again"] = float(S2["hit126"].mean()) if len(S2) else None
    res["after_discovery_stats"] = (IC.stats(S2["ex126"].to_numpy(), S2["entry_idx"].to_numpy(), 126)
                                    if len(S2) else None)
    top = d126[d126["label"] == "top"]
    res["exante_top_n_trades_126"] = int(len(top))
    res["exante_top_mean_net_excess_126"] = float(top["ex_mkt_net"].mean()) if len(top) else None
    res["exante_top_share_hit_126"] = float((top["r"] >= mult).mean()) if len(top) else None
    res["all_purchases_mean_net_excess_126"] = float(df.loc[df["v126"], "ex126"].mean())
    res["top_expost_insiders_by_total_raw_126"] = (
        df[df["v126"]].groupby("insider_cik").agg(n=("r126", "size"), best=("r126", "max"),
                                                    mean_net_excess=("ex126", "mean"))
        .sort_values("best", ascending=False).head(10).reset_index().to_dict(orient="records"))
    return res


def inputs_table(trades: pd.DataFrame, sessions: np.ndarray, permnos: np.ndarray, dinfo: dict,
                 tinfo: dict) -> list[dict]:
    def age(p: Path) -> str:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d") if p.exists() else "absent"
    rows = [
        {"input": "Form 4 events (code P buys)", "path": str(EVENTS), "file_date": age(EVENTS),
         "span": tinfo["filing_span"], "rows": tinfo["buy_rows_all"], "rows_used": tinfo["copy_trades"],
         "survivorship": "filings are a full tape; linked rows only (permno link)"},
        {"input": "CRSP daily (dsf per year)", "path": str(WRDS / "crsp_dsf_<year>.parquet"),
         "file_date": age(WRDS / "crsp_dsf_2024.parquet"), "span": [str(sessions[0]), str(sessions[-1])],
         "rows": None, "permnos": int(len(permnos)), "survivorship": "includes dead names (delisting-inclusive)"},
        {"input": "CRSP delistings", "path": str(DELIST), "file_date": age(DELIST), "span": None,
         "rows": dinfo["delist_records_in_span"], "survivorship": "folded into returns"},
        {"input": "FF daily market (SPY proxy)", "path": str(FF), "file_date": age(FF), "span": None,
         "rows": None, "survivorship": "index"},
    ]
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("part", choices=["declare", "run"])
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.part == "declare":
        return part_declare(a.out)
    return part_run(a.out)


if __name__ == "__main__":
    raise SystemExit(main())
