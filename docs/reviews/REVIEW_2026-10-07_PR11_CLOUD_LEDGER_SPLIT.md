# REVIEW 2026-10-07 — PR #11 (cloud ledger split), backend only

Reviewer: adversarial (data integrity + measurement correctness). PR head `904ba019`
(`origin/claude/beautiful-meitner-hq5614`), read in the detached worktree
`C:\Users\mrthn\aegis-finance-pr11`. Scope: `forecast_ledger.py`, `forecast_ledger_migration.py`,
`scripts/ledger_split.py`, `scripts/evidence_ladder_null_audit.py`, every changed reader of
`predictions.jsonl`, `backend/config.py`. Docs, SVGs and Optimus are covered by another reviewer.

## Verdict: MERGE AFTER FIXES

The question that matters most has a clear answer. **With the split NOT applied, every reader and
both writers produce the same output as `main`, checked against today's real ledger.** That covers
37,651 rows, a 56,069,487-byte copy taken 17:15 HKT, and 38 checks (see "Equivalence evidence").
`resolve_all` on a copy writes **byte-identical** output to main's (sha256 `79b353ea…`, 2,458 grades).
So merging changes no measured number today.

**Applied to a copy of today's ledger,** the split folds back to the legacy rows exactly: order,
content and key order. `forecast_reputation.load_ledger`, `logical_lines` (text, apart from CRLF),
`row_count`, the accrual canary and `ledger_health` all came out equal (APPLIED in 6.7 s, chain ok).

Fix these before merging:
- **F1**: a test that fails on this machine.
- **F9**: two merge conflicts with `wip/2026-10-07-day`.

Fix these before the attended `--apply`:
- **F2, F3**: `--status` reports `ok` while the ledger cannot be read or written.
- **F4**: the commit step leaves the frozen file uncommitted.
- **F5**: a startup ERROR on Railway at every boot.

The rest can follow.

## Findings

| # | file:line | failing scenario (one sentence) | severity | fix |
|---|---|---|---|---|
| F1 | `backend/tests/test_forecast_ledger_split.py:594-607` | On any Windows machine with Git for Windows defaults (`core.autocrlf=true` in `C:/Program Files/Git/etc/gitconfig`), the "CRLF rewrite" commit `v3` normalises to no change. `git commit -am v3` then exits 1 and the test fails. Reproduced: it passes with `GIT_CONFIG_NOSYSTEM=1`. CI is Linux and stays green, so the owner's local targeted run is red. | **High (merge blocker)**: red on the PC | Pass `-c core.autocrlf=false` in the `git()` helper, or write a `.gitattributes` with `* -text` into the temp repo before `v1`. |
| F2 | `backend/services/forecast_ledger.py:1543-1600` (`status`), `:1042` (`_check_tail`) | After the split, a torn tail in the open month's forecast stream makes every `belief_state.append` refuse and every strict reader raise `JSONDecodeError`. That includes `resolve_all`, `ledger_health` and `iif1`. Meanwhile `status(rehash=True)` and `scripts.ledger_split --status` report **`ok`** with `problems: []`. Reproduced on a copy. | **High (post-split)**: the operator's verification command is green on a ledger that is down | In `status()`, run `_check_tail` on every unsealed stream file. Treat `fold.bad_lines > 0` and `refused_events > 0` as problems. Add an attended `--quarantine-torn-tail` that moves the fragment to a dated sidecar under the lock, with a receipt. One crash should not halt forecast writing until someone edits a file by hand: this machine has had bugchecks that left NUL-filled tails (memory, 09-12). |
| F3 | `forecast_ledger.py:667-684` (`_read_events`, strict), `belief_state.py:1190` | A single hand-written or malformed event (for example one that sets `ticker`) makes `read_predictions` raise `ValueError`. That halts `resolve_all`, `void_unresolvable`, `ledger_health` and `forecast_populations` (UNREADABLE). The design says such an event "is counted (`refused_events`) and never applied" and that "a malformed event never blocks the real grade". That holds only in lenient mode. `ledger_health`'s "refused by the fold" problem line is dead code, because the strict read raises first. `status(rehash=True)` still says `ok` (it records `bad_lines` and never raises a problem). Reproduced. | Medium (post-split) | In strict mode, raise only on bytes that do not parse. Route `event_problem` rows to `stats.refused_events` and let `fold()` skip them, as documented. `ledger_health` then shows them as a DEGRADED problem, which is what the existing branch was written for. Add a test that a malformed event leaves `read_predictions` working and `ledger_health` DEGRADED. |
| F4 | `forecast_ledger_migration.py:793`, research note §6 step 4 (line 198) | The commit step adds only `forecasts/`, `resolutions/` and `ledger_manifests/forecast_ledger`. The frozen `predictions.jsonl`, which is ` M` on the PC as normal, is left **uncommitted**. Its last state, the one the marker's `legacy_sha256`/`legacy_bytes` vouch for, therefore exists in no commit. One `git checkout -- .` or `reset --hard` (the 09-24 incident) rolls it back to an older commit. `legacy_frozen_check` then reports DEGRADED for ever, and the documented rollback (delete the marker) would read an older ledger than the one migrated. | Medium | Add `backend/data/optimus/predictions.jsonl` to the `next` command and to step 4, in the same commit as the marker. Have `--status` print whether the marker's `legacy_sha256` matches `git hash-object`-reachable content at HEAD. |
| F5 | `backend/services/belief_state.py:622-636, 684-685` | The split check runs **before** the existing "destination already holds records → not_needed" rule. The image ships `backend/data/optimus` (no `.dockerignore` exclusion; `backend/Dockerfile:18 COPY backend/`). So once the split is committed and deployed, every Railway boot logs `logger.error(... NOT copied ...)` and reports `source_split_not_copied`, even though the volume ledger was migrated months ago and nothing needs copying. | Low-Medium (log noise that trains the reader to skim ERRORs) | Read `dst` first. If it holds rows, report `not_needed`. Report `source_split_not_copied` only when the volume is empty and the source is split. |
| F6 | `forecast_ledger.py:787, 807-850` (`_LOGICAL_CACHE`) | After the split, one full `logical_lines` scan keeps **82 MB** in that process for its lifetime, measured with tracemalloc on the 37,651-row copy (peak 133 MB). The cap is 256 MB of *text*, roughly 300 MB resident. That is per process: the API, every health probe and the sim, on a machine whose suite has been reaped twice for memory (memory, 10-07). The legacy path streamed the file and retained nothing. | Medium (post-split, grows ~25 MB/month) | Drop the module cache, or cap it at a few MB and key it on the caller. Better: give `_ledger_scan`/`_writer_scan` a streaming fold (forecast lines streamed, terminal sets from the small resolution files). Move `LOGICAL_CACHE_MAX_BYTES` and `REPLACE_RETRIES` (`:274`) into `backend/config.py`, per the repo rule. |
| F7 | `forecast_ledger.py:1198-1221` (`legacy_rewrite` → `atomic_write_text` → `_replace`) | **Pre-split, Windows only.** Main's `resolve_all` used `write_text`, which truncates in place and succeeds while another process has the file open. The PR uses `os.replace`. That fails with PermissionError while any reader holds the 56 MB file open: the API, a health probe iterating `logical_lines`, git hashing it, an indexer or AV. It gives up after 12 retries (~3.6 s), so a grading pass can now raise where main succeeded. Nothing is lost (the old bytes stay; the next pass regrades), but grades are delayed and the receipt is missing. `void_unresolvable` already had this exposure on main. | Low-Medium | Keep the atomic write. On final PermissionError in `legacy_rewrite`, return a typed refusal on the receipt (`ledger_busy_replace`) rather than raising, and/or lengthen the retry window to ~30 s for the legacy file only. |
| F8 | `forecast_ledger.py:1543-1600`, `verify_chain` `:1440-1455` | Rows appended to an **unsealed** month after the migration can be truncated away, and `status(rehash=True)` still says `ok`. `streams_at_apply` covers only the bytes the migration wrote, and `fold >= legacy_rows` still holds. The next `--seal --apply` then seals the shortened file. Reproduced: one appended row deleted, status `ok`. The note's "in-band chain" caveat covers forged chains, not this. | Low-Medium | Under the lock, have each append update a per-open-stream high-water mark (bytes plus sha256 of the file) in `HEAD.json` or a sibling `OPEN.json`. `status`/`seal_closed` refuse a file that is shorter than its mark or whose prefix hash differs. |
| F9 | merge with `wip/2026-10-07-day` | `git merge-tree --write-tree wip/2026-10-07-day 904ba019` gives two content conflicts: `.gitignore` and `backend/tests/test_guard_missing_input_contract.py`. `config.py`, `query_planner.py` and `system_health.py` auto-merge. | Medium (merge mechanics) | Rebase the PR onto the day branch, or resolve both by hand. Re-run `test_guard_missing_input_contract.py` after resolving, because both sides append to `CASES`. |
| F10 | `forecast_ledger.py:597-613` (`_read_legacy`), used by the lenient readers | Main's lenient readers `forecast_reputation.load_ledger`, `night_specialist_scoreboard.load` and `daily_learning_report._jsonl` split on `\n` (file iteration). The PR's legacy path uses `str.splitlines()`, which also splits on U+2028/U+2029/U+0085/`\x0b`/`\x0c`/`\x1c-\x1e`. A row whose LLM text carries a raw U+2028 (`json.dumps(ensure_ascii=False)` does not escape it) would be **dropped** (two bad lines) where main kept it. Also, `night_error_dataset` lost main's `errors="replace"` (invalid UTF-8 now raises), and `legibility.calibration_date_counts` lost main's `isinstance(r, dict)` filter. The live ledger has **zero** such characters today (scanned), so no number moves now. The streams backend splits on `b"\n"`, so the two backends disagree on such a row. | Low (latent) | In lenient mode, read the legacy file by line iteration (`open(..., newline=None)`), as `logical_lines` already does. Keep `read_text().splitlines()` only for the strict path, where it equals main's `read_predictions`. Filter non-dict rows in lenient mode. |
| F11 | `scripts/ledger_split.py:79` | `--apply` returns exit **1** for `APPLIED_WITH_PROBLEMS`, a state in which the switch **has happened**. The module docstring defines 1 as "unexpected error". An operator, or a wrapper that reads the code, can take it as "nothing changed". | Low | Use a distinct code (e.g. 3 = switched with problems) and print the `post_switch_error` / `next` line as plain text after the JSON. |
| F12 | `belief_state.py:989` (`resolve_all` report) | When the ledger refuses a pair (`refused_by_ledger > 0`) or another pass graded it first, `resolved` / `void` / `pending_not_yet_due` are still computed from this pass's in-memory `graded` list. The receipt can therefore count as resolved a grade that was never written. Only `newly_resolved` was corrected. | Low | Compute `resolved`/`void`/`overdue` from a re-read, or subtract the refused and skipped ids. |

Not defects, but noted:
- **`ledger_lock` takes its per-thread `RLock`** (`forecast_ledger.py:398`) **with no timeout.** A second thread in the same process waits for ever, never reaching `LedgerBusy` after `FORECAST_LEDGER_LOCK_TIMEOUT_S`.
- **The guard-contract case writes an un-removed temp dir** (`tempfile.mkdtemp()`).
- **The enrolment gate (`test_forecast_ledger_readers.py`) only sees the literal `predictions.jsonl` and three constant names.** A path passed through a local variable (`EP.ledger_path(pop)` → `p.open()`) is invisible to it. I grepped every `ledger_path(` and `.PREDICTIONS` consumer by hand and found no bypassing reader today (`ledger_resolver`, `resolve_campaign_ledger`, `calibration`, `morning`, `agency` all go through `read_predictions`/`append`). The terminal and Optimus repos were not checked.

## The cloud review's 12 claimed fixes

| # | verified here | how |
|---|---|---|
| 1 | yes | `--discard-partial --legacy other.jsonl` in a migrated dir → `MigrationRefused`; `forecasts/day_2026-10-06.json` survived a real discard |
| 2 | partly | refused by `event_problem`, but in strict mode it **raises** rather than being counted (F3) |
| 3 | yes | `skipped_already_terminal` on a second grade; the first grade survived the fold |
| 4 | yes | an Aug-dated forecast is filed in 2026-10, `late_filed: 1` |
| 5 | yes | a bypass append to the frozen file → DEGRADED in `status()` and in `ledger_health` |
| 6 | yes for sealed months; **no for open months** (F8) | deleting the newest seal and its stream → `BROKEN` via HEAD |
| 7 | yes | `KeyboardInterrupt` at the marker write → streams removed, backend still legacy |
| 8-10 | read, not exercised | — |
| 11 | yes | ALREADY_APPLIED / refusal paths |
| 12 | yes, with F1 | cross-process lock test **passed on Windows here**, so "msvcrt reasoned about, not executed" (note §9) is now executed. The git-history test fails on Windows (F1). |

## Equivalence evidence (what I ran)

- **Pre-split readers.** Scratch `eq.py` under `%TEMP%\claude\pr11rev\`: main's module source (`git show origin/main:…`) imported beside the PR's, both run against a byte copy of the live ledger (37,651 rows) and a 3,000-row slice. 38 checks, **ALL EQUAL**:
  - `read_predictions`, `evidence_population._read_jsonl`, `forecast_reputation.load_ledger`;
  - `iif1_grader.load_records` (power and grade);
  - `daily_review._tail_rows` and accrual `_tail_lines` at 1 kB / 400 kB / 1 GB, plus `forecast_accrual`;
  - `logical_lines` vs line iteration (with and without `contains`), `row_count`, and `content_digest` vs the file sha256;
  - `model_routing._forecast` for NVDA/AAPL/MU.
- **Pre-split writer** (`eq_write.py`). `resolve_all` with an identical deterministic `resolve_one` stub (1 in 7 due rows graded) on two copies, main vs PR: **bytes equal**, sha256 `79b353ea8ad6de10…`, 2,458 newly resolved. PR receipt `ledger_backend: legacy`, `refused_by_ledger: 0`.
- **Applied split** (`streams.py`, on a copy). `plan` READY (verification ok, 2 made_at inversions, both within a month), then `apply`: APPLIED in 6.7 s, 4 months sealed, chain ok.
  - Equal to the legacy reference copy: `read_predictions` (content + order + key order), `forecast_reputation.load_ledger`, `logical_lines` (parsed, and text apart from CRLF: 0 differing lines), `row_count` 37,651/37,651, `forecast_accrual.rows_by_day`.
  - `ledger_health` showed no differences outside the new keys.
  - Tail sets equal at 400 kB. At 4 MB the streams tail returned one extra row, a different cut point across files; that is harmless for its two consumers, which use only frozen fields.
- **Adversarial runs** (`adv.py`, `adv2.py`, `adv3.py`, `adv4.py`, `mem.py`). Results behind F2, F3, F6 and F8, and the confirmations in the table above.
- The live `predictions.jsonl` was only **copied** (`cp`), never opened for writing. Nothing in the manager's checkout was modified except this file.

## Tests run (worktree `C:\Users\mrthn\aegis-finance-pr11`, `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 python -m pytest -q -p no:cacheprovider`)

1. `backend/tests/test_forecast_ledger_split.py backend/tests/test_forecast_ledger_readers.py backend/tests/test_evidence_ladder_null_audit.py backend/tests/test_guard_missing_input_contract.py backend/tests/test_signal_reachability.py`: **1 failed, 212 passed, exit 1** (60 s). The failure is `test_the_git_history_replay_finds_the_first_byte_and_semantic_breaks` (F1).
2. That test alone with `GIT_CONFIG_NOSYSTEM=1`: **1 passed, exit 0**.
3. Reader coverage:
   - Files: `test_belief_state`, `test_forecast_grader`, `test_evidence_population`, `test_forecast_populations`, `test_forecast_reputation`, `test_expected_return`, `test_iif1_grader`, `test_accrual_canary`, `test_daily_review`, `test_u_forecast`, `test_fast_mover_forensics`, `test_data_catalog_and_ledger_archive`, `test_legibility_routers`, `test_model_routing`, `test_query_planner`, `test_system_health`, `test_bridge_report`, `test_daily_learning_report`, `test_decision_autopsy`, `test_night_error_dataset`, `test_thesis_card`, `test_control_coverage`, `test_ledger_resolver`, `test_resolver_guard`, `test_quarantine_survives_establishment`, `test_stitched_tickers_every_reader`, `test_book_forecasts`, `test_agency_review`, `nn_lab/tests/test_nn_lab.py`.
   - Result: **742 passed, exit 0** (120 s).
4. Not run: the full suite (memory rule).

## What I did not check

- `scripts/evidence_ladder_null_audit.py` was read for its method only. Its test passed, but I did not re-derive its null rates or confirm that its `excess_pp` matches `/arena`'s computation.
- The `legacy_history_report` git replay on the PC's real history (`--plan --history`). Its memory and runtime over 24+ versions of a 56 MB file were not measured.
- The `msvcrt` lock under real contention between the sim, the API and a grader. Only the suite's two-process test ran.
- Forced-crash behaviour (power loss mid-`os.write` or mid-`os.replace`). It was simulated by injected exceptions only.
- The desktop .exe frozen-path behaviour of the new lock and marker paths.
- `routers/control.py` was not exercised live.
- Readers in the terminal and Optimus repos (for example `tools/refresh_aegis.py`).
- Docs, SVGs, research-intake scripts, `render_public_assets.py` (the other reviewer's scope).
- Fix-claims 8-10 in the cloud review's table (NaN compare, `os.replace` retry, unopenable lock) were read, not exercised.
