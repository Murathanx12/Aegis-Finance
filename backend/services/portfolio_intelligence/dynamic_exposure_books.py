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

CONTRACTS v3 (2026-11-15, CH-45 follow-up)
==========================================
v2 is superseded before any forward decision (nothing ran forward under it), for
two reasons:

* the leader-gap rule read `straddle_forward/earnings_cache.json`, which holds
  only PAST report dates, so forward it could fire only if the cache happened to
  be re-pulled between a reaction close and that evening's step. v3 reads the
  forward catalyst calendar (`forward_calendar/snapshots`, task
  AegisForwardCalendar): every pull's answer for every leader is appended to
  `calendar_facts.jsonl` with the row's OWN `pulled_utc` (its observation stamp)
  and source, and a report date acts on a decision only while the newest
  observation at or before that decision still names it. The reaction session is
  the first session whose OPEN is strictly after the report's time; a report
  whose time is not stated (or a vendor estimate) is taken at the CLOSE of its
  date, so its reaction session is the next session -- the convention that cannot
  read a price before it existed. STALE is the forward calendar's freshness and
  coverage; a leader with no announced next date is UNSCHEDULED (named, healthy
  while the calendar is fresh).
* preservation admitted gross up to 3.95x (beta clip 3). v3 caps the QQQ hedge
  at 1.0x equity, so gross <= 2.0 at every decision.
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
CONTRACT_VERSION = "v3"
CONTRACTS_REL = "docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v3.json"
#: Superseded on 2026-11-15 before any forward decision (only a backfilled dry run in a
#: work folder ran under it). Kept byte for byte; never edited.
CONTRACTS_V1_REL = "docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v1.json"
CONTRACTS_V1_MANIFEST = "328a0c7337ef45b7aa29b6faf4921cf66e65cad82a6bb37db9edb06d6dab9294"
#: Superseded on 2026-11-15 before any forward decision (no scheduled task ever ran it;
#: only backfilled dry runs in work folders). Kept byte for byte; never edited.
CONTRACTS_V2_REL = "docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v2.json"
CONTRACTS_V2_MANIFEST = "c65e70d9239ac19cf3e7de466a8634d965e8854e1048133e4555e36b32e279b9"
FACTS_FILE = "calendar_facts.jsonl"
FACT_SCHEMA = "dynamic_exposure_calendar_fact/2"
CODE_VERSIONS_FILE = "code_versions_accepted.jsonl"
SPECS_V2_REL = "docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json"
#: v1/v2's past-report cache; v3 does not read it (kept for the receipt of what v2 read).
EARNINGS_REL = "straddle_forward/earnings_cache.json"
FORWARD_CALENDAR_REL = "forward_calendar/snapshots"
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
            "earnings_dates": (FORWARD_CALENDAR_REL + "/fc_<stamp>_<h6>.jsonl (task AegisForwardCalendar, "
                               "forward_calendar.py): per pull and leader the vendor's next_date, timing, "
                               "event_utc, event_time_known, confirmation, last_reported_date. The v1/v2 "
                               "past-report cache " + EARNINGS_REL + " is not read"),
            "calendar_observation": ("every pull's answer for every leader is appended once to "
                                     "calendar_facts.jsonl (append-only) with the row's OWN pulled_utc as "
                                     "observed_utc, its pull_id and source. A report date d acts on the decision "
                                     "at time T only while the newest observation with observed_utc <= T names "
                                     "d (as next_date or last_reported_date); FAILED rows and rows naming no date "
                                     "carry no information and are skipped. So a date announced ahead acts on "
                                     "time; a date first observed after its reaction session's close is "
                                     "LEARNED_LATE and acts only on decisions after its observation (never "
                                     "retroactively; stored rows never change); a date replaced before its "
                                     "reaction close is MOVED and never acts"),
            "reaction_session": ("the first session whose OPEN is strictly after the report time. The report "
                                 "time is the newest pre-event observation's event_utc when the calendar states "
                                 "the time (event_time_known: BMO -> the report date's own session, AMC or "
                                 "intraday -> the next session); when the time is not stated (timing UNKNOWN, "
                                 "or a VENDOR_ESTIMATE) it is the CLOSE of the report date, so the reaction "
                                 "session is the next session: the convention that cannot read a price before "
                                 "it existed. A date first named only after its event takes its time from that "
                                 "first observation (last_reported_utc when stated, else the close of the date). "
                                 "One reaction session per report (v2 checked two)"),
            "gap": "open_s / close_(s-1) - 1 of the leader on the reaction session s, from the bars",
            "non_earnings_gaps": "do not fire (as the replay code ran; NVDA 11-09 / 11-12 2026 excluded)",
            "calendar_stale_days": c.DYNAMIC_BOOK_FORWARD_CALENDAR_STALE_DAYS,
            "calendar_horizon_days": c.DYNAMIC_BOOK_CALENDAR_HORIZON_DAYS,
            "unscheduled_overdue_days": c.DYNAMIC_BOOK_UNSCHEDULED_OVERDUE_DAYS,
            "calendar_stale_rule": ("at the run: the forward calendar is STALE when its newest FULL_UNIVERSE "
                                    "receipt is older than calendar_stale_days, not OK, or its snapshot is "
                                    "damaged (forward_calendar.freshness), or a leader's own row is "
                                    "CALENDAR_STALE / NOT_COVERED / served from an older snapshot, or a leader "
                                    "has no bars; a step then exits 3 naming it. A leader whose fresh row holds "
                                    "no next date is UNSCHEDULED: named (OVERDUE when its last report is older "
                                    "than unscheduled_overdue_days), exit 0. A next date beyond "
                                    "calendar_horizon_days is SCHEDULED_FAR: healthy")},
        "preservation": {
            "id": "b_qqq_trend_hedge",
            "definition": ("if close_(t-1)(QQQ) < SMA_sma_sessions(QQQ closes through t-1): short QQQ "
                           "over session t with notional h x NAV, h = min(beta_(t-1) clipped to beta_clip, "
                           "hedge_notional_cap, gross_cap - stock exposure x gross long); beta_(t-1) = OLS "
                           "beta of the book's daily returns on QQQ's over the beta_window sessions ending "
                           "t-1; otherwise no hedge"),
            "etf": c.DYNAMIC_BOOK_HEDGE_ETF, "sma_sessions": c.DYNAMIC_BOOK_HEDGE_SMA,
            "beta_window_sessions": c.DYNAMIC_BOOK_HEDGE_BETA_WINDOW,
            "beta_min_obs": c.DYNAMIC_BOOK_HEDGE_BETA_MIN_OBS,
            "beta_clip": list(c.DYNAMIC_BOOK_HEDGE_BETA_CLIP),
            "hedge_notional_cap": c.DYNAMIC_BOOK_HEDGE_NOTIONAL_CAP,
            "gross_cap": c.DYNAMIC_BOOK_GROSS_CAP,
            "gross_cap_why": ("the brain's decision of 2026-11-15: a book named preservation may not exceed "
                              "2.0x gross. v2 admitted 3.95x (beta clip 3) and held 2.49-2.90x in the "
                              "backfilled window. The cap binds at every decision (each close, after the "
                              "rebalance); between closes the legs drift with prices (a +10% QQQ session at "
                              "the cap moves gross to ~2.28x before the next close rebalances it)"),
            "book_returns_for_beta": ("sessions <= D: the entry weights held at constant weight "
                                      "(backcast, cash at 0); sessions >= E: the book's realised NAV "
                                      "return, paired with QQQ over the same interval (E: open to close)")},
    }


def hedge_bound(*, capped: bool = True) -> float:
    """The largest hedge (x equity) the rule admits: v3 caps it, the v2 form only clips beta."""
    hi = float(_config.DYNAMIC_BOOK_HEDGE_BETA_CLIP[1])
    return min(hi, float(_config.DYNAMIC_BOOK_HEDGE_NOTIONAL_CAP)) if capped else hi


def worst_case_lines(gross_long: float) -> dict:
    """CLAUDE.md protocol 4, in dollars on the report equity: the largest admissible book's
    gross, every long name gapping -WORST_GAP at full exposure (hedge credited 0), a
    one-session +SQUEEZE QQQ against the largest admissible hedge (longs credited 0), and
    both in one session; v3 beside the v2 form."""
    book = float(_config.DYNAMIC_BOOK_REPORT_EQUITY_USD)
    gap, sq = float(_config.DYNAMIC_BOOK_WORST_GAP), float(_config.DYNAMIC_BOOK_SQUEEZE_QQQ_UP)
    out = {"equity_usd": book, "gross_long": gross_long}
    for k, capped in (("v3", True), ("v2_form", False)):
        h = hedge_bound(capped=capped)
        longs, squeeze = -book * gross_long * gap, -book * h * sq
        out[k] = {"gross_admissible": round(gross_long + h, 4), "longs_gap_usd": round(longs, 2),
                  "hedge_squeeze_usd": round(squeeze, 2), "both_in_one_session_usd": round(longs + squeeze, 2)}
    return out


def contract_bodies(*, frozen_utc: str, specs: dict) -> list[dict]:
    """The three contract bodies from config + the v2 base spec (no hashes yet)."""
    pid = _config.DYNAMIC_BOOK_BASE_POLICY_ID
    base = next((s for s in specs["specifications"] if s["policy_id"] == pid), None)
    if base is None:
        raise DynamicBookRefused(f"base policy {pid} is not in {SPECS_V2_REL}")
    rules = _rules()
    rules["preservation"]["worst_case_usd"] = worst_case_lines(float(base["gross_target"]))
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
        "supersedes": {"file": CONTRACTS_V2_REL, "manifest_sha256": CONTRACTS_V2_MANIFEST,
                       "why": ("v2 was superseded on 2026-11-15 BEFORE any forward decision: no scheduled "
                               "task ever ran it, only backfilled dry runs in work folders. v3 changes: "
                               "(1) the leader report dates come from the forward catalyst calendar with "
                               "each observation's own pulled_utc (v2 read a past-report cache whose dates "
                               "were known only after the event, so forward the rule could not fire on "
                               "time); one reaction session per report, from the stated report time; STALE "
                               "is the forward calendar's freshness and coverage, a leader without a next "
                               "date is UNSCHEDULED. (2) preservation's QQQ hedge is capped at 1.0x equity "
                               "(gross <= 2.0; v2 admitted 3.95x). Growth's rule is unchanged; all three "
                               "take v3 ids because the family's inputs changed"),
                       "chain": [{"file": CONTRACTS_V1_REL, "manifest_sha256": CONTRACTS_V1_MANIFEST,
                                  "superseded_by": CONTRACTS_V2_REL}]},
        "fill_convention": ("base book: buy at the open of E, held (rolling grade rule v2: a name "
                            "with no valid open waits in cash at 0%); exposure and hedge changes at "
                            "the close of the deciding session; daily rebalanced to the exposure "
                            "fraction; cash and short collateral earn 0"),
        "costs": {"base_round_trip": "xs_ranker.COST_BPS_BY_BAND per name, half at entry, half at the mark",
                  "stock_exposure_change_bps": _config.DYNAMIC_BOOK_COST_STOCK_BPS,
                  "etf_hedge_change_bps": _config.DYNAMIC_BOOK_COST_ETF_BPS,
                  "hedge_borrow_bps_yr": _config.DYNAMIC_BOOK_HEDGE_BORROW_BPS_YR,
                  "exposure_starts_at": 1.0, "hedge_starts_at": 0.0},
        "inputs": ["prices_2025_26/bars.parquet (open, close, volume)",
                   FORWARD_CALENDAR_REL + " (FULL_UNIVERSE pulls; receipts for freshness)",
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
                    f"config or the v2 spec file no longer equals frozen contract {c['contract_id']} ({key}). "
                    f"A changed rule is a NEW contract id in a new file; restore the config or declare a new contract version")
    return out


def load_contracts(path: Path, specs: dict) -> tuple[dict, dict[str, dict]]:
    p = Path(path)
    if not p.is_file():
        raise DynamicBookRefused(f"contracts file {p} is absent; run `compile-contracts` (attended)")
    doc = json.loads(p.read_bytes())
    return doc, verify_contracts(doc, specs)


# ──────────────────────────────── inputs ────────────────────────────────────

def _utc_ts(v: Any) -> Optional[pd.Timestamp]:
    if v is None or v == "":
        return None
    t = pd.Timestamp(v)
    return t.tz_convert("UTC") if t.tzinfo else t.tz_localize("UTC")


def _open_after(cal: Any, t: pd.Timestamp) -> pd.Timestamp:
    """The first opening bell strictly after `t` (UTC). An injected calendar may
    provide `open_after`; the real one is `market_sessions.next_session_open`."""
    f = getattr(cal, "open_after", None)
    if f is not None:
        return _utc_ts(f(t.to_pydatetime()))
    from backend.services import market_sessions as MS
    return _utc_ts(MS.next_session_open(t.to_pydatetime()))


def _date_close_utc(cal: Any, d: pd.Timestamp) -> pd.Timestamp:
    """The close of the report date's session; a date that is not a session is taken
    at 16:00 New York (the next open then follows it)."""
    c = cal.close_of(d) if cal is not None else None
    if c is not None:
        return _utc_ts(c)
    from backend.services import forward_calendar as FC
    return _utc_ts(FC.session_close_utc(pd.Timestamp(d).date()))


def read_observations(out: Path) -> list[dict]:
    """Every forward-calendar observation on record in `<out>/calendar_facts.jsonl`."""
    p = Path(out) / FACTS_FILE
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("schema") != FACT_SCHEMA:
                raise DynamicBookRefused(f"{p} holds a {r.get('schema')!r} row: this --out was written "
                                         f"under another contract version (a changed family is a new --out)")
            rows.append(r)
    return rows


def ingest_forward_calendar(out: Path, data_root: Path, *, now: datetime, run_id: str) -> dict:
    """Append, once per (pull, leader), the forward calendar's answer for each leader:
    the row's OWN pulled_utc is the observation stamp. Only FULL pulls finalised under
    a stamp at or before `now` are read; a damaged snapshot (bad lines, or fewer rows
    than its index) is skipped and named. Never rewrites a line."""
    from backend.services import disk_guard
    from backend.services import forward_calendar as FC
    leaders = tuple(_config.DYNAMIC_BOOK_LEADERS)
    have = read_observations(out)
    seen_pulls = {r["pull_id"] for r in have}
    files, _after = FC._final_snapshots(Path(data_root), now)
    new, damaged, opened = [], [], 0
    for _stamp, f in files:
        pid = f.name[:-len(".jsonl")]
        if pid in seen_pulls:
            continue
        rows, n_bad = FC.read_snapshot(f)
        opened += 1
        idx = FC._load_index(f.parent, pid)
        n_ear = sum(1 for r in rows if r.get("row_kind") == "earnings")
        short = idx is not None and isinstance(idx.get("n_earnings_rows"), int) and n_ear < idx["n_earnings_rows"]
        if n_bad or short:
            damaged.append({"pull_id": pid, "n_bad_lines": n_bad, "short_vs_index": bool(short)})
            continue
        hdr = next((r for r in rows if r.get("row_kind") == "pull_header"), {})
        for r in rows:
            if r.get("row_kind") != "earnings" or r.get("ticker") not in leaders:
                continue
            pu = _utc_ts(r.get("pulled_utc"))
            if pu is None or pu > pd.Timestamp(now):
                continue
            new.append({"schema": FACT_SCHEMA, "kind": "forward_calendar_observation", "leader": r["ticker"],
                        "pull_id": pid, "scope": hdr.get("scope"), "observed_utc": pu.isoformat(),
                        "status": r.get("status"), "next_date": r.get("next_date"), "timing": r.get("timing"),
                        "event_utc": r.get("event_utc"), "event_time_known": bool(r.get("event_time_known")),
                        "confirmation": r.get("confirmation"),
                        "last_reported_date": r.get("last_reported_date"),
                        "last_reported_utc": r.get("last_reported_utc"), "error": r.get("error"),
                        "source": f"{r.get('source')} via {FORWARD_CALENDAR_REL}/{f.name}",
                        "first_recorded_utc": now.isoformat(), "run_id": run_id})
    new.sort(key=lambda r: (r["observed_utc"], r["leader"]))
    p = Path(out) / FACTS_FILE
    for r in new:
        disk_guard.locked_append_line(p, json.dumps(r, sort_keys=True), fsync=True)
    return {"observations": have + new, "appended": len(new), "snapshots_read": opened,
            "snapshots_damaged": damaged}


def _informative(o: dict) -> bool:
    return o.get("status") in ("DATE", "NO_DATE") and bool(o.get("next_date") or o.get("last_reported_date"))


def _belief_intervals(rows: list[dict], d: str) -> list[list[Optional[str]]]:
    """[start, end) spans of observed_utc during which the newest informative
    observation names `d` (as next_date or last_reported_date)."""
    spans: list[list[Optional[str]]] = []
    for o in rows:
        names = d in (o.get("next_date"), o.get("last_reported_date"))
        if names and (not spans or spans[-1][1] is not None):
            spans.append([o["observed_utc"], None])
        elif not names and spans and spans[-1][1] is None:
            spans[-1][1] = o["observed_utc"]
    return spans


def believed(fact: dict, decision: Any) -> bool:
    """A report date acts on a decision at `decision` only inside a belief span."""
    if decision is None:
        return False
    t = _utc_ts(decision)
    return any(_utc_ts(a) <= t and (b is None or t < _utc_ts(b)) for a, b in fact["belief_spans"])


def leader_facts(observations: list[dict], *, cal: Any, as_of: Optional[datetime] = None) -> list[dict]:
    """One fact per (leader, report date) the calendar ever named, from observations
    with observed_utc <= `as_of` only: the report time and reaction session, the first
    observation, whether it was announced before the event, and its belief spans."""
    cut = None if as_of is None else _utc_ts(as_of)
    by: dict[str, list[dict]] = {}
    for o in observations:
        if not _informative(o) or (cut is not None and _utc_ts(o["observed_utc"]) > cut):
            continue
        by.setdefault(o["leader"], []).append(o)
    since = {k: pd.Timestamp(v) for k, v in _config.DYNAMIC_BOOK_LEADER_SINCE.items()}
    out = []
    for leader, rows in sorted(by.items()):
        rows.sort(key=lambda o: o["observed_utc"])
        dates = sorted({x for o in rows for x in (o.get("next_date"), o.get("last_reported_date")) if x})
        for d in dates:
            dd = pd.Timestamp(d)
            if leader in since and dd < since[leader]:
                continue
            close_d = _date_close_utc(cal, dd)
            pre = None                                   # newest pre-event row announcing d as next_date
            for o in rows:
                if o.get("next_date") != d:
                    continue
                t_ev = (_utc_ts(o["event_utc"]) if o.get("event_time_known") and o.get("event_utc") else close_d)
                if _utc_ts(o["observed_utc"]) < t_ev:
                    pre = (o, t_ev)
            first = next(o for o in rows if d in (o.get("next_date"), o.get("last_reported_date")))
            if pre is not None:
                src, t_event = pre
                timing, basis = (src.get("timing") or "UNKNOWN"), ("stated" if src.get("event_time_known")
                                                                 else "unstated: close of the date")
            else:                                        # first named after the event: its first row decides
                src = first
                stated = first.get("last_reported_date") == d and bool(first.get("last_reported_utc"))
                t_event = _utc_ts(first["last_reported_utc"]) if stated else close_d
                timing, basis = ("STATED_AFTER" if stated else "UNKNOWN"), ("stated after the event" if stated
                                                                           else "unstated: close of the date")
            out.append({"leader": leader, "earnings_date": d, "timing": timing, "time_basis": basis,
                        "event_utc_assumed": t_event.isoformat(),
                        "reaction_session": _open_after(cal, t_event).tz_convert(None).normalize().date().isoformat(),
                        "announced_before_event": pre is not None,
                        "first_observed_utc": first["observed_utc"], "first_pull_id": first["pull_id"],
                        "confirmation": src.get("confirmation"), "source_pull_id": src["pull_id"],
                        "belief_spans": _belief_intervals(rows, d)})
    return out


def leader_events(bars: pd.DataFrame, facts: list[dict], sessions: list[pd.Timestamp]) -> list[dict]:
    """The gap of each fact's reaction session, from the bars: one row per fact whose
    reaction session is in `sessions` and has a previous session. `fires` when the gap
    is at or below the threshold; whether it ACTS on a decision is `believed`."""
    thr = float(_config.DYNAMIC_BOOK_LEADER_GAP)
    if not facts:
        return []
    sub = bars[bars["symbol"].isin({f["leader"] for f in facts})]
    opn = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last").reindex(sessions)
    cls = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(sessions)
    sidx = {s: i for i, s in enumerate(sessions)}
    out = []
    for f in facts:
        s = pd.Timestamp(f["reaction_session"])
        j = sidx.get(s)
        if j is None or j < 1 or f["leader"] not in opn.columns:
            continue
        g = opn[f["leader"]].iloc[j] / cls[f["leader"]].iloc[j - 1] - 1.0
        if np.isfinite(g):
            out.append({**f, "session": s.date().isoformat(), "gap": float(g), "fires": bool(g <= thr)})
    return sorted(out, key=lambda e: (e["session"], e["leader"]))


def event_status(e: dict, decision_utc: dict) -> str:
    """ON_TIME: believed at the reaction close (announced ahead, or seen after the event
    but before that close); LEARNED_LATE: first observed after it; MOVED: named before it
    but replaced by then."""
    dec = decision_utc.get(pd.Timestamp(e["session"]))
    if believed(e, dec):
        return "ON_TIME" if e["announced_before_event"] else "ON_TIME_SEEN_AFTER_EVENT"
    if dec is not None and _utc_ts(e["first_observed_utc"]) > _utc_ts(dec):
        return "LEARNED_LATE"
    return "MOVED"


def calendar_health(data_root: Path, *, now: datetime, leaders_in_bars: Optional[set] = None) -> dict:
    """The forward calendar's freshness and coverage at `now`, per leader: SCHEDULED /
    SCHEDULED_FAR / UNSCHEDULED (healthy while the calendar is fresh) or STALE (a step
    exits 3). Dates come from `forward_calendar.next_dates` (the newest row pulled at or
    before `now`), each with its observation stamp."""
    from backend.services import forward_calendar as FC
    sd = float(_config.DYNAMIC_BOOK_FORWARD_CALENDAR_STALE_DAYS)
    hz = int(_config.DYNAMIC_BOOK_CALENDAR_HORIZON_DAYS)
    od = int(_config.DYNAMIC_BOOK_UNSCHEDULED_OVERDUE_DAYS)
    leaders = tuple(_config.DYNAMIC_BOOK_LEADERS)
    fresh = FC.freshness(Path(data_root), now, stale_days=sd)
    nd = FC.next_dates(leaders, now, hz, root=Path(data_root), stale_days=sd)
    today = pd.Timestamp(nd["market_date"])
    stale: dict[str, list[str]] = {}
    unscheduled: dict[str, list[str]] = {}
    if fresh["verdict"] != "ALIVE":
        stale["_forward_calendar"] = [f"{fresh['verdict']}: {fresh['detail']}"]
    per = {}
    for t in leaders:
        v = nd["tickers"][t]
        last = (v.get("last_reported") or {}).get("date")
        row = {"label": v["label"], "reason": v.get("reason"), "next_date": v.get("date"),
               "timing": v.get("timing"), "event_time_known": v.get("event_time_known"),
               "confirmation": v.get("confirmation"), "observed_utc": v.get("pulled_utc"),
               "pull_id": v.get("pull_id"), "age_days": v.get("age_days"), "last_reported": last,
               "days_away": v.get("days_away")}
        why = []
        if leaders_in_bars is not None and t not in leaders_in_bars:
            why.append("no bars for the leader")
        if v["label"] in (FC.NOT_COVERED, FC.CALENDAR_STALE, FC.FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED):
            why.append(f"{v['label']}: {v.get('reason')}")
        if why:
            row["state"] = "STALE"
            stale[t] = why
        elif v.get("date") and v["label"] == FC.DATE_IN_HORIZON:
            row["state"] = "SCHEDULED"
        elif v.get("date"):
            row["state"] = "SCHEDULED_FAR"
        else:
            age = None if not last else int((today - pd.Timestamp(last)).days)
            row["state"] = "UNSCHEDULED"
            unscheduled[t] = [f"no announced next date ({v.get('reason')}); last report {last}"
                              + ("" if age is None else f", {age} days ago")
                              + (" -- OVERDUE" if age is None or age > od else "")]
        per[t] = row
    return {"freshness": fresh, "market_date": nd["market_date"], "stale_days": sd, "horizon_days": hz,
            "leaders": per, "stale": stale, "unscheduled": unscheduled}


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
                  decision_utc: Optional[dict] = None, gross_long: float = 1.0,
                  hedge_capped: bool = True) -> list[dict]:
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
        ev = [(sidx[pd.Timestamp(e["session"])], e) for e in events
              if e.get("fires") and pd.Timestamp(e["session"]) in sidx]
        for k in range(n):
            i = sidx[days[k]]
            prev = sessions[i - 1]
            dec = None if decision_utc is None else decision_utc.get(prev)
            if dec is None:
                raise DynamicBookRefused(f"no decision time for the close of {prev.date()}")
            # event session j <= i-1 (its gap known at that open), and the calendar named the
            # report date in its newest observation at or before this decision's close
            live = [e for j, e in ev if 1 <= i - j <= L and believed(e, dec)]
            e_k = gross if live else 1.0
            rows.append({"k": k + 1, "date": days[k], "signal_asof": prev, "exposure": e_k, "hedge": 0.0,
                         "fired": ";".join(f"{e['leader']}@{e['session']}({e['gap']:+.3f})" for e in live) or None})
        return rows
    if personality == "preservation":
        sma_n = int(_config.DYNAMIC_BOOK_HEDGE_SMA)
        win = int(_config.DYNAMIC_BOOK_HEDGE_BETA_WINDOW)
        lo, hi = _config.DYNAMIC_BOOK_HEDGE_BETA_CLIP
        min_obs = int(_config.DYNAMIC_BOOK_HEDGE_BETA_MIN_OBS)
        cap = hedge_bound(capped=hedge_capped)
        gcap = float(_config.DYNAMIC_BOOK_GROSS_CAP) if hedge_capped else math.inf
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
                    h_k = float(min(hi, max(lo, beta)))                  # the v2 form
                    if hedge_capped:
                        h_k = float(max(0.0, min(h_k, cap, gcap - 1.0 * gross_long)))
            if h_k + 1.0 * gross_long > gcap + 1e-12:
                raise DynamicBookRefused(f"preservation gross {h_k + gross_long:.4f} > cap {gcap} on {days[k].date()}")
            rows.append({"k": k + 1, "date": days[k], "signal_asof": prev, "exposure": 1.0, "hedge": h_k,
                         "qqq_close_prev": last, "qqq_sma_prev": sma, "beta_prev": beta,
                         "hedge_cap_bound": bool(beta is not None and h_k > 0
                                                 and h_k < min(hi, max(lo, beta)) - 1e-12),
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
             band: float, stats: dict, gross_long: float, run_id: str, provisional: bool = False,
             hedged_capped: bool = True) -> dict:
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
            "gross_notional_admissible": float(gross_long + (hedge_bound(capped=hedged_capped)
                                                             if contract["personality"] == "preservation" else 0.0)),
            "squeeze_usd_observed": -book * float(h.max()) * float(_config.DYNAMIC_BOOK_SQUEEZE_QQQ_UP),
            "squeeze_usd_admissible": -book * float(_config.DYNAMIC_BOOK_SQUEEZE_QQQ_UP) * (
                hedge_bound(capped=hedged_capped) if contract["personality"] == "preservation" else 0.0),
            "sessions_hedge_cap_bound": int(sum(bool(r.get("hedge_cap_bound")) for r in sub)),
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
    else:
        R._write_once(decl_p, json.dumps({"schema": "dynamic_exposure_declaration/3", "task": TASK_NAME,
                                          "contract_version": CONTRACT_VERSION,
                                          "declared_utc": now.isoformat(),
                                          "contracts_manifest_sha256": cdoc["manifest_sha256"],
                                          "contracts": {c["contract_id"]: c["contract_sha256"]
                                                        for c in contracts.values()},
                                          "spec_manifest_sha256": manifest, "config": snap,
                                          "rolling_config": rsnap, "rolling_config_hash": digest(rsnap),
                                          "code_version": code, "license": "PRODUCT_EXPERIMENT"},
                                         sort_keys=True, indent=1, default=list))
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
    cal = calendar or R.XnysCalendar()
    leaders = list(_config.DYNAMIC_BOOK_LEADERS)
    in_bars = set(bars.loc[bars["symbol"].isin(leaders), "symbol"].unique())
    health = calendar_health(data_root, now=now, leaders_in_bars=in_bars)
    stale = health["stale"]
    ing = ingest_forward_calendar(out, data_root, now=now, run_id=run_id)
    first = max(0, sessions.index(sched[0]) - 1)
    decision_utc = {s: pd.Timestamp(cal.close_of(s)) for s in sessions[first:]}
    facts = leader_facts(ing["observations"], cal=cal)
    events = leader_events(bars, facts, sessions)
    for e in events:
        e["status"] = event_status(e, decision_utc) if pd.Timestamp(e["session"]) in decision_utc else "BEFORE_ANCHOR"
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
        paths, ser = compute_cohort(c, bars, sessions, ing["observations"], horizon=horizon, through=last_bar,
                                    decision_utc=decision_utc, cal=cal)
        for p in PERSONALITIES:
            ct = contracts[p]
            rows = paths[p]
            for r in rows:
                dec = decision_utc[pd.Timestamp(r["signal_asof"])]
                r["calendar_observed"] = "n/a" if p != "balanced" else "forward_calendar"
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
    row = {"task": TASK_NAME, "schema": "dynamic_exposure_run/3", "contract_version": CONTRACT_VERSION, "utc": now.isoformat(), "mode": mode,
           "rc": rc, "action": ("STALE_CALENDAR" if rc == 3 else "BORN" if born else "MARKED" if (new_p or new_m) else "NOTHING_DUE"), "calendar_stale": stale,
           "stored_rows_rechecked": len(stored), "stored_rows_differ": 0, "code_version": code,
           "code_note": code_note, "run_id": run_id, "through": last_bar.date().isoformat(), "born": born, "skipped": skipped,
           "cohorts_total": len(existing), "paths_total": len(have_p) + len(new_p), "paths_written": len(new_p), "marks_written": len(new_m),
           "paths_part": None if pp is None else str(pp), "marks_part": None if mp is None else str(mp),
           "leader_events": [{k: v for k, v in e.items() if k != "belief_spans"} for e in events],
           "leader_calendar": health["leaders"], "calendar_unscheduled": health["unscheduled"],
           "forward_calendar": {"freshness": health["freshness"], "observations_appended": ing["appended"],
                                "observations_total": len(ing["observations"]),
                                "snapshots_read": ing["snapshots_read"],
                                "snapshots_damaged": ing["snapshots_damaged"]},
           "contracts": {c["contract_id"]: c["contract_sha256"] for c in contracts.values()},
           "llm_spend_usd": 0.0, "broker_calls": 0}
    from backend.services import disk_guard
    disk_guard.locked_append_line(out / "runs.jsonl", json.dumps(row, sort_keys=True, default=str), fsync=True)
    row["table"] = table
    row["cohorts"] = {k: {kk: v[kk] for kk in ("entry_session", "n_names", "holdings_hash", "stats",
                                               "backfilled") if kk in v} | {"rolling_crosscheck": v.get("rolling_crosscheck")}
                      for k, v in existing.items()}
    return row


def compute_cohort(c: dict, bars: pd.DataFrame, sessions: list[pd.Timestamp], observations: list[dict], *,
                   horizon: int, through: pd.Timestamp, decision_utc: dict, cal: Any,
                   as_of: Optional[datetime] = None, hedge_capped: bool = True) -> tuple[dict, dict]:
    """The three exposure paths of one born cohort, from bars and the calendar
    observations only (`as_of`: only observations with observed_utc <= it)."""
    events = leader_events(bars, leader_facts(observations, cal=cal, as_of=as_of), sessions)
    ser = cohort_series(c["long"], bars, sessions, pd.Timestamp(c["cohort_id"]),
                        pd.Timestamp(c["entry_session"]), through, horizon)
    out = {}
    for p in PERSONALITIES:
        rows = exposure_path(p, days=ser["days"], sessions=sessions, base_ret=ser["base_ret"],
                             q_ret=ser["q_ret"], q_close=ser["q_close"], pre_book_ret=ser["pre_book_ret"],
                             pre_q_ret=ser["pre_q_ret"], events=events, decision_utc=decision_utc,
                             gross_long=float(c.get("gross_long", 1.0)), hedge_capped=hedge_capped)
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


def pit_recheck(c: dict, bars: pd.DataFrame, sessions: list[pd.Timestamp], observations: list[dict], *,
                horizon: int, through: pd.Timestamp, decision_utc: dict, cal: Any, seed: int = 7) -> dict:
    """For every session k of the cohort: poison every bar dated >= k AND drop every
    calendar observation made after the close that decided k, recompute, and require
    the exposure and hedge decided for sessions <= k to be unchanged. A decision that
    moves read a price dated on or after its session, or a calendar fact observed after
    its decision."""
    ref, ser = compute_cohort(c, bars, sessions, observations, horizon=horizon, through=through,
                              decision_utc=decision_utc, cal=cal)
    sidx = {s: i for i, s in enumerate(sessions)}
    checked = differ = 0
    bad = []
    for j, day in enumerate(ser["days"]):
        dec = decision_utc[sessions[sidx[day] - 1]]
        got, _ = compute_cohort(c, poison_from(bars, day, seed + j), sessions, observations, horizon=horizon,
                                through=through, decision_utc=decision_utc, cal=cal, as_of=dec)
        for p in PERSONALITIES:
            for a, b in zip(ref[p][: j + 1], got[p][: j + 1]):
                checked += 1
                if abs(a["exposure"] - b["exposure"]) > 1e-12 or abs(a["hedge"] - b["hedge"]) > 1e-9:
                    differ += 1
                    bad.append((p, a["date"].date().isoformat(), day.date().isoformat()))
    return {"cohort_id": c["cohort_id"], "decisions_checked": checked, "differ": differ, "examples": bad[:5]}


def preservation_cap_comparison(out: Path, data_root: Path, *, asof: Any = None,
                                now: Optional[datetime] = None, calendar: Any = None) -> list[dict]:
    """Read-only: for every cohort born in `out`, the preservation path under the v2 form
    (beta clip only) and under v3 (hedge <= 1.0x equity, gross <= 2.0), side by side, at
    the latest state. Writes nothing. Backfilled cohorts are one episode: no claim."""
    now = now or datetime.now(timezone.utc)
    specs, _ = R.load_specs(REPO / SPECS_V2_REL)
    spec = next(s for s in specs["specifications"] if s["policy_id"] == _config.DYNAMIC_BOOK_BASE_POLICY_ID)
    horizon = int(spec["horizon_sessions"])
    anchor = pd.Timestamp(_config.ROLLING_COHORT_ANCHOR)
    through = pd.Timestamp(asof).normalize() if asof is not None else pd.Timestamp(now.date())
    bars = R.load_bars(data_root, start=anchor - pd.Timedelta(days=400), end=through)
    sessions = R.bench_sessions(bars)
    cal = calendar or R.XnysCalendar()
    first = max(0, sessions.index(next(s for s in sessions if s >= anchor)) - 1)
    dec = {s: pd.Timestamp(cal.close_of(s)) for s in sessions[first:]}
    rows = []
    for p in sorted((Path(out) / "cohorts").glob("dxb_cohort_*.json")):
        c = json.loads(p.read_bytes())
        if pd.Timestamp(c["entry_session"]) not in set(sessions):
            continue
        ser = cohort_series(c["long"], bars, sessions, pd.Timestamp(c["cohort_id"]),
                            pd.Timestamp(c["entry_session"]), sessions[-1], horizon)
        row = {"cohort_id": c["cohort_id"], "backfilled": bool(c["backfilled"])}
        for tag, capped in (("v2", False), ("v3", True)):
            path = apply_path(exposure_path("preservation", days=ser["days"], sessions=sessions,
                                            base_ret=ser["base_ret"], q_ret=ser["q_ret"], q_close=ser["q_close"],
                                            pre_book_ret=ser["pre_book_ret"], pre_q_ret=ser["pre_q_ret"],
                                            events=[], decision_utc=dec, gross_long=float(c["gross_long"]),
                                            hedge_capped=capped), ser["base_ret"], ser["q_ret"])
            m = mark_row({"contract_id": f"DXB-preservation-{tag}", "contract_sha256": "-",
                          "personality": "preservation"}, c, path, len(path), spy_cum=ser["spy_ret_cum"],
                         band=float(c["band_round_trip"]), stats=c["stats"], gross_long=c["gross_long"],
                         run_id="compare", provisional=True, hedged_capped=capped)
            row[tag] = {k: m[k] for k in ("mark_k", "ret_net", "spy_ret", "beta_eff", "beta_adj_excess",
                                          "max_drawdown", "worst_day_usd", "gross_notional_max",
                                          "gross_notional_admissible", "squeeze_usd_observed",
                                          "squeeze_usd_admissible", "mean_hedge", "sessions_hedged",
                                          "sessions_hedge_cap_bound")}
            row[tag]["navs"] = [r["nav"] for r in path]
            row[tag]["hedges"] = [r["hedge"] for r in path]
        rows.append(row)
    return rows


def status(data_root: Path, out: Path, *, now: Optional[datetime] = None) -> dict:
    """Read-only: what the brain reads before scheduling. The contract version in force
    (and whether `out` was declared under it), the forward calendar's freshness, every
    leader's next announced date with its observation stamp, the cohorts tracked and the
    last run row. rc 3 when the calendar is STALE (a step would exit 3), 2 when the
    contracts do not verify or `out` was declared under other contracts, else 0. Creates
    and writes nothing."""
    now = now or datetime.now(timezone.utc)
    out = Path(out)
    res: dict = {"utc": now.isoformat(), "contract_version": CONTRACT_VERSION, "contracts_file": CONTRACTS_REL,
                 "out": str(out), "problems": []}
    try:
        specs, _ = R.load_specs(REPO / SPECS_V2_REL)
        cdoc, contracts = load_contracts(REPO / CONTRACTS_REL, specs)
        res["contracts_manifest_sha256"] = cdoc["manifest_sha256"]
        res["contracts"] = {c["contract_id"]: c["contract_sha256"] for c in contracts.values()}
    except (DynamicBookRefused, R.RollingCohortRefused) as exc:
        res["problems"].append(f"contracts do not verify: {exc}")
        p = REPO / CONTRACTS_REL
        cdoc = json.loads(p.read_bytes()) if p.is_file() else None          # its manifest, for the out check
    decl_p = out / "declaration.json"
    if decl_p.is_file():
        d = json.loads(decl_p.read_bytes())
        res["declaration"] = {k: d.get(k) for k in ("declared_utc", "contract_version",
                                                    "contracts_manifest_sha256", "code_version")}
        if cdoc is not None and d.get("contracts_manifest_sha256") != cdoc["manifest_sha256"]:
            res["problems"].append(f"{out} was declared under contracts {d.get('contracts_manifest_sha256')} "
                                   f"({d.get('contract_version') or 'v1/v2'}), not the {CONTRACT_VERSION} in force: "
                                   f"a step there refuses; use a new --out")
    else:
        res["declaration"] = None
    try:
        health = calendar_health(data_root, now=now)
    except Exception as exc:                                          # noqa: BLE001 -- reported, never green
        health = {"stale": {"_forward_calendar": [f"unreadable: {type(exc).__name__}: {exc}"]},
                  "unscheduled": {}, "leaders": {}, "freshness": None}
    res["forward_calendar"] = health.get("freshness")
    res["leaders"] = health.get("leaders")
    res["calendar_stale"] = health["stale"]
    res["calendar_unscheduled"] = health["unscheduled"]
    cdir = out / "cohorts"
    res["cohorts"] = [{"cohort_id": c["cohort_id"], "entry_session": c["entry_session"],
                       "backfilled": c["backfilled"], "holdings_hash": c["holdings_hash"]}
                      for c in (json.loads(p.read_bytes()) for p in sorted(cdir.glob("dxb_cohort_*.json")))
                      ] if cdir.is_dir() else []
    try:
        res["calendar_observations_on_record"] = len(read_observations(out))
    except DynamicBookRefused as exc:
        res["problems"].append(str(exc))
    runs = out / "runs.jsonl"
    last = None
    if runs.is_file():
        lines = [x for x in runs.read_text(encoding="utf8").splitlines() if x.strip()]
        if lines:
            r = json.loads(lines[-1])
            last = {k: r.get(k) for k in ("utc", "mode", "action", "rc", "through", "contract_version",
                                          "cohorts_total", "paths_total", "stored_rows_differ", "reason")}
    res["last_run"] = last
    res["rc"] = 2 if res["problems"] else 3 if health["stale"] else 0
    return res


def stored_marks(out: Path) -> pd.DataFrame:
    return _read(Path(out) / "marks")


def contracts_file_sha(path: Path) -> Optional[str]:
    p = Path(path)
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if p.is_file() else None


def fmt_pct(v: Optional[float]) -> str:
    return "  n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:+.2f}%"
