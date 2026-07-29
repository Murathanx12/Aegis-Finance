# Session 2026-07-29B — sandbox build (Fable): EVENT-INTEL + FF pin + two prod catches

Murat granted full autonomy ("your sandbox"). Executed Priority A of
`ROADMAP_2026-07-29_POST_FREEZE.md` under the 2026-07-29B binding acceptance
spec, plus the adopted hardening item. Freeze untouched; nothing arms.

## Shipped (aegis-finance `b4275c2` → `e9f0880` → `987ce03`)

1. **FF vintage pin (product side)** — `b4275c2`. The research pin is
   monthly-only, so the product got its own frozen daily vintage:
   `backend/data/ff_daily_pinned.csv.gz` (FF5 daily 1963-07→2026-05-29 +
   Mom daily 1926-11→, decimal, 258 KB) + sha256 sidecar
   (`17a97adc5094…`, vintage date 2026-07-29). csv.gz deliberately, NOT
   parquet — both `.gitignore` and `.dockerignore` blanket-ignore
   `*.parquet` (the crash-model `.pkl` absent-in-prod trap). Loader:
   hash-gate (tamper ⇒ refuse + live_unpinned fallback), pinned span never
   rewritten by the live tail, provenance
   (`pinned+live_append`/`pinned_only`/`live_unpinned`/`unavailable`)
   attached to every decompose response. 10 tests.
   **Verified live:** `/api/analytics/factors/AAPL` serves
   `factor_data_provenance: {mode: pinned+live_append, sha 17a97adc…}`.

2. **EVENT-INTEL** — `e9f0880`. `backend/services/event_intel.py` +
   `/api/event-intel/{ticker}` + `/stats`, daily-brief events block,
   stock-page Events card, /dev extraction panel, `health/full.event_intel`.
   Spec compliance: direction taxonomy EXPLICIT/IMPLIED/NEUTRAL/UNKNOWN
   relative to scope; extraction tier = parse fidelity only (D4 closure —
   no outcome-confidence anywhere); LLM (spend-guarded DeepSeek) classifies
   into ENUMS only so every rendered sentence is a deterministic template —
   the no-advice playbook holds by construction, plus a scrubber for
   advice-shaped external titles; per-feed canaries (empty feed + dead
   canary = disclosed unavailable, never quiet); source integrity; context
   cards attach only measured stats with N (earnings beat_rate is the one
   measured base rate today; 8-K cards carry the §20 selection-trap note).
   26 tests. **Shakedown:** 162 live events / 18 tickers, 100% valid
   structure (bar 90%), 0 forbidden-language leaks; 3 audit-driven fixes
   (sell-off scrub false-positive; not-about-scope headlines ⇒ unknown;
   EXPLICIT restricted to realized outcomes).
   **Verified live:** AAPL 9 events (LLM path active in prod), brief served
   18 events / 5 directed with per-ticker unavailable disclosure.

3. **Daily-brief geopolitical bug** (found by recon, fixed in `e9f0880`):
   `_geopolitical_block` read `.score`/`.label` but the producer emits
   `event_score`/`interpretation` — the fields silently served None for
   weeks (None is also the legitimate unavailable value, so nothing looked
   wrong). Regression test added. **Verified live:** brief now serves
   `event_score 0.3, label "Low — no significant event risk"` — the first
   non-null values this surface ever returned.

4. **EDGAR 8-K feed was silently dead in prod** (caught by the canary on
   its FIRST live day; fixed in `987ce03`): the CIK lookup 403'd in prod
   and locally. Root cause: `edgar_events` predates the 2026-06-17
   one-choke-point convention and used its own UA with a github.io
   pseudo-contact that SEC rejects; `insider_form4._sec_get` fetches the
   same URL fine (real-contact UA + 403 retry + shared limiter). All EDGAR
   HTTP in `edgar_events` now routes through `_sec_get`. The v13-era
   `/api/events/8k` surface (zero frontend consumers) was likely dead in
   prod since birth — the second silently-dead SEC collector this
   convention has caught (insider was the first, NEG_RESULTS §5).

## Silent-fragility audit (run, clean)

No fix-now findings. Two accepted known-gaps: (a) canary verdicts cached
1h ⇒ a feed dying mid-window can read "no events" as quiet for ≤1h before
the next canary discloses it (fails toward suspect); (b)
`health/full.event_intel` zeros mean "uncalled", not "healthy" — acceptable
for an on-demand surface. /dev panel states this explicitly.

## Test state

Fast suite 3,061 green (baseline 3,025 + 36 new; later +edgar patch-target
fix, re-verified affected files 50 green). Frontend `next build` clean.

## LLM budget note

EVENT-INTEL consumes ≤1 spend-guarded call per ticker per 15 min (cached),
inside the existing 150/day cap; exhaustion degrades to keyword extraction,
disclosed via the per-event `method` field.

## Hard lines held

Descriptive-only; no buy/sell language anywhere (enforced by construction +
tests); failed feeds disclosed; freeze at 159 untouched; paper_nav paths
untouched; nothing arms — any future event→allocation wiring requires
pre-registration (CANON §6).
