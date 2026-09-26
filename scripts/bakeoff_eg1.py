"""Bake-off E-G1: extraction accuracy per provider, graded the same day.

    python -m scripts.bakeoff_eg1 --dry-run          # sample + census + the system prompt, $0
    python -m scripts.bakeoff_eg1                    # 240 items x 4 arms, DeepSeek cap $0.15
    python -m scripts.bakeoff_eg1 --arms rules,deepseek --n 40

G-fix, adjudication row 7 (reviewer G, "THE EXPERIMENT MURAT ASKED FOR").
`/compare` used to ask three models for a DIRECTION probability on six price
numbers; direction skill is -7.9% held out, so that contest is won by noise and
reads out in years. This batch answers the routing question instead: which
provider READS a dated news item into typed fields best, per dollar and per
second, graded against `analyst/target_revisions.parquet` (see
`model_routing` for the gold rule, declared before the run).

Arms: `rules` (regex baseline), `deepseek` (deepseek-chat), `nvidia` (the
`NVIDIA_ADJUDICATOR_MODEL`, 429-retried, content only), `local` (llama-server
through `llama_server.ensure()`, stopped BY PID at the end -- it must not be
left running). The receipt is flushed every 20 rows, with the wire `system`
prompt on the first flush, and every row carries the model the provider says
answered (`usage.model` / `response.model`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                     # noqa: E402
from backend.services import model_routing as MR        # noqa: E402


def _call_named(provider, system, user, *, purpose, **kw):
    from backend.services import llm_analyzer as LA
    # an attended batch with its own dollar cap: not the 150-call production counter
    return LA.call_named(provider, system, user, purpose=purpose,
                         production_budget=False, **kw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--n-matched", type=int, default=None)
    ap.add_argument("--arms", default=",".join(MR.BAKEOFF_ARMS))
    ap.add_argument("--cap-usd", type=float, default=None)
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    arms = tuple(x.strip() for x in a.arms.split(",") if x.strip())
    bad = [x for x in arms if x not in MR.BAKEOFF_ARMS]
    if bad:
        print(f"REFUSED: unknown arm(s) {bad}; have {MR.BAKEOFF_ARMS}")
        return 2
    n = a.n or int(_cfg.MODEL_ROUTING_BAKEOFF_N)
    n_m = a.n_matched if a.n_matched is not None else min(
        int(_cfg.MODEL_ROUTING_BAKEOFF_N_MATCHED), round(n * 0.75))
    items, census = MR.bakeoff_sample(n=n, n_matched=n_m, seed=a.seed)
    print(json.dumps(census, indent=1, default=str))
    if a.dry_run:
        print("\n===== SYSTEM =====\n" + MR.bakeoff_system())
        if items:
            print("\n===== USER (item 0) =====\n" + MR.bakeoff_user(items[0]))
            print("\n===== GOLD (item 0) =====\n" + json.dumps(items[0]["gold"]))
        print(f"\nDRY RUN: {len(items)} items, arms {arms}; nothing called.")
        return 0
    out = Path(a.out) if a.out else (MR.receipt_dir() / f"bakeoff_{MR.BAKEOFF_ID}_{date.today()}.json")
    res = MR.run_bakeoff(items, arms=arms, call_fn=_call_named, out_path=out,
                         cap_usd=a.cap_usd, census=census)
    print(json.dumps({k: res[k] for k in ("path", "n_rows", "spent_deepseek_usd",
                                          "local_server_after")}, indent=1, default=str))
    for line in MR.bakeoff_table(json.loads(Path(res["path"]).read_text(encoding="utf-8"))):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
