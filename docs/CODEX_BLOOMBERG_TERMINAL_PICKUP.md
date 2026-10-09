# Bloomberg Terminal visit: inputs for Codex

Owner confirmed Oct 9 that Terminal access will be available later this week.
Codex verified all 13 drills; the live gate still refuses missing WLS. This
checklist is not an order sheet or a final strategy decision.

## Files to bring back

1. Open WLS Index and `MEMB <GO>`. Export complete membership as CSV or Excel,
   retaining Bloomberg tickers **with exchange codes**, WLS identity and date.
   Save the unchanged original in `backend/data/optimus/contest/wls/`, e.g.
   `WLS_MEMB_2026-10-09.xlsx`. Keep introductory rows/sheets for inspection;
   do not substitute another universe or export just the visible page.
2. Save current TMSG Help/T&C pages with challenge year, capture time and
   source section. Keep account-bearing originals privately; supply sanitized
   rule evidence. No credentials or account identifiers in public Git.
3. Identify the actual order/blotter/fill export format. A sanitized sample or
   column list is useful. Do not place an order solely to create test data.

## Questions the current rules must settle

- Fill prices/times; supported order types; gaps, halts and unfilled orders.
- Commissions/fees; sale-proceeds availability and settlement restrictions.
- Position-cap denominator and whether it applies at entry or continuously.
- Cash/full-investment requirements, initial deadline, re-entry/trade limits.
- Non-US eligibility, local-session fills, FX and board lots.
- Exact Relative P&L and benchmark; dividends, splits and final valuation.

Record a source page/section beside each answer. Unanswered items stay unknown.
The fuller existing list is `CONTEST_RUNBOOK_2026-10.md`, page 2; its assumptions
are not controlling rules.

## Codex execution after the visit

1. Inspect source files and record provenance/hash/time. Validate membership:

   ```powershell
   .venv\Scripts\python.exe -m scripts.contest_rehearsal gate --mode contest
   ```

2. Reconcile confirmed rules; rerun the decision-critical ROT5_TRAIL versus
   MAXTAIL_BH comparison with independent review. Explicitly record the
   supported choice in `contest/live/BOOK`.
3. Check every drill verdict, then produce a dated Oct 12 dry preview using
   authentic membership and current inputs. A preview is not a frozen order.
4. After authorized actual Terminal entry, validate its export format and run:

   ```powershell
   .venv\Scripts\python.exe -m scripts.contest_rehearsal verify --mode contest --date YYYY-MM-DD --entered C:\path\to\actual_blotter.txt
   ```

   The verifier checks entered tickets against that day's frozen sheet. A
   match does not prove execution; preserve separate actual fill evidence.
   Never invent fills or reconstruct forward rows.

Registration, membership, rules, selected policy and verified fills remain
separate facts. No live BOOK was chosen by this checklist.
