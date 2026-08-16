"""N21 — what does the precursor policy actually PAY, on securities nobody read?

    python -m scripts.n21_policy_utility --freeze       # 1. select + hash rules
    python -m scripts.n21_policy_utility --power-only   # 2. dispersion, no U
    python -m scripts.n21_policy_utility                # 3. the test

WHY THIS EXISTS
===============
Every result so far prices the precursors through a MODEL of the action:

    L_min = (mu_rest + c) / ( q * (|mu_tail| + mu_rest) )

N4B derived it, Order 4 discovered `mu_rest` sits in the numerator, Order 5
found delta cancels, N20 measured the conditional numerator and found it moved
the bar the wrong way. Four results, all about one algebraic object, none of
them a measurement of what the policy earns.

This measures what the policy earns.

    Delta U  =  U(precursor de-risking)  -  U(buy and hold)

under a DECLARED utility, net of declared costs, on securities no trial in the
register has ever read. That is the mission's own objective — terminal wealth
under a declared utility, not coverage, not lift, not classification.

THE THREE STAGES ARE THE DISCIPLINE
===================================
`--freeze` re-derives N9's train-selected rules from SPY/XLF/XLE up to
2015-12-31 and writes them with a SHA-256. It cannot see the fresh slice: the
fresh tickers are not in the universe it downloads. The prereg then quotes the
hash, so "the rules were frozen first" is checkable rather than asserted.

`--power-only` reads the fresh slice's PRICES to measure the dispersion of the
block-level utility difference, and never computes a utility difference for the
policy — it estimates dispersion from a policy-free surrogate. This is the one
place the fresh data is touched before the decision rule is committed, and it
is touched for a quantity the hypothesis cannot move.

Then, and only then, the run.

THE UNIT PROBLEM, FACED RATHER THAN AVOIDED
===========================================
Terminal wealth over one path is ONE number per security. Eight co-moving ETFs
give an effective sample near one, and a test with n_eff = 1 cannot resolve
anything — which is exactly the class of error R13c was written to refuse.

So the outcome is the utility difference over **non-overlapping half-year
blocks**, and the dependence unit is the block ACROSS the whole cross-section,
never the security-block. That is declared in the prereg and enforced by the
same `block_bootstrap_paired` the world model uses.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services import world_model as WM
from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import market_stress as MS
from backend.services.research_gym import utility as U
from backend.services.research_gym.slice_register import (SliceIdentity,
                                                          SliceRefusal,
                                                          SliceRegister)

GYM = _config.OPTIMUS_LEDGER_DIR / "research_gym"
FROZEN = GYM / "n21_frozen_rules.json"
OUT = GYM / "n21_policy_utility.json"

# ── frozen: the selection side, identical to N9 ────────────────────────────
TRAIN_SECURITIES = ("SPY", "XLF", "XLE")
TRAIN_END = "2015-12-31"
SEARCH_FEATURES = ("vix", "drawdown_pct", "ret_1m_pct", "ret_3m_pct",
                   "ret_6m_pct", "realised_vol_20d", "vol_ratio_20_60",
                   "stress_pctile")
QUANTILES = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
HORIZON = 20
TAIL_Q = 0.10
L_MIN = 1.69                       # N4B's 20d break-even, inherited

# ── frozen: the evaluation side, declared before the slice is read ─────────
#: Eight names the register reports as read by NO trial at H=20.
FRESH_SLICE = ("XRT", "XHB", "KRE", "XOP", "ITB", "SMH", "IBB", "IGV")
EVAL_START = "2006-07-01"          # common coverage for all eight
EVAL_END = "2026-08-15"
#: The action N4B priced: exposure to ZERO for H days after a fire. Reported
#: secondary at 0.5, never primary — the primary must match the priced action.
DELTA_PRIMARY = 0.0
DELTA_SECONDARY = 0.5
COST_PER_TURN = 0.0010             # 10bps each way, N4B's declared cost
BLOCK_MONTHS = 6                   # the outcome unit
N_PLACEBO = 200                    # matched-exposure draws per security
SEED = 20260816


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")
                   ).encode("utf-8")).hexdigest()


def _latest_autopsies() -> Path | None:
    files = sorted(GYM.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def _state_frame(tkr: str, vix, start: str, end: str):
    """N9's state vector, byte-for-byte. Every term shifted."""
    import numpy as np
    import pandas as pd
    import yfinance as yf

    px = yf.download(tkr, start=start, end=end, progress=False)["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.squeeze()
    px = px.dropna()
    if len(px) < 400:
        return None
    r = px.pct_change().dropna()
    rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
    rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
    roll_max = px.rolling(252, min_periods=20).max()
    df = pd.DataFrame({
        "vix": vix.reindex(r.index).ffill().shift(1),
        "drawdown_pct": ((px / roll_max - 1.0) * 100.0).shift(1),
        "ret_1m_pct": (px.pct_change(21) * 100.0).shift(1),
        "ret_3m_pct": (px.pct_change(63) * 100.0).shift(1),
        "ret_6m_pct": (px.pct_change(126) * 100.0).shift(1),
        "realised_vol_20d": rv20.shift(1),
        "vol_ratio_20_60": (rv20 / rv60).shift(1),
    }, index=r.index)
    df["stress_pctile"] = MS.stress_pctile(rv20.shift(1).tolist())
    df["ret"] = r
    df[f"fwd_{HORIZON}"] = ((px.shift(-HORIZON) / px - 1.0) * 100.0
                            ).reindex(r.index)
    return df


def _vix(start: str, end: str):
    import pandas as pd
    import yfinance as yf
    v = yf.download("^VIX", start=start, end=end, progress=False)["Close"]
    return v.squeeze() if isinstance(v, pd.DataFrame) else v


def _mask(df, cand) -> "object":
    import numpy as np
    m = np.ones(len(df), dtype=bool)
    for feat, op, thr in cand:
        col = df[feat].to_numpy(dtype=float)
        with np.errstate(invalid="ignore"):
            ok = (col >= thr) if op == ">=" else (col <= thr)
        m &= np.where(np.isnan(col), False, ok)
    return m


# ══════════════════════════════════════════════════════════════════════════
# STAGE 1 — freeze
# ══════════════════════════════════════════════════════════════════════════

def freeze(a) -> int:
    """Re-derive N9's train-selected rules and write them with a hash.

    Structurally blind to the fresh slice: `FRESH_SLICE` is never downloaded
    here, so a rule cannot have been chosen with any knowledge of it.
    """
    import numpy as np
    import pandas as pd

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
        if spec:
            try:
                incumbent.append(AU.compile_precursor(spec))
            except Exception:                                    # noqa: BLE001
                pass
    print(f"incumbent library: {len(incumbent)} compiled precursors "
          f"from {path.name}")

    vix = _vix("1999-01-01", TRAIN_END)
    frames = {}
    for tkr in TRAIN_SECURITIES:
        d = _state_frame(tkr, vix, "1999-01-01", TRAIN_END)
        if d is None:
            print(f"  {tkr}: insufficient history")
            return 1
        recs = d[list(AU.TRANSFERABLE_FEATURES & set(d.columns))].to_dict(
            "records")
        fired = np.zeros(len(d), dtype=bool)
        for fn in incumbent:
            for i, rec in enumerate(recs):
                if fired[i]:
                    continue
                try:
                    if fn(rec):
                        fired[i] = True
                except Exception:                                # noqa: BLE001
                    pass
        d["incumbent_fired"] = fired
        frames[tkr] = d
        print(f"  {tkr}: {len(d)} days, incumbent fires "
              f"{100.0 * fired.mean():.1f}%")

    train = pd.concat([frames[t] for t in TRAIN_SECURITIES])
    clauses = []
    for f in SEARCH_FEATURES:
        col = train[f].replace([np.inf, -np.inf], np.nan).dropna()
        if len(col) < 500:
            continue
        for q in QUANTILES:
            thr = float(np.quantile(col, q))
            clauses.append((f, ">=", thr))
            clauses.append((f, "<=", thr))
    singles = [(c,) for c in clauses]
    pairs = [(x, y) for x, y in itertools.combinations(clauses, 2)
             if x[0] != y[0]]
    candidates = singles + pairs
    print(f"\nSEARCH DENOMINATOR: {len(candidates)} candidate rules")

    fw = train[f"fwd_{HORIZON}"].to_numpy(dtype=float)
    ok = ~np.isnan(fw)
    fw = fw[ok]
    inc = train["incumbent_fired"].to_numpy()[ok]
    cut = float(np.quantile(fw, TAIL_Q))
    uncovered = (fw <= cut) & (~inc)
    print(f"uncovered bottom-decile moves in train: {uncovered.sum()}")

    selected = []
    for cand in candidates:
        fire = _mask(train, cand)[ok]
        base = float(fire.mean())
        if base <= 0.005 or base >= 0.60:
            continue
        lift = float(fire[uncovered].mean()) / base
        if lift >= L_MIN:
            selected.append({"clauses": [list(c) for c in cand],
                             "train_lift": lift, "base_rate": base})
    selected.sort(key=lambda s: -s["train_lift"])
    print(f"selected at train lift >= {L_MIN}: {len(selected)} rules")

    # ── the aggregation, calibrated on TRAIN and frozen with the rules ─────
    # N9 scored each rule INDIVIDUALLY and never as a set. Taking the union
    # (de-risk if any rule fires) is degenerate: 598 OR-ed rules fire on most
    # days, so the "policy" is just holding cash. The power stage found this
    # on the fresh slice's fire rate before any utility existed, which is
    # what the staged design is for — and the fix is calibrated HERE, on
    # train, so the fresh slice contributes nothing to the specification.
    votes = np.zeros(len(train), dtype=float)
    for s in selected:
        votes += _mask(train, tuple(tuple(c) for c in s["clauses"]))
    votes /= max(len(selected), 1)
    incumbent_rate = float(train["incumbent_fired"].mean())
    theta = float(np.quantile(votes, 1.0 - incumbent_rate))
    print(f"vote threshold calibrated on TRAIN: theta = {theta:.4f} "
          f"(matches the incumbent library's {100 * incumbent_rate:.1f}% "
          f"firing rate)")
    print(f"  union of all {len(selected)} rules would fire on "
          f"{100.0 * (votes > 0).mean():.1f}% of train days — degenerate, "
          f"which is why the vote exists")

    payload = {
        "trial": "N21",
        "stage": "frozen_rule_set",
        "derived_from": "N9's train-side selection, re-run",
        "train_securities": list(TRAIN_SECURITIES),
        "train_end": TRAIN_END,
        "horizon_days": HORIZON,
        "tail_q": TAIL_Q,
        "l_min": L_MIN,
        "search_denominator": len(candidates),
        "n_uncovered_train": int(uncovered.sum()),
        "autopsy_file": path.name,
        "n_rules": len(selected),
        "aggregation": "vote_share >= theta",
        "vote_threshold_theta": theta,
        "theta_calibrated_to_incumbent_rate": incumbent_rate,
        "train_union_fire_rate": float((votes > 0).mean()),
        "rules": selected,
        "fresh_slice_NOT_read_here": list(FRESH_SLICE),
        "differs_from_n9_and_why": {
            "n9_reported_train_pass": 582,
            "here": len(selected),
            "cause": (
                "N9 downloads prices to 2026 and slices to TRAIN_END AFTER "
                "computing fwd_20, so its late-2015 training rows carry "
                "forward returns built from up to 20 trading days of 2016 "
                "prices — a 20-day embargo leak ACROSS the train/foreign "
                "boundary, in the selection stage. This freeze cannot commit "
                "it: it never downloads past TRAIN_END, so the last ~20 rows "
                "per security have no outcome and drop out. Reproducing N9's "
                "download window here returns exactly 582, which is how the "
                "cause was established rather than guessed."),
            "materiality": (
                "~60 of ~12,830 training rows (0.5%), shifting the decile "
                "thresholds enough to move the selected count 582 -> 598. "
                "N9's headline was a confirmation result on six OTHER "
                "securities over 2016-2026, which 20 days of early-2016 SPY/"
                "XLF/XLE prices cannot plausibly inform. Recorded because "
                "'small and probably immaterial' is how a leak survives, not "
                "because it is believed to have changed N9's verdict."),
        },
    }
    payload["rules_sha256"] = _sha(selected)
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nrules_sha256 = {payload['rules_sha256']}")
    print(f"wrote {FROZEN}")
    print("\nPut that hash in the prereg and COMMIT before running the test.")
    return 0


# ══════════════════════════════════════════════════════════════════════════
# the policy
# ══════════════════════════════════════════════════════════════════════════

def _exposure_path(fire, n: int, horizon: int, delta: float):
    """Exposure over time: `delta` for `horizon` days after any fire, else 1.

    Overlapping fires extend rather than restart, so a cluster of warnings is
    one de-risking episode and not several. This is a declared choice: the
    alternative (restart on every fire) is a longer and more expensive policy,
    and choosing between them after seeing returns would be selection.
    """
    import numpy as np
    exp = np.ones(n, dtype=float)
    until = -1
    for i in range(n):
        if fire[i]:
            until = max(until, i + horizon)
        if i <= until:
            exp[i] = delta
    return exp


def _wealth(ret, exposure, cost: float):
    """Net wealth path. Cost is charged on every change in exposure."""
    import numpy as np
    turns = np.abs(np.diff(np.concatenate([[1.0], exposure])))
    net = exposure * ret - turns * cost
    return np.cumprod(1.0 + net)


def _blocks(dates, months: int):
    """Non-overlapping calendar blocks — the declared dependence unit."""
    import numpy as np
    import pandas as pd
    idx = pd.DatetimeIndex(dates)
    key = (idx.year.to_numpy() * 100
           + ((idx.month.to_numpy() - 1) // months) * months)
    uniq = np.unique(key)
    return key, uniq


def _max_dd(w) -> float:
    """Max drawdown of a wealth path, in percentage points."""
    import numpy as np
    return float(100.0 * (1.0 - w / np.maximum.accumulate(w)).max())


def _placebo_exposure(n: int, n_derisked: int, horizon: int, delta: float,
                      rng):
    """De-risk the SAME number of days, in randomly placed windows.

    The registered null. Being out of the market lowers drawdown whether or not
    the timing carries information, so "beats zero" is not evidence about the
    signal — only "beats a policy with the same exposure budget" is.
    """
    import numpy as np
    exp = np.ones(n, dtype=float)
    if n_derisked <= 0:
        return exp
    n_windows = max(1, int(round(n_derisked / horizon)))
    starts = rng.integers(0, max(1, n - horizon), size=n_windows)
    for s in starts:
        exp[s:s + horizon] = delta
    return exp


def _log_growth(w) -> float:
    """Terminal log growth of a wealth path, in percent."""
    import numpy as np
    return float(np.log(max(w[-1], 1e-9)) * 100.0)


def _stats(w):
    """A `utility.PathStats` from a wealth path, so the declared personalities
    can score this policy with the same code the Gym uses."""
    import numpy as np
    r = np.diff(w) / w[:-1]
    dn = r[r < 0]
    peak = np.maximum.accumulate(w)
    uw = w < peak
    dd = 1.0 - w / peak
    return U.PathStats(
        n_days=len(w),
        terminal_wealth=float(w[-1]), min_wealth=float(w.min()),
        net_return_pct=float((w[-1] - 1.0) * 100.0),
        realised_vol_pct=float(np.std(r, ddof=1) * np.sqrt(252) * 100.0),
        downside_deviation_pct=(float(np.std(dn, ddof=1) * np.sqrt(252) * 100.0)
                                if dn.size > 1 else None),
        max_drawdown_pct=float(dd.max() * 100.0),
        max_drawdown_days=int(uw.sum()),
        time_under_water_frac=float(uw.mean()),
        worst_day_pct=float(r.min() * 100.0) if r.size else None,
        worst_week_pct=None,
        expected_shortfall_5_pct=(
            float(np.mean(np.sort(r)[:max(1, int(0.05 * r.size))]) * 100.0)
            if r.size >= 20 else None),
        recovery_days=None,
        ruin=bool(w.min() <= U.RUIN_FLOOR),
    )


# ══════════════════════════════════════════════════════════════════════════
# STAGES 2 and 3
# ══════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--power-only", action="store_true")
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--skip-slice-claim", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    if a.freeze:
        return freeze(a)

    import numpy as np

    if not FROZEN.exists():
        print(f"no frozen rule set at {FROZEN} — run --freeze first")
        return 1
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    check = _sha(frozen["rules"])
    if check != frozen["rules_sha256"]:
        print(f"REFUSED: frozen rule file has been edited "
              f"({check} != {frozen['rules_sha256']})")
        return 1
    rules = [tuple(tuple(c) for c in r["clauses"]) for r in frozen["rules"]]
    print(f"frozen rule set: {len(rules)} rules, sha256 "
          f"{frozen['rules_sha256'][:16]}...")

    # ── the slice claim, before a price is read ────────────────────────────
    ident = SliceIdentity(
        securities=tuple(FRESH_SLICE), start=EVAL_START, end=EVAL_END,
        outcome_horizon_days=HORIZON,
        outcome_definition="net log wealth of a de-risking policy vs buy-hold",
        information_cutoff=EVAL_END)
    reg = SliceRegister()
    verdict = reg.check(ident, "CONFIRM", trial="N21")
    print(f"slice {ident.slice_id}: CONFIRM allowed={verdict['allowed']}")
    if not verdict["allowed"]:
        print(f"  REFUSED: {verdict}")
        return 1

    vix = _vix(EVAL_START, EVAL_END)
    frames = {}
    for tkr in FRESH_SLICE:
        d = _state_frame(tkr, vix, EVAL_START, EVAL_END)
        if d is None:
            print(f"  {tkr}: insufficient history — EXCLUDED")
            continue
        frames[tkr] = d
        print(f"  {tkr}: {len(d)} days "
              f"{str(d.index[0])[:10]} -> {str(d.index[-1])[:10]}")
    if len(frames) < 4:
        print("too few securities survived; aborting")
        return 1

    # ── fire mask: the frozen VOTE, at the frozen threshold ────────────────
    theta = float(frozen["vote_threshold_theta"])
    best = tuple(tuple(c) for c in frozen["rules"][0]["clauses"])
    print(f"aggregation: vote_share >= {theta:.4f} (calibrated on train)")
    for tkr, d in frames.items():
        votes = np.zeros(len(d), dtype=float)
        for cand in rules:
            votes += _mask(d, cand)
        votes /= max(len(rules), 1)
        d["fire"] = votes >= theta
        d["fire_best"] = _mask(d, best)
        print(f"  {tkr}: vote fires {100.0 * d['fire'].mean():.1f}%  |  "
              f"union would fire {100.0 * (votes > 0).mean():.1f}%  |  "
              f"single best rule {100.0 * d['fire_best'].mean():.1f}%")

    # ── power stage: dispersion WITHOUT the policy's utility ───────────────
    if a.power_only:
        # A policy-free surrogate: the block-level log-growth difference
        # between the security and a 50/50 blend with cash. It has the same
        # units and roughly the same dispersion as the real contrast, and it
        # cannot be moved by the hypothesis, because no rule enters it.
        diffs = []
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            for u in uniq:
                m = key == u
                if m.sum() < 40:
                    continue
                w_full = np.cumprod(1.0 + r[m])
                w_half = np.cumprod(1.0 + 0.5 * r[m])
                diffs.append(_log_growth(w_half) - _log_growth(w_full))
        diffs = np.asarray(diffs)
        n_blocks = len(set(_blocks(list(frames.values())[0].index,
                                   BLOCK_MONTHS)[1]))

        # ── the design effect, MEASURED rather than assumed ────────────────
        # "one block across the whole cross-section" assumes the eight
        # securities carry one observation between them. That is the
        # conservative end; the honest number is the design effect implied by
        # their average pairwise correlation:
        #     n_eff = k / (1 + (k-1) * rho_bar)
        # Measured on the POLICY-FREE surrogate, so the hypothesis cannot move
        # its own power declaration.
        import pandas as pd
        wide = {}
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            col = {}
            for u in uniq:
                m = key == u
                if m.sum() < 40:
                    continue
                col[int(u)] = (_log_growth(np.cumprod(1.0 + 0.5 * r[m]))
                               - _log_growth(np.cumprod(1.0 + r[m])))
            wide[tkr] = pd.Series(col)
        W = pd.DataFrame(wide).dropna()
        C = W.corr().to_numpy()
        k = C.shape[0]
        rho = float((C.sum() - np.trace(C)) / (k * (k - 1)))
        n_eff_cs = k / (1.0 + (k - 1) * rho)
        n_eff = n_blocks * n_eff_cs
        years = n_blocks * BLOCK_MONTHS / 12.0
        sd_block = float(np.std(diffs, ddof=1))
        mde_block = (1.959963985 + 0.8416212336) * sd_block / np.sqrt(n_eff)
        mde_annual = mde_block * (12.0 / BLOCK_MONTHS)

        print("\n=== POWER INPUTS (design stage) ===")
        print(f"  average pairwise correlation of block outcomes rho = "
              f"{rho:.3f} over {k} securities")
        print(f"  effective cross-section  = {n_eff_cs:.2f} "
              f"(k / (1 + (k-1)rho)), NOT {k}")
        print(f"  => n_available_effective = {n_eff:.0f} "
              f"(NOT {len(diffs)} security-blocks)")
        print(f"  80%-power MDE            = {mde_block:.2f}pp per "
              f"{BLOCK_MONTHS}-month block = {mde_annual:.2f}pp/yr of log growth")
        print(f"  the execution standard asks for +3%/yr net excess; resolving "
              f"3pp/yr needs")
        need = ((1.959963985 + 0.8416212336) * sd_block
                / (3.0 / (12.0 / BLOCK_MONTHS))) ** 2
        # ERRATUM 2026-08-16, found in review. `need` is a count of EFFECTIVE
        # observations, and this slice supplies `n_eff_cs` of them per block —
        # not one. The first version divided by the block rate alone and
        # printed 172 years, which is the honest 95 multiplied by the very
        # cross-section the line above had just finished measuring. Using the
        # design effect to compute n_eff and then dropping it when converting
        # n_eff back to years counts the cross-section once and forgets it
        # once. The conclusion (>> 20 years) survives; the number did not, and
        # the error ran in the direction that made the finding louder.
        eff_per_year = (12.0 / BLOCK_MONTHS) * n_eff_cs
        print(f"    n = {need:.0f} independent-equivalent observations = "
              f"{need / eff_per_year:.0f} YEARS at {eff_per_year:.2f} of them "
              f"per year ({12.0 / BLOCK_MONTHS:.0f} blocks x "
              f"{n_eff_cs:.2f} effective securities), against the "
              f"{years:.0f} this slice holds")
        print(f"    [counting blocks alone and ignoring the effective "
              f"cross-section would claim {need * BLOCK_MONTHS / 12.0:.0f} "
              f"years — the same cross-section used twice, once as a "
              f"multiplier and once not at all]")

        # ── would a DIFFERENT outcome be resolvable on the same slice? ─────
        # Terminal log growth is the noisiest possible way to ask a question
        # that was always about tail avoidance. Same surrogate, same blocks,
        # same dependence unit — only the outcome changes. Still policy-free.
        def _dd(w):
            return float(100.0 * (1.0 - w / np.maximum.accumulate(w)).max())

        alt: dict[str, list] = {"max_drawdown_pp": [], "worst_day_pp": [],
                                "downside_semidev_pp": []}
        alt_wide: dict[str, dict] = {k: {} for k in alt}
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            for u in uniq:
                m = key == u
                if m.sum() < 40:
                    continue
                rf, rh = r[m], 0.5 * r[m]
                v = {
                    "max_drawdown_pp": (_dd(np.cumprod(1.0 + rh))
                                        - _dd(np.cumprod(1.0 + rf))),
                    "worst_day_pp": 100.0 * (rh.min() - rf.min()),
                    "downside_semidev_pp": 100.0 * (
                        np.std(np.minimum(rh, 0.0), ddof=1)
                        - np.std(np.minimum(rf, 0.0), ddof=1)),
                }
                for k2, val in v.items():
                    alt[k2].append(val)
                    alt_wide[k2].setdefault(tkr, {})[int(u)] = val

        print("\n  SAME slice, SAME blocks, SAME dependence unit — other "
              "outcomes:")
        print(f"  {'outcome':<22s} {'rho':>6s} {'n_eff':>7s} {'sd':>8s} "
              f"{'MDE/block':>10s}")
        for k2, vals in alt.items():
            Wk = pd.DataFrame(alt_wide[k2]).dropna()
            Ck = Wk.corr().to_numpy()
            kk = Ck.shape[0]
            rk = float((Ck.sum() - np.trace(Ck)) / (kk * (kk - 1)))
            ne = n_blocks * (kk / (1.0 + (kk - 1) * rk))
            sk = float(np.std(vals, ddof=1))
            mk = (1.959963985 + 0.8416212336) * sk / np.sqrt(ne)
            print(f"  {k2:<22s} {rk:>6.3f} {ne:>7.0f} {sk:>8.3f} "
                  f"{mk:>10.3f}pp")
        print()
        print(f"  surrogate block log-growth difference: sd "
              f"{np.std(diffs, ddof=1):.3f}pp over {len(diffs)} security-blocks")
        print(f"  securities                = {len(frames)}")
        print(f"  {BLOCK_MONTHS}-month blocks per security = {n_blocks}")
        print(f"  DEPENDENCE UNIT: one {BLOCK_MONTHS}-month calendar block "
              f"across the WHOLE cross-section")
        print(f"  => n_available_effective  = {n_blocks} "
              f"(NOT {len(diffs)} security-blocks)")
        print(f"  event_frequency_per_year  = {12.0 / BLOCK_MONTHS:.1f}")
        print(f"  cross_sectional_n         = {len(frames)}")
        print(f"  outcome_dispersion        = {np.std(diffs, ddof=1):.3f}pp")
        print("\n--power-only: no policy utility was computed.")
        return 0

    if not a.skip_slice_claim:
        try:
            reg.claim(ident, "CONFIRM", trial="N21",
                      consumed_at="2026-08-16T21:00:00Z",
                      prereg="docs/TRIALS/PREREG_N21_POLICY_UTILITY.md",
                      note="direct policy-utility test of the frozen N9 rules")
        except SliceRefusal as exc:
            print(f"REFUSED: {exc}")
            return 1

    # ── the test ───────────────────────────────────────────────────────────
    results = {}
    for delta, tag in ((DELTA_PRIMARY, "primary"), (DELTA_SECONDARY,
                                                    "secondary")):
        per_sec, block_rows = {}, []
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            exp = _exposure_path(d["fire"].to_numpy(), len(d), HORIZON, delta)
            w_pol = _wealth(r, exp, COST_PER_TURN)
            w_bh = _wealth(r, np.ones(len(d)), COST_PER_TURN)
            per_sec[tkr] = {
                "policy_log_growth_pp": _log_growth(w_pol),
                "buyhold_log_growth_pp": _log_growth(w_bh),
                "delta_log_growth_pp": _log_growth(w_pol) - _log_growth(w_bh),
                "policy_max_dd_pct": float(
                    100.0 * (1.0 - w_pol / np.maximum.accumulate(w_pol)).max()),
                "buyhold_max_dd_pct": float(
                    100.0 * (1.0 - w_bh / np.maximum.accumulate(w_bh)).max()),
                "avg_exposure": float(exp.mean()),
            }
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            for u in uniq:
                m = key == u
                if m.sum() < 40:
                    continue
                e = exp[m]
                bp = _wealth(r[m], e, COST_PER_TURN)
                bb = _wealth(r[m], np.ones(int(m.sum())), COST_PER_TURN)
                block_rows.append({
                    "security": tkr, "block": int(u),
                    "date": d.index[m][0],
                    "d_log_growth_pp": _log_growth(bp) - _log_growth(bb),
                })

        # ── PRIMARY: block drawdown difference vs a matched-exposure placebo
        rng = np.random.default_rng(SEED)
        dd_obs, dd_placebo = [], []
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            exp = _exposure_path(d["fire"].to_numpy(), len(d), HORIZON, delta)
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            for u in uniq:
                m = key == u
                if m.sum() < 40:
                    continue
                rm, em = r[m], exp[m]
                base_dd = _max_dd(_wealth(rm, np.ones(int(m.sum())),
                                          COST_PER_TURN))
                dd_obs.append(_max_dd(_wealth(rm, em, COST_PER_TURN)) - base_dd)
            n_off = int((exp < 1.0).sum())
            for _ in range(N_PLACEBO):
                pe = _placebo_exposure(len(d), n_off, HORIZON, delta, rng)
                got = []
                for u in uniq:
                    m = key == u
                    if m.sum() < 40:
                        continue
                    rm = r[m]
                    got.append(_max_dd(_wealth(rm, pe[m], COST_PER_TURN))
                               - _max_dd(_wealth(rm, np.ones(int(m.sum())),
                                                 COST_PER_TURN)))
                dd_placebo.append(float(np.mean(got)))
        # ── DIAGNOSTIC, added after seeing the primary. Cannot change it. ──
        # The registered placebo places de-risking windows UNIFORMLY at random.
        # Real fires CLUSTER in volatile periods, and clustering alone lowers
        # drawdown without any predictive skill — so the registered null may be
        # too weak, in the direction that flatters the result. SS37: a new
        # instrument's first positive is the one that looks like it working.
        #
        # The stronger null is a CIRCULAR BLOCK SHIFT of the actual fire mask:
        # it preserves the count, the run lengths and the autocorrelation
        # exactly, and destroys only the alignment between state and outcome.
        # This is the null N9 used, and it is the one that matters.
        shift_null = []
        for tkr, d in frames.items():
            r = d["ret"].to_numpy(dtype=float)
            fire = d["fire"].to_numpy()
            key, uniq = _blocks(d.index, BLOCK_MONTHS)
            n = len(d)
            for _ in range(N_PLACEBO):
                k = int(rng.integers(1, n))
                se = _exposure_path(np.roll(fire, k), n, HORIZON, delta)
                got = []
                for u in uniq:
                    m = key == u
                    if m.sum() < 40:
                        continue
                    rm = r[m]
                    got.append(_max_dd(_wealth(rm, se[m], COST_PER_TURN))
                               - _max_dd(_wealth(rm, np.ones(int(m.sum())),
                                                 COST_PER_TURN)))
                shift_null.append(float(np.mean(got)))
        shift_null = np.asarray(shift_null)

        # ── THE NULL INVARIANCE CONTRACT, applied to both nulls ────────────
        # Written after this trial, because of this trial. Max drawdown is
        # path-dependent, so `declared_invariants_for` requires the null to
        # preserve clustering and run lengths as well as frequency — and the
        # registered placebo does not. The check is run on the MASKS only, so
        # it costs nothing and could have run at registration.
        from backend.services.research_gym import null_invariance as NI

        required = NI.declared_invariants_for("max drawdown per block")
        crng = np.random.default_rng(SEED + 7)
        contracts: dict[str, dict] = {}
        for label, spec in (
                ("registered_matched_exposure",
                 NI.NullSpec("matched_exposure_uniform_windows",
                             preserves=required,
                             why="as pre-registered: same de-risked day count, "
                                 "windows placed uniformly at random")),
                ("diagnostic_block_shift",
                 NI.NullSpec("circular_block_shift", preserves=required,
                             why="rotate the real fire mask; alignment is the "
                                 "only property destroyed"))):
            worst = None
            for tkr, d in frames.items():
                n = len(d)
                real = (_exposure_path(d["fire"].to_numpy(), n, HORIZON, delta)
                        < 1.0).tolist()
                n_off = sum(real)
                draws = []
                for _ in range(40):
                    if label == "registered_matched_exposure":
                        pe = _placebo_exposure(n, n_off, HORIZON, delta, crng)
                        draws.append((pe < 1.0).tolist())
                    else:
                        k = int(crng.integers(1, n))
                        se = _exposure_path(np.roll(d["fire"].to_numpy(), k), n,
                                            HORIZON, delta)
                        draws.append((se < 1.0).tolist())
                v = NI.verify(spec, NI.summarise(real),
                              [NI.summarise(x) for x in draws])
                if worst is None or (not v.ok and worst["ok"]):
                    worst = {**v.as_dict(), "security": tkr, "why": v.why()}
            contracts[label] = worst
            print(f"\n  NULL CONTRACT [{label}]: "
                  f"{'PRESERVED' if worst['ok'] else 'VIOLATED'}")
            if not worst["ok"]:
                bad = [c["detail"] for c in worst["checks"] if not c["ok"]]
                print(f"    fails {sorted(set(bad))} on {worst['security']} "
                      f"— a p-value from this null measures the property it "
                      f"broke as much as the alignment under test")

        dd_obs = np.asarray(dd_obs)
        dd_placebo = np.asarray(dd_placebo)
        obs_mean = float(dd_obs.mean())
        p5 = float(np.quantile(dd_placebo, 0.05))
        p95 = float(np.quantile(dd_placebo, 0.95))
        p_val = float((dd_placebo <= obs_mean).mean())

        if obs_mean <= p5:
            dd_verdict = ("POLICY_REDUCES_DRAWDOWN" if abs(obs_mean) >= 3.0
                          else "DETECTABLE_BUT_IMMATERIAL")
        elif obs_mean >= p95:
            dd_verdict = "POLICY_WORSENS_DRAWDOWN"
        else:
            dd_verdict = "NO_TIMING_INFORMATION"

        d_arr = np.array([b["d_log_growth_pp"] for b in block_rows])
        dates = np.array([np.datetime64(b["date"], "D") for b in block_rows])
        # block length 1 day: the calendar block IS the unit, so one bootstrap
        # draw takes one whole half-year across the whole cross-section
        inf = WM.block_bootstrap_paired(d_arr, dates, 1, n_boot=4000, seed=SEED)

        pooled = float(np.mean([v["delta_log_growth_pp"]
                                for v in per_sec.values()]))
        n_better = sum(1 for v in per_sec.values()
                       if v["delta_log_growth_pp"] > 0)
        dd = float(np.mean([v["policy_max_dd_pct"] - v["buyhold_max_dd_pct"]
                            for v in per_sec.values()]))

        verdict = ("POLICY_ADDS_UTILITY" if inf.ci_lo > 0 else
                   "POLICY_DESTROYS_UTILITY" if inf.ci_hi < 0 else
                   "NOT_DETECTABLE_IN_SCOPE")
        results[tag] = {
            "delta": delta, "per_security": per_sec,
            "pooled_delta_log_growth_pp": pooled,
            "securities_improved": n_better, "n_securities": len(per_sec),
            "mean_max_dd_change_pp": dd,
            "block_inference": inf.as_dict(),
            "log_growth_verdict_UNPOWERED": verdict,
            "n_blocks": len(block_rows),
            "PRIMARY_drawdown": {
                "observed_mean_block_dd_pp": obs_mean,
                "placebo_p5": p5, "placebo_p95": p95,
                "placebo_median": float(np.median(dd_placebo)),
                "p_value": p_val, "n_placebo_draws": len(dd_placebo),
                "material_floor_pp": 3.0,
                "verdict": dd_verdict,
                # The registered verdict is what the committed rule produced
                # and stays. `inference_status` is a separate field because the
                # two are separate facts: the rule ran as written, and the
                # instrument it ran on does not support the reading. Rewriting
                # `verdict` would destroy the first fact to record the second.
                "inference_status": (
                    "PRIMARY_INFERENCE_INVALIDATED_BY_NULL_MISSPECIFICATION"
                    if not contracts["registered_matched_exposure"]["ok"]
                    else "PRIMARY_INFERENCE_STANDS"),
                "null_contracts": contracts,
                "required_invariants_for_this_outcome": list(required),
                "DIAGNOSTIC_block_shift_null": {
                    "note": ("added after the primary; preserves fire count, "
                             "run lengths and clustering, destroys only "
                             "state-outcome alignment. Cannot change the "
                             "registered verdict."),
                    "median": float(np.median(shift_null)),
                    "p5": float(np.quantile(shift_null, 0.05)),
                    "p_value": float((shift_null <= obs_mean).mean()),
                    "survives": bool(obs_mean
                                     <= float(np.quantile(shift_null, 0.05))),
                },
            },
        }

        print(f"\n{'=' * 74}")
        print(f"delta = {delta}  ({tag}{'' if tag == 'primary' else ', reported never deciding'})")
        print(f"{'=' * 74}")
        print(f"{'security':<10s} {'policy':>10s} {'buy-hold':>10s} "
              f"{'delta':>9s} {'ddP':>7s} {'ddBH':>7s} {'expo':>6s}")
        for tkr, v in per_sec.items():
            print(f"{tkr:<10s} {v['policy_log_growth_pp']:>10.1f} "
                  f"{v['buyhold_log_growth_pp']:>10.1f} "
                  f"{v['delta_log_growth_pp']:>+9.1f} "
                  f"{v['policy_max_dd_pct']:>7.1f} "
                  f"{v['buyhold_max_dd_pct']:>7.1f} "
                  f"{v['avg_exposure']:>6.2f}")
        print(f"\n  pooled delta log growth {pooled:+.2f}pp   "
              f"{n_better}/{len(per_sec)} securities improved")
        print(f"  mean max-drawdown change {dd:+.2f}pp "
              "(negative = shallower under the policy)")
        print(f"  block-level: {inf.n_rows} security-blocks = {inf.n_dates} "
              f"calendar blocks x ~{inf.n_securities} securities "
              f"=> n_eff {inf.n_effective:.0f}")
        print(f"  mean {inf.mean:+.3f}pp per block  90% CI "
              f"[{inf.ci_lo:+.3f}, {inf.ci_hi:+.3f}]  MDE "
              f"{inf.mde_80pct_power:.3f}pp")
        print(f"  log-growth reading: {verdict}  -- REGISTERED UNPOWERED "
              f"(MDE {inf.mde_80pct_power * 12.0 / BLOCK_MONTHS:.2f}pp/yr vs a "
              f"3pp/yr standard); this may NOT produce a verdict")

        print(f"\n  PRIMARY — block max-drawdown difference vs a "
              f"matched-exposure placebo")
        print(f"    observed  {obs_mean:+.3f}pp per block")
        print(f"    placebo   median {np.median(dd_placebo):+.3f}  "
              f"5th {p5:+.3f}  95th {p95:+.3f}   "
              f"({len(dd_placebo)} draws)")
        print(f"    p = {p_val:.4f}   material floor 3.0pp")
        print(f"    VERDICT: {dd_verdict}")

        sp5 = float(np.quantile(shift_null, 0.05))
        sp_p = float((shift_null <= obs_mean).mean())
        print(f"\n    DIAGNOSTIC (added after the primary; cannot change it) —"
              f"\n    circular block-shift of the ACTUAL fire mask, which "
              f"preserves\n    count, run lengths and clustering and destroys "
              f"only the alignment:")
        print(f"      shifted null: median {np.median(shift_null):+.3f}  "
              f"5th {sp5:+.3f}   observed {obs_mean:+.3f}   p = {sp_p:.4f}")
        print("      " + ("the primary SURVIVES the stronger null"
                          if obs_mean <= sp5 else
                          "the primary DOES NOT survive the stronger null — "
                          "the registered\n      placebo was too weak and the "
                          "reduction is consistent with CLUSTERING"))

        # the personalities — reported, and each one inherits the log-growth
        # arm's unpowered status because each contains a terminal-return term
        if tag == "primary":
            print("\n  by declared personality (whole path) — ALL UNPOWERED, "
                  "each contains a return term:")
            for obj in U.PERSONALITIES:
                vals = []
                for tkr, d in frames.items():
                    r = d["ret"].to_numpy(dtype=float)
                    e = _exposure_path(d["fire"].to_numpy(), len(d), HORIZON,
                                       delta)
                    wp = _wealth(r, e, COST_PER_TURN)
                    wb = _wealth(r, np.ones(len(d)), COST_PER_TURN)
                    sp = U.score_one(obj, _stats(wp))
                    sb = U.score_one(obj, _stats(wb))
                    if sp is None or sb is None:
                        vals = None
                        break
                    vals.append(sp - sb)
                if vals is None:
                    print(f"    {obj.name:<16s} (not scorable)")
                else:
                    results[tag].setdefault("personalities", {})[obj.name] = \
                        float(np.mean(vals))
                    print(f"    {obj.name:<16s} {np.mean(vals):+8.2f} "
                          f"{obj.units}")

    payload = {
        "trial": "N21",
        "prereg": "docs/TRIALS/PREREG_N21_POLICY_UTILITY.md",
        "frozen_rules_sha256": frozen["rules_sha256"],
        "n_frozen_rules": len(rules),
        "slice_id": ident.slice_id,
        "fresh_slice": list(frames),
        "eval_start": EVAL_START, "eval_end": EVAL_END,
        "horizon_days": HORIZON, "cost_per_turn": COST_PER_TURN,
        "block_months": BLOCK_MONTHS,
        "dependence_unit": f"one {BLOCK_MONTHS}-month calendar block across "
                           f"the whole cross-section",
        "results": results,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=2, default=str),
                           encoding="utf-8")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
