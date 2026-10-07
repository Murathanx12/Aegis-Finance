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
Writing the folder does not publish anything. The commit of `backend/data/public_receipts/`
to `main` and its push are what put these pages on the public site (Railway builds from
main). `commit_public_receipts` (`scripts.publish_receipts --commit`, and the LAST step of
the AegisDataCatalog firing) does exactly that and nothing else, and REFUSES off `main`
(review C15 H1). Until a commit lands the public site serves the previous commit's copy,
whose ages are recomputed at serve time from each receipt's own stamp, so a stale copy
reads STALE, never fresh.

HOW THE ROUTERS CHOOSE
======================
By AGE (review C15 M1): the copy whose newest receipt stamp is newer wins; on a tie the
more complete one (more receipts present); live on a full tie. When the published copy is
served it says so in `served_from`, every receipt is re-aged from its own stamp, and the
row-level ages baked at publish time (Arena `mark_status` / `mark_age_days`, health
`age_s_now`) are recomputed from serve time.
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

# ── the owner's identity (review C15 M2) ─────────────────────────────────────────
#: The owner is named in shortlist provenance ("shortlist source: Murat") and card text.
#: EVERY kind is scrubbed (case-insensitive) to "the owner", and the same patterns are in
#: `leak_scan`, so a form the scrub missed REFUSES the publish instead of shipping.
#: Patterns: `config.OWNER_NAME_PATTERNS` (name + GitHub handle), plus extras from the env
#: var `AEGIS_OWNER_PATTERNS` (comma-separated regexes), plus two derived AT RUNTIME and never
#: written to the repo: the local part of the git `user.email` and the home folder's name.


def _runtime_owner_tokens() -> list[str]:
    out: list[str] = []
    try:
        import subprocess                                            # noqa: PLC0415
        r = subprocess.run(["git", "config", "user.email"], cwd=str(L.REPO), capture_output=True,
                           text=True, timeout=10)
        local = (r.stdout or "").strip().split("@")[0]
        if len(local) >= 4:
            out.append(re.escape(local))
    except Exception:                                                # noqa: BLE001 -- optional extra
        pass
    home = Path.home().name
    if len(home) >= 4 and home.lower() not in ("user", "users", "runner", "admin", "root", "home"):
        out.append(re.escape(home))
    return out


_OWNER_RX: Optional[re.Pattern] = None


def owner_pattern() -> re.Pattern:
    global _OWNER_RX
    if _OWNER_RX is None:
        import os                                                    # noqa: PLC0415
        pats = list(getattr(_config, "OWNER_NAME_PATTERNS", ()) or ())
        pats += [x.strip() for x in os.getenv("AEGIS_OWNER_PATTERNS", "").split(",") if x.strip()]
        pats += _runtime_owner_tokens()
        _OWNER_RX = re.compile("|".join(f"(?:{x})" for x in pats) or r"(?!x)x", re.IGNORECASE)
    return _OWNER_RX


def _owner_scrub(v: Any) -> Any:
    rx = owner_pattern()
    if isinstance(v, str):
        return rx.sub("the owner", v)
    if isinstance(v, list):
        return [_owner_scrub(x) for x in v]
    if isinstance(v, dict):
        return {(rx.sub("the owner", k) if isinstance(k, str) else k): _owner_scrub(x) for k, x in v.items()}
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
    out = {**blob, "lists": lists, "n_lists_dropped_owner_personal": dropped,
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
        if owner_pattern().search(v):
            out.append(f"{where}: owner identity")
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
            b, verdict = sanitised_bytes(k, _owner_scrub(payload))
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
                "how_public": ("this folder is TRACKED; a commit of backend/data/public_receipts/ to main and its "
                               "push make the pages public (publish_receipts.commit_public_receipts, the last step "
                               "of the AegisDataCatalog firing; it refuses off main). Routers serve whichever of "
                               "the live receipts and this copy is newer by the receipts' own stamps."),
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


def newest_stamp(payload: Optional[dict]) -> Optional[datetime]:
    """The newest OWN stamp among a payload's present receipts (never a file mtime)."""
    ts = [L.parse_utc(r.get("stamp_utc")) for r in (payload or {}).get("receipts") or []
          if r.get("status") != "MISSING"]
    ts = [t for t in ts if t is not None]
    return max(ts) if ts else None


def prefer_published(live: Optional[dict], pub: Optional[dict]) -> bool:
    """Review C15 M1: the NEWER of the two by their own receipt stamps wins; on a tie (or when
    neither is dateable) the more complete one (more receipts present) wins, live on a full tie."""
    if pub is None:
        return False
    if live is None:
        return True
    tl, tp = newest_stamp(live), newest_stamp(pub)
    if tl is not None and tp is not None and tl != tp:
        return tp > tl
    if tl is None and tp is not None:
        return True
    if tp is None and tl is not None:
        return False
    return _n_present(live) < _n_present(pub)


_ARENA_ROW_LISTS = ("books", "winners", "short_lived", "losers")


def _reage_arena(out: dict, now: datetime) -> None:
    """A published copy's book rows carry `mark_status` / `mark_age_days` baked at the ROI
    receipt's stamp. Recompute both from serve time: age += whole days since that stamp, and
    LIVE becomes STALE past `PAPER_ACCOUNT_MARK_STALE_DAYS` (the ROI writer's own rule)."""
    roi = next((r for r in out.get("receipts") or [] if r.get("kind") == "paper_accounts_roi"), None)
    t0 = L.parse_utc((roi or {}).get("stamp_utc"))
    stale_days = float(getattr(_config, "PAPER_ACCOUNT_MARK_STALE_DAYS", 4))
    shift = (now.date() - t0.date()).days if t0 else None
    for key in _ARENA_ROW_LISTS:
        rows = []
        for r in out.get(key) or []:
            r = dict(r)
            if r.get("mark_status") in ("LIVE", "STALE"):
                age = r.get("mark_age_days")
                if shift is None or not isinstance(age, (int, float)):
                    r["mark_status"], r["mark_age_days"] = "STALE", None
                else:
                    r["mark_age_days"] = int(age) + shift
                    r["mark_status"] = "LIVE" if r["mark_age_days"] <= stale_days else "STALE"
            rows.append(r)
        if key in out:
            out[key] = rows
    nums = out.get("numbers")
    if isinstance(nums, dict) and out.get("books"):
        counts: dict[str, int] = {}
        for r in out["books"]:
            ms = r.get("mark_status")
            if ms:
                counts[ms] = counts.get(ms, 0) + 1
        out["numbers"] = {**nums, "mark_status_counts": counts}


def _reage_health(out: dict, now: datetime) -> None:
    """Health rows: `age_s_now` recomputed from each row's own `evidence_utc`."""
    def fix(rows):
        res = []
        for r in rows or []:
            r = dict(r)
            ev = L.parse_utc(r.get("evidence_utc"))
            r["age_s_now"] = round((now - ev).total_seconds(), 1) if ev else None
            res.append(r)
        return res
    out["groups"] = [{**g, "rows": fix(g.get("rows"))} for g in out.get("groups") or []]
    for key in ("process_census", "same_output_rows"):
        if key in out:
            out[key] = fix(out[key])


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
    if kind == "arena":
        _reage_arena(out, now)
    elif kind == "system_health":
        _reage_health(out, now)
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


# ═══════════════════════════════════════════════════════════ commit + push (review C15 H1)
#
# Writing the folder publishes nothing: Railway builds from `main`. This is the caller that
# actually publishes. It commits ONLY `backend/data/public_receipts/` and pushes `main`, and
# it REFUSES (changing nothing) when:
#   * the current branch is not `main` (a data commit on a work branch never reaches Railway,
#     and switching branches from a scheduled job is not this job's call);
#   * anything OUTSIDE the folder is staged (the commit must be data-only);
#   * the manifest is not status OK or a published file does not hash to it;
#   * after `git add` of the folder, its staged diff is empty (nothing new to publish);
#   * `main` already carries unpushed commits that touch anything outside the folder (a data
#     job never pushes code it did not write).
# The commit message is fixed: `public receipts <published_utc> (data-only, sanitised; no
# code)`. No hook is skipped and nothing is signed differently. Every attempt writes ONE row
# (COMMITTED / REFUSED with the reasons) to `task_keeper/publish_commit.jsonl`.
# CI note: `ci.yml` runs the fast suite on every push to main, so a daily data commit costs
# one CI run a day; the Vercel workflow is filtered to `frontend/**` and does not fire.

COMMIT_MESSAGE = "public receipts {stamp} (data-only, sanitised; no code)"


def _git(runner, repo: Path, *args: str):
    return runner(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120)


def _lines(r) -> list[str]:
    return [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]


def _under(path: str, folder_rel: str) -> bool:
    f = folder_rel.rstrip("/")
    return path == f or path.startswith(f + "/")


def verify_manifest(folder: Path) -> list[str]:
    """Reasons the folder is not fit to commit (empty = fit)."""
    man = read_manifest(folder)
    if man is None:
        return [f"no readable {MANIFEST} in the folder"]
    bad = []
    if man.get("status") != "OK":
        bad.append(f"manifest status is {man.get('status')!r}, not 'OK' ({man.get('why') or 'no reason'})")
    for name, e in (man.get("kinds") or {}).items():
        if e.get("status") != "OK":
            continue
        f = folder / name / "latest.json"
        if not f.is_file():
            bad.append(f"{name}/latest.json is missing")
        elif _sha(f.read_bytes()) != e.get("sha256"):
            bad.append(f"{name}/latest.json does not hash to the manifest")
    return bad


def commit_public_receipts(*, repo: Optional[Path] = None, folder: Optional[Path] = None,
                           runner: Optional[Callable[..., Any]] = None, branch: Optional[str] = None,
                           remote: Optional[str] = None, log_path: Optional[Path] = None,
                           push: bool = True) -> dict:
    import subprocess                                                 # noqa: PLC0415
    runner = runner or subprocess.run
    repo = Path(repo or L.REPO)
    folder = Path(folder or public_dir())
    branch = branch or getattr(_config, "PUBLIC_RECEIPTS_BRANCH", "main")
    remote = remote or getattr(_config, "PUBLIC_RECEIPTS_REMOTE", "origin")
    row: dict[str, Any] = {"job": "publish_commit", "branch_required": branch}
    try:
        folder_rel = folder.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        row.update(status="REFUSED", reasons=["the public folder is not inside the repository"])
        return _log_commit(row, log_path)
    row["folder"] = folder_rel
    reasons: list[str] = []
    try:
        cur = _lines(_git(runner, repo, "rev-parse", "--abbrev-ref", "HEAD"))
        row["branch"] = cur[0] if cur else None
        if row["branch"] != branch:
            reasons.append(f"current branch is {row['branch']!r}, not {branch!r}: the public site builds "
                           f"from {branch}; this job never switches branches")
        outside = [x for x in _lines(_git(runner, repo, "diff", "--cached", "--name-only"))
                   if not _under(x, folder_rel)]
        if outside:
            reasons.append(f"{len(outside)} staged change(s) outside {folder_rel}/ (e.g. {outside[:3]}); "
                           f"the commit must be data-only")
        reasons += verify_manifest(folder)
        if reasons:
            row.update(status="REFUSED", reasons=reasons)
            return _log_commit(row, log_path)
        add = _git(runner, repo, "add", "--", folder_rel)
        if add.returncode != 0:
            row.update(status="REFUSED", reasons=[f"git add failed: {(add.stderr or '').strip()[-300:]}"])
            return _log_commit(row, log_path)
        staged = _lines(_git(runner, repo, "diff", "--cached", "--name-only", "--", folder_rel))
        if not staged:
            row.update(status="REFUSED",
                       reasons=[f"the staged diff of {folder_rel}/ is empty: nothing new to publish"])
            return _log_commit(row, log_path)
        outside = [x for x in _lines(_git(runner, repo, "diff", "--cached", "--name-only"))
                   if not _under(x, folder_rel)]
        if outside:
            _git(runner, repo, "reset", "-q", "--", folder_rel)
            row.update(status="REFUSED", reasons=[f"staged changes outside the folder appeared: {outside[:3]}"])
            return _log_commit(row, log_path)
        stamp = (read_manifest(folder) or {}).get("published_utc") or _now().isoformat(timespec="seconds")
        msg = COMMIT_MESSAGE.format(stamp=stamp)
        c = _git(runner, repo, "commit", "-m", msg, "--", folder_rel)
        if c.returncode != 0:
            _git(runner, repo, "reset", "-q", "--", folder_rel)
            err = ((c.stderr or "") + (c.stdout or "")).strip()[-300:]
            row.update(status="REFUSED", reasons=[f"git commit failed: {err}"])
            return _log_commit(row, log_path)
        head = _lines(_git(runner, repo, "rev-parse", "HEAD"))
        row.update(status="COMMITTED", commit=head[0] if head else None, message=msg, n_files=len(staged))
        if not push:
            return _log_commit(row, log_path)
        ahead = _lines(_git(runner, repo, "log", "--name-only", "--format=", f"{remote}/{branch}..{branch}"))
        foreign = sorted({x for x in ahead if not _under(x, folder_rel)})
        if foreign:
            row.update(pushed=False,
                       push_refused=(f"{branch} carries unpushed commits touching {len(foreign)} path(s) "
                                     f"outside the folder (e.g. {foreign[:3]}); a data job never pushes "
                                     f"code. The data commit stays local."))
            return _log_commit(row, log_path)
        ps = _git(runner, repo, "push", remote, branch)
        row["pushed"] = ps.returncode == 0
        if ps.returncode != 0:
            row["push_refused"] = f"git push failed: {(ps.stderr or '').strip()[-300:]}"
    except Exception as exc:                                          # noqa: BLE001
        row.update(status="REFUSED", reasons=[f"{type(exc).__name__}: {str(exc)[:300]}"])
    return _log_commit(row, log_path)


def _log_commit(row: dict, log_path: Optional[Path]) -> dict:
    row = {"utc": _now().isoformat(timespec="seconds"), **row}
    p = Path(log_path or Path(_config.OPTIMUS_LEDGER_DIR) / "task_keeper" / "publish_commit.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


__all__ = ["commit_public_receipts", "verify_manifest", "owner_pattern", "newest_stamp", "KINDS", "MAX_BYTES", "choose", "folder_bytes", "leak_scan", "load_published", "prefer_published",
           "public_dir", "publish", "read_manifest", "refresh", "sanitised_bytes"]
