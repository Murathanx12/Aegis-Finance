# The paper fleet — who owns what, measured 2026-09-22

**This file is the authority on which brokerage accounts exist and who executes
into them.** Every dated `HANDOFF_*` / `BUILD_*` doc that mentions `hack3` is a
diary entry from before 2026-09-22 and is not a source of truth (CLAUDE.md:
"Dated handoffs are in `docs/archive/` and are a diary"). 138 such references
exist; none of them were rewritten, because rewriting history is how a programme
loses the ability to audit itself.

## The measurement, not the memory

Read from `/v2/account` and `/v2/positions` at 2026-09-22 12:05 HKT:

| account | number | equity | cash | positions | last order | vs $100k start |
|---|---|---:|---:|---:|---|---:|
| hack1 | PA3WXDS3MJ53 | $95,754 | $22,003 | 3 | 2026-09-09 | **−4.2%** |
| hack2 | PA33ON4NRJAX | $98,820 | $98,820 | 0 | 2026-09-04 | **−1.2%** |
| hack3 | PA3JYEG4DF9G | $80,821 | $11,816 | 9 | 2026-09-18 | **−19.2%** |
| hack4 | PA3R9XHMCVDA | $89,437 | $15,412 | 4 | 2026-09-21 | **−10.6%** |
| hack5 | PA3T8OTGULCD | $93,704 | $87,044 | 3 | 2026-09-14 | **−6.3%** |
| hack6 | PA3I816FLXE9 | $85,201 | **−$5,388** | 16 | 2026-09-17 | **−14.8%** |

**Fleet total $543,738 of $600,000 — down 9.4%. Every one of the six is down.**

Two lines deserve reading twice:

* **hack6 holds negative cash (−$5,388).** Negative cash on a brokerage account
  is margin. A book that was never supposed to lever is levered, and nothing in
  the fleet's own code noticed. `pc_broker.MAX_INVESTED_FRAC <= 1.0` is asserted
  at import precisely so the PC book cannot repeat this, and
  `test_gross_exposure_never_exceeds_equity` pins it.
* **hack2 has been 100% cash since 2026-09-04.** It is not losing money because
  it is not doing anything. An idle account is not a conservative account; it is
  an account whose mandate silently stopped.

## What changed on 2026-09-22

* **The Railway loop `aat-loop-hack3` was removed** (`railway down --service
  aat-loop-hack3`). Its last act, at 2026-09-21T22:03Z, was
  `submitted long_shares BE` — it was a live executor, not a dormant service.
  The service and its volume still exist; only the deployment is gone, so it is
  restored by a `railway up`, not by a rebuild.
* **Murat deleted hack3** as a book. **But the Alpaca account PA3JYEG4DF9G still
  answers `/v2/account` and still holds 9 positions worth ~$69k.** Deleting the
  Railway service does not close the brokerage account, and closing a book in
  one's head does not either. If those positions are meant to be gone, they have
  to be sold or the account closed at Alpaca. This is written down because the
  gap between "I deleted it" and "it still answers" is exactly the shape of
  [[feedback-verify-the-persistence-claim]].
* **Six revoked credentials were removed from `aegis-finance/.env`**:
  `ALPACA_API_KEY_ID`/`_SECRET_KEY`, `ALPACA_ARENA_*`, `ALPACA_LANE_D_*`. All
  three pairs answered **HTTP 401** when probed, and `scripts/connection_check.py`
  had already recorded them as `alpaca_revoked` back in Session 36 — so the code
  knew they were dead while the file still carried them. Backup:
  `.env.bak_before_cleanup_2026-09-22`.
* `ANTHROPIC_API_KEY=` (empty) was **deliberately left in place.** CLAUDE.md
  documents it as a known, handled condition with `test_llm_provider_declaration.py`
  pinning the declaration; removing it risks a pinned test to tidy one line.

## The execution-owner rule

> **One account, one execution owner.** Two executors on one account do not
> produce a blended strategy; they produce a track record that means nothing.

This is enforced, not promised:

* Every order the PC sends carries
  `client_order_id = "aegispc-<uuid>"` (`pc_broker.LEASE_PREFIX`).
* `pc_broker.check_lease()` reads the account's orders since the lease opened
  and **halts on any fill without that prefix**. A foreign fill is proof of a
  second owner, so ownership is measured rather than assumed.
* The lease file records the owning PID, so a second copy of the loop on this
  machine refuses too.

| account | owner from 2026-09-22 | executes |
|---|---|---|
| **PC-PAPER** (`ALPACA_PC_KEY_ID`) | **this PC**, `scripts/live_market_loop.py` | the ranked 21-session book |
| hack1, hack2, hack4, hack5, hack6 | Railway `loving-elegance` / `aat-loop-<role>` | the terminal repo's mandates |
| hack3 / PA3JYEG4DF9G | **nobody** — loop removed, account still open | nothing |

## Credentials, and the one rule about them

The PC reads **`ALPACA_PC_KEY_ID`** and **`ALPACA_PC_SECRET_KEY`** and nothing
else. There is no fallback to another role's pair — `test_no_other_roles_credential_is_substituted`
pins that — because a fallback is how one book quietly trades another's account.

And they are never aliased onto `APCA_*`. On 2026-09-21 aliasing the repo's
ALPACA pair onto the venue's names put a dead credential in front of P6's own
working fallback, the bars refresh answered 401, and the night lost its panel.
`night_run_until.KEY_ALIASES` is now empty on purpose.

**Data** credentials are separate from **order** credentials and always have
been: `night_p6_bars_and_regret.data_credential()` resolves a read-only key for
the bars host. It currently prefers `AAT_HACK3_*`, which still works — but hack3
is a deleted book, and a data path that depends on a deleted book's key is a
trap waiting for the day Alpaca finally revokes it. Moving that preference off
HACK3 is owed.

## What "make all the paper accounts useful" needs next

Murat, 2026-09-22: *"make all the paper accounts useful."* Four of the six are
carrying a mandate; hack2 is idle and hack3 is now ownerless. The honest reading
of the table is that the fleet's problem is not idleness — it is that the five
**active** books are down between 4% and 19%. Pointing more capital at mandates
that are losing would multiply the loss, not the learning.

So the order is: prove the PC book's ranking earns its keep on PC-PAPER first,
then repoint the idle accounts at it as independent seeds (different start
dates, same policy) rather than as new strategies. A new mechanism arrives as
its own book, never as a weight in an existing one (CLAUDE.md, THE BOTTLENECK).
