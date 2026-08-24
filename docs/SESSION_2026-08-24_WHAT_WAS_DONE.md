# SESSION 2026-08-24 (evening) — what was done

**Range** `bca1b99` → `HEAD` · every push CI-green and deploy-verified live.
**Read with** `docs/SESSION_2026-08-24_WHAT_IS_LEFT.md`, which is the handoff half.

The instruction that shaped the whole session, verbatim: *"don't kill or skip
ideas this easily by just saying everything is connected to each other — find a
way to classify, separate etc. With every setback find a way around."*

**The method that came out of it: attack the stated REASON, not the verdict.**
A verdict can be right for a reason that is wrong, and the reason is what gets
carried into the successor. Three verdicts were re-examined that way. Two kept
their conclusion and lost their reason; one flipped outright.

---

## 1. The external review's P0.2 correction — done, and it had a deadline

`selector_identity.py` · health key `selector_identity` · 10 tests.

Book identity is now dependency-aware: config + **selector identity** + router
identity, where selector identity splits into a hand-declared ALGORITHM version
and DERIVED dependency prints — families **and weights**, because
`mom_12_1: 1.0 → 2.0` is a different policy with an identical family set and
nothing caught that either. An undeclared selector is REFUSED rather than
defaulted to the composite's dependencies.

**The deadline nobody had noticed:** the nine live books had not yet taken their
per-book stamp, and `assert_config_current` migrates only while the legacy hash
still verifies. A formula that moved would have stranded every NAV history
permanently. All ten fingerprints are byte-identical to the legacy value, proven
by test, via the same `*_BASELINE` scoping `ROUTER_FINGERPRINT_BASELINE` uses.
**Verified live at 05:14 ET Monday: live hash = local hash, 0 of 9 stamped.**

## 2. Options — `iv_put_minus_call_30d` now TRANSFERS

`docs/FINDING_2026-08-24_OPTIONS_CONVENTION.md` · `option_implier.py` · 22 tests
· four declared measurements, each committed before its numbers existed.

| arm | median | gap vs panel +0.00194 | transfers |
|---|---|---|---|
| vendor IV *(where this started)* | −0.02428 | −0.02622 | no |
| ours, declared r, trailing q | −0.00338 | −0.00532 | no |
| **ours, q over the option's own WINDOW** | **−0.00179** | **−0.00373** | **yes** |

Two wrong conventions, no calibration layer, nothing fitted:

1. **yfinance's `impliedVolatility` column discounts nothing** — our own solver
   at r = 0, q = 0 reproduces it to 0.0009. That was the entire 0.026, and it is
   why the two spent routes failed: matched-strike fixed *which strikes*, the
   rank fixed *the scale*, and both kept reading the disputed column.
2. **The trailing dividend yield is the wrong `q` for a 30-day option.** Only
   11 of 39 names carry an ex-date inside the window; for the rest the correct
   `q` is zero and the trailing figure over-subtracts.

Ruled out on the way: early exercise (−0.0007, wrong direction, via a
Bjerksund–Stensland arm), the parity-implied rate (overshoots to +0.023 on 22 of
39 — and the failure diagnoses itself, the slope in K carrying exactly the
strike-dependent term the other arm measured), and **my own preferred
explanation** — I claimed the transfer test was mis-specified because the panel
spans rate regimes; the panel's residual regressed on FEDFUNDS over 168 months
is flat (slope +0.00001, t 0.04). They discount correctly; ours moved with the
rate *because ours was wrong*.

**`EVENT_RESPONSE_v1` may serve the full model on this column.** The
drop-feature fallback the review proposed is no longer needed.

The store records our residual and its conventions from its first row (schema
1.2.0), because `pi_options_pit` first fires tonight and a chain has no history
to go back for.

## 3. The graph — verdict kept, reason replaced, successor retired

`docs/FINDING_2026-08-24_GRAPH_BACKBONE.md` · `graph_beats_null()` · two
declared rounds plus a successor screen.

"100% dense ⇒ no graph" was measuring randomness: **a degree-preserving null on
the same coverage predicts 95.8%**. With 176 names drawing ~17 firms from a pool
of 94, `min_shared = 1` was admitting pairs connected *below* chance. The sweep
varied which edges exist and never what an edge is worth — significance-weighted
edges take corr with own return from −1.0000 to **−0.234 at 100% of the universe
rankable**, which no `min_shared` value achieved.

It fails anyway, on the right question: the graph concentrates **97%** as much as
its own null (z = −10.6). Real, and negligible — an equivalence result.

**And the successor was screened the same day** (`GRAPH-MIDCAP-SCREEN-1`), for
one coverage pull and no price data:

| | mega-cap | mid-cap band (rank 700–1600) |
|---|---|---|
| median covering firms | 17 | **6** |
| ratio to null | 0.972 | **0.924** |
| verdict | NEGLIGIBLE | **NEGLIGIBLE** |

Coverage really is three times thinner and the ratio really does improve — the
selectivity hypothesis points the right way and lands nowhere near the 0.80 bar.
**So the mechanism is closed on live-tradeable US equities generally, and
`GRAPH_PROPAGATION_MIDCAP_v2` is retired before it was declared.**

## 4. Roadmap item C — `REVISION-FORECASTER-1`: STOP

`docs/FINDING_2026-08-24_REVISION_FORECASTER.md` · pre-registered at `d81577e`
in the Aegis module, corpse-linted **PASS**, before the target column existed.

| link | IC | t |
|---|---|---|
| event state → revision | **+0.623** | +60.4 |
| revision → subsequent return (from `t1`) | +0.003 / +0.007 | 0.21 / 0.48 |
| composition: event state → return | −0.0005 | −0.04 |

The component of the revision a public numeric surprise explains is precisely
the component the market has already priced.

**The instrument was wrong once and produced a t of 4.04.** `t1` sits a median
20 days after the event — inside both return windows. I had already written the
interpretation before checking. Correctly timed: t = 0.81. Pinned by test.

## 5. The LLM provider question

**Nothing was ever broken.** `_get_provider` tests truthiness, so an empty
`ANTHROPIC_API_KEY` falls through to DeepSeek, which has been live throughout.
The Chinese replies were themselves proof the model was answering.

**The Chinese glitch was our bug, and I made the same mistake fixing it.**
Exactly one prompt named an output language (`explain_move.py`); every other
caller had none. I fixed it centrally in `llm_analyzer._call_llm` — better, and
**still wrong**: seven modules build their own client and call
`chat.completions.create` directly, so a fix inside one protected one of seven.
That is the identical per-call-site error one level up, made by the session that
had just written the comment criticising it.

The contract now lives once in **`llm_language.py`** and six of the seven call
sites import it (`llm_analyzer`, `llm_swarm`, `optimus_specialists`,
`leakage_probe`, `copilot`, `architecture_arena`). **`why_moved` is deliberately
deferred with a dated reason** — it fires tonight and is the P0 being waited on;
editing it hours before that run is risk with no upside.

`test_llm_language_contract.py` walks the source tree **by AST** and asserts
every direct call site applies the pin, so a new one that forgets is a red suite
rather than a discovery when somebody notices Chinese in a dashboard. (The first
version grepped the text and matched `llm_language` itself, because its
docstring *names* the call it exists to discuss — a detector that cannot tell
code from prose is the kind that gets an exemption added to silence it.)

A reply >10% non-Latin script is **refused** — one program-wide counter, on the
health surface. Refused rather than retried because the arena mints *gradeable*
records from some of this output.

`SOLE_PROVISIONED_PROVIDER = "deepseek"` + `provider_status()`, which reports
`declared_but_empty` separately from `absent`. In `CLAUDE.md`, in memory, and
test-pinned.

## 6. Three footguns removed

* **`.env.hidden` was not gitignored** — the CI-mimic recipe's own name for the
  secrets file. `git add -A` would have staged it.
* **The recipe then fired on me.** The subshell died before its EXIT trap ran
  and this machine had no keys for ten minutes — with the warning about that
  exact failure written hours earlier by this same session. `config.py` now
  gates `load_dotenv` on `AEGIS_IGNORE_DOTENV=1`; nothing moves. On its first
  run the switch caught **three of my own new tests** asserting against the
  ambient `.env`.
* **The Monday gate is one command** — `python -m scripts.monday_gate_check` —
  and it computes both clocks itself, reporting PENDING rather than FAIL for a
  job that has not had its chance yet.

---

## The through-line

**Six instrument defects, all found by running the instrument and asking what
it actually measured**: an `n_eff` gate that re-asked the density question; a
null comparison with one draw and no dispersion; a regime subset of one month
with no minimum; a return window containing the mediator it was scoring; and a
registered power calculation 2–3× optimistic because it used a theoretical null
where a realised prior was already on hand; and a language-contract
detector that matched its own docstring.

The last one has a rule attached: **derive `outcome_dispersion` from a realised
prior on the same panel, never from the theoretical null** — it understates by
~45% here.

**Demonstrated edge remains 0%.** What changed is that one blocked mechanism is
now servable, two dead ends are closed with measurements instead of arguments,
and the reasons in the record are ones a successor can rely on.
