"""CH-46d -- the embeddings classifier's REJECT as a DEMOTION filter for the ticker hub.

WHY
===
CH-46 (`news_entity_embed.py`) failed as a PROMOTER (the promotions it would make on untitled
rows were right 2 of 30 on the builder's hand read), while its REJECTIONS of the hub's
body-match / digest `mentions` tags were right 29 of 30. This module holds the pure pieces a
hub would need to HIDE such tags, and the evaluation script (`scripts/news_tag_demotion.py`)
measures whether that is safe.

WHAT IT MAY TOUCH
=================
Only a hub tag with ``tier == "mentions"`` that came from an article-body name match
(``where == "body"``) or a world-digest ticker (``m == "digest_typed"``). An ``about``-tier
tag (title names the company, or an SEC filing by CIK) is NEVER hidden, whatever the sidecar
says; a provider / reader-lane tag is never hidden; a tag is never ADDED.

LANGUAGE GATE
=============
The encoder (bge-small-en) is English-only, so a row whose text is mostly non-Latin script
(`llm_language.non_latin_share > NON_LATIN_BAR`) is routed to ``uncertain`` before any
decision: it is neither demoted nor promoted.

SIDECAR
=======
``news_tag_demotion_sidecar.jsonl``, one line per tag to hide:
``{"schema", "row_id", "ticker", "action": "hide", "score", "threshold", "variant",
"classifier", "model", "declaration_sha"}`` -- ids, tickers and numbers, no text. ``row_id`` is
``ticker_hub.row_id``. `read_sidecar` refuses a missing file or a line of another schema
(`DemotionRefused`, a red exit in the CLI); `apply_demotions` is the function a hub would call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from backend import config as C
from backend.services import llm_language as L

SCHEMA = "news-tag-demotion/1"

SIDECAR_MISSING = "SIDECAR_MISSING"
SIDECAR_BAD_SCHEMA = "SIDECAR_BAD_SCHEMA"

#: per-tag decisions of `decide_demotion`
REJECT = "reject"
KEEP = "keep"
UNCERTAIN_LANGUAGE = "uncertain_language"
UNSCORED = "unscored"


class DemotionRefused(RuntimeError):
    """The demotion sidecar cannot be read (missing, or a line of another schema)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fields(tag: Any) -> tuple[str, str, Optional[str], Optional[str]]:
    """(ticker, method, tier, where) from a hub tag dict ``{t, m, tier, where}`` or the
    CH-46 list form ``[t, m, tier, where]``."""
    if isinstance(tag, Mapping):
        return (str(tag.get("t") or ""), str(tag.get("m") or ""), tag.get("tier"), tag.get("where"))
    t = list(tag) + [None] * 4
    return (str(t[0] or ""), str(t[1] or ""), t[2], t[3])


def is_demotable(tag: Any) -> bool:
    """True only for a body-match or digest `mentions` tag. `about` is never demotable."""
    _t, m, tier, where = _fields(tag)
    return tier == "mentions" and (where == "body" or m == "digest_typed")


def non_english(text: str, bar: Optional[float] = None) -> bool:
    """The language gate: more than `bar` (default the house NON_LATIN_BAR) of the letters
    sit in a non-Latin script."""
    return L.non_latin_share(text or "") > float(L.NON_LATIN_BAR if bar is None else bar)


def decide_demotion(score: Optional[float], threshold: float, text: str,
                    bar: Optional[float] = None) -> str:
    """One population tag: `unscored` (no classifier pair: cannot be demoted),
    `uncertain_language` (the gate), `reject` (score below the threshold) or `keep`."""
    return decide_gated(score, threshold, non_english(text, bar))


def decide_gated(score: Optional[float], threshold: float, gated: bool) -> str:
    """`decide_demotion` with the gate already evaluated (one gate per row, many tags)."""
    if score is None:
        return UNSCORED
    if gated:
        return UNCERTAIN_LANGUAGE
    return REJECT if float(score) < float(threshold) else KEEP


def sidecar_line(row_id: str, ticker: str, score: float, threshold: float, *, variant: str,
                 classifier: str, model: str, declaration_sha: str) -> dict:
    return {"schema": SCHEMA, "row_id": str(row_id), "ticker": str(ticker), "action": "hide",
            "score": round(float(score), 4), "threshold": round(float(threshold), 6),
            "variant": str(variant), "classifier": str(classifier), "model": str(model),
            "declaration_sha": str(declaration_sha)}


def write_sidecar(path: Path, lines: Iterable[dict]) -> int:
    """Atomic write (temp file, then replace). Returns the number of lines."""
    p = Path(path)
    tmp = Path(str(p) + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        for ln in lines:
            if ln.get("schema") != SCHEMA:
                raise DemotionRefused(SIDECAR_BAD_SCHEMA, f"refusing to write a line of schema {ln.get('schema')!r}")
            fh.write(json.dumps(ln, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n")
            n += 1
    os.replace(tmp, p)
    return n


def read_sidecar(path: Path) -> dict[tuple[str, str], dict]:
    """{(row_id, ticker): line}. Refuses a missing file and any line of another schema."""
    p = Path(path)
    if not p.is_file():
        raise DemotionRefused(SIDECAR_MISSING, f"no demotion sidecar at {p}")
    out: dict[tuple[str, str], dict] = {}
    with open(p, encoding="utf-8") as fh:
        for k, line in enumerate(fh, 1):
            if not line.strip():
                continue
            o = json.loads(line)
            if not isinstance(o, dict) or o.get("schema") != SCHEMA or o.get("action") != "hide":
                raise DemotionRefused(SIDECAR_BAD_SCHEMA, f"{p} line {k} is not a {SCHEMA} hide line")
            out[(str(o["row_id"]), str(o["ticker"]))] = o
    return out


def apply_demotions(row_id: str, tags: Sequence[Any],
                    demotions: Mapping[tuple[str, str], Any]) -> tuple[list, list]:
    """(kept, hidden) for one hub row. Pure: the input is not modified. A tag is hidden only
    when the sidecar names (row_id, ticker) AND the tag is a body-match / digest `mentions`
    tag; an `about` tag is kept whatever the sidecar says. Nothing is added."""
    kept, hidden = [], []
    for tag in tags or []:
        t = _fields(tag)[0]
        if (str(row_id), t) in demotions and is_demotable(tag):
            hidden.append(tag)
        else:
            kept.append(tag)
    return kept, hidden


def default_sidecar_path(work: Path) -> Path:
    return Path(work) / str(C.NEWS_DEMOTE_SIDECAR_NAME)
