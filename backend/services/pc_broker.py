"""The PC's own paper brokerage — ground truth, a lease, and hard mandate limits.

WHY THIS IS NOT `alpaca_mirror`
===============================
`portfolio_intelligence/alpaca_mirror` mirrors ONE internal lane's positions
once a day from Railway. It is verification infrastructure: it copies decisions
that were already made somewhere else. This module is the opposite — it is the
PC acting as the execution owner of one paper account, in the session, from the
ranking the PC just computed.

The 2026-09-22 morning report could not answer "paper NAV vs SPY" on this
machine. It could not answer it because nothing on this machine had ever asked
the broker. Every number below comes from the venue, never from a local
assumption, and `snapshot()` persists it so the learning system has economic
feedback instead of an inference.

THE ONE THING THAT CAN CORRUPT A TRACK RECORD
=============================================
Two executors on one account. hack3's Railway loop was submitting orders as
recently as 2026-09-21T22:03Z; it was removed the same day this module was
written, and hack3 itself was then deleted. But "we took it down" is a promise,
and a promise is not a mechanism. So:

* Every order carries `client_order_id = f"{LEASE_PREFIX}-{uuid}"`.
* `check_lease()` reads the account's recent orders and REFUSES if it finds a
  fill whose client_order_id does not carry our prefix and whose timestamp is
  after the lease opened. A foreign fill is proof of a second owner.
* The lease file records the owning PID, so a second copy of the loop on this
  same machine refuses too.

That turns an ownership assumption into an ownership *measurement*, which is the
same move `decision_authority` makes everywhere else in this programme.

WHAT IS REFUSED IN CODE, NOT IN INTENTION
=========================================
* **The live host.** `TRADING_HOST` is the paper host and `_host()` raises if
  anything ever points it at `api.alpaca.markets`. There is no flag for real
  money and adding one is not a small change.
* **Leverage.** Target notional may never exceed `equity * MAX_INVESTED_FRAC`,
  and `MAX_INVESTED_FRAC <= 1.0` is asserted at import. hack6 is currently
  running -$5,388 of cash — negative cash on a paper account is margin, and it
  is exactly what this refusal prevents.
* **Shorts.** Long-only. A negative target quantity is clipped to zero, never
  sent as a sell-short.
* **Concentration.** No name above `MAX_NAME_FRAC` of equity. The Bloomberg
  Challenge caps a single name at 20%; this sits below it deliberately so the
  competition rule is never the binding constraint.
* **Being the tape.** No order above `MAX_ADV_PARTICIPATION` of the name's
  20-session median dollar volume. A rank means nothing if entering the name
  moves it.

CREDENTIALS
===========
`ALPACA_PC_KEY_ID` / `ALPACA_PC_SECRET_KEY` and nothing else. No fallback to
another role's pair, and no aliasing onto `APCA_*`: on 2026-09-21 aliasing the
repo's ALPACA pair onto the venue's names shadowed P6's own working credential
and the night lost its bars. A missing pair REFUSES loudly and names the two
variables it wants.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# See `xs_ranker` for why these are not rooted on `Path(__file__)`.
from backend import config as _cfg

STATE_DIR = _cfg.OPTIMUS_LEDGER_DIR / "pc_book"
LEASE_PATH = STATE_DIR / "execution_lease.json"

TRADING_HOST = "https://paper-api.alpaca.markets"
DATA_HOST = "https://data.alpaca.markets"
LEASE_PREFIX = "aegispc"

KEY_ENV = "ALPACA_PC_KEY_ID"
SECRET_ENV = "ALPACA_PC_SECRET_KEY"

#: Murat wrote the pair into `.env` on 2026-09-22 as `PC-PAPER_key` /
#: `PC-PAPER_secret`. A hyphen is not a legal shell identifier, so
#: `export PC-PAPER_key=...` would be a syntax error and `$PC-PAPER_key` reads
#: as `$PC` minus `PAPER_key` — but `python-dotenv` puts it into `os.environ`
#: verbatim and `os.environ["PC-PAPER_key"]` retrieves it fine. Both spellings
#: are accepted so the file he actually wrote works, and the canonical
#: underscored names stay the ones the docs and errors name.
KEY_ALTS = (KEY_ENV, "PC-PAPER_key", "PC_PAPER_KEY")
SECRET_ALTS = (SECRET_ENV, "PC-PAPER_secret", "PC_PAPER_SECRET")

# ── the mandate, enforced below ─────────────────────────────────────────────
#: Fraction of equity that may be invested. 1.0 = fully invested, never levered.
MAX_INVESTED_FRAC = 1.00
#: Largest single position as a fraction of equity. Below the Challenge's 20%.
MAX_NAME_FRAC = 0.12
#: Largest single order as a fraction of the name's 20-session median $ volume.
MAX_ADV_PARTICIPATION = 0.02
#: Smallest order worth sending. Below this the cost is all of the edge.
MIN_ORDER_USD = 250.0
#: Orders per session, a circuit breaker on a loop that starts thrashing.
MAX_ORDERS_PER_SESSION = 120

#: Sampled into every NAV row at the same instant as equity, so a relative
#: return is computable later without re-fetching a close price and hoping the
#: clocks matched. SPY is the headline; IWM and QQQ separate "the market rose"
#: from "large caps rose" -- on 2026-09-21 SPY made +1.55% and IWM only +0.52%,
#: and a book of small names measured against the wrong one looks better or
#: worse than it was.
BENCHMARKS: tuple[str, ...] = ("SPY", "QQQ", "IWM")

assert MAX_INVESTED_FRAC <= 1.0, "MAX_INVESTED_FRAC > 1.0 is leverage"


class BrokerError(RuntimeError):
    """The broker cannot be used safely. Never swallowed into a no-op."""


class OwnershipConflict(BrokerError):
    """Another executor is trading this account. Halt, do not compete."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _host() -> str:
    h = os.environ.get("AEGIS_PC_TRADING_HOST", TRADING_HOST)
    if "paper-api" not in h:
        raise BrokerError(
            f"REFUSED: {h!r} is not a paper host. This module has no real-money "
            f"path and must not be given one.")
    return h


def credentials() -> tuple[str, str]:
    kid = next((os.environ[k] for k in KEY_ALTS if os.environ.get(k)), None)
    sec = next((s for s in SECRET_ALTS if os.environ.get(s)), None)
    sec = os.environ[sec] if sec else None
    if not kid or not sec:
        raise BrokerError(
            f"REFUSED: the PC paper account is not configured. Set {KEY_ENV} and "
            f"{SECRET_ENV} in .env (the PC-PAPER pair). Present: "
            f"{KEY_ENV}={'yes' if kid else 'NO'}, {SECRET_ENV}={'yes' if sec else 'NO'}. "
            f"No other role's credential is substituted, by design.")
    return kid, sec


def _headers() -> dict[str, str]:
    kid, sec = credentials()
    return {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec,
            "Content-Type": "application/json"}


def _call(method: str, path: str, *, host: str | None = None,
          params: dict | None = None, body: dict | None = None,
          timeout: float = 30.0) -> Any:
    url = (host or _host()) + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:   # noqa: S310 allowlisted host
            return json.loads(fh.read() or b"null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise BrokerError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


# ────────────────────────────── reading truth ───────────────────────────────

def account() -> dict:
    return _call("GET", "/v2/account")


def positions() -> list[dict]:
    return _call("GET", "/v2/positions") or []


def orders(status: str = "all", limit: int = 100, after: str | None = None) -> list[dict]:
    return _call("GET", "/v2/orders",
                 params={"status": status, "limit": limit, "direction": "desc",
                         "after": after}) or []


def clock() -> dict:
    """The VENUE's clock. Never the laptop's — the terminal repo learned that."""
    return _call("GET", "/v2/clock")


def last_prices(symbols: Iterable[str]) -> dict[str, float]:
    """Latest trade price per symbol, from the data host, in batches."""
    syms = [s for s in dict.fromkeys(symbols) if s]
    out: dict[str, float] = {}
    for i in range(0, len(syms), 200):
        chunk = syms[i:i + 200]
        # SIP is the consolidated tape and the PC-PAPER plan does not carry it:
        # measured 2026-09-22, `feed=sip` answers HTTP 403 "subscription does not
        # permit querying recent SIP data". IEX is free and real-time, covers a
        # smaller share of volume, and is the right default for a paper book that
        # only needs a mark. The feed used is RETURNED, because a price from a
        # partial tape is a different number and the caller should be able to say
        # which one it got.
        d = None
        for feed in ("sip", "iex"):
            try:
                d = _call("GET", "/v2/stocks/trades/latest", host=DATA_HOST,
                          params={"symbols": ",".join(chunk), "feed": feed})
                break
            except BrokerError as exc:
                if feed == "iex":
                    logger.warning("pc_broker: latest trades failed for %d symbols "
                                   "on every feed: %s", len(chunk), exc)
        if d is None:
            continue
        for sym, t in (d.get("trades") or {}).items():
            if t and t.get("p"):
                out[sym] = float(t["p"])
    return out


def snapshot(*, tag: str = "tick", out_dir: Path | None = None) -> dict:
    """Persist the venue's own view of the book. THE learning system's feedback.

    Written append-only to `nav.jsonl` so a night's equity curve survives a
    crash, plus `state_latest.json` for anything that wants one read.
    """
    d = Path(out_dir or STATE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    acct = account()
    pos = positions()
    payload = {
        "t": _now(),
        "tag": tag,
        "account_number": acct.get("account_number"),
        "equity": float(acct.get("equity") or 0.0),
        "last_equity": float(acct.get("last_equity") or 0.0),
        "cash": float(acct.get("cash") or 0.0),
        "long_market_value": float(acct.get("long_market_value") or 0.0),
        "short_market_value": float(acct.get("short_market_value") or 0.0),
        "buying_power": float(acct.get("buying_power") or 0.0),
        "n_positions": len(pos),
        "positions": [
            {"symbol": p["symbol"], "qty": float(p["qty"]),
             "avg_entry_price": float(p["avg_entry_price"]),
             "market_value": float(p["market_value"]),
             "unrealized_pl": float(p["unrealized_pl"]),
             "unrealized_plpc": float(p["unrealized_plpc"]),
             "current_price": float(p.get("current_price") or 0.0)}
            for p in pos
        ],
    }
    # THE BENCHMARK, recorded beside the equity and at the same instant.
    #
    # Without this, "paper NAV vs SPY" cannot be answered later at all: an
    # equity curve with no benchmark sampled on the same clock can only be
    # compared to a close price fetched afterwards, which is a different
    # question. Murat, 2026-09-22: the fleet made +0.60% on a day SPY made
    # +1.55% -- beta without alpha, and invisible until the two numbers sit in
    # one row.
    #
    # A failed quote is recorded as None with its reason. It is never dropped:
    # a missing benchmark that looks like "no data" would quietly turn a
    # relative number into an absolute one.
    try:
        bench = last_prices(BENCHMARKS)
        payload["benchmarks"] = {b: bench.get(b) for b in BENCHMARKS}
        payload["benchmark_error"] = None
    except BrokerError as exc:
        payload["benchmarks"] = {b: None for b in BENCHMARKS}
        payload["benchmark_error"] = str(exc)[:200]

    payload["invested_frac"] = (payload["long_market_value"] / payload["equity"]
                                if payload["equity"] else None)
    payload["intraday_return"] = (
        payload["equity"] / payload["last_equity"] - 1.0
        if payload["last_equity"] else None)
    with (d / "nav.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")
    (d / "state_latest.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


# ─────────────────────────────── the lease ──────────────────────────────────

def open_lease(*, owner: str = "live_market_loop", force: bool = False) -> dict:
    """Claim sole execution ownership of this account. Records the PID."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    acct = account()
    prior = None
    if LEASE_PATH.exists():
        try:
            prior = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = None
    if prior and prior.get("pid") and prior.get("open") and not force:
        if _pid_alive(int(prior["pid"])) and int(prior["pid"]) != os.getpid():
            raise OwnershipConflict(
                f"another loop holds the lease: pid {prior['pid']} since "
                f"{prior.get('opened')}. Kill it by that PID, or pass force=True "
                f"only if you have verified it is gone.")
    lease = {"open": True, "owner": owner, "pid": os.getpid(),
             "opened": _now(), "account_number": acct.get("account_number"),
             "equity_at_open": float(acct.get("equity") or 0.0),
             "prefix": LEASE_PREFIX}
    LEASE_PATH.write_text(json.dumps(lease, indent=1), encoding="utf-8")
    return lease


def close_lease() -> None:
    if not LEASE_PATH.exists():
        return
    try:
        d = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    d["open"] = False
    d["closed"] = _now()
    LEASE_PATH.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        import subprocess
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_lease(lease: dict) -> dict:
    """Is anyone ELSE trading this account? A foreign fill is proof that they are.

    Returns a verdict dict rather than raising, so the caller decides whether a
    conflict halts trading (it should) or only annotates the receipt.
    """
    opened = lease.get("opened")
    foreign = []
    for o in orders(status="all", limit=200):
        if opened and (o.get("submitted_at") or "") <= opened:
            continue
        coid = o.get("client_order_id") or ""
        if not coid.startswith(LEASE_PREFIX):
            foreign.append({"id": o.get("id"), "client_order_id": coid,
                            "symbol": o.get("symbol"), "side": o.get("side"),
                            "status": o.get("status"),
                            "submitted_at": o.get("submitted_at")})
    return {
        "conflict": bool(foreign),
        "n_foreign_orders": len(foreign),
        "foreign": foreign[:10],
        "verdict": ("OWNERSHIP CONFLICT: orders this loop did not place have "
                    "appeared since the lease opened. Another executor is live "
                    "on this account. HALT."
                    if foreign else "sole owner: every order since the lease "
                                    "opened carries this loop's prefix"),
    }


# ──────────────────────────────── ordering ──────────────────────────────────

@dataclass
class Target:
    """One line of the desired book. Weight is a fraction of EQUITY."""
    symbol: str
    weight: float
    reason: str = ""
    rank: int | None = None
    expected_relative_return_21d: float | None = None
    median_dollar_vol: float | None = None


@dataclass
class PlannedOrder:
    symbol: str
    side: str
    qty: int
    notional: float
    reason: str
    refused: str | None = None
    current_qty: float = 0.0
    target_qty: float = 0.0
    price: float = 0.0


def plan_orders(targets: list[Target], *, equity: float, held: dict[str, float],
                prices: dict[str, float],
                max_name_frac: float = MAX_NAME_FRAC,
                max_invested_frac: float = MAX_INVESTED_FRAC,
                min_order_usd: float = MIN_ORDER_USD) -> list[PlannedOrder]:
    """Desired book -> the orders that reach it, with every limit applied here.

    Refusals are RETURNED, not dropped. A name that wanted to trade and could
    not must appear on the receipt with the sentence that stopped it, or the
    morning report cannot answer "what rule blocked a profitable opportunity".
    """
    if equity <= 0:
        raise BrokerError(f"REFUSED: equity {equity} is not positive")

    tgt = {t.symbol: t for t in targets}
    total_w = sum(max(0.0, t.weight) for t in targets)
    if total_w > max_invested_frac + 1e-9:
        scale = max_invested_frac / total_w
        for t in targets:
            t.weight *= scale

    plans: list[PlannedOrder] = []
    for sym in dict.fromkeys(list(tgt) + list(held)):
        t = tgt.get(sym)
        px = prices.get(sym, 0.0)
        cur_qty = float(held.get(sym, 0.0))
        want_w = max(0.0, t.weight) if t else 0.0           # long-only: never < 0
        refusal = None

        if want_w > max_name_frac:
            refusal = (f"weight {want_w:.1%} exceeds MAX_NAME_FRAC {max_name_frac:.0%}; "
                       f"clipped")
            want_w = max_name_frac
        if px <= 0:
            plans.append(PlannedOrder(sym, "none", 0, 0.0,
                                      (t.reason if t else "exit"),
                                      refused=f"no price for {sym}; cannot size safely",
                                      current_qty=cur_qty))
            continue

        target_qty = int((want_w * equity) // px)
        delta = target_qty - int(cur_qty)
        notional = abs(delta) * px

        if delta == 0:
            continue
        if notional < min_order_usd and target_qty != 0:
            plans.append(PlannedOrder(sym, "buy" if delta > 0 else "sell", 0, notional,
                                      (t.reason if t else "exit"),
                                      refused=(f"${notional:,.0f} < MIN_ORDER_USD "
                                               f"${min_order_usd:,.0f}: the cost is the edge"),
                                      current_qty=cur_qty, target_qty=target_qty, price=px))
            continue

        adv = (t.median_dollar_vol if t else None)
        if adv and notional > adv * MAX_ADV_PARTICIPATION:
            capped = int((adv * MAX_ADV_PARTICIPATION) // px)
            refusal = (f"order ${notional:,.0f} is "
                       f"{notional/adv:.2%} of 20d median $vol; capped at "
                       f"{MAX_ADV_PARTICIPATION:.0%} (={capped} sh)")
            delta = capped if delta > 0 else -capped
            notional = abs(delta) * px
            if delta == 0:
                plans.append(PlannedOrder(sym, "none", 0, 0.0, (t.reason if t else "exit"),
                                          refused=refusal, current_qty=cur_qty,
                                          target_qty=target_qty, price=px))
                continue

        plans.append(PlannedOrder(
            symbol=sym, side="buy" if delta > 0 else "sell", qty=abs(int(delta)),
            notional=notional, reason=(t.reason if t else "not in the ranked book: exit"),
            refused=refusal, current_qty=cur_qty, target_qty=target_qty, price=px))

    # sells first: they free the buying power the buys need
    plans.sort(key=lambda p: (p.side != "sell", -p.notional))
    return plans


def submit(plan: PlannedOrder, *, tif: str = "day", dry_run: bool = False) -> dict:
    """Send ONE order, tagged with the lease prefix so ownership is provable."""
    if plan.qty <= 0 or plan.side not in ("buy", "sell"):
        return {"status": "skipped", "why": "nothing to send", "plan": asdict(plan)}
    coid = f"{LEASE_PREFIX}-{uuid.uuid4().hex[:20]}"
    body = {"symbol": plan.symbol, "qty": str(plan.qty), "side": plan.side,
            "type": "market", "time_in_force": tif, "client_order_id": coid}
    if dry_run:
        return {"status": "dry_run", "order": body, "plan": asdict(plan)}
    r = _call("POST", "/v2/orders", body=body)
    return {"status": "submitted", "client_order_id": coid, "order_id": r.get("id"),
            "symbol": plan.symbol, "side": plan.side, "qty": plan.qty,
            "notional": plan.notional, "reason": plan.reason, "submitted_at": _now()}


def held_quantities() -> dict[str, float]:
    return {p["symbol"]: float(p["qty"]) for p in positions()}
