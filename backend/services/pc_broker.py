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
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
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
#: A held name is rebalanced toward a non-zero target only when the drift is at
#: least this fraction of the target notional (and never below MIN_ORDER_USD).
REBALANCE_DRIFT_FRAC: float = float(os.getenv("AEGIS_PC_REBALANCE_DRIFT_FRAC", "0.10"))
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


class EpochPreSubmitRefused(BrokerError):
    """A local guard refused before any network order POST was attempted."""


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


def orders(status: str = "all", limit: int = 100, after: str | None = None,
           *, before_order_id: str | None = None) -> list[dict]:
    return _call("GET", "/v2/orders",
                 params={"status": status, "limit": limit, "direction": "desc",
                         "after": after, "before_order_id": before_order_id}) or []


def order_by_client_id(client_order_id: str) -> dict:
    """A 404 is an unresolved historical lookup, never permission to resend."""
    return _call("GET", "/v2/orders:by_client_order_id",
                 params={"client_order_id": client_order_id})


def fill_activities(order_id: str, *, page_token: str | None = None) -> list[dict]:
    """One page of broker FILL activities for a specific order."""
    return _call("GET", "/v2/account/activities/FILL",
                 params={"order_id": order_id, "page_size": 100,
                         "page_token": page_token, "direction": "desc"}) or []


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

def _process_birth_utc(pid: int) -> str | None:
    """Kernel creation time; a PID alone can be reused after a process exits."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(wintypes.DWORD)]
            k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
                ctypes.POINTER(wintypes.FILETIME)] * 4
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = k32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None
            try:
                code = wintypes.DWORD()
                if not k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                    return None
                times = [wintypes.FILETIME() for _ in range(4)]
                if not k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                    return None
                ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                born = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(
                    microseconds=ticks // 10)
                return born.isoformat(timespec="microseconds")
            finally:
                k32.CloseHandle(handle)
        stat = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        ticks = int(stat.rsplit(")", 1)[1].split()[19])
        boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text(
            encoding="utf-8").splitlines() if line.startswith("btime "))
        born = datetime.fromtimestamp(boot + ticks / os.sysconf("SC_CLK_TCK"),
                                      tz=timezone.utc)
        return born.isoformat(timespec="microseconds")
    except (OSError, ValueError, IndexError, StopIteration, OverflowError):
        return None


@contextmanager
def _lease_mutex():
    """Kernel-held lease mutex: a dead process cannot strand a lock file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = LEASE_PATH.with_name(LEASE_PATH.name + ".lock")
    with lock.open("a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
            os.fsync(fh.fileno())
        fh.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise OwnershipConflict("broker lease mutation already in progress") from exc
        try:
            yield
        finally:
            fh.seek(0)
            if os.name == "nt":
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _write_lease(path: Path, row: dict) -> None:
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(row, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def open_lease(*, owner: str = "live_market_loop", force: bool = False) -> dict:
    """Atomically claim the sole broker lease; never force-steal an open one."""
    if force:
        raise OwnershipConflict("forced broker lease takeover is disabled")
    with _lease_mutex():
        try:
            prior = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            prior = None
        except (OSError, ValueError) as exc:
            raise OwnershipConflict("prior broker lease is unreadable") from exc
        if prior and prior.get("open"):
            raise OwnershipConflict("prior broker lease is still open; clean closure required")
        birth = _process_birth_utc(os.getpid())
        if birth is None:
            raise OwnershipConflict("process birth cannot be verified")
        acct = account()
        if not acct.get("account_number"):
            raise OwnershipConflict("broker account number absent at lease open")
        lease = {"open": True, "owner": owner, "pid": os.getpid(),
                 "process_birth_utc": birth, "session_nonce": uuid.uuid4().hex,
                 "opened": _now(), "account_number": acct["account_number"],
                 "equity_at_open": float(acct.get("equity") or 0.0),
                 "prefix": LEASE_PREFIX}
        _write_lease(LEASE_PATH, lease)
        return lease


def close_lease(*, expected_nonce: str | None = None) -> None:
    with _lease_mutex():
        try:
            d = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            raise OwnershipConflict("broker lease is unreadable at close") from exc
        if (expected_nonce is not None and d.get("session_nonce") != expected_nonce):
            raise OwnershipConflict("broker lease changed owner before close")
        if (d.get("pid") != os.getpid() or not d.get("process_birth_utc")
                or d["process_birth_utc"] != _process_birth_utc(os.getpid())):
            raise OwnershipConflict("broker lease process identity changed before close")
        if not d.get("open"):
            return
        d["open"] = False
        d["closed"] = _now()
        _write_lease(LEASE_PATH, d)
        if d.get("session_nonce"):
            history = STATE_DIR / "lease_history"
            history.mkdir(parents=True, exist_ok=True)
            _write_lease(history / f"{d['session_nonce']}.json", d)


def recover_unclean_epoch_lease(*, journal_path: Path, broker) -> dict:
    """Explicit dead-owner release after exact journal and read-only order proof.

    This does not retry, cancel or submit an order. An ambiguous intent, order
    lookup or fill leaves the old lease open for attended investigation.
    """
    from backend.services import pc_policy_epoch as PE  # noqa: PLC0415
    from backend.services import sim_session as SS  # noqa: PLC0415
    with _lease_mutex():
        try:
            lease = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OwnershipConflict("unclean lease unreadable") from exc
        status = SS.status()
        session = status.get("session") or {}
        row = PE._load(journal_path)
        birth = lease.get("process_birth_utc")
        pid = lease.get("pid")
        if (status.get("state") != "UNCLEAN" or not lease.get("open")
                or not isinstance(pid, int) or not birth
                or lease.get("owner") != f"sim_run {session.get('id')}"
                or session.get("id") != row.get("session_id")
                or session.get("pid") != pid
                or row.get("lease_pid") != pid or row.get("lease_birth_utc") != birth
                or lease.get("session_nonce") != row.get("nonce")
                or row.get("content_sha256") != PE.EXPECTED_CONTENT_SHA256
                or PE.account_fingerprint(lease.get("account_number"))
                   != PE.EXPECTED_ACCOUNT_FINGERPRINT
                or row.get("account_fingerprint") != PE.EXPECTED_ACCOUNT_FINGERPRINT):
            raise OwnershipConflict("unclean lease, session and epoch identity disagree")
        observed_birth = _process_birth_utc(pid)
        if observed_birth == birth or (observed_birth is None and _pid_alive(pid)):
            raise OwnershipConflict("old lease process may still be alive")
        if row.get("state") not in {"PREPARED", "RECONCILED", "ACTIVE"}:
            raise OwnershipConflict("unclean transition is not fully resolved")
        stock_intents = list(row.get("stock_intents") or [])
        unresolved = [i for i in stock_intents if i.get("status") not in
                      {"FILLED", "GUARD_REFUSED_NO_POST"}]
        if (len(unresolved) > 1 or any(i not in stock_intents[-1:]
                                       or i.get("status") not in
                                       {"SUBMIT_UNKNOWN", "ACKNOWLEDGED"}
                                       for i in unresolved)):
            raise OwnershipConflict("unclean stock POST may be unresolved")
        core = row.get("intent")
        if row["state"] == "PREPARED" and core:
            raise OwnershipConflict("prepared epoch unexpectedly carries an exit")
        if core and (row["state"] not in {"RECONCILED", "ACTIVE"}
                     or not row.get("fill_economic")):
            raise OwnershipConflict("unclean core exit has no reconciled fill")
        known = PE.stock_client_ids(row)
        evidence = broker.evidence(known_client_ids=known)
        try:
            observed = datetime.fromisoformat(str(evidence["observed_utc"]))
            age = (datetime.now(timezone.utc)
                   - observed.astimezone(timezone.utc)).total_seconds()
        except (KeyError, TypeError, ValueError) as exc:
            raise OwnershipConflict("recovery broker timestamp unreadable") from exc
        ev_lease = evidence.get("lease") or {}
        acct = evidence.get("account") or {}
        if (observed.tzinfo is None or not -5 <= age <= 30
                or evidence.get("host") != PE.PAPER_HOST
                or evidence.get("orders_complete") is not True
                or evidence.get("foreign_orders") != []
                or evidence.get("open_orders") != []
                or acct.get("account_number") != lease.get("account_number")
                or any(ev_lease.get(k) != lease.get(k) for k in
                       ("owner", "pid", "process_birth_utc", "session_nonce",
                        "account_number", "open"))):
            raise OwnershipConflict("unclean broker account/order evidence incomplete")
        economic = PE._economic(evidence)
        if (row["state"] in {"RECONCILED", "ACTIVE"}
                and PE._decimal(economic["spy_qty"], "recovery SPY residual") >= 1):
            raise OwnershipConflict("unclean strategic index exit is unresolved")
        resolved = False
        for intent in ([core] if core else []) + stock_intents:
            coid = intent["client_order_id"]
            order = broker.order_by_client_id(coid)
            if intent is not core and intent.get("status") == "GUARD_REFUSED_NO_POST":
                if order is not None:
                    raise OwnershipConflict("order appeared after proven no-POST refusal")
                continue
            expected_symbol = "SPY" if intent is core else intent["symbol"]
            expected_side = "sell" if intent is core else intent["side"]
            if (not order or not order.get("id")
                    or order.get("client_order_id") != coid
                    or order.get("symbol") != expected_symbol
                    or order.get("side") != expected_side
                    or str(order.get("status") or "").lower() != "filled"
                    or PE._decimal(order.get("qty"), "recovery order quantity")
                       != PE._decimal(intent.get("qty"), "recovery intent quantity")):
                raise OwnershipConflict("unclean known order unresolved or changed")
            total, cash_flow, seen = PE.Decimal(0), PE.Decimal(0), set()
            for fill in broker.fills(order["id"]):
                fid = fill.get("id")
                if (not fid or fid in seen or fill.get("order_id") != order["id"]
                        or fill.get("symbol") != expected_symbol
                        or fill.get("side") != expected_side
                        or fill.get("activity_type") != "FILL"):
                    raise OwnershipConflict("unclean fill history ambiguous")
                seen.add(fid)
                quantity = PE._decimal(fill.get("qty"), "recovery fill quantity")
                price = PE._decimal(fill.get("price"), "recovery fill price")
                if quantity <= 0 or price <= 0:
                    raise OwnershipConflict("unclean fill quantity or price invalid")
                total += quantity
                cash_flow += quantity * price * (1 if expected_side == "sell" else -1)
            if total != PE._decimal(intent.get("qty"), "recovery intent quantity"):
                raise OwnershipConflict("unclean fills do not sum to owned order")
            if intent in unresolved:
                current_qty = sum((PE._decimal(p["qty"], "recovery held quantity")
                                   for p in evidence["positions"]
                                   if p.get("symbol") == expected_symbol), PE.Decimal(0))
                start_qty = PE._decimal(intent.get("starting_qty"), "recovery starting quantity")
                start_cash = PE._decimal(intent.get("starting_cash"), "recovery starting cash")
                expected_qty = start_qty + total * (1 if expected_side == "buy" else -1)
                tolerance = max(PE.Decimal("0.01"), abs(cash_flow) * PE.Decimal("0.0001"))
                if (current_qty != expected_qty
                        or abs(PE._decimal(economic["cash"], "recovery cash")
                               - start_cash - cash_flow) > tolerance):
                    raise OwnershipConflict("unclean stock fill economics do not reconcile")
                intent["status"] = "FILLED"
                intent["filled_utc"] = _now()
                intent["measured_cash_flow"] = str(cash_flow)
                resolved = True
        if resolved:
            PE._save(journal_path, row)
            row = PE._load(journal_path)
        # Re-read process identity and lease while the mutex is still held.
        if (_process_birth_utc(pid) == birth
                or json.loads(LEASE_PATH.read_text(encoding="utf-8")) != lease):
            raise OwnershipConflict("unclean owner or lease changed during recovery")
        lease["open"] = False
        lease["closed"] = _now()
        lease["recovered_from_unclean"] = True
        lease["journal_revision"] = row.get("revision")
        lease["journal_sha256"] = PE._sha(row)
        lease["recovery_order_count"] = len(known)
        lease["unclean_session"] = {"id": session["id"], "pid": pid,
                                    "state": "UNCLEAN",
                                    "heartbeat": session.get("heartbeat")}
        _write_lease(LEASE_PATH, lease)
        history = STATE_DIR / "lease_history"
        history.mkdir(parents=True, exist_ok=True)
        _write_lease(history / f"{lease['session_nonce']}.json", lease)
        return {"status": "RECOVERED_CLOSED", "journal_revision": row.get("revision"),
                "known_order_count": len(known)}


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
                min_order_usd: float = MIN_ORDER_USD,
                max_adv_participation: float = MAX_ADV_PARTICIPATION,
                rebalance_drift_frac: float = REBALANCE_DRIFT_FRAC) -> list[PlannedOrder]:
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
        # THE DRIFT BAND (2026-09-25, first live PROBE day): a 2% target on a
        # $345 stock is 58.3 shares; as the price moves the integer flips and the
        # loop sold 1 GOOGL at 13:37 and bought it back at 13:47. A rebalance of
        # a name we already hold, toward a non-zero target, is sent only when
        # the drift is worth the spread. Entries and exits are never gated here.
        if cur_qty and target_qty:
            band_usd = max(min_order_usd, rebalance_drift_frac * want_w * equity)
            if notional < band_usd:
                plans.append(PlannedOrder(sym, "buy" if delta > 0 else "sell", 0, notional,
                                          (t.reason if t else "exit"),
                                          refused=(f"drift ${notional:,.0f} < band "
                                                   f"${band_usd:,.0f} ({rebalance_drift_frac:.0%} "
                                                   f"of the target): rounding churn, not a decision"),
                                          current_qty=cur_qty, target_qty=target_qty, price=px))
                continue
        if notional < min_order_usd and target_qty != 0:
            plans.append(PlannedOrder(sym, "buy" if delta > 0 else "sell", 0, notional,
                                      (t.reason if t else "exit"),
                                      refused=(f"${notional:,.0f} < MIN_ORDER_USD "
                                               f"${min_order_usd:,.0f}: the cost is the edge"),
                                      current_qty=cur_qty, target_qty=target_qty, price=px))
            continue

        adv = (t.median_dollar_vol if t else None)
        if adv and notional > adv * max_adv_participation:
            capped = int((adv * max_adv_participation) // px)
            refusal = (f"order ${notional:,.0f} is "
                       f"{notional/adv:.2%} of 20d median $vol; capped at "
                       f"{max_adv_participation:.0%} (={capped} sh)")
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


def submit_epoch_core_exit(*, qty: int, client_order_id: str,
                           session_id: str, session_nonce: str,
                           account_fingerprint: str) -> dict:
    """Serialize exact lease ownership through the broker POST boundary."""
    with _lease_mutex():
        return _submit_epoch_core_exit_locked(
            qty=qty, client_order_id=client_order_id, session_id=session_id,
            session_nonce=session_nonce, account_fingerprint=account_fingerprint)


def _submit_epoch_core_exit_locked(*, qty: int, client_order_id: str,
                           session_id: str, session_nonce: str,
                           account_fingerprint: str) -> dict:
    """One narrow, deterministic SPY reduction with a fresh broker/lease guard.

    The caller must already have persisted its intent and must resolve any
    ambiguous POST using ``order_by_client_id``. This function never retries.
    """
    from backend.services import pc_policy_epoch as PE       # noqa: PLC0415
    if (_host() != PE.PAPER_HOST or not re.fullmatch(r"aegispc-e[0-9a-f]{20}",
                                                      client_order_id or "")
            or type(qty) is not int or qty <= 0):
        raise BrokerError("epoch exit identity, host, or quantity refused")
    try:
        lease = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrokerError("epoch exit lease unreadable") from exc
    acct = account()
    if (lease.get("open") is not True or lease.get("owner") != f"sim_run {session_id}"
            or lease.get("session_nonce") != session_nonce
            or lease.get("pid") != os.getpid()
            or not lease.get("process_birth_utc")
            or lease["process_birth_utc"] != _process_birth_utc(os.getpid())
            or lease.get("account_number") != acct.get("account_number")
            or PE.account_fingerprint(acct.get("account_number")) != account_fingerprint
            or account_fingerprint != PE.EXPECTED_ACCOUNT_FINGERPRINT):
        raise BrokerError("epoch exit account or lease identity changed")
    if (clock() or {}).get("is_open") is not True:
        raise BrokerError("epoch exit venue closed")
    open_orders = orders(status="open", limit=500)
    if not isinstance(open_orders, list) or len(open_orders) >= 500 or open_orders:
        raise BrokerError("epoch exit has pending or incomplete open orders")
    held = positions()
    try:
        if not isinstance(held, list) or not isinstance(acct, dict):
            raise PE.EpochRefused("invalid account or positions")
        cash = PE._decimal(acct.get("cash"), "exit cash")
        equity = PE._decimal(acct.get("equity"), "exit equity")
        gross = PE._decimal(acct.get("long_market_value"), "exit gross")
        quantities = [(p.get("symbol"), PE._decimal(p.get("qty"), "held quantity"),
                       PE._decimal(p.get("market_value"), "held market value"))
                      for p in held]
    except (PE.EpochRefused, AttributeError, TypeError) as exc:
        raise BrokerError("epoch exit account or held quantities invalid") from exc
    symbols = [sym for sym, _, _ in quantities]
    tolerance = max(PE.Decimal("1"), equity * PE.Decimal("0.0005"))
    if (equity <= 0 or cash < 0 or gross < 0
            or any(not isinstance(sym, str) or not sym or q < 0 or v < 0
                   for sym, q, v in quantities)
            or len(set(symbols)) != len(symbols)
            or abs(gross - sum((v for _, _, v in quantities), PE.Decimal(0))) > tolerance
            or abs(equity - cash - gross) > tolerance):
        raise BrokerError("epoch exit account or held capacity does not reconcile")
    spy_qty = sum((q for sym, q, _ in quantities if sym == "SPY"), PE.Decimal(0))
    if spy_qty < qty:
        raise BrokerError("epoch exit exceeds verified held shares or short book")
    if (account() != acct or positions() != held
            or orders(status="open", limit=500) != open_orders):
        raise BrokerError("epoch exit broker snapshot raced a change")
    body = {"symbol": "SPY", "qty": str(qty), "side": "sell", "type": "market",
            "time_in_force": "day", "client_order_id": client_order_id}
    return _call("POST", "/v2/orders", body=body)


def submit_epoch_stock(*, symbol: str, side: str, qty: int,
                       client_order_id: str, session_id: str,
                       session_nonce: str, account_fingerprint: str,
                       minimum_cash_buffer: float, median_dollar_vol: float,
                       planned_price: float, max_name_frac: float,
                       max_adv_participation: float, sleeve: str,
                       risk_sigmas: dict, revision_members: list[str],
                       probe_custody_symbols: list[str],
                       starting_positions: dict[str, str]) -> dict:
    """Serialize lease mutation against the final stock broker POST."""
    with _lease_mutex():
        try:
            body = _submit_epoch_stock_locked(
                symbol=symbol, side=side, qty=qty, client_order_id=client_order_id,
                session_id=session_id, session_nonce=session_nonce,
                account_fingerprint=account_fingerprint,
                minimum_cash_buffer=minimum_cash_buffer,
                median_dollar_vol=median_dollar_vol, planned_price=planned_price,
                max_name_frac=max_name_frac,
                max_adv_participation=max_adv_participation, sleeve=sleeve,
                risk_sigmas=risk_sigmas, revision_members=revision_members,
                probe_custody_symbols=probe_custody_symbols,
                starting_positions=starting_positions)
        except Exception as exc:  # no POST occurs inside the local preflight
            raise EpochPreSubmitRefused(str(exc)) from exc
        return _call("POST", "/v2/orders", body=body)


def _submit_epoch_stock_locked(*, symbol: str, side: str, qty: int,
                       client_order_id: str, session_id: str,
                       session_nonce: str, account_fingerprint: str,
                       minimum_cash_buffer: float, median_dollar_vol: float,
                       planned_price: float,
                       max_name_frac: float, max_adv_participation: float,
                       sleeve: str, risk_sigmas: dict,
                       revision_members: list[str],
                       probe_custody_symbols: list[str],
                       starting_positions: dict[str, str]) -> dict:
    """Submit one contract-planned stock leg under the same exclusive lease.

    The caller owns durable intent/replay and validates portfolio risk. This
    final broker boundary re-reads identity, venue, open orders and buying
    capacity so a stale plan cannot send after a competing order appears.
    """
    from backend.services import pc_policy_epoch as PE       # noqa: PLC0415
    if (_host() != PE.PAPER_HOST or not re.fullmatch(r"aegispc-s[0-9a-f]{20}",
                                                      client_order_id or "")
            or not symbol or symbol.upper() == "SPY"
            or side not in {"buy", "sell"} or type(qty) is not int or qty <= 0
            or minimum_cash_buffer != 0.01 or max_name_frac != 0.12
            or max_adv_participation != 0.02):
        raise BrokerError("epoch stock order identity or body refused")
    try:
        if isinstance(median_dollar_vol, bool):
            raise ValueError("boolean ADV")
        adv = float(median_dollar_vol)
    except (TypeError, ValueError) as exc:
        raise BrokerError("epoch stock ADV absent") from exc
    if not math.isfinite(adv) or adv <= 0:
        raise BrokerError("epoch stock ADV absent or invalid")
    try:
        lease = json.loads(LEASE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrokerError("epoch stock lease unreadable") from exc
    acct = account()
    if (not lease.get("open") or lease.get("owner") != f"sim_run {session_id}"
            or lease.get("session_nonce") != session_nonce
            or lease.get("pid") != os.getpid()
            or not lease.get("process_birth_utc")
            or lease["process_birth_utc"] != _process_birth_utc(os.getpid())
            or lease.get("account_number") != acct.get("account_number")
            or PE.account_fingerprint(acct.get("account_number")) != account_fingerprint
            or account_fingerprint != PE.EXPECTED_ACCOUNT_FINGERPRINT):
        raise BrokerError("epoch stock account or lease identity changed")
    open_orders = orders(status="open", limit=500)
    if len(open_orders) >= 500 or open_orders:
        raise BrokerError("epoch stock pending or incomplete open orders")
    first_positions = positions()
    raw_px = last_prices([symbol]).get(symbol)
    if isinstance(raw_px, bool):
        raise BrokerError("epoch stock quote has boolean price")
    try:
        px = float(raw_px)
    except (TypeError, ValueError) as exc:
        raise BrokerError("epoch stock quote unreadable") from exc
    if isinstance(planned_price, bool):
        raise BrokerError("epoch stock planned price invalid")
    try:
        basis_price = float(planned_price)
    except (TypeError, ValueError) as exc:
        raise BrokerError("epoch stock planned price unreadable") from exc
    if (not math.isfinite(basis_price) or basis_price <= 0
            or not math.isfinite(px) or px <= 0
            or abs(px / basis_price - 1.0) > 0.10):
        raise BrokerError("epoch stock arrival quote requires replan")
    latest_acct = account()
    latest_positions = positions()
    latest_orders = orders(status="open", limit=500)
    if (latest_orders or len(latest_orders) >= 500
            or latest_acct.get("account_number") != acct.get("account_number")
            or any(latest_acct.get(k) != acct.get(k)
                   for k in ("equity", "cash", "long_market_value"))
            or sorted((p.get("symbol"), p.get("qty"), p.get("market_value"))
                      for p in first_positions)
               != sorted((p.get("symbol"), p.get("qty"), p.get("market_value"))
                         for p in latest_positions)):
        raise BrokerError("epoch stock broker snapshot raced a change")
    try:
        if any(isinstance(acct.get(k), bool) for k in
               ("cash", "equity", "long_market_value")):
            raise ValueError("boolean account economic")
        if any(isinstance(p.get(k), bool) for p in first_positions
               for k in ("qty", "market_value")):
            raise ValueError("boolean position economic")
        cash = float(acct["cash"])
        equity = float(acct["equity"])
        gross = float(acct["long_market_value"])
        held = {p["symbol"]: float(p["qty"]) for p in first_positions}
        marked = {p["symbol"]: float(p["market_value"]) for p in first_positions}
    except (KeyError, TypeError, ValueError) as exc:
        raise BrokerError("epoch stock account economics unreadable") from exc
    tolerance = max(1.0, equity * 0.0005)
    if (not all(math.isfinite(x) for x in (px, cash, equity, gross, *held.values(),
                                           *marked.values()))
            or px <= 0 or cash < 0 or equity <= 0 or gross < 0
            or any(q < 0 for q in held.values())
            or any(v < 0 for v in marked.values())
            or abs(gross - sum(marked.values())) > tolerance
            or abs(equity - cash - gross) > tolerance):
        raise BrokerError("epoch stock account economics do not reconcile")
    if (not isinstance(starting_positions, dict)
            or len(held) != len(first_positions)
            or set(held) != set(starting_positions)
            or any(PE._decimal(p["qty"], "fresh held quantity")
                   != PE._decimal(starting_positions[p["symbol"]], "planned held quantity")
                   for p in first_positions)):
        raise BrokerError("epoch stock holdings changed since durable plan")
    if side == "sell" and held.get(symbol, 0.0) < qty:
        raise BrokerError("epoch stock sell exceeds verified held shares")
    notional = qty * px
    if notional > adv * max_adv_participation:
        raise BrokerError("epoch stock order exceeds fresh ADV capacity")
    current_name_value = held.get(symbol, 0.0) * px
    projected_name_value = current_name_value + (notional if side == "buy" else -notional)
    if side == "buy" and projected_name_value > equity * max_name_frac:
        raise BrokerError("epoch stock buy exceeds fresh per-name cap")
    projected_gross = gross + current_name_value - marked.get(symbol, 0.0)
    projected_gross += notional if side == "buy" else -notional
    projected_values = dict(marked)
    projected_values[symbol] = projected_name_value
    if not isinstance(risk_sigmas, dict) or not isinstance(revision_members, list) \
            or not isinstance(probe_custody_symbols, list):
        raise BrokerError("epoch stock frozen risk context absent")
    if len(revision_members) != 20 or len(set(revision_members)) != 20:
        raise BrokerError("epoch stock revision membership invalid")
    try:
        adverse = 0.0
        for name, value in projected_values.items():
            if value <= 0:
                continue
            sigma_value = risk_sigmas.get(name)
            if isinstance(sigma_value, bool):
                raise ValueError("boolean sigma")
            sigma = float(sigma_value)
            if not math.isfinite(sigma) or sigma <= 0:
                raise ValueError("invalid sigma")
            adverse += value / equity * 3.0 * sigma
    except (TypeError, ValueError) as exc:
        raise BrokerError("epoch stock scenario risk unknown") from exc
    rf_gross = sum(projected_values.get(s, 0.0) for s in revision_members) / equity
    probe_gross = sum(projected_values.get(s, 0.0)
                      for s in set(probe_custody_symbols)) / equity
    if (not math.isfinite(adverse) or adverse > 0.10
            or rf_gross > 0.30 or rf_gross * 0.3203 > 0.10
            or (sleeve in {"PROBE", "PROBE_EXIT"} and probe_gross > 0.20)
            or (sleeve == "EXPLOIT" and side == "buy"
                and projected_name_value > equity * 0.10)):
        raise BrokerError("epoch stock fresh frozen sleeve/scenario risk exceeded")
    if side == "buy" and (notional > cash - equity * minimum_cash_buffer
                          or projected_gross > equity * (1 - minimum_cash_buffer)):
        raise BrokerError("epoch stock buy exceeds verified cash or gross buffer")
    if not bool((clock() or {}).get("is_open")):
        raise BrokerError("epoch stock venue closed")
    body = {"symbol": symbol, "qty": str(qty), "side": side, "type": "market",
            "time_in_force": "day", "client_order_id": client_order_id}
    return body


def held_quantities() -> dict[str, float]:
    return {p["symbol"]: float(p["qty"]) for p in positions()}
