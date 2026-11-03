## Local integration receipt - 2026-11-04

Integrated in `C:/Users/mrthn/aegis-funnel-sync-integrated` on branch
`codex/funnel-sync-integrated-20261104`, with HEAD/base
`5753a07a2c2aef800ee8280806c2f10711859d73` (corrected PR #63).
The source is the five uncommitted allowlisted files from
`C:/Users/mrthn/aegis-funnel-sync-once-candidate`, whose HEAD is
`866943a3671d7d9c11a1dda555bb1d6b4c97ad51`.

Owner handoff reports independent review completed with 108 tests PASS.
The historical candidate note below predates that handoff and still records
its earlier failed-review/re-review state; it is retained as provenance,
not the current review verdict. No new independent integration review was
performed in this session, and the review artifact was not independently
retrieved. The source HEAD alone does not identify its uncommitted candidate.

Integration differences from the supplied files: retain the corrected base's
frozen-policy config-path test and decoded-payload assertion, remove one
unused `Path` import from the new sync tests for Ruff, and add this receipt.
`backend/Dockerfile` and `backend/config.py` remain identical to the base.
Only the five owner-allowlisted files are changed; the integration is uncommitted.

Validation: transfer + sync + `test_pc_policy_epoch_prepared.py`: **161 passed**.
Targeted Ruff and `git diff --check` passed after the unused-import removal.
Tests use temporary state and mocked transports; there was no native Railway
inspection/write, deployment, task registration, push or PR operation.
Production and dirty R were not operated on. Native transport compatibility,
remote clock calibration, scheduled execution and unattended adoption remain
unproven. The clock/pause, HOLD recovery and advisory-lock caveats below remain.

---

# Guarded one-pass funnel sync candidate

Base: PR #63 head `866943a3`. This is a local candidate, inactive after an
independent review FAIL; it is not deployed, registered, merged, pushed or
live-write verified. The transfer module is changed only in this isolated
worktree to add an optional commit deadline. Its manual default remains
unchanged. No collector, paid data/model call, NAV or order path is invoked.

From this worktree root, use the module entry point:

```powershell
python -m scripts.sync_ic_funnel_once C:\absolute\source\funnel_night10.json --project <project-uuid> --environment <environment-uuid> --service <service-uuid> --state-dir C:\private\ic-funnel-sync
```

All three lowercase UUIDs are mandatory, including dry-run. Default validates
locally and emits metadata only; no network, subprocess, directory or marker
creation. `--apply` enables remote inspection and, only if appropriate, transfer.
No apply command was run during development. There is no task registration.

## Decisions

- Reuse `transfer_ic_funnel.validate`, including its 10-day source age bound,
  5-minute future tolerance, byte/count bounds and consumer checks. Snapshot
  source bytes once; never upload a later unvalidated file revision.
- Fixed remote target `/data/funnel_night10.json`; require a mounted `/data`,
  regular target and no target symlink. Railway SSH uses explicit IDs and
  `python3 -`; Python program and payload travel only on stdin. Captured remote
  output and stderr are never forwarded. Metadata output contains no candidates.
- Identical SHA-256: no write. Older local or equal timestamp with different
  hash: refuse. Absent remote permits initial installation; otherwise only a
  strictly newer source reaches the existing locked compare-and-swap transfer.
  CAS uses the inspected remote hash, so a concurrent target change refuses.
- Each `--apply` invocation fixes an absolute UTC cutoff at **16:29:00 SGT**
  (one minute before the 16:30 margin ahead of the actual 16:45–17:05 PC
  protection window). A pass beginning after 17:05:00 uses the following day's
  cutoff. Starting two SSH steps requires 120 seconds plus 15 seconds of
  margin; one step requires 60 seconds plus 15 seconds. Recheck before state
  setup, immediately before inspection, after inspection, and inside the
  transfer module immediately before launching Railway SSH. The inspection
  helper also checks at its subprocess boundary. Any clock jump or resume
  crossing the deadline refuses locally.
- The sync wrapper passes the same absolute cutoff through SSH stdin to the
  transfer module's remote entry point. While holding the existing directory
  lock, the remote transaction checks its own UTC clock immediately before
  `os.replace`. At or after 16:29:00 SGT, or during 16:30–17:05 inclusive, it
  refuses, removes its temporary staging file and leaves the target unchanged.
  The opt-in parameter is absent from the ordinary manual transfer CLI path.
  Railway SSH has a 60-second local timeout per call; Windows identity/ACL
  helpers have 10 seconds each.
- Per-target exclusive local lock rejects overlap. Use ONE stable state
  directory for this target across all runs, sources and checkouts. There is no
  polling, retry, automatic rollback or sleep loop.

## HOLD and recovery

The dedicated state directory must be outside Git, on a trusted local filesystem
under a trusted parent owned by the operator. Do not put unrelated files there.
POSIX mode is 0700. On Windows, captured `whoami` supplies the current SID;
PowerShell assigns a new protected directory ACL granting only that SID full
inherited access in one assignment (no intermediate permissive ACL reset).
Failure stops before network. Local administrators retain
their usual ability to take ownership. No secrets or payload enter state.

HOLD is named by a hash of the three target IDs. It contains only those IDs and
the exact local content hash. A private temporary file is flushed, fsynced and
atomically replaced before inspection/transfer; POSIX also fsyncs the parent.
Pre-arming covers a process killed before it could report ambiguity. Transport
failure, timeout, malformed receipt and any transfer exception leave HOLD.
Confirmed read-only conflicts and pre-transfer clock/age refusals clear it.
Clock refusal after HOLD is pre-armed but before inspection may retain HOLD;
this is conservative and uses the same read-only hash reconciliation path.

With HOLD present, dry-run stays offline. Apply requires the same target and
exact local bytes, then runs only remote hash inspection. Exact match clears
HOLD and returns `hold_reconciled` without writing or proceeding to transfer.
Mismatch, missing remote, changed local bytes, invalid state or inspection
failure refuses and preserves HOLD. A held source can reconcile even if it has
subsequently aged past the freshness bound. No retry follows reconciliation in
that invocation.

Process death can leave the exclusive `.lock`. This intentionally blocks every
pass. An attended operator must first establish the original process/remote
operation has ended before removing that exact stale lock. Preserve HOLD and
the original source bytes; never delete HOLD to force a retry. If remote hash
does not match, investigate through a separately authorized attended workflow.

## Validation and rollback

```powershell
python -m pytest backend/tests/test_sync_ic_funnel_once.py backend/tests/test_transfer_ic_funnel.py -q
```

Tests use temporary files and fake transports, execute the inspection stdin
program with only the destination redirected, and exercise the existing CAS
transaction tests. No real Railway SSH is used. Windows state ACL setup is
exercised by apply-mode unit tests against pytest temporary directories.
Final focused result: **108 passed**, including a native Windows ACL assertion
that the state directory has one protected allow rule for the current SID.

Rollback of this candidate is simply to stop using the new CLI; it is not
registered anywhere. Preserve any HOLD/lock evidence. No remote rollback or
last-good replacement is implemented. The only product changes are the new
sync script, opt-in transfer guard, focused tests and this document, left
uncommitted in a new worktree.

## Open risks before unattended adoption

- The independent review failure has been repaired in this candidate, but
  independent re-review remains required. Passing tests are not native Railway
  evidence or an unattended-adoption approval.
- No live read/write rehearsal, CLI-version compatibility check, remote clock
  calibration, deployment or scheduler proof was performed for this wrapper.
- Windows atomic replace/fsync is not a guarantee against all power loss or
  storage faults. The exclusive lock and pre-armed HOLD fail closed on process
  interruption; state deletion, alternate state directories, parent reparse
  attacks and hostile local users are outside the trusted-operator model.
- A timeout ends local waiting; it cannot prove the remote Python process has
  stopped. Hence HOLD, no blind retries and attended stale-lock recovery.
- The local and remote guards trust their respective system clocks. A wrong or
  backward-jumping remote clock cannot be proved safe offline. Even with a
  correct clock, an OS pause after the remote check and before `os.replace`
  cannot be ruled out in Python; the one-minute remote gap is a bounded
  mitigation, not a hard real-time guarantee. SSH descendants may outlive the
  local timeout, but their delayed commit is refused when the remote guard sees
  the cutoff. No scheduler/service settings were changed.
- Locking/CAS inherits PR #63's directory-inode advisory lock; other remote
  writers that ignore it can race. A shared state directory is required locally.
- Normal remote inspection validates schema before timestamp comparison;
  malformed remote state refuses with HOLD instead of being overwritten.
  Inspection stdout is bounded after subprocess capture, as in the transfer
  module; a hostile transport could consume memory before that check.
