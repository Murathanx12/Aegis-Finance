# Q16: ci_watch false negative, root cause + fix (2026-10-07)

## The symptom

`python -m scripts.ci_watch --wait` printed "run not finished (or not created
yet); polling again in 90s" repeatedly and then exited 2 ("no run found for
that sha within the wait window") for commit `e041ec14`, while the public API
showed that commit's CI run had completed successfully ~20 minutes earlier.
Earlier the same day, the watcher saw two workflow runs for commit `92f147f6`
(`CI` and `Deploy frontend to Vercel`) and timed out with "newest run not
finished; no verdict" even though CI later completed (as a failure).

## Root causes, each reproduced live against the public API before fixing

1. **"Newest run" picked by list index across workflows, not by name.**
   `GET /actions/runs?head_sha=92f147f6334f3651a98277f0aada1eaa5c26671b`
   returns `total_count: 2` — `Deploy frontend to Vercel` listed *before*
   `CI`, same `created_at` second. The old code did `rs[0]` as "the" run; CI's
   own status was invisible behind an unrelated workflow whenever the API's
   ordering put it first.

2. **20-minute `--wait` deadline is shorter than CI's own measured duration.**
   `e041ec14`: `created_at` 05:42:46Z → `updated_at` 06:03:55Z (~21 min).
   `92f147f6`'s CI run: 04:37:17Z → 05:01:36Z (~24 min). A 20-minute window
   times out on a run that is about to go green, every time it runs close to
   its typical duration.

3. **Client-side filtering of a repo-wide, all-workflows page** instead of
   the API's own `head_sha` filter. The old code fetched
   `?per_page=max(n,10)` (every workflow, repo-wide, newest-first) and
   filtered in Python. `?head_sha=<full sha>` returns exactly the runs for
   that commit directly (`total_count: 1` for `e041ec14`; `total_count: 2`
   for `92f147f6`) — verified live.

4. **`head_sha` requires the FULL 40-char sha.** The old default truncated to
   7 characters for display and then reused that truncated value. Verified
   live: `?head_sha=e041ec14` (8 chars) → `total_count: 0`, even though the
   full-sha query against the same commit returns the real run.

5. **The dominant cause for the `e041ec14` incident itself.** The watch was
   run with no `--sha` from branch `wip/2026-10-07-day`; `git rev-parse HEAD`
   resolved to `0b6655f3` — a **different commit with the identical commit
   message**, built directly on parent `92f147f6` (skipping intervening
   commits present in `wip/2026-10-07-day`'s own history). Confirmed via
   `git branch --contains`:
   - `e041ec14` → `main`, `origin/main` only.
   - `0b6655f3` → `wip/2026-10-07-day`, `origin/wip/2026-10-07-day` only.

   `.github/workflows/ci.yml` triggers only on `push: branches: [main]` and
   `pull_request: branches: [main]`. Live query
   `?head_sha=0b6655f38363fd0420223c8b094553e27283151e` → `total_count: 0`,
   and `GET /pulls?head=Murathanx12:wip/2026-10-07-day&state=all` → `[]` (no
   PR). **`0b6655f3` can never get a CI run from this branch, no matter how
   long the watcher waits.** The 20-minute poll was a technically faithful —
   and completely useless — answer to the wrong question: it should have
   refused in one call instead of burning the full wait window on a commit
   that structurally cannot produce a verdict, while the commit that actually
   mattered (`e041ec14`, pushed to `main`) had already gone green.

## The fix (`scripts/ci_watch.py`, rewritten)

- Resolves the **full** sha via `git rev-parse` (refuses with a distinct exit
  code if it can't get 40 hex chars — no silent short-sha API calls).
- Queries `GET /actions/runs?head_sha=<full sha>` directly instead of
  client-side filtering a repo-wide page.
- Explicitly selects the run named `CI`; every other workflow run sharing the
  sha is printed as `(other workflow, not the verdict)` and never used to
  decide the exit code.
- `WAIT_MINUTES = 40` (was 20), with `--wait-minutes` to override.
- Before polling at all, `ci_can_ever_run(sha)` checks whether the sha is
  reachable from `origin/main` or is the head of an **open** PR into main
  (`GET /pulls?head=<owner>:<branch>&state=open`). If neither, it **refuses
  immediately** — this is the direct fix for root cause #5.
- Six distinct exit codes instead of the old overloaded 0/1/2, so the exit
  code alone tells you which of six situations happened (success, CI
  failure, API unreachable, "can never run from here", "no run appeared in
  the wait window", "still running when the window closed", "bad ref").
- On a completed run, prints each job's conclusion and, for any job that
  didn't succeed, pulls annotations from the **public**
  `/check-runs/{id}/annotations` endpoint (GitHub Actions job ids and
  Checks-API check-run ids are the same number — verified live) so a red CI
  is diagnosable from this one call, no token needed.

## Files changed

- `scripts/ci_watch.py` — rewritten (see its module docstring for the
  numbered root-cause list, identical to the one above).
- `backend/tests/test_ci_watch.py` — new, 24 tests against real saved
  fixtures (success, failure+annotations, masking, in-progress→success,
  eventual consistency, timeout-while-in-progress, the up-front refusal, and
  short-vs-full sha resolution).
- `backend/tests/fixtures/ci_watch/*.json` — real API responses saved
  2026-10-07 while reproducing both incidents: `runs_e041ec14_by_head_sha`,
  `runs_92f147f6_by_head_sha` (the masking case), `runs_0b6655f3_by_head_sha`
  (`total_count: 0` — the never-triggers case), `jobs_e041ec14`,
  `jobs_92f147f6_ci_failure`, `check_runs_92f147f6`,
  `annotations_112633519248` (the real failing-test messages), and
  `pulls_wip_branch` (`[]` — no open PR).

## pytest summary

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_ci_watch*.py backend/tests/test_signal_reachability.py -q
.................................
33 passed in 20.83s
```

## The real watcher, run once against `e041ec14`

```
$ python -m scripts.ci_watch --sha e041ec140b91a9df680e13a65a5a5796f1c9270c
e041ec1  completed    success   2026-10-07T05:42:46Z  CI  https://github.com/Murathanx12/Aegis-Finance/actions/runs/37577670765
  backend (pytest offline + ruff + pip-audit): success
  frontend (next build): success
$ echo exit=$?
exit=0
```

## Two live sanity checks beyond the required run

`--wait` with no `--sha`, run from the actual `wip/2026-10-07-day` checkout
(reproducing the exact failure mode without a 40-minute wait):

```
watching HEAD 56fa6e222f5a495575d3c7ef53f9fd462356e9d8
REFUSING to wait: 56fa6e2 is not reachable from origin/main and branch
'wip/2026-10-07-day' has no open PR into main. ci.yml triggers only on
push/PR to main -- this sha can never get a CI run from here.
Pass the sha that IS on main (e.g. `git rev-parse origin/main`), or open a
PR for this branch.
(exit 3)
```

`92f147f6` (the masking + failure case), live:

```
  (other workflow, not the verdict) Deploy frontend to Vercel    completed    success   2026-10-07T04:37:17Z
92f147f  completed    failure   2026-10-07T04:37:17Z  CI  https://github.com/Murathanx12/Aegis-Finance/actions/runs/37572335555
  backend (pytest offline + ruff + pip-audit): failure -- failed steps: ['Pytest (fast suite — offline, blocking)']
    [.github:145233] Process completed with exit code 1.
    [backend/tests/test_opportunities_router.py:122] test_router_is_registered_on_the_app
    [backend/tests/test_analyst_reputation.py:56] test_firm_reliability_is_byte_identical_to_the_pinned_fixture
    [.github:5316] Process completed with exit code 1.
  frontend (next build): success
(exit 1)
```

## Open item, not fixed here (owner decision)

Root cause #5 is a symptom of a deeper practice: a worktree/session produced
a commit (`e041ec14`) that was pushed straight to `main` with the hotfix
alone, while the active session's own branch (`wip/2026-10-07-day`) carries
the identical hotfix as a sibling commit (`0b6655f3`) sitting inside a much
larger day's worth of accumulated work on top of the same parent
(`92f147f6`). `git diff --stat` between the two shows they are NOT
equivalent trees — `0b6655f3`'s side has 76 files / ~176k lines beyond the
hotfix itself, all the rest of `wip/2026-10-07-day`'s work — so this is not
a silent duplicate/conflicting fix, just confirmation that `main` is now
behind `wip/2026-10-07-day` by one small hotfix. Before merging
`wip/2026-10-07-day` into `main`, resolve that one hotfix file (route
registration / fixture line-ending) as already-applied rather than
reapplying or reverting it.
