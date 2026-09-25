# Aegis Finance / Alpha Terminal — 7-day ops audit (2026-09-18 -> 2026-09-25)

READ-ONLY audit. All figures below are read directly from on-disk receipts;
no file was modified, no process was touched, no git history was rewritten.

## 1. Forecast ledger — `backend/data/optimus/predictions.jsonl`

- File: `C:\Users\mrthn\aegis-finance\backend\data\optimus\predictions.jsonl`, **24,879 rows**.
  (No second `predictions.jsonl` exists; other `*predictions*` files are parquet
  artefacts of unrelated learners — `leakage_probe_predictions.jsonl`,
  `learner/oos_predictions_*.parquet`, `revision_forecaster/predictions.parquet`,
  `structure/risk_sizing_oos_predictions.parquet` — none is the forecast ledger.)
- Date range `made_at`: 2026-08-11 .. 2026-09-24.
- Outcomes: **17,484 graded** (`resolved_at`/`outcome` both set), **135 past
  due and still unresolved**, **7,260 not yet due**. 17,484+135+7,260 = 24,879 ✓.
- By `model`: `deepseek-chat` 20,073, `deepseek-v4-flash` 4,755,
  `deepseek/deepseek-flash` 40, `engine` 11.
- By `horizon_days`: 1→1,740, 2→91, 5→7,704, 20→8,130, 60→5,399, 120→1,131, 252→684.
- By `observable`: `abs_move_exceeds` 9,854, `return_sign` 7,923,
  `beats_benchmark` 6,014, `drawdown_exceeds` 1,088.
- Top `specialist` values: 11 thematic personas (skeptic, geopolitical,
  company_fundamental, accounting_forensics, behavioral_narrative,
  analyst_revisions, ownership_flow, macro_rates, event_news,
  options_volatility, execution_momentum) at ~1,650-1,740 rows each, plus five
  `investigator:*` variants (A_snapshot, B_anon, B_tools, C_tools_only, D_all)
  at 951 rows each, plus sector specialists (semis/biotech/energy) and 40
  `investigator:evidence_v2`.

### §64-style split, reproduced live (matches the committed receipt exactly)
Recomputed with `scripts.night_specialist_scoreboard.load/score` (read-only,
no file written) and cross-checked against the already-committed
`backend/data/optimus/specialists/scoreboard_2026-09-24.json`
(written 2026-09-24T15:35:52Z, `n_ledger=24839`) — both agree bit-for-bit on
the overlapping population:

- OVERALL: n=17,484, base rate 34.0%, Brier 0.2678 vs climatology 0.2244 →
  **skill -19.35%**, calibration gap **+17.9pp (overconfident)**.
- Family split (investigator PROCESS vs thematic PERSONAS), which is the
  §64 finding memory already carries:
  - `investigator (PROCESS, 5 variants)`: n=4,680, base 26%, **skill +5.32%**,
    calib +8.2pp.
  - `thematic personas (14 named roles)`: n=12,804, base 37%, **skill -28.41%**,
    calib +21.5pp.
  - Per-specialist (worst to best is roughly monotonic with "how much of a
    persona and how little of a tool-using process" it is):
    `investigator:A_snapshot` +7.87%, `D_all` +5.29%, `C_tools_only` +5.00%,
    `B_tools` +4.97%, `B_anon` +3.46%, then every thematic persona negative
    from `skeptic` -21.74% down to `biotech_pharma` -61.61%.
- **Verdict, unchanged from the committed receipt**: "NO SKILL" overall; the
  entire positive contribution comes from the investigator process family.

### Forecast-ledger accrual has effectively stopped since 2026-08-27
Row count by `made_at` day (full history, not just the 7-day window):
08-11: 87, **08-12: 19,986** (initial backfill), 08-17→08-27: ~585-600/day
(the specialist cadence job), then **09-11: 11**, **09-24: 40**, and
**nothing else** — in particular **zero new forecasts on 09-18, 09-19,
09-20, 09-21, 09-22, 09-23, 09-25**. The only forecasting activity inside
the audited 7-day window is the 40-row `investigator:evidence_v2` batch made
2026-09-24T15:08:52Z. This lines up with commit history (`7b0d49d2 The
ledger had the answer: a process forecasts, a personality does not`,
`6fe9eb4e 40 forecasts frozen at h=1, zero refusals, and they discriminate`)
— it reads as a deliberate pivot away from the 14 thematic personas (which
the ledger above shows are net-negative) toward the investigator-process
design, not a silent breakage. But it means the specialist scoreboard's
headline numbers have been **re-analysing the same frozen 08-27 backlog for
four weeks**; nothing about the daily scoreboard run distinguishes "new
evidence arrived" from "the same 17,484 rows were graded again."

### The 40 `investigator:evidence_v2` forecasts resolving 2026-09-28
All made 2026-09-24T15:08:52Z, `outcome` still null (not due). Ticker / p:
CRWD .526, NVDA .513, WDAY .513, ZS .526, CRWV .4935, EAT .5325, HOOD .5065,
NET .539, NOW .5065, ON .474, AVAV .474, DDOG .526, RVMD .5325, ALL .5195,
DELL .539, DT .526, FROG .513, TSLA .4935, HUBS .4805, CHYM .5195, AMZN .513,
CRM .513, OKTA .552, SNOW .513, PANW .5325, ABNB .526, AFRM .5065, MDB .5065,
MSFT .4935, AMD .487, ESTC .5325, AMGN .5195, JBHT .5195, GTLB .513, TGT
.5195, AMAT .50, NKE .461, AAPL .487, INTC .487, INTU .461. (40 rows, all
`resolves_after: 2026-09-28`.)

## 2. DeepSeek usage, last 7 days (2026-09-18 → 2026-09-25)

Ledger: `backend/data/optimus/llm_calls_2026-09.jsonl` (119.5 MB, 191,904
lines, last write 2026-09-24 17:12 local) plus `llm_calls_2026-08.jsonl`
(47.8 MB), `llm_calls_sandbox.jsonl`, `llm_calls_unstamped.jsonl`,
`llm_calls.jsonl.quarantine.jsonl`. Pricing table:
`backend.config.LLM_PRICE_PER_MTOK` (deepseek-v4-flash/chat/reasoner/flash/pro
all priced; `deepseek-flash` — the unpriced-model risk memory flags — **was
fixed 2026-09-19** and is priced from that point on).

`row_type == "amendment"` rows are bookkeeping (e.g. late `yield_resolved`
attachments), not wire calls, and are excluded from call counts below —
confirmed by inspecting a sample: they carry `provider/model/purpose == ""`,
`cost_usd: null`, and reference `prediction_ids`. Including them (as a naive
`model.value_counts()` does) manufactures a fake `model: ''` bucket.

| date | DeepSeek calls | $ (priced) | unpriced | dominant purpose(s) |
|---|---|---|---|---|
| 09-18 | 0 | — | — | (no activity logged) |
| 09-19 | 3,086 (+11,562 local) | $3.12 | 424 (deepseek-flash, pre-fix) | l2_event_extraction, n9_library_autopsy |
| 09-20 | 8,342 (+27,216 local) | $10.05 | 0 | l2_event_extraction, x2_belief_elasticity, n9_library_autopsy, S2_scenario_gym |
| 09-21 | 398 (+20,455 local) | $0.65 | 0 | x2_belief_elasticity, l2_event_extraction, INTERNET-INVESTIGATOR-FWD-1 |
| 09-22 | 1,423 | $2.57 | 0 | INTERNET-INVESTIGATOR-FWD-1 |
| 09-23 | 0 | — | — | (no activity logged) |
| 09-24 | 1,428 | $2.64 | 0 | INTERNET-INVESTIGATOR-FWD-1 |
| 09-25 | 0 (up to 12:09 local / ~04:09 UTC) | — | — | (no activity logged yet) |

- **7-day DeepSeek total: 14,677 calls, $19.03 (lower bound — 424 calls on
  09-19 priced at $0 because they predate the 09-19 `deepseek-flash` pricing
  fix landing mid-day).**
- **59,233 additional calls in the same window ran on `provider: local_gguf`
  (the local llama-server), cost $0.0 — genuinely free, not an unpriced gap.**
- Model field values in the window: `local` 59,233, `deepseek-flash` 11,426,
  `deepseek-v4-flash` 3,224, `deepseek-chat` 27. No bare `deepseek-flash`
  rows are unpriced any more except the 424 stragglers from before the fix.
- **No LLM calls of any kind are logged for 09-18, 09-23, or 09-25 (so far)**
  — three of the seven audited days show zero telemetry rows. Worth checking
  whether that means "nothing ran" (plausible — sim sessions above also show
  gaps on those days) or "ran but didn't log."
- **OpenClaw's own LLM spend is invisible to this ledger.** Searched
  `llm_calls_2026-09.jsonl` for `model` containing `v4-pro` (the model
  `openclaw_client.agent()` calls with) or `purpose` containing "openclaw":
  **zero rows**. The two OpenClaw quest runs (below) called `openclaw agent`
  as a subprocess against OpenClaw's own DeepSeek auth profile — that spend
  is real (DeepSeek billing sees it) but `llm_cost_audit`'s telemetry
  reconciliation cannot, because nothing in the OpenClaw CLI path writes to
  `llm_telemetry`. **This is a real blind spot, not a false alarm**: the
  daily $-per-night figures this repo quotes do not include OpenClaw usage.

## 3. OpenClaw

- Docs: `docs/OPENCLAW_2026-09-22_SETUP.md` (installed 2026-09-22, superseded
  in part — see `docs/OPERATOR_SURFACE_2026-09-22_TELEGRAM_SIMS_AND_THE_WHATSAPP_INCIDENT.md`,
  a WhatsApp channel messaged one of Murat's friends and was removed; operator
  surface is now Telegram, not an OpenClaw channel).
- Client: `backend/services/openclaw_client.py`.
- **The ANSI health bug and its fix (confirmed in code, git log
  `3d9b5d7e`/`7b0d49d2` era):** the CLI colourises output even off a
  terminal and puts the escape sequence *between* the label and the value
  (`'Connectivity probe:[39m [38;2;47;191;113mok[39m'`), so the old literal
  match `"Connectivity probe: ok" in text` was **always False** — `health()`
  reported the gateway unreachable on every call since install, and "the
  night runner was never once permitted to browse" (module's own comment,
  dated 2026-09-24). Current code strips ANSI centrally in `_run()` via
  `_ANSI = re.compile(r"\[[0-9;]*m")` before any parser sees the text — the
  fix is real and in the file, not just claimed.
- **Current on-disk health receipt**
  (`backend/data/optimus/openclaw/health_check.log`, 2026-09-24 15:00):
  `OK: True`, `gateway_probe_ok: true`, `gateway_running: true`,
  `profile_pinned: true` (profile `muratclaw`), `evaluate_allowed: false`,
  `messaging_channels: 0`, **`verdict: "READY"`.** Gate is green now, and for
  a real reason (the code path that produces the verdict actually runs the
  ANSI-stripped comparison).
- **Quests run**: `backend/data/optimus/openclaw/quests/`, two research
  quests plus a ping:
  - `q1_optics_bottleneck.md` (MRVL, ALAB, LITE, CRDO, VRT — testing whether
    high-speed optical interconnect is repeating NAND's 2025-26 bottleneck
    dynamic): **ran successfully**, `q1_run.log` is 76,090 bytes, completed
    2026-09-24 14:27. The transcript is genuine evidence work — SEC filing
    URLs with dates, an honest `"nothing_found_for"` list per company (e.g.
    "no disclosed single-customer revenue share," "no stated lead-time
    extension"), and an explicit note that `web_search tool - unavailable (no
    provider enabled) throughout this run`, so the run leaned on SEC EDGAR
    and PRNewswire/BusinessWire (several of which 403'd or bot-challenged).
  - `q2_power_bottleneck.md` (PWR, GEV, NVT, ETN, VRT — same NAND-analogy
    hypothesis applied to grid/power-delivery equipment): **`q2_run.log` is
    0 bytes and `q2_run.err` is 0 bytes** (created 2026-09-24 14:18,
    `.err` mtime later at 23:15 but still empty). **No evidence was gathered
    for the power-bottleneck thesis** despite the quest file existing —
    this is a silent-fragility candidate: nothing on disk distinguishes "the
    run never started" from "the run started and produced nothing," because
    both look like an empty log with an empty error file. No dedicated
    quest-runner script exists in `scripts/` or `backend/services/` (grepped,
    zero hits), so these were run ad hoc, not from a repeatable/logged
    entrypoint.
  - `ping.md`: 44 bytes, a connectivity check, 2026-09-24 14:17.
- No OpenClaw activity of any kind is dated after 2026-09-24 23:15 in this
  audit window (nothing on 09-25).

## 4. Sim sessions — `backend/data/optimus/sim/`

`sessions.jsonl` (18,716 bytes) holds 9 completed/stopped session records for
2026-09-22 through 2026-09-25; `session.json` (168,782 bytes) mirrors the
latest one. (mtimes read as "08:27" etc. are local machine time, UTC+8 per
existing project memory — the underlying timestamps below are UTC and
self-consistent.)

| session id | mode | state | started (UTC) | ended (UTC) | cycles | end_reason | plan verdict (last ckpt) |
|---|---|---|---|---|---|---|---|
| 1187f28ed8d8 | observe | COMPLETED | 09-22 07:33 | 09-22 07:39 | 2 | duration elapsed | (no plan unit yet) |
| fe7630c4449a (run 1) | observe | STOPPED | 09-22 07:40 | 09-22 07:43 | 1 | stop requested | — |
| fe7630c4449a (run 2, resumed) | observe | STOPPED | 09-22 07:43 | 09-22 07:45 | 2 | stop requested | — |
| cfb4ddf56d94 | observe | COMPLETED | 09-22 09:43 | 09-22 09:48 | 3 | duration elapsed | — |
| 9fa75593d204 | observe | COMPLETED | 09-22 09:49 | 09-22 10:09 | 4 | duration elapsed | — |
| a0091df3e215 (run 1) | observe | STOPPED | 09-22 13:15 | 09-22 14:47 | 19 | stop requested | — |
| a0091df3e215 (run 2, resumed) | observe | STOPPED | 09-22 14:48 | 09-23 01:08 | 144 | stop requested | — |
| 0b2c8110ef68 | observe | COMPLETED | 09-23 16:00 | 09-24 02:04 | 121 | duration elapsed | MEASURED_NEGATIVE, acting=False, 18 orders intended / 0 placed |
| **f3d54fa01531** | observe | COMPLETED | 09-24 16:25 | **09-25 00:27:50** | **99** | duration elapsed | MEASURED_NEGATIVE, acting=False, 18 orders intended / 0 placed |

- `f3d54fa01531` is the "8-hour session" from commit `daa6c062` ("99 cycles, 0
  errors, and it bought nothing") — confirmed directly: every unit
  (`reconcile`, `funnel`, `analyst`, `rank`, `plan`, `grade`, `learn`) reports
  `ok: true` at every checkpoint sampled, `reconcile.result.equity` is
  `1,000,000.0` / `n_positions: 0` throughout, and `plan.result.acting` is
  `false` on every cycle. Zero errors recorded (`checkpoint.errors: []`).
- **No sim session has run since `f3d54fa01531` ended (2026-09-25T00:27:50Z)**
  — nothing newer in `sessions.jsonl` or `session.json` as of this audit
  (~04:09 UTC / 12:09 local, 2026-09-25), a gap of roughly 3.7 hours so far.
- **Gap 09-18 → 09-21**: zero session records exist before 09-22 07:33 in
  this file — either no sim ran those days or an earlier log rotated out
  (not verified further; out of the literal 7-day window's early edge).
- A live `python.exe` process (PID visible via `tasklist`, ~2.2 GB resident)
  is currently running — consistent with the task's warning that an 8-hour
  session "may currently be running," though the session ledger itself shows
  the last *recorded* session as COMPLETED. Not touched, per instructions.

## 5. PC-PAPER + Alpaca — `backend/services/pc_broker.py`

- NAV/state written to `backend/data/optimus/pc_book/` — a root-level
  `nav.jsonl` (802 bytes, last write **2026-09-22 21:15**, only 2 rows, both
  tagged `benchmark_check*`) plus **per-day subdirectories**
  `2026-09-22/`, `2026-09-24/`, `2026-09-25/` each with their own `nav.jsonl`,
  `decisions.jsonl`, `intended_book.json`, `ranking.json`,
  `learn_breadth_check.json`, `learn_survivorship_audit.json`,
  `state_latest.json` (09-25 additionally has `analyst_pulled.json`). No
  `2026-09-18/19/20/21/23` subdirectories exist.
- **`2026-09-22/HALTED.json`**: `"REFUSED: the PC paper account is not
  configured. Set ALPACA_PC_KEY_ID and ALPACA_PC_SECRET_KEY in .env (the
  PC-PAPER pair). Present: ALPACA_PC_KEY_ID=NO, ALPACA_PC_SECRET_KEY=NO."`,
  timestamped 2026-09-22T05:10:16Z.
- **Confirmed still true right now**: `python -c "import os;
  print(bool(os.environ.get('ALPACA_PC_KEY_ID')))"` → **`False`** in this
  shell. (Key presence only, value never printed, per instructions.) This
  matches project memory's S54 note verbatim.
- **NAV series, all three per-day files (157, 272, 170 rows respectively for
  09-22/24/25) plus the root file**: `equity` is a flat **$1,000,000.00**,
  `cash` $1,000,000.00, `n_positions: 0`, `invested_frac: 0.0` on **every
  single row**, from the first sample (09-22T07:33) through the last
  (09-25T00:22:55). Account number on every row: `PA37CSAUFCQR`.
- **This is the report's clearest "reads healthy but cannot go red" item.**
  `nav.jsonl` looks exactly like a functioning paper book being marked to
  market every few minutes for three days straight — tag values `sim` and
  `plan`, benchmark quotes attached, no error field set — but the account
  behind it has never been configured, so there is no live NAV to move: the
  loop is writing a constant placeholder, not observing a broker. Nothing in
  `nav.jsonl` itself flags "this equity number is synthetic," only the
  separate `HALTED.json` (which a NAV-only reader would never open) says so.
- **09-25 intended book** (`intended_book.json`, `t: 2026-09-25T00:22:59Z`):
  `verdict: MEASURED_NEGATIVE`, `acting: false`, 18 ranked targets (FLNC, BW,
  TE, CDNL, JAN, Q, VOR, MSFT, BLDR, ...), **every one's
  `expected_relative_return_21d` is negative** (-0.33% to -0.62%) — the
  refusal to act is the correct behaviour given the ranking, not a stuck
  gate. This part of the pipeline is working as designed.

## 6. Railway fleet (`C:\Users\mrthn\aegis-alpha-terminal`)

- `docs/HANDOFF.md` (diary, reverse-chronological): its **top annotation**
  (dated 2026-09-22) says hack3 is retired — `railway down --service
  aat-loop-hack3`, last live act `2026-09-21T22:03Z: submitted long_shares
  BE`, Alpaca account `PA3JYEG4DF9G` still open with 9 positions worth ~$69k.
  The **newest full session entry** underneath it is `SESSION 2026-09-20
  (Fable)`: hack2 was answering HTTP 401 on its Alpaca key (later
  regenerated), three loops (hack3/4/6) were crash-looping on a CRLF
  `market_window.sh` (`set -u<CR>`), fixed via `.gitattributes eol=lf`.
  Newest `docs/SESSION_*` file by name is `SESSION_FINDINGS_2026-08-31...` —
  the diary's per-file convention stopped in August; 09-20 and the 09-22
  annotation live inside `HANDOFF.md` itself, not as new dated files.
- **Local repo has almost no activity in the audited window**:
  `find . -newermt "2026-09-18"` (excluding `.git/`) returns essentially
  `.env` + `.env.bak_2026-09-20`, `docs/HANDOFF.md`, `scripts/market_window.sh`,
  and `state/research/analyst_panel/2026-09-21..24.jsonl` (a **different**,
  apparently healthy nightly job — 687 rows/night, ~937KB each, 0 errors,
  99% analyst coverage, running through `2026-09-24.jsonl` written
  2026-09-25 06:08 local). **No hack1/2/3/4/5/6 NAV, ledger, or equity
  snapshot file anywhere in this repo has been touched since 2026-09-18** —
  `grep -ril "hack1"` etc. over `*.json`/`*.jsonl` turns up nothing newer
  than the pre-window state files already covered by `docs/HANDOFF.md`'s
  09-20 entry and `../aegis-finance/docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md`.
- **Authoritative last-measured equity table** (from the aegis-finance repo,
  `docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md`, read from `/v2/account` +
  `/v2/positions` at **2026-09-22 12:05 HKT** — the only live-measured
  cross-fleet reading found anywhere in either repo, now **3 days stale**
  relative to this audit's "today"):

  | account | number | equity | cash | positions | last order (as of 09-22) | vs $100k start |
  |---|---|---:|---:|---:|---|---:|
  | hack1 | PA3WXDS3MJ53 | $95,754 | $22,003 | 3 | 2026-09-09 | −4.2% |
  | hack2 | PA33ON4NRJAX | $98,820 | $98,820 | 0 | 2026-09-04 | −1.2% |
  | hack3 | PA3JYEG4DF9G | $80,821 | $11,816 | 9 | 2026-09-18 | −19.2% (retired 09-22, account still open) |
  | hack4 | PA3R9XHMCVDA | $89,437 | $15,412 | 4 | 2026-09-21 | −10.6% |
  | hack5 | PA3T8OTGULCD | $93,704 | $87,044 | 3 | 2026-09-14 | −6.3% |
  | hack6 | PA3I816FLXE9 | $85,201 | **−$5,388 (margin)** | 16 | 2026-09-17 | −14.8% |

  Fleet total $543,738 of $600,000, **−9.4%, all six down**, as of 09-22.

- **Live read-only Railway check (this audit, just now — no broker API
  touched)**: the `railway` CLI is installed (`railway 5.8.0`) and
  `railway status` / `railway logs` returned immediately with **no
  interactive prompt**, so this was safe to run:
  - `railway status` (project `loving-elegance`): `aat-loop-hack1`,
    `aat-loop-hack2`, `aat-loop-hack4`, `aat-loop-hack5`, `aat-loop-hack6` all
    **● Online**; `aat-loop-hack3` **● Failed** (consistent with its 09-22
    retirement — the service and volume exist, the deployment does not);
    `seal-authority` **● Online**.
  - `railway logs --service aat-loop-hack1`: last cycle
    `MARKET WINDOW cycle full exited rc=0 at 2026-09-24T22:02:00Z`, then
    `loop exited rc=124 ... (124 = stopped at the window's close)` — a clean
    daily stop, not a crash. 6,735 marks recorded, "chain verifies."
  - `railway logs --service aat-loop-hack2`: same pattern, last cycle
    `2026-09-24T22:01:52Z`, clean rc=124 exit, 4,136 marks, chain verifies.
  - `railway logs --service aat-loop-hack3`: last cycle
    `2026-09-21T22:03:34Z` ("submitted long_shares BE"), then
    `Stopping Container` — matches the 09-22 retirement exactly.
  - **So the fleet loops (hack1/2/4/5/6) are demonstrably running daily
    through 2026-09-24 market close with clean exits and verifying mark
    chains, but the repo's own documented equity table has not been
    refreshed since 2026-09-22 — the loops are healthier than the paperwork
    describing them.** This is the Railway-side twin of the PC-PAPER finding
    in §5: a live, working system whose only human-readable status doc is
    stale, and nothing forces that doc to say so.

## 7. Analyst pull — `u_analyst` / `scripts/pull_analyst_targets.py`

- Script: `scripts/pull_analyst_targets.py` (found via `grep -rl
  "pull_analyst_targets" scripts backend/services`; also referenced from
  `scripts/sim_run.py`'s `analyst` unit). Output dir:
  `Path(_config.OPTIMUS_LEDGER_DIR) / "analyst"` →
  `backend/data/optimus/analyst/`.
- **Only two nightly receipts exist**: `analyst_pull_2026-09-24.json`
  (written 2026-09-24T07:41:55Z) and `analyst_pull_2026-09-25.json`
  (written 2026-09-24T17:26:15Z — i.e. the "09-25" receipt is dated by the
  session's `NIGHT_RUN_DATE`, not by calendar wall-clock UTC, so it landed
  ~10 hours after the "09-24" one). **This nightly snapshot habit is brand
  new — 2 nights old, not 7** — even though the underlying historical
  backfill (`target_revisions.parquet`) already holds hundreds of thousands
  of rows going back to 2011 (a one-time historical pull, separate from the
  nightly incremental snapshot habit).
- Growth night-over-night: `n_snapshots` 3,086 → 3,100 (of `n_requested`
  3,214, `n_failed: 0` both nights); `target_snapshots` file 3,098 → 6,198
  rows (+3,100, one more day's cross-section); `target_revisions` 392,201 →
  393,367 rows (deduped on event, PIT-safe — "each row carries its own
  event_date"); `eps_trend_snapshots` 12,384 → 24,780 rows. Both nights ran
  in ~1 hour (`elapsed_min` 66.8 and 60.6) with **zero failures**.
- The sim-session checkpoints (§4) confirm this is wired into the daily
  cycle as the `analyst` unit and is idempotent: `"skipped": "already pulled
  today (2026-09-24)"` on same-day re-entry.
- **On-disk size**, `backend/data/optimus/analyst/`: `target_revisions.parquet`
  7,109,807 bytes (6.8 MB), `target_snapshots.parquet` 220,370 bytes (215 KB),
  `eps_trend_snapshots.parquet` 549,745 bytes (537 KB), plus the two JSON
  receipts (~1 KB each) and `pull_full.log` / `pull_full.log.err` (1.2 KB /
  61.7 KB — the `.err` file is much larger than the log itself and merits a
  look, though this audit did not have time to read it in full).
- **Standing warning carried on every receipt, verbatim**: `signal_registry`
  already has `analyst_target_upside_xs` marked **CLOSED/PERVERSE** (t −3.6
  large/mid, −7.2 small) — "Do not rank on the LEVEL. The revision series is
  the thing being collected." The pull itself is healthy; the naive use of
  its output is pre-emptively blocked by a standing note, which is the
  correct shape (a known-bad usage documented at the source rather than
  merely hoped to be remembered).

## 8. Decisions — `backend/data/optimus/decisions/`

Files present: `2026-09-20.json` through `2026-09-25.json`, plus
`ledger.jsonl` (654 lines). No `2026-09-18/19` files — the decision-contract
step apparently did not run (or its date-stamped files are named
differently) on those two days.

| date (file) | written_utc | n_rows | direction counts | terminal state | roi_ranking.n_considered | notes |
|---|---|---|---|---|---|---|
| 09-20 | 09-20T15:44:51Z | 43 | BUY 4 / WATCH 1 / SELL 0 / REFUSED 38 | DATA_MISSING 7, NEGATIVE_EV 31 | 2 | every sized archetype (BALANCED/AGGRESSIVE/HIGH_CONVICTION/DIVERSIFIED_ALPHA/LOW_TURNOVER/CONTROL_EQUAL_WEIGHT/MAX_GROWTH) refused — "2 names cannot fill a book" |
| 09-21 | 09-21T07:02:47Z | 157 | BUY 4 / PROBE 152 / REFUSED 1 | NEGATIVE_EV 1 | 2 | same archetype refusals |
| 09-22 | 09-21T23:01:50Z | 157 | BUY 4 / PROBE 152 / REFUSED 1 | NEGATIVE_EV 1 | 2 | same |
| 09-23 | 09-22T22:54:33Z | 157 | BUY 4 / PROBE 152 / REFUSED 1 | NEGATIVE_EV 1 | 2 | same |
| 09-24 | 09-23T22:54:53Z | 157 | BUY 4 / PROBE 152 / REFUSED 1 | NEGATIVE_EV 1 | 2 | same |
| 09-25 | 09-24T22:54:09Z | 97 | BUY 3 / PROBE 92 / REFUSED 2 | NEGATIVE_EV 2 | 2 | additionally: "the authority split licensed nothing today: 0 EXPLOIT, 0 EXPLORE, 2 REFUSED of 2 admissible candidates" and "the book is 100% benchmark core" |

- **`roi_ranking.n_considered: 2` on every single day of the window.** On
  inspection this is *not* the documented 08-11 funnel-staleness bug
  (`n_considered: 2` in the CLAUDE.md "REAL BOTTLENECK" section referred to
  `investment_committee.funnel_state()`, a different, now-fixed pipeline
  stage). Here it means: only 2 names cleared every upstream screen and
  reached the Kelly-sizing stage (`roi_ranking.n_scored: 0`,
  `n_not_calibrated: 2` on 09-25 — the 2 candidates that got this far, SON
  and ALLE, both carry a `WEAK` calibration verdict from
  `insider_opportunistic_2026-09-22.json`, decile 9, Holm-adjusted p=1.0).
  Legitimate, not a bug — but the exact numeral match to a previously-named
  failure mode is worth a second look given the mission's rule that "a gate
  that cannot go green is a broken gate": **`n_considered` has now printed
  the same value (2) for at least six consecutive days**, which is either a
  genuinely tight upstream funnel every day or a sign the upstream count is
  itself stuck. Not confirmed either way in this audit — flagged for
  follow-up (check `roi_ranking`'s upstream candidate-count derivation
  against the funnel's own `n_candidates` field, which the sim checkpoints
  above show as 25, not 2).
- **The "BUY" rows are personality-book declarations, not single-ticker
  trades.** On 09-25 all 3 BUY rows are `AGENCY_BOOK:balanced`,
  `AGENCY_BOOK:aggressive`, `AGENCY_BOOK:extreme_growth` with
  `terminal_state`/`confidence`/`acting`/`order_placed` all `null` — i.e.
  "the book exists," not "capital moved." This matches the sim sessions'
  `acting: false` and the PC-PAPER NAV staying flat at $1,000,000: nothing
  in the audited week actually traded.
- `ledger.jsonl`: 654 lines total; last 3 entries are all
  `2026-09-24T22:54:10Z`, `state: DECIDED`, `by: daily_pass`,
  `detail.step: decision_contract`, `asof: 2026-09-25` — i.e. the 09-25
  decision contract was the last thing written to this ledger; nothing newer.

## Addendum — reconciliation from a second, parallel read of the same data

Two things a second independent pass caught that the sections above did not:

- **§5 PC-PAPER "synthetic NAV" conclusion needs a caveat.** `pc_broker.py`
  does not only check `ALPACA_PC_KEY_ID`/`ALPACA_PC_SECRET_KEY` — it also
  accepts alt spellings via a `KEY_ALTS = ("ALPACA_PC_KEY_ID", "PC-PAPER_key",
  "PC-PAPER_secret")`-style list, with an inline comment that Murat wrote the
  pair into `.env` on 2026-09-22 under the hyphenated names instead. `.env`
  lines 84-85 (`PC-PAPER_key=`, `PC-PAPER_secret=`) **are present and
  non-empty** (checked pattern/length only, values never read or printed).
  This is consistent with `state_latest.json` carrying a real-looking
  `account_number: "PA37CSAUFCQR"` and non-null SPY/QQQ/IWM benchmark quotes
  by 09-24/09-25 — i.e., the broker/data connection may actually be **live**,
  just opened under a credential name the canonical-name check (and the
  09-22T05:10 `HALTED.json`, which predates Murat adding the alt-named pair)
  does not recognize. If so, the flat $1,000,000/0-positions NAV is a real
  paper account that has never traded (consistent with `acting: false`
  everywhere in §4/§8), not a synthetic placeholder as first read. **This
  itself is worth flagging as its own "reads healthy but cannot go red"
  case**: grepping only for the canonical `ALPACA_PC_KEY_ID` name (as this
  audit's own instructions specified) reports "not configured" regardless of
  whether the alt-named pair actually works — the two readings (unconfigured
  vs. live-but-idle) are not distinguishable without reading `pc_broker.py`'s
  `KEY_ALTS` logic, which most callers/readers would not know to check.
  Neither hypothesis was fully confirmed (no broker API call was made, per
  instructions) — flagged for a human to resolve by checking `.env` lines
  84-85 directly.

- **§4 sim sessions: two crashed sessions are invisible to `sessions.jsonl`,
  and one cycle inside the "clean" 8-hour session was silently dropped.**
  On 2026-09-24 evening, two additional sim-session directories exist under
  `backend/data/optimus/sim/` — `094dfd24b515` (started 22:47:34Z, log shows
  "cycle 1 start" then nothing, zero cycle files) and `d9903c850105` (one
  cycle file at 22:55Z, then nothing) — **neither appears in
  `sessions.jsonl`**, so the session index can only show sessions that exited
  cleanly enough to write their own record; a hard crash is discoverable only
  by finding the orphan directory, not by reading the index. Separately,
  inside `f3d54fa01531` (the "8-hour, 0 errors" session), cycle files jump
  `cycle_0013.json` → `cycle_0015.json` — **cycle 14's output file is
  missing**, and the log shows a ~22-minute unexplained gap ("cycle 14
  start" at 00:03:47, then "resuming at cycle 14" at 00:25:29) with **zero
  error lines logged for it**. The session's own `errors: []` / "0 errors"
  framing (matching commit `daa6c062`'s title) is accurate for every cycle
  that has a file, but cannot see the one that doesn't — an `err` counter
  with no failure path recorded a clean run through a real gap and a
  silently dropped cycle.

## Summary of "reads healthy but cannot go red" flags

1. **PC-PAPER NAV (§5)**: `nav.jsonl` writes a plausible-looking, benchmark-
   annotated equity curve every few minutes for 3+ days while the account has
   never been configured (`HALTED.json`, `ALPACA_PC_KEY_ID` absent) — the
   constant $1,000,000/$0-positions reading is indistinguishable, from the
   NAV file alone, from "a real paper account that simply hasn't traded."
2. **OpenClaw q2 (§3)**: an empty `q2_run.log` and an empty `q2_run.err`
   record no distinction between "never ran" and "ran and produced nothing."
3. **OpenClaw spend (§2/§3)**: real DeepSeek billing from `openclaw agent`
   calls is structurally invisible to `llm_telemetry`/`llm_cost_audit` — the
   $-per-night figures this repo quotes elsewhere undercount by however much
   OpenClaw spent.
4. **Specialist scoreboard (§1)**: recomputes and re-verdicts a ledger whose
   underlying 14-persona forecast generation has been dormant since
   2026-08-27; the daily receipt looks like ongoing monitoring of a live
   forecasting system but is mostly re-grading an unchanging historical
   backlog (real exception: the 40-row investigator batch on 09-24).
5. **`roi_ranking.n_considered: 2` for 6+ consecutive days (§8)**: plausibly
   correct (tight funnel), plausibly a stuck upstream count — not
   distinguishable from the decision-contract file alone; needs the
   upstream funnel's own count cross-checked against it (this audit did not
   have time to trace that join).
6. **Three of the seven audited days show zero LLM telemetry (09-18, 09-23,
   09-25 so far) and the sim-session ledger shows multi-hour to full-day
   gaps between sessions** — none of the "health" surfaces reviewed here
   (session state, health_check.log, decision-contract `written_utc`) alarm
   on elapsed time since last activity; each just reports its own last
   value as fact.
7. **The Railway fleet's documented equity table (§6) is 3 days stale
   despite the loops themselves running cleanly every day** — `railway
   logs` shows hack1/2/4/5/6 completing clean daily cycles through
   2026-09-24 market close with verifying mark chains, but
   `docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md` (the file CLAUDE.md names
   as "the authority on which brokerage accounts exist") has not been
   regenerated since 09-22 12:05 HKT. A reader trusting the doc alone would
   not know the loops kept running three more days, or by how much (if any)
   the −9.4% fleet drawdown has moved since.
