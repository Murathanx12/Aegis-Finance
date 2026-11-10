"""What would revision_flow_v0's member list be TODAY? Read-only; writes one new file.

    python -m scripts.revision_flow_refresh --out <new file> [--asof YYYY-MM-DD]

The live sleeve mirrors `revision_flow_v0` (book cb8d492bb8bf9ade), frozen ONCE on
2026-09-25 by `scripts.revision_flow_sweep --freeze-books`. Nothing re-selects it:
`sim_run.u_plan` rewrites `decisions/pc_plan/revision_flow_members.json` every cycle
with a fresh `written_utc` over the same twenty names. On survivor-free CRSP
2000-2024 an un-refreshed top-20 net-raises list keeps about half its month-1 edge
in month 2 and little by month 3-4 (night-backtests decay table), so the frozen
list is, by that history, the weaker half of the signal.

This job re-runs the SAME rule the book was frozen with
(`revision_flow.select_members`: net_raises x n_firms over the 90 days strictly
before `asof`, >= 3 firms acting, among xs_ranker-eligible names on the latest bars
date, top 20) and prints overlap / in / out against the live members file. It
freezes nothing, edits no book, touches no contract, and REFUSES to write into the
pc_plan folder or over an existing file. A refresh that the owner adopts is a NEW
book frozen through `revision_flow_sweep --freeze-books` (attended), plus the
config book id and the hack2_v2 contract copy -- see the S65 leak-followup report.

Eligibility is computed on the last ~500 calendar days of bars, enough for every
column `xs_ranker.mark_eligible` reads (63-session windows, 126 sessions seen); the
stitched-ticker split (`load_bars(split_stitched=True)`) is not applied, which can
only matter for a ticker reused by a new company inside that window.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import config as _cfg                         # noqa: E402
from backend.services import revision_flow as RF           # noqa: E402
from backend.services import xs_ranker as XR               # noqa: E402

REVISIONS_PATH = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
MEMBERS_PATH = Path(_cfg.OPTIMUS_LEDGER_DIR) / "decisions" / "pc_plan" / "revision_flow_members.json"
K, MIN_FIRMS, LOOKBACK_DAYS = 20, 3, 500


def eligible_on_last_date(paths: list[Path], symbols: set, *,
                          until: date | None = None) -> tuple[pd.Timestamp, set]:
    frames = []
    for p in paths:
        last = pd.read_parquet(p, columns=["date"])["date"].max()
        if until is not None:
            last = min(pd.Timestamp(last), pd.Timestamp(until))
        cut = pd.Timestamp(last) - timedelta(days=LOOKBACK_DAYS)
        frames.append(pd.read_parquet(p, filters=[("date", ">=", cut),
                                                  ("date", "<=", pd.Timestamp(last))]))
    b = pd.concat(frames, ignore_index=True)
    b["symbol"] = b["symbol"].astype(str)
    b = b[b["symbol"].str.upper().isin(symbols | {"SPY"})]
    b["date"] = pd.to_datetime(b["date"])
    b = b.drop_duplicates(subset=["symbol", "date"], keep="first")
    b = b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    f = XR.mark_eligible(XR.build_features(b))
    d = f["date"].max()
    day = f[(f["date"] == d) & f["eligible"]]
    return d, set(day["symbol"].str.upper())


def refresh(*, asof: date, members_path: Path = MEMBERS_PATH,
            bars_until: date | None = None) -> dict:
    rev = pd.read_parquet(REVISIONS_PATH)
    covered = set(rev["ticker"].astype(str).str.upper())
    bars_date, elig = eligible_on_last_date(XR.survivorship_free_paths(), covered,
                                            until=bars_until)
    flow = RF.compute(rev, asof=pd.Timestamp(asof))
    top = RF.select_members(flow, elig, k=K, min_firms=MIN_FIRMS)
    live = json.loads(Path(members_path).read_text(encoding="utf-8")) if Path(members_path).is_file() else {}
    frozen = sorted(live.get("members") or [])
    new = list(top.index)
    rows = [{"ticker": t, "rule_score": int(s), "net_raises": int(flow.loc[t, "net_raises"]),
             "n_firms": int(flow.loc[t, "n_firms"]),
             "median_target_change": float(flow.loc[t, "median_target_change"]),
             "in_frozen_list": t in frozen} for t, s in top.items()]
    frozen_now = []
    for t in frozen:
        r = {"ticker": t, "eligible_today": t in elig}
        if t in flow.index:
            r.update(net_raises=int(flow.loc[t, "net_raises"]), n_firms=int(flow.loc[t, "n_firms"]),
                     rule_score=int(flow.loc[t, "net_raises"] * flow.loc[t, "n_firms"]))
        else:
            r["rule_score"] = None
        frozen_now.append(r)
    return {
        "receipt": "revision_flow_refresh", "licence": "PRODUCT_EXPERIMENT",
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": asof.isoformat(), "bars_date": str(bars_date.date()),
        "revisions_last_event": str(pd.to_datetime(rev["event_date"]).max()),
        "revisions_rows": int(len(rev)), "eligible_covered_names": len(elig),
        "rule": f"top {K} by net_raises x n_firms, >= {MIN_FIRMS} firms, 90d strictly before asof",
        "frozen_members_file": str(members_path), "frozen_book_id": live.get("book_id"),
        "frozen_written_utc": live.get("written_utc"),
        "overlap": len(set(new) & set(frozen)), "n_new": len(new), "n_frozen": len(frozen),
        "names_in": sorted(set(new) - set(frozen)), "names_out": sorted(set(frozen) - set(new)),
        "refreshed": rows, "frozen_members_today": frozen_now,
        "not_done": "no book frozen, no contract or config touched, live members file not written",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="a NEW file; refused if it exists")
    ap.add_argument("--asof", default=None, help="default: today (as the v0 freeze did)")
    ap.add_argument("--bars-until", default=None,
                    help="cap the bars date (reproduce a past freeze, e.g. 2026-09-21)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if out.exists():
        print(f"REFUSED: {out} exists; this job never overwrites", file=sys.stderr)
        return 2
    if out.parent == MEMBERS_PATH.parent.resolve():
        print(f"REFUSED: {out.parent} is the live pc_plan folder", file=sys.stderr)
        return 2
    asof = date.fromisoformat(a.asof) if a.asof else date.today()
    res = refresh(asof=asof, bars_until=(date.fromisoformat(a.bars_until)
                                         if a.bars_until else None))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(out)
    print(f"bars {res['bars_date']} asof {res['asof']}: overlap {res['overlap']}/{res['n_new']}; "
          f"in {res['names_in']}; out {res['names_out']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
