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
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from contextlib import contextmanager
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


@contextmanager
def role_writer_lock(role: str, base: Optional[Path] = None):
    """One manager/protection writer per account; OS releases on process death."""
    if not re.fullmatch(r"hack[1-6]", role):
        raise FleetRefusal("invalid fleet role for writer lock")
    path = root(base) / "locks" / f"{role}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fh:
        if path.stat().st_size == 0:
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise FleetRefusal(f"{role}: another fleet writer owns the account") from exc
        try:
            yield
        finally:
            fh.seek(0)
            if os.name == "nt":
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


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


def owned_order_types(role: str, base: Optional[Path] = None) -> dict[str, str]:
    """Types supported by both an owned LIVE decision and an accepted order outcome.

    A decision alone is a plan, not an order.  The outcome must carry the same
    run/client id and an actual broker order id.  Conflicting evidence is left
    unknown rather than guessing a cooldown result.
    """
    decisions: dict[tuple[str, str], str] = {}
    outcomes: dict[tuple[str, str], str] = {}
    conflicts: set[tuple[str, str]] = set()
    for row in read_jsonl(decisions_path(base)):
        if row.get("role") != role or not row.get("run_id") or not row.get("coid"):
            continue
        key = (row["run_id"], row["coid"])
        if row.get("row") == "decision" and row.get("mode") == "LIVE" and not row.get("refused"):
            typ = row.get("type")
            if typ not in (*STOP_TYPES, "limit"):
                conflicts.add(key)
                continue
            if key in decisions and decisions[key] != typ:
                conflicts.add(key)
            decisions[key] = typ
        elif row.get("row") == "outcome" and row.get("order_id"):
            outcome = str(row.get("outcome") or "")
            if not outcome.startswith("submitted "):
                continue
            oid = str(row["order_id"])
            if key in outcomes and outcomes[key] != oid:
                conflicts.add(key)
            outcomes[key] = oid
    by_id: dict[str, str] = {}
    ambiguous: set[str] = set()
    for key, typ in decisions.items():
        if key in conflicts or key not in outcomes:
            continue
        oid = outcomes[key]
        if oid in by_id and by_id[oid] != typ:
            ambiguous.add(oid)
        by_id[oid] = typ
    return {oid: typ for oid, typ in by_id.items() if oid not in ambiguous}


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
                                   coid=client_order_id(role, day, "stoprenew", sym, h, f"{q}"),
                                   inputs={"replaces_stop": old}))
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


# ─────────────────────────────── named gates (C26) ──────────────────────────
#
# THE DECISION STORY OF ONE ORDER: proposal -> ordered named gates -> outcome
# (2026-10-07, borrowed from the Alpaca hackathon winners: Killswitch's fifteen
# deterministic gates that only shrink or kill, Autobelay's logged gate layer).
# `check_limits` above is kept verbatim for its callers and tests; the runner
# now walks GATES instead, and every verdict lands on the decision row.
#
# THE INVARIANTS, pinned by `test_fleet_gates.py`:
#   1. A gate can never INCREASE a proposed size. A SHRINK whose `to` is not
#      below the current quantity is a GATE DEFECT and kills the order.
#   2. A protective order (stop, cancel) and a declared `exit` are blocked by
#      no RISK gate except `order_count` -- the frozen per-run circuit breaker
#      counts and caps every non-cancel order, as it did before C26.
#   3. GATE_POLICY_VERSION "c26-p2-frozen-terms" (review 2026-10-07 F2): cash,
#      gross_cap, name_cap and turnover_budget REFUSE (never shrink) exactly as
#      `check_limits` / `apply_turnover_budget` did when the contracts were
#      frozen; the one behaviour change kept is `long_only` cutting an
#      oversized sell to the shares held (the old refusal left the name held).

GATE_PASS, GATE_SHRINK, GATE_KILL = "PASS", "SHRINK", "KILL"
GATE_LEASE, GATE_SHAPE, GATE_RISK = "lease", "shape", "risk"
UNKNOWN_SECTOR = "UNKNOWN"

#: `cooldown` and `sector_concentration` (C26, 2026-10-07) are the two gates
#: that can change a LIVE book's executed positions tonight (hack2's Technology
#: buys would be KILLED -- Technology is already 67% of hack2 -- before the
#: owner has decided whether that gate should bind; see
#: `docs/research_notes/2026-10-07/fleet_gates_and_eod_audit_2026-10-07.md`).
#: `config.FLEET_NEW_GATES_MODE` ("shadow" | "enforce") decides whether they
#: bind. In "shadow" (the default) each still evaluates against the real
#: order and ctx, but `run_gates` overrides its verdict to PASS before it can
#: shrink or kill anything, and the real verdict/reason it computed is kept on
#: the trace row as `shadow_verdict` (`SHADOW_WOULD_KILL: ...` or
#: `SHADOW_WOULD_SHRINK(to=<q>): ...`). In "enforce" they bind like every
#: other gate and `shadow_verdict` is never set.
NEW_GATES: frozenset = frozenset({"cooldown", "sector_concentration"})
SHADOW_MODE, ENFORCE_MODE = "shadow", "enforce"

#: Every semantic choice the gates make relative to the pre-C26 hard gate,
#: hashed into `gates_config()` and printed on every run receipt.
#: c27 (2026-10-07): the c26-p2 frozen terms unchanged, plus the wash-trade
#: SEQUENCE for top-ups -- an order-sequencing correctness fix, not a gate.
GATE_POLICY_VERSION = "c27-wash-trade-sequence"
GATE_POLICY_CHOICES = {
    "cash": "REFUSE (restored: pre-C26 check_limits)",
    "gross_cap": "REFUSE (restored: pre-C26 check_limits)",
    "name_cap": "REFUSE (restored: pre-C26 check_limits)",
    "turnover_budget": ("REFUSE, and spent in plan order as soon as an order passes this gate (restored: "
                        "pre-C26 apply_turnover_budget). Exempt: protective orders, cancels and kind 'exit' only "
                        "-- a rebalance sell, full or partial, spends the budget: the v2 contract text says "
                        "'enter ... inside the daily turnover budget' and grants exits no exemption"),
    "order_count": "every non-cancel order counts and is refused beyond the cap, exits included (restored)",
    "long_only": "SHRINK an oversized sell to the long quantity (C26 bug fix; was a refusal)",
    "stop_never_loosened": "raise a replacing stop to the stop it replaces (assertion; planners already max())",
    "re_protect": "the stop for the shares left after a sell is sized AFTER the gates from the executed quantity",
    "wash_trade_sequence": ("C27, NOT a gate and NOT shadowed (binds from the first pass): a top-up of a name "
                            "with a resting sell stop is sent as cancel stop -> buy -> wait terminal -> ONE stop "
                            "for the shares held, at max(prior stop, contract level); rollback re-places the "
                            "original stop on any failure; a sequence that cannot be made safe is "
                            "REFUSED_WASH_TRADE_RULE on the trace, never silently skipped"),
}


@dataclass
class GateCtx:
    """What the gates read, and the running totals they commit to after a pass.
    `stopped_out` None means the stop history could not be read: the cooldown
    gate then KILLS buys (cannot determine is a refusal, never a pass)."""
    equity: float
    cash: float
    held: dict
    mv: dict
    gross: float
    contract: dict
    today: date
    stop_file_present: bool = False
    credential_ok: bool = True
    reconciliation_ok: bool = True
    reconciliation_status: str = "OK"
    market_ok: bool = True
    turnover_left: float = float("inf")
    orders_used: int = 0
    stopped_out: Optional[dict] = field(default_factory=dict)   # symbol -> ISO date of the stop fill
    sector_of: dict = field(default_factory=dict)
    sector_mv: dict = field(default_factory=dict)
    cooldown_sessions: Optional[int] = None
    sector_max_frac: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.sector_mv:
            for s, v in self.mv.items():
                k = self.sector_of.get(s) or UNKNOWN_SECTOR
                self.sector_mv[k] = self.sector_mv.get(k, 0.0) + abs(float(v))
        if self.cooldown_sessions is None:
            self.cooldown_sessions = int(_cfg.FLEET_GATE_COOLDOWN_SESSIONS)
        if self.sector_max_frac is None:
            self.sector_max_frac = float(_cfg.FLEET_GATE_SECTOR_MAX_FRAC)


def is_exit(a: Action, held: dict) -> bool:
    """An order that only removes exposure: a protective stop, a cancel, a
    declared exit, or a sell of the WHOLE long position. A trim (a sell of part
    of it) reduces risk but is a rebalance, and pays the turnover budget."""
    if a.kind in ("exit", "cancel", "stop_new", "stop_renew") or a.protective:
        return True
    return a.side == "sell" and a.qty > 0 and a.qty + 1e-9 >= max(0.0, float(held.get(a.symbol, 0.0)))


def _px(a: Action) -> float:
    return float(a.limit_price or a.stop_price or a.price_ref or 0.0)


def _shrink(a: Action, cap_usd: float, why: str, ctx: GateCtx) -> tuple[str, Optional[int], str]:
    """SHRINK to the largest whole quantity whose notional fits `cap_usd`, or
    KILL when nothing (or less than the minimum order) fits."""
    px = _px(a)
    if px <= 0:
        return GATE_KILL, None, f"{why}: no price to size against"
    q = int(math.floor(max(0.0, cap_usd) / px + 1e-9))
    if q >= a.qty:
        return GATE_PASS, None, why + ": fits"
    mn = float(ctx.contract["caps"].get("min_order_usd") or 0.0)
    if q <= 0 or q * px < mn:
        return GATE_KILL, None, (f"{why}: room ${max(0.0, cap_usd):,.0f} leaves less than the "
                                 f"${mn:,.0f} minimum order")
    return GATE_SHRINK, q, f"{why}: {a.qty} -> {q} (room ${cap_usd:,.0f})"


# -- lease class: may block anything, exits included --

def g_kill_switch(a: Action, ctx: GateCtx):
    if ctx.stop_file_present:
        return GATE_KILL, None, "fleet_manager/STOP is present: the owner's kill switch"
    return GATE_PASS, None, "no STOP file"


def g_credential(a: Action, ctx: GateCtx):
    if not ctx.credential_ok:
        return GATE_KILL, None, "the account's credential was not accepted"
    return GATE_PASS, None, "account read with its own key"


def g_reconciliation(a: Action, ctx: GateCtx):
    if not ctx.reconciliation_ok:
        return GATE_KILL, None, (f"RECONCILIATION {ctx.reconciliation_status}: every order on this account "
                                 "refused (the single-writer lease is not proven)")
    return GATE_PASS, None, "broker = record + fills, no foreign executor"


def g_venue_window(a: Action, ctx: GateCtx, mode: str = "DRY"):
    if mode == "LIVE" and not ctx.market_ok:
        return GATE_KILL, None, "venue closed or within minutes of the close: orders only while open"
    return GATE_PASS, None, "venue open" if mode == "LIVE" else "dry: nothing is sent"


# -- shape class: a malformed order is not an order --

def g_instrument(a: Action, ctx: GateCtx):
    if a.kind == "cancel":
        return GATE_PASS, None, "cancel"
    if not _EQUITY_TICKER.match(a.symbol):
        return GATE_KILL, None, (f"{a.symbol} is not a plain equity ticker: no option or other order "
                                 "is ever built here")
    return GATE_PASS, None, "plain equity"


def g_order_shape(a: Action, ctx: GateCtx):
    if a.kind == "cancel":
        return GATE_PASS, None, "cancel"
    if a.qty <= 0:
        return GATE_KILL, None, "quantity is not positive"
    if a.order_type not in ("limit", "stop"):
        return GATE_KILL, None, f"order type {a.order_type!r} refused: limit or stop only, never market"
    if a.side not in ("buy", "sell"):
        return GATE_KILL, None, f"side {a.side!r} refused"
    if a.side == "buy" and (a.limit_price is None or a.limit_price <= 0):
        return GATE_KILL, None, "a buy needs a limit price near the quote"
    if a.order_type == "stop" and not a.protective:
        return GATE_KILL, None, "a stop order must be protective"
    return GATE_PASS, None, f"{a.order_type} {a.side}"


def g_long_only(a: Action, ctx: GateCtx):
    if a.side != "sell":
        return GATE_PASS, None, "not a sell"
    long_q = int(math.floor(max(0.0, float(ctx.held.get(a.symbol, 0.0))) + 1e-9))
    if a.qty <= long_q:
        return GATE_PASS, None, f"sell {a.qty} <= long {long_q}"
    if long_q <= 0:
        return GATE_KILL, None, f"sell {a.qty} with nothing long held: would open a short (shorting refused)"
    return GATE_SHRINK, long_q, f"sell {a.qty} > long {long_q}: shrunk to the long quantity (no short)"


def g_stop_never_loosened(a: Action, ctx: GateCtx):
    if a.order_type != "stop":
        return GATE_PASS, None, "not a stop"
    old = (a.inputs or {}).get("replaces_stop")
    if old is None or a.stop_price is None:
        return GATE_PASS, None, "replaces no resting stop"
    if float(a.stop_price) + 1e-9 >= float(old):
        return GATE_PASS, None, f"stop {a.stop_price} >= the stop it replaces {old}"
    a.inputs["stop_before_gate"] = a.stop_price
    a.stop_price = float(old)
    return GATE_SHRINK, a.qty, (f"stop raised to the stop it replaces ({old}): a replaced stop is never "
                                "loosened (the loss distance shrank; quantity unchanged)")


# -- risk class: PASS for every exit; may only shrink or kill an entry or a trim --

def g_min_order(a: Action, ctx: GateCtx):
    if is_exit(a, ctx.held):
        return GATE_PASS, None, "exit: never blocked by a risk gate"
    mn = float(ctx.contract["caps"].get("min_order_usd") or 0.0)
    if a.notional < mn:
        return GATE_KILL, None, f"${a.notional:,.0f} < min order ${mn:,.0f}"
    return GATE_PASS, None, f"${a.notional:,.0f} >= ${mn:,.0f}"


def g_cooldown(a: Action, ctx: GateCtx):
    if a.side != "buy" or is_exit(a, ctx.held):
        return GATE_PASS, None, "not an entry"
    n = int(ctx.cooldown_sessions or 0)
    if ctx.stopped_out is None:
        return GATE_KILL, None, "stop history unreadable: cannot show the name was not stopped out recently"
    d0 = ctx.stopped_out.get(a.symbol)
    if not d0:
        return GATE_PASS, None, f"no stop fill on {a.symbol} in the lookback"
    k = sessions_between(date.fromisoformat(str(d0)[:10]), ctx.today)
    if k < n:
        return GATE_KILL, None, f"{a.symbol} was stopped out {d0} ({k} session(s) ago) < cooldown {n}"
    return GATE_PASS, None, f"{a.symbol} stopped out {d0}, {k} session(s) ago >= cooldown {n}"


def g_turnover_budget(a: Action, ctx: GateCtx):
    """Frozen terms (pre-C26 `apply_turnover_budget`): every non-protective
    order except a cancel or a declared `exit` spends the session's budget in
    plan order, the moment it passes HERE (so a later refusal still spent it,
    exactly as before); beyond the budget it is REFUSED, never shrunk."""
    if a.kind in ("cancel", "exit") or a.protective:
        return GATE_PASS, None, "protective, cancel or declared exit: spends no turnover budget"
    if a.notional > ctx.turnover_left + 1e-6:
        return GATE_KILL, None, (f"daily turnover budget: ${a.notional:,.0f} would exceed "
                                 f"${max(0.0, ctx.turnover_left):,.0f} left")
    ctx.turnover_left -= a.notional
    return GATE_PASS, None, f"${a.notional:,.0f} spent; ${ctx.turnover_left:,.0f} left"


def g_cash(a: Action, ctx: GateCtx):
    if a.side != "buy":
        return GATE_PASS, None, "not a buy"
    n = a.qty * float(a.limit_price or 0)
    if ctx.cash - n < -1e-6:
        return GATE_KILL, None, f"cash ${ctx.cash:,.0f} - ${n:,.0f} < 0: would borrow (no leverage)"
    return GATE_PASS, None, f"${n:,.0f} within cash ${ctx.cash:,.0f}"


def g_gross_cap(a: Action, ctx: GateCtx):
    if a.side != "buy":
        return GATE_PASS, None, "not a buy"
    cap = float(ctx.contract["caps"]["max_gross_frac"])
    n = a.qty * float(a.limit_price or 0)
    if ctx.gross + n > cap * ctx.equity + 1e-6:
        return GATE_KILL, None, f"gross ${ctx.gross + n:,.0f} > {cap:.0%} of equity ${ctx.equity:,.0f}"
    return GATE_PASS, None, f"gross ${ctx.gross + n:,.0f} <= {cap:.0%} of equity"


def g_name_cap(a: Action, ctx: GateCtx):
    if a.side != "buy":
        return GATE_PASS, None, "not a buy"
    cap = name_cap(ctx.contract["caps"], a.symbol)
    n = a.qty * float(a.limit_price or 0)
    after = ctx.mv.get(a.symbol, 0.0) + n
    if after > cap * ctx.equity * 1.005:
        return GATE_KILL, None, f"{a.symbol} would be ${after:,.0f} > {cap:.0%} of equity"
    return GATE_PASS, None, f"{a.symbol} ${after:,.0f} <= {cap:.0%} of equity"


def sector_room_usd(sector_mv: float, gross: float, equity: float, x: float) -> float:
    """Largest added notional n with (sector + n) <= x * max(gross + n, equity).
    The denominator is the account's gross, floored at equity so an account
    that is mostly cash can still buy its first names."""
    n1 = x * equity - sector_mv
    if gross + n1 <= equity + 1e-9:
        return n1
    return (x * gross - sector_mv) / (1.0 - x) if x < 1.0 else float("inf")


def g_sector_concentration(a: Action, ctx: GateCtx):
    if a.side != "buy":
        return GATE_PASS, None, "not a buy"
    ov = ctx.contract["caps"].get("name_cap_overrides") or {}
    if a.symbol in ov:
        return GATE_PASS, None, (f"{a.symbol} carries the contract's own declared cap {float(ov[a.symbol]):.0%} "
                                 "(the broad-market control)")
    sec = ctx.sector_of.get(a.symbol) or UNKNOWN_SECTOR
    x = float(ctx.sector_max_frac)
    room = sector_room_usd(ctx.sector_mv.get(sec, 0.0), ctx.gross, ctx.equity, x)
    return _shrink(a, room, f"sector {sec} <= {x:.0%} of gross", ctx)


def g_order_count(a: Action, ctx: GateCtx):
    """Frozen terms: the per-run circuit breaker counts every non-cancel order,
    exits and stops included, and refuses beyond the cap (pre-C26 behaviour)."""
    if a.kind == "cancel":
        return GATE_PASS, None, "cancel: not counted"
    cap = int(ctx.contract["caps"]["max_orders_per_run"])
    if ctx.orders_used >= cap:
        return GATE_KILL, None, f"per-run order cap {cap}"
    return GATE_PASS, None, f"order {ctx.orders_used + 1} of {cap}"


#: THE ORDER IS THE CONTRACT: lease, then shape, then risk. The tuple is pinned
#: against `config.FLEET_GATE_ORDER` by a test, so the doc and the code cannot drift.
GATES: tuple = (
    ("kill_switch", GATE_LEASE, g_kill_switch),
    ("credential", GATE_LEASE, g_credential),
    ("reconciliation", GATE_LEASE, g_reconciliation),
    ("venue_window", GATE_LEASE, g_venue_window),
    ("instrument", GATE_SHAPE, g_instrument),
    ("order_shape", GATE_SHAPE, g_order_shape),
    ("long_only", GATE_SHAPE, g_long_only),
    ("stop_never_loosened", GATE_SHAPE, g_stop_never_loosened),
    ("min_order", GATE_RISK, g_min_order),
    ("cooldown", GATE_RISK, g_cooldown),
    ("turnover_budget", GATE_RISK, g_turnover_budget),
    ("cash", GATE_RISK, g_cash),
    ("gross_cap", GATE_RISK, g_gross_cap),
    ("name_cap", GATE_RISK, g_name_cap),
    ("sector_concentration", GATE_RISK, g_sector_concentration),
    ("order_count", GATE_RISK, g_order_count),
)


def gates_config() -> dict:
    """The operator overlay the gates read, hashed onto every receipt: gates are
    NOT part of a frozen contract (they may only shrink), so their version
    travels beside the contract hash instead of inside it."""
    body = {"order": [g[0] for g in GATES], "classes": {g[0]: g[1] for g in GATES},
            "cooldown_sessions": int(_cfg.FLEET_GATE_COOLDOWN_SESSIONS),
            "sector_max_frac": float(_cfg.FLEET_GATE_SECTOR_MAX_FRAC),
            "sector_denominator": "max(gross after the order, equity)",
            "unknown_sector": f"one bucket named {UNKNOWN_SECTOR}",
            "name_cap_tolerance": 1.005,
            "new_gates": sorted(NEW_GATES), "new_gates_mode": str(_cfg.FLEET_NEW_GATES_MODE),
            "gate_policy_version": GATE_POLICY_VERSION, "gate_policy_choices": GATE_POLICY_CHOICES,
            "sector_map_max_age_days": int(_cfg.FLEET_GATE_SECTOR_MAP_MAX_AGE_DAYS),
            "sector_max_unknown_frac": float(_cfg.FLEET_GATE_SECTOR_MAX_UNKNOWN_FRAC)}
    body["hash"] = _sha(json.dumps(body, sort_keys=True))
    return body


def story_id(role: str, day: str, pass_: str, coid: str) -> str:
    """The fleet's own Decision Story id (PC-PAPER's `decision_story` ids are
    not reused here: a fleet order is not a PC-PAPER decision)."""
    return "fs-" + _sha(role, day, pass_, coid)


def run_gates(a: Action, ctx: GateCtx, *, mode: str = "DRY", gates: Optional[tuple] = None,
             new_gates_mode: Optional[str] = None) -> list[dict]:
    """Walk the gates in order. Mutates `a.qty` (shrink only), `a.refused`
    (on a KILL) and, after a full pass, the running totals in `ctx`. Returns
    the trace: one row per gate evaluated, ending at the first KILL.

    `new_gates_mode` ("shadow" | "enforce", default `config.FLEET_NEW_GATES_MODE`)
    governs `NEW_GATES` only: in "shadow" each still runs against the real
    order, but a verdict that would KILL or SHRINK is overridden to PASS (the
    order is untouched) and the real verdict is kept on the row as
    `shadow_verdict`; every other gate enforces regardless."""
    gates = GATES if gates is None else gates
    ngm_raw = new_gates_mode if new_gates_mode is not None else _cfg.FLEET_NEW_GATES_MODE
    default_mode = _cfg.FLEET_NEW_GATES_MODE if isinstance(ngm_raw, dict) else ngm_raw

    def mode_of(gate: str) -> str:
        return ngm_raw.get(gate, default_mode) if isinstance(ngm_raw, dict) else ngm_raw
    trace: list[dict] = []
    if a.refused:
        trace.append({"gate": "planner", "class": "plan", "verdict": GATE_KILL, "reason": a.refused,
                      "qty_in": a.qty, "qty_out": 0})
        return trace
    for name, cls, fn in gates:
        q_in = a.qty
        try:
            verdict, to, why = fn(a, ctx, mode) if fn is g_venue_window else fn(a, ctx)
        except Exception as exc:                                  # noqa: BLE001 -- a broken gate refuses
            verdict, to, why = GATE_KILL, None, f"GATE_ERROR {type(exc).__name__}: {exc}"[:200]
        row = {"gate": name, "class": cls, "verdict": verdict, "reason": why, "qty_in": q_in}
        if name in NEW_GATES and mode_of(name) != ENFORCE_MODE and verdict in (GATE_KILL, GATE_SHRINK):
            shadow = (f"SHADOW_WOULD_KILL: {why}" if verdict == GATE_KILL
                      else f"SHADOW_WOULD_SHRINK(to={to}): {why}")
            row.update(verdict=GATE_PASS, reason=f"{why} [shadow -- would have bound]",
                      shadow_verdict=shadow)
            trace.append(dict(row, qty_out=a.qty))
            continue
        if verdict == GATE_SHRINK:
            if to is None or int(to) > q_in or (int(to) == q_in and a.order_type != "stop"):
                verdict, why = GATE_KILL, (f"GATE_DEFECT: {name} returned SHRINK to {to} from {q_in}; "
                                           "a gate may never enlarge (or fake-shrink) an order")
                row.update(verdict=verdict, reason=why)
            else:
                a.qty = int(to)
        elif verdict not in (GATE_PASS, GATE_KILL):
            verdict, why = GATE_KILL, f"GATE_DEFECT: unknown verdict {verdict!r}"
            row.update(verdict=verdict, reason=why)
        if verdict == GATE_KILL:
            a.refused = f"{name}: {why}"
            row["qty_out"] = 0
            trace.append(row)
            return trace
        row["qty_out"] = a.qty
        trace.append(row)
    # every gate passed: commit the order to the running totals (the turnover
    # budget was already spent at its own gate, as the pre-C26 code spent it)
    if a.kind != "cancel":
        ctx.orders_used += 1
    if a.side == "buy":
        n = a.qty * float(a.limit_price or 0)
        ctx.cash -= n
        ctx.mv[a.symbol] = ctx.mv.get(a.symbol, 0.0) + n
        ctx.gross += n
        sec = ctx.sector_of.get(a.symbol) or UNKNOWN_SECTOR
        ctx.sector_mv[sec] = ctx.sector_mv.get(sec, 0.0) + n
    return trace


def gate_summary(traces: Iterable[list[dict]]) -> dict:
    """{gate: {PASS: n, SHRINK: n, KILL: n, SHADOW_WOULD_KILL: n, SHADOW_WOULD_SHRINK: n}}
    over a run. A shadowed verdict is counted under its SHADOW_ key, never as PASS
    (review 2026-10-07 F12: in shadow the cells used to read PASS forever)."""
    out: dict[str, dict[str, int]] = {}
    for tr in traces:
        for r in tr:
            d = out.setdefault(r["gate"], {})
            sv = str(r.get("shadow_verdict") or "")
            k = ("SHADOW_WOULD_KILL" if sv.startswith("SHADOW_WOULD_KILL") else
                 "SHADOW_WOULD_SHRINK" if sv.startswith("SHADOW_WOULD_SHRINK") else r["verdict"])
            d[k] = d.get(k, 0) + 1
    return out


#: Gates whose SHRINK replaced what the pre-C26 hard gate did as a REFUSAL.
_WAS_REFUSAL = frozenset({"long_only"})


def c26_delta(traces: Iterable[list[dict]]) -> dict:
    """Did C26 change anything on this account tonight? The one line the owner reads."""
    n_sk = n_ss = n_shr = n_r2s = 0
    for tr in traces:
        for r in tr:
            sv = str(r.get("shadow_verdict") or "")
            if sv.startswith("SHADOW_WOULD_KILL"):
                n_sk += 1
            elif sv.startswith("SHADOW_WOULD_SHRINK"):
                n_ss += 1
            if r.get("verdict") == GATE_SHRINK:
                n_shr += 1
                if r.get("gate") in _WAS_REFUSAL:
                    n_r2s += 1
    line = (f"C26: {n_sk} shadow-would-kill, {n_ss} shadow-would-shrink, {n_shr} shrinks applied, "
            f"{n_r2s} refusals\u2192shrink")
    return {"shadow_would_kill": n_sk, "shadow_would_shrink": n_ss, "shrinks_applied": n_shr,
            "refusals_to_shrink": n_r2s, "gate_policy_version": GATE_POLICY_VERSION, "line": line}



# ─────────────────────────────── C27: the wash-trade sequence ───────────────
#
# THE DEFECT (measured 2026-10-07): since 2026-10-01, 49 of 75 LIVE buys came
# back HTTP 403 "potential wash trade detected. use complex orders". Every one
# was a TOP-UP of a name already holding our resting GTC sell stop. The broker's
# own table (WASH_RULE_URL, fetched 2026-10-07) says why, in two rows:
#
#     | stop sell  | limit buy  | always rejected |
#     | limit buy  | stop sell  | always rejected |
#
# So a buy cannot be placed while the stop rests, AND the stop for the combined
# quantity cannot be placed while any part of the buy is still open. The only
# lawful order of operations with plain orders is:
#
#     cancel the resting stop(s) -> confirm CANCELED -> buy -> wait until the buy
#     is TERMINAL (cancel any unfilled remainder) -> ONE stop for the shares
#     actually held, at max(prior stop, the contract's stop level)
#
# with a rollback at every step (`execute_topup_sequence`). This is NOT a gate
# and is NOT shadowed: it changes no quantity, no cap and no stop distance
# (the combined stop is never looser than the stop it replaces); it changes
# only the ORDER in which the frozen contract's own orders reach the broker.

WASH_RULE_URL = "https://docs.alpaca.markets/us/docs/user-protection"
WASH_RULE_QUOTE = ("If we detect a possible wash trade, we reject the order and send back an error message "
                   "with the HTTP status code 403 (Forbidden). [...] | stop sell | limit buy | always rejected | "
                   "[...] | limit buy | stop sell | always rejected | [...] These complex orders and trailing "
                   "stop orders are exceptions to our wash trade protection.")
REFUSED_WASH_TRADE_RULE = "REFUSED_WASH_TRADE_RULE"
REFUSED_WORST_CASE_LINE = "REFUSED_WORST_CASE_LINE"
REJ_WASH, REJ_422, REJ_OTHER = "wash_trade_403", "http_422", "other"
_TERMINAL = ("canceled", "filled", "expired", "rejected", "done_for_day")
#: Order classes the broker exempts ("complex orders"); we place none, and a leg
#: of one is never cancelled by this sequence.
_WASH_EXEMPT_CLASSES = ("bracket", "oco", "oto")


def classify_rejection(outcome: Any) -> Optional[str]:
    """`wash_trade_403` | `http_422` | `other` for a broker rejection; None when
    the outcome is not a rejection. Reads the outcome text `submit_once` writes
    ("REJECTED http 403: {... 'potential wash trade detected ...'}") or a buy's
    terminal status `rejected`."""
    s = str(outcome or "")
    if not s.startswith("REJECTED") and s != "rejected":
        return None
    if "wash trade" in s or "40310000" in s:
        return REJ_WASH
    if "http 422" in s:
        return REJ_422
    return REJ_OTHER


def rejection_summary(actions: Iterable[dict], *, threshold: Optional[float] = None) -> dict:
    """The day's LIVE buys that reached the broker, and how many it rejected, by
    reason. A buy REFUSED by us (a gate, REFUSED_WASH_TRADE_RULE) never reached
    the broker and is counted under `refused_before_broker`, not here."""
    thr = float(_cfg.FLEET_REJECTED_BUY_DEGRADED_FRAC if threshold is None else threshold)
    n_sent = 0
    by = {REJ_WASH: 0, REJ_422: 0, REJ_OTHER: 0}
    refused_c27 = 0
    for a in actions:
        if a.get("side") != "buy" or a.get("kind") != "buy":
            continue
        ref = str(a.get("refused") or "")
        if ref.startswith(REFUSED_WASH_TRADE_RULE) or ref.startswith(REFUSED_WORST_CASE_LINE):
            refused_c27 += 1
            continue
        if a.get("mode") != "LIVE":
            continue
        oc = str(a.get("outcome") or "")
        if not oc or oc.startswith("STOP file"):
            continue
        n_sent += 1
        k = classify_rejection(oc) or classify_rejection(a.get("entry_status"))
        if k:
            by[k] += 1
    n_rej = sum(by.values())
    frac = (n_rej / n_sent) if n_sent else 0.0
    degraded = bool(n_sent and frac > thr)
    line = (f"C27 rejections: {n_rej} of {n_sent} LIVE buys rejected by the broker ({frac:.0%}) -- "
            f"{by[REJ_WASH]} wash-trade 403, {by[REJ_422]} 422, {by[REJ_OTHER]} other; "
            f"{refused_c27} refused before the broker ({REFUSED_WASH_TRADE_RULE}/{REFUSED_WORST_CASE_LINE})"
            + (f" -> DEGRADED (> {thr:.0%})" if degraded else ""))
    return {"n_live_buys_sent": n_sent, "n_rejected": n_rej, "by_reason": by, "rejected_frac": round(frac, 4),
            "refused_before_broker": refused_c27, "threshold": thr, "degraded": degraded, "line": line}


def wash_conflicts(symbol: str, buy_limit: Optional[float], open_orders: Iterable[dict]) -> list[tuple[dict, str]]:
    """Resting orders on `symbol` the broker's table rejects a new LIMIT BUY
    against: [(order, "stop" | "blocking")]. "stop" = a sell stop / stop_limit
    this sequence may cancel and re-place; "blocking" = a resting sell limit or
    market order (an exit in flight), which a top-up never cancels."""
    out: list[tuple[dict, str]] = []
    bl = float(buy_limit or 0.0)
    for o in open_orders:
        if o.get("symbol") != symbol or o.get("side") != "sell":
            continue
        if str(o.get("order_class") or "simple") in _WASH_EXEMPT_CLASSES:
            continue
        t = o.get("type")
        if t == "trailing_stop":
            continue                                  # exempt in the broker's own words
        if t == "stop":
            out.append((o, "stop"))
        elif t == "stop_limit":
            if bl >= float(o.get("limit_price") or 0.0):
                out.append((o, "stop"))
        elif t == "market":
            out.append((o, "blocking"))
        elif t == "limit":
            if bl >= float(o.get("limit_price") or float("inf")):
                out.append((o, "blocking"))
    return out


def plan_topup_sequence(a: Action, open_orders: list[dict], *, held_qty: float, stop_frac: float,
                        stop_how: str, contract_hash: str, day: str
                        ) -> tuple[list[Action], Optional[Action], Optional[str]]:
    """For a buy: (cancels of the conflicting resting stops, the ONE combined
    stop, refusal). ([], None, None) when nothing conflicts (a new name, or only
    a trailing stop rests): the buy goes out exactly as before.

    The combined stop: quantity = held + this buy (re-read from the broker after
    the buy is terminal, so it is never above what is held), price =
    max(every replaced stop, the contract's stop level at the reference price)
    -- `stop_never_loosened` re-checks it at the gate."""
    if a.side != "buy" or a.refused:
        return [], None, None
    conf = wash_conflicts(a.symbol, a.limit_price, open_orders)
    if not conf:
        return [], None, None
    blocking = [o for o, k in conf if k != "stop"]
    if blocking:
        o = blocking[0]
        return [], None, (f"{REFUSED_WASH_TRADE_RULE}: a resting {o.get('type')} sell {o.get('id')} on {a.symbol} "
                          "would make the broker reject this buy, and it is an exit in flight, not a stop this "
                          "pass may cancel")
    stops = [o for o, _ in conf]
    px = float(a.price_ref or a.limit_price or 0.0)
    old = max(float(o.get("stop_price") or 0.0) for o in stops)
    sp = max(old, stop_price_for(px, stop_frac)) if px > 0 else old
    if px <= 0 or sp >= px:
        return [], None, (f"{REFUSED_WASH_TRADE_RULE}: the combined stop {sp} would be at/above the reference "
                          f"price {px}; the resting stop is left alone")
    held_i = int(math.floor(max(0.0, float(held_qty)) + 1e-9))
    seq = "ws-" + _sha(a.coid, *sorted(str(o.get("id")) for o in stops), n=12)
    resting = [{"id": o.get("id"), "type": o.get("type"), "stop_price": float(o.get("stop_price") or 0.0),
                "limit_price": o.get("limit_price"), "qty": float(o.get("qty") or 0.0),
                "client_order_id": o.get("client_order_id")} for o in stops]
    cancels = [Action(a.role, "cancel", a.symbol, 0, "", "cancel", protective=True, cancel_order_id=r["id"],
                      price_ref=px, coid=f"cancel:{r['id']}",
                      reason=(f"C27 wash-trade sequence {seq}: release the resting stop {r['client_order_id']} "
                              f"({r['qty']:g} @ {r['stop_price']}) so the top-up buy is lawful"),
                      inputs={"wash_seq": seq, "seq_step": "cancel_resting_stop", "resting": r})
               for r in resting]
    combined = held_i + int(a.qty)
    stop = Action(a.role, "stop_combined", a.symbol, combined, "sell", "stop", "gtc", stop_price=sp,
                  price_ref=px, protective=True,
                  coid=client_order_id(a.role, day, "stopcmb", a.symbol, contract_hash, f"{combined}"),
                  reason=(f"C27 wash-trade sequence {seq}: ONE stop for held {held_i} + top-up {a.qty}, at "
                          f"max(prior stop {old}, contract level {stop_how}); placed only after the buy is "
                          "terminal, for the shares the broker then reports"),
                  inputs={"wash_seq": seq, "seq_step": "combined_stop", "replaces_stop": old,
                          "stop_frac": stop_frac, "held_before": held_i, "topup_qty": int(a.qty)})
    a.inputs.update(wash_seq=seq, seq_step="buy", resting_stops=resting)
    return cancels, stop, None


def topup_worst_case(*, held: float, px: float, resting: list[dict], add_qty: int, add_px: float,
                     combined_sp: float, planned_frac: float) -> dict:
    """One top-up name, in dollars at the stops (gaps can be worse):
    now      = held shares at their resting stops (whole position if not fully covered),
    old_plan = now + the added shares at the contract stop fraction (what the
               pre-C27 path printed: buy and a separate stop),
    sequence = held + added shares at the ONE combined stop."""
    cov = sum(float(r.get("qty") or 0.0) for r in resting)
    if held > 0 and resting and cov + 1e-9 >= held:
        now = max(0.0, (px - min(float(r["stop_price"]) for r in resting)) * held)
    else:
        now = abs(held * px)
    old_plan = now + add_qty * add_px * planned_frac
    seq = max(0.0, (px - combined_sp) * held) + max(0.0, (add_px - combined_sp) * add_qty)
    return {"now": round(now, 2), "old_plan": round(old_plan, 2), "sequence": round(seq, 2),
            "delta_vs_now": round(seq - now, 2), "delta_vs_old_plan": round(seq - old_plan, 2)}


def topup_line_walk(worst_now: float, line: float, deltas: list[tuple[str, float]]) -> dict[str, str]:
    """C27 worst-case rule, in plan order: a top-up sequence may not take the
    account's worst case (at the stops) above its contract's line, nor raise it
    further when it already sits above. A sequence that LOWERS the worst case
    (the combined stop re-based the held shares upward) always passes.
    -> {key: "OK" | REFUSED_WORST_CASE_LINE}."""
    out: dict[str, str] = {}
    cum = 0.0
    for k, d in deltas:
        if d > 1e-6 and worst_now + cum + d > line:
            out[k] = REFUSED_WORST_CASE_LINE
            continue
        out[k] = "OK"
        cum += d
    return out


def _now_ms(now: Callable[[], float]) -> str:
    return datetime.fromtimestamp(now(), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def execute_topup_sequence(v: "Venue", buy: Action, cancels: list[Action], stop: Action, *,
                           wait_buy_s: Optional[float] = None, wait_cancel_s: Optional[float] = None,
                           sleep: Callable = time.sleep, now: Callable[[], float] = time.time,
                           refresh: bool = True) -> dict:
    """cancel resting stop(s) -> buy -> wait terminal -> ONE combined stop, as one
    unit, every step timestamped. Rollback:

    * a resting stop that will not confirm CANCELED: re-place every stop already
      cancelled, send no buy (REFUSED_WASH_TRADE_RULE; ABORTED_STOP_FILLED when
      it had filled -- the position changed under us);
    * the buy is rejected: re-place the original stop(s) immediately
      (BUY_REJECTED_ROLLED_BACK);
    * the combined stop is rejected: place a plain protective `stop` (market on
      trigger) at the same price under a new id and mark the sequence REFUSED;
      if that is rejected too, re-place the original stop(s) and mark it
      UNPROTECTED with the uncovered quantity.

    The stop-less window runs from the first CONFIRMED cancel to the first
    accepted stop (combined, protective or restored) and is on the result."""
    wb = float(_cfg.FLEET_WASH_SEQ_BUY_WAIT_S if wait_buy_s is None else wait_buy_s)
    wc = float(_cfg.FLEET_WASH_SEQ_CANCEL_WAIT_S if wait_cancel_s is None else wait_cancel_s)
    ev: list[dict] = []
    out: dict[str, Any] = {"wash_seq": buy.inputs.get("wash_seq"), "symbol": buy.symbol, "events": ev,
                           "outcomes": {}, "order_ids": {}, "buy_filled_qty": 0, "combined_qty": None,
                           "stop_price": stop.stop_price, "status": None, "refused": None,
                           "stopless_window_s": None, "unprotected_qty": 0}
    t_open: list[float] = []
    t_close: list[float] = []

    def log(e: str, **k: Any) -> None:
        ev.append({"t": _now_ms(now), "e": e, **k})

    def protect_ok() -> None:
        if not t_close:
            t_close.append(now())

    def held_now(default: float) -> float:
        try:
            for p in v.positions():
                if p.get("symbol") == buy.symbol:
                    return float(p.get("qty") or 0.0)
            return 0.0
        except Exception:                                   # noqa: BLE001 -- fall back to the arithmetic
            return default

    def restore(cancelled: list[Action], cap_qty: float) -> int:
        """Re-place the original stops (plain `stop`, same price), capped at what is held."""
        left = int(math.floor(max(0.0, cap_qty) + 1e-9))
        placed = 0
        for i, c in enumerate(cancelled, 1):
            r = c.inputs.get("resting") or {}
            q = min(int(float(r.get("qty") or 0)), left - placed)
            if q <= 0:
                continue
            ra = Action(buy.role, "stop_restore", buy.symbol, q, "sell", "stop", "gtc",
                        stop_price=float(r.get("stop_price") or 0.0), price_ref=stop.price_ref, protective=True,
                        coid=f"{stop.coid[:112]}-rb{i}",
                        reason=f"C27 rollback: re-place the original stop {r.get('client_order_id')}")
            so = submit_once(v, ra)
            log("restore_sent", coid=ra.coid, qty=q, stop_price=ra.stop_price, outcome=so["outcome"])
            out["outcomes"][ra.coid] = so["outcome"]
            if so.get("order_id"):
                out["order_ids"][ra.coid] = so["order_id"]
                placed += q
                protect_ok()
        return placed

    def finish(status: str, refused: Optional[str] = None) -> dict:
        out["status"], out["refused"] = status, refused
        if t_open:
            out["stopless_window_s"] = round((t_close[0] if t_close else now()) - t_open[0], 3)
        log("done", status=status)
        return out

    held0 = float(stop.inputs.get("held_before") or 0)
    # Re-read what rests NOW: a stop renewed or placed earlier in this same run
    # (maintenance) has an id the plan never saw, and it conflicts just the same.
    if refresh:
        try:
            live = wash_conflicts(buy.symbol, buy.limit_price, v.open_orders())
        except Exception as exc:                            # noqa: BLE001 -- the plan's list is the fallback
            live = None
            log("open_orders_unreadable", error=f"{type(exc).__name__}: {exc}"[:120])
        if live is not None:
            blocking = [o for o, k in live if k != "stop"]
            if blocking:
                why = (f"a resting {blocking[0].get('type')} sell {blocking[0].get('id')} conflicts and is not a "
                       "stop; nothing cancelled, buy not sent")
                out["outcomes"][buy.coid] = f"{REFUSED_WASH_TRADE_RULE}: {why}"
                out["outcomes"][stop.coid] = "not sent: sequence refused before any step"
                for c in cancels:
                    out["outcomes"][c.coid] = "not sent: sequence refused before any step"
                return finish(REFUSED_WASH_TRADE_RULE, f"{REFUSED_WASH_TRADE_RULE}: {why}")
            plan_ids = {c.cancel_order_id for c in cancels}
            for o, _ in live:
                if o.get("id") not in plan_ids:
                    r = {"id": o.get("id"), "type": o.get("type"), "stop_price": float(o.get("stop_price") or 0.0),
                         "limit_price": o.get("limit_price"), "qty": float(o.get("qty") or 0.0),
                         "client_order_id": o.get("client_order_id")}
                    cancels = cancels + [Action(buy.role, "cancel", buy.symbol, 0, "", "cancel", protective=True,
                                                cancel_order_id=r["id"], price_ref=stop.price_ref,
                                                coid=f"cancel:{r['id']}", inputs={"resting": r},
                                                reason="C27: a stop resting at execution the plan did not see")]
                    log("extra_resting_stop", order_id=r["id"], stop_price=r["stop_price"], qty=r["qty"])
            live_ids = {o.get("id") for o, _ in live}
            for c in cancels:
                if c.cancel_order_id not in live_ids:
                    out["outcomes"][c.coid] = "not sent: the planned stop no longer rests"
            cancels = [c for c in cancels if c.cancel_order_id in live_ids]
            hi = max([float((c.inputs.get("resting") or {}).get("stop_price") or 0.0) for c in cancels] or [0.0])
            if stop.stop_price is not None and hi > float(stop.stop_price):
                log("combined_stop_raised", old=stop.stop_price, new=hi)   # never looser than anything resting
                stop.stop_price = hi
                out["stop_price"] = hi
    cancelled: list[Action] = []
    for c in cancels:
        stc = v.cancel(c.cancel_order_id)
        log("cancel_sent", order_id=c.cancel_order_id, http=stc)
        term = (wait_terminal(v, c.cancel_order_id, timeout_s=wc, sleep=sleep) if stc in (200, 204)
                else f"http {stc}")
        out["outcomes"][c.coid] = f"cancel http {stc}, {term}"
        log("cancel_terminal", order_id=c.cancel_order_id, status=term)
        if term == "canceled":
            cancelled.append(c)
            if not t_open:
                t_open.append(now())
            continue
        # not cancelled: it FILLED (the position changed under us) or the venue would not confirm
        still_resting = sum(float((x.inputs.get("resting") or {}).get("qty") or 0)
                            for x in cancels if x not in cancelled and x is not c)
        if term != "filled":
            still_resting += float((c.inputs.get("resting") or {}).get("qty") or 0)
        restore(cancelled, held_now(held0) - still_resting)
        why = (f"resting stop {c.cancel_order_id} {'FILLED' if term == 'filled' else 'not confirmed canceled'} "
               f"({term}); buy not sent, cancelled stop(s) re-placed")
        out["outcomes"][buy.coid] = f"{REFUSED_WASH_TRADE_RULE}: {why}"
        out["outcomes"][stop.coid] = "not sent: sequence aborted before the buy"
        return finish("ABORTED_STOP_FILLED" if term == "filled" else REFUSED_WASH_TRADE_RULE,
                      f"{REFUSED_WASH_TRADE_RULE}: {why}")

    so = submit_once(v, buy)
    log("buy_sent", coid=buy.coid, outcome=so["outcome"])
    out["outcomes"][buy.coid] = so["outcome"]
    if not so.get("order_id"):
        h = held_now(held0)
        placed = restore(cancelled, h)
        out["outcomes"][stop.coid] = "not sent: the buy was rejected; the original stop(s) re-placed"
        want = min(int(math.floor(h + 1e-9)),
                   int(sum(float((c.inputs.get("resting") or {}).get("qty") or 0) for c in cancelled)))
        out["unprotected_qty"] = max(0, want - placed)
        if out["unprotected_qty"]:
            return finish("UNPROTECTED", f"REFUSED: the buy was rejected and the original stop could not be "
                                         f"re-placed for {out['unprotected_qty']} share(s)")
        return finish("BUY_REJECTED_ROLLED_BACK")
    boid = so["order_id"]
    out["order_ids"][buy.coid] = boid
    term = wait_terminal(v, boid, timeout_s=wb, sleep=sleep)
    log("buy_terminal" if term in _TERMINAL else "buy_open", status=term)
    if term not in _TERMINAL:
        # any open part of the buy makes the stop unlawful ("limit buy | stop sell | always rejected")
        stc = v.cancel(boid)
        term = wait_terminal(v, boid, timeout_s=wc, sleep=sleep) if stc in (200, 204) else f"http {stc}"
        log("buy_remainder_cancel", http=stc, status=term)
    try:
        od = v.order(boid)
        out["buy_filled_qty"] = int(float(od.get("filled_qty") or 0))
        out["buy_filled_avg_price"] = od.get("filled_avg_price")
    except Exception:                                       # noqa: BLE001
        pass
    out["buy_status"] = term
    q = int(math.floor(held_now(held0 + out["buy_filled_qty"]) + 1e-9))
    out["combined_qty"] = q
    if q <= 0:
        out["outcomes"][stop.coid] = "not sent: nothing held after the buy"
        return finish("OK_NOTHING_HELD")
    stop.qty = q
    so = submit_once(v, stop)
    log("combined_stop_sent", coid=stop.coid, qty=q, stop_price=stop.stop_price, outcome=so["outcome"])
    out["outcomes"][stop.coid] = so["outcome"]
    if so.get("order_id"):
        out["order_ids"][stop.coid] = so["order_id"]
        protect_ok()
        return finish("OK")
    # the combined stop was rejected: a plain protective stop at the same price, new id
    pa = Action(buy.role, "stop_protective", buy.symbol, q, "sell", "stop", "gtc", stop_price=stop.stop_price,
                price_ref=stop.price_ref, protective=True, coid=f"{stop.coid[:114]}-p",
                reason="C27: the combined stop was rejected; plain protective stop at the same price")
    so2 = submit_once(v, pa)
    log("protective_stop_sent", coid=pa.coid, qty=q, stop_price=pa.stop_price, outcome=so2["outcome"])
    out["outcomes"][pa.coid] = so2["outcome"]
    if so2.get("order_id"):
        out["order_ids"][pa.coid] = so2["order_id"]
        protect_ok()
        return finish("REFUSED", f"REFUSED: the combined stop was rejected ({so['outcome'][:80]}); a protective "
                                 f"stop for {q} at {pa.stop_price} was placed instead")
    placed = restore(cancelled, q)
    out["unprotected_qty"] = max(0, q - placed)
    return finish("UNPROTECTED" if out["unprotected_qty"] else "REFUSED",
                  f"REFUSED: combined and protective stops rejected; original stop(s) re-placed for {placed} of "
                  f"{q}; {out['unprotected_qty']} share(s) UNPROTECTED")


def wash_sequence_summary(results: Iterable[dict]) -> dict:
    """Per account: how many top-up sequences ran, how they ended, and the
    longest stop-less window (seconds)."""
    rs = list(results)
    by: dict[str, int] = {}
    for r in rs:
        by[str(r.get("status"))] = by.get(str(r.get("status")), 0) + 1
    win = [float(r["stopless_window_s"]) for r in rs if r.get("stopless_window_s") is not None]
    return {"n": len(rs), "by_status": by, "max_stopless_window_s": max(win) if win else None,
            "stopless_events": len(win),
            "unprotected_qty": sum(int(r.get("unprotected_qty") or 0) for r in rs)}


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

    def stop_fills_since(self, iso: str, *, owned_types: Optional[dict[str, str]] = None) -> list[dict]:
        """Sell fills since `iso` whose order was a STOP (C26 cooldown gate),
        newest first: [{symbol, filled_at, order_id, type}].

        Read from FILL activities, not from the order list: Alpaca's `after`
        filters orders by SUBMISSION time, and the stops that matter are GTC
        orders submitted weeks before they fill. An order's type comes from the
        closed orders submitted in the window, including exact nested child
        identities, else from one GET per order id.
        A missing historical order may use a matching accepted local owned-order
        outcome.  Unresolved or conflicting types raise: history stays UNKNOWN."""
        activities = self.fills(after=iso)
        if not isinstance(activities, list) or len(activities) >= 1000:
            raise FleetRefusal("historical FILL pages incomplete")
        def aware_time(value: Any, label: str) -> datetime:
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("naive time")
                return stamp
            except (AttributeError, TypeError, ValueError) as exc:
                raise FleetRefusal(f"historical {label} time invalid") from exc

        def positive_qty(value: Any, label: str) -> float:
            try:
                if isinstance(value, bool):
                    raise ValueError("boolean quantity")
                qty = float(value)
                if not math.isfinite(qty) or qty <= 0:
                    raise ValueError("nonpositive or nonfinite quantity")
                return qty
            except (TypeError, ValueError) as exc:
                raise FleetRefusal(f"historical {label} quantity invalid") from exc

        since = aware_time(iso, "window")
        fills = []
        activity_ids: set[str] = set()
        for f in activities:
            if not isinstance(f, dict):
                raise FleetRefusal("historical FILL row malformed")
            if f.get("side") == "sell":
                if (f.get("activity_type") != "FILL"
                        or not all(isinstance(f.get(key), str) and f[key]
                                   for key in ("id", "order_id", "symbol"))):
                    raise FleetRefusal("historical sell FILL identity incomplete")
                if f["id"] in activity_ids:
                    raise FleetRefusal("historical sell FILL identity duplicated")
                activity_ids.add(f["id"])
                positive_qty(f.get("qty"), "sell FILL")
                if aware_time(f.get("transaction_time"), "sell FILL") < since:
                    raise FleetRefusal("historical sell FILL before requested window")
                fills.append(f)
        if not fills:
            return []
        closed = self.get("/v2/orders", params={"status": "closed", "after": iso, "limit": 500,
                                                "direction": "desc", "nested": "true"})
        if not isinstance(closed, list) or len(closed) >= 500:
            raise FleetRefusal("historical closed order page incomplete")
        type_of: dict[str, str] = {}
        nested: dict[str, dict] = {}
        seen_ids: set[str] = set()
        for parent in closed:
            if not isinstance(parent, dict):
                raise FleetRefusal("historical closed order row malformed")
            parent_id = parent.get("id")
            if parent_id is not None and (not isinstance(parent_id, str) or not parent_id):
                raise FleetRefusal("historical closed order identity malformed")
            if parent_id:
                if parent_id in seen_ids:
                    raise FleetRefusal("duplicate historical broker order identity")
                seen_ids.add(parent_id)
                if parent.get("type"):
                    type_of[parent_id] = parent["type"]
            legs = parent.get("legs")
            if legs is None:
                continue
            if (not isinstance(legs, list) or
                    (legs and (not parent_id or not isinstance(parent.get("order_class"), str)
                               or parent["order_class"] not in
                               {"mleg", "bracket", "oco", "oto"}))):
                raise FleetRefusal("nested historical order structure malformed")
            for leg in legs:
                if (not isinstance(leg, dict) or not isinstance(leg.get("id"), str)
                        or not leg["id"] or leg.get("legs")):
                    raise FleetRefusal("nested historical order leg malformed")
                leg_id = leg["id"]
                if leg_id in seen_ids:
                    raise FleetRefusal("duplicate historical broker order identity")
                seen_ids.add(leg_id)
                nested[leg_id] = leg

        def leg_type(leg: dict, fs: list[dict]) -> str:
            """Bind a nested child to its exact FILL identity before trusting type."""
            kind = leg.get("type")
            if kind not in (*STOP_TYPES, "market", "limit"):
                raise FleetRefusal("nested historical order type unknown")
            if leg.get("side") != "sell" or any(f["symbol"] != leg.get("symbol") for f in fs):
                raise FleetRefusal("nested historical leg symbol/side disagrees with FILL")
            qty = positive_qty(leg.get("qty"), "nested ordered")
            filled = positive_qty(leg.get("filled_qty"), "nested filled")
            activity_qty = sum(positive_qty(f.get("qty"), "nested FILL") for f in fs)
            if filled > qty + 1e-6 or activity_qty > filled + 1e-6:
                raise FleetRefusal("nested historical leg/FILL quantity conflicts")
            if (not isinstance(leg.get("status"), str)
                    or leg["status"] not in {"filled", "partially_filled"}):
                raise FleetRefusal("nested historical leg is not a filled order")
            times = [aware_time(f.get("transaction_time"), "nested FILL") for f in fs]
            submitted = (aware_time(leg["submitted_at"], "nested submission")
                         if leg.get("submitted_at") is not None else None)
            broker = (aware_time(leg["filled_at"], "nested fill")
                      if leg.get("filled_at") is not None else None)
            if (leg["status"] == "filled" and broker is None
                    or submitted is not None and any(t < submitted for t in times)
                    or broker is not None and any(t > broker for t in times)
                    or broker is not None and submitted is not None and broker < submitted
                    or (abs(activity_qty - filled) <= 1e-6 and leg["status"] == "filled"
                        and max(times) != broker)):
                raise FleetRefusal("nested historical leg/FILL time conflicts")
            return kind

        nested_fills: dict[str, list[dict]] = {}
        for fill in fills:
            if fill["order_id"] in nested:
                nested_fills.setdefault(fill["order_id"], []).append(fill)
        for order_id, matched in nested_fills.items():
            kind = leg_type(nested[order_id], matched)
            # A direct child GET may be 404 for mleg legs. If it is readable,
            # it must corroborate rather than contradict the nested broker row.
            st, direct = self.call("GET", f"/v2/orders/{order_id}")
            if st == 200:
                leg = nested[order_id]
                if (not isinstance(direct, dict) or direct.get("id") != order_id
                        or direct.get("type") != kind
                        or direct.get("symbol") != leg["symbol"]
                        or direct.get("side") != "sell"
                        or direct.get("status") != leg.get("status")
                        or positive_qty(direct.get("qty"), "direct ordered")
                        != positive_qty(leg.get("qty"), "nested ordered")
                        or positive_qty(direct.get("filled_qty"), "direct filled")
                        != positive_qty(leg.get("filled_qty"), "nested filled")
                        or (aware_time(direct["filled_at"], "direct fill")
                            if direct.get("filled_at") is not None else None)
                        != (aware_time(leg["filled_at"], "nested fill")
                            if leg.get("filled_at") is not None else None)):
                    raise FleetRefusal("direct and nested historical child identities conflict")
            elif st != 404:
                raise FleetRefusal(f"historical nested child unreadable: HTTP {st}")
            type_of[order_id] = kind
        out = []
        for f in fills:
            oid = f["order_id"]
            if oid not in type_of:
                st, js = self.call("GET", f"/v2/orders/{oid}")
                if st == 200 and isinstance(js, dict):
                    type_of[oid] = js.get("type")
                elif st == 404:
                    type_of[oid] = (owned_types or {}).get(oid)
                else:
                    raise FleetRefusal(f"historical order type unreadable: HTTP {st}")
            if not type_of[oid]:
                raise FleetRefusal("historical order type unknown for a sell fill")
            if type_of[oid] not in (*STOP_TYPES, "market", "limit"):
                raise FleetRefusal("historical order type unrecognized for a sell fill")
            if type_of[oid] in STOP_TYPES:
                out.append({"symbol": f.get("symbol"), "filled_at": f.get("transaction_time"),
                            "order_id": oid, "type": type_of[oid]})
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


def submit_once(v: Venue, a: Action, *, strict_new: bool = False) -> dict:
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
    if existing and strict_new:
        raise FleetRefusal("exact protective client id appeared before POST; no suffix or resend")
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
                "order_id": js.get("id"), "ack": js}
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
