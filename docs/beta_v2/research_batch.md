# Bounded existing-data research readiness

`scripts/beta_v2_research_batch.py` is an offline readiness consumer, not a batch
executor. It reuses an explicitly named existing catalogue and ten fixed input
slots. Five proposed families retain 21 proposed arms: RF/NR (5), news/hybrid (5),
public disclosure flow (3), dated suppliers (3), and company transcripts (5).
Every arm remains `blocked_not_evaluated`; evaluations, results and new trial
registrations remain zero. Historical cumulative trials remain unknown.

The CLI reads the existing CANON, known failures and source-interface hashes
before selected datasets. It does not submit a daemon job, initialize a registry,
run a strategy/backtest, acquire data, infer text, compute P&L or alter NAV.
Its sole output is a qualification manifest on stdout. Save real receipts
outside Git under the owner's private evidence root; retain old receipts.

```powershell
$env:AEGIS_IGNORE_DOTENV = '1'
python -B scripts/beta_v2_research_batch.py --catalogue <exact-existing-catalogue.json> --runtime-root <existing-runtime-root> --limit 10 --sample-rows 64
python -B scripts/beta_v2_research_batch.py --catalogue <same-catalogue.json> --runtime-root <same-root> --prior-manifest <saved-v2-manifest.json> --prior-sha256 <exact-file-SHA256> --limit 2 --sample-rows 64
python -B -m pytest --noconftest -p no:cacheprovider backend/tests/test_beta_v2_research_batch.py -q
```

## What a structural sample establishes

Catalogue metadata is indexed, not a claim that every listed input was scanned.
Only the ten explicit slots are considered. A slot with no bound path means
"not bound here", not absence across local storage. A missing required column
means absence from that selected version's schema, not global source absence.
No discovery scan or substitute column/source is selected automatically.

Each sampled input must match the catalogue's full-content SHA256 and schema
hash. Hashing covers file bytes; it does not evaluate every row. Footer row/date
statistics are labeled metadata. Sampling reads only required key/clock columns
from the prefix of row group zero, at most 128 rows (64 by default), with exact
selected columns, sampled count and footer-row fraction recorded. It is neither
random nor representative coverage, a uniqueness census, or PIT qualification.

`structure_checked` means a bounded diagnostic was produced. Its defects may be
nonzero: missing/invalid candidate keys, repeated valid candidate keys, invalid
clocks or timezone ambiguity. No row is deduplicated or repaired. Date labels
remain separate from aware instants. A naive datetime is unresolved, not silently
converted to UTC. Valid instants are normalized before sample min/max comparisons;
mixed date/instant summaries carry no misleading shared min/max. Clock presence
does not prove historical public availability, permissible joins or no leakage.

Readiness always remains `unknown_not_qualified` overall and `unqualified` per
input. Structural success cannot change an arm's research status. Existing
failure controls, registration, instrument null/injected-edge calibration,
power/MDE, folds/purge, costs/borrow and independent validation remain unmet.

## Resource and resume boundaries

Limits are 1–10 newly visited slots, 1–128 sampled rows, 64 MiB per input file and
16 MiB catalogue/prior JSON. Before sampling, selected column chunks in row group
zero must have known nonnegative uncompressed sizes totaling at most 16 MiB.
Unknown or larger decompression refuses sampling. Reading is pinned to row group
zero so a short group cannot spill into an unchecked later group. Hashes bracket
sampling; changed bytes discard the diagnostic. Catalogue, tool, canon, negative
results and interface hashes bind the manifest contract.

Resume requires the exact saved manifest file hash and the same v2 contract,
input plan, source hashes and resource limits. IDs/order/path/family/status and
cursor must agree. The cursor denotes attempted slots, including blocked slots;
`qualification_pass_complete` means all ten slots attempted, never research or
readiness completion. Previous samples are recomputed after rehashing; cached
diagnostic values are not trusted. `--limit` counts new slots while revalidation
may revisit the prior prefix (at most all ten slots). Changed source bytes refuse
that version; a changed contract requires a fresh qualification with old receipts
retained. A v1 prototype manifest is not silently upgraded or resumed as v2.

The preserved initial native qualification recorded six 64-row samples and a
news-panel refusal above the decompression bound. Those are dated observations.
Use the latest private qualification and source hashes for current results;
this document does not claim that inputs were newly evaluated or broadly scanned.
