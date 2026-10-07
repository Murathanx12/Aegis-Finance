"""Speak with results: what is ahead of SPY, by how much, over which window, with
which label, and what would raise it -- then what is not yet claimable.

    python -m scripts.results_voice                 # newest run id both receipts share
    python -m scripts.results_voice --run-id 2026-10-06T235345Z

WHY (2026-10-07, the owner)
===========================
"Rather than saying we have 100% proof, we should say that we have this amount
of success... at this point we have this, this, this. This is doing really well
compared to S&P 500. This can be improved by this."

Every scoreboard had been opening with what could NOT be claimed, so a book up
+7% in a week against SPY's +1.4% read as "no improvement". The methodology does
not change here: the labels are book_dna's (OBSERVED(n) / EARLY_EVIDENCE /
REPLICATED, never VALIDATED_EDGE from this path), leaders are said to be chosen
after the fact, every window and session count is printed, and controls and
twins never count as strategies. What changes is the ORDER: results first, with
their label and the specific thing that would raise it; the claim boundary last,
as one line (`CLAIMS PROMOTED: ...`).

WHAT IT READS / WRITES
======================
Reads `paper_accounts/roi_<run>.json` + `paper_accounts/book_dna_<run>.json`
(the same run id). Writes `results_voice_<run>.json` and `results_voice_<run>.md`
beside them. Deterministic: no clock is read except to pick the default run id
(which is the newest shared run id on disk, itself not a clock). Every section
names the receipt paths its numbers came from. No equity dollars are written.

A missing receipt, an empty row set or a run id without both files REFUSES
(`ResultsVoiceRefused`); a writer that cannot find its inputs says so and never
emits an empty "0 of 0 ahead" headline.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any, Optional

from backend import config as _config
from backend.services import book_dna as _dna

SCHEMA = "results_voice/1"
REPO = Path(__file__).resolve().parents[2]
PA_DIR = Path(_config.OPTIMUS_LEDGER_DIR) / "paper_accounts"
RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")
_HASH_RE = re.compile(r"\[([0-9a-f]{8})\]\s*$")


class ResultsVoiceRefused(RuntimeError):
    """The inputs a results statement needs are not there (no pair, no rows)."""


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def params() -> dict:
    return {
        "control_name_markers": list(_cfg("RESULTS_VOICE_CONTROL_NAME_MARKERS",
                                          ("_random_twin", "comparato", "__", "-control"))),
        "bet_jaccard": float(_cfg("RESULTS_VOICE_BET_JACCARD", 0.80)),
        "n_leaders": int(_cfg("RESULTS_VOICE_N_LEADERS", 5)),
        "n_losers": int(_cfg("RESULTS_VOICE_N_LOSERS", 5)),
        "random_twin_kinds": list(_cfg("RESULTS_VOICE_RANDOM_TWIN_KINDS",
                                       ("matched_twin21", "matched_random", "random_same_band",
                                        "random_sleeve"))),
        "label_ladder": list(_dna.LABEL_LADDER),
        "label_ceiling_of_book_dna": _dna.LABEL_CEILING,
    }


def rel(p: Path) -> str:
    p = Path(p)
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return p.name


# ───────────────────────────────────────────────────────────── locating inputs

def run_ids(folder: Path, prefix: str) -> set[str]:
    out = set()
    if not Path(folder).is_dir():
        return out
    for p in Path(folder).glob(f"{prefix}_*.json"):
        rid = p.name[len(prefix) + 1:-len(".json")]
        if RUN_ID_RE.match(rid):
            out.add(rid)
    return out


def newest_shared_run_id(folder: Path = PA_DIR) -> str:
    shared = run_ids(folder, "roi") & run_ids(folder, "book_dna")
    if not shared:
        raise ResultsVoiceRefused(f"no run id has both roi_<run>.json and book_dna_<run>.json in {rel(folder)}")
    return max(shared)


def load_pair(run_id: str, folder: Path = PA_DIR) -> tuple[dict, dict, Path, Path]:
    if not run_id or not RUN_ID_RE.match(str(run_id)):
        raise ResultsVoiceRefused(f"run id {run_id!r} is not of the form YYYY-MM-DDTHHMMSSZ")
    rp, dp = Path(folder) / f"roi_{run_id}.json", Path(folder) / f"book_dna_{run_id}.json"
    for p in (rp, dp):
        if not p.is_file():
            raise ResultsVoiceRefused(f"{rel(p)} is not on disk")
    return (json.loads(rp.read_text(encoding="utf-8")), json.loads(dp.read_text(encoding="utf-8")), rp, dp)


# ───────────────────────────────────────────────────────────── classification

def control_reason(account: str, book: Optional[dict], markers: list[str]) -> Optional[str]:
    """Why an account is a control/twin and not a strategy, or None."""
    b = book or {}
    if b.get("twin_of"):
        return f"twin_of {b['twin_of']}"
    if b.get("category") in ("twin", "control"):
        return f"book_dna category {b['category']}"
    for m in markers:
        if m in account:
            return f"name contains {m!r}"
    return None


def short_name(account: str, width: int = 40) -> str:
    m = _HASH_RE.search(account)
    if m:
        text = account[:m.start()].strip()
        return f"{text[:width - 12].rstrip()}... [{m.group(1)}]" if len(text) > width - 12 else account
    return account


def mechanism(account: str, book: Optional[dict], family: Optional[str]) -> tuple[str, str]:
    """(one-liner, source). book_dna first, then the config table, then what is known."""
    b = book or {}
    for k in ("mechanism", "thesis", "description"):
        if isinstance(b.get(k), str) and b[k].strip():
            return b[k].strip(), f"book_dna.{k}"
    table = dict(_cfg("RESULTS_VOICE_MECHANISMS", {}))
    for key in sorted(table, key=lambda x: (-len(x), x)):
        if account.startswith(key) or f"[{key}]" in account:
            return str(table[key]), f"config.RESULTS_VOICE_MECHANISMS[{key!r}]"
    if family == "night_books":
        m = _HASH_RE.search(account)
        return (account[:m.start()].strip() if m else account), "the night book's own name"
    if b.get("rule"):
        return f"rule {b['rule']} (no one-line description recorded)", "book_dna.rule"
    return "mechanism not recorded in book_dna or config", "none"


def jaccard(a: frozenset, b: frozenset) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def cluster_bets(accounts: list[str], tickers: dict[str, frozenset], thr: float) -> dict:
    """Exact-set groups AND Jaccard >= thr connected components (deterministic)."""
    known = [a for a in accounts if tickers.get(a)]
    exact: dict[frozenset, list[str]] = {}
    for a in known:
        exact.setdefault(tickers[a], []).append(a)
    exact_groups = sorted((sorted(v) for v in exact.values() if len(v) > 1), key=lambda g: g[0])
    parent = {a: a for a in accounts}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    edges = []
    for i, a in enumerate(known):
        for b in known[i + 1:]:
            j = jaccard(tickers[a], tickers[b])
            if j >= thr:
                edges.append({"a": a, "b": b, "jaccard": round(j, 3)})
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    comps: dict[str, list[str]] = {}
    for a in accounts:
        comps.setdefault(find(a), []).append(a)
    bet_of = {}
    for root, members in comps.items():
        for m in members:
            bet_of[m] = sorted(members)
    return {"exact_groups": exact_groups, "jaccard_edges": edges, "bet_of": bet_of,
            "n_bets": len(comps), "n_holdings_unknown": len([a for a in accounts if not tickers.get(a)])}


# ───────────────────────────────────────────────────────────── what raises a label

def raise_path(book: Optional[dict], vs_spy_pp: Optional[float], p_dna: dict) -> dict:
    """The next rung on book_dna's ladder and exactly what is missing, from book_dna's
    OWN rule (`book_dna.evidence_label`): EARLY_EVIDENCE = >= early_min_sessions,
    excess > 0, sub-windows OK with >= 2 of 3 positive; REPLICATED = that AND a fair
    twin beaten or a frozen replication; VALIDATED_EDGE = a validator on unseen data."""
    b = book or {}
    ev = b.get("evidence") or {}
    label = str(ev.get("label") or "UNLABELLED")
    rung = label.split("(")[0]
    early = int(p_dna.get("early_min_sessions") or _cfg("BOOK_DNA_EARLY_MIN_SESSIONS", 21))
    n = int(b.get("sessions_graded") or 0)
    sub = b.get("subwindows") or {}
    blockers: list[str] = []
    out: dict = {"label": label, "rung": rung, "label_why": ev.get("why")}
    if rung in ("OBSERVED", "UNLABELLED"):
        need = max(0, early - n)
        out.update(next_label="EARLY_EVIDENCE", sessions_needed=need, early_min_sessions=early)
        holding: list[str] = []
        if need:
            blockers.append(f"{need} more session(s) ({n} of {early})")
        if (vs_spy_pp or 0) <= 0:
            blockers.append("excess vs SPY must be > 0 (now "
                            f"{'n/a' if vs_spy_pp is None else f'{vs_spy_pp:+.2f} pp'})")
        else:
            holding.append(f"excess stays > 0 (now {vs_spy_pp:+.2f} pp)")
        if sub.get("status") != "OK":
            blockers.append(f"sub-windows not computable: {str(sub.get('why') or ev.get('why') or '')[:140]}")
        elif int(sub.get("n_positive") or 0) < 2:
            blockers.append(f"only {sub.get('n_positive')} of 3 sub-windows positive (needs 2)")
        else:
            holding.append(f">= 2 of 3 sub-windows stay positive (now {sub.get('n_positive')} of 3)")
        out["must_hold"] = holding
        out["subwindows_positive"] = sub.get("n_positive") if sub.get("status") == "OK" else None
    elif rung == "EARLY_EVIDENCE":
        out.update(next_label="REPLICATED", sessions_needed=0)
        blockers.append("beat its fair twin (excess over the twin > 0) or a frozen replication qualifying")
    elif rung == "REPLICATED":
        out.update(next_label="VALIDATED_EDGE", sessions_needed=None)
        blockers.append("a validator run on data the idea never saw (not awarded by book_dna)")
    else:
        out.update(next_label=None, sessions_needed=None)
    out.setdefault("must_hold", [])
    out["blockers"] = blockers
    out["line"] = (("; ".join(blockers) if blockers else "every condition met on this receipt")
                   + (f", if {' and '.join(out['must_hold'])}" if out["must_hold"] else ""))
    return out


def twin_of(account_set: list[str], books: dict[str, dict], parent: dict, kinds: list[str],
            rep: str) -> Optional[dict]:
    """The leader's random twin: book_dna's fair-twin kind first, then `kinds` order;
    the representative's own twins before a cluster member's."""
    pref = ((parent.get("fair_twin") or {}).get("kind"))
    order = ([pref] if pref else []) + [k for k in kinds if k != pref]
    for who in [rep] + [a for a in account_set if a != rep]:
        tw = [b for b in books.values() if b.get("twin_of") == who]
        for k in order:
            hit = sorted((t for t in tw if t.get("twin_kind") == k), key=lambda t: str(t.get("account")))
            if hit:
                t = hit[0]
                pb = books.get(who) or {}
                gap = (None if t.get("return_pct") is None or pb.get("return_pct") is None
                       else round(float(pb["return_pct"]) - float(t["return_pct"]), 3))
                return {"account": t.get("account"), "kind": k, "twin_of": who,
                        "return_pct": t.get("return_pct"), "vs_spy_pp": t.get("excess_pp"),
                        "gap_pp": gap,
                        "book_dna_excess_over_fair_twin_pp": (pb.get("fair_twin") or {}).get("excess_over_twin_pp")}
    return None


# ───────────────────────────────────────────────────────────── build

def _r(x: Any, nd: int = 3) -> Optional[float]:
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def build(roi: Optional[dict], dna: Optional[dict], *, roi_path: str, dna_path: str) -> dict:
    if not isinstance(roi, dict) or not roi.get("rows"):
        raise ResultsVoiceRefused("the ROI receipt is missing or has no rows")
    if not isinstance(dna, dict) or not isinstance(dna.get("books"), list):
        raise ResultsVoiceRefused("the book_dna receipt is missing or has no books")
    P = params()
    p_dna = dna.get("params") or {}
    receipts = [roi_path, dna_path]
    books = {str(b.get("account")): b for b in dna["books"]}

    strategy, excluded = [], []
    for r in roi["rows"]:
        a = str(r.get("account"))
        if r.get("status") != "LIVE" or r.get("vs_spy_pp") is None:
            continue
        why = control_reason(a, books.get(a), P["control_name_markers"])
        if why:
            excluded.append({"account": a, "why": why})
        else:
            strategy.append(r)
    if not strategy:
        raise ResultsVoiceRefused("no LIVE strategy account with a vs-SPY number in the ROI receipt")
    strategy.sort(key=lambda r: (-float(r["vs_spy_pp"]), str(r["account"])))
    accounts = [str(r["account"]) for r in strategy]
    by_acc = {str(r["account"]): r for r in strategy}
    marks = sorted({str(r.get("last_mark")) for r in strategy if r.get("last_mark")})
    as_of = marks[-1] if marks else None
    n_ahead = sum(1 for r in strategy if float(r["vs_spy_pp"]) > 0)

    tickers = {a: frozenset((books.get(a) or {}).get("tickers") or []) for a in accounts}
    cl = cluster_bets(accounts, tickers, P["bet_jaccard"])
    bet_ahead = {tuple(cl["bet_of"][a]) for a in accounts if float(by_acc[a]["vs_spy_pp"]) > 0}

    fams: dict[str, list[float]] = {}
    for r in strategy:
        fams.setdefault(str(r.get("family")), []).append(float(r["vs_spy_pp"]))
    families = [{"family": f, "accounts": len(v), "ahead": sum(1 for x in v if x > 0),
                 "median_vs_spy_pp": round(statistics.median(v), 3)}
                for f, v in sorted(fams.items(), key=lambda kv: (-statistics.median(kv[1]), kv[0]))]

    def row_view(a: str) -> dict:
        r, b = by_acc[a], books.get(a) or {}
        return {"account": a, "family": r.get("family"), "roi_pct": _r(r.get("roi_pct")),
                "spy_same_window_pct": _r(r.get("spy_same_window_pct")), "vs_spy_pp": _r(r.get("vs_spy_pp")),
                "inception": r.get("inception"), "last_mark": r.get("last_mark"),
                "sessions_graded": b.get("sessions_graded"),
                "evidence_label": (b.get("evidence") or {}).get("label"),
                "evidence_why": (b.get("evidence") or {}).get("why")}

    leaders, seen = [], set()
    for a in accounts:
        bet = tuple(cl["bet_of"][a])
        if bet in seen:
            continue
        seen.add(bet)
        b = books.get(a) or {}
        mech, msrc = mechanism(a, b, by_acc[a].get("family"))
        tw = twin_of(list(bet), books, b, P["random_twin_kinds"], a)
        exact = next((g for g in cl["exact_groups"] if a in g), [a])
        leaders.append({**row_view(a), "rank": len(leaders) + 1, "bet_members": list(bet),
                        "same_names_as": [m for m in exact if m != a],
                        "mechanism": mech, "mechanism_source": msrc,
                        "random_twin": tw,
                        "twin_line": (f"random twin {tw['account']} ({tw['kind']}) {tw['return_pct']:+.2f}%: "
                                      f"leader ahead of it by {tw['gap_pp']:+.2f} pp"
                                      if tw and tw.get("gap_pp") is not None and tw.get("return_pct") is not None
                                      else "no random twin seeded for this bet: the twin gap is NOT_COMPUTABLE"),
                        "raise": raise_path(b, by_acc[a].get("vs_spy_pp"), p_dna),
                        "receipts": receipts})
        if len(leaders) >= P["n_leaders"]:
            break

    losers = []
    for a in sorted(accounts, key=lambda x: (float(by_acc[x]["vs_spy_pp"]), x))[:P["n_losers"]]:
        losers.append({**row_view(a), "bet_members": cl["bet_of"][a], "receipts": receipts})

    rungs = {}
    for a in accounts:
        rung = str(((books.get(a) or {}).get("evidence") or {}).get("label") or "UNLABELLED").split("(")[0]
        rungs[rung] = rungs.get(rung, 0) + 1
    ladder = list(_dna.LABEL_LADDER)
    above = sorted((x for x in rungs if x in ladder and ladder.index(x) > 0), key=ladder.index)
    top_rung = max((x for x in rungs if x in ladder), key=ladder.index, default="UNLABELLED")
    promoted = [{"account": a, "label": (books.get(a) or {}).get("evidence", {}).get("label")}
                for a in accounts
                if str(((books.get(a) or {}).get("evidence") or {}).get("label") or "").split("(")[0] in above]
    claims_line = ("CLAIMS PROMOTED: " + (
        ", ".join(f"{x['account']} {x['label']}" for x in promoted) if promoted else
        f"none -- the highest label any strategy account holds is {top_rung}; leaders are chosen after "
        f"the fact from {len(accounts)} accounts, so the top of the table is biased upward"))

    summ = dna.get("summary") or {}
    voice = {
        "schema": SCHEMA, "receipt": "results_voice", "licence": roi.get("licence") or "PRODUCT_EXPERIMENT",
        "run_id": roi.get("run_id") or dna.get("roi_receipt_run_id"),
        "roi_generated_utc": roi.get("generated_utc"), "book_dna_generated_utc": dna.get("generated_utc"),
        "receipts": receipts, "params": P,
        "headline": {"n_strategy_accounts": len(accounts), "n_ahead": n_ahead,
                     "n_behind": len(accounts) - n_ahead, "as_of_mark": as_of,
                     "older_marks": [m for m in marks if m != as_of],
                     "n_excluded_controls": len(excluded),
                     "n_distinct_bets": cl["n_bets"], "n_distinct_bets_ahead": len(bet_ahead),
                     "receipts": receipts},
        "families": families,
        "clusters": {"bet_jaccard": P["bet_jaccard"], "n_distinct_bets": cl["n_bets"],
                     "n_holdings_unknown": cl["n_holdings_unknown"],
                     "exact_same_names": cl["exact_groups"],
                     "jaccard_bets": sorted((m for m in {tuple(v) for v in cl["bet_of"].values()} if len(m) > 1),
                                            key=lambda g: g[0]),
                     "jaccard_edges": cl["jaccard_edges"],
                     "book_dna_context": {"jaccard_threshold": summ.get("jaccard_threshold"),
                                          "n_holdings_clusters_ahead": summ.get("n_holdings_clusters_ahead"),
                                          "effective_bets_exante": summ.get("effective_bets_exante"),
                                          "clusters_ge3": [{"n": c.get("n"), "members": c.get("members")}
                                                           for c in summ.get("clusters_ge3") or []]},
                     "receipts": receipts},
        "leaders": leaders,
        "losers": losers,
        "claims": {"labels_held": dict(sorted(rungs.items())), "claimable_above_observed": above,
                   "top_rung": top_rung, "promoted": promoted, "line": claims_line,
                   "ceiling_note": (f"book_dna awards at most {_dna.LABEL_CEILING}; VALIDATED_EDGE needs a "
                                    f"validator on data the idea never saw"),
                   "receipts": receipts},
        "excluded_controls": excluded,
    }
    voice["headline_lines"] = headline_lines(voice)
    return voice


# ───────────────────────────────────────────────────────────── voice

def _leader_short(x: dict) -> str:
    return (f"{short_name(x['account'], 48)} {x['vs_spy_pp']:+.2f} pp ({x['sessions_graded']} s, "
            f"{x['evidence_label']})")


def headline_lines(v: dict) -> list[str]:
    """The six lines a handoff, the morning report and the phone all open with."""
    h, L = v["headline"], v["leaders"]
    rid = v.get("run_id")
    lines = [f"RESULTS as of the {h['as_of_mark']} marks (run {rid}): {h['n_ahead']} of "
             f"{h['n_strategy_accounts']} strategy accounts are ahead of SPY, each over its own window; "
             f"they are {h['n_distinct_bets_ahead']} distinct bets ahead of {h['n_distinct_bets']} "
             f"(holdings Jaccard >= {v['params']['bet_jaccard']:g}; {h['n_excluded_controls']} controls/twins "
             f"excluded)."]
    if L:
        x = L[0]
        same = f" (with {', '.join(x['same_names_as'])}: same names)" if x["same_names_as"] else ""
        lines.append(f"LEADER {x['account']}{same}: {x['roi_pct']:+.2f}% vs SPY {x['spy_same_window_pct']:+.2f}% "
                     f"= {x['vs_spy_pp']:+.2f} pp, {x['inception']} -> {x['last_mark']}, "
                     f"{x['sessions_graded']} sessions, {x['evidence_label']}. {x['mechanism']}.")
        lines.append("NEXT: " + "; ".join(_leader_short(y) for y in L[1:4]) if len(L) > 1 else "NEXT: none")
        rz = x["raise"]
        lines.append(f"WHAT RAISES IT: {x['account']} -> {rz.get('next_label')}: {rz['line']}. "
                     f"{x['twin_line'][0].upper()}{x['twin_line'][1:]}.")
    else:
        lines += ["LEADER: none", "NEXT: none", "WHAT RAISES IT: n/a"]
    if v["losers"]:
        w = v["losers"][0]
        lines.append(f"BEHIND: {h['n_behind']} of {h['n_strategy_accounts']}; worst {short_name(w['account'], 48)} "
                     f"{w['vs_spy_pp']:+.2f} pp ({w['family']}, {w['inception']} -> {w['last_mark']}, "
                     f"{w['sessions_graded']} s).")
    else:
        lines.append(f"BEHIND: {h['n_behind']} of {h['n_strategy_accounts']}.")
    lines.append(v["claims"]["line"] + ".")
    return lines


def render_md(v: dict) -> str:
    rc = ", ".join(f"`{p}`" for p in v["receipts"])
    out = [f"# RESULTS VOICE {v['run_id']}", "",
           f"Licence {v['licence']}; paper books. Receipts: {rc}. Every number below is read from them.", ""]
    out += v["headline_lines"]
    out += ["", f"## Families (strategy accounts only) — receipts: {rc}", "",
            "| family | accounts | ahead of SPY | median vs SPY (pp) |", "|---|---:|---:|---:|"]
    out += [f"| {f['family']} | {f['accounts']} | {f['ahead']} | {f['median_vs_spy_pp']:+.2f} |" for f in v["families"]]
    out += ["", f"## Leaders: the top {len(v['leaders'])} DISTINCT bets — receipts: {rc}", "",
            "Chosen after the fact from the whole table; a leader over a few sessions is an observation, "
            "not a skill claim.", "",
            "| # | account (bet members) | return | SPY same window | vs SPY | window | sessions | label | random twin |",
            "|---:|---|---:|---:|---:|---|---:|---|---|"]
    for x in v["leaders"]:
        tw = x["random_twin"]
        twc = (f"{tw['return_pct']:+.2f}% ({tw['kind']}), gap {tw['gap_pp']:+.2f} pp"
               if tw and tw.get("gap_pp") is not None else "none seeded")
        mem = f" ({', '.join(m for m in x['bet_members'] if m != x['account'])})" if len(x["bet_members"]) > 1 else ""
        out.append(f"| {x['rank']} | {x['account']}{mem} | {x['roi_pct']:+.2f}% | {x['spy_same_window_pct']:+.2f}% | "
                   f"{x['vs_spy_pp']:+.2f} pp | {x['inception']} -> {x['last_mark']} | {x['sessions_graded']} | "
                   f"{x['evidence_label']} | {twc} |")
    out += ["", "Mechanisms:", ""]
    out += [f"- **{x['account']}** — {x['mechanism']} _(source: {x['mechanism_source']})_" for x in v["leaders"]]
    out += ["", f"## What would raise each leader's label — rule: `backend/services/book_dna.py` evidence_label; "
                f"receipts: {rc}", ""]
    for x in v["leaders"]:
        rz = x["raise"]
        out.append(f"- **{x['account']}** {rz['label']} -> {rz.get('next_label')}: {rz['line']}. "
                   f"{x['twin_line'][0].upper()}{x['twin_line'][1:]}.")
    out += ["", f"## Behind SPY: the worst {len(v['losers'])}, named with the same honesty — receipts: {rc}", "",
            "| account | family | return | SPY same window | vs SPY | window | sessions | label |",
            "|---|---|---:|---:|---:|---|---:|---|"]
    for x in v["losers"]:
        out.append(f"| {x['account']} | {x['family']} | {x['roi_pct']:+.2f}% | {x['spy_same_window_pct']:+.2f}% | "
                   f"{x['vs_spy_pp']:+.2f} pp | {x['inception']} -> {x['last_mark']} | {x['sessions_graded']} | "
                   f"{x['evidence_label']} |")
    c = v["clusters"]
    out += ["", f"## Clusters: accounts that are one bet — receipts: {rc}", "",
            f"- exact same ticker set: {c['exact_same_names'] or 'none'}",
            f"- holdings Jaccard >= {c['bet_jaccard']:g}: {c['jaccard_bets'] or 'none'}",
            f"- {c['n_holdings_unknown']} account(s) carry no holdings in book_dna and count as their own bet",
            f"- book_dna context (Jaccard {c['book_dna_context']['jaccard_threshold']}): "
            f"{c['book_dna_context']['n_holdings_clusters_ahead']} holdings clusters ahead; ex-ante effective bets "
            f"{c['book_dna_context']['effective_bets_exante']}"]
    cl = v["claims"]
    out += ["", f"## Claims — receipts: {rc}", "", f"- {cl['line']}.",
            f"- labels held by strategy accounts: {cl['labels_held']}", f"- {cl['ceiling_note']}.", ""]
    return "\n".join(out)


def write(v: dict, out_dir: Path, run_id: str) -> tuple[Path, Path]:
    """Deterministic output named by the INPUT run id: a rerun over the same immutable
    pair writes the same bytes, so replacing it loses nothing."""
    out_dir = Path(out_dir)
    jp, mp = out_dir / f"results_voice_{run_id}.json", out_dir / f"results_voice_{run_id}.md"
    for p, text in ((jp, json.dumps(v, indent=1, sort_keys=False, default=str)), (mp, render_md(v))):
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        if tmp.read_text(encoding="utf-8") != text:
            tmp.unlink(missing_ok=True)
            raise ResultsVoiceRefused(f"write verification failed for {rel(p)}")
        tmp.replace(p)
    return jp, mp


def run(run_id: Optional[str] = None, folder: Path = PA_DIR, *, write_files: bool = True) -> dict:
    folder = Path(folder)
    rid = run_id or newest_shared_run_id(folder)
    roi, dna, rp, dp = load_pair(rid, folder)
    v = build(roi, dna, roi_path=rel(rp), dna_path=rel(dp))
    v["run_id"] = rid
    v["headline_lines"] = headline_lines(v)
    if write_files:
        jp, mp = write(v, folder, rid)
        return {"status": "ok", "run_id": rid, "json": rel(jp), "md": rel(mp), "voice": v}
    return {"status": "ok", "run_id": rid, "voice": v}


def safe_run(run_id: Optional[str] = None, folder: Path = PA_DIR) -> dict:
    """For schedulers: never raises. {'status': 'ok', 'json', 'md', 'headline_lines'} or
    {'status': 'skip', 'line': 'SKIP results_voice: <why>'} -- a failed results statement
    must not cost the pass that produced the receipts."""
    try:
        out = run(run_id, folder)
    except Exception as exc:                                       # noqa: BLE001 -- reported, never raised
        return {"status": "skip", "line": f"SKIP results_voice: {type(exc).__name__}: {str(exc)[:240]}"}
    return {"status": "ok", "run_id": out["run_id"], "json": out["json"], "md": out["md"],
            "headline_lines": out["voice"]["headline_lines"],
            "line": f"results_voice {out['run_id']}: {out['voice']['headline_lines'][0][:200]}"}


def public_view(v: dict, is_personal) -> dict:
    """The /arena section: flat, scalar leaves only (the sanitiser's allow-list is
    `legibility_sanitise.RESULTS_VOICE`), owner-personal books dropped from every list
    and every headline line that names one. No dollars exist in `v` to begin with."""
    fam_of = {x["account"]: x.get("family") for x in v.get("leaders", []) + v.get("losers", [])}

    def personal(a: Any) -> bool:
        return bool(is_personal(a, fam_of.get(a)))
    personal_names = [a for a in fam_of if personal(a)]
    h = v["headline"]
    lines = [ln for ln in v.get("headline_lines") or [] if not any(n in ln for n in personal_names)]
    leaders = []
    for x in v.get("leaders") or []:
        if personal(x["account"]):
            continue
        tw, rz = x.get("random_twin") or {}, x.get("raise") or {}
        leaders.append({k: x.get(k) for k in ("rank", "account", "family", "roi_pct", "spy_same_window_pct",
                                              "vs_spy_pp", "inception", "last_mark", "sessions_graded",
                                              "evidence_label", "mechanism", "twin_line")}
                       | {"bet_members": [m for m in x.get("bet_members") or [] if not is_personal(m, None)],
                          "twin_kind": tw.get("kind"), "twin_return_pct": tw.get("return_pct"),
                          "twin_gap_pp": tw.get("gap_pp"), "next_label": rz.get("next_label"),
                          "sessions_needed": rz.get("sessions_needed"), "raise_line": rz.get("line")})
    losers = [{k: x.get(k) for k in ("account", "family", "roi_pct", "spy_same_window_pct", "vs_spy_pp",
                                     "inception", "last_mark", "sessions_graded", "evidence_label")}
              for x in v.get("losers") or [] if not personal(x["account"])]
    c, cl = v.get("clusters") or {}, v.get("claims") or {}
    return {
        "run_id": v.get("run_id"), "as_of_mark": h.get("as_of_mark"),
        "n_strategy_accounts": h.get("n_strategy_accounts"), "n_ahead": h.get("n_ahead"),
        "n_behind": h.get("n_behind"), "n_distinct_bets": h.get("n_distinct_bets"),
        "n_distinct_bets_ahead": h.get("n_distinct_bets_ahead"), "n_excluded_controls": h.get("n_excluded_controls"),
        "bet_jaccard": c.get("bet_jaccard"),
        "headline_lines": lines, "n_headline_lines_dropped_owner_personal": len(v.get("headline_lines") or []) - len(lines),
        "families": [f for f in v.get("families") or [] if not is_personal("", f.get("family"))],
        "leaders": leaders, "losers": losers,
        "same_names_groups": [" = ".join(m for m in g if not is_personal(m, None))
                              for g in c.get("exact_same_names") or []],
        "one_bet_groups": [" ~ ".join(m for m in g if not is_personal(m, None)) for g in c.get("jaccard_bets") or []],
        "claims_line": cl.get("line"), "claimable_above_observed": cl.get("claimable_above_observed"),
        "top_rung": cl.get("top_rung"), "ceiling_note": cl.get("ceiling_note"),
        "receipt_files": v.get("receipts"),
    }


# ───────────────────────────────────────────────────────────── readers for the surfaces

def newest_voice_path(folder: Path = PA_DIR, suffix: str = ".md") -> Optional[Path]:
    """The newest results_voice_<run>{suffix} by run id (never by mtime)."""
    ids = []
    for p in Path(folder).glob(f"results_voice_*{suffix}"):
        rid = p.name[len("results_voice_"):-len(suffix)]
        if RUN_ID_RE.match(rid):
            ids.append(rid)
    return (Path(folder) / f"results_voice_{max(ids)}{suffix}") if ids else None


def headline_block(folder: Path = PA_DIR, n: int = 6) -> tuple[Optional[Path], list[str]]:
    """The first `n` headline lines of the newest .md (the lines after its preamble)."""
    p = newest_voice_path(folder, ".md")
    if p is None:
        return None, []
    lines = p.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if ln.startswith(("RESULTS ", "LEADER", "NEXT:", "WHAT RAISES IT:", "BEHIND:",
                                                 "CLAIMS PROMOTED:"))]
    return p, body[:n]


__all__ = ["SCHEMA", "ResultsVoiceRefused", "build", "cluster_bets", "control_reason", "headline_block",
           "headline_lines", "load_pair", "mechanism", "newest_shared_run_id", "newest_voice_path", "params", "public_view",
           "raise_path", "render_md", "run", "safe_run", "write"]
