---
name: analyst-report-extract
description: Turn ONE sell-side / broker / Bloomberg analyst report (PDF or its converted tables) into validated, dated rows the universe and ranker can ingest — rating, price target and prior target, scenarios with probabilities, EPS revisions, key debates, dated catalysts and falsifiers — plus an operating-bridge review. Use when the owner hands over an analyst note, broker research, an initiation, a target change, or a converted file under AEGIS_DOCUMENTS/bloomberg/converted/; not for news articles, filings or transcripts.
---

# Analyst report → dated rows

Licensed content (UBS, Bloomberg, Capital IQ, any broker). **The repo is public.**
The report, its text and its extracted rows never enter git. Rows go to
`backend/data/optimus/analyst_reports/` (gitignored) or under `AEGIS_DOCUMENTS/`.
Only code and synthetic fixtures are committed. Do not send report text to a hosted
model (DeepSeek included) unless the owner has approved that report; extract by
reading it yourself or from the converted tables.

Origin: privately reconstructed from one licensed broker report and its
conversion (`AEGIS_DOCUMENTS/bloomberg/converted/MANIFEST.json`: header, scenarios,
EPS-revision, quantitative-review and financials tables). One report is a template,
not evidence of skill. It replaces the user-level `aegis-analyst-operating-bridge`
skill, whose method is step 4 below.

## 1. Bind the source (before reading a number)

- File path, SHA-256, page count, the publication date printed on the note, and
  `first_held_at` — the date the owner or the system first held it (file mtime is
  NOT that date; ask, or take it from the download/receipt record). Unknown stays
  `null`, and then the rows are `pit_safe: false` and never enter a backtest.
- `knowable_at = max(published_at, first_held_at)`. A consumer joins on this, never
  on `published_at`.

## 2. Extract these fields (unknown = `null`, never guessed)

| Field | Where it usually is | Rule |
|---|---|---|
| `rating` | front page, rating box | broker's raw label; code normalises to buy/hold/sell/unknown |
| `price_target`, `prior_price_target` | front page / "Valuation" | both, or the change cannot be computed. Code computes `target_change_pct` |
| `price_at_publication` | front page, with its price date | |
| `scenarios[]` | "Upside/Downside spectrum", bull/base/bear box | `name` ∈ upside/base/downside, `price_target`, `probability` (**often not stated → null**), `assumptions` {metric: number} |
| `eps_revisions[]` | "Old vs new estimates" table | `period`, `fiscal_context`, `eps_from`, `eps_to`, `consensus`, `pct_change_stated`; code recomputes the % and warns on a mismatch |
| `key_debates[]` | summary / "investment thesis" | one line each, paraphrased, with `page` |
| `catalysts[]` | "catalysts", "upcoming events" | `event`, `expected_date` (null if the note gives none), `date_stated_by_source` |
| `falsifiers[]` | risks, downside case, or derived | `statement`, `observable` (what is measured), `by_date`, `origin` = `source` or `aegis_hypothesis`. **At least one is required.** |

Text is a pointer, not a copy: one line, ≤ 240 characters, with the page.

## 3. Validate, then write rows

Write the extraction as JSON (same keys as
`backend/tests/fixtures/analyst_report/synthetic_report.json`) OUTSIDE the repo, then:

```
python -m scripts.analyst_report_rows validate <report.json>
python -m scripts.analyst_report_rows validate <report.json> --out backend/data/optimus/analyst_reports/rows.jsonl
```

Exit 2 = invalid; every error is listed and nothing is written. A warning (stated %
disagrees with recomputed, probabilities not summing to 1) is a finding about the
note — report it, do not edit the number. Rows are append-only and idempotent
(`row_id`). `analyst_report_rows.visible_at(rows, asof)` is the only read a
decision may use.

## 4. The operating-bridge review (research input, not a forecast)

1. Separate reported results, attributed management statements, analyst
   estimates/targets, and Aegis hypotheses. A broker's reported fact is not
   independent verification of the issuer.
2. Bridge: actual vs prior period, vs prior broker estimate, vs consensus; then each
   changed revenue / margin / FCF assumption. Code computes changes; unavailable
   comparators stay empty.
3. Valuation only when the forecast metric, multiple, EV/equity adjustments and
   diluted shares are all given; otherwise say the target's derivation is incomplete.
   A 12-month target is not a short-session forecast; a bear case is not a stop.
4. Name a dated future observation that would separate base from upside from
   downside — that is the falsifier row.

## What the rows are for, and what they are not

- The CHANGE carries information; the LEVEL does not. `signal_registry` holds
  `analyst_target_upside_xs` as CLOSED/PERVERSE (high implied upside predicted
  NEGATIVE returns). Rank on `target_change_pct`, EPS revisions and rating changes;
  never on implied upside.
- A single report is one firm's opinion. Ranker features (rating level, target
  dispersion, firm-count-normalised raises — roadmap CH-32) need many reports and a
  by-year table before anything reads them.
- Nothing here sizes a position or reaches an order.
