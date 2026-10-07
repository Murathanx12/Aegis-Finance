# The forecast ledger split: sealed monthly streams (cloud, 2026-10-07)

**RESULT IMPROVEMENT: NONE.** This is data-integrity infrastructure. It is built and tested; **the real
ledger was not migrated**: only `--plan` ran against it. The migration is one attended local command.

## 1. The problem

`backend/data/optimus/predictions.jsonl` holds every forecast the system makes (36,979 rows, 54,658,943
bytes at `92f147f`, growing ~25 MB a month) and was rewritten **in place** every time a record
resolved: `belief_state.resolve_all` wrote the whole file with a non-atomic `write_text`, and
`forecast_grader.void_unresolvable` rewrote it again. Consequences:

- every grade is a 54 MB git diff, and the file reaches GitHub's 100 MB limit around December;
- a crash mid-`write_text` leaves half a ledger;
- `resolve_all` read the file, graded for a while, then wrote what it had read: a row appended by
  another writer during the grading pass was **overwritten** (lost);
- no byte-level seal of a closed month is possible while a later grade rewrites its bytes;
- the file is CRLF on disk and in the committed blob (all 36,979 lines), from Windows text-mode writes.

## 2. The remembered chain break, checked first

The brief (and `docs/reviews/REVIEW_2026-10-06_C10_DATA_CATALOG.md` Q8) says the old row-hash chain of
this ledger broke on 25 Aug 2026, around line 1203. **Verified, and it does not apply to this file:**

- `predictions.jsonl` carries **no row-chain field at all**. Every one of its 36,979 rows was scanned
  for a chain-shaped key (`prev_hash`, `row_hash`, `_prev`, `*chain*`, `*prev*hash*`, ...). The only
  hash-named fields are content hashes of the row's own inputs: `prompt_hash` (36,979),
  `input_snapshot_hash` (36,979), `policy_hash` (12,151). They link nothing.
- The ledger whose `_prev` hash chain "has been broken since 25 Aug" is the **terminal repo's**
  `state/decisions.jsonl` (`docs/REDTEAM_2026-09-02_ENGINE_AUDIT.md` R14 traces the concurrent-writer
  lock defect behind it; `scripts/write_superseded_sidecars.py` says "the ledger hash chain in the
  terminal repo"; `docs/research_notes/2026-09-13/spec_allocator_kill_promote.md` quotes the terminal
  repo's `docs/HANDOFF.md`). The finding doc the roadmap cites,
  `docs/FINDING_LEDGER_CHAIN_BREAK_2026-08-25.md`, is not in this repo's history either.
- What this ledger DID have is git. `legacy_history_report` replays **all 24 committed versions**
  (`eb979491` 2026-08-11 .. `92f147f6` 2026-10-07, full history fetched, not a shallow clone):
  **CONTINUOUS**. Across every consecutive pair, 0 rows removed, 0 frozen forecast fields changed,
  0 grades changed or withdrawn, 0 reorders, every new row appended at the end; 19,721 rows became
  terminal in place (the resolution rewrites of 09-20, 09-24, 09-26, 10-02 and 10-07, matching their
  commit messages: 14,703 graded, 2,781 recovered, 130 voided, ...).
- **First byte-level discontinuity:** commit `4603cce95a7c` (2026-09-20), **line 1**: the same row with
  different bytes (CR added; the first whole-file CRLF rewrite, which also wrote the first grades).
  Line sha256 before `559dc01fc7650ee50462cf58bc98ba15f46209aab5de22dbb2c5451997aea311`, after
  `9d4a80dfc9e51b44854018cb82610e600f752322ffa08378d1660bd8aa314a23`. Before it, every committed
  version was a byte-prefix extension of its predecessor (pure appends; the first CRLF lines were
  appended on 09-12).

Both results go on the genesis manifest as `legacy_chain_break`, **unrepaired**, with two statements:
legacy row-chain continuity is not being repaired (there is none, and the legacy bytes are untouched),
and tamper evidence for the forecast ledger restarts at the new manifest chain.

## 3. The design

```
backend/data/optimus/
  predictions.jsonl                         legacy; frozen after the switch, never rewritten
  forecasts/forecasts_<YYYY-MM>.jsonl       forecast rows AS MADE, by made_at month   (LF, append-only)
  resolutions/resolutions_<YYYY-MM>.jsonl   resolve/void EVENTS, by recorded month    (LF, append-only)
  ledger_manifests/forecast_ledger/
    MIGRATION.json                          the switch: which legacy file, its sha256, when
    <stream>_<YYYY-MM>.json                 one manifest per sealed month, chained
```

(`forecasts/` already holds `sim_run`'s `day_<date>.json` receipts; no reader globs a pattern that
matches both, and `ledger_archive` now refuses the stream files.)

- **Fold:** a reader takes every forecast row (month order, file order) and applies events by
  `prediction_id`. The **first terminal event wins**; a later one, or one for an unknown id, is counted
  (`FoldStats`) and never applied. That is the legacy semantics made explicit (`resolve_one` never
  re-grades; the void pass skips graded rows). Writers also skip a second terminal event under the lock.
- **An event may only add.** `make_event` refuses to change or delete a frozen forecast field; a grade
  sets the resolution fields (`RESOLUTION_KEYS`) or adds new ones.
- **Writes:** one fsynced `os.write` per batch to an `O_APPEND` file; LF on every platform; a file whose
  last byte is not `\n` (a torn append) is refused, never glued onto. Every rewrite (manifests, the
  marker, the legacy file before the switch) is temp file -> flush -> fsync -> `os.replace`.
- **Lock:** one cross-process lock per ledger directory (`.forecast_ledger.lock`; `fcntl.flock` /
  `msvcrt.locking`), re-entrant per thread. Every writer re-selects the backend UNDER it, so the switch
  is atomic for every writer running this code.
- **Late forecasts:** a backdated row (a restoration) whose `made_at` month is sealed is filed in the
  open month; its `made_at` is untouched and the month's manifest counts `rows_made_in_another_month`.
- **Sealing:** `forecast_ledger --seal [--apply]`, attended: a month is sealable one whole day
  (`FORECAST_LEDGER_SEAL_GRACE_DAYS`) after it ends, by the run clock (never a file mtime). Chain order
  is (month, forecasts before resolutions); each manifest carries rows, bytes, sha256, first/last id and
  `prev_manifest_sha256`, and its own `manifest_sha256` over its canonical content. Sealing refuses when
  the existing chain does not verify (a changed sealed file, an edited manifest, a missing or wrong
  predecessor) or when a candidate would land before the chain's tail.
- **The switch:** `backend_for(path)` answers `legacy` with no marker, `streams` with a valid marker
  naming this file, and **refuses** (`ForecastLedgerError`) when a marker is present but unreadable:
  falling back to the frozen legacy file would read a ledger that stopped growing.

## 4. Exact migration semantics

Per legacy row (`forecast_ledger_migration.split_row`):

- **open** (no outcome, not void): the forecast stream gets the row as-is (`json.dumps`, key order kept,
  LF instead of CRLF). No event.
- **terminal** (graded or void): the forecast half is the row with its resolution fields reset to the
  open defaults (`RESOLUTION_DEFAULTS`) and the trailing block of non-core resolution fields the
  resolver *appended* to an older-schema row removed (`calibration_bucket`, `vs_benchmark` on a 1.0.0
  row; `voided_at`, `voided_by`); the event carries exactly the fields that differ, in legacy key order.
  This is a reconstruction (the legacy resolver overwrote the as-made bytes), stated on the marker.
- **months:** a forecast by its `made_at` month; a grade by `resolved_at`; a void by `voided_at`. Six
  2026-08 voids carry no `voided_at` (a manual void before the void pass stamped one); they are filed
  under their forecast's month with `month_basis` saying so.
- **verification, every row:** fold == legacy row (dict equality), same canonical content hash, same
  key order, identical frozen fields; and the planned stream BYTES are parsed back through the reader's
  own fold and compared to the legacy rows in legacy order. Any mismatch refuses the apply.

## 5. The plan against the real ledger (cloud run, read-only)

`python -m scripts.ledger_split --plan --history` at `92f147f`:

```
LEDGER SPLIT PLAN (ledger_split/1, 2026-10-07T06:13:25+00:00) -- writes nothing
source:          backend/data/optimus/predictions.jsonl
source sha256:   f484044c98676096ddccaaed002a663a5601cc20b3a017b2ea244998321d9d54
source:          54,658,943 bytes, 36,979 lines, 36,979 rows (36,979 CRLF, 0 blank, 0 duplicate ids, 2 made_at order inversions)
terminal rows:   {'resolve': 20180, 'void': 136}  open rows: 16,663
forecast streams (by made_at month):
  2026-08   24,828 rows    24,952,634 B  f2f88f060bd1c6e0  backend/data/optimus/forecasts/forecasts_2026-08.jsonl
  2026-09    7,111 rows    14,908,000 B  f3e2ae0cb5df6636  backend/data/optimus/forecasts/forecasts_2026-09.jsonl
  2026-10    5,040 rows    12,378,182 B  67f5277488ad67bc  backend/data/optimus/forecasts/forecasts_2026-10.jsonl
resolution streams (by resolved/voided month):
  2026-08        6 events       3,222 B  a0cf40e00c8178e5  backend/data/optimus/resolutions/resolutions_2026-08.jsonl
  2026-09   17,913 events   7,354,590 B  35ed16bf59aa7873  backend/data/optimus/resolutions/resolutions_2026-09.jsonl
  2026-10    2,397 events   1,097,956 B  9e5f7c945cd50b88  backend/data/optimus/resolutions/resolutions_2026-10.jsonl
event month basis: {'made_at (voided_at absent on the legacy row)': 6, 'resolved_at': 20180, 'voided_at': 130}
manifest plan:   seal at apply ['forecasts_2026-08', 'resolutions_2026-08', 'forecasts_2026-09', 'resolutions_2026-09'] (genesis forecasts_2026-08); left open ['forecasts_2026-10', 'resolutions_2026-10']; grace 1 day(s)
                 manifests in backend/data/optimus/ledger_manifests/forecast_ledger; marker backend/data/optimus/ledger_manifests/forecast_ledger/MIGRATION.json
verification:    fold==legacy 36,979/36,979; canonical hash 36,979; key order 36,979; frozen fields 36,979; round trip EQUAL / order EQUAL  -> OK
legacy row chain: NO_ROW_CHAIN -- first mismatch line None; chain fields none; hash fields present {'input_snapshot_hash': 36979, 'policy_hash': 12151, 'prompt_hash': 36979}
git history:     CONTINUOUS over 24 committed versions (eb979491bf5f..92f147f6334f, shallow=False); totals {'removed': 0, 'frozen_changed': 0, 'grade_changed': 0, 'newly_terminal': 19721, 'reordered_pairs': 0, 'appended': 36892, 'appended_not_at_end': 0}
  first byte discontinuity: 4603cce95a7c (2026-09-20T18:17:35+08:00) line 1: same row, different bytes (line endings: CR added); expected line sha256 559dc01fc7650ee5, found 9d4a80dfc9e51b44
next (attended, writers stopped): python -m scripts.ledger_split --apply --expect-sha256 f484044c98676096ddccaaed002a663a5601cc20b3a017b2ea244998321d9d54
```

Full planned stream sha256s:

| file | rows | bytes | sha256 |
|---|---:|---:|---|
| `forecasts/forecasts_2026-08.jsonl` | 24,828 | 24,952,634 | `f2f88f060bd1c6e0168ae8998941ed26ceeb2a9383dd3a87d39cf09dfe528229` |
| `forecasts/forecasts_2026-09.jsonl` | 7,111 | 14,908,000 | `f3e2ae0cb5df6636036387b29bcc9b9b0f0a65b5fe3dd3a2050dc984368b2902` |
| `forecasts/forecasts_2026-10.jsonl` | 5,040 | 12,378,182 | `67f5277488ad67bcd6354dd1416c0834a1041f6535e13d5723c0cb22ce56c899` |
| `resolutions/resolutions_2026-08.jsonl` | 6 | 3,222 | `a0cf40e00c8178e507c78877524773527689c285e5fec3bea10319ee92842268` |
| `resolutions/resolutions_2026-09.jsonl` | 17,913 | 7,354,590 | `35ed16bf59aa7873e44c11577591966183e39a0497432a5f1f630002818e03a5` |
| `resolutions/resolutions_2026-10.jsonl` | 2,397 | 1,097,956 | `9e5f7c945cd50b88d8b4ff60e5be1c8833ffec06796a574eeffc9d7c641ec688` |

**This sha256 will be stale on the PC.** The local loop appends after `92f147f`; the operator's own
`--plan` prints the fingerprint that `--apply` must be given.

### 5a. Rehearsal on a COPY of the real ledger (cloud scratch directory, never the tracked file)

`--apply --expect-sha256 f484044c...` against a byte copy: **APPLIED** in 22 s; every one of the 36,979
rows read back through the real reader equal to the legacy row (canonical hash, order); 4 months sealed
(forecasts/resolutions 2026-08 and 2026-09) with the chain `ok`; the copy's legacy bytes untouched
(`legacy_frozen_intact: true`); `--status` `ok`. After the switch, a `belief_state.append` landed in
`forecasts_2026-10.jsonl`, a void was recorded as an event and folded back, the legacy copy's sha256 did
not move, and `ledger_health` named the backend. The tracked ledger's sha256 was checked unchanged
afterwards.

Read cost on that copy, against the legacy file (same machine):

| read | legacy | streams |
|---|---:|---:|
| `read_rows` (every row, resolutions folded) | 0.83 s | 0.89 s |
| `logical_lines`, full scan (health probes) | 0.07-0.11 s | 0.84 s first, 0.01 s cached |
| `logical_lines(contains=...)`, per-ticker lookup | 0.10 s | 0.31 s first, 0.09 s after |

(The first rehearsal measured `read_rows` at 8.4 s: the per-line error label resolved a path on every
line. Fixed before commit; the label is now built only on a failure.)

## 6. The one attended local migration

1. Pull this branch and **restart every writer** (scheduled sim owner, grader, night jobs, the API):
   only code from this change takes the ledger lock. Then stop them for the migration window.
2. `python -m scripts.ledger_split --plan --history` and read it (it writes nothing).
3. Run the `--apply --expect-sha256 <sha>` line it ends with. In one locked run it: refuses if a byte
   moved since the plan; splits and verifies every row; writes each stream file atomically and reads it
   back; re-hashes the legacy file (a writer that bypassed the lock is caught here and everything this
   run wrote is removed); writes `MIGRATION.json` (**the switch**); seals 2026-08 and 2026-09 (the
   genesis manifest carries `legacy_chain_break` and the legacy sha256); and re-reads every row through
   the real reader and compares it to the legacy rows.
4. `git add backend/data/optimus/forecasts backend/data/optimus/resolutions
   backend/data/optimus/ledger_manifests/forecast_ledger` and commit. Restart the writers.
5. `python -m scripts.ledger_split --status` (backend `streams`, chain `ok`, legacy frozen intact).
   On the 2nd of each month (one day of grace): `python -m backend.services.forecast_ledger --seal`
   to see what closes, then `--seal --apply` and commit.

## 7. Rollback and recovery

- **Before the switch** (anything fails, or the legacy file moves): `--apply` removes every file it
  wrote; the legacy file is never modified; readers never left it.
- **Interrupted apply** (power loss before the marker): readers still use the legacy file and
  `--status` says DEGRADED (stream files beside no marker); `--apply` refuses until
  `python -m scripts.ledger_split --discard-partial` (refused once a marker exists).
- **Crash after the switch, before sealing:** the ledger is migrated; `--status` lists the closed
  months as unsealed; run `forecast_ledger --seal --apply`.
- **Undo after the switch:** delete `MIGRATION.json` and every reader returns to the legacy file, which
  is byte-for-byte the planned one. Any forecast or grade written to the streams since is then
  invisible, so only do it immediately, and check `--status` first.
- **A second apply** with the same fingerprint prints `ALREADY_APPLIED` and writes nothing; with a
  different one it refuses.

## 8. What was migrated, and what remains legacy

Writers routed through the layer: `belief_state.append`, `belief_state.resolve_all` (legacy rewrite now
atomic and re-read under the lock: a row appended while grading is kept, a row graded meanwhile keeps
its first grade), `forecast_grader.void_unresolvable`. Receipts that now name the backend:
`resolve_all`'s report (`ledger_backend`), the grader receipt, `ledger_health`, the `/api/control`
forecast payload, the accrual canary row, population `lineage`.

Readers routed: `belief_state.read_predictions` (and so every caller of it), `accrual_canary`,
`daily_review._tail_rows`, `evidence_population` (`read_population`, `lineage` digest), `fast_mover_forensics`,
`forecast_reputation.load_ledger` (and so `expected_return`), `iif1_grader.load_records`,
`legibility.calibration_date_counts`, `model_routing._forecast`, `query_planner._pred_claim_rows`,
`system_health` (`_ledger_scan`, `_writer_scan`), `routers/control`, `nn_lab/table.ledger`, and the
scripts `bridge_report`, `daily_learning_report`, `decision_autopsy`, `night_error_dataset`,
`night_specialist_scoreboard`, `thesis_cards`.

`backend/tests/test_forecast_ledger_readers.py` is the gate that keeps it that way: every file naming
the ledger in code is classified (via the layer, or why not), and nothing opens a ledger-path constant
directly. A new direct reader fails it.

Still legacy, by design: the arena's own ledger (`arena/predictions.jsonl`) and the leakage probe's
(`leakage_probe_predictions.jsonl`) are separate logical ledgers and stay single files;
`scripts/stock_lists_v3_build.py` (a dated 2026-09-27 one-off that reads rows the frozen file still
holds); the legacy branches of the writers and readers (kept until a later cleanup PR deletes them along
with the frozen file).

## 9. Known limits

- A process running code from **before** this change does not take the lock: it is caught by the
  apply's legacy re-hash (before the switch) but not after it. Hence step 1.
- The Windows lock path (`msvcrt.locking`) was reasoned about, not executed, in this cloud session.
- The manifest chain is in-band: deleting the newest manifest together with its stream file is not
  visible to the chain alone (any hash chain has this property); git history is the outer check.
- Migrated events carry `recorded_at: null` (the legacy row had only a date); new events carry the
  recording time.

Tests: `backend/tests/test_forecast_ledger_split.py` (44), `backend/tests/test_forecast_ledger_readers.py`
(5), and the `forecast_ledger` case in `test_guard_missing_input_contract.py`.
