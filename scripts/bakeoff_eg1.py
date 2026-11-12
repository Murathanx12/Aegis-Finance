"""Bake-off E-G1: extraction accuracy per provider, graded the same day.

    python -m scripts.bakeoff_eg1 --dry-run          # sample + census + the system prompt, $0
    python -m scripts.bakeoff_eg1                    # 240 items x 4 arms, DeepSeek cap $0.15
    python -m scripts.bakeoff_eg1 --arms rules,deepseek --n 40
    python -m scripts.bakeoff_eg1 --dry-run --arms rules,deepseek,local,featherless:Qwen/Qwen3-30B-A3B-Instruct-2507

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
left running), and `featherless:<model id>` (CH-04b: any id in
`config.FEATHERLESS_MODELS`, e.g. `featherless:Qwen/Qwen2.5-7B-Instruct`; every
call goes through `call_named("featherless")` -> `provider_budget.featherless_attempt`,
plus a batch cap per arm, MODEL_ROUTING_BAKEOFF_FEATHERLESS_CAP_USD; a model not
on that list is REFUSED, rc 2; a Featherless budget refusal during the run is rc 2).
The summary prints, per pair of arms, n paired (both answered), raw agreement and
Cohen's kappa on event_type and on direction; `--dry-run` prints the plan with a
projected cost per arm from config prices and calls nothing.

The receipt is flushed every 20 rows, with the wire `system` prompt on the first flush, and every row carries the model the provider says
answered (`usage.model` / `response.model`).
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _featherless_status() -> str:
    from backend.services import provider_budget as PB
    return PB.featherless_status_line()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--n-matched", type=int, default=None)
    ap.add_argument("--arms", default=",".join(MR.BAKEOFF_ARMS),
                    help=f"comma-separated; {', '.join(MR.BAKEOFF_ARMS)}, or "
                         f"{MR.FEATHERLESS_ARM_PREFIX}<id> with <id> in config.FEATHERLESS_MODELS "
                         f"({', '.join(getattr(_cfg, 'FEATHERLESS_MODELS', ()))})")
    ap.add_argument("--cap-usd", type=float, default=None)
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    arms = tuple(x.strip() for x in a.arms.split(",") if x.strip())
    bad = [x for x in arms if x not in MR.BAKEOFF_ARMS and MR.featherless_arm_model(x) is None]
    if bad:
        print(f"REFUSED: unknown arm(s) {bad}; have {MR.BAKEOFF_ARMS}")
        return 2
    arm_bad = MR.bakeoff_arm_refusals(arms)
    if not a.dry_run:
        # a paid arm without its key is refused BEFORE sampling or any spend
        arm_bad += MR.bakeoff_key_refusals(arms)
    if arm_bad:
        for line in arm_bad:
            print(f"REFUSED arm {line}")
        return 2
    fl_arms = [x for x in arms if MR.featherless_arm_model(x) is not None]
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
        for line in MR.bakeoff_plan(items, arms, cap_usd=a.cap_usd):
            print(line)
        if fl_arms:
            print(_featherless_status())
        return 0
    if fl_arms:
        print("BEFORE " + _featherless_status())
    out = Path(a.out) if a.out else MR.receipt_dir() / MR.default_receipt_name()
    res = MR.run_bakeoff(items, arms=arms, call_fn=_call_named, out_path=out,
                         cap_usd=a.cap_usd, census=census)
    print(json.dumps({k: res[k] for k in ("path", "n_rows", "spent_deepseek_usd",
                                          "local_server_after")}, indent=1, default=str))
    receipt = json.loads(Path(res["path"]).read_text(encoding="utf-8"))
    for line in MR.bakeoff_table(receipt):
        print(line)
    rc = 0
    if fl_arms:
        print(json.dumps({"spent_featherless_usd": res.get("spent_featherless_usd")}, default=str))
        print("AFTER " + _featherless_status())
        # a guard's refusal is red: a Featherless arm that was refused (envelope,
        # missing key) or stopped by its batch cap is rc 2, never a quiet row in a green run
        refused = {}
        for r in receipt.get("rows") or []:
            if r.get("arm") in fl_arms and r.get("status") in ("BUDGET_REFUSED", "NOT_CONFIGURED",
                                                                "BUDGET_CAP"):
                k = f"{r['arm']}:{r['status']}"
                refused[k] = refused.get(k, 0) + 1
        if refused:
            print(f"REFUSED: featherless arm rows refused {refused} -- see the receipt's `error` fields")
            rc = 2
    # an arm that answered NOTHING measured nothing: red, with its reasons
    for arm in arms:
        rs = [r for r in receipt.get("rows") or [] if r.get("arm") == arm]
        if not any(r.get("pred") for r in rs):
            why = sorted({str(r.get("refusal") or r.get("status")) for r in rs}) or ["no rows"]
            print(f"FAILED: arm {arm!r} answered 0 of {len(rs)} rows ({', '.join(why)})")
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
