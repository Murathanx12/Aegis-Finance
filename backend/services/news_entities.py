"""N-D — entity resolution: a headline in, symbols out, and a counted refusal.

Roadmap 2026-09-11 §3 N-D: *"issuer-name -> symbol table for HK/JP/KR/CN names
that also list in the US (ADRs) and for the 3,060-symbol Alpaca universe;
unresolved rows kept with `tickers=[]` and counted."*

WHAT THIS IS AND IS NOT
=======================
It is a deterministic, offline, no-LLM string resolver. It answers *"which
symbols does this text name?"* and nothing else. In particular it does **not**
answer whether the text is ABOUT the company favourably, or at all:

    "Nvidia denies the report that it cancelled the order"   -> ["NVDA"]

is the correct answer. A denial still names the issuer, and typing that denial
is L2's job (the LLM as reader), not a string matcher's. Resolving a denial to
`[]` would hide the row from the panel entirely — the mistake would be silent,
which is the one kind this repo tries hardest not to make.

THE THREE RULES, in the order they fire
=======================================
1. **Explicit ticker tokens** — `$NVDA`, `(NVDA)`, `NASDAQ: NVDA`, and Asian
   local codes `9988.HK`, `6758.T`, `2330.TW`, `034220.KS`. A local code is
   mapped to its US ADR leg through `asia_adrs.csv`, which is the whole point
   of that table: a Hong Kong headline about 9988.HK and a New York headline
   about BABA are the same issuer and must land on the same symbol.
2. **Primary names** from `issuers.csv` — "Agilent Technologies", "Alcoa".
3. **Aliases**, same table, pipe-separated.

THE LENGTH FLOOR, AND WHY IT EXISTS
===================================
Rules 2 and 3 are where a name table turns into a false-positive machine. Three
guards, all of them cheap and all of them testable:

* an alias shorter than `MIN_ALIAS_CHARS` (5) never matches by name — this is
  what stops symbol `A` (Agilent) from claiming every sentence containing the
  letter A, and `V`, `F`, `GM` from claiming their English homographs. Those
  names are still reachable by rule 1, which is the correct trade: an explicit
  `$A` is unambiguous, a bare "a" never is.
* `_GENERIC_ALIASES` drops alias strings that are ordinary English or ordinary
  business vocabulary ("energy", "capital", "holdings", "systems", ...). These
  appear as alias fragments for dozens of issuers and would resolve a macro
  headline to a random one of them.
* `_AMBIGUOUS_NAMES` — real company names that are also common words (apple,
  visa, target, gap, shell, ...) — match ONLY when a corporate cue word
  (`inc`, `ceo`, `shares`, `earnings`, `nasdaq`, ...) appears within
  `_CUE_WINDOW` characters. "Visa applications surge in Singapore" resolves to
  nothing; "Visa Inc. beat on earnings" resolves to V.

COVERAGE IS A NUMBER, NOT A FEELING
===================================
`issuers.csv` ships with 200 of its 3,056 rows carrying a real `primary_name`
(the 09-11 probe measured yfinance `.info` at 1.38 s/name, so the full pull is
~70 minutes and was out of that probe's budget). `stats()` prints exactly that,
so a low name-match rate reads as a known data gap rather than a broken
resolver. `scripts/news_pull.py` puts the per-source resolution rate in every
receipt for the same reason.
"""

from __future__ import annotations

import csv
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from backend import config as _config

#: A name alias shorter than this never matches on its own. See the docstring.
MIN_ALIAS_CHARS = 5

#: How far from an ambiguous name a corporate cue may sit and still license it.
_CUE_WINDOW = 40

#: Alias strings that are ordinary English or ordinary business vocabulary.
#: Each of these appears as an alias fragment for many issuers; matching one
#: resolves a macro headline to an arbitrary company.
_GENERIC_ALIASES = frozenset(
    """
    group holdings holding company companies corporation corp incorporated limited
    technologies technology systems solutions services service industries industrial
    international global national american united states america national
    financial finance bancorp bancshares banks banking insurance capital partners
    resources materials mining metals energies energy power electric utilities
    pharmaceuticals pharmaceutical pharma biosciences bioscience sciences science
    therapeutics laboratories laboratory research development health healthcare
    medical media entertainment communications telecom networks network
    properties property realty trust trusts investment investments income growth
    acquisition acquisitions enterprises enterprise ventures venture brands
    products production manufacturing motors automotive airlines airways
    software digital data cloud cyber security semiconductor semiconductors
    petroleum natural gas water steel chemical chemicals food foods beverage
    retail stores market markets exchange fund funds index shares class
    """.split()
)

#: Real company names that are also common English words. These match only with
#: a corporate cue nearby.
_AMBIGUOUS_NAMES = frozenset(
    """
    apple visa target gap shell ford amazon block square match unity
    arrow builders carnival chip core delta dollar edison eagle envision
    equity expedia gold hope host jack key lands life lincoln magnet
    marathon medium mosaic nike nordson origin owens paycom pool primerica
    progress range rush sage science service signet skyline snap sprout
    stride sun sunrise tandem tapestry tempur toll travel twist union
    vector victory vital wave west winner wolf world yeti zoom
    """.split()
)

#: Words that license an ambiguous name. Deliberately market vocabulary, not
#: sentiment vocabulary — this is a resolver, not a classifier.
_CORP_CUES = frozenset(
    """
    inc inc. corp corp. co co. ltd ltd. plc llc lp sa ag nv se
    shares shareholders stock stocks share earnings revenue guidance quarterly
    quarter eps dividend buyback ceo cfo coo chairman board nasdaq nyse
    ticker analyst analysts upgrade downgrade downgraded upgraded rating
    profit profits loss losses sales outlook forecast merger acquisition
    ipo filing 8-k 10-q 10-k sec investors investor market cap valuation
    """.split()
)

#: Asian local listing codes: 9988.HK, 6758.T, 2330.TW, 034220.KS, 600519.SS
_LOCAL_CODE_RE = re.compile(r"\b(\d{3,6}\.(?:HK|TW|T|KS|SS|SZ))\b")

#: `$NVDA`
_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")

#: `(NVDA)` and `NASDAQ: NVDA` / `NYSE:NVDA`
_PAREN_RE = re.compile(r"\(([A-Z]{1,5})\)")
_VENUE_RE = re.compile(r"\b(?:NASDAQ|NYSE|NYSEAMERICAN|AMEX|OTC|CBOE)\s*:\s*([A-Z]{1,5})\b")

_WORD_RE = re.compile(r"[A-Za-z0-9&.']+")


def entities_dir() -> Path:
    """`backend/data/news_entities` — from the IMAGE, not from `DATA_DIR`.

    Same rule as the source registry and `paper_portfolios.yaml`
    (`config.py:105-115`): version-controlled tables that ship with the code
    are never placed where a mounted volume could shadow them. Resolved at call
    time so a test can repoint `_config.BACKEND_DIR`.
    """
    return Path(_config.BACKEND_DIR) / "data" / "news_entities"


@dataclass(frozen=True)
class Resolution:
    """What a text resolved to, and by which rule.

    `tickers` is what goes in the corpus row; `how` is what goes in a receipt
    when someone asks why a headline was tagged with a symbol.
    """

    tickers: tuple[str, ...]
    how: dict[str, str]

    def __bool__(self) -> bool:
        return bool(self.tickers)


class _Tables:
    """The compiled name tables. Built once, keyed on the files' mtimes."""

    def __init__(self, issuers: Path, adrs: Path):
        self.issuers_path = issuers
        self.adrs_path = adrs
        self.symbols: set[str] = set()
        self.named_symbols: set[str] = set()
        self.name_to_symbol: dict[str, str] = {}
        self.local_to_us: dict[str, str] = {}
        self.n_issuer_rows = 0
        self.n_adr_rows = 0
        self.n_aliases_dropped_short = 0
        self.n_aliases_dropped_generic = 0
        self._name_re: re.Pattern | None = None
        self._build()

    # -- construction ----------------------------------------------------

    def _add_name(self, name: str, symbol: str) -> None:
        key = " ".join(name.lower().split())
        if not key:
            return
        stripped = key.rstrip(".").strip()
        if stripped in _GENERIC_ALIASES:
            self.n_aliases_dropped_generic += 1
            return
        if len(stripped) < MIN_ALIAS_CHARS:
            self.n_aliases_dropped_short += 1
            return
        # First writer wins: `issuers.csv` is symbol-sorted, so a collision
        # resolves deterministically rather than by iteration order.
        self.name_to_symbol.setdefault(stripped, symbol)

    def _build(self) -> None:
        if self.issuers_path.exists():
            with self.issuers_path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    sym = (row.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    self.n_issuer_rows += 1
                    self.symbols.add(sym)
                    primary = (row.get("primary_name") or "").strip()
                    if primary:
                        self.named_symbols.add(sym)
                        self._add_name(_strip_corporate_suffix(primary), sym)
                        self._add_name(primary, sym)
                    for alias in (row.get("aliases") or "").split("|"):
                        alias = alias.strip()
                        if not alias or alias.upper() == sym:
                            continue  # the ticker itself is rule 1's business
                        self._add_name(alias, sym)
                        self._add_name(_strip_corporate_suffix(alias), sym)
        if self.adrs_path.exists():
            with self.adrs_path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    us = (row.get("us_symbol") or "").strip().upper()
                    if not us:
                        continue
                    self.n_adr_rows += 1
                    self.symbols.add(us)
                    local = (row.get("local_symbol") or "").strip().upper()
                    if local:
                        self.local_to_us[local] = us
                    short = (row.get("us_short_name_yfinance") or "").strip()
                    if short:
                        self.named_symbols.add(us)
                        self._add_name(_strip_corporate_suffix(short), us)
                        self._add_name(short, us)
        names = sorted(self.name_to_symbol, key=len, reverse=True)
        if names:
            self._name_re = re.compile(
                r"(?<![A-Za-z0-9])(" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9])",
                re.IGNORECASE,
            )

    # -- use -------------------------------------------------------------

    def name_matches(self, text: str) -> list[tuple[str, str, int]]:
        if not self._name_re:
            return []
        out = []
        for m in self._name_re.finditer(text):
            key = " ".join(m.group(1).lower().split())
            sym = self.name_to_symbol.get(key)
            if sym:
                out.append((sym, key, m.start()))
        return out


_SUFFIXES = (
    "incorporated", "inc.", "inc", "corporation", "corp.", "corp", "company",
    "co.", "limited", "ltd.", "ltd", "plc", "llc", "l.p.", "lp", "n.v.", "nv",
    "s.a.", "sa", "a.g.", "ag", "group holding limited", "group holding",
    "holdings", "holding", "group", "the",
)


def _strip_corporate_suffix(name: str) -> str:
    """"Agilent Technologies, Inc." -> "Agilent Technologies".

    Repeated, because "Alibaba Group Holding Limited" needs three passes. The
    stripped form is registered ALONGSIDE the full one, never instead of it.
    """
    s = " ".join(name.replace(",", " ").split())
    changed = True
    while changed and s:
        changed = False
        low = s.lower()
        for suf in _SUFFIXES:
            if low.endswith(" " + suf):
                s = s[: -(len(suf) + 1)].strip()
                changed = True
                break
    return s


_CACHE: dict[str, object] = {}
_LOCK = threading.Lock()


def tables(issuers: Path | None = None, adrs: Path | None = None) -> _Tables:
    """The compiled tables, rebuilt when either CSV's mtime changes."""
    d = entities_dir()
    ip = Path(issuers) if issuers is not None else d / "issuers.csv"
    ap = Path(adrs) if adrs is not None else d / "asia_adrs.csv"
    stamp = (
        str(ip), ip.stat().st_mtime_ns if ip.exists() else 0,
        str(ap), ap.stat().st_mtime_ns if ap.exists() else 0,
    )
    with _LOCK:
        if _CACHE.get("stamp") == stamp:
            return _CACHE["tables"]  # type: ignore[return-value]
    built = _Tables(ip, ap)
    with _LOCK:
        _CACHE["stamp"] = stamp
        _CACHE["tables"] = built
    return built


def _cue_near(text_low: str, pos: int, length: int) -> bool:
    lo = max(0, pos - _CUE_WINDOW)
    hi = min(len(text_low), pos + length + _CUE_WINDOW)
    window = text_low[lo:hi]
    return any(w in _CORP_CUES for w in _WORD_RE.findall(window))


def resolve(text: str, *, tbl: _Tables | None = None, limit: int = 8) -> Resolution:
    """Symbols named by `text`, in first-appearance order, at most `limit`.

    Returns an empty `Resolution` rather than guessing. An unresolved row is
    kept with `tickers: []` and COUNTED — that count is the honest denominator
    of every coverage claim lane N makes.
    """
    if not text:
        return Resolution((), {})
    t = tbl or tables()
    text_low = text.lower()
    found: dict[str, str] = {}
    order: list[str] = []

    def take(sym: str, rule: str) -> None:
        if sym not in found:
            found[sym] = rule
            order.append(sym)

    # Rule 1 — explicit tokens. A local Asian code maps to its US ADR leg.
    for m in _LOCAL_CODE_RE.finditer(text):
        us = t.local_to_us.get(m.group(1).upper())
        if us:
            take(us, "adr_local_code")
    for rx, rule in ((_CASHTAG_RE, "cashtag"), (_PAREN_RE, "paren_ticker"), (_VENUE_RE, "venue_ticker")):
        for m in rx.finditer(text):
            sym = m.group(1).upper()
            if sym in t.symbols:
                take(sym, rule)

    # Rules 2 and 3 — names and aliases, with the ambiguity guard.
    for sym, key, pos in t.name_matches(text):
        if key in _AMBIGUOUS_NAMES and not _cue_near(text_low, pos, len(key)):
            continue
        take(sym, "name")

    return Resolution(tuple(order[:limit]), {s: found[s] for s in order[:limit]})


def stats(tbl: _Tables | None = None) -> dict:
    """The table's own coverage, for a receipt.

    `named_symbols` vs `issuer_rows` is the live measure of the 09-11 name-table
    gap: 200 of 3,056 rows carry a real `primary_name`, so a low name-match rate
    is a DATA gap with a number beside it, not a broken resolver.
    """
    t = tbl or tables()
    return {
        "issuer_rows": t.n_issuer_rows,
        "adr_rows": t.n_adr_rows,
        "symbols": len(t.symbols),
        "named_symbols": len(t.named_symbols),
        "name_keys": len(t.name_to_symbol),
        "local_codes": len(t.local_to_us),
        "aliases_dropped_below_length_floor": t.n_aliases_dropped_short,
        "aliases_dropped_as_generic": t.n_aliases_dropped_generic,
        "min_alias_chars": MIN_ALIAS_CHARS,
        "issuers_path": str(t.issuers_path),
        "adrs_path": str(t.adrs_path),
        "note": (
            "named_symbols < issuer_rows is the known 2026-09-11 name-table gap "
            "(yfinance .info measured at 1.38 s/name; the full 3,056-name pull is "
            "~70 minutes). Symbols without a primary_name are still reachable by "
            "explicit ticker token."
        ),
    }
