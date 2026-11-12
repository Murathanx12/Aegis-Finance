"""Grade the `source:*` forecasts already in the ledger (CH-12 / CH-35). READ-ONLY.

    python -m scripts.source_picks_grade --data-root <optimus dir> --out <dir>

Reads the forecast ledger ONLY through `backend.services.forecast_ledger`
(`logical_lines`, streamed; the live file is ~120 MB and rewritten in place) and,
optionally, the stored Dow Jones article titles (`--corpus`, url + title only).
Writes ONE receipt, `source_picks_grade_<run_id>.json`, into `--out`, which must
lie outside `--data-root`. Never writes into the data folder; prints the file
count of the data root (top level) and of its `sources/` before and after.

Grading uses the ledger's OWN resolved outcomes (`outcome` 1 = the name beat SPY
over the horizon, as resolved by belief_state), so no bars are re-read.

Per `source:*` specialist and horizon (1/5/20): n rows, n resolved, distinct
tickers, distinct DATE BLOCKS (decision_date), hit rate (outcome agrees with the
stated direction) beside the stated confidence (0.60 = max(p, 1-p)), Brier vs
0.25 and vs the pooled base rate, and the declared primary statistic:

    x_i = hit_i - control_i,  control_i = b if the row says up else 1 - b,

`b` = the pooled share of resolved `source:*` rows at that horizon whose name
beat SPY (a random-direction call with the same up/down mix scores 0 on x). Its
mean has a CR1 SE clustered by date block AND by ticker; the coarser (larger)
SE decides; t = mean / SE; MDE = 2.8 x SE (the source_scorecard convention).

Verdict (declared before the run; headline horizon h=5):
  CANNOT_DISTINGUISH      resolved < 30, or date blocks < 10, or neither below;
  SUPPORTED_IN_SCOPE      t >= 2.0 on the coarser SE;
  NOT_SUPPORTED_IN_SCOPE  the stated edge is rejected: hit + 2 SE < 0.60 AND
                          MDE <= 0.10 (the test could see the claimed +0.10).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

HORIZONS: tuple[int, ...] = (1, 5, 20)
HEADLINE_H = 5
MIN_RESOLVED = 30
MIN_BLOCKS = 10
T_SUPPORT = 2.0
MDE_MULT = 2.8
STATED_CONF = 0.60
NVIDIA_CASE_TICKERS = ("NVDA", "AVGO", "CRWV")
_DJ_HOST = re.compile(r"^https?://([a-z0-9-]+\.)*(wsj|barrons|marketwatch)\.com/", re.I)
_SPEC_RE = re.compile(r'"specialist":\s*"(source:[^"]*)"')


class GradeRefused(RuntimeError):
    """A missing or unsafe input: the CLI exits 2, never 0."""


def _url_path(u: str) -> str:
    return re.sub(r"[?#].*$", "", str(u or "")).strip().lower()


def _names(d: Path) -> set[str]:
    try:
        return {x.name for x in d.iterdir()}
    except OSError:
        return set()


def _snapshot(data_root: Path) -> dict[str, set[str]]:
    return {"data_root_top": _names(data_root), "sources": _names(data_root / "sources")}


def load_source_rows(ledger: Path) -> tuple[list[dict], Counter]:
    """(parsed source:* rows, an INDEPENDENT regex count per specialist over every
    logical line) -- the two must reconcile."""
    from backend.services import forecast_ledger as FL
    if not FL.exists(ledger):
        raise GradeRefused(f"NO_LEDGER: {ledger} does not exist")
    rows: list[dict] = []
    for line in FL.logical_lines(ledger, contains='"source:'):
        r = json.loads(line)
        sp = str(r.get("specialist") or "")
        if not sp.startswith("source:"):
            continue
        iu = r.get("inputs_used") or {}
        rows.append({
            "prediction_id": r.get("prediction_id"), "specialist": sp,
            "ticker": str(r.get("ticker") or "").upper(),
            "h": int(r.get("horizon_days") or 0), "p": float(r.get("probability")),
            "made_at": str(r.get("made_at") or ""),
            "decision_date": str(r.get("decision_date") or str(r.get("made_at") or "")[:10]),
            "claim_utc": str(iu.get("claim_utc") or ""),
            "claim_hash": iu.get("claim_hash"),
            "url": str(iu.get("post_url") or r.get("next_observable") or ""),
            "thesis": str(r.get("thesis") or ""),
            "outcome": r.get("outcome"), "void": r.get("void_reason"),
            "resolves_after": r.get("resolves_after"),
            "observable": r.get("observable")})
    indep: Counter = Counter()
    for line in FL.logical_lines(ledger):
        m = _SPEC_RE.search(line)
        if m:
            indep[m.group(1)] += 1
    return rows, indep


def load_titles(corpus: Optional[Path]) -> dict[str, str]:
    """url path -> stored title (wsj / barrons / marketwatch only)."""
    if corpus is None:
        return {}
    out: dict[str, str] = {}
    for pub in ("barrons", "wsj", "marketwatch"):
        for p in glob.glob(str(corpus / pub / "*" / "*.json")):
            try:
                d = json.loads(Path(p).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            u = _url_path(d.get("url") or "")
            if u and d.get("title"):
                out.setdefault(u, str(d["title"]))
    return out


def classify(rows: list[dict], titles: dict[str, str]) -> None:
    from backend.services import dowjones_claims as DC
    for r in rows:
        col = r["specialist"].removeprefix("source:")
        if not _DJ_HOST.search(r["url"]):
            # a social / registry source (source:x:<handle>), not a Dow Jones page
            r.update(page_type="not_a_dowjones_page", page_class="NOT_A_PAGE", title_known=False)
            continue
        title = titles.get(_url_path(r["url"]), "")
        ptype = DC.page_type_of(r["url"], title, col)
        try:
            cls = DC.page_class(ptype)
        except DC.PageTypeRefused:
            cls = "UNCLASSIFIED"
        r.update(page_type=ptype, page_class=cls, title_known=bool(title))


def _cse(x: np.ndarray, g: list) -> Optional[float]:
    from backend.services.source_scorecard import clustered_se
    return clustered_se(x, np.asarray(g))


def _r(v: Any, nd: int = 4) -> Any:
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, nd)


def base_rates(rows: list[dict]) -> dict[int, Optional[float]]:
    out = {}
    for h in HORIZONS:
        o = [int(r["outcome"]) for r in rows if r["h"] == h and _resolved(r)]
        out[h] = (sum(o) / len(o)) if o else None
    return out


def _resolved(r: dict) -> bool:
    return r["void"] is None and r["outcome"] in (0, 1, 0.0, 1.0, True, False)


def cell(rows: list[dict], b: Optional[float]) -> dict:
    """The graded statistics of one set of rows (one specialist x horizon)."""
    res = [r for r in rows if _resolved(r)]
    out: dict[str, Any] = {
        "n": len(rows), "n_resolved": len(res), "n_void": sum(r["void"] is not None for r in rows),
        "n_open": sum(r["void"] is None and not _resolved(r) for r in rows),
        "tickers": len({r["ticker"] for r in rows}),
        "date_blocks": len({r["decision_date"] for r in rows}),
        "date_blocks_resolved": len({r["decision_date"] for r in res}),
        "tickers_resolved": len({r["ticker"] for r in res}),
        "n_up": sum(r["p"] > 0.5 for r in rows), "n_down": sum(r["p"] < 0.5 for r in rows)}
    if not res or b is None:
        return out
    o = np.array([float(r["outcome"]) for r in res])
    p = np.array([r["p"] for r in res])
    up = p > 0.5
    hit = np.where(up, o, 1 - o)
    ctrl = np.where(up, b, 1 - b)
    x = hit - ctrl
    se_d = _cse(x, [r["decision_date"] for r in res])
    se_t = _cse(x, [r["ticker"] for r in res])
    ses = [s for s in (se_d, se_t) if s is not None]
    se = max(ses) if ses else None
    hse_d = _cse(hit, [r["decision_date"] for r in res])
    hse_t = _cse(hit, [r["ticker"] for r in res])
    hses = [s for s in (hse_d, hse_t) if s is not None]
    hse = max(hses) if hses else None
    brier = float(((p - o) ** 2).mean())
    out.update({
        "stated_confidence": _r(float(np.maximum(p, 1 - p).mean())),
        "hit_rate": _r(float(hit.mean())),
        "hit_rate_up": _r(float(hit[up].mean())) if up.any() else None,
        "hit_rate_down": _r(float(hit[~up].mean())) if (~up).any() else None,
        "base_rate_beats_spy": _r(b), "control_hit": _r(float(ctrl.mean())),
        "excess_hit_vs_control": _r(float(x.mean())),
        "se_date_blocks": _r(se_d), "se_ticker": _r(se_t),
        "coarser_scheme": (None if se is None else ("date" if se == se_d else "ticker")),
        "se": _r(se), "t": _r(float(x.mean()) / se) if se else None,
        "mde": _r(MDE_MULT * se) if se else None,
        "mde_reason": None if se else ("no clustered SE: fewer than 2 date blocks or 2 tickers "
                                       "among resolved rows, so no MDE exists and no verdict "
                                       "other than CANNOT_DISTINGUISH is allowed"),
        "hit_se": _r(hse),
        "brier": _r(brier), "brier_coin": 0.25,
        "brier_base_rate": _r(float(((b - o) ** 2).mean())),
        "brier_skill_vs_coin": _r(1 - brier / 0.25),
        "brier_skill_vs_base": _r(1 - brier / float(((b - o) ** 2).mean()))
        if float(((b - o) ** 2).mean()) > 0 else None})
    return out


def verdict(c: dict) -> str:
    if c.get("mde") is None:
        return "CANNOT_DISTINGUISH"
    if c["n_resolved"] < MIN_RESOLVED or c["date_blocks_resolved"] < MIN_BLOCKS:
        return "CANNOT_DISTINGUISH"
    if c["t"] is not None and c["t"] >= T_SUPPORT:
        return "SUPPORTED_IN_SCOPE"
    if (c["hit_rate"] + 2 * (c.get("hit_se") or c["se"]) < STATED_CONF
            and c["mde"] <= 0.10):
        return "NOT_SUPPORTED_IN_SCOPE"
    return "CANNOT_DISTINGUISH"


def by_month(rows: list[dict], b: Optional[float]) -> dict:
    out = {}
    for m in sorted({r["decision_date"][:7] for r in rows}):
        c = cell([r for r in rows if r["decision_date"][:7] == m], b)
        out[m] = {k: c.get(k) for k in ("n", "n_resolved", "date_blocks_resolved", "hit_rate",
                                        "excess_hit_vs_control", "brier")}
    return out


def leave_one_month_out(rows: list[dict], b: Optional[float]) -> dict:
    months = sorted({r["decision_date"][:7] for r in rows})
    vals = {}
    for m in months:
        c = cell([r for r in rows if r["decision_date"][:7] != m], b)
        vals[m] = c.get("excess_hit_vs_control")
    ok = [v for v in vals.values() if v is not None]
    return {"by_month_dropped": vals, "worst": min(ok) if ok else None}


def duplicates(rows: list[dict]) -> dict:
    k = Counter((_url_path(r["url"]), r["ticker"], r["h"]) for r in rows)
    d = {kk: v for kk, v in k.items() if v > 1}
    by_sp = Counter()
    for r in rows:
        if k[(_url_path(r["url"]), r["ticker"], r["h"])] > 1:
            by_sp[r["specialist"]] += 1
    return {"keys_with_more_than_one_row": len(d), "extra_rows": sum(v - 1 for v in d.values()),
            "rows_in_duplicated_keys_by_specialist": dict(by_sp)}


def extraction_lag(rows: list[dict]) -> dict:
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        try:
            d = (datetime.fromisoformat(r["made_at"])
                 - datetime.fromisoformat(r["claim_utc"])).total_seconds() / 86400
            k = "<1d" if d < 1 else "1-6d" if d < 7 else "7-29d" if d < 30 else ">=30d"
        except ValueError:
            k = "undated"
        out[r["specialist"]][k] += 1
    return {s: dict(c) for s, c in out.items()}


def nvidia_case(rows: list[dict], day: str) -> list[dict]:
    from backend.services import dowjones_claims as DC
    out = []
    for r in rows:
        if r["ticker"] not in NVIDIA_CASE_TICKERS or not r["made_at"].startswith(day):
            continue
        para = re.sub(r"^\[[^\]]+\]\s*", "", r["thesis"])
        d = "up" if r["p"] > 0.5 else "down"
        stance = DC.explicit_stance({"direction": d, "paraphrase": para})
        if r["page_class"] == "MENTION":
            instead = "nothing (MENTION page: no directional forecast; default ON)"
        elif r["page_class"] == "STANCE_REQUIRED":
            instead = (f"a {stance} row only with DOWJONES_STANCE_REQUIRED_ENFORCE"
                       if stance else "nothing with DOWJONES_STANCE_REQUIRED_ENFORCE "
                                      "(no explicit stance in the claim; counted)")
        else:
            instead = "the same row (PICK page)"
        out.append({"prediction_id": r["prediction_id"], "ticker": r["ticker"], "h": r["h"],
                    "specialist": r["specialist"], "made_at": r["made_at"],
                    "article_first_seen_utc": r["claim_utc"], "p": r["p"],
                    "url_path": _url_path(r["url"]), "page_type": r["page_type"],
                    "page_class": r["page_class"], "outcome": r["outcome"],
                    "resolves_after": r["resolves_after"], "paraphrase": para[:200],
                    "stance_aware_reader_would_write": instead})
    return out


def grade(rows: list[dict], indep: Counter) -> dict:
    b = base_rates(rows)
    specs = sorted({r["specialist"] for r in rows})
    per: dict[str, Any] = {}
    for sp in specs:
        rs = [r for r in rows if r["specialist"] == sp]
        hz = {}
        for h in HORIZONS:
            c = cell([r for r in rs if r["h"] == h], b[h])
            c["verdict"] = verdict(c)
            hz[str(h)] = c
        head = hz[str(HEADLINE_H)]
        hrows = [r for r in rs if r["h"] == HEADLINE_H]
        dd = sorted({r["decision_date"] for r in rs})
        cls = Counter(r["page_class"] for r in rs)
        per[sp] = {
            "n_rows": len(rs), "ledger_regex_count": indep.get(sp, 0),
            "reconciles": indep.get(sp, 0) == len(rs),
            "n_resolved": sum(_resolved(r) for r in rs),
            "tickers": len({r["ticker"] for r in rs}), "date_blocks": len(dd),
            "decision_dates": [dd[0], dd[-1]] if dd else None,
            "rows_by_page_class": dict(cls),
            "headline_horizon": HEADLINE_H, "verdict": head["verdict"],
            "scope": (f"{sp}, beats_benchmark vs SPY at h={HEADLINE_H} sessions, decision "
                      f"dates {dd[0] if dd else '-'}..{dd[-1] if dd else '-'}, "
                      f"{head['n_resolved']} resolved rows on {head['date_blocks_resolved']} "
                      f"date blocks, rows as labelled by dowjones_claims.column_of"),
            "by_horizon": hz,
            "by_month_h5": by_month(hrows, b[HEADLINE_H]),
            "leave_one_month_out_h5": leave_one_month_out(hrows, b[HEADLINE_H]),
            "h5_excluding_mention_rows": cell([r for r in hrows if r["page_class"] != "MENTION"],
                                              b[HEADLINE_H]),
            "h5_mention_rows_only": cell([r for r in hrows if r["page_class"] == "MENTION"],
                                         b[HEADLINE_H])}
    pooled = {str(h): cell([r for r in rows if r["h"] == h], b[h]) for h in HORIZONS}
    for h in HORIZONS:
        pooled[str(h)]["verdict"] = verdict(pooled[str(h)])
    return {"base_rate_beats_spy_by_h": {str(h): _r(v) for h, v in b.items()},
            "per_specialist": per, "pooled_all_source": pooled}


def run(data_root: Path, out_dir: Path, *, corpus: Optional[Path] = None,
        run_id: Optional[str] = None, nvidia_day: Optional[str] = None) -> tuple[dict, Path]:
    data_root = Path(data_root).resolve()
    out_dir = Path(out_dir).resolve()
    if not data_root.is_dir():
        raise GradeRefused(f"NO_DATA_ROOT: {data_root}")
    if out_dir == data_root or data_root in out_dir.parents:
        raise GradeRefused(f"REFUSED_OUT_INSIDE_DATA_ROOT: {out_dir}")
    ledger = data_root / "predictions.jsonl"
    before = _snapshot(data_root)
    rows, indep = load_source_rows(ledger)
    if not rows:
        raise GradeRefused(f"NO_SOURCE_ROWS: {ledger} holds no source:* rows")
    titles = load_titles(corpus)
    classify(rows, titles)
    g = grade(rows, indep)
    mention = [r for r in rows if r["page_class"] == "MENTION"]
    now = datetime.now(timezone.utc)
    rid = run_id or now.strftime("%Y%m%dT%H%M%SZ")
    day = nvidia_day or now.date().isoformat()
    after = _snapshot(data_root)
    added = {k: sorted(after[k] - before[k]) for k in after}
    ours = [n for v in added.values() for n in v if n.startswith("source_picks_grade")]
    rec = {
        "receipt": "source_picks_grade", "run_id": rid,
        "generated_utc": now.isoformat(timespec="seconds"), "llm_spend_usd": 0.0,
        "read_only": True, "ledger": str(ledger), "ledger_read_via": "forecast_ledger.logical_lines",
        "corpus_titles_joined": len(titles),
        "files_before": {k: len(v) for k, v in before.items()},
        "files_after": {k: len(v) for k, v in after.items()},
        "files_added_during_run": added,
        "files_removed_during_run": {k: sorted(before[k] - after[k]) for k in after},
        "files_unchanged": before == after,
        "wrote_into_data_root": bool(ours),
        "n_source_rows": len(rows),
        "n_source_rows_regex_count": sum(indep.values()),
        "reconciles": sum(indep.values()) == len(rows) and all(
            v["reconciles"] for v in g["per_specialist"].values()),
        "rule": {"primary": "x = hit - control, control = b (up) / 1-b (down), b pooled per h",
                 "se": "CR1, clustered by date block and by ticker; the larger decides",
                 "mde": f"{MDE_MULT} x SE", "headline_horizon": HEADLINE_H,
                 "supported": f"t >= {T_SUPPORT}",
                 "not_supported": f"hit + 2 SE < {STATED_CONF} and MDE <= 0.10",
                 "cannot_distinguish": f"otherwise, or resolved < {MIN_RESOLVED}, "
                                       f"or date blocks < {MIN_BLOCKS}"},
        "mention_rows": {"n": len(mention),
                         "by_specialist": dict(Counter(r["specialist"] for r in mention)),
                         "by_page_type": dict(Counter(r["page_type"] for r in mention)),
                         "n_title_known": sum(r["title_known"] for r in mention),
                         "exclude_rule": ("page_class(page_type_of(post_url, stored title, "
                                          "column)) == 'MENTION' (dowjones_claims)"),
                         "prediction_ids": sorted(r["prediction_id"] for r in mention)},
        "rows_by_page_class": dict(Counter(r["page_class"] for r in rows)),
        "unclassified_page_types": dict(Counter(r["page_type"] for r in rows
                                                if r["page_class"] == "UNCLASSIFIED")),
        "duplicates": duplicates(rows),
        "extraction_lag_made_minus_first_seen": extraction_lag(rows),
        **g,
        "nvidia_case_day": day,
        "nvidia_case": nvidia_case(rows, day)}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"source_picks_grade_{rid}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)
    return rec, path


def format_table(rec: dict) -> str:
    lines = [f"source_picks_grade {rec['run_id']}  rows {rec['n_source_rows']} "
             f"(regex {rec['n_source_rows_regex_count']}, reconciles {rec['reconciles']})  "
             f"MENTION rows {rec['mention_rows']['n']}  files unchanged {rec['files_unchanged']}",
             f"{'specialist':34} {'n':>5} {'res':>5} {'tk':>4} {'blk':>4} | h=5: {'hit':>6} "
             f"{'conf':>5} {'ctrl':>6} {'brier':>6} {'t':>6} {'MDE':>6}  verdict"]
    for sp, v in rec["per_specialist"].items():
        c = v["by_horizon"][str(HEADLINE_H)]
        f = lambda k: "-" if c.get(k) is None else f"{c[k]:.3f}"  # noqa: E731
        lines.append(f"{sp:34} {v['n_rows']:>5} {v['n_resolved']:>5} {v['tickers']:>4} "
                     f"{v['date_blocks']:>4} | {f('hit_rate'):>9} {f('stated_confidence'):>5} "
                     f"{f('control_hit'):>6} {f('brier'):>6} {f('t'):>6} {f('mde'):>6}  "
                     f"{v['verdict']}")
    return "\n".join(lines)


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", required=True, type=Path,
                    help="the optimus data folder holding the forecast ledger (read-only)")
    ap.add_argument("--out", required=True, type=Path, help="receipt directory (outside data root)")
    ap.add_argument("--corpus", type=Path, default=None,
                    help="news_corpus/dowjones root, for stored titles (read-only)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--nvidia-day", default=None, help="UTC day of the Nvidia case rows")
    a = ap.parse_args(list(argv) if argv is not None else None)
    try:
        rec, path = run(a.data_root, a.out, corpus=a.corpus, run_id=a.run_id,
                        nvidia_day=a.nvidia_day)
    except GradeRefused as e:
        print(f"REFUSED: {e}")
        return 2
    print(format_table(rec))
    print(f"files before {rec['files_before']} after {rec['files_after']}")
    print(f"receipt: {path}")
    if not rec["files_unchanged"]:
        print(f"NOTE: the data folder changed during the run (other writers): "
              f"added {rec['files_added_during_run']}")
    if not rec["reconciles"] or rec["wrote_into_data_root"]:
        print("RED: n does not reconcile with the ledger, or this run wrote into the data root")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
