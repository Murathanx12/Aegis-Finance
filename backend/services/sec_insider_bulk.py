"""
SEC Insider Transactions bulk data sets (Forms 3/4/5) — the PIT parser.
=======================================================================

Lane I1 of `docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2.

WHAT THIS CORRECTS
------------------
`scripts/n4_event_table.py`'s docstring says, of Form 4: *"No Form 4 tape is
entitled or present. ABSENT, not fabricated."* That was true of WRDS and of
this repo's disk; it was NOT true of the world. The SEC publishes every Form
3/4/5 it has received since 2006 Q1 as a quarterly ZIP of tab-delimited
tables, free, no key, no entitlement:

    https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets

82 quarters were listed on 2026-09-07 (2006q1 .. 2026q2). This module is the
OFFLINE half — parsing, classification, receipts. The network half (download,
cursor, resume) is `scripts/sec_insider_bulk_load.py`. Nothing here touches
the network, so every function below is unit-testable in the fast suite.

THE PIT RULE, AND ITS HONEST LIMIT
----------------------------------
`observed_at_utc` is when the row became AVAILABLE. It is **never** derived
from `TRANS_DATE` — the transaction happens up to two business days (and, on
Forms 5, up to 45 days after fiscal year end) before anyone outside the issuer
can see it.

The bulk `SUBMISSION.tsv` carries `FILING_DATE` and **no acceptance
timestamp** (verified on 2006q1 / 2013q2 / 2023q2 / 2025q1 — 13 columns before
2023q2, 14 after, none of them an acceptance time; the Financial Statement
Data Sets' `accepted` field has no counterpart here). So the availability
bound this module can defend from the bulk files alone is:

    observed_at_utc      = FILING_DATE at 22:00 America/New_York, in UTC
    observed_at_precision= "date"
    observed_at_basis    = "FILING_DATE_EOD_CONSERVATIVE"

22:00 ET is the close of EDGAR's filing window; a Form 4 accepted after 17:30
ET is disseminated the NEXT business day, so end-of-filing-day is the latest
moment the filing can be assumed public, and a consumer that wants to trade on
it must use the NEXT session's open. `next_tradable_session_bound()` states
that explicitly rather than leaving it to a caller's memory.

A true acceptance timestamp EXISTS per accession at
`data.sec.gov/submissions/CIK##########.json` (`acceptanceDateTime`) and in
each filing's `-index.json`; that is one HTTP request per issuer or per
filing, which is a separate job. The column `acceptance_datetime_utc` is
carried NULL by this parser and `observed_at_basis` says so on every row —
an absence that is declared, not a guess wearing a timestamp.

WHAT A ROW IS CLASSIFIED AS
---------------------------
`TRANS_CODE` (SEC Form 345 code table) is mapped to a coarse `trans_class` by
`TRANS_CODE_MAP`; `is_open_market_purchase` is the one flag the
Cohen-Malloy-Pomorski literature runs on and it is deliberately narrow:

    code 'P'  AND  acquired/disposed 'A'  AND  the non-derivative table
    AND  NOT a 10b5-1 plan trade (where the filing says).

`plan_10b5_1` is `YES` / `NO` / `UNKNOWN` — never a silent False. The
`AFF10B5ONE` checkbox only exists from 2023 Q2 (the SEC's Dec-2022 rule
amendment); before that the only signal is the filer's own footnote text, so
`plan_10b5_1_source` records which of the two, or `ABSENT`, produced the value.

ROUTINE vs OPPORTUNISTIC (Cohen-Malloy-Pomorski 2012)
-----------------------------------------------------
An insider who bought in the SAME CALENDAR MONTH in each of the three
strictly-prior years is ROUTINE; an insider with purchases in each of the
three prior years but no such month pattern is OPPORTUNISTIC; anyone without
three prior years of purchases is UNCLASSIFIABLE and is dropped, never
defaulted to opportunistic. `classify_routine_opportunistic` reproduces
`backend.services.cmp_insider.classify_buy` exactly (pinned by test) so the
bulk tape and the live scorer cannot drift apart.

CMP's 82 bp/month value-weighted long-short (1989-2007) is the PRIOR that
motivates carrying the split. It is not a claim of this repo, and this module
deliberately builds NO book and computes NO return.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- constants

#: SEC fair-access: a descriptive User-Agent with a contact, and <=10 req/s.
#: A 403 from omitting this is the failure mode the collector post-mortem
#: (FRAGILITY_RESEARCH_2026-06-14) already paid for once.
SEC_USER_AGENT = "AEGIS Research mrthnabdullaev@gmail.com"

INDEX_URL = ("https://www.sec.gov/data-research/sec-markets-data/"
             "insider-transactions-data-sets")

#: The ZIP path prefix moved once (2026q2 is served from
#: /files/datastandardsinnovation/...), so the loader SCRAPES the index page
#: and only falls back to this pattern. Hard-coding it alone would have
#: silently skipped the newest quarter.
ZIP_URL_PATTERN = ("https://www.sec.gov/files/structureddata/data/"
                   "insider-transactions-data-sets/{quarter}_form345.zip")

FIRST_QUARTER = "2006q1"

#: The tables this parser reads out of each quarterly ZIP.
SUBMISSION_TSV = "SUBMISSION.tsv"
REPORTINGOWNER_TSV = "REPORTINGOWNER.tsv"
NONDERIV_TRANS_TSV = "NONDERIV_TRANS.tsv"
DERIV_TRANS_TSV = "DERIV_TRANS.tsv"
FOOTNOTES_TSV = "FOOTNOTES.tsv"

OBSERVED_AT_BASIS = "FILING_DATE_EOD_CONSERVATIVE"
#: 22:00 America/New_York == 02:00 UTC next day (EDT) / 03:00 UTC next day
#: (EST). Rather than depend on a tz database at parse time we take the LATER
#: of the two (03:00 UTC on filing_date + 1 day), which can only ever be
#: conservative — it never claims a row was visible earlier than it was.
OBSERVED_AT_UTC_OFFSET = timedelta(hours=27)

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


# --------------------------------------------------- transaction code table

#: SEC Form 345 transaction codes -> (class, human label).
#: Source: the "Explanation of Responses" code table on Forms 4/5 and the
#: FORM_345_readme.htm shipped inside every quarterly ZIP.
TRANS_CODE_MAP: dict[str, tuple[str, str]] = {
    # -- General transaction codes -------------------------------------
    "P": ("OPEN_MARKET_PURCHASE", "Open market or private purchase"),
    "S": ("OPEN_MARKET_SALE", "Open market or private sale"),
    "V": ("VOLUNTARY_EARLY_REPORT", "Transaction voluntarily reported earlier than required"),
    # -- Rule 16b-3 transaction codes ----------------------------------
    "A": ("GRANT_AWARD", "Grant, award or other acquisition under Rule 16b-3(d)"),
    "D": ("DISPOSITION_TO_ISSUER", "Disposition to the issuer under Rule 16b-3(e)"),
    "F": ("TAX_OR_EXERCISE_WITHHOLDING",
          "Payment of exercise price or tax liability by delivering/withholding securities"),
    "I": ("PLAN_DISCRETIONARY", "Discretionary transaction under Rule 16b-3(f) (benefit plan)"),
    "M": ("OPTION_EXERCISE", "Exercise/conversion of derivative security exempt under 16b-3"),
    # -- Derivative securities codes -----------------------------------
    "C": ("DERIVATIVE_CONVERSION", "Conversion of derivative security"),
    "E": ("DERIVATIVE_EXPIRATION", "Expiration of short derivative position"),
    "H": ("DERIVATIVE_EXPIRATION",
          "Expiration (or cancellation) of long derivative position with value received"),
    "O": ("OPTION_EXERCISE", "Exercise of out-of-the-money derivative security"),
    "X": ("OPTION_EXERCISE", "Exercise of in-the-money or at-the-money derivative security"),
    # -- Other exempt / small acquisition codes ------------------------
    "G": ("GIFT", "Bona fide gift"),
    "L": ("SMALL_ACQUISITION", "Small acquisition under Rule 16a-6"),
    "W": ("INHERITANCE", "Acquisition or disposition by will or the laws of descent"),
    "Z": ("VOTING_TRUST", "Deposit into or withdrawal from voting trust"),
    # -- Other transaction codes ---------------------------------------
    "J": ("OTHER", "Other acquisition or disposition (footnote required)"),
    "K": ("EQUITY_SWAP", "Transaction in equity swap or instrument with similar characteristics"),
    "U": ("TENDER", "Disposition pursuant to a tender of shares in a change of control"),
}

#: The ONLY class the opportunistic-buy literature treats as a discretionary
#: open-market purchase. Everything else — grants (A), option exercises
#: (M/X/O), tax withholding (F), gifts (G), plan-discretionary (I), swaps (K)
#: — is excluded, because none of them is a decision to pay cash for stock.
DISCRETIONARY_PURCHASE_CLASS = "OPEN_MARKET_PURCHASE"
DISCRETIONARY_SALE_CLASS = "OPEN_MARKET_SALE"

UNKNOWN_CODE_CLASS = "UNKNOWN_CODE"

#: 10b5-1 plan values.
PLAN_YES, PLAN_NO, PLAN_UNKNOWN = "YES", "NO", "UNKNOWN"
PLAN_SOURCE_CHECKBOX = "AFF10B5ONE"      # 2023q2 onward
PLAN_SOURCE_FOOTNOTE = "FOOTNOTE_TEXT"   # inferred from the filer's own prose
PLAN_SOURCE_ABSENT = "ABSENT"            # neither available -> PLAN_UNKNOWN

_FOOTNOTE_10B5_1 = re.compile(r"10\s*b5\s*-?\s*1", re.IGNORECASE)

#: Link outcomes. An unlinked row is a COUNTED REFUSAL with a reason, never a
#: dropped row (CLAUDE.md: "a check that did not run is not a check that
#: passed; a refusal is a finding").
LINK_OK = "crsp_stocknames_interval"
LINK_NO_SYMBOL = "REFUSED_NO_SYMBOL"
LINK_NO_VINTAGE = "REFUSED_OUTSIDE_CRSP_VINTAGE"
LINK_NO_MATCH = "REFUSED_TICKER_NOT_IN_CRSP"
LINK_AMBIGUOUS = "REFUSED_AMBIGUOUS_TICKER"

ROUTINE, OPPORTUNISTIC, UNCLASSIFIABLE = "routine", "opportunistic", "unclassifiable"


class SecInsiderBulkError(RuntimeError):
    """A refusal from this module. Raised, never swallowed — a 403 or a
    truncated ZIP that is silently absorbed is the house failure mode."""


# ------------------------------------------------------------- date helpers

def parse_sec_date(value: Any) -> date | None:
    """'31-MAR-2025' -> date(2025, 3, 31). Empty/malformed -> None.

    The bulk files use DD-MON-YYYY throughout (all four probed vintages).
    ISO is also accepted so a caller can feed a normalised value back in.
    """
    if value is None:
        return None
    # pandas NaT passes `isinstance(x, datetime)` (it subclasses it) and then
    # yields FLOAT nan for .year/.month, which blew up a f"{m:02d}" three
    # layers down with "Unknown format code 'd' for object of type 'float'".
    # A missing date must become None here, at the boundary, not a nan that
    # travels. Same for float nan out of a parquet column.
    if value != value:  # noqa: PLR0124 — the NaN/NaT identity test
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        d = value.date()
        return d if isinstance(d, date) else None
    s = str(value).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    parts = s.split("-")
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = _MONTHS[parts[1].strip().upper()[:3]]
        year = int(parts[2][:4])
        return date(year, month, day)
    except (ValueError, KeyError):
        return None


def observed_at_utc(filing_date: date | None) -> datetime | None:
    """The PIT availability bound for a filing: end of the FILING day, in UTC.

    NEVER call this with a transaction date. `assert_pit_sane` exists to make
    that mistake loud rather than plausible.
    """
    if filing_date is None:
        return None
    return (datetime(filing_date.year, filing_date.month, filing_date.day,
                     tzinfo=timezone.utc) + OBSERVED_AT_UTC_OFFSET)


def next_tradable_session_bound(filing_date: date | None) -> date | None:
    """The first CALENDAR day on which a consumer may act on the filing.

    `observed_at_utc` is end-of-filing-day, so the earliest tradable moment is
    the next session's open. This returns the next calendar day (weekend /
    holiday handling belongs to the caller's own trading calendar); a book
    that uses the filing date itself as its entry date is trading on
    information that may not have been public until 22:00 that evening.
    """
    if filing_date is None:
        return None
    return filing_date + timedelta(days=1)


#: A quarter with more future-dated transactions than this is a PARSING bug
#: (a month/day swap, say), not the SEC's own long tail. Measured on 2025q1:
#: 20 of 150,789 rows = 0.013%.
MAX_FUTURE_DATED_FRACTION = 0.01
#: ...and only once there are enough rows for a fraction to mean anything. On
#: a 6-row fixture "1 in 6" is 17% and says nothing; a real quarter carries
#: ~150,000 rows. A ratio floor must be checked against its own denominator.
MIN_ROWS_FOR_FRACTION_CHECK = 1_000


def assert_pit_sane(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Refuse a table whose PIT bound could permit a lookahead join.

    FATAL (raises):
      1. `observed_at_utc` is not EXACTLY the `filing_date`-derived bound.
         This is the clause that goes red on a lookahead join: build the
         column from `trans_date` — the natural mistake, because `trans_date`
         is the column that *feels* like the event — and every row fails, at
         once, with the offending pair printed.
      2. For a normally-ordered row (trans_date <= filing_date),
         `observed_at_utc` is not strictly after the end of the transaction
         day.
      3. More than MAX_FUTURE_DATED_FRACTION of rows are future-dated, in a
         table big enough (MIN_ROWS_FOR_FRACTION_CHECK) for the fraction to
         mean anything.

    COUNTED, NOT FATAL: individual rows whose `trans_date` is AFTER their
    `filing_date`. These exist in the real tape — 20 of 150,789 rows in
    2025q1, e.g. accession 0001137547-25-000041 filed 2025-03-20 for a
    2025-10-23 transaction. They are filer errors or pre-announced scheduled
    trades, and they are NOT a PIT hazard: the filing is still the moment the
    row became public, and it is EARLIER than the transaction, not later. A
    guard that died on them would have made the whole loader unrunnable for a
    hazard that points the safe way; a guard that hid them would have lost a
    real data fact. They are returned as `future_dated_transactions` and
    belong in the coverage receipt.

    Returns a summary dict; raises SecInsiderBulkError on any FATAL finding.
    """
    checked = violations = future_dated = 0
    examples: list[dict] = []
    future_examples: list[dict] = []
    for r in rows:
        fd = parse_sec_date(r.get("filing_date"))
        td = parse_sec_date(r.get("trans_date"))
        obs = r.get("observed_at_utc")
        if fd is None or obs is None:
            continue
        if not isinstance(obs, datetime):
            obs = datetime.fromisoformat(str(obs))
        if obs.tzinfo is None:
            obs = obs.replace(tzinfo=timezone.utc)
        checked += 1
        bad = []
        if observed_at_utc(fd) != obs:
            bad.append("observed_at_utc is not the filing_date-derived bound")
        if td is not None and td > fd:
            future_dated += 1
            if len(future_examples) < 5:
                future_examples.append({"accession": r.get("accession"),
                                        "trans_date": str(td), "filing_date": str(fd)})
        elif td is not None:
            end_of_trans_day = datetime(td.year, td.month, td.day,
                                        tzinfo=timezone.utc) + timedelta(days=1)
            if obs < end_of_trans_day:
                bad.append("observed_at_utc is not strictly after the transaction day")
        if bad:
            violations += 1
            if len(examples) < 5:
                examples.append({"accession": r.get("accession"), "reasons": bad,
                                 "trans_date": str(td), "filing_date": str(fd),
                                 "observed_at_utc": str(obs)})
    if violations:
        raise SecInsiderBulkError(
            f"PIT violation on {violations}/{checked} rows: {examples}")
    if (checked >= MIN_ROWS_FOR_FRACTION_CHECK
            and future_dated / checked > MAX_FUTURE_DATED_FRACTION):
        raise SecInsiderBulkError(
            f"{future_dated}/{checked} rows are future-dated "
            f"(> {MAX_FUTURE_DATED_FRACTION:.1%}) — that is a parser bug, not "
            f"the SEC's tail: {future_examples}")
    return {"rows_checked": checked, "violations": 0,
            "future_dated_transactions": future_dated,
            "future_dated_examples": future_examples}


# --------------------------------------------------------- field normalisers

def normalise_flag(value: Any) -> bool | None:
    """The bulk files encode booleans FOUR ways in the same column
    (`AFF10B5ONE` in 2025q1: '0', '1', 'true', 'false', ''). A parser that
    only knew '0'/'1' would read 'false' as truthy garbage."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"1", "true", "y", "yes"}:
        return True
    if s in {"0", "false", "n", "no"}:
        return False
    return None


def normalise_cik(value: Any) -> str | None:
    """'0001840502' -> '1840502'. Matches cmp_insider's key convention so the
    bulk history and the live scorer share one keyspace."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s.lstrip("0") or s


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def classify_trans_code(code: Any) -> tuple[str, str]:
    """(trans_class, label). An unmapped code is UNKNOWN_CODE, not dropped —
    a new SEC code must show up in the receipt, not vanish."""
    c = (str(code) if code is not None else "").strip().upper()
    if c in TRANS_CODE_MAP:
        return TRANS_CODE_MAP[c]
    return (UNKNOWN_CODE_CLASS, f"Unmapped SEC transaction code {c!r}")


def resolve_10b5_1(aff_checkbox: Any, footnote_hit: bool | None) -> tuple[str, str]:
    """(plan_10b5_1, plan_10b5_1_source).

    The checkbox wins where it exists (2023q2 ->). Before that the filer's own
    footnote text is the only evidence, and it can only ever say YES — the
    absence of the phrase is not evidence of absence, so a footnote miss on a
    pre-2023 filing stays UNKNOWN.
    """
    flag = normalise_flag(aff_checkbox)
    if flag is True:
        return PLAN_YES, PLAN_SOURCE_CHECKBOX
    if flag is False:
        return PLAN_NO, PLAN_SOURCE_CHECKBOX
    if footnote_hit:
        return PLAN_YES, PLAN_SOURCE_FOOTNOTE
    return PLAN_UNKNOWN, PLAN_SOURCE_ABSENT


def is_discretionary_open_market_purchase(row: Mapping[str, Any]) -> bool:
    """The narrow flag. Every clause is load-bearing:

      table == NONDERIV      a derivative 'P' is buying an option, not stock
      trans_class == OPEN_MARKET_PURCHASE   code 'P'
      acquired_disposed == 'A'              acquired, not disposed
      plan_10b5_1 != YES     a scheduled plan trade carries no information
      shares > 0             a zero-share row is a footnote artefact
    """
    return bool(
        row.get("table") == "NONDERIV"
        and row.get("trans_class") == DISCRETIONARY_PURCHASE_CLASS
        and str(row.get("acquired_disposed") or "").upper() == "A"
        and row.get("plan_10b5_1") != PLAN_YES
        and (row.get("shares") or 0) > 0
    )


def is_discretionary_open_market_sale(row: Mapping[str, Any]) -> bool:
    """The sale mirror. Kept beside the purchase flag so a book that wants
    winner-vs-matched-loser (CLAUDE.md rule 4) has the loser side typed."""
    return bool(
        row.get("table") == "NONDERIV"
        and row.get("trans_class") == DISCRETIONARY_SALE_CLASS
        and str(row.get("acquired_disposed") or "").upper() == "D"
        and row.get("plan_10b5_1") != PLAN_YES
        and (row.get("shares") or 0) > 0
    )


# ---------------------------------------------------------- the ZIP parser

def _read_tsv(zf: zipfile.ZipFile, name: str) -> Iterator[dict]:
    """Stream one tab-delimited member. Missing member -> refusal, not [].

    A quarter whose NONDERIV_TRANS.tsv silently went missing would otherwise
    write a green, empty receipt.
    """
    if name not in {i.filename for i in zf.infolist()}:
        raise SecInsiderBulkError(f"{name} missing from {zf.filename!r}")
    with zf.open(name) as fh:
        reader = csv.DictReader(
            io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""),
            delimiter="\t")
        for row in reader:
            yield row


def _footnote_10b5_1_accessions(zf: zipfile.ZipFile) -> set[str]:
    """Accessions whose footnote text mentions a Rule 10b5-1 plan.

    FOOTNOTES.tsv is the largest member (41 MB in 2025q1) and is scanned as
    raw text rather than parsed — we only need the accession of any line that
    mentions the rule.
    """
    hits: set[str] = set()
    try:
        for row in _read_tsv(zf, FOOTNOTES_TSV):
            acc = (row.get("ACCESSION_NUMBER") or "").strip()
            if not acc or acc in hits:
                continue
            blob = " ".join(v for k, v in row.items()
                            if k and k != "ACCESSION_NUMBER" and isinstance(v, str))
            if _FOOTNOTE_10B5_1.search(blob):
                hits.add(acc)
    except SecInsiderBulkError:
        logger.warning("FOOTNOTES.tsv absent from %s — 10b5-1 stays UNKNOWN "
                       "on pre-2023 rows of this quarter", zf.filename)
    return hits


_EMPTY_OWNER = {"owner_cik": None, "owner_name": None, "owner_relationship": None,
                "is_director": False, "is_officer": False, "is_tenpercent": False,
                "is_other_insider": False, "officer_title": None}


def parse_quarter_zip(path: str | Path, *, quarter: str | None = None,
                      scan_footnotes: bool = True) -> tuple[list[dict], dict]:
    """(rows, parse_receipt) for one quarterly ZIP.

    Offline: takes a path, opens no socket. `rows` are transaction-level —
    one row per (accession, reporting owner, transaction). A filing with two
    reporting owners and three transactions produces six rows, which is what
    the ownership tables mean; the receipt reports the fan-out so a reader
    cannot mistake row count for filing count.
    """
    path = Path(path)
    quarter = quarter or path.stem.split("_")[0]
    with zipfile.ZipFile(path) as zf:
        members = {i.filename: i.file_size for i in zf.infolist()}

        subs: dict[str, dict] = {}
        aff_raw: dict[str, Any] = {}
        for r in _read_tsv(zf, SUBMISSION_TSV):
            acc = (r.get("ACCESSION_NUMBER") or "").strip()
            if not acc:
                continue
            fd = parse_sec_date(r.get("FILING_DATE"))
            doc = (r.get("DOCUMENT_TYPE") or "").strip()
            aff_raw[acc] = r.get("AFF10B5ONE")
            plan, plan_src = resolve_10b5_1(r.get("AFF10B5ONE"), False)
            subs[acc] = {
                "accession": acc,
                "form_type": doc or None,
                "is_amendment": doc.endswith("/A"),
                "issuer_cik": normalise_cik(r.get("ISSUERCIK")),
                "issuer_name": (r.get("ISSUERNAME") or "").strip() or None,
                "symbol": (r.get("ISSUERTRADINGSYMBOL") or "").strip().upper() or None,
                "filing_date": fd,
                "period_of_report": parse_sec_date(r.get("PERIOD_OF_REPORT")),
                "plan_10b5_1": plan,
                "plan_10b5_1_source": plan_src,
                "observed_at_utc": observed_at_utc(fd),
                "observed_at_precision": "date",
                "observed_at_basis": OBSERVED_AT_BASIS,
                "acceptance_datetime_utc": None,
            }

        # The AFF10B5ONE checkbox exists only from 2023q2 (SEC rule amendment
        # of Dec 2022). Scanning 41 MB of FOOTNOTES.tsv is pointless where the
        # checkbox already answered for every filing, so the scan is LAZY: it
        # runs only if at least one submission is still UNKNOWN. Skipping it
        # unconditionally would leave the whole 2006-2023 tape blind to plan
        # trades; running it unconditionally would cost ~0.4 s x 82 for nothing.
        unknown_accs = {a for a, s in subs.items() if s["plan_10b5_1"] == PLAN_UNKNOWN}
        footnote_hits: set[str] = set()
        if scan_footnotes and unknown_accs:
            footnote_hits = _footnote_10b5_1_accessions(zf) & unknown_accs
            for acc in footnote_hits:
                plan, plan_src = resolve_10b5_1(aff_raw.get(acc), True)
                subs[acc]["plan_10b5_1"] = plan
                subs[acc]["plan_10b5_1_source"] = plan_src

        owners: dict[str, list[dict]] = defaultdict(list)
        for r in _read_tsv(zf, REPORTINGOWNER_TSV):
            acc = (r.get("ACCESSION_NUMBER") or "").strip()
            if not acc:
                continue
            rel = (r.get("RPTOWNER_RELATIONSHIP") or "")
            rel_u = rel.upper()
            owners[acc].append({
                "owner_cik": normalise_cik(r.get("RPTOWNERCIK")),
                "owner_name": (r.get("RPTOWNERNAME") or "").strip() or None,
                "owner_relationship": rel.strip() or None,
                "is_director": "DIRECTOR" in rel_u,
                "is_officer": "OFFICER" in rel_u,
                "is_tenpercent": "TENPERCENT" in rel_u,
                "is_other_insider": "OTHER" in rel_u,
                "officer_title": (r.get("RPTOWNER_TITLE") or "").strip() or None,
            })

        rows: list[dict] = []
        code_counts: dict[str, int] = defaultdict(int)
        orphan_trans = 0
        no_owner_trans = 0

        for table, member in (("NONDERIV", NONDERIV_TRANS_TSV),
                              ("DERIV", DERIV_TRANS_TSV)):
            for r in _read_tsv(zf, member):
                acc = (r.get("ACCESSION_NUMBER") or "").strip()
                sub = subs.get(acc)
                if sub is None:
                    orphan_trans += 1
                    continue
                code = (r.get("TRANS_CODE") or "").strip().upper()
                code_counts[code or "(blank)"] += 1
                trans_class, _label = classify_trans_code(code)
                shares = _to_float(r.get("TRANS_SHARES"))
                price = _to_float(r.get("TRANS_PRICEPERSHARE"))
                base = {
                    **sub,
                    "quarter": quarter,
                    "table": table,
                    "trans_sk": (r.get("NONDERIV_TRANS_SK")
                                 or r.get("DERIV_TRANS_SK") or "").strip() or None,
                    "security_title": (r.get("SECURITY_TITLE") or "").strip() or None,
                    "trans_date": parse_sec_date(r.get("TRANS_DATE")),
                    "deemed_execution_date": parse_sec_date(r.get("DEEMED_EXECUTION_DATE")),
                    "trans_form_type": (r.get("TRANS_FORM_TYPE") or "").strip() or None,
                    "trans_code": code or None,
                    "trans_class": trans_class,
                    "acquired_disposed": (r.get("TRANS_ACQUIRED_DISP_CD") or "").strip().upper() or None,
                    "shares": shares,
                    "price_per_share": price,
                    "dollar_value": (shares * price) if (shares is not None and price) else None,
                    "shares_owned_following": _to_float(r.get("SHRS_OWND_FOLWNG_TRANS")),
                    "direct_indirect": (r.get("DIRECT_INDIRECT_OWNERSHIP") or "").strip().upper() or None,
                    "trans_timeliness": (r.get("TRANS_TIMELINESS") or "").strip().upper() or None,
                }
                owner_list = owners.get(acc)
                if not owner_list:
                    no_owner_trans += 1
                    owner_list = [_EMPTY_OWNER]
                for own in owner_list:
                    row = {**base, **own}
                    row["is_open_market_purchase"] = is_discretionary_open_market_purchase(row)
                    row["is_open_market_sale"] = is_discretionary_open_market_sale(row)
                    rows.append(row)

    filing_dates = [s["filing_date"] for s in subs.values() if s["filing_date"]]
    receipt = {
        "quarter": quarter,
        "zip_path": str(path),
        "zip_bytes": path.stat().st_size if path.exists() else None,
        "zip_members": members,
        "submissions": len(subs),
        "reporting_owner_rows": sum(len(v) for v in owners.values()),
        "rows": len(rows),
        "orphan_transactions_no_submission": orphan_trans,
        "transactions_with_no_reporting_owner": no_owner_trans,
        "trans_code_counts": dict(sorted(code_counts.items(), key=lambda kv: -kv[1])),
        "unknown_codes": sorted({c for c in code_counts
                                 if c != "(blank)" and c not in TRANS_CODE_MAP}),
        "filing_date_min": str(min(filing_dates)) if filing_dates else None,
        "filing_date_max": str(max(filing_dates)) if filing_dates else None,
        "distinct_issuers": len({s["issuer_cik"] for s in subs.values() if s["issuer_cik"]}),
        "distinct_insiders": len({r["owner_cik"] for r in rows if r.get("owner_cik")}),
        "open_market_purchases": sum(1 for r in rows if r["is_open_market_purchase"]),
        "open_market_sales": sum(1 for r in rows if r["is_open_market_sale"]),
        "plan_10b5_1_counts": count_by(rows, "plan_10b5_1"),
        "plan_10b5_1_source_counts": count_by(rows, "plan_10b5_1_source"),
        "trans_class_counts": count_by(rows, "trans_class"),
        "observed_at_basis": OBSERVED_AT_BASIS,
        "footnote_10b5_1_accessions": len(footnote_hits),
        "footnotes_scanned": bool(scan_footnotes),
    }
    return rows, receipt


def count_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[str(r.get(key))] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ------------------------------------------- routine / opportunistic (CMP)

def build_purchase_history(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict]:
    """{owner_cik: {"years": sorted[int], "year_months": sorted[str]}} over
    DISCRETIONARY OPEN-MARKET PURCHASES only.

    Keyed on the TRANSACTION month (CMP's own definition: the pattern is when
    the insider trades, not when the paperwork lands). This is a HISTORY, not
    a signal — `classify_routine_opportunistic` only ever consults strictly
    prior years, which is what makes the classification point-in-time: a
    purchase made in year y-1 was filed within two business days of itself and
    so was public long before any year-y purchase is classified.
    """
    years: dict[str, set[int]] = defaultdict(set)
    yms: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if not r.get("is_open_market_purchase"):
            continue
        cik = normalise_cik(r.get("owner_cik"))
        td = parse_sec_date(r.get("trans_date"))
        if not cik or td is None:
            continue
        years[cik].add(td.year)
        yms[cik].add(f"{td.year}-{td.month:02d}")
    return {cik: {"years": sorted(years[cik]), "year_months": sorted(yms[cik])}
            for cik in years}


def classify_routine_opportunistic(cik: Any, trans_date: Any,
                                   history: Mapping[str, Mapping[str, Any]]) -> str:
    """'routine' | 'opportunistic' | 'unclassifiable'.

    Identical in behaviour to `cmp_insider.classify_buy` (pinned by test):
    three strictly-prior years of purchases are required, and the same
    calendar month in all three makes the insider ROUTINE. No history ->
    UNCLASSIFIABLE, never defaulted to opportunistic.
    """
    key = normalise_cik(cik)
    if not key:
        return UNCLASSIFIABLE
    hist = history.get(key)
    if not hist:
        return UNCLASSIFIABLE
    td = parse_sec_date(trans_date)
    if td is None:
        return UNCLASSIFIABLE
    years = set(hist.get("years") or [])
    yms = set(hist.get("year_months") or [])
    if not all((td.year - k) in years for k in (1, 2, 3)):
        return UNCLASSIFIABLE
    if all(f"{td.year - k}-{td.month:02d}" in yms for k in (1, 2, 3)):
        return ROUTINE
    return OPPORTUNISTIC


# ---------------------------------------------------------- CRSP permno link

def build_crsp_ticker_index(stocknames) -> dict[str, list[tuple[date, date, int, int]]]:
    """{TICKER: [(namedt, nameenddt, permno, shrcd), ...]} from a CRSP
    stocknames frame. Pure; takes an already-loaded DataFrame so the fast
    suite can drive it with three rows."""
    index: dict[str, list[tuple[date, date, int, int]]] = defaultdict(list)
    end_col = "nameenddt" if "nameenddt" in stocknames.columns else "nameendt"
    for tkr, start, end, permno, shrcd in zip(
            stocknames["ticker"], stocknames["namedt"], stocknames[end_col],
            stocknames["permno"], stocknames["shrcd"]):
        s = parse_sec_date(start)
        e = parse_sec_date(end)
        if not tkr or s is None or e is None:
            continue
        try:
            index[str(tkr).strip().upper()].append(
                (s, e, int(permno), int(shrcd) if shrcd == shrcd else -1))
        except (TypeError, ValueError):
            continue
    return dict(index)


def link_permno(symbol: Any, on: date | None,
                crsp_index: Mapping[str, Sequence[tuple[date, date, int, int]]],
                vintage_end: date | None) -> tuple[int | None, str]:
    """(permno, link_method_or_refusal_reason).

    An unlinked row is a COUNTED REFUSAL carrying WHICH refusal, so the
    coverage receipt can separate "our linker is bad" from "CRSP does not
    reach this year" — the entitled vintage ends 2024-12-31, so every 2025-26
    row is REFUSED_OUTSIDE_CRSP_VINTAGE and is NOT evidence of a broken
    linker. The CIK -> ticker leg needs no external map: the SEC's own
    SUBMISSION table carries `ISSUERTRADINGSYMBOL` as of the filing, which is
    point-in-time by construction and strictly better than today's
    company_tickers.json (a ticker is a dated alias — SECURITY-IDENTITY-LAYER-1).
    """
    sym = str(symbol).strip().upper() if symbol else ""
    if not sym or on is None:
        return None, LINK_NO_SYMBOL
    if vintage_end is not None and on > vintage_end:
        return None, LINK_NO_VINTAGE
    hits = [(p, shrcd) for (start, end, p, shrcd) in crsp_index.get(sym, ())
            if start <= on <= end]
    if not hits:
        return None, LINK_NO_MATCH
    permnos = {p for p, _ in hits}
    if len(permnos) == 1:
        return int(next(iter(permnos))), LINK_OK
    common = {p for p, shrcd in hits if shrcd in (10, 11)}
    if len(common) == 1:
        return int(next(iter(common))), LINK_OK
    return None, LINK_AMBIGUOUS


# ------------------------------------------------------- fabrication guard

#: Every field a Form 4 row may carry that is FACT FROM THE FILING. Nothing
#: outside this set may be invented by us; the derived fields are enumerated
#: separately so a reviewer can see, in one place, exactly which columns are
#: ours and which are the SEC's.
SOURCE_FIELDS = frozenset({
    "accession", "form_type", "issuer_cik", "issuer_name", "symbol",
    "filing_date", "period_of_report", "owner_cik", "owner_name",
    "owner_relationship", "officer_title", "table", "trans_sk",
    "security_title", "trans_date", "deemed_execution_date", "trans_form_type",
    "trans_code", "acquired_disposed", "shares", "price_per_share",
    "shares_owned_following", "direct_indirect", "trans_timeliness",
})

DERIVED_FIELDS = frozenset({
    "quarter", "is_amendment", "is_director", "is_officer", "is_tenpercent",
    "is_other_insider", "trans_class", "dollar_value", "plan_10b5_1",
    "plan_10b5_1_source", "observed_at_utc", "observed_at_precision",
    "observed_at_basis", "acceptance_datetime_utc",
    "is_open_market_purchase", "is_open_market_sale",
    # attached by the loader's link pass
    "permno", "permno_link_method", "cmp_class",
})


def assert_not_fabricated(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Refuse any row that could not have come from a real SEC filing.

    A Form 4 row must carry an accession number in EDGAR's own format, must
    not invent a column outside SOURCE_FIELDS | DERIVED_FIELDS, must carry a
    filing date if it carries a transaction code, and must not carry a
    `dollar_value` that its own shares x price does not produce. Those four
    are FATAL — they can only be OUR mistake.

    A transaction date decades from its own filing is the SEC's typo, not our
    invention (2025q1 carries two: 2035-01-10 and 2028-01-01), so it is
    COUNTED as `implausible_dates` and reported, never raised. Raises on any
    fatal finding; returns a summary.
    """
    acc_re = re.compile(r"^\d{10}-\d{2}-\d{6}$")
    allowed = SOURCE_FIELDS | DERIVED_FIELDS
    problems: list[str] = []
    implausible: list[str] = []
    for i, r in enumerate(rows):
        extra = set(r.keys()) - allowed
        if extra:
            problems.append(f"row {i}: columns outside the declared schema: {sorted(extra)}")
        acc = str(r.get("accession") or "")
        if not acc_re.match(acc):
            problems.append(f"row {i}: accession {acc!r} is not an EDGAR accession number")
        fd = parse_sec_date(r.get("filing_date"))
        if r.get("trans_code") and fd is None:
            problems.append(f"row {i}: a transaction with no filing_date cannot be PIT-stamped")
        td = parse_sec_date(r.get("trans_date"))
        # NOT `td > fd`: the real tape carries a handful of future-dated
        # transactions per quarter (see assert_pit_sane) and they are the
        # SEC's, not ours. What no real filing can be is decades away from
        # its own accession — that is a typo or an invention.
        if fd is not None and td is not None and not (
                fd - timedelta(days=365 * 20) <= td <= fd + timedelta(days=730)):
            if len(implausible) < 10:
                implausible.append(
                    f"{r.get('accession')}: trans_date {td} vs filing_date {fd}")
        sh, px, dv = r.get("shares"), r.get("price_per_share"), r.get("dollar_value")
        if dv is not None and sh is not None and px:
            if abs(float(dv) - float(sh) * float(px)) > max(1e-6, abs(float(dv)) * 1e-9):
                problems.append(f"row {i}: dollar_value {dv} is not shares x price")
        if len(problems) > 20:
            break
    if problems:
        raise SecInsiderBulkError("fabrication guard: " + "; ".join(problems[:20]))
    return {"rows_checked": len(rows), "violations": 0,
            "implausible_dates": len(implausible),
            "implausible_date_examples": implausible[:5]}


# ------------------------------------------------------------- quarter maths

def split_quarter(q: str) -> tuple[int, int]:
    s = str(q).strip().lower()
    if len(s) != 6 or s[4] != "q" or not s[:4].isdigit() or s[5] not in "1234":
        raise SecInsiderBulkError(f"malformed quarter {q!r}; want e.g. '2006q1'")
    return int(s[:4]), int(s[5])


def quarters_between(start: str, end: str) -> list[str]:
    """['2006q1', ...] inclusive. Refuses a reversed or malformed range."""
    y0, q0 = split_quarter(start)
    y1, q1 = split_quarter(end)
    if (y1, q1) < (y0, q0):
        raise SecInsiderBulkError(f"end {end!r} precedes start {start!r}")
    out: list[str] = []
    y, q = y0, q0
    while (y, q) <= (y1, q1):
        out.append(f"{y}q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out
