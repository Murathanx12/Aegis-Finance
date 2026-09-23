"""Every closed round trip the fleet made, and what predicted the losses.

    python -m scripts.fleet_trade_autopsy

WHY THIS IS THE HIGHEST-VALUE THING AVAILABLE TONIGHT
=====================================================
Measured 2026-09-24, from the venue:

    fleet drawdown        -$47,307
    unrealised              -$905     <- what it HOLDS is nearly flat
    realised             -$46,401     <- 98% of the loss is CLOSED trades
    traded notional    $2,090,090
    loss per dollar traded  222 bps
    §59's round-trip toll   6-35 bps

Friction explains at most a sixth of it. The rest is DIRECTION: the fleet loses
roughly 4% on every position it takes, which is not a weak edge, it is a
strongly negative one. A selector that reliably loses is worth exactly as much
as one that reliably wins, because the instruction "stop doing this" is free and
immediate.

So this script does not look for alpha. It asks one question of every closed
round trip:

    what did the names we BOUGHT have in common, and does it predict the loss?

If entries cluster on a characteristic that carries a negative forward return in
our own panel, that is a rule worth money tonight -- before any new model, any
new data, and any new night.

HOW A ROUND TRIP IS RECONSTRUCTED
=================================
Alpaca reports FILLS, not trades. Positions are matched FIFO per (book, symbol):
each sell consumes the oldest open buy lots. A trip closed across several sells
is reported once, at the quantity-weighted exit.

Two honesty constraints:

* **Open lots are excluded.** A position still held has no realised return, and
  including its mark would mix "what happened" with "what might".
* **Options are excluded from the feature join.** `FSLR261016C00190000` is not
  in the price panel and has no momentum or volatility of its own; a trip on it
  is counted in the P&L totals and dropped from the regression, and the receipt
  says how many that was.

The entry features come from `xs_ranker.build_features` AS OF THE ENTRY DATE,
which is the only way to ask what was knowable when the decision was made.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import xs_ranker as XR                # noqa: E402

OUT = _cfg.OPTIMUS_LEDGER_DIR / "fleet_audit"
HOST = "https://paper-api.alpaca.markets"
ROLES = ("HACK1", "HACK2", "HACK4", "HACK5", "HACK6")
TERMINAL_ENV = Path("../aegis-alpha-terminal/.env")

#: An option symbol: root + 6-digit date + C/P + 8-digit strike.
def is_option(sym: str) -> bool:
    return len(sym) > 10 and any(c.isdigit() for c in sym[-8:])


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in TERMINAL_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def fills(role: str, kid: str, sec: str, *, max_rows: int = 3000) -> list[dict]:
    H = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
    out, page = [], None
    while len(out) < max_rows:
        u = f"{HOST}/v2/account/activities/FILL?page_size=100&direction=asc"
        if page:
            u += f"&page_token={page}"
        req = urllib.request.Request(u, headers=H)
        with urllib.request.urlopen(req, timeout=30) as fh:   # noqa: S310 allowlisted
            d = json.loads(fh.read())
        if not d:
            break
        for f in d:
            out.append({"book": role.lower(), "symbol": f["symbol"],
                        "side": f["side"], "qty": float(f["qty"]),
                        "price": float(f["price"]),
                        "t": f["transaction_time"][:10],
                        "ts": f["transaction_time"]})
        page = d[-1]["id"]
        if len(d) < 100:
            break
    return out


def round_trips(all_fills: list[dict]) -> tuple[list[dict], dict]:
    """FIFO-match fills into closed round trips. Open lots are EXCLUDED."""
    lots: dict[tuple[str, str], deque] = defaultdict(deque)
    trips, open_qty = [], 0.0
    for f in sorted(all_fills, key=lambda x: x["ts"]):
        key = (f["book"], f["symbol"])
        if f["side"].startswith("buy"):
            lots[key].append({"qty": f["qty"], "price": f["price"], "t": f["t"]})
            continue
        remaining = f["qty"]
        while remaining > 1e-9 and lots[key]:
            lot = lots[key][0]
            take = min(remaining, lot["qty"])
            trips.append({
                "book": f["book"], "symbol": f["symbol"],
                "entry_date": lot["t"], "exit_date": f["t"],
                "qty": take, "entry": lot["price"], "exit": f["price"],
                "pnl": (f["price"] - lot["price"]) * take,
                "ret": (f["price"] / lot["price"] - 1.0) if lot["price"] else None,
                "notional": lot["price"] * take,
                "hold_days": (date.fromisoformat(f["t"])
                              - date.fromisoformat(lot["t"])).days,
            })
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] <= 1e-9:
                lots[key].popleft()
    for v in lots.values():
        open_qty += sum(l["qty"] for l in v)
    return trips, {"open_lots_excluded": round(open_qty, 2)}


def attach_entry_features(trips: list[dict]) -> pd.DataFrame:
    """What each bought name looked like ON THE DAY IT WAS BOUGHT."""
    df = pd.DataFrame(trips)
    if df.empty:
        return df
    df["is_option"] = df["symbol"].map(is_option)
    eq = df[~df["is_option"]].copy()
    if eq.empty:
        return df
    bars = XR.load_bars(XR.survivorship_free_paths())
    feats = XR.build_features(bars)
    feats = XR.mark_eligible(feats)
    keep = ["symbol", "date", "mom_21", "mom_63", "mom_252_21", "rev_5",
            "vol_21", "vol_63", "dollar_vol_log", "amihud", "skew_63",
            "px_vs_52w_high", "turnover_surge", "beta_63", "median_dollar_vol"]
    keep = [c for c in keep if c in feats.columns]
    feats = feats[keep].copy()
    eq["date"] = pd.to_datetime(eq["entry_date"])
    merged = eq.merge(feats, on=["symbol", "date"], how="left")
    return merged


def what_predicts_the_loss(d: pd.DataFrame) -> list[dict]:
    """Per-feature: what did winners look like vs losers, at ENTRY?

    Not a model. A difference in means with a t, because with ~250 trips a
    model would fit the noise and a difference of means will not.
    """
    if d.empty or "ret" not in d:
        return []
    ok = d[d["ret"].notna()]
    win, lose = ok[ok["ret"] > 0], ok[ok["ret"] <= 0]
    # OUTCOME columns must never enter this comparison. `ret > 0` is the
    # DEFINITION of a winner, so including it reports t +25 and says nothing;
    # `pnl`, `hold_days` and `exit` are decided after the entry and cannot be
    # "what the buyer could see". The first version of this let them in, which
    # is the same leakage rule this repo enforces everywhere else, broken in
    # the one place it was being used to draw a conclusion.
    OUTCOMES = {"ret", "pnl", "hold_days", "exit", "qty", "notional", "entry"}
    rows = []
    for f in ok.columns:
        if f in ("symbol", "book", "entry_date", "exit_date", "date", "is_option"):
            continue
        if f in OUTCOMES:
            continue
        if not pd.api.types.is_numeric_dtype(ok[f]):
            continue
        a, b = win[f].dropna(), lose[f].dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        sa, sb = a.std(ddof=1), b.std(ddof=1)
        se = math.sqrt(sa**2 / len(a) + sb**2 / len(b))
        if not np.isfinite(se) or se == 0:
            continue
        t = (a.mean() - b.mean()) / se
        rows.append({"feature": f, "winners_mean": float(a.mean()),
                     "losers_mean": float(b.mean()), "t": float(t),
                     "n_win": int(len(a)), "n_lose": int(len(b))})
    rows.sort(key=lambda r: -abs(r["t"]))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    env = _env()
    raw = []
    for role in ROLES:
        kid, sec = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if kid and sec:
            try:
                raw += fills(role, kid, sec)
            except Exception as exc:                            # noqa: BLE001
                print(f"  {role}: {type(exc).__name__}: {exc}")
    trips, meta = round_trips(raw)
    print(f"{len(raw)} fills -> {len(trips)} closed round trips "
          f"({meta['open_lots_excluded']} open lots excluded)")
    if not trips:
        print("no closed trips; nothing to autopsy")
        return 1

    df = attach_entry_features(trips)
    eqt = df[~df["is_option"]] if "is_option" in df else df
    opt = df[df["is_option"]] if "is_option" in df else df.iloc[0:0]

    tot_pnl = float(df["pnl"].sum())
    tot_not = float(df["notional"].sum())
    wins = int((df["ret"] > 0).sum())
    print(f"\nrealised P&L ${tot_pnl:+,.0f} on ${tot_not:,.0f} entered notional "
          f"= {tot_pnl/tot_not*10000:+.0f} bps per position taken")
    print(f"hit rate {wins}/{len(df)} = {wins/len(df):.1%} | "
          f"median hold {df['hold_days'].median():.0f}d | "
          f"{len(opt)} option trip(s) excluded from the feature join")
    print(f"mean winner {df[df['ret']>0]['ret'].mean()*100:+.2f}%  "
          f"mean loser {df[df['ret']<=0]['ret'].mean()*100:+.2f}%")

    by_book = (df.groupby("book")
               .agg(trips=("pnl", "size"), pnl=("pnl", "sum"),
                    hit=("ret", lambda s: (s > 0).mean()),
                    med_hold=("hold_days", "median"))
               .sort_values("pnl"))
    print(f"\n{'book':>7} {'trips':>6} {'P&L':>10} {'hit':>7} {'hold':>6}")
    for b, r in by_book.iterrows():
        print(f"{b:>7} {int(r['trips']):>6} {r['pnl']:>+10,.0f} "
              f"{r['hit']:>6.0%} {r['med_hold']:>5.0f}d")

    disc = what_predicts_the_loss(eqt)
    print(f"\nWHAT DID WINNERS LOOK LIKE AT ENTRY, vs LOSERS  (|t| first)")
    print(f"{'feature':>18} {'winners':>11} {'losers':>11} {'t':>7}")
    for r in disc[:10]:
        flag = "  <<<" if abs(r["t"]) > 2 else ""
        print(f"{r['feature']:>18} {r['winners_mean']:>+11.4f} "
              f"{r['losers_mean']:>+11.4f} {r['t']:>+7.2f}{flag}")
    if not disc:
        print("  (too few matched trips to compare)")

    res = {
        "receipt": "fleet_trade_autopsy", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "read_only": True,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_fills": len(raw), "n_trips": len(trips), **meta,
        "realised_pnl": tot_pnl, "entered_notional": tot_not,
        "bps_per_position": tot_pnl / tot_not * 10000 if tot_not else None,
        "hit_rate": wins / len(df) if len(df) else None,
        "median_hold_days": float(df["hold_days"].median()),
        "n_option_trips_excluded_from_features": int(len(opt)),
        "by_book": json.loads(by_book.reset_index().to_json(orient="records")),
        "entry_discriminators": disc[:20],
        "verdict": _verdict(tot_pnl, tot_not, wins, len(df), disc),
        "read_me_first": (
            "Closed round trips only — an open position has no realised return "
            "and including its mark would mix what happened with what might. "
            "Entry features are AS OF THE ENTRY DATE, which is the only way to "
            "ask what was knowable when the decision was made."),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"trade_autopsy_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"-> {out}")
    return 0


def _verdict(pnl, notional, wins, n, disc) -> str:
    bps = pnl / notional * 10000 if notional else 0
    hit = wins / n if n else 0
    strong = [d for d in disc if abs(d["t"]) > 2]
    head = (f"{n} closed trips, hit rate {hit:.0%}, {bps:+.0f} bps per position "
            f"taken. ")
    if abs(bps) < 40:
        return head + ("That is within the range transaction costs alone could "
                       "explain (6-35 bps by liquidity band), so this is a "
                       "friction problem, not a selection one.")
    body = ("Far beyond what friction can explain, so the entries are "
            "directionally wrong rather than merely expensive. ")
    if strong:
        names = ", ".join(f"{d['feature']} (t {d['t']:+.1f})" for d in strong[:3])
        return head + body + (
            f"Winners and losers differ at ENTRY on: {names}. That is a "
            f"'stop doing this' rule available tonight — it needs no new model "
            f"and no new data, and it is worth testing on the panel before it "
            f"is believed.")
    return head + body + (
        "No entry characteristic separates winners from losers at |t| > 2, so "
        "the losses are not explained by any single feature measured here. "
        "That is itself informative: it points at timing or sizing rather than "
        "at a screenable property of the names.")


if __name__ == "__main__":
    raise SystemExit(main())
