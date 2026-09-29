"""Reconcile what the PROVIDER charged against what TELEMETRY recorded.

    python -m scripts.llm_cost_audit                 # since the last snapshot
    python -m scripts.llm_cost_audit --since 2026-08-15 --balance-then 57.12
    python -m scripts.llm_cost_audit --no-network    # ledger arithmetic only

THE QUESTION THIS ANSWERS
=========================
"The IIF-1 receipt says $0.941/night and the account is losing about $3/day."
Both can be true, and on 2026-08-24 both were: they count different
populations. This script stops that being an argument by printing ONE line —

    provider_balance_delta - telemetry_total = unaccounted

— and, when the ledger can attribute it, a per-purpose breakdown of where the
telemetry half went.

WHAT IT REFUSES TO DO
=====================
* It never reports a cost for a call whose model is not in
  `config.LLM_PRICE_PER_MTOK`. Those are counted separately and the total is
  labelled a LOWER BOUND, because a None priced as 0 is how a total becomes a
  lie that sums correctly.
* It never treats a missing balance endpoint as $0 spend.
* It never pools the local ledger with production's. They are different files
  on different hosts; if only one is readable, the output says which.

READING THE OUTPUT
==================
`unaccounted > 0` means the provider charged for calls telemetry did not see —
the interesting direction, and the one that means a module is spending without
recording. `unaccounted < 0` usually means a top-up landed inside the window
(the balance went UP), which the script names rather than clamping away.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import deepseek_balance as bal          # noqa: E402
from backend.services import llm_telemetry as tel             # noqa: E402

# The recompute below re-prices every row, so an unpriced model would log once
# per CALL. The COUNT is the finding, not forty thousand identical lines; the
# models themselves are reported in `unpriced_models`.
#
# The quieting is SCOPED to the recompute call and restored after it. It used
# to be a module-level `setLevel(ERROR)` on the telemetry logger, which meant
# that merely IMPORTING this script silenced every telemetry warning (unpriced
# model, failed ledger write, unreadable lines) for the rest of the process —
# found 2026-09-29 when a test importing it emptied four telemetry tests'
# captured warnings.
import contextlib as _contextlib                              # noqa: E402
import logging as _logging                                    # noqa: E402

_TEL_LOGGER = _logging.getLogger("backend.services.llm_telemetry")


@_contextlib.contextmanager
def _quiet_telemetry():
    prev = _TEL_LOGGER.level
    _TEL_LOGGER.setLevel(_logging.ERROR)
    try:
        yield
    finally:
        _TEL_LOGGER.setLevel(prev)


def _iso_day(ts: str) -> str:
    return str(ts or "")[:10]


def ledger_totals(path: Path, since: str | None) -> dict:
    """Sum one telemetry ledger. Returns priced/unpriced split, never a blend."""
    out = {"path": str(path), "exists": path.exists(), "n_calls": 0,
           "n_priced": 0, "n_unpriced": 0, "n_amendments": 0, "usd": 0.0,
           "by_purpose": defaultdict(float), "by_day": defaultdict(float),
           "by_model": defaultdict(int), "unpriced_models": defaultdict(int),
           "tokens_in": 0, "tokens_out": 0, "cached_tokens": 0}
    if not path.exists():
        return _undefault(out)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if since and _iso_day(row.get("ts", "")) < since:
            continue
        # AMENDMENT rows are bookkeeping, not wire calls: they attach
        # prediction_ids to a call already counted, carry zero tokens and no
        # model, and pricing them is meaningless. The first version of this
        # script counted 7,083 of them as "unpriced calls" and stamped the
        # whole total a LOWER BOUND — an instrument that reported a $28 hole
        # and a fake reason for it in the same breath. Filtered by row_type,
        # the local ledger has ZERO unpriced calls.
        if str(row.get("row_type") or "call") != "call":
            out["n_amendments"] = out.get("n_amendments", 0) + 1
            continue
        out["n_calls"] += 1
        out["tokens_in"] += int(row.get("tokens_in") or 0)
        out["tokens_out"] += int(row.get("tokens_out") or 0)
        out["cached_tokens"] += int(row.get("cached_tokens") or 0)
        model = str(row.get("model") or "")
        out["by_model"][model] += 1
        cost = row.get("cost_usd")
        if cost is None:
            # Recompute rather than trust the stored None: the price table may
            # have gained the model since the row was written.
            with _quiet_telemetry():
                cost = tel.price_call(model, int(row.get("tokens_in") or 0),
                                      int(row.get("tokens_out") or 0),
                                      int(row.get("cached_tokens") or 0))
        if cost is None:
            out["n_unpriced"] += 1
            out["unpriced_models"][model] += 1
            continue
        out["n_priced"] += 1
        out["usd"] += float(cost)
        out["by_purpose"][str(row.get("purpose") or "?")] += float(cost)
        out["by_day"][_iso_day(row.get("ts", ""))] += float(cost)
    return _undefault(out)


def _undefault(d: dict) -> dict:
    for k, v in list(d.items()):
        if isinstance(v, defaultdict):
            d[k] = dict(v)
    d["usd"] = round(d["usd"], 6)
    return d


def ledger_bases() -> list[Path]:
    """The BASE path(s) the writer appends beside (before month expansion)."""
    seen, out = set(), []
    env = os.getenv(tel.LLM_TELEMETRY_PATH_ENV)
    from backend.config import DATA_DIR
    for p in ((Path(env) if env else None), tel.LLM_CALLS,
              DATA_DIR / "optimus" / "llm_calls.jsonl"):
        if p is None:
            continue
        k = str(Path(p).resolve())
        if k not in seen:
            seen.add(k)
            out.append(Path(p))
    return out


def find_ledgers() -> list[Path]:
    """Every telemetry ledger FILE this host can read. Listed, not merged.

    2026-09-29: this read only the legacy monolith `llm_calls.jsonl`, which the
    2026-09-12 rotation retired in favour of `llm_calls_<YYYY-MM>.jsonl` -- so
    the telemetry half was $0.00 on every run while the provider's balance
    moved $1.47 in one night (a cap that reads a different ledger than the
    writer, again). The file list now comes from the WRITER's own naming rule,
    `llm_telemetry.ledger_files`, so reader and writer cannot drift.
    Each base appears once (`[base]` placeholder when nothing exists, so an
    absent ledger is printed as absent rather than silently omitted).
    """
    seen, out = set(), []
    for base in ledger_bases():
        files = tel.ledger_files(base) or [base]
        for f in files:
            k = str(Path(f).resolve())
            if k not in seen:
                seen.add(k)
                out.append(Path(f))
    return out


#: When provider and telemetry differ by more than this, the audit says
#: DISAGREE by name. Absolute floor (rounding, a balance read a few calls
#: late) or a share of the provider's own delta, whichever is larger.
DISAGREE_TOLERANCE_USD = 0.05
DISAGREE_TOLERANCE_FRAC = 0.05


def agreement(provider_delta: float | None, tel_usd: float) -> dict:
    """AGREE / DISAGREE / NOT COMPUTABLE, with the tolerance that decided it."""
    if provider_delta is None:
        return {"verdict": "NOT COMPUTABLE", "tolerance_usd": None,
                "gap_usd": None}
    tol = max(DISAGREE_TOLERANCE_USD, DISAGREE_TOLERANCE_FRAC * abs(provider_delta))
    gap = round(provider_delta - tel_usd, 6)
    return {"verdict": "DISAGREE" if abs(gap) > tol else "AGREE",
            "tolerance_usd": round(tol, 6), "gap_usd": gap}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default=None,
                    help="ISO date; default = the day of the last balance "
                         "snapshot, else 7 days back")
    ap.add_argument("--balance-then", type=float, default=None,
                    help="known balance at --since, when no snapshot exists "
                         "(e.g. 57.12 as of 2026-08-15)")
    ap.add_argument("--no-network", action="store_true",
                    help="skip the provider read; ledger arithmetic only")
    ap.add_argument("--snapshot", action="store_true",
                    help="also APPEND this read to the snapshot ledger")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    snaps = bal.snapshots()
    since = a.since or (_iso_day(snaps[-1]["read_at"]) if snaps
                        else str(date.today().replace(
                            day=max(1, date.today().day - 7))))

    # ── the provider half ───────────────────────────────────────────────────
    now_bal, bal_err = None, None
    if not a.no_network:
        try:
            now_bal = (bal.snapshot("cost_audit") if a.snapshot
                       else bal.read_balance())
        except bal.BalanceUnavailable as exc:
            bal_err = str(exc)

    then = a.balance_then
    then_at = f"--balance-then {then}" if then is not None else None
    if then is None and snaps:
        prior = [s for s in snaps if _iso_day(s["read_at"]) <= since]
        if prior:
            then = float(prior[-1]["total_usd"])
            then_at = f"snapshot {prior[-1]['read_at']} ({prior[-1].get('label')})"

    provider_delta = (round(then - now_bal["total_usd"], 6)
                      if (then is not None and now_bal) else None)

    # ── the telemetry half ──────────────────────────────────────────────────
    ledgers = [ledger_totals(p, since) for p in find_ledgers()]
    readable = [x for x in ledgers if x["exists"]]
    tel_usd = round(sum(x["usd"] for x in readable), 6)
    n_unpriced = sum(x["n_unpriced"] for x in readable)

    unaccounted = (round(provider_delta - tel_usd, 6)
                   if provider_delta is not None else None)
    agree = agreement(provider_delta, tel_usd)

    report = {
        "since": since,
        "balance_now_usd": (now_bal or {}).get("total_usd"),
        "balance_then_usd": then,
        "balance_then_source": then_at,
        "balance_error": bal_err,
        "provider_delta_usd": provider_delta,
        "telemetry_total_usd": tel_usd,
        "telemetry_is_lower_bound": n_unpriced > 0,
        "n_unpriced_calls": n_unpriced,
        "unaccounted_usd": unaccounted,
        "agreement": agree["verdict"],
        "agreement_tolerance_usd": agree["tolerance_usd"],
        "ledgers": ledgers,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if a.json:
        print(json.dumps(report, indent=1, default=str))
        return 0

    print(f"LLM COST AUDIT  (since {since})")
    print("=" * 66)
    if bal_err:
        print(f"  provider balance : UNAVAILABLE — {bal_err}")
        print("                     (this is NOT $0 spend; the audit is "
              "incomplete)")
    else:
        print(f"  balance now      : ${report['balance_now_usd']}")
        print(f"  balance at start : "
              f"{'$%s' % then if then is not None else 'UNKNOWN'}"
              f"   [{then_at or 'no snapshot, no --balance-then'}]")
    print(f"  provider says     : "
          f"{'$%.4f spent' % provider_delta if provider_delta is not None else 'NOT COMPUTABLE'}")
    print(f"  telemetry says    : ${tel_usd:.4f}"
          f"{'  (LOWER BOUND: %d unpriced calls)' % n_unpriced if n_unpriced else ''}")
    if unaccounted is not None:
        verdict = ("top-up inside the window (balance rose)" if unaccounted < 0
                   else "calls the ledger never saw" if unaccounted > 0.01
                   else "reconciled")
        print(f"  UNACCOUNTED       : ${unaccounted:.4f}   <- {verdict}")
    print(f"  provider vs telemetry: {agree['verdict']}"
          + (f"  (gap ${agree['gap_usd']:.4f}, tolerance ${agree['tolerance_usd']:.4f})"
             if agree["tolerance_usd"] is not None else
             "  (no provider delta: cannot say they agree)"))
    print()
    for led in ledgers:
        mark = "" if led["exists"] else "   (absent on this host)"
        print(f"  ledger {led['path']}{mark}")
        if not led["exists"]:
            continue
        print(f"    calls {led['n_calls']}  priced {led['n_priced']}  "
              f"unpriced {led['n_unpriced']}  "
              f"amendments {led['n_amendments']}  ${led['usd']:.4f}")
        for k, v in sorted(led["by_purpose"].items(),
                           key=lambda kv: -kv[1])[:12]:
            print(f"      {k:<34} ${v:.4f}")
        if led["unpriced_models"]:
            print(f"      UNPRICED MODELS: {dict(led['unpriced_models'])}")
    print()
    print("  A total that omits a host's ledger is not this host's fault and "
          "is not zero.\n  Production writes its own file on Railway's volume; "
          "run this there too, or\n  read it through the API, before calling "
          "any number the program-wide spend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
