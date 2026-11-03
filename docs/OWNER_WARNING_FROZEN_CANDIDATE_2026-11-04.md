# Owner warning frozen-input candidate - local only

Base: `cac7f219e3074c3ef0f3ff51ce2b4d96fcc5788f`.
Worktree: `C:/Users/mrthn/aegis-owner-warning-frozen`.
Branch: `codex/owner-warning-frozen-20261104`.
This is a local source candidate. No live adoption, task changes,
remote operations, trade/NAV writes, or actual message delivery were performed.
Local `main` had advanced to `4a1cd669` at setup; the owner's explicit base was
retained. This note makes no claim about current production health.

## Changed interfaces

- `scripts/owner_event_warning.py`: opt-in `--newest-approved-pc-paper` requires
  `--expected-account-sha256`, supplied externally from an independently approved
  PC-PAPER account identity. Definition: SHA256 of the exact UTF-8 account_number
  string, without JSON quoting, whitespace stripping, or other normalization.
  Never derive this expected identity from the currently discovered snapshots.
- Selection reads only `pc_book/state_latest.json`, yesterday's and today's
  Singapore-calendar `pc_book/YYYY-MM-DD/state_latest.json`. There is no glob,
  recursive scan, history/NAV read, IIF input, or broker lookup. Native producer
  `sim_run._run_loop` fixes the PC local date once at session start and can keep
  writing into that folder after Singapore midnight. A dated candidate's
  embedded UTC timestamp must map to the folder's Singapore date or the next
  Singapore date. The selector still reads only today's and yesterday's folders;
  older folders are not probed. The top-level file has no date-folder attestation.
- Every present candidate must carry the same externally pinned account. Missing,
  malformed, foreign-account, future, non-UTC, wrong-folder, or equal-clock / unequal
  byte candidates refuse. Stale candidates do not win. Exact-byte duplicates at
  the same clock are allowed. The newest timestamp within the existing 24-hour
  adapter freshness limit wins; filesystem mtime is never the freshness clock.
- `frozen_read` opens local regular files through pinned no-reparse handles
  (Windows ancestor and final-file handles; POSIX no-follow dir_fd traversal),
  with a 2 MiB limit and metadata stability check. Windows denies write/delete
  sharing until the read closes. Read errors refuse; no insecure fallback.
- `build_saved_warning_bytes` and `warn_saved_bytes` consume frozen native bytes.
  Selected source-line bytes and snapshot bytes remain in memory through final
  assessment, message hashing and the existing private journal/ACK delivery.
  A later pathname replacement cannot substitute the assessed evidence.
- Manual suppression logic, known Apple proof hashes, journal/ACK machinery,
  event identity and default preview behavior are retained.

## Compatibility and adoption boundary

The existing `--pc-paper-snapshot PATH --journal-dir PATH` CLI and path-based
adapter functions remain available. The legacy CLI also uses frozen assessment/
delivery bytes, while preserving its explicit-path arguments and change-refusal
checks. It does not gain the selector's account pin or secure-handle selection
contract. Direct adapter path APIs retain their original caller-attested contract.
No installed task arguments or reviewed baseline files were edited.

A later separately authorized adoption would need independent exact-source review
of these new runner/adapter bytes and a new matching review receipt. Existing
review hashes will not qualify the changed candidate. Keep the existing private
journal and verified manual-suppression evidence; do not fabricate or migrate ACKs.
The account hash is a required independent owner input, not a value supplied by
this builder. Preview remains the default; no live command was run here.

## Bounds and limits

The selector opens at most three snapshots, each <=2 MiB. Corpus scope remains
the two UTC daily SEC source files, now <=2 MiB each in selector mode. There is a
cooperative five-second runner budget, checked during selection/holdings/source
loops, between manual-proof reads, during source-review hashing and before
delivery. Selector mode accepts at most 64 manual suppression records. It refuses entry from 16:44:25 through 17:05:00
Singapore time, leaving 35 seconds ahead of IIF; the existing transport deadline
is <=30 seconds and the sender checks the budget again before calling transport.
These checks do NOT establish a hard OS wall-clock bound: synchronous filesystem,
ACL, JSON or transport calls can stall between checks. Existing external task
limits were not inspected or changed. Hard no-overlap proof requires a separate
runner/task boundary review; do not adopt this as proof of that property.

Only Windows secure reads were exercised on this machine. POSIX handle traversal
is source-reviewed but not runtime-tested here. The inherited private journal
trust/ACK and same-user-tampering limits remain as documented by the adapter.

## Validation

Fixture-only tests exercise full account swap and mixed identity refusal;
missing/wrong expected hashes; future, stale, wrong-folder and non-UTC snapshots;
equal-clock conflicts; exact frozen bytes after mid-run snapshot AND source
replacement through a fake sender and persisted ACK; refreshed Apple suppression
while a second held event is delivered by a fake sender; no preview writes;
Windows junction refusal and read-handle replacement/write exclusion; fixed
selection scope; budget and IIF refusals. Existing warning, runner and bridge
contract tests are included. No real sender or live account is used.

Validation command:
`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_owner_warning_frozen_inputs.py backend/tests/test_owner_event_warning_runner.py backend/tests/test_owner_event_warning.py backend/tests/test_owner_event_warning_bridge_contract.py backend/tests/test_telegram_owner_once.py -q --disable-warnings`

Original candidate result: **191 passed, 1 skipped** (5.71 seconds).
Only these focused suites were run, not the entire backend suite. The new test
file has 25 passing cases; the pre-existing platform skip is in the adapter suite.

Independent review: first read-only worktree review was blocked by sandbox access.
A source-only independent review found four defects: legacy reopen race, missing
manual-proof budget cooperation, corpus existence probing before secure read,
and uncaught Decimal InvalidOperation. All four were fixed and covered by new
regressions. Existing runner tests now intercept the frozen-byte delivery API.
The independent source-packet follow-up established no remaining concrete
high/medium defects in the reviewed scope and confirmed closure of all four
findings. That reviewer did not execute tests; the test results above were run
by the builder. This is candidate review only, not live-adoption approval.
After review, only test-clock determinism and this note changed. The 25 new
selector/frozen-input cases passed again (2.37 seconds).

Original reviewed candidate source byte identities (not an adoption/gate receipt):

- `scripts/owner_event_warning.py`: `8842df152b7f759009755f607c8ac7689071ee3e3651f62f2a2f405b7b8d5d67`
- `backend/services/owner_event_warning.py`: `880acd0ddd761211a2708259e1587b2ca9b0e4a766f609ff2d4ab19ae9dcff4d`

## Session-folder provenance correction, 2026-11-04

The owner reported a preview refusal on saved R data: `pc_book/2026-11-03/state_latest.json`
carried `t=2026-11-03T18:20:00Z`, which is 2026-11-04 02:20 Singapore time.
That is consistent with `sim_run._run_loop` taking the folder date once at
session start and continuing to write there overnight. This is a supplied
observation; this worktree did not open R or run a preview against it.

The selector now allows a dated snapshot's Singapore calendar date to equal
its folder date or the following date. A separate regression proves a two-day-old
folder is never probed. Existing future, stale, account, wrong-folder and
equal-clock refusals remain covered by the focused suite.

The five warning-related test files above returned **193 passed, 1 skipped**
(5.55 seconds); the new test file alone returned **27 passed** (2.47 seconds).
Ruff passed on all touched Python files. The repository-wide `ruff check backend engine` reported 1,310 findings outside those touched files and did not pass.
`git diff --check` passed. No live adoption or actual warning send was attempted.

Updated runner source SHA256: `a74ba5c88b0c358d6a413f0e5012c07206721d7c5bab3a8e2a59446a4fbfad57`.
