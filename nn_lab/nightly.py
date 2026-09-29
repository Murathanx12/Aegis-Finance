"""The nightly loop.

    python -m nn_lab.nightly [--time-box-min 90]

Rebuilt 2026-09-29 after `docs/reviews/REVIEW_2026-09-29_NN_LAB.md`. Each night, in order,
each step checkpointed so a crashed night RESUMES (same UTC day only):

  a. APPEND   rebuild the table's tail from the refreshed bars (+ side groups). The shrink
              guard compares the TABLE: every stored grid row and every stored label must
              still be there (review F6: comparing today's cross-section with yesterday's
              refused ordinary weekdays).
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


class TableShrink(RuntimeError):
    """A rebuild would lose a stored grid row or a stored label."""


# ─────────────────────────── small pure helpers (tested) ─────────────────────

def night_status(new_rows_since_last_run: int, refused: str | None = None, *, stale: bool = False) -> str:
    if refused:
        return "REFUSED"
    if stale:
        return "STALE_BARS"
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


def shrink_check(old: pd.DataFrame, new: pd.DataFrame, labels=tuple(f"y_{h}" for h in H)) -> dict:
    """Compare the TABLE, not today's cross-section. RAISE if a stored grid row or a stored
    label is gone. Yesterday's off-grid live rows may go (today's replace them)."""
    og = old[old["on_grid"]] if "on_grid" in old else old
    ng = new[new["on_grid"]] if "on_grid" in new else new
    ok = pd.MultiIndex.from_frame(og[["date", "symbol"]])
    nk = pd.MultiIndex.from_frame(ng[["date", "symbol"]])
    lost = ok.difference(nk)
    if len(lost):
        ex = [(str(d.date()), s) for d, s in list(lost)[:3]]
        raise TableShrink(f"table would LOSE {len(lost):,} stored grid rows, e.g. {ex}; refused, original kept")
    lost_dates = set(og["date"]) - set(ng["date"])
    if lost_dates:
        raise TableShrink(f"table would LOSE {len(lost_dates)} grid dates; refused, original kept")
    a = og.set_index(["date", "symbol"])[list(labels)].notna()
    b = ng.set_index(["date", "symbol"])[list(labels)].notna().reindex(a.index, fill_value=False)
    lost_lab = int((a & ~b).to_numpy().sum())
    if lost_lab:
        raise TableShrink(f"table would LOSE {lost_lab:,} stored labels; refused, original kept")
    return {"grid_rows_kept": int(len(ok)), "grid_rows_new": int(len(nk.difference(ok))),
            "labels_filled": int((~a & b).to_numpy().sum()) if len(a) else 0}


def labelled_dates(dates, cal: pd.DatetimeIndex, h: int) -> pd.DatetimeIndex:
    """Grid dates whose h-session label window has ELAPSED on the calendar (review F5.5:
    'y is not null' kept dates whose only labels were a few delisted names)."""
    d = pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates)))
    pos = np.searchsorted(cal.values, d.values)
    return pd.DatetimeIndex(np.sort(d[pos + 1 + h < len(cal)]))


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

def step_append() -> dict:
    """Rebuild the tail (every grid date from the first with a pending label) + the newest session."""
    from nn_lab import table as T
    tab = pd.read_parquet(C.TABLE_PATH)
    old_max = tab["date"].max()
    cal_old = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    bars = T.load_bars([C.BARS_DEEP, C.BARS_RECENT, C.BARS_DELISTED], start="2025-01-01",
                       extend_only=[C.BARS_RECENT])
    cal_new = T.session_calendar(bars)
    cal = pd.DatetimeIndex(np.union1d(cal_old.values, cal_new.values))
    grid = cal[T.grid_mask(cal)]
    pending = tab.loc[tab["on_grid"] & tab[[f"y_{h}" for h in H]].isna().any(axis=1), "date"]
    tail_start = pending.min() if len(pending) else old_max
    tail_start = max(tail_start, pd.Timestamp("2026-01-15"))   # recent bars need 252 sessions of lookback
    keep = grid[grid >= tail_start]
    rows = T.price_rows(bars, cal, keep_dates=keep, keep_last=True)
    del bars
    rows = T.add_excess_labels(rows)
    rows["on_grid"] = rows["date"].isin(set(grid))
    rows = T.attach_side_groups(rows)
    T.assert_pit(rows)
    new = pd.concat([tab[tab["date"] < tail_start], rows[tab.columns.intersection(rows.columns)]],
                    ignore_index=True)
    chk = shrink_check(tab, new)
    tmp = C.TABLE_PATH.with_suffix(".tmp.parquet")
    new.to_parquet(tmp, index=False)
    if len(pd.read_parquet(tmp, columns=["date"])) != len(new):
        raise RuntimeError("table write verification failed; original kept")
    os.replace(tmp, C.TABLE_PATH)
    pd.DataFrame({"date": cal}).to_parquet(C.TABLE_PATH.parent / "calendar.parquet", index=False)
    new_dates = sorted(set(rows["date"]) - set(tab["date"]))
    return {"old_max_date": str(old_max.date()), "new_max_date": str(new["date"].max().date()),
            "tail_start": str(tail_start.date()), "rows_rebuilt": int(len(rows)),
            "rows_added": int((rows["date"] > old_max).sum()), "new_dates": [str(d.date()) for d in new_dates],
            "labels_filled": chk["labels_filled"], "grid_rows_kept": chk["grid_rows_kept"],
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
    row = {"written_utc": L._now(), "walk_forward_receipt": wf.get("_receipt"), "trust": trust,
           "magnitude": mag, "in_charge": inc.get("model"), "forward_added": forward_added}
    L._append_jsonl(C.TRUST_LEDGER, [row])
    return {"trust": trust, "trust_yesterday": (prev or {}).get("trust"), "magnitude": mag,
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


def step_freeze(run_id: str, trust: dict, mag: dict, wf: dict) -> dict:
    """Freeze every roster model, the ensemble and the size forecast for the newest date."""
    import joblib
    from nn_lab import models as M
    from nn_lab.nn import Trainer, ensemble_predict
    from nn_lab.table import GROUPS
    state = json.loads(RIVALS_STATE.read_text())
    feats_all = [c for g in GROUPS.values() for c in g]
    tab = pd.read_parquet(C.TABLE_PATH, columns=["date", "symbol"] + feats_all)
    dd = tab["date"].max()
    live = tab[tab["date"] == dd].sort_values("symbol").reset_index(drop=True)
    X, xn = M.design_matrix(live, state["groups"])
    X = X[:, [xn.index(n) for n in state["xnames"]]]
    sym = live["symbol"].to_numpy()
    books = books_symbols()
    out: dict = {"decision_date": str(dd.date()), "names": int(len(live)),
                 "in_frozen_book": int(np.isin(sym, list(books)).sum()), "files": {}}
    scores: dict[str, dict[int, np.ndarray]] = {}

    in_book = np.isin(sym, list(books))

    def frame(h, **cols):
        return pd.DataFrame({"symbol": sym, "horizon": h, **cols, "in_frozen_book": in_book})

    trs = [Trainer.load(Path(p)) for p in state["models"]["nn"]["paths"]]
    pn = ensemble_predict(trs, X)
    parts = {m: [] for m in C.DIRECTION_ROSTER}
    mag_parts = {m: [] for m in C.MAGNITUDE_ROSTER}
    for j, h in enumerate(H):
        q = pn["q"][:, j, :]
        s_nn = pn["mean"][:, j].astype("float64")
        parts["nn"].append(frame(h, score=s_nn, prob=pn["prob"][:, j], q05=q[:, 0], q25=q[:, 1], q50=q[:, 2],
                                 q75=q[:, 3], q95=q[:, 4]))
        s_lg = joblib.load(state["models"]["lgbm"][f"h{h}"]).predict(live[state["feats"]])
        s_rg = joblib.load(state["models"]["ridge"][f"h{h}"]).predict(X)
        s_mo = live["mom_12_1"].to_numpy(dtype="float64")
        parts["lgbm"].append(frame(h, score=s_lg))
        parts["ridge"].append(frame(h, score=s_rg))
        parts["mom_12_1"].append(frame(h, score=s_mo))
        parts["zero"].append(frame(h, score=np.zeros(len(live))))
        scores[h] = {"nn": s_nn, "lgbm": s_lg, "ridge": s_rg, "mom_12_1": s_mo, "zero": np.zeros(len(live))}
        if h in C.MAGNITUDE_HORIZONS:
            vol = live["vol_63"].to_numpy(dtype="float64") * np.sqrt(h / 252.0) * L.SQRT_2_PI
            ra = joblib.load(state["models"]["ridge_abs"][f"h{h}"]).predict(X)
            nw = (q[:, 4] - q[:, 0]) / 3.29 * L.SQRT_2_PI
            mag_parts["trailing_vol"].append(frame(h, pred_abs=vol))
            mag_parts["ridge_abs"].append(frame(h, pred_abs=np.clip(ra, 1e-4, None)))
            mag_parts["nn_width"].append(frame(h, pred_abs=nw))
    ver = state["versions"]
    for m in C.DIRECTION_ROSTER:
        out["files"][m] = L.freeze(pd.concat(parts[m], ignore_index=True), model=m, decision_date=dd,
                                   model_version=ver.get(m, m), run_id=run_id, kind="direction")
    for m in C.MAGNITUDE_ROSTER:
        out["files"][m] = L.freeze(pd.concat(mag_parts[m], ignore_index=True), model=m, decision_date=dd,
                                   model_version=ver.get(m, m), run_id=run_id, kind="magnitude")
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
    top = pd.DataFrame({"symbol": sym, "ens21": ens[H.index(21)]["score"].to_numpy()})
    out["ensemble_top10_h21"] = top.nlargest(10, "ens21")["symbol"].tolist()
    return out


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
               "nn_width": None}[model]
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
    why = refuse_reason()
    if why:
        rec.update({"status": "REFUSED", "refused": why})
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
    steps = (("append", step_append),
             ("grade", step_grade),
             ("trust", lambda: step_trust(forward_added=(rec.get("grade") or {}).get("graded_now", 0) > 0)),
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
    rec.setdefault("status", night_status(new_rows, stale=table_last < closed))
    rec["per_model"] = _per_model_lines(rec)
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def _per_model_lines(rec: dict) -> list[str]:
    tr = (rec.get("trust") or {}).get("trust") or {}
    ty = (rec.get("trust") or {}).get("trust_yesterday") or {}
    out = []
    for m, hv in tr.items():
        v = hv.get("h21", {})
        y = (ty.get(m) or {}).get("h21", {})
        out.append(f"{m:10s} h21 graded dates {v.get('graded_dates')} ({v.get('n_forward_blocks')} blocks) | "
                   f"trust today {v.get('trust')} yesterday {y.get('trust')} | source {v.get('source')}")
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
