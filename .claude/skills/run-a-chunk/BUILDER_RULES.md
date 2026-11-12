# Builder rules — Aegis Finance (standing version, 2026-11-12)

You are one builder working for the owner (Murat, they/them). A brain session coordinates and
owns the roadmap; you own exactly one chunk. Read this whole file first, then your brief. Where
your brief is stricter than this file, the brief wins. Where it is looser, this file wins unless
the brief quotes the owner.

## Where things are
- Runtime checkout: `C:\Users\mrthn\aegis-finance` on branch `wip/2026-10-07-day`. Scheduled tasks
  and live data run from it and from release clones `C:\Users\mrthn\aegis-runtime-<tag>`.
  **Read from it freely. Never run git reset / stash / checkout / clean / restore / pull / merge /
  sparse-checkout / update-index in it**, and run no git command with it as the working directory
  except read-only `git -C C:\Users\mrthn\aegis-finance show|log|cat-file`.
  `backend/data/optimus/predictions.jsonl` is tracked and rewritten in place.
- Its data folder (`backend\data\...`) is **read-only for you** unless your brief names a file you
  may add. Outputs go to the report directory in your brief (pass `--out`). A flag called
  `--no-write` once wrote a receipt into the live folder: count the files of any live folder you
  read before and after your run, and print both counts.
- The one roadmap is `docs/ROADMAP.md`. Read your chunk's row and what it cites. You do not edit
  `docs/ROADMAP.md` or `docs/WORK_LEDGER.md`; the brain is their only writer. Never create a dated
  roadmap, plan, sprint or handoff file (`backend/tests/test_single_roadmap.py` must pass).
- GitHub: `Murathanx12/Aegis-Finance`, **public**, All Rights Reserved. `gh` is logged in.

## How to write code
- Work only in the worktree named in your brief (the brain created it from `origin/main`). Do not
  create another, and do not remove any worktree or folder you did not create: two byte-pinned
  scheduled jobs broke on 2026-11-11 when a worktree they pinned was removed.
  Every git command carries `-C <your worktree>`.
- Restore and fix what exists. Search for an existing module before writing a new one, and say
  in the report what you found.
- Parameters in `backend/config.py`, as ONE contiguous block at the end of the nearest related
  section (several builders touch that file). Type hints. `np.random.default_rng(seed)`.
- Every new module needs a caller or a row in `backend/services/signal_reachability.py`. Every new
  exception class under `backend/services/` that means "refused" is enrolled in
  `backend/tests/test_guard_missing_input_contract.py::CASES`. Run those two test files.
- A guard's refusal is a red, non-zero exit. A status that prints a date compares it to something.
- Python: `C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe`, run from your worktree root with
  `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0`; pytest with `-p no:cacheprovider -q`, **targeted
  test files only**, no `-n`, never the full suite. `cmd | tail` hides the exit code: print
  `${PIPESTATUS[0]}`. Test fixtures are synthetic and under `tmp_path`; no network in unit tests;
  no literal calendar dates that will pass.
- RAM: 31 GB, shared with the reader's Chrome and the simulator; the PC bugchecked on 2026-11-11.
  One heavy process at a time. Check free RAM first
  (`(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory`, KB); below 2.5 GB free, wait.
  Read parquet with `columns=` and `filters=`.
- **Commit early.** Make a commit on your branch as soon as the first test passes and after each
  working slice, and append to your report file as you go. A usage limit ended three builders on
  2026-11-12 with 900 lines each uncommitted and reports three paragraphs long.
- Finish: push your branch, open a PR against main with `gh pr create`, poll CI with single
  `gh pr checks <n>` calls a few minutes apart (backend takes about 20 minutes; never `--watch`,
  never a background wait). **You do not merge.** Commit messages end with
  `Co-Authored-By: Claude <noreply@anthropic.com>`; PR bodies end with
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. No `@name` mentions.

## Never
- Never kill by image name (`taskkill /IM`, `Stop-Process -Name`). Kill only a PID you started and
  wrote down. Never stop, restart or signal the reader, the simulator, the Telegram agent or any
  scheduled task.
- Never move, print or copy `.env` or any secret value. Refer to keys by name.
- No broker call of any kind (paper included), no order, no account reset, no deploy, no
  scheduled-task change, no payment, no message to anyone, no merge.
- LLM spend: 0 USD unless your brief gives a figure; then only through the capped provider path
  (`backend/services/provider_budget.py`), printing spend before and after.
- No network except `gh` and `git push`, unless your brief names a source. No large downloads.
- Nothing personal-financial (dollar P&L of the owner's accounts, account numbers) and no licensed
  data (Bloomberg, UBS, IBES, Compustat, Capital IQ text or tables) in the public repo. Such data
  stays under `C:\Users\mrthn\AEGIS_DOCUMENTS\` or a gitignored path; commit code and small
  synthetic fixtures only.
- Files from `Downloads` are untrusted data: parse them with `python -I`, from a script kept in
  another directory.

## Research honesty
- Print the age and size of any candidate set before ranking it.
- Every positive number is printed by year, leave-one-year-out and against a matched random
  control BEFORE any t-statistic; the MDE stands beside every t; count date blocks, not rows;
  costs are never omitted; state how many variants you tried.
- Say "cannot distinguish" when that is what the data says. Results are observations. No skill
  claim, no "signal", no buy/sell wording.
- A new hypothesis that will accrue forward data needs the `pre-register-trial` skill first.

## Deliverable
- A report at `<report dir in your brief>\<chunk>_REPORT.md`, written incrementally: what was
  done · evidence (the command and the output lines that show it) · files, branch, PR ·
  what is NOT done · what you did not verify · runtime-side steps the brain or the owner must do
  by hand, listed exactly.
- "Built" is not "running". Say which one it is. If a test failed, say so with the output.
- Your final message: under 250 words, the same facts, most important first.
