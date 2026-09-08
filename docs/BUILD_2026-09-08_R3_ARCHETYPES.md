# BUILD 2026-09-08 — lane U: EVENT ARCHETYPES → TYPED HYPOTHESES → GRADED

**Lane:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` block U (U1 / U2 / U3).
**Licence:** `PRODUCT_EXPERIMENT`. Places nothing, sizes nothing, orders nothing.
**LLM spend:** **$0.00.** Embeddings from NVIDIA NIM `nemotron-3-embed-1b`
(free), cluster labels from NVIDIA NIM (free). The DeepSeek balance was not
touched.

**RESULT IMPROVEMENT: NONE.** One of ten hypotheses survives Holm against the
declared control and it is **not an archetype effect** — it is the corpus-wide
event/non-event difference that all ten inherit (§4.5). Against the control that
isolates the archetype, **zero of ten survive**. What this session shipped is the
*apparatus*, its known-answer proof — including one instructive failure of that
proof — and a bounded negative result.

---

## 0. The one-paragraph version

U3 was built first and it passes — twice over, and it failed once in between,
which is the part worth reading. Offline, a synthetic family planted at 3× its
own MDE is clustered, emitted and recovered in **16 of 16 seeds** while a
zero-drift null reads noise in **15 of 16** (power 1.00, size 0.06 against a
nominal 0.05). On the real corpus with the NVIDIA embedder the gate **first
failed**, correctly, because the plant was wrong for the embedder; with the plant
fixed it passes end to end — planted family recovered at F1 **0.986** and graded
at Holm p **5.4e-9**, null family recovered at F1 **0.922** and reading t 0.58.

Then the real answer. Twenty archetypes, ten graded at family = 10, and the
declared primary statistic keeps **one**: `A18`, the takeover-chatter archetype,
at −0.809 pp over five sessions, t −3.02, Holm-adjusted **0.0484**. It does not
survive contact with the number printed beside it: the **corpus-level**
event-minus-control difference is **−0.848 pp at t −3.03**, statistically the
same. `A18` did not beat the other archetypes; it inherited an effect all of them
share. The post-hoc test that separates the two — archetype against *other
events* rather than against non-event days — returns **zero of ten under Holm and
zero under BH-FDR, best adjusted p 0.544**, with not one archetype powered for
its own observed effect.

**So: the machinery works, the archetypes are only half stable (ARI 0.54), and
the archetype partition carries no incremental information over "an event
happened" on this tape.** The tape is the other finding: of 993,005 rows in
`event_table_v1` (2015-2026), exactly **21,841** carry both a headline an
embedder can read and a CRSP permno a return can be computed for — 91 names,
2015-2018, mega-cap tech by construction. A positive result here would have been
a regime finding about those names in those years, and the lane could not have
produced a `RESEARCH_CLAIM` even if the numbers had come out.

---

## 1. U3 FIRST — the known-answer gate

> A discovery pipeline that has never been shown to find a planted answer is not
> evidence of anything.

`backend/services/archetypes.py::known_answer` plants two synthetic event
families into a corpus and runs the *whole* pipeline over the result — embed,
cluster, recover, emit, grade, correct:

| family | n | planted drift | must end as |
|---|---|---|---|
| `PLANTED` | 400 | 3 × its own cluster MDE | clustered **and** separated after Holm |
| `NULLFAM` | 400 | 0.0 | clustered **and** reading noise |

Four checks, all of which must hold:

1. `planted_family_clustered` — some union of ≥80%-pure clusters holds ≥80% of it;
2. **`null_family_clustered`** — the same for the null. This is the check that is
   easy to omit and the one that makes the gate mean anything: a pipeline that
   cannot see the null family at all would pass 1, 3 and 4 by accident;
3. `planted_separated_after_holm` — Holm-adjusted p ≤ 0.05 over the declared
   family **and** the observed effect clears its own MDE;
4. `null_reads_noise` — the null does not survive the BH-FDR *screen*.

### 1.1 The operating characteristic (offline, deterministic embedder)

| planted drift | gate passes | reading |
|---|---|---|
| 3 × cluster MDE (2.04 pp/event) | **16 / 16** | power 1.00 |
| 0.0 | **1 / 16** | size 0.0625 vs nominal 0.05 |

Pinned by `backend/tests/test_u_archetypes.py`
(`test_u3_has_power_at_three_times_the_cluster_mde`, ≥7/8; and
`test_u3_on_a_corpus_with_nothing_planted_passes_at_about_the_nominal_rate`,
≤2/8). Both run in the fast, network-blocked suite.

### 1.2 What went wrong first, and why it is in the file

**The plant was sized against the wrong MDE.** The first version computed the
drift as a multiple of the *corpus's* block-mean sd. But the planted cluster has
~11 events per block where the corpus has ~33, so its block sd is ~1.9× larger
and its true MDE ~1.9× higher. Planted at "3× MDE" it was really at 1.6× its own,
and a −3.05 SE noise draw sank it. Fixed by `archetypes.plant_drift()`, which
sizes against the cluster's own `(z_α + z_power) · σ_event / √n_events`. The
wrong denominator is recorded in the docstring so it is not re-derived.

**The negative control was one realisation.** The first zero-drift test asserted
`not passed` on a single seed and failed — because that seed's noise mean landed
at −3.05 SE and a family with a drift of exactly zero read as separated. A
known-answer harness whose negative control is one draw is measuring the draw.
It is now eight seeds with a bound on the pass count.

**The plant did not match the embedder — and the gate caught it.** Run 01 on the
real corpus with `nemotron-3-embed-1b` returned
`planted_family_clustered: False, null_family_clustered: False`, and the script
stopped and graded nothing. The receipt is kept as
`U_archetypes_nim_run01_RARE_TOKEN_PLANT_FAILED.json`, and the diagnosis is in
it: the embedder had put **both** planted families into **one cluster of exactly
800 at purity 0.50**, with no real headline joining it. It had separated
*register* — "this is not a financial headline" — and was blind to *which* pile
of rare words a row came from, because to a language model two piles of
unrelated rare tokens are the same thing.

That is a fact about the plant, not about the pipeline, and it is the single
most useful thing this lane learned:

> **The plant must match the embedder's notion of similarity.** A hashing
> embedder sees tokens, so it gets two rare vocabularies. A language model sees
> meaning, so it gets realistic headlines from two *semantically distinct event
> families* (a product-safety recall family and an executive-appointment
> family), built from shared filler so the only thing separating them is what
> they mean.

`--plant {templates,tokens}` selects the mode and defaults per embedder; the mode
that ran is stamped on the receipt. The offline CI gate keeps the token plant
with the hashing embedder, where its power is 16/16.

**The recovery criterion was measuring `k`.** The first criterion was "the union
of clusters that are individually ≥80% pure". At a fine `k` a perfectly
concentrated 400-member family needs several clusters, none of which need be 80%
pure, so the criterion failed families that were in fact fully recovered — it was
a statement about the grid. It is now the standard **best cluster-matching F1**
over clusters added greedily in descending precision, with the per-cluster table
printed beside it so a reader can see which is doing the work. The receipt also
carries `recoverability_arithmetic` — the planted family's share of the corpus
against the mean cluster size — because a family smaller than the finest cluster
`k` can produce is unrecoverable by arithmetic, whatever the embedder does.

### 1.3 U3 on the real frame

The same gate is run inside `scripts/u_archetypes_run.py` against the real event
frame — real headlines, real CRSP returns, real market and beta legs — with the
two families planted into it, before anything real is graded. **If U3 does not
pass, the script stops and grades nothing** (`--continue-on-u3-fail` exists only
to diagnose).

### 1.4 U3 on the real corpus — **PASSED**

Run 03, `U_archetypes_nim.json`, `nemotron-3-embed-1b`, template plant, at the
`k = 20` the pipeline chose on the real corpus with the plant unseen:

| check | result |
|---|---|
| `planted_family_clustered` | **True** — best cluster-matching F1 **0.986** (purity 0.973, recall 1.000, one cluster of 411) |
| `null_family_clustered` | **True** — F1 **0.922** (purity 0.855, recall 1.000, one cluster of 468) |
| `planted_separated_after_holm` | **True** — +2.630 pp over 5 days, block t **8.31**, MDE 0.886 pp, Holm-adjusted p **5.4e-9** |
| `null_reads_noise` | **True** — +0.153 pp, block t **0.58**, p 0.56; BH-FDR keeps only `planted` |

The drift was planted at 3 × the planted cluster's own MDE (2.472 pp/event on an
event sd of 5.88%), and the realised draw landed at +0.53 SE of target
(2.628 pp realised against 2.472 pp target) — reported, so a near-miss would be
readable rather than mysterious.

**So the pipeline finds a planted archetype end to end on the real tape, and
declines a planted null on the same tape.** Everything below is interpretable.

---

## 2. U1 — the archetypes

`k` is chosen on the real corpus by silhouette over a **declared** grid, before
the U3 plant is introduced, and every `k` looked at is reported because every one
of them is a cell charged to the search (invariant 16).

| k | silhouette | smallest cluster | largest cluster |
|---|---|---|---|
| 6 | 0.0827 | 1,488 | 5,253 |
| 8 | 0.0699 | 1,196 | 5,138 |
| 10 | 0.0691 | 753 | 4,159 |
| 12 | 0.0912 | 958 | 3,337 |
| 16 | 0.1049 | 690 | 2,545 |
| 20 | 0.1114 | 223 | 2,099 |
| 24 | 0.1078 | 223 | 1,633 |

**Chosen k = 20, silhouette 0.1114.**

### 2.1 Stability — the number that decides whether these are archetypes at all

> A clustering that changes completely with the seed is not an archetype set.

Five fits, each on a fresh 80% resample with a fresh seed, compared pairwise on
the rows they share:

| statistic | value |
|---|---|
| mean adjusted Rand over 10 pairs | **0.540** |
| worst pair | 0.488 |
| seeds | [1, 2, 3, 4, 5] · subsample 0.8 |

**Read this honestly: ARI 0.54 is partial stability, not an archetype set.**
About half the pairwise assignment structure survives a reseed-and-resample. The
large, vocabulary-distinct clusters (options-flow alerts, semiconductor
supply-chain, takeover chatter) are stable; the boundaries between the several
"general market movement" clusters are not. A silhouette of 0.11 says the same
thing from the other side: financial headlines do not form well-separated
regions in this embedding — they form a continuum with a few dense spots.

That is a finding about the corpus and the embedder, and it caps what any
per-archetype result can mean: a hypothesis attached to a cluster whose
membership moves under a reseed is a hypothesis about a fuzzy set.

### 2.2 Cluster sizes at k = 20

{"0": 679, "1": 1060, "2": 1089, "3": 778, "4": 295, "5": 1737, "6": 717, "7": 1031, "8": 223, "9": 922, "10": 1717, "11": 1733, "12": 735, "13": 881, "14": 1476, "15": 1288, "16": 602, "17": 2049, "18": 2099, "19": 730}

Smallest 223, largest 2,099, mean 1,092.

### 2.3 The labels are DESCRIPTIONS, and most of them refused

Each cluster was labelled **once** by a free NVIDIA NIM model
(`nemotron-3.5-lightning-30b-a3b`, $0.00) from member titles and over-represented
terms only — it never saw a return. It mostly failed, and the failure is
recorded rather than papered over: **the free reasoning models emit their chain
of thought and spend the whole token budget on it**, so at 600 tokens `0 of 20`
replies reached the requested three lines and at 1500 tokens with an explicit
"do not think out loud" instruction most still did not. `parse_label_reply`
anchors on the direction token and returns `None` rather than the model's first
line — which would have been the word "Here's".

Where the model refused, the **mechanical top-terms label stands**, and
`label_source` says which happened for every cluster. Nothing downstream reads
a label: the grading sees only the MEMBERS. This is a finding for the L
(free-inference) lane, not a blocker for this one.

---

## 3. U2 — the typed hypotheses and the corpse route

### 3.1 The ten emitted hypotheses

Twenty archetypes were emitted and **none was refused by the corpse route**, so
the ten graded are the ten largest by the rank rule fixed before grading. Labels
are the **mechanical top-terms** descriptions — the free model refused on
nineteen of twenty (§2.3).

| archetype | label (description, not evidence) | precursor (observable BEFOREHAND) | direction | horizon | family | members |
|---|---|---|---|---|---|---|
| `A18` | street's/chatter/believes/takeover | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 2,099 |
| `A17` | disclosed/terms/contract/kratos | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 2,049 |
| `A05` | adj/eps/gaap/est | `earnings_surprise_sue` + `days_since_public<=1` | TWO_SIDED | 5d | events/earnings | 1,737 |
| `A11` | peek/futures/preview/economic | `earnings_surprise_sue` + `days_since_public<=1` | TWO_SIDED | 5d | events/earnings | 1,733 |
| `A10` | bears/barron's/jim/cramer | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 1,717 |
| `A14` | crowd/vetr/unusual/options | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 1,476 |
| `A15` | nordstrom/penney/department/store | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 1,288 |
| `A02` | rallied/hitting/then/three | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 1,089 |
| `A01` | dramexchange/nand/ryzen/gpu | `event_text_archetype` + `days_since_public<=1` | TWO_SIDED | 5d | events/other | 1,060 |
| `A07` | maintains/rating/coverage/initiates | `analyst_target_upside` + `days_since_public<=1` | TWO_SIDED | 5d | analyst | 1,031 |

Every precursor is the pair *(this event is in archetype X, and it has been
public for at most one day)*. Entry is the close of the first trading day
**strictly after** `observed_at_utc`, so **none of the ten is buying the reaction
it claims to predict** — the day-0 move belongs to the session before the
position exists. That convention was worth 92.5% of a headline number in the
sibling event-family lane (+5.54% on a day-0 close entry against +0.41%
PIT-safe), which is why it is stamped on the receipt rather than assumed.

### 3.2 What a hypothesis is here

Each archetype emits one `TypedHypothesis` whose every field is fixed **before**
any return is computed:

```
precursor   {"all": [{"feature": <family feature>, "op": "in_archetype",
                      "value": <archetype id>},
                     {"feature": "days_since_public", "op": "<=", "value": 1}]}
direction   LONG | SHORT | TWO_SIDED  — declared by the free model from member
            TITLES ONLY; it never saw a return. The test is two-sided regardless:
            the declaration buys no multiplicity relief.
horizon     5 trading days for all ten. One horizon, declared up front, so there
            is no horizon search to charge for. {1, 21} are EXPLORATORY and are
            screened separately, outside the family.
family      assigned MECHANICALLY from a fixed lexicon, not by the model
members     the event ids
```

**The Micron test.** The precursor is decidable from the event's own text at the
moment it becomes public, and entry is the close of the first trading day
*strictly after* `observed_at_utc`. Nothing in the precursor names a forward
return; `test_the_precursor_is_observable_beforehand_and_names_no_return` pins it.

### 3.3 The corpse register is DERIVED, not copied

`load_corpses()` builds the register from `backend/data/signal_registry.yaml`, so
it cannot drift from the registry. The only hand-written part is the map from a
signal id to the FEATURE its rule keys on — the shared vocabulary without which
a "mechanistic comparator" cannot collide with anything and is decorative.

Built this run: **14 corpses from 14 `CLOSED` rows in the registry**, of which
**11 block** (`REFUTED_IN_SCOPE`) and 3 block nothing
(`NOT_DETECTABLE_IN_SCOPE`). `closed_signals_without_a_feature_map` is empty —
every closed signal is mapped, so no corpse was skipped silently.

`REJECTED` and `PERVERSE` are powered evidence against the rule and become
`REFUTED_IN_SCOPE`, which closes. **`SHELF` does not**: "IC clears, the net book
does not" is an absence of a demonstrated book, not powered evidence against the
mechanism, so those rows land in `corpses_that_block_nothing` — named, and
blocking nothing. That distinction is `Corpse.blocks_anything`, and it is why 195
old kills stopped gate-keeping.

### 3.4 Routing, and that it bites

`route_through_corpses` calls `research_gym.scope.corpse_check` — the mechanistic
comparator — **not** `research_daemon.assert_distinct_from_corpses`, which counts
the words in a sentence. Three unit tests pin that it actually bites:

* an exact re-run of a closed rule → `BLOCKED`, corpse named;
* a mechanistically distinct descendant with the same action pair →
  `ALLOWED_WITH_PARENT_CONTROL`, `parent_control_required = True`;
* a `SHELF` row → admitted, and the shelved signal is still *named* in
  `corpses_that_block_nothing`.

One thing the comparator does badly and the receipt now says so: `corpse_check`
returns exactly one `parent` (`parents[0]`), and which one that is depends on
register ordering. `route_through_corpses` therefore reports
`action_pair_corpses` — the full list of closed mechanisms sharing the action
pair — beside it, so "the parent" reads as an ordering rather than a judgement.

All twenty archetypes routed cleanly and **none was refused**:

| outcome | count |
|---|---|
| `ALLOWED_WITH_PARENT_CONTROL` | **20** |
| `RESURRECTION_TAX` | 0 |
| `BLOCKED` | 0 |

Every one carries `parent_control_required = True`, and the parent named by
`corpse_check` is `accruals` for all twenty — which is exactly the ordering
artefact above warns about, since **ten** closed mechanisms share the action pair
(`long_top_quintile_equal_weight` / `hold_market`) and `accruals` is merely first
alphabetically. The full list is on every route as `action_pair_corpses`:

`accruals`, `analyst_target_upside_xs`, `fda_approval_monthly`,
`inst_ownership_level_13f`, `llm_stock_selection`, `momentum_12_1`,
`momentum_spillover`, `options_ranking_raw`, `reversal_dip`, `value_btm`.

Three shelved signals are **named and block nothing**, as designed:
`earnings_surprise_monthly`, `issuance_payout`, `short_interest_level`. That
`earnings_surprise_monthly` (PEAD at monthly resolution, IC t −2.6, inverted) is
named but not blocking beside the two `events/earnings` archetypes is the
comparator behaving correctly: a shelved monthly construction does not close a
5-day event-time question, and pretending it did would be the over-closing this
programme keeps having to undo.

**What the router did NOT do.** Nothing was blocked, so on this corpus the gate
demonstrated only its permissive branch. The blocking branches are exercised by
unit test, not by this run
(`test_an_exact_rerun_of_a_closed_rule_is_blocked_and_names_the_corpse`).

---

## 4. The alpha ruler, and the ten graded hypotheses

### 4.1 How a hypothesis is graded

| discipline | how it is honoured here |
|---|---|
| beta printed first | `beta_mean_pre_event` from `beta_panel.beta_pre`, last value ≤ entry |
| absolute beside relative | `raw_mean_pp` and `mkt_mean_pp` printed beside `ar_mean_pp` |
| **name-days are not periods** | one observation per **calendar month**; `n_effective` = date blocks |
| EW vs VW | both block series computed; a sign disagreement is stamped `EW_VW_DISAGREE` |
| tail before mean | top-1% share of the summed AR, plus the one-block jackknife on t |
| matched control | same NAME, same MONTH, a session with no event — the "without the event" arm |
| three eras | 2015H1-2016H1 / 2016H2-2017H1 / 2017H2-2018H2, **never pooled** |
| MDE and power BEFORE confirmation | `mde_pp` and `powered_for_observed_effect` on every row |
| screen vs export | BH-FDR to screen, **Holm to export**, both printed, family = 10 |

Abnormal return is the market model with zero alpha, `r − β·r_mkt`, over 5
trading days from the first close strictly after the row became public. Market is
the pinned Ken French daily `Mkt-RF + RF`.

### 4.2 The corpus-level number that has to be read FIRST

Before any archetype: **across all 21,841 events**, entering at the close of the
first trading day strictly after the headline and holding 5 sessions, against the
**same names in the same months on a day with no event**:

| arm | mean difference | block t | MDE | powered | p |
|---|---|---|---|---|---|
| abnormal return (β-adjusted) | **−0.848 pp** | **−3.03** | 0.784 pp | yes | 0.0044 |
| RAW return (no β at all) | −0.681 pp | −2.74 | 0.695 pp | no | 0.0093 |

Event-arm β 1.272 vs control-arm β 1.278 — so this is **not** a beta
mismatch between the arms, and it survives dropping the beta adjustment
entirely. Market leg over the event windows +0.216 pp against +0.187 pp over the
control windows.

**Every archetype inherits this.** The ten negative differences below are not ten
findings; they are one corpus fact seen ten times, and a family correction over
ten treats them as far more independent than they are.

### 4.3 The ten, graded — the declared primary statistic

Ranked by archetype size (the rule fixed before grading). `EMC` = event minus
matched control, paired by block. Holm is over **family = 10**.

| id | β | raw pp | mkt pp | AR pp | t(EW) | t(VW) | **EMC pp** | **t** | EMC raw pp | MDE pp | powered | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `A18` | 1.29 | -0.108 | +0.241 | -0.421 | -1.52 | -1.76 | **-0.809** | **-3.02** | -0.817 | 0.750 | yes | 0.0048 | 0.0484 |
| `A17` | 1.30 | -0.031 | +0.219 | -0.330 | -1.05 | -2.09 | **-0.598** | **-2.47** | -0.593 | 0.678 | no | 0.0187 | 0.1683 |
| `A05` | 1.19 | +0.179 | +0.177 | -0.066 | -0.24 | -0.16 | **-0.432** | **-1.49** | -0.503 | 0.815 | no | 0.1467 | 1.0000 |
| `A11` | 1.25 | +0.541 | +0.213 | +0.231 | +0.99 | +0.02 | **-0.115** | **-0.48** | -0.123 | 0.673 | no | 0.6361 | 1.0000 |
| `A10` | 1.21 | +0.433 | +0.210 | +0.131 | +0.44 | +0.83 | **-0.742** | **-2.18** | -0.569 | 0.953 | no | 0.0358 | 0.2864 |
| `A14` | 1.37 | +0.501 | +0.203 | +0.142 | +0.40 | +0.63 | **-0.212** | **-0.59** | -0.172 | 1.006 | no | 0.5580 | 1.0000 |
| `A15` | 1.02 | +0.430 | +0.225 | +0.162 | +0.44 | +0.01 | **-0.184** | **-0.50** | -0.249 | 1.041 | no | 0.6235 | 1.0000 |
| `A02` | 1.25 | +0.498 | +0.296 | +0.070 | +0.21 | +0.89 | **-0.305** | **-0.96** | -0.198 | 0.886 | no | 0.3422 | 1.0000 |
| `A01` | 1.87 | +1.187 | +0.218 | +0.750 | +1.69 | +1.65 | **-0.100** | **-0.24** | -0.040 | 1.157 | no | 0.8099 | 1.0000 |
| `A07` | 1.19 | +0.605 | +0.356 | +0.126 | +0.38 | +1.50 | **-0.231** | **-0.69** | -0.070 | 0.932 | no | 0.4924 | 1.0000 |

* **BH-FDR screen keeps 1 · Holm export keeps 1: `A18` at adjusted p 0.0484.**
* On the raw abnormal return with no control at all, **Holm keeps 0** (best
  adjusted p 1.000) — reported as `family_correction_secondary_raw_ar`.
* No `EW_VW_DISAGREE` flag fired; the value-weighted t agrees in sign with the
  equal-weighted t on all ten.
* Only `A18` is powered for its own observed effect (|−0.809| ≥ MDE 0.750). The
  other nine are asking a question this tape cannot answer, and their p-values
  should be read as such.
* Tail check: `A18`'s top 1% of events carry 13.1% of the summed abnormal
  return and the worst one-block jackknife moves t by 0.54, so it is not a
  tail-carried result. **Caveat on the diagnostic itself:** where an
  archetype's summed AR is near zero the top-1% *share* explodes or flips sign
  (`A05` reads −4.08, `A17` −3.28). That is the ratio being undefined, not a
  finding, and it is why the jackknife is printed beside it.

### 4.4 Three eras, never pooled

E1 2015H1-2016H1 · E2 2016H2-2017H1 · E3 2017H2-2018H2. Every event falls inside
a declared era (`n_events_outside_every_declared_era` = 0 on all ten).

| id | E1 | E2 | E3 | same sign | eras significant (uncorrected) |
|---|---|---|---|---|---|
| `A18` | -0.11 (t -0.19) | -0.67 (t -1.60) | -0.46 (t -1.02) | yes | — |
| `A17` | -0.69 (t -0.88) | -0.18 (t -0.49) | -0.10 (t -0.27) | yes | — |
| `A05` | +0.55 (t +1.17) | -0.98 (t -2.34) | +0.31 (t +0.73) | no | E2_2016H2-2017H1 |
| `A11` | +0.19 (t +0.40) | -0.14 (t -0.69) | +0.69 (t +1.38) | no | — |
| `A10` | +0.67 (t +1.30) | -0.51 (t -1.63) | +0.06 (t +0.08) | no | — |
| `A14` | -0.14 (t -0.37) | -0.64 (t -1.65) | +1.27 (t +1.47) | no | — |
| `A15` | +0.05 (t +0.08) | -0.58 (t -1.31) | +1.08 (t +1.43) | no | — |
| `A02` | +0.14 (t +0.35) | -0.02 (t -0.03) | +0.10 (t +0.15) | no | — |
| `A01` | +0.63 (t +0.85) | +1.24 (t +1.77) | +0.33 (t +0.37) | yes | — |
| `A07` | +0.50 (t +1.20) | -0.57 (t -0.75) | +0.51 (t +1.22) | no | — |

**Not one archetype is significant in even a single era before any correction,
except `A05` in E2 alone — which is the definition of a REGIME, not a finding.**
`A18`, the only Holm survivor, has the same sign in all three eras and clears
nothing in any of them.

### 4.5 The test that kills it — archetype vs OTHER EVENTS

`A18`'s EMC is **−0.809 pp at t −3.02**. The corpus-level EMC is **−0.848 pp at
t −3.03**. Those are the same number. So `A18` surviving Holm says the *event*
mattered, not the *archetype*: the control it beat was a non-event day, and every
archetype beats that control by about the same amount.

The question that separates the two is *is this archetype different from the
other events?* This is a **POST-HOC diagnostic** — computed after the primary
results were read, recorded in the sidecar
`U_archetypes_posthoc_vs_other_events.json` — and it therefore **cannot carry a
claim**. It is reported because leaving it out would let a corpus-level effect be
read as an archetype discovery.

| id | archetype − other events, pp | t | MDE pp | powered | p | Holm p |
|---|---|---|---|---|---|---|
| `A18` | -0.450 | -1.99 | 0.633 | no | 0.0544 | 0.544 |
| `A17` | -0.083 | -0.47 | 0.493 | no | 0.6397 | 1.000 |
| `A05` | -0.060 | -0.23 | 0.740 | no | 0.8215 | 1.000 |
| `A11` | +0.292 | +1.26 | 0.651 | no | 0.2176 | 1.000 |
| `A10` | -0.006 | -0.03 | 0.649 | no | 0.9786 | 1.000 |
| `A14` | +0.155 | +0.46 | 0.949 | no | 0.6507 | 1.000 |
| `A15` | +0.192 | +0.54 | 0.990 | no | 0.5902 | 1.000 |
| `A02` | +0.082 | +0.26 | 0.881 | no | 0.7959 | 1.000 |
| `A01` | +0.776 | +1.77 | 1.229 | no | 0.0861 | 0.775 |
| `A07` | +0.148 | +0.51 | 0.806 | no | 0.6115 | 1.000 |

**ZERO of ten survive Holm. ZERO survive the BH-FDR screen. Best Holm-adjusted
p = 0.544. Not one archetype is powered for its own observed effect.**

That is the lane's answer: **on this tape the archetype partition carries no
incremental information over "an event happened".**

---

## 5. What did not work, and what is still missing

### 5.1 The corpus is the binding constraint, and it is small

| quantity | value |
|---|---|
| rows in `event_table_v1` (2015-2026) | 993,005 |
| of those, news rows carrying a headline | 95,228 |
| of those, also carrying a CRSP permno | **21,841 (22.9%)** |
| distinct names | **91** |
| years with material coverage | **2015-2018** (2015: 3,051 · 2016: 8,093 · 2017: 8,116 · 2018: 2,580 · 2022: 1) |
| date blocks | 38 |
| events dropped for any reason | **0** (all five drop reasons counted, all zero) |
| NaN daily CRSP returns treated as a zero-return day | 12 |

The other 971,164 rows are untestable by *this* route, and for structural
reasons, not fixable ones:

* **618,419 IBES earnings-surprise rows carry no text at all.** An embedder has
  nothing to read. They are the `E3` lane's, not this one's.
* **276,978 EDGAR 8-K rows carry only item codes**, and only 8% of them link to
  a permno at all. An 8-K item family is already a discrete label; embedding
  `"2.02,9.01"` recovers the label and discovers nothing.
* The news corpus is the terminal repo's 156-symbol pull, so the 91 linked names
  are **mega-cap tech**. Any positive result on this tape would have been a
  regime finding about those names in those years.

So the honest scope of the whole lane is: *91 mega-cap-tech names, four years,
21,841 headlines.* The `E1/E2` backfill (resumable puller, tradable universe) is
the dependency that changes this, and until it lands no `RESEARCH_CLAIM` can
come out of the U route regardless of what the numbers do.

### 5.2 What did not work

1. **The rare-token plant, against a semantic embedder.** Run 01 failed the gate
   because `nemotron-3-embed-1b` put both planted families into one cluster at
   purity 0.50. Diagnosed, fixed, and the failed receipt is kept.
2. **The first plant sizing.** Against the corpus MDE rather than the planted
   cluster's own; a −3.05 SE draw sank it.
3. **The first negative control.** One seed, so it measured the draw.
4. **The first recovery criterion.** "Union of individually ≥80%-pure clusters"
   is a statement about `k`, not about recovery. Replaced by best
   cluster-matching F1.
5. **The free labeller.** 19 of 20 clusters got no model label: the free NIM
   reasoning models spend the entire token budget on visible chain of thought,
   at 600 tokens and still at 1500 with an explicit "do not think out loud".
   Mechanical top-terms labels stood in, `label_source` records which happened,
   and nothing downstream reads a label.
6. **Direction declaration bought nothing.** The free model was asked to declare
   LONG/SHORT/UNCLEAR from titles alone so that agreement with the realised sign
   could be measured. It returned a direction for one cluster of twenty, so all
   ten hypotheses ran as `TWO_SIDED` and the measurement was not made.
7. **Clustering stability is 0.54, not 0.9.** Half the assignment structure
   survives a reseed-and-resample. The dense, vocabulary-distinct clusters are
   stable; the boundaries among the several "general market movement" clusters
   are not. Silhouette 0.111 says the same from the other side.

### 5.3 What the corpse comparator did not demonstrate

Nothing was `BLOCKED` and nothing paid a `RESURRECTION_TAX` on this run, so the
gate exercised only its permissive branch against real hypotheses. Its blocking
branches are covered by unit test. Separately, `corpse_check` names exactly one
parent and the choice is register-order-dependent — mitigated by reporting
`action_pair_corpses`, not fixed. Fixing it properly means changing
`research_gym/scope.py`, which is another lane's file and another lane's call.

### 5.4 The open question this lane leaves behind

The corpus-level result — **a news-day entry underperforms a same-name,
same-month quiet-day entry by 0.85 pp over five sessions, t −3.03, and by
0.68 pp before any beta adjustment** — is the one number here worth another
session. It is powered on the β-adjusted arm and *not* powered on the raw arm,
it is one fact and not ten, and it was produced by a *matched control that this
lane chose*, so it is exactly the shape that a different control could erase.
The pre-registered follow-up is: does it survive a control matched on
**pre-event volatility and dollar volume** rather than only on name and month?
News clusters on days that were already moving, and "already moving" is the
obvious confound this design does not remove.

It is not a claim, it is not a book, and nothing should be sized on it.

---

## 6. Tests

Baseline before this lane, measured first:
**1 failed, 7,409 passed, 20 skipped** (`test_signal_reachability::test_every_orphan_is_classified`,
pre-existing, `backend.vendor.*` from another lane).

After: **7,610 passed, 29 skipped, 2 failed** on the long run — both transient,
both green on immediate re-run (`test_guard_missing_input_contract` and
`test_signal_reachability` were racing another agent's in-flight edits to
`backend/services` and `backend/vendor`; re-run individually: `1 passed` and
`9 passed`). `backend.services.archetypes` is reachable through
`scripts/u_archetypes_run.py` and needs no `CLASSIFIED` row.

New: **25 tests in `backend/tests/test_u_archetypes.py`** (all offline, all in
the fast suite) and **9 in `backend/tests/test_u_archetypes_receipt.py`** (X9
style: every number is read out of the receipt and the prose is required to
carry it; they skip, naming the file, when the receipt is absent).

What the 25 pin, beyond the U3 gate itself:

| test | what would otherwise rot |
|---|---|
| `test_block_grade_counts_date_blocks_not_events` | pooling name-days; asserts the block t is smaller than the pooled t on a corpus with a shared monthly shock |
| `test_the_paired_difference_removes_a_shared_regime` | a regime present in both arms shows t > 8 raw and < 3 paired |
| `test_the_paired_difference_keeps_a_real_event_effect` | and the paired test still finds a planted 1 pp effect |
| `test_ew_vw_disagreement_is_flagged` | one huge name dragging the VW mean the other way |
| `test_tail_diagnostics_surfaces_a_result_carried_by_a_handful_of_rows` | 1 row in 401 carrying 90% of the sum |
| `test_one_era_significant_is_reported_as_a_regime` | a single-era effect read as a finding |
| `test_era_table_counts_blocks_that_fall_in_no_declared_era` | three filters that do not partition |
| `test_family_correction_warns_when_the_family_shrank` | a family that shrinks after the results are seen |
| `test_an_exact_rerun_of_a_closed_rule_is_blocked_and_names_the_corpse` | the corpse gate going decorative |
| `test_a_shelved_signal_blocks_nothing_and_is_named_anyway` | SHELF silently gate-keeping |
| `test_the_precursor_is_observable_beforehand_and_names_no_return` | the Micron test |
| `test_clustering_is_stable_on_separable_text_and_unstable_on_noise` | a stability metric that reports 1.0 on noise |
| `test_silhouette_refuses_rather_than_returning_zero_on_one_cluster` | "measured and bad" vs "not defined" |
| `test_every_dropped_event_is_accounted_for_by_reason` | a silent drop |

---

## 7. Files

| path | what |
|---|---|
| `backend/services/archetypes.py` | the library: embedding, clustering, stability, typed hypotheses, corpse routing, block grading, the paired matched-control difference, era tables, family correction, the U3 harness |
| `scripts/u_archetypes_run.py` | the runner: event frame, CRSP/FF/beta legs, NIM embeddings, free-model labels, provenance-stamped receipt |
| `backend/tests/test_u_archetypes.py` | U3 offline (25 tests) |
| `backend/tests/test_u_archetypes_receipt.py` | X9-style doc-vs-receipt pins (9 tests) |
| `backend/data/optimus/archetypes/U_archetypes_nim.json` | **the receipt** (run 03) |
| `backend/data/optimus/archetypes/U_archetypes_nim_run01_RARE_TOKEN_PLANT_FAILED.json` | run 01, kept: the gate failing on a bad plant |
| `backend/data/optimus/archetypes/U_archetypes_posthoc_vs_other_events.json` | the post-hoc sidecar (§4.5) |
| `backend/data/optimus/archetypes/U_archetypes_assignment.csv` | every event's archetype, so any cluster can be audited |

Reproduce: `python -m scripts.u_archetypes_run --embedder nim --cache`
(≈26 min from a warm embedding cache; ≈70 min cold, 351 free NIM calls,
16,822 distinct titles, 708 s of embedding wall time, **$0.00**).
The embedding cache is written **outside the repo** (`%TEMP%/aegis_archetypes`,
overridable with `AEGIS_ARCHETYPE_CACHE`) because 17k × 2048 float32 is ~128 MB
and a cache is not a receipt.
