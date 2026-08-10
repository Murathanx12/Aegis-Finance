# Portfolio reconciliation — what the repo already knew

_Generated 2026-08-10T17:31:45+00:00 by `scripts/reconcile_book.py`._

BUILD-1.1 finished by asking Murat to type in his holdings. He answered:
*"mirror and conviction is already my portfolio, i logged them."* He was
right. Three sources in this repo carried the book and nothing had ever
read two of them together. This is what they say, including where they
disagree.

## Sources

| source | status | what it is |
|---|---|---|
| `book_lanes` | READ | backend/data/book_lanes.yaml `holdings:` — its own header calls these share counts GROUND TRUTH, used to derive lane seed weights |
| `conviction_log` | READ | immutable personal decision log (prod, /api/pi/conviction/decisions), 12 `enter` rows dated 2026-07-11 |
| `murat_book` | READ | backend/data/murat_book.yaml — reconstructed from the January 2026 research PDF; positions are a placeholder dollar split, cost_basis is the PDF's entry price |

Conviction log payload SHA-256 `66e3adff27dd2d19b4ac144b5ab5c6d7…`, fetched 2026-08-10T16:27:20+00:00.

## The recovered book

**12 positions, all 12 share counts recovered.** 1 contested. Cost basis: 7 reconstructed, 5 missing. Cash: **UNRECOVERABLE**.

| ticker | shares | source | contested | cost basis | basis status |
|---|---:|---|---|---:|---|
| AARD | 1000 | conviction_log | no | 10 | RECONSTRUCTED |
| ABSI | 600 | conviction_log | no | — | MISSING |
| AMSC | 50 | conviction_log | no | — | MISSING |
| BHVN | 300 | conviction_log | no | 8 | RECONSTRUCTED |
| DKNG | 150 | conviction_log | no | 29 | RECONSTRUCTED |
| HUBS | 10 | conviction_log | no | — | MISSING |
| KYTX | 250 | conviction_log | no | — | MISSING |
| NTLA | 250 | conviction_log | no | 13 | RECONSTRUCTED |
| PRCH | 200 | conviction_log | no | 10 | RECONSTRUCTED |
| QUBT | 300 | conviction_log | **YES** | 13 | RECONSTRUCTED |
| SLDP | 600 | conviction_log | no | — | MISSING |
| SOC | 700 | conviction_log | no | 5 | RECONSTRUCTED |

## Disagreements — printed, not resolved

* **QUBT share count.** `conviction_log` = 300, `book_lanes` = 200, `murat_book` = 300. Using **300** from `conviction_log` — the conviction log is a dated immutable entry; book_lanes.yaml is an undated config file. **Murat should confirm which is right.**

## What is genuinely unrecoverable

* **cash** — no source records a cash balance. book_lanes.yaml normalises to a notional $100k, the conviction log records share decisions only, and murat_book.yaml carries `cash: 0` as a placeholder. An unknown cash balance is an unknown NAV.
* **cost basis for 5 names** (ABSI, AMSC, HUBS, KYTX, SLDP) — no source carries a fill price. The conviction log's `price` is the market price on 2026-07-11, the day the decisions were typed in, and the rationale says the shares were bought months earlier. Using it as a cost basis would silently invent a P&L.

## Excluded — in the January reconstruction, not in the book

The conviction log enumerates the whole book as of 2026-07-11. A name in
the January PDF but absent from that log is read as **exited**. This is
the one inference in this document rather than a reading, so it is
flagged for confirmation.

| ticker | reconstruction cost basis |
|---|---:|

## What is still needed from Murat

Two fields, and only two:

1. **`cash`** — the brokerage cash balance. Without it the NAV is the
   equity value only, and every weight is computed against the wrong
   denominator.
2. **QUBT: 300 or 200 shares?** The dated log says 300; the lane config
   says 200.

Optional but useful: fill prices for ABSI, AMSC, HUBS, KYTX, SLDP — without them
the book has no P&L for those positions, though every forward-looking
number works fine, because cost basis does not enter a decision.

Until `cash` is supplied the book stays `confirmed: false` and every
dollar figure prints **SIMULATED — DO NOT EXECUTE**.
