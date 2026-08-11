# NIGHT-10 — analyst revisions: the delivery sweep that did not run, and why

The briefing made this the priority experiment: resolve why the two revision
constructions disagree in small caps, then sweep low-turnover delivery vehicles.

**Neither happened, and the reason is the finding.** The identification question
turned out to rest on a difference that is not distinguishable from zero, and
the instrument that was supposed to resolve it cannot resolve differences of
that size.

Full verdict: `Aegis module/docs/ANALYST_IDENT_1_VERDICT_2026-08-11.md`.
Receipts: `runs/ARENA1/ANALYST_IDENT_1/{results,power_audit_factory}.json`.

---

## 1. The identification question, and the gate that stopped it

ANALYST-IBES-1 left the small segment UNRESOLVED because two constructions of
one idea disagreed in sign:

| arm | construction | small, 1m, gross |
|---|---|---:|
| A2 `tgt_rev_breadth` | `(numup1m − numdown1m) / numest` | **+6.05 %/yr** |
| A3 `tgt_rev_3m` | Δ of the consensus target level over 3m | **−0.73 %/yr** |

The parent verdict wrote down its own successor hypothesis: `numup1m`/`numdown1m`
count analyst **actions**, while a change in the consensus mean mixes actions
with **coverage churn** — an analyst initiating at a high target moves the mean
with nobody having revised anything, and the contamination scales as 1/`numest`,
so it bites hardest where coverage is thin. That is small caps.

ANALYST-IDENT-1 registered that test with two gates in front of it.

| gate | result |
|---|---|
| **DATA_QUALITY** | **PASS** — `numest` is a clean integer count (non-integer share 0.000) with 52.2% mass at zero 3-month change, so "same count" can be read as "same analysts" |
| **POWER** | **FAIL** — the churn-free subsample retains 52.2% of name-months over 250 months (both floors cleared), but the realised MDE is **10.8 %/yr** against a registered target of 4.0 and a disputed gap of **6.8** |

Per the registered rule: **no arm ran, no number is quoted, small stays
UNRESOLVED.**

*A note on the gate itself.* The first implementation used an **assumed**
monthly dispersion rather than the realised one the pre-registration specified.
It also failed, at 12.8%/yr — but it was replaced with the registered method
before the verdict was taken. A gate stricter than its own registration
manufactures the verdict it reports.

---

## 2. The disagreement was never a disagreement

POWER_FAILED raised a question about the parent. Rebuilding all ten
ANALYST-IBES-1 arms through the parent's own Factory (8 of 10 reproduce their
published gross excess to **0.00 points**; the two `tgt_upside` arms do not and
their readings are **withheld**):

**The small-segment A2-vs-A3 difference, tested on the paired monthly series** —
which handles the 0.578 correlation between the two books exactly, rather than
assuming it away:

| | |
|---|---:|
| paired months | 249 |
| mean difference (A2 − A3) | **+3.70 %/yr** |
| standard error | **3.60 %/yr** |
| **t** | **1.03** |
| significant at 5% | **no** |

The parent adjudicated its registered prediction 5 ("A2 and A3 agree in sign")
by comparing two point estimates and reading their signs. **The difference it
was really about is one standard error from zero.**

Two underpowered estimates disagree in sign routinely. A decision rule that
reads that as refutation manufactures "unidentified object" verdicts out of
noise — and this one did.

---

## 3. Was the parent ever powered to see its own numbers?

| | count |
|---|---:|
| arms measured | 10 |
| reproducing their published number (gap ≤ 1.5 pts) | 8 |
| **significant at 5%** | **1** |
| **above their own 80%-power MDE** | **0** |

Not one arm reported an effect large enough for that design to have found it
reliably. This does not make the numbers wrong. It places the whole trial in the
region where significant findings systematically overstate their effects and
where a null and a real effect look alike.

---

## 4. So what is true about analyst revisions?

Stated as narrowly as the evidence allows:

* **Levels are dead.** Negative on three independent instruments, **gross**, so
  not a cost story. `analyst_target_upside_xs` stays PERVERSE/CLOSED, and the
  two unfaithful audit arms mean the levels result was **not re-measured here**
  and is untouched by any of this.
* **Revision breadth (A2) is the least-bad object in the family.** +6.05%/yr
  gross in small at 1m, t 2.23 — significant, but **below its own 7.6%/yr
  80%-power MDE**, which is exactly where the winner's curse lives.
* **The gross-to-net gap is the one prediction that held decisively.** A2 small
  monthly gives up **5.67 points** to costs at 10.2× turnover, against 1.85 for
  levels at 3.7×. The mechanism predicted in advance is the mechanism observed.
* **Δ-consensus (A3) is not identified**, and now is not known to *need*
  identifying, since it never measurably disagreed with A2.

**Nothing graduates.** `analyst_target_revision` stays HYPOTHESIS,
`allowed_in_pm` stays false — as the pre-registration required regardless of
outcome.

---

## 5. Why the delivery sweep was not run

The sweep would have tested revision persistence, acceleration, consensus
breadth, error-normalised magnitude, alignment with earnings revisions, price
non-reaction, monthly and quarterly clocks, minimum holding periods, and delayed
rebalance. Every one of those is an economically motivated variant and every one
deserves a run.

**On an instrument with a 7.6–12.3 %/yr detection threshold, that sweep produces
a list of numbers that cannot be told apart.** The turnover finding — 10.2× and
5.67 points of cost — already says the direct implementation is dead; a sweep of
delivery vehicles searching for a survivor in that noise band is best-of-N with
no denominator, which is the exact failure ARENA-1 was built to expose.

**The sweep is the right next experiment, after the instrument is fixed, not
before.** Running it tonight would have produced a night of numbers and no
knowledge.

## 6. What would change this

* **A higher-powered instrument** — longer window, more names per leg, or a
  panel estimator whose standard error is smaller than the effects sought.
  Everything else in this family is downstream of that.
* **The churn hypothesis remains open.** It was never tested. It is not worth
  reopening on this instrument at this power.
* The paired test uses **gross arithmetic** monthly excess while the parent's
  headline is a **geometric** CAGR difference. Different functionals; the t on
  the paired series is nonetheless the correct significance test for a
  difference.
