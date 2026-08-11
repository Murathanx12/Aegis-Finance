# NIGHT-10 — the MIRROR challenge (paper only)

**No trade. No lane seeded. No flag flipped. No `paper_nav` row written. No
order path touched.** This is a comparison, not an instruction.

Receipts: `docs/BUILD1/mirror_challenge.json`, `scripts/mirror_challenge.py`.

---

## The book as it stands

12 names, marked NAV **$39,500**, all 12 priced. **Cash: UNKNOWN** — Murat has
not supplied it, so every weight below is a share of marked equity, not of the
account. The book carries no `confirmed: true`, so this is a **simulation on an
unconfirmed book**.

**The QUBT fork is carried, not resolved.** The conviction decision log says 300
shares; `backend/config` says 200. That is **$893 of NAV**. Both are printed;
neither is adopted.

---

## What Optimus can actually say about the book

The held names are mostly *not* in the market funnel's candidate list — the
funnel screens for liquidity and profitability, and this book is small-cap
biotech and speculative growth. An earlier version of this run scored only the
overlap and reported "no view on your book", which was a **bug, not a finding**:
it had never looked. The holdings now run through the funnel's own stage-3
enrichment and are scored in **one cross-section** with the candidates, so the
z-scores mean the same thing on both sides.

| ticker | $bn | score | verdict | confidence | led by |
|---|---:|---:|---|---|---|
| **PRCH** | 1.75 | **+0.179** | **BUY** | MEDIUM | profitability_small |
| BHVN | 2.19 | 0.000 | NO_ACTION | NONE | — (no licensed evidence) |
| DKNG | 12.04 | −0.119 | HOLD | LOW | insider_opportunistic |
| HUBS | 10.77 | −0.119 | HOLD | LOW | insider_opportunistic |
| QUBT | 2.01 | −0.119 | HOLD | LOW | insider_opportunistic |
| AMSC | 1.50 | −0.346 | HOLD | MEDIUM | profitability_small |
| ABSI | 1.53 | −0.565 | HOLD | MEDIUM | profitability_small |
| SLDP | 0.54 | −0.614 | HOLD | MEDIUM | profitability_small |
| SOC | 0.95 | −0.967 | HOLD | LOW | profitability_small |
| NTLA | 1.68 | −1.393 | HOLD | MEDIUM | profitability_small |
| AARD | 0.17 | −1.424 | HOLD | LOW | profitability_small |
| KYTX | 0.48 | −1.685 | HOLD | MEDIUM | profitability_small |

**11 of 12 carry licensed evidence. One name — PRCH — is a BUY.**

### The caveat that matters most

Most of these names are **pre-revenue or early-revenue biotech and speculative
growth**, and the signal ranking them is `profitability_small` — gross profit
over assets. A company with no product revenue scores badly on gross
profitability by construction. **That is a category mismatch, not a verdict on
the thesis.** `profitability_small` was validated on the CRSP small segment as a
whole; nobody has measured it on pre-revenue biotech, where the thesis is a
binary clinical outcome the signal cannot see at all.

So: the negative scores on AARD, KYTX, NTLA, ABSI and SLDP say *"this engine's
one licensed small-cap picker has nothing good to say about these names"*. They
do **not** say the theses are wrong. The engine has no signal that can evaluate
a clinical-stage thesis, and it should not be read as though it does.

---

## The open-universe arm

Given the same capital and the full investable US universe, Optimus screened
5,324 names, carried 40 to candidacy, and **could not build a single portfolio**:
every archetype refused, because only two names cleared a positive ranking score.
See `NIGHT10_CAPITAL_FRONTIER.md` for the refusal table.

**So the honest answer to "what would Optimus buy instead?" is: almost nothing,
and it will not pretend otherwise.** Its one market-wide BUY tonight is CVLG
(Covenant Logistics, $0.84bn, MEDIUM confidence, led by profitability_small).

That is not a recommendation to sell the book and buy CVLG. It is the statement
that the engine's licensed evidence base is currently too thin to justify
replacing a 12-name book, and that any comparison claiming otherwise would be
comparing a real portfolio against an artefact of a 2-name evidence set.

---

## Proposed kill conditions — awaiting Murat

Five held names have **no kill condition on record**. None was invented from the
engine; these are proposals for Murat to accept, amend or reject. Every one
prints as `PROPOSED_AWAITING_MURAT` wherever it appears.

| ticker | proposed kill condition |
|---|---|
| ABSI | cash runway falls below 12 months, or a lead programme is discontinued without a named successor |
| AMSC | two consecutive quarters of declining grid-segment backlog, or largest-customer concentration exceeds 40% of revenue |
| HUBS | net revenue retention falls below 100% for two consecutive quarters |
| KYTX | a lead clinical programme misses its primary endpoint, or cash runway falls below 12 months |
| SLDP | a named OEM partnership lapses without replacement, or cash runway falls below 12 months |

---

## What Optimus cannot say about this book

* **Cash** — not supplied.
* **Cost bases** — 5 of 12 unknown, so no per-name P&L is computed and none is
  guessed.
* **`confirmed`** — absent, so every number here is a simulation.
* **Expected return** — NOT CALIBRATED for any name in any arm. The comparison
  is of *composition*, never of forecast return.
* **Whether the theses are right** — the engine has one small-cap picker and no
  clinical-outcome signal. On most of this book, it is the wrong instrument.
