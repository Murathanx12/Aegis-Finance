# FACTOR_MENU.md — Qlib Alpha158 Factor Reference Menu

> **Status: REFERENCE ONLY. Nothing here is wired into Aegis.** This is a formula
> catalog harvested from Microsoft Qlib's `Alpha158` handler to inform a *future*
> cross-sectional ranker. Qlib is **not** a dependency of Aegis and is not cloned,
> vendored, or imported anywhere in this repo. No code, dependencies, or config
> were changed to produce this document.

## 1. What Alpha158 is — and the gate any of these must clear

[Alpha158](https://github.com/microsoft/qlib) is the canonical feature handler that
ships with Microsoft's Qlib quant platform (`qlib/contrib/data/loader.py`,
`Alpha158DL.get_feature_config`; wrapped by `Alpha158` in
`qlib/contrib/data/handler.py`). It is a fixed set of ~158 hand-crafted technical
features computed per-instrument from daily OHLCV bars: a handful of intraday
"K-bar" shape features, normalized price/volume ratios, and a large block of
rolling-window features (momentum, volatility, regression, ranks, up/down counts,
volume dynamics) over windows `[5, 10, 20, 30, 60]`. Qlib expresses each feature as
a string in its own expression DSL (`$close`, `Ref`, `Mean`, `Std`, `Slope`,
`Corr`, `Quantile`, etc.); the plain-English translations below are mine, the raw
DSL strings are quoted verbatim from the loader.

**The critical caveat — none of these is "alpha" until it survives the Aegis gate.**
Alpha158 was designed for the China A-share universe with Qlib's own point-in-time
data store. On this project we have already learned (the hard way) that a
plausible-looking factor proves nothing on its own:

- **Forward-IC first.** Any candidate must accrue real out-of-sample
  Information Coefficient via the project's `factor_ic` / forward-IC machinery
  (the same bench the T8/T9/T10 selection signals run through) **before** it can
  influence any ranking or lane. Backtest IC on free data does not count — see T7.
- **DSR/PBO overfitting gate.** A factor that looks good in-sample must clear the
  Deflated Sharpe / PBO / CPCV guards already wired to the gate. Mining 158
  features and keeping the best is *exactly* the multiple-testing trap those guards
  exist to catch; the more of this menu we test, the harsher the deflation must be.
- **Point-in-time, delisted-inclusive universe.** This is the binding constraint.
  Per the **T7 = REJECT-on-free-data** finding (`docs/NEGATIVE_RESULTS.md`,
  `docs/BACKLOG.md`), yfinance cannot build a survivorship-free universe (only
  ~1 of 20 delisted names was usable), so **no backtest on our current free data
  can certify cross-sectional alpha** — selection signals validate **forward only**
  (PIT IC + live NAV). Several Alpha158 features (RANK, QTLU/QTLD, the cross-name
  ranks) are explicitly cross-sectional and would be the *most* distorted by a
  survivorship-biased universe. Treat every row below as a hypothesis to be
  forward-tested, never as an adopted signal.

Bottom line: this menu is a source of *well-defined, reproducible candidate
formulas*. Adoption path is unchanged from the rest of the project — pre-register,
wire a forward-IC collector, let the clock accrue, then face the DSR/PBO gate.

---

## 2. The factor menu (grouped, with exact Qlib expressions)

Notation: `$open/$high/$low/$close/$volume` are the daily bar fields. `Ref($x, d)`
= value of `$x` `d` days ago. `%d` = the rolling window. `Greater/Less` =
element-wise max/min. `1e-12` terms are divide-by-zero guards. `/$close`
normalization makes a feature scale-free (comparable across price levels and across
names) — this is how Alpha158 makes price-derived features cross-sectionally usable.

### 2a. K-bar features (single-bar candle shape; window = current day)

| Factor | Plain-English formula | Qlib expression | What it captures |
|--------|----------------------|-----------------|------------------|
| KMID  | (close − open) / open | `($close-$open)/$open` | Body of the candle as % of open — net intraday drift |
| KLEN  | (high − low) / open | `($high-$low)/$open` | Full intraday range as % of open — daily realized range |
| KMID2 | (close − open) / range | `($close-$open)/($high-$low+1e-12)` | Body as a fraction of the day's range — conviction of the move |
| KUP   | (high − max(open,close)) / open | `($high-Greater($open, $close))/$open` | Upper wick as % of open — rejected upside |
| KUP2  | upper wick / range | `($high-Greater($open, $close))/($high-$low+1e-12)` | Upper wick as fraction of range |
| KLOW  | (min(open,close) − low) / open | `(Less($open, $close)-$low)/$open` | Lower wick as % of open — rejected downside / dip-buying |
| KLOW2 | lower wick / range | `(Less($open, $close)-$low)/($high-$low+1e-12)` | Lower wick as fraction of range |
| KSFT  | (2·close − high − low) / open | `(2*$close-$high-$low)/$open` | Where close sits vs range midpoint, scaled by open — intraday "shift" |
| KSFT2 | (2·close − high − low) / range | `(2*$close-$high-$low)/($high-$low+1e-12)` | Close position within range (≈ −1 at low, +1 at high) |

### 2b. Price features (lagged price ratios; default fields OPEN/HIGH/LOW/VWAP, window `[0]`)

Default config uses only the current bar (`window = [0]`), i.e. each field
expressed relative to today's close. With window `d>0` it becomes the lagged ratio
`Ref($field, d)/$close`.

| Factor | Plain-English formula | Window(s) | What it captures |
|--------|----------------------|-----------|------------------|
| OPEN0 | open / close | 0 (default) | Open relative to close (intraday gap/position) |
| HIGH0 | high / close | 0 (default) | High relative to close (room above) |
| LOW0  | low / close | 0 (default) | Low relative to close (room below) |
| VWAP0 | vwap / close | 0 (default) | Close vs volume-weighted avg price — intraday positioning |
| `{FIELD}{d}` | `Ref($field, d) / close` (d>0) | configurable | Past field level vs today's close (price reversion/trend) |

Exact expression: `Ref($field, d)/$close` for `d>0`, and `$field/$close` at `d=0`,
for each `field` in `["OPEN", "HIGH", "LOW", "VWAP"]`.

### 2c. Volume features (normalized volume; window `[0]` default)

| Factor | Plain-English formula | Window(s) | What it captures |
|--------|----------------------|-----------|------------------|
| VOLUME0 | volume / volume (≈1 today) | 0 (default) | Identity at d=0; basis for lagged volume ratios |
| `VOLUME{d}` | `Ref($volume, d) / volume` (d>0) | configurable | Past volume vs today's volume — volume trend |

Exact expression: `Ref($volume, d)/($volume+1e-12)` for `d>0`,
`$volume/($volume+1e-12)` at `d=0`.

### 2d. Rolling features (window `d` ∈ `[5, 10, 20, 30, 60]` unless noted)

Price/return-based rolling features:

| Factor | Plain-English formula | Window(s) | What it captures |
|--------|----------------------|-----------|------------------|
| ROC{d}  | close `d` days ago / close | 5,10,20,30,60 | Rate of change — **momentum** (inverse form: >1 means price fell) |
| MA{d}   | mean(close, d) / close | 5,10,20,30,60 | Distance from moving average — trend / mean-reversion |
| STD{d}  | std(close, d) / close | 5,10,20,30,60 | Rolling price **volatility** (coefficient-of-variation-like) |
| BETA{d} | slope of close vs time, d / close | 5,10,20,30,60 | Linear trend slope per day, normalized — trend speed |
| RSQR{d} | R² of close-vs-time regression, d | 5,10,20,30,60 | Trend *quality* / linearity (how clean the trend is) |
| RESI{d} | regression residual of close, d / close | 5,10,20,30,60 | Deviation from fitted trend line — short-term dislocation |
| MAX{d}  | max(high, d) / close | 5,10,20,30,60 | Distance below recent high (52w-high analog) |
| MIN{d}  | min(low, d) / close | 5,10,20,30,60 | Distance above recent low |
| QTLU{d} | 80th-pctile(close, d) / close | 5,10,20,30,60 | Upper-quantile price level vs now — overbought band |
| QTLD{d} | 20th-pctile(close, d) / close | 5,10,20,30,60 | Lower-quantile price level vs now — oversold band |
| RANK{d} | percentile rank of today's close within last d | 5,10,20,30,60 | Where today sits in its own recent distribution (0–1) |
| RSV{d}  | (close − min low) / (max high − min low) | 5,10,20,30,60 | Stochastic %K — position in d-day high/low range |
| IMAX{d} | bars-since-highest-high / d | 5,10,20,30,60 | Recency of the high (0=today) — uptrend freshness |
| IMIN{d} | bars-since-lowest-low / d | 5,10,20,30,60 | Recency of the low |
| IMXD{d} | (idx of high − idx of low) / d | 5,10,20,30,60 | Ordering of high vs low — directional structure |
| CORR{d} | corr(close, log volume, d) | 5,10,20,30,60 | Price–volume co-movement (confirmation of moves) |
| CORD{d} | corr(close-return, log volume-change, d) | 5,10,20,30,60 | Return–volume-change co-movement |
| CNTP{d} | fraction of up days, d | 5,10,20,30,60 | Up-day frequency — bullish persistence |
| CNTN{d} | fraction of down days, d | 5,10,20,30,60 | Down-day frequency |
| CNTD{d} | CNTP − CNTN | 5,10,20,30,60 | Net up/down day balance |
| SUMP{d} | sum of up-moves / sum of |moves|, d | 5,10,20,30,60 | Share of total movement that was upward (RSI-like) |
| SUMN{d} | sum of down-moves / sum of |moves|, d | 5,10,20,30,60 | Share of movement that was downward |
| SUMD{d} | (up-sum − down-sum) / |moves|-sum, d | 5,10,20,30,60 | Net directional pressure (≈ scaled RSI) |

Exact expressions:

```
ROC{d}  = Ref($close, %d)/$close
MA{d}   = Mean($close, %d)/$close
STD{d}  = Std($close, %d)/$close
BETA{d} = Slope($close, %d)/$close
RSQR{d} = Rsquare($close, %d)
RESI{d} = Resi($close, %d)/$close
MAX{d}  = Max($high, %d)/$close
MIN{d}  = Min($low, %d)/$close
QTLU{d} = Quantile($close, %d, 0.8)/$close
QTLD{d} = Quantile($close, %d, 0.2)/$close
RANK{d} = Rank($close, %d)
RSV{d}  = ($close-Min($low, %d))/(Max($high, %d)-Min($low, %d)+1e-12)
IMAX{d} = IdxMax($high, %d)/%d
IMIN{d} = IdxMin($low, %d)/%d
IMXD{d} = (IdxMax($high, %d)-IdxMin($low, %d))/%d
CORR{d} = Corr($close, Log($volume+1), %d)
CORD{d} = Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), %d)
CNTP{d} = Mean($close>Ref($close, 1), %d)
CNTN{d} = Mean($close<Ref($close, 1), %d)
CNTD{d} = Mean($close>Ref($close, 1), %d)-Mean($close<Ref($close, 1), %d)
SUMP{d} = Sum(Greater($close-Ref($close, 1), 0), %d)/(Sum(Abs($close-Ref($close, 1)), %d)+1e-12)
SUMN{d} = Sum(Greater(Ref($close, 1)-$close, 0), %d)/(Sum(Abs($close-Ref($close, 1)), %d)+1e-12)
SUMD{d} = (Sum(Greater($close-Ref($close, 1), 0), %d)-Sum(Greater(Ref($close, 1)-$close, 0), %d))/(Sum(Abs($close-Ref($close, 1)), %d)+1e-12)
```

Volume-based rolling features:

| Factor | Plain-English formula | Window(s) | What it captures |
|--------|----------------------|-----------|------------------|
| VMA{d}   | mean(volume, d) / volume | 5,10,20,30,60 | Volume vs its average — relative activity |
| VSTD{d}  | std(volume, d) / volume | 5,10,20,30,60 | Volume **volatility** (erratic vs steady flow) |
| WVMA{d}  | std(|ret|·vol, d) / mean(|ret|·vol, d) | 5,10,20,30,60 | Volatility of dollar-impact-weighted volume — disorderly trading |
| VSUMP{d} | up-volume-changes / |volume-changes|, d | 5,10,20,30,60 | Share of volume change that was increasing |
| VSUMN{d} | down-volume-changes / |volume-changes|, d | 5,10,20,30,60 | Share of volume change that was decreasing |
| VSUMD{d} | (up − down volume-changes) / |changes|, d | 5,10,20,30,60 | Net volume-trend direction |

Exact expressions:

```
VMA{d}   = Mean($volume, %d)/($volume+1e-12)
VSTD{d}  = Std($volume, %d)/($volume+1e-12)
WVMA{d}  = Std(Abs($close/Ref($close, 1)-1)*$volume, %d)/(Mean(Abs($close/Ref($close, 1)-1)*$volume, %d)+1e-12)
VSUMP{d} = Sum(Greater($volume-Ref($volume, 1), 0), %d)/(Sum(Abs($volume-Ref($volume, 1)), %d)+1e-12)
VSUMN{d} = Sum(Greater(Ref($volume, 1)-$volume, 0), %d)/(Sum(Abs($volume-Ref($volume, 1)), %d)+1e-12)
VSUMD{d} = (Sum(Greater($volume-Ref($volume, 1), 0), %d)-Sum(Greater(Ref($volume, 1)-$volume, 0), %d))/(Sum(Abs($volume-Ref($volume, 1)), %d)+1e-12)
```

> **Provenance note.** All K-bar, rolling, and the formula strings above are quoted
> verbatim from `qlib/contrib/data/loader.py` (`Alpha158DL.get_feature_config`).
> The exact list of *price* fields and the *windows* applied to the price/volume
> blocks are config-driven in Qlib (default `windows=[5,10,20,30,60]` for rolling,
> price/volume default to current-bar `[0]`); the total of "158" counts the full
> cross-product of features × windows plus the K-bar set. I did not separately
> verify the precise default `price`/`volume` window lists against the handler
> wrapper, so treat the window column for groups 2b/2c as "configurable, defaults
> shown" rather than canonical.

---

## 3. What Aegis already computes (avoid duplication)

Cross-checked against `backend/services/cross_sectional_momentum.py` and
`engine/training/features.py`. Aegis already has direct or near-direct equivalents
for a large chunk of Alpha158's *price/momentum/volatility* block:

| Alpha158 factor | Aegis equivalent (already built) | Where |
|-----------------|----------------------------------|-------|
| ROC{d} (momentum) | `mom_1w..mom_12m` (`pct_change` over 5/10/21/42/63/126/252) **and** the 1M/3M/6M/12M cross-sectional composite | `features.py` §2; `cross_sectional_momentum.py` |
| RANK{d} (cross-name rank) | percentile rank + quintiles of the momentum composite | `cross_sectional_momentum.py` (`percentile`, `quintile`) |
| MAX{d}/MIN{d} (dist from high/low) | `dist_52w_high`, `dist_52w_low`, `drawdown_from_peak` | `features.py` §2 |
| STD{d} (price/return vol) | `vol_1w..vol_12m` (rolling std of log returns) + vol ratios, vol-of-vol, vol z-score | `features.py` §3 |
| MA{d} (dist from MA) | `sma_50d_dev / sma_100d_dev / sma_200d_dev`, `golden_cross` | `features.py` §4 |
| BETA{d}/RSQR{d} (trend slope/quality) | partial: `trend_strength_3m/12m` (mom/vol), MACD, RSI — *slope/R² not explicit* | `features.py` §4 |
| RSV{d} (stochastic %K) | Stochastic via `ta` lib in `technical_analysis.py` (service layer, not the ML matrix) | `technical_analysis.py` |
| CNTP/CNTN/CNTD (up/down day ratio) | `neg_day_ratio_21d/63d`, `down_streak` (down-side only) | `features.py` §6 |
| SUMP/SUMN/SUMD (directional pressure) | RSI (`rsi_14d`) is the close cousin; SUMD ≈ scaled RSI | `features.py` §4 |
| K-bar body/wick (KMID/KUP/KLOW…) | bollinger position, candle-shape features **not** present | — (gap) |
| CORR/CORD, VMA/VSTD/WVMA, VSUMP/N/D (price–volume) | **not present** — Aegis ML matrix is index-level (SP500/VIX/yields), no per-name OHLCV volume features | — (gap) |
| QTLU/QTLD (quantile bands) | `bollinger_pos` is the nearest analog; explicit rolling quantiles **not** present | — (gap) |
| IMAX/IMIN/IMXD (recency of extremes) | **not present** | — (gap) |

Key structural difference: `features.py` builds an **index/macro-level** feature
matrix (one row per date, features off SP500/VIX/yields/credit) for the *crash
model*. Alpha158 is **per-instrument cross-sectional** (one row per name per date).
`cross_sectional_momentum.py` is the only existing per-name cross-sectional ranker,
and it is deliberately scoped to momentum (and flagged "DESCRIPTIVE… weak/
insignificant forward IC on this universe — not validated alpha"). So the genuinely
*new* surface area Alpha158 offers Aegis is: **per-name volume/price-volume
features, candle-shape features, quantile-band features, and trend-quality
(slope/R²) features** — none of which the current code computes per instrument.

---

## 4. Top ~10 worth testing first (candidates for the forward-IC bench — NOT adoptions)

Selection criteria: (a) *adds information Aegis does not already have* (favor the
gaps above over re-deriving momentum), (b) cheap and robust to compute from free
yfinance OHLCV, (c) least sensitive to the survivorship problem (favor
within-name/time-series features over cross-name ranks that the biased universe
distorts most). Each is a **hypothesis to pre-register and forward-IC**, exactly
like T8/T9/T10 — not something to wire on faith.

1. **WVMA{20} / WVMA{60}** — volatility of return-weighted volume. Captures
   disorderly / impactful trading that Aegis has *no* analog for. Distinct from
   plain vol. Robust within-name.
2. **CORR{20}** — close–volume correlation. Classic "is the move confirmed by
   volume" signal; entirely new to Aegis. Within-name, survivorship-light.
3. **VSUMD{20}** — net volume-trend direction. Accumulation/distribution proxy;
   complements price momentum we already have. New surface.
4. **RESI{20}** — residual from the price trend line (price dislocation vs its own
   regression). Short-horizon mean-reversion candidate; not currently computed.
5. **RSQR{20}** — trend *quality*. Pairs naturally with our existing momentum: a
   strong-but-clean trend (high RSQR) may carry different forward IC than a noisy
   one. Cheap to add, conceptually orthogonal.
6. **KSFT2 / KMID2** — candle-shape "where did it close in the range / body
   conviction." Intraday microstructure info absent from Aegis; single-bar so
   trivially PIT-safe. Test as a pair.
7. **RSV{20}** (stochastic %K) — position in the 20-day high/low range. We compute
   this in `technical_analysis.py` for display but it never enters a ranked,
   IC-tested signal; worth promoting to the bench.
8. **QTLU{60} − QTLD{60} band position** — overbought/oversold via rolling
   quantiles rather than Bollinger σ-bands; more robust to fat tails. New form.
9. **IMXD{60}** — ordering/recency of the 60-day high vs low. Compact trend-
   structure feature with no Aegis equivalent; within-name, survivorship-light.
10. **CNTD{20} / SUMD{20}** — net up/down-day balance and net directional
    pressure. Close to RSI but as explicit, separable factors; let the bench tell
    us if they add IC over `rsi_14d`.

**Deliberately deprioritized for the *first* bench:** `RANK{d}` and the raw
cross-sectional ranks — they are the features most corrupted by a survivorship-
biased universe (T7), so they should wait for a PIT/delisted-inclusive data source.
Plain `ROC{d}` momentum is also low-priority: we already have it, and it already
showed weak forward IC on this universe (`cross_sectional_momentum.py` notes,
`docs/FACTOR_VALIDATION.md`).

---

### Sources
- Microsoft Qlib — `qlib/contrib/data/loader.py` (`Alpha158DL.get_feature_config`):
  https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py
- Microsoft Qlib — `qlib/contrib/data/handler.py` (`Alpha158` handler):
  https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py
- Cross-checked Aegis code: `backend/services/cross_sectional_momentum.py`,
  `engine/training/features.py`.
- Project survivorship/gate context: `docs/NEGATIVE_RESULTS.md`, `docs/BACKLOG.md`
  (T7 REJECT-on-free-data), `docs/FACTOR_VALIDATION.md`.
