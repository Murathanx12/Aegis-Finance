"""Read saved cohort evidence only; never import a producer, grader or executor.

No prices are fetched and no grades are recomputed. Missing evidence is None,
not zero. The only optional write is a new, explicitly named census receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path


OLD_LEDGER_SHA = "77c97204549fe819e52b623be6b744220c8e7fd2ffe46350ac9c7e4b9b31bdba"
OLD_RECEIPT_SHA = "0fb53e80c1d6be0a4e25519d54ddbc3e88bea0396ac46397292fdfa7df92fa96"
OLD_IDS_SHA = "a4aaa677a205d7cf05975a3cdab24cda624051c7995ed533dae38f70164e2ef8"
MANIFEST_SHA = "395304089d999350f9a510978cb801f83bb4f39cffab86a9e68559e9d12bbce1"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _reject(value: str) -> None:
    raise ValueError("NONFINITE_JSON: " + value)


def _pairs(pairs: list) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY: " + key)
        out[key] = value
    return out


def strict_json(raw: bytes | str) -> object:
    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            _reject(token)
        return value
    return json.loads(raw, parse_constant=_reject, parse_float=finite_float, object_pairs_hook=_pairs)


class Sources:
    """Byte identity and observation clocks, without mtime-as-evidence clocks."""

    def __init__(self) -> None:
        self.refs = {}

    def read(self, path: Path | str, *, lines: bool = False) -> object:
        path = Path(path).resolve()
        before = path.stat()
        if before.st_size > 32 * 1024**2:
            raise ValueError("BOUNDED_CENSUS_SOURCE: " + str(path))
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("SOURCE_CHANGED_DURING_READ: " + str(path))
        if lines:
            if not raw or not raw.endswith(b"\n") or any(not s.strip() for s in raw.splitlines()):
                raise ValueError("EMPTY_OR_TORN_JSONL: " + str(path))
            value = [strict_json(s) for s in raw.splitlines()]
        else:
            value = strict_json(raw)
        ref = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
               "bytes": len(raw), "read_at": datetime.now(timezone.utc).isoformat()}
        if isinstance(value, dict):
            ref["embedded_clocks"] = {k: value[k] for k in (
                "observed_at", "graded_utc", "generated_utc", "declared_at", "asof",
                "bars_through", "benchmark_last_bar", "grade_day", "closed_session",
                "reviewed_at") if k in value}
        self.refs[str(path)] = ref
        return value

    def ref(self, path: Path | str) -> dict:
        return self.refs[str(Path(path).resolve())]

    def verify_unchanged(self) -> None:
        for ref in self.refs.values():
            if hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest() != ref["sha256"]:
                raise ValueError("SOURCE_CHANGED_AFTER_READ: " + ref["path"])


def exact_join(expected: list, rows: list[dict], key: str = "book_id") -> dict:
    """Report dropped/duplicate/foreign IDs, including equal-count substitutions."""
    expected = list(expected)
    if len(expected) != len(set(expected)) or any(not isinstance(i, str) or not i for i in expected):
        raise ValueError("INVALID_EXPECTED_ID_SET")
    ids = [r.get(key) for r in rows]
    valid = [i for i in ids if isinstance(i, str) and i]
    counts = Counter(valid)
    missing, extra = sorted(set(expected) - set(valid)), sorted(set(valid) - set(expected))
    duplicates = {i: n for i, n in sorted(counts.items()) if n > 1}
    invalid = [n for n, i in enumerate(ids, 1) if not isinstance(i, str) or not i]
    return {"status": "EXACT" if not (missing or extra or duplicates or invalid) else "REFUSED",
            "expected_count": len(expected), "row_count": len(rows), "unique_ids": len(counts),
            "joined_ids": len(set(expected) & set(valid)), "missing_ids": missing,
            "extra_ids": extra, "duplicate_ids": duplicates, "invalid_id_rows": invalid,
            "expected_ids_sha256": digest(sorted(expected)), "actual_ids_sha256": digest(sorted(valid))}


def require_exact(join: dict) -> None:
    if join["status"] != "EXACT":
        raise ValueError("COHORT_ID_JOIN_REFUSED: " + json.dumps(join, sort_keys=True))


def finite(value: object) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def session_date(value: object) -> date:
    """Native grader session labels are ISO dates, not timestamps or prose."""
    if not isinstance(value, str):
        raise ValueError("ISO_SESSION_DATE_REQUIRED")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("ISO_SESSION_DATE_REQUIRED")
    return parsed


def aware_clock(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    return stamp.astimezone(timezone.utc)


def receipt_bounds(doc: dict) -> tuple[date | None, datetime | None, list[str]]:
    """Price bounds come from data/session fields, never file or generation time."""
    errors, dates, generated = [], [], []
    try:
        for field in ("closed_session", "bars_through", "benchmark_last_bar", "grade_day"):
            if field in doc:
                dates.append(session_date(doc[field]))
        if not dates or not any(k in doc for k in ("closed_session", "bars_through", "benchmark_last_bar")):
            errors.append("MISSING_RECEIPT_DATA_CLOCK")
        for field in ("graded_utc", "observed_at"):
            if field in doc:
                generated.append(aware_clock(doc[field]))
        if not generated:
            errors.append("MISSING_RECEIPT_GENERATION_CLOCK")
    except (TypeError, ValueError):
        errors.append("INVALID_RECEIPT_CLOCK")
    upper = min(dates) if dates else None
    created = min(generated) if generated else None
    # These two cohorts use SPY session dates. A receipt cannot contain a closed
    # SPY session in a later UTC day. This is a bound, not a trading-day calendar.
    if upper and created and upper > created.date():
        errors.append("DATA_CLOCK_AFTER_RECEIPT")
    return upper, created, errors


def outcome_errors(cell: dict, grade: dict) -> list[str]:
    required = ["gross", "net", "nav_usd"]
    if grade.get("benchmark_missing") is not True:
        required += ["benchmark_return", "vs_benchmark"]
    errors = ["INVALID_OUTCOME_" + k for k in required if not finite(cell.get(k))]
    if grade.get("grade_rule_version") == 2 and not finite(cell.get("weight_priced")):
        errors.append("INVALID_OUTCOME_weight_priced")
    return errors


def validate_saved_grade(book: dict, grade: dict, upper: date | None,
                         created: datetime | None, context_errors: list[str]) -> dict:
    """Check saved v1/v2 contracts without invoking the grader or a calendar.

    Entry is the benchmark session OPEN strictly after the frozen as-of date.
    Session counts come from the saved benchmark calendar, with only necessary
    date-order/calendar-day ceilings checked here; exact exchange replay is not
    claimed. Saved entry includes all-cash books and is not a fill/exposure flag.
    """
    errors = list(context_errors)
    if type(grade.get("grade_rule_version")) is not int or grade["grade_rule_version"] not in (1, 2):
        errors.append("UNSUPPORTED_GRADE_RULE_VERSION")
    td = grade.get("to_date")
    td = td if isinstance(td, dict) else {}
    entry = mark = None
    count = td.get("sessions")
    if grade.get("status") != "OK":
        errors.append("GRADE_NOT_OK")
    try:
        frozen, asof = aware_clock(book.get("frozen_utc")), session_date(book.get("asof"))
        entry, mark = session_date(grade.get("entry_session")), session_date(td.get("as_of"))
        if upper is None or created is None:
            errors.append("UNSUPPORTED_RECEIPT_CLOCKS")
        elif not (max(asof, frozen.date()) < entry <= mark <= upper) or frozen > created:
            errors.append("INVALID_ENTRY_MARK_ORDER_OR_DATA_BOUND")
    except (TypeError, ValueError):
        errors.append("INVALID_ENTRY_MARK_OR_FREEZE_CLOCK")
    if type(count) is not int or count <= 0:
        errors.append("POSITIVE_INTEGER_SESSIONS_REQUIRED")
    elif entry and mark and count > (mark - entry).days + 1:
        errors.append("SESSIONS_EXCEED_CALENDAR_DAY_CEILING")
    clock_errors = list(errors)
    entered = True if not clock_errors else None
    if grade.get("status") == "PENDING" and not grade.get("entry_session"):
        entered = False
    if td.get("status") != "OK":
        errors.append("TO_DATE_NOT_OK")
    errors += outcome_errors(td, grade)
    marked = True if not errors else None
    if grade.get("status") == "PENDING" and not td:
        marked = False

    declared = book.get("horizon_days")
    if (not isinstance(declared, list) or not declared or
            any(type(h) is not int or h <= 0 for h in declared) or len(set(declared)) != len(declared)):
        raise ValueError("INVALID_DECLARED_HORIZONS")
    horizon = grade.get("horizons")
    horizon = horizon if isinstance(horizon, dict) else {}
    expected = {str(h) for h in declared}
    horizon_errors = []
    if set(horizon) != expected:
        horizon_errors.append("DECLARED_HORIZON_SET_MISMATCH")
    if marked is not True:
        horizon_errors.append("HORIZONS_REQUIRE_VALID_SUCCESSFUL_GRADE")
    for h in declared:
        cell = horizon.get(str(h))
        if not isinstance(cell, dict):
            horizon_errors.append(f"{h}:MISSING_OR_NONOBJECT_CELL")
            continue
        status = cell.get("status")
        if status == "PENDING":
            if not isinstance(cell.get("why"), str) or not cell["why"].strip():
                horizon_errors.append(f"{h}:PENDING_REASON_REQUIRED")
            if type(count) is int and count >= h:
                horizon_errors.append(f"{h}:PENDING_AFTER_MATURITY")
        elif status == "OK":
            horizon_errors += [f"{h}:" + e for e in outcome_errors(cell, grade)]
            try:
                end = session_date(cell.get("as_of"))
                if (marked is not True or type(count) is not int or count < h or
                        entry is None or mark is None or upper is None or
                        not entry <= end <= mark <= upper or
                        (end - entry).days + 1 < h or (mark - end).days < count - h or
                        (h == count and end != mark)):
                    horizon_errors.append(f"{h}:UNSUPPORTED_HORIZON_SESSION_OR_CLOCK")
            except (TypeError, ValueError):
                horizon_errors.append(f"{h}:INVALID_HORIZON_CLOCK")
        else:
            horizon_errors.append(f"{h}:INVALID_CELL_STATUS")
    matured = any(c.get("status") == "OK" for c in horizon.values()) if not horizon_errors else None
    weight = grade.get("weight_in_market")
    exposed = weight > 0 if marked is True and finite(weight) and weight >= 0 else None
    return {"entered": entered, "marked": marked, "matured": matured,
            "weight_in_market": weight, "positive_market_exposure": exposed,
            "declared_horizons": declared, "validation_errors": errors,
            "horizon_validation_errors": horizon_errors,
            "horizon_statuses": {str(h): c.get("status") if isinstance(c, dict) else None for h, c in horizon.items()}}


def cohort_census(books: list[dict], *, asof: str, expected_count: int,
                  expected_ids_sha: str | None = None, manifest_sha: str | None = None,
                  grade_doc: dict | None = None) -> dict:
    ids = [b.get("book_id") for b in books]
    if len(books) != expected_count:
        raise ValueError("COHORT_COUNT_MISMATCH")
    require_exact(exact_join(ids, books))
    if expected_ids_sha is not None and digest(sorted(ids)) != expected_ids_sha:
        raise ValueError("COHORT_ID_PIN_MISMATCH")
    for book in books:
        if book.get("asof") != asof or book.get("schema") != "llm_portfolio/1":
            raise ValueError("WRONG_COHORT")
        if manifest_sha is not None:
            src = book.get("source", {})
            if (src.get("type") != "prospective_population1000" or
                    src.get("manifest_sha256") != manifest_sha or
                    src.get("historical_nav_inherited") is not False):
                raise ValueError("WRONG_POPULATION_MANIFEST")
    result = {"frozen": len(books), "ids_sha256": digest(sorted(ids)),
              "asof": asof, "frozen_clocks": dict(Counter(b.get("frozen_utc") for b in books)),
              "grade_join": None, "entered": None, "marked": None, "matured_books": None,
              "unknown_grade_reason": "NO_SAVED_GRADE"}
    if grade_doc is None:
        return result
    grades = grade_doc.get("grades")
    if not isinstance(grades, list):
        raise ValueError("SAVED_GRADES_REQUIRED")
    join = exact_join(ids, grades)
    result["grade_join"] = join
    if join["status"] != "EXACT":
        result["unknown_grade_reason"] = "GRADE_ID_JOIN_REFUSED"
        return result
    if any(g.get("asof", asof) != asof for g in grades):
        raise ValueError("WRONG_GRADE_COHORT")
    if "books" in grade_doc:
        require_exact(exact_join(ids, grade_doc["books"]))
    by_id = {g["book_id"]: g for g in grades}
    upper, created, context_errors = receipt_bounds(grade_doc)
    joined = []
    horizon_counts = Counter()
    for book in books:
        g = by_id[book["book_id"]]
        td = g.get("to_date") if isinstance(g.get("to_date"), dict) else {}
        validated = validate_saved_grade(book, g, upper, created, context_errors)
        for h, status in validated["horizon_statuses"].items():
            horizon_counts[h + ":" + str(status)] += 1
        joined.append({"book_id": book["book_id"], "policy_id": book.get("source", {}).get("policy_id"),
                       "entry_session": g.get("entry_session"), "status": g.get("status"),
                       "mark_session": td.get("as_of"), "sessions": td.get("sessions"), **validated})
    result.update(unknown_grade_reason=None,
                  entered=sum(r["entered"] for r in joined) if all(r["entered"] is not None for r in joined) else None,
                  marked=sum(r["marked"] for r in joined) if all(r["marked"] is not None for r in joined) else None,
                  known_marked=sum(r["marked"] is True for r in joined),
                  unknown_mark_count=sum(r["marked"] is None for r in joined),
                  matured_books=sum(r["matured"] for r in joined) if all(r["matured"] is not None for r in joined) else None,
                  unknown_horizon_count=sum(r["matured"] is None for r in joined),
                  positive_market_exposure=sum(r["positive_market_exposure"] for r in joined)
                      if all(r["positive_market_exposure"] is not None for r in joined) else None,
                  zero_market_exposure=sum(r["positive_market_exposure"] is False for r in joined)
                      if all(r["positive_market_exposure"] is not None for r in joined) else None,
                  unknown_market_exposure_count=sum(r["positive_market_exposure"] is None for r in joined),
                  validation_status="REFUSED_OR_PARTIAL" if any(r["validation_errors"] or r["horizon_validation_errors"] for r in joined) else "VALID_SAVED_READBACK",
                  data_upper_bound=upper.isoformat() if upper else None,
                  receipt_generated_at=created.isoformat() if created else None,
                  entry_convention="Saved benchmark session OPEN after frozen/as-of date; includes cash-only books; not broker fills or positive exposure",
                  grade_status_counts=dict(Counter(r["status"] for r in joined)),
                  entry_sessions=dict(Counter(r["entry_session"] for r in joined)),
                  mark_sessions=dict(Counter(r["mark_session"] for r in joined)),
                  horizon_status_counts=dict(horizon_counts), rows=joined)
    if result["validation_status"] != "VALID_SAVED_READBACK":
        result["unknown_grade_reason"] = "ROW_CONTRACT_VALIDATION_REFUSED_OR_PARTIAL"
    return result


def policy_census(specs: dict, books: list[dict], operation: dict) -> dict:
    policies = [s["policy_id"] for s in specs["specifications"]]
    require_exact(exact_join(policies, [{"policy_id": p} for p in policies], "policy_id"))
    frozen = [b["source"]["policy_id"] for b in books]
    # A partial population is legitimate only with one explicit state per spec.
    if len(frozen) != len(set(frozen)) or not set(frozen) <= set(policies):
        raise ValueError("DUPLICATE_OR_FOREIGN_POLICY")
    states = operation["states"]
    require_exact(exact_join(policies, [{"policy_id": p} for p in states], "policy_id"))
    waiting = sorted(set(policies) - set(frozen))
    if any(not states[p].startswith(("WAIT_", "REFUSED_")) for p in waiting):
        raise ValueError("UNFROZEN_POLICY_WITHOUT_EXPLICIT_WAIT")
    require_exact(exact_join([b["book_id"] for b in books], operation["grades"]))
    grades = {g["book_id"]: g for g in operation["grades"]}
    for book in books:
        if book["book_id"] not in grades or states[book["source"]["policy_id"]] != grades[book["book_id"]].get("status"):
            raise ValueError("POLICY_STATE_GRADE_MISMATCH")
    by_policy = {s["policy_id"]: s for s in specs["specifications"]}
    return {"specifications": len(policies), "frozen": len(frozen), "unfrozen": len(waiting),
            "frozen_control_role_counts": dict(Counter(by_policy[p]["control_role"] for p in frozen)),
            "state_counts": dict(Counter(states.values())),
            "wait_counts": dict(Counter(states[p] for p in waiting)),
            "waits": [{"policy_id": p, "state": states[p]} for p in waiting],
            "policy_to_book": {b["source"]["policy_id"]: b["book_id"] for b in books}}


def latest_document(sources: Sources, paths: object, clock: str) -> tuple:
    docs = [(p, sources.read(p)) for p in sorted(paths)]
    if not docs:
        return None, None
    def timestamp(item: tuple) -> datetime:
        value = datetime.fromisoformat(item[1][clock].replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("AWARE_RECEIPT_CLOCK_REQUIRED")
        return value
    return max(docs, key=timestamp)


def build_census(evidence_root: Path, runtime_root: Path, pointer: Path) -> dict:
    sources = Sources()
    evidence_root, runtime_root = Path(evidence_root), Path(runtime_root)
    old_dir = evidence_root / "oct14-continuation-20261014/local-branching/2026-10-14"
    pop_dir = evidence_root / "oct15-clean-recovery-20261015/branching-population-1000-r1"
    old_path, new_path = old_dir / "books.jsonl", pop_dir / "runtime/books.jsonl"
    old_books, new_books = sources.read(old_path, lines=True), sources.read(new_path, lines=True)
    freeze_path = old_dir / "freeze_receipt.json"
    freeze = sources.read(freeze_path)
    if sources.ref(old_path)["sha256"] != OLD_LEDGER_SHA or sources.ref(freeze_path)["sha256"] != OLD_RECEIPT_SHA:
        raise ValueError("ORIGINAL_COHORT_PIN_CHANGED")
    old_grade_path, old_grade = latest_document(sources, old_dir.glob("grade_*.json"), "graded_utc")
    if old_grade is not None and (old_grade.get("source_ledger_sha256") != OLD_LEDGER_SHA or
            old_grade.get("freeze_receipt_sha256") != OLD_RECEIPT_SHA or
            Path(old_grade["source_ledger"]).resolve() != old_path.resolve()):
        raise ValueError("ORIGINAL_GRADE_SOURCE_JOIN")
    old = cohort_census(old_books, asof="2026-10-14", expected_count=247,
                        expected_ids_sha=OLD_IDS_SHA, grade_doc=old_grade)
    old.update(ledger_ref=sources.ref(old_path), freeze_ref=sources.ref(freeze_path),
               freeze_consumer_readback=freeze["shared_consumer_readback"],
               grade_ref=sources.ref(old_grade_path) if old_grade_path else None,
               controls=sum(b["kind"] == "control" for b in old_books))
    config = sources.read(pop_dir / "OPERATING_CONFIG.json")
    specs = sources.read(config["specifications_path"])
    if digest(specs) != MANIFEST_SHA or config["manifest_sha256"] != MANIFEST_SHA:
        raise ValueError("FROZEN_MANIFEST_PIN_CHANGED")
    declaration = sources.read(pop_dir / "runtime/declaration.json")
    if declaration["manifest_sha256"] != MANIFEST_SHA or declaration["inherited_nav"] is not False:
        raise ValueError("WRONG_DECLARATION")
    if any(b["source"].get("declared_at") != declaration["declared_at"] for b in new_books):
        raise ValueError("BOOK_DECLARATION_CLOCK_JOIN")
    operation_path, operation = latest_document(sources, (pop_dir / "runtime").glob("operation_*.json"), "observed_at")
    if operation is None or operation.get("schema") != "shared_virtual_population_consumer/1" or Path(operation["ledger"]).resolve() != new_path.resolve():
        raise ValueError("EXACT_POPULATION_CONSUMER_REQUIRED")
    new = cohort_census(new_books, asof="2026-10-15", expected_count=886,
                        manifest_sha=MANIFEST_SHA, grade_doc=operation)
    new.update(policy_census(specs, new_books, operation), ledger_ref=sources.ref(new_path),
               consumer_ref=sources.ref(operation_path), declared_at=declaration["declared_at"],
               closed_session=operation["closed_session"], activation=operation["activation"],
               registry_remote_verification=operation["registry_remote_verification"])
    historical = sources.read(pop_dir / "runtime/operation_20261015T181504246913Z.json")
    historical_readback = policy_census(specs, new_books, historical)
    events_path = old_dir.parent / "automation_runs.jsonl"
    events = sources.read(events_path, lines=True)
    latest_event = max(events, key=lambda r: datetime.fromisoformat(r["utc"]))
    old["latest_owner_event"] = latest_event
    new["owner_consumer_receipt_matches_latest_operation"] = Path(latest_event.get("population1000", {}).get("receipt", "")).resolve() == operation_path.resolve()
    new["owner_summary_counts_match_saved_operation"] = (
        latest_event.get("population1000", {}).get("marked") == new["marked"] and
        latest_event.get("population1000", {}).get("operating_states") == new["state_counts"])
    old["latest_owner_ledger_pin_matches"] = latest_event.get("ledger_sha256") == sources.ref(old_path)["sha256"]
    account_dir = runtime_root / "backend/data/optimus/paper_accounts"
    roi_path, roi = latest_document(sources, account_dir.glob("roi_*.json"), "generated_utc")
    consumer = {"ref": sources.ref(roi_path) if roi_path else None, "original_247": None, "oct15_886": None}
    if roi is not None:
        for label, books in (("original_247", old_books), ("oct15_886", new_books)):
            expected = {b["book_id"] for b in books}
            rows = [r for r in roi["rows"] if r.get("book_id") in expected]
            consumer[label] = exact_join(sorted(expected), rows)
            consumer[label]["meaning"] = "Saved paper_accounts ROI inclusion only; private grader consumer is separate"
    pointer_path = Path(pointer)
    # The pointer is append-heavy. Read and preserve just its authoritative top block.
    with pointer_path.open(encoding="utf-8") as handle:
        top = []
        for line in handle:
            if line.startswith("--- Earlier checkpoints"):
                break
            top.append(line)
    top_text = "".join(top)
    r5 = evidence_root / "oct15-clean-recovery-20261015/branching-dynamic-pair-carrier-r5"
    review_path = r5 / "outer-wrapper-r1/reviews/INDEPENDENT_R5_RESOURCE_ROLE_SOURCE_REVIEW.json"
    review = sources.read(review_path)
    gates = [{"gate": label, "path": str(r5 / relative)} for label, relative in (
        ("native.qualify", "native_carrier.py"), ("shim", "outer-wrapper-r1/carrier_shim.py"),
        ("outer bootstrap/guard", "outer-wrapper-r1/outer_bootstrap.py"),
        ("PowerShell", "outer-wrapper-r1/invoke_preheld.ps1"))]
    for gate in gates:
        gate["sha256"] = hashlib.sha256(Path(gate["path"]).read_bytes()).hexdigest()
    sources.verify_unchanged()
    return {"schema": "beta_v2_population_census/1", "observed_at": datetime.now(timezone.utc).isoformat(),
            "validation_contract": "SAVED_GRADE_DATES_DECLARED_HORIZONS_V2",
            "mode": "READ_SAVED_EVIDENCE_ONLY", "operational_writes": 0,
            "grading_calls": 0, "network_calls": 0, "original_247": old, "oct15_population": new,
            "oct15_1815_historical": {k: historical_readback[k] for k in ("specifications", "frozen", "unfrozen", "state_counts", "wait_counts")},
            "paper_accounts_consumer": consumer,
            "continuation": {"pointer": str(pointer_path), "top_block_sha256": hashlib.sha256(top_text.encode()).hexdigest(),
                             "top_block": top_text, "four_gates": gates, "r5_review_ref": sources.ref(review_path),
                             "financial_retry_authorized_by_r5_review": review["financial_retry_authorized"],
                             "status": "DATED_POINTER_REQUIRES_R6_SAME_PACKAGE_READONLY_CALIBRATION; NO_OPERATION_PERFORMED"},
            "limitations": ["Saved grade readback, not independent price revaluation or runtime execution certification",
                            "Counts of zero mean observed empty ID joins or saved horizon states, not absent evidence",
                            "R6 status is from the dated pointer and R5 review, not a scan of later engineering work"],
            "source_refs": list(sources.refs.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--pointer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_census(args.evidence_root, args.runtime_root, args.pointer)
    # Exclusive creation protects prior receipts; never opens an operational ledger for writing.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "original_marked": result["original_247"]["marked"],
                      "oct15_marked": result["oct15_population"]["marked"]}))


if __name__ == "__main__":
    main()
