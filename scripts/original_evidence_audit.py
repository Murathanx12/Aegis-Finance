"""Read-only, dated census of original paper and source-forecast evidence.

The input is an existing OPTIMUS_LEDGER_DIR. This tool never grades a live
forecast, resolves an outcome, downloads data, or changes paper state. Its
output contains account-level private evidence and must stay outside Git.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re


TARGETS = (
    "revision_flow_v0",
    "revision_flow_v0_random_twin",
    "lib_net_raises_2026-09-26",
    "pers_revision_flow_leaders_2026-09-25",
)
SOURCE_COLUMNS = {"source:wsj_heard_on_the_street", "source:barrons_stock_picks"}
PARENT_ID = "cb8d492bb8bf9ade"
TWIN_ID = "e74c9063d451e316"
SEED = "20260925"


class EvidenceRefused(ValueError):
    """Input is missing, contradictory, or changed while being inspected."""


def _require_unsplit_forecast_ledger(src: Sources) -> None:
    """This audit hashes one physical legacy prefix, not the post-split logical ledger."""
    from backend.services import forecast_ledger

    marker = forecast_ledger.marker_path(src.root / forecast_ledger.LEGACY_NAME)
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise EvidenceRefused("cannot establish absence of forecast ledger migration marker") from exc
    raise EvidenceRefused("forecast ledger migration marker present; historical physical-prefix "
                          "audit refuses the split logical ledger")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Sources:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.records: dict[str, dict] = {}

    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root) or not p.is_file():
            raise EvidenceRefused(f"missing or outside data root: {rel}")
        return p

    def _record(self, rel: str, digest: str, size: int) -> None:
        prior = self.records.get(rel)
        if prior is not None:
            if (prior["sha256"], prior["complete_prefix_bytes"]) != (digest, size):
                raise EvidenceRefused(f"source changed between reads: {rel}")
            return
        self.records[rel] = {"sha256": digest, "complete_prefix_bytes": size,
                             "captured_utc": _now()}

    def json(self, rel: str) -> dict:
        p = self._path(rel)
        b = p.read_bytes()
        digest = hashlib.sha256(b).hexdigest()
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise EvidenceRefused(f"changed while reading: {rel}")
        try:
            value = json.loads(b)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EvidenceRefused(f"invalid JSON {rel}: {exc}") from exc
        if not isinstance(value, dict):
            raise EvidenceRefused(f"expected JSON object: {rel}")
        self._record(rel, digest, len(b))
        return value

    def jsonl(self, rel: str):
        """Read a complete captured prefix, then verify those exact bytes again.

        Appends after capture are excluded. Truncation, rewriting, or a partial
        final line refuses the audit. Rows are yielded one at a time.
        """
        p = self._path(rel)
        size = p.stat().st_size
        h = hashlib.sha256()
        with p.open("rb") as stream:
            remaining = size
            while remaining:
                line = stream.readline(remaining)
                if not line or not line.endswith(b"\n"):
                    raise EvidenceRefused(f"incomplete JSONL prefix: {rel}")
                remaining -= len(line)
                h.update(line)
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise EvidenceRefused(f"invalid JSONL row in {rel}: {exc}") from exc
                if not isinstance(row, dict):
                    raise EvidenceRefused(f"expected JSONL object: {rel}")
                yield row
        check = hashlib.sha256()
        with p.open("rb") as stream:
            remaining = size
            while remaining:
                b = stream.read(min(1024 * 1024, remaining))
                if not b:
                    raise EvidenceRefused(f"truncated while verifying: {rel}")
                check.update(b)
                remaining -= len(b)
        if check.digest() != h.digest():
            raise EvidenceRefused(f"prefix changed while reading: {rel}")
        self._record(rel, h.hexdigest(), size)


def _required(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceRefused(message)


def _priced(row: dict) -> bool:
    return row.get("roi_pct") is not None and row.get("equity") is not None


def _due_date(row: dict) -> date | None:
    try:
        return date.fromisoformat(str(row["resolves_after"])[:10])
    except (KeyError, ValueError):
        return None


def _weights(book: dict) -> dict[str, float]:
    return {p["ticker"]: float(p["weight"]) for p in book.get("positions", [])
            if p.get("ticker")}


def verify_original_twin(books: list[dict], contract: dict, rows: dict[str, dict],
                         dna: dict[str, dict]) -> dict:
    """Exact frozen lineage; never infer a control from a profitable name marker."""
    by_id = {b.get("book_id"): b for b in books}
    _required(len(books) == 2 and len(by_id) == 2, "duplicate original frozen book ID")
    parent, twin = by_id.get(PARENT_ID), by_id.get(TWIN_ID)
    _required(parent is not None and twin is not None, "original frozen books missing")
    _required(parent.get("name") == TARGETS[0] and twin.get("name") == TARGETS[1],
              "original book names/IDs mismatch")
    _required(parent.get("frozen_utc") == twin.get("frozen_utc")
              and parent.get("asof") == twin.get("asof")
              and parent.get("model") == twin.get("model"), "original twin epoch mismatch")
    _required(SEED in str(twin.get("strategy", ""))
              and f"CONTROL for {TARGETS[0]}" in str(twin.get("strategy", "")),
              "original control seed/statement missing")
    sel, tw = contract.get("selection", {}), contract.get("twin", {})
    _required(sel.get("book_id") == PARENT_ID and tw.get("book_id") == TWIN_ID
              and sel.get("book_frozen_utc") == parent["frozen_utc"],
              "hack2 contract does not bind original pair")
    _required(_weights(parent) == {k: float(v) for k, v in
              ((p["ticker"], p["weight"]) for p in sel.get("positions", []))},
              "contract parent weights differ")
    _required(_weights(twin) == {k: float(v) for k, v in tw.get("weights", {}).items()},
              "contract twin weights differ")
    a, b = rows[TARGETS[0]], rows[TARGETS[1]]
    da, db = dna[TARGETS[0]], dna[TARGETS[1]]
    for field in ("inception", "last_mark", "spy_same_window_pct"):
        _required(a.get(field) is not None and a.get(field) == b.get(field),
                  f"original twin {field} mismatch")
    _required(da.get("sessions_graded") == db.get("sessions_graded")
              and da.get("sessions_graded", 0) > 0, "original twin sessions mismatch")
    _required(da.get("book_id") == PARENT_ID and db.get("book_id") == TWIN_ID,
              "DNA original book IDs mismatch")
    return {"parent_book_id": PARENT_ID, "twin_book_id": TWIN_ID,
            "frozen_utc": parent["frozen_utc"], "seed": int(SEED),
            "inception": a["inception"], "last_mark": a["last_mark"],
            "sessions_graded": da["sessions_graded"],
            "same_mark_gap_pp": round(float(a["roi_pct"]) - float(b["roi_pct"]), 3),
            "published_dna_twin_of": db.get("twin_of"),
            "published_dna_category": db.get("category"),
            "interpretation": "descriptive frozen-control mark difference; no published fair-twin join"}


def paper_census(src: Sources, run_id: str) -> dict:
    base = "paper_accounts/"
    roi = src.json(base + f"roi_{run_id}.json")
    dna = src.json(base + f"book_dna_{run_id}.json")
    voice = src.json(base + f"results_voice_{run_id}.json")
    _required(roi.get("run_id") == run_id and voice.get("run_id") == run_id
              and dna.get("roi_receipt_generated_utc") == roi.get("generated_utc")
              and voice.get("roi_generated_utc") == roi.get("generated_utc")
              and voice.get("book_dna_generated_utc") == dna.get("generated_utc"),
              "matched paper receipts differ")
    rows = roi.get("rows", [])
    books = dna.get("books", [])
    _required(isinstance(rows, list) and isinstance(books, list), "paper rows missing")
    rr = {r["account"]: r for r in rows}
    dd = {b["account"]: b for b in books}
    _required(len(rr) == len(rows) and len(dd) == len(books), "duplicate account identity")
    priced = [r for r in rows if _priced(r)]
    comparable = [r for r in priced if r.get("spy_same_window_pct") is not None]
    missing_roi = [{"account": r["account"], "family": r.get("family"),
                    "status": r.get("status")} for r in rows if not _priced(r)]
    missing_spy = Counter(r.get("family") for r in priced
                          if r.get("spy_same_window_pct") is None)
    aggregate = roi.get("aggregate", {})
    _required(aggregate.get("all_priced", {}).get("n") == len(priced)
              and aggregate.get("n_ahead_of_spy", 0) + aggregate.get("n_behind_spy", 0)
              == len(comparable), "ROI aggregate denominator mismatch")
    excluded = {x["account"]: x.get("why") for x in voice.get("excluded_controls", [])}
    _required(set(excluded) <= set(rr), "voice excludes unknown accounts")
    strategies = []
    for r in comparable:
        if r["account"] in excluded:
            continue
        strategies.append({"account": r["account"], "family": r.get("family"),
                           "roi_pct": r["roi_pct"], "spy_pct": r["spy_same_window_pct"],
                           "vs_spy_pp": r["vs_spy_pp"], "outcome": (
                               "ahead" if r["vs_spy_pp"] > 0 else "behind_or_equal"),
                           "last_mark": r.get("last_mark")})
    ahead = sum(r["outcome"] == "ahead" for r in strategies)
    head = voice.get("headline", {})
    _required(len(strategies) == head.get("n_strategy_accounts")
              and ahead == head.get("n_ahead")
              and len(strategies) - ahead == head.get("n_behind"),
              "voice strategy census mismatch")
    dna_winners = {b["account"] for b in books if b.get("category") == "strategy"
                   and isinstance(b.get("excess_pp"), (int, float))
                   and b["excess_pp"] > 0}
    voice_winners = {r["account"] for r in strategies if r["outcome"] == "ahead"}
    delta = sorted(dna_winners - voice_winners)
    _required(len(dna_winners) == aggregate.get("n_ahead_strategy")
              and not (voice_winners - dna_winners), "DNA strategy winners mismatch")
    target_ids = {n: dd.get(n, {}).get("book_id") for n in TARGETS}
    _required(all(target_ids.values()) and len(set(target_ids.values())) == len(TARGETS),
              "revision DNA book IDs missing or duplicated")
    selected_books = [b for b in src.jsonl("llm_portfolio/books.jsonl")
                      if b.get("book_id") in set(target_ids.values())]
    _required(len(selected_books) == len(TARGETS), "revision frozen book IDs missing/duplicate")
    frozen = [b for b in selected_books if b.get("book_id") in (PARENT_ID, TWIN_ID)]
    contract = src.json("paper_accounts/fleet_manager/contracts/hack2_v2.json")
    twin = verify_original_twin(frozen, contract, rr, dd)
    by_book = {b["book_id"]: b for b in selected_books}
    _required(all(by_book[target_ids[n]].get("name") == n for n in TARGETS),
              "revision book name/ID mismatch")
    holdings = {n: {p["ticker"] for p in by_book[target_ids[n]].get("positions", [])
                    if p.get("ticker") and p["ticker"] != "CASH"}
                for n in TARGETS}
    overlap = {n: {"shared_names": len(holdings[TARGETS[0]] & holdings[n]),
                   "union_names": len(holdings[TARGETS[0]] | holdings[n])}
               for n in TARGETS[1:]}
    family = {}
    for r in strategies:
        f = family.setdefault(str(r["family"]), {"accounts": 0, "ahead": 0, "behind_or_equal": 0})
        f["accounts"] += 1
        f[r["outcome"]] += 1
    return {"run_id": run_id, "roi_generated_utc": roi.get("generated_utc"),
            "dna_generated_utc": dna.get("generated_utc"),
            "counts": {"rows": len(rows), "priced": len(priced),
                       "own_window_spy": len(comparable),
                       "dna_strategy_ahead": len(dna_winners),
                       "voice_strategy_accounts": len(strategies),
                       "voice_ahead": ahead, "voice_behind": len(strategies) - ahead,
                       "voice_excluded_controls": len(excluded)},
            "missing_roi": missing_roi, "priced_missing_spy_by_family": dict(missing_spy),
            "dna_category_counts": dict(Counter(b.get("category") for b in books)),
            "excluded_control_reasons": dict(Counter(excluded.values())),
            "winner_definition_difference": [
                {"account": n, "family": rr[n].get("family"),
                 "vs_spy_pp": rr[n]["vs_spy_pp"], "voice_reason": excluded.get(n)}
                for n in delta],
            "strategies": sorted(strategies, key=lambda x: x["account"]),
            "strategy_families": family, "revision_name_overlap": overlap,
            "displayed_losers": [
                {"account": x.get("account"), "vs_spy_pp": x.get("vs_spy_pp")}
                for x in voice.get("losers", [])],
            "original_twin": twin}


def _net(lb: dict, name: str) -> float:
    found = [x for x in lb.get("grades", []) if x.get("name") == name]
    _required(len(found) == 1 and found[0].get("to_date", {}).get("status") == "OK"
              and found[0]["to_date"].get("net") is not None,
              f"frozen grade missing: {name}")
    return float(found[0]["to_date"]["net"])


def common_window(src: Sources, start_file: str, end_file: str) -> dict:
    base = "llm_portfolio/"
    start = src.json(base + start_file)
    end = src.json(base + end_file)
    first, last = start.get("bars_through"), end.get("bars_through")
    _required(first and last and first < last, "frozen leaderboard dates invalid")
    grades = [r for r in src.jsonl("paper_accounts/fleet_manager/grades.jsonl")
              if r.get("role") == "hack2" and first < str(r.get("session", "")) <= last]
    grades.sort(key=lambda x: x["session"])
    _required(len(grades) == len({r["session"] for r in grades}) and grades,
              "fleet grade dates duplicate/missing")
    _required(grades[0].get("prev_session") == first and grades[-1]["session"] == last
              and all(b.get("prev_session") == a.get("session")
                      for a, b in zip(grades, grades[1:])),
              "fleet grade session chain has a gap")
    expected = []
    cursor = date.fromisoformat(first) + timedelta(days=1)
    stop = date.fromisoformat(last)
    while cursor <= stop:
        if cursor.weekday() < 5:
            expected.append(str(cursor))
        cursor += timedelta(days=1)
    _required([r["session"] for r in grades] == expected,
              "fleet grade missing weekday session (or market holiday needs explicit review)")
    _required(all(r.get("contract_version") == "v2"
                  and r.get("policy_hash") == "2301fa30c7b851df"
                  and r.get("twin_priced_share") == 1.0
                  and all(isinstance(r.get(k), (int, float))
                          for k in ("account_return", "spy_return", "twin_return"))
                  for r in grades), "fleet grade policy/pricing missing")
    frozen = {n: round(100 * ((1 + _net(end, n)) / (1 + _net(start, n)) - 1), 3)
              for n in TARGETS}
    fleet = {k: round(100 * (math.prod(1 + r[k] for r in grades) - 1), 3)
             for k in ("account_return", "spy_return", "twin_return")}
    return {"first_mark": first, "last_mark": last,
            "sessions": [r["session"] for r in grades],
            "frozen_net_endpoint_ratio_pct": frozen,
            "fleet_compounded_pct": fleet,
            "interpretation": "descriptive aligned marks; broker timing/cash differ"}


def partial_fills(src: Sources) -> dict:
    base = "paper_accounts/fleet_manager/"
    decisions = [r for r in src.jsonl(base + "decisions.jsonl")
                 if r.get("role") == "hack2"]
    modes = Counter(str(r.get("mode")) for r in decisions)
    run_dir = src.root / base / "runs"
    _required(run_dir.is_dir(), "fleet runs missing")
    by_order: dict[str, dict] = {}
    for p in sorted(run_dir.glob("run_*.json")):
        run = src.json(str(p.relative_to(src.root)).replace("\\", "/"))
        accounts = run.get("accounts", [])
        if not isinstance(accounts, list):
            continue
        for account in accounts:
            if account.get("role") != "hack2":
                continue
            for action in account.get("actions", []):
                oid = action.get("order_id")
                if oid and float(action.get("filled_qty") or 0) > 0:
                    by_order[str(oid)] = {"kind": action.get("kind"),
                                          "status": action.get("entry_status")}
    return {"decision_rows": len(decisions), "modes": dict(modes),
            "order_ids_with_nonzero_filled_qty_in_run_snapshots": len(by_order),
            "reported_statuses": dict(Counter(x["status"] for x in by_order.values())),
            "fee_attribution": "unavailable",
            "limitation": "partial action snapshots, not a complete fill or fee ledger"}


def forecast_census(src: Sources, source_day: str, asof: date) -> tuple[dict, dict]:
    from backend.services import forecast_grader, source_registry

    _require_unsplit_forecast_ledger(src)
    selected: dict[tuple, dict] = {}
    selected_ids: set[str] = set()
    all_counts = Counter()
    cases: dict[str, list[dict]] = {x: [] for x in ("GPRO", "PSNL", "TEM")}
    for row in src.jsonl("predictions.jsonl"):
        all_counts["rows"] += 1
        if row.get("outcome") is not None:
            all_counts["resolved"] += 1
        elif row.get("void_reason"):
            all_counts["void"] += 1
        elif _due_date(row) is None:
            all_counts["missing_or_invalid_due_date"] += 1
        elif _due_date(row) <= asof:
            all_counts["date_due_unresolved"] += 1
        else:
            all_counts["not_date_due"] += 1
        if row.get("ticker") in cases:
            case = {
                k: row.get(k) for k in ("prediction_id", "specialist", "horizon_days",
                                        "probability", "made_at", "resolves_after",
                                        "resolved_at", "outcome")}
            detail = row.get("resolution_detail") or {}
            if isinstance(detail, dict) and row.get("outcome") is not None:
                case["realised_return"] = detail.get("realised_return")
                case["vs_benchmark"] = detail.get("vs_benchmark")
                case["n_bars"] = detail.get("n_bars")
            cases[row["ticker"]].append(case)
        if str(row.get("made_at", "")).startswith(source_day) and row.get("specialist") in SOURCE_COLUMNS:
            key = (row.get("specialist"), row.get("ticker"), row.get("horizon_days"),
                   row.get("input_snapshot_hash"))
            _required(key not in selected, "duplicate original forecast key")
            prediction_id = row.get("prediction_id")
            _required(isinstance(prediction_id, str) and prediction_id
                      and prediction_id not in selected_ids,
                      "duplicate or missing original prediction ID")
            selected[key] = row
            selected_ids.add(prediction_id)
    _required(bool(selected), "no original forecasts for source day")
    claims, constructed, matched = 0, 0, 0
    constructed_keys: set[tuple] = set()
    constructed_ids: set[str] = set()
    for c in src.jsonl("sources/claims.jsonl"):
        if c.get("source_id") not in {s.removeprefix("source:") for s in SOURCE_COLUMNS}:
            continue
        if not str(c.get("observed_utc", "")).startswith(source_day):
            continue
        claims += 1
        for row in source_registry.claim_rows(
                c["source_id"], c["ticker"], c["claim_text"], c["claim_utc"],
                direction=c.get("direction"), source_kind=c.get("source_kind", ""),
                post_url=c.get("post_url", ""), made_at=c["observed_utc"]):
            constructed += 1
            key = (row["specialist"], row["ticker"], row["horizon_days"],
                   row["input_snapshot_hash"])
            prediction_id = row["prediction_id"]
            _required(key not in constructed_keys and prediction_id not in constructed_ids,
                      "duplicate constructed forecast key or prediction ID")
            constructed_keys.add(key)
            constructed_ids.add(prediction_id)
            original = selected.get(key)
            _required(original is not None and all(row[k] == original[k] for k in
                      ("prediction_id", "probability", "made_at", "input_snapshot_hash",
                       "observable", "benchmark")), "original forecast reproduction mismatch")
            matched += 1
    _required(constructed > 0 and constructed_keys == set(selected)
              and constructed_ids == selected_ids,
              "original forecast set not fully reproduced")
    by_horizon: dict[str, dict] = {}
    for h in sorted({r["horizon_days"] for r in selected.values()}):
        cohort = [r for r in selected.values() if r["horizon_days"] == h]
        _required(all(_due_date(r) is not None for r in cohort),
                  "original forecast due date missing")
        buckets = Counter(forecast_grader.bucket_of(r, today=asof) for r in cohort)
        by_horizon[str(h)] = {"n": len(cohort),
                              "resolved": buckets.get("graded", 0),
                              "void": buckets.get("VOID", 0),
                              "not_yet_due": buckets.get("not_yet_due", 0),
                              "date_due_unresolved": sum(
                                  r.get("outcome") is None and not r.get("void_reason")
                                  and _due_date(r) <= asof
                                  for r in cohort),
                              "buckets": dict(buckets),
                              "outcome_1": sum(r.get("outcome") == 1 for r in cohort),
                              "outcome_0": sum(r.get("outcome") == 0 for r in cohort),
                              "recorded_resolves_after": sorted({r.get("resolves_after")
                                                                for r in cohort})}
    probabilities = Counter(str(r["probability"]) for r in selected.values())
    _required(all(r.get("observable") == "beats_benchmark"
                  and r.get("benchmark") == "SPY" for r in selected.values()),
              "source probability is not P(beats SPY)")
    _require_unsplit_forecast_ledger(src)
    return ({"source_day": source_day, "asof_date": str(asof),
             "ledger_scope": "pre-migration physical legacy prefix only",
             "claim_rows": claims, "constructed": constructed, "matched": matched,
             "probability_semantics": "P(beats SPY), not P(absolute up)",
             "probabilities": dict(probabilities), "by_horizon": by_horizon,
             "recorded_due_convention": "belief_state.resolution_date uses calendar buffer; actual session bars required for resolution",
             "ledger_all_counts": dict(all_counts)}, cases)


def _poll(src: Sources) -> dict:
    rows = list(src.jsonl("news_corpus/dowjones/_structured/barrons_big_money_poll.jsonl"))
    _required(len(rows) == 1, "poll row count mismatch")
    poll = rows[0]
    article = src.json("news_corpus/dowjones/barrons/2026-09-26/"
                       "6c4f10ed9906349773f0.json")
    _required(poll.get("article_sha") == article.get("sha")
              and poll.get("published_utc") == article.get("published_utc")
              and poll.get("first_seen_utc") == article.get("first_seen_utc")
              and article.get("pit_grade") == "archive", "archive poll lineage mismatch")
    values = [poll.get(x) for x in ("bullish_pct", "bearish_pct", "neutral_pct")]
    _required(all(isinstance(x, (int, float)) for x in values), "poll values missing")
    body = article.get("text", "")
    _required(bool(re.search(r"47% of professional investors are bullish", body, re.I))
              and bool(re.search(r"19% of money managers are bearish", body, re.I))
              and bool(re.search(r"Another 34% say they are neutral", body, re.I)),
              "article poll percentages not recoverable")
    return {"published_utc": poll["published_utc"],
            "first_seen_utc": poll["first_seen_utc"],
            "stored_vector": values, "stored_sum": sum(values),
            "usable_probability_vector": sum(values) == 100,
            "article_vector": [47, 19, 34],
            "diagnosis": "stored bullish 57 belongs to overvaluation question; archive, no forecast"}


def cases_and_poll(src: Sources, cases: dict[str, list[dict]],
                   asof: date) -> dict:
    article = src.json("news_corpus/dowjones/wsj/2026-09-26/"
                       "394c556d2550d759034b.json")
    claims_job = src.json("dowjones/claims_2026-09-26_205050.json")
    _required(article.get("pit_grade") == "first_seen_only"
              and article.get("published_utc") < article.get("first_seen_utc"),
              "WSJ article timing invalid")
    claim_rows = [r for r in src.jsonl("sources/claims.jsonl")
                  if r.get("ticker") in ("PSNL", "TEM")
                  and r.get("post_url") == article.get("url")]
    _required(len(claim_rows) == 2, "PSNL/TEM original claims missing")
    _required(all(article["first_seen_utc"] <= r.get("observed_utc", "")
                  for r in claim_rows), "claim precedes source ingestion")
    parsed = [r for r in claims_job.get("per_article", [])
              if r.get("sha") == article.get("sha")]
    _required(len(parsed) == 1 and parsed[0].get("status") == "OK"
              and parsed[0].get("forecast_rows") == 6
              and claims_job.get("started_utc", "") <= min(
                  r.get("observed_utc", "") for r in claim_rows),
              "PSNL/TEM parse receipt does not match forecasts")
    cards = {t: src.json(f"thesis_cards/2026-09-27/{t}.json")
             for t in ("PSNL", "TEM")}
    frozen_holdings = Counter()
    for book in src.jsonl("llm_portfolio/books.jsonl"):
        frozen_day = str(book.get("frozen_utc", ""))[:10]
        if not frozen_day or frozen_day > "2026-09-27":
            continue
        for ticker in {p.get("ticker") for p in book.get("positions", [])} & set(cases):
            frozen_holdings[ticker] += 1
    decisions = {}
    for p in sorted((src.root / "decisions").glob("2026-*.json")):
        day = p.stem
        if day > str(asof):
            continue
        d = src.json(f"decisions/{day}.json")
        decisions[day] = {t: sum(r.get("ticker") == t for r in d.get("rows", []))
                          for t in cases}
    archive = []
    for p in sorted((src.root / "news_corpus" / "alpaca_benzinga_news").glob("2026-*.jsonl")):
        rel = str(p.relative_to(src.root)).replace("\\", "/")
        archive.extend(r for r in src.jsonl(rel)
                       if "GPRO" in r.get("tickers", []))
    return {"PSNL_TEM": {
                "article_sha": article["sha"],
                "article_published_utc": article["published_utc"],
                "first_seen_utc": article["first_seen_utc"],
                "claims_job_started_utc": claims_job.get("started_utc"),
                "claim_ids": {r["ticker"]: r["claim_hash"] for r in claim_rows},
                "claim_observed_utc": {r["ticker"]: r["observed_utc"] for r in claim_rows},
                "parse_completion_exact_utc": None,
                "forecasts": {t: cases[t] for t in ("PSNL", "TEM")},
                "cards": {t: {k: cards[t].get(k) for k in
                              ("run_utc", "verdict", "confidence", "refusal_why")}
                          for t in cards},
                "decision_rows_inspected": decisions,
                "frozen_book_holdings_through_2026_09_27": {
                    t: frozen_holdings[t] for t in ("PSNL", "TEM")},
                "order_fill_status": "unknown; no exact decision rows in inspected days"},
            "GPRO": {"forecast_rows": cases["GPRO"],
                     "decision_rows_inspected": {d: v["GPRO"] for d, v in decisions.items()},
                     "frozen_book_holdings_through_2026_09_27": frozen_holdings["GPRO"],
                     "archived_articles_exact_tagged": len(archive),
                     "archived_article_publication_years": dict(Counter(
                         str(r.get("published_utc", ""))[:4] for r in archive)),
                     "archived_first_seen_range": [
                         min((r["first_seen_utc"] for r in archive), default=None),
                         max((r["first_seen_utc"] for r in archive), default=None)],
                     "chronology": "missing; historical crowd-list mention is not a trade"},
            "archive_poll": _poll(src)}


def build(data_root: Path, run_id: str, source_day: str, asof: date,
          start_file: str, end_file: str) -> dict:
    src = Sources(data_root)
    paper = paper_census(src, run_id)
    window = common_window(src, start_file, end_file)
    fills = partial_fills(src)
    forecast, cases = forecast_census(src, source_day, asof)
    examples = cases_and_poll(src, cases, asof)
    _required(examples["archive_poll"]["usable_probability_vector"] is False,
              "bad historical poll unexpectedly passes vector guard")
    _require_unsplit_forecast_ledger(src)
    return {"schema": "original_evidence_audit/1", "captured_utc": _now(),
            "asof_date": str(asof), "data_root_policy": "caller-supplied read-only root",
            "paper": paper, "common_window": window, "partial_fills": fills,
            "original_forecasts": forecast, "cases": examples,
            "sources": src.records,
            "limits": ["descriptive paper evidence only", "no live grading or new labels",
                       "no strategy variants or retrospective challenger run",
                       "forecast census is the pre-migration physical legacy prefix only",
                       "per-source complete prefixes, not an atomic cross-file snapshot"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, required=True,
                    help="existing backend/data/optimus root (read-only)")
    ap.add_argument("--run-id", required=True, help="matched ROI/DNA/voice run ID")
    ap.add_argument("--source-day", default="2026-09-26")
    ap.add_argument("--asof", type=date.fromisoformat, required=True)
    ap.add_argument("--start-leaderboard", default="leaderboard_2026-09-28.json")
    ap.add_argument("--end-leaderboard", default="leaderboard_2026-10-08.json")
    ap.add_argument("--out", type=Path, required=True,
                    help="private JSON outside the repository and data root")
    args = ap.parse_args(argv)
    output = args.out.resolve()
    repo = Path(__file__).resolve().parents[1]
    data_root = args.data_root.resolve()
    runtime_repo = data_root.parents[2]
    if (output.is_relative_to(repo) or output.is_relative_to(runtime_repo)
            or output.is_relative_to(data_root)):
        ap.error("--out must be outside both repositories and the data root")
    if output.exists():
        ap.error("--out already exists; use a fresh dated receipt")
    report = build(args.data_root, args.run_id, args.source_day, args.asof,
                   args.start_leaderboard, args.end_leaderboard)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"OK {output} sources={len(report['sources'])} "
          f"paper={report['paper']['counts']} "
          f"forecast={report['original_forecasts']['constructed']}/"
          f"{report['original_forecasts']['matched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
