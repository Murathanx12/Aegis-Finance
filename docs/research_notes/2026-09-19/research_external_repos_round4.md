# Eight external tools/repos, reviewed for what Aegis should attach

Date: 2026-09-19. Read-only research task. Nothing under `C:\Users\mrthn\aegis-finance` was
modified except this file. No git commits made. No paid API calls. `.env` not read.

**Prior work read first** (per instruction, so this doesn't repeat it):
`docs/EXTERNAL_2026-09-07_FIVE_REPOS.md` — "Five external repos, reviewed for what Aegis should
port" (2026-09-07), which already did a deep read of `freqtrade`, plus `ecc`, `TradingAgents`,
`Vibe-Trading`, `OpenAlice`. **`freqtrade` is re-scoped below, not re-derived** — its section here
is a two-line pointer back to that doc's §3, which already has the architecture table, the
`minimal_roi`/exit-ladder/protections/FreqAI read, and — critically — the GPL-3.0 licence ruling
that governs today's answer too. `research_notes/2026-09-13/research_registry.md` does not exist
(checked; `research_notes/` had no `2026-09-13` subdirectory before this session).

Also read: `CLAUDE.md` Rules section (DO/DO NOT), and `docs/AEGIS_STRATEGIC_INVARIANTS.md` (16
points). The binding constraints on every recommendation below: **no LLM authority over real
capital**, **no order path in this repo** (execution lives in `aegis-alpha-terminal`, this repo
places no orders), **no database** (`backend/` is a stateless API with in-memory cache —
DO NOT list), **costs never omitted**, **PIT discipline everywhere data touches a backtest**,
and licence discipline: a **public** repo cannot absorb GPL/AGPL source without relicensing the
whole combined work (the exact ruling `EXTERNAL_2026-09-07_FIVE_REPOS.md` §3(e) already made for
freqtrade).

**What Aegis already has**, checked before recommending anything (so nothing below duplicates it):
- Backtest/farm engines: `scripts/portfolio_farm_run.py` + ~12 sibling `portfolio_farm_*.py`
  (breadth, calibrate, concentration, confidence, diagnose, paired_power, signal_power,
  subperiod, universe_audit, widened) and `scripts/night_first_books_replay.py` — a mature,
  in-house, cost-aware, walk-forward cross-sectional portfolio replay stack.
- Learner: `learner/` — a 20-file shared-trunk, multi-horizon, cross-sectional panel model
  (`encoder.py`, `neural_long.py`, `dataset.py`, `calibrate.py`, `evaluate.py`, `allocator.py`,
  `growth.py`) trained on **engineered tabular features** (49 columns) over a monthly panel —
  not a raw-K-line sequence model. This is the gap Kronos could fill (see §1).
- Scrapers: `scripts/news_pull.py` (whole-market news, GDELT/EDGAR/Alpaca/RSS fetchers dispatched
  through `backend/services/news_registry.py`'s YAML-registered sources — an id not in the
  registry is a refusal, not a silent empty pull) and `scripts/hiring_pull.py`. No BeautifulSoup,
  Playwright, or Selenium in `backend/requirements.txt` today — only `lxml`. Per S53 memory, the
  insider collector has been **403-ing on 100% of prod fetches while passing 12 green tests** —
  a live, named failure that a stealthy fetcher would directly address (see §6).
- Desktop app: `desktop/aegis_desktop.py` — a pywebview shell over the FastAPI backend + static
  Next.js export, shipped as a PyInstaller `.exe` (`build/AegisDesktop`, `dist/AegisDesktop`).
  Portfolio state is **already** browser-`localStorage`-only (`frontend/src/app/portfolio/page.tsx`,
  `aegis_holdings` key) — CLAUDE.md's "no server-side portfolio state" rule, already followed.

---

## Decision table (read this first)

| Repo / tool | What it is | Licence | Maintained? | One thing to take | Verdict |
|---|---|---|---|---|---|
| **Kronos** (`shiyu-coder/Kronos`, HF org `NeoQuasar`) | Foundation transformer for OHLCV "K-line" sequences, 4.1M–499M params | **MIT** | Yes — 39.2k★, AAAI 2026 accepted | A pretrained sequence encoder as a **new, independent arm** in `learner/` (raw-path features, not tabular) | **ATTACH_LATER** — vendor the 24.7M `Kronos-small` weights, but as `PRODUCT_EXPERIMENT` research only; it must clear the farm's own evidence bar before any book reads it |
| **freqtrade** | Mature crypto trading bot: strategy DSL, backtester, FreqAI adaptive ML, protections | **GPL-3.0** | Yes — 54.5k★, pushed yesterday | Already fully reviewed in `EXTERNAL_2026-09-07_FIVE_REPOS.md` §3 — **ideas only** (`minimal_roi`, exit ladder, protections, `do_predict` trust flag), never source | **IGNORE for copy-paste** (GPL forbids pasting into a public repo); **reference-only**, already actioned in the prior doc |
| **EskiFolio** → resolved as **Ghostfolio** (`ghostfolio/ghostfolio`) — see §3 for the resolution | Self-hosted personal wealth/portfolio tracker, Angular+NestJS+Prisma+Postgres+Redis | **AGPL-3.0** | Yes — 9.3k★, pushed yesterday | Nothing Aegis doesn't already have (localStorage portfolio page) — at most a UI reference | **IGNORE** — AGPL + Postgres/Redis server violate two CLAUDE.md rules at once (no database, no server-side portfolio state) for zero net capability |
| **NautilusTrader** | Rust-core, Python-API, nanosecond event-driven backtest/live trading engine, equities+FX+crypto adapters | **LGPL-3.0** (linking-safe, unlike GPL) | Yes — 29.1k★, pushed today, v2 Rust/PyO3 RC as of Aug 2026 | A second, independently-audited **event-driven** backtest engine (bar/tick-level fills) to cross-check `portfolio_farm`'s vectorised-monthly results on execution mechanics | **ATTACH_LATER** — `pip install nautilus_trader` (LGPL permits this in a public repo, unlike freqtrade's GPL); heavy (156 MB wheel, Python ≥3.12), so gate behind a `slow`/optional extras group, never load in the fast suite |
| **Hummingbot** | Crypto market-making/arbitrage bot + Gateway (on-chain DEX execution) | **Apache-2.0** | Yes — 20.1k★, pushed yesterday | Nothing usable — Aegis trades equities via Alpaca paper, not crypto, and the task itself flags this as an order-routing/market-making tool | **IGNORE** — out of instrument scope, and its entire value proposition (Gateway = an order path) is explicitly barred from this repo |
| **Scrapling** | Adaptive Python web-scraping framework: static + stealthy + Playwright fetchers, anti-bot bypass, self-healing selectors | **BSD-3-Clause** | Yes — 82.2k★(!), pushed yesterday, tiny (180 KB wheel core) | A `StealthyFetcher` backend for `news_pull.py`'s registry, specifically for the sources that currently 403 | **ATTACH_NOW** — permissive licence, small core, directly answers a named live failure (insider collector 403s) |
| **Osiris** (`simplifaisoul/osiris`) | Next.js/MapLibre real-time OSINT map dashboard (flights, CCTV, seismic, news, conflict zones) | MIT (repo says so) | Nominally — 9.7k★, pushed today | Nothing safe to take as-is | **IGNORE** — repo description carries an embedded `pump.fun` token contract address and a paywalled "RedTeam Console"; treat as an unaudited, monetisation-motivated project. See §7 |
| **Xfield / "$50,000 to clone"** | Unidentified | — | — | — | **CANNOT IDENTIFY** — reported honestly below (§8), not guessed |

---

## §1. Kronos (`NeoQuasar` / `shiyu-coder/Kronos`)

**What it is.** "The first open-source foundation model for financial candlesticks (K-lines)",
trained on OHLCV sequences from 45+ global exchanges (the README's stated training set mixes
China A-share and BTC/USDT; the exact split isn't published). Architecture: a specialised
tokenizer quantises continuous multi-dimensional K-line data into hierarchical discrete tokens,
then an autoregressive decoder-only Transformer is pretrained on the token stream — i.e. it
treats a candlestick sequence the way a language model treats tokens, and can be sampled forward
for a probabilistic multi-step price-path forecast. Four sizes: `Kronos-mini` (4.1M),
`Kronos-small` (24.7M), `Kronos-base` (102.3M) on Hugging Face/GitHub; `Kronos-large` (499.2M) is
**not** open-sourced. Accepted at AAAI 2026.

**Licence.** MIT (`LICENSE` in the repo). Free to vendor, modify, and redistribute with
attribution — the cleanest licence of the eight.

**Maintenance.** `shiyu-coder/Kronos` (39,213★, 6,531 forks, MIT, pushed 2026-04-13) is the
canonical repo — not `NeoQuasar/Kronos` (that GitHub org doesn't exist; `NeoQuasar` is the Hugging
Face org the weights are published under). `peiking88/Kronos` is a zero-star fork, not the source.
Python: no `requires_python` published (it is not a PyPI package) — install is `git clone` +
`pip install -r requirements.txt`, then `from model import Kronos, KronosTokenizer,
KronosPredictor` from inside the cloned tree. Install size dominated by the weights: `Kronos-small`
+ `Kronos-Tokenizer-base` together are well under 500 MB (24.7M-param model in fp16/bf16 is
roughly 50 MB of weights; the tokenizer is smaller).

**The one thing Aegis could take.** Aegis's `learner/` is entirely **tabular, cross-sectional,
engineered-feature** (49 hand-built columns fed to LightGBM/a shared-trunk neural net — see
`learner/encoder.py`'s own docstring). It has never modelled a raw price-path sequence directly.
Kronos is a pretrained **sequence encoder** that could sit in `learner/` as a genuinely different
arm — an embedding of "what did the last N candles look like" that gets concatenated onto the
existing 49-column feature vector, or scored as its own independent selector per CLAUDE.md's
BOTTLENECK rule ("a new mechanism arrives as its own book, never a weight folded into
`arena_composite`"). **What it must NOT be used for**: it must not be treated as an oracle that
outputs a tradeable signal on day one — the repo publishes no equity-curve/Sharpe backtest at all
(only next-bar reconstruction-style demos), so under CLAUDE.md's three licences this enters as a
`PRODUCT_EXPERIMENT` at best, and specifically it must not skip the farm's own cost/PIT/multiplicity
gates just because the weights are pretrained elsewhere — a foundation model's training corpus is
itself a potential PIT leak (if China A-share + BTC training data overlaps in time with any period
Aegis backtests on US equities, that's not leakage in the technical sense across markets, but the
model's *general* sense of "what a plausible candle sequence looks like" was shaped by data whose
dates need to be checked against every backtest window before any claim is made).

**Attach recipe.**
```
git submodule add https://github.com/shiyu-coder/Kronos.git third_party/kronos
# OR (no git history bloat from a 39k-star repo):
git clone --depth 1 https://github.com/shiyu-coder/Kronos.git /tmp/kronos_src
cp -r /tmp/kronos_src/model third_party/kronos_model   # vendor just the model/ package
pip install -r third_party/kronos_model/requirements.txt   # torch, einops, etc.
```
Adapter file: `learner/kronos_encoder.py` (~15 lines):
```python
# learner/kronos_encoder.py
from third_party.kronos_model import Kronos, KronosTokenizer, KronosPredictor
import numpy as np

_TOK = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
_MODEL = Kronos.from_pretrained("NeoQuasar/Kronos-small")
_PREDICTOR = KronosPredictor(_MODEL, _TOK, max_context=512)

def kronos_embedding(ohlcv_df, as_of_timestamp) -> np.ndarray:
    """PIT-safe: caller must pre-slice ohlcv_df to rows strictly before as_of_timestamp.
    Returns a fixed-width vector (last hidden state or a short forecast) to
    concatenate onto learner/encoder.py's 49-column feature matrix."""
    # NOTE: do not call predictor.predict() with y_timestamp in the future of
    # as_of_timestamp during a backtest -- that is the model's own generation head,
    # not a feature; use it as an encoder, not a forecaster, until it has cleared
    # a pre-registered trial.
    ...
```
**What a human must do by hand**: nothing requiring credentials — weights download anonymously
from Hugging Face on first `from_pretrained()` call (no API key). A GPU is optional but the
104M/499M variants are slow on CPU; `Kronos-mini`/`-small` run on CPU in the fast test suite's
budget if ever unit-tested, but any real backtest run belongs in the `slow` marker, network-gated
like every other yfinance-shaped call.

**Verdict: ATTACH_LATER.** MIT licence and a real, differentiated capability (sequence modelling
Aegis has never had) argue for pulling it in — but "later" because it needs a `pre-register-trial`
pass before it touches any book, and the vendored `third_party/kronos_model/` directory needs its
own entry in `signal_reachability.py` per CLAUDE.md's "give every new module a caller or classify
it" rule the day it lands, not after.

---

## §2. freqtrade — pointer, not a re-review

Fully covered in `docs/EXTERNAL_2026-09-07_FIVE_REPOS.md` §3 (attach table with 13 rows, `(h)`
what-not-to-copy list). Restating only what changed the calculus for *this* round: Murat's
instruction this time was "just copy-paste it" — **that specific instruction cannot be honoured
for freqtrade**. `LICENSE` is GPL-3.0 (confirmed again today: `license.spdx_id == "GPL-3.0"` via
the GitHub API, HEAD pushed 2026-09-18, 54,512★). Aegis-Finance is a public repo; pasting any
GPL-3.0 source file into it — even one function — obligates the combined repository to GPL-3.0.
That is a licence change nobody has approved. The prior doc's answer stands: **reimplement the
named ideas** (`minimal_roi` time-decayed exit curve, the ranked exit ladder, `IProtection`
circuit breakers, FreqAI's `do_predict` trust flag, the published fill-assumption list) **from the
English description, never from the file**. No new action here; verdict unchanged: **IGNORE for
copy-paste, reference-only** (already actioned).

---

## §3. "EskiFolio" — name resolution, then the tool

**Resolution.** No GitHub repository, org, user, or package named `eskifolio` (or close spellings)
exists — confirmed via `GET /search/repositories?q=eskifolio` returning `total_count: 0`. This is
almost certainly a mis-transcription. Two real open-source portfolio trackers exist that the name
could be pointing at: **Ghostfolio** (`ghostfolio/ghostfolio`, the closer phonetic match —
"[Gh]ost-folio" vs "[Esk]i-folio" share the "-folio" suffix and syllable count, which is the kind
of thing a speech-to-text pass mangles) and **Wealthfolio** (a smaller, local-first Rust/Tauri
alternative surfaced in the same search results). **Confidence: medium (∼55%) that Ghostfolio is
meant**; noting Wealthfolio as the alternate candidate rather than guessing silently. Proceeding
with Ghostfolio as the primary answer below; if wrong, the corrective is cheap (Wealthfolio is
architecturally similar — self-hosted, portfolio-tracking, not a signal source).

**What it is.** Ghostfolio — "Open Source Wealth Management Software" (repo description),
Angular + NestJS + Prisma + Nx + TypeScript, self-hosted, tracks stocks/ETFs/crypto net worth and
computes performance metrics (TWR, X-ray allocation, FIRE calculator). Not a signal-generation or
backtesting tool — a personal dashboard.

**Licence.** **AGPL-3.0** (`license.spdx_id`) — the strictest copyleft of the eight (network-use
clause: even running a *modified* Ghostfolio as a network service, without distributing the
binary, triggers the source-disclosure obligation). Confirmed 9,315★, pushed 2026-09-18.

**Maintenance.** Active, TypeScript, Nx monorepo. No published Python version (not a Python
project); requires Node.js, PostgreSQL, and Redis to self-host (`docker-compose.yml` in the repo).

**The one thing Aegis could take, and what it must NOT be used for.** There is genuinely little
to take: Aegis already ships a portfolio page (`frontend/src/app/portfolio/page.tsx`,
`portfolio-intelligence/my-portfolio/page.tsx`) that stores holdings in browser `localStorage` —
exactly the CLAUDE.md rule ("Store portfolio state server-side" is a DO NOT). Ghostfolio's entire
architecture is the opposite: a server-side Postgres database of holdings, which is a second
CLAUDE.md DO NOT ("Add a database — this is a stateless API with in-memory cache") stacked on top
of the AGPL problem. At most, its X-ray/allocation-breakdown **UI concept** could be referenced
(not copied) when redesigning the existing localStorage portfolio page. It must not be deployed as
a service that talks to `backend/`, integrated into the FastAPI app, or have its source pasted
anywhere in this repo.

**Attach recipe, if Murat still wants a personal net-worth tracker.** Run it **outside** Aegis-Finance
entirely, as an unrelated self-hosted app on the same machine, never imported into this codebase:
```
git clone https://github.com/ghostfolio/ghostfolio.git   # OUTSIDE this repo, e.g. C:\Users\mrthn\ghostfolio
docker compose --env-file .env.docker -f docker/docker-compose.yml up -d
```
**By hand**: create a Postgres volume, set `ACCESS_TOKEN_SALT`/`JWT_SECRET_KEY` env vars, and
optionally an external market-data API key (Ghostfolio defaults to Yahoo Finance, keyless for
basic use). This is a completely separate personal tool, zero code shared with Aegis.

**Verdict: IGNORE** (for attachment to this repo). Zero incremental capability over what already
exists, AGPL-3.0 forbids folding it into a public repo without relicensing, and its own database
requirement conflicts with a standing DO NOT. If Murat wants it as a personal, unrelated app, that
is a one-line docker-compose decision with no bearing on Aegis-Finance and does not belong under
`third_party/`.

---

## §4. NautilusTrader (`nautechsystems/nautilus_trader`)

**What it is.** "Production-grade Rust-native trading engine with deterministic event-driven
architecture" — a backtest AND live-trading engine (same code path for both, the project's core
design claim) with nanosecond-resolution timestamps, a `ParquetDataCatalog` for historical data,
and adapters for equities, futures, FX, and crypto venues (Interactive Brokers, Databento, Binance,
Bybit, etc.). Rust core exposed to Python via PyO3; strategies are authored in Python.

**Licence.** **LGPL-3.0** (`license.spdx_id`) — materially different from freqtrade's GPL-3.0.
LGPL is designed exactly for this use case: a library that a proprietary or differently-licensed
application can **import and use unmodified** (`pip install nautilus_trader`, `import
nautilus_trader`) without forcing the importing application's own source to relicense. The
obligation only attaches if Aegis modifies NautilusTrader's own source and redistributes that
modified version. **This means Murat's "just copy-paste it and use it" instruction *is* honourable
here, in the specific sense that pip-installing and importing it is fully compliant** — unlike
freqtrade, there is no licence reason to avoid it.

**Maintenance.** Very active — 29,114★, 3,834 forks, 134 open issues, pushed **today**
(2026-09-19). Per web search, the project shipped its "final 1.x release" (legacy Cython core) on
2026-08-02 and is moving to a Rust+PyO3 v2 core, currently release-candidate for Python strategy
authoring, backtesting, and live operation. Python: `requires_python: <3.15,>=3.12` — **stricter
than Aegis's own floor**; worth checking `backend/requirements.txt` / CI's Python version before
counting on this (if Aegis's CI runs 3.11, this cannot be added without a Python bump or an
isolated venv). Install size: the macOS arm64 wheel alone is **156 MB** (Rust binary bundled) —
by far the largest of the eight tools reviewed; this must never load in the fast/offline test
suite (CLAUDE.md's "~4090 tests, 2-7 min" budget) and belongs behind an optional extras group.

**The one thing Aegis could take.** An **independent, event-driven (bar/tick-level fill
simulation) backtest engine** to cross-check `portfolio_farm_run.py`'s results on execution
mechanics specifically — fill timing, partial fills, multi-venue order lifecycle — none of which
`portfolio_farm` (a monthly cross-sectional replay, per its own doc references to "walk-forward
temporal splits") models at that granularity. This is the same role freqtrade's backtester plays
in the prior review's §3, but importable without a licence fight. Candidate use: replay the
30-minute lane-D book (mentioned in project memory, S53 chunk 3c) through NautilusTrader's
`BacktestEngine` as a second opinion, not a replacement.

**What it must NOT be used for.** Its live-trading adapters (Interactive Brokers, Binance, Bybit,
etc.) are an **order path** — explicitly out of scope for this repo per the task instruction and
per the FOUR-REPOSITORIES table in CLAUDE.md (execution lives in `aegis-alpha-terminal`). If
NautilusTrader's execution layer is ever wanted, it belongs in the *terminal* repo's own review,
not here, and even there it would compete with the existing Alpaca-based execution loop rather
than replace it casually.

**Attach recipe.**
```
pip install nautilus_trader   # LGPL-3.0: permitted, unmodified use in a public repo
```
Given the 156 MB wheel and the Python ≥3.12 floor, put it in a **separate optional requirements
file** rather than `backend/requirements.txt`:
```
# requirements-nautilus.txt (NEW file)
nautilus_trader>=1.231.0,<2
```
Adapter file: `scripts/nautilus_crosscheck.py` (~15 lines of pseudocode):
```python
# scripts/nautilus_crosscheck.py
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.persistence.catalog import ParquetDataCatalog

def crosscheck_book(book_id: str, start, end):
    """Replay one already-frozen book's bar data through Nautilus's fill
    simulator and diff its per-trade P&L against portfolio_farm's own replay.
    Read-only: never writes to paper_nav, never places an order."""
    catalog = ParquetDataCatalog(f"backend/data/optimus/nautilus_catalog/{book_id}")
    engine = BacktestEngine()
    # ... load the book's frozen strategy contract, translate to a minimal
    # Nautilus Strategy that only emits the SAME entries/exits the book already
    # took (no new signal generation), run, diff fills against the book's ledger.
    return diff_report
```
**By hand**: nothing needs credentials for the backtest path (historical bars can come from
Aegis's own parquet, converted to `ParquetDataCatalog` format with the bundled CLI). A Databento
or Interactive Brokers key is only needed if Murat wants Nautilus's *own* data adapters instead of
feeding it Aegis's existing data — not required for the cross-check use case.

**Verdict: ATTACH_LATER.** No licence blocker (rare among the eight), but it is a 156 MB, Python
≥3.12 dependency whose only clear job today is a cross-check nobody has asked for yet — bring it
in as the optional `requirements-nautilus.txt` extra when the 30-minute lane-D book (or any book
where fill-timing precision matters) actually needs a second opinion, not before.

---

## §5. Hummingbot (`hummingbot/hummingbot`)

**What it is.** Open-source high-frequency **crypto market-making and arbitrage** bot: a Python
client plus "Gateway", a middleware service that holds private keys and submits orders directly to
on-chain DEXs (AMM/CLMM pools) and CEX order books across many venues.

**Licence.** Apache-2.0 (permissive — no licence blocker). 20,053★, pushed 2026-09-18. Python
`requires_python: >=3.10.12`; PyPI wheel is a modest 4.5 MB (the bulk of the system is the
separate Gateway Node.js service, not counted in the Python wheel).

**The one thing Aegis could take — there isn't one worth the exposure.** Everything of value in
Hummingbot (its connector abstraction, its strategy templates) is aimed at market-making spread
capture and DEX arbitrage, neither of which appears anywhere in Aegis's mission (equities,
risk-adjusted or risk-seeking terminal wealth per a declared utility — see CLAUDE.md's Mission
section). **What it must NOT be used for** is explicit in the task instructions themselves: order
routing and crypto market making. Gateway *is*, structurally, an order path with custodied private
keys — the single sharpest violation available of "no order path in the research repo" and "no LLM
authority over real capital" (an LLM-adjacent agentic strategy calling Hummingbot's Condor harness,
per the 2026 search results, would put an LLM one hop from a signed transaction).

**Attach recipe.** None recommended. If a future, clearly-scoped need for crypto execution ever
arises, that decision belongs in `aegis-alpha-terminal` (the execution repo) with its own attended
review — never silently in Aegis-Finance.

**Verdict: IGNORE.** Wrong instrument class, wrong repo (order path), and the task's own framing
already flags it as the thing to identify-and-reject.

---

## §6. Scrapling (`D4Vinci/Scrapling`)

**What it is.** "An adaptive Web Scraping framework" — a parsing layer (`page.css(...)`,
`page.xpath(...)`) plus four fetcher backends of increasing stealth: `Fetcher` (fast HTTP with TLS
fingerprinting), `StealthyFetcher` (browser automation with anti-detection / claims to bypass
Cloudflare Turnstile), `DynamicFetcher` (full Playwright), and session-persistent variants of each.
Its headline feature is "Smart Element Tracking" — selectors that auto-relocate after a site's DOM
changes, using similarity matching instead of breaking on the next layout tweak.

**Licence.** **BSD-3-Clause** — fully permissive, no attribution-in-source obligation beyond the
licence file, safe to vendor or pip-install in a public repo without any combined-work concern.

**Maintenance.** 82,202★(!) — by a wide margin the most starred repo in this whole review,
including the five from 2026-09-07 — 8,369 forks, pushed **yesterday** (2026-09-18), only 6 open
issues (unusually low for that star count, suggesting an actively-triaged issue tracker). Python
`requires_python: >=3.10`. Core wheel is tiny (**180 KB**) — the base install
(`pip install scrapling`) is parser-only; `pip install scrapling[fetchers]` pulls in the browser
automation stack (Playwright/Camoufox-class dependencies), which is where the real weight lives
and should be treated like Aegis's existing Playwright-adjacent guard (network-blocked in the fast
suite, `slow`-marked).

**The one thing Aegis could take.** A `StealthyFetcher`/`DynamicFetcher` backend for
`scripts/news_pull.py`'s source registry (`backend/services/news_registry.py`), specifically for
sources that reject Aegis's current `urllib`-based `_http_get` (`scripts/news_pull.py:264`) — the
insider collector's **100% 403 rate in production while its 12 unit tests stay green** (per
project memory S53, this is a named, live, unresolved failure, exactly the silent-fragility shape
CLAUDE.md's skill list exists to catch). Scrapling's fingerprint spoofing and Cloudflare-class
bypass is a direct, targeted fix, not a speculative one.

**What it must NOT be used for.** Scrapling is a **fetch/parse** tool; it must not become an
alternate discovery path that bypasses `news_registry.py`'s refusal-on-unknown-id gate, and its
output must still be dated/PIT-graded through the same `pit_grade` machinery
(`native_stamp`/`first_seen_only`/`index_state`) every other source uses — a scraped page has no
special exemption from invariant 20 (index-state feeds never get `label_source: true`).

**Attach recipe.**
```
pip install "scrapling[fetchers]"   # BSD-3-Clause; add to backend/requirements.txt
scrapling install   # post-install step Scrapling ships to fetch browser binaries -- run once, by hand, not in CI
```
Adapter file: `backend/services/fetchers/scrapling_fetcher.py` (~15 lines) registered as a new
fetch strategy alongside `fetch_gdelt`/`fetch_edgar`/`fetch_alpaca` in `scripts/news_pull.py`:
```python
# backend/services/fetchers/scrapling_fetcher.py
from scrapling.fetchers import StealthyFetcher

def fetch_stealthy(src, ctx) -> "FetchResult":
    """Drop-in replacement for scripts/news_pull.py::_http_get for one
    registry source at a time -- named in the registry as parser=..., never
    a silent global switch. Still runs through the SOURCE_BUDGET_S timeout
    and the existing PIT-grade + refusal-on-unknown-id path."""
    page = StealthyFetcher.get(src.url, timeout=45_000)
    return FetchResult(raw=page.body, status=page.status, fetched_at=_now())
```
**By hand**: run `scrapling install` once locally (and in the CI image, as a build step — not a
runtime call) to download the bundled Camoufox/Playwright browser binary; no API keys, no logins.
The only manual judgement call is *which* registry sources get switched to the stealthy fetcher —
that should be a deliberate per-source registry edit (`backend/data/news_sources.yaml`), not a
blanket swap, since the stealthy path is slower and heavier than the plain HTTP one.

**Verdict: ATTACH_NOW.** Permissive licence, tiny core footprint, directly answers a named,
currently-unsolved production failure (the insider-collector 403s), and the attach is genuinely a
`pip install` + one new fetcher function — the closest thing among the eight to what Murat actually
asked for ("download it and make it attached... don't remake it").

---

## §7. Osiris (`simplifaisoul/osiris`)

**What it is.** A Next.js 16 / TypeScript / MapLibre GL real-time "global intelligence dashboard" —
16 toggleable map layers (flight tracking via ADS-B, maritime AIS, CCTV camera feeds, USGS
earthquake data, wildfire, weather, space/satellite tracking, 23 live news broadcasts, a
Telegram-OSINT geoparsing layer, and a "RECON toolkit" doing port scanning / DNS / WHOIS / SSL
inspection / crypto-wallet OFAC-sanctions cross-checking). Positioned explicitly as "A Palantir
Alternative." Runs client-heavy (WebGL rendering in-browser) with a small (~220 MB Docker image)
or Node.js backend; "works partially without any API keys."

**Licence.** MIT, per `license.spdx_id` — permissive on paper.

**Maintenance and a real red flag.** 9,665★, 1,999 forks, 312 commits, pushed **today**
(2026-09-19) — numerically healthy. But **the repository's own GitHub description field carries an
embedded Solana `pump.fun` token contract address**
(`2nZNHm3Lr9umG3DVrzYwHgktwkuKuJRXqqRqs3ewpump` — the `pump` suffix is the pump.fun vanity-address
signature), and multiple near-identical forks/clones on GitHub (`ZEZE1020/osiris-ai`,
`cristiannegru/osiris`) carry the **same** description text verbatim, which is the shape of a
coordinated token-promotion campaign riding on a plausible-looking open-source project rather than
organic forking. The repo also gates a "Special OSIRIS Console" / "RedTeam Console" behind a
Patreon paywall, and bundles OFAC-sanctions and crypto-wallet-intelligence tooling inside an
otherwise-MIT-licensed public dashboard — a combination that raises more questions about the
maintainer's actual incentives than it answers about code quality. No CVE or malware report was
found in this pass, but **none was specifically looked for either** — this verdict is "don't trust
the supply chain," not "confirmed malicious."

**The one thing Aegis could take, and what it must NOT be used for.** The *idea* — fusing many
public sensor feeds (flights, seismic, news, weather, satellite) into one situational dashboard —
loosely rhymes with the VISION file's "whole-market news, Asia first" sensor framing, but nothing
in Osiris is finance-specific and nothing here should be pulled into an execution- or
capital-adjacent codebase from a project whose own README is doing crypto-token marketing. It must
not be `npm install`ed, Docker-pulled, or have any of its code read into Aegis's dependency tree
given the token-promotion pattern; if the dashboard concept is wanted, it should be **reimplemented
from the public data-source list only** (NASA, USGS, OpenSanctions were cited as legitimate
upstream sources in the README), never by importing Osiris's own package.

**Attach recipe.** None recommended.

**Verdict: IGNORE.** The idea (many-sensor fusion dashboard) is not without merit, but the
specific artefact is an unaudited repo whose own marketing embeds a speculative-token address —
exactly the kind of supply-chain trust question CLAUDE.md's discipline (silent-fragility-audit,
never trust a green test alone) exists to flag before code, not after.

---

## §8. "Xfield — they offer $50,000 to clone their software"

**Could not identify this with any confidence, and I am saying so rather than guessing.**
Searched: `"Xfield" $50,000 clone software`, `"xfield" reddit "clone this" OR "$50k"`, `"Xfield"
startup Y Combinator`, `"Xfield" AI agent SaaS Hacker News`, and checked the most plausible
literal domain, `xfield.ai` — that domain resolves to a **GoDaddy parked-domain page**
(`window.LANDER_SYSTEM="PW"`, GoDaddy's `wsimg.com` parking-lander script), i.e. no live product
sits there today. Other "Xfield" hits found (a mobile arcade game "XField Score Up", a New Zealand
aviation-maintenance-software reseller "Xfield Trading Limited" trading as Skatermate/Trails AMS, a
geophysical-modelling plugin by dGB Earth Sciences, an FCC-allocation tool by V-Soft, a gemstone
shop in Alberta) share only the name and none plausibly matches "a company offering $50,000 to
clone their software." An `X/Twitter` account `@XfieldAi` exists (joined Jan 2025) but returned no
usable content through search. **No entity found matches the description.** If Murat has a URL,
screenshot, or more specific context (which platform he saw the offer on, roughly when, what the
software does), that would resolve this in one more search pass — worth a follow-up ask rather than
a guess, given the size of the number involved.

---

## Summary of attach actions, in order of effort

1. **Scrapling** — `pip install "scrapling[fetchers]"`, add one fetcher function to
   `scripts/news_pull.py`'s registry path, targeted first at the insider-collector 403s. Smallest,
   highest-confidence win; BSD-3-Clause, no licence question.
2. **NautilusTrader** — `requirements-nautilus.txt` as an optional extra, used only when a book
   needs a second-opinion, fill-level backtest cross-check. LGPL-3.0 permits the import; the cost
   is size (156 MB) and a Python ≥3.12 floor to verify against Aegis's CI first.
3. **Kronos** — vendor `Kronos-small` + its tokenizer under `third_party/`, wire as a new
   `learner/` arm, run it through `pre-register-trial` before any book reads its output. MIT, but
   the effort is in the evidence gate, not the install.
4. **freqtrade, Ghostfolio, Hummingbot, Osiris** — no action. Three different disqualifiers
   (GPL/AGPL licence, wrong instrument class + order path, unaudited token-promotion supply
   chain) each independently sufficient.
5. **Xfield** — unresolved; ask Murat for more context rather than guess.
