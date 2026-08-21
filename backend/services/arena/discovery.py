"""DISCOVERY_UNIVERSE + the frozen daily information state.

This module is the caller the 16 descriptive collectors never had: it reads
their PIT scores (leak-free, `observed_at <= decision_ts`) and joins them with
price-derived state into one snapshot per session, frozen write-once before
any decision is made. The snapshot hash is the `information_state_hash` every
decision and experience record carries.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Protocol

from backend import config as _config
from backend.db import get_connection, get_series_observable
from backend.services.arena import store

logger = logging.getLogger(__name__)

#: PIT key prefixes joined into the snapshot. Every one of these accrues daily
#: from `_daily_check` and previously had no consumer.
SCORE_PREFIXES: dict[str, str] = {
    "multifactor": "multifactor_score:",
    "insider_opp": "insider_opp:",
    "insider_cmp": "insider_cmp:",
    "revisions": "revisions_score:",
    "pead": "pead_score:",
}

#: `quality` is deliberately ABSENT above. The PIT store carries
#: `quality_score:` for the ~12-name registered cross-section only
#: (TRIAL-QUALITY-IC), and mixing that with the arena's own universe-wide
#: quality would put two populations inside one cross-sectional z-score — the
#: exact error the coverage work exists to remove. The arena computes quality
#: for its WHOLE universe in `arena/fundamentals.py`, using the same pure
#: scorer the registered collector uses, and that is the only source of the
#: `quality` factor here.


class PricePanel(Protocol):
    """What the engine needs from prices. Injected, so tests stay offline."""

    def sessions(self) -> list[date]: ...
    def open_price(self, ticker: str, day: date) -> float | None: ...
    def close_price(self, ticker: str, day: date) -> float | None: ...
    def close_history(self, ticker: str, day: date,
                      n: int) -> list[float]: ...
    def volume_history(self, ticker: str, day: date,
                       n: int) -> list[float]: ...


class ArenaPanel:
    """Adjusted daily bars via yfinance, with trailing-history access.

    Same conventions as copy_lab's panel: holes are holes, sessions come from
    the benchmark's own index, NaN is unavailable rather than a value.
    """

    def __init__(self, tickers: list[str], start: str,
                 end: str | None = None, benchmark: str = "SPY"):
        import pandas as pd
        import yfinance as yf
        self.benchmark = benchmark
        names = sorted(set(t.upper() for t in tickers) | {benchmark})
        end = end or str(date.today() + timedelta(days=1))
        self._open: dict = {}
        self._close: dict = {}
        self._vol: dict = {}
        try:
            df = yf.download(names, start=start, end=end, auto_adjust=True,
                             progress=False, group_by="ticker", timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.error("ARENA price panel fetch failed (%s) — every name "
                         "reads UNAVAILABLE (ineligible, never a pass)", exc)
            df = pd.DataFrame()
        for t in names:
            try:
                sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                o = pd.to_numeric(sub["Open"], errors="coerce").dropna()
                c = pd.to_numeric(sub["Close"], errors="coerce").dropna()
                v = pd.to_numeric(sub.get("Volume"), errors="coerce").dropna()
            except Exception:  # noqa: BLE001
                continue
            if c.empty:
                continue
            self._open[t] = o
            self._close[t] = c
            if v is not None and not v.empty:
                self._vol[t] = v

    def sessions(self) -> list[date]:
        import pandas as pd
        s = self._close.get(self.benchmark)
        if s is None or s.empty:
            logger.error("ARENA: no %s history — no sessions to mark against",
                         self.benchmark)
            return []
        return [d.date() for d in pd.to_datetime(s.index)]

    def _at(self, store_: dict, ticker: str, day: date):
        import pandas as pd
        s = store_.get(ticker.upper())
        if s is None or s.empty:
            return None
        idx = pd.to_datetime(s.index)
        hit = s[idx.date == day]
        if len(hit) == 0:
            return None
        v = float(hit.iloc[0])
        return v if v == v else None

    def open_price(self, ticker: str, day: date):
        return self._at(self._open, ticker, day)

    def close_price(self, ticker: str, day: date):
        return self._at(self._close, ticker, day)

    def close_history(self, ticker: str, day: date, n: int) -> list[float]:
        import pandas as pd
        s = self._close.get(ticker.upper())
        if s is None or s.empty:
            return []
        idx = pd.to_datetime(s.index)
        upto = s[idx.date <= day]
        return [float(v) for v in upto.tail(n).tolist() if v == v]

    def volume_history(self, ticker: str, day: date, n: int) -> list[float]:
        import pandas as pd
        s = self._vol.get(ticker.upper())
        if s is None or s.empty:
            return []
        idx = pd.to_datetime(s.index)
        upto = s[idx.date <= day]
        return [float(x) for x in upto.tail(n).tolist() if x == x]

    def close_frame_fast(self, tickers, *, today: date | None = None):
        """Wide close panel straight from the stored series — the generic
        builder in `experience.close_frame` would call `close_price` once per
        (ticker, session) and each of those rebuilds a DatetimeIndex."""
        import pandas as pd
        cols = {t: s for t in sorted(set(str(x).upper() for x in tickers))
                if (s := self._close.get(t)) is not None and not s.empty}
        if not cols:
            return pd.DataFrame()
        df = pd.DataFrame(cols)
        df.index = pd.to_datetime(df.index)
        if today is not None:
            df = df[df.index.date <= today]
        return df


# ── universe ────────────────────────────────────────────────────────────────
def candidate_universe(extra: list[str] | None = None) -> list[str]:
    """The CORE universe: watchlist + sector names + whatever books hold.

    This is the declared population. `priced_fraction` — the degraded-fetch
    guard — is measured against THIS, never against the scan extension, or a
    scan full of tickers that have since been renamed would drag the fraction
    under the floor and stop the books from deciding for a reason that has
    nothing to do with the names they trade.
    """
    su = _config.config.get("stock_universe", {})
    names: set[str] = {t.upper() for t in su.get("default_watchlist", [])}
    for sect in (su.get("sector_stocks") or {}).values():
        names.update(t.upper() for t in sect)
    names.update(t.upper() for t in (extra or []))
    return sorted(names)


#: Where the broad scan list comes from. CRSP's own PIT monthly panel, which
#: is already on disk with `ticker`, `dollar_vol` and an `eligible` screen —
#: a real, data-derived US common-stock universe rather than a list typed from
#: memory. Its vintage ends 2024-12-31, so some tickers have since been
#: renamed or delisted; those simply read `no_price` and drop out, which is
#: the honest failure mode and the reason the scan is kept OUT of the
#: `priced_fraction` denominator.
SCAN_SOURCE = "crsp_pit_monthly_v1.parquet"
_SCAN_CACHE: dict[int, list[str]] = {}


def scan_universe(limit: int = 400) -> list[str]:
    """The `limit` most liquid eligible names in the CRSP PIT panel's last
    month. Cached per limit — this reads a 545k-row parquet."""
    if limit in _SCAN_CACHE:
        return _SCAN_CACHE[limit]
    path = _config.OPTIMUS_LEDGER_DIR / "crsp_pit" / SCAN_SOURCE
    if not path.exists():
        logger.warning("ARENA: no scan source at %s — DISCOVERY runs over the "
                       "core universe only, which means no name outside the "
                       "watchlist can ever be found", path)
        _SCAN_CACHE[limit] = []
        return []
    try:
        import pandas as pd
        df = pd.read_parquet(path, columns=["date", "ticker", "dollar_vol",
                                            "eligible"])
        last = df["date"].max()
        recent = df[(df["date"] == last) & df["eligible"].astype(bool)]
        recent = recent.dropna(subset=["ticker", "dollar_vol"])
        top = (recent.sort_values("dollar_vol", ascending=False)
               .head(limit)["ticker"].astype(str).str.upper().tolist())
    except Exception as exc:  # noqa: BLE001
        logger.error("ARENA: scan universe unreadable (%s) — core only", exc)
        top = []
    # Tickers CRSP writes with a share-class suffix that yfinance spells with
    # a dash (BRK.B -> BRK-B). Left alone if already clean.
    out = sorted({t.replace(".", "-") for t in top if t and t.isascii()})
    _SCAN_CACHE[limit] = out
    logger.info("ARENA scan universe: %d names from %s (as of %s)",
                len(out), SCAN_SOURCE, last if 'last' in dir() else "?")
    return out


# ── feature computation (pure given inputs) ─────────────────────────────────
MOM_LOOKBACK = 252   # sessions in the 12-1 momentum window
MOM_SKIP = 21        # most recent sessions EXCLUDED — the anti-chase month


def _mom_12_1(closes: list[float]) -> float | None:
    """Classic 12-1 momentum: return from t-252 to t-21. The last month is
    excluded by construction, which is exactly what the streak/factor-chase
    anti-signal results demand of any momentum the arena uses."""
    if len(closes) < MOM_LOOKBACK:
        return None
    a, b = closes[-(MOM_SKIP + 1)], closes[-MOM_LOOKBACK]
    return (a / b - 1.0) if b else None


def _trailing_features(closes: list[float]) -> dict:
    out: dict = {"vol63": None, "ret21": None, "streak_up": 0}
    if len(closes) >= 2:
        rets = [closes[i] / closes[i - 1] - 1.0
                for i in range(1, len(closes)) if closes[i - 1]]
        if len(rets) >= 21:
            out["ret21"] = closes[-1] / closes[-22] - 1.0
        if len(rets) >= 40:  # enough for a usable vol estimate
            window = rets[-63:]
            m = sum(window) / len(window)
            var = sum((r - m) ** 2 for r in window) / max(len(window) - 1, 1)
            out["vol63"] = var ** 0.5
        streak = 0
        for r in reversed(rets):
            if r > 0:
                streak += 1
            else:
                break
        out["streak_up"] = streak
    return out


def build_day_state(day: date, panel: PricePanel,
                    universe: list[str], *, db_path=None,
                    core: list[str] | None = None,
                    scan: list[str] | None = None,
                    tracker_block: dict | None = None,
                    nominations: list[dict] | None = None) -> dict:
    """One frozen information state: per-name prices, trailing state, the
    latest PIT score of every family (leak-free as of end of ``day``), and
    the tracker observations over the wider scan universe."""
    as_of_ts = f"{day}T23:59:59+00:00"
    conn = get_connection(db_path) if db_path is not None else get_connection()
    try:
        return _build_day_state_with_conn(
            day, panel, universe, conn, as_of_ts, core=core, scan=scan,
            tracker_block=tracker_block, nominations=nominations)
    finally:
        conn.close()


def _build_day_state_with_conn(day, panel, universe, conn,
                               as_of_ts: str, core=None, scan=None,
                               tracker_block=None, nominations=None) -> dict:
    names: dict[str, dict] = {}
    for t in universe:
        close = panel.close_price(t, day)
        if close is None:
            names[t] = {"status": "no_price"}
            continue
        closes = panel.close_history(t, day, MOM_LOOKBACK + 10)
        feats = _trailing_features(closes)
        scores: dict[str, float | None] = {"mom_12_1": _mom_12_1(closes)}
        for label, prefix in SCORE_PREFIXES.items():
            try:
                series = get_series_observable(conn, prefix + t, as_of_ts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ARENA: PIT read failed for %s%s: %s",
                               prefix, t, exc)
                series = []
            scores[label] = (float(series[-1]["value"])
                             if series and series[-1].get("value") is not None
                             else None)
        names[t] = {"status": "ok", "close": close, **feats,
                    "scores": scores}
    # Universe-wide quality, arena-owned. This is the factor the composite
    # already declared and could only populate for one name in 207.
    try:
        from backend.services.arena import fundamentals as _fund
        q = _fund.scores()
        for t, v in q.items():
            if names.get(t, {}).get("status") == "ok":
                names[t]["scores"]["quality"] = v
    except Exception as exc:  # noqa: BLE001
        logger.error("ARENA: universe quality unavailable (%s) — the "
                     "composite falls back to whatever else a name has, and "
                     "the coverage histogram will show it", exc)

    _add_arena_composite(names)
    n_scored = sum(1 for v in names.values()
                   if v.get("scores", {}).get("arena_composite") is not None)
    # Coverage histogram in the frozen state itself: "how many names were
    # ranked on how many factors" is the question FEATURE-COVERAGE-AUDIT-1
    # had to reconstruct, and a state that does not carry it makes every
    # later reader reconstruct it too.
    hist: dict[str, int] = {}
    for v in names.values():
        k = v.get("scores", {}).get("coverage_n")
        if k is not None:
            hist[str(k)] = hist.get(str(k), 0) + 1
    # DEGRADED-FETCH GUARD denominator: the CORE universe only. See
    # `candidate_universe` — a scan full of tickers renamed since the CRSP
    # vintage would otherwise drag the fraction under the floor and stop the
    # books deciding for a reason unrelated to the names they trade.
    core_names = [t for t in (core or universe)]
    n_core_priced = sum(1 for t in core_names
                        if names.get(t, {}).get("status") == "ok")
    priced_fraction = (n_core_priced / len(core_names)) if core_names else 0.0
    n_priced = sum(1 for v in names.values() if v.get("status") == "ok")

    # TRACKER CONTEXT over the wider scanned set. Never a score — see
    # `trackers.py` for the two reasons.
    if tracker_block is None:
        try:
            from backend.services.arena import trackers as _tr
            tracker_block = _tr.observe(day, panel,
                                        sorted(set(scan or []) | set(names)))
        except Exception as exc:  # noqa: BLE001
            logger.error("ARENA: tracker pass failed (%s) — the state is "
                         "frozen WITHOUT context; discovery finds nothing "
                         "today and the receipt says so", exc)
            tracker_block = {"scanned_n": 0, "observations": [],
                             "by_kind": {},
                             "error": f"{type(exc).__name__}: {exc}"}
    tracker_block = dict(tracker_block)
    for t, f in (tracker_block.pop("features", None) or {}).items():
        if t in names and names[t].get("status") == "ok":
            names[t]["context"] = f
    tracker_block["nominations"] = list(nominations or [])

    return {"date": str(day), "as_of_ts": as_of_ts, "universe_n": len(universe),
            "core_n": len(core_names), "core_priced_n": n_core_priced,
            "trackers": tracker_block,
            "scored_n": n_scored, "composite_version": COMPOSITE_VERSION,
            "coverage_histogram": hist,
            # The cross-section IS the estimator: every score in this state is
            # a z-score over whatever got priced. A day that fetched 20 of 180
            # names is not a thin day, it is a DIFFERENT universe wearing the
            # same name, and the snapshot is write-once so that mistake would
            # be permanent. Carried here so the decision path can refuse it.
            "priced_n": n_priced, "priced_fraction": round(priced_fraction, 4),
            "names": names}


#: The arena's OWN composite over the arena's OWN universe. The registered
#: collectors (multifactor etc.) score only the ~12-name book cross-section,
#: and widening THEM would change their z-scores mid-trial — so the arena
#: blends its own price-derived 12-1 momentum with whatever PIT families a
#: name has, using the same frozen pure estimator (z-score each factor
#: cross-sectionally, weighted mean of the AVAILABLE factors per name).
COMPOSITE_WEIGHTS: dict[str, float] = {
    "mom_12_1": 1.0,
    "multifactor": 1.0,   # itself momentum+insider+revisions on book names
    "revisions": 0.5,
    "insider_opp": 0.5,
    "pead": 0.5,
    "quality": 0.5,
}

#: Estimator identity. The YAML's SHA-256 is segment identity for the BOOKS,
#: but the composite they select on lives here in Python, so a code edit could
#: change every book's policy without changing a single config hash. This
#: string is carried into the seed and the daily receipt and is checked on
#: every run — see `spec.policy_fingerprint` and `store.assert_config_current`.
COMPOSITE_VERSION = "arena_composite@3-universe_quality"

#: Pairwise sample size at which the empirical factor correlation is trusted
#: 90% of the way. Below it the estimate is shrunk toward rho=1.
CORR_SHRINK_K = 20.0


def _pairwise_corr(cols: dict[str, dict[str, float]],
                   factors: list[str]) -> list[list[float]]:
    """Correlation between factor z-scores over names that have BOTH, shrunk
    toward 1.0 by pairwise sample size.

    Shrinking toward 1 (not toward 0) is deliberate: rho = 1 reproduces the
    plain weighted MEAN exactly, which is what this composite did before. So
    with no evidence the estimator degrades to its own predecessor rather than
    to a third behaviour, and every departure from it is paid for by pairwise
    observations. Order 24 measured 3–7 shared latent factors across all
    sources — high correlation is the prior, and 1.0 is its conservative edge.
    """
    k = len(factors)
    corr = [[1.0] * k for _ in range(k)]
    for a in range(k):
        for b in range(a + 1, k):
            xa, xb = cols.get(factors[a], {}), cols.get(factors[b], {})
            shared = sorted(set(xa) & set(xb))
            n = len(shared)
            r = 1.0
            if n >= 3:
                va = [xa[t] for t in shared]
                vb = [xb[t] for t in shared]
                ma, mb = sum(va) / n, sum(vb) / n
                sa = (sum((v - ma) ** 2 for v in va) / (n - 1)) ** 0.5
                sb = (sum((v - mb) ** 2 for v in vb) / (n - 1)) ** 0.5
                if sa > 0 and sb > 0:
                    cov = sum((va[i] - ma) * (vb[i] - mb)
                              for i in range(n)) / (n - 1)
                    lam = n / (n + CORR_SHRINK_K)
                    r = lam * max(-0.99, min(0.99, cov / (sa * sb))) + (1 - lam)
            corr[a][b] = corr[b][a] = r
    return corr


def _zscore_col(col: dict[str, float]) -> dict[str, float]:
    n = len(col)
    if n < 2:
        return {t: 0.0 for t in col}
    m = sum(col.values()) / n
    sd = (sum((v - m) ** 2 for v in col.values()) / (n - 1)) ** 0.5
    return {t: ((v - m) / sd if sd > 0 else 0.0) for t, v in col.items()}


def _add_arena_composite(names: dict) -> None:
    """Coverage-normalized composite, plus the raw mean and the coverage
    vector beside it.

    FEATURE-COVERAGE-AUDIT-1 (`scripts/arena_coverage_audit.py`): the plain
    weighted mean of available z-scores shrinks well-measured names toward the
    middle, so under the live coverage split (~12 of ~180 names carry the PIT
    families) the enriched names appear in a top-12 selection 0.43 times on
    average against the 0.80 that coverage-blindness would give — they are
    structurally scarce in the tail the selection reads. Dividing the weighted
    SUM by the standard deviation implied by each name's OWN available set
    removes that; a name's composite then has unit variance whatever it was
    scored on.

    Two numbers are kept for every name so the change is auditable rather than
    asserted: `arena_composite` (normalized, what selection uses) and
    `arena_composite_raw_mean` (the predecessor). `coverage_n` and
    `coverage` record WHICH factors were present, so a later reader can ask
    whether missingness was doing the ranking without re-deriving the state.

    Honest sizing, from the same audit: normalizing is worth +0.012 in latent
    -skill units (1.6% of the oracle gap) while widening coverage from 12
    names to all 180 is worth +0.239 (31%). This fixes a defect; it does not
    fix the arena's real coverage hole, and it must not be reported as if it
    did.
    """
    factors = [f for f in COMPOSITE_WEIGHTS]
    cols_raw: dict[str, dict[str, float]] = {}
    for factor in factors:
        col = {t: row["scores"][factor] for t, row in names.items()
               if row.get("status") == "ok"
               and row.get("scores", {}).get(factor) is not None}
        if col:
            cols_raw[factor] = col
    z = {f: _zscore_col(col) for f, col in cols_raw.items()}
    corr = _pairwise_corr(z, factors)

    for t, row in names.items():
        if row.get("status") != "ok":
            continue
        present = [i for i, f in enumerate(factors) if t in z.get(f, {})]
        row["scores"]["coverage"] = [factors[i] for i in present]
        row["scores"]["coverage_n"] = len(present)
        if not present:
            row["scores"]["arena_composite"] = None
            row["scores"]["arena_composite_raw_mean"] = None
            continue
        w = [COMPOSITE_WEIGHTS[factors[i]] for i in present]
        vals = [z[factors[i]][t] for i in present]
        num = sum(wi * v for wi, v in zip(w, vals))
        den = sum(w)
        var = sum(w[a] * w[b] * corr[present[a]][present[b]]
                  for a in range(len(present)) for b in range(len(present)))
        row["scores"]["arena_composite"] = (
            round(num / var ** 0.5, 4) if var > 0 else 0.0)
        row["scores"]["arena_composite_raw_mean"] = (
            round(num / den, 4) if den else 0.0)


def freeze_day_state(day: date, panel: PricePanel, universe: list[str],
                     *, root=None, db_path=None, core=None, scan=None,
                     tracker_block=None, nominations=None) -> dict:
    existing = store.read_snapshot(str(day), root)
    if existing is not None:
        return existing
    state = build_day_state(day, panel, universe, db_path=db_path,
                            core=core, scan=scan,
                            tracker_block=tracker_block,
                            nominations=nominations)
    if state["scored_n"] == 0:
        # A snapshot with zero scores would make every book silently hold
        # forever while looking scheduled and green. Freeze it anyway (it IS
        # the day's truth) but say so loudly in the log and the state itself.
        logger.warning("ARENA: %s snapshot has ZERO multifactor-scored names "
                       "out of %d — selection cannot refresh from this state",
                       day, state["universe_n"])
    return store.freeze_snapshot(str(day), state, root)
