# Chunk 23a — PROBE: the virtual graded row, and the probability on the EXPLORE row

Spec by Fable, 2026-09-21, from roadmap §16.2–16.3 (row 23a) and Murat's
review (Part 2, "The critical difference is PROBE"). Builder: Opus, after 22c
lands. Validator: Fable.

## What already exists (read before writing a line)

* `decision_contract._ic_rows` writes a row for EVERY ranked name, refusals
  included, then trims refusals to `MAX_REFUSED_ROWS = 50`. Every row carries
  `expiry_utc` from its falsifier's window or the policy horizon.
* `decision_ledger.score_due` grades EVERY due row with a ticker, refused or
  not: close-to-close from `asof` to `expiry_utc`, written as `SCORED` with
  `realised_return`. So refused names are already "virtually traded" — but
  they are lumped under one word, capped at 50, single-horizon, and nothing
  reads them back into a measured read. That is the gap, not the grading.
* `decision_authority.assign` has exactly two "unmeasured" branches, both
  REFUSED today: "no rank-bearing licensed signal leads this name" and
  "NO measured read exists for {sig} (config.SIGNAL_MEASURED_RETURN has no
  row)". Every other refusal in that loop is EVIDENCE of no EV (net read not
  above `EXPLORE_MIN_NET_PCT`; CALIBRATED but outranked) and stays REFUSED.
* EXPLORE rows carry `thompson_seed` and `thompson_draw_pct_per_month`, not
  the probability the draw selected them.

## The change, in six parts

1. **`PROBE` authority.** `decision_authority.PROBE = "PROBE"`, in
   `AUTHORITIES`, NOT in `ACTIVE_AUTHORITIES` (it never sizes). The two
   unmeasured branches above assign `PROBE` with a `probe_basis` sentence that
   says which of the two it was. `AuthoritySplit` gains `probe` (list) and
   `probe_basis` (dict). Weight stays 0; capital resolution is unchanged and
   the contract prints `probe_count` beside the four buckets.

2. **`hypothesis_id`.** Deterministic, short, on every row the authority
   touches: `sha256(f"{signal}|{mechanism}|{information_set}")[:12]` where
   `mechanism` is `forecast_grader.mechanism_of(rec)` (exists) and
   `information_set` is the funnel's `generated_at` date's MONTH (so a
   hypothesis is the same object across days and differs across the
   quarterly panel refresh). Written as `hypothesis_id` and
   `hypothesis_id_basis` (the three inputs in clear). A PROBE row without a
   `hypothesis_id` cannot be written (test).

3. **One PROBE row per horizon.** `config.PROBE_HORIZONS_SESSIONS = (5, 21,
   63, 126)`. For each PROBE name the contract writes one row per horizon:
   `decision_id` includes the horizon; `expiry_utc` = asof + h sessions (use
   the session calendar the resolver already uses; if none exists, calendar
   days × 7/5 with the basis saying so); `direction = "PROBE"`;
   `position_budget = {weight 0, dollars 0, shares 0, capital_usd, virtual:
   true, virtual_notional_usd: config.PROBE_VIRTUAL_NOTIONAL_USD (100),
   basis}`; `maximum_loss` as refused rows (nothing at risk). PROBE rows are
   NOT subject to the `MAX_REFUSED_ROWS` trim — they are the panel; cap them
   separately at `config.PROBE_MAX_NAMES_PER_DAY` (200) by rank, and print
   how many were cut.

4. **The grader records the benchmark beside the raw return.** In
   `score_due`, when SPY bars are in the fetched frame, `detail` gains
   `benchmark_return` (SPY close-to-close over the same window) and
   `excess_return`; when SPY is absent the two fields are present and `None`
   with `benchmark_basis` naming why. Never grade at zero; never drop.

5. **The reader that turns PROBE grades into a measured read.** New
   `backend/services/probe_panel.py`: `read_for(hypothesis_id, horizon_sessions,
   *, path=None, asof=None) -> ProbeRead | None` over SCORED rows with
   `direction == "PROBE"`: `n`, `n_blocks` (distinct asof MONTHS, canon §58),
   `mean_excess_pct`, `se_pct` (block bootstrap over months, 200 draws, seeded),
   `sign_hit_rate`, `first_asof`, `last_asof`, `receipt` (the ledger path +
   the row count). It is a measured read only when `n >= config.PROBE_MIN_GRADED`
   (30) AND `n_blocks >= config.PROBE_MIN_BLOCKS` (6); below that it returns
   the read with `measured = False` and the two shortfalls named.
   `decision_authority`, in the "NO measured read" branch, consults
   `probe_panel.read_for` first: a measured PROBE read enters the EXPLORE
   path as `posterior_source = "PROBE_PANEL"` (a THIRD value beside the two
   that exist; update the docstring that says "two values and no third"). An
   unmeasured one stays PROBE and the `probe_basis` says how many grades short.

6. **The selection probability on every EXPLORE candidate.** Thompson
   selection is a draw over K candidates for M slots; the probability that
   candidate i is selected is estimated by replaying the draw
   `config.EXPLORE_SELECTION_REPLAYS` (2,000) times with rng seeded from
   `seed_for(asof, "SELECTION_REPLAY", signal)` — the same posterior means and
   ses, fresh draws — and counting the fraction in which i lands in the top M
   under the budget. Written on every EXPLORE candidate row (selected or not)
   as `selection_probability`, `selection_probability_basis`, and on the
   receipt as a block. PROBE rows carry `selection_probability = 1.0` with the
   basis "every unmeasured name probes; no draw". This is the field off-policy
   evaluation needs later (review item 12); it changes no decision today.
   Two companions, from `research_sequential_evidence_and_bandits.md` (a
   doubly-robust off-policy estimator cannot run without them): every EXPLORE
   candidate row also carries `action_set` (the tickers considered for the M
   slots that day, with each one's posterior mean and se) and
   `context_features` (the small dict the authority already has: signal,
   decile, vol_annual, horizon, regime tag if the funnel carries one). Write
   them once per day on the receipt and reference by `action_set_sha256` on
   each row, so the ledger row stays small.

## What it must NOT do

* No capital moves: PROBE weight is 0 by construction; the tests assert the
  capital resolution vector is bit-identical before and after for a fixture
  with PROBE names.
* No mutation of existing ledger rows; `REFUSED` rows already written stay
  as they are (append-only). Yesterday's "NO measured read" refusals are
  not re-labelled.
* No new REFUSED sentence without a `classify_refusal` pattern (the
  UNCLASSIFIED count is a test).
* PROBE never bypasses PIT: the row's information cutoff is the funnel's
  `generated_at`, as every row's is.

## Tests (tmp_path only, never `backend/data`)

1. A rec with no measured read → PROBE with four rows (one per horizon),
   `hypothesis_id` present, weight 0, capital resolution unchanged.
2. A rec whose read is measured-but-nonpositive → still REFUSED (evidence).
3. `probe_panel.read_for` on a synthetic ledger with 40 scored PROBE rows over
   8 months → `measured = True` with the right n/n_blocks/mean; with 40 rows
   in 2 months → `measured = False`, shortfall names blocks.
4. A measured PROBE read reaches the EXPLORE path with
   `posterior_source = "PROBE_PANEL"`.
5. `selection_probability` sums to ≈ M over the candidate set (±0.05) and is
   1.0 on PROBE rows; the replay is deterministic for a fixed asof.
6. The grader writes `benchmark_return` / `excess_return` when SPY is in the
   frame and `None` + basis when it is not.
7. `MAX_REFUSED_ROWS` does not trim PROBE rows; `PROBE_MAX_NAMES_PER_DAY` does,
   by rank, and the cut count is on the receipt.

## The closing line (§16.1)

On the day 23a lands no PROBE row can be graded (the shortest horizon is 5
sessions), so the honest receipt line is:

`BELIEF_CHANGED: pending — N PROBE rows written under H hypothesis ids for
2026-09-21 (first grade due 2026-09-28 at 5 sessions); today's REFUSED count
fell from 39 to R because "no measured read" is no longer a refusal.
Yesterday there was no posterior for these H hypotheses; the first one is
printed by the scoreboard on the morning the panel reaches PROBE_MIN_GRADED.`

The scoreboard gains one line: PROBE rows open / graded / hypotheses measured.
