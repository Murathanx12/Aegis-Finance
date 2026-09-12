"""L4 -- the Qwen3-30B-A3B arm's IDLE measurement protocol, written before it is run.

THIS JOB DOES NOT START THE MODEL SERVER, AND IT DOES NOT STOP ONE. The desktop
shell owns `llama-server`'s lifetime, and a night job that starts a 17 GB model
because it wanted a number is how two sessions end up fighting over a card. So
with the reader down, this REFUSES BY NAME -- `PENDING_MODEL` -- and writes:

* the exact sweep it will run and the stop condition;
* the file check, which is the frozen identity of the candidate reader
  (present? bytes? sha256?);
* the frozen R2 prompts it will measure on, by hash, imported from
  `r2_trial` rather than retyped;
* the refusal-rate protocol, with "refusal" defined by the code that already
  defines it;
* and the wall-time arithmetic, from R2's OWN measured token counts, so the
  question "is this arm even practical to run nightly" is answered by a number
  before a single token is spent.

WHY THE PROTOCOL IS THE DELIVERABLE. `HANDOFF_2026-09-10` section 3's Qwen3
numbers -- 17.28 GB, `--n-cpu-moe 48` -> 1,854 MiB VRAM, 19.8 tok/s generation,
5.6 tok/s prompt eval -- were taken while PyInstaller saturated all 20 cores.
The doc calls them a lower bound and names re-measuring idle as the next
session's first task. A run that happens when the reader is up must ask the
SAME question this file froze, not a similar one thought up on the night.

A MODEL SWAP IS A NEW ARM. `TRIAL-R2-monthly-news-digest-read.md` section 6:
"A 14B, a different quantisation of the same weights, or a different server
build is a different reader and gets its own registration and its own place in
the multiplicity count." So `R2-Qwen3` is registered beside R2, never as an
upgrade to it, and adoption needs BOTH its own control-adjusted number beating
R2's on the same blocks AND a Lookahead Propensity no worse than R2's -- a win
on the first driven by the second getting worse is not a win.

Licence: PRODUCT_EXPERIMENT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_checkpoint import atomic_write_json            # noqa: E402
from scripts.night_n3_frozen_embedding_head import OUT_DIR, _now  # noqa: E402

JOB = "L4_qwen3_measure"
LICENCE = "PRODUCT_EXPERIMENT"
ARM = "R2-Qwen3"

MODEL_REPO = "Qwen/Qwen3-30B-A3B-Instruct-2507"
GGUF_REPO = "bartowski/Qwen_Qwen3-30B-A3B-Instruct-2507-GGUF"
GGUF_FILE = "Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
LICENSE = "apache-2.0"

#: the roadmap's own sweep, descending -- fewer MoE layers on the CPU as the
#: number falls, so more of the model sits on the card
N_CPU_MOE_SWEEP = (48, 40, 32, 24)

#: the 5060's usable budget and the OS/desktop floor implied by HANDOFF
#: 2026-09-10 section 3 (8,151 total - 6,866 free = 1,285 MiB resident)
CARD_TOTAL_MIB = 8151
DESKTOP_FLOOR_MIB = 1285
STOP_WITHIN_MIB = 500

#: HANDOFF 2026-09-10 section 3, taken while PyInstaller used all 20 cores
CONTENDED = {"file_gb": 17.28, "n_cpu_moe": 48, "vram_mib": 1854,
             "generation_tok_s": 19.8, "prompt_eval_tok_s": 5.6,
             "incumbent_generation_tok_s": 41.4,
             "note": "a LOWER BOUND -- all 20 cores were saturated by a PyInstaller build"}

REFUSAL_DIGESTS = 200


def _sha256_file(p: Path, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_check(with_hash: bool = True) -> dict:
    """Present? How many bytes? Which sha256? The file IS the frozen identity."""
    from backend.services import llama_server

    path = llama_server.LLAMA_MODEL.parent / GGUF_FILE
    out = {"expected_file": GGUF_FILE, "searched_at": str(path), "present": path.is_file(),
           "gguf_repo": GGUF_REPO, "hub_repo": MODEL_REPO, "license": LICENSE,
           "quant": "Q4_K_M -- the same quant level the incumbent runs, for an "
                    "apples-to-apples file-size and VRAM comparison"}
    if not path.is_file():
        out["sha256"] = None
        out["status"] = ("ABSENT -- download it from the GGUF repo above and re-run; the "
                         "sha256 computed at that moment is what freezes this arm's identity")
        return out
    out["bytes"] = int(path.stat().st_size)
    out["gigabytes"] = round(out["bytes"] / 1e9, 3)
    out["gibibytes"] = round(out["bytes"] / (1 << 30), 2)
    out["size_note"] = ("HANDOFF 2026-09-10 section 3 says 17.28 GB; that is GiB. The same "
                        "18,556,686,752 bytes is 18.56 GB decimal and 17.28 GiB binary -- "
                        "one file, two units, and NOT evidence the file changed.")
    if with_hash:
        t0 = time.time()
        out["sha256"] = _sha256_file(path)
        out["sha256_seconds"] = round(time.time() - t0, 1)
    out["status"] = "PRESENT"
    return out


def reader_state() -> dict:
    """Ask, never start. Ask, never stop."""
    from backend.services import llama_server

    st = llama_server.status()
    return {"listening": st["listening"], "ready": st["ready"], "pid": st["pid"],
            "foreign": st["foreign"], "model_loaded": st["model"], "vram": st["vram"],
            "detail": st["detail"],
            "this_job_never_starts_or_stops_it": (
                "the desktop shell owns llama-server's lifetime; a night job that started a "
                "17 GB model to get a number is two sessions fighting over one card")}


def protocol() -> dict:
    """The exact run, frozen now so the run that happens asks this question."""
    from backend.services.portfolio_intelligence import r2_trial

    return {
        "step_1_idle_precondition": {
            "gpu": "scripts/gpu_guard.contention() -- the SAME helper E2 uses, not a second "
                   "ad hoc nvidia-smi parse",
            "refuse_above_mib": 3072,
            "cpu": "no PyInstaller build, no night-factory job, no other llama-server; the "
                   "2026-09-10 numbers are a lower bound precisely because this was not true",
        },
        "step_2_sweep": {
            "n_cpu_moe": list(N_CPU_MOE_SWEEP),
            "env": "AEGIS_LLAMA_N_CPU_MOE",
            "between_settings": "stop() then start(), PID-owned -- never taskkill /IM",
            "measure_at_each": ["vram_mib (llama_server.vram())", "load_seconds",
                                "prompt_eval_tok_s", "generation_tok_s"],
            "benchmark_prompt": ("R2's OWN frozen prompts, so the number is comparable to R2's "
                                 "and not to a differently-shaped prompt"),
            "stop_condition": (f"stop descending once VRAM is within {STOP_WITHIN_MIB} MiB of "
                               f"{CARD_TOTAL_MIB} - {DESKTOP_FLOOR_MIB} = "
                               f"{CARD_TOTAL_MIB - DESKTOP_FLOOR_MIB} MiB usable"),
            "decisive_number": ("prompt-eval tok/s. R2's digests are a month of news per name, "
                                "so generation speed is nearly irrelevant beside how fast the "
                                "reader can READ"),
        },
        "step_3_refusal_rate": {
            "n_digests": REFUSAL_DIGESTS,
            "drawn_from": "PANEL-B's per-name-month digests (18,501 cells over 19 blocks)",
            "build": "the PLAIN Instruct build -- abliterated only if refusals exceed the "
                     "incumbent's, and then as its own arm R2-Qwen3-abliterated, never a "
                     "silent swap-in",
            "a_refusal_is": ["a non-JSON / unparseable reply (night_r2_monthly_llm.parse "
                             "returns no direction)",
                             "the model declining to answer",
                             "backend.services.llm_language.refuse() firing on a >10% "
                             "non-Latin-script reply -- the language pin applies to a local "
                             "reader too; a model that code-switches is still a bad reader"],
            "compared_to": ("Qwen2.5-7B's own refusal rate on the SAME 200 prompts -- not to "
                            "an absolute zero, because the incumbent's rate is not zero either"),
        },
        "frozen_prompts": r2_trial.fingerprint(),
        "step_4_registration": {
            "arm": ARM,
            "beside": "R2 (Qwen2.5-7B-Instruct-Q4_K_M)",
            "same": ["PANEL-B", "the shuffled-digest control (seed 20260909)",
                     "read_minus_shuffled_control", "Newey-West lag-2 t on monthly blocks",
                     "25 bps a side on realised turnover"],
            "block_count": ("19 monthly blocks -- PANEL-B's, confirmed from "
                            "R2_widened_panelB_run01.json ('18501 cells over 19 month "
                            "blocks'). NOT 112: that is PANEL-A's count and PANEL-A is a "
                            "different panel."),
            "pre_registered_before": "the first Qwen3 digest is read",
        },
        "step_5_decision_rule": {
            "adopt_only_if": [
                "R2-Qwen3's OWN read_minus_shuffled_control beats R2's own, on the SAME "
                "blocks, at the same significance bar R2 uses",
                "AND its Lookahead Propensity (lane X item L3) is NOT worse than R2's",
            ],
            "a_pass_on_the_first_alone_is": "CONDITIONAL_ON_LAP, never ADOPTED",
            "why": ("a bigger, differently-trained model reading the same anonymised digest "
                    "may simply have memorised more pre-cutoff fact; a win driven by that is "
                    "not a win"),
        },
    }


def wall_time() -> dict:
    """Is this arm practical to run nightly? From R2's OWN measured token counts."""
    # PANEL-A, night_factory_2026-09-08/R2_monthly_llm_2015_2024_run01.json:
    # usage.tokens_in 5,098,607 and tokens_out 216,677 over 15,433 calls
    # (7,417 arm + 7,417 control + 299 + 300 canary), elapsed 5,854.2 s.
    calls_a, tin, tout, elapsed_a = 15433, 5_098_607, 216_677, 5854.2
    p_tok = tin / calls_a
    c_tok = tout / calls_a
    panelb_calls = 18_501 * 2                     # the arm and its shuffled control

    incumbent_s_per_call = elapsed_a / calls_a
    q3 = CONTENDED["prompt_eval_tok_s"], CONTENDED["generation_tok_s"]
    q3_s_per_call = p_tok / q3[0] + c_tok / q3[1]
    return {
        "source": ("R2 PANEL-A's own usage block -- 5,098,607 tokens in and 216,677 out over "
                   "15,433 calls in 5,854.2s. Not guessed."),
        "mean_prompt_tokens": round(p_tok, 1),
        "mean_completion_tokens": round(c_tok, 1),
        "panelB_calls_arm_plus_control": panelb_calls,
        "incumbent_qwen2_5_7b": {
            "measured_seconds_per_call": round(incumbent_s_per_call, 3),
            "panelB_hours": round(panelb_calls * incumbent_s_per_call / 3600, 2),
        },
        "qwen3_30b_a3b_at_the_CONTENDED_rates": {
            "prompt_eval_tok_s": q3[0], "generation_tok_s": q3[1],
            "seconds_per_call": round(q3_s_per_call, 1),
            "panelB_hours": round(panelb_calls * q3_s_per_call / 3600, 1),
            "panelB_days": round(panelb_calls * q3_s_per_call / 86400, 1),
        },
        "what_this_decides": (
            "at the contended prompt-eval rate the PANEL-B read is a multi-WEEK job, so the "
            "idle re-measurement is not a tidiness exercise -- it is the difference between "
            "an arm that can be run and one that cannot. If idle prompt-eval does not come "
            "up by roughly an order of magnitude, R2-Qwen3 is not a nightly arm at any "
            "n_cpu_moe and the honest move is to say so rather than to start it."),
        "arithmetic": ("digests x (mean_prompt_tokens / prompt_eval_tok_s + "
                       "mean_completion_tokens / generation_tok_s)"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L4 Qwen3-30B-A3B idle measurement protocol")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="skip the 17 GB sha256")
    ap.add_argument("--stage", default="raw")
    args = ap.parse_args(argv)

    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (
        OUT_DIR / f"{JOB}_run{args.run:02d}{'_smoke' if args.smoke else ''}.json")

    receipt = {
        "job": JOB, "licence": LICENCE, "run": args.run, "smoke": bool(args.smoke),
        "stage": args.stage, "llm_spend_usd": 0.0,
        "arm": ARM,
        "question": ("Idle, not contended: what does Qwen3-30B-A3B-Instruct-2507 Q4_K_M cost "
                     "in VRAM and buy in prompt-eval tok/s at each --n-cpu-moe, does the plain "
                     "Instruct build refuse any of R2's frozen prompts, and is the resulting "
                     "wall time compatible with a nightly arm?"),
        "inputs": [GGUF_FILE],
        "model_identity": file_check(with_hash=not args.smoke),
        "reader": reader_state(),
        "contended_measurement_being_superseded": CONTENDED,
        "protocol": protocol(),
        "wall_time": wall_time(),
        "status": "running", "written_utc": _now(),
    }

    st = receipt["reader"]
    present = receipt["model_identity"]["present"]
    if st["ready"]:
        receipt["status"] = "REFUSED"
        receipt["verdict"] = (
            "REFUSED: llama-server is UP and this job does not measure against a reader it did "
            "not sequence. The idle sweep needs the card to itself and needs to restart the "
            "server between n_cpu_moe settings, which is the desktop shell's job to sequence.")
        receipt["headline"] = f"reader is up as PID {st['pid']} -- L4 will not measure around it"
    else:
        receipt["status"] = "PENDING_MODEL"
        receipt["verdict"] = (
            f"PENDING_MODEL: the reader is not answering ({st['detail']}) and this job does not "
            f"start it. The GGUF is {'PRESENT' if present else 'ABSENT'} and the protocol above "
            f"is frozen, so the run that happens when the server is up asks this question "
            f"rather than a similar one.")
        wt = receipt["wall_time"]
        receipt["headline"] = (
            f"{ARM} PENDING_MODEL: file {'present' if present else 'ABSENT'}"
            + (f" ({receipt['model_identity'].get('gigabytes')} GB, sha256 "
               f"{str(receipt['model_identity'].get('sha256'))[:12]}...)" if present else "")
            + f"; sweep n_cpu_moe {list(N_CPU_MOE_SWEEP)}; refusal test on {REFUSAL_DIGESTS} "
            f"PANEL-B digests; at the CONTENDED 5.6 tok/s prompt eval PANEL-B would take "
            f"{wt['qwen3_30b_a3b_at_the_CONTENDED_rates']['panelB_days']} days against the "
            f"incumbent's {wt['incumbent_qwen2_5_7b']['panelB_hours']} hours")
    receipt["next_test"] = (
        "run this file with the machine idle and the desktop shell sequencing llama-server: "
        "the sweep, then the 200-digest refusal test against Qwen2.5-7B's rate on the SAME "
        "prompts, then -- only if the wall time permits -- the registered PANEL-B read")
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = _now()
    atomic_write_json(out, receipt, indent=1)
    print(receipt["headline"])
    print(receipt["verdict"])
    print(f"receipt: {out}")
    return 0


def L4_qwen3_measure(smoke: bool = False, run: int = 1) -> dict:
    out = OUT_DIR / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    argv = ["--run", str(run), "--out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
