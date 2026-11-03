# Owner lineage caller candidate - 2026-11-04

INACTIVE; independent owner review pending. No adoption/review credentials, scheduler or transport configuration created.
Base: `31db98d1109fff6974b99f3695edd861798bccb8`. Worktree: `C:/Users/mrthn/aegis-owner-lineage-caller-candidate`; branch: `candidate/owner-lineage-caller`.

The runner assesses the already frozen single SEC line and snapshot through the reviewed pure connector before journal reservation. The frozen run UTC is both evidence cutoff and decision clock. `forecast_input_id` and `provisional_decision_id` enter receipts, the persisted artifact and rendered text, so the existing text/tag ACK binds them. Connector refusal or decision-artifact disagreement refuses before reservation. `NO_CALIBRATED_EVENT_FORECAST`, null forecast ID, zero new allocation and the existing conditional stress arithmetic remain explicit.

`SOURCE_PATHS` now additionally binds saved_sec_event_path.py and saved_sec_forecast_input.py. Neither dependency nor the Telegram bridge was edited. The ticker/accession journal identity, manual suppression proof path and single sender remain unchanged; refreshed snapshots do not make a suppressed/manual or journaled event a new delivery. Legacy normalized/path entry points remain unchanged.

Validation: 236 passed, 1 skipped (directory symlinks unavailable), using:

```powershell
python -m pytest -p backend.tests.test_owner_event_warning_runner backend/tests/test_owner_event_warning.py backend/tests/test_owner_event_warning_runner.py backend/tests/test_owner_warning_frozen_inputs.py backend/tests/test_owner_event_warning_bridge_contract.py backend/tests/test_saved_sec_event_path.py backend/tests/test_saved_sec_forecast_input.py -q -rs
python -m ruff check scripts/owner_event_warning.py backend/services/owner_event_warning.py backend/tests/test_owner_event_warning_runner.py backend/tests/test_owner_warning_frozen_inputs.py
git diff --check
```

Tests use synthetic temporary files and mocked owner/transport/ACKs. They exercise refreshed Apple-only suppression (zero transport), a distinct eligible event, bound ACK/replay, timeout/ambiguous ACK/interruption refusal, replacement-resistant frozen lineage, connector refusal and both executable dependency replacements. Explicit `-p` loads shared fixtures for the existing frozen-input test module.

Limits: synthetic ACKs do not prove native delivery or owner reading. Hashes identify bytes/context, not truth or authenticity. Existing private-journal same-user replacement and directory-entry power-loss limits remain. Review attestations are not signatures; source-file review is not a lock on already loaded Python code. No independent review performed in this session. No live R/E, launcher/review gates, policy-pinned sources, NAV/orders, live sends, task changes, model/network calls, PR, push or activation.

SHA256 (exact working-tree bytes; unchanged dependencies included for review):

| File | SHA256 |
|---|---|
| `scripts/owner_event_warning.py` | `570ea35c2edc8fd63bcd30fd3b062729da554ed638b1e06f60f6d2c5631053f5` |
| `backend/services/owner_event_warning.py` | `e774c40bd4c3fb746855734a18e8bb9fbd0af459082a89c3aeaabb657b4eecb6` |
| `backend/tests/test_owner_event_warning_runner.py` | `066217f76ec0e816320c22f7bf6ec6870fb918d576a3abbc876379ab419b5306` |
| `backend/tests/test_owner_warning_frozen_inputs.py` | `e97ec8c86013f9ecf02e0c7a051ec1e71425ad56744e1cecb76f9d7df88f7fb6` |
| `backend/services/saved_sec_event_path.py` | `6b30f69d42b68a022c4dc43f6ea444d00e4a136cee8ed76d36d5d2e24f209964` |
| `backend/services/saved_sec_forecast_input.py` | `38ddeb22f6b2c02615df7ab9b2f910ce9cbf40ad7056ec1ee78fe895a30d385f` |
| `backend/services/telegram_bridge.py` | `1a6fc6ee80612d3b0cb8b230688535b752f22efede9171c875d842f659723f58` |
