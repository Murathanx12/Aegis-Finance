"""Which fields does this system WRITE and never READ?

    python -m scripts.write_only_telemetry_audit
    python -m scripts.write_only_telemetry_audit --min-occurrences 3

Writes `docs/WRITE_ONLY_TELEMETRY.md` and
`backend/data/optimus/write_only_telemetry.json`.

WHY (Order 17 Track F, Order 18 §3.5)
======================================
`decision_lag_minutes` was written onto every IIF-1 receipt and read by
NOTHING. It was not wrong; it was inert. That matters twice over:

  * as DEAD WEIGHT it is harmless but misleading — a receipt carrying a field
    reads as a system that checks that field;
  * as a MISSING CHECK it is the whole failure, and this is the case that
    actually happened. The two clocks that a launch guard needed were sitting
    on disk, on every receipt, the entire time. Nobody had connected them,
    so the guard was calibrated on the wrong one.

A field written and never read is therefore not a tidiness problem. It is a
question that was measured and never asked, and the audit exists to list them
so each one gets a decision: WIRE IT UP, or DELETE IT. Leaving it is the only
wrong answer, because inert telemetry looks exactly like working telemetry.

HOW THE READ SIDE IS DETERMINED, AND ITS LIMIT
-----------------------------------------------
A field counts as READ if its name appears anywhere in the Python sources
outside of the places that write it — subscript, `.get()`, attribute access,
f-string, or a bare string constant. That is deliberately GENEROUS: a false
"read" makes this audit quieter, and a quiet audit is the safe direction for a
tool whose output is a work list rather than a gate.

Tests are counted SEPARATELY. A field read only by the test that asserts it was
written is still write-only in production — the test proves the writer works,
not that anything consumes it. That distinction is the point of the report's
third column, and `decision_lag_minutes` had exactly that shape.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_JSON = REPO / "backend" / "data" / "optimus" / "write_only_telemetry.json"
OUT_DOC = REPO / "docs" / "WRITE_ONLY_TELEMETRY.md"

#: Where receipts and records live. These are the files whose keys are the
#: telemetry surface — the things this system tells itself about its own runs.
RECORD_GLOBS = (
    "docs/receipts/*.json",
    "backend/data/optimus/*.json",
    "backend/data/optimus/iif1_nights/*.json",
    "backend/data/optimus/iif1_launches/*.json",
    "docs/conviction_replay/*.json",
)

SOURCE_GLOBS = ("backend/**/*.py", "scripts/**/*.py", "engine/**/*.py",
                "lab/**/*.py")

#: Keys that are structural rather than telemetry: they carry the record's
#: identity, not a measurement, and "nothing reads it" is not a finding for a
#: field whose job is to be human-readable in the file.
STRUCTURAL = frozenset({
    "note", "notes", "receipt", "basis", "generated_by", "trial", "run_at",
    "description", "comment", "version", "schema", "_comment", "interpretation",
    "may_not_conclude", "reason", "label", "title", "summary",
})


def _keys_of(obj, prefix="", depth=0, out=None):
    """Every key in a record, flattened, to a bounded depth."""
    out = out if out is not None else Counter()
    if depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            out[k] += 1
            _keys_of(v, prefix, depth + 1, out)
    elif isinstance(obj, list):
        for v in obj[:20]:
            _keys_of(v, prefix, depth + 1, out)
    return out


def _load_records() -> tuple[Counter, dict[str, set[str]]]:
    written: Counter = Counter()
    where: dict[str, set[str]] = {}
    for pat in RECORD_GLOBS:
        for p in REPO.glob(pat):
            if p.stat().st_size > 40_000_000:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                continue
            keys = _keys_of(data)
            for k, n in keys.items():
                written[k] += n
                where.setdefault(k, set()).add(
                    str(p.relative_to(REPO)).replace("\\", "/"))
    return written, where


def _read_sites(names: set[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Count where each name appears in sources, split prod vs tests."""
    prod: Counter = Counter()
    tests: Counter = Counter()
    pats = {n: re.compile(r"\b" + re.escape(n) + r"\b") for n in names}
    for pat in SOURCE_GLOBS:
        for p in REPO.glob(pat):
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if "__pycache__" in rel:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:                                  # noqa: BLE001
                continue
            is_test = "/tests/" in rel or rel.split("/")[-1].startswith("test_")
            for n, rx in pats.items():
                c = len(rx.findall(text))
                if not c:
                    continue
                if is_test:
                    tests[n] += c
                else:
                    prod[n] += c
    return dict(prod), dict(tests)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="write_only_telemetry_audit")
    ap.add_argument("--min-occurrences", type=int, default=1,
                    help="ignore keys appearing fewer times than this across "
                         "all records. DEFAULT 1, and the default matters: at "
                         "2 this audit silently dropped `decision_lag_minutes` "
                         "— the very field it was built for — because it "
                         "appears on exactly one receipt. A threshold that "
                         "excludes the motivating case is a threshold chosen "
                         "against the wrong world.")
    ap.add_argument("--self-check", action="store_true", default=True,
                    help="assert the audit can still see its own motivating "
                         "case; disable only if that receipt is removed")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    written, where = _load_records()
    candidates = {k for k, n in written.items()
                  if n >= a.min_occurrences and k not in STRUCTURAL
                  and not k.startswith("_")}
    excluded = sorted(k for k, n in written.items()
                      if n < a.min_occurrences and k not in STRUCTURAL
                      and not k.startswith("_"))

    # The audit's own motivating case, used as a canary. `decision_lag_minutes`
    # is written on exactly one receipt, so any threshold above 1 hides it —
    # and it is the field this whole audit exists because of. If the canary
    # goes missing the audit is reporting a smaller world than it claims.
    canary = "decision_lag_minutes"
    canary_visible = canary in candidates or canary not in written
    if a.self_check and canary in written and canary not in candidates:
        print(f"SELF-CHECK FAILED: `{canary}` is written but excluded at "
              f"--min-occurrences {a.min_occurrences}. That is the exact field "
              f"this audit was built for. Lower the threshold or the audit is "
              f"quietly reporting a smaller world than it claims.")
        return 2

    prod, tests = _read_sites(candidates)

    rows = []
    for k in sorted(candidates):
        # The writer itself always mentions the name, so one production
        # occurrence is the write. Two or more means something else refers
        # to it — generously counted as a read.
        p = prod.get(k, 0)
        t = tests.get(k, 0)
        if p >= 2:
            verdict = "read"
        elif t > 0:
            verdict = "TEST_ONLY"
        else:
            verdict = "WRITE_ONLY"
        rows.append({"field": k, "times_written": written[k],
                     "prod_mentions": p, "test_mentions": t,
                     "verdict": verdict,
                     "files": sorted(where.get(k, ()))[:4]})

    write_only = [r for r in rows if r["verdict"] == "WRITE_ONLY"]
    test_only = [r for r in rows if r["verdict"] == "TEST_ONLY"]

    print("=" * 74)
    print("WRITE-ONLY TELEMETRY AUDIT")
    print("=" * 74)
    print(f"  record fields examined   {len(rows)}")
    print(f"  WRITE_ONLY (nothing reads them)   {len(write_only)}")
    print(f"  TEST_ONLY  (only a test reads them) {len(test_only)}")
    if excluded:
        print(f"  excluded by --min-occurrences {a.min_occurrences}: "
              f"{len(excluded)} (NAMED in the JSON, never silently dropped)")
    print(f"  canary `{canary}` visible: {canary_visible}")
    print()
    for r in write_only[:40]:
        print(f"  WRITE_ONLY  {r['field']:38s} written {r['times_written']:5d}x"
              f"  {r['files'][0] if r['files'] else ''}")
    if test_only:
        print()
        for r in test_only[:25]:
            print(f"  TEST_ONLY   {r['field']:38s} written "
                  f"{r['times_written']:5d}x  tests {r['test_mentions']}")

    payload = {
        "audit": "WRITE-ONLY TELEMETRY",
        "min_occurrences": a.min_occurrences,
        "n_examined": len(rows),
        "n_write_only": len(write_only),
        "n_test_only": len(test_only),
        "n_excluded_by_threshold": len(excluded),
        "excluded_by_threshold": excluded[:50],
        "canary_field": canary,
        "canary_visible": bool(canary_visible),
        "rows": rows,
        "method": ("a field counts as READ on 2+ production mentions, which is "
                   "deliberately generous: the writer itself is one mention, "
                   "and a false 'read' makes this audit quieter, which is the "
                   "safe direction for a work list"),
        "why": ("decision_lag_minutes sat on every IIF-1 receipt and was read "
                "by nothing; the two clocks a launch guard needed were on disk "
                "the whole time and the guard was calibrated on the wrong one"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUT_DOC.write_text(_render(payload), encoding="utf-8")
    print(f"\nwrote {OUT_JSON.relative_to(REPO)}")
    print(f"wrote {OUT_DOC.relative_to(REPO)}")
    return 0


def _render(p: dict) -> str:
    L = ["# Write-only telemetry — measured, never asked", ""]
    A = L.append
    A("Generated by `scripts/write_only_telemetry_audit.py`. Regenerate rather")
    A("than edit.")
    A("")
    A("A field written and never read is not a tidiness problem. It is a")
    A("question that was **measured and never asked**. `decision_lag_minutes`")
    A("was on every IIF-1 receipt and read by nothing — and the two clocks a")
    A("launch guard needed were sitting on disk the entire time, which is why")
    A("the guard ended up calibrated on the wrong one.")
    A("")
    A("Each row below needs a decision: **wire it up, or delete it.** Leaving")
    A("it is the only wrong answer, because inert telemetry looks exactly like")
    A("working telemetry.")
    A("")
    A(f"- fields examined: **{p['n_examined']}**")
    A(f"- WRITE_ONLY: **{p['n_write_only']}**")
    A(f"- excluded by threshold: **{p['n_excluded_by_threshold']}** (named in")
    A("  the JSON — a silent exclusion is how this audit first hid its own")
    A(f"  motivating case, `{p['canary_field']}`)")
    A(f"- TEST_ONLY: **{p['n_test_only']}** — a test asserting the field was")
    A("  written proves the WRITER works, not that anything consumes it.")
    A("  `decision_lag_minutes` had exactly this shape.")
    A("")
    A("*Method: " + p["method"] + ".*")
    A("")
    for verdict, heading in (("WRITE_ONLY", "## Nothing reads these"),
                             ("TEST_ONLY", "## Only a test reads these")):
        rows = [r for r in p["rows"] if r["verdict"] == verdict]
        if not rows:
            continue
        A(heading)
        A("")
        A("| field | times written | prod mentions | test mentions | seen in |")
        A("|---|---:|---:|---:|---|")
        for r in sorted(rows, key=lambda x: -x["times_written"]):
            A(f"| `{r['field']}` | {r['times_written']} | {r['prod_mentions']} "
              f"| {r['test_mentions']} | "
              f"{'`' + r['files'][0] + '`' if r['files'] else '—'} |")
        A("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
