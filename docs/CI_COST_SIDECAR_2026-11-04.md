# CI cost sidecar — local candidate, 2026-11-04

Base/HEAD: `e07c84d6183dfeed1ccfbc3a88b24bfe732390e3` (fetched origin/main).
Worktree: `C:/Users/mrthn/aegis-ci-cost-sidecar`.
Branch: `codex/ci-cost-sidecar-20261104`. Uncommitted; not pushed or merged.

## Decision

Preserve both event triggers, all three job IDs/check names, backend job body
and gate, frontend job body, and same-PR-only concurrency cancellation.
Classify both push and PR events; frontend skips only on an affirmative output.
Keep duplicate PR/main backend suites: these test different trees, and eliminating
one is outside this conservative change. Main runs remain independent.

The frontend npm build/test commands and Next/TypeScript/PostCSS configuration
consume frontend-local inputs. No build-time import/read of backend Python,
scripts Python, docs Markdown or receipt files was found. The explicit allowlist
is backend/services/**/*.py, backend/tests/**/*.py, scripts/**/*.py, docs/**/*.md,
and backend/data/public_receipts/**. Anything else (including root configuration,
shared files, frontend, workflows, classifier tests and non-Python backend files)
forces frontend CI. Revisit this allowlist if build inputs change.

Push: compare event.before to checked-out HEAD, across the entire push. Retain
the existing receipt-only backend skip on push only. PR: establish that both
event base/head SHAs are ancestors of the checked-out test merge, then compare
their merge base to that test merge. This includes base drift, so a frontend
change on main also triggers frontend CI on a backend-only PR. NUL-delimited
Git paths and --no-renames retain both sides of moves. Empty diff, absent/zero
SHA, missing history, malformed output/encoding, unsupported event or git error
means full CI. Classifier checkout uses depth 64 on PRs and 2 on pushes;
unavailable history sacrifices savings, never checks. Classifier job failures
also run both downstream jobs unless the workflow is cancelled.

No workflow-level path filters: existing checks remain present. The existing
`!cancelled()` status condition remains in both dependent jobs, avoiding an
implicit success-only dependency gate without making superseded runs immortal.
Main runs do not share cancellation groups. No runs were cancelled manually.

## Read-only remote evidence

Both branch protection and effective main branch rules REST requests returned
HTTP 403: "Upgrade to GitHub Pro or make this repository public to enable this
feature." Required contexts and merge-queue configuration remain UNKNOWN.
No protection settings were changed. Exact existing check names are preserved;
GitHub documents job-level skipped checks as successful, unlike workflow-level
path filtering. No merge_group event is added by this bounded patch.

PR66 head: 3ec764dc849a98bc00992f9345a3362464e6a6c9.
PR67 head: 4eff02fa036bb65572208e7bf7a584d13d757592.
Their current file lists fit the frontend-independent allowlist; actual decisions
also depend on complete Git diffs/base drift, not these API file lists.

- Run 41721791436 (PR66): frontend 21:26:21–21:30:40 UTC, 259s.
- Run 41724824288 (PR67): frontend 21:46:37–21:50:17 UTC, 220s.
- Combined avoidable frontend job time for comparable proven diffs: 479s,
  approximately 8 runner-minutes, before added classifier overhead. A comparable
  PR plus main push could save approximately 8 minutes total. This is a duration
  estimate, not measured invoice savings or reduced backend critical-path time.

## Validation and limits

`python -m unittest discover -s tests/ci -v`: 8 tests PASS, with table-driven
allowlist/unknown cases and real temporary Git histories for merges, base drift,
multiple commits, rename/deletion and missing refs; CLI output tested as well.
YAML parsed; deterministic comparison to HEAD verified unchanged triggers,
concurrency, names, backend gate, and both expensive job bodies.
`actionlint v1.7.12 -shellcheck= .github/workflows/ci.yml`: PASS.
`git diff --check`: PASS. No application suites/build run for CI-only changes.
Independent read-only Codex review: no concrete findings in the requested scope;
its temporary-Git tests were sandbox-blocked, while all 8 tests passed locally.
No hosted execution of this candidate; checkout overhead and native cancellation
remain unmeasured. Branch protection remains unverified due to API access.

Sources:
- https://github.com/Murathanx12/Aegis-Finance/actions/runs/41721791436
- https://github.com/Murathanx12/Aegis-Finance/actions/runs/41724824288
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://github.com/github/docs/blob/main/content/pull-requests/reference/status-checks.md
