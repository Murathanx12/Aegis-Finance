"""CH-66: a filing-TEXT tool for the investigator, beside the frozen tool layer.

WHAT WAS WRONG
==============
`investigator_tools.read_filings` returns form, date and 8-K item codes. The
one forecasting process here with measured held-out skill was reading item
codes, never what the filing says.

WHY THIS IS A NEW MODULE AND `investigator_tools.py` IS UNTOUCHED
================================================================
`night_launcher.NIGHT_MODULES` hashes the BYTES of `investigator_tools.py` into
every INTERNET-INVESTIGATOR-FWD-1 launch manifest, and a launch whose module
hashes differ from its rehearsal is refused. `tools_for_arm` is part of that
frozen design. So the text does not go into `read_filings`; it is a second
tool, `read_filings_text`, offered only to a separately named configuration and
only while `config.INVESTIGATOR_FILING_TEXT_ENABLED` is on (default OFF). The
IIF-1 arms are never offered it, whatever the flag says.

WHAT A ROW CARRIES
==================
The old fields (`form`, `filed`, `items`, `classification`) plus:

    text_excerpt         the start of the text, bounded by config
    text_chars           length of the text the excerpt was cut from
    truncated_at_source  True when ALL we hold is the collector's body and it is
                         exactly the collector's cut length: the guidance table
                         may be missing, and the model is told so in words
    text_source          "full_exhibit" | "collector_body"
    outlook_excerpt      full text only: the part starting at the first
                         outlook/guidance heading, else None
    source_url, filed_utc, exhibit, accession

POINT IN TIME
=============
A row is returned only when its EDGAR acceptance time (`published_utc`,
`pit_grade: native_stamp`) is at or before `as_of_utc`. The frozen tool has no
clock argument because the trial is forward-only; this one keeps that default
(as-of = now) and lets the CALLER pass a clock. The model cannot: `as_of_utc`
is not in the parameter schema. A row with no usable timestamp is excluded and
counted, never guessed.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config as C
from backend.services import investigator_tools as IT
from backend.services import sec_exhibit_full as SX

logger = logging.getLogger(__name__)

TOOL_NAME = "read_filings_text"

TRUNCATION_NOTE = (
    "truncated_at_source=true means only the first "
    "{cut} characters of the exhibit are stored; tables that come later "
    "(guidance, outlook, segment detail) may be missing. Do not read their "
    "absence as 'no guidance was given'.")

_OUTLOOK = re.compile(
    r"\b(?:business |financial |full[- ]year |fiscal (?:year )?\d{2,4} |"
    r"(?:first|second|third|fourth) quarter (?:fiscal )?(?:\d{4} )?)?"
    r"(?:outlook|guidance)\b", re.IGNORECASE)

PARAMETERS: dict = {"type": "object", "required": ["ticker"], "properties": {
    "ticker": {"type": "string"},
    "days": {"type": "integer", "minimum": 1, "maximum": 90}}}

DESCRIPTION = (
    "Recent SEC 8-K Exhibit 99 press releases for a ticker WITH TEXT: item "
    "codes, acceptance time, source URL and an excerpt. Each row says whether "
    "the stored text was cut at source.")


def data_root() -> Path:
    return Path(C.OPTIMUS_LEDGER_DIR)


def is_frozen_arm(configuration: str) -> bool:
    try:
        IT.tools_for_arm(configuration)
    except KeyError:
        return False
    return True


def filing_text_enabled(configuration: str) -> bool:
    """True only for a named non-frozen configuration while the switch is on."""
    if is_frozen_arm(configuration):
        return False
    return (bool(C.INVESTIGATOR_FILING_TEXT_ENABLED)
            and configuration in tuple(C.INVESTIGATOR_FILING_TEXT_CONFIGURATIONS))


def tools_for_configuration(configuration: str) -> list[str]:
    """The tool names a configuration may call.

    A frozen IIF-1 arm gets exactly `investigator_tools.tools_for_arm(arm)`.
    A configuration listed in `INVESTIGATOR_FILING_TEXT_CONFIGURATIONS` gets the
    six base tools, plus the text tool when the switch is on. Anything else is
    a KeyError, for the reason the frozen layer gives: a typo must not silently
    become a different configuration."""
    if is_frozen_arm(configuration):
        return IT.tools_for_arm(configuration)
    if configuration not in tuple(C.INVESTIGATOR_FILING_TEXT_CONFIGURATIONS):
        raise KeyError(f"unknown investigator configuration {configuration!r}")
    base = IT.tools_for_arm("B_tools")
    return base + [TOOL_NAME] if filing_text_enabled(configuration) else base


def tool_schemas(configuration: str) -> list[dict]:
    names = tools_for_configuration(configuration)
    out = IT.openai_tool_schemas([n for n in names if n != TOOL_NAME])
    if TOOL_NAME in names:
        out.append({"type": "function", "function": {
            "name": TOOL_NAME, "description": DESCRIPTION, "parameters": PARAMETERS}})
    return out


def _classification(items: list[str]) -> Any:
    try:
        from backend.services.edgar_events import classify_items
        return classify_items(items)[0]
    except Exception:  # noqa: BLE001 - a label, never worth losing the row for
        return None


def outlook_excerpt(text: str, max_chars: int) -> tuple[Optional[str], Optional[int]]:
    """The slice starting at the first outlook/guidance heading AFTER the head
    excerpt, so the two excerpts do not repeat each other."""
    head = int(C.INVESTIGATOR_FILING_TEXT_EXCERPT_CHARS)
    m = _OUTLOOK.search(text, head)
    if not m:
        return None, None
    return text[m.start(): m.start() + int(max_chars)], m.start()


def read_filings_text(ticker: str, days: Optional[int] = None, *,
                      as_of_utc: Optional[datetime] = None,
                      root: Optional[Path] = None,
                      max_rows: Optional[int] = None) -> Optional[dict]:
    """Stored 8-K EX-99 rows for `ticker`, newest first, point in time.

    Returns None when nothing in the window matches (the tool layer reports
    that as `empty`); raises when the store itself is missing, which the tool
    layer reports as `unavailable`. The two are never merged."""
    sym = str(ticker or "").upper().strip()
    if not sym:
        raise TypeError("ticker is required")
    days = int(C.INVESTIGATOR_FILING_TEXT_DAYS if days is None else days)
    max_rows = int(C.INVESTIGATOR_FILING_TEXT_MAX_ROWS if max_rows is None else max_rows)
    as_of = SX.parse_utc(as_of_utc) if as_of_utc is not None else datetime.now(timezone.utc)
    if as_of is None:
        raise ValueError("as_of_utc must carry a timezone")
    paths = SX.default_paths(Path(root) if root else data_root())
    SX.check_inputs(paths)                       # missing store -> refusal -> unavailable
    cik_map = SX.load_cik_map(paths["cik_map"])
    floor = as_of - timedelta(days=days)
    # Rows filed AFTER the as-of time are counted in `_audit`, which the model
    # never sees: telling a replayed model "one filing is coming" is a leak.
    audit = {"excluded_after_as_of": 0}
    counts = {"matched_ticker": 0, "excluded_no_timestamp": 0,
              "excluded_before_window": 0,
              "returned": 0, "truncated_at_source": 0, "full_text": 0,
              "not_shown_over_max_rows": 0}
    picked: dict[str, tuple[datetime, dict]] = {}
    for r in SX.read_body_rows(paths["corpus"], since=floor):
        if sym not in SX.row_tickers(r, cik_map):
            continue
        counts["matched_ticker"] += 1
        filed = SX.parse_utc(r.get("published_utc"))
        if filed is None:
            counts["excluded_no_timestamp"] += 1
            continue
        if filed > as_of:
            audit["excluded_after_as_of"] += 1
            counts["matched_ticker"] -= 1
            continue
        if filed < floor:
            counts["excluded_before_window"] += 1
            continue
        picked[str(r.get("raw_id") or r.get("url"))] = (filed, r)
    if not picked:
        if counts["excluded_no_timestamp"]:
            # Rows exist but cannot be dated: say so rather than "nothing found".
            return {"ticker": sym, "as_of_utc": SX._iso(as_of), "window_days": days,
                    "rows": [], "counts": counts, "_audit": audit}
        return None
    ordered = sorted(picked.items(), key=lambda kv: (kv[1][0], kv[0]), reverse=True)
    counts["not_shown_over_max_rows"] = max(0, len(ordered) - max_rows)
    shown = ordered[:max_rows]
    # The store is month files keyed by the filing's month: read only those.
    months = {filed.strftime("%Y-%m") for _rid, (filed, _r) in shown}
    full = SX.read_full_store(paths["store"], months=months)
    head = int(C.INVESTIGATOR_FILING_TEXT_EXCERPT_CHARS)
    rows = []
    for rid, (filed, r) in shown:
        stored = r.get("body") or ""
        f = full.get(rid)
        # The full text is the exhibit as filed (EDGAR archive documents do not
        # change after acceptance); it is used only for a filing already
        # admitted by its acceptance time above, whenever it was fetched.
        if f and f.get("text"):
            text, source = f["text"], "full_exhibit"
            cut = bool(f.get("capped"))
            n_chars = int(f.get("n_chars") or len(text))
        else:
            text, source, cut = stored, "collector_body", SX.is_truncated(stored)
            n_chars = len(text)
        items = SX.item_codes(r)
        row = {
            "form": "8-K", "filed": filed.date().isoformat(), "items": items,
            "classification": _classification(items),
            "exhibit": SX.tag_value(r, "exhibit:"),
            "accession": SX.tag_value(r, "accession:"),
            "source_url": r.get("url") or "", "filed_utc": SX._iso(filed),
            "text_source": source, "text_chars": n_chars,
            "truncated_at_source": bool(cut),
            "collector_body_chars": len(stored),
            # full text only: does it start with what the collector stored? False
            # is shown, never repaired (a different document, or a cleaner change).
            "prefix_matches_stored": f.get("prefix_matches_stored") if source == "full_exhibit" else None,
            "text_excerpt": text[:head],
            "outlook_excerpt": None, "outlook_offset": None,
        }
        if source == "full_exhibit":
            row["outlook_excerpt"], row["outlook_offset"] = outlook_excerpt(
                text, int(C.INVESTIGATOR_FILING_TEXT_OUTLOOK_CHARS))
            counts["full_text"] += 1
        if cut:
            counts["truncated_at_source"] += 1
        rows.append(row)
    counts["returned"] = len(rows)
    out = {"ticker": sym, "as_of_utc": SX._iso(as_of), "window_days": days,
           "rows": rows, "counts": counts, "_audit": audit}
    if counts["truncated_at_source"]:
        out["warning"] = TRUNCATION_NOTE.format(cut=C.SEC_EXHIBIT_COLLECTOR_CUT_CHARS)
    return out


def as_model_text(res: IT.ToolResult) -> str:
    """What the model sees. `ToolResult.as_model_text` cuts the JSON at 6,000
    characters without saying so, which would hand over a cut body as if whole;
    here whole ROWS are dropped (oldest first) until the text fits, and the
    number dropped is stated."""
    if res.status != IT.STATUS_OK or not isinstance(res.payload, dict):
        return res.as_model_text()
    limit = int(C.INVESTIGATOR_FILING_TEXT_MODEL_CHARS)
    payload = {k: v for k, v in res.payload.items() if not str(k).startswith("_")}
    rows = list(payload.get("rows") or [])
    dropped = 0
    while True:
        payload["rows"] = rows
        payload["rows_dropped_for_length"] = dropped
        body = json.dumps(payload, default=str, ensure_ascii=False)
        if len(body) <= limit or not rows:
            break
        rows = rows[:-1]
        dropped += 1
    text = f"[{res.tool}] {body}"
    if res.caveat:
        text += f"\n[{res.tool}] PARTIAL: {res.caveat[:300]}"
    return text


def run_filing_text_tool(args: dict, budget: Optional[IT.ToolBudget] = None, *,
                         configuration: str,
                         as_of_utc: Optional[datetime] = None,
                         root: Optional[Path] = None) -> IT.ToolResult:
    """Execute the text tool with the frozen layer's result contract: `ok`,
    `empty` and `unavailable` stay distinct, every path is timed and logged to
    the budget, and a configuration that is not offered the tool is refused in
    words."""
    t0 = time.perf_counter()

    def finish(res: IT.ToolResult) -> IT.ToolResult:
        res.latency_ms = (time.perf_counter() - t0) * 1000.0
        if budget is not None:
            budget.log.append(res.as_row())
        return res

    if not filing_text_enabled(configuration):
        return finish(IT.ToolResult(
            TOOL_NAME, IT.STATUS_UNAVAILABLE,
            reason=f"tool not offered to configuration {configuration!r}"))
    if budget is not None and not budget.take():
        return finish(IT.ToolResult(
            TOOL_NAME, IT.STATUS_UNAVAILABLE,
            reason=f"tool budget exhausted after {budget.max_calls} calls"))
    allowed = set(PARAMETERS["properties"])
    extra = set(args or {}) - allowed
    if extra:
        return finish(IT.ToolResult(TOOL_NAME, IT.STATUS_UNAVAILABLE,
                                    reason=f"bad arguments: unexpected {sorted(extra)}"))
    try:
        payload = read_filings_text(as_of_utc=as_of_utc, root=root, **(args or {}))
    except TypeError as exc:
        return finish(IT.ToolResult(TOOL_NAME, IT.STATUS_UNAVAILABLE,
                                    reason=f"bad arguments: {exc}"))
    except Exception as exc:  # noqa: BLE001 - the one place a failure becomes `unavailable`
        logger.warning("tool %s failed: %s", TOOL_NAME, exc)
        return finish(IT.ToolResult(TOOL_NAME, IT.STATUS_UNAVAILABLE,
                                    reason=f"{type(exc).__name__}: {exc}"))
    if payload is None:
        return finish(IT.ToolResult(TOOL_NAME, IT.STATUS_EMPTY))
    caveat = ""
    c = payload.get("counts") or {}
    if c.get("excluded_no_timestamp"):
        caveat = f"{c['excluded_no_timestamp']} row(s) had no usable timestamp and were excluded"
    return finish(IT.ToolResult(TOOL_NAME, IT.STATUS_OK, payload=payload, caveat=caveat))
