# C18 build spec: reputation-weighted analyst consensus, replacing every `n >= 5` / `>= 3 brokers` cliff (2026-10-07)

**Status: BUILD SPEC for an Opus builder. Not registered, not implemented.** Researcher pass,
read-only on code and data (one throwaway `pandas.read_parquet` against
`backend/data/optimus/analyst/target_revisions.parquet`, no write). Grounds every formula and file
reference in code actually read this session, not in memory. Reads behind this spec:
`docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md` §1-§2,
`docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md`, `docs/TRIALS/TRIAL-ANALYST-SNOWBALL-1.md` (unsigned),
`docs/reviews/REVIEW_2026-10-06_C9_CONTEST_DIRECTION.md` F1,
`backend/services/pit_features.py` (`firm_reliability`, `skill_features`),
`backend/services/crsp_pit_bridges.py` (`first_movers`, `analyst2_panel`),
`scripts/opportunities_build.py` (the Explorer's `analyst_stance`/`upside["n_targets"]` build),
`scripts/contest_direction.py` (`RULES["ROT5_DIR"]`, `analyst_direction`, `direction_rank`),
`scripts/stock_lists_v3_build.py` (the literal `n_an < 5` gate),
`backend/services/forecast_grader.py` + `backend/services/belief_state.py` (`Observable`,
`resolve_one`), and one row each of `predictions.jsonl` and
`backend/data/optimus/analyst/target_revisions.parquet` (395,127 rows, 12 columns, schema below).

---

## 0. What exists today, named so nobody re-derives it

- **The cliff this replaces, found in three places, not one:**
  1. `scripts/stock_lists_v3_build.py:454`: `if n_an is None or n_an < 5:` — the ROI list v3.2
     eligibility gate. Binary: a name with 4 covering analysts is excluded outright.
  2. `scripts/contest_direction.py:372`: `oper = set(nrep[nrep >= 3].index)` — a *different*
     coverage gate (earnings-reaction count for MAXTAIL's "operating company" filter, not analyst
     coverage, but the same shape of cliff; not touched by this spec, named so it is not confused
     with the analyst-coverage gates).
  3. The note's own §2.2 target: `target_cv_180`-style dispersion features in
     `crsp_pit_bridges.py` that assume `>= 3 brokers` before trusting a dispersion number.
- **The machinery that already exists and is extended, not replaced:**
  `pit_features.firm_reliability(actor_corpus, asof, firm_col="estimid")`
  (`backend/services/pit_features.py:307-326`): per-broker edge = hit rate minus the
  direction-conditional base rate, on claims whose `public_at + RESOLVE_DAYS` resolves strictly
  before `asof` (`RESOLVE_DAYS = 92`), shrunk `shrunk = edge * n/(n+SKILL_SHRINK_K)`
  (`SKILL_SHRINK_K = 20`), mapped to `weight = clip(1 + SKILL_SLOPE*shrunk, *SKILL_CLIP)`
  (`SKILL_SLOPE = 10.0`, `SKILL_CLIP = (0.5, 1.5)`), with `SKILL_PRIOR = 1.0` as the no-information
  fallback. This function pools **all** of a firm's claims regardless of sector or horizon — the
  gap this spec closes.
- **What ANALYST-SKILL-1 actually found** (verdict doc, cited in full): registered word **ADOPT**,
  ΔIC +0.00084, t 2.52, 71 months — but the mechanism is **attenuation of an anti-signal consensus**
  (skill-weighted IC sits closer to zero than equal-weighted in 70% of months; months where the raw
  consensus worked, skill-weighting *hurt*, mean ΔIC −0.00089). The analyst-level (not firm-level)
  weighting would have been REJECT (ΔIC +0.00035, t 1.32) had it decided. **Recommendation standing
  from that verdict: do not fund more provenance engineering on target-upside LEVEL; test any new
  reputation machinery on revision FLOW instead**, where base IC is not a known anti-signal. C18
  follows that recommendation: §2 below is deliberately agnostic to which consensus OBJECT (upside
  level vs. revision flow) a caller feeds it — the hierarchy is a weighting layer, not a new signal.
- **The data on disk today:** `target_revisions.parquet`, 395,127 rows, 12 columns — `ticker,
  pulled_at, event_date, firm, from_grade, to_grade, action, target_action, prior_target,
  current_target, target_change, pit_safe` (read directly this session; 5 sample rows span
  Goldman/UBS/Stephens/Deutsche Bank/HC Wainwright). **No `first_seen_utc` column on the file read
  this session** — `REVIEW_2026-10-06_C9` F1 found the PIT guard vacuous because re-pulls overwrite
  `pulled_at`, and `scripts/pull_analyst_targets.py` (lines ~302-317) now computes `first_seen_utc`
  via `groupby(key)["first_seen_utc"].transform("min")` on dedup, but that fix had not yet produced
  a column on the file this session read. **C18 must verify `first_seen_utc` is present and
  monotone before using this file for anything PIT-sensitive**, not assume the fix shipped merely
  because the code exists (same trap F1 itself documents).
- **Horizon, honestly:** neither instrument on disk (`target_revisions.parquet`'s yfinance scrape,
  nor the WRDS `tr_ibes.ptgdetu` bridge `ANALYST-SKILL-1` used) carries more than one horizon — both
  are 12-month price targets. The "horizon" dimension in the three-level hierarchy below is
  therefore **degenerate today** (a single bucket, `"12m"`), kept only so the code does not need
  rewriting the day a second horizon (6-month, 24-month) target table exists. Say this on the
  receipt so a reader does not credit the hierarchy with more resolution than the data supports.

---

## 1. The reputation weight: formulas, in the order a builder implements them

### 1.1 What "sector" and "horizon" mean operationally

- **Sector**: `backend.config.WHY_MOVED_TICKER_SECTOR[ticker]` if present, else the Alpaca-asset
  identity's `sector`/industry field (the same two sources `opportunities_build.py:648-655` already
  falls back through for the Explorer). A ticker with neither is `sector = "UNKNOWN"` — its own
  bucket, never silently merged into the global pool.
- **Horizon**: `"12m"`, constant, for both instruments on disk today (§0). The code takes a
  `horizon_col` parameter so a second horizon drops in without a rewrite.

### 1.2 The four quantities, all computed from claims resolved strictly before `asof`

Reuse `firm_reliability`'s existing resolution filter unchanged: a claim counts only if
`public_at + RESOLVE_DAYS < asof` (`RESOLVE_DAYS = 92`, unchanged — this is the PIT margin
`TRIAL-ANALYST-SNOWBALL-1.md`'s trap #3 names explicitly: "the reputation prior resolves before t0,
not merely a window ending before t0").

For a firm `F`, sector `S`, horizon `H` (here always `"12m"`), as of date `t`:

```
n_cell   = count of F's resolved claims in (S, H)
raw_cell = hit_rate(F, S, H) − expected(F, S, H)      # expected = direction-conditional base rate,
                                                        # computed exactly as firm_reliability does
                                                        # today, just restricted to the (S,H) subset

n_firm   = count of F's resolved claims in ANY sector/horizon
raw_firm = hit_rate(F) − expected(F)                   # = today's firm_reliability, unchanged

n_sh     = count of ALL firms' resolved claims in (S, H)   # pooled across firms — "the sector prior"
raw_sh   = hit_rate(S, H) − expected(S, H)

n_g, raw_g = the same pooled over EVERY resolved claim (the anchor; ≈ 0 by construction, since
             `expected` is itself the direction-conditional mean over the same population)
```

### 1.3 Three nested shrinkage levels (not four — `global` is the anchor, not a shrink target)

```
shrunk_sh   = raw_sh   * n_sh   / (n_sh   + K1)                    # sector pool shrunk toward 0
firm_eff    = (raw_firm * n_firm + shrunk_sh * K1) / (n_firm + K1) # firm-wide shrunk toward the
                                                                     # SECTOR prior, not toward 0
edge_final  = (raw_cell * n_cell + firm_eff * K_SUB) / (n_cell + K_SUB)  # cell shrunk toward firm_eff

weight(F, S, H, t) = clip(1 + SKILL_SLOPE * edge_final, *SKILL_CLIP)     # unchanged formula
```

- `K1 = SKILL_SHRINK_K = 20` — **unchanged, reused at two places**: sector-pool-toward-global and
  firm-toward-sector. This is "the prereg family's convention" per the existing code comment; it is
  not re-tuned.
- `K_SUB = 40` — **new, frozen here, proposed by the 2026-10-06 note §2.2.3**: `K_sub = 2 × K1`,
  because claims at a (firm, sector, horizon) cut are a strict subset of a firm's claims and
  saturate slower. Stated as a frozen default for the orchestrator to accept or override **before**
  any read, per the standing rule "a prior chosen after the diagnostic is not a prior."
- **Why this resolves the one apparent tension in the sources:** the note's own worked example
  ("400 claims overall but 8 in semiconductors ... falls back to the firm-wide edge") is the
  `n_firm` large, `n_cell` small case — `edge_final` sits close to `firm_eff`, which itself sits
  close to `raw_firm` (barely shrunk, because `n_firm=400 >> K1=20`). The task's required test ("a
  new firm gets the sector prior") is the `n_firm = n_cell = 0` case — `firm_eff` reduces exactly to
  `shrunk_sh`, so a never-before-seen firm's very first claim is weighted by the sector's own pooled
  track record, not flattened straight to the global `SKILL_PRIOR = 1.0`. One formula serves both
  examples because the firm-level shrink target is the **sector** prior, not the global one; only
  the sector pool itself shrinks toward global.
- **Never a hard gate.** No branch of this formula excludes a name. A name with 1 covering firm, 0
  firm-level history and a thin sector pool still produces a `weight` in `[0.5, 1.5]` — just one
  close to 1.0, carrying little information, exactly as intended.

### 1.4 Per-ticker aggregates (what a consumer actually reads)

For ticker `T`, sector `S`, at date `t`, over its current covering firms `{F_1 .. F_n}` (each firm's
**latest** `to_grade`/target within 365 days — same "latest per firm" convention
`contest_direction.analyst_direction` already uses):

```
w_i            = weight(F_i, S, H, t)                      # §1.3
s_i            = directional sign of F_i's current stance (+1/0/-1, same grade_sign/CONS_SIGN maps
                 already used by contest_direction.py / opportunities_build.py — unchanged)
x_i            = F_i's current 12m target level (for the median-target leg; omit firms with no
                 numeric target from that leg only, never from the stance leg)

weighted_stance        = Σ(w_i · s_i) / Σw_i                              ∈ [-1, 1]
weighted_median_target = weighted_median({x_i}, weights={w_i})            # standard weighted median:
                                                                           # cumulative weight crosses
                                                                           # 50% of Σw_i
dispersion             = sqrt( Σw_i·(x_i − weighted_mean_target)² / Σw_i ) / weighted_mean_target
                         # weighted coefficient of variation — replaces the raw-count `target_cv_180`
n_effective            = (Σw_i)² / Σ(w_i²)                                 # Kish effective sample size
                                                                           # (bounded [1, n]; equals n
                                                                           # only when every w_i is equal)
weight_bearing         = [(F_i, w_i, n_cell_i)] sorted by |w_i·s_i| descending   # for the receipt/audit
```

`n_effective` is the literal replacement for `n >= 5` / `nrep >= 3`: a name with 2 covering firms at
weight ≈1.0 each now carries `n_effective ≈ 2` (printed, not excluded); a name with 5 firms of which
4 are near-zero weight carries `n_effective` well below 5 even though the raw count clears the old
cliff — which is the point: the cliff was a crude proxy for "is this consensus estimated precisely
enough," and `n_effective` is the thing it was a proxy for.

---

## 2. File-by-file build list

1. **`backend/services/pit_features.py`** — extend `firm_reliability`, do not replace it:
   - New function `firm_reliability_hier(actor_corpus, asof, *, sector_map, horizon_col=None,
     firm_col="estimid", sector_col="sector", k1=SKILL_SHRINK_K, k_sub=2*SKILL_SHRINK_K)` returning a
     frame indexed by `(firm, sector, horizon)` with columns `n_cell, n_firm, n_sh, raw_cell,
     firm_eff, shrunk_sh, edge_final, weight`. Implements §1.2-1.3 exactly; reuses the SAME resolution
     filter (`public_at + RESOLVE_DAYS < asof`) as today's `firm_reliability`, by calling it (or its
     shared helper) for the firm-level and sector-pooled numbers rather than re-deriving the PIT
     filter a second time — a second independent implementation of "resolved before asof" is exactly
     the kind of drift CLAUDE.md's guardrails exist to prevent.
   - `firm_reliability` itself is **untouched** — `ANALYST-SKILL-1`'s registered reproduction
     (`python -m scripts.analyst_skill_1 --run`) must give byte-identical numbers after this change,
     and that reproducibility is the first test below.
   - New small helper `weighted_median(values, weights)` and `kish_n_effective(weights)` — generic,
     no analyst-specific logic, usable by anything else that weights a consensus.

2. **`backend/services/crsp_pit_bridges.py`** — **no change in this chunk.** `analyst2_panel`'s
   `skilled`/`unskilled` split (binary, `SKILL_MIN_RESOLVED = 20` claims, `mean(exc63) > 0`) is a
   different, coarser mechanism already feeding `strategy_library_ext`'s `skilled_leader` /
   `first_mover_leadership` rules. Per the note's §2.2.4 and the verdict's own recommendation, a
   hierarchical reputation weight belongs on revision **flow**, not target upside level, and that is
   a successor trial (`ANALYST-SKILL-2`, named below), not a silent edit to a bridge the factory
   already runs nightly. Flag it as the next natural consumer, do not wire it in this chunk.

3. **`scripts/opportunities_build.py`** — the Explorer. Add, never replace:
   - At the `analyst` block (~line 672-709): alongside `upside["n_targets"] = n_an` (raw count,
     kept), add `upside["n_effective"] = ...` and `upside["weighted_median_target"]`,
     `upside["dispersion"]` (§1.4), each with their own `..._source` string per the file's own
     `missing_because[field]` convention when the weight table is unavailable for a ticker (e.g. no
     resolved-claims history for ANY covering firm yet — `n_effective` still computes, just stays
     close to `n_an` at prior weights ≈ 1.0).
   - At the `stance` block (~line 733-753): add `stance["weighted_stance"]` (§1.4) beside the
     existing unweighted `label`/`consensus_sign`/`revision_sign`. **The existing unweighted fields
     are kept, not replaced** — `stance["label"]` still exists and still means what it meant
     yesterday; a reader comparing today's receipt to yesterday's sees the same keys plus new ones.
   - `scripts/stock_lists_v3_build.py:454`'s `n_an < 5` gate: **replaced** with
     `n_effective < N_EFFECTIVE_MIN` where `N_EFFECTIVE_MIN` is declared in `backend/config.py`
     (never hardcoded, per house rule), defaulted to the same `5` the old cliff used so the v3.2 list
     does not silently admit more names than before without a deliberate config change — the
     mechanism changes, the admitted set does not, on day one.

4. **`scripts/contest_direction.py`** — see §3 below (ROT5_DIR recommendation). No edit to the
   frozen `RULES["ROT5_DIR"]` contract or `analyst_direction`'s consensus formula in this chunk.

5. **Monthly receipt**: `backend/data/optimus/analyst/reputation_weights_<YYYY-MM>.parquet` — one
   row per `(month_end, firm, sector, horizon)` with every column `firm_reliability_hier` produces,
   plus `asof`, `k1`, `k_sub`, `n_sh_firms` (distinct firms contributing to that sector pool, so a
   thin sector pool is visible, not just a thin firm). Written by a small new script,
   `scripts/analyst_reputation_weights.py --run`, on the same monthly cadence
   `scripts/analyst_skill_1.py` already uses for its own receipt — not computed ad hoc inside a hot
   path, so a reader can diff this month's weights against last month's without re-running anything.
   Enrolled in `backend/services/signal_reachability.py` per the house "every new module gets a
   caller or a classification" rule.

6. **Config** (`backend/config.py`): `N_EFFECTIVE_MIN = 5` (replaces the literal `5` in
   `stock_lists_v3_build.py`), `SKILL_K_SUB = 40` (new, §1.3) — both named parameters, neither a
   magic number in a service file, per house `DO` rules.

---

## 3. Consumers: the Explorer ships now, ROT5_DIR does not touch its frozen contract

**Recommendation: C18 ships Explorer-only in this chunk. Any contest-facing version is a NEW
declared book, `ROT5_DIR_v3`, never an edit to the live `ROT5_DIR` contract.**

Reasons, each grounded in what was actually read:

- `scripts/contest_direction.py`'s own docstring: "Each rule is a frozen contract: the policy hash
  is `sha256(rule text | the code of this module and contest_rehearsal.py)` ... **A change to the
  rule OR the code under the same (name, version) REFUSES.**" `analyst_direction`'s consensus
  formula (today: flat `cons = mean(signs)`, line ~310) is inside `contract_sha`'s hashed source.
  Editing it to use §1.4's `weighted_stance` changes the hash under the SAME declared version,
  which the module's own `ContractChanged` guard is built to refuse — this is not a workaround to
  route around, it is the guard doing its job.
- The contest window is **Oct 12 – Nov 13, 2026**; today is Oct 7. `REVIEW_2026-10-06_C9` F2 already
  measured that the direction filter itself is "a mean-for-variance trade, not a free lunch" (top-5
  event replay: +0.45pp/event, t −1.33, two of eight years the wrong sign) — i.e. ROT5_DIR's OWN
  value is not yet settled. Changing its consensus mechanism five days before the contest starts,
  on top of an already-unsettled filter, stacks two untested changes into one live decision — exactly
  the shape CLAUDE.md's "new mechanism arrives as its own book, never as a weight" rule exists to
  prevent (stated there for `arena_composite`; the same logic applies to a frozen contest contract).
- The Explorer (`scripts/opportunities_build.py`) carries **no frozen contract hash** — it is a
  descriptive dashboard, not a traded book, so the usual registration/freeze machinery does not
  apply and there is nothing for a reputation-weighted field to collide with. It is also where the
  owner will actually see the new object first (§5 below).

**Concretely:** register `ROT5_DIR_v3` (version=3, `supersedes` = the current v2 hash, same pattern
`_V1`/v2 already uses) with `consensus` redefined as `weighted_stance` and `order` re-sorting on
`weighted_stance`/`dispersion` in place of the flat `cons`/`rev_mom`. Freeze it as a **separate**
shadow book, graded beside `ROT5_TRAIL` and `ROT5_DIR` v2 by the same grader, same licence
(`PRODUCT_EXPERIMENT`), same "no capital" status every other shadow book in this contest carries. It
may become the live book for a FUTURE contest cycle once it has its own graded history; it is not a
live candidate for Oct 12.

`pit_features`'s bridges (`crsp_pit_bridges.analyst2_panel`): named as the next natural consumer
(§2 item 2), explicitly deferred to a successor trial on revision flow, per the standing attenuation
finding.

---

## 4. The snowball follow-through leg as a free shadow series

### 4.1 What the ledger can and cannot grade today (confirmed this session, not assumed)

One row of `backend/data/optimus/predictions.jsonl` was read. Its schema: `prediction_id, ticker,
specialist, observable, horizon_days, probability, threshold, benchmark, made_at, resolves_after,
thesis, counter_thesis, next_observable, model, model_version, prompt_hash, input_snapshot_hash,
schema_version, resolved_at, outcome, brier, resolution_detail`.

`backend/services/belief_state.py`'s `Observable` enum has exactly four members — `RETURN_SIGN`,
`BEATS_BENCHMARK`, `ABS_MOVE_EXCEEDS`, `DRAWDOWN_EXCEEDS` — and `resolve_one(rec, prices, *, today)`
resolves **every** one of them from `prices[rec["ticker"]]` alone (and `prices[rec["benchmark"]]` for
the benchmark case). There is no branch that reads anything but a price series, and the function's
very first ticker check (`if tkr not in prices.columns: ... this record can never resolve`) assumes
a price-indexed object is the only possible grading input.

**Confirmed answer to the task's question: no, the forecast ledger cannot carry a non-price event
outcome as built today.** `MECHANISM_HAS_NO_GRADER` (one of `forecast_grader.py`'s own
`REFUSAL_BUCKETS`) exists for precisely this case — a row whose `observable` no grader in the
repository knows. Writing a "P(>= 2 other firms raise)" row into `predictions.jsonl` with the
existing machinery untouched would silently and permanently land every row there, which is exactly
the "17,614 records sitting in no bucket for six weeks" failure `forecast_grader.py`'s own comment
(lines 80-82) names as the reason that module exists.

### 4.2 Recommendation: a separate shadow ledger, same row shape, own tiny grader

Rather than extending `Observable`/`resolve_one` (which would require threading a non-price data
source into a function whose contract — and whose callers across the grading pipeline — assume
`prices` is the only input), build a **parallel, minimal ledger** that mirrors the schema so it is
inspectable with the same habits, but is graded by its own small function:

- **File:** `backend/data/optimus/analyst/snowball_followthrough_shadow.jsonl`.
- **Row fields**, same names as `predictions.jsonl` where they mean the same thing, so nobody has to
  learn a second vocabulary:
  ```
  prediction_id        : sha-derived id, same convention
  ticker                : the t0 permno's ticker as of t0
  specialist            : "analyst_snowball_followthrough"   (a PROCESS name, per the 09-24 finding
                                                                that a process forecasts and a
                                                                persona does not — this is a process)
  observable            : "analyst_follow_through_ge2"         (NOT in belief_state.Observable — see
                                                                §4.1; this ledger does not call
                                                                resolve_one)
  horizon_days          : 63                                   (trading sessions, matching the trial
                                                                draft's primary-1 metric)
  probability           : the PIT-safe baseline rate (§4.3)
  threshold             : 2                                     (distinct OTHER firms)
  made_at               : t0's usable date
  resolves_after        : t0 + 63 trading sessions (calendar date)
  t0_broker             : the broker whose raise ended the quiet spell
  t0_firm_reliability_weight : firm_reliability(asof=t0)["weight"] for t0_broker — reported, never
                               deciding, per the trial draft's own frozen construction
  resolved_at           : null until graded
  outcome               : null until graded (0/1: did >= 2 OTHER distinct firms raise within 63
                           sessions of t0, read from crsp_pit_bridges.first_movers's own event frame)
  brier                 : null until graded ((probability − outcome)²), same formula as belief_state
  resolution_detail     : {} until graded, then {"n_other_firms_raised": k, "firms": [...]}
  schema_version        : "1.0.0"
  ```
- **Grading rule:** a tiny function, `grade_snowball_shadow(rec, revisions_or_bridge_output, *,
  today)`, structurally parallel to `resolve_one` (same early-exit shape: `outcome is not None` →
  no-op; `today < resolves_after` → not yet due) but reading the analyst-revision event frame
  (`crsp_pit_bridges.first_movers`'s own construction, reused literally — nothing new needs
  inventing for the count itself, only the grading wrapper) instead of a price panel. It writes
  `outcome`, `resolved_at`, `brier` in the same shapes `resolve_one` does, so a later decision to
  fold this ledger into the main one (should the follow-through leg ever graduate past descriptive
  context) is a migration, not a rewrite.
- **Nothing trades.** This ledger has no consumer in any book, ranker or ROI list — stated explicitly
  here so `signal_reachability.py`'s unreachable-module gate classifies it correctly as a
  deliberately caller-less descriptive ledger, not an orphan.

### 4.3 The baseline probability must itself be PIT-safe — a trap the task's own framing invites

The snowball note's §1.4 by-year table (18.0% @21s / 35.9% @63s overall, rising from ~18-33%
pre-2020 to 35-45% from 2020 on) is a **full-sample descriptive statistic**. Using it directly as
the `probability` field for, say, a 2014 t0 event would leak 2020-2026's higher rate backward into a
2014 forecast — the same look-ahead shape the trial draft's own §1.7 names for the reputation prior,
applied here to the baseline itself. **The shadow row's `probability` must be an expanding-window
estimate: the historical `P(snow63)` computed only from t0 events whose own 63-session resolution
window closed strictly before this t0** (not merely "before this t0," because an event resolved
*after* the current t0 but with a t0 date before it is not yet knowable either — same `RESOLVE_DAYS`
logic as §1.2, applied to the follow-through outcome instead of a broker's claim). Early t0 events
(2012-2013, thin history) get a wide, uninformative prior (`probability ≈ 0.5` or the Laplace
estimate with a strong pseudo-count) rather than the full-sample 36%; the estimate tightens as more
resolved history accrues. This is a one-line build requirement with a two-paragraph consequence if
skipped — stated here so the builder does not reach for the note's convenient table.

---

## 5. The return leg: what would make it registrable, stated in years, honestly

The unsigned trial draft's own linter output (R13, pasted in full in `TRIAL-ANALYST-SNOWBALL-1.md`)
already answers this with real numbers — restated here, not re-derived, because re-deriving it would
risk a silently different assumption:

- **n_required = 7,064; n_available = 312`, over 26 corpus-years, capped at 12 independent
  21-session windows per year** (`R13b`: "only 12.0 independent windows fit in a year" at this
  event rate and horizon — the cap, not the raw event count, is what bounds `n_available`).
- **Literal answer, "just wait longer," stated so nobody proposes it sincerely:**
  `7,064 / 12 ≈ 589 years` of additional forward (or historical) t0 accrual at the SAME blocking
  rule. This is not a real option and the spec says so plainly: the historical-replay design, as
  constructed (one effective observation per calendar month), **cannot ever be powered by waiting**,
  on any human timescale.
- **The actual route, already named by the linter's own R13b/R14 note:** `cross_sectional_rho` is
  "deliberately not declared" in the draft precisely because it is unmeasured — "rho must be
  measured on a policy-free surrogate (e.g. same-month 21-session excess returns of random matched
  raise dates) before it can be claimed, and that measurement is the one step that could move this
  leg from UNPOWERED to RESOLVABLE." If same-month t0 events are substantially less than perfectly
  correlated (events on different tickers sharing a calendar month do NOT share the same earnings
  print, same news, same idiosyncratic driver — only the market's own day-to-day moves, which the
  SPY-relative return already nets out), the true number of independent observations per month is
  closer to the **event count** than to **1**, and `n_available` could already clear 7,064 without
  a single additional year — the draft's own construction #2 (matched random raise dates) is the
  tool to measure this, and it is a measurement, not a wait.
- **What C18 should NOT do:** register the return leg, sign the draft as-is, or treat the 589-year
  number as license to drop the question. The correct next action (not in this chunk's scope,
  flagged for the orchestrator) is: run the `cross_sectional_rho` measurement the draft already
  specifies, re-run `lint_prereg.py`, and let that verdict — `RESOLVABLE` or still
  `UNPOWERED_AT_REGISTRATION` — decide whether the return leg is ever registered at all. C18 itself
  touches only the reputation weight (§1-§3) and the follow-through shadow ledger (§4); the return
  leg stays `RETIRED_FROM_CURRENT_SEARCH` pending that one measurement.

---

## 6. Tests (named, not sketched)

1. **A single reliable firm outweighs five unreliable ones.** Synthetic `actor_corpus`: firm `A`
   with `n_cell = 50`, consistently correct (raw edge ≈ +0.10); firms `B..F`, each `n_cell = 50`,
   consistently wrong in the opposite direction (raw edge ≈ −0.05 each, same sign of stance). Assert
   `sign(weighted_stance)` follows `A`'s sign once `|w_A · s_A|` exceeds `Σ|w_i · s_i|` over
   `B..F`, and that the flat/unweighted mean-of-signs over the same six firms would have gone the
   other way (proving the weighting, not the data, produced the flip).
2. **PIT: mutating later rows changes nothing.** Compute `weight(F, S, H, t0)` on a frozen
   `actor_corpus`. Append or mutate rows whose `public_at` is such that `public_at + RESOLVE_DAYS`
   falls on or after `t0` (i.e., rows that look like they predate `t0` by naive date but have not
   actually resolved as of `t0`). Recompute — assert byte-identical `n_cell, n_firm, n_sh,
   edge_final, weight`. This is the regression test for the PIT filter carried through all three
   new levels, not just the firm level `firm_reliability` already tests.
3. **A new firm gets the sector prior.** Firm `Z`, `n_firm = n_cell = 0` (first-ever observed
   claim), in sector `S` with a measured, nonzero `shrunk_sh`. Assert `firm_eff(Z) == shrunk_sh`
   exactly (within float tolerance) and `edge_final(Z) == shrunk_sh` (since `n_cell=0` too), i.e.
   `weight(Z) == clip(1 + SKILL_SLOPE * shrunk_sh, *SKILL_CLIP)` — not `SKILL_PRIOR = 1.0` unless
   `shrunk_sh` itself happens to be ≈ 0.
4. **`firm_reliability` reproducibility.** `python -m scripts.analyst_skill_1 --run` gives the
   SAME ΔIC/t as the 2026-09-26 verdict (+0.00084 / 2.52) after `firm_reliability_hier` is added —
   proof the existing registered trial's numbers are untouched by this chunk.
5. **`n_effective` replaces the cliff without changing the admitted set on day one.** On the v3.2
   ROI-list universe, `n_effective < N_EFFECTIVE_MIN` (default 5) excludes the same tickers
   `n_an < 5` excluded on the frozen `STOCK_LISTS_ASOF` snapshot — a receipt diff, zero tickers
   added or dropped — proving the mechanism changed and the decision did not, by construction, on
   the day it ships.
6. **Thin coverage lowers `n_effective`, never drops the name.** A ticker with exactly 2 covering
   firms, both weight ≈ 1.0: `n_effective ≈ 2`, present in the Explorer output with that number
   printed, not absent.
7. **Snowball shadow grader confirms the non-price gap (§4.1) rather than assuming it.** A unit
   test that feeds a `predictions.jsonl`-shaped row with `observable =
   "analyst_follow_through_ge2"` through `belief_state.resolve_one` and asserts it returns `None`
   with a logged `unknown observable` warning (today's actual behavior) — pinning the exact finding
   this spec reports, so a future change to `resolve_one` that silently starts "handling" it is
   caught rather than discovered as a drift.

---

## 7. What the owner will see change on the Explorer

Two lines, as asked:

1. **A name that was excluded outright (e.g. a thin-coverage small-cap with 2-4 analysts) now
   appears on the ROI-eligible section with `n_effective` printed beside its upside and median
   target, instead of being silently absent from the ranked list** — the Explorer's
   `missing_because["analyst"]` reason for such a name changes from "excluded, n < 5" to a present
   row carrying a visibly low `n_effective` and a `weighted_stance` the owner can read as "thin but
   real," exactly the names the task names as the target case (a 2-4-analyst small-cap, same shape
   as QUBT/KYTX/SLDP would be if their own counts sit in that range on the day this ships).
2. **Every Explorer card's `analyst_stance` block gains one number** — `weighted_stance` sits beside
   the existing unweighted `label`, and when they disagree (a thin-but-reliable covering firm
   pulling the weighted number one way while the raw majority vote points the other), the card now
   shows that disagreement explicitly rather than only ever reporting the majority view.

---

## Summary for the orchestrator

- **Three formulas, one line each:**
  1. `shrunk_sh = raw_sh · n_sh / (n_sh + K1)` — the sector's own pooled edge, shrunk toward the
     global anchor (reuses `K1 = SKILL_SHRINK_K = 20`).
  2. `firm_eff = (raw_firm · n_firm + shrunk_sh · K1) / (n_firm + K1)` — the firm's own edge, shrunk
     toward **its sector's** prior, not the global one (same `K1`) — this is what makes a brand-new
     firm inherit the sector prior exactly, and a well-covered firm stay close to its own number.
  3. `edge_final = (raw_cell · n_cell + firm_eff · K_SUB) / (n_cell + K_SUB)`, then
     `weight = clip(1 + 10 · edge_final, 0.5, 1.5)` — the (firm, sector, horizon) cell, shrunk toward
     `firm_eff`, with a new frozen `K_SUB = 40` (= 2×`K1`, proposed by the 2026-10-06 note, not
     tuned on any read).
- **ROT5_DIR recommendation: Explorer-only now; a NEW `ROT5_DIR_v3` shadow book for any
  contest-facing use, never an edit to the live, frozen `ROT5_DIR` v2 contract five days before the
  Oct 12 contest start.**
- **Return leg:** stays `RETIRED_FROM_CURRENT_SEARCH`. The literal "more years" answer is ≈589 years
  at the current per-month blocking (`7,064 / 12`) — not a real option. The one measurement that
  could actually change the verdict is `cross_sectional_rho` on the policy-free surrogate the trial
  draft already specifies but never ran.
