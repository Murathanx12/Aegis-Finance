# DECISION — WRDS receipt policy (two-tier receipts)

**Raised** 2026-08-20 by external review, before the discovery run
generated the artifacts it concerns. **Status: PROPOSED — Murat's call.**
The run below proceeds under the proposed policy because the
conservative branch (withhold) is the safe default and is reversible;
publishing is not.

## The problem

Aegis's receipts culture assumes artifacts are publishable: every trial
writes a JSON receipt, receipts are committed, and the repo is MIT
licensed. That assumption held while every input was free data.

It does not hold for WRDS. The HKU entitlement is a licence to *use*
CRSP, Compustat, IBES, OptionMetrics, TAQ and Thomson 13F for research;
it is not a licence to redistribute them. Redistribution is not limited
to raw extracts — a derived per-security time series that lets a third
party reconstruct the source is redistribution too, and the 13F-derived
holdings panels are close enough to the source to be treated as such.

So a discovery run now produces artifacts that legally cannot be
published the way everything before them was. Deciding this *after*
generating eight hours of them would leave two bad options: breach the
licence, or silently break the audit chain by withholding receipts with
no record that they exist. The second is worse, because it is invisible.

## The policy

**Two-tier receipts.**

**Tier PUBLIC — committed to the repo, as today.**
- Code, configuration, and the declared grammar.
- Config and data **hashes** (SHA-256 of the private artifact).
- Aggregate statistics that cannot reconstruct the source: counts, rank
  ICs, QLIKE and other losses, coefficients, p-values, MDEs, CIs,
  verdicts, effective dimensions, cluster counts.
- Metadata about coverage: row counts, date windows, universe sizes,
  drop accounting.
- Everything a reader needs to *check the reasoning* and *re-run the
  code given their own entitlement*.

**Tier PRIVATE — local artifact store, gitignored, hash published.**
- Any per-security or per-manager time series derived from WRDS.
- Panels, feature matrices, holdings, per-book holdings paths.
- Model weights trained directly on WRDS panels **when the weights are
  large relative to the training data** (a memorisation risk); ordinary
  low-parameter models trained on hundreds of thousands of rows are
  PUBLIC.

**The rule that keeps the chain honest:** a withheld artifact is still
*declared*. Every private artifact gets a public stub recording its
name, its SHA-256, its row count, its date window, its schema, and the
sentence "withheld under the WRDS licence". A reader can then tell the
difference between an artifact that does not exist and one they cannot
see — which is the entire point of a receipts culture.

## What this does NOT license

- It does not permit publishing a WRDS-derived series because it "looks
  aggregated". If a third party could invert it to recover per-security
  values, it is Tier PRIVATE.
- It does not weaken reproducibility claims. A result that can only be
  reproduced by someone with the same entitlement must SAY SO in its
  receipt, in the `reproducibility` field, naming the entitlement
  required. Claiming open reproducibility on entitled data is a false
  claim about the evidence, and the programme treats those as findings.
- It does not apply to JKP factor returns, which are free with citation,
  or to Kenneth French data. Those stay Tier PUBLIC and should be
  preferred for any result intended for the open-source tool.

## Consequence for the public tool

The public Aegis tool must not depend on a WRDS-only artifact for any
user-facing number. Where a finding was established on WRDS data, the
shipped tool either (a) reproduces it on free data and reports the
degradation honestly, or (b) states that the finding is research-only
and does not drive the tool. This is a product boundary, not just a
legal one, and it should be recorded on the roadmap.

## Implementation

- `.gitignore` already excludes `backend/data/optimus/wrds/*.parquet`;
  metas are committed. Extend the same split to any new derived panel.
- Receipt writers gain a `reproducibility` field:
  `{"tier": "public"|"private", "entitlement_required": [...],
    "private_artifacts": [{"name":..., "sha256":..., "rows":...}]}`.
- The stub-on-withhold rule is the part that needs enforcing in code;
  until it is, it is a review checklist item.

## Open question for Murat

HKU's WRDS terms may be more specific than the general case assumed
here (some institutions permit publishing derived series below a
granularity threshold). If the actual terms are available, they govern
and this document should be replaced by a citation to them — the
programme's own standing rule is that **the catalogue is not
entitlement**, and by the same logic a reasonable assumption about a
licence is not the licence.
