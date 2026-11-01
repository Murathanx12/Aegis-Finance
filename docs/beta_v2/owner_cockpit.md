# Private owner cockpit

`scripts.beta_v2_owner_cockpit` renders the existing canonical registry into one
self-contained HTML file. It adds no registry, database, dispatch, live health
check or acceptance authority. Its complete denominator is 146 requests, 17
tasks and 28 hypotheses; missing or different IDs refuse instead of truncating.
The four frozen C02 acquisition files are unrelated and remain unchanged.

Use the existing registry's IDs/statuses, code-pinned source baseline and typed
ATLAS `Projection` / direct-task-evidence `query` interfaces. Original workbook
task prerequisites remain effective even if copied request edges are missing.
Task receipts reached through prerequisites do not fulfill the task itself.
Supplied reports that the registry does not reference appear in the source index
only. No prose report is parsed into a new completion verdict.

Create an explicit private JSON input manifest:

```json
{
  "schema": "owner_cockpit_inputs/1",
  "as_of": "now",
  "registry_root": "<absolute checkout root>",
  "registry": {
    "path": "<absolute canonical registry.json>",
    "sha256": "<expected raw SHA-256>",
    "captured_at": "<aware capture instant>"
  },
  "baseline": {
    "path": "<checkout>/docs/beta_v2/source_baseline.json",
    "sha256": "c86768ac85e5a1a4f68a190ce4a0b85a9b5536c9e2f912127b25107afcf64b26",
    "captured_at": "<aware capture instant>"
  },
  "evidence": [
    {
      "kind": "receipt",
      "path": "<one exact existing receipt>",
      "sha256": "<expected raw SHA-256>",
      "captured_at": "<aware capture instant>"
    }
  ]
}
```

An empty evidence list is valid and visibly unresolved. Capture clocks are
operator assertions, distinct from this build's actual read clock, the registry's
planning date and registered receipt verification dates. `now` resolves after
the explicit reads; an earlier fixed as-of refuses current-registry replay.
No source file named by a registry reference is opened automatically. Full
canonical structural validation runs only when all evidence/routing references
are explicitly supplied; otherwise its omission and exact missing paths stay
visible. Structural validation never substitutes for original archive attestation.
The baseline must be the existing loader's independently code-pinned file.

```powershell
$env:AEGIS_IGNORE_DOTENV = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
& C:/Users/mrthn/aegis-finance/.venv/Scripts/python.exe -B -m scripts.beta_v2_owner_cockpit `
  --manifest <private-input-manifest.json> `
  --manifest-sha256 <expected-manifest-SHA256> `
  --output-dir <NEW-directory-under-aegis-recovery-evidence>
```

The parent must exist. The resolved output must be under the current user's
`aegis-recovery-evidence` root; a matching directory name or `..` alone cannot
authorize a different destination. Output refuses an existing directory, repository
output, symlink or junction. It creates only `index.html` and `receipt.json` in
the new private evidence directory; it never publishes under `frontend/public`,
touches native history, starts a task or fetches a service. The receipt binds the
HTML hash, input paths/hashes/clocks and exact counts. Inputs are rechecked before
output. Input limits are 2 MiB each, at most 15 explicit opaque evidence files,
and a 5 MiB HTML output limit. Failure is explicit; there is no partial catalogue
or silently reduced request denominator. A failed disk write can leave an
incomplete new bundle; no existing artifact is cleaned up or overwritten.

The page uses local system fonts, embedded CSS/JavaScript and no external assets,
client fetches or network links. It works from a local file. Search, task,
recorded-status and evidence filters update exact shown/full counts; Reset
returns all records. Requests and hypotheses have expandable acceptance,
dependency, evidence, source and review detail. The task table separates direct
evidence from prerequisite evidence and records missing receipt dates explicitly.
Without JavaScript all items remain readable. No completion percentages, runtime
health badges or served-model assertions are calculated.

All input text is escaped for HTML. Embedded JSON also escapes markup delimiters
and uses no executable interpolation; dynamic labels use DOM text APIs. A CSP
allows only the exact embedded script hash and inline styling, with network,
base-URL and form actions disabled. Input prose remains untrusted data.

`build()` without the required manifest/hash/output raises `CockpitRefused`
before file access. This module is under `scripts`, outside backend guard
discovery; no shared guard exemption or CASE edit is needed. Verification should
exercise a real generated page's counts/filter/reset and a hostile label, rather
than adding tests that repeat the rendering implementation.
