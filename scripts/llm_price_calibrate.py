"""Calibrate a model's row of `config.LLM_PRICE_PER_MTOK` from the provider's
own balance, and reprice a day's thesis cards on that one ruler.

    # a bounded batch through the SAME route the cards use, bracketed by reads
    python -m scripts.llm_price_calibrate run --max-quests 8 --cap-usd 0.6
    # refit offline from two snapshots already in deepseek_balance.jsonl
    python -m scripts.llm_price_calibrate fit --before <read_at> --after <read_at>
    # price every card of a day from its telemetry row's tokens (sidecar only)
    python -m scripts.llm_price_calibrate reprice-day --date 2026-09-27

WHY: `backend/services/llm_price_calibration.py`. The receipt is written to
`<ledger>/llm_price/calibration_<date>.json`; `reprice-day` writes
`<ledger>/thesis_cards/<date>/spend_repriced.json` and adds
`spend_repriced_usd` to that day's `_run_receipt.json`. No card is rewritten.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                               # noqa: E402
from backend.services import llm_price_calibration as LPC        # noqa: E402

MODEL = "deepseek-flash"
OUT_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "llm_price"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_balance() -> dict:
    from backend.services import deepseek_balance as DB
    return DB.read_balance()


def settled_snapshot(label: str, *, min_wait_s: float, poll_s: float = 30.0,
                     max_wait_s: float = 420.0) -> dict:
    """Wait at least `min_wait_s`, then poll until two consecutive reads agree,
    and PERSIST the settled one. DeepSeek posts spend with a lag; a read taken
    at the last reply under-states the window."""
    from backend.services import deepseek_balance as DB
    t0 = time.time()
    time.sleep(max(0.0, min_wait_s))
    prev = _read_balance()["total_usd"]
    reads = [prev]
    while time.time() - t0 < max_wait_s:
        time.sleep(poll_s)
        cur = _read_balance()["total_usd"]
        reads.append(cur)
        if cur == prev:
            break
        prev = cur
    snap = DB.snapshot(label)
    snap["settle_reads"] = reads
    snap["settle_wait_s"] = round(time.time() - t0, 1)
    return snap


def window_rows(before: str, after: str) -> list[dict]:
    from backend.services import llm_telemetry as LT
    return LPC.deepseek_rows_between(LT.read_calls(), before, after)


def fit_between(before: dict, after: dict) -> dict:
    rows = window_rows(before["read_at"], after["read_at"])
    delta = round(float(before["total_usd"]) - float(after["total_usd"]), 6)
    w = LPC.window_from_rows(rows, delta_usd=delta, model=MODEL)
    prior = dict(_cfg.LLM_PRICE_PER_MTOK[MODEL])
    fit = LPC.fit_prices([w], prior)
    from backend.services import llm_telemetry as LT
    per_call = [{"call_id": r.get("call_id"), "ts": r.get("ts"), "purpose": r.get("purpose"),
                 "model": r.get("model"), "tokens_in": r.get("tokens_in"),
                 "cached_tokens": r.get("cached_tokens"), "tokens_out": r.get("tokens_out"),
                 "table_cost_usd": LT.row_cost(r),
                 "openclaw_reported_cost_usd": (r.get("meta") or {}).get("openclaw_cost_usd"),
                 "status": (r.get("meta") or {}).get("status")}
                for r in rows]
    reported = sum(float(c["openclaw_reported_cost_usd"] or 0) for c in per_call)
    return {"model": MODEL, "balance_before": {k: before.get(k) for k in
                                               ("read_at", "total_usd", "label", "settle_reads")},
            "balance_after": {k: after.get(k) for k in
                              ("read_at", "total_usd", "label", "settle_reads", "settle_wait_s")},
            "provider_delta_usd": delta, "window": w, "fit": fit,
            "n_calls": w["n_calls"], "n_offset_calls": w["n_offset_calls"],
            "telemetry_at_prior_table_usd": round(sum(c["table_cost_usd"] or 0 for c in per_call), 6),
            "openclaw_reported_usd": round(reported, 6),
            "per_call": per_call}


def cmd_run(a) -> int:
    from backend.services import thesis_card as TC
    from scripts import thesis_cards as S
    day = datetime.now(timezone.utc).date().isoformat()
    have = {str(c.get("ticker")).upper() for c in TC.read_cards(day)}
    if a.tickers:
        uni = [{"ticker": t.strip().upper(), "kind": "personal", "source": "calibration"}
               for t in a.tickers.split(",") if t.strip()]
    else:
        uni = [u for u in S.default_universe() if u["ticker"].upper() not in have]
    uni = [u for u in uni if u["ticker"].upper() not in have][:a.max_quests]
    print(f"calibration batch: {[u['ticker'] for u in uni]}", flush=True)
    from backend.services import openclaw_client as OC
    h = OC.health()
    if not h.ok:
        print(f"REFUSED_UNHEALTHY: {h.as_dict()}")
        return 2
    before = settled_snapshot("calibration_before", min_wait_s=0, poll_s=20, max_wait_s=60)
    print(f"balance before: ${before['total_usd']} at {before['read_at']}", flush=True)
    res = S.run(universe=uni, asof=day, max_quests=a.max_quests, cap_usd=a.cap_usd,
                parallel=a.parallel, model=_cfg.THESIS_CARD_MODEL)
    after = settled_snapshot("calibration_after", min_wait_s=a.lag_s)
    print(f"balance after: ${after['total_usd']} at {after['read_at']} "
          f"(settle reads {after['settle_reads']})", flush=True)
    rec = fit_between(before, after)
    rec.update({"receipt": "llm_price_calibration", "made_utc": _now(),
                "route": "scripts.thesis_cards.run (OpenClaw quest + llm_analyzer synth)",
                "batch_tickers": [u["ticker"] for u in uni],
                "run_state": res.get("state"), "run_done": res.get("done"),
                "run_refused": res.get("refused")})
    return _write(rec, day)


def cmd_fit(a) -> int:
    from backend.services import deepseek_balance as DB
    snaps = {s["read_at"]: s for s in DB.snapshots()}
    rec = fit_between(snaps[a.before], snaps[a.after])
    rec.update({"receipt": "llm_price_calibration", "made_utc": _now(), "route": "offline refit"})
    return _write(rec, (a.date or a.after[:10]))


def _write(rec: dict, day: str) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"calibration_{day}.json"
    p.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    f = rec["fit"]
    print(json.dumps({k: f.get(k) for k in ("status", "method", "delta_total_usd",
                                            "fitted_usd_per_mtok", "bracket_usd_per_mtok",
                                            "k_vs_prior", "k_bracket",
                                            "relative_uncertainty", "adoptable", "why")},
                     indent=1))
    print(f"n_calls {rec['n_calls']} (+{rec['n_offset_calls']} offset), provider "
          f"${rec['provider_delta_usd']}, telemetry@prior ${rec['telemetry_at_prior_table_usd']}, "
          f"openclaw reported ${rec['openclaw_reported_usd']} -> {p}")
    return 0 if f["status"] == LPC.STATUS_OK else 1


# ─────────────────────────── reprice a day's cards ───────────────────────────

def _match_rows(cards: list[dict], rows: list[dict]) -> dict[str, dict]:
    """Card -> its quest telemetry row, by OpenClaw's reported `costUsd` (the
    same float from the same envelope lands on both), else by the nearest
    timestamp within 180 s. A row is used once."""
    from backend.services import thesis_card as TC
    quest = [r for r in rows if r.get("purpose") == TC.QUEST_PURPOSE]
    used: set[str] = set()
    out: dict[str, dict] = {}
    for c in cards:
        oc = c.get("openclaw_cost_usd")
        hit = None
        if isinstance(oc, (int, float)):
            for r in quest:
                if r["call_id"] not in used and (r.get("meta") or {}).get("openclaw_cost_usd") == oc:
                    hit = r
                    break
        if hit is None and c.get("run_utc"):
            t = LPC._instant(c["run_utc"])
            best = None
            for r in quest:
                if r["call_id"] in used:
                    continue
                dt = abs(((LPC._instant(r.get("ts")) or t) - t).total_seconds())
                if dt <= 180 and (best is None or dt < best[0]):
                    best = (dt, r)
            hit = best[1] if best else None
        if hit is not None:
            used.add(hit["call_id"])
            out[str(c["ticker"]).upper()] = hit
    return out


def reprice_day(day: str, *, root: Path | None = None, rows: list[dict] | None = None) -> dict:
    from backend.services import llm_telemetry as LT
    from backend.services import thesis_card as TC
    r = Path(root) if root is not None else TC.cards_root()
    cards = [c for c in TC.read_cards(day, root=root)
             if not c.get("_unreadable") and "openclaw_status" in c]
    if rows is None:
        rows = [x for x in LT.read_calls() if str(x.get("ts", ""))[:10] == day]
    cal_on = (getattr(_cfg, "LLM_PRICE_CALIBRATION", {}) or {}).get("calibrated_on")
    # Reprice a card unless it was priced at the CURRENT calibration already.
    todo = [c for c in cards if not ("cost_usd" in c and c.get("price_table_as_of") == cal_on)]
    match = _match_rows(todo, rows)
    todo_t = {str(c["ticker"]).upper() for c in todo}
    side: dict[str, Any] = {}
    tot_rep, tot_oc, tot_old, n_unmatched = 0.0, 0.0, 0.0, 0
    for c in cards:
        t = str(c["ticker"]).upper()
        ds = float(c.get("deepseek_cost_usd") or 0.0)
        if t not in todo_t:           # already priced at the current table
            continue
        row = match.get(t)
        oc = c.get("openclaw_cost_usd")
        tot_oc += float(oc or 0) + ds
        if row is None:
            n_unmatched += 1
            side[t] = {"cost_usd_repriced": None, "card_hash": c.get("card_hash"),
                       "why": "no telemetry row matched"}
            continue
        q = LT.row_cost(row)
        rep = None if q is None else round(q + ds, 8)
        tot_rep += rep or 0.0
        tot_old += float(row.get("cost_usd") or 0) + ds
        side[t] = {"cost_usd_repriced": rep, "quest_cost_usd_repriced": q,
                   "card_hash": c.get("card_hash"),
                   "cost_usd_as_written_on_card": c.get("cost_usd"),
                   "synth_cost_usd": ds, "openclaw_reported_cost_usd": oc,
                   "telemetry_call_id": row["call_id"], "tokens_in": row.get("tokens_in"),
                   "cached_tokens": row.get("cached_tokens"), "tokens_out": row.get("tokens_out")}
    cal = getattr(_cfg, "LLM_PRICE_CALIBRATION", {}) or {}
    out = {"receipt": "thesis_cards_spend_repriced", "day": day, "made_utc": _now(),
           "ruler": "config.LLM_PRICE_PER_MTOK applied to each quest's telemetry tokens "
                    "+ the synth call's measured telemetry delta",
           "price_row": {MODEL: _cfg.LLM_PRICE_PER_MTOK[MODEL]},
           "calibration": {k: cal.get(k) for k in ("calibrated_on", "receipt")},
           "n_cards": len(side), "n_unmatched": n_unmatched,
           "spend_repriced_usd": round(tot_rep, 6),
           "spend_openclaw_reported_usd": round(tot_oc, 6),
           "spend_as_written_in_telemetry_usd": round(tot_old, 6),
           "note": ("cards are not rewritten; `thesis_card.card_spend` reads this file "
                    "for any card of the day that lacks `cost_usd`"),
           "cards": side}
    d = r / day
    (d / TC.REPRICED_SIDECAR).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    rp = d / "_run_receipt.json"
    if rp.exists():
        try:
            rc = json.loads(rp.read_text(encoding="utf-8"))
            rc["spend_repriced_usd"] = out["spend_repriced_usd"]
            rc["spend_repriced_sidecar"] = TC.REPRICED_SIDECAR
            rp.write_text(json.dumps(rc, indent=1, default=str), encoding="utf-8")
        except (OSError, ValueError):
            pass
    print(f"{day}: {len(side)} cards repriced (unmatched {n_unmatched}): "
          f"${out['spend_repriced_usd']:.4f} at the table vs OpenClaw-reported "
          f"${out['spend_openclaw_reported_usd']:.4f}; card_spend now "
          f"${TC.card_spend(day, root=root)['spend_per_card_sum']:.4f}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--max-quests", type=int, default=8)
    r.add_argument("--cap-usd", type=float, default=0.6)
    r.add_argument("--parallel", type=int, default=2)
    r.add_argument("--tickers", default=None)
    r.add_argument("--lag-s", type=float, default=120.0)
    f = sub.add_parser("fit")
    f.add_argument("--before", required=True)
    f.add_argument("--after", required=True)
    f.add_argument("--date", default=None)
    d = sub.add_parser("reprice-day")
    d.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "fit":
        return cmd_fit(a)
    reprice_day(a.date or datetime.now(timezone.utc).date().isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
