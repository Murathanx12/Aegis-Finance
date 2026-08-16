# The daily surface is in, and the blocker was never what I said it was

**2026-08-16.** Phase A of `IV-ORACLE-GAP-1` has its data. Read-only, bounded,
manifested. No production path, lane, NAV, live registry or deployment touched.

---

## 1. The correction that unblocked it

I reported WRDS as unreachable and attributed it to the route:

> "wrds-pgdata:9737 AND wrds-www:443 both time out while other hosts connect,
> sandbox on and off — that is the route to Wharton, likely a campus VPN."

Two of those three facts were right and the conclusion was wrong. The check that
distinguished them cost ten seconds and I had not run it: **a fourth port.**

```
DNS  wrds-pgdata.wharton.upenn.edu -> 165.123.60.118
DNS  wrds-www.wharton.upenn.edu    -> 165.123.60.122
DNS  wrds-cloud.wharton.upenn.edu  -> 165.123.60.117

BLOCKED wrds-pgdata:9737    BLOCKED wrds-pgdata:5432    BLOCKED wrds-www:443
OPEN    wrds-cloud:22       (keyboard-interactive offered — the account exists)
```

Same /24, same instant, one port open. That is **port filtering, not a route**,
and a filtered port has a workaround a closed route does not:

```
ssh -N -L 9737:wrds-pgdata.wharton.upenn.edu:9737 murathan12@wrds-cloud.wharton.upenn.edu
```

The puller now detects such a forward and routes through it, keeping `host` as
the real WRDS name so the existing pgpass entry still matches and only
redirecting `hostaddr` — the alternative was editing Murat's credential file to
work around a networking detail, which is the wrong file to touch for that
reason.

**In the event the tunnel was not needed**: on the retry the direct route was
open and the pull ran straight through. That does not retire the finding — it
means the earlier reading ("the route is closed") was never tested against the
one observation that could distinguish route from port, and the workaround now
exists for the next time it is not open. Three hosts failing looked like one
cause and was one guess.

## 2. The month-end claim, settled from the vendor's own table

`optionm.vsurfd` does not exist. The daily surface is **per-year relations**,
`optionm.vsurfd2000 .. vsurfd2025`. Discovered, not assumed — the first query
failed on the name.

```
optionm.vsurfd2015:  404,564,776 rows   252 distinct dates   2015-01-02 .. 12-31
our optionm_vsurf_me 2015:                12 distinct dates   median gap 31 days
```

That is the vendor confirming, from the same year of the same product, that the
month-end limitation this programme reported **twice as a property of
OptionMetrics** was our own `WHERE` clause. A property of your extraction is not
a property of the data — and at 404M rows/year the bound in the puller is not an
optimisation, it is what makes the pull possible at all.

## 3. The mapping refused before it resolved

`--map` returned **2 of 18** tickers and named the other 16 as ambiguous rather
than picking. That refusal was the guard working: "lowest secid" would have been
wrong for two names.

Every ticker resolves to three kinds of row, and the vendor's own classification
columns separate them:

| kind | `index_flag` | `issue_type` | `class` | `exchange_d` | what it is |
|---|---|---|---|---|---|
| derived index | `1` | `A` | `I` / `N` | 32768 | an index ON the ETF |
| **the fund** | **`0`** | **`%`** | — | 1 or 4 | what we want |
| dead symbol | `0` | NULL | — | 0 | SPY 7571, GLD 8274 — 1990s tickers reusing the letters |

Rule: `index_flag = '0' AND issue_type = '%'` → **18/18, exactly one each.**

Cross-checked against an identifier the vendor did not choose: the surviving
cusips are `78462F10` (SPY), `78467X10` (DIA), `46090E10` (QQQ), the `4642876x`
iShares family and `81369Y**` for every Select Sector SPDR. Two independent
classifications agreeing is what makes this a derivation; either alone would be
a guess with a citation. Both the raw candidates and the rule are in the
manifest, so a later reader sees what was chosen *from*.

## 4. What was pulled

```
14 files   376,572 rows   3,523 observation dates   2006-01-03 .. 2019-12-31
6.1 MB     coords per security-date: median 6.0 in EVERY year, no partial cells
```

`3,523` is the number this trial's pre-registration declared as Phase A's
trading-day count **before a single option row existed**. The extraction matches
the registered design exactly, which is a check I would not get twice.

Per-year date counts run 250–253, the actual NYSE trading-day counts. The
puller's "under 200 dates is not daily" warning did not fire in any year.

**Named, never imputed:**

* **GLD is absent in 2006–2007** and present from 2008. GLD listed in 2004;
  its *options* did not trade until 2008, so this is the world, not the
  extraction. Any rung scored on GLD before 2008 would be scored on a security
  that had no option market.
* **EEM has 206 of 251 dates in 2006**, full coverage after.

A rung scored on a partially covered panel against one scored on a full panel is
a comparison of coverage, not of information — so these two go into the analysis
as an explicit alignment step, not as a footnote.

## 5. What has NOT happened

Phase B (2020-06-01 .. 2026-07-17) is **not pulled and not registered**. It is
reserved, calendar-disjoint by 153 days, and under R13f it will return
`ADAPTIVE_HISTORICAL_VALIDATION` rather than independent confirmation, because
WM0 read those dates. See the amendment in `docs/TRIALS/PREREG_IV_ORACLE_GAP_1.md`.

No rung has been computed. No loss has been evaluated. H1 has not been read, and
the design's own refusal — recompute the per-block dispersion on the actual
cheap-vs-IV pair, and terminate `UNPOWERED_AT_REGISTRATION` if the MDE exceeds
5.35pp — runs before it is.
