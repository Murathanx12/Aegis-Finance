# Weekend reading list -- generated 2026-09-26 from the books

**How to paste.** Click a link (MuratClaw (Work) Chrome, signed in). On an article: Ctrl+A, Ctrl+C, then in `DIGEST.md` add a line `=== <url> | <date> | <source>` and paste under it (or save the page as a .txt into this folder). On a list or search page, open the articles it shows and paste each one. When done: `python -m scripts.digest_ingest --once --claims`.

**What happens after ingest.** Each entry is stored locally (never committed); DeepSeek extracts the claims (ticker, up/down, horizon, magnitude, the quote); each claim becomes a `source:<column>` forecast row dated at ingest time, and the existing grader scores it from the next session against SPY at 1/5/20 sessions. The column (Heard on the Street, Barron's picks, ...) earns or loses its weight from those grades.

Names: personal 12, competition 23, PROBE 23 (56 distinct).

## (a) WSJ news archive, one day per trading day, last 8 weeks
Why: the dated record of what WSJ said, to grade against what happened. Extract: every headline naming a listed stock -> open it -> paste. Fields: ticker, direction, horizon, magnitude, quote.

- [2026-09-25 (Fri)](https://www.wsj.com/news/archive/2026/09/25)
- [2026-09-24 (Thu)](https://www.wsj.com/news/archive/2026/09/24)
- [2026-09-23 (Wed)](https://www.wsj.com/news/archive/2026/09/23)
- [2026-09-22 (Tue)](https://www.wsj.com/news/archive/2026/09/22)
- [2026-09-21 (Mon)](https://www.wsj.com/news/archive/2026/09/21)
- [2026-09-18 (Fri)](https://www.wsj.com/news/archive/2026/09/18)
- [2026-09-17 (Thu)](https://www.wsj.com/news/archive/2026/09/17)
- [2026-09-16 (Wed)](https://www.wsj.com/news/archive/2026/09/16)
- [2026-09-15 (Tue)](https://www.wsj.com/news/archive/2026/09/15)
- [2026-09-14 (Mon)](https://www.wsj.com/news/archive/2026/09/14)
- [2026-09-11 (Fri)](https://www.wsj.com/news/archive/2026/09/11)
- [2026-09-10 (Thu)](https://www.wsj.com/news/archive/2026/09/10)
- [2026-09-09 (Wed)](https://www.wsj.com/news/archive/2026/09/09)
- [2026-09-08 (Tue)](https://www.wsj.com/news/archive/2026/09/08)
- [2026-09-04 (Fri)](https://www.wsj.com/news/archive/2026/09/04)
- [2026-09-03 (Thu)](https://www.wsj.com/news/archive/2026/09/03)
- [2026-09-02 (Wed)](https://www.wsj.com/news/archive/2026/09/02)
- [2026-09-01 (Tue)](https://www.wsj.com/news/archive/2026/09/01)
- [2026-08-31 (Mon)](https://www.wsj.com/news/archive/2026/08/31)
- [2026-08-28 (Fri)](https://www.wsj.com/news/archive/2026/08/28)
- [2026-08-27 (Thu)](https://www.wsj.com/news/archive/2026/08/27)
- [2026-08-26 (Wed)](https://www.wsj.com/news/archive/2026/08/26)
- [2026-08-25 (Tue)](https://www.wsj.com/news/archive/2026/08/25)
- [2026-08-24 (Mon)](https://www.wsj.com/news/archive/2026/08/24)
- [2026-08-21 (Fri)](https://www.wsj.com/news/archive/2026/08/21)
- [2026-08-20 (Thu)](https://www.wsj.com/news/archive/2026/08/20)
- [2026-08-19 (Wed)](https://www.wsj.com/news/archive/2026/08/19)
- [2026-08-18 (Tue)](https://www.wsj.com/news/archive/2026/08/18)
- [2026-08-17 (Mon)](https://www.wsj.com/news/archive/2026/08/17)
- [2026-08-14 (Fri)](https://www.wsj.com/news/archive/2026/08/14)
- [2026-08-13 (Thu)](https://www.wsj.com/news/archive/2026/08/13)
- [2026-08-12 (Wed)](https://www.wsj.com/news/archive/2026/08/12)
- [2026-08-11 (Tue)](https://www.wsj.com/news/archive/2026/08/11)
- [2026-08-10 (Mon)](https://www.wsj.com/news/archive/2026/08/10)
- [2026-08-07 (Fri)](https://www.wsj.com/news/archive/2026/08/07)
- [2026-08-06 (Thu)](https://www.wsj.com/news/archive/2026/08/06)
- [2026-08-05 (Wed)](https://www.wsj.com/news/archive/2026/08/05)
- [2026-08-04 (Tue)](https://www.wsj.com/news/archive/2026/08/04)
- [2026-08-03 (Mon)](https://www.wsj.com/news/archive/2026/08/03)

## (b) Barron's picks, pans, scorecard, polls, lists
Why: Barron's publishes named, dated calls and grades them itself -- the cleanest external track record to beat. Extract: ticker, buy/sell, target if stated, date.

- [Barron's stock picks page](https://www.barrons.com/market-data/stocks/stock-picks)
- [Barron's picks topic](https://www.barrons.com/topics/barrons-picks)
- [Picks-and-pans scorecard (search)](https://www.barrons.com/search?query=picks%20and%20pans%20scorecard)
- [Big Money poll (search)](https://www.barrons.com/search?query=Big%20Money%20poll)
- [Roundtable (search)](https://www.barrons.com/search?query=Barron%27s%20Roundtable)
- [10 favorite stocks for 2026 (search)](https://www.barrons.com/search?query=10%20favorite%20stocks%20for%202026)
- [10 favorite stocks for 2025 (search)](https://www.barrons.com/search?query=10%20favorite%20stocks%20for%202025)

## (c) Heard on the Street, per name (WSJ search)
Why: HOTS is WSJ's directional column; every piece on a name we hold or probe is a gradeable call. Extract: ticker, direction, horizon, quote.

- [AARD](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AARD) -- personal
- [ABSI](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20ABSI) -- personal
- [AMSC](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AMSC) -- personal
- [BHVN](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20BHVN) -- personal
- [DKNG](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20DKNG) -- personal/competition
- [HUBS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20HUBS) -- personal
- [KYTX](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20KYTX) -- personal
- [NTLA](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20NTLA) -- personal
- [PRCH](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20PRCH) -- personal
- [QUBT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20QUBT) -- personal
- [SLDP](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20SLDP) -- personal
- [SOC](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20SOC) -- personal
- [VRT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20VRT) -- competition
- [GEV](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20GEV) -- competition
- [MU](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20MU) -- competition
- [TSM](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20TSM) -- competition/probe
- [HOOD](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20HOOD) -- competition
- [NVT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20NVT) -- competition
- [AVGO](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AVGO) -- competition
- [CLS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20CLS) -- competition
- [BE](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20BE) -- competition
- [MP](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20MP) -- competition
- [LEU](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20LEU) -- competition
- [CCJ](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20CCJ) -- competition
- [NOVT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20NOVT) -- competition
- [IONQ](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20IONQ) -- competition
- [VRTX](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20VRTX) -- competition
- [WST](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20WST) -- competition
- [COGT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20COGT) -- competition
- [VKTX](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20VKTX) -- competition
- [AGIO](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AGIO) -- competition
- [RGEN](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20RGEN) -- competition
- [BBIO](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20BBIO) -- competition
- [PRAX](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20PRAX) -- competition
- [AAPL](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AAPL) -- probe
- [ADUS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20ADUS) -- probe
- [ALG](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20ALG) -- probe
- [AMZN](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AMZN) -- probe
- [ARCO](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20ARCO) -- probe
- [AVPT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20AVPT) -- probe
- [BR](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20BR) -- probe
- [CHD](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20CHD) -- probe
- [CHH](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20CHH) -- probe
- [GMAB](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20GMAB) -- probe
- [GOOG](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20GOOG) -- probe
- [GOOGL](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20GOOGL) -- probe
- [INCY](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20INCY) -- probe
- [JAZZ](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20JAZZ) -- probe
- [META](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20META) -- probe
- [MSFT](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20MSFT) -- probe
- [NVDA](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20NVDA) -- probe
- [PAGS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20PAGS) -- probe
- [PDS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20PDS) -- probe
- [SNDR](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20SNDR) -- probe
- [STNG](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20STNG) -- probe
- [TS](https://www.wsj.com/search?query=Heard%20on%20the%20Street%20TS) -- probe

## (d) MarketWatch analyst estimates + overview (earnings date), per name
Why: consensus rating, target and EPS estimates, dated -- a claim with a natural resolution (the next report). Extract: rating, mean/high/low target, next-quarter EPS estimate, earnings date.

- AARD: [analyst estimates](https://www.marketwatch.com/investing/stock/aard/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/aard) -- personal
- ABSI: [analyst estimates](https://www.marketwatch.com/investing/stock/absi/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/absi) -- personal
- AMSC: [analyst estimates](https://www.marketwatch.com/investing/stock/amsc/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/amsc) -- personal
- BHVN: [analyst estimates](https://www.marketwatch.com/investing/stock/bhvn/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/bhvn) -- personal
- DKNG: [analyst estimates](https://www.marketwatch.com/investing/stock/dkng/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/dkng) -- personal/competition
- HUBS: [analyst estimates](https://www.marketwatch.com/investing/stock/hubs/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/hubs) -- personal
- KYTX: [analyst estimates](https://www.marketwatch.com/investing/stock/kytx/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/kytx) -- personal
- NTLA: [analyst estimates](https://www.marketwatch.com/investing/stock/ntla/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/ntla) -- personal
- PRCH: [analyst estimates](https://www.marketwatch.com/investing/stock/prch/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/prch) -- personal
- QUBT: [analyst estimates](https://www.marketwatch.com/investing/stock/qubt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/qubt) -- personal
- SLDP: [analyst estimates](https://www.marketwatch.com/investing/stock/sldp/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/sldp) -- personal
- SOC: [analyst estimates](https://www.marketwatch.com/investing/stock/soc/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/soc) -- personal
- VRT: [analyst estimates](https://www.marketwatch.com/investing/stock/vrt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/vrt) -- competition
- GEV: [analyst estimates](https://www.marketwatch.com/investing/stock/gev/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/gev) -- competition
- MU: [analyst estimates](https://www.marketwatch.com/investing/stock/mu/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/mu) -- competition
- TSM: [analyst estimates](https://www.marketwatch.com/investing/stock/tsm/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/tsm) -- competition/probe
- HOOD: [analyst estimates](https://www.marketwatch.com/investing/stock/hood/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/hood) -- competition
- NVT: [analyst estimates](https://www.marketwatch.com/investing/stock/nvt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/nvt) -- competition
- AVGO: [analyst estimates](https://www.marketwatch.com/investing/stock/avgo/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/avgo) -- competition
- CLS: [analyst estimates](https://www.marketwatch.com/investing/stock/cls/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/cls) -- competition
- BE: [analyst estimates](https://www.marketwatch.com/investing/stock/be/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/be) -- competition
- MP: [analyst estimates](https://www.marketwatch.com/investing/stock/mp/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/mp) -- competition
- LEU: [analyst estimates](https://www.marketwatch.com/investing/stock/leu/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/leu) -- competition
- CCJ: [analyst estimates](https://www.marketwatch.com/investing/stock/ccj/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/ccj) -- competition
- NOVT: [analyst estimates](https://www.marketwatch.com/investing/stock/novt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/novt) -- competition
- IONQ: [analyst estimates](https://www.marketwatch.com/investing/stock/ionq/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/ionq) -- competition
- VRTX: [analyst estimates](https://www.marketwatch.com/investing/stock/vrtx/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/vrtx) -- competition
- WST: [analyst estimates](https://www.marketwatch.com/investing/stock/wst/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/wst) -- competition
- COGT: [analyst estimates](https://www.marketwatch.com/investing/stock/cogt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/cogt) -- competition
- VKTX: [analyst estimates](https://www.marketwatch.com/investing/stock/vktx/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/vktx) -- competition
- AGIO: [analyst estimates](https://www.marketwatch.com/investing/stock/agio/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/agio) -- competition
- RGEN: [analyst estimates](https://www.marketwatch.com/investing/stock/rgen/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/rgen) -- competition
- BBIO: [analyst estimates](https://www.marketwatch.com/investing/stock/bbio/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/bbio) -- competition
- PRAX: [analyst estimates](https://www.marketwatch.com/investing/stock/prax/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/prax) -- competition
- AAPL: [analyst estimates](https://www.marketwatch.com/investing/stock/aapl/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/aapl) -- probe
- ADUS: [analyst estimates](https://www.marketwatch.com/investing/stock/adus/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/adus) -- probe
- ALG: [analyst estimates](https://www.marketwatch.com/investing/stock/alg/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/alg) -- probe
- AMZN: [analyst estimates](https://www.marketwatch.com/investing/stock/amzn/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/amzn) -- probe
- ARCO: [analyst estimates](https://www.marketwatch.com/investing/stock/arco/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/arco) -- probe
- AVPT: [analyst estimates](https://www.marketwatch.com/investing/stock/avpt/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/avpt) -- probe
- BR: [analyst estimates](https://www.marketwatch.com/investing/stock/br/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/br) -- probe
- CHD: [analyst estimates](https://www.marketwatch.com/investing/stock/chd/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/chd) -- probe
- CHH: [analyst estimates](https://www.marketwatch.com/investing/stock/chh/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/chh) -- probe
- GMAB: [analyst estimates](https://www.marketwatch.com/investing/stock/gmab/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/gmab) -- probe
- GOOG: [analyst estimates](https://www.marketwatch.com/investing/stock/goog/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/goog) -- probe
- GOOGL: [analyst estimates](https://www.marketwatch.com/investing/stock/googl/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/googl) -- probe
- INCY: [analyst estimates](https://www.marketwatch.com/investing/stock/incy/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/incy) -- probe
- JAZZ: [analyst estimates](https://www.marketwatch.com/investing/stock/jazz/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/jazz) -- probe
- META: [analyst estimates](https://www.marketwatch.com/investing/stock/meta/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/meta) -- probe
- MSFT: [analyst estimates](https://www.marketwatch.com/investing/stock/msft/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/msft) -- probe
- NVDA: [analyst estimates](https://www.marketwatch.com/investing/stock/nvda/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/nvda) -- probe
- PAGS: [analyst estimates](https://www.marketwatch.com/investing/stock/pags/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/pags) -- probe
- PDS: [analyst estimates](https://www.marketwatch.com/investing/stock/pds/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/pds) -- probe
- SNDR: [analyst estimates](https://www.marketwatch.com/investing/stock/sndr/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/sndr) -- probe
- STNG: [analyst estimates](https://www.marketwatch.com/investing/stock/stng/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/stng) -- probe
- TS: [analyst estimates](https://www.marketwatch.com/investing/stock/ts/analystestimates) | [overview](https://www.marketwatch.com/investing/stock/ts) -- probe

## (e) WSJ research ratings, per name
Why: dated consensus rating and price-target range. Extract: rating counts, mean/high/low target, as-of date.

- [AARD](https://www.wsj.com/market-data/quotes/AARD/research-ratings) -- personal
- [ABSI](https://www.wsj.com/market-data/quotes/ABSI/research-ratings) -- personal
- [AMSC](https://www.wsj.com/market-data/quotes/AMSC/research-ratings) -- personal
- [BHVN](https://www.wsj.com/market-data/quotes/BHVN/research-ratings) -- personal
- [DKNG](https://www.wsj.com/market-data/quotes/DKNG/research-ratings) -- personal/competition
- [HUBS](https://www.wsj.com/market-data/quotes/HUBS/research-ratings) -- personal
- [KYTX](https://www.wsj.com/market-data/quotes/KYTX/research-ratings) -- personal
- [NTLA](https://www.wsj.com/market-data/quotes/NTLA/research-ratings) -- personal
- [PRCH](https://www.wsj.com/market-data/quotes/PRCH/research-ratings) -- personal
- [QUBT](https://www.wsj.com/market-data/quotes/QUBT/research-ratings) -- personal
- [SLDP](https://www.wsj.com/market-data/quotes/SLDP/research-ratings) -- personal
- [SOC](https://www.wsj.com/market-data/quotes/SOC/research-ratings) -- personal
- [VRT](https://www.wsj.com/market-data/quotes/VRT/research-ratings) -- competition
- [GEV](https://www.wsj.com/market-data/quotes/GEV/research-ratings) -- competition
- [MU](https://www.wsj.com/market-data/quotes/MU/research-ratings) -- competition
- [TSM](https://www.wsj.com/market-data/quotes/TSM/research-ratings) -- competition/probe
- [HOOD](https://www.wsj.com/market-data/quotes/HOOD/research-ratings) -- competition
- [NVT](https://www.wsj.com/market-data/quotes/NVT/research-ratings) -- competition
- [AVGO](https://www.wsj.com/market-data/quotes/AVGO/research-ratings) -- competition
- [CLS](https://www.wsj.com/market-data/quotes/CLS/research-ratings) -- competition
- [BE](https://www.wsj.com/market-data/quotes/BE/research-ratings) -- competition
- [MP](https://www.wsj.com/market-data/quotes/MP/research-ratings) -- competition
- [LEU](https://www.wsj.com/market-data/quotes/LEU/research-ratings) -- competition
- [CCJ](https://www.wsj.com/market-data/quotes/CCJ/research-ratings) -- competition
- [NOVT](https://www.wsj.com/market-data/quotes/NOVT/research-ratings) -- competition
- [IONQ](https://www.wsj.com/market-data/quotes/IONQ/research-ratings) -- competition
- [VRTX](https://www.wsj.com/market-data/quotes/VRTX/research-ratings) -- competition
- [WST](https://www.wsj.com/market-data/quotes/WST/research-ratings) -- competition
- [COGT](https://www.wsj.com/market-data/quotes/COGT/research-ratings) -- competition
- [VKTX](https://www.wsj.com/market-data/quotes/VKTX/research-ratings) -- competition
- [AGIO](https://www.wsj.com/market-data/quotes/AGIO/research-ratings) -- competition
- [RGEN](https://www.wsj.com/market-data/quotes/RGEN/research-ratings) -- competition
- [BBIO](https://www.wsj.com/market-data/quotes/BBIO/research-ratings) -- competition
- [PRAX](https://www.wsj.com/market-data/quotes/PRAX/research-ratings) -- competition
- [AAPL](https://www.wsj.com/market-data/quotes/AAPL/research-ratings) -- probe
- [ADUS](https://www.wsj.com/market-data/quotes/ADUS/research-ratings) -- probe
- [ALG](https://www.wsj.com/market-data/quotes/ALG/research-ratings) -- probe
- [AMZN](https://www.wsj.com/market-data/quotes/AMZN/research-ratings) -- probe
- [ARCO](https://www.wsj.com/market-data/quotes/ARCO/research-ratings) -- probe
- [AVPT](https://www.wsj.com/market-data/quotes/AVPT/research-ratings) -- probe
- [BR](https://www.wsj.com/market-data/quotes/BR/research-ratings) -- probe
- [CHD](https://www.wsj.com/market-data/quotes/CHD/research-ratings) -- probe
- [CHH](https://www.wsj.com/market-data/quotes/CHH/research-ratings) -- probe
- [GMAB](https://www.wsj.com/market-data/quotes/GMAB/research-ratings) -- probe
- [GOOG](https://www.wsj.com/market-data/quotes/GOOG/research-ratings) -- probe
- [GOOGL](https://www.wsj.com/market-data/quotes/GOOGL/research-ratings) -- probe
- [INCY](https://www.wsj.com/market-data/quotes/INCY/research-ratings) -- probe
- [JAZZ](https://www.wsj.com/market-data/quotes/JAZZ/research-ratings) -- probe
- [META](https://www.wsj.com/market-data/quotes/META/research-ratings) -- probe
- [MSFT](https://www.wsj.com/market-data/quotes/MSFT/research-ratings) -- probe
- [NVDA](https://www.wsj.com/market-data/quotes/NVDA/research-ratings) -- probe
- [PAGS](https://www.wsj.com/market-data/quotes/PAGS/research-ratings) -- probe
- [PDS](https://www.wsj.com/market-data/quotes/PDS/research-ratings) -- probe
- [SNDR](https://www.wsj.com/market-data/quotes/SNDR/research-ratings) -- probe
- [STNG](https://www.wsj.com/market-data/quotes/STNG/research-ratings) -- probe
- [TS](https://www.wsj.com/market-data/quotes/TS/research-ratings) -- probe
