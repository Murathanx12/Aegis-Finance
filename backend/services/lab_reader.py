"""WHICH READER TYPES THE CORPUS — local by default, cloud only when it is paid for.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 3.2,
amended by `docs/research_notes/2026-09-13/research_cloud_llm_readers.md`, which
landed after the spec was written.

THE SPEC AND THE MEASUREMENT DISAGREED, AND THE MEASUREMENT WON
===============================================================
The spec designed a `CloudReader` protocol with NO concrete implementation,
because the research draft was unfilled at the time and building against an
unfilled draft is how a spec drifts from the research meant to ground it. By
the time this was built the draft had landed and reported a measurement: the
DeepSeek path is already wired through `model_provider.PROVIDERS` and
`free_inference.complete`, and `night_l2_typed_events --backend deepseek` typed
6,000 rows on 2026-09-13 at about $2 with a 0.3% refusal rate once the schema
was on the wire.

So there are THREE readers, not two, and the difference between the second and
the third is the whole point:

* `local` — llama-server on this machine. Free, slow (51-261 h for the 6,020-row
  backlog), and the default. Never started or stopped by the lab.
* `deepseek` — ALREADY IMPLEMENTED, through the same `free_inference.complete`
  seam every other backend uses. Metered: every tick is guarded by
  `lab_budget` BEFORE the call.
* `cloud` — a generic `CloudReader` for a provider that is NOT one of the
  wired backends. NOTHING is registered, and asking for it REFUSES by name
  (`CLOUD_READER_NOT_IMPLEMENTED`) rather than silently falling back to local
  and calling the result a cloud run. That refusal is the honest state to ship
  and it is what keeps the hook from rotting into a lie.

WHY A REFUSAL RATHER THAN A FALLBACK
====================================
A fallback would make `AEGIS_L2_READER=cloud` produce a receipt that says
`reader: cloud` over rows a local model typed. Every downstream comparison —
the local/cloud overlap kappa most of all — would then be comparing a reader
with itself. A silent substitution is the failure `book_cadence.UnsupportedSignal`
already refuses for signals; this is the same rule for readers.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from backend import config as _config

#: The env var that picks the reader. `local` when unset — the default a
#: machine with no key and no budget must land on.
READER_ENV = "AEGIS_L2_READER"

#: The readers this module knows. `cloud` is the generic hook and has no
#: implementation; `deepseek` is wired and metered.
READERS = ("local", "deepseek", "cloud")

#: MEASURED 2026-09-13 17:18, from the CALL LEDGER rather than from the job's
#: own receipt: **$2.04 over 6,007 typed rows** on DeepSeek, prompt-cached,
#: schema on the wire, 1 h 45 min wall, event-type kappa 0.87 on the 50-row
#: re-prompt. The job's own `llm_spend_usd` printed **$0.00** for that same run
#: -- the field reads the local-cost path -- so the ledger is the number that
#: ships here and `lab_budget` books this estimate whenever a metered run
#: reports zero. Used ONLY for the pre-call guard; the ground truth stays
#: `scripts/llm_cost_audit.py`'s reconciliation against the provider's balance.
#: Named an ESTIMATE in every receipt that quotes it, because it is one.
DEEPSEEK_MEASURED_USD = 2.04
DEEPSEEK_MEASURED_ROWS = 6007
DEEPSEEK_USD_PER_ROW = DEEPSEEK_MEASURED_USD / DEEPSEEK_MEASURED_ROWS


class CloudReaderNotImplemented(RuntimeError):
    """`AEGIS_L2_READER=cloud` and no `CloudReader` is registered.

    Deliberately NOT a fallback to local: a receipt that said `reader: cloud`
    over locally typed rows would make every local-vs-cloud comparison a
    comparison of one reader with itself.
    """


class ReaderRefused(RuntimeError):
    """The chosen reader cannot run, and the receipt says which one and why."""


@runtime_checkable
class CloudReader(Protocol):
    """One method, returning exactly what the local reader returns.

    The shape is the local path's own so that a typed row carries no trace of
    which reader produced it beyond the `backend` field that is written on
    purpose. A protocol with a wider return type would let a cloud reader
    smuggle a field the local one cannot produce, and the first model trained
    on the union would silently be reading a provider label.
    """

    def type_batch(self, rows: list[dict]) -> list[Any]:
        ...


#: Nothing is registered. `register()` exists so chunk 15 can fill this in
#: without touching the supervisor, and `test_cloud_reader_env_var_without_
#: implementation_refuses_by_name` asserts the empty case refuses.
_REGISTRY: dict[str, CloudReader] = {}


def register(name: str, reader: CloudReader) -> None:
    if not isinstance(reader, CloudReader):
        raise TypeError(f"{name!r} does not satisfy the CloudReader protocol "
                        f"(it needs `type_batch(rows) -> list`)")
    _REGISTRY[name] = reader


def registered() -> list[str]:
    return sorted(_REGISTRY)


def get(name: str) -> CloudReader:
    if name not in _REGISTRY:
        raise CloudReaderNotImplemented(
            f"CLOUD_READER_NOT_IMPLEMENTED: no CloudReader is registered"
            + (f" under {name!r}" if name else "")
            + f". Registered: {registered() or 'none'}. This is a REFUSAL, not a "
              f"fallback to the local reader — a receipt that said `reader: cloud` "
              f"over locally typed rows would make every local-vs-cloud "
              f"comparison a comparison of one reader with itself. Chunk 15 "
              f"registers one; until then set {READER_ENV}=local or =deepseek.")
    return _REGISTRY[name]


def chosen(env: dict | None = None) -> str:
    """The reader the environment asks for, `local` when it asks for nothing."""
    src = env if env is not None else os.environ
    name = (src.get(READER_ENV) or "local").strip().lower()
    return name


def provider_configured(name: str) -> bool:
    from backend.services import model_provider
    return name in model_provider.PROVIDERS and model_provider.configured(name)


def estimate_usd(reader: str, rows: int) -> float:
    """What `rows` rows would cost at this reader. Local is 0.0, and says so."""
    if reader in ("local", "cloud"):
        return 0.0
    if reader == "deepseek":
        return round(DEEPSEEK_USD_PER_ROW * max(0, int(rows)), 6)
    return 0.0


def resolve(*, rows_this_tick: int, env: dict | None = None) -> dict:
    """Which backend the typing loop should call, or a NAMED refusal.

    Returns a row carrying `backend` (what `L2_typed_events` is given), the
    estimate, and the reason. Raises nothing: the caller records a refusal in
    its receipt and moves to the next loop, which is what "a refusal is a
    finding" means for a loop that must keep ticking.
    """
    name = chosen(env)
    row: dict = {"reader": name, "rows_this_tick": int(rows_this_tick),
                 "metered": name not in ("local",),
                 "estimated_usd": estimate_usd(name, rows_this_tick),
                 "cost_basis": ("MEASURED 2026-09-13 by the CALL LEDGER: "
                                f"${DEEPSEEK_MEASURED_USD:.2f} over "
                                f"{DEEPSEEK_MEASURED_ROWS:,} rows (the job receipt "
                                "printed $0.00 for the same run); an ESTIMATE, "
                                "reconciled by llm_cost_audit.py"
                                if name == "deepseek" else "local reads cost compute, "
                                "not dollars")}

    if name not in READERS:
        return {**row, "ok": False, "refusal": "UNKNOWN_READER",
                "detail": f"{name!r} is not one of {READERS}; set {READER_ENV}"}

    if name == "local":
        return {**row, "ok": True, "backend": "local"}

    if name == "cloud":
        try:
            get("")
        except CloudReaderNotImplemented as exc:
            return {**row, "ok": False, "refusal": "CLOUD_READER_NOT_IMPLEMENTED",
                    "detail": str(exc)}
        return {**row, "ok": True, "backend": "cloud"}

    # a wired provider: it must be configured AND inside the day's dollar cap,
    # and the cap is checked BEFORE the call, never refunded after one.
    if not provider_configured(name):
        from backend.services import model_provider
        key = (model_provider.PROVIDERS.get(name) or {}).get("key_env")
        return {**row, "ok": False, "refusal": f"{name.upper()}_NOT_CONFIGURED",
                "detail": (f"{key} is unset or empty. A reader that cannot "
                           f"authenticate is a refusal, not a fallback to local.")}

    from backend.services import lab_budget
    try:
        budget = lab_budget.guard(row["estimated_usd"], backend=name,
                                  what=f"L2 typing, {rows_this_tick} rows")
    except lab_budget.SpendCapReached as exc:
        return {**row, "ok": False, "refusal": "DAILY_SPEND_CAP_REACHED",
                "detail": str(exc),
                "spend_today_usd": lab_budget.spend_today()["spend_today_usd"],
                "spend_cap_usd": lab_budget.cap_usd()}
    return {**row, "ok": True, "backend": name,
            "spend_today_usd": budget["spend_today_usd"],
            "spend_cap_usd": budget["cap_usd"],
            "remaining_usd": budget["remaining_usd"]}


def overlap_rows() -> int:
    """How many rows BOTH readers type, for the agreement (kappa) comparison.

    A paired sample: the same rows through both readers, so kappa answers "do
    these two readers agree" rather than "do two different samples look alike".
    """
    return int(_config.LAB_L2_OVERLAP_ROWS)


def overlap_report(typed_rows: list[dict] | None = None, *,
                   target: int | None = None) -> dict:
    """Kappa between two READERS on the rows both of them typed.

    Distinct from L2's own `kappa_rows` control, which re-prompts ONE reader
    with a second prompt hash and measures prompt sensitivity. This one holds
    the prompt fixed and changes the reader, and the two questions have been
    confused before: "the model is stable" and "the models agree" are different
    claims and only the second licenses mixing two readers' rows in one table.

    PAIRED BY ROW KEY, never by position. Two readers that typed different
    samples of the same size would otherwise produce a kappa over rows that
    have nothing to do with each other.
    """
    target = int(target if target is not None else overlap_rows())
    if typed_rows is None:
        typed_rows = _read_typed_rows()

    by_key: dict[tuple, dict[str, dict]] = {}
    for r in typed_rows:
        key = (str(r.get("source") or ""), str(r.get("first_seen_utc") or ""),
               str(r.get("raw_id") or ""))
        backend = str(r.get("backend") or "unstated")
        # first write per (key, backend) wins: a re-typed row is the cursor
        # having been rewound, and scoring both copies would double one reader.
        by_key.setdefault(key, {}).setdefault(backend, r)

    paired = {k: v for k, v in by_key.items() if len(v) >= 2}
    backends = sorted({b for v in by_key.values() for b in v})
    row = {"n_paired": len(paired), "target_rows": target,
           "backends_seen": backends,
           "note": ("kappa between two READERS on the same rows, prompt held "
                    "fixed — not L2's own second-prompt control, which holds the "
                    "reader fixed and changes the prompt")}
    if len(paired) < 2:
        return {**row, "status": "insufficient_overlap",
                "why": (f"{len(paired)} row(s) have been typed by two or more "
                        f"readers; the declared overlap set is {target}. Until a "
                        f"second reader runs, kappa is CANNOT DETERMINE and no "
                        f"row from two readers may be mixed in one table.")}

    from scripts.night_l2_typed_events import agreement
    a_name, b_name = sorted({b for v in paired.values() for b in v})[:2]
    rows_a = [v[a_name] for v in paired.values() if a_name in v and b_name in v]
    rows_b = [v[b_name] for v in paired.values() if a_name in v and b_name in v]
    return {**row, "status": ("ok" if len(rows_a) >= target
                              else "below_declared_overlap"),
            "reader_a": a_name, "reader_b": b_name,
            "agreement": agreement(rows_a, rows_b)}


def _read_typed_rows() -> list[dict]:
    from pathlib import Path

    from backend.services import jsonl_io as jio
    d = Path(_config.DATA_DIR) / "optimus" / "typed_events"
    if not d.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(d.glob("*.jsonl")):
        got, _bad = jio.read_rows(p)
        out.extend(got)
    return out


__all__ = ["DEEPSEEK_MEASURED_ROWS", "DEEPSEEK_MEASURED_USD",
           "DEEPSEEK_USD_PER_ROW", "READERS", "READER_ENV", "CloudReader",
           "CloudReaderNotImplemented", "ReaderRefused", "chosen",
           "estimate_usd", "get", "overlap_report", "overlap_rows",
           "provider_configured", "register", "registered", "resolve"]
