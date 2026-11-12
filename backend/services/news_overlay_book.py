"""CH-14b -- the NEWS RISK-OVERLAY book: a gross scalar on a copy of one book.

WHAT IT IS
==========
An internal paper book (simulation only: no broker, no order, no LLM call) that
holds a COPY of one existing paper book (`NEWS_OVERLAY_BASE_BOOK`) scaled by a
gross-exposure scalar s in [NEWS_OVERLAY_SCALAR_MIN, NEWS_OVERLAY_SCALAR_MAX].
The scalar comes from the world digest's typed theme TONE, by ONE mapping that
was declared in `backend/config.py` before any replay was run
(`NEWS_OVERLAY_MAPPING_DECLARED_UTC`, `NEWS_OVERLAY_MAPPINGS_TRIED`).

Its TWIN is the same book at scalar 1.0: the same names in the same relative
proportions, re-targeted at the same moments, charged at the same cost rate.
At s == 1.0 every session the two NAV lines are identical by construction
(pinned by test), so any difference between them is the overlay and nothing
else.

WHY AN OVERLAY AND NOT A PICKER
===============================
CH-12 (2026-11-12): the hack6 news buys could not be told from matched names
(-0.90%, t -0.80, MDE 6%, 4 calendar blocks), and the world digest names 1-3
article-backed companies per run. It does produce typed themes with tone every
run. So news acts here on HOW MUCH is held, never on WHICH names.

THE FOUR RULES THAT DO NOT RELAX (PRODUCT_EXPERIMENT)
=====================================================
1. No information before it was public: a decision for session t reads only
   digests whose own stamp is strictly before t's decision time
   (`NEWS_OVERLAY_DECISION_ET`, America/New_York); fill = t's close.
2. No target leakage: the mapping reads digest tone only, never a return.
3. Costs never omitted: rates come through `contract.CostModel`, which refuses
   zero costs via `portfolio_farm.Policy`; the overlay pays on its own scalar
   turnover and, scaled, on the base book's rebalances.
4. Frozen once forward: `contract()` hashes the whole rule; `step()` refuses
   to append to a decision file frozen under a different hash.

A stale, empty or baseline-less digest gives scalar 1.0 with a NAMED
degradation on the row, never silently. A missing base book or missing price
input REFUSES (`NewsOverlayRefused`), which the CLI turns into a non-zero exit.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from backend import config as _cfg

LICENCE = "PRODUCT_EXPERIMENT"
SCHEMA = "news_overlay_book/v1"
CONTRACT_NAME = "NEWS_OVERLAY_v1"
ET = ZoneInfo("America/New_York")

#: Degradation names. Every one of them forces scalar 1.0.
NO_DIGEST = "NO_DIGEST_BEFORE_DECISION"
STALE = "STALE_DIGEST"
EMPTY = "EMPTY_DIGEST"
NO_BASELINE = "NO_BASELINE"
DEGRADATIONS = (NO_DIGEST, STALE, EMPTY, NO_BASELINE)


class NewsOverlayRefused(RuntimeError):
    """A required input (base holdings, prices, digest folder) is missing, or the
    decision file is frozen under a different contract. Never a quiet 1.0."""


# ───────────────────────────── the contract ─────────────────────────────────

def params() -> dict:
    return {k: getattr(_cfg, k) for k in (
        "NEWS_OVERLAY_BASE_BOOK", "NEWS_OVERLAY_SCALAR_MIN", "NEWS_OVERLAY_SCALAR_MAX",
        "NEWS_OVERLAY_MIN_THEMES", "NEWS_OVERLAY_BASELINE_N", "NEWS_OVERLAY_BASELINE_MIN",
        "NEWS_OVERLAY_SLOPE", "NEWS_OVERLAY_DEADBAND", "NEWS_OVERLAY_STEP",
        "NEWS_OVERLAY_DECISION_ET", "NEWS_OVERLAY_MAX_AGE_HOURS",
        "NEWS_OVERLAY_COST_BPS_PER_SIDE", "NEWS_OVERLAY_SLIPPAGE_BPS",
        "NEWS_OVERLAY_NOTIONAL_USD", "NEWS_OVERLAY_MAPPING_DECLARED_UTC",
        "NEWS_OVERLAY_MAPPINGS_TRIED")}


def cost_rate() -> float:
    """One-way cost as a fraction of traded notional. Built through
    `contract.CostModel` so the repository's ONE zero-cost refusal fires."""
    from backend.strategy.contract import CostModel
    cm = CostModel(transaction_cost_bps=float(_cfg.NEWS_OVERLAY_COST_BPS_PER_SIDE),
                   slippage_bps=float(_cfg.NEWS_OVERLAY_SLIPPAGE_BPS))
    return (float(cm.transaction_cost_bps) + float(cm.slippage_bps)) / 10_000.0


def contract() -> dict:
    """The frozen rule. Its hash names every decision row."""
    p = params()
    body = {
        "name": CONTRACT_NAME,
        "schema": SCHEMA,
        "licence": f"{LICENCE} (internal simulation only: no broker, no order, no LLM authority)",
        "base_book_id": p["NEWS_OVERLAY_BASE_BOOK"],
        "twin": "the base book at scalar 1.0: identical names, relative weights, re-target moments "
                "and cost rate; only the scalar differs",
        "inputs": {
            "digests": "OPTIMUS_LEDGER_DIR/digest/world_digest_<YYYYMMDDTHHMMSSZ>.json "
                       "(world_digest.out_dir); fields themes[].tone.fear_greed and "
                       "themes[].tone.n_independent_sources; dry runs ignored",
            "base_holdings": "DATA_DIR/aegis_pi.db paper_positions (shares, opened_at, closed_at) "
                             "+ paper_book_decisions (asof_date, decided_utc) for base_book_id",
            "prices": "OPTIMUS_LEDGER_DIR/prices_2025_26/bars.parquet close",
        },
        "mapping": ("F = sum_i n_i * fear_greed_i / sum_i n_i over themes with numeric "
                    "tone.fear_greed, n_i = max(1, n_independent_sources); fewer than MIN_THEMES "
                    "-> EMPTY. B = median F over the previous BASELINE_N valid digests stamped "
                    "strictly before this digest; fewer than BASELINE_MIN -> NO_BASELINE. "
                    "d = F - B; raw = 1 - SLOPE * max(0, -d - DEADBAND); scalar = clip("
                    "round(raw / STEP) * STEP, SCALAR_MIN, SCALAR_MAX). Any degradation -> 1.0."),
        "timing": ("decision time = DECISION_ET America/New_York on session t; read only digests "
                   "stamped strictly before it; newest older than MAX_AGE_HOURS -> STALE; fill = "
                   "close of t (the next close after the digest's own stamp); the scalar earns "
                   "close t -> close t+1"),
        "rebalance": ("a book re-targets at a session close only when its scalar changed or the "
                      "base book's holdings changed; otherwise it holds its shares"),
        "costs": ("one-way rate = (COST_BPS_PER_SIDE + SLIPPAGE_BPS) / 1e4 on every traded dollar, "
                  "including the overlay's own scalar turnover; cash earns 0"),
        "objective": ("terminal NAV of the overlay vs its twin under the BALANCED personality "
                      "(same notional, same costs); read daily, by date block, raw lines first"),
        "params": p,
    }
    body["policy_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return body


# ───────────────────────────── digest state ─────────────────────────────────

def parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def tone_score(themes: Sequence[Mapping]) -> tuple[Optional[float], int]:
    """(F, n_toned): the source-weighted mean fear_greed, or None when fewer
    than MIN_THEMES themes carry a numeric tone."""
    num, den, n = 0.0, 0.0, 0
    for th in themes or ():
        tone = (th or {}).get("tone") or {}
        fg = tone.get("fear_greed")
        if not isinstance(fg, (int, float)) or isinstance(fg, bool) or not math.isfinite(fg):
            continue
        w = max(1.0, float(tone.get("n_independent_sources") or th.get("n_independent_sources") or 1))
        num += w * float(fg)
        den += w
        n += 1
    if n < int(_cfg.NEWS_OVERLAY_MIN_THEMES) or den <= 0:
        return None, n
    return num / den, n


def digest_summary(d: Mapping) -> Optional[dict]:
    """The only fields the overlay reads from one digest JSON."""
    stamp = d.get("stamp")
    if not stamp or d.get("dry_run"):
        return None
    try:
        stamped = parse_stamp(str(stamp))
    except ValueError:
        return None
    themes = d.get("themes") or []
    f, n = tone_score(themes)
    return {"digest_id": str(stamp), "stamped_utc": stamped, "F": f, "n_toned": n,
            "n_themes": len(themes)}


def load_digests(digest_dir: Path) -> list[dict]:
    """Every non-dry world digest in `digest_dir`, oldest first. A missing
    folder REFUSES: an overlay with no digest folder would read as 'no news'."""
    p = Path(digest_dir)
    if not p.is_dir():
        raise NewsOverlayRefused(f"no digest folder at {p}; refusing rather than reading 'no news'")
    out = []
    for fp in sorted(p.glob("world_digest_*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        s = digest_summary(d) if isinstance(d, dict) else None
        if s:
            out.append(s)
    out.sort(key=lambda r: r["stamped_utc"])
    return out


def decision_time(session: date) -> datetime:
    hh, mm = (int(x) for x in str(_cfg.NEWS_OVERLAY_DECISION_ET).split(":"))
    return datetime.combine(session, time(hh, mm), tzinfo=ET).astimezone(timezone.utc)


def map_scalar(d: float) -> tuple[float, float]:
    """(raw, scalar) for a tone deviation d = F - baseline."""
    raw = 1.0 - float(_cfg.NEWS_OVERLAY_SLOPE) * max(0.0, -float(d) - float(_cfg.NEWS_OVERLAY_DEADBAND))
    step = float(_cfg.NEWS_OVERLAY_STEP)
    q = round(raw / step) * step
    s = min(float(_cfg.NEWS_OVERLAY_SCALAR_MAX), max(float(_cfg.NEWS_OVERLAY_SCALAR_MIN), q))
    return raw, round(s, 6)


def compute_scalar(digests: Sequence[Mapping], decision_utc: datetime) -> dict:
    """The scalar for one decision, from digests stamped STRICTLY before it."""
    seen = [g for g in digests if g["stamped_utc"] < decision_utc]
    out: dict[str, Any] = {"decision_utc": decision_utc.isoformat(timespec="seconds"),
                           "scalar": 1.0, "raw": None, "F": None, "baseline": None, "d": None,
                           "digest_id": None, "digest_stamped_utc": None, "degradation": None,
                           "n_digests_visible": len(seen), "n_baseline": 0}
    if not seen:
        out["degradation"] = NO_DIGEST
        return out
    g = max(seen, key=lambda r: r["stamped_utc"])
    out.update({"digest_id": g["digest_id"],
                "digest_stamped_utc": g["stamped_utc"].isoformat(timespec="seconds"),
                "F": g["F"], "n_toned": g["n_toned"]})
    age_h = (decision_utc - g["stamped_utc"]).total_seconds() / 3600.0
    out["digest_age_hours"] = round(age_h, 2)
    if age_h > float(_cfg.NEWS_OVERLAY_MAX_AGE_HOURS):
        out["degradation"] = STALE
        return out
    if g["F"] is None:
        out["degradation"] = EMPTY
        return out
    prior = [r["F"] for r in seen if r["stamped_utc"] < g["stamped_utc"] and r["F"] is not None]
    prior = prior[-int(_cfg.NEWS_OVERLAY_BASELINE_N):]
    out["n_baseline"] = len(prior)
    if len(prior) < int(_cfg.NEWS_OVERLAY_BASELINE_MIN):
        out["degradation"] = NO_BASELINE
        return out
    b = statistics.median(prior)
    d = float(g["F"]) - float(b)
    raw, s = map_scalar(d)
    out.update({"baseline": round(b, 6), "d": round(d, 6), "raw": round(raw, 6), "scalar": s})
    return out


# ───────────────────────────── the step ─────────────────────────────────────

def decisions_path(root: Optional[Path] = None) -> Path:
    return (Path(root) if root else Path(_cfg.OPTIMUS_LEDGER_DIR)) / "news_overlay_book" / "decisions.jsonl"


def step(session: date, *, digests: Sequence[Mapping], base_weights: Mapping[str, float],
         prev_scalar: Optional[float] = None, enabled: Optional[bool] = None,
         out_path: Optional[Path] = None, write: bool = True, label: str = "FORWARD") -> dict:
    """One decision row for `session`. Writes only when the flag is ON and
    `write` is True; with the flag OFF it computes and writes NOTHING."""
    if not base_weights:
        raise NewsOverlayRefused(f"no base-book holdings for {session}: an overlay on nothing "
                                 f"would grade as flat")
    on = bool(_cfg.NEWS_OVERLAY_BOOK_ENABLED if enabled is None else enabled)
    c = contract()
    sc = compute_scalar(digests, decision_time(session))
    g = sum(float(w) for w in base_weights.values())
    prev = 1.0 if prev_scalar is None else float(prev_scalar)
    row = {"schema": SCHEMA, "label": label, "session": session.isoformat(),
           "policy_hash": c["policy_hash"], "base_book_id": c["base_book_id"], **sc,
           "prev_scalar": prev, "base_gross": round(g, 6),
           "overlay_gross": round(g * sc["scalar"], 6),
           "scalar_turnover_frac": round(abs(sc["scalar"] - prev) * g, 6),
           "est_scalar_cost_frac": round(abs(sc["scalar"] - prev) * g * cost_rate(), 8),
           "n_names": len(base_weights), "fill": f"close of {session.isoformat()}",
           "flag_enabled": on, "written": False}
    if on and write:
        p = Path(out_path) if out_path else decisions_path()
        _refuse_foreign_contract(p, c["policy_hash"])
        p.parent.mkdir(parents=True, exist_ok=True)
        row["written"] = True
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row


def _refuse_foreign_contract(p: Path, policy_hash: str) -> None:
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h = json.loads(line).get("policy_hash")
        if h and h != policy_hash:
            raise NewsOverlayRefused(f"{p} is frozen under policy {h}; this rule hashes to "
                                     f"{policy_hash}. A changed rule is NEWS_OVERLAY_v2, a new file.")
        return


# ───────────────────────────── the simulation ───────────────────────────────

@dataclass
class Book:
    cash: float
    shares: dict

    def value(self, px: Mapping[str, float]) -> float:
        return self.cash + sum(n * px[t] for t, n in self.shares.items())


def simulate(sessions: Sequence[date], prices: Mapping[date, Mapping[str, float]],
             base_weights: Mapping[date, Mapping[str, float]], base_changed: Mapping[date, bool],
             scalars: Mapping[date, float], *, notional: Optional[float] = None) -> dict:
    """Mark the overlay and its twin over `sessions`.

    At each session close (the fill), a book re-targets to scalar x base weights
    of its own NAV when its scalar changed or the base holdings changed (and on
    the first session); otherwise it holds. Costs on every traded dollar. The
    twin is the same procedure with scalar 1.0 throughout."""
    if not sessions:
        raise NewsOverlayRefused("no sessions to simulate")
    rate = cost_rate()
    nav0 = float(_cfg.NEWS_OVERLAY_NOTIONAL_USD if notional is None else notional)
    books = {"overlay": Book(nav0, {}), "twin": Book(nav0, {})}
    last_s = {"overlay": None, "twin": None}
    rows = []
    for t in sessions:
        px = prices.get(t)
        w = base_weights.get(t)
        if px is None or not w:
            raise NewsOverlayRefused(f"missing prices or base weights on {t}")
        missing = [s for s in w if s not in px]
        if missing:
            raise NewsOverlayRefused(f"no close on {t} for {missing[:5]}")
        rec: dict[str, Any] = {"session": t.isoformat(), "scalar": float(scalars.get(t, 1.0))}
        twin_pre = None
        for name in ("twin", "overlay"):              # twin first: the overlay copies it
            bk = books[name]
            s = rec["scalar"] if name == "overlay" else 1.0
            for sym in list(bk.shares):
                if sym not in px:
                    raise NewsOverlayRefused(f"no close on {t} for held {sym}")
            pre = bk.value(px)
            traded, cost = 0.0, 0.0
            if last_s[name] is None or s != last_s[name] or base_changed.get(t, False):
                if name == "twin":
                    twin_pre = pre
                    target = {sym: float(wt) * pre / px[sym] for sym, wt in w.items()}
                else:
                    # The overlay holds the TWIN's exact shares, scaled: same names,
                    # same relative weights, so the scalar is the only difference.
                    tw = books["twin"]
                    tw_pre = twin_pre if twin_pre is not None else tw.value(px)
                    target = {sym: s * n * pre / tw_pre for sym, n in tw.shares.items()}
                for sym in set(target) | set(bk.shares):
                    traded += abs(target.get(sym, 0.0) - bk.shares.get(sym, 0.0)) * px[sym]
                cost = traded * rate
                bk.cash = pre - sum(n * px[sym] for sym, n in target.items()) - cost
                bk.shares = target
                last_s[name] = s
            post = bk.value(px)
            rec[f"{name}_nav"] = post
            rec[f"{name}_traded"] = traded
            rec[f"{name}_cost"] = cost
            rec[f"{name}_gross"] = (post - bk.cash) / post if post else 0.0
        rows.append(rec)
    for i, r in enumerate(rows):
        for name in books:
            prev = nav0 if i == 0 else rows[i - 1][f"{name}_nav"]
            r[f"{name}_ret"] = r[f"{name}_nav"] / prev - 1.0
    return {"rows": rows, "cost_rate": rate, "notional": nav0,
            "holdings_last": {k: dict(v.shares) for k, v in books.items()}}


__all__ = ["NewsOverlayRefused", "contract", "params", "cost_rate", "tone_score", "digest_summary",
           "load_digests", "decision_time", "map_scalar", "compute_scalar", "step", "simulate",
           "decisions_path", "DEGRADATIONS", "NO_DIGEST", "STALE", "EMPTY", "NO_BASELINE"]
