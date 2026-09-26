# Fast movers -- 2026-09-26

Receipt: `fast_movers_2026-09-26.json`. Rules: `backend/services/fast_mover_forensics.py`. State at entry uses only rows stamped <= entry; the ex-post catalyst is a separate column. Credit requires beating the median of 3 matched controls by >= 1 sigma_h AND the mechanism visible at entry AND the reason it was held.

## Counts

```
{
 "n_cases": 318,
 "n_unique_ticker_entries": 203,
 "class_counts": {
  "OTHER": 175,
  "UNFORESEEABLE_NEWS": 40,
  "SECTOR_BETA": 26,
  "ATTENTION_REFLEXIVITY": 29,
  "RIGHT_STOCK_WRONG_REASON": 28,
  "ANALYST_CASCADE": 15,
  "PRODUCT_DEMAND": 5
 },
 "credit_counts": {
  "none": 108,
  "n/a": 210
 },
 "favourable": 108,
 "adverse": 210,
 "favourable_beating_controls": 62,
 "credited": 0,
 "coverage_by_family": {
  "night_books_twin": {
   "positions": 336,
   "priced": 336,
   "unpriced": {},
   "cases": 129
  },
  "night_books": {
   "positions": 22,
   "priced": 22,
   "unpriced": {},
   "cases": 20
  },
  "website_lane_localdb": {
   "positions": 665,
   "priced": 439,
   "unpriced": {
    "symbol absent from the bars panel": 226
   },
   "cases": 111
  },
  "pc_paper": {
   "positions": 11,
   "priced": 0,
   "unpriced": {
    "no session after entry in the panel": 10,
    "entry outside the panel's sessions": 1
   },
   "cases": 0
  },
  "conviction_log": {
   "positions": 12,
   "priced": 11,
   "unpriced": {
    "symbol absent from the bars panel": 1
   },
   "cases": 9
  },
  "alpaca_fleet": {
   "positions": 89,
   "priced": 87,
   "unpriced": {
    "symbol absent from the bars panel": 1,
    "no session after entry in the panel": 1
   },
   "cases": 49
  }
 },
 "candidate_features": []
}
```

## Cases

| ticker | book | entry | h | move | move h1 / h5 | sigma_h | class | credited | control median | candidate feature |
|---|---|---|---:|---:|---|---:|---|---|---:|---|
| TWST | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | +31.4% | +6.0% / +31.4% | 12.4% | OTHER | none | +0.2% |  |
| AXTI | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | OTHER | n/a | -1.5% |  |
| AXTI | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | OTHER | n/a | +1.6% |  |
| AXTI | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | OTHER | n/a | -0.3% |  |
| PRAX | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -11.7% | -2.4% / -11.7% | 8.7% | OTHER | n/a | -1.4% |  |
| LITE | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -11.0% | -11.0% / -0.8% | 6.1% | OTHER | n/a | -7.3% |  |
| WOLF | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | OTHER | n/a | -1.4% |  |
| WOLF | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | OTHER | n/a | +0.7% |  |
| WOLF | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | OTHER | n/a | +1.4% |  |
| ERAS | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | OTHER | n/a | +6.5% |  |
| ERAS | book:b109c8861c43e3c6 * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | OTHER | n/a | +2.3% |  |
| ERAS | book:3b3e7049e693c3e4 * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | OTHER | n/a | -0.8% |  |
| NUAI | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -5.7% | -5.7% / -1.3% | 7.9% | OTHER | n/a | +0.1% |  |
| NUAI | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -5.7% | -5.7% / -1.3% | 7.9% | OTHER | n/a | -2.1% |  |
| MU | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 5.9% | SECTOR_BETA | n/a | -3.4% |  |
| ORKA | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | +5.5% | +5.5% / +4.4% | 4.1% | OTHER | none | +0.8% |  |
| SNDK | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | OTHER | n/a | -3.7% |  |
| SNDK | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | OTHER | n/a | -5.8% |  |
| SNDK | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | OTHER | n/a | -8.4% |  |
| RVMD | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -5.2% | +1.8% / -5.2% | 5.4% | ATTENTION_REFLEXIVITY | n/a | -0.2% |  |
| RARE | hack6 | 2026-09-02 | 1 | -42.4% | -42.4% / -44.2% | 3.3% | ATTENTION_REFLEXIVITY | n/a | -1.2% |  |
| RARE | hack6 | 2026-09-03 | 1 | -42.3% | -42.3% / -46.1% | 3.3% | ATTENTION_REFLEXIVITY | n/a | -0.2% |  |
| MU | conservative | 2026-05-01 | 5 | +37.7% | +6.3% / +37.7% | 10.0% | OTHER | none | +2.1% |  |
| RKLB | conservative | 2026-05-01 | 5 | +33.8% | +1.9% / +33.8% | 12.6% | ATTENTION_REFLEXIVITY | none | +3.6% |  |
| SECZ | book:0b4039242299f2e0 | 2026-09-11 | 5 | +30.1% | -1.7% / +30.1% | 18.0% | ATTENTION_REFLEXIVITY | none | +1.0% |  |
| AMD | conservative | 2026-05-01 | 5 | +26.3% | -5.3% / +26.3% | 9.9% | RIGHT_STOCK_WRONG_REASON | none | +5.9% |  |
| INTC | conservative | 2026-05-01 | 5 | +24.9% | -4.2% / +24.9% | 11.1% | OTHER | none | +0.9% |  |
| ABSI | conviction | 2026-07-10 | 5 | -21.7% | -3.7% / -21.7% | 18.6% | OTHER | n/a | +2.5% |  |
| NTLA | conviction | 2026-07-10 | 5 | -20.0% | -8.4% / -20.0% | 12.5% | OTHER | n/a | -3.9% |  |
| MSTR | conservative | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | RIGHT_STOCK_WRONG_REASON | none | +5.1% |  |
| MSTR | balanced | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | RIGHT_STOCK_WRONG_REASON | none | +0.5% |  |
| MSTR | aggressive | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | RIGHT_STOCK_WRONG_REASON | none | -0.5% |  |
| MSTR | balanced-ew-control | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | RIGHT_STOCK_WRONG_REASON | none | -3.1% |  |
| RZLV | hack4 | 2026-09-01 | 1 | -19.4% | -19.4% / -20.4% | 5.3% | ATTENTION_REFLEXIVITY | n/a | +0.0% |  |
| ABSI | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | OTHER | none | -2.8% |  |
| ABSI | book:6310ca122657f8b1 | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | OTHER | none | +0.3% |  |
| ABSI | book:668a4e273abf21ff | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | OTHER | none | -0.0% |  |
| ADPT | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +18.3% | +2.5% / +18.3% | 7.9% | OTHER | none | +4.9% |  |
| FWDI | book:1dc244805b119552 | 2026-09-11 | 5 | +17.6% | +6.1% / +17.6% | 13.1% | UNFORESEEABLE_NEWS | none | -5.0% |  |
| OKLO | hack1 | 2026-09-09 | 5 | -16.6% | -6.6% / -16.6% | 11.5% | UNFORESEEABLE_NEWS | n/a | -3.6% |  |
| BE | hack6 | 2026-08-28 | 5 | +16.1% | -5.3% / +16.1% | 17.1% | OTHER | none | -0.4% |  |
| ABCL | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | OTHER | none | -0.8% |  |
| ABCL | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | OTHER | none | -3.8% |  |
| ABCL | book:6310ca122657f8b1 | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | OTHER | none | -1.3% |  |
| ABCL | book:668a4e273abf21ff | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | OTHER | none | +1.3% |  |
| INIO | book:9d62cc74239b435d | 2026-09-11 | 1 | -15.0% | -15.0% / +3.1% | 5.3% | OTHER | n/a | +0.4% |  |
| ORCL | conservative | 2026-05-01 | 5 | +14.0% | +4.9% / +14.0% | 8.5% | OTHER | none | +3.9% |  |
| ABG | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | ATTENTION_REFLEXIVITY | n/a | -6.4% |  |
| ABG | book:6310ca122657f8b1 | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | ATTENTION_REFLEXIVITY | n/a | +0.3% |  |
| ABG | book:668a4e273abf21ff | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | ATTENTION_REFLEXIVITY | n/a | +0.3% |  |
| ACHV | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +13.5% | +2.8% / +13.5% | 8.7% | OTHER | none | +6.7% |  |
| NAMS | hack6 | 2026-09-02 | 5 | -13.4% | +2.5% / -13.4% | 6.6% | ATTENTION_REFLEXIVITY | n/a | -0.1% |  |
| SOC | conviction | 2026-07-10 | 1 | +13.0% | +13.0% / +11.0% | 10.3% | ATTENTION_REFLEXIVITY | none | +3.6% |  |
| MNPR | book:0b4039242299f2e0 | 2026-09-11 | 5 | -13.0% | -2.3% / -13.0% | 9.7% | OTHER | n/a | +2.4% |  |
| PANW | hack2 | 2026-09-04 | 5 | +12.8% | +1.7% / +12.8% | 8.2% | ANALYST_CASCADE | n/a | -0.9% |  |
| NAMS | hack6 | 2026-09-08 | 1 | -12.4% | -12.4% / -18.7% | 2.9% | ATTENTION_REFLEXIVITY | n/a | -5.0% |  |
| AVTX | hack6 | 2026-09-09 | 1 | -12.3% | -12.3% / -15.4% | 4.2% | OTHER | n/a | -3.8% |  |
| PANW | hack1 | 2026-09-04 | 5 | +12.2% | +1.2% / +12.3% | 8.2% | ANALYST_CASCADE | n/a | -3.0% |  |
| ULS | hack6 | 2026-09-08 | 5 | -12.2% | -1.2% / -12.2% | 5.8% | OTHER | n/a | -3.0% |  |
| NAMS | hack6 | 2026-09-03 | 5 | -12.1% | -2.1% / -12.1% | 6.6% | ATTENTION_REFLEXIVITY | n/a | +1.8% |  |
| COHR | book:9d62cc74239b435d | 2026-09-11 | 1 | -12.1% | -12.1% / +4.7% | 6.4% | OTHER | n/a | -4.8% |  |
| COHR | book:1dc244805b119552 | 2026-09-11 | 1 | -12.1% | -12.1% / +4.7% | 6.4% | OTHER | n/a | -5.0% |  |
| GPCR | hack6 | 2026-09-08 | 1 | -11.4% | -11.4% / -16.3% | 3.1% | ATTENTION_REFLEXIVITY | n/a | -3.5% |  |
| BTU | book:1dc244805b119552 | 2026-09-11 | 5 | -11.2% | -3.7% / -11.2% | 6.8% | ATTENTION_REFLEXIVITY | n/a | -9.4% |  |
| AMD | conservative | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | RIGHT_STOCK_WRONG_REASON | none | +7.4% |  |
| AMD | balanced | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | RIGHT_STOCK_WRONG_REASON | none | +5.9% |  |
| AMD | aggressive | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | RIGHT_STOCK_WRONG_REASON | none | +5.9% |  |
| AMD | balanced-ew-control | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | RIGHT_STOCK_WRONG_REASON | none | +4.0% |  |
| COIN | conservative | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | OTHER | none | -1.0% |  |
| COIN | balanced | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | OTHER | none | +0.9% |  |
| COIN | aggressive | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | OTHER | none | -1.0% |  |
| COIN | balanced-ew-control | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | OTHER | none | -0.8% |  |
| LENZ | hack4 | 2026-09-09 | 1 | -11.1% | -11.1% / -22.0% | 4.2% | OTHER | n/a | -6.3% |  |
| TXG | book:9d62cc74239b435d | 2026-09-11 | 5 | +11.0% | +1.6% / +11.0% | 10.8% | OTHER | none | +3.2% |  |
| DKNG | conservative | 2026-05-01 | 5 | +11.0% | +2.5% / +11.0% | 7.3% | OTHER | none | -1.2% |  |
| JACK | book:60c4658f92c49e48 | 2026-09-11 | 5 | -10.9% | +0.0% / -10.9% | 12.3% | OTHER | n/a | -5.3% |  |
| HPE | book:000b263cf7ec2286 | 2026-09-11 | 1 | -10.8% | -10.8% / -1.9% | 4.0% | PRODUCT_DEMAND | n/a | +6.6% |  |
| AEIS | book:9d62cc74239b435d | 2026-09-11 | 1 | -10.6% | -10.6% / -7.8% | 4.9% | OTHER | n/a | +0.0% |  |
| MRAM | book:9d62cc74239b435d | 2026-09-11 | 1 | -10.5% | -10.5% / -7.2% | 6.2% | OTHER | n/a | +0.4% |  |
| IMCR | hack6 | 2026-09-08 | 5 | -10.5% | -2.9% / -10.5% | 4.6% | UNFORESEEABLE_NEWS | n/a | -1.4% |  |
| TEN | book:9d62cc74239b435d | 2026-09-11 | 5 | +10.4% | +5.2% / +10.4% | 5.5% | ATTENTION_REFLEXIVITY | none | -6.5% |  |
| AVGO | conservative | 2026-08-11 | 5 | -10.2% | -1.7% / -10.2% | 7.6% | OTHER | n/a | +10.7% |  |
| ABVX | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | OTHER | n/a | -3.1% |  |
| ABVX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | OTHER | n/a | -4.0% |  |
| ABVX | book:6310ca122657f8b1 | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | OTHER | n/a | -2.8% |  |
| ABVX | book:668a4e273abf21ff | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | OTHER | n/a | +4.2% |  |
| SLDP | conservative | 2026-05-01 | 5 | -10.1% | +1.2% / -10.1% | 8.6% | OTHER | n/a | -14.0% |  |
| TTAM | book:9d62cc74239b435d | 2026-09-11 | 5 | -10.1% | -3.9% / -10.1% | 5.1% | OTHER | n/a | -3.9% |  |
| GPGI | book:1dc244805b119552 | 2026-09-11 | 5 | -9.9% | -2.4% / -9.9% | 9.0% | OTHER | n/a | -3.3% |  |
| UEC | hack6 | 2026-08-28 | 1 | -9.8% | -9.8% / -15.0% | 5.3% | OTHER | n/a | +1.1% |  |
| TRMD | book:1dc244805b119552 | 2026-09-11 | 5 | +9.8% | +1.5% / +9.8% | 5.3% | UNFORESEEABLE_NEWS | none | -0.2% |  |
| TRMD | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +9.8% | +1.5% / +9.8% | 5.3% | UNFORESEEABLE_NEWS | none | -4.5% |  |
| AR | book:9d62cc74239b435d | 2026-09-11 | 5 | -9.8% | -1.4% / -9.8% | 4.4% | UNFORESEEABLE_NEWS | n/a | +3.5% |  |
| PRCH | conviction | 2026-07-10 | 1 | -9.7% | -9.7% / -7.9% | 4.4% | OTHER | n/a | +0.7% |  |
| GRAB | hack6 | 2026-09-08 | 1 | -9.5% | -9.5% / -13.4% | 2.3% | ATTENTION_REFLEXIVITY | n/a | +1.7% |  |
| AAOI | book:57c7af9fb85e59e8 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | OTHER | n/a | -5.9% |  |
| AAOI | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | OTHER | n/a | +3.2% |  |
| AAOI | book:1dc244805b119552 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | OTHER | n/a | +5.3% |  |
| AAOI | book:6310ca122657f8b1 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | OTHER | n/a | +4.7% |  |
| AAOI | book:668a4e273abf21ff | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | OTHER | n/a | +1.3% |  |
| MU | balanced | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | UNFORESEEABLE_NEWS | n/a | -1.4% |  |
| MU | aggressive | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | UNFORESEEABLE_NEWS | n/a | -3.2% |  |
| MU | balanced-ew-control | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | UNFORESEEABLE_NEWS | n/a | +0.1% |  |
| ARDX | hack6 | 2026-09-08 | 5 | -9.1% | +1.6% / -9.1% | 7.1% | OTHER | n/a | -13.1% |  |
| INTC | balanced | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | OTHER | none | -1.4% |  |
| INTC | aggressive | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | OTHER | none | -0.7% |  |
| INTC | balanced-ew-control | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | OTHER | none | +0.0% |  |
| NGVC | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +9.0% | +3.3% / +9.0% | 6.6% | UNFORESEEABLE_NEWS | none | -1.8% |  |
| ABX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | ATTENTION_REFLEXIVITY | n/a | -1.1% |  |
| ABX | book:6310ca122657f8b1 | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | ATTENTION_REFLEXIVITY | n/a | -3.6% |  |
| ABX | book:668a4e273abf21ff | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | ATTENTION_REFLEXIVITY | n/a | -1.9% |  |
| USAR | hack6 | 2026-08-28 | 1 | -8.9% | -8.9% / -10.0% | 5.8% | OTHER | n/a | -2.0% |  |
| ADNT | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -8.8% | -3.2% / -8.8% | 7.4% | UNFORESEEABLE_NEWS | n/a | +1.2% |  |
| ORCL | balanced | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | ANALYST_CASCADE | n/a | +0.1% |  |
| ORCL | aggressive | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | ANALYST_CASCADE | n/a | +1.9% |  |
| ORCL | balanced-ew-control | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | ANALYST_CASCADE | n/a | +1.9% |  |
| LXEO | hack4 | 2026-09-09 | 1 | -8.8% | -8.8% / -13.0% | 3.5% | OTHER | n/a | -1.7% |  |
| META | conservative | 2026-08-11 | 5 | -8.7% | -2.8% / -8.7% | 6.5% | OTHER | n/a | +3.2% |  |
| ACMR | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -8.6% | -8.6% / -6.4% | 6.4% | OTHER | n/a | -0.5% |  |
| TEAM | book:9d62cc74239b435d | 2026-09-11 | 1 | +8.6% | +8.6% / +8.1% | 6.1% | OTHER | none | +3.5% |  |
| AMSC | hack6 | 2026-09-08 | 5 | -8.6% | -3.2% / -8.6% | 9.5% | SECTOR_BETA | n/a | -4.1% |  |
| CTNM | book:9d62cc74239b435d | 2026-09-11 | 5 | -8.6% | +0.2% / -8.6% | 9.4% | ANALYST_CASCADE | n/a | +4.9% |  |
| NVDA | conservative | 2026-05-01 | 5 | +8.4% | +0.0% / +8.4% | 5.5% | SECTOR_BETA | none | +5.9% |  |
| KYTX | conviction | 2026-07-10 | 1 | -8.4% | -8.4% / -12.2% | 5.1% | OTHER | n/a | +0.7% |  |
| NVDA | balanced | 2026-09-04 | 5 | -8.4% | -2.1% / -8.4% | 5.7% | ANALYST_CASCADE | n/a | -2.8% |  |
| AA | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | UNFORESEEABLE_NEWS | n/a | +0.5% |  |
| AA | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | UNFORESEEABLE_NEWS | n/a | -4.0% |  |
| AA | book:6310ca122657f8b1 | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | UNFORESEEABLE_NEWS | n/a | -4.3% |  |
| AA | book:668a4e273abf21ff | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | UNFORESEEABLE_NEWS | n/a | -2.8% |  |
| AA | book:1ece648f7410da8e | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | UNFORESEEABLE_NEWS | n/a | -3.8% |  |
| NVDA | aggressive | 2026-09-04 | 5 | -8.3% | -2.0% / -8.3% | 5.7% | ANALYST_CASCADE | n/a | -3.2% |  |
| NVDA | balanced-ew-control | 2026-09-04 | 5 | -8.3% | -2.0% / -8.3% | 5.7% | ANALYST_CASCADE | n/a | -3.6% |  |
| DKNG | conservative | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | UNFORESEEABLE_NEWS | n/a | -5.8% |  |
| DKNG | balanced | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | UNFORESEEABLE_NEWS | n/a | -3.0% |  |
| DKNG | aggressive | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | UNFORESEEABLE_NEWS | n/a | -0.4% |  |
| DKNG | balanced-ew-control | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | UNFORESEEABLE_NEWS | n/a | -3.9% |  |
| INTC | balanced-ew-control | 2026-09-11 | 5 | +8.3% | -3.1% / +8.3% | 11.1% | RIGHT_STOCK_WRONG_REASON | none | +2.8% |  |
| RGTI | conservative | 2026-05-01 | 5 | +8.2% | +1.1% / +8.2% | 12.2% | OTHER | none | +2.2% |  |
| NB | hack4 | 2026-09-02 | 5 | -8.2% | -1.2% / -8.2% | 11.8% | OTHER | n/a | +4.1% |  |
| AMSC | conviction | 2026-07-10 | 5 | -8.2% | -4.9% / -8.2% | 11.6% | OTHER | n/a | -3.1% |  |
| HUBS | conviction | 2026-07-10 | 5 | +8.1% | +4.9% / +8.1% | 11.9% | OTHER | none | -0.2% |  |
| GPOR | book:000b263cf7ec2286 | 2026-09-11 | 5 | -8.1% | -0.4% / -8.1% | 4.1% | OTHER | n/a | -5.2% |  |
| HL | hack6 | 2026-08-28 | 1 | -8.0% | -8.0% / -4.3% | 4.3% | OTHER | n/a | -1.1% |  |
| CHYM | book:1dc244805b119552 | 2026-09-11 | 5 | -8.0% | +3.0% / -8.0% | 9.4% | ATTENTION_REFLEXIVITY | n/a | -1.7% |  |
| META | aggressive | 2026-09-04 | 5 | +7.9% | -0.5% / +7.9% | 6.4% | ANALYST_CASCADE | none | -4.1% |  |
| META | balanced-ew-control | 2026-09-04 | 5 | +7.9% | -0.5% / +7.9% | 6.4% | ANALYST_CASCADE | none | -0.2% |  |
| FTH | book:1dc244805b119552 | 2026-09-11 | 5 | -7.9% | +4.4% / -7.9% | 17.1% | UNFORESEEABLE_NEWS | n/a | -0.3% |  |
| META | balanced | 2026-09-04 | 5 | +7.8% | -0.6% / +7.8% | 6.4% | ANALYST_CASCADE | none | -6.4% |  |
| PLUG | hack1 | 2026-09-09 | 5 | -7.8% | -3.7% / -7.8% | 8.3% | UNFORESEEABLE_NEWS | n/a | -2.2% |  |
| ADEA | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.7% | -7.7% / -7.1% | 3.8% | OTHER | n/a | +0.6% |  |
| MP | hack6 | 2026-08-28 | 1 | -7.7% | -7.7% / -8.1% | 4.4% | OTHER | n/a | -0.6% |  |
| SVV | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.7% | +0.7% / -7.7% | 7.6% | OTHER | n/a | +3.5% |  |
| SCZM | book:9d62cc74239b435d | 2026-09-11 | 1 | -7.7% | -7.7% / -1.9% | 4.7% | OTHER | n/a | -0.7% |  |
| GS | conservative | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | UNFORESEEABLE_NEWS | n/a | -3.7% |  |
| GS | balanced | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | UNFORESEEABLE_NEWS | n/a | -1.5% |  |
| GS | aggressive | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | UNFORESEEABLE_NEWS | n/a | -3.7% |  |
| GS | balanced-ew-control | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | UNFORESEEABLE_NEWS | n/a | -0.0% |  |
| QUBT | conviction | 2026-07-10 | 1 | -7.6% | -7.6% / -9.9% | 6.8% | OTHER | n/a | -1.6% |  |
| MRVL | conservative | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | RIGHT_STOCK_WRONG_REASON | none | +0.0% |  |
| MRVL | balanced | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | RIGHT_STOCK_WRONG_REASON | none | -2.0% |  |
| MRVL | aggressive | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | RIGHT_STOCK_WRONG_REASON | none | +13.8% |  |
| MRVL | balanced-ew-control | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | RIGHT_STOCK_WRONG_REASON | none | +0.8% |  |
| KRMN | hack6 | 2026-09-09 | 1 | -7.4% | -7.4% / -0.6% | 4.3% | OTHER | n/a | -2.7% |  |
| ECG | book:32adc8a0ec8ca0fe | 2026-09-11 | 1 | -7.4% | -7.4% / -3.5% | 4.1% | OTHER | n/a | -4.1% |  |
| ACDC | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | OTHER | n/a | -0.5% |  |
| ACDC | book:6310ca122657f8b1 | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | OTHER | n/a | +0.2% |  |
| ACDC | book:668a4e273abf21ff | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | OTHER | n/a | -0.1% |  |
| A | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | OTHER | none | -3.6% |  |
| A | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | OTHER | none | -0.2% |  |
| ACRS | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +7.3% | +7.3% / +4.7% | 3.4% | ATTENTION_REFLEXIVITY | none | -0.9% |  |
| A | book:6310ca122657f8b1 | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | OTHER | none | +3.1% |  |
| A | book:668a4e273abf21ff | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | OTHER | none | +0.7% |  |
| A | book:1ece648f7410da8e | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | OTHER | none | -3.6% |  |
| WVE | hack4 | 2026-09-09 | 5 | -7.3% | -3.9% / -7.3% | 7.7% | SECTOR_BETA | n/a | -5.0% |  |
| ACLS | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.2% | -7.2% / -3.6% | 5.0% | OTHER | n/a | +0.8% |  |
| JMIA | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.1% | -1.9% / -7.1% | 7.8% | OTHER | n/a | -1.0% |  |
| PLTR | conservative | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | OTHER | none | -0.5% |  |
| PLTR | balanced | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | OTHER | none | +4.6% |  |
| PLTR | aggressive | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | OTHER | none | +4.2% |  |
| PLTR | balanced-ew-control | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | OTHER | none | +0.0% |  |
| MAZE | hack6 | 2026-09-02 | 5 | -7.1% | -3.1% / -7.1% | 6.3% | SECTOR_BETA | n/a | -8.4% |  |
| CAL | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.0% | -0.7% / -7.0% | 8.9% | SECTOR_BETA | n/a | -6.4% |  |
| CAL | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -7.0% | -0.7% / -7.0% | 8.9% | SECTOR_BETA | n/a | -7.5% |  |
| NTST | book:1dc244805b119552 | 2026-09-11 | 5 | -7.0% | -0.1% / -7.0% | 3.3% | UNFORESEEABLE_NEWS | n/a | -1.7% |  |
| ACI | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.9% | +6.9% / +3.8% | 3.5% | OTHER | none | +1.9% |  |
| ABAT | hack4 | 2026-09-02 | 5 | -6.9% | -1.1% / -6.9% | 13.4% | SECTOR_BETA | n/a | +1.5% |  |
| DNN | hack6 | 2026-08-28 | 1 | -6.9% | -6.9% / -6.0% | 4.0% | OTHER | n/a | +1.6% |  |
| CDE | hack6 | 2026-08-28 | 1 | -6.9% | -6.9% / -4.8% | 4.7% | OTHER | n/a | -1.4% |  |
| ABAT | hack4 | 2026-08-31 | 5 | +6.8% | -1.5% / +6.8% | 13.6% | OTHER | none | +3.8% |  |
| ADBE | conservative | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | RIGHT_STOCK_WRONG_REASON | none | +2.2% |  |
| ADBE | balanced | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | RIGHT_STOCK_WRONG_REASON | none | +3.8% |  |
| ADBE | aggressive | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | RIGHT_STOCK_WRONG_REASON | none | -8.3% |  |
| ADBE | balanced-ew-control | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | RIGHT_STOCK_WRONG_REASON | none | +0.8% |  |
| OSS | book:1dc244805b119552 | 2026-09-11 | 1 | -6.7% | -6.7% / -3.2% | 5.1% | OTHER | n/a | -1.4% |  |
| TTI | book:1dc244805b119552 | 2026-09-11 | 1 | -6.7% | -6.7% / -12.3% | 3.6% | OTHER | n/a | -0.6% |  |
| AMZN | conservative | 2026-08-11 | 5 | -6.7% | -3.9% / -6.7% | 6.2% | OTHER | n/a | -2.8% |  |
| UPBD | book:60c4658f92c49e48 | 2026-09-11 | 5 | -6.7% | -0.6% / -6.7% | 6.1% | SECTOR_BETA | n/a | -7.5% |  |
| ADBE | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.6% | +6.6% / -0.1% | 3.1% | RIGHT_STOCK_WRONG_REASON | none | -4.8% |  |
| NKTR | hack6 | 2026-09-03 | 5 | -6.6% | -0.7% / -6.6% | 6.8% | OTHER | n/a | +1.3% |  |
| DY | book:9d62cc74239b435d | 2026-09-11 | 1 | -6.6% | -6.6% / -5.0% | 3.6% | OTHER | n/a | +0.8% |  |
| IONQ | conservative | 2026-05-01 | 5 | +6.6% | -1.0% / +6.6% | 14.6% | SECTOR_BETA | none | -0.6% |  |
| CRM | conservative | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | RIGHT_STOCK_WRONG_REASON | none | +2.0% |  |
| CRM | balanced | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | RIGHT_STOCK_WRONG_REASON | none | -0.1% |  |
| CRM | aggressive | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | RIGHT_STOCK_WRONG_REASON | none | -2.0% |  |
| CRM | balanced-ew-control | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | RIGHT_STOCK_WRONG_REASON | none | -5.3% |  |
| AD | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -6.6% | +0.5% / -6.6% | 3.2% | ATTENTION_REFLEXIVITY | n/a | -3.0% |  |
| ABAT | hack4 | 2026-09-01 | 1 | +6.5% | +6.5% / +2.3% | 6.1% | OTHER | none | +1.9% |  |
| AAON | book:57c7af9fb85e59e8 | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | OTHER | n/a | -2.3% |  |
| AAON | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | OTHER | n/a | -0.1% |  |
| AAON | book:6310ca122657f8b1 | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | OTHER | n/a | -0.4% |  |
| AAON | book:668a4e273abf21ff | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | OTHER | n/a | +3.6% |  |
| ENPH | hack6 | 2026-08-28 | 1 | -6.5% | -6.5% / -6.6% | 5.0% | OTHER | n/a | -0.8% |  |
| QS | hack6 | 2026-08-28 | 1 | -6.4% | -6.4% / -8.2% | 4.9% | OTHER | n/a | +0.3% |  |
| UUUU | hack6 | 2026-08-28 | 1 | -6.3% | -6.3% / -8.1% | 4.9% | OTHER | n/a | -2.4% |  |
| WGO | book:9d62cc74239b435d | 2026-09-11 | 5 | -6.3% | +0.5% / -6.3% | 6.5% | SECTOR_BETA | n/a | -5.2% |  |
| PLGO | book:000b263cf7ec2286 | 2026-09-11 | 5 | -6.3% | -0.8% / -6.3% | 4.0% | ATTENTION_REFLEXIVITY | n/a | -2.2% |  |
| BUR | hack6 | 2026-09-08 | 5 | -6.3% | +0.4% / -6.3% | 5.5% | UNFORESEEABLE_NEWS | n/a | -0.1% |  |
| HON | conservative | 2026-08-11 | 5 | -6.3% | -3.4% / -6.3% | 5.0% | ANALYST_CASCADE | n/a | +0.2% |  |
| IONQ | balanced-ew-control | 2026-09-11 | 5 | +6.2% | +1.8% / +6.2% | 11.3% | RIGHT_STOCK_WRONG_REASON | none | +0.8% |  |
| SGML | book:9d62cc74239b435d | 2026-09-11 | 1 | -6.2% | -6.2% / +4.9% | 4.5% | OTHER | n/a | +0.4% |  |
| NX | book:0b4039242299f2e0 | 2026-09-11 | 5 | -6.2% | -2.4% / -6.2% | 9.6% | OTHER | n/a | -2.9% |  |
| CRVL | book:1dc244805b119552 | 2026-09-11 | 1 | +6.2% | +6.2% / +3.9% | 1.9% | OTHER | none | +2.3% |  |
| MAZE | hack6 | 2026-09-03 | 5 | -6.1% | +0.0% / -6.1% | 6.3% | SECTOR_BETA | n/a | -5.6% |  |
| COIN | conservative | 2026-05-01 | 1 | +6.1% | +6.1% / +5.2% | 5.5% | OTHER | none | +1.9% |  |
| UEC | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -6.1% | -1.8% / -6.1% | 9.1% | SECTOR_BETA | n/a | -4.1% |  |
| CHKP | book:60c4658f92c49e48 | 2026-09-11 | 1 | +6.1% | +6.1% / +1.7% | 2.5% | OTHER | none | -0.4% |  |
| CARR | book:60c4658f92c49e48 | 2026-09-11 | 5 | -6.1% | -0.2% / -6.1% | 4.8% | ATTENTION_REFLEXIVITY | n/a | -1.5% |  |
| QUBT | hack6 | 2026-08-28 | 5 | -6.1% | -3.5% / -6.1% | 11.7% | OTHER | n/a | -3.0% |  |
| POWL | book:f46aaaa40b8c039a | 2026-09-11 | 1 | -6.1% | -6.1% / +1.2% | 4.0% | OTHER | n/a | -0.4% |  |
| ACN | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.0% | +6.0% / -1.4% | 3.7% | OTHER | none | -0.9% |  |
| HOG | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -6.0% | -0.7% / -6.0% | 5.4% | SECTOR_BETA | n/a | -3.4% |  |
| BDC | book:1dc244805b119552 | 2026-09-11 | 1 | -5.9% | -5.9% / -7.9% | 3.2% | OTHER | n/a | +2.6% |  |
| AMD | balanced | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | OTHER | none | +1.7% |  |
| AMD | aggressive | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | OTHER | none | +1.1% |  |
| AMD | balanced-ew-control | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | OTHER | none | -1.7% |  |
| MSTR | conservative | 2026-05-01 | 5 | +5.9% | +3.7% / +5.9% | 13.3% | SECTOR_BETA | none | +14.8% |  |
| AVGO | book:1dc244805b119552 | 2026-09-11 | 1 | -5.9% | -5.9% / -2.4% | 2.7% | ANALYST_CASCADE | n/a | -4.5% |  |
| AVGO | book:32adc8a0ec8ca0fe | 2026-09-11 | 1 | -5.9% | -5.9% / -2.4% | 2.7% | ANALYST_CASCADE | n/a | +2.0% |  |
| HAL | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.9% | -2.0% / -5.9% | 4.8% | SECTOR_BETA | n/a | -2.6% |  |
| AADX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | UNFORESEEABLE_NEWS | none | -4.6% |  |
| AADX | book:6310ca122657f8b1 | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | UNFORESEEABLE_NEWS | none | -1.7% |  |
| AADX | book:668a4e273abf21ff | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | UNFORESEEABLE_NEWS | none | -4.6% |  |
| AADX | book:1ece648f7410da8e | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | UNFORESEEABLE_NEWS | none | -4.3% |  |
| MU | conservative | 2026-08-11 | 1 | +5.8% | +5.8% / +9.3% | 7.0% | OTHER | none | -0.2% |  |
| ALMU | hack4 | 2026-08-31 | 1 | -5.8% | -5.8% / +0.6% | 6.4% | OTHER | n/a | +0.7% |  |
| GE | balanced | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | SECTOR_BETA | n/a | -2.7% |  |
| GE | aggressive | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | SECTOR_BETA | n/a | -3.7% |  |
| GE | balanced-ew-control | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | SECTOR_BETA | n/a | -3.7% |  |
| DKNG | conviction | 2026-07-10 | 5 | -5.8% | -0.1% / -5.8% | 7.6% | OTHER | n/a | -2.1% |  |
| NKTR | hack6 | 2026-09-02 | 1 | +5.8% | +5.8% / -2.2% | 3.0% | OTHER | none | +3.0% |  |
| NXE | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.7% | -5.7% / -6.9% | 3.1% | OTHER | n/a | -1.8% |  |
| BJ | book:60c4658f92c49e48 | 2026-09-11 | 1 | +5.7% | +5.7% / +2.1% | 1.9% | OTHER | none | +0.4% |  |
| NEXN | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 5.4% | SECTOR_BETA | n/a | -3.0% |  |
| CVS | book:1dc244805b119552 | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 3.6% | ATTENTION_REFLEXIVITY | n/a | +7.1% |  |
| CVS | book:60c4658f92c49e48 | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 3.6% | ATTENTION_REFLEXIVITY | n/a | -1.9% |  |
| EGO | book:60c4658f92c49e48 | 2026-09-11 | 1 | -5.6% | -5.6% / -0.9% | 4.1% | OTHER | n/a | +0.3% |  |
| DHR | conservative | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | OTHER | none | -0.3% |  |
| DHR | balanced | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | OTHER | none | -0.4% |  |
| DHR | aggressive | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | OTHER | none | -0.6% |  |
| DHR | balanced-ew-control | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | OTHER | none | +2.1% |  |
| QQQ | conservative | 2026-05-01 | 5 | +5.5% | -0.2% / +5.5% | 2.8% | OTHER | none | -2.4% |  |
| ERIE | book:9d62cc74239b435d | 2026-09-11 | 1 | +5.5% | +5.5% / -0.7% | 3.1% | OTHER | none | +1.4% |  |
| ACHR | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | UNFORESEEABLE_NEWS | n/a | -1.9% |  |
| ACHR | book:6310ca122657f8b1 | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | UNFORESEEABLE_NEWS | n/a | -2.9% |  |
| ACHR | book:668a4e273abf21ff | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | UNFORESEEABLE_NEWS | n/a | -2.5% |  |
| ORCL | conservative | 2026-08-11 | 5 | -5.5% | +1.5% / -5.5% | 9.3% | OTHER | n/a | -1.2% |  |
| MU | conservative | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | UNFORESEEABLE_NEWS | n/a | -1.0% |  |
| MU | balanced | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | UNFORESEEABLE_NEWS | n/a | +0.6% |  |
| MU | aggressive | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | UNFORESEEABLE_NEWS | n/a | +0.8% |  |
| MU | balanced-ew-control | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | UNFORESEEABLE_NEWS | n/a | +0.9% |  |
| NBR | book:60c4658f92c49e48 | 2026-09-11 | 5 | -5.4% | -3.6% / -5.4% | 7.0% | OTHER | n/a | +0.8% |  |
| FSLR | conservative | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | OTHER | n/a | +1.9% |  |
| FSLR | balanced | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | OTHER | n/a | +1.3% |  |
| FSLR | aggressive | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | OTHER | n/a | +0.8% |  |
| FSLR | balanced-ew-control | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | OTHER | n/a | -0.4% |  |
| FUL | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.4% | -2.4% / -5.4% | 4.7% | SECTOR_BETA | n/a | -7.3% |  |
| ALMU | hack4 | 2026-09-01 | 5 | +5.4% | +1.8% / +5.4% | 12.9% | OTHER | none | -1.6% |  |
| XOM | conservative | 2026-05-01 | 5 | -5.4% | +0.6% / -5.4% | 4.2% | SECTOR_BETA | n/a | +3.1% |  |
| ORCL | conservative | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | PRODUCT_DEMAND | n/a | +8.4% |  |
| ORCL | balanced | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | PRODUCT_DEMAND | n/a | -2.0% |  |
| ORCL | aggressive | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | PRODUCT_DEMAND | n/a | +6.8% |  |
| ORCL | balanced-ew-control | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | PRODUCT_DEMAND | n/a | -2.0% |  |
| TTWO | conservative | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | OTHER | n/a | +4.0% |  |
| TTWO | balanced | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | OTHER | n/a | +1.9% |  |
| TTWO | aggressive | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | OTHER | n/a | -1.8% |  |
| TTWO | balanced-ew-control | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | OTHER | n/a | +5.6% |  |
| MAZE | hack6 | 2026-09-09 | 1 | -5.3% | -5.3% / -8.8% | 2.8% | OTHER | n/a | -1.7% |  |
| NCLH | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.3% | -1.2% / -5.3% | 6.6% | SECTOR_BETA | n/a | -3.7% |  |
| NCLH | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -5.3% | -1.2% / -5.3% | 6.6% | OTHER | n/a | +0.5% |  |
| AAUC | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | OTHER | n/a | -1.3% |  |
| AAUC | book:6310ca122657f8b1 | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | OTHER | n/a | -0.1% |  |
| AAUC | book:668a4e273abf21ff | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | OTHER | n/a | +0.8% |  |
| FSLR | conservative | 2026-08-11 | 1 | -5.2% | -5.2% / -8.1% | 3.9% | OTHER | n/a | +0.7% |  |
| CALY | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -5.2% | -1.5% / -5.2% | 5.0% | ATTENTION_REFLEXIVITY | n/a | -0.8% |  |
| NVDA | hack4 | 2026-08-28 | 5 | +5.2% | +0.8% / +5.2% | 6.1% | SECTOR_BETA | none | +2.8% |  |
| ADBE | conservative | 2026-08-11 | 1 | -5.2% | -5.2% / -3.6% | 3.2% | OTHER | n/a | +1.5% |  |
| TDC | book:f46aaaa40b8c039a | 2026-09-11 | 1 | +5.2% | +5.2% / +3.5% | 4.1% | OTHER | none | -3.2% |  |
| NOVT | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.2% | -5.2% / -9.8% | 3.0% | OTHER | n/a | +0.4% |  |
| PAYS | book:000b263cf7ec2286 | 2026-09-11 | 5 | -5.1% | -1.4% / -5.1% | 10.0% | OTHER | n/a | -0.9% |  |
| NPO | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.1% | -5.1% / -2.3% | 2.8% | OTHER | n/a | +1.2% |  |
| SMR | hack6 | 2026-08-28 | 1 | -5.1% | -5.1% / -0.7% | 5.8% | OTHER | n/a | -1.7% |  |
| IONQ | balanced | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | OTHER | n/a | -0.6% |  |
| IONQ | aggressive | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | OTHER | n/a | +2.5% |  |
| IONQ | balanced-ew-control | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | OTHER | n/a | -0.6% |  |
| DKNG | conservative | 2026-08-11 | 1 | +5.1% | +5.1% / -0.9% | 3.7% | OTHER | none | -2.8% |  |
| ALM | book:f46aaaa40b8c039a | 2026-09-11 | 1 | -5.1% | -5.1% / -10.7% | 5.7% | OTHER | n/a | -0.6% |  |
| HALO | book:60c4658f92c49e48 | 2026-09-11 | 5 | +5.1% | +0.9% / +5.1% | 6.8% | UNFORESEEABLE_NEWS | none | +0.4% |  |
| GOOGL | conservative | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | RIGHT_STOCK_WRONG_REASON | none | -0.6% |  |
| GOOGL | balanced | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | RIGHT_STOCK_WRONG_REASON | none | +4.5% |  |
| GOOGL | aggressive | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | RIGHT_STOCK_WRONG_REASON | none | -1.7% |  |
| GOOGL | balanced-ew-control | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | RIGHT_STOCK_WRONG_REASON | none | +6.4% |  |
| MSFT | conservative | 2026-08-11 | 5 | -5.0% | -2.9% / -5.0% | 6.5% | OTHER | n/a | -3.7% |  |
| MLYS | hack6 | 2026-09-02 | 1 | +4.9% | +4.9% / +8.8% | 3.0% | OTHER | none | +0.3% |  |
| MAZE | hack6 | 2026-09-17 | 1 | -4.6% | -4.6% / -- | 2.9% | ATTENTION_REFLEXIVITY | n/a | -1.5% |  |
| ATR | hack6 | 2026-09-08 | 1 | -3.3% | -3.3% / -1.2% | 1.4% | SECTOR_BETA | n/a | -3.3% |  |
| BIP | book:60c4658f92c49e48 | 2026-09-11 | 1 | -3.1% | -3.1% / -1.9% | 1.6% | SECTOR_BETA | n/a | -2.1% |  |
| PFE | conservative | 2026-08-11 | 1 | -2.7% | -2.7% / +0.7% | 1.3% | OTHER | n/a | -0.8% |  |
| NGG | book:9d62cc74239b435d | 2026-09-11 | 1 | -2.2% | -2.2% / +0.2% | 1.2% | OTHER | n/a | +1.2% |  |

## Supplement: the ~10% books at h = 6 (2026-09-21)

Outside the declared window (h in 1, 5); printed because that session is where their gain came from.

| ticker | book | entry | h | move | move h1 / h5 | sigma_h | class | credited | control median | candidate feature |
|---|---|---|---:|---:|---|---:|---|---|---:|---|
| TWST | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +30.5% | -- / -- | 13.6% | OTHER | none | -2.2% |  |
| NUAI | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +28.8% | -- / -- | 19.4% | UNFORESEEABLE_NEWS | none | -0.5% |  |
| NUAI | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +28.8% | -- / -- | 19.4% | UNFORESEEABLE_NEWS | none | -5.1% |  |
| AXTI | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | ANALYST_CASCADE | none | -1.6% |  |
| AXTI | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | ANALYST_CASCADE | none | +1.7% |  |
| AXTI | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | ANALYST_CASCADE | none | -4.3% |  |
| PRAX | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | -11.7% | -- / -- | 9.5% | OTHER | n/a | -2.5% |  |
| SNDK | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | UNFORESEEABLE_NEWS | none | +0.5% |  |
| SNDK | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | UNFORESEEABLE_NEWS | none | +3.1% |  |
| SNDK | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | UNFORESEEABLE_NEWS | none | +2.9% |  |
| WOLF | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | UNFORESEEABLE_NEWS | none | -2.6% |  |
| WOLF | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | UNFORESEEABLE_NEWS | none | -1.2% |  |
| WOLF | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | UNFORESEEABLE_NEWS | none | -1.6% |  |
| MU | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +6.7% | -- / -- | 14.5% | RIGHT_STOCK_WRONG_REASON | none | +2.0% |  |
| ERAS | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | OTHER | n/a | +2.4% |  |
| ERAS | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | OTHER | n/a | -1.5% |  |
| ERAS | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | OTHER | n/a | +1.7% |  |

`*` = one of the ~10% books Murat named (abstention, always-invested, 12-1 momentum).
