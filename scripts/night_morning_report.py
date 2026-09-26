"""J3 -- THE MORNING REPORT: what the night did, economics first, and five
questions each answered by a RULE.

WHY A RULE AND NOT A SUMMARY
============================
A night writes twenty receipts. A human reading them at 07:30 reads the two
with the longest headlines, and a session that shipped thirty engineering
changes and moved nothing says so nowhere. So the one question that matters --
*is AEGIS objectively better than it was last night?* -- is answered here by a
MECHANICAL rule: YES only if some receipt carries a closing line
`MODEL_IMPROVED:` / `CAPITAL_CHANGED:` / `WEIGHT_CHANGED:` with a measured
before -> after. No line, no YES. A night of clean engineering that moved no
number gets a NO with the sentence, which is the whole point.

The other four are the same shape: Q2 lists those lines verbatim, Q3 lists every
`HYPOTHESIS_KILLED:` / `BELIEF_CHANGED:`, Q4 names the first grade dates that
are actually owed, Q5 is J1's top curriculum item.

NEVER INVENT A NUMBER
=====================
Every block reads a named file. A missing or unreadable input prints
`CANNOT DETERMINE` **with the path it looked for**, because a blank line reads
as a zero and a zero here reads as "flat against the market". The scoreboard's
own `CANNOT DETERMINE` sentences are passed through verbatim rather than
re-derived -- there is exactly one place in this repository that knows why the
NAV is unknown on this machine, and it is not this file.

Runs inside the night factory as `J3_morning_report`, and standalone:

    python -m scripts.night_morning_report --date 2026-09-22 --out report.md

Licence: PRODUCT_EXPERIMENT. Reads receipts; writes one Markdown file and one
receipt. No model is called and `llm_spend_usd` is 0.0 by construction.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "J3_morning_report"
LICENCE = "PRODUCT_EXPERIMENT"
STAGE = "pnl"

#: A receipt earns a YES on Q1 only by carrying one of these prefixes with a
#: measured before -> after. They are scanned for in every STRING VALUE of every
#: receipt in the night folder, at any depth: a job should not have to know
#: which key the reader looks at, only to say the sentence.
IMPROVEMENT_PREFIXES = ("MODEL_IMPROVED:", "CAPITAL_CHANGED:", "WEIGHT_CHANGED:")
BELIEF_PREFIXES = ("HYPOTHESIS_KILLED:", "BELIEF_CHANGED:")

#: The champion/challenger jobs whose receipts carry a before/after metric.
MODEL_JOBS = ("E1_event_head", "E2_embedding_horizon", "E3_adaptive_conformal",
              "E4_adwin_gated_refit", "E5_stopping_rules", "N3_frozen_embedding_head")

#: Statuses that are a job NOT finishing, and what to call each in the report.
FAILED_STATUSES = ("REFUSED", "PENDING_MODEL", "FAILED", "ERROR", "TIMEOUT",
                   "running", "CANNOT_DETERMINE")

MAX_LINES = 120


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_date() -> str:
    return datetime.now().date().isoformat()


def data_dir() -> Path:
    return REPO / "backend" / "data" / "optimus"


def night_dir(day: str) -> Path:
    return data_dir() / f"night_factory_{day}"


# ===========================================================================
# READING
# ===========================================================================


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_receipts(folder: Path) -> dict:
    """Every `*.json` in the night folder, keyed by filename stem."""
    out: dict = {}
    if not Path(folder).is_dir():
        return out
    for f in sorted(Path(folder).glob("*.json")):
        payload = read_json(f)
        if isinstance(payload, dict):
            out[f.stem] = payload
    return out


def find_receipt(receipts: dict, *needles: str):
    """The first receipt whose stem or `job` contains any needle."""
    for stem, payload in receipts.items():
        job = str(payload.get("job") or payload.get("receipt") or "")
        for n in needles:
            if n.lower() in stem.lower() or n.lower() in job.lower():
                return stem, payload
    return None, None


def scan_lines(node, prefixes: tuple[str, ...], path: str = "") -> list[tuple[str, str]]:
    """Every (json path, string) in `node` whose text starts with a prefix.

    Depth-first over dicts, lists and strings. A prefix is matched on the
    STRIPPED string, so a line written as part of a longer verdict paragraph is
    found by `split` on newlines too -- a job that ends its verdict with the
    sentence does not have to give it its own key.
    """
    hits: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            hits += scan_lines(v, prefixes, f"{path}.{k}" if path else str(k))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            hits += scan_lines(v, prefixes, f"{path}[{i}]")
    elif isinstance(node, str):
        for chunk in node.splitlines():
            s = chunk.strip()
            for p in prefixes:
                if s.startswith(p):
                    hits.append((path, s))
                    break
    return hits


def scan_all(receipts: dict, prefixes: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    for stem, payload in sorted(receipts.items()):
        for where, line in scan_lines(payload, prefixes):
            out.append({"receipt": stem, "at": where, "line": line})
    return out


def has_before_after(line: str) -> bool:
    """A closing line only counts when it carries a measured before -> after.

    The cheapest honest test: the line contains an arrow AND at least two
    numbers. `MODEL_IMPROVED: it feels better` is not an improvement, and a rule
    that accepted it would make Q1 a formality within a week.
    """
    import re

    arrow = ("->" in line) or ("→" in line) or (" to " in line)
    nums = re.findall(r"[-+]?\d*\.?\d+", line)
    return bool(arrow and len(nums) >= 2)


# ===========================================================================
# BLOCKS
# ===========================================================================


def cannot(what: str, path) -> str:
    return f"CANNOT DETERMINE: {what} (looked for `{path}`)"


def block_money(day: str) -> list[str]:
    """MONEY FIRST, from the BROKER, not from our own arithmetic.

    Added 2026-09-22. The previous NAV block read `daily_pass.scoreboard`, a
    path that never carried a broker number, so the report printed
    "CANNOT DETERMINE" every morning while the account itself was one HTTP call
    away. `pc_broker.snapshot` now writes the venue's own equity to
    `pc_book/<date>/nav.jsonl` on every tick of the live loop, and this reads
    that. If the file is absent the loop did not run, and THAT is the finding —
    printed as such, not as a missing number.
    """
    from pathlib import Path as _P
    book = _P(__file__).resolve().parents[1] / "backend" / "data" / "optimus" / "pc_book" / day
    nav = book / "nav.jsonl"
    if not nav.exists():
        return ["- " + cannot(
            "the live market loop wrote no NAV: it did not run, or it held no "
            "broker lease. This is an OPERATIONAL finding, not a missing number "
            "— the account can be read in one call", nav)]
    rows = read_jsonl(nav)
    if not rows:
        return ["- " + cannot("nav.jsonl exists but is empty", nav)]
    first, last = rows[0], rows[-1]
    d_eq = last["equity"] - first["equity"]
    pct = (d_eq / first["equity"] * 100) if first["equity"] else float("nan")
    lines = [
        f"- **equity ${last['equity']:,.2f}** (account {last.get('account_number')}), "
        f"cash ${last['cash']:,.2f}, {last['n_positions']} positions, "
        f"{(last.get('invested_frac') or 0)*100:.0f}% invested",
        f"- session move: ${d_eq:+,.2f} ({pct:+.2f}%) across {len(rows)} broker reads "
        f"{first['t'][11:16]}Z -> {last['t'][11:16]}Z",
    ]
    if last.get("intraday_return") is not None:
        lines.append(f"- vs the broker's own last_equity: {last['intraday_return']*100:+.2f}%")
    pos = sorted(last.get("positions") or [], key=lambda p: p["unrealized_pl"])
    if pos:
        w, b = pos[0], pos[-1]
        lines.append(f"- best {b['symbol']} ${b['unrealized_pl']:+,.0f} "
                     f"({b['unrealized_plpc']*100:+.1f}%) · "
                     f"worst {w['symbol']} ${w['unrealized_pl']:+,.0f} "
                     f"({w['unrealized_plpc']*100:+.1f}%)")
    stopped = read_json(book / "LIVE_LOOP_STOPPED.json")
    if isinstance(stopped, dict):
        v = (stopped.get("ranking_verdict") or {}).get("verdict")
        lines.append(f"- loop: mode {stopped.get('mode')}, {stopped.get('orders_sent')} orders sent"
                     + (f", ranking {v}" if v else "")
                     + (f", HALTED {stopped['halted']}" if stopped.get("halted") else ""))
    return lines


def block_ranking(day: str, top_n: int = 20) -> list[str]:
    """The twenty best next-month names, with the number that sized them.

    Added 2026-09-22. This is the answer to "what should I own next month" and
    it is the Bloomberg Challenge's own unit — next-21-session RELATIVE return.
    The expected return printed is the REALISED out-of-sample mean of that score
    decile, never a model output; an uncalibrated decile prints so rather than
    printing a zero that reads as a confident flat call.
    """
    from pathlib import Path as _P
    p = (_P(__file__).resolve().parents[1] / "backend" / "data" / "optimus"
         / "pc_book" / day / "ranking.json")
    r = read_json(p)
    if not isinstance(r, dict):
        return ["- " + cannot("the live loop wrote no ranking", p)]
    v = r.get("verdict") or {}
    out = [f"- {r.get('n_eligible', 0):,} eligible names ranked as of {r.get('asof')} "
           f"(model {r.get('model_version')}, {r.get('elapsed_s')}s)",
           f"- **{v.get('verdict')}** — {v.get('why')}"]
    rows = (r.get("top") or [])[:top_n]
    if not rows:
        out.append("- " + cannot("the ranking carries no names", p))
        return out
    out.append("")
    out.append("| # | ticker | decile | exp rel 21d (net) | downside p20 | P(beat) | liquidity |")
    out.append("|---|---|---|---|---|---|---|")
    for x in rows:
        er = x.get("expected_relative_return_21d_net")
        dn = x.get("downside_21d")
        pb = x.get("probability_beat_benchmark")
        out.append(
            f"| {x.get('rank')} | {x.get('symbol')} | {x.get('decile')} | "
            f"{'UNMEASURED' if er is None else f'{er*100:+.2f}%'} | "
            f"{'—' if dn is None else f'{dn*100:+.2f}%'} | "
            f"{'—' if pb is None else f'{pb*100:.0f}%'} | "
            f"{x.get('liquidity_band')} |")
    return out


def _nav_summary(nav) -> str:
    """22 books of raw JSON on the first line nobody can read is not a report.

    Keeps every number that decides anything — the spread, the benchmark, the
    excess, the worst and best book — and drops the per-book array, which is on
    disk for anyone who wants it.
    """
    if not isinstance(nav, dict):
        return str(nav) if nav else ""
    books = nav.get("books") or []
    if not books:
        return str(nav)[:300]
    best = max(books, key=lambda b: b.get("pct", 0))
    worst = min(books, key=lambda b: b.get("pct", 0))
    w = nav.get("window") or {}
    return (f"{nav.get('n_books')} books, mean {nav.get('mean_since_inception_pct'):+.2f}% vs "
            f"{nav.get('benchmark_symbol')} {nav.get('benchmark_pct'):+.2f}% "
            f"= excess {nav.get('excess_pct'):+.2f}% "
            f"({w.get('first_date')}..{w.get('last_date')}); "
            f"best {best['book'][-8:]} {best['pct']:+.2f}%, "
            f"worst {worst['book'][-8:]} {worst['pct']:+.2f}%")


def block_nav(receipts: dict, folder: Path, day: str) -> list[str]:
    lines = block_money(day)
    stem, pas = find_receipt(receipts, f"daily_pass_{day}", "daily_pass")
    sb = (pas or {}).get("scoreboard") if isinstance(pas, dict) else None
    if not isinstance(sb, dict):
        lines.append("- internal lanes: " + cannot(
            "no daily-pass receipt carries a `scoreboard` block",
            folder / f"daily_pass_{day}.json"))
        return lines
    lines += [f"- internal NAV vs SPY: {_nav_summary(sb.get('nav_vs_spy')) or cannot('the scoreboard names no NAV', stem)}",
              f"- EXPLOIT P&L: {sb.get('exploit_pnl') or 'CANNOT DETERMINE'}",
              f"- EXPLORE P&L: {sb.get('explore_pnl') or 'CANNOT DETERMINE'}"]
    cap = sb.get("capital_resolution") or {}
    if cap:
        lines.append(f"- capital resolved: {cap.get('nothing_happened_is_not_allowed') or cap}")
    return lines


def block_authority(contract: dict | None, ledger: list[dict], folder: Path,
                    day: str) -> list[str]:
    if not isinstance(contract, dict):
        return ["- " + cannot("no decision contract on disk",
                              data_dir() / "decisions" / f"{day}.json")]
    rows = contract.get("rows") or []
    by_auth: dict = {}
    names: dict = {}
    for r in rows:
        a = str(r.get("authority") or "UNCLASSIFIED")
        by_auth[a] = by_auth.get(a, 0) + 1
        names.setdefault(a, set()).add(str(r.get("ticker")))
    lines = [f"- direction: {contract.get('count_by_direction')}",
             f"- authority: {by_auth or 'CANNOT DETERMINE: no row carries an authority'}"]
    for a in ("EXPLOIT", "EXPLORE", "PROBE"):
        if a in names:
            got = sorted(n for n in names[a] if n and n != "None")
            lines.append(f"- {a} names ({len(got)}): {', '.join(got[:12])}"
                         + (" ..." if len(got) > 12 else ""))
    states: dict = {}
    for r in ledger:
        states[str(r.get("state"))] = states.get(str(r.get("state")), 0) + 1
    lines.append(f"- decision ledger states: {states or cannot('no ledger rows', 'decisions/ledger.jsonl')}")
    return lines


def block_roi(contract: dict | None) -> list[str]:
    if not isinstance(contract, dict):
        return ["- CANNOT DETERMINE: no contract, so no ROI rows"]
    roi = contract.get("roi_ranking") or {}
    if not roi:
        return ["- CANNOT DETERMINE: the contract carries no `roi_ranking` block"]
    seen = roi.get("calibration_seen") or {}
    lines = [f"- ROI rule: {roi.get('rule')}; considered {roi.get('n_considered')}, "
             f"scored {roi.get('n_scored')}, not calibrated {roi.get('n_not_calibrated')}"]
    ranked = []
    for tkr, blk in seen.items():
        mu = blk.get("decile_mean_pct")
        if mu is not None:
            ranked.append((float(mu), tkr, blk.get("signal"), blk.get("calibration_verdict")))
    ranked.sort(reverse=True)
    if ranked:
        for mu, tkr, sig, v in ranked[:5]:
            lines.append(f"  - {tkr} ({sig}): {mu:+.4f}%/horizon, calibration {v}")
    else:
        lines.append("  - CANNOT DETERMINE: no name carries a calibrated expected return")
    return lines


def block_calibration(receipts: dict) -> list[str]:
    stem, c7 = find_receipt(receipts, "C7_signal_calibration", "calibrate_signal")
    if not isinstance(c7, dict):
        return ["- " + cannot("no C7 calibration receipt in the night folder",
                              "night_factory_<date>/C7_signal_calibration_run*.json")]
    verdicts = (c7.get("verdicts") or c7.get("counts_by_verdict")
                or c7.get("summary") or c7.get("counts") or {})
    lines = [f"- {stem}: {c7.get('headline') or c7.get('verdict') or 'no headline'}"]
    if verdicts:
        lines.append(f"- per-signal: {json.dumps(verdicts, default=str)[:400]}")
    else:
        lines.append("- per-signal: CANNOT DETERMINE — the receipt carries no "
                     "`verdicts`/`summary` block; the counts above are its headline")
    return lines


def block_errors(receipts: dict) -> list[str]:
    stem, j1 = find_receipt(receipts, "J1_error_dataset")
    if not isinstance(j1, dict):
        return ["- " + cannot("no J1 error-dataset receipt",
                              "night_factory_<date>/J1_error_dataset_run*.json")]
    lines = [f"- {j1.get('headline')}"]
    for e in (j1.get("largest_errors") or [])[:5]:
        lines.append(f"  - {e.get('ticker')} {e.get('date')} {e.get('mechanism')}: "
                     f"expected {e.get('expected')}, actual {e.get('actual')} "
                     f"({e.get('cluster')})")
    for c in (j1.get("curriculum") or [])[:3]:
        lines.append(f"  - CURRICULUM {c.get('cluster')} (n {c.get('count')}, "
                     f"priority {c.get('priority')}): {c.get('experiment')}")
    return lines


def block_missed(receipts: dict) -> list[str]:
    stem, j2 = find_receipt(receipts, "J2_missed_opportunity", "missed_opportunity")
    if not isinstance(j2, dict):
        return ["- " + cannot("no J2 missed-opportunity receipt (it may not have run)",
                              "night_factory_<date>/J2_missed_opportunity*.json")]
    lines = [f"- {j2.get('headline') or j2.get('verdict') or stem}"]
    paired = j2.get("paired")
    if paired is not None:
        lines.append(f"- paired: {paired if not isinstance(paired, dict) else json.dumps(paired)[:200]}")
    top = j2.get("top_missed")
    if isinstance(top, list):
        for m in top[:5]:
            lines.append(f"  - {json.dumps(m, default=str)[:180]}")
    elif top is not None:
        lines.append(f"  - {json.dumps(top, default=str)[:200]}")
    return lines


def block_drift(receipts: dict) -> list[str]:
    stem, e4 = find_receipt(receipts, "E4_adwin")
    if not isinstance(e4, dict):
        return ["- " + cannot("no E4 ADWIN receipt", "night_factory_<date>/E4_adwin_gated_refit_run*.json")]
    tl = e4.get("timeline")
    cost = e4.get("cost") or {}
    refits = cost.get("refits") or {}
    fired = refits.get("ADWIN")
    if fired is None:
        return [f"- {stem}: CANNOT DETERMINE — the receipt carries no refit count"]
    detected = "DRIFT DETECTED" if int(fired) > 1 else "NO DRIFT DETECTED"
    return [f"- {detected}: ADWIN refit {fired}x vs FIXED {refits.get('FIXED')}",
            f"- timeline: {json.dumps(tl, default=str)[:220] if tl else 'none on the receipt'}"]


def block_models(receipts: dict) -> list[str]:
    lines: list[str] = []
    for job in MODEL_JOBS:
        stem, r = find_receipt(receipts, job)
        if not isinstance(r, dict):
            continue
        verdict = str(r.get("verdict") or "")
        status = str(r.get("status") or "")
        call = ("promoted" if "promot" in verdict.lower()
                else "rejected" if ("reject" in verdict.lower()
                                    or "FAILED_VARIANT" in verdict)
                else "NO_IMPROVEMENT")
        lines.append(f"- {job}: {call} (status {status or 'unknown'}) — "
                     f"{(r.get('headline') or verdict or 'no headline')[:200]}")
    if not lines:
        lines = ["- " + cannot("no champion/challenger receipt in the night folder",
                               "night_factory_<date>/{E1,E3,E4,E5}*.json")]
    return lines


def block_gym(receipts: dict) -> list[str]:
    stem, s2 = find_receipt(receipts, "S2_scenario_gym", "scenario_gym")
    if not isinstance(s2, dict):
        return ["- " + cannot("no gym receipt", "night_factory_<date>/S2_scenario_gym_run*.json")]
    return [f"- {stem}: {s2.get('headline') or s2.get('verdict') or s2.get('status')}"]


def block_bandit(ledger: list[dict], contract: dict | None) -> list[str]:
    scored = sum(1 for r in ledger if str(r.get("state")) == "SCORED")
    need = 30
    try:
        from backend import config
        need = int(getattr(config, "PROBE_MIN_GRADED", 30))
    except Exception:                                               # noqa: BLE001
        pass
    return [f"- bandit / off-policy evaluation: CANNOT DETERMINE — {scored} SCORED "
            f"decision row(s) on the ledger against the {need} the gate requires. "
            f"An OPE estimate on {scored} rows would be a number about the prior."]


def block_spend(receipts: dict, folder: Path, day: str) -> list[str]:
    rows = read_jsonl(data_dir() / "deepseek_balance.jsonl")
    night = [r for r in rows if str(r.get("read_at") or "")[:10] in
             (day, _prev_day(day))]
    lines: list[str] = []
    if len(night) >= 2:
        first, last = night[0], night[-1]
        f_tot, l_tot = first.get("total_usd"), last.get("total_usd")
        if f_tot is not None and l_tot is not None:
            lines.append(f"- provider balance {f_tot} -> {l_tot} "
                         f"(delta {float(l_tot) - float(f_tot):+.4f} USD, "
                         f"topped up {last.get('topped_up_usd')})")
    if not lines:
        lines.append("- " + cannot("fewer than two balance reads cover this night",
                                   data_dir() / "deepseek_balance.jsonl"))
    ours = 0.0
    for stem, r in receipts.items():
        v = r.get("llm_spend_usd")
        try:
            ours += float(v)
        except (TypeError, ValueError):
            continue
    lines.append(f"- our ledger: {ours:.4f} USD across {len(receipts)} receipt(s) "
                 f"(a receipt that declares no `llm_spend_usd` contributes nothing "
                 f"and is not counted as zero spend)")
    return lines


def _prev_day(day: str) -> str:
    from datetime import date, timedelta
    try:
        return str(date.fromisoformat(day) - timedelta(days=1))
    except ValueError:
        return day


def block_machine(folder: Path) -> list[str]:
    logs = sorted(Path(folder).glob("night_local_*.log")) if Path(folder).is_dir() else []
    if not logs:
        return ["- " + cannot("no night log in the folder", f"{folder}/night_local_*.log")]
    log = logs[-1]
    try:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    except OSError:
        return ["- " + cannot("the night log could not be read", log)]
    hits = [ln.strip() for ln in tail
            if any(k in ln for k in ("GPU", "VRAM", "CPU", "MiB", "nvidia"))]
    if not hits:
        return [f"- {log.name}: CANNOT DETERMINE — no GPU/CPU line in the last 400 lines"]
    return [f"- {log.name}: {hits[-1][:200]}"]


def block_jobs(receipts: dict) -> list[str]:
    bad, ok, silent = [], 0, []
    for stem, r in sorted(receipts.items()):
        st = str(r.get("status") or "")
        if not st:
            # NOT skipped: a receipt that declares no status is a receipt whose
            # outcome nobody can read, and counting it as "finished" is exactly
            # the silence this block exists to break.
            silent.append(stem)
            continue
        if st in FAILED_STATUSES or st.startswith("REFUSED"):
            bad.append(f"  - {stem}: {st} — {(str(r.get('verdict') or ''))[:140]}")
        else:
            ok += 1
    lines = [f"- {ok} receipt(s) declared a finished status; {len(bad)} did not; "
             f"{len(silent)} declared NO status at all"]
    if silent:
        lines.append(f"  - no status declared: {', '.join(silent[:10])}"
                     + (" ..." if len(silent) > 10 else ""))
    return lines + bad[:12]


def block_stop(folder: Path) -> list[str]:
    p = Path(folder) / "NIGHT_STOPPED.json"
    alt = data_dir() / "NIGHT_STOPPED.json"
    for cand in (p, alt):
        payload = read_json(cand)
        if isinstance(payload, dict):
            return [f"- STOP CONFIRMED: {json.dumps(payload, default=str)[:400]}"]
    lab = read_json(data_dir() / "lab_status.json")
    if isinstance(lab, dict):
        return [f"- no `NIGHT_STOPPED.json`; `lab_status.json` says running="
                f"{lab.get('running')} stopped_by={lab.get('stopped_by')} "
                f"pid={lab.get('pid')} at {lab.get('utc')}"]
    return ["- " + cannot("no stop confirmation and no lab status",
                          f"{folder}/NIGHT_STOPPED.json")]


# ===========================================================================
# THE FIVE QUESTIONS
# ===========================================================================


def five_questions(receipts: dict, contract: dict | None) -> dict:
    improved = [h for h in scan_all(receipts, IMPROVEMENT_PREFIXES)
                if has_before_after(h["line"])]
    unmeasured = [h for h in scan_all(receipts, IMPROVEMENT_PREFIXES)
                  if not has_before_after(h["line"])]
    beliefs = scan_all(receipts, BELIEF_PREFIXES)

    q1 = ("YES" if improved else "NO")
    q1_why = (f"{len(improved)} receipt line(s) carry a measured before -> after"
              if improved else
              ("NO receipt in this night's folder carries a "
               f"{'/'.join(IMPROVEMENT_PREFIXES)} line with a measured before -> after, "
               "so nothing measurable moved. Engineering happened; the numbers did not."
               + (f" ({len(unmeasured)} line(s) carried the prefix and no measured "
                  f"before -> after, and do not count.)" if unmeasured else "")))

    owed: list[str] = []
    if isinstance(contract, dict):
        for r in (contract.get("rows") or []):
            if r.get("direction") in ("PROBE",) or r.get("authority") == "EXPLORE":
                exp = r.get("expiry_utc")
                if exp:
                    owed.append(f"{r.get('ticker')} ({r.get('direction')}/"
                                f"{r.get('authority')}) first grade {str(exp)[:10]}")
    owed = sorted(set(owed))

    weak: list[str] = []
    if isinstance(contract, dict):
        for tkr, blk in ((contract.get("roi_ranking") or {}).get("calibration_seen") or {}).items():
            if str(blk.get("calibration_verdict")) == "WEAK":
                weak.append(f"{tkr}/{blk.get('signal')}: WEAK, spread t "
                            f"{blk.get('spread_t')}, Holm p {blk.get('holm_p')}")

    _, j1 = find_receipt(receipts, "J1_error_dataset")
    curr = (j1 or {}).get("curriculum") or []
    q5 = (f"{curr[0].get('cluster')} (n {curr[0].get('count')}): {curr[0].get('experiment')}"
          if curr else cannot("no J1 curriculum", "night_factory_<date>/J1_error_dataset_run*.json"))

    return {
        "Q1_better_than_last_night": q1,
        "Q1_why": q1_why,
        "Q2_improvement_lines": improved,
        "Q2_prefixed_lines_without_a_measured_before_after": unmeasured,
        "Q3_belief_lines": beliefs,
        "Q4_first_grade_dates_owed": owed,
        "Q4_weak_calibration_cells": weak,
        "Q5_top_curriculum_item": q5,
    }


# ===========================================================================
# THE REPORT
# ===========================================================================


def _subsystem_lines() -> list[str]:
    """The health probes' DEAD/STALE rows, one line each (review 2026-09-26 §4.3)."""
    try:
        from backend.services.system_health import non_alive_lines
        return non_alive_lines()
    except Exception as exc:                                    # noqa: BLE001
        return [f"_subsystems: CANNOT DETERMINE ({type(exc).__name__})_"]


def render(day: str, folder: Path, receipts: dict, contract: dict | None,
           ledger: list[dict], q: dict) -> str:
    """The report, body first and the five questions last.

    The line cap trims the BODY, never the questions: a report truncated at the
    bottom would drop the one section a reader is here for, and the sections
    above it are all recoverable from the receipts the header names.
    """
    L: list[str] = []
    L.append(f"# MORNING REPORT {day}")
    L.append("")
    L.append(f"Night folder `{folder}` — {len(receipts)} receipt(s). "
             f"Written {_now()}. Licence PRODUCT_EXPERIMENT; no model was called.")
    L.append("")
    L.append("## 0. Subsystems not ALIVE (DEAD/STALE first)")
    L += _subsystem_lines()
    L.append("")
    L.append("## 1. Paper NAV vs SPY")
    L += block_nav(receipts, folder, day)
    L.append("")
    L.append("## 1b. The twenty best next-month names")
    L += block_ranking(day)
    L.append("")
    L.append("## 2. EXPLOIT / EXPLORE / PROBE")
    L += block_authority(contract, ledger, folder, day)
    L.append("")
    L.append("## 3. Expected-return leaders")
    L += block_roi(contract)
    L.append("")
    L.append("## 4. Calibration verdicts")
    L += block_calibration(receipts)
    L.append("")
    L.append("## 5. Largest graded errors and the curriculum")
    L += block_errors(receipts)
    L.append("")
    L.append("## 6. Missed opportunities")
    L += block_missed(receipts)
    L.append("")
    L.append("## 7. Drift")
    L += block_drift(receipts)
    L.append("")
    L.append("## 8. Champion vs challengers")
    L += block_models(receipts)
    L.append("")
    L.append("## 9. Gym")
    L += block_gym(receipts)
    L.append("")
    L.append("## 10. Bandit / OPE")
    L += block_bandit(ledger, contract)
    L.append("")
    L.append("## 11. DeepSeek spend")
    L += block_spend(receipts, folder, day)
    L.append("")
    L.append("## 12. Machine")
    L += block_machine(folder)
    L.append("")
    L.append("## 13. Jobs that did not finish")
    L += block_jobs(receipts)
    L.append("")
    L.append("## 14. STOP confirmation")
    L += block_stop(folder)
    L.append("")
    Q: list[str] = []
    Q.append("## THE FIVE QUESTIONS")
    Q.append(f"**Q1 — Is AEGIS objectively better than last night? {q['Q1_better_than_last_night']}.** "
             f"{q['Q1_why']}")
    Q.append("")
    Q.append("**Q2 — What measurably improved?**")
    if q["Q2_improvement_lines"]:
        for h in q["Q2_improvement_lines"][:10]:
            Q.append(f"- `{h['receipt']}` {h['line']}")
    else:
        Q.append("- none")
    Q.append("")
    Q.append("**Q3 — What belief changed or died?**")
    if q["Q3_belief_lines"]:
        for h in q["Q3_belief_lines"][:10]:
            Q.append(f"- `{h['receipt']}` {h['line']}")
    else:
        Q.append("- none")
    Q.append("")
    Q.append("**Q4 — What is owed, and when?**")
    for s in (q["Q4_first_grade_dates_owed"][:10] or ["none"]):
        Q.append(f"- {s}")
    for s in q["Q4_weak_calibration_cells"][:5]:
        Q.append(f"- WEAK near-miss: {s}")
    Q.append("")
    Q.append(f"**Q5 — What should tonight test?** {q['Q5_top_curriculum_item']}")
    Q.append("")

    over = len(L) + len(Q) - MAX_LINES
    if over > 0:
        cut = min(over + 2, max(0, len(L) - 4))
        elided = L[len(L) - cut:]
        L = L[: len(L) - cut]
        L.append(f"_({cut} body line(s) truncated to keep the report under "
                 f"{MAX_LINES} lines; the elided sections are recoverable from the "
                 f"receipts in `{folder}`. First elided line: "
                 f"{(elided[0] if elided else '')[:80]})_")
        L.append("")
    return "\n".join(L + Q) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="J3 -- the morning report")
    ap.add_argument("--out", default=None, help="the Markdown report path")
    ap.add_argument("--receipt-out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0,
                    help="accepted for interface parity; nothing here is random")
    ap.add_argument("--resume", action="store_true", help="tolerated; one pass")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--date", default=None)
    ap.add_argument("--folder", default=None, help="override the night folder")
    ap.add_argument("--stage", default=STAGE)
    args = ap.parse_args(argv)

    t0 = time.time()
    day = args.date or run_date()
    folder = Path(args.folder) if args.folder else night_dir(day)
    receipts = load_receipts(folder)
    contract = read_json(data_dir() / "decisions" / f"{day}.json")
    ledger = read_jsonl(data_dir() / "decisions" / "ledger.jsonl")
    ledger = [r for r in ledger if str(r.get("asof") or "")[:10] == day] or ledger

    q = five_questions(receipts, contract if isinstance(contract, dict) else None)
    md = render(day, folder, receipts, contract if isinstance(contract, dict) else None,
                ledger, q)

    out_md = Path(args.out) if args.out else (folder / f"MORNING_REPORT_{day}.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    receipt = {
        "job": JOB, "licence": LICENCE, "stage": args.stage, "llm_spend_usd": 0.0,
        "run": args.run, "smoke": bool(args.smoke), "date": day,
        "report_path": str(out_md),
        "night_folder": str(folder),
        "n_receipts_read": len(receipts),
        "receipts_read": sorted(receipts),
        "contract_on_disk": isinstance(contract, dict),
        "n_ledger_rows": len(ledger),
        "report_lines": len(md.splitlines()),
        "five_questions": q,
        "method": {
            "improvement_prefixes": list(IMPROVEMENT_PREFIXES),
            "belief_prefixes": list(BELIEF_PREFIXES),
            "q1_rule": ("YES only if some receipt carries an improvement prefix WITH a "
                        "measured before -> after (an arrow and at least two numbers); "
                        "otherwise NO with the sentence"),
            "llm": "NONE. There is no call site in this module.",
        },
        "headline": (f"{day}: Q1 {q['Q1_better_than_last_night']} — "
                     f"{len(q['Q2_improvement_lines'])} measured improvement line(s), "
                     f"{len(q['Q3_belief_lines'])} belief line(s), "
                     f"{len(receipts)} receipt(s) read"),
        "verdict": q["Q1_why"],
        "status": "done",
        "elapsed_s": round(time.time() - t0, 1),
        "written_utc": _now(),
    }
    out_json = Path(args.receipt_out) if args.receipt_out else (
        folder / f"{JOB}_run{args.run:02d}{'_smoke' if args.smoke else ''}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print("\n" + receipt["headline"])
    print(receipt["verdict"])
    print(f"report:  {out_md}")
    print(f"receipt: {out_json}")
    return 0


def J3_morning_report(smoke: bool = False, run: int = 1) -> dict:
    day = run_date()
    out = night_dir(day) / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["--run", str(run), "--receipt-out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
