"""Decision-time membership is FROZEN once a grid date is stored (owner decision 2026-10-06).

    "Freeze historical universe membership once a forecast has been generated. Vendor
     retrospective adjustments are appended as later REVISIONS; what the model knew at
     prediction time is never rewritten."

Why: from 2026-10-01 every night refused with `TableShrink` because the vendor re-adjusted
313 histories for dividends, which moved the trailing median dollar volume of EQBK and
THFF across the $3M floor on two January grid dates. The bars were present; only a
marginal eligibility moved. The guard was right that the TABLE must not lose a row, and
wrong that a re-adjustment is a loss. This module separates the two.

WHAT IS FROZEN, in plain words (review C5 F1/F2, 2026-10-07): the FIRST-STORED VINTAGE of
each grid row -- its membership and its feature values as computed the night the date was
first stored. For grid dates first stored on/after config.PIT_DOLLAR_VOLUME_FROM that night is
the decision night (lag recorded per date in membership_vintage.jsonl), so the frozen value is
what the model could know. For older dates the vintage is LATER than the decision date: their
dollar-volume features and eligibility carry the dividends paid in between
(config.PRE_FREEZE_DV_NOTE). The exact rows a forecast was scored on are a separate record:
`nightly.save_frozen_inputs` writes them beside each night's frozen forecast files.

A nightly rebuild of a stored grid date may only:

  (a) ADD new grid dates (and replace yesterday's off-grid live rows);
  (b) set a label to its BEST-KNOWN value: fill a missing one, replace a provisional one, and
      replace a final one that moved by more than config.LABEL_REVISION_MIN_ABS (logged as
      LABEL_RECOMPUTED). A label is an outcome, not decision-time knowledge (review F10);
  (c) APPEND a revision row (`revisions.parquet`) for each MATERIAL vendor change to
      membership or decision-time features (config tolerances): a stored member the rebuild
      would now call ineligible, a name it would now add, a symbol absent from the rebuilt
      bars, a feature value. These are recorded, never applied.

It may NEVER drop a stored row or date. `TableShrink` stays the guard for a genuine shrink:
the merged table is still checked row by row, and a rebuild that cannot reproduce more than
config.MEMBERSHIP_REFUSE_SHARE of the stored membership (absent and ineligible counted
separately) is a broken input, not a re-adjustment, and is REFUSED. Smaller counts above the
config.NIGHT_DEGRADED_* levels make the night DEGRADED.

`membership_hashes` gives every grid date a sha256 of its sorted member list, so a later
audit can prove nothing moved: the receipt carries them, and `check_frozen` refuses a
write in which any stored date's hash changed (an exclusion-list removal is allowed only
when declared, counted and reported).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nn_lab import config as C

H = C.HORIZONS
KEY = ["date", "symbol"]

#: Every threshold lives in nn_lab/config.py (review C5 F4) and is read at CALL time, so a
#: test can move it and the receipt prints the values actually used (`thresholds()`).
ABS_TOL = 1e-7     # float32 storage noise: below this two floats are the same number


def thresholds() -> dict:
    return {"membership_refuse_share": C.MEMBERSHIP_REFUSE_SHARE,
            "membership_refuse_floor": C.MEMBERSHIP_REFUSE_FLOOR,
            "refuse_rule": "refuse when absent > cap or ineligible > cap; cap = max(floor, int(share x stored tail rows))",
            "night_degraded_absent_over": C.NIGHT_DEGRADED_ABSENT_OVER,
            "night_degraded_would_drop_over": C.NIGHT_DEGRADED_WOULD_DROP_OVER,
            "night_degraded_etf_removed_over": C.NIGHT_DEGRADED_ETF_REMOVED_OVER,
            "feature_revision_abs_tol": C.FEATURE_REVISION_ABS_TOL,
            "feature_revision_level_rel_tol": C.FEATURE_REVISION_LEVEL_REL_TOL,
            "feature_level_columns": list(C.FEATURE_LEVEL_COLUMNS),
            "label_revision_min_abs": C.LABEL_REVISION_MIN_ABS,
            "label_rule": "a final label is replaced (and logged) only when |recomputed - stored| > min_abs; "
                          "exactly min_abs is not a revision"}


class TableShrink(RuntimeError):
    """A rebuild would lose a stored grid row, a stored grid date or a stored label, or a
    frozen date's membership would move."""


# ─────────────────────────────── helpers ─────────────────────────────────────

def labelled_dates(dates, cal: pd.DatetimeIndex, h: int) -> pd.DatetimeIndex:
    """Grid dates whose h-session label window has ELAPSED on the calendar (review F5.5:
    'y is not null' kept dates whose only labels were a few delisted names)."""
    d = pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates)))
    pos = np.searchsorted(cal.values, d.values)
    return pd.DatetimeIndex(np.sort(d[pos + 1 + h < len(cal)]))


def _grid(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["on_grid"].astype(bool)] if "on_grid" in df.columns else df


def membership_hashes(df: pd.DataFrame) -> dict[str, str]:
    """{grid date: sha256 of its sorted member symbols joined by newline}. Byte-stable: it
    depends only on the set of (date, symbol) keys, never on row order or values."""
    g = _grid(df)[KEY]
    out: dict[str, str] = {}
    for d, s in g.groupby("date", sort=True)["symbol"]:
        body = "\n".join(sorted(map(str, s.unique()))).encode("utf-8")
        out[str(pd.Timestamp(d).date())] = hashlib.sha256(body).hexdigest()
    return out


def hashes_digest(hashes: dict[str, str]) -> str:
    """One sha256 over the whole {date: hash} map (sorted), for a one-line comparison."""
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def table_counts(df: pd.DataFrame) -> dict:
    """Rows, grid rows, grid dates and stored labels per horizon: printed before and after."""
    g = _grid(df)
    return {"rows": int(len(df)), "grid_rows": int(len(g)),
            "grid_dates": int(g["date"].nunique()) if len(g) else 0,
            "last_date": str(pd.Timestamp(df["date"].max()).date()) if len(df) else None,
            "labels": {f"y_{h}": int(g[f"y_{h}"].notna().sum()) for h in H if f"y_{h}" in g.columns}}


def shrink_check(old: pd.DataFrame, new: pd.DataFrame, labels=tuple(f"y_{h}" for h in H)) -> dict:
    """Compare the TABLE, not today's cross-section. RAISE if a stored grid row or a stored
    label is gone. Yesterday's off-grid live rows may go (today's replace them)."""
    og, ng = _grid(old), _grid(new)
    ok = pd.MultiIndex.from_frame(og[KEY])
    nk = pd.MultiIndex.from_frame(ng[KEY])
    lost = ok.difference(nk)
    if len(lost):
        ex = [(str(pd.Timestamp(d).date()), s) for d, s in list(lost)[:3]]
        raise TableShrink(f"table would LOSE {len(lost):,} stored grid rows, e.g. {ex}; refused, original kept")
    lost_dates = set(og["date"]) - set(ng["date"])
    if lost_dates:
        raise TableShrink(f"table would LOSE {len(lost_dates)} grid dates; refused, original kept")
    a = og.set_index(KEY)[list(labels)].notna()
    b = ng.set_index(KEY)[list(labels)].notna()
    b = b[~b.index.duplicated()].reindex(a.index, fill_value=False)
    lost_lab = int((a & ~b).to_numpy().sum())
    if lost_lab:
        raise TableShrink(f"table would LOSE {lost_lab:,} stored labels; refused, original kept")
    return {"grid_rows_kept": int(len(ok)), "grid_rows_new": int(len(nk.difference(ok))),
            "labels_filled": int((~a & b).to_numpy().sum()) if len(a) else 0}


def check_frozen(old: pd.DataFrame, new: pd.DataFrame, allowed_removed: pd.DataFrame | None = None) -> dict:
    """RAISE if any stored grid date's membership differs in the new table, except for the
    (date, symbol) keys in `allowed_removed` (a deliberate exclusion-list change, which the
    caller counts and reports). `old` is the stored table BEFORE any exclusion (review F6)."""
    og, ng = _grid(old)[KEY], _grid(new)[KEY]
    ho, hn = membership_hashes(old), membership_hashes(new)
    moved = [d for d, h in ho.items() if hn.get(d) != h]
    explained: list[str] = []
    if moved and allowed_removed is not None and len(allowed_removed):
        ar = _grid(allowed_removed)[KEY] if "on_grid" in allowed_removed else allowed_removed[KEY]
        okeys = pd.MultiIndex.from_frame(og)
        expect = og[~okeys.isin(pd.MultiIndex.from_frame(ar))]
        he = membership_hashes(expect.assign(on_grid=True))
        explained = [d for d in moved if hn.get(d) == he.get(d)]
        moved = [d for d in moved if d not in explained]
    if moved:
        raise TableShrink(f"frozen membership MOVED on {len(moved)} stored grid dates, e.g. {moved[:3]}; "
                          f"refused, original kept")
    return {"frozen_dates_checked": len(ho), "frozen_dates_moved": 0,
            "frozen_dates_changed_by_declared_exclusion": len(explained),
            "new_dates": sorted(set(hn) - set(ho))}


# ─────────────────────────────── the merge ───────────────────────────────────

def feature_columns(df: pd.DataFrame) -> list[str]:
    from nn_lab.table import GROUPS
    cols = [c for g in GROUPS.values() for c in g] + ["med_dv", "close"]
    return [c for c in cols if c in df.columns]


def _differs(a: np.ndarray, b: np.ndarray, abs_tol: float = ABS_TOL, rel_tol: float = 0.0) -> np.ndarray:
    """True where b is a MATERIAL change of a: one side NaN, or |b-a| > abs_tol and
    |b-a| > rel_tol x |a|."""
    a = a.astype("float64")
    b = b.astype("float64")
    both_nan = np.isnan(a) & np.isnan(b)
    one_nan = np.isnan(a) ^ np.isnan(b)
    with np.errstate(invalid="ignore"):
        d = np.abs(a - b)
        far = (d > abs_tol) & (d > rel_tol * np.abs(a))
    return (one_nan | far) & ~both_nan


def feature_material(A: np.ndarray, B: np.ndarray, cols: list[str]) -> np.ndarray:
    """Per cell: is the rebuilt feature a MATERIAL revision (config tolerances, review F3)?"""
    D = np.zeros(A.shape, dtype=bool)
    for k, c in enumerate(cols):
        rel = C.FEATURE_REVISION_LEVEL_REL_TOL if c in C.FEATURE_LEVEL_COLUMNS else 0.0
        abs_ = ABS_TOL if c in C.FEATURE_LEVEL_COLUMNS else C.FEATURE_REVISION_ABS_TOL
        D[:, k] = _differs(A[:, k], B[:, k], abs_, rel)
    return D


def _row_hash(df: pd.DataFrame) -> np.ndarray:
    if not len(df):
        return np.array([], dtype=object)
    num = df.select_dtypes(include=[np.number, bool]).astype("float64").round(6)
    h = pd.util.hash_pandas_object(num, index=False).to_numpy()
    return np.array([f"{int(x):016x}" for x in h], dtype=object)


def _reason_close(st_close: np.ndarray, rb_close: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = rb_close.astype("float64") / st_close.astype("float64")
    return np.array([
        (f"adjusted close rescaled x{x:.6f} (vendor dividend/split re-adjustment of the history)"
         if np.isfinite(x) and abs(x - 1.0) > 1e-6 else "inputs changed with the close unchanged "
         "(side group or volume revision)") for x in r], dtype=object)


def merge_frozen(stored: pd.DataFrame, rebuilt: pd.DataFrame, *, tail_start: pd.Timestamp,
                 cal_stored: pd.DatetimeIndex, run_id: str, asof_utc: str,
                 vendor_bars_through: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Merge a tail rebuild into the stored table under frozen membership.

    `stored`  : the stored table (all columns).
    `rebuilt` : the rebuild of every date >= tail_start, labels already computed over the
                FROZEN membership of each stored date (see `restrict_to_frozen`). It may carry
                `_rebuild_eligible` (False for a stored member the rebuild forced in although
                its rebuilt eligibility failed).
    Returns (new table, revision rows, stats). Never drops a stored grid row or date."""
    tail_start = pd.Timestamp(tail_start)
    cols = list(stored.columns)
    head = stored[stored["date"] < tail_start]
    st_tail = stored[stored["date"] >= tail_start]
    st_grid = _grid(st_tail)
    stored_dates = set(_grid(stored)["date"])
    st_keys = pd.MultiIndex.from_frame(st_grid[KEY])

    rb = rebuilt.copy()
    if "_rebuild_eligible" not in rb.columns:
        rb["_rebuild_eligible"] = True
    rb_on = rb["on_grid"].astype(bool).to_numpy()
    rb_keys = pd.MultiIndex.from_frame(rb[KEY])
    is_member = rb_keys.isin(st_keys)
    on_stored_date = rb["date"].isin(stored_dates).to_numpy()
    would_add = rb[rb_on & on_stored_date & ~is_member]
    rb_members = rb[is_member & rb_on]
    rb_members = rb_members[~pd.MultiIndex.from_frame(rb_members[KEY]).duplicated()]
    # appended: new grid dates + today's off-grid live rows (never a stored grid key)
    rb_new = rb[~(rb_on & on_stored_date)]
    rb_new = rb_new[~(rb_new["on_grid"].astype(bool) & pd.MultiIndex.from_frame(rb_new[KEY]).isin(st_keys))]

    S = st_grid.set_index(KEY)
    R = rb_members.set_index(KEY).reindex(S.index)
    present = R["_rebuild_eligible"].notna().to_numpy()
    elig = R["_rebuild_eligible"].eq(True).to_numpy() & present
    out = S.copy()
    revs: list[pd.DataFrame] = []

    def rev(mask: np.ndarray, kind: str, reason, columns, max_rel, hashes):
        if not mask.any():
            return
        idx = S.index[mask]
        revs.append(pd.DataFrame({
            "date": idx.get_level_values(0), "symbol": idx.get_level_values(1), "kind": kind,
            "reason": reason if np.ndim(reason) else np.full(mask.sum(), reason, dtype=object),
            "columns": columns if np.ndim(columns) else np.full(mask.sum(), columns, dtype=object),
            "max_rel_change": max_rel if np.ndim(max_rel) else np.full(mask.sum(), max_rel, dtype="float64"),
            "rebuilt_values_hash": hashes}))

    # 1. a stored member the vendor re-adjustment made ineligible: kept, revision appended
    ineligible = present & ~elig
    if ineligible.any():
        smd = S["med_dv"].to_numpy(dtype="float64") if "med_dv" in S else np.full(len(S), np.nan)
        rmd = R["med_dv"].to_numpy(dtype="float64") if "med_dv" in R else np.full(len(S), np.nan)
        rss = R["sessions_seen"].to_numpy(dtype="float64") if "sessions_seen" in R else np.full(len(S), np.nan)
        reason = np.array([
            f"rebuilt eligibility FAILED (median $ volume stored {a:,.0f} -> rebuilt {b:,.0f}, floor "
            f"{C.MIN_MEDIAN_DOLLAR_VOL:,.0f}; sessions {c:.0f}); membership frozen, row kept"
            for a, b, c in zip(smd[ineligible], rmd[ineligible], rss[ineligible])], dtype=object)
        rev(ineligible, "MEMBERSHIP_WOULD_DROP", reason, "membership", np.nan,
            _row_hash(pd.DataFrame({"med_dv": rmd[ineligible]})))
    # 2. a stored member whose symbol the rebuild could not produce at all
    absent = ~present
    rev(absent, "MEMBER_ABSENT_FROM_REBUILD",
        "symbol absent from the rebuilt bars (or below the history floor); stored row kept as stored",
        "membership", np.nan, np.full(int(absent.sum()), "", dtype=object))

    # 3. features: frozen; a changed value is a revision, never applied
    fcols = feature_columns(st_grid)
    if fcols and present.any():
        A = S[fcols].to_numpy(dtype="float64")
        B = R[fcols].to_numpy(dtype="float64")
        D = np.zeros(A.shape, dtype=bool)
        D[present] = feature_material(A[present], B[present], fcols)     # config tolerances (F3)
        changed = D.any(axis=1)
        if changed.any():
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = np.abs(B - A) / np.maximum(np.abs(A), ABS_TOL)
            rel = np.where(D, rel, np.nan)
            rc_ = np.where(np.isfinite(rel), rel, np.inf)[changed]       # NaN<->value counts as inf
            maxrel = np.where(D[changed], rc_, -np.inf).max(axis=1)
            names = np.array(fcols, dtype=object)
            colstr = np.array([",".join(names[row][:12]) + ("..." if row.sum() > 12 else "")
                               for row in D[changed]], dtype=object)
            sc = S["close"].to_numpy() if "close" in S else np.full(len(S), np.nan)
            rc = R["close"].to_numpy() if "close" in R else np.full(len(S), np.nan)
            rev(changed, "FEATURES_REVISED", _reason_close(sc[changed], rc[changed]), colstr, maxrel,
                _row_hash(R.loc[changed, fcols].reset_index(drop=True)))

    # 4. labels (review F10): a label is an OUTCOME, not decision-time knowledge, so the
    #    best-known value trains the model. Fill a missing one; replace a provisional one (stored
    #    before its window elapsed); replace a FINAL one only when it moved by MORE than
    #    LABEL_REVISION_MIN_ABS against the STORED value, and log that change. A smaller change
    #    is counted and not applied, so the stored label is always within the tolerance of the
    #    best-known one and a slow drift is logged the night its total passes the tolerance.
    labels_filled = labels_provisional_replaced = labels_final_recomputed = labels_final_tiny = 0
    tol = C.LABEL_REVISION_MIN_ABS
    dates_idx = S.index.get_level_values(0)
    for h in H:
        y, f, dx = f"y_{h}", f"fwd_{h}", f"delist_exit_{h}"
        if y not in S.columns:
            continue
        final = dates_idx.isin(labelled_dates(stored_dates, cal_stored, h))
        sy = S[y].to_numpy(dtype="float64")
        ry = R[y].to_numpy(dtype="float64")
        have_r = present & ~np.isnan(ry)
        fill = np.isnan(sy) & have_r
        prov = ~np.isnan(sy) & ~final & have_r
        changed_final = ~np.isnan(sy) & final & have_r & _differs(sy, ry)
        with np.errstate(invalid="ignore"):
            big = np.abs(ry - sy) > tol
        recompute = changed_final & big
        labels_final_tiny += int((changed_final & ~big).sum())
        upd = fill | prov | recompute
        if recompute.any():
            rev(recompute, "LABEL_RECOMPUTED",
                np.array([f"final {y} recomputed from the current bars: stored {a:.6f} -> {b:.6f} (applied: "
                          f"an outcome, not decision-time knowledge)" for a, b in zip(sy[recompute], ry[recompute])],
                         dtype=object),
                y, np.abs(ry - sy)[recompute], _row_hash(R.loc[recompute, [y]].reset_index(drop=True)))
        for c in (y, f, dx):
            if c in out.columns and c in R.columns and upd.any():
                out.loc[upd, c] = R.loc[upd, c].to_numpy()
        labels_filled += int(fill.sum())
        labels_provisional_replaced += int((prov & _differs(sy, ry)).sum())
        labels_final_recomputed += int(recompute.sum())

    out = out.reset_index()[cols]
    rb_new_c = rb_new[[c for c in cols if c in rb_new.columns]]
    new = pd.concat([head, out, rb_new_c], ignore_index=True)
    new = new.sort_values(KEY, kind="mergesort").reset_index(drop=True)

    if len(would_add):
        wa = would_add.reset_index(drop=True)
        revs.append(pd.DataFrame({
            "date": wa["date"].to_numpy(), "symbol": wa["symbol"].to_numpy(), "kind": "MEMBERSHIP_WOULD_ADD",
            "reason": "the re-adjusted bars make this name eligible on a stored (frozen) date; not added",
            "columns": "membership", "max_rel_change": np.nan,
            "rebuilt_values_hash": _row_hash(pd.DataFrame(
                {"med_dv": wa["med_dv"].to_numpy(dtype="float64") if "med_dv" in wa else np.zeros(len(wa))}))}))
    R_ = (pd.concat(revs, ignore_index=True) if revs else
          pd.DataFrame(columns=["date", "symbol", "kind", "reason", "columns", "max_rel_change",
                                "rebuilt_values_hash"]))
    R_["asof_utc"] = asof_utc
    R_["run_id"] = run_id
    R_["vendor_bars_through"] = vendor_bars_through
    cap = membership_cap(len(S))
    stats = {"stored_tail_grid_rows": int(len(S)),
             "membership_would_drop": int(ineligible.sum()), "member_absent_from_rebuild": int(absent.sum()),
             "membership_would_add": int(len(would_add)),
             "rows_re_adjusted": int(R_["kind"].eq("FEATURES_REVISED").sum()) if len(R_) else 0,
             "rows_dropped": 0, "drop_cap": cap,
             "thresholds": thresholds(),
             "labels_filled": labels_filled, "labels_provisional_replaced": labels_provisional_replaced,
             "labels_final_recomputed_applied_and_logged": labels_final_recomputed,
             "labels_final_changed_within_tolerance_not_applied": labels_final_tiny,
             "rows_appended": int(len(rb_new_c)),
             "revisions_by_kind": R_["kind"].value_counts().to_dict() if len(R_) else {}}
    if int(absent.sum()) > cap:
        raise TableShrink(f"the rebuild cannot produce {int(absent.sum()):,} of {len(S):,} stored tail members "
                          f"(absent from the bars; cap {cap:,}): that is a broken input (truncated bars file?), "
                          f"not a vendor re-adjustment; refused, original kept")
    if int(ineligible.sum()) > cap:
        raise TableShrink(f"the rebuild would make {int(ineligible.sum()):,} of {len(S):,} stored tail members "
                          f"ineligible (cap {cap:,}): that is a broken input, not a vendor re-adjustment; "
                          f"refused, original kept")
    return new, R_, stats


def membership_cap(n_stored_tail: int) -> int:
    """Refuse when absent > cap (or ineligible > cap); exactly cap passes."""
    return max(int(C.MEMBERSHIP_REFUSE_FLOOR), int(C.MEMBERSHIP_REFUSE_SHARE * n_stored_tail))


def degraded_reasons(mstats: dict | None) -> list[str]:
    """Membership counts above the declared levels (config) that make a night DEGRADED."""
    m = mstats or {}
    out = []
    if int(m.get("member_absent_from_rebuild", 0)) > C.NIGHT_DEGRADED_ABSENT_OVER:
        out.append(f"{m['member_absent_from_rebuild']} stored members ABSENT from the rebuilt bars "
                   f"(> {C.NIGHT_DEGRADED_ABSENT_OVER})")
    if int(m.get("membership_would_drop", 0)) > C.NIGHT_DEGRADED_WOULD_DROP_OVER:
        out.append(f"{m['membership_would_drop']} stored members the rebuild would drop "
                   f"(> {C.NIGHT_DEGRADED_WOULD_DROP_OVER})")
    if int(m.get("etf_removed_from_frozen_dates", 0)) > C.NIGHT_DEGRADED_ETF_REMOVED_OVER:
        out.append(f"{m['etf_removed_from_frozen_dates']} frozen members removed by the ETF exclusion list "
                   f"(> {C.NIGHT_DEGRADED_ETF_REMOVED_OVER})")
    return out


def record_vintage(new_grid_dates, vendor_bars_through: str, cal: pd.DatetimeIndex, run_id: str,
                   path: Path | None = None) -> list[dict]:
    """One append-only row per grid date the night it is FIRST stored: the bars' vintage and
    the lag in sessions between the decision date and that vintage. Lag 0 = no session after t
    was in the bars, so no later dividend can be in its dollar volume (review F1)."""
    path = Path(path or C.MEMBERSHIP_VINTAGE)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["date"])
            except Exception:
                continue
    vt = pd.Timestamp(vendor_bars_through)
    rows = []
    for d in sorted(pd.DatetimeIndex(new_grid_dates)):
        ds = str(d.date())
        if ds in seen:
            continue
        lag = int(np.searchsorted(cal.values, np.datetime64(vt), side="right") -
                  np.searchsorted(cal.values, np.datetime64(d), side="right"))
        rows.append({"date": ds, "first_stored_run": run_id, "vendor_bars_through": str(vt.date()),
                     "lag_sessions": lag, "pit_dollar_volume": lag == 0,
                     "note": ("no session after t in the bars: dollar volume and eligibility are point-in-time"
                              if lag == 0 else f"{lag} session(s) after t were in the bars: dividends ex-dated in "
                              f"that window are in the adjusted dollar volume")})
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return rows


def restrict_to_frozen(rows: pd.DataFrame, stored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop rebuilt rows on a STORED grid date that are not stored members (returned
    separately as the would-add set) so the excess labels' median is over the frozen
    membership. Call BEFORE `table.add_excess_labels`."""
    sg = _grid(stored)
    st_keys = pd.MultiIndex.from_frame(sg[KEY])
    on = rows["on_grid"].astype(bool).to_numpy() & rows["date"].isin(set(sg["date"])).to_numpy()
    member = pd.MultiIndex.from_frame(rows[KEY]).isin(st_keys)
    extra = on & ~member
    return rows[~extra].reset_index(drop=True), rows[extra].reset_index(drop=True)


# ─────────────────────────────── the revisions file ──────────────────────────

REV_COLS = ["date", "symbol", "kind", "reason", "columns", "max_rel_change", "rebuilt_values_hash",
            "asof_utc", "run_id", "vendor_bars_through"]


def _rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(C.REPO).resolve())).replace("\\", "/")
    except ValueError:
        return Path(path).name


#: Kinds the nightly tail rebuild RE-DIFFS every night against a stored value that never
#: changes (features and membership are frozen, never applied). For these, "no row tonight"
#: on a checked date means the vendor value is back at the stored one: a REVERSION, logged.
#: LABEL_RECOMPUTED is excluded: an applied label moves the stored value, so its silence the
#: next night is agreement, not a reversion.
REVERTIBLE_KINDS = ("FEATURES_REVISED", "MEMBERSHIP_WOULD_DROP", "MEMBERSHIP_WOULD_ADD",
                    "MEMBER_ABSENT_FROM_REBUILD")
REVERTED_HASH = "REVERTED_TO_STORED"
#: label revisions are per horizon (`columns` = y_h); everything else is one timeline per name-date
_LABEL_KINDS = ("LABEL_RECOMPUTED", "LABEL_REVISED")
_TL_KEY = ["date", "symbol", "kind", "_ck"]


def _timeline_key(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out["symbol"] = out["symbol"].astype(str)
    out["kind"] = out["kind"].astype(str)
    out["_ck"] = [str(c) if k in _LABEL_KINDS else "" for k, c in zip(out["kind"], out["columns"])]
    return out


def revisions_history(path: Path, archive_dir: Path | None = None) -> pd.DataFrame:
    """The live log plus every rotated month (the timeline spans the rotation)."""
    path = Path(path)
    parts = [pd.read_parquet(f) for f in sorted(Path(archive_dir or revisions_archive_dir(path))
                                               .glob("revisions_????-??.parquet"))]
    if path.exists():
        parts.append(pd.read_parquet(path))
    parts = [x for x in parts if len(x)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=REV_COLS)


def append_revisions(revs: pd.DataFrame, path: Path, *, checked_from: pd.Timestamp | None = None,
                     run_id: str | None = None, asof_utc: str | None = None,
                     archive_dir: Path | None = None) -> dict:
    """Append-only TIMELINE per (date, symbol, kind[, label column]) (C15, review C5 F9).

    A row is appended when its rebuilt-values hash differs from the LATEST logged state of
    its key (or the key is new), so the same vendor value seen again tomorrow is not a new
    revision while a flip-flop is: A(stored) -> B -> C -> B logs B, C, B.

    `checked_from` (the night's tail start): a key of a `REVERTIBLE_KINDS` kind on a date the
    rebuild checked tonight, whose latest state is a revision but which produced NO row
    tonight, has gone back to the frozen stored value; a `REVERTED_TO_STORED` row records it.
    So A -> B -> A logs TWO revisions (B, then the reversion), not one.

    The latest state is read over the live file AND the rotated months. Written
    temp -> verify -> replace; a stored revision is never removed."""
    path = Path(path)
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=REV_COLS)
    hist = revisions_history(path, archive_dir)
    r = revs.reindex(columns=REV_COLS).copy() if len(revs) else pd.DataFrame(columns=REV_COLS)
    r["date"] = pd.to_datetime(r["date"])
    latest = None
    if len(hist):
        h = _timeline_key(hist)
        h["_ord"] = range(len(h))
        latest = h.sort_values("_ord").groupby(_TL_KEY, sort=False).tail(1).set_index(_TL_KEY)
    n_revert = 0
    if len(r):
        rk = _timeline_key(r)
        rk = rk.drop_duplicates(_TL_KEY, keep="last")
        if latest is not None:
            prev = latest["rebuilt_values_hash"].astype(str).reindex(pd.MultiIndex.from_frame(rk[_TL_KEY]))
            same = prev.to_numpy(dtype=object) == rk["rebuilt_values_hash"].astype(str).to_numpy(dtype=object)
            rk = rk[~same]
        r = rk.drop(columns=["_ck"])
    if checked_from is not None and latest is not None and len(latest):
        lat = latest.reset_index()
        tonight = set(map(tuple, _timeline_key(revs.reindex(columns=REV_COLS))[_TL_KEY].astype(str).to_numpy())) \
            if len(revs) else set()
        cand = lat[lat["kind"].isin(REVERTIBLE_KINDS)
                   & (lat["date"] >= pd.Timestamp(checked_from))
                   & (lat["rebuilt_values_hash"].astype(str) != REVERTED_HASH)]
        if len(cand):
            keys = cand[_TL_KEY].astype(str).to_numpy()
            cand = cand[[tuple(k) not in tonight for k in keys]]
        if len(cand):
            n_revert = int(len(cand))
            rv = pd.DataFrame({
                "date": cand["date"].to_numpy(), "symbol": cand["symbol"].to_numpy(), "kind": cand["kind"].to_numpy(),
                "reason": "the vendor value returned to the frozen stored value (a reversion of the logged revision)",
                "columns": cand["columns"].astype(str).to_numpy(), "max_rel_change": np.nan,
                "rebuilt_values_hash": REVERTED_HASH,
                "asof_utc": asof_utc or "", "run_id": run_id or "", "vendor_bars_through": ""})
            r = pd.concat([r, rv], ignore_index=True) if len(r) else rv
    if not len(r):
        return {"n_appended": 0, "n_reverted": 0, "n_total": int(len(old)), "path": _rel(path)}
    if len(old):
        old["date"] = pd.to_datetime(old["date"])
    new = pd.concat([old, r], ignore_index=True) if len(old) else r.reset_index(drop=True)
    new = new.reindex(columns=REV_COLS)
    for c in ("kind", "reason", "columns", "rebuilt_values_hash", "asof_utc", "run_id", "vendor_bars_through", "symbol"):
        new[c] = new[c].astype(str)
    new["max_rel_change"] = pd.to_numeric(new["max_rel_change"], errors="coerce")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    new.to_parquet(tmp, index=False)
    if len(pd.read_parquet(tmp, columns=["date"])) != len(new) or len(new) < len(old):
        raise RuntimeError("revisions write verification failed; original kept")
    tmp.replace(path)
    return {"n_appended": int(len(r)), "n_reverted": n_revert, "n_total": int(len(new)), "path": _rel(path)}


# ─────────────────────────────── monthly rotation (C15) ──────────────────────
#
# Review C5 F9: `table/` is gitignored, so the "never removed" record of vendor changes
# was an untracked local file, read whole and rewritten every night. Closed months
# (by each row's own `asof_utc`, never the file mtime) move to
# `nn_lab/revisions_archive/revisions_<YYYY-MM>.parquet`, TRACKED (un-ignored in
# .gitignore), with a committed JSON manifest beside it: rows, kinds, first/last asof,
# the sha256 of the parquet bytes and the command. A sealed month is written once.

REVISIONS_MANIFEST_SCHEMA = "nn_lab/revisions_manifest/1"


def revisions_archive_dir(path: Path | None = None) -> Path:
    """`<nn_lab out>/revisions_archive`, derived from the live log's path
    (`<out>/table/revisions.parquet`), so a test's tmp log never writes the real archive."""
    return (Path(path).parent.parent if path is not None else Path(C.OUT)) / "revisions_archive"


def _sha256_file(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rotate_revisions(path: Path, *, now: datetime | None = None, archive_dir: Path | None = None) -> dict:
    """Move every CLOSED month's rows (asof_utc month < the current UTC month) out of the
    live log into a sealed monthly parquet + manifest. Refuses a month already sealed
    (the rows stay in the live file, named); verifies archive + remaining == before."""
    path = Path(path)
    now = now or datetime.now(timezone.utc)
    adir = Path(archive_dir or revisions_archive_dir(path))
    cur = now.strftime("%Y-%m")
    if not path.exists():
        return {"status": "OK", "sealed": [], "refused": [], "why": "no live revisions file"}
    live = pd.read_parquet(path)
    if not len(live):
        return {"status": "OK", "sealed": [], "refused": []}
    month = live["asof_utc"].astype(str).str[:7]
    undated = ~month.str.match(r"^\d{4}-\d{2}$")
    closed = sorted(set(month[~undated & (month < cur)]))
    sealed, refused = [], []
    keep = pd.Series(True, index=live.index)
    for m in closed:
        out = adir / f"revisions_{m}.parquet"
        man = adir / f"revisions_{m}.json"
        if out.exists() or man.exists():
            refused.append({"month": m, "why": f"{out.name} is already sealed (a month is written once); "
                                               f"{int((month == m).sum())} rows stay in the live file"})
            continue
        rows = live[month == m]
        adir.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.parquet")
        rows.to_parquet(tmp, index=False)
        if len(pd.read_parquet(tmp, columns=["date"])) != len(rows):
            tmp.unlink(missing_ok=True)
            refused.append({"month": m, "why": "archive write verification failed; rows kept live"})
            continue
        tmp.replace(out)
        body = {"schema": REVISIONS_MANIFEST_SCHEMA, "month": m, "rows": int(len(rows)),
                "kinds": {str(k): int(v) for k, v in rows["kind"].astype(str).value_counts().items()},
                "first_asof_utc": str(rows["asof_utc"].astype(str).min()),
                "last_asof_utc": str(rows["asof_utc"].astype(str).max()),
                "parquet": _rel(out), "parquet_sha256": _sha256_file(out),
                "sealed_utc": now.isoformat(timespec="seconds"),
                "command": "nn_lab.membership.rotate_revisions (called by nn_lab.nightly.step_append)"}
        mt = man.with_suffix(".tmp")
        mt.write_text(json.dumps(body, indent=1), encoding="utf-8")
        json.loads(mt.read_text(encoding="utf-8"))
        mt.replace(man)
        keep &= month != m
        sealed.append({"month": m, "rows": body["rows"], "parquet_sha256": body["parquet_sha256"],
                       "manifest": _rel(man)})
    if sealed:
        rest = live[keep]
        tmp = path.with_suffix(".tmp.parquet")
        rest.to_parquet(tmp, index=False)
        n_arch = sum(x["rows"] for x in sealed)
        if len(pd.read_parquet(tmp, columns=["date"])) + n_arch != len(live):
            tmp.unlink(missing_ok=True)
            raise RuntimeError("rotation verification failed (archive + live != before); live file kept")
        tmp.replace(path)
    return {"status": "REFUSED" if refused and not sealed else "OK", "sealed": sealed, "refused": refused,
            "n_undated_rows_kept_live": int(undated.sum()), "live_rows_after": int(len(live) - sum(
                x["rows"] for x in sealed))}


# ─────────────────────────────── the audit ───────────────────────────────────

def audit(receipt_dir: Path | None = None, table_path: Path | None = None) -> dict:
    """Prove nothing moved: every date hash in the OLDEST receipt that carries hashes must be
    identical in every later one and in the table on disk. A run whose receipt lacks hashes
    (a refusal) is skipped and named. Exit code 0 only when nothing moved."""
    rd = Path(receipt_dir or C.RECEIPT_DIR)
    tp = Path(table_path or C.TABLE_PATH)
    recs = []
    for f in sorted(rd.glob("nightly_*.json")):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        h = (r.get("append") or {}).get("membership_hash_by_date")
        recs.append((f.name, h))
    with_h = [(n, h) for n, h in recs if h]
    out: dict = {"receipts_with_hashes": [n for n, _ in with_h],
                 "receipts_without_hashes_after_first": [n for n, h in recs if not h and with_h and n > with_h[0][0]]}
    if not with_h:
        out["status"] = "CANNOT_DETERMINE: no receipt carries membership hashes yet"
        return out
    moved = []
    for i in range(1, len(with_h)):
        prev, cur = with_h[i - 1][1], with_h[i][1]
        moved += [(with_h[i][0], d) for d, h in prev.items() if cur.get(d) != h]
    if tp.exists():
        now = {d: h[:16] for d, h in membership_hashes(pd.read_parquet(tp, columns=["date", "symbol", "on_grid"])).items()}
        moved += [("table_on_disk", d) for d, h in with_h[-1][1].items() if now.get(d) != h]
        out["table_dates"] = len(now)
    out["dates_checked"] = len(with_h[0][1])
    out["moved"] = moved[:50]
    out["n_moved"] = len(moved)
    out["status"] = "OK: no frozen date moved" if not moved else "MOVED"
    return out


if __name__ == "__main__":
    import sys
    res = audit()
    print(json.dumps(res, indent=1, default=str))
    sys.exit(0 if res.get("n_moved") == 0 else 2)
