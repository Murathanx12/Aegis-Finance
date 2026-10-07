"""The nightly loop.

    python -m nn_lab.nightly [--time-box-min 90]

Rebuilt 2026-09-29 after `docs/reviews/REVIEW_2026-09-29_NN_LAB.md`. Each night, in order,
each step checkpointed so a crashed night RESUMES (same UTC day only):

  a. APPEND   rebuild the table's tail from the refreshed bars (+ side groups). The shrink
              guard compares the TABLE: every stored grid row and every stored label must
              still be there (review F6: comparing today's cross-section with yesterday's
              refused ordinary weekdays). Since 2026-10-06 a stored grid date's MEMBERSHIP and
              features are FROZEN (nn_lab/membership.py): the rebuild adds new dates and
              matured labels, and every vendor re-adjustment is appended to
              table/revisions.parquet, never applied. A refusal is status REFUSED, with a receipt.
  b. GRADE    every frozen file whose horizon has elapsed, after its sha256 is checked
              against the ledger (`loop.step_grade`). Delisted names exit at their last close.
  c. TRUST    every model's posterior rank IC from its graded forward blocks (walk-forward
              blocks at 0.1 weight until forward blocks exist); the model in charge changes
              only on a night that added forward grades (`loop.decide_in_charge`).
  d. FIT      the fitted rivals (network, LightGBM, ridge, ridge on |y|) are refit ONLY when
              a new labelled grid date exists (review F5: a night with no new label trained
              and "promoted" on an unchanged block), on train+val (F5.4).
  e. FREEZE   every roster model, the trust-weighted ensemble and the size-of-move forecast
              for the newest decision date, each to its own immutable file.
  f. RECEIPT  per model: graded dates so far, trust today and yesterday, what changed.
              Status OK / DEGRADED (nothing new) / STALE_BARS (the table is behind the last
              closed weekday session) / FAILED / REFUSED / TIMEOUT.

There is no promotion on a validation block any more. It refuses BY NAME on a STOP file,
low disk, low memory, a concurrent run. It imports nothing from the live decision path
and places no orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from nn_lab import config as C
from nn_lab import loop as L
from nn_lab import membership as MB
from nn_lab import seeds as S

H = C.HORIZONS
STATE_PATH = C.OUT / "night_state.json"
LOCK_PATH = C.OUT / "night.lock"
RIVALS_STATE = C.MODEL_DIR / "rivals" / "state.json"
N_SEEDS = 3
LEGACY_V0 = {"model": "nn_v0_leaky", "file": "pred_2026-09-25_nightly_20260928T141823Z.parquet",
             "receipt": "nightly_20260928T141823Z.json",
             "why": "the 2026-09-28 network, trained on the table with the future-split leak (F1); graded "
                    "honestly forward, never trusted or ensembled"}


# TableShrink, shrink_check and labelled_dates moved to nn_lab/membership.py (2026-10-06,
# the frozen-membership merge); re-exported here so every caller and test keeps its name.
TableShrink = MB.TableShrink
shrink_check = MB.shrink_check
labelled_dates = MB.labelled_dates


# ─────────────────────────── small pure helpers (tested) ─────────────────────

def night_status(new_rows_since_last_run: int, refused: str | None = None, *, stale: bool = False,
                 degraded: list[str] | tuple = ()) -> str:
    """REFUSED > STALE_BARS > DEGRADED (membership counts above the declared levels, review C5
    F5, or nothing new) > OK."""
    if refused:
        return "REFUSED"
    if stale:
        return "STALE_BARS"
    if degraded:
        return "DEGRADED"
    return "OK" if new_rows_since_last_run > 0 else "DEGRADED"


def last_closed_weekday(now_utc: datetime | None = None) -> pd.Timestamp:
    """The last weekday whose US close has surely passed (21:15 UTC covers both DST
    regimes). A US market holiday reads as a session here, so the day after one can say
    STALE_BARS falsely; the receipt says so."""
    now = now_utc or datetime.now(timezone.utc)
    d = pd.Timestamp(now.date())
    if now.hour * 60 + now.minute < 21 * 60 + 15:
        d -= pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def free_gb_disk(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def free_gb_ram() -> float | None:
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1e9
    except Exception:
        return None


def refuse_reason() -> str | None:
    if C.STOP_FILE.exists():
        return f"STOP_FILE present at {C.STOP_FILE}"
    d = free_gb_disk(C.OUT if C.OUT.exists() else C.REPO)
    if d < C.MIN_FREE_DISK_GB:
        return f"LOW_DISK: {d:.1f} GB free < {C.MIN_FREE_DISK_GB}"
    r = free_gb_ram()
    if r is not None and r < C.MIN_FREE_RAM_GB:
        return f"LOW_MEMORY: {r:.1f} GB free < {C.MIN_FREE_RAM_GB}"
    if LOCK_PATH.exists():
        try:
            pid = int(json.loads(LOCK_PATH.read_text())["pid"])
            if _pid_alive(pid):
                return f"CONCURRENT_RUN: pid {pid} holds {LOCK_PATH}"
        except Exception:
            pass
    return None


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259
    except Exception:
        return False


sha256_file = L.sha256_file


def books_symbols(path: Path | None = None) -> set[str]:
    """Every ticker held by any frozen book. Books store `positions: [{ticker, weight}]`
    (the 2026-09-28 file looked for `weights` and wrote in_frozen_book = 0 everywhere)."""
    bp = Path(path or (C.OPTIMUS / "llm_portfolio" / "books.jsonl"))
    out: set[str] = set()
    if bp.exists():
        for line in bp.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r.get("weights"), dict):
                out.update(r["weights"].keys())
            for hold in (r.get("holdings") or []) + (r.get("positions") or []):
                if isinstance(hold, dict):
                    t = hold.get("ticker") or hold.get("symbol")
                    if t:
                        out.add(str(t))
    return out


# ─────────────────────────────── steps ───────────────────────────────────────

REVISIONS_PATH = C.TABLE_DIR / "revisions.parquet"


def step_append(run_id: str = "manual") -> dict:
    """Rebuild the tail (every grid date from the first with a pending label) + the newest
    session, under FROZEN membership (nn_lab/membership.py, owner decision 2026-10-06):
    a stored grid date keeps exactly its stored members and features; the rebuild may add
    new dates and missing labels, and everything else the vendor changed is appended to
    `revisions.parquet`, never applied. TableShrink still refuses a genuine shrink."""
    from nn_lab import table as T
    tab = pd.read_parquet(C.TABLE_PATH)
    before_raw = MB.table_counts(tab)
    # review C5 F6: the frozen hashes are taken BEFORE the exclusion list is applied, so a list
    # change that removes frozen members is counted, reported and degrades the night instead of
    # vanishing from the frozen check.
    hashes_before = MB.membership_hashes(tab)
    tab_raw_keys = tab.loc[tab["on_grid"].astype(bool), ["date", "symbol", "on_grid"]].copy()
    # 2026-09-30: an ETF/ETN/fund leaving the universe is a deliberate universe change, not a
    # shrink: its stored rows are dropped here, counted, and the shrink guard compares the rest.
    from nn_lab.universe_filter import excluded as _etf_excluded
    _ex = tab["symbol"].isin(_etf_excluded())
    dropped_etf_rows = int(_ex.sum())
    etf_removed = tab.loc[_ex & tab["on_grid"].astype(bool), ["date", "symbol", "on_grid"]].copy()
    tab = tab[~_ex].reset_index(drop=True)
    before = MB.table_counts(tab)
    old_max = tab["date"].max()
    cal_old = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    bars = T.load_bars([C.BARS_DEEP, C.BARS_RECENT, C.BARS_DELISTED], start="2025-01-01",
                       extend_only=[C.BARS_RECENT])
    vendor_through = str(pd.Timestamp(bars["date"].max()).date())
    cal_new = T.session_calendar(bars)
    cal = pd.DatetimeIndex(np.union1d(cal_old.values, cal_new.values))
    grid = cal[T.grid_mask(cal)]
    pending = tab.loc[tab["on_grid"] & tab[[f"y_{h}" for h in H]].isna().any(axis=1), "date"]
    tail_start = pending.min() if len(pending) else old_max
    tail_start = max(tail_start, pd.Timestamp("2026-01-15"))   # recent bars need 252 sessions of lookback
    keep = grid[grid >= tail_start]
    stored_tail = tab[tab["on_grid"] & (tab["date"] >= tail_start)][["date", "symbol"]]
    rows = T.price_rows(bars, cal, keep_dates=keep, keep_last=True, force_keys=stored_tail)
    del bars
    rows["on_grid"] = rows["date"].isin(set(grid))
    # the excess label's median is taken over the FROZEN membership of a stored date
    rows, _would_add = MB.restrict_to_frozen(rows, tab)
    rows = T.add_excess_labels(rows)
    if len(_would_add):   # no labels: merge_frozen records them as revisions and never adds them
        rows = pd.concat([rows, _would_add], ignore_index=True)
    rows = T.attach_side_groups(rows)
    T.assert_pit(rows)
    keep_cols = list(tab.columns.intersection(rows.columns)) + ["_rebuild_eligible"]
    new, revs, mstats = MB.merge_frozen(tab, rows[[c for c in keep_cols if c in rows.columns]],
                                        tail_start=tail_start, cal_stored=cal_old, run_id=run_id,
                                        asof_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        vendor_bars_through=vendor_through)
    chk = shrink_check(tab, new)            # the genuine-shrink guard, on the merged table
    # every stored date's membership hash unchanged, measured against the table BEFORE the
    # exclusion list; only the declared exclusion removals may differ (F6)
    frozen = MB.check_frozen(tab_raw_keys, new, allowed_removed=etf_removed)
    mstats["etf_removed_from_frozen_dates"] = int(len(etf_removed))
    if len(etf_removed):
        revs = pd.concat([revs, pd.DataFrame({
            "date": etf_removed["date"].to_numpy(), "symbol": etf_removed["symbol"].to_numpy(),
            "kind": "ETF_EXCLUDED_FROM_FROZEN_DATE",
            "reason": "the ETF/ETN/fund exclusion list removed this stored member (a declared universe change)",
            "columns": "membership", "max_rel_change": np.nan, "rebuilt_values_hash": "etf",
            "asof_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": run_id,
            "vendor_bars_through": vendor_through})], ignore_index=True)
    after = MB.table_counts(new)
    if after["grid_rows"] < before["grid_rows"] or after["grid_dates"] < before["grid_dates"]:
        raise TableShrink(f"table would shrink {before} -> {after}; refused, original kept")
    tmp = C.TABLE_PATH.with_suffix(".tmp.parquet")
    new.to_parquet(tmp, index=False)
    if len(pd.read_parquet(tmp, columns=["date"])) != len(new):
        raise RuntimeError("table write verification failed; original kept")
    os.replace(tmp, C.TABLE_PATH)
    pd.DataFrame({"date": cal}).to_parquet(C.TABLE_PATH.parent / "calendar.parquet", index=False)
    # F6: revisions are appended only AFTER the table write is verified, so a failed write never
    # leaves the log holding revisions of a table that did not land (and suppresses the retry's)
    # C15 (review C5 F9): a TIMELINE per key (a flip-flop A->B->A is two revisions, the second a
    # REVERTED_TO_STORED row for a checked tail date), then closed months rotate to a tracked
    # monthly parquet + committed manifest. A rotation failure never fails the night.
    rv = MB.append_revisions(revs, REVISIONS_PATH, checked_from=tail_start, run_id=run_id,
                             asof_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        rv["rotation"] = MB.rotate_revisions(REVISIONS_PATH)
    except Exception as exc:                                   # noqa: BLE001 -- named on the receipt
        rv["rotation"] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    stored_grid_dates = set(tab.loc[tab["on_grid"].astype(bool), "date"])
    new_grid = sorted(set(new.loc[new["on_grid"].astype(bool), "date"]) - stored_grid_dates)
    vintage = MB.record_vintage(new_grid, vendor_through, cal, run_id)
    hashes_after = MB.membership_hashes(new)
    prev_h = ((last_receipt() or {}).get("append") or {}).get("membership_hash_by_date") or {}
    moved_vs_prev = sorted(d for d, h in prev_h.items() if hashes_after.get(d, "")[:16] != h)
    new_dates = sorted(set(rows["date"]) - set(tab["date"]))
    return {"old_max_date": str(old_max.date()), "new_max_date": str(new["date"].max().date()),
            "tail_start": str(tail_start.date()), "rows_rebuilt": int(len(rows)),
            "rows_added": int((rows["date"] > old_max).sum()), "new_dates": [str(d.date()) for d in new_dates],
            "labels_filled": chk["labels_filled"], "grid_rows_kept": chk["grid_rows_kept"],
            "etf_rows_dropped_from_stored_table": dropped_etf_rows,
            "table_before_raw": before_raw, "table_before": before, "table_after": after,
            "membership": {**mstats, **frozen,
                           "degraded_reasons": MB.degraded_reasons(mstats),
                           "line": (f"{mstats['rows_re_adjusted']:,} rows re-adjusted (material, config "
                                    f"tolerances); {mstats['membership_would_drop']:,} members the rebuild "
                                    f"would drop and {mstats['member_absent_from_rebuild']:,} absent from it, "
                                    f"kept; 0 dropped; {mstats['membership_would_add']:,} would-add recorded, "
                                    f"not added; {mstats['labels_final_recomputed_applied_and_logged']:,} final "
                                    f"labels recomputed; {mstats['etf_removed_from_frozen_dates']:,} removed by "
                                    f"the exclusion list")},
            "frozen_means": ("the FIRST-STORED VINTAGE of membership and features: point-in-time only for grid "
                             f"dates first stored from {C.PIT_DOLLAR_VOLUME_FROM} at lag 0 (membership_vintage)"),
            "pre_freeze_dollar_volume_note": C.PRE_FREEZE_DV_NOTE,
            "vintage_of_new_grid_dates": vintage,
            "revisions": {**rv, "n_this_run_before_dedupe": int(len(revs))},
            "vendor_bars_through": vendor_through,
            "membership_hash_digest_before": MB.hashes_digest(hashes_before),
            "membership_hash_digest_after": MB.hashes_digest(hashes_after),
            "membership_hash_by_date": {d: h[:16] for d, h in hashes_after.items()},
            "membership_dates_moved_vs_previous_receipt": moved_vs_prev,
            "table_rows": int(len(new)), "table_sha256": sha256_file(C.TABLE_PATH)}


def _grade_bars(start: pd.Timestamp):
    from nn_lab import table as T
    bars = T.load_bars([C.BARS_DEEP, C.BARS_RECENT, C.BARS_DELISTED], start=str(start.date()),
                       extend_only=[C.BARS_RECENT])
    cal_t = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    cal = pd.DatetimeIndex(np.union1d(cal_t.values, T.session_calendar(bars).values))
    return bars, cal


def register_legacy_v0() -> dict:
    """Put the 2026-09-28 frozen file in the ledger ONCE, with the sha256 its own receipt
    recorded (verified), so it is graded forward. Never trusted, never ensembled."""
    idx = L.ledger_index()
    p = C.PRED_DIR / LEGACY_V0["file"]
    rp = C.RECEIPT_DIR / LEGACY_V0["receipt"]
    if not p.exists() or not rp.exists():
        return {"status": "ABSENT"}
    dd = LEGACY_V0["file"].split("_")[1]
    if (dd, LEGACY_V0["model"]) in idx:
        return {"status": "ALREADY_REGISTERED"}
    rec = json.loads(rp.read_text())
    want = ((rec.get("train") or {}).get("predictions") or {}).get("sha256")
    got = sha256_file(p)
    if want != got:
        return {"status": "REFUSED", "why": f"sha256 {got[:12]} != receipt {str(want)[:12]}"}
    df = pd.read_parquet(p, columns=["model_version", "written_utc"])
    L._append_jsonl(C.FROZEN_LEDGER, [{
        "decision_date": dd, "model": LEGACY_V0["model"], "model_version": df["model_version"].iloc[0],
        "kind": "direction", "file": str(p.relative_to(C.REPO)), "sha256": got, "rows": int(len(df)),
        "horizons": list(H), "written_utc": df["written_utc"].iloc[0], "run_id": LEGACY_V0["receipt"][:-5],
        "note": LEGACY_V0["why"]}])
    return {"status": "REGISTERED", "sha256": got}


def step_grade() -> dict:
    reg = register_legacy_v0()
    led = L._read_jsonl(C.FROZEN_LEDGER)
    if not led:
        return {"legacy_v0": reg, "graded_now": 0, "note": "no frozen predictions yet"}
    start = pd.Timestamp(min(e["decision_date"] for e in led)) - pd.Timedelta(days=10)
    bars, cal = _grade_bars(start)
    return {"legacy_v0": reg, **L.step_grade(bars, cal)}


def wf_record() -> dict:
    """The newest POST-REVIEW walk-forward receipt, as {roster model: {hH: {mean, n_blocks}}}.
    A pre-review (leaky) receipt is never used to seed trust."""
    fs = sorted(C.RECEIPT_DIR.glob("wf_*.json"))
    for f in reversed(fs):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        if not r.get("post_review"):
            continue
        names = {"nndist": "nn", "lgbm": "lgbm", "ridge": "ridge", "mom": "mom_12_1"}
        out: dict = {"_receipt": f.name, "_oos_path": r.get("oos_path")}
        for wm, rm in names.items():
            for hk, v in (r.get("models", {}).get(wm) or {}).items():
                ic = v.get("rank_ic") or {}
                out.setdefault(rm, {})[hk] = {"mean": ic.get("mean"), "n_blocks": ic.get("n_blocks") or 0}
        for hk, v in (r.get("magnitude") or {}).items():
            for key, rm in (("nndist_width_minus_vol", "nn_width"), ("ridge_abs_minus_vol", "ridge_abs")):
                bs = v.get(key) or {}
                if bs:
                    out.setdefault(rm, {})[hk] = {"mean": bs.get("mean"), "n_blocks": bs.get("n_blocks") or 0}
        return out
    return {"_receipt": None}


def step_trust(forward_added: bool) -> dict:
    grades = L._read_jsonl(C.FORWARD_GRADES)
    cal = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    wf = wf_record()
    trust = L.trust_table(grades, cal, wf)
    mag = L.magnitude_table(grades, cal, wf)
    prev_rows = L._read_jsonl(C.TRUST_LEDGER)
    prev = prev_rows[-1] if prev_rows else None
    ic_prev = json.loads(C.IN_CHARGE.read_text()) if C.IN_CHARGE.exists() else None
    inc = L.decide_in_charge(ic_prev, trust, forward_added=forward_added)
    C.IN_CHARGE.write_text(json.dumps(inc, indent=1, default=str))
    changes = []
    for m, hv in trust.items():
        for hk, v in hv.items():
            old = (((prev or {}).get("trust") or {}).get(m) or {}).get(hk, {})
            if old.get("trust") != v["trust"] or old.get("graded_dates") != v["graded_dates"]:
                changes.append(f"{m} {hk}: trust {old.get('trust')} -> {v['trust']} "
                               f"(graded dates {old.get('graded_dates')} -> {v['graded_dates']}, source {v['source']})")
    weights = L.weight_report(trust, (prev or {}).get("trust"), [m for m in C.DIRECTION_ROSTER if m != "zero"])
    row = {"written_utc": L._now(), "walk_forward_receipt": wf.get("_receipt"),
           "trust_rule": "forward graded blocks only; walk-forward reported, not used (amended 2026-09-29)",
           "trust": trust, "ensemble_weights": weights,
           "magnitude": mag, "in_charge": inc.get("model"), "forward_added": forward_added}
    L._append_jsonl(C.TRUST_LEDGER, [row])
    return {"trust": trust, "trust_yesterday": (prev or {}).get("trust"), "magnitude": mag,
            "ensemble_weights": weights,
            "in_charge": inc, "changes": changes or ["no change"], "walk_forward_receipt": wf.get("_receipt"),
            "_wf": wf}


def _feature_sets(df):
    from nn_lab import models as M
    from nn_lab.table import GROUPS
    groups = M.active_groups(df, list(GROUPS))
    return groups, M.feature_list(groups)


def step_fit(run_id: str, variant: str, force: bool = False) -> dict:
    """Refit the fitted rivals only when the table holds a NEW labelled grid date."""
    import joblib
    from nn_lab import models as M
    from nn_lab.nn import Trainer
    from nn_lab.splits import latest_split
    from nn_lab.table import GROUPS
    feats_all = [c for g in GROUPS.values() for c in g]
    df = pd.read_parquet(C.TABLE_PATH, columns=["date", "symbol", "on_grid"] + feats_all + [f"y_{h}" for h in H])
    cal = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    df = df[df["on_grid"]].sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    lab = {h: labelled_dates(df["date"].unique(), cal, h) for h in H}
    newest = str(lab[5][-1].date()) if len(lab[5]) else None
    state = json.loads(RIVALS_STATE.read_text()) if RIVALS_STATE.exists() else {}
    if not force and state.get("newest_labelled_grid_date") == newest and state.get("models"):
        return {"refit": False, "why": f"no new labelled grid date (newest {newest}): no training tonight",
                **{k: state[k] for k in ("models", "versions", "newest_labelled_grid_date")}}
    tr_dates = lab[5]
    groups, feats = _feature_sets(df[df["date"].isin(tr_dates)])
    Xall, xnames = M.design_matrix(df, groups)
    rdir = RIVALS_STATE.parent
    rdir.mkdir(parents=True, exist_ok=True)
    tag = f"{newest}_{run_id[-16:]}"
    models, versions = {}, {}
    for h in H:
        m = df["date"].isin(lab[h]).values & df[f"y_{h}"].notna().values
        yw = M.winsorize_by_date(df.loc[m], f"y_{h}")
        lg = M.fit_lgbm(df.loc[m, feats], yw, seed=1000 + h)
        rg = M.fit_ridge(Xall[m], yw)
        for name, obj in (("lgbm", lg), ("ridge", rg)):
            p = rdir / f"{name}_h{h}_{tag}.joblib"
            joblib.dump(obj, p)
            models.setdefault(name, {})[f"h{h}"] = str(p)
        if h in C.MAGNITUDE_HORIZONS:
            ya = np.abs(yw)
            ra = M.fit_ridge(Xall[m], ya)
            p = rdir / f"ridge_abs_h{h}_{tag}.joblib"
            joblib.dump(ra, p)
            models.setdefault("ridge_abs", {})[f"h{h}"] = str(p)
    # the network: early stopping picks the epoch count on the latest block, then a refit on
    # train+val with that count (F5.4); seeds drawn outside every recorded seed.
    f = latest_split(lab[21], cal)
    trm, vam = df["date"].isin(f.train).values, df["date"].isin(f.val).values
    allm = df["date"].isin(lab[5]).values
    Yw = np.column_stack([np.where(df["date"].isin(lab[h]).values, df[f"y_{h}"].values, np.nan) for h in H]
                         ).astype("float32")
    for j, h in enumerate(H):
        Yw[:, j] = pd.Series(Yw[:, j]).groupby(df["date"].values).transform(
            lambda s: s.clip(s.quantile(0.01), s.quantile(0.99))).to_numpy(dtype="float32")
    codes = pd.factorize(df["date"])[0]
    seeds = S.draw(N_SEEDS)
    S.record(seeds, source=run_id)
    nn_paths, fits = [], []
    for sd in seeds:
        t = Trainer(Xall.shape[1], seed=sd, variant=variant)
        r = t.fit(Xall[trm], Yw[trm], codes[trm], Xall[vam], Yw[vam], codes[vam])
        best_ep = int(np.argmax([e["val_ic"] for e in r["history"]])) + 1
        t2 = Trainer(Xall.shape[1], seed=sd, variant=variant)
        t2.fit_fixed(Xall[allm], Yw[allm], codes[allm], best_ep)
        p = rdir / f"nn_{tag}_seed{sd}.pt"
        t2.save(p)
        nn_paths.append(str(p))
        fits.append({"seed": sd, "best_epoch": best_ep, "val_ic_by_epoch": [e["val_ic"] for e in r["history"]]})
    models["nn"] = {"paths": nn_paths}
    for k in models:
        versions[k] = f"{k}-" + hashlib.sha256(json.dumps({"tag": tag, "groups": groups, "k": k},
                                                            sort_keys=True).encode()).hexdigest()[:12]
    state = {"newest_labelled_grid_date": newest, "models": models, "versions": versions,
             "groups": groups, "feats": feats, "xnames": xnames, "nn_fits": fits, "run_id": run_id,
             "written_utc": L._now()}
    RIVALS_STATE.write_text(json.dumps(state, indent=1, default=str))
    return {"refit": True, "newest_labelled_grid_date": newest, "groups_used": groups,
            "train_rows_h5": int(allm.sum()), "nn_fits": fits, "models": models, "versions": versions}


def input_columns() -> list[str]:
    """The raw columns every roster model is scored from (design_matrix ranks them per date)."""
    from nn_lab.table import GROUPS
    return [c for g in GROUPS.values() for c in g]


def score_live(live: pd.DataFrame, state: dict, *, with_nn: bool = True) -> dict:
    """Score the live rows with the fitted rivals in `state`. ONE function for the nightly
    freeze and for a re-score from the saved inputs (review C5 F2), so the two cannot drift.
    `live` must be sorted by symbol (step_freeze and the saved inputs both are)."""
    import joblib
    from nn_lab import models as M
    X, xn = M.design_matrix(live, state["groups"])
    X = X[:, [xn.index(n) for n in state["xnames"]]]
    pn = None
    if with_nn and (state.get("models", {}).get("nn") or {}).get("paths"):
        from nn_lab.nn import Trainer, ensemble_predict
        pn = ensemble_predict([Trainer.load(Path(p)) for p in state["models"]["nn"]["paths"]], X)
    scores: dict = {}
    ridge_abs: dict = {}
    for j, h in enumerate(H):
        sc = {"lgbm": joblib.load(state["models"]["lgbm"][f"h{h}"]).predict(live[state["feats"]]),
              "ridge": joblib.load(state["models"]["ridge"][f"h{h}"]).predict(X),
              "mom_12_1": live["mom_12_1"].to_numpy(dtype="float64"),
              "zero": np.zeros(len(live))}
        if pn is not None:
            sc["nn"] = pn["mean"][:, j].astype("float64")
        scores[h] = sc
        if h in C.MAGNITUDE_HORIZONS and "ridge_abs" in state["models"]:
            ridge_abs[h] = joblib.load(state["models"]["ridge_abs"][f"h{h}"]).predict(X)
    return {"X": X, "pn": pn, "scores": scores, "ridge_abs": ridge_abs}


def frozen_inputs_path(decision_date, run_id: str, frozen_dir: Path | None = None) -> Path:
    return Path(frozen_dir or C.FROZEN_DIR) / str(pd.Timestamp(decision_date).date()) / f"inputs_{run_id}.parquet"


def save_frozen_inputs(live: pd.DataFrame, *, decision_date, run_id: str, state: dict,
                       frozen_dir: Path | None = None, ledger: Path | None = None, note: str | None = None) -> dict:
    """The exact rows a night's forecasts were scored on, as ONE immutable parquet beside the
    frozen forecast files, its sha256 in `frozen_inputs_ledger.jsonl` (review C5 F2: the
    table replaces yesterday's live rows, so without this the inputs of a frozen forecast
    were gone within 24 h). Exclusive create: an existing file is verified, never rewritten."""
    path = frozen_inputs_path(decision_date, run_id, frozen_dir)
    dd = str(pd.Timestamp(decision_date).date())
    led = Path(ledger or C.FROZEN_INPUTS_LEDGER)
    cols = ["date", "symbol"] + [c for c in input_columns() if c in live.columns]
    df = live[cols].sort_values("symbol", kind="mergesort").reset_index(drop=True)
    rel = str(path.relative_to(C.REPO)).replace("\\", "/") if str(path).startswith(str(C.REPO)) else path.name
    if path.exists():
        return {"status": "ALREADY_SAVED", "file": rel, "sha256": sha256_file(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    with open(tmp, "rb") as src, open(path, "xb") as dst:
        dst.write(src.read())
    tmp.unlink(missing_ok=True)
    sha = sha256_file(path)
    entry = {"decision_date": dd, "run_id": run_id, "file": rel, "sha256": sha, "rows": int(len(df)),
             "columns": len(cols), "model_versions": state.get("versions"),
             "xnames_sha256": hashlib.sha256(json.dumps(state.get("xnames")).encode()).hexdigest()[:16],
             "written_utc": L._now(), **({"note": note} if note else {})}
    L._append_jsonl(led, [entry])
    return {"status": "SAVED", **entry}


def rescore_from_inputs(path: Path, state: dict, *, with_nn: bool = True) -> dict:
    """Re-score a frozen night from its saved inputs (the audit of `save_frozen_inputs`)."""
    return score_live(pd.read_parquet(path), state, with_nn=with_nn)


def step_freeze(run_id: str, trust: dict, mag: dict, wf: dict) -> dict:
    """Freeze every roster model, the ensemble and the size forecast for the newest date."""
    state = json.loads(RIVALS_STATE.read_text())
    feats_all = input_columns()
    tab = pd.read_parquet(C.TABLE_PATH, columns=["date", "symbol"] + feats_all)
    dd = tab["date"].max()
    live = tab[tab["date"] == dd].sort_values("symbol", kind="mergesort").reset_index(drop=True)
    del tab
    scored = score_live(live, state)
    pn = scored["pn"]
    sym = live["symbol"].to_numpy()
    books = books_symbols()
    out: dict = {"decision_date": str(dd.date()), "names": int(len(live)),
                 "in_frozen_book": int(np.isin(sym, list(books)).sum()), "files": {}}
    scores: dict[str, dict[int, np.ndarray]] = {}

    in_book = np.isin(sym, list(books))

    def frame(h, **cols):
        return pd.DataFrame({"symbol": sym, "horizon": h, **cols, "in_frozen_book": in_book})

    parts = {m: [] for m in C.DIRECTION_ROSTER}
    mag_parts = {m: [] for m in C.MAGNITUDE_ROSTER}
    for j, h in enumerate(H):
        q = pn["q"][:, j, :]
        s_nn = scored["scores"][h]["nn"]
        parts["nn"].append(frame(h, score=s_nn, prob=pn["prob"][:, j], q05=q[:, 0], q25=q[:, 1], q50=q[:, 2],
                                 q75=q[:, 3], q95=q[:, 4]))
        s_lg = scored["scores"][h]["lgbm"]
        s_rg = scored["scores"][h]["ridge"]
        s_mo = scored["scores"][h]["mom_12_1"]
        parts["lgbm"].append(frame(h, score=s_lg))
        parts["ridge"].append(frame(h, score=s_rg))
        parts["mom_12_1"].append(frame(h, score=s_mo))
        parts["zero"].append(frame(h, score=np.zeros(len(live))))
        scores[h] = {"nn": s_nn, "lgbm": s_lg, "ridge": s_rg, "mom_12_1": s_mo, "zero": np.zeros(len(live))}
        if h in C.MAGNITUDE_HORIZONS:
            vol = live["vol_63"].to_numpy(dtype="float64") * np.sqrt(h / 252.0) * L.SQRT_2_PI
            ra = scored["ridge_abs"][h]
            nw = (q[:, 4] - q[:, 0]) / 3.29 * L.SQRT_2_PI
            mag_parts["trailing_vol"].append(frame(h, pred_abs=vol))
            mag_parts["ridge_abs"].append(frame(h, pred_abs=np.clip(ra, 1e-4, None)))
            mag_parts["nn_width"].append(frame(h, pred_abs=nw))
    members = _size_member_parts(live, frame)
    for m, mp in members.get("parts", {}).items():
        mag_parts[m] = mp
    out["size_members"] = {"roster": list(members.get("parts", {})), "coef": members.get("coef")}
    mag_parts = {m: v for m, v in mag_parts.items() if v}
    ver = state["versions"]
    for m in C.DIRECTION_ROSTER:
        out["files"][m] = L.freeze(pd.concat(parts[m], ignore_index=True), model=m, decision_date=dd,
                                   model_version=ver.get(m, m), run_id=run_id, kind="direction")
    for m in C.MAGNITUDE_ROSTER:
        if m not in mag_parts:
            continue
        out["files"][m] = L.freeze(pd.concat(mag_parts[m], ignore_index=True), model=m, decision_date=dd,
                                   model_version=ver.get(m, members.get("versions", {}).get(m, m)),
                                   run_id=run_id, kind="magnitude")
    ens, weights = [], {}
    for h in H:
        s, w = L.ensemble_scores(scores[h], trust, h)
        weights[f"h{h}"] = w
        ens.append(frame(h, score=s))
    out["files"]["ensemble"] = L.freeze(pd.concat(ens, ignore_index=True), model="ensemble", decision_date=dd,
                                        model_version="ens-" + hashlib.sha256(json.dumps(weights, sort_keys=True)
                                                                              .encode()).hexdigest()[:12],
                                        run_id=run_id, kind="direction", extra={"weights": weights})
    out["ensemble_weights"] = weights
    out["size_forecast"] = write_size_forecast(dd, sym, mag_parts, mag, wf, run_id)
    # the exact scored rows, beside the frozen files (review C5 F2), with a re-score check
    inp = save_frozen_inputs(live, decision_date=dd, run_id=run_id, state=state)
    if inp.get("status") in ("SAVED", "ALREADY_SAVED"):
        re_ = rescore_from_inputs(frozen_inputs_path(dd, run_id), state)
        inp["rescore_check"] = {f"{m}_h{h}": bool(np.allclose(re_["scores"][h][m], scored["scores"][h][m],
                                                              rtol=1e-5, atol=1e-7, equal_nan=True))
                                for h in H for m in scored["scores"][h] if m in re_["scores"][h]}
        inp["rescore_reproduces_scores"] = all(inp["rescore_check"].values())
    out["frozen_inputs"] = inp
    top = pd.DataFrame({"symbol": sym, "ens21": ens[H.index(21)]["score"].to_numpy()})
    out["ensemble_top10_h21"] = top.nlargest(10, "ens21")["symbol"].tolist()
    return out


def _size_member_parts(live: pd.DataFrame, frame) -> dict:
    """The size members (nn_lab/size_members.py) for the newest date, when the flag is on.
    They are MAGNITUDE models: frozen and graded like trailing vol, weighted only by forward
    graded blocks (prior 0). A failure here never fails the night: the members are skipped
    and the reason is on the receipt."""
    from nn_lab import size_members as SM
    roster = SM.member_roster()
    if not roster:
        return {}
    try:
        pr = SM.nightly_member_predictions(live)
    except Exception as e:                                     # noqa: BLE001
        return {"coef": {"error": repr(e)[:300]}}
    parts, versions = {}, {}
    for m in roster:
        if m not in pr:
            continue
        parts[m] = [frame(h, pred_abs=np.clip(pr[m][h], 1e-4, None)) for h in C.MAGNITUDE_HORIZONS]
        versions[m] = f"{m}-" + hashlib.sha256(json.dumps({k: v for k, v in pr["_coef"].items()
                                                           if k.startswith(m)}, sort_keys=True)
                                               .encode()).hexdigest()[:12]
    return {"parts": parts, "coef": pr.get("_coef"), "versions": versions}


def step_size_members() -> dict:
    """Rebuild the size members' sidecar (earnings expected in the window, text residual) for
    every row of the table, from releases and news known strictly before each row's t."""
    from nn_lab import size_members as SM
    try:
        return SM.build()
    except Exception as e:                                     # noqa: BLE001
        # never fails the night: the freeze step then scores from the previous sidecar
        # (a live row it lacks reads "no earnings expected") and says so here
        return {"status": "SIDECAR_REBUILD_FAILED", "error": repr(e)[:300]}


def _conformal(model: str, h: int, wf: dict) -> dict:
    """Interval scale for `model` at h: forward rows when there are enough, else walk-forward."""
    rows_p, rows_x = [], []
    for e in L._read_jsonl(C.FROZEN_LEDGER):
        if e["model"] != model:
            continue
        op = C.OUTCOMES_DIR / f"{e['decision_date']}_h{h}.parquet"
        if not op.exists() or L.verify(e) != "OK":
            continue
        fz = pd.read_parquet(L._resolve(e["file"]))
        o = pd.read_parquet(op)
        mm = fz[fz["horizon"] == h].merge(o, on="symbol")
        rows_p.append(mm["pred_abs"].to_numpy())
        rows_x.append(mm["excess"].to_numpy())
    n_fwd = int(sum(len(a) for a in rows_p))
    if n_fwd >= C.CONFORMAL_MIN_ROWS:
        return {**L.conformal_factors(np.concatenate(rows_p), np.concatenate(rows_x)), "source": "forward"}
    op = wf.get("_oos_path")
    if op and Path(op).exists():
        o = pd.read_parquet(op)
        y = o.get(f"y_{h}")
        col = {"trailing_vol": f"vol_sigma_{h}", "ridge_abs": f"ridgeabs_score_{h}",
               "nn_width": None}.get(model)      # a size member has no walk-forward column
        if model == "nn_width" and f"nndist_q95_{h}" in o:
            pa = (o[f"nndist_q95_{h}"] - o[f"nndist_q05_{h}"]) / 3.29 * L.SQRT_2_PI
        elif col and col in o:
            pa = o[col] * (L.SQRT_2_PI if model == "trailing_vol" else 1.0)
        else:
            pa = None
        if pa is not None and y is not None:
            return {**L.conformal_factors(pa.to_numpy(), y.to_numpy()), "source": "walk_forward",
                    "forward_rows_so_far": n_fwd}
    return {"c50": Z_FALLBACK[0], "c90": Z_FALLBACK[1], "source": "gaussian_fallback", "forward_rows_so_far": n_fwd}


Z_FALLBACK = (L.Z50 / L.SQRT_2_PI, L.Z90 / L.SQRT_2_PI)


def write_size_forecast(dd, sym, mag_parts, mag, wf, run_id) -> dict:
    """ONE file per night: ticker, expected |excess move| over 5 and 21 sessions, a 90% and a
    50% interval (conformal), the model and its trust. It forecasts SIZE, not direction."""
    C.SIZE_DIR.mkdir(parents=True, exist_ok=True)
    p = C.SIZE_DIR / f"size_{pd.Timestamp(dd).date()}.parquet"
    meta = {"decision_date": str(pd.Timestamp(dd).date()), "run_id": run_id, "written_utc": L._now(),
            "what": "expected ABSOLUTE excess move (vs the cross-sectional median) and a symmetric interval; "
                    "it says NOTHING about direction", "by_horizon": {}}
    df = pd.DataFrame({"ticker": sym})
    for h in C.MAGNITUDE_HORIZONS:
        model, why = L.choose_magnitude(mag, h)
        pa = pd.concat(mag_parts[model], ignore_index=True)
        pa = pa[pa["horizon"] == h]["pred_abs"].to_numpy()
        cf = _conformal(model, h, wf)
        df[f"exp_abs_move_{h}"] = pa
        df[f"lo90_{h}"] = -cf["c90"] * pa
        df[f"hi90_{h}"] = cf["c90"] * pa
        df[f"lo50_{h}"] = -cf["c50"] * pa
        df[f"hi50_{h}"] = cf["c50"] * pa
        df[f"model_{h}"] = model
        df[f"trust_improvement_over_vol_{h}"] = (mag.get(model, {}).get(f"h{h}", {})
                                                  .get("improvement_over_vol") or 0.0)
        meta["by_horizon"][f"h{h}"] = {"model": model, "why": why, "conformal": cf}
    if p.exists():
        return {"status": "ALREADY_FROZEN", "file": str(p), "sha256": sha256_file(p), **meta}
    tmp = p.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    with open(tmp, "rb") as src, open(p, "xb") as dst:
        dst.write(src.read())
    tmp.unlink(missing_ok=True)
    meta.update({"status": "FROZEN", "file": str(p), "sha256": sha256_file(p), "rows": int(len(df))})
    p.with_suffix(".json").write_text(json.dumps(meta, indent=1, default=str))
    return meta


# ─────────────────────────────── driver ──────────────────────────────────────

def last_receipt() -> dict | None:
    fs = sorted(C.RECEIPT_DIR.glob("nightly_*.json"))
    for f in reversed(fs):
        try:
            return json.loads(f.read_text())
        except Exception:
            continue
    return None


def _resume_state(now: datetime) -> dict:
    """A failed night is resumed ONLY on the same UTC day (review F5: a resume reused the
    previous night's `done.append` without checking the date)."""
    if not STATE_PATH.exists():
        return {}
    st = json.loads(STATE_PATH.read_text())
    if st.get("complete", True) is False and str(st.get("run_id", ""))[8:16] == f"{now:%Y%m%d}":
        return st
    return {}


def main(time_box_min: float = C.NIGHT_TIME_BOX_MIN, variant: str | None = None) -> dict:
    t0 = time.time()
    now = datetime.now(timezone.utc)
    run_id = f"nightly_{now:%Y%m%dT%H%M%SZ}"
    C.OUT.mkdir(parents=True, exist_ok=True)
    C.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    rec: dict = {"artefact": "NN_LAB_NIGHTLY", "schema": 2, "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
                 "broker_authority": "NONE: writes predictions, never orders",
                 "started_utc": now.isoformat(timespec="seconds")}
    rec["table_before"] = table_size()       # printed BEFORE any rebuild (the 2026-09-26 lesson)
    why = refuse_reason()
    if why:
        rec.update({"status": "REFUSED", "refused": why,
                    "evidence": f"NO_NEW_EVIDENCE: refused before any step ({why})"})
        (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(rec, indent=1, default=str))
        return rec
    LOCK_PATH.write_text(json.dumps({"pid": os.getpid(), "run_id": run_id}))
    st = _resume_state(now)
    done = dict(st.get("done", {})) if st else {}
    if st:
        rec["resumed_from"] = st.get("run_id")
    state = {"run_id": run_id, "complete": False, "done": done}
    variant = variant or _variant_choice()
    rec["variant"] = variant
    ran_now: set[str] = set()
    ctx: dict = {}
    from nn_lab import size_members as _SM
    steps = (("append", lambda: step_append(run_id)),) + ((("size_members", step_size_members),) if _SM.member_roster() else ()) + (
             ("grade", step_grade),
             # only a DIRECTION-roster grade is forward evidence for the model in charge (F8):
             # the legacy v0 file and the magnitude models never move it
             ("trust", lambda: step_trust(forward_added=(rec.get("grade") or {})
                                          .get("graded_now_direction_roster", 0) > 0)),
             ("fit", lambda: step_fit(run_id, variant)),
             ("freeze", lambda: step_freeze(run_id, ctx["trust"]["trust"], ctx["trust"]["magnitude"],
                                            ctx["trust"]["_wf"])))
    try:
        for name, fn in steps:
            if name in done and name not in ("trust",):
                rec[name] = done[name] | {"resumed": True}
                continue
            if (time.time() - t0) / 60 > time_box_min:
                rec.update({"status": "TIMEOUT", "stopped_before": name})
                break
            res = fn()
            ran_now.add(name)
            if name == "trust":
                ctx["trust"] = res
                res = {k: v for k, v in res.items() if k != "_wf"}
            rec[name] = res
            done[name] = res
            STATE_PATH.write_text(json.dumps(state, indent=1, default=str))
        else:
            state["complete"] = True
            STATE_PATH.write_text(json.dumps(state, indent=1, default=str))
    except TableShrink as e:
        # a genuine shrink (or a moved frozen membership) is a REFUSAL with its reason, and the
        # stored table is untouched; a vendor re-adjustment no longer lands here (membership.py)
        rec.update({"status": "REFUSED", "refused": f"TABLE_SHRINK: {e}"})
        STATE_PATH.write_text(json.dumps(state, indent=1, default=str))
    except Exception as e:
        rec.update({"status": "FAILED", "error": repr(e)})
        STATE_PATH.write_text(json.dumps(state, indent=1, default=str))
    finally:
        LOCK_PATH.unlink(missing_ok=True)
    ap = rec.get("append", {}) if "append" in ran_now else {}
    new_rows = max(0, int(ap.get("rows_added", 0))) + max(0, int(ap.get("labels_filled", 0)))
    new_rows += int((rec.get("grade") or {}).get("graded_now", 0)) if "grade" in ran_now else 0
    prev = last_receipt()
    table_last = pd.Timestamp((rec.get("append") or {}).get("new_max_date") or "1970-01-01")
    closed = last_closed_weekday(now)
    rec["bars"] = {"table_last_session": str(table_last.date()), "last_closed_weekday": str(closed.date()),
                   "note": "weekday calendar: the day after a US holiday can read STALE_BARS falsely"}
    rec["new_rows_since_last_run"] = new_rows
    rec["previous_run"] = prev.get("run_id") if prev else None
    rec["degraded_reasons"] = list(((rec.get("append") or {}).get("membership") or {}).get("degraded_reasons") or [])
    rec.setdefault("status", night_status(new_rows, stale=table_last < closed, degraded=rec["degraded_reasons"]))
    rec["per_model"] = _per_model_lines(rec)
    rec["table_after"] = table_size()
    rec["evidence"] = evidence_line(rec)
    try:
        rec["tournament"] = tournament()
    except Exception as e:                                      # noqa: BLE001
        rec["tournament"] = {"status": "UNAVAILABLE", "error": repr(e)[:300]}
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def table_size(path: Path | None = None) -> dict | None:
    """Rows, grid rows, grid dates, labels per horizon of the STORED table (None if absent)."""
    p = Path(path or C.TABLE_PATH)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["date", "on_grid"] + [f"y_{h}" for h in H])
        return MB.table_counts(df)
    except Exception as e:                                      # noqa: BLE001
        return {"error": repr(e)[:200]}


def evidence_line(rec: dict) -> str:
    """What tonight added to what the lab knows, or an explicit NO_NEW_EVIDENCE reason."""
    if rec.get("status") in ("REFUSED", "FAILED", "TIMEOUT"):
        why = rec.get("refused") or rec.get("error") or rec.get("stopped_before")
        return f"NO_NEW_EVIDENCE: night {rec.get('status')} ({why})"
    parts = []
    fit = rec.get("fit") or {}
    if fit.get("refit"):
        parts.append(f"REFIT on newest labelled grid date {fit.get('newest_labelled_grid_date')}")
    g = int((rec.get("grade") or {}).get("graded_now", 0) or 0)
    if g:
        parts.append(f"{g} frozen forecasts graded forward")
    lf = int((rec.get("append") or {}).get("labels_filled", 0) or 0)
    if lf:
        parts.append(f"{lf:,} labels matured")
    deg = rec.get("degraded_reasons") or []
    tail = ("; DEGRADED: " + "; ".join(deg)) if deg else ""
    if not parts:
        return "NO_NEW_EVIDENCE: " + (fit.get("why") or "no refit") + "; 0 forecasts graded; 0 labels matured" + tail
    return "; ".join(parts) + tail


TOURNAMENT_MODELS = {"nndist": "nn", "lgbm": "lgbm", "ridge": "ridge", "mom": "mom_12_1"}


def _newest_post_review_wf() -> tuple[str, dict] | None:
    for f in reversed(sorted(C.RECEIPT_DIR.glob("wf_*.json"))):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        if r.get("post_review"):
            return f.name, r
    return None


def _weight_sentence() -> str:
    """One plain sentence from the trust ledger: has any model earned forward weight?"""
    rows = L._read_jsonl(C.TRUST_LEDGER) if C.TRUST_LEDGER.exists() else []
    last = rows[-1] if rows else {}
    w = []
    for hk, ew in (last.get("ensemble_weights") or {}).items():
        for m, v in (ew.get("models") or {}).items():
            w.append(float(v.get("weight") or 0.0))
    if not w or max(w) <= 0:
        return ("no model has earned forward weight; ensemble weights are zero; the book holds the neutral "
                "(no-view) sleeve")
    return f"forward weights are non-zero (max {max(w):.3f}); see trust.ensemble_weights"


def _val_gap(r: dict) -> dict:
    """The NN's in-sample validation IC (best epoch, mean over seeds and folds) beside its
    walk-forward test IC: the overfit the tournament exists to expose."""
    vals = []
    for f in r.get("folds") or []:
        for fit in f.get("nn_dist") or []:
            ep = fit.get("val_ic_by_epoch") or []
            if ep:
                vals.append(max(ep))
    wf = {hk: (v.get("rank_ic") or {}).get("mean") for hk, v in ((r.get("models") or {}).get("nndist") or {}).items()}
    return {"nn_val_ic_best_epoch_mean": round(float(np.mean(vals)), 5) if vals else None,
            "nn_walk_forward_test_ic": wf,
            "note": "validation IC is the early-stopping block's mean over horizons (in-sample for the epoch "
                    "choice); the test IC is out of sample"}


def tournament() -> dict:
    """The NN beside ridge and LightGBM on the SAME folds (owner 2026-10-06: complexity
    must earn its place). Two sources, neither refit tonight:
      walk_forward: the newest post-review receipt -- the same purged expanding folds with a
                    63-session embargo (splits.py / walkforward.py) for every model;
      forward:      graded frozen forecasts, restricted to decision dates on which EVERY
                    model in the comparison was graded (the same forward fold set).
    The verdict per horizon is NN minus the better of ridge / LightGBM."""
    out: dict = {"rule": "the NN earns its place at h only if its rank IC beats max(ridge, lgbm) by more "
                         "than one SE of the difference; otherwise the simpler model stays"}
    wf = _newest_post_review_wf()
    if wf is None:
        out["walk_forward"] = {"status": "NO_POST_REVIEW_RECEIPT"}
    else:
        name, r = wf
        rows: dict = {}
        for wm, rm in TOURNAMENT_MODELS.items():
            for hk, v in (r.get("models", {}).get(wm) or {}).items():
                ic = v.get("rank_ic") or {}
                tp = v.get("top20_minus_random_net") or {}
                rows.setdefault(hk, {})[rm] = {"rank_ic": ic.get("mean"), "se": ic.get("se"), "t": ic.get("t"),
                                               "n_blocks": ic.get("n_blocks"),
                                               "t_nonoverlapping": ic.get("t_strict"),
                                               "n_blocks_nonoverlapping": ic.get("n_blocks_nonoverlapping"),
                                               "rank_ic_by_year": v.get("rank_ic_by_year"),
                                               "rank_ic_loyo_worst": v.get("rank_ic_loyo_worst"),
                                               "top20_minus_random_net": tp.get("mean"), "top20_t": tp.get("t")}
        verdict = {}
        for hk, mv in rows.items():
            nn = mv.get("nn") or {}
            # review C5 F7: the single-column 12-1 momentum is in the baseline set
            base = {m: mv[m] for m in ("ridge", "lgbm", "mom_12_1") if (mv.get(m) or {}).get("rank_ic") is not None}
            if nn.get("rank_ic") is None or not base:
                continue
            best_name = max(base, key=lambda m: base[m]["rank_ic"])
            best = base[best_name]
            diff = nn["rank_ic"] - best["rank_ic"]
            # an upper bound: the two folds' errors are positively correlated, so the true SE is smaller
            se = float(np.hypot(nn.get("se") or 0.0, best.get("se") or 0.0))
            verdict[hk] = {"nn_minus_best_baseline": round(diff, 5), "best_baseline": best_name,
                           "baselines_compared": sorted(base),
                           "se_of_difference_upper_bound": round(se, 5),
                           "verdict": ("NN EARNS ITS PLACE" if diff > se else
                                       "NN DOES NOT BEAT the simpler baseline: complexity has not earned its place")}
        written = pd.Timestamp(r.get("written_utc")) if r.get("written_utc") else None
        age = (round((pd.Timestamp.now(tz="UTC") - written).total_seconds() / 86400, 2)
               if written is not None else None)
        tonight_sha = sha256_file(C.TABLE_PATH) if C.TABLE_PATH.exists() else None
        out["walk_forward"] = {"receipt": name, "folds": len(r.get("folds") or []),
                               "table_sha256_of_that_run": r.get("table_sha256"),
                               "written_utc": r.get("written_utc"), "age_days": age,
                               "same_table_as_tonight": bool(tonight_sha and tonight_sha == r.get("table_sha256")),
                               "use_crsp_deaths_in_that_run": r.get("use_crsp_deaths"),
                               "note": ("printed from the receipt, not refit tonight; computed on the table "
                                        "as it stood then" + ("" if r.get("use_crsp_deaths") else
                                        " -- BEFORE the CRSP-deaths rebuild (a different survivor set)")),
                               "in_sample_val_ic_vs_walk_forward": _val_gap(r),
                               "by_horizon": rows, "verdict": verdict}
    out["forward_weight_sentence"] = _weight_sentence()
    g = pd.DataFrame(L._read_jsonl(C.FORWARD_GRADES))
    want = list(TOURNAMENT_MODELS.values())
    if not len(g) or "rank_ic" not in g.columns:
        out["forward"] = {"status": "NO_FORWARD_GRADES_YET", "n_rows": int(len(g))}
        return out
    fwd: dict = {}
    for h in H:
        gh = g[(g["horizon"] == h) & g["model"].isin(want) & g["rank_ic"].notna()]
        if not len(gh):
            continue
        per = gh.pivot_table(index="decision_date", columns="model", values="rank_ic", aggfunc="first")
        have = [m for m in want if m in per.columns]
        common = per[have].dropna()
        fwd[f"h{h}"] = {"common_decision_dates": int(len(common)),
                        "mean_rank_ic": {m: round(float(common[m].mean()), 5) for m in have} if len(common) else {},
                        "note": "mean rank IC over decision dates graded for every listed model"}
    out["forward"] = fwd or {"status": "NO_FORWARD_GRADES_YET", "n_rows": int(len(g))}
    return out


def _per_model_lines(rec: dict) -> list[str]:
    """Per model at h21: forward graded blocks, trust, ensemble WEIGHT and what moved it."""
    tr = (rec.get("trust") or {}).get("trust") or {}
    ty = (rec.get("trust") or {}).get("trust_yesterday") or {}
    ew = (((rec.get("trust") or {}).get("ensemble_weights") or {}).get("h21") or {})
    wm = ew.get("models") or {}
    out = []
    for m, hv in tr.items():
        v = hv.get("h21", {})
        y = (ty.get(m) or {}).get("h21", {})
        w = wm.get(m) or {}
        out.append(f"{m:10s} h21 forward graded blocks {v.get('n_forward_blocks')} "
                   f"({v.get('graded_dates')} dates) | trust today {v.get('trust')} yesterday {y.get('trust')} "
                   f"| weight {w.get('weight', 'n/a')} (was {w.get('weight_yesterday', 'n/a')}) "
                   f"| moved by: {w.get('moved_by', 'n/a')} | source {v.get('source')}")
    if ew:
        out.append(f"neutral (no-view) sleeve h21 {ew.get('neutral')}; scaled down to 1: {ew.get('scaled_down_to_1')}")
    return out


def _variant_choice() -> str:
    p = C.OUT / "variant_choice.json"
    if p.exists():
        return json.loads(p.read_text())["variant"]
    return "dist"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-box-min", type=float, default=C.NIGHT_TIME_BOX_MIN)
    ap.add_argument("--variant", default=None)
    a = ap.parse_args()
    r = main(a.time_box_min, a.variant)
    print(json.dumps({k: v for k, v in r.items() if k not in ("trust",)}, indent=1, default=str)[:20000])
    sys.exit(0 if r.get("status") in ("OK", "DEGRADED", "STALE_BARS") else 2)
