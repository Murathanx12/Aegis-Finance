"""hyp_lab: a hypothesis ledger that learns.

Each hypothesis is a TYPED row: mechanism, the observable precursor known beforehand, what would
separate it from ordinary factor beta, the observation that would refute it, the data it needs,
a test design with a declared split, a status, a verdict and receipts. The ledger is an
append-only event log (`ledger.jsonl`): a hypothesis row, then update rows (declared, run,
verdict). State is the fold of that log, so nothing is ever rewritten.

The loop, once a night (scripts/hyp_lab.py nightly, after the nn_lab nightly):
  1. read the ledger and the verdicts so far (the families' track records);
  2. GENERATE new hypotheses with DeepSeek and the local model, each shown the past verdicts;
     any row that cannot state a refuting observation or a precursor is DISCARDED;
  3. DEDUPE against docs/TRIALS, the closed LLM list and the ledger itself;
  4. RANK by EV = P(changes the roadmap) x value - cost, where P learns from verdicts;
  5. DECLARE the top few runnable cells in a receipt (sha256) BEFORE running them;
  6. RUN them (backend/services/hyp_cells.py) and write the verdicts back.

Licence PRODUCT_EXPERIMENT. No LLM authority over capital; nothing here trades.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from backend import config as C

REPO = Path(__file__).resolve().parents[2]
HYP_DIR = C.DATA_DIR / "optimus" / "hyp_lab"
LEDGER = HYP_DIR / "ledger.jsonl"
RECEIPTS = HYP_DIR / "receipts"
STOP = HYP_DIR / "STOP"
TRIALS_DIR = REPO / "docs" / "TRIALS"
CLOSED_DOCS = [REPO / "docs" / "WHAT_WE_ALREADY_KNOW_LLM.md", REPO / "docs" / "NEGATIVE_RESULTS.md"]

REQUIRED = ("title", "mechanism", "precursor", "separation_from_beta", "refutation", "target")
TARGETS = ("size", "direction", "return", "co_movement", "llm_capability", "data")
STATUSES = ("PROPOSED", "DISCARDED_NO_REFUTATION", "DUPLICATE_OF_CLOSED", "DUPLICATE_IN_LEDGER",
            "NEEDS_CELL", "DECLARED", "RUN", "SPENT", "DEFERRED_FAMILY_BUDGET")
#: CANDIDATE (2026-10-06, the theory cells' word for a positive) counts as a positive exactly
#: like CONDITIONAL_POSITIVE in the family posterior.
VERDICTS = ("CONDITIONAL_POSITIVE", "CANDIDATE", "FAILED_VARIANT", "CANNOT_DISTINGUISH", "REFUSED",
            "MECHANISM_REJECTED", "RETIRED_FROM_CURRENT_SEARCH")
POSITIVE_VERDICTS = ("CONDITIONAL_POSITIVE", "CANDIDATE")

#: value points of a decisive answer, by what it would change (a return edge changes the most)
VALUE = {"return": 10.0, "co_movement": 6.0, "size": 4.0, "direction": 3.0, "llm_capability": 3.0, "data": 2.0}
#: what each runnable cell actually measures: its value comes from THAT, not from the target a
#: generator claimed (a size test does not earn a return edge's value)
CELL_TARGET = {"macro_lead_lag": "return", "event_readthrough": "co_movement", "size_feature_increment": "size"}
#: prior P(conditional positive) per family before any verdict: Beta(a, b)
FAMILY_PRIOR = (1.0, 4.0)
DEDUP_CLOSED = 0.09        # cosine to a closed item at/above this = duplicate (calibrated 2026-09-29: four known duplicates 0.10-0.32, unrelated rows 0.02-0.06)
DEDUP_LEDGER = 0.70        # cosine to an existing ledger row at/above this = duplicate


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower()).split())


def hyp_id(mechanism: str, precursor: str, params: dict | None = None) -> str:
    """Stable id from the mechanism, the precursor and the cell parameters (a new parameter set
    is a new hypothesis row: it gets its own verdict and counts as its own look)."""
    key = _norm(mechanism) + "|" + _norm(precursor) + "|" + json.dumps(params or {}, sort_keys=True)
    return "H-" + hashlib.sha1(key.encode()).hexdigest()[:10]


def make_hypothesis(*, title: str, mechanism: str, precursor: str, separation_from_beta: str,
                    refutation: str, target: str, family: str, source: str, source_ref: str = "",
                    data_needed: list[str] | None = None, cell_type: str | None = None,
                    params: dict | None = None, split: dict | None = None,
                    negative_informative: bool = False, cost_usd: float = 0.0, cpu_min: float = 5.0,
                    gpu_min: float = 0.0, expected_power: float = 0.5, notes: str = "") -> dict:
    """A typed hypothesis row. A row without a refuting observation or a precursor is returned
    with status DISCARDED_NO_REFUTATION (kept in the ledger, so the discard is itself counted)."""
    row = {"kind": "hypothesis", "title": title.strip(), "mechanism": mechanism.strip(),
           "precursor": (precursor or "").strip(), "separation_from_beta": (separation_from_beta or "").strip(),
           "refutation": (refutation or "").strip(), "target": target, "family": family,
           "source": source, "source_ref": source_ref, "data_needed": list(data_needed or []),
           "cell_type": cell_type, "params": params or {}, "split": split or {},
           "negative_informative": bool(negative_informative), "cost_usd": float(cost_usd),
           "cpu_min": float(cpu_min), "gpu_min": float(gpu_min),
           "expected_power": float(max(0.0, min(1.0, expected_power))), "notes": notes,
           "created_utc": now_utc()}
    if target not in TARGETS:
        raise ValueError(f"target {target!r} not in {TARGETS}")
    row["hyp_id"] = hyp_id(mechanism, precursor, params)
    too_short = lambda s: len(_norm(s)) < 12  # noqa: E731
    if too_short(row["refutation"]) or too_short(row["precursor"]):
        row["status"] = "DISCARDED_NO_REFUTATION"
    elif cell_type is None:
        row["status"] = "NEEDS_CELL"
    else:
        row["status"] = "PROPOSED"
    row["sha256"] = hashlib.sha256(json.dumps({k: v for k, v in row.items() if k != "created_utc"},
                                              sort_keys=True, default=str).encode()).hexdigest()
    return row


# ------------------------------------------------------------------ the log
def append(rows: list[dict], path: Path | None = None) -> int:
    path = path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    return len(rows)


#: fields an update row may set on a hypothesis (append-only annotations; review 2026-10-06 F8)
ANNOTATION_FIELDS = ("reread_of", "family_label", "powered")


def update(hid: str, *, status: str | None = None, verdict: str | None = None, receipt: str | None = None,
           summary: dict | None = None, path: Path | None = None, fields: dict | None = None) -> dict:
    if status is not None and status not in STATUSES:
        raise ValueError(f"status {status!r}")
    if verdict is not None and verdict not in VERDICTS:
        raise ValueError(f"verdict {verdict!r}")
    bad = set(fields or {}) - set(ANNOTATION_FIELDS)
    if bad:
        raise ValueError(f"fields {sorted(bad)} not in {ANNOTATION_FIELDS}")
    ev = {"kind": "update", "hyp_id": hid, "status": status, "verdict": verdict, "receipt": receipt,
          "summary": summary or {}, "utc": now_utc()}
    if fields:
        ev["fields"] = dict(fields)
    append([ev], path)
    return ev


def load_state(path: Path | None = None) -> dict[str, dict]:
    """Fold the log: the first hypothesis row per id wins; updates apply in order."""
    path = path or LEDGER
    state: dict[str, dict] = {}
    if not path.exists():
        return state
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") == "hypothesis":
                if r["hyp_id"] not in state:
                    state[r["hyp_id"]] = {**r, "history": []}
            elif r.get("kind") == "update" and r.get("hyp_id") in state:
                s = state[r["hyp_id"]]
                if r.get("status"):
                    s["status"] = r["status"]
                if r.get("verdict"):
                    s["verdict"] = r["verdict"]
                if r.get("receipt"):
                    s.setdefault("receipts", []).append(r["receipt"])
                if r.get("summary"):
                    s["last_summary"] = r["summary"]
                for k, v in (r.get("fields") or {}).items():
                    if k in ANNOTATION_FIELDS:
                        s[k] = v
                s["history"].append({k: r.get(k) for k in ("status", "verdict", "utc")})
    return state


# ------------------------------------------------------------------ dedupe
def closed_corpus() -> list[dict]:
    """What has been tested or registered already: every docs/TRIALS file (title + first 1,500
    chars), every row of the closed-LLM table, every heading of NEGATIVE_RESULTS.md."""
    items = []
    if TRIALS_DIR.exists():
        for p in sorted(TRIALS_DIR.glob("*.md")):
            t = p.read_text(encoding="utf-8", errors="replace")
            items.append({"ref": f"docs/TRIALS/{p.name}", "text": p.stem.replace("-", " ") + " " + t[:600]})
    for p in CLOSED_DOCS:
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(t.splitlines()):
            if line.startswith("|") and line.count("|") > 4 and "---" not in line:
                items.append({"ref": f"{p.relative_to(REPO).as_posix()}:{i + 1}", "text": line})
            elif line.startswith("#"):
                items.append({"ref": f"{p.relative_to(REPO).as_posix()}:{i + 1}", "text": line})
    # review 2026-10-06 F8: the library rules already run on CRSP are closed items too
    for name, ref in library_rules().items():
        items.append({"ref": ref, "text": name.replace("_", " ") + " " + name})
    return items


LIBRARY_RULE_GLOB = "library_rules_*.jsonl"


def library_rules(rebuild_dir: Path | None = None) -> dict[str, str]:
    """{rule name: 'receipt path#rule'} for every library rule already RUN on CRSP. A hypothesis
    that names one of these is a RE-READ (review 2026-10-06 F8: `hi52` was declared as new while
    LIB_2026-09-29T0802Z had run it). Plain-word rule names (no '_' and no digit, e.g. 'roe') are
    left to the cosine check: matching them as tokens would flag ordinary prose."""
    d = rebuild_dir or (C.DATA_DIR / "optimus" / "crsp_rebuild")
    out: dict[str, str] = {}
    for f in sorted(d.glob(LIBRARY_RULE_GLOB)) if d.exists() else []:
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    name = str(r.get("rule") or "")
                    if r.get("status") == "RUN" and name and ("_" in name or any(c.isdigit() for c in name)):
                        out.setdefault(name.lower(), f"{_rel(f)}#{name}")
        except OSError:
            continue
    return out


def reread_of(h: dict, rules: dict[str, str] | None = None) -> str | None:
    """The library receipt this hypothesis re-reads (an exact rule-name token in its text), or None."""
    rules = library_rules() if rules is None else rules
    toks = set(re.findall(r"[a-z0-9_]+", hyp_text(h).lower()))
    for tok in sorted(toks):
        if tok in rules:
            return rules[tok]
    return None


def hyp_text(h: dict) -> str:
    return " ".join(str(h.get(k, "")) for k in ("title", "mechanism", "precursor"))


def dedupe(new: list[dict], state: dict[str, dict], corpus: list[dict] | None = None,
           rules: dict[str, str] | None = None) -> list[dict]:
    """Mark each PROPOSED/NEEDS_CELL row that is too close to a closed item or an existing ledger
    row. The nearest match and its cosine ride on the row either way. A row naming a library
    rule already run on CRSP carries `reread_of` and counts +0 in its family's posterior; unless
    it was DECLARED as a re-read (`declared_reread`), it is also a DUPLICATE_OF_CLOSED."""
    rules = library_rules() if rules is None else rules
    from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
    from sklearn.metrics.pairwise import cosine_similarity  # noqa: PLC0415
    corpus = closed_corpus() if corpus is None else corpus
    led = [h for h in state.values() if h.get("status") not in ("DISCARDED_NO_REFUTATION",)]
    docs = [c["text"] for c in corpus] + [hyp_text(h) for h in led] + [hyp_text(h) for h in new]
    if not new:
        return new
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, stop_words="english").fit(docs)
    Xn = vec.transform([hyp_text(h) for h in new])
    Xc = vec.transform([c["text"] for c in corpus]) if corpus else None
    Xl = vec.transform([hyp_text(h) for h in led]) if led else None
    out = []
    seen_sigs = {params_signature(h) for h in led} - {None}
    for i, h in enumerate(new):
        h = dict(h)
        best_c = (0.0, None)
        if Xc is not None:
            s = cosine_similarity(Xn[i], Xc).ravel()
            j = int(s.argmax())
            best_c = (float(s[j]), corpus[j]["ref"])
        best_l = (0.0, None)
        if Xl is not None:
            s = cosine_similarity(Xn[i], Xl).ravel()
            j = int(s.argmax())
            best_l = (float(s[j]), led[j]["hyp_id"])
        h["dedup"] = {"nearest_closed": best_c[1], "cos_closed": round(best_c[0], 3),
                      "nearest_ledger": best_l[1], "cos_ledger": round(best_l[0], 3)}
        sig = params_signature(h)
        ro = reread_of(h, rules)
        if ro:
            h["reread_of"] = ro
        if h.get("status") in ("PROPOSED", "NEEDS_CELL"):
            if ro and not h.get("declared_reread") and not h.get("resurrects"):
                h["status"] = "DUPLICATE_OF_CLOSED"
            elif h["hyp_id"] in state or (sig and sig in seen_sigs):
                h["status"] = "DUPLICATE_IN_LEDGER"
            elif h["hyp_id"] in state:
                h["status"] = "DUPLICATE_IN_LEDGER"
            elif best_l[0] >= DEDUP_LEDGER and not h.get("params"):
                h["status"] = "DUPLICATE_IN_LEDGER"
            elif best_c[0] >= DEDUP_CLOSED and not h.get("resurrects"):
                h["status"] = "DUPLICATE_OF_CLOSED"
        if sig and h.get("status") in ("PROPOSED",):
            seen_sigs.add(sig)
        out.append(h)
    return out


def params_signature(h: dict) -> str | None:
    """(cell type, params) as a string: two rows with the same signature are the same test."""
    if not h.get("cell_type"):
        return None
    return h["cell_type"] + "|" + json.dumps(h.get("params") or {}, sort_keys=True)


# ------------------------------------------------------------------ learning + ranking
def canonical_family(name: str | None) -> str:
    """The fixed taxonomy (config.HYP_LAB_FAMILIES): aliases fold known splits; any other
    free-text label is UNMAPPED, so a renamed family cannot buy a fresh quota."""
    f = (name or "").strip()
    f = C.HYP_LAB_FAMILY_ALIASES.get(f, f)
    return f if f in C.HYP_LAB_FAMILIES else C.HYP_LAB_UNMAPPED_FAMILY


def is_powered(h: dict) -> bool:
    """Was this negative verdict POWERED (could the cell have seen the effect worth having)?
    Explicit `powered` (on the row or its summary) wins. Otherwise, from the summary: the confirm
    mean is significantly the wrong way (t <= -2), or the confirm MDE is no larger than a
    positive design effect. Unknown counts as NOT powered: silence is not evidence."""
    s = h.get("last_summary") or {}
    for v in (h.get("powered"), s.get("powered")):
        if isinstance(v, bool):
            return v
    c, d = s.get("confirm") or {}, s.get("design") or {}
    ct, cmde, dm = c.get("t"), c.get("mde"), d.get("mean")
    if ct is not None and float(ct) <= -2.0:
        return True
    if cmde is not None and dm is not None and float(dm) > 0 and float(cmde) <= float(dm):
        return True
    return False


def _verdict_utc(h: dict) -> datetime | None:
    for e in reversed(h.get("history") or []):
        if e.get("verdict") and e.get("utc"):
            try:
                return datetime.fromisoformat(str(e["utc"]))
            except ValueError:
                return None
    return None


def verdict_weight(h: dict, now: datetime | None = None) -> float:
    """1.0, or 0.5 once the verdict is older than HYP_LAB_VERDICT_DECAY_DAYS."""
    u = _verdict_utc(h)
    if u is None:
        return 1.0
    now = now or datetime.now(timezone.utc)
    if u.tzinfo is None:
        u = u.replace(tzinfo=timezone.utc)
    return 0.5 if (now - u).days > C.HYP_LAB_VERDICT_DECAY_DAYS else 1.0


def family_record(state: dict[str, dict], now: datetime | None = None) -> dict[str, dict]:
    """Per family (canonical): raw verdict counts, and the Beta posterior mean of P(positive)
    from EVIDENCE only (review 2026-10-06 F6/F8):
    * a positive (CONDITIONAL_POSITIVE / CANDIDATE) counts +1;
    * a FAILED_VARIANT counts +1 failure only when POWERED (`is_powered`); unpowered counts 0;
    * a CANNOT_DISTINGUISH counts 0 (it cannot see the effect: it is not a failure);
    * a re-read of a rule already run (`reread_of`) counts 0;
    * a verdict older than HYP_LAB_VERDICT_DECAY_DAYS counts half."""
    rec: dict[str, dict] = {}
    for h in state.values():
        f = canonical_family(h.get("family"))
        r = rec.setdefault(f, {"CONDITIONAL_POSITIVE": 0, "FAILED_VARIANT": 0, "CANNOT_DISTINGUISH": 0,
                               "REFUSED": 0, "n_rows": 0, "failed_powered": 0.0, "positive_weighted": 0.0,
                               "rereads": 0})
        r["n_rows"] += 1
        v = h.get("verdict")
        if not v:
            continue
        if v in POSITIVE_VERDICTS:
            r["CONDITIONAL_POSITIVE"] += 1
        elif v in r:
            r[v] += 1
        if h.get("reread_of"):
            r["rereads"] += 1
            continue
        w = verdict_weight(h, now)
        if v in POSITIVE_VERDICTS:
            r["positive_weighted"] += w
        elif v == "FAILED_VARIANT" and is_powered(h):
            r["failed_powered"] += w
    for f, r in rec.items():
        a = FAMILY_PRIOR[0] + r["positive_weighted"]
        b = FAMILY_PRIOR[1] + r["failed_powered"]
        r["p_positive"] = round(a / (a + b), 4)
    return rec


# ------------------------------------------------------------------ the posterior fed BACKWARD
# CHUNK C12 / owner decision D6 (2026-10-06), borrowed from RD-Agent(Q)'s bandit scheduler:
# the family posterior used to re-rank only what had already been generated; it now also
# decides how much of the NEXT generation round a family may take. A shrink, never a kill:
# the weight has a declared floor, every quota is >= 1, nothing is deleted or closed.
def family_weight(p_positive: float, floor: float | None = None, min_weight: float | None = None) -> float:
    """1.0 at/above the posterior floor; below it, proportionally less, never under min_weight."""
    floor = C.HYP_LAB_FAMILY_POSTERIOR_FLOOR if floor is None else float(floor)
    min_weight = C.HYP_LAB_FAMILY_MIN_WEIGHT if min_weight is None else float(min_weight)
    p = float(p_positive)
    if p >= floor:
        return 1.0
    return round(max(min_weight, p / floor), 4)


def family_budget(fam: dict[str, dict], n: int, quotas: dict[str, int] | None = None) -> dict[str, dict]:
    """Per family with a record: posterior, weight, and its quota of the next `n` generated
    hypotheses. Base quota = ceil(n x MAX_SHARE); a shrunk family gets floor(base x weight),
    never below 1. A taxonomy family with no record gets the base quota. UNMAPPED (free-text
    labels) always gets the MEDIAN quota of the mapped families, never a fresh full one.
    `quotas` (the policy_state preference `hyp_family_gen_quota`) overrides a computed quota."""
    base = max(1, math.ceil(n * C.HYP_LAB_FAMILY_MAX_SHARE))
    out: dict[str, dict] = {}
    for f, r in fam.items():
        w = family_weight(r.get("p_positive", FAMILY_PRIOR[0] / sum(FAMILY_PRIOR)))
        out[f] = {"p_positive": r.get("p_positive"), "weight": w,
                  "quota": max(1, int(math.floor(base * w + 1e-9))), "base_quota": base, "shrunk": w < 1.0}
    mapped = sorted(b["quota"] for f, b in out.items() if f != C.HYP_LAB_UNMAPPED_FAMILY)
    med = int(mapped[(len(mapped) - 1) // 2]) if mapped else base   # lower median: never rounds up
    um = out.get(C.HYP_LAB_UNMAPPED_FAMILY) or {"p_positive": None, "weight": 1.0, "base_quota": base, "shrunk": False}
    um["quota"] = max(1, min(int(um.get("quota", med)), med))
    um["unmapped_median_quota"] = med
    out[C.HYP_LAB_UNMAPPED_FAMILY] = um
    for f, q in (quotas or {}).items():
        if f in out:
            out[f]["quota"] = max(1, int(q))
            out[f]["quota_source"] = "policy_state"
    return out


def quotas_from_budget(budget: dict[str, dict]) -> dict[str, int]:
    """The policy_state generation preference: every family's quota (>= 1)."""
    return {f: int(b["quota"]) for f, b in sorted(budget.items())}


def policy_gen_quotas() -> dict[str, int]:
    """The generation quotas the night last wrote to policy_state (empty = none written)."""
    try:
        from backend.services import policy_state as PS  # noqa: PLC0415
        q = PS.load().get("hyp_family_gen_quota") or {}
        return {str(k): int(v) for k, v in q.items()}
    except Exception:  # noqa: BLE001 -- no preference: the computed quotas apply
        return {}


def ev_weights_from_budget(budget: dict[str, dict]) -> dict[str, float]:
    """The policy_state preference: only the shrunk families (absent = weight 1.0)."""
    return {f: b["weight"] for f, b in sorted(budget.items()) if b["weight"] < 1.0}


def policy_ev_weights() -> dict[str, float]:
    """The EV weights the night last wrote to policy_state (empty = no preference = 1.0)."""
    try:
        from backend.services import policy_state as PS  # noqa: PLC0415
        w = PS.load().get("hyp_family_ev_weight") or {}
        return {str(k): float(v) for k, v in w.items()}
    except Exception:  # noqa: BLE001 -- an unreadable preference ranks unshrunk (weight 1.0)
        return {}


def apply_family_budget(rows: list[dict], budget: dict[str, dict], n: int) -> list[dict]:
    """Rows from one generation round, in model order: once a family has used its quota, its
    further PROPOSED / NEEDS_CELL rows are DEFERRED_FAMILY_BUDGET (kept in the ledger, counted,
    re-admitted by rank() when the family's weight returns to 1.0). Nothing is dropped."""
    base = max(1, math.ceil(n * C.HYP_LAB_FAMILY_MAX_SHARE))
    used: dict[str, int] = {}
    out = []
    for h in rows:
        h = dict(h)
        f = canonical_family(h.get("family"))
        if h.get("status") in ("PROPOSED", "NEEDS_CELL"):
            quota = (budget.get(f) or {}).get("quota", base)
            if used.get(f, 0) >= quota:
                h["deferred_from_status"] = h["status"]
                h["status"] = "DEFERRED_FAMILY_BUDGET"
                h["deferred_reason"] = (f"family {f} used its quota {quota} of {n} this round "
                                        f"(posterior {(budget.get(f) or {}).get('p_positive')})")
            else:
                used[f] = used.get(f, 0) + 1
        out.append(h)
    return out


def family_policy_report(budget: dict[str, dict], generated: list[dict], ranked: list[dict]) -> dict[str, dict]:
    """Per family, what the receipt and LEDGER.md print: posterior, weight, quota,
    n_generated_tonight (admitted), n_deferred_tonight, n_shrunk (queue rows ranked at weight < 1)."""
    cf = canonical_family
    fams = set(budget) | {cf(h.get("family")) for h in generated} | {cf(h.get("family")) for h in ranked}
    out = {}
    for f in sorted(fams):
        b = budget.get(f) or {}
        out[f] = {"posterior": b.get("p_positive"), "weight": b.get("weight", 1.0), "quota": b.get("quota"),
                  "n_generated_tonight": sum(1 for h in generated if cf(h.get("family")) == f
                                             and h.get("status") in ("PROPOSED", "NEEDS_CELL")),
                  "n_deferred_tonight": sum(1 for h in generated if cf(h.get("family")) == f
                                            and h.get("status") == "DEFERRED_FAMILY_BUDGET"),
                  "n_shrunk": sum(1 for h in ranked if cf(h.get("family")) == f
                                  and (h.get("score") or {}).get("ev_weight", 1.0) < 1.0)}
    return out


def weekly_guarantee(state: dict[str, dict], weights: dict[str, float], now: datetime | None = None,
                     days: int | None = None) -> list[dict]:
    """Review 2026-10-06 F6: a shrunk family (weight < 1) whose last RUN is older than `days`
    (or never) gets its best runnable row -- PROPOSED or a DEFERRED row that was PROPOSED --
    guaranteed a slot tonight, so a family that is only hard to measure is still explored."""
    now = now or datetime.now(timezone.utc)
    days = C.HYP_LAB_SHRUNK_FAMILY_MIN_RUN_DAYS if days is None else days
    fam = family_record(state, now)
    out = []
    for f, w in sorted(weights.items()):
        if w >= 1.0:
            continue
        rows = [h for h in state.values() if canonical_family(h.get("family")) == f]
        last = None
        for h in rows:
            for e in h.get("history") or []:
                if e.get("status") == "RUN" and e.get("utc"):
                    try:
                        u = datetime.fromisoformat(str(e["utc"]))
                    except ValueError:
                        continue
                    u = u if u.tzinfo else u.replace(tzinfo=timezone.utc)
                    last = u if last is None or u > last else last
        if last is not None and (now - last).days < days:
            continue
        cands = [h for h in rows if h.get("cell_type") and (
            h.get("status") == "PROPOSED"
            or (h.get("status") == "DEFERRED_FAMILY_BUDGET" and h.get("deferred_from_status") == "PROPOSED"))]
        if not cands:
            continue
        best = max(cands, key=lambda h: score(h, fam, {})["ev"])
        out.append({**best, "status": "PROPOSED", "score": score(best, fam, weights),
                    "guaranteed": f"family {f} not run since {last.isoformat() if last else 'never'}"})
    return out


def score(h: dict, fam: dict[str, dict], ev_weights: dict[str, float] | None = None) -> dict:
    """EV = P(changes the roadmap) x value - cost.

    P(changes) = power x [P(positive) + (1 - P(positive)) x w_neg], where w_neg = 0.35 when a clean
    negative would close a live lead (negative_informative) else 0.10; P(positive) is the family's
    Beta posterior (it LEARNS from verdicts). value = VALUE[target] x novelty, novelty = 1 - the
    cosine to the nearest closed item. cost = LLM dollars + GPU minutes x 0.01 + CPU minutes x 0.002
    (points per dollar = 1)."""
    p_pos = fam.get(canonical_family(h.get("family")), {}).get("p_positive",
                                                             FAMILY_PRIOR[0] / sum(FAMILY_PRIOR))
    w_neg = 0.35 if h.get("negative_informative") else 0.10
    p_change = float(h.get("expected_power", 0.5)) * (p_pos + (1 - p_pos) * w_neg)
    novelty = 1.0 - float((h.get("dedup") or {}).get("cos_closed", 0.0))
    tgt = CELL_TARGET.get(h.get("cell_type") or "", h.get("target"))
    value = VALUE.get(tgt, 2.0) * max(0.1, novelty)
    cost = float(h.get("cost_usd", 0)) + 0.01 * float(h.get("gpu_min", 0)) + 0.002 * float(h.get("cpu_min", 0))
    # D6: the family's EV weight (a policy_state preference, floor > 0) shrinks the benefit, not the cost
    w = float((ev_weights or {}).get(canonical_family(h.get("family")), 1.0))
    return {"p_positive_family": round(p_pos, 4), "p_change": round(p_change, 4), "value": round(value, 3),
            "cost": round(cost, 4), "ev_weight": round(w, 4), "ev_unshrunk": round(p_change * value - cost, 4),
            "ev": round(w * p_change * value - cost, 4)}


def _effective_status(h: dict, fam: dict[str, dict]) -> str | None:
    """A DEFERRED_FAMILY_BUDGET row is re-admitted (as the status it had) once its family's
    posterior is back at/above the floor: a deferral, never a close."""
    s = h.get("status")
    if s == "DEFERRED_FAMILY_BUDGET":
        p = (fam.get(canonical_family(h.get("family"))) or {}).get("p_positive", FAMILY_PRIOR[0] / sum(FAMILY_PRIOR))
        if family_weight(p) >= 1.0:
            return h.get("deferred_from_status") or ("PROPOSED" if h.get("cell_type") else "NEEDS_CELL")
    return s


def rank(state: dict[str, dict], runnable_only: bool = False,
         ev_weights: dict[str, float] | None = None) -> list[dict]:
    """The queue by EV. `ev_weights` defaults to the policy_state preference the night wrote."""
    fam = family_record(state)
    ev_weights = policy_ev_weights() if ev_weights is None else ev_weights
    rows = []
    for h in state.values():
        st = _effective_status(h, fam)
        if st not in ("PROPOSED", "NEEDS_CELL"):
            continue
        if runnable_only and (st != "PROPOSED" or not h.get("cell_type")):
            continue
        rows.append({**h, "status": st, "score": score(h, fam, ev_weights)})
    return sorted(rows, key=lambda r: r["score"]["ev"], reverse=True)


# ------------------------------------------------------------------ declare + run
def declare(rows: list[dict], night: str, path: Path | None = None, notes: list[str] | None = None) -> dict:
    """Write the declaration receipt BEFORE any cell runs: the exact cell types, params, splits
    and verdict rule, with a sha256 over the content. Returns the receipt (with its path)."""
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    body = {"job": "hyp_lab.declare", "licence": "PRODUCT_EXPERIMENT", "night": night,
            "declared_utc": now_utc(),
            "verdict_rule": "hyp_cells.verdict: design fold fixes the sign; confirm fold decides. "
                            "CONDITIONAL_POSITIVE = confirm mean > 0, t >= 2, design mean > 0; "
                            "FAILED_VARIANT = confirm mean <= 0, or t < 2 with MDE <= effect worth having; "
                            "else CANNOT_DISTINGUISH. SE over date blocks, MDE = 2.8 SE.",
            "disclosures": list(notes or []),
            "cells": [{k: r.get(k) for k in ("hyp_id", "title", "family", "target", "cell_type", "params",
                                             "split", "refutation", "separation_from_beta")} for r in rows]}
    blob = json.dumps(body, sort_keys=True, default=str)
    body["sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = path or (RECEIPTS / f"declare_{stamp}.json")
    p.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
    for r in rows:
        update(r["hyp_id"], status="DECLARED", receipt=_rel(p))
    body["path"] = str(p)
    return body


def summarize_result(res: dict) -> dict:
    """The few numbers that the next generation prompt and the markdown view need."""
    out = {"verdict": res.get("verdict"), "reason": res.get("reason")}
    if isinstance(res.get("powered"), bool):
        out["powered"] = res["powered"]
    for role in ("design", "confirm"):
        d = res.get(role) or {}
        prim = None
        for k, v in d.items():
            if isinstance(v, dict) and "mean" in v and "t" in v and (k.startswith("primary") or k == "increment"):
                prim = v
                break
        if prim:
            out[role] = {k: prim.get(k) for k in ("mean", "t", "mde", "n", "n_blocks")}
    return out


def run_declared(rows: list[dict], night: str, runner=None, stop_file: Path | None = None,
                 before_each=None) -> list[dict]:
    """Run each declared cell; write its receipt and its verdict back into the ledger."""
    if runner is None:
        from backend.services import hyp_cells  # noqa: PLC0415
        runner = hyp_cells.run_cell
    stop_file = stop_file or STOP
    results = []
    for r in rows:
        if stop_file.exists():
            update(r["hyp_id"], status="DECLARED", summary={"note": "STOP file present; not run"})
            continue
        if before_each is not None:
            before_each(r)
        try:
            res = runner(r["cell_type"], r["params"])
        except Exception as e:  # noqa: BLE001  -- a crashed cell is a REFUSED verdict, recorded
            res = {"verdict": "REFUSED", "reason": f"{type(e).__name__}: {str(e)[:300]}"}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rp = RECEIPTS / f"cell_{r['hyp_id']}_{stamp}.json"
        RECEIPTS.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps({"hyp_id": r["hyp_id"], "title": r.get("title"), "night": night,
                                  "run_utc": now_utc(), "result": res}, indent=1, default=str), encoding="utf-8")
        v = res.get("verdict") if res.get("verdict") in VERDICTS else "REFUSED"
        summ = summarize_result(res)
        update(r["hyp_id"], status="RUN", verdict=v, receipt=_rel(rp), summary=summ)
        results.append({"hyp_id": r["hyp_id"], "title": r.get("title"), **summ, "receipt": str(rp)})
    return results


# ------------------------------------------------------------------ generation
GEN_SYSTEM = """You propose testable stock-market hypotheses for a research lab that has already killed many ideas.
Return ONLY a JSON array (no prose) of objects with exactly these keys:
"title" (<= 12 words), "mechanism" (why it would happen, 1-2 sentences), "precursor" (the observable, known BEFORE the trade, that triggers it),
"separation_from_beta" (what observation would separate it from ordinary market/sector/factor beta),
"refutation" (the specific observation in the test that would REFUTE it), "target" (one of "size","direction","return","co_movement"),
"family" (a short snake_case mechanism family), "cell_type" (one of the CELL TYPES below, or null if none fits), "params" (object for that cell type, or {}).
Rules: every hypothesis MUST have a concrete refutation; do not repeat any hypothesis in the PAST VERDICTS; prefer mechanisms whose precursor is public before the move; prefer READ-THROUGH and second-order effects; no bare 'the LLM predicts direction' ideas (closed)."""


def generation_prompt(state: dict[str, dict], cell_catalog: str, n: int = 8, max_past: int = 40,
                      budget: dict[str, dict] | None = None) -> str:
    fam = family_record(state)
    budget = family_budget(fam, n) if budget is None else budget
    past = []
    for h in list(state.values())[-max_past:]:
        if h.get("verdict") or h.get("status") in ("DUPLICATE_OF_CLOSED",):
            s = h.get("last_summary") or {}
            c = s.get("confirm") or {}
            past.append(f"- {h['title']} [{h.get('family')}] -> {h.get('verdict') or h.get('status')}"
                        + (f" (confirm mean {c.get('mean')}, t {c.get('t')})" if c else ""))
    famline = "; ".join(f"{k}: {v['CONDITIONAL_POSITIVE']}+/{v['FAILED_VARIANT']}-/{v['CANNOT_DISTINGUISH']}?"
                        for k, v in sorted(fam.items()))
    # Review 2026-10-06 F7: the prompt never names which families are shrunk or their caps (that
    # invites relabelling); it names the fixed taxonomy, and the quota is enforced after parsing.
    budline = ("\n\nFAMILY LABELS: \"family\" must be exactly one of: " + ", ".join(C.HYP_LAB_FAMILIES)
               + f". Any other label is filed as {C.HYP_LAB_UNMAPPED_FAMILY} and capped. Families whose "
               "cells keep failing get fewer slots per round; prefer mechanisms the track record has "
               "not yet refuted.")
    return (f"PAST VERDICTS (do not repeat; learn from them):\n" + ("\n".join(past) or "- none yet")
            + f"\n\nFAMILY TRACK RECORD (+positive/-failed/?cannot-distinguish): {famline or 'none'}"
            + budline
            + f"\n\nCELL TYPES (the lab can run these tonight without a human):\n{cell_catalog}"
            + f"\n\nPropose {n} NEW hypotheses. At least half must use a cell type with valid params.")


CELL_CATALOG = """1. macro_lead_lag params {"driver": "CL=F"|"^TNX"|"basket:SYM1,SYM2,...", "targets": [US tickers, 3-10], "expected_sign": 1|-1, "h": 1|5, "shock_z": 2.0}
   tests: after a driver shock at close t (|daily change| >= shock_z trailing sd), does the target basket move from open t+1 to close t+h beyond its market beta in the expected direction? design 2016-2022, confirm 2023-2026.
2. event_readthrough params {"link": "comention"|"corr_peer", "event_type": one of earnings_report, guidance_change, new_contract_or_partnership, regulatory_approval, clinical_trial_result, equity_issuance_dilution, analyst_target_change, "min_ratio": 2.0-4.0, "k": 3-8, "min_source_dv_pct": 0 or 0.5}
   tests: after a source name's big reaction to that event type, do linked names (co-mentioned in earlier news, or return-correlation peers) move more than their own volatility the next session, vs vol-matched unlinked names? design 2025, confirm 2026.
3. size_feature_increment params {"feature_set": "abn_attention"|"tone_agreement"|"event_prior", "design_fold": "F2025"|"F2026", "confirm_fold": "F2026"|"F2025"}
   tests: does a cell-level news feature add rank IC for the size of the next-session move over trailing volatility + a TF-IDF text model?"""


def parse_generated(items, source: str, source_ref: str, symbols: frozenset | set | None = None) -> list[dict]:
    """Model output -> typed rows. Anything malformed or without a refutation is kept as a
    DISCARDED row so the discard rate per model is visible; a cell whose params do not validate
    becomes NEEDS_CELL (with the reason in `params._invalid`)."""
    from backend.services import hyp_cells  # noqa: PLC0415
    out = []
    if isinstance(items, dict):
        items = items.get("hypotheses") or [items]
    for it in items or []:
        if not isinstance(it, dict):
            continue
        tgt = it.get("target") if it.get("target") in TARGETS else "return"
        ct = it.get("cell_type") if it.get("cell_type") in hyp_cells.CELL_TYPES else None
        params = it.get("params") if isinstance(it.get("params"), dict) else {}
        ok, why = validate_params(ct, params, symbols) if ct else (False, "no cell type")
        if ct and not ok:
            ct, params = None, {**params, "_invalid": why}
        label = re.sub(r"[^a-z0-9_]", "_", str(it.get("family") or "generated").lower())[:40] or "generated"
        fam = canonical_family(label)
        try:
            row = make_hypothesis(
                title=str(it.get("title") or "")[:160] or "untitled", mechanism=str(it.get("mechanism") or ""),
                precursor=str(it.get("precursor") or ""), separation_from_beta=str(it.get("separation_from_beta") or ""),
                refutation=str(it.get("refutation") or ""), target=tgt, family=fam, source=source,
                source_ref=source_ref, cell_type=ct, params=params if ct else {},
                expected_power=0.5 if ct else 0.2, cpu_min=5.0, notes="" if ct else f"params: {json.dumps(params)[:200]}")
            if label != fam:
                row["family_label"] = label
            out.append(row)
        except (ValueError, TypeError):
            continue
    return out


def validate_params(cell_type: str, p: dict, symbols: frozenset | set | None = None) -> tuple[bool, str]:
    """Cheap validation so a generated row can run unattended. With `symbols` (the bars panel's
    symbol set) a macro row needs >= 2 targets and every basket name in the panel."""
    if cell_type == "macro_lead_lag":
        d = str(p.get("driver", ""))
        if not (d in ("CL=F", "^TNX") or (d.startswith("basket:") and len(d) > 8)):
            return False, "driver"
        t = p.get("targets")
        if not isinstance(t, list) or not 1 <= len(t) <= 15:
            return False, "targets"
        if symbols is not None:
            if sum(1 for x in t if x in symbols) < 2:
                return False, "fewer than 2 targets in the bars panel"
            if d.startswith("basket:") and not all(x in symbols for x in d[7:].split(",") if x):
                return False, "basket name not in the bars panel"
        if p.get("expected_sign") not in (1, -1):
            return False, "expected_sign"
        if int(p.get("h", 1)) not in (1, 5):
            return False, "h"
        return True, ""
    if cell_type == "event_readthrough":
        if p.get("link") not in ("comention", "corr_peer"):
            return False, "link"
        return True, ""
    if cell_type == "size_feature_increment":
        if p.get("feature_set") not in ("abn_attention", "tone_agreement", "event_prior"):
            return False, "feature_set"
        if {p.get("design_fold"), p.get("confirm_fold")} != {"F2025", "F2026"}:
            return False, "folds"
        return True, ""
    return False, "cell type"


def _created_within(h: dict, seconds: float) -> bool:
    try:
        ts = datetime.fromisoformat(str(h.get("created_utc"))).timestamp()
    except ValueError:
        return False
    return ts >= datetime.now(timezone.utc).timestamp() - seconds


def render_markdown(state: dict[str, dict], path: Path | None = None,
                    family_policy: dict[str, dict] | None = None) -> str:
    """LEDGER.md: the ranked queue, the verdicts, and the families' track records (with the
    D6 generation policy per family: posterior, weight, quota, generated tonight, shrunk)."""
    fam = family_record(state)
    q = rank(state)
    if family_policy is None:
        # no nightly in hand: "tonight" = rows created in the last 24 h
        family_policy = family_policy_report(family_budget(fam, 8),
                                             [h for h in state.values() if _created_within(h, 86400)], q)
    lines = ["# hyp_lab ledger (generated; the truth is ledger.jsonl)", "",
             f"Rows: {len(state)}. Generated {now_utc()}.", "", "## Verdicts", "",
             "| hyp_id | title | family | verdict | confirm mean | t | MDE |", "|---|---|---|---|---|---|---|"]
    for h in state.values():
        if h.get("verdict"):
            c = (h.get("last_summary") or {}).get("confirm") or {}
            lines.append(f"| {h['hyp_id']} | {h['title']} | {h.get('family')} | {h['verdict']} | "
                         f"{c.get('mean')} | {c.get('t')} | {c.get('mde')} |")
    lines += ["", "## Queue (ranked by EV)", "", "| rank | hyp_id | title | target | cell | EV | P(change) | value | source |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, h in enumerate(q[:40], 1):
        s = h["score"]
        lines.append(f"| {i} | {h['hyp_id']} | {h['title']} | {h['target']} | {h.get('cell_type') if h.get('status') == 'PROPOSED' else 'NEEDS_CELL'} | "
                     f"{s['ev']} | {s['p_change']} | {s['value']} | {h['source']} |")
    lines += ["", "## Family track record", "",
              f"Posterior fed back into generation (D6): below P = {C.HYP_LAB_FAMILY_POSTERIOR_FLOOR} a family's "
              f"quota and EV are multiplied by max({C.HYP_LAB_FAMILY_MIN_WEIGHT}, P / "
              f"{C.HYP_LAB_FAMILY_POSTERIOR_FLOOR}); never a kill.", "",
              "| family | + | - | ? | posterior P(positive) | weight | quota of 8 | n_generated_tonight "
              "| n_deferred_tonight | n_shrunk |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(fam.items(), key=lambda kv: -kv[1]["n_rows"]):
        fp = family_policy.get(k) or {}
        lines.append(f"| {k} | {v['CONDITIONAL_POSITIVE']} | {v['FAILED_VARIANT']} | {v['CANNOT_DISTINGUISH']} | "
                     f"{v['p_positive']} | {fp.get('weight', 1.0)} | {fp.get('quota')} | "
                     f"{fp.get('n_generated_tonight', 0)} | {fp.get('n_deferred_tonight', 0)} | {fp.get('n_shrunk', 0)} |")
    counts: dict[str, int] = {}
    for h in state.values():
        counts[h.get("status", "?")] = counts.get(h.get("status", "?"), 0) + 1
    lines += ["", "## Status counts", "", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))]
    md = "\n".join(lines) + "\n"
    (path or (HYP_DIR / "LEDGER.md")).write_text(md, encoding="utf-8")
    return md
