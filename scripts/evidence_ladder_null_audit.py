"""How often does the evidence ladder label a book that has NO edge? (cloud audit, 2026-10-07)

    python -m scripts.evidence_ladder_null_audit               # print the tables; write nothing
    python -m scripts.evidence_ladder_null_audit --receipt     # also write a run-id receipt

THE RULE BEING MEASURED
=======================
`book_dna.evidence_label` awards the public rungs from SIGNS:

* EARLY_EVIDENCE: >= `BOOK_DNA_EARLY_MIN_SESSIONS` (21) sessions, compounded excess
  over SPY > 0, and >= 2 of 3 contiguous sub-window excesses > 0
  (`book_dna.subwindows`);
* REPLICATED: EARLY_EVIDENCE plus an excess over the fair twin > 0 (any margin), or
  a same-rule sibling that is itself EARLY_EVIDENCE.

A sign rule is almost scale-free: under "no edge" its rate does not depend on the
market's drift or on how big the book is, and depends on volatility only through
compounding drag (the excess is compounded book minus compounded SPY, so extra
tracking variance costs about sigma^2/2 a session and makes a no-edge book slightly
LESS likely to be labelled; at a ~16%/yr tracking error that is under a point at 63
sessions). So the rate can be measured once, here, without any data -- and it is the
number a reader of `/arena` needs before an `EARLY_EVIDENCE` badge means anything.

HOW
===
Synthetic daily SPY and book returns (book = SPY + alpha + tracking noise; fair twin
= SPY + independent or correlated tracking noise), the excess series fed through
`book_dna.subwindows` and `book_dna.evidence_label` THEMSELVES for every single-look
cell. For the daily re-evaluation the pages actually perform (a label recomputed
every session from 21 on), a vectorised copy of the same two functions is used for
speed -- and `check_vectorised_against_module()` proves it agrees with the module on
random paths before any number is printed (it refuses otherwise).

Beside the ladder sits a time-uniform alternative, so the trade-off is on one
table: Robbins' normal-mixture boundary on the cumulative excess (Howard, Ramdas,
McAuliffe & Sekhon 2021), whose crossing probability under no edge is <= alpha at
EVERY look by Ville's inequality. It is shown with the true noise scale (an
operational version must estimate it; that costs a little power, not validity in
large samples).

WHAT IT DOES NOT DO
===================
It changes nothing in `book_dna`. Whether a rung needs a different rule is the
owner's decision (`docs/research_notes/2026-10-07/evidence_ladder_null_rate_cloud_2026-10-07.md`
states the options); this supplies the number that decision needs. Seeds are fixed,
so two runs print the same table.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import book_dna as BD  # noqa: E402

TRADING_DAYS = 252
#: Daily SPY: ~16%/yr vol, ~10%/yr drift. The sign rule does not care; the
#: values only make the paths look like markets.
SPY_MU, SPY_SIGMA = 0.10 / TRADING_DAYS, 0.16 / math.sqrt(TRADING_DAYS)
#: Daily tracking error of a concentrated stock book vs SPY (~16%/yr).
TE_SIGMA = 0.16 / math.sqrt(TRADING_DAYS)
LOOKS = (21, 42, 63, 126, 252)
EDGES_PER_YEAR = (0.0, 0.05, 0.10, 0.20)
ALPHA_BOUNDARY = 0.05
#: Mixture scale for the Robbins boundary, in sessions: tightest around a quarter.
RHO_SESSIONS = 63.0


class AuditRefused(RuntimeError):
    """The vectorised copy disagrees with book_dna: nothing is printed as a result."""


def simulate(n_paths: int, n_days: int, *, alpha_year: float, seed: int,
             twin_corr: float = 0.0, fat_tails: bool = False) -> dict:
    """Daily (spy, book, twin) returns, shape (n_paths, n_days)."""
    rng = np.random.default_rng(seed)

    def noise(size):
        if not fat_tails:
            return rng.standard_normal(size)
        df = 4.0                              # Student t(4), rescaled to unit variance
        return rng.standard_t(df, size) / math.sqrt(df / (df - 2.0))

    spy = SPY_MU + SPY_SIGMA * noise((n_paths, n_days))
    e_book = noise((n_paths, n_days))
    e_twin = twin_corr * e_book + math.sqrt(max(0.0, 1 - twin_corr ** 2)) * noise((n_paths, n_days))
    book = spy + alpha_year / TRADING_DAYS + TE_SIGMA * e_book
    twin = spy + TE_SIGMA * e_twin
    return {"spy": spy, "book": book, "twin": twin}


# ─────────────────────────────── the module's own functions ──────────────────

def module_label(book: np.ndarray, spy: np.ndarray, twin: np.ndarray | None, n: int,
                 p: dict) -> str:
    """One path, one look, through book_dna's own subwindows + evidence_label."""
    series = [(f"d{i:04d}", float(book[i]), float(spy[i])) for i in range(n)]
    sub = BD.subwindows(series, n)
    excess_pp = 100.0 * (float(np.prod(1 + book[:n])) - float(np.prod(1 + spy[:n])))
    twin_pp = None
    if twin is not None:
        twin_pp = 100.0 * (float(np.prod(1 + book[:n])) - float(np.prod(1 + twin[:n])))
    return BD.evidence_label(sessions=n, excess_pp=round(excess_pp, 3), sub=sub,
                             fair_twin_excess_pp=twin_pp, replicated_by=None, p=p)["label"]


# ─────────────────────────────── the vectorised copy ─────────────────────────

def _compound(x: np.ndarray, start: int, stop: int) -> np.ndarray:
    return np.prod(1.0 + x[:, start:stop], axis=1) - 1.0


def vector_labels(book: np.ndarray, spy: np.ndarray, twin: np.ndarray | None, n: int,
                  p: dict) -> np.ndarray:
    """0 = OBSERVED, 1 = EARLY_EVIDENCE, 2 = REPLICATED for every path at look n.

    The same arithmetic as `book_dna.subwindows` (np.array_split thirds, compounded
    book minus compounded SPY, rounded to 3 dp in pp, > 0) and `evidence_label`."""
    m = book.shape[0]
    if n < p["early_min_sessions"] or n < 3:
        return np.zeros(m, dtype=int)
    bounds = [(int(c[0]), int(c[-1]) + 1) for c in np.array_split(np.arange(n), 3)]
    n_pos = np.zeros(m, dtype=int)
    for a, b in bounds:
        sub_pp = np.round(100.0 * (_compound(book, a, b) - _compound(spy, a, b)), 3)
        n_pos += (sub_pp > 0).astype(int)
    excess_pp = np.round(100.0 * (_compound(book, 0, n) - _compound(spy, 0, n)), 3)
    early = (excess_pp > 0) & (n_pos >= 2)
    out = early.astype(int)
    if twin is not None:
        twin_pp = 100.0 * (_compound(book, 0, n) - _compound(twin, 0, n))
        out = np.where(early & (twin_pp > 0), 2, out)
    return out


def check_vectorised_against_module(p: dict, *, n_check: int = 400, seed: int = 7) -> dict:
    """Refuse unless the copy agrees with book_dna on every sampled (path, look)."""
    sim = simulate(n_check, TRADING_DAYS, alpha_year=0.05, seed=seed, twin_corr=0.5)
    rng = np.random.default_rng(seed + 1)
    names = {0: "OBSERVED", 1: "EARLY_EVIDENCE", 2: "REPLICATED"}
    mismatches = 0
    checked = 0
    for n in sorted({21, 22, 23, 40, 63, 64, 65, int(rng.integers(21, TRADING_DAYS + 1))}):
        vec = vector_labels(sim["book"], sim["spy"], sim["twin"], n, p)
        for i in range(n_check):
            mod = module_label(sim["book"][i], sim["spy"][i], sim["twin"][i], n, p)
            checked += 1
            if mod.split("(")[0] != names[int(vec[i])]:
                mismatches += 1
    if mismatches:
        raise AuditRefused(f"the vectorised copy disagrees with book_dna on {mismatches} of "
                           f"{checked} (path, look) pairs; no rate is reported")
    return {"checked_pairs": checked, "mismatches": 0}


# ─────────────────────────────── the time-uniform boundary ───────────────────

def robbins_crossed(book: np.ndarray, spy: np.ndarray, *, start: int, alpha: float,
                    rho: float) -> np.ndarray:
    """Per path: did the cumulative daily excess ever cross the (upper half of the)
    two-sided normal-mixture boundary between session `start` and the end?

    S_t = sum of standardised daily excess; boundary |S_t| >= sqrt((t + rho) *
    (2 log(1/alpha) + log((t + rho) / rho))). P(ever cross | no edge) <= alpha."""
    z = (book - spy) / TE_SIGMA
    s = np.cumsum(z, axis=1)
    t = np.arange(1, z.shape[1] + 1, dtype=float)
    bound = np.sqrt((t + rho) * (2.0 * math.log(1.0 / alpha) + np.log((t + rho) / rho)))
    hit = s[:, start - 1:] >= bound[start - 1:]
    return hit.any(axis=1)


# ─────────────────────────────── the audit ───────────────────────────────────

def run(n_paths: int = 20_000, seed: int = 20261007) -> dict:
    p = BD.params()
    check = check_vectorised_against_module(p)
    single, ever, twin_rows, fat, power = [], [], [], [], []
    for k, edge in enumerate(EDGES_PER_YEAR):
        sim = simulate(n_paths, TRADING_DAYS, alpha_year=edge, seed=seed + k, twin_corr=0.0)
        for n in LOOKS:
            lab = vector_labels(sim["book"], sim["spy"], sim["twin"], n, p)
            single.append({"edge_per_year": edge, "look_session": n,
                           "p_early_or_better": float((lab >= 1).mean()),
                           "p_replicated": float((lab == 2).mean())})
        for horizon in (63, 126, 252):
            hit = np.zeros(n_paths, dtype=bool)
            for n in range(p["early_min_sessions"], horizon + 1):
                hit |= vector_labels(sim["book"], sim["spy"], None, n, p) >= 1
            crossed = robbins_crossed(sim["book"][:, :horizon], sim["spy"][:, :horizon],
                                      start=p["early_min_sessions"], alpha=ALPHA_BOUNDARY,
                                      rho=RHO_SESSIONS)
            ever.append({"edge_per_year": edge, "daily_looks_through": horizon,
                         "p_ever_early_evidence": float(hit.mean()),
                         "p_ever_robbins_boundary": float(crossed.mean())})
    for j, corr in enumerate((0.0, 0.5, 0.8)):
        sim = simulate(n_paths, TRADING_DAYS, alpha_year=0.0, seed=seed + 100 + j, twin_corr=corr)
        for n in (21, 63, 252):
            lab = vector_labels(sim["book"], sim["spy"], sim["twin"], n, p)
            twin_rows.append({"twin_noise_corr": corr, "look_session": n,
                              "p_replicated_no_edge": float((lab == 2).mean())})
    sim = simulate(n_paths, TRADING_DAYS, alpha_year=0.0, seed=seed + 200, fat_tails=True)
    for n in (21, 63, 252):
        lab = vector_labels(sim["book"], sim["spy"], sim["twin"], n, p)
        fat.append({"look_session": n, "p_early_or_better_t4": float((lab >= 1).mean())})
    null_by_n = {r["look_session"]: r["p_early_or_better"] for r in single
                 if r["edge_per_year"] == 0.0}
    for r in single:
        if r["edge_per_year"] > 0:
            base = null_by_n[r["look_session"]]
            power.append({**r, "likelihood_ratio_vs_no_edge":
                          round(r["p_early_or_better"] / base, 3) if base else None})
    return {
        "audit": "evidence_ladder_null_audit", "licence": "RESEARCH_NOTE",
        "rule": {"early_min_sessions": p["early_min_sessions"],
                 "early": "excess > 0 and >= 2 of 3 sub-windows > 0 (book_dna.evidence_label)",
                 "replicated": "early and excess over the fair twin > 0"},
        "model": {"paths": n_paths, "seed": seed, "spy_mu_daily": SPY_MU,
                  "spy_sigma_daily": SPY_SIGMA, "tracking_error_daily": TE_SIGMA,
                  "note": ("the ladder's rule is sign-based, so its no-edge rates depend on "
                           "these scales only through compounding drag (small at this "
                           "tracking error); the edge rows depend on edge / tracking error")},
        "vectorised_copy_check": check,
        "single_look": single, "daily_reevaluation": ever, "replicated_vs_twin": twin_rows,
        "fat_tails_t4": fat, "edge_likelihood_ratios": power,
        "boundary": {"kind": "Robbins normal mixture, two-sided, upper crossings counted",
                     "alpha": ALPHA_BOUNDARY, "rho_sessions": RHO_SESSIONS,
                     "reference": "Howard, Ramdas, McAuliffe & Sekhon (2021), Annals of Statistics 49(2)"},
    }


def render(r: dict) -> str:
    out = [f"EVIDENCE LADDER NULL AUDIT ({r['model']['paths']:,} paths, seed {r['model']['seed']}; "
           f"vectorised copy == book_dna on {r['vectorised_copy_check']['checked_pairs']:,} pairs)",
           "", "Single look -- P(label >= EARLY_EVIDENCE):",
           "  edge/yr   " + "  ".join(f"n={n:<4}" for n in LOOKS)]
    for edge in EDGES_PER_YEAR:
        row = [x for x in r["single_look"] if x["edge_per_year"] == edge]
        out.append(f"  {edge:>6.0%}   " + "  ".join(f"{x['p_early_or_better']:.3f}" for x in row))
    out += ["", "Daily re-evaluation from session 21 -- P(EVER labelled) vs the time-uniform boundary:",
            "  edge/yr  through   ever EARLY   ever Robbins(a=0.05)"]
    for x in r["daily_reevaluation"]:
        out.append(f"  {x['edge_per_year']:>6.0%}  {x['daily_looks_through']:>7}   "
                   f"{x['p_ever_early_evidence']:>10.3f}   {x['p_ever_robbins_boundary']:>10.3f}")
    out += ["", "No edge -- P(REPLICATED) through the fair-twin clause:"]
    for x in r["replicated_vs_twin"]:
        out.append(f"  twin noise corr {x['twin_noise_corr']:.1f}, n={x['look_session']:<4} "
                   f"{x['p_replicated_no_edge']:.3f}")
    out += ["", "No edge, fat tails (t4) -- P(label >= EARLY_EVIDENCE):"]
    for x in r["fat_tails_t4"]:
        out.append(f"  n={x['look_session']:<4} {x['p_early_or_better_t4']:.3f}")
    out += ["", "Likelihood ratio of the badge (P(EARLY | edge) / P(EARLY | no edge)):"]
    for x in r["edge_likelihood_ratios"]:
        out.append(f"  edge {x['edge_per_year']:.0%}/yr, n={x['look_session']:<4} "
                   f"LR {x['likelihood_ratio_vs_no_edge']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evidence_ladder_null_audit",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("--paths", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--receipt", action="store_true",
                    help="write backend/data/optimus/audits/evidence_ladder_null_audit_<run id>.json")
    a = ap.parse_args(argv)
    try:
        r = run(a.paths, a.seed)
    except AuditRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(render(r))
    if a.receipt:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        r["run_id"] = run_id
        out = REPO / "backend" / "data" / "optimus" / "audits" / f"evidence_ladder_null_audit_{run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"\nreceipt: {out.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
