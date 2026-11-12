"""CLI for the LLM selector book (`backend/services/llm_selector_book.py`).

    # read-only: today's candidate set, one full packet, token estimate, cost
    python -m scripts.llm_selector_book --dry-run --data-root <optimus dir> --out <dir>

    # write the frozen contract from the code (only when the contract changes)
    python -m scripts.llm_selector_book --freeze-contract

    # ONE real decision at the WALL CLOCK (env AEGIS_LLM_SELECTOR_BOOK=1; the brain runs it)
    python -m scripts.llm_selector_book --decide --data-root <optimus dir>

    # put that decision's three books on the CH-11 ruler (llm_portfolio/books.jsonl)
    python -m scripts.llm_selector_book --register --decision-date D --data-root <optimus dir> --dry-run
    python -m scripts.llm_selector_book --register --decision-date D --data-root <optimus dir>

`--now` is for `--dry-run` ONLY; `--decide --now` is refused (NOW_NOT_ALLOWED).

Exit codes: 0 done · 2 refused (stale/undateable/empty/too few candidates,
missing input, unstamped field, reply defect, provider refusal, contract drift,
already decided, already registered, --now with --decide) · 3 DeepSeek budget
refused · 4 flag off (nothing read, called or written).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import config as C
from backend.services import llm_selector_book as S


def _count(dirs: list[Path]) -> dict:
    return {str(d): (sum(1 for x in d.iterdir()) if d.is_dir() else None) for d in dirs}


def _watched(data_root: Path) -> list[Path]:
    return [data_root, data_root.parent, data_root / "digest", data_root / "analyst",
            data_root / "llm_selector", data_root / "llm_portfolio"]


def _now(arg: str | None) -> datetime:
    if not arg:
        return datetime.now(timezone.utc)
    t = S.parse_stamp(arg)
    if t is None:
        raise SystemExit(f"--now {arg!r} is not a time")
    return t


def dry_run(data_root: Path, out: Path, now: datetime) -> dict:
    inputs = S.load_inputs(data_root, now)
    cset = inputs["cset"]
    packets = S.all_packets(inputs, now)
    system, user = S.render(cset, packets, now)
    cost = S.cost_projection(system, user)
    k = int(C.LLM_SELECTOR_K)
    seed = S.selection_seed(S.decision_date(now))
    rec = {
        "schema": S.SCHEMA + "/dry_run", "generated_utc": S.iso(datetime.now(timezone.utc)),
        "decision_time": S.iso(now), "decision_date": str(S.decision_date(now)),
        "contract_hash": S.contract_hash(), "inputs": inputs["paths"], "sizes": inputs["sizes"],
        "candidate_set": {k2: v for k2, v in cset.items() if k2 not in ("members", "generated_dt")},
        "packet_hash": S.packets_hash(packets),
        "packets_n_facts": {p["ticker"]: len(p["facts"]) for p in packets},
        "packets_n_excluded_at_or_after_decision": {p["ticker"]: p["n_excluded_at_or_after_decision"]
                                                    for p in packets},
        "packet_example": packets[0] if packets else None,
        "prompt_hash": S.sha16(S.pinned_system(system) + "\n" + user),
        "prompt_hash_rendered": S.sha16(system + "\n" + user),
        "prompt_chars": {"system": len(system), "user": len(user)},
        "cost": cost,
        "twins_preview": {"selection": {"seed": seed,
                                        "tickers": S.selection_twin(cset["tickers"], k, seed)},
                          "incumbent": S.incumbent_twin(cset["ranked"], k)},
        "llm_calls_made": 0,
        "entry_session": S.entry_session(now), "entry_rule": S.ENTRY_RULE,
        "too_few_candidates": len(cset["tickers"]) <= k,
        "flag": {"LLM_SELECTOR_BOOK_ENABLED": bool(C.LLM_SELECTOR_BOOK_ENABLED),
                 "FUNNEL_NEWS_SOURCE_ENABLED": bool(C.FUNNEL_NEWS_SOURCE_ENABLED)},
    }
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"llm_selector_dry_run_{stamp}.json").write_text(json.dumps(rec, indent=1, default=str),
                                                           encoding="utf-8")
    (out / f"llm_selector_dry_run_{stamp}_prompt.txt").write_text(
        "=== SYSTEM ===\n" + system + "\n\n=== USER ===\n" + user, encoding="utf-8")
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--decide", action="store_true")
    g.add_argument("--freeze-contract", action="store_true")
    g.add_argument("--register", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="alone: the read-only packet dry run; with --register: print only")
    ap.add_argument("--decision-date", default=None, help="--register: the decision_date to register")
    ap.add_argument("--data-root", default=str(C.OPTIMUS_LEDGER_DIR))
    ap.add_argument("--out", default=None)
    ap.add_argument("--now", default=None, help="decision instant (UTC ISO); default now")
    a = ap.parse_args(argv)
    if not (a.decide or a.freeze_contract or a.register or a.dry_run):
        ap.error("one of --dry-run, --decide, --register, --freeze-contract is required")
    if a.decide and a.dry_run:
        ap.error("--decide and --dry-run are different runs")

    if a.freeze_contract:
        body = S.contract()
        body["frozen_utc"] = S.iso(datetime.now(timezone.utc))
        S.CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        S.CONTRACT_PATH.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"contract {body['contract_hash']} -> {S.CONTRACT_PATH}")
        return 0

    data_root = Path(a.data_root)
    if a.register:
        if not a.decision_date:
            print("REFUSED: --register needs --decision-date")
            return S.EXIT_REFUSED
        sel = Path(a.out) if a.out else data_root / "llm_selector"
        try:
            res = S.register(selector_dir=sel, target=data_root / "llm_portfolio" / "books.jsonl",
                             decision_date_=a.decision_date, dry_run=a.dry_run)
        except S.SelectorRefused as exc:
            print(f"REFUSED {exc.code}: {exc.detail}")
            return exc.exit_code
        verb = "WOULD APPEND" if a.dry_run else "APPENDED"
        print(f"{verb} {len(res['lines'])} rows to {res['target']}:")
        for ln in res["lines"]:
            print(ln)
        return 0
    if a.decide and a.now:
        print("REFUSED NOW_NOT_ALLOWED: --decide uses the wall clock; --now is for --dry-run only "
              "(a back-dated decision is not forward evidence)")
        return S.EXIT_REFUSED
    if a.decide and not S.flag_on():
        print("REFUSED FLAG_OFF: LLM_SELECTOR_BOOK_ENABLED / AEGIS_LLM_SELECTOR_BOOK are off; "
              "nothing read, called or written")
        return S.EXIT_CODES[S.FLAG_OFF]
    now = S.wall_clock() if a.decide else _now(a.now)
    out = Path(a.out) if a.out else (S.default_out_dir() if a.decide else None)
    if out is None:
        print("REFUSED: --dry-run needs --out (it never writes into the data folder by default)")
        return S.EXIT_REFUSED
    before = _count(_watched(data_root))
    try:
        if a.dry_run:
            rec = dry_run(data_root, out, now)
            cs, c = rec["candidate_set"], rec["cost"]
            print(f"candidate set: {cs['n_ranked']} ranked + {cs['n_added']} added "
                  f"(added_by_source included: {cs['added_by_source_included']}), generated "
                  f"{cs['generated_at']}, age {cs['age_days']:.2f} d (limit {cs['limit_days']} d), "
                  f"hash {cs['candidate_set_hash']}")
            print(f"inputs: {rec['sizes']}")
            print(f"packets: {len(rec['packets_n_facts'])}, facts per name {rec['packets_n_facts']}")
            print(f"excluded at/after decision: {rec['packets_n_excluded_at_or_after_decision']}")
            print(f"tokens: ~{c['est_input_tokens_chars_div_4']} in (chars/4) + <= {c['max_output_tokens']} out; "
                  f"reservation bound {c['budget_reservation_bound']}")
            for lab, r in c["by_price_row"].items():
                print(f"cost [{lab} {r['model']}]: ${r['usd_per_decision']:.5f}/decision, "
                      f"${r['usd_per_month']:.4f}/month at {c['decisions_per_month']} decisions "
                      f"(${r['usd_per_month_if_daily']:.4f}/month if daily)")
            print(f"contract {rec['contract_hash']}; LLM calls made: 0")
            print(json.dumps(rec["packet_example"], indent=1, default=str)[:4000])
        else:
            inputs = S.load_inputs(data_root, now)
            packets = S.all_packets(inputs, now)
            res = S.run_decision(cset=inputs["cset"], packets=packets, decision_time=now, out_dir=out)
            print(json.dumps({"book_ids": res["row"]["book_ids"], "picks": res["row"]["picks"],
                              "cost_usd": res["row"]["cost_usd"]}, indent=1, default=str))
    except S.SelectorRefused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}")
        return exc.exit_code
    finally:
        after = _count(_watched(data_root))
        print(f"live folder file counts before {before}")
        print(f"live folder file counts after  {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
