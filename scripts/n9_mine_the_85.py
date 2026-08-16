"""N9 — can ANY rule in the existing grammar mark the moves the library misses?

    python -m scripts.n9_mine_the_85

Registered at `docs/TRIALS/PREREG_N9_MINE_THE_85.md` before this file computed
anything.

THE QUESTION THAT COMES BEFORE PAYING FOR AUTOPSIES
===================================================
Order 3 ranks "mine the 85%" highest: run the autopsy machinery on exceptional
moves that had no precursor, so N4's null becomes a generator. Right shape. But
an LLM autopsy's output must COMPILE into `autopsy.TRANSFERABLE_FEATURES` — the
eight-feature vocabulary — or it is refused at the door. So one question comes
first and costs nothing:

    does any rule expressible in that vocabulary mark the uncovered moves?

If nothing does, no story compiled into it will either, and the constraint is
the GRAMMAR rather than the moves. That changes what the dollar should buy.

WHY AN EXHAUSTIVE SEARCH IS HONEST HERE AND USUALLY IS NOT
==========================================================
Enumerating ~9,000 rules and reporting the best is data mining. It becomes an
instrument when three things are true, and all three are enforced below:

1. **The denominator is printed.** The exact candidate count is the
   multiple-comparison denominator and every survivor is quoted against it.
2. **Selection and evaluation do not share data.** Candidates are chosen on
   three securities before 2016 and scored once on three DIFFERENT securities
   after 2016. No re-tuning, no second look.
3. **The bar was set elsewhere.** `L_min` comes from N4B's break-even
   de-risking economics, computed for a different experiment before this file
   existed.

The output is CANDIDATES, never claims. Nothing here is promoted by this script.

AND THE INFORMATIVE OUTCOME MAY BE THE IN-SAMPLE ONE
====================================================
If no rule clears the bar even on TRAIN — with the outcome known, on the data
the rule was chosen from — that is not a weak result. It says the vocabulary
cannot express a rule that marks these moves at all, which is a statement about
the language and is the one finding here that would close something.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import market_stress as MS
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n9_mine_the_85.json"
AUTOPSIES = _config.OPTIMUS_LEDGER_DIR / "research_gym"

TRAIN_SECURITIES = ("SPY", "XLF", "XLE")
FOREIGN_SECURITIES = ("QQQ", "IWM", "XLK")
#: AMENDMENT 1. Six securities in NEITHER slice, declared in the prereg before
#: they were touched. The rules selected on train are frozen — no re-selection,
#: no re-tuning — and scored once here. This is the confirmation of an
#: aggregate test that was itself designed after seeing the per-rule failure,
#: which is exactly why it needs one.
CONFIRM_SECURITIES = ("DIA", "XLV", "XLI", "XLP", "XLU", "XLB")
TRAIN_END = "2015-12-31"
FOREIGN_START = "2016-01-01"

HORIZONS = (20, 60)
TAIL_Q = 0.10
SEED = 20260816
#: Block shifts of the FOREIGN forward returns, for the aggregate placebo.
N_PLACEBO = 200

#: N4B's break-even de-risking lift, per horizon. Inherited, not invented here.
L_MIN = {20: 1.69, 60: 2.11}

#: The eight-feature transferable vocabulary, minus `security` (a rule over the
#: ticker is a rule about which market you are in) and `vix_bucket` (a coarsening
#: of `vix`, already covered by thresholding it).
SEARCH_FEATURES = ("vix", "drawdown_pct", "ret_1m_pct", "ret_3m_pct",
                   "ret_6m_pct", "realised_vol_20d", "vol_ratio_20_60",
                   "stress_pctile")

#: Thresholds at the deciles of the TRAINING distribution. Deciles rather than
#: a fixed grid so the same code works on a feature measured in points and one
#: measured in [0, 1] — and so a threshold means the same thing across
#: securities with different scales.
QUANTILES = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def _latest_autopsies() -> Path | None:
    files = sorted(AUTOPSIES.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--confirm", action="store_true",
                    help="also score the FROZEN train-selected rules on the "
                         "six confirmation securities (prereg amendment 1)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf

    # ── the incumbent library, so "uncovered" means uncovered by IT ─────────
    path = Path(a.autopsies) if a.autopsies else _latest_autopsies()
    if path is None:
        print("no autopsy file")
        return 1
    incumbent = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        au = (json.loads(ln).get("autopsy") or {})
        spec = au.get("affected_precursor") or au.get("executable_precursor")
        if not spec:
            continue
        try:
            incumbent.append(AU.compile_precursor(spec))
        except Exception:                                        # noqa: BLE001
            pass
    print(f"incumbent library: {len(incumbent)} compiled precursors "
          f"from {path.name}")

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    universe = (tuple(TRAIN_SECURITIES) + tuple(FOREIGN_SECURITIES)
                + (tuple(CONFIRM_SECURITIES) if a.confirm else ()))
    frames: dict[str, pd.DataFrame] = {}
    for tkr in universe:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change().dropna()
        rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
        rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
        roll_max = px.rolling(252, min_periods=20).max()
        df = pd.DataFrame({
            # Every state term is shifted: read at the close BEFORE the window
            # it labels, so a rule can never see the move it is marking.
            "vix": vix.reindex(r.index).ffill().shift(1),
            "drawdown_pct": ((px / roll_max - 1.0) * 100.0).shift(1),
            "ret_1m_pct": (px.pct_change(21) * 100.0).shift(1),
            "ret_3m_pct": (px.pct_change(63) * 100.0).shift(1),
            "ret_6m_pct": (px.pct_change(126) * 100.0).shift(1),
            "realised_vol_20d": rv20.shift(1),
            "vol_ratio_20_60": (rv20 / rv60).shift(1),
        }, index=r.index)
        df["stress_pctile"] = MS.stress_pctile(
            rv20.shift(1).tolist())
        df["security"] = tkr
        for H in HORIZONS:
            df[f"fwd_{H}"] = ((px.shift(-H) / px - 1.0) * 100.0).reindex(r.index)

        # The incumbent's firing mask, evaluated exactly as N4 evaluates it.
        recs = df[list(AU.TRANSFERABLE_FEATURES & set(df.columns))].to_dict(
            "records")
        fired = np.zeros(len(df), dtype=bool)
        for fn in incumbent:
            for i, rec in enumerate(recs):
                if fired[i]:
                    continue
                try:
                    if fn(rec):
                        fired[i] = True
                except Exception:                                # noqa: BLE001
                    pass
        df["incumbent_fired"] = fired
        frames[tkr] = df
        print(f"  {tkr}: {len(df)} days, incumbent fires "
              f"{100.0 * fired.mean():.1f}%")

    # ── build the candidate grammar from the TRAINING distribution only ─────
    train = pd.concat([frames[t].loc[:TRAIN_END] for t in TRAIN_SECURITIES])
    clauses: list[tuple[str, str, float]] = []
    for f in SEARCH_FEATURES:
        col = train[f].replace([np.inf, -np.inf], np.nan).dropna()
        if len(col) < 500:
            print(f"  (feature {f} has too little training history — skipped)")
            continue
        for q in QUANTILES:
            thr = float(np.quantile(col, q))
            clauses.append((f, ">=", thr))
            clauses.append((f, "<=", thr))

    singles = [(c,) for c in clauses]
    pairs = [(x, y) for x, y in itertools.combinations(clauses, 2)
             if x[0] != y[0]]
    candidates = singles + pairs
    print(f"\nSEARCH DENOMINATOR: {len(candidates)} candidate rules "
          f"({len(singles)} single-clause, {len(pairs)} two-clause). "
          f"Every survivor is quoted against this number.")

    def _mask(df: pd.DataFrame, cand) -> "np.ndarray":
        m = np.ones(len(df), dtype=bool)
        for feat, op, thr in cand:
            col = df[feat].to_numpy(dtype=float)
            with np.errstate(invalid="ignore"):
                ok = (col >= thr) if op == ">=" else (col <= thr)
            m &= np.where(np.isnan(col), False, ok)
        return m

    def _slice(secs, lo=None, hi=None) -> pd.DataFrame:
        parts = []
        for t in secs:
            d = frames[t]
            if lo:
                d = d.loc[lo:]
            if hi:
                d = d.loc[:hi]
            parts.append(d)
        return pd.concat(parts)

    def _score(df: pd.DataFrame, H: int, cand) -> dict | None:
        """Lift of `cand` over the exceptional moves the INCUMBENT missed."""
        f = df[f"fwd_{H}"].to_numpy(dtype=float)
        ok = ~np.isnan(f)
        if ok.sum() < 500:
            return None
        f = f[ok]
        inc = df["incumbent_fired"].to_numpy()[ok]
        fire = _mask(df, cand)[ok]
        cut = float(np.quantile(f, TAIL_Q))
        # THE TARGET: bottom-decile moves the incumbent did NOT mark. A rule
        # that re-finds what the six already catch adds nothing to coverage.
        uncovered = (f <= cut) & (~inc)
        if uncovered.sum() < 30:
            return None
        base = float(fire.mean())
        if base <= 0.005 or base >= 0.60:
            # A rule that never fires cannot cover anything, and one that fires
            # on most days "covers" by doing nothing (the PCI trap N4 names).
            return None
        cov = float(fire[uncovered].mean())
        lift = cov / base
        # n_effective: H-day windows sampled daily, bounded by the count of
        # distinct firing EPISODES more than 21 days apart.
        pos = np.flatnonzero(fire & uncovered)
        n_eff = PW.effective_n(int(uncovered.sum()), H,
                               n_episodes=PW.count_episodes(pos.tolist()))
        se = PW.se_proportion(cov, n_eff)
        # MDE of the LIFT, which is the coverage MDE divided by the base rate.
        mde = (PW.mde_from_se(se) / base) if se else None
        return {"lift": lift, "coverage": cov, "base_rate": base,
                "n_uncovered": int(uncovered.sum()),
                "n_fired_uncovered": int((fire & uncovered).sum()),
                "n_effective": n_eff, "mde_lift": mde}

    def _aggregate(df: "pd.DataFrame", H: int, selected, label: str) -> dict | None:
        """Does the SELECTED SET transfer to `df`, against a measured null?

        One question instead of N underpowered ones. The null is BLOCK-SHIFTED
        rather than assumed: a set chosen for high train lift has no null of
        1.0, and SS20 records that permuted-label placebos in this programme are
        not centred where theory says they should be.
        """
        got = [s["lift"] for cand, _ in selected
               if (s := _score(df, H, cand)) is not None]
        if not got:
            return None
        obs = sorted(got)[len(got) // 2]
        rng = np.random.default_rng(SEED + H)
        shuffled = df.copy()
        src = df[f"fwd_{H}"].to_numpy(dtype=float)
        meds = []
        for _ in range(N_PLACEBO):
            # Circular block shift: breaks the state -> outcome link while
            # preserving the forward return's own autocorrelation, so the
            # placebo is not made easy by destroying the series structure.
            k = int(rng.integers(H * 2, max(len(src) - H * 2, H * 2 + 1)))
            shuffled[f"fwd_{H}"] = np.roll(src, k)
            g = [s["lift"] for cand, _ in selected
                 if (s := _score(shuffled, H, cand)) is not None]
            if g:
                meds.append(sorted(g)[len(g) // 2])
        if not meds:
            return None
        ms = sorted(meds)
        p = (sum(1 for m in meds if m >= obs) + 1) / (len(meds) + 1)
        out = {"slice": label, "n_rules_scored": len(got),
               "observed_median_lift": obs, "placebo_median": ms[len(ms) // 2],
               "placebo_p95": ms[int(0.95 * len(ms))], "n_placebo": len(meds),
               "p_value": p}
        print(f"  AGGREGATE [{label}] — median lift of the selected set: "
              f"{obs:.3f}  ({len(got)} rules scored)")
        print(f"    placebo ({len(meds)} block shifts): median "
              f"{out['placebo_median']:.3f}  p95 {out['placebo_p95']:.3f}"
              f"  ->  p = {p:.3f}")
        print(f"    -> {'the SET transfers' if p < 0.05 else 'indistinguishable from label-broken selection'}")
        return out

    results: dict = {"denominator": len(candidates), "horizons": {},
                     "train_securities": list(TRAIN_SECURITIES),
                     "foreign_securities": list(FOREIGN_SECURITIES),
                     "train_end": TRAIN_END, "foreign_start": FOREIGN_START,
                     "L_min": L_MIN, "seed": SEED}

    tr = _slice(TRAIN_SECURITIES, hi=TRAIN_END)
    fo = _slice(FOREIGN_SECURITIES, lo=FOREIGN_START)

    for H in HORIZONS:
        bar = L_MIN[H]
        print(f"\n{'=' * 70}\nH={H}d — bar is N4B's break-even lift {bar}")
        train_pass = []
        for cand in candidates:
            s = _score(tr, H, cand)
            if s and s["lift"] >= bar:
                train_pass.append((cand, s))
        train_pass.sort(key=lambda kv: -kv[1]["lift"])
        print(f"  cleared on TRAIN: {len(train_pass)} / {len(candidates)}")

        if not train_pass:
            print("  -> nothing in the grammar marks these moves even IN "
                  "SAMPLE, with the outcome known. That is a finding about the "
                  "VOCABULARY, not about the moves.")
            results["horizons"][str(H)] = {"train_pass": 0, "foreign_pass": 0,
                                           "survivors": [],
                                           "verdict": "GRAMMAR_CANNOT_EXPRESS_IT"}
            continue

        survivors = []
        # SS37: check the kill as hard as the pass. "Zero survived" means two
        # completely different things depending on WHERE the foreign lifts
        # landed, and a run that prints only the count cannot tell them apart:
        #   * foreign lift ~1.0  -> the train pass was overfitting. A real null.
        #   * foreign lift ~bar but MDE wider -> underpowered. Says nothing.
        foreign_lifts, point_pass, unscored = [], 0, 0
        for cand, s_tr in train_pass:
            s_fo = _score(fo, H, cand)
            if not s_fo:
                unscored += 1
                continue
            foreign_lifts.append(s_fo["lift"])
            if s_fo["lift"] >= bar:
                point_pass += 1
            clears = (s_fo["mde_lift"] is not None
                      and s_fo["lift"] - s_fo["mde_lift"] > bar)
            if clears:
                survivors.append({
                    "rule": [{"feature": f, "op": o, "value": round(v, 4)}
                             for f, o, v in cand],
                    "train": s_tr, "foreign": s_fo})
        # How many of `train_pass` would clear FOREIGN by chance alone at a
        # one-sided 5% test. Printed beside the count so the reader never has
        # to work out whether the survivors are more than the noise floor.
        expected_by_chance = 0.05 * len(train_pass)
        print(f"  cleared on FOREIGN: {len(survivors)}   "
              f"(point estimate alone would pass {point_pass})   "
              f"expected by chance from {len(train_pass)} looks: "
              f"~{expected_by_chance:.1f} at a 5% test — the acceptance rule "
              f"here is STRICTER than that, so this is an upper bound")
        if foreign_lifts:
            fl = sorted(foreign_lifts)
            q = lambda p: fl[min(int(p * len(fl)), len(fl) - 1)]   # noqa: E731
            print(f"  FOREIGN lift of the {len(fl)} train-passers: "
                  f"median {q(0.5):.2f}  p10 {q(0.10):.2f}  p90 {q(0.90):.2f}  "
                  f"max {fl[-1]:.2f}   ({unscored} unscoreable)")
            print(f"    -> {'OVERFIT: they collapse to the base rate' if q(0.5) < 1.25 else 'they hold up in point terms; the failure is POWER'}")
        for s in survivors[:10]:
            rule = " AND ".join(f"{c['feature']} {c['op']} {c['value']}"
                                for c in s["rule"])
            print(f"    lift {s['foreign']['lift']:5.2f} "
                  f"(MDE {s['foreign']['mde_lift']:4.2f}, "
                  f"n_eff {s['foreign']['n_effective']:5.1f}, "
                  f"fires {100 * s['foreign']['base_rate']:4.1f}%)  {rule}")
        # ── the aggregate test, because the per-rule ones are underpowered ──
        # 461 near-duplicate rules each failing its own MDE is not 461 pieces
        # of evidence for nothing; it is one underpowered instrument used 461
        # times. The powered version asks ONE question — does the SELECTED SET
        # transfer — and it needs a placebo, because a set selected for high
        # train lift does not have a null of 1.0 (SS20: permuted-label placebos
        # are not centred on zero, measured 2026-08-12).
        placebo = _aggregate(fo, H, train_pass, "foreign") if foreign_lifts else None
        confirm = (_aggregate(_slice(CONFIRM_SECURITIES), H, train_pass,
                              "confirmation (amendment 1)")
                   if (a.confirm and train_pass) else None)

        results["horizons"][str(H)] = {
            "placebo": placebo,
            "train_pass": len(train_pass), "foreign_pass": len(survivors),
            "foreign_point_pass": point_pass,
            "foreign_lift_median": (sorted(foreign_lifts)[len(foreign_lifts) // 2]
                                    if foreign_lifts else None),
            "foreign_lift_max": max(foreign_lifts) if foreign_lifts else None,
            "expected_by_chance": expected_by_chance,
            "survivors": survivors[:50],
            "verdict": ("CANDIDATE_GENERATED" if
                        len(survivors) > expected_by_chance
                        else "NOT_DETECTABLE_IN_SCOPE")}

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1), and a "
          "survivor count at or below the chance expectation is not a "
          "discovery however good the best row looks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
