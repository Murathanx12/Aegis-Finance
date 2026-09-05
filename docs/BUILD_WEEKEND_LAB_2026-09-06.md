# WEEKEND LAB — 2026-09-06/07 — did nineteen years say what seven could not?

*Written continuously by the lab, not at the end. Numbers are re-checked against
their receipts before each update; a line with no receipt is not in this file.*

---

## RESULTS SCOREBOARD (the house rule: this block comes before any code count)

| | |
|---|---|
| **Best historical net strategy vs the market** | *pending — W2 baseline still on its first pass* |
| **Best forward paper strategy** | unchanged; the lab placed no orders and touched no book |
| **Independent selector count** | unchanged |
| **New actionable finding** | **YES — three, below** |
| **External execution drag** | not measured this weekend (no orders) |
| **LLM spend** | **$0.00** — no LLM call was made |

**RESULT IMPROVEMENT SO FAR: the instrument got 2.2× longer, and two published
kinds of feature died under their own controls.** No strategy has yet been
promoted, and none was killed.

---

## 1. The one thing the weekend was for

Friday's night lab left a single number in the way: the best learner cell on
2013-2024 was **+14.4%/yr ahead of the market and NOISE by every honest test**
(DSR 0.197 against a 0.2305 noise bar, SPA p 0.29, PBO 0.29), and at that Sharpe
**t = 2 needed 16.1 years of out-of-sample months against the 7.0 on hand.**

That is a statistical ceiling, not a modelling one. So the weekend bought tape,
not model size.

### W1 — the long panel exists, and its early years are not thin

`learner/long_panel.py` → `train_table_long.parquet`, schema
`learner-train-table-3`.

| | incumbent | long panel |
|---|---|---|
| window | 2013-2024 | **1999-2024** |
| name-months | 605,410 | **925,757** |
| months | 143 | **310** |
| IBES loader pin | 605,410 | 1,228,757 name-months |
| CRSP daily rows read | ~13M | **31,051,486** |

**The roadmap's worry did not survive contact with the data.** It hedged that
"IBES coverage is thinner pre-2004 — print it; do not fake it." Printed:

| year | name-months | names | hygiene pass |
|---|---|---|---|
| 1999 (from March) | 19,733 | 2,895 | 0.804 |
| 2000 | 34,261 | 3,461 | 0.771 |
| 2004 | 35,283 | 3,316 | 0.788 |
| 2013 | 33,861 | 3,101 | 0.874 |
| 2024 | 38,124 | 3,420 | 0.773 |

The early era runs at roughly **85-90% of the late era's density**, not a
fraction of it. **Months, not rows, are what buy a t-statistic**, and months
went from 143 to 310.

### The share-basis fix holds in 1999, and the first gate that said so was broken

The 2026-09-04 share-basis correction (read the UNADJUSTED `ibes__ptgsumu`, never
rescale the adjusted file) had only ever been pinned on AAPL 2013-06. It needed a
test in the era it was never tested on.

**The first version of that gate could not pass.** It asked for `ratio` on rows
where `split_prior_year` is true — and `dataset.hygiene` defines
`target_readable = ... & ~split_prior_year`, so `build` NULLS `ratio` on exactly
those rows by construction. The gate saw zero rows, produced `nan`, and printed
FAIL. That is the failure CLAUDE.md already names: *a gate that cannot go green
is a broken gate, not a strict one.* Fixed by reading `ratio_unhygienic` — the
audit column that holds the raw ratio on precisely the suppressed rows — and by
matching the control on everything hygiene asks for **except** the split flag, so
the only difference between the two sides is the share-basis change itself.

**Result, 1999-2004:** 1,453 permnos with a share-basis change, 19,619 rows.

| | in-band rate | median ratio |
|---|---|---|
| names with a share-basis change | **0.9807** | 1.2149 |
| matched control, no change | 0.9780 | 1.2439 |

Gap **−0.0027**. A split-adjusted numerator over a raw denominator would move a
2:1 name's ratio by a factor of two and open a gap of tens of points. **PASS.**

---

## 2. Three findings, in order of how much they change what we do

### FINDING 1 — a t of −12 was a split artefact, and no test caught it

The behavioural feature `vwap_60d_gap` (price relative to its 60-session
volume-weighted average) first measured at **controlled t −12.06**, negative in
all three eras — by a distance the strongest controlled result in its table.

It was an artefact. The first construction took `Σ(prc·vol)/Σvol` — a **raw**
share-basis average over 60 sessions — and divided by **today's** `cfacpr`. For
any name that split inside the window the numerator mixes pre- and post-split
prices, the denominator mixes pre- and post-split share counts, and rescaling by
one day's factor corrects neither. Split-heavy names have distinctive forward
returns, so the feature was substantially measuring *did this name split
recently*.

The fix needs no extra data. Adjusted share volume is already derivable:

```
dollar_vol / adj_prc  =  (prc·vol) / (prc/cfacpr)  =  vol·cfacpr
```

so `Σdollar_vol / Σ(dollar_vol/adj_prc)` is a dollar-weighted average of
`adj_prc` itself — split-consistent by construction, one basis on both legs, no
rescaling at all.

**After the fix: controlled t −1.14. Nothing.**

This is `reference_farm_split_adjustment` arriving from a new direction, and the
uncomfortable part is the last clause: **no test caught it.** It was caught by
fixing the basis on principle before reading the result. Had the first run been
reported, the weekend's headline would have been an artefact.

*Related, same class:* `attention_z` is built on **dollar** volume rather than
share volume, deliberately — dollar volume is split-invariant, so the problem is
removed rather than corrected for. A share-count z-score reads a 2:1 split as a
6-sigma attention event.

### FINDING 2 — the 52-week-high effect is momentum on this universe

`W6_behavioural`, 925,757 rows, 309 months, 1999-2024. Each feature is reported
twice: its plain cross-sectional rank IC, and its coefficient in a **monthly
Fama-MacBeth regression that also holds momentum, size and vol** — because the
control belongs in the regression, not in a sentence after it.

| feature | rank IC | t (raw) | **t (controlled)** | eras +/− | verdict |
|---|---|---|---|---|---|
| `prox_52w_high` | +0.0556 | 5.39 | **−1.33** | 0/3 | **killed by controls** |
| `attention_z` | +0.0181 | 4.12 | **0.88** | 1/2 | **killed by controls** |
| `vwap_60d_gap` | +0.0143 | 2.10 | −1.14 | 0/3 | nothing |
| `prox_52w_low` | −0.0038 | −0.61 | −1.77 | 1/2 | nothing |
| `ret_5d` | −0.0120 | −2.10 | **−4.27** | 0/3 | **survives** |
| `attention_z_5d` | +0.0185 | 4.55 | **+2.71** | 2/1 | **survives** |
| `amihud_21d` | −0.0500 | −7.55 | **−2.37** | 0/3 | **survives** |

George–Hwang 52-week-high proximity looks like a strong effect at raw IC t 5.39
and **adds nothing** once the thing it correlates with is held in the same
regression. Same for single-day attention; only its 5-day average survives.

What does survive, on 26 years and with controls:
- **short-run reversal** (`ret_5d`, t −4.27, same sign in 3 of 3 eras) — classic, and it replicates;
- **5-day attention** (t +2.71, 2 of 3 eras);
- **Amihud illiquidity, with the sign INVERTED from the textbook** (t −2.37, 3 of 3 eras). More illiquid → *worse* forward excess. Plausibly because the analyst-covered universe with a $2 floor has already screened out the compensated end of illiquidity, so what is left is the uncompensated end. Flagged as a claim for Fable to attack, not as a result.

### FINDING 3 — the winner/matched-loser factory found an archetype that survives Holm

`W7_matched_loser`, **297 formation months (1999-04 → 2023-12)**, 50 residual
winners × 5 matched controls each.

The design, because it is the whole result: the 12-month forward excess is
**residualised within each month on size, momentum and vol ranks**, and each
winner is matched to five names in the **same sector** with the nearest (size,
momentum, vol) ranks that are neither winners nor losers. Every feature is dated
at the **formation month**; the outcome is twelve months later. So a difference
that survives is a difference that was **observable beforehand** — the Micron
test — not a story told afterwards.

**The loser side is what makes it a test.** Look at the largest t's:

| feature | winner − control | loser − control | reading |
|---|---|---|---|
| `vol_60d__xs` | +0.0257, block-t **19.0** | +0.0316, block-t **~30** | same direction both tails |
| `log_market_cap__xs` | −0.0225, block-t **−10.7** | −0.0263, block-t **−24** | same direction both tails |
| `dispersion__xs` | +0.0602, block-t **11.8** | +0.0747, block-t **~25** | same direction both tails |

Small, cheap, volatile, high-dispersion names are over-represented in **both**
tails. That is a statement about being **extreme**, not about being **right**,
and every one of them is correctly excluded.

What survives the matched control, a non-overlapping |t| ≥ 2.5, a consistent sign
in ≥ 2 of 3 eras, **and** a loser side that moves differently:

| feature | winner − control | naive t | NW t | **block t** | BH q | **Holm p** | eras |
|---|---|---|---|---|---|---|---|
| `log_dollar_vol_20d` | −0.1308 | −9.75 | −4.51 | **−4.57** | 1.7e-05 | **0.00018** | 0+/3− |
| `log_dollar_vol_20d__xs` | −0.0105 | −7.71 | −3.63 | **−3.91** | 0.00027 | **0.0031** | 0+/3− |
| `consensus_rev_1m__xs` | +0.0094 | 3.97 | 3.50 | **3.73** | 0.00053 | **0.0062** | 3+/0− |
| `net_rev_4w` | +0.0108 | 3.57 | 3.02 | 3.05 | 0.0050 | 0.063 | 2+/1− |
| `net_rev_1m` | +0.0111 | 3.65 | 2.98 | 2.98 | 0.0062 | 0.079 | 3+/0− |
| `consensus__xs` | −0.0250 | −7.06 | −2.94 | −2.72 | 0.012 | 0.152 | 0+/3− |
| `consensus_rev_1m` | +0.0058 | 3.06 | 2.91 | 2.70 | 0.012 | 0.152 | 3+/0− |
| `net_rev_4w__xs` | +0.0069 | 2.95 | 2.47 | 2.50 | 0.021 | 0.259 | 2+/1− |

Eight candidates, but only **three DISTINCT ideas** — `net_rev_*` /
`consensus_rev_*` and their `__xs` ranks are four views of one idea, and counting
them separately would inflate the finding by construction. **All 8 survive
BH-FDR 10%; 3 survive Holm 5%** (CANON §63: screen = BH, export = Holm).

**The archetype, in words.** Against a name matched on sector, size, momentum and
vol, a future 12-month residual winner was, at formation:

1. **thinly traded for its size** — market cap is matched, dollar volume is not, so this is *low turnover*, not *small* (Holm p 0.00018, same sign in 3 of 3 eras);
2. **being upgraded** — analyst ratings revising up (Holm p 0.0062, 3 of 3 eras);
3. **rated worse than its twin** to begin with (`consensus__xs` −2.72, BH-surviving, 3 of 3 eras).

*Unloved, illiquid for its size, and improving from a low base.* That is a
falsifiable archetype and it is not a restatement of size or momentum, because
both were matched away.

**The honest counterweight — the recall baseline.** Share of each month's residual
top-50 already in the top decile of each precursor at formation, against the 0.10
a chance precursor gets:

| precursor | recall | lift |
|---|---|---|
| analyst upside | **0.195** | 2.0× |
| net revisions | 0.140 | 1.4× |
| 12-1 momentum | 0.135 | 1.4× |

So this is a real precursor with a **2× lift, not a discovery machine**. A mean
difference alone could not have told those apart, which is why both are printed.

### FINDING 4 — supply-chain momentum: CANNOT DETERMINE, and the reason is scope

`learner/features_graph.py`, built this weekend from `MARKET-GRAPH-1`.

The roadmap said the edges exist "2015-2024 only". **Measured, they do not.**
`filing_date` runs **2014-04-24 → 2024-06-26**; the source's own `date` column is
a quarterly research cut running 1–428 days *after* the filing (median 154) and
is never used as `valid_from`. Real coverage: **2014-05 → 2024-12, 129 months,
11 panel years of 26.**

Nothing reaches |t| = 2 in any of three variants. The best-directed arm is
customer momentum, equal-weight, **FM t 1.45** — the right sign for the
Cohen–Frazzini diffusion story, and **needing 18.6 years of tape against the 9.75
the graph has.** The controls killed nothing, because the raw ICs were already
~0.01 at |t| < 1.5; there was never a raw signal to strip.

Three scope facts that bound any future claim:

- **The median "customer average" is an average of ONE name** (median neighbours: customer 1, supplier 1, competitor 2). This is not a supply-chain graph; it is a handful of named counterparties per filer.
- The resolver placed **30.6% of raw mentions**; 69.2% of the residue is *not in CRSP* — Samsung, TSMC, Foxconn, Sanofi. **The graph is structurally missing most of the actual supply chain because most of it is not US-listed.**
- Every monthly cross-section is the graph universe (89–219 names), i.e. large widely-covered filers — not the panel.

The join matches **2.08% of panel rows**, against a ceiling of 4.4% (386 of 8,981
names × 11 of 26 years). `attach` prints all three numbers so nobody "fixes" it by
widening the tolerance.

**`MECHANISM_REJECTED` would be wrong.** This closes *this graph at this size*:
`FAILED_VARIANT` / `DEPRIORITIZED`, pending a wider edge set.

### FINDING 5 — my own survivor filter had a sign bug that hid three of four features

The first version of the era test asked `holds_in_2_of_3` — how many eras had a
**positive** mean. That is right for a **strategy's excess return**, where the
book is long and a negative era is a failure. It is wrong for a **feature's
coefficient**: a reliably negative feature is a signal, traded the other way
round. The filter was dropping `ret_5d`, `amihud_21d` and (at the time)
`vwap_60d_gap` for the crime of being consistently negative.

Both are now reported — `holds_in_2_of_3` and `same_sign_in_2_of_3` — and every
caller names which one it means.

---

## 3. Infrastructure built (all of it running, none of it theoretical)

| what | where | why it exists |
|---|---|---|
| CUDA torch | 2.11.0+cu128, RTX 5060 Laptop, sm_120 | verified with a real matmul: 20 GPU matmuls in 0.433 s vs 3 CPU matmuls in 0.791 s (~36× per op). Blackwell has no kernels before cu128. |
| the long panel | `learner/long_panel.py` | 1999-2024, era column, coverage-by-year, the early-era share-basis gate, and `--regate` so a wrong gate costs no rebuild |
| `power_note` | `learner/inference.py` | `t = SR·√T` inverted: `years_needed_for_t2` beside every Sharpe, so NOISE and UNDERPOWERED stop being written in the same word |
| turnover hysteresis | `learner/evaluate.py` `book(hold_k=)` | buy at rank ≤ k, hold until rank > hold_k. On pure noise it cuts turnover 0.751 → 0.503 and moves net toward gross — it saves cost, it cannot create edge. REFUSES when `hold_k ≤ k`. |
| a real quantile head | `learner/models.py` `fit_predict(quantile=)` | pinball objective. q0.9 vs q0.1 correlate **−0.885**, and q0.9 vs the mean head only **−0.25** — ranking by the right tail is a genuinely different book. REFUSES rather than returning the mean head under a q-labelled name. |
| behavioural features | `learner/features_price.py` | 31,051,486 rows, 1998-2024, 94-100% coverage per column |
| the weekend runner | `scripts/weekend_lab.py` | variant cycling (twenty passes = twenty questions, not one question twenty times), two-strike skip, and a BEST SO FAR block rewritten at the top of the leaderboard each pass |
| evidence memory | `learner/evidence_memory.py` | **a single pass can neither promote nor kill**; REFUTED additionally needs three passes that each HAD THE POWER to detect the effect |

---

## 4. The honest part: three unreachable gates in one session

Three times today a gate was written against a key or column that could not
exist, and each would have printed a clean, false result:

1. the early-era share-basis gate read `ratio`, which hygiene NULLS on exactly the rows it was inspecting → permanent FAIL;
2. W7's archetype bar read `t_hac`/`t_block`, but `evaluate.overlap_corrected` returns `t_newey_west`/`block_t_block` → every corrected t came back `None`, and the job printed **"0 archetype candidates"** as though that were a finding;
3. W8's null bar read `p_value`, but `states.shuffled_null` returns `p_value_one_sided`.

All three now **REFUSE** on a missing key instead of defaulting to `None`. The
pattern is worth naming because it is not a typo class — it is that *a missing
input and a negative result look identical downstream*, and the default value is
what makes them indistinguishable.

---

## 5. Still running / open

- **W2** — the 32-cell learner grid on 26 years. First pass in flight.
- **W7** — winner vs matched loser, re-running with the corrected overlap t.
- **W8** — market states with three nulls.
- **W3 / W4 / W5** — neural on GPU, supply-chain graph, options surface: in progress in parallel lanes.

*Claims for Fable to attack are marked as such above.*
