"""THE ONE SURVIVING G3 LINEAGE, frozen as a static rule -- and the probe that
says whether the execution repo can actually run it.

WHAT THIS IS
============
`E5_stopping_rules` deflated every G3 lineage's Sharpe for how many genomes the
search tried and wrote its verdict to `G3_lineage_verdicts.jsonl`. Exactly one
lineage came back `ACTIVE`: **32f752af234f0d3d**, observed Sharpe 6.2735 against
an expected-maximum bar of 3.1528 at 595 raw trials (251 lineages), DSR 1.000
against a 0.95 bar, 342 banks met, 8,208 windows measured. That is the only
mechanism in this repository that has cleared a MULTIPLICITY-CORRECTED bar
rather than a raw t-stat, which is why chunk 13b was asked to put it in an
account.

A genome is not a rule until somebody writes it down. This job reads the
evaluation log, pulls the lineage's representative genome out of it, and writes
it as a FROZEN decision rule under `backend/data/optimus/engines/` -- weights,
k, weighting scheme, holding multiple, floor -- beside the receipt that
deflated it and the trial count the deflation used.

**The evolutionary search never runs again for this.** The rule is a fixed
vector; running the search to "re-derive" it would be a new search with a new
multiplicity budget, and the DSR that licensed this row would no longer apply.

WHAT THIS IS ALSO, AND IT IS THE PART THAT DECIDED CHUNK 13B
============================================================
The rule is a linear composite of FOURTEEN cross-sectionally z-scored features
from `backend/data/optimus/learner/train_table_long.parquet`. Whether it can be
executed live is not a question about the weights -- it is a question about
whether the execution repo can compute those fourteen columns, for its own
universe, on the morning of a trade. `FEATURE_SOURCES` below answers that
feature by feature, from the code that BUILDS each one (`learner/dataset.py`),
and `probe()` turns it into a verdict.

It comes back NO, and it names which inputs. The honest consequence is written
into the receipt rather than worked around: hack4 keeps its current mandate and
is governed by the allocator's drawdown cut, and this rule waits for the panel
it needs to exist on the execution side.

    python -m scripts.night_factory_jobs G3_lineage_export
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("g3_lineage_export")

JOB = "G3_lineage_export"
ENGINE = "g3_lineage_v1"
LICENCE = "PRODUCT_EXPERIMENT"

#: The one ACTIVE lineage and the genome `E5_stopping_rules` chose to represent
#: it. Both are read back out of the receipts rather than trusted from here --
#: these constants exist so a reader knows which row is meant, and `export()`
#: refuses if the receipts no longer agree with them.
LINEAGE = "32f752af234f0d3d"
REPRESENTATIVE = "a85d7eb6323ab821"

RUN_DIR = "night_factory_2026-09-08"
VERDICTS = "G3_lineage_verdicts.jsonl"
EVALUATIONS = "G3_evaluations.jsonl"
SEARCH_RECEIPT = "G3_evolve_run01.json"
SEARCH_AMENDMENT = "G3_verdict_amendment.json"

#: Every feature the genome weights, WHERE IT COMES FROM, and whether the
#: execution repo can compute it. `builder` is the line in `learner/dataset.py`
#: that defines it; `terminal` is `yes` / `partial` / `no` with the reason.
#:
#: `partial` is not `yes`. A Finnhub 1-5 recommendation mean is not IBES's
#: recommendation mean, and `alpha/tracker.py` already refuses a coverage count
#: whose scale is uncalibrated -- so a `partial` column would put a DIFFERENT
#: number under a weight that was fitted on the panel's number.
FEATURE_SOURCES = {
    "mom_12_1__xs": {
        "builder": "CRSP monthly returns, 12-1", "family": "price",
        "terminal": "yes",
        "why": "derivable from Alpaca daily bars given ~13 months of history"},
    "ret_1m__xs": {"builder": "CRSP monthly return", "family": "price",
                   "terminal": "yes", "why": "daily bars"},
    "ret_6m__xs": {"builder": "CRSP monthly returns, 6m", "family": "price",
                   "terminal": "yes", "why": "daily bars"},
    "drawdown_60d__xs": {"builder": "close / rolling max, 60 sessions",
                         "family": "price", "terminal": "yes", "why": "daily bars"},
    "vol_60d__xs": {"builder": "realised vol, 60 sessions", "family": "price",
                    "terminal": "yes", "why": "daily bars"},
    "log_close__xs": {"builder": "log(close)", "family": "price",
                      "terminal": "yes", "why": "daily bars"},
    "log_market_cap__xs": {
        "builder": "log(market_cap) = log(|prc| x shrout), CRSP",
        "family": "size", "terminal": "no",
        "why": ("the venue's asset record carries NO shares outstanding and no "
                "market cap -- `alpha/universe.py` states it in the stored "
                "screen: 'market_cap_screen: NOT APPLIED (no cap in the "
                "venue's asset record)', and every stored member's "
                "`market_cap_usd` is null")},
    "ratio__xs": {
        "builder": "mean_target / close, IBES ptgsumu (UNADJUSTED) over CRSP prc",
        "family": "analyst", "terminal": "partial",
        "why": ("the execution repo has a consensus target for its ~150-name "
                "window universe from a different vendor and from the news "
                "corpus, on a different basis; it has none for the thousands of "
                "names the cross-section is computed over")},
    "coverage__xs": {
        "builder": "IBES numest", "family": "analyst", "terminal": "partial",
        "why": ("yfinance `numberOfAnalystOpinions` where readable -- and "
                "`alpha/tracker.py` already refuses a row whose "
                "`coverage_source` is an uncalibrated scale, which is the same "
                "objection one level down")},
    "disagreement__xs": {
        "builder": "(ptghigh - ptglow) / meanptg, IBES", "family": "analyst",
        "terminal": "no",
        "why": "IBES price-target HIGH and LOW are not available on this side at all"},
    "dispersion__xs": {
        "builder": "stdev / meanptg, IBES", "family": "analyst", "terminal": "no",
        "why": ("the standard deviation of analyst price targets. Finnhub's free "
                "tier 403s on `stock/price-target` -- `scripts/analyst_panel.py` "
                "in the execution repo says so in its own first paragraph")},
    "net_rev_4w__xs": {
        "builder": "(numup4w - numdown4w) / numest, IBES", "family": "revision",
        "terminal": "no",
        "why": ("four-week counts of UP and DOWN estimate revisions. Nothing on "
                "the execution side counts revisions, and a count cannot be "
                "reconstructed from a level")},
    "target_rev_1m__xs": {
        "builder": ("meanptg / (prior meanptg x cfacpr(t)/cfacpr(t-1)) - 1, "
                    "own monthly history with a CRSP split rebase"),
        "family": "revision", "terminal": "no",
        "why": ("needs a monthly IBES consensus history per name AND CRSP's "
                "cumulative price factor to rebase across splits -- the panel "
                "holds 1999-2024; the execution repo's own target snapshots "
                "begin in August 2026 and carry no split factor")},
    "consensus_rev_1m__xs": {
        "builder": "consensus - prior month's consensus, own monthly history",
        "family": "revision", "terminal": "no",
        "why": "same monthly IBES history as above"},
}

#: The objection that survives even the `yes` rows, and it is the decisive one.
CROSS_SECTION_NOTE = (
    "EVERY feature is `__xs` -- a WITHIN-MONTH CROSS-SECTIONAL z-score over the "
    "panel's own cross-section (925,757 rows; roughly two thousand names a "
    "month). The execution repo's universe at decision time is the window "
    "universe (98 names on the stored 2026-08-28 build) or a theme list of 40. "
    "A z-score over 98 names is not the z-score the weights were fitted on, so "
    "even the six price features would feed DIFFERENT numbers into the same "
    "coefficients. This objection does not depend on any vendor and cannot be "
    "bought: it is fixed only by giving the execution side the same monthly "
    "cross-section, which is what the engine-file pattern (`F_seasonality_*`) "
    "does for Book F.")


class LineageUnavailable(RuntimeError):
    """A receipt this job reads is absent or no longer says what it said."""


def run_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / RUN_DIR


def engines_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "engines"


def _jsonl(path: Path):
    if not path.is_file():
        raise LineageUnavailable(
            f"{path} is absent. This job reads receipts the night search already "
            f"wrote; it does not re-run the search, because a re-run is a NEW "
            f"search with a new multiplicity budget and the DSR that licensed "
            f"this lineage would no longer apply to it.")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def active_lineage(*, path: Path | None = None) -> dict:
    """The one lineage `E5_stopping_rules` marked ACTIVE. Refuses if not exactly one."""
    rows = [r for r in _jsonl(path or (run_dir() / VERDICTS))
            if r.get("verdict") == "ACTIVE"]
    if len(rows) != 1:
        raise LineageUnavailable(
            f"{len(rows)} lineage(s) marked ACTIVE in {VERDICTS}, not 1 "
            f"({[r.get('lineage') for r in rows]}). This job freezes THE "
            f"surviving lineage; with none there is nothing to freeze, and with "
            f"several the choice is a decision somebody has to take on the "
            f"record rather than a `[0]` in a script.")
    return rows[0]


def genome_for(key: str, *, path: Path | None = None) -> dict:
    """The evaluation row whose `key` is `key`, with its genome."""
    for r in _jsonl(path or (run_dir() / EVALUATIONS)):
        if r.get("key") == key:
            return r
    raise LineageUnavailable(
        f"no evaluation row with key {key!r} in {EVALUATIONS}; the verdict file "
        f"names a representative the evaluation log does not carry, which means "
        f"the two receipts are from different runs")


def probe(sources: dict | None = None) -> dict:
    """Can the execution repo compute this rule's inputs? Feature by feature."""
    src = sources or FEATURE_SOURCES
    by_state: dict[str, list[str]] = {"yes": [], "partial": [], "no": []}
    for f, meta in src.items():
        by_state[meta["terminal"]].append(f)
    blocking = sorted(by_state["no"])
    executable = not blocking and not by_state["partial"]
    return {
        "executable_in_the_terminal_repo": executable,
        "n_features": len(src),
        "computable": sorted(by_state["yes"]),
        "partial_and_therefore_not_usable": sorted(by_state["partial"]),
        "missing": blocking,
        "missing_detail": {f: src[f] for f in blocking},
        "partial_detail": {f: src[f] for f in sorted(by_state["partial"])},
        "cross_section_objection": CROSS_SECTION_NOTE,
        "verdict": (
            "EXECUTABLE" if executable else
            f"NOT EXECUTABLE. {len(blocking)} of {len(src)} features have no "
            f"source on the execution side at all "
            f"({', '.join(blocking)}), and {len(by_state['partial'])} more have "
            f"only a DIFFERENT vendor's near-substitute, which is not the number "
            f"the weight was fitted on. Independently of both, every feature is a "
            f"within-month cross-sectional z and the execution repo's "
            f"cross-section is two orders of magnitude smaller."),
        "what_would_change_it": (
            "the engine-file pattern this chunk already built for Book F: the "
            "research side computes the monthly cross-section and ships a frozen "
            "per-name ranking, so the execution side needs none of the fourteen "
            "columns. That is a research job (a monthly rebuild of "
            "`train_table_long` from a PIT vintage that reaches 2026, which the "
            "panel currently does not), not a fleet change -- and it is the "
            "honest next step for this lineage."),
    }


def export(*, out_dir: Path | None = None) -> dict:
    """Freeze the rule, run the probe, write the file. Returns the receipt."""
    v = active_lineage()
    if v.get("lineage") != LINEAGE or v.get("representative_key") != REPRESENTATIVE:
        raise LineageUnavailable(
            f"the ACTIVE lineage is now {v.get('lineage')!r} / "
            f"{v.get('representative_key')!r}, not the {LINEAGE!r} / "
            f"{REPRESENTATIVE!r} this job was written against. Refusing rather "
            f"than freezing a different rule under the same name.")
    ev = genome_for(REPRESENTATIVE)
    g = ev["genome"]
    # A PROBE OVER A FEATURE LIST NOBODY CHECKED IS A PROBE OF THE WRONG RULE.
    # The classification below is written by hand; the weights are read off the
    # receipt. If the two ever name different features the probe is answering a
    # question about a genome that is not this one, so it REFUSES rather than
    # reporting a verdict about a subset.
    if set(g["w"]) != set(FEATURE_SOURCES):
        raise LineageUnavailable(
            f"the genome weights {sorted(set(g['w']) - set(FEATURE_SOURCES))} that "
            f"FEATURE_SOURCES does not classify, and FEATURE_SOURCES classifies "
            f"{sorted(set(FEATURE_SOURCES) - set(g['w']))} the genome does not "
            f"weight. A probe over a feature list nobody checked is a probe of "
            f"the wrong rule.")
    p = probe()

    payload = {
        "engine": ENGINE,
        "lineage": LINEAGE,
        "representative_key": REPRESENTATIVE,
        "licence": LICENCE,
        "job": JOB,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": {
            "kind": "linear composite of within-month cross-sectional z-scores",
            "weights": dict(g["w"]),
            "k": g["k"],
            "weighting": g["weight"],
            "hold_mult": g["hold_mult"],
            "hold_k": (None if g["hold_mult"] is None
                       else int(g["k"]) * int(g["hold_mult"])),
            "tradable_floor_usd": g["floor"],
            "rank": "descending by the composite; the top k are held",
            "panel": "backend/data/optimus/learner/train_table_long.parquet",
            "cost_bps_per_side": 25.0,
            "search_never_re_runs": (
                "this is a FIXED vector. Re-running the evolutionary search to "
                "re-derive it would be a new search with a new multiplicity "
                "budget, and the deflated Sharpe that licensed this row would "
                "not apply to the result."),
        },
        "dsr_receipt": {
            "path": f"{RUN_DIR}/{VERDICTS}",
            "verdict": v.get("verdict"),
            "reason": v.get("reason"),
            "observed_sharpe": v.get("observed_sharpe"),
            "expected_maximum_sharpe": v.get("expected_maximum_sharpe"),
            "dsr": v.get("dsr"),
            "dsr_bar": v.get("dsr_bar"),
            "n_observations": v.get("n_observations"),
            "banks_met": v.get("banks_met"),
            "n_windows_measured": v.get("n_windows_measured"),
            "pbo": v.get("pbo"),
            "pbo_status": v.get("pbo_status"),
        },
        "trials": {
            "n_trials_raw": v.get("n_trials_raw"),
            "n_trials_effective_proxy": v.get("n_trials_effective_proxy"),
            "n_trials_effective_onc": v.get("n_trials_effective_onc"),
            "gap": v.get("n_trials_effective_onc_gap"),
        },
        "dev_only": {
            "search_receipt": f"{RUN_DIR}/{SEARCH_RECEIPT}",
            "amendment": f"{RUN_DIR}/{SEARCH_AMENDMENT}",
            "holdout": "2016-2024 NOT READ by the search",
            "corrected_verdict_of_the_search": "CONDITIONAL",
            "two_standing_defects": [
                "the null genomes were NOT held to the arm's own drawdown "
                "refusal (69.3% of candidates were refused), so the fitness is "
                "'admissible minus typical', not 'admissible minus admissible'",
                "the archive ranked on ONE window bank for almost every lineage; "
                "this lineage is the exception (342 banks met)",
            ],
            "fitness_on_this_row": ev.get("result"),
            "full_dev_max_dd": ev.get("full_dev_max_dd"),
        },
        "terminal_repo_probe": p,
        "feature_sources": FEATURE_SOURCES,
    }

    d = Path(out_dir) if out_dir else engines_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"G3_lineage_{LINEAGE}.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return {"file": str(out), "payload": payload}


def G3_lineage_export(*, smoke: bool = False) -> dict:       # noqa: N802
    r = export()
    p = r["payload"]["terminal_repo_probe"]
    return {
        "job": JOB, "engine": ENGINE, "licence": LICENCE, "llm_spend_usd": 0.0,
        "lineage": LINEAGE, "representative_key": REPRESENTATIVE,
        "file": r["file"],
        "stage": "weights",
        "executable_in_the_terminal_repo": p["executable_in_the_terminal_repo"],
        "missing": p["missing"],
        "partial": p["partial_and_therefore_not_usable"],
        "headline": (
            f"lineage {LINEAGE} frozen as a static rule (14 weights, k="
            f"{r['payload']['rule']['k']}, {r['payload']['rule']['weighting']}, "
            f"hold_mult {r['payload']['rule']['hold_mult']}); DSR "
            f"{r['payload']['dsr_receipt']['dsr']} vs bar "
            f"{r['payload']['dsr_receipt']['dsr_bar']} at "
            f"{r['payload']['trials']['n_trials_raw']} raw trials. PROBE: "
            f"{len(p['missing'])} features have NO source in the execution repo "
            f"and {len(p['partial_and_therefore_not_usable'])} more have only a "
            f"different vendor's substitute"),
        "verdict": (
            "RULE FROZEN, NOT DEPLOYED. " + p["verdict"] + " Consequence, taken "
            "on the record: hack4 keeps its current mandate and is governed by "
            "the allocator's drawdown cut (TRIAL-DRAFT-ALLOCATOR-v0 section 1); "
            "this rule waits for a monthly cross-section on the execution side, "
            "which is the Book F engine-file pattern applied to a panel that "
            "does not yet reach 2026."),
        "family_max_p": None,
    }


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.out_dir:
        r = export(out_dir=Path(a.out_dir))
        print(json.dumps({"file": r["file"],
                          "probe": r["payload"]["terminal_repo_probe"]["verdict"]}, indent=1))
        return 0
    print(json.dumps(G3_lineage_export(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
