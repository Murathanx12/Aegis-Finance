"""Publish the public pages' receipts into a TRACKED folder (chunk C15, 2026-10-07).

    python -m scripts.publish_receipts            # build, sanitise, write public_receipts/
    python -m scripts.publish_receipts --dry-run  # print what would be written, write nothing

WHY
===
The C19 legibility pages (Arena, Forecast Lab, Theory Lab, System Health) and the C4
Opportunity Explorer read receipts that are not in git: the ROI receipt, the reputation
receipt, the learning report and the twin boards are untracked, the health receipt is
gitignored (C19 review F12, C4 review F6). The Railway image builds from git, so on the
public site every page but the Theory Lab 404'd.

WHAT IS PUBLISHED
=================
For each public page, the payload its router serves, built from the NEWEST receipts on
this machine by the SAME builder (`legibility.*_payload`, `opportunities.load_latest`)
and passed through the SAME deny-by-default sanitiser the routers use
(`legibility_sanitise.sanitise` with the page's allow-list). The page payload IS the
trimmed receipt: only the fields the page renders survive, and every source receipt it
was built from is named in the payload's receipts strip and in the manifest with the
sha256 of the bytes read.

A tracked folder in a public repo is a SECOND publication channel that bypasses the
router entirely (C19 review F12), so sanitising happens HERE, at copy time, and the
published bytes are then checked twice: they must be a fixed point of the sanitiser
(`sanitise(x) == x`) and a deny-scan must find no dollar-equity key, account id, user
path, PID or loopback address. Either failing REFUSES that page (its previous copy stays).

    backend/data/public_receipts/<kind>/latest.json     the sanitised payload
    backend/data/public_receipts/MANIFEST.json          kind, sources (+sha256, stamp),
                                                       sha256 of the published copy, bytes

SIZE BUDGET: the folder is refused above `config.PUBLIC_RECEIPTS_MAX_BYTES` (5 MB);
nothing is written when the new set would exceed it.

WHAT MAKES THE PAGES PUBLIC
===========================
Writing the folder does not publish anything. The DAILY COMMIT of
`backend/data/public_receipts/` (and the push that deploys it) is what puts these pages
on the public site. Until it is committed the public site serves the previous commit's
copy, whose ages are recomputed at serve time from each receipt's own stamp, so a stale
copy reads STALE, never fresh.

HOW THE ROUTERS CHOOSE
======================
Live receipts first. The published copy is served when the live builder finds nothing
(a fresh Railway checkout) or finds FEWER of the page's receipts than the published copy
names (a partial checkout: e.g. the hyp_lab ledger is tracked but the twin boards are
not). The served payload then says so in `served_from`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _config
from backend.services import legibility as L
from backend.services import legibility_sanitise as S

SCHEMA = "public_receipts/1"
MANIFEST = "MANIFEST.json"
MAX_BYTES = int(getattr(_config, "PUBLIC_RECEIPTS_MAX_BYTES", 5_000_000))

#: per-row caps for the Opportunity Explorer copy (the page shows the first few; the live
#: receipt keeps all of them)
OPP_CAPS = {"news": 3, "catalysts": 5, "why_picked": 5}
OPP_RECENT_CAP = 3
#: rows per list in the public copy, in the receipt's own order (the list's rank order).
#: Only `analyst_upside_v3` (700 names) is longer today; the page says how many were cut.
OPP_MAX_ROWS_PER_LIST = 250


def public_dir() -> Path:
    """`<data>/public_receipts`, the SIBLING of the optimus ledger dir (so a test that points
    the ledger dir at a tmp folder never reads the real published copies)."""
    return Path(_config.OPTIMUS_LEDGER_DIR).parent / "public_receipts"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ═══════════════════════════════════════════════════════════ the kinds

#: the owner is named in shortlist provenance ("shortlist source: Murat") and in card text;
#: the public copy says "the owner" (C19 dropped owner-personal books for the same reason)
_OWNER_NAME = re.compile(r"\bMurat(?:han)?\b")


def _owner_scrub(v: Any) -> Any:
    if isinstance(v, str):
        return _OWNER_NAME.sub("the owner", v)
    if isinstance(v, list):
        return [_owner_scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: _owner_scrub(x) for k, x in v.items()}
    return v


def _opportunities() -> Optional[dict]:
    from backend.services import opportunities as OPP              # noqa: PLC0415
    blob = OPP.load_latest()
    if blob is None:
        return None
    src = OPP.opportunities_dir() / str(blob.get("receipt_file"))
    lists, dropped = [], 0
    for lst in blob.get("lists") or []:
        lid = str(lst.get("list_id") or "")
        if any(lid.startswith(p) for p in L.PERSONAL_ACCOUNT_PREFIXES):
            dropped += 1                    # an owner-personal list never reaches a public copy
            continue
        rows = []
        for r in (lst.get("rows") or [])[:OPP_MAX_ROWS_PER_LIST]:
            r = dict(r)
            for k, cap in OPP_CAPS.items():
                if isinstance(r.get(k), list):
                    r[k] = r[k][:cap]
            for k in ("insiders", "politicians"):
                if isinstance(r.get(k), dict) and isinstance(r[k].get("recent"), list):
                    r[k] = {**r[k], "recent": r[k]["recent"][:OPP_RECENT_CAP]}
            rows.append(r)
        lists.append({**lst, "rows": rows, "n_rows_in_receipt": len(lst.get("rows") or []),
                      "rows_trimmed_note": (f"public copy: the first {OPP_MAX_ROWS_PER_LIST} rows of "
                                            f"{len(lst.get('rows') or [])} in the receipt's order; "
                                            f"news <= {OPP_CAPS['news']}, catalysts <= "
                                            f"{OPP_CAPS['catalysts']}, insider / politician trades <= "
                                            f"{OPP_RECENT_CAP} per name; source URLs dropped")})
    out = {**blob, "lists": _owner_scrub(lists), "n_lists_dropped_owner_personal": dropped,
           "receipts": [{"kind": "opportunities", "file": L.rel(src), "sha256": L.sha256_of(src),
                         "stamp_utc": blob.get("generated_utc"), "role": "every row"}]}
    return out


@dataclass(frozen=True)
class Kind:
    name: str
    spec: str
    build: Callable[[], Optional[dict]]
    page: str


KINDS: tuple[Kind, ...] = (
    Kind("arena", "arena", lambda: L.arena_payload(), "/arena"),
    Kind("arena_stories", "arena_stories", lambda: L.stories_payload(), "/arena (decision stories)"),
    Kind("forecast_lab", "forecast_lab", lambda: L.forecast_lab_payload(), "/forecast-lab"),
    Kind("theory_lab_sticky", "theory_lab", lambda: L.theory_lab_payload(board="sticky"), "/theory-lab?board=sticky"),
    Kind("theory_lab_basket", "theory_lab", lambda: L.theory_lab_payload(board="basket"), "/theory-lab?board=basket"),
    Kind("system_health", "system_health", lambda: L.system_health_payload(), "/health"),
    Kind("opportunities", "opportunities", _opportunities, "/opportunities"),
)
KIND_BY_NAME = {k.name: k for k in KINDS}


# ═══════════════════════════════════════════════════════════ the leak scan

_LEAK_PATTERNS = (
    ("user path", re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]|/(?:home|Users|root)/[^\s\"']+")),
    ("broker account id", re.compile(r"\bPA[0-9A-Z]{8,}\b")),
    ("process id", re.compile(r"\bp?pid[ =:]*\d+")),
    ("loopback address", re.compile(r"\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0)(?::\d+)?")),
)


def leak_scan(v: Any, where: str = "$") -> list[str]:
    """Every denied key and every leaking string anywhere in `v` (empty = clean)."""
    out: list[str] = []
    if isinstance(v, dict):
        for k, x in v.items():
            if S._denied(str(k)):
                out.append(f"{where}.{k}: denied key")
            out.extend(leak_scan(str(k), f"{where}<key>") if isinstance(k, str) else [])
            out.extend(leak_scan(x, f"{where}.{k}"))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            out.extend(leak_scan(x, f"{where}[{i}]"))
    elif isinstance(v, str):
        for name, rx in _LEAK_PATTERNS:
            if rx.search(v):
                out.append(f"{where}: {name}")
    return out


def _sources(payload: dict) -> list[dict]:
    return [{k: r.get(k) for k in ("kind", "file", "sha256", "stamp_utc", "role", "status")}
            for r in payload.get("receipts") or [] if r.get("file")]


def sanitised_bytes(kind: Kind, payload: dict) -> tuple[Optional[bytes], dict]:
    """(bytes, verdict) -- None when the copy is refused, with the reason."""
    spec = S.SPEC[kind.spec]
    clean = S.sanitise(payload, spec)
    again = S.sanitise(json.loads(json.dumps(clean, default=str)), spec)
    if json.dumps(again, sort_keys=True, default=str) != json.dumps(clean, sort_keys=True, default=str):
        return None, {"status": "REFUSED", "why": "the published copy is not a fixed point of the sanitiser"}
    leaks = leak_scan(clean)
    if leaks:
        return None, {"status": "REFUSED", "why": f"leak scan found {len(leaks)} item(s): {leaks[:5]}"}
    return json.dumps(clean, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8"), {"status": "OK"}


# ═══════════════════════════════════════════════════════════ publish

def publish(*, out_dir: Optional[Path] = None, kinds: tuple[Kind, ...] = KINDS, dry_run: bool = False,
            max_bytes: int = MAX_BYTES, now: Optional[datetime] = None) -> dict:
    """Build -> sanitise -> verify every kind; refuse the whole set above `max_bytes`;
    otherwise write each `<kind>/latest.json` (temp -> verify -> replace) and the manifest.
    A kind whose build fails or finds nothing keeps its previous published copy (named)."""
    now = now or _now()
    out_dir = Path(out_dir or public_dir())
    prev = read_manifest(out_dir) or {}
    entries: dict[str, dict] = {}
    blobs: dict[str, bytes] = {}
    for k in kinds:
        e: dict[str, Any] = {"page": k.page, "spec": f"legibility_sanitise.SPEC[{k.spec!r}]",
                             "file": f"{k.name}/latest.json"}
        try:
            payload = k.build()
        except Exception as exc:                                    # noqa: BLE001 -- named, never raised
            payload = None
            e.update(status="REFUSED", why=f"build raised {type(exc).__name__}: {str(exc)[:200]}")
        if payload is None and "status" not in e:
            e.update(status="MISSING", why="the builder found no receipt on this machine")
        if payload is not None:
            b, verdict = sanitised_bytes(k, payload)
            e.update(verdict)
            if b is not None:
                blobs[k.name] = b
                e.update(sources=_sources(payload), sha256=_sha(b), bytes=len(b),
                         payload_status=payload.get("status"))
        if k.name not in blobs:
            old = (prev.get("kinds") or {}).get(k.name) or {}
            if (out_dir / e["file"]).is_file() and old.get("sha256"):
                e["kept_previous"] = {"sha256": old.get("sha256"), "published_utc": old.get("published_utc"),
                                      "bytes": old.get("bytes")}
        else:
            e["published_utc"] = now.isoformat(timespec="seconds")
        entries[k.name] = e
    # the budget is on the folder AFTER this publish: new copies + kept previous copies
    total = sum(len(b) for b in blobs.values()) + sum(int((e.get("kept_previous") or {}).get("bytes") or 0)
                                                     for e in entries.values())
    published = sorted(blobs)
    failed = sorted(n for n, e in entries.items() if e.get("status") == "REFUSED")
    missing = sorted(n for n, e in entries.items() if e.get("status") == "MISSING")
    # MISSING = no receipt exists on this machine either (the live page 404s too): named, not a failure
    status = "REFUSED" if not published else ("DEGRADED" if failed else "OK")
    why = None
    if total > max_bytes:
        status, why = "REFUSED", (f"the public set would be {total:,} bytes, over the {max_bytes:,}-byte budget "
                                  f"(config.PUBLIC_RECEIPTS_MAX_BYTES); nothing written")
    elif not published:
        why = "no page could be published (every kind missing or refused); nothing written"
    manifest = {"schema": SCHEMA, "published_utc": now.isoformat(timespec="seconds"), "status": status,
                "why": why, "total_bytes": total, "max_bytes": max_bytes,
                "how_public": ("this folder is TRACKED; the daily commit of backend/data/public_receipts/ is what "
                               "makes the pages public. Routers serve live receipts first and this copy when the "
                               "live directory lacks the page's receipts (Railway)."),
                "sanitiser": "backend/services/legibility_sanitise.py (deny-by-default, per-page allow-list) + "
                             "publish_receipts.leak_scan; each copy is a fixed point of the sanitiser",
                "kinds": entries, "published": published, "refused": failed, "missing": missing}
    if dry_run or status == "REFUSED":
        return {**manifest, "written": False, "out_dir": L.rel(out_dir)}
    for name, b in blobs.items():
        p = out_dir / name / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(b)
        if _sha(tmp.read_bytes()) != entries[name]["sha256"]:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"{name}: write verification failed; previous copy kept")
        tmp.replace(p)
    mp = out_dir / MANIFEST
    tmp = mp.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(mp)
    return {**manifest, "written": True, "out_dir": L.rel(out_dir)}


def read_manifest(out_dir: Optional[Path] = None) -> Optional[dict]:
    p = Path(out_dir or public_dir()) / MANIFEST
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return None


def folder_bytes(out_dir: Optional[Path] = None) -> int:
    d = Path(out_dir or public_dir())
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


# ═══════════════════════════════════════════════════════════ serving

_CACHE: dict = {}


def load_published(kind: str, out_dir: Optional[Path] = None, *, copy: bool = True) -> Optional[dict]:
    """The published copy of `kind`, or None. Never raises on a bad file (None = absent)."""
    p = Path(out_dir or public_dir()) / kind / "latest.json"
    try:
        if not p.is_file():
            return None
        st = p.stat()
        key = (str(p), st.st_size, st.st_mtime_ns)        # mtime keys the CACHE only, never an age
        hit = _CACHE.get(str(p))
        if hit and hit[0] == key:
            blob = hit[1]
        else:
            blob = json.loads(p.read_text(encoding="utf-8"))
            _CACHE[str(p)] = (key, blob)
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict):
        return None
    return json.loads(json.dumps(blob)) if copy else blob      # copy=False: the caller must not mutate it


def _n_missing(payload: Optional[dict]) -> int:
    return sum(1 for r in (payload or {}).get("receipts") or [] if r.get("status") == "MISSING")


def _n_present(payload: Optional[dict]) -> int:
    return sum(1 for r in (payload or {}).get("receipts") or [] if r.get("status") != "MISSING")


def prefer_published(live: Optional[dict], pub: Optional[dict]) -> bool:
    """Serve the published copy when the live build found nothing, or found fewer of the
    page's receipts than the published copy names."""
    if pub is None:
        return False
    if live is None:
        return True
    return _n_present(live) < _n_present(pub)


def refresh(pub: dict, kind: str, now: Optional[datetime] = None) -> dict:
    """Recompute every receipt's age from ITS OWN stamp at serve time (an age baked in at
    publish time would be wrong the next day) and say where the payload came from."""
    now = now or _now()
    out = dict(pub)
    recs = []
    for r in out.get("receipts") or []:
        r = dict(r)
        if r.get("status") != "MISSING":
            r.update(L.freshness(str(r.get("kind")), r.get("stamp_utc"), now))
        recs.append(r)
    if recs:
        out["receipts"] = recs
        out["status"] = L.overall_status(recs)
    man = read_manifest() or {}
    published = ((man.get("kinds") or {}).get(kind) or {}).get("published_utc")
    out["published_utc"] = published
    out["served_from"] = (f"public_receipts/{kind}/latest.json (published {published or 'at an unknown time'}): "
                          f"the live receipt directory on this server lacks this page's receipts; ages are "
                          f"recomputed now from each receipt's own stamp")
    return out


def choose(kind: str, live: Optional[dict]) -> Optional[dict]:
    pub = load_published(kind, copy=False)          # `refresh` builds new top-level / receipt dicts
    return refresh(pub, kind) if prefer_published(live, pub) else live


__all__ = ["KINDS", "MAX_BYTES", "choose", "folder_bytes", "leak_scan", "load_published", "prefer_published",
           "public_dir", "publish", "read_manifest", "refresh", "sanitised_bytes"]
