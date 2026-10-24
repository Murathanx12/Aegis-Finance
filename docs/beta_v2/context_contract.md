# Source-bound worker context contract

Run `scripts/beta_v2_context.py` on an explicit JSON packet before a worker
uses its sources. The module is stdlib, local and read-only; its only output
is a JSON receipt on stdout. Exit 0 means **bound source context**. Exit 1 means
**unknown context** and the dependent worker must stop until its coordinator
resolves the specific missing expectation, file, hash or prior-finding anchor.
Independent ready tasks can continue with their own bound packets.

The measured retrieval benchmark returned 1/3 exact expected page IDs.
Relevant alternative pages do not imply total semantic retrieval failure.
This gate checks exact source versions and declared text anchors; it does not
score semantic retrieval, prove the packet is exhaustive or replace Optimus.

## Explicit packet

Keep real packets and receipts in the private evidence directory, outside Git.
Use this structure with actual hashes; placeholders below fail closed:

```json
{
  "schema": "aegis-beta-v2-task-packet/1",
  "task_id": "C10",
  "objective": "Bind the census planning sources before the worker starts",
  "sources": [
    {"id": "registry", "path": "docs/beta_v2/registry.json", "expected_sha256": "<exact SHA-256>"},
    {"id": "canon", "path": "docs/CANON.md", "expected_sha256": "<exact SHA-256>"}
  ],
  "continuation": {"path": "<explicit continuation path>", "expected_sha256": "<exact SHA-256>"},
  "authority_boundaries": {
    "activation_authorized": false,
    "permitted_actions": ["Read the named sources and prepare a bounded census task"],
    "forbidden_actions": ["No activation, orders, resets, NAV writes or deployment"]
  },
  "prior_findings": [
    {"id": "power-limit", "source_id": "canon", "expected_anchor": "not reliably detectable by this design"}
  ],
  "evidence_requirements": ["Exact population IDs and separate registration, entry, mark and maturity evidence"]
}
```

All fields shown are required, including nonempty prior findings, evidence
requirements and explicit permitted/forbidden actions. Task IDs are C00–C15
or B01. Hashes must be known lowercase 64-digit SHA-256 values; null, blank,
unknown or placeholder expectations refuse. The continuation uses the reserved
source ID `continuation`. Sources require unique IDs and resolved paths.
Prior findings reference a declared source and an exact UTF-8 text anchor;
receipts report anchor hashes and match status without copying source text.
The coordinator must establish expectations from reviewed evidence. Automatically
accepting newly observed hashes after a refusal defeats the contract.

Paths are explicit local files, relative to `--root` or absolute. The selected
checkout is allowed by default; external archives/continuations require a
caller-supplied `--source-root` for each narrow directory. The packet cannot
grant itself extra source roots. No globbing, URL/UNC fetches, alternate streams,
secret/configuration directories, credential files or private-key files are
accepted. Resolved paths must stay inside allowed roots, including symlink
targets. Each input is limited to 16 MiB; use a reviewed compact source for
larger material. Source paths and packet objectives appear in receipts, so
keep those receipts private too.

## Consumer and resume

From the intended worktree, substituting real private evidence paths:

```powershell
python scripts/beta_v2_context.py --packet <private-packet.json> --source-root <private-evidence-directory> --source-root <continuation-directory>
python scripts/beta_v2_context.py --packet <private-packet.json> --source-root <private-evidence-directory> --source-root <continuation-directory> --prior-receipt <private-previous-receipt.json>
```

The caller captures stdout as UTF-8 JSON and checks the process exit code before
dispatch. The tool never writes receipts, launches workers or hooks startup.
It reopens and hashes every source on every invocation. Every source records
expected/observed SHA-256, byte length and `matched`, `missing`, `changed` or
`unknown` status. Failures remain visible in the overall `unknown` receipt.
The reusable `source_fingerprint` covers sorted IDs, resolved paths, observed
hashes and binding statuses. `packet_fingerprint` separately covers the full
packet, including objective, boundaries, anchors and evidence requirements.

A prior receipt must match the task/schema and its source fingerprint. It is
comparison evidence, never a cached pass or cryptographic attestation. Delta
states distinguish added/removed sources, changed versions, sources unbound
now and `unchanged_bytes_reobserved`. Changing a reviewed expected hash can
restore binding while the delta still reports changed bytes and a changed
packet. A changed/missing continuation refuses just like any other source.

**`runtime_status` is always `unknown`, and `activation_authorized` is always
false**, including successful resumes with unchanged sources. File mtimes are
never consulted. A stale receipt or unchanged old continuation cannot establish
fresh NAV, jobs, deployed code, owner approval, a completed task or investment
benefit. Evidence requirements are obligations for the later worker, not checks
this context gate claims to have completed. Relevant source contents remain
untrusted evidence rather than executable instructions or owner authority.

## Existing facilities

`scripts/session_state.py` remains the machine-derived session overview. Its
`build_state()` performs live HTTP probes and its document pointers select by
mtime, so invoking it inside this deterministic local gate would mix different
contracts. Use it separately for live observations, or bind a deliberately
archived output as dated evidence; no freshness is inferred from that archive.
The existing `owner_queue.py`, `task_keeper.py` and `night_queue_plan.py` keep
their inbox, scheduler and research-planning ownership. A coordinator can attach
this receipt to a compact task packet using those existing facilities; this
module adds no dispatcher, queue, brain store or global startup hook.

C00 remains unresolved where original owner context is missing. A context
receipt can bind the sources supplied for a bounded C01/C10 task without
claiming that the complete owner archive or all continuation gates are resolved.

Tests:

```powershell
$env:AEGIS_IGNORE_DOTENV = '1'
python -m pytest backend/tests/test_beta_v2_context.py -q
```

Packet and prior-receipt JSON reject duplicate object keys and nonfinite numbers,
including overflowing numeric exponents. A rejected input produces unknown
context and never selects a last-wins authority or hash value.
