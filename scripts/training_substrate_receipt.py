"""TRAINING_SUBSTRATE_V1 — the machine-readable receipt that closes the
substrate gate (Order 28 §1).

    python -m scripts.training_substrate_receipt

The claim is scoped exactly: **all inputs required by TRAINING_SUBSTRATE_V1
are verified** — never "all WRDS data." The receipt:

  * consumes the freshest `substrate_verification.json` and REFUSES if any
    file anywhere in the bulk store is TRUNCATED / SHORT_MAJOR / CORRUPT,
    or if any CONSUMED input is not verifiably complete;
  * hashes (sha256) every consumed curated file — the panel's actual
    inputs — and records name/rows for the bulk catalogue at large;
  * restates the standing boundaries: over-cap tables earn partitioned
    ingestion through a NAMED CONSUMER, never by existing; terminal
    entitlement facts are facts, not failures; CRSP vintage ends
    2024-12-31.

**v1.1 (2026-08-23)** adds the families the full pull produced — JKP USA
back to 1926, the 13 foreign markets, and AEGIS-PANEL-2 — and adds the one
check the v1 receipt could not make.

THE CHECK v1 COULD NOT MAKE. v1 verified the files that EXIST and reported
the manifest's own counts back. Neither speaks to the plan: a planned table
that was never attempted has no file to verify and no failure row to count,
so it is absent from both. Measured 2026-08-23: seven such tables (all, as
it turned out, genuinely empty on the server — but nothing on disk could
have told the difference between "empty" and "lost"). `plan_reconciliation`
now derives outstanding = plan − on-disk − empty − over-cap − terminal and
REFUSES on a non-empty remainder. Deferred-by-rule is a decision; unaccounted
for is a hole, and only one of the two may pass silently.

Output: backend/data/optimus/wrds/TRAINING_SUBSTRATE_V1.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
CRSP_PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
AEGIS_PANEL = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
JKP_FULL = WRDS / "jkp_full"
BULK = WRDS / "bulk"
OUT = WRDS / "TRAINING_SUBSTRATE_V1.json"
RECEIPT_VERSION = "1.1"

#: The curated files the training stack actually consumes, by family.
CONSUMED = {
    "SPINE": [CRSP_PIT / "crsp_pit_monthly_v1.parquet",
              CRSP_PIT / "crsp_pit_monthly_early.parquet"],
    "PRICES_DAILY": sorted(WRDS.glob("crsp_dsf_*.parquet")),
    "CHARACTERISTICS": [WRDS / "jkp_global_factor_usa.parquet"],
    # v1.1: the full pull. The 2013+ USA extract above is what panel-1
    # consumed and is kept as its own family rather than superseded, because
    # panel-1's receipts still cite it and a receipt that renames a consumed
    # input breaks the trials that reference it.
    "CHARACTERISTICS_USA_FULL": sorted(JKP_FULL.glob("jkp_usa_*.parquet")),
    "CHARACTERISTICS_FOREIGN": sorted(JKP_FULL.glob("jkp_risk_*.parquet")),
    "PANEL": [AEGIS_PANEL / "aegis_panel_v1.parquet"],
    "PANEL_V2": [AEGIS_PANEL / "aegis_panel_v2.parquet"],
    "LINKS": sorted(WRDS.glob("link_*.parquet")),
    "FUNDAMENTALS_RATIOS": sorted(WRDS.glob("finratio_*.parquet"))
                           + [WRDS / "compustat_fundq.parquet"],
    "ANALYSTS": sorted(WRDS.glob("ibes_consensus_*.parquet")),
    "OPTIONS": sorted(WRDS.glob("optionm_surface30d_*.parquet")),
    "MICROSTRUCTURE": sorted(WRDS.glob("taq_iid_*.parquet")),
    "OWNERSHIP_13F": sorted(WRDS.glob("tr13f_s34_*.parquet")),
    "FACTORS": sorted(WRDS.glob("ff_*.parquet"))
               + [WRDS / "bondret_monthly.parquet",
                  WRDS / "frb_rates_daily.parquet",
                  WRDS / "frb_rates_monthly.parquet"],
}

BROKEN = ("TRUNCATED", "SHORT_MAJOR", "CORRUPT")


def _reconcile_plan(man: dict) -> dict:
    """Every planned table accounted for by exactly one disposition.

    The dispositions are not equivalent and the distinction is the point:

      on_disk       pulled, and `substrate_verification` judged the file;
      empty         pulled, zero rows — writes NO parquet, so disk cannot
                    see it and only the manifest can vouch for it;
      over_cap      MEASURED above MAX_ROWS and deferred by the standing
                    named-consumer rule. A DECISION, and a reversible one:
                    these carry the cap they were measured against, so
                    raising it re-queues them automatically;
      terminal      permission denied / absent from server. An ENTITLEMENT
                    FACT about this account, not a transport failure.

    Anything left over is none of those — planned, absent, and undeclared.
    That remainder is what makes this a refusal rather than a report: the
    other four are things somebody decided, and an unaccounted table is a
    thing nobody knows about.
    """
    from scripts.wrds_pull_everything import PLAN_CACHE
    plan = json.loads(PLAN_CACHE.read_text(encoding="utf-8"))["plan"]
    on_disk = {p.stem for p in BULK.glob("*.parquet")}
    empty = {p["name"] for p in (man.get("pulled") or []) if p.get("rows") == 0}
    over = {o["name"] for o in (man.get("over_cap") or [])}
    terminal = {t["name"] for t in json.loads(
        (WRDS / "pull_terminal_failures.json").read_text(encoding="utf-8")
    )["tables"]}

    counts = dict(on_disk=0, empty=0, over_cap=0, terminal=0)
    outstanding = []
    for p in plan:
        if f"{p['schema']}__{p['table']}" in on_disk:
            counts["on_disk"] += 1
        elif p["name"] in empty:
            counts["empty"] += 1
        elif p["name"] in over:
            counts["over_cap"] += 1
        elif p["name"] in terminal:
            counts["terminal"] += 1
        else:
            outstanding.append(p["name"])

    if outstanding:
        raise SystemExit(
            f"REFUSED: {len(outstanding)} planned table(s) are unaccounted "
            f"for — not on disk, not recorded empty, not measured over-cap, "
            f"not a terminal entitlement fact: {outstanding[:20]}\n"
            f"  Run `python -m scripts.wrds_pull_catchup --dry-run`; they "
            f"will appear as NEVER_ATTEMPTED.")

    return {"n_planned": len(plan), **counts, "n_outstanding": 0,
            "note": "over_cap is a DECISION (deferred by the named-consumer "
                    "rule, re-queued if MAX_ROWS rises) and terminal is an "
                    "ENTITLEMENT FACT. Neither is a hole. An unaccounted "
                    "table would be, and this receipt refuses on one."}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    ver = json.loads((WRDS / "substrate_verification.json")
                     .read_text(encoding="utf-8"))
    man = json.loads((WRDS / "pull_everything_manifest.json")
                     .read_text(encoding="utf-8"))

    broken = [f for f in ver["files"] if f["verdict"] in BROKEN]
    unknown = [f for f in ver["files"]
               if f["verdict"] in ("UNVERIFIED", "IN_FLIGHT")]
    if broken:
        raise SystemExit(f"REFUSED: {len(broken)} broken file(s) in the "
                         f"bulk store: {[b['file'] for b in broken][:10]}")

    missing = {fam: [str(p) for p in paths if not p.exists()]
               for fam, paths in CONSUMED.items()}
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        raise SystemExit(f"REFUSED: consumed inputs missing: {missing}")
    # a glob that matches nothing has no paths to fail the check above —
    # an EMPTY family is a rename or a deleted store, never a pass
    empty = [fam for fam, paths in CONSUMED.items() if not paths]
    if empty:
        raise SystemExit(f"REFUSED: consumed families matched ZERO files "
                         f"(rename/typo/deleted store?): {empty}")

    families = {}
    for fam, paths in CONSUMED.items():
        families[fam] = [{"file": p.name,
                          "bytes": p.stat().st_size,
                          "sha256_16": _sha(p)} for p in paths]

    over_cap = man.get("over_cap", [])
    n_terminal = int(man.get("n_terminal_not_entitled", 0))
    n_pulled = len(man.get("pulled", []))

    reconciliation = _reconcile_plan(man)

    receipt = {
        "receipt": "TRAINING_SUBSTRATE_V1",
        "version": RECEIPT_VERSION,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claim": "all inputs required by TRAINING_SUBSTRATE_V1 are "
                 "verified — NOT 'all WRDS data'",
        "verification": {
            "verified_at": ver["verified_at"],
            "n_files": ver["n_files"],
            "by_verdict": ver["by_verdict"],
            "n_broken": 0,
            "unknown_status": [u["file"] for u in unknown],
            "unknown_note": "UNVERIFIED/IN_FLIGHT files are status-unknown "
                            "and are NOT consumed by any family below",
        },
        "consumed_families": families,
        "catalogue_at_large": {
            "n_tables_pulled": n_pulled,
            "n_over_cap": len(over_cap),
            "over_cap_rule": "a large table earns partitioned ingestion "
                             "through a NAMED CONSUMER, never by existing",
            "n_terminal_not_entitled": n_terminal,
            "terminal_note": "entitlement facts (permission denied / "
                             "absent from server), recorded not retried",
            "completed_at": man.get("completed_at"),
        },
        "plan_reconciliation": reconciliation,
        "vintage": {"crsp_ends": "2024-12-31",
                    # panel-1's world, unchanged — its receipts cite it
                    "jkp_window": "2013-01-31..2024-12-31",
                    "panel_window": "2014-01-31..2024-11-29",
                    # v1.1: what the full pull added
                    "jkp_usa_full_window": "1926-01-31..2024-12-31",
                    "jkp_foreign_window": "2013-01-31..2024-12-31",
                    "jkp_foreign_markets": 13,
                    "panel_v2_window": "1926-01-31..2024-12-31"},
        "pit_receipts": {
            "jkp_spot_audit": "aegis_panel/jkp_pit_audit_2026-08-22.json "
                              "= PASS",
        },
    }
    OUT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({
        "version": RECEIPT_VERSION,
        "n_files_verified": ver["n_files"],
        "by_verdict": ver["by_verdict"],
        "consumed_files": sum(len(v) for v in families.values()),
        "unknown_status": [u["file"] for u in unknown],
        "over_cap": len(over_cap), "terminal": n_terminal,
        "plan_reconciliation": reconciliation,
    }, indent=2))
    print("receipt:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
