"""Split the legacy `predictions.jsonl` into sealed monthly streams -- the attended migration.

    python -m scripts.ledger_split --plan                              # print the plan; write nothing
    python -m scripts.ledger_split --plan --history                    # + verify every committed version
    python -m scripts.ledger_split --apply --expect-sha256 <sha>       # migrate exactly what was planned
    python -m scripts.ledger_split --apply --plan-file plan.json       # ... or against a saved --json plan
    python -m scripts.ledger_split --discard-partial                   # remove an interrupted apply's files

WHAT THE SPLIT DOES TO ONE ROW
==============================
An OPEN row (no outcome, not void) goes to the forecast stream byte-for-byte as
the legacy writer serialised it (key order kept, LF instead of CRLF).

A TERMINAL row (graded or void) is split in two:

* the FORECAST is the row with its resolution fields reset to the open-record
  defaults (`forecast_ledger.RESOLUTION_DEFAULTS`), and with the trailing block
  of non-core resolution fields the resolver APPENDED to an older-schema row
  (`calibration_bucket`, `vs_benchmark` on a 1.0.0 row; `voided_at`/`voided_by`)
  removed -- i.e. the row in the shape it was made in;
* the EVENT carries exactly the fields that differ, in the legacy key order.

Folding the event onto the forecast reproduces the legacy row: dict-equal, the
same key order, and the same canonical content hash. `plan()` checks that for
every row, and also re-parses the serialised stream BYTES through the real
reader and compares the result to the legacy rows in legacy order -- the
round trip, not just the split.

The legacy file's own resolution step overwrote the forecast in place, so for a
graded row the "as made" bytes are not recoverable from the ledger itself; the
reset-to-defaults rule is a reconstruction, stated here and on the marker.

EVENT MONTHS
------------
A grade is filed by its `resolved_at` month; a void by its `voided_at` month.
Six voids from 2026-08 carry no `voided_at` (a manual void before the void pass
stamped one); they are filed under their forecast's `made_at` month and say so
(`month_basis`).

THE CHAIN BREAK THAT WAS REMEMBERED
===================================
Handoffs say "the ledger hash chain has been broken since 25 Aug" and a review
placed it in this file. It is not here: `predictions.jsonl` never carried a row
chain (`legacy_chain_report` searches every row for a chain field and finds
only content hashes: `prompt_hash`, `input_snapshot_hash`, `policy_hash`).
The torn `_prev` chain is the terminal repo's `state/decisions.jsonl`
(docs/REDTEAM_2026-09-02_ENGINE_AUDIT.md R14; scripts/write_superseded_sidecars.py).
What this ledger DID have is git: `legacy_history_report` replays every
committed version and reports the first byte-level discontinuity and whether
any committed forecast was ever removed or rewritten. Both go on the genesis
manifest as `legacy_chain_break`, unrepaired, and tamper evidence restarts at
the new manifest chain.
"""

from __future__ import annotations

import copy
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend import config as _config
from backend.services import forecast_ledger as FL
from backend.services.forecast_ledger import MigrationRefused

MIGRATION_VERSION = "ledger_split/1"
#: Resolution fields every schema version carried at creation; never dropped
#: from the forecast half even when they trail the row.
CORE_KEYS = ("resolved_at", "outcome", "brier", "resolution_detail", "void_reason")
#: Exact names a row-hash chain field has gone by in this programme and the
#: terminal repo. A key containing "chain", or "prev" and "hash" together, is
#: also treated as one.
CHAIN_FIELD_NAMES = frozenset({"prev_hash", "prev_row_hash", "row_hash", "chain_hash",
                               "prev_sha256", "row_sha256", "entry_hash", "prev_entry_hash",
                               "_prev", "_hash", "hash_prev", "prev"})

NOT_REPAIRED = ("Legacy row-chain continuity is NOT being repaired. The legacy file is "
                "left byte-for-byte untouched; whatever it is, it stays.")
RESTART = ("Tamper evidence for the forecast ledger restarts at this manifest chain: the "
           "genesis manifest vouches for the bytes of the streams it seals and for the "
           "legacy file's sha256 below. Nothing before it is vouched for by the chain -- "
           "only by git history.")


def _now() -> datetime:
    return FL._now()


# ─────────────────────────────── one row ─────────────────────────────────────

def terminal_kind(row: dict) -> Optional[str]:
    if row.get("outcome") is not None:
        return "resolve"
    if row.get("void_reason"):
        return "void"
    return None


def split_row(row: dict) -> tuple[dict, Optional[dict]]:
    """(forecast half, event half or None). See the module docstring."""
    kind = terminal_kind(row)
    if kind is None:
        return dict(row), None
    keys = list(row)
    cut = len(keys)
    while cut and keys[cut - 1] in FL.RESOLUTION_KEYS and keys[cut - 1] not in CORE_KEYS:
        cut -= 1
    suffix = set(keys[cut:])
    forecast: dict = {}
    for k in keys[:cut]:
        forecast[k] = (copy.deepcopy(FL.RESOLUTION_DEFAULTS.get(k))
                       if k in FL.RESOLUTION_KEYS else row[k])
    sets = {k: row[k] for k in keys
            if k in suffix or (k in FL.RESOLUTION_KEYS and forecast.get(k) != row[k])}
    if kind == "resolve":
        month, basis = FL.month_of(row.get("resolved_at")), "resolved_at"
    else:
        month, basis = FL.month_of(row.get("voided_at")), "voided_at"
    if month is None:
        month = FL.month_of(row.get("made_at"))
        basis = (f"made_at ({'resolved_at' if kind == 'resolve' else 'voided_at'} absent "
                 f"on the legacy row)")
    event = {"schema": FL.EVENT_SCHEMA, "prediction_id": row.get("prediction_id"),
             "event": kind, "set": sets, "recorded_at": None,
             "writer": f"scripts.ledger_split ({MIGRATION_VERSION}): legacy row",
             "month_basis": basis, "_month": month}
    return forecast, event


def _frozen(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in FL.RESOLUTION_KEYS}


# ─────────────────────────────── the whole file ──────────────────────────────

def split_legacy(raw: bytes, *, source: str = FL.LEGACY_NAME) -> dict:
    """Pure: legacy bytes -> planned stream files + a verification report.

    Refuses (MigrationRefused) on an unparseable line, a row without a
    prediction_id or a placeable made_at, or a duplicate id -- a split of an
    ambiguous ledger would have to choose, and choosing is what a migration
    must not do silently."""
    if not raw:
        raise MigrationRefused(f"{source} is empty: there is nothing to split")
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    rows: list[dict] = []
    crlf = blank = 0
    for i, line in enumerate(lines, 1):
        if line.endswith(b"\r"):
            crlf += 1
        s = line.strip()
        if not s:
            blank += 1
            continue
        try:
            row = json.loads(s.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationRefused(f"{source}:{i} is not valid JSON ({exc}); fix or quarantine "
                                   f"it first -- a split never drops a line") from exc
        if not isinstance(row, dict) or not isinstance(row.get("prediction_id"), str):
            raise MigrationRefused(f"{source}:{i} has no prediction_id")
        if FL.month_of(row.get("made_at")) is None:
            raise MigrationRefused(f"{source}:{i} ({row['prediction_id']}) has no YYYY-MM made_at")
        row["__line__"] = i
        rows.append(row)
    dup = [k for k, n in Counter(r["prediction_id"] for r in rows).items() if n > 1]
    if dup:
        raise MigrationRefused(f"{len(dup)} duplicate prediction_id(s) in {source} "
                               f"(e.g. {dup[:3]}); resolve them before splitting")

    forecasts: dict[str, list[bytes]] = {}
    events: dict[str, list[bytes]] = {}
    by_kind: Counter = Counter()
    by_basis: Counter = Counter()
    checks = Counter()
    mismatches: list[dict] = []
    inversions = 0
    prev_made = None
    for row in rows:
        line_no = row.pop("__line__")
        made = str(row["made_at"])
        if prev_made is not None and made < prev_made:
            inversions += 1
        prev_made = made
        forecast, event = split_row(row)
        forecasts.setdefault(FL.month_of(row["made_at"]), []).append(FL.row_line(forecast))
        folded = dict(forecast)
        if event is not None:
            month = event.pop("_month")
            events.setdefault(month, []).append(FL.row_line(event))
            by_kind[event["event"]] += 1
            by_basis[event["month_basis"]] += 1
            folded.update(event["set"])
        checks["rows"] += 1
        ok_eq = folded == row
        ok_hash = FL.canonical_row_hash(folded) == FL.canonical_row_hash(row)
        ok_order = list(folded) == list(row)
        ok_frozen = _frozen(forecast) == _frozen(row)
        checks["fold_equals_legacy"] += ok_eq
        checks["canonical_hash_equal"] += ok_hash
        checks["key_order_preserved"] += ok_order
        checks["frozen_fields_identical"] += ok_frozen
        if not (ok_eq and ok_hash and ok_frozen) and len(mismatches) < 20:
            mismatches.append({"line": line_no, "prediction_id": row["prediction_id"],
                               "equal": ok_eq, "hash": ok_hash, "frozen": ok_frozen})

    files = ([("forecasts", m, b"".join(v)) for m, v in sorted(forecasts.items())]
             + [("resolutions", m, b"".join(v)) for m, v in sorted(events.items())])
    # THE ROUND TRIP: parse the planned bytes back through the reader's own
    # parse + fold, and compare to the legacy rows in legacy order.
    back = fold_bytes({m: b for s, m, b in files if s == "forecasts"},
                      {m: b for s, m, b in files if s == "resolutions"})
    rt_same = (len(back) == len(rows)
               and all(FL.canonical_row_hash(a) == FL.canonical_row_hash(b)
                       for a, b in zip(back, rows)))
    rt_order = [r["prediction_id"] for r in back] == [r["prediction_id"] for r in rows]
    verification = {**{k: int(v) for k, v in checks.items()},
                    "round_trip_rows": len(back), "round_trip_equal": rt_same,
                    "round_trip_order_equal": rt_order, "mismatches": mismatches,
                    "ok": (not mismatches and rt_same and rt_order
                           and checks["fold_equals_legacy"] == len(rows))}
    return {
        "source": {"name": source, "sha256": FL.sha256_bytes(raw), "bytes": len(raw),
                   "lines": len(lines), "rows": len(rows), "blank_lines": blank,
                   "crlf_lines": crlf, "duplicate_ids": 0,
                   "made_at_order_inversions": inversions,
                   "terminal": dict(by_kind),
                   "open": len(rows) - sum(by_kind.values())},
        "files": files,
        "events_by_basis": dict(sorted(by_basis.items())),
        "verification": verification,
    }


def fold_bytes(forecast_files: dict[str, bytes], resolution_files: dict[str, bytes]) -> list[dict]:
    """The reader's fold over in-memory stream bytes (month order)."""
    stats = FL.FoldStats()
    by_id: dict[str, dict] = {}
    for month in sorted(forecast_files):
        for i, line in enumerate(FL._split_raw_lines(forecast_files[month]), 1):
            row = FL._parse_line(line, f"forecasts_{month}", i, True, stats.bad_lines)
            if row is not None and row.get("prediction_id") not in by_id:
                by_id[row["prediction_id"]] = row
    evs = []
    for month in sorted(resolution_files):
        for i, line in enumerate(FL._split_raw_lines(resolution_files[month]), 1):
            ev = FL._parse_line(line, f"resolutions_{month}", i, True, stats.bad_lines)
            if ev is not None:
                evs.append(ev)
    FL.fold(by_id, evs, stats)
    return list(by_id.values())


# ─────────────────────────────── the remembered chain ────────────────────────

def _is_chain_field(name: str) -> bool:
    n = name.lower()
    return n in CHAIN_FIELD_NAMES or "chain" in n or ("prev" in n and ("hash" in n or "sha" in n))


def legacy_chain_report(raw: bytes, *, source: str = FL.LEGACY_NAME,
                        claim: Optional[str] = None) -> dict:
    """Does the legacy file carry a row chain, and where does it first break?

    Uses the ledger's REAL fields. With no chain field anywhere the answer is
    `NO_ROW_CHAIN` and there is no first mismatch to report -- which is itself
    the finding, because the remembered break is then somebody else's. With a
    chain field, the link scheme is identified from the first link (sha256 of
    the previous line, of the previous row's canonical JSON, or the previous
    row's own hash field) and the first line where it fails is reported with the
    expected and found values."""
    lines = [ln.rstrip(b"\r") for ln in FL._split_raw_lines(raw)]
    parsed: list[tuple[int, bytes, dict]] = []
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            parsed.append((i, ln, obj))
    chain_fields: Counter = Counter()
    hash_like: Counter = Counter()
    for _, _, obj in parsed:
        for k in obj:
            if _is_chain_field(k):
                chain_fields[k] += 1
            elif "hash" in k.lower() or "sha" in k.lower():
                hash_like[k] += 1
    out: dict = {
        "source": source, "source_sha256": FL.sha256_bytes(raw), "source_bytes": len(raw),
        "rows_scanned": len(parsed),
        "chain_fields_searched": sorted(CHAIN_FIELD_NAMES) + ["*chain*", "*prev*hash*",
                                                              "*prev*sha*"],
        "chain_fields_found": dict(chain_fields),
        "hash_fields_present": dict(sorted(hash_like.items())),
        "first_mismatch_line": None, "previous_hash_expected": None, "hash_found": None,
        "statement_not_repaired": NOT_REPAIRED, "statement_restart": RESTART,
    }
    if claim:
        out["claim_checked"] = claim
    if not chain_fields:
        out["status"] = "NO_ROW_CHAIN"
        out["finding"] = (f"none of the {len(parsed):,} rows carries a row-chain field; the "
                          f"hash-named fields present ({', '.join(sorted(hash_like)) or 'none'}) "
                          f"are CONTENT hashes of a row's own prompt/inputs/policy and link "
                          f"nothing. There is no chain here to break.")
        return out
    prev_field = max(chain_fields, key=lambda k: ("prev" in k.lower(), chain_fields[k]))
    self_fields = [k for k in chain_fields if k != prev_field]
    schemes = {
        "prev_line_sha256": lambda prev_ln, prev_obj: FL.sha256_bytes(prev_ln),
        "prev_row_canonical_sha256": lambda prev_ln, prev_obj: FL.canonical_row_hash(prev_obj),
    }
    for sf in self_fields:
        schemes[f"prev_row_field:{sf}"] = (lambda f: lambda prev_ln, prev_obj: prev_obj.get(f))(sf)
    chained = [(i, ln, o) for i, ln, o in parsed if prev_field in o]
    out["prev_field"] = prev_field
    if len(chained) < 2:
        out["status"] = "CHAIN_TOO_SHORT"
        return out
    scheme = None
    for name, fn in schemes.items():
        if chained[1][2].get(prev_field) == fn(chained[0][1], chained[0][2]):
            scheme = name
            break
    if scheme is None:
        out["status"] = "UNRECOGNISED_SCHEME"
        out["first_mismatch_line"] = chained[1][0]
        out["hash_found"] = chained[1][2].get(prev_field)
        out["finding"] = ("the first link verifies under no known scheme; the line above is "
                          "where verification first fails, under every scheme tried")
        return out
    out["scheme"] = scheme
    fn = schemes[scheme]
    breaks = 0
    for (i0, l0, o0), (i1, l1, o1) in zip(chained, chained[1:]):
        want = fn(l0, o0)
        if o1.get(prev_field) != want:
            breaks += 1
            if out["first_mismatch_line"] is None:
                out.update(first_mismatch_line=i1, previous_hash_expected=want,
                           hash_found=o1.get(prev_field),
                           first_mismatch_prediction_id=o1.get("prediction_id"))
    out["breaks"] = breaks
    out["status"] = "BROKEN" if breaks else "INTACT"
    return out


def _git(args: list[str], cwd: Path, *, binary: bool = False, timeout: float = 300):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace").strip()[:300]
                           or f"git {' '.join(args)} exited {r.returncode}")
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def legacy_history_report(legacy_path: Path, *, repo: Optional[Path] = None,
                          max_versions: Optional[int] = None) -> dict:
    """Replay every COMMITTED version of the legacy file: the only tamper
    evidence it ever had was git, so this is the verifier of that evidence.

    Per consecutive pair of versions: rows removed, frozen fields changed,
    grades changed or withdrawn, appends not at the end, line-ending changes;
    and the FIRST version that is not a byte-prefix extension of its
    predecessor, with the first differing line's sha256 before and after.
    Never raises: a missing git or a path outside the checkout is reported as
    NOT_COMPUTED with the reason."""
    repo = Path(repo) if repo else FL._repo_root()
    try:
        relp = Path(legacy_path).resolve().relative_to(repo.resolve()).as_posix()
    except (ValueError, OSError):
        return {"status": "NOT_COMPUTED",
                "reason": f"{legacy_path} is not inside the git checkout {repo}"}
    try:
        shallow = _git(["rev-parse", "--is-shallow-repository"], repo).strip() == "true"
        log = _git(["log", "--format=%H %cI", "--reverse", "--", relp], repo).split("\n")
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "NOT_COMPUTED", "reason": f"git unavailable: {exc}"}
    commits = [ln.split(" ", 1) for ln in log if ln.strip()]
    if max_versions:
        commits = commits[-max_versions:]
    if not commits:
        return {"status": "NOT_COMPUTED", "reason": f"no commit touches {relp}"}
    versions: list[dict] = []
    totals = Counter()
    first_break: Optional[dict] = None
    first_semantic: Optional[dict] = None
    chain_seen: Counter = Counter()
    prev_lines: Optional[list[bytes]] = None
    prev_raw: Optional[bytes] = None
    prev_index: Optional[dict] = None
    prev_order: Optional[list[str]] = None
    for sha, when in commits:
        try:
            raw = _git(["cat-file", "blob", f"{sha}:{relp}"], repo, binary=True)
        except Exception as exc:                                   # noqa: BLE001
            versions.append({"commit": sha[:12], "committed_at": when, "error": str(exc)[:200]})
            continue
        lines = FL._split_raw_lines(raw)
        index: dict[str, tuple[str, str, bool]] = {}
        order: list[str] = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            try:
                obj = json.loads(s.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                totals["unparseable_lines"] += 1
                continue
            if not isinstance(obj, dict):
                continue
            for k in obj:
                if _is_chain_field(k):
                    chain_seen[k] += 1
            pid = obj.get("prediction_id")
            res = {k: obj[k] for k in obj if k in FL.RESOLUTION_KEYS}
            index[pid] = (FL.canonical_row_hash(_frozen(obj)), FL.canonical_row_hash(res),
                          terminal_kind(obj) is not None)
            order.append(pid)
        v = {"commit": sha[:12], "committed_at": when, "rows": len(order),
             "bytes": len(raw), "sha256": FL.sha256_bytes(raw),
             "crlf_lines": sum(1 for ln in lines if ln.endswith(b"\r"))}
        if prev_index is not None:
            removed = [p for p in prev_index if p not in index]
            frozen_changed = [p for p in prev_index if p in index
                              and prev_index[p][0] != index[p][0]]
            grade_changed = [p for p in prev_index if p in index and prev_index[p][2]
                             and prev_index[p][1] != index[p][1]]
            newly_terminal = [p for p in prev_index if p in index and not prev_index[p][2]
                              and index[p][2]]
            pos = {p: i for i, p in enumerate(order)}
            survivors = [p for p in prev_order if p in pos]
            reordered = sum(1 for a, b in zip(survivors, survivors[1:]) if pos[a] > pos[b])
            new_ids = [p for p in order if p not in prev_index]
            first_new = min((pos[p] for p in new_ids), default=None)
            not_at_end = (sum(1 for p in survivors if pos[p] > first_new)
                          if first_new is not None else 0)
            v.update(removed=len(removed), frozen_changed=len(frozen_changed),
                     grade_changed=len(grade_changed), newly_terminal=len(newly_terminal),
                     reordered_pairs=reordered, appended=len(new_ids),
                     appended_not_at_end=not_at_end,
                     byte_prefix_of_next=raw.startswith(prev_raw))
            for k in ("removed", "frozen_changed", "grade_changed", "newly_terminal",
                      "reordered_pairs", "appended", "appended_not_at_end"):
                totals[k] += v[k]
            semantic = removed or frozen_changed or grade_changed or reordered or not_at_end
            if semantic and first_semantic is None:
                first_semantic = {"commit": sha[:12], "committed_at": when,
                                  "removed": len(removed), "frozen_changed": len(frozen_changed),
                                  "grade_changed": len(grade_changed),
                                  "sample": (removed or frozen_changed or grade_changed)[:5]}
            if not v["byte_prefix_of_next"] and first_break is None:
                i = next((j for j, (a, b) in enumerate(zip(prev_lines, lines)) if a != b),
                         min(len(prev_lines), len(lines)))
                before = prev_lines[i] if i < len(prev_lines) else b""
                after = lines[i] if i < len(lines) else b""
                kind = "line removed or truncated"
                cr_added = after.endswith(b"\r") and not before.endswith(b"\r")
                try:
                    ob, oa = json.loads(before.strip()), json.loads(after.strip())
                    if ob == oa:
                        kind = ("same row, different bytes (line endings: CR "
                                + ("added)" if cr_added else "changed)"))
                    elif _frozen(ob) == _frozen(oa):
                        kind = "same forecast, resolution fields rewritten in place"
                    else:
                        kind = "a different row at this line (removal, reorder or edit)"
                except (ValueError, TypeError):
                    pass
                first_break = {"commit": sha[:12], "committed_at": when, "line": i + 1,
                               "previous_line_sha256": FL.sha256_bytes(before),
                               "found_line_sha256": FL.sha256_bytes(after),
                               "classification": kind,
                               "previous_commit": versions[-1]["commit"] if versions else None}
        versions.append(v)
        prev_lines, prev_raw, prev_index, prev_order = lines, raw, index, order
    ok = not first_semantic
    return {
        "status": "CONTINUOUS" if ok else "DISCONTINUOUS",
        "path": relp, "shallow_clone": shallow, "versions": len(versions),
        "first_commit": versions[0]["commit"] if versions else None,
        "last_commit": versions[-1]["commit"] if versions else None,
        "chain_fields_seen_in_any_version": dict(chain_seen),
        "totals": dict(totals),
        "first_semantic_break": first_semantic,
        "first_byte_discontinuity": first_break,
        "finding": (("across every committed version no forecast row was removed, reordered "
                     "or had a frozen field changed, and no grade was changed or withdrawn; "
                     "byte-level changes are resolutions written in place and line endings")
                    if ok else "a committed forecast was removed, reordered or rewritten: "
                               "see first_semantic_break"),
        "per_version": versions,
    }


CLAIM_25_AUG = ("Handoffs and docs/reviews/REVIEW_2026-10-06_C10_DATA_CATALOG.md Q8 say a "
                "per-row ledger hash chain broke on 25 Aug 2026 (remembered at line ~1203). "
                "That chain is the terminal repo's state/decisions.jsonl `_prev` chain "
                "(docs/REDTEAM_2026-09-02_ENGINE_AUDIT.md R14, scripts/write_superseded_sidecars.py, "
                "docs/research_notes/2026-09-13/spec_allocator_kill_promote.md); this file "
                "never carried one, so the claim does not apply to it.")


# ─────────────────────────────── plan ────────────────────────────────────────

def _planned_files(be: FL.Backend, split: dict) -> list[dict]:
    out = []
    for stream, month, data in split["files"]:
        out.append({"stream": stream, "month": month,
                    "file": FL.rel(be.stream_path(stream, month)),
                    "rows": len(FL._split_raw_lines(data)), "bytes": len(data),
                    "sha256": FL.sha256_bytes(data)})
    return out


def plan(legacy_path: Optional[Path] = None, *, now: Optional[datetime] = None,
         history: bool = False) -> dict:
    """Everything `--apply` would do, computed from the file as it is now.
    Writes nothing."""
    legacy = Path(legacy_path) if legacy_path is not None else FL.default_legacy_path()
    be = FL.backend_for(legacy)
    run = now or _now()
    out: dict = {"tool": "scripts.ledger_split", "mode": "plan",
                 "migration_version": MIGRATION_VERSION, "utc": FL._iso(run),
                 "backend_now": be.describe(), "writes": "none"}
    if be.kind == "streams":
        out["status"] = "ALREADY_APPLIED"
        out["reason"] = be.reason
        return out
    if not legacy.exists():
        raise MigrationRefused(f"no legacy ledger at {FL.rel(legacy)}")
    raw = legacy.read_bytes()
    split = split_legacy(raw, source=FL.rel(legacy))
    files = _planned_files(be, split)
    chain = legacy_chain_report(raw, source=FL.rel(legacy), claim=CLAIM_25_AUG)
    if history:
        chain["git_history"] = legacy_history_report(legacy)
    order = sorted(files, key=lambda f: FL._chain_key(f["stream"], f["month"]))
    seal = [f"{f['stream']}_{f['month']}" for f in order if FL.is_sealable_month(f["month"], run)]
    left_open = [f"{f['stream']}_{f['month']}" for f in order
                 if not FL.is_sealable_month(f["month"], run)]
    strays = [p.name for s in FL.STREAMS for _, p in FL.stream_files(be, s)]
    out.update({
        "status": "READY" if split["verification"]["ok"] and not strays else "BLOCKED",
        "source": {"path": FL.rel(legacy), **split["source"]},
        "forecast_streams": [f for f in files if f["stream"] == "forecasts"],
        "resolution_streams": [f for f in files if f["stream"] == "resolutions"],
        "events_by_basis": split["events_by_basis"],
        "manifest_plan": {
            "manifest_dir": FL.rel(be.manifest_dir),
            "marker": FL.rel(FL.marker_path(legacy)),
            "chain_order": "month, then forecasts before resolutions",
            "seal_at_apply": seal, "genesis": seal[0] if seal else None,
            "left_open": left_open,
            "grace_days": _config.FORECAST_LEDGER_SEAL_GRACE_DAYS,
            "note": ("each manifest records rows, bytes and sha256 of its stream file and the "
                     "previous manifest's hash; the hashes of the manifests themselves include "
                     "the seal timestamp and are computed at --apply"),
        },
        "verification": split["verification"],
        "legacy_chain_break": chain,
        "blocking": ([f"stream files already exist: {strays}"] if strays else [])
                    + ([] if split["verification"]["ok"] else ["split verification failed"]),
        "next": (f"python -m scripts.ledger_split --apply --expect-sha256 "
                 f"{split['source']['sha256']}"),
    })
    return out


# ─────────────────────────────── apply ───────────────────────────────────────

def _strays(be: FL.Backend) -> list[Path]:
    out = [p for s in FL.STREAMS for _, p in FL.stream_files(be, s)]
    if be.manifest_dir.is_dir():
        out += sorted(p for p in be.manifest_dir.glob("*.json"))
    return out


def apply(legacy_path: Optional[Path] = None, *, expect_sha256: Optional[str] = None,
          plan_file: Optional[Path] = None, now: Optional[datetime] = None,
          history: bool = True) -> dict:
    """Migrate exactly the planned bytes, verify, then switch. Attended.

    Order: refuse without a fingerprint -> lock -> refuse if already switched
    to a different source, or if stream files already exist -> re-hash the
    legacy file against the fingerprint -> split and verify -> write each
    stream file atomically -> re-read and verify the bytes on disk -> re-hash
    the legacy file again (a writer that bypassed the lock) -> write the marker
    (THE SWITCH) -> seal the closed months -> verify through the real reader.
    Any failure before the switch removes what this run wrote; the legacy file
    is never modified."""
    legacy = Path(legacy_path) if legacy_path is not None else FL.default_legacy_path()
    planned = None
    if plan_file is not None:
        try:
            planned = json.loads(Path(plan_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MigrationRefused(f"cannot read the plan file {plan_file}: {exc}") from exc
        psha = ((planned or {}).get("source") or {}).get("sha256")
        if not psha:
            raise MigrationRefused(f"{plan_file} is not a `--plan --json` output (no source.sha256)")
        if expect_sha256 and expect_sha256 != psha:
            raise MigrationRefused(f"--expect-sha256 {expect_sha256[:12]} disagrees with the plan "
                                   f"file's source sha256 {psha[:12]}")
        expect_sha256 = psha
    if not expect_sha256:
        raise MigrationRefused(
            "--apply needs the source fingerprint the plan printed: run "
            "`python -m scripts.ledger_split --plan`, then pass --expect-sha256 <sha> "
            "(or --plan-file <the --plan --json output>). Nothing was written.")
    run = now or _now()
    with FL.ledger_lock(legacy.parent, purpose="ledger_split --apply"):
        be = FL.backend_for(legacy)
        if be.kind == "streams":
            if (be.marker or {}).get("legacy_sha256") == expect_sha256:
                return {"status": "ALREADY_APPLIED", "reason": be.reason,
                        "marker": FL.rel(FL.marker_path(legacy)), "writes": "none"}
            raise MigrationRefused(
                f"{FL.rel(legacy)} was already migrated from source sha256 "
                f"{str((be.marker or {}).get('legacy_sha256'))[:12]}, not {expect_sha256[:12]}. "
                f"A second application is refused.")
        strays = _strays(be)
        if strays:
            raise MigrationRefused(
                f"{len(strays)} stream/manifest file(s) already exist with no migration marker "
                f"(an interrupted --apply?): {[p.name for p in strays[:8]]}. Readers still use the "
                f"legacy file. Run `python -m scripts.ledger_split --discard-partial`, then "
                f"--plan and --apply again.")
        if not legacy.exists():
            raise MigrationRefused(f"no legacy ledger at {FL.rel(legacy)}")
        raw = legacy.read_bytes()
        sha = FL.sha256_bytes(raw)
        if sha != expect_sha256:
            raise MigrationRefused(
                f"the legacy ledger changed since the plan: planned sha256 {expect_sha256[:12]}, "
                f"found {sha[:12]} ({len(raw):,} bytes). A writer appended or graded after the "
                f"plan. Re-run --plan, then --apply with the new sha256. Nothing was written.")
        split = split_legacy(raw, source=FL.rel(legacy))
        if not split["verification"]["ok"]:
            raise MigrationRefused(f"split verification failed: "
                                   f"{split['verification']['mismatches'][:3]}")
        files = _planned_files(be, split)
        if planned is not None:
            want = {(f["stream"], f["month"], f["sha256"], f["rows"])
                    for f in (planned.get("forecast_streams") or [])
                    + (planned.get("resolution_streams") or [])}
            have = {(f["stream"], f["month"], f["sha256"], f["rows"]) for f in files}
            if want != have:
                raise MigrationRefused("the recomputed split differs from the plan file's "
                                       "(a different splitter version?); nothing written")
        chain = legacy_chain_report(raw, source=FL.rel(legacy), claim=CLAIM_25_AUG)
        if history:
            chain["git_history"] = legacy_history_report(legacy)
            chain["git_history"].pop("per_version", None)
        written: list[Path] = []
        switched = False
        try:
            for stream, month, data in split["files"]:
                p = be.stream_path(stream, month)
                if p.exists():
                    raise MigrationRefused(f"{FL.rel(p)} appeared during the apply; stopping")
                FL.atomic_write_bytes(p, data)
                written.append(p)
            for (stream, month, data), f in zip(split["files"], files):
                disk = be.stream_path(stream, month).read_bytes()
                if FL.sha256_bytes(disk) != f["sha256"]:
                    raise MigrationRefused(f"{f['file']} did not read back as written")
            if FL.sha256_file(legacy) != expect_sha256:
                raise MigrationRefused(
                    "the legacy ledger changed DURING the apply although the ledger lock was "
                    "held: a writer that does not take the lock (code from before this change "
                    "that was not restarted) appended to it. Everything this run wrote was "
                    "removed; restart every writer, then --plan and --apply again.")
            marker = {
                "schema": FL.MARKER_SCHEMA, "migration_version": MIGRATION_VERSION,
                "migrated_from_legacy": True, "legacy_name": legacy.name,
                "legacy_path": FL.rel(legacy), "legacy_sha256": sha,
                "legacy_bytes": len(raw), "legacy_rows": split["source"]["rows"],
                "applied_at_utc": FL._iso(run),
                "source": {"path": FL.rel(legacy), **split["source"]},
                "streams_at_apply": files,
                "events_by_basis": split["events_by_basis"],
                "verification": {k: v for k, v in split["verification"].items()
                                 if k != "mismatches"},
                "legacy_chain_break": chain,
                "split_rule": ("open rows verbatim; terminal rows split into the forecast with "
                               "resolution fields reset to RESOLUTION_DEFAULTS (trailing non-core "
                               "resolution fields removed) and one event carrying exactly the "
                               "differing fields; fold == legacy row, verified row by row"),
                "legacy_file_policy": ("left byte-for-byte untouched and frozen: every writer "
                                       "goes to the streams after this marker; deleting it is a "
                                       "later cleanup decision"),
                "command": f"python -m scripts.ledger_split --apply --expect-sha256 {sha}",
            }
            FL.atomic_write_bytes(FL.marker_path(legacy),
                                  (json.dumps(marker, indent=1, ensure_ascii=False) + "\n")
                                  .encode("utf-8"))
            switched = True
        except BaseException:
            if not switched:
                for p in written:
                    p.unlink(missing_ok=True)
            raise
        seal = FL.seal_closed(legacy, now=run, apply=True,
                              provenance={"apply_command": marker["command"]})
        legacy_rows = [json.loads(s) for s in (ln.strip() for ln in FL._split_raw_lines(raw)) if s]
        now_rows = FL.read_rows(legacy)
        same = (len(now_rows) == len(legacy_rows)
                and all(FL.canonical_row_hash(a) == FL.canonical_row_hash(b)
                        for a, b in zip(now_rows, legacy_rows)))
        chain_now = FL.verify_chain(legacy, rehash=True)
        legacy_intact = FL.sha256_file(legacy) == sha
    return {"status": "APPLIED" if same and chain_now["status"] == "ok" and legacy_intact
            else "APPLIED_WITH_PROBLEMS",
            "marker": FL.rel(FL.marker_path(legacy)), "source_sha256": sha,
            "streams": files, "sealed": seal.get("sealed", []),
            "reader_rows_equal_legacy": same, "chain": chain_now["status"],
            "chain_problems": chain_now["problems"], "legacy_untouched": legacy_intact,
            "legacy_chain_break_status": chain.get("status"),
            "next": ("git add backend/data/optimus/forecasts backend/data/optimus/resolutions "
                     "backend/data/optimus/ledger_manifests/forecast_ledger && git commit")}


def discard_partial(legacy_path: Optional[Path] = None) -> dict:
    """Remove an interrupted `--apply`'s stream files and manifests. Refused
    once the marker exists: then the streams ARE the ledger."""
    legacy = Path(legacy_path) if legacy_path is not None else FL.default_legacy_path()
    with FL.ledger_lock(legacy.parent, purpose="ledger_split --discard-partial"):
        be = FL.backend_for(legacy)
        if be.kind == "streams":
            raise MigrationRefused("the migration marker exists: the streams are the ledger and "
                                   "are never discarded by this command")
        strays = _strays(be)
        for p in strays:
            p.unlink()
    return {"status": "DISCARDED" if strays else "NOTHING_TO_DISCARD",
            "removed": [FL.rel(p) for p in strays]}


def render_plan(p: dict) -> str:
    """The plan as a human reads it at the console."""
    if p.get("status") == "ALREADY_APPLIED":
        return f"ALREADY APPLIED: {p.get('reason')}"
    s = p["source"]
    lines = [f"LEDGER SPLIT PLAN ({p['migration_version']}, {p['utc']}) -- writes nothing",
             f"source:          {s['path']}",
             f"source sha256:   {s['sha256']}",
             f"source:          {s['bytes']:,} bytes, {s['lines']:,} lines, {s['rows']:,} rows "
             f"({s['crlf_lines']:,} CRLF, {s['blank_lines']} blank, {s['duplicate_ids']} duplicate ids, "
             f"{s['made_at_order_inversions']} made_at order inversions)",
             f"terminal rows:   {s['terminal']}  open rows: {s['open']:,}",
             "forecast streams (by made_at month):"]
    for f in p["forecast_streams"]:
        lines.append(f"  {f['month']}  {f['rows']:>7,} rows  {f['bytes']:>12,} B  "
                     f"{f['sha256'][:16]}  {f['file']}")
    lines.append("resolution streams (by resolved/voided month):")
    for f in p["resolution_streams"]:
        lines.append(f"  {f['month']}  {f['rows']:>7,} events {f['bytes']:>11,} B  "
                     f"{f['sha256'][:16]}  {f['file']}")
    lines.append(f"event month basis: {p['events_by_basis']}")
    m = p["manifest_plan"]
    lines += [f"manifest plan:   seal at apply {m['seal_at_apply']} (genesis {m['genesis']}); "
              f"left open {m['left_open']}; grace {m['grace_days']} day(s)",
              f"                 manifests in {m['manifest_dir']}; marker {m['marker']}"]
    v = p["verification"]
    lines.append(f"verification:    fold==legacy {v['fold_equals_legacy']:,}/{v['rows']:,}; "
                 f"canonical hash {v['canonical_hash_equal']:,}; key order {v['key_order_preserved']:,}; "
                 f"frozen fields {v['frozen_fields_identical']:,}; round trip "
                 f"{'EQUAL' if v['round_trip_equal'] else 'DIFFERS'} / order "
                 f"{'EQUAL' if v['round_trip_order_equal'] else 'DIFFERS'}  -> "
                 f"{'OK' if v['ok'] else 'FAILED'}")
    c = p["legacy_chain_break"]
    lines.append(f"legacy row chain: {c['status']} -- first mismatch line "
                 f"{c['first_mismatch_line']}; chain fields {c['chain_fields_found'] or 'none'}; "
                 f"hash fields present {c['hash_fields_present']}")
    gh = c.get("git_history")
    if gh:
        if gh.get("status") == "NOT_COMPUTED":
            lines.append(f"git history:     NOT COMPUTED ({gh.get('reason')})")
        else:
            fb = gh.get("first_byte_discontinuity") or {}
            lines.append(f"git history:     {gh['status']} over {gh['versions']} committed versions "
                         f"({gh['first_commit']}..{gh['last_commit']}, shallow={gh['shallow_clone']}); "
                         f"totals {gh['totals']}")
            if fb:
                lines.append(f"  first byte discontinuity: {fb['commit']} ({fb['committed_at']}) line "
                             f"{fb['line']}: {fb['classification']}; expected line sha256 "
                             f"{fb['previous_line_sha256'][:16]}, found {fb['found_line_sha256'][:16]}")
    if p.get("blocking"):
        lines.append(f"BLOCKED: {p['blocking']}")
    lines.append(f"next (attended, writers stopped): {p['next']}")
    return "\n".join(lines)

