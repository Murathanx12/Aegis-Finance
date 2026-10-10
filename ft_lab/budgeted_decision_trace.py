"""Frozen real-source PRODUCT_EXPERIMENT; offline consumers, no execution authority.

Manual source annotations are an inspection fixture, not measured model output.
Run in a fresh process: python -m ft_lab.budgeted_decision_trace --runtime-root PATH
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "backend/data/optimus/local_pc/budgeted_20261010/trace"
CUTOFF = "2026-10-10T00:00:00+00:00"
ASOF = "2026-10-10"
VERSION = "bounded_decision_trace/v1"

# Chosen for distinct real mechanisms, including two eligible top-50 flows,
# a lower-ranked flow, negative revisions, and the known ambiguous settlement.
# No outcome or model extraction informed these manual annotations.
SPECS = [
    dict(day="2026-10-01", ticker="ACN", id="0001467373-26-000037:q4fy26earnings8-kexhibit.htm",
         sha="f8ac1a1509dabdd9c53bd74bf75fc430d226b31b6a80f561fa6a9ee63928d8b6",
         entity="Accenture", event="earnings_report", reporting_date="2026-10-01",
         date_span="NEW YORK&#59; October&#160;1, 2026", numbers=["$11.5 billion", "$22.2 billion"],
         spans=["Accenture Reports Fourth-Quarter and Full-Year Fiscal 2026 Results", "grew adjusted EPS 8%", "New bookings of $22.2 billion"],
         mechanism="Reported bookings and EPS can change future consensus expectations.",
         contradiction="Above-guidance revenue does not establish future return direction.", status="reported"),
    dict(day="2026-10-03", ticker="SNOW", id="0001640147-26-000043:exhibit991-launchpressrele.htm",
         sha="1741e4d79fc29bc3e13f796a86529f948ac1d823110539b2f1b307e3378374cd",
         entity="Snowflake Inc.", event="debt_or_financing", reporting_date="2026-09-28",
         date_span="September 28, 2026", numbers=["$3.5 Billion", "$1.3 billion", "$2.2 billion"],
         spans=["Snowflake Announces Proposed Private Placement of $3.5 Billion of 0.00% Convertible Senior Notes", "today announced that it intends to offer, subject to market conditions and other factors"],
         mechanism="Proposed convertible financing creates funding and dilution questions.",
         contradiction="Proposed and conditional; neither issue date nor completion is established.", status="proposed"),
    dict(day="2026-10-08", ticker="MGNI", id="0001193125-26-417011:d149525dex991.htm",
         sha="704d433472e482137651fb24c9cba84f12cb03ede36a64db2b97b8e867b051f5",
         entity="Magnite", event="debt_or_financing", reporting_date="2026-10-07",
         date_span="Oct.7, 2026", numbers=["50 Basis Points", "$1.8 Million"],
         spans=["Magnite Successfully Completes Term Loan and Revolving Credit Facility Repricing", "Generates Approximately $1.8 Million in Annualized Interest Savings", "All other material terms remain substantially unchanged."],
         mechanism="Lower interest margin can reduce financing expense.",
         contradiction="Savings are approximate; announcement date does not prove exact completion date.", status="completed_reported"),
    dict(day="2026-10-08", ticker="LEVI", id="0000094845-26-000048:exhibit991-3q2026pressrele.htm",
         sha="3fb5e908807b99871216677c8ad7d32e5795d4b77db901fd3bf372152cc0d508",
         entity="Levi Strauss", event="earnings_report", reporting_date="2026-10-07",
         date_span="SAN FRANCISCO (October&#160;7, 2026)", numbers=["13.8%", "$0.43", "$0.48"],
         spans=["RAISES FULL YEAR 2026 MARGIN AND EPS OUTLOOK", "While our direct-to-consumer business fell short of our internal expectations"],
         mechanism="Raised EPS outlook supports a possible analyst revision while DTC weakness offsets it.",
         contradiction="Raised company outlook coexists with net analyst target reductions in the stored window.", status="reported"),
    dict(day="2026-09-19", ticker="CACC", id="0000885550-26-000192:cacc_8k20260917pr.htm",
         sha="176077ac6276618759a5e86969d61c1579e192fc24e328865e5b20e9f7813873",
         entity="Credit Acceptance Corporation", event="litigation_settlement", reporting_date="2026-09-17",
         date_span="September 17, 2026", numbers=["$60 million", "$15.5 million"],
         spans=["announced today that it has entered or will enter into consent judgments", "the Company will pay $60 million to a consumer relief fund"],
         mechanism="Consent judgments imply relief payments and resolution of litigation.",
         contradiction="Mixed entered/will-enter language does not establish a settlement event day.", status="mixed_confirmed_future"),
]


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, sort_keys=True, allow_nan=False,
                               default=str) + "\n", encoding="utf-8")


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


def event_day(spec: dict, role: str) -> str:
    """Only the explicitly annotated reporting day is source-grounded here.

    In particular no date associated with 'announced ... entered or will enter'
    is licensed as a settlement/completion day. Never infer from filing stamp.
    """
    if role != "reporting":
        raise ValueError("unsupported event-date role: " + role)
    return spec["reporting_date"]


def validate_candidate(facts: dict, excerpt: str, spec: dict) -> dict:
    """Bounded source-inspected contract; not a general semantic extractor.

    The public pilot parser checks syntax and substring evidence, but does not
    establish that an announcement dateline dates the operative action.
    """
    from ft_lab.news_pilot_qwen7b import parse_reply
    parsed = parse_reply(json.dumps(facts), excerpt)
    supported = spec["reporting_date"] if spec["event"] == "earnings_report" else None
    if parsed["event_type"] != spec["event"]:
        raise ValueError("event differs from frozen source inspection")
    if parsed["event_date"] is not None and parsed["event_date"] != supported:
        raise ValueError("unsupported_operative_event_day: dateline licenses reporting only")
    return parsed


def extract(doc: dict, spec: dict, path: Path, cutoff: str = CUTOFF) -> dict:
    from ft_lab.news_pilot_cascade import source_ok
    from ft_lab.news_pilot_p3 import constraint_receipt
    from ft_lab.news_pilot_qwen7b import parse_reply
    body = doc["body"]
    if doc["raw_id"] != spec["id"] or sha_bytes(body.encode()) != spec["sha"]:
        raise ValueError("frozen source identity/content changed")
    if spec["ticker"] not in doc["tickers"]:
        raise ValueError("source ticker mismatch")
    if any(timestamp(doc[k]) > timestamp(cutoff) for k in ("published_utc", "first_seen_utc")):
        raise ValueError("source not known at information cutoff")
    excerpt = body[:1600]
    frozen = dict(id=doc["raw_id"], split="dev", source_kind=doc["source"],
                  source_url=doc["url"], source_path=str(path), excerpt=excerpt,
                  content_sha256=sha_bytes(excerpt.encode()))
    source_ok(frozen)
    if spec["date_span"] not in excerpt:
        raise ValueError("reporting date is not source-grounded")
    facts = dict(entity=spec["entity"], event_type=spec["event"], event_date=None,
                 date_precision="unknown", numbers=spec["numbers"],
                 evidence_spans=spec["spans"], abstain=False)
    # Explicit REPORT dates are events; completion/settlement days stay unknown.
    if spec["event"] == "earnings_report":
        facts.update(event_date=event_day(spec, "reporting"), date_precision="day")
    validate_candidate(facts, excerpt, spec)
    return {**frozen, "body_sha256": spec["sha"], "ticker": spec["ticker"],
            "published_utc": doc["published_utc"], "first_seen_utc": doc["first_seen_utc"],
            "tz_source": doc.get("tz_source"), "facts": facts,
            "annotation_method": "manual_frozen_source_inspection; no model output",
            "source_spans": [{"text": span, "start": excerpt.index(span), "end": excerpt.index(span) + len(span)}
                             for span in dict.fromkeys([spec["entity"], spec["date_span"], *spec["numbers"], *spec["spans"]])],
            "constraint_receipt": constraint_receipt(excerpt),
            "reporting_date": event_day(spec, "reporting"), "date_span": spec["date_span"],
            "event_date_status": "confirmed_reporting_only" if facts["event_date"] else "unknown_action_day",
            "dates": [{"date": spec["reporting_date"], "role": "reporting", "status": "explicit_source_day", "span": spec["date_span"]}],
            "estimated_dates": [], "estimated_dates_status": "none asserted; no completion inferred",
            "action_status": spec["status"], "mechanism": spec["mechanism"],
            "mechanism_status": "manual_interpretation_not_forecast", "contradiction": spec["contradiction"],
            "horizons_sessions": [5, 21, 63], "horizon_status": "consumer_horizons_not_source_prediction",
            "numeric_status": "approximate" if "Approximately" in " ".join(spec["spans"]) else "source_reported"}


def denied(*args, **kwargs):
    raise RuntimeError("offline trace forbids network/model/broker execution")


def protect_runtime(runtime: Path):
    """Process-level fail-loud guard for accidental runtime writes."""
    def audit(event, args):
        if event == "subprocess.Popen":
            denied()
        if event == "open":
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            paths = [path] if writing else []
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename"):
            paths = args[:2] if event == "os.rename" else args[:1]
        else:
            return
        for path in paths:
            if not isinstance(path, (str, bytes, os.PathLike)):
                continue
            resolved = Path(os.fsdecode(path)).resolve()
            if resolved == runtime or runtime in resolved.parents:
                raise RuntimeError("read-only runtime mutation refused: " + event)
    sys.addaudithook(audit)


def reject_stored_reply(checkpoint: Path, cacc: dict) -> dict:
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    matches = [r for r in state["rows"].values() if r["id"] == cacc["id"]]
    if len(matches) != 1:
        raise ValueError("CACC checkpoint identity missing or ambiguous")
    row = matches[0]
    if sha_bytes(row["raw_reply"].encode()) != row["raw_sha256"]:
        raise ValueError("stored raw reply hash changed")
    raw = json.loads(row["raw_reply"])
    fields = ("entity", "event_type", "event_date", "date_precision", "numbers", "evidence_spans", "abstain")
    candidate = {k: raw[k] for k in fields}
    try:
        validate_candidate(candidate, cacc["excerpt"], SPECS[-1])
    except ValueError as exc:
        if "unsupported_operative_event_day" not in str(exc):
            raise
        return {"source_id": cacc["id"], "current_source_body_sha256": cacc["body_sha256"],
                "checkpoint_path": str(checkpoint), "raw_reply_sha256": row["raw_sha256"],
                "original_excerpt_sha256": row["content_sha256"], "prompt_version": row["prompt_version"],
                "candidate": candidate, "candidate_origin": "actual_stored_failed_local_reply",
                "verdict": "REJECTED", "reason": str(exc), "operative_source_span": cacc["facts"]["evidence_spans"][0],
                "binding_note": "Same pinned SEC source ID; candidate substrings rechecked against stored raw article excerpt. Original pilot excerpt hash preserved separately."}
    raise ValueError("stored candidate did not reproduce the unsupported date")


def run(runtime: Path, output: Path, failed_checkpoint: Path | None = None) -> dict:
    runtime, output = runtime.resolve(), output.resolve()
    allowed = DEFAULT_OUT.resolve()
    if output != allowed and allowed not in output.parents:
        raise ValueError("output must stay in the isolated trace directory")
    if runtime == output or runtime in output.parents:
        raise ValueError("output must not be inside read-only runtime")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output exists and is not empty; choose a fresh subdirectory")
    protect_runtime(runtime)
    # BEFORE importing config-dependent consumers: default stores are isolated.
    os.environ["AEGIS_DATA_DIR"] = str(output / "isolated_data")
    import pandas as pd
    from backend import config
    from backend.services import expected_return as ER, pc_broker as PB
    from scripts import sim_run as S
    if output not in Path(config.OPTIMUS_LEDGER_DIR).resolve().parents:
        raise RuntimeError("config was imported before store isolation; use a fresh process")
    docs = []
    frozen_rows = {}
    for spec in SPECS:
        path = runtime / "news_corpus/sec_edgar_8k_ex99_body" / (spec["day"] + ".jsonl")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        matches = [row for row in rows if row["raw_id"] == spec["id"]]
        if len(matches) != 1:
            raise ValueError("missing/duplicate frozen source: " + spec["id"])
        docs.append(extract(matches[0], spec, path))
        frozen_rows.setdefault(spec["day"], []).append(matches[0])
    tickers = [d["ticker"] for d in docs]
    rev_path = runtime / "analyst/target_revisions.parquet"
    revisions = pd.read_parquet(rev_path)
    original_count = len(revisions)
    known = pd.to_datetime(revisions["first_seen_utc"], utc=True, errors="coerce")
    # Missing first_seen is NEVER promoted from event_date/pulled_at.
    revisions = revisions[known.notna() & (known <= pd.Timestamp(CUTOFF))].copy()
    events = pd.to_datetime(revisions.event_date, utc=True, errors="coerce")
    revisions = revisions[events.notna() & (events < pd.Timestamp(ASOF, tz="UTC"))].copy()
    sweep_path = runtime / "analyst/revision_flow_sweep_2026-09-25.json"
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    if timestamp(sweep["written_utc"]) > timestamp(CUTOFF):
        raise ValueError("sweep was not available at cutoff")
    flow = ER._revision_state(ER.Sources(revisions=revisions), ASOF)
    selected = revisions[revisions.ticker.isin(tickers)].copy()
    selected = selected[pd.to_datetime(selected.event_date, utc=True) >= pd.Timestamp(ASOF, tz="UTC") - pd.Timedelta(days=90)]
    write(output / "sources.json", {"cutoff_utc": CUTOFF, "documents": docs})
    cacc = docs[-1]
    unsupported = {**cacc["facts"], "event_date": "2026-09-17", "date_precision": "day"}
    try:
        validate_candidate(unsupported, cacc["excerpt"], SPECS[-1])
    except ValueError as exc:
        write(output / "settlement_date_rejection.json", {"source_id": cacc["id"], "source_body_sha256": cacc["body_sha256"],
              "candidate": unsupported, "candidate_origin": "explicit regression witness reproducing failed settlement-date claim; not a model reply",
              "verdict": "REJECTED", "reason": str(exc), "operative_source_span": cacc["facts"]["evidence_spans"][0]})
    else:
        raise RuntimeError("unsupported settlement date escaped validation")
    if failed_checkpoint is not None:
        write(output / "actual_failed_reply_rejection.json", reject_stored_reply(failed_checkpoint, cacc))
        state = json.loads(failed_checkpoint.read_text(encoding="utf-8"))
        row = next(r for r in state["rows"].values() if r["id"] == cacc["id"])
        write(output / "failed_reply_input.json", {"rows": {cacc["id"]: {k: row[k] for k in
              ("id", "raw_reply", "raw_sha256", "content_sha256", "prompt_version")}}})
    write(output / "analyst_sources.json", {"path": str(rev_path), "sha256": sha_bytes(rev_path.read_bytes()),
          "n_source_rows": original_count, "n_known_rows": len(revisions), "selected_rows": selected.to_dict("records"),
          "first_seen_required": True, "rule": "strict event_date < asof; trailing 90 days; >=3 firms",
          "flow": {t: {"rank": flow["rank"].get(t), **(flow["flow"].loc[t].to_dict() if t in flow["flow"].index else {})} for t in tickers},
          "caveat": "Retrospective yfinance history with receipt-time first_seen; descriptive product inspection, not historical PIT certification."})
    # Stored snapshot is an input, never a broker read. No account identifier copied.
    snap_path = runtime / "pc_book/2026-10-09/nav.jsonl"
    snaps = [json.loads(x) for x in snap_path.read_text(encoding="utf-8").splitlines()]
    snaps = [s for s in snaps if timestamp(s["t"]) <= timestamp(CUTOFF)]
    if not snaps:
        raise ValueError("no stored snapshot at cutoff")
    snap = max(snaps, key=lambda x: timestamp(x["t"]))
    snapshot = {k: snap[k] for k in ("t", "equity", "cash", "n_positions", "positions")}
    bars_path = runtime / "prices_2025_26/bars.parquet"
    symbols = tickers + [p["symbol"] for p in snapshot["positions"]] + ["SPY"]
    bars = pd.read_parquet(bars_path, columns=["symbol", "date", "close"], filters=[("symbol", "in", symbols)])
    bars = bars[pd.to_datetime(bars.date, utc=True) < pd.Timestamp(CUTOFF)].sort_values("date")
    prices = {str(t): float(g.iloc[-1].close) for t, g in bars.groupby("symbol")}
    if any(t not in prices for t in symbols):
        raise ValueError("stored price missing; refuse fabricated or zero fallback")
    write(output / "portfolio_input.json", {"snapshot": snapshot, "source_path": str(snap_path),
          "snapshot_sha256": sha_bytes(json.dumps(snapshot, sort_keys=True).encode()),
          "prices": prices, "price_dates": {t: str(g.iloc[-1].date) for t, g in bars.groupby("symbol")},
          "price_source": str(bars_path), "price_semantics": "stored prior close; not a live quote"})
    # A frozen local input mirror permits another run without rereading runtime.
    frozen_runtime = output / "frozen_runtime"
    for day, rows in frozen_rows.items():
        target = frozen_runtime / "news_corpus/sec_edgar_8k_ex99_body" / (day + ".jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    for source, relative in [(rev_path, "analyst/target_revisions.parquet"), (sweep_path, "analyst/revision_flow_sweep_2026-09-25.json")]:
        target = frozen_runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = frozen_runtime / "pc_book/2026-10-09/nav.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
    target = frozen_runtime / "prices_2025_26/bars.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(target, index=False)
    manifest = {"version": VERSION, "source_module": "ft_lab.budgeted_decision_trace", "licence": "PRODUCT_EXPERIMENT", "cutoff_utc": CUTOFF,
                "asof": ASOF, "source_set_sha256": sha_bytes(json.dumps(docs, sort_keys=True).encode()),
                "sweep_path": str(sweep_path), "sweep_sha256": sha_bytes(sweep_path.read_bytes()),
                "selection": "five predeclared source mechanisms; no outcome-based selection",
                "no_news_boundary": ER.NOT_READ_BY_DESIGN["source:"],
                "no_model_calls": True, "spend_usd": 0, "activation_allowed": False}
    write(output / "manifest.json", manifest)
    results = {}
    # No numerical consumer is replaced. Only broker I/O receives stored inputs.
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", denied))
        stack.enter_context(patch.object(socket, "create_connection", denied))
        stack.enter_context(patch.object(PB, "snapshot", lambda **kw: snapshot))
        stack.enter_context(patch.object(PB, "last_prices", lambda syms: {s: prices[s] for s in syms}))
        for name in ("submit", "clock", "orders"):
            stack.enter_context(patch.object(PB, name, denied))
        for variant in ("full", "without_news", "without_analyst"):
            folder = output / variant
            folder.mkdir(parents=True)
            news = [] if variant == "without_news" else docs
            predictions = [{"id": d["id"], "specialist": "source:manual_inspection", "made_at": d["first_seen_utc"],
                            "ticker": d["ticker"], "facts": d["facts"], "abstain": True,
                            "why": "No calibrated probability or return prediction extracted from source facts"} for d in news]
            src = ER.Sources(label=VERSION + ":" + variant, revisions=None if variant == "without_analyst" else revisions,
                             sweep=None if variant == "without_analyst" else sweep, predictions=predictions,
                             decision_rows=[], regime=None,
                             unavailable={"regime": "isolated; no network", "ibes": "not loaded; no new reliability inference",
                                          "revisions": "ablation removes analyst source" if variant == "without_analyst" else "",
                                          "ranking": "no independent ranker injected"})
            forecast = ER.build(ASOF, tickers, src, out_dir=folder / "forecast")
            write(folder / "inputs.json", {"news_source_ids": [d["id"] for d in news],
                  "analyst_source_removed": variant == "without_analyst", "news_rows": predictions})
            # Candidate inventory is identical across arms; no forecast outcome selected it.
            ranking = {"asof": ASOF, "model_version": "inventory_only_not_ranker", "top20_net_rel_21d": None,
                       "top": [{"symbol": t, "rank": i + 1, "calibration_measured": False} for i, t in enumerate(tickers)]}
            write(folder / "ranking.json", ranking)
            src.ranking = ranking
            write(folder / "funnel.json", {"generated_at": CUTOFF, "evidence_basis": {"ranked_by": ["frozen_source_inventory"]},
                  "candidates": []})
            plan = S.u_plan(folder, "research", asof=ASOF, funnel_path=folder / "funnel.json",
                            ledger_path=folder / "decision_ledger.jsonl", contracts_dir=folder / "contracts",
                            er_sources=src, er_dir=folder / "planner_forecast", now_utc=timestamp(CUTOFF))
            book = json.loads((folder / "intended_book.json").read_text(encoding="utf-8"))
            if book["sent"] or book["acting"] or plan.get("n_sent", 0):
                raise RuntimeError("isolated plan unexpectedly acquired authority")
            results[variant] = {"forecast": forecast["names"], "forecast_writers": forecast["forecast_writers"],
                                "plan": plan, "book": book["book"], "orders_by_state": book["orders_by_state"]}
    full = results["full"]
    summary = {**manifest, "n_documents": len(docs), "n_tickers": len(tickers), "n_selected_revision_events": len(selected),
               "n_forecast_cells_per_variant": sum(sum(k.startswith("h") and k[1:].isdigit() for k in row) for row in full["forecast"].values()),
               "news_forecast_equal": full["forecast"] == results["without_news"]["forecast"],
               "news_book_equal": full["book"] == results["without_news"]["book"],
               "analyst_forecast_equal": full["forecast"] == results["without_analyst"]["forecast"],
               "analyst_book_equal": full["book"] == results["without_analyst"]["book"],
               "consumer_decision_story_lines": {v: r["plan"].get("decision_story_line") for v, r in results.items()},
               "consumer_decision_story_mismatches": [v for v, r in results.items()
                    if "MISMATCH" in str(r["plan"].get("decision_story_line"))],
               "variants": results, "acceptance": "ACTUAL_CONSUMERS_EXECUTED; NEWS_TO_FORECAST_NOT_READ_BY_DESIGN",
               "limitations": ["No measured new extraction/model skill", "Prior sweep is survivor-selected direction context; no alpha claim",
                               "No new source probability or news adoption", "Empty PROBE shortlist is explicit abstention", "Research mode; no orders or fills",
                               "Existing without_analyst decision-story replay MISMATCH/NOT_SEPARABLE is retained; runner input reproduction does not certify that consumer replay"]}
    write(output / "trace.json", summary)
    return {k: v for k, v in summary.items() if k not in ("variants", "limitations")}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime-root", type=Path, required=True)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--failed-reply-checkpoint", type=Path)
    args = p.parse_args()
    print(json.dumps(run(args.runtime_root, args.out, args.failed_reply_checkpoint), sort_keys=True))


if __name__ == "__main__":
    main()
