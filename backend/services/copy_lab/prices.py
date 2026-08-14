"""The default price panel: adjusted daily bars, and holes left as holes.

`auto_adjust=True` is how "corporate_actions: adjust" is implemented — splits
and dividends are already in the series, so a 4-for-1 split does not read as a
75% loss. What it does NOT handle is a ticker CHANGE or a merger: those return
no data at all, which is why the engine treats a name that goes permanently dark
as a liquidation at the last price it actually saw rather than at a price
reconstructed from somewhere else.

Sessions come from the BENCHMARK's index, not from a calendar. A session is a
day the market printed; holidays simply are not there, and no holiday table has
to be maintained or kept correct.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


class YFinancePanel:
    """Adjusted OHLCV for a fixed ticker set, fetched once and held."""

    def __init__(self, tickers: list[str], start: str, end: str | None = None,
                 benchmark: str = "SPY"):
        import yfinance as yf
        self.benchmark = benchmark
        names = sorted(set(t.upper() for t in tickers) | {benchmark})
        end = end or str(date.today() + timedelta(days=1))
        self._open: dict[str, pd.Series] = {}
        self._close: dict[str, pd.Series] = {}
        self._dv: dict[str, pd.Series] = {}
        try:
            df = yf.download(names, start=start, end=end, auto_adjust=True,
                             progress=False, group_by="ticker", timeout=30)
        except Exception as exc:                               # noqa: BLE001
            logger.error("COPY-LAB price panel fetch failed (%s) — every name "
                         "will read UNAVAILABLE, which the engine treats as "
                         "ineligible rather than as a pass", exc)
            df = pd.DataFrame()

        for t in names:
            try:
                sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                o = pd.to_numeric(sub["Open"], errors="coerce").dropna()
                c = pd.to_numeric(sub["Close"], errors="coerce").dropna()
                v = pd.to_numeric(sub["Volume"], errors="coerce").dropna()
            except Exception:                                  # noqa: BLE001
                continue
            if c.empty:
                continue
            self._open[t] = o
            self._close[t] = c
            self._dv[t] = (c.reindex(v.index).ffill() * v).rolling(20).median()

    def sessions(self) -> list[date]:
        s = self._close.get(self.benchmark)
        if s is None or s.empty:
            # No benchmark, no sessions. Refusing here is better than inventing
            # a business-day calendar the exchange never agreed to.
            logger.error("COPY-LAB: no %s history — there are no sessions to "
                         "fill or mark against", self.benchmark)
            return []
        return [d.date() for d in pd.to_datetime(s.index)]

    def _at(self, store: dict, ticker: str, day: date):
        s = store.get(ticker.upper())
        if s is None or s.empty:
            return None
        idx = pd.to_datetime(s.index)
        hit = s[idx.date == day]
        if len(hit) == 0:
            return None
        v = float(hit.iloc[0])
        return v if v == v else None            # NaN is unavailable, not a value

    def open_price(self, ticker: str, day: date):
        return self._at(self._open, ticker, day)

    def close_price(self, ticker: str, day: date):
        return self._at(self._close, ticker, day)

    def adv20(self, ticker: str, day: date):
        return self._at(self._dv, ticker, day)
