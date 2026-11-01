# Cooperating paper-scope threads

`openclaw_client._paper_scope_lock` now acquires a per-process `threading.RLock`
before entering the unchanged `disk_guard.file_lock` on
`aegis_openclaw_exclusive_paper_scope.lock`, still with `timeout_s=0`.

Two cooperating threads therefore wait locally instead of treating one another
as an external paper-scope conflict. The OS file lock still excludes a different
process immediately. A nonparticipating thread that holds the original disk
guard also remains exclusive. Same-thread nested use remains reentrant at both
layers. The context still yields the original guard path. Both locks release on
protected-action exceptions and on foreign-lock refusal.

No `disk_guard`, browser/profile, native-broker context, credential/environment
filter, topology lock, page quota, tab cap, paging rule or task setting changes.
All browser commands still enter the same guarded `_run` path, and the pool's
existing guarded target listing uses the same scope helper. The fix does not
introduce a browser call, fallback profile or another reader owner.

## Evidence and operating limits

The new native two-tab owner proved target/open/in-flight mechanics, but its
first observation receipt also showed same-process scope contention and failed
tab closes. `C04_CONTENT_YIELD_PACKET.md` and the final-window addendum under
private recovery evidence distinguish attempts, classified reads, actual stored
bodies, ordinary pacing and failed-close IDs. These are not interchangeable
health or body-yield measures.

The local `RLock` waits for its holder; it has no added timeout, FIFO guarantee
or STOP cancellation. Existing command timeouts remain unchanged and do not
create a new aggregate queue/handoff deadline. This narrow correction makes no
wall-time bound or parallel-transport claim. A waiting thread issues no extra
browser command; existing reservation, quota, pacing and stop rules still apply.
Do not widen quotas or infer useful content yield from two open tabs alone.

An already running Python pool retains its loaded old module. Source adoption
therefore needs the coordinator's existing owned idle/STOP/carry/finalization
transition and old-owner natural exit, followed by the reviewed action/source
pin rebind. Do not replace an active owner's code in memory or start a duplicate.
Failed-close IDs must be checked against the exact generation's recorded reader
IDs and a later guarded current-target inventory before an owned close; a saved
failed-close ID does not prove the tab still exists. No builder browser action,
tab close or native installation is performed by this source build.

## Offline tests and acceptance

`backend/tests/test_openclaw_paper_scope_threads.py` uses actual threads with a
private temporary guard path. The first thread holds the scope while the second
waits, then both succeed. The exception variant proves the waiter continues;
nested scopes preserve reentry and the original yielded path. A test-owned
direct base interpreter holds a real private OS file/byte-range lock. The parent
must refuse before the protected action with exactly `timeout_s=0`, then recover
after release. The child imports only stdlib, never an SDK, and is joined by PID.

Focused existing OpenClaw profile/HTTP, broker-context/tool-scope and disk-guard
tests remain appropriate security regressions. Their temporary guard paths must
be isolated from the live native paper-scope file. No browser, gateway, provider
or financial operation is part of acceptance. Tests/source review establish the
mechanism; the next coordinator-owned transition and measured article-body/
failed-close readback establish native concurrency yield separately.
