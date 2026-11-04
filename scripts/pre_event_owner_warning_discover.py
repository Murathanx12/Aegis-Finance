"""Bounded saved-receipt discovery candidate; no scheduler or transport authority.

Preview is default. Send requires an independent exact-source review including
this module; protected local task adoption is separate and is not performed here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import InvalidOperation
import json
import os
from pathlib import Path
import re
import time

from scripts import pre_event_owner_warning_once as once

MAX_ENTRIES = 64
MAX_SECONDS = 5
_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError,
           InvalidOperation, OverflowError, RecursionError)


def run(*, receipt_dir: Path, ledger_dir: Path, expected_account_sha256: str,
        journal_dir: Path, send: bool = False, review: Path | None = None,
        now: datetime | None = None) -> tuple[int, dict]:
    """Select earliest eligible ET event, then newest observation, then filename.

    Rescan saved receipts each invocation; mtime and a mutable cursor confer no
    freshness. Journal existence suppresses even ambiguous previous attempts.
    Actual claim/ACK verification remains exclusively in the existing sender.
    """
    started = time.monotonic()
    rejected = duplicate = matched = 0

    def check():
        if time.monotonic() - started > MAX_SECONDS:
            raise ValueError("DISCOVERY_BUDGET_EXCEEDED")
        once._iif_deadline(now or datetime.now(timezone.utc))

    def result(status, reason):
        return {"status": status, "reason": reason, "delivery": "NOT_SENT",
                "matched": matched, "rejected": rejected, "duplicates": duplicate}

    try:
        actual = now or datetime.now(timezone.utc)
        if actual.utcoffset() != timedelta(0):
            raise ValueError("UTC_REQUIRED")
        if not isinstance(expected_account_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", expected_account_sha256):
            raise ValueError("ACCOUNT_PIN_REQUIRED")
        check()
        if send:
            if review is None:
                raise ValueError("INDEPENDENT_EXACT_SOURCE_REVIEW_REQUIRED")
            once._review(review)
            check()
        directory = Path(receipt_dir).absolute()
        journal = Path(journal_dir).absolute()
        identity = once.capture._private_identity(directory)
        journal_identity = once.private_journal._journal_identity(journal)
        paths = []
        # Count ALL entries, including temp/unrelated files, before reading any.
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, 1):
                check()
                if count > MAX_ENTRIES:
                    return 2, result("REFUSED", "DISCOVERY_ENTRY_LIMIT")
                if once.capture._FINAL_NAME.fullmatch(entry.name):
                    paths.append(directory / entry.name)
        snapshot = None
        candidates = []
        for path in sorted(paths):
            check()
            matched += 1
            try:
                receipt, response, encoded = once._receipt(path)
                packet = once.capture.evaluate_saved_capture(
                    receipt, response, cutoff_utc=actual.isoformat())
                if packet.get("status") != "EVIDENCE_ONLY":
                    raise ValueError("CALENDAR_REPLAY_REFUSED")
                if snapshot is None:
                    snapshot = once.selector.select_snapshot(
                        ledger_dir, now=actual,
                        expected_account_sha256=expected_account_sha256, check=check)
                artifact = once.warning.build_pre_event_warning_bytes(
                    packet=packet, response_bytes=response, snapshot_bytes=snapshot,
                    expected_snapshot_sha256=once.selector.sha(snapshot),
                    expected_account_sha256=expected_account_sha256,
                    cutoff_utc=actual.isoformat(), now_utc=actual.isoformat())
                if artifact["status"] != "PROVISIONAL":
                    raise ValueError("INELIGIBLE_EVENT")
                event = artifact["event_id"]
                if any(os.path.lexists(journal / (event + suffix)) for suffix in (
                        ".json", ".result.json", ".result.pending.json")):
                    duplicate += 1
                    continue
                observed = once.capture._utc_datetime(receipt["observed_utc"])
                candidates.append(((artifact["event_date_et"], -observed.timestamp(),
                                    path.name), path, encoded))
            except _ERRORS:
                rejected += 1
        check()
        if (once.capture._private_identity(directory) != identity
                or once.private_journal._journal_identity(journal) != journal_identity):
            raise ValueError("PRIVATE_ROOT_CHANGED")
        if not candidates:
            return (2 if rejected else 0), result(
                "REFUSED" if rejected else "NO_OP",
                "NO_VALID_RECEIPT" if rejected else (
                    "DUPLICATE_EVENTS_SUPPRESSED" if duplicate else "NO_SAVED_RECEIPT"))
        _, selected, encoded = min(candidates, key=lambda item: item[0])
        if once.selector.frozen_read(selected) != encoded:
            raise ValueError("RECEIPT_CHANGED")
        check()
        def selected_check():
            check()
            if (once.capture._private_identity(directory) != identity
                    or once.private_journal._journal_identity(journal) != journal_identity
                    or once.selector.frozen_read(selected) != encoded):
                raise ValueError("SELECTED_INPUT_CHANGED")
            check()

        # The callback only adds constraints: discovery's original five-second
        # budget and frozen selection remain binding throughout delegated reads.
        return once.run(receipt_path=selected, ledger_dir=ledger_dir,
                        expected_account_sha256=expected_account_sha256,
                        journal_dir=journal, now=now, send=send, review=review,
                        pre_send_check=selected_check)
    except _ERRORS:
        return 2, result("REFUSED", "DISCOVERY_REFUSED_REVIEW_INPUTS_AND_GATES")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--pc-paper-ledger", type=Path, required=True)
    parser.add_argument("--expected-account-sha256", required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args(argv)
    if args.send and args.review is None:
        parser.error("--send requires --review (independent exact-source review)")
    code, output = run(receipt_dir=args.receipt_dir, ledger_dir=args.pc_paper_ledger,
                       expected_account_sha256=args.expected_account_sha256,
                       journal_dir=args.journal_dir, send=args.send, review=args.review)
    print(json.dumps(output, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
