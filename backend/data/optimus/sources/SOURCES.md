# SOURCES -- the source/actor scoreboard (2026-09-26)

Every source is a forecaster that has not earned a weight yet. Social sources are an **attention layer, not a truth layer**; X and Reddit **never generate orders**. A source whose names pop then fade is kept and labelled `use_as: reversal`.

Receipt: `scoreboard_2026-09-26.json` -- 477 sources, 0 claims, 0 sources with at least one claim.

## By kind

| kind | sources | claims | unverified |
|---|---:|---:|---:|
| filing | 4 | 0 | 0 |
| industry_specialist | 1 | 0 | 0 |
| newswire | 14 | 0 | 0 |
| reddit_community | 2 | 0 | 0 |
| sell_side | 456 | 0 | 0 |

## Sources with claims (or social, unverified or not)

| source | kind | verified | n | lead h (med) | corrob. | 1d | 5d | 21d signed | FP 21d | skill h1/h5/h20 | crowding | weight | use as |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| (none: no claim recorded and no X/Reddit source registered yet) | | | | | | | | | | | | | |

477 further registered sources (newswires, filings, brokerages) have n=0 and weight=prior; they are in the JSON receipt.

## Metrics

- `lead_h_median`: hours from claim to the earliest mainstream (newswire/filing) item on the same ticker within +/-48h; positive = source first
- `corroboration_rate`: share of claims with a mainstream item on the same ticker in that window (a proxy for fact accuracy until facts are matched)
- `rel_ret_Nd`: mean name-minus-SPY return over N sessions entering at the first close strictly after the claim date
- `signed_ret_Nd`: the same, times the claim's stated direction
- `false_positive_rate_21d`: share of directional claims whose signed 21-session relative return was negative
- `skill_hN`: forecast_reputation.arm_skill keyed (source_id, beats_benchmark, h), held out on the later half by date
- `crowding_signature`: mean signed 21d minus mean signed 5d; <= -0.01 with a positive 5d and n >= 10 = use_as reversal
- `weight`: 'prior' until 20 graded rows at a horizon; then max(0, best held-out skill)
