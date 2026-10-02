"""Contest ORDER SHEET: the desk's ranking turned into tickets a human types into TMSG.

The owner enters every order into the Bloomberg Terminal by hand. This module makes the
sheet hard to mistype and easy to check:

* one line per ticket: Terminal ticker WITH exchange code (``UNH US Equity``), side, quantity
  in SHARES (computed from the contest capital, rounded down to the board lot), a limit, the
  notional at the limit, and the session it is for (Hong Kong AND New York time);
* a control block the owner can check on the blotter after entry: number of lines, total
  shares per side, total notional, and an 8-character SHEET CODE;
* ``verify``: paste the Terminal blotter back and every missing ticket, wrong quantity
  (including a slipped zero), flipped side or mistyped ticker is printed.

Also the pre-trade checks the dress rehearsal drills: share classes of one issuer, bar-defect
flags, the 20% cap at the limit price and under drift, a split between sheet and fill.

Nothing here places an order or sends anything. PRODUCT_EXPERIMENT; family of one.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import zlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from scripts import contest_calendar as cc

try:                                            # parameters live in backend/config.py
    from backend import config as _cfg          # noqa: WPS433
except Exception:                               # noqa: BLE001
    _cfg = None


def _c(name: str, default: Any) -> Any:
    return getattr(_cfg, name, default) if _cfg is not None else default


NOTIONAL_USD = float(_c("CONTEST_NOTIONAL_USD", 1_000_000.0))
CAP = float(_c("CONTEST_POSITION_CAP", 0.20))
LIMIT_BAND = float(_c("CONTEST_BUY_LIMIT_BAND", 0.05))
SPLIT_GUARD = float(_c("CONTEST_SPLIT_GUARD", 0.30))
DEFECT_LOOKBACK_DAYS = int(_c("CONTEST_DEFECT_LOOKBACK_DAYS", 730))
NY = "America/New_York"

# Board lots as the builder knows them. UNVERIFIED unless the Terminal (or TMSG) confirms; HK lots
# differ per stock (None = look it up on the Terminal before entering).
LOTS = {"US": 1, "EU": 1, "JP": 100, "CN": 100, "ID": 100, "TW": 1000, "KR": 1, "IN": 1, "HK": None}

# Known multi-class US issuers (one earnings report, two tickers). Name normalisation catches most
# of the rest; this list catches the ones whose names differ.
MULTI_CLASS = [("GOOGL", "GOOG"), ("BRK-B", "BRK-A"), ("FOXA", "FOX"), ("NWSA", "NWS"), ("LBRDK", "LBRDA"),
               ("UAA", "UA"), ("BF-B", "BF-A"), ("LEN", "LEN-B"), ("HEI", "HEI-A"), ("Z", "ZG"),
               ("MOG-A", "MOG-B"), ("GEF", "GEF-B"), ("CWEN", "CWEN-A"), ("RUSHA", "RUSHB"), ("BIO", "BIO-B"),
               ("LILA", "LILAK"), ("FWONA", "FWONK"), ("MKC", "MKC-V"), ("STZ", "STZ-B"), ("DISCA", "DISCK"),
               ("LSXMA", "LSXMK"), ("BATRA", "BATRK"), ("LEN", "LENB"), ("CMCSA", "CMCSK"), ("PBR", "PBR-A"),
               ("VALE", "VALE3"), ("QRTEA", "QRTEB"), ("GTN", "GTN-A"), ("HVT", "HVT-A"), ("KELYA", "KELYB")]
_NAME_DROP = re.compile(r"\b(class|cl|series|ser|ordinary|shares?|common|stock|inc|incorporated|corp|corporation|"
                        r"co|company|ltd|limited|plc|holdings?|group|the|sa|ag|nv|se|ab|asa|oyj|spa|pref|preferred|"
                        r"prf|non[- ]?voting|voting|npv|adr|ads|reit|trust|tbk|pt|kk|bhd|[a-c])\b")


class OrderRefused(ValueError):
    """A ticket that would break a contest rule or cannot be priced."""


# ───────────────────────────── issuers and flags ─────────────────────────────

def issuer_key(symbol: str, name: Optional[str] = None) -> str:
    """One key per issuer: known multi-class pairs first, then the normalised company name."""
    s = str(symbol).upper()
    for grp in MULTI_CLASS:
        if s in grp:
            return "MC:" + grp[0]
    if name and isinstance(name, str) and name.strip():
        n = name.lower().replace("&", " and ")
        n = re.sub(r"[^a-z0-9 ]", " ", n)
        n = _NAME_DROP.sub(" ", n)
        n = re.sub(r"\s+", " ", n).strip()
        if len(n) >= 3:
            return "NM:" + n
    base = re.sub(r"[-./].*$", "", s)
    return "SY:" + base


def dedupe_issuers(ranked: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the best-ranked line of each issuer. `ranked` is in rank order (symbol, name?)."""
    if ranked.empty:
        return ranked, ranked.iloc[0:0]
    names = ranked["name"] if "name" in ranked.columns else pd.Series([None] * len(ranked), index=ranked.index)
    keys = [issuer_key(s, n) for s, n in zip(ranked.symbol, names)]
    r = ranked.assign(issuer=keys)
    first = r.drop_duplicates("issuer", keep="first")
    dup = r[~r.index.isin(first.index)].copy()
    if len(dup):
        keep_sym = dict(zip(first.issuer, first.symbol))
        dup["refusal"] = [f"REFUSED_SAME_ISSUER_AS {keep_sym[k]}" for k in dup.issuer]
    return first, dup


def latest_defects(folder: Optional[Path] = None) -> dict:
    """{symbol: reason} from the newest bar_defects receipt (US bars only; read-only)."""
    folder = Path(folder) if folder is not None else cc.OPT / "bar_defects"
    files = sorted(folder.glob("bar_defects_*.json")) if folder.exists() else []
    if not files:
        return {}
    d = json.loads(files[-1].read_text(encoding="utf-8"))
    out: dict = {"_file": files[-1].name}
    ds = d.get("defect_screen", {}) or {}
    for c in ds.get("cuts", []) or []:
        out.setdefault(c.get("symbol"), []).append(("CUT", c.get("first_after") or c.get("last_before")))
    for c in ds.get("suspects", []) or []:
        out.setdefault(c.get("symbol"), []).append(("SUSPECT", c.get("date")))
    for c in ds.get("spikes", []) or []:
        out.setdefault(c.get("symbol"), []).append(("SPIKE", c.get("end") or c.get("start")))
    for s in (d.get("stitched", {}) or {}).get("defect_cut_symbols", []) or []:
        out.setdefault(s, []).append(("DEFECT_CUT", None))
    return out


def defect_flag(symbol: str, asof: Any, defects: dict, lookback_days: int = DEFECT_LOOKBACK_DAYS) -> Optional[str]:
    """A reason string when a defect sits inside the window the trailing features read."""
    rows = defects.get(str(symbol).upper()) or defects.get(str(symbol))
    if not rows:
        return None
    lo = pd.Timestamp(asof) - pd.Timedelta(days=lookback_days)
    for kind, when in rows:
        if when is None or pd.isna(pd.Timestamp(when)) or pd.Timestamp(when) >= lo:
            return f"REFUSED_DEFECT_FLAGGED ({kind} {when or ''} in {defects.get('_file', 'bar_defects')})".strip()
    return None


# ───────────────────────────── sizing ─────────────────────────────

def lot_size(symbol: str) -> Optional[int]:
    return LOTS.get(cc.market_of(symbol), 1)


def cap_usd(nav_usd: float, *, notional_usd: float = NOTIONAL_USD, cap: float = CAP) -> dict:
    """The position cap under both readings of the rule; the SHEET uses the smaller one.

    T&C (2021-2025 wording): "No single position ... greater than 20% of the notional amount".
    Reading A: 20% of the $1M notional ($200k fixed). Reading B: 20% of current NAV."""
    a, b = cap * notional_usd, cap * nav_usd
    return {"of_notional": a, "of_nav": b, "binding": min(a, b),
            "binding_reading": "20% of notional" if a <= b else "20% of current NAV"}


def size_ticket(ref_local: float, fx_local_per_usd: float, budget_usd: float, lot: Optional[int],
                band: float = LIMIT_BAND) -> dict:
    """Shares so that notional AT THE LIMIT is <= budget: a gap up to the limit cannot breach the cap."""
    if not (np.isfinite(ref_local) and ref_local > 0 and np.isfinite(fx_local_per_usd) and fx_local_per_usd > 0):
        raise OrderRefused("no reference price")
    limit_local = round_price(ref_local * (1 + band))
    limit_usd = limit_local / fx_local_per_usd
    q = math.floor(budget_usd / limit_usd)
    step = lot or 1
    q = (q // step) * step
    if q <= 0:
        raise OrderRefused(f"one board lot ({step}) at the limit exceeds the budget")
    return {"qty": int(q), "limit_local": limit_local, "notional_usd_at_limit": round(q * limit_usd, 2),
            "notional_usd_at_ref": round(q * ref_local / fx_local_per_usd, 2), "lot": lot,
            "lot_status": "CHECK BOARD LOT ON TERMINAL" if lot is None else ("1" if step == 1 else f"{step} (UNVERIFIED)")}


def round_price(p: float) -> float:
    if p >= 1000:
        return float(round(p, 0))
    if p >= 10:
        return float(round(p, 2))
    return float(round(p, 4))


# ───────────────────────────── the sheet ─────────────────────────────

@dataclass
class Ticket:
    n: int
    side: str                      # BUY / SELL
    bbg: str                       # '<TICKER> <EXCH> Equity'
    symbol: str
    market: str
    qty: int
    order_type: str                # 'LIMIT' / 'MARKET AT OPEN'
    limit_local: Optional[float]
    currency: str
    session_date: str              # the local session the ticket is for
    open_utc: str
    open_hkt: str
    open_ny: str
    notional_usd: float
    status: str = "LIVE"           # LIVE / VOID_LATE / OVERDUE
    note: str = ""
    report: str = ""
    code: str = ""
    extra: dict = field(default_factory=dict)


_ALPH = "ACDEFHJKMNPRTUVWXY34679"


def line_code(side: str, bbg: str, qty: int) -> str:
    """Two characters that change when the side, the ticker or the quantity changes."""
    v = zlib.crc32(f"{side.upper()}|{norm_bbg(bbg)}|{int(qty)}".encode()) & 0xFFFF
    return _ALPH[v % len(_ALPH)] + _ALPH[(v // len(_ALPH)) % len(_ALPH)]


def norm_bbg(bbg: str) -> str:
    s = re.sub(r"\s+EQUITY$", "", str(bbg).upper().strip())
    return re.sub(r"\s+", " ", s)


def session_open_utc(symbol: str, day: Any) -> pd.Timestamp:
    tz, o, _ = cc.session_hours(symbol)
    h, m = map(int, o.split(":"))
    d = pd.Timestamp(day)
    return pd.Timestamp(datetime(d.year, d.month, d.day, h, m), tz=tz).tz_convert("UTC")


def code_of(lines: Iterable[tuple]) -> str:
    """Order-independent 8-character code of (side, ticker, qty) triples."""
    canon = "\n".join(sorted(f"{sd}|{norm_bbg(b)}|{int(q) if q is not None else -1}" for sd, b, q in lines))
    return hashlib.sha256(canon.encode()).hexdigest()[:8].upper()


def sheet_code(tickets: Iterable[Ticket]) -> str:
    return code_of((t.side, t.bbg, t.qty) for t in tickets if t.status != "VOID_LATE")


def control_block(tickets: list[Ticket]) -> dict:
    live = [t for t in tickets if t.status != "VOID_LATE"]
    buys = [t for t in live if t.side == "BUY"]
    sells = [t for t in live if t.side == "SELL"]
    return {"n_lines": len(live), "n_buy": len(buys), "n_sell": len(sells),
            "buy_shares": int(sum(t.qty for t in buys)), "sell_shares": int(sum(t.qty for t in sells)),
            "buy_notional_usd": round(float(sum(t.notional_usd for t in buys)), 2),
            "sheet_code": sheet_code(tickets)}


def render(tickets: list[Ticket], *, day: str, nav_usd: float, cap: dict, freeze_utc: str,
           header: list[str] | None = None) -> tuple[str, str]:
    """(markdown, one-line text). SELL first, then BUY in opening order."""
    cb = control_block(tickets)
    L = [f"# ORDER SHEET {day}  (frozen {freeze_utc} UTC)", ""]
    L += header or []
    L += ["", f"NAV used for sizing: ${nav_usd:,.0f}. Position budget: ${cap['binding']:,.0f} "
              f"({cap['binding_reading']}; the other reading allows ${max(cap['of_notional'], cap['of_nav']):,.0f}). "
              f"Buy limits are {LIMIT_BAND:.0%} above the last close so the notional AT THE LIMIT stays under the cap.",
          "", "Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY "
              f"ticket is above ${cap['binding']:,.0f}, the quantity is wrong: stop and re-read the line.", ""]
    late = [t for t in tickets if t.status == "VOID_LATE"]
    if late:
        L += [f"**LATE SHEET: {len(late)} line(s) are VOID** -- their session opened before this sheet was frozen. "
              "Do NOT enter them. They are listed at the bottom for the record.", ""]
    for side in ("SELL", "BUY"):
        rows = [t for t in tickets if t.side == side and t.status != "VOID_LATE"]
        L += [f"## {side} ({len(rows)})", ""]
        if not rows:
            L += ["- none", ""]
            continue
        L += ["| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in sorted(rows, key=lambda x: x.open_utc):
            lim = "" if t.limit_local is None else f"{t.limit_local:,}"
            L.append(f"| {t.n} | **{t.bbg}** | {t.side} | **{t.qty:,}** | {t.order_type} | {lim} | {t.currency} "
                     f"| {t.notional_usd:,.0f} | {t.open_hkt} / {t.open_ny} | {t.code} | {t.status}{'; ' + t.note if t.note else ''} |")
        L.append("")
    L += ["## CONTROL (check on the blotter after entering)", "",
          f"- lines: **{cb['n_lines']}** ({cb['n_sell']} SELL, {cb['n_buy']} BUY)",
          f"- total SELL shares: **{cb['sell_shares']:,}**; total BUY shares: **{cb['buy_shares']:,}**",
          f"- total BUY notional at the limits: **${cb['buy_notional_usd']:,.0f}** (never above "
          f"${cap['binding'] * max(1, cb['n_buy']):,.0f})",
          f"- SHEET CODE: **{cb['sheet_code']}**. Paste the blotter into "
          f"`python -m scripts.contest_rehearsal verify --date {day} --entered <file>`: it must print the same code.",
          ""]
    if late:
        L += ["## VOID (late; never enter)", ""]
        for t in late:
            L.append(f"- {t.side} {t.bbg} {t.qty:,} -- session opened {t.open_hkt} HKT, before the freeze")
        L.append("")
    md = "\n".join(L) + "\n"
    live = [t for t in tickets if t.status != "VOID_LATE"]
    short = (f"ORDERS {day} [{cb['sheet_code']}]: "
             + ("; ".join(f"{t.side} {norm_bbg(t.bbg)} {t.qty:,}" for t in sorted(live, key=lambda x: (x.side != 'SELL', x.open_utc)))
                or "no tickets")
             + f". Control: {cb['n_lines']} lines, BUY shares {cb['buy_shares']:,}, SELL shares {cb['sell_shares']:,}.")
    return md, short


# ───────────────────────────── verify (manual entry) ─────────────────────────────

_SIDE = {"BUY": "BUY", "B": "BUY", "BOT": "BUY", "BOUGHT": "BUY", "SELL": "SELL", "S": "SELL", "SLD": "SELL",
         "SOLD": "SELL"}


def parse_blotter(text: str) -> list[dict]:
    """Tolerant parser: one ticket per line, any order of '<side> <ticker> <exch> [Equity] <qty>'."""
    out = []
    for raw in str(text).splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        prev = None
        while prev != ln:                                  # 1,200 -> 1200 (thousands separators)
            prev, ln = ln, re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", ln)
        toks = [t for t in re.split(r"[,\t;|]+|\s+", ln.upper()) if t]
        side = next((_SIDE[t] for t in toks if t in _SIDE), None)
        nums = [t for t in toks if re.fullmatch(r"\d[\d,]*", t)]
        qty = int(nums[-1].replace(",", "")) if nums else None
        rest = [t for t in toks if t not in _SIDE and t != "EQUITY" and not re.fullmatch(r"\d[\d,]*(\.\d+)?", t)]
        if len(rest) >= 2 and re.fullmatch(r"[A-Z]{2}", rest[1] or ""):
            bbg = f"{rest[0]} {rest[1]}"
        elif rest:
            bbg = rest[0]
        else:
            bbg = ""
        # a numeric ticker (HK/JP/KR/TW) is the first number when two numbers are present
        if len(nums) >= 2 and not rest[:1]:
            bbg = nums[0]
        elif len(nums) >= 2 and len(rest) >= 1 and re.fullmatch(r"[A-Z]{2}", rest[0]):
            bbg = f"{nums[0]} {rest[0]}"
        out.append({"raw": raw, "side": side, "bbg": norm_bbg(bbg), "qty": qty})
    return out


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def verify(expected: list[Ticket], entered_text: str) -> dict:
    """Compare what was typed with the frozen sheet. Returns {ok, problems[], sheet_code_entered}."""
    exp = {(t.side, norm_bbg(t.bbg)): t for t in expected if t.status != "VOID_LATE"}
    got = parse_blotter(entered_text)
    problems, seen = [], set()
    for g in got:
        key = (g["side"], g["bbg"])
        if key in exp:
            seen.add(key)
            t = exp[key]
            if g["qty"] != t.qty:
                kind = "QTY_MISMATCH"
                q, e = g["qty"], t.qty
                if q and e and (q in (e * 10, e * 100) or e in (q * 10, q * 100)):
                    kind = "QTY_SLIPPED_ZERO"
                elif q and sorted(str(q)) == sorted(str(e)):
                    kind = "QTY_TRANSPOSED_DIGITS"
                problems.append({"kind": kind, "ticker": t.bbg, "side": t.side, "expected": t.qty, "entered": g["qty"]})
            continue
        flip = ("SELL" if g["side"] == "BUY" else "BUY", g["bbg"])
        if flip in exp:
            seen.add(flip)
            problems.append({"kind": "SIDE_FLIPPED", "ticker": g["bbg"], "expected": flip[0], "entered": g["side"]})
            continue
        root = [k for k in exp if k[0] == g["side"] and k not in seen and " " not in g["bbg"]
                and k[1].split(" ")[0] == g["bbg"]]
        if root:
            k = root[0]
            seen.add(k)
            problems.append({"kind": "EXCHANGE_CODE_MISSING", "expected": exp[k].bbg, "entered": g["raw"].strip()})
            if g["qty"] != exp[k].qty:
                problems.append({"kind": "QTY_MISMATCH", "ticker": exp[k].bbg, "side": g["side"],
                                 "expected": exp[k].qty, "entered": g["qty"]})
            continue
        near = sorted(((_lev(g["bbg"], k[1]), k) for k in exp if k[0] == g["side"] and k not in seen))
        if near and near[0][0] <= 2:
            k = near[0][1]
            seen.add(k)
            problems.append({"kind": "TICKER_TYPO", "expected": exp[k].bbg, "entered": g["raw"].strip()})
            continue
        problems.append({"kind": "UNEXPECTED_TICKET", "entered": g["raw"].strip()})
    for k, t in exp.items():
        if k not in seen:
            problems.append({"kind": "MISSING_TICKET", "ticker": t.bbg, "side": t.side, "qty": t.qty})
    entered_code = code_of((g["side"] or "?", g["bbg"], g["qty"]) for g in got)
    return {"ok": not problems, "problems": problems, "n_entered": len(got), "n_expected": len(exp),
            "sheet_code_expected": sheet_code(expected), "sheet_code_entered": entered_code}


# ───────────────────────────── at-the-fill checks ─────────────────────────────

SPLIT_RATIOS = (1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 20, 2 / 3, 3 / 2, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 20.0)


def split_check(ref_price: float, live_price: float, guard: float = SPLIT_GUARD) -> dict:
    """Terminal price vs the sheet's reference. Beyond the guard: a split/consolidation or a gap."""
    if not (ref_price and live_price and np.isfinite(ref_price) and np.isfinite(live_price)):
        return {"verdict": "NO_PRICE", "action": "do not enter: no price to check against"}
    r = live_price / ref_price
    if abs(r - 1) <= guard:
        return {"verdict": "OK", "ratio": round(r, 4), "action": "enter as printed"}
    near = min(SPLIT_RATIOS, key=lambda x: abs(math.log(r / x)))
    if abs(math.log(r / near)) < 0.03:
        return {"verdict": "SPLIT_SUSPECT", "ratio": round(r, 4), "split_ratio": round(near, 4),
                "action": (f"price is {r:.2f}x the sheet's: check CACS for a split. If confirmed, SHARES = "
                           f"sheet shares / {near:.4g} (same dollars); the limit scales the same way")}
    return {"verdict": "GAP", "ratio": round(r, 4),
            "action": "price moved beyond the guard with no split ratio: SKIP the ticket (the limit protects a buy)"}


def drift_check(positions: pd.DataFrame, nav_usd: float, *, notional_usd: float = NOTIONAL_USD,
                cap: float = CAP) -> pd.DataFrame:
    """positions: symbol, qty, price_usd. Flags market value above the cap under both readings.

    The desk's holds last one or two sessions, so drift is transient; whether a breach by drift
    must be traded away is an OWNER-CONFIRM rule (T&C: 'No single position held ... may be
    greater than 20% of the notional amount')."""
    p = positions.copy()
    p["mv_usd"] = p.qty * p.price_usd
    p["pct_nav"] = p.mv_usd / nav_usd
    p["over_nav_cap"] = p.pct_nav > cap + 1e-9
    p["over_notional_cap"] = p.mv_usd > cap * notional_usd + 1e-6
    lim = np.minimum(cap * nav_usd, cap * notional_usd)
    p["trim_shares_if_at_all_times"] = np.where(p.mv_usd > lim, np.ceil((p.mv_usd - lim) / p.price_usd), 0).astype(int)
    return p


def to_json(tickets: list[Ticket]) -> list[dict]:
    return [asdict(t) for t in tickets]


def from_json(rows: list[dict]) -> list[Ticket]:
    return [Ticket(**r) for r in rows]


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))
