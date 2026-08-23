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


#: Per-target credential prefixes. An Alpaca paper account is ONE account with
#: ONE equity curve, so two targets cannot share one set of keys without
#: writing two strategies into a single track record. The legacy lane keeps the
#: unprefixed variables it has always used; anything else needs its own.
CREDENTIAL_PREFIX = {"lane": "ALPACA", "arena": "ALPACA_ARENA"}


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

    @property
    def key_env(self) -> tuple[str, str]:
        """The env vars holding THIS target's Alpaca credentials."""
        pre = CREDENTIAL_PREFIX.get(self.kind, "ALPACA")
        return f"{pre}_API_KEY_ID", f"{pre}_API_SECRET_KEY"


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


@dataclass(frozen=True)
class Intent:
    """What the internal book will hold at the NEXT open, and when it decided.

    WHY THIS EXISTS AND `positions()` IS NOT ENOUGH
    ----------------------------------------------
    An arena book decides after the close and QUEUES orders for the next
    session's open; `positions()` reports what is already settled, which is the
    result of the PREVIOUS decision. Mirroring settled positions therefore
    executed each decision one session late:

        Mon 17:45  book decides BUY X, queued for Tue open
        Tue 09:30  the internal book's declared fill
        Tue 17:45  the internal book records that fill
        Wed 16:30  the mirror finally SEES X and submits
        Thu 09:30  the external account actually gets X

    Two sessions of drift, silently. The external account was not validating
    the strategy — it was validating a delayed variant of it, and every
    execution number measured against it would have been about the delay.

    So the broker mirrors ORDER INTENT: submitted after the decision, filling
    at the same open the internal book fills at. `decided_for` names that open,
    so a submission can be checked against the fill it was meant to catch.
    """

    shares: dict[str, float]
    basis: str                  # "intent" | "settled"
    decided_for: str | None     # decision date whose fill this intent targets
    pending_n: int


def intent(target: MirrorTarget, *, db_path=None, root=None) -> Intent:
    """Target holdings for the next open: settled positions plus queued orders.

    A lane has no queued-order concept in this adapter, so it reports its
    settled book with `basis="settled"` -- unchanged behaviour, named honestly
    rather than silently sharing a code path with something it is not.
    """
    settled = positions(target, db_path=db_path, root=root)
    if target.kind != "arena":
        return Intent(shares=settled, basis="settled", decided_for=None,
                      pending_n=0)

    from backend.services.arena import store
    book = store.read_positions(target.source_id, root)
    pending = list(book.get("pending") or [])
    if not pending:
        return Intent(shares=settled, basis="settled", decided_for=None,
                      pending_n=0)

    want = dict(settled)
    decided_for = None
    for o in pending:
        t = o.get("ticker")
        px = o.get("decision_close")
        usd = o.get("usd")
        decided_for = o.get("decision_date") or decided_for
        if not t or not px or not usd:
            # An order we cannot price is an order we cannot mirror. Carrying
            # the settled line for that name is the conservative reading: it
            # neither invents a position nor liquidates one on a missing field.
            logger.warning(
                "paper broker: pending order for %s on %s is unpriceable "
                "(close=%r usd=%r) — carrying the settled position instead",
                t, target.target_id, px, usd)
            continue
        delta = float(usd) / float(px)
        if str(o.get("side")).lower() == "sell":
            delta = -delta
        after = want.get(t, 0.0) + delta
        if after < -1e-9:
            # A short is not something this book can express, so clamping is
            # right — but a SILENT clamp is the house failure mode. If the
            # internal book ever queues a sell larger than the position, the
            # external account would go flat on that name while the internal
            # one went short, and the divergence would be blamed on execution.
            logger.error(
                "paper broker: %s queues a sell of %s taking the position to "
                "%.4f shares. Clamping to flat — the internal book and the "
                "external account will DIVERGE on this name.",
                target.target_id, t, after)
        want[t] = max(0.0, after)
    return Intent(shares={t: sh for t, sh in want.items() if sh > 0},
                  basis="intent", decided_for=decided_for,
                  pending_n=len(pending))


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


class SharedAccountRefused(RuntimeError):
    """Two targets would trade the same Alpaca account."""


def credentials(target: MirrorTarget) -> tuple[str, str] | None:
    """This target's keys, refusing a set shared with the legacy lane.

    THE HAZARD THIS REFUSES. `lane:mirror` has a live, third-party-verified
    equity curve going back to inception. If an arena book were pointed at the
    same account, the arena's orders would execute into that history and the
    mirror lane's verification -- the entire reason the integration exists --
    would silently become a record of two different strategies.

    So a non-legacy target must carry its OWN credentials. Falling back to the
    lane's would be the permissive direction, and the permissive direction here
    destroys a track record irreversibly.
    """
    kid, ksec = target.key_env
    k, s = os.getenv(kid, "").strip(), os.getenv(ksec, "").strip()
    if not (k and s):
        return None
    if not target.is_legacy_lane:
        lane_k = os.getenv("ALPACA_API_KEY_ID", "").strip()
        if lane_k and k == lane_k:
            raise SharedAccountRefused(
                f"{target.target_id} resolves to the SAME Alpaca account as "
                f"lane:mirror ({kid} matches ALPACA_API_KEY_ID). One account "
                f"has one equity curve: running both would execute this book's "
                f"orders into the mirror lane's third-party-verified history "
                f"and destroy it. Create a separate Alpaca PAPER account and "
                f"set {kid} / {ksec}.")
    return (k, s)


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
    try:
        creds = credentials(t)
        cred_state = "present" if creds else "absent"
        cred_error = None
    except SharedAccountRefused as e:
        cred_state, cred_error = "REFUSED", str(e)
    return {
        "status": "ok" if cred_state != "REFUSED" else "REFUSED",
        "target_id": t.target_id,
        "credentials": cred_state,
        "credential_env": list(t.key_env),
        "credential_error": cred_error,
        "kind": t.kind,
        "source_id": t.source_id,
        "is_legacy_lane": t.is_legacy_lane,
        "equity_key": t.equity_key,
        "declared_via": (TARGET_ENV if os.getenv(TARGET_ENV)
                         else f"default ({DEFAULT_TARGET})"),
    }
