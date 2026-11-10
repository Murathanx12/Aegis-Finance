"""PC-PAPER's own index (OD-10): dry-run, freeze, measure. NEVER sends an order.

    python -m scripts.pc_own_index dry-run   # the orders the sim WOULD send (sell SPY, buy list)
    python -m scripts.pc_own_index freeze    # write the frozen contract (attended, once per version)
    python -m scripts.pc_own_index measure   # index vs SPY vs its random twin since the freeze

The dry-run is OFFLINE: equity and holdings come from the newest broker-truth
receipt (`pc_book/state_latest.json`, written by pc_broker.snapshot), prices from
that receipt (held names) and the bars panel's last close (the rest), sigmas and
history from the bars panels. It imports no submit path and calls no broker.

Exit codes: 0 plan OK · 2 REFUSED (candidate file stale/empty/unreadable, broker
receipt stale or another account) · 3 contract conflict (changed since freeze,
or PC_BENCHMARK_CORE and PC_OWN_INDEX both on). A refusal never falls back to SPY.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services import pc_own_index as OI             # noqa: E402

RC_OK, RC_REFUSED, RC_CONTRACT = 0, 2, 3


def _folder(arg: Optional[str]) -> Path:
    return Path(arg) if arg else Path(_config.OPTIMUS_LEDGER_DIR) / "decisions" / "pc_plan"


def _age_days(stamp: Any, now: datetime) -> Optional[float]:
    return OI._age_days(stamp, now)


def _newest_plan_receipt(pc_book: Path) -> Optional[Path]:
    days = sorted((d for d in pc_book.glob("20??-??-??") if (d / "intended_book.json").exists()),
                  key=lambda d: d.name)
    return (days[-1] / "intended_book.json") if days else None


def _last_closes(bars: Path, syms: list[str]) -> dict[str, float]:
    try:
        import pandas as pd                                        # noqa: PLC0415
        df = pd.read_parquet(bars, columns=["symbol", "date", "close"],
                             filters=[("symbol", "in", list(syms))])
        df = df.sort_values("date").groupby("symbol").tail(1)
        return {str(r.symbol): float(r.close) for r in df.itertuples() if r.close and r.close > 0}
    except Exception:                                              # noqa: BLE001
        return {}


def dry_run(args: argparse.Namespace) -> int:
    now = (datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc))
    folder = _folder(args.folder)
    pc_book = Path(_config.OPTIMUS_LEDGER_DIR) / "pc_book"
    bars = Path(args.bars) if args.bars else Path(_config.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
    print("PC-PAPER OWN INDEX -- DRY RUN (no order is sent; no broker is called)")
    if bool(getattr(_config, "PC_BENCHMARK_CORE", False)) and bool(getattr(_config, "PC_OWN_INDEX", False)):
        print("REFUSED: PC_BENCHMARK_CORE and PC_OWN_INDEX are both True")
        return RC_CONTRACT
    print(f"  config: PC_BENCHMARK_CORE={_config.PC_BENCHMARK_CORE} PC_OWN_INDEX={_config.PC_OWN_INDEX}"
          f" (the dry-run plans as if PC_OWN_INDEX were on)")
    # ---- broker truth: the newest receipt, never a trading call --------------
    snap_path = Path(args.snapshot) if args.snapshot else pc_book / "state_latest.json"
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"REFUSED: broker receipt unreadable {snap_path}: {exc}")
        return RC_REFUSED
    age = _age_days(snap.get("t"), now)
    limit = float(_config.PC_MANDATE_EQUITY_MAX_AGE_DAYS)
    if age is None or age > limit:
        print(f"REFUSED: broker receipt {snap_path.name} stamp {snap.get('t')} is "
              f"{'undateable' if age is None else f'{age:.1f} d old'} (limit {limit:g} d)")
        return RC_REFUSED
    if str(snap.get("account_number")) != str(_config.PC_PAPER_ACCOUNT_NUMBER):
        print(f"REFUSED: receipt is account {snap.get('account_number')}, not PC-PAPER")
        return RC_REFUSED
    equity = float(snap["equity"])
    held = {str(p["symbol"]): float(p["qty"]) for p in snap.get("positions") or []}
    mv = {str(p["symbol"]): float(p.get("market_value") or 0.0) for p in snap.get("positions") or []}
    px_held = {str(p["symbol"]): float(p.get("current_price") or 0.0) for p in snap.get("positions") or []}
    print(f"  broker receipt: {snap_path} t={snap.get('t')} ({age:.2f} d old) equity "
          f"${equity:,.2f} cash ${float(snap.get('cash') or 0):,.2f} positions {len(held)}")
    # ---- the other sleeves, from the newest plan receipt ----------------------
    rec_path = Path(args.plan_receipt) if args.plan_receipt else _newest_plan_receipt(pc_book)
    rec = {}
    if rec_path and rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    rf = rec.get("revision_flow") or {}
    rf_w = {s: float(w) for s, w in (rf.get("weights_after_gate") or rf.get("weights") or {}).items()}
    rf_acting = bool(rf.get("acting"))
    acting = dict(rf_w) if rf_acting else {}
    acting_targets = [b for b in rec.get("book") or []
                      if (b.get("state") == "PROBE" and rec.get("probe_acting"))
                      or (b.get("state") == "EXPLOIT" and rec.get("exploit_acting"))]
    for b in acting_targets:
        acting[str(b["symbol"])] = float(b["weight"])
    claimed = set(rf_w) | set(acting)
    print(f"  plan receipt: {rec_path} asof {rec.get('asof')} -- revision_flow {len(rf_w)} names "
          f"{sum(rf_w.values()):.2%} acting={rf_acting}; PROBE acting={rec.get('probe_acting')}; "
          f"EXPLOIT acting={rec.get('exploit_acting')}")
    # ---- contract -------------------------------------------------------------
    cpath = folder / OI.CONTRACT_FILE
    if cpath.exists():
        try:
            contract = OI.load_frozen(cpath)
            print(f"  contract: FROZEN {contract['policy_hash'][:16]} at {contract['frozen_utc']}")
        except OI.OwnIndexRefused as exc:
            print(f"REFUSED (contract): {exc}")
            return RC_CONTRACT
    else:
        content = OI.contract_content()
        contract = {"content": content, "policy_hash": OI.policy_hash(content),
                    "frozen_utc": None}
        print(f"  contract: NOT FROZEN YET -- `freeze` would write {cpath} with policy hash "
              f"{contract['policy_hash'][:16]} (version {content['version']})")
    # ---- membership (in memory: the dry-run writes nothing) -------------------
    from backend.services import pc_risk as PR                     # noqa: PLC0415
    from backend.services import pc_sleeves as SL                  # noqa: PLC0415
    sig = PR.panel_sigmas(bars)
    fb, fb_src = PR.fallback_sigma(PR.universe_stats(sig))
    refusal = None
    try:
        row = OI.membership(folder, contract=contract,
                            funnel_path=Path(args.funnel) if args.funnel else None,
                            now=now, exclude=set(rf_w), sigmas=sig, write=False)
        print(f"  {row['line']}")
    except OI.OwnIndexRefused as exc:
        refusal = str(exc)
        row = {"members": [], "previous_members": []}
        print(f"  membership REFUSED: {refusal}")
    members = list(row.get("members") or [])
    idx_syms = set(members) | set(row.get("previous_members") or [])
    owned = {s for s in idx_syms if s in held and s not in claimed} | {"SPY"}
    resid = {s: mv[s] / equity for s in held if s not in owned and s not in acting and equity > 0}
    names = [m for m in members if m not in claimed]
    prices = dict(px_held)
    prices.update({s: p for s, p in _last_closes(bars, [s for s in names if s not in prices]).items()})
    history = SL.bound_history(names, bars) if names and refusal is None else None
    res = OI.plan(contract=contract, members_row=row, refusal=refusal, equity=equity, held=held,
                  prices=prices, acting_weights=acting, claimed=claimed, held_residual=resid,
                  sigmas=sig, fallback_sigma=fb, history=history, mode="paper_profit")
    print(f"\n  {res['line']}")
    for ln in res.get("worst_case_lines") or []:
        print(f"  {ln}")
    print(f"  sigma fallback {fb:.2%} ({fb_src}); prices: held from the receipt, others last close "
          f"of {bars.parent.name}")
    if row.get("twin", {}).get("weights"):
        print(f"  random twin (seed {row['twin']['seed']}): {sorted(row['twin']['weights'])}")
    # ---- the orders it WOULD send --------------------------------------------
    plans = list(res.get("plans") or [])
    plans.sort(key=lambda p: (p.side != "sell", -p.notional))
    print("\n  WOULD SEND (sells first), state / side / qty / symbol / ~notional / note:")
    sells = buys = 0.0
    for p in plans:
        st = res["state_of"].get(p.symbol, "?")
        note = f"  [{p.refused}]" if p.refused else ""
        print(f"    {st:15s} {p.side:4s} {p.qty:6d} {p.symbol:6s} ${p.notional:>12,.0f}{note}")
        if p.qty > 0 and p.side == "sell":
            sells += p.notional
        elif p.qty > 0 and p.side == "buy":
            buys += p.notional
    cash_after = float(snap.get("cash") or 0.0) + sells - buys
    gross_after = (float(snap.get("long_market_value") or 0.0) - sells + buys) / equity
    print(f"\n  totals: sells ${sells:,.0f}, buys ${buys:,.0f}; cash after ~${cash_after:,.0f} "
          f"({cash_after / equity:.2%}); gross after ~{gross_after:.2%} of equity")
    if args.out:
        Path(args.out).write_text(json.dumps({
            "t": now.isoformat(timespec="seconds"), "snapshot": str(snap_path),
            "plan_receipt": str(rec_path), "equity": equity,
            "own_index": {k: v for k, v in res.items() if k not in ("plans", "targets")},
            "orders": [{"state": res["state_of"].get(p.symbol), "side": p.side, "qty": p.qty,
                        "symbol": p.symbol, "notional": p.notional, "refused": p.refused,
                        "reason": p.reason} for p in plans],
            "totals": {"sells": sells, "buys": buys, "cash_after": cash_after,
                       "gross_after": gross_after}}, indent=1, default=str), encoding="utf-8")
        print(f"  receipt: {args.out}")
    if refusal is not None or res.get("refused"):
        print(f"\nREFUSED: {res.get('refused') or refusal} -- no index buy; SPY is never the filler")
        return RC_REFUSED
    return RC_OK


def freeze(args: argparse.Namespace) -> int:
    path = _folder(args.folder) / OI.CONTRACT_FILE
    try:
        row = OI.freeze(path)
    except OI.OwnIndexRefused as exc:
        print(f"REFUSED: {exc}")
        return RC_CONTRACT
    print(f"frozen: {path}\n  policy_hash {row['policy_hash']}\n  version "
          f"{row['content']['version']}  frozen_utc {row['frozen_utc']}")
    return RC_OK


def measure(args: argparse.Namespace) -> int:
    folder = _folder(args.folder)
    row = OI._read_json(folder / OI.MEMBERS_FILE)
    if not row:
        print(f"REFUSED: no membership at {folder / OI.MEMBERS_FILE}")
        return RC_REFUSED
    deep = Path(args.bars) if args.bars else Path(_config.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
    out = OI.measure(row, deep)
    print(json.dumps(out, indent=1, default=str))
    return RC_REFUSED if out.get("error") else RC_OK


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dry-run")
    d.add_argument("--snapshot"), d.add_argument("--plan-receipt"), d.add_argument("--funnel")
    d.add_argument("--folder"), d.add_argument("--bars"), d.add_argument("--now")
    d.add_argument("--out", help="also write the dry-run as JSON here")
    f = sub.add_parser("freeze")
    f.add_argument("--folder")
    m = sub.add_parser("measure")
    m.add_argument("--folder"), m.add_argument("--bars")
    a = ap.parse_args(argv)
    return {"dry-run": dry_run, "freeze": freeze, "measure": measure}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
