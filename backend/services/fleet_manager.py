"""THE FLEET DAILY MANAGER: the hack1-hack6 paper accounts, managed from this PC.

    python -m scripts.fleet_manager_run --pass open            # dry run, every account
    python -m scripts.fleet_manager_run --pass open --live     # per-account modes decide

WHY (2026-09-29 night)
======================
Murat: *"update the hacks positions daily. do either locally or with railway.
update them based on the latest results and the news."* The four Railway loops
(hack1/4/5/6) were taken down the same day for the $20/month budget. Positions
stayed at the broker protected only by resting GTC stops: nothing re-entered,
took an exit the contract called for, or replaced a stop. This module is the
logic; `scripts/fleet_manager_run.py` is the only caller that talks to the venue.

WHAT THE RESEARCH ALLOWS US TO SAY (and therefore what this is not)
===================================================================
No rule on disk has a demonstrated edge over the market net of costs (CRSP
library: 133 rules, 0 pass the deflated Sharpe). LLM direction calls are at
coin level. The SIZE of a move is forecastable, so stops are quoted in daily
sigma. News implications are ungraded until 2026-10-09. So the daily update is
a disciplined PAPER process that generates graded evidence -- one account per
alpha source so the errors differ -- never a claim of skill. Licence:
PRODUCT_EXPERIMENT for every contract here.

THE RULES THAT ARE CODE, NOT INTENTION
======================================
* Paper host only (`Venue` refuses anything else). No option order can be
  built: `check_limits` refuses a symbol that is not a plain equity ticker.
* Long only: a sell may never exceed the long quantity held (no shorting).
* Gross <= FLEET_MANAGER_MAX_GROSS_FRAC of equity and cash after every buy >= 0
  (no leverage); one name <= FLEET_MANAGER_MAX_NAME_FRAC; a daily turnover
  budget on every non-protective order; a per-run order cap.
* Limit orders near the quote, stop orders for protection; never a market order.
* Orders only while the venue's clock says open and >= N minutes before close.
* Idempotent client order ids: (role, session day, kind, symbol, contract
  hash, intent) -> one id, checked at the venue before a POST, so a re-run
  cannot double-submit.
* Reconciliation first: the broker's positions must equal the last recorded
  positions plus the fills since, and no order without our prefix may have
  been submitted since. Any mismatch REFUSES every order on that account.
* Every decision is a dated row written BEFORE the order is sent.
* A contract is frozen by content (policy hash) before its first decision; a
  changed rule is a new version, never an edit.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend import config as _cfg

LICENCE = "PRODUCT_EXPERIMENT"
TRADING_HOST = "https://paper-api.alpaca.markets"
DATA_HOST = "https://data.alpaca.markets"
COID_PREFIX = "aegisfm"
#: Protective stops the Railway loops left resting. Adopted (counted as cover),
#: never re-submitted under this prefix.
LEGACY_STOP_PREFIX = "aat-stop-"
STOP_TYPES = ("stop", "stop_limit", "trailing_stop")
DEAD_STATUSES = ("canceled", "expired", "rejected", "done_for_day", "replaced")
_EQUITY_TICKER = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")


class FleetRefusal(RuntimeError):
    """An order or a run that must not happen. Never swallowed into a no-op."""


# ─────────────────────────────── paths ──────────────────────────────────────

def root(base: Optional[Path] = None) -> Path:
    return Path(base) if base else Path(_cfg.OPTIMUS_LEDGER_DIR) / "paper_accounts" / "fleet_manager"


def stop_file(base: Optional[Path] = None) -> Path:
    return root(base) / "STOP"


def contracts_dir(base: Optional[Path] = None) -> Path:
    return root(base) / "contracts"


def state_path(role: str, base: Optional[Path] = None) -> Path:
    return root(base) / "state" / f"{role}.json"


def decisions_path(base: Optional[Path] = None) -> Path:
    return root(base) / "decisions.jsonl"


def grades_path(base: Optional[Path] = None) -> Path:
    return root(base) / "grades.jsonl"


def modes_path(base: Optional[Path] = None) -> Path:
    return root(base) / "modes.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(*parts: Any, n: int = 16) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:n]


def atomic_write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))          # verify before replace
    tmp.replace(p)


def append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
        fh.flush()


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


# ─────────────────────────────── contracts ──────────────────────────────────

def policy_hash(body: dict) -> str:
    core = {k: v for k, v in body.items() if k not in ("policy_hash", "frozen_utc")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def contract_file(role: str, version: str, base: Optional[Path] = None) -> Path:
    return contracts_dir(base) / f"{role}_{version}.json"


def freeze_contract(body: dict, base: Optional[Path] = None) -> dict:
    """Write once. An existing file with a DIFFERENT hash refuses: a changed
    rule is a new version, never an edit of a frozen one."""
    _refuse_prepared(body, "freeze")
    h = policy_hash(body)
    p = contract_file(body["role"], body["version"], base)
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        if old.get("policy_hash") != h:
            raise FleetRefusal(f"REFUSED: {p.name} is frozen as {old.get('policy_hash')}; the rule "
                               f"now hashes to {h}. A changed rule is a new version, not an edit.")
        return old
    out = dict(body)
    out["policy_hash"] = h
    out["frozen_utc"] = _now_iso()
    atomic_write_json(p, out)
    return out


def load_contract(role: str, version: str, base: Optional[Path] = None) -> dict:
    p = contract_file(role, version, base)
    if not p.exists():
        raise FleetRefusal(f"REFUSED: no frozen contract {p.name}; freeze before the first decision")
    c = json.loads(p.read_text(encoding="utf-8"))
    if policy_hash(c) != c.get("policy_hash"):
        raise FleetRefusal(f"REFUSED: {p.name} content does not match its policy hash (edited after freeze)")
    _refuse_prepared(c, f"load {p.name}")
    return c


def _refuse_prepared(body: dict, what: str) -> None:
    """C20 (2026-10-07): a v3 contract is written `PREPARED_NOT_SEEDED` under
    `contracts_v3/`, and NO seed path may act on it. Activation is the owner's
    act (D2): a re-freeze whose only difference is the status. A prepared body
    that reaches the live folder -- copied by hand, or passed to freeze -- is
    refused here, before any decision is made on it."""
    if str(body.get("status") or "").startswith(str(_cfg.FLEET_V3_STATUS_PREPARED)):
        raise FleetRefusal(f"REFUSED: {what}: contract {body.get('role')} {body.get('version')} "
                           f"is {_cfg.FLEET_V3_STATUS_PREPARED}; seeding it is the owner's act "
                           f"(roadmap 2026-10-06 §6 D2), not a fleet-manager path")


def name_cap(caps: dict, symbol: str) -> float:
    """The per-name cap for `symbol`: the contract's override when it names one
    (the market CONTROL holds ~95% in one broad ETF), else max_name_frac."""
    ov = caps.get("name_cap_overrides") or {}
    return float(ov.get(symbol, caps["max_name_frac"]))


def caps_block() -> dict:
    return {"max_gross_frac": _cfg.FLEET_MANAGER_MAX_GROSS_FRAC,
            "max_name_frac": _cfg.FLEET_MANAGER_MAX_NAME_FRAC,
            "daily_turnover_frac": _cfg.FLEET_MANAGER_DAILY_TURNOVER_FRAC,
            "max_orders_per_run": _cfg.FLEET_MANAGER_MAX_ORDERS_PER_RUN,
            "min_order_usd": _cfg.FLEET_MANAGER_MIN_ORDER_USD,
            "shorting": False, "new_options": False, "leverage": False}


def stop_rule_block(max_frac: float) -> dict:
    return {"quoted_in": "daily sigma",
            "sigma": (f"{_cfg.FLEET_MANAGER_SIGMA_WINDOW}-session sd of close-to-close returns on the "
                      "bar-defect-screened panel (Alpaca daily bars when a name is not in the panel)"),
            "k_sigma": _cfg.FLEET_MANAGER_STOP_K_SIGMA,
            "min_frac": _cfg.FLEET_MANAGER_STOP_MIN_FRAC,
            "max_frac": float(max_frac),
            "distance": "clip(k_sigma x sigma, min_frac, max_frac) of the reference price",
            "never_loosen": "a replaced stop is never below the stop it replaces",
            "order": "GTC sell stop for the full long quantity; renewed within "
                     f"{_cfg.FLEET_MANAGER_STOP_RENEW_DAYS} days of its expiry"}


def costs_block() -> dict:
    return {"assumed_bps_per_side": _cfg.FLEET_MANAGER_COST_BPS_PER_SIDE,
            "fill_convention": (f"DAY limit at ask x (1+{_cfg.FLEET_MANAGER_LIMIT_SLIP_BPS:g}bps) for buys and "
                                f"bid x (1-{_cfg.FLEET_MANAGER_LIMIT_SLIP_BPS:g}bps) for sells; an unfilled "
                                "limit is not traded; last trade when the IEX quote is one-sided or wider "
                                f"than {_cfg.FLEET_MANAGER_MAX_SPREAD_FRAC:.0%}")}


# ─────────────────────────────── stops in sigma ─────────────────────────────

def sigma_stop_frac(sigma_d: Optional[float], *, max_frac: float,
                    k: Optional[float] = None, min_frac: Optional[float] = None) -> tuple[float, str]:
    """Stop distance as a fraction of price, and how it was derived."""
    k = _cfg.FLEET_MANAGER_STOP_K_SIGMA if k is None else k
    lo = _cfg.FLEET_MANAGER_STOP_MIN_FRAC if min_frac is None else min_frac
    lo = min(lo, max_frac)
    if sigma_d is None or not math.isfinite(sigma_d) or sigma_d <= 0:
        return float(max_frac), "no sigma: the contract's maximum distance"
    raw = k * sigma_d
    d = min(max(raw, lo), max_frac)
    how = f"{k:g} x sigma {sigma_d:.4f} = {raw:.4f}"
    if d != raw:
        how += f", clipped to [{lo:.3f}, {max_frac:.3f}] -> {d:.4f}"
    return float(d), how


def contract_stop_frac(contract: dict, sigma_d: Optional[float]) -> tuple[float, str]:
    """The stop distance under THIS contract's frozen stop rule (k, floor, cap).
    Contracts frozen before 2026-09-30 carry the config values, so the result
    is unchanged for them; the market control declares a wide disaster stop."""
    sr = contract["stop_rule"]
    return sigma_stop_frac(sigma_d, max_frac=float(sr["max_frac"]), k=sr.get("k_sigma"),
                           min_frac=sr.get("min_frac"))


def round_price(p: float) -> float:
    """Alpaca's tick: cents at or above $1, four decimals below."""
    return round(p, 2) if p >= 1.0 else round(p, 4)


def stop_price_for(ref_price: float, frac: float) -> float:
    return round_price(ref_price * (1.0 - frac))


def sigma_from_closes(closes: Iterable[float], window: Optional[int] = None) -> Optional[float]:
    w = window or _cfg.FLEET_MANAGER_SIGMA_WINDOW
    xs = [float(c) for c in closes if c is not None and float(c) > 0]
    if len(xs) < min(w, 40) + 1:
        return None
    xs = xs[-(w + 1):]
    rets = [xs[i] / xs[i - 1] - 1.0 for i in range(1, len(xs))]
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    s = math.sqrt(var)
    return s if s > 0 else None


# ─────────────────────────────── ids ────────────────────────────────────────

def client_order_id(role: str, day: str, kind: str, symbol: str, contract_hash: str,
                    intent: str = "") -> str:
    """Deterministic per (role, session day, kind, symbol, contract, intent).
    Price is deliberately NOT in the key: a re-run a minute later sees a new
    price and must still map to the same id."""
    h = _sha(role, day, kind, symbol, contract_hash, intent, n=10)
    return f"{COID_PREFIX}-{role}-{day.replace('-', '')}-{kind}-{symbol}-{h}"[:128]


# ─────────────────────────────── reconciliation ─────────────────────────────

def signed_positions(positions: Iterable[dict]) -> dict[str, float]:
    return {p["symbol"]: float(p["qty"]) for p in positions}


def reconcile(prev_positions: Optional[dict[str, float]], fills: Iterable[dict],
              broker_positions: dict[str, float], orders_since: Iterable[dict]) -> dict:
    """Broker truth == previous record + fills since, and nobody else is trading.

    `fills` are Alpaca FILL activities (side buy / sell / sell_short).
    `orders_since` are orders SUBMITTED after the previous record; any without
    our prefix is proof of a second executor."""
    foreign = [{"client_order_id": o.get("client_order_id"), "symbol": o.get("symbol"),
                "side": o.get("side"), "status": o.get("status"),
                "submitted_at": o.get("submitted_at")}
               for o in orders_since if not str(o.get("client_order_id") or "").startswith(COID_PREFIX)]
    if prev_positions is None:
        return {"status": "NO_BASELINE", "ok": False, "mismatches": [], "foreign_orders": foreign,
                "why": "no previous record to reconcile against; run --rebaseline after checking"}
    expected = dict(prev_positions)
    for f in fills:
        q = float(f.get("qty") or 0)
        sgn = 1.0 if f.get("side") == "buy" else -1.0
        expected[f["symbol"]] = expected.get(f["symbol"], 0.0) + sgn * q
    mism = []
    for sym in sorted(set(expected) | set(broker_positions)):
        e, b = expected.get(sym, 0.0), broker_positions.get(sym, 0.0)
        if abs(e - b) > 1e-6:
            mism.append({"symbol": sym, "expected": e, "broker": b})
    ok = not mism and not foreign
    return {"status": "OK" if ok else ("MISMATCH" if mism else "FOREIGN_ORDERS"), "ok": ok,
            "mismatches": mism, "foreign_orders": foreign}


# ─────────────────────────────── entry dates / sessions ─────────────────────

def sessions_between(start: date, end: date) -> int:
    """Weekday sessions after `start` up to and including `end` (holidays
    ignored: one session of error on a horizon of 21+)."""
    if end <= start:
        return 0
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def lot_entry_date(held_qty: float, fills_desc: list[dict]) -> tuple[Optional[date], str]:
    """Walk the fills newest-first, un-doing them until the lot is empty; the
    fill that empties it is the lot's first entry."""
    running = float(held_qty)
    last = None
    for f in fills_desc:
        q = float(f.get("qty") or 0)
        running += -q if f.get("side") == "buy" else q
        last = f
        if running <= 1e-9:
            return date.fromisoformat(str(f["transaction_time"])[:10]), "exact"
    if last is not None:
        return date.fromisoformat(str(last["transaction_time"])[:10]), "oldest fill read (lot older)"
    return None, "no fills read"


# ─────────────────────────────── actions ────────────────────────────────────

@dataclass
class Action:
    role: str
    kind: str                     # stop_new | stop_renew | cancel | exit | buy | sell
    symbol: str
    qty: int = 0
    side: str = ""
    order_type: str = ""          # limit | stop | cancel
    tif: str = "day"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    price_ref: float = 0.0
    reason: str = ""
    protective: bool = False
    cancel_order_id: Optional[str] = None
    coid: str = ""
    inputs: dict = field(default_factory=dict)
    refused: Optional[str] = None

    @property
    def notional(self) -> float:
        return abs(self.qty) * float(self.limit_price or self.stop_price or self.price_ref or 0.0)

    def body(self) -> dict:
        b: dict[str, Any] = {"symbol": self.symbol, "qty": str(int(self.qty)), "side": self.side,
                             "type": self.order_type, "time_in_force": self.tif,
                             "client_order_id": self.coid}
        if self.limit_price is not None:
            b["limit_price"] = f"{self.limit_price:.4f}".rstrip("0").rstrip(".")
        if self.stop_price is not None:
            b["stop_price"] = f"{self.stop_price:.4f}".rstrip("0").rstrip(".")
        return b


def stops_for(symbol: str, open_orders: Iterable[dict]) -> list[dict]:
    return [o for o in open_orders if o.get("symbol") == symbol and o.get("side") == "sell"
            and o.get("type") in STOP_TYPES]


def plan_maintenance(role: str, positions: list[dict], open_orders: list[dict],
                     sigma: dict[str, Optional[float]], contract: dict, day: str,
                     today: date) -> tuple[list[Action], list[str], list[dict]]:
    """Every long share position has resting stops for its full quantity; a
    stop expiring soon is renewed; options and shorts are FLAGGED, never
    traded here."""
    h = contract["policy_hash"]
    acts: list[Action] = []
    flags: list[str] = []
    table: list[dict] = []
    renew = timedelta(days=_cfg.FLEET_MANAGER_STOP_RENEW_DAYS)
    for p in positions:
        sym, qty = p["symbol"], float(p["qty"])
        px = float(p.get("current_price") or 0.0)
        if p.get("asset_class") == "us_option":
            exp = option_expiry(sym)
            if exp and (exp - today).days <= _cfg.FLEET_MANAGER_OPTION_ALERT_DTE:
                flags.append(f"OPTION_DTE {sym} expires {exp}")
            if qty < 0:
                flags.append(f"SHORT_OPTION_LEG {sym} {qty:g} (checked for cover by root below)")
            continue
        if qty < 0:
            flags.append(f"SHORT_SHARES {sym} {qty:g}: not covered automatically; owner decides")
            continue
        sig = sigma.get(sym)
        frac, how = contract_stop_frac(contract, sig)
        stops = stops_for(sym, open_orders)
        covered = sum(float(o.get("qty") or 0) for o in stops)
        row = {"symbol": sym, "qty": qty, "price": px, "sigma_d": sig, "target_stop_frac": round(frac, 4),
               "target_stop_how": how,
               "resting": [{"stop_price": o.get("stop_price"), "qty": o.get("qty"),
                            "client_order_id": o.get("client_order_id"), "expires_at": o.get("expires_at"),
                            "distance_frac": (round((px - float(o["stop_price"])) / px, 4)
                                              if px and o.get("stop_price") else None),
                            "distance_sigma": (round((px - float(o["stop_price"])) / px / sig, 2)
                                               if px and sig and o.get("stop_price") else None)}
                           for o in stops]}
        table.append(row)
        if px <= 0:
            flags.append(f"NO_PRICE {sym}: cannot place a stop safely")
            continue
        uncovered = int(math.floor(qty - covered + 1e-9))
        if uncovered > 0:
            sp = stop_price_for(px, frac)
            acts.append(Action(role, "stop_new", sym, uncovered, "sell", "stop", "gtc",
                               stop_price=sp, price_ref=px, protective=True,
                               reason=f"UNPROTECTED: stops cover {covered:g} of {qty:g}; stop at {how}",
                               coid=client_order_id(role, day, "stop", sym, h, f"{uncovered}"),
                               inputs={"sigma_d": sig, "stop_frac": frac}))
        for o in stops:
            exp_at = o.get("expires_at")
            if not exp_at:
                continue
            try:
                exp_dt = datetime.fromisoformat(str(exp_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            if exp_dt - datetime.now(timezone.utc) <= renew:
                old = float(o.get("stop_price") or 0)
                sp = max(old, stop_price_for(px, frac))
                if sp >= px:
                    flags.append(f"STOP_RENEW_REFUSED {sym}: renewed stop {sp} would be at/above price {px}")
                    continue
                q = int(float(o.get("qty") or 0))
                acts.append(Action(role, "cancel", sym, 0, "", "cancel", protective=True,
                                   cancel_order_id=o.get("id"), price_ref=px,
                                   reason=f"stop {o.get('client_order_id')} expires {exp_at}: renew",
                                   coid=f"cancel:{o.get('id')}"))
                acts.append(Action(role, "stop_renew", sym, q, "sell", "stop", "gtc", stop_price=sp,
                                   price_ref=px, protective=True,
                                   reason=f"renewal of an expiring stop, never below it ({old})",
                                   coid=client_order_id(role, day, "stoprenew", sym, h, f"{q}")))
    # a short option leg must be covered by a long leg of the same root
    roots: dict[str, float] = {}
    for p in positions:
        if p.get("asset_class") == "us_option":
            r = p["symbol"][:-15]
            roots[r] = roots.get(r, 0.0) + float(p["qty"])
    for r, net in roots.items():
        if net < 0:
            flags.append(f"NAKED_SHORT_OPTIONS {r}: net {net:g} contracts")
    return acts, flags, table


def option_expiry(sym: str) -> Optional[date]:
    if len(sym) < 16:
        return None
    try:
        return datetime.strptime(sym[-15:][:6], "%y%m%d").date()
    except ValueError:
        return None


def plan_horizon_exits(role: str, positions: list[dict], entry: dict[str, Optional[date]],
                       contract: dict, legacy: set[str], today: date, day: str,
                       held_by_version: Optional[dict[str, str]] = None) -> list[Action]:
    """Exit a legacy position whose declared horizon has passed (the frozen
    v1 terms). v2 names are handled by the rebalance."""
    acts = []
    lt = contract.get("legacy_terms") or {}
    hz = lt.get("expected_horizon_sessions")
    if not hz:
        return acts
    for p in positions:
        sym = p["symbol"]
        if sym not in legacy or p.get("asset_class") == "us_option" or float(p["qty"]) <= 0:
            continue
        e = entry.get(sym)
        if e is None:
            continue
        n = sessions_between(e, today)
        if n >= int(hz):
            acts.append(Action(role, "exit", sym, int(float(p["qty"])), "sell", "limit", "day",
                               price_ref=float(p.get("current_price") or 0),
                               reason=f"HORIZON: {n} sessions since entry {e} >= declared {hz}",
                               coid=client_order_id(role, day, "exit", sym, contract["policy_hash"])))
    return acts


# ─────────────────────────────── targets ────────────────────────────────────

def book_targets(book_positions: Iterable[dict], *, max_name: float,
                 excluded: Optional[dict[str, str]] = None,
                 issuer_of: Optional[dict[str, str]] = None) -> tuple[dict[str, float], list[dict]]:
    """A frozen book -> target weights, every drop named. Weights are CLIPPED
    at the name cap and NOT renormalised: what is dropped stays cash."""
    excluded = excluded or {}
    issuer_of = issuer_of or {}
    rows = sorted(((str(p["ticker"]).upper(), float(p["weight"])) for p in book_positions
                   if str(p.get("ticker")).upper() != "CASH" and float(p.get("weight") or 0) > 0),
                  key=lambda t: -t[1])
    out: dict[str, float] = {}
    drops: list[dict] = []
    seen_issuer: dict[str, str] = {}
    for t, w in rows:
        if not _EQUITY_TICKER.match(t):
            drops.append({"symbol": t, "why": "not a plain equity ticker"})
            continue
        if t in excluded:
            drops.append({"symbol": t, "why": excluded[t]})
            continue
        iss = issuer_of.get(t)
        if iss and iss in seen_issuer:
            drops.append({"symbol": t, "why": f"second share class of issuer {iss} (kept {seen_issuer[iss]})"})
            continue
        if iss:
            seen_issuer[iss] = t
        if w > max_name:
            drops.append({"symbol": t, "why": f"weight {w:.3f} clipped to {max_name:.3f}", "clipped": True})
            w = max_name
        out[t] = w
    return out, drops


def news_targets(signal: dict[str, dict], *, unit: float, max_names: int,
                 excluded: Optional[dict[str, str]] = None,
                 already_moved: Optional[dict[str, float]] = None,
                 max_moved: Optional[float] = None) -> tuple[dict[str, float], list[dict]]:
    """SHADOW_NEWS_v0's typed signal -> a fixed-unit sleeve. Only d > 0 (long
    only), strongest first; a name that already moved more than `max_moved`
    5-session sigmas is not chased."""
    excluded = excluded or {}
    already_moved = already_moved or {}
    mm = _cfg.FLEET_MANAGER_NEWS_MAX_ALREADY_MOVED_SIGMA if max_moved is None else max_moved
    cand = sorted(((t, s) for t, s in signal.items() if float(s.get("d") or 0) > 0),
                  key=lambda ts: (-float(ts[1]["d"]), -int(ts[1].get("n") or 0), ts[0]))
    out: dict[str, float] = {}
    drops: list[dict] = []
    for t, s in cand:
        if len(out) >= max_names:
            drops.append({"symbol": t, "why": f"beyond the {max_names}-name sleeve"})
            continue
        if not _EQUITY_TICKER.match(t):
            drops.append({"symbol": t, "why": "not a plain equity ticker"})
            continue
        if t in excluded:
            drops.append({"symbol": t, "why": excluded[t]})
            continue
        mv = already_moved.get(t)
        if mv is not None and mv > mm:
            drops.append({"symbol": t, "why": f"already moved {mv:+.2f} 5-session sigma > {mm:g}"})
            continue
        out[t] = unit
    return out, drops


# ─────────────────────────────── the rebalance ──────────────────────────────

def plan_rebalance(role: str, targets: dict[str, float], *, equity: float,
                   held: dict[str, float], prices: dict[str, float], legacy: set[str],
                   pending: dict[str, float], contract: dict, day: str,
                   exit_untargeted: bool = True) -> list[Action]:
    """Targets -> buys/sells. Legacy names (held under the previous version's
    terms) are neither sold nor counted as capacity: v2 fills what remains of
    the gross cap. Refusals are returned on the Action, never dropped."""
    if equity <= 0:
        raise FleetRefusal(f"REFUSED: equity {equity} is not positive")
    caps = contract["caps"]
    h = contract["policy_hash"]
    legacy_gross = sum(abs(held.get(s, 0.0)) * prices.get(s, 0.0) for s in legacy)
    capacity = max(0.0, caps["max_gross_frac"] * equity - legacy_gross)
    want_total = sum(targets.values()) * equity
    scale = min(1.0, capacity / want_total) if want_total > 0 else 0.0
    acts: list[Action] = []
    names = list(dict.fromkeys(list(targets) + [s for s in held if s not in legacy]))
    for sym in names:
        if sym in legacy:
            continue
        px = float(prices.get(sym) or 0.0)
        cur = float(held.get(sym, 0.0)) + float(pending.get(sym, 0.0))
        w = min(float(targets.get(sym, 0.0)), name_cap(caps, sym)) * scale
        if sym not in targets and not exit_untargeted:
            continue
        if px <= 0:
            acts.append(Action(role, "buy" if sym in targets else "sell", sym, 0, price_ref=0.0,
                               reason="target" if sym in targets else "not in target: exit",
                               refused=f"no price for {sym}; cannot size safely"))
            continue
        tq = int((w * equity) // px)
        delta = tq - int(cur)
        if delta == 0:
            continue
        side = "buy" if delta > 0 else "sell"
        a = Action(role, side, sym, abs(delta), side, "limit", "day", price_ref=px,
                   reason=(f"target {w:.4f} of equity (scale {scale:.3f}); held {cur:g} -> {tq}"
                           if sym in targets else "held under this version, no longer targeted: exit"),
                   coid=client_order_id(role, day, side, sym, h),
                   inputs={"target_weight": round(w, 6), "scale": round(scale, 4), "target_qty": tq,
                           "held_plus_pending": cur})
        if abs(delta) * px < caps["min_order_usd"] and tq != 0:
            a.refused = f"${abs(delta) * px:,.0f} < min order ${caps['min_order_usd']:,.0f}"
        acts.append(a)
    acts.sort(key=lambda a: (a.side != "sell", -a.notional))
    return acts


def apply_turnover_budget(acts: list[Action], *, equity: float, used_today: float,
                          frac: float) -> float:
    """Non-protective orders spend the session's turnover budget in order;
    beyond it they are refused by name. Returns the notional spent."""
    budget = frac * equity - used_today
    spent = 0.0
    for a in acts:
        if a.protective or a.refused or a.kind in ("exit", "cancel"):
            continue
        if spent + a.notional > budget + 1e-6:
            a.refused = (f"daily turnover budget: ${spent + a.notional:,.0f} would exceed "
                         f"${budget:,.0f} left of {frac:.0%} x equity")
            continue
        spent += a.notional
    return spent


# ─────────────────────────────── the hard gate ──────────────────────────────

def check_limits(a: Action, *, equity: float, cash: float, held: dict[str, float],
                 mv: dict[str, float], gross: float, contract: dict) -> Optional[str]:
    """The last check before ANY order. Returns the refusal sentence or None.

    Mutates nothing; the caller updates `cash`, `mv` and `gross` after a pass."""
    caps = contract["caps"]
    if a.kind == "cancel":
        return None
    if not _EQUITY_TICKER.match(a.symbol):
        return f"{a.symbol} is not a plain equity ticker: no option or other order is ever built here"
    if a.qty <= 0:
        return "quantity is not positive"
    if a.order_type not in ("limit", "stop"):
        return f"order type {a.order_type!r} refused: limit or stop only, never market"
    if a.side == "sell":
        long_q = max(0.0, held.get(a.symbol, 0.0))
        if a.qty > long_q + 1e-9:
            return (f"sell {a.qty} > long {long_q:g} held: would open a short "
                    f"(shorting is {'allowed' if caps.get('shorting') else 'refused'} for this contract)")
        if a.order_type == "stop" and not a.protective:
            return "a stop order must be protective"
        return None
    if a.side != "buy":
        return f"side {a.side!r} refused"
    if a.limit_price is None or a.limit_price <= 0:
        return "a buy needs a limit price near the quote"
    notional = a.qty * a.limit_price
    if cash - notional < -1e-6:
        return f"cash ${cash:,.0f} - ${notional:,.0f} < 0: would borrow (no leverage)"
    if gross + notional > caps["max_gross_frac"] * equity + 1e-6:
        return (f"gross ${gross + notional:,.0f} > {caps['max_gross_frac']:.0%} of equity "
                f"${equity:,.0f}")
    cap = name_cap(caps, a.symbol)
    if mv.get(a.symbol, 0.0) + notional > cap * equity * 1.005:
        return (f"{a.symbol} would be ${mv.get(a.symbol, 0.0) + notional:,.0f} > "
                f"{cap:.0%} of equity")
    return None


# ─────────────────────────────── pricing ────────────────────────────────────

def limit_for(side: str, quote: Optional[dict], last: Optional[float]) -> tuple[Optional[float], str]:
    slip = _cfg.FLEET_MANAGER_LIMIT_SLIP_BPS / 1e4
    bid = float((quote or {}).get("bp") or 0)
    ask = float((quote or {}).get("ap") or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2
        if (ask - bid) / mid <= _cfg.FLEET_MANAGER_MAX_SPREAD_FRAC:
            p = ask * (1 + slip) if side == "buy" else bid * (1 - slip)
            return round_price(p), f"quote bid {bid} ask {ask}"
    if last and last > 0:
        p = last * (1 + slip) if side == "buy" else last * (1 - slip)
        return round_price(p), f"last trade {last} (IEX quote one-sided or wide: bid {bid} ask {ask})"
    return None, "no quote and no last trade"


# ─────────────────────────────── worst case ─────────────────────────────────

def worst_case(positions: list[dict], open_orders: list[dict], planned: Iterable[Action],
               equity: float, stop_frac_for_new: dict[str, float]) -> dict:
    """Dollars lost if every stop fills at its price (gaps can be worse), plus
    gross / equity, over what is held AND what this run would add."""
    per, gross, n = [], 0.0, 0
    for p in positions:
        if p.get("asset_class") == "us_option":
            mv = float(p.get("market_value") or 0)
            gross += abs(mv)
            per.append({"symbol": p["symbol"], "worst_usd": max(0.0, mv), "basis": "option value to zero"})
            continue
        qty, px = float(p["qty"]), float(p.get("current_price") or 0)
        mv = qty * px
        gross += abs(mv)
        n += 1
        st = stops_for(p["symbol"], open_orders)
        cov = sum(float(o.get("qty") or 0) for o in st)
        if qty > 0 and st and cov + 1e-9 >= qty:
            sp = min(float(o.get("stop_price") or 0) for o in st)
            per.append({"symbol": p["symbol"], "worst_usd": max(0.0, (px - sp) * qty),
                        "basis": f"resting stop {sp}"})
        else:
            per.append({"symbol": p["symbol"], "worst_usd": abs(mv), "basis": "no full stop: whole position"})
    for a in planned:
        if a.refused or a.side != "buy":
            continue
        px = float(a.limit_price or a.price_ref or 0)
        f = stop_frac_for_new.get(a.symbol, _cfg.FLEET_MANAGER_STOP_MIN_FRAC)
        gross += a.qty * px
        n += 1
        per.append({"symbol": a.symbol, "worst_usd": a.qty * px * f, "basis": f"planned stop {f:.3f}"})
    tot = sum(r["worst_usd"] for r in per)
    return {"worst_usd": round(tot, 2), "worst_pct_equity": round(100 * tot / equity, 2) if equity else None,
            "gross_usd": round(gross, 2), "gross_over_equity": round(gross / equity, 4) if equity else None,
            "n_names": n, "per_name": per}


def formula_worst_case(n: int, notional_frac: float, stop_frac: float, equity: float) -> dict:
    """CLAUDE.md protocol 4, for the largest admissible book of a contract."""
    frac = n * notional_frac * stop_frac
    return {"n": n, "notional_frac": round(notional_frac, 4), "stop_frac": round(stop_frac, 4),
            "worst_frac": round(frac, 4), "worst_usd": round(frac * equity, 2),
            "gross_over_equity": round(n * notional_frac, 4)}


# ─────────────────────────────── twins and grades ───────────────────────────

def matched_random_twin(held_weights: dict[str, float], sigma: dict[str, float],
                        pool: dict[str, float], seed: int) -> dict[str, float]:
    """Each held name -> a random pool name in the same sigma decile (pool
    deciles), drawn without replacement with a fixed seed. Weights copied."""
    import random
    rng = random.Random(seed)
    items = sorted((s, v) for s, v in pool.items() if v and v > 0 and s not in held_weights)
    if not items:
        return {}
    vals = sorted(v for _, v in items)
    def dec(v: float) -> int:
        lo, hi = 0, len(vals)
        while lo < hi:
            mid = (lo + hi) // 2
            if vals[mid] < v:
                lo = mid + 1
            else:
                hi = mid
        return min(9, int(10 * lo / max(1, len(vals))))
    by: dict[int, list[str]] = {}
    for s, v in items:
        by.setdefault(dec(v), []).append(s)
    used: set[str] = set()
    out: dict[str, float] = {}
    for s in sorted(held_weights):
        d = dec(sigma.get(s) or vals[len(vals) // 2])
        choices = [c for c in by.get(d, []) if c not in used] or [c for c, _ in items if c not in used]
        if not choices:
            break
        c = rng.choice(choices)
        used.add(c)
        out[c] = out.get(c, 0.0) + float(held_weights[s])
    return out


def weighted_return(weights: dict[str, float], rets: dict[str, Optional[float]]) -> tuple[Optional[float], float]:
    """Sum w_i r_i over names with a return; the share of weight priced."""
    tot_w = sum(abs(w) for w in weights.values())
    if tot_w <= 0:
        return 0.0, 1.0
    got = 0.0
    r = 0.0
    for s, w in weights.items():
        x = rets.get(s)
        if x is None or not math.isfinite(x):
            continue
        got += abs(w)
        r += w * x
    return (r if got > 0 else None), got / tot_w


def grade_row(role: str, day: str, *, account_ret: Optional[float], spy_ret: Optional[float],
              twin_ret: Optional[float], twin_priced_share: float, contract: dict,
              turnover_frac: float = 0.0) -> dict:
    cost = 2 * _cfg.FLEET_MANAGER_COST_BPS_PER_SIDE / 1e4 * turnover_frac
    def sub(a, b):
        return None if a is None or b is None else round(a - b, 6)
    return {"schema": "fleet_manager_grade/1", "role": role, "session": day,
            "contract_version": contract.get("version"), "policy_hash": contract.get("policy_hash"),
            "account_return": account_ret, "spy_return": spy_ret, "twin_return": twin_ret,
            "twin_priced_share": round(twin_priced_share, 3),
            "vs_spy": sub(account_ret, spy_ret), "vs_twin": sub(account_ret, twin_ret),
            "declared_cost_drag": round(cost, 6),
            "note": ("account return is the broker's equity change (paper fills, no commission); the "
                     "declared cost drag is what the contract charges on that day's turnover"),
            "written_utc": _now_iso()}


# ─────────────────────────────── the venue ──────────────────────────────────

Transport = Callable[[str, str, dict, Optional[bytes]], tuple[int, bytes]]


def _urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:   # noqa: S310 allowlisted hosts
            return fh.status, fh.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class Venue:
    """One paper account. The ONLY object here that reaches the network, and
    only through `transport` (tests pass a fake)."""

    def __init__(self, key_id: str, secret: str, *, transport: Optional[Transport] = None,
                 host: str = TRADING_HOST, data_host: str = DATA_HOST) -> None:
        if "paper-api" not in host:
            raise FleetRefusal(f"REFUSED: {host!r} is not a paper host")
        self._h = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret,
                   "Content-Type": "application/json"}
        self._t = transport or _urllib_transport
        self.host, self.data_host = host, data_host

    def call(self, method: str, path: str, *, params: Optional[dict] = None,
             body: Optional[dict] = None, data: bool = False) -> tuple[int, Any]:
        url = (self.data_host if data else self.host) + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        st, raw = self._t(method, url, self._h, json.dumps(body).encode() if body is not None else None)
        try:
            js = json.loads(raw or b"null")
        except ValueError:
            js = {"raw": (raw or b"")[:300].decode(errors="replace")}
        return st, js

    def get(self, path: str, **kw) -> Any:
        st, js = self.call("GET", path, **kw)
        if st != 200:
            raise FleetRefusal(f"GET {path} -> HTTP {st}: {str(js)[:200]}")
        return js

    def clock(self) -> dict:
        return self.get("/v2/clock")

    def account(self) -> dict:
        return self.get("/v2/account")

    def positions(self) -> list[dict]:
        return self.get("/v2/positions") or []

    def open_orders(self) -> list[dict]:
        return self.get("/v2/orders", params={"status": "open", "nested": "true", "limit": 500}) or []

    def orders_since(self, iso: str) -> list[dict]:
        return self.get("/v2/orders", params={"status": "all", "after": iso, "limit": 500,
                                              "direction": "asc"}) or []

    def fills(self, *, after: Optional[str] = None, max_pages: int = 10) -> list[dict]:
        """FILL activities, newest first."""
        out: list[dict] = []
        token = None
        for _ in range(max_pages):
            page = self.get("/v2/account/activities/FILL",
                            params={"after": after, "page_size": 100, "direction": "desc",
                                    "page_token": token}) or []
            out.extend(page)
            if len(page) < 100:
                break
            token = page[-1].get("id")
        return out

    def order_by_coid(self, coid: str) -> Optional[dict]:
        st, js = self.call("GET", "/v2/orders:by_client_order_id", params={"client_order_id": coid})
        if st == 404:
            return None
        if st != 200:
            raise FleetRefusal(f"order lookup {coid} -> HTTP {st}")
        return js

    def order(self, oid: str) -> dict:
        return self.get(f"/v2/orders/{oid}")

    def submit(self, body: dict) -> tuple[int, Any]:
        return self.call("POST", "/v2/orders", body=body)

    def cancel(self, oid: str) -> int:
        st, _ = self.call("DELETE", f"/v2/orders/{oid}")
        return st

    def quotes(self, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        js = self.get("/v2/stocks/quotes/latest", params={"symbols": ",".join(symbols), "feed": "iex"},
                      data=True)
        return js.get("quotes") or {}

    def last_trades(self, symbols: list[str]) -> dict[str, float]:
        if not symbols:
            return {}
        js = self.get("/v2/stocks/trades/latest", params={"symbols": ",".join(symbols), "feed": "iex"},
                      data=True)
        return {s: float(t["p"]) for s, t in (js.get("trades") or {}).items() if t and t.get("p")}

    def daily_closes(self, symbols: list[str], start: str) -> dict[str, list[tuple[str, float]]]:
        out: dict[str, list[tuple[str, float]]] = {}
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            token = None
            for _ in range(20):
                js = self.get("/v2/stocks/bars", params={"symbols": ",".join(chunk), "timeframe": "1Day",
                                                         "start": start, "feed": "iex", "limit": 10000,
                                                         "adjustment": "all", "page_token": token},
                              data=True)
                for s, bars in (js.get("bars") or {}).items():
                    out.setdefault(s, []).extend((b["t"][:10], float(b["c"])) for b in bars)
                token = js.get("next_page_token")
                if not token:
                    break
        return out

    def daily_bars(self, symbols: list[str], start: str) -> dict[str, list[dict]]:
        """{symbol: [{d, o, h, l, c}, ...]} (IEX, split/dividend adjusted)."""
        out: dict[str, list[dict]] = {}
        token = None
        for _ in range(20):
            js = self.get("/v2/stocks/bars", params={"symbols": ",".join(symbols), "timeframe": "1Day",
                                                     "start": start, "feed": "iex", "limit": 10000,
                                                     "adjustment": "all", "page_token": token}, data=True)
            for s, bars in (js.get("bars") or {}).items():
                out.setdefault(s, []).extend({"d": b["t"][:10], "o": float(b["o"]), "h": float(b["h"]),
                                              "l": float(b["l"]), "c": float(b["c"])} for b in bars)
            token = js.get("next_page_token")
            if not token:
                break
        return out

    def intraday_bars(self, symbols: list[str], start_iso: str, end_iso: str,
                      timeframe: str = "5Min") -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        token = None
        for _ in range(20):
            js = self.get("/v2/stocks/bars", params={"symbols": ",".join(symbols), "timeframe": timeframe,
                                                     "start": start_iso, "end": end_iso, "feed": "iex",
                                                     "limit": 10000, "adjustment": "all", "page_token": token},
                          data=True)
            for s_, bars in (js.get("bars") or {}).items():
                out.setdefault(s_, []).extend({"t": b["t"], "o": float(b["o"]), "h": float(b["h"]),
                                               "l": float(b["l"]), "c": float(b["c"])} for b in bars)
            token = js.get("next_page_token")
            if not token:
                break
        return out

    def portfolio_history(self) -> dict:
        return self.get("/v2/account/portfolio/history", params={"period": "1M", "timeframe": "1D"})


def wait_terminal(v: Venue, oid: str, *, timeout_s: float = 12.0, sleep: Callable = time.sleep) -> str:
    t0 = time.monotonic()
    st = ""
    while time.monotonic() - t0 < timeout_s:
        try:
            st = v.order(oid).get("status", "")
        except FleetRefusal:
            st = "unknown"
        if st in ("canceled", "filled", "expired", "rejected", "done_for_day"):
            return st
        sleep(0.5)
    return st or "timeout"


def submit_once(v: Venue, a: Action) -> dict:
    """POST an order only if no order with its client id exists at the venue.

    The id is deterministic (`client_order_id`), so a re-run of the same pass,
    a crash-and-restart, or a second copy of the task maps to the SAME id and is
    skipped here -- and the venue itself rejects a duplicate id as a second line
    of defence."""
    if a.refused:
        return {"outcome": f"refused: {a.refused}", "sent": False}
    if a.kind == "cancel" or a.order_type not in ("limit", "stop"):
        raise FleetRefusal("submit_once sends limit or stop orders only")
    existing = v.order_by_coid(a.coid)
    if existing and a.protective:
        # A protective stop whose earlier order under this id is DEAD (cancelled
        # to release shares, expired, rejected) must not be skipped: that skip
        # would leave the shares unprotected overnight. Walk to the first free
        # or live suffix; the walk is itself deterministic, so a re-run lands
        # on the same live order and still cannot double-submit.
        base = a.coid
        for i in range(1, 6):
            if str(existing.get("status")) not in DEAD_STATUSES:
                break
            a.coid = f"{base[:120]}-r{i}"
            existing = v.order_by_coid(a.coid)
            if not existing:
                break
    if existing:
        return {"outcome": f"ALREADY SUBMITTED ({existing.get('status')}): idempotent skip",
                "sent": False, "order_id": existing.get("id")}
    st, js = v.submit(a.body())
    if st in (200, 201) and isinstance(js, dict):
        return {"outcome": f"submitted {js.get('status')} id {js.get('id')}", "sent": True,
                "order_id": js.get("id")}
    return {"outcome": f"REJECTED http {st}: {str(js)[:160]}", "sent": False}


# ─────────────────────────────── market control ─────────────────────────────

def control_targets(contract: dict) -> dict[str, float]:
    """The market CONTROL's one target: the broad ETF at its declared weight."""
    sel = contract["selection"]
    return {str(sel["symbol"]): float(sel["weight"])}


# ─────────────────────────────── tight-stop counterfactual ──────────────────
# The owner's question (2026-09-29): four legacy stops sit within ~1 daily sigma
# of price, and stops that tight were measured on 2026-09-24 to be mostly noise-
# triggered and to lose against holding. The manager never loosens a stop on its
# own, so the stops stay; this records, per session and going FORWARD from the
# moment of registration, what the tight stop, a 3-sigma stop and plain holding
# would each have done -- evidence for the owner's decision, not a decision.

def cf_stop_path(p0: float, qty: float, stop: Optional[float], bars_after: list[dict]) -> dict:
    """Dollar P&L from p0 of `qty` shares under a stop at `stop` (None = hold),
    over sessions strictly AFTER registration. A gap through the stop fills at
    the open (min(open, stop)): gaps can be worse than the stop price."""
    if not bars_after:
        return {"pnl_usd": 0.0, "triggered": None, "exit_price": None, "sessions": 0}
    for b in bars_after:
        if stop is not None and b["l"] <= stop:
            px = min(b["o"], stop)
            return {"pnl_usd": round(qty * (px - p0), 2), "triggered": b["d"], "exit_price": round(px, 4),
                    "sessions": len(bars_after)}
    last = bars_after[-1]["c"]
    return {"pnl_usd": round(qty * (last - p0), 2), "triggered": None, "exit_price": None,
            "mark": round(last, 4), "sessions": len(bars_after)}


def partial_bar(intraday: list[dict], day: str) -> Optional[dict]:
    """The part of a session AFTER registration, from intraday bars, as one bar."""
    if not intraday:
        return None
    xs = sorted(intraday, key=lambda b: b["t"])
    return {"d": day, "o": xs[0]["o"], "h": max(b["h"] for b in xs), "l": min(b["l"] for b in xs),
            "c": xs[-1]["c"], "partial_from": xs[0]["t"]}


def cf_stop_row(reg: dict, bars: list[dict], asof: str, reg_day_bar: Optional[dict] = None,
                broker_tight: Optional[dict] = None) -> dict:
    """One dated counterfactual row for one registered position. `reg_day_bar` is
    the rest of the registration session after the registration time (intraday),
    so a tight stop hit that same evening is counted."""
    after = sorted((b for b in bars if reg["registered_session"] < b["d"] <= asof), key=lambda b: b["d"])
    if reg_day_bar:
        after = [reg_day_bar] + after
    q, p0 = float(reg["qty"]), float(reg["p0"])
    tight = cf_stop_path(p0, q, reg["tight_stop"], after)
    wide = cf_stop_path(p0, q, reg["wide_stop"], after)
    hold = cf_stop_path(p0, q, None, after)
    return {"schema": "fleet_stop_counterfactual/1", "role": reg["role"], "symbol": reg["symbol"],
            "asof_session": asof, "registered_session": reg["registered_session"], "p0": p0, "qty": q,
            "tight_stop": reg["tight_stop"], "tight_stop_sigma": reg.get("tight_stop_sigma"),
            "wide_stop": reg["wide_stop"], "wide_stop_sigma": reg.get("wide_stop_sigma"),
            "tight": tight, "wide_3sigma": wide, "hold": hold, "broker_tight_stop": broker_tight,
            "tight_minus_hold_usd": round(tight["pnl_usd"] - hold["pnl_usd"], 2),
            "wide_minus_hold_usd": round(wide["pnl_usd"] - hold["pnl_usd"], 2),
            "note": ("forward from registration only; a gap through a stop fills at the open; the tight "
                     "stop is the one actually resting at the broker, so its path is also the account's"),
            "written_utc": _now_iso()}


# ─────────────────────────────── source scoreboard (learning) ───────────────

def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def luck_table(k: int, n_sessions: int, daily_sd: Optional[float], best_cum_excess: Optional[float]) -> dict:
    """How often the BEST of k accounts with NO skill looks this good.

    Under the null every account's daily excess is iid N(0, sd^2), so a
    cumulative excess over n sessions is ~N(0, sd^2 n) and
    P(max of k >= x) = 1 - Phi(x / (sd sqrt n))^k."""
    out: dict[str, Any] = {
        "k_accounts": k, "n_sessions": n_sessions,
        "p_best_of_k_beats_benchmark_by_chance": round(1 - 0.5 ** k, 4) if k else None,
        "p_best_of_k_shows_t_ge_2_by_chance": round(1 - _phi(2.0) ** k, 4) if k else None}
    if daily_sd and daily_sd > 0 and n_sessions > 0 and best_cum_excess is not None and k:
        z = best_cum_excess / (daily_sd * math.sqrt(n_sessions))
        out["best_cum_excess"] = round(best_cum_excess, 6)
        out["z_of_best"] = round(z, 3)
        out["p_best_of_k_at_least_this_by_chance"] = round(1 - _phi(z) ** k, 4)
    return out


def source_trust(block_means: list[float], *, prior_sd: Optional[float] = None,
                 block_sd: Optional[float] = None) -> dict:
    """Normal-normal posterior of a source's mean daily excess, prior N(0, prior_sd^2),
    from COMPLETED blocks only (nn_lab/loop.py `posterior`, forward-only)."""
    ps = _cfg.FLEET_TRUST_PRIOR_SD if prior_sd is None else prior_sd
    bs = _cfg.FLEET_TRUST_BLOCK_SD if block_sd is None else block_sd
    k = (bs / ps) ** 2
    n = float(len(block_means))
    m = sum(block_means) / n if n else 0.0
    trust = n * m / (n + k)
    return {"trust_daily_excess": round(trust, 7), "n_blocks": int(n),
            "forward_mean_daily_excess": round(m, 7) if n else None,
            "shrink": round(n / (n + k), 4), "prior_strength_blocks": round(k, 2),
            "weight": round(max(0.0, trust) / _cfg.FLEET_TRUST_FULL, 4)}


def _cum(xs: list[float]) -> float:
    v = 1.0
    for x in xs:
        v *= 1.0 + x
    return v - 1.0


def source_scoreboard(grades: list[dict], alpha_of: dict[str, str], *,
                      control_role: str = "hack5", block_sessions: Optional[int] = None) -> dict:
    """Per account (= per alpha source): cumulative return, vs SPY, vs its twin,
    vs the CONTROL account on the same sessions; which source is ahead; the luck
    table beside it; and a forward-only trust from COMPLETED blocks.

    `alpha_of`: policy_hash -> alpha source. A grade row's source is the
    contract it was graded under, so a v1 -> v2 switch starts a new source.
    The control's own excess is measured vs SPY (it is the benchmark for the rest)."""
    bsz = block_sessions or _cfg.FLEET_TRUST_BLOCK_SESSIONS
    rows = [g for g in grades if g.get("account_return") is not None and g.get("session")]
    seen: set = set()
    uniq = []
    for g in sorted(rows, key=lambda r: (r["session"], r.get("written_utc") or "")):
        key = (g["role"], g["session"])
        if key not in seen:
            seen.add(key)
            uniq.append(g)
    ctrl = {g["session"]: float(g["account_return"]) for g in uniq
            if g["role"] == control_role and g.get("contract_version") == "v2"}
    by: dict[tuple[str, str], list[dict]] = {}
    for g in uniq:
        by.setdefault((g["role"], g.get("policy_hash") or "?"), []).append(g)
    table = []
    for (role, ph), gs in sorted(by.items()):
        gs = sorted(gs, key=lambda r: r["session"])
        acc = [float(g["account_return"]) for g in gs]
        spy = [float(g["spy_return"]) for g in gs if g.get("spy_return") is not None]
        tw = [float(g["vs_twin"]) for g in gs if g.get("vs_twin") is not None]
        exc_s = [float(g["vs_spy"]) for g in gs if g.get("vs_spy") is not None]
        exc_c = [float(g["account_return"]) - ctrl[g["session"]] for g in gs
                 if role != control_role and g["session"] in ctrl]
        exc = exc_c if (role != control_role and exc_c) else exc_s
        blocks = [sum(exc[i:i + bsz]) / bsz for i in range(0, len(exc) - bsz + 1, bsz)]
        mu = sum(exc) / len(exc) if exc else 0.0
        sd = math.sqrt(sum((x - mu) ** 2 for x in exc) / (len(exc) - 1)) if len(exc) > 1 else None
        table.append({"role": role, "policy_hash": ph, "alpha_source": alpha_of.get(ph, "?"),
                      "contract_version": gs[-1].get("contract_version"),
                      "n_sessions": len(gs), "first": gs[0]["session"], "last": gs[-1]["session"],
                      "cum_return": round(_cum(acc), 6), "cum_spy": round(_cum(spy), 6) if spy else None,
                      "sum_vs_spy": round(sum(exc_s), 6), "sum_vs_twin": round(sum(tw), 6) if tw else None,
                      "sum_vs_control": round(sum(exc_c), 6) if exc_c else None,
                      "excess_basis": ("vs control account" if (role != control_role and exc_c) else "vs SPY"),
                      "daily_excess_sd": round(sd, 6) if sd else None,
                      "completed_blocks": len(blocks), "trust": source_trust(blocks)})
    ranked = [t for t in table if t["role"] != control_role]

    def key(t: dict) -> float:
        return t["sum_vs_control"] if t["sum_vs_control"] is not None else t["sum_vs_spy"]
    ranked.sort(key=lambda t: -key(t))
    k = len({t["role"] for t in table})
    sds = [t["daily_excess_sd"] for t in table if t["daily_excess_sd"]]
    n = max([t["n_sessions"] for t in ranked] or [0])
    best = ranked[0] if ranked else None
    luck = luck_table(k, n, (sum(sds) / len(sds)) if sds else None, key(best) if best else None)
    ahead = None
    if best:
        pk = table[0]["trust"]["prior_strength_blocks"]
        ahead = (f"{best['role']} ({best['alpha_source'][:70]}) is ahead: {key(best) * 100:+.2f}% summed daily "
                 f"excess {best['excess_basis']} over {best['n_sessions']} session(s). By chance alone the best of "
                 f"{k} beats its benchmark with p = {luck['p_best_of_k_beats_benchmark_by_chance']}"
                 + (f" and is at least this far ahead with p = {luck['p_best_of_k_at_least_this_by_chance']}"
                    if luck.get("p_best_of_k_at_least_this_by_chance") is not None else "")
                 + f". Weights move only on COMPLETED blocks of {bsz} sessions (shrink n/(n+{pk})).")
    return {"schema": "fleet_source_scoreboard/1", "control_role": control_role,
            "n_grade_rows": len(uniq), "table": table, "ranked_ex_control": [t["role"] for t in ranked],
            "ahead": ahead, "luck": luck}
