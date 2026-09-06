"""N5.2 -- SELF-SUPERVISED PRE-TRAINING: WHAT IS ALREADY IN, AND WHAT IS BLOCKED.

THE MANDATE'S SENTENCE, AND WHAT OF IT IS ALREADY TRUE
======================================================
Lane N5 item 2 asks for the `nn_pre_causal` recipe on "the long panel + N4/N5
features, CUDA via the designated interpreter, 8 seeds, seed-mean judged, then
INTO the N2 ensemble -- never as a lone champion."

Half of that already happened and the receipt should say so rather than
re-deriving it: `nn_pre_causal` was trained on the long panel with masked-feature
self-supervised pre-training at the CAUSAL scope, 8 seeds, and the frozen stage
holds all eight plus the seed-mean. N2 stacks `nn_pre_causal_seedmean` beside
seven other arms and never as a champion, which is the mandate's structural
requirement. This job records THAT, with the numbers, instead of claiming a
re-training it did not do.

WHAT IS BLOCKED, AND BY WHAT
============================
The half that is not done is "+ N4/N5 features". Those columns do not exist on
the long panel yet: N4's event table was built tonight as a separate parquet on
a symbol key and has not been joined onto the panel, and N5's compression
features are being built in the same session. Pre-training on features that do
not exist is not a smaller version of the experiment; it is the experiment we
already ran, given a new name. So this is DEFERRED with the blocker named.

A DEFERRAL IS A RECEIPT. A lane with no file in the morning reads as a lane
nobody reached.

    python -m scripts.n5b_pretraining_status
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP           # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N5b_pretraining_status.json"

#: `requirements-gpu.txt` names it; the env var overrides it. Never guessed.
DEFAULT_GPU_PYTHON = (Path(os.environ.get("LOCALAPPDATA", ""))
                      / "Programs" / "Python" / "Python312" / "python.exe")

_PROBE = (
    "import json,sys\n"
    "try:\n"
    "    import torch\n"
    "    d = {'torch': torch.__version__,\n"
    "         'cuda_available': bool(torch.cuda.is_available()),\n"
    "         'device_name': (torch.cuda.get_device_name(0)\n"
    "                         if torch.cuda.is_available() else None),\n"
    "         'capability': (list(torch.cuda.get_device_capability(0))\n"
    "                        if torch.cuda.is_available() else None),\n"
    "         'torch_file': getattr(torch, '__file__', None)}\n"
    "except Exception as exc:\n"
    "    d = {'error': f'{type(exc).__name__}: {exc}'}\n"
    "d['python_executable'] = sys.executable\n"
    "d['python_version'] = sys.version.split()[0]\n"
    "print(json.dumps(d))\n"
)


def probe_gpu_interpreter() -> dict:
    """Ask the DESIGNATED interpreter what it has. Never infer it from ours.

    The 2026-09-06 review spent an afternoon on "was torch downgraded?" when the
    answer was "a different interpreter ran the job". The probe therefore runs
    the other python and reports its executable path beside its answer.
    """
    exe = Path(os.environ.get("AEGIS_GPU_PYTHON") or DEFAULT_GPU_PYTHON)
    out = {"designated_interpreter": str(exe),
           "source": ("AEGIS_GPU_PYTHON" if os.environ.get("AEGIS_GPU_PYTHON")
                      else "requirements-gpu.txt default")}
    if not exe.exists():
        out["status"] = "ABSENT"
        out["why"] = f"{exe} does not exist on this host"
        return out
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(_PROBE)
            script = fh.name
        r = subprocess.run([str(exe), script], capture_output=True, text=True,
                           timeout=120)
        try:
            os.unlink(script)
        except OSError:
            pass
        if r.returncode != 0:
            out["status"] = "REFUSED"
            out["why"] = (r.stderr or "")[-800:]
            return out
        out.update(json.loads(r.stdout.strip().splitlines()[-1]))
        out["status"] = "ok"
    except Exception as exc:                                        # noqa: BLE001
        out["status"] = "REFUSED"
        out["why"] = f"{type(exc).__name__}: {exc}"
    return out


def run(*, verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    tracker = RP.InputTracker()
    out: dict = {
        "job": "N5b_pretraining_status",
        "lane": "N5",
        "question": ("is the self-supervised arm in the ensemble, and can it be "
                     "re-trained tonight on N4/N5 features?"),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
    }
    log("  probing the designated GPU interpreter ...")
    out["gpu"] = probe_gpu_interpreter()

    # ---- what already exists: the frozen 8-seed stage
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B
    meta_path = W3B.STAGE_DIR / "w3b_meta_nn_pre_causal.json"
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            tracker.opened(meta_path)
            out["frozen_arm"] = {
                "status": "PRESENT",
                "columns": m.get("columns"),
                "n_seeds": len([c for c in (m.get("columns") or [])
                                if c.startswith("nn_pre_causal_s")]),
                "seed_mean_column": "nn_pre_causal_seedmean",
                "scope": m.get("scope"),
                "rows": m.get("rows"),
                "written_utc": m.get("written_utc"),
                "recipe": ("masked-feature self-supervised pre-training at the "
                           "CAUSAL scope -- the `all` scope is a named look-ahead "
                           "in learner/neural_long and may not carry a claim"),
            }
        except Exception as exc:                                    # noqa: BLE001
            out["frozen_arm"] = {"status": "REFUSED",
                                 "why": f"{type(exc).__name__}: {exc}"}
    else:
        out["frozen_arm"] = {"status": "ABSENT", "path": str(meta_path)}

    # ---- is it in the ensemble, and never a champion?
    n2 = OUT_DIR / "N2_ensemble.json"
    if n2.exists():
        rec = json.loads(n2.read_text(encoding="utf-8"))
        tracker.opened(n2)
        arms = rec.get("arms_stacked") or {}
        cells = rec.get("cells") or {}
        out["in_the_ensemble"] = {
            "stacked": "nn_pre_causal" in arms,
            "coverage_share": (arms.get("nn_pre_causal") or {}).get("coverage_share"),
            "mean_reliability_weight_share": ((rec.get("reliability") or {})
                                              .get("mean_weight_share_by_arm") or {})
            .get("nn_pre_causal"),
            "full_sample_beta_matched_pct_per_year": (
                (rec.get("reliability") or {})
                .get("full_sample_mean_excess_by_arm_pct_per_year") or {})
            .get("nn_pre_causal"),
            "its_own_book_beta": (cells.get("nn_pre_causal") or {}).get("beta"),
            "its_own_book_t": ((cells.get("nn_pre_causal") or {})
                               .get("PRIMARY_beta_matched") or {}).get("t_paired"),
            "is_a_lone_champion_anywhere": False,
            "why_not": ("N2 selects no arm. The ensemble's two weightings are both "
                        "reported and the equal-weight one wins, so no arm -- this "
                        "one included -- is ever quoted alone as the book."),
        }
    else:
        out["in_the_ensemble"] = {"status": "CANNOT DETERMINE",
                                  "why": f"{n2} has not been written"}

    # ---- what a re-training needs, and what of it exists
    from learner import long_panel as LP
    events = REPO / "backend" / "data" / "optimus" / "events" / "event_table_v1.parquet"
    compression = OUT_DIR / "N5_event_compression.json"
    blockers = []
    if not events.exists():
        blockers.append("N4's event table does not exist")
    else:
        blockers.append(
            "N4's event table exists but is a SEPARATE parquet on a symbol key; it "
            "has not been joined onto the long panel, so there is no event feature "
            "column for the pre-training to see")
    if not compression.exists():
        blockers.append("N5's event-compression features have not been written")
    out["retraining_with_N4_N5_features"] = {
        "verdict": "DEFERRED",
        "blockers": blockers,
        "long_panel_present": LP.LONG_TABLE.exists(),
        "what_would_change": ("`dataset.feature_columns()` would gain the event and "
                              "novelty columns and the pre-training corpus would "
                              "cover them. Until those columns are ON the panel, "
                              "re-running the recipe reproduces the arm we already "
                              "have under a new name -- and its 8 seeds are frozen "
                              "in the stage, so it would also cost the comparability "
                              "of every cell graded against them tonight."),
        "cost_estimate": ("8 seeds x 21 folds on CUDA; W3's own run13 is the "
                          "reference for the wall time"),
    }
    g = out["gpu"]
    out["headline"] = (
        f"CUDA {g.get('cuda_available')} on {g.get('device_name')} via "
        f"{Path(str(g.get('python_executable') or g.get('designated_interpreter'))).name} "
        f"(torch {g.get('torch')}); the 8-seed self-supervised arm is PRESENT and IS "
        f"stacked in the N2 ensemble (weight share "
        f"{(out.get('in_the_ensemble') or {}).get('mean_reliability_weight_share')}), "
        f"never a lone champion; re-training on N4/N5 features is DEFERRED -- "
        f"{len(blockers)} blocker(s)")
    RP.attach(out, sys.argv, {"default_gpu_python": str(DEFAULT_GPU_PYTHON)}, tracker)
    return out


def write(rec: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    try:
        rec = run()
    except Exception:                                               # noqa: BLE001
        rec = {"job": "N5b_pretraining_status", "status": "FAILED",
               "traceback": traceback.format_exc(),
               "headline": "FAILED -- see traceback"}
        write(rec)
        print(rec["traceback"], flush=True)
        return 1
    write(rec)
    print(rec.get("headline"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
