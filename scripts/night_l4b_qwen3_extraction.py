"""L4b -- the comparison that DECIDES whether Qwen3-30B replaces the 7B for L2 typing.

    python -m scripts.night_l4b_qwen3_extraction                # 240 items x (7B, 30B), $0
    python -m scripts.night_l4b_qwen3_extraction --freeze-only  # freeze + verify the inputs
    python -m scripts.night_l4b_qwen3_extraction --smoke        # 8 items per arm

L4 answers "what does the 30B cost and how fast is it". That does not say
whether it READS better, and speed without accuracy is not a reason to swap a
reader. The accuracy question already has a frozen test: bake-off E-G1
(`scripts/bakeoff_eg1.py`, receipt `model_routing/bakeoff_E-G1_2026-09-26.json`)
graded 240 dated news items into typed fields -- ticker, event_type, direction
-- against `analyst/target_revisions.parquet`, and the incumbent 7B scored
62.2% field accuracy against DeepSeek's 63.1%.

This job re-reads THE SAME 240 items with the SAME wire system prompt (its
sha256 must equal the 09-26 receipt's), the same user template, the same
parser and the same grader (`model_routing.parse_extraction` /
`grade_extraction` / `_summarise`), through two LOCAL arms only:

* `local_7b`  -- Qwen2.5-7B-Instruct Q4_K_M, the incumbent L2 reader;
* `local_30b` -- Qwen3-30B-A3B-Instruct-2507 Q4_K_M at L4's best measured
  `--n-cpu-moe` (else `config.L4B_QWEN3_N_CPU_MOE_DEFAULT`, and it says so).

Both arms run on servers this job starts and stops BY PID (`OwnedServer` from
L4), one at a time, on L4's named port through one client, so the only
difference between them is the weights. $0.

THE DECISION RULE IS WRITTEN INTO THE RECEIPT BEFORE THE FIRST ITEM IS READ:
the 30B replaces the 7B for L2 typing only if its field accuracy is higher by
>= `L4B_MIN_GAIN_PTS` points with the PAIRED difference's t >= `L4B_MIN_T`,
AND the nightly typing backlog at its measured seconds/item fits in
`L4B_NIGHT_HOURS`. Otherwise `KEEP_7B`, and the 30B file becomes a candidate to
move to the archive drive (17.28 GiB on a C: that sat at 0 bytes on 09-27).
An incomplete comparison decides nothing: `INCOMPLETE`, never a quiet KEEP.

THE INPUTS ARE FROZEN, not re-sampled. The 240 items are rebuilt once from the
corpus with the 09-26 seed and parameters, checked against the 09-26 receipt
(census, item ids and strata, the first user message byte for byte, the wire
system sha256), and written to `bakeoff_E-G1_items_frozen.json` with their own
sha256. Every later run reads that file; a corpus that drifted is a REFUSAL,
never a silently different test. The file carries news bodies and stays local
(`news_corpus/_frozen/`, gitignored with the corpus); its sha256 is in every
receipt.

Licence: PRODUCT_EXPERIMENT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                # noqa: E402
from scripts import night_l4_qwen3_measure as L4                  # noqa: E402

JOB = "L4b_qwen3_extraction"
LICENCE = "PRODUCT_EXPERIMENT"
ARMS = ("local_7b", "local_30b")

MIN_GAIN_PTS = float(getattr(_cfg, "L4B_MIN_GAIN_PTS", 3.0))
MIN_T = float(getattr(_cfg, "L4B_MIN_T", 2.0))
NIGHT_HOURS = float(getattr(_cfg, "L4B_NIGHT_HOURS", 8.0))
MAX_MINUTES = float(getattr(_cfg, "L4B_MAX_MINUTES", 80.0))
LOOKBACK_DAYS = int(getattr(_cfg, "L4B_BACKLOG_LOOKBACK_DAYS", 7))
BACKLOG_FALLBACK = int(getattr(_cfg, "L4B_BACKLOG_ROWS_FALLBACK", 3000))
QWEN3_MOE_DEFAULT = int(getattr(_cfg, "L4B_QWEN3_N_CPU_MOE_DEFAULT", 48))

#: the frozen test this job re-reads -- the 2026-09-26 E-G1 run
SOURCE_RECEIPT = "bakeoff_E-G1_2026-09-26.json"
SOURCE_SEED = 20260926
SOURCE_N, SOURCE_N_MATCHED = 240, 96
FROZEN_ITEMS = "bakeoff_E-G1_items_frozen.json"
#: census keys that grow with the corpus by construction (rows AFTER seen_max
#: keep arriving) and so are not evidence the sample moved
GROWING_CENSUS_KEYS = ("rows_read", "after_seen_max")
FLUSH_EVERY = int(getattr(_cfg, "MODEL_ROUTING_BAKEOFF_FLUSH_EVERY", 20))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def routing_dir() -> Path:
    from backend.services import model_routing as MR
    return MR.receipt_dir()


def frozen_path() -> Path:
    """Beside the corpus it was cut from, in a `_`-prefixed folder: gitignored
    with the corpus (it carries news bodies) and skipped by `bakeoff_sample`'s
    and `nightly_typing_rows`' folder walks."""
    from backend.services import model_routing as MR
    return MR.ledger_dir() / "news_corpus" / "_frozen" / FROZEN_ITEMS


# =============================================================== frozen inputs

def freeze_items(*, source: Path | None = None, out: Path | None = None,
                 sample_fn=None) -> dict:
    """Load the frozen 240 items, or rebuild + verify + freeze them once.

    Returns `{"ok", "items", "sha256", "path", "checks", "reason"}`. A rebuild
    that does not reproduce the 09-26 receipt is `ok: False` -- the test is
    frozen, so a different sample is a different test and is refused.
    """
    from backend.services import llm_language as LL
    from backend.services import model_routing as MR

    out = Path(out or frozen_path())
    if out.is_file():
        blob = json.loads(out.read_text(encoding="utf-8"))
        items = blob["items"]
        sha = _sha(json.dumps(items, sort_keys=True))
        if sha != blob.get("items_sha256"):
            return {"ok": False, "reason": (f"{out.name} does not hash to its own recorded "
                                            f"sha256 ({sha[:12]} vs "
                                            f"{str(blob.get('items_sha256'))[:12]}); refusing a "
                                            "tampered frozen input"), "path": str(out)}
        return {"ok": True, "items": items, "sha256": sha, "path": str(out),
                "checks": blob.get("checks"), "frozen_utc": blob.get("frozen_utc"),
                "wire_system_sha256": blob.get("wire_system_sha256")}

    src = Path(source or routing_dir() / SOURCE_RECEIPT)
    if not src.is_file():
        return {"ok": False, "reason": f"the source receipt {src} is absent", "path": str(out)}
    ref = json.loads(src.read_text(encoding="utf-8"))
    sample_fn = sample_fn or MR.bakeoff_sample
    items, census = sample_fn(n=SOURCE_N, n_matched=SOURCE_N_MATCHED, seed=SOURCE_SEED)
    checks: dict = {}
    ref_c = ref.get("census") or {}
    checks["census_mismatch"] = {k: [ref_c.get(k), census.get(k)] for k in ref_c
                                 if k not in GROWING_CENSUS_KEYS and ref_c.get(k) != census.get(k)}
    strata = {r["item_id"]: r["item_stratum"] for r in ref.get("rows") or []}
    checks["n_items"] = len(items)
    checks["ids_and_strata_match"] = (
        len(items) == int(ref.get("n_items") or -1)
        and all(strata.get(i["item_id"]) == i["gold"]["stratum"] for i in items))
    checks["first_user_message_matches"] = (
        bool(items) and MR.bakeoff_user(items[0]) == ref.get("user_template_example"))
    wire = LL.pin(MR.bakeoff_system())
    checks["wire_system_sha256_matches"] = _sha(wire) == ref.get("system_sha256")
    ok = (not checks["census_mismatch"] and checks["ids_and_strata_match"]
          and checks["first_user_message_matches"] and checks["wire_system_sha256_matches"])
    if not ok:
        return {"ok": False, "checks": checks, "path": str(out),
                "reason": ("the rebuilt sample does NOT reproduce the 09-26 E-G1 receipt; a "
                           "different sample is a different test -- refused, not re-run")}
    sha = _sha(json.dumps(items, sort_keys=True))
    blob = {"receipt": "bakeoff_items_frozen", "bakeoff": MR.BAKEOFF_ID,
            "source_receipt": src.name, "seed": SOURCE_SEED, "n": SOURCE_N,
            "n_matched": SOURCE_N_MATCHED, "frozen_utc": _now(), "checks": checks,
            "census_at_freeze": census, "wire_system_sha256": _sha(wire),
            "items_sha256": sha, "items": items}
    from backend.services import disk_guard
    disk_guard.atomic_write_json(out, blob)
    return {"ok": True, "items": items, "sha256": sha, "path": str(out), "checks": checks,
            "frozen_utc": blob["frozen_utc"], "wire_system_sha256": _sha(wire)}


# =============================================================== the statistics

def item_scores(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """{item_id: (correct fields, graded fields)} -- the E-G1 pooled definition."""
    out = {}
    for r in rows:
        g = r.get("grade") or {}
        vals = [g.get(k) for k in ("ticker", "event_type", "direction") if g.get(k) is not None]
        out[r["item_id"]] = (sum(1 for v in vals if v), len(vals))
    return out


def paired_field_accuracy(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """B minus A on the SAME items. Pooled field accuracy (the E-G1 metric) and
    its paired SE: diff = mean(d_i)/mean(g_i), SE = sd(d_i)/sqrt(n)/mean(g_i),
    where d_i is B's minus A's correct-field count on item i and g_i the number
    of graded fields (a function of the gold only, so equal across arms)."""
    a, b = item_scores(rows_a), item_scores(rows_b)
    ids = sorted(set(a) & set(b))
    n = len(ids)
    if n < 2:
        return {"n": n, "diff_pts": None, "se_pts": None, "t": None,
                "reason": "fewer than 2 paired items"}
    d = [b[i][0] - a[i][0] for i in ids]
    g = [a[i][1] for i in ids]
    gbar = sum(g) / n
    acc_a = sum(a[i][0] for i in ids) / sum(g)
    acc_b = sum(b[i][0] for i in ids) / sum(g)
    diff = (sum(d) / n) / gbar
    sd = statistics.stdev(d)
    se = sd / math.sqrt(n) / gbar
    t = (diff / se) if se > 0 else None
    return {"n": n, "acc_a": round(acc_a, 4), "acc_b": round(acc_b, 4),
            "diff_pts": round(100 * diff, 2), "se_pts": round(100 * se, 2),
            "t": None if t is None else round(t, 2),
            "n_b_better": sum(1 for x in d if x > 0), "n_a_better": sum(1 for x in d if x < 0),
            "n_tied": sum(1 for x in d if x == 0),
            "definition": "B minus A, pooled field accuracy over ticker/event_type/direction"}


def decision_rule() -> dict:
    """The rule, as data, so it is written before the run and read after it."""
    return {
        "replace_7b_for_l2_typing_only_if": [
            f"field accuracy (30B - 7B) >= {MIN_GAIN_PTS:g} points on the SAME 240 items",
            f"AND the paired difference's t >= {MIN_T:g}",
            f"AND the nightly typing backlog at the 30B's measured mean seconds/item fits in "
            f"{NIGHT_HOURS:g} hours",
        ],
        "otherwise": ("KEEP_7B -- and the 30B file is a candidate to move to the archive "
                      "drive (a decided KEEP is not a reason to hold 17.28 GiB on C:)"),
        "incomplete": ("INCOMPLETE if either arm did not read every item -- an unfinished "
                       "comparison decides nothing, and never defaults to KEEP"),
        "min_gain_pts": MIN_GAIN_PTS, "min_t": MIN_T, "night_hours": NIGHT_HOURS,
        "scope": ("L2 typing ONLY. R2-Qwen3 (the monthly digest read) keeps its own "
                  "registered two-condition rule in TRIAL-R2 s.6 / L4's protocol"),
    }


def decide(paired: dict, projected_hours: float | None, *, n_expected: int,
           n_a: int, n_b: int, min_gain_pts: float = MIN_GAIN_PTS, min_t: float = MIN_T,
           night_hours: float = NIGHT_HOURS) -> dict:
    """Apply `decision_rule()`. Pure: every input is on the receipt."""
    if n_a < n_expected or n_b < n_expected or paired.get("n", 0) < n_expected:
        return {"decision": "INCOMPLETE",
                "why": (f"7B read {n_a}, 30B read {n_b}, paired {paired.get('n')} of "
                        f"{n_expected}; an unfinished comparison decides nothing")}
    gain = paired.get("diff_pts")
    t = paired.get("t")
    fails = []
    if gain is None or gain < min_gain_pts:
        fails.append(f"gain {gain} pts < {min_gain_pts:g}")
    if t is None or t < min_t:
        fails.append(f"paired t {t} < {min_t:g}" if t is not None
                     else "paired t undefined (zero variance)")
    if projected_hours is None or projected_hours > night_hours:
        fails.append(f"projected nightly typing {projected_hours} h > {night_hours:g} h"
                     if projected_hours is not None else "nightly typing time not projectable")
    if not fails:
        return {"decision": "REPLACE_7B_FOR_L2",
                "why": (f"+{gain} pts (t {t}) and {projected_hours} h <= {night_hours:g} h: the "
                        "30B replaces the 7B for L2 typing -- a routing change a human makes, "
                        "not this job"),
                "failed_conditions": []}
    return {"decision": "KEEP_7B", "why": "; ".join(fails), "failed_conditions": fails,
            "archive_candidate": ("the 30B GGUF (17.28 GiB) is a candidate to move to the "
                                  "archive drive; L4's receipt keeps its sha256 so it can come "
                                  "back as the same arm")}


# =============================================================== the backlog

def nightly_typing_rows(*, corpus_dir: Path | None = None, today: datetime | None = None,
                        lookback_days: int = LOOKBACK_DAYS) -> dict:
    """How many rows L2 must type per night: the news corpus's mean daily inflow
    over the last `lookback_days` complete days, by `first_seen_utc`. Falls back
    to `config.L4B_BACKLOG_ROWS_FALLBACK` -- and SAYS so -- when unmeasurable."""
    from backend.services import model_routing as MR
    corpus_dir = Path(corpus_dir or MR.ledger_dir() / "news_corpus")
    today = today or datetime.now(timezone.utc)
    days = {(today - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(1, lookback_days + 1)}
    counts = {d: 0 for d in days}
    try:
        for f in corpus_dir.glob("*/*.jsonl"):
            if f.parent.name.startswith("_"):
                continue
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    i = line.find('"first_seen_utc"')
                    if i < 0:
                        continue
                    d = line[i:i + 40].split(":", 1)[1].strip().strip('"')[:10]
                    if d in counts:
                        counts[d] += 1
    except OSError as exc:
        return {"rows_per_night": BACKLOG_FALLBACK, "source": "FALLBACK",
                "detail": f"corpus unreadable ({type(exc).__name__}); config fallback used"}
    total = sum(counts.values())
    if total == 0:
        return {"rows_per_night": BACKLOG_FALLBACK, "source": "FALLBACK",
                "detail": f"no corpus rows first seen in the last {lookback_days} days; "
                          "config fallback used"}
    return {"rows_per_night": int(round(total / lookback_days)), "source": "MEASURED",
            "detail": f"mean daily first_seen inflow over {lookback_days} complete days",
            "by_day": dict(sorted(counts.items()))}


# =============================================================== the arms

def local_call(port: int, wire_system: str, user: str) -> dict:
    """One extraction through the named server, graded exactly as E-G1 grades.

    Mirrors `llm_analyzer.call_named('local', ...)` at the wire: the pinned
    system, temperature 0.0, max_tokens 150; an empty reply and a >10%
    non-Latin reply are refusals (the language pin binds a local reader too).
    """
    from backend.services import llm_language as LL
    from backend.services import model_routing as MR

    r = L4.chat(port, {"system": wire_system, "user": user, "max_tokens": 150},
                cache_prompt=True)
    text = r.get("text")
    status = "OK"
    if r.get("error"):
        status = "ERROR"
    elif not text:
        status = "REFUSED_EMPTY_CONTENT"
    elif LL.non_latin_share(text) > LL.NON_LATIN_BAR:
        status = "LANGUAGE_REFUSED"
    pred, why = (MR.parse_extraction(text) if status == "OK" else (None, status))
    return {"model": r.get("served_model"), "status": status, "cost_usd": 0.0,
            "cost_status": "LISTED", "latency_s": r.get("wall_s"), "pred": pred,
            "refusal": why, "raw": (text or "")[:300] or None, "error": r.get("error"),
            "prompt_n": r.get("prompt_n"), "prompt_tok_s": r.get("prompt_tok_s"),
            "gen_tok_s": r.get("gen_tok_s")}


def run_arm(arm: str, cfg, items: list[dict], wire_system: str, *, add, budget,
            launcher: list[str] | None = None, health_wait_s: float = L4.HEALTH_WAIT_S,
            call=None, sample_every: int = FLUSH_EVERY) -> dict:
    """Start `cfg`, read every item, stop BY PID (always), check VRAM.
    `budget` is an `L4.AwakeBudget`: a machine that slept does not spend it."""
    from backend.services import model_routing as MR
    call = call or local_call
    info: dict = {"arm": arm, "model": Path(cfg.model).name, "n_cpu_moe": cfg.n_cpu_moe,
                  "config": {k: getattr(cfg, k) for k in ("name", "model", "port", "n_cpu_moe")},
                  "vram_baseline_mib": L4.vram_used_mib(),
                  "ram_available_before_gib": L4.avail_ram_gb(), "n_read": 0}
    stop_reason = lambda: L4.stop_file_reason() or ("budget" if budget.exhausted() else None)  # noqa: E731
    peaks = {"vram": [], "rss": [], "ram": []}
    with L4.OwnedServer(cfg, JOB, launcher=launcher, health_wait_s=health_wait_s,
                        should_stop=stop_reason) as srv:
        st = srv.start()
        info["start"] = {k: st.get(k) for k in ("ready", "action", "pid", "reason",
                                                "load_seconds", "exit_code")}
        info["server_pid"] = st.get("pid")
        if st.get("ready"):
            info["vram_loaded_mib"] = L4.vram_used_mib()
            info["server_rss_mib"] = L4.proc_rss_mib(srv.pid)
            info["ram_available_loaded_gib"] = L4.avail_ram_gb()
            peaks["vram"].append(info["vram_loaded_mib"])
            peaks["rss"].append(info["server_rss_mib"])
            peaks["ram"].append(info["ram_available_loaded_gib"])
            t0 = time.time()
            toks: list[float] = []
            for it in items:
                why = stop_reason()
                if why:
                    info["interrupted"] = why
                    break
                res = call(cfg.port, wire_system, MR.bakeoff_user(it))
                res["arm"] = arm
                if isinstance(res.get("gen_tok_s"), (int, float)):
                    toks.append(float(res["gen_tok_s"]))
                add(it, res)
                info["n_read"] += 1
                if sample_every and info["n_read"] % int(sample_every) == 0:
                    peaks["vram"].append(L4.vram_used_mib())
                    peaks["rss"].append(L4.proc_rss_mib(srv.pid))
                    peaks["ram"].append(L4.avail_ram_gb())
            info["read_seconds"] = round(time.time() - t0, 1)
            info["generation_tok_s_median"] = (round(statistics.median(toks), 2)
                                               if toks else None)
    info["stop"] = srv.stopped
    info["vram_after"] = L4.wait_vram_back(info["vram_baseline_mib"])
    num = lambda xs: [x for x in xs if isinstance(x, (int, float))]      # noqa: E731
    info["vram_peak_mib"] = max(num(peaks["vram"]), default=None)
    info["server_rss_peak_mib"] = max(num(peaks["rss"]), default=None)
    info["ram_available_min_gib"] = min(num(peaks["ram"]), default=None)
    return info


def l4_best_n_cpu_moe(root: Path | None = None) -> dict:
    """L4's best measured --n-cpu-moe from the newest receipt that has one."""
    root = Path(root or REPO / "backend" / "data" / "optimus")
    cands = sorted(root.glob("night_factory_*/L4_qwen3_measure_run*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        if p.name.endswith("_smoke.json"):
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        best = r.get("best_setting") or {}
        if best.get("n_cpu_moe") is not None:
            return {"n_cpu_moe": int(best["n_cpu_moe"]), "source": str(p.relative_to(root)),
                    "prompt_eval_tok_s": best.get("prompt_eval_tok_s_r2_median")}
    return {"n_cpu_moe": QWEN3_MOE_DEFAULT, "source": "DEFAULT",
            "detail": "no L4 receipt with a measured best setting; config default used"}


# =============================================================== the run

def run_comparison(*, smoke: bool = False, run_no: int = 1, out: Path | None = None,
                   max_minutes: float = MAX_MINUTES, launcher: list[str] | None = None,
                   check_gpu: bool = True, need_ram_gb: float = L4.MIN_FREE_RAM_GB,
                   need_disk_gb: float = L4.MIN_FREE_DISK_GB, freeze_only: bool = False,
                   frozen: dict | None = None, configs: dict | None = None,
                   health_wait_s: float = L4.HEALTH_WAIT_S, call=None) -> dict:
    from backend.services import llm_language as LL
    from backend.services import model_routing as MR

    t0 = time.time()
    budget = L4.AwakeBudget(max_minutes)
    out_path: dict = {"p": Path(out) if out else None}

    def write(receipt: dict) -> Path:
        if out_path["p"] is None:                    # resolved at the FIRST write
            out_path["p"] = L4.free_receipt_path(L4.night_folder(), JOB, run_no, smoke)
        from backend.services import disk_guard
        receipt["receipt_path"] = str(out_path["p"])
        receipt["written_utc"] = _now()
        receipt["elapsed_s"] = round(time.time() - t0, 1)
        receipt["budget"] = budget.view()
        disk_guard.atomic_write_json(out_path["p"], receipt)
        return out_path["p"]

    wire_system = LL.pin(MR.bakeoff_system())
    receipt: dict = {
        "job": JOB, "licence": LICENCE, "run": run_no, "run_id": L4.new_run_id(),
        "smoke": bool(smoke), "stage": "raw",
        "llm_spend_usd": 0.0, "arms": list(ARMS),
        "model": {"local_7b": L4.INCUMBENT_FILE, "local_30b": L4.GGUF_FILE},
        "question": ("On E-G1's frozen 240 items, does Qwen3-30B-A3B read news into typed "
                     "fields better than the incumbent 7B -- by enough, reliably enough, and "
                     "fast enough to replace it for L2 typing?"),
        "decision_rule": decision_rule(), "decision": None,
        "wire_system_sha256": _sha(wire_system), "status": "running",
    }
    # the machine first: a refusal must cost seconds, not a corpus rebuild or a
    # corpus scan on a machine that has no RAM to spare (2026-09-27)
    cfgs = None
    if not freeze_only:
        best = l4_best_n_cpu_moe()
        receipt["qwen3_setting"] = best
        cfgs = configs or {"local_7b": L4.incumbent_config(),
                           "local_30b": L4.qwen3_config(best["n_cpu_moe"])}
        receipt["configs"] = {a: {k: getattr(c, k) for k in ("name", "model", "port", "n_cpu_moe")}
                              for a, c in cfgs.items()}
        receipt["model"] = {a: Path(c.model).name for a, c in cfgs.items()}
        pre = L4.preflight(JOB, need_ram_gb=need_ram_gb, need_disk_gb=need_disk_gb,
                           models=(() if launcher else tuple(c.model for c in cfgs.values())),
                           check_gpu=check_gpu, check_binary=not launcher)
        receipt["preflight"] = pre
        if not pre["ok"]:
            codes = sorted({r["code"] for r in pre["refusals"]})
            receipt.update(status=codes[0], headline=f"L4b not run: {', '.join(codes)}",
                           verdict=("REFUSED (" + ", ".join(codes) + "): "
                                    + "; ".join(r["detail"] for r in pre["refusals"])),
                           next_test="the lab's idle-GPU queue re-dispatches L4b on a later day")
            write(receipt)
            return receipt

    fz = frozen or freeze_items()
    receipt["frozen_inputs"] = {k: fz.get(k) for k in ("ok", "sha256", "path", "checks",
                                                       "frozen_utc", "reason")}
    if not fz.get("ok"):
        receipt.update(status="REFUSED_INPUTS", headline="E-G1 inputs not reproducible",
                       verdict=f"REFUSED: {fz.get('reason')}")
        write(receipt)
        return receipt
    if fz.get("wire_system_sha256") and fz["wire_system_sha256"] != receipt["wire_system_sha256"]:
        receipt.update(status="REFUSED_INPUTS", headline="the wire system prompt changed",
                       verdict=("REFUSED: the wire system prompt no longer hashes to the one "
                                "the items were frozen with; a changed prompt is a new test"))
        write(receipt)
        return receipt
    items = list(fz["items"])
    if smoke:
        items = items[:8]
    receipt["n_items"] = len(items)
    if freeze_only:
        receipt.update(status="FROZEN", headline=f"{len(items)} items frozen, sha256 "
                       f"{str(fz['sha256'])[:12]}", verdict="DESCRIPTIVE: inputs frozen only")
        write(receipt)
        return receipt

    backlog = nightly_typing_rows()
    receipt["nightly_typing_backlog"] = backlog

    # the rule is on disk, with the frozen inputs' hash, BEFORE the first item
    receipt["rows"] = []
    write(receipt)
    ref = {}
    try:
        src = json.loads((routing_dir() / SOURCE_RECEIPT).read_text(encoding="utf-8"))
        ref = {r["item_id"]: r for r in src.get("rows") or [] if r.get("arm") == "local"}
    except (OSError, ValueError):
        pass

    def add(item: dict, res: dict) -> None:
        res["item_id"] = item["item_id"]
        res["item_stratum"] = item["gold"]["stratum"]
        res["grade"] = MR.grade_extraction(res["pred"], item)
        receipt["rows"].append(res)
        if len(receipt["rows"]) % FLUSH_EVERY == 0:
            write(receipt)

    arms_info = {}
    try:
        for arm in ARMS:
            if budget.exhausted() or L4.stop_file_reason():
                arms_info[arm] = {"arm": arm, "n_read": 0,
                                  "skipped": L4.stop_file_reason() or "budget"}
                continue
            arms_info[arm] = run_arm(arm, cfgs[arm], items, wire_system, add=add,
                                     budget=budget, launcher=launcher,
                                     health_wait_s=health_wait_s, call=call)
            receipt["arms_info"] = arms_info
            write(receipt)
    except BaseException as exc:                 # servers already stopped by OwnedServer
        receipt["exception"] = f"{type(exc).__name__}: {exc}"[:400]
        receipt["arms_info"] = arms_info
        receipt["status"] = "FAILED"
        write(receipt)
        raise
    receipt["arms_info"] = arms_info
    rows = receipt["rows"]
    by_arm = {a: [r for r in rows if r["arm"] == a] for a in ARMS}
    receipt["summary"] = MR._summarise(rows, ARMS)
    receipt["summary"].pop("_nvidia_vs_deepseek", None)
    for a in ARMS:
        lat = [float(r["latency_s"]) for r in by_arm[a] if r.get("latency_s") is not None]
        if a in receipt["summary"]:
            receipt["summary"][a]["seconds_per_item_mean"] = (round(sum(lat) / len(lat), 3)
                                                              if lat else None)
    paired = paired_field_accuracy(by_arm["local_7b"], by_arm["local_30b"])
    receipt["paired_30b_minus_7b"] = paired
    s30 = (receipt["summary"].get("local_30b") or {}).get("seconds_per_item_mean")
    projected = (round(backlog["rows_per_night"] * s30 / 3600, 2) if s30 else None)
    receipt["projection"] = {"rows_per_night": backlog["rows_per_night"],
                             "rows_source": backlog["source"],
                             "seconds_per_item_30b": s30,
                             "seconds_per_item_7b": (receipt["summary"].get("local_7b") or {})
                             .get("seconds_per_item_mean"),
                             "hours_30b": projected, "night_hours": NIGHT_HOURS,
                             "note": ("E-G1's prompt (system with 43 ids + one document) is the "
                                      "L2-shaped read; prompt caching is ON as it is for L2, so "
                                      "the shared system prefix is read once per server")}
    if ref:
        same = [r for r in by_arm["local_7b"] if r["item_id"] in ref]
        agree = sum(1 for r in same if (r.get("pred") or {}).get("event_type")
                    == (ref[r["item_id"]].get("pred") or {}).get("event_type"))
        receipt["reproducibility_vs_2026_09_26_local_arm"] = {
            "n": len(same), "event_type_agreement": round(agree / len(same), 4) if same else None,
            "field_accuracy_2026_09_26": (src.get("summary") or {}).get("local", {})
            .get("field_accuracy") if ref else None}
    d = decide(paired, projected, n_expected=len(items), n_a=len(by_arm["local_7b"]),
               n_b=len(by_arm["local_30b"]))
    receipt["decision"] = d
    stopped = [{"arm": a, "pid": (i.get("stop") or {}).get("pid"),
                "stopped_ok": (i.get("stop") or {}).get("ok"),
                "vram_after_mib": (i.get("vram_after") or {}).get("after_mib"),
                "vram_baseline_mib": (i.get("vram_after") or {}).get("baseline_mib"),
                "model": i.get("model"), "n_cpu_moe": i.get("n_cpu_moe"),
                "generation_tok_s_median": i.get("generation_tok_s_median"),
                "vram_peak_mib": i.get("vram_peak_mib"),
                "server_rss_peak_mib": i.get("server_rss_peak_mib"),
                "ram_available_min_gib": i.get("ram_available_min_gib")}
               for a, i in arms_info.items()]
    receipt["servers_stopped_by_pid"] = stopped
    sm = receipt["summary"]
    fa = {a: (sm.get(a) or {}).get("field_accuracy") for a in ARMS}
    receipt["status"] = "DECIDED" if d["decision"] != "INCOMPLETE" else "INCOMPLETE"
    receipt["headline"] = (
        f"E-G1 local: 7B {fa['local_7b']} vs 30B {fa['local_30b']} field accuracy; "
        f"30B-7B {paired.get('diff_pts')} pts (SE {paired.get('se_pts')}, t {paired.get('t')}, "
        f"n {paired.get('n')}); 30B {s30} s/item -> {projected} h for "
        f"{backlog['rows_per_night']} rows/night; {d['decision']}")
    receipt["verdict"] = (("ADOPT" if d["decision"] == "REPLACE_7B_FOR_L2" else
                           "REJECTED" if d["decision"] == "KEEP_7B" else "CANNOT DETERMINE")
                          + f": {d['decision']} -- {d['why']}")
    write(receipt)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L4b: E-G1 extraction, local 7B vs local 30B")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="8 items per arm")
    ap.add_argument("--freeze-only", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=MAX_MINUTES)
    a = ap.parse_args(argv)
    r = run_comparison(smoke=a.smoke, run_no=a.run, out=Path(a.out) if a.out else None,
                       max_minutes=a.max_minutes, freeze_only=a.freeze_only)
    print(r.get("headline"))
    print(r.get("verdict"))
    return 0


def L4b_qwen3_extraction(smoke: bool = False, run: int = 1,
                         out: str | Path | None = None) -> dict:
    """The night-factory entry point (the factory writes the returned payload;
    `out` is its receipt path, so this run's own flushes land in the same file)."""
    return run_comparison(smoke=smoke, run_no=run, out=Path(out) if out else None)


if __name__ == "__main__":
    raise SystemExit(main())
