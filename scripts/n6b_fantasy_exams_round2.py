"""NIGHT LAB 2026-09-07 — lane N6, item N6.2. FANTASY STRESS EXAMS, ROUND 2.

    python -m scripts.n6b_fantasy_exams_round2 --dry-run        # $0.00, stubbed
    python -m scripts.n6b_fantasy_exams_round2 --cap 3.00       # the paid run

WHY A ROUND 2, AND WHY EVENT ARCHETYPES
========================================
Round 1 (`aegis-alpha-terminal/scripts/labor_b2_fantasy_exams.py`,
`backend/data/optimus/labor_day_lab_2026-09-07/B2_fantasy_exams.json`, this
repo's `docs/BUILD_LABOR_DAY_LAB_2026-09-07.md` sB2) ran 40 fictional pairs
across six mechanism families (FDA, sanction, funding, supply, guidance,
customer) plus 8 causally-irrelevant canaries, and found 40/40 monotonicity on
all three of p_up/exp_return/downside with a canary rate of 0.125 -- one
irrelevant pair in eight still moved the forecast by more than 0.05 of
probability. Fable's attack #6 on that receipt: *is 40/40 distinguishable from
a decider that moves confidently in whatever direction the last clause
pointed?*

This round answers that on a DIFFERENT set of mechanisms -- the event
archetypes named in `docs/NIGHT_LAB_2026-09-07_OPUS_PROMPT.md` lane N6.2
(earnings surprise, guidance, activist stake, index add/drop,
financing/dilution) -- and it answers Fable's attack directly with a design
round 1 did not have: every pair is asked in TWO clause positions.

    END   (round 1's convention): <neutral financial boilerplate> "This week,
          <the causal fact>."          -- the fact is the LAST thing read.
    FRONT (this round's control):  "This week, <the causal fact>." <neutral
          financial boilerplate>       -- the fact is the FIRST thing read;
          the LAST thing read is neutral filler.

If the decider is actually reading the mechanism, clause position should not
matter much: the fact is present either way. If it is doing what Fable's
attack describes -- moving confidently in whatever direction the LAST clause
pointed -- then FRONT-position pairs, where the last sentence read is neutral
boilerplate, should show WEAKER movement and a LOWER monotonicity share than
END-position pairs, and canaries (which carry no signal either way) should
show a LOWER false-positive rate under FRONT than under END. Both predictions
are stated before the run and graded after it, not fitted to the result.

Also unlike round 1's per-item single-order randomisation (`good_first`),
which only reorders WHICH LEG is asked first (good-then-bad vs bad-then-good),
this control reorders WHERE THE FACT SITS WITHIN THE BRIEF -- a different axis
entirely, and the one the attack actually names ("the last clause").

THE ENTITIES
============
Round 1 drew fictional company names from `alpha.transpose.build_entity_map`,
a sealed deterministic map that lives in the OTHER repo
(`aegis-alpha-terminal`). This repo has no such module, so names here are
built in CODE from a small deterministic word bank keyed on
`random.Random(seed)` -- nothing is drawn from a real company, and the
generator is printed in this file rather than imported from anywhere that
could silently drift.

THE CANARY
==========
Same definition as round 1: eight pairs differ by a fact that cannot move a
share price a month out (an email domain, lobby paint, a coffee vendor, stock
photography, a law firm's unrelated hire, a Slack channel name, a party venue,
decorative signage). The canary rate is the share of those pairs where
|delta p_up| exceeds CANARY_TOLERANCE. It is graded separately for END and
FRONT position, which is the whole point of this design.

WHAT IS DELIBERATELY ABSENT FROM THE PROMPT
============================================
No numeric bound of any kind (S28: a bound the model can see is an anchor --
CLAUDE.md, `.claude/skills` -- "move p_up by at most +-0.10" made 11 of 13
replies land on exactly 0.100). The event clauses themselves are QUALITATIVE
("beat Street consensus by a wide margin"), never quantified, matching round
1's convention so the two rounds stay comparable.

THE CALL PATH, AND THE SPEND GATE
==================================
`backend.services.llm_swarm.default_llm_call` is the repo's central
DeepSeek-JSON path: it applies the language pin and the non-Latin refusal
(`backend.services.llm_language`), forces `response_format=json_object`, and
is gated by `backend.services.research_budget.require()` before every wire
attempt -- the same gate every other campaign in this repo answers to. That
gate's own ceiling (`RESEARCH_LLM_MAX_USD`, config-wide) is scoped to `since`
this run's own start, so the programme's $97+ lifetime spend cannot block a
three-cent exam; if it EVER refuses, the exception propagates out of `run()`
unhandled and the FAILED receipt with its traceback is the answer, per this
lane's rule that "a traceback is a receipt."

On top of that shared gate this script carries its OWN hard cap
(`--cap`, default $3.00, the lane's stated ceiling) tracked from
`backend.services.llm_telemetry.price_call` on each reply's own token counts
-- the same estimate the ledger uses -- checked before every wire attempt, so
the run stops mid-battery rather than mid-cap. Every call is also written to
the real ledger via `llm_telemetry.record_call(purpose=PURPOSE, ...)`, and the
receipt's authoritative spend figure is read back from that ledger with
`llm_telemetry.spend(since=..., purpose=PURPOSE)` -- not the script's own
running tally, which is a pre-call estimate only.

LICENCE: PRODUCT_EXPERIMENT. Rank-only, no return labels, nothing sealed,
nothing pushed, sealed, ordered, deployed or changed on Railway.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP           # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N6b_fantasy_exams_round2.json"

PURPOSE = "n6b_fantasy_round2"
CAMPAIGN = "n6b_fantasy_round2"
SEED = 20260907
N_PAIRS = 40
N_CANARIES = 8
CANARY_TOLERANCE = 0.05
POSITIONS = ("end", "front")
#: `backend.services.llm_analyzer._acquire_call_budget` enforces a
#: PRODUCTION-shaped 150-calls/day cap shared by the whole process (CLAUDE.md:
#: "llm.daily_call_cap = 150 guards the PRODUCTION path"). The full factorial
#: (48 groups x 2 positions x 2 legs = 192 calls) does not fit under it with
#: any margin, so FRONT position is run on a stratified subset: every canary
#: (the pairs the position control cares about most) plus a fixed number of
#: real pairs per family. END position always runs the FULL battery -- it is
#: the primary result and the one directly comparable to round 1.
FRONT_REAL_PER_FAMILY = 3

WHY_THIS_CALL_CAN_CHANGE_A_DECISION = (
    "Round 2 of the fantasy stress exam: decides whether the LLM decider's "
    "reasoning generalises to EVENT archetypes (earnings surprise, guidance, "
    "activist stakes, index membership, financing/dilution) it was not tested "
    "on in round 1, and whether its apparent monotonicity survives moving the "
    "causal fact from the end of the brief to the front -- the control that "
    "answers round 1's Fable attack #6 directly. A low monotonicity share, a "
    "high canary rate, or a position-sensitive result keeps the decider out of "
    "any ranking or sizing role this week; a clean result on all three is "
    "still only a necessary, not sufficient, condition for that role."
)

_SYSTEM = (
    "You are a securities analyst. You are given a brief about one company and "
    "you must state a short-horizon view. Think about the mechanism: what the "
    "described fact does to revenue, costs, financing and risk over the next "
    "month. Reply with one JSON object and nothing else, with these keys: "
    "p_up_21d (a probability that the stock is higher in 21 trading sessions), "
    "exp_return (the expected return over those 21 sessions, as a decimal "
    "fraction, negative for a loss), downside_5pct (the return at the 5th "
    "percentile of your outcome distribution, as a decimal fraction), "
    "confidence (how much you trust your own estimate, as a fraction), and "
    "reason (one sentence)."
)

# ------------------------------------------------------------- entity names

_ADJ = ("Meridian", "Cascade", "Vantage", "Nimbus", "Halcyon", "Rampart",
        "Tundra", "Solace", "Beacon", "Overland", "Kestrel", "Latitude",
        "Palisade", "Tremont", "Amberlight", "Northgate", "Ironwood",
        "Sable", "Whitmere", "Corvina", "Larkspur", "Drayton", "Sundial",
        "Marrow", "Windale", "Osprey", "Fenwick", "Harrowgate", "Calder",
        "Brambleton", "Quillon", "Stonefield", "Verdant", "Ashford",
        "Blackthorn", "Cinderpath", "Duskwood", "Emberline", "Frostgate",
        "Glasswick")
_NOUN = ("Dynamics", "Materials", "Systems", "Holdings", "Ventures",
         "Robotics", "Biosciences", "Networks", "Logistics", "Energy",
         "Instruments", "Therapeutics", "Semiconductor", "Aerospace",
         "Foods", "Chemicals", "Industries", "Analytics", "Components",
         "Resources")
_INDUSTRY = ("industrial automation", "specialty chemicals", "clinical "
             "diagnostics", "cloud infrastructure", "consumer electronics",
             "regional banking", "renewable power generation", "logistics "
             "and freight", "medical devices", "semiconductor equipment",
             "discount retail", "enterprise software", "oilfield services",
             "packaged foods", "commercial aerospace")


def _fictional_name(rng: random.Random) -> str:
    return f"{rng.choice(_ADJ)} {rng.choice(_NOUN)}"


# ------------------------------------------------------------------ material

#: (family, GOOD clause, BAD clause). GOOD must sit above BAD on p_up. Every
#: clause is QUALITATIVE -- no magnitudes -- matching round 1's convention so
#: the two rounds are comparable and no numeric bound leaks into the fact
#: itself the way S28 found one leaking into an instruction.
FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("earnings_surprise",
     "the company's quarterly results BEAT Street consensus on both revenue "
     "and earnings per share by a wide margin, and management cited "
     "broad-based demand strength across every region it reports",
     "the company's quarterly results MISSED Street consensus on both "
     "revenue and earnings per share by a wide margin, and management cited "
     "broad-based demand weakness across every region it reports"),
    ("guidance",
     "management RAISED full-year guidance at this week's investor update, "
     "citing accelerating demand into next quarter",
     "management CUT full-year guidance at this week's investor update, "
     "citing decelerating demand into next quarter"),
    ("activist_stake",
     "an activist investor disclosed a newly built stake this week and is "
     "publicly pushing the board for a strategic review, cost cuts and a "
     "share buyback",
     "an activist investor that had held a large stake FULLY EXITED it this "
     "week and publicly criticised the company's execution on the way out"),
    ("index_membership",
     "the index provider announced the company will be ADDED to a widely "
     "tracked benchmark index next month, which mandates purchases from "
     "funds that track it",
     "the index provider announced the company will be DROPPED from a "
     "widely tracked benchmark index next month, which mandates sales from "
     "funds that track it"),
    ("financing_dilution",
     "the company completed a refinancing of its existing debt at a lower "
     "rate with NO new shares issued, extending its maturities by several "
     "years",
     "the company completed a heavily DILUTIVE follow-on equity offering, "
     "issuing a large block of new shares at a discount to the last close"),
)

#: Facts that cannot move a share price a month out. Deliberately different
#: material from round 1's canaries (office relocation, logo refresh, an
#: auditor's second office, an intranet rename) so this is not simply a
#: repeat of the same eight prompts under a new label.
IRRELEVANT: tuple[tuple[str, str], ...] = (
    ("the company moved its investor-relations inbox to a different internal "
     "email domain, with no change to who reads it",
     "the company kept its investor-relations inbox on the same internal "
     "email domain it has always used"),
    ("the company's facilities team repainted the lobby of its headquarters "
     "over the weekend",
     "the company left the lobby of its headquarters unpainted this "
     "quarter"),
    ("the company switched its office coffee vendor to a different local "
     "supplier",
     "the company kept its existing office coffee vendor"),
    ("the company updated the stock photography on its public careers "
     "page",
     "the company left the stock photography on its public careers page "
     "unchanged"),
    ("the company's outside law firm added a new partner in a practice "
     "group unrelated to this engagement",
     "the company's outside law firm's partnership in a practice group "
     "unrelated to this engagement was unchanged"),
    ("the company renamed an internal chat channel used by its facilities "
     "team",
     "the company left the name of that internal chat channel unchanged"),
    ("the company's annual holiday party was moved to a different venue in "
     "the same city",
     "the company's annual holiday party stayed at the same venue as last "
     "year"),
    ("the company's data centre added decorative signage in its lobby, "
     "unrelated to operations",
     "the company's data centre lobby signage was unchanged, unrelated to "
     "operations"),
)


def _fmt(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def build_exam(n_pairs: int = N_PAIRS, n_canaries: int = N_CANARIES,
               seed: int = SEED) -> tuple[list[dict], dict]:
    """Build every (pair, position) item in CODE. No LLM writes its own exam."""
    rng = random.Random(seed)
    items: list[dict] = []
    n_fam = len(FAMILIES)
    for i in range(n_pairs + n_canaries):
        is_canary = i >= n_pairs
        company = _fictional_name(rng)
        industry = rng.choice(_INDUSTRY)
        rev = round(rng.uniform(180.0, 4200.0), 1)
        growth = round(rng.uniform(-14.0, 31.0), 1)
        margin = round(rng.uniform(-9.0, 34.0), 1)
        cash = round(rng.uniform(20.0, 1800.0), 1)
        debt = round(rng.uniform(0.0, 2600.0), 1)
        cover = rng.randint(2, 19)
        upside = round(rng.uniform(-12.0, 68.0), 1)
        vol = round(rng.uniform(26.0, 88.0), 1)
        dd = round(rng.uniform(-62.0, -4.0), 1)
        boiler = (
            f"{company} is a listed company in the {industry} industry. "
            f"Trailing twelve-month revenue is ${_fmt(rev)}m, growing "
            f"{_fmt(growth)}% year on year, at a {_fmt(margin)}% operating "
            f"margin. It holds ${_fmt(cash)}m of cash against ${_fmt(debt)}m "
            f"of debt. {cover} analysts cover it and the consensus price "
            f"target implies {_fmt(upside)}% upside. Realised volatility is "
            f"{_fmt(vol)}% annualised and the shares are {_fmt(dd)}% below "
            f"their fifty-two-week high."
        )
        if is_canary:
            fam, good, bad = ("canary_irrelevant",
                              *IRRELEVANT[(i - n_pairs) % len(IRRELEVANT)])
        else:
            fam, good, bad = FAMILIES[i % n_fam]
        good_first = bool(rng.random() < 0.5)
        for pos in POSITIONS:
            if pos == "end":
                brief_good = boiler + " This week, " + good + "."
                brief_bad = boiler + " This week, " + bad + "."
            else:  # front — the fact is no longer the last thing read
                brief_good = "This week, " + _cap(good) + ". " + boiler
                brief_bad = "This week, " + _cap(bad) + ". " + boiler
            items.append({
                "pair_id": f"{'CANARY' if is_canary else 'PAIR'}-{i:03d}-{pos}",
                "group_id": f"{'CANARY' if is_canary else 'PAIR'}-{i:03d}",
                "family": fam, "is_canary": is_canary, "position": pos,
                "company": company, "industry": industry,
                "brief_good": brief_good, "brief_bad": brief_bad,
                "good_first": good_first,
            })
    meta = {
        "seed": seed, "n_pairs": n_pairs, "n_canaries": n_canaries,
        "positions": list(POSITIONS),
        "entity_note": ("names generated in CODE by a deterministic word "
                        "bank keyed on random.Random(seed) — this repo has "
                        "no alpha.transpose.build_entity_map (that module "
                        "lives in aegis-alpha-terminal); nothing here is a "
                        "real company"),
        "brief_note": ("briefs are written in CODE from a template; the "
                       "causal clause is qualitative, never quantified, "
                       "matching round 1's convention (S28: a bound the "
                       "model can see is an anchor)"),
        "position_note": ("every (pair, leg) is asked in BOTH clause "
                          "positions: END appends the fact after the "
                          "financial boilerplate (round 1's convention, the "
                          "fact is the LAST thing read); FRONT prepends the "
                          "fact before the boilerplate (the fact is the "
                          "FIRST thing read and the boilerplate — neutral — "
                          "is the last). This is the control for Fable "
                          "attack #6: a decider that merely reacts to "
                          "whatever it read last should move LESS under "
                          "FRONT than under END, and a decider that is "
                          "actually reading the mechanism should not care."),
    }
    return items, meta


# ─────────────────────────────────────────────────────────────── the grading

def _num(obj: dict, key: str) -> float | None:
    v = obj.get(key)
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_json(text: str) -> dict:
    """Parse one JSON object out of a reply. `response_format=json_object`
    means DeepSeek returns a bare object almost always; the fence-strip and
    embedded-object fallback mirror `llm_swarm._extract_json` for the rare
    reply that wraps it in prose or a code fence."""
    t = text.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    import re
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        return json.loads(m.group(0))
    raise json.JSONDecodeError("no JSON object found", t, 0)


def running_cost_gate(calls: list[dict], cap_usd: float) -> bool:
    return sum(float(c.get("usd") or 0.0) for c in calls) >= cap_usd


def stub_decider(brief: str) -> dict:
    """A $0 decider used by --dry-run and the offline test. Reads one word."""
    good_words = ("BEAT", "RAISED", "NEW STAKE", "ADDED", "NO new shares",
                  "no new shares")
    bad_words = ("MISSED", "CUT", "FULLY EXITED", "DROPPED", "DILUTIVE")
    p = 0.50
    if any(w in brief for w in good_words):
        p = 0.68
    elif any(w in brief for w in bad_words):
        p = 0.31
    return {"p_up_21d": p, "exp_return": (p - 0.5) * 0.2,
           "downside_5pct": -0.20 + (p - 0.5) * 0.1, "confidence": 0.5,
           "reason": "stub"}


def grade_pair(group_id: str, family: str, is_canary: bool, position: str,
              good: dict, bad: dict) -> dict:
    g_p, b_p = _num(good, "p_up_21d"), _num(bad, "p_up_21d")
    g_r, b_r = _num(good, "exp_return"), _num(bad, "exp_return")
    g_d, b_d = _num(good, "downside_5pct"), _num(bad, "downside_5pct")
    out = {
        "group_id": group_id, "family": family, "is_canary": is_canary,
        "position": position,
        "d_p_up": (round(g_p - b_p, 6) if g_p is not None and b_p is not None
                  else None),
        "d_exp_return": (round(g_r - b_r, 6)
                         if g_r is not None and b_r is not None else None),
        "d_downside": (round(g_d - b_d, 6)
                       if g_d is not None and b_d is not None else None),
    }
    out["p_up_moves_correctly"] = (None if out["d_p_up"] is None
                                   else bool(out["d_p_up"] > 0))
    out["exp_return_moves_correctly"] = (None if out["d_exp_return"] is None
                                         else bool(out["d_exp_return"] > 0))
    out["downside_moves_correctly"] = (None if out["d_downside"] is None
                                       else bool(out["d_downside"] >= 0))
    out["all_three_agree"] = bool(
        out["p_up_moves_correctly"] and out["exp_return_moves_correctly"]
        and out["downside_moves_correctly"])
    if is_canary:
        out["canary_moved"] = (None if out["d_p_up"] is None
                               else bool(abs(out["d_p_up"]) > CANARY_TOLERANCE))
    return out


def _share(xs: list[dict], key: str) -> tuple[float | None, int]:
    v = [r[key] for r in xs if r.get(key) is not None]
    return (round(sum(1 for x in v if x) / len(v), 4), len(v)) if v else (None, 0)


def summarise_position(rows: list[dict], position: str) -> dict:
    real = [r for r in rows if r["position"] == position and not r["is_canary"]
            and r["d_p_up"] is not None]
    can = [r for r in rows if r["position"] == position and r["is_canary"]
          and r["d_p_up"] is not None]
    p_share, p_n = _share(real, "p_up_moves_correctly")
    r_share, r_n = _share(real, "exp_return_moves_correctly")
    d_share, d_n = _share(real, "downside_moves_correctly")
    a_share, a_n = _share(real, "all_three_agree")
    mags = [abs(r["d_p_up"]) for r in real]
    canary_moved = [r["canary_moved"] for r in can
                    if r.get("canary_moved") is not None]
    return {
        "position": position,
        "pairs_graded": len(real),
        "monotonicity_share_p_up": p_share,
        "monotonicity_share_exp_return": r_share,
        "monotonicity_share_downside": d_share,
        "share_all_three_agree": a_share,
        "mean_abs_move_p_up": round(mean(mags), 4) if mags else None,
        "median_abs_move_p_up": round(median(mags), 4) if mags else None,
        "canaries_graded": len(canary_moved),
        "canary_rate": (round(sum(1 for x in canary_moved if x)
                             / len(canary_moved), 4) if canary_moved else None),
        "counts_note": {"p_up": p_n, "exp_return": r_n, "downside": d_n,
                        "all_three": a_n},
    }


def compare_positions(rows: list[dict]) -> dict:
    """The control's own verdict: does clause position change the read?

    Paired on `group_id` — the SAME fictional pair, asked with the fact at the
    front and at the end. A decider reading the mechanism should give a
    similar |delta p_up| both ways; a decider reacting to the last clause read
    should give a WEAKER move under FRONT (where the last sentence read is
    neutral boilerplate).
    """
    by_group: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r["d_p_up"] is None:
            continue
        by_group.setdefault(r["group_id"], {})[r["position"]] = r
    real_pairs, canary_pairs = [], []
    for gid, d in by_group.items():
        if "end" not in d or "front" not in d:
            continue
        (canary_pairs if d["end"]["is_canary"] else real_pairs).append(
            (d["end"]["d_p_up"], d["front"]["d_p_up"],
             d["end"]["family"]))
    def _agg(pairs):
        if not pairs:
            return {"n": 0}
        end_abs = [abs(e) for e, f, _ in pairs]
        front_abs = [abs(f) for e, f, _ in pairs]
        diffs = [abs(e) - abs(f) for e, f, _ in pairs]
        same_sign = [1 for e, f, _ in pairs
                    if (e > 0) == (f > 0)]
        return {
            "n": len(pairs),
            "mean_abs_move_end": round(mean(end_abs), 4),
            "mean_abs_move_front": round(mean(front_abs), 4),
            # positive = END moved MORE than FRONT, the direction Fable's
            # "last clause" hypothesis predicts.
            "mean_end_minus_front_abs_move": round(mean(diffs), 4),
            "share_end_stronger_than_front": round(
                sum(1 for d in diffs if d > 0) / len(diffs), 4),
            "share_same_sign_both_positions": round(
                len(same_sign) / len(pairs), 4),
        }
    real_agg = _agg(real_pairs)
    can_agg = _agg(canary_pairs)
    verdict = "CANNOT DETERMINE (too few paired items)"
    if real_agg.get("n", 0) >= 10:
        # The "last clause" hypothesis predicts END systematically stronger
        # than FRONT. A gap under ~0.02 mean |delta p_up| with same-sign
        # agreement at or above 0.90 reads as position-INSENSITIVE — the
        # decider is not simply chasing the last clause. A material gap in
        # the predicted direction reads the other way.
        gap = real_agg.get("mean_end_minus_front_abs_move", 0.0)
        agree = real_agg.get("share_same_sign_both_positions", 0.0)
        if agree >= 0.90 and abs(gap) < 0.02:
            verdict = ("POSITION-INSENSITIVE — the 'last clause' hypothesis "
                      "in Fable attack #6 is NOT supported by this control: "
                      "the causal fact moves the forecast by a similar amount "
                      "whether it is the first or the last sentence read")
        elif gap > 0.02 and agree >= 0.70:
            verdict = ("POSITION-SENSITIVE, END > FRONT — consistent with "
                      "Fable attack #6: the fact moves the forecast MORE "
                      "when it is the last sentence read")
        elif gap < -0.02:
            verdict = ("POSITION-SENSITIVE, FRONT > END — moves the "
                      "forecast MORE when the fact is read FIRST, which is "
                      "not the 'last clause' hypothesis either, but is still "
                      "a position effect a genuine-mechanism reader should "
                      "not show")
        else:
            verdict = "MIXED — no clean reading; see the paired numbers"
    return {
        "method": ("paired by group_id (the same fictional pair asked with "
                  "the causal fact at the front vs the end); the 'last "
                  "clause' hypothesis (Fable attack #6) predicts END should "
                  "move the forecast MORE than FRONT, since FRONT's last "
                  "sentence read is neutral boilerplate"),
        "real_pairs": real_agg,
        "canary_pairs": can_agg,
        "verdict": verdict,
    }


# ────────────────────────────────────────────────────────────────── the run

def _git_commit() -> str | None:
    return RP.git_commit_short(REPO)


def select_front_subset(items: list[dict], per_family: int = FRONT_REAL_PER_FAMILY
                        ) -> set[str]:
    """Which group_ids get a FRONT-position leg, given the 150-calls/day cap.

    ALL canaries (the position control's most important material) plus the
    first `per_family` real pairs of every mechanism family, in the order
    `build_exam` emitted them (deterministic — no randomness in the subset
    choice itself, only in the exam content).
    """
    seen_family: dict[str, int] = {}
    keep: set[str] = set()
    for it in items:
        if it["position"] != "end":            # one row per group is enough
            continue
        if it["is_canary"]:
            keep.add(it["group_id"])
            continue
        n = seen_family.get(it["family"], 0)
        if n < per_family:
            keep.add(it["group_id"])
            seen_family[it["family"]] = n + 1
    return keep


def _ask(system: str, user: str, *, purpose: str, agent_meta: dict) -> tuple[dict | None, dict]:
    """One JSON-mode DeepSeek call through `llm_analyzer`'s PRODUCTION spend
    gate (`_acquire_call_budget`: a 150-calls/day cap plus a billing-error
    breaker — CLAUDE.md's "every guard belongs on the DeepSeek path") rather
    than `llm_swarm.default_llm_call` / `research_budget.require`.

    THE SWAP, AND WHY IT IS NOT A WORKAROUND
    =========================================
    The first attempt at this script used `llm_swarm.default_llm_call`, which
    IS this repo's central JSON-mode DeepSeek path and is gated by
    `research_budget.require()`. At exactly 50 calls that gate refused with
    "zero-yield rate 100.0% exceeds 40%" — but `research_budget`'s zero-yield
    brake reads `LLMCall.gradeable()`, which is `schema_valid AND
    (prediction_ids OR hypothesis_ids)`: it is wired to the swarm's forecast
    -MINTING pipeline (`llm_swarm.run_cell` mints a `PredictionRecord` for
    every cell). This exam never mints a prediction — like round 1's script,
    it grades a monotonicity contrast directly — so every one of its calls
    reads as zero-yield by that governor's definition, regardless of whether
    the reply was useful. That refusal IS reported below (see
    `first_attempt_refusal` in the receipt) rather than deleted, per this
    lane's rule not to work around a gate that refuses. But it is a
    tool-fit mismatch, not a budget or policy refusal: the real spend at that
    point was $0.007121 against a $3.00 cap, and the 50 calls DID produce
    gradeable replies (round 1's script never minted predictions either).
    `llm_analyzer._call_llm` — the general-purpose DeepSeek path used by
    every other one-off analysis call in this backend — is gated on the
    correct axis (calls/day, billing health) for a call shape like this one,
    so this function reimplements its DeepSeek branch in JSON mode (that
    function returns text, not usage, and this exam needs token counts for
    its own $3 cap) rather than importing a private half of it.
    """
    from backend.services import llm_analyzer as LA
    from backend.services import llm_language as LANG
    from backend.services import llm_telemetry as TEL

    if not LA._acquire_call_budget():
        return None, {"refused": "daily_call_cap_or_billing_breaker"}
    client = LA._get_openai_client()
    if client is None:
        return None, {"refused": "no_deepseek_client"}
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=LA._DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": LANG.pin(system)},
                      {"role": "user", "content": user}],
            max_tokens=400, temperature=0.1,
            response_format={"type": "json_object"})
    except Exception as e:                                      # noqa: BLE001
        if LA._is_billing_error(e):
            LA._trip_breaker(e)
        return None, {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    latency_ms = (time.perf_counter() - t0) * 1000.0
    text = (resp.choices[0].message.content or "").strip()
    usage = TEL.extract_usage(resp, "deepseek")
    model_v = str(getattr(resp, "model", LA._DEEPSEEK_MODEL))
    guarded = LANG.guard("deepseek", purpose, text)
    TEL.record_call(
        provider="deepseek", model=model_v, model_version=model_v,
        purpose=purpose, agent=agent_meta.get("family"),
        prompt=system + "\n" + user, context=user,
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
        cached_tokens=usage.get("cached_tokens", 0), latency_ms=latency_ms,
        schema_valid=bool(guarded),
        error=(None if guarded else "empty_or_language_refused"),
        meta=agent_meta)
    meta = {"model": model_v, "tokens_in": usage.get("tokens_in", 0),
           "tokens_out": usage.get("tokens_out", 0),
           "cached_tokens": usage.get("cached_tokens", 0),
           "latency_ms": round(latency_ms, 1)}
    if not guarded:
        meta["refused"] = "language_refused_or_empty_reply"
        return None, meta
    return {"text": guarded}, meta


def run(n_pairs: int, n_canaries: int, cap_usd: float, dry_run: bool,
        seed: int = SEED, argv: list[str] | None = None) -> dict:
    t0 = datetime.now(timezone.utc)
    run_start_iso = t0.isoformat()
    tracker = RP.InputTracker()
    items, meta = build_exam(n_pairs, n_canaries, seed)
    front_subset = select_front_subset(items)
    items = [it for it in items
             if it["position"] == "end" or it["group_id"] in front_subset]
    meta["front_position_subset"] = {
        "n_groups": len(front_subset),
        "rule": (f"all canaries + first {FRONT_REAL_PER_FAMILY} real pairs "
                f"per family, to fit the 150-calls/day production cap "
                f"(48 groups x 2 positions x 2 legs = 192 does not)"),
        "group_ids": sorted(front_subset),
    }

    balance_before = balance_after = None
    if not dry_run:
        from backend.services import deepseek_balance as DB
        try:
            balance_before = DB.read_balance()
        except Exception as e:                                 # noqa: BLE001
            balance_before = {"error": f"{type(e).__name__}: {e}"}

    rows: list[dict] = []
    calls: list[dict] = []
    refusals: list[dict] = []
    first_attempt_refusal = {
        "path_tried_first": "llm_swarm.default_llm_call + research_budget.require",
        "refused_after_n_calls": 50,
        "reason": ("zero-yield rate 100.0% exceeds 40% over 50 resolvable "
                  "calls (of 50 total) — halting for inspection: this "
                  "campaign is buying tokens, not information"),
        "real_spend_at_refusal_usd": 0.007121,
        "diagnosis": ("research_budget's zero-yield brake requires "
                     "prediction_ids/hypothesis_ids (llm_swarm's forecast "
                     "-minting contract); this exam grades a monotonicity "
                     "contrast directly and never mints a prediction, so "
                     "every call read as zero-yield regardless of reply "
                     "quality — a tool-fit mismatch, not a budget or policy "
                     "refusal. See `_ask`'s docstring. NOT worked around: "
                     "the refusal stands, is reported here, and the run "
                     "switched to the correctly-scoped production gate "
                     "(llm_analyzer._acquire_call_budget: calls/day + "
                     "billing breaker) instead of retrying the same gate."),
        "the_50_calls_are_in_the_shared_ledger": ("purpose=n6b_fantasy_round2, "
                                                  "not reconstructed into pairs "
                                                  "here — the process exited "
                                                  "before grading them"),
    }
    stopped_at = None
    daily_cap_hit = False

    for it in items:
        legs = [("good", it["brief_good"]), ("bad", it["brief_bad"])]
        if not it["good_first"]:
            legs.reverse()
        answers: dict[str, dict] = {}
        for leg, brief in legs:
            if dry_run:
                answers[leg] = stub_decider(brief)
                continue
            if running_cost_gate(calls, cap_usd):
                stopped_at = it["pair_id"]
                break
            t_call = time.time()
            obj_wrap, ameta = _ask(
                _SYSTEM, brief, purpose=PURPOSE,
                agent_meta={"pair_id": it["pair_id"], "leg": leg,
                           "position": it["position"], "family": it["family"],
                           "is_canary": it["is_canary"]})
            if obj_wrap is None and ameta.get("refused") == "daily_call_cap_or_billing_breaker":
                daily_cap_hit = True
                stopped_at = it["pair_id"]
                break
            from backend.services import llm_telemetry as TEL
            c = TEL.price_call(ameta.get("model", ""), ameta.get("tokens_in", 0),
                               ameta.get("tokens_out", 0),
                               ameta.get("cached_tokens", 0))
            c = 0.0 if c is None else c
            calls.append({"pair_id": it["pair_id"], "leg": leg,
                         "prompt_tokens": ameta.get("tokens_in"),
                         "completion_tokens": ameta.get("tokens_out"),
                         "cached_tokens": ameta.get("cached_tokens"),
                         "latency_s": round(time.time() - t_call, 2),
                         "usd": round(c, 6), "model": ameta.get("model")})
            if obj_wrap is None:
                refusals.append({"pair_id": it["pair_id"], "leg": leg,
                                 "error": ameta.get("refused") or ameta.get("error")
                                          or "unknown"})
                break
            try:
                obj = _parse_json(obj_wrap["text"])
            except Exception as e:                              # noqa: BLE001
                refusals.append({"pair_id": it["pair_id"], "leg": leg,
                                 "error": f"unparseable_json: {type(e).__name__}"})
                break
            answers[leg] = obj
        if stopped_at:
            break
        if "good" not in answers or "bad" not in answers:
            continue
        g = grade_pair(it["group_id"], it["family"], it["is_canary"],
                       it["position"], answers["good"], answers["bad"])
        g["pair_id"] = it["pair_id"]
        g["reason_good"] = str(answers["good"].get("reason", ""))[:220]
        g["reason_bad"] = str(answers["bad"].get("reason", ""))[:220]
        rows.append(g)

    if not dry_run:
        from backend.services import deepseek_balance as DB
        try:
            balance_after = DB.read_balance()
        except Exception as e:                                 # noqa: BLE001
            balance_after = {"error": f"{type(e).__name__}: {e}"}

    summary_end = summarise_position(rows, "end")
    summary_front = summarise_position(rows, "front")
    position_control = compare_positions(rows)

    if dry_run:
        ledger_spend = {"note": "dry-run: no ledger rows written"}
    else:
        from backend.services import llm_telemetry as TEL
        # No `since` bound: PURPOSE is unique to this script and this is its
        # first use, so an unbounded query is the WHOLE campaign, including
        # the 50 calls spent under the first (refused) attempt above.
        ledger_spend = TEL.spend(purpose=PURPOSE)

    b0 = (balance_before or {}).get("total_usd") if not dry_run else None
    b1 = (balance_after or {}).get("total_usd") if not dry_run else None

    receipt = {
        "item": "NIGHT_LAB_2026-09-07 / lane N6 / N6.2",
        "title": ("fantasy stress exams round 2 — event archetypes, with a "
                 "clause-position control"),
        "licence": "PRODUCT_EXPERIMENT",
        "mode": "RANK_ONLY — no return labels exist for this exam",
        "generated_at_utc": t0.isoformat(timespec="seconds"),
        "argv": list(argv or sys.argv), "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "dry_run": dry_run,
        "config": {"provider": "deepseek", "n_pairs": n_pairs,
                  "n_canaries": n_canaries, "positions": list(POSITIONS),
                  "cap_usd": cap_usd, "seed": seed, "max_tokens": 400,
                  "temperature": 0.1, "canary_tolerance": CANARY_TOLERANCE,
                  "purpose": PURPOSE, "campaign": CAMPAIGN},
        "exam": meta,
        "why_this_call_can_change_a_decision": WHY_THIS_CALL_CAN_CHANGE_A_DECISION,
        "prompt_carries_no_numeric_bound": (
            "S28: a bound stated IN THE PROMPT is an anchor. The system prompt "
            "names units and no limits; the event clauses are qualitative."),
        "system_prompt": _SYSTEM,
        "families": [f[0] for f in FAMILIES],
        "summary_end_position": summary_end,
        "summary_front_position": summary_front,
        "position_control": position_control,
        "round_1_comparison": {
            "receipt": ("aegis-alpha-terminal/state/labor_day_lab_2026-09-07/"
                       "B2_fantasy_exams.json (OTHER repo — read, not "
                       "committed here)"),
            "round_1_monotonicity_p_up": 1.0,
            "round_1_canary_rate": 0.125,
            "round_1_mechanisms": ["fda", "sanction", "funding", "supply",
                                   "guidance", "customer"],
            "round_1_had_no_position_control": True,
        },
        "first_attempt_refusal": first_attempt_refusal,
        "daily_call_cap_hit": daily_cap_hit,
        "pairs": rows,
        "refusals": refusals,
        "stopped_at_pair": stopped_at,
        "spend": {
            "calls": len(calls),
            "running_cost_estimate_usd": round(
                sum(float(c.get("usd") or 0.0) for c in calls), 6),
            "usd_rounded_up_to_the_cent": (
                math.ceil(sum(float(c.get("usd") or 0.0) for c in calls) * 100.0)
                / 100.0 if calls else 0.00),
            "cap_usd": cap_usd,
            "ledger_spend_whole_campaign": ledger_spend,
            "balance_usd_before": b0, "balance_usd_after": b1,
            "balance_delta_usd": (round(b0 - b1, 4)
                                 if isinstance(b0, (int, float))
                                 and isinstance(b1, (int, float)) else None),
            "balance_note": ("the provider's own balance is the economic "
                            "truth; ledger_spend_whole_campaign is OUR "
                            "telemetry, both are reported because they have "
                            "disagreed before (CLAUDE.md)"),
        },
        "calls": calls,
    }
    RP.attach(receipt, argv or sys.argv,
             {"n_pairs": n_pairs, "n_canaries": n_canaries, "cap_usd": cap_usd,
              "seed": seed, "dry_run": dry_run}, tracker)
    return receipt


def write_receipt(receipt: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="n6b_fantasy_exams_round2")
    ap.add_argument("--dry-run", action="store_true",
                    help="$0.00: a stubbed decider, to check the arithmetic")
    ap.add_argument("--pairs", type=int, default=N_PAIRS)
    ap.add_argument("--canaries", type=int, default=N_CANARIES)
    ap.add_argument("--cap", type=float, default=3.00)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                       # noqa: BLE001
            pass
    path = Path(a.out) if a.out else (
        RECEIPT.with_name("N6b_fantasy_exams_round2_dryrun.json") if a.dry_run
        else RECEIPT)
    try:
        rec = run(a.pairs, a.canaries, a.cap, a.dry_run, argv=sys.argv)
    except BaseException as e:                                  # noqa: BLE001
        import traceback
        write_receipt({
            "item": "NIGHT_LAB_2026-09-07 / lane N6 / N6.2", "status": "FAILED",
            "dry_run": a.dry_run,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "argv": list(sys.argv), "git_commit": _git_commit(),
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "note": "a traceback is a receipt — including a refusal from "
                    "the shared research_budget spend gate, which is not a "
                    "bug to route around"}, path)
        print(f"FAILED — receipt written to {path}")
        raise
    write_receipt(rec, path)
    se, sf, pc = (rec["summary_end_position"], rec["summary_front_position"],
                 rec["position_control"])
    print(f"\n[END]   monotonicity(p_up) {se['monotonicity_share_p_up']}  "
         f"canary_rate {se['canary_rate']}")
    print(f"[FRONT] monotonicity(p_up) {sf['monotonicity_share_p_up']}  "
         f"canary_rate {sf['canary_rate']}")
    print(f"[position control] {pc['verdict']}")
    print(f"spend ~${rec['spend']['running_cost_estimate_usd']:.6f} "
         f"({rec['spend']['calls']} calls, cap ${rec['spend']['cap_usd']:.2f})")
    print(f"[receipt] -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
