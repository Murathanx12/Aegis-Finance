# V2 Candidates

Features deferred until V1 (Phases 0-7) is shipped and has real usage data.
Listing here is intentionally non-binding — these may or may not survive
contact with actual users.

## LLM commentary on portfolio logic

**Pitch:** an LLM that reads the user's holdings + decision log and
explains "what your portfolio is doing" or "why this trade differs from
your stated thesis."

**Why deferred:**
- Adds a cost ceiling (LLM API calls cost real money per request).
- Introduces hallucination risk in a financial context — model could
  state facts about holdings that aren't true and the user has no way
  to verify without leaving the app.
- Exactly the kind of feature that derails a 60%-complete project. The
  V1 work is honest measurement, not narrative generation.

**Conditions to revisit:** V1 ships, scheduler runs unattended for 60
days without intervention, and ≥1 real user has logged ≥30 personal
decisions through the conviction lane.

## Point-in-time S&P 500 constituent universe

**Pitch:** rebuild the replay universe from a survivorship-bias-free
constituents history (e.g. CRSP, WRDS, or paid Polygon data) so the
backtested numbers reflect what an investor could actually have invested
in at each rebalance date.

**Why deferred:**
- Free-tier-friendly survivorship-free constituent feeds don't really
  exist. Anything reliable is paid.
- The current ETF-only diagnostic numbers (Sharpe 0.45-0.64) are the
  honest baseline already documented in `docs/replay_diagnostics_v1.md`.
- The full-universe replay numbers are flagged with the survivorship
  disclaimer everywhere they appear in the UI, so users aren't misled.

**Conditions to revisit:** project has revenue or grant funding to cover
a paid data feed, OR a free survivorship-free dataset becomes available.

## Live V7 crash model in replay

**Pitch:** replace `crash_prob_override=0.15` in the replay engine with
the real V7 crash model output computed against `MarketDataAtTimestamp`
sliced features, so we can validate whether the crash overlay actually
fires at sensible historical moments (COVID, 2022 selloff, 2024 carry
unwind).

**Why deferred:**
- The V7 model's feature pipeline currently fetches data internally;
  we exposed an `external_features` parameter in Phase 4 but haven't
  validated that the as-of feature reconstruction matches what V7 was
  trained on bit-for-bit.
- A mismatch would either silently return garbage probabilities or
  hard-error.
- Better to ship V1 with a documented stub override and a `/replay`
  endpoint that takes `crash_prob_override` as a parameter so power
  users can experiment.

**Conditions to revisit:** Phase 7 deployment is stable, scheduler
hourly MtM is producing data, and we have time to do the feature
reconstruction validation properly.

## Cost basis input + de-emphasis on holdings table

**Pitch:** add a `cost_basis` column to the holdings input form on
`/portfolio-intelligence/my-portfolio` and render it in muted small
text per SPEC §9 (Frydman et al. disposition effect).

**Why deferred:**
- Phase 5.5 (Personal Conviction lane) is where cost basis becomes
  load-bearing — that's where decision-time entry price feeds into
  the attribution + skill measurement pipeline.
- Adding it to the existing holdings form before Phase 5.5 means
  duplicating the input affordance in two places when 5.5 lands.

**Conditions to revisit:** Phase 5.5 lands. Cost basis input goes in
the Personal Conviction page. The my-portfolio page can then read
the same data store.

## Catalyst calendar + did-you-know panel

Already covered in `docs/phase2_decisions.md` — both deferred to a
later frontend pass once the reference lane MetricPacks are stable
enough to compare against. Not blockers for V1.
