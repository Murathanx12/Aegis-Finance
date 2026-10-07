"""THE THREE FRONTEND BUILDS, IN ONE RECEIPT WITH THREE EXIT CODES.

    python -m scripts.frontend_check                 # all three
    python -m scripts.frontend_check --skip site     # e.g. desktop-only
    python -m scripts.frontend_check --out r.json

WHY THIS IS ONE COMMAND AND NOT THREE HABITS
============================================
`frontend/` has THREE ways to be wrong and they do not agree with each other:

* `npx tsc --noEmit` -- types only, no bundling, no route analysis;
* `npx next build` -- the SITE build, which does the full route/page analysis;
* `AEGIS_DESKTOP_BUILD=1 npx next build` -- the STATIC EXPORT the desktop app
  serves, which takes a different code path and tolerates things the site build
  refuses.

On 2026-09-11 the last one passed and the first two did not: two board cards
each defined `STATUS_TONE`, the desktop export swallowed the duplicate and the
site build rejected it, and CI went red on the merge (`bf6de3e`). The launcher
only ever ran the export, so nothing local could have caught it -- which is why
`desktop.launcher.maybe_frontend` now calls THIS, and why the receipt carries
all three return codes rather than the one that happened to be run.

The order matters and is not arbitrary. The desktop export runs LAST, so
`frontend/out` is left holding the export the desktop app serves rather than
whatever the site build wrote over it.

Exit code: 0 only when every step that ran returned 0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"
#: the latest run. One file, overwritten: this is a gate, not a time series.
DEFAULT_RECEIPT = REPO / "backend" / "data" / "optimus" / "frontend_check.json"

#: (name, argv after `npx`, extra env, what it catches)
STEPS: list[tuple[str, list[str], dict, str]] = [
    ("tsc", ["tsc", "--noEmit"], {},
     "type errors, with no bundling and no route analysis"),
    ("site", ["next", "build"], {},
     "the site build -- full route and page analysis; refuses duplicates the export tolerates"),
    ("desktop", ["next", "build"], {"AEGIS_DESKTOP_BUILD": "1"},
     "the static export the desktop app serves; runs LAST so frontend/out is left holding it"),
]

#: a cold `next build` on this machine is well under this; the cap only exists
#: so a hung build fails loudly instead of holding a launch open forever.
STEP_TIMEOUT_S = float(os.getenv("AEGIS_FRONTEND_CHECK_TIMEOUT_S", "1800"))


# ------------------------------------------------------------------ Q18 guard
#
# 2026-10-07: the live site's console printed, on every page,
# `[aegis] NEXT_PUBLIC_API_URL is not an absolute http(s) URL (got 11 chars
# starting "[")`. `vercel env ls` showed the Project variable set to the real
# Railway URL -- but Vercel's CLI REDACTS a variable marked "Sensitive" to the
# literal 11-character string "[SENSITIVE]" on `vercel pull` / `vercel env
# pull`, and because `NEXT_PUBLIC_*` is inlined by webpack at build time,
# `vercel build` compiled that placeholder straight into the browser bundle.
# The site stayed up only because `frontend/src/lib/api.ts`'s `resolveApiBase`
# (C4, 2026-10-06) refused the bad value and fell back to
# `PUBLIC_API_FALLBACK` -- the same URL this guard checks for below. That
# fallback is a mercy, not a fix: it is why this shipped broken for a full day
# with every request still answering.
#
# The fix is the workflow's Build step setting `NEXT_PUBLIC_API_URL` directly
# (see `.github/workflows/deploy-frontend-vercel.yml`), which wins over
# whatever `vercel pull` wrote. This guard exists for the regression: the only
# way the placeholder comes back is `vercel pull` writing it again and
# something reading that file instead of the explicit env var.
API_URL_REDACTION_PLACEHOLDER = "[SENSITIVE]"

#: the public production API host every build must inline. NOT a secret --
#: it is the URL README.md lists as "Live" and `PUBLIC_API_FALLBACK` in
#: `frontend/src/lib/api.ts`. Kept as a literal here (this file cannot import
#: TypeScript); `test_frontend_check_api_url.py` pins it equal to that
#: fallback and to the workflow's Build-step env var so the three cannot
#: drift apart silently.
EXPECTED_API_URL = "https://aegis-finance-production.up.railway.app"
EXPECTED_API_HOST = "aegis-finance-production.up.railway.app"


def guard_bundle_for_redacted_api_url(bundle_dir: Path) -> dict:
    """Grep every emitted `.js` chunk under `bundle_dir` for the Vercel CLI's
    redaction placeholder and for the Railway host string. Pure function of
    the filesystem -- never raises, never runs a build. A missing directory
    or a directory with no `.js` files is CANNOT DETERMINE, not a pass: a
    guard that reports green for nothing to scan is the same broken shape as
    `check()`'s own "no Node on PATH" case above.
    """
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        return {"ok": None, "verdict": "CANNOT DETERMINE",
                "reason": f"no bundle directory at {bundle_dir}",
                "files_scanned": 0, "placeholder_hits": [], "host_found": False}
    js_files = sorted(bundle_dir.rglob("*.js"))
    placeholder_hits: list[str] = []
    host_found = False
    for f in js_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if API_URL_REDACTION_PLACEHOLDER in text:
            placeholder_hits.append(str(f.relative_to(bundle_dir)))
        if EXPECTED_API_HOST in text:
            host_found = True
    if not js_files:
        return {"ok": None, "verdict": "CANNOT DETERMINE",
                "reason": f"no .js files under {bundle_dir}",
                "files_scanned": 0, "placeholder_hits": [], "host_found": False}
    ok = not placeholder_hits and host_found
    if placeholder_hits:
        reason = f"redaction placeholder {API_URL_REDACTION_PLACEHOLDER!r} found in {len(placeholder_hits)} file(s)"
    elif not host_found:
        reason = f"Railway host {EXPECTED_API_HOST!r} not found in any built chunk"
    else:
        reason = "ok"
    return {"ok": ok, "verdict": "GREEN" if ok else "RED", "reason": reason,
            "files_scanned": len(js_files), "placeholder_hits": placeholder_hits,
            "host_found": host_found}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_step(name: str, argv: list[str], extra_env: dict, npx: str,
             cwd: Path) -> dict:
    t0 = time.time()
    env = {**os.environ, **extra_env}
    row = {"step": name, "cmd": f"npx {' '.join(argv)}",
           "env": (" ".join(f"{k}={v}" for k, v in extra_env.items()) or None)}
    try:
        # ENCODING IS NOT OPTIONAL HERE. `text=True` decodes with the console
        # code page, which on this machine is cp1252, and `next build` draws
        # box characters: the first real run of this script raised
        # `UnicodeDecodeError` inside subprocess's reader THREAD, which does not
        # propagate -- the build was reported correctly and its output was gone.
        # A checker whose tail is empty exactly when a build is red is no
        # checker at all.
        r = subprocess.run([npx, *argv], cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=STEP_TIMEOUT_S, env=env, check=False)
    except subprocess.TimeoutExpired:
        return row | {"returncode": None, "seconds": round(time.time() - t0, 2),
                      "ok": False, "error": f"timed out after {STEP_TIMEOUT_S:.0f}s"}
    except (OSError, subprocess.SubprocessError) as exc:
        return row | {"returncode": None, "seconds": round(time.time() - t0, 2),
                      "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    # tsc writes its errors to STDOUT, next writes most of its to STDERR, so a
    # tail of one of them is a tail of nothing half the time.
    tail = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
    return row | {"returncode": r.returncode, "seconds": round(time.time() - t0, 2),
                  "ok": r.returncode == 0, "tail": tail[-1500:]}


def check(*, root: Path = REPO, skip: tuple[str, ...] = (),
          receipt_path: Path | None = None) -> dict:
    """Run the three builds and return the receipt. Never raises for a red build."""
    frontend = root / "frontend"
    receipt: dict = {"receipt": "frontend_check", "utc": _now(),
                     "licence": "PRODUCT_EXPERIMENT", "frontend": str(frontend),
                     "steps": [], "skipped": list(skip)}
    npx = shutil.which("npx")
    if not frontend.is_dir():
        receipt.update({"ok": None, "verdict": "CANNOT DETERMINE",
                        "headline": f"no frontend directory at {frontend}"})
    elif npx is None:
        # CANNOT DETERMINE, not FAILED: no Node is not a red frontend, and a
        # gate that reports red for its own missing tool teaches the reader to
        # skim red lines.
        receipt.update({"ok": None, "verdict": "CANNOT DETERMINE",
                        "headline": "Node/npx is not on PATH, so nothing was checked"})
    else:
        for name, argv, extra, why in STEPS:
            if name in skip:
                receipt["steps"].append({"step": name, "ok": None, "returncode": None,
                                         "reason": "skipped", "catches": why})
                continue
            row = run_step(name, argv, extra, npx, frontend)
            row["catches"] = why
            receipt["steps"].append(row)
        ran = [s for s in receipt["steps"] if s.get("reason") != "skipped"]
        bad = [s["step"] for s in ran if not s.get("ok")]
        receipt["exit_codes"] = {s["step"]: s.get("returncode") for s in receipt["steps"]}
        receipt["ok"] = not bad and bool(ran)
        receipt["verdict"] = "GREEN" if receipt["ok"] else ("RED" if bad else "CANNOT DETERMINE")
        receipt["headline"] = (
            f"{len(ran)} build(s) green in "
            f"{sum(s.get('seconds') or 0 for s in ran):.0f}s" if receipt["ok"] else
            f"RED: {', '.join(bad)}" if bad else "nothing ran")
    p = Path(receipt_path) if receipt_path else DEFAULT_RECEIPT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    receipt["receipt_path"] = str(p)
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tsc + site build + desktop export, one receipt")
    ap.add_argument("--skip", action="append", default=[],
                    choices=[s[0] for s in STEPS], help="skip a step (repeatable)")
    ap.add_argument("--out", default=None, help="where to write the receipt")
    ap.add_argument("--guard-api-url-dir", default=None, metavar="DIR",
                    help="run ONLY the Q18 redaction-placeholder guard against this already-"
                         "built bundle directory (e.g. frontend/.vercel/output/static after "
                         "`vercel build`, or frontend/.next after a local `next build`) and "
                         "exit -- skips the three builds entirely")
    a = ap.parse_args(argv)
    if a.guard_api_url_dir:
        guard = guard_bundle_for_redacted_api_url(Path(a.guard_api_url_dir))
        print(f"api-url guard: {guard['verdict']} -- {guard['reason']} "
              f"({guard['files_scanned']} .js file(s) scanned)")
        for hit in guard["placeholder_hits"]:
            print(f"  PLACEHOLDER FOUND: {hit}")
        return 0 if guard["ok"] else 1
    r = check(skip=tuple(a.skip), receipt_path=Path(a.out) if a.out else None)
    for s in r["steps"]:
        code = s.get("returncode")
        mark = {True: "ok", False: "FAIL", None: "--"}[s.get("ok")]
        print(f"  {s['step']:8s} {mark:5s} exit {str(code):5s} "
              f"{s.get('seconds', '--')}s  {s.get('error') or ''}")
    print(f"{r['verdict']}: {r['headline']}")
    print(f"receipt -> {r['receipt_path']}")
    for s in r["steps"]:
        if s.get("ok") is False and s.get("tail"):
            print(f"\n--- {s['step']} ---\n{s['tail']}")
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
