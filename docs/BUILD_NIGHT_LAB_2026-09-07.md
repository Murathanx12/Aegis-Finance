# BUILD — NIGHT LAB, 2026-09-07 — construction, events, unsupervised, simulations

Mandate `NIGHT_LAB_2026-09-07_OPUS_PROMPT.md`. Seven lanes, six agents, local
commits only — **nothing pushed, sealed, ordered, deployed or changed on
Railway.** Receipts: `backend/data/optimus/night_lab_2026-09-07/`.
CI was **green on HEAD `7088764`** before any work started (`backend` and
`frontend` both success).

---

## RESULTS SCOREBOARD

### The N1 sentence — does the IC become money?

> **No, not on its own — but the construction was destroying a real and
> measurable amount, and it is worth +4.670pp/yr on one family.** Broadening
> every book raises the transfer coefficient from **0.11–0.20 to 0.28–0.64**
> and effective names from **7–19 to 50–300**, with no prediction changed. But
> only **15 of 100** broad-minus-control comparisons are positive (median
> **−2.853pp/yr**). The exception is the revision family:
> `revisions|k=300|rank|hold=600|25bps` beats its own top-50 VW control by
> **+4.670pp/yr, t 2.584**, TC **0.132 → 0.4865**, effective names
> **12.2 → 224.9**, on the same 309 months from the same frozen column — and
> that delta is **positive in all three eras** (+0.51 / +0.23 / +0.42 %/mo).
> **Holm over the 100-comparison delta family: 0.4884. Nothing survives.**

The starkest single pair, one column, two constructions, 1999–2024:

| book on `revisions` | beta | TC | eff. names | TW net | market | β-matched |
|---|---|---|---|---|---|---|
| top-50 VW, 25 bps (the incumbent) | 0.882 | 0.132 | 12.2 | **3.66** | 13.18 | −3.494%/yr t −1.54 |
| top-300 EW hold-600, 10 bps | 1.086 | 0.587 | 299.4 | **29.27** | 13.18 | +2.964%/yr t 1.785 |

**RESULT IMPROVEMENT: a mechanism, not a claim.** The construction effect is
era-stable; the alpha it uncovers is not. Level family 160 cells, family-min p
0.004947, best cell Holm **0.79152**, **0 survive**, best-cell verdict **NOISE**
(DSR 0.4513, WITHIN_SELECTION_NOISE).

| | |
|---|---|
| **Best historical net strategy vs the market** | `ensemble_ew\|k=100\|ew\|hold=200\|10bps` — beta **1.1951**, β-matched **+5.651%/yr t 2.424** over 309 months, TW **62.87** vs market **13.18**. Its edge is **1999-2007 (t 2.988)**; on the 107 months when it is actually an eight-arm ensemble it is **+2.142%/yr t 0.697**. |
| **Best forward paper strategy** | unchanged — the lab placed no orders and touched no book |
| **Independent selector count** | unchanged — nothing was promoted |
| **Farm candidates tested / promoted** | 160 level cells + 100 delta comparisons + 12 cadence cells + 12 floor cells / **0 promoted** |
| **New actionable finding** | **YES — four**, below |
| **External execution drag** | not measured (no orders); the *modelled* drag is N3's measured TAQ line |
| **LLM spend** | **$0.03** of an $8.00 cap — DeepSeek only, all in N6.2 |

---

## Lane by lane

**N1 — construction.** `learner/fundamental_law.py` (new): IC, effective breadth
`(Σw)²/Σw²`, transfer coefficient (corr of realised *active* weights with
z(signal) over the whole admissible cross-section, not the holdings), β, implied
vs realised IR. TC < 0.5 ⇒ `CONSTRUCTION_DEFECT` — the book's signal verdict is
not readable from it. Every term returns `None` with a reason rather than a zero
it did not measure. `evaluate.book()` gains opt-in `return_weights` and
`weight="rank"`; the default key set is still byte-identical to v1's receipt.
**N1.3:** the index-hedged long-short works as a hedge (realised β 0.00–0.05) and
**loses money — 19 of 20 cells negative**, every cell negative at 25 bps; best is
+0.346%/yr over cash, t 0.178. The **exclusion books** are the survivor shape:
universe EW minus the bottom decile beats the EW universe by **+0.861pp/yr t
2.487** at 10 bps (TW 18.72 vs 14.41) and +0.482pp t 1.382 at 25 bps.
**N1.4:** monthly refit beats the *annual* control in **12 of 12** constructions
(median +1.204pp/yr, family-min p 0.1098, best Holm 1.0) — and the gain **falls
by a factor of seven** as TC rises: +2.658pp at top-50 VW (TC 0.160), +0.363pp at
top-300 rank (TC 0.483). A2's +5.751pp was the narrowest instrument we own
measured against a frozen-once baseline nobody proposes.

**N2 — the selection-free ensemble.** Eight trained arms, monthly cross-sectional
percentile ranks, no arm chosen. **The reliability weighting the mandate asked
for LOSES to equal weight** by −1.041pp/yr (t −0.907), so equal weight is the
honest ensemble. Its inputs were searched and the receipt says so; family = 2
(both weightings are reported). DSR 0.9687, MDE 4.66%/yr, powered **False**.

**N3 — size-aware floors.** `execution_authority` (terminal repo) learns
`book_size_usd`; omitting it reproduces flat-$3m byte for byte; unresolvable ⇒
`CANNOT_DETERMINE`. The curve runs the **wrong way** for the small-book thesis:

| book | floor @1% ADV | TAQ band | measured-cost edge | t |
|---|---|---|---|---|
| institutional | $3.0m | 1m–5m | +2.795%/yr | 1.019 |
| **$100k** | **$500k** | 100k–1m | **−9.629%/yr** | **−3.279** |
| $1m | $5.0m | 5m–10m | +3.397%/yr | 1.369 |
| $10m | $50m | 50m+ | +4.245%/yr | 2.176 |

Family 12, family-max p 0.99948, 0 survive Holm. All three named dead cells stay
dead: the small-cap 5-session reversal goes **−0.49%/5-session (t −2.30)** at the
$100k floor on a measured ~74.5 bps one-way cost; S28's $100k–$1m band is gross
+0.19%/yr against a **17.86%/yr** measured cost line. Capacity is an advantage in
what a small book *may* hold and a disadvantage in what it *costs* to hold.

**N4 — the event-time table.** `event_table_v1.parquet`, **993,005 rows,
2015-2024, 81–86%** of the CRSP-common proxy per year: IBES EPS surprises
618,419 · 8-K item codes 276,978 · news 95,228 and growing · 13D/G 2,380. Three
gaps stated rather than papered over: **13D/G is effectively absent for
2015-2024** (all rows from seven days in Aug 2026), **Form 4 is absent
everywhere** (a guard test fails if a future run fabricates one), and the
mandate's `--universe tradable` does not exist in the puller — `fleet` (~156
names) was used and flagged. **PEAD / revision-on-event / surprise×reaction books
are NOT run**: the Alpaca leg is ~27% through and grading books on a quarter of a
source is file size mistaken for sample size. The pull continues in a detached
process; `python -m scripts.n4_event_table --build` re-joins in ~9 s.

**N5 — unsupervised.** *Event compression:* 127,157 raw news rows → **97,949
canonical events, ratio 1.298** (TF-IDF; a **lower bound**, it catches
reformatted duplicates and misses same-event stories with no shared vocabulary).
The NVIDIA embedder was **ABSENT — no `NVIDIA_API_KEY` in this repo**. Novelty
tested on 18,071 events with a matured forward return: **IC 0.003663, model-null
percentile 0.92, p 0.0846 → WITHIN_MODEL_NULL.** Only 2015-2018 is testable — the
panel ends 2024-12 and the corpus is mostly 2025-2026, so the three-era table
**cannot be filled and is not claimed**. *Self-supervised pre-training:* CUDA
**True**, RTX 5060, torch 2.11.0+cu128, probed by *running* the designated
interpreter. The 8-seed arm is present and **is** stacked in the ensemble (0.253
weight share), never a lone champion. Re-training on N4/N5 features is
**DEFERRED** — those columns are not on the panel.

**N6 — simulations.** *Battery v2:* **5 of 5 worlds ALL_PASS** through N1's
control construction, N1's broad construction and N2's ensemble — linear 9.914,
regime 7.479, graph 10.473, event 33.006, and the **null's best cell t 1.577,
NOISE**. The new **event world** (alpha on the top decile, zero on the other 90%,
demeaned within the month so the EW market leg is unchanged by construction) is
where the two constructions disagree most: **control t 33.0 vs broad t 14.2**.
*Breadth is not free when the edge is concentrated* — a result about N4's whole
programme, obtained where the answer was known. The **sensitivity ladder**
answers Fable's attack #5: the machine recovers B1's scale (t 5.20, IC 0.068) and
**half of it** (t 2.02, IC 0.019), and loses it at a quarter (t 0.80) and an
eighth (t −0.28). *Fantasy exams round 2:* 40 new **event** pairs, **40/40
monotone** on all three outputs, canary **0/8**; the new clause-position control
gives mean |Δp_up| END 0.305 vs FRONT 0.291, gap 0.014 under a 0.02 bar →
**POSITION-INSENSITIVE**, which answers attack #6 directly. *Path Monte Carlo,
$100k at 1×* (proxy genome, block=6, 4,000 draws, full-history horizon):
**P(lose half) 0.442**, median worst DD −48.2% (−$48,152), p95 −72.8%, worst
−90.9%, longest under-water 64mo median / 163mo p95; **1.3× P(lose half) 0.765**;
at a 3-year horizon 1.0× is 0.036. The exact champion's own disclosed row is
−46.88% maxDD and P(lose half) 0.232 — **compare, do not average.**

**N7 — memory, registry, leaderboard.** Every receipt walked into the evidence
memory and `LEADERBOARD.md`, whose head is ranked on the **beta-matched t** with
the family correction beside it — pinned by a test in which a cell with 45× the
terminal wealth and t 0.1 must not appear in the head.

---

## Claims for Fable to attack

1. **N1's headline is one family of one signal.** `revisions` is the only
   selector where broadening pays; the other nine mostly lose. Is +4.670pp/yr at
   Holm 0.4884 distinguishable from the best of 100 correlated comparisons?
2. **The delta's era-stability is the claim, not the level.** The construction
   delta is positive in 3 of 3 eras while every *level* is 1999-2007. Attack:
   a difference of two books built from the same ranking shares most of its noise
   — is the paired t honest about that?
3. **The ensemble's t 2.424 is a three-arm ensemble's t.** On the 107 months when
   all eight arms exist it is t 0.697. Which of those is the object we would run?
4. **The reliability weighting losing to equal weight may be a window artefact.**
   36 months was the mandate's number and was not tuned — but it was also not
   tested at any other length, so "reliability bought nothing" is a statement
   about one window.
5. **N3's curve may be a cost-model result, not a capacity result.** The $100k
   book's −9.63%/yr is a measured 74.5 bps one-way spread applied to a book with
   ~100% monthly turnover. Under hysteresis the same names would pay a third of
   that. The floor lane and the construction lane were never crossed.
6. **The battery's floor of 0.5× is a floor on a 120-name 9-year panel**, not on
   ours. On the real panel the MDE is 4.66%/yr; on the synthetic ladder the
   recovered rung is an oracle excess of ~8.8%/yr. Are these the same statement?
7. **The event world says breadth dilutes a concentrated edge, on synthetic
   data.** Nothing in this night tests that on the real event table, because the
   books were not run.
8. **N6.3's path Monte Carlo is a PROXY.** The parent genome lacks the champion's
   vol overlay, and its P(lose half) is 0.442 against the champion's disclosed
   0.232. Which number belongs in the contract's worst-case table?
9. **N5's novelty feature is untestable where it matters.** 18,071 of ~98,000
   canonical events have a matured forward return, all 2015-2018. A verdict of
   WITHIN_MODEL_NULL on 18% of the corpus's oldest slice is not a verdict on the
   feature.
10. **N1.4's monotone shape has a competing explanation.** The refit premium may
    fall with breadth because a broad book's excess is simply *less volatile*, so
    the same pp is a smaller t — the receipt reports pp, not standardised effect.

---

## Test counts, spend, provenance

- **Finance fast suite: 7127 passed, 20 skipped, 122 deselected in 511.35 s,
  exit 0** (`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"
  -q --timeout=300`). New this night: `test_fundamental_law.py` **18**,
  `test_n1_n2_construction.py` **16**, `test_n6_battery_v2_and_n7.py` **15**,
  `test_n3_size_aware_floors.py` **37 (+3 skipped by design)**,
  `test_n4_event_table.py` **23**, `test_n6b_exams_and_paths.py` **22**,
  `test_n5_unsupervised.py` **18** — **149 new checks**.
- **Terminal: 80 suites / 3,226 checks, 4 suites FAILING — and they fail
  identically with tonight's change stashed.** `tests_smoke_equity`,
  `tests_smoke_pair`, `tests_smoke_entry_timing` and `tests_smoke` (which imports
  equity). Proximate cause: `run_pass` returns `considered=0` in the dry
  end-to-end. It was **ET Sunday 13:34** when this ran. Reported, not fixed — it
  is the fleet's entry gate and Tuesday's pre-open is attended.
- **LLM spend: $0.03** of an $8.00 cap. All DeepSeek, all N6.2: 192 calls,
  ledger $0.025525, provider balance $9.28 before and after (below its own
  reporting granularity). N1/N2/N3/N4/N5/N6.1/N6.3/N7: **$0.00**. No Anthropic or
  OpenAI call was made.
- Every receipt carries `argv`, resolved config and the SHA-256 of every input
  actually opened (`backend/services/receipt_provenance.attach`).
- Read-only throughout. The only network activity was N4's Alpaca/Benzinga news
  pull, which continues in a detached process and writes to the terminal repo's
  corpus.

## Defects found by the work itself

1. `realised_ir` on a constant series returned **6.6e15** — a Sharpe made of
   float noise, the same shape as the degenerate OLS that turned CI red on 09-06.
   The test is now relative to the series' own scale.
2. The N1.4 prediction cache's fingerprint check **could never fail**: parquet
   does not persist `DataFrame.attrs`, so the read-back was always `None` and a
   cache built on one universe would have been served to another. Fingerprint
   moved to a sidecar; a mismatch refuses the cache.
3. The battery's graph world came back `REFUSED: features unavailable` from a
   **call-site bug** — `synthetic_edges` writes a file and was handed a
   directory; `attach_graph_features` returns three things and was unpacked into
   two. In a receipt that refusal reads exactly like a machine that cannot see
   graph edges.
4. N4's first coverage metric divided raw symbol counts by a permno universe and
   printed shares **over 400%**, because IBES covers many non-CRSP securities.
5. The swarm's `research_budget` governor **refused N6.2 at exactly 50 calls**
   ("zero-yield rate 100.0%") because it requires minted prediction ids that a
   monotonicity contrast never mints. Tool-fit mismatch, not a budget refusal;
   preserved in the receipt rather than routed around.

## What is queued, not done

The PEAD / revision-on-event / surprise×reaction books over the event table (N4's
pull is ~27% through) · the self-supervised re-training on event features (its
two blockers are named) · the 13D/G 2015-2024 backfill (~4,000 days) · Form 4
(no source on disk in either repo) · N3's OBSERVE_ONLY live population (needs
venue credentials) · the terminal repo's four weekend-failing suites · the
crossing of N3's measured spreads with N1's hysteresis, which claim 5 above says
is the next honest cell.
