"""RETURN-PANEL-TOURNAMENT-1 runner.

    python -m scripts.return_panel_tournament_run --null-world
    python -m scripts.return_panel_tournament_run --stage primary
    python -m scripts.return_panel_tournament_run --stage screen

Protocol: docs/TRIALS/PREREG_RETURN_PANEL_TOURNAMENT_1.md (frozen before
any model saw AEGIS-PANEL-1). Order is enforced, not hoped for: the
registered primary REFUSES to run without (a) a signature, (b) a PASS JKP
PIT-audit receipt, (c) a NULL_WORLD receipt from the same panel hash whose
outcome is NOT_ESTABLISHED inside its MDE. The §64 masked audit is written
before any verdict is computed.
"""

from __future__ import annotations

import argparse
import hashlib
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

from backend import config as _config                        # noqa: E402
from backend.services import aegis_panel as AP               # noqa: E402
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             bootstrap_block_dates,
                                             head_verdicts,
                                             rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

TRIAL = "RETURN-PANEL-TOURNAMENT-1"
PREREG = REPO / "docs" / "TRIALS" / "PREREG_RETURN_PANEL_TOURNAMENT_1.md"
OUT = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
PANEL_PATH = OUT / "aegis_panel_v1.parquet"
PIT_AUDIT = OUT / "jkp_pit_audit_2026-08-22.json"
NULL_RECEIPT = OUT / "tournament_null_world.json"
ECONOMIC_BAR = 0.01
SEED = 20260819
NULL_SEED = 20260822
TEST_YEARS = range(2016, 2025)
MIN_TRAIN = 20_000
LABEL = "ret_1m_fwd"


def _panel_hash() -> str:
    h = hashlib.sha256()
    with open(PANEL_PATH, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load():
    df = pd.read_parquet(PANEL_PATH)
    meta = json.loads((OUT / "aegis_panel_v1.meta.json")
                      .read_text(encoding="utf-8"))
    fam = meta["family_map"]
    floor = list(AP.FLOOR_FEATURES)
    full = floor + sorted(c for c, f in fam.items() if f != "PRICE_FLOOR")
    df["month"] = pd.PeriodIndex(df["month"], freq="M")
    return df, floor, full, fam


def _folds(df: pd.DataFrame):
    for y in TEST_YEARS:
        jan = pd.Period(f"{y}-01", freq="M")
        tr = df[(df["month"] + 1 < jan) & df[LABEL].notna()]
        te = df[(df["month"].dt.year == y) & df[LABEL].notna()]
        if len(tr) < MIN_TRAIN or not len(te):
            print(f"  fold {y} REFUSED (train {len(tr)}, test {len(te)})")
            continue
        yield y, tr, te


def _sk_pipe(model):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(SimpleImputer(strategy="median"),
                         StandardScaler(), model)


def _arm_factories():
    from lightgbm import LGBMRanker, LGBMRegressor
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor

    def lgbm():
        return LGBMRegressor(n_estimators=300, num_leaves=31,
                             learning_rate=0.05, random_state=SEED,
                             verbose=-1)

    return {
        "floor_lgbm": ("floor", lgbm),
        "full_lgbm": ("full", lgbm),
        "full_ridge": ("full", lambda: _sk_pipe(Ridge(alpha=1.0))),
        "full_mlp": ("full", lambda: _sk_pipe(
            MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=200,
                         random_state=SEED))),
        "full_lgbm_rank": ("full", lambda: LGBMRanker(
            objective="lambdarank", n_estimators=300, num_leaves=31,
            learning_rate=0.05, random_state=SEED, verbose=-1)),
    }


def _fit_predict(arm: str, mk, cols, tr, te, label: str = LABEL
                 ) -> np.ndarray:
    Xtr, Xte = tr[cols].to_numpy(), te[cols].to_numpy()
    if arm == "full_lgbm_rank":
        rel = (tr.groupby("month")[label]
               .transform(lambda s: pd.qcut(s.rank(method="first"), 10,
                                            labels=False)))
        order = tr["month"].argsort(kind="stable").to_numpy()
        m = mk()
        srt = tr.iloc[order]
        m.fit(srt[cols].to_numpy(),
              rel.iloc[order].to_numpy().astype(int),
              group=srt.groupby("month", sort=True).size().to_list())
        return m.predict(Xte)
    m = mk()
    m.fit(Xtr, tr[label].to_numpy())
    return m.predict(Xte)


CACHE_DIR = OUT / "screen_cache"


def _cache_load(key: str, panel_hash: str) -> pd.Series | None:
    p = CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("panel_hash") != panel_hash:
        # a rebuilt panel invalidates every cached arm — a stale entry
        # merged into a fresh run would silently mix result eras
        print(f"  [cache] {key} STALE (panel hash changed) — recomputing")
        return None
    return pd.Series(d["ic"], index=pd.to_datetime(d["dates"]))


def _cache_save(key: str, s: pd.Series, panel_hash: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(
        {"panel_hash": panel_hash,
         "dates": [str(d.date()) for d in s.index],
         "ic": [float(v) for v in s.to_numpy()]}), encoding="utf-8")


def cached_arm(key: str, fn, panel_hash: str) -> pd.Series:
    """Per-arm IC series cache so a wall-clock-bounded screen run resumes
    instead of restarting. Every entry is stamped with the panel hash and
    a mismatch recomputes — never merges."""
    s = _cache_load(key, panel_hash)
    if s is not None:
        print(f"  [cache] {key}  ic {float(s.mean()):+.4f}")
        return s
    s = fn()
    _cache_save(key, s, panel_hash)
    return s


def run_arms(df, floor, full, arms: list[str], label=LABEL) -> dict:
    facs = _arm_factories()
    ics: dict[str, list] = {a: [] for a in arms}
    for y, tr, te in _folds(df):
        tr = tr[tr[label].notna()]
        te = te[te[label].notna()]
        for a in arms:
            kind, mk = facs[a]
            cols = floor if kind == "floor" else full
            t0 = time.perf_counter()
            pred = _fit_predict(a, mk, cols, tr, te, label=label)
            s = rank_ic_by_date(pred, te[label].to_numpy(),
                                te["date"].to_numpy())
            ics[a].append(s)
            print(f"  {y} {a:16s} ic {float(s.mean()):+.4f} "
                  f"({time.perf_counter() - t0:6.1f}s)", flush=True)
    return {a: pd.concat(v) for a, v in ics.items() if v}


def paired_contrast(ic_a: pd.Series, ic_b: pd.Series, seed=SEED) -> dict:
    ix = ic_a.index.intersection(ic_b.index)
    d = (ic_a.loc[ix] - ic_b.loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=seed).as_dict()
    inf["block_days_derived"] = block
    inf["n_dates"] = int(len(ix))
    return inf


def _null_world_ok() -> dict | None:
    if not NULL_RECEIPT.exists():
        return None
    r = json.loads(NULL_RECEIPT.read_text(encoding="utf-8"))
    # prereg §5 erratum 2026-08-22: the gate is the absence of a WIN on
    # noise (powered nulls correctly return the noninferiority verdict)
    ok = (r.get("panel_hash") == _panel_hash()
          and r.get("verdict") not in ("COMPLEX_WINS", "INFORMATION_ADDS")
          and r.get("within_mde") is True)
    return r if ok else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="return_panel_tournament_run")
    ap.add_argument("--null-world", action="store_true")
    ap.add_argument("--planted-world",
                    choices=("linear", "linear_dense", "nonlinear"),
                    default="", help="sensitivity validation: replace the "
                    "label with a synthetic one of DECLARED size built "
                    "from real features; measures what the instrument "
                    "can FIND (sparse single-column vs dense family)")
    ap.add_argument("--stage", choices=("primary", "screen"),
                    default="primary")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    signer = assert_signed(PREREG)
    audit = json.loads(PIT_AUDIT.read_text(encoding="utf-8"))
    if audit.get("verdict") != "PASS":
        raise SystemExit(f"JKP PIT audit is {audit.get('verdict')!r}, "
                         f"not PASS — the panel may not be opened.")
    df, floor, full, fam = _load()
    phash = _panel_hash()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{TRIAL}  signer: {signer[:40]}  panel {phash}  "
          f"rows {len(df):,}")

    if a.planted_world:
        # SENSITIVITY WORLD — the complement of the null world. The null
        # proved the pipeline refuses noise; this proves it can DETECT a
        # planted signal of roughly the declared economic size, carried by
        # JKP columns the floor cannot see. Nothing here is market
        # evidence; the receipt says so.
        rng = np.random.default_rng(20260823)
        df = df.copy()

        def _z(col):
            z = df.groupby("month")[col].transform(
                lambda s: (s - s.mean()) / (s.std(ddof=0) or 1.0))
            return z.fillna(0.0).to_numpy()

        noise = rng.standard_normal(len(df))
        if a.planted_world == "linear":
            planted_ic, carrier = 0.03, "qmj (sparse: ONE column of 419)"
            df[LABEL] = 0.03 * _z("qmj") + noise
            expect = ("sparse needle: planted R^2 0.0009 sits near the "
                      "419/200k selection-noise floor — partial recovery "
                      "at best; the point is to MEASURE it")
        elif a.planted_world == "linear_dense":
            fam_map = json.loads(
                (OUT / "aegis_panel_v1.meta.json").read_text(
                    encoding="utf-8"))["family_map"]
            qcols = [c for c, f in fam_map.items()
                     if f == "QUALITY_PROFITABILITY"]
            planted_ic = 0.03
            carrier = f"mean z of {len(qcols)} QUALITY columns (dense)"
            zsum = np.zeros(len(df))
            for c in qcols:
                zsum += _z(c)
            zc = zsum / np.std(zsum)
            df[LABEL] = 0.03 * zc + noise
            expect = ("dense family carrier — the realistic shape of "
                      "factor signal; full_lgbm should recover most of "
                      "0.03 and clear the verdict")
        else:
            planted_ic, carrier = 0.05, "qmj*be_me (pure interaction)"
            df[LABEL] = 0.05 * _z("qmj") * _z("be_me") + noise
            expect = ("full_lgbm recovers part of the interaction; "
                      "full_ridge sees ~nothing (zero linear projection)")
        arms = (["floor_lgbm", "full_lgbm"]
                if a.planted_world == "linear"
                else ["floor_lgbm", "full_lgbm", "full_ridge"])
        ics = run_arms(df, floor, full, arms)
        # z-label variant: train on the per-date z-scored label. Per-date
        # Spearman is invariant to per-date monotone transforms, so this
        # changes ONLY the training objective — the hypothesis under test
        # is that pooled MSE on RAW returns drowns cross-sectional signal
        # in cross-date vol dispersion. An instrument finding here earns a
        # successor registration; it never touches real labels directly.
        dfz = df.copy()
        dfz[LABEL] = dfz.groupby("month")[LABEL].transform(
            lambda s: (s - s.mean()) / (s.std(ddof=0) or 1.0))
        for k, s in run_arms(dfz, floor, full,
                             ["floor_lgbm", "full_lgbm"]).items():
            ics[f"{k}_zlabel"] = s
        out = {"trial": TRIAL, "mode": "SENSITIVITY_WORLD",
               "world": a.planted_world, "at": stamp,
               "panel_hash": phash, "seed": 20260823,
               "planted": {"carrier": carrier, "target_ic": planted_ic},
               "expectation": expect,
               "pooled_ic": {k: round(float(s.mean()), 5)
                             for k, s in ics.items()},
               "contrasts": {}}
        for arm in [x for x in ics if x != "floor_lgbm"]:
            base = ("floor_lgbm_zlabel" if arm.endswith("_zlabel")
                    and arm != "floor_lgbm_zlabel" else "floor_lgbm")
            inf = paired_contrast(ics[arm], ics[base])
            v = head_verdicts({"c": inf}, economic_bar=ECONOMIC_BAR)["c"]
            out["contrasts"][f"{arm}_minus_floor"] = {
                "contrast": inf, "verdict": v["verdict"]}
            print(f"  {arm}: dIC {inf['mean']:+.4f} "
                  f"(mde {inf['mde_80pct_power']:.4f}) -> {v['verdict']}")
        p = OUT / f"tournament_planted_{a.planted_world}.json"
        p.write_text(json.dumps(out, indent=2, default=str),
                     encoding="utf-8")
        print(f"receipt: {p.name} (SENSITIVITY_WORLD — not market "
              f"evidence)")
        return 0

    if a.null_world:
        rng = np.random.default_rng(NULL_SEED)
        df = df.copy()
        df[LABEL] = (df.groupby("month")[LABEL]
                     .transform(lambda s: s.to_numpy()[
                         rng.permutation(len(s))]))
        print("NULL WORLD — labels permuted within formation date")
        ics = run_arms(df, floor, full, ["floor_lgbm", "full_lgbm"])
        inf = paired_contrast(ics["full_lgbm"], ics["floor_lgbm"])
        v = head_verdicts({"c": inf}, economic_bar=ECONOMIC_BAR)["c"]
        within = bool(abs(inf["mean"]) < inf["mde_80pct_power"])
        receipt = {"trial": TRIAL, "mode": "NULL_WORLD", "at": stamp,
                   "panel_hash": phash, "seed": NULL_SEED,
                   "contrast": inf, "verdict": v["verdict"],
                   "within_mde": within,
                   "pooled_ic": {k: round(float(s.mean()), 5)
                                 for k, s in ics.items()}}
        NULL_RECEIPT.write_text(json.dumps(receipt, indent=2,
                                           default=str), encoding="utf-8")
        print(f"NULL WORLD verdict {v['verdict']}  dIC {inf['mean']:+.5f} "
              f"(mde {inf['mde_80pct_power']:.5f})  within_mde={within}")
        if not within or v["verdict"] == "COMPLEX_WINS":
            print("!! SIGNAL FOUND IN NOISE — halt everything; this "
                  "receipt is the finding.")
            return 1
        print("null world clean: no win on noise, inside MDE.")
        return 0

    if a.stage == "primary":
        if _null_world_ok() is None:
            raise SystemExit("no valid NULL_WORLD receipt for this panel "
                             "hash — run --null-world first (prereg §5).")
        ics = run_arms(df, floor, full, ["floor_lgbm", "full_lgbm"])
        inf = paired_contrast(ics["full_lgbm"], ics["floor_lgbm"])

        # §64 masked audit BEFORE any verdict
        masked = {k: v for k, v in inf.items() if k != "mean"}
        audit64 = {"audit": f"{TRIAL} §64 (mean masked here)",
                   "at": stamp, **masked,
                   "economic_bar": ECONOMIC_BAR,
                   "win_limb_answerable": True,
                   "noninferior_limb_answerable":
                       bool(inf["mde_80pct_power"] <= ECONOMIC_BAR)}
        (OUT / "tournament_primary_audit.json").write_text(
            json.dumps(audit64, indent=2, default=str), encoding="utf-8")
        print("§64:", json.dumps({k: audit64[k] for k in
                                  ("n_dates", "se", "mde_80pct_power",
                                   "noninferior_limb_answerable")},
                                 default=str))

        v = head_verdicts({"full_minus_floor": inf},
                          economic_bar=ECONOMIC_BAR)["full_minus_floor"]
        relabel = {"COMPLEX_WINS": "INFORMATION_ADDS",
                   "LINEAR_NONINFERIOR": "FLOOR_NONINFERIOR",
                   "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
        v["verdict"] = relabel[v["verdict"]]

        # ADOPT gate: the full arm's own pooled IC, block-bootstrapped
        zeros = pd.Series(0.0, index=ics["full_lgbm"].index)
        own = paired_contrast(ics["full_lgbm"], zeros)
        adopt = bool(v["verdict"] == "INFORMATION_ADDS"
                     and own["mean"] >= ECONOMIC_BAR
                     and own["ci_lo"] > 0.0)
        receipt = {"trial": TRIAL, "mode": "REGISTERED", "stage": "primary",
                   "at": stamp, "signed_by": signer, "panel_hash": phash,
                   "pit_audit": PIT_AUDIT.name,
                   "primary": {"cell": "full_lgbm - floor_lgbm, "
                                       "ret_1m_fwd rank IC",
                               "contrast": inf, "verdict": v},
                   "full_arm_own_ic": own,
                   "adopt_grade": adopt,
                   "pooled_ic": {k: round(float(s.mean()), 5)
                                 for k, s in ics.items()},
                   "ic_by_year": {k: {int(y): round(float(g.mean()), 4)
                                      for y, g in s.groupby(
                                          s.index.year)}
                                  for k, s in ics.items()}}
        p = OUT / "tournament_primary.json"
        p.write_text(json.dumps(receipt, indent=2, default=str),
                     encoding="utf-8")
        print(f"PRIMARY: {v['verdict']}  dIC {inf['mean']:+.4f} "
              f"(mde {inf['mde_80pct_power']:.4f})  "
              f"full-arm IC {own['mean']:+.4f}  adopt_grade={adopt}")
        print("receipt:", p.name)
        return 0

    # ── screen stage ───────────────────────────────────────────────────────
    if not (OUT / "tournament_primary.json").exists():
        raise SystemExit("primary receipt missing — screens follow the "
                         "primary, never precede it.")
    prim = json.loads((OUT / "tournament_primary.json")
                      .read_text(encoding="utf-8"))
    ics = {a: cached_arm(f"arm_{a}", lambda a=a: run_arms(
               df, floor, full, [a])[a], phash)
           for a in ("floor_lgbm", "full_lgbm", "full_ridge",
                     "full_lgbm_rank", "full_mlp")}
    screen = {"model_ordering": {}}
    for arm in ("full_ridge", "full_mlp", "full_lgbm_rank"):
        if arm in ics:
            screen["model_ordering"][f"{arm}_minus_full_lgbm"] = \
                paired_contrast(ics[arm], ics["full_lgbm"])
    fams = sorted({f for f in fam.values() if f != "PRICE_FLOOR"})
    screen["family_alone_vs_floor"] = {}
    for f in fams:
        cols = floor + [c for c, ff in fam.items() if ff == f]
        fic = cached_arm(f"family_{f}", lambda cols=cols: run_arms(
            df, floor, cols, ["full_lgbm"])["full_lgbm"], phash)
        screen["family_alone_vs_floor"][f] = {
            "pooled_ic": round(float(fic.mean()), 5),
            "contrast_vs_floor": paired_contrast(fic,
                                                 ics["floor_lgbm"])}
        print(f"  family {f:24s} ic "
              f"{screen['family_alone_vs_floor'][f]['pooled_ic']:+.4f}")
    vol_ics = {a: cached_arm(f"vol_{a}", lambda a=a: run_arms(
                   df, floor, full, [a], label="fwd_vol_21d")[a], phash)
               for a in ("floor_lgbm", "full_lgbm")}
    screen["vol_cross_check"] = {k: round(float(s.mean()), 4)
                                 for k, s in vol_ics.items()}
    receipt = {"trial": TRIAL, "mode": "REGISTERED", "stage": "screen",
               "at": stamp, "signed_by": signer, "panel_hash": phash,
               "primary_receipt_at": prim["at"],
               "pooled_ic": {k: round(float(s.mean()), 5)
                             for k, s in ics.items()},
               "ic_by_year": {k: {int(y): round(float(g.mean()), 4)
                                  for y, g in s.groupby(s.index.year)}
                              for k, s in ics.items()},
               "screen": screen,
               "discipline": "SCREEN = BH-FDR(m=run) per §63; nothing "
                             "here decides; export claims go through "
                             "Holm on a successor registration"}
    p = OUT / "tournament_screen.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
