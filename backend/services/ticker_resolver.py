"""
Ticker Resolver — company name → symbol
=========================================

Users type "MARVELL" or "apple" into the stock page and get a 404 because
everything downstream expects "MRVL"/"AAPL". This service resolves free-text
company names to tickers: a static alias map first (offline, instant), then
an optional yfinance Search fallback (cached, rate-limit-guarded).

resolve_ticker("marvell")            -> {"ticker": "MRVL", "name": "Marvell Technology", ...}
resolve_ticker("APPLE INC")          -> {"ticker": "AAPL", ...}
resolve_ticker("AAPL")               -> {"ticker": "AAPL", ...}  (identity)
resolve_ticker("XYZZY123")           -> None
"""

from __future__ import annotations

import logging
import re

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Corporate suffixes that users omit or add inconsistently.
_SUFFIXES = (
    "INCORPORATED", "TECHNOLOGIES", "TECHNOLOGY", "CORPORATION", "HOLDINGS",
    "COMPANIES", "PLATFORMS", "INTERNATIONAL", "COMPANY", "GROUP", "CORP",
    "INC", "LTD", "PLC", "CO", "SA", "NV", "AG", "THE", "&",
)

# display-name aliases → ticker. Keys are matched AFTER normalization
# (uppercase, punctuation stripped, corporate suffixes removed).
_ALIASES: dict[str, tuple[str, str]] = {
    # Mega/large caps + the screener universe
    "APPLE": ("AAPL", "Apple"),
    "MICROSOFT": ("MSFT", "Microsoft"),
    "NVIDIA": ("NVDA", "NVIDIA"),
    "ALPHABET": ("GOOGL", "Alphabet (Google)"),
    "GOOGLE": ("GOOGL", "Alphabet (Google)"),
    "AMAZON": ("AMZN", "Amazon"),
    "META": ("META", "Meta Platforms"),
    "FACEBOOK": ("META", "Meta Platforms"),
    "TESLA": ("TSLA", "Tesla"),
    "BERKSHIRE HATHAWAY": ("BRK-B", "Berkshire Hathaway (B)"),
    "BERKSHIRE": ("BRK-B", "Berkshire Hathaway (B)"),
    "ELI LILLY": ("LLY", "Eli Lilly"),
    "LILLY": ("LLY", "Eli Lilly"),
    "BROADCOM": ("AVGO", "Broadcom"),
    "JPMORGAN": ("JPM", "JPMorgan Chase"),
    "JP MORGAN": ("JPM", "JPMorgan Chase"),
    "VISA": ("V", "Visa"),
    "MASTERCARD": ("MA", "Mastercard"),
    "UNITEDHEALTH": ("UNH", "UnitedHealth"),
    "UNITED HEALTH": ("UNH", "UnitedHealth"),
    "EXXON": ("XOM", "Exxon Mobil"),
    "EXXON MOBIL": ("XOM", "Exxon Mobil"),
    "JOHNSON JOHNSON": ("JNJ", "Johnson & Johnson"),
    "JOHNSON AND JOHNSON": ("JNJ", "Johnson & Johnson"),
    "WALMART": ("WMT", "Walmart"),
    "PROCTER GAMBLE": ("PG", "Procter & Gamble"),
    "PROCTER AND GAMBLE": ("PG", "Procter & Gamble"),
    "HOME DEPOT": ("HD", "Home Depot"),
    "COSTCO": ("COST", "Costco"),
    "ORACLE": ("ORCL", "Oracle"),
    "SALESFORCE": ("CRM", "Salesforce"),
    "NETFLIX": ("NFLX", "Netflix"),
    "ADOBE": ("ADBE", "Adobe"),
    "COCA COLA": ("KO", "Coca-Cola"),
    "COCACOLA": ("KO", "Coca-Cola"),
    "COKE": ("KO", "Coca-Cola"),
    "PEPSI": ("PEP", "PepsiCo"),
    "PEPSICO": ("PEP", "PepsiCo"),
    "MCDONALDS": ("MCD", "McDonald's"),
    "CHEVRON": ("CVX", "Chevron"),
    "ABBVIE": ("ABBV", "AbbVie"),
    "MERCK": ("MRK", "Merck"),
    "PFIZER": ("PFE", "Pfizer"),
    "BANK OF AMERICA": ("BAC", "Bank of America"),
    "WELLS FARGO": ("WFC", "Wells Fargo"),
    "GOLDMAN SACHS": ("GS", "Goldman Sachs"),
    "GOLDMAN": ("GS", "Goldman Sachs"),
    "MORGAN STANLEY": ("MS", "Morgan Stanley"),
    "AMD": ("AMD", "Advanced Micro Devices"),
    "ADVANCED MICRO DEVICES": ("AMD", "Advanced Micro Devices"),
    "INTEL": ("INTC", "Intel"),
    "QUALCOMM": ("QCOM", "Qualcomm"),
    "TEXAS INSTRUMENTS": ("TXN", "Texas Instruments"),
    "MICRON": ("MU", "Micron Technology"),
    "MARVELL": ("MRVL", "Marvell Technology"),
    "TSMC": ("TSM", "Taiwan Semiconductor"),
    "TAIWAN SEMICONDUCTOR": ("TSM", "Taiwan Semiconductor"),
    "ASML": ("ASML", "ASML"),
    "ARM": ("ARM", "Arm Holdings"),
    "PALANTIR": ("PLTR", "Palantir"),
    "SNOWFLAKE": ("SNOW", "Snowflake"),
    "CROWDSTRIKE": ("CRWD", "CrowdStrike"),
    "DATADOG": ("DDOG", "Datadog"),
    "SERVICENOW": ("NOW", "ServiceNow"),
    "SHOPIFY": ("SHOP", "Shopify"),
    "UBER": ("UBER", "Uber"),
    "AIRBNB": ("ABNB", "Airbnb"),
    "PAYPAL": ("PYPL", "PayPal"),
    "BLOCK": ("XYZ", "Block (Square)"),
    "SQUARE": ("XYZ", "Block (Square)"),
    "COINBASE": ("COIN", "Coinbase"),
    "ROBINHOOD": ("HOOD", "Robinhood"),
    "DRAFTKINGS": ("DKNG", "DraftKings"),
    "BOEING": ("BA", "Boeing"),
    "LOCKHEED": ("LMT", "Lockheed Martin"),
    "LOCKHEED MARTIN": ("LMT", "Lockheed Martin"),
    "RAYTHEON": ("RTX", "RTX (Raytheon)"),
    "RTX": ("RTX", "RTX (Raytheon)"),
    "NORTHROP": ("NOC", "Northrop Grumman"),
    "NORTHROP GRUMMAN": ("NOC", "Northrop Grumman"),
    "GENERAL DYNAMICS": ("GD", "General Dynamics"),
    "CATERPILLAR": ("CAT", "Caterpillar"),
    "DEERE": ("DE", "John Deere"),
    "JOHN DEERE": ("DE", "John Deere"),
    "GENERAL ELECTRIC": ("GE", "GE Aerospace"),
    "GE": ("GE", "GE Aerospace"),
    "HONEYWELL": ("HON", "Honeywell"),
    "UNION PACIFIC": ("UNP", "Union Pacific"),
    "UPS": ("UPS", "United Parcel Service"),
    "UNITED PARCEL": ("UPS", "United Parcel Service"),
    "FEDEX": ("FDX", "FedEx"),
    "DISNEY": ("DIS", "Walt Disney"),
    "WALT DISNEY": ("DIS", "Walt Disney"),
    "COMCAST": ("CMCSA", "Comcast"),
    "VERIZON": ("VZ", "Verizon"),
    "ATT": ("T", "AT&T"),
    "AT T": ("T", "AT&T"),
    "TMOBILE": ("TMUS", "T-Mobile US"),
    "T MOBILE": ("TMUS", "T-Mobile US"),
    "NIKE": ("NKE", "Nike"),
    "STARBUCKS": ("SBUX", "Starbucks"),
    "TARGET": ("TGT", "Target"),
    "LOWES": ("LOW", "Lowe's"),
    "FORD": ("F", "Ford Motor"),
    "GENERAL MOTORS": ("GM", "General Motors"),
    "GM": ("GM", "General Motors"),
    "RIVIAN": ("RIVN", "Rivian"),
    "LUCID": ("LCID", "Lucid Group"),
    "OCCIDENTAL": ("OXY", "Occidental Petroleum"),
    "CONOCOPHILLIPS": ("COP", "ConocoPhillips"),
    "CONOCO": ("COP", "ConocoPhillips"),
    "SCHLUMBERGER": ("SLB", "SLB (Schlumberger)"),
    "HALLIBURTON": ("HAL", "Halliburton"),
    "NEXTERA": ("NEE", "NextEra Energy"),
    "NEXTERA ENERGY": ("NEE", "NextEra Energy"),
    "DUKE ENERGY": ("DUK", "Duke Energy"),
    "SOUTHERN": ("SO", "Southern Company"),
    "AMERICAN EXPRESS": ("AXP", "American Express"),
    "AMEX": ("AXP", "American Express"),
    "BLACKROCK": ("BLK", "BlackRock"),
    "BLACKSTONE": ("BX", "Blackstone"),
    "CHARLES SCHWAB": ("SCHW", "Charles Schwab"),
    "SCHWAB": ("SCHW", "Charles Schwab"),
    "CITIGROUP": ("C", "Citigroup"),
    "CITI": ("C", "Citigroup"),
    "THERMO FISHER": ("TMO", "Thermo Fisher Scientific"),
    "ABBOTT": ("ABT", "Abbott Laboratories"),
    "DANAHER": ("DHR", "Danaher"),
    "BRISTOL MYERS": ("BMY", "Bristol Myers Squibb"),
    "BRISTOL MYERS SQUIBB": ("BMY", "Bristol Myers Squibb"),
    "AMGEN": ("AMGN", "Amgen"),
    "GILEAD": ("GILD", "Gilead Sciences"),
    "MODERNA": ("MRNA", "Moderna"),
    "NOVO NORDISK": ("NVO", "Novo Nordisk"),
    "LINDE": ("LIN", "Linde"),
    "SHERWIN WILLIAMS": ("SHW", "Sherwin-Williams"),
    "NEWMONT": ("NEM", "Newmont"),
    "FREEPORT": ("FCX", "Freeport-McMoRan"),
    "FREEPORT MCMORAN": ("FCX", "Freeport-McMoRan"),
    "PROLOGIS": ("PLD", "Prologis"),
    "REALTY INCOME": ("O", "Realty Income"),
    "AMERICAN TOWER": ("AMT", "American Tower"),
    "SPOTIFY": ("SPOT", "Spotify"),
    "ROBLOX": ("RBLX", "Roblox"),
    "ELECTRONIC ARTS": ("EA", "Electronic Arts"),
    "SOFI": ("SOFI", "SoFi Technologies"),
    "IONQ": ("IONQ", "IonQ"),
    "VERTIV": ("VRT", "Vertiv"),
    "SUPER MICRO": ("SMCI", "Super Micro Computer"),
    "SUPERMICRO": ("SMCI", "Super Micro Computer"),
    "DELL": ("DELL", "Dell Technologies"),
    "IBM": ("IBM", "IBM"),
    "CISCO": ("CSCO", "Cisco Systems"),
    "APPLIED MATERIALS": ("AMAT", "Applied Materials"),
    "LAM RESEARCH": ("LRCX", "Lam Research"),
    "KLA": ("KLAC", "KLA"),
    "SYNOPSYS": ("SNPS", "Synopsys"),
    "CADENCE": ("CDNS", "Cadence Design"),
    "INTUIT": ("INTU", "Intuit"),
    "WORKDAY": ("WDAY", "Workday"),
    "MONGODB": ("MDB", "MongoDB"),
    "CLOUDFLARE": ("NET", "Cloudflare"),
    "ZSCALER": ("ZS", "Zscaler"),
    "FORTINET": ("FTNT", "Fortinet"),
    "PANW": ("PANW", "Palo Alto Networks"),
    "PALO ALTO": ("PANW", "Palo Alto Networks"),
    "PALO ALTO NETWORKS": ("PANW", "Palo Alto Networks"),
    # Common ETFs typed as names
    "SP500": ("SPY", "SPDR S&P 500 ETF"),
    "S P 500": ("SPY", "SPDR S&P 500 ETF"),
    "SP 500": ("SPY", "SPDR S&P 500 ETF"),
    "NASDAQ": ("QQQ", "Invesco QQQ (Nasdaq-100)"),
    "NASDAQ 100": ("QQQ", "Invesco QQQ (Nasdaq-100)"),
}

# Reverse index: known tickers → display name (identity resolution).
_KNOWN_TICKERS: dict[str, str] = {t: n for (t, n) in _ALIASES.values()}

_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")


def _normalize(query: str) -> str:
    q = _NON_ALNUM.sub(" ", query.upper())
    words = [w for w in q.split() if w]
    # Strip corporate suffixes from the tail ("MARVELL TECHNOLOGY INC" → "MARVELL")
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    if words and words[0] == "THE":
        words = words[1:]
    return " ".join(words)


def resolve_ticker(query: str, allow_network: bool = True) -> dict | None:
    """Resolve free text to {"ticker", "name", "source"} or None.

    allow_network=False restricts to the offline alias map (used on the 404
    path so a throttled prod instance never adds another Yahoo call there).
    """
    if not query or not query.strip():
        return None
    q = _normalize(query)
    if not q:
        return None

    # Identity: already a known ticker (with . / - variants normalized to space)
    compact = q.replace(" ", "-")
    for candidate in (q, compact, q.replace(" ", ".")):
        if candidate in _KNOWN_TICKERS:
            return {"ticker": candidate, "name": _KNOWN_TICKERS[candidate],
                    "source": "alias"}

    if q in _ALIASES:
        ticker, name = _ALIASES[q]
        return {"ticker": ticker, "name": name, "source": "alias"}

    # Prefix match on aliases ("MARVEL" → MARVELL) — take the shortest key
    prefix_hits = sorted(k for k in _ALIASES if k.startswith(q) and len(q) >= 4)
    if prefix_hits:
        ticker, name = _ALIASES[prefix_hits[0]]
        return {"ticker": ticker, "name": name, "source": "alias_prefix"}

    if allow_network:
        return _search_yahoo(query.strip())
    return None


def _search_yahoo(query: str) -> dict | None:
    """yfinance Search fallback — cached 24h, rate-limit guarded."""
    cache_key = f"tkr:resolve:{query.upper()}"
    hit = cache_get(cache_key, 86400)
    if hit is not None:
        return hit or None  # cached "no match" is stored as {}

    from backend.services.data_fetcher import _yf_lock, _rl_breaker_active, _trip_rl_breaker, _is_rate_limit

    if _rl_breaker_active():
        return None
    try:
        import yfinance as yf
        with _yf_lock:
            quotes = yf.Search(query, max_results=8).quotes or []
    except Exception as e:
        if _is_rate_limit(e):
            _trip_rl_breaker()
        else:
            logger.warning("ticker search failed for %r: %s", query, e)
        return None

    best = None
    for item in quotes:
        symbol = item.get("symbol")
        if not symbol:
            continue
        qtype = item.get("quoteType", "")
        if qtype not in ("EQUITY", "ETF"):
            continue
        # Prefer plain US listings over foreign suffixed ones (e.g. "0M2J.L")
        if "." in symbol and best is not None:
            continue
        entry = {
            "ticker": symbol.upper(),
            "name": item.get("shortname") or item.get("longname") or symbol,
            "source": "yahoo_search",
        }
        if "." not in symbol:
            best = entry
            break
        best = best or entry

    cache_set(cache_key, best or {})
    return best
