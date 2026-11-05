"""Small, local-only evidence sample after a paid world-digest budget refusal.

This intentionally cannot certify complete intake or a held-security edge.
No collector, provider, model, portfolio, owner delivery, or database is called.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from itertools import islice
import json
import math
from pathlib import Path

from backend.services import provisional_event_review as P
from backend.services import world_digest as WD


MAX_FILES = 48
MAX_DIR_ENTRIES = 512
MAX_FILE_BYTES = 2_097_152
MAX_SCAN_BYTES = 8_388_608
MAX_LINES = 1_024
MAX_SOURCES = 64
SOURCES = ("dj_reader_barrons", "dj_reader_wsj", "sec_edgar_8k_ex99_body",
           "dj_reader_marketwatch", "google_news_rss_en_gb")


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return clock.astimezone(timezone.utc) if clock.tzinfo is not None else None


def _files(root: Path, days: list[str]) -> list[Path]:
    base = root / "news_corpus"
    paths = [base / source / f"{day}.jsonl" for source in SOURCES for day in days]
    # The bounded full-page sample covers reader articles without enumerating
    # every page or silently calling the full collector.
    for publisher in ("marketwatch", "wsj"):
        for day in days:
            folder = base / "dowjones" / publisher / day
            if folder.is_dir() and not folder.is_symlink():
                entries = list(islice(folder.glob("*.json"), MAX_DIR_ENTRIES + 1))
                if len(entries) > MAX_DIR_ENTRIES:
                    raise ValueError("DIRECTORY_CAP")
                paths.extend(sorted(entries)[:4])
    return paths


def _event_key(identity: str) -> str:
    # One source identity, one provisional event. No semantic grouping from a
    # body, sidebar or shared keyword without an independently reviewed edge.
    return "event:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]


def build_sample(*, root: Path, review_time: datetime, cutoff: datetime,
                 hours: float) -> tuple[list[P.SourceItem], str]:
    """Return an explicitly partial, byte-bounded source sample and status."""
    if (not isinstance(root, Path) or not root.is_absolute() or root.is_symlink()
            or review_time.tzinfo is None or cutoff.tzinfo is None or review_time < cutoff
            or not math.isfinite(hours) or not 0 < hours <= 36):
        return [], "INVALID_SAMPLE_WINDOW"
    since = cutoff - timedelta(hours=hours)
    days = [(since + timedelta(days=n)).date().isoformat()
            for n in range((cutoff - since).days + 2)]
    try:
        paths = _files(root, days)
    except ValueError:
        return [], "DIRECTORY_CAP"
    if len(paths) > MAX_FILES:
        return [], "FILE_CAP"
    files = []
    total = 0
    for path in paths:
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            return [], "UNSAFE_SOURCE_PATH"
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_SCAN_BYTES:
            return [], "SOURCE_BYTE_CAP"
        files.append(path)
    if not files:
        return [], "NO_LOCAL_SOURCE"
    candidates: list[tuple[int, P.SourceItem]] = []
    lines = 0
    seen: set[tuple[str, str]] = set()
    capped = False
    for path in files:
        with path.open("rb") as stream:
            raw_rows = stream if path.suffix == ".jsonl" else (stream.read(),)
            for raw in raw_rows:
                lines += 1
                if lines > MAX_LINES:
                    capped = True
                    break
                payload = raw.rstrip(b"\r\n") if path.suffix == ".jsonl" else raw
                if not payload or len(payload) > P.MAX_SOURCE_BYTES:
                    continue
                try:
                    row = json.loads(payload)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(row, dict) or str(row.get("page_kind") or "").startswith("stock"):
                    continue
                first = _utc(row.get("first_seen_utc"))
                published_raw = row.get("published_utc")
                published = _utc(published_raw) if published_raw else None
                if (first is None or not since <= first <= cutoff
                        or (published_raw and published is None)
                        or (published and published > first)):
                    continue
                title = str(row.get("title") or "")
                body = str(row.get("body") or row.get("text") or "")
                if len(title) < 12 or (path.suffix == ".json" and len(body) < 400):
                    continue
                url = str(row.get("url") or "")
                identity = WD.norm_url(url) or str(row.get("raw_id") or "")
                if not identity:
                    continue
                source_key = "source:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]
                sha = hashlib.sha256(payload).hexdigest()
                if (source_key, sha) in seen:
                    continue
                seen.add((source_key, sha))
                kind = ("FILING" if path.parent.name.startswith("sec_edgar_") else
                        "ARTICLE" if len(body) >= 400 else "REFERENCE_PAGE")
                clock = first.isoformat()
                candidate = P.SourceItem(
                    source_key=source_key, event_key=_event_key(identity),
                    payload=payload, first_seen_utc=clock, version_seen_utc=clock,
                    published_utc=published.isoformat() if published else None,
                    provenance=P.SourceProof(sha, clock, hashlib.sha256(raw).hexdigest()),
                    kind=kind)
                # Ranking selects review candidates only; it proves no event
                # relation or issuer edge. All omitted rows remain unknown.
                text = title.casefold()
                priority = (0 if "data center" in text or "data centre" in text else
                            0 if "binance" in text and ("hack" in text or "breach" in text) else
                            1 if path.parent.name == "dj_reader_wsj" and "meta" in text else
                            2 if kind == "FILING" else 3 if kind == "ARTICLE" else 4)
                candidates.append((priority, candidate))
        if capped:
            break
    candidates.sort(key=lambda pair: (pair[0], pair[1].first_seen_utc,
                                      pair[1].source_key, pair[1].provenance.source_sha256))
    selected = [item for _, item in candidates[:MAX_SOURCES]]
    return selected, "PARTIAL_CAP" if capped or len(candidates) > MAX_SOURCES else "PARTIAL_ALLOWLIST"


def write_budget_sidecar(*, root: Path, directory: Path, review_time: datetime,
                         cutoff: datetime, hours: float) -> dict:
    sources, status = build_sample(root=root, review_time=review_time, cutoff=cutoff,
                                   hours=hours)
    if not sources:
        return {"status": status, "source_rows": 0}
    receipt = P.build_review(
        sources=sources, issuer_edges=[], holdings=None,
        review_time_utc=review_time.astimezone(timezone.utc).isoformat(),
        source_cutoff_utc=cutoff.astimezone(timezone.utc).isoformat(),
        input_complete=False, max_sources=MAX_SOURCES,
        upstream_state="BUDGET_REFUSED", upstream_exit_code=2)
    path = P.write_receipt(receipt, directory=directory)
    return {"status": "WRITTEN_PARTIAL", "source_rows": len(sources),
            "receipt_id": receipt["receipt_id"], "file": path.name,
            "sample_limit": status}
