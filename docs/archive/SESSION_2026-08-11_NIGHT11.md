# NIGHT-11 — the referee got fixed, and the player got its first licensed evidence

**2026-08-11.** Three external reviews arrived saying the same thing: the
research machinery is a 9/10 truth machine bolted to a 5/10 investment brain, and
the next work should go to the player rather than the referee. They were right
about the diagnosis. They were wrong about two of the prescriptions, and this
session measured both rather than adopting them.

Commits: `e88c6b1` `26d1546` `466671f` (Aegis module) · `c34ae31` (aegis-finance).

---

## 1. What was fixed

### P0-A — the MDE and the t-stat now come from the same standard error

Real, exactly as reported. `_power_block` divided by `sigma/sqrt(n)` while every
t-statistic beside it was Newey-West. The mechanism was mundane:
`newey_west_tstat()` returned only `t`, never its SE, so any caller wanting an
MDE had to re-derive one and every caller re-derived the IID one.

Re-audited the ten ANALYST-IBES-1 arms with the estimator the inference already
used (`scripts/audit_power_hac.py`, never reads a mean, accrues 0):

| | published | corrected |
|---|---|---|
| detection range | 6.3–19.9 %/yr | **6.47–24.82 %/yr** |
| arms above their own MDE | 0 of 10 | **0 of 10** |

HAC/IID runs 0.72–1.24. **No verdict moves and the finding gets stronger** — the
same direction as the null-bar correction that preceded it.

One judgment call: significance uses the HAC SE; the **MDE uses
`max(HAC, IID)`**. When the Bartlett sum comes out net-negative the HAC SE falls
below IID (3 of the 10 arms), and adopting it there would buy power out of
estimation noise in the autocovariances. An MDE licenses a null, so understating
it overstates the kill.

### P0-B — the shadow register was about to mislabel a forward record

`shadow_portfolios.yaml` still said the false-discovery bar was +4.87 %/yr and
that two challengers had cleared it. Both halves wrong together: +4.87 is the
real-data equal-weight CONTROL genome — the same measurement separately published
as "4th of 384" — doing duty as the threshold its own challengers were judged
against. The measured bar is **+6.90 %/yr** and **0 of 384 clear it**.

This mattered because nothing is seeded yet. The register is the label the
forward record would have been born with, and the two "above the bar" tags would
have ridden for the 24 months before anyone is allowed to speak.

Four tests tie the file to its receipt, **verified to fail when reverted to
4.87** rather than passing vacuously. The root defect was not a bad calculation;
it was a headline number with no link to the run that produced it.

---

## 2. What was built — Layer 1

`aegis_brain/pf/information.py`. Fama-MacBeth over the full eligible
cross-section, one slope per month, Newey-West over the slopes — date-clustering
done the oldest way, so within-month correlation is handled exactly rather than
assumed away. ~900,000 stock-months instead of 252 portfolio-months.

Three-valued verdicts, because "we could not see it" and "it is not there" had
been the same record for 195 experiments. A result carries `licenses` stating
that it permits a Layer-2 test and no money claim.

**Calibrated before it was allowed to issue a verdict**, with the plant verified
present in every synthetic world as a paired difference against the null world of
the same seed. ARENA-1's generator cancelled its own plant and every known-answer
test it ran was silently executed on a null world; that is not repeated here.

---

## 3. Where the reviews were wrong

### The 4–10x power gain does not exist. It is 1.63x, and only in small caps.

All three reviews asserted that estimating on the panel would collapse the
standard error. Written as a test assertion (`ratio > 2.0`) it **failed at 1.31**.
Beta dispersion → 1.30. Sector factors → 1.29. Correlated within-basket
residuals → 1.46–1.52. The failing assertion is kept in the test file with the
number it failed at.

On the real panel, same signals and months: **0.98x to 2.11x, median 1.63x** —
1.45–2.11x in small caps and **0.98x / 0.99x in large/mid, i.e. none at all.**
Mechanically sensible: in large caps a top-50 book already IS most of the
investable cross-section, so there is no breadth left to recover.

An 8 %/yr MDE becomes ~5 %/yr. That reopens some UNRESOLVED corpses. It does not
make the standard design adequate, and the rescue queue has been rescoped
accordingly.

### The MDE prescription conflated two quantities

Reviewer 2 prescribed `MDE_HAC = 2.8 x SE_HAC` and read detection at that
threshold as 80% power. An MDE is *defined* against a 5% significance test: at a
true effect of 2.8 SE the rule "reject when |t| >= 1.96" fires 80% of the time,
but the rule "reject when |effect| >= MDE" fires ~50%. Measured at 58% just above
the MDE. The stricter rule is kept — it is the winner's-curse guard NIGHT-10
argued for — and both rates are now reported so the label cannot be misread.

---

## 4. REVINFO-1 — the first licensed Layer-1 evidence this programme has

Pre-registered, corpse-linted PASS against 306 priors, holdout unread, accrues 0.
Full table in `docs/REVINFO_1_VERDICT_2026-08-11.md` (Aegis module).

**Three constructions of the revision idea carry cross-sectional information in
SMALL caps**, and two hold it to six months. Best arm `tgt_rev_breadth` small:
**+9.36 %/yr at t 4.87** against its own MDE of 5.76, decaying +7.32 / +5.45 /
+2.95 at h=3/6/12. `eps_rev_breadth` — never tested at Layer 1 before — is the
most persistent: +6.64 / +5.54 / +4.66 at t 5.10 / 4.71 / 3.65.

7 of 32 INFORMATION_PRESENT, 21 UNRESOLVED, 4 NO_INFORMATION. **Not one large-cap
arm clears its MDE at any horizon.**

The decay is monotone in every arm, but under CANON §18 that is a claim about a
DIFFERENCE and has NOT been tested as one. **No half-life number may be quoted
yet.**

### The control passed on sign and failed on magnitude — the real finding

`tgt_upside` is PERVERSE/CLOSED at −16.70 %/yr through a top-50 book. Here it
reads **−0.16 %/yr, t −0.03**. The gate passes; the reproduction does not. The
decile spreads explain it:

| h=1, small | breadth | decile | incumbent top-50 |
|---|---:|---:|---:|
| `tgt_rev_breadth` | +9.36 | **+13.21** (t 6.04) | +6.05 |
| `tgt_upside` | −0.16 | **+1.18** (t 0.19) | **−16.70** |

The revision signals get STRONGER as the instrument concentrates — their
information is broad. `tgt_upside` is flat at the decile level and only turns
catastrophic in the extreme top ~3%, where lottery-stock junk concentrates.

⇒ **a corpse killed by a concentrated top-50 book is not automatically
re-testable by a cross-sectional instrument.** A rescue queue built only on this
instrument would exonerate every tail-perverse signal by averaging its perversity
away. Each rescue now carries both arms.

---

## 5. The instrument's own verdict rule was wrong, and the data caught it

`NO_INFORMATION` was issued whenever an effect missed its MDE and the MDE looked
small. Run against real data it labelled arms at **t = 2.21** and **t = 2.72**
"evidence of absence". An effect significantly different from zero cannot be
evidence that there is no effect.

It is now a one-sided equivalence bound: the whole 95% interval must lie inside
the region already declared not worth having, and the arm must not be
significant. Re-running the full grid changed **7 of 32 verdicts** — **5 false
kills prevented, 2 kills correctly ISSUED**. It moved in both directions, which
is the evidence that it is more correct rather than merely more permissive.

---

## 6. What is NOT claimed

* No money claim. The spread is dollar-neutral and unconstrained; Round 16
  measured 88–99.9% of a comparable spread in the short leg a long-only book
  cannot hold. **The short-leg decomposition is the next thing that could kill
  this whole family regardless of Layer 1.**
* Nothing overturns ANALYST-IBES-1. Different question, different instrument.
* No graveyard corpse is reopened. Reopening needs its own pre-registration.
* No position, no sizing, no registry grade changed.

---

## 7. Next, in order

1. The half-life as a paired difference (CANON §18) — no half-life claim until.
2. **The short-leg decomposition.** Highest-information next test: it can kill
   the family cheaply.
3. Layer 2 — the decision boundary, `E[r_entrant − r_incumbent]`. Accrues.
4. The rescue queue with both a cross-sectional and a tail-concentrated arm.
5. Everything in `docs/ROADMAP_OPTIMUS_BRAIN_NIGHT11.md` — belief state,
   prediction ledger, category routing, LLM specialists, seeding the books.

## 8. Still owed by Murat

cash · QUBT 300 vs 200 · rulings on five kill conditions · `confirmed: true` ·
a real `ANTHROPIC_API_KEY` (still EMPTY — every LLM finding to date is a finding
about DeepSeek) · seeding the shadow books · the graceful-degradation ruling.
