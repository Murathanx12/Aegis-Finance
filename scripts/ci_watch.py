"""ci_watch -- the last N GitHub Actions runs for this repo, from the PUBLIC API.

No token, no `gh`. Prints one line per run (sha, status, conclusion, when,
per-step conclusions + failure annotations for the backend job) so a session
can answer "is CI green on what I just pushed?" in one call instead of
waiting for an e-mail.

Why this exists (2026-09-06): finance CI was red for two days across eleven
pushes and nobody in a session noticed, because the only surface was GitHub's
notification e-mail. The public API is rate-limited to 60 calls/hour
unauthenticated; this script makes a handful of calls, so poll at the cadence
the data changes (a run takes ~20-25 min), never in a tight loop.

REWRITTEN 2026-10-07 (Q16) -- the watcher reported a false negative TWICE in
one day, and this file is the receipt for why, each root cause reproduced
against the live API before being fixed:

  1. PICKING "NEWEST RUN" BY LIST INDEX ACROSS WORKFLOWS. For commit
     92f147f6, the API returns BOTH "CI" and "Deploy frontend to Vercel" runs
     for the same head_sha, same `created_at` second. `rs[0]` was whichever
     one the API happened to list first -- CI's own status was invisible
     behind an unrelated workflow. Fixed: select the run named CI_WORKFLOW_NAME
     explicitly; print the others as "(other workflow, not the verdict)".

  2. THE 20-MINUTE WAIT WINDOW WAS SHORTER THAN CI'S OWN MEASURED DURATION.
     e041ec14's CI run took 05:42:46 -> 06:03:55 (~21 min); 92f147f6's took
     04:37:17 -> 05:01:36 (~24 min). A 20-minute deadline guarantees a timeout
     on a run that is about to go green. Fixed: WAIT_MINUTES = 40.

  3. CLIENT-SIDE FILTERING OF A REPO-WIDE, ALL-WORKFLOWS PAGE instead of the
     API's own `head_sha` filter. The old code fetched `?per_page=10` (every
     workflow, newest-first, repo-wide) and filtered in Python -- fragile
     under pagination and wasteful. Fixed: query `?head_sha=<full sha>`
     directly; verified live that it returns exactly the runs for that commit
     (`total_count: 1` for e041ec14, `total_count: 2` -- CI + Vercel -- for
     92f147f6).

  4. THE head_sha FILTER REQUIRES THE FULL 40-CHAR SHA. The old default
     truncated to 7 chars for display (`[:7]`) and then used that truncated
     value for lookups too. Verified live: `?head_sha=<7-char prefix>` returns
     `total_count: 0` even for a sha that has a run under the full hash. Fixed:
     resolve and use the FULL sha throughout; the 7-char form is for display
     only.

  5. THE DOMINANT ROOT CAUSE, FOUND BY RE-RUNNING THE EXACT FAILING CALL: the
     "e041ec14" watch never passed `--sha`, so it defaulted to `git rev-parse
     HEAD` on branch `wip/2026-10-07-day` -- which resolved to `0b6655f3`, a
     DIFFERENT commit with the identical commit message, built from an
     earlier parent (`92f147f6` directly, skipping intervening commits).
     `0b6655f3` lives ONLY on `wip/2026-10-07-day` (confirmed:
     `git branch --contains` lists only that branch); `e041ec14` -- the commit
     that was actually pushed to `main` and went green 20 minutes before the
     watcher gave up -- lives ONLY on `main`. `.github/workflows/ci.yml`
     triggers on `push: branches: [main]` and `pull_request: branches: [main]`
     ONLY, so `0b6655f3` can structurally never get a CI run: querying
     `?head_sha=<0b6655f3's full sha>` returns `total_count: 0`, confirmed
     live, no matter how long the watcher waits. The 20-minute poll was a
     correct, if confusing, answer to the wrong question. Fixed: before
     waiting, check whether the resolved sha is reachable from `origin/main`
     or is the head of an open PR into main; if neither, REFUSE immediately
     (EXIT_NEVER_TRIGGERS) instead of polling for up to 40 minutes against a
     commit that cannot ever produce a run. This is the same family as the
     repo's "a gate that cannot go green is a broken gate" rule -- a watcher
     that cannot ever see a verdict must say so in one call, not time out.

Usage:
    python -m scripts.ci_watch                 # last runs for HEAD
    python -m scripts.ci_watch --n 10
    python -m scripts.ci_watch --sha 0866945    # the run(s) for one commit
    python -m scripts.ci_watch --wait           # poll until the CI run finishes (default 40 min)
    python -m scripts.ci_watch --wait --wait-minutes 60

Exit codes (one situation each -- do not collapse these back into "0 vs
nonzero"; that is the bug this rewrite fixes):
    0  the CI run completed successfully
    1  the CI run completed with a failure (job/step/annotations printed)
    2  the GitHub API was unreachable or rate-limited -- not a verdict
    3  the resolved commit can never trigger CI from here (not on main, no
       open PR into main) -- refused before waiting, see root cause #5 above
    4  waited the full window and GitHub never created a CI run for this sha
       (eventual consistency / wrong sha / workflow renamed)
    5  a CI run exists and is still queued/in_progress when the wait window
       closes (the run itself may still go green or red after this exits)
    6  could not resolve the given ref to a full 40-char sha
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "Murathanx12/Aegis-Finance"
OWNER = REPO.split("/")[0]
API = f"https://api.github.com/repos/{REPO}"
ACTIONS = f"{API}/actions"
UA = {"User-Agent": "aegis-ci-watch/1.0", "Accept": "application/vnd.github+json"}

#: The workflow whose conclusion IS the verdict. Other workflows (Vercel
#: deploy, the GDELT canary, the prod monitor) can share a head_sha and must
#: never be mistaken for it (root cause #1 above).
CI_WORKFLOW_NAME = "CI"

#: Measured 2026-10-07 across two runs: ~21 and ~24 minutes. 40 min is margin,
#: not the measured figure, because a 25-min run plus poll latency plus a
#: slightly slower day must not re-create the same false timeout.
WAIT_MINUTES = 40
POLL_SECONDS = 90

EXIT_SUCCESS = 0
EXIT_CI_FAILED = 1
EXIT_API_UNREACHABLE = 2
EXIT_NEVER_TRIGGERS = 3
EXIT_NO_RUN_APPEARED = 4
EXIT_TIMED_OUT_IN_PROGRESS = 5
EXIT_BAD_REF = 6


def _get(url: str) -> dict | list | None:
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


def _git(args: list[str]) -> str | None:
    """Best-effort local git call. Returns stripped stdout, or None on any
    failure (missing ref, not a repo, git not on PATH, timeout) -- callers
    must treat None as "don't know", never as a negative answer."""
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)  # noqa: S603,S607
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def resolve_full_sha(ref: str) -> str | None:
    """`git rev-parse <ref>`, full 40-char form. The GitHub `head_sha` query
    param requires the full hash -- a 7-char prefix silently returns
    `total_count: 0` (verified live 2026-10-07), so a short sha must never be
    sent to the API even though it is fine for on-screen display."""
    out = _git(["rev-parse", ref])
    if out and len(out) == 40:
        return out
    return None


def current_branch() -> str | None:
    return _git(["branch", "--show-current"])  # empty/None on detached HEAD


def sha_is_on_main(sha: str) -> bool | None:
    """True/False only when git can actually answer from local knowledge
    (requires a fetched `origin/main`); None means "can't tell", which must
    never be treated as a refusal -- only a confirmed False does."""
    try:
        r = subprocess.run(  # noqa: S603,S607
            ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
            capture_output=True, timeout=10,
        )
    except Exception:  # noqa: BLE001
        return None
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    return None


def open_pr_for_branch(branch: str) -> dict | None:
    d = _get(f"{API}/pulls?head={OWNER}:{branch}&state=open&per_page=5")
    if isinstance(d, list) and d:
        return d[0]
    return None


def ci_can_ever_run(sha: str) -> tuple[bool, str]:
    """Root cause #5: `.github/workflows/ci.yml` triggers ONLY on
    `push: branches: [main]` and `pull_request: branches: [main]`. A commit
    that is neither reachable from `origin/main` nor the head of an open PR
    into main will NEVER get a CI run, no matter how long this waits.
    Returns (can_run_or_unknown, human reason) -- unknown reads as True so a
    stale/missing local `origin/main` never produces a false refusal."""
    on_main = sha_is_on_main(sha)
    if on_main is not False:
        return True, "reachable from origin/main (or undetermined locally)"
    branch = current_branch()
    if branch:
        pr = open_pr_for_branch(branch)
        if pr:
            return True, f"open PR #{pr['number']} ({pr.get('html_url')}) into main"
    return False, (
        f"{sha[:7]} is not reachable from origin/main and "
        f"{'branch ' + repr(branch) + ' has no open PR into main' if branch else 'HEAD is detached with no open PR'}. "
        "ci.yml triggers only on push/PR to main -- this sha can never get a CI run from here."
    )


def runs_for_sha(sha: str) -> list[dict] | None:
    """The API's own filter, not a client-side scan of a repo-wide page
    (root cause #3). `None` means the API call itself failed; `[]` means it
    succeeded and found nothing (yet)."""
    d = _get(f"{ACTIONS}/runs?head_sha={sha}&per_page=30")
    if d is None:
        return None
    return d.get("workflow_runs", [])


def check_run_annotations(check_run_id: int) -> list[dict]:
    d = _get(f"{API}/check-runs/{check_run_id}/annotations")
    return d if isinstance(d, list) else []


def steps_with_annotations(run_id: int) -> list[str]:
    """Per-job conclusion, and for any job that did not succeed, the
    check-run annotations (file:line + message) from the PUBLIC
    `/check-runs/{id}/annotations` endpoint -- GitHub Actions job ids and
    Checks-API check-run ids are the same number, verified live 2026-10-07,
    so no extra lookup is needed to go from a job to its annotations."""
    d = _get(f"{ACTIONS}/runs/{run_id}/jobs")
    if not d:
        return ["  (jobs unavailable)"]
    lines: list[str] = []
    for j in d.get("jobs", []):
        bad_steps = [s["name"] for s in j.get("steps", []) if s.get("conclusion") not in (None, "success", "skipped")]
        lines.append(f"  {j['name']}: {j.get('conclusion')}" + (f" -- failed steps: {bad_steps}" if bad_steps else ""))
        if j.get("conclusion") not in (None, "success", "skipped"):
            for ann in check_run_annotations(j["id"]):
                if ann.get("annotation_level") == "failure":
                    where = f"{ann.get('path')}:{ann.get('start_line')}"
                    lines.append(f"    [{where}] {ann.get('message')}")
    return lines


def select_ci_run(all_runs: list[dict]) -> tuple[dict | None, list[dict]]:
    """Split the runs for a sha into (the CI run, every other workflow's
    run) -- never let the latter stand in for the former (root cause #1)."""
    ci_runs = [r for r in all_runs if r.get("name") == CI_WORKFLOW_NAME]
    others = [r for r in all_runs if r.get("name") != CI_WORKFLOW_NAME]
    if not ci_runs:
        return None, others
    # Re-runs share a head_sha; the most recently started attempt is the verdict.
    ci_runs.sort(key=lambda r: r.get("run_started_at") or r.get("created_at") or "", reverse=True)
    return ci_runs[0], others


def watch(sha: str, wait: bool, wait_minutes: int) -> int:
    can_run, reason = ci_can_ever_run(sha)
    if not can_run:
        print(f"REFUSING to wait: {reason}")
        print("Pass the sha that IS on main (e.g. `git rev-parse origin/main`), or open a PR for this branch.")
        return EXIT_NEVER_TRIGGERS

    deadline = time.time() + wait_minutes * 60
    while True:
        all_runs = runs_for_sha(sha)
        if all_runs is None:
            return EXIT_API_UNREACHABLE
        ci_run, others = select_ci_run(all_runs)
        for r in others:
            print(f"  (other workflow, not the verdict) {r['name']:<28} {r['status']:<12} {str(r['conclusion']):<9} {r['created_at']}")
        if ci_run is None:
            if not wait or time.time() > deadline:
                print(f"no '{CI_WORKFLOW_NAME}' run found for {sha} within the wait window")
                return EXIT_NO_RUN_APPEARED
            print(f"... no '{CI_WORKFLOW_NAME}' run yet for {sha[:7]}; polling again in {POLL_SECONDS}s")
            time.sleep(POLL_SECONDS)
            continue

        print(f"{sha[:7]}  {ci_run['status']:<12} {str(ci_run['conclusion']):<9} {ci_run['created_at']}  {ci_run['name']}  {ci_run['html_url']}")
        if ci_run["status"] == "completed":
            for ln in steps_with_annotations(ci_run["id"]):
                print(ln)
            return EXIT_SUCCESS if ci_run["conclusion"] == "success" else EXIT_CI_FAILED

        if not wait or time.time() > deadline:
            print(f"'{CI_WORKFLOW_NAME}' run {ci_run['html_url']} still {ci_run['status']} after the {wait_minutes}-minute wait window")
            return EXIT_TIMED_OUT_IN_PROGRESS
        print(f"... {CI_WORKFLOW_NAME} run {ci_run['status']}; polling again in {POLL_SECONDS}s")
        time.sleep(POLL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5, help="unused by the head_sha-filtered path; kept for CLI compat")
    ap.add_argument("--sha", default=None, help="ref/hash resolved with `git rev-parse` (default: HEAD)")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--wait-minutes", type=int, default=WAIT_MINUTES)
    a = ap.parse_args(argv)

    ref = a.sha or "HEAD"
    sha = resolve_full_sha(ref)
    if sha is None:
        print(f"cannot resolve '{ref}' to a full 40-char sha (git rev-parse failed, or the object was never fetched locally)")
        return EXIT_BAD_REF
    if a.sha is None:
        print(f"watching HEAD {sha}")

    return watch(sha, a.wait, a.wait_minutes)


if __name__ == "__main__":
    sys.exit(main())
