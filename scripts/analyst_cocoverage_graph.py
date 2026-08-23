"""ANALYST-COCOVERAGE-GRAPH-1 — the cheapest possible test of the graph idea.

WHY THIS FIRST, AND WHY IT IS ALLOWED TO FAIL
=============================================
`ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md` says no GNN until simple graph
propagation features beat a non-graph baseline. This is that test, and it costs
one groupby over data already on disk: IBES tells us which analysts cover which
firms, so "these two companies share analysts" is free.

Shared-analyst coverage is a documented cross-firm information channel. The
AEGIS-specific part is the one no published version can do: **weight the edge by
the analysts' MEASURED reliability**, which `docs/FINDING_2026-08-23_ANALYST_
RELIABILITY.md` established persists out of sample (unrestricted corr 0.25,
every evidence rung's CI excluding zero). If reliability-weighted edges carry
nothing beyond raw co-coverage, that is worth knowing before anyone builds a
graph neural network on top of the idea.

WHAT IS DECLARED BEFORE THE RUN
===============================
Everything in `SPEC`, including the decision rule and the economic bar. The
`spec_hash` is stamped into the receipt, so a bar moved after seeing the answer
is visible as a hash that does not match. This is a SCREEN under
`PRODUCT_EXPERIMENT`, not a `RESEARCH_CLAIM`: it decides what to BUILD next, and
it may not be cited as evidence that anything is alpha.

THE SAMPLE SIZE IS MONTHS
=========================
CANON §58: `n_effective` counts DATE BLOCKS. One month is one block. Roughly
4,000 firms per month is breadth, not independence -- they share the market
factor, and a monthly cross-sectional IC computed over 4,000 names still gives
exactly one observation of whether the signal worked that month.

POINT-IN-TIME
=============
* coverage at month `t` uses recommendations issued STRICTLY BEFORE `t`;
* analyst reliability applied during year `Y` is estimated only on claims
  announced before `Y` (expanding window, never the full sample);
* the peer signal is the peer return realised in month `t`; the target is the
  firm's own return in month `t+1`. Nothing in the signal is measured after the
  point the signal would have been acted on.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
ACTOR = REPO / "backend" / "data" / "optimus" / "actor_corpus"
OUT = REPO / "backend" / "data" / "optimus" / "graph"


#: FROZEN BEFORE THE RUN. The bar and the decision rule are the two things a
#: screen can quietly move after seeing its answer, so they are declared here
#: and hashed into the receipt.
SPEC: dict = {
    "trial_id": "ANALYST-COCOVERAGE-GRAPH-1",
    "licence": "PRODUCT_EXPERIMENT (screen — decides what to build, never cited as alpha)",
    "question": (
        "Does the return of firms connected by SHARED ANALYST COVERAGE predict "
        "a firm's next-month return, and does weighting those edges by the "
        "analysts' MEASURED reliability add anything over raw co-coverage?"),
    "coverage_window_months": 12,
    "min_shared_analysts": 1,
    "min_peers": 3,
    "min_firms_per_month": 200,
    "eval_years": [2014, 2024],
    "reliability": {
        "source": "actor_corpus/ibes_graded.parquet",
        "scheme": "expanding window — year Y uses claims announced before Y",
        "min_claims": 30,
    },
    "signal_month": "peer return realised in month t",
    "target_month": "own return in month t+1",
    "primary_metric": (
        "mean monthly cross-sectional Spearman rank IC of signal vs next-month "
        "return"),
    "n_effective": "MONTHS (date blocks) — never firm-months (CANON §58)",
    "economic_bar_ic": 0.01,
    "multiplicity": "BH-FDR across every arm in this run, q <= 0.10 (CANON §63)",
    "decision_rule": (
        "CONTINUE the graph programme iff at least one arm has mean IC >= "
        "0.01 AND survives BH-FDR at q <= 0.10. Otherwise the graph programme "
        "STOPS HERE and the GNN is never built. A directional arm beating its "
        "own reverse is reported but does not by itself license continuation."),
    "arms": [
        "own_ret_1m         CONTROL: the firm's own last-month return "
        "(short-term reversal). Not a graph arm; present so a peer signal that "
        "is merely own momentum in disguise is visible.",
        "peer_eq            equal-weighted over DISTINCT peers",
        "peer_shared        weighted by number of shared analysts",
        "peer_rel           weighted by PIT analyst reliability (the AEGIS arm)",
        "peer_leader        peers with MORE analyst coverage than the target "
        "(leader -> laggard)",
        "peer_laggard       peers with LESS coverage (the reverse direction; "
        "the leader story predicts this is weaker)",
        "peer_rel_near_high peer_rel restricted to targets within 5% of their "
        "52-week high",
    ],
    "what_this_cannot_show": (
        "Tradability. This is an IC screen with no costs, no capacity, no "
        "turnover limit and no portfolio construction. An IC above the bar "
        "licenses BUILDING a selector, never claiming an edge."),
}


#: AMENDMENT-1, declared 2026-08-24 AFTER seeing the primary run. It is
#: therefore POST-HOC and cannot upgrade the primary verdict; it exists because
#: the primary run's diagnosis showed one arm was never actually tested.
#:
#: WHAT THE DIAGNOSIS FOUND. `peer_rel` weighted an edge by `max(0, analyst
#: edge)`, which deletes two populations at once: every analyst without 30
#: prior graded claims, and every analyst whose measured edge is negative. In
#: 2014 that left **0.1%** of coverage rows carrying any weight at all, and even
#: 2024 only reaches 28%. The arm returned +0.005 (p=0.73) because its graph was
#: nearly empty, not because reliability carries nothing. Reporting that as
#: "reliability weighting does not work" would be correct arithmetic against the
#: wrong world.
#:
#: So the amendment tests the hypothesis the way it should have been posed:
#: reliability as a TILT around an intact graph rather than a filter that
#: destroys it. An unknown analyst keeps weight 1.0 and contributes exactly as
#: they do in `peer_eq`; a measured analyst is scaled up or down.
AMENDMENT: dict = {
    "amendment_id": "ANALYST-COCOVERAGE-GRAPH-1/AMENDMENT-1",
    "status": "POST-HOC — declared after seeing the primary run",
    "cannot": ("upgrade the primary verdict, or be cited as a confirmation. "
               "A hypothesis re-specified after its first answer is a new "
               "hypothesis and owes fresh evidence."),
    "why": ("the primary `peer_rel` arm was STARVED, not refuted: 0.1% of 2014 "
            "coverage carried a weight, 28% by 2024"),
    "new_arms": [
        "peer_rel_tilt      w = clip(1 + k*edge, 0.25, 4); unknown analysts "
        "keep w=1, so the graph stays intact and only the TILT is tested",
        "peer_eq_near_high  the 52-week-high slice attached to the arm that "
        "actually works. The primary run attached it to `peer_rel` and so "
        "measured the starved graph inside a subsample — a mis-specification, "
        "not a result about 52-week highs",
    ],
    "tilt_k": 2.0,
    "tilt_bounds": [0.25, 4.0],
    "near_high_threshold": -0.05,
    "decision_rule": (
        "`peer_rel_tilt` beating `peer_eq` by more than its own paired SE is "
        "the only thing that would license reliability-weighted edges as a "
        "distinct mechanism. Equal performance means reliability adds nothing "
        "HERE and the cheap arm wins on parsimony."),
}


#: AMENDMENT-2, declared 2026-08-24, also POST-HOC. The single most likely
#: mundane explanation of the primary result, and the primary run did not test
#: it: analysts cover firms in the same INDUSTRY, so "firms connected by shared
#: analysts" is largely "firms in the same sector". If `peer_eq` is industry
#: momentum wearing a graph's clothes, the graph adds nothing a SIC dummy does
#: not, and the graph programme should not continue whatever the primary
#: verdict said.
#:
#: The literature's actual claim is the opposite -- that shared-analyst links
#: carry information BEYOND industry -- so this is the test that decides which
#: story is true here, on this window, with this construction.
AMENDMENT_2: dict = {
    "amendment_id": "ANALYST-COCOVERAGE-GRAPH-1/AMENDMENT-2",
    "status": "POST-HOC — declared after the primary run",
    "question": ("is the co-coverage signal anything more than industry "
                 "momentum?"),
    "new_arms": [
        "sic2_peer          COMPETING BASELINE: equal-weighted return of every "
        "firm in the same SIC2, ignoring analysts entirely. Needs no graph.",
        "peer_eq_xsic       the co-coverage signal computed ONLY over peers in "
        "a DIFFERENT SIC2. If the graph carries information beyond industry, "
        "this survives; if it is industry momentum, this collapses.",
    ],
    "decision_rule": (
        "The graph earns its place ONLY if `peer_eq_xsic` clears the same 0.01 "
        "bar. If it does not, the co-coverage result is a sector effect and "
        "the graph programme STOPS regardless of the primary verdict — a "
        "cheaper mechanism that explains the same number wins."),
}


#: AMENDMENT-3, declared 2026-08-24. POST-HOC, and it asks the question that
#: decides whether the CONTINUE verdict means anything in production.
#:
#: THE SCREEN VALIDATED A SIGNAL THAT MAY HAVE NO LIVE DATA PATH. Co-coverage
#: was measured at ANALYST granularity (`amaskcd`), which exists only in IBES --
#: a WRDS research dataset, not a production feed. What the live stack actually
#: has is `analyst_intelligence`'s upgrades/downgrades feed, which attributes to
#: the FIRM ("JP Morgan", "Goldman Sachs"), not the individual.
#:
#: Those are different graphs. Measured over 2014-2024 US recommendations:
#: 8,336 distinct analysts against 589 distinct firms, and a median analyst
#: follows 4 names where a median firm follows 14. A firm-level graph is far
#: denser and far less selective, so an effect carried by "these two companies
#: share an ANALYST" need not survive "these two companies share a BANK".
#:
#: A signal that cannot be computed live is not a selector. This measures
#: whether the licensed one can be.
AMENDMENT_3: dict = {
    "amendment_id": "ANALYST-COCOVERAGE-GRAPH-1/AMENDMENT-3",
    "status": "POST-HOC — declared after the primary run",
    "question": ("does the co-coverage effect survive at the FIRM granularity "
                 "a live feed can actually supply?"),
    "why": ("the primary screen used `amaskcd` (individual analyst), which "
            "exists only in IBES. Production has firm-attributed "
            "upgrades/downgrades via yfinance. 8,336 analysts vs 589 firms; "
            "median coverage 4 names vs 14."),
    "arm": "peer_eq computed over a graph whose edges are SHARED FIRMS",
    "decision_rule": (
        "GRAPH_PROPAGATION_v1 is IMPLEMENTABLE iff the firm-level arm clears "
        "the same 0.01 bar the primary declared. If it does not, the licensed "
        "selector has no live data path at the granularity it was validated "
        "at, and the CONTINUE verdict must say so rather than being handed to "
        "a builder who discovers it afterwards."),
}


def amendment_3_hash() -> str:
    return hashlib.sha256(
        json.dumps(AMENDMENT_3, sort_keys=True).encode()).hexdigest()[:16]


def amendment_2_hash() -> str:
    return hashlib.sha256(
        json.dumps(AMENDMENT_2, sort_keys=True).encode()).hexdigest()[:16]


def amendment_hash() -> str:
    return hashlib.sha256(
        json.dumps(AMENDMENT, sort_keys=True).encode()).hexdigest()[:16]


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:16]


# ───────────────────────────────────────────────────────── substrate


def _cusip_to_permno() -> pd.DataFrame:
    n = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                        columns=["permno", "ncusip", "namedt", "nameendt"])
    n = n.dropna(subset=["ncusip"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"])
    return n


def sic2_map() -> pd.DataFrame:
    """permno -> SIC2 division, with the name-history dates it is valid for."""
    n = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                        columns=["permno", "hsiccd", "namedt", "nameendt"])
    n = n.dropna(subset=["hsiccd"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"])
    n["sic2"] = (n["hsiccd"].astype("int64") // 100).astype("int16")
    return n[["permno", "sic2", "namedt", "nameendt"]]


def monthly_panel(y0: int, y1: int) -> pd.DataFrame:
    """Per (permno, month): return, market cap, and distance to 52-week high.

    Built from CRSP daily so the 52-week high is a real trailing high rather
    than a max of twelve month-end closes.
    """
    # SCHEMA DRIFT IS REAL HERE. `crsp_dsf_1990..2012` carry only
    # (permno, date, prc, ret, vol); 2013 onward add shrout, cfacpr, askhi and
    # the rest. Filling the missing ones with defaults would put an unadjusted
    # price series into the 52-week high and read every split as a crash, so
    # the years without a split factor are REFUSED rather than patched.
    need = ["permno", "date", "ret", "prc", "shrout", "cfacpr"]
    import pyarrow.parquet as _pq
    frames, missing = [], []
    # One warm-up year is enough: `high_252` needs min_periods=120 sessions, so
    # a January eval month already has a full trailing year behind it.
    for yr in range(y0 - 1, y1 + 1):
        p = WRDS / f"crsp_dsf_{yr}.parquet"
        if not p.exists():
            missing.append(f"{yr}: absent")
            continue
        have = set(_pq.ParquetFile(p).schema_arrow.names)
        gap = [c for c in need if c not in have]
        if gap:
            missing.append(f"{yr}: missing {gap}")
            continue
        frames.append(pd.read_parquet(p, columns=need))
    if missing:
        sys.exit("REFUSED: the evaluation window is not covered by CRSP "
                 "files carrying a split factor:\n  " + "\n  ".join(missing)
                 + "\nNarrow eval_years rather than filling the gap — an "
                   "unadjusted price makes every split look like a crash "
                   "against the 52-week high.")
    if not frames:
        sys.exit("REFUSED: no crsp_dsf_*.parquet on disk")
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d = d.dropna(subset=["ret"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    d = d.dropna(subset=["ret"])

    # Adjusted price, so a split does not read as a 50% drawdown from the high.
    d["px"] = (d["prc"].abs() / d["cfacpr"].replace(0, np.nan))
    d = d.sort_values(["permno", "date"])
    # Trailing 252-session high, per name.
    d["high_252"] = (d.groupby("permno")["px"]
                     .transform(lambda s: s.rolling(252, min_periods=120).max()))
    d["month"] = d["date"].values.astype("datetime64[M]")

    # Compound in log space: a per-group lambda over ~700k groups is minutes,
    # a grouped sum is seconds. Clipped at -99.99% because a delisting return
    # of exactly -1 sends log1p to -inf and takes the whole month with it.
    d["lg"] = np.log1p(d["ret"].clip(lower=-0.9999))
    g = d.groupby(["permno", "month"], sort=False)
    out = g.agg(
        lg=("lg", "sum"),
        px=("px", "last"),
        high_252=("high_252", "last"),
        shrout=("shrout", "last"),
        n_days=("ret", "size"),
    ).reset_index()
    out["ret"] = np.expm1(out["lg"])
    out = out.drop(columns=["lg"])
    # A month with a handful of sessions is a delisting or a halt, not a month.
    out = out[out["n_days"] >= 15].copy()
    out["mcap"] = out["px"] * out["shrout"]
    out["dist_high"] = out["px"] / out["high_252"] - 1.0
    return out


def coverage(y0: int, y1: int, id_col: str = "amaskcd") -> pd.DataFrame:
    """(coverer, permno, month) — who covered what, using only the past.

    `id_col` is `amaskcd` (individual analyst, IBES-only) or `estimid` (the
    brokerage firm, which a live feed can supply). AMENDMENT-3.

    An analyst covers a firm in month `t` if they issued a recommendation on it
    in the `coverage_window_months` ending STRICTLY BEFORE `t`.
    """
    recs = pd.read_parquet(
        WRDS / "bulk" / "ibes__recddet.parquet",
        columns=["cusip", id_col, "anndats", "usfirm"])
    recs["anndats"] = pd.to_datetime(recs["anndats"])
    recs = recs[(recs["usfirm"] == 1)
                & (recs["anndats"].dt.year >= y0 - 2)
                & (recs["anndats"].dt.year <= y1)]
    link = _cusip_to_permno()
    m = recs.merge(link, left_on="cusip", right_on="ncusip", how="inner")
    m = m[(m["anndats"] >= m["namedt"]) & (m["anndats"] <= m["nameendt"])]
    m = m[[id_col, "permno", "anndats"]].copy()
    m["permno"] = m["permno"].astype("int64")
    # `estimid` is a broker code, not an integer; factorise so the sparse
    # incidence matrix can index it either way.
    m["amaskcd"] = (m[id_col].astype("int64") if id_col == "amaskcd"
                    else pd.factorize(m[id_col])[0].astype("int64"))
    m["rec_month"] = m["anndats"].values.astype("datetime64[M]")
    return m


def reliability_by_year(min_claims: int) -> dict[int, dict[int, float]]:
    """Analyst edge, expanding window: year Y uses only claims before Y.

    Reuses the graded corpus rather than regrading. Edge is the analyst's hit
    rate minus the base rate of THEIR OWN direction mix -- a pure-buy analyst
    scored against a blended null is credited with the buy/sell base-rate gap
    as if it were skill.
    """
    p = ACTOR / "ibes_graded.parquet"
    if not p.exists():
        sys.exit("REFUSED: actor corpus missing. Run "
                 "`python -m scripts.actor_corpus_ibes --build` first — the "
                 "reliability arm is the whole point of this screen.")
    g = pd.read_parquet(p, columns=["amaskcd", "direction", "outcome",
                                    "anndats"])
    g["year"] = pd.to_datetime(g["anndats"]).dt.year
    null_by_dir = g.groupby("direction")["outcome"].mean().to_dict()
    out: dict[int, dict[int, float]] = {}
    for yr in range(int(g["year"].min()) + 1, int(g["year"].max()) + 2):
        past = g[g["year"] < yr]
        if past.empty:
            out[yr] = {}
            continue
        agg = past.groupby("amaskcd").agg(n=("outcome", "size"),
                                          hit=("outcome", "mean"))
        mix = (past.groupby("amaskcd")["direction"]
               .apply(lambda s: float(np.mean([null_by_dir[int(d)] for d in s]))))
        edge = (agg["hit"] - mix)
        edge = edge[agg["n"] >= min_claims]
        out[yr] = edge.to_dict()
    return out


# ───────────────────────────────────────────────────────── the signal


def _month_signals(cov_m: pd.DataFrame, rets: dict[int, float],
                   n_cov: dict[int, int], rel: dict[int, float],
                   min_shared: int, min_peers: int,
                   sic: dict[int, int] | None = None) -> pd.DataFrame:
    """Every arm's peer signal for one month.

    Built as a sparse incidence product rather than by hand. The first version
    accumulated leave-one-out sums per analyst, which silently computes the
    SHARED-COUNT-weighted mean and cannot express the equal-weighted one: two
    firms sharing three analysts contributed three times, so `peer_eq` would
    have been `peer_shared` under a different name and the receipt would have
    reported two arms that were one arm.

        A            analysts x firms, 1 where the analyst covers the firm
        C = A' A     firms x firms, entry (i,j) = SHARED ANALYST COUNT
        B = C > 0    the same graph, unweighted
        C_rel = A_w' A   entry (i,j) = sum of covering analysts' reliability
    """
    from scipy import sparse

    cov_m = cov_m[cov_m["permno"].isin(rets)]
    if cov_m.empty:
        return pd.DataFrame()
    firms = np.array(sorted(cov_m["permno"].unique()))
    analysts = np.array(sorted(cov_m["amaskcd"].unique()))
    if len(firms) < 2:
        return pd.DataFrame()
    fi = {p: i for i, p in enumerate(firms)}
    ai = {a: i for i, a in enumerate(analysts)}

    rows = cov_m["amaskcd"].map(ai).to_numpy()
    cols = cov_m["permno"].map(fi).to_numpy()
    data = np.ones(len(rows), dtype="float64")
    A = sparse.csr_matrix((data, (rows, cols)),
                          shape=(len(analysts), len(firms)))
    A.data[:] = 1.0                      # an analyst covering a firm twice is
    A.sum_duplicates()                   # still one covering analyst
    A.data[:] = 1.0

    w = np.array([max(0.0, float(rel.get(int(a), 0.0))) for a in analysts])
    A_w = sparse.diags(w) @ A

    # AMENDMENT-1: reliability as a TILT, not a filter. An analyst with no
    # measured edge keeps weight 1.0 and contributes exactly as they do in
    # `peer_eq`, so the graph is never gutted and what is tested is the
    # marginal value of knowing an analyst is good.
    k = float(AMENDMENT["tilt_k"])
    lo, hi = AMENDMENT["tilt_bounds"]
    w_tilt = np.clip(
        1.0 + k * np.array([float(rel.get(int(a), 0.0)) for a in analysts]),
        lo, hi)
    A_t = sparse.diags(w_tilt) @ A

    C = (A.T @ A).tocsr()
    C.setdiag(0)
    C.eliminate_zeros()
    if min_shared > 1:
        C.data[C.data < min_shared] = 0.0
        C.eliminate_zeros()

    C_rel = (A_w.T @ A).tocsr()
    C_rel.setdiag(0)
    C_rel.eliminate_zeros()

    C_tilt = (A_t.T @ A).tocsr()
    C_tilt.setdiag(0)
    C_tilt.eliminate_zeros()

    B = C.copy()
    B.data[:] = 1.0

    r = np.array([rets[int(p)] for p in firms], dtype="float64")
    cov_n = np.array([n_cov.get(int(p), 0) for p in firms], dtype="float64")
    ones = np.ones(len(firms))

    def _wmean(M) -> np.ndarray:
        num = M @ r
        den = M @ ones
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)

    # DIRECTION. A peer is a LEADER of the target when MORE analysts cover it
    # -- the information-conduit reading. `laggard` is the identical
    # construction reversed, so the direction claim carries its own control
    # rather than an assertion.
    coo = C.tocoo()
    lead_mask = cov_n[coo.col] > cov_n[coo.row]
    lag_mask = cov_n[coo.col] < cov_n[coo.row]
    C_lead = sparse.csr_matrix(
        (coo.data[lead_mask], (coo.row[lead_mask], coo.col[lead_mask])),
        shape=C.shape)
    C_lag = sparse.csr_matrix(
        (coo.data[lag_mask], (coo.row[lag_mask], coo.col[lag_mask])),
        shape=C.shape)

    # AMENDMENT-2: the same graph with every SAME-INDUSTRY edge removed.
    peer_xsic = np.full(len(firms), np.nan)
    if sic:
        sic_arr = np.array([sic.get(int(p), -1) for p in firms])
        b = B.tocoo()
        keep = (sic_arr[b.row] != sic_arr[b.col]) & (sic_arr[b.row] >= 0) \
            & (sic_arr[b.col] >= 0)
        B_x = sparse.csr_matrix(
            (b.data[keep], (b.row[keep], b.col[keep])), shape=B.shape)
        peer_xsic = _wmean(B_x)

    n_peers = np.asarray((B @ ones)).ravel()
    df = pd.DataFrame({
        "permno": firms,
        "n_peers": n_peers,
        "peer_eq": _wmean(B),
        "peer_shared": _wmean(C),
        "peer_rel": _wmean(C_rel),
        "peer_rel_tilt": _wmean(C_tilt),
        "peer_leader": _wmean(C_lead),
        "peer_laggard": _wmean(C_lag),
        "peer_eq_xsic": peer_xsic,
    })
    return df[df["n_peers"] >= min_peers].copy()


# ───────────────────────────────────────────────────────── evaluation


def _rank_ic(x: np.ndarray, y: np.ndarray) -> float | None:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30:
        return None
    a, b = x[ok], y[ok]
    if np.all(a == a[0]) or np.all(b == b[0]):
        return None
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def _bh_fdr(pvals: dict[str, float], q: float) -> dict[str, bool]:
    """Benjamini-Hochberg over EVERY arm in the run (CANON §63)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    survives, thresh = {}, 0.0
    for i, (_k, p) in enumerate(items, start=1):
        if p <= i / m * q:
            thresh = i / m * q
    for k, p in items:
        survives[k] = p <= thresh
    return survives


def run(id_col: str = "amaskcd") -> dict:
    from scipy import stats

    y0, y1 = SPEC["eval_years"]
    print(f"spec_hash {spec_hash()}", flush=True)
    print("loading monthly panel...", flush=True)
    panel = monthly_panel(y0, y1)
    print(f"  {len(panel):,} firm-months", flush=True)
    print("loading coverage...", flush=True)
    cov = coverage(y0, y1, id_col)
    print(f"  {len(cov):,} linked recommendations", flush=True)
    rel_by_year = reliability_by_year(SPEC["reliability"]["min_claims"])
    sic_names = sic2_map()

    panel = panel.sort_values(["permno", "month"])
    # THE FORWARD MONTH MUST BE t+1, NOT "the next row". `shift(-1)` takes the
    # next month the name APPEARS in, so a halted or delisted-and-relisted firm
    # would have a return three months later labelled as next month's. Measured
    # here: 109 of 549,775 rows (0.02%) — immaterial to the estimate, and
    # nulled anyway because a target that is silently the wrong month is not a
    # thing to be approximately right about.
    panel["fwd_ret"] = panel.groupby("permno")["ret"].shift(-1)
    _nxt = panel.groupby("permno")["month"].shift(-1)
    _gap = (_nxt - panel["month"]).dt.days
    panel.loc[~_gap.between(28, 31), "fwd_ret"] = np.nan
    panel["own_ret_1m"] = panel["ret"]

    months = [m for m in sorted(panel["month"].unique())
              if y0 <= pd.Timestamp(m).year <= y1]
    win = SPEC["coverage_window_months"]
    arms = ["own_ret_1m", "peer_eq", "peer_shared", "peer_rel",
            "peer_leader", "peer_laggard", "peer_rel_near_high",
            # AMENDMENT-1 and -2 (post-hoc)
            "peer_rel_tilt", "peer_eq_near_high",
            "sic2_peer", "peer_eq_xsic"]
    post_hoc = {"peer_rel_tilt", "peer_eq_near_high",
                "sic2_peer", "peer_eq_xsic"}
    ics: dict[str, list[float]] = {a: [] for a in arms}
    ic_month: dict[str, list[str]] = {a: [] for a in arms}
    n_used = 0

    for m in months:
        ts = pd.Timestamp(m)
        lo = ts - pd.DateOffset(months=win)
        # STRICTLY before the signal month: coverage is what was knowable.
        cov_m = cov[(cov["anndats"] >= lo) & (cov["anndats"] < ts)]
        if cov_m.empty:
            continue
        cur = panel[panel["month"] == m]
        if len(cur) < SPEC["min_firms_per_month"]:
            continue
        rets = dict(zip(cur["permno"].to_numpy(), cur["ret"].to_numpy()))
        n_cov = cov_m.groupby("permno")["amaskcd"].nunique().to_dict()
        rel = rel_by_year.get(ts.year, {})
        sn = sic_names[(sic_names["namedt"] <= ts)
                       & (sic_names["nameendt"] >= ts)]
        sic = dict(zip(sn["permno"].astype("int64"), sn["sic2"]))

        sig = _month_signals(cov_m, rets, n_cov, rel,
                             SPEC["min_shared_analysts"], SPEC["min_peers"],
                             sic=sic)
        if sig.empty:
            continue
        j = sig.merge(cur[["permno", "fwd_ret", "own_ret_1m", "dist_high",
                           "ret"]],
                      on="permno", how="inner").dropna(subset=["fwd_ret"])
        # COMPETING BASELINE, no graph at all: the equal-weighted return of
        # every other firm in the same SIC2 this month.
        j["sic2"] = j["permno"].map(sic)
        grp = j.groupby("sic2")["ret"]
        j["sic2_peer"] = ((grp.transform("sum") - j["ret"])
                          / (grp.transform("size") - 1).replace(0, np.nan))
        if len(j) < SPEC["min_firms_per_month"]:
            continue
        n_used += 1
        y = j["fwd_ret"].to_numpy()
        for a in arms:
            if a.endswith("_near_high"):
                base = a[: -len("_near_high")]
                near = j["dist_high"] >= AMENDMENT["near_high_threshold"]
                if near.sum() < 50:
                    continue
                ic = _rank_ic(j.loc[near, base].to_numpy(),
                              j.loc[near, "fwd_ret"].to_numpy())
            else:
                ic = _rank_ic(j[a].to_numpy(), y)
            if ic is not None:
                ics[a].append(ic)
                ic_month[a].append(str(pd.Timestamp(m).date()))

    results = {}
    pvals = {}
    for a, series in ics.items():
        if len(series) < 12:
            results[a] = {"n_months": len(series), "status": "TOO_FEW_MONTHS"}
            continue
        arr = np.array(series)
        mean = float(arr.mean())
        se = float(arr.std(ddof=1) / np.sqrt(len(arr)))
        t = mean / se if se > 0 else 0.0
        p = float(2 * (1 - stats.t.cdf(abs(t), df=len(arr) - 1)))
        # MDE at 80% power for THIS many months, so a null is readable.
        mde = float(2.80 * se)
        results[a] = {"n_months": len(arr), "mean_ic": round(mean, 5),
                      "se": round(se, 5), "t": round(t, 3),
                      "p_two_sided": round(p, 5),
                      "mde_80pct_power": round(mde, 5),
                      "above_economic_bar": bool(mean >= SPEC["economic_bar_ic"])}
        pvals[a] = p

    # The post-hoc arms get their OWN BH-FDR family. Folding them into the
    # primary family would change the primary arms' thresholds after the fact,
    # which is the multiplicity error running backwards.
    primary_p = {k: v for k, v in pvals.items() if k not in post_hoc}
    post_p = {k: v for k, v in pvals.items() if k in post_hoc}
    surv = _bh_fdr(primary_p, 0.10) if primary_p else {}
    surv.update(_bh_fdr(post_p, 0.10) if post_p else {})
    for a in post_hoc:
        if a in results:
            results[a]["post_hoc"] = True
    for a, s in surv.items():
        results[a]["bh_fdr_survives"] = bool(s)

    # PAIRED, because the decision rule is about one arm beating another on the
    # SAME months. Comparing two means with independent SEs would ignore that
    # both arms had the same good and bad months, which is most of their
    # variance -- and would make a difference of 0.00008 look uncertain rather
    # than precisely zero.
    def _paired(a: str, b: str) -> dict | None:
        ma = dict(zip(ic_month[a], ics[a]))
        mb = dict(zip(ic_month[b], ics[b]))
        common = sorted(set(ma) & set(mb))
        if len(common) < 12:
            return None
        d = np.array([ma[m] - mb[m] for m in common])
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        mean = float(d.mean())
        return {"vs": b, "n_months": len(d), "mean_diff": round(mean, 6),
                "se": round(se, 6),
                "t": round(mean / se, 3) if se > 0 else 0.0,
                "beats_by_more_than_1se": bool(mean > se)}

    comparisons = {
        "peer_rel_tilt_vs_peer_eq": _paired("peer_rel_tilt", "peer_eq"),
        "peer_leader_vs_peer_laggard": _paired("peer_leader", "peer_laggard"),
        "peer_eq_vs_own_ret_1m": _paired("peer_eq", "own_ret_1m"),
        "peer_eq_xsic_vs_sic2_peer": _paired("peer_eq_xsic", "sic2_peer"),
        "peer_eq_vs_sic2_peer": _paired("peer_eq", "sic2_peer"),
    }

    graph_arms = [a for a in arms if a != "own_ret_1m" and a not in post_hoc]
    passed = [a for a in graph_arms
              if results.get(a, {}).get("above_economic_bar")
              and results.get(a, {}).get("bh_fdr_survives")]
    verdict = "CONTINUE" if passed else "STOP"

    receipt = {
        "trial_id": SPEC["trial_id"],
        "spec_hash": spec_hash(),
        "amendment_hash": amendment_hash(),
        "amendment_2_hash": amendment_2_hash(),
        "spec": SPEC,
        "amendment": AMENDMENT,
        "amendment_2": AMENDMENT_2,
        "n_months_evaluated": n_used,
        "n_effective": n_used,
        "results": results,
        "paired_comparisons": comparisons,
        "monthly_ic": {a: dict(zip(ic_month[a], [round(x, 6) for x in ics[a]]))
                       for a in arms},
        "arms_passing": passed,
        "verdict": verdict,
        "verdict_meaning": (
            "CONTINUE: at least one graph arm cleared the declared 0.01 bar "
            "AND survived BH-FDR — the graph programme earns its next step. "
            "STOP: it did not, and the GNN is not built."),
        "direction_check": {
            "paired": comparisons.get("peer_leader_vs_peer_laggard"),
            "note": ("positive means information flows from BETTER-COVERED "
                     "firms to less-covered ones, which is the conduit "
                     "reading. Reported, never licensing on its own."),
        },
        "amendment_verdict": (
            "reliability adds nothing here — `peer_rel_tilt` does not beat "
            "`peer_eq` by more than one paired SE, so the cheap arm wins on "
            "parsimony"
            if (comparisons.get("peer_rel_tilt_vs_peer_eq") or {})
            .get("beats_by_more_than_1se") is False
            else "see paired_comparisons"),
    }
    receipt["granularity"] = id_col
    if id_col != "amaskcd":
        receipt["amendment_3"] = AMENDMENT_3
        receipt["amendment_3_hash"] = amendment_3_hash()
    OUT.mkdir(parents=True, exist_ok=True)
    name = ("cocoverage_receipt.json" if id_col == "amaskcd"
            else f"cocoverage_receipt_{id_col}.json")
    (OUT / name).write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    import sys as _sys
    _by = "estimid" if "--by-firm" in _sys.argv else "amaskcd"
    r = run(_by)
    print(json.dumps({k: v for k, v in r.items() if k != "spec"},
                     indent=2, default=str))
