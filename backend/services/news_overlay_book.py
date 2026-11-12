"""CH-14b -- the NEWS RISK-OVERLAY book: a gross scalar on a copy of one book.

WHAT IT IS
==========
An internal paper book (simulation only: no broker, no order, no LLM call) that
holds a COPY of one base (v3: LIQUID-RANDOM-50, a seeded monthly random draw of
50 liquid names derived from the bars panel; SPY alone for comparison) scaled by a
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
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from backend import config as _cfg

LICENCE = "PRODUCT_EXPERIMENT"
SCHEMA = "news_overlay_book/v3"
CONTRACT_NAME = "NEWS_OVERLAY_v3"
ET = ZoneInfo("America/New_York")

#: Degradation names. Every one of them forces scalar 1.0.
NO_DIGEST = "NO_DIGEST_BEFORE_DECISION"
STALE = "STALE_DIGEST"
EMPTY = "EMPTY_DIGEST"
NO_BASELINE = "NO_BASELINE"
NO_DECISION_ROW = "NO_DECISION_ROW"       # grade: a session with no forward row -> 1.0
STALE_BASE = "STALE_BASE_BARS"            # v3: too much base weight on stale bars -> REFUSED at 1.0
DEGRADATIONS = (NO_DIGEST, STALE, EMPTY, NO_BASELINE, NO_DECISION_ROW, STALE_BASE)
#: Row labels. Only FORWARD rows are graded; BACKDATED (a --date other than
#: today's ET session) and BACKFILL (the replay) never are.
FORWARD, BACKDATED, BACKFILL = "FORWARD", "BACKDATED", "BACKFILL"

#: The contracts this one replaced, with the reason. Kept IN the contract.
HISTORY = (
    {"name": "NEWS_OVERLAY_v1", "policy_hash": "ce686058847fdbc7",
     "declared_utc": "2026-11-12T09:13:00+00:00", "replay_run": "20261112T091714Z",
     "superseded_because": ("review of PR #125: the baseline's age was unbounded (on 2026-11-10 "
                            "the baseline was 12 digests from 2026-10-12..14); a session with no "
                            "decision row held the last scalar instead of 1.0; the forward step "
                            "dated sessions by the machine's local date; early closes were not "
                            "handled. v1 was never seeded and has no forward rows.")},
    {"name": "NEWS_OVERLAY_v2", "policy_hash": "2d85fa126b83f4ac",
     "declared_utc": "2026-11-12T09:28:00+00:00", "replay_run": "20261112T093355Z",
     "superseded_because": ("its base book:9d62cc74239b435d (a random 50 from the $3M+ band) was "
                            "unreadable: 30 of 32 replay days DEGRADED on stale base bars (HLX 22 "
                            "days without a bar), a 70% one-day move, and a probable unadjusted 2:1 "
                            "split (XP) as the largest single-name loss. The brain session decided "
                            "not to seed on it. v3 keeps the mapping and changes the base. v2 was "
                            "never seeded and has no forward rows.")},
)


class NewsOverlayRefused(RuntimeError):
    """A required input (base holdings, prices, digest folder) is missing, or the
    decision file is frozen under a different contract. Never a quiet 1.0."""


#: v3's base, in words. The parameters it names are in `params()` (and so in the hash).
BASE_DEFINITION = (
    "LIQUID-RANDOM-50, derived from the bars panel, never stored. Draw date D = the first XNYS "
    "session of each calendar month; holdings for every session t are the draw dated D(t) = the "
    "first session of t's month. Eligible on D, using ONLY bars dated strictly before D: median "
    "close x volume over the last LIQUID_DV_SESSIONS sessions >= LIQUID_MIN_DOLLAR_VOL; last close "
    ">= LIQUID_MIN_PRICE; >= LIQUID_MIN_HISTORY real bars; newest bar no more than "
    "LIQUID_MAX_BAR_AGE sessions before the last session before D; no SUSPECT_CORPORATE_ACTION in "
    "the last LIQUID_SUSPECT_LOOKBACK sessions (discovery_autopsy's rule: a one-bar raw move, last "
    "real bar to next real bar, above AUTOPSY_SUSPECT_UP or below AUTOPSY_SUSPECT_DOWN on a name "
    "whose previous close is >= AUTOPSY_MIN_PRICE); not an ETF or index proxy "
    "(LIQUID_EXCLUDE_ETFS: xs_ranker.INDEX_PROXIES + llm_portfolio.is_etf). Eligible symbols are "
    "sorted and LIQUID_N are drawn by paper_books._draw (np.random.default_rng, without "
    "replacement) with seed int(sha256('LIQUID_SEED:D')[:8], 16), recorded on every draw. Equal "
    "weight at D's close (the fill), then held as shares (drifting) until the next draw; a draw "
    "re-targets at its D's close. Costs: the engine's standard 5 + 1 bps per side.")

WHY_RANDOM = (
    "Why a random liquid base and not a strategy book: CH-11 (2026-11-12) found the strategy books "
    "are mostly ONE bet (momentum and revision-flow correlate 0.95-0.99; overlap 54-84%) and that "
    "the volatility band explains much of their results. An overlay on one of them would mix the "
    "scalar with that bet. A random draw from the liquid ($50M+/day) band holds no selection, so "
    "the one thing this book tests is HOW MUCH is held. A random liquid book is not a strategy, "
    "and its own return vs SPY is a property of the draw, not of the overlay.")


# ───────────────────────────── the contract ─────────────────────────────────

def params() -> dict:
    return {k: getattr(_cfg, k) for k in (
        "NEWS_OVERLAY_BASE_BOOK", "NEWS_OVERLAY_SCALAR_MIN", "NEWS_OVERLAY_SCALAR_MAX",
        "NEWS_OVERLAY_MIN_THEMES", "NEWS_OVERLAY_BASELINE_N", "NEWS_OVERLAY_BASELINE_MIN",
        "NEWS_OVERLAY_SLOPE", "NEWS_OVERLAY_DEADBAND", "NEWS_OVERLAY_STEP",
        "NEWS_OVERLAY_DECISION_ET", "NEWS_OVERLAY_MAX_AGE_HOURS",
        "NEWS_OVERLAY_COST_BPS_PER_SIDE", "NEWS_OVERLAY_SLIPPAGE_BPS",
        "NEWS_OVERLAY_NOTIONAL_USD", "NEWS_OVERLAY_MAPPING_DECLARED_UTC",
        "NEWS_OVERLAY_V2_DECLARED_UTC", "NEWS_OVERLAY_MAPPINGS_TRIED",
        "NEWS_OVERLAY_BASELINE_MAX_AGE_DAYS", "NEWS_OVERLAY_STEP_WINDOW_ET",
        "NEWS_OVERLAY_STALE_BAR_SESSIONS",
        "NEWS_OVERLAY_V3_DECLARED_UTC", "NEWS_OVERLAY_BASES_TRIED", "NEWS_OVERLAY_LIQUID_N",
        "NEWS_OVERLAY_LIQUID_MIN_DOLLAR_VOL", "NEWS_OVERLAY_LIQUID_DV_SESSIONS",
        "NEWS_OVERLAY_LIQUID_MIN_PRICE", "NEWS_OVERLAY_LIQUID_MIN_HISTORY",
        "NEWS_OVERLAY_LIQUID_MAX_BAR_AGE", "NEWS_OVERLAY_LIQUID_SUSPECT_LOOKBACK",
        "NEWS_OVERLAY_LIQUID_SEED", "NEWS_OVERLAY_LIQUID_EXCLUDE_ETFS",
        "NEWS_OVERLAY_STALE_REFUSE_SHARE", "NEWS_OVERLAY_COMPARISON_BASE",
        "AUTOPSY_SUSPECT_UP", "AUTOPSY_SUSPECT_DOWN", "AUTOPSY_MIN_PRICE")}


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
        "base_definition": BASE_DEFINITION,
        "why_random_base": WHY_RANDOM,
        "comparison_base": {"id": p["NEWS_OVERLAY_COMPARISON_BASE"],
                            "role": ("COMPARISON ONLY, never graded: the same scalars applied to SPY "
                                     "alone (scalar x SPY vs 1.0 x SPY), so the overlay's effect can "
                                     "be read on the index too")},
        "twin": "the base book at scalar 1.0: identical names, relative weights, re-target moments "
                "and cost rate; only the scalar differs",
        "inputs": {
            "digests": "OPTIMUS_LEDGER_DIR/digest/world_digest_<YYYYMMDDTHHMMSSZ>.json "
                       "(world_digest.out_dir); fields themes[].tone.fear_greed and "
                       "themes[].tone.n_independent_sources; dry runs ignored",
            "base_holdings": ("derived, never stored: LIQUID-RANDOM-50 from "
                              "OPTIMUS_LEDGER_DIR/prices_2025_26/bars.parquet (close, volume) dated "
                              "strictly before each monthly draw date"),
            "prices": "OPTIMUS_LEDGER_DIR/prices_2025_26/bars.parquet close",
        },
        "mapping": ("F = sum_i n_i * fear_greed_i / sum_i n_i over themes with numeric "
                    "tone.fear_greed, n_i = max(1, n_independent_sources); fewer than MIN_THEMES "
                    "-> EMPTY. B = median F over the previous BASELINE_N valid digests stamped "
                    "strictly before this digest AND no more than BASELINE_MAX_AGE_DAYS older than it; "
                    "fewer than BASELINE_MIN -> NO_BASELINE. "
                    "d = F - B; raw = 1 - SLOPE * max(0, -d - DEADBAND); scalar = clip("
                    "round(raw / STEP) * STEP, SCALAR_MIN, SCALAR_MAX). Any degradation -> 1.0."),
        "timing": ("session t = an XNYS session dated in America/New_York; decision time = "
                   "min(DECISION_ET, the session's real close - 30 min) on t; read only digests "
                   "stamped strictly before it; newest older than MAX_AGE_HOURS -> STALE; fill = "
                   "close of t (the next close after the digest's own stamp); the scalar earns "
                   "close t -> close t+1. The forward step runs only inside STEP_WINDOW_ET on a "
                   "real session (refused otherwise); a --date other than today's ET session is "
                   "BACKDATED and never graded; one FORWARD row per session (a repeat is a no-op)"),
        "stale_bar_refusal": ("v3: at decision time for session t, the base's holdings for t are "
                              "weighted at the last close before t; if more than STALE_REFUSE_SHARE "
                              "of that weight sits on names whose newest bar (as of the session "
                              "before t) is more than STALE_BAR_SESSIONS sessions old, the decision "
                              "is REFUSED: scalar 1.0, degradation STALE_BASE_BARS, holdings named "
                              "(v2 only flagged this)"),
        "grading": ("only FORWARD rows of this policy_hash; a session with no row -> scalar 1.0, "
                    "reason NO_DECISION_ROW (never the last scalar held); a session where a base "
                    "holding's last real bar is more than STALE_BAR_SESSIONS sessions old is "
                    "also marked DEGRADED on the grade and the holdings are listed"),
        "rebalance": ("a book re-targets at a session close only when its scalar changed or the "
                      "base book's holdings changed (a base rebalance dated on a non-session day "
                      "takes effect at the first session after it); otherwise it holds its shares"),
        "costs": ("one-way rate = (COST_BPS_PER_SIDE + SLIPPAGE_BPS) / 1e4 on every traded dollar, "
                  "including the overlay's own scalar turnover; cash earns 0"),
        "objective": ("terminal NAV of the overlay vs its twin under the BALANCED personality "
                      "(same notional, same costs); read daily, by date block, raw lines first"),
        "disclosure": {"mappings_tried": p["NEWS_OVERLAY_MAPPINGS_TRIED"],
                       "seen_before_choosing": ("the range of the per-run source-weighted tone input "
                                                "(about -0.21 .. +0.05 over 2026-09-29..11-11) had been "
                                                "seen before SLOPE and DEADBAND were chosen; no return "
                                                "of any kind had been seen"),
                       "v2_change": ("only the baseline-age bound and the forward-path fixes; chosen "
                                     "by a reviewer's correctness finding, not from replay returns"),
                       "bases_tried": p["NEWS_OVERLAY_BASES_TRIED"],
                       "v3_change": ("only the base (and the stale-bar flag becoming a refusal). The "
                                     "tone->scalar rule (SLOPE, DEADBAND, STEP, bounds, MIN_THEMES, "
                                     "BASELINE_N/MIN/MAX_AGE_DAYS, timing) is v2's, unchanged. Base "
                                     "choice is a SECOND LOOK at this design: bases tried = 2 (the "
                                     "$3M random draw, then LIQUID-RANDOM-50); tone mappings tried = 1 "
                                     "functional form with one parameter set (v2's MAPPINGS_TRIED = 2 "
                                     "counts the v2 baseline-age bound as a second variant and is kept). "
                                     "The v2 replay had been seen (overlay -0.84 pp vs twin) before "
                                     "v3 was declared; the v3 base was chosen for readability (stale "
                                     "bars, splits, small caps), not from that number, and its seed "
                                     "was declared in config before any v3 replay ran")},
        "history": list(HISTORY),
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


def _et(hhmm: str) -> time:
    hh, mm = (int(x) for x in str(hhmm).split(":"))
    return time(hh, mm)


def session_close(session: date) -> Optional[datetime]:
    """The real XNYS close (early closes included), or None on a non-session day."""
    from backend.services import market_sessions as MS
    return MS.session_close_utc(session)


def is_session(day: date) -> bool:
    from backend.services import market_sessions as MS
    return MS.is_session(day)


def decision_time(session: date) -> datetime:
    """min(DECISION_ET, real close - 30 min) on `session`, in UTC (DST-aware)."""
    t = datetime.combine(session, _et(_cfg.NEWS_OVERLAY_DECISION_ET), tzinfo=ET).astimezone(timezone.utc)
    try:
        close = session_close(session)
    except Exception:                                          # noqa: BLE001 - calendar out of range
        close = None
    if close is not None:
        t = min(t, close - timedelta(minutes=30))
    return t


def forward_session(now: datetime) -> tuple[date, Optional[str]]:
    """(session, refusal) for a forward step run at wall clock `now` (tz-aware).
    The session is the America/New_York date; a non-session day or a time
    outside STEP_WINDOW_ET (window end capped at the real close) is a refusal."""
    if now.tzinfo is None:
        raise NewsOverlayRefused("forward_session needs a tz-aware clock")
    local = now.astimezone(ET)
    d = local.date()
    if not is_session(d):
        return d, f"{d} ({local:%a}) is not an XNYS session"
    lo, hi = (datetime.combine(d, _et(x), tzinfo=ET) for x in _cfg.NEWS_OVERLAY_STEP_WINDOW_ET)
    close = session_close(d)
    if close is not None:
        hi = min(hi, close.astimezone(ET))
        lo = min(lo, hi - timedelta(minutes=30))
    if not (lo <= local < hi):
        return d, (f"{local:%Y-%m-%d %H:%M} ET is outside the step window "
                   f"{lo:%H:%M}-{hi:%H:%M} ET for session {d}")
    if now.astimezone(timezone.utc) < decision_time(d):
        return d, f"{local:%H:%M} ET is before the decision time for {d}"
    return d, None


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
    oldest = g["stamped_utc"] - timedelta(days=float(_cfg.NEWS_OVERLAY_BASELINE_MAX_AGE_DAYS))
    prior = [r["F"] for r in seen if oldest <= r["stamped_utc"] < g["stamped_utc"] and r["F"] is not None]
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
         out_path: Optional[Path] = None, write: bool = True, label: str = FORWARD,
         now: Optional[datetime] = None,
         stale: Optional[Mapping[str, Any]] = None) -> dict:
    """One decision row for `session`. Writes only when the flag is ON and
    `write` is True; with the flag OFF it computes and writes NOTHING.
    Every row carries `written_utc` (the wall clock, `now`). A second FORWARD
    row for the same session under this contract is a no-op, never a row."""
    if label not in (FORWARD, BACKDATED, BACKFILL):
        raise NewsOverlayRefused(f"unknown row label {label!r}")
    if not base_weights:
        raise NewsOverlayRefused(f"no base-book holdings for {session}: an overlay on nothing "
                                 f"would grade as flat")
    on = bool(_cfg.NEWS_OVERLAY_BOOK_ENABLED if enabled is None else enabled)
    c = contract()
    sc = compute_scalar(digests, decision_time(session))
    if stale is not None:
        sc["stale_weight_share"] = round(float(stale.get("share") or 0.0), 6)
        sc["stale_names"] = dict(stale.get("names") or {})
        if float(stale.get("share") or 0.0) > float(_cfg.NEWS_OVERLAY_STALE_REFUSE_SHARE):
            sc["tone_degradation"] = sc["degradation"]
            sc["tone_scalar"] = sc["scalar"]
            sc.update({"scalar": 1.0, "degradation": STALE_BASE, "refused": True})
    g = sum(float(w) for w in base_weights.values())
    prev = 1.0 if prev_scalar is None else float(prev_scalar)
    row = {"schema": SCHEMA, "label": label, "session": session.isoformat(),
           "policy_hash": c["policy_hash"], "base_book_id": c["base_book_id"], **sc,
           "prev_scalar": prev, "base_gross": round(g, 6),
           "overlay_gross": round(g * sc["scalar"], 6),
           "scalar_turnover_frac": round(abs(sc["scalar"] - prev) * g, 6),
           "est_scalar_cost_frac": round(abs(sc["scalar"] - prev) * g * cost_rate(), 8),
           "n_names": len(base_weights), "fill": f"close of {session.isoformat()}",
           "flag_enabled": on, "written": False,
           "written_utc": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
               timespec="seconds")}
    if on and write:
        p = Path(out_path) if out_path else decisions_path()
        existing = _refuse_foreign_contract(p, c["policy_hash"])
        dup = [r for r in existing if r.get("session") == row["session"]
               and r.get("label") == label]
        if dup and label == FORWARD:
            return {**dup[-1], "written": False, "duplicate": True}
        p.parent.mkdir(parents=True, exist_ok=True)
        row["written"] = True
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row


def _refuse_foreign_contract(p: Path, policy_hash: str) -> list[dict]:
    """Every row of `p` must carry `policy_hash`; returns the rows."""
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        h = r.get("policy_hash")
        if h != policy_hash:
            raise NewsOverlayRefused(f"{p} line {i} is under policy {h}; this rule hashes to "
                                     f"{policy_hash}. A changed rule writes a new file.")
        rows.append(r)
    return rows


def read_forward_rows(p: Path, policy_hash: str) -> list[dict]:
    """The gradeable rows: FORWARD, this contract, one per session (first wins)."""
    seen: dict[str, dict] = {}
    for r in _refuse_foreign_contract(p, policy_hash):
        if r.get("label") == FORWARD and r.get("session") not in seen:
            seen[r["session"]] = r
    return [seen[k] for k in sorted(seen)]


def grade_scalars(sessions: Sequence[date], rows: Sequence[Mapping]) -> tuple[dict, dict]:
    """(scalar, reason) per session for grading: the row's scalar, or 1.0 with
    NO_DECISION_ROW when the session has no FORWARD row. Never the last held."""
    by = {str(r["session"]): r for r in rows}
    sc, why = {}, {}
    for t in sessions:
        r = by.get(t.isoformat())
        if r is None:
            sc[t], why[t] = 1.0, NO_DECISION_ROW
        else:
            sc[t], why[t] = float(r["scalar"]), r.get("degradation")
    return sc, why


def stale_holdings(last_bar_pos: Mapping[str, Mapping[date, int]], sessions: Sequence[date],
                   weights: Mapping[date, Mapping[str, float]], n: Optional[int] = None) -> dict:
    """{session: {symbol: sessions_since_last_real_bar}} for holdings older than
    STALE_BAR_SESSIONS. `last_bar_pos[sym][t]` = index distance from t to the
    symbol's last real bar on or before t (absent = no bar at all)."""
    lim = int(_cfg.NEWS_OVERLAY_STALE_BAR_SESSIONS if n is None else n)
    out: dict = {}
    for t in sessions:
        bad = {}
        for sym in weights.get(t, {}):
            age = (last_bar_pos.get(sym) or {}).get(t)
            if age is None or age > lim:
                bad[sym] = age
        if bad:
            out[t] = bad
    return out


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


# ───────────────────────────── loaders (read-only) ──────────────────────────

CASH = "$CASH"      # book_cadence.CASH, repeated so this reader never imports the stepper


def load_base_holdings(db_path: Path, book_id: str) -> list[dict]:
    """The base book's holdings snapshots, oldest first: [{asof, decided_utc,
    shares: {sym: n}, cash}]. Opened READ-ONLY (sqlite uri mode=ro)."""
    import sqlite3
    p = Path(db_path)
    if not p.is_file():
        raise NewsOverlayRefused(f"no paper-book store at {p}")
    conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    try:
        dec = conn.execute("SELECT asof_date, decided_utc FROM paper_book_decisions "
                           "WHERE book_id = ? ORDER BY decided_utc", (book_id,)).fetchall()
        pos = conn.execute("SELECT ticker, shares, opened_at FROM paper_positions "
                           "WHERE portfolio_id = ?", (book_id,)).fetchall()
    finally:
        conn.close()
    if not dec or not pos:
        raise NewsOverlayRefused(f"base book {book_id} has no decisions or positions in {p}")
    by_open: dict[str, dict] = {}
    for tk, sh, opened in pos:
        by_open.setdefault(str(opened), {})[str(tk)] = float(sh)
    snaps = []
    for asof, decided in dec:
        sh = by_open.get(str(decided))
        if sh is None:
            continue
        cash = sh.pop(CASH, 0.0)
        snaps.append({"asof": date.fromisoformat(str(asof)[:10]), "decided_utc": str(decided),
                      "shares": sh, "cash": cash})
    if not snaps:
        raise NewsOverlayRefused(f"base book {book_id}: no position set matches a decision stamp")
    return snaps


def base_weights_by_session(snaps: Sequence[Mapping], sessions: Sequence[date],
                            closes: Mapping[date, Mapping[str, float]]) -> tuple[dict, dict]:
    """(weights, changed) per session: the base book's own shares x close / its
    NAV (cash included), from the newest snapshot with asof <= session."""
    weights, changed = {}, {}
    prev_idx = None
    for t in sessions:
        live = [i for i, s in enumerate(snaps) if s["asof"] <= t]
        if not live:
            raise NewsOverlayRefused(f"no base-book holdings on or before {t}")
        idx = live[-1]
        sn = snaps[idx]
        px = closes[t]
        val = {k: n * px[k] for k, n in sn["shares"].items()}
        nav = sum(val.values()) + float(sn["cash"])
        weights[t] = {k: v / nav for k, v in val.items()}
        # a NEW snapshot since the previous session (an asof on a weekend or
        # holiday takes effect at the first session after it)
        changed[t] = prev_idx is not None and idx != prev_idx
        prev_idx = idx
    return weights, changed


# ───────────────────────────── v3: the LIQUID-RANDOM-50 base ────────────────
#
# Why here and not in paper_books: `paper_books.create` persists the book and its
# twins into aegis_pi.db and `book_cadence` writes positions and NAV there (a live
# store a builder may not write), and the engine's random twin screens on a
# 21-session median with no history, stale-bar or corporate-action rule. So the
# base is a deterministic, replayable DEFINITION: holdings are derived from the
# bars panel on each draw date from bars strictly before it. The draw itself is
# the engine's (`paper_books._draw`), so the randomness is the engine's.

def month_draw_date(t: date) -> date:
    """D(t): the first XNYS session of t's calendar month."""
    d = date(t.year, t.month, 1)
    for _ in range(31):
        if is_session(d):
            return d
        d += timedelta(days=1)
    raise NewsOverlayRefused(f"no XNYS session found in {t:%Y-%m}")


def draw_seed(asof: date, base: Optional[int] = None) -> int:
    b = int(_cfg.NEWS_OVERLAY_LIQUID_SEED if base is None else base)
    return int(hashlib.sha256(f"{b}:{asof.isoformat()}".encode()).hexdigest()[:8], 16)


def excluded_symbols() -> set:
    """ETFs and index proxies kept out of the liquid draw. An import failure
    refuses (a silent empty set would let SPY into a 'stock' draw)."""
    if not bool(_cfg.NEWS_OVERLAY_LIQUID_EXCLUDE_ETFS):
        return set()
    try:
        from backend.services import xs_ranker as XR
    except Exception as exc:                                   # noqa: BLE001
        raise NewsOverlayRefused(f"xs_ranker.INDEX_PROXIES unavailable ({exc})") from exc
    out = {str(s).upper() for s in XR.INDEX_PROXIES}
    out |= {str(s).upper() for s in getattr(_cfg, "BOOK_KNOWN_ETFS", ())}
    out |= {str(s).upper() for s in dict(getattr(_cfg, "THEME_ETF_MAP", {}) or {}).values()}
    if getattr(_cfg, "BOOK_WLS_PROXY", None):
        out.add(str(_cfg.BOOK_WLS_PROXY).upper())
    return out


def bar_ages(close, upto: date) -> dict:
    """{symbol: sessions from its newest real bar to the last session <= upto}
    (None = no bar at all). `close` is a wide frame (index = session dates)."""
    import numpy as np
    idx = [d for d in close.index if d <= upto]
    if not idx:
        return {}
    notna = close.loc[idx].notna().to_numpy()[::-1]
    anyv = notna.any(axis=0)
    first = notna.argmax(axis=0)
    return {str(s): (int(first[j]) if anyv[j] else None) for j, s in enumerate(close.columns)}


def eligibility(close, volume, asof: date) -> dict:
    """The LIQUID-RANDOM-50 rules on `asof`, from rows dated STRICTLY before it.
    `close`/`volume`: wide frames, index = XNYS session dates, NaN = no bar."""
    import numpy as np
    idx = [d for d in close.index if d < asof]
    if len(idx) < 2:
        raise NewsOverlayRefused(f"fewer than 2 sessions of bars before {asof}")
    c = close.loc[idx]
    v = volume.reindex(index=idx, columns=c.columns)
    n_hist = c.notna().sum(axis=0)
    ages = bar_ages(c, idx[-1])
    last_close = c.ffill().iloc[-1]
    W = int(_cfg.NEWS_OVERLAY_LIQUID_DV_SESSIONS)
    dv = (c * v).iloc[-W:].median(axis=0, skipna=True)
    L = int(_cfg.NEWS_OVERLAY_LIQUID_SUSPECT_LOOKBACK)
    cc = c.iloc[-(L + 1):]
    prev = cc.ffill().shift(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (cc / prev - 1.0).where(cc.notna())
    sus = ((prev >= float(_cfg.AUTOPSY_MIN_PRICE))
           & ((r > float(_cfg.AUTOPSY_SUSPECT_UP)) | (r < float(_cfg.AUTOPSY_SUSPECT_DOWN)))).iloc[1:]
    suspect = sus.any(axis=0)
    excl = excluded_symbols()
    fails = {"dollar_vol": set(), "price": set(), "history": set(), "stale": set(),
             "suspect": set(), "etf": set()}
    pool = []
    for s in c.columns:
        sym = str(s)
        bad = False
        if not (dv.get(s) == dv.get(s)) or float(dv[s]) < float(_cfg.NEWS_OVERLAY_LIQUID_MIN_DOLLAR_VOL):
            fails["dollar_vol"].add(sym); bad = True
        if not (last_close.get(s) == last_close.get(s)) or float(last_close[s]) < float(_cfg.NEWS_OVERLAY_LIQUID_MIN_PRICE):
            fails["price"].add(sym); bad = True
        if int(n_hist[s]) < int(_cfg.NEWS_OVERLAY_LIQUID_MIN_HISTORY):
            fails["history"].add(sym); bad = True
        a = ages.get(sym)
        if a is None or a > int(_cfg.NEWS_OVERLAY_LIQUID_MAX_BAR_AGE):
            fails["stale"].add(sym); bad = True
        if bool(suspect.get(s, False)):
            fails["suspect"].add(sym); bad = True
        if sym.upper() in excl:
            fails["etf"].add(sym); bad = True
        if not bad:
            pool.append(sym)
    return {"asof": asof, "last_bar_date_used": idx[-1], "n_symbols": int(c.shape[1]),
            "pool": sorted(pool), "fails": fails}


def draw_liquid_base(close, volume, asof: date, *, n: Optional[int] = None,
                     seed: Optional[int] = None) -> dict:
    """One recorded draw. Refuses when the pool holds fewer than n names."""
    from backend.services import paper_books as PB
    el = eligibility(close, volume, asof)
    k = int(_cfg.NEWS_OVERLAY_LIQUID_N if n is None else n)
    sd = draw_seed(asof) if seed is None else int(seed)
    if len(el["pool"]) < k:
        raise NewsOverlayRefused(f"LIQUID-RANDOM-{k} on {asof}: only {len(el['pool'])} eligible names")
    names = PB._draw(el["pool"], k, sd)
    if el["last_bar_date_used"] >= asof:                       # belt and braces: never a bar on/after D
        raise NewsOverlayRefused(f"draw on {asof} used a bar dated {el['last_bar_date_used']}")
    return {"asof": asof.isoformat(), "seed": sd, "base_seed": int(_cfg.NEWS_OVERLAY_LIQUID_SEED),
            "pool_size": len(el["pool"]), "n_symbols_in_panel": el["n_symbols"],
            "fail_counts": {k2: len(v) for k2, v in el["fails"].items()},
            "last_bar_date_used": el["last_bar_date_used"].isoformat(), "names": names,
            "pool_sha16": hashlib.sha256(",".join(el["pool"]).encode()).hexdigest()[:16]}


def liquid_snapshots(draws: Sequence[Mapping], close_ff) -> list[dict]:
    """Snapshots for `base_weights_by_session`: equal weight at each D's close."""
    snaps = []
    for dr in draws:
        D = date.fromisoformat(dr["asof"])
        if D not in close_ff.index:
            raise NewsOverlayRefused(f"no bar row for draw date {D}: cannot fill the draw at its close")
        row = close_ff.loc[D]
        k = len(dr["names"])
        sh = {}
        for s in dr["names"]:
            px = row.get(s)
            if not (px == px) or not px:
                raise NewsOverlayRefused(f"no close for drawn {s} at {D}")
            sh[s] = (1.0 / k) / float(px)
        snaps.append({"asof": D, "shares": sh, "cash": 0.0, "draw": dict(dr)})
    return snaps


def stale_weight_share(shares: Mapping[str, float], close_prev: Mapping[str, float],
                       ages_prev: Mapping[str, Optional[int]], limit: Optional[int] = None) -> dict:
    """{share, names}: the share of the base's weight (shares x last close before
    the decision) on names whose newest bar is more than `limit` sessions old."""
    lim = int(_cfg.NEWS_OVERLAY_STALE_BAR_SESSIONS if limit is None else limit)
    w = {s: float(n) * float(close_prev.get(s) or 0.0) for s, n in shares.items()}
    tot = sum(w.values())
    bad = {s: ages_prev.get(s) for s in shares
           if ages_prev.get(s) is None or int(ages_prev.get(s)) > lim}
    share = (sum(w[s] for s in bad) / tot) if tot > 0 else (1.0 if bad else 0.0)
    return {"share": share, "names": bad}


__all__ = ["month_draw_date", "draw_seed", "eligibility", "draw_liquid_base", "liquid_snapshots",
           "stale_weight_share", "bar_ages", "STALE_BASE", "BASE_DEFINITION", "WHY_RANDOM",
           "forward_session", "read_forward_rows", "grade_scalars", "stale_holdings",
           "FORWARD", "BACKDATED", "BACKFILL", "NO_DECISION_ROW", "HISTORY", "NewsOverlayRefused", "load_base_holdings", "base_weights_by_session", "contract", "params", "cost_rate", "tone_score", "digest_summary",
           "load_digests", "decision_time", "map_scalar", "compute_scalar", "step", "simulate",
           "decisions_path", "DEGRADATIONS", "NO_DIGEST", "STALE", "EMPTY", "NO_BASELINE"]
