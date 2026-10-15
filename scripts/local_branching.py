"""Deterministic private PRODUCT_EXPERIMENT branches of frozen factory books.

Run `python -m scripts.local_branching preview|freeze|grade`. This never writes
the production book ledger, tracked paper NAV, broker state, or trial registry.
The blocked inferential family draft gives these descriptive marks no promotion
authority. See docs/research/LOCAL_BRANCHING_PRODUCT_CONTRACT_2026-10-14.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from backend.services import llm_portfolio as LP


CONTRACT = "docs/research/LOCAL_BRANCHING_PRODUCT_CONTRACT_2026-10-14.md"
OUT = Path.home() / "aegis-recovery-evidence" / "oct14-continuation-20261014" / "local-branching"
SOURCE_ROOT = Path.home() / "aegis-finance" / "backend" / "data" / "optimus"
SOURCE_LEDGER = SOURCE_ROOT / "llm_portfolio" / "books.jsonl"
OMIT_SLOTS = range(1, 7)
WEIGHT_RULES = ("equal", "parent_proportional")
MAX_BAR_AGE_DAYS = 5
FROZEN_COHORT = date(2026, 10, 14)
FROZEN_RECEIPT_SHA256 = "0fb53e80c1d6be0a4e25519d54ddbc3e88bea0396ac46397292fdfa7df92fa96"
FROZEN_LEDGER_SHA256 = "77c97204549fe819e52b623be6b744220c8e7fd2ffe46350ac9c7e4b9b31bdba"
FROZEN_IDS_SHA256 = "a4aaa677a205d7cf05975a3cdab24cda624051c7995ed533dae38f70164e2ef8"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON token: {value}")


def _finite_tree(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite_tree(v) for v in value)
    return True


def verified_frozen_books(ledger: Path, receipt_path: Path,
                          *, cohort: date = FROZEN_COHORT) -> list[dict]:
    """Refuse partial/tampered private cohorts before LP's permissive JSONL reader."""
    if cohort != FROZEN_COHORT:
        raise ValueError("only the pinned 2026-10-14 private cohort may be graded")
    if digest(receipt_path) != FROZEN_RECEIPT_SHA256:
        raise ValueError("private freeze receipt bytes differ from inception pin")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"),
                         parse_constant=_reject_constant)
    if (receipt.get("status") != "FROZEN_PRIVATE" or
            receipt.get("licence") != "PRODUCT_EXPERIMENT" or
            receipt.get("asof") != cohort.isoformat() or
            receipt.get("contract_commit") != "8253f6d8" or
            Path(receipt.get("private_ledger", "")).resolve() != ledger.resolve() or
            receipt.get("private_ledger_sha256") != FROZEN_LEDGER_SHA256 or
            receipt.get("frozen_total") != 247 or
            receipt.get("frozen_branches") != 228 or
            receipt.get("same_date_controls") != 19 or
            receipt.get("eligible_parents") != 19 or
            receipt.get("source_parents") != 20 or
            receipt.get("rule_grid") != {"omit_slots": list(OMIT_SLOTS),
                                         "weight_rules": list(WEIGHT_RULES)}):
        raise ValueError("private freeze receipt violates frozen contract")
    if digest(ledger) != receipt["private_ledger_sha256"]:
        raise ValueError("private ledger bytes differ from freeze receipt")
    rows = []
    for line_no, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"empty private ledger row {line_no}")
        try:
            row = json.loads(line, parse_constant=_reject_constant)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"malformed private ledger row {line_no}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object private ledger row {line_no}")
        if not _finite_tree(row):
            raise ValueError(f"non-finite private ledger row {line_no}")
        rows.append(row)
    ids = [b.get("book_id") for b in rows]
    if (len(rows) != 247 or any(not isinstance(i, str) or not i for i in ids) or
            len(set(ids)) != 247 or
            hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()
            != FROZEN_IDS_SHA256):
        raise ValueError("private ledger ID set/count differs from inception")
    refused = {r["source_book_id"] for r in receipt["refused_parents"]}
    parents = set(receipt["source_ids"]) - refused
    if len(parents) != 19:
        raise ValueError("private parent/refusal set differs from contract")
    arms: Counter = Counter()
    for row in rows:
        src = row.get("source")
        pos = row.get("positions")
        if (row.get("schema") != "llm_portfolio/1" or
                row.get("asof") != cohort.isoformat() or
                row.get("state") != "READY" or
                row.get("model") != "deterministic_existing_factory_branch" or
                row.get("benchmark") != "SPY" or
                row.get("horizon_days") != [21, 63, 126] or
                row.get("start_capital_usd") != 1_000_000 or
                not isinstance(src, dict) or not isinstance(pos, list) or len(pos) < 2):
            raise ValueError("private book violates frozen contract")
        parent = src.get("source_book_id")
        slot = src.get("omit_slot")
        rule = src.get("weight_rule")
        if (src.get("type") != "local_branching_product_experiment" or
                src.get("contract") != CONTRACT or
                src.get("source_asof") != "2026-09-25" or parent not in parents or
                (slot, rule) not in ({(None, "parent_proportional")} |
                                     {(s, r) for s in OMIT_SLOTS for r in WEIGHT_RULES}) or
                row.get("kind") != ("control" if slot is None else "personal") or
                (slot is None) != (src.get("omitted_ticker") is None)):
            raise ValueError("private book source arm violates frozen contract")
        tickers = [p.get("ticker") for p in pos if isinstance(p, dict)]
        weights = [p.get("weight") for p in pos if isinstance(p, dict)]
        if (len(tickers) != len(pos) or len(set(tickers)) != len(pos) or
                "CASH" not in tickers or
                any(not isinstance(t, str) or not t for t in tickers) or
                any(not isinstance(w, (int, float)) or isinstance(w, bool) or
                    not math.isfinite(w) or w < 0 for w in weights) or
                abs(sum(weights) - 1.0) > 1e-5):
            raise ValueError("private book positions are invalid")
        arms[(parent, slot, rule)] += 1
    required = {(p, None, "parent_proportional") for p in parents} | {
        (p, s, r) for p in parents for s in OMIT_SLOTS for r in WEIGHT_RULES}
    if set(arms) != required or any(n != 1 for n in arms.values()):
        raise ValueError("private source grid is incomplete or duplicated")
    books = LP.read_books(ledger)
    if [b.get("book_id") for b in books] != ids:
        raise ValueError("shared portfolio reader differs from strict private readback")
    return books


def source_parents(path: Path = SOURCE_LEDGER) -> list[dict]:
    parents = [b for b in LP.read_books(path) if b.get("source") == "book_factory"
               and b.get("kind") in ("personal", "competition")
               and not b.get("parent_book_id")]
    if len(parents) != 20 or len({b["book_id"] for b in parents}) != 20:
        raise ValueError(f"expected 20 distinct factory parents, found {len(parents)}")
    return sorted(parents, key=lambda b: b["book_id"])


def cached_bars(symbols: set[str], root: Path = SOURCE_ROOT) -> pd.DataFrame:
    paths = (root / "prices_2025_26" / "bars.parquet",
             root / "llm_portfolio" / "global_bars.parquet")
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"cached-price input missing: {p}")
    cols = ["symbol", "date", "open", "close", "volume"]
    us = pd.read_parquet(paths[0], columns=cols,
                         filters=[("symbol", "in", sorted(symbols))])
    global_ = pd.read_parquet(paths[1], columns=cols,
                              filters=[("symbol", "in", sorted(symbols))])
    bars = LP.union_bars(us, global_)
    return bars[bars["symbol"].isin(symbols)].copy()


def latest_valid_bars(bars: pd.DataFrame) -> dict[str, str]:
    valid = bars[(bars["open"] > 0) & (bars["close"] > 0)].copy()
    valid["date"] = pd.to_datetime(valid["date"])
    return {str(s): str(pd.Timestamp(d).date())
            for s, d in valid.groupby("symbol")["date"].max().items()}


def eligible(parents: list[dict], latest: dict[str, str], asof: date) -> tuple[list[dict], list[dict]]:
    floor = asof - timedelta(days=MAX_BAR_AGE_DAYS)
    if "SPY" not in latest or date.fromisoformat(latest["SPY"]) < floor:
        raise ValueError(f"SPY benchmark missing/stale; latest={latest.get('SPY')}")
    good, refused = [], []
    for parent in parents:
        names = [p["ticker"] for p in parent["positions"] if p["ticker"] != "CASH"]
        stale = [{"ticker": s, "last_valid_bar": latest.get(s)} for s in names
                 if s not in latest or date.fromisoformat(latest[s]) < floor]
        if len(names) < 7:
            refused.append({"source_book_id": parent["book_id"], "name": parent["name"],
                            "reason": "fewer than seven names"})
        elif stale:
            refused.append({"source_book_id": parent["book_id"], "name": parent["name"],
                            "reason": "stale or missing current price", "names": stale})
        else:
            good.append(parent)
    return good, refused


def _cash(parent: dict) -> float:
    return sum(float(p["weight"]) for p in parent["positions"] if p["ticker"] == "CASH")


def candidate(parent: dict, *, asof: date, slot: int | None,
              weight_rule: str = "parent_proportional") -> dict:
    names = [p for p in parent["positions"] if p["ticker"] != "CASH"]
    if slot is not None and (slot < 1 or slot > len(names)):
        raise ValueError("omission slot outside the source's presentation order")
    omitted = names[slot - 1]["ticker"] if slot is not None else None
    kept = [p for i, p in enumerate(names, start=1) if i != slot]
    cash = _cash(parent)
    invested = 1.0 - cash
    raw = ([1.0] * len(kept) if weight_rule == "equal"
           else [float(p["weight"]) for p in kept])
    total = sum(raw)
    if total <= 0 or invested < 0:
        raise ValueError("source weights unusable")
    positions = [{"ticker": p["ticker"], "weight": invested * w / total,
                  "thesis": p.get("thesis", ""), "falsifier": p.get("falsifier", "")}
                 for p, w in zip(kept, raw)]
    positions.append({"ticker": "CASH", "weight": cash,
                      "thesis": "source declared cash", "falsifier": "not applicable"})
    arm = "control" if slot is None else f"omit{slot}_{weight_rule}"
    return {
        "name": f"local_loo_{parent['book_id']}_{arm}" + ("__control" if slot is None else ""),
        "kind": "control" if slot is None else "personal",
        "state": "READY", "objective": "descriptive 126-session net construction sensitivity vs same-vintage parent control and SPY",
        "model": "deterministic_existing_factory_branch", "benchmark": "SPY",
        "strategy": (f"Inherited 2026-09-25 source {parent['book_id']} ({parent['kind']}); "
                     f"presentation-order omitted {omitted or 'none'} at slot {slot or 0}; "
                     f"weight rule {weight_rule}; fixed holdings; no rebalance; no new signal"),
        "horizon_days": [21, 63, 126], "positions": positions,
        "source": {"type": "local_branching_product_experiment", "source_book_id": parent["book_id"],
                   "source_name": parent["name"], "source_kind": parent["kind"],
                   "source_asof": parent["asof"], "omit_slot": slot,
                   "omitted_ticker": omitted, "weight_rule": weight_rule,
                   "contract": CONTRACT},
    }


def population(parents: list[dict], asof: date, universe: set[str]) -> list[dict]:
    out = []
    for parent in parents:
        specs = [(None, "parent_proportional")]
        specs += [(slot, rule) for slot in OMIT_SLOTS for rule in WEIGHT_RULES]
        for slot, rule in specs:
            raw = candidate(parent, asof=asof, slot=slot, weight_rule=rule)
            out.append(LP.freeze(raw, today=asof, universe=universe))
    ids = [b["book_id"] for b in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate frozen book IDs")
    return out


def overlap_receipt(books: list[dict]) -> dict:
    controls = {b["source"]["source_book_id"]: b for b in books
                if b["source"]["omit_slot"] is None}
    sets, vectors, overlaps = defaultdict(list), defaultdict(list), []
    for b in books:
        positions = [p for p in b["positions"] if p["ticker"] != "CASH"]
        tickers = frozenset(p["ticker"] for p in positions)
        sets[tuple(sorted(tickers))].append(b["book_id"])
        vectors[tuple(sorted((p["ticker"], round(float(p["weight"]), 8))
                             for p in b["positions"]))].append(b["book_id"])
        control = controls[b["source"]["source_book_id"]]
        base = {p["ticker"]: p["weight"] for p in control["positions"]}
        now = {p["ticker"]: p["weight"] for p in b["positions"]}
        overlaps.append({"book_id": b["book_id"], "source_book_id": control["source"]["source_book_id"],
                         "ticker_jaccard": round(len(tickers & {s for s in base if s != "CASH"}) /
                                                 len(tickers | {s for s in base if s != "CASH"}), 6),
                         "weight_overlap": round(sum(min(now.get(s, 0), base.get(s, 0))
                                                     for s in set(now) | set(base)), 6)})
    return {"unique_ticker_sets": len(sets), "unique_weight_vectors": len(vectors),
            "ticker_set_duplicate_groups": [v for v in sets.values() if len(v) > 1],
            "weight_vector_duplicate_groups": [v for v in vectors.values() if len(v) > 1],
            "overlap_with_control": overlaps}


def execute(command: str, asof: date, *, grade_day: date | None = None,
            bars_override: pd.DataFrame | None = None,
            grade_evidence: dict | None = None,
            expected_session: date | None = None) -> dict:
    daydir = OUT / asof.isoformat()
    ledger = daydir / "books.jsonl"
    if command == "grade":
        books = verified_frozen_books(ledger, daydir / "freeze_receipt.json", cohort=asof)
        names = LP.book_tickers(books) | {"SPY"}
        bars = bars_override if bars_override is not None else cached_bars(names)
        spy = bars[(bars["symbol"] == "SPY") & (bars["open"] > 0) & (bars["close"] > 0)]
        if spy.empty:
            raise ValueError("SPY benchmark has no valid cached bar")
        benchmark_last_bar = str(pd.to_datetime(spy["date"]).max().date())
        observed_day = grade_day or date.today()
        if observed_day < asof:
            raise ValueError("grade day precedes cohort freeze date")
        if expected_session is not None:
            if observed_day != expected_session or benchmark_last_bar != expected_session.isoformat():
                raise ValueError("benchmark/cutoff differs from validated closed session")
            if pd.to_datetime(bars["date"]).max().date() != expected_session:
                raise ValueError("bar snapshot extends beyond validated closed session")
        result = LP.leaderboard(books, bars, today=observed_day, voided=[])
        if expected_session is not None:
            ids = [r.get("book_id") for r in result.get("books", [])]
            if (result.get("bars_through") != expected_session.isoformat() or
                    result.get("n_books") != 247 or result.get("n_twins") != 0 or
                    len(ids) != 247 or
                    hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()
                    != FROZEN_IDS_SHA256):
                raise ValueError("shared leaderboard differs from validated session or 247 frozen IDs")
        result.update({"licence": "PRODUCT_EXPERIMENT", "source_ledger": str(ledger),
                       "source_ledger_sha256": FROZEN_LEDGER_SHA256,
                       "freeze_receipt_sha256": FROZEN_RECEIPT_SHA256,
                       "benchmark_last_bar": benchmark_last_bar,
                       "grade_evidence": grade_evidence or {},
                       "grade_day": observed_day.isoformat(),
                       "note": "Descriptive marks; R13 inferential family draft blocked."})
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = daydir / f"grade_{stamp}.json"
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(result, indent=1, default=str) + "\n")
        return {"grade_receipt": str(path), "status_counts": result.get("status_counts"),
                "n_books": result.get("n_books"), "n_twins": result.get("n_twins"),
                "bars_through": result.get("bars_through"),
                "benchmark_last_bar": benchmark_last_bar}

    parents = source_parents()
    source_sha = digest(SOURCE_LEDGER)
    names = {p["ticker"] for b in parents for p in b["positions"] if p["ticker"] != "CASH"} | {"SPY"}
    bars = cached_bars(names)
    latest = latest_valid_bars(bars)
    good, refused = eligible(parents, latest, asof)
    fresh_universe = {s for s, day in latest.items()
                      if date.fromisoformat(day) >= asof - timedelta(days=MAX_BAR_AGE_DAYS)}
    books = population(good, asof, fresh_universe)
    expected = len(good) * (1 + len(OMIT_SLOTS) * len(WEIGHT_RULES))
    if len(books) != expected:
        raise AssertionError("population count mismatch")
    overlap = overlap_receipt(books)
    receipt = {"licence": "PRODUCT_EXPERIMENT", "status": "PREVIEW" if command == "preview" else "FROZEN_PRIVATE",
               "asof": asof.isoformat(), "contract_commit": "8253f6d8",
               "source_ledger_sha256": source_sha, "source_parents": len(parents),
               "eligible_parents": len(good), "refused_parents": refused,
               "planned_branches": len(parents) * len(OMIT_SLOTS) * len(WEIGHT_RULES),
               "frozen_branches": len(good) * len(OMIT_SLOTS) * len(WEIGHT_RULES),
               "same_date_controls": len(good), "frozen_total": len(books),
               "source_ids": [p["book_id"] for p in parents],
               "rule_grid": {"omit_slots": list(OMIT_SLOTS), "weight_rules": list(WEIGHT_RULES)},
               "multiplicity_attempts": len(good) * len(OMIT_SLOTS) * len(WEIGHT_RULES),
               **overlap}
    daydir.mkdir(parents=True, exist_ok=True)
    if command == "freeze":
        preview = daydir / "preview_receipt.json"
        if not preview.exists():
            raise ValueError("a source-pinned preview is required before freeze")
        pinned = json.loads(preview.read_text(encoding="utf-8"))
        if pinned.get("source_ledger_sha256") != source_sha or pinned.get("source_ids") != receipt["source_ids"]:
            raise ValueError("source ledger changed since preview; inspect and preview again")
        if ledger.exists():
            raise FileExistsError(f"private ledger already frozen: {ledger}")
        with ledger.open("x", encoding="utf-8") as f:
            for book in books:
                f.write(json.dumps(book, default=str) + "\n")
        readback = LP.read_books(ledger)
        if [b["book_id"] for b in readback] != [b["book_id"] for b in books]:
            raise RuntimeError("shared consumer readback differs from frozen rows")
        receipt["shared_consumer_readback"] = len(readback)
        receipt["private_ledger"] = str(ledger)
        receipt["private_ledger_sha256"] = digest(ledger)
    path = daydir / ("freeze_receipt.json" if command == "freeze" else "preview_receipt.json")
    path.write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8")
    return {"receipt": str(path), "source_parents": len(parents), "eligible_parents": len(good),
            "refused_parents": refused, "branches": receipt["frozen_branches"],
            "controls": len(good), "unique_ticker_sets": overlap["unique_ticker_sets"],
            "unique_weight_vectors": overlap["unique_weight_vectors"],
            "readback": receipt.get("shared_consumer_readback")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preview", "freeze", "grade"))
    parser.add_argument("--cohort", default=date.today().isoformat(),
                        help="actual freeze date and private ledger folder")
    parser.add_argument("--today", default=date.today().isoformat(),
                        help="grade cutoff date, ignored for preview/freeze")
    args = parser.parse_args()
    print(json.dumps(execute(args.command, date.fromisoformat(args.cohort),
                             grade_day=date.fromisoformat(args.today)), indent=2))


if __name__ == "__main__":
    main()
