# C06 ATLAS receipt view

`scripts/beta_v2_atlas_view.py` projects explicitly supplied local receipts into
typed nodes and edges. It uses the existing world-state, event, thesis, decision
and V2 planning contracts. It imports only the standard library, opens no DB,
follows no directory trees and invokes no inference, grading or runtime writer.
The CLI writes one new output file with exclusive creation. Keep actual output
in the private evidence root, outside this public repository.

## Contracts and semantics

| Input kind | Existing contract | Identity and availability |
|---|---|---|
| `beliefs` | `backend/services/world_state.py`, `world_state/v2` | Topic; enclosing `as_of` gate and row `last_updated` |
| `scenarios` | Same service, `macro_scenarios/v2` | Native `scenario_id`; snapshot `as_of` |
| `event` | `backend/services/event_store.py` | `observation_hash` and separate `canonical_hash`; `ingested_at`/`accepted_at`, never publisher date |
| `thesis` | `backend/services/thesis_card.py` | Native `thesis_id` or `card_hash`; `run_utc` |
| `decisions` | `backend/services/decision_contract.py` | Native `decision_id`; `built_utc`, else enclosing `written_utc` |
| `registry` | `scripts/beta_v2_registry.py`, schema version 1 | Operational task/request/hypothesis IDs; current file-read clock |
| `receipt` | Opaque explicit evidence file | Only SHA-256 and path; content is not parsed or executed |

Economic identities use `economic:<kind>:<native-id>`; operational identities use
`operational:<kind>:<native-id>`. A registry H01 is an administrative hypothesis,
separate from an economic scenario or native decision hypothesis ID. No cross
namespace equivalence is inferred from identical text.

World-state `co_mention_edges` remain `co_mention`, including their original sign,
lag and support count. A scenario's prose `causal_chain` remains a declared,
label-only hypothesis; it generates no causal company edges. Root references in
beliefs are `REFERENCE_ONLY`, with underlying source joins unresolved. Equal
canonical event hashes collapse to one root; observation hashes remain separate
sightings. Counts do not become votes, reliability, exposure or weights.
Native event-store `source_url`, `source_timestamp` and generic `entities` are
preserved. Generic entities are not upgraded to companies without typed ticker
fields; that company join remains unresolved.

`evidence_reliability`, `economic_exposure` and original portfolio weight fields
are separate attributes. Missing values remain null. Scenario indicator weights
are named `indicator_weight` and never become portfolio weights. No sizing
calculation or scenario-probability sizing read occurs. Decision `position_budget`
stays a separate field; it is not reported as an actual holding weight.

Source citations plus an explicit ticker in one card permit a
`source -> company -> thesis/decision` subject query. This means a source is cited
for that company, not that its body proves a claim, caused a decision or directly
mentions the ticker. `thesis -> decision` lineage requires an actual `thesis_id`
on the decision and that thesis in the supplied inputs. Shared tickers or similar
text never manufacture this lineage.

## Consumer invocation

From the isolated repository root, supply each existing receipt by exact path:

```powershell
python -B scripts/beta_v2_atlas_view.py build --as-of now --receipt "beliefs=<runtime>/backend/data/optimus/world_state/beliefs.json" --receipt "scenarios=<runtime>/backend/data/optimus/world_state/scenarios.json" --receipt "registry=docs/beta_v2/registry.json" --receipt "thesis=<exact-card.json>" --receipt "decisions=<exact-daily-contract.json>" --output "<private-evidence-root>/atlas/view.json"
python -B scripts/beta_v2_atlas_view.py query --view "<private-evidence-root>/atlas/view.json" --from-node "economic:source:<exact-native-source-id-or-URL>" --target-kind decision --output "<private-evidence-root>/atlas/source-query.json"
python -B scripts/beta_v2_atlas_view.py query --view "<private-evidence-root>/atlas/view.json" --from-node operational:task:C06 --target-kind evidence --output "<private-evidence-root>/atlas/task-query.json"
python -B -m unittest backend.tests.test_beta_v2_atlas_view -v
```

`--polarity supportive|contrary|unclassified|all` filters evidence links. Structural
links remain traversable. Native world-state contradiction IDs are contrary to
the recorded **prior** belief; generic evidence IDs and card citations remain
unclassified. Optional explicit `supportive_evidence_ids` / `contrary_evidence_ids`
are honored only as references to supplied nodes. Direction, bullish wording,
co-mention sign and a card's aggregate verdict do not classify individual sources.

For registry evidence, add `--receipt "receipt=<exact-evidence-file>"` and use
`--registry-root <checkout>` when relative evidence paths belong to another
checkout. A link requires matching the registry's exact path/hash and a valid
`verified_at` clock. No file named by a reference is read automatically. Empty
registry evidence returns `UNRESOLVED`, never inferred completion.

## Time guard and limits

`--as-of` requires an aware timestamp or `now` resolved after the explicit input
reads. Availability, publisher/source, effective and expiry clocks are retained
separately. Future availability, future effectiveness, expired records, missing
availability and invalid/unzoned clocks are excluded with reasons. Source dates,
planning dates, information cutoffs and first-seen dates cannot substitute for
availability. Unknown expiry remains null; no expiry is invented from half-life
or horizon year. Effective/expiry filtering describes an active receipt view;
known but not-yet-effective announcements appear in `excluded`.

A query uses the saved view's exact as-of timestamp; an alternate instant requires
a rebuild. Current aggregate snapshots cannot reconstruct an earlier historical
state. Embedded producer clocks are preserved assertions, not certification that
the archive was complete or available historically. The registry's date-only
`as_of` is planning metadata; historical registry replay is unavailable without a
properly dated existing snapshot.

At most 16 explicitly named files, 2 MiB per file, 500 records per list, 2,500
nodes, 5,000 edges/unresolved joins and 1,000 query paths are admitted. Query depth
is 1–4. Oversized input refuses; no implicit scan or truncation occurs. Outputs
carry exact input paths, hashes and record locators. Missing references remain
in `unresolved`; excluded records are separate from empty results. This adapter
adds no brain, database, causal inference or operational authority.

## Reviewed temporal and task-evidence boundaries

Scenario rows pass both the snapshot gate and their own `last_updated`,
`effective_at` and `expires_at` checks. Only an absent row `last_updated` inherits
snapshot availability; an explicit invalid, null or future update cannot fall
back. Emitted scenario/indicator and contradiction facts retain the same clock
block that admitted them. No expiry is inferred from prose or horizon years.

A task-to-evidence query uses `DIRECT_TASK_EVIDENCE`: only that task's own
`registered_evidence` edge can make `status=MATCHED`. Reachable prerequisite
receipts appear separately in `dependency_paths` with
`REACHABLE_PREREQUISITE_EVIDENCE_ONLY`; they never fulfill the task. Other typed
queries retain their bounded path traversal.
