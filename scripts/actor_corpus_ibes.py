"""The first real actor corpus: IBES analyst recommendations, graded.

WHY ANALYSTS FIRST
==================
`actor_intelligence` shipped as an estimator with nothing to estimate from. Of
the actor types it can score, analysts are the only one with a clean,
timestamped, already-on-disk corpus: `ibes__recddet` carries 3.26M
recommendations with an analyst id, a standardised direction, and -- crucially
-- BOTH the announcement timestamp and the timestamp IBES recorded it at. That
is precisely the `public_at` / `observed_at` split the module refuses to work
without.

Commentators (the actual "inverse Cramer" case) come LAST, not first: there is
no clean public feed of timestamped calls, so that is an ingestion problem, not
a statistics one.

WHAT IS GRADED
==============
A recommendation is a directional claim about a company. `ireccd` is IBES's
standardised scale, 1 (strong buy) to 5 (strong sell):

    1, 2  -> +1   3 -> NOT A CLAIM (refused)   4, 5 -> -1

Hold is not a weak buy. Scoring it as one would build a track record out of the
times an analyst declined to make a call, so it is dropped rather than bucketed.

THE THREE PLACES THIS COULD SILENTLY CHEAT, AND WHAT STOPS EACH
===============================================================
1. **Timestamp.** `anndats`+`anntims` is when the recommendation became public.
   A rec announced after the close is not actionable at that close, so the
   position opens at the NEXT session's close strictly after the announcement
   instant. Using `actdats` (when IBES recorded it) would be worse in the other
   direction -- it lags publication -- so both are carried and the gap is
   reported as the disclosure lag rather than assumed to be zero.
2. **The null.** A buy recommendation graded against zero is right whenever the
   market rises. Every claim is graded against the EQUAL-WEIGHTED UNIVERSE over
   the same window, so the question is "did this name beat the market", not
   "did the market go up". Analysts are overwhelmingly bullish; a 0-return null
   would hand the whole profession a free edge.
3. **Survivorship.** A name that delists mid-window has a real outcome. CRSP
   `ret` carries the delisting return where one exists, and a claim whose name
   stops trading is graded on what it did up to that point, not dropped -- a
   corpus that quietly drops its failures measures the survivors.

Usage:
    python -m scripts.actor_corpus_ibes --build
    python -m scripts.actor_corpus_ibes --score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
OUT = REPO / "backend" / "data" / "optimus" / "actor_corpus"

#: Analyst recommendations are conventionally evaluated over a quarter.
HORIZON_TD = 63

#: Only years where the CRSP daily panel is on disk.
FIRST_YEAR, LAST_YEAR = 2013, 2024

#: Floor on the cusip->permno link rate WITHIN the US subset. Measured at 74%
#: on 2026-08-23; a fall below this means the join has broken and the survivors
#: are a selected sample.
MIN_LINK_RATE = 0.60

#: A sector benchmark needs enough names to mean anything. Below this the
#: claim falls back to the whole market and says so on the row.
MIN_SECTOR_NAMES = 10

#: A claim needs a full horizon of forward data to be graded. The last
#: HORIZON_TD sessions therefore carry claims that cannot resolve; they are
#: EXCLUDED and counted, never graded as misses.
DIRECTION = {1: 1, 2: 1, 4: -1, 5: -1}      # 3 (hold) is deliberately absent


def _sic2() -> pd.DataFrame:
    n = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                        columns=["permno", "hsiccd", "namedt", "nameendt"])
    n = n.dropna(subset=["hsiccd"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"])
    n["sic2"] = (n["hsiccd"].astype("int64") // 100).astype("int16")
    return n[["permno", "sic2", "namedt", "nameendt"]]


def _market_and_forward() -> pd.DataFrame:
    """Per (permno, date): forward HORIZON_TD return, and its SECTOR benchmark.

    THE BENCHMARK IS THE WHOLE RESULT. Graded against the equal-weighted
    market, every analyst buy call in this corpus underperforms by 3.67% over
    63 sessions and the three analysts the inverse gate licensed turned out to
    be 37-56% concentrated in one SIC2 (mostly pharma/chemicals). That is not
    analyst skill being measured -- it is sector and size exposure. Analysts
    cover larger, growthier names while an equal-weighted CRSP market is
    dominated by small caps, so the comparison was answering a question nobody
    asked.

    So a claim is graded against its own SIC2 division over the same window.
    An analyst is then credited only for picking names that beat their SECTOR,
    which is the thing a stock recommendation actually asserts.
    """
    frames = []
    for yr in range(FIRST_YEAR - 1, LAST_YEAR + 1):
        p = WRDS / f"crsp_dsf_{yr}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["permno", "date", "ret"])
        frames.append(d)
    if not frames:
        sys.exit("REFUSED: no crsp_dsf_*.parquet on disk")
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d = d.dropna(subset=["ret"])
    d["ret"] = d["ret"].astype("float64")

    d = d.sort_values(["permno", "date"], kind="mergesort")
    d["lr"] = np.log1p(d["ret"].clip(-0.99, None))
    g = d.groupby("permno", sort=False)
    d["cr"] = g["lr"].cumsum()
    d["fwd_cr"] = g["cr"].shift(-HORIZON_TD) - d["cr"]

    # Sector as of each row's own date (a permno's SIC changes over its life).
    sic = _sic2()
    j = d[["permno", "date"]].reset_index(drop=True)
    j["_row"] = np.arange(len(j))
    k = j.merge(sic, on="permno", how="inner")
    k = k[(k["date"] >= k["namedt"]) & (k["date"] <= k["nameendt"])]
    k = k.drop_duplicates("_row")
    d = d.reset_index(drop=True)
    d["sic2"] = np.nan
    d.loc[k["_row"].to_numpy(), "sic2"] = k["sic2"].to_numpy()

    # The benchmark: equal-weighted forward return of the same SIC2 division,
    # over the same window. Sectors with too few names would be a noisy
    # benchmark, so they fall back to the whole market and are FLAGGED.
    grp = d.dropna(subset=["sic2", "fwd_cr"]).groupby(["date", "sic2"])
    bench = grp["fwd_cr"].agg(["mean", "size"]).rename(
        columns={"mean": "sec_fwd", "size": "sec_n"})
    mkt_fwd = d.groupby("date")["fwd_cr"].mean().rename("mkt_fwd")

    d = d.join(bench, on=["date", "sic2"]).join(mkt_fwd, on="date")
    thin = d["sec_n"].fillna(0) < MIN_SECTOR_NAMES
    d["benchmark_kind"] = np.where(thin, "market", "sector")
    d["bench_fwd"] = np.where(thin, d["mkt_fwd"], d["sec_fwd"])
    d["fwd_excess"] = d["fwd_cr"] - d["bench_fwd"]
    return d[["permno", "date", "fwd_excess", "benchmark_kind", "sic2"]]


def _cusip_to_permno() -> pd.DataFrame:
    n = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                        columns=["permno", "ncusip", "namedt", "nameendt"])
    n = n.dropna(subset=["ncusip"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"])
    return n


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    recs = pd.read_parquet(
        WRDS / "bulk" / "ibes__recddet.parquet",
        columns=["cusip", "amaskcd", "estimid", "emaskcd", "ireccd",
                 "anndats", "anntims", "actdats", "usfirm"])
    n_raw = len(recs)

    recs["anndats"] = pd.to_datetime(recs["anndats"])
    recs["actdats"] = pd.to_datetime(recs["actdats"])
    recs = recs[(recs["anndats"].dt.year >= FIRST_YEAR)
                & (recs["anndats"].dt.year <= LAST_YEAR)]
    n_window = len(recs)

    # SCOPE, DECLARED. IBES covers international issuers; CRSP is US-only, so
    # a non-US recommendation cannot link and must not be counted as a link
    # FAILURE. Measured 2026-08-23: usfirm=0 matches CRSP at 0.1% and usfirm=1
    # at 74.0%, and 80% of this window is usfirm=0 -- so an unfiltered merge
    # silently drops four rows in five and reports a 14.6% "link rate" that
    # looks like a broken join and is actually a universe mismatch.
    #
    # This corpus is therefore about US analyst coverage of US common stock.
    # A foreign-coverage corpus is a different study needing a different price
    # panel, not a bug fix.
    n_non_us = int((recs["usfirm"] != 1).sum())
    recs = recs[recs["usfirm"] == 1]
    n_us = len(recs)

    recs["ireccd"] = pd.to_numeric(recs["ireccd"], errors="coerce")
    n_hold = int((recs["ireccd"] == 3).sum())
    recs["direction"] = recs["ireccd"].map(DIRECTION)
    recs = recs.dropna(subset=["direction", "amaskcd", "cusip"])
    recs["direction"] = recs["direction"].astype("int8")
    n_directional = len(recs)

    # cusip -> permno, as of the announcement date.
    link = _cusip_to_permno()
    m = recs.merge(link, left_on="cusip", right_on="ncusip", how="inner")
    m = m[(m["anndats"] >= m["namedt"]) & (m["anndats"] <= m["nameendt"])]
    n_linked = len(m)
    link_rate = n_linked / n_directional if n_directional else 0.0
    # A link rate that quietly falls is how a corpus becomes a corpus about
    # whatever still linked. Refuse rather than report a biased sample.
    if link_rate < MIN_LINK_RATE:
        sys.exit(
            f"REFUSED: only {link_rate:.1%} of US directional recommendations "
            f"linked to a permno (floor {MIN_LINK_RATE:.0%}). Below this the "
            f"corpus is a statement about whichever names still link, not "
            f"about analysts.")

    fwd = _market_and_forward()
    sessions = pd.Index(sorted(fwd["date"].unique()))

    # A rec announced AFTER the close is not actionable at that close. Open at
    # the next session STRICTLY after the announcement instant.
    #
    # AN UNKNOWN TIME IS NOT MIDNIGHT. The first version wrote
    # `.astype(str).fillna("00:00:00")` -- which fills nothing, because
    # `astype(str)` has already turned NaT into the string "NaT" -- and then
    # coerced the unparseable hour to 0. A missing announcement time therefore
    # became 00:00, i.e. PRE-MARKET, i.e. tradable at that same session's open.
    # For any recommendation actually released after that close, the grade was
    # then computed from a price that PRECEDED the information. Unknown times
    # now take the next session, which is the only reading that cannot buy the
    # move it is trying to predict, and the count is reported so the choice is
    # visible rather than assumed to be rare.
    ann = m["anndats"].to_numpy()
    tim = m["anntims"].astype(str)
    hh = pd.to_numeric(tim.str.slice(0, 2), errors="coerce")
    # EXACTLY MIDNIGHT IS A PLACEHOLDER, NOT A TIME. 3,168 US rows in this
    # window carry `00:00:00` while the rest of hour 0 is spread across the
    # minute field (00:16, 00:17, 00:02 ...) exactly as real stamps are, and
    # the midnight share falls monotonically from 5.5% of 2013 to 0.1% of
    # 2024 -- the signature of a legacy default being retired, not of analysts
    # who published at midnight. Read as a time it means pre-market, which
    # would make an unknown-time release tradable at a price that may precede
    # it; read as unknown it costs one session of precision on 1.3% of claims.
    # Only one of those two errors can buy the move it is predicting.
    unknown = hh.isna() | (tim.str.slice(0, 8) == "00:00:00")
    n_unknown_time = int(unknown.sum())
    # 16:00 ET close; anything at or after it — and anything we cannot read —
    # lands on the following session.
    same_day_ok = ((hh < 16) & ~unknown).fillna(False).to_numpy()
    pos = sessions.searchsorted(ann, side="left")
    pos = np.where(same_day_ok, pos, pos + 1)
    ok = pos < len(sessions)
    m = m[ok].copy()
    m["open_date"] = sessions[pos[ok]]
    n_dated = len(m)

    m["permno"] = m["permno"].astype("int64")
    j = m.merge(fwd, left_on=["permno", "open_date"], right_on=["permno", "date"],
                how="left")
    n_unresolvable = int(j["fwd_excess"].isna().sum())
    j = j.dropna(subset=["fwd_excess"])

    j["outcome"] = ((np.sign(j["fwd_excess"]) == j["direction"])
                    .astype("int8"))
    j["public_at"] = j["open_date"].dt.strftime("%Y-%m-%dT00:00:00+00:00")
    j["disclosure_lag_days"] = (j["actdats"] - j["anndats"]).dt.days

    keep = j[["amaskcd", "estimid", "emaskcd", "permno", "direction",
              "outcome", "fwd_excess", "public_at", "anndats",
              "disclosure_lag_days", "benchmark_kind", "sic2"]].copy()
    keep["amaskcd"] = keep["amaskcd"].astype("int64")
    keep.to_parquet(OUT / "ibes_graded.parquet", index=False)

    receipt = {
        "horizon_trading_days": HORIZON_TD,
        "window": [FIRST_YEAR, LAST_YEAR],
        "benchmark": ("equal-weighted SIC2 sector, same window; falls back to "
                      "the whole market where the sector has < "
                      f"{MIN_SECTOR_NAMES} names, flagged per row"),
        "benchmark_rationale": (
            "An EW-market benchmark made every analyst buy call underperform "
            "by 3.67% and licensed three analysts for INVERSE who turned out "
            "to be 37-56% concentrated in one SIC2. That measured sector and "
            "size exposure, not analyst skill."),
        "n_raw_recommendations": n_raw,
        "n_in_window": n_window,
        "n_non_us_dropped": n_non_us,
        "n_us": n_us,
        "scope": ("US analyst coverage of US common stock. IBES covers "
                  "international issuers and CRSP does not, so usfirm=0 is "
                  "EXCLUDED by declaration rather than lost in the join "
                  "(measured: usfirm=0 links at 0.1%, usfirm=1 at 74.0%)."),
        "n_hold_dropped": n_hold,
        "n_directional": n_directional,
        "n_linked_to_permno": n_linked,
        "link_rate_within_us": round(link_rate, 4),
        "link_rate_floor": MIN_LINK_RATE,
        "n_with_open_date": n_dated,
        "n_unknown_announcement_time": n_unknown_time,
        "unknown_time_rule": ("`anntims` unreadable OR exactly 00:00:00 -> "
                              "the NEXT session's open, never the same one. "
                              "Exact midnight is a legacy placeholder (its "
                              "share falls 5.5% of 2013 -> 0.1% of 2024 while "
                              "the rest of hour 0 spreads across the minute "
                              "field like real stamps); read as a time it "
                              "would make an unknown-time release tradable at "
                              "a price that may precede it."),
        "n_unresolvable_no_forward_window": n_unresolvable,
        "n_graded": int(len(keep)),
        "n_analysts": int(keep["amaskcd"].nunique()),
        "hold_note": ("`ireccd == 3` is NOT a weak buy. Scoring it would build "
                      "a record out of declined calls, so it is dropped and "
                      "counted."),
        "unresolvable_note": ("claims in the last 63 sessions have no forward "
                              "window; EXCLUDED, never graded as misses"),
    }
    (OUT / "build_receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


def score() -> None:
    from backend.services import actor_intelligence as AI

    p = OUT / "ibes_graded.parquet"
    if not p.exists():
        sys.exit("REFUSED: corpus not built. Run --build first.")
    g = pd.read_parquet(p)

    # THE NULL IS PER DIRECTION, and then per analyst's own direction MIX.
    # Buy and sell claims do not resolve in their favour at the same rate
    # (measured: 0.567 vs 0.447 against sector). An analyst who only ever says
    # buy must be graded against the buy null, or the entire difference between
    # buy-side and sell-side base rates is credited to them as skill. Every
    # licensed "inverse" in the first pass was a pure-buy analyst, which is
    # exactly the shape this error produces.
    null_by_dir = g.groupby("direction")["outcome"].mean().to_dict()
    overall_null = float(g["outcome"].mean())

    # Split by TIME, not at random: the holdout must be a period the selection
    # never saw. A random split leaks, because one analyst's calls are
    # correlated within a quarter.
    g["year"] = pd.to_datetime(g["anndats"]).dt.year
    cut = 2021
    train = g[g["year"] < cut]
    hold = g[g["year"] >= cut]

    def _claims(frame: pd.DataFrame) -> list[dict]:
        return [{"actor": f"analyst:{a}", "actor_type": "analyst",
                 "public_at": pa, "outcome": int(o), "direction": int(d)}
                for a, pa, o, d in zip(frame["amaskcd"], frame["public_at"],
                                       frame["outcome"], frame["direction"])]

    train_claims, hold_claims = _claims(train), _claims(hold)

    counts = train.groupby("amaskcd").size()
    eligible = counts[counts >= 50].index.tolist()
    print(f"scoring {len(eligible)} analysts with >=50 graded calls "
          f"in {train['year'].min()}-{cut - 1}", flush=True)

    skills, holds = [], []
    for a in eligible:
        actor = f"analyst:{a}"
        # This analyst's own blended null: the direction mix they actually
        # used, weighted by each direction's base rate.
        mix = train[train["amaskcd"] == a]["direction"]
        own_null = float(np.mean([null_by_dir[int(d)] for d in mix]))
        try:
            s = AI.actor_skill(train_claims, actor=actor, null_rate=own_null)
        except AI.ActorEvidenceRefused:
            continue
        s["own_null"] = round(own_null, 4)
        skills.append(s)
        try:
            hmix = hold[hold["amaskcd"] == a]["direction"]
            h_null = (float(np.mean([null_by_dir[int(d)] for d in hmix]))
                      if len(hmix) else own_null)
            h = AI.actor_skill(hold_claims, actor=actor, null_rate=h_null)
            holds.append({"actor": actor, "edge": h["edge"],
                          "n_decision_days": h["n_decision_days"]})
        except AI.ActorEvidenceRefused:
            pass

    lic = AI.inverse_license(skills, holdout=holds)

    # PERSISTENCE IS THE PREMISE, SO IT BELONGS IN THE RECEIPT.
    # `corr(train edge, holdout edge) = 0.516` is the number the entire actor
    # layer rests on -- if a track record does not predict the next call, the
    # statistics around it are decoration. It was computed ad hoc and written
    # into prose, which means it could not be re-checked after any change to
    # the corpus without re-deriving it by hand. It is now an artefact.
    #
    # Fisher-z interval, and the unit is the ANALYST: each analyst contributes
    # one (train, holdout) pair, so the pairs are independent in the way the
    # interval assumes. It is NOT a walk-forward -- one split, one estimate.
    #
    # AND THE WHOLE LADDER, NOT ONE RUNG. The first report of this number was
    # "0.516 over n = 50 analysts" without naming the rule that produced 50 of
    # 222: a minimum of 30 graded claims in the HOLDOUT. Unrestricted the same
    # split gives 0.25. Neither is wrong -- an analyst whose holdout edge rests
    # on 6 calls contributes a very noisy y, and noise in y attenuates r toward
    # zero -- but reporting only the filtered rung leaves the reader unable to
    # tell attenuation from selection. The ladder is monotone in holdout
    # evidence, which is the signature of attenuation; every rung is reported
    # so no single threshold has to be believed.
    #
    # The filter is on holdout PRECISION, never on holdout OUTCOME, so it does
    # not select analysts for having persisted. That distinction is the only
    # thing keeping this from being circular.
    hold_by_actor = {h["actor"]: h for h in holds}
    rows = [(s["edge"], hold_by_actor[s["actor"]]) for s in skills
            if s["actor"] in hold_by_actor]
    hold_claims = {f"analyst:{a}": int(n)
                   for a, n in hold.groupby("amaskcd").size().items()}

    def _corr(pairs: list[tuple[float, float]]) -> dict | None:
        if len(pairs) < 4:
            return None
        xs = np.array([a for a, _ in pairs], dtype=float)
        ys = np.array([b for _, b in pairs], dtype=float)
        if xs.std() == 0 or ys.std() == 0:
            return None
        r = float(np.corrcoef(xs, ys)[0, 1])
        z = np.arctanh(np.clip(r, -0.999999, 0.999999))
        se = 1.0 / np.sqrt(len(pairs) - 3)
        lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
        return {"n_analysts": len(pairs), "corr": round(r, 4),
                "ci95": [round(float(lo), 4), round(float(hi), 4)],
                "holds_above_zero": bool(lo > 0)}

    ladder = {}
    for thr in (0, 10, 20, 30, 40, 50):
        pairs = [(te, h["edge"]) for te, h in rows
                 if hold_claims.get(h["actor"], 0) >= thr]
        got = _corr(pairs)
        if got:
            ladder[f"min_holdout_claims_{thr}"] = got
    persistence = {
        "unit": "analyst — one (train edge, holdout edge) pair each",
        "interval": "Fisher-z",
        "headline": ladder.get("min_holdout_claims_0"),
        "by_min_holdout_claims": ladder,
        "note": ("ONE time split, not a walk-forward. The threshold is on "
                 "holdout PRECISION, never on holdout outcome; r rising with "
                 "it is the signature of attenuation from measurement error "
                 "in y, not of selecting analysts who persisted."),
    }
    print(f"persistence: {persistence}", flush=True)

    ranked = sorted(skills, key=lambda s: s["edge"])
    res = {
        "benchmark": "equal-weighted SIC2 sector over the same window",
        "null_overall": round(overall_null, 4),
        "null_note": ("each analyst is graded against their OWN direction mix, "
                      "not the pooled rate — a pure-buy analyst scored against "
                      "a blended null is credited with the buy/sell base-rate "
                      "gap as if it were skill"),
        "null_by_direction": {str(k): round(v, 4)
                              for k, v in null_by_dir.items()},
        "n_graded_claims": int(len(g)),
        "n_analysts_scored": len(skills),
        "persistence": persistence,
        "train_window": [int(train["year"].min()), cut - 1],
        "holdout_window": [cut, int(g["year"].max())],
        "worst_5": [{k: s[k] for k in
                     ("actor", "edge", "z", "n_decision_days",
                      "shrunk_hit_rate")} for s in ranked[:5]],
        "best_5": [{k: s[k] for k in
                    ("actor", "edge", "z", "n_decision_days",
                     "shrunk_hit_rate")} for s in ranked[-5:]],
        "inverse_license": {
            "n_licensed": len(lic["licensed"]),
            "licensed": lic["licensed"],
            "m_considered": lic["m_considered"],
            "n_refused": len(lic["refused"]),
        },
    }
    (OUT / "score_receipt.json").write_text(json.dumps(res, indent=2,
                                                       default=str))
    print(json.dumps(res, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    if a.score:
        score()
    if not (a.build or a.score):
        ap.error("pass --build and/or --score")


if __name__ == "__main__":
    main()
