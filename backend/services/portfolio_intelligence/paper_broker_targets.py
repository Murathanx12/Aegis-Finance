"""What the external PAPER broker is allowed to mirror, and where it reads it.

WHY THIS EXISTS
===============
`alpaca_mirror` was built to do one job: replicate the legacy `mirror` lane into
an Alpaca PAPER account so a third party computes that lane's equity curve. It
hard-codes `MIRRORED_LANE = "mirror"` and reads the lane SQLite tables.

Meanwhile the arena grew ten books that make daily decisions under frozen
information states -- the actual continuously-learning engine -- and NONE of
them could reach the external paper account. The brain and the paper broker
were both built and never joined. That is the gap this module closes.

THE ONE-ACCOUNT CONSTRAINT
==========================
An Alpaca paper account is ONE account with ONE equity curve. Ten books cannot
share it. So mirroring is a DECLARED CHOICE of exactly one target, named in the
environment, and changing it is a policy event -- not something a deploy does
by accident.

WHAT IS DELIBERATELY REFUSED
============================
* **Silent redirection of the legacy `mirror` lane.** The default target is
  `lane:mirror` and stays byte-identical to the old behaviour. A lane with a
  live third-party-verified history does not get repointed at a different
  strategy because a new feature shipped.
* **Real money.** Targets are paper-only; the host refusal lives in
  `alpaca_mirror` and is unchanged.
* **An unknown target.** An unparseable or unregistered target REFUSES rather
  than falling back to a default, because a typo that silently mirrors the
  wrong book would corrupt a track record with no error anywhere.

ACTIVATION
==========
Set `AEGIS_PAPER_BROKER_TARGET=arena:CURRENT_BEST_v1` (or any seeded book id).
Seeding remains attended and env-gated exactly as before.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass


logger = logging.getLogger(__name__)

#: The environment variable that declares the single mirrored target.
TARGET_ENV = "AEGIS_PAPER_BROKER_TARGET"

#: Unset means the legacy behaviour, unchanged. This default is load-bearing:
#: the `mirror` lane has a live third-party-verified history and must keep it.
DEFAULT_TARGET = "lane:mirror"


class UnknownTarget(ValueError):
    """A declared mirror target that cannot be resolved. Never defaulted."""


class TargetNotSeeded(RuntimeError):
    """The internal source has no positions to mirror yet."""


@dataclass(frozen=True)
class MirrorTarget:
    """One mirrorable internal book, and how to read its state."""

    target_id: str
    kind: str                    # "lane" | "arena"
    source_id: str               # lane portfolio_id, or arena book_id
    #: PIT keys are namespaced per target so two targets can never write over
    #: each other's third-party equity history.
    equity_key: str
    state_key: str
    trial_param: str
    purpose: str

    @property
    def is_legacy_lane(self) -> bool:
        return self.target_id == DEFAULT_TARGET


def _lane_target(lane: str) -> MirrorTarget:
    # The legacy lane keeps its ORIGINAL, un-namespaced keys. Renaming them
    # would orphan the equity history this whole adapter exists to record.
    legacy = lane == "mirror"
    return MirrorTarget(
        target_id=f"lane:{lane}",
        kind="lane",
        source_id=lane,
        equity_key="alpaca:equity" if legacy else f"alpaca:equity:lane:{lane}",
        state_key=("alpaca:mirror_state" if legacy
                   else f"alpaca:mirror_state:lane:{lane}"),
        trial_param=("alpaca-mirror-verification" if legacy
                     else f"alpaca-mirror-verification:lane:{lane}"),
        purpose=("Third-party NAV verification: Alpaca PAPER account "
                 f"replicates the `{lane}` lane's open positions."),
    )


def _arena_target(book_id: str) -> MirrorTarget:
    return MirrorTarget(
        target_id=f"arena:{book_id}",
        kind="arena",
        source_id=book_id,
        equity_key=f"alpaca:equity:arena:{book_id}",
        state_key=f"alpaca:mirror_state:arena:{book_id}",
        trial_param=f"alpaca-paper-execution:arena:{book_id}",
        purpose=("External PAPER execution of arena book "
                 f"`{book_id}`: a third party fills the orders the internal "
                 "book decided, so execution assumptions are measured rather "
                 "than assumed. PRODUCT_EXPERIMENT -- never validated alpha."),
    )


def parse_target(raw: str | None = None) -> MirrorTarget:
    """Resolve the declared target. Refuses the unknown; never guesses."""
    value = (raw if raw is not None
             else os.getenv(TARGET_ENV, "")).strip() or DEFAULT_TARGET
    if ":" not in value:
        raise UnknownTarget(
            f"{TARGET_ENV}={value!r} is not a target. Use 'lane:<lane_id>' or "
            f"'arena:<BOOK_ID>'. Refusing rather than defaulting, because a "
            f"typo that silently mirrored the wrong book would corrupt a "
            f"track record with no error anywhere.")
    kind, _, source = value.partition(":")
    kind, source = kind.strip().lower(), source.strip()
    if not source:
        raise UnknownTarget(f"{TARGET_ENV}={value!r} names no source id")
    if kind == "lane":
        return _lane_target(source)
    if kind == "arena":
        return _arena_target(source)
    raise UnknownTarget(
        f"{TARGET_ENV}={value!r}: unknown kind {kind!r}. Known: lane, arena.")


# ------------------------------------------------------------- state reads


def positions(target: MirrorTarget, *, db_path=None,
              root=None) -> dict[str, float]:
    """Open positions of the internal source: {ticker: shares}."""
    if target.kind == "lane":
        from backend.db import get_connection
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT ticker, shares FROM paper_positions "
                "WHERE portfolio_id = ? AND closed_at IS NULL",
                (target.source_id,),
            ).fetchall()
        finally:
            conn.close()
        return {r["ticker"]: float(r["shares"]) for r in rows
                if float(r["shares"]) > 0}

    from backend.services.arena import store
    book = store.read_positions(target.source_id, root)
    out: dict[str, float] = {}
    for ticker, pos in (book.get("positions") or {}).items():
        shares = float((pos or {}).get("shares") or 0.0)
        if shares > 0:
            out[ticker] = shares
    return out


def nav(target: MirrorTarget, *, db_path=None, root=None) -> float | None:
    """Latest internal NAV of the source, or None if it has never been marked."""
    if target.kind == "lane":
        from backend.db import get_connection
        conn = get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT nav FROM paper_nav WHERE portfolio_id = ? "
                "ORDER BY date DESC LIMIT 1", (target.source_id,),
            ).fetchone()
        finally:
            conn.close()
        return float(row["nav"]) if row else None

    from backend.services.arena import store
    rows = store.read_nav(target.source_id, root)
    if not rows:
        return None
    # NAV rows are appended in session order; the last one is the current mark.
    last = rows[-1]
    value = last.get("nav")
    return float(value) if value is not None else None


def annotation(target: MirrorTarget) -> dict:
    """The registry row, so the lane-adjacent ledger stays complete."""
    return {
        "kind": "infrastructure",
        "purpose": target.purpose,
        "target_id": target.target_id,
        "source_kind": target.kind,
        "source_id": target.source_id,
        "paper_only": True,
        "real_capital": False,
        "doc": ("backend/services/portfolio_intelligence/"
                "paper_broker_targets.py docstring"),
    }


def describe(target: MirrorTarget | None = None) -> dict:
    """Health/diagnostic row: what is declared, and is it even resolvable."""
    try:
        t = target or parse_target()
    except UnknownTarget as e:
        return {"status": "REFUSED", "declared": os.getenv(TARGET_ENV),
                "error": str(e)}
    return {
        "status": "ok",
        "target_id": t.target_id,
        "kind": t.kind,
        "source_id": t.source_id,
        "is_legacy_lane": t.is_legacy_lane,
        "equity_key": t.equity_key,
        "declared_via": (TARGET_ENV if os.getenv(TARGET_ENV)
                         else f"default ({DEFAULT_TARGET})"),
    }
