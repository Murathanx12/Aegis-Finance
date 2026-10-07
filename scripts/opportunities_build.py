"""Build the Opportunity Explorer receipt (chunk C4, 2026-10-06). Offline, $0.

    python -m scripts.opportunities_build                 # writes the receipt
    python -m scripts.opportunities_build --dry-run       # prints coverage only

One JSON per run: `<OPTIMUS_LEDGER_DIR>/opportunities/opportunities_<asof>_<runid>.json`
(run id in the name, so a second run can never overwrite the first). The router
`backend/routers/opportunities.py` serves the newest one -- or, on a server with no raw
receipts at all (a fresh image checkout), the published copy (next paragraph).

Q17 (2026-10-07): a raw receipt is 5-8 MB and SUBSTRATE, never git-tracked
(`.gitignore`); `prune_raw_receipts` keeps only the newest `config.OPPORTUNITIES_KEEP_RAW`
locally, by the run id in the FILENAME, never by mtime. What IS committed is the sanitised,
size-capped copy this script writes through `publish_receipts` after every build
(`publish_public_copy`) -- `backend/data/public_receipts/opportunities/latest.json`, <= 2.4
MB -- which is what the public site actually reads and what `docs/DATA_CATALOG.md`
catalogues as the durable record; the raw folder is local scratch, kept only so the newest
few runs stay inspectable without re-fetching every input.

WHERE EACH LIST COMES FROM (no list is re-ranked here)
------------------------------------------------------
* `roi_v3`, `thesis_cards_v3`, `analyst_upside_v3`: the tables of the stock-list
  build the owner reviewed (`docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md`,
  written by `scripts/stock_lists_v3_build.py` via `scripts/stock_lists_pdf.py`).
  If the build left its machine-readable ROI rows (`<WORK>/roi_list_v3.json`, the
  hook added 2026-10-06) they are preferred; otherwise the committed Markdown
  table is parsed, and `source` says which.
* The books (`human_ai_thematic_v2`, `bloomberg_rehearsal_2026-09-27`, ...): the
  last frozen record per name in `llm_portfolio/books.jsonl`.

WHAT EACH ROW IS ENRICHED WITH, AND FROM WHERE
----------------------------------------------
price / sigma63 ......... llm_portfolio/global_bars.parquet, then prices_2025_26/bars.parquet
analyst targets ......... analyst/target_snapshots.parquet (latest row per ticker), else the MarketWatch snapshot
analyst count / mix ..... stock_lists/<asof>/yf_analyst_v3.json, then the MarketWatch snapshot
revision flow ........... analyst/target_revisions.parquet through services/revision_flow.compute
analyst reputation ...... services/analyst_reputation (C18): per-firm weights from the month's
                          analyst/reputation_weights_<YYYY-MM>.json, every number from the revision file.
                          LABELLED: the weight did not persist out of sample (review C18 F1) -- plumbing,
                          never skill; the weighted target-level upside is DIAGNOSTIC_ONLY, never displayed.
name / why / dates ...... thesis_cards/<newest day>/<ticker>.json
earnings dates .......... the card, straddle_forward/earnings_cache.json, v3_facts EDGAR+91d, MW
insiders ................ official/tables/insider_tx.jsonl (SEC Form 4, EDGAR acceptance time)
short interest .......... official/tables/short_interest.jsonl (FINRA)
politician trades ....... official/tables/politician_trades.jsonl (House PTRs)
news .................... the card's dated news, news_corpus/*/<day>.jsonl, dowjones/_claims, sources/claims.jsonl
exchange / sector ....... ticker suffix; potential_universe/2026-09-02.jsonl identity; config.WHY_MOVED_TICKER_SECTOR

A field nobody can answer is null with `missing_because[field]`. Nothing is guessed.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import opportunities as O  # noqa: E402
from backend.services import publish_receipts as PR  # noqa: E402

OPT = Path(_config.OPTIMUS_LEDGER_DIR)


def newest_stock_list() -> tuple[str, Path, Path]:
    """(asof, WORK dir, rendered Markdown) of the NEWEST stock-list build on disk (F6:
    never a hard-coded date). A day counts only when its WORK dir holds the build's
    inputs AND a rendered `stock_lists_<day>_v*.md` exists; the highest version wins."""
    for d in sorted((OPT / "stock_lists").glob("20*"), reverse=True):
        if not (d / "v3_facts.json").exists() and not (d / "roi_list_v3.json").exists():
            continue
        mds = sorted((REPO / "docs" / "research_notes" / d.name).glob(f"stock_lists_{d.name}_v*.md"),
                     key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem.rsplit("_v", 1)[-1])] or [0])
        if mds:
            return d.name, d, mds[-1]
    raise SystemExit("no stock-list build on disk (stock_lists/<day>/ with a rendered Markdown)")


try:
    STOCK_LISTS_ASOF, WORK, MD_V3 = newest_stock_list()
except SystemExit:  # importable without a build on disk (tests); build() then has only the books
    STOCK_LISTS_ASOF, WORK, MD_V3 = None, OPT / "stock_lists" / "_none", REPO / "docs" / "_no_stock_list.md"
MD_V3_REL = MD_V3.relative_to(REPO).as_posix()

NEWS_LOOKBACK_DAYS = 30
INSIDER_LOOKBACK_DAYS = 180
MAX_NEWS = 8
MAX_CATALYSTS = 6
COVERAGE_MIN_FIRMS = _config.OPPORTUNITIES_COVERAGE_MIN_FIRMS
COVERAGE_WINDOW_DAYS = _config.OPPORTUNITIES_COVERAGE_WINDOW_DAYS
BINARY_WINDOW_SESSIONS = _config.OPPORTUNITIES_BINARY_WINDOW_SESSIONS
RUNWAY_MIN_QUARTERS = _config.OPPORTUNITIES_RUNWAY_MIN_QUARTERS
BADGE_MIN_FLAGS = _config.OPPORTUNITIES_BADGE_MIN_FLAGS
LOW_UPSIDE = _config.OPPORTUNITIES_LOW_UPSIDE
#: F1: an FDA / clinical binary event. Word-bounded so "NDA" does not match "agenda".
BINARY_RE = re.compile(r"\b(pdufa|fda|bla|s?nda|crl|complete response|readout|read-out|top-?line|"
                       r"phase (?:3|iii)|pivotal|advisory committee|adcom|approval decision)\b", re.I)
SIGMA_WINDOW = 63
SIGMA_MIN_OBS = 42
MOVE_SESSIONS = 21

MOVE_EXPLAIN = ("MoveScore = how far this stock may travel over the next 21 trading sessions, UP OR DOWN: "
                "its last 63 sessions of daily volatility x sqrt(21) x sqrt(2/pi). It is a MAGNITUDE, not a forecast of direction.")
DIRECTION_EXPLAIN = ("Analyst stance = the analysts' consensus rating plus the sign of their last 90 days of price-target "
                     "revisions (raises minus cuts). It is what analysts SAY, not a forecast; it never comes from volatility, "
                     "and it can disagree with the upside (a positive stance on a stock already above its median target).")

BOOKS: list[tuple[str, str, Optional[str], str]] = [
    # (list_id, book name, label, title)
    ("human_ai_thematic_v2", "human_ai_thematic_v2", None, "Human + AI thematic book v2 (6-month, vs SPY)"),
    ("human_ai_thematic_v1", "human_ai_thematic_v1", "CONTROL: the un-reviewed v1 of the thematic book",
     "Human + AI thematic book v1 (control)"),
    ("reviewer_opus_2026-09-25", "reviewer_opus_2026-09-25", None, "Adversarial reviewer's book (60% non-USD)"),
    ("cards_supports_2026-09-25", "cards_supports_2026-09-25", None, "Every 'supports' thesis card, equal weight"),
    ("probe_equal_2026-09-26", "probe_equal_2026-09-26", None, "PROBE names, equal weight"),
    ("murat_core_satellite_2026-09-27", "murat_core_satellite_2026-09-27",
     "BENCHMARK_OVERLAY: 80% SPY core + a 20% sleeve; it is the market plus a tilt, never a flagship",
     "Core-satellite (80% SPY)"),
    ("bloomberg_rehearsal_2026-09-27", "bloomberg_rehearsal_2026-09-27",
     "MAGNITUDE RANKING: not a long list. Sorted by expected move SIZE for a contest that pays for movement; "
     "the top names were analyst Sell/Hold with no upside.",
     "Contest rehearsal sheet (Bloomberg dress rehearsal)"),
]


# ───────────────────────────── small helpers ─────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(x: Any) -> Optional[float]:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


_QUOTED = re.compile(r"'([^'\\]*)'|\"([^\"\\]*)\"")


def _listish(v: Any) -> list:
    """A list, or the repr of a list of plain strings (the news corpus stores
    `tickers` as "['TGT']"). Parsed by regex: nothing is evaluated."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip().startswith("["):
        return [a or b for a, b in _QUOTED.findall(v)]
    return []


def _iso_day(s: Any) -> Optional[str]:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else None


def _md_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]


def md_table_after(lines: list[str], heading_pat: str) -> list[dict]:
    """Rows of the first Markdown table after the heading matching `heading_pat`."""
    start = next((i for i, ln in enumerate(lines) if re.match(heading_pat, ln)), None)
    if start is None:
        return []
    hdr, rows = None, []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        if not ln.startswith("|"):
            if hdr is not None and rows:
                break
            continue
        cells = _md_cells(ln)
        if hdr is None:
            hdr = cells
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        rows.append(dict(zip(hdr, cells)))
    return rows


def _pct_cell(s: str) -> Optional[float]:
    m = re.search(r"([+-]?\d+(?:\.\d+)?)%", s or "")
    return float(m.group(1)) / 100.0 if m else None


def _read_jsonl(p: Path) -> list[dict]:
    out = []
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    except OSError:
        pass
    return out


# ───────────────────────────── the lists ─────────────────────────────

def load_books() -> dict[str, dict]:
    recs = _read_jsonl(OPT / "llm_portfolio" / "books.jsonl")
    voided = {r.get("voided_book_id") for r in recs if r.get("kind") == "void"}
    out = {}
    for r in recs:
        if r.get("kind") in ("twin", "void") or r.get("book_id") in voided or "name" not in r:
            continue
        out[r["name"]] = r
    return out


def lists_from_md() -> tuple[list[dict], str]:
    lines = MD_V3.read_text(encoding="utf-8").splitlines() if MD_V3.exists() else []
    out = []
    # ROI list: prefer the build's own JSON rows (hook added 2026-10-06), else the MD table.
    roi_json = WORK / "roi_list_v3.json"
    roi_rows: list[dict] = []
    roi_src = None
    if roi_json.exists():
        blob = json.loads(roi_json.read_text(encoding="utf-8"))
        roi_src = roi_json.relative_to(REPO).as_posix()
        for r in blob.get("ranked", []):
            roi_rows.append({"ticker": r["ticker"], "rank": r["rank"], "list_score": r["score"],
                             "eligibility": "RANKED", "why_list": None, "card": r.get("card"), "n": r.get("n")})
        for r in blob.get("excluded", []):
            roi_rows.append({"ticker": r["ticker"], "rank": None, "list_score": r["score"],
                             "eligibility": "EXCLUDED_BY_v3.2_RULE", "why_list": r.get("why"),
                             "card": r.get("card"), "n": r.get("n")})
    elif lines:
        roi_src = f"{MD_V3_REL} section 3 (parsed Markdown table)"
        for r in md_table_after(lines, r"^# 3\. ROI-MAXING"):
            t = (r.get("Ticker") or "").split()[0]
            m = re.search(r"\(n (\d+)\)", r.get("Ticker") or "")
            roi_rows.append({"ticker": t, "rank": int(r["#"]) if (r.get("#") or "").isdigit() else None,
                             "list_score": _pct_cell(r.get("Score", "")), "eligibility": "RANKED",
                             "why_list": None, "card": r.get("Card"), "n": int(m.group(1)) if m else None})
        for r in md_table_after(lines, r"^## EXCLUDED FROM THE ROI LIST"):
            n = r.get("n analysts")
            roi_rows.append({"ticker": r.get("Ticker"), "rank": None, "list_score": _pct_cell(r.get("Raw score", "")),
                             "eligibility": "EXCLUDED_BY_v3.2_RULE", "why_list": r.get("Reason"),
                             "card": r.get("Card"), "n": int(n) if (n or "").isdigit() else None})
    if roi_rows:
        out.append({"list_id": "roi_v3", "title": "ROI shortlist v3.2 (hypothesis ranking)", "kind": "ranking",
                    "label": "HYPOTHESIS ranking: score = clip(analyst upside, +/- 2 sigma 126 sessions) x card conviction. "
                             "Names the v3.2 eligibility rule excluded (n analysts < 5, research-note veto) are shown, "
                             "marked EXCLUDED, instead of hidden.",
                    "asof": STOCK_LISTS_ASOF, "source": roi_src,
                    "horizon": "21-session check on 2026-10-26; upside bound over 126 sessions",
                    "evidence_default": "OBSERVED", "magnitude_ranking": False, "entries": roi_rows})
    cards = md_table_after(lines, r"^# 2\. THESIS CARDS v3")
    if cards:
        out.append({"list_id": "thesis_cards_v3", "title": "Thesis-card shortlist v3 (60 + 10 names)", "kind": "shortlist",
                    "label": "A verdict is about the EVIDENCE for the bull case (supports / neutral / against), not a price call.",
                    "asof": STOCK_LISTS_ASOF, "source": f"{MD_V3_REL} section 2", "horizon": "per-card falsifier date",
                    "evidence_default": "OBSERVED", "magnitude_ranking": False,
                    "entries": [{"ticker": r.get("Ticker"), "rank": None, "list_score": None, "eligibility": "LISTED",
                                 "why_list": f"shortlist source: {r.get('From')}" if r.get("From") else None,
                                 "card": r.get("Verdict / conf"), "n": None} for r in cards]})
    an = []
    for pat, band in ((r"^## 5a\.", ">= 100% (n >= 5)"), (r"^## 5b\.", "50-100% (n >= 5)")):
        for r in md_table_after(lines, pat):
            n = r.get("n")
            an.append({"ticker": r.get("Ticker"), "rank": None, "list_score": _pct_cell(r.get("Upside", "")),
                       "eligibility": f"band {band}", "why_list": None, "card": None,
                       "n": int(n) if (n or "").isdigit() else None})
    # 5c is printed as a paragraph "TICKER 1177% (n 4); ..." rather than a table
    i5c = next((i for i, ln in enumerate(lines) if ln.startswith("## 5c.")), None)
    if i5c is not None:
        para = next((ln for ln in lines[i5c + 1:i5c + 6] if re.search(r"\(n \d+\)", ln)), "")
        for m in re.finditer(r"([A-Z][A-Z0-9.\-]*) (\d+)% \((?:n )?(\d+|\?|no count)\)", para):
            an.append({"ticker": m.group(1), "rank": None, "list_score": int(m.group(2)) / 100.0,
                       "eligibility": "band >= 50%, fewer than 5 analysts", "why_list": None, "card": None,
                       "n": int(m.group(3)) if m.group(3).isdigit() else None})
    if an:
        out.append({"list_id": "analyst_upside_v3", "title": "Analyst-implied upside >= 50% (screen)", "kind": "screen",
                    "label": "SCREEN, not a buy list: target-LEVEL upside measured PERVERSE in this repo (-90 bps/month large/mid, "
                             "-199 small). High upside most often means the price fell and targets have not caught up.",
                    "asof": STOCK_LISTS_ASOF, "source": f"{MD_V3_REL} section 5a/5b/5c", "horizon": None,
                    "evidence_default": "OBSERVED", "magnitude_ranking": False, "entries": an})
    return out, MD_V3_REL


def lists_from_books(books: dict[str, dict]) -> list[dict]:
    out = []
    for list_id, name, label, title in BOOKS:
        b = books.get(name)
        if not b:
            continue
        entries = []
        for p in sorted(b.get("positions") or [], key=lambda p: -float(p.get("weight") or 0)):
            if str(p.get("ticker")).upper() == "CASH":
                continue  # declared cash is the list's `cash_weight`, not a security row
            entries.append({"ticker": p["ticker"], "rank": None, "weight": float(p.get("weight") or 0),
                            "list_score": None, "eligibility": "HELD", "why_list": None, "card": None, "n": None,
                            "thesis": p.get("thesis"), "falsifier": p.get("falsifier"),
                            "theme": p.get("theme"), "theme_source": p.get("theme_source"),
                            "is_etf": bool(p.get("is_etf"))})
        hz = b.get("horizon_days")
        hz = [int(x) for x in re.findall(r"\d+", hz)] if isinstance(hz, str) else (hz or [])
        out.append({"list_id": list_id, "title": title, "kind": "book", "label": label,
                    "asof": b.get("asof"), "frozen_utc": b.get("frozen_utc"), "book_id": b.get("book_id"),
                    "benchmark": b.get("benchmark"), "objective": b.get("objective"),
                    "cash_weight": _finite(b.get("cash_weight")),
                    "source": f"backend/data/optimus/llm_portfolio/books.jsonl (book_id {b.get('book_id')})",
                    "horizon": f"{max(hz)} sessions" if hz else None,
                    "evidence_default": "EARLY_EVIDENCE", "magnitude_ranking": list_id.startswith("bloomberg_rehearsal"),
                    "entries": entries})
    return out


# ───────────────────────────── enrichment sources ─────────────────────────────

def load_bars(tickers: set[str]) -> pd.DataFrame:
    g = pd.read_parquet(OPT / "llm_portfolio" / "global_bars.parquet", columns=["symbol", "date", "close", "source"])
    g = g[g["symbol"].isin(tickers | {"SPY"})]
    miss = sorted(tickers - set(g["symbol"]))
    if miss:
        p = OPT / "prices_2025_26" / "bars.parquet"
        if p.exists():
            b = pd.read_parquet(p, columns=["symbol", "date", "close"], filters=[("symbol", "in", miss)])
            b["source"] = "prices_2025_26/bars.parquet"
            g = pd.concat([g, b], ignore_index=True)
    g["date"] = pd.to_datetime(g["date"])
    return g.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")


def price_and_sigma(bars: pd.DataFrame) -> dict[str, dict]:
    out = {}
    for sym, df in bars.groupby("symbol"):
        df = df.dropna(subset=["close"])
        if df.empty:
            continue
        last = df.iloc[-1]
        closes = df["close"].values[-(SIGMA_WINDOW + 1):]
        closes = closes[closes > 0]
        lr = np.diff(np.log(closes)) if len(closes) > 1 else np.array([])
        sig = float(np.std(lr, ddof=1)) if len(lr) >= SIGMA_MIN_OBS else None
        src = last.get("source")
        out[sym] = {"close": float(last["close"]), "date": str(last["date"].date()),
                    "source": "llm_portfolio/global_bars.parquet (yfinance)" if src == "yfinance" else str(src),
                    "sigma63": sig, "n_obs": int(len(lr))}
    return out


def load_targets() -> dict[str, dict]:
    s = pd.read_parquet(OPT / "analyst" / "target_snapshots.parquet")
    s = s.sort_values("observed_at").groupby("ticker").tail(1)
    return {r.ticker: {"low": _finite(r.target_low), "median": _finite(r.target_median), "high": _finite(r.target_high),
                       "mean": _finite(r.target_mean), "snapshot_price": _finite(r.price),
                       "observed_utc": str(r.observed_at)}
            for r in s.itertuples()}


def load_yf() -> dict:
    p = WORK / "yf_analyst_v3.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_mw() -> dict:
    out = {}
    for r in _read_jsonl(OPT / "news_corpus" / "dowjones" / "_structured" / "mw_analyst_snapshot.jsonl"):
        if r.get("ticker"):
            out[r["ticker"]] = r
    return out


def load_revisions(tickers: set[str], asof: pd.Timestamp) -> tuple[dict, Optional[str]]:
    try:
        from backend.services import revision_flow as RF
        rv = pd.read_parquet(OPT / "analyst" / "target_revisions.parquet")
        rv = rv[rv["ticker"].isin(tickers)]
        n_all = len(rv)
        if "pit_safe" in rv.columns:
            rv = rv[rv["pit_safe"] == True]  # noqa: E712  the service refuses non-PIT rows; dropped and counted
        flow = RF.compute(rv, asof=asof)
        pulled = str(rv["pulled_at"].max()) if len(rv) else None
        return ({t: {k: _finite(v) for k, v in row.items()} for t, row in flow.iterrows()},
                f"pulled {pulled}; rows used {len(rv)} of {n_all} (non-PIT rows dropped)")
    except Exception as e:  # noqa: BLE001  a missing flow is a null with a reason, never a crash
        return {}, f"ERROR {type(e).__name__}: {e}"


def load_reputation(now: datetime, *, write: bool = True) -> dict:
    """C18: the month's reputation weights + the revision rows FIRST SEEN before now.
    `write=False` (dry run) computes in memory and writes nothing (review F11).
    A failure is a named ERROR carried onto every row's missing_because, never a raise."""
    from backend.services import analyst_reputation as AR  # noqa: PLC0415
    try:
        asof = pd.Timestamp(now.astimezone(timezone.utc).replace(tzinfo=None))
        rv = AR.load_revisions()
        blob, path, fresh = AR.monthly_receipt(asof, rv=rv, write=write)
        where = path.relative_to(REPO).as_posix() if path else "in memory (dry run: nothing written)"
        pit = blob.get("pit") or {}
        return {"known": AR.known_before(rv, asof), "tabs": AR.tables_from_receipt(blob),
                "sectors": AR.load_identity_sectors(),
                "label": blob.get("label") or AR.PERSISTENCE_LABEL_UNKNOWN,
                "pit_status": pit.get("status"),
                "source": (f"services/analyst_reputation over {where} "
                           f"(weights as of {blob.get('asof')}; {'written by this run' if fresh else 'read back'}); "
                           f"rows first seen before {asof.isoformat(timespec='minutes')} UTC; "
                           f"PIT {pit.get('status')}"),
                "receipt": where, "weights_asof": blob.get("asof"),
                "asof": asof, "error": None}
    except Exception as exc:                                        # noqa: BLE001
        return {"error": f"ERROR {type(exc).__name__}: {str(exc)[:200]}"}


def reputation_for(t: str, sector: Optional[str], price: Optional[float], rep: dict) -> tuple[Optional[dict], Optional[str]]:
    """(consensus, why-missing). Sector falls back exactly as the reputation receipt's does."""
    if rep.get("error"):
        return None, f"analyst reputation unavailable: {rep['error']}"
    from backend.services import analyst_reputation as AR  # noqa: PLC0415
    sec = _config.WHY_MOVED_TICKER_SECTOR.get(t) or rep["sectors"].get(t) or "UNKNOWN"
    c = AR.ticker_consensus(rep["known"], t, sec, rep["tabs"], rep["asof"], price=price)
    if c is None:
        return None, f"no firm with a dated target action on this ticker in the last {AR.COVER_DAYS} days"
    c["source"] = rep["source"]
    c["receipt"] = rep["receipt"]
    c["label"] = rep.get("label") or AR.PERSISTENCE_LABEL_UNKNOWN
    c["pit_status"] = rep.get("pit_status")
    return c, None


def load_cards() -> dict[str, list[tuple[str, dict]]]:
    """EVERY card per ticker, oldest day first: [(day, card), ...]. F5: "why picked" may
    only quote a card dated on or before the list's freeze; a later one is commentary."""
    out: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for day_dir in sorted(glob.glob(str(OPT / "thesis_cards" / "20*"))):
        day = Path(day_dir).name
        for f in glob.glob(str(Path(day_dir) / "*.json")):
            if Path(f).name.startswith("_"):
                continue
            try:
                c = json.loads(Path(f).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(c, dict) or "ticker" not in c or str(c.get("verdict", "")).startswith("REFUSED"):
                continue
            out[c["ticker"]].append((day, c))
    return out


def cards_split(cards: list[tuple[str, dict]], freeze: Optional[str]) -> tuple:
    """(pre_day, pre_card, now_day, now_card): the newest card on or before `freeze`
    and the newest card overall. No freeze date -> the pre card is None."""
    pre = [(d, c) for d, c in cards if freeze and d <= str(freeze)[:10]]
    pre_day, pre_card = pre[-1] if pre else (None, None)
    now_day, now_card = cards[-1] if cards else (None, None)
    return pre_day, pre_card, now_day, now_card


def dated_firms(tickers: set[str], today: pd.Timestamp) -> tuple[dict[str, int], str]:
    """F1 coverage: DISTINCT firms with a dated target action in the last
    COVERAGE_WINDOW_DAYS before `today` (strictly before; PIT rows only)."""
    try:
        rv = pd.read_parquet(OPT / "analyst" / "target_revisions.parquet",
                             columns=["ticker", "event_date", "firm", "pit_safe", "pulled_at"])
    except Exception as e:  # noqa: BLE001
        return {}, f"ERROR {type(e).__name__}: {e}"
    rv = rv[rv["ticker"].isin(tickers) & (rv["pit_safe"] == True)]  # noqa: E712
    d = pd.to_datetime(rv["event_date"], errors="coerce")
    lo = today - pd.Timedelta(days=COVERAGE_WINDOW_DAYS)
    rv = rv[(d >= lo) & (d < today)]
    through = str(pd.to_datetime(rv["pulled_at"]).max())[:10] if len(rv) else None
    return rv.groupby("ticker")["firm"].nunique().astype(int).to_dict(), f"target_revisions.parquet, pulled through {through}"


def runway_table(tickers: set[str], today: str) -> dict[str, dict]:
    """F1 runway: cash and equivalents / the latest QUARTERLY operating loss (80-100-day
    period, filed on or before today) from sec_facts_history.parquet. A LOWER bound:
    the XBRL tag pulled is CashAndCashEquivalents, which excludes marketable securities."""
    p = OPT / "fundamentals_sec" / "sec_facts_history.parquet"
    if not p.exists():
        return {}
    h = pd.read_parquet(p, columns=["ticker", "fact", "filed", "end", "period_days", "val"],
                        filters=[("ticker", "in", sorted(tickers)), ("fact", "in", ["cash", "operating_income"])])
    h = h[pd.to_datetime(h["filed"]) <= pd.Timestamp(today)]
    out = {}
    for t, x in h.groupby("ticker"):
        cash = x[x["fact"] == "cash"].sort_values("filed").tail(1)
        oi = x[(x["fact"] == "operating_income") & x["period_days"].between(80, 100)].sort_values("filed").tail(1)
        if cash.empty or oi.empty:
            continue
        c, q = float(cash["val"].iloc[0]), float(oi["val"].iloc[0])
        out[t] = {"cash_usd": c, "cash_end": str(cash["end"].iloc[0]), "op_income_q_usd": q,
                  "quarter_end": str(oi["end"].iloc[0]), "filed": str(oi["filed"].iloc[0])[:10],
                  "quarters": (round(c / -q, 2) if q < 0 else None),
                  "source": "SEC XBRL (sec_facts_history.parquet): CashAndCashEquivalents / quarterly operating loss; "
                            "a LOWER bound (marketable securities are not in the tag)"}
    return out


def risk_checks(n_dated: Optional[int], cats: list[dict], runway: Optional[dict], today: str,
                *, is_etf: bool = False) -> dict:
    """F1: three SEPARATE checks; each is {on: True/False/None, detail}. None = cannot
    determine, with the reason in `detail`. The badge needs BADGE_MIN_FLAGS of them on."""
    if is_etf:
        return {k: {"on": False, "detail": "ETF"} for k in ("coverage", "binary_event", "runway")}
    cov = ({"on": n_dated < COVERAGE_MIN_FIRMS,
            "detail": f"{n_dated} firm(s) with a dated target action in {COVERAGE_WINDOW_DAYS} days "
                      f"(flag below {COVERAGE_MIN_FIRMS})"}
           if n_dated is not None else {"on": None, "detail": "no revision data loaded"})
    hits = []
    for c in cats:
        txt = f"{c.get('kind') or ''} {c.get('detail') or ''}"
        if BINARY_RE.search(txt):
            n = int(np.busday_count(today, c["date"])) if c["date"] >= today else -1
            if 0 <= n <= BINARY_WINDOW_SESSIONS:
                hits.append(f"{c['date']} {c['kind']}: {(c.get('detail') or '')[:80]} ({n} weekdays away)")
    binary = {"on": bool(hits), "detail": "; ".join(hits) if hits else
              f"no FDA/trial event within {BINARY_WINDOW_SESSIONS} weekdays among the dated catalysts"}
    if runway is None:
        rw = {"on": None, "detail": "no XBRL cash + quarterly operating income on file (foreign filer, ETF or not pulled)"}
    elif runway["quarters"] is None:
        rw = {"on": False, "detail": f"operating income positive in the quarter to {runway['quarter_end']}"}
    else:
        rw = {"on": runway["quarters"] < RUNWAY_MIN_QUARTERS,
              "detail": f"cash ${runway['cash_usd']/1e6:,.1f}M / quarterly operating loss "
                        f"${-runway['op_income_q_usd']/1e6:,.1f}M = {runway['quarters']} quarters "
                        f"(flag below {RUNWAY_MIN_QUARTERS}; lower bound, cash excludes marketable securities)"}
    return {"coverage": cov, "binary_event": binary, "runway": rw}


def load_facts() -> dict:
    p = WORK / "v3_facts.json"
    return json.loads(p.read_text(encoding="utf-8")).get("names", {}) if p.exists() else {}


def load_identity() -> dict:
    out = {}
    for r in _read_jsonl(OPT / "potential_universe" / "2026-09-02.jsonl"):
        if "symbol" in r and isinstance(r.get("identity"), dict):
            out[r["symbol"]] = r["identity"]
    return out


def load_ciks() -> dict[str, str]:
    p = OPT / "official" / "company_tickers.json"
    if not p.exists():
        return {}
    m = json.loads(p.read_text(encoding="utf-8")).get("map", {})
    return {t: cik for cik, t in m.items()}


def load_official(tickers: set[str], now: datetime) -> dict:
    base = OPT / "official" / "tables"
    since = now - timedelta(days=INSIDER_LOOKBACK_DAYS)
    ins: dict[str, list] = defaultdict(list)
    first_pub = None
    names: dict[str, str] = {}
    for r in _read_jsonl(base / "insider_tx.jsonl"):
        pu = r.get("public_utc")
        if pu and (first_pub is None or pu < first_pub):
            first_pub = pu
        t = r.get("ticker")
        if t in tickers:
            if r.get("issuer_name"):
                names.setdefault(t, r["issuer_name"])
            try:
                if datetime.fromisoformat(pu) >= since:
                    ins[t].append(r)
            except (TypeError, ValueError):
                continue
    si: dict[str, dict] = {}
    for r in _read_jsonl(base / "short_interest.jsonl"):
        t = r.get("ticker") or r.get("symbol")
        if t in tickers and (t not in si or str(r.get("settlement_date")) > str(si[t].get("settlement_date"))):
            si[t] = r
    pol: dict[str, list] = defaultdict(list)
    for r in _read_jsonl(base / "politician_trades.jsonl"):
        t = r.get("ticker")
        if t in tickers:
            try:
                if datetime.fromisoformat(r.get("public_utc")) >= since:
                    pol[t].append(r)
            except (TypeError, ValueError):
                continue
    return {"insiders": ins, "insider_table_first_public_utc": first_pub, "issuer_names": names,
            "short_interest": si, "politicians": pol}


#: search pages, Google News redirect stubs, and the reader's visits to a quote or
#: analyst-estimates PAGE (already linked from every row) are not news items.
_BAD_URL = re.compile(r"/search\?|news\.google\.com/rss|/investing/stock/[^/?#]+(/analystestimates)?/?$")


def load_news(tickers: set[str], today: date) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    days = {(today - timedelta(days=i)).isoformat() for i in range(NEWS_LOOKBACK_DAYS + 1)}
    nc = OPT / "news_corpus"
    for f in glob.glob(str(nc / "*" / "20*.jsonl")):
        if Path(f).stem not in days:
            continue
        src = Path(f).parent.name
        for r in _read_jsonl(Path(f)):
            hit = [t for t in _listish(r.get("tickers")) if t in tickers]
            url, title = r.get("url") or "", r.get("title") or ""
            if not hit or _BAD_URL.search(url) or not url.startswith("http") or title in ("", "read_next"):
                continue
            for t in hit:
                out[t].append({"title": title[:200], "url": url, "published_utc": r.get("published_utc") or None,
                               "first_seen_utc": r.get("first_seen_utc"), "source": src})
    for f in glob.glob(str(nc / "dowjones" / "_claims" / "20*.jsonl")):
        if Path(f).stem not in days:
            continue
        for r in _read_jsonl(Path(f)):
            t = r.get("ticker")
            if t in tickers and str(r.get("url", "")).startswith("http"):
                out[t].append({"title": (r.get("paraphrase") or r.get("quote") or "")[:200], "url": r["url"],
                               "published_utc": r.get("published_utc") or None, "first_seen_utc": r.get("first_seen_utc"),
                               "source": f"dowjones claim ({r.get('source_id')})"})
    for r in _read_jsonl(OPT / "sources" / "claims.jsonl"):
        t = r.get("ticker")
        if t in tickers and str(r.get("post_url", "")).startswith("http") and (_iso_day(r.get("claim_utc")) or "") in days:
            out[t].append({"title": (r.get("claim_text") or "")[:200], "url": r["post_url"],
                           "published_utc": r.get("claim_utc"), "first_seen_utc": r.get("observed_utc"),
                           "source": f"reader claim ({r.get('source_id')})"})
    return out


def load_earnings_cache() -> dict:
    p = OPT / "straddle_forward" / "earnings_cache.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def sessions_since(spy_dates: list[str], asof: Optional[str]) -> Optional[int]:
    if not asof:
        return None
    return sum(1 for d in spy_dates if d > asof)


# ───────────────────────────── the row ─────────────────────────────

CONS_SIGN = {"strong_buy": 1, "buy": 1, "outperform": 1, "overweight": 1, "hold": 0, "neutral": 0,
             "equal-weight": 0, "underperform": -1, "underweight": -1, "sell": -1, "strong_sell": -1}


def build_row(e: dict, lst: dict, ctx: dict) -> dict:
    t = e["ticker"]
    miss: dict[str, str] = {}
    foreign = O.is_foreign(t)
    freeze = lst.get("asof")
    pre_day, pre_card, card_day, card = cards_split(ctx["cards"].get(t, []), freeze)
    facts = ctx["facts"].get(t, {})
    yf = ctx["yf"].get(t) or {}
    mw = ctx["mw"].get(t) or {}
    ident = ctx["identity"].get(t) or {}
    px = ctx["px"].get(t)
    tg = ctx["targets"].get(t)
    rv = ctx["revisions"].get(t)
    is_etf = bool(e.get("is_etf"))

    # identity
    name, name_src = None, None
    for cand, src in (((card or {}).get("name"), f"thesis card {card_day}"),
                      (ctx["official"]["issuer_names"].get(t), "SEC Form 4 issuer name"),
                      (yf.get("name"), "yfinance (2026-09-27 pull; may be truncated)"),
                      ((ctx["official"]["short_interest"].get(t) or {}).get("issue_name"), "FINRA short-interest issue name")):
        if cand:
            name, name_src = str(cand), src
            break
    if not name:
        miss["company_name"] = ("ETF: no company-name receipt" if is_etf else
                                "no card, Form 4, yfinance or FINRA row names this ticker")
    if foreign:
        exchange, currency = O.exchange_of(t)
        ex_src = "ticker suffix convention" if exchange else None
        if exchange is None:
            miss["exchange"] = (f"ticker suffix '.{O.split_suffix(t)[1]}' has no mapping in "
                                "services/opportunities.SUFFIX_EXCHANGE")
            miss["currency"] = "follows the exchange"
    else:
        exchange, currency = ident.get("exchange"), "USD"
        ex_src = "potential_universe 2026-09-02 identity (Alpaca asset)" if exchange else None
        if not exchange:
            miss["exchange"] = "not in the 2026-09-02 potential-universe identity file"

    # sector
    sector, sector_src = None, None
    if t in _config.WHY_MOVED_TICKER_SECTOR:
        sector, sector_src = _config.WHY_MOVED_TICKER_SECTOR[t], "GICS sector declared in config.WHY_MOVED_TICKER_SECTOR"
    elif ident.get("sector"):
        sector, sector_src = ident["sector"], "industry label, potential_universe 2026-09-02 (Alpaca)"
    theme = e.get("theme")
    if not sector:
        miss["sector"] = ("no sector receipt for this ticker (no GICS/industry row on disk)"
                          + ("; the book's theme is shown instead" if theme else ""))

    # price
    price = None
    if px:
        price = {"value": round(px["close"], 4), "date": px["date"], "source": px["source"], "currency": currency}
    else:
        miss["price"] = "no bar in global_bars or prices_2025_26 for this ticker"

    # analyst reputation (C18): weights, never a gate
    rep, rep_miss = reputation_for(t, sector, (price or {}).get("value") if not foreign else None,
                                   ctx.get("reputation") or {"error": "reputation context not loaded"})
    if rep_miss:
        miss["analyst_reputation"] = rep_miss

    # analysts
    n_an, n_src = None, None
    if yf.get("n") is not None:
        n_an, n_src = int(yf["n"]), f"yfinance numberOfAnalystOpinions, fetched {str(yf.get('fetched_utc'))[:10]}"
    elif mw.get("n_analysts") is not None:
        n_an, n_src = int(mw["n_analysts"]), f"MarketWatch analyst page, read {str(mw.get('first_seen_utc'))[:10]}"
    elif e.get("n") is not None:
        n_an, n_src = int(e["n"]), f"stock list v3 table ({STOCK_LISTS_ASOF})"
    analyst = None
    upside = None
    if tg and any(tg.get(k) is not None for k in ("low", "median", "high")):
        analyst = {**{k: tg[k] for k in ("low", "median", "high", "mean")}, "n": n_an, "n_source": n_src,
                   "observed_utc": tg["observed_utc"], "snapshot_price": tg["snapshot_price"],
                   "source": "analyst/target_snapshots.parquet (latest row)",
                   # yfinance writes the string "none" when there is no rating: that is absence, not a rating
                   "consensus": (yf.get("key") if yf.get("key") not in (None, "", "none") else None)
                   or mw.get("consensus_rating"), "mix": yf.get("counts")}
    elif mw.get("target_median") is not None or mw.get("target_mean") is not None:
        analyst = {"low": _finite(mw.get("target_low")), "median": _finite(mw.get("target_median")),
                   "high": _finite(mw.get("target_high")), "mean": _finite(mw.get("target_mean")), "n": n_an,
                   "n_source": n_src, "observed_utc": mw.get("first_seen_utc"),
                   "snapshot_price": _finite(mw.get("current_price")),
                   "source": "MarketWatch analyst snapshot", "consensus": mw.get("consensus_rating"), "mix": None}
    if analyst:
        base = price["value"] if price else analyst.get("snapshot_price")
        if base and not foreign:
            upside = {k: (round(analyst[k] / base - 1.0, 4) if analyst.get(k) else None) for k in ("low", "median", "high")}
            upside["basis"] = (f"vs last close {price['date']}" if price else "vs the snapshot's own price")
        else:
            miss["upside"] = "no price in the targets' currency to compare them with"
    else:
        miss["analyst"] = ("ETF: no analyst targets" if is_etf else
                           "foreign listing: the analyst snapshot covers US tickers only" if foreign else
                           "no target row in target_snapshots.parquet or the MarketWatch snapshot")
        miss["upside"] = "no analyst target to compare with"
    if analyst and n_an is None:
        miss["analyst.n"] = "no analyst count from yfinance, MarketWatch or the list table"
    if upside is not None:
        med = upside.get("median")
        single = bool(analyst and analyst.get("low") is not None and analyst.get("low") == analyst.get("high")) or n_an == 1
        upside["n_targets"] = n_an          # yfinance opinion count: never compared with the revision file
        if rep and e.get("why_list") and "n < 5" in str(e.get("why_list")):
            # review F4: the replacement numbers come from ONE source (the revision file)
            # and are not set against the yfinance count above
            upside["cliff_replaced"] = {"old_rule": "n analysts >= 5 (stock lists v3.2)",
                                        "n_covering_firms": rep.get("n_covering_firms"),
                                        "sum_of_weights": rep.get("sum_of_weights"),
                                        "label": rep.get("label"),
                                        "note": "the list's frozen rule still excluded it; coverage is printed, not gated"}
        upside["single_target"] = single
        upside["low_upside"] = (med is not None and med < LOW_UPSIDE)
        upside["low_upside_threshold"] = LOW_UPSIDE
        upside["targets_date"] = str((analyst or {}).get("observed_utc") or "")[:10] or None
        upside["price_date"] = price["date"] if price else None

    # revisions
    revision = None
    if rv:
        revision = {"net_raises_90d": rv.get("net_raises"), "n_firms_90d": rv.get("n_firms"),
                    "median_target_change_90d": rv.get("median_target_change"), "n_events_90d": rv.get("n_events"),
                    "asof": ctx["asof"], "source": "services/revision_flow.compute over analyst/target_revisions.parquet",
                    "pulled": ctx["revisions_pulled"]}
    else:
        miss["revision"] = (f"revision flow failed: {ctx['revisions_pulled']}"
                            if str(ctx["revisions_pulled"]).startswith("ERROR")
                            else "no dated target revision in the 90 days before today (absent, not zero)")

    # magnitude
    move = None
    if px and px.get("sigma63"):
        m21 = px["sigma63"] * math.sqrt(MOVE_SESSIONS) * math.sqrt(2.0 / math.pi)
        move = {"label": "MAGNITUDE", "expected_abs_move_21s": round(m21, 4), "sigma63_daily": round(px["sigma63"], 5),
                "bars_to": px["date"], "explain": MOVE_EXPLAIN}
    else:
        miss["move_score"] = (f"fewer than {SIGMA_MIN_OBS} daily returns in the last {SIGMA_WINDOW} sessions"
                              if px else "no bars")

    # direction (never from sigma)
    cons_key = str((analyst or {}).get("consensus") or "").strip().lower().replace(" ", "_")
    c_sign = CONS_SIGN.get(cons_key)
    r_sign = None
    if revision and revision.get("net_raises_90d") is not None and (revision.get("n_firms_90d") or 0) >= 1:
        nr = revision["net_raises_90d"]
        r_sign = 1 if nr > 0 else (-1 if nr < 0 else 0)
    if c_sign is None and r_sign is None:
        stance = None
        miss["analyst_stance"] = "neither an analyst consensus rating nor a 90-day revision flow exists for this name"
    else:
        tot = (c_sign or 0) + (r_sign or 0)
        lab = "POSITIVE" if tot > 0 else ("NEGATIVE" if tot < 0 else "NEUTRAL")
        if c_sign and r_sign and c_sign != r_sign:
            lab = "MIXED"   # the rating and the revisions point opposite ways
        med_up = (upside or {}).get("median")
        stance = {"label": lab, "consensus": cons_key or None, "consensus_sign": c_sign,
                  "revision_sign": r_sign, "single_source": (c_sign is None) or (r_sign is None),
                  "conflicts_with_upside": bool(lab == "POSITIVE" and med_up is not None and med_up < 0),
                  "revisions_through": ctx.get("revision_through"),
                  "explain": DIRECTION_EXPLAIN}

    # why picked (1-3, each naming its service)
    why: list[dict] = []
    if lst["kind"] == "book" and e.get("thesis"):
        why.append({"reason": str(e["thesis"])[:300],
                    "service": f"llm_portfolio book {lst['list_id']} (frozen {str(lst.get('frozen_utc'))[:10]})"})
    if lst["list_id"] == "roi_v3" and e.get("list_score") is not None:
        why.append({"reason": (f"ROI hypothesis score {e['list_score']*100:+.1f}% (rank {e['rank']})" if e.get("rank")
                               else f"raw ROI score {e['list_score']*100:+.1f}%, EXCLUDED: {e.get('why_list')}"),
                    "service": "scripts/stock_lists_v3_build.py section 3 (clip(U, +/-2 sigma126) x card conviction)"})
    if lst["list_id"] == "analyst_upside_v3" and e.get("list_score") is not None:
        why.append({"reason": f"analyst mean-target upside {e['list_score']*100:.0f}% on {STOCK_LISTS_ASOF} ({e.get('eligibility')})",
                    "service": "analyst target snapshot screen (stock lists v3 section 5; level upside measured perverse)"})
    if e.get("why_list") and lst["list_id"] == "thesis_cards_v3":
        why.append({"reason": e["why_list"], "service": "stock lists v3 shortlist assembly"})
    if pre_card:
        vc = f"{pre_card.get('verdict')}/{pre_card.get('confidence')}"
        bull = str(pre_card.get("bull") or "")[:220]
        when = (f"same day as the {str(freeze)[:10]} freeze; the card records no run time, so the order is not provable"
                if pre_day == str(freeze)[:10] else f"before the {str(freeze)[:10]} freeze")
        why.append({"reason": f"thesis card {pre_day} ({when}): {vc}"
                              + (f" -- {bull}" if bull and bull != "None" else ""),
                    "service": "thesis_cards (OpenClaw web pass + DeepSeek synthesis)"})
    # F5: no fundamentals "filler" reason: no list here was ranked on it except the
    # core-satellite sleeve, whose own thesis line already says so.
    why = why[:3]
    if not why:
        miss["why_picked"] = (f"the list carries no per-name reason and no thesis card is dated on or before "
                              f"its {str(freeze)[:10]} freeze")
    later = None
    if card and card_day and (pre_day is None or card_day > pre_day) and freeze and card_day > str(freeze)[:10]:
        bull = str(card.get("bull") or "")[:300]
        later = {"day": card_day, "verdict": card.get("verdict"), "confidence": card.get("confidence"),
                 "text": bull if bull and bull != "None" else None,
                 "note": f"written {card_day}, AFTER the list froze on {str(freeze)[:10]}: not a reason it was picked"}

    # catalysts
    today = ctx["today"]
    cats: list[dict] = []
    for u in _listish((card or {}).get("upcoming_dates")):
        parts = [p.strip() for p in str(u).split("|")]
        d = _iso_day(parts[0])
        if d and d >= today:
            url = next((p for p in parts if p.startswith("http")), None)
            cats.append({"date": d, "kind": parts[1] if len(parts) > 1 else "event",
                         "detail": parts[2][:200] if len(parts) > 2 else None, "url": url,
                         "source": f"thesis card {card_day}"})
    ec = ctx["earn_cache"].get(t) or {}
    fut = sorted(d for d in ec.get("dates") or [] if d >= today)
    if fut:
        cats.append({"date": fut[0], "kind": "earnings", "detail": None, "url": None,
                     "source": f"straddle_forward earnings cache (pulled {str(ec.get('pulled_utc'))[:10]})"})

    def has_earn() -> bool:
        return any(c["kind"].lower().startswith("earn") for c in cats)

    if facts.get("earn_est") and str(facts["earn_est"]) >= today and not has_earn():
        cats.append({"date": facts["earn_est"], "kind": "earnings (ESTIMATE)",
                     "detail": f"last 8-K item 2.02 {facts.get('last_202')} + 91 days", "url": None,
                     "source": "EDGAR + 91d estimate (v3_facts)"})
    if mw.get("next_earnings_date") and not has_earn():
        try:
            d = str(pd.Timestamp(mw["next_earnings_date"]).date())
            if d >= today:
                cats.append({"date": d, "kind": "earnings", "detail": None, "url": mw.get("url"),
                             "source": "MarketWatch analyst page"})
        except (ValueError, TypeError):
            pass
    seen: set = set()
    uniq_c = []
    for c in sorted(cats, key=lambda c: c["date"]):
        k = (c["date"], c["kind"])
        if k not in seen:
            seen.add(k)
            uniq_c.append(c)
    cats = uniq_c[:MAX_CATALYSTS]
    if not cats:
        miss["catalysts"] = (f"no dated future event in the card, the earnings cache, the EDGAR estimate or "
                             f"MarketWatch (as of {today})")

    # news
    news = []
    for n in _listish((card or {}).get("news_30d_top")):
        parts = [p.strip() for p in str(n).split("|")]
        url = next((p for p in parts if p.startswith("http")), None)
        if url and _iso_day(parts[0]):
            news.append({"title": (parts[2] if len(parts) > 2 else parts[-1])[:200], "url": url,
                         "published_utc": parts[0], "first_seen_utc": None,
                         "source": f"thesis card {card_day} ({parts[1] if len(parts) > 1 else 'news'})"})
    # Corpus items carry the collector's ticker TAG, which can be wrong (a robotics column tagged
    # VKTX on 2026-10-02). Keep one only when its title names the ticker or the company.
    root = O.split_suffix(t)[0]
    name_tok = next((w for w in re.findall(r"[A-Za-z][A-Za-z&\-]{3,}", name or "")
                     if w.lower() not in {"corp", "corporation", "holdings", "group", "company", "incorporated", "limited",
                                          "the", "class", "common", "shares", "technologies", "therapeutics", "inc"}), None)
    tick_re = (re.compile(rf"(?<![A-Za-z0-9]){re.escape(root)}(?![A-Za-z0-9])") if len(root) >= 2 else None)
    name_re = re.compile(rf"\b{re.escape(name_tok)}\b", re.I) if name_tok else None

    def _relevant(title: str) -> bool:
        return bool((tick_re and tick_re.search(title)) or (name_re and name_re.search(title)))

    kept = [n for n in ctx["news"].get(t, []) if _relevant(n.get("title") or "")]
    if len(kept) < len(ctx["news"].get(t, [])):
        miss["news.dropped"] = (f"{len(ctx['news'].get(t, [])) - len(kept)} tagged item(s) dropped: the title names "
                                "neither the ticker nor the company")
    news += kept
    uniq, seen_u = [], set()
    for n in sorted(news, key=lambda n: str(n.get("published_utc") or n.get("first_seen_utc") or ""), reverse=True):
        tkey = re.sub(r"\W+", " ", (n.get("title") or "").lower()).strip()[:80]
        if n["url"] in seen_u or (tkey and tkey in seen_u):
            continue
        seen_u.add(n["url"])
        seen_u.add(tkey)
        uniq.append(n)
    news = uniq[:MAX_NEWS]
    if not news:
        miss["news"] = (f"no ticker-tagged item with a URL in the last {NEWS_LOOKBACK_DAYS} days "
                        "(news corpus, DJ claims, reader claims, thesis card)")

    # insiders / holders
    off = ctx["official"]
    disc = [r for r in off["insiders"].get(t, []) if r.get("code") in ("P", "S") and not r.get("is_derivative")]
    insiders = None
    cov_from = str(off["insider_table_first_public_utc"] or "")[:10] or None
    eff_days = ctx.get("insider_window_days", INSIDER_LOOKBACK_DAYS)
    if disc:
        buys = [r for r in disc if r.get("code") == "P"]
        sells = [r for r in disc if r.get("code") == "S"]
        insiders = {"window_days": eff_days, "covers_from": cov_from, "n_buys": len(buys), "n_sells": len(sells),
                    "buy_usd": round(sum(_finite(r.get("value_usd")) or 0 for r in buys)),
                    "sell_usd": round(sum(_finite(r.get("value_usd")) or 0 for r in sells)),
                    "n_insiders": len({r.get("owner_name") for r in disc}),
                    "n_10b5_1": sum(1 for r in disc if r.get("rule_10b5_1") is True),
                    "recent": [{"public_utc": r.get("public_utc"), "transaction_date": r.get("transaction_date"),
                                "owner": r.get("owner_name"), "role": r.get("officer_title") or r.get("role"),
                                "side": "BUY" if r.get("code") == "P" else "SELL", "shares": _finite(r.get("shares")),
                                "value_usd": _finite(r.get("value_usd")), "rule_10b5_1": r.get("rule_10b5_1"),
                                "url": r.get("index_url")}
                               for r in sorted(disc, key=lambda r: str(r.get("public_utc")), reverse=True)[:5]],
                    "source": "SEC Form 4 via services/official_sources (insider_tx), open-market P/S only",
                    "table_covers_from_utc": off["insider_table_first_public_utc"]}
    else:
        miss["insiders"] = ("foreign listing: no SEC Form 4" if foreign else
                            f"no open-market Form 4 buy or sell since {cov_from} ({eff_days} days): the official "
                            f"table starts {cov_from}, so this is NOT a {INSIDER_LOOKBACK_DAYS}-day answer")
    si = off["short_interest"].get(t)
    short_interest = ({"settlement_date": si.get("settlement_date"), "short_qty": _finite(si.get("short_qty")),
                       "change_pct": _finite(si.get("change_pct")), "days_to_cover": _finite(si.get("days_to_cover")),
                       "public_utc": si.get("public_utc"), "source": "FINRA short interest (official_sources)"}
                      if si else None)
    if not si:
        miss["short_interest"] = "no FINRA short-interest row for this symbol in the official table"
    pol = off["politicians"].get(t, [])
    politicians = ({"window_days": INSIDER_LOOKBACK_DAYS, "n": len(pol),
                    "recent": [{"member": r.get("member"), "tx_type": r.get("tx_type"), "trade_date": r.get("trade_date"),
                                "disclosure_date": r.get("disclosure_date"), "amount_lo": r.get("amount_lo"),
                                "amount_hi": r.get("amount_hi"), "url": r.get("pdf_url")}
                               for r in sorted(pol, key=lambda r: str(r.get("public_utc")), reverse=True)[:3]],
                    "source": "House periodic transaction reports (official_sources)"} if pol else None)

    # falsifier / horizon / evidence
    falsifier = e.get("falsifier") or (pre_card or {}).get("falsifier")
    if not falsifier:
        miss["falsifier"] = "the list declares none and no thesis card is dated on or before its freeze"
    horizon = lst.get("horizon")
    if not horizon:
        miss["horizon"] = "a screen declares no holding horizon"
    if lst["evidence_default"] == "EARLY_EVIDENCE":
        n_s = sessions_since(ctx["spy_dates"], lst.get("asof"))
        evidence = {"label": "EARLY_EVIDENCE", "sessions": n_s,
                    "note": f"paper-graded from the first session after {lst.get('asof')}; {n_s} sessions is not a result"}
    else:
        evidence = {"label": "OBSERVED", "sessions": None,
                    "note": f"listed on {lst.get('asof')}; not traded, nothing graded"}

    # lane (F1): three separate checks; the badge needs BADGE_MIN_FLAGS of them
    checks = risk_checks(ctx["dated_firms"].get(t, 0) if ctx.get("dated_firms_ok") else None,
                         cats, ctx["runway"].get(t), today, is_etf=is_etf)
    flags = [k for k, v in checks.items() if v["on"]]
    lane = ("BENCHMARK" if is_etf else
            "HIGH_RISK_INNOVATION" if len(flags) >= BADGE_MIN_FLAGS else "CORE")
    if not is_etf and move and move["expected_abs_move_21s"] >= 0.15:
        checks["high_volatility_info"] = {"on": None, "detail": f"expected 21-session move "
                                          f"{move['expected_abs_move_21s']*100:.0f}% (information only; not a flag)"}

    stamps = [str(s) for s in ((price or {}).get("date"), (analyst or {}).get("observed_utc"),
                               (card or {}).get("run_utc")) if s]
    last_update = max(stamps, key=lambda s: s[:19]) if stamps else None
    weight = e.get("weight")
    if weight is None:
        miss["weight"] = "a ranked list or screen, not a book: no weight is declared"

    return {
        "ticker": t, "company_name": name, "company_name_source": name_src,
        "exchange": exchange, "exchange_source": ex_src, "currency": currency, "is_foreign": foreign, "is_etf": is_etf,
        "list_id": lst["list_id"], "weight": weight, "rank": e.get("rank"), "list_score": e.get("list_score"),
        "eligibility": e.get("eligibility"),
        "sector": sector, "sector_source": sector_src, "theme": theme,
        "price": price, "analyst": analyst, "upside": upside, "revision": revision,
        "move_score": move, "analyst_stance": stance, "analyst_reputation": rep, "why_picked": why,
        "card": ({"day": pre_day, "verdict": pre_card.get("verdict"), "confidence": pre_card.get("confidence"),
                  "card_hash": pre_card.get("card_hash")} if pre_card else None),
        "later_commentary": later, "freeze_date": str(freeze)[:10] if freeze else None,
        "catalysts": cats, "news": news, "insiders": insiders, "short_interest": short_interest,
        "politicians": politicians, "falsifier": falsifier, "horizon": horizon, "evidence": evidence,
        "lane": lane, "risk_flags": flags, "risk_checks": checks, "last_update_utc": last_update,
        "links": O.links(t, ctx["ciks"].get(t)), "missing_because": miss,
    }


def build(now: Optional[datetime] = None, *, write_receipts: bool = True) -> dict:
    now = now or _now()
    today = now.date().isoformat()
    md_lists, md_src = lists_from_md()
    lists = md_lists + lists_from_books(load_books())
    tickers = {e["ticker"] for lst in lists for e in lst["entries"] if e.get("ticker")}
    bars = load_bars(tickers)
    spy_dates = sorted(str(d.date()) for d in bars.loc[bars["symbol"] == "SPY", "date"])
    revisions, rv_pulled = load_revisions(tickers, pd.Timestamp(today))
    firms, firms_src = dated_firms(tickers, pd.Timestamp(today))
    official = load_official(tickers, now)
    cov_from = str(official["insider_table_first_public_utc"] or "")[:10]
    win = INSIDER_LOOKBACK_DAYS
    if cov_from:
        win = min(INSIDER_LOOKBACK_DAYS, (now.date() - date.fromisoformat(cov_from)).days)
    rv_through = None
    m = re.search(r"pulled (\d{4}-\d{2}-\d{2})", str(rv_pulled))
    if m:
        rv_through = m.group(1)
    ctx = {"today": today, "asof": today, "cards": load_cards(), "facts": load_facts(), "yf": load_yf(),
           "mw": load_mw(), "identity": load_identity(), "px": price_and_sigma(bars), "targets": load_targets(),
           "revisions": revisions, "revisions_pulled": rv_pulled, "official": official,
           "dated_firms": firms, "dated_firms_ok": not firms_src.startswith("ERROR"),
           "runway": runway_table(tickers, today), "insider_window_days": win, "revision_through": rv_through,
           "news": load_news(tickers, now.date()), "earn_cache": load_earnings_cache(), "ciks": load_ciks(),
           "spy_dates": spy_dates, "reputation": load_reputation(now, write=write_receipts)}
    out_lists = []
    for lst in lists:
        rows = [build_row(e, lst, ctx) for e in lst["entries"] if e.get("ticker")]
        meta = {k: v for k, v in lst.items() if k != "entries"}
        meta["coverage"] = {f: sum(1 for r in rows if r.get(f)) for f in
                            ("company_name", "exchange", "sector", "price", "analyst", "revision", "move_score",
                             "analyst_stance", "analyst_reputation", "catalysts", "news", "insiders", "falsifier")}
        meta["n_high_risk_innovation"] = sum(1 for r in rows if r["lane"] == "HIGH_RISK_INNOVATION")
        out_lists.append({**meta, "rows": rows})
    return {
        "schema": O.SCHEMA, "generated_utc": now.isoformat(timespec="seconds"), "asof": today,
        "run_id": now.strftime("%Y%m%dT%H%M%SZ"), "builder": "scripts/opportunities_build.py",
        "licence": "PRODUCT_EXPERIMENT: nothing here is a claim of alpha and none of it is an order.",
        "legend": {"move_score": MOVE_EXPLAIN, "analyst_stance": DIRECTION_EXPLAIN,
                   "analyst_reputation": ("Covering firms and the sum of their reputation weights, both from the dated "
                                          "revision file. " + str(ctx["reputation"].get("label") or "") + ": the weight is "
                                          "plumbing, not skill. Target-level upside re-weighted by it is DIAGNOSTIC_ONLY "
                                          "and not shown."),
                   "high_risk_innovation": (f"Three separate flags: COVERAGE (fewer than {COVERAGE_MIN_FIRMS} firms with a "
                                            f"dated target action in {COVERAGE_WINDOW_DAYS} days), BINARY EVENT (an FDA / "
                                            f"trial date within {BINARY_WINDOW_SESSIONS} weekdays) and RUNWAY (cash below "
                                            f"{RUNWAY_MIN_QUARTERS} quarters of operating loss). The badge needs "
                                            f"{BADGE_MIN_FLAGS} of the 3."),
                   "low_upside": f"LOW UPSIDE = median-target upside below {LOW_UPSIDE:.0%}; never shown green.",
                   "evidence": "OBSERVED = listed, not traded. EARLY_EVIDENCE = paper-graded for N sessions; not a result."},
        "inputs": {"stock_list_markdown": md_src, "stock_list_work_dir": WORK.relative_to(REPO).as_posix(),
                   "books": "backend/data/optimus/llm_portfolio/books.jsonl",
                   "bars_last_spy": spy_dates[-1] if spy_dates else None,
                   "revision_flow": rv_pulled, "revision_through": rv_through,
                   "dated_firms": firms_src,
                   "analyst_reputation": ctx["reputation"].get("source") or ctx["reputation"].get("error"),
                   "analyst_reputation_label": ctx["reputation"].get("label"),
                   "insider_coverage_from": cov_from or None, "insider_window_days": win,
                   "stale_after_days": _config.OPPORTUNITIES_STALE_DAYS},
        "lists": out_lists,
    }


def write(blob: dict, base: Optional[Path] = None) -> Path:
    d = O.opportunities_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"opportunities_{blob['asof']}_{blob['run_id']}.json"
    if p.exists():
        raise SystemExit(f"refusing to overwrite {p.name}")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, ensure_ascii=False, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))  # verify before replace
    tmp.replace(p)
    return p


def prune_raw_receipts(base: Optional[Path] = None, keep: Optional[int] = None) -> list[Path]:
    """Q17 (2026-10-07): delete raw receipts beyond the newest `keep` (default
    `config.OPPORTUNITIES_KEEP_RAW`). Ordered by the (asof, run id) in the FILENAME via
    `opportunities.receipts` -- never by mtime: a fresh checkout's files are all "written
    today", and this repo already lost that distinction once (CLAUDE.md protocol item 7).
    The raw file is scratch once the published copy exists; this never touches that copy.
    Returns the paths actually removed, oldest-kept-cutoff first."""
    keep_n = _config.OPPORTUNITIES_KEEP_RAW if keep is None else keep
    removed = []
    for p in O.receipts(base)[max(keep_n, 0):]:
        try:
            p.unlink()
            removed.append(p)
        except OSError:
            continue
    return removed


def publish_public_copy() -> dict:
    """Q17: push the just-written receipt through the SAME sanitiser the public site reads
    (`publish_receipts`), scoped to the `opportunities` kind only, so the tracked
    `backend/data/public_receipts/opportunities/latest.json` is current without a separate
    `python -m scripts.publish_receipts` run. A failed or refused publish is printed and
    never fails the build: the raw receipt this run wrote is already safely on disk, and the
    previous published copy (if any) is kept, named, by `publish_receipts.publish` itself."""
    return PR.publish(kinds=(PR.KIND_BY_NAME["opportunities"],))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Opportunity Explorer receipt.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    blob = build(write_receipts=not a.dry_run)   # F11: a dry run writes nothing
    for lst in blob["lists"]:
        print(f"{lst['list_id']:<34} n={len(lst['rows']):>4}  HRI={lst['n_high_risk_innovation']:>3}  {lst['coverage']}")
    if a.dry_run:
        return 0
    p = write(blob)
    print(f"wrote {p.relative_to(REPO).as_posix()} ({p.stat().st_size/1e6:.2f} MB)")
    removed = prune_raw_receipts()
    if removed:
        print(f"pruned {len(removed)} raw receipt(s) beyond the newest {_config.OPPORTUNITIES_KEEP_RAW} "
              f"(by run id): {', '.join(r.name for r in removed)}")
    pub = publish_public_copy()
    opp_entry = (pub.get("kinds") or {}).get("opportunities") or {}
    opp_bytes = opp_entry.get("bytes") or 0
    print(f"published public copy: {opp_bytes:,} B / {PR.MAX_BYTES:,} B budget "
          f"({opp_entry.get('status')}; folder {pub.get('status')}"
          + (f": {pub['why']}" if pub.get("why") else "") + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
