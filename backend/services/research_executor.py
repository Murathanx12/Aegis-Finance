"""AEGIS-RESEARCH-EXECUTOR-1 — the daemon stops being only a queue.

The first real receipt said ``submitted: 13, tests_run: 0`` — a scheduler,
not a factory. This module is the smallest executor that can take a queued
job to an outcome WITHOUT loosening a single gate on the way:

* a job runs only through an adapter DECLARED for its hypothesis_id — no
  adapter, no run, and the receipt says so per job rather than in aggregate;
* an adapter may not substitute data, estimator or period: it declares what
  it will read and the executor pins that against the submitted job before
  calling run();
* signature-gated and conventions-gated jobs classify BLOCKED with the
  reason in words — a blocked job is a finding about the queue, not a
  failure of it (the ACTIONABLE vs DELIBERATE split, applied to research);
* an INSTRUMENT_AUDIT adapter may run for a blocked trial (power audit,
  matched-control balance, dataset description) but its output is never
  recorded as the trial's result — the audit receipt says what it is.

States stay the daemon's. Verdict criteria stay `decide()`'s (§63). The
executor's only powers are: classify, run what is runnable, record honest
receipts.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from backend.services.research_daemon import (DAEMON_DIR, ResearchDaemon,
                                              Submission)

RUNNABLE = "RUNNABLE"
BLOCKED = "BLOCKED"
NO_ADAPTER = "NO_ADAPTER"

#: Adapter kinds. RESULT adapters produce the trial's own outcome and are
#: recorded through daemon.record_result; INSTRUMENT_AUDIT adapters measure
#: the instrument (power, coverage, balance) and never touch the trial's
#: result slot.
KIND_RESULT = "RESULT"
KIND_INSTRUMENT_AUDIT = "INSTRUMENT_AUDIT"


class ExecutorRefused(RuntimeError):
    """A required declaration is missing. Refused, not defaulted."""


@dataclass(frozen=True)
class JobOutcome:
    """What a RESULT adapter must return. p_value is the trial's declared
    statistic under its declared null — the executor does not interpret it."""

    p_value: float
    observed_effect: float | None
    artifacts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class JobAdapter:
    hypothesis_id: str
    kind: str                                  # KIND_RESULT | KIND_INSTRUMENT_AUDIT
    #: What this adapter reads — pinned against the job at run time so a
    #: silent substitution of period/universe is a refusal, not a footnote.
    reads_universe: str
    reads_start: str
    reads_end: str
    run: Callable[[], JobOutcome | dict]
    #: None = runnable. A sentence = why this job cannot run yet (signature,
    #: conventions, absent data). Blocked adapters never call run().
    blocked_reason: str | None = None

    def assert_matches(self, sub: Submission) -> None:
        j = sub.job
        if (self.reads_universe != j.universe or self.reads_start != j.start
                or self.reads_end != j.end):
            raise ExecutorRefused(
                f"{self.hypothesis_id}: adapter declares "
                f"{self.reads_universe}/{self.reads_start}..{self.reads_end} "
                f"but the SUBMITTED job says {j.universe}/{j.start}..{j.end}."
                f" A job may never silently substitute data or period.")


class Executor:
    def __init__(self, daemon: ResearchDaemon,
                 adapters: dict[str, JobAdapter] | None = None) -> None:
        self.daemon = daemon
        self.adapters = dict(adapters or {})

    def register(self, adapter: JobAdapter) -> None:
        if adapter.hypothesis_id in self.adapters:
            raise ExecutorRefused(
                f"{adapter.hypothesis_id}: an adapter is already registered; "
                f"two adapters for one hypothesis is two experiments sharing "
                f"one ledger entry")
        if adapter.kind not in (KIND_RESULT, KIND_INSTRUMENT_AUDIT):
            raise ExecutorRefused(f"unknown adapter kind {adapter.kind!r}")
        self.adapters[adapter.hypothesis_id] = adapter

    # -- classification ------------------------------------------------------
    def classify(self, sub: Submission) -> dict:
        """RUNNABLE / BLOCKED(reason) / NO_ADAPTER, with the submission's own
        shelf state respected. Never raises for an unknown job — the receipt
        is where 'we cannot run this' becomes legible."""
        a = self.adapters.get(sub.job.hypothesis_id)
        if a is None:
            return {"status": NO_ADAPTER,
                    "reason": "no adapter declared — building one is the "
                              "unit of work that makes this job real"}
        if a.blocked_reason:
            return {"status": BLOCKED, "reason": a.blocked_reason,
                    "kind": a.kind}
        return {"status": RUNNABLE, "kind": a.kind}

    def classify_all(self) -> dict[str, dict]:
        return {s.job.hypothesis_id: self.classify(s)
                for s in self.daemon.queue()}

    # -- execution -----------------------------------------------------------
    def run_ready(self, *, max_jobs: int = 2) -> dict:
        """Run up to `max_jobs` RUNNABLE jobs, highest frozen priority first.

        Failures are caught, counted and reported with their traceback tail —
        a job that dies must not kill the night, and a night that reports
        'ok' over a dead job would be the house failure mode.
        """
        receipt: dict = {
            "executor": "AEGIS-RESEARCH-EXECUTOR-1",
            "started_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "executed": [], "audited": [], "failed": [],
            "blocked": [], "no_adapter": [],
        }
        ran = 0
        for sub in self.daemon.queue():
            hid = sub.job.hypothesis_id
            c = self.classify(sub)
            if c["status"] == NO_ADAPTER:
                receipt["no_adapter"].append(hid)
                continue
            if c["status"] == BLOCKED:
                receipt["blocked"].append({"hypothesis_id": hid,
                                           "reason": c["reason"]})
                continue
            if ran >= max_jobs:
                break
            a = self.adapters[hid]
            t0 = time.perf_counter()
            try:
                a.assert_matches(sub)
                out = a.run()
                elapsed = round(time.perf_counter() - t0, 1)
                if a.kind == KIND_RESULT:
                    if not isinstance(out, JobOutcome):
                        raise ExecutorRefused(
                            f"{hid}: RESULT adapter returned "
                            f"{type(out).__name__}, not JobOutcome — a "
                            f"result without a declared statistic is not "
                            f"recordable")
                    self.daemon.record_result(
                        hid, p_value=out.p_value,
                        observed_effect=out.observed_effect)
                    receipt["executed"].append(
                        {"hypothesis_id": hid, "p_value": out.p_value,
                         "observed_effect": out.observed_effect,
                         "elapsed_s": elapsed})
                else:
                    receipt["audited"].append(
                        {"hypothesis_id": hid, "elapsed_s": elapsed,
                         "audit": out if isinstance(out, dict) else {},
                         "note": "INSTRUMENT_AUDIT — measures the "
                                 "instrument, not the hypothesis; the "
                                 "trial's result slot is untouched"})
                ran += 1
            except Exception as e:                       # noqa: BLE001
                receipt["failed"].append(
                    {"hypothesis_id": hid, "error": repr(e),
                     "trace_tail": traceback.format_exc().strip()
                     .splitlines()[-3:]})
                ran += 1
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        receipt["tests_run_total"] = self.daemon.tests_run()
        return receipt

    def write_receipt(self, receipt: dict, *, out_dir: Path | None = None
                      ) -> Path:
        d = Path(out_dir or DAEMON_DIR)
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        p = d / f"executor_{stamp}.json"
        p.write_text(json.dumps(receipt, indent=2, default=str),
                     encoding="utf-8")
        return p


# ── the first real adapters ────────────────────────────────────────────────
def convexity_power_audit() -> dict:
    """INSTRUMENT_AUDIT for CONVEXITY-PRESERVATION-1: what could the trial
    resolve, on the episodes that exist? No policy verdict — trim-vs-hold
    belongs to the signed registration. This reads the materialized episode
    file and reports per-threshold episode counts, matched-control coverage
    and the per-date-block MDE the registered contrast would face."""
    import numpy as np
    import pandas as pd

    from backend import config as _config

    path = (_config.OPTIMUS_LEDGER_DIR / "convexity"
            / "episodes_v1.parquet")
    if not path.exists():
        raise ExecutorRefused(f"episode file absent at {path}; an audit of "
                              f"nothing would report a clean instrument")
    df = pd.read_parquet(path)
    out: dict = {"n_episodes": int(len(df)),
                 "by_threshold": {str(k): int(v) for k, v in
                                  df["threshold"].value_counts().items()}}
    if "control" in df.columns:
        out["matched_fraction"] = round(float(df["control"].notna().mean()),
                                        4)
    # date blocks: crossing month (§58 — the unit is the DATE BLOCK)
    if "crossing_date" in df.columns:
        months = pd.to_datetime(df["crossing_date"]).dt.to_period("M")
        out["n_date_blocks"] = int(months.nunique())
        # the registered contrast is a tw_<arm> − tw_hold difference; its
        # power is priced on the per-block SE of that PAIRED difference
        # (trim_25 as the representative arm — same construction as the rest)
        if {"tw_trim_25", "tw_hold"} <= set(df.columns) and \
                out["n_date_blocks"] >= 2:
            d = df["tw_trim_25"] - df["tw_hold"]
            per_block = d.groupby(months).mean()
            se = float(per_block.std(ddof=1)
                       / np.sqrt(out["n_date_blocks"]))
            out["per_block_se_paired_trim25_vs_hold"] = round(se, 6)
            out["mde_80pct_terminal_wealth_fraction"] = round(2.8 * se, 6)
            out["declared_expected_effect"] = 0.030
    out["audit_basis"] = ("descriptive + power only; the trim-vs-hold "
                          "verdict runs under the signed registration")
    return out
