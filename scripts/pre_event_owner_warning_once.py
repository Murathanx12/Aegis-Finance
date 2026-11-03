"""One saved Finnhub calendar receipt to a sanitized PC-PAPER owner preview.

Invoke with python -m scripts.pre_event_owner_warning_once. No provider access.
--send additionally needs an independently authored exact-source review JSON:
{schema: pre-event-warning-review/1, independent_exact_source_review: true,
 reviewer: nonempty string, sha256: {each SOURCE_PATHS entry: exact byte hash}}.
There is no bundled review or automatic enrollment.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from decimal import InvalidOperation
import json
from pathlib import Path
import re
import time

from backend.services import earnings_calendar_capture as capture
from backend.services import owner_event_warning as private_journal
from backend.services import pre_event_delivery as delivery
from backend.services import pre_event_owner_warning as warning
from scripts import owner_event_warning as selector

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "backend/services/saved_earnings_calendar_input.py",
    "backend/services/earnings_calendar_capture.py",
    "backend/services/pre_event_owner_warning.py",
    "backend/services/pre_event_delivery.py",
    "backend/services/owner_event_warning.py",
    "backend/services/telegram_bridge.py",
    "scripts/owner_event_warning.py",
    "scripts/pre_event_owner_warning_once.py",
)
SGT = timezone(timedelta(hours=8))


class Refused(ValueError):
    """Only fixed refusal codes may leave the runner."""


def _check_window(now: datetime) -> int:
    local = now.astimezone(SGT)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    start = 16 * 3600 + 30 * 60
    end = 17 * 3600 + 5 * 60
    if start <= seconds < end:
        raise Refused("IIF_WINDOW_DEFER")
    return start - seconds if seconds < start else 24 * 3600 + start - seconds


def _review(path: Path) -> None:
    document = private_journal._object(selector.frozen_read(path).decode("utf-8"))
    hashes = {name: selector.sha(selector.frozen_read(ROOT / name))
              for name in SOURCE_PATHS}
    if (set(document) != {"schema", "independent_exact_source_review", "reviewer", "sha256"}
            or document["schema"] != "pre-event-warning-review/1"
            or document["independent_exact_source_review"] is not True
            or not isinstance(document["reviewer"], str)
            or not document["reviewer"].strip()
            or document["sha256"] != hashes):
        raise Refused("INDEPENDENT_EXACT_SOURCE_REVIEW_REQUIRED")


def _receipt(path: Path) -> tuple[dict, bytes, bytes]:
    if capture._FINAL_NAME.fullmatch(path.name) is None:
        raise Refused("PUBLISHED_RECEIPT_REQUIRED")
    identity = capture._private_identity(path.parent)
    encoded = selector.frozen_read(path)
    if len(encoded) > capture._MAX_RECEIPT_BYTES:
        raise Refused("RECEIPT_TOO_LARGE")
    receipt = private_journal._object(encoded.decode("utf-8"))
    response = base64.b64decode(receipt["response_bytes_b64"], validate=True)
    if (capture._private_identity(path.parent) != identity
            or not capture._valid_receipt(receipt, response)):
        raise Refused("PUBLISHED_RECEIPT_INVALID")
    return receipt, response, encoded


def _preview(artifact: dict, delivery_state: str) -> dict:
    keys = ("status", "reason", "ticker", "at_utc", "observed_utc",
            "event_date_et", "event_time_status", "snapshot_as_of_utc",
            "saved_exposure_usd", "equity_usd", "exposure_weight",
            "conditional_loss_usd", "forecast_status", "paper_decision",
            "event_id", "decision_id", "input_id")
    return {**{key: artifact[key] for key in keys if key in artifact},
            "delivery": delivery_state}


def run(*, receipt_path: Path, ledger_dir: Path, expected_account_sha256: str,
        journal_dir: Path, send: bool = False, review: Path | None = None,
        now: datetime | None = None) -> tuple[int, dict]:
    """Preview by default. The CLI never accepts a caller-provided clock."""
    actual_now = now or datetime.now(timezone.utc)
    started = time.monotonic()

    def check() -> None:
        if time.monotonic() - started > 5:
            raise Refused("PRE_SEND_BUDGET_EXCEEDED")
        _check_window(now or datetime.now(timezone.utc))

    try:
        if actual_now.utcoffset() != timedelta(0):
            raise Refused("UTC_REQUIRED")
        if (not isinstance(expected_account_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_account_sha256) is None):
            raise Refused("ACCOUNT_PIN_REQUIRED")
        if send:
            check()
        private_journal._journal_identity(journal_dir)
        receipt, response, encoded = _receipt(Path(receipt_path))
        if send:
            check()
        packet = capture.evaluate_saved_capture(
            receipt, response, cutoff_utc=receipt["cutoff_utc"])
        if packet.get("status") != "EVIDENCE_ONLY":
            raise Refused("CALENDAR_REPLAY_REFUSED")
        if send:
            check()
        snapshot = selector.select_snapshot(
            ledger_dir, now=actual_now,
            expected_account_sha256=expected_account_sha256,
            check=check if send else lambda: None)
        artifact = warning.build_pre_event_warning_bytes(
            packet=packet, response_bytes=response, snapshot_bytes=snapshot,
            expected_snapshot_sha256=selector.sha(snapshot),
            expected_account_sha256=expected_account_sha256,
            cutoff_utc=receipt["cutoff_utc"], now_utc=actual_now.isoformat())
        if artifact["status"] != "PROVISIONAL":
            return 2, _preview(artifact, "NOT_SENT")
        if not send:
            return 0, _preview(artifact, "PREVIEW")
        if review is None:
            raise Refused("INDEPENDENT_EXACT_SOURCE_REVIEW_REQUIRED")
        check()
        _review(review)
        check()
        # Prevent a changed receipt from being used after review/preflight.
        if selector.frozen_read(receipt_path) != encoded:
            raise Refused("RECEIPT_CHANGED")
        from backend.services import telegram_bridge

        owner = telegram_bridge.owner_chat_id()
        if not isinstance(owner, str) or re.fullmatch(r"[1-9][0-9]*", owner) is None:
            raise Refused("PRIVATE_NUMERIC_OWNER_REQUIRED")
        check()
        _review(review)
        check()
        until = time.time() + min(30, _check_window(now or datetime.now(timezone.utc)))

        def sender(text: str, *, tag: str) -> dict:
            check()
            return telegram_bridge.send_owner_once(
                text, tag=tag, expected_owner=owner, until=until)

        state = delivery.deliver(artifact, journal_dir=journal_dir, sender=sender)
        result = _preview(artifact, state)
        return (0 if state in ("SENT", "ALREADY_SENT") else 2), result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError,
            InvalidOperation, OverflowError, RecursionError):
        return 2, {"status": "REFUSED", "reason": "RUN_REFUSED_REVIEW_INPUTS_AND_GATES",
                   "delivery": "NOT_SENT"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published-receipt", type=Path, required=True)
    parser.add_argument("--pc-paper-ledger", type=Path, required=True)
    parser.add_argument("--expected-account-sha256", required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args(argv)
    code, result = run(receipt_path=args.published_receipt,
                       ledger_dir=args.pc_paper_ledger,
                       expected_account_sha256=args.expected_account_sha256,
                       journal_dir=args.journal_dir, send=args.send,
                       review=args.review)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
