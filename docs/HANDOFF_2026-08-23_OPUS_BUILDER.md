# HANDOFF 2026-08-23 → next builder session (Opus)

Supersedes `HANDOFF_2026-08-22_OPUS_BUILDER.md`, which stays readable for its
trap list. Read this first, then `docs/ROADMAP_POSITION_2026-08-21.md` §7 for
the older attended queue.

---

## 1. THE DATA QUESTION, CLOSED

**"Did we pull everything we can from WRDS?"** — answered with a receipt, not
an assertion. `TRAINING_SUBSTRATE_V1.json` is now **v1.1** and carries a
`plan_reconciliation` that refuses unless every planned table has a declared
disposition:

| disposition | n | what it means |
|---|---|---|
| on disk | 843 | pulled, and `substrate_verification` judged the file |
| empty | 9 | pulled, zero rows — writes no parquet, only the manifest vouches |
| over cap | 235 | **measured** above 8M rows, deferred by the named-consumer rule |
| terminal | 240 | permission denied (212) / absent from server (28) — entitlement facts |
| **outstanding** | **0** | — |
| **planned** | **1,327** | of 42,167 catalogue tables |

Plus the curated layer the panels actually consume: **175 consumed files**
(was 129), 46 GB bulk + 6.3 GB JKP. Verification: 857 files, 716 COMPLETE,
137 SHORT_MINOR, **0 CORRUPT, 0 UNVERIFIED**.

### What was actually wrong, and it was not the data

The manifest said `completed_at`. The substrate receipt said every consumed
input was verified. `wrds_pull_catchup --dry-run` said `RETRYABLE: 0`. **Seven
planned tables had never been attempted**, and all three missed them for one
structural reason: each reads the record of what *happened* — files on disk,
failure rows — and a table nobody ever asked for leaves no trace in either.

This is the same bug `wrds_pull_catchup` was written to fix. That module's own
docstring records the original pull reporting completion with 79% of its plan
missing, because it counted failures instead of its plan. The catch-up then
counted failures too.

The seven were pulled. **All are genuinely empty on the server** — nothing was
lost. That is luck, not a check: an empty table writes no parquet, so disk
cannot tell "empty" from "never pulled."

**Fixed both places** (`ba53b16`): the catch-up queue is reconciled against the
plan and names `NEVER_ATTEMPTED` tables out loud; the receipt refuses on an
unaccounted table. 8 CI-complete tests, refusal path exercised both ways.

### The 23.2 billion rows we deliberately do NOT have

The 235 over-cap tables are a **decision**, and they are not random:

| family | partitions | rows | named consumer? |
|---|---|---|---|
| `optionm.vsurfd*` | 30 | 10.07B (43.3%) | **yes** — `optionm_surface30d_*` (29 files) |
| `optionm.opprcd*` | 30 | 4.31B (18.6%) | **NO** |
| `ibes` detail (`det_xepsint`, `secdrevm`, …) | 59 | 3.31B (14.2%) | partial (`ibes_consensus_*`) |
| `boardex` director networks | 8 | 1.63B (7.0%) | no (tier 2) |
| `crsp` daily nav/returns | 25 | 1.42B (6.1%) | spine covers the need |
| `optionm.stdopd/hvold/fwdprd` | 56 | 0.73B (3.1%) | no |
| everything else | 26 | 1.76B (7.5%) | — |
| **total** | **234** | **23.23B** | (1 more unmeasured: two COUNTs timed out) |

Two thirds of what we deferred is **option-market microstructure**, and the
rule worked: the biggest family (`vsurfd`, 10B rows) already earned partitioned
ingestion through a named consumer, as did TAQ (`taq_iid_*`, 12 files) out of a
36,778-table firehose. **`optionm.opprcd` — 4.31B rows of daily option prices
across 30 year-partitions — is the largest family with no named consumer.** It
is the single biggest unexploited data asset in the store, and the standing
`MAX_ROWS` decision in the attended queue is really a decision about it.

**Do not read "0 outstanding" as "we have everything."** It means every planned
table has a disposition somebody chose. The catalogue-vs-entitlement rule still
stands: 212 tables this account cannot read are facts about the account.

---

## 2. STATE SNAPSHOT

- **Suite:** 5,375 fast tests. The only red is `test_data_generator_wiring.py`
  (14), caused by the **uncommitted** `lab/` v5 rewrite dropping
  `_compute_market_signal_for_lab`. CI runs a clean tree and is green.
- **Panels:** `aegis_panel_v1.parquet` (230,640 × 419, 2013+) and
  `aegis_panel_v2.parquet` (4,157,680 × ~419, 1926–2024, 4.18 GB,
  28,159 permnos, 4.05M labeled). Panel hash `2812090a3ecbd1f5`.
- **Panel-2 instrument** declared and frozen: `aegis_panel2_spec.py`,
  spec hash `d58b6d0310008713`. **The T2 prereg must CITE that hash.**
- **Gates:** `detectability_gate.assert_detectable` (no default bars),
  `router_capital_gate.assert_router_licensed` (live router FAILS it).
- **Demonstrated market edge: still 0%.** One positive family result, no
  spendable signal.

---

## 3. WHAT IS DONE

| item | verdict | receipt |
|---|---|---|
| WRDS pull, all sources | complete + reconciled | `TRAINING_SUBSTRATE_V1.json` v1.1 |
| JKP full (USA 1926+, 13 foreign) | 45 chunks, 6.3 GB, 0 at-cap fills | `jkp_full/pull_census_2026-08-23.json` |
| AEGIS-PANEL-1 / -2 | built, PIT-audited PASS | `jkp_pit_audit_2026-08-22.json` |
| RETURN-PANEL-TOURNAMENT-1 | **NOT_ESTABLISHED** (under-powered — see §4) | `tournament_primary.json` |
| RISK-PRICE-EARLY-1 | early era tight zero, modern cell +0.0299 | `risk_price_early_trial.json` |
| **RISK-PRICE-FOREIGN-1** | **NOT_US_ONLY — first positive family result** | `risk_price_foreign_trial.json` |
| Panel-2 detectability | instrument no longer blind | `PANEL2_DETECTABILITY_2026-08-23.md` |
| ORDER 27 P2 / G1 battery | gate built, **live router disqualified** | `ORDER_27_P2_ROUTER_CAPITAL_GATE_2026-08-23.md` |
| ORDER 28 substrate gate | opened, now v1.1 | this doc §1 |

## 4. WHAT IS LEFT — ordered, with the gate on each

**(a) A memory-feasible LINEAR arm. Highest value, blocks T2.**
Panel-1's best arm in *both* dense worlds was `full_ridge`; no ridge fits
beside a 6.9 GB panel in float64 on 31 GB, so panel-2 omitted it and its
best-of-arms is a **conservative floor** in exactly the diffuse worlds that
matter. Route: ridge by normal equations on a 412×412 Gram matrix accumulated
in chunks. Until this exists, a diffuse-signal null is close to vacuous.

**(b) The risk-price forward registration — the one thing FOREIGN-1 licensed.**
Exactly one forward registration. Recommended: a new-ID arena book on the
risk-price family (also P9's second distinct selection signal). Same-era
foreign carries **no confirm authority** (linter rule N9); an era-bound claim
confirms forward only.

**(c) RETURN-PANEL-TOURNAMENT-2 prereg.** Only after (a). Declare
`min_recovery` from what a null must rule out — bound ≈ MDE/recovery — **not
from what passes**. At today's numbers the gate reduces to `min_recovery ≤
0.126`, and picking 0.126 because it passes is the exact failure mode. Sparse
null bounds truth at 0.011 (= the economic bar); diffuse null at 0.042 (4×).
Cite `spec_hash d58b6d0310008713`. Null world FIRST, §64 power audit, every
verdict literal asserted reachable, then the registered run whose runner calls
`assert_detectable` as its opening act.

**(d) `MAX_ROWS` decision — really an `optionm.opprcd` decision.** See §1.

**(e) ORDER 27 leftovers:** EVENT_IMPACT bridge · PROFIT_ALLOCATOR_v2 (gated on
true OOS forecasts) · P9 alpha-diversity books (gated on a surviving signal —
none yet).

**(f) ORDER 29 (news/event engine) — do NOT start unattended.** Collectors
touch prod scheduling and LLM spend.

**(g) `lab/rd_loop` retirement — blocked.** Committing the uncommitted `lab/`
v5 rewrite as-is turns CI red (14 tests). Either finish the rewrite or revert.

### ATTENDED (Murat's keyboard)

1. **Flip `trust_router.CLUSTER_ADJUST_DEFAULT` → `True`** (recommended). The
   capital gate refuses the v1.1 receipt while it is off, and the live router
   is unlicensed either way. It moves a live book's sizing, which is why no
   session took it.
2. `MAX_ROWS` / `opprcd` decision · prediction-ledger quarantine ·
   crash-overlay retrain-vs-disarm (rec: retrain as a named panel consumer) ·
   design-review rules amendments · ORDER 29 verdict · 08-27 resolve run ·
   **G2 signatures before 09-08** · unset `AEGIS_SEED_ARENA`.

---

## 5. WHAT THIS PROJECT HAS ACTUALLY DISCOVERED

Kept separate from the build queue on purpose. These are the results worth
carrying forward; each has receipts in the repo.

### Empirical

1. **Modern US large-caps are the anomaly, not the norm.** RISK-PRICE-FOREIGN-1:
   the price floor alone carries **+0.023 IC abroad in the era where the US
   floor is exactly zero**; 12/13 markets positive, dIC +0.0215 vs MDE 0.0183.
   The programme's first positive family result, and it reframes every null
   measured on the US slice — we were sampling the most crowded market on earth
   and reading its crowding as a law.
2. **Risk is stationary; return is not.** Era-transfer 1.001 vs 0.992. With
   §59 (risk resolves ~30× faster than return), this is the single strongest
   argument that the product is RISK-shaped and the return claim stays honest.
3. **Adding a data feed never adds a dimension.** Sixteen sources share 3–7
   latent factors. Breadth of *feeds* is not breadth of *information* — the
   thing that buys information is decision **days**, not names per day.
4. **206 published predictors, net median −0.12%/yr** after realistic costs.
   The literature is not a menu.
5. **Short-horizon winner-chasing is an anti-signal**, not a weak signal:
   `streak_up5` −0.366%/21d (out-of-era confirmed, Holm-surviving),
   last-month factor-chasing −2.1/−2.6%/yr, and +40 trims/exits *destroy* 60d
   wealth.
6. **412 characteristics do not beat a 7-column price floor** on US 2016–2024
   (dIC −0.0025) — with the scope correction below. Within it, `RISK_PRICE` is
   the only family with a pulse (+0.0157 IC alone; the full panel dilutes it
   to zero), and LambdaRank actively hurts (−0.04).
7. **The arena's "composite" was 12-1 momentum for 99.5% of names.** Coverage
   histogram `{"1": 206, "6": 1}`. A diversity illusion that survived because
   nobody looked at the histogram.
8. **The live capital router fails its own gate**: 29.3% null-world
   recommendation rate with 100% of capital exposure behind it. Four separate
   defects, each measured, not inferred.
9. **13F `fdate` is a vintage stamp, not a filing date** — one column
   definition killed the entire MANAGER-* research family.

### Methods this project built that we have not seen elsewhere

1. **The planted-world detectability gate.** Before a null verdict may count,
   the instrument must recover a *known planted* effect at the panel's own
   hash. Enforced in code with **no default bars** — the prereg declares them.
   This converted "412 characteristics don't work" from a finding into a
   scope-limited one, and that correction is the difference between a real
   negative and an under-powered one.
2. **The z-label identity — a diagnostic that separates the objective from the
   data.** Per-date z-scoring maps a heteroskedastic world *exactly* onto its
   homoskedastic twin (the label's `sd_month` divides out; per-date Spearman is
   invariant to a positive within-date scalar), so the two runs are
   bit-identical while the raw arms differ sharply. The gap between raw and
   z-labelled recovery is therefore **pure training-objective damage**, cleanly
   separated from data difficulty. Measured 4.8% → 12.6%, interval off zero.
   Panel-1 asked this exact question, measured +0.00008, and concluded "scale is
   the whole story" — it was wrong, and the window was why.
3. **Effective-n from date blocks, and the Kish design effect at the routing
   layer.** An actor's three vol_state cells are three views of *the same
   mornings*; counting them independently understated dispersion **2.03×**.
   Generalises: any per-decision fan-out (horizons, states, tenors) inflates n
   unless the block unit is derived from the panel's own spacing.
4. **Grade → trust → capital licensing, tested on correlated null worlds.** The
   gate fingerprints the *live estimator's source* so a passing receipt cannot
   outlive the code that earned it.
5. **Scope-aware verdicts, enforced by a linter (N9).** Same-era foreign
   evidence has **no confirm authority** — an era-bound claim confirms forward
   only. The linter downgraded a trial's own grade *before* it ran, which is
   the only time such a rule is worth anything.
6. **Plan-driven completeness.** A pull is finished when every planned item has
   a *declared disposition*, not when the failure count is zero. Deferred is a
   decision; unaccounted is a hole; only one may pass silently. (§1.)
7. **A null owes two tests** (MDE *and* equivalence), and **a global negative
   does not answer a conditional question that was never asked.** Both were
   paid for by verdicts this programme had to correct.

### The honest summary

Nine months in: **demonstrated market edge 0%.** One positive family result
(foreign risk-price), one instrument big enough to see a diffuse effect, and a
methodology that has now caught its own errors four times — the under-powered
null, the router's inflated confidence, the arena's fake diversity, and this
week's silent pull hole. The machinery is real. The edge is not there yet, and
saying so is the point.

---

## 6. TRAPS (paid for, still live)

- **A failure-driven queue cannot see a never-attempted item.** New this week;
  the general form is worth carrying: any "what's left" list derived from the
  record of what happened is blind to what never started.
- Background shells die at ~10 min; Bash `run_in_background` waiters die
  silently above 600 s → use `Monitor`, or a detached resumable loop.
- `$TMPDIR` is **not set** in this Bash — redirecting to `"$TMPDIR/x.log"`
  writes to `/x.log` and dies on permission. Use the scratchpad path.
- Background Bash may start outside the repo → `python -m scripts.x` fails
  with "No module named". `cd` explicitly.
- PS 5.1: `2>&1` on a native exe wraps stderr as `NativeCommandError`; with
  `$ErrorActionPreference="Stop"` python's first *warning* kills a detached run
  silently. Use `Start-Process -RedirectStandardOutput/-Error`.
- PS 5.1 mangles embedded quotes in native args → `git commit -F file`.
- A new `*Error`/`*Refused` in `backend/services/` must be enrolled or exempted
  in `backend/tests/guard_contract.py` **the same commit**, or CI goes red.
- Mask-slicing a 6.9 GB panel copies it per fold and pages the box (75 s fold →
  15 min). The panel is sorted by `eom`; folds are contiguous **views**.
- Receipts stamped `SENSITIVITY_WORLD` are never market evidence.
- `STATISTICAL_MDE_80 ≠ DECISION_MDE_80`; preregs quote both.
- Tests over gitignored data must take the panel hash **from the receipt**.
- Verify prod after every deploying push. Green tests are not a live
  verification.
