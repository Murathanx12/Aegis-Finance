# How often does the evidence ladder label a book with no edge? (cloud audit, 2026-10-07)

**RESULT IMPROVEMENT: NONE.** This note measures a label, not a strategy.

**Answer:** about **four times in ten** at any single look, and **seven to nine times in ten** at some
point once the label is recomputed every session. `REPLICATED` is reached by **a quarter to a third** of
no-edge books through its fair-twin clause. For a book that really has a 10%/yr edge at a 16%/yr
tracking error, the badge is only **1.2-1.6x** more likely than for a book with none.

Receipt: `backend/data/optimus/audits/evidence_ladder_null_audit_20261007T062317Z.json` (20,000 paths, seed
20261007). Reproduce: `python -m scripts.evidence_ladder_null_audit --receipt` (55 s; seeded, so the table
is identical). Tests: `backend/tests/test_evidence_ladder_null_audit.py`.

## 1. The rule

`backend/services/book_dna.py::evidence_label` (the public ladder; `LABEL_LADDER`, line 61):

- `EARLY_EVIDENCE` = at least `BOOK_DNA_EARLY_MIN_SESSIONS` (21) sessions, compounded excess over SPY
  `> 0`, and at least 2 of 3 contiguous sub-window excesses `> 0` (`book_dna.subwindows`);
- `REPLICATED` = `EARLY_EVIDENCE` and an excess over the fair twin `> 0` by any margin (or a same-rule
  sibling that is itself `EARLY_EVIDENCE`).

Every clause is a SIGN. A sign rule's rate under "no edge" does not depend on the book's size or the
market's drift, and depends on volatility only through compounding drag (more tracking variance makes a
no-edge book slightly *less* likely to be labelled; at ~16%/yr it is under a point). So the rate is a
property of the rule and can be measured without any of the repo's data.

## 2. How it was measured

Synthetic daily returns: SPY with 16%/yr volatility; a book = SPY + edge + tracking noise (16%/yr); a
fair twin = SPY + its own tracking noise (independent, or correlated 0.5 / 0.8 with the book's). Every
single-look cell runs the paths through **`book_dna.subwindows` and `book_dna.evidence_label`
themselves**. The daily re-evaluation (a label recomputed at every session from 21 on, which is what a
page that rebuilds each day does) uses a vectorised copy of the same two functions; the audit first
checks that copy against the module on 3,200 (path, look) pairs and **refuses to print a number if any
pair disagrees** (`check_vectorised_against_module`). Fat tails: Student t(4) innovations as a
robustness row. Beside the ladder sits a time-uniform alternative, Robbins' normal-mixture boundary on
the cumulative excess (Howard, Ramdas, McAuliffe and Sekhon, 2021), whose crossing probability under no
edge is at most alpha at every look (Ville's inequality); alpha = 0.05, mixture scale 63 sessions.

## 3. Results (from the receipt)

Single look, P(label >= `EARLY_EVIDENCE`):

| edge / yr | n = 21 | n = 42 | n = 63 | n = 126 | n = 252 |
|---|---:|---:|---:|---:|---:|
| **0% (no edge)** | **0.407** | **0.407** | **0.401** | **0.400** | **0.391** |
| 5% | 0.447 | 0.456 | 0.461 | 0.484 | 0.510 |
| 10% | 0.481 | 0.509 | 0.526 | 0.574 | 0.629 |
| 20% | 0.552 | 0.600 | 0.632 | 0.716 | 0.816 |

Daily re-evaluation from session 21, P(EVER labelled) against the time-uniform boundary:

| edge / yr | through session | ever `EARLY_EVIDENCE` | ever crosses Robbins (alpha 0.05) |
|---|---:|---:|---:|
| **0%** | 63 | **0.728** | 0.000 |
| **0%** | 126 | **0.806** | 0.002 |
| **0%** | 252 | **0.859** | 0.005 |
| 10% | 252 | 0.938 | 0.021 |
| 20% | 252 | 0.977 | 0.069 |

No edge, P(`REPLICATED`) through the fair-twin clause alone: **0.31** (twin noise independent),
**0.28** (correlation 0.5), **0.24** (correlation 0.8), flat across n = 21 / 63 / 252.

No edge with t(4) tails: 0.411 / 0.403 / 0.388 at n = 21 / 63 / 252 (the rate is not a Gaussian artefact).

Likelihood ratio of the badge, P(`EARLY_EVIDENCE` | edge) / P(... | no edge): 1.10-1.30 for 5%/yr,
**1.18-1.61 for 10%/yr**, 1.36-2.09 for 20%/yr (n = 21 to 252).

## 4. What it means

1. **`EARLY_EVIDENCE` reads as "the excess is positive and not all in one third of the window."** That is a
   description of the past (which is exactly what `OBSERVED(n)` already says), not evidence: four in ten
   coin-flip books have it at any moment, and most have had it at some point within a quarter.
2. **The badge barely moves the odds.** At a 10%/yr edge and a realistic tracking error, a book with
   the badge is at most 1.6 times as likely to be the real one. Unless most of the 362 priced books
   already had a real edge, a page of badges would be mostly no-edge books.
3. **`REPLICATED` through the twin clause is not replication.** A quarter to a third of no-edge books
   reach it. Review C3 F7 called the bar "too low for the rung's name"; this is the number.
4. **Why it has not misled anyone yet:** per review C3 F7, no book has a dense >= 21-session series
   (their sub-windows are `NOT_COMPUTABLE`), so all 362 books print `OBSERVED(n)`. That protection is a
   property of the data feed, and it ends the day the fleet grader and the night-book NAV become dense.
5. **The honest alternative has the honest cost.** A time-uniform boundary holds its false-positive rate
   at every daily look (0.5% here), but a book with an information ratio of 1.25 (20%/yr over 16%/yr)
   crosses it only 6.9% of the time within a year. That is the same wall the rest of the programme keeps
   meeting (the MDE), shown here at the level of a label rather than a trial.

## 5. Options for the owner (none applied; `book_dna` is unchanged)

| option | effect | cost |
|---|---|---|
| A. Print the null rate beside the badge ("a no-edge book shows this 40% of the time") | honest at once; no rule change | the badge stays near-uninformative |
| B. Rename the rung to what it is (e.g. `POSITIVE_SO_FAR`) and keep `EARLY_EVIDENCE` unawarded | words match the measurement | a public vocabulary change |
| C. Award `EARLY_EVIDENCE` only on a time-uniform crossing (Robbins mixture or an e-process on the excess, alpha 0.05, its n and boundary printed on the badge); `REPLICATED` the same against the fair twin | false-positive rate bounded at every look, including daily re-looks | almost no book will earn it within a year, which is the truth |
| D. Keep the sign rule but add a minimum t-statistic | fewer false badges | still invalid under daily re-looks unless the threshold grows with n |

The fit with the house rules ("a guard that cannot go green is a broken guard" against "every number
carries its evidence label") points to **C for the award plus A for the display**: the ladder keeps a
rung that can be reached, and it can only be reached by evidence that survives the daily re-look. The
prior-art map for the measurement system (`edge_measurement_prior_art_cloud_2026-10-07.md`, same folder)
covers confidence sequences and e-values.

## 6. Limits

Independent days (positive autocorrelation in the excess would raise the no-edge rate, not lower it);
one tracking-error level for the edge rows (the no-edge rows do not need one); the fair twin modelled as
SPY plus noise, not as the repo's matched twin; the same-rule-sibling path to `REPLICATED` not modelled
(it can only add badges). None of these can bring the no-edge rate near a conventional 5%.
