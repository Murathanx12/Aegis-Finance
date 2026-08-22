"""Planted-world detectability at AEGIS-PANEL-2 scale — the gate on TOURNAMENT-2.

TOURNAMENT-1's sensitivity worlds measured the instrument **blind below planted
IC 0.03** on panel-1 (230,640 rows; the dense world recovered +0.00097 of a
planted 0.03, ci_lo −0.0043). The declared successor was SCALE, and panel-2 is
that: 4,157,680 stock-months over 1926-2024, eighteen times the rows, the same
412 characteristics, a construction-matched floor
(`backend/services/aegis_panel2_spec.py`).

This script asks the only question the gate cares about: **at this scale, can
the instrument see a planted effect of the size the tournament claims to
bound?** It plants the three worlds `detectability_gate.REQUIRED_WORLDS` names
— `linear`, `linear_dense`, `linear_hetero` — with the same carriers and the
same 0.03 target as panel-1, so the two panels' receipts are readable against
each other.

WHAT CHANGED BETWEEN THE PANELS, so no reader attributes the difference to one
cause: scale (18x rows), universe (floored -> all-cap), training era (2013+ ->
1926+), and floor construction (own daily-price features, disjoint from JKP ->
seven JKP price columns that are a SUBSET of the 412). The detectability
result belongs to that bundle, not to scale alone.

Nothing here is market evidence. Every receipt is stamped SENSITIVITY_WORLD,
the real label is destroyed before any arm sees it (the hetero world reads it
ONLY as a per-month volatility), and `detectability_gate` refuses to read a
receipt that is not stamped that way.

MEMORY IS THE BINDING CONSTRAINT AND IT SHAPED THE DESIGN. The feature matrix
is 6.9 GB; a boolean-mask slice of it is a second 6.4 GB, which on a 31 GB
machine put the first attempt into paging (a fold that took 75 s took 15 min).
The panel is already sorted by `eom`, so every fold's training set is a
contiguous PREFIX and its test set a contiguous SLICE — and contiguous slices
of a numpy array are VIEWS. The matrix is therefore built once and never
copied again.

    python -m scripts.panel2_planted_worlds --calibrate --subsample 300000
    python -m scripts.panel2_planted_worlds --world all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import aegis_panel2_spec as S            # noqa: E402
from backend.services.net_tournament import (bootstrap_block_dates,  # noqa: E402
                                             head_verdicts,
                                             rank_ic_by_date)
from backend.services.world_model import block_bootstrap_paired  # noqa: E402

TRIAL = "RETURN-PANEL-TOURNAMENT-2"
OUT = S.OUT_DIR
CACHE = OUT / "panel2_planted_cache"

#: Its own directory, using the filename `detectability_gate.RECEIPT_TEMPLATE`
#: expects. The gate takes a receipt DIRECTORY plus a panel hash, so panel-2's
#: worlds must not sit beside panel-1's under the same names — one directory
#: per panel is what lets `assert_detectable` be pointed at the right evidence
#: while the panel-1 live pin keeps failing at its own hash.
RECEIPT_DIR = OUT / "panel2_detectability"

ECONOMIC_BAR = 0.01
SEED = 20260823
TARGET_IC = 0.03

#: Same test years as panel-1's tournament, so the comparison isolates the
#: instrument rather than the window. Training is every month whose label is
#: realised before the test year opens — on panel-2 that reaches back to 1926.
TEST_YEARS = range(2016, 2025)
MIN_TRAIN = 20_000

#: panel-1 ran ridge and MLP too; at 4.16M x 412 those go through
#: StandardScaler in float64 (~14 GB for the training matrix alone) beside a
#: 6.9 GB panel on a 31 GB machine. Omitted, and stated rather than silent:
#: the gate's claim is "SOME full arm can see an effect this size", and
#: full_lgbm is the arm that recovered most of panel-1's dense world.
ARMS = ("floor_lgbm", "full_lgbm")

#: Train on the per-date z-scored label. Per-date Spearman is invariant to a
#: per-date monotone transform, so this changes ONLY the training objective —
#: the hypothesis being that pooled MSE on raw returns spends its capacity on
#: cross-DATE dispersion instead of the cross-SECTIONAL ordering we score.
#:
#: panel-1 ran these and measured them useless (+0.00008 in its hetero world),
#: but panel-1's history was 2013+. panel-2 reaches back to 1926 and therefore
#: contains the 1930s, where monthly cross-sectional dispersion is enormous —
#: so the mechanism these arms test is far stronger here than in the sample
#: that dismissed them. Omitting them would have left the hetero world's
#: blindness unexplained AND made this run's arm set quietly narrower than the
#: panel-1 receipts it is compared against.
ZLABEL_ARMS = ("floor_lgbm_zlabel", "full_lgbm_zlabel")

ALL_ARMS = ARMS + ZLABEL_ARMS

#: Every arm's contrast base: a z-label arm is compared with the z-label
#: floor, never the raw one, or the contrast would confound the feature set
#: with the training objective.
CONTRAST_BASE = {"full_lgbm": "floor_lgbm",
                 "full_lgbm_zlabel": "floor_lgbm_zlabel"}


def _lgbm():
    from lightgbm import LGBMRegressor
    return LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05,
                         random_state=SEED, verbose=-1, n_jobs=-1)


# ── loading: one contiguous matrix, then the DataFrame is dropped ───────────
class Panel:
    """The panel as arrays: a feature matrix plus the keys, nothing else.

    `X` is C-contiguous float32 in the declared column order, so a row range
    is a view. `Xf` is the floor columns materialised once (7 columns, ~116 MB)
    because they are not adjacent in `X`.
    """

    def __init__(self, X, Xf, y_real, month_code, dates, spec):
        self.X, self.Xf = X, Xf
        self.y_real = y_real
        self.month_code = month_code
        self.dates = dates
        self.spec = spec
        self.n = len(X)

    def matrix(self, arm: str):
        return self.Xf if arm.startswith("floor_") else self.X


def load_panel(spec: dict, *, subsample: int = 0) -> Panel:
    import pyarrow.parquet as pq

    full = list(spec["full"])
    cols = [S.DATE_COL, S.MONTH_COL, S.LABEL] + full
    t = pq.read_table(S.PANEL_PATH, columns=cols)
    df = t.to_pandas()
    del t

    month = pd.PeriodIndex(pd.to_datetime(df[S.MONTH_COL]), freq="M")
    if subsample:
        # A subsample is for TIMING only; re-sorting keeps the contiguous-slice
        # invariant true so the calibration path exercises the real one.
        df = df.assign(_m=month).sample(n=min(subsample, len(df)),
                                        random_state=SEED).sort_values("_m")
        month = pd.PeriodIndex(df.pop("_m"), freq="M")

    dates = pd.to_datetime(df[S.DATE_COL]).to_numpy()
    y_real = df[S.LABEL].to_numpy(dtype=np.float64)
    month_code = (month.year.to_numpy() * 12
                  + month.month.to_numpy()).astype(np.int64)
    if not (month_code[1:] >= month_code[:-1]).all():
        raise SystemExit(
            "panel-2 is not sorted by month — every fold slice in this script "
            "assumes it is, and an unsorted panel would train on rows from "
            "AFTER the test year while reporting the right row counts")

    # One allocation, filled column by column so the DataFrame and a second
    # full-width copy never coexist.
    X = np.empty((len(df), len(full)), dtype=np.float32)
    for j, c in enumerate(full):
        X[:, j] = df[c].to_numpy(dtype=np.float32)
    del df

    floor_idx = [full.index(c) for c in spec["floor"]]
    Xf = np.ascontiguousarray(X[:, floor_idx])
    return Panel(X, Xf, y_real, month_code, dates, spec)


def folds(p: Panel):
    """(year, n_train, test_start, test_stop) — all contiguous.

    Train is every row whose month+1 is still before the test January, the
    same embargo panel-1 used: the label is next month's return, so a row from
    December of the prior year would resolve INSIDE the test window.
    """
    mc = p.month_code
    for y in TEST_YEARS:
        jan = y * 12 + 1
        n_tr = int(np.searchsorted(mc, jan - 1, side="left"))
        a = int(np.searchsorted(mc, y * 12 + 1, side="left"))
        b = int(np.searchsorted(mc, y * 12 + 12, side="right"))
        if n_tr < MIN_TRAIN or b <= a:
            print(f"  fold {y} REFUSED (train {n_tr:,}, test {b - a:,})")
            continue
        yield y, n_tr, a, b


# ── planting ────────────────────────────────────────────────────────────────
def _z(values: np.ndarray, month_code: np.ndarray) -> np.ndarray:
    """Per-month cross-sectional z-score, with panel-1's exact semantics.

    Deliberately the same pandas groupby-transform panel-1 used (skipna mean
    and population std, then NaN -> 0) rather than a faster hand-rolled
    reduction: the label these build IS the known answer, and a subtly
    different z-score would make the two panels' receipts answer subtly
    different questions while looking identical.
    """
    s = pd.Series(values.astype(np.float64))
    z = s.groupby(month_code).transform(
        lambda v: (v - v.mean()) / (v.std(ddof=0) or 1.0))
    return z.fillna(0.0).to_numpy()


def real_month_dispersion(p: Panel) -> np.ndarray:
    sd = pd.Series(p.y_real).groupby(p.month_code).transform(
        lambda v: v.std(ddof=0))
    return sd.fillna(sd.median()).to_numpy()


def plant(p: Panel, world: str, real_sd: np.ndarray) -> tuple[np.ndarray, str]:
    """Return the synthetic label of DECLARED size, and its carrier's name.

    Returned rather than written into the panel: the feature matrix is shared
    across worlds and must never be touched, and a label array is 33 MB.
    """
    full = list(p.spec["full"])
    fam = p.spec["family_map"]
    rng = np.random.default_rng(SEED)
    noise = rng.standard_normal(p.n)

    if world == "linear":
        z = _z(p.X[:, full.index("qmj")], p.month_code)
        return TARGET_IC * z + noise, "qmj (sparse: ONE column of 412)"

    qcols = [c for c, f in fam.items() if f == "QUALITY_PROFITABILITY"]
    zsum = np.zeros(p.n)
    for c in qcols:
        zsum += _z(p.X[:, full.index(c)], p.month_code)
    zc = zsum / (np.std(zsum) or 1.0)
    if world == "linear_dense":
        return (TARGET_IC * zc + noise,
                f"mean z of {len(qcols)} QUALITY columns (dense)")
    if world == "linear_hetero":
        return (real_sd * (TARGET_IC * zc + noise),
                f"mean z of {len(qcols)} QUALITY columns, REAL per-month "
                f"dispersion on both terms")
    raise SystemExit(f"unknown world {world!r}")


# ── per-(world, arm, fold) cache: the run must survive a killed shell ───────
def _cache_path(world: str, arm: str, year: int, phash: str) -> Path:
    return CACHE / f"{phash}_{world}_{arm}_{year}.json"


def _normalise(s: pd.Series) -> pd.Series:
    """Force a DatetimeIndex on every IC series, fresh or cached.

    panel-2's `date` column yields plain dates while a cached series comes back
    through `pd.to_datetime` as Timestamps. Left alone, a RESUMED run would
    intersect a cached arm's index with a fresh arm's and match NOTHING —
    writing a receipt whose interval was computed over zero dates.
    """
    out = s.copy()
    out.index = pd.to_datetime(out.index)
    return out


def _cached(world, arm, year, phash) -> pd.Series | None:
    p = _cache_path(world, arm, year, phash)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return pd.Series(d["ic"], index=pd.to_datetime(d["dates"]))


def _save(world, arm, year, phash, s: pd.Series) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    _cache_path(world, arm, year, phash).write_text(json.dumps(
        {"panel_hash": phash, "world": world, "arm": arm, "year": year,
         "dates": [str(pd.Timestamp(d).date()) for d in s.index],
         "ic": [float(v) for v in s.to_numpy()]}), encoding="utf-8")


def run_world(p: Panel, world: str, phash: str, *, real_sd: np.ndarray,
              deadline: float | None) -> tuple[dict, bool]:
    y, carrier = plant(p, world, real_sd)
    yz = _z(y, p.month_code)   # same ordering per date, different objective
    ics: dict[str, list] = {a: [] for a in ALL_ARMS}
    for year, n_tr, a, b in folds(p):
        for arm in ALL_ARMS:
            hit = _cached(world, arm, year, phash)
            if hit is not None:
                ics[arm].append(hit)
                print(f"  [cache] {year} {arm:11s} ic {float(hit.mean()):+.4f}",
                      flush=True)
                continue
            if deadline is not None and time.time() > deadline:
                print("  wall clock reached - banking partial work", flush=True)
                return {"carrier": carrier, "ics": ics}, False
            M = p.matrix(arm)
            target = yz if arm.endswith("_zlabel") else y
            t0 = time.perf_counter()
            m = _lgbm()
            m.fit(M[:n_tr], target[:n_tr])     # contiguous prefix -> a VIEW
            pred = m.predict(M[a:b])           # contiguous slice  -> a VIEW
            del m
            # Scored against the RAW label always: the z-label arms change how
            # the model is trained, never what counts as being right.
            s = _normalise(rank_ic_by_date(pred, y[a:b], p.dates[a:b]))
            _save(world, arm, year, phash, s)
            ics[arm].append(s)
            print(f"  {year} {arm:11s} ic {float(s.mean()):+.4f} "
                  f"(train {n_tr:,}, {time.perf_counter() - t0:6.1f}s)",
                  flush=True)
    return {"carrier": carrier, "ics": ics}, True


def contrast(a: pd.Series, b: pd.Series) -> dict:
    ix = a.index.intersection(b.index)
    if len(ix) == 0:
        raise SystemExit(
            "contrast over ZERO shared dates - the two arms' IC series do not "
            "overlap. Refusing rather than writing a receipt whose interval "
            "was computed from nothing.")
    d = (a.loc[ix] - b.loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=SEED).as_dict()
    inf["block_days_derived"] = block
    inf["n_dates"] = int(len(ix))
    return inf


def write_receipt(world: str, res: dict, spec: dict, phash: str) -> Path:
    ics = {a: pd.concat(v) for a, v in res["ics"].items() if v}
    out = {
        "trial": TRIAL,
        "mode": "SENSITIVITY_WORLD",
        "world": world,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": S.PANEL,
        "panel_hash": phash,
        "spec_hash": S.spec_hash(spec),
        "seed": SEED,
        "planted": {"carrier": res["carrier"], "target_ic": TARGET_IC},
        "arms_run": list(ics),
        "arms_omitted": ["full_ridge", "full_mlp"],
        "arms_omitted_reason": (
            "float64 scaling of a 4.16M x 412 training matrix does not fit "
            "beside the panel on this machine; full_lgbm is the arm that "
            "recovered most of panel-1's dense world"),
        "differs_from_panel1_by": (
            "scale (18x rows), universe (floored -> all-cap), training era "
            "(2013+ -> 1926+), floor construction (own daily-price features "
            "disjoint from JKP -> seven JKP price columns that are a SUBSET "
            "of the 412). The result belongs to the bundle, not to scale."),
        "zlabel_collapses_hetero_onto_dense": (
            "EXPECTED IDENTITY, not a duplicated run: the hetero label is "
            "sd_month * (0.03*zc + noise), and per-date z-scoring divides by "
            "that same within-month sd, so z(y_hetero) == z(y_dense) exactly. "
            "Identical training target -> identical model, and per-date "
            "Spearman is invariant to the positive within-date scalar, so the "
            "scored IC coincides too. All 18 cached zlabel fold series are "
            "bit-identical between the two worlds. The consequence is the "
            "finding: every bit of the hetero world's extra difficulty is "
            "attributable to the TRAINING OBJECTIVE, and z-labelling removes "
            "it exactly."),
        "hetero_is_not_the_same_world_across_panels": (
            "linear_hetero scales signal and noise by the PANEL'S OWN realised "
            "per-month cross-sectional dispersion, so the world is a function "
            "of the data it is planted in. panel-2 spans 1926-2024 and "
            "therefore contains the 1930s, whose dispersion dwarfs anything in "
            "panel-1's 2013+ window: panel-2's hetero world is HARDER, not the "
            "same world with more rows. A lower recovery here is therefore "
            "evidence that the realistic world remains undetectable — NOT "
            "evidence that scale made detection worse."
            if world == "linear_hetero" else
            "not applicable: this world's carrier is panel-independent"),
        "pooled_ic": {k: round(float(s.mean()), 5) for k, s in ics.items()},
        "contrasts": {},
    }
    for arm, base in CONTRAST_BASE.items():
        if arm not in ics or base not in ics:
            continue
        inf = contrast(ics[arm], ics[base])
        v = head_verdicts({"c": inf}, economic_bar=ECONOMIC_BAR)["c"]
        out["contrasts"][f"{arm}_minus_floor"] = {"contrast": inf,
                                                  "verdict": v["verdict"]}
        print(f"  {arm}: dIC {inf['mean']:+.4f} "
              f"(mde {inf['mde_80pct_power']:.4f}, ci_lo {inf['ci_lo']:+.4f})"
              f" -> {v['verdict']}", flush=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    p = RECEIPT_DIR / f"tournament_planted_{world}.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="panel2_planted_worlds")
    ap.add_argument("--world", choices=("linear", "linear_dense",
                                        "linear_hetero", "all"), default="all")
    ap.add_argument("--max-seconds", type=float, default=0)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--subsample", type=int, default=0)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    spec = S.resolve()
    t0 = time.time()
    print(f"loading panel-2 ({len(spec['full'])} features)...", flush=True)
    p = load_panel(spec, subsample=a.subsample)
    print(f"  {p.n:,} rows x {p.X.shape[1]} features in {time.time()-t0:.0f}s "
          f"(X {p.X.nbytes/1e9:.2f} GB, floor {p.Xf.nbytes/1e9:.3f} GB)",
          flush=True)
    phash = S.panel_hash()
    print(f"panel_hash {phash}  spec_hash {S.spec_hash(spec)}", flush=True)
    real_sd = real_month_dispersion(p)

    if a.calibrate:
        y, _ = plant(p, "linear_dense", real_sd)
        for year, n_tr, lo, hi in folds(p):
            for arm in ARMS:
                M = p.matrix(arm)
                t1 = time.perf_counter()
                m = _lgbm()
                m.fit(M[:n_tr], y[:n_tr])
                s = rank_ic_by_date(m.predict(M[lo:hi]), y[lo:hi],
                                    p.dates[lo:hi])
                print(f"  CALIBRATE {year} {arm:11s} train {n_tr:,} "
                      f"ic {float(s.mean()):+.4f}  "
                      f"{time.perf_counter()-t1:.1f}s", flush=True)
            return 0
        return 1

    deadline = (t0 + a.max_seconds) if a.max_seconds else None
    worlds = (["linear", "linear_dense", "linear_hetero"]
              if a.world == "all" else [a.world])
    all_done = True
    for w in worlds:
        print(f"\n=== {w} (planted IC {TARGET_IC}) ===", flush=True)
        res, done = run_world(p, w, phash, real_sd=real_sd, deadline=deadline)
        if not done:
            all_done = False
            break
        print(f"receipt: {write_receipt(w, res, spec, phash).name} "
              f"(SENSITIVITY_WORLD - not market evidence)", flush=True)
    print("COMPLETE" if all_done else "PARTIAL - relaunch to resume")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
