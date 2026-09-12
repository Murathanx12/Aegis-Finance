"""Crash-safety for long night jobs: atomic checkpoints, resume, and a persistent
search state that lets a search ACCUMULATE across nights instead of replaying.

Why this file exists (2026-09-10). The PC died at 02:2x local while
`night_g3_evolve_v2` was 3.1 hours into a 5-hour box. The job holds its whole
result in memory and writes ONE receipt at exit, so the receipt said
`exited 1073807364 with no receipt` and the generation curve was gone.

Reconstructing the run from `G3_evaluations.jsonl` turned up the larger defect:
the crashed run was a **deterministic replay**. Both runs used seed 20260909 and
`bank_seed = seed + 1000 * gen`, so both drew the same window banks, initialised
the same population, and walked the same tree. Of the 541 distinct genomes the
crashed run evaluated, **541 were already in the earlier run's log** -- overlap
1.000, zero discovery. The earlier run had reached generation 436; the crashed
one died at 343, behind where the programme already was.

So there are two separate failures and this module addresses both:

1. **Crash safety** -- `Checkpoint`. State is written every generation with
   tmp + `os.replace`, which is atomic on Windows and POSIX alike, so a kill
   mid-write leaves the previous good checkpoint rather than a truncated file.
   A resume refuses if the configuration moved: a resumed run under different
   parameters is a different experiment wearing the first one's run number.

2. **Cross-night accumulation** -- `SearchState`. A persistent record of every
   bank seed ever used FOR SELECTION, plus the elites carried forward. Night
   n+1 seeds its population from night n's elites and draws banks the search
   has never selected on.

   The methodological trap this guards: once nights accumulate, an "out-of-bank"
   archive bank drawn at random will eventually collide with a bank some earlier
   night selected on, and the honesty of the whole archive rests on that bank
   being unseen. `SearchState.fresh_bank_seeds` therefore draws only from
   outside the union of every selection bank seed ever recorded, and
   `n_seeds_rejected_as_seen` travels in the receipt so the reader can see the
   guard firing rather than trust that it exists.

Nothing here runs a job, seals a book, or arms anything. It is state on disk.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_json", "rng_state_to_json", "rng_state_from_json",
           "Checkpoint", "SearchState"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict, *, indent: int | None = None) -> Path:
    """Write JSON so that a kill mid-write cannot destroy the previous version.

    `Path.write_text` truncates the target first, so an OS kill between truncate
    and flush leaves a zero-length checkpoint -- which is worse than no
    checkpoint, because a resume would load it and refuse. tmp + `os.replace`
    is atomic within a filesystem on both Windows and POSIX.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def rng_state_to_json(state: tuple) -> list:
    """`random.Random.getstate()` is `(version, tuple_of_625_ints, gauss_next)`.

    JSON has no tuples, so a naive round-trip returns lists and `setstate`
    raises `TypeError: state[1] must be a tuple`. Converted explicitly here so
    the failure cannot be discovered at 3am on a resume.
    """
    return [state[0], list(state[1]), state[2]]


def rng_state_from_json(blob: Any) -> tuple:
    return (blob[0], tuple(blob[1]), blob[2])


class Checkpoint:
    """Per-run crash state for one long job.

    `config` is the identity of the experiment. A resume whose config differs
    from the checkpoint's is REFUSED, not silently accepted: the run number and
    the receipt would claim continuity that does not exist.
    """

    def __init__(self, path: Path, config: dict):
        self.path = Path(path)
        self.config = dict(config)

    # ---- writing -----------------------------------------------------------
    def save(self, state: dict) -> Path:
        return atomic_write_json(self.path, {
            "kind": "night_checkpoint",
            "config": self.config,
            "written_utc": _now(),
            "state": state,
        })

    # ---- reading -----------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict:
        """Return the saved state, or raise with a reason a human can act on."""
        if not self.path.exists():
            raise FileNotFoundError(f"no checkpoint at {self.path}")
        try:
            blob = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"checkpoint at {self.path} is not readable JSON ({exc}); it was probably "
                f"killed mid-write by a build that did not use atomic_write_json. Delete it "
                f"and start fresh -- do not guess at its contents."
            ) from exc
        saved = blob.get("config") or {}
        drift = {k: (saved.get(k), v) for k, v in self.config.items() if saved.get(k) != v}
        if drift:
            raise ValueError(
                "REFUSED to resume: the configuration moved since the checkpoint. "
                + "; ".join(f"{k}: checkpoint {a!r} vs now {b!r}" for k, (a, b) in sorted(drift.items()))
                + ". A resume under different parameters is a different experiment. "
                  "Run without --resume to start a new run, or restore the parameters."
            )
        return blob.get("state") or {}

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class SearchState:
    """Search memory that survives the night, so night n+1 is not night n again.

    Two things persist and they do different jobs:

    * `bank_seeds_selected_on` -- every window-bank seed the search has ever
      earned a fitness against, across all nights. The archive re-score is only
      meaningful on a bank drawn from OUTSIDE this set, and once nights
      accumulate a random draw will collide with it.
    * `elites` -- the genomes carried into the next night's initial population,
      each with the median fitness it earned and how many banks it met.

    Carrying elites forward is selection carried across nights. That is
    permitted under PRODUCT_EXPERIMENT ("explore dirty, promote clean") and it
    is exactly what makes the search cumulative -- but it means the archive's
    out-of-bank claim is load-bearing, which is why the seed guard above is not
    optional.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        blob: dict = {}
        if self.path.exists():
            try:
                blob = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                blob = {}
        self.night_index: int = int(blob.get("night_index") or 0)
        self.bank_seeds_selected_on: set[int] = {int(s) for s in (blob.get("bank_seeds_selected_on") or [])}
        self.bank_seeds_archived_on: set[int] = {int(s) for s in (blob.get("bank_seeds_archived_on") or [])}
        self.elites: list[dict] = list(blob.get("elites") or [])
        self.history: list[dict] = list(blob.get("history") or [])
        self.loaded_from_disk: bool = bool(blob)

    # ---- bank seeds --------------------------------------------------------
    def fresh_bank_seeds(self, rng: random.Random, n: int, *, lo: int = 1, hi: int = 2 ** 31 - 1
                         ) -> tuple[list[int], int]:
        """`n` bank seeds no night has ever SELECTED on, plus the rejection count.

        The rejection count is returned rather than logged so the caller can put
        it in the receipt. A guard whose firing is invisible is a guard the next
        reader has to take on faith.
        """
        out: list[int] = []
        rejected = 0
        seen = set(self.bank_seeds_selected_on)
        guard = 0
        while len(out) < n:
            guard += 1
            if guard > 100_000 * max(n, 1):
                raise RuntimeError(
                    f"REFUSED: could not draw {n} unseen bank seeds after {guard} attempts; "
                    f"{len(seen)} seeds are already recorded as selected on. The seed space "
                    f"is exhausted or the recorded set is corrupt -- do not fall back to a seen seed."
                )
            s = rng.randint(lo, hi)
            if s in seen or s in out:
                rejected += 1
                continue
            out.append(s)
        return out, rejected

    def record_selection_banks(self, seeds) -> None:
        self.bank_seeds_selected_on.update(int(s) for s in seeds)

    def record_archive_banks(self, seeds) -> None:
        self.bank_seeds_archived_on.update(int(s) for s in seeds)

    # ---- elites ------------------------------------------------------------
    def seed_population(self, n: int) -> list[dict]:
        """The carried elites, best first, at most `n` of them. May be empty."""
        ranked = sorted(self.elites, key=lambda e: -(e.get("fitness") if e.get("fitness") is not None else -9e9))
        return [dict(e["genome"]) for e in ranked[:n] if e.get("genome")]

    def update_elites(self, rows: list[dict], keep: int = 24,
                      exclude_lineages=None) -> None:
        """Merge this night's rows into the carried elites, best-median first.

        A genome already carried keeps the row with MORE banks met, not the one
        with the better fitness: preferring the better number would be selection
        on the outcome, which is the error this repo has paid for more than once
        (`feedback_a_matched_control_must_not_be_picked_on_the_outcome`).

        `exclude_lineages` is E5's DEPRIORITIZED set (`scripts/
        night_stopping_rules.deprioritized_lineages`). A lineage whose deflated
        Sharpe did not clear the bar for how many genomes the search tried is
        not bred from again, and -- this is the half that is easy to miss -- it
        is also dropped from the elites ALREADY carried, or a lineage
        deprioritized tonight would go on parenting every future night out of
        state written before the verdict existed. Nothing is deleted: its
        evaluations stay in `G3_evaluations.jsonl` and its verdict stays in
        `G3_lineage_verdicts.jsonl`, so the exclusion is reversible by a later
        pass that reaches a different verdict.
        """
        banned = {str(x) for x in (exclude_lineages or ())}

        def _ok(e: dict) -> bool:
            return not banned or str(e.get("lineage") or "") not in banned

        by_key: dict[str, dict] = {e["key"]: e for e in self.elites
                                   if e.get("key") and _ok(e)}
        for r in rows:
            k = r.get("key")
            if not k or r.get("fitness") is None or not _ok(r):
                continue
            old = by_key.get(k)
            if old is None or (r.get("banks_met") or 0) > (old.get("banks_met") or 0):
                by_key[k] = r
        self.elites = sorted(by_key.values(),
                             key=lambda e: -(e.get("fitness") if e.get("fitness") is not None else -9e9))[:keep]

    # ---- persistence -------------------------------------------------------
    def close_night(self, summary: dict) -> Path:
        self.night_index += 1
        self.history.append({"night_index": self.night_index, "utc": _now(), **summary})
        return atomic_write_json(self.path, {
            "kind": "night_search_state",
            "night_index": self.night_index,
            "bank_seeds_selected_on": sorted(self.bank_seeds_selected_on),
            "bank_seeds_archived_on": sorted(self.bank_seeds_archived_on),
            "elites": self.elites,
            "history": self.history[-50:],
            "written_utc": _now(),
        }, indent=1)
