# ERRATUM — N9: the confirmation held out SECURITIES, not DATA

**Filed 2026-08-16**, after the review asked for N9's 20-day embargo leak to be
repaired and every downstream claim frozen until it was. The repair ran. It
changed almost nothing. Looking for its effect found something larger.

**Status of N9's headline (`lift 1.271, p = 0.015`, six confirmation
securities): WITHDRAWN as a transfer result.** Not because it was mis-computed
— it reproduces — but because the slice it was computed on does not support the
reading it was given.

---

## 1. The embargo leak was real and immaterial

`scripts.audit_temporal_lineage` measures it against the real NYSE calendar:
**80 leaking training dates**, reaching to 2016-02-01 (H=20) and 2016-03-30
(H=60). The training frame was sliced at `TRAIN_END` *after* `fwd_H` had been
computed on prices downloaded to 2026, so the last H training rows carried
labels built from the evaluation period.

Repaired by `research_gym.lineage`, which derives each row's `label_end_ts`
from the index and purges **per horizon**:

| | pre-repair | repaired |
|---|---|---|
| admissible train rows, H=20 | 12,828 | 12,768 (−60) |
| admissible train rows, H=60 | 12,828 | 12,648 (−180) |
| rules clearing TRAIN, H=20 | 582 | 603 |
| **confirmation median lift, H=20** | **1.271, p = 0.015** | **1.279, p = 0.015** |
| confirmation median lift, H=60 | 1.330, p = 0.075 | 1.326, p = 0.065 |

So the review's priority-zero repair is done, and the answer is that **the leak
did not carry N9's result**. Recording that plainly matters as much as
recording a leak that did: a defect found is not automatically a defect that
mattered, and treating every found defect as load-bearing is its own way of
being wrong.

## 2. What did carry it

Amendment 1 confirmed the frozen rule set on six securities *in neither prior
slice* — `DIA XLV XLI XLP XLU XLB` — over **1999–2026**. Different tickers. The
**same calendar**. Rules selected on SPY/XLF/XLE through 2015 were then scored
on other index ETFs through the same 2008, the same 2011, the same 2015.

Splitting that confirmation at the selection boundary, same securities, same
rules, same placebo, nothing else changed:

| confirmation slice | H=20 | H=60 |
|---|---|---|
| **1999–2015 — calendar-OVERLAPPING with selection** | **1.464, p = 0.010** | **1.437, p = 0.020** |
| full history, as registered | 1.279, p = 0.015 | 1.326, p = 0.065 |
| **2016+ — calendar-disjoint** | **0.765, p = 0.771** | **0.693, p = 0.806** |

The registered number is the average of a period where the set transfers and a
period where it does not, and the period where it does is the one that shares
its market states with the selection window. On calendar-disjoint data the
median lift is **below the placebo median** at both horizons.

### The power reading is checked, and it does not hold

§37: a kill is checked as hard as a pass. Three reasons this is not "the
shorter slice could not see it":

1. The disjoint slice scores **461** rules (H=20) against the overlapping
   slice's **527** — comparable, not a fraction.
2. The point estimates are on **opposite sides of 1.0** and the p-values on
   opposite sides of 0.5. An underpowered null sits near the placebo with a
   wide interval; this sits below it.
3. "2016+ has no tail structure to find" is refuted by N9's own foreign slice,
   which is also 2016+: `QQQ IWM XLK` gives **1.412, p = 0.040** at H=20.

That third point is the honest complication and it is not resolved: **on
calendar-disjoint data the set transfers on one group of three securities and
does not on another group of six.** Which is exactly what an effective
cross-section of ~1.4 (§58, `k/(1+(k−1)ρ̄)` at the ρ̄ these ETFs carry) predicts
you should be unable to distinguish. Six confirmation securities were never six
observations.

## 3. What this changes

* **N9 may not be cited as a confirmed transfer.** Its status is
  `TRANSFER_NOT_ESTABLISHED_CALENDAR_CONFOUNDED`.
* **The 1.271 figure is withdrawn** from every downstream sentence. N9's
  contribution to the "the precursor library is dead" conclusion is unchanged
  and arguably strengthened — a route that looked like the one positive is now
  a fourth negative.
* **N9B** measured a *difference* between two vocabularies on this same slice.
  A difference between two things measured on a confounded slice inherits the
  confound; its "the vocabulary is not the ceiling" conclusion is now
  `INHERITS_PARENT_CONFOUND` and needs re-running on calendar-disjoint data
  before it is quoted.
* **N20 and N21** used the frozen rule set, not N9's confirmation number. N21
  froze and re-derived the rules from train only and never downloaded past the
  cutoff — `audit_temporal_lineage` scores it CLEAN. Their conclusions do not
  depend on the withdrawn figure.

## 4. The generalisable part

> **Holding out securities is not holding out data when the securities
> co-move.** A confirmation slice's identity is universe × period × outcome ×
> information cutoff; changing only the first coordinate changes the least
> informative one.

`research_gym.slice_register` already stores all four coordinates and already
detects overlap on period. What it did not do — and now does not need to,
because this is now a lint at registration — is require a trial to *say* which
of them it is actually varying.

## 5. Artifacts

| | |
|---|---|
| pre-repair (immutable) | `backend/data/optimus/research_gym/n9_mine_the_85.json` |
| repaired, purged | `n9_repaired_purged.json` |
| repaired + period split | `n9_repaired_split.json` |
| lineage audit, all designs | `temporal_lineage_audit.json` |

The pre-repair artifact is not overwritten; `n9_mine_the_85.py` now **refuses**
to write over an existing file. A run made under a different lineage is
evidence about the process that produced it.
