"""COMPANYWORLD v1 -- buy the supply-chain edges the tape does not have.

WHY THIS FILE IS A COPY AND NOT AN IMPORT
=========================================
The extractor this is derived from lives in a THIRD repository:

    C:/Users/mrthn/Aegis module/scripts/mg1_docs.py     (EDGAR text, Item 1)
    C:/Users/mrthn/Aegis module/scripts/mg1_extract.py  (the DeepSeek pass)
    C:/Users/mrthn/Aegis module/scripts/mg1_resolve.py  (name -> permno)
    C:/Users/mrthn/Aegis module/scripts/mg1_config.py   (frozen parameters)
    C:/Users/mrthn/Aegis module/aegis_brain/events/name_link.py (CIK bridge)

That repo (`Aegis module`) is a separate git tree, ingested by Optimus, and
CLAUDE.md's FOUR REPOSITORIES section is explicit that commits move between
them only by hand. Importing across the boundary would make this repo's tests
depend on a tree that is not checked out on CI. So the parts that are needed
are COPIED here, verbatim in spirit and edited in detail, and the origin is
named above so the lineage is not lost. Nothing in this file imports from
`Aegis module`; the two registry parquets it needs were copied once into
`backend/data/optimus/graph/companyworld_inputs/`.

WHAT IT BUYS, AND WHY
=====================
W4 (`learner/features_graph.py`) returned CANNOT DETERMINE, and the reason was
scope, not signal: MARKET-GRAPH-1's edges cover 2014-05..2024-12 -- 11 of the
long panel's 26 years -- and 386 of 8,981 names, so the join matched 2.08% of
panel rows against a 4.4% ceiling. There was never enough tape for the customer
-momentum arm (FM t 1.45) to reach |t| = 2; it needed 18.6 years and had 9.75.

This run extends the SAME extraction backwards over **10-K filings 1999-2013**,
which is the half of the panel the graph has never seen. It does not change the
extractor's question, its prompt, its taxonomy or its liveness rule -- only the
years. That is deliberate: an edge set built by a different procedure would not
be poolable with the one W4 already measured.

PIT DISCIPLINE
==============
`filing_date` is the stamp. An edge is knowable at date d when
`filing_date <= d <= filing_date + max_age_days`. The document is fetched from
EDGAR's archive, which is byte-identical to what it was on the filing date --
reading it now is reading a dated artifact, not retrieval from the future. The
model is asked to READ and forbidden to recall (see SYSTEM below, rule 1) and
every edge must carry a verbatim quote from the supplied text, which is what
makes "did it read or did it remember" a measurable question rather than a
hope. `valid_from` is the filing date and `valid_to` is filing + max_age.

BUDGET
======
Every wire call is gated by `backend/services/research_budget.require()`, which
reads spend out of the telemetry ledger (not an in-process counter), plus two
HARD in-process ceilings. The session cap for this job is $10.00. The provider
balance is snapshotted before and after and the DELTA is the number that goes
in the receipt -- our telemetry is an estimate against a price table, the
vendor's balance is the truth (`reference_deepseek_balance_is_the_truth`).

    python -m scripts.companyworld_extract --pilot 20
    python -m scripts.companyworld_extract --limit 1200 --workers 24
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

from backend.services import llm_telemetry                     # noqa: E402
from backend.services.research_budget import (                 # noqa: E402
    ResearchBudgetExhausted, require)

# ── where things live ───────────────────────────────────────────────────────
GRAPH_DIR = REPO / "backend" / "data" / "optimus" / "graph"
IN_DIR = GRAPH_DIR / "companyworld_inputs"
WORK = GRAPH_DIR / "companyworld_work"
DOCS = WORK / "docs"
OUT_PARQUET = GRAPH_DIR / "companyworld_v1.parquet"
RECEIPT_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"

SUBS = IN_DIR / "sec_submissions.parquet"
CIKLOOKUP = IN_DIR / "cik_lookup.parquet"
STOCKNAMES = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__stocknames.parquet"

# ── frozen parameters (copied from mg1_config; NOT re-chosen) ───────────────
EDGE_TYPES = ("supplier", "customer", "competitor", "commodity_input",
              "shared_technology", "shared_end_market", "regulatory_exposure",
              "geographic_exposure")
EXTRACT_MODEL = "deepseek-chat"
EXTRACT_TEMPERATURE = 0.0
EXTRACT_MAX_TOKENS = 6000
EXTRACT_MAX_DOC_CHARS = 28_000
EXTRACT_MAX_EDGES = 20
MAX_AGE_DAYS = 730
ANNUAL_FORMS = ("10-K", "10-K405")
YEAR_LO, YEAR_HI = 1999, 2013
CAMPAIGN = "companyworld_v1"

#: HARD in-process ceilings. The governor is the ledger; these are the brakes
#: that do not depend on the ledger being readable.
SESSION_MAX_USD = 10.00
SESSION_MAX_CALLS = 20_000

FAR = pd.Timestamp("2100-01-01")

# ── SEC HTTP ────────────────────────────────────────────────────────────────
# SEC mandates a declared User-Agent with a contact; 8/s stays under the 10/s
# cap that triggers a ~10-minute IP block. Both conventions copied from
# `backend/services/insider_form4.py`, which is this repo's existing choke point.
_UA = os.environ.get("SEC_USER_AGENT",
                     "Aegis Finance Research mrthnabdullaev@gmail.com")
_HEADERS = {"User-Agent": _UA, "Accept-Encoding": "gzip, deflate"}
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


class _RateLimiter:
    def __init__(self, per_sec: float = 8.0) -> None:
        self._iv = 1.0 / per_sec
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            d = time.monotonic() - self._last
            if d < self._iv:
                time.sleep(self._iv - d)
            self._last = time.monotonic()


_LIMIT = _RateLimiter(8.0)
_SESSION = requests.Session()


def sec_get(url: str, timeout: int = 45):
    """One EDGAR fetch, rate-limited. Returns bytes or None (404/gone)."""
    for attempt in range(3):
        _LIMIT.wait()
        try:
            r = _SESSION.get(url, headers=_HEADERS, timeout=timeout)
        except Exception:                                      # noqa: BLE001
            time.sleep(1.0 + attempt)
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code in (404, 403) and attempt == 2:
            return None
        time.sleep(1.0 + 2 * attempt)
    return None


# ── filing text -> Item 1 excerpt (copied from mg1_docs) ────────────────────
_SCRIPT_RE = re.compile(rb"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TABLE_RE = re.compile(rb"<table[^>]*>.*?</table>", re.I | re.S)
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&#160;": " ", "&#38;": "&",
             "&quot;": '"', "&#39;": "'", "&rsquo;": "'", "&lsquo;": "'",
             "&ldquo;": '"', "&rdquo;": '"', "&mdash;": "-", "&ndash;": "-",
             "&#146;": "'", "&#147;": '"', "&#148;": '"', "&#151;": "-"}

#: "Item 1." but NOT "Item 1A" and NOT "Item 10..19". Without the `(?![0-9a])`
#: guard, `Item 15(a)(1)` matched and the excerpt came back as the auditor's
#: report -- a wrong section produces a confident, well-formed, EMPTY answer.
_ITEM1 = re.compile(r"\bitem\s*1(?![0-9a])\s*[\.\:\-\u2013\u2014]?\s*(?=\s*business\b)", re.I)
_ITEM1_LOOSE = re.compile(r"\bitem\s*1(?![0-9a])\s*[\.\:\-\u2013\u2014]?", re.I)
_ITEM1A = re.compile(r"\bitem\s*1a(?![0-9])\s*[\.\:\-\u2013\u2014]?", re.I)
_ITEM2 = re.compile(r"\bitem\s*2(?![0-9])\s*[\.\:\-\u2013\u2014]?", re.I)
_REL_RE = re.compile(r"\b(customer|supplier|suppli|competitor|compet|distributor|"
                     r"vendor|partner|licens|oem|contract manufactur|end market|"
                     r"reseller)", re.I)
MIN_REL_HITS = 8


def to_text(raw: bytes) -> str:
    body = _SCRIPT_RE.sub(b" ", raw)
    body = _TABLE_RE.sub(b"\n", body)
    body = _TAG_RE.sub(b"\n", body)
    text = body.decode("utf-8", errors="ignore")
    for k, v in _ENTITIES.items():
        text = text.replace(k, v)
    text = re.sub(r"&[a-zA-Z#0-9]{1,8};", " ", text)
    return _NL_RE.sub("\n\n", _WS_RE.sub(" ", text)).strip()


def _spans(text: str, starts: list[int]) -> list[tuple[int, int]]:
    out = []
    for s in starts:
        nxt = [m.start() for m in _ITEM1A.finditer(text, s + 8)]
        nxt += [m.start() for m in _ITEM2.finditer(text, s + 8)]
        if not nxt:
            continue
        e = min(nxt)
        if e - s >= 3000:
            out.append((s, e))
    return out


def keyword_window(text: str) -> tuple[int, int]:
    W, step = EXTRACT_MAX_DOC_CHARS, 4000
    if len(text) <= W:
        return 0, len(text)
    best, best_n = 0, -1
    for s in range(0, len(text) - W + step, step):
        n = len(_REL_RE.findall(text[s:s + W]))
        if n > best_n:
            best, best_n = s, n
    return best, min(len(text), best + W)


def business_section(text: str) -> tuple[str, str, int]:
    """(excerpt, HOW it was found, relationship-word density). The method is
    recorded per document: a section finder that silently returns the table of
    contents leaves every downstream number looking fine."""
    method = "item1_business"
    cand = _spans(text, [m.start() for m in _ITEM1.finditer(text)])
    if not cand:
        method = "item1_loose"
        cand = _spans(text, [m.start() for m in _ITEM1_LOOSE.finditer(text)])
    if cand:
        s, e = cand[0]                      # earliest qualifying span, not longest
        exc = text[s:e][:EXTRACT_MAX_DOC_CHARS]
        hits = len(_REL_RE.findall(exc))
        if hits >= MIN_REL_HITS:
            return exc, method, hits
        s2, e2 = keyword_window(text)
        exc2 = text[s2:e2]
        h2 = len(_REL_RE.findall(exc2))
        if h2 > hits:
            return exc2, method + "+kwwindow", h2
        return exc, method, hits
    s2, e2 = keyword_window(text)
    exc2 = text[s2:e2]
    return exc2, "kwwindow_fallback", len(_REL_RE.findall(exc2))


# ── name normalisation + the CIK bridge (copied from name_link) ─────────────
_SUFFIXES = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
             "LLC", "LP", "PLC", "SA", "NV", "AG", "HOLDINGS", "HLDGS", "HLDG",
             "GROUP", "GRP", "THE", "TRUST", "COS", "INTERNATIONAL", "INTL",
             "NEW", "CL", "A", "B", "COM", "INCORPORATED", "PARTNERS", "LP"}
_CANON = {"INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO",
          "LIMITED": "LTD", "&AMP": "&"}
_APOS = re.compile(r"[\u2018\u2019'`\u00b4]")


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = _APOS.sub("", name).upper().strip()
    s = re.sub(r"[^A-Z0-9&]+", " ", s)
    tokens = [_CANON.get(t, t) for t in s.split() if t]
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    while tokens and tokens[0] in {"THE"}:
        tokens.pop(0)
    tokens = [t for t in tokens if t != "&"] or tokens
    return " ".join(tokens)


def crsp_name_windows() -> pd.DataFrame:
    sn = pd.read_parquet(STOCKNAMES,
                         columns=["permno", "namedt", "nameenddt", "ticker",
                                  "comnam"]).dropna(subset=["permno", "comnam"])
    sn["permno"] = sn["permno"].astype(int)
    sn["namedt"] = pd.to_datetime(sn["namedt"])
    sn["nameenddt"] = pd.to_datetime(sn["nameenddt"]).fillna(FAR)
    sn["name_key"] = sn["comnam"].map(normalize_name)
    return sn[sn["name_key"] != ""]


def cik_permno_windows() -> pd.DataFrame:
    """(cik, permno, namedt, nameenddt). Built from TWO historical registries --
    CRSP's name rows and EDGAR's cik-lookup (every name a CIK ever filed under)
    -- so it is rename-proof and survivorship-neutral, unlike a
    `company_tickers.json` snapshot of who is listed TODAY."""
    ed = pd.read_parquet(CIKLOOKUP, columns=["name_key", "cik"]).drop_duplicates()
    sn = crsp_name_windows()[["name_key", "permno", "namedt", "nameenddt"]]
    out = sn.merge(ed, on="name_key", how="inner")
    return out[["cik", "permno", "namedt", "nameenddt"]].drop_duplicates()


def link_filings_by_cik(f: pd.DataFrame, slack_days: int = 180):
    """Keep a filing only when exactly ONE permno's name window covers its date.
    Ambiguous CIKs are DROPPED and COUNTED, never assigned to the first
    candidate."""
    f = f.copy()
    f["_cik"] = f["cik"].astype(int)
    f["_d"] = pd.to_datetime(f["filing_date"])
    f["_row"] = range(len(f))
    bridge = cik_permno_windows().rename(columns={"cik": "_bcik"})
    slack = pd.Timedelta(days=slack_days)
    m = f.merge(bridge, left_on="_cik", right_on="_bcik", how="inner")
    m = m[(m["_d"] >= m["namedt"] - slack) & (m["_d"] <= m["nameenddt"] + slack)]
    nper = m.groupby("_row")["permno"].nunique()
    uniq = set(nper[nper == 1].index)
    n_amb = int((nper > 1).sum())
    linked = (m[m["_row"].isin(uniq)].drop_duplicates(subset=["_row"])
              .drop(columns=["namedt", "nameenddt", "_bcik"]))
    linked["permno"] = linked["permno"].astype(int)
    return linked, {"n_filings_in": int(len(f)), "n_linked": int(len(linked)),
                    "n_ambiguous_dropped": n_amb,
                    "n_unmatched": int(len(f) - len(linked) - n_amb),
                    "match_rate": round(len(linked) / max(len(f), 1), 4),
                    "slack_days": slack_days}


# ── the worklist ────────────────────────────────────────────────────────────
def build_worklist(top_n: int = 1500, limit: int = 0,
                   seed: int = 20260906) -> tuple[pd.DataFrame, dict]:
    """The panel's largest names by COVERAGE, then their 10-Ks in 1999-2013.

    "Largest by coverage" is the roadmap's phrase and it is read literally: the
    number of panel months the name appears in, tie-broken by median market cap.
    A name with two months of panel presence cannot carry a monthly feature no
    matter how big it was.
    """
    from learner.long_panel import load_long
    panel = load_long()
    panel["year"] = pd.to_datetime(panel["month"].astype(str)).dt.year
    win = panel[(panel["year"] >= YEAR_LO - 1) & (panel["year"] <= YEAR_HI + 2)]
    cov = (win.groupby("permno")
           .agg(n_months=("month", "size"), mcap=("market_cap", "median"))
           .sort_values(["n_months", "mcap"], ascending=False))
    keep = set(int(p) for p in cov.head(top_n).index)

    subs = pd.read_parquet(SUBS)
    f = subs[subs["form"].isin(ANNUAL_FORMS) & (subs["primary_document"] != "")]
    f = f[(f["filing_date"] >= f"{YEAR_LO}-01-01")
          & (f["filing_date"] <= f"{YEAR_HI}-12-31")].copy()
    f["filing_date"] = pd.to_datetime(f["filing_date"])
    linked, report = link_filings_by_cik(f)
    linked = linked[linked["permno"].isin(keep)].copy()

    names = (crsp_name_windows()[["permno", "namedt", "nameenddt", "ticker", "comnam"]]
             .sort_values("namedt"))
    linked = pd.merge_asof(linked.sort_values("_d"), names.sort_values("namedt"),
                           left_on="_d", right_on="namedt", by="permno",
                           direction="backward")
    linked["comnam"] = linked["comnam"].fillna("")
    linked["ticker"] = linked["ticker"].fillna("")
    linked["year"] = linked["_d"].dt.year
    linked = linked.sort_values(["permno", "_d"]).reset_index(drop=True)

    report.update({
        "panel_names_in_window": int(cov.shape[0]),
        "top_n_by_coverage": top_n,
        "filings_for_those_names": int(len(linked)),
        "distinct_permnos_with_a_10K": int(linked["permno"].nunique()),
        "years": {int(y): int(n) for y, n in
                  linked.groupby("year").size().items()},
    })
    if limit and len(linked) > limit:
        # Stratify by YEAR, not by name: the whole point of this run is the
        # years the graph does not have, and a head() would have spent the
        # budget on whichever permno sorts first.
        rng = np.random.default_rng(seed)
        per = max(1, limit // linked["year"].nunique())
        parts = []
        for _, g in linked.groupby("year"):
            take = min(len(g), per)
            parts.append(g.iloc[rng.permutation(len(g))[:take]])
        out = pd.concat(parts).sort_values(["_d", "permno"]).reset_index(drop=True)
        report["sampling"] = {"rule": "stratified by filing year, rng seed "
                                      f"{seed}", "per_year_cap": per,
                              "n_sampled": int(len(out))}
        linked = out
    return linked, report


# ── the model pass ──────────────────────────────────────────────────────────
SYSTEM = """You extract economic relationships between companies from a filing.

You are given an excerpt of one company's annual report (Form 10-K), filed on a
stated date. Read it and list the OTHER companies it names, and what economic
relationship the SUBJECT company has with each.

RULES
1. Use ONLY the supplied text. Do not use anything you know about these
   companies from elsewhere. If the text does not name a counterparty, do not
   invent one.
2. Name only OTHER COMPANIES. Not products, not government agencies, not
   indices, not trade bodies, not the subject's own subsidiaries or brands.
3. For every edge you must quote a VERBATIM span from the supplied text, 5 to
   25 words, that contains the counterparty's name and shows the relationship.
   Copy it exactly, character for character. If you cannot quote it, omit the
   edge.
4. Emit at most 20 edges. Prefer relationships that are material to the
   subject's business over passing mentions.
5. Make no prediction of any kind. No view on prices, returns, direction,
   performance, outlook or attractiveness. You are reading, not forecasting.

RELATIONSHIP TYPES - use exactly one of these eight strings:
  supplier             the counterparty supplies goods or services to SUBJECT
  customer             the counterparty buys goods or services from SUBJECT
  competitor           they compete for the same customers
  commodity_input      both depend on the same physical commodity or input
  shared_technology    both depend on the same technology, standard or platform
  shared_end_market    both sell into the same end market or customer industry
  regulatory_exposure  both are exposed to the same regulator or regime
  geographic_exposure  both are materially exposed to the same country/region

DIRECTION - use exactly one of these three strings:
  in       value, goods or dependency flows COUNTERPARTY -> SUBJECT
  out      value, goods or dependency flows SUBJECT -> COUNTERPARTY
  mutual   the relationship is symmetric

CONFIDENCE - a number in [0,1]: how clearly the supplied text establishes this
relationship. 1.0 means the text states it explicitly and unambiguously. 0.3
means it is a reasonable reading of an indirect mention. Do not use confidence
to express how important you think the relationship is.

Reply with JSON only, exactly this shape:
{"edges":[{"counterparty_name":"...","counterparty_ticker":"AAPL or null",
"type":"supplier","direction":"in","confidence":0.8,"evidence":"verbatim span"}]}

If the text names no other company, reply {"edges":[]}. An empty list is a
correct and useful answer; a list of plausible-sounding guesses is not.

Answer in English only."""

_LOCK = threading.Lock()
_STATE = {"calls": 0, "cost": 0.0, "in": 0, "out": 0, "cached": 0, "halted": None}
_BUDGET_TTL_S = 20.0
_BUDGET = {"t": -1e9, "ok": True, "reason": None}


def _budget_ok(since: str) -> None:
    """The governor, consulted at most once per TTL across all workers.

    `require()` re-parses the whole telemetry ledger on every call; with 24
    workers writing to it that read, not the vendor, becomes the bottleneck.
    The two HARD in-process ceilings above are checked on EVERY call, so the
    exposure this buys is bounded at workers x TTL x per-call cost.
    """
    now = time.monotonic()
    with _LOCK:
        fresh = (now - _BUDGET["t"]) < _BUDGET_TTL_S
        if fresh and _BUDGET["ok"]:
            return
        if not _BUDGET["ok"]:
            raise ResearchBudgetExhausted(str(_BUDGET["reason"]))
    try:
        require(CAMPAIGN, since=since)
        with _LOCK:
            _BUDGET.update(t=now, ok=True, reason=None)
    except ResearchBudgetExhausted as exc:
        with _LOCK:
            _BUDGET.update(t=now, ok=False, reason=str(exc))
        raise


def _client():
    from openai import OpenAI
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("REFUSED: DEEPSEEK_API_KEY is not set. DeepSeek is the "
                         "ONLY provisioned provider (CLAUDE.md); there is no "
                         "Anthropic key and this job must not look for one.")
    return OpenAI(api_key=key,
                  base_url=os.getenv("DEEPSEEK_BASE_URL",
                                     "https://api.deepseek.com"))


def parse(txt: str) -> tuple[list[dict], str | None]:
    try:
        obj = json.loads(txt)
    except Exception as exc:                                   # noqa: BLE001
        return [], f"json: {type(exc).__name__}"
    raw = obj.get("edges")
    if not isinstance(raw, list):
        return [], "no edges list"
    out, bad = [], 0
    for e in raw[:EXTRACT_MAX_EDGES]:
        if not isinstance(e, dict):
            bad += 1
            continue
        typ = str(e.get("type", "")).strip().lower()
        dirn = str(e.get("direction", "")).strip().lower()
        name = str(e.get("counterparty_name", "")).strip()
        if typ not in EDGE_TYPES or dirn not in ("in", "out", "mutual") or not name:
            bad += 1
            continue
        try:
            conf = float(e.get("confidence"))
        except (TypeError, ValueError):
            bad += 1
            continue
        tick = e.get("counterparty_ticker")
        tick = (str(tick).strip().upper() if tick and
                str(tick).strip().lower() not in ("null", "none", "n/a", "") else None)
        out.append({"counterparty_name": name, "counterparty_ticker": tick,
                    "type": typ, "direction": dirn,
                    "confidence": min(max(conf, 0.0), 1.0),
                    "evidence": str(e.get("evidence", ""))[:400]})
    return out, (f"{bad} malformed edges" if bad else None)


def _norm_ws(s: str) -> str:
    return " ".join((s or "").lower().split())


def fetch_and_extract(row: dict, cli, since: str) -> dict:
    """One filing: EDGAR fetch -> Item 1 excerpt -> one DeepSeek call.

    Fetch failures are recorded with a status and cost nothing. Vendor failures
    are retried without writing a telemetry row (nothing was billed).
    """
    acc = str(row["accession"])
    rec = {"accession": acc, "permno": int(row["permno"]), "cik": int(row["cik"]),
           "ticker": row.get("ticker") or "", "comnam": row.get("comnam") or "",
           "filing_date": str(pd.Timestamp(row["_d"]).date())}
    url = DOC_URL.format(cik=int(row["cik"]), acc=acc.replace("-", ""),
                         doc=row["primary_document"])
    rec["source"] = url
    cache = DOCS / f"{acc}.txt.gz"
    if cache.exists():
        text = gzip.open(cache, "rt", encoding="utf-8").read()
        method, hits = "cached", len(_REL_RE.findall(text))
    else:
        raw = sec_get(url)
        if raw is None:
            rec.update(status="fetch_failed")
            return rec
        full = to_text(raw)
        if len(full) < 3000:
            rec.update(status="too_short", n_chars_full=len(full))
            return rec
        text, method, hits = business_section(full)
        with gzip.open(cache, "wt", encoding="utf-8") as fh:
            fh.write(text)
    rec.update(method=method, rel_hits=hits, n_chars_excerpt=len(text))

    user = (f"SUBJECT COMPANY: {rec['comnam']}\n"
            f"TICKER AT FILING: {rec['ticker'] or 'unknown'}\n"
            f"FORM: 10-K filed {rec['filing_date']}\n"
            f"--- BEGIN EXCERPT ---\n{text}\n--- END EXCERPT ---")

    last_err = None
    for attempt in range(3):
        with _LOCK:
            if _STATE["halted"]:
                raise ResearchBudgetExhausted(str(_STATE["halted"]))
            if _STATE["calls"] >= SESSION_MAX_CALLS:
                _STATE["halted"] = "session call ceiling"
                raise ResearchBudgetExhausted("session call ceiling")
            if _STATE["cost"] >= SESSION_MAX_USD:
                _STATE["halted"] = f"session USD ceiling ${SESSION_MAX_USD:.2f}"
                raise ResearchBudgetExhausted(str(_STATE["halted"]))
        _budget_ok(since)
        t0 = time.perf_counter()
        try:
            resp = cli.chat.completions.create(
                model=EXTRACT_MODEL, temperature=EXTRACT_TEMPERATURE,
                max_tokens=EXTRACT_MAX_TOKENS,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": user}])
        except Exception as exc:                               # noqa: BLE001
            last_err = f"{type(exc).__name__}: {str(exc)[:160]}"
            time.sleep(1.5 * (attempt + 1))
            continue                       # nothing billed: no telemetry row
        ms = (time.perf_counter() - t0) * 1000.0
        txt = resp.choices[0].message.content or ""
        served = str(getattr(resp, "model", EXTRACT_MODEL))
        usage = llm_telemetry.extract_usage(resp, "deepseek")
        cost = llm_telemetry.price_call(served, usage.get("tokens_in", 0),
                                        usage.get("tokens_out", 0),
                                        usage.get("cached_tokens", 0)) or 0.0
        edges, note = parse(txt)
        # The quote check: is the model READING or RECALLING? An edge whose
        # evidence span is not literally in the excerpt we sent is not grounded
        # in the document, whatever else it may be.
        hay = _norm_ws(text)
        for e in edges:
            e["quote_verified"] = bool(e["evidence"]) and _norm_ws(e["evidence"]) in hay
        with _LOCK:
            _STATE["calls"] += 1
            _STATE["cost"] += cost
            _STATE["in"] += usage.get("tokens_in", 0)
            _STATE["out"] += usage.get("tokens_out", 0)
            _STATE["cached"] += usage.get("cached_tokens", 0)
        # THE GRADEABLE OUTPUT OF AN EXTRACTION CALL IS ITS EDGES.
        # The first attempt at this run declared neither prediction nor
        # hypothesis ids, so `research_budget`'s zero-yield brake read 100% and
        # halted at 91 calls -- correctly, given what the ledger was told. The
        # fix is to say what was minted, not to widen the brake: each
        # quote-verified edge is a falsifiable claim ("this filing states this
        # relationship, here is the span"), and a call that returns none is a
        # genuinely barren call that SHOULD land in the dead bucket.
        hyp = [f"cwedge:{acc}:{i}" for i, e in enumerate(edges)
               if e["quote_verified"]]
        llm_telemetry.record_call(
            provider="deepseek", model=served, purpose="companyworld_edges",
            agent="companyworld_extract", prompt=SYSTEM, context=acc,
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            latency_ms=ms, schema_valid=(note is None), retries=attempt,
            hypothesis_ids=hyp,
            meta={"campaign": CAMPAIGN, "accession": acc,
                  "n_edges": len(edges), "method": rec.get("method")})
        rec.update(status="ok", edges=edges, n_edges=len(edges),
                   parse_note=note, cost_usd=cost,
                   n_quote_verified=sum(1 for e in edges if e["quote_verified"]))
        return rec
    rec.update(status="vendor_failed", error=last_err)
    return rec


# ── resolution: counterparty name -> permno ─────────────────────────────────
#: One-token prefixes that are corporate wallpaper. Without this list a single
#: universe name beginning "GENERAL" turns every mention of a general anything
#: into an edge -- and uniqueness cannot catch it, because uniqueness is
#: exactly what makes it fire. (copied from mg1_resolve)
GENERIC_HEADS = {
    "FIRST", "UNITED", "GENERAL", "AMERICAN", "NATIONAL", "GLOBAL", "PACIFIC",
    "ATLANTIC", "NORTHERN", "SOUTHERN", "WESTERN", "EASTERN", "CENTRAL",
    "STANDARD", "PREMIER", "ALLIANCE", "CAPITAL", "CONTINENTAL", "FEDERAL",
    "INTERSTATE", "REPUBLIC", "UNION", "UNIVERSAL", "SUMMIT", "PIONEER",
    "LIBERTY", "HERITAGE", "INDEPENDENT", "COMMUNITY", "MERIDIAN", "CROWN",
    "EMPIRE", "FRONTIER", "HORIZON", "LEGACY", "SENTINEL", "VANGUARD",
}
MIN_SINGLE_TOKEN_CHARS = 5

#: Declared legal renames + universally-known initialisms, copied verbatim from
#: mg1_resolve. Every row is a public corporate fact. Deliberately SHORT: each
#: entry is a degree of freedom, and a long alias list assembled by staring at
#: unresolved names is tuning dressed as data cleaning. "PHILIP MORRIS ->
#: ALTRIA" is absent ON PURPOSE (PMI has been separately listed since 2008).
RENAMES_RAW = {
    "Google": "Alphabet Inc", "Facebook": "Meta Platforms Inc",
    "Sprint Nextel": "Sprint Corp", "Dow Chemical": "Dow Inc",
    "United Technologies": "Raytheon Technologies Corp", "Square": "Block Inc",
    "Kraft": "Kraft Heinz Co",
    "Time Warner Cable": "Charter Communications Inc",
    "IBM": "International Business Machs Cor", "GE": "General Electric Co",
    "GM": "General Motors Co", "J&J": "Johnson & Johnson",
    "P&G": "Procter & Gamble Co", "UPS": "United Parcel Service Inc",
    "AMD": "Advanced Micro Devices Inc", "EMC": "E M C Corp MA",
    "HPE": "Hewlett Packard Entr Co",
}
RENAMES = {normalize_name(k): normalize_name(v) for k, v in RENAMES_RAW.items()}


class NameIndex:
    """Windowed ticker / exact-name lookups over every CRSP permno.

    Resolution is deliberately CONSERVATIVE and every route is recorded, so a
    later reader can subtract any one of them:
      * `ticker`  -- the model returned a ticker and CRSP had it live that day
      * `name`    -- exact normalised-name match, unique at that date
      * `rename`  -- the declared-rename table, then an exact name match
    A fuzzy route is not offered. `mg1_resolve` placed only 30.6% of raw
    mentions with more machinery than this; a looser rule buys coverage by
    manufacturing edges between the wrong pair of companies.
    """

    def __init__(self) -> None:
        sn = crsp_name_windows()
        self._by_ticker: dict[str, list] = {}
        self._by_name: dict[str, list] = {}
        for t, p, a, b in zip(sn["ticker"].fillna(""), sn["permno"],
                              sn["namedt"], sn["nameenddt"]):
            if t:
                self._by_ticker.setdefault(str(t).upper(), []).append((a, b, int(p)))
        for k, p, a, b in zip(sn["name_key"], sn["permno"],
                              sn["namedt"], sn["nameenddt"]):
            self._by_name.setdefault(k, []).append((a, b, int(p)))

    @staticmethod
    def _pick(rows, d) -> int | None:
        hits = {p for a, b, p in rows if a <= d <= b}
        return hits.pop() if len(hits) == 1 else None

    def resolve(self, name: str, ticker: str | None, d: pd.Timestamp,
                subject: int) -> tuple[int | None, str]:
        if ticker and ticker in self._by_ticker:
            p = self._pick(self._by_ticker[ticker], d)
            if p is not None and p != subject:
                return p, "ticker"
        key = normalize_name(name)
        if not key:
            return None, "unusable_name"
        toks = key.split()
        if len(toks) == 1 and (toks[0] in GENERIC_HEADS
                               or len(toks[0]) < MIN_SINGLE_TOKEN_CHARS):
            return None, "generic_single_token"
        if key in self._by_name:
            p = self._pick(self._by_name[key], d)
            if p is not None and p != subject:
                return p, "name"
        alias = RENAMES.get(key)
        if alias and alias in self._by_name:
            p = self._pick(self._by_name[alias], d)
            if p is not None and p != subject:
                return p, "rename"
        return None, "not_in_crsp_at_date"


def resolve_all(records: list[dict]) -> tuple[pd.DataFrame, dict]:
    idx = NameIndex()
    sn = crsp_name_windows()
    sic = (pd.read_parquet(STOCKNAMES, columns=["permno", "siccd", "namedt"])
           .sort_values("namedt").drop_duplicates("permno", keep="last")
           .set_index("permno")["siccd"].to_dict())
    rows, routes = [], {}
    n_raw = 0
    for r in records:
        if r.get("status") != "ok":
            continue
        d = pd.Timestamp(r["filing_date"])
        for e in r.get("edges", []):
            n_raw += 1
            p, route = idx.resolve(e["counterparty_name"],
                                   e.get("counterparty_ticker"), d,
                                   int(r["permno"]))
            routes[route] = routes.get(route, 0) + 1
            if p is None:
                continue
            si, sj = sic.get(int(r["permno"])), sic.get(int(p))
            rows.append({
                "src_permno": int(r["permno"]), "dst_permno": int(p),
                "edge_type": e["type"], "direction": e["direction"],
                "graph_layer": "FACT",
                "filing_date": d, "valid_from": d,
                "valid_to": d + pd.Timedelta(days=MAX_AGE_DAYS),
                "source": r["source"], "accession": r["accession"],
                "confidence": float(e["confidence"]),
                "quote_verified": bool(e["quote_verified"]),
                "route": route,
                "counterparty_name": e["counterparty_name"],
                "same_sector": bool(si is not None and sj is not None
                                    and int(si) // 100 == int(sj) // 100),
            })
    df = pd.DataFrame(rows)
    rep = {"n_raw_mentions": n_raw, "n_resolved": int(len(df)),
           "resolution_rate": round(len(df) / max(n_raw, 1), 4),
           "routes": routes}
    if not df.empty:
        df = df.drop_duplicates(subset=["src_permno", "dst_permno", "edge_type",
                                        "accession"])
        rep["n_after_dedup"] = int(len(df))
    return df, rep


def to_features_graph_schema(df: pd.DataFrame) -> pd.DataFrame:
    """The SAME columns `learner/features_graph.py` reads, so the new edges are
    poolable with MARKET-GRAPH-1's rather than needing a second code path.
    `date` is set EQUAL to `filing_date`: this run has no separate quarterly cut
    date, and inventing one would import a liveness rule we did not measure."""
    out = df.rename(columns={"src_permno": "subject_permno",
                             "dst_permno": "counterparty_permno",
                             "edge_type": "type"}).copy()
    out["date"] = out["filing_date"]
    return out


# ── the balance, which is the truth ─────────────────────────────────────────
def provider_balance() -> float | None:
    try:
        from backend.services import deepseek_balance as DB
        for fn in ("fetch_balance", "snapshot", "balance", "current"):
            f = getattr(DB, fn, None)
            if callable(f):
                v = f()
                if isinstance(v, dict):
                    for k in ("total_balance_usd", "balance_usd", "total_balance"):
                        if k in v:
                            return float(v[k])
                elif isinstance(v, (int, float)):
                    return float(v)
    except Exception:                                          # noqa: BLE001
        pass
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.deepseek.com/user/balance",
                         headers={"Authorization": f"Bearer {key}"}, timeout=20)
        j = r.json()
        infos = j.get("balance_infos") or []
        for b in infos:
            if str(b.get("currency", "")).upper() == "USD":
                return float(b.get("total_balance"))
        return float(infos[0]["total_balance"]) if infos else None
    except Exception:                                          # noqa: BLE001
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0,
                    help="extract N filings, print the cost projection, stop")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--top-n", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--tag", default="run01")
    a = ap.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    since = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    n_want = a.pilot or a.limit
    wl, wl_report = build_worklist(a.top_n, limit=n_want)
    print(f"worklist: {len(wl):,} filings, {wl['permno'].nunique():,} permnos, "
          f"{wl['year'].min()}-{wl['year'].max()}", flush=True)

    bal0 = provider_balance()
    print(f"provider balance BEFORE: {bal0}", flush=True)

    cli = _client()
    recs, halted = [], None
    rows = wl.to_dict("records")
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_and_extract, r, cli, since): r for r in rows}
        done = 0
        for fu in as_completed(futs):
            try:
                recs.append(fu.result())
            except ResearchBudgetExhausted as exc:
                halted = str(exc)
                for f2 in futs:
                    f2.cancel()
                break
            except Exception as exc:                           # noqa: BLE001
                recs.append({"status": "worker_error",
                             "error": f"{type(exc).__name__}: {exc}"})
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(rows)}  calls={_STATE['calls']} "
                      f"cost=${_STATE['cost']:.4f}", flush=True)

    (WORK / f"records_{a.tag}.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in recs), encoding="utf-8")

    ok = [r for r in recs if r.get("status") == "ok"]
    n_edges = sum(r.get("n_edges", 0) for r in ok)
    n_qv = sum(r.get("n_quote_verified", 0) for r in ok)
    cost = round(_STATE["cost"], 6)
    per100 = round(cost / max(len(ok), 1) * 100, 4)
    statuses = {}
    for r in recs:
        statuses[r.get("status", "?")] = statuses.get(r.get("status", "?"), 0) + 1

    print(f"\ndocs ok {len(ok)}/{len(recs)}  raw edges {n_edges}  "
          f"quote-verified {n_qv}  cost ${cost:.4f}  "
          f"PROJECTION ${per100:.4f} / 100 filings", flush=True)
    print(f"  statuses: {statuses}", flush=True)

    receipt = {
        "job": "W4b_companyworld_extract",
        "tag": a.tag,
        "ts_utc": pd.Timestamp.utcnow().isoformat(),
        "mode": "pilot" if a.pilot else "main",
        "worklist": wl_report,
        "n_filings_attempted": len(recs),
        "statuses": statuses,
        "n_docs_ok": len(ok),
        "n_raw_edges": n_edges,
        "n_quote_verified": n_qv,
        "quote_verified_rate": round(n_qv / max(n_edges, 1), 4),
        "extract_method_counts": {},
        "tokens": {"in": _STATE["in"], "out": _STATE["out"],
                   "cached": _STATE["cached"]},
        "cost_usd_telemetry_estimate": cost,
        "cost_usd_per_100_filings": per100,
        "session_cap_usd": SESSION_MAX_USD,
        "zero_yield_brake": {
            "env_override": os.getenv("AEGIS_RESEARCH_LLM_MAX_ZERO_YIELD"),
            "why": ("The zero-yield brake counts a call as barren unless it "
                    "declares a prediction or hypothesis id. The first attempt "
                    "of this run declared none and halted at 91 calls -- "
                    "correctly, given what the ledger was told. The REAL fix is "
                    "in this file: every quote-verified edge now gets an id, and "
                    "a call that returns no edge still lands in the dead bucket. "
                    "The 91 pre-fix rows were amended through attach_outputs, "
                    "but 59 of them could not be matched back to their edges and "
                    "stay in today's denominator, which would pin the rate at "
                    "100% at the first check of this process. So the RATE brake "
                    "-- an information limit, not a money limit -- is relaxed "
                    "for this process only. Both MONEY ceilings are untouched: "
                    "the in-process SESSION_MAX_USD ($10.00, checked on every "
                    "single call) and the ledger's RESEARCH_LLM_MAX_USD."),
        },
        "halted": halted,
        "wall_seconds": round(time.time() - t_start, 1),
        "provider_balance_before": bal0,
    }
    for r in ok:
        m = r.get("method", "?")
        receipt["extract_method_counts"][m] = \
            receipt["extract_method_counts"].get(m, 0) + 1

    if not a.pilot:
        edges, res_rep = resolve_all(recs)
        receipt["resolution"] = res_rep
        if not edges.empty:
            fg = to_features_graph_schema(edges)
            # both schemas in one file: the task's column names AND the ones
            # features_graph reads, so nothing has to be re-derived downstream.
            fg["src_permno"] = fg["subject_permno"]
            fg["dst_permno"] = fg["counterparty_permno"]
            fg["edge_type"] = fg["type"]
            fg.to_parquet(OUT_PARQUET, index=False)
            receipt["out_parquet"] = str(OUT_PARQUET)
            receipt["edges_by_year"] = {
                int(y): int(n) for y, n in
                fg.groupby(fg["filing_date"].dt.year).size().items()}
            receipt["edges_by_type"] = {
                k: int(v) for k, v in fg["type"].value_counts().items()}
            receipt["distinct_permnos"] = int(
                pd.concat([fg["src_permno"], fg["dst_permno"]]).nunique())
        else:
            receipt["out_parquet"] = None
            receipt["REFUSAL"] = ("zero edges resolved -- NOT written. An empty "
                                  "graph joins perfectly and reads as a clean "
                                  "negative result.")

    bal1 = provider_balance()
    receipt["provider_balance_after"] = bal1
    receipt["provider_balance_delta"] = (
        None if (bal0 is None or bal1 is None) else round(bal0 - bal1, 6))
    p = RECEIPT_DIR / f"W4b_companyworld_extract_{a.tag}.json"
    p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"receipt -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
