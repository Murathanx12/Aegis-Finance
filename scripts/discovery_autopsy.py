"""CH-13 daily discovery-failure autopsy (attended CLI).

    python -m scripts.discovery_autopsy --data-root backend/data/optimus --out <folder>

Reads the live data folder read-only and writes `autopsy_<session>.json` (+ a
run-id copy, a markdown table, `index.jsonl`, `research_queue.jsonl` and the ISO
week's roll-up) under `--out`. A missing input or an unsupported screen exits 2
with the refusal code; see `backend/services/discovery_autopsy.py`.
"""

from __future__ import annotations

from backend.services.discovery_autopsy import main

if __name__ == "__main__":
    raise SystemExit(main())
