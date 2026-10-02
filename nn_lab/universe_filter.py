"""ETFs, ETNs and funds out of nn_lab's universe (review F7 'Universe', 2026-09-30).

A fund is not a company: a leveraged or volatility ETN decays by construction, and a model
that learns the decay reads it as skill. The living panel was already built without them
(`pull_deep_bars` dropped the universe file's `etf_like` members, except the index proxies
nn_lab skips anyway); they entered through `bars_delisted.parquet` (VXX, SILJ, BKCH, OILU:
funds that went inactive after the universe snapshot) and would enter through any later file.

Sources, each recorded per symbol:
  1. `etf_like` in the terminal repo's universe files (the venue's own asset record);
  2. a strict name pattern on the SEC company-ticker list (ETF/ETN/ProShares/iShares/...;
     "Trust" alone is NOT a fund: Healthcare Realty Trust is a company);
  3. the same pattern on Alpaca's inactive-asset names, when that list is on disk
     (`universe_meta/alpaca_assets_inactive.json`, fetched by `nn_lab.fetch_assets`).

    python -m nn_lab.universe_filter        # writes universe_meta/etf_exclusions.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from nn_lab import config as C

TERMINAL_UNIVERSE_DIR = C.REPO.parent / "aegis-alpha-terminal" / "state" / "universe"
SEC_TICKERS = C.OPTIMUS / "edgar_8k" / "company_tickers.json"
ALPACA_INACTIVE = C.OUT / "universe_meta" / "alpaca_assets_inactive.json"

FUND_NAME = re.compile(
    r"\b(ETF|ETN|ETNS|ETFS|PROSHARES|ISHARES|SPDR|DIREXION|IPATH|MICROSECTORS|"
    r"GRANITESHARES|LEVERAGED|INVERSE|ULTRAPRO|ULTRASHORT|2X|3X|-1X|-2X|-3X|"
    r"VIX|VOLATILITY|INDEX FUND|EXCHANGE[- ]TRADED|CLOSED[- ]END FUND|MUNICIPAL FUND|INCOME FUND|"
    r"(GOLD|SILVER|BITCOIN|ETHER|OIL|PLATINUM|PALLADIUM|COMMODITY) TRUST)\b", re.I)


def is_fund_name(name: str | None) -> bool:
    return bool(name) and bool(FUND_NAME.search(str(name)))


def collect(terminal_dir: Path | None = None, sec_path: Path | None = None,
            alpaca_path: Path | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    tdir = Path(terminal_dir or TERMINAL_UNIVERSE_DIR)
    for p in sorted(tdir.glob("*.json")) if tdir.exists() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in d.get("members", []):
            # the name, not the `etf_like` flag: that flag marks Healthcare Realty Trust (HR) and
            # WisdomTree, Inc. (WT), two companies
            if is_fund_name(m.get("name")):
                out.setdefault(m["symbol"], {"source": f"terminal_universe:{p.name}", "name": m.get("name")})
    sp = Path(sec_path or SEC_TICKERS)
    if sp.exists():
        d = json.loads(sp.read_text(encoding="utf-8"))
        for r in (d.values() if isinstance(d, dict) else d):
            if is_fund_name(r.get("title")):
                out.setdefault(r["ticker"], {"source": "sec_company_tickers:name", "name": r.get("title")})
    ap = Path(alpaca_path or ALPACA_INACTIVE)
    if ap.exists():
        for a in json.loads(ap.read_text(encoding="utf-8")):
            if is_fund_name(a.get("name")):
                out.setdefault(a["symbol"], {"source": "alpaca_inactive:name", "name": a.get("name")})
    return out


#: Checked by hand 2026-09-30: companies whose ticker a fund reused later, missing from the
#: CRSP common-stock file on disk (foreign domicile / below its screen). Their table rows are the
#: company's, not the fund's.
KEEP_AS_COMPANY = {"INFO": "IHS Markit Ltd, table rows 2017-01..2022-04 (a Harbor ETF reused INFO later)",
                   "RESI": "Front Yard Residential, table rows 2016-07..2021-02 (a Kelly ETF reused RESI later)"}

CRSP_MONTHLY = C.OPTIMUS / "crsp_pit" / "crsp_pit_monthly_v1.parquet"


def crsp_company_months(path: Path | None = None) -> dict[str, set[str]]:
    """ticker -> the months (YYYY-MM) CRSP lists it as a COMMON STOCK (share codes 10/11)."""
    import pandas as pd
    p = Path(path or CRSP_MONTHLY)
    if not p.exists():
        return {}
    m = pd.read_parquet(p, columns=["ticker", "date"]).dropna()
    m["ym"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m")
    return {t: set(g) for t, g in m.groupby("ticker")["ym"]}


def company_in_its_life(symbol_months: dict[str, set[str]], crsp: dict[str, set[str]]) -> set[str]:
    """Symbols a name pattern calls a fund, but which CRSP lists as a common stock during the
    months their bars cover: the ticker was a company's before a fund reused it (EV = Eaton
    Vance to 2021, INFO = IHS Markit to 2022). Those are KEPT."""
    return {s for s, ms in symbol_months.items() if ms & crsp.get(s.split("#")[0], set())}


def write(path: Path | None = None, symbol_months: dict[str, set[str]] | None = None, **kw) -> dict:
    ex = collect(**kw)
    kept_as_company: list[str] = []
    if symbol_months is not None:
        keep = company_in_its_life({s: m for s, m in symbol_months.items() if s in ex}, crsp_company_months())
        keep |= {k for k in KEEP_AS_COMPANY if k in ex}
        kept_as_company = sorted(keep)
        for s in keep:
            ex.pop(s, None)
    rec = {"artefact": "NN_LAB_ETF_EXCLUSIONS", "n": len(ex),
           "by_source": {s: sum(1 for v in ex.values() if v["source"].split(":")[0] == s)
                         for s in ("terminal_universe", "sec_company_tickers", "alpaca_inactive")},
           "kept_as_company_by_crsp": kept_as_company,
           "rule": "exact symbol only (a renamed earlier segment SYM#k is another company and is never excluded)",
           "alpaca_inactive_names_on_disk": Path(kw.get("alpaca_path") or ALPACA_INACTIVE).exists(),
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "symbols": dict(sorted(ex.items()))}
    p = Path(path or C.ETF_EXCLUSIONS)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


_CACHE: dict[str, frozenset] = {}


def excluded(path: Path | None = None) -> frozenset:
    """The exclusion set, or empty when the flag is off or the file is absent."""
    if not C.EXCLUDE_ETFS:
        return frozenset()
    p = Path(path or C.ETF_EXCLUSIONS)
    key = str(p)
    if key not in _CACHE:
        _CACHE[key] = (frozenset(json.loads(p.read_text(encoding="utf-8"))["symbols"])
                       if p.exists() else frozenset())
    return _CACHE[key]


def table_symbol_months(table_path: Path | None = None) -> dict[str, set[str]]:
    import pandas as pd
    t = pd.read_parquet(table_path or C.TABLE_PATH, columns=["symbol", "date"])
    t["ym"] = t["date"].dt.strftime("%Y-%m")
    return {s: set(g) for s, g in t.groupby("symbol")["ym"]}


if __name__ == "__main__":
    r = write(symbol_months=table_symbol_months())
    print(json.dumps({k: v for k, v in r.items() if k != "symbols"}, indent=1))
