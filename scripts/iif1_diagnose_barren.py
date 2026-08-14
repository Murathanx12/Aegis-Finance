"""Why did 23 of Night 1's 50 cells produce nothing? Ask the vendor, cheaply.

    python scripts/iif1_diagnose_barren.py --tickers CSCO,HD,AVB --arm A_snapshot

WHAT THIS IS AND IS NOT
=======================
It is a DIAGNOSTIC, not a night. It replays the real microtask chain against
the frozen Night-1 snapshot and reports why the forecast call did or did not
yield. It never mints, never touches the evidence ledger, and never writes an
`iif1_nights` receipt. Its spend is booked under its own purpose so it cannot
inflate the trial's measured cost.

SHAPE ONLY — THE BLIND IS NOT NEGOTIABLE
========================================
IIF-1 is a 40-night blind. Printing a forecaster's priors and posteriors during
it would put the thing under test in front of the people running it, and no
amount of "we only glanced" repairs that. So this prints the SHAPE of a reply
and never its content:

    did it parse · was it cut off at the token ceiling · what type the top level
    was · whether `forecasts` was a list and how long · which keys each cell
    carried · which observable names came back · whether the size bound arrived
    as a fraction or a percent · which drop code fired

Probabilities, rationales and raw text are read by the classifier and discarded.
The one deliberate exception is `--show-raw`, which exists for a chain that
fails in a way none of the above explains; it prints the raw reply and is
therefore BLIND-BREAKING. It refuses to run without `--i-accept-blind-break`,
and it names the tickers it burned so they can be excluded from the trial.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from backend.services import investigator_agent as A
from backend.services import iif1_features as F

#: Booked separately from the trial. A diagnostic that spent under the trial's
#: purpose would make the night look more expensive than it was, and the
#: funding rule (R1) turns on that exact number.
PURPOSE = "IIF1-DIAGNOSTIC"
CAMPAIGN = "brain_v3"


def classify_threshold(v) -> str:
    """Fraction, percent, or neither — WITHOUT reporting the number."""
    if v is None:
        return "null"
    if not isinstance(v, (int, float)):
        return f"not_a_number({type(v).__name__})"
    if 0 < v < 1.0:
        return "fraction_ok"
    if 1.0 <= v <= 100.0:
        return "looks_like_percent"
    return "out_of_any_plausible_range"


def shape_of(call) -> dict:
    """Everything diagnostic about a reply and nothing revealing."""
    out = {
        "task": call.task,
        "ok": call.ok,
        "finish_reason": call.finish_reason or "(vendor sent none)",
        "truncated": call.truncated,
        "tokens_out": call.tokens_out,
        "n_chars": len(call.text or ""),
        "parse_error": call.error[:120] if call.error else "",
    }
    p = call.parsed
    out["top_level_type"] = type(p).__name__
    if not isinstance(p, dict):
        return out
    fc = p.get("forecasts")
    out["forecasts_type"] = type(fc).__name__
    out["has_forecasts_key"] = "forecasts" in p
    out["other_top_level_keys"] = sorted(k for k in p if k != "forecasts")
    if not isinstance(fc, list):
        return out
    out["n_items"] = len(fc)
    out["item_keys"] = sorted({k for it in fc if isinstance(it, dict)
                               for k in it})
    out["observables"] = sorted({str(it.get("observable")) for it in fc
                                 if isinstance(it, dict)})
    out["horizons"] = sorted({it.get("horizon_days") for it in fc
                              if isinstance(it, dict)
                              and isinstance(it.get("horizon_days"), int)})
    out["threshold_units"] = dict(Counter(
        classify_threshold(it.get("threshold")) for it in fc
        if isinstance(it, dict)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tickers", required=True,
                    help="comma-separated, from the Night 1 receipt")
    ap.add_argument("--arm", default="A_snapshot",
                    help="A_snapshot is cheapest and reproduces 15 of the 23")
    ap.add_argument("--night", default="2026-08-14",
                    help="which frozen snapshot to replay")
    ap.add_argument("--max-tokens", type=int, default=A.MAX_TOKENS,
                    help="sweep this to test the token-ceiling hypothesis")
    ap.add_argument("--show-raw", action="store_true",
                    help="BLIND-BREAKING: print the raw reply text")
    ap.add_argument("--i-accept-blind-break", action="store_true")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    if a.show_raw and not a.i_accept_blind_break:
        print("--show-raw prints forecaster output during a live blind. "
              "Pass --i-accept-blind-break and expect to exclude these "
              "tickers from the trial.")
        return 2

    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    import datetime as _dt
    snap = F.load_snapshot(
        _dt.datetime.fromisoformat(f"{a.night}T12:00:00+00:00"), sandbox=False)
    feats = snap["features"]

    from backend.services.llm_swarm import default_llm_call
    from backend.services import llm_telemetry

    def call(*, system, user, model="deepseek-v4-flash", temperature=0.0,
             max_tokens=a.max_tokens):
        reply = default_llm_call(system, user, model=model,
                                 temperature=temperature,
                                 max_tokens=max_tokens, campaign=CAMPAIGN)
        llm_telemetry.record_call(
            provider="deepseek", model=model, purpose=PURPOSE, agent=PURPOSE,
            model_version=str(getattr(reply, "model_version", "") or model),
            prompt=system + user,
            tokens_in=int(getattr(reply, "tokens_in", 0) or 0),
            tokens_out=int(getattr(reply, "tokens_out", 0) or 0),
            latency_ms=getattr(reply, "latency_ms", None),
            meta={"diagnostic_for": "INTERNET-INVESTIGATOR-FWD-1",
                  "max_tokens": max_tokens})
        return reply

    # `_task` passes `max_tokens=A.MAX_TOKENS` EXPLICITLY on every call, so a
    # default on the injected client never reaches the vendor — the first run of
    # this script swept the ceiling to 4000 and got back `tokens_out: 1600`
    # every time. The knob has to be turned where the agent actually reads it.
    A.MAX_TOKENS = int(a.max_tokens)

    print(f"arm={a.arm}  max_tokens={a.max_tokens}  night={a.night}")
    print(f"{'ticker':<7s} {'fc':>3s} {'drop':<34s} trunc  finish_reasons")
    print("-" * 78)

    verdicts = Counter()
    details = []
    for t in tickers:
        agent = A.Investigator(a.arm, llm_call=call,
                               model="deepseek-v4-flash")
        inv = agent.investigate(t, feats.get(t, {}))
        row = inv.as_row()
        drop = row["terminal_drop_reason"] or "(produced)"
        verdicts[drop] += 1
        print(f"{t:<7s} {row['n_forecasts']:>3d} {drop:<34s} "
              f"{row['n_truncated_calls']:>5d}  {row['finish_reasons']}")
        shapes = [shape_of(c) for c in inv.calls]
        details.append({"ticker": t, "row": row, "calls": shapes})
        if a.show_raw:
            for c in inv.calls:
                if c.task == "forecast":
                    print(f"  RAW[{t}]: {c.text!r}")

    print("\nverdicts:", dict(verdicts))
    print("\nper-call shapes (forecast task only):")
    for d in details:
        fc = [s for s in d["calls"] if s["task"] == "forecast"]
        for s in fc:
            print(f"  {d['ticker']:<7s} {json.dumps(s, default=str)}")

    spent = llm_telemetry.spend()
    print(f"\ndiagnostic spend is booked under purpose={PURPOSE}, not the "
          f"trial. ledger total now ${spent.get('total_cost_usd', 0.0):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
