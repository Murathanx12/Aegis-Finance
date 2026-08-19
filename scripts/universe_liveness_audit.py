"""Universe liveness audit — the EA catch, mechanized for the whole panel.

EA's death was caught by a HUMAN noticing trades vanish while quotes ghost
on. This script makes that check structural: it joins the TAQ quoted panel
(quotes per name-day) with the effective-spread panel (trades per name-day)
and runs `security_identity.quote_ghost_scan` over the result. A name whose
final sessions show quotes without trades is flagged for quarantine; the
known-dead are asserted dead (canary — exit non-zero if the scan misses a
name the identity master says is terminal inside the window).

Run after every TAQ re-pull. Offline; reads only committed artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import security_identity as SI      # noqa: E402

OPT = REPO / "backend" / "data" / "optimus"


def build_panel() -> pd.DataFrame:
    q = pd.read_csv(OPT / "taq_quoted_spreads_calibration.csv")
    # the 08-18 MMC/SQ re-pull appended YYYYMMDD rows to an ISO-dated CSV —
    # normalize both spellings rather than trusting one
    ds = q["date"].astype(str).str.replace("-", "", regex=False)
    q["date"] = pd.to_datetime(ds, format="%Y%m%d")
    t = pd.read_json(OPT / "taq_effective_spreads_v1.jsonl", lines=True)
    t["date"] = pd.to_datetime(t["date"].astype(str))
    j = q[["ticker", "date", "n_quotes"]].merge(
        t[["ticker", "date", "n_trades"]], on=["ticker", "date"],
        how="left")
    # a quoted name-day with NO trades row = zero resolved trades that day
    j["n_trades"] = j["n_trades"].fillna(0).astype(int)
    return j


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    panel = build_panel()
    last_day = panel["date"].max()
    print(f"panel: {panel['ticker'].nunique()} names × "
          f"{panel['date'].nunique()} days through {last_day.date()}")

    flags = SI.quote_ghost_scan(panel, min_ghost_days=3)
    for f in flags:
        r = SI.resolve(f["ticker"], last_day.date())
        known = (r.provenance == "CURATED" and not r.alive)
        f["identity_master"] = ("KNOWN_DEAD: " + (r.terminal_reason or "")
                                if known else "NOT IN MASTER — investigate "
                                "(rename? delisting? feed gap?)")
        print(f"  GHOST {f['ticker']}: {f['ghost_days_at_end']} quote-only "
              f"days after last trade {f['last_trade_date'][:10]} — "
              f"{f['identity_master'][:70]}")
    if not flags:
        print("  no ghosts flagged")

    # CANARY: for every curated-terminal name dying INSIDE the window, the
    # panel must be in one of exactly two honest states — GHOST-FLAGGED
    # (quote rows extend past death and the scan caught them) or CLEAN_DEAD
    # (its rows END on/before the terminal date, as EA's do after the 08-18
    # truncation). Rows past death with no flag = the scan went blind to
    # the case it was built for; exit non-zero.
    blind = []
    flagged = {f["ticker"] for f in flags}
    for tkr in panel["ticker"].unique():
        r = SI.resolve(tkr, last_day.date())
        if (r.provenance == "CURATED" and not r.alive and r.terminal_date
                and r.terminal_date >= str(panel["date"].min().date())):
            last_row = panel.loc[panel["ticker"] == tkr, "date"].max()
            if str(last_row.date()) <= r.terminal_date:
                print(f"  CLEAN_DEAD {tkr}: rows end {last_row.date()} <= "
                      f"terminal {r.terminal_date}")
            elif tkr not in flagged:
                blind.append(tkr)
    if blind:
        print(f"CANARY FAILED: {blind} carry rows past their terminal date "
              f"and were not flagged — the scan has gone blind")
        return 2

    out = {"generated_from": ["taq_quoted_spreads_calibration.csv",
                              "taq_effective_spreads_v1.jsonl"],
           "n_names": int(panel["ticker"].nunique()),
           "last_day": str(last_day.date()),
           "flags": flags, "canary": "ok"}
    p = OPT / "universe_liveness_audit.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"receipt: {p.relative_to(REPO)}  (canary ok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
