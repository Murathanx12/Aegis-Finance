# Two paper lanes died of a line ending, and nothing reported it

*2026-08-28. `scripts/copy_lab_run --status/--run`,
`backend/services/copy_lab/lanes.config_hash`.*

## The question that found it

"Check the Aegis paper accounts — did any beat the S&P 500, and how?"

The sweep answered *none of them ever held a position*: zero `nav.jsonl` files
across ten arena books, and both `copy_lab` trackers — `ACTIVIST_13D` (13D
activist stakes) and `CORPORATE_INSIDER_CLUSTER` (Form 4 cluster buys) — sitting
at `cash = 100000.0, positions = {}, last_nav = None` since 14 August.

That is an absence, not a result. So: run them and find out why.

## What the run said

    ConfigDrift: CORPORATE_INSIDER_CLUSTER was seeded under config 697ddd4e0005
    but the file on disk hashes to 727963034563 — refusing to run. Segment
    identity IS the configuration; continuing would attribute one strategy's
    record to another's rules.

The refusal is correct in principle and wrong in fact. `git log` on the
configuration shows **exactly one commit — the seeding commit.** Not a character
had changed.

    file: UTF-8 text, with CRLF line terminators
    CRLF count: 247    bare LF: 0
    sha256 raw     : 72796303456314f5     <- what the engine computes now
    sha256 LF-norm : 697ddd4e000560ff     <- exactly the seeded hash

Git's `autocrlf` rewrote 247 line endings on checkout. `config_hash` hashed raw
bytes. **A strategy's identity changed because of a platform convention.**

## Why fourteen days passed

Nothing schedules these lanes. `--run` is invoked by hand, and when it is not
invoked the lane's state file reads exactly the same as a lane that ran and
found no events: cash at 100,000, no positions, `last_nav: null`.

**A refusal nobody reads is indistinguishable from a lane with nothing to do.**
Same shape as the 2026-08-27 finding that refusing correctly and having nothing
to refuse print identically — and the same shape as ten arena books with no NAV.
This project's characteristic failure is not a wrong answer. It is a system that
declines to act and reports that identically to a system with nothing to act on.

## The fix, and why it is not a weakening

`config_hash` now normalises `\r\n` to `\n` before hashing.

A line ending is not a configuration: no threshold, holding period, sizing rule
or universe can differ between two files that are equal after normalisation. Any
real edit still changes the hash and still stops the lane — pinned by
`test_config_hash_still_changes_on_a_real_edit`.

It is **backward compatible by construction**. The seeds were hashed when the
working tree held LF, and normalising an LF file is the identity, so the seeded
hashes match again and the lanes revive **with their 14 August inception dates
intact**. That mattered: the system's own rule is that a changed configuration
is a NEW lane, so re-seeding would have thrown the inception away and started
the record over.

## What the revived run then showed

The lanes now execute and mark NAV. They still have no positions, for a second
and separate reason:

- `CORPORATE_INSIDER_CLUSTER` — 92 events considered, 9 new signals, **all 9
  ineligible**: newest `public_at` is 2026-08-12, before the 14 August
  inception. The Form 4 source has not advanced in over two weeks.
- `ACTIVIST_13D` — **0 events considered.** The 13D source yields nothing at
  all.

So there were two independent stoppages stacked on each other, and the first one
hid the second. Fixing the hash converts "the lane refuses to run" into "the
lane runs and its data source is dead", which is progress precisely because it
is now a question with an owner.

## Status

`PRODUCT_EXPERIMENT`. No claim is made about activist or insider copying — the
lanes have still never held a share. What has changed is that they can, and that
their silence now means something specific.
