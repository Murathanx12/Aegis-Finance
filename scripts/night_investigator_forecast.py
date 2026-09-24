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

#: §64, held out. The raw probability is stored too; this is what gets used.
SHRINK = 0.65

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
2. Before the probability, list the specific facts that moved you, each with the
   FIELD NAME it came from. A fact you cannot name a field for is not a fact.
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

Return STRICT JSON, nothing before or after:

{"ticker": "...", "probability": 0.52,
 "facts_used": [{"field": "rev_qoq", "value": "...", "why_it_matters": "..."}],
 "falsifier": "what would make this wrong",
 "confidence_in_the_evidence": "high|medium|low",
 "what_is_missing": ["the field you most wish you had"]}
"""

#: What the model is told is already settled, so the answer is not a rediscovery.
STANDING = [
    "§59 price/volume alone cannot rank this cross-section at 21 sessions",
    "§62 eleven exit rules all lose to holding; a -2% stop is 0.93 daily sigma",
    "§63 revenue growth with margin expansion has NO dose-response",
    "analyst price-target LEVELS are CLOSED/PERVERSE (t -3.6); revisions differ",
]


def evidence_packets(n: int, *, asof=None) -> list[dict]:
    """One compact, fully point-in-time packet per candidate."""
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

    # Candidates: names with the most 90-day revision activity that are also
    # eligible. Fresh dated events are the one input in the packet that bears
    # on a ONE-DAY horizon, and §64 says a confident number needs one.
    ranked = sorted(rev.items(), key=lambda kv: -kv[1]["revisions_90d"])
    out = []
    live_idx = {r.symbol: r for r in live.itertuples()}
    for t, rv in ranked:
        r = live_idx.get(t)
        if r is None:
            continue
        out.append({
            "ticker": t, "asof": str(r.date)[:10], "price": _r(r.close, 2),
            "cost_bps_round_trip": round(XR.round_trip_bps(r.median_dollar_vol), 1),
            "liquidity_band": XR.liquidity_band(r.median_dollar_vol),
            "mom_21": _r(r.mom_21), "mom_63": _r(r.mom_63),
            "ret_1d": _r(r.rev_1), "ret_5d": _r(r.rev_5),
            "realised_vol_63_annual": _r(r.vol_63), "beta_63": _r(r.beta_63),
            "vs_52w_high": _r(r.px_vs_52w_high), "vs_ma200": _r(r.px_vs_ma200),
            "drawdown_63": _r(r.max_drawdown_63),
            **fund.get(t, {}), **rv,
        })
        if len(out) >= n:
            break
    return out


def _r(v, nd: int = 4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, nd)


def ask(packet: dict, *, model: str = MODEL, timeout: float = 420.0) -> dict:
    """One investigation. Returns the parsed JSON, or a refusal row."""
    body = (CONTRACT
            + "\n\nSTANDING RESULTS (already settled, do not rediscover):\n"
            + "\n".join(f"- {s}" for s in STANDING)
            + "\n\nEVIDENCE PACKET:\n"
            + json.dumps(packet, indent=1))
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(body)
        msg = fh.name
    try:
        r = subprocess.run(
            ["openclaw", "agent", "--message-file", msg, "--model", model],
            capture_output=True, text=True, timeout=timeout,
            shell=(sys.platform == "win32"), cwd=str(REPO))
    except subprocess.SubprocessError as exc:
        return {"refused": f"{type(exc).__name__}: {str(exc)[:120]}"}
    finally:
        try:
            Path(msg).unlink()
        except OSError:
            pass
    txt = (r.stdout or "").strip()
    if "{" not in txt or "}" not in txt:
        return {"refused": f"no JSON in reply (rc {r.returncode})",
                "raw": txt[:300], "stderr": (r.stderr or "")[-200:]}
    try:
        return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except ValueError as exc:
        return {"refused": f"unparseable JSON: {exc}", "raw": txt[:300]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true",
                    help="build packets and print one; ask nothing")
    a = ap.parse_args(argv)

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
        # §64's recalibration, applied BEFORE the number is written for use.
        shrunk = BASE_RATE + SHRINK * (raw - BASE_RATE)
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
                notes_text=(f"raw {raw:.3f} shrunk to {shrunk:.3f} at w={SHRINK} "
                            f"toward base {BASE_RATE} -- §64, held out")))
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
