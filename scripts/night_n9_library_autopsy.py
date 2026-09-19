"""N9 -- mine the 85%: LLM autopsies of the moves the precursor library missed.

RE-TEST 3 OF THE 2026-09-19 FAILURE THESIS
==========================================
`NEGATIVE_RESULTS.md` §51 (N4) measured the programme metric nobody had:

    horizon  tail     n      covered   NO WARNING AT ALL
    20d      bottom   4,118  14.4%     85.6%
    60d      bottom   4,094  12.4%     87.6%

and then measured why that number is worse than it looks -- **the library fires
on 15.3% of ALL days**, so 12-17% coverage of exceptional moves IS the base
rate. Mean lift 0.82-1.15 against an MDE of 0.25-0.62: NO COVERAGE, at every
horizon, in both tails.

§51's own closing paragraph says what that is a verdict ON: *"This is a fair
test of a SIX-rule library, not a verdict on precursors. Six rules from six
autopsies of SPY sell decisions were never going to cover the tails of six ETFs
across 27 years... the library is currently far too small to be doing the job
it is being validated for."* The fix it names, in the same section, is more
autopsy-generated precursors at ~$0.001 each. The 2026-09-19 failure thesis
ranks it the **cheapest lever in the file**.

WHAT THIS JOB DOES, AND THE ONE THING IT MUST NOT DO
====================================================
It runs the EXISTING autopsy machinery over the UNWARNED exceptional moves --
the ones where nothing in the incumbent library fired in the sessions before
the move -- and files what the reader proposes as **CANDIDATES**.

A candidate is not a library member and this job cannot make one. A precursor
enters the library only through `scripts/library_measure_*` +
`scripts/library_placebo_null`, and that separation is §37/§41's lesson paid
for in full: **a verdict that KILLS or ADMITS is the hardest kind to notice
being wrong**, and §41 found that every refutation one standard produced had
been manufactured by its own denominator. A generator that could also admit its
own output would be the same defect with the sign flipped.

So the output here is a JSONL of proposals, each carrying the move it was
written from, the precursor in the closed grammar, its testable definition and
the reader's own stated evidence -- and `status: "CANDIDATE"` on every row,
written by this file and asserted by its tests.

THE GRAMMAR IS THE BINDING CONSTRAINT, AND IT IS N9's OWN FINDING
=================================================================
`scripts/n9_mine_the_85.py` asked the question that comes before paying for
autopsies: does ANY rule in the eight-feature transferable vocabulary mark the
uncovered moves? A proposal that does not compile into
`research_gym.autopsy.TRANSFERABLE_FEATURES` is untestable BY CONSTRUCTION, so
it is REFUSED at the door here (`REFUSED_VOCABULARY`), counted, and the refusal
rate is on the receipt. A refusal is a finding: a run where most proposals fail
to compile is a statement about the language, not about the moves.

THE MONEY, AND THE TWO WAYS A CAP STOPS BEING A CAP
===================================================
`config.N9_LIBRARY_AUTOPSY_MAX_USD` ($10.00) caps ONE RUN. The cap is checked
BEFORE every submission and never refunded after -- a call that was made and
then regretted has already been billed. The spend printed on the receipt is
read from the CALL LEDGER (`llm_telemetry.read_calls`), never from a constant:
`L2_typed_events` carried a literal zero for `llm_spend_usd` and reported a
$2.384 run as free.

That was not enough, and the first probe proved it. **2026-09-19 14:10 local,
`--max-usd 1.0 --workers 2 --reader deepseek`:** DeepSeek renamed
`deepseek-chat`'s served model to `deepseek-flash` on 2026-09-14, the price
table did not carry the new id, and all 424 of that run's ledger rows came back
`cost_usd: null`. `spend_from_ledger` sums a null as 0.0, so the $1.00 cap read
**$0.00 for fifteen minutes** while the provider balance moved **$0.21**. The
cap was not loose; it could not bind at all.

  * **`REFUSED_UNPRICED_CALL`** -- ANY ledger row for this run's purpose whose
    `cost_usd` is None is a cap breach by definition, because every total that
    sums it treats it as zero. Checked at each flush (the cadence the cap
    already re-reads the ledger at), the run stops there, and the receipt names
    the model id it could not price.
  * **`REFUSED_NO_LEDGER`** -- a paid run refuses to start when the ledger the
    cap reads cannot be read or appended to. Not `LLM_CALLS.exists()`: the
    ledger rotated to one file a month on 2026-09-12 and the monolith is
    legitimately gone, so that check could never go green. What is checked is
    the STREAM and the directory it appends into. An unmetered (local) reader
    skips it, because no dollar cap can bind on a free run.

AND EVERY EXIT WRITES ITS ROWS
==============================
The same probe filed 400 candidates, was interrupted, and left **no receipt** --
`night_factory_jobs.main()` writes the receipt only after this function
RETURNS, so fifteen minutes of billed calls had nothing naming what they
bought. The autopsy loop now flushes and RETURNS on any `BaseException`,
`KeyboardInterrupt` included, with `stopped: "INTERRUPTED"` and its reason. The
cursor is at the flushed rows, so a resumed run re-bills none of them.

    python -m scripts.night_factory_jobs N9_library_autopsy --smoke
    python -m scripts.night_factory_jobs N9_library_autopsy --max-usd 2 --workers 4
    python -m scripts.night_factory_jobs N9_library_autopsy --reader local

LICENCE: PRODUCT_EXPERIMENT. Nothing here orders, promotes, or enters a library.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from backend.services.research_gym import autopsy as AU

logger = logging.getLogger("n9_library_autopsy")

JOB = "N9_library_autopsy"
LICENCE = "PRODUCT_EXPERIMENT"
PURPOSE = "n9_library_autopsy"

#: Never a literal (2026-09-18: three idle-queue jobs overwrote committed
#: receipts three nights running). Unset means TODAY.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

#: The HELD panel. `n9_mine_the_85.py` selected rules on SPY/XLF/XLE before
#: 2016 and scored them on QQQ/IWM/XLK after; these six were declared in that
#: prereg's Amendment 1 as securities in NEITHER slice, and they are where the
#: autopsies are drawn from here for the same reason: a precursor mined from a
#: security a later test will score it on is not a candidate, it is a memory.
HELD_SECURITIES: tuple[str, ...] = ("DIA", "XLV", "XLI", "XLP", "XLU", "XLB")

#: §51's own two horizons and its tail definition, unchanged so the coverage
#: number this job is trying to move is the number it is measured against.
HORIZONS: tuple[int, ...] = (20, 60)
TAIL_Q = 0.10

#: How many sessions BEFORE a move count as "the library had a chance". §51
#: evaluates a precursor on the state of the day the window opens; a warning
#: that can only fire on the day itself is not a warning, so the incumbent is
#: given a window and the window is declared here rather than chosen later.
WARNING_WINDOW_SESSIONS = 5

#: Rows per flush. A killed run keeps everything it has already paid for.
FLUSH_EVERY = 50

#: The reply's ceiling. Deliberately high: on a reasoning model the ceiling
#: bounds THINKING PLUS answer, so a structured object requested under a tight
#: ceiling comes back EMPTY and the cause is invisible (IIF-1 night 1).
MAX_TOKENS = 4_000

#: The refusal classes, so a run's yield has a denominator with named parts.
REFUSAL_CLASSES = ("REFUSED_UNPARSEABLE", "REFUSED_SCHEMA",
                   "REFUSED_VOCABULARY", "REFUSED_READER_ERROR",
                   "REFUSED_NOT_FALSIFIABLE")

#: THE TWO RUN-LEVEL REFUSALS. Neither is a property of a document: each says
#: the CAP cannot do its job, and a paid run under a cap that cannot bind is an
#: uncapped run wearing a cap's receipt. Both were written after the first
#: probe (2026-09-19 14:10 local) spent $0.21 against a $1.00 cap that read
#: $0.00 for fifteen minutes.
REFUSED_UNPRICED_CALL = "REFUSED_UNPRICED_CALL"
REFUSED_NO_LEDGER = "REFUSED_NO_LEDGER"

#: Every row this job writes carries it, and nothing downstream may read a row
#: without it. A candidate is a PROPOSAL; the library is earned elsewhere.
CANDIDATE_STATUS = "CANDIDATE"

ADMISSION_PATH = ("scripts/library_measure_2006_2019.py + "
                  "scripts/library_placebo_null.py")


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / f"night_factory_{RUN_DATE}"


def gym_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "research_gym"


def candidates_path() -> Path:
    return gym_dir() / "library_candidates.jsonl"


def cursor_path() -> Path:
    return gym_dir() / "library_candidates_cursor.json"


def max_usd_default() -> float:
    from backend import config as _config
    return float(_config.N9_LIBRARY_AUTOPSY_MAX_USD)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# the two guards the first probe paid for


def ledger_writable(path: Path | None = None) -> dict:
    """Can the CALL LEDGER the cap reads be read and appended to?

    MEASURED 2026-09-19: the first N9 probe ran for fifteen minutes under a
    $1.00 cap that read $0.00 the whole time. A cap that reads a ledger it
    cannot see is not a loose cap, it is NO cap -- its total is a lower bound
    of zero and it can never bind.

    NOT `LLM_CALLS.exists()`. The ledger rotated to one file a month on
    2026-09-12 and the monolith is legitimately gone, so that check would be a
    gate that can never go green -- the exact defect `monday_gate_check` printed
    for weeks. What is checked is the STREAM (`ledger_files`) and the DIRECTORY
    it appends into.
    """
    from backend.services import llm_telemetry as tel

    base = path if path is not None else tel._resolve_path(None)
    if base is None:
        return {"ok": False, "reason": REFUSED_NO_LEDGER,
                "base": None, "files": [],
                "detail": ("telemetry resolves NO write path here (the pytest "
                           "branch, or AEGIS_LLM_TELEMETRY_PATH unset in a "
                           "context that disables writing). A paid run whose "
                           "calls are never ledgered cannot be capped.")}
    base = Path(base)
    files = [str(q) for q in tel.ledger_files(base)]
    parent = base.parent
    if not parent.is_dir():
        return {"ok": False, "reason": REFUSED_NO_LEDGER, "base": str(base),
                "files": files,
                "detail": f"the ledger directory {parent} does not exist"}
    if not os.access(parent, os.W_OK):
        return {"ok": False, "reason": REFUSED_NO_LEDGER, "base": str(base),
                "files": files,
                "detail": f"the ledger directory {parent} is not writable"}
    if not files:
        return {"ok": False, "reason": REFUSED_NO_LEDGER, "base": str(base),
                "files": files,
                "detail": (f"no ledger file under {parent} matches {base.name} "
                           f"or its monthly rotation. The cap would read $0.00 "
                           f"for this whole run because there is nothing to "
                           f"read, which is a lower bound and not a total.")}
    return {"ok": True, "reason": None, "base": str(base), "files": files,
            "n_files": len(files),
            "checked": ("the ledger STREAM and the directory it appends into, "
                        "not the pre-rotation monolith -- that file is "
                        "legitimately gone since 2026-09-12")}


def unpriced_calls(since_utc: str, *, purpose: str = PURPOSE,
                   path: Path | None = None) -> dict:
    """Rows for THIS run whose `cost_usd` is None, and the models that wrote them.

    `cost_usd is None` means `llm_telemetry.price_call` did not recognise the
    model id the PROVIDER returned. Summing that as zero is the failure the
    first probe demonstrated end to end: DeepSeek renamed `deepseek-chat`'s
    served model to `deepseek-flash` on 2026-09-14, every one of 424 rows came
    back unpriced, `spend_from_ledger` added them as 0.0, and a $1.00 cap read
    $0.00 while the balance moved $0.21.

    An unpriced call is therefore a CAP BREACH by definition, not a rounding
    error: the run cannot know what it is spending, so it must stop and say
    which model id it could not price.
    """
    from backend.services import llm_telemetry as tel

    cut = str(since_utc or "")[:19]
    models: dict[str, int] = {}
    n = 0
    for row in tel.read_calls(path=path):
        if str(row.get("purpose") or "") != purpose:
            continue
        if str(row.get("ts") or "")[:19] < cut:
            continue
        if row.get("cost_usd") is None:
            n += 1
            m = str(row.get("model") or "<no model id>")
            models[m] = models.get(m, 0) + 1
    return {
        "n_unpriced": n,
        "models": models,
        "since_utc": since_utc,
        "purpose": purpose,
        "why_it_is_a_breach": (
            "an unpriced row is added as 0.0 by every total that sums it, so a "
            "cap over it is a lower bound of zero. The model id below is not in "
            "`config.LLM_PRICE_PER_MTOK`; price it from the provider's balance "
            "before running this job again."),
    }


def _r(x, n: int = 6):
    return None if x is None else round(float(x), n)


class ReaderUnavailable(RuntimeError):
    """The reader is not answering. A property of the RUN, not of a move."""


# --------------------------------------------------------------------------
# the incumbent library


def latest_autopsy_file(directory: Path | None = None) -> Path | None:
    """The newest autopsy JSONL, or `None`. Never a fabricated empty library.

    An EMPTY incumbent would make every move "unwarned" and the job would
    report 100% uncovered -- a number that says nothing about the library and
    everything about the file being missing.
    """
    d = directory or gym_dir()
    if not d.is_dir():
        return None
    cands = sorted(d.glob("autopsies_*.jsonl"),
                   key=lambda p: (p.stat().st_mtime, p.name))
    return cands[-1] if cands else None


def load_incumbent(path: Path | None = None) -> dict:
    """Compile every precursor in the incumbent library. Refusals are counted."""
    p = path or latest_autopsy_file()
    if p is None or not p.is_file():
        return {"path": (str(p) if p else None), "compiled": [],
                "n_rows": 0, "n_compiled": 0, "n_uncompilable": 0,
                "refused": ("REFUSED: no autopsies_*.jsonl under "
                            f"{gym_dir()} -- with no incumbent library every "
                            "move is 'unwarned' by default, which measures "
                            "the missing file and not the coverage")}
    compiled, rows, bad = [], 0, 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows += 1
        try:
            au = (json.loads(line).get("autopsy") or {})
        except json.JSONDecodeError:
            bad += 1
            continue
        spec = au.get("affected_precursor") or au.get("executable_precursor")
        if not spec:
            bad += 1
            continue
        try:
            compiled.append((spec, AU.compile_precursor(
                spec, vocabulary=AU.TRANSFERABLE_FEATURES)))
        except Exception:                                        # noqa: BLE001
            bad += 1
    return {"path": str(p), "compiled": compiled, "n_rows": rows,
            "n_compiled": len(compiled), "n_uncompilable": bad,
            "refused": None}


def fires(compiled, state: dict) -> bool:
    """Does ANY incumbent precursor fire on this state? A rule that raises on
    this state did not fire; it was unevaluable, and §51 counts those."""
    for _spec, fn in compiled:
        try:
            if fn(state):
                return True
        except Exception:                                        # noqa: BLE001
            continue
    return False


# --------------------------------------------------------------------------
# the held panel
#
# `load_bars` is the ONE network door and it is a module-level seam: the tests
# pass a frame and nothing leaves the machine.


def load_bars(ticker: str, start: str, end: str):
    """Daily closes for one security. The default path uses yfinance."""
    import pandas as pd
    import yfinance as yf

    bars = yf.download(ticker, start=start, end=end, progress=False)
    if bars is None or len(bars) == 0:
        raise ReaderUnavailable(
            f"REFUSED: no bars for {ticker} between {start} and {end}; a "
            f"panel built from an empty fetch would report zero exceptional "
            f"moves and read as full coverage")
    px = bars["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.squeeze()
    return px.dropna()


def load_vix(start: str, end: str):
    return load_bars("^VIX", start, end)


def build_states(px, vix, *, security: str):
    """The transferable state at every session, and the forward moves.

    Every state term is SHIFTED: read at the close BEFORE the window it labels,
    so a rule can never see the move it is marking. This is `n9_mine_the_85`'s
    own construction, reproduced rather than reinvented so the coverage number
    means the same thing.
    """
    import numpy as np
    import pandas as pd

    from backend.services.research_gym import market_stress as MS

    r = px.pct_change().dropna()
    rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
    rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
    roll_max = px.rolling(252, min_periods=20).max()
    df = pd.DataFrame({
        "vix": vix.reindex(r.index).ffill().shift(1),
        "drawdown_pct": ((px / roll_max - 1.0) * 100.0).shift(1),
        "ret_1m_pct": (px.pct_change(21) * 100.0).shift(1),
        "ret_3m_pct": (px.pct_change(63) * 100.0).shift(1),
        "ret_6m_pct": (px.pct_change(126) * 100.0).shift(1),
        "realised_vol_20d": rv20.shift(1),
        "vol_ratio_20_60": (rv20 / rv60).shift(1),
    }, index=r.index)
    df["stress_pctile"] = MS.stress_pctile(rv20.shift(1).tolist())
    df["security"] = security
    for h in HORIZONS:
        df[f"fwd_{h}"] = ((px.shift(-h) / px - 1.0) * 100.0).reindex(r.index)
    return df


def _state_of(row) -> dict:
    out = {}
    for k in AU.TRANSFERABLE_FEATURES:
        if k not in row:
            continue
        v = row[k]
        if k == "security":
            out[k] = str(v)
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            fv = None
        out[k] = None if fv is None or fv != fv else round(fv, 4)
    return out


def unwarned_moves(frames: dict, incumbent, *, tail_q: float = TAIL_Q,
                   window: int = WARNING_WINDOW_SESSIONS) -> dict:
    """Exceptional moves in the held panel, split by whether anything warned.

    "Exceptional" is the tail decile of the forward move, per security and per
    horizon -- §51's own definition. "Warned" means an incumbent precursor
    fired on ANY of the `window` sessions up to and including the one the
    window opens on.
    """
    import numpy as np

    moves, covered, total = [], 0, 0
    for tkr, df in frames.items():
        idx = list(df.index)
        state_rows = [_state_of(df.iloc[i]) for i in range(len(df))]
        fired = []
        for st in state_rows:
            fired.append(fires(incumbent, st))
        for h in HORIZONS:
            col = df[f"fwd_{h}"].to_numpy(dtype="float64")
            ok = np.isfinite(col)
            if ok.sum() < 50:
                continue
            lo = float(np.quantile(col[ok], tail_q))
            hi = float(np.quantile(col[ok], 1.0 - tail_q))
            for i in range(len(df)):
                if not ok[i]:
                    continue
                tail = ("bottom" if col[i] <= lo else
                        "top" if col[i] >= hi else None)
                if tail is None:
                    continue
                total += 1
                warned = any(fired[max(0, i - window + 1): i + 1])
                if warned:
                    covered += 1
                    continue
                st = state_rows[i]
                if any(v is None for k, v in st.items() if k != "security"):
                    continue          # unevaluable state: not a candidate move
                moves.append({
                    "security": tkr,
                    "date": str(idx[i])[:10],
                    "horizon_sessions": int(h),
                    "tail": tail,
                    "forward_return_pct": round(float(col[i]), 3),
                    "state": st,
                })
    base_rate = (float(np.mean([f for tkr in frames
                                for f in [fires(incumbent, _state_of(
                                    frames[tkr].iloc[i]))
                                    for i in range(len(frames[tkr]))]]))
                 if frames else 0.0)
    return {
        "moves": moves,
        "n_exceptional": total,
        "n_covered": covered,
        "n_unwarned": len(moves),
        "covered_share": _r(covered / total, 4) if total else None,
        "library_fires_on_share_of_all_days": _r(base_rate, 4),
        "lift_vs_base_rate": (_r((covered / total) / base_rate, 4)
                              if total and base_rate else None),
        "tail_q": tail_q, "warning_window_sessions": window,
        "note": ("§51's own metric: coverage is only coverage if it exceeds "
                 "the share of ALL days the library fires on. Lift 1.0 is "
                 "where the library sat on 2026-08-17."),
    }


# --------------------------------------------------------------------------
# the prompt and the reply


SCHEMA_HINT = """Reply with ONE json object and nothing else. Every field is required.

{
  "contemporaneous_evidence": ["facts knowable AT the observation date"],
  "post_outcome_evidence":    ["facts knowable ONLY after the move"],
  "proposed_mechanism":       "why this is repeatable, not one bad month",
  "precursor_definition":     "the rule in one plain sentence a human can check",
  "affected_precursor":       {"all": [{"feature": "vix", "op": ">=", "value": 28}]},
  "unaffected_precursor":     {"all": [{"feature": "vix", "op": "<", "value": 15}]},
  "falsifier":                "the observation that would kill this",
  "alternative_explanation":  "the most credible rival account"
}

RULES THE REPLY MUST OBEY OR IT IS DISCARDED
- Both precursors may ONLY read features from the TRANSFERABLE VOCABULARY
  listed above. A rule written over anything else is untestable by
  construction, because the out-of-sample corpus does not carry it.
  Operators: > >= < <= == != in not_in, combined with all / any / not.
- Neither precursor may read the forward return, the tail, or anything dated
  after the observation date.
- `unaffected_precursor` is your hypothesis' PLACEBO ARM, not a formality: a
  region where you expect NO excess of these moves from the same reading. The
  two must be disjoint -- no state may satisfy both.
- Anything you know only because you were shown the move belongs in
  `post_outcome_evidence`, never in `contemporaneous_evidence`.
- Numbers in a clause are the units shown in the STATE block: vix in points,
  every *_pct in percent, stress_pctile in [0, 1], vol_ratio_20_60 a ratio."""


def build_prompt(move: dict) -> str:
    """Everything the reader needs, and the outcome it is allowed to see."""
    lines = [
        "You are performing an AUTOPSY on one EXCEPTIONAL MARKET MOVE that no "
        "rule in our precursor library warned about.",
        "You may see the move. That is the point. Your job is to propose what "
        "would have had to be OBSERVABLE BEFOREHAND for this to be a "
        "repeatable, markable regularity rather than one unusual month, and "
        "to state it so it can be tested on moves you have not seen.",
        "",
        f"SECURITY      {move['security']}",
        f"OBSERVED AT   {move['date']}  (the close; every state term below was "
        f"read at the PREVIOUS close)",
        f"THE MOVE      {move['forward_return_pct']:+.2f}% over the next "
        f"{move['horizon_sessions']} sessions -- the {move['tail']} decile of "
        f"this security's own forward-return distribution at that horizon",
        "",
        "STATE at the observation date:",
    ]
    for k in sorted(move["state"]):
        lines.append(f"  {k} = {move['state'][k]!r}")
    lines += [
        "",
        "TRANSFERABLE VOCABULARY -- both precursors may read ONLY these:",
        "  " + ", ".join(sorted(AU.TRANSFERABLE_FEATURES)),
        "",
        "WHAT WE ALREADY KNOW, so you do not propose it again:",
        "  * The existing library is six rules, all written over `vix`, all "
        "derived from SELL autopsies about de-risking after volatility "
        "spikes. It fires on ~15% of all days and covers ~15% of exceptional "
        "moves -- exactly the base rate. A rule that is `vix >= 35` in "
        "different words adds nothing.",
        "  * A rule that fires almost always is not a warning. Aim for "
        "something that would fire on a small, nameable minority of days.",
        "",
        "Propose ONE precursor for this move.",
    ]
    return "\n".join(lines)


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

_REQUIRED = ("contemporaneous_evidence", "post_outcome_evidence",
             "proposed_mechanism", "precursor_definition",
             "affected_precursor", "unaffected_precursor",
             "falsifier", "alternative_explanation")


def parse_reply(raw: str) -> tuple[dict | None, dict | None]:
    """`(candidate_fields, refusal)`. Exactly one is `None`.

    No repair and no retry at any step: a reply that has to be fixed to be
    usable is a reply whose usable rate we would then be over-stating.
    """
    text = _FENCE.sub("", (raw or "").strip()).strip()
    if not text:
        return None, {"reason": "REFUSED_UNPARSEABLE",
                      "detail": "the reply was empty after fences were stripped"}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, {"reason": "REFUSED_UNPARSEABLE",
                      "detail": f"json.loads: {exc}", "raw": text[:1000]}
    if not isinstance(obj, dict):
        return None, {"reason": "REFUSED_SCHEMA",
                      "detail": f"root: expected an object, got "
                                f"{type(obj).__name__}"}
    missing = [k for k in _REQUIRED if k not in obj]
    if missing:
        return None, {"reason": "REFUSED_SCHEMA",
                      "detail": f"missing required field(s): {missing}"}
    for k in ("proposed_mechanism", "precursor_definition", "falsifier",
              "alternative_explanation"):
        if not str(obj.get(k) or "").strip():
            return None, {"reason": "REFUSED_NOT_FALSIFIABLE",
                          "detail": (f"{k} is empty; an autopsy with no {k} is "
                                     f"not a cheap autopsy, it is a "
                                     f"non-autopsy")}
    for key in ("affected_precursor", "unaffected_precursor"):
        try:
            AU.compile_precursor(obj[key],
                                 vocabulary=AU.TRANSFERABLE_FEATURES)
        except AU.VocabularyRefused as exc:
            return None, {"reason": "REFUSED_VOCABULARY",
                          "detail": f"{key}: {exc}"}
        except AU.PrecursorRefused as exc:
            return None, {"reason": "REFUSED_SCHEMA",
                          "detail": f"{key}: {exc}"}
    return {k: obj[k] for k in _REQUIRED}, None


# --------------------------------------------------------------------------
# the readers


def deepseek_reader(prompt: str, *, max_tokens: int = MAX_TOKENS) -> str:
    """The cloud reader. DeepSeek is the only provider; the ledger prices it."""
    from backend.services.llm_research import ask
    res = ask(prompt, purpose=PURPOSE, temperature=0.0,
              max_tokens=max_tokens, schema_hint=SCHEMA_HINT)
    if res.get("truncated"):
        raise ReaderUnavailable(
            f"reply_truncated_at_token_ceiling (max_tokens={max_tokens}); on a "
            f"reasoning model the ceiling bounds thinking plus answer")
    return res.get("text") or ""


def local_reader(prompt: str, *, max_tokens: int = MAX_TOKENS) -> str:
    """The local reader. It NEVER starts or stops a server."""
    from backend.services.free_inference import complete
    reply = complete("local_gguf", prompt, system=SCHEMA_HINT,
                     max_tokens=max_tokens, temperature=0.0, purpose=PURPOSE)
    return getattr(reply, "text", "") or ""


def probe_local() -> str | None:
    """Is the local reader answering? Never starts it, never stops it."""
    from backend.services.free_inference import complete
    from backend.services.model_provider import LanguageRefused, ProviderRefusal
    try:
        complete("local_gguf", "Answer with the single word OK.",
                 system="Answer in English.", max_tokens=4, temperature=0.0,
                 purpose=f"{PURPOSE}_probe")
        return None
    except (ProviderRefusal, LanguageRefused) as exc:
        return f"{type(exc).__name__}: {exc}"


def resolve_reader(name: str | None):
    """`(reader, backend, refusal)`. The refusal is by NAME, never a silent
    fallback: a run that quietly used a different model than the one on the
    receipt is a run whose receipt is wrong."""
    choice = (name or "deepseek").lower()
    if choice == "local":
        why = probe_local()
        if why:
            return None, "local_gguf", (
                "REFUSED_NO_LOCAL_SERVER: --reader local was asked for and no "
                f"llama-server is answering ({why}). This job never starts or "
                "stops a server; bring one up and run it again.")
        return local_reader, "local_gguf", None
    if choice != "deepseek":
        return None, choice, f"REFUSED_UNKNOWN_READER: {choice!r}"
    from backend.services.llm_research import available
    ok, why = available()
    if not ok:
        return None, "deepseek", f"REFUSED_NO_PROVIDER: {why}"
    return deepseek_reader, "deepseek", None


# --------------------------------------------------------------------------
# the cursor


def move_key(move: dict) -> str:
    """Stable id of one move, so a resumed run never re-bills a proposal."""
    raw = f"{move['security']}|{move['date']}|{move['horizon_sessions']}|{move['tail']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_cursor(path: Path | None = None) -> dict:
    p = path or cursor_path()
    if not p.is_file():
        return {"done": [], "rows_written": 0, "updated_utc": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("unreadable cursor at %s; starting from zero", p)
        return {"done": [], "rows_written": 0, "updated_utc": None}
    d.setdefault("done", [])
    d.setdefault("rows_written", 0)
    return d


def save_cursor(done, *, rows_written: int, path: Path | None = None) -> None:
    p = path or cursor_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"done": sorted(set(done)),
                             "rows_written": int(rows_written),
                             "updated_utc": _now()}, indent=1),
                 encoding="utf-8")


def append_rows(rows: list, path: Path | None = None) -> None:
    if not rows:
        return
    p = path or candidates_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def candidate_row(move: dict, fields: dict, *, backend: str,
                  incumbent_path: str | None) -> dict:
    """One CANDIDATE. Never a library member -- the status says so on the row."""
    return {
        "status": CANDIDATE_STATUS,
        "admission_path": ADMISSION_PATH,
        "may_not_enter_the_library_from_here": (
            "§37/§41: a verdict that KILLS or ADMITS is the hardest kind to "
            "notice being wrong, and §41 found every refutation one standard "
            "produced had been manufactured by its own denominator. The "
            "generator does not get to admit its own output."),
        "candidate_id": move_key(move),
        "job": JOB, "licence": LICENCE, "run_date": RUN_DATE,
        "written_utc": _now(),
        "reader_backend": backend,
        "incumbent_library": incumbent_path,
        "move": move,
        **fields,
    }


def refusal_row(move: dict, refusal: dict, *, backend: str) -> dict:
    """A refusal is a FINDING and belongs in the denominator."""
    return {"status": "REFUSED", "candidate_id": move_key(move),
            "job": JOB, "run_date": RUN_DATE, "written_utc": _now(),
            "reader_backend": backend, "move": move, **refusal}


# --------------------------------------------------------------------------
# the run


def autopsy_moves(moves: list, *, reader, backend: str, cap, workers: int,
                  incumbent_path: str | None, flush_every: int = FLUSH_EVERY,
                  cursor: dict | None = None,
                  candidates_file: Path | None = None,
                  cursor_file: Path | None = None,
                  unpriced_check=None) -> dict:
    """Propose one precursor per move, under the cap, resumable, flushed.

    `unpriced_check() -> dict | None` runs AT EVERY FLUSH, which is the same
    cadence the cap re-reads the ledger at. It returns a block when the run has
    produced a call the ledger could not price, and the run stops there by name:
    everything collected is written first, so the stop costs no row.
    """
    cur = cursor if cursor is not None else load_cursor(cursor_file)
    done = set(cur.get("done") or [])
    todo = [m for m in moves if move_key(m) not in done]
    counts = {c: 0 for c in REFUSAL_CLASSES}
    written = 0
    pending: list = []

    def _one(move):
        try:
            text = reader(build_prompt(move))
        except Exception as exc:                                 # noqa: BLE001
            return move, None, {"reason": "REFUSED_READER_ERROR",
                                "detail": f"{type(exc).__name__}: {exc}"}
        fields, refusal = parse_reply(text)
        return move, fields, refusal

    def _flush():
        nonlocal pending
        append_rows(pending, candidates_file)
        pending = []
        save_cursor(done, rows_written=cur.get("rows_written", 0) + written,
                    path=cursor_file)

    def _result(stopped: str, detail=None, unpriced=None) -> dict:
        return {
            "moves_offered": len(moves),
            "moves_already_done": len(moves) - len(todo),
            "moves_attempted": len(done) - len(cur.get("done") or []),
            "candidates_filed": written,
            "refusals": {k: v for k, v in counts.items() if v},
            "n_refused": sum(counts.values()),
            "stopped": stopped,
            "stop_detail": detail,
            "unpriced": unpriced,
            "stopped_on_cap": stopped == "MAX_USD_CAP",
            "flush_every": flush_every,
            "cursor_file": str(cursor_file or cursor_path()),
            "candidates_file": str(candidates_file or candidates_path()),
        }

    batch: list = []
    stopped = "complete"
    detail = None
    unpriced = None
    try:
        for move in todo:
            if not cap.may_submit():
                stopped = "MAX_USD_CAP"
                detail = (f"the cap refused the next submission after "
                          f"{written} filed row(s)")
                break
            cap.charge()
            batch.append(move)
            if len(batch) < max(1, int(workers)):
                continue
            for m, fields, refusal in _run_batch(batch, _one, workers):
                written += _record(m, fields, refusal, pending, done, counts,
                                   backend=backend,
                                   incumbent_path=incumbent_path)
            batch = []
            if len(pending) >= flush_every:
                _flush()
                # AT THE FLUSH, not per row: `read_calls` is 1.4 s cold and the
                # check is worth less than the row it would cost per call.
                if unpriced_check is not None:
                    unpriced = unpriced_check()
                    if unpriced:
                        stopped = REFUSED_UNPRICED_CALL
                        detail = (
                            f"{unpriced['n_unpriced']} call(s) this run came "
                            f"back with a model id the price table does not "
                            f"carry: {unpriced['models']}. The cap over them "
                            f"is a lower bound of ZERO, so the run stops here "
                            f"rather than spending under a cap that cannot "
                            f"bind.")
                        break
        if stopped == "complete" and batch:
            for m, fields, refusal in _run_batch(batch, _one, workers):
                written += _record(m, fields, refusal, pending, done, counts,
                                   backend=backend,
                                   incumbent_path=incumbent_path)
            batch = []
    except BaseException as exc:                                 # noqa: BLE001
        # EVERY EXIT FLUSHES. The first probe was interrupted after 424 billed
        # calls and 400 filed rows and left NO receipt, because the receipt is
        # written by `night_factory_jobs.main()` only after this function
        # returns. Fifteen minutes of spend with nothing naming what it bought
        # is the defect; re-raising here would reproduce it.
        _flush()
        return _result("INTERRUPTED",
                       f"{type(exc).__name__}: {exc}", unpriced)
    _flush()
    if stopped == "complete" and unpriced_check is not None:
        # One last read, so a run that finished inside a single flush window
        # still learns its calls were unpriced.
        last = unpriced_check()
        if last:
            unpriced = last
            stopped = REFUSED_UNPRICED_CALL
            detail = (f"{last['n_unpriced']} call(s) this run were unpriced "
                      f"({last['models']}); the cap over them was a lower "
                      f"bound of zero for the whole run.")
    return _result(stopped, detail, unpriced)


def _run_batch(batch, fn, workers: int):
    if int(workers) <= 1 or len(batch) == 1:
        return [fn(m) for m in batch]
    with ThreadPoolExecutor(max_workers=int(workers)) as pool:
        return list(pool.map(fn, batch))


def _record(move, fields, refusal, pending, done, counts, *, backend,
            incumbent_path) -> int:
    """Returns 1 when a CANDIDATE was filed, 0 when a refusal was."""
    key = move_key(move)
    if refusal is not None:
        counts[refusal["reason"]] = counts.get(refusal["reason"], 0) + 1
        pending.append(refusal_row(move, refusal, backend=backend))
        # A READER error is a property of the RUN, not of the move, so the
        # cursor does NOT pass it: the next run retries exactly that move.
        # Every other class is a property of the reply to THIS move and is
        # never re-billed. (L2's rule, same reason.)
        if refusal["reason"] != "REFUSED_READER_ERROR":
            done.add(key)
        return 0
    pending.append(candidate_row(move, fields, backend=backend,
                                 incumbent_path=incumbent_path))
    done.add(key)
    return 1


def N9_library_autopsy(*, smoke: bool = False, run: int = 1,   # noqa: N802
                       max_usd: float | None = None, workers: int = 1,
                       reader: str | None = None,
                       frames: dict | None = None,
                       start: str = "1999-01-01",
                       end: str | None = None) -> dict:
    """One receipt: the coverage read, the autopsies, the candidates, the cost."""
    from scripts.night_l2_typed_events import _RunCap, spend_from_ledger

    t0 = datetime.now(timezone.utc)
    since = _now()
    cap_usd = float(max_usd_default() if max_usd is None else max_usd)
    end = end or datetime.now().strftime("%Y-%m-%d")

    base = {
        "job": JOB, "licence": LICENCE, "run": int(run), "run_date": RUN_DATE,
        "smoke": bool(smoke),
        "question": (
            "NEGATIVE_RESULTS §51: the precursor library warns on 12-17% of "
            "exceptional moves and fires on 15.3% of ALL days -- coverage IS "
            "the base rate, lift 0.82-1.15 against an MDE of 0.25-0.62. §51's "
            "own fix is more autopsy-generated precursors. What does the "
            "reader propose for the moves nothing warned about?"),
        "held_panel": list(HELD_SECURITIES),
        "held_panel_why": (
            "PREREG_N9_MINE_THE_85 Amendment 1's six securities -- in neither "
            "the selection slice (SPY/XLF/XLE, pre-2016) nor the foreign one "
            "(QQQ/IWM/XLK, post-2016). A precursor mined from a security a "
            "later test will score it on is not a candidate, it is a memory."),
        "horizons": list(HORIZONS), "tail_q": TAIL_Q,
        "warning_window_sessions": WARNING_WINDOW_SESSIONS,
        "output_is_candidates_only": {
            "status_on_every_row": CANDIDATE_STATUS,
            "admission_path": ADMISSION_PATH,
            "why": ("§37/§41. This job generates; it may not admit. A "
                    "generator that could also admit its own output is the "
                    "same defect with the sign flipped."),
        },
        "cost_cap": {"max_usd": cap_usd,
                     "config_key": "N9_LIBRARY_AUTOPSY_MAX_USD",
                     "checked": "BEFORE every submission, never refunded after",
                     "also_breached_by": (
                         "an UNPRICED call. A row whose `cost_usd` is None is "
                         "summed as 0.0 by every total that reads it, so the "
                         "cap over it is a lower bound of zero. The run stops "
                         f"by name ({REFUSED_UNPRICED_CALL}) and prints the "
                         "model id it could not price."),
                     "requires": (
                         f"a readable, appendable call ledger, else "
                         f"{REFUSED_NO_LEDGER} before the first submission")},
    }

    incumbent = load_incumbent()
    base["incumbent_library"] = {k: v for k, v in incumbent.items()
                                 if k != "compiled"}
    if incumbent["refused"]:
        return {**base, "coverage": None, "autopsies": None,
                "spend": spend_from_ledger(since, purpose=PURPOSE),
                "headline": incumbent["refused"],
                "verdict": incumbent["refused"],
                "elapsed_s": round((datetime.now(timezone.utc)
                                    - t0).total_seconds(), 1),
                "written_utc": _now()}

    if frames is None:
        try:
            vix = load_vix(start, end)
            universe = (HELD_SECURITIES[:2] if smoke else HELD_SECURITIES)
            frames = {t: build_states(load_bars(t, start, end), vix,
                                      security=t) for t in universe}
        except Exception as exc:                                 # noqa: BLE001
            why = (f"REFUSED_NO_BARS: the held panel could not be built "
                   f"({type(exc).__name__}: {exc}). A panel from an empty "
                   f"fetch reports zero exceptional moves and reads as full "
                   f"coverage.")
            return {**base, "coverage": None, "autopsies": None,
                    "spend": spend_from_ledger(since, purpose=PURPOSE),
                    "headline": why, "verdict": why,
                    "elapsed_s": round((datetime.now(timezone.utc)
                                        - t0).total_seconds(), 1),
                    "written_utc": _now()}

    coverage = unwarned_moves(frames, incumbent["compiled"])
    moves = coverage.pop("moves")
    if smoke:
        moves = moves[:3]
    base["coverage"] = coverage
    base["n_moves_this_run"] = len(moves)

    fn, backend, refusal = resolve_reader(reader)
    base["reader"] = {"asked_for": reader or "deepseek", "backend": backend,
                      "refused": refusal}

    # THE LEDGER COMES BEFORE THE FIRST SUBMISSION, and only for a run that can
    # spend: a local reader costs compute, so no dollar cap can bind and none
    # is needed. `lab_budget.UNMETERED_BACKENDS` is the same list `_RunCap`
    # reads, imported rather than retyped so the two cannot disagree about
    # which backends cost money.
    from backend.services import lab_budget
    metered = backend not in lab_budget.UNMETERED_BACKENDS
    ledger = ledger_writable() if metered else {
        "ok": True, "reason": None,
        "checked": f"skipped: {backend} is unmetered, so no cap can bind"}
    base["ledger"] = ledger
    base["metered"] = metered
    if fn is not None and metered and not ledger["ok"]:
        why = (f"{REFUSED_NO_LEDGER}: {ledger['detail']} A cap that reads a "
               f"ledger it cannot see is not a loose cap, it is no cap -- and "
               f"this job will not spend under one.")
        return {**base, "autopsies": None,
                "spend": spend_from_ledger(since, purpose=PURPOSE),
                "headline": (f"{coverage['n_unwarned']} unwarned exceptional "
                             f"moves found; {why}"),
                "verdict": why,
                "elapsed_s": round((datetime.now(timezone.utc)
                                    - t0).total_seconds(), 1),
                "written_utc": _now()}

    if fn is None:
        return {**base, "autopsies": None,
                "spend": spend_from_ledger(since, purpose=PURPOSE),
                "headline": (f"{coverage['n_unwarned']} unwarned exceptional "
                             f"moves found; {refusal}"),
                "verdict": refusal,
                "elapsed_s": round((datetime.now(timezone.utc)
                                    - t0).total_seconds(), 1),
                "written_utc": _now()}

    cap = _RunCap(cap_usd, backend=backend, since_utc=since,
                  refresh_every=FLUSH_EVERY)

    def _unpriced():
        """A block when this run has produced an unpriced call, else None.

        Only a METERED run can breach this way: a local reader writes
        `cost_usd = 0.0`, not `None`, because its price is known to be zero.
        """
        if not metered:
            return None
        u = unpriced_calls(since, purpose=PURPOSE)
        return u if u["n_unpriced"] else None

    res = autopsy_moves(moves, reader=fn, backend=backend, cap=cap,
                        workers=workers,
                        incumbent_path=incumbent["path"],
                        unpriced_check=_unpriced)
    spend = spend_from_ledger(since, purpose=PURPOSE)

    filed = res["candidates_filed"]
    stopped = res.get("stopped") or "complete"
    spend_is_a_lower_bound = bool((res.get("unpriced") or {}).get("n_unpriced"))
    return {
        **base,
        "autopsies": res,
        "cap_block": cap.block(),
        "spend": spend,
        "llm_spend_usd": spend["usd"],
        "spend_is_a_lower_bound": spend_is_a_lower_bound,
        "spend_caveat": (
            (f"UNPRICED CALLS: {res['unpriced']['models']}. Every total above "
             f"that sums them treats them as 0.0, so `llm_spend_usd` is a "
             f"LOWER BOUND and the real figure is the provider's balance. "
             f"`scripts/llm_cost_audit.py --snapshot` is the ground truth.")
            if spend_is_a_lower_bound else None),
        "headline": (
            f"{coverage['n_unwarned']} of {coverage['n_exceptional']} "
            f"exceptional moves unwarned (library covers "
            f"{coverage['covered_share']}, fires on "
            f"{coverage['library_fires_on_share_of_all_days']} of all days, "
            f"lift {coverage['lift_vs_base_rate']}); {filed} CANDIDATE "
            f"precursor(s) filed, {res['n_refused']} refused "
            f"{res['refusals']}, ${spend['usd']:.4f}"
            f"{'+ (LOWER BOUND, unpriced calls)' if spend_is_a_lower_bound else ''}"
            f" of ${cap_usd:.2f} spent; stopped={stopped}"),
        "next_test": (
            f"none of these is a library member. Each has to clear "
            f"{ADMISSION_PATH} on foreign slices with its parent move barred, "
            f"and the metric that decides is §51's LIFT over the library's own "
            f"firing rate -- not whether the rule fires."),
        "verdict": (
            (f"{REFUSED_UNPRICED_CALL} — {res['stop_detail']} {filed} row(s) "
             f"were filed before the stop and are kept; nothing is re-billed.")
            if stopped == REFUSED_UNPRICED_CALL else
            (f"INTERRUPTED — {res['stop_detail']}. {filed} row(s) were flushed "
             f"before the exit and the cursor is at them, so a resumed run "
             f"re-bills none of them. This receipt exists BECAUSE the run did "
             f"not finish: the first probe was interrupted after 424 billed "
             f"calls and left nothing naming what they bought.")
            if stopped == "INTERRUPTED" else
            "SMOKE — proves the job runs end to end on three moves; no "
            "coverage number may be read from it"
            if smoke else
            f"{filed} candidates for {ADMISSION_PATH}. A candidate is "
            f"a proposal, not a precursor: nothing here changes the "
            f"library's measured coverage until the measurement job "
            f"runs."),
        "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "written_utc": _now(),
    }
