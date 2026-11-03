# Saved-calendar discovery: isolated source candidate

Base: origin/main `40cdc5d57922fed49dd6fa8d6d67a44ded62b9a3`.

`scripts.pre_event_owner_warning_discover` is a preview-only candidate for the
existing 10-minute AegisOwnerEventWarning workflow. It does not install, register,
modify or activate a task or R launcher. No provider requests, credentials,
Telegram sends, trades, journal writes, cursors or fabricated receipts are used.

The CLI takes `--receipt-dir`, `--pc-paper-ledger`,
`--expected-account-sha256` and `--journal-dir`. All directories must already
exist. There is deliberately no `--send` or caller clock CLI option.

Discovery examines at most 64 directory entries (including unrelated and temp
files), refuses overflow rather than silently truncating, and uses a five-second
cooperative discovery budget. It checks the existing protected IIF interval,
private capture/journal identities, frozen reads, published filename and seal,
saved-calendar replay, exact account pin and approved fresh snapshot selector.
Each receipt keeps its own observation clock. Checkout mtime is never evidence.
No recursive scan or provider fallback occurs. Private-root trust has the same
same-user replacement limitation documented by the existing capture/journal.
Local filesystem operations are not forcibly interrupted by the cooperative timer.

Eligible events are ordered by earliest ET date, newest embedded observation,
then filename. Any existing event attempt/result/pending journal path suppresses
that event conservatively, including corrupt or uncertain attempts. Discovery
never calls a sender to test duplicates or certifies an ACK. With no candidate,
JSON reports explicit NO_OP (empty/duplicate-only) or REFUSED (invalid inputs),
with counts. One valid candidate can coexist with corrupt/ineligible receipts.
The selected receipt bytes and private-root identities are rechecked before
exactly one call to `pre_event_owner_warning_once.run`, always with send disabled.
That runner independently revalidates the saved evidence/account/journal and owns
its existing additional execution budget. Preview is neither a delivery receipt
nor authorization to send; it does not reserve the event against concurrent previews.

## Adoption dependency — existing task cannot call this automatically

The installed task/launcher was not inspected or changed in this source-only
chunk. Treat the owner's stated 10-minute cadence as supplied context, not live
verification. No native task invocation or delivery was tested.

The existing sender's exact-source review list does not include this new discovery
module. Enabling sends through discovery safely requires a separately reviewed
source-policy extension covering this module and its imports, plus a reviewed
local launcher/task adoption. This candidate stops before that protected change.
Do not wrap preview output in a sender or monkeypatch the review list. The
existing independent review, account pin, private journal durable reservation,
pre-send budget, IIF deadline, ET event deadline, owner pin and transport duplicate
guard must all remain binding. No compatible approval/review file is generated.

Offline tests exercise actual synthetic sealed receipt replay, selected event,
corrupt/multiple/empty inputs, entry/time bounds, expiry, account/IIF refusal,
root/receipt mutation, deterministic ordering and journal suppression. Transport
and provider functions fail the tests if reached. The unchanged one-receipt suite
also covers exact reviews, event/send deadlines and durable duplicate behavior.
No independent reviewer agent was available; these checks are not an independent
source review or local adoption approval.
