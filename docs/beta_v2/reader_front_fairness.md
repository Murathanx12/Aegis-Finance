# Reader front dispatch fairness

`reader_front_fairness.filter_front_streaks` receives the existing pool's
budget-filtered candidates immediately before the unchanged scheduler chooser.
After two consecutive `front` or `front_text` dequeues on a host, it suppresses
that host's fronts only if a discovered `article` with `parent_url` waits in that
candidate set. All other candidates retain their identities and order, including
robots prerequisites. No qualifying article means fronts continue without idle.

`Pool.take` updates the host counter under its existing lock at dequeue. Two
workers therefore share the same counter. Any nonfront dispatch resets it;
front counts saturate at two. Counts include reads that later fail, and reset
on process restart. The per-host status field `front_dispatch_streak` reports
this bounded count. It measures dispatches, not successful bodies or wall time.

The existing governor, host slots, cooling, readiness times, budget filtering,
robots checks, transport guards and scheduler ordering within retained candidates
still apply. Candidate membership does not grant robots or fetch permission;
those existing checks remain authoritative. No acquisition, inference or paid
budget is expanded. This cannot promise global FIFO, a body yield, or elapsed
time to an article. Continuous search/robots/other nonfront work is outside this
front-only rule.

The pure original-source probe under private evidence reproduces conditional
starvation with continuously replenished due fronts; a finite front backlog
eventually drains. Native observations of fronts alone do not prove permanent
starvation. Focused tests exercise actual locked `Pool.take`, two threads, budget
denial, host/governor holds and unchanged chooser preferences with mock queues.

This is an isolated source build. The native pool differs from the worktree;
adoption requires the exact preimage-bound minimal delta and independent review,
then the coordinator's separate runtime transition. No whole-file replacement
from the worktree is qualified by these tests.
