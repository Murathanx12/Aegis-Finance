"""EVIDENCE MEMORY -- what a weekend of passes is allowed to conclude.

THE PROBLEM THIS SOLVES
=======================
A looping lab produces the same shaped receipt over and over. Without a memory,
pass 19 knows nothing that pass 1 knew, the leaderboard is a LOG rather than a
state, and the only way to read forty hours of work is to read forty hours of
work. Worse, it makes both errors available at once:

* a cell that happened to look good on ONE pass gets quoted as a finding, and
* a cell that happened to look flat on ONE pass gets called dead.

THE RULE THAT PREVENTS BOTH: **A SINGLE OBSERVATION CAN NEITHER PROMOTE NOR
KILL.** Every state transition needs at least two DISTINCT observations agreeing,
and `REFUTED` needs three AND needs each to have had the POWER to detect the
effect. That last clause is the one usually missing, and it is the difference
between "we looked and it was not there" and "we looked with an instrument too
short to see it". The night lab of 2026-09-05 produced exactly that situation --
a +14.4%/yr arm needing 16.1 years to resolve on 7 years of tape -- and reporting
it as NOISE would have been a false negative dressed as rigour.

**DISTINCT, NOT REPEATED -- and this file learned it from its own output.** The
first version counted raw passes and promoted `attention_z_5d` to SUPPORTED on
"24 of 24 passes". The weekend runner had simply executed a DETERMINISTIC job
twenty-four times against the same panel; those were twenty-four copies of one
observation. A rule meant to stop one lucky pass being quoted had licensed the
opposite error: **a deterministic job promoting itself by being run again.**
`evidence_key` now collapses passes that asked the same question of the same data
and got the same answer. What survives as replication is a different VARIANT --
W7's top-50/top-100/top-25 and 6m/12m arms are four genuinely different
questions; running W6 nine times is one.

THE STATES, AND WHAT EACH ONE LICENSES
======================================
| state | means | may it be traded? |
|---|---|---|
| `IDEA` | fewer than 2 DISTINCT observations. Nothing is known yet. | no |
| `CONDITIONAL` | clears its bar once, not twice | paper only |
| `SUPPORTED` | clears DSR + SPA + PBO + 2-of-3 eras on >= 2 distinct observations | candidate |
| `REGIME_SPECIFIC` | real in ONE era, absent in the others | paper, scoped |
| `COST_KILLED` | beats the market GROSS, loses NET | no -- fix the costs |
| `REFUTED` | 3+ POWERED distinct observations, none positive | no |

`COST_KILLED` is a separate state on purpose. "It does not work" and "it works
and the spread eats it" call for completely different next moves -- the second
one is an execution problem, and collapsing it into REFUTED throws away a live
lead. This repo has killed several ideas that were only ever the second kind.

THE ESTIMATOR IS NOT NEW
========================
The shrinkage comes from `backend/services/arena/trust_router.backoff_estimate`,
re-keyed from (actor, context) to (family, cell). A thin cell inherits its
family's rate instead of shouting alone, which is the same reason that estimator
exists on the arena side: a leaf with two observations and a 100% hit rate is
not a 100% hit rate. Re-using it rather than writing a second shrinkage rule
means the two halves of the system cannot disagree about what thin evidence is
worth.

APPEND-ONLY, JSONL, ON PURPOSE
==============================
Every observation is appended and nothing is ever rewritten, so the state is
always DERIVED from the full history and can be recomputed under a different
rule later. A store that overwrites its own summary cannot answer "what did we
believe before we changed the bar", which is the question every retrospective
actually asks. It is greppable, diffable, and survives a killed job with
everything written up to that moment intact.

...AND SUPERSEDABLE, AT ONE PLACE ONLY
======================================
Append-only with no supersession lets a RETRACTED experiment keep voting, which
is what `supersede()` and e6ce604 fixed. That fix lived inside `snapshot()`,
which was enough for `snapshot()` and for nothing else: `read_all` and
`state_of` are public and unfiltered, so the second consumer -- the registry
export below -- would have inherited the whole leaked store with nothing going
red. `live_rows()` is now THE place supersessions are applied, and `snapshot`,
`state_of(..., rules=...)` and `registry_rows` all route through it.

THE MEMORY SPEAKS TO THE ALLOCATOR (B6 §4)
==========================================
`--to-registry` writes `(family, era, state) -> {n, sharpe, dsr, spa_p, pbo,
verdict}` into a `conditional_evidence:` block in
`backend/data/signal_registry.yaml` -- read-only for the PM until B9, and
structurally so: nothing in `backend/services/signal_registry.py` reads a
sixth top-level key. What the memory has WITHDRAWN travels with what it knows:
a superseded or retracted family is not exported, and the block names it, its
reason, and the count of cells being withheld.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE_DIR = REPO / "backend" / "data" / "optimus" / "learner"
STORE = STORE_DIR / "evidence_memory.jsonl"
STATE_SNAPSHOT = STORE_DIR / "evidence_memory_state.json"

VERSION = "evidence-memory-1"

STATES = ("IDEA", "CONDITIONAL", "SUPPORTED", "REGIME_SPECIFIC",
          "COST_KILLED", "REFUTED")

#: A pass "clears the bar" when it would have been called NOVEL on its own.
DSR_BAR = 0.95
SPA_BAR = 0.10
PBO_BAR = 0.5

#: A single pass can neither promote nor kill.
MIN_PASSES_TO_PROMOTE = 2
MIN_PASSES_TO_REFUTE = 3


#: The verdict vocabulary this repo actually uses, defined in
#: `scripts/weekend_lab_jobs.verdict_from` / `.screen_verdict`. It is repeated
#: here rather than imported because importing `weekend_lab_jobs` pulls the
#: whole lab (pandas, the panel loader, torch) into a CLI whose job is to read
#: a JSONL file. `test_evidence_registry_export.py` pins the two lists equal,
#: so the copy cannot drift silently.
VERDICT_VOCABULARY = (
    "NOVEL", "DECAYED", "SCREEN_SURVIVOR", "SCREEN_ONLY",
    "CANNOT DETERMINE", "NOISE", "REFUTED",
)

#: A SCREEN has no book, so it has no Sharpe to deflate and can never reach
#: NOVEL. `screen_verdict`'s docstring: "NOVEL is reserved for something that
#: survived a book, a family and a deflation. A screen cannot reach it, and
#: pretending otherwise is how a coefficient becomes a claim."
SCREEN_CEILING = "SCREEN_SURVIVOR"

#: States the registry is told about. IDEA means "fewer than two distinct
#: observations -- nothing is known yet", and 313 of those would be 313 rows
#: saying nothing. An absent family is the honest encoding of "no evidence".
EXPORTED_STATES = ("SUPPORTED", "REGIME_SPECIFIC", "CONDITIONAL",
                   "COST_KILLED", "REFUTED")

#: Strength order for picking the row that represents a (family, state) group.
_STATE_RANK = {s: i for i, s in enumerate(
    ("REFUTED", "IDEA", "COST_KILLED", "CONDITIONAL", "REGIME_SPECIFIC",
     "SUPPORTED"))}


class EvidenceMemoryError(RuntimeError):
    """The memory cannot be read as written. Loud, because everything derives
    its state from it and a silently-skipped line changes the answer."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ recording

def observe(family_id: str, cell: str, *, n_months, sharpe=None, dsr=None,
            spa_p=None, pbo=None, verdict=None, powered=None,
            years_needed_for_t2=None, years_observed=None,
            eras=None, gross_beats_market=None, net_beats_market=None,
            job=None, run=None, variant=None, note=None,
            screen_cleared=None, controlled_t=None, holm_p=None) -> dict:
    """Append ONE observation. Never updates, never dedupes, never overwrites."""
    row = {
        "screen_cleared": screen_cleared, "controlled_t": controlled_t,
        "holm_p": holm_p,
        "utc": _now(), "version": VERSION,
        "family_id": family_id, "cell": cell,
        "job": job, "run": run, "variant": variant,
        "n_months": n_months, "sharpe": sharpe,
        "dsr": dsr, "spa_p": spa_p, "pbo": pbo,
        "verdict": verdict,
        "powered": powered,
        "years_needed_for_t2": years_needed_for_t2,
        "years_observed": years_observed,
        "eras": eras,
        "gross_beats_market": gross_beats_market,
        "net_beats_market": net_beats_market,
        "note": note,
    }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


SUPERSESSIONS = STORE_DIR / "evidence_memory_supersessions.jsonl"


def supersede(family_id: str, before_utc: str, why: str,
              cell_prefix: str | None = None) -> dict:
    """Mark observations of a family (or cell) BEFORE a time as not counting.

    THE DEFECT THIS REPAIRS, found in this module's own output on 2026-09-06.
    The store is append-only, which is right: a summary that overwrites itself
    cannot answer "what did we believe before we changed the bar". But
    append-only with no supersession means a RETRACTED experiment keeps voting.

    W7's matched-control pool was leaking (it excluded future losers, so any
    predictor of outcome dispersion differed from winners by construction). It
    was fixed, and the leaked RECEIPTS were moved aside. The observations those
    receipts had already written stayed in the JSONL, still outnumbering the
    corrected ones -- and the memory went on reporting
    `log_dollar_vol_20d` as SUPPORTED, which is precisely the archetype the fix
    destroyed (Holm 0.000178 -> 0.158).

    So supersession is EXPLICIT, APPENDED, and carries its reason. Nothing is
    deleted; `read_all()` still returns every row, and `--show-superseded` prints
    what is being excluded and why. The difference between "we never saw this"
    and "we saw it, and then we learned the instrument was broken" is the whole
    value of keeping the file.
    """
    if not family_id:
        raise EvidenceMemoryError(
            "supersede() needs a family_id. A rule with no family would "
            "silently retract the whole memory.")
    if not why:
        raise EvidenceMemoryError(
            "supersede() needs a reason. An unreasoned retraction is "
            "indistinguishable from data loss six weeks later.")
    _check_before_utc(before_utc)
    row = {"utc": _now(), "family_id": family_id, "before_utc": before_utc,
           "cell_prefix": cell_prefix, "why": why}
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with SUPERSESSIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def _check_before_utc(before_utc) -> None:
    """A supersession boundary that cannot match is a BROKEN rule, not a lax one.

    `is_superseded` compares ISO strings lexicographically, which is correct for
    two full timestamps and silently WRONG for anything shorter: a rule written
    `before_utc: "2026-09-05"` excludes nothing at all, because
    `"2026-09-05T05:40:00+00:00" < "2026-09-05"` is False. The rule would sit in
    the file looking like a retraction while every retracted observation went on
    voting -- the exact failure e6ce604 was written to end, re-entering through
    the boundary instead of through the store.

    `None` is permitted and means the WHOLE family, for all time: a retraction
    with no surviving correction.
    """
    if before_utc is None:
        return
    s = str(before_utc)
    try:
        datetime.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise EvidenceMemoryError(
            f"before_utc {before_utc!r} is not an ISO timestamp. Supersession "
            f"compares ISO strings, so a partial value (a bare date, say) "
            f"matches NOTHING and the rule excludes nothing while reading as a "
            f"retraction. Pass a full timestamp, or None to supersede the "
            f"family for all time.") from exc
    if len(s) < len("2026-09-05T00:00:00"):
        raise EvidenceMemoryError(
            f"before_utc {before_utc!r} is shorter than a full timestamp; "
            f"lexicographic comparison against "
            f"'2026-09-05T05:40:00+00:00' would exclude nothing.")


def read_supersessions() -> list[dict]:
    """Every retraction rule on file. A line that does not parse RAISES.

    THE ASYMMETRY THAT DECIDES THIS. `read_all` skips an unparseable
    observation and the cost is one data point. Skipping an unparseable
    SUPERSESSION re-admits a retracted experiment to every state, tally and
    export -- silently, and in the direction of claiming more than we know. The
    two reads look alike and their failures do not, so this one refuses.
    """
    if not SUPERSESSIONS.exists():
        return []
    out = []
    for i, line in enumerate(
            SUPERSESSIONS.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceMemoryError(
                f"{SUPERSESSIONS.name} line {i} does not parse: {exc}. This "
                f"file is refused rather than skipped: a dropped supersession "
                f"puts a RETRACTED experiment back in the state counts.") from exc
        if not isinstance(row, dict) or not row.get("family_id"):
            raise EvidenceMemoryError(
                f"{SUPERSESSIONS.name} line {i} has no family_id: {row!r}")
        _check_before_utc(row.get("before_utc"))
        out.append(row)
    return out


def is_superseded(r: dict, rules: list[dict]) -> str | None:
    """The reason this observation no longer counts, or None."""
    for s in rules:
        if s.get("family_id") not in (None, r.get("family_id")):
            continue
        pre = s.get("cell_prefix")
        if pre and not str(r.get("cell", "")).startswith(pre):
            continue
        before = s.get("before_utc")
        if before is None or str(r.get("utc", "")) < str(before):
            return s.get("why") or "superseded"
    return None


def superseded_families(rules: list[dict] | None = None) -> dict[str, str]:
    """Family -> why, for every family ANY retraction rule touches.

    Row-level supersession is right for the STATE: a family whose instrument was
    fixed keeps the observations the fixed instrument produced. It is not right
    for an EXPORT to the registry, which is a claim made to the half of the
    system that allocates. A family we have already had to retract once does not
    get to speak there until a human re-admits it (B9). The rule is conservative
    on purpose, and the receipt names every family it silences and why.
    """
    rules = read_supersessions() if rules is None else rules
    out: dict[str, str] = {}
    for s in rules:
        fam = s.get("family_id")
        if not fam:
            continue
        out.setdefault(fam, s.get("why") or "superseded")
    return out


def live_rows(rows: list[dict] | None = None,
              rules: list[dict] | None = None) -> tuple[list[dict], dict, dict]:
    """THE ONE PLACE supersessions are applied.

    Everything that derives state goes through here -- `snapshot()`,
    `state_of(..., rules=...)` and the registry export -- because e6ce604 put the
    filter at a SINGLE CALL SITE, and a second consumer written later would have
    inherited the unfiltered store without anything going red. The fix to a
    retracted experiment voting must not itself be reachable only from one
    function.

    Returns (kept, dropped_by_reason, per_rule_effect).
    """
    rows = read_all() if rows is None else rows
    rules = read_supersessions() if rules is None else rules
    if not rules:
        return list(rows), {}, {}
    kept, dropped = [], {}
    for r in rows:
        why = is_superseded(r, rules)
        if why is None:
            kept.append(r)
        else:
            dropped[why] = dropped.get(why, 0) + 1
    effect = {}
    for i, s in enumerate(rules):
        n = sum(1 for r in rows if is_superseded(r, [s]))
        effect[f"{i}:{s.get('family_id')}"] = {
            "before_utc": s.get("before_utc"),
            "cell_prefix": s.get("cell_prefix"),
            "observations_excluded": n,
            "why": s.get("why"),
            # A rule that excludes nothing is either already spent or WRONG, and
            # it must never read as "applied, no effect" without saying so.
            "WARNING": (None if n else
                        "this rule excludes ZERO observations -- check its "
                        "before_utc and family_id; a retraction that matches "
                        "nothing is a broken guard, not a lax one"),
        }
    return kept, dropped, effect


def read_all() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ------------------------------------------------------------------- scoring

def _clears(r: dict) -> bool:
    """Would this ONE observation have been called a result on its own?

    TWO KINDS OF ROW, TWO BARS, AND NEITHER PRETENDS TO BE THE OTHER. A BOOK row
    carries a Deflated Sharpe, an SPA p and a PBO, and clears on those. A SCREEN
    row (a Fama-MacBeth coefficient, a matched-control difference) has no book
    and therefore no Sharpe to deflate; it clears on its own controlled t, its
    era sign, and -- where the job computed one -- a Holm-corrected p. Stamping a
    fake DSR on a screen row, as the first version did, made this function
    re-read the number that produced it and report the agreement as evidence.
    """
    if r.get("screen_cleared") is not None:
        if not bool(r["screen_cleared"]):
            return False
        holm = r.get("holm_p")
        # Where the job corrected for multiplicity, the correction is the bar.
        return bool(holm is None or (isinstance(holm, (int, float)) and holm <= 0.05))
    dsr, spa_p, pbo = r.get("dsr"), r.get("spa_p"), r.get("pbo")
    if not isinstance(dsr, (int, float)) or not isinstance(spa_p, (int, float)):
        return False
    if dsr < DSR_BAR or spa_p > SPA_BAR:
        return False
    if isinstance(pbo, (int, float)) and pbo >= PBO_BAR:
        return False
    eras = r.get("eras") or {}
    return bool(eras.get("holds_in_2_of_3") or eras.get("same_sign_in_2_of_3"))


def _era_count(r: dict) -> tuple[int, int]:
    eras = r.get("eras") or {}
    pos = eras.get("eras_with_a_positive_mean")
    meas = eras.get("eras_measured")
    return (int(pos) if isinstance(pos, int) else 0,
            int(meas) if isinstance(meas, int) else 0)


def evidence_key(r: dict) -> tuple:
    """What makes an observation a NEW piece of evidence rather than a copy.

    THE BUG THIS EXISTS TO FIX, caught in this module's own output on 2026-09-06:

        SUPPORTED  attention_z_5d  (cleared the full bar on 24 of 24 passes)

    Twenty-four of twenty-four passes is not twenty-four pieces of evidence. The
    weekend runner had executed `W6_behavioural` twenty-four times against the
    same panel with the same code, and a deterministic job returns the identical
    number every time. Those were twenty-four COPIES of one observation.

    The rule "a single pass can neither promote nor kill" was written to stop one
    lucky pass being quoted as a finding. Counting raw rows let in the opposite
    error: a deterministic job promotes itself by being run again. Same shape as
    `feedback_count_the_days_before_reading_the_columns` ("file size is not
    sample size") -- PASS COUNT IS NOT EVIDENCE COUNT.

    So evidence is keyed on the VARIANT and on the RESULT ITSELF, rounded. Two
    passes that asked the same question of the same data and got the same answer
    collapse to one. A different variant, a different panel, or a materially
    different number is new evidence; a re-run is not.
    """
    def _r(x, n=4):
        return round(float(x), n) if isinstance(x, (int, float)) else None
    return (r.get("variant"), _r(r.get("dsr")), _r(r.get("spa_p")),
            _r(r.get("pbo")), r.get("n_months"), _r(r.get("sharpe"), 6),
            _r(r.get("controlled_t")), _r(r.get("holm_p"), 6),
            r.get("screen_cleared"), r.get("verdict"))


def distinct_evidence(rows: list[dict]) -> list[dict]:
    """One row per distinct evidence key, keeping the most recent of each."""
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen[evidence_key(r)] = r
    return list(seen.values())


def state_of(rows: list[dict], family_rate: float | None = None,
             global_rate: float | None = None,
             rules: list[dict] | None = None) -> dict:
    """The state of ONE cell, from every observation of it.

    Order matters and is deliberate: COST_KILLED is checked BEFORE REFUTED,
    because a cell that beats the market gross and loses net is an execution
    problem wearing a research failure's clothes, and calling it REFUTED closes
    a live lead.

    `rules` is the supersession list. Pass it and a RETRACTED observation cannot
    vote here either -- not only inside `snapshot()`, where e6ce604 put the
    filter. A caller that holds the rules and does not pass them gets the
    unfiltered answer, which is why `snapshot()` and the registry export both
    pass them and `test_evidence_memory_superseded.py` pins the difference.
    """
    from backend.services.arena import trust_router as TR
    if rules:
        rows, _dropped, _eff = live_rows(rows, rules)
    raw_passes = len(rows)
    if raw_passes == 0:
        return {"state": "IDEA", "passes": 0, "why": "never observed",
                "distinct_observations": 0, "raw_passes": 0,
                "passes_clearing_the_bar": 0}
    # DISTINCT EVIDENCE, not raw passes. A deterministic job re-run twenty-four
    # times is one observation, not twenty-four. See `evidence_key`.
    rows = distinct_evidence(rows)
    n = len(rows)
    cleared = sum(1 for r in rows if _clears(r))
    powered = [r for r in rows if r.get("powered") is True]
    n_powered = len(powered)
    cost_killed = [r for r in rows
                   if r.get("gross_beats_market") is True
                   and r.get("net_beats_market") is False]
    # Shrunk hit rate: global -> family -> this cell. A leaf with 2 of 2 is not
    # a 100% rate, and the hierarchy is what says so.
    levels = []
    if global_rate is not None:
        levels.append((global_rate * 100.0, 100.0))
    if family_rate is not None:
        levels.append((family_rate * 50.0, 50.0))
    levels.append((float(cleared), float(n)))
    est = TR.backoff_estimate(levels, prior=0.10)

    regime = 0
    for r in rows:
        pos, meas = _era_count(r)
        if meas >= 3 and pos == 1:
            regime += 1

    if n < MIN_PASSES_TO_PROMOTE:
        state, why = ("IDEA",
                      f"{raw_passes} pass(es) collapse to {n} DISTINCT observation(s); a "
                      "single observation can neither promote nor kill, and re-running a "
                      "deterministic job is not a second observation")
    elif cleared >= MIN_PASSES_TO_PROMOTE:
        state, why = ("SUPPORTED",
                      f"cleared the full bar on {cleared} of {n} DISTINCT observations "
                      f"(from {raw_passes} passes)")
    elif len(cost_killed) >= MIN_PASSES_TO_PROMOTE:
        state, why = ("COST_KILLED",
                      f"beat the market GROSS and lost NET on {len(cost_killed)} of {n} DISTINCT "
                      "passes -- an execution problem, not a research failure")
    elif regime >= MIN_PASSES_TO_PROMOTE:
        state, why = ("REGIME_SPECIFIC",
                      f"positive in exactly one of three eras on {regime} of {n} distinct observations")
    elif cleared >= 1:
        state, why = "CONDITIONAL", f"cleared the bar on {cleared} of {n} distinct observations, not twice"
    elif n_powered >= MIN_PASSES_TO_REFUTE:
        state, why = ("REFUTED",
                      f"{n_powered} POWERED DISTINCT observations and none cleared the bar")
    else:
        # THE CLAUSE THAT IS USUALLY MISSING. Without power, "we looked and found
        # nothing" is not evidence of absence, and calling it REFUTED would be a
        # false negative wearing rigour's clothes.
        need = [r.get("years_needed_for_t2") for r in rows
                if isinstance(r.get("years_needed_for_t2"), (int, float))]
        state = "IDEA"
        why = (f"{n} distinct observations ({raw_passes} passes), none cleared the bar, but "
               f"only {n_powered} had the POWER to "
               f"detect it"
               + (f" (a t = 2 would need up to {max(need):.1f} years)" if need else "")
               + " -- absence of evidence is not evidence of absence")
    return {
        "state": state, "why": why,
        "distinct_observations": n, "raw_passes": raw_passes,
        "passes": n, "passes_clearing_the_bar": cleared,
        "powered_passes": n_powered,
        "cost_killed_passes": len(cost_killed),
        "one_era_only_passes": regime,
        "shrunk_clear_rate": round(float(est["estimate"]), 4),
        "evidence_n": est["evidence_n"],
        "last_seen": rows[-1].get("utc"),
        "best_dsr": max((r["dsr"] for r in rows
                         if isinstance(r.get("dsr"), (int, float))), default=None),
        "median_n_months": sorted(
            [r["n_months"] for r in rows if isinstance(r.get("n_months"), int)]
        )[len(rows) // 2] if any(isinstance(r.get("n_months"), int) for r in rows) else None,
    }


def snapshot() -> dict:
    """Every cell's state, derived from the whole history. Written to disk.

    Observations covered by a supersession rule are EXCLUDED from the state and
    COUNTED in the receipt, so the snapshot says how much evidence it is
    declining to use and why.
    """
    all_rows = read_all()
    rules = read_supersessions()
    rows, dropped, rule_effect = live_rows(all_rows, rules)
    by_cell: dict[tuple[str, str], list[dict]] = {}
    by_family: dict[str, list[dict]] = {}
    for r in rows:
        by_cell.setdefault((r.get("family_id"), r.get("cell")), []).append(r)
        by_family.setdefault(r.get("family_id"), []).append(r)
    g_clear = (sum(1 for r in rows if _clears(r)) / len(rows)) if rows else 0.0
    fam_rate = {f: (sum(1 for r in rs if _clears(r)) / len(rs)) if rs else 0.0
                for f, rs in by_family.items()}
    cells = {}
    for (fam, cell), rs in by_cell.items():
        cells[f"{fam}::{cell}"] = state_of(rs, family_rate=fam_rate.get(fam),
                                           global_rate=g_clear, rules=rules)
    counts: dict[str, int] = {}
    for v in cells.values():
        counts[v["state"]] = counts.get(v["state"], 0) + 1
    out = {
        "version": VERSION, "written_utc": _now(),
        "observations": len(rows),
        "observations_on_file": len(all_rows),
        "observations_superseded": dict(sorted(dropped.items(), key=lambda kv: -kv[1])),
        "supersession_rules": len(rules),
        "supersession_rule_effects": rule_effect,
        "superseded_families_barred_from_export": superseded_families(rules),
        "cells": len(cells),
        "families": sorted(by_family),
        "global_clear_rate": round(g_clear, 4),
        "state_counts": counts,
        "rule": ("a single DISTINCT observation can neither promote nor kill; a "
                 "deterministic job re-run is not a second observation (see "
                 f"`evidence_key`); REFUTED additionally requires {MIN_PASSES_TO_REFUTE} "
                 "distinct observations that each HAD THE POWER to detect the effect"),
        "by_cell": dict(sorted(cells.items(),
                               key=lambda kv: -(kv[1].get("best_dsr") or 0))),
    }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_SNAPSHOT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def record_receipt(payload: dict) -> int:
    """Fold one weekend-lab receipt into the memory. Returns rows written.

    THE LAB DOES NOT PRODUCE ONE SHAPE OF RECEIPT, AND PRETENDING IT DOES COSTS
    EVERYTHING. The first version of this function read only `payload["cells"]`
    -- the grid shape W2 produces -- so W6's `features`, W7's
    `archetype_candidates` and W8's single family result all folded to ZERO
    observations, and the memory reported "0 cells tracked" while sitting on
    four real receipts. A memory that silently ignores three quarters of the
    evidence is worse than no memory, because the loop then reads its own
    emptiness as "nothing has been found yet".

    So the shape is DETECTED, and a receipt whose shape is not recognised
    records one FAMILY-LEVEL observation rather than nothing -- the fact that a
    family was tested is itself evidence, and losing it is the failure this
    docstring exists to prevent.
    """
    fam = payload.get("family_id")
    if not fam:
        return 0
    written = _record_cells(payload, fam)
    written += _record_features(payload, fam)
    if written == 0:
        # Not a recognised shape. Record that the family was TESTED, with
        # whatever inference it carries, rather than dropping it silently.
        inf = payload.get("inference") or {}
        power = inf.get("power") or {}
        observe(fam, "__family__",
                n_months=payload.get("n_common_months") or payload.get("months"),
                dsr=(inf.get("deflated_sharpe") or {}).get("dsr"),
                spa_p=(inf.get("spa") or {}).get("p_spa_consistent"),
                pbo=(inf.get("pbo") or {}).get("pbo"),
                verdict=payload.get("verdict"),
                powered=power.get("powered"),
                years_needed_for_t2=power.get("years_needed_for_t2"),
                years_observed=power.get("years_observed"),
                eras=payload.get("era_sign_table"),
                job=payload.get("job"), run=payload.get("run"),
                variant=payload.get("variant"),
                note="family-level observation: this receipt carries no per-cell grid")
        written = 1
    return written


def _record_features(payload: dict, fam: str) -> int:
    """The FEATURE shape: W6/W4/W5's `features` list, and W7's candidates.

    A feature is graded on its CONTROLLED t and its era sign, not on a DSR --
    there is no book and therefore no Sharpe. `_clears` reads the era table and
    the verdict, so a feature cell is comparable to a strategy cell in the one
    respect the memory cares about: did this pass clear its own bar.
    """
    written = 0
    for r in payload.get("features") or []:
        if not isinstance(r, dict) or "feature" not in r:
            continue
        t = r.get("t_fm_beta_controlled")
        eras = r.get("era_sign_table") or {}
        power = r.get("power") or {}
        cleared = bool(isinstance(t, (int, float)) and abs(t) >= 2.0
                       and eras.get("same_sign_in_2_of_3"))
        observe(fam, f"feature::{r['feature']}",
                n_months=r.get("months"),
                # A controlled t on a monthly coefficient series IS t = SR*sqrt(T),
                # so the Sharpe it implies is recoverable and comparable.
                sharpe=(round(float(t) / (float(r["months"]) ** 0.5), 5)
                        if isinstance(t, (int, float)) and r.get("months") else None),
                # NO FABRICATED DSR. The first version stamped dsr=0.99 / spa_p=0.01
                # when the t cleared and 0.10 / 0.90 when it did not, which made
                # `_clears` algebraically identical to the t-test that fed it --
                # a bar that re-reads its own input and reports agreement as
                # corroboration. It also made every SUPPORTED cell carry
                # `best_dsr` exactly 0.99, and `snapshot()` SORTS on that.
                # A feature screen has no book, so it has no Sharpe to deflate:
                # the honest record is the t and the era sign, and `_clears`
                # reads `screen_cleared` for these rows.
                dsr=None, spa_p=None, pbo=None,
                screen_cleared=cleared,
                controlled_t=(round(float(t), 4) if isinstance(t, (int, float)) else None),
                verdict=("CLEARS" if cleared else "does not clear"),
                powered=power.get("powered"),
                years_needed_for_t2=power.get("years_needed_for_t2"),
                years_observed=power.get("years_observed"),
                eras=eras,
                job=payload.get("job"), run=payload.get("run"),
                variant=payload.get("variant"),
                note=(f"controlled t {t}; graded on the controlled coefficient and the "
                      "era sign, not on a DSR -- a feature has no book"))
        written += 1
    for a in payload.get("archetype_candidates") or []:
        if not isinstance(a, dict) or "feature" not in a:
            continue
        holm = a.get("holm_p")
        bh = a.get("bh_fdr_q")
        cleared = bool(isinstance(holm, (int, float)) and holm <= 0.05)
        observe(fam, f"archetype::{a['feature']}",
                n_months=a.get("months"),
                dsr=None, spa_p=None, pbo=None,
                screen_cleared=cleared,
                holm_p=(holm if isinstance(holm, (int, float)) else None),
                controlled_t=a.get("t_block_non_overlapping"),
                verdict=("SURVIVES_HOLM" if cleared else "screen only"),
                powered=(a.get("power") or {}).get("powered"),
                years_needed_for_t2=(a.get("power") or {}).get("years_needed_for_t2"),
                years_observed=(a.get("power") or {}).get("years_observed"),
                eras=a.get("era_sign_table"),
                job=payload.get("job"), run=payload.get("run"),
                variant=payload.get("variant"),
                note=(f"winner-minus-matched-control; non-overlapping t "
                      f"{a.get('t_block_non_overlapping')}, BH q {bh}, Holm {holm}"))
        written += 1
    return written


def _record_cells(payload: dict, fam: str) -> int:
    """The GRID shape: W2's `cells`, one book per (arm, target, horizon, cost)."""
    inf = payload.get("inference") or {}
    power = inf.get("power") or {}
    eras = payload.get("era_sign_table")
    cells = payload.get("cells") or {}
    best = payload.get("best_cell")
    written = 0
    for cell, book in cells.items():
        if not isinstance(book, dict) or "error" in book:
            continue
        tw_net = book.get("terminal_wealth_net")
        tw_gross = book.get("terminal_wealth_gross")
        tw_mkt = book.get("terminal_wealth_market_same_months")
        is_best = (cell == best)
        observe(
            fam, cell,
            n_months=book.get("months"),
            sharpe=None,
            # Only the BEST cell carries the family-level inference: the DSR,
            # SPA and PBO were computed FOR the family maximum, and pasting them
            # onto every cell would let a mediocre cell inherit the champion's
            # correction.
            dsr=(inf.get("deflated_sharpe") or {}).get("dsr") if is_best else None,
            spa_p=(inf.get("spa") or {}).get("p_spa_consistent") if is_best else None,
            pbo=(inf.get("pbo") or {}).get("pbo") if is_best else None,
            verdict=payload.get("verdict") if is_best else None,
            powered=power.get("powered") if is_best else None,
            years_needed_for_t2=power.get("years_needed_for_t2") if is_best else None,
            years_observed=power.get("years_observed") if is_best else None,
            eras=eras if is_best else None,
            gross_beats_market=(None if tw_gross is None or tw_mkt is None
                                else bool(tw_gross > tw_mkt)),
            net_beats_market=(None if tw_net is None or tw_mkt is None
                              else bool(tw_net > tw_mkt)),
            job=payload.get("job"), run=payload.get("run"),
            variant=payload.get("variant"),
            note=("family maximum -- carries the family's inference"
                  if is_best else "family member -- book only"),
        )
        written += 1
    return written


# ────────────────────────── the registry export (B6 §4) ──────────────────────
#
# THE HALF OF THE SYSTEM THAT ALLOCATES CANNOT READ A JSONL. `signal_registry.
# yaml` is the machine-readable interface between the lab and the PM, and until
# now the evidence memory spoke only to itself: twelve SUPPORTED cells and one
# reasoned retraction lived in a 65 MB append-only file that nothing downstream
# opens. `--to-registry` writes what the memory KNOWS -- including what it has
# WITHDRAWN -- into a `conditional_evidence:` block.
#
# IT IS READ-ONLY FOR THE PM UNTIL B9, AND THAT IS A STRUCTURAL FACT, NOT A
# PROMISE. `backend/services/signal_registry.load()` builds its `Registry` from
# exactly five top-level keys -- schema, written, signals, standing_constraints,
# source_of_truth -- and `Registry` has no field for anything else. A new
# top-level block is invisible to `permits()`, `weight()`, `check_closed()` and
# every caller of them. `test_evidence_registry_export.py` pins that: it greps
# the repo for consumers of the string and asserts the loaded Registry cannot
# see the block.

REGISTRY_YAML = REPO / "backend" / "data" / "signal_registry.yaml"

_BEGIN = ("# ═══ BEGIN conditional_evidence — generated by "
          "`python -m learner.evidence_memory --to-registry` ═══")
_END = "# ═══ END conditional_evidence ═══"

_CAPPING_WORDS = ("REFUTED", "NOISE", "CANNOT DETERMINE")


def _leading_vocabulary_word(s) -> str | None:
    """The vocabulary word a recorded verdict string starts with, if any."""
    if not isinstance(s, str):
        return None
    t = s.strip().upper()
    for w in sorted(VERDICT_VOCABULARY, key=len, reverse=True):
        if t.startswith(w):
            return w
    return None


def _derive_verdict(obs: dict) -> str:
    """The vocabulary word this ONE observation earns on its own fields."""
    if obs.get("screen_cleared") is not None:
        # A SCREEN. No book, no Sharpe, no deflation -- the ceiling is
        # SCREEN_SURVIVOR and NOVEL is unreachable by construction.
        if bool(obs["screen_cleared"]):
            holm = obs.get("holm_p")
            if isinstance(holm, (int, float)) and holm <= 0.05:
                return "SCREEN_SURVIVOR"
            return "SCREEN_ONLY"
        if obs.get("powered") is False:
            return "CANNOT DETERMINE"
        return "NOISE"
    dsr, spa_p, pbo = obs.get("dsr"), obs.get("spa_p"), obs.get("pbo")
    eras = obs.get("eras") or {}
    if (isinstance(dsr, (int, float)) and isinstance(spa_p, (int, float))
            and dsr >= DSR_BAR and spa_p <= SPA_BAR
            and (not isinstance(pbo, (int, float)) or pbo < PBO_BAR)
            and eras.get("holds_in_2_of_3")):
        return "NOVEL"
    if obs.get("powered") is False:
        return "CANNOT DETERMINE"
    return "NOISE"


def export_verdict(obs: dict) -> tuple[str, str | None]:
    """(vocabulary word, the reason it was capped) for one observation.

    THE EXPORT MAY NEVER GRADE ABOVE THE JOB THAT RAN IT. `W3_neural_long`
    records dsr 0.9835, spa 0.016, pbo 0.086 and three positive eras -- which is
    NOVEL by the arithmetic -- and its own verdict is
    "NOISE (clears the market bar, does NOT beat lgbm)", because the comparison
    that mattered was against `lgbm_clf` and the arithmetic never saw it. A
    re-derivation that ignores the recorded word would promote that arm on its
    way into the registry, which is the one direction of error this export can
    make and the PM cannot check.

    So: derive, then CAP. A recorded NOISE / REFUTED / CANNOT DETERMINE binds.
    """
    derived = _derive_verdict(obs)
    recorded = _leading_vocabulary_word(obs.get("verdict"))
    if recorded in _CAPPING_WORDS and derived not in _CAPPING_WORDS:
        return recorded, (f"derived {derived}, capped by the job's own recorded "
                          f"verdict {str(obs.get('verdict'))[:90]!r}")
    return derived, None


def _era_verdict(months, t) -> str:
    """An era slice carries no deflation and no multiplicity correction, so it
    cannot exceed SCREEN_ONLY. Naming it anything stronger would let a
    three-way split of one sample produce three independent-looking findings."""
    if not isinstance(months, int) or months < 6 or not isinstance(t, (int, float)):
        return "CANNOT DETERMINE"
    if abs(float(t)) >= 2.0:
        return "SCREEN_ONLY"
    return "NOISE"


def _representative(rows: list[dict]) -> dict:
    """The observation that speaks for a cell: the strongest that CLEARED, else
    the most recent. Named in the export so the number can be traced back."""
    cleared = [r for r in rows if _clears(r)]
    pool = cleared or rows

    def key(r):
        return (float(r.get("dsr") or 0.0),
                abs(float(r.get("controlled_t") or 0.0)),
                str(r.get("utc") or ""))
    return sorted(pool, key=key)[-1]


def _num(x, nd=6):
    return round(float(x), nd) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def registry_rows(rows: list[dict] | None = None,
                  rules: list[dict] | None = None) -> tuple[list[dict], dict]:
    """`(family, era, state) -> {n, sharpe, dsr, spa_p, pbo, verdict}`.

    One row per (family, era, state) group. Within a group the numbers belong to
    the REPRESENTATIVE cell, which is named on the row -- an average over cells
    would be a number no experiment produced, and a maximum with nothing naming
    it is the family-max flattery this repo has paid for twice.

    Excluded, loudly and by name in the receipt:
      * every family any supersession rule touches (a retracted family does not
        speak to the allocator until a human re-admits it);
      * every family whose recorded verdict says RETRACT;
      * IDEA cells -- fewer than two distinct observations is not evidence, and
        313 rows saying "nothing is known yet" would bury the twelve that
        matter.
    """
    all_rows = read_all() if rows is None else rows
    rules = read_supersessions() if rules is None else rules
    live, dropped, rule_effect = live_rows(all_rows, rules)
    barred = superseded_families(rules)

    excluded: dict[str, dict] = {}
    for fam, why in barred.items():
        excluded[fam] = {"reason": "SUPERSEDED", "why": why}
    for r in live:
        v = str(r.get("verdict") or "")
        if "RETRACT" in v.upper() and r.get("family_id") not in excluded:
            excluded[str(r.get("family_id"))] = {
                "reason": "RETRACTED", "why": v[:200]}

    by_cell: dict[tuple, list[dict]] = {}
    by_family: dict[str, list[dict]] = {}
    held: dict[tuple, list[dict]] = {}
    for r in live:
        fam = r.get("family_id")
        if fam in excluded:
            held.setdefault((fam, r.get("cell")), []).append(r)
            continue
        by_cell.setdefault((fam, r.get("cell")), []).append(r)
        by_family.setdefault(fam, []).append(r)
    g_clear = (sum(1 for r in live if _clears(r)) / len(live)) if live else 0.0
    fam_rate = {f: (sum(1 for r in rs if _clears(r)) / len(rs)) if rs else 0.0
                for f, rs in by_family.items()}

    # WHAT IS BEING WITHHELD, BY NAME AND BY STATE. Excluding a retracted family
    # silently would be the same error as letting it vote, pointed the other way:
    # nine of the memory's twelve SUPPORTED cells are in `weekend-W7-matched-
    # loser`, and every one of them survives the row-level supersession because
    # the corrected re-runs came AFTER the boundary. They may be entirely sound.
    # The export declines to speak for them and SAYS SO, with the count, so a
    # human at B9 re-admits a known quantity rather than rediscovering it.
    for (fam, cell), rs in sorted(held.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        st = state_of(rs, rules=rules)
        node = excluded[fam].setdefault("cells_withheld_by_state", {})
        node[st["state"]] = node.get(st["state"], 0) + 1

    # And the rows the ROW-LEVEL rule already removed, per family. A family
    # whose every observation predates the boundary has NO surviving cell to
    # withhold, and `cells_withheld_by_state: {}` would then read as "nothing
    # was there" rather than "all of it was retracted".
    for r in all_rows:
        fam = r.get("family_id")
        if fam in excluded and is_superseded(r, rules):
            excluded[fam]["observations_row_superseded"] = (
                excluded[fam].get("observations_row_superseded", 0) + 1)

    groups: dict[tuple[str, str], list[tuple[dict, dict, str]]] = {}
    idea_cells = 0
    for (fam, cell), rs in sorted(by_cell.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        st = state_of(rs, family_rate=fam_rate.get(fam), global_rate=g_clear,
                      rules=rules)
        if st["state"] not in EXPORTED_STATES:
            idea_cells += 1
            continue
        groups.setdefault((fam, st["state"]), []).append(
            (st, _representative(distinct_evidence(rs)), cell))

    out: list[dict] = []
    for (fam, state), members in sorted(groups.items()):
        members.sort(key=lambda m: (float(m[0].get("best_dsr") or 0.0),
                                    m[0].get("passes_clearing_the_bar", 0),
                                    str(m[2])))
        st, obs, cell = members[-1]
        verdict, capped = export_verdict(obs)
        base = {
            "family": fam, "era": "ALL", "state": state,
            "n": obs.get("n_months") if isinstance(obs.get("n_months"), int) else None,
            "sharpe": _num(obs.get("sharpe")),
            "dsr": _num(obs.get("dsr")),
            "spa_p": _num(obs.get("spa_p")),
            "pbo": _num(obs.get("pbo")),
            "verdict": verdict,
            "cells_in_this_state": len(members),
            "representative_cell": cell,
            "distinct_observations": st.get("distinct_observations"),
            "recorded_verdict": (str(obs.get("verdict"))[:160]
                                 if obs.get("verdict") is not None else None),
            "note": capped or st.get("why", "")[:200],
        }
        out.append(base)
        eras = obs.get("eras") or {}
        for era_key in sorted(k for k in eras
                              if isinstance(eras.get(k), dict) and "-" in str(k)):
            cellera = eras[era_key]
            months = cellera.get("months")
            t = cellera.get("t")
            out.append({
                "family": fam, "era": str(era_key), "state": state,
                "n": months if isinstance(months, int) else None,
                # t = SR * sqrt(T) on a monthly series, so the era's own t and
                # month count recover the era's monthly Sharpe. dsr/spa_p/pbo are
                # FULL-SAMPLE corrections and are left null rather than pasted
                # onto a slice they were not computed for.
                "sharpe": (_num(float(t) / (float(months) ** 0.5))
                           if isinstance(t, (int, float)) and isinstance(months, int)
                           and months > 0 else None),
                "dsr": None, "spa_p": None, "pbo": None,
                "verdict": _era_verdict(months, t),
                "cells_in_this_state": len(members),
                "representative_cell": cell,
                "distinct_observations": st.get("distinct_observations"),
                "recorded_verdict": None,
                "note": (f"era slice: mean {cellera.get('mean_pct')}%/mo, t {t}; "
                         f"no deflation and no multiplicity correction on a "
                         f"slice, so it cannot exceed SCREEN_ONLY"),
            })

    meta = {
        "observations_on_file": len(all_rows),
        "observations_counted": len(live),
        "observations_superseded": dict(sorted(dropped.items(), key=lambda kv: -kv[1])),
        "supersession_rules": len(rules),
        "supersession_rule_effects": rule_effect,
        "families_excluded": dict(sorted(excluded.items())),
        "idea_cells_not_exported": idea_cells,
        "cells_exported": sum(r["cells_in_this_state"] for r in out if r["era"] == "ALL"),
    }
    for fam in excluded:
        excluded[fam].setdefault("cells_withheld_by_state", {})
        excluded[fam].setdefault("observations_row_superseded", 0)
    return out, meta


def _render_block(rows: list[dict], meta: dict) -> str:
    """The YAML text, DETERMINISTIC -- no wall clock anywhere in it.

    Idempotence is the requirement and a timestamp would break it on the second
    run, so provenance is carried by a content hash and by the newest
    observation the store held, both of which are functions of the input.
    """
    import hashlib
    import yaml
    payload = {
        "generated_by": "python -m learner.evidence_memory --to-registry",
        "source": "backend/data/optimus/learner/evidence_memory.jsonl",
        "schema": "conditional-evidence-1",
        "read_only_until": (
            "B9. Nothing in backend/services/signal_registry.py reads this "
            "block: Registry is built from schema/written/signals/"
            "standing_constraints/source_of_truth and has no field for it. It "
            "is a record for humans and for B9, not an input to allocation."),
        "verdict_vocabulary": list(VERDICT_VOCABULARY),
        "rules": [
            "a SCREEN cannot reach NOVEL -- no book, no Sharpe, no deflation",
            "an ERA SLICE cannot exceed SCREEN_ONLY -- no deflation, no "
            "multiplicity correction on a third of one sample",
            "the export never grades ABOVE the job's own recorded verdict",
            "a SUPERSEDED or RETRACTED family is not exported at all; the "
            "families_excluded block names each one and why",
            "IDEA cells are not exported -- fewer than two distinct "
            "observations is not evidence",
        ],
        "provenance": {
            "observations_on_file": meta["observations_on_file"],
            "observations_counted": meta["observations_counted"],
            # A LIST, not a dict keyed by the reason: a 250-character key drives
            # PyYAML into its `? ... :` complex-key form, which is valid and
            # unreadable, and this block is meant to be read by a human at B9.
            "observations_superseded": [
                {"n": n, "why": why}
                for why, n in meta["observations_superseded"].items()],
            "supersession_rules": meta["supersession_rules"],
            "newest_observation_utc": meta.get("newest_observation_utc"),
            "rows_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16],
        },
        "families_excluded": meta["families_excluded"],
        "idea_cells_not_exported": meta["idea_cells_not_exported"],
        "cells_exported": meta["cells_exported"],
        "rows": rows,
    }
    body = yaml.safe_dump({"conditional_evidence": payload}, sort_keys=False,
                          default_flow_style=False, width=96, allow_unicode=False)
    return f"{_BEGIN}\n{body}{_END}\n"


def to_registry(registry_path: str | Path | None = None, *,
                dry_run: bool = False,
                rows: list[dict] | None = None,
                rules: list[dict] | None = None) -> dict:
    """Write the `conditional_evidence:` block. Idempotent, byte-for-byte.

    The file is edited as TEXT between two markers, never round-tripped through
    a YAML loader: `signal_registry.yaml` is 56 lines of reasoned comment before
    its first key, and `yaml.safe_dump` of a parsed copy would delete every one
    of them while the diff looked like a rewrite of the whole registry. Only the
    bytes between the markers move; everything outside them is copied verbatim,
    including its line endings, which are CRLF on this file.
    """
    path = Path(registry_path or REGISTRY_YAML)
    if not path.exists():
        raise EvidenceMemoryError(f"signal registry not found at {path}")
    all_rows = read_all() if rows is None else rows
    exported, meta = registry_rows(all_rows, rules)
    meta["newest_observation_utc"] = max(
        (str(r.get("utc")) for r in all_rows if r.get("utc")), default=None)

    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    flat = raw.replace("\r\n", "\n")
    block = _render_block(exported, meta)

    if _BEGIN in flat:
        head, rest = flat.split(_BEGIN, 1)
        if _END not in rest:
            raise EvidenceMemoryError(
                f"{path.name} has a BEGIN marker and no END marker. Refusing to "
                f"guess where the generated block stops -- a wrong guess "
                f"silently deletes a hand-written registry entry.")
        tail = rest.split(_END, 1)[1]
        if tail.startswith("\n"):
            tail = tail[1:]
        new_flat = head + block + tail
    else:
        new_flat = (flat if flat.endswith("\n") else flat + "\n") + "\n" + block

    new_raw = new_flat.replace("\n", "\r\n") if crlf else new_flat
    changed = new_raw.encode("utf-8") != raw.encode("utf-8")

    # The block must never be able to break the file for the readers that DO
    # exist. Parse the result before it is allowed to land.
    import yaml
    parsed = yaml.safe_load(new_raw)
    if not isinstance(parsed, dict) or "signals" not in parsed:
        raise EvidenceMemoryError(
            "the rewritten registry does not parse as a registry -- refusing "
            "to write it")
    untouched = {k: v for k, v in parsed.items() if k != "conditional_evidence"}
    before = yaml.safe_load(raw) or {}
    before.pop("conditional_evidence", None)
    if untouched != before:
        raise EvidenceMemoryError(
            "writing conditional_evidence would change another block of the "
            "registry -- refusing. This is the check that makes 'appends only' "
            "a fact rather than an intention.")

    if not dry_run and changed:
        path.write_bytes(new_raw.encode("utf-8"))

    return {
        "registry": str(path),
        "dry_run": bool(dry_run),
        "changed": bool(changed),
        "rows_written": len(exported),
        "rows_by_state": _count(exported, "state"),
        "rows_by_era": _count(exported, "era"),
        "rows_by_verdict": _count(exported, "verdict"),
        "families_exported": sorted({r["family"] for r in exported}),
        "families_excluded": meta["families_excluded"],
        "idea_cells_not_exported": meta["idea_cells_not_exported"],
        "cells_exported": meta["cells_exported"],
        "observations_on_file": meta["observations_on_file"],
        "observations_counted": meta["observations_counted"],
        "observations_superseded": meta["observations_superseded"],
        "supersession_rule_effects": meta["supersession_rule_effects"],
        "rows": exported,
    }


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="evidence memory")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--show-superseded", action="store_true",
                    help="print the supersession rules and what each one excludes")
    ap.add_argument("--ingest-dir", help="fold every *.json receipt in a directory")
    ap.add_argument("--to-registry", action="store_true",
                    help="write the conditional_evidence block into "
                         "backend/data/signal_registry.yaml (read-only for the "
                         "PM until B9)")
    ap.add_argument("--registry", default=None,
                    help="path to the registry YAML (default: the repo's)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --to-registry: derive and report, write nothing")
    ap.add_argument("--receipt", default=None,
                    help="write the run receipt to this JSON path")
    a = ap.parse_args(argv)
    if a.ingest_dir:
        n = 0
        for p in sorted(Path(a.ingest_dir).glob("*.json")):
            try:
                n += record_receipt(json.loads(p.read_text(encoding="utf-8")))
            except Exception as exc:                                    # noqa: BLE001
                print(f"  {p.name}: {type(exc).__name__}: {exc}")
        print(f"folded {n} cell observations")
    if a.show_superseded:
        rules = read_supersessions()
        rows = read_all()
        if not rules:
            print("no supersession rules -- every observation on file is counted")
        for r in rules:
            n = sum(1 for x in rows if is_superseded(x, [r]))
            print("")
            print(f"  family    {r.get('family_id')}")
            print(f"  before    {r.get('before_utc')}")
            print(f"  excludes  {n} observations")
            print(f"  why       {r.get('why')}")
        print("")
        print("Nothing is deleted: `read_all()` still returns every row. The "
              "difference between 'we never saw this' and 'we saw it and then "
              "learned the instrument was broken' is why the file is kept.")
        return 0
    if a.to_registry:
        rec = to_registry(a.registry, dry_run=a.dry_run)
        printable = {k: v for k, v in rec.items() if k != "rows"}
        print(json.dumps(printable, indent=1, default=str))
        for r in rec["rows"]:
            print(f"  {r['family']:<34} {r['era']:<11} {r['state']:<16} "
                  f"n={r['n']} verdict={r['verdict']}")
        if a.receipt:
            rp = Path(a.receipt)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
            print(f"receipt -> {rp}")
        return 0
    s = snapshot()
    print(json.dumps({k: v for k, v in s.items() if k != "by_cell"}, indent=1))
    for k, v in list(s["by_cell"].items())[:15]:
        print(f"  {v['state']:<16} {k[:80]}  ({v['why'][:70]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
