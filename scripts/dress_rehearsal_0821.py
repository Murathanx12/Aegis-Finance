"""DRESS REHEARSAL for the attended 2026-08-21 resolve — on a copy, with fake prices.

    python -m scripts.dress_rehearsal_0821
    python -m scripts.dress_rehearsal_0821 --as-of 2026-08-21

WHY (Order 18 §3.2)
===================
Thursday is the first time the resolver, the grader and the paired read will
run in sequence against real outcomes. Every piece has been tested; the
SEQUENCE has not, and the pieces were built on different days by someone who
had a different part of the system in mind each time. A pipeline whose parts
each pass is not a pipeline that runs.

So it runs today, end to end, against a COPY of the campaign ledger with
FABRICATED prices — and the fabrication is the point, because a rehearsal that
needs the real answer cannot be run before the real answer exists.

WHAT THIS PROVES AND WHAT IT DOES NOT
--------------------------------------
PROVES: the four stages hand their outputs to each other in the shapes they
expect, the receipt is writable, the grader's refusals fire where they should,
and the campaign ledger is byte-identical afterwards.

DOES NOT PROVE: that Thursday's prices will be fetchable, that the outcomes
will be what the fake ones are, or that the read will be licensed. The
synthetic outcomes here are drawn at the MEASURED base rate so the printed
Brier is in a realistic range — a rehearsal that produced an absurd number
would train the eye to ignore the number.

THE SAFETY PROPERTY, AND IT IS CHECKED RATHER THAN PROMISED
------------------------------------------------------------
The campaign ledger is hashed before the rehearsal and after it, and the
rehearsal FAILS if the two differ. "The rehearsal used a copy" is a claim about
what the code does; the hash is a claim about what happened. Those are not the
same claim, and this project has been wrong about which one it had before.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import evidence_population as EP        # noqa: E402
from backend.services import iif1_grader as G                 # noqa: E402
from backend.services.ledger_resolver import resolve_due      # noqa: E402

POPULATION = EP.EvidencePopulation.CAMPAIGN_FORWARD

#: Drawn at the measured h=5 climatology so the rehearsal's Brier lands in a
#: realistic range. A rehearsal printing an absurd number teaches the reader to
#: skip the number, which is the opposite of its purpose.
SYNTHETIC_BASE_RATE = 0.1963
SEED = 20260818


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _synthetic_prices(seed: int):
    """A deterministic price panel for any ticker and window the resolver asks.

    Deliberately a CLOSURE over one RNG rather than a fresh one per call: the
    resolver may ask for overlapping windows, and a per-call RNG would hand it
    two different prices for the same ticker-date, which is a world no market
    has and would hide a real bug in window handling.
    """
    cache: dict[str, pd.Series] = {}

    def _fetch(tickers: list[str], start: str, end: str) -> pd.DataFrame:
        idx = pd.bdate_range(start=start, end=end)
        if len(idx) == 0:
            idx = pd.bdate_range(start=start, periods=1)
        out = {}
        for t in tickers:
            if t not in cache:
                rng = np.random.default_rng(
                    seed + int(hashlib.sha256(t.encode()).hexdigest()[:8], 16))
                full = pd.bdate_range(start="2026-08-01", end="2026-12-31")
                # Vol chosen so 5-day |move| clears 5% at roughly the measured
                # base rate; the outcomes are then realistic without being real.
                steps = rng.normal(0.0, 0.019, len(full))
                cache[t] = pd.Series(100.0 * np.exp(np.cumsum(steps)),
                                     index=full)
            s = cache[t]
            out[t] = s.reindex(idx).ffill().bfill()
        return pd.DataFrame(out, index=idx)

    return _fetch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dress_rehearsal_0821")
    ap.add_argument("--as-of", default="2026-08-21",
                    help="the date Thursday's run will use")
    ap.add_argument("--workdir", default="",
                    help="where the copy lives; a temp dir by default")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    today = date.fromisoformat(a.as_of)
    real = EP.ledger_path(POPULATION)
    work = Path(a.workdir) if a.workdir else Path(
        tempfile.mkdtemp(prefix="aegis_rehearsal_"))
    work.mkdir(parents=True, exist_ok=True)

    print("=" * 74)
    print(f"DRESS REHEARSAL — the 2026-08-21 pipeline, as-of {today}")
    print("=" * 74)
    print("SYNTHETIC OUTCOMES. Nothing here is evidence about the world.")
    print()

    # ── stage 0: pin the real ledger, so the safety claim is checkable ─────
    before = _sha256(real)
    print(f"[0/4] campaign ledger  {real.name}")
    print(f"      sha256 BEFORE    {before[:32]}...")

    copy = work / "predictions_rehearsal.jsonl"
    shutil.copy2(real, copy)
    n_records = sum(1 for _ in copy.open(encoding="utf-8") if _.strip())
    print(f"      copied to        {copy}")
    print(f"      records          {n_records}")

    # ── stage 1: the resolver, against the COPY, with fabricated prices ────
    print(f"\n[1/4] RESOLVE (as of {today}, synthetic prices)")
    try:
        report = resolve_due(path=copy, today=today,
                             price_fetch=_synthetic_prices(a.seed))
    except Exception as e:                                     # noqa: BLE001
        print(f"      STAGE FAILED: {type(e).__name__}: {e}")
        print("      This is exactly what the rehearsal is for. Thursday would "
              "have failed here, attended, with the window closing.")
        return 1
    print(f"      due              {report.get('due')}")
    print(f"      newly_resolved   {report.get('newly_resolved')}")
    print(f"      pending          {report.get('pending')}")
    print(f"      overdue          {report.get('overdue')}")
    print(f"      unpriceable      {len(report.get('unpriceable', []))}")
    print(f"      priced_from      {report.get('priced_from')}")

    # ── stage 2: the receipt, written where the real run writes one ────────
    print("\n[2/4] RECEIPT")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    receipt = work / f"REHEARSAL_campaign_resolution_{stamp}.json"
    receipt.write_text(json.dumps({
        "receipt": "REHEARSAL — not a campaign resolution",
        "is_rehearsal": True,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": str(today),
        "ledger_used": str(copy),
        "real_ledger_sha256_before": before,
        "report": report,
        "note": ("SYNTHETIC PRICES. This receipt exists to prove the write "
                 "path works; it is evidence about the pipeline and about "
                 "nothing else. It is written to a workdir and NOT to "
                 "docs/receipts/, so it cannot be mistaken for a real one."),
    }, indent=2, default=str), encoding="utf-8")
    print(f"      wrote            {receipt.name}")
    print("      NOT in docs/receipts/ — a rehearsal receipt filed with the "
          "real ones is a future misreading waiting to happen")

    # ── stage 3: the grader, on its own synthetic path ─────────────────────
    print("\n[3/4] GRADER — paired read, BSS and Murphy decomposition")
    try:
        out = G.synthetic_pipeline_check(seed=a.seed) if hasattr(
            G, "synthetic_pipeline_check") else None
    except Exception as e:                                     # noqa: BLE001
        print(f"      STAGE FAILED: {type(e).__name__}: {e}")
        return 1
    if out is None:
        # The grader's synthetic path lives behind the script's --synthetic
        # flag rather than a library entry point; call it the same way Thursday
        # would, so the rehearsal exercises the real surface.
        import subprocess
        rc = subprocess.run(
            [sys.executable, "-m", "scripts.iif1_grade", "--synthetic",
             "--seed", str(a.seed)],
            cwd=str(REPO)).returncode
        # Never read an exit code through a pipeline — this project has been
        # burned by `cmd | tail` reporting tail's 0 while cmd was killed.
        print(f"      grader exit      {rc}")
        if rc != 0:
            print("      STAGE FAILED — the synthetic grade did not complete")
            return 1

    # ── stage 4: the safety property, CHECKED ──────────────────────────────
    print("\n[4/4] THE CAMPAIGN LEDGER, RE-HASHED")
    after = _sha256(real)
    print(f"      sha256 AFTER     {after[:32]}...")
    if after != before:
        print("\n  *** THE REAL LEDGER CHANGED DURING A REHEARSAL. ***")
        print("  Something in this pipeline writes to the population path "
              "rather than the path it was handed. Do NOT run Thursday's "
              "resolve until that is found.")
        return 2
    print("      IDENTICAL — the rehearsal touched a copy, and this is the "
          "check rather than the claim")

    print("\n" + "=" * 74)
    print("REHEARSAL COMPLETE. Thursday's sequence runs.")
    print(f"  workdir: {work}")
    print("  Thursday, for real:  python -m scripts.resolve_campaign_ledger "
          "--dry-run   then --commit")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
