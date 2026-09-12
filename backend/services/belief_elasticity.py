"""X2 -- how much does the model's belief move when the NEWS changes?

C1 wrote, for 6,935 real headlines, one to three counterfactual rewrites each:
a `sign_flip` (the same event with the opposite valence), an `escalation` (more
of the same), and an `actor_timing` change (who, or when). Show the model the
real anonymised headline and then its rewrite, and the CHANGE in its forecast
is a number per name-day -- how much the belief depends on the news rather than
on the calendar. Spec `docs/research_notes/2026-09-12/spec_lane_x.md` section 3.

WHAT WAS MEASURED HERE RATHER THAN ASSUMED
==========================================
The spec proposed `escalation: delta = +1 fixed`, and flagged it: *"the builder
should re-verify this against a larger sample before freezing, since the
sampled rows show escalation direction sometimes equal to the real row's own
direction and sometimes not."* Counted over all 6,935 C1 rows on 2026-09-12:

    escalation counterfactuals        6,026
      direction == the parent's       4,919   (81.63%)
      direction != the parent's       1,107   (18.37%)

So a fixed `+1` would be wrong for nearly a fifth of them. An escalation is
"more of the same" only when it points the same way as the row it escalates;
when it does not, it is some other perturbation wearing the escalation label
and it has no principled denominator. Those cells are DROPPED and counted, not
forced to +1. Same discipline for `sign_flip`: 5,437 of 6,674 have a signed
parent and a signed, DIFFERENT counterfactual direction; the other 1,237 (an
UNCLEAR on either side, or a "flip" that did not change the sign) cannot anchor
a denominator and are dropped rather than zero-filled.

`actor_timing` is excluded from the elasticity entirely -- it changes who or
when, not the event's sign or magnitude, so `delta_event` has no scale. It is
kept only for the direction-flip diagnostic.

THE PLACEBO
===========
A real mechanism concentrates elasticity on TRUE (headline, its own
counterfactual) pairs and shows nothing on (headline, an unrelated headline's
counterfactual) pairs. The placebo's distribution is the null the true pairs
are compared against -- never zero (the 2026-09-08 D1 lesson).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]

#: C1's rows, one per real headline.
C1_PATH = (REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08" /
           "C1_counterfactual_news.jsonl")

#: Where the feature table for E1 lands. The parquet is gitignored (it is data);
#: `MANIFEST.json` beside it is tracked, so a reader without the file still
#: knows its shape, its row count and which run wrote it.
FEATURE_DIR = REPO / "backend" / "data" / "optimus" / "x_lane"

DIRECTION_SIGN: dict[str, int | None] = {"POSITIVE": 1, "NEGATIVE": -1, "UNCLEAR": None}

#: Kinds that carry a principled denominator, in the order the receipt reports.
ELASTIC_KINDS: tuple[str, ...] = ("sign_flip", "escalation")
#: Kept for the flip diagnostic only -- see the module docstring.
DIAGNOSTIC_ONLY_KINDS: tuple[str, ...] = ("actor_timing",)

#: The rng family every X-lane shuffle shares (R2's own seed).
SEED = 20260909


def signed(direction) -> int | None:
    """`POSITIVE`/`NEGATIVE`/`UNCLEAR` (or +1/-1/0) to a sign, or `None`."""
    if direction is None:
        return None
    if isinstance(direction, (int, float)) and not isinstance(direction, bool):
        v = int(direction)
        return v if v in (-1, 1) else (0 if v == 0 else None)
    return DIRECTION_SIGN.get(str(direction).strip().upper())


def signed_p(direction: str | int | None, confidence: float) -> float:
    """The model's reply as one signed scalar: `+conf` UP, `-conf` DOWN, 0 FLAT.

    R2's parser returns `(dir, conf)` with `dir` in {1, 0, -1}; this is the same
    convention, so a reply parsed by `night_r2_monthly_llm.parse` drops straight
    in without a second mapping to disagree with.
    """
    s = signed(direction)
    if s is None or s == 0:
        return 0.0
    return float(s) * float(min(max(confidence, 0.0), 1.0))


def delta_event(kind: str, parent_direction, cf_direction) -> float | None:
    """The SIGNED scale of the perturbation, or `None` when it has none.

    `sign_flip`: `sign(cf) - sign(parent)`, typically +/-2. Undefined when
    either side is UNCLEAR, or when the "flip" did not change the sign -- a
    denominator of zero is not a small denominator.

    `escalation`: `+1` in the PARENT's own signed frame (more of the same), and
    only when the counterfactual agrees with the parent's direction. Measured,
    not assumed: 18.37% of C1's escalations point the other way.

    `actor_timing` and anything else: `None`.
    """
    p, c = signed(parent_direction), signed(cf_direction)
    if kind == "sign_flip":
        if p in (None, 0) or c in (None, 0) or p == c:
            return None
        return float(c - p)
    if kind == "escalation":
        if p in (None, 0) or c is None or c != p:
            return None
        return float(p)
    return None


def elasticity(p_real: float, p_cf: float, delta: float | None) -> float | None:
    """`(p_cf - p_real) / delta_event`, or `None` when the scale is undefined."""
    if delta in (None, 0):
        return None
    return float((float(p_cf) - float(p_real)) / float(delta))


def flip_pass(p_real: float, p_cf: float, delta: float | None) -> int | None:
    """P3, spec section 3.5: did the forecast move the way the news did?

    `1` when `sign(p_cf - p_real) == sign(delta_event)`. A TIE counts as FAIL:
    a model that does not move at all on a sign-flipped input is not
    demonstrating sensitivity to content. `None` only when there is no scale to
    compare against, in which case the cell is not in the denominator either.
    """
    if delta in (None, 0):
        return None
    move = float(p_cf) - float(p_real)
    if move == 0.0:
        return 0
    return 1 if ((move > 0) == (float(delta) > 0)) else 0


# ------------------------------------------------------------------ the rows

def load_c1(path: Path | None = None) -> list[dict]:
    """C1's rows with a usable anonymised headline, or `[]` if absent.

    Only `status == "OK"` rows: a `REFUSED_SCHEMA` row has no trustworthy
    counterfactual structure, and 259 of the 6,935 are refusals whose presence
    in a denominator would understate the extraction's own success rate.
    """
    path = Path(path or C1_PATH)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") != "OK" or not str(row.get("anon") or "").strip():
            continue
        out.append(row)
    return out


def pairs(rows: Iterable[dict], kinds: Iterable[str] = ELASTIC_KINDS) -> list[dict]:
    """Every (real headline, counterfactual) pair with a defined denominator.

    Each pair names the two texts to ask the model and the `delta_event` that
    will divide the answer. Pairs whose scale is undefined are NOT returned --
    `drop_reasons` counts them so the receipt can say how many and why.
    """
    want = set(kinds)
    out = []
    for row in rows:
        for i, cf in enumerate(row.get("counterfactuals") or []):
            kind = str(cf.get("kind") or "")
            if kind not in want:
                continue
            d = delta_event(kind, row.get("direction"), cf.get("direction"))
            if d is None:
                continue
            out.append({
                "uid": str(row.get("uid")), "cf_index": i, "kind": kind,
                "symbols": list(row.get("symbols") or []),
                "effective_at": row.get("effective_at"),
                "event_type": row.get("event_type"),
                "parent_direction": row.get("direction"),
                "cf_direction": cf.get("direction"),
                "delta_event": d,
                "real_text": str(row.get("anon") or ""),
                "cf_text": str(cf.get("text") or ""),
                "changed": cf.get("changed"),
            })
    return out


def drop_reasons(rows: Iterable[dict], kinds: Iterable[str] = ELASTIC_KINDS) -> dict:
    """Why a counterfactual has no denominator, counted per kind.

    A dropped cell that is never counted is a silently narrowed sample, which
    is the same shape as a filter that selects the regime. These are the
    numbers the receipt prints beside the kept ones.
    """
    want = set(kinds)
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        for cf in row.get("counterfactuals") or []:
            kind = str(cf.get("kind") or "")
            if kind not in want:
                continue
            bucket = out.setdefault(kind, {"kept": 0, "parent_unclear": 0,
                                           "cf_unclear": 0, "no_change_in_sign": 0,
                                           "escalation_points_the_other_way": 0})
            p, c = signed(row.get("direction")), signed(cf.get("direction"))
            if delta_event(kind, row.get("direction"), cf.get("direction")) is not None:
                bucket["kept"] += 1
            elif p in (None, 0):
                bucket["parent_unclear"] += 1
            elif c is None:
                bucket["cf_unclear"] += 1
            elif kind == "sign_flip":
                bucket["no_change_in_sign"] += 1
            else:
                bucket["escalation_points_the_other_way"] += 1
    return out


def placebo_pairs(pair_rows: list[dict], *, seed: int = SEED) -> list[dict]:
    """(headline, an UNRELATED headline's counterfactual of the same kind).

    Same kind, different `uid`, drawn with the shared rng family. The
    `delta_event` carried is the DONOR's -- the denominator belongs to the
    perturbation, and using the recipient's would compare a rewrite of one
    story against the scale of another.
    """
    rng = random.Random(seed)
    by_kind: dict[str, list[dict]] = {}
    for p in pair_rows:
        by_kind.setdefault(p["kind"], []).append(p)
    out = []
    for kind, group in by_kind.items():
        if len(group) < 2:
            continue
        order = list(range(len(group)))
        rng.shuffle(order)
        for i, j in enumerate(order):
            if group[j]["uid"] == group[i]["uid"]:
                j = (j + 1) % len(group)
                if group[j]["uid"] == group[i]["uid"]:
                    continue
            donor = group[j]
            out.append({**group[i], "kind": kind, "is_placebo": True,
                        "donor_uid": donor["uid"],
                        "cf_text": donor["cf_text"],
                        "cf_direction": donor["cf_direction"],
                        "delta_event": donor["delta_event"]})
    return out


# --------------------------------------------------------- the feature table

def feature_rows(scored: Iterable[dict], placebo_scored: Iterable[dict] | None = None
                 ) -> list[dict]:
    """One row per `uid`: the primary sign_flip leg, the escalation diagnostic,
    and the placebo's own value for the SAME uid.

    The three are never fused into one number. A consumer nets the real
    elasticity against ITS OWN placebo rather than against a pooled benchmark,
    which is why `belief_elasticity_placebo_null` travels beside the feature
    instead of being subtracted here.
    """
    per_uid: dict[str, dict] = {}
    for s in scored:
        u = s["uid"]
        row = per_uid.setdefault(u, {
            "uid": u, "symbols": s.get("symbols") or [],
            "effective_at": s.get("effective_at"), "event_type": s.get("event_type"),
            "belief_elasticity_sign_flip": None,
            "belief_elasticity_escalation": None,
            "belief_elasticity_placebo_null": None,
            "flip_pass": None, "n_pairs": 0})
        row["n_pairs"] += 1
        if s.get("elasticity") is None:
            continue
        if s["kind"] == "sign_flip":
            row["belief_elasticity_sign_flip"] = s["elasticity"]
            row["flip_pass"] = s.get("flip_pass")
        elif s["kind"] == "escalation":
            row["belief_elasticity_escalation"] = s["elasticity"]
    for s in placebo_scored or []:
        row = per_uid.get(s["uid"])
        if row is not None and s.get("elasticity") is not None:
            row["belief_elasticity_placebo_null"] = s["elasticity"]
    return list(per_uid.values())


def write_feature_table(rows: list[dict], *, run_date: str, run: int,
                        directory: Path | None = None) -> dict:
    """Write the parquet and the tracked manifest beside it.

    The parquet is data and is gitignored; `MANIFEST.json` is not, so a reader
    on a checkout without the file still knows its shape, its row count and
    which run wrote it -- the failure `git ls-files` made visible on 2026-09-11
    when a re-grade wrote tracked artefacts beside gitignored scratch.
    """
    import hashlib

    import pandas as pd

    directory = Path(directory or FEATURE_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"elasticity_{run_date}_run{run:02d}.parquet"
    df = pd.DataFrame(rows)
    if not df.empty and "symbols" in df.columns:
        df["symbols"] = df["symbols"].apply(lambda v: ",".join(map(str, v or [])))
    df.to_parquet(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path = directory / "MANIFEST.json"
    entries = {}
    if manifest_path.is_file():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = {}
    entries[path.name] = {
        "rows": int(len(df)), "columns": list(df.columns),
        "sha256": digest, "bytes": path.stat().st_size,
        "written_by": "scripts/night_x2_elasticity.py", "run": run,
        "consumer": ("E1's tabular head, left-joined on (symbol, effective_at); NaN "
                     "where C1 has no counterfactual for that cell -- LightGBM handles "
                     "NaN natively and this table is never fillna(0)'d"),
    }
    manifest_path.write_text(json.dumps(entries, indent=1, sort_keys=True),
                             encoding="utf-8")
    return {"path": str(path), "manifest": str(manifest_path), "rows": int(len(df)),
            "sha256": digest}


def pit_note() -> str:
    """The PIT rule X2 adds, spec section 3.3, in one sentence for the receipt."""
    return ("The elasticity for a uid may enter a prediction whose decision date is on "
            "or after that headline's own `effective_at` -- E1's existing contract, "
            "unchanged. X2 adds only that BOTH the real-headline forecast and the "
            "counterfactual-substituted forecast must exist before that decision, which "
            "they trivially do: the counterfactual call needs no future information, "
            "only the already-published headline it perturbs.")
