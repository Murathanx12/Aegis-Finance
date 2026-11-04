# C06 bounded lineage diagnostic (2026-11-04)

Base: remote main `6dc083fff6a00b2edaaa7d18d6df36c3dccd394b`.
Scope: diagnostic/refusal only; C06 remains incomplete. No adapter port or
producer changes, runtime adoption, causal claim, paper action, or data rewrite.

## Exact blocker

`backend/services/decision_contract.py:_base_row` and `build_daily_contracts`
produce decision IDs and (on probe rows) hypothesis IDs, but no native
`thesis_id` or `card_hash` reference. `backend/services/thesis_card.py:build_card`
emits `card_hash`. Hypothesis IDs and ticker matches are not thesis references.
Closing this gap requires a separately scoped native producer contract carrying
the actual consumed thesis identifier and availability/provenance into the
decision. An adapter cannot reconstruct that missing historical fact.

## Reviewed sources inspected, not ported

Owner root: `C:/Users/mrthn/aegis-worktrees/beta-v2-owner-20261025`.
Read `docs/AEGIS_BETA_V2_ROADMAP.md` C06 and the private review
`C:/Users/mrthn/aegis-recovery-evidence/beta-v2-owner-20261025/reviews/C06_C12_FIX_REVIEW.md`.
The adapter has only stdlib dependencies; no C12/registry implementation import
is needed. Its reviewed file bytes still match:

| Owner-relative source | SHA256 |
|---|---|
| `scripts/beta_v2_atlas_view.py` | `36a18d836a569372ee30a4e1ac2ac8e266c86746f63320dd5605477fd4459364` |
| `backend/tests/test_beta_v2_atlas_view.py` | `4aa93ea0d8da071a4219749d76f79d3c6487092fe5902c690b9bf81f4fd25df8` |
| `docs/beta_v2/atlas_view.md` | `e829f27b3f970949370450b44503cbe00074cb55188ca89d0f6b1788673fa1e2` |

The review qualifies a local saved projection, explicitly leaves thesis-to-decision
lineage unresolved, and does not qualify C06 completion. The user's fallback
instruction therefore controls this packet: only a small refusal diagnostic.

## Probe semantics

`scripts/c06_lineage_diagnostic.py` reads one explicitly named saved view, requires
its exact SHA256 and literal saved as-of string, preserves embedded source refs
and endpoint facts/clocks, and never follows embedded paths. It returns JSON on
stdout and exits 2. It never returns PASS/MATCHED or lineage paths. It does not
verify original source files or certify the saved assertions as historically true.

The requested source -> company -> thesis -> decision chain is refused when the
native thesis ID is missing. Shared-ticker subject edges never repair it. Even a
saved explicit thesis edge returns `NATIVE_PRODUCER_CONTRACT_NOT_QUALIFIED`;
this fallback has no authority to accept a future producer contract. Duplicate
identities/conflicting thesis or decision facts, future availability, unknown or
invalid availability, future effectiveness, expiry, changed bytes or clocks
refuse. Time checking conservatively covers the whole view, including unrelated
facts. Publisher dates are preserved assertions, not availability substitutes.

## Saved native observation

Read-only probe of private `atlas/r2-native-view.json` under the evidence root:
SHA256 `80f08c738d6036b1dea7a752eb1cba6f21594ae730034b08446def2d8d43d1e1`,
exact saved as-of `2026-10-24T17:38:41.445928+00:00`. All 97 saved decision nodes
return `MISSING_NATIVE_THESIS_ID`; zero lineage passes. This is saved evidence,
not current runtime health. Source endpoint used:
`economic:source:https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2027`.
Example decision: `economic:decision:8a6bd9ef0a03ffa4`.

Invocation (supply the private exact view path):

```powershell
python -B scripts/c06_lineage_diagnostic.py --view <r2-native-view.json> --expected-sha256 80f08c738d6036b1dea7a752eb1cba6f21594ae730034b08446def2d8d43d1e1 --as-of 2026-10-24T17:38:41.445928+00:00 --source economic:source:https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2027 --decision economic:decision:8a6bd9ef0a03ffa4
```

Focused checks (backend autouse fixtures/plugins and cache writes disabled):

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -B -m pytest --noconftest -p no:cacheprovider -o addopts='' -q backend/tests/test_c06_lineage_diagnostic.py
python -B -m ruff check scripts/c06_lineage_diagnostic.py backend/tests/test_c06_lineage_diagnostic.py --no-cache
```
## Verification and review limits

Final focused result: 13 tests plus 12 subtests passed; Ruff passed. Two pytest
warnings concern timeout settings whose plugins were deliberately disabled.
Independent read-only review is saved at
`C:/Users/mrthn/aegis-recovery-evidence/c06-bounded-20261104-review.txt`.
It found output nesting could escape structured refusal and tests lacked status
assertions. Added a pre-retention depth limit (32), parser recursion refusal,
explicit status/lineage/path assertions, and CLI exit/no-embedded-read regressions.
The builder reran the focused checks after these fixes; the final changes were
not independently re-reviewed. No full backend suite or deployed test was run.

The initial all-97-decision saved probe receipt is
`C:/Users/mrthn/aegis-recovery-evidence/c06-bounded-20261104-probe.json`;
its code/test hashes identify that observation's intermediate revision. The final
probe receipt has suffix `-final` and identifies the final code/test bytes.
Only the isolated worktree was authored; protected owner/R worktrees were not
reset, cleaned, staged or edited. No push, merge, deploy or scheduled task.
