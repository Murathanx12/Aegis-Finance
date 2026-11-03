"""Private, single-attempt journal for reviewed saved-calendar owner warnings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from backend.services import owner_event_warning as journal


def message(artifact: dict) -> str:
    """Render only fields produced by the pure warning builder."""
    if (artifact.get("schema") != "pre-event-owner-warning/1"
            or artifact.get("status") != "PROVISIONAL"
            or not re.fullmatch(r"[A-Z]{1,5}(?:[.-][A-Z])?", artifact.get("ticker", ""))
            or any(not isinstance(artifact.get(key), str)
                   or not re.fullmatch(r"[0-9a-f]{64}", artifact[key])
                   for key in ("event_id", "input_id", "receipt_id",
                               "capture_input_id", "receipt_sha256"))):
        raise ValueError("PROVISIONAL_WARNING_REQUIRED")
    return (
        f"PROVISIONAL PC-PAPER pre-event warning: {artifact['ticker']}\n"
        f"Finnhub earnings calendar OBSERVED {artifact['observed_utc']}; "
        f"scheduled ET date {artifact['event_date_et']}; event time UNKNOWN.\n"
        f"Saved PC-PAPER exposure at {artifact['snapshot_as_of_utc']}: "
        f"USD {artifact['saved_exposure_usd']} of equity USD {artifact['equity_usd']} "
        f"(weight {artifact['exposure_weight']}).\n"
        f"Conditional loss if held name declines 5%: USD "
        f"{artifact['conditional_loss_usd']['5_percent_decline']}; "
        f"10%: USD {artifact['conditional_loss_usd']['10_percent_decline']}.\n"
        "Saved receipt only; provider authenticity unverified. "
        "No calibrated forecast, price direction, probability, or new allocation. "
        "HOLD_EXISTING / NO_NEW_BET / REVIEW_NEW_EVIDENCE (paper only).\n"
        f"Event ID {artifact['event_id']}\n"
        f"Sealed receipt ID {artifact['receipt_id']}; "
        f"capture input ID {artifact['capture_input_id']}; "
        f"receipt file SHA256 {artifact['receipt_sha256']}; "
        f"decision replay input ID {artifact['input_id']}"
    )


def _regular(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400


def _confirmed(path: Path, result_path: Path, pending: Path, event_id: str) -> dict | None:
    try:
        if os.path.lexists(pending) or not _regular(path) or not _regular(result_path):
            return None
        if path.stat().st_size > 16_384 or result_path.stat().st_size > 4_096:
            return None
        record = journal._object(path.read_text(encoding="utf-8"))
        result = journal._object(result_path.read_text(encoding="utf-8"))
        artifact = record["artifact"]
        tag = "pre-event-warning:" + event_id
        valid = (
            record["state"] == "SENDING"
            and artifact["event_id"] == event_id
            and record["artifact_sha256"] == journal._digest(artifact)
            and record["tag_sha256"] == journal._digest({"tag": tag})
            and record["text_sha256"] == journal._hash(message(artifact))
            and result["state"] == "SENT"
            and result["at"] == artifact["at_utc"]
            and journal._valid_ack(result["ack"], record)
        )
        return artifact if valid else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def deliver(artifact: dict, *, journal_dir: Path, sender) -> tuple[str, dict]:
    """Durably reserve an event before one transport call; never retry ambiguity."""
    text = message(artifact)
    event_id = artifact["event_id"]
    tag = "pre-event-warning:" + event_id
    record = {
        "state": "SENDING", "artifact": artifact,
        "artifact_sha256": journal._digest(artifact),
        "tag_sha256": journal._digest({"tag": tag}),
        "text_sha256": journal._hash(text),
    }
    directory = Path(journal_dir)
    try:
        identity = journal._journal_identity(directory)
    except (OSError, ValueError):
        return "REFUSED_JOURNAL_UNQUALIFIED", artifact
    path = directory / (event_id + ".json")
    result_path = path.with_suffix(".result.json")
    pending = path.with_suffix(".result.pending.json")
    if any(os.path.lexists(candidate) for candidate in (path, result_path, pending)):
        acknowledged = _confirmed(path, result_path, pending, event_id)
        return (("ALREADY_SENT", acknowledged) if acknowledged is not None
                else ("DUPLICATE_RECONCILE_REQUIRED", artifact))
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return "DUPLICATE_RECONCILE_REQUIRED", artifact
    except OSError:
        return "UNKNOWN_RECONCILE_REQUIRED", artifact
    try:
        if journal._journal_identity(directory) != identity:
            return "UNKNOWN_RECONCILE_REQUIRED", artifact
    except (OSError, ValueError):
        return "UNKNOWN_RECONCILE_REQUIRED", artifact
    state = "UNKNOWN_RECONCILE_REQUIRED"
    ack = None
    try:
        response = sender(text, tag=tag)
        if journal._valid_ack(response, record):
            state = "SENT"
            ack = {key: response[key] for key in (*journal._ACK_HASH_KEYS,
                                                 "delivery_binding_sha256")}
            ack.update(state="SENT", messages=1)
    except Exception:
        pass  # A transport exception can follow successful native delivery.
    try:
        with pending.open("x", encoding="utf-8") as stream:
            json.dump({"state": state, "at": artifact["at_utc"], "ack": ack},
                      stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, result_path)
        pending.unlink()
    except (OSError, TypeError, ValueError):
        state = "UNKNOWN_RECONCILE_REQUIRED"
    return state, artifact
