"""The Gym charter, as code rather than as a promise.

RULING R2. Historical data is the **Gym**; forward data is the sole
**certification** surface. Inside the Gym, aggressive search is licensed —
thousands of policy variants, counterfactual replay, evolutionary mutation,
deliberate overfitting in order to study what overfits. That licence is only
safe because three walls stand outside it, and a wall that lives in a document
is a wall that gets walked through at 2am by someone in a hurry.

  WALL 1  Nothing inside the Gym is evidence.
  WALL 2  Every search leaves a lineage row.
  WALL 3  Export requires transfer + pre-registration + forward certification.

WHY WALL 1 NEEDS A TYPE
=======================
"Do not quote Gym numbers in the README" is exactly the kind of rule that holds
for six weeks and then fails once, quietly, in a moment of enthusiasm — and the
failure is invisible, because a Gym number looks precisely like a real one.
`GymResult` therefore refuses to render itself as a claim. It carries its
numbers, it computes freely, and `as_claim()` raises. To publish a Gym number
you must first take it through `request_export`, which will tell you what is
missing.

The point is not that the type cannot be circumvented — anything can be
circumvented by someone determined. The point is that circumventing it requires
writing a line of code that says, unmistakably, what is being done.

WHY THE PARENT EPISODE IS BARRED
================================
An explanation is not knowledge because it explains its parent well. Any
mechanism discovered by staring at April 2020 will fit April 2020; that is what
"discovered by staring at it" means. So the episode that generated a hypothesis
is excluded from the evidence for it, by construction, in `TransferTest`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend import config as _config

logger = logging.getLogger(__name__)

GYM_DIR = _config.OPTIMUS_LEDGER_DIR / "research_gym"
LINEAGE_LEDGER = GYM_DIR / "lineage.jsonl"

CAMPAIGN = "RESEARCH-GYM-1"


class GymOutputIsNotEvidence(RuntimeError):
    """WALL 1. Raised when a Gym number is asked to behave like a finding."""


class ExportRefused(RuntimeError):
    """WALL 3. The mechanism has not earned its way out of the Gym."""


@dataclass
class GymResult:
    """A number produced inside the Gym. Freely computable, never citable."""
    name: str
    value: Any
    campaign: str = CAMPAIGN
    detail: dict = field(default_factory=dict)
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds"))

    def as_claim(self) -> str:
        raise GymOutputIsNotEvidence(
            f"{self.name!r} was produced inside {self.campaign}, where "
            f"overfitting is licensed and thousands of variants are tried. It "
            f"is a HYPOTHESIS, not a result, and it may not appear in a README "
            f"claim, a track-record surface or a funding argument. To publish "
            f"it: survive a transfer test on slices that generated none of it, "
            f"then pre-register, then certify forward. See request_export().")

    def __str__(self) -> str:                       # pragma: no cover - repr
        return (f"<GymResult {self.name}={self.value!r} "
                f"(hypothesis, not evidence)>")


# ── WALL 2: every search leaves a lineage row ───────────────────────────────

@dataclass
class LineageRow:
    """Why this candidate exists.

    `parent_id` plus `parent_failure` is the whole point: candidate N exists
    because candidate N−1 failed in a RECORDED way. A search whose rows say only
    "tried X, scored 0.3" is a leaderboard; one that says "tried X because Y
    lost its edge net of costs" is a record of reasoning, and only the second
    can be audited for the thing that actually matters — whether the search was
    hill-climbing on a single sample.
    """
    candidate_id: str
    campaign: str
    hypothesis: str
    parent_id: str | None = None
    parent_failure: str = ""
    params: dict = field(default_factory=dict)
    fitness: dict = field(default_factory=dict)
    n_episodes: int = 0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds"))

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["citable"] = False
        d["note"] = ("Gym lineage. Not evidence, not a result, never quoted. "
                     "R2 wall 2.")
        return d


def record_lineage(row: LineageRow, path: Path | None = None) -> None:
    """Append one lineage row. Returns None — nothing may branch on a write."""
    p = path or LINEAGE_LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row.as_dict(), ensure_ascii=False) + "\n")


def read_lineage(path: Path | None = None) -> list[dict]:
    """Every ledgered candidate, plus a placeholder for every unreadable one.

    A CORRUPT ROW MUST NOT VANISH.
    The lineage ledger is the denominator in §20: it is how this campaign
    reports its own multiple-comparison count. The previous version skipped
    unparseable lines with a bare `continue`, which means a truncated write
    would silently SHRINK the recorded search — in the direction that makes
    every deflation computed against it too generous, and with no trace.

    That is the same failure this whole module exists to prevent, sitting in
    the function that reports it. Unreadable rows are now counted and returned
    as explicit placeholders, so `unledgered_search_warning` sees them and a
    reader cannot mistake a damaged ledger for a small one.
    """
    p = path or LINEAGE_LEDGER
    if not p.exists():
        return []
    out, unreadable = [], 0
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            unreadable += 1
            out.append({"candidate_id": f"UNREADABLE:line{i + 1}",
                        "campaign": CAMPAIGN, "unreadable": True,
                        "error": f"{type(exc).__name__}: {exc}",
                        "citable": False})
    if unreadable:
        logger.error(
            "lineage ledger %s has %d unreadable row(s) — they are RETAINED as "
            "placeholders because dropping them would understate this "
            "campaign's search count (§20) and no deflation computed against "
            "it would be trustworthy", p, unreadable)
    return out


def unledgered_search_warning(n_candidates_tried: int,
                              path: Path | None = None) -> str | None:
    """§20 applied to the Gym: batches are checked against themselves.

    If more candidates were tried than were ledgered, the campaign's effective
    multiple-comparison count is unknown and every deflation computed from it
    understates. Saying so is cheap; discovering it afterwards is not.
    """
    n = len(read_lineage(path))
    if n_candidates_tried > n:
        return (f"{n_candidates_tried} candidates were tried and {n} are "
                f"ledgered — {n_candidates_tried - n} searches left no lineage "
                f"row, so this campaign's true multiple-comparison count is "
                f"UNKNOWN and any deflation against it understates")
    return None


# ── WALL 3: what it takes to leave ──────────────────────────────────────────

@dataclass
class TransferTest:
    """Evidence that a mechanism works where it was not discovered.

    `origin_episode_ids` are the episodes that GENERATED the hypothesis, and
    they are barred from proving it — not down-weighted, barred. A rule that
    only explains its parent is an overfit with a good story, and including the
    parent is how that becomes invisible.
    """
    mechanism: str
    origin_episode_ids: list[str]
    tested_episode_ids: list[str] = field(default_factory=list)
    slices: list[str] = field(default_factory=list)
    result_by_slice: dict = field(default_factory=dict)

    def contamination(self) -> set[str]:
        return set(self.origin_episode_ids) & set(self.tested_episode_ids)

    def is_clean(self) -> bool:
        return not self.contamination()

    def n_independent_slices_passed(self) -> int:
        return sum(1 for v in self.result_by_slice.values()
                   if isinstance(v, dict) and v.get("passed"))


#: A mechanism must survive on this many slices that generated none of it. Not
#: a magic number: it is the smallest count at which "it worked somewhere else"
#: cannot be one lucky period, and it matches the regime-block requirement the
#: execution standard already imposes on live candidates.
MIN_TRANSFER_SLICES = 3


def request_export(mechanism: str, transfer: TransferTest, *,
                   preregistration_id: str | None = None,
                   forward_certification_id: str | None = None) -> dict:
    """Can this leave the Gym? Returns the verdict and everything missing.

    Deliberately returns a REPORT rather than a boolean. "No" is not useful on
    its own; "no, because it has two clean slices and needs three, and has no
    pre-registration" is a work item.
    """
    missing: list[str] = []
    contaminated = transfer.contamination()
    if contaminated:
        missing.append(
            f"the transfer test includes {len(contaminated)} episode(s) that "
            f"GENERATED the hypothesis ({sorted(contaminated)[:3]}...) — the "
            f"parent may not prove the rule")
    passed = transfer.n_independent_slices_passed()
    if passed < MIN_TRANSFER_SLICES:
        missing.append(f"survived {passed} independent slice(s), needs "
                       f"{MIN_TRANSFER_SLICES}")
    if not preregistration_id:
        missing.append("no frozen pre-registration")
    if not forward_certification_id:
        missing.append("no forward certification — the Gym cannot certify "
                       "itself, and historical data is contaminated by "
                       "everything we have already learned from it (R8)")

    ok = not missing
    return {
        "mechanism": mechanism,
        "exportable": ok,
        "missing": missing,
        "transfer_clean": transfer.is_clean(),
        "slices_passed": passed,
        "slices_required": MIN_TRANSFER_SLICES,
        "verdict": ("EXPORTABLE — pre-registered and forward-certified"
                    if ok else "REFUSED — " + "; ".join(missing)),
    }


def assert_exportable(mechanism: str, transfer: TransferTest, **kw) -> dict:
    """`request_export`, but raising. For call sites about to publish."""
    rep = request_export(mechanism, transfer, **kw)
    if not rep["exportable"]:
        raise ExportRefused(rep["verdict"])
    return rep
