# IC funnel transfer candidate — 2026-11-04

Base: `cac7f219e3074c3ef0f3ff51ce2b4d96fcc5788f` (`origin/main` fetched).
Branch/worktree: `codex/funnel-transfer-candidate`, `C:/Users/mrthn/aegis-funnel-transfer-candidate`.
Candidate only: no upload, registration, push, merge, deployment or paid calls.

## Behavior

`IC_FUNNEL_PATH` remains the original, policy-pinned
`backend/data/funnel_night10.json` in Python. The Railway Docker image replaces
the packaged file at that path with a symlink to `/data/funnel_night10.json`
after copying the backend source. Local development still reads its normal
file. Cloud `/data` never falls back to the packaged image. Existing
`ic_health()` reports missing volume data as DEGRADED. The frozen prepared PC
policy epoch source check passes without modifying its contract or hashes.

Run locally, without network or writes:

```powershell
python scripts/transfer_ic_funnel.py <source-json>
```

The CLI requires explicit `--apply`, `--project`, `--environment`, `--service`
and `--expected-remote-sha256` before invoking Railway. Expected state is a
64-character lowercase SHA256, or literal `ABSENT` for initial provisioning.
These options describe future reviewed operation; no apply invocation was run.
All three target options require explicit lowercase UUIDs; names are rejected.
Use reviewed target IDs and a fresh read-only remote hash observation; do not
inherit a potentially unrelated linked Railway service.

Bounded contract: UTF-8 JSON object, <=2 MiB, no duplicate keys/nonfinite numbers,
maximum nesting 20, bounded collections, timezone-aware `generated_at`, no more
than five minutes ahead, no older than 10 days, 1–1500 distinct uppercase ticker
candidates, positive finite price/median_dollar_vol/vol_annual. Additional producer
fields are preserved byte for byte. This validates transport admissibility, not
source correctness, investment merit or current market freshness. Ten days is
the existing IC operational horizon; it does not imply freshness today.

The subprocess uses an argument list, `shell=False`, 60-second timeout and the
existing Railway SSH authentication. Both remote program and base64 payload go
via stdin (`python3 -`), never in command arguments. Raw stdout/stderr and
exception details are suppressed; receipts contain only status/reason or
validated stamp/hash/byte/count metadata. Nothing is persisted as a receipt
unless the operator explicitly redirects stdout.

Remote checks: `/data` is a mount, parent is a directory, target is not a symlink
and is a regular file if present. A nonblocking directory-inode flock serializes
this tool's transfers. Under that lock it validates the existing last-good file,
checks its expected hash, rejects older stamps and equal-stamp/different-byte
conflicts; equal hash is a no-write success. A corrupt existing file is refused,
not overwritten. An absent target requires explicit `ABSENT`.

A private temporary file in `/data` is flushed/fsynced and hash checked before
one atomic `os.replace` to the fixed target; the directory is then fsynced.
Precommit failures preserve the last good file and clean up the staging file.
The only intended remote writes are that private staging file and the fixed
`/data/funnel_night10.json` target. No backup, ledger, database, NAV, orders,
scheduler or registration API is imported or called. A hard process crash can
leave an orphan staging file; it cannot expose partial target contents.

Transport timeout/failure or a failure after the atomic commit is **unconfirmed**:
the remote may have committed. Obtain a new read-only hash observation before
any retry. No automatic rollback or retry is attempted. Directory locking only
coordinates this tool; an unrelated writer that ignores the lock must be ruled
out by the attended operator. Directory symlink checks are a safeguard, not a
sandbox against a hostile root process.

## Evidence and review boundary

User-supplied read-only observations: CLI 5.8 authenticated; service
Aegis-Finance, production; AEGIS_DATA_DIR=/data, mounted volume root-owned 755,
SSH uid 0; volume artifact absent while packaged artifact exists; stdin cat
probe succeeded. These facts were not refreshed or converted to upload authority.
Local `railway ssh --help` confirms target flags. No live SSH was invoked here.

Tests execute the exact transmitted Python source through fake SSH, using a
pytest temporary target, with Linux directory fd/flock operations emulated on
Windows. Real staged file writes, file fsync, hashing and atomic replacement
run locally. Linux flock/mount/directory-fsync behavior and Railway end-to-end
execution remain unverified in production. Independent Pasteur Sol review reported P1 incompatible consumer shapes;
the corrections below are tested. Independent re-review is outstanding
before any live upload.

Focused validation: `python -m pytest backend/tests/test_transfer_ic_funnel.py -q` ? 66 passed.
Python compilation and scoped `git diff --check` also passed.
Covers default dry-run, invalid/schema/stale source refusal before spawning,
remote newer/equal stamp/hash conflict, compare-and-swap race, invalid last good,
missing mount, stage-fsync/replace failures, idempotence, sanitized receipt,
timeout ambiguity, config defaults, and actual missing-volume IC health.
The tests constrain file mutations to pytest temporary directories; source and
config checks are read-only. No NAV/order paths were changed.

Final silent-fragility audit: refusal paths return nonzero with fixed reason codes;
empty/invalid input cannot report success; all subprocess calls have timeouts;
no paid/network model imports; cold missing-volume behavior is covered. No live
production execution was performed. Independent re-review remains outstanding.

## Windows resolution and native target IDs

The CLI resolves `railway.exe`, then `railway.cmd` with `shutil.which` on
Windows (`railway` on POSIX). It passes the resolved absolute path as argv[0],
with `shell=False`. PowerShell aliases and `.ps1` files are not used. Missing
executables produce `railway_executable_missing` before any subprocess call;
dry-run does not resolve or invoke Railway.

Owner-supplied read-only native probe: project name `selfless-courage` failed
with Project not found, while these exact IDs accepted stdin via `python3 -`
and returned `AEGIS_REMOTE_STDIN_OK`:

| Option | Required ID for the reviewed future operator |
|---|---|
| `--project` | `8105f1ef-f39d-4a82-971e-e5d02db5ac8c` |
| `--environment` | `c36ec00c-9250-494d-ae1c-3d07c2bcf60a` |
| `--service` | `05e102b9-b7ee-479d-9257-a506f74730d5` |

These are supplied probe observations, not an upload receipt or authorization.
A positive CLI parser test uses these IDs with a mocked transfer function;
no real SSH is invoked. Names are refused by both parser and transfer API.

## Consumer contract correction after independent P1 review

The reviewer reproduced `shortlist()` crashes for `evidence_basis` as a string
and candidate `why` as an integer. Validation now requires optional
`evidence_basis`/`universe` to be mapping-or-null; evidence list fields
(`ranked_by`, `filtered_by`, `recorded_but_not_ranked_on`) and candidate
`why`/`blocked_by` to be string-list-or-null; and optional `score` to be finite
numeric-or-null, excluding booleans and overflowing integers. Missing optional
fields keep the existing consumer defaults. Unknown producer fields are
preserved, not dropped or reinterpreted.

Tests reproduce both reported failures plus an invalid ranked_by element using
the actual `IC.shortlist`, then verify refusal before SSH and before remote
staging. Valid missing/null defaults also go through the actual reader. The
unchanged checked-in producer artifact is validated and read at its own embedded
historical timestamp: this is a compatibility test, not a claim of freshness
now. Real source data was not regenerated or altered.

Read-only native executable verification after the Windows correction:
resolved `.cmd`, `subprocess.run([resolved_path, '--version'], shell=False)`
returned exit 0 and `railway 5.8.0`. This is a version check only; no SSH or
upload occurred.

Additional owner-supplied read-only native observation: explicit-ID stdin Python
returned 1 for `os.path.ismount("/data")` on the current Railway service. This
supports the mount guard for that observation only; no remote write was made.

## Numeric consumer bound after second independent P1 review

The independent reviewer reproduced three `IC._compute_funnel_state` crashes:
`quality=10**400` and `market_cap=10**400` overflow during float conversion,
and `vol_annual=1e308` overflows cross-sectional variance with another
ordinary candidate. The validator now requires numeric consumer fields to be
finite, float-representable and at most 1e100 in absolute value. All JSON
numeric values get the same magnitude bound. Positive volatility must be at
least 1e-100 so inverse-volatility weighting stays finite. With at most 1500
candidates, the recommendation variance (squared differences and their sum)
and factory inverse-volatility sum stay far below float overflow. The limits
are deliberately loose relative to the checked-in and PC producer artifacts;
this is an arithmetic safety bound, not a signal or investment threshold.

Regression tests first reproduce the actual reader OverflowError using the
unchanged checked-in 25-candidate artifact with one value mutated in a test
temporary file, then verify local validation refusal before SSH. Additional
cases cover every numeric adapter route, required numeric fields and tiny
volatility. A read-only test on the Oct26 PC artifact validates it at its own
stamp and exercises the actual IC reader through its CLEAN gate and all 25
recommendations. The PC artifact remains untouched. A CLI dry-run was also
performed separately; its receipt is local validation only.

## Attended transfer observation — November 4, 2026

After independent source review passed, the reviewed script was committed as
`88342446`. An explicit-ID `--apply` call used `ABSENT` as the expected remote
state and transferred the local October 26 snapshot to the existing Railway
production volume. The sanitized receipt reported `transferred`, 31,876 bytes,
25 candidates and SHA256
`1470feb6969905fb84e7f3f8097447ea60329438102f834a473efa71e6b6f53b`.
An independent remote `sha256sum` matched; the target was mode 0600. Running
the existing IC `_compute_funnel_state` against the volume path on Railway
returned `available=True`, `gate=CLEAN`, 25 recommendations. These are
read-only verification results after the one upload, not proof that the live
application reads the volume yet. The currently deployed `cac7f219` code still
reads its packaged image file until the Docker binding passes CI and deploys.

The first hosted CI run failed one frozen prepared PC policy test because a
prior version changed `backend/config.py`. That source change was reverted;
the Docker binding preserves the policy-pinned Python bytes. The corrected
local focused suite (transfer plus prepared policy) passed 119 tests.

No scheduled transfer exists. The PC's next funnel refresh will require a
separate reviewed sync mechanism to keep the volume artifact current.
