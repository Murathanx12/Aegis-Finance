"""Pooled per-family tests: the strategy library's most powerful honest test.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM). Every number is HINDSIGHT:
the rules were written on 2026-09-26, after every month scored.

Reviewer idea 3 (`docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md`
§8): a single rule's alpha on the 32 monthly blocks of 2024-26 has an MDE of
~2.46%/month, so "no rule shows alpha in both windows" is what happens nine
times in ten even when every rule carries a real 12%/yr alpha. Pooling the
rules of one family into ONE equal-weight series of monthly active returns
averages away the part of each rule's noise the others do not share, and the
family becomes the unit of the claim. Multiplicity is then counted over
FAMILIES, not cells.

Pooling helps only as far as the members disagree. With n members whose
pairwise correlation averages rho, the variance of the pooled mean is about
sigma^2 (1 + (n - 1) rho) / n, i.e. the pooled SE is the single SE over
sqrt(n_eff), n_eff = n / (1 + (n - 1) rho). A family of near-duplicates
(rho -> 1) has n_eff -> 1 and its SE does NOT shrink; that is printed on every
row (`effective_n`) rather than assumed. The SE itself is always measured on
the pooled series (plain sd / sqrt(T), and Newey-West at lag max(hold) - 1,
floored at the plain one as for single rules), never derived from n_eff.

The same three verdicts as a single rule (`signal_structure.verdict`) on the
ex-ante-hedged 2024-26 alpha: ALPHA_DETECTED / CANNOT_DISTINGUISH / BETA_EXPLAINS.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from backend.services import signal_structure as SS

MIN_RULES = 3                    # a family with fewer rules is not pooled
WINDOWS = ("dev", "sealed", "full")
WINDOW_LABEL = {"dev": "dev (entry < 2024)", "sealed": "2024-26", "full": "full"}
T_BAR = 2.0


class FamilyPoolRefused(RuntimeError):
    """A family with fewer than MIN_RULES rules, or a pooled series with fewer
    than signal_structure.MIN_MONTHS months: the receipt refuses by name."""


# ── the pieces ──────────────────────────────────────────────────────────────

def effective_n(frame: pd.DataFrame, *, min_periods: int = SS.MIN_MONTHS) -> dict:
    """n members, their mean pairwise correlation and n_eff = n / (1 + (n-1) rho).

    A pair without `min_periods` common months is left out of the mean. rho is
    floored at 0 for n_eff (negative average correlation would promise more
    than n independent bets) and n_eff is clipped to [1, n]."""
    n = int(frame.shape[1])
    if n == 0:
        return {"n": 0, "mean_pair_rho": None, "n_eff": None, "n_pairs": 0}
    if n == 1:
        return {"n": 1, "mean_pair_rho": None, "n_eff": 1.0, "n_pairs": 0}
    c = frame.corr(min_periods=min_periods).to_numpy(dtype=float)
    iu = np.triu_indices(n, 1)
    v = c[iu]
    v = v[np.isfinite(v)]
    if not len(v):
        return {"n": n, "mean_pair_rho": None, "n_eff": None, "n_pairs": 0}
    rho = float(v.mean())
    neff = n / (1.0 + (n - 1) * max(rho, 0.0))
    return {"n": n, "mean_pair_rho": rho, "n_eff": float(min(max(neff, 1.0), n)),
            "n_pairs": int(len(v))}


def pool(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(equal-weight mean across the members present each month, members present)."""
    return frame.mean(axis=1, skipna=True), frame.notna().sum(axis=1)


def mean_test(x: Iterable[float], *, hold_months: int = 1) -> dict:
    """The mean of a monthly series with plain SE (sd / sqrt T), Newey-West SE at
    lag hold - 1 (Bartlett), the USED SE = max(plain, HAC) when hold > 1 (HAC
    may widen, never narrow: `signal_structure.HAC_FLOOR_NOTE`), t and MDE at
    80% power (2.8 x SE). Refuses below MIN_MONTHS."""
    v = np.asarray([float(z) for z in x], dtype=float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < SS.MIN_MONTHS:
        raise FamilyPoolRefused(f"{n} months < {SS.MIN_MONTHS}; the pooled test refuses")
    m = float(v.mean())
    sd = float(v.std(ddof=1))
    se = sd / math.sqrt(n)
    L = SS.hac_lags_for(hold_months)
    se_h = SS.hac_se_mean(v, L)
    use_hac = L > 0 and np.isfinite(se_h)
    se_u = max(se, se_h) if use_hac else se
    return {"n": n, "mean_monthly": m, "sd_monthly": sd,
            "se_plain": se, "t_plain": m / se if se > 0 else float("nan"),
            "se_hac": se_h, "t_hac": (m / se_h) if np.isfinite(se_h) and se_h > 0 else float("nan"),
            "hac_lags": int(L), "se_used": se_u,
            "se_basis": ("plain" if L == 0 else ("hac" if se_h >= se else "plain (HAC below plain: floored)")),
            "t_used": m / se_u if se_u > 0 else float("nan"), "mde_80": SS.MDE_Z * se_u}


def families(cells: dict, cids: Iterable[str], *, min_rules: int = MIN_RULES) -> tuple[dict, dict]:
    """({family: [cell ids]} for families with >= min_rules members,
    {family: n} for the ones too small to pool)."""
    by: dict = {}
    for c in cids:
        by.setdefault(cells[c].get("family") or "none", []).append(c)
    ok = {f: sorted(v) for f, v in sorted(by.items()) if len(v) >= min_rules}
    small = {f: len(v) for f, v in sorted(by.items()) if len(v) < min_rules}
    return ok, small


def require_family(members: list, family: str, *, min_rules: int = MIN_RULES) -> None:
    if len(members) < min_rules:
        raise FamilyPoolRefused(f"family {family!r}: {len(members)} rule(s) < {min_rules}; not pooled")


# ── one family against one benchmark ────────────────────────────────────────

def _ols_or_refusal(y: pd.Series, X: Optional[pd.DataFrame], hold_months: int) -> dict:
    if X is None:
        return {"status": "NO_FACTORS"}
    try:
        return SS.ols(y, X, hold_months=hold_months)
    except SS.InsufficientHistory as e:
        return {"status": "REFUSED", "why": str(e)}


def family_test(frame: pd.DataFrame, masks: dict, *, family: str, hold_months: int = 1,
                X: Optional[pd.DataFrame] = None, min_rules: int = MIN_RULES) -> dict:
    """`frame`: date x member cells of monthly ACTIVE returns against ONE
    benchmark. `masks`: {"dev", "sealed"} boolean arrays over frame.index
    (the factory's entry-date split). `X`: optional factor spreads on the same
    index for the in-window alpha and the ex-ante (dev-beta) hedge.

    Per window: the pooled mean with plain / HAC / used SE, t and MDE; the
    median single-member SE and MDE with the same estimator; their ratio; the
    effective n of the members in that window; and, with X, the OLS alpha.
    The verdict reads the ex-ante-hedged 2024-26 alpha with the same rules
    as a single rule; without X it reads the plain pooled 2024-26 mean."""
    members = list(frame.columns)
    require_family(members, family, min_rules=min_rules)
    y, present = pool(frame)
    full = np.ones(len(frame), dtype=bool)
    wm = {"dev": np.asarray(masks["dev"]), "sealed": np.asarray(masks["sealed"]), "full": full}
    out: dict = {"family": family, "n_rules": len(members), "members": members,
                 "hold_months_used": int(hold_months), "windows": {}}
    for w, mk in wm.items():
        sub = frame[mk]
        ys = y[mk].dropna()
        row: dict = {"min_members_present": int(present[mk][present[mk] > 0].min())
                     if (present[mk] > 0).any() else 0}
        try:
            row["pooled"] = mean_test(ys, hold_months=hold_months)
        except FamilyPoolRefused as e:
            row["pooled"] = {"status": "REFUSED", "why": str(e)}
        singles = []
        for c in members:
            try:
                singles.append(mean_test(sub[c].dropna(), hold_months=hold_months))
            except FamilyPoolRefused:
                continue
        if singles:
            se1 = float(np.median([s_["se_used"] for s_ in singles]))
            row["single_rule_median_se"] = se1
            row["single_rule_median_mde_80"] = SS.MDE_Z * se1
            row["n_single_rules_tested"] = len(singles)
            row["n_single_rules_t_ge_2"] = sum(1 for s_ in singles if s_["t_used"] >= T_BAR)
            if "se_used" in row["pooled"]:
                row["se_ratio_pooled_to_single"] = row["pooled"]["se_used"] / se1 if se1 > 0 else None
        en = effective_n(sub)
        row["effective_n"] = en
        if en.get("n_eff"):
            row["se_ratio_implied_by_n_eff"] = 1.0 / math.sqrt(en["n_eff"])
        row["ols"] = _ols_or_refusal(ys, X[mk] if X is not None else None, hold_months)
        out["windows"][w] = row
    # the verdict, as for a single rule: the 2024-26 alpha after the betas you could have known
    d_ols = out["windows"]["dev"]["ols"]
    s_ = out["windows"]["sealed"]
    if X is not None and "betas" in d_ols:
        try:
            h = SS.exante_hedge(y[wm["sealed"]], X[wm["sealed"]], d_ols["betas"],
                                hold_months=hold_months)
        except SS.InsufficientHistory as e:
            h = {"status": "REFUSED", "why": str(e)}
    else:
        p = s_["pooled"]
        h = ({"t": p["t_used"], "mde_80": p["mde_80"], "alpha_monthly": p["mean_monthly"],
              "se": p["se_used"], "basis": "plain pooled mean (no factors)"}
             if "t_used" in p else {"status": "REFUSED", "why": p.get("why")})
    out["alpha_after_dev_hedge"] = h
    obs = (s_["pooled"] or {}).get("mean_monthly")
    out["verdict"] = SS.verdict(h, obs) if "t" in h else "REFUSED"
    out["alpha_sign"] = ("+" if h.get("alpha_monthly", 0) > 0 else "-") if "t" in h else None
    pd_, ps_ = out["windows"]["dev"]["pooled"], s_["pooled"]
    out["mean_t_ge_2_both_windows"] = bool(pd_.get("t_used", -9) >= T_BAR and ps_.get("t_used", -9) >= T_BAR)
    so = s_["ols"]
    out["ols_alpha_t_ge_2_both_windows"] = bool(d_ols.get("t_alpha_used", -9) >= T_BAR
                                                and so.get("t_alpha_used", -9) >= T_BAR)
    return out


def dsr_over_families(series: dict, n_families: int) -> dict:
    """{family: DSR of its full-window pooled series at n = number of families}."""
    out = {}
    for f, s in series.items():
        v = pd.Series(s).dropna()
        out[f] = SS.dsr_at(v.to_numpy(), n_families) if len(v) >= SS.MIN_MONTHS else None
    return out
