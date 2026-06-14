# TRIAL-003 — Conviction lane (Murat's decisions) vs the rules baselines

**Pre-registered:** 2026-06-14 (BEFORE any inception row exists — tamper-evidence, same pattern as TRIAL-001). **Purpose:** conviction. **Status:** pre-registered; decision-capture surface built (`POST /api/pi/conviction/decision` + `scripts/log_conviction.py`), lane not yet seeded (attended write-path session).

## Hypothesis

**Murat's discretionary decisions add value over the rules baselines.** The
conviction lane is seeded identically to the mirror lane; thereafter positions
change ONLY via Murat's logged decisions (`personal_decisions`). It answers: "does
Murat's judgment beat both his own static allocation (mirror) and the rules engine
(balanced)?" — the comparison Murat said he wanted most.

## Seeding discipline (identical to TRIAL-002 — must not deviate)

- **Inception = TODAY (2026-06-14) at CURRENT market prices, normalized to $100k.**
- Share counts ground truth; live prices at seeding → current-market-value weights.
  No historical buy prices, no invented past inception (look-ahead bias).
- Prior personal return out of scope; never in the forward record.

## Holdings (confirmed 2026-06-14, 12 names)

SOC 700 · DKNG 150 · NTLA 250 · AARD 1000 · BHVN 300 · HUBS 10 · KYTX 250 ·
PRCH 200 · QUBT 200 · AMSC 50 · ABSI 600 · SLDP 600.

## Decision capture (built 2026-06-14, `da71109`)

`personal_decisions` is immutable and forward-only: timestamp = server-now (never
backdated); a past action is flagged `late_entry`; corrections append via
`amends_id` (DB triggers forbid update/delete); rationale ≥ 50 chars; conviction
1–5; action ∈ {enter, add, trim, exit}. Logged via the endpoint or the CLI in <10s.
**The lane applies these decisions to positions — that wiring is the attended session.**

## Decision rule

- **Primary metric:** full-window net Sharpe (daily `paper_nav`), conviction lane
  vs the **balanced** reference lane (and reported vs the mirror lane).
- **Min window:** 12 months; earliest decision 2027-06-14; quarterly after.
- **Secondaries (reported, NOT deciding):** max drawdown, vol, Calmar, turnover,
  hit rate of logged decisions, attribution (selection vs timing) once `decision_outcomes` accrues.
- **No skill claim before 24 months.** Concentrated book → meaningless for months.

## Firewall note

This is a **human-judgment** lane (Murat's decisions), not an LLM lane — so the
hindsight firewall (no backtest experience feeding live decisions) does not apply
here; it applies to the future LLM-conviction lane (Goal 8/A2), which is separate.

## Registry / guards

Registered at seeding (cumulative trials → 5). Correlated with the mirror lane (same
book) — raw N is the DSR gate floor; N_eff reports the redundancy (T2). UI note as TRIAL-002.
