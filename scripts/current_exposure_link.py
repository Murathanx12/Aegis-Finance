"""E5 local current-review linker. Explicit pins only; no production caller.

PRODUCT_EXPERIMENT. Hashes bind bytes, never authorship or historical dates.
The sole admitted profile is saved META Class A; no E2/E3 authority is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from backend.services import owner_decision_bridge as bridge
from backend.services import owner_decision_view as view

MAX_BYTES = 8 * 1024 * 1024
CANDIDATE = "CURRENT_HELD_ASSET_CANDIDATE_CALLER_ATTESTED"


@dataclass(frozen=True)
class Pin:
    path: Path
    sha256: str


def refuse(code: str) -> None:
    raise view.ViewRefused(code)


def clock(value: Any) -> datetime:
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        refuse("INVALID_CLOCK")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        refuse("INVALID_CLOCK")


def exact(value: Any, keys: str) -> dict:
    if type(value) is not dict or set(value) != set(keys.split()):
        refuse("INVALID_FIELDS")
    return value


def read(pin: Pin, cap: int = MAX_BYTES) -> bytes:
    if type(pin) is not Pin:
        refuse("INVALID_PIN")
    return view._read_pinned(pin.path, pin.sha256, cap)


def parse(data: bytes) -> dict:
    try:
        result = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=view._unique_object,
            parse_constant=lambda _: refuse("INVALID_JSON"),
        )
    except (UnicodeError, ValueError, RecursionError):
        refuse("INVALID_JSON")
    if type(result) is not dict:
        refuse("INVALID_JSON")
    return result


def norm(value: Any) -> str:
    if type(value) is not str or not value or len(value) > 150:
        refuse("INVALID_NAME")
    return " ".join(re.sub(r"[^a-z0-9 ]", "", value.casefold()).split())


def _build_link(
    *,
    receipt: Pin,
    selected_event_id: str,
    corpus_root: Path,
    locator: bridge.RowLocator,
    page: Pin,
    subject: Pin,
    mapping: Pin,
    mapping_inputs: dict[str, Pin],
    broker: Pin | None,
    history: Pin | None = None,
    cutoff_utc: str | None = None,
) -> dict:
    """Read exactly one selected E4 chain; return a sanitized pinnable receipt.

    review_at is captured here, never accepted from a manifest. cutoff_utc is
    only an additional historical-view filter and cannot backdate invocation.
    E1/mapper selections are caller attestations tied to externally pinned files.
    """
    review_at = datetime.now(timezone.utc)
    cutoff = clock(cutoff_utc) if cutoff_utc else review_at
    if cutoff > review_at:
        refuse("FUTURE_CUTOFF")
    clocks = []

    def known(label: str, value: str, *, bound: datetime = review_at) -> datetime:
        instant = clock(value)
        if instant > bound:
            refuse("WITNESS_AFTER_REVIEW")
        clocks.append({"witness": label, "at_utc": value, "authority": "SAVED_CALLER_CLAIM"})
        return instant

    e4 = bridge.build_selected_event_view(
        receipt_path=receipt.path,
        receipt_sha256=receipt.sha256,
        selected_event_id=selected_event_id,
        corpus_root=corpus_root,
        locators=[locator],
    )
    e2 = view._parse_receipt(read(receipt), require_one_group=False)
    group = next(g for g in e2["groups"] if g["event_id"] == selected_event_id)
    (source,) = group["sources"]
    known("e2_review", e2["review_time_utc"])
    known("e2_source_cutoff", e2["source_cutoff_utc"])
    first = known("source_first_seen", source["first_seen_utc"])
    version = known("source_version", source["version_seen_utc"])
    if source["published_utc"]:
        known("source_published_publisher_claim", source["published_utc"])
    if max(first, version) > cutoff:
        refuse("SOURCE_AFTER_CUTOFF")
    s = exact(
        parse(read(subject)),
        "schema source_sha256 raw_line_sha256 page_sha256 issuer_cik issuer_name qualification observed_at_utc rights",
    )
    if (
        s["schema"] != "e5-subject-assertion/1"
        or s["rights"] != "LOCAL_METADATA_ONLY"
        or s["source_sha256"] != source["source_sha256"]
        or s["raw_line_sha256"] != source["proof_witness_sha256"]
        or s["page_sha256"] != page.sha256
    ):
        refuse("SUBJECT_SOURCE_BINDING")
    subject_at = known("subject_assertion", s["observed_at_utc"])
    if subject_at > cutoff:
        refuse("SUBJECT_AFTER_CUTOFF")
    # Full-subject attestation is necessary, not a tag/mention inference.
    if (
        s["qualification"] != "FULL_ISSUER_SUBJECT"
        or s["issuer_cik"] != "1326801"
        or norm(s["issuer_name"]) != "meta platforms inc"
    ):
        refuse("ISSUER_SUBJECT_REQUIRED")
    p = parse(read(page))
    if (
        p.get("page_kind") != "article"
        or len(str(p.get("body") or p.get("text") or "")) < 400
        or "meta" not in str(p.get("title", "")).casefold()
    ):
        refuse("FULL_PAGE_REQUIRED")
    # Bind full-page identity to the exact metadata row, never a sibling page.
    raw = read(Pin(corpus_root / locator.relative_corpus_path, locator.container_sha256))
    row = parse(raw.splitlines(keepends=True)[locator.line_number - 1].rstrip(b"\r\n"))
    if not row.get("url") or row.get("url") != p.get("url"):
        refuse("PAGE_IDENTITY_MISMATCH")
    page_at = known("full_page_first_seen", p.get("first_seen_utc"))
    if page_at > cutoff:
        refuse("SOURCE_AFTER_CUTOFF")
    m = exact(
        parse(read(mapping)),
        "schema observed_at_utc provenance_mode input_sha256 candidates issuer_candidates rights",
    )
    if (
        m["schema"] != "e5-mapping-selection/1"
        or m["rights"] != "LOCAL_METADATA_ONLY"
        or m["provenance_mode"] != "CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE"
    ):
        refuse("MAPPING_PROVENANCE_REQUIRED")
    map_at = known("mapping_observed", m["observed_at_utc"])
    if map_at > cutoff:
        refuse("MAPPING_AFTER_CUTOFF")
    names = {"master", "master_meta", "proxy", "proxy_receipt"}
    if (
        set(mapping_inputs) != names
        or type(m["input_sha256"]) is not dict
        or set(m["input_sha256"]) != names
    ):
        refuse("MAPPING_INPUT_SET")
    inputs = {}
    for name in sorted(names):
        if m["input_sha256"][name] != mapping_inputs[name].sha256:
            refuse("MAPPING_PIN_MISMATCH")
        inputs[name] = read(mapping_inputs[name])
    expected_issuer = [
        {
            "symbol": "META",
            "identity_level": "ISSUER_CANDIDATE_ONLY",
            "listing_candidates": [
                {
                    "market": "US",
                    "exchange": "NMS",
                    "symbol": "META",
                    "membership": "UNCONFIRMED_MEMBERSHIP",
                    "listing_validity": "UNKNOWN",
                }
            ],
        }
    ]
    if m["issuer_candidates"] != expected_issuer:
        refuse("MAPPER_CANDIDATE_COLLISION")
    candidates = m["candidates"]
    if type(candidates) is not list or len(candidates) != 1:
        refuse("AMBIGUOUS_ISSUER")
    c = exact(candidates[0], "cik symbol issuer_name class venue asset_class conflicts")
    if c != {
        "cik": "1326801",
        "symbol": "META",
        "issuer_name": "Meta Platforms, Inc.",
        "class": "Class A Common Stock",
        "venue": "NASDAQ",
        "asset_class": "us_equity",
        "conflicts": [],
    }:
        refuse("IDENTITY_COLLISION")
    master = parse(inputs["master"])
    matches = [
        r
        for r in master.values()
        if type(r) is dict and (str(r.get("cik_str")) == "1326801" or r.get("ticker") == "META")
    ]
    if (
        len(matches) != 1
        or str(matches[0].get("cik_str")) != "1326801"
        or matches[0].get("ticker") != "META"
        or norm(matches[0].get("title")) != "meta platforms inc"
    ):
        refuse("MASTER_COLLISION")
    # Read the pinned proxy bytes in memory, not a path reopened by pandas.
    import io
    import pandas as pd

    try:
        proxy = pd.read_parquet(
            io.BytesIO(inputs["proxy"]), columns=["market", "symbol", "exchange"]
        )
        rows = proxy.loc[proxy["symbol"].isin(["META", "US:META"])].to_dict("records")
    except Exception:
        refuse("INVALID_PROXY")
    if len(rows) != 1 or rows[0]["market"] != "US" or rows[0]["exchange"] != "NMS":
        refuse("PROXY_COLLISION")
    meta, proxy_receipt = parse(inputs["master_meta"]), parse(inputs["proxy_receipt"])
    if meta.get("n_entries") != len(master) or proxy_receipt.get("rows_after") != len(proxy):
        refuse("MAPPING_ROW_COUNT")
    status = "SYMBOL_OVERLAP_ONLY"
    history_sha = None
    if broker is None:
        if history is None:
            refuse("HOLDING_WITNESS_REQUIRED")
        h = parse(read(history, 65536))
        history_at = known("ticker_history_snapshot_claim", h.get("t"))
        if history_at > cutoff:
            refuse("HISTORY_AFTER_CUTOFF")
        positions = h.get("positions")
        if type(positions) is not list or len(positions) > 1000:
            refuse("INVALID_HISTORY")
        matches = [r for r in positions if type(r) is dict and r.get("symbol") == "META"]
        from decimal import Decimal, InvalidOperation

        try:
            quantity = Decimal(str(matches[0]["qty"])) if len(matches) == 1 else Decimal("NaN")
            if not quantity.is_finite() or quantity == 0:
                refuse("INVALID_HISTORY_POSITION")
        except (InvalidOperation, KeyError):
            refuse("INVALID_HISTORY_POSITION")
        history_sha = history.sha256
    asset_hash = None
    broker_hashes = None
    if broker is not None:
        b = exact(
            parse(read(broker, 65536)),
            "schema observed_from_utc observed_until_utc host positions_count positions_response_sha256 assets_response_sha256 selected limits",
        )
        if (
            b["schema"] != "aegis_current_paper_asset_witness/v1"
            or b["host"] != "paper-api.alpaca.markets"
            or type(b["positions_count"]) is not int
            or b["positions_count"] < 1
            or type(b["limits"]) is not list
            or any(type(v) is not str for v in b["limits"])
        ):
            refuse("INVALID_BROKER_WITNESS")
        start = known("broker_common_observed_from", b["observed_from_utc"])
        end = known("broker_common_observed_until", b["observed_until_utc"])
        if start > end or (end - start).total_seconds() > 60:
            refuse("INVALID_BROKER_INTERVAL")
        if (
            type(b["selected"]) is not dict
            or not 1 <= len(b["selected"]) <= 3
            or not set(b["selected"]) <= {"META", "TGT", "XYZ"}
            or set(b["assets_response_sha256"]) != set(b["selected"])
        ):
            refuse("INVALID_BROKER_SELECTION")
        for symbol, a in b["selected"].items():
            exact(
                a,
                "position_present_nonzero position_asset_id asset_id name exchange asset_class status",
            )
            view._hash(b["assets_response_sha256"][symbol])
        a = b["selected"].get("META")
        if a is None:
            refuse("ASSET_NOT_SELECTED")
        if (
            a["position_present_nonzero"] is not True
            or a["status"] != "active"
            or a["exchange"] != "NASDAQ"
            or a["asset_class"] != "us_equity"
            or norm(a["name"]) != "meta platforms inc class a common stock"
        ):
            refuse("ASSET_CONCORDANCE")
        if (
            type(a["asset_id"]) is not str
            or not re.fullmatch(r"[a-zA-Z0-9-]{8,80}", a["asset_id"])
            or a["asset_id"] != a["position_asset_id"]
        ):
            refuse("ASSET_ID_MISMATCH")
        asset_hash = hashlib.sha256(a["asset_id"].encode()).hexdigest()
        broker_hashes = {
            "receipt": broker.sha256,
            "positions_response": view._hash(b["positions_response_sha256"]),
            "asset_response": b["assets_response_sha256"]["META"],
        }
        status = "HOLDINGS_AFTER_CUTOFF" if end > cutoff else CANDIDATE
    out = {
        "schema": "current_exposure_link/1",
        "status": status,
        "scope": "CURRENT_BROKER_OBSERVATION_ONLY",
        "review_at_utc": review_at.isoformat(),
        "view_cutoff_utc": cutoff.isoformat(),
        "event_id": selected_event_id,
        "source_id": source["source_id"],
        "issuer_cik": "1326801",
        "symbol": "META",
        "e4_view_id": e4["view_id"],
        "e2_receipt_sha256": receipt.sha256,
        "source_sha256": source["source_sha256"],
        "raw_line_sha256": source["proof_witness_sha256"],
        "page_sha256": page.sha256,
        "subject_assertion_sha256": subject.sha256,
        "mapping_selection_sha256": mapping.sha256,
        "mapping_input_sha256": m["input_sha256"],
        "history_sha256": history_sha,
        "mapping_vintage": m["provenance_mode"],
        "broker_hashes": broker_hashes,
        "asset_id_sha256": asset_hash,
        "reported_nonzero": status == CANDIDATE,
        "evidence_clocks": clocks,
        "asset_observed_from_utc": "UNKNOWN",
        "asset_observed_until_utc": "UNKNOWN",
        "position_observed_from_utc": "UNKNOWN",
        "position_observed_until_utc": "UNKNOWN",
        "position_as_of_utc": "UNKNOWN",
        "issuer_security_basis": "NAME_SYMBOL_CLASS_VENUE_INFERENCE",
        "broker_origin": "UNVERIFIED_SAVED_RECEIPT",
        "event_time_holding": "UNKNOWN",
        "PIT_security": "UNVERIFIED",
        "owner_decision": "UNOBSERVED",
        "delivery": "NOT_ATTEMPTED",
        "forecast": "NONE",
        "portfolio_action": "NONE",
        "E2_direct_issuer_authority": False,
        "E3_warning_authority": False,
        "relation_chain": [
            "FULL_ISSUER_SUBJECT_CALLER_ATTESTED",
            "CURRENT_ISSUER_CANDIDATE",
            "INFERRED_CLASS_VENUE_ASSET",
            "SAME_ID_NONZERO_POSITION",
        ]
        if status == CANDIDATE
        else [],
        "unknowns": [
            "BROKER_ORIGIN",
            "INDEPENDENT_ISSUER_CLASS_VENUE_BINDING",
            "EVENT_TIME_CONTINUITY",
            "LISTING_VALIDITY",
            "PROXY_MEMBERSHIP",
        ],
        "alternatives": [],
        "rights": {
            "source": "LOCAL_METADATA_ONLY",
            "mapping": "PUBLIC_METADATA_WITH_UNCONFIRMED_PROXY",
            "broker": "PRIVATE_HASH_AND_BOOLEAN_ONLY",
        },
    }
    out["receipt_id"] = view._digest(
        json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    )
    return out


def _write_receipt(result: dict, *, evidence_dir: Path, filename: str) -> Path:
    """Exclusive append-only local receipt; directory must already exist externally.

    No default output and no mkdir; operator chooses a dedicated evidence dir.
    Reject repo directories (including worktrees), redirects and private payloads
    by accepting only receipts returned by build_link with intact digest.
    """
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}\.json", filename):
        refuse("INVALID_OUTPUT_NAME")
    if not evidence_dir.is_absolute() or evidence_dir.drive.startswith("\\\\"):
        refuse("INVALID_OUTPUT_DIR")
    for p in (evidence_dir, *evidence_dir.parents):
        info = p.lstat()
        if (
            p.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400
            or (p / ".git").exists()
        ):
            refuse("INVALID_OUTPUT_DIR")
    allowed = set(
        "schema status scope review_at_utc view_cutoff_utc event_id source_id issuer_cik symbol e4_view_id e2_receipt_sha256 source_sha256 raw_line_sha256 page_sha256 subject_assertion_sha256 mapping_selection_sha256 mapping_input_sha256 history_sha256 mapping_vintage broker_hashes asset_id_sha256 reported_nonzero evidence_clocks asset_observed_from_utc asset_observed_until_utc position_observed_from_utc position_observed_until_utc position_as_of_utc issuer_security_basis broker_origin event_time_holding PIT_security owner_decision delivery forecast portfolio_action E2_direct_issuer_authority E3_warning_authority relation_chain unknowns alternatives rights receipt_id".split()
    )
    if type(result) is not dict or set(result) != allowed:
        refuse("INVALID_OUTPUT_RECEIPT")
    body = {k: v for k, v in result.items() if k != "receipt_id"}
    if result.get("schema") != "current_exposure_link/1" or result.get(
        "receipt_id"
    ) != view._digest(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()):
        refuse("INVALID_OUTPUT_RECEIPT")
    target = evidence_dir / filename
    try:
        with target.open("xb") as stream:
            stream.write((json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
    except FileExistsError:
        refuse("OUTPUT_EXISTS")
    return target


def build_link(**kwargs: Any) -> dict:
    """Fail loud with sanitized codes even for malformed caller shapes."""
    try:
        return _build_link(**kwargs)
    except view.ViewRefused:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError, RecursionError):
        refuse("INVALID_LINK_INPUT")


def write_link(*, evidence_dir: Path, filename: str, **kwargs: Any) -> Path:
    """Build and exclusively write a receipt; never serialize caller output data."""
    result = build_link(**kwargs)
    return _write_receipt(result, evidence_dir=evidence_dir, filename=filename)
