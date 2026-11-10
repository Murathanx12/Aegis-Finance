"""PC-PAPER's OWN index in place of the SPY core (owner decision OD-10, 2026-11-10).

Owner, 2026-11-10: the account must stop holding SPY -- *"it should go for
specific stocks and make its own index"*. SPY stays the BENCHMARK only; cash,
never SPY, fills an empty slot. This module is the construction; `sim_run.u_plan`
calls it where the D14 core used to be planned (`config.PC_OWN_INDEX`), and
`python -m scripts.pc_own_index dry-run` prints the same plan offline.

WHAT THE INDEX IS (nothing new is invented; every input already exists)
---------------------------------------------------------------------
* MEMBERS: the opportunity funnel's candidates (`config.IC_FUNNEL_PATH`, the
  universe hub's 5,3xx -> 1,500 -> 250 -> 40 -> 25 selection), one line per
  issuer (`investment_committee.collapse_share_classes`), in the funnel's own
  score order, minus `PC_OWN_INDEX_EXCLUDED` (SPY and broad index ETFs) and the
  revision_flow sleeve's names, top `PC_OWN_INDEX_N`. Frozen into a membership
  file and reused for `PC_OWN_INDEX_REBALANCE_DAYS`; then rebuilt from a FRESH
  candidate file. A stale (> `PC_OWN_INDEX_MAX_SOURCE_AGE_DAYS`), undateable,
  unreadable or empty candidate file REFUSES -- it never falls back to SPY.
* WEIGHTS: equal, `w = min(PC_OWN_INDEX_MAX_NAME_FRAC, G / N)` with N the
  DECLARED count, so fewer qualifying names leave their slots in CASH.
* GROSS G: chosen by the worst case, not conviction -- the largest multiple of
  `PC_OWN_INDEX_GROSS_STEP` that fits in what the other sleeves leave (minus a
  cash buffer), never above `PC_OWN_INDEX_MAX_GROSS` (the share the owner
  approved, 30%), and passes BOTH (1) the whole book's one-day rho=1 k-sigma
  loss <= `PC_WORST_CASE_MAX_FRAC_OF_EQUITY` and (2) G x |the basket's worst
  21-session return over the FIXED window from `PC_OWN_INDEX_HISTORY_START`|
  <= `PC_OWN_INDEX_MAX_WORST_21_SESSION_LOSS_FRAC`. A member without that
  history is EXCLUDED (its slot is cash), so a young listing cannot drop 2020
  from the bound (review #89 R4). An UNKNOWN bound fails; gates only shrink.
* ONE SYMBOL, ONE SLEEVE: a member another sleeve holds or acts on this cycle is
  skipped (its slot stays cash). Held names that are members and that no other
  sleeve claims are ADOPTED (rebalanced to the index weight). A previous member
  that left at a SUCCESSFUL rebuild is sold (OWN_INDEX_EXIT); a held member
  excluded for short history is HELD, not sold.
* THE OLD CORE: a held SPY is sold whole-share (CORE_EXIT) only in a plan that
  also BUYS the index (a valid contract, a fresh membership and a gross both
  bounds pass). Every refusal -- stale/empty candidates, no qualifying member,
  an unknown or failing bound, no valid contract -- holds EVERYTHING: SPY, the
  held members and any leaver; no sell intent leaves a refusal (review2 #89
  B1). Without a valid contract the session sends no order at all (review #89
  R2).
* FUNDED BUYS ONLY: index buys go out only after every sell of the session is
  CONFIRMED filled, sized from the broker's cash read after those fills, with
  the book's gross checked against equity first (`gate_index_buys`, review #89
  R3). A skipped, failed or unconfirmed sell means no index buy this session.

LICENCE: PRODUCT_EXPERIMENT. `contract_content()` is the frozen strategy contract
(policy hash over every parameter + this module's source, timestamp, inputs,
costs, fill convention, objective, control); `freeze()` writes it once BEFORE the
first decision and `load_frozen()` REFUSES when config or code no longer match.
No skill claim: the funnel's PROBE shortlist graded MEASURED_NEGATIVE at h=5
(-0.76% per decision day over 22 days, 2026-11-05) and the receipt says so.

PURE except the file readers/writers named here. Never an order: plans only.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _cfg

SCHEMA = "pc_own_index/v1"
MEMBERS_SCHEMA = "pc_own_index_members/v1"
STATE = "OWN_INDEX"
EXIT_STATE = "OWN_INDEX_EXIT"
HOLD_STATE = "OWN_INDEX_HOLD"
CORE_EXIT_STATE = "CORE_EXIT"
CONTRACT_FILE = "own_index_contract.json"
MEMBERS_FILE = "own_index_members.json"
MEMBERS_HISTORY = "own_index_members_history.jsonl"
SOURCE_FILE = Path(__file__).resolve()
#: Index buys are sized at the plan price plus this margin, so a market fill a
#: little above the plan price cannot spend cash the sizing did not count.
BUY_PRICE_MARGIN = 0.005
_sleep = time.sleep


class OwnIndexRefused(RuntimeError):
    """The index cannot be built or traded safely; nothing is bought, SPY is never a filler."""


# ───────────────────────────── contract ─────────────────────────────────────

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def source_sha256(path: Optional[Path] = None) -> str:
    """This module's source, CRLF-normalised (a Windows checkout hashes the same)."""
    return hashlib.sha256(Path(path or SOURCE_FILE).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds")


def contract_content(cfg: Any = None) -> dict:
    """The strategy contract, derived from config + code. Same inputs -> same hash."""
    c = cfg or _cfg
    k = float(c.PROBE_WORST_CASE_SIGMA)
    per_side = float(c.FLEET_MANAGER_COST_BPS_PER_SIDE)
    return {
        "schema": SCHEMA,
        "version": str(c.PC_OWN_INDEX_VERSION),
        "account": "PC-PAPER (Alpaca paper; config.PC_PAPER_ACCOUNT_NUMBER)",
        "licence": "PRODUCT_EXPERIMENT",
        "owner_decision": "OD-10 2026-11-10: no SPY core; specific stocks, its own index; "
                          "SPY is the benchmark only; cash, not SPY, fills empty slots",
        "inputs": {
            "membership_source": "config.IC_FUNNEL_PATH candidates (opportunity_funnel stage 4), "
                                 "issuer-collapsed (investment_committee.collapse_share_classes), "
                                 "funnel score order",
            "source_max_age_days": float(c.PC_OWN_INDEX_MAX_SOURCE_AGE_DAYS),
            "source_age_basis": "the file's own generated_at stamp; undateable = stale; never mtime",
            "excluded_symbols": sorted(str(s).upper() for s in c.PC_OWN_INDEX_EXCLUDED),
            "excluded_sleeves": "names of the revision_flow sleeve and of any acting PROBE/"
                                "EXPLOIT target this cycle (one symbol, one sleeve)",
            "equity": "the broker's equity read (pc_broker.snapshot), never a literal",
            "sigma": f"pc_risk.panel_sigmas ({int(c.FLEET_MANAGER_SIGMA_WINDOW)}-session daily "
                     f"sigma, bars panel); a name without one at the universe p90",
            "history": "pc_own_index.bound_history: the longest panel on disk "
                       "(pc_sleeves.history_panel), FIXED window from history_start; a member "
                       "first priced more than history_tolerance_days after it is excluded",
            "history_start": str(c.PC_OWN_INDEX_HISTORY_START),
            "history_tolerance_days": int(c.PC_OWN_INDEX_HISTORY_TOLERANCE_DAYS),
            "adv": "each member's median_dollar_vol from the candidate file feeds "
                   "pc_broker.plan_orders' MAX_ADV_PARTICIPATION cap",
        },
        "construction": {
            "n_declared": int(c.PC_OWN_INDEX_N),
            "weighting": "equal; w = min(max_name_frac, G / n_declared); unfilled slots are cash",
            "max_name_frac": float(c.PC_OWN_INDEX_MAX_NAME_FRAC),
            "gross_step": float(c.PC_OWN_INDEX_GROSS_STEP),
            "rebalance_days": float(c.PC_OWN_INDEX_REBALANCE_DAYS),
            "between_rebuilds": "pc_broker.plan_orders drift band (REBALANCE_DRIFT_FRAC) only",
            "cash_buffer": float(c.PC_OWN_INDEX_CASH_BUFFER),
            "max_gross": float(c.PC_OWN_INDEX_MAX_GROSS),
            "long_only": True, "leverage": 0.0, "gross_cap": 1.0,
        },
        "risk": {
            "k_sigma": k,
            "one_day_book_limit_frac": float(c.PC_WORST_CASE_MAX_FRAC_OF_EQUITY),
            "worst_21_session_limit_frac": float(c.PC_OWN_INDEX_MAX_WORST_21_SESSION_LOSS_FRAC),
            "unknown_bound": "fails (the index gross is 0)",
            "worst_21_basis": "min(every-name-priced window, any window) over the eligible "
                              "members, from history_start",
            "stops": "none declared; the no-stop ceiling is the whole gross",
            "gates_only_shrink": True,
        },
        "costs_and_fills": {
            "orders": "pc_broker.submit: Alpaca paper market DAY orders, whole shares, sells "
                      "before buys, only while the venue clock is open, under the session lease",
            "funded_buys": "index buys only after every sell is confirmed filled "
                           f"(wait {float(c.PC_OWN_INDEX_SELL_FILL_WAIT_S):g} s), sized from the "
                           "broker's cash after the fills less the cash buffer, at plan price + "
                           f"{BUY_PRICE_MARGIN:.1%}, and only while long market value + buys <= "
                           "(1 - cash buffer) x equity",
            "declared_cost_bps_per_side": per_side,
            "cost_basis": "fills measured from the broker; the grade charges the declared "
                          "cost on turnover; slippage vs arrival is never imputed as zero",
            "limits": "pc_broker MAX_NAME_FRAC, MIN_ORDER_USD, MAX_ADV_PARTICIPATION, "
                      "MAX_ORDERS_PER_SESSION, REBALANCE_DRIFT_FRAC unchanged",
        },
        "objective": {
            "primary": "terminal wealth of PC-PAPER vs SPY over the same window (descriptive)",
            "control": "a sigma-decile matched random twin of the same members' weights, drawn "
                       "at each membership freeze from the bars panel (fleet_manager."
                       "matched_random_twin), seed = sha256(policy_hash + frozen_utc)[:8]",
            "grading": "each member writes sleeve decision rows (sim_run._sleeve_decision_rows, "
                       "label OWN_INDEX) graded as excess over SPY at PC_SLEEVE_GRADE_HORIZONS",
            "claim": "none. OBSERVED until matured forward evidence; no skill claim",
        },
        "code": {"module": "backend/services/pc_own_index.py", "source_sha256": source_sha256()},
    }


def policy_hash(content: dict) -> str:
    return _sha(content)


def freeze(path: Path, *, now: Optional[datetime] = None, cfg: Any = None) -> dict:
    """Write the contract ONCE (temp -> replace). Same content: idempotent.
    Different content at the same version: REFUSED (bump PC_OWN_INDEX_VERSION)."""
    content = contract_content(cfg)
    h = policy_hash(content)
    p = Path(path)
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        if old.get("policy_hash") == h:
            return old
        if (old.get("content") or {}).get("version") == content["version"]:
            raise OwnIndexRefused(
                f"a different contract is frozen under {content['version']} "
                f"({str(old.get('policy_hash'))[:12]} != {h[:12]}): bump "
                f"PC_OWN_INDEX_VERSION; a frozen version is never rewritten")
    row = {"content": content, "policy_hash": h, "frozen_utc": _iso(now or _now()),
           "superseded": (json.loads(p.read_text(encoding="utf-8")).get("policy_hash")
                          if p.exists() else None)}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(row, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)
    return row


def load_frozen(path: Path, *, cfg: Any = None) -> dict:
    """The frozen contract, verified against what config + code say NOW."""
    p = Path(path)
    if not p.exists():
        raise OwnIndexRefused(f"no frozen contract at {p}: run `python -m scripts.pc_own_index "
                              f"freeze` (attended) before the first decision")
    try:
        row = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OwnIndexRefused(f"frozen contract unreadable: {type(exc).__name__}: {exc}") from exc
    if row.get("policy_hash") != _sha(row.get("content")):
        raise OwnIndexRefused("frozen contract's bytes do not match its own policy hash")
    now_h = policy_hash(contract_content(cfg))
    if row["policy_hash"] != now_h:
        raise OwnIndexRefused(
            f"config or code changed since the freeze ({row['policy_hash'][:12]} frozen, "
            f"{now_h[:12]} now): bump PC_OWN_INDEX_VERSION and re-freeze, attended")
    return row


# ───────────────────────────── candidates ───────────────────────────────────

def _age_days(stamp: Any, now: datetime) -> Optional[float]:
    if not stamp:
        return None
    try:
        ts = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def read_candidates(funnel_path: Optional[Path] = None, *, now: Optional[datetime] = None,
                    max_age_days: Optional[float] = None,
                    issuer_of: Optional[dict] = None) -> dict:
    """The candidate set with its AGE and SIZE, or OwnIndexRefused."""
    path = Path(funnel_path or _cfg.IC_FUNNEL_PATH)
    now = now or _now()
    limit = float(_cfg.PC_OWN_INDEX_MAX_SOURCE_AGE_DAYS if max_age_days is None else max_age_days)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OwnIndexRefused(f"candidate file unreadable ({path.name}): "
                              f"{type(exc).__name__}: {exc}"[:240]) from exc
    stamp = payload.get("generated_at")
    age = _age_days(stamp, now)
    rows = [r for r in (payload.get("candidates") or []) if r.get("ticker")]
    info = {"path": str(path), "generated_at": stamp,
            "age_days": None if age is None else round(age, 2),
            "max_age_days": limit, "n_raw": len(rows)}
    if age is None:
        raise OwnIndexRefused(f"candidate file {path.name} carries no usable generated_at: "
                              f"its age CANNOT BE DETERMINED, so it is not fresh")
    if age > limit:
        raise OwnIndexRefused(f"candidate file {path.name} is {age:.1f} days old "
                              f"(generated {str(stamp)[:19]}, limit {limit:g}): STALE")
    if age < -0.01:
        raise OwnIndexRefused(f"candidate file {path.name} is dated in the future ({stamp})")
    if not rows:
        raise OwnIndexRefused(f"candidate file {path.name} is fresh and EMPTY: no index today")
    from backend.services import investment_committee as IC        # noqa: PLC0415
    collapsed = IC.collapse_share_classes(
        [{**r, "ticker": str(r["ticker"]).upper()} for r in rows], issuer_of=issuer_of)
    info["n_after_issuer_collapse"] = len(collapsed)
    info["share_class_dropped"] = [d for r in collapsed for d in (r.get("share_class_dropped") or [])]
    info["rows"] = collapsed
    info["line"] = (f"candidates: {len(rows)} in {path.name}, {len(collapsed)} issuers, "
                    f"generated {str(stamp)[:19]} ({age:.1f} d old, limit {limit:g} d)")
    return info


# ───────────────────────────── membership ───────────────────────────────────

def _read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _twin(members: list[str], sigmas: dict, *, seed: int, exclude: set) -> dict:
    if not members or not sigmas:
        return {"weights": {}, "seed": seed, "note": "no sigma panel: twin not drawn"}
    from backend.services.fleet_manager import matched_random_twin   # noqa: PLC0415
    w = 1.0 / len(members)
    pool = {s: v for s, v in sigmas.items() if s not in exclude and s not in members}
    tw = matched_random_twin({m: w for m in members}, sigmas, pool, seed)
    return {"weights": tw, "seed": seed,
            "rule": "same-sigma-decile random name per member, without replacement, "
                    "equal weight (fleet_manager.matched_random_twin)"}


def membership(folder: Path, *, contract: dict, funnel_path: Optional[Path] = None,
               now: Optional[datetime] = None, exclude: Optional[set] = None,
               sigmas: Optional[dict] = None, write: bool = True,
               issuer_of: Optional[dict] = None) -> dict:
    """The current members. Reused while younger than the rebalance period and
    frozen under the same policy hash; else rebuilt from a FRESH candidate file
    (OwnIndexRefused when it is stale/empty). `write=False` (the dry-run)
    computes in memory and writes nothing."""
    now = now or _now()
    c = contract["content"]
    h = contract["policy_hash"]
    folder = Path(folder)
    prev = _read_json(folder / MEMBERS_FILE)
    period = float(c["construction"]["rebalance_days"])
    if prev and prev.get("policy_hash") == h:
        age = _age_days(prev.get("frozen_utc"), now)
        if age is not None and 0 <= age < period:
            return {**prev, "status": "HELD_MEMBERSHIP", "membership_age_days": round(age, 2),
                    "line": (f"membership held: {len(prev.get('members') or [])} names frozen "
                             f"{str(prev.get('frozen_utc'))[:19]} ({age:.1f} d, rebuild at "
                             f"{period:g} d) from {str((prev.get('source') or {}).get('generated_at'))[:19]}")}
    cands = read_candidates(funnel_path, now=now,
                            max_age_days=float(c["inputs"]["source_max_age_days"]),
                            issuer_of=issuer_of)
    excl = {str(s).upper() for s in c["inputs"]["excluded_symbols"]} | {
        str(s).upper() for s in (exclude or set())}
    n = int(c["construction"]["n_declared"])
    members, skipped = [], []
    for r in cands["rows"]:
        t = str(r["ticker"]).upper()
        if t in excl:
            skipped.append(t)
            continue
        if len(members) < n:
            members.append(t)
    frozen = _iso(now)
    seed = int(hashlib.sha256((h + frozen).encode("ascii")).hexdigest()[:8], 16)
    row = {"schema": MEMBERS_SCHEMA, "policy_hash": h, "version": c["version"],
           "frozen_utc": frozen, "members": members, "n_declared": n,
           "excluded_skipped": skipped,
           "previous_members": list((prev or {}).get("members") or []),
           "source": {k: v for k, v in cands.items() if k not in ("rows", "line")},
           "candidate_scores": {str(r["ticker"]).upper(): r.get("score") for r in cands["rows"]},
           "median_dollar_vol": {str(r["ticker"]).upper(): r.get("median_dollar_vol")
                                 for r in cands["rows"]
                                 if isinstance(r.get("median_dollar_vol"), (int, float))},
           "twin": _twin(members, sigmas or {}, seed=seed, exclude=excl)}
    if not members:
        raise OwnIndexRefused(f"no candidate survives the exclusions "
                              f"({len(cands['rows'])} issuers, all excluded): no index today")
    if write:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / (MEMBERS_FILE + ".tmp")
        tmp.write_text(json.dumps(row, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(folder / MEMBERS_FILE)
        with (folder / MEMBERS_HISTORY).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return {**row, "status": "REBUILT" if write else "REBUILT_NOT_WRITTEN",
            "membership_age_days": 0.0,
            "line": (f"membership rebuilt: {len(members)} of {n} declared names; {cands['line']}"
                     + (f"; excluded {skipped}" if skipped else ""))}


# ───────────────────────────── history ──────────────────────────────────────

def bound_history(names: list[str], short_path: Optional[Path] = None, *,
                  start: Optional[str] = None, tolerance_days: Optional[int] = None,
                  window: int = 21) -> dict:
    """The 21-session bound on a FIXED window with a minimum-history rule (review
    #89 R4). A member first priced more than `tolerance_days` after `start` is
    SHORT and excluded (`short_history`); the bound is the worse of the
    every-name-priced and any-coverage windows over the eligible names, so it
    cannot loosen when the membership rotates. {"error": ...} fails bound 2."""
    from backend.services import pc_sleeves as SL                  # noqa: PLC0415
    start_s = str(start or _cfg.PC_OWN_INDEX_HISTORY_START)
    tol = int(_cfg.PC_OWN_INDEX_HISTORY_TOLERANCE_DAYS if tolerance_days is None
              else tolerance_days)
    path, warn = SL.history_panel(short_path)
    base = {"history_start": start_s, "history_tolerance_days": tol, "warning": warn}
    if path is None:
        return {**base, "error": warn, "eligible": [], "short_history": list(names)}
    try:
        import pandas as pd                                        # noqa: PLC0415
        df = pd.read_parquet(path, columns=["symbol", "date", "close"],
                             filters=[("symbol", "in", list(names))])
        df = df[df["close"].notna()]
        first = df.groupby("symbol")["date"].min()
    except Exception as exc:                                       # noqa: BLE001
        return {**base, "error": f"{type(exc).__name__}: {exc}"[:200], "eligible": [],
                "short_history": list(names)}
    limit = pd.Timestamp(start_s) + pd.Timedelta(days=tol)
    eligible = [s for s in names if s in first.index and pd.Timestamp(first[s]) <= limit]
    short = [s for s in names if s not in eligible]
    base.update({"eligible": eligible, "short_history": short,
                 "first_priced": {s: str(pd.Timestamp(first[s]).date())
                                  for s in names if s in first.index}})
    if not eligible:
        return {**base, "error": f"no member has history from {start_s} (+{tol} d)"}
    h = SL.basket_history(eligible, path, window=window)
    out = {**h, **base}
    full, anyw = h.get("worst_window_return"), h.get("worst_window_return_any")
    if full is None or anyw is None or h.get("error"):
        out["error"] = h.get("error") or "worst window not computable"
        out.pop("worst_window_return", None)
        return out
    out["worst_window_return_full"] = float(full)
    out["worst_window_return"] = min(float(full), float(anyw))
    out["worst_window_basis"] = (f"min(all-priced, any) over {len(eligible)} members priced "
                                 f"since {start_s}; {len(short)} short-history member(s) excluded")
    return out


# ───────────────────────────── sizing ───────────────────────────────────────

def book_k_sigma_frac(weights: dict[str, float], sigmas: dict, *, k: float,
                      fallback: float) -> float:
    """One-day rho=1 k-sigma loss of a set of long weights, as a fraction of equity."""
    return sum(max(0.0, float(w)) * k * float(sigmas.get(s) or fallback)
               for s, w in weights.items())


def choose_gross(*, names: list[str], n_declared: int, max_name_frac: float, room: float,
                 other_weights: dict[str, float], sigmas: dict, fallback: float, k: float,
                 day_limit: float, worst_21: Optional[float], window_limit: float,
                 step: float, max_gross: Optional[float] = None) -> dict:
    """The largest declared-N gross G (a multiple of `step`, never above
    `max_gross`, the owner-approved share) such that, with w = min(cap, G/N) on
    the `names` that qualify, BOTH bounds hold."""
    other = book_k_sigma_frac(other_weights, sigmas, k=k, fallback=fallback)
    if int(n_declared) <= 0 or step <= 0:
        return {"room": room, "upper": 0.0, "other_k_sigma_frac": other, "trials": [],
                "worst_21": worst_21, "declared_gross": 0.0, "w_each": 0.0, "gross": 0.0,
                "binding": "n_declared_zero" if int(n_declared) <= 0 else "step_zero"}
    caps = {"n_x_cap": n_declared * max_name_frac, "room": room}
    if max_gross is not None:
        caps["owner_max_gross"] = float(max_gross)
    upper_by = min(caps, key=lambda k_: caps[k_])
    hi = max(0.0, caps[upper_by])
    hi = math.floor(hi / step + 1e-9) * step
    trials = []
    g = hi
    best = None
    while g > 1e-9:
        w = min(max_name_frac, g / n_declared)
        gross = w * len(names)
        idx = book_k_sigma_frac({s: w for s in names}, sigmas, k=k, fallback=fallback)
        one = other + idx <= day_limit + 1e-12
        two = worst_21 is not None and gross * abs(float(worst_21)) <= window_limit + 1e-12
        trials.append({"declared_gross": round(g, 4), "w_each": w, "gross": gross,
                       "book_k_sigma_frac": other + idx, "bound_one_day": one,
                       "window_frac": (None if worst_21 is None else gross * abs(float(worst_21))),
                       "bound_21_session": two})
        if one and two:
            best = trials[-1]
            break
        g = round(g - step, 10)
    out = {"room": room, "upper": hi, "upper_set_by": upper_by, "max_gross": max_gross,
           "other_k_sigma_frac": other, "trials": trials[:25], "worst_21": worst_21}
    if best is None:
        out.update({"declared_gross": 0.0, "w_each": 0.0, "gross": 0.0,
                    "binding": ("21_session_unknown" if worst_21 is None else
                                upper_by if hi < step else "both_fail_at_every_step")})
    else:
        first = trials[0]
        out.update({"declared_gross": best["declared_gross"], "w_each": best["w_each"],
                    "gross": best["gross"], "book_k_sigma_frac": best["book_k_sigma_frac"],
                    "binding": (upper_by if best is first else
                                "one_day_k_sigma" if not first["bound_one_day"] else
                                "worst_21_session")})
    return out


def worst_case_lines(*, equity: float, n_declared: int, max_name_frac: float, w_each: float,
                     names: list[str], sigmas: dict, fallback: float, k: float,
                     other_weights: dict[str, float], history: Optional[dict],
                     max_gross: Optional[float] = None) -> dict:
    """Session protocol item 4, in dollars: the LARGEST ADMISSIBLE index
    (min(N x cap, owner max gross)) and the PLANNED one, alone and with the rest
    of the book."""
    eq = float(equity)
    avg = (sum(float(sigmas.get(s) or fallback) for s in names) / len(names)) if names else fallback
    big_g = n_declared * max_name_frac
    if max_gross is not None:
        big_g = min(big_g, float(max_gross))
    plan_g = w_each * len(names)
    other = book_k_sigma_frac(other_weights, sigmas, k=k, fallback=fallback)
    other_g = sum(max(0.0, float(w)) for w in other_weights.values())
    out = {"equity_usd": eq, "k_sigma": k, "avg_daily_sigma": avg,
           "largest_admissible": {"n": n_declared, "notional_frac": max_name_frac,
                                  "gross": big_g, "stop": "none",
                                  "k_sigma_usd": -big_g * k * avg * eq,
                                  "no_stop_ceiling_usd": -big_g * eq},
           "planned": {"n": len(names), "notional_frac": w_each, "gross": plan_g,
                       "k_sigma_usd": -plan_g * k * avg * eq,
                       "with_rest_of_book_k_sigma_usd": -(plan_g * k * avg + other) * eq,
                       "sum_notional_over_equity": plan_g + other_g}}
    lines = [
        (f"LARGEST ADMISSIBLE own index at ${eq:,.0f}: {big_g:.0%} gross (min of {n_declared} "
         f"names x {max_name_frac:.2%} = {n_declared * max_name_frac:.0%} and the owner's max "
         f"gross {'none' if max_gross is None else f'{float(max_gross):.0%}'}); no stop is "
         f"declared, so n x notional x stop = {big_g:.0%} x 100% = -${big_g * eq:,.0f}; rho=1 "
         f"{k:g}-sigma day {big_g:.0%} x {k:g} x {avg:.2%} = -${big_g * k * avg * eq:,.0f}"),
        (f"PLANNED own index: {len(names)} x {w_each:.2%} = {plan_g:.2%} gross; {k:g}-sigma day "
         f"-${plan_g * k * avg * eq:,.0f}; with the rest of the book ({other_g:.2%} gross) "
         f"-${(plan_g * k * avg + other) * eq:,.0f} ({plan_g * k * avg + other:.2%} of equity); "
         f"sum|notional|/equity {plan_g + other_g:.2f}"),
    ]
    if history and "worst_window_return" in history:
        ww = float(history["worst_window_return"])
        out["planned"]["worst_21_session_usd"] = plan_g * ww * eq
        out["largest_admissible"]["worst_21_session_usd"] = big_g * ww * eq
        lines.append(
            f"21-SESSION: the members' equal-weight basket's worst {history.get('window_sessions', 21)}"
            f"-session return {ww:.2%} (to {history.get('worst_window_end')}, all priced, "
            f"{history.get('panel')} {history.get('first')}..{history.get('last')}): planned "
            f"-${abs(plan_g * ww * eq):,.0f}, largest admissible -${abs(big_g * ww * eq):,.0f}; "
            f"worst day {float(history.get('worst_day_return') or 0):.2%} ({history.get('worst_day')})"
            + (f"; {history['warning']}" if history.get("warning") else ""))
    else:
        lines.append("21-SESSION: UNKNOWN ("
                     + str((history or {}).get("error") or "no history") + "): bound 2 fails")
    out["lines"] = lines
    return out


# ───────────────────────────── the plan ─────────────────────────────────────

def plan(*, contract: Optional[dict], members_row: Optional[dict], refusal: Optional[str],
         equity: float, held: dict[str, float], prices: dict[str, float],
         acting_weights: dict[str, float], claimed: set, held_residual: dict[str, float],
         sigmas: dict, fallback_sigma: float, history: Optional[dict], mode: str,
         core_symbol: str = "SPY", cfg: Any = None) -> dict:
    """One cycle of the own index: targets, the orders (pc_broker.plan_orders, in
    its own call so no other sleeve's share count moves), the old core's exit,
    the worst case and one receipt line. Never raises; never sends."""
    from backend.services import pc_broker as PB                   # noqa: PLC0415
    c = cfg or _cfg
    core = str(core_symbol).upper()
    out: dict = {"enabled": True, "applied": False, "acting": False, "state": STATE,
                 "contract_hash": (contract or {}).get("policy_hash"),
                 "contract_frozen_utc": (contract or {}).get("frozen_utc"),
                 "weights": {}, "plans": [], "state_of": {}}
    if contract is None:
        out["refused"] = refusal or "no valid frozen contract"
        out["exit_acting"] = False
        out["line"] = f"own index: REFUSED -- {out['refused']}; nothing moves (SPY is not sold either)"
        return out
    cc = contract["content"]
    members = list((members_row or {}).get("members") or [])
    prev = list((members_row or {}).get("previous_members") or [])
    owned = {s for s in set(members) | set(prev) if s in held and s not in claimed and s != core}
    spy_qty = float(held.get(core, 0.0) or 0.0)
    out["core_exit"] = {"symbol": core, "held_qty": spy_qty,
                        "sell_qty": int(math.floor(spy_qty)) if spy_qty >= 1 else 0,
                        "fractional_residual": spy_qty - math.floor(spy_qty) if spy_qty else 0.0}

    def _refuse(why: str, **extra: Any) -> dict:
        """Review2 #89 B1: a refusal of ANY kind holds EVERYTHING -- the held
        members, the leavers and the old core. No sell intent leaves a refusal:
        names leave only at a successful rebuild (members chosen AND sized),
        and SPY is retired only in the same plan that buys the index."""
        out.update(extra)
        out.update({"refused": why, "plans": [], "applied": False, "acting": False,
                    "exit_acting": False, "held_index_names": sorted(owned),
                    "weights": {}, "targets": []})
        out["core_exit"].update({"sell_qty": 0, "held_on_refusal": spy_qty > 0})
        for s in sorted(owned):
            out["state_of"][s] = HOLD_STATE
        if spy_qty > 0:
            out["state_of"][core] = HOLD_STATE
        out["line"] = (f"own index: REFUSED -- {why}; nothing is sold or bought: "
                       f"{len(owned)} held member(s) HELD"
                       + (f", {core} {spy_qty:g} sh HELD (retired only with a funded index)"
                          if spy_qty > 0 else ""))
        return out

    if refusal is not None or not members:
        return _refuse(refusal or "membership empty")
    short = set((history or {}).get("short_history") or [])
    names = [m for m in members if m not in claimed and m not in short]
    skipped = [m for m in members if m in claimed]
    skipped_short = [m for m in members if m not in claimed and m in short]
    out["skipped_short_history"] = skipped_short
    if not names:
        return _refuse(f"no member qualifies: in another acting sleeve {skipped}, "
                       f"short history {skipped_short}",
                       members=members, skipped_claimed=skipped)
    # a held member that is still a member but cannot be sized (short history)
    # is HELD, never sold: it has not left the index. Its weight counts against
    # the room and the one-day bound.
    held_short = sorted(owned & set(skipped_short))
    leavers = sorted(owned - set(members))
    k = float(c.PROBE_WORST_CASE_SIGMA)
    buf = float(cc["construction"]["cash_buffer"])
    acting = {s: float(w) for s, w in acting_weights.items() if float(w) > 0}
    resid = {s: float(w) for s, w in held_residual.items()
             if s not in owned and s != core and float(w) > 0}
    for s in held_short:
        px_s = float(prices.get(s) or 0.0)
        if px_s > 0 and float(equity) > 0:
            resid[s] = float(held.get(s, 0.0)) * px_s / float(equity)
    room = max(0.0, 1.0 - sum(acting.values()) - sum(resid.values()) - buf)
    ww = (history or {}).get("worst_window_return")
    pick = choose_gross(names=names, n_declared=int(cc["construction"]["n_declared"]),
                        max_name_frac=float(cc["construction"]["max_name_frac"]), room=room,
                        other_weights={**acting, **resid}, sigmas=sigmas,
                        fallback=fallback_sigma, k=k,
                        day_limit=float(cc["risk"]["one_day_book_limit_frac"]),
                        worst_21=(None if ww is None else float(ww)),
                        window_limit=float(cc["risk"]["worst_21_session_limit_frac"]),
                        step=float(cc["construction"]["gross_step"]),
                        max_gross=float(cc["construction"]["max_gross"]))
    w = float(pick["w_each"])
    weights = {s: w for s in names} if w > 0 else {}
    wc = worst_case_lines(equity=equity, n_declared=int(cc["construction"]["n_declared"]),
                          max_name_frac=float(cc["construction"]["max_name_frac"]), w_each=w,
                          names=names, sigmas=sigmas, fallback=fallback_sigma, k=k,
                          other_weights={**acting, **resid}, history=history,
                          max_gross=float(cc["construction"]["max_gross"]))
    adv = dict((members_row or {}).get("median_dollar_vol") or {})
    targets = [PB.Target(symbol=s, weight=w,
                         reason=(f"OWN_INDEX ({cc['version']} {contract['policy_hash'][:12]}): "
                                 f"equal weight {w:.2%}; PRODUCT_EXPERIMENT"),
                         median_dollar_vol=(float(adv[s]) if isinstance(adv.get(s), (int, float))
                                            else None))
               for s in names] if weights else []
    if not weights:
        return _refuse(f"worst case allows no index ({pick['binding']})",
                       members=members, names=names, skipped_claimed=skipped, sizing=pick,
                       worst_case=wc, worst_case_lines=wc["lines"])
    # the old core: sold whole-share, only in a plan that also buys the index
    core_plans = []
    if spy_qty >= 1:
        px = float(prices.get(core) or 0.0)
        q = int(math.floor(spy_qty))
        core_plans.append(PB.PlannedOrder(
            symbol=core, side="sell", qty=q if px > 0 else 0, notional=q * px,
            reason=(f"CORE_EXIT (OD-10, owner 2026-11-10): the strategic {core} core is retired; "
                    f"{core} is the benchmark only"),
            refused=(None if px > 0 else f"no price for {core}; cannot size safely"),
            current_qty=spy_qty, target_qty=spy_qty - q, price=px))
        out["state_of"][core] = CORE_EXIT_STATE
    for s in held_short:
        out["state_of"][s] = HOLD_STATE
    plan_held = {s: float(held.get(s, 0.0)) for s in (set(names) | set(leavers))}
    idx_plans = PB.plan_orders(targets, equity=equity, held=plan_held, prices=prices)
    for p in idx_plans:
        if p.symbol in weights:
            out["state_of"][p.symbol] = STATE
        else:
            p.reason = (f"OWN_INDEX_EXIT: left the index at the "
                        f"{(members_row or {}).get('frozen_utc', '?')[:10]} rebuild")
            out["state_of"][p.symbol] = EXIT_STATE
    for s in names:
        out["state_of"].setdefault(s, STATE)
    n_decl = int(cc["construction"]["n_declared"])
    out.update({
        "applied": bool(weights), "acting": bool(weights) and mode == "paper_profit",
        "exit_acting": mode == "paper_profit",
        "members": members, "names": names, "skipped_claimed": skipped,
        "adopted_held": sorted(owned & set(names)), "held_short_history": held_short,
        "leavers": leavers,
        "weights": weights, "w_each": w, "gross": w * len(names),
        "n_declared": n_decl, "n_slots_cash": n_decl - len(names),
        "membership": {k_: v for k_, v in (members_row or {}).items()
                       if k_ not in ("candidate_scores",)},
        "sizing": pick, "worst_case": wc, "worst_case_lines": wc["lines"],
        "targets": targets, "plans": core_plans + idx_plans})
    out["line"] = (f"own index ({cc['version']} {contract['policy_hash'][:12]}): {len(names)} of "
                   f"{n_decl} declared x {w:.2%} = {w * len(names):.2%} gross (binding: "
                   f"{pick['binding']}; room {room:.2%})"
                   + (f"; skipped, in another sleeve: {skipped}" if skipped else "")
                   + (f"; excluded, short history: {skipped_short}" if skipped_short else "")
                   + (f"; {n_decl - len(names)} slot(s) cash" if n_decl > len(names) else "")
                   + (f"; {core} {out['core_exit']['sell_qty']} sh -> CORE_EXIT" if core_plans else "")
                   + (f"; held, short history: {held_short}" if held_short else "")
                   + ("" if mode == "paper_profit" else f"; mode={mode}: not acting"))
    return out


def clip_buys_to_post_fill_gross(plans: list, *, held: dict, prices: dict, equity: float,
                                 sendable: Callable[[Any], bool], cash_buffer: float,
                                 clip_syms: set) -> Optional[dict]:
    """Price the book as it stands after every sendable order fills; if gross
    exceeds 1 - buffer, cut the index's buys (largest first) until it does not.
    Mutates `plans`; returns what was cut, or None."""
    qty = {s: float(q) for s, q in held.items()}
    for p in plans:
        if p.qty > 0 and sendable(p):
            qty[p.symbol] = qty.get(p.symbol, 0.0) + (p.qty if p.side == "buy" else -p.qty)
    post = sum(max(0.0, q) * float(prices.get(s) or 0.0) for s, q in qty.items())
    cap = (1.0 - float(cash_buffer)) * float(equity)
    if post <= cap + 1e-6:
        return None
    excess = post - cap
    cut: dict = {}
    for p in sorted((p for p in plans if p.symbol in clip_syms and p.side == "buy"
                     and p.qty > 0 and p.price > 0 and sendable(p)), key=lambda p: -p.notional):
        if excess <= 1e-6:
            break
        n = min(p.qty, int(math.ceil(excess / p.price)))
        p.qty -= n
        p.notional = p.qty * p.price
        p.target_qty = p.current_qty + p.qty
        excess -= n * p.price
        cut[p.symbol] = n
        if p.qty == 0:
            p.refused = "OWN_INDEX_CLIPPED_TO_POST_FILL_GROSS"
    return {"post_fill_gross_before": post / float(equity), "cut_shares": cut,
            "line": (f"OWN_INDEX_CLIPPED_TO_POST_FILL_GROSS: the book after fills would be "
                     f"{post / float(equity):.2%} of equity; index buys cut {cut}")}


def held_index_names(folder: Path, held: dict, *, exclude: set, core_symbol: str = "SPY") -> set:
    """Held names the membership file says are (or were) index members, minus
    `exclude` (an acting sleeve's claim). Read WITHOUT the contract, so a
    contract refusal or a rollback can HOLD them instead of exiting them."""
    row = _read_json(Path(folder) / MEMBERS_FILE) or {}
    idx = {str(s).upper() for s in (row.get("members") or [])} | {
        str(s).upper() for s in (row.get("previous_members") or [])}
    core = str(core_symbol).upper()
    return {s for s in held if str(s).upper() in idx and s not in exclude
            and str(s).upper() != core}


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def fill_lookup_method(broker: Any) -> Optional[str]:
    """How a broker module can confirm a fill by client order id (review2 #89
    B2): main's pc_broker has `order_by_client_id`; the RUNTIME's
    (wip/2026-10-07-day) has only `orders(status, limit, after)`. None means
    neither: the own index must not start, because a SPY sale could go out with
    no way to confirm it before the buys."""
    if callable(getattr(broker, "order_by_client_id", None)):
        return "order_by_client_id"
    if callable(getattr(broker, "orders", None)):
        return "orders"
    return None


#: orders(status="all") page size used to confirm fills on a broker without the
#: by-client-id lookup (Alpaca's maximum); newest first, so a session's sells
#: are on the first page.
FILL_LOOKUP_PAGE = 500


def _order_statuses(broker: Any, method: str, coids: list[str]) -> dict[str, str]:
    if method == "order_by_client_id":
        out = {}
        for c in coids:
            try:
                out[c] = str((broker.order_by_client_id(c) or {}).get("status"))
            except Exception as exc:                               # noqa: BLE001
                out[c] = f"unreadable ({type(exc).__name__})"
        return out
    try:
        rows = broker.orders(status="all", limit=FILL_LOOKUP_PAGE) or []
    except Exception as exc:                                       # noqa: BLE001
        return {c: f"unreadable ({type(exc).__name__})" for c in coids}
    by = {str(r.get("client_order_id")): str(r.get("status")) for r in rows
          if isinstance(r, dict)}
    return {c: by.get(c, "not listed") for c in coids}


def gate_index_buys(buys: list, *, sells: list, sent: list[dict], broker: Any,
                    cash_buffer: float, other_buys: list, wait_s: float, poll_s: float,
                    sleep: Optional[Callable[[float], None]] = None) -> dict:
    """Which index buys may go out NOW, and how many shares (review #89 R3).

    1. Every sell this session must have been SUBMITTED; a skipped or failed
       sell (an open order, a venue rejection) refuses every index buy.
    2. Every submitted sell must be confirmed FILLED by the broker within
       `wait_s`; anything else refuses every index buy. Confirmed through
       `order_by_client_id` where the broker has it, else `orders(status=all)`
       (the runtime's pc_broker); a broker with neither refuses at once.
    3. The broker's account is re-read AFTER the fills: budget = cash - buffer x
       equity - this session's other buys, and long market value + buys must
       stay <= (1 - buffer) x equity. Buys are cut, in order, to fit, each at
       plan price + BUY_PRICE_MARGIN; an unreadable account refuses.
    Returns {"allowed": {id(plan): qty}, "line", ...}; never sends."""
    sleep = sleep or _sleep
    by_sym: dict[str, list] = {}
    for r in sent:
        by_sym.setdefault(str(r.get("symbol")), []).append(r)
    out: dict = {"allowed": {}, "n_buys": len(buys), "n_sells": len(sells)}

    def _refuse(why: str) -> dict:
        out["refused"] = why
        out["line"] = f"OWN_INDEX buys REFUSED this session: {why}"
        return out
    coids = []
    for p in sells:
        rs = [r for r in by_sym.get(p.symbol, []) if r.get("side", "sell") == "sell"
              or r.get("status") != "submitted"]
        if not rs or any(r.get("status") != "submitted" for r in rs):
            st = (rs[-1].get("status") if rs else "not sent")
            why = (rs[-1].get("why") or rs[-1].get("error") or "") if rs else ""
            return _refuse(f"funding sell {p.symbol} {st}{(': ' + str(why)[:80]) if why else ''}"
                           f"; no index buy without it")
        coids += [(p.symbol, r.get("client_order_id")) for r in rs]
    pending = {c: s for s, c in coids}
    if None in pending:
        return _refuse(f"funding sell {pending[None]} has no client order id to confirm")
    method = fill_lookup_method(broker)
    out["fill_lookup"] = method
    if pending and method is None:
        return _refuse("the broker exposes no order lookup (neither order_by_client_id nor "
                       "orders): no fill can be confirmed")
    deadline = time.monotonic() + max(0.0, float(wait_s))
    last: dict = {}
    while pending:
        for c, st in _order_statuses(broker, method, list(pending)).items():
            last[pending[c]] = st
            if st == "filled":
                pending.pop(c)
        if not pending or time.monotonic() >= deadline:
            break
        sleep(max(0.0, float(poll_s)))
    if pending:
        return _refuse("funding sell(s) not confirmed filled within "
                       f"{float(wait_s):g} s: " + ", ".join(f"{s} {last.get(s)}"
                                                          for s in pending.values()))
    try:
        acct = broker.account() or {}
    except Exception as exc:                                       # noqa: BLE001
        return _refuse(f"account unreadable after the fills ({type(exc).__name__})")
    cash, eq, lmv = _f(acct.get("cash")), _f(acct.get("equity")), _f(acct.get("long_market_value"))
    if cash is None or eq is None or lmv is None or eq <= 0:
        return _refuse("account cash/equity/long_market_value unreadable after the fills")
    other = sum(max(0, int(p.qty)) * float(p.price or 0.0) for p in other_buys)
    buf = float(cash_buffer) * eq
    budget = min(cash - buf - other, (eq - buf) - lmv - other)
    out.update({"cash": cash, "equity": eq, "long_market_value": lmv, "other_buys_usd": other,
                "budget_usd": budget})
    if budget <= 0:
        return _refuse(f"no funded room after the fills: cash ${cash:,.0f}, long ${lmv:,.0f}, "
                       f"equity ${eq:,.0f}, buffer ${buf:,.0f}, other buys ${other:,.0f}")
    left, cut = budget, {}
    for p in buys:
        px = float(p.price or 0.0) * (1.0 + BUY_PRICE_MARGIN)
        q = min(int(p.qty), int(left // px)) if px > 0 else 0
        if q > 0:
            out["allowed"][id(p)] = q
            left -= q * px
        if q < int(p.qty):
            cut[p.symbol] = int(p.qty) - q
    out["cut_shares"] = cut
    out["line"] = (f"OWN_INDEX buys funded after {len(sells)} confirmed sell(s): budget "
                   f"${budget:,.0f} (cash ${cash:,.0f} - buffer ${buf:,.0f} - other buys "
                   f"${other:,.0f}; gross room ${(eq - buf) - lmv - other:,.0f})"
                   + (f"; cut {cut}" if cut else ""))
    return out


# ───────────────────────────── measurement ──────────────────────────────────

def measure(members_row: dict, bars_path: Path, *, benchmark: str = "SPY") -> dict:
    """Equal-weight buy-and-hold from the membership freeze day's close to the
    newest bar: the index, its random twin, the benchmark. An OBSERVATION."""
    import pandas as pd                                            # noqa: PLC0415
    members = list(members_row.get("members") or [])
    twin = list(((members_row.get("twin") or {}).get("weights") or {}).keys())
    syms = sorted(set(members) | set(twin) | {benchmark})
    df = pd.read_parquet(bars_path, columns=["symbol", "date", "close"],
                         filters=[("symbol", "in", syms)])
    wide = df.pivot_table(index="date", columns="symbol", values="close").sort_index()
    t0 = pd.Timestamp(str(members_row.get("frozen_utc"))[:10])
    base = wide[wide.index <= t0]
    if base.empty:
        return {"error": f"no bar on or before {t0.date()}"}
    p0, p1 = base.iloc[-1], wide.iloc[-1]

    def _ew(names: list) -> tuple[Optional[float], int]:
        r = [(float(p1[s]) / float(p0[s]) - 1.0) for s in names
             if s in wide and pd.notna(p0.get(s)) and pd.notna(p1.get(s)) and float(p0[s]) > 0]
        return ((sum(r) / len(r)) if r else None), len(r)
    idx, n_i = _ew(members)
    tw, n_t = _ew(twin)
    bm, _ = _ew([benchmark])
    out = {"from": str(base.index[-1].date()), "to": str(wide.index[-1].date()),
           "index_ew_return": idx, "n_index_priced": n_i, "twin_ew_return": tw,
           "n_twin_priced": n_t, f"{benchmark}_return": bm,
           "index_minus_benchmark": (None if idx is None or bm is None else idx - bm),
           "index_minus_twin": (None if idx is None or tw is None else idx - tw),
           "label": "OBSERVED: gross of costs, before any order; no skill claim"}
    return out
