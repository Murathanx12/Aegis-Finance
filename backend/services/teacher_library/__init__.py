"""TEACHER-LIBRARY-1 — public actors as a data class.

Two things live under this package and they are NOT the same thing:

  TEACHER-LIBRARY   research substrate. Canonical events, actor behaviour,
                    mechanisms. Claims require independent Aegis testing and a
                    pre-registration before any number grades a hypothesis.

  COPY-LAB          forward experimental PAPER portfolios. Product-oriented,
                    may run before statistical certification, and is labelled
                    EXPERIMENTAL / NOT VALIDATED ALPHA wherever it is shown.

The rule that binds both: `public_at` is the only timestamp a copy strategy or
a backtest may enter on. Entering at the transaction date measures a portfolio
nobody could have held.

Nothing in this package joins an event to an outcome. That is deliberate — the
moment a number could grade a hypothesis, `pre-register-trial` comes first.
"""

from .events import (ACTION_TYPES, ACTOR_TYPES, OK_DATA, OK_EMPTY, UNAVAILABLE,
                     TeacherEvent, TeacherEventInvalid, sha256_of)

__all__ = ["TeacherEvent", "TeacherEventInvalid", "ACTOR_TYPES",
           "ACTION_TYPES", "OK_DATA", "OK_EMPTY", "UNAVAILABLE", "sha256_of"]
