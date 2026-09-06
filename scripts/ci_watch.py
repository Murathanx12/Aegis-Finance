"""ci_watch -- the last N GitHub Actions runs for this repo, from the PUBLIC API.

No token, no `gh`. Prints one line per run (sha, status, conclusion, when,
per-step conclusions for the backend job) so a session can answer "is CI
green on what I just pushed?" in one call instead of waiting for an e-mail.

Why this exists (2026-09-06): finance CI was red for two days across eleven
pushes and nobody in a session noticed, because the only surface was GitHub's
notification e-mail. The public API is rate-limited to 60 calls/hour
unauthenticated; this script makes 1 + N calls, so poll at the cadence the
data changes (a run takes ~10 min), never in a tight loop.

Usage:
    python -m scripts.ci_watch                 # last 5 runs
    python -m scripts.ci_watch --n 10
    python -m scripts.ci_watch --sha 0866945   # the run(s) for one commit
    python -m scripts.ci_watch --wait          # poll every 90s until the newest run finishes (max 20 min)

Exit code: 0 if the newest completed run succeeded, 1 if it failed, 2 if the
API was unreachable (a rate limit reads as absence -- say so, never guess).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

REPO = "Murathanx12/Aegis-Finance"
API = f"https://api.github.com/repos/{REPO}/actions"
UA = {"User-Agent": "aegis-ci-watch/1.0", "Accept": "application/vnd.github+json"}


def _get(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            print(f"RATE LIMITED or forbidden ({e.code}) -- the API said nothing; that is not a verdict", file=sys.stderr)
        else:
            print(f"HTTP {e.code} from {url}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"unreachable: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def runs(n: int, sha: str | None) -> list[dict]:
    d = _get(f"{API}/runs?per_page={max(n, 10)}")
    if not d:
        return []
    out = d.get("workflow_runs", [])
    if sha:
        out = [r for r in out if r["head_sha"].startswith(sha)]
    return out[:n]


def steps(run_id: int) -> list[str]:
    d = _get(f"{API}/runs/{run_id}/jobs")
    if not d:
        return ["(jobs unavailable)"]
    lines = []
    for j in d.get("jobs", []):
        bad = [s["name"] for s in j.get("steps", []) if s.get("conclusion") not in (None, "success", "skipped")]
        lines.append(f"  {j['name']}: {j.get('conclusion')}" + (f" -- failed steps: {bad}" if bad else ""))
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--sha", default=None)
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args(argv)

    deadline = time.time() + 20 * 60
    while True:
        rs = runs(a.n, a.sha)
        if not rs:
            return 2
        for r in rs:
            print(f"{r['head_sha'][:7]}  {r['status']:<12} {str(r['conclusion']):<9} {r['created_at']}  {r['name']}")
        newest = rs[0]
        if newest["status"] == "completed" or not a.wait or time.time() > deadline:
            break
        print("... newest run still in progress; polling again in 90s")
        time.sleep(90)

    newest = rs[0]
    if newest["status"] == "completed":
        for ln in steps(newest["id"]):
            print(ln)
        return 0 if newest["conclusion"] == "success" else 1
    print("newest run not finished; no verdict")
    return 1


if __name__ == "__main__":
    sys.exit(main())
