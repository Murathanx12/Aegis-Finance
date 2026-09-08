# BUILD — NIGHT LAB, 2026-09-07 — construction, events, unsupervised, simulations

Mandate `NIGHT_LAB_2026-09-07_OPUS_PROMPT.md`. Seven lanes, five agents, local
commits only — **nothing pushed, sealed, ordered, deployed or changed on
Railway.** Receipts: `backend/data/optimus/night_lab_2026-09-07/`. CI was
**green on HEAD `7088764`** before any work started.

## RESULTS SCOREBOARD

### The N1 sentence — does the IC become money?

> **No, not on its own — but the construction was destroying a real, measurable
> amount, and collecting it is worth +4.670pp/yr on one family.** Broadening
> every book raises the transfer coefficient from **0.11–0.20 to 0.28–0.64** and
> effective names from **7–19 to 50–300**, with no prediction changed. Yet only
> **15 of 100** broad-minus-control comparisons are positive (median
> **−2.853pp/yr**). The exception is the revision family:
> `revisions|k=300|rank|hold=600|25bps` beats its own top-50 VW control by
> **+4.670pp/yr, t 2.584**, TC **0.132 → 0.4865**, effective names
> **12.2 → 224.9**, same 309 months, same frozen column — and that delta is
> **positive in all three eras** (+0.51 / +0.23 / +0.42 %/mo) while every *level*
> is 1999-2007. **Holm over the 100-comparison delta family: 0.4884. Nothing
> survives.**

One column, two constructions, 1999–2024 — **shown AT EQUAL COST**, because a
construction effect and a cost effect quoted in one column is two experiments
wearing one label. Corrected 2026-09-07 (X9): the original table put the 25 bps
control beside the 10 bps broad book, so its 3.66 → 29.27 line was **8.0× of
which the construction bought ~5.0× and the cost rate bought the rest**. The
receipt is `N1_construction_books.json::cells`; the four cells are named.

**At 25 bps** (`revisions|k=50|vw|hold=none|25bps` → `revisions|k=300|ew|hold=600|25bps`):

| book on `revisions` | β | TC | eff. names | TW net | market | β-matched |
|---|---|---|---|---|---|---|
| top-50 VW (the incumbent) | 0.882 | 0.132 | 12.2 | **3.66** | 13.18 | −3.494%/yr t −1.54 |
| top-300 EW hold-600 | 1.0855 | 0.5869 | 299.4 | **18.14** | 13.18 | +1.096%/yr t 0.659 |

**At 10 bps** (`revisions|k=50|vw|hold=none|10bps` → `revisions|k=300|ew|hold=600|10bps`):

| book on `revisions` | β | TC | eff. names | TW net | market | β-matched |
|---|---|---|---|---|---|---|
| top-50 VW (the incumbent) | 0.8823 | 0.132 | 12.2 | **8.96** | 13.18 | −0.004%/yr t −0.002 |
| top-300 EW hold-600 | 1.0861 | 0.5869 | 299.4 | **29.27** | 13.18 | +2.964%/yr t 1.785 |

**`29.27` may never be quoted beside `3.66` as one comparison.** The same-cost
pairs are **3.66 → 18.14 at 25 bps** (4.96×) and **8.96 → 29.27 at 10 bps**
(3.27×). `backend/tests/test_x9_doc_numbers.py` fails if the two strings meet
again in `docs/`.

**RESULT IMPROVEMENT: a mechanism, not a claim.** The construction effect is
era-stable; the alpha it uncovers is not. Level family 160 cells, family-min p
0.004947, best cell Holm **0.79152**, **0 survive**, verdict **NOISE** (DSR
0.4513).

| | |
|---|---|
| **Best historical net strategy** | `ensemble_ew\|k=100\|ew\|hold=200\|10bps` — β **1.1951**, β-matched **+5.651%/yr t 2.424** over 309 months, TW **62.87** vs market **13.18**. Its edge is 1999-2007 (t 2.988); on the 107 months when it is genuinely an eight-arm ensemble, **+2.142%/yr t 0.697** |
| **Best forward paper strategy** | unchanged — no order placed, no book touched |
| **Independent selector count** | unchanged — nothing promoted |
| **Cells tested / promoted** | 160 level + 100 delta + 12 cadence + 12 floor / **0** |
| **New actionable finding** | **YES — four** (the construction tax; the ensemble's era; the floor curve's direction; breadth dilutes a concentrated edge) |
| **External execution drag** | not measured (no orders). The *modelled* drag is N3's measured TAQ line |
| **LLM spend** | **$0.03** of an $8.00 cap — DeepSeek only, all in N6.2 |

## Lane by lane

**N1 — construction.** `learner/fundamental_law.py` (new) attaches IC, effective
breadth `(Σw)²/Σw²`, transfer coefficient (corr of realised *active* weights with
z(signal) over the whole admissible cross-section, **not** the holdings), β and
implied-vs-realised IR to every book; TC < 0.5 ⇒ `CONSTRUCTION_DEFECT`, i.e. the
signal verdict is not readable from that book. Every term returns `None` with a
reason rather than a zero it did not measure. `evaluate.book()` gains opt-in
`return_weights` and `weight="rank"`; the default key set stays byte-identical to
v1's receipt. **N1.3:** the index-hedged long-short hedges *mostly* correctly — realised β
spans **−0.0605 … 0.4254** over the 20 cells: **14 of 20 sit inside |β| ≤ 0.05
and six do not** — `momentum` −0.0601/−0.0605, `ridge` 0.2047/0.2056 and
`encoder` 0.4238/0.4254 (each at both cost rates; the ridge and encoder cells are
47-month windows, so those four carry real market exposure and their numbers are
not a hedged book's). Corrected 2026-09-07: the earlier "0.00–0.05" was false for
six cells. It **loses — 19 of 20 cells negative**, all negative at 25 bps; best
+0.346%/yr over cash t 0.178. The **exclusion book** is the survivor shape:
universe EW minus the bottom decile beats the EW universe by **+0.861pp/yr t
2.487** at 10 bps (TW 18.72 vs 14.41), +0.482pp t 1.382 at 25 bps. **N1.4:**
monthly refit beats the *annual* control in **12 of 12** constructions (median
+1.204pp/yr, family-min p 0.1098, best Holm 1.0) — and the gain **falls sevenfold
as TC rises**: +2.658pp at top-50 VW (TC 0.160) → +0.363pp at top-300 rank (TC
0.483). A2's +5.751pp was the narrowest instrument we own, against a frozen-once
baseline nobody proposes.

**N2 — the selection-free ensemble.** Eight trained arms, monthly percentile
ranks, no arm chosen. **The reliability weighting the mandate asked for LOSES to
equal weight** by −1.041pp/yr (t −0.907). Equal weight: DSR 0.9687, MDE 4.66%/yr,
powered False, family = 2 (both weightings reported); its inputs were searched and
the receipt says so.

**N3 — size-aware floors.** `execution_authority` (terminal repo) learns
`book_size_usd`; omitting it reproduces flat-$3m byte for byte; unresolvable ⇒
`CANNOT_DETERMINE`, never a permissive default. The curve runs the **wrong way**
for the small-book thesis:

| book | floor @1% ADV | TAQ band | measured-cost edge | t |
|---|---|---|---|---|
| institutional | $3.0m | 1m–5m | +2.795%/yr | 1.019 |
| **$100k** | **$500k** | 100k–1m | **−9.629%/yr** | **−3.279** |
| $1m | $5.0m | 5m–10m | +3.397%/yr | 1.369 |
| $10m | $50m | 50m+ | +4.245%/yr | 2.176 |

Family 12, family-max p 0.99948, 0 survive Holm. All three named dead cells stay
dead: the small-cap 5-session reversal goes **−0.49%/5-session t −2.30** at the
$100k floor (measured ~74.5 bps one-way); S28's $100k–$1m band is gross +0.19%/yr
against a **17.86%/yr** cost line. Capacity is an advantage in what a small book
*may* hold and a disadvantage in what it *costs* to hold.

**N4 — the event-time table.** `event_table_v1.parquet`: **993,005 rows
spanning 2015-2026** — **789,277 of them in 2015-2024**, 107,986 in 2025 and
95,742 in 2026 — at **81–86%** of the CRSP-common proxy per year (2015-2024; the
proxy is 0 for 2025-2026, so that share is `null` there and is not claimed;
corrected 2026-09-07, the earlier "993,005 rows, 2015-2024" put a 2015-2026 count
under a 2015-2024 label) — IBES surprises 618,419 ·
8-K 276,978 · news 95,228 and growing · 13D/G 2,380. Three gaps stated, not
papered over: **13D/G is effectively absent 2015-2024** (all rows from seven days
in Aug 2026); **Form 4 is absent from both repos** (a guard test fails if a run
fabricates one); the puller has no `tradable` universe, so `fleet` (~156 names)
was used and flagged. **PEAD / revision-on-event / surprise×reaction books are
NOT run** — the Alpaca leg is ~27% through, and grading on a quarter of a source
is file size mistaken for sample size. The pull continues in a detached process;
`python -m scripts.n4_event_table --build` re-joins in ~9 s.

**N5 — unsupervised.** *The four states, third null:* a name-path-controlled
derangement swaps whole real state-label PATHS between companies — calendar
fixed, each name's own forward return untouched — and **CLEARS at p 0.005** (371,848
rows, 5,358 names, 200 draws, both 1m and 3m). Null 1 clears (0.000), **null 2
still fails (1.000)**. **FINAL VERDICT CANNOT_DETERMINE**, and a genuinely new
split rather than a restatement. **The four states are DEMOTED to
informational-only everywhere** — never a sizing, admission or routing input;
`potential_universe.STATE_SEMANTICS` is already inert but its text quotes null 1
alone and *reads* as validated. *Event compression:* **137,190** news rows → **105,494
canonical events, ratio 1.3005**, declared a **lower bound** (corrected
2026-09-07 from a stale 127,157 → 97,949 / 1.298 snapshot; the receipt at HEAD is
`N5_event_compression.json`) (TF-IDF catches
reformatted duplicates, misses same-event stories with no shared vocabulary).
NVIDIA NIM re-probed **OK in 935 ms** against the 09-05 receipt's
CANNOT_DETERMINE at 30.2 s — transient network, not a dead key. Novelty on the
18,071 events with a matured forward return: **IC 0.003663, model-null percentile
0.92, p 0.0846 → WITHIN_MODEL_NULL**; only 2015-2018 is testable, so the
three-era table **cannot be filled and is not claimed**. *Pre-training:* CUDA
**True** (RTX 5060, torch 2.11.0+cu128) by *running* the designated interpreter;
the 8-seed arm is stacked in the ensemble at 0.253 weight share, never a lone
champion; re-training on N4/N5 features **DEFERRED**, both blockers named.

**N6 — simulations.** *Battery v2:* **5 of 5 worlds ALL_PASS** through N1's
control construction, N1's broad construction and N2's ensemble — linear 9.914,
regime 7.479, graph 10.473, event 33.006, **null's best cell t 1.577 → NOISE**.
The new **event world** (alpha on the top decile, zero on the other 90%, demeaned
within the month so the EW market leg is unchanged by construction) is where the
constructions disagree most: **control t 33.0 vs broad t 14.2** — *breadth is not
free when the edge is concentrated*, obtained where the answer was known, and a
result about N4's whole programme. *Ladder:* the machine recovers B1's planted
scale (t 5.20, IC 0.068) and **half of it** (t 2.02, IC 0.019), losing a quarter
(0.80) and an eighth (−0.28) — Fable's attack #5 answered with a number.
*Fantasy exams round 2:* 40 new event pairs, **40/40 monotone**, canary **END 0/8, FRONT
1/8** (`CANARY-045-front` moved; round-1 rate was also 1/8 — corrected
2026-09-07, the single "0/8" was the END arm only);
the new clause-position control gives |Δp_up| END 0.305 vs FRONT 0.291, gap 0.014
under a 0.02 bar → **POSITION-INSENSITIVE** (attack #6 answered). *Path MC,
$100k at 1×* (proxy genome, block 6, 4,000 draws): **P(lose half) 0.442**, median
worst DD −48.2% (−$48,152), p95 −72.8%, worst −90.9%, under-water 64mo median /
163mo p95; **1.3× → 0.765**; 3-year horizon 1.0× → 0.036. The exact champion's
disclosed row is −46.88% maxDD and P(lose half) 0.232 — **compare, do not
average.**

**N7 — memory, registry, board.** **17 receipts, 177 evidence rows, 166 cells,
4 families**; registry export 12 rows (8 SUPPORTED, 4 COST_KILLED) into
`signal_registry.yaml`'s read-only `conditional_evidence`. The board's head is
ranked on the **β-matched t** with the family correction beside it, pinned by a
test in which a cell with 45× the terminal wealth and t 0.1 must not appear.

## Claims for Fable to attack

1. **N1's headline is one family of one signal.** Nine of ten selectors lose when
   broadened. Is +4.670pp/yr at Holm 0.4884 distinguishable from the best of 100
   correlated comparisons?
2. **The delta's era-stability is the claim, not the level** — but a difference of
   two books built from one ranking shares most of its noise. Is the paired t
   honest about that?
3. **The ensemble's t 2.424 is a three-arm ensemble's t.** On the 107 months when
   all eight arms exist it is t 0.697. Which is the object we would run?
4. **"Reliability bought nothing" is a statement about one window.** 36 months was
   the mandate's number, untuned — and untested at any other length.
5. **N3's curve may be a cost-model result, not a capacity result.** The $100k
   book's −9.63%/yr is a 74.5 bps spread applied at ~100% monthly turnover. Under
   N1's hysteresis it would pay a third of that. **The floor lane and the
   construction lane were never crossed. That is the next cell.**
6. **The battery's 0.5× floor is a floor on a 120-name 9-year panel**, an oracle
   excess near 8.8%/yr. Our real MDE is 4.66%/yr. Are these the same statement?
7. **"Breadth dilutes a concentrated edge" is synthetic.** Nothing tonight tests
   it on the real event table, because the books were not run.
8. **N6.3's Monte Carlo is a PROXY** without the champion's vol overlay: P(lose
   half) 0.442 vs the champion's disclosed 0.232. Which belongs in the contract?
9. **N5's novelty verdict covers 18% of the corpus's oldest slice.** 18,071 of
   ~98,000 canonical events, all 2015-2018. That is a verdict about that slice.
10. **N1.4's monotone shape has a competing explanation**: a broad book's excess
    is less volatile, so the same pp is a smaller t. The receipt reports pp.

## Tests, spend, provenance

- **Finance fast suite: 7142 passed, 17 skipped, 123 deselected in 460.68 s,
  exit 0** (`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"
  -q --timeout=300`). New this night, measured together: **158 passed, 3 skipped
  in 19.27 s** — `test_fundamental_law.py` 18 · `test_n1_n2_construction.py` 16 ·
  `test_n6_battery_v2_and_n7.py` 17 · `test_n3_size_aware_floors.py` 37 (+3
  skipped by design) · `test_n4_event_table.py` 23 ·
  `test_n6b_exams_and_paths.py` 22 · `test_n5_unsupervised.py` 25.
- **Terminal: 80 suites / 3,226 checks (3,213 before N3's 13), 4 suites FAILING —
  and they fail identically with tonight's change stashed**: `tests_smoke_equity`,
  `tests_smoke_pair`, `tests_smoke_entry_timing`, `tests_smoke`. Proximate cause:
  `run_pass` returns `considered=0` in the dry end-to-end. It was **ET Sunday
  13:34**. Reported, not fixed — it is the fleet's entry gate and Tuesday's
  pre-open is attended.
- **LLM spend $0.03** of an $8.00 cap: 192 DeepSeek calls, ledger $0.025525,
  provider balance $9.28 before and after (below its own reporting granularity).
  Every other lane **$0.00**. No Anthropic or OpenAI call was made.
- Every receipt carries `argv`, resolved config and the SHA-256 of every input
  actually opened (`receipt_provenance.attach`). The only network activity was
  N4's news pull, read-only, still running detached.

## Defects the work found in itself

1. `realised_ir` on a constant series returned **6.6e15** — a Sharpe of float
   noise, the shape of the degenerate OLS that turned CI red on 09-06. The zero
   test must be relative to the series' own scale, never `sd > 0`.
2. A prediction cache's fingerprint check **could never fail**: parquet does not
   persist `DataFrame.attrs`, so the read-back was always `None` and a cache built
   on one universe would have been served to another. Fingerprint → sidecar.
3. The battery's graph world returned `REFUSED: features unavailable` from a
   **call-site bug** (a file path handed a directory; a 3-tuple unpacked into 2).
   In a receipt that reads exactly like a machine that cannot see graph edges.
4. N4's first coverage metric printed shares **over 400%** — raw symbol counts
   over a permno universe, because IBES covers many non-CRSP securities.
5. N7's receipt guard demanded a `job` key and **dropped four real receipts** that
   use B1's `item` + `title` — the failure `record_receipt` was fixed for last
   weekend, reintroduced one layer up.
6. **Pre-existing, found by a loaded machine:** `job_receipts.write()` names the
   file from the **write** time while `test_receipts_come_back_newest_first`
   asserts on `started_at` at one-second resolution; a slow write inverts the
   order. One full-suite pass gave 7141/1-failed; it passes alone, as a file, and
   on the clean re-run. The fix is to derive the filename from `started`.
7. The swarm's `research_budget` governor **refused N6.2 at exactly 50 calls**
   ("zero-yield rate 100.0%") because it requires minted prediction ids a
   monotonicity contrast never mints. Tool-fit mismatch, not a budget refusal;
   preserved in the receipt rather than routed around.

## Queued, not done

The event books over N4's table (the pull is ~27% through) · self-supervised
re-training on event features (blockers named) · the 13D/G 2015-2024 backfill
(~4,000 days) · Form 4 (no source on disk in either repo) · N3's OBSERVE_ONLY
live population (needs venue credentials) · the terminal repo's four
weekend-failing suites · the `job_receipts` filename fix · **and the cell claim 5
names: N3's measured spreads crossed with N1's hysteresis.**
