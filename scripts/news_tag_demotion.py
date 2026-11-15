"""CH-46d -- does the CH-46 classifier's REJECT find WRONG hub tags? (`backend/services/news_tag_demotion.py`)

    python -m scripts.news_tag_demotion sheet    --work DIR --ch46 DIR
    python -m scripts.news_tag_demotion evaluate --work DIR --ch46 DIR --declaration FILE
                                                 [--data-root <optimus dir>] [--profiles FILE]

`sheet` reads the frozen CH-46 artefacts (rows.jsonl, pairs.npz, classifier.json,
companies.json; nothing is refitted), builds the POPULATION (body-match and digest `mentions`
tags on rows outside the classifier's train split), applies the language gate and both declared
thresholds, and draws the stratified sample. It writes, under `--work` only:
`population.jsonl` (ids, tickers, numbers), `labelling_blind.csv` (shuffled; title and an
excerpt for LOCAL reading; NO score, decision or rule column) and `labelling_key.csv` (the key).
`evaluate` reads `labels_builder.csv` (lid,label,reason) and writes `demotion_receipt.json`
and the demotion sidecar. `--work` must be outside any git checkout: the blind sheet holds
licensed text.

Exit codes: 0 ok; 2 a refusal (a missing input, `--work` inside a repo, an unreadable sidecar,
labels missing for sampled pairs). No LLM call, no network, no scheduled caller.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import argparse  # noqa: E402
import csv  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Optional  # noqa: E402

import numpy as np  # noqa: E402

from backend import config as C  # noqa: E402
from backend.services import news_entity_embed as NEE  # noqa: E402
from backend.services import news_tag_demotion as ND  # noqa: E402

POP_NAME = "population.jsonl"
BLIND_NAME = "labelling_blind.csv"
KEY_NAME = "labelling_key.csv"
LABELS_NAME = "labels_builder.csv"
RECEIPT_NAME = "demotion_receipt.json"
EXCERPT_HEAD = 600
EXCERPT_WIN = 300


class EvalRefused(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _need(p: Path) -> Path:
    if not Path(p).is_file():
        raise EvalRefused("INPUT_MISSING", f"no {p}")
    return Path(p)


def _sha_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ─────────────────────────────────────────────── population

def thresholds(ch46: Path) -> dict:
    """Variant 1 = the CH-46 `reject` threshold as frozen in classifier.json; variant 2 = the
    declared alternative (NEWS_DEMOTE_ALT_POS_SHARE of validation positives below it)."""
    model = json.loads(_need(ch46 / NEE.MODEL_NAME).read_text(encoding="utf-8"))
    d = np.load(_need(ch46 / NEE.PAIRS_NAME))
    part, row, y, score = d["part"], d["row"], d["y"], d["score"]
    va = part[row] == 1
    v1_check = NEE.choose_thresholds(score[va], y[va])["reject"]
    v2 = NEE.choose_thresholds(score[va], y[va], reject_pos_share=float(C.NEWS_DEMOTE_ALT_POS_SHARE))
    return {"v1": float(model["thresholds"]["reject"]), "v1_recomputed": float(v1_check),
            "v2": float(v2["reject"]), "v2_pos_share": float(C.NEWS_DEMOTE_ALT_POS_SHARE),
            "classifier": model.get("classifier_sha"),
            "model": f"{model['model'].get('model_id')}@{str(model['model'].get('revision'))[:12]}"}


def month_of(eff: Optional[str], ep: int, lo: int) -> str:
    if not eff or ep < lo:
        return "pre-window"
    return eff[:7]


def build_population(ch46: Path) -> tuple[list[dict], dict, dict]:
    """One record per population tag (+ the texts of population rows, kept in memory only)."""
    th = thresholds(ch46)
    records, _CE, _m = NEE.load_company_index(ch46)
    syms = [r["symbol"] for r in records]
    sym_ix = {s: i for i, s in enumerate(syms)}
    nc = len(syms)
    d = np.load(ch46 / NEE.PAIRS_NAME)
    prow, pcomp, pscore, part = d["row"], d["comp"], d["score"], d["part"]
    pkey = prow.astype(np.int64) * nc + pcomp.astype(np.int64)
    order = np.argsort(pkey, kind="stable")
    skey = pkey[order]
    rows_meta: list[tuple] = []
    texts: dict[int, dict] = {}
    pop: list[dict] = []
    ep_max = 0
    for i, r in enumerate(NEE.iter_row_file(ch46)):
        ep_max = max(ep_max, int(r.get("ep") or 0))
        tags = [h for h in r.get("hub") or [] if ND.is_demotable(h)]
        if not tags or int(part[i]) == 0:
            continue
        gate_text = f"{r.get('title') or ''} {r.get('text') or ''}"
        gated = ND.non_english(gate_text)
        texts[i] = {"title": r.get("title") or "", "text": r.get("text") or "",
                    "tlen": int(r.get("tlen") or 0), "ment": r.get("ment") or {}}
        for h in tags:
            t, m, _tier, where = ND._fields(h)
            j = -1
            if t in sym_ix:
                k = i * nc + sym_ix[t]
                a = int(np.searchsorted(skey, k))
                if a < len(skey) and skey[a] == k:
                    j = int(order[a])
            sc = float(pscore[j]) if j >= 0 else None
            pop.append({"ri": i, "row_id": r["id"], "ticker": t, "fam": r["fam"], "eff": r.get("eff"),
                        "ep": int(r.get("ep") or 0), "part": int(part[i]), "pair": j, "score": sc,
                        "method": "digest" if m == "digest_typed" else "body", "gated": bool(gated),
                        "labelled_row": bool(r.get("pos")),
                        "label_a": (0 if t not in (r.get("pos") or []) else 1) if r.get("pos") else None})
        rows_meta.append(i)
    lo = ep_max - int(C.TICKER_HUB_INDEX_DAYS) * 86400
    for p in pop:
        p["month"] = month_of(p["eff"], p["ep"], lo)
        sc = p["score"]
        p["dec1"] = ND.decide_gated(sc, th["v1"], p["gated"])
        p["dec2"] = ND.decide_gated(sc, th["v2"], p["gated"])
        p["dec1_ungated"] = ND.decide_gated(sc, th["v1"], False)
    meta = {"thresholds": th, "ep_max": ep_max, "window_lo_utc": datetime.fromtimestamp(lo, timezone.utc).isoformat(),
            "rows_with_population_tags": len(rows_meta)}
    return pop, texts, meta


# ─────────────────────────────────────────────── sampling

def allocate(sizes: dict, n: int) -> dict:
    """Proportional allocation with largest remainder (never more than a stratum holds)."""
    tot = sum(sizes.values())
    if tot == 0 or n <= 0:
        return {k: 0 for k in sizes}
    n = min(n, tot)
    raw = {k: n * v / tot for k, v in sizes.items()}
    al = {k: min(int(raw[k]), sizes[k]) for k in sizes}
    left = n - sum(al.values())
    for k in sorted(sizes, key=lambda k: (-(raw[k] - int(raw[k])), k)):
        if left <= 0:
            break
        if al[k] < sizes[k]:
            al[k] += 1
            left -= 1
    return al


def draw(pool: list[int], pop: list[dict], n: int, rng: np.random.Generator) -> list[int]:
    by: dict = defaultdict(list)
    for q in pool:
        by[(pop[q]["fam"], pop[q]["month"])].append(q)
    al = allocate({k: len(v) for k, v in by.items()}, n)
    out: list[int] = []
    for k in sorted(by):
        if al[k]:
            out += sorted(rng.choice(by[k], al[k], replace=False).tolist())
    return out


def excerpt(t: dict, ticker: str) -> str:
    text = t["text"]
    head = text[:EXCERPT_HEAD]
    pos = (t["ment"].get(ticker) or [0, 1.0])[1]
    off = int(float(pos) * max(t["tlen"], 1))
    if EXCERPT_HEAD - 50 < off < len(text):
        head += " [...] " + text[max(0, off - EXCERPT_WIN): off + EXCERPT_WIN]
    if t["tlen"] > len(text) or len(text) > EXCERPT_HEAD:
        head += " [excerpt ends]"
    return head


def _prior_audit_pairs(ch46: Path) -> set:
    p = ch46 / "self_audit_sheet.csv"
    if not p.is_file():
        return set()
    with open(p, encoding="utf-8", newline="") as fh:
        return {int(r["pair"]) for r in csv.DictReader(fh)}


def cmd_sheet(work: Path, ch46: Path) -> dict:
    pop, texts, meta = build_population(ch46)
    prior = _prior_audit_pairs(ch46)
    rng = np.random.default_rng(int(C.NEWS_DEMOTE_SEED))
    rej = [q for q, p in enumerate(pop) if p["dec1"] == ND.REJECT and p["pair"] not in prior]
    kept = [q for q, p in enumerate(pop) if p["dec1"] != ND.REJECT and (p["pair"] < 0 or p["pair"] not in prior)]
    s_rej = draw(rej, pop, int(C.NEWS_DEMOTE_SAMPLE_REJECT), rng)
    s_kept = draw(kept, pop, int(C.NEWS_DEMOTE_SAMPLE_KEPT), rng)
    sample = [(q, "reject") for q in s_rej] + [(q, "kept") for q in s_kept]
    perm = rng.permutation(len(sample))
    records, _CE, _m = NEE.load_company_index(ch46)
    names = {r["symbol"]: r["name"] for r in records}
    with open(work / POP_NAME, "w", encoding="utf-8") as fh:
        for q, p in enumerate(pop):
            fh.write(json.dumps({"q": q, **p}, ensure_ascii=True, separators=(",", ":")) + "\n")
    with open(work / BLIND_NAME, "w", encoding="utf-8", newline="") as fb, \
            open(work / KEY_NAME, "w", encoding="utf-8", newline="") as fk:
        wb, wk = csv.writer(fb), csv.writer(fk)
        wb.writerow(["lid", "ticker", "company", "source_family", "title", "excerpt"])
        wk.writerow(["lid", "q", "arm", "row_id", "ticker", "fam", "month", "score", "dec1", "dec2", "pair"])
        for lid, k in enumerate(perm, 1):
            q, arm = sample[int(k)]
            p = pop[q]
            t = texts[p["ri"]]
            wb.writerow([lid, p["ticker"], names.get(p["ticker"]), p["fam"], t["title"], excerpt(t, p["ticker"])])
            wk.writerow([lid, q, arm, p["row_id"], p["ticker"], p["fam"], p["month"], p["score"],
                         p["dec1"], p["dec2"], p["pair"]])
    return {"population_tags": len(pop), "reject_pool": len(rej), "kept_pool": len(kept),
            "sampled_reject": len(s_rej), "sampled_kept": len(s_kept), "prior_audit_pairs_excluded": len(prior),
            **meta}


# ─────────────────────────────────────────────── evaluation

def _rate(k: int, n: int) -> dict:
    return {"n": n, "k": k, "share": round(k / n, 4) if n else None, "ci95": NEE.wilson(k, n)}


def _load_jsonl(p: Path) -> list[dict]:
    with open(_need(p), encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def _labels(work: Path, key: list[dict]) -> dict[int, int]:
    lab: dict[int, int] = {}
    with open(_need(work / LABELS_NAME), encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            v = str(r.get("label") or "").strip()
            if v in ("0", "1", "2"):
                lab[int(r["lid"])] = int(v)
    missing = [k["lid"] for k in key if int(k["lid"]) not in lab]
    if missing:
        raise EvalRefused("LABELS_MISSING", f"{len(missing)} sampled pairs carry no label (first: {missing[:5]})")
    return lab


def wrong_table(items: list[tuple[str, int]]) -> dict:
    """{group: rate of label 0 among labels 0/1} plus the cannot-tell count."""
    g: dict = defaultdict(Counter)
    for k, lab in items:
        g[k][lab] += 1
    return {k: {**_rate(c[0], c[0] + c[1]), "cannot_tell": c[2]} for k, c in sorted(g.items())}


def weighted_wrong(sample: list[tuple[tuple, int]], pool_sizes: Counter) -> dict:
    """Stratum-weighted share wrong (weights = pool stratum sizes, over sampled strata only)."""
    by: dict = defaultdict(Counter)
    for s, lab in sample:
        if lab in (0, 1):
            by[s][lab] += 1
    w_tot = sum(pool_sizes[s] for s in by)
    if not w_tot:
        return {"share": None, "pool_share_covered": 0.0}
    est = sum(pool_sizes[s] * by[s][0] / (by[s][0] + by[s][1]) for s in by) / w_tot
    return {"share": round(est, 4), "pool_share_covered": round(w_tot / max(sum(pool_sizes.values()), 1), 4)}


def share_removed(rej_l: list[int], kept_l: list[int], n_rej: int, n_kept: int,
                  between_l: Optional[list[int]] = None, n_between: int = 0,
                  B: Optional[int] = None, seed: Optional[int] = None) -> dict:
    """Share of all wrong population tags that the reject removes, with a bootstrap interval.
    Labels are 0 (wrong) / 1 (right); `between` is the variant-1 reject band a stricter
    variant keeps."""
    B = int(C.NEWS_DEMOTE_BOOTSTRAP if B is None else B)
    rng = np.random.default_rng(int(C.NEWS_DEMOTE_SEED if seed is None else seed))
    a, b = np.array(rej_l), np.array(kept_l)
    c = np.array(between_l or [], dtype=int)

    def est(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> Optional[float]:
        if not len(x) or not len(y):
            return None
        wr = n_rej * float((x == 0).mean())
        wk = n_kept * float((y == 0).mean())
        wb = n_between * float((z == 0).mean()) if len(z) else 0.0
        tot = wr + wk + wb
        return wr / tot if tot else None

    point = est(a, b, c)
    bs = []
    for _ in range(B):
        e = est(rng.choice(a, len(a)) if len(a) else a, rng.choice(b, len(b)) if len(b) else b,
                rng.choice(c, len(c)) if len(c) else c)
        if e is not None:
            bs.append(e)
    ci = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)] if bs else [None, None]
    return {"share": round(point, 4) if point is not None else None, "ci95_bootstrap": ci, "B": B,
            "n_reject_pool": n_rej, "n_kept_pool": n_kept, "n_between_pool": n_between}


def verdict(k_wrong: int, n: int, bar: Optional[float] = None) -> str:
    bar = float(C.NEWS_DEMOTE_PRECISION_BAR if bar is None else bar)
    lo, hi = NEE.wilson(k_wrong, n)
    if lo is None:
        return "CANNOT_DISTINGUISH"
    if lo >= bar:
        return "OBSERVED"
    if hi < bar:
        return "FAILED_VARIANT"
    return "CANNOT_DISTINGUISH"


def hub_effect(data_root: Path, profiles: Path, demotions: dict, top_n: Optional[int] = None) -> dict:
    """Rows per ticker in the LIVE hub generation before and after hiding the demotions, for
    the largest companies by market cap present in the hub universe. Reads ids and tags only."""
    top_n = int(C.NEWS_DEMOTE_TOP_N if top_n is None else top_n)
    root = Path(data_root) / str(C.TICKER_HUB_DIRNAME)
    cur = json.loads(_need(root / "CURRENT.json").read_text(encoding="utf-8"))
    gen = root / cur["generation"]
    uni = json.loads(_need(gen / "universe.json").read_text(encoding="utf-8"))
    prof = json.loads(_need(profiles).read_text(encoding="utf-8"))
    caps = sorted(((float(v.get("market_cap_usd") or 0), s) for s, v in prof.items()
                   if s in uni and isinstance(v, dict) and v.get("market_cap_usd")), reverse=True)
    top = [s for _c, s in caps[:top_n]]
    before, after, about_b, about_a, hidden_by = Counter(), Counter(), Counter(), Counter(), Counter()
    n_rows = n_hidden = n_rows_touched = 0
    for f in sorted(gen.glob("rows_*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                o = json.loads(line)
                rid, tags = o.get("id"), o.get("tags") or []
                n_rows += 1
                kept, hidden = ND.apply_demotions(rid, tags, demotions)
                n_hidden += len(hidden)
                n_rows_touched += 1 if hidden else 0
                for t in {x.get("t") for x in tags}:
                    before[t] += 1
                for t in {x.get("t") for x in kept}:
                    after[t] += 1
                for t in {x.get("t") for x in tags if x.get("tier") == "about"}:
                    about_b[t] += 1
                for t in {x.get("t") for x in kept if x.get("tier") == "about"}:
                    about_a[t] += 1
                for x in hidden:
                    hidden_by[x.get("t")] += 1
    table = []
    for s in top:
        b, a = before[s], after[s]
        table.append({"ticker": s, "rows_before": b, "rows_after": a, "hidden": b - a,
                      "share_hidden": round((b - a) / b, 4) if b else None,
                      "about_before": about_b[s], "about_after": about_a[s],
                      "loses_more_than_half": bool(b and (b - a) / b > 0.5)})
    return {"generation": cur["generation"], "built_utc": cur.get("built_utc"), "hub_rows": n_rows,
            "tags_hidden": n_hidden, "rows_touched": n_rows_touched,
            "demotions_in_sidecar": len(demotions),
            "demotions_matched_in_live_hub": sum(hidden_by.values()),
            "top_by_market_cap": table,
            "tickers_losing_more_than_half": [r["ticker"] for r in table if r["loses_more_than_half"]],
            "about_tags_changed": sum(1 for r in table if r["about_before"] != r["about_after"]),
            "market_cap_source": str(profiles)}


def cmd_evaluate(work: Path, ch46: Path, declaration: Path, data_root: Path, profiles: Path) -> dict:
    pop = _load_jsonl(work / POP_NAME)
    with open(_need(work / KEY_NAME), encoding="utf-8", newline="") as fh:
        key = list(csv.DictReader(fh))
    lab = _labels(work, key)
    th = thresholds(ch46)
    # ── counts
    strata = Counter((p["fam"], p["month"]) for p in pop)
    dec1 = Counter(p["dec1"] for p in pop)
    rej_pool = Counter((p["fam"], p["month"]) for p in pop if p["dec1"] == ND.REJECT)
    kept_pool = Counter((p["fam"], p["month"]) for p in pop if p["dec1"] != ND.REJECT)
    gated = [p for p in pop if p["dec1"] == ND.UNCERTAIN_LANGUAGE]
    gate = {"bar_non_latin_share": float(ND.L.NON_LATIN_BAR),
            "population_pairs_scored": sum(1 for p in pop if p["score"] is not None),
            "pairs_moved_to_uncertain": len(gated),
            "rows_moved": len({p["row_id"] for p in gated}),
            "of_which_would_have_been_reject": sum(1 for p in gated if p["dec1_ungated"] == ND.REJECT),
            "by_source": dict(Counter(p["fam"] for p in gated)),
            "reject_without_gate": sum(1 for p in pop if p["dec1_ungated"] == ND.REJECT),
            "reject_with_gate": dec1[ND.REJECT]}
    # ── (a) precise-label contradiction (recall only: every tag in this pool is wrong by the label)
    pa = [p for p in pop if p["label_a"] is not None]
    a_wrong = [p for p in pa if p["label_a"] == 0]
    scored_a = [p for p in a_wrong if p["score"] is not None]
    by_fam_a = defaultdict(Counter)
    for p in a_wrong:
        by_fam_a[p["fam"]]["n"] += 1
        by_fam_a[p["fam"]]["rej1"] += int(p["dec1"] == ND.REJECT)
        by_fam_a[p["fam"]]["rej2"] += int(p["dec2"] == ND.REJECT)
    precise = {"pool_tags": len(pa), "contradicted_by_precise_label": len(a_wrong),
               "agreeing_with_precise_label": len(pa) - len(a_wrong), "scored": len(scored_a),
               "v1_rejected": _rate(sum(1 for p in a_wrong if p["dec1"] == ND.REJECT), len(a_wrong)),
               "v2_rejected": _rate(sum(1 for p in a_wrong if p["dec2"] == ND.REJECT), len(a_wrong)),
               "v1_rejected_by_source": {f: _rate(c["rej1"], c["n"]) for f, c in sorted(by_fam_a.items())},
               "by_part": dict(Counter(str(p["part"]) for p in a_wrong)),
               "note": ("every tag in this pool is WRONG by the precise label (a ticker not named in the title "
                        "or filing of a row that has one), so this measures RECALL of the reject on wrong "
                        "tags, not its precision; the precise label is itself not exhaustive")}
    # ── (b) builder's labels
    rej_s = [(k, lab[int(k["lid"])]) for k in key if k["arm"] == "reject"]
    kept_s = [(k, lab[int(k["lid"])]) for k in key if k["arm"] == "kept"]
    r01 = [(k, v) for k, v in rej_s if v in (0, 1)]
    k01 = [(k, v) for k, v in kept_s if v in (0, 1)]
    k_wrong_r = sum(1 for _k, v in r01 if v == 0)
    t2 = th["v2"]
    r2 = [(k, v) for k, v in r01 if float(k["score"]) < t2]
    between = [(k, v) for k, v in r01 if float(k["score"]) >= t2]
    n_rej1 = dec1[ND.REJECT]
    n_rej2 = sum(1 for p in pop if p["dec2"] == ND.REJECT)
    n_kept1 = len(pop) - n_rej1
    v1 = {"threshold": th["v1"], "pool": n_rej1,
          "precision_reject_is_wrong": {**_rate(k_wrong_r, len(r01)),
                                        "cannot_tell": sum(1 for _k, v in rej_s if v == 2)},
          "precision_weighted_by_stratum": weighted_wrong([((k["fam"], k["month"]), v) for k, v in rej_s], rej_pool),
          "by_source": wrong_table([(k["fam"], v) for k, v in rej_s]),
          "by_month": wrong_table([(k["month"], v) for k, v in rej_s]),
          "by_method": wrong_table([(pop[int(k["q"])]["method"], v) for k, v in rej_s]),
          "kept_sample_wrong": {**_rate(sum(1 for _k, v in k01 if v == 0), len(k01)),
                                "cannot_tell": sum(1 for _k, v in kept_s if v == 2),
                                "by_source": wrong_table([(k["fam"], v) for k, v in kept_s]),
                                "by_decision": wrong_table([(k["dec1"], v) for k, v in kept_s])},
          "share_of_wrong_tags_removed": share_removed([v for _k, v in r01], [v for _k, v in k01], n_rej1, n_kept1),
          "verdict": verdict(k_wrong_r, len(r01))}
    k2 = sum(1 for _k, v in r2 if v == 0)
    v2 = {"threshold": t2, "pos_share": th["v2_pos_share"], "pool": n_rej2,
          "precision_reject_is_wrong": _rate(k2, len(r2)),
          "note": "estimated on the variant-1 reject sample pairs that score below the variant-2 threshold",
          "share_of_wrong_tags_removed": share_removed([v for _k, v in r2], [v for _k, v in k01], n_rej2, n_kept1,
                                                       between_l=[v for _k, v in between],
                                                       n_between=n_rej1 - n_rej2),
          "verdict": verdict(k2, len(r2))}
    # ── sidecar (variant 1) and the hub effect
    decl_sha = _sha_file(declaration)
    lines = [ND.sidecar_line(p["row_id"], p["ticker"], p["score"], th["v1"], variant="v1",
                             classifier=th["classifier"], model=th["model"], declaration_sha=decl_sha[:16])
             for p in pop if p["dec1"] == ND.REJECT]
    sc_path = ND.default_sidecar_path(work)
    n_lines = ND.write_sidecar(sc_path, lines)
    dem = ND.read_sidecar(sc_path)
    hub_root = Path(data_root) / str(C.TICKER_HUB_DIRNAME)
    files_before = sum(len(fn) for _d, _n, fn in os.walk(hub_root))
    hub = hub_effect(data_root, profiles, dem)
    files_after = sum(len(fn) for _d, _n, fn in os.walk(hub_root))
    hub["live_hub_files_before_after"] = [files_before, files_after]
    return {
        "schema": "news-tag-demotion-eval/1", "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "declaration": {"path": str(declaration), "sha256": decl_sha},
        "inputs": {"ch46_work": str(ch46), "classifier": th["classifier"], "model": th["model"],
                   "pairs_sha256_16": _sha_file(ch46 / NEE.PAIRS_NAME)[:16]},
        "thresholds": th, "variants_tried": 2,
        "population": {"tags": len(pop), "rows": len({p["row_id"] for p in pop}),
                       "by_method": dict(Counter(p["method"] for p in pop)),
                       "by_decision_v1": dict(dec1),
                       "by_decision_v2": dict(Counter(p["dec2"] for p in pop)),
                       "by_part": dict(Counter(str(p["part"]) for p in pop)),
                       "n_per_stratum": {f"{a}|{b}": n for (a, b), n in sorted(strata.items())},
                       "reject_pool_per_stratum": {f"{a}|{b}": n for (a, b), n in sorted(rej_pool.items())},
                       "kept_pool_per_stratum": {f"{a}|{b}": n for (a, b), n in sorted(kept_pool.items())}},
        "sample": {"reject": len(rej_s), "kept": len(kept_s),
                   "reject_per_stratum": dict(Counter(f"{k['fam']}|{k['month']}" for k, _v in rej_s)),
                   "kept_per_stratum": dict(Counter(f"{k['fam']}|{k['month']}" for k, _v in kept_s)),
                   "labels": dict(Counter(str(v) for v in lab.values())),
                   "labeller": "the builder (an AI agent), blind to score and decision -- NOT an independent labeller"},
        "language_gate": gate, "precise_label_contradiction": precise,
        "variant_1": v1, "variant_2": v2,
        "sidecar": {"path": str(sc_path), "lines": n_lines, "round_trip_keys": len(dem)},
        "hub_effect": hub,
        "verdict": v1["verdict"],
        "verdict_bar": float(C.NEWS_DEMOTE_PRECISION_BAR),
    }


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("sheet", "evaluate"))
    ap.add_argument("--work", required=True)
    ap.add_argument("--ch46", required=True)
    ap.add_argument("--declaration")
    ap.add_argument("--data-root", default=str(C.OPTIMUS_LEDGER_DIR))
    ap.add_argument("--profiles", default=str(Path.home() / "aegis-alpha-terminal" / "state" / "tracker" / "profiles.json"))
    a = ap.parse_args(argv)
    try:
        work = NEE.check_out_dir(Path(a.work))
        ch46 = Path(a.ch46)
        if a.cmd == "sheet":
            res = cmd_sheet(work, ch46)
            print(json.dumps(res, indent=1, default=str))
            return 0
        if not a.declaration:
            raise EvalRefused("DECLARATION_MISSING", "evaluate needs --declaration")
        res = cmd_evaluate(work, ch46, _need(Path(a.declaration)), Path(a.data_root), Path(a.profiles))
        tmp = work / (RECEIPT_NAME + ".tmp")
        tmp.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, work / RECEIPT_NAME)
        print(json.dumps({"verdict": res["verdict"], "v1": res["variant_1"]["precision_reject_is_wrong"],
                          "receipt": str(work / RECEIPT_NAME)}, indent=1))
        return 0
    except (EvalRefused, ND.DemotionRefused, NEE.EmbedTagRefused) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
