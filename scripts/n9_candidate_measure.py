"""Measure N9's bought candidates LOCALLY, before anyone buys candidate 3,051.

    python -m scripts.n9_candidate_measure            # every CANDIDATE row
    python -m scripts.n9_candidate_measure --limit 200

2026-09-20. N9 bought 3,050 candidate precursors from DeepSeek ($1.67) and
measured none of them. Each row carries an `affected_precursor` (the rule that
is supposed to precede an exceptional move) and an `unaffected_precursor`
(the author's own placebo arm). Both are rules over the transferable state
vocabulary, so both can be evaluated on the held panel at zero cost.

TWO READS PER CANDIDATE, BECAUSE ONE WOULD BE A MEMORY
=====================================================
* ORIGIN read: the rule on the security it was mined from, with the origin
  move's own window EXCLUDED (the model was shown that move; a rule that only
  re-finds it has learned nothing). This is an IN-SAMPLE SCREEN and the
  receipt says so.
* FOREIGN read: the rule with its `security ==` clause stripped, on the five
  held securities it was NOT mined from. This is the CLAUDE.md test -- "tested
  on foreign slices with its parent barred" -- and it is the read that counts.

THE NULL is a circular date-shift of the firing mask (shifts drawn outside
+-63 sessions), which keeps the rule's own clustering and asks whether the
DATES it fires on matter. p is the share of shifts whose mean forward return is
at least as favourable (in the tail's direction) as the observed one. The
family is screened with BH-FDR (canon section 63: SCREEN = BH-FDR), and the
count of survivors is reported BESIDE the count expected by chance.

Nothing here enters the library, orders, or promotes. Stage: screen.
LICENCE: PRODUCT_EXPERIMENT.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "N9_candidate_measure"
LICENCE = "PRODUCT_EXPERIMENT"
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")
SEED = 20260920
N_SHIFTS = 400
MIN_FIRES = 10
EXCLUDE_ORIGIN_SESSIONS = 63
NULL_MIN_SHIFT = 63

OPS = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne"}


def _mask(spec, df, *, strip_security: bool):
    """A boolean Series for one rule over a state frame. Vectorised twin of
    `autopsy.compile_precursor` -- same grammar (all / any / not / clause)."""
    if isinstance(spec, dict):
        if "all" in spec:
            parts = [_mask(s, df, strip_security=strip_security) for s in spec["all"]]
            parts = [p for p in parts if p is not None]
            if not parts:
                return None
            out = parts[0]
            for p in parts[1:]:
                out = out & p
            return out
        if "any" in spec:
            parts = [_mask(s, df, strip_security=strip_security) for s in spec["any"]]
            parts = [p for p in parts if p is not None]
            if not parts:
                return None
            out = parts[0]
            for p in parts[1:]:
                out = out | p
            return out
        if "not" in spec:
            inner = _mask(spec["not"], df, strip_security=strip_security)
            return None if inner is None else ~inner
        feat, op, val = spec.get("feature"), spec.get("op"), spec.get("value")
        if feat == "security":
            if strip_security:
                return None                         # clause dropped on purpose
            col = df["security"]
            if op == "==":
                return col == val
            if op == "!=":
                return col != val
            if op == "in":
                return col.isin(list(val))
            if op == "not_in":
                return ~col.isin(list(val))
            raise ValueError(f"bad security op {op!r}")
        if feat not in df.columns:
            raise KeyError(feat)
        col = df[feat]
        if op in OPS:
            return getattr(col, OPS[op])(float(val)) & col.notna()
        if op == "in":
            return col.isin([float(v) for v in val])
        if op == "not_in":
            return ~col.isin([float(v) for v in val]) & col.notna()
        raise ValueError(f"bad op {op!r}")
    raise ValueError("spec is not a dict")


def _null_p(fwd, fires, observed, sign, rng):
    """Share of circular shifts whose mean is at least as favourable."""
    import numpy as np
    n = len(fwd)
    ok = np.isfinite(fwd)
    at_least = 0
    used = 0
    for _ in range(N_SHIFTS):
        k = int(rng.integers(NULL_MIN_SHIFT, n - NULL_MIN_SHIFT))
        m = np.roll(fires, k) & ok
        if m.sum() < MIN_FIRES:
            continue
        used += 1
        mu = float(fwd[m].mean())
        if sign * mu >= sign * observed:
            at_least += 1
    return ((at_least + 1) / (used + 1)) if used else None, used


def measure_one(cand, frames, rng):
    import numpy as np
    move = cand.get("move") or {}
    if not isinstance(move, dict):
        move = {}
    origin = move.get("security")
    h = int(move.get("horizon_sessions") or 20)
    tail = move.get("tail")
    sign = 1.0 if tail == "top" else -1.0 if tail == "bottom" else 0.0
    spec = cand.get("affected_precursor")
    placebo = cand.get("unaffected_precursor")
    out = {"candidate_id": cand.get("candidate_id"), "origin": origin,
           "horizon": h, "tail": tail, "written_utc": cand.get("written_utc")}
    if not isinstance(spec, dict) or sign == 0.0 or origin not in frames:
        out["refused"] = "RULE_OR_MOVE_UNREADABLE"
        return out
    col = f"fwd_{h}"
    # ---- ORIGIN read, origin move excluded ---------------------------------
    df = frames[origin]
    try:
        m = _mask(spec, df, strip_security=False)
        pm = _mask(placebo, df, strip_security=False) if isinstance(placebo, dict) else None
    except (KeyError, ValueError) as exc:
        out["refused"] = f"RULE_UNEVALUABLE: {type(exc).__name__} {exc}"
        return out
    if m is None:
        out["refused"] = "RULE_EMPTY"
        return out
    fires = m.to_numpy(dtype=bool)
    fwd = df[col].to_numpy(dtype="float64")
    d0 = str(move.get("date") or "")[:10]
    excl = 0
    if d0:
        pos = int(np.searchsorted(df.index.values.astype("datetime64[ns]"),
                                  np.datetime64(d0)))
        lo = max(0, pos - EXCLUDE_ORIGIN_SESSIONS)
        hi = min(len(df), pos + EXCLUDE_ORIGIN_SESSIONS)
        excl = int(fires[lo:hi].sum())
        fires[lo:hi] = False
    ok = np.isfinite(fwd)
    fm = fires & ok
    base = float(fwd[ok].mean())
    row = {"n_fires": int(fm.sum()), "origin_window_fires_excluded": excl,
           "fires_share_of_days": round(float(fires.mean()), 4)}
    if fm.sum() >= MIN_FIRES:
        mu = float(fwd[fm].mean())
        p, used = _null_p(fwd, fires, mu, sign, rng)
        row.update({"mean_fwd_pct": round(mu, 3), "base_mean_fwd_pct": round(base, 3),
                    "excess_in_tail_direction_pct": round(sign * (mu - base), 3),
                    "hit_rate_tail_direction": round(float((sign * fwd[fm] > 0).mean()), 3),
                    "null_p": (round(p, 4) if p is not None else None),
                    "null_shifts_used": used})
        if pm is not None:
            pf = pm.to_numpy(dtype=bool) & ok
            row["placebo_n_fires"] = int(pf.sum())
            row["placebo_mean_fwd_pct"] = (round(float(fwd[pf].mean()), 3)
                                           if pf.sum() >= MIN_FIRES else None)
    else:
        row["verdict"] = "TOO_FEW_FIRES"
    out["origin_read"] = row
    # ---- FOREIGN read: security clause stripped, five other securities ------
    parts, fwds = [], []
    for tkr, fdf in frames.items():
        if tkr == origin:
            continue
        try:
            fm2 = _mask(spec, fdf, strip_security=True)
        except (KeyError, ValueError):
            fm2 = None
        if fm2 is None:
            continue
        parts.append(fm2.to_numpy(dtype=bool))
        fwds.append(fdf[col].to_numpy(dtype="float64"))
    frow = {"securities": [t for t in frames if t != origin]}
    if parts:
        fires_f = np.concatenate(parts)
        fwd_f = np.concatenate(fwds)
        okf = np.isfinite(fwd_f)
        fmf = fires_f & okf
        frow["n_fires"] = int(fmf.sum())
        frow["fires_share_of_days"] = round(float(fires_f.mean()), 4)
        if fmf.sum() >= MIN_FIRES:
            mu = float(fwd_f[fmf].mean())
            basef = float(fwd_f[okf].mean())
            p, used = _null_p(fwd_f, fires_f, mu, sign, rng)
            frow.update({"mean_fwd_pct": round(mu, 3), "base_mean_fwd_pct": round(basef, 3),
                         "excess_in_tail_direction_pct": round(sign * (mu - basef), 3),
                         "hit_rate_tail_direction": round(float((sign * fwd_f[fmf] > 0).mean()), 3),
                         "null_p": (round(p, 4) if p is not None else None),
                         "null_shifts_used": used})
        else:
            frow["verdict"] = "TOO_FEW_FIRES"
    else:
        frow["verdict"] = "RULE_HAS_ONLY_A_SECURITY_CLAUSE"
    out["foreign_read"] = frow
    return out


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg: how many of the sorted p's pass at level q."""
    ps = sorted(p for p in pvals if p is not None)
    n = len(ps)
    k = 0
    for i, p in enumerate(ps, start=1):
        if p <= q * i / n:
            k = i
    return k, n


def main() -> int:
    import numpy as np
    from scripts import night_n9_library_autopsy as N9
    from backend.config import OPTIMUS_LEDGER_DIR

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", default="2003-01-01")
    args = ap.parse_args()
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    gym = OPTIMUS_LEDGER_DIR / "research_gym"
    cpath = gym / "library_candidates.jsonl"
    cands = []
    for line in cpath.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("status") == "CANDIDATE":
            cands.append(r)
    if args.limit:
        cands = cands[:args.limit]
    end = datetime.now().strftime("%Y-%m-%d")
    vix = N9.load_vix(args.start, end)
    frames = {}
    for tkr in N9.HELD_SECURITIES:
        px = N9.load_bars(tkr, args.start, end)
        frames[tkr] = N9.build_states(px, vix, security=tkr)
    rows = []
    for i, c in enumerate(cands):
        rows.append(measure_one(c, frames, rng))
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(cands)} measured ({time.time() - t0:.0f}s)", flush=True)
    out_dir = OPTIMUS_LEDGER_DIR / f"night_factory_{RUN_DATE}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "N9_candidate_measure_rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _summ(key):
        reads = [r.get(key) or {} for r in rows if not r.get("refused")]
        measured = [x for x in reads if x.get("null_p") is not None]
        ps = [x["null_p"] for x in measured]
        k, n = bh_fdr(ps, 0.10)
        raw05 = sum(1 for p in ps if p <= 0.05)
        exc = [x["excess_in_tail_direction_pct"] for x in measured]
        return {"n_reads": len(reads), "n_measured": len(measured),
                "n_too_few_fires": sum(1 for x in reads if x.get("verdict") == "TOO_FEW_FIRES"),
                "raw_p_le_0_05": raw05, "expected_by_chance_at_0_05": round(0.05 * n, 1),
                "bh_fdr_q10_survivors": k, "bh_family_n": n,
                "median_excess_in_tail_direction_pct": (round(float(np.median(exc)), 3) if exc else None),
                "share_excess_positive": (round(float(np.mean([e > 0 for e in exc])), 3) if exc else None)}

    receipt = {
        "job": JOB, "licence": LICENCE, "stage": "screen", "llm_spend_usd": 0.0,
        "run_date": RUN_DATE,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidates_file": str(cpath), "n_candidates": len(cands),
        "n_refused": sum(1 for r in rows if r.get("refused")),
        "refusals": {},
        "panel": {"securities": list(N9.HELD_SECURITIES), "start": args.start, "end": end,
                  "sessions": {t: int(len(f)) for t, f in frames.items()}},
        "construction": {"seed": SEED,
                         "null": (f"circular date-shift of the firing mask, {N_SHIFTS} shifts, "
                                  f"|shift| >= {NULL_MIN_SHIFT} sessions"),
                         "min_fires": MIN_FIRES,
                         "origin_window_excluded_sessions": EXCLUDE_ORIGIN_SESSIONS,
                         "screen": "BH-FDR q=0.10 over the family (canon section 63)",
                         "horizon": "each candidate's own move horizon (20 or 60 sessions), gross of costs"},
        "ORIGIN_read_IN_SAMPLE_SCREEN": _summ("origin_read"),
        "FOREIGN_read_parent_barred": _summ("foreign_read"),
        "rows": str(rows_path),
        "elapsed_s": round(time.time() - t0, 1),
        "read_me_first": ("The ORIGIN read is in-sample by construction (the rule was written while "
                          "looking at a move on that security); only the FOREIGN read can promote "
                          "anything, and even that is a SCREEN, not a claim. Survivors go to the "
                          "registered admission path, never straight to a book."),
    }
    for r in rows:
        if r.get("refused"):
            k = r["refused"].split(":")[0]
            receipt["refusals"][k] = receipt["refusals"].get(k, 0) + 1
    rp = out_dir / "N9_candidate_measure_run01.json"
    rp.write_text(json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("n_candidates", "n_refused", "refusals",
                                              "ORIGIN_read_IN_SAMPLE_SCREEN",
                                              "FOREIGN_read_parent_barred", "elapsed_s")}, indent=1))
    print("receipt:", rp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
