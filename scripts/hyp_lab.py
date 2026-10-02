"""hyp_lab CLI: seed, generate, rank, declare, run, nightly.

    .venv/Scripts/python.exe -m scripts.hyp_lab seed
    .venv/Scripts/python.exe -m scripts.hyp_lab generate --provider deepseek --n 8
    .venv/Scripts/python.exe -m scripts.hyp_lab rank
    .venv/Scripts/python.exe -m scripts.hyp_lab declare --ids H-abc,H-def      # receipt BEFORE running
    .venv/Scripts/python.exe -m scripts.hyp_lab run --receipt <declare receipt>
    .venv/Scripts/python.exe -m scripts.hyp_lab nightly --k 3 --cap 0.40       # the scheduled caller
    .venv/Scripts/python.exe -m scripts.hyp_lab t2 --fold F2025                # cache a fold's T2 predictions
    .venv/Scripts/python.exe -m scripts.hyp_lab schtasks [--create]            # AegisHypLabNightly, after nn_lab

Stop: create backend/data/optimus/hyp_lab/STOP. Every paid call goes through hyp_llm (per-night cap
shared with every hyp_lab process). Licence PRODUCT_EXPERIMENT; nothing trades.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend import config as C
from backend.services import hyp_lab as L
from backend.services import hyp_llm as HL

TASK = "AegisHypLabNightly"
TASK_TIME = "09:30"          # local; the nn_lab nightly is 08:30 and the daily pass ends ~08:00


def _free_ram_gb() -> float:
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                        ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1024 ** 3
    except Exception:  # noqa: BLE001
        return float("nan")


def wait_ram(label: str, floor: float | None = None, max_wait_s: int = 900) -> float:
    """Pause, never crash, while free RAM is under the floor; refuse after max_wait_s."""
    floor = C.HYP_LAB_MIN_FREE_RAM_GB if floor is None else floor
    t0 = time.monotonic()
    r = _free_ram_gb()
    while r == r and r < floor:
        if time.monotonic() - t0 > max_wait_s:
            raise SystemExit(f"REFUSED {label}: free RAM {r:.1f} GB < {floor} for {max_wait_s}s")
        print(f"[hyp_lab] {label}: free RAM {r:.1f} GB < {floor}; pausing 20 s", flush=True)
        time.sleep(20)
        r = _free_ram_gb()
    return r


# ------------------------------------------------------------------ seed rows
def seed_rows() -> list[dict]:
    """(a) open leads in the 2026-09-29 notes, (b) the world digest's second-order paths grouped
    into recurring mechanisms, (c) tonight's size/attention questions. Each row names the note
    it came from. Idempotent: a row whose id exists is skipped by dedupe."""
    notes = "docs/research_notes/2026-09-29/"
    wd = notes + "world_digest_2026-09-29.md"
    ft = notes + "ft_lab_first_run_2026-09-29.md"
    M = L.make_hypothesis
    rows = [
        # ---------------- (b) world digest mechanisms -> macro_lead_lag
        M(title="Oil shock -> airlines lag", family="macro_readthrough_commodity", target="return",
          mechanism="Jet fuel is 20-30% of airline cost and hedges are partial; if investors under-react to an oil "
                    "shock, airlines keep falling (rising) the session after a large oil rise (fall).",
          precursor="WTI front-month (CL=F) close-to-close change at close t beyond 2 trailing 63-session sd",
          separation_from_beta="the same-day response is ordinary oil beta and is printed separately; the test is the "
                               "open t+1 -> close t+h residual after the basket's SPY beta (design-fold estimate)",
          refutation="confirm-fold (2023-26) mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "CL=F", "targets": ["DAL", "UAL", "LUV", "AAL", "ALK", "JBLU"], "expected_sign": -1,
                  "h": 1, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          negative_informative=True, expected_power=0.5, cpu_min=1),
        M(title="Yield spike -> regional banks lag", family="macro_readthrough_rates", target="return",
          mechanism="A 10-year yield spike raises unrealised securities losses and deposit costs; if the market "
                    "under-reacts, regional banks keep falling the next session.",
          precursor="^TNX close-to-close change at close t beyond 2 trailing 63-session sd",
          separation_from_beta="same-day response printed apart; the lag residual after SPY beta is the test",
          refutation="confirm-fold mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "^TNX", "targets": ["ZION", "KEY", "CFG", "RF", "HBAN", "FITB", "MTB", "CMA", "WAL", "EWBC"],
                  "expected_sign": -1, "h": 1, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          negative_informative=True, expected_power=0.5, cpu_min=1),
        M(title="Yield spike -> utilities lag", family="macro_readthrough_rates", target="return",
          mechanism="Utilities are bond proxies; a yield spike lowers their fair value and slow money keeps "
                    "selling the next session.",
          precursor="^TNX change at close t beyond 2 trailing sd",
          separation_from_beta="same-day beta printed apart; lag residual after SPY beta",
          refutation="confirm-fold mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "^TNX", "targets": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "PEG"],
                  "expected_sign": -1, "h": 1, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          negative_informative=False, expected_power=0.5, cpu_min=1),
        M(title="Yield spike -> homebuilders lag", family="macro_readthrough_rates", target="return",
          mechanism="Mortgage rates follow the 10-year; homebuilders' demand falls with them and the repricing "
                    "takes more than a session.",
          precursor="^TNX change at close t beyond 2 trailing sd",
          separation_from_beta="same-day beta printed apart; lag residual after SPY beta",
          refutation="confirm-fold mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "^TNX", "targets": ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MTH", "TMHC"],
                  "expected_sign": -1, "h": 1, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          expected_power=0.5, cpu_min=1),
        M(title="AI leader shock -> semi equipment lag", family="equity_readthrough_supply_chain", target="return",
          mechanism="A large move in the AI-chip leaders changes expected foundry and tool orders; suppliers "
                    "(equipment, foundry) catch up over the next sessions.",
          precursor="equal-weight NVDA/AVGO/AMD close-to-close move at close t beyond 2 trailing sd",
          separation_from_beta="same-day co-move (sector beta) printed apart; lag residual after SPY beta",
          refutation="confirm-fold mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "basket:NVDA,AVGO,AMD", "targets": ["AMAT", "LRCX", "KLAC", "ASML", "TSM", "TER", "ONTO"],
                  "expected_sign": 1, "h": 1, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          expected_power=0.5, cpu_min=1),
        M(title="Oil shock -> refiners and chemicals (input cost) lag", family="macro_readthrough_commodity",
          target="return",
          mechanism="Crude is an input for chemicals and some refiners; margins compress after a spike and the "
                    "market reprices over days.",
          precursor="CL=F change at close t beyond 2 trailing sd",
          separation_from_beta="same-day beta printed apart; lag residual after SPY beta",
          refutation="confirm-fold mean signed residual <= 0, or t < 2 with MDE below the design effect",
          source="world_digest", source_ref=wd, cell_type="macro_lead_lag",
          params={"driver": "CL=F", "targets": ["DOW", "LYB", "WLK", "OLN", "HUN", "CE"], "expected_sign": -1,
                  "h": 5, "shock_z": 2.0}, split={"design": "2016-2022", "confirm": "2023-2026"},
          expected_power=0.4, cpu_min=1),
        # ---------------- (a) + (c) read-through on earnings, the owner's example
        M(title="Earnings shock read-through to text-linked names (next-session size)",
          family="event_readthrough_text_link", target="co_movement",
          mechanism="When a large customer or supplier reports a big surprise, names that the news already links "
                    "to it reprice; if the diffusion is slow, their next-session move exceeds their own volatility.",
          precursor="a source cell typed earnings_report by the student with |x_oc| >= 2x its trailing vol, and "
                    "names co-mentioned with it in documents known at least a day before",
          separation_from_beta="vol-matched unlinked names on the same date are the control; the 252-session "
                               "correlation peers (factor beta) run as their own cell for comparison",
          refutation="confirm-fold (2026) linked-minus-control log size ratio at t+1 <= 0, or t < 2 with MDE "
                     "below the design effect",
          source="owner_brief+day_notes", source_ref=ft, cell_type="event_readthrough",
          params={"link": "comention", "event_type": "earnings_report", "min_ratio": 2.0, "k": 5,
                  "min_source_dv_pct": 0, "lookback_days": 180},
          split={"design": "2025", "confirm": "2026-01..09"}, negative_informative=True, expected_power=0.45, cpu_min=2),
        M(title="Earnings shock read-through to correlation peers (factor-beta control)",
          family="event_readthrough_corr_peer", target="co_movement",
          mechanism="Names that co-move with the source (a factor-beta link) inherit part of its surprise on the "
                    "next session if the factor reprices slowly.",
          precursor="the same source events; links = the top-5 252-session return-correlation peers as of t-1",
          separation_from_beta="this IS the beta link: it is the comparison for the text-link cell",
          refutation="confirm-fold linked-minus-control log size ratio at t+1 <= 0, or t < 2 with MDE below "
                     "the design effect",
          source="owner_brief", source_ref=ft, cell_type="event_readthrough",
          params={"link": "corr_peer", "event_type": "earnings_report", "min_ratio": 2.0, "k": 5,
                  "min_source_dv_pct": 0, "lookback_days": 180},
          split={"design": "2025", "confirm": "2026-01..09"}, expected_power=0.5, cpu_min=4),
        M(title="Abnormal attention predicts move size beyond priors and TF-IDF", family="size_attention",
          target="size",
          mechanism="A name covered far more than its own normal attracts more traders and a larger move than "
                    "its trailing vol and its words imply.",
          precursor="documents in the cell vs the symbol's mean daily document count over the previous 60 days; "
                    "distinct sources in the 5 days before",
          separation_from_beta="the base is trailing vol + news counts + TF-IDF (T2); the increment is paired per date",
          refutation="confirm-fold (2026 test block) paired IC increment over T2 <= 0, or t < 2 with MDE below "
                     "the design effect",
          source="day_notes", source_ref=ft + " sec. 4 (attention +0.069, t 2.24, the only |t|>2 psychology field)",
          cell_type="size_feature_increment",
          params={"feature_set": "abn_attention", "design_fold": "F2025", "confirm_fold": "F2026"},
          split={"design": "F2025", "confirm": "F2026"}, negative_informative=True, expected_power=0.7, cpu_min=8),
        M(title="Cross-source disagreement predicts move size beyond TF-IDF", family="size_disagreement",
          target="size",
          mechanism="When coverage of the same name disagrees in tone, uncertainty is higher and the resolution "
                    "move is larger than the words' average implies.",
          precursor="lexicon tone per document in the cell: sd across documents, |mean|, share opposing the mean",
          separation_from_beta="base T2 includes the bag of words and the trailing vol; paired per date",
          refutation="confirm-fold paired IC increment over T2 <= 0, or t < 2 with MDE below the design effect",
          source="owner_brief", source_ref="brief: 'does cross-source agreement or disagreement predict size'",
          cell_type="size_feature_increment",
          params={"feature_set": "tone_agreement", "design_fold": "F2025", "confirm_fold": "F2026"},
          split={"design": "F2025", "confirm": "F2026"}, expected_power=0.6, cpu_min=10),
        M(title="Event-type size prior, 2025 as a second fold", family="size_event_prior", target="size",
          mechanism="Earnings (and some other event types) move more than trailing vol predicts; the prior "
                    "should hold in a year it was not found in.",
          precursor="the student's event type of the cell's first document (typed before the open)",
          separation_from_beta="base T2 (trailing vol + TF-IDF, which already carries the words); paired per date",
          refutation="confirm-fold (2025 H2) paired IC increment over T2 <= 0, or t < 2 with MDE below the design effect",
          source="day_notes", source_ref=ft + " evening CONTINUE FROM HERE (the second fold)",
          cell_type="size_feature_increment",
          params={"feature_set": "event_prior", "design_fold": "F2026", "confirm_fold": "F2025"},
          split={"design": "F2026 (already seen: earnings +0.24)", "confirm": "F2025"}, negative_informative=True,
          expected_power=0.7, cpu_min=6),
        # ---------------- (a) open leads that need a cell or forward time
        M(title="Digest second-order, unmentioned implications beat the vol prior",
                        family="digest_forward", target="size",
                        mechanism="The synthesis finds second-order paths no article named; if they carry "
                                  "information, those rows beat their own vol prior more than first-order rows.",
                        precursor="frozen news_digest implication rows with order=2 and mentioned_in_articles=False",
                        separation_from_beta="each row carries its own vol_prior_p; Brier improvement by decision date",
                        refutation="per-date Brier improvement of order-2 unmentioned rows <= 0 once >= 10 decision "
                                   "dates are graded",
                        source="world_digest", source_ref=wd + " HIGHEST-EV (forward; first grades 2026-10-09)",
                        cell_type=None, negative_informative=True, expected_power=0.3, cpu_min=2),
        M(title="Belief elasticity (X2) graded against returns", family="llm_belief_elasticity",
          target="llm_capability",
          mechanism="The LLM's call moves when only the news changes (t 31.9 vs placebo); if that movement is "
                    "information, the moved calls should be graded right more often than the unmoved.",
          precursor="the 10,063 X2 elasticity pairs already on disk",
          separation_from_beta="compare against a trailing-vol / momentum prior on the same rows",
          refutation="elasticity-weighted hit rate or Brier no better than the unweighted on graded returns",
          source="closed_list_open_item", source_ref="docs/WHAT_WE_ALREADY_KNOW_LLM.md (X2 belief elasticity: grade vs returns)",
          cell_type=None, negative_informative=True, expected_power=0.5, cpu_min=20),
        M(title="TRIAL-LEAK-1 difference-in-differences never computed", family="llm_leakage",
          target="llm_capability",
          mechanism="Identified vs masked accuracy gap measures memorisation; the DiD was designed and never run.",
          precursor="the 1,600 canary-wave rows on disk",
          separation_from_beta="within-case difference (identified vs masked), so ticker effects cancel",
          refutation="DiD accuracy gap within its MDE of zero",
          source="closed_list_open_item", source_ref="docs/WHAT_WE_ALREADY_KNOW_LLM.md (TRIAL-LEAK-1)",
          cell_type=None, expected_power=0.5, cpu_min=20),
        M(title="Volatility compression breakout with frictions", family="vol_compression",
          target="return",
          mechanism="Names whose realised vol compresses far below their own history break out; the handoff owes "
                    "the friction test.",
          precursor="21/252-session realised-vol ratio in its bottom decile at t",
          separation_from_beta="matched twin on size/momentum; net of costs",
          refutation="net return vs twin <= 0 on the CRSP board",
          source="day_notes", source_ref="docs/HANDOFF_2026-09-29_THE_DAY_THE_BACKTESTS_DIED.md NEXT #5",
          cell_type=None, expected_power=0.5, cpu_min=30, notes="owned by the CRSP-bridge agents tonight; not run here"),
    ]
    return rows


def cmd_seed(_a) -> int:
    state = L.load_state()
    rows = L.dedupe(seed_rows(), state)
    rows = [r for r in rows if r["hyp_id"] not in state]
    n = L.append(rows)
    print(json.dumps({"seeded": n, "status": _counts(rows)}, indent=1))
    return 0


def _counts(rows) -> dict:
    c: dict = {}
    for r in rows:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def generate(provider: str, n: int, cap: float | None, max_tokens: int = 6000) -> dict:
    state = L.load_state()
    user = L.generation_prompt(state, L.CELL_CATALOG, n=n)
    r = HL.call(L.GEN_SYSTEM, user, purpose="hyp_lab_generate", arm=f"generate:{provider}", provider=provider,
                max_tokens=max_tokens, temperature=0.7, cap_usd=cap)
    items = HL.parse_json(r.get("text"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = L.RECEIPTS / f"generate_{provider}_{stamp}.json"
    L.RECEIPTS.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({"provider": provider, "status": r.get("status"), "served_model": r.get("served_model"),
                                    "prompt_user": user, "reply": r.get("text"),
                                    "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out")},
                                   indent=1, default=str), encoding="utf-8")
    if not r.get("ok") or items is None:
        return {"provider": provider, "ok": False, "status": r.get("status"), "receipt": str(raw_path)}
    from backend.services import hyp_cells as HC
    rows = L.parse_generated(items, source=f"{provider}_gen", source_ref=str(raw_path.relative_to(L.REPO)),
                             symbols=HC.bar_symbols())
    rows = L.dedupe(rows, state)
    L.append(rows)
    return {"provider": provider, "ok": True, "n_items": len(items) if isinstance(items, list) else 1,
            "n_rows": len(rows), "status": _counts(rows), "receipt": str(raw_path),
            "served_model": r.get("served_model")}


def cmd_generate(a) -> int:
    print(json.dumps(generate(a.provider, a.n, a.cap), indent=1))
    return 0


def cmd_rank(a) -> int:
    state = L.load_state()
    q = L.rank(state, runnable_only=a.runnable)
    for i, h in enumerate(q[:a.top], 1):
        s = h["score"]
        print(f"{i:2d} {h['hyp_id']} EV {s['ev']:+.3f} P {s['p_change']:.3f} V {s['value']:.2f} "
              f"[{h.get('cell_type') if h.get('status') == 'PROPOSED' else 'NEEDS_CELL'}] {h['title']} ({h['source']})")
    L.render_markdown(state)
    return 0


def cmd_declare(a) -> int:
    state = L.load_state()
    ids = [x for x in a.ids.split(",") if x]
    rows = [state[i] for i in ids if i in state]
    missing = [i for i in ids if i not in state]
    if missing:
        raise SystemExit(f"unknown ids {missing}")
    if len(rows) > C.HYP_LAB_MAX_CELLS_PER_NIGHT:
        raise SystemExit(f"REFUSED: {len(rows)} cells > {C.HYP_LAB_MAX_CELLS_PER_NIGHT}")
    rec = L.declare(rows, HL.night_id())
    print(json.dumps({"declared": ids, "receipt": rec["path"], "sha256": rec["sha256"]}, indent=1))
    return 0


def cmd_run(a) -> int:
    rec = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    state = L.load_state()
    rows = [state[c["hyp_id"]] for c in rec["cells"] if c["hyp_id"] in state
            and state[c["hyp_id"]].get("status") == "DECLARED"]
    if a.only:
        keep = set(a.only.split(","))
        rows = [r for r in rows if r["hyp_id"] in keep]
    res = L.run_declared(rows, rec["night"], before_each=lambda r: wait_ram(f"run {r['hyp_id']}", max_wait_s=3600))
    L.render_markdown(L.load_state())
    print(json.dumps(res, indent=1, default=str))
    return 0


def cmd_t2(a) -> int:
    from backend.services import hyp_cells as HC
    wait_ram("t2")
    t = HC.t2_predictions(a.fold)
    print(json.dumps({"fold": a.fold, "rows": len(t)}))
    return 0


def stop_report(path: Path, *, now: datetime | None = None,
                warn_h: float | None = None) -> dict | None:
    """WHY a run would exit on a STOP file: which file, since when, how old.

    2026-10-02: a 0-byte hyp_lab/STOP dropped at 2026-09-29 22:41 stopped every
    nightly for three days, and the only trace was `LastTaskResult 3` -- the
    .cmd exited before python, so no receipt said which file or how old. The
    stop still binds (owner's call); a stop older than
    `config.STOP_FILE_STALE_WARN_H` is REPORTED as possibly forgotten."""
    p = Path(path)
    if not p.exists():
        return None
    now = now or datetime.now(timezone.utc)
    warn_h = float(C.STOP_FILE_STALE_WARN_H if warn_h is None else warn_h)
    mt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_h = round((now - mt).total_seconds() / 3600.0, 1)
    out = {"stop_file": str(p), "stop_since_utc": mt.isoformat(timespec="seconds"),
           "stop_age_h": age_h, "stale": age_h > warn_h, "warn_after_h": warn_h}
    out["line"] = (f"STOPPED by {p} (since {out['stop_since_utc']}, {age_h} h old)"
                   + (f" -- WARNING: older than {warn_h:g} h, possibly forgotten; delete it "
                      f"to resume" if out["stale"] else ""))
    return out


def nightly(k: int, cap: float, providers: list[str], time_box_min: float) -> dict:
    """The scheduled caller: generate -> dedupe -> rank -> declare top-k runnable -> run -> render.
    STOP file and RAM floor refuse by name; the dollar cap is this run's own (and the night cap
    still binds through hyp_llm)."""
    t0 = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rec = {"job": "hyp_lab.nightly", "started_utc": L.now_utc(), "night": HL.night_id(), "k": k, "cap_usd": cap}
    stop = stop_report(L.STOP)
    if stop:
        # WHY it exited goes FIRST in the receipt
        rec = {"why_exited": stop["line"], "stop": stop, **rec}
        rec.update(status="REFUSED", reason=stop["line"])
        return _write_nightly(rec, stamp)
    rec["free_ram_gb_start"] = round(wait_ram("nightly"), 2)
    spent0 = HL.spent()["binding_usd"]
    gens = []
    for p in providers:
        if L.STOP.exists() or (time.monotonic() - t0) / 60 > time_box_min:
            break
        if p == "local":
            # never START a 4-5 GB model server from a daytime job: use it only if it is already up
            from backend.services import llama_server as LS
            if not LS.health_ok():
                gens.append({"provider": "local", "ok": False, "status": "SKIPPED_SERVER_NOT_UP"})
                continue
        # the run's own cap: this run may spend `cap` on top of what the night had already spent
        gens.append(generate(p, 8, spent0 + cap))
    rec["generation"] = gens
    state = L.load_state()
    q = L.rank(state, runnable_only=True)[:k]
    rec["declared"] = []
    if q and not L.STOP.exists():
        d = L.declare(q, HL.night_id())
        rec["declared"] = [h["hyp_id"] for h in q]
        rec["declare_receipt"] = d["path"]
        state = L.load_state()
        rows = [state[h["hyp_id"]] for h in q]
        rec["results"] = L.run_declared(rows, HL.night_id(),
                                        before_each=lambda r: wait_ram(f"nightly {r['hyp_id']}", max_wait_s=1800))
    L.render_markdown(L.load_state())
    rec["spend_this_run_usd"] = round(HL.spent()["binding_usd"] - spent0, 5)
    rec["wall_min"] = round((time.monotonic() - t0) / 60, 1)
    rec["status"] = "OK"
    return _write_nightly(rec, stamp)


def _write_nightly(rec: dict, stamp: str) -> dict:
    L.RECEIPTS.mkdir(parents=True, exist_ok=True)
    p = L.RECEIPTS / f"nightly_{stamp}.json"
    p.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    rec["receipt"] = str(p)
    return rec


def cmd_nightly(a) -> int:
    rec = nightly(a.k, a.cap, [p for p in a.providers.split(",") if p], a.time_box)
    print(json.dumps({k: rec.get(k) for k in ("status", "reason", "declared", "spend_this_run_usd", "receipt")},
                     indent=1, default=str))
    if rec.get("stop"):
        return 3          # the exit code the old .cmd used for a STOP, now WITH a receipt
    return 0 if rec.get("status") == "OK" else 2


def cmd_schtasks(a) -> int:
    repo = L.REPO
    cmdfile = repo / "backend" / "data" / "optimus" / "hyp_lab" / "run_nightly.cmd"
    cmdfile.write_text(
        "@echo off\r\n"
        f'cd /d "{repo}"\r\n'
        "set AEGIS_PERSONAL_MODE=0\r\n"
        # no `if exist STOP exit /b 3` here any more (2026-10-02): python reads
        # the STOP file itself and writes a receipt naming it and its age.
        f'"{repo / ".venv" / "Scripts" / "python.exe"}" -m scripts.hyp_lab nightly --k 3 '
        f'--cap {C.HYP_LAB_NIGHTLY_CAP_USD} >> "{L.HYP_DIR / "nightly.log"}" 2>&1\r\n', encoding="utf-8")
    args = ["schtasks", "/Create", "/TN", TASK, "/TR", f'"{cmdfile}"', "/SC", "DAILY", "/ST", TASK_TIME, "/F"]
    print(" ".join(args))
    if a.create:
        r = subprocess.run(args, capture_output=True, text=True)
        print(r.stdout.strip(), r.stderr.strip())
        return r.returncode
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed").set_defaults(f=cmd_seed)
    g = sub.add_parser("generate")
    g.add_argument("--provider", default="deepseek", choices=["deepseek", "local"])
    g.add_argument("--n", type=int, default=8)
    g.add_argument("--cap", type=float, default=None)
    g.set_defaults(f=cmd_generate)
    r = sub.add_parser("rank")
    r.add_argument("--top", type=int, default=30)
    r.add_argument("--runnable", action="store_true")
    r.set_defaults(f=cmd_rank)
    d = sub.add_parser("declare")
    d.add_argument("--ids", required=True)
    d.set_defaults(f=cmd_declare)
    u = sub.add_parser("run")
    u.add_argument("--receipt", required=True)
    u.add_argument("--only", default="")
    u.set_defaults(f=cmd_run)
    t = sub.add_parser("t2")
    t.add_argument("--fold", default="F2025")
    t.set_defaults(f=cmd_t2)
    n = sub.add_parser("nightly")
    n.add_argument("--k", type=int, default=3)
    n.add_argument("--cap", type=float, default=C.HYP_LAB_NIGHTLY_CAP_USD)
    n.add_argument("--providers", default="deepseek,local")
    n.add_argument("--time-box", dest="time_box", type=float, default=C.HYP_LAB_NIGHTLY_TIME_BOX_MIN)
    n.set_defaults(f=cmd_nightly)
    s = sub.add_parser("schtasks")
    s.add_argument("--create", action="store_true")
    s.set_defaults(f=cmd_schtasks)
    a = ap.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
