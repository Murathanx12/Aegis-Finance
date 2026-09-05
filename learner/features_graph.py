"""SUPPLY-CHAIN AND PEER MOMENTUM -- what the names AROUND a name did last month.

THE HYPOTHESIS, STATED SO IT CAN LOSE
=====================================
A supplier's customers rallying last month predicts the supplier. The claim is
about INFORMATION DIFFUSION, not about correlation: Cohen & Frazzini (2008)
argue that investors are attention-constrained and do not immediately propagate
news along an economic link they can read about in a 10-K, so the customer's
price move arrives at the supplier with a lag. If that is true, an equal-weight
average of a name's customers' last-month returns has cross-sectional
predictive power for the name's NEXT month, and it has that power OVER AND
ABOVE the name's own momentum -- because if it does not, we have simply
rediscovered that linked firms co-move, which nobody disputes and nobody can
trade.

The falsifier is written into the job: every feature is reported twice, once as
a raw cross-sectional rank IC and once as the t of its coefficient in a monthly
Fama-MacBeth regression that ALSO holds the name's own 12-1 momentum, its size,
its 60-day vol, its own last-month return, and -- the control this particular
family actually needs -- the leave-one-out mean last-month return of its own
SECTOR. Competitors are same-sector by construction (54.9% of the source's edges
are same-sector), so "competitor momentum" without a sector-momentum control is
sector momentum with a graph-shaped name on it. The control belongs in the
regression, not in a sentence after it (`feedback_check_whether_the_noise_is_shared`).

WHERE THE GRAPH COMES FROM, AND WHAT IT IS NOT
==============================================
`../Aegis module/runs/MARKET-GRAPH-1/edge_instances.parquet` -- 10,923 live edge
instances extracted by an LLM pass over 3,457 10-K/10-Q filings and resolved to
CRSP permnos on both ends. It is NOT a purchased supply-chain dataset. It is
small on purpose and it is small in fact:

* 386 distinct permnos (285 filing subjects, 294 counterparties);
* 1,067 filings, 38 quarterly cut dates;
* the resolver placed only 30.6% of raw mentions -- the residue is 69.2%
  "not in CRSP" (Samsung, Sanofi, Foxconn, TSMC: the graph is missing most of
  the world's actual supply chain because most of it is not US-listed);
* and the whole thing lives inside ONE decade of a twenty-six-year panel.

That last point is measured here, not asserted. `build()` reports the real
first and last filing date, the per-year edge count, and the fraction of the
long panel's years that carry any feature at all, so any claim made off this
family is scoped by how much tape it actually had.

`valid_from` IS THE FILING DATE, NOT THE AS-OF DATE
===================================================
The source carries two dates. `filing_date` is when the document became public
(2014-04-24 .. 2024-06-26). `date` is the quarterly cut date at which the
source's own panel considered the edge live, and it runs 1 to 428 days AFTER
the filing -- it is a research convenience, not an information event. A feature
keyed on `date` would be *conservative* (later than knowable) rather than
leaky, but it would also throw away up to fourteen months of legitimately
public information and would import someone else's liveness rule.

So this module keys liveness on `filing_date` and replaces the source's cut-date
rule with one explicit parameter, `max_age_days` (default 730 -- two annual
filing cycles). An edge is live at date `d` when
`filing_date <= d <= filing_date + max_age_days`.

DIRECTION IS READ, NOT ASSUMED
==============================
The source's `direction` column is `out` / `in` / `mutual`, and the joint
distribution with `type` is not decorative:

    competitor  5,537 mutual        supplier   980 in
    customer    3,169 out / 27 in   shared_*    ~900 mutual

`customer/out` means the subject named an outbound customer: the counterparty
buys from the subject. `supplier/in` means the counterparty sells to the
subject. Each oriented edge therefore yields TWO directed relations -- if A's
filing says B is A's customer, then B's suppliers include A -- and building the
reverse is what gives the ~100 permnos that never filed anything any coverage
at all.

187 customer/supplier edges are marked `mutual`, which is un-orientable: the
extraction knows there is a trade relationship and not which way it points.
They are DROPPED from the oriented classes and counted in the receipt, which is
the same 187 the source's own reversed-direction control dropped.

FOUR RELATION CLASSES
=====================
`cust` (the counterparty buys from me) · `supp` (the counterparty sells to me) ·
`comp` (declared competitor) · `assoc` (shared technology / shared end market /
shared regulatory exposure). They are kept apart rather than pooled into one
"linked firms" number because the hypothesis makes DIFFERENT predictions for
them -- diffusion should run from customer to supplier, and competitor momentum
should if anything run the other way as share is taken -- and a pooled feature
whose two halves disagree reads as zero.

WHY THE COUNTERPARTY RETURN IS RAW AND NOT MARKET-EXCESS
========================================================
Every test here is cross-sectional WITHIN a calendar month: a rank IC and a
Fama-MacBeth slope. Subtracting any month-constant from the counterparty
returns -- the market return, the graph universe's mean, anything -- leaves
every rank and every within-month slope exactly where it was. Demeaning would
change the printed feature values and change no number in the receipt, so it is
not done, and this paragraph exists so nobody adds it later believing it fixes
something.

POINT-IN-TIME
=============
A feature row is stamped with `date` = the first calendar day AFTER the return
month closes, and edges are admitted on `filing_date <= month_end`. So the row
dated 2016-04-01 aggregates counterparty returns realised over March 2016 using
edges filed on or before 2016-03-31, and a trade on 2016-03-31 gets FEBRUARY's
row, never March's. The join onto the panel is a BACKWARD `merge_asof` on
`entry_date` with a 40-day tolerance -- backward because a forward join would
hand the panel a month that had not finished, and 40 days because a name whose
graph went dark two months ago must get NaN rather than a stale carry-forward.

A COLUMN THAT IS EMPTY EVERYWHERE IS A COLUMN THAT WAS NEVER BUILT
==================================================================
`build()` refuses on an all-NaN feature and `attach()` returns the MATCH RATE,
because a join that matched 3% of rows and a join that matched 97% produce the
same shaped frame and only one of them is a feature. Here the honest number is
near 3%: 386 names inside a 8,981-name panel, one decade inside twenty-six
years. The receipt says so in the headline rather than in a footnote.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
GRAPH_FEATURES = OUT_DIR / "features_graph.parquet"
GRAPH_RECEIPT = OUT_DIR / "features_graph_receipt.json"

VERSION = "features-graph-1"

#: The extracted market graph. A sibling repo, not this one -- `Aegis module`
#: holds the 2026-07/08 investor-brain runs and is ingested by Optimus, not by
#: Aegis-Finance. The env var exists so a test can point at a fixture without
#: the module inventing a fallback that silently produces an empty graph.
EDGE_SOURCE_ENV = "AEGIS_MARKET_GRAPH_EDGES"
DEFAULT_EDGE_SOURCE = REPO.parent / "Aegis module" / "runs" / "MARKET-GRAPH-1" / "edge_instances.parquet"

#: Columns actually read off the parquet. Column-selective on purpose: the file
#: is small but the machine is not idle, and `route`/`accession`/`lo`/`hi` are
#: provenance for the extraction, not inputs to a feature.
EDGE_COLUMNS = ("subject_permno", "counterparty_permno", "filing_date", "date",
                "type", "direction", "confidence", "same_sector")

#: How long a filing's statement about who trades with whom stays believable.
#: Two annual cycles. The source's own liveness rule kept an instance alive for
#: at most 428 days; this is looser and it is a PARAMETER, printed in every
#: receipt, so a later result can be checked against it instead of inheriting it.
DEFAULT_MAX_AGE_DAYS = 730

#: `type` x `direction` -> (relation from the subject's view,
#:                          relation from the counterparty's view).
#: Read off the data, not assumed: see the module docstring's cross-tab.
_ORIENTED: dict[tuple[str, str], tuple[str, str]] = {
    ("customer", "out"): ("cust", "supp"),   # "B is our customer"  => B buys from A
    ("customer", "in"): ("supp", "cust"),    # "we are B's customer" => A buys from B
    ("supplier", "in"): ("supp", "cust"),    # "B supplies us"      => A buys from B
    ("supplier", "out"): ("cust", "supp"),   # "we supply B"        => B buys from A
}
#: Symmetric types. `mutual` is the only direction they carry.
_SYMMETRIC: dict[str, str] = {
    "competitor": "comp",
    "shared_technology": "assoc",
    "shared_end_market": "assoc",
    "regulatory_exposure": "assoc",
}

RELATIONS: tuple[str, ...] = ("cust", "supp", "comp", "assoc")

#: One family per relation class, because an ablation removes an IDEA and not a
#: column: the equal-weight and confidence-weight versions of the same class are
#: two views of one hypothesis and would protect each other.
FAMILIES: dict[str, tuple[str, ...]] = {
    "customer_momentum": ("graph_cust_mom_1m_ew", "graph_cust_mom_1m_cw"),
    "supplier_momentum": ("graph_supp_mom_1m_ew", "graph_supp_mom_1m_cw"),
    "competitor_momentum": ("graph_comp_mom_1m_ew", "graph_comp_mom_1m_cw"),
    "association_momentum": ("graph_assoc_mom_1m_ew", "graph_assoc_mom_1m_cw"),
    # NOT a momentum feature. Degree is the confound every graph result has to
    # be checked against -- a well-connected name is a big, widely covered name
    # -- so it is tested in the same table rather than argued about afterwards.
    "graph_position": ("graph_log_degree",),
}

FEATURES: tuple[str, ...] = tuple(c for cols in FAMILIES.values() for c in cols)

#: Diagnostics that ride along on the join but are NOT tested. Counts, not
#: signals: they say how many names each average was taken over, which is the
#: difference between a mean of eleven customers and a mean of one.
COUNT_COLUMNS: tuple[str, ...] = tuple(f"graph_n_{r}" for r in RELATIONS)


def family_of(col: str) -> str | None:
    for fam, cols in FAMILIES.items():
        if col in cols:
            return fam
    return None


def edge_source() -> Path:
    override = os.environ.get(EDGE_SOURCE_ENV)
    return Path(override) if override else DEFAULT_EDGE_SOURCE


# -------------------------------------------------------------------- edges

def load_edges(path: Path | None = None) -> pd.DataFrame:
    """The raw edge instances, or a REFUSAL that says where it looked.

    Absence of a local object is not evidence of absence (CLAUDE.md), so the
    message names the exact path, the env override, and the two strings to
    search for, rather than letting the caller conclude the dataset does not
    exist. What it never does is return an empty frame: an empty graph joins
    perfectly, produces all-NaN features, and reports a clean zero.
    """
    p = Path(path) if path is not None else edge_source()
    if not p.exists():
        raise SystemExit(
            f"REFUSED: no market-graph edge file at {p}.\n"
            f"  - override the location with {EDGE_SOURCE_ENV}=<path to edge_instances.parquet>\n"
            "  - the file is produced by the MARKET-GRAPH-1 run in the SIBLING repo\n"
            "    `Aegis module` (see CLAUDE.md, FOUR REPOSITORIES), not by this one\n"
            "  - search for the strings 'edge_instances' and 'MARKET-GRAPH-1' before\n"
            "    concluding it was never built -- it is not tracked by this repo's git\n"
            "This module does NOT fall back to an empty graph: all-NaN features join "
            "silently and read as a clean negative result.")
    df = pd.read_parquet(p, columns=list(EDGE_COLUMNS))
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["date"] = pd.to_datetime(df["date"])
    if df["filing_date"].isna().all():
        raise SystemExit(f"REFUSED: every filing_date in {p} is null; there is no "
                         "point-in-time stamp to key liveness on.")
    return df


def relation_table(edges: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Directed (subject, related, relation, valid_from, weight), both ways.

    One source row becomes up to two rows: A's filing naming B as a customer
    tells us B is a customer of A *and* that A is a supplier of B. The reverse
    half is where the ~100 permnos that never filed anything get any coverage,
    and dropping it would make the feature a property of who files rather than
    of who trades.

    `valid_from` is the FILING date. `weight` is the extraction confidence
    (0.30-1.00), which is the only per-edge weight the source carries -- there
    is no revenue share, no dollar volume, nothing that would make a
    value-weighted version of these features possible. The receipt says that
    rather than letting `_cw` read as an economic weighting.
    """
    e = edges.copy()
    e["type"] = e["type"].astype(str)
    e["direction"] = e["direction"].astype(str)
    rows = []
    counts = {"oriented": 0, "symmetric": 0, "unoriented_dropped": 0, "unmapped": 0}
    for (typ, direc), g in e.groupby(["type", "direction"], sort=True):
        if (typ, direc) in _ORIENTED:
            fwd, rev = _ORIENTED[(typ, direc)]
            counts["oriented"] += len(g)
        elif typ in _SYMMETRIC and direc == "mutual":
            fwd = rev = _SYMMETRIC[typ]
            counts["symmetric"] += len(g)
        elif typ in ("customer", "supplier"):
            # Un-orientable trade edge: the extraction knows there is a
            # relationship and not which way it points. Dropped, counted, never
            # guessed -- a guessed direction is the one error this family cannot
            # detect afterwards.
            counts["unoriented_dropped"] += len(g)
            continue
        else:
            counts["unmapped"] += len(g)
            continue
        for subj, rel_, other in (("subject_permno", fwd, "counterparty_permno"),
                                  ("counterparty_permno", rev, "subject_permno")):
            rows.append(pd.DataFrame({
                "subject": g[subj].to_numpy(),
                "related": g[other].to_numpy(),
                "relation": rel_,
                "valid_from": g["filing_date"].to_numpy(),
                "weight": pd.to_numeric(g["confidence"], errors="coerce").to_numpy(),
                "same_sector": g["same_sector"].to_numpy(),
            }))
    if not rows:
        raise SystemExit("REFUSED: no edge row mapped onto a relation class; the source's "
                         "type/direction vocabulary has changed.")
    rel = pd.concat(rows, ignore_index=True)
    rel = rel[rel["subject"] != rel["related"]]
    rel["weight"] = rel["weight"].fillna(1.0).clip(lower=0.0)
    # Same (pair, relation, filing) asserted by two extractions: keep the
    # strongest. Distinct filings stay distinct rows -- a re-affirmation in a
    # later 10-K is what keeps the edge alive, and collapsing to the first
    # filing would age every long-standing relationship out of the panel.
    rel = (rel.groupby(["subject", "related", "relation", "valid_from"], as_index=False)
              .agg(weight=("weight", "max"), same_sector=("same_sector", "max")))
    counts["directed_rows"] = int(len(rel))
    counts["by_relation"] = {r: int((rel["relation"] == r).sum()) for r in RELATIONS}
    counts["permnos"] = int(pd.concat([rel["subject"], rel["related"]]).nunique())
    return rel, counts


# ------------------------------------------------------------ monthly returns

def monthly_returns(permnos, start_year: int, end_year: int,
                    verbose: bool = True) -> pd.DataFrame:
    """Calendar-month compounded returns for exactly the graph's permnos.

    Column-selective and permno-filtered inside the per-year read, because the
    daily file is ~950k rows a year and the graph needs ~386 names of it. CRSP
    `ret` is already the holding-period return, so compounding it inside the
    month is the whole computation; nothing here touches price levels, so the
    split-basis problem that governs `features_price` does not arise.
    """
    from scripts import tracker_ibes_backtest as tib
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    want = set(int(p) for p in permnos)
    frames = []
    for year in range(start_year, end_year + 1):
        f = tib.WRDS / f"crsp_dsf_{year}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["permno", "date", "ret"])
        d = d[d["permno"].isin(want)]
        if len(d):
            frames.append(d)
    if not frames:
        raise SystemExit(f"REFUSED: no CRSP daily files for {start_year}-{end_year}; "
                         "the counterparty return leg cannot be built.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    px["ret"] = pd.to_numeric(px["ret"], errors="coerce")
    px = px[px["ret"].notna()]
    px["month"] = px["date"].dt.to_period("M")
    g = px.groupby(["permno", "month"], sort=False)["ret"]
    mret = g.apply(lambda s: float(np.prod(1.0 + s.to_numpy()) - 1.0)).rename("mret")
    ndays = g.size().rename("ndays")
    out = pd.concat([mret, ndays], axis=1).reset_index()
    # A month with three trading days of data is a delisting stub, not a month.
    # Kept but flagged, so the receipt can say how many averages leaned on one.
    out["thin_month"] = out["ndays"] < 10
    log(f"  monthly returns: {len(out):,} permno-months over "
        f"{out['permno'].nunique()} permnos")
    return out


# ------------------------------------------------------------------- build

def _month_end(period: pd.Period) -> pd.Timestamp:
    return period.to_timestamp(how="end").normalize()


def build(max_age_days: int = DEFAULT_MAX_AGE_DAYS, edges_path: Path | None = None,
          verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, date) with the neighbourhood-return columns.

    `date` is the first calendar day AFTER the aggregated return month, so the
    row is knowable at `date` and a backward join can never hand the panel a
    month that has not finished.
    """
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    edges = load_edges(edges_path)
    rel, rel_counts = relation_table(edges)
    log(f"  edges {len(edges):,} -> directed relations {len(rel):,} "
        f"({rel_counts['unoriented_dropped']} un-orientable dropped)")

    permnos = pd.concat([rel["subject"], rel["related"]]).unique()
    first_filing = pd.Timestamp(rel["valid_from"].min())
    last_filing = pd.Timestamp(rel["valid_from"].max())
    # The return leg starts in the filing month itself (the first feature row is
    # the month AFTER the first filing) and runs to the last month a live edge
    # can reach, capped at the last year of tape on disk.
    ret_start = int(first_filing.year)
    ret_end = min(int((last_filing + pd.Timedelta(days=max_age_days)).year), 2024)
    mret = monthly_returns(permnos, ret_start, ret_end, verbose=verbose)
    mret_by_month = {m: g.set_index("permno")[["mret", "thin_month"]]
                     for m, g in mret.groupby("month", sort=True)}

    months = sorted(mret_by_month)
    out_frames = []
    for m in months:
        d_eff = _month_end(m)                      # edges must be filed by here
        if d_eff < first_filing:
            continue
        live = rel[(rel["valid_from"] <= d_eff)
                   & (rel["valid_from"] >= d_eff - pd.Timedelta(days=max_age_days))]
        if live.empty:
            continue
        # One row per (subject, related, relation): several filings may assert
        # the same live relationship, and an edge re-affirmed three times is not
        # three customers.
        live = (live.groupby(["subject", "related", "relation"], as_index=False)
                    .agg(weight=("weight", "max")))
        r = mret_by_month[m]
        live = live.join(r, on="related")
        live = live[live["mret"].notna()]
        if live.empty:
            continue
        live["_wx"] = live["weight"] * live["mret"]
        agg = (live.groupby(["subject", "relation"], as_index=False)
                   .agg(ew=("mret", "mean"), wx=("_wx", "sum"),
                        w=("weight", "sum"), n=("related", "size")))
        agg["cw"] = agg["wx"] / agg["w"].where(agg["w"] > 0)
        wide = agg.pivot(index="subject", columns="relation",
                         values=["ew", "cw", "n"])
        frame = pd.DataFrame(index=wide.index)
        for rname in RELATIONS:
            for kind in ("ew", "cw"):
                col = f"graph_{rname}_mom_1m_{kind}"
                frame[col] = wide[kind][rname] if (kind, rname) in wide.columns else np.nan
            ncol = f"graph_n_{rname}"
            frame[ncol] = (wide["n"][rname] if ("n", rname) in wide.columns
                           else np.nan)
        deg = live.groupby("subject")["related"].nunique()
        frame["graph_log_degree"] = np.log1p(deg.reindex(frame.index).astype("float64"))
        frame = frame.reset_index().rename(columns={"subject": "permno"})
        frame["feature_month"] = str(m)
        frame["date"] = d_eff + pd.Timedelta(days=1)
        out_frames.append(frame)

    if not out_frames:
        raise SystemExit("REFUSED: no month produced a single live edge with a matched "
                         "counterparty return. The graph and the price tape do not "
                         "overlap; there is no feature here to test.")
    out = pd.concat(out_frames, ignore_index=True)
    for c in (*FEATURES, *COUNT_COLUMNS):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out[["permno", "date", "feature_month", *FEATURES, *COUNT_COLUMNS]]
    out = out.sort_values(["permno", "date"]).reset_index(drop=True)

    cov = {c: round(float(out[c].notna().mean()), 4) for c in FEATURES}
    empty = [c for c, v in cov.items() if v == 0.0]
    if empty:
        raise SystemExit(
            f"REFUSED: {empty} are NaN on every one of {len(out):,} rows. A column that is "
            "empty everywhere is a column that was never built, and joining it to the panel "
            "would add a feature the model silently ignores.")

    by_year = (out.assign(_y=out["date"].dt.year)
                  .groupby("_y")
                  .agg(rows=("permno", "size"), permnos=("permno", "nunique"))
                  .reset_index().rename(columns={"_y": "year"}))
    edge_year = (edges.assign(_y=pd.to_datetime(edges["filing_date"]).dt.year)
                      .groupby("_y").size())

    receipt = {
        "version": VERSION,
        # THE FILE THAT WAS ACTUALLY READ, not the module default.
        #
        # This line used to be `str(edge_source())`, which ignores the
        # `edges_path` argument entirely. On 2026-09-06 `w4_companyworld_rerun`
        # ran three arms over three different edge files and all three receipts
        # named `../Aegis module/runs/MARKET-GRAPH-1/edge_instances.parquet` --
        # including the arm whose 2,020 rows came from `companyworld_v1.parquet`
        # and the pooled arm whose 12,943 rows came from neither file alone.
        # Only `source_rows` disagreed, and a reader who trusted the path would
        # have attributed a never-seen-tape result to the tape it was testing
        # against. Outcome provenance is a standing rule; a receipt that names
        # the wrong file is worse than one that names none.
        "source": str(Path(edges_path) if edges_path is not None else edge_source()),
        "source_is_the_module_default": bool(edges_path is None),
        "source_rows": int(len(edges)),
        "licence": "PRODUCT_EXPERIMENT",
        # --- the coverage window, MEASURED. The roadmap said "reportedly
        # 2015-2024"; these are the numbers that either confirm it or do not.
        "coverage": {
            "filing_date_first": str(first_filing.date()),
            "filing_date_last": str(last_filing.date()),
            "source_as_of_date_first": str(pd.Timestamp(edges["date"].min()).date()),
            "source_as_of_date_last": str(pd.Timestamp(edges["date"].max()).date()),
            "as_of_minus_filing_days": {
                "min": int((edges["date"] - edges["filing_date"]).dt.days.min()),
                "median": float((edges["date"] - edges["filing_date"]).dt.days.median()),
                "max": int((edges["date"] - edges["filing_date"]).dt.days.max()),
            },
            "feature_date_first": str(out["date"].min().date()),
            "feature_date_last": str(out["date"].max().date()),
            "feature_months": int(out["feature_month"].nunique()),
            "feature_years": int(out["date"].dt.year.nunique()),
            "long_panel_years": 26,
            "edges_by_filing_year": {int(k): int(v) for k, v in edge_year.items()},
            "rows_by_year": by_year.to_dict("records"),
        },
        "max_age_days": max_age_days,
        "liveness_rule": ("filing_date <= month_end <= filing_date + max_age_days; the "
                          "source's own as-of `date` column is NOT used, because it runs "
                          "1-428 days after the filing and is a research cut date rather "
                          "than an information event"),
        "relations": rel_counts,
        "rows": int(len(out)),
        "permnos": int(out["permno"].nunique()),
        "families": {k: list(v) for k, v in FAMILIES.items()},
        "non_null_rate": cov,
        "median_neighbours": {c: (float(out[c].median()) if out[c].notna().any() else None)
                              for c in COUNT_COLUMNS},
        "weight_note": ("`_cw` weights by EXTRACTION CONFIDENCE (0.30-1.00), the only "
                        "per-edge weight the source carries. There is no revenue share and "
                        "no traded volume on these edges, so a value-weighted customer "
                        "average is not available and `_cw` must not be read as one."),
        "demean_note": ("counterparty returns are RAW. Every test is cross-sectional within "
                        "a month, so subtracting any month-constant leaves every rank and "
                        "every within-month slope unchanged."),
        "pit_note": ("a row dated d aggregates the returns of the month ending d-1, over "
                     "edges whose FILING date is <= d-1; a trade on the last day of a month "
                     "receives the previous month's row"),
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log(f"  feature rows {len(out):,} over {out['permno'].nunique()} permnos, "
        f"{receipt['coverage']['feature_date_first']}..{receipt['coverage']['feature_date_last']} "
        f"({receipt['coverage']['feature_years']} of 26 panel years)")
    log("  coverage: " + ", ".join(f"{c} {v:.3f}" for c, v in cov.items()))
    return out, receipt


def save(df: pd.DataFrame, receipt: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(GRAPH_FEATURES, index=False)
    GRAPH_RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")


def load() -> pd.DataFrame:
    if not GRAPH_FEATURES.exists():
        raise SystemExit(f"REFUSED: {GRAPH_FEATURES} does not exist. Build it: "
                         "python -m learner.features_graph --build")
    return pd.read_parquet(GRAPH_FEATURES)


def available() -> bool:
    return GRAPH_FEATURES.exists()


def receipt() -> dict:
    if not GRAPH_RECEIPT.exists():
        return {}
    return json.loads(GRAPH_RECEIPT.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- attach

def attach(panel: pd.DataFrame, feats: pd.DataFrame | None = None,
           tolerance_days: int = 40) -> tuple[pd.DataFrame, dict]:
    """BACKWARD merge_asof onto `entry_date` -- the date the money moved.

    Backward, not nearest: a forward join would hand the panel a month that had
    not finished. Tolerance is 40 days, one month plus slack, so a name whose
    graph went dark gets NaN instead of a neighbourhood return carried forward
    from a quarter ago.

    The note reports the MATCH RATE for every column AND the two numbers that
    explain it -- how much of the panel is inside the graph's date window, and
    how much of it is on a permno the graph has ever heard of. A 3% match rate
    that is 3% because the graph covers 386 of 8,981 names is a different fact
    from a 3% match rate caused by a broken key, and the shaped frame looks
    identical either way.
    """
    if feats is None:
        feats = load()
    p = panel.copy()
    p["entry_date"] = pd.to_datetime(p["entry_date"])
    f = feats.copy()
    f["date"] = pd.to_datetime(f["date"])
    cols = [c for c in (*FEATURES, *COUNT_COLUMNS) if c in f.columns]
    f = f[["permno", "date", *cols]]
    before = len(p)
    in_window = float(((p["entry_date"] >= f["date"].min())
                       & (p["entry_date"] <= f["date"].max() + pd.Timedelta(days=tolerance_days))
                       ).mean())
    on_graph = float(p["permno"].isin(set(f["permno"].unique())).mean())
    p = p.sort_values("entry_date")
    f = f.sort_values("date")
    p = pd.merge_asof(p, f, left_on="entry_date", right_on="date", by="permno",
                      direction="backward", tolerance=pd.Timedelta(days=tolerance_days),
                      suffixes=("", "_gfeat"))
    rates = {c: round(float(p[c].notna().mean()), 4) for c in cols}
    feat_rates = {c: v for c, v in rates.items() if c in FEATURES}
    best = max(feat_rates.values()) if feat_rates else 0.0
    note = {
        "rows_in": before, "rows_out": int(len(p)),
        "match_rate": rates,
        "tolerance_days": tolerance_days,
        "direction": "backward (a forward join would use a month that had not finished)",
        "panel_share_inside_the_graph_date_window": round(in_window, 4),
        "panel_share_on_a_permno_the_graph_covers": round(on_graph, 4),
        "ceiling": round(min(in_window, on_graph), 4),
        "why_the_ceiling": ("the product of a ONE-DECADE date window and a 386-name "
                            "universe inside an 8,981-name panel; the match rate is not "
                            "a join defect and must not be repaired by widening the "
                            "tolerance"),
    }
    note["verdict"] = ("JOINED" if best > 0.5 else
                       f"THIN -- best feature column matches {best:.2%} of panel rows")
    return p.drop(columns=[c for c in p.columns if c.endswith("_gfeat")]), note


# ---------------------------------------------------------------------- job

#: A feature needs this many usable (row, month) observations before its t is
#: reported as a result rather than as CANNOT DETERMINE. Lower than W6's 5,000
#: because the graph is one decade of 386 names by construction -- but the
#: number is stated, and a feature under it is refused, not shaded.
MIN_ROWS = 3000
MIN_MONTHS = 24
MIN_NAMES_PER_MONTH = 30


def _fm_month(g: pd.DataFrame, feat: str, ret: str, controls: list[str]) -> float | None:
    """One month's Fama-MacBeth slope on the feature, controls in the SAME fit.

    Ranks, not levels: a 26-year panel spans two orders of magnitude of cap and
    vol, and a level regression would let one cross-section set the slope for
    all of them. Mirrors `weekend_lab_jobs._residualise`.
    """
    X = np.column_stack([np.ones(len(g))] + [
        g[c].rank(pct=True).to_numpy() for c in [feat, *controls]])
    y = g[ret].to_numpy(dtype="float64")
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return float(coef[1])


def _t(s: pd.Series) -> float | None:
    s = pd.Series(s).dropna()
    if len(s) < 3 or not s.std(ddof=1):
        return None
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))


def _sector_momentum(panel: pd.DataFrame) -> pd.Series:
    """Leave-one-out mean of `ret_1m` inside (month, sector).

    THE control this family needs. 54.9% of the source's edges are same-sector
    and every `comp` edge is a same-sector edge by construction, so competitor
    momentum without this is sector momentum wearing a graph's name. Leave-one-
    out because including the name's own return would put the dependent
    variable's own lag on both sides of the comparison.
    """
    if "ret_1m" not in panel.columns or "sector" not in panel.columns:
        return pd.Series(np.nan, index=panel.index)
    r = pd.to_numeric(panel["ret_1m"], errors="coerce")
    key = [panel["month"].astype(str), panel["sector"].astype(str)]
    grp = r.groupby(key)
    tot = grp.transform("sum")
    cnt = grp.transform("count")
    return (tot - r.fillna(0.0)) / (cnt - r.notna().astype(int)).replace(0, np.nan)


def job(variant: int = 0) -> dict:
    """W4 -- does a name's neighbourhood's last month predict its next one?

    Variant 0 is the primary: `excess_vw_1m` against momentum / size / vol.
    Variant 1 swaps in the STRICTER control set (own last-month return and
    leave-one-out sector momentum on top), which is the regression that decides
    whether "supply-chain momentum" is anything other than sector momentum.
    Variant 2 asks the same question of the 3-month horizon, because diffusion
    that takes a quarter is still diffusion and a 1-month test would miss it.
    """
    from learner import inference, long_panel as LP  # noqa: F401
    from scripts.weekend_lab_jobs import era_sign_table  # ONE definition of the era rule

    if not available():
        return {"verdict": "DEFERRED", "job_planned": "W4_graph_momentum",
                "headline": ("features_graph.parquet not built yet "
                             "(python -m learner.features_graph --build)")}
    rec = receipt()
    feats = load()
    df = LP.load_long()
    df, join_note = attach(df, feats)

    ret = "excess_vw_3m" if variant == 2 else "excess_vw_1m"
    base = ["mom_12_1", "log_market_cap", "vol_60d"]
    if variant == 1:
        df["_sector_mom_1m"] = _sector_momentum(df)
        base = base + ["ret_1m", "_sector_mom_1m"]
    have = [c for c in base if c in df.columns]
    control_label = ("momentum/size/vol" if variant != 1
                     else "momentum/size/vol + own 1m return + leave-one-out sector 1m")

    rows, kept = [], {}
    for feat in FEATURES:
        d = df[["month", feat, ret, *have]].dropna()
        if len(d) < MIN_ROWS:
            rows.append({"feature": feat, "family": family_of(feat),
                         "verdict": "CANNOT DETERMINE", "rows": int(len(d)),
                         "why": f"fewer than {MIN_ROWS:,} usable rows"})
            continue
        ics, betas, months, names = [], [], [], []
        for m, g in d.groupby("month", sort=True):
            if len(g) < MIN_NAMES_PER_MONTH:
                continue
            ics.append(float(g[feat].rank().corr(g[ret].rank())))
            betas.append(_fm_month(g, feat, ret, have))
            months.append(str(m))
            names.append(int(len(g)))
        if len(ics) < MIN_MONTHS:
            rows.append({"feature": feat, "family": family_of(feat),
                         "verdict": "CANNOT DETERMINE", "rows": int(len(d)),
                         "months": len(ics),
                         "why": f"fewer than {MIN_MONTHS} months with "
                                f"{MIN_NAMES_PER_MONTH}+ names"})
            continue
        ic = pd.Series(ics, index=months)
        be = pd.Series([b for b in betas], index=months, dtype="float64")
        kept[feat] = be
        rows.append({
            "feature": feat, "family": family_of(feat),
            "rows": int(len(d)), "months": int(len(ic)),
            "median_names_per_month": int(np.median(names)),
            "mean_rank_ic": round(float(ic.mean()), 5),
            "t_rank_ic": (round(_t(ic), 3) if _t(ic) is not None else None),
            "mean_fm_beta_controlled": round(float(be.mean(skipna=True)), 6),
            "t_fm_beta_controlled": (round(_t(be), 3) if _t(be) is not None else None),
            "controls": have,
            "era_sign_table": era_sign_table(be),
            "power": inference.power_note(be.dropna().tolist()),
        })

    tested = [r for r in rows if r.get("t_fm_beta_controlled") is not None]
    # SAME sign, not positive sign: a reliably negative feature is a signal
    # traded the other way round (weekend_lab_jobs.era_sign_table's own lesson).
    survivors = [r for r in tested
                 if abs(r["t_fm_beta_controlled"]) >= 2.0
                 and (r.get("era_sign_table") or {}).get("same_sign_in_2_of_3")]
    killed = [r["feature"] for r in tested
              if r.get("t_rank_ic") is not None
              and abs(r["t_rank_ic"]) >= 3.0 and abs(r["t_fm_beta_controlled"]) < 2.0]
    underpowered = [r["feature"] for r in tested
                    if (r.get("power") or {}).get("powered") is False]
    refused = [r["feature"] for r in rows if r.get("verdict") == "CANNOT DETERMINE"]

    if not tested:
        verdict = "CANNOT DETERMINE (coverage)"
    elif survivors:
        verdict = "NOVEL"
    elif len(underpowered) == len(tested):
        verdict = "CANNOT DETERMINE (underpowered)"
    else:
        verdict = "NOISE"

    cov = (rec.get("coverage") or {})
    scope = (f"{cov.get('feature_years')} of {cov.get('long_panel_years')} panel years "
             f"({cov.get('feature_date_first')}..{cov.get('feature_date_last')}), "
             f"{rec.get('permnos')} of {df['permno'].nunique():,} panel names")
    return {
        "question": ("does a name's customers'/suppliers'/competitors' last month predict "
                     "its next one, once its own momentum, size and vol are in the same "
                     "regression?"),
        "family_id": "weekend-W4-graph-momentum",
        "licence": "PRODUCT_EXPERIMENT",
        "target": ret,
        "control_set": control_label,
        "scope": scope,
        "graph_receipt": {k: rec.get(k) for k in
                          ("source", "source_rows", "max_age_days", "relations", "coverage")},
        "join": join_note,
        "features": rows,
        "n_features_tested": len(tested),
        "n_features_refused_for_coverage": len(refused),
        "survivors_controlled_t2_and_same_sign_2of3_eras": [
            {"feature": r["feature"], "t": r["t_fm_beta_controlled"],
             "sign": (r.get("era_sign_table") or {}).get("dominant_sign")}
            for r in survivors],
        "killed_by_the_controls": killed,
        "killed_note": ("these cleared |t| >= 3 on the RAW rank IC and fall below |t| = 2 "
                        "once the controls are in the same monthly regression. They are "
                        "not features; they are the controls wearing a graph's name."),
        "multiplicity_note": (f"{len(tested)} features were tested; a |t| >= 2 bar on "
                              f"{len(tested)} tests expects {0.05 * max(len(tested), 0):.1f} "
                              "false positives, so the era requirement is doing the work a "
                              "Holm correction would"),
        "scope_note": ("the cross-section of every monthly regression here is the GRAPH "
                       "universe, not the panel: a name with no live edge has a NaN feature "
                       "and drops out. These are large, widely covered US filers, and the "
                       "verdict is scoped to them."),
        "headline": (f"{len(tested)} graph features on {scope}; "
                     f"{len(survivors)} clear |t| >= 2 WITH controls and keep one sign in 2 "
                     f"of 3 eras: "
                     f"{[(r['feature'], r['t_fm_beta_controlled']) for r in survivors] or 'none'}"
                     f"; killed by the controls: {killed or 'none'}; "
                     f"refused for coverage: {refused or 'none'}"),
        "verdict": verdict,
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="supply-chain and peer momentum features")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--job", action="store_true", help="run the W4 evaluation and print it")
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    ap.add_argument("--edges", type=str, default=None)
    a = ap.parse_args(argv)
    if a.build:
        df, rec = build(max_age_days=a.max_age_days,
                        edges_path=Path(a.edges) if a.edges else None)
        save(df, rec)
        print(f"WROTE {GRAPH_FEATURES} ({len(df):,} rows)")
        return 0
    if a.job:
        print(json.dumps(job(a.variant), indent=1, default=str))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
