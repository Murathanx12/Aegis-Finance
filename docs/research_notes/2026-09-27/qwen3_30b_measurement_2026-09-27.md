# Qwen3-30B-A3B: measured, not assumed (2026-09-27)

**Murat's question:** why is the 30B not used?

**Short answer:** because nobody had measured it idle, and the job that was
supposed to measure it could not. `scripts/night_l4_qwen3_measure.py` never
started a server. With the 7B up it refused, and with the 7B down it wrote
`PENDING_MODEL` and a plan. The only numbers on record are from 2026-09-10:
17.28 GiB, `--n-cpu-moe 48` → 1,854 MiB VRAM, 19.8 tok/s generation against the
7B's 41.4, and 5.6 tok/s prompt eval. They were taken while a PyInstaller build
kept all 20 cores busy, so they are a lower bound. They are not a verdict.

**What changed (this commit):**

1. **L4 now starts and stops the 30B itself.** It uses a second, named server
   config (`ServerConfig`) with an explicit model path and `--n-cpu-moe`, on its
   own port (`config.L4_PORT` = 8093, not 8080). The default serving model is
   never started, stopped or re-pointed, so no caller of the default reader can
   reach the 30B.
   - It refuses if any llama-server is up on the default port, if the GPU is
     held (gpu_guard contention, a RUNNING sim session, or another live
     L4/L4b), if free RAM is under 20 GiB, if free disk is under 25 GiB, or if
     the STOP file exists.
   - It waits on `/health`, not the open port.
   - It measures prompt-eval and generation tok/s (llama-server `timings`,
     `cache_prompt` off, 128 generated tokens with `ignore_eos`), plus VRAM,
     server working set and available RAM, at each setting of 48, 40, 32 and
     24.
   - It stops the server by PID after each setting (`taskkill /PID /T`, then
     `/F`, then the Popen handle). It checks that the PID is gone and that VRAM
     is back within 300 MiB of the pre-start baseline.
   - Every exit path stops the server: exception, `/health` timeout, STOP file,
     running out of budget. A hard kill of the job is covered by the Windows
     job object and by the factory's tree kill.
2. **L4b decides** (`scripts/night_l4b_qwen3_extraction.py`, queued after L4
   and allowed to own the GPU).
   - **Test set:** the same 240 E-G1 items, the same wire system prompt
     (sha256 `4c832e7e…`), the same parser and the same grader.
   - **Arms:** local 7B against local 30B, both on servers the job starts and
     stops, at $0.
   - **Frozen inputs:** the items were rebuilt from the 09-26 seed. The rebuild
     matched the receipt's census, ids, strata and first user message, apart
     from `rows_read`/`after_seen_max`, which grow with the corpus by design.
     The items are frozen in
     `news_corpus/_frozen/bakeoff_E-G1_items_frozen.json`, sha256
     `eba693d39c94…`, which is gitignored along with the corpus.
   - **Decision rule, written into the receipt before the first item:** replace
     the 7B for L2 typing only if all three hold:
     - field accuracy is at least +3.0 points higher;
     - the paired t is at least 2.0;
     - the nightly typing backlog at the 30B's measured s/item fits in 8 hours.

     If any condition fails, the answer is `KEEP_7B` and the 30B file becomes a
     candidate for the archive drive. An unfinished comparison is `INCOMPLETE`,
     never a quiet KEEP.
3. **The night-folder defect is fixed.** `night_factory` fixed its output
   folder once, at import. The always-on lab imports it into a process that
   runs for days, so after midnight the lab filed receipts under yesterday's
   date while checking today's folder for "already ran". The folder is now
   resolved at write time. `run_job` pins one folder per launch (receipt, log,
   and the child's `NIGHT_RUN_DATE`). The CLI `main()` pins its own night for
   its duration.

**Continuation (same evening): what the second builder added.**

4. **The power plan is a named refusal too** (`REFUSED_MAY_SLEEP`). It calls
   `night_factory.refuse_if_the_machine_may_sleep()` rather than copying it. A
   17 GiB load that the machine can suspend halfway through measures the
   suspend, not the model.
5. **The job's own budget counts awake seconds** (`AwakeBudget`, the same
   poll-gap rule as `night_factory.await_within_box`), so eight hours of Modern
   Standby do not spend a 50-minute budget. The factory's box is still the
   authority that kills the job, and it kills it by PID tree.
6. **A hard kill cannot leave 17 GiB mapped.** The server is bound to a Windows
   job object with `KILL_ON_JOB_CLOSE` (`llama_server.bind_lifetime`, the same
   helper the 7B uses). A test now terminates the job process with
   `TerminateProcess`, so no user code runs, and checks that the fake server's
   PID is gone.
7. **Receipts:**
   - Each receipt carries a `run_id` (UTC stamp + PID), `model`, the
     `n_cpu_moe` sweep and the awake/slept budget.
   - Each setting records its model and its knob, plus tok/s, VRAM loaded and
     peak, server RSS peak and the minimum available RAM. Peaks are sampled
     after every call, not taken once.
   - Writes are atomic (`disk_guard.atomic_write_json`) to `<job>_runNN.json`
     at the first NN that does not exist, so a second run cannot overwrite the
     first.
   - Under the factory, `--out` is now forwarded, so the mid-run flushes land
     in the factory's own receipt file.
8. **A refusal costs seconds.** L4 hashes the 17 GiB file only once the
   preflight has cleared. L4b runs its preflight before it rebuilds the frozen
   items or scans the corpus for the backlog.

**Did it run tonight?** No. Both jobs were run once for real at 22:05 HKT, and
both refused cleanly by name. No server was started, and the 7B on 8080 was
left running:

- `backend/data/optimus/l4_live_proof/L4_qwen3_measure_refusal_20260927T140538Z.json`
- `backend/data/optimus/l4_live_proof/L4b_qwen3_extraction_refusal_20260927T140610Z.json`

Both went to a separate folder on purpose. A REFUSED receipt in today's night
folder counts as "ran today" for the lab's idle queue, and would have used up
today's turn.

| check | value | floor | refusal |
|---|---|---|---|
| RAM available | **0.6 GiB** | 20 GiB | `REFUSED_RAM` |
| sim session | **RUNNING** | none | `REFUSED_GPU_LOCK_HELD` |
| default port 8080 | **llama-server PID 146528** (not this job's) | free | `REFUSED_SERVER_UP` |
| GPU | **5,460 MiB** unaccounted for | < 3,072 MiB others | `REFUSED_GPU_CONTENDED` |
| power plan | AC standby 0 (never) | never | none |
| disk C: | ~215 GB free | 25 GB | none |

The earlier 21:17 HKT preflight showed 3.0 GiB of RAM and a RUNNING sim.

So no tok/s number exists yet. L4 and L4b stay in `LAB_IDLE_QUEUE` and run the
next time the machine has room. Two lab behaviours decide when that is:

- The lab holds any GPU-owning job in `GPU_BUSY` while the 7B is listening.
- One REFUSED receipt counts as that job's turn for the date. Only a TIMEOUT
  gets a retry.

So on a night when the sim runs, the first dispatch refuses and the next
attempt is the following date. That is a lab policy question, and this change
does not alter it.

**What would move the decision:** the 30B wins only on better reading that also
fits the night. The 7B's E-G1 field accuracy is 62.2% and DeepSeek's is 63.1%,
so a +3-point gain would put the local 30B ahead of the paid reader. If it does
not win, the right move is to archive the 17.28 GiB file, not to keep it "in
case".
