"""Rolling live cohorts of the branching population (CH-16 / M3, 2026-11-14).

WHY THIS EXISTS
===============
`branch_population_runtime.consume_batch` freezes each declared policy ONCE
EVER (`if pid in by_policy: continue`). The 886 books of 2026-10-15 therefore
share one entry date: n = 1 at the declared unit, and no new book has been
born since. The owner's decision (2026-11-14): make the population live --
keep collecting data points so backtests can run on what was collected.

What changes, and what does not:

* A BOOK stays immutable. Its entry record is written once (exclusive create)
  and never edited: that is what makes it evidence.
* The POPULATION becomes live. The same declared specs are re-entered as a NEW
  dated cohort every `ROLLING_COHORT_CADENCE_SESSIONS` sessions, so cohorts
  overlap and each spec accumulates many independent entry dates instead of
  one. Weak specs stopping re-entry is CH-16 proper, not this module.
* Controls are honest: SPY at the SAME invested share (not cash) and N random
  same-liquidity-band portfolios per DISTINCT holding set, with derived seeds.
* Every mark is one row of one append-only table (`marks/part-<run>.parquet`),
  which a backtest can read later.

THE TWO CLOCKS OF A COHORT (declared in the strategy contract)
==============================================================
For cohort date D (a closed XNYS session) the book enters at the OPEN of the
first session E after D.

* `available_before_utc` = E at 00:00 UTC -- the information cutoff. Every
  input row must be dated strictly before it: bars dated <= D, revisions with
  `event_date < D` (revision_flow's strict rule) AND `first_seen_utc` before
  the cutoff, news with `cached_utc`/`first_seen`/`published` before it. This
  is before any E opening bell, so nothing acted on was not yet public.
* `decision_utc` = D at 21:00 UTC (at or after the US close in both DST
  regimes) -- the reference clock for each spec's `max_age_days` freshness.

The forward step and the backfill use the SAME two clocks, so a backfilled
cohort is what the forward step would have built from the rows still on disk.
A backfilled row is flagged `backfilled: true`: never forward evidence, usable
as backtest data.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.portfolio_intelligence.branch_population import digest, semantic, targets

SPECS_SCHEMA = "rolling_population_specs/2"
COHORT_SCHEMA = "rolling_cohort/1"
MARK_SCHEMA = "rolling_cohort_mark/1"
V1_RUNNABLE = ("news_only", "revision_flow", "net_raises", "hybrid_news_revision")
BAR_FAMILIES = ("low_risk", "momentum_12_1")
TASK_NAME = "AegisRollingCohorts"
BENCH = "SPY"
#: Paths under `--data-root` (the optimus ledger dir). Read only.
BARS_REL = "prices_2025_26/bars.parquet"
REVISIONS_REL = "analyst/target_revisions.parquet"
NEWS_REL = "news_corpus/_digest_cache/extract_wd_v1.jsonl"


class RollingCohortRefused(RuntimeError):
    """A cohort could not be born or marked honestly: refused, never guessed.

    Raised on a missing input file, a spec manifest that changed after birth,
    an input frame that cannot say it is point in time, or a cohort ledger that
    is torn. The CLI turns it into a non-zero exit.
    """


REPO = Path(__file__).resolve().parents[3]
CONTRACT_REL = "docs/TRIALS/TRIAL-ROLLING-COHORTS-20261114.md"
#: Health/operations knobs: changing these does not change how a book is graded.
_OPERATIONAL_KEYS = frozenset({"ROLLING_COHORT_LOCK_WAIT_S", "ROLLING_COHORT_PRICE_GRACE_H",
                               "ROLLING_COHORT_STALE_CADENCES"})


# ──────────────────────── grading config and versions ───────────────────────

def _sha_lf(path: Path) -> Optional[str]:
    p = Path(path)
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if p.is_file() else None


def config_snapshot() -> dict:
    """Everything that decides how a book is built and graded, JSON-normalised.

    Bound into `declaration.json` at the first run; a later run whose snapshot
    differs is refused with the differing keys named (born books must keep
    being graded under the rules they were born under)."""
    from backend.services import xs_ranker as XR
    snap: dict = {k: getattr(_config, k) for k in sorted(dir(_config))
                  if k.startswith("ROLLING_COHORT_") and k not in _OPERATIONAL_KEYS}
    snap["xs_ranker.COST_BPS_BY_BAND"] = dict(XR.COST_BPS_BY_BAND)
    snap["xs_ranker.MIN_PRICE"] = XR.MIN_PRICE
    snap["contract_sha256_lf"] = _sha_lf(REPO / CONTRACT_REL)
    return json.loads(json.dumps(snap, sort_keys=True, default=list))


def check_costs(snap: dict) -> bool:
    """Refuse any cost <= 0 unless the zero-cost diagnostic is declared. Returns the flag."""
    diag = bool(snap.get("ROLLING_COHORT_ZERO_COST_DIAGNOSTIC"))
    bad = [f"band {k}={v}" for k, v in snap["xs_ranker.COST_BPS_BY_BAND"].items() if not v > 0]
    for k in ("ROLLING_COHORT_SPY_COST_BPS", "ROLLING_COHORT_SHORT_BORROW_BPS_YR"):
        if not snap[k] > 0:
            bad.append(f"{k}={snap[k]}")
    if bad and not diag:
        raise RollingCohortRefused(f"a cost <= 0 is refused ({', '.join(bad)}); set "
                                   f"ROLLING_COHORT_ZERO_COST_DIAGNOSTIC=True for a diagnostic run, "
                                   f"and every row will say so")
    return diag


_CODE_VERSION: dict = {}


def code_version() -> Optional[str]:
    """`git rev-parse HEAD` of the checkout this module runs from; None when unknowable."""
    if "v" not in _CODE_VERSION:
        import subprocess
        try:
            r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                               text=True, timeout=5)
            _CODE_VERSION["v"] = r.stdout.strip() if r.returncode == 0 and len(r.stdout.strip()) == 40 else None
        except (OSError, subprocess.SubprocessError):
            _CODE_VERSION["v"] = None
    return _CODE_VERSION["v"]


# ─────────────────────────────── specs (v2) ─────────────────────────────────

def rolling_semantic(spec: dict) -> dict:
    """The identity of a spec: v1 families keep v1's `semantic()` exactly."""
    if spec["family"] in BAR_FAMILIES:
        return {k: spec[k] for k in ("family", "mechanism", "hedge", "horizon_sessions",
                                     "liquidity_segment", "construction", "max_names",
                                     "control_role", "gross_target", "name_cap")}
    return semantic(spec)


def compile_specs(v1: dict) -> dict:
    """Spec file v2: the runnable v1 specs (same ids) plus two bar-only families.

    Dropped from v1, with the reason recorded: the three `no_news_control` cash
    books (cash measures market exposure, not news -- replaced by the SPY
    same-share and random same-band controls) and the four research-only
    families that never had an input adapter.
    """
    specs: list[dict] = []
    excluded: list[dict] = []
    for s in v1["specifications"]:
        if s["family"] not in V1_RUNNABLE:
            why = ("cash control replaced by SPY-at-same-share and random same-band controls"
                   if s["family"] == "no_news_control" else "research spec: no dated input adapter")
            excluded.append({"policy_id": s["policy_id"], "family": s["family"], "reason": why})
            continue
        key = digest(semantic(s))
        if key != s["semantic_sha256"] or key[:24] != s["policy_id"]:
            raise RollingCohortRefused(f"v1 spec {s['policy_id']} no longer hashes to its id")
        row = {k: v for k, v in s.items() if k not in ("state", "activation", "record_start")}
        row.update(spec_source="POPULATION-1000-SPECIFICATIONS.json", state="DECLARED_ROLLING")
        specs.append(row)
    for family, mechanisms, hedges in (("low_risk", ("low_vol_63", "low_beta_252"), ("none",)),
                                       ("momentum_12_1", ("mom_12_1",), ("spy_beta", "none"))):
        for mech, hedge, horizon, liq, cons, names in itertools.product(
                mechanisms, hedges, (21, 63, 126), ("liquid", "broad"),
                ("equal", "volatility_aware"), (10, 20, 40)):
            row = dict(family=family, mechanism=mech, hedge=hedge, horizon_sessions=horizon,
                       liquidity_segment=liq, construction=cons, max_names=names,
                       control_role="treatment", gross_target=0.95, name_cap=0.05,
                       input_families=["bars"], license="PRODUCT_EXPERIMENT",
                       spec_source="ROLLING-COHORTS-SPECIFICATIONS-v2", state="DECLARED_ROLLING")
            key = digest(rolling_semantic(row))
            row.update(policy_id=key[:24], semantic_sha256=key)
            specs.append(row)
    ids = [s["policy_id"] for s in specs]
    if len(ids) != len(set(ids)):
        raise RollingCohortRefused("duplicate policy ids in the v2 spec grid")
    counts: dict = {}
    for s in specs:
        counts[s["family"]] = counts.get(s["family"], 0) + 1
    return {"schema": SPECS_SCHEMA, "license": "PRODUCT_EXPERIMENT",
            "parent_manifest_sha256": digest(v1),
            "parent_file": "docs/TRIALS/POPULATION-1000-SPECIFICATIONS.json",
            "contract": "docs/TRIALS/TRIAL-ROLLING-COHORTS-20261114.md",
            "specifications": specs, "excluded": excluded,
            "counts": {"specs": len(specs), "by_family": counts, "excluded": len(excluded)}}


def load_specs(path: Path) -> tuple[dict, str]:
    p = Path(path)
    if not p.is_file():
        raise RollingCohortRefused(f"spec file {p} is absent")
    specs = json.loads(p.read_bytes())
    if specs.get("schema") != SPECS_SCHEMA:
        raise RollingCohortRefused(f"{p} is not a {SPECS_SCHEMA} file")
    for s in specs["specifications"]:
        if digest(rolling_semantic(s)) != s["semantic_sha256"]:
            raise RollingCohortRefused(f"spec {s['policy_id']} was edited: its content no "
                                       f"longer hashes to its declared semantic_sha256")
    return specs, digest(specs)


# ──────────────────────────────── calendar ──────────────────────────────────

def bench_sessions(bars: pd.DataFrame, *, through: Any = None) -> list[pd.Timestamp]:
    d = bars.loc[bars["symbol"] == BENCH, "date"]
    if through is not None:
        d = d[d <= pd.Timestamp(through)]
    return sorted(pd.to_datetime(d.unique()))


def schedule(sessions: list[pd.Timestamp], *, anchor: Any, cadence: int) -> list[pd.Timestamp]:
    """Cohort dates: the anchor session, then every `cadence` sessions after it."""
    a = pd.Timestamp(anchor)
    if a not in set(sessions):
        raise RollingCohortRefused(f"anchor {a.date()} is not a session in the {BENCH} bars")
    i = sessions.index(a)
    return sessions[i::cadence]


def clocks(cohort: pd.Timestamp, entry: pd.Timestamp) -> tuple[datetime, datetime]:
    decision = datetime.combine(cohort.date(), time(21, 0), tzinfo=timezone.utc)
    available = datetime.combine(entry.date(), time(0, 0), tzinfo=timezone.utc)
    return decision, available


def _utc(v: Any) -> Optional[datetime]:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    t = pd.Timestamp(v)
    if pd.isna(t):
        return None
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.to_pydatetime()


# ──────────────────────────────── inputs ────────────────────────────────────

def load_bars(data_root: Path, *, start: Any, end: Any) -> pd.DataFrame:
    p = Path(data_root) / BARS_REL
    if not p.is_file():
        raise RollingCohortRefused(f"bars panel {p} is absent")
    f = pd.read_parquet(p, columns=["symbol", "date", "open", "close", "volume"],
                        filters=[("date", ">=", pd.Timestamp(start)), ("date", "<=", pd.Timestamp(end))])
    f["date"] = pd.to_datetime(f["date"])
    return f


def _is_etf(t: str) -> bool:
    from backend.services import llm_portfolio as lp
    return lp.is_etf(t)


def market_features(bars: pd.DataFrame, cohort: pd.Timestamp) -> pd.DataFrame:
    """Per-symbol features from bars dated <= `cohort` ONLY (sliced here)."""
    from backend.services import xs_ranker as XR
    prior = bars[bars["date"] <= cohort]
    days = bench_sessions(prior)[-253:]
    if len(days) < 64 or days[-1] != cohort:
        raise RollingCohortRefused(f"{BENCH} has no bar on cohort date {cohort.date()} "
                                   f"(or < 64 sessions of history)")
    win = prior[prior["date"] >= days[0]]
    close = win.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(days)
    dv = (win["close"] * win["volume"]).rename("dv")
    dvw = pd.concat([win[["date", "symbol"]], dv], axis=1).pivot_table(
        index="date", columns="symbol", values="dv", aggfunc="last").reindex(days[-63:])
    last_date = prior.groupby("symbol")["date"].max()
    rets = close.pct_change(fill_method=None)
    r63 = rets.tail(63)
    vol = r63.std().where(r63.count() >= 20)
    r252 = rets.tail(252)
    x = r252[BENCH]
    beta, beta_se, nobs = {}, {}, {}
    xv = x.to_numpy()
    for s in r252.columns:
        y = r252[s].to_numpy()
        m = np.isfinite(y) & np.isfinite(xv)
        n = int(m.sum())
        if n < 120:
            continue
        xm, ym = xv[m] - xv[m].mean(), y[m] - y[m].mean()
        vx = float((xm * xm).sum())
        if vx <= 0:
            continue
        b = float((xm * ym).sum() / vx)
        resid = ym - b * xm
        beta[s] = b
        beta_se[s] = math.sqrt(float((resid * resid).sum()) / (n - 2) / vx)
        nobs[s] = n
    mom = (close.iloc[-22] / close.iloc[-253] - 1.0) if len(days) >= 253 else pd.Series(np.nan, index=close.columns)
    out = pd.DataFrame({"last_close": close.ffill().iloc[-1], "vol63": vol,
                        "beta252": pd.Series(beta), "beta_se": pd.Series(beta_se),
                        "beta_n": pd.Series(nobs), "mom12_1": mom,
                        "mdv63": dvw.median(), "last_date": last_date})
    out.index.name = "symbol"
    out["band"] = [XR.liquidity_band(float(v)) if pd.notna(v) else "small" for v in out["mdv63"]]
    out["segment"] = np.where(out["band"].isin(["mega", "large", "mid"]), "liquid", "broad")
    out["cost_bps"] = [XR.COST_BPS_BY_BAND[b] for b in out["band"]]
    live = (out["last_date"] >= cohort - pd.Timedelta(days=5)) & (out["last_close"] >= XR.MIN_PRICE)
    proxies = set(XR.INDEX_PROXIES)
    out["eligible"] = live & np.array([not (s in proxies or s == "CASH" or _is_etf(s)) for s in out.index])
    return out.drop(columns=["last_date"])


def revision_features(revisions: pd.DataFrame, *, cohort: pd.Timestamp,
                      available_before: datetime) -> tuple[pd.DataFrame, dict]:
    """revision_flow.compute on rows first seen before the cutoff, events < D."""
    from backend.services import revision_flow as rf
    if "pit_safe" not in revisions.columns or "first_seen_utc" not in revisions.columns:
        raise RollingCohortRefused("revisions carry no pit_safe / first_seen_utc column")
    seen = pd.to_datetime(revisions["first_seen_utc"], utc=True, errors="coerce")
    keep = seen.notna() & (seen < pd.Timestamp(available_before))
    frame = revisions[keep.to_numpy()]
    event = pd.to_datetime(frame["event_date"], errors="coerce")
    frame = frame[(event < cohort).to_numpy()]
    flow = rf.compute(frame, asof=cohort)
    newest = seen[keep].max()
    n_events = int(flow["n_events"].sum()) if len(flow) else 0
    return flow, {"n_events_90d": n_events, "n_tickers": int(len(flow)),
                  "newest_first_seen_utc": None if pd.isna(newest) else newest.isoformat()}


def load_news_items(path: Path) -> list[dict]:
    """Parse the typed-news cache once into VERSIONS (one per cached row).

    Same admission rules as v1's adapter. Versions are deduplicated per cohort,
    AFTER that cohort's cutoff (`dedupe_news_versions`): a re-typing cached after
    the cutoff must never change what an earlier cohort saw.
    """
    p = Path(path)
    if not p.is_file():
        return []
    versions: list[dict] = []
    with p.open("r", encoding="utf8") as f:
        for line in f:
            if len(line) > 1024 * 1024:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            row = rec.get("row")
            if not isinstance(row, dict) or not rec.get("cached_utc"):
                continue
            if (not row.get("item_id") or not row.get("url") or row.get("source_kind") != "news"
                    or row.get("injection_lines_removed") not in (None, 0)):
                continue
            score = row.get("sentiment")
            if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1:
                continue
            known, first = _utc(rec["cached_utc"]), _utc(row.get("first_seen_utc"))
            if known is None or first is None:
                continue
            published = _utc(row.get("published_utc")) or first
            if first > known or published > known:
                continue
            versions.append({"item_id": row["item_id"], "known": known, "published": published,
                             "event_type": row.get("event_type"), "score": float(score),
                             "tickers": [str(t).upper() for t in row.get("tickers") or []]})
    return versions


def dedupe_news_versions(versions: list[dict], *, available_before: datetime) -> list[dict]:
    """Versions known before the cutoff ONLY, then v1's rule: the latest version
    per item; an item typed with two event types (before the cutoff) is dropped."""
    items: dict[str, Optional[dict]] = {}
    for v in versions:
        if v["known"] >= available_before:
            continue
        prev = items.get(v["item_id"], "absent")
        if prev is None:
            continue
        if prev != "absent" and prev["event_type"] != v["event_type"]:
            items[v["item_id"]] = None          # ambiguous typed event: dropped, like v1
            continue
        if prev == "absent" or prev["known"] < v["known"]:
            items[v["item_id"]] = v
    return [v for v in items.values() if v]


def news_features(items: list[dict], *, available_before: datetime, decision: datetime,
                  market: set) -> tuple[list[dict], dict]:
    """Items known before the cutoff and published within 5 days of the decision.

    `items` are raw versions: the cutoff is applied BEFORE they are deduplicated."""
    out = []
    newest = None
    for it in dedupe_news_versions(items, available_before=available_before):
        newest = it["known"] if newest is None or it["known"] > newest else newest
        if (decision - it["published"]).total_seconds() > 5 * 86400 or it["published"] > decision:
            continue
        for t in it["tickers"]:
            if t in market:
                out.append({"ticker": t, "event_type": it["event_type"], "score": it["score"],
                            "published": it["published"].isoformat(), "item_id": it["item_id"]})
    n_items = len({r["item_id"] for r in out})
    return out, {"n_items_5d": n_items, "n_ticker_rows_5d": len(out),
                 "newest_cached_utc": None if newest is None else newest.isoformat()}


def _frame_hash(df: Optional[pd.DataFrame]) -> Optional[str]:
    if df is None:
        return None
    return hashlib.sha256(df.round(10).to_csv(lineterminator="\n").encode()).hexdigest()


# ─────────────────────────────── targets ────────────────────────────────────

def _clip(raw: dict[str, float], spec: dict) -> dict[str, float]:
    total = sum(raw.values())
    return {t: min(spec.get("name_cap", .05), spec.get("gross_target", .95) * v / total)
            for t, v in raw.items()}


def bar_targets(spec: dict, market: pd.DataFrame) -> tuple[Optional[dict], float]:
    """Long weights (+ SPY short weight) for the two bar-only families."""
    m = market[market["eligible"]]
    if spec["liquidity_segment"] == "liquid":
        m = m[m["segment"] == "liquid"]
    if spec["family"] == "low_risk":
        col = "vol63" if spec["mechanism"] == "low_vol_63" else "beta252"
        m = m[np.isfinite(m[col]) & np.isfinite(m["vol63"]) & (m["vol63"] > 0)]
        if spec["mechanism"] == "low_beta_252":
            m = m[m["beta252"] > 0]            # a negative-beta name is not "low risk", it is a hedge
        q = m[m[col] <= m[col].quantile(0.2)]
        pick = q.sort_values([col]).head(spec["max_names"])
    else:
        m = m[np.isfinite(m["mom12_1"]) & np.isfinite(m["beta252"]) & np.isfinite(m["vol63"]) & (m["vol63"] > 0)]
        q = m[m["mom12_1"] >= m["mom12_1"].quantile(0.8)]
        pick = q.sort_values(["mom12_1"], ascending=False).head(spec["max_names"])
    if pick.empty:
        return None, 0.0
    names = sorted(pick.index)
    raw = {t: (1.0 / float(pick.at[t, "vol63"]) if spec["construction"] == "volatility_aware" else 1.0)
           for t in names}
    w = _clip(raw, spec)
    short = 0.0
    if spec.get("hedge") == "spy_beta":
        short = float(min(1.5, max(0.0, sum(w[t] * float(pick.at[t, "beta252"]) for t in names))))
    return w, short


def v1_rows(spec: dict, *, market: pd.DataFrame, revision: Optional[pd.DataFrame],
            news: Optional[list[dict]], decision: datetime, cohort: pd.Timestamp) -> list[dict]:
    """Rows in the shape `branch_population.targets` reads, after v1's filters."""
    rows: list[dict] = []
    base = datetime.combine(cohort.date(), time(), tzinfo=timezone.utc)
    seg_ok = (lambda t: market.at[t, "segment"] == "liquid") if spec["liquidity_segment"] == "liquid" else (lambda t: True)
    limit = spec["max_age_days"] * 86400
    if "revision" in spec["input_families"] and revision is not None:
        for t, v in revision.iterrows():
            if t not in market.index or not market.at[t, "eligible"] or not seg_ok(t):
                continue
            event = base - timedelta(days=float(v["days_since_last"]))
            if (decision - event).total_seconds() > limit:
                continue
            vol = market.at[t, "vol63"]
            rows.append(dict(ticker=t, family="revision", score=None, n_firms=float(v["n_firms"]),
                             net_raises=float(v["net_raises"]), event_at=event.isoformat(),
                             volatility=float(vol) if pd.notna(vol) else float("nan")))
    if "news" in spec["input_families"] and news is not None:
        agg: dict[str, list] = {}
        for r in news:
            if r["event_type"] != spec["event_type"]:
                continue
            t = r["ticker"]
            if t not in market.index or not market.at[t, "eligible"] or not seg_ok(t):
                continue
            pub = _utc(r["published"])
            if (decision - pub).total_seconds() > limit:
                continue
            agg.setdefault(t, []).append((r["score"], pub))
        for t, vals in agg.items():
            vol = market.at[t, "vol63"]
            rows.append(dict(ticker=t, family="news", score=sum(v for v, _ in vals) / len(vals),
                             n_firms=None, net_raises=None,
                             event_at=min(p for _, p in vals).isoformat(),
                             volatility=float(vol) if pd.notna(vol) else float("nan")))
    if spec["construction"] == "volatility_aware":
        rows = [r for r in rows if math.isfinite(r["volatility"]) and r["volatility"] > 0]
    return rows


def holdings_hash(long_w: dict, short: float) -> str:
    return digest(sorted([[t, round(w, 6)] for t, w in long_w.items()]) + [["SHORT:" + BENCH, round(short, 6)]])[:24]


# ──────────────────────────────── birth ─────────────────────────────────────

def family_input_status(specs: dict, inputs: dict) -> dict:
    """WAIT_INPUT per input family, with the count that decided it."""
    st = {"bars": {"status": "OK", **inputs["bars_meta"]}}
    rv, nw = inputs["revision_meta"], inputs["news_meta"]
    if rv is None:
        st["revision"] = {"status": "WAIT_INPUT", "why": "revisions file absent"}
    else:
        stale = None
        if rv.get("newest_first_seen_utc"):
            stale = (inputs["available_before"] - _utc(rv["newest_first_seen_utc"])).total_seconds() / 86400
        ok = (rv["n_events_90d"] >= _config.ROLLING_COHORT_REVISION_MIN_EVENTS
              and stale is not None and stale <= _config.ROLLING_COHORT_REVISION_MAX_STALE_DAYS)
        st["revision"] = {"status": "OK" if ok else "WAIT_INPUT", **rv,
                          "newest_age_days": None if stale is None else round(stale, 2),
                          "min_events_90d": _config.ROLLING_COHORT_REVISION_MIN_EVENTS,
                          "max_stale_days": _config.ROLLING_COHORT_REVISION_MAX_STALE_DAYS}
    if nw is None:
        st["news"] = {"status": "WAIT_INPUT", "why": "typed-news cache absent"}
    else:
        stale = None
        if nw.get("newest_cached_utc"):
            stale = (inputs["available_before"] - _utc(nw["newest_cached_utc"])).total_seconds() / 86400
        ok = (nw["n_items_5d"] >= _config.ROLLING_COHORT_NEWS_MIN_ITEMS
              and stale is not None and stale <= _config.ROLLING_COHORT_NEWS_MAX_STALE_DAYS)
        st["news"] = {"status": "OK" if ok else "WAIT_INPUT", **nw,
                      "newest_age_days": None if stale is None else round(stale, 2),
                      "min_items_5d": _config.ROLLING_COHORT_NEWS_MIN_ITEMS,
                      "max_stale_days": _config.ROLLING_COHORT_NEWS_MAX_STALE_DAYS}
    return st


def build_inputs(*, bars: pd.DataFrame, revisions: Optional[pd.DataFrame], news_items: Optional[list],
                 cohort: pd.Timestamp, entry: pd.Timestamp) -> dict:
    decision, available = clocks(cohort, entry)
    market = market_features(bars, cohort)
    flow, rmeta = (None, None)
    if revisions is not None:
        flow, rmeta = revision_features(revisions, cohort=cohort, available_before=available)
    news, nmeta = (None, None)
    if news_items is not None:
        news, nmeta = news_features(news_items, available_before=available, decision=decision,
                                    market=set(market.index[market["eligible"]]))
    hashes = {"bars": _frame_hash(market), "revision": _frame_hash(flow),
              "news": digest(sorted([r["item_id"], r["ticker"], r["score"]] for r in news)) if news is not None else None}
    return {"cohort": cohort, "entry": entry, "decision": decision, "available_before": available,
            "market": market, "revision": flow, "news": news, "hashes": hashes,
            "bars_meta": {"n_symbols": int(len(market)), "n_eligible": int(market["eligible"].sum())},
            "revision_meta": rmeta, "news_meta": nmeta}


def _seed(cohort: str, hh: str, k: int) -> int:
    tag = f"{_config.ROLLING_COHORT_SEED_TAG}|{cohort}|{hh}|{k}"
    return int(hashlib.sha256(tag.encode()).hexdigest()[:15], 16)


def random_controls(long_w: dict, short: float, market: pd.DataFrame, *, cohort: str, hh: str,
                    k_controls: int) -> list[dict]:
    """Name-for-name random same-band replacements, same weights, same short leg."""
    pool = market[market["eligible"]]
    by_band: dict[str, list[str]] = {}
    for s, b in pool["band"].items():
        if s not in long_w:
            by_band.setdefault(b, []).append(s)
    for v in by_band.values():
        v.sort()
    every = sorted(s for s in pool.index if s not in long_w)
    out = []
    for k in range(k_controls):
        seed = _seed(cohort, hh, k)
        rng = np.random.default_rng(seed)
        chosen: set = set()
        w = {}
        fallbacks = 0
        for t in sorted(long_w):
            band = market.at[t, "band"] if t in market.index else "small"
            cands = [s for s in by_band.get(band, []) if s not in chosen]
            if not cands:                       # band exhausted: any live name (llm_portfolio.twins rule)
                fallbacks += 1
                cands = [s for s in every if s not in chosen]
            if not cands:
                raise RollingCohortRefused("random same-band control ran out of live names")
            pick = cands[int(rng.integers(len(cands)))]
            chosen.add(pick)
            w[pick] = long_w[t]
        out.append({"kind": "random_control", "control_k": k, "seed": seed, "band_fallbacks": fallbacks,
                    "control_id": digest([hh, cohort, k, seed])[:24], "parent_holdings_hash": hh,
                    "long": w, "short": short, "holdings_hash": holdings_hash(w, short),
                    "cost_bps": {t: float(market.at[t, "cost_bps"]) for t in w}})
    return out


def birth(specs: dict, manifest: str, inputs: dict, *, backfilled: bool, born_utc: str,
          k_controls: int) -> dict:
    """One cohort: one row per spec (a READY book or a WAIT row with its count)."""
    cohort = inputs["cohort"].date().isoformat()
    market = inputs["market"]
    fstat = family_input_status(specs, inputs)
    rows, distinct = [], {}
    for spec in specs["specifications"]:
        need = list(spec["input_families"])
        waiting = [f for f in need if fstat.get(f, {}).get("status") != "OK"]
        base = {"policy_id": spec["policy_id"], "semantic_sha256": spec["semantic_sha256"],
                "family": spec["family"], "mechanism": spec["mechanism"],
                "horizon_sessions": spec["horizon_sessions"]}
        if waiting:
            rows.append({**base, "status": "WAIT_INPUT",
                         "why": {f: {k: fstat[f].get(k) for k in fstat[f] if k != "status"} for f in waiting}})
            continue
        if spec["family"] in BAR_FAMILIES:
            long_w, short = bar_targets(spec, market)
        else:
            frows = v1_rows(spec, market=market, revision=inputs["revision"], news=inputs["news"],
                            decision=inputs["decision"], cohort=inputs["cohort"])
            w = targets(spec, frows, asof=inputs["decision"].isoformat()) if frows else None
            long_w = {t: v for t, v in (w or {}).items() if t != "CASH"} or None
            short = 0.0
        if not long_w:
            rows.append({**base, "status": "WAIT_NO_ELIGIBLE_NAMES"})
            continue
        in_hash = digest([inputs["hashes"]["bars"]] + [inputs["hashes"][f] for f in need if f != "bars"])
        hh = holdings_hash(long_w, short)
        gross_long = float(sum(long_w.values()))
        beta_ex = float(sum(w * float(market.at[t, "beta252"]) for t, w in long_w.items()
                            if pd.notna(market.at[t, "beta252"])) - short)
        rows.append({**base, "status": "READY",
                     "book_id": digest([spec["semantic_sha256"], cohort, in_hash])[:24],
                     "params": rolling_semantic(spec), "long": long_w, "short": short,
                     "cash": round(1.0 - gross_long, 10), "gross_long": gross_long, "gross_short": short,
                     "invested_share": gross_long - short, "n_names": len(long_w),
                     "holdings_hash": hh, "inputs_hash": in_hash, "beta_ex_ante": beta_ex,
                     "matched_no_news_policy_id": spec.get("matched_no_news_policy_id"),
                     "cost_bps": {t: float(market.at[t, "cost_bps"]) for t in long_w}})
        distinct.setdefault(hh, (long_w, short))
    controls = []
    for hh in sorted(distinct):
        long_w, short = distinct[hh]
        controls += random_controls(long_w, short, market, cohort=cohort, hh=hh, k_controls=k_controls)
    counts: dict = {}
    for r in rows:
        key = f"{r['family']}:{r['status']}"
        counts[key] = counts.get(key, 0) + 1
    return {"schema": COHORT_SCHEMA, "cohort_id": cohort, "entry_session": inputs["entry"].date().isoformat(),
            "decision_utc": inputs["decision"].isoformat(),
            "available_before_utc": inputs["available_before"].isoformat(),
            "backfilled": bool(backfilled), "forward_evidence": not backfilled, "born_utc": born_utc,
            "spec_manifest_sha256": manifest, "input_hashes": inputs["hashes"], "input_status": fstat,
            "n_books": sum(r["status"] == "READY" for r in rows), "n_distinct_portfolios": len(distinct),
            "counts": counts, "books": rows, "controls": controls,
            "seed_tag": _config.ROLLING_COHORT_SEED_TAG, "k_random_controls": k_controls}


# ──────────────────────────────── store ─────────────────────────────────────

class Store:
    """`<out>/declaration.json`, `cohorts/cohort_<D>.json` (write-once),
    `inputs/` (feature snapshots taken only at birth), `marks/part-<run>.parquet`
    (append-only), `scoreboard_<run>.json`, `runs.jsonl` (the task journal)."""

    def __init__(self, out: Path):
        self.out = Path(out)
        self.cohorts_dir = self.out / "cohorts"
        self.marks_dir = self.out / "marks"
        self.inputs_dir = self.out / "inputs"

    def declaration(self) -> Optional[dict]:
        p = self.out / "declaration.json"
        return json.loads(p.read_bytes()) if p.is_file() else None

    def declare(self, *, manifest: str, specs_path: str, now: datetime) -> dict:
        d = self.declaration()
        snap = config_snapshot()
        if d is not None:
            if d["spec_manifest_sha256"] != manifest:
                raise RollingCohortRefused(
                    f"the spec manifest changed after birth ({d['spec_manifest_sha256'][:12]} -> "
                    f"{manifest[:12]}). Born books are immutable: a changed spec grid is a NEW "
                    f"population with its own --out, never an edit of this one")
            if "config_hash" not in d:
                raise RollingCohortRefused("this population was declared before its grading config was "
                                           "bound; start a new --out")
            old = d["config"]
            diff = sorted(k for k in set(old) | set(snap) if old.get(k) != snap.get(k))
            if diff:
                raise RollingCohortRefused(
                    f"the grading config differs from the one this population was declared under: "
                    f"{', '.join(f'{k} {old.get(k)!r} -> {snap.get(k)!r}' for k in diff)}. Born books keep "
                    f"their rules; a changed config is a new population with its own --out")
            return d
        d = {"schema": "rolling_population_declaration/2", "task": TASK_NAME,
             "declared_utc": now.isoformat(), "spec_manifest_sha256": manifest, "specs_path": specs_path,
             "license": "PRODUCT_EXPERIMENT", "contract": CONTRACT_REL,
             "config": snap, "config_hash": digest(snap), "code_version": code_version()}
        self.out.mkdir(parents=True, exist_ok=True)
        _write_once(self.out / "declaration.json", json.dumps(d, sort_keys=True, default=list, indent=1))
        return d

    def cohort_path(self, cohort_id: str) -> Path:
        return self.cohorts_dir / f"cohort_{cohort_id}.json"

    def cohorts(self) -> list[dict]:
        if not self.cohorts_dir.is_dir():
            return []
        out = []
        for p in sorted(self.cohorts_dir.glob("cohort_*.json")):
            try:
                out.append(json.loads(p.read_bytes()))
            except ValueError as exc:
                raise RollingCohortRefused(f"cohort ledger {p.name} is torn: {exc}") from exc
        return out

    def write_cohort(self, rec: dict, inputs: dict, manifest: str) -> Path:
        p = self.cohort_path(rec["cohort_id"])
        if p.exists():
            old = json.loads(p.read_bytes())
            if old["spec_manifest_sha256"] != manifest:
                raise RollingCohortRefused(f"cohort {rec['cohort_id']} was born under another spec manifest")
            return p
        self.cohorts_dir.mkdir(parents=True, exist_ok=True)
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        snap = self.inputs_dir / f"{rec['cohort_id']}_{digest(inputs['hashes'])[:16]}"
        if not snap.with_suffix(".market.parquet").exists():
            inputs["market"].reset_index().to_parquet(snap.with_suffix(".market.parquet"), index=False)
        if inputs["revision"] is not None and not snap.with_suffix(".revision.parquet").exists():
            inputs["revision"].reset_index().to_parquet(snap.with_suffix(".revision.parquet"), index=False)
        if inputs["news"] is not None and not snap.with_suffix(".news.json").exists():
            _write_once(snap.with_suffix(".news.json"), json.dumps(inputs["news"]))
        rec = dict(rec, input_snapshot_prefix=snap.name)
        _write_once(p, json.dumps(rec, sort_keys=True, allow_nan=False))
        return p

    def marks(self, columns: Optional[list[str]] = None) -> pd.DataFrame:
        if not self.marks_dir.is_dir():
            return pd.DataFrame()
        parts = sorted(self.marks_dir.glob("part-*.parquet"))
        if not parts:
            return pd.DataFrame()
        cols = None if columns is None else sorted(set(columns) | {"book_id", "mark_k"})
        m = pd.concat([pd.read_parquet(p, columns=cols) for p in parts], ignore_index=True)
        dup = m.duplicated(["book_id", "mark_k"])
        if dup.any():
            raise RollingCohortRefused(
                f"marks table holds {int(dup.sum())} duplicate (book_id, mark_k) rows: two passes "
                f"wrote the same marks. Counting them would double the evidence; repair by hand")
        return m if columns is None else m[columns]

    def append_marks(self, rows: list[dict], run_id: str) -> Optional[Path]:
        if not rows:
            return None
        self.marks_dir.mkdir(parents=True, exist_ok=True)
        p = self.marks_dir / f"part-{run_id}.parquet"
        tmp = p.with_suffix(".tmp")
        pd.DataFrame(rows).to_parquet(tmp, index=False)
        os.replace(tmp, p)
        return p

    def journal(self, row: dict) -> None:
        from backend.services import disk_guard
        self.out.mkdir(parents=True, exist_ok=True)
        disk_guard.locked_append_line(self.out / "runs.jsonl", json.dumps(row, sort_keys=True, default=str),
                                      fsync=True)


def _write_once(path: Path, text: str) -> None:
    """temp -> verify -> link into place; an existing file is never replaced."""
    path = Path(path)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:8]}.tmp")
    with tmp.open("x", encoding="utf8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)            # fails if `path` exists: write-once
    except FileExistsError:
        tmp.unlink()
        raise RollingCohortRefused(f"{path.name} already exists; a born record is never rewritten")
    tmp.unlink()


# ──────────────────────────────── marks ─────────────────────────────────────

def _path_for(long_w: dict, short: float, close: pd.DataFrame, opn: pd.DataFrame,
              spy_close: np.ndarray, spy_open0: float) -> tuple[np.ndarray, dict]:
    """NAV path (open of E = 1.0) of a buy-and-hold book; cash earns 0.

    A name with no valid open at E waits in cash at 0% until its first valid
    open (grade rule v2: never re-weighted onto the others). A halted or
    delisted name is held flat at its last close.
    """
    n = len(close)
    nav = np.full(n, 1.0 - sum(long_w.values()))
    deferred = {}
    for t, w in long_w.items():
        if t not in close.columns:
            nav += w
            deferred[t] = "NO_BARS"
            continue
        o = opn[t].to_numpy(dtype=float)
        ok = np.flatnonzero(np.isfinite(o) & (o > 0))
        if not len(ok):
            nav += w
            deferred[t] = "NO_VALID_OPEN_YET"
            continue
        j = int(ok[0])
        if j > 0:
            deferred[t] = f"ENTERED_AT_SESSION_{j + 1}"
        c = close[t].ffill().to_numpy(dtype=float)
        path = np.ones(n)
        path[j:] = c[j:] / o[j]
        path[~np.isfinite(path)] = 1.0
        nav += w * path
    nav += short * (1.0 - spy_close / spy_open0)
    return nav, deferred


def _beta(nav: np.ndarray, spy_close: np.ndarray, spy_open0: float) -> tuple[Optional[float], Optional[float], int]:
    r = np.diff(np.concatenate([[1.0], nav])) / np.concatenate([[1.0], nav[:-1]])
    x = np.diff(np.concatenate([[spy_open0], spy_close])) / np.concatenate([[spy_open0], spy_close[:-1]])
    m = np.isfinite(r) & np.isfinite(x)
    n = int(m.sum())
    if n < 3:
        return None, None, n
    xm, ym = x[m] - x[m].mean(), r[m] - r[m].mean()
    vx = float((xm * xm).sum())
    if vx <= 0:
        return None, None, n
    b = float((xm * ym).sum() / vx)
    resid = ym - b * xm
    se = math.sqrt(float((resid * resid).sum()) / (n - 2) / vx) if n > 2 else None
    return b, se, n


def mark_rows(cohorts: list[dict], bars: pd.DataFrame, *, through: pd.Timestamp,
              existing: set, run_id: str) -> list[dict]:
    """New mark rows (book or control x mark session) not already in the table."""
    sessions = bench_sessions(bars, through=through)
    if not sessions:
        return []
    marks = tuple(_config.ROLLING_COHORT_MARK_SESSIONS)
    need: set = set()
    plan = []
    for c in cohorts:
        e = pd.Timestamp(c["entry_session"])
        if e not in set(sessions):
            continue
        i0 = sessions.index(e)
        items = [("book", b) for b in c["books"] if b["status"] == "READY"] + [("random_control", k) for k in c["controls"]]
        todo = []
        for kind, it in items:
            rid = it["book_id"] if kind == "book" else it["control_id"]
            horizon = it["horizon_sessions"] if kind == "book" else max(_config.ROLLING_COHORT_HORIZONS)
            for k in marks:
                if k > horizon or i0 + k - 1 >= len(sessions) or (rid, k) in existing:
                    continue
                todo.append((kind, it, rid, k))
        if todo:
            plan.append((c, i0, todo))
            for _kind, it in items:            # controls too: a book row reads them
                need.update(it["long"])
    if not plan:
        return []
    need.add(BENCH)
    lo = min(sessions[i0] for _c, i0, _t in plan)
    sub = bars[(bars["symbol"].isin(need)) & (bars["date"] >= lo) & (bars["date"] <= through)]
    close_all = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    open_all = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last")
    rows: list[dict] = []
    for c, i0, todo in plan:
        days = sessions[i0:]
        close = close_all.reindex(days)
        opn = open_all.reindex(days)
        spy_c = close[BENCH].to_numpy(dtype=float)
        spy_o0 = float(opn[BENCH].iloc[0])
        rnd: dict[str, list] = {}
        for ctl in c["controls"]:
            rnd.setdefault(ctl["parent_holdings_hash"], []).append(ctl)
        cache: dict[str, tuple] = {}

        def path(hh, long_w, short):
            if hh not in cache:
                cache[hh] = _path_for(long_w, short, close, opn, spy_c, spy_o0)
            return cache[hh]

        for kind, it, rid, k in todo:
            nav, deferred = path(it["holdings_hash"], it["long"], it["short"])
            i = k - 1
            gross = float(nav[i] - 1.0)
            half = sum(w * it["cost_bps"].get(t, 35.0) for t, w in it["long"].items()) / 2.0
            half += it["short"] * _config.ROLLING_COHORT_SPY_COST_BPS / 2.0
            borrow = it["short"] * _config.ROLLING_COHORT_SHORT_BORROW_BPS_YR * k / 252.0
            cost = (2 * half + borrow) / 1e4
            net = gross - cost
            spy = float(spy_c[i] / spy_o0 - 1.0)
            share = float(sum(it["long"].values()) - it["short"])
            ctl_net = share * spy - abs(share) * _config.ROLLING_COHORT_SPY_COST_BPS / 1e4
            b, se, n = _beta(nav[: i + 1], spy_c[: i + 1], spy_o0)
            row = {"schema": MARK_SCHEMA, "run_id": run_id, "kind": kind, "book_id": rid,
                   "cohort_id": c["cohort_id"], "entry_session": c["entry_session"], "mark_k": k,
                   "mark_date": days[i].date().isoformat(), "backfilled": bool(c["backfilled"]),
                   "holdings_hash": it["holdings_hash"], "n_names": len(it["long"]),
                   "gross_long": float(sum(it["long"].values())), "gross_short": float(it["short"]),
                   "invested_share": share, "ret_gross": gross, "ret_net": net,
                   "ret_net_entry_only": gross - (half + borrow) / 1e4, "cost_charged": cost,
                   "spy_ret": spy, "control_same_share_net": ctl_net,
                   "excess_same_share": net - ctl_net, "excess_vs_spy": net - spy,
                   "beta_window": b, "beta_se": se, "beta_n": n, "n_deferred_entry": len(deferred)}
            if kind == "book":
                ctl = rnd.get(it["holdings_hash"], [])
                vals = []
                for x in ctl:
                    xn, _ = path(x["holdings_hash"], x["long"], x["short"])
                    xh = sum(w * x["cost_bps"].get(t, 35.0) for t, w in x["long"].items()) / 2.0
                    xh += x["short"] * _config.ROLLING_COHORT_SPY_COST_BPS / 2.0
                    vals.append(float(xn[i] - 1.0) - (2 * xh + borrow) / 1e4)
                rmean = float(np.mean(vals)) if vals else None
                row.update(policy_id=it["policy_id"], family=it["family"], mechanism=it["mechanism"],
                           horizon_sessions=it["horizon_sessions"],
                           params_json=json.dumps(it["params"], sort_keys=True),
                           inputs_hash=it["inputs_hash"], beta_ex_ante=it["beta_ex_ante"],
                           random_n=len(vals), random_mean_net=rmean,
                           excess_vs_random=None if rmean is None else net - rmean,
                           seed=None, parent_holdings_hash=None)
            else:
                row.update(policy_id=None, family="random_control", mechanism="random_same_band",
                           horizon_sessions=None, params_json=None, inputs_hash=None,
                           beta_ex_ante=None, random_n=None, random_mean_net=None,
                           excess_vs_random=None, seed=str(it["seed"]),
                           parent_holdings_hash=it["parent_holdings_hash"])
            rows.append(row)
    return rows


# ─────────────────────────────── scoreboard ─────────────────────────────────

def block_stats(values: list[float], session_idx: list[int], *, block: int, z: float) -> dict:
    """Mean with SE on NON-OVERLAPPING cohort-date blocks (overlap-aware n)."""
    if not values:
        return {"n_cohorts": 0, "n_blocks": 0, "mean": None, "se": None, "mde": None}
    df = pd.DataFrame({"v": values, "b": [i // block for i in session_idx]})
    bm = df.groupby("b")["v"].mean()
    n = int(len(bm))
    se = float(bm.std(ddof=1) / math.sqrt(n)) if n >= 2 else None
    return {"n_cohorts": int(len(df)), "n_blocks": n, "mean": float(df["v"].mean()),
            "se": se, "mde": None if se is None else z * se}


def _verdict(st: dict) -> str:
    if st["se"] is None or st["n_blocks"] < 2:
        return f"CANNOT DETERMINE ({st['n_blocks']} non-overlapping block(s); need >= 2 for an error bar)"
    if abs(st["mean"]) < st["mde"]:
        return f"CANNOT DETERMINE (|mean| {abs(st['mean']):.4f} < MDE {st['mde']:.4f})"
    return "OBSERVED DIFFERENCE BEYOND THE MDE (descriptive; not a claim)"


def scoreboard(marks: pd.DataFrame, cohorts: list[dict], *, mark_k: int, sessions: list[pd.Timestamp]) -> dict:
    z = float(_config.ROLLING_COHORT_MDE_Z)
    sidx = {s.date().isoformat(): i for i, s in enumerate(sessions)}
    out: dict = {"schema": "rolling_cohort_scoreboard/1", "mark_k": mark_k, "mde_z": z,
                 "label_rule": "OBSERVED(n_cohorts) only; no promotion, no EARLY_EVIDENCE logic here",
                 "unit": "excess_same_share = book net - SPY at the same invested share (net of its cost)",
                 "cohorts": [], "specs": [], "families": {}, "pairs": {}}
    for c in cohorts:
        ready = [b for b in c["books"] if b["status"] == "READY"]
        fam: dict = {}
        for b in c["books"]:
            f = fam.setdefault(b["family"], {"entered": 0, "distinct": set(), "WAIT_INPUT": 0,
                                             "WAIT_NO_ELIGIBLE_NAMES": 0})
            if b["status"] == "READY":
                f["entered"] += 1
                f["distinct"].add(b["holdings_hash"])
            else:
                f[b["status"]] = f.get(b["status"], 0) + 1
        out["cohorts"].append({"cohort_id": c["cohort_id"], "entry_session": c["entry_session"],
                               "backfilled": c["backfilled"], "books": len(ready),
                               "distinct_portfolios": c["n_distinct_portfolios"],
                               "random_controls": len(c["controls"]),
                               "input_status": {k: v.get("status") for k, v in c["input_status"].items()},
                               "families": {k: {**{x: y for x, y in v.items() if x != "distinct"},
                                                "distinct": len(v["distinct"])} for k, v in sorted(fam.items())}})
    if marks.empty:
        out["note"] = f"no mark at {mark_k} sessions yet"
        return out
    b = marks[(marks["kind"] == "book") & (marks["mark_k"] == mark_k)].copy()
    if b.empty:
        out["note"] = f"no mark at {mark_k} sessions yet"
        return out
    b["sidx"] = b["cohort_id"].map(sidx)
    b = b[b["sidx"].notna()]
    b["sidx"] = b["sidx"].astype(int)
    for view, sub in (("forward", b[~b["backfilled"]]), ("all_incl_backfilled", b)):
        specs_out = []
        for pid, g in sub.groupby("policy_id"):
            st = block_stats(g["excess_same_share"].tolist(), g["sidx"].tolist(), block=mark_k, z=z)
            loco = [float(g.drop(index=i)["excess_same_share"].mean()) for i in g.index] if len(g) > 1 else []
            r = g["excess_vs_random"].dropna()
            specs_out.append({"policy_id": pid, "family": g["family"].iloc[0], "mechanism": g["mechanism"].iloc[0],
                              **st, "label": f"OBSERVED({st['n_cohorts']})", "verdict": _verdict(st),
                              "distinct_portfolios": int(g["holdings_hash"].nunique()),
                              "by_month": {k: float(v) for k, v in g.groupby(g["cohort_id"].str[:7])["excess_same_share"].mean().items()},
                              "loco_min": min(loco) if loco else None, "loco_max": max(loco) if loco else None,
                              "mean_excess_vs_random": float(r.mean()) if len(r) else None,
                              "mean_excess_vs_spy": float(g["excess_vs_spy"].mean())})
        out["specs" if view == "forward" else "specs_all"] = specs_out
        fams = {}
        for fam, g in sub.groupby("family"):
            d = g.drop_duplicates(["cohort_id", "holdings_hash"])     # per DISTINCT portfolio
            per_c = d.groupby("cohort_id")["excess_same_share"].mean()
            st = block_stats(per_c.tolist(), [sidx[x] for x in per_c.index], block=mark_k, z=z)
            fams[fam] = {**st, "books": int(len(g)), "distinct_portfolio_cohort_rows": int(len(d)),
                         "verdict": _verdict(st)}
        out["families" if view == "forward" else "families_all"] = fams
    out["pairs"] = _pairs(b, cohorts)
    sp = out.get("specs_all", [])
    out["summary"] = {"specs_scored_forward": len(out.get("specs", [])), "specs_scored_all": len(sp),
                      "cannot_determine_all": sum(s["verdict"].startswith("CANNOT") for s in sp),
                      "median_mde_all": (float(np.median([s["mde"] for s in sp if s["mde"] is not None]))
                                         if any(s["mde"] is not None for s in sp) else None)}
    return out


def _pairs(b: pd.DataFrame, cohorts: list[dict]) -> dict:
    """Pairs that differ by ONE declared delta, counted only where holdings differ."""
    out = {}
    key = {(r["cohort_id"], r["policy_id"]): r for r in b.to_dict("records")}
    hyb, mom = [], []
    for c in cohorts:
        ready = {x["policy_id"]: x for x in c["books"] if x["status"] == "READY"}
        for x in ready.values():
            twin = x.get("matched_no_news_policy_id")
            if x["family"] == "hybrid_news_revision" and twin in ready:
                hyb.append((c["cohort_id"], x["policy_id"], twin))
            if x["family"] == "momentum_12_1" and x["params"]["hedge"] == "spy_beta":
                p = dict(x["params"], hedge="none")
                other = digest(p)[:24]
                if other in ready:
                    mom.append((c["cohort_id"], x["policy_id"], other))
    for name, pairs in (("hybrid_vs_no_news_twin", hyb), ("momentum_hedged_vs_unhedged", mom)):
        same = diff = 0
        deltas = []
        for cid, a, z in pairs:
            ra, rz = key.get((cid, a)), key.get((cid, z))
            if ra is None or rz is None:
                continue
            if ra["holdings_hash"] == rz["holdings_hash"]:
                same += 1
                continue
            diff += 1
            deltas.append(ra["ret_net"] - rz["ret_net"])
        out[name] = {"pairs_marked": same + diff, "identical_holdings": same, "differ": diff,
                     "mean_net_difference": float(np.mean(deltas)) if deltas else None,
                     "note": "row-level mean over differing pairs; pairs share cohorts, not independent"}
    return out


# ─────────────────────────────── the runner ─────────────────────────────────

class XnysCalendar:
    """The exchange calendar (`market_sessions`); injectable for tests."""

    def next_open_after(self, day: pd.Timestamp) -> datetime:
        from backend.services import market_sessions as MS
        return MS.next_session_open(MS.session_close_utc(day))

    def close_of(self, day: Any) -> Optional[datetime]:
        from backend.services import market_sessions as MS
        return MS.session_close_utc(day)


def _read_revisions(data_root: Path) -> Optional[pd.DataFrame]:
    p = Path(data_root) / REVISIONS_REL
    if not p.is_file():
        return None
    return pd.read_parquet(p, columns=["ticker", "event_date", "firm", "target_action", "prior_target",
                                       "current_target", "pit_safe", "first_seen_utc"])


def _rss_mb() -> Optional[dict]:
    """Resident and (Windows) peak working set of this process, MB."""
    try:
        import psutil
        m = psutil.Process().memory_info()
        peak = getattr(m, "peak_wset", None)
        return {"rss": round(m.rss / 1024 ** 2, 1),
                "peak": None if peak is None else round(peak / 1024 ** 2, 1)}
    except Exception:                                            # noqa: BLE001
        pass
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return None
        return {"rss": round(pmc.WorkingSetSize / 1024 ** 2, 1), "peak": round(pmc.PeakWorkingSetSize / 1024 ** 2, 1)}
    except Exception:                                            # noqa: BLE001
        return None


def run(mode: str, *, data_root: Path, out: Path, specs_path: Path, asof: Any = None,
        now: Optional[datetime] = None, date_from: Any = None, date_to: Any = None,
        calendar: Any = None) -> dict:
    """One idempotent pass. `step`: birth the due cohort if its entry has not
    opened, mark every cohort, write the scoreboard. `backfill`: birth every
    scheduled cohort in [from, to] whose entry has passed, flagged backfilled.

    One pass at a time per output folder (`run.lock`): a second pass waits
    `ROLLING_COHORT_LOCK_WAIT_S` and then returns a WAIT_LOCK row with rc 0.
    Never writes under `data_root`. Returns the journal row (also appended).
    """
    from backend.services import disk_guard
    store = Store(out)
    store.out.mkdir(parents=True, exist_ok=True)
    try:
        with disk_guard.file_lock(store.out / "run.lock", timeout_s=float(_config.ROLLING_COHORT_LOCK_WAIT_S)):
            return _run_locked(mode, data_root=data_root, store=store, specs_path=specs_path, asof=asof,
                               now=now, date_from=date_from, date_to=date_to, calendar=calendar)
    except disk_guard.FileLockTimeout as exc:
        row = {"task": TASK_NAME, "schema": "rolling_cohort_run/1", "mode": mode, "action": "WAIT_LOCK",
               "rc": 0, "born": [], "utc": (now or datetime.now(timezone.utc)).isoformat(),
               "reason": f"another pass holds {store.out / 'run.lock'}: {exc}"}
        store.journal(row)
        return row


def _run_locked(mode: str, *, data_root: Path, store: "Store", specs_path: Path, asof: Any,
                now: Optional[datetime], date_from: Any, date_to: Any, calendar: Any) -> dict:
    t0 = datetime.now(timezone.utc)
    now = now or t0
    cal = calendar or XnysCalendar()
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:6]
    specs, manifest = load_specs(specs_path)
    zero_diag = check_costs(config_snapshot())             # before anything is declared or written
    decl = store.declare(manifest=manifest, specs_path=str(specs_path), now=now)
    versions = {"config_hash": decl["config_hash"], "code_version": code_version(),
                "zero_cost_diagnostic": zero_diag}
    anchor = pd.Timestamp(_config.ROLLING_COHORT_ANCHOR)
    cadence = int(_config.ROLLING_COHORT_CADENCE_SESSIONS)
    through = pd.Timestamp(asof).normalize() if asof is not None else pd.Timestamp(now.date())
    bars = load_bars(data_root, start=anchor - pd.Timedelta(days=400), end=through)
    sessions = bench_sessions(bars)
    if not sessions or sessions[-1] < anchor:
        raise RollingCohortRefused(f"the {BENCH} bars do not reach the anchor {anchor.date()}")
    last_bar = sessions[-1]
    sched = schedule(sessions, anchor=anchor, cadence=cadence)
    existing = {c["cohort_id"]: c for c in store.cohorts()}
    # A session that has CLOSED but is not in the bars yet is the evening wait.
    next_open = cal.next_open_after(last_bar)
    next_close = cal.close_of(next_open.date()) if next_open else None
    prices_waiting = bool(next_close and now >= next_close)
    state: dict = {"loaded": False, "revisions": None, "news": None}
    born, missed, skipped = [], [], []

    def _birth(d: pd.Timestamp, entry: pd.Timestamp, backfilled: bool) -> None:
        if not state["loaded"]:
            state.update(loaded=True, revisions=_read_revisions(data_root),
                         news=load_news_items(Path(data_root) / NEWS_REL))
        inp = build_inputs(bars=bars, revisions=state["revisions"], news_items=state["news"],
                           cohort=d, entry=entry)
        rec = birth(specs, manifest, inp, backfilled=backfilled, born_utc=now.isoformat(),
                    k_controls=int(_config.ROLLING_COHORT_RANDOM_CONTROLS))
        rec.update(versions)
        store.write_cohort(rec, inp, manifest)
        existing[rec["cohort_id"]] = rec
        born.append({"cohort_id": rec["cohort_id"], "backfilled": backfilled, "books": rec["n_books"],
                     "distinct_portfolios": rec["n_distinct_portfolios"],
                     "random_controls": len(rec["controls"]),
                     "input_status": {k: v["status"] for k, v in rec["input_status"].items()},
                     "counts": rec["counts"]})

    if mode == "step":
        d = sched[-1]
        if d.date().isoformat() not in existing:
            i = sessions.index(d)
            if i + 1 < len(sessions):
                missed.append({"cohort_id": d.date().isoformat(), "why": "entry session already in the bars"})
            else:
                entry_open = cal.next_open_after(d)
                if now >= entry_open:
                    missed.append({"cohort_id": d.date().isoformat(),
                                   "why": f"entry open {entry_open.isoformat()} has passed"})
                else:
                    _birth(d, pd.Timestamp(entry_open.date()), backfilled=False)
    elif mode == "backfill":
        lo = pd.Timestamp(date_from) if date_from is not None else anchor
        hi = pd.Timestamp(date_to) if date_to is not None else last_bar
        for d in sched:
            if not lo <= d <= hi or d.date().isoformat() in existing:
                continue
            i = sessions.index(d)
            if i + 1 < len(sessions):
                entry = sessions[i + 1]
            else:
                entry_open = cal.next_open_after(d)
                if now < entry_open:
                    skipped.append({"cohort_id": d.date().isoformat(),
                                    "why": "FORWARD_WINDOW_OPEN: its entry has not opened; the step births it"})
                    continue
                entry = pd.Timestamp(entry_open.date())
            _birth(d, entry, backfilled=True)
    else:
        raise RollingCohortRefused(f"unknown mode {mode!r}")

    cohorts = [existing[k] for k in sorted(existing)]
    have = store.marks(columns=["book_id", "mark_k"])
    keys = set(zip(have["book_id"], have["mark_k"])) if len(have) else set()
    rows = mark_rows(cohorts, bars, through=last_bar, existing=keys, run_id=run_id)
    for r in rows:
        r.update(versions)
    part = store.append_marks(rows, run_id)
    marks = store.marks()
    boards = {str(k): scoreboard(marks, cohorts, mark_k=k, sessions=sessions)
              for k in _config.ROLLING_COHORT_HORIZONS}
    # A scoreboard is written only when its inputs changed (a birth or new marks);
    # a 2-hourly idle step points at the previous one instead of copying it.
    prior = sorted(store.out.glob("scoreboard_*.json"))
    if born or rows or not prior:
        board_path = store.out / f"scoreboard_{run_id}.json"
        tmp = board_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"run_id": run_id, "through": last_bar.date().isoformat(), "boards": boards},
                                  default=str), encoding="utf8")
        os.replace(tmp, board_path)
    else:
        board_path = prior[-1]

    fwd = [c for c in cohorts if not c["backfilled"]]
    sidx = {s: i for i, s in enumerate(sessions)}
    if fwd:
        newest_fwd = max(c["cohort_id"] for c in fwd)
        fwd_age = len(sessions) - 1 - sidx.get(pd.Timestamp(newest_fwd), len(sessions) - 1)
    else:
        newest_fwd = None
        declared = pd.Timestamp(_utc(decl["declared_utc"]).date())
        fwd_age = sum(1 for s in sessions if s > declared)
    live = 0
    for c in cohorts:
        e = pd.Timestamp(c["entry_session"])
        if e not in sidx or sidx[e] + max(_config.ROLLING_COHORT_HORIZONS) - 1 > len(sessions) - 1:
            live += 1
    if born:
        action = "BORN"
    elif prices_waiting:
        action = "WAIT_PRICES"
    elif missed:
        action = "MISSED_ENTRY_WINDOW"
    elif rows:
        action = "MARKED"
    else:
        action = "NOTHING_DUE"
    row = {"task": TASK_NAME, "schema": "rolling_cohort_run/1", "utc": now.isoformat(), "mode": mode,
           "action": action, "rc": 0, "run_id": run_id, "through": last_bar.date().isoformat(),
           "prices_waiting": prices_waiting, "born": born, "missed": missed, "skipped": skipped,
           "cohorts_total": len(cohorts), "cohorts_forward": len(fwd), "cohorts_live": live,
           "newest_cohort": max(existing) if existing else None, "newest_forward_cohort": newest_fwd,
           "forward_age_sessions": int(fwd_age), "cadence_sessions": cadence,
           "stale_limit_sessions": cadence * int(_config.ROLLING_COHORT_STALE_CADENCES),
           "marks_written": len(rows), "marks_part": None if part is None else str(part),
           "marks_total": int(len(marks)), "scoreboard": str(board_path),
           "summary_21": boards.get("21", {}).get("summary"),
           "spec_manifest_sha256": manifest, "llm_spend_usd": 0.0, "broker_calls": 0,
           "runtime_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 2), "rss_mb": _rss_mb()}
    store.journal(row)
    return row
