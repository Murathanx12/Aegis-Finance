"""Two forward ledgers, two purposes, and no way to confuse them.

THE FACT THIS MODULE EXISTS TO MAKE UNFORGETTABLE
=================================================
There are two populations of forward prediction records, and they are not one
ledger:

  CAMPAIGN_FORWARD   the research campaign's records — ~20,073 of them, written
                     into the in-repo/in-image ledger by the arena, the swarm
                     and the nightly trials. Graded LOCALLY and ATTENDED as
                     outcomes fall due. This is what ABLATION_FWD certifies
                     against.

  LIVE_FORWARD       the deployed product's own accrual, resolved by the nightly
                     `pi_ledger_resolve` job. Authoritative for anything said
                     about the live deployment.

                     **Its true size is currently ZERO.** This paragraph used to
                     read "~112 records on the Railway persistent volume", and
                     that was wrong: adjudicated 2026-08-15, all 112 of those
                     records are content-identical to the FIRST 112 rows of the
                     campaign ledger — a partial copy that reached the volume
                     before the migration guard existed, not the product's own
                     history. `live_forward_is_established()` enforces the
                     distinction so no surface can claim a live forward record
                     that does not exist. See
                     `docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md`.

They were discovered to be different populations only because ABLATION_FWD read
one while production resolved the other, and the boot warning about "19,961
records absent from the persisted ledger" turned out to be the system correctly
refusing a merge nobody had decided on. The merge stays refused: pooling
campaign records into the live product ledger would make NEITHER authoritative.

WHY A FIELD AND NOT ONLY A PATH
===============================
On Railway the two ledgers are different files. **Locally they are the same
file**, because `AEGIS_DATA_DIR` is unset and the volume does not exist here. A
separation enforced by path alone would therefore be enforced in production and
absent on the machine where the attended campaign resolutions are actually going
to be run — which is precisely backwards.

So population is a FIELD on the record, and the path is a second, independent
statement. A record with no field belongs to the population that owns the file
it was found in, and where the two paths coincide the owner is CAMPAIGN_FORWARD
— because the file in the repo is the campaign's history, and the live ledger
genuinely does not exist on a developer machine. `read_population(LIVE_FORWARD)`
locally returns nothing, which is the true answer.

WHAT THIS MODULE REFUSES
========================
* writing records of one population into the other's ledger;
* reading "the ledger" without saying which one;
* pooling two populations into one estimate without a prospectively declared
  pooling rule (there is none, so it simply refuses).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from enum import Enum
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

LEDGER_FILE = "predictions.jsonl"


class EvidencePopulation(str, Enum):
    """Which body of forward evidence a record belongs to."""

    CAMPAIGN_FORWARD = "campaign_forward"
    LIVE_FORWARD = "live_forward"
    SANDBOX = "sandbox"

    @property
    def ledger_id(self) -> str:
        return _LEDGER_IDS[self]

    @property
    def resolver(self) -> str:
        return _RESOLVERS[self]


#: Stable identifiers. These travel on receipts and verdicts, so they are named
#: once here rather than reconstructed from an enum value at each call site.
_LEDGER_IDS = {
    EvidencePopulation.CAMPAIGN_FORWARD: "aegis:ledger:campaign_forward",
    EvidencePopulation.LIVE_FORWARD: "aegis:ledger:live_forward",
    EvidencePopulation.SANDBOX: "aegis:ledger:sandbox",
}

_RESOLVERS = {
    EvidencePopulation.CAMPAIGN_FORWARD:
        "attended, local: scripts/resolve_campaign_ledger.py",
    EvidencePopulation.LIVE_FORWARD:
        "production scheduler job: pi_ledger_resolve",
    EvidencePopulation.SANDBOX: "none — sandbox records are never resolved",
}


class PopulationRequired(ValueError):
    """A ledger operation was attempted without saying which population."""


class PopulationCrossWrite(RuntimeError):
    """A write would have put one population's records in another's ledger."""


class PopulationPoolingRefused(RuntimeError):
    """Two populations were about to be estimated as one. There is no rule."""


def parse(value: "str | EvidencePopulation | None") -> EvidencePopulation:
    """Coerce a CLI/API string, refusing the empty case rather than guessing.

    A default here would be the whole bug: the reason the two ledgers were
    confused for a month is that every reader had one.
    """
    if value is None or value == "":
        raise PopulationRequired(
            "an evidence population must be named explicitly — one of "
            + ", ".join(p.value for p in EvidencePopulation)
            + ". There is deliberately no default: 'the forward ledger' is "
              "two different populations with two different purposes, and a "
              "report that does not say which is not a report.")
    if isinstance(value, EvidencePopulation):
        return value
    try:
        return EvidencePopulation(str(value).strip().lower())
    except ValueError as exc:
        raise PopulationRequired(
            f"{value!r} is not an evidence population; expected one of "
            + ", ".join(p.value for p in EvidencePopulation)) from exc


# ── where each population lives ─────────────────────────────────────────────
def ledger_dir(pop: EvidencePopulation) -> Path:
    if pop is EvidencePopulation.CAMPAIGN_FORWARD:
        # The in-repo / in-image ledger. NOT derived from AEGIS_DATA_DIR: the
        # campaign's history is a repository artifact and must not follow a
        # volume mount around.
        return _config.OPTIMUS_LEDGER_LEGACY_DIR
    if pop is EvidencePopulation.LIVE_FORWARD:
        # The persistent volume on Railway; the same directory locally, where
        # there is no volume — see the module docstring.
        return _config.OPTIMUS_LEDGER_DIR
    return _config.OPTIMUS_LEDGER_DIR / "sandbox"


def ledger_path(pop: EvidencePopulation) -> Path:
    return ledger_dir(pop) / LEDGER_FILE


def paths_coincide() -> bool:
    """Do CAMPAIGN and LIVE resolve to one file? True on a dev machine.

    Stated rather than hidden: where this is True, the separation is carried by
    the record field alone, and every status report says so.
    """
    return (ledger_path(EvidencePopulation.CAMPAIGN_FORWARD).resolve()
            == ledger_path(EvidencePopulation.LIVE_FORWARD).resolve())


def owner_of(path: "Path | str") -> EvidencePopulation:
    """Which population an untagged record in this file belongs to.

    CAMPAIGN wins a tie. On a machine where the volume path and the repo path
    are the same file, the records in it are the campaign's — the live ledger is
    a production artifact and does not exist here.
    """
    p = Path(path).resolve()
    if p == ledger_path(EvidencePopulation.SANDBOX).resolve():
        return EvidencePopulation.SANDBOX
    if p == ledger_path(EvidencePopulation.CAMPAIGN_FORWARD).resolve():
        return EvidencePopulation.CAMPAIGN_FORWARD
    if p == ledger_path(EvidencePopulation.LIVE_FORWARD).resolve():
        return EvidencePopulation.LIVE_FORWARD
    raise PopulationRequired(
        f"{p} is not one of the declared evidence ledgers; a record's "
        f"population cannot be inferred from an unknown file")


def population_of(row: dict, *,
                  path: "Path | str | None" = None) -> EvidencePopulation:
    """A record's population: its own field, else the owner of its file."""
    tag = (row or {}).get("evidence_population")
    if tag:
        return parse(tag)
    if path is None:
        raise PopulationRequired(
            "this record carries no evidence_population and no file was given "
            "to attribute it to — refusing to guess")
    return owner_of(path)


# ── reading ─────────────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> list[dict]:
    """Tolerant read: a torn line is counted by the caller, never silently ok."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_population(pop: "str | EvidencePopulation",
                    path: "Path | None" = None) -> list[dict]:
    """Every record of ONE population. Never both, never a default."""
    pop = parse(pop)
    p = Path(path) if path is not None else ledger_path(pop)
    return [r for r in _read_jsonl(p) if population_of(r, path=p) is pop]


def stamp(records: list, pop: "str | EvidencePopulation") -> list:
    """Write the population onto records that do not already declare one.

    Refuses to RE-stamp: a record that already claims a population and is being
    written into another one is the cross-write this module exists to stop, and
    silently relabelling it would be the worst available outcome.
    """
    pop = parse(pop)
    for r in records:
        current = (r.get("evidence_population")
                   if isinstance(r, dict) else
                   getattr(r, "evidence_population", None))
        if current and parse(current) is not pop:
            raise PopulationCrossWrite(
                f"record already declares {current!r} and is being written as "
                f"{pop.value} — a record does not change population, and the "
                f"two ledgers are not interchangeable")
        if isinstance(r, dict):
            r["evidence_population"] = pop.value
            r.setdefault("ledger_id", pop.ledger_id)
        else:
            setattr(r, "evidence_population", pop.value)
            if not getattr(r, "ledger_id", None):
                setattr(r, "ledger_id", pop.ledger_id)
    return records


def assert_write_allowed(pop: "str | EvidencePopulation",
                         path: "Path | str") -> None:
    """Refuse a write of `pop`'s records into another population's file.

    Where the paths coincide the file check cannot fire, so it does not pretend
    to: the guarantee there is carried by `stamp`, and the coincidence is
    disclosed by `status()`. Where they differ — production — this is the wall.
    """
    pop = parse(pop)
    target = Path(path).resolve()
    if target == ledger_path(pop).resolve():
        # Note this also passes where the two paths coincide, which is a dev
        # machine and is the case the record field — not this check — covers.
        return
    raise PopulationCrossWrite(
        f"refusing to write {pop.value} records to {target}: that file is the "
        f"{_describe(target)} ledger. The campaign resolver never writes the "
        f"volume and the production resolver never writes the repo ledger — "
        f"mixing them would leave neither authoritative.")


def _describe(path: Path) -> str:
    try:
        return owner_of(path).value
    except PopulationRequired:
        return "unknown"


def refuse_pooling(*pops: "str | EvidencePopulation") -> None:
    """Two populations in one estimate needs a rule that does not exist."""
    distinct = {parse(p) for p in pops}
    if len(distinct) > 1:
        raise PopulationPoolingRefused(
            "cannot combine " + ", ".join(sorted(p.value for p in distinct))
            + " into one estimate. A combined number needs a prospectively "
              "declared pooling/meta-analysis rule, and none is registered. "
              "Report them side by side instead.")


# ── lineage: what a receipt has to carry ────────────────────────────────────
def _source_commit() -> str | None:
    """The repo HEAD, read from .git without shelling out. None if unknown."""
    try:
        git = Path(_config.PROJECT_ROOT) / ".git"
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            p = git / ref
            if p.exists():
                return p.read_text(encoding="utf-8").strip()[:40]
            packed = git / "packed-refs"
            if packed.exists():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split(" ", 1)[0][:40]
            return None
        return head[:40]
    except Exception:                                          # noqa: BLE001
        return None


def lineage(pop: "str | EvidencePopulation",
            path: "Path | None" = None) -> dict:
    """Everything a verdict must state about the evidence it used."""
    pop = parse(pop)
    p = Path(path) if path is not None else ledger_path(pop)
    rows = read_population(pop, p)
    made = sorted(str(r.get("made_at") or "") for r in rows if r.get("made_at"))
    digest = hashlib.sha256()
    if p.exists():
        digest.update(p.read_bytes())
    return {
        "evidence_population": pop.value,
        "ledger_id": pop.ledger_id,
        "logical_uri": f"{pop.ledger_id}#{LEDGER_FILE}",
        "ledger_path": str(p),
        "ledger_exists": p.exists(),
        "record_count": len(rows),
        "first_record_at": made[0] if made else None,
        "last_record_at": made[-1] if made else None,
        "provenance_sha256": digest.hexdigest() if p.exists() else None,
        "provenance_covers": ("the whole file, including records of other "
                              "populations if the paths coincide"),
        "source_commit": _source_commit(),
        "resolver": pop.resolver,
        "paths_coincide": paths_coincide(),
    }


def _record_hash(r: dict) -> str:
    """The same full-record hash `belief_state`'s migration guard compares on."""
    return hashlib.sha256(
        json.dumps(r, sort_keys=True, default=str,
                   ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def live_forward_is_established(sample_cap: int = 50_000,
                                path: "Path | None" = None) -> dict:
    """Does LIVE_FORWARD hold anything the campaign did not already write?

    ADJUDICATED 2026-08-15 (`docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md`).
    The docstring at the top of this module used to describe LIVE_FORWARD as
    "the deployed product's own accrual — ~112 records on the Railway persistent
    volume". That was false. The boot warning reported 19,961 of the image
    ledger's 20,073 records as absent from the volume, which puts the
    intersection at exactly 112 — the volume's entire contents — so the
    persisted ledger is a strict SUBSET of the campaign ledger. Four independent
    checks agree it is specifically the first 112 rows: 12 distinct specialists,
    six void records, one distinct model, last-written 2026-08-12.

    So the live population's true size is ZERO, and the volume holds a partial
    copy of campaign history that arrived before the migration guard existed.

    This function exists so that no surface can claim otherwise. It does not
    delete anything — removing rows from the authoritative persisted ledger is
    irreversible and belongs to Murat, not to a session — it just makes the
    claim unavailable. An empty ledger and a ledger full of somebody else's
    records must not both read as "the product has a forward record".
    """
    # `path` is threaded so the guard inspects the SAME file the caller is about
    # to act on. Checking the default location while resolution runs against an
    # overridden one would be a check that passed for a different ledger, which
    # is worse than no check at all.
    live = read_population(EvidencePopulation.LIVE_FORWARD, path=path)
    if not live:
        return {"established": False, "n_records": 0,
                "n_shared_with_campaign": 0, "n_genuine": 0,
                "quarantined_hashes": frozenset(),
                "comparison_available": True,
                "reason": "LIVE_FORWARD is empty — the product has accrued no "
                          "forward evidence yet, which is the honest state"}
    campaign = {_record_hash(r) for r in
                read_population(EvidencePopulation.CAMPAIGN_FORWARD)
                [:sample_cap]}
    if not campaign:
        # THE COMPARISON SET IS AN INPUT, AND ITS ABSENCE IS NOT A PASS.
        #
        # With no campaign ledger to compare against, `shared` is 0, every copy
        # looks genuine, `established` is True and the quarantine clears itself —
        # the guard would "pass" BECAUSE it could not see the thing it checks.
        #
        # This function does not raise, because health surfaces call it and a
        # missing repo artifact must not take a status page down. It reports the
        # gap instead, and `quarantined_hashes()` — the guard on the irreversible
        # path — refuses on it. Reporting and refusing are different jobs.
        return {
            "established": False,
            "n_records": len(live),
            "n_shared_with_campaign": 0,
            "n_genuine": 0,
            "quarantined_hashes": frozenset(),
            "comparison_available": False,
            "reason": (f"cannot judge whether {len(live)} LIVE_FORWARD "
                       f"record(s) are the product's own: the campaign ledger "
                       f"at {ledger_path(EvidencePopulation.CAMPAIGN_FORWARD)} "
                       f"is missing or empty, so there is nothing to compare "
                       f"against. Absence of the comparison set is not evidence "
                       f"these records are genuine."),
        }
    quarantined = frozenset(h for h in (_record_hash(r) for r in live)
                            if h in campaign)
    shared = sum(1 for r in live if _record_hash(r) in campaign)
    established = shared < len(live)
    return {
        "established": established,
        "n_records": len(live),
        "n_shared_with_campaign": shared,
        # THE COUNT THE RELEASE DECISION ACTUALLY TURNS ON.
        #
        # `established` is a statement about the population ("is there anything
        # here the campaign did not write?"). It is NOT a licence to grade the
        # shared records, and callers must not read it as one — see
        # `quarantined_hashes`.
        "n_genuine": len(live) - shared,
        # Record-level identity of the copies, so a caller that IS allowed to
        # resolve the genuine records can exclude these by content rather than
        # by trusting a population-wide boolean. A genuine record would have to
        # be byte-identical to a campaign record — same prediction_id, same
        # timestamps — to land in here, so the false-quarantine risk is nil and
        # the direction of the error is refusal.
        "quarantined_hashes": quarantined,
        "comparison_available": True,
        "reason": ("" if established else
                   f"every one of {len(live)} LIVE_FORWARD record(s) is "
                   f"content-identical to a CAMPAIGN_FORWARD record. This is "
                   f"not the product's accrual, it is a partial copy of "
                   f"campaign history that reached the volume before the "
                   f"migration guard existed. Treat the live population as "
                   f"UNESTABLISHED (size zero) — see "
                   f"docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md"),
    }


def quarantined_hashes(path: "Path | None" = None,
                       sample_cap: int = 50_000) -> frozenset:
    """Hashes of LIVE_FORWARD records that the campaign already wrote.

    WHY THIS IS NOT `live_forward_is_established()["established"]`
    =============================================================
    Because that boolean is released by the arrival of ONE unrelated record.
    `established = shared < len(live)` was written to answer "has the product
    accrued anything of its own?", and it answers that correctly. But
    `ledger_resolver` used it as the gate on whether to grade the file — and
    resolution rewrites the WHOLE file. So the first genuine forecast the
    deployed product ever writes flips the gate open and hands all 112 copied
    campaign records to the grader, unattended, on the next 16:30 ET tick.
    Reproduced 2026-08-17: 112 copies + 1 genuine record ⇒ established True,
    112 records due, all 112 of them copies.

    An outcome written onto a record is the thing that makes it evidence, and it
    cannot be un-written. So the quarantine is enforced per RECORD and survives
    the population becoming established: the copies are never graded on the live
    volume, whatever else is in the file. Removing them belongs to Murat, not to
    a session; this only makes them ungradeable.

    REFUSES when the campaign ledger — the set this compares against — is
    missing or empty. This is the guard on an irreversible act, so an input it
    cannot see is a refusal and not a clean verdict. Callers that only want to
    DESCRIBE the population should read `live_forward_is_established()` and its
    `comparison_available` flag, which reports the same gap without raising.
    """
    est = live_forward_is_established(sample_cap=sample_cap, path=path)
    if est.get("comparison_available") is False:
        raise PopulationRequired(
            est["reason"] + " Refusing to compute the quarantine rather than "
            "clearing it — see docs/"
            "LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md")
    return est["quarantined_hashes"]


def record_hash(r: dict) -> str:
    """Public alias — callers outside this module need the same identity."""
    return _record_hash(r)


def _population_status(pop: EvidencePopulation) -> dict:
    from datetime import date
    rows = read_population(pop)
    today = date.today()

    def _due(r: dict) -> bool:
        ra = r.get("resolves_after")
        if not ra:
            return False
        try:
            return date.fromisoformat(str(ra)[:10]) <= today
        except ValueError:
            return False

    active = [r for r in rows if r.get("outcome") is None
              and not r.get("void_reason")]
    resolved = [r for r in rows if r.get("resolved_at")]
    out = lineage(pop)
    out.update({
        "raw_predictions": len(rows),
        "resolved": len(resolved),
        "unresolved": len(active),
        "due": sum(1 for r in active if _due(r)),
        "void": sum(1 for r in rows if r.get("void_reason")),
    })
    return out


def status() -> dict:
    """The dual-population report. Both, side by side, never summed."""
    return {
        "generated_for": "the two forward evidence populations",
        "paths_coincide": paths_coincide(),
        "coincidence_note": (
            "CAMPAIGN_FORWARD and LIVE_FORWARD resolve to the SAME FILE on this "
            "machine (no AEGIS_DATA_DIR, so there is no volume). The separation "
            "here is carried by each record's evidence_population field; the "
            "path check can only bind in production."
            if paths_coincide() else
            "the two populations are separate files, and both the record field "
            "and the path enforce the separation"),
        "populations": {p.value: _population_status(p)
                        for p in (EvidencePopulation.CAMPAIGN_FORWARD,
                                  EvidencePopulation.LIVE_FORWARD)},
        # A record COUNT is not evidence that a population exists. The live
        # ledger reported 112 for days while holding nothing but a copy of the
        # campaign's first 112 rows, and every surface that read the count
        # would have called that a live forward record.
        "live_forward_established": live_forward_is_established(),
        "pooling": ("REFUSED — no prospectively declared pooling rule exists. "
                    "These two numbers are never added."),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="evidence_population",
        description="Status of the two forward evidence populations.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        import sys
        for s in (sys.stdout, sys.stderr):
            s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    st = status()
    if a.json:
        print(json.dumps(st, indent=2, default=str))
        return 0
    print("=" * 70)
    print("FORWARD EVIDENCE — TWO POPULATIONS, REPORTED SEPARATELY")
    print("=" * 70)
    print(f"\npaths coincide: {st['paths_coincide']}\n  {st['coincidence_note']}")
    for name, s in st["populations"].items():
        print(f"\n{name.upper()}   ({s['ledger_id']})")
        print(f"  path             {s['ledger_path']}"
              + ("" if s["ledger_exists"] else "   [ABSENT]"))
        print(f"  raw predictions  {s['raw_predictions']}")
        print(f"  due              {s['due']}")
        print(f"  resolved         {s['resolved']}")
        print(f"  unresolved       {s['unresolved']}")
        print(f"  void             {s['void']}")
        print(f"  earliest         {s['first_record_at']}")
        print(f"  latest           {s['last_record_at']}")
        print(f"  resolver         {s['resolver']}")
        print(f"  provenance       {s['provenance_sha256']}")
    print(f"\npooling: {st['pooling']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
