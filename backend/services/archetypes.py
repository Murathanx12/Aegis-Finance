"""EVENT ARCHETYPES -- the unsupervised -> typed-hypothesis -> genome route (lane U).

WHAT THIS IS
============
`docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` block U. The idea Murat keeps
returning to: *an event causes many downstream consequences, and the interesting
structure is in the SHAPE of an event, not in its ticker.* So:

    U1  embed the canonical events, cluster them into ARCHETYPES
    U2  each archetype emits a TYPED HYPOTHESIS -- precursor, direction,
        horizon, family, members -- routed through
        `research_gym.scope.corpse_check`, the MECHANISTIC comparator
    U3  a KNOWN-ANSWER gate: a planted event family with a planted drift must be
        recovered end to end, and a planted NULL family must read noise

U3 IS BUILT FIRST AND IT IS THE POINT. A discovery pipeline that has never been
shown to find a planted answer is not evidence of anything. `plant_family()` and
`known_answer()` below are the harness; `backend/tests/test_u_archetypes.py`
runs it offline (network-blocked CI) on a synthetic panel, and
`scripts/u_archetypes_run.py` runs the same code on the real corpus with the
NVIDIA `nemotron-3-embed-1b` embeddings.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
* It does not fetch. Every function here takes arrays and frames. The script
  owns I/O so the whole discovery path is exercisable with no network -- which
  is what makes the known-answer runnable in the fast suite.
* It has NO trading authority. It emits hypotheses and grades them. Nothing
  here sizes, stops, or orders. LICENCE: PRODUCT_EXPERIMENT.
* It never lets a cluster LABEL become evidence. A label is a description
  produced once by a free model from member titles alone; the MEMBERS are the
  evidence and the grading never reads the label.

THE FOUR TRAPS THIS FILE IS WRITTEN AGAINST
===========================================
1. **Name-days are not periods.** Pooling event-days printed t -65 once where
   one portfolio return per period gave t -16.6. Every t here is computed on
   BLOCK means (one observation per calendar month), never on events.
2. **An EW average against a VW market is the regime.** So `block_grade`
   reports the equal-weighted AND the value-weighted block series side by side,
   and a hypothesis whose EW and VW signs disagree is stamped
   `EW_VW_DISAGREE`.
3. **35 rows of 46,361 once carried 81% of a result.** `tail_diagnostics`
   reports the top-1% contribution share and the block jackknife BEFORE any
   verdict is read.
4. **A benchmark-relative number inside an absolute structure.** Every result
   carries `raw_mean_pp` and `mkt_mean_pp` beside `ar_mean_pp`, and beta is
   printed first.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Sequence

import numpy as np

from backend.services.research_gym import power as PW
from backend.services.research_gym import scope as SC

LICENCE = "PRODUCT_EXPERIMENT"

# -- 1. EMBEDDING -----------------------------------------------------------
#
# Two embedders, one interface. The hashing one is deterministic, offline and
# free, and is the ONLY one the fast suite may use (network is blocked there).
# The NIM one is the production path for the real run; it lives in the script,
# not here, so importing this module can never make a network call.

_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def hash_embed(texts: Sequence[str], dim: int = 256, *, ngram: int = 2,
               seed: int = 0) -> np.ndarray:
    """A deterministic hashing bag-of-ngrams embedder, L2-normalised.

    Not a language model and not pretending to be one. It exists so the whole
    clustering -> hypothesis -> grading path can be exercised with the network
    blocked, and so the known-answer gate has an embedder whose behaviour is a
    function of the text and nothing else. Same text, same vector, forever.
    """
    X = np.zeros((len(texts), dim), dtype="float64")
    for i, t in enumerate(texts):
        toks = tokenize(t)
        grams = list(toks)
        for n in range(2, max(2, ngram) + 1):
            grams += [" ".join(toks[j:j + n]) for j in range(len(toks) - n + 1)]
        for g in grams:
            h = hashlib.blake2b(f"{seed}:{g}".encode(), digest_size=8).digest()
            idx = int.from_bytes(h, "big") % dim
            sign = 1.0 if (h[0] & 1) else -1.0
            X[i, idx] += sign
    return l2_normalise(X)


def l2_normalise(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype="float64")
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return X / n


# -- 2. CLUSTERING ----------------------------------------------------------

def kmeans(X: np.ndarray, k: int, *, seed: int = 0, n_init: int = 4,
           max_iter: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Spherical k-means on L2-normalised rows (cosine == euclidean there).

    Written out rather than imported so the result does not move when sklearn
    changes a default. `n_init` restarts, best inertia wins.
    """
    X = l2_normalise(X)
    n = X.shape[0]
    k = int(min(max(1, k), n))
    best = None
    for r in range(n_init):
        rng = np.random.default_rng(seed * 1000 + r)
        centres = [X[rng.integers(n)]]
        for _ in range(k - 1):
            d = 1.0 - np.max(np.asarray(centres) @ X.T, axis=0)
            d = np.clip(d, 0.0, None)
            tot = d.sum()
            centres.append(X[rng.integers(n)] if tot <= 0
                           else X[rng.choice(n, p=d / tot)])
        C = l2_normalise(np.asarray(centres))
        lab = np.full(n, -1, dtype="int64")
        for _ in range(max_iter):
            new = np.argmax(X @ C.T, axis=1)
            if np.array_equal(new, lab):
                break
            lab = new
            for j in range(k):
                m = lab == j
                if m.any():
                    C[j] = X[m].mean(axis=0)
            C = l2_normalise(C)
        inertia = float(np.sum(1.0 - np.max(X @ C.T, axis=1)))
        if best is None or inertia < best[0]:
            best = (inertia, lab.copy(), C.copy())
    return best[1], best[2]


def silhouette(X: np.ndarray, labels: Sequence[int], *, sample: int = 2000,
               seed: int = 0) -> float | None:
    """Cosine silhouette on a bounded random sample (the full matrix is O(n^2)).

    Returns None where fewer than two clusters have members -- a silhouette on
    one cluster is a number with no meaning, and reporting 0.0 there would read
    as "measured and bad" rather than "not defined".
    """
    X = l2_normalise(X)
    labels = np.asarray(labels)
    if np.unique(labels).size < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = (np.arange(X.shape[0]) if X.shape[0] <= sample
           else np.sort(rng.choice(X.shape[0], size=sample, replace=False)))
    Xs, ls = X[idx], labels[idx]
    if np.unique(ls).size < 2:
        return None
    D = 1.0 - (Xs @ Xs.T)
    np.fill_diagonal(D, np.nan)
    out = []
    uniq = np.unique(ls)
    for i in range(Xs.shape[0]):
        own = ls == ls[i]
        if own.sum() <= 1:
            out.append(0.0)
            continue
        a = float(np.nanmean(D[i, own]))
        b = min(float(np.nanmean(D[i, ls == c])) for c in uniq if c != ls[i])
        out.append(0.0 if max(a, b) == 0 else (b - a) / max(a, b))
    return float(np.mean(out))


def adjusted_rand(a: Sequence[int], b: Sequence[int]) -> float:
    """Adjusted Rand index. 1.0 identical, ~0.0 chance-level agreement."""
    a = np.asarray(a)
    b = np.asarray(b)
    _, ia = np.unique(a, return_inverse=True)
    _, ib = np.unique(b, return_inverse=True)
    cm = np.zeros((ia.max() + 1, ib.max() + 1), dtype="int64")
    np.add.at(cm, (ia, ib), 1)

    def c2(x):
        x = np.asarray(x, dtype="float64")
        return float((x * (x - 1.0) / 2.0).sum())

    sij, sa, sb = c2(cm), c2(cm.sum(1)), c2(cm.sum(0))
    n = c2(np.array([a.size]))
    exp = (sa * sb / n) if n else 0.0
    mx = 0.5 * (sa + sb)
    return 1.0 if mx == exp else float((sij - exp) / (mx - exp))


def stability(X: np.ndarray, k: int, *, seeds: Sequence[int] = (1, 2, 3, 4, 5),
              subsample: float = 0.8, n_init: int = 2,
              max_iter: int = 60) -> dict:
    """Reseed AND resample. A clustering that changes with the seed is not an
    archetype set, and this is the number that says so.

    Each pair of runs is compared on the rows they SHARE, which is why the
    subsample matters: agreeing on the same rows under the same seed is not
    evidence of anything.
    """
    X = np.asarray(X, dtype="float64")
    n = X.shape[0]
    runs = []
    for s in seeds:
        rng = np.random.default_rng(10_000 + s)
        idx = np.sort(rng.choice(n, size=max(2, int(n * subsample)),
                                 replace=False))
        lab, _ = kmeans(X[idx], k, seed=s, n_init=n_init, max_iter=max_iter)
        runs.append((idx, lab))
    aris = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            ia, la = runs[i]
            ib, lb = runs[j]
            common = np.intersect1d(ia, ib)
            if common.size < 10:
                continue
            aris.append(adjusted_rand(la[np.searchsorted(ia, common)],
                                      lb[np.searchsorted(ib, common)]))
    return {"k": int(k), "n_pairs": len(aris),
            "ari_mean": float(np.mean(aris)) if aris else None,
            "ari_min": float(np.min(aris)) if aris else None,
            "seeds": [int(s) for s in seeds], "subsample": float(subsample)}


def choose_k(X: np.ndarray, k_grid: Sequence[int], *, seed: int = 0,
             sample: int = 2000, n_init: int = 2, max_iter: int = 60) -> dict:
    """Silhouette across a DECLARED grid.

    Every k looked at is reported, because a grid that reports only its winner
    has spent budget it did not account for (invariant 16).
    """
    rows = []
    for k in k_grid:
        lab, _ = kmeans(X, k, seed=seed, n_init=n_init, max_iter=max_iter)
        sizes = np.bincount(lab, minlength=int(k)).tolist()
        rows.append({"k": int(k),
                     "silhouette": silhouette(X, lab, sample=sample, seed=seed),
                     "n_clusters_nonempty": int(sum(1 for s in sizes if s)),
                     "size_min": int(min(sizes)), "size_max": int(max(sizes))})
    scored = [r for r in rows if r["silhouette"] is not None]
    best = max(scored, key=lambda r: r["silhouette"])["k"] if scored else None
    return {"grid": [int(k) for k in k_grid], "rows": rows, "best_k": best,
            "n_looked_at": len(rows),
            "note": "every k in the grid is a cell LOOKED AT (invariant 16)"}


def top_terms(members: Sequence[int], all_docs: Sequence[str],
              n: int = 8) -> list[str]:
    """The cluster's most over-represented tokens against the whole corpus.

    A MECHANICAL label. It stands in when no model is reachable, and it is
    recorded beside any model-written label so a reader can see whether the
    sentence matches the members.
    """
    from collections import Counter
    inside, outside = Counter(), Counter()
    mem = set(int(i) for i in members)
    for i, t in enumerate(all_docs):
        (inside if i in mem else outside).update(set(tokenize(t)))
    ni, no = max(1, len(mem)), max(1, len(all_docs) - len(mem))
    score = {}
    for w, c in inside.items():
        if c < max(2, 0.02 * ni) or len(w) < 3:
            continue
        score[w] = (c / ni) / ((outside.get(w, 0) / no) + 1e-6)
    return [w for w, _ in sorted(score.items(), key=lambda kv: -kv[1])[:n]]


# -- 3. TYPED HYPOTHESES ----------------------------------------------------
#
# The precursor vocabulary is SHARED with the corpse register on purpose. A
# comparator that cannot collide is decorative.

#: Mechanism family -> the feature name a rule in that family keys on. These are
#: the same strings the corpse register uses, which is what lets `corpse_check`
#: see a descendant.
FAMILY_FEATURE: dict[str, str] = {
    "events/earnings": "earnings_surprise_sue",
    "events/guidance": "guidance_revision",
    "events/corporate_action": "corporate_action_8k_item",
    "events/regulatory": "regulatory_event_flag",
    "analyst": "analyst_target_upside",
    "positioning": "inst_ownership_change",
    "price": "trailing_return_rank",
    "options": "options_surface_stat",
    "accounting": "accounting_accrual_rank",
    "events/other": "event_text_archetype",
}

#: Lexicons are mechanical and FIXED BEFORE the run. They decide which feature
#: an archetype's precursor names -- not what its answer is.
FAMILY_LEXICON: dict[str, tuple[str, ...]] = {
    "events/earnings": ("earnings", "eps", "beats", "misses", "quarterly",
                        "revenue", "profit", "results", "q1", "q2", "q3", "q4"),
    "events/guidance": ("guidance", "outlook", "forecast", "guides", "raises",
                        "lowers", "warns"),
    "analyst": ("upgrade", "downgrade", "analyst", "price target", "initiates",
                "reiterates", "overweight", "underweight", "rating"),
    "positioning": ("stake", "13d", "13g", "activist", "institutional",
                    "short interest", "insider", "hedge fund"),
    "price": ("rally", "plunge", "slides", "surges", "52-week", "gains",
              "falls", "jumps", "drops", "tumbles", "soars"),
    "options": ("options", "calls", "puts", "implied volatility", "unusual"),
    "events/corporate_action": ("merger", "acquisition", "acquires", "split",
                                "dividend", "buyback", "spin-off", "offering",
                                "ceo", "cfo", "resigns", "appoints"),
    "events/regulatory": ("fda", "sec ", "lawsuit", "settlement", "approval",
                          "investigation", "recall", "subpoena", "antitrust"),
    "accounting": ("restatement", "impairment", "writedown", "goodwill",
                   "accrual"),
}


def classify_family(texts: Sequence[str]) -> tuple[str, dict]:
    """Mechanical family assignment from member text. No model, no outcome.

    Ties break toward `events/other`, which is the honest label for a cluster
    whose vocabulary matches nothing declared -- and those are the ones worth
    reading.
    """
    hits = {f: 0 for f in FAMILY_LEXICON}
    for t in texts:
        low = (t or "").lower()
        for f, words in FAMILY_LEXICON.items():
            if any(w in low for w in words):
                hits[f] += 1
    n = max(1, len(texts))
    share = {f: c / n for f, c in hits.items()}
    best = max(share, key=lambda f: share[f])
    if share[best] < 0.30:
        return "events/other", share
    return best, share


@dataclass(frozen=True)
class TypedHypothesis:
    """What an archetype emits.

    Every field is declared BEFORE any return is computed, and
    `prospectively_declared` says so in a field the corpse comparator reads.
    """
    hypothesis_id: str
    archetype_id: str
    family: str
    precursor: dict
    direction: str                 # LONG | SHORT | TWO_SIDED
    direction_source: str
    horizon_days: int
    proposed_action: str
    default_action: str
    declared_scope: str
    n_members: int
    member_ids: tuple[str, ...]
    label: str
    label_source: str
    top_terms: tuple[str, ...]
    prospectively_declared: bool = True
    rank_rule: str = "archetype size, descending -- fixed before grading"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["member_ids"] = list(self.member_ids[:25])
        d["n_member_ids_shown"] = min(25, len(self.member_ids))
        d["top_terms"] = list(self.top_terms)
        return d


def emit_hypothesis(*, archetype_id: str, texts: Sequence[str],
                    member_ids: Sequence[str], horizon_days: int,
                    label: str, label_source: str, terms: Sequence[str],
                    direction: str = "TWO_SIDED",
                    direction_source: str = "declared two-sided (no model)",
                    scope: str = SC.AFFECTED) -> TypedHypothesis:
    """One archetype -> one typed hypothesis.

    THE PRECURSOR IS OBSERVABLE BEFOREHAND, which is the whole research problem
    (the Micron test). The two clauses are:

      * the event belongs to this archetype -- decidable from the event's own
        text at the moment it becomes public; and
      * `days_since_public <= 1` -- the position is opened on information that
        was already public, never on the event's own timestamp.

    Nothing in the precursor reads a forward return, and nothing reads the
    cluster label.
    """
    family, _ = classify_family(texts)
    feature = FAMILY_FEATURE.get(family, FAMILY_FEATURE["events/other"])
    precursor = {"all": [
        {"feature": feature, "op": "in_archetype", "value": archetype_id},
        {"feature": "days_since_public", "op": "<=", "value": 1},
    ]}
    act = ("short_top_quintile_equal_weight" if direction == "SHORT"
           else "long_top_quintile_equal_weight")
    return TypedHypothesis(
        hypothesis_id=f"U-ARCH-{archetype_id}-h{horizon_days}",
        archetype_id=str(archetype_id), family=family, precursor=precursor,
        direction=direction, direction_source=direction_source,
        horizon_days=int(horizon_days), proposed_action=act,
        default_action="hold_market", declared_scope=scope,
        n_members=len(member_ids), member_ids=tuple(member_ids),
        label=label, label_source=label_source, top_terms=tuple(terms))


# -- 4. THE CORPSE ROUTE (U2) ----------------------------------------------

def route_through_corpses(h: TypedHypothesis,
                          corpses: Sequence[SC.Corpse]) -> dict:
    """`research_gym.scope.corpse_check` -- the MECHANISTIC comparator.

    NOT `research_daemon.assert_distinct_from_corpses`, which counts the words
    in a sentence. This one compares rule SHAPES and action pairs, and it names
    the corpse a descendant must carry as a control.

    A second, weaker layer is reported beside it: any corpse sharing a leaf
    FEATURE with this precursor. That layer never blocks; it exists so a reader
    can see the near-misses the shape comparator did not fire on.
    """
    res = SC.corpse_check(precursor=h.precursor,
                          proposed_action=h.proposed_action,
                          default_action=h.default_action,
                          scope=h.declared_scope, corpses=list(corpses),
                          prospectively_declared=h.prospectively_declared)
    mine = {f for f, _ in SC.rule_shape(h.precursor)}
    res["feature_overlap_corpses"] = sorted(
        c.mechanism_id for c in corpses
        if mine & {f for f, _ in SC.rule_shape(c.precursor)})
    # `corpse_check` names ONE parent (`parents[0]`). Which one that is depends
    # on register order, so the full candidate list is reported beside it --
    # otherwise "the parent" reads as a judgement when it is an ordering.
    res["action_pair_corpses"] = sorted(
        c.mechanism_id for c in corpses
        if (c.proposed_action, c.default_action) == (h.proposed_action,
                                                     h.default_action)
        and c.blocks_anything)
    res["admitted"] = res["outcome"] != SC.BLOCKED
    return res


# -- 5. GRADING (the alpha ruler, block-wise) -------------------------------

def _t_and_se(x) -> tuple[float | None, float | None]:
    x = np.asarray([v for v in np.asarray(x, dtype="float64")
                    if np.isfinite(v)], dtype="float64")
    if x.size < 2:
        return None, None
    se = float(x.std(ddof=1) / math.sqrt(x.size))
    return (float(x.mean() / se) if se > 0 else None), se


def _p_from_t(t: float | None, df: int) -> float | None:
    if t is None or df < 1:
        return None
    try:
        from scipy import stats
        return float(2.0 * stats.t.sf(abs(t), df))
    except Exception:                                          # noqa: BLE001
        return float(math.erfc(abs(t) / math.sqrt(2.0)))


def block_grade(*, blocks: Sequence[str], ar: Sequence[float],
                raw: Sequence[float], mkt: Sequence[float],
                beta: Sequence[float], weight: Sequence[float] | None = None,
                horizon_days: int = 5) -> dict:
    """ONE observation per DATE BLOCK. Never one per event.

    `n_effective` counts date blocks (CANON section 58). The event count is
    reported beside it because the gap between them is the whole reason the
    rule exists: pooling name-days once printed t -65 where the block series
    printed -16.6.

    Beta is printed FIRST -- the mean pre-event beta of the events in the
    hypothesis -- because an excess computed against a market the book is not
    beta-matched to is a LOADING, not an alpha (S43).
    """
    import pandas as pd
    n = len(list(ar))
    df = pd.DataFrame({"block": [str(b) for b in blocks],
                       "ar": np.asarray(ar, dtype="float64"),
                       "raw": np.asarray(raw, dtype="float64"),
                       "mkt": np.asarray(mkt, dtype="float64"),
                       "beta": np.asarray(beta, dtype="float64"),
                       "w": (np.ones(n) if weight is None
                             else np.asarray(weight, dtype="float64"))})
    df = df[np.isfinite(df["ar"].to_numpy())]
    if df.empty:
        return {"verdict": "CANNOT_DETERMINE", "why": "no finite rows",
                "n_events": 0, "n_blocks": 0}

    def _wm(g):
        w = g["w"].to_numpy(dtype="float64")
        v = g["ar"].to_numpy(dtype="float64")
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        return float(v.mean()) if w.sum() <= 0 else float((v * w).sum() / w.sum())

    ew = df.groupby("block")["ar"].mean()
    vw = df.groupby("block")[["ar", "w"]].apply(_wm)
    raw_b = df.groupby("block")["raw"].mean()
    mkt_b = df.groupby("block")["mkt"].mean()

    t_ew, se_ew = _t_and_se(ew.to_numpy())
    t_vw, _ = _t_and_se(vw.to_numpy())
    n_blocks = int(ew.size)
    n_eff = float(n_blocks)
    sd = float(ew.std(ddof=1)) if n_blocks > 1 else None
    mde = PW.mde_mean(sd, n_eff) if sd else None
    obs = float(ew.mean())
    agree = (t_ew is not None and t_vw is not None
             and float(np.sign(ew.mean())) == float(np.sign(vw.mean())))
    return {
        "beta_mean_pre_event": (float(np.nanmean(df["beta"].to_numpy()))
                                if np.isfinite(df["beta"].to_numpy()).any()
                                else None),
        "n_events": int(len(df)),
        "n_blocks": n_blocks,
        "n_effective": n_eff,
        "n_effective_basis": "DATE BLOCKS (calendar months with >=1 event)",
        "ar_mean_pp": obs * 100.0,
        "raw_mean_pp": float(raw_b.mean()) * 100.0,
        "mkt_mean_pp": float(mkt_b.mean()) * 100.0,
        "ar_t_ew": t_ew,
        "ar_se_pp": (se_ew * 100.0) if se_ew else None,
        "ar_mean_vw_pp": float(vw.mean()) * 100.0,
        "ar_t_vw": t_vw,
        "ew_vw_sign_agree": bool(agree),
        "ew_vw_flag": None if agree else "EW_VW_DISAGREE",
        "mde_pp": (mde * 100.0) if mde else None,
        "powered_for_observed_effect": bool(mde is not None
                                            and abs(obs) >= mde),
        "p_two_sided": _p_from_t(t_ew, n_blocks - 1),
        "horizon_days": int(horizon_days),
    }


def tail_diagnostics(ar: Sequence[float], blocks: Sequence[str]) -> dict:
    """Check the TAIL before the mean, always.

    Two numbers: the share of the summed abnormal return carried by the top 1%
    of events, and the largest change in the block t from deleting ONE block.
    35 rows of 46,361 once carried 81% of a result here.
    """
    import pandas as pd
    a = np.asarray(ar, dtype="float64")
    b = np.asarray([str(x) for x in blocks])
    ok = np.isfinite(a)
    a, b = a[ok], b[ok]
    out: dict = {"n": int(a.size)}
    if a.size:
        k = max(1, int(math.ceil(0.01 * a.size)))
        order = np.argsort(-np.abs(a))
        tot = float(a.sum())
        out["top1pct_n"] = k
        out["top1pct_share_of_sum"] = (float(a[order[:k]].sum() / tot)
                                       if tot != 0 else None)
    bm = pd.DataFrame({"b": b, "ar": a}).groupby("b")["ar"].mean()
    t0, _ = _t_and_se(bm.to_numpy())
    worst = worst_b = None
    if t0 is not None and bm.size > 3:
        for lab in bm.index:
            t1, _ = _t_and_se(bm.drop(lab).to_numpy())
            if t1 is None:
                continue
            d = abs(t1 - t0)
            if worst is None or d > worst:
                worst, worst_b = d, str(lab)
    out.update({"block_t": t0, "max_abs_t_change_dropping_one_block": worst,
                "most_influential_block": worst_b, "n_blocks": int(bm.size)})
    return out


def paired_block_difference(*, blocks_a: Sequence[str], a: Sequence[float],
                            blocks_b: Sequence[str], b: Sequence[float]) -> dict:
    """EVENT minus MATCHED CONTROL, block by block, paired.

    This is the statistic that actually discriminates, and the one the
    hypothesis lives or dies on. An equal-weighted average of 91 mega-caps has
    a mean abnormal return in most months whether or not anything happened, so
    a positive `ar_mean_pp` on its own is a statement about the names and the
    era. The paired difference against the same names in the same months
    WITHOUT the event removes both.

    Only blocks present on BOTH sides are used, and the count is reported --
    an unpaired block silently dropped is how a paired test stops being paired.
    """
    import pandas as pd
    A = pd.DataFrame({"b": [str(x) for x in blocks_a],
                      "v": np.asarray(a, dtype="float64")})
    B = pd.DataFrame({"b": [str(x) for x in blocks_b],
                      "v": np.asarray(b, dtype="float64")})
    A = A[np.isfinite(A["v"].to_numpy())].groupby("b")["v"].mean()
    B = B[np.isfinite(B["v"].to_numpy())].groupby("b")["v"].mean()
    common = sorted(set(A.index) & set(B.index))
    if len(common) < 2:
        return {"verdict": "CANNOT_DETERMINE", "n_paired_blocks": len(common)}
    d = A.loc[common].to_numpy() - B.loc[common].to_numpy()
    t, se = _t_and_se(d)
    sd = float(np.std(d, ddof=1))
    mde = PW.mde_mean(sd, float(len(common)))
    return {"n_paired_blocks": len(common),
            "n_blocks_event_only": len(set(A.index) - set(B.index)),
            "n_blocks_control_only": len(set(B.index) - set(A.index)),
            "diff_mean_pp": float(d.mean()) * 100.0,
            "diff_t": t, "diff_se_pp": (se * 100.0) if se else None,
            "mde_pp": (mde * 100.0) if mde else None,
            "powered_for_observed_effect": bool(
                mde is not None and abs(float(d.mean())) >= mde),
            "p_two_sided": _p_from_t(t, len(common) - 1),
            "reading": ("event minus the same names in the same months without "
                        "the event; this is the number the hypothesis lives on")}


def era_table(*, eras: Mapping[str, tuple[str, str]], blocks: Sequence[str],
              ar: Sequence[float]) -> dict:
    """Three eras, NEVER pooled.

    A result in one era is a REGIME and is labelled one. The pooled number is
    reported too, and marked as the thing that hides the regime.
    """
    import pandas as pd
    df = pd.DataFrame({"block": [str(b) for b in blocks],
                       "ar": np.asarray(ar, dtype="float64")})
    df = df[np.isfinite(df["ar"].to_numpy())]
    rows = {}
    for name, (lo, hi) in eras.items():
        sub = df[(df["block"] >= lo) & (df["block"] <= hi)]
        if sub.empty:
            rows[name] = {"verdict": "NO_COVERAGE", "n_events": 0}
            continue
        bm = sub.groupby("block")["ar"].mean()
        t, _ = _t_and_se(bm.to_numpy())
        sd = float(bm.std(ddof=1)) if bm.size > 1 else None
        mde = PW.mde_mean(sd, float(bm.size)) if sd else None
        rows[name] = {"n_events": int(len(sub)), "n_blocks": int(bm.size),
                      "mean_pp": float(bm.mean()) * 100.0, "t": t,
                      "mde_pp": (mde * 100.0) if mde else None,
                      "p_two_sided": _p_from_t(t, int(bm.size) - 1)}
    signs = [float(np.sign(r["mean_pp"])) for r in rows.values()
             if r.get("mean_pp") is not None]
    sig = [n for n, r in rows.items()
           if r.get("p_two_sided") is not None and r["p_two_sided"] <= 0.05]
    # A block that falls in NO declared era is invisible to the era table and
    # visible in the pooled number. Counting it is the difference between a
    # partition and three filters that happen not to overlap.
    covered = np.zeros(len(df), dtype=bool)
    for lo, hi in eras.values():
        covered |= ((df["block"] >= lo) & (df["block"] <= hi)).to_numpy()
    return {"eras": rows, "n_eras_with_coverage": len(signs),
            "n_events_outside_every_declared_era": int((~covered).sum()),
            "blocks_outside_every_declared_era": sorted(
                set(df.loc[~covered, "block"].tolist())),
            "same_sign_in_all_covered": bool(signs and len(set(signs)) == 1),
            "eras_significant_uncorrected": sig,
            "reading": ("one era significant and the others not is a REGIME, "
                        "not a finding; the pooled number hides it")}


def family_correction(p_by_id: Mapping[str, float], *,
                      family_size: int) -> dict:
    """SCREEN = BH-FDR, EXPORT = Holm, both reported (CANON section 63).

    `family_size` is declared and asserted: the correction is over the family
    the search was run in, not over the subset that happened to look good.
    """
    from backend.strategy import verdict as V
    got = len([p for p in p_by_id.values()
               if p is not None and np.isfinite(float(p))])
    both = V.screen_then_export(dict(p_by_id))
    both["declared_family_size"] = int(family_size)
    both["p_values_supplied"] = got
    both["family_size_matches_declaration"] = bool(got == family_size)
    if got != family_size:
        both["warning"] = (
            f"declared family = {family_size} but {got} finite p-values were "
            f"supplied; the correction below is over {got}. A family that "
            f"shrinks after the results are seen is not a family.")
    return both


# -- 6. U3 -- THE KNOWN-ANSWER GATE ----------------------------------------

@dataclass(frozen=True)
class PlantedFamily:
    """A synthetic event family with a DECLARED drift, planted before anything
    is clustered.

    `drift` of 0.0 is the null family, and the null is not an afterthought: a
    pipeline that finds the planted edge and ALSO finds an edge in the null has
    told you nothing.

    TWO MODES, AND THE CHOICE IS NOT COSMETIC
    =========================================
    `vocabulary` plants a bag of rare tokens -- fine for the hashing embedder,
    which sees tokens. `templates` plants realistic, semantically coherent
    headlines -- and it is the ONLY honest mode for a language-model embedder.

    Measured 2026-09-08 on the real corpus: with two rare-token vocabularies,
    `nemotron-3-embed-1b` put BOTH planted families into ONE cluster of exactly
    800 (purity 0.50 each) and no real headline joined it. The embedder had
    separated *register* -- "this is not a financial headline" -- and was blind
    to which nonsense vocabulary a row came from, because to a language model
    two piles of unrelated rare words are the same thing. The gate correctly
    reported FAILED; what failed was the plant.
    """
    name: str
    vocabulary: tuple[str, ...]
    n_events: int
    drift: float
    seed: int
    templates: tuple[str, ...] = ()


#: Filler shared by BOTH families, so the only thing separating them is the
#: template's meaning -- not a private vocabulary the embedder could key on.
_FILLER_SUBJECTS = ("The company", "The group", "The manufacturer",
                    "The issuer", "The firm")
_FILLER_TAILS = ("according to a statement", "the company said",
                 "in a filing on Tuesday", "people familiar said",
                 "per a press release", "the statement added")


def plant_family(fam: PlantedFamily, *, n_blocks: int = 36,
                 block_labels: Sequence[str] | None = None) -> dict:
    """Build the synthetic rows, spread across blocks, each carrying `drift`."""
    rng = np.random.default_rng(fam.seed)
    labels = (list(block_labels) if block_labels is not None
              else [f"B{i:03d}" for i in range(n_blocks)])
    titles, blocks, ids = [], [], []
    if fam.templates:
        tpl = np.array(list(fam.templates))
        subj = np.array(_FILLER_SUBJECTS)
        tail = np.array(_FILLER_TAILS)
        for i in range(fam.n_events):
            t = str(rng.choice(tpl))
            t = t.replace("{co}", str(rng.choice(subj)))
            t = t.replace("{n}", f"{int(rng.integers(2, 900)) * 1000:,}")
            titles.append(f"{t}, {rng.choice(tail)}")
            blocks.append(labels[int(rng.integers(len(labels)))])
            ids.append(f"{fam.name}-{i:05d}")
    else:
        vocab = np.array(list(fam.vocabulary))
        for i in range(fam.n_events):
            k = int(rng.integers(3, min(6, vocab.size)))
            words = rng.choice(vocab, size=k, replace=False)
            titles.append(" ".join(words.tolist()))
            blocks.append(labels[int(rng.integers(len(labels)))])
            ids.append(f"{fam.name}-{i:05d}")
    return {"family": fam.name, "event_ids": ids, "titles": titles,
            "blocks": blocks, "drift": float(fam.drift), "n": fam.n_events,
            "mode": "templates" if fam.templates else "vocabulary"}


def drift_for_multiple_of_mde(sd_block: float, n_blocks: int,
                              multiple: float = 2.0) -> float:
    """Plant at a DECLARED multiple of an MDE computed from the noise.

    Never at a number chosen because it worked. The multiple is stated in the
    receipt beside the MDE it was derived from.
    """
    mde = PW.mde_mean(float(sd_block), float(n_blocks))
    return float(multiple * (mde or 0.0))


def plant_drift(event_sd: float, n_events: int, *,
                multiple: float = 3.0) -> dict:
    """The MDE that matters is the PLANTED CLUSTER'S OWN, not the corpus's.

    A first version of this gate sized the plant against the whole corpus's
    block-mean sd and then failed on a -3 sigma noise draw, because the planted
    cluster has far fewer events per block and therefore a much larger block
    sd. The corpus MDE is the wrong denominator; the cluster's is

        mde = (z_alpha + z_power) * event_sd / sqrt(n_events)

    which is what `mde_mean` reduces to once the block-mean sd is written out.
    Reported as a dict so the receipt carries the MDE the plant was sized
    against, not only the drift that came out of it.
    """
    mde = (PW.Z_ALPHA_TWO_SIDED_05 + PW.Z_POWER_80) * float(event_sd) / math.sqrt(
        max(1, int(n_events)))
    return {"event_sd": float(event_sd), "n_events": int(n_events),
            "cluster_mde": float(mde), "multiple": float(multiple),
            "drift": float(multiple * mde),
            "basis": "(z_alpha+z_power) * event_sd / sqrt(n_events)"}


def known_answer(*, embed: Callable[[Sequence[str]], np.ndarray],
                 planted: dict, null: dict, background_titles: Sequence[str],
                 background_blocks: Sequence[str],
                 background_ar: Sequence[float], k: int, seed: int = 0,
                 purity_floor: float = 0.80, horizon_days: int = 5,
                 declared_family_size: int | None = None) -> dict:
    """U3 END TO END: cluster -> emit -> grade, on a corpus with a planted
    family and a planted null in it.

    PASSES only if all four hold:

      1. the planted family is RECOVERED by clustering -- some cluster is
         >= `purity_floor` planted members and holds >= `purity_floor` of them;
      2. the same is true of the NULL family (it must be FOUND, so that its
         null verdict is about the drift and not about the clustering);
      3. the planted hypothesis is separated from zero AFTER family correction
         and clears its own MDE;
      4. the null hypothesis does NOT survive the screen.

    Condition 2 is the one that is easy to leave out and it is the one that
    makes the gate mean something: a pipeline that cannot see the null family
    at all would "pass" 1, 3 and 4 by accident.
    """
    ids = ([f"BG-{i:06d}" for i in range(len(background_titles))]
           + list(planted["event_ids"]) + list(null["event_ids"]))
    titles = list(background_titles) + list(planted["titles"]) + list(null["titles"])
    blocks = list(background_blocks) + list(planted["blocks"]) + list(null["blocks"])
    rng = np.random.default_rng(seed + 7)
    bg_ar = list(background_ar)
    sd = float(np.std(bg_ar, ddof=1)) if len(bg_ar) > 1 else 0.02
    p_noise = rng.normal(0.0, sd, size=planted["n"])
    n_noise = rng.normal(0.0, sd, size=null["n"])
    ar = (bg_ar + (p_noise + planted["drift"]).tolist()
          + (n_noise + null["drift"]).tolist())
    # A -3 sigma noise draw is a fact about this run, not a mystery. Report the
    # realised planted mean beside the target so a near-miss is readable.
    realised = {"planted_target_pp": planted["drift"] * 100.0,
                "planted_realised_pp": float(np.mean(p_noise) + planted["drift"]) * 100.0,
                "planted_noise_mean_in_se": float(
                    np.mean(p_noise) / (sd / math.sqrt(max(1, planted["n"])))),
                "null_realised_pp": float(np.mean(n_noise) + null["drift"]) * 100.0,
                "event_sd": float(sd)}
    truth = ([""] * len(background_titles) + [planted["family"]] * planted["n"]
             + [null["family"]] * null["n"])

    X = embed(titles)
    lab = np.asarray(kmeans(X, k, seed=seed)[0])

    def recover(fam: str) -> dict:
        """Best achievable cluster-matching F1 for this family.

        A family recovered as several clusters is still recovered, and a family
        that needs half the corpus to reach full recall is not. Clusters are
        added greedily in descending precision and the union's F1 is tracked;
        the criterion is the MAXIMUM F1 over that path, which is the standard
        cluster-matching score and is not a knob.

        The earlier criterion -- "the union of clusters that are individually
        >= purity_floor pure" -- is scale-dependent in a way that quietly
        measures k: at a fine k no single cluster of a 400-member family need
        be 80% pure even though the family is perfectly concentrated. Both the
        F1 path and the per-cluster table are reported so a reader can see
        which of the two is doing the work.
        """
        want = np.array([t == fam for t in truth])
        cand = []
        for c in np.unique(lab):
            m = lab == c
            if not m.any():
                continue
            cand.append({"cluster": int(c),
                         "purity": float((want & m).sum() / m.sum()),
                         "n_family_in_cluster": int((want & m).sum()),
                         "size": int(m.sum())})
        cand.sort(key=lambda r: (-r["purity"], -r["n_family_in_cluster"]))
        best = {"f1": 0.0, "clusters": [], "purity": 0.0, "recall": 0.0,
                "size": 0}
        chosen, hit, tot = [], 0, int(want.sum())
        for r in cand:
            chosen.append(r["cluster"])
            hit += r["n_family_in_cluster"]
            size = sum(x["size"] for x in cand
                       if x["cluster"] in set(chosen))
            prec = hit / max(1, size)
            rec_ = hit / max(1, tot)
            f1 = 0.0 if (prec + rec_) == 0 else 2 * prec * rec_ / (prec + rec_)
            if f1 > best["f1"]:
                best = {"f1": float(f1), "clusters": list(chosen),
                        "purity": float(prec), "recall": float(rec_),
                        "size": int(size)}
        best["cluster"] = best["clusters"][0] if best["clusters"] else int(
            cand[0]["cluster"])
        if not best["clusters"]:
            best["clusters"] = [best["cluster"]]
        best["n_clusters_used"] = len(best["clusters"])
        best["per_cluster"] = cand[:12]
        best["criterion"] = f"best cluster-matching F1 >= {purity_floor}"
        best["recovered"] = bool(best["f1"] >= purity_floor)
        return best

    rec_p, rec_n = recover(planted["family"]), recover(null["family"])

    def grade(clusters) -> dict:
        w = np.where(np.isin(lab, list(np.atleast_1d(clusters))))[0]
        sub_ar = [ar[i] for i in w]
        sub_b = [blocks[i] for i in w]
        g = block_grade(blocks=sub_b, ar=sub_ar, raw=sub_ar,
                        mkt=[0.0] * len(w), beta=[1.0] * len(w),
                        horizon_days=horizon_days)
        g["tail"] = tail_diagnostics(sub_ar, sub_b)
        return g

    gp, gn = grade(rec_p["clusters"]), grade(rec_n["clusters"])
    ps = {"planted": gp.get("p_two_sided"), "null": gn.get("p_two_sided")}
    fam_n = int(declared_family_size or max(2, int(np.unique(lab).size)))
    used = set(rec_p["clusters"]) | set(rec_n["clusters"])
    for c in np.unique(lab):
        if len(ps) >= fam_n:
            break
        if int(c) in used:
            continue
        ps[f"cluster_{int(c)}"] = grade([int(c)]).get("p_two_sided")
    corr = family_correction(ps, family_size=len(ps))

    holm = corr["export_holm"].get("adjusted", {})
    checks = {
        "planted_family_clustered": bool(rec_p["recovered"]),
        "null_family_clustered": bool(rec_n["recovered"]),
        "planted_separated_after_holm": bool(
            holm.get("planted", 1.0) <= 0.05
            and gp.get("powered_for_observed_effect")),
        "null_reads_noise": bool(
            "null" not in corr["screen_bh_fdr"].get("survivors", [])),
    }
    sizes = np.bincount(lab, minlength=int(np.max(lab)) + 1)
    return {"gate": "U3_KNOWN_ANSWER", "k": int(k), "seed": int(seed),
            "n_rows": len(titles), "n_ids": len(ids), "checks": checks,
            "recoverability_arithmetic": {
                "planted_share_of_corpus": planted["n"] / max(1, len(titles)),
                "mean_cluster_size": float(len(titles) / max(1, int(
                    np.unique(lab).size))),
                "largest_cluster": int(sizes.max()),
                "smallest_nonempty_cluster": int(sizes[sizes > 0].min()),
                "note": ("a family of n events can only reach purity_floor if "
                         "k is fine enough for a cluster of about n to exist; "
                         "a failed recovery at a coarse k is a statement about "
                         "k, not about the embedder")},
            "plant_mode": planted.get("mode"),
            "passed": all(checks.values()),
            "planted_recovery": rec_p, "null_recovery": rec_n,
            "planted_grade": gp, "null_grade": gn, "family_correction": corr,
            "planted_drift_pp": planted["drift"] * 100.0,
            "null_drift_pp": null["drift"] * 100.0,
            "realised_plant": realised,
            "note": ("a discovery pipeline that has never recovered a planted "
                     "answer is not evidence of anything")}
