"""CHRONOLOGY-AUDIT-1 — does every join assert `observed_at`, not `date`?

Order 24 Phase 0, blocking. The house failure mode is semantic, not
syntactic: correct arithmetic against the wrong world. Three temporal
alignment defects have already been paid for (FRED publication-vs-
reference date, collectors writing zeros, NAV stamped today against
yesterday's close), so the standing findings do not get to be assumed
innocent — each join is measured.

This audit does NOT re-run the trials. It measures the alignment of the
inputs those trials consumed, and reports the SIGN and SIZE of every
lag. A guard that happens to be satisfied is not the same as a guard
that is asserted: several checks below exist to convert "it is fine in
practice" into "it refuses if it ever stops being fine".

    python -m scripts.chronology_audit

Every check prints PASS / FAIL / QUANTIFIED. QUANTIFIED means there is
no bug but there is a hazard whose size the consumer must respect.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
OUT = _config.OPTIMUS_LEDGER_DIR / "audits"
CHECKS: list[dict] = []


def record(name: str, status: str, detail: str, **kw) -> None:
    CHECKS.append({"check": name, "status": status, "detail": detail, **kw})
    print(f"[{status:10s}] {name}: {detail}")


# ── C1: options observed_at vs formation date ──────────────────────────────
def c1_options_lag(years=(2001, 2012)) -> None:
    """The options risk head joins IV at t to realized vol over t+1..t+21.

    That is the CORRECT convention (IV at close of t is known at close of
    t) — but only if opt_date never postdates the formation date. The
    live guard is `lag > 14 -> NaN`, which is ONE-SIDED: a negative lag
    (an option observed AFTER formation) sails straight through it.
    Measure the sign.
    """
    try:
        from scripts.net_ladder_rungs_run import options_monthly
    except Exception as e:                                     # noqa: BLE001
        record("C1_OPTIONS_LAG", "SKIP", f"import failed: {e}")
        return
    opt = options_monthly(years=years)
    # formation date = last trading day of each month in the CRSP panel
    early = pd.read_parquet(PIT / "crsp_pit_monthly_early.parquet",
                            columns=["date"])
    early["date"] = pd.to_datetime(early["date"])
    me = (early.groupby(early["date"].dt.to_period("M"))["date"]
          .max().rename("formation"))
    j = opt.merge(me, left_on="month", right_index=True, how="inner")
    lag = (j["formation"] - pd.to_datetime(j["opt_date"])).dt.days
    neg = int((lag < 0).sum())
    status = "PASS" if neg == 0 else "FAIL"
    record("C1_OPTIONS_LAG", status,
           f"n={len(lag):,} lag(formation-opt_date) days "
           f"min={lag.min()} p50={lag.median()} max={lag.max()} "
           f"NEGATIVE={neg} (negative == option observed after formation "
           f"== lookahead the one-sided `lag>14` guard cannot catch)",
           n=int(len(lag)), lag_min=int(lag.min()), lag_max=int(lag.max()),
           lag_p50=float(lag.median()), n_negative=neg,
           n_beyond_14=int((lag > 14).sum()))


# ── C2: fwd_vol excludes the formation day ─────────────────────────────────
def c2_fwd_vol_exclusivity() -> None:
    """`fwd_vol` at t must be std(ret[t+1..t+21]), never including ret[t].

    Reconstruct the published expression on synthetic data where the
    answer is known, so the check does not depend on WRDS being present.
    """
    rng = np.random.default_rng(20260820)
    n = 300
    ret = pd.Series(rng.normal(size=n))
    fwd_vol = ret[::-1].rolling(21).std(ddof=1)[::-1].shift(-1)
    t = 100
    want = ret.iloc[t + 1:t + 22].std(ddof=1)
    got = fwd_vol.iloc[t]
    ok = np.isclose(want, got)
    # and the contaminated variant it must NOT equal
    contaminated = ret.iloc[t:t + 21].std(ddof=1)
    record("C2_FWD_VOL_EXCLUSIVITY", "PASS" if ok else "FAIL",
           f"fwd_vol[t]={got:.6f} == std(ret[t+1..t+21])={want:.6f} "
           f"(same-day-contaminated variant would be "
           f"{contaminated:.6f}; differs by "
           f"{abs(contaminated - want):.6f})",
           matches_forward=bool(ok),
           differs_from_contaminated=bool(not np.isclose(contaminated,
                                                        want)))


# ── C3: IBES actual-before-announcement hazard ─────────────────────────────
def c3_ibes_actual_gate() -> None:
    """`actual` is stamped on the statpers row but only becomes public at
    anndats_act. Any consumer reading `actual` at statpers is reading the
    future. Quantify how often the two differ, both eras."""
    for tag, f in (("modern", "ibes_consensus_monthly.parquet"),
                   ("early", "ibes_consensus_monthly_early.parquet")):
        p = WRDS / f
        if not p.exists():
            record(f"C3_IBES_ACTUAL_GATE[{tag}]", "SKIP", "file absent")
            continue
        df = pd.read_parquet(p, columns=["statpers", "actual",
                                         "anndats_act"])
        df["statpers"] = pd.to_datetime(df["statpers"], errors="coerce")
        df["anndats_act"] = pd.to_datetime(df["anndats_act"],
                                           errors="coerce")
        has = df["actual"].notna() & df["anndats_act"].notna()
        sub = df[has]
        future = sub["anndats_act"] > sub["statpers"]
        lag = (sub["anndats_act"] - sub["statpers"]).dt.days
        record(f"C3_IBES_ACTUAL_GATE[{tag}]", "QUANTIFIED",
               f"{int(future.sum()):,}/{len(sub):,} "
               f"({100 * future.mean():.1f}%) of rows carrying an `actual` "
               f"have anndats_act AFTER statpers — median "
               f"{lag[future].median():.0f}d, max {lag[future].max():.0f}d "
               f"of lookahead if `actual` is read at statpers. Consumers "
               f"MUST gate on anndats_act <= formation.",
               n_rows_with_actual=int(len(sub)),
               n_future=int(future.sum()),
               pct_future=round(float(100 * future.mean()), 2),
               median_lookahead_days=float(lag[future].median()),
               max_lookahead_days=float(lag[future].max()))


# ── C4: 13F filing lag (fdate must postdate rdate) ─────────────────────────
def c4_13f_filing_lag(years=(1996, 2024)) -> None:
    """Does the 13F substrate carry a public-availability column at all?

    The pull declares `fdate (vintage)` as the PIT knowledge column, and
    the intuition — "fdate is the FILE date, filing happens <=45d after
    quarter end" — is wrong for tr_13f.s34. Both fdate and rdate are
    Thomson VINTAGE quarter-ends: fdate is the vintage the record was
    distributed in, rdate the quarter the holdings refer to. Neither is
    the date the filing hit EDGAR. If fdate is always a quarter-end and
    almost always equals rdate, then there is NO knowledge date in this
    table and manager features must impose the statutory deadline
    (rdate + 45 days) explicitly.
    """
    rows, bad, qe_all, n_files = [], 0, True, 0
    for yr in range(years[0], years[1] + 1):
        p = WRDS / f"tr13f_s34_{yr}.parquet"
        if not p.exists():
            continue
        n_files += 1
        df = pd.read_parquet(p, columns=["fdate", "rdate"])
        df["fdate"] = pd.to_datetime(df["fdate"], errors="coerce")
        df["rdate"] = pd.to_datetime(df["rdate"], errors="coerce")
        qe_all = qe_all and bool(df["fdate"].dt.is_quarter_end.all())
        d = (df["fdate"] - df["rdate"]).dt.days.dropna()
        bad += int((d < 0).sum())
        rows.append(d)
    if not rows:
        record("C4_13F_KNOWLEDGE_DATE", "SKIP", "no 13F files")
        return
    d = pd.concat(rows)
    pct_equal = float(100 * (d == 0).mean())
    # fdate is a usable knowledge date ONLY if it is not merely a
    # quarter-end mirror of rdate
    absent = qe_all and pct_equal > 50.0
    record("C4_13F_KNOWLEDGE_DATE", "FAIL" if absent else "PASS",
           (f"n={len(d):,} rows over {n_files} yearly files. "
            f"fdate==rdate on {pct_equal:.1f}% of rows; every fdate is a "
            f"quarter-end ({qe_all}). fdate is therefore a VINTAGE stamp, "
            f"NOT an SEC filing date — this table carries no public-"
            f"availability column. Treating fdate as the knowledge date "
            f"grants up to the full 45-day statutory filing window of "
            f"lookahead. Manager features must gate on rdate + 45d (or a "
            f"real EDGAR filing date), and MANAGER-* trials are BLOCKED "
            f"until they do."
            if absent else
            f"n={len(d):,} (fdate-rdate) p50={d.median()}d "
            f"negatives={bad}"),
           n=int(len(d)), n_files=n_files, pct_fdate_eq_rdate=pct_equal,
           all_fdate_quarter_end=qe_all, n_negative=bad,
           knowledge_date_present=bool(not absent),
           required_mitigation="gate manager features on rdate + 45 days")


# ── C5: Compustat rdq vs datadate ──────────────────────────────────────────
def c5_compustat_rdq() -> None:
    p = WRDS / "compustat_fundq.parquet"
    if not p.exists():
        record("C5_COMPUSTAT_RDQ", "SKIP", "file absent")
        return
    df = pd.read_parquet(p, columns=["datadate", "rdq"])
    df["datadate"] = pd.to_datetime(df["datadate"], errors="coerce")
    df["rdq"] = pd.to_datetime(df["rdq"], errors="coerce")
    null_rdq = int(df["rdq"].isna().sum())
    d = (df["rdq"] - df["datadate"]).dt.days.dropna()
    record("C5_COMPUSTAT_RDQ", "QUANTIFIED",
           f"n={len(df):,}; rdq NULL on {null_rdq:,} rows "
           f"({100 * null_rdq / len(df):.1f}%) — those have NO honest "
           f"knowledge date and must be dropped, not imputed. "
           f"(rdq-datadate) days p50={d.median():.0f} "
           f"p95={d.quantile(0.95):.0f} max={d.max()}: using datadate as "
           f"the knowledge date buys that much lookahead.",
           n=int(len(df)), n_null_rdq=null_rdq,
           p50_days=float(d.median()), p95_days=float(d.quantile(0.95)),
           max_days=int(d.max()))


# ── C6: finratio public_date is the as-of key ──────────────────────────────
def c6_finratio_asof() -> None:
    for tag, f in (("modern", "finratio_monthly.parquet"),
                   ("early", "finratio_monthly_early.parquet")):
        p = WRDS / f
        if not p.exists():
            record(f"C6_FINRATIO_ASOF[{tag}]", "SKIP", "file absent")
            continue
        cols = pd.read_parquet(p).columns.tolist()
        df = pd.read_parquet(p, columns=[c for c in ("public_date", "adate",
                                                     "qdate") if c in cols])
        pubd = pd.to_datetime(df["public_date"], errors="coerce")
        if "adate" in df.columns:
            ad = pd.to_datetime(df["adate"], errors="coerce")
            d = (pubd - ad).dt.days.dropna()
            det = (f"public_date - adate: p50={d.median():.0f}d "
                   f"min={d.min()} (negative would mean the ratio was "
                   f"'available' before its accounting date)")
            status = "PASS" if (d.min() >= 0) else "FAIL"
        else:
            det = ("only public_date present — that IS the availability "
                   "stamp, as-of lookups on it are correct")
            status = "PASS"
        record(f"C6_FINRATIO_ASOF[{tag}]", status,
               f"n={len(df):,}; {det}", n=int(len(df)))


# ── C7: does the teacher library carry the PIT column it claims? ───────────
def c7_manager_library_pit() -> None:
    """A declared PIT column that is not IN the artifact is not a policy,
    it is a sentence. manager_actions_quarterly_v1's meta says
    "downstream features key on fdate, never rdate" — check whether
    `fdate` survived the build at all."""
    base = _config.OPTIMUS_LEDGER_DIR / "teacher_library"
    pq = base / "manager_actions_quarterly_v1.parquet"
    mp = base / "manager_actions_quarterly_v1.meta.json"
    if not pq.exists():
        record("C7_MANAGER_LIBRARY_PIT", "SKIP", "artifact absent")
        return
    cols = [c.lower() for c in pd.read_parquet(pq).columns]
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    claim = str(meta.get("pit", ""))
    claims_fdate = "fdate" in claim
    has_fdate = "fdate" in cols
    ok = (not claims_fdate) or has_fdate
    record("C7_MANAGER_LIBRARY_PIT", "PASS" if ok else "FAIL",
           (f"meta claims {claim!r} but the artifact's columns are "
            f"{cols} — `fdate` is ABSENT, so no downstream feature can "
            f"key on it. The only time column is `q`, derived from RDATE "
            f"(the described quarter), which the meta explicitly forbids "
            f"as knowledge time. Combined with C4 (fdate is a vintage "
            f"stamp anyway, not a filing date), the teacher library v1 "
            f"has NO honest knowledge date: MANAGER-* trials stay BLOCKED "
            f"until v2 carries rdate + 45d."
            if not ok else f"claim {claim!r} satisfiable; cols={cols}"),
           claimed_pit=claim, artifact_columns=cols,
           fdate_present=has_fdate,
           blocks_trials=["MANAGER-WINNER-HOLDING-1",
                          "MANAGER-ADD-TO-WINNER-1",
                          "MANAGER-DRAWDOWN-BEHAVIOR-1",
                          "MANAGER-CONVICTION-PERSISTENCE-1"])


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    print("CHRONOLOGY-AUDIT-1 — observed_at discipline\n")
    for fn in (c2_fwd_vol_exclusivity, c3_ibes_actual_gate,
               c4_13f_filing_lag, c5_compustat_rdq, c6_finratio_asof,
               c7_manager_library_pit, c1_options_lag):
        try:
            fn()
        except Exception as e:                                 # noqa: BLE001
            record(fn.__name__, "ERROR", f"{type(e).__name__}: {e}")
    OUT.mkdir(parents=True, exist_ok=True)
    fails = [c for c in CHECKS if c["status"] in ("FAIL", "ERROR")]
    receipt = {"audit": "CHRONOLOGY-AUDIT-1",
               "run_at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "n_checks": len(CHECKS), "n_failed": len(fails),
               "verdict": "CLEAN" if not fails else "DEFECTS_FOUND",
               "checks": CHECKS}
    p = OUT / "chronology_audit_2026-08-20.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print(f"\n{len(CHECKS)} checks, {len(fails)} failed -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
