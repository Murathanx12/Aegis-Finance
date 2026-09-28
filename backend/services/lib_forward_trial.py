"""TRIAL-LIB-FWD-TWIN-1: the ONE forward comparison (lane M6, 2026-09-28).

The strategy library's frozen forward books against their frozen twins, pooled
by cluster, read at 21 and 63 sessions, with the luck table printed beside it
and a kill rule written before the first session. Registers a comparison over
books ALREADY frozen; creates no book. Canonical commitment:
`docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md`.

Everything the future read needs is here, so the decision is computed by code
from frozen inputs and not by a reader on the day:

* `select_pairs` -- which book is read against which frozen twin (matched_random
  when frozen, else random_same_band; the type travels with the row);
* `pooled_z` -- the cluster-pooled rule - twin difference and its z against the
  sigma FROZEN in the registration receipt;
* `decide` -- the kill rule;
* `luck_table` -- P(the best of K zero-skill books reads z >= 2).
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np

TRIAL_ID = "TRIAL-LIB-FWD-TWIN-1"
PARAM = "lib-forward-vs-twin-pooled-by-cluster"
DOC = "docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md"
ENTRY_SESSION = "2026-09-28"          # every lib book enters at this open (llm_portfolio.entry_session)
READ_21 = "2026-10-26"                # XNYS session 21 from the entry session
READ_63 = "2026-12-24"                # XNYS session 63 (the PRIMARY read)
Z_PASS = 2.0
Z_KILL = 1.0
Z_EARLY_KILL = -2.0
TWIN_PREFERENCE = ("matched_random", "random_same_band")
MAX_DROPPED_SHARE = 0.25
# AMENDMENT 2026-09-28 (before the 13:30Z open; review F2). The registered
# correlations (within 0.66, between 0.09) were estimated on the MATCHED-twin
# differences, while 25 of 30 books are read against a SIZE-BAND-ONLY twin whose
# difference keeps the vol / momentum style. Re-estimated on the difference type
# actually read (band-only proxy: rule - random_1@k50; matched for the 5 matched
# pairs), same backtest months (2017-01..2026-07), same frozen sigmas. These are
# the DECIDING correlations; the registered ones are printed beside every read.
# Receipt: backend/data/optimus/trials/lib_forward_trial_amendment_<run id>.json
RHO_WITHIN_REGISTERED = 0.6558515018340987
RHO_BETWEEN_REGISTERED = 0.09328961144204369
RHO_WITHIN_AS_READ = 0.783815046551912
RHO_BETWEEN_AS_READ = 0.4034623782721821
VERDICTS = ("SURVIVES", "CANNOT_DISTINGUISH", "KILL", "EARLY_KILL", "CANNOT_DETERMINE", "INTERIM")


class LibTrialInputMissing(RuntimeError):
    """A book, twin, cluster or frozen sigma the trial needs is absent: the read
    refuses by name rather than pooling what happens to be there."""


# ── who is compared with whom ────────────────────────────────────────────────

def select_pairs(books: Iterable[dict]) -> list[dict]:
    """[{book_id, name, twin_book_id, twin_type}] for every live lib_ parent.

    Live = a `lib_` parent that is not a twin and has no VOID row. The twin is
    the first frozen twin of that parent in `TWIN_PREFERENCE` order; a parent
    with none refuses by name."""
    rows = list(books)
    void_ids = {r.get("book_id") for r in rows if r.get("kind") == "void"}
    parents = [r for r in rows if r.get("kind") not in ("twin", "void")
               and str(r.get("name", "")).startswith("lib_") and r.get("book_id") not in void_ids]
    twins: dict = {}
    for r in rows:
        if r.get("kind") == "twin":
            twins.setdefault(r.get("parent_book_id"), {})[r.get("twin")] = r.get("book_id")
    out = []
    for p in parents:
        t = twins.get(p["book_id"], {})
        kind = next((k for k in TWIN_PREFERENCE if k in t), None)
        if kind is None:
            raise LibTrialInputMissing(f"{p.get('name')}: no frozen twin of type {TWIN_PREFERENCE}")
        out.append({"book_id": p["book_id"], "name": p["name"], "kind": p.get("kind"),
                    "twin_book_id": t[kind], "twin_type": kind})
    return sorted(out, key=lambda x: x["name"])


def cluster_of(name: str, bridge_rows: Iterable[dict]) -> str:
    """The bridge's full-window cluster id, or `solo:<name>` for a book the
    bridge could not cluster (forward-only books have no backtest series)."""
    for r in bridge_rows:
        if r.get("book") == name:
            c = r.get("cluster_full")
            return str(c) if c is not None else f"solo:{name}"
    return f"solo:{name}"


# ── the pooled statistic ─────────────────────────────────────────────────────

def pooled_sd(sigmas: dict, clusters: dict, rho_within: float, rho_between: float) -> float:
    """sd of D = mean over clusters of (mean over the cluster's books of d_i),
    with d_i ~ (0, sigma_i^2), corr rho_within inside a cluster and
    rho_between across clusters."""
    names = list(sigmas)
    by_c: dict = {}
    for n in names:
        by_c.setdefault(clusters[n], []).append(n)
    C = len(by_c)
    w = {n: 1.0 / (C * len(by_c[clusters[n]])) for n in names}
    var = 0.0
    for a in names:
        for b in names:
            if a == b:
                rho = 1.0
            elif clusters[a] == clusters[b]:
                rho = rho_within
            else:
                rho = rho_between
            var += w[a] * w[b] * rho * sigmas[a] * sigmas[b]
    return math.sqrt(max(var, 0.0))


def effective_bets(n_clusters: int, rho_between: float) -> float:
    """Equal-weight clusters with a common pairwise correlation behave like
    n / (1 + (n - 1) rho) independent bets."""
    return n_clusters / (1.0 + (n_clusters - 1) * rho_between) if n_clusters else 0.0


def pooled_z(diffs: dict, clusters: dict, frozen: dict, horizon: int) -> dict:
    """`diffs`: {book name: book return - twin return over the horizon}.
    `frozen`: the registration receipt's `frozen` block. The sigma of every book
    is READ from it, never re-estimated. The DECIDING `z` uses the amended
    correlations (`RHO_*_AS_READ`, estimated on the twin type actually read);
    `z_registered` uses the receipt's original correlations and is printed
    beside it, never decides."""
    key = f"sigma_{horizon}"
    sig = frozen.get(key) or {}
    missing = [n for n in diffs if n not in sig]
    if missing:
        raise LibTrialInputMissing(f"no frozen {key} for {missing[:3]}")
    cl = {n: clusters[n] for n in diffs}
    by_c: dict = {}
    for n, d in diffs.items():
        by_c.setdefault(cl[n], []).append(float(d))
    D = float(np.mean([np.mean(v) for v in by_c.values()])) if by_c else float("nan")
    s_ = {n: sig[n] for n in diffs}
    sd = pooled_sd(s_, cl, RHO_WITHIN_AS_READ, RHO_BETWEEN_AS_READ)
    sd_reg = pooled_sd(s_, cl, frozen["rho_within"], frozen["rho_between"])
    return {"horizon": horizon, "n_books": len(diffs), "n_clusters": len(by_c),
            "pooled_diff": D, "sd": sd, "z": (D / sd) if sd > 0 else None,
            "rho_basis": "as_read (amendment 2026-09-28): deciding",
            "sd_registered": sd_reg, "z_registered": (D / sd_reg) if sd_reg > 0 else None,
            "effective_bets": effective_bets(len(by_c), RHO_BETWEEN_AS_READ)}


def decide(z21: Optional[dict], z63: Optional[dict], *, n_expected: int, n_dropped: int) -> dict:
    """The written kill rule, as code."""
    if n_expected and n_dropped / n_expected > MAX_DROPPED_SHARE:
        return {"verdict": "CANNOT_DETERMINE",
                "why": f"{n_dropped} of {n_expected} books dropped (> {MAX_DROPPED_SHARE:.0%}); extend"}
    if z63 is None:
        if z21 and z21.get("z") is not None and z21["z"] <= Z_EARLY_KILL:
            return {"verdict": "EARLY_KILL", "why": f"z_21 {z21['z']:+.2f} <= {Z_EARLY_KILL}"}
        return {"verdict": "INTERIM", "why": "21-session read is reported, never acted on (except EARLY_KILL)"}
    z = z63.get("z")
    if z is None:
        return {"verdict": "CANNOT_DETERMINE", "why": "no z at 63 sessions"}
    if z >= Z_PASS and (z21 or {}).get("pooled_diff", 0) > 0:
        return {"verdict": "SURVIVES", "why": f"z_63 {z:+.2f} >= {Z_PASS} and the 21-session sign is positive"}
    if z < Z_KILL:
        return {"verdict": "KILL", "why": f"z_63 {z:+.2f} < {Z_KILL}"}
    return {"verdict": "CANNOT_DISTINGUISH", "why": f"{Z_KILL} <= z_63 {z:+.2f} < {Z_PASS}: extend to 126 sessions"}


# ── luck ─────────────────────────────────────────────────────────────────────

def luck_table(ks: Iterable[int], rhos: Iterable[float], *, z_bar: float = 2.0,
               n_sim: int = 100_000, seed: int = 20260928) -> list[dict]:
    """P(max of K equicorrelated N(0,1) >= z_bar), E[max z], by simulation.
    Zero skill everywhere: what the BEST book reads by luck alone."""
    rng = np.random.default_rng(seed)
    out = []
    for k in ks:
        for rho in rhos:
            k = int(k)
            common = rng.standard_normal(n_sim)
            idio = rng.standard_normal((n_sim, k))
            z = math.sqrt(rho) * common[:, None] + math.sqrt(1.0 - rho) * idio
            mx = z.max(axis=1)
            out.append({"k": k, "rho": float(rho), "p_best_ge_z": float((mx >= z_bar).mean()),
                        "e_best_z": float(mx.mean()), "z_bar": z_bar,
                        "p_independent_closed_form": (1.0 - (0.5 * math.erfc(-z_bar / math.sqrt(2))) ** k)
                        if rho == 0 else None})
    return out


def ensure_lib_forward_trial(db_path=None, *, frozen_receipt: str = "") -> int:
    """Idempotently register the trial in `rule_experiments` (the cumulative
    count the DSR/PBO gates deflate against). The production registry needs the
    same call at startup (one line in backend/main.py, owed -- not made here)."""
    from backend.services.portfolio_intelligence.trial_registry import ensure_trial_registered
    notes = {
        "trial": TRIAL_ID,
        "hypothesis": ("the strategy library's frozen forward books beat their frozen twins, pooled by "
                       "cluster (honest prior: weak -- 2 of 288 backtest cells cleared t >= 2 vs the "
                       "matched twin in both windows, about what luck gives)"),
        "primary_metric": "pooled-by-cluster (book - twin) return over 63 sessions, z vs the frozen sigma",
        "decision_rule": {"survives": f"z_63 >= {Z_PASS} and the 21-session sign > 0",
                          "kill": f"z_63 < {Z_KILL}", "early_kill": f"z_21 <= {Z_EARLY_KILL}",
                          "otherwise": "CANNOT_DISTINGUISH: extend to 126 sessions, same rule"},
        "entry": ENTRY_SESSION, "read_21": READ_21, "read_63": READ_63,
        "creates_books": False, "frozen_receipt": frozen_receipt, "doc": DOC,
    }
    return ensure_trial_registered(PARAM, notes, db_path=db_path)
