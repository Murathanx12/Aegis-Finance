"""Sticky twin: the v1 (month-level) vs v2 (per-draw) turnover check, rule by rule (2026-10-07).

    python -m scripts.sticky_v2_compare --v2-run STK_2026-10-07_v2_1

Reads two finished boards, writes one receipt; scores nothing:
- v1: `twin_board_STK_2026-10-07_2.jsonl` with the rows of its supplement `STK_2026-10-07_3`
  (the two `inv_amihud` rules) laid over it, as `board_supersessions.json` reads it;
- v2: the `--v2-run` board (`hyp_twin_board --twin sticky --sticky-check v2`), whose rows carry
  BOTH checks (`sticky_turnover_check` = v2, `sticky_turnover_check_v1` = v1 on the aggregate).

Prints per rule the v1 and v2 gaps and any verdict change, checks that every rule OK on both
boards has the SAME twin series (the construction did not change), and the headline: rules at
sticky fair-twin t >= 2 on v2, of those with pure selection t >= 2, of those with net-minus-market
t >= 2 in validation, with by-year and leave-one-year-out for any positive; plus the stricter
conjunction (selection t >= 2 on the basket twin `FT_2026-10-07_1` + supplement `FT_2026-10-07_2`
as well). Receipt: `hyp_lab/sticky_v2_compare_<v2 run>.json` (written once).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.hyp_twin_board import t_of  # noqa: E402
from scripts.hyp_investable import OUT, _now, _write  # noqa: E402

V1_RUN, V1_SUPP = "STK_2026-10-07_2", "STK_2026-10-07_3"
BASKET_RUN, BASKET_SUPP = "FT_2026-10-07_1", "FT_2026-10-07_2"
SERIES_COLS = ("twin_gross", "twin_cost", "twin_turnover", "twin_full_rt", "fair_twin_net", "pure_selection")


def board(run: str, supp: str | None = None) -> dict:
    rows = {}
    for r in (run, supp):
        if not r:
            continue
        for ln in (OUT / f"twin_board_{r}.jsonl").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                x = json.loads(ln)
                if r == supp and x.get("status") != "OK":
                    continue                      # a refused supplement row leaves the full row standing
                x["_run"] = r
                rows[x["rule"]] = x
    return rows


def _gap(r: dict, key: str):
    return (r.get(key) or {}).get("median_abs_gap")


def _ok(r: dict | None) -> bool:
    return bool(r) and r.get("status") == "OK"


def compare(v2_run: str) -> dict:
    v1, v2 = board(V1_RUN, V1_SUPP), board(v2_run)
    bk = board(BASKET_RUN, BASKET_SUPP)
    per, recon_max, recon_n, t_mismatch = [], 0.0, 0, []
    for rule in sorted(set(v1) | set(v2)):
        a, b = v1.get(rule), v2.get(rule)
        chg = None
        if a and b and _ok(a) != _ok(b):
            chg = "OK->REFUSED" if _ok(a) else "REFUSED->OK"
        row = {"rule": rule, "v1_status": (a or {}).get("status", "ABSENT")[:120],
               "v2_status": (b or {}).get("status", "ABSENT")[:120], "verdict_change": chg,
               "v1_gap_on_v1_board": _gap(a or {}, "sticky_turnover_check"),
               "v1_gap_recomputed_on_v2_board": _gap(b or {}, "sticky_turnover_check_v1"),
               "v2_gap": _gap(b or {}, "sticky_turnover_check"),
               "v1_months_excluded_share": None, "v2_pairs_excluded_share":
                   ((b or {}).get("sticky_turnover_check") or {}).get("share_pairs_excluded")}
        c1 = (b or {}).get("sticky_turnover_check_v1") or {}
        if c1.get("n_months") is not None:
            tot = c1["n_months"] + c1.get("n_months_excluded_death_or_collision", 0)
            row["v1_months_excluded_share"] = round(c1.get("n_months_excluded_death_or_collision", 0) / tot, 4) if tot else None
        if _ok(b):
            row.update(fair_t=t_of(b, "fair_twin_net"), selection_t=t_of(b, "pure_selection"),
                       market_validate_t=t_of(b, "net_minus_market", "validate"))
        if _ok(a) and _ok(b):
            pa = OUT / f"fair_twin_series_{a['_run']}" / f"{rule}.parquet"
            pb = OUT / f"fair_twin_series_{v2_run}" / f"{rule}.parquet"
            if pa.exists() and pb.exists():
                A, B = pd.read_parquet(pa), pd.read_parquet(pb)
                if not A.index.equals(B.index):
                    t_mismatch.append(f"{rule}: series dates differ")
                else:
                    d = max(float(np.nanmax(np.abs(A[c].to_numpy(float) - B[c].to_numpy(float)))) for c in SERIES_COLS)
                    recon_max, recon_n = max(recon_max, d), recon_n + 1
            for k in ("fair_twin_net", "pure_selection"):
                if abs(t_of(a, k) - t_of(b, k)) > 1e-9:
                    t_mismatch.append(f"{rule}: {k} t {t_of(a, k)} vs {t_of(b, k)}")
        per.append(row)
    ok2 = [r for r in v2.values() if _ok(r)]
    fair = sorted(r["rule"] for r in ok2 if t_of(r, "fair_twin_net") >= 2)
    fair_sel = sorted(r for r in fair if t_of(v2[r], "pure_selection") >= 2)
    fair_sel_mkt = sorted(r for r in fair_sel if t_of(v2[r], "net_minus_market", "validate") >= 2)
    both_twins = sorted(r for r in fair_sel if _ok(bk.get(r)) and t_of(bk[r], "pure_selection") >= 2)
    both_mkt = sorted(r for r in both_twins if t_of(v2[r], "net_minus_market", "validate") >= 2)
    ok1 = [r for r in v1.values() if _ok(r)]
    v1_fair = sorted(r["rule"] for r in ok1 if t_of(r, "fair_twin_net") >= 2)
    v1_fair_sel = sorted(r for r in v1_fair if t_of(v1[r], "pure_selection") >= 2)
    v1_fair_sel_mkt = sorted(r for r in v1_fair_sel if t_of(v1[r], "net_minus_market", "validate") >= 2)

    def detail(rule: str) -> dict:
        r = v2[rule]
        out = {}
        for k in ("fair_twin_net", "net_minus_market", "pure_selection"):
            c = r.get(k) or {}
            out[k] = {w: {"mean_monthly": (c.get(w) or {}).get("mean_monthly"), "t": (c.get(w) or {}).get("t_blocks")}
                      for w in ("full", "design", "validate", "late", "design_validate") if c.get(w)}
            if "by_hold_year" in c:
                out[k]["by_hold_year"] = c["by_hold_year"]
                out[k]["loo_worst"] = c.get("loo_worst")
        return out

    changes = [r for r in per if r["verdict_change"]]
    v1g = [r["v1_months_excluded_share"] for r in per if r["v1_months_excluded_share"] is not None]
    v2g = [r["v2_pairs_excluded_share"] for r in per if r["v2_pairs_excluded_share"] is not None]
    head = {"v2_n_ok": len(ok2), "v2_n_refused": sum(1 for r in v2.values() if not _ok(r)),
            "v2_fair_twin_t_ge_2": len(fair), "v2_fair_and_selection_t_ge_2": len(fair_sel),
            "v2_fair_and_selection_and_market_validate_t_ge_2": fair_sel_mkt,
            "v2_stricter_selection_on_both_twins": len(both_twins),
            "v2_stricter_and_market_validate": both_mkt,
            "v1_n_ok": len(ok1), "v1_fair_twin_t_ge_2": len(v1_fair), "v1_fair_and_selection_t_ge_2": len(v1_fair_sel),
            "v1_fair_and_selection_and_market_validate_t_ge_2": v1_fair_sel_mkt,
            "verdict_changes": {"OK->REFUSED": sorted(r["rule"] for r in changes if r["verdict_change"] == "OK->REFUSED"),
                                "REFUSED->OK": sorted(r["rule"] for r in changes if r["verdict_change"] == "REFUSED->OK")},
            "median_share_excluded": {"v1_months": float(np.median(v1g)) if v1g else None,
                                      "v2_draw_month_pairs": float(np.median(v2g)) if v2g else None},
            "median_gap": {"v1": float(np.nanmedian([r["v1_gap_recomputed_on_v2_board"] for r in per
                                                     if r["v1_gap_recomputed_on_v2_board"] is not None])),
                           "v2": float(np.nanmedian([r["v2_gap"] for r in per if r["v2_gap"] is not None]))}}
    sentence = (f"Sticky twin, per-draw check v2 ({v2_run}, 301 rules): {head['v2_n_ok']} OK, {head['v2_n_refused']} "
                f"refused (v1: {head['v1_n_ok']} OK); {len(fair)} at fair-twin t >= 2, {len(fair_sel)} of them with pure "
                f"selection t >= 2, {len(fair_sel_mkt)} of those with net-minus-market t >= 2 in validation"
                + (f" ({', '.join(fair_sel_mkt)})" if fair_sel_mkt else "")
                + f"; selection t >= 2 on both twins: {len(both_twins)}, of which {len(both_mkt)} beat the market in "
                  f"validation. RESULT IMPROVEMENT: NONE unless that last number is a survivor.")
    return {"schema": "hyp_lab/sticky_v2_compare/1", "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT",
            "v1_board": [V1_RUN, V1_SUPP], "v2_board": v2_run, "basket_board": [BASKET_RUN, BASKET_SUPP],
            "construction_reconciliation": {"rules_ok_on_both_with_series": recon_n,
                                            "max_abs_diff_series_cols": recon_max, "cols": list(SERIES_COLS),
                                            "t_mismatches": t_mismatch},
            "headline": head, "scoreboard_sentence": sentence,
            "positives_detail": {r: detail(r) for r in sorted(set(fair_sel_mkt) | set(both_mkt))},
            "per_rule": per, "llm_spend_usd": 0.0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--v2-run", required=True)
    a = ap.parse_args(argv)
    out = OUT / f"sticky_v2_compare_{a.v2_run}.json"
    if out.exists():
        print(f"REFUSED: {out.name} exists (written once)")
        return 2
    if not (OUT / f"twin_board_SUMMARY_{a.v2_run}.json").exists():
        print(f"REFUSED: {a.v2_run} has no summary: the board did not finish")
        return 2
    body = compare(a.v2_run)
    _write(out, body)
    print(body["scoreboard_sentence"])
    print(json.dumps(body["headline"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
