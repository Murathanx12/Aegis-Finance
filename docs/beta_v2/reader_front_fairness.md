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


## Conditional global front burst

The global dequeue counter also saturates at two for front/front_text and resets
on every nonfront dispatch, under the same Pool lock. At the cap, a pure probe
uses the unchanged RS.choose with an article-first key and the exact existing
candidate map, blocked/free-slot/readiness/clock/in-flight inputs. It activates
only if an already discovered, budget-admitted article is in that chooser's
winning five-second-ready and minimum-in-flight group. It never deletes global
fronts or rebuilds readiness. Without such an article, the original key is used
and fronts continue without added idle.

When activated, a local front flag prefixes the original key for that final
choose call. Pool._key stays its original tuple; all nonfront kinds retain
their original relative order. Robots/search may still precede articles. This
counts dispatch grants, including later failures; it does not promise FIFO,
body success, publisher completeness, a deadline or any native performance.
Continuous eligible nonfront work and articles outside the winning group remain
outside this front-only ordering rule. Restart resets the counter.

Portable synthetic tests use the actual helper, Pool.take AST and unchanged
RS.choose from repository paths. The real-thread negative control has THREE
hosts: after B's first front, article host A and another front host D both have
zero in-flight. With only the global rule disabled the second dispatch is D's
front; with it enabled the second is A's article. A two-host case alone cannot
prove this effect because ordinary in-flight precedence may favor A. Additional
tests preserve five-second boundaries, blocked/slots/budget holds, item identity,
nonfront ordering and exception-before-dequeue behavior. These fixtures do not
qualify runtime adoption or real article yield.
