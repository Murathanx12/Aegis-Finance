"""Murat's own point-in-time sheets, parsed rather than transcribed.

WHY A PARSER AND NOT A HAND-TYPED TABLE
=======================================

The two PDFs in `docs/conviction_replay/` are the only point-in-time record of
what Murat held, what he was watching but did not hold, and what he paid — dated
2025-11-07 and 2026-01-13, with sold-at annotations. Every number this session
reports about his record is derived from them, so a silent transcription slip
would propagate into the selection verdict with nothing to catch it. Parsing the
PDF text keeps the chain auditable: the raw text sits beside the PDFs in
`raw_text_*.txt` and this module is the only thing that reads it.

The sheets are the reason the central question is IDENTIFIED rather than a
story. They contain both the picks and the pool the picks came from, priced on
the same day. That makes "did his judgment add anything beyond the analyst
spreadsheet" a measurable quantity instead of an anecdote.

WHAT THE SHEETS ARE NOT
-----------------------
They are not a NAV series, not a transaction log, and carry no share counts or
cash. They cannot produce a portfolio return, and nothing here should be read as
one. They support exactly one thing: equal-weighted forward returns of named
sets, from a date both sets share.

Prices use European decimal commas ("0,80"), sometimes mixed with points in the
same table, and a few rating cells carry a stray letter ("4.4p"). All three are
handled and logged rather than silently coerced.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHEET_DIR = REPO_ROOT / "docs" / "conviction_replay"

#: The sheets, in the order they were written.
SHEETS = {
    "2025-11-07": SHEET_DIR / "raw_text_2025-11-07.txt",
    "2026-01-13": SHEET_DIR / "raw_text_2026-01-13.txt",
}

#: Tickers as written on the sheet -> the symbol that actually trades. Murat
#: typed these by hand from a terminal; two are transpositions. Every entry
#: here is a CORRECTION TO HIS SHEET and is listed so the correction is visible
#: rather than buried in a lookup that silently succeeds.
TICKER_FIXES = {
    "APMX": "AMPX",     # Amprius Technologies — transposed
}

#: Rows that are headers, section titles or page furniture rather than holdings.
_SKIP = re.compile(
    r"^(STOCK|my portfolio|My Watchlist|ww|=====|month|12|PRICE|Rating)", re.I)

#: A holding row: TICKER then two-to-four numeric-ish cells.
_ROW = re.compile(r"^([A-Z]{1,5})\b(.*)$")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _to_float(tok: str) -> float | None:
    """Parse a sheet cell. Commas are decimal separators, not thousands."""
    tok = tok.strip().rstrip("p")            # a stray 'p' appears on 3 ratings
    if not tok:
        return None
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


@dataclass
class Holding:
    """One row of one sheet."""
    ticker: str
    sheet_ticker: str
    price: float | None
    price_later: float | None       # the 13/01/2026 column, January sheet only
    analyst_target: float | None
    consensus_rating: float | None
    section: str                    # "portfolio" | "watchlist"
    sold_at: float | None = None
    sheet_date: str = ""

    @property
    def sheet_upside(self) -> float | None:
        """Upside as HIS sheet implied it — target over the price he recorded."""
        if not self.price or not self.analyst_target:
            return None
        return self.analyst_target / self.price - 1.0


@dataclass
class Sheet:
    date: str
    holdings: list[Holding] = field(default_factory=list)

    def section(self, name: str) -> list[Holding]:
        return [h for h in self.holdings if h.section == name]

    @property
    def portfolio(self) -> list[Holding]:
        return self.section("portfolio")

    @property
    def watchlist(self) -> list[Holding]:
        return self.section("watchlist")

    def non_picks(self) -> list[Holding]:
        """Watchlist names he did NOT hold on this sheet.

        The January sheet lists promoted names in BOTH sections; a name in both
        is a pick, and counting it as a non-pick would put the same security on
        both sides of the comparison and bias the answer toward zero.
        """
        held = {h.ticker for h in self.portfolio}
        return [h for h in self.watchlist if h.ticker not in held]


def _parse_lines(lines: list[str], sheet_date: str, n_price_cols: int) -> Sheet:
    sheet = Sheet(date=sheet_date)
    section = None
    pending_sold: float | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "portfolio" in low and "stock" not in low:
            section = "portfolio"
            continue
        if "watchlist" in low:
            section = "watchlist"
            continue
        if section is None or _SKIP.match(line):
            continue

        # "at 34.4)" — the continuation of a "(sold" annotation that the PDF
        # wrapped onto its own line. It may ONLY complete a row that actually
        # opened one: attaching it to whatever happened to be parsed last put
        # ALMS's exit price on DKNG, which is the kind of silent misattribution
        # that survives every test because nothing downstream can contradict it.
        cont = re.match(r"^at\s+([\d.,]+)\)", line)
        if cont:
            if pending_sold is not None and sheet.holdings:
                sheet.holdings[-1].sold_at = _to_float(cont.group(1))
            else:
                logger.warning("%s: orphan exit annotation %r — no row above it "
                               "opened a '(sold' marker; dropped", sheet_date, line)
            pending_sold = None
            continue

        m = _ROW.match(line)
        if not m:
            continue
        sheet_tkr, rest = m.group(1), m.group(2)
        # The annotation wraps, so `(sold` is usually alone on the row and the
        # price is what follows it. Strip ONLY the marker (and the exit price if
        # it did fit) — a greedy strip to the line end eats the price columns
        # and drops the row entirely, which is how three sold positions went
        # missing from the January portfolio on the first pass.
        sold_here = re.search(r"sold\s+at\s+([\d.,]+)", rest, re.I)
        pending_sold = (_to_float(sold_here.group(1)) if sold_here
                        else (0.0 if re.search(r"\(\s*sold\b", rest, re.I) else None))
        rest = re.sub(r"\(\s*sold\b(?:\s+at\s+[\d.,]+)?\)?", " ", rest, flags=re.I)
        nums = [_to_float(t) for t in _NUM.findall(rest)]
        nums = [n for n in nums if n is not None]
        if len(nums) < 2:
            logger.debug("%s: skipping unparsable row %r", sheet_date, line)
            continue

        if n_price_cols == 2:
            price = nums[0] if len(nums) > 0 else None
            later = nums[1] if len(nums) > 1 else None
            target = nums[2] if len(nums) > 2 else None
            rating = nums[3] if len(nums) > 3 else None
        else:
            price, later = nums[0], None
            target = nums[1] if len(nums) > 1 else None
            rating = nums[2] if len(nums) > 2 else None

        tkr = TICKER_FIXES.get(sheet_tkr, sheet_tkr)
        if any(h.ticker == tkr and h.section == section for h in sheet.holdings):
            # CHYM is typed twice in the November watchlist. Counting a name
            # twice weights it twice in an equal-weighted set.
            logger.warning("%s: %s appears twice in %s — keeping the first",
                           sheet_date, tkr, section)
            pending_sold = None
            continue

        sheet.holdings.append(Holding(
            ticker=tkr, sheet_ticker=sheet_tkr, price=price, price_later=later,
            analyst_target=target, consensus_rating=rating, section=section,
            sold_at=(pending_sold or None), sheet_date=sheet_date))
    return sheet


def load_sheet(date: str) -> Sheet:
    """Parse one sheet. `date` is a key of `SHEETS`."""
    path = SHEETS[date]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing — regenerate it from the PDF beside it; the "
            f"replay must never silently run on a partial sheet")
    text = path.read_text(encoding="utf-8")
    # the January sheet's tables carry two price columns; the November one, one.
    # The report prose that follows the January tables must not be parsed, so
    # everything from the report heading onward is dropped.
    cut = text.find("Investment Report")
    if cut > 0:
        text = text[:cut]
    n_price_cols = 2 if "13/01/2026" in text else 1
    sheet = _parse_lines(text.splitlines(), date, n_price_cols)
    if not sheet.portfolio or not sheet.watchlist:
        raise ValueError(
            f"{date}: parsed {len(sheet.portfolio)} portfolio and "
            f"{len(sheet.watchlist)} watchlist rows — a sheet with an empty "
            f"side cannot support the comparison it exists for")
    logger.info("%s: %d portfolio, %d watchlist, %d sold-at annotations",
                date, len(sheet.portfolio), len(sheet.watchlist),
                sum(1 for h in sheet.holdings if h.sold_at is not None))
    return sheet


def all_tickers() -> list[str]:
    """Every distinct traded symbol across both sheets."""
    out: set[str] = set()
    for d in SHEETS:
        try:
            out.update(h.ticker for h in load_sheet(d).holdings)
        except FileNotFoundError:
            logger.warning("%s sheet missing", d)
    return sorted(out)
