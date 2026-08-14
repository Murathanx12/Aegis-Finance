"""INTERNET-INVESTIGATOR-FWD-1 — the four integrity holes found in review.

Each test here pins a defect that passed every existing check. They are grouped
in their own file because they are not about whether a night WORKS — they are
about whether a night that works is the trial that was registered.

  1. A production invocation could be reshaped by its own arguments.
  2. Pairing was asserted on tickers, while the statistic is computed on cells.
  3. Provenance used a process-salted hash and the wrong served model, and the
     receipts were written where a deploy would delete them.
  4. The nightly ceiling was checked after the fact, so the last call could
     cross it.

Offline and deterministic.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile

import pytest

from backend.services import iif1_prereg as P
from backend.services import investigator_night as N
from backend.tests.test_investigator_night import (FakeReply, _feats, good_llm,
                                                   no_tools)


def _needs_frozen_config():
    if P.load_frozen_config() is None:
        pytest.skip("frozen-config exemption declared for this context")


# ── 1. a production invocation cannot be reshaped by its arguments ──────────

@pytest.mark.parametrize("kw,needle", [
    ({"k": 10}, "TRIGGERS_PER_NIGHT"),
    ({"arms": ("A_snapshot", "B_tools")}, "ARMS"),
    ({"max_usd": 100.0}, "NIGHTLY_MAX_USD"),
])
def test_a_production_run_refuses_overridden_frozen_parameters(kw, needle):
    """`verify_or_refuse()` compares module CONSTANTS and cannot see arguments.

    So this passed every check before the EFFECTIVE invocation was verified:

        run_night(k=10, arms=("A_snapshot","B_tools"), max_usd=100)

    The verifier read `TRIGGERS_PER_NIGHT == 40`, a complete `ARMS` and a $12
    ceiling, reported the trial as registered — and the run then executed ten
    triggers across two arms at a hundred dollars. A frozen parameter a caller
    can override is not frozen; it is a default.
    """
    _needs_frozen_config()
    with pytest.raises(N.SandboxRequired, match=needle):
        N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                    dry_run=True, **kw)


@pytest.mark.parametrize("kw,needle", [
    ({"llm_call": good_llm}, "llm_call was injected"),
    ({"tool_runner": no_tools}, "tool_runner was injected"),
])
def test_a_production_run_refuses_injected_dependencies(kw, needle):
    """Injection and accrual shared one path, and `dry_run` defaults to False —
    so a real paid client passed through `llm_call` would have written the
    evidence ledger with no pre-registration check at all."""
    _needs_frozen_config()
    with pytest.raises(N.SandboxRequired, match=needle):
        N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                    dry_run=True, **kw)


def test_the_refusal_names_its_remedy():
    _needs_frozen_config()
    with pytest.raises(N.SandboxRequired, match="sandbox=True"):
        N.run_night({"T1": _feats()}, k=1, dry_run=True)


def test_a_sandbox_run_never_reaches_the_evidence_ledger(monkeypatch):
    """`sandbox` outranks `dry_run`. Forgetting `dry_run=True` must not be able
    to turn a rehearsal into forward evidence."""
    wrote: list = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: wrote.extend(recs))
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    monkeypatch.setattr(N, "SANDBOX_RECEIPTS_DIR",
                        pathlib.Path(tempfile.mkdtemp()))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=good_llm,
                      tool_runner=no_tools, dry_run=False, sandbox=True)
    assert res.status == "ok" and res.sandbox is True
    assert wrote == [], "a sandbox run wrote to the evidence ledger"
    assert res.records, "the rehearsal minted nothing to inspect"
    assert res.records_written == 0


def test_sandbox_and_production_receipts_do_not_share_a_directory():
    assert N.SANDBOX_RECEIPTS_DIR != N.RECEIPTS_DIR


def test_receipts_live_with_the_ledger_on_the_persistent_volume():
    """NIGHT-14 defect F7, reproduced in this very file: the receipt was written
    under the repo while the ledger it describes lives on the volume, so a
    deploy would keep every prediction and destroy the evidence of how it was
    produced."""
    from backend.services import belief_state
    assert N.RECEIPTS_DIR.parent == belief_state.LEDGER_DIR


def test_the_minted_records_are_not_serialised_into_the_receipt(monkeypatch):
    """`records` exists so a rehearsal can inspect what a night would write. It
    carries priors and posteriors, and the receipt is read by a human every
    morning for forty mornings."""
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=good_llm,
                      tool_runner=no_tools, dry_run=True, sandbox=True)
    assert res.records
    assert "records" not in res.as_dict()
    blob = json.dumps(res.as_dict(), default=str)
    for leak in ("posterior", "probability", "rationale"):
        assert leak not in blob


# ── 2. pairing at the forecast-cell level ──────────────────────────────────

def test_cell_key_distinguishes_horizon_and_threshold():
    a = N.cell_key("NVDA", {"observable": "abs_move_exceeds",
                            "horizon_days": 5, "threshold": 0.05})
    b = N.cell_key("NVDA", {"observable": "abs_move_exceeds",
                            "horizon_days": 1, "threshold": 0.05})
    c = N.cell_key("NVDA", {"observable": "abs_move_exceeds",
                            "horizon_days": 5, "threshold": 0.03})
    assert a != b and a != c
    assert a == N.cell_key("NVDA", {"observable": "abs_move_exceeds",
                                    "horizon_days": 5, "threshold": 0.05000000})


def test_a_cell_missing_from_one_arm_is_removed_from_every_arm(monkeypatch):
    """Ticker-level pairing is necessary and NOT sufficient.

    Every arm attempts T1, but one arm's forecaster drops the 1-day cell. A
    ticker-level guard sees five arms that all "did T1" and compares different
    cell sets under the name of a paired test.
    """
    state = {"drop": False}

    def lossy(*, system, user, model="deepseek-v4-flash", **kw):
        r = good_llm(system=system, user=user, model=model)
        if "MAGNITUDE" in system and state["drop"]:
            body = json.loads(r.text)
            body["forecasts"] = [f for f in body["forecasts"]
                                 if f["horizon_days"] != 1]
            r.text = json.dumps(body)
        return r

    real = N.Investigator

    class OneArmLoses(real):                                   # type: ignore
        def investigate(self, ticker, snapshot=None):
            state["drop"] = (self.arm == "C_tools_only")
            return super().investigate(ticker, snapshot)

    monkeypatch.setattr(N, "Investigator", OneArmLoses)
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=lossy,
                      tool_runner=no_tools, dry_run=True, sandbox=True)

    assert res.status == "ok"
    assert res.cell_pairing["n_cells_dropped_unpaired"] > 0

    by_arm = {arm: {(r.ticker, r.horizon_days) for r in res.records
                    if r.arm == arm} for arm in N.ARMS}
    assert len(set(map(frozenset, by_arm.values()))) == 1, by_arm
    assert all(1 not in {h for _, h in ks} for ks in by_arm.values()), \
        "the 1-day cell survived in arms that should have lost it symmetrically"


def test_drop_rates_are_reported_rather_than_repaired(monkeypatch):
    """A differential malformed-output rate is itself an architectural result,
    so it is surfaced rather than quietly patched over."""
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=good_llm,
                      tool_runner=no_tools, dry_run=True, sandbox=True)
    cp = res.cell_pairing
    assert set(cp["per_arm"]) == set(N.ARMS)
    assert all("n_dropped_for_pairing" in v for v in cp["per_arm"].values())
    assert cp["n_cells_paired"] == cp["n_cells_union"]     # nothing lost here
    assert "threshold" in cp["key"]


def test_zero_shared_cells_voids_the_night(monkeypatch):
    """Nothing survived the intersection means nothing paired to compare, and
    an empty comparison must not be recorded as a quiet night."""
    def no_forecasts(*, system, user, model="m", **kw):
        if "MAGNITUDE" in system:
            return FakeReply(json.dumps({"forecasts": []}), model)
        return good_llm(system=system, user=user, model=model)

    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=no_forecasts,
                      tool_runner=no_tools, dry_run=True, sandbox=True)
    assert res.status == "void"
    assert "nothing paired" in res.void_reason
    assert res.records == []


# ── 3. provenance ──────────────────────────────────────────────────────────

def test_the_dossier_identifier_is_sha256_not_a_process_salted_hash():
    """The defect was worse than "an ugly identifier".

    `input_snapshot` is not stored — the ledger stores `input_snapshot_hash`.
    So a process-salted `hash(inv.dossier)` sitting inside that dict made the
    ENTIRE snapshot hash non-reproducible: the same night, replayed, produced a
    different hash, and no record could ever be tied back to the input that
    produced it. That is the field's only job.

    Pinned at the source, because the symptom is invisible in a single process:
    `hash()` is stable within one interpreter and only differs across runs.
    """
    src = pathlib.Path(N.__file__).read_text(encoding="utf-8")
    assert "hash(inv.dossier)" not in src, "the process-salted hash is back"
    assert "hashlib.sha256" in src
    assert "dossier_sha256" in src


def test_the_snapshot_hash_is_stable_when_the_same_night_is_replayed(monkeypatch):
    """The property the SHA-256 buys: replay the identical night, get the
    identical record identity."""
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    kw = dict(k=1, llm_call=good_llm, tool_runner=no_tools,
              dry_run=True, sandbox=True, night="2026-08-14")
    a = N.run_night({"T1": _feats()}, **kw)
    b = N.run_night({"T1": _feats()}, **kw)
    assert a.records and b.records
    assert [r.input_snapshot_hash for r in a.records] == \
           [r.input_snapshot_hash for r in b.records]
    assert hashlib.sha256(b"x").hexdigest() == hashlib.sha256(b"x").hexdigest()


def test_the_record_names_the_model_that_served_the_forecast_call(monkeypatch):
    """`sorted(served_models)[0]` returns whichever name sorts first across five
    microtasks. If the extractor and the forecaster were served different models
    — the failure that voided a model-diversity arm — the record would name a
    model that did not make the forecast attached to it."""
    def mixed(*, system, user, model="deepseek-v4-flash", **kw):
        r = good_llm(system=system, user=user, model=model)
        # sorts BEFORE the forecaster's model, so the old code picked it
        r.model_version = ("deepseek-v4-flash" if "MAGNITUDE" in system
                           else "aaa-other-model")
        return r

    monkeypatch.setattr(N, "_spend_since", lambda s: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=mixed,
                      tool_runner=no_tools, dry_run=True, sandbox=True)
    assert res.records
    for r in res.records:
        assert r.model_version == "deepseek-v4-flash"
    # the other served model is not lost — it is on the night receipt
    assert "aaa-other-model" in res.per_arm["B_tools"]["rows"][0]["served_models"]


# ── 4. the ceiling is hard, not approximate ────────────────────────────────

def test_the_last_call_cannot_carry_the_night_past_the_ceiling(monkeypatch):
    """At $11.99 against a $12 cap the old gate permitted one more call, and
    that call could take the night over a ceiling the prereg calls hard."""
    monkeypatch.setattr(N, "_spend_since", lambda s: (11.99, 10))
    call = N.make_llm_call(since_iso="x", max_usd=12.0)
    with pytest.raises(N.NightlyBudgetExhausted, match="would be breached"):
        call(system="s", user="u")


def test_the_reserve_is_larger_than_a_typical_call_by_a_wide_margin():
    """MARKET-GRAPH-1 measured $0.00073/call on document-sized payloads. A
    reserve at that size would not be worst-case."""
    assert N.WORST_CASE_CALL_USD >= 0.01


def test_spending_well_under_the_ceiling_still_proceeds(monkeypatch):
    monkeypatch.setattr(N, "_spend_since", lambda s: (1.00, 10))
    monkeypatch.setattr("backend.services.llm_swarm.default_llm_call",
                        lambda *a, **k: FakeReply("{}"))
    monkeypatch.setattr(N, "_record_telemetry", lambda *a, **k: None)
    call = N.make_llm_call(since_iso="x", max_usd=12.0)
    assert call(system="s", user="u") is not None
