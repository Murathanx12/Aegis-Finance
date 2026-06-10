# Aegis Finance — V2 Goals

Claude's recommended objectives for V2, with concrete success criteria. Murat's expectations are in the final section. This is the why and what-does-success-look-like — the sequenced task plan lives in `.claude/commands/go.md` (Phase 2 stack).

---

## North star for V2

Turn Aegis from an honest baseline into an honest advantage — a tool a self-directed investor can actually act on, that improves itself only in ways it can prove out-of-sample, and that stays trustworthy precisely because it's honest about its own limits. V1 proved we can measure honestly. V2 proves the honest measurement is worth something.

The one rule that governs every goal below: **nothing ships as "it works" until a measured, out-of-sample number says so.** That discipline is the product.

---

## Theme 1 — Make it optimal and self-improving (without self-deception)

**Goal 1 — Optimized, and proven optimal.**
Replace equal-weight with leakage-safe HRP / Black-Litterman (Step #2), wired through an as-of price path, landed as a SHA-versioned config change.
*Done when:* the track record has a clean v1→v2 segment boundary and attribution shows the optimized-vs-equal-weight delta on forward (not backtest) data.

**Goal 2 — Self-improving without self-deception.**
The guarded rule-evolution loop (Step #3): propose rule changes → test on walk-forward/CPCV → adopt only survivors of DSR/PBO deflated against the cumulative trial count → record every trial (adopted and rejected).
*Done when:* the loop runs autonomously, ≥1 adopted improvement holds up forward, and the registry shows rejected trials far outnumber adopted ones.
*First candidates (parked from grind session 2026-06-10):* Ledoit-Wolf vs sample covariance comparison; vix_deep_contango threshold activation; FRED-hosted uncertainty proxies (USEPUINDXD) as GPRH replacement.

## Theme 2 — Make it honest at scale

**Goal 3 — Audit the sprawl into an honest capability map.**
Classify all ~85 services as validated / descriptive / cruft → CAPABILITY_MATRIX.md.
*Done when:* every surfaced signal is backed by a measured skill number or explicitly labeled descriptive; surface area shrinks or holds flat — never grows.

**Goal 4 — Every factor grade honestly measured, not just momentum.**
Point-in-time EDGAR fundamentals panel → Alphalens IC for Value / Growth / Profitability / Revisions at real sample size.
*Done when:* honest IC + verdict for all five factors in FACTOR_VALIDATION.md.

**Goal 5 — News as a measured flag, not a fortune-teller.**
Per-stock surprise/event detection, gated against the no-news Brier baseline.
*Done when:* it beats the baseline out-of-sample (ship as signal) or is documented as a negative result and shipped as labeled context.

## Theme 3 — Make it trustworthy and durable

**Goal 6 — End the context-loss tax.**
Optimus MCP server; Claude Code wired to it. Optimus reads Aegis (corpus + experiment registry + postmortems); it never owns Aegis's operational data.
*Done when:* a fresh session auto-loads verified state, decisions, and guardrails.

**Goal 7 — A forward track record that earns trust.**
Clean forward data accumulation; live (not replay) comparison vs SPY/AGG/60-40; PM-attribution surface. TRACK_RECORD_POLICY.md governs: the live forward NAV is the only "track record"; replay/compare are labeled methodology backtests.
*Done when:* multi-month clean live record, honest live-vs-benchmark UI, attribution on track toward the 24-month threshold — no skill claims before then.

**Goal 8 — Make judgment measurable.**
Conviction lane (Murat's real decisions, logged with rationale) and portfolio-mirror lane (Aegis manages Murat's actual holdings by its own rules from a shared inception) — attribution answers "did Aegis beat Murat on Murat's own book."
*Done when:* both lanes run with decisions logged and attributed. Honest answer pending ~24 months; a 14-position small/mid-cap book means months of divergence are statistically meaningless — no conclusions drawn early.

---

## Anti-goals — what V2 deliberately will NOT be

- Not an autonomous broker-connected trader of real money. It measures and informs; the human keeps the keys.
- Not an RL / online-learning agent optimizing on its own P&L. That learns noise and dies live.
- Not a Bloomberg / institutional-parity push. Wrong league, wrong cost model, dilutes the wedge.
- Not a feature-count arms race. Consolidation beats expansion.
- Not a maker of skill claims before the data supports them. 24-month discipline holds.

---

## Murat's additions

*(Drafted by Claude from the 2026-06-10 planning session; Murat to edit/confirm. Anything here that conflicts with the anti-goals resolves in favor of the anti-goals.)*

**A1 — Breadth: "budget JP Morgan" via tiered coverage.**
Aegis should eventually cover most US-listed stocks, not a curated few. Mechanism: Tier 2 broad coverage (analyst consensus targets, implied upside, ratings, basic risk — descriptive, near-zero compute, daily-cached via yfinance/Finnhub free tiers) across ~S&P 500 + Russell 1000 first, expanding as the data budget proves sustainable; Tier 1 deep analysis (Monte Carlo, SHAP, crash beta) for ~50–100 tickers promoted by holdings/watchlist/demand. Analyst-implied-upside runs as a registered IC trial before any signal claim — it ships as a labeled descriptive column either way, and a published negative result is itself a differentiator.

**A2 — The brain in the loop.**
Optimus is how the system "learns from mistakes": it ingests session postmortems, decision rationales, and rejected experiments — process knowledge, never weight updates from P&L. The LLM conviction lane (LLM proposes portfolio decisions using Optimus context, every decision logged, attributed against rules baselines) is the measured form of "AI managing money." Firewall: the LLM lane is forward-only; backtest "experience" is hindsight-contaminated for a model that knows history.

**A3 — Live visibility is non-negotiable.**
Reading raw JSON is not observability. The live equity-curve UI (all lanes vs benchmarks, segment boundaries, freshness state) and the one-screen health report are product requirements, not nice-to-haves. If Murat can't see the track record in one glance, the deploy isn't done.

**A4 — Event awareness.**
Any material update on a covered stock (price shock, filing, FDA/regulatory event) should reach the user with Aegis's analysis attached. Buy/sell language only if the news signal passes the Brier gate (Goal 5); otherwise labeled descriptive context. This is the path from "information hub" to "guide."

**A5 — The end state.**
A user enters or generates a portfolio; Aegis guides it: risk, crash exposure, rebalance suggestions, event alerts — every signal labeled per the capability matrix. Free and open source for adoption; the moat is the forward track record, the private brain, and the experiment registry — never the code. Paid tier (API/priority) considered only after adoption, never at the cost of the free tool being the best public option. Psychohistory is the narrative north star — sufficient data → probabilistic estimates of major market events — but it is an aspiration the validation work either earns or honestly bounds; Aegis's own measurements (12-month horizons ≈ base rates) are quoted before the aspiration is.

**A6 — Priority confirmation.**
Observability before optimization (P0 #2 before Step #2) — confirmed. The track record being visible matters more than it being optimal, because visibility is what makes everything else verifiable.

---

## What success looks like at the end of V2

Aegis is optimized and self-improving under rigorous guards; every signal it shows is either measured or honestly labeled; it has a clean multi-month forward track record honestly compared to benchmarks, visible in one glance; Murat's judgment and the LLM's judgment are both being measured against the baselines; coverage is broad where cheap and deep where it counts; and every Claude session resumes with full context. It is smaller and sharper where it counts, broader only where breadth is honest — and it can prove, with forward evidence, that it does what it says.
