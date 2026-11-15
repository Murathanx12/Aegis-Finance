"""Dynamic exposure book family (CH-45, 2026-11-15): one base selection, three
declared personalities, re-entered every rolling cohort.

WHAT THIS IS
============
The rolling cohorts (`branch_population_rolling`) enter a STATIC buy-and-hold
book per spec per cohort. CH-45 adds the smallest honest dynamic layer on top:
the same base book, with an exposure path that changes INSIDE a cohort's life
by a rule frozen in a contract before the first decision.

* growth        the base selection, held (exposure 1.0, no hedge);
* balanced      held, with rule (d) of the 11-14 market replay: after a declared
                leader's earnings-session gap-down of 5% or more, stock exposure
                0.5 for the next 5 sessions;
* preservation  held, with rule (b): while QQQ closes below its 50-session
                average, short QQQ at beta x NAV (beta of the book on QQQ over
                the previous 126 sessions, clipped to [0, 3]).

The rule definitions and parameters are the replay's (section 0 / 0b of
`aegis-recovery-evidence/s69-reports-20261114/council/replay/replay_findings.txt`,
code `s3_rules.py`), not tuned. Two stated departures, both on the side of
honesty: (1) rule (d) fires at the close of EACH of {announce session, next
session} whose own gap is <= -5% -- the replay chose the larger |gap| of the two,
which at the announce-day close peeks at the next open; (2) the QQQ short pays
the rolling machinery's borrow fee (the replay charged 0).

ONE CLOCK
=========
The book of cohort D enters at the open of E (the next session), exactly the
rolling cohort's book (same `market_features`, same `bar_targets`, so the same
holdings hash). The exposure held over session k is decided from data through
the CLOSE of session k-1 (for E: the close of D, which is before the cohort
cutoff E 00:00 UTC). Every path row records `signal_asof` (that close) and a
test recomputes every row from bars truncated at it.

WHAT IS STORED
==============
`<out>/declaration.json` (write-once: contract manifest + config), one
write-once `cohorts/dxb_cohort_<D>.json` per cohort (base holdings, sector share,
effective bets), and two append-only tables: `paths/part-<run>.parquet` (one row
per contract x cohort x session: exposure, hedge, the signal inputs, the daily
return) and `marks/part-<run>.parquet` (the 5..126-session marks). A row is
written only once its session has closed, and it never changes afterwards
because nothing it depends on is dated later. Backfilled cohorts carry
`backfilled: true` and are never forward evidence. The v2 spec file and the
rolling population's own files are read, never written.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.services.portfolio_intelligence.branch_population import digest

CONTRACTS_SCHEMA = "dynamic_exposure_contracts/1"
PATH_SCHEMA = "dynamic_exposure_path/1"
MARK_SCHEMA = "dynamic_exposure_mark/1"
COHORT_SCHEMA = "dynamic_exposure_cohort/1"
TASK_NAME = "AegisDynamicBooks"
REPO = R.REPO
CONTRACT_VERSION = "v2"
CONTRACTS_REL = "docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v2.json"
#: Superseded on 2026-11-15 before any forward decision (only a backfilled dry run in a
#: work folder ran under it). Kept byte for byte; never edited.
CONTRACTS_V1_REL = "docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v1.json"
CONTRACTS_V1_MANIFEST = "328a0c7337ef45b7aa29b6faf4921cf66e65cad82a6bb37db9edb06d6dab9294"
FACTS_FILE = "calendar_facts.jsonl"
CODE_VERSIONS_FILE = "code_versions_accepted.jsonl"
SPECS_V2_REL = "docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json"
EARNINGS_REL = "straddle_forward/earnings_cache.json"
UNIVERSE_REL = "potential_universe"
PERSONALITIES = ("growth", "balanced", "preservation")
REPLAY_SOURCE = ("aegis-recovery-evidence/s69-reports-20261114/council/replay/"
                 "replay_findings.txt sections 0, 0b, 3; s3_rules.py run_rule()")


class DynamicBookRefused(RuntimeError):
    """A dynamic book could not be built or marked honestly: refused, never guessed.

    Raised on a contract whose content no longer hashes to its id, a config that
    no longer equals the frozen contract, a base spec missing from the v2 file,
    a missing input file, or an exposure decision that would read data dated on
    or after the session it is applied to. The CLI turns it into exit 2."""


# ─────────────────────────────── contracts ──────────────────────────────────

def _rules() -> dict:
    c = _config
    return {
        "growth": {"id": "hold", "definition": "stock exposure 1.0 every session; no hedge"},
        "balanced": {
            "id": "d_leader_gap",
            "definition": ("at the close of a leader's earnings-reaction session s with "
                           "open_s / close_(s-1) - 1 <= gap_threshold, stock exposure = "
                           "gross_after_event for sessions s+1 .. s+sessions_after_event "
                           "(overlapping events: the minimum)"),
            "leaders": list(c.DYNAMIC_BOOK_LEADERS),
            "leader_since": dict(c.DYNAMIC_BOOK_LEADER_SINCE),
            "gap_threshold": c.DYNAMIC_BOOK_LEADER_GAP,
            "gross_after_event": c.DYNAMIC_BOOK_LEADER_GROSS,
            "sessions_after_event": c.DYNAMIC_BOOK_LEADER_SESSIONS,
            "earnings_dates": EARNINGS_REL + " (dates[] per leader)",
            "reaction_sessions": ("PIT form: the first session on/after the earnings date AND the "
                                  "session after it; each fires on its own gap. Replay: the larger "
                                  "|gap| of the two (peeks at the next open)"),
            "non_earnings_gaps": "do not fire (as the replay code ran; NVDA 11-09 / 11-12 2026 excluded)",
            "calendar_observation": ("a calendar fact (leader, report date) acts only on decisions taken at or "
                                     "after the run that FIRST RECORDED it (calendar_facts.jsonl, append-only, "
                                     "run stamp); a fact first recorded after the close of its reaction session "
                                     "is LEARNED_LATE and never acts retroactively. Facts recorded by the "
                                     "declaring run have an UNKNOWN observation time (the only pull on record "
                                     "is 2026-11-11); rows decided before the declaration carry "
                                     "calendar_observed: unknown"),
            "calendar_stale_days": c.DYNAMIC_BOOK_LEADER_CALENDAR_STALE_DAYS,
            "calendar_stale_rule": ("a leader is STALE when its newest known report is older than "
                                    "calendar_stale_days at the run, or its calendar pull predates the last "
                                    "session; a step with a STALE leader exits non-zero and names it")},
        "preservation": {
            "id": "b_qqq_trend_hedge",
            "definition": ("if close_(t-1)(QQQ) < SMA_sma_sessions(QQQ closes through t-1): short QQQ "
                           "over session t with notional beta_(t-1) x NAV; beta_(t-1) = OLS beta of the "
                           "book's daily returns on QQQ's over the beta_window sessions ending t-1, "
                           "clipped to beta_clip; otherwise no hedge"),
            "etf": c.DYNAMIC_BOOK_HEDGE_ETF, "sma_sessions": c.DYNAMIC_BOOK_HEDGE_SMA,
            "beta_window_sessions": c.DYNAMIC_BOOK_HEDGE_BETA_WINDOW,
            "beta_min_obs": c.DYNAMIC_BOOK_HEDGE_BETA_MIN_OBS,
            "beta_clip": list(c.DYNAMIC_BOOK_HEDGE_BETA_CLIP),
            "book_returns_for_beta": ("sessions <= D: the entry weights held at constant weight "
                                      "(backcast, cash at 0); sessions >= E: the book's realised NAV "
                                      "return, paired with QQQ over the same interval (E: open to close)")},
    }


def contract_bodies(*, frozen_utc: str, specs: dict) -> list[dict]:
    """The three contract bodies from config + the v2 base spec (no hashes yet)."""
    pid = _config.DYNAMIC_BOOK_BASE_POLICY_ID
    base = next((s for s in specs["specifications"] if s["policy_id"] == pid), None)
    if base is None:
        raise DynamicBookRefused(f"base policy {pid} is not in {SPECS_V2_REL}")
    rules = _rules()
    common = {
        "family": "dynamic_exposure_book", "license": "PRODUCT_EXPERIMENT",
        "frozen_utc": frozen_utc, "chunk": "CH-45",
        "base_selection": {"spec_file": SPECS_V2_REL, "spec_manifest_sha256": digest(specs),
                           "policy_id": pid, "semantic_sha256": base["semantic_sha256"],
                           "params": R.rolling_semantic(base),
                           "why": ("momentum is the high-beta family the fleet held (the replay's "
                                   "subject); hedge none so the preservation hedge is the only hedge; "
                                   "horizon 126 so 21/63/126 are marked; 40 names: the least "
                                   "sector-concentrated momentum spec (top-1 sector 24-33% over the "
                                   "10-15..11-12 cohorts vs 37-60% at 10 names); equal over "
                                   "volatility_aware on a tie (no estimated input). Chosen on "
                                   "construction and sector share, by a session that had ALREADY SEEN "
                                   "this window's returns (replay sections 1 and 3A and the live rolling "
                                   "scoreboard of 2026-11-14 preceded the freeze)"),
                           "hindsight": ("the balanced rule's gain in this window is one event (GOOGL "
                                         "2026-10-29), mostly one day (11-05), inside the episode the rule "
                                         "was written about; the replay's long-sample difference for the "
                                         "rule is +1.0 pp/yr (se 2.0). Not out-of-sample evidence")},
        "cohort_clock": {"anchor": _config.ROLLING_COHORT_ANCHOR,
                         "cadence_sessions": int(_config.ROLLING_COHORT_CADENCE_SESSIONS),
                         "entry": "open of the first session E after cohort date D",
                         "cutoff": "E 00:00 UTC (branch_population_rolling.clocks)",
                         "mark_sessions": [k for k in _config.ROLLING_COHORT_MARK_SESSIONS
                                           if k <= base["horizon_sessions"]],
                         "horizon_sessions": base["horizon_sessions"]},
        "decision_timing": ("exposure for session t is decided at the close of t-1 from data "
                            "through that close and traded at it; for E, the close of D. The balanced "
                            "cut reads a gap known at the OPEN of s and trades at the close of s "
                            "(executable). The preservation hedge reads the close of t-1 and trades AT "
                            "that same close: the replay's convention, not strictly executable (live use "
                            "needs a close-auction order sized before the close, or the next open)"),
        "supersedes": {"file": CONTRACTS_V1_REL, "manifest_sha256": CONTRACTS_V1_MANIFEST,
                       "why": ("v1 was superseded on 2026-11-15 BEFORE any forward decision: only a "
                               "backfilled dry run in a work folder ran under it. v2 changes: calendar "
                               "facts act only from their first recorded run (no retroactive cut); a STALE "
                               "leader calendar exits a step non-zero; the declaration binds the rolling "
                               "grading config and the code version; the base-selection wording states the "
                               "hindsight; the hedge timing is stated. Rules and parameters unchanged")},
        "fill_convention": ("base book: buy at the open of E, held (rolling grade rule v2: a name "
                            "with no valid open waits in cash at 0%); exposure and hedge changes at "
                            "the close of the deciding session; daily rebalanced to the exposure "
                            "fraction; cash and short collateral earn 0"),
        "costs": {"base_round_trip": "xs_ranker.COST_BPS_BY_BAND per name, half at entry, half at the mark",
                  "stock_exposure_change_bps": _config.DYNAMIC_BOOK_COST_STOCK_BPS,
                  "etf_hedge_change_bps": _config.DYNAMIC_BOOK_COST_ETF_BPS,
                  "hedge_borrow_bps_yr": _config.DYNAMIC_BOOK_HEDGE_BORROW_BPS_YR,
                  "exposure_starts_at": 1.0, "hedge_starts_at": 0.0},
        "inputs": ["prices_2025_26/bars.parquet (open, close, volume)", EARNINGS_REL,
                   "potential_universe/<newest>.jsonl identity.sector (report only)"],
        "source": REPLAY_SOURCE,
        "evidence_in_replay": "every rule difference near or below its MDE (3-21 pp/yr); no skill claim",
    }
    objectives = {
        "growth": "terminal wealth, aggressive personality: full exposure, no drawdown control",
        "balanced": "terminal wealth with a declared event cut: balanced personality",
        "preservation": ("drawdown first (preservation personality): accepts the replay's long-run "
                         "cost of the hedge (9-13 pp/yr) for a shallower drawdown"),
    }
    out = []
    for p in PERSONALITIES:
        out.append({**common, "contract_id": f"DXB-{p}-{CONTRACT_VERSION}", "personality": p,
                    "objective": objectives[p], "rule": rules[p]})
    return out


def seal(body: dict) -> dict:
    return {**body, "contract_sha256": digest({k: v for k, v in body.items() if k != "contract_sha256"})}


def compile_contracts(*, frozen_utc: str, specs: dict) -> dict:
    cs = [seal(b) for b in contract_bodies(frozen_utc=frozen_utc, specs=specs)]
    doc = {"schema": CONTRACTS_SCHEMA, "license": "PRODUCT_EXPERIMENT", "chunk": "CH-45",
           "note": ("immutable once written: a changed rule or parameter is a new contract id in a new "
                    "file, never an edit of this one"),
           "contracts": cs}
    doc["manifest_sha256"] = digest({k: v for k, v in doc.items() if k != "manifest_sha256"})
    return doc


def verify_contracts(doc: dict, specs: dict) -> dict[str, dict]:
    """Recompute every hash and compare the frozen rules with config. Refuses on any drift."""
    if doc.get("schema") != CONTRACTS_SCHEMA:
        raise DynamicBookRefused(f"not a {CONTRACTS_SCHEMA} file")
    if digest({k: v for k, v in doc.items() if k != "manifest_sha256"}) != doc.get("manifest_sha256"):
        raise DynamicBookRefused("contract manifest no longer hashes to manifest_sha256: the file was edited")
    out = {}
    for c in doc["contracts"]:
        if seal(c)["contract_sha256"] != c["contract_sha256"]:
            raise DynamicBookRefused(f"contract {c['contract_id']} was edited: its content no longer "
                                     f"hashes to its contract_sha256")
        out[c["personality"]] = c
    if tuple(sorted(out)) != tuple(sorted(PERSONALITIES)):
        raise DynamicBookRefused(f"contracts cover {sorted(out)}, expected {sorted(PERSONALITIES)}")
    fresh = {b["personality"]: b for b in contract_bodies(frozen_utc="-", specs=specs)}
    for p, c in out.items():
        for key in ("rule", "costs", "base_selection", "cohort_clock"):
            if fresh[p][key] != c[key]:
                raise DynamicBookRefused(
                    f"config or v2 spec no longer equals frozen contract {c['contract_id']} ({key}). "
                    f"A changed rule is a NEW contract id in a new file; restore the config or declare v2")
    return out


def load_contracts(path: Path, specs: dict) -> tuple[dict, dict[str, dict]]:
    p = Path(path)
    if not p.is_file():
        raise DynamicBookRefused(f"contracts file {p} is absent; run `compile-contracts` (attended)")
    doc = json.loads(p.read_bytes())
    return doc, verify_contracts(doc, specs)


# ──────────────────────────────── inputs ────────────────────────────────────

def load_earnings(data_root: Path) -> dict[str, list[pd.Timestamp]]:
    p = Path(data_root) / EARNINGS_REL
    if not p.is_file():
        raise DynamicBookRefused(f"earnings calendar {p} is absent: the leader-gap rule cannot see events")
    raw = json.loads(p.read_bytes())
    return {t: sorted(pd.Timestamp(d).normalize() for d in (raw.get(t) or {}).get("dates", []))
            for t in _config.DYNAMIC_BOOK_LEADERS}


def load_earnings_pulls(data_root: Path) -> dict[str, Optional[pd.Timestamp]]:
    """`pulled_utc` per leader. The cache keeps only reports dated BEFORE its pull,
    so a report after the pull is invisible until the next pull."""
    raw = json.loads((Path(data_root) / EARNINGS_REL).read_bytes())
    out: dict[str, Optional[pd.Timestamp]] = {}
    for t in _config.DYNAMIC_BOOK_LEADERS:
        v = (raw.get(t) or {}).get("pulled_utc")
        if not v:
            out[t] = None
            continue
        ts = pd.Timestamp(v)
        out[t] = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
    return out


def leader_calendar_status(earn: dict, pulls: dict, *, now: datetime, last_session: pd.Timestamp,
                           leaders_in_bars: Optional[set] = None) -> dict:
    """Per leader: the newest known report, its age at the run, the pull time, and
    STALE with the reason. A STALE leader cannot fire the rule on time."""
    lim = float(_config.DYNAMIC_BOOK_LEADER_CALENDAR_STALE_DAYS)
    today = pd.Timestamp(now.date())
    out = {}
    for t, ds in earn.items():
        past = [d for d in ds if d <= today]
        age = None if not past else int((today - past[-1]).days)
        pull = pulls.get(t)
        why = []
        if leaders_in_bars is not None and t not in leaders_in_bars:
            why.append("no bars for the leader")
        if age is None:
            why.append("no report date in the calendar")
        elif age > lim:
            why.append(f"newest report {past[-1].date()} is {age} days old (> {lim:.0f})")
        if pull is None:
            why.append("no pull time recorded")
        elif pull.tz_convert(None).normalize() < pd.Timestamp(last_session).normalize():
            why.append(f"calendar pulled {pull.isoformat()} before the last session "
                       f"{pd.Timestamp(last_session).date()}")
        out[t] = {"last": None if not past else past[-1].date().isoformat(), "age_days": age,
                  "pulled_utc": None if pull is None else pull.isoformat(),
                  "status": "STALE" if why else "OK", "why": why}
    return out


def record_calendar_facts(out: Path, earn: dict, pulls: dict, *, now: datetime, run_id: str,
                          baseline: bool) -> dict[tuple, dict]:
    """Append every (leader, report date) not yet on record, stamped with this run.
    Returns every fact on record. Never rewrites a line."""
    from backend.services import disk_guard
    path = Path(out) / FACTS_FILE
    facts: dict[tuple, dict] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf8").splitlines():
            if line.strip():
                f = json.loads(line)
                facts.setdefault((f["leader"], f["earnings_date"]), f)
    for t, ds in earn.items():
        for d in ds:
            key = (t, d.date().isoformat())
            if key in facts:
                continue
            f = {"schema": "dynamic_exposure_calendar_fact/1", "leader": t, "earnings_date": key[1],
                 "first_recorded_utc": now.isoformat(), "run_id": run_id, "baseline": bool(baseline),
                 "observation": "UNKNOWN (recorded by the declaring run)" if baseline else "RECORDED",
                 "cache_pulled_utc": None if pulls.get(t) is None else pulls[t].isoformat()}
            disk_guard.locked_append_line(path, json.dumps(f, sort_keys=True), fsync=True)
            facts[key] = f
    return facts


def fact_usable(fact: Optional[dict], decision: Optional[datetime]) -> bool:
    """A fact acts on a decision only if recorded at or before it (baseline facts:
    observation time unknown, usable, and the rows say so)."""
    if fact is None:
        return False
    if fact["baseline"]:
        return True
    return decision is not None and pd.Timestamp(fact["first_recorded_utc"]) <= pd.Timestamp(decision)


def load_sector_map(data_root: Path, *, asof: Optional[pd.Timestamp] = None) -> tuple[dict, str]:
    """book_dna's rule (identity.sector of the newest potential_universe file), but
    the newest file dated on/before `asof` when one is."""
    d = Path(data_root) / UNIVERSE_REL
    files = sorted(d.glob("*.jsonl")) if d.is_dir() else []
    if asof is not None:
        dated = [f for f in files if f.stem[:10] <= asof.date().isoformat()]
        files = dated or files
    if not files:
        return {}, "none"
    m = {}
    with files[-1].open(encoding="utf8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            s = (r.get("identity") or {}).get("sector")
            if s and r.get("symbol"):
                m[r["symbol"]] = s
    return m, f"{UNIVERSE_REL}/{files[-1].name} ({len(m)} symbols)"


def leader_events(bars: pd.DataFrame, earn: dict, sessions: list[pd.Timestamp]) -> list[dict]:
    """PIT leader gap-downs: one row per fired session, with the gap and its source date."""
    thr = float(_config.DYNAMIC_BOOK_LEADER_GAP)
    since = {k: pd.Timestamp(v) for k, v in _config.DYNAMIC_BOOK_LEADER_SINCE.items()}
    sub = bars[bars["symbol"].isin(list(earn))]
    opn = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last").reindex(sessions)
    cls = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(sessions)
    sidx = pd.DatetimeIndex(sessions)
    out = []
    for t, dates in earn.items():
        if t not in opn.columns:
            continue
        for d in dates:
            if t in since and d < since[t]:
                continue
            i = int(sidx.searchsorted(d))
            for j in (i, i + 1):
                if j < 1 or j >= len(sessions):
                    continue
                g = opn[t].iloc[j] / cls[t].iloc[j - 1] - 1.0
                if np.isfinite(g) and g <= thr:
                    out.append({"leader": t, "earnings_date": d.date().isoformat(),
                                "session": sessions[j].date().isoformat(), "gap": float(g)})
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: (e["session"], e["leader"])):
        if (e["leader"], e["session"]) not in seen:
            seen.add((e["leader"], e["session"]))
            uniq.append(e)
    return uniq


def replay_form_events(bars: pd.DataFrame, earn: dict, sessions: list[pd.Timestamp]) -> list[tuple]:
    """The replay's own selection (larger |gap| of the two candidates), for the
    comparison printed in the receipt only. Never used to decide exposure."""
    thr = float(_config.DYNAMIC_BOOK_LEADER_GAP)
    since = {k: pd.Timestamp(v) for k, v in _config.DYNAMIC_BOOK_LEADER_SINCE.items()}
    sub = bars[bars["symbol"].isin(list(earn))]
    opn = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last").reindex(sessions)
    cls = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(sessions)
    sidx = pd.DatetimeIndex(sessions)
    out = set()
    for t, dates in earn.items():
        if t not in opn.columns:
            continue
        for d in dates:
            if t in since and d < since[t]:
                continue
            i = int(sidx.searchsorted(d))
            if i < 1 or i >= len(sessions) - 1:
                continue
            gaps = [opn[t].iloc[j] / cls[t].iloc[j - 1] - 1 for j in (i, i + 1)]
            if not np.isfinite(gaps).any():
                continue
            j = (i, i + 1)[int(np.nanargmax(np.abs(gaps)))]
            g = opn[t].iloc[j] / cls[t].iloc[j - 1] - 1
            if g <= thr:
                out.add((t, sessions[j].date().isoformat()))
    return sorted(out)


# ───────────────────────────── exposure rules ───────────────────────────────

def _ols_beta(y: np.ndarray, x: np.ndarray, min_obs: int) -> Optional[float]:
    m = np.isfinite(y) & np.isfinite(x)
    if int(m.sum()) < min_obs:
        return None
    xm, ym = x[m] - x[m].mean(), y[m] - y[m].mean()
    vx = float((xm * xm).sum())
    return None if vx <= 0 else float((xm * ym).sum() / vx)


def exposure_path(personality: str, *, days: list[pd.Timestamp], sessions: list[pd.Timestamp],
                  base_ret: np.ndarray, q_ret: np.ndarray, q_close: pd.Series,
                  pre_book_ret: pd.Series, pre_q_ret: pd.Series, events: list[dict],
                  facts: Optional[dict] = None, decision_utc: Optional[dict] = None) -> list[dict]:
    """Exposure e_k and hedge h_k for each cohort session k, from data through the
    close of the previous session only.

    `days` are the cohort's sessions E, E+1, ...; `sessions` the full calendar;
    `base_ret[k]` / `q_ret[k]` the book's and QQQ's return over session k (k = 0:
    open to close); `q_close` QQQ closes over `sessions` (history included);
    `pre_book_ret` / `pre_q_ret` close-to-close returns for sessions <= D.
    """
    sidx = {s: i for i, s in enumerate(sessions)}
    n = len(days)
    rows = []
    if personality == "growth":
        for k in range(n):
            prev = sessions[sidx[days[k]] - 1]
            rows.append({"k": k + 1, "date": days[k], "signal_asof": prev, "exposure": 1.0, "hedge": 0.0,
                         "fired": None})
        return rows
    if personality == "balanced":
        L = int(_config.DYNAMIC_BOOK_LEADER_SESSIONS)
        gross = float(_config.DYNAMIC_BOOK_LEADER_GROSS)
        ev = [(sidx[pd.Timestamp(e["session"])], e) for e in events if pd.Timestamp(e["session"]) in sidx]
        for k in range(n):
            i = sidx[days[k]]
            prev = sessions[i - 1]
            dec = None if decision_utc is None else decision_utc.get(prev)
            if facts is not None and dec is None:
                raise DynamicBookRefused(f"no decision time for the close of {prev.date()}")
            live = [e for j, e in ev if 1 <= i - j <= L            # event session j <= i-1: known at that close
                    and (facts is None or fact_usable(facts.get((e["leader"], e["earnings_date"])), dec))]
            e_k = gross if live else 1.0
            rows.append({"k": k + 1, "date": days[k], "signal_asof": prev, "exposure": e_k, "hedge": 0.0,
                         "fired": ";".join(f"{e['leader']}@{e['session']}({e['gap']:+.3f})" for e in live) or None})
        return rows
    if personality == "preservation":
        sma_n = int(_config.DYNAMIC_BOOK_HEDGE_SMA)
        win = int(_config.DYNAMIC_BOOK_HEDGE_BETA_WINDOW)
        lo, hi = _config.DYNAMIC_BOOK_HEDGE_BETA_CLIP
        min_obs = int(_config.DYNAMIC_BOOK_HEDGE_BETA_MIN_OBS)
        qc = q_close.reindex(sessions)
        # beta series: pre-entry backcast pairs, then realised pairs, in session order
        pairs_y = list(pre_book_ret.to_numpy(dtype=float))
        pairs_x = list(pre_q_ret.to_numpy(dtype=float))
        for k in range(n):
            i = sidx[days[k]]
            prev = sessions[i - 1]
            hist = qc.iloc[: i].dropna()                           # closes through t-1 only
            h_k, beta, sma, last = 0.0, None, None, None
            if len(hist) >= sma_n:
                sma = float(hist.iloc[-sma_n:].mean())
                last = float(hist.iloc[-1])
                y, x = np.array(pairs_y[-win:]), np.array(pairs_x[-win:])
                beta = _ols_beta(y, x, min_obs)
                if last < sma and beta is not None:
                    h_k = float(min(hi, max(lo, beta)))
            rows.append({"k": k + 1, "date": days[k], "signal_asof": prev, "exposure": 1.0, "hedge": h_k,
                         "qqq_close_prev": last, "qqq_sma_prev": sma, "beta_prev": beta,
                         "fired": "QQQ<SMA50" if h_k > 0 else None})
            pairs_y.append(float(base_ret[k]))                     # session k becomes known at its close
            pairs_x.append(float(q_ret[k]))
        return rows
    raise DynamicBookRefused(f"unknown personality {personality!r}")


def apply_path(rows: list[dict], base_ret: np.ndarray, q_ret: np.ndarray) -> list[dict]:
    """Daily net return of the dynamic book (before the base band round trip)."""
    cs, ce = _config.DYNAMIC_BOOK_COST_STOCK_BPS / 1e4, _config.DYNAMIC_BOOK_COST_ETF_BPS / 1e4
    borrow = _config.DYNAMIC_BOOK_HEDGE_BORROW_BPS_YR / 1e4 / 252.0
    e_prev, h_prev, nav = 1.0, 0.0, 1.0
    for r, b, q in zip(rows, base_ret, q_ret):
        if not pd.Timestamp(r["signal_asof"]) < pd.Timestamp(r["date"]):
            raise DynamicBookRefused(f"exposure for {r['date']} read data dated {r['signal_asof']}")
        e, h = r["exposure"], r["hedge"]
        cost = cs * abs(e - e_prev) + ce * abs(h - h_prev) + borrow * h
        x = e * float(b) - h * float(q) - cost
        nav *= 1.0 + x
        r.update(base_ret=float(b), qqq_ret=float(q), rule_cost=cost, ret=x, nav=nav)
        e_prev, h_prev = e, h
    return rows


# ──────────────────────────────── per cohort ────────────────────────────────

def base_book(spec: dict, market: pd.DataFrame) -> tuple[dict, float, str]:
    long_w, short = R.bar_targets(spec, market)
    if not long_w:
        raise DynamicBookRefused("the base selection has no eligible names for this cohort")
    return long_w, short, R.holdings_hash(long_w, short)


def entry_stats(long_w: dict, bars: pd.DataFrame, cohort: pd.Timestamp, sector_map: dict,
                market: pd.DataFrame) -> dict:
    """Sector share (book_dna.concentration) and effective bets (book_dna.
    participation_ratio) on return correlations over the window ending at D."""
    from backend.services import book_dna as BD
    conc = BD.concentration(long_w, sector_map)
    n_win = int(_config.DYNAMIC_BOOK_BETS_WINDOW)
    sess = R.bench_sessions(bars, through=cohort)[-(n_win + 1):]
    sub = bars[bars["symbol"].isin(list(long_w) + [R.BENCH]) & bars["date"].isin(sess)]
    rets = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(sess) \
        .pct_change(fill_method=None).iloc[1:]
    names = [t for t in sorted(long_w) if t in rets.columns and rets[t].notna().mean() >= 0.9]
    out = {"sector": conc, "bets_window_sessions": n_win, "bets_names_used": len(names)}
    if len(names) >= 2:
        M = rets[names].fillna(0.0).to_numpy()
        raw = np.corrcoef(M.T)
        spy = rets[R.BENCH].fillna(0.0).to_numpy()
        vs = float(np.var(spy))
        res = np.column_stack([M[:, i] - (np.cov(spy, M[:, i], ddof=0)[0, 1] / vs if vs > 0 else 0.0) * spy
                               for i in range(M.shape[1])])
        out.update(effective_bets_raw=round(BD.participation_ratio(raw), 2),
                   effective_bets_spy_residual=round(BD.participation_ratio(np.corrcoef(res.T)), 2),
                   median_pairwise_corr=round(float(np.median(raw[np.triu_indices(len(names), 1)])), 3))
    beta_book = float(sum(w * float(market.at[t, "beta252"]) for t, w in long_w.items()
                          if t in market.index and pd.notna(market.at[t, "beta252"])))
    q = _config.DYNAMIC_BOOK_HEDGE_ETF
    out["beta_ex_ante"] = beta_book
    out["beta_qqq_on_spy"] = (float(market.at[q, "beta252"]) if q in market.index
                              and pd.notna(market.at[q, "beta252"]) else None)
    return out


def cohort_series(long_w: dict, bars: pd.DataFrame, sessions: list[pd.Timestamp], cohort: pd.Timestamp,
                  entry: pd.Timestamp, through: pd.Timestamp, horizon: int) -> dict:
    """Base NAV path (the rolling grade rule), QQQ path, and the pre-entry backcast."""
    q = _config.DYNAMIC_BOOK_HEDGE_ETF
    i0 = sessions.index(entry)
    days = [s for s in sessions[i0: i0 + horizon] if s <= through]
    need = list(long_w) + [R.BENCH, q]
    sub = bars[bars["symbol"].isin(need)]
    close_all = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    open_all = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last")
    if q not in close_all.columns:
        raise DynamicBookRefused(f"{q} has no bars: the preservation hedge cannot be priced")
    close, opn = close_all.reindex(days), open_all.reindex(days)
    spy_c = close[R.BENCH].to_numpy(dtype=float)
    spy_o0 = float(opn[R.BENCH].iloc[0])
    nav, deferred = R._path_for(long_w, 0.0, close, opn, spy_c, spy_o0)
    base_ret = nav / np.concatenate([[1.0], nav[:-1]]) - 1.0
    qc = close[q].to_numpy(dtype=float)
    q_ret = np.concatenate([[qc[0] / float(opn[q].iloc[0]) - 1.0], qc[1:] / qc[:-1] - 1.0])
    win = int(_config.DYNAMIC_BOOK_HEDGE_BETA_WINDOW)
    pre = [s for s in sessions if s <= cohort][-(win + 1):]
    pc = close_all.reindex(pre)
    pr = pc.pct_change(fill_method=None).iloc[1:]
    cols = [t for t in long_w if t in pr.columns]
    pre_book = (pr[cols].fillna(0.0) * pd.Series({t: long_w[t] for t in cols})).sum(axis=1)
    return {"days": days, "base_ret": base_ret, "q_ret": q_ret, "spy_ret_cum": spy_c / spy_o0 - 1.0,
            "q_close": close_all[q].reindex(sessions), "pre_book_ret": pre_book, "pre_q_ret": pr[q],
            "deferred": deferred}


def band_cost(long_w: dict, market: pd.DataFrame) -> float:
    """The rolling book's round trip (half at entry, half at the mark), as a fraction."""
    half = sum(w * float(market.at[t, "cost_bps"]) if t in market.index else w * 35.0
               for t, w in long_w.items()) / 2.0
    return 2 * half / 1e4


def mark_row(contract: dict, cohort: dict, rows: list[dict], k: int, *, spy_cum: np.ndarray,
             band: float, stats: dict, gross_long: float, run_id: str, provisional: bool = False) -> dict:
    sub = rows[:k]
    nav = np.array([r["nav"] for r in sub])
    gross = float(nav[-1] - 1.0)
    net = gross - band
    spy = float(spy_cum[k - 1])
    bq = stats.get("beta_qqq_on_spy") or 0.0
    beta_eff = float(np.mean([r["exposure"] * stats["beta_ex_ante"] - r["hedge"] * bq for r in sub]))
    path = np.concatenate([[1.0], nav])
    dd = float((path / np.maximum.accumulate(path) - 1.0).min())
    e = np.array([r["exposure"] for r in sub])
    h = np.array([r["hedge"] for r in sub])
    book = float(_config.DYNAMIC_BOOK_REPORT_EQUITY_USD)
    fired = [r for r in sub if r.get("fired")]
    return {"schema": MARK_SCHEMA, "run_id": run_id, "contract_id": contract["contract_id"],
            "contract_sha256": contract["contract_sha256"], "personality": contract["personality"],
            "cohort_id": cohort["cohort_id"], "entry_session": cohort["entry_session"],
            "backfilled": bool(cohort["backfilled"]), "forward_evidence": not cohort["backfilled"],
            "provisional": provisional, "mark_k": k, "mark_date": sub[-1]["date"].date().isoformat(),
            "holdings_hash": cohort["holdings_hash"], "ret_gross": gross, "ret_net": net,
            "base_band_cost": band, "rule_cost": float(sum(r["rule_cost"] for r in sub)),
            "spy_ret": spy, "excess_vs_spy": net - spy, "beta_eff": beta_eff,
            "beta_adj_excess": net - beta_eff * spy, "max_drawdown": dd,
            "worst_case_usd": -book * float(e.max()) * gross_long * float(_config.DYNAMIC_BOOK_WORST_GAP),
            "worst_day_usd": book * float(min(r["ret"] for r in sub)),
            "gross_notional_max": float((e * gross_long + h).max()),
            "gross_notional_admissible": float(gross_long + (_config.DYNAMIC_BOOK_HEDGE_BETA_CLIP[1]
                                                             if contract["personality"] == "preservation" else 0.0)),
            "squeeze_usd_observed": -book * float(h.max()) * float(_config.DYNAMIC_BOOK_SQUEEZE_QQQ_UP),
            "squeeze_usd_admissible": -book * float(_config.DYNAMIC_BOOK_SQUEEZE_QQQ_UP) * (
                float(_config.DYNAMIC_BOOK_HEDGE_BETA_CLIP[1]) if contract["personality"] == "preservation"
                else 0.0),
            "calendar_observed_unknown_sessions": int(sum(r.get("calendar_observed") == "unknown" for r in sub)),
            "sessions_cut": int((e < 1).sum()), "sessions_hedged": int((h > 0).sum()),
            "mean_exposure": float(e.mean()), "mean_hedge": float(h.mean()),
            "first_rule_session": fired[0]["date"].date().isoformat() if fired else None,
            "last_rule_session": fired[-1]["date"].date().isoformat() if fired else None,
            "sector_top1": (stats["sector"].get("top_sector") or {}).get("weight_of_covered"),
            "sector_top1_name": (stats["sector"].get("top_sector") or {}).get("sector"),
            "effective_bets": stats.get("effective_bets_raw"),
            "effective_bets_spy_residual": stats.get("effective_bets_spy_residual")}


# ──────────────────────────────── store ─────────────────────────────────────

def _append(dirpath: Path, rows: list[dict], run_id: str) -> Optional[Path]:
    if not rows:
        return None
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / f"part-{run_id}.parquet"
    tmp = p.with_suffix(".tmp")
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    os.replace(tmp, p)
    return p


def _read(dirpath: Path) -> pd.DataFrame:
    parts = sorted(dirpath.glob("part-*.parquet")) if dirpath.is_dir() else []
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) if parts else pd.DataFrame()


def config_snapshot() -> dict:
    snap = {k: getattr(_config, k) for k in sorted(dir(_config)) if k.startswith("DYNAMIC_BOOK_")}
    return json.loads(json.dumps(snap, sort_keys=True, default=list))


def output_dir(data_root: Path, out: Optional[Path]) -> Path:
    own = (Path(data_root) / "dynamic_books").resolve()
    o = (Path(out) if out is not None else own).resolve()
    root = Path(data_root).resolve()
    if (o == root or root in o.parents) and not (o == own or own in o.parents):
        raise DynamicBookRefused(f"--out {o} is inside the data root; only {own} is allowed there")
    return o


# ──────────────────────────────── the runner ────────────────────────────────

def run(mode: str, *, data_root: Path, out: Path, contracts_path: Optional[Path] = None,
        specs_path: Optional[Path] = None, asof: Any = None, now: Optional[datetime] = None,
        date_from: Any = None, date_to: Any = None, calendar: Any = None,
        rolling_out: Optional[Path] = None, accept_code_version: bool = False) -> dict:
    """`backfill`: every scheduled cohort in [from, to] whose entry is in the bars,
    flagged backfilled. `step`: the due cohort if its entry has not opened (forward).
    Both then extend the append-only paths and marks. Never writes under data_root
    (except `<data_root>/dynamic_books`)."""
    now = now or datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:6]
    specs, manifest = R.load_specs(Path(specs_path or REPO / SPECS_V2_REL))
    cdoc, contracts = load_contracts(Path(contracts_path or REPO / CONTRACTS_REL), specs)
    for k, v in (("stock", _config.DYNAMIC_BOOK_COST_STOCK_BPS), ("etf", _config.DYNAMIC_BOOK_COST_ETF_BPS),
                 ("borrow", _config.DYNAMIC_BOOK_HEDGE_BORROW_BPS_YR)):
        if not v > 0:
            raise DynamicBookRefused(f"a {k} cost <= 0 is refused ({v})")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    decl_p = out / "declaration.json"
    snap = config_snapshot()
    rsnap = R.config_snapshot()              # xs_ranker band costs, MIN_PRICE, every ROLLING_COHORT_* filter
    code = R.code_version()
    declaring = not decl_p.is_file()
    code_note = None
    if not declaring:
        d = json.loads(decl_p.read_bytes())
        if d["contracts_manifest_sha256"] != cdoc["manifest_sha256"] or d["config"] != snap:
            raise DynamicBookRefused("this --out was declared under other contracts or another config; "
                                     "a changed family is a new --out")
        if d.get("rolling_config") != rsnap:
            diff = sorted(k for k in set(d.get("rolling_config") or {}) | set(rsnap)
                          if (d.get("rolling_config") or {}).get(k) != rsnap.get(k))
            raise DynamicBookRefused(f"the rolling grading config the base book depends on changed since the "
                                     f"declaration: {', '.join(diff)}. A changed base is a new --out")
        accepted = {d.get("code_version")}
        cv_p = out / CODE_VERSIONS_FILE
        if cv_p.is_file():
            accepted |= {json.loads(x)["code_version"] for x in cv_p.read_text(encoding="utf8").splitlines()
                         if x.strip()}
        if code not in accepted:
            if not accept_code_version:
                raise DynamicBookRefused(
                    f"code version {code} differs from the declared {d.get('code_version')} and from every "
                    f"accepted one; rerun attended with --accept-code-version (the stored-vs-recompute check "
                    f"still refuses any changed row)")
            from backend.services import disk_guard
            disk_guard.locked_append_line(cv_p, json.dumps({"code_version": code, "accepted_utc": now.isoformat(),
                                                            "run_id": run_id}, sort_keys=True), fsync=True)
            code_note = f"code version {code} accepted (attended)"
        declared_utc = pd.Timestamp(d["declared_utc"])
    else:
        R._write_once(decl_p, json.dumps({"schema": "dynamic_exposure_declaration/2", "task": TASK_NAME,
                                          "declared_utc": now.isoformat(),
                                          "contracts_manifest_sha256": cdoc["manifest_sha256"],
                                          "contracts": {c["contract_id"]: c["contract_sha256"]
                                                        for c in contracts.values()},
                                          "spec_manifest_sha256": manifest, "config": snap,
                                          "rolling_config": rsnap, "rolling_config_hash": digest(rsnap),
                                          "code_version": code, "license": "PRODUCT_EXPERIMENT"},
                                         sort_keys=True, indent=1, default=list))
        declared_utc = pd.Timestamp(now)
    spec = next(s for s in specs["specifications"] if s["policy_id"] == _config.DYNAMIC_BOOK_BASE_POLICY_ID)
    horizon = int(spec["horizon_sessions"])
    anchor = pd.Timestamp(_config.ROLLING_COHORT_ANCHOR)
    through = pd.Timestamp(asof).normalize() if asof is not None else pd.Timestamp(now.date())
    bars = R.load_bars(data_root, start=anchor - pd.Timedelta(days=400), end=through)
    sessions = R.bench_sessions(bars)
    if not sessions or sessions[-1] < anchor:
        raise DynamicBookRefused(f"the bars do not reach the anchor {anchor.date()}")
    last_bar = sessions[-1]
    sched = R.schedule(sessions, anchor=anchor, cadence=int(_config.ROLLING_COHORT_CADENCE_SESSIONS))
    earn = load_earnings(data_root)
    pulls = load_earnings_pulls(data_root)
    cal = calendar or R.XnysCalendar()
    in_bars = set(bars.loc[bars["symbol"].isin(list(earn)), "symbol"].unique())
    cal_status = leader_calendar_status(earn, pulls, now=now, last_session=last_bar, leaders_in_bars=in_bars)
    stale = {t: v["why"] for t, v in cal_status.items() if v["status"] == "STALE"}
    facts = record_calendar_facts(out, earn, pulls, now=now, run_id=run_id, baseline=declaring)
    first = max(0, sessions.index(sched[0]) - 1)
    decision_utc = {s: pd.Timestamp(cal.close_of(s)) for s in sessions[first:]}
    events = leader_events(bars, earn, sessions)
    for e in events:
        f = facts.get((e["leader"], e["earnings_date"]))
        close_s = decision_utc.get(pd.Timestamp(e["session"]))
        e["fact_first_recorded_utc"] = None if f is None else f["first_recorded_utc"]
        e["status"] = ("NOT_RECORDED" if f is None else "BASELINE_OBSERVATION_UNKNOWN" if f["baseline"] else
                       "ON_TIME" if close_s is not None and pd.Timestamp(f["first_recorded_utc"]) <= close_s
                       else "LEARNED_LATE")
    cdir = out / "cohorts"
    existing = {}
    if cdir.is_dir():
        for p in sorted(cdir.glob("dxb_cohort_*.json")):
            c = json.loads(p.read_bytes())
            existing[c["cohort_id"]] = c
    born, skipped = [], []

    def _birth(d: pd.Timestamp, entry: pd.Timestamp, backfilled: bool) -> None:
        market = R.market_features(bars, d)
        long_w, short, hh = base_book(spec, market)
        smap, ssrc = load_sector_map(data_root, asof=d)
        stats = entry_stats(long_w, bars, d, smap, market)
        rec = {"schema": COHORT_SCHEMA, "cohort_id": d.date().isoformat(),
               "entry_session": entry.date().isoformat(), "backfilled": bool(backfilled),
               "forward_evidence": not backfilled, "born_utc": now.isoformat(),
               "base_policy_id": spec["policy_id"], "long": long_w, "short": short, "holdings_hash": hh,
               "gross_long": float(sum(long_w.values())), "n_names": len(long_w),
               "band_round_trip": band_cost(long_w, market), "market_hash": R._frame_hash(market),
               "stats": stats, "sector_source": ssrc,
               "contracts": {c["contract_id"]: c["contract_sha256"] for c in contracts.values()},
               "price_filter_uses_adjusted": bool(backfilled),
               "panel_universe_asof": _config.ROLLING_COHORT_PANEL_UNIVERSE_ASOF}
        if rolling_out is not None:
            rp = Path(rolling_out) / "cohorts" / f"cohort_{rec['cohort_id']}.json"
            if rp.is_file():
                rc = json.loads(rp.read_bytes())
                rb = next((b for b in rc["books"] if b["policy_id"] == spec["policy_id"]), None)
                rec["rolling_crosscheck"] = ("NO_BOOK" if rb is None or rb.get("status") != "READY" else
                                             "MATCH" if rb["holdings_hash"] == hh else
                                             f"DIFF ({rb['holdings_hash']} vs {hh})")
            else:
                rec["rolling_crosscheck"] = "NO_ROLLING_COHORT"
        cdir.mkdir(parents=True, exist_ok=True)
        R._write_once(cdir / f"dxb_cohort_{rec['cohort_id']}.json",
                      json.dumps(rec, sort_keys=True, allow_nan=False, default=float))
        existing[rec["cohort_id"]] = rec
        born.append(rec["cohort_id"])

    if mode == "backfill":
        lo = pd.Timestamp(date_from) if date_from is not None else anchor
        hi = pd.Timestamp(date_to) if date_to is not None else last_bar
        for d in sched:
            if not lo <= d <= hi or d.date().isoformat() in existing:
                continue
            i = sessions.index(d)
            if i + 1 >= len(sessions):
                skipped.append({"cohort_id": d.date().isoformat(),
                                "why": "FORWARD_WINDOW_OPEN: its entry is not in the bars; the step births it"})
                continue
            _birth(d, sessions[i + 1], backfilled=True)
    elif mode == "step":
        d = sched[-1]
        if d.date().isoformat() not in existing:
            entry_open = cal.next_open_after(d)
            if d == last_bar and now < entry_open:
                _birth(d, pd.Timestamp(entry_open.date()), backfilled=False)
            else:
                skipped.append({"cohort_id": d.date().isoformat(),
                                "why": f"entry open {entry_open.isoformat()} passed or bars not at {d.date()}"})
    else:
        raise DynamicBookRefused(f"unknown mode {mode!r}")

    have_p = _read(out / "paths")
    have_m = _read(out / "marks")
    pkeys = set(zip(have_p["contract_sha256"], have_p["cohort_id"], have_p["k"])) if len(have_p) else set()
    mkeys = set(zip(have_m["contract_sha256"], have_m["cohort_id"], have_m["mark_k"])) if len(have_m) else set()
    stored = ({(r.contract_sha256, r.cohort_id, int(r.k)): (r.exposure, r.hedge, r.nav)
               for r in have_p[["contract_sha256", "cohort_id", "k", "exposure", "hedge", "nav"]].itertuples()}
              if len(have_p) else {})
    mismatch: list = []
    new_p, new_m, table = [], [], []
    marks_k = [k for k in _config.ROLLING_COHORT_MARK_SESSIONS if k <= horizon]
    for cid in sorted(existing):
        c = existing[cid]
        entry = pd.Timestamp(c["entry_session"])
        if entry not in set(sessions):
            continue
        paths, ser = compute_cohort(c, bars, sessions, earn, horizon=horizon, through=last_bar, facts=facts,
                                    decision_utc=decision_utc)
        for p in PERSONALITIES:
            ct = contracts[p]
            rows = paths[p]
            for r in rows:
                dec = decision_utc[pd.Timestamp(r["signal_asof"])]
                r["calendar_observed"] = ("n/a" if p != "balanced" else
                                          "unknown" if dec < declared_utc else "recorded")
                key = (ct["contract_sha256"], cid, r["k"])
                if key in stored:
                    se, sh, sn = stored[key]
                    if abs(se - r["exposure"]) > 1e-12 or abs(sh - r["hedge"]) > 1e-12 or abs(sn - r["nav"]) > 1e-12:
                        mismatch.append({"contract": ct["contract_id"], "cohort": cid, "k": r["k"],
                                         "stored": [se, sh, sn], "recomputed": [r["exposure"], r["hedge"], r["nav"]]})
                if key in pkeys:
                    continue
                new_p.append({"schema": PATH_SCHEMA, "run_id": run_id, "contract_id": ct["contract_id"],
                              "contract_sha256": ct["contract_sha256"], "personality": p, "cohort_id": cid,
                              "backfilled": bool(c["backfilled"]), "k": r["k"],
                              "date": r["date"].date().isoformat(),
                              "signal_asof": pd.Timestamp(r["signal_asof"]).date().isoformat(),
                              "exposure": r["exposure"], "hedge": r["hedge"], "fired": r.get("fired"),
                              "qqq_close_prev": r.get("qqq_close_prev"), "qqq_sma_prev": r.get("qqq_sma_prev"),
                              "beta_prev": r.get("beta_prev"), "calendar_observed": r["calendar_observed"],
                              "decision_utc": dec.isoformat(), "base_ret": r["base_ret"],
                              "qqq_ret": r["qqq_ret"], "rule_cost": r["rule_cost"], "ret": r["ret"],
                              "nav": r["nav"]})
            band = float(c["band_round_trip"])
            for k in marks_k:
                if k <= len(rows) and (ct["contract_sha256"], cid, k) not in mkeys:
                    new_m.append(mark_row(ct, c, rows, k, spy_cum=ser["spy_ret_cum"], band=band,
                                          stats=c["stats"], gross_long=c["gross_long"], run_id=run_id))
            if rows:
                table.append(mark_row(ct, c, rows, len(rows), spy_cum=ser["spy_ret_cum"], band=band,
                                      stats=c["stats"], gross_long=c["gross_long"], run_id=run_id,
                                      provisional=len(rows) not in marks_k))
    if mismatch:
        raise DynamicBookRefused(
            f"{len(mismatch)} stored path row(s) differ from the recompute (first: {mismatch[0]}). A stored "
            f"row is evidence and never changes; nothing was appended. Diagnose the input that moved "
            f"(bars re-adjusted, calendar, code) before any further run")
    pp = _append(out / "paths", new_p, run_id)
    mp = _append(out / "marks", new_m, run_id)
    rc = 3 if (mode == "step" and stale) else 0
    row = {"task": TASK_NAME, "schema": "dynamic_exposure_run/2", "utc": now.isoformat(), "mode": mode,
           "rc": rc, "action": "STALE_CALENDAR" if rc == 3 else "OK", "calendar_stale": stale,
           "stored_rows_rechecked": len(stored), "stored_rows_differ": 0, "code_version": code,
           "code_note": code_note, "run_id": run_id, "through": last_bar.date().isoformat(), "born": born, "skipped": skipped,
           "cohorts_total": len(existing), "paths_written": len(new_p), "marks_written": len(new_m),
           "paths_part": None if pp is None else str(pp), "marks_part": None if mp is None else str(mp),
           "leader_events": events, "replay_form_events": replay_form_events(bars, earn, sessions),
           "leader_calendar": cal_status,
           "contracts": {c["contract_id"]: c["contract_sha256"] for c in contracts.values()},
           "llm_spend_usd": 0.0, "broker_calls": 0}
    from backend.services import disk_guard
    disk_guard.locked_append_line(out / "runs.jsonl", json.dumps(row, sort_keys=True, default=str), fsync=True)
    row["table"] = table
    row["cohorts"] = {k: {kk: v[kk] for kk in ("entry_session", "n_names", "holdings_hash", "stats",
                                               "backfilled") if kk in v} | {"rolling_crosscheck": v.get("rolling_crosscheck")}
                      for k, v in existing.items()}
    return row


def compute_cohort(c: dict, bars: pd.DataFrame, sessions: list[pd.Timestamp], earn: dict, *,
                   horizon: int, through: pd.Timestamp, facts: Optional[dict] = None,
                   decision_utc: Optional[dict] = None) -> tuple[dict, dict]:
    """The three exposure paths of one born cohort, from bars and the calendar only."""
    events = leader_events(bars, earn, sessions)
    ser = cohort_series(c["long"], bars, sessions, pd.Timestamp(c["cohort_id"]),
                        pd.Timestamp(c["entry_session"]), through, horizon)
    out = {}
    for p in PERSONALITIES:
        rows = exposure_path(p, days=ser["days"], sessions=sessions, base_ret=ser["base_ret"],
                             q_ret=ser["q_ret"], q_close=ser["q_close"], pre_book_ret=ser["pre_book_ret"],
                             pre_q_ret=ser["pre_q_ret"], events=events, facts=facts,
                             decision_utc=decision_utc)
        out[p] = apply_path(rows, ser["base_ret"], ser["q_ret"])
    return out, ser


def poison_from(bars: pd.DataFrame, day: pd.Timestamp, seed: int) -> pd.DataFrame:
    """Every open and close dated on or after `day` multiplied by a random factor."""
    b = bars.copy()
    m = (b["date"] >= day).to_numpy()
    rng = np.random.default_rng(seed)
    for col in ("open", "close"):
        b.loc[m, col] = b.loc[m, col].to_numpy() * rng.uniform(0.5, 1.5, int(m.sum()))
    return b


def pit_recheck(c: dict, bars: pd.DataFrame, sessions: list[pd.Timestamp], earn: dict, *,
                horizon: int, through: pd.Timestamp, seed: int = 7, facts: Optional[dict] = None,
                decision_utc: Optional[dict] = None) -> dict:
    """For every session k of the cohort: poison every bar dated >= k, recompute, and
    require the exposure and hedge decided for sessions <= k to be unchanged. A
    decision that moves read data dated on or after the session it was applied to."""
    ref, ser = compute_cohort(c, bars, sessions, earn, horizon=horizon, through=through, facts=facts,
                              decision_utc=decision_utc)
    checked = differ = 0
    bad = []
    for j, day in enumerate(ser["days"]):
        got, _ = compute_cohort(c, poison_from(bars, day, seed + j), sessions, earn,
                                horizon=horizon, through=through, facts=facts, decision_utc=decision_utc)
        for p in PERSONALITIES:
            for a, b in zip(ref[p][: j + 1], got[p][: j + 1]):
                checked += 1
                if abs(a["exposure"] - b["exposure"]) > 1e-12 or abs(a["hedge"] - b["hedge"]) > 1e-9:
                    differ += 1
                    bad.append((p, a["date"].date().isoformat(), day.date().isoformat()))
    return {"cohort_id": c["cohort_id"], "decisions_checked": checked, "differ": differ, "examples": bad[:5]}


def stored_marks(out: Path) -> pd.DataFrame:
    return _read(Path(out) / "marks")


def contracts_file_sha(path: Path) -> Optional[str]:
    p = Path(path)
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if p.is_file() else None


def fmt_pct(v: Optional[float]) -> str:
    return "  n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:+.2f}%"
