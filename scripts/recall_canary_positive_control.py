"""Can the recall canary EVER say YES?

LLM-LEAKAGE-PROBE-1's canary returned `recall: NO` and `direction: UNSURE` on
419 of 419 identified items, in both eras. That is the reassuring answer, and a
canary that only ever returns the reassuring answer is indistinguishable from a
canary that is measuring prompt compliance rather than memory.

The probe stratified by era (pre-cutoff vs recent) and called that its positive
control. It is not one: both strata returned zero, so the stratification cannot
separate "the model does not remember these items" from "this instrument cannot
emit YES".

A real positive control asks about moves the model unambiguously knows and
checks that the SAME prompt, unchanged, produces YES with a correct direction.

  - If YES appears here and never on the probe's items, the canary works and
    the probe's 0/419 is a real measurement of no outcome recall.
  - If YES never appears even here, the canary is inert, the 0/419 means
    nothing, and the identified-vs-masked forecast gap becomes the ONLY
    evidence about leakage.

Either way the answer is a finding. This is the check that decides whether the
other check counted.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from backend.services import leakage_probe as lp  # noqa: E402

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
KEY = os.getenv("DEEPSEEK_API_KEY")

#: Moves that are in every retrospective ever written. If the model does not
#: recall the direction of THESE, it does not recall anything, and the canary is
#: measuring something other than memory. Truth is the realised 20d sign.
FAMOUS: list[tuple[str, str, str, str]] = [
    ("SPY", "2020-02-19", "SPDR S&P 500 ETF", "DOWN"),   # COVID top
    ("SPY", "2020-03-23", "SPDR S&P 500 ETF", "UP"),     # COVID bottom
    ("SPY", "2008-09-15", "SPDR S&P 500 ETF", "DOWN"),   # Lehman
    ("SPY", "2008-03-10", "SPDR S&P 500 ETF", "UP"),     # Bear Stearns
    ("AAPL", "2007-01-09", "Apple Inc", "UP"),           # iPhone launch
    ("TSLA", "2020-08-31", "Tesla Inc", "DOWN"),         # post-split top
    ("GME", "2021-01-27", "GameStop Corp", "DOWN"),      # squeeze peak
    ("NVDA", "2023-05-24", "NVIDIA Corp", "UP"),         # the AI print
    ("META", "2022-02-02", "Meta Platforms", "DOWN"),    # -26% day
    ("SVB", "2023-03-08", "SVB Financial", "DOWN"),      # the bank run
]


def ask(system: str, user: str) -> dict:
    body = {"model": "deepseek-v4-flash",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            # v4-flash emits reasoning tokens by default and they are drawn
            # from this same budget. At 400 the first run truncated 6 of 10
            # replies MID-JSON -- one of them mid-way through a correct YES.
            # A truncated reply read as a refusal is the reassuring answer
            # arriving by accident, which is the exact failure this control
            # exists to catch.
            "max_tokens": 2000, "temperature": 0.0}
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    return {"served_model": r.get("model"),
            "text": r["choices"][0]["message"].get("content", ""),
            "usage": r.get("usage")}


def main() -> None:
    if not KEY:
        raise SystemExit("DEEPSEEK_API_KEY not set")
    out, rows = [], []
    for ticker, as_of, company, truth in FAMOUS:
        system, user = lp.recall_canary(ticker, as_of, company)
        try:
            resp = ask(system, user)
        except Exception as exc:                      # noqa: BLE001
            rows.append({"ticker": ticker, "as_of": as_of, "error": str(exc)[:120]})
            continue
        try:
            parsed = lp.extract_json(resp["text"]) or {}
        except Exception:                             # noqa: BLE001
            # An unparseable reply is not a NO. It is a missing answer, and
            # counting it as a NO would inflate exactly the reassuring number
            # this control exists to distrust.
            rows.append({"ticker": ticker, "as_of": as_of, "truth_20d": truth,
                         "recall": "UNPARSEABLE", "direction_20d": "",
                         "directional": False, "correct": False,
                         "served_model": resp["served_model"],
                         "what": resp["text"][:160]})
            continue
        said = str(parsed.get("recall", "")).strip().upper()
        d20 = str(parsed.get("direction_20d", "")).strip().upper()
        rows.append({"ticker": ticker, "as_of": as_of, "truth_20d": truth,
                     "recall": said, "direction_20d": d20,
                     "directional": d20 in ("UP", "DOWN"),
                     "correct": d20 == truth,
                     "served_model": resp["served_model"],
                     "what": str(parsed.get("what", ""))[:120]})
        out.append(resp)

    ok = [r for r in rows if "error" not in r]
    yes = [r for r in ok if r["recall"] == "YES"]
    directional = [r for r in ok if r.get("directional")]
    correct = [r for r in directional if r["correct"]]

    print(f"n asked            : {len(rows)}  (errors: {len(rows) - len(ok)})")
    print(f"recall == YES      : {len(yes)}/{len(ok)}")
    print(f"gave a direction   : {len(directional)}/{len(ok)}")
    print(f"direction correct  : {len(correct)}/{len(directional)}"
          if directional else "direction correct  : n/a")
    print("recall values      :", dict(Counter(r["recall"] for r in ok)))
    print()
    for r in rows:
        print(json.dumps(r))

    verdict = (
        "CANARY IS LIVE — it can emit YES, so the probe's 0/419 on its own "
        "items is a real measurement of no outcome recall"
        if directional else
        "CANARY IS INERT — it never commits a direction even on moves every "
        "retrospective covers, so the probe's 0/419 measures prompt compliance "
        "and NOT memory; the identified-vs-masked forecast gap becomes the only "
        "evidence about leakage")
    print("\nVERDICT:", verdict)

    dest = Path("backend/data/leakage_probe/positive_control.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(
        {"rows": rows, "n": len(ok), "n_recall_yes": len(yes),
         "n_directional": len(directional), "n_correct": len(correct),
         "verdict": verdict}, indent=1), encoding="utf-8")
    print("wrote", dest)


if __name__ == "__main__":
    main()
