"""Forecast the way the only arm that WORKS forecasts.

    python -m scripts.night_investigator_forecast --n 20

WHY THIS EXACT SHAPE, AND NOT ANOTHER PERSONA
=============================================
`NEGATIVE_RESULTS.md` §64 graded 14,703 frozen forecasts and found the bench
splits cleanly in two:

    investigator:*  n 2,325  raw +4.38%  recalibrated +8.97% (w 0.65)  disc +16.7
    thematic (9)    n 5,027  raw -27.98% recalibrated  -0.00% (w 0.00) disc -2.0

Nine thematic personas -- `geopolitical`, `behavioral_narrative`,
`ownership_flow`, `event_news`, `company_fundamental` and the rest -- have
NEGATIVE discrimination. They assign higher probabilities to things that do not
happen. Their optimal weight, held out, is exactly zero.

The five that work are not smarter. They run a **process**: gather evidence,
name the source of each fact, state what would falsify the call, and only then
give a number. This module is that process, and three of its design choices are
read straight off §64 rather than chosen:

* **h=1.** Investigator skill is +5.75% with +16.7 discrimination at one day and
  +0.09% -- nothing -- by five. Asking at 20 days is asking where the skill is
  known to be absent.
* **shrink 0.65 toward the base rate** before the number is used anywhere. The
  failure mode is overconfidence (+17pp calibration gap), not ignorance, and
  that is the half that recalibration repairs. BOTH numbers are stored: `raw`
  for future recalibration research, `probability` for use.
  AMENDED 2026-09-26 (adjudication row 2): that shrink was earned on MAGNITUDE
  and is applied to magnitude rows only. Every row this module writes is a
  DIRECTION row (`beats_benchmark`), where held-out skill is -8.7% and the best
  weight is 0 -- so those rows are written RAW, with `raw_probability` and
  `shrink_basis` as proper fields (`recalibrate`).
* **no persona in the prompt.** Not a stylistic preference -- the measured
  difference between the two families is 33 points of Brier skill.

WHAT IS SENT, AND WHAT IS DELIBERATELY NOT
==========================================
The model receives a compact evidence packet assembled from what is ACTUALLY on
disk: price and liquidity features, the latest SEC quarter dated by its filing,
and the 90-day analyst revision flow from `target_revisions` (PIT-safe, real
event dates). It is told the cost of trading the name, and it is told which
standing results are already closed so it does not spend its answer
rediscovering §59.

It is NOT given a story about the sector, a narrative, or an instruction to
adopt a viewpoint. It is not asked whether the stock is good.

THE QUESTION IS FALSIFIABLE OR IT IS NOT ASKED
==============================================
One question per name: **will this beat SPY over the next session?** It resolves
from adjusted closes with no judgment, the grader already knows how, and the
sim's `u_grade` unit picks it up without anyone remembering to.

This is NOT a trade and does not become one. A probability with information in
it still needs a probability-to-return calibration before it can be sized, and
that does not exist. §61 is what happens when a number gets quoted before it has
one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                      # noqa: E402

OUT = Path(_config.OPTIMUS_LEDGER_DIR) / "investigator"

#: The arm name. Distinct from the historical `investigator:*` arms so this
#: version is graded on its own record rather than inheriting theirs.
SPECIALIST = "investigator:evidence_v2"

#: §64, held out -- earned on MAGNITUDE questions (`abs_move_exceeds`) only.
#: Adjudication 2026-09-26 row 2: on DIRECTION (`return_sign`/`beats_benchmark`)
#: the same arms score -8.7% held out and the best training-half weight is 0,
#: so this shrink is NOT applied to direction rows (see `recalibrate`).
SHRINK = 0.65

#: The `shrink_basis` strings written on every row. Frozen: a report groups on
#: them, and a reworded basis would split one population in two.
SHRINK_BASIS_MAGNITUDE = "§64 magnitude held-out"
SHRINK_BASIS_DIRECTION = "none: direction skill unmeasured"

_DIRECTION_OBSERVABLES = ("beats_benchmark", "return_sign")


def recalibrate(raw: float, observable) -> tuple[float, str]:
    """(probability to write, shrink_basis) for one raw forecast.

    MAGNITUDE rows keep §64's shrink toward `BASE_RATE`, where it was earned.
    DIRECTION rows are written RAW: no direction calibration exists yet, and
    borrowing the magnitude one is "the wrong skill with the wrong correction"
    (audit 2026-09-26 C8). `forecast_reputation` recalibrates direction from
    `raw_probability` once it has n.
    """
    obs = getattr(observable, "value", observable)
    raw = float(raw)
    if obs in _DIRECTION_OBSERVABLES:
        return raw, SHRINK_BASIS_DIRECTION
    return BASE_RATE + SHRINK * (raw - BASE_RATE), SHRINK_BASIS_MAGNITUDE

#: §64: skill is at one day and gone by five.
HORIZON_DAYS = 1

#: A coin, until this arm has enough graded rows to estimate its own base rate.
#: Stated rather than assumed: "beats SPY tomorrow" is close to a coin flip by
#: construction and a wrong prior here biases every shrunk number.
BASE_RATE = 0.50

MODEL = "deepseek/deepseek-flash"

CONTRACT = """You are running an INVESTIGATION, not giving an opinion.

You will be shown evidence about one company. Produce a probability that its
total return over the NEXT ONE TRADING SESSION exceeds SPY's over the same
session.

Rules that decide whether your answer is used at all:

1. Reason ONLY from the evidence given. You have no browsing here and no
   memory of this company's recent news. If a field is null, it is UNKNOWN --
   say so rather than filling it in.
2. Before the probability, list the specific facts that moved you. START each
   one with the FIELD NAME it came from. A fact you cannot name a field for is
   not a fact.
3. State the FALSIFIER: what would have to be true for your call to be wrong.
4. One session is very short. Most of what is interesting about a company does
   not resolve in one day, and the honest answer to most of these is close to
   0.50. A confident number on weak evidence is the failure mode that made nine
   other specialists worse than useless -- they were not wrong about the world,
   they were overconfident about it.
5. Probabilities below 0.30 or above 0.70 require evidence in the packet that
   specifically bears on ONE DAY, such as an extreme recent move, a very high
   realised volatility, or a fresh dated analyst revision. Momentum over 63
   sessions is not evidence about tomorrow.

Return STRICT JSON, nothing before or after. Every string must be PLAIN: no
quotation marks inside a string, no newlines inside a string, no percent signs
attached to a quoted number. Use flat strings, not nested objects.

{"ticker": "AAA", "probability": 0.52,
 "facts_used": ["rev_qoq 0.06 is modest and says nothing about one session",
                "revisions_90d 70 with net_raises_90d 44 is a live flow"],
 "falsifier": "what would make this wrong, in one plain sentence",
 "confidence_in_the_evidence": "medium",
 "what_is_missing": ["intraday_flow"]}
"""

#: THE SIM'S DAILY CONTRACT (u_forecast, 2026-09-25). One call, two horizons.
#:
#: Murat's order was h=1 AND h=5 rows for every name, every sim day. Two calls
#: per name would double the spend for a second number §64 says carries almost
#: nothing (h=5 skill +0.09%); one call that states both keeps the h=1 process
#: intact and buys the h=5 row at the price of a few output tokens. Because the
#: prompt differs from v2, the arm is versioned: `investigator:evidence_v3`
#: is graded on its own record and never pooled with v2's.
SPECIALIST_DAILY = "investigator:evidence_v3"
DAILY_HORIZONS = (1, 5)

# ── the day's refusal states, each named for its TRUE cause (2026-09-28) ──────
#: The ledger the cap reads and the spend AGREE the cap is reached.
REFUSED_CAP = "REFUSED_CAP"
#: The cap cannot confirm the writer's spend: the ledger did not move after a
#: SUCCESSFUL call, is unreadable, or holds unpriced rows (a lower bound).
REFUSED_CAP_READER_DISAGREES = "REFUSED_CAP_READER_DISAGREES"
#: The OpenClaw gateway / CLI failed the call (`TIMEOUT`, `RC_NONZERO`, or the
#: CLI could not be run) on every retry. NOT terminal for the day: a later sim
#: cycle resumes it (`resume_gate`). 2026-09-27 was this, filed as REFUSED_CAP.
REFUSED_DEPENDENCY_DOWN = "REFUSED_DEPENDENCY_DOWN"
#: `openclaw_client.agent` statuses that are the transport's failure, not the
#: model's answer. EMPTY_LOG / UNPARSEABLE_ENVELOPE stay per-name refusals.
TRANSPORT_FAILURE_STATUSES = ("TIMEOUT", "RC_NONZERO")
#: Receipt states that end the UTC day. REFUSED_DEPENDENCY_DOWN is not one of
#: them until `FORECAST_DEP_MAX_RUNS_PER_DAY` runs have ended in it.
TERMINAL_STATES = ("DONE", REFUSED_CAP, REFUSED_CAP_READER_DISAGREES, "DEGRADED")
#: What the unit does without the gateway. The evidence packet is ALREADY built
#: from disk only (no browsing: CONTRACT says so); the LLM call through OpenClaw
#: IS the forecast. There is no forecast to degrade to, so the run refuses by
#: the true name rather than write a number nobody made.
DEGRADE_PATH = ("none: the packet is disk-only already and the OpenClaw call is "
                "the forecaster; without it there is no forecast to write, so "
                "the run refuses as REFUSED_DEPENDENCY_DOWN and a later cycle "
                "retries. The gateway is never restarted from here.")


def _iso_now(now_fn=None) -> str:
    return (now_fn or (lambda: datetime.now(timezone.utc)))().isoformat(timespec="seconds")


def resume_gate(prior: dict | None, *, now: datetime | None = None) -> dict | None:
    """None when today's unit may (re)start; else the skip it must return.

    A TERMINAL state ends the day. REFUSED_DEPENDENCY_DOWN ends it only after
    `FORECAST_DEP_MAX_RUNS_PER_DAY` failed runs; before that, a new run waits
    `FORECAST_DEP_RETRY_MIN_GAP_S` after the last failure. Shared by
    `daily_forecast` and `sim_run.u_forecast` so the two cannot disagree.
    """
    if not prior:
        return None
    st = prior.get("state")
    base = {"state": st, "n_rows_written": prior.get("n_rows_written")}
    if st in TERMINAL_STATES:
        return {**base, "skipped": f"already ran today ({prior.get('day')})"}
    if st != REFUSED_DEPENDENCY_DOWN:
        return None                                     # RUNNING: resume
    dep = prior.get("dependency") or {}
    runs = int(dep.get("runs_ended_down") or 0)
    cap = int(_config.FORECAST_DEP_MAX_RUNS_PER_DAY)
    if runs >= cap:
        return {**base, "skipped": (f"dependency down on {runs} of {cap} runs "
                                    f"today: no further retry today")}
    last = dep.get("last_failed_utc")
    now = now or datetime.now(timezone.utc)
    try:
        last_dt = datetime.fromisoformat(str(last)) if last else None
    except ValueError:
        last_dt = None
    gap = float(_config.FORECAST_DEP_RETRY_MIN_GAP_S)
    if last_dt is not None and (now - last_dt).total_seconds() < gap:
        return {**base, "skipped": (f"dependency down at {last}; run {runs + 1} of "
                                    f"{cap} waits {gap:.0f}s after the last failure")}
    return None

CONTRACT_DAILY = """You are running an INVESTIGATION, not giving an opinion.

You will be shown evidence about one company. Produce TWO probabilities:
  probability_1d: its total return over the NEXT ONE TRADING SESSION exceeds SPY's
  probability_5d: its total return over the NEXT FIVE TRADING SESSIONS exceeds SPY's

Rules that decide whether your answer is used at all:

1. Reason ONLY from the evidence given. You have no browsing here and no
   memory of this company's recent news. If a field is null, it is UNKNOWN --
   say so rather than filling it in. Do not call any tool.
2. Before the probabilities, list the specific facts that moved you. START each
   one with the FIELD NAME it came from. A fact you cannot name a field for is
   not a fact.
3. State the FALSIFIER: what would have to be true for your call to be wrong.
4. One session is very short and five is not much longer. The honest answer to
   most of these is close to 0.50. A confident number on weak evidence is the
   failure mode that made nine other specialists worse than useless -- they
   were not wrong about the world, they were overconfident about it.
5. Probabilities below 0.30 or above 0.70 require evidence in the packet that
   specifically bears on the horizon, such as an extreme recent move, a very
   high realised volatility, or a fresh dated analyst revision.

Return STRICT JSON, nothing before or after. Every string must be PLAIN: no
quotation marks inside a string, no newlines inside a string. Use flat strings.

{"ticker": "AAA", "probability_1d": 0.52, "probability_5d": 0.51,
 "facts_used": ["rev_qoq 0.06 is modest and says nothing about one session"],
 "falsifier": "what would make this wrong, in one plain sentence",
 "confidence_in_the_evidence": "medium",
 "what_is_missing": ["intraday_flow"]}
"""

#: §64 / Q-3: the nine thematic persona arms, RETIRED at optimal weight zero
#: (held-out skill -27.98%, discrimination negative). A spending decision, not
#: a research one. Their code stays (`llm_swarm._spec`, `why_moved.LENSES`);
#: they are simply never on the daily cadence, and every u_forecast receipt
#: lists them so the retirement is visible where the forecasting happens.
RETIRED_WEIGHT_ZERO = ("geopolitical", "behavioral_narrative", "ownership_flow",
                       "event_news", "company_fundamental", "biotech_pharma",
                       "semis_technology", "accounting_forensics",
                       "options_volatility")
RETIRED_NOTE = ("RETIRED_WEIGHT_ZERO: NEGATIVE_RESULTS §64 -- the nine thematic "
                "personas score -27.98% held out with negative discrimination; "
                "optimal weight 0.00. No cadence job asks them. As of "
                "2026-09-25 none had written a row since 2026-08-12.")

#: What the model is told is already settled, so the answer is not a rediscovery.
STANDING = [
    "§59 price/volume alone cannot rank this cross-section at 21 sessions",
    "§62 eleven exit rules all lose to holding; a -2% stop is 0.93 daily sigma",
    "§63 revenue growth with margin expansion has NO dose-response",
    "analyst price-target LEVELS are CLOSED/PERVERSE (t -3.6); revisions differ",
]


def evidence_inputs(*, asof=None) -> dict:
    """Everything a packet is built from, loaded ONCE: the live panel row per
    symbol, the latest SEC quarter, the 90-day revision flow. Heavy (the bars
    panel), which is why the sim runs this out of process."""
    from backend.services import xs_ranker as XR

    bars = XR.load_bars(XR.survivorship_free_paths())
    panel = XR.build_panel(bars)
    live = (panel[panel["eligible"]].sort_values("date")
            .drop_duplicates("symbol", keep="last"))

    fund: dict[str, dict] = {}
    try:
        from backend.services import inflection as INF
        q = INF.add_features(INF.quarterly_panel())
        q = q[q["sequential_ok"]].sort_values("filed").drop_duplicates(
            "ticker", keep="last")
        for r in q.itertuples():
            fund[r.ticker] = {"rev_qoq": _r(r.rev_qoq),
                              "gross_margin": _r(r.gm),
                              "gross_margin_chg": _r(r.gm_chg),
                              "last_filed": str(r.filed)[:10]}
    except Exception:                                              # noqa: BLE001
        pass

    rev: dict[str, dict] = {}
    p = Path(_config.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
    if p.exists():
        d = pd.read_parquet(p)
        d["event_date"] = pd.to_datetime(d["event_date"], errors="coerce", utc=True)
        now = pd.Timestamp(asof or date.today(), tz="UTC")
        # STRICTLY in the past. One future-dated row exists in this vendor feed
        # (a Jefferies row on AMR) and a `<=` filter removes it by construction.
        d = d[(d["event_date"] <= now)
              & (d["event_date"] >= now - pd.Timedelta(days=90))]
        ta = d["target_action"].str.lower()
        g = d.assign(up=(ta == "raises").astype(int),
                     dn=(ta == "lowers").astype(int)).groupby("ticker")
        for t, sub in g:
            rev[t] = {"revisions_90d": int(len(sub)),
                      "net_raises_90d": int(sub["up"].sum() - sub["dn"].sum()),
                      "median_target_change": _r(sub["target_change"].median()),
                      "last_revision": str(sub["event_date"].max())[:10]}

    return {"live": {r.symbol: r for r in live.itertuples()}, "fund": fund,
            "rev": rev, "XR": XR}


def top_revision_tickers(inputs: dict, n: int) -> list[str]:
    """Names with the most 90-day revision activity that are also eligible.
    Fresh dated events are the one input that bears on a short horizon."""
    ranked = sorted(inputs["rev"].items(), key=lambda kv: -kv[1]["revisions_90d"])
    return [t for t, _ in ranked if t in inputs["live"]][:n]


def packet_for(ticker: str, inputs: dict) -> dict | None:
    """One compact, fully point-in-time packet, or None when the name has no
    eligible panel row (the caller reports it UNPRICED, never skips silently)."""
    r = inputs["live"].get(ticker)
    if r is None:
        return None
    XR = inputs["XR"]
    return {
        "ticker": ticker, "asof": str(r.date)[:10], "price": _r(r.close, 2),
        "cost_bps_round_trip": round(XR.round_trip_bps(r.median_dollar_vol), 1),
        "liquidity_band": XR.liquidity_band(r.median_dollar_vol),
        "mom_21": _r(r.mom_21), "mom_63": _r(r.mom_63),
        "ret_1d": _r(r.rev_1), "ret_5d": _r(r.rev_5),
        "realised_vol_63_annual": _r(r.vol_63), "beta_63": _r(r.beta_63),
        "vs_52w_high": _r(r.px_vs_52w_high), "vs_ma200": _r(r.px_vs_ma200),
        "drawdown_63": _r(r.max_drawdown_63),
        **inputs["fund"].get(ticker, {}), **inputs["rev"].get(ticker, {}),
    }


def evidence_packets(n: int, *, asof=None, tickers: list[str] | None = None,
                     inputs: dict | None = None) -> list[dict]:
    """One packet per candidate. Default candidates: the top-`n` revision names
    (the v2 CLI's population); `tickers` overrides them, in order."""
    inputs = inputs or evidence_inputs(asof=asof)
    names = tickers if tickers is not None else top_revision_tickers(inputs, n)
    out = []
    for t in names:
        pk = packet_for(t, inputs)
        if pk is not None:
            out.append(pk)
        if len(out) >= n:
            break
    return out


def _r(v, nd: int = 4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, nd)


def _message(packet: dict, contract: str) -> str:
    return (contract
            + "\n\nSTANDING RESULTS (already settled, do not rediscover):\n"
            + "\n".join(f"- {s}" for s in STANDING)
            + "\n\nEVIDENCE PACKET:\n"
            + json.dumps(packet, indent=1))


def parse_reply(txt: str, *, keys: tuple[str, ...] = ("probability",)) -> dict:
    """The model's JSON, or a DEGRADED parse of its scalar fields, or a refusal.

    2 of the first 6 v2 replies failed with "Expecting ',' delimiter" deep
    inside `facts_used` -- an unescaped quote in a prose field. Discarding the
    whole reply throws away a probability the model did state, and "fixing" the
    JSON would mean guessing what it meant to write. So: lift ONLY the scalar
    fields that can be read unambiguously, mark the row `parse: degraded`, and
    record the structured reasoning as missing rather than reconstruct it.
    """
    txt = (txt or "").strip()
    if "{" not in txt or "}" not in txt:
        return {"refused": "no JSON in reply", "raw": txt[:300]}
    blob = txt[txt.index("{"):txt.rindex("}") + 1]
    try:
        return json.loads(blob)
    except ValueError as exc:
        out: dict = {"parse": "degraded", "parse_error": str(exc)[:120],
                     "facts_used": None}
        for k in keys:
            m = re.search(r'"' + re.escape(k) + r'"\s*:\s*([01]?\.?\d+)', blob)
            if m:
                out[k] = float(m.group(1))
        if not any(k in out for k in keys):
            return {"refused": f"unparseable JSON and no probability: {exc}",
                    "raw": txt[:300]}
        c = re.search(r'"confidence_in_the_evidence"\s*:\s*"(\w+)"', blob)
        if c:
            out["confidence_in_the_evidence"] = c.group(1)
        return out


def ask(packet: dict, *, model: str = MODEL, timeout: float = 420.0,
        contract: str = CONTRACT, purpose: str = "investigator_forecast",
        keys: tuple[str, ...] = ("probability",)) -> dict:
    """One investigation through `openclaw_client.agent`, which writes the
    call's telemetry row (tokens, cost, model) to the same ledger every cap
    reads. Returns the parsed JSON (plus `_call`), or a refusal row."""
    from backend.services import openclaw_client as OC

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(_message(packet, contract))
        msg = fh.name
    try:
        res = OC.agent(msg, model=model, timeout=timeout, purpose=purpose)
    except (OSError, subprocess.SubprocessError) as exc:
        # the CLI could not be launched or run: the DEPENDENCY, not the name
        return {"refused": f"{type(exc).__name__}: {str(exc)[:120]}",
                "transport_failed": True}
    finally:
        try:
            Path(msg).unlink()
        except OSError:
            pass
    call = {k: res.get(k) for k in ("status", "call_id", "usage",
                                    "openclaw_cost_usd", "latency_s",
                                    "session_id")}
    if res.get("status") != "OK":
        return {"refused": f"openclaw {res.get('status')} (rc {res.get('rc')})",
                "stderr": (res.get("stderr") or "")[-200:], "_call": call,
                "transport_failed": res.get("status") in TRANSPORT_FAILURE_STATUSES}
    out = parse_reply(res.get("reply") or "", keys=keys)
    out["_call"] = call
    return out


# ───────────────────────── the sim's daily unit (u_forecast) ─────────────────

def forecast_day_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "forecasts"


def day_receipt_path(day: str) -> Path:
    return forecast_day_dir() / f"day_{day}.json"


def _murat_book_tickers(path: Path | None = None) -> list[str]:
    import yaml
    p = path or (REPO / "backend" / "data" / "murat_book.yaml")
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return []
    return [str(x["ticker"]).upper() for x in (d.get("positions") or [])
            if isinstance(x, dict) and x.get("ticker")]


def llm_book_records(path: Path | None = None) -> list[dict]:
    """Frozen llm_portfolio books, read straight from `books.jsonl`.

    Twins (records carrying `parent_book_id`) are excluded: a random-band twin's
    names are the CONTROL, and forecasting them would spend on noise."""
    p = path or (Path(_config.OPTIMUS_LEDGER_DIR) / "llm_portfolio" / "books.jsonl")
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("parent_book_id") or r.get("parent_hash"):
            continue
        # A twin frozen as a standalone book (revision_flow_v0_random_twin,
        # 2026-09-25, before twins carried parent_book_id) took 20 of the day's
        # 60 forecast slots with control names -- the reviewer's row 7.
        if "random_twin" in str(r.get("name") or "") or str(r.get("kind") or "") == "twin":
            continue
        out.append(r)
    return out


def _llm_book_tickers(path: Path | None = None) -> list[str]:
    out = []
    for r in llm_book_records(path):
        for pos in r.get("positions") or []:
            t = (pos or {}).get("ticker")
            if t and str(t).upper() not in ("CASH", "$CASH"):
                out.append(str(t).upper())
    return out


def _funnel_tickers(path: Path | None = None) -> list[str]:
    p = Path(path or _config.IC_FUNNEL_PATH)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(c["ticker"]).upper() for c in (d.get("candidates") or [])
            if isinstance(c, dict) and c.get("ticker")]


def forecast_universe(*, sources: dict[str, list[str]], max_names: int) -> dict:
    """The union, in PRIORITY order, truncated at `max_names`.

    Order: Murat's book, the frozen llm_portfolio books, the funnel shortlist,
    the top revision names. What was cut is named on the receipt, never dropped
    silently."""
    order = ("murat_book", "llm_books", "funnel", "top_revisions")
    seen: dict[str, str] = {}
    for src in order:
        for t in sources.get(src) or []:
            t = str(t).upper()
            if t and t not in seen:
                seen[t] = src
    names = list(seen)
    return {"tickers": names[:max_names], "cut": names[max_names:],
            "source_of": seen,
            "n_by_source": {s: len(sources.get(s) or []) for s in order}}


def _spent_today(day: str, *, telemetry_path: Path | None) -> dict:
    """Today's u_forecast spend, from the SAME ledger the calls write to."""
    from backend.services import llm_telemetry as LT
    return LT.spend(since=day, path=telemetry_path,
                    purpose=_config.FORECAST_PURPOSE)


def daily_forecast(*, today: str | None = None,
                   max_names: int | None = None,
                   cap_usd: float | None = None,
                   model: str | None = None,
                   sources: dict[str, list[str]] | None = None,
                   inputs: dict | None = None,
                   ask_fn=None,
                   packet_fn=None,
                   ledger_path: Path | None = None,
                   telemetry_path: Path | None = None,
                   receipt_dir: Path | None = None,
                   sleep_fn=None,
                   now_fn=None) -> dict:
    """Once per UTC day: h=1 AND h=5 rows for every name in the union.

    Idempotent. The day receipt `forecasts/day_<date>.json` is written at START
    (`state: RUNNING`) and after every name, so a crash resumes where it
    stopped instead of re-asking (and re-paying for) names already written. A
    receipt in a TERMINAL state (DONE / REFUSED_CAP /
    REFUSED_CAP_READER_DISAGREES / DEGRADED) ends the day.

    EVERY REFUSAL NAMES ITS TRUE CAUSE (2026-09-28). On 2026-09-27 the OpenClaw
    gateway dropped the first call (code 1006) and the day was filed
    REFUSED_CAP with $0.00 of $2.00 spent -- terminal, no retry, 0 rows. Now:

    * `REFUSED_CAP` only when the ledger the cap reads is readable, complete
      and at or over the cap: reader and spend AGREE.
    * `REFUSED_CAP_READER_DISAGREES` when the cap cannot confirm the writer:
      after the first SUCCESSFUL call the ledger did not move (2026-09-21's
      $10.05 under a $2.00 cap), or the ledger is unreadable or a lower bound.
      The first-flush check is made only on a call whose status is OK; a failed
      call costs nothing and proves nothing about the cap.
    * `REFUSED_DEPENDENCY_DOWN` when the transport failed
      (`TRANSPORT_FAILURE_STATUSES`, or the CLI could not be run) on
      `FORECAST_DEP_RETRY_MAX_ATTEMPTS` calls for one name, sleeping
      `FORECAST_DEP_RETRY_BACKOFF_S` between them. Not terminal: `resume_gate`
      lets a later cycle resume after `FORECAST_DEP_RETRY_MIN_GAP_S`, up to
      `FORECAST_DEP_MAX_RUNS_PER_DAY` runs. The receipt's `dependency` block
      counts every call and every failure. Nothing here restarts the gateway.
    """
    import time as _time

    from backend.services import belief_state as B

    sleep_fn = sleep_fn or _time.sleep
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    day = today or now_fn().date().isoformat()
    max_names = int(max_names or _config.FORECAST_MAX_NAMES_PER_DAY)
    cap_usd = float(cap_usd if cap_usd is not None else _config.FORECAST_DAILY_CAP_USD)
    model = model or _config.FORECAST_MODEL
    rdir = Path(receipt_dir) if receipt_dir is not None else forecast_day_dir()
    rpath = rdir / f"day_{day}.json"
    max_attempts = max(1, int(_config.FORECAST_DEP_RETRY_MAX_ATTEMPTS))
    backoff = tuple(float(x) for x in _config.FORECAST_DEP_RETRY_BACKOFF_S) or (0.0,)

    prior = None
    if rpath.exists():
        try:
            prior = json.loads(rpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = None
    gate = resume_gate(prior, now=now_fn())
    if gate is not None:
        return {**gate, "receipt": str(rpath)}

    if sources is None:
        inputs = inputs or evidence_inputs(asof=day)
        sources = {"murat_book": _murat_book_tickers(),
                   "llm_books": _llm_book_tickers(),
                   "funnel": _funnel_tickers(),
                   "top_revisions": top_revision_tickers(
                       inputs, _config.FORECAST_TOP_REVISION_NAMES)}
    if packet_fn is None:
        if inputs is None:
            inputs = evidence_inputs(asof=day)
        packet_fn = lambda t: packet_for(t, inputs)                # noqa: E731
    uni = forecast_universe(sources=sources, max_names=max_names)
    ask_fn = ask_fn or (lambda pk: ask(pk, model=model, contract=CONTRACT_DAILY,
                                       purpose=_config.FORECAST_PURPOSE,
                                       keys=("probability_1d", "probability_5d")))

    rec = {"receipt": "u_forecast_day", "day": day, "state": "RUNNING",
           "licence": "PRODUCT_EXPERIMENT", "specialist": SPECIALIST_DAILY,
           "model": model, "horizons": list(DAILY_HORIZONS), "shrink": SHRINK,
           "shrink_applied_to": "magnitude rows only", "direction_rows": SHRINK_BASIS_DIRECTION,
           "base_rate_assumed": BASE_RATE, "cap_usd": cap_usd,
           "max_names": max_names, "universe": uni,
           "retired_weight_zero": list(RETIRED_WEIGHT_ZERO),
           "retired_note": RETIRED_NOTE,
           "done": [], "unpriced": [], "refused": [], "n_rows_written": 0,
           "dependency": {"name": "OpenClaw gateway (openclaw_client.agent)",
                          "retry_policy": {
                              "max_calls_per_name_per_run": max_attempts,
                              "backoff_s": list(backoff),
                              "max_runs_per_utc_day": int(_config.FORECAST_DEP_MAX_RUNS_PER_DAY),
                              "min_gap_between_runs_s": float(_config.FORECAST_DEP_RETRY_MIN_GAP_S),
                              "unit_timeout_s": float(_config.FORECAST_UNIT_TIMEOUT_S)},
                          "degrade_path": DEGRADE_PATH,
                          "n_calls": 0, "n_failed_calls": 0, "n_retries": 0,
                          "runs": 0, "runs_ended_down": 0,
                          "last_failed_utc": None, "failures": []},
           "started_utc": _iso_now(now_fn)}
    if prior and prior.get("state") in ("RUNNING", REFUSED_DEPENDENCY_DOWN):
        for k in ("done", "unpriced", "refused", "n_rows_written"):
            rec[k] = prior.get(k, rec[k])
        pdep = prior.get("dependency") or {}
        for k in ("n_calls", "n_failed_calls", "n_retries", "runs",
                  "runs_ended_down", "last_failed_utc", "failures"):
            if k in pdep:
                rec["dependency"][k] = pdep[k]
        rec["resumed"] = True
        rec["resumed_from_state"] = prior.get("state")
    dep = rec["dependency"]
    dep["runs"] = int(dep.get("runs") or 0) + 1

    def flush() -> None:
        rdir.mkdir(parents=True, exist_ok=True)
        tmp = rpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        tmp.replace(rpath)

    def transport_failed(ans: dict, call: dict) -> bool:
        return bool(ans.get("transport_failed")) or \
            call.get("status") in TRANSPORT_FAILURE_STATUSES

    flush()
    finished = set(rec["done"]) | set(rec["unpriced"]) \
        | {r["ticker"] for r in rec["refused"]}
    first_check: dict | None = None
    spent = 0.0
    for t in uni["tickers"]:
        if t in finished:
            continue
        s = _spent_today(day, telemetry_path=telemetry_path)
        if not s:
            rec.update(state=REFUSED_CAP_READER_DISAGREES,
                       why=("today's u_forecast spend is UNKNOWN (no telemetry "
                            "ledger could be opened); a cap that cannot read "
                            "cannot bind, so the day is refused"))
            break
        spent = float(s.get("total_cost_usd") or 0.0)
        rec["spent_usd"] = spent
        if s.get("total_is_lower_bound"):
            rec.update(state=REFUSED_CAP_READER_DISAGREES,
                       why=f"{s.get('n_unpriced_calls')} unpriced call(s): the "
                           f"spend total is a LOWER BOUND and cannot bind a cap")
            break
        if spent >= cap_usd:
            rec.update(state=REFUSED_CAP,
                       why=f"spent ${spent:.4f} >= cap ${cap_usd:.2f} today "
                           f"(read from the same ledger the calls write)")
            break

        pk = packet_fn(t)
        if pk is None:
            rec["unpriced"].append(t)
            flush()
            continue

        # ---- the call, retried while the DEPENDENCY fails (never the name) ----
        attempt, down = 0, False
        while True:
            ans = ask_fn(pk)
            call = ans.pop("_call", {}) or {}
            dep["n_calls"] += 1
            if not transport_failed(ans, call):
                break
            attempt += 1
            dep["n_failed_calls"] += 1
            dep["last_failed_utc"] = _iso_now(now_fn)
            dep["failures"] = (dep["failures"] + [{
                "ticker": t, "attempt": attempt, "utc": dep["last_failed_utc"],
                "status": call.get("status"), "call_id": call.get("call_id"),
                "why": str(ans.get("refused"))[:120],
                "stderr": str(ans.get("stderr") or "")[-160:]}])[-20:]
            flush()
            if attempt >= max_attempts:
                down = True
                break
            wait = backoff[min(attempt - 1, len(backoff) - 1)]
            print(f"  {t}: dependency failure {attempt}/{max_attempts} "
                  f"({call.get('status') or ans.get('refused')}); retry in "
                  f"{wait:.0f}s", flush=True)
            dep["n_retries"] += 1
            sleep_fn(wait)
        if down:
            dep["runs_ended_down"] = int(dep.get("runs_ended_down") or 0) + 1
            last = dep["failures"][-1]
            rec.update(state=REFUSED_DEPENDENCY_DOWN,
                       why=(f"the OpenClaw call failed {attempt} time(s) in a row on "
                            f"{t} (last: {last['status'] or last['why']}); the cap "
                            f"was NOT the cause (spent ${spent:.4f} of "
                            f"${cap_usd:.2f}). Run {dep['runs']} ended down "
                            f"({dep['runs_ended_down']} of "
                            f"{int(_config.FORECAST_DEP_MAX_RUNS_PER_DAY)} allowed "
                            f"today); a later cycle resumes after "
                            f"{float(_config.FORECAST_DEP_RETRY_MIN_GAP_S):.0f}s"))
            break

        if first_check is None and call.get("call_id") \
                and call.get("status", "OK") == "OK":
            after = _spent_today(day, telemetry_path=telemetry_path)
            delta = float((after or {}).get("total_cost_usd") or 0.0) - spent
            first_check = {"ledger_delta_usd": round(delta, 6),
                           "writer_openclaw_cost_usd": call.get("openclaw_cost_usd"),
                           "ledger_rows_after": (after or {}).get("n_calls"),
                           "call_status": call.get("status", "OK")}
            rec["first_flush_check"] = first_check
            print(f"  first flush: ledger delta ${delta:.5f}, openclaw's own "
                  f"estimate ${call.get('openclaw_cost_usd')}", flush=True)
            if delta <= 0:
                rec.update(state=REFUSED_CAP_READER_DISAGREES,
                           why=("a SUCCESSFUL call was made but the ledger the cap "
                                "reads did not move: the cap cannot bind"))
                flush()
                break
        ps = {h: ans.get(f"probability_{h}d") for h in DAILY_HORIZONS}
        if "refused" in ans or not all(isinstance(v, (int, float))
                                       and 0.0 <= float(v) <= 1.0
                                       for v in ps.values()):
            rec["refused"].append({"ticker": t, "why": str(
                ans.get("refused") or f"probabilities {ps}")[:160]})
            flush()
            continue
        recs = []
        for h, raw in ps.items():
            raw = float(raw)
            shrunk, basis = recalibrate(raw, B.Observable.BEATS_BENCHMARK)
            try:
                recs.append(B.make_prediction(
                    ticker=t, specialist=SPECIALIST_DAILY,
                    observable=B.Observable.BEATS_BENCHMARK,
                    horizon_days=h, probability=shrunk, benchmark="SPY",
                    thesis=json.dumps(ans.get("facts_used"))[:1200],
                    counter_thesis=str(ans.get("falsifier"))[:800],
                    next_observable=json.dumps(ans.get("what_is_missing"))[:300],
                    model=model, model_version="evidence_v3",
                    prompt=CONTRACT_DAILY, input_snapshot=pk,
                    licence="PRODUCT_EXPERIMENT", decision_date=day,
                    raw_probability=raw, shrink_basis=basis,
                    notes_text=(f"u_forecast {day}: raw {raw:.3f} written as "
                                f"{shrunk:.3f} ({basis}); "
                                f"source {uni['source_of'].get(t)}")))
            except ValueError as exc:
                rec["refused"].append({"ticker": t, "why": f"record: {exc}"[:160]})
        if recs:
            B.append(recs, path=ledger_path)
            rec["n_rows_written"] += len(recs)
            rec["done"].append(t)
            if call.get("call_id"):
                try:
                    from backend.services import llm_telemetry as LT
                    LT.attach_outputs(call["call_id"],
                                      prediction_ids=[r.prediction_id for r in recs],
                                      path=telemetry_path)
                except Exception:                                  # noqa: BLE001
                    pass
        flush()

    if rec["state"] == "RUNNING":
        rec["state"] = "DONE" if rec["n_rows_written"] > 0 else "DEGRADED"
        if rec["state"] == "DEGRADED":
            rec["why"] = ("zero forecast rows written today: "
                          f"{len(rec['unpriced'])} unpriced, "
                          f"{len(rec['refused'])} refused")
    s = _spent_today(day, telemetry_path=telemetry_path) or {}
    rec["spent_usd"] = s.get("total_cost_usd")
    rec["ended_utc"] = _iso_now(now_fn)
    flush()
    return {"state": rec["state"], "n_rows_written": rec["n_rows_written"],
            "n_done": len(rec["done"]), "n_unpriced": len(rec["unpriced"]),
            "n_refused": len(rec["refused"]), "spent_usd": rec["spent_usd"],
            "dependency_calls": dep["n_calls"],
            "dependency_failed_calls": dep["n_failed_calls"],
            "dependency_retries": dep["n_retries"],
            "dependency_runs_ended_down": dep["runs_ended_down"],
            "why": rec.get("why"), "receipt": str(rpath)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true",
                    help="build packets and print one; ask nothing")
    ap.add_argument("--daily", action="store_true",
                    help=("run the sim's u_forecast day by hand (idempotent per "
                          "UTC day; spends up to FORECAST_DAILY_CAP_USD)"))
    a = ap.parse_args(argv)

    if a.daily:
        res = daily_forecast(model=(a.model if a.model != MODEL else None))
        print(json.dumps(res, indent=1, default=str))
        return 0 if res.get("state") in ("DONE", None) or res.get("skipped") else 2

    packets = evidence_packets(a.n)
    print(f"{len(packets)} evidence packets built", flush=True)
    if not packets:
        print("REFUSED: no candidate had both a price row and revision history")
        return 2
    if a.dry_run:
        print(json.dumps(packets[0], indent=1))
        return 0

    from backend.services import belief_state as B

    rows, recs = [], []
    for i, pk in enumerate(packets, 1):
        ans = ask(pk, model=a.model)
        if "refused" in ans or not isinstance(ans.get("probability"), (int, float)):
            print(f"  {i:>3}/{len(packets)} {pk['ticker']:<6} REFUSED "
                  f"{str(ans.get('refused'))[:70]}", flush=True)
            rows.append({"ticker": pk["ticker"], **ans})
            continue
        raw = float(ans["probability"])
        if not 0.0 <= raw <= 1.0:
            print(f"  {i:>3}/{len(packets)} {pk['ticker']:<6} REFUSED "
                  f"probability {raw}", flush=True)
            continue
        # §64's shrink is a MAGNITUDE correction; a direction row goes raw.
        shrunk, basis = recalibrate(raw, B.Observable.BEATS_BENCHMARK)
        rows.append({"ticker": pk["ticker"], "raw_probability": raw,
                     "probability": shrunk, **{k: v for k, v in ans.items()
                                               if k != "probability"}})
        try:
            recs.append(B.make_prediction(
                ticker=pk["ticker"], specialist=SPECIALIST,
                observable=B.Observable.BEATS_BENCHMARK,
                horizon_days=HORIZON_DAYS, probability=shrunk,
                benchmark="SPY",
                thesis=json.dumps(ans.get("facts_used"))[:1200],
                counter_thesis=str(ans.get("falsifier"))[:800],
                next_observable=json.dumps(ans.get("what_is_missing"))[:300],
                model=a.model, model_version="evidence_v2",
                prompt=CONTRACT, input_snapshot=pk,
                licence="PRODUCT_EXPERIMENT",
                raw_probability=raw, shrink_basis=basis,
                notes_text=(f"raw {raw:.3f} written as {shrunk:.3f} ({basis})")))
        except ValueError as exc:
            print(f"      record refused: {exc}", flush=True)
        print(f"  {i:>3}/{len(packets)} {pk['ticker']:<6} raw {raw:.2f} -> "
              f"{shrunk:.2f}  conf {str(ans.get('confidence_in_the_evidence'))[:6]:<6} "
              f"{len(ans.get('facts_used') or [])} facts", flush=True)

    written = 0
    if recs:
        B.append(recs)
        written = len(recs)

    ps = [r["probability"] for r in rows if "probability" in r]
    res = {"receipt": "investigator_forecast", "licence": "PRODUCT_EXPERIMENT",
           "specialist": SPECIALIST, "model": a.model,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "horizon_days": HORIZON_DAYS, "shrink": SHRINK,
           "shrink_applied_to": "magnitude rows only", "direction_rows": SHRINK_BASIS_DIRECTION,
           "base_rate_assumed": BASE_RATE,
           "n_packets": len(packets), "n_forecast": len(ps),
           "n_written_to_ledger": written,
           "mean_probability": float(np.mean(ps)) if ps else None,
           "spread": [float(np.min(ps)), float(np.max(ps))] if ps else None,
           "design_from": ("§64 -- process not persona (33 points of Brier skill "
                           "between the two families), h=1 (skill is +5.75% there "
                           "and +0.09% by h=5), shrink 0.65 (the failure is "
                           "overconfidence, not ignorance)"),
           "not_a_trade": ("a probability with information in it still needs a "
                           "probability-to-return calibration before it can be "
                           "sized, and that does not exist"),
           "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"forecasts_{date.today()}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n{len(ps)} forecasts, {written} written to the ledger; "
          f"mean {res['mean_probability']}, spread {res['spread']}")
    print(f"They grade themselves: the sim's `u_grade` unit resolves h=1 rows "
          f"on the next session's close.")
    print(f"-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
