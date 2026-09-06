# G7 — the forward lanes under the product ruler

*`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.2 — beta is allowed;
hidden beta is not. **Beta is column one.***

*The rule, which this line obeys: nothing here says "beats SPY" without beta, maxDD and the cost basis in the same sentence.*

- **Rows:** 16 (7 readable, 9 CANNOT DETERMINE)
- **Benchmark:** SPY total return, PINNED offline (`spy_tr_yf_adjclose`, 7212 sessions)
- **Frequency:** daily · HAC lag 5 · floor 20 observations
- **Leverage-neutral:** the lane's series scaled to SPY's realized vol over the same sessions, borrowed notional financed at RF + 100 bps annualised, unused cash earning RF (learner.growth.lever)
- **RF:** pinned Fama-French daily, last real observation 2026-05-29; 71 later sessions held flat at 5.04%/yr (each row also carries the rf=0 sensitivity)

| beta | t(beta-1) | beta Dimson | R2 vs SPY | book | verdict | n | window | raw exc %/yr | raw exc pp | lev-neutral exc %/yr | lev-neutral exc pp | maxDD book % | maxDD SPY % | cost basis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| -0.0416 | -12.665 | 0.1156 | 0.006 | conservative | OK | 47 | 2026-06-09 → 2026-08-18 | -15.374 | -2.497 | -11.614 | -1.862 | -2.33 | -3.376 | lane YAML marks, no extra bps |
| -0.0317 | -12.041 | 0.1108 | 0.0035 | balanced | OK | 47 | 2026-06-09 → 2026-08-18 | -14.282 | -2.311 | -9.401 | -1.495 | -2.238 | -3.376 | lane YAML marks, no extra bps |
| -0.0267 | -9.088 | 0.1374 | 0.0015 | aggressive | OK | 47 | 2026-06-09 → 2026-08-18 | -6.749 | -1.064 | -0.627 | -0.097 | -2.592 | -3.376 | lane YAML marks, no extra bps |
| 0.0972 | -8.818 | 0.6898 | 0.015 | balanced-ew-control | OK | 45 | 2026-06-11 → 2026-08-18 | -39.97 | -6.107 | -41.251 | -6.333 | -5.993 | -3.376 | lane YAML marks, no extra bps |
| 0.5563 | -1.008 | 1.2105 | 0.0469 | mirror | OK | 41 | 2026-06-17 → 2026-08-18 | -92.409 | -22.148 | -56.565 | -10.217 | -24.65 | -3.376 | lane YAML marks, no extra bps |
| 0.7163 | -1.071 | 1.9313 | 0.05 | conviction | OK | 41 | 2026-06-17 → 2026-08-18 | -45.237 | -7.68 | -23.249 | -3.566 | -21.277 | -3.376 | lane YAML marks, no extra bps |
| 0.0389 | -9.09 | 0.1252 | 0.0056 | conservative-atr | OK | 40 | 2026-06-18 → 2026-08-18 | 1.135 | 0.144 | 28.215 | 3.307 | -1.505 | -3.376 | lane YAML marks, no extra bps |
| — | — | — | — | smallmid-quality | CANNOT DETERMINE | 17 | — | — | — | — | — | — | — | lane YAML marks, no extra bps |
| — | — | — | — | tsmom-overlay | CANNOT DETERMINE | 14 | — | — | — | — | — | — | — | lane YAML marks, no extra bps |
| — | — | — | — | tsmom-6040-control | CANNOT DETERMINE | 14 | — | — | — | — | — | — | — | lane YAML marks, no extra bps |
| — | — | — | — | hack1 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |
| — | — | — | — | hack2 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |
| — | — | — | — | hack3 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |
| — | — | — | — | hack4 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |
| — | — | — | — | hack5 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |
| — | — | — | — | hack6 | CANNOT DETERMINE | 4 | — | — | — | — | — | — | — | venue fills, 0 commission |

**Cost basis legend** — *lane YAML marks, no extra bps* = website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here · *venue fills, 0 commission* = Alpaca PAPER account equity as reported by the venue: fills-as-filled, commission-free US equities, so the cost basis is realised slippage only and no explicit bps is applied on top

**`raw exc %/yr` and `lev-neutral exc %/yr` annualise a window of 40-47 sessions.** They are rates, not forecasts, and their standard errors are large; the `pp` columns are what actually happened.

## Readable books, one sentence each

- beta -0.0416 (t vs 1 = -12.665): conservative trails SPY by -2.497 pp raw over 47 sessions, maxDD -2.33% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -1.862 pp
- beta -0.0317 (t vs 1 = -12.041): balanced trails SPY by -2.311 pp raw over 47 sessions, maxDD -2.238% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -1.495 pp
- beta -0.0267 (t vs 1 = -9.088): aggressive trails SPY by -1.064 pp raw over 47 sessions, maxDD -2.592% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -0.097 pp
- beta 0.0972 (t vs 1 = -8.818): balanced-ew-control trails SPY by -6.107 pp raw over 45 sessions, maxDD -5.993% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -6.333 pp [STALE MARKS: beta on yesterday's market exceeds today's; Dimson beta 0.6898 is the exposure, and the vol used for the leverage-neutral rescale is smoothed, so that column flatters this book]
- beta 0.5563 (t vs 1 = -1.008): mirror trails SPY by -22.148 pp raw over 41 sessions, maxDD -24.65% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -10.217 pp [STALE MARKS: beta on yesterday's market exceeds today's; Dimson beta 1.2105 is the exposure, and the vol used for the leverage-neutral rescale is smoothed, so that column flatters this book]
- beta 0.7163 (t vs 1 = -1.071): conviction trails SPY by -7.68 pp raw over 41 sessions, maxDD -21.277% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess -3.566 pp [STALE MARKS: beta on yesterday's market exceeds today's; Dimson beta 1.9313 is the exposure, and the vol used for the leverage-neutral rescale is smoothed, so that column flatters this book]
- beta 0.0389 (t vs 1 = -9.09): conservative-atr beats SPY by 0.144 pp raw over 40 sessions, maxDD -1.505% vs SPY -3.376%, cost basis: website paper lane NAV, marked to market from recorded weights per the lane YAML; no extra bps applied here; LEVERAGE-NEUTRAL excess 3.307 pp

## Refusals, and why

- **smallmid-quality** — only 17 observations aligned with SPY and RF (the source series carries 17 returns); the floor is 20. Not interpolated, not extended.
- **tsmom-overlay** — only 14 observations aligned with SPY and RF (the source series carries 14 returns); the floor is 20. Not interpolated, not extended.
- **tsmom-6040-control** — only 14 observations aligned with SPY and RF (the source series carries 14 returns); the floor is 20. Not interpolated, not extended.
- **hack1** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.
- **hack2** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.
- **hack3** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.
- **hack4** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.
- **hack5** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.
- **hack6** — only 4 observations aligned with SPY and RF (the source series carries 5 returns); the floor is 20. Not interpolated, not extended.

## The beta column has a bias, and it points DOWN

**3 readable books load more on YESTERDAY'S market than on today's:** balanced-ew-control, mirror, conviction.

- these books load MORE on yesterday's market than on today's. A book cannot react to the market a day late; its marks can, and these do. So the ruler's contemporaneous beta is biased TOWARD ZERO for them and understates market exposure -- a stale mark HIDES beta, which is the one thing the amendment §2.2 forbids. `beta_dimson` is the exposure to read; the OLS beta is the ruler's literal number. Both are in the table.
- smoothed marks also understate realized volatility, so the leverage-neutral rescale (SPY vol / book vol) is an UPPER bound for the flagged books and their leverage-neutral excess is flattered by an unknown amount.
- How to settle it: compare a lane's NAV against the same weights repriced at the session's official close. That is a mark-to-market question for the website lane job, not a question this table can answer, and it is stated as an open item rather than assumed either way.

## Where the series were looked for

```json
{
 "website_lanes": {
  "searched": [
   {
    "path": "C:\\Users\\mrthn\\aegis-finance\\backend\\data\\aegis_pi.db",
    "kind": "sqlite paper_nav (canonical)",
    "exists": true,
    "paper_nav_rows": 0,
    "lanes": []
   },
   {
    "path": "C:\\Users\\mrthn\\aegis-finance\\docs\\conviction_replay\\prod_reads_2026-08-19\\track_record_full.json",
    "kind": "captured /api/pi/track-record",
    "exists": true,
    "lanes": [
     "aggressive",
     "balanced",
     "balanced-ew-control",
     "conservative",
     "conservative-atr",
     "conviction",
     "mirror",
     "smallmid-quality",
     "tsmom-6040-control",
     "tsmom-overlay"
    ],
    "expected_nav_date": "2026-08-18",
    "inception_date": "2026-06-08"
   },
   {
    "path": "C:\\Users\\mrthn\\aegis-finance\\.cache\\track_record.json",
    "kind": "captured /api/pi/track-record",
    "exists": true,
    "lanes": [
     "aggressive",
     "balanced",
     "balanced-ew-control",
     "conservative",
     "conservative-atr",
     "conviction",
     "mirror"
    ],
    "expected_nav_date": "2026-06-26",
    "inception_date": "2026-06-08"
   }
  ],
  "store": "C:\\Users\\mrthn\\aegis-finance\\docs\\conviction_replay\\prod_reads_2026-08-19\\track_record_full.json",
  "lanes_found": 10,
  "canonical_store": "C:\\Users\\mrthn\\aegis-finance\\backend\\data\\aegis_pi.db",
  "snapshot_expected_nav_date": "2026-08-18"
 },
 "hack_accounts": {
  "repo": "C:\\Users\\mrthn\\aegis-alpha-terminal",
  "repo_exists": true,
  "searched": [
   {
    "path": "C:\\Users\\mrthn\\aegis-alpha-terminal\\state\\benchmark_regret_20260903.json",
    "exists": true,
    "accounts": {
     "hack1": 6,
     "hack2": 6,
     "hack3": 6,
     "hack4": 6,
     "hack5": 6,
     "hack6": 6
    }
   }
  ],
  "accounts_found": 6,
  "secondary_not_merged": [
   {
    "path": "C:\\Users\\mrthn\\aegis-alpha-terminal\\state\\learning_report\\2026-09-02.json",
    "exists": true,
    "why_not_merged": "its session label is derived differently and disagrees with the primary series; merging would invent a return from a date bug"
   },
   {
    "path": "C:\\Users\\mrthn\\aegis-alpha-terminal\\state\\learning_report\\2026-09-03.json",
    "exists": true,
    "why_not_merged": "its session label is derived differently and disagrees with the primary series; merging would invent a return from a date bug"
   },
   {
    "path": "C:\\Users\\mrthn\\aegis-alpha-terminal\\state\\learning_report\\2026-09-04.json",
    "exists": true,
    "why_not_merged": "its session label is derived differently and disagrees with the primary series; merging would invent a return from a date bug"
   },
   {
    "path": "C:\\Users\\mrthn\\aegis-alpha-terminal\\state\\labor_day_lab_2026-09-07\\D1_connection_check_terminal.json",
    "exists": true,
    "why_not_merged": "its session label is derived differently and disagrees with the primary series; merging would invent a return from a date bug"
   }
  ],
  "railway": "NOT CALLED. A local dated series exists; and the venue could not lengthen it either -- the accounts are ~6 sessions old, so the binding constraint is account AGE, not readability."
 }
}
```

_Receipt: `backend/data/optimus/growth_book/G7_forward_lanes.json`_
