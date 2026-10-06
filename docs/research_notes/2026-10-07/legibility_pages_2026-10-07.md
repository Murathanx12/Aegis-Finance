# C19: four legibility pages, every number naming its receipt (2026-10-07)

Licence: PRODUCT_EXPERIMENT (display only). Read-only: no router builds, grades or writes anything.
Builder files: `backend/services/legibility.py`, `backend/routers/arena_v1.py`,
`backend/routers/legibility_v1.py`, `backend/tests/test_legibility_routers.py`,
`frontend/src/app/{arena,forecast-lab,theory-lab,health}/page.tsx`,
`frontend/src/components/legibility/receipts.tsx`; edits to `backend/main.py` (two `include_router`),
`backend/config.py` (`LEGIBILITY_STALE_HOURS`), `frontend/src/lib/api.ts` (types + 5 fetchers),
`frontend/src/components/sidebar.tsx` (new "Evidence" group).

## Rules the read side keeps

- **Newest by stamp, never mtime, never a literal date.** Each receipt kind is chosen by the run stamp in its
  file name (`roi_<date>T<hhmmss>Z`, `health_<YYYYMMDDTHHMMSSZ>`, `reputation_<date>`, ...). Its age is then
  computed at serve time from the receipt's OWN `generated_utc` / `written_utc` / `as_of`. An undateable
  receipt is `UNKNOWN`, never `FRESH`. mtime is used only as a parse-cache key.
- **STALE past `config.LEGIBILITY_STALE_HOURS[kind]`** (producer cadence + margin: ROI/book_dna 48 h, health 26 h,
  reputation / learning report / grade_forecasts / nn nightly 48 h, world state 24 h, walk-forward 14 d, hyp_lab
  ledger 7 d, twin boards 30 d, analyst weights 40 d). Every page shows a receipts strip (file, stamp, age, status)
  and a red STALE banner when any receipt is past its limit.
- **Null + `missing_because`**, never a zero. Every page lists "what is null today, and why".
- **Labels are copied, never upgraded.** The Arena prints `book_dna`'s `evidence.label` as written
  (`OBSERVED(n)` -> `EARLY_EVIDENCE` -> `REPLICATED` -> `VALIDATED_EDGE`); "proven" appears nowhere.
- **No secrets, no machine details.** Absolute paths are cut to repo-relative ones (`scrub`), notes naming a
  `.env` location are dropped, broker account numbers / cash / equity fields are not served, raw vendor rows
  (CRSP, analyst targets) are never served: only the derived board and weight summaries.

## Page -> endpoint -> receipt map

| page | endpoint | receipt(s) read (newest by stamp) | what is copied |
|---|---|---|---|
| `/arena` | `GET /api/arena/v1/latest` | `paper_accounts/roi_<date>T<hhmmss>Z.json` (broker-read preferred over `.nobroker`; the undated same-day copy skipped) + the `book_dna_<stamp>.json` that ROI receipt names in `aggregate.book_dna_receipt` | `aggregate.top_line`, `collapse_line`, `evidence_density_line` verbatim; n ahead / twins / controls / clusters; ex-ante bets; `book_dna.books` (category twin/control/strategy, sessions graded, evidence label, beta, cash, holdings, sub-windows); `book_dna.holdings_clusters`; `book_dna.losers` (error type + why); winners = strategy books with excess > 0 |
| `/arena` drawer | `GET /api/arena/v1/stories[?ticker=]` | `decision_story/stories_<YYYY-MM>.jsonl` + `alternatives_<YYYY-MM>.jsonl`; `decision_story/regret/regret_<run>.json` | decision rows, frozen alternatives, `regret_ledger.h_table(receipt, 5)` (shown only for the PC-PAPER book: C11 writes stories for that plan only) |
| `/forecast-lab` | `GET /api/legibility/v1/forecast-lab` | `reputation/reputation_<date>.json`; `learning_reports/report_<date>.json`; `night_factory_<date>/grade_forecasts_<date>.json`; `nn_lab/receipts/nightly_<stamp>.json`; `nn_lab/receipts/wf_<date>*.json`; `digest/world_state_<stamp>.json` + `digest/world_digest_<stamp>.json`; `analyst/reputation_weights_<month>.json` | calibration bins (h1/h5); skill per arm x observable x horizon with `kind` magnitude/direction, pooled n-weighted by kind x horizon (the only arithmetic on the page: a pooled mean of receipt numbers); the sigma_63 prior's held-out skill vs the LLM's (`closing.vol_prior`); trust per arm (news digest size/direction from the shadow grade, nn_lab members from the nightly) with the `WORLD_DIGEST_TRUST_*` rule printed; regime rows with both baselines and the receipt's own note ("not a finding before the first h5 grades (2026-10-09)..."); nn_lab tournament (the nightly's printed walk-forward table with ITS age, the newest walk-forward run's models x horizons with verdicts, the |y| magnitude IC); analyst reputation summary |
| `/theory-lab` | `GET /api/legibility/v1/theory-lab` | `hyp_lab/ledger.jsonl` (folded by `hyp_lab.load_state`); `hyp_lab/theory_*_DECLARATION_*.json` + `_RESULTS_*.json`; `hyp_lab/twin_board_SUMMARY_{STK,FT}_<date>_<n>.json` + rows `twin_board_<run>.jsonl`; the newest `docs/HANDOFF_*.md` carrying an "Honest sentence" on CRSP | every hypothesis with its state (mapping below), powered flag, confirm mean/t/MDE, declaration sha256 and run id; family posteriors (`hyp_lab.family_record` + `family_weight`); four columns per library rule (gross/gross = `pure_selection`, net/net = `fair_twin_net`, `net_minus_market`, `twin_full_round_trip_UPPER_BOUND`) by window, sticky vs basket toggle; the CRSP sentence quoted with its source plus the sticky board's counts |
| `/health` | `GET /api/legibility/v1/system-health` | `health/health_<stamp>.json` | rows grouped by verdict with fine states; evidence age now and at probe time; `process_census:*` rows; rows whose detail says "same output for" highlighted; task owners = `task_receipts.TASK_RECEIPT` x `config.HEALTH_TASK_CADENCE_H` joined to the receipt's `task:*` rows; one-line summary = `legibility.health_line`, pinned byte-identical to `scripts.daily_pass.step_health`'s headline by `test_health_line_is_the_daily_pass_line` |

404 when a page has no receipt at all; 422 on a malformed `ticker`/`limit`; 500 names the exception.

### Board choice (Theory Lab)

Per twin kind, SMOKE runs are excluded and the board with the MOST rules wins (newest stamp on a tie): the newest
STK run on 10-07 (`STK_2026-10-07_3`) is a 2-rule rerun and is not the board. Served today: sticky
`STK_2026-10-07_2` (301 rules, 277 scored), basket `FT_2026-10-07_1` (301). The other boards are named on the page
as "not served".

### Theory state mapping (`legibility.theory_state`)

| hyp_lab | state |
|---|---|
| status `DISCARDED_NO_REFUTATION`; verdict `REFUSED` | INVALID_EXPERIMENT |
| status `DUPLICATE_*` (no verdict); verdict `RETIRED_FROM_CURRENT_SEARCH` | RETIRED |
| verdict `MECHANISM_REJECTED`; `FAILED_VARIANT` **and powered** | FALSIFIED |
| `FAILED_VARIANT` **unpowered** | WEAKENING (an unpowered negative is not a falsification) |
| latest verdict positive after a non-positive one / non-positive after positive | STRENGTHENING / WEAKENING |
| positive verdict with a split whose primary mean <= 0 (theory cells) | REGIME_SPECIFIC |
| `CONDITIONAL_POSITIVE` / `CANDIDATE` | CONDITIONAL_SUPPORT / EARLY_SUPPORT |
| `CANNOT_DISTINGUISH`, or no verdict yet | HYPOTHESIS |

`powered` is `hyp_lab.is_powered` unchanged (explicit flag, else confirm t <= -2, else confirm MDE <= design
effect; unknown = not powered). Today: HYPOTHESIS 60, CONDITIONAL_SUPPORT 3, WEAKENING 22, FALSIFIED 2, RETIRED 16.
The three 10-06 theory cells (hi52, insider_hold, beat_streak) are FAILED_VARIANT and read WEAKENING because the
hyp_lab summary carries no confirm block to prove power; the page prints that rule beside them.

## What is null today, and why (10-07 ~06:00 UTC, the machine's receipts)

- **Arena decision stories: 404.** `backend/data/optimus/decision_story/` does not exist: no PC-PAPER plan cycle
  has frozen a story yet on this machine, so no regret receipt either. The drawer says so for PC-PAPER and says
  "none by construction" for every other book.
- **Arena: 5 accounts carry no evidence label** (`NO_LABEL`): ROI rows `book_dna` did not list (367 ROI rows vs
  362 book rows: the 3 agency accounts, hack3 CREDENTIAL_INVALID, one VOIDED). Each shows the reason.
- **Every label is `OBSERVED(n)`**: `book_dna`'s own evidence-density line ("only 1 of 147 books ahead of SPY has
  >= 21 sessions"). The page does not soften it.
- **System Health: no process census.** The newest health receipt (`health_20261006T175305Z`) predates C14's
  `process_census` probe; the page prints that reason until a new probe run writes the rows.
- **Forecast Lab regime rows:** 0 graded dates, trust 0 vs both baselines; the receipt's note says the first h5
  grades are 2026-10-09. **nn_lab:** every member's forward trust is 0 (0 graded dates), so the page prints
  "no model has earned forward weight" (derived from the trust table, not hard-coded).
- **Forecast Lab per-arm skill** is `null` for arms with too few held-out rows (the receipt's own null).

## Deployment caveat (owed, not mine to fix: no git in this chunk)

On the public site these pages will mostly 404, the C4 F6 pattern: the Railway image builds from git and most of
these receipts are not in git. Checked with `git ls-files` / `git check-ignore`: `book_dna_*` and
`hyp_lab/ledger.jsonl` are tracked; `roi_<stamp>.json`, `reputation_*`, `twin_board_*`, `nn_lab/receipts/nightly_*`,
`learning_reports/report_*.json`, `grade_forecasts_*`, `analyst/reputation_weights_*` are untracked;
`health/health_*.json` and `digest/world_state_*.json` are gitignored. The pages work locally and in the desktop
build (C24). Making them public is a decision: commit trimmed receipts, or publish them on deploy.

## Verification

- `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_legibility_routers.py backend/tests/test_signal_reachability.py backend/tests/test_opportunities_router.py backend/tests/test_control_router_authority.py -q` (see the builder report for the counts).
- Full-app smoke (TestClient on `backend.main.app`, real receipts): arena 200 (607 KB), stories 404, stories bad
  ticker 422, forecast-lab 200 (71 KB), theory-lab 200 (938 KB), system-health 200 (45 KB); every receipt FRESH.
- `npx tsc --noEmit` exit 0; `python -m scripts.frontend_check` once at the end (codes in the builder report).

## Review fixes (REVIEW_2026-10-07_C19_LEGIBILITY_PAGES.md, 66/100), applied the same day

This section supersedes the "No secrets, no machine details" bullet above: that claim was false on the real
receipts (`by_family` carried dollar equity) until this fix.

- **F1/F8: one deny-by-default sanitiser at the router boundary.**
  - The sanitiser is `backend/services/legibility_sanitise.py`. `arena_v1.serve` applies it to every endpoint.
  - Keys are allow-listed per payload type (table below), and anything not listed is dropped at every depth.
  - A structure that arrives where a leaf is declared is dropped.
  - A deny-set of key names is removed even inside free-keyed maps: `equity, cash, last_equity, start_capital,
    sum_equity, sum_start_capital, pnl, account_number, buying_power, portfolio_value, market_value,
    unrealized_pl`, plus any key matching secret, password, api_key, token or credential.
  - Every string and every map key is scrubbed:
    - URLs keep their path and lose their host, without mangling (`https://<broker>/v2/account` becomes
      `/v2/account`).
    - Absolute paths become repo-relative.
    - `pid N cmdline contains X` becomes "a live process answers as X"; any other `pid N` becomes `pid [n]`.
    - Loopback hosts and ports are removed.
    - Credential env-var names are removed: UPPER_SNAKE names with a KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL,
      AUTH, APCA or ALPACA component, and `NAME_*` globs.
    - Broker-style account ids are removed.
    - A paywalled publisher's name and its page counts are removed.
  - `by_family` is served as `{n, n_priced, roi_pct}` only.
  - Owner-personal books are dropped at the source: the owner's book family and any account named for the owner,
    including its twins. The page says how many were dropped.
  - A 500 returns only `<what>: internal error (<ExceptionType>)`. The message is logged, never served.
- **F2: row supersession.** The reader now applies a row-level overlay.
  - The overlay file is `hyp_lab/board_supersessions.json`, written on 10-07 by this fix from
    `sticky_twin_2026-10-06.md` F4.
  - It records that `STK_2026-10-07_3` supersedes `mom_12_1_liqw` and `qc623_mom63_liquidity_weighted` in
    `STK_2026-10-07_2`, and that `FT_2026-10-07_2` supersedes the same two rows in `FT_2026-10-07_1`.
  - Each overlaid row is marked with its source run. On the sticky board, validate fair-twin t moves from -2.56
    to -1.05 for liqw and from -0.35 to +0.12 for qc623.
  - **Owed to the board writer:** stamp `supersedes_rows` on the supplement itself, so this hand-written file
    can retire.
- **F3: one walk-forward run per card.**
  - The tournament card uses only the run the nightly cites (`wf_20260929_post_review`).
  - The newer `wf_20261007T_c5_review` is shown as a separate "review rerun" card.
  - Every receipt a card uses appears in the receipts strip with its role. That includes the cited and review
    walk-forwards, the world digest, the supplements, the supersession file and the handoff.
- **F4: theory states.**
  - UNINFORMATIVE and FALSIFIED_VARIANT are added. The map is served as `state_map` and printed in the legend.
  - Real counts today: HYPOTHESIS 49, UNINFORMATIVE 33, CONDITIONAL_SUPPORT 3, FALSIFIED_VARIANT 2, RETIRED 16,
    WEAKENING 0.
  - The "Negative results" panel lists only FALSIFIED, FALSIFIED_VARIANT and WEAKENING.
- **F5: the Arena leads with the collapsed counts.**
  - The page opens with the top line and the twin-collapsed counts:
    - 1 book with at least 21 sessions is ahead of SPY;
    - 36 strategy books are ahead, which collapse to 20 holdings clusters and 2.6 ex-ante bets.
  - The raw "147 ahead" tile is gone.
  - Winners are strategy books with at least `book_dna.params.early_min_sessions` (21) sessions. Today that is
    hack2 alone.
  - A collapsed panel, "short-lived books (not evidence)", holds the rest.
  - Twins and controls are dimmed, badged, and sorted after strategy books by default.
- **F6/F7: baselines and calibration.**
  - Every skill number names its baseline. The reputation skill uses the hindsight base rate of the held-out rows;
    the sigma prior uses the training-half base rate.
  - The reader no longer pools skill. It shows arms > 0 / scored / listed, and the best and worst arm copied
    from the receipt.
  - The volatility IC rides on the sigma prior's row as its sanity check, not as a second piece of evidence.
  - Each calibration bin carries:
    - its row count n;
    - a Wilson 95% interval on rows, declared as narrower than the truth;
    - its distinct dates and h-session date blocks.
  - The dates come from reproducing `forecast_reputation.calibration_curve` on the ledger cut at the receipt's
    `written_utc`. They are served only when every bin's n matches the receipt. Today 19/19 h1 bins and 27/27 h5
    bins match.
  - Bins with fewer than 30 rows or 5 dates are drawn hollow.
  - **Owed to the reputation writer:** emit `n_dates` and an interval per bin, so the reader stops reproducing them.
- **F9: freshness.**
  - The newest run-stamped ROI receipt is served even when it is a `.nobroker` pass. A banner then names the
    newest broker read and its age.
  - Every receipt ref carries the sha256 of the bytes read.
  - The Arena table has a mark-status column.
- **F11: payload weight.** The Theory Lab serves board rows for ONE board (`?board=sticky|basket`; anything else
  is a 422). The payload drops from 1.05 MB to 0.54 MB.

### Allow-list per endpoint (`legibility_sanitise.SPEC`)

| endpoint | top-level keys allowed | row / nested keys allowed |
|---|---|---|
| all | `schema, page, served_utc, status, receipts[kind, file, stamp_utc, age_hours, stale_after_hours, status, line, missing_because, sha256, role, note], missing_because{*}` | none beyond the receipts list |
| `/api/arena/v1/latest` | `evidence_ladder, receipt_choice, top, numbers, by_family, broker_read, clusters, winners, short_lived, losers, books, filters, links` | book: `account, family, category, twin_kind, twin_of, strategy, book_id, status, mark_status, mark_age_days, inception, last_mark, sessions_graded, return_pct, spy_same_window_pct, vs_spy_pp, spy_base, evidence_label/rung/n/why, n_holdings, holdings[ticker, weight], holdings_source, beta_vs_spy, beta_n_obs, cash_fraction, one_name_why, subwindows*, manager_last_run, note, source, error_type, error_why, decomposition{*}, missing_because{*}`; `by_family{*: n, n_priced, roi_pct}`; `broker_read: performed, n_accounts, n_priced, read_utc, errors{*}` |
| `/api/arena/v1/stories` | `month, n_decisions, scope, stories, regret` | story: ids, session, ticker, action, state, cohort, acting, abstention, target/held/plan weights, selector_rank, reason, refused, policy_version, mode, replay flag, order id, alternatives[alt, target_weight, status, why]; regret: the h5 table columns |
| `/api/legibility/v1/forecast-lab` | `house_finding, calibration, calibration_note, skill, sigma_prior, closing, grades, trust, regime, tournament, review_rerun, analyst_reputation` | calibration bin: `arm_prefix, horizon, observable, bin, n, p_mean, p_lo, p_hi, base_rate, wilson_lo/hi, n_dates, n_date_blocks, thin, blocks_missing_because`; arm rows: `arm, family, observable, horizon_days, kind, n, n_total, brier, clim, skill, disc, calib_gap, weight`; analyst: summary counts, limits, `top_firms_by_claims[firm, n_claims, weight_mean, raw_edge]` |
| `/api/legibility/v1/theory-lab` | `states, state_map, state_counts, powered_rule, theories, n_negative, n_uninformative, families, family_prior, theory_cells, boards{sticky, basket}, board_served, crsp, links` | theory: `hyp_id, title, family(_raw), target, status, verdict, powered, state, state_rule, confirm_mean/t/mde, reason, reread_of, declaration_sha256, run_id, receipts, created_utc, refutation, mechanism, precursor`; board row: `rule, family, status, reason, columns{col{window: mean_monthly, t, mde_monthly}}, turnover, rule_cost_bps, twin_cost_bps, sticky_turnover_ok, source_run, superseded_in, superseded_why` |
| `/api/legibility/v1/system-health` | `generated_utc, health_line, exit_code, counts, state_counts, read_me_first, source, groups, process_census, same_output_rows, task_owners, same_output_rule` | probe row: `name, probe, where, verdict, state, cadence_s, evidence, evidence_utc, age_s_at_probe, age_s_now, detail, proof, same_output, missing_because`; task owner: `task, receipt, cadence_h, session_only, retired, registered_only, hash_rule_off, state, verdict, detail, missing_because` |

### Tests

- `backend/tests/test_legibility_routers.py` builds real-shaped receipts and poisons them with:
  - a fake account number and dollar equity;
  - a user-home path, PIDs and ports;
  - credential env-var names and a broker URL;
  - a publisher reader with page counts;
  - owner-personal books.
- It then greps every WHOLE serialized response for all of them.
- A mutation that bypasses `sanitise` turns two of those tests red (checked).
