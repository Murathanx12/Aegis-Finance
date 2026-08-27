# FINDING 2026-08-27 — the Railway bill is half plan fee and half a process that computes for nobody

**Command:** `railway metrics --json --since <window>` against `selfless-courage / Aegis-Finance`.
**Rates:** Railway published — RAM $10/GB-month, CPU $20/vCPU-month, volume $0.15/GB-month, metered
by the minute. Rates are INPUTS and are printed beside every figure so a rate change does not
silently invalidate the conclusion.

## What is actually deployed

**One service.** `selfless-courage / Aegis-Finance`, running commit `6ddcf53`, with a 202 MB volume
at `/data`. The second project, `loving-elegance`, holds **no services at all**. The
`aegis-alpha-terminal` loops were never deployed — `railway.toml` and the Dockerfile exist, unused.

So there is no fleet to trim. There is one process, and it is the website.

## The measurement

| window | CPU avg | RAM avg | volume | HTTP reqs | attributed usage |
|---|---|---|---|---|---|
| last 6h | 0.376 vCPU | 0.597 GB | 0.197 GB | 11 | **$13.51/mo** |
| last 12h | 0.356 vCPU | 0.789 GB | 0.196 GB | 13 | **$15.04/mo** |
| last 1h | 0 | 0 | 0.197 GB | 0 | service **SLEEPING** |

Peak memory reached **2.99 GB**; peak CPU **27.2 vCPU against a 24.0 limit** — it bursts past its own
ceiling.

## Three things this settles

**1. It is NOT only RAM.** The 2026 cost work concluded memory was overwhelmingly responsible, and
FinBERT idle-unloading was added because of it. That worked: RAM is now 0.6–0.8 GB, about $6–8/month.
But **CPU is 0.36 vCPU average, which is $7.1–7.5/month — roughly the same again.** Any plan that
only attacks memory now addresses half the usage bill.

**2. That CPU is not serving anybody.** Thirteen HTTP requests in twelve hours, and a third of a core
burning continuously underneath them. p50 latency is 2,303 ms on the requests that do arrive. This is
the "something is staying resident or computing continuously" hypothesis, confirmed with a number:
**the process spends far more compute on itself than on its visitors.**

**3. Serverless sleep is already working, and it is why the bill is not worse.** The current
deployment reads `SLEEPING` and the last hour shows 0 CPU / 0 MB. So the fix is not "make it sleep" —
it already does. The fix is that **when it wakes, it does a third of a core of work for eleven
requests.**

## What the $30 is

Measured usage is **$13–15/month**. The bill is ~$30. **Roughly half of it is therefore the plan's
base fee, not consumption** — Hobby is a $5/month minimum, Pro is $20.

**I could not confirm which plan is active.** `railway whoami --json` and `railway status --json`
return the workspace and project but no tier, and the CLI exposes no billing command. So this is
arithmetic on the gap, not a reading of the invoice — **check the plan in the dashboard before acting
on it.** If it is Pro and no Pro-specific capability is in use, dropping to Hobby is worth ~$15/month
immediately and requires changing nothing about the code.

That would be the largest single saving available, and it is a settings change rather than an
architecture project.

## What the architecture change is worth, honestly

If the continuous compute were eliminated entirely and RAM halved, usage would fall from ~$14 to
perhaps **$3–5/month**. Real, and worth doing — but **smaller than the plan question**, and it should
be sequenced second for that reason.

The shape is not in dispute: heavy analysis runs locally or nightly and writes snapshots; the web
server reads snapshots and holds no model. The measurement above says where to start — find what
consumes 0.36 vCPU while the site serves eleven requests, because that is now the larger half of
usage, and it was not what the previous investigation was looking for.

## What this does NOT license

Deploying nothing to Railway ever again. It licenses the rule already agreed: **no new always-on
service until projected total is ≤$10/month, or there is a measured reason it cannot be.** A cron job
that starts, works and exits does not create an always-on service and is not covered by that bar.

**No new Railway service was created in this session.**
