"""JOB3 (2026-09-29 night): LLM theories measured fairly -- SIZE and conditional questions,
post-cutoff, blinded, no tools, forced probabilities, proper scoring against free baselines.

Not a repeat of the closed rows in docs/WHAT_WE_ALREADY_KNOW_LLM.md: bare direction (AMNESIA-2,
X2 blind), headline-level size buckets (world digest 09-29), zero-shot size buckets vs the vol
prior (ft_lab 09-29). Here the model gets a BINARY conditional question with a threshold scaled
to the name's own volatility, a PAIRWISE comparison on the same date, a NUMBERS arm that is
graded against the numbers alone, and several samples per item.

Questions
  Q1   P(|next-session open-to-close move minus SPY's| > the name's trailing 21-session mean
       |abnormal move|).  "event" = y > vol21_absx.
  Q2   two blinded companies with news on the SAME entry date: P(A's absolute move > B's).
Arms (provider x information)
  text     blinded news only
  num      blinded news + the numbers (trailing vol, sd21/sd63, last move, liquidity, news
           counts, and the numbers-model probability L_T2)
  id       canary: name the company from the blinded text, or UNKNOWN
Baselines (fitted on the TRAIN block only; the whole panel, not the LLM sample)
  base     train base rate of the event
  L_B1     logistic on trailing priors ("vol prior")
  L_T2     logistic on trailing priors + news counts + (T2 TF-IDF forecast - log vol) ("the numbers")

Run (project interpreter):
  python -m scripts.hyp_llm_theories declare --run RUN
  python -m scripts.hyp_llm_theories run --run RUN --provider deepseek --q q1 --arm text --split test
  python -m scripts.hyp_llm_theories analyze --run RUN
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "backend" / "data" / "optimus" / "hyp_lab"
CELLS = ROOT / "ft_lab" / "data" / "cells.parquet"
PREDS = ROOT / "ft_lab" / "data" / "preds_baselines.parquet"
SEED = 20260930
CAP_USD = 2.40
CODE = "Company X"

PRIOR_TRAILING = ["l_vol21_absx", "l_sd21_cc", "l_sd63_cc", "l_last_absx", "l_dv21"]
META = ["l_n_docs", "l_n_sources", "pre_bell"]

# ---------------------------------------------------------------- prompts
SYS_Q1_TEXT = (
    "You forecast the SIZE (not the direction) of a stock's next move from one news item. "
    "The company's name and ticker are replaced by 'Company X'. You have no tools. "
    "Question: will Company X's move from the next session's open to its close, measured "
    "relative to the S&P 500 and in absolute value, be LARGER than its own typical daily move "
    "over the past month? Historically this happens about {base:.0%} of the time for stocks "
    "with news. Reply with ONLY a JSON object: {{\"p\": <probability 0 to 1>}}.")
SYS_Q1_NUM = (
    "You forecast the SIZE (not the direction) of a stock's next move from one news item and "
    "some numbers. The company's name and ticker are replaced by 'Company X'. You have no tools. "
    "Question: will Company X's move from the next session's open to its close, measured "
    "relative to the S&P 500 and in absolute value, be LARGER than its typical daily move "
    "(given below)? Historically this happens about {base:.0%} of the time for stocks with news. "
    "A statistical model that reads the same numbers and a bag-of-words of the text gives the "
    "probability shown as 'model probability'; you may agree with it or move away from it if "
    "the news justifies it. Reply with ONLY a JSON object: {{\"p\": <probability 0 to 1>}}.")
SYS_Q2_TEXT = (
    "Two different companies had news before the same trading session. Names and tickers are "
    "replaced by 'Company A' and 'Company B'. You have no tools. Question: which stock will move "
    "MORE in absolute value, relative to the S&P 500, from that session's open to its close? "
    "Reply with ONLY a JSON object: {\"p_a\": <probability 0 to 1 that Company A moves more>}.")
SYS_Q2_NUM = (
    "Two different companies had news before the same trading session. Names and tickers are "
    "replaced by 'Company A' and 'Company B'. You have no tools. Question: which stock will move "
    "MORE in absolute value, relative to the S&P 500, from that session's open to its close? "
    "Each company's typical daily move and other numbers are given. Reply with ONLY a JSON "
    "object: {\"p_a\": <probability 0 to 1 that Company A moves more>}.")
SYS_ID = (
    "The company in this news item has been anonymised as 'Company X'. If you can tell which "
    "real company it is, give its name and ticker; otherwise say UNKNOWN. Do not guess wildly. "
    "Reply with ONLY a JSON object: {\"company\": \"<name or UNKNOWN>\", \"ticker\": \"<ticker or UNKNOWN>\"}.")


def numbers_block(r) -> str:
    return (f"Typical daily move (21-session mean |move vs S&P 500|): {r.vol21_absx * 100:.2f}%\n"
            f"Daily volatility, 21 sessions: {r.sd21_cc * 100:.2f}%; 63 sessions: {r.sd63_cc * 100:.2f}%\n"
            f"Last session's |move vs S&P 500|: {r.last_absx * 100:.2f}%\n"
            f"Median daily dollar volume, 21 sessions: ${r.dv21 / 1e6:,.1f}M\n"
            f"News items about it for this session: {int(r.n_docs)} from {int(r.n_sources)} sources; "
            f"published before the open: {'yes' if r.pre_bell else 'no'}\n"
            f"Model probability that the move exceeds the typical move: {r.p_LT2:.2f}")


# ---------------------------------------------------------------- blinding
def blind(text: str, symbol: str, title: str | None, code: str = CODE) -> tuple[str, list]:
    from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
    al = X2.name_aliases(symbol, title)
    out = X2.blind_text(text, al, code)
    return out, X2.leaks(out, al)


def identified(answer: dict | None, symbol: str, title: str | None) -> bool:
    """A canary answer names the right company: ticker equal, or an alias inside the name."""
    if not isinstance(answer, dict):
        return False
    tk = str(answer.get("ticker") or "").upper().strip()
    if tk and tk == symbol.upper():
        return True
    from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
    name = str(answer.get("company") or "").lower()
    if not name or "unknown" in name:
        return False
    return any(len(a) >= 4 and a.lower() in name for a in X2.name_aliases(symbol, title)[1:])


# ---------------------------------------------------------------- numbers models
def _logit_fit(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
    from sklearn.preprocessing import StandardScaler  # noqa: PLC0415
    sc = StandardScaler().fit(X)
    m = LogisticRegression(C=1.0, max_iter=500).fit(sc.transform(X), y)
    return lambda Z: m.predict_proba(sc.transform(Z))[:, 1]


def load_panel() -> pd.DataFrame:
    c = pd.read_parquet(CELLS)
    p = pd.read_parquet(PREDS, columns=["symbol", "entry_date", "T2_trailing_meta_tfidf"])
    c = c.merge(p, on=["symbol", "entry_date"], how="inner")
    c = c[c["split"].isin(["train", "val", "test"])].reset_index(drop=True)
    c["event"] = (c["y"] > c["vol21_absx"]).astype(int)
    c["t2_rel"] = c["T2_trailing_meta_tfidf"] - c["l_vol21_absx"]
    tr = c["split"] == "train"
    f_b1 = _logit_fit(c.loc[tr, PRIOR_TRAILING].values, c.loc[tr, "event"].values)
    f_t2 = _logit_fit(c.loc[tr, PRIOR_TRAILING + META + ["t2_rel"]].values, c.loc[tr, "event"].values)
    c["p_LB1"] = f_b1(c[PRIOR_TRAILING].values)
    c["p_LT2"] = f_t2(c[PRIOR_TRAILING + META + ["t2_rel"]].values)
    c["p_base"] = float(c.loc[tr, "event"].mean())
    return c


def sample_cells(c: pd.DataFrame, split: str, n: int, seed: int, titles: dict) -> pd.DataFrame:
    """Stratified by week; tickers >= 3 letters with an SEC title (so the mask has a name to
    remove); cells whose blinded text still leaks an alias are dropped, never repaired."""
    s = c[(c["split"] == split) & (c["symbol"].str.len() >= 3)
          & c["symbol"].map(lambda x: x in titles)].copy()
    rng = np.random.default_rng(seed)
    weeks = sorted(s["week"].unique())
    per = int(math.ceil(1.6 * n / len(weeks)))
    parts = []
    for w in weeks:
        g = s[s["week"] == w]
        parts.append(g.iloc[rng.choice(len(g), size=min(per, len(g)), replace=False)])
    s = pd.concat(parts)
    s = s.iloc[rng.permutation(len(s))]
    keep = []
    for r in s.itertuples():
        bt, lk = blind(r.text, r.symbol, titles.get(r.symbol))
        if not lk:
            keep.append((r.Index, bt))
        if len(keep) >= n:
            break
    out = s.loc[[k for k, _ in keep]].copy()
    out["btext"] = [b for _, b in keep]
    out["key"] = out["symbol"] + "|" + out["entry_date"]
    return out


def make_pairs(s: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for d, g in s.groupby("entry_date"):
        idx = list(g.index)
        rng.shuffle(idx)
        for i in range(0, len(idx) - 1, 2):
            a, b = s.loc[idx[i]], s.loc[idx[i + 1]]
            if a["symbol"] == b["symbol"]:
                continue
            rows.append({"key": a["key"] + "~" + b["key"], "entry_date": d, "week": a["week"],
                         "month": a["month"], "a": a["key"], "b": b["key"],
                         "a_more": int(a["y"] > b["y"]),
                         "vol_a_higher": int(a["vol21_absx"] > b["vol21_absx"]),
                         "t2_diff": float(a["T2_trailing_meta_tfidf"] - b["T2_trailing_meta_tfidf"])})
    p = pd.DataFrame(rows)
    return p.iloc[rng.permutation(len(p))[:n]].reset_index(drop=True)


def pair_numbers_model(c: pd.DataFrame, seed: int):
    """Logistic of P(A moves more) on the T2 forecast difference, fitted on TRAIN-block pairs."""
    tr = c[c["split"] == "train"]
    rng = np.random.default_rng(seed)
    rows = []
    for _, g in tr.groupby("entry_date"):
        if len(g) < 2:
            continue
        ix = rng.permutation(len(g))
        g = g.iloc[ix]
        k = len(g) // 2
        a, b = g.iloc[:k], g.iloc[k:2 * k]
        rows.append(np.c_[a["T2_trailing_meta_tfidf"].values - b["T2_trailing_meta_tfidf"].values,
                          (a["y"].values > b["y"].values).astype(int)])
    m = np.vstack(rows)
    f = _logit_fit(m[:, :1], m[:, 1].astype(int))
    return lambda d: f(np.asarray(d, dtype=float).reshape(-1, 1))


# ---------------------------------------------------------------- scoring
def block_stats(per_row: pd.Series, dates: pd.Series) -> dict:
    """Mean of per-row values with SE over weekly blocks of the entry date (dates -> date means
    -> week means). MDE = 2.8 x SE."""
    df = pd.DataFrame({"v": per_row.values, "d": pd.to_datetime(dates.values)}).dropna()
    if df.empty:
        return {"mean": None, "se": None, "t": None, "mde": None, "n": 0, "n_blocks": 0}
    dm = df.groupby("d")["v"].mean()
    wk = dm.groupby(dm.index.to_period("W-FRI")).mean()
    nb = len(wk)
    se = float(wk.std(ddof=1) / math.sqrt(nb)) if nb > 1 else None
    m = float(df["v"].mean())
    return {"mean": round(m, 5), "se": None if se is None else round(se, 5),
            "t": None if not se else round(m / se, 2), "mde": None if se is None else round(2.8 * se, 5),
            "n": int(len(df)), "n_blocks": int(nb)}


def brier(p, y) -> np.ndarray:
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def auc(p, y) -> float | None:
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return None
    from sklearn.metrics import roc_auc_score  # noqa: PLC0415
    return round(float(roc_auc_score(y, p)), 4)


def ece(p, y, bins: int = 10) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    e = np.minimum((p * bins).astype(int), bins - 1)
    tot = 0.0
    for b in range(bins):
        m = e == b
        if m.any():
            tot += m.mean() * abs(p[m].mean() - y[m].mean())
    return round(float(tot), 4)


def score_binary(df: pd.DataFrame, pcol: str, ycol: str, refs: list[str]) -> dict:
    out = {"n": int(len(df)), "brier": round(float(brier(df[pcol], df[ycol]).mean()), 5),
           "auc": auc(df[pcol], df[ycol]), "ece": ece(df[pcol], df[ycol]),
           "mean_p": round(float(df[pcol].mean()), 4), "sd_p": round(float(df[pcol].std()), 4),
           "base_rate_in_sample": round(float(df[ycol].mean()), 4)}
    for r in refs:
        diff = pd.Series(brier(df[r], df[ycol]) - brier(df[pcol], df[ycol]), index=df.index)
        st = block_stats(diff, df["entry_date"])
        ref_b = float(brier(df[r], df[ycol]).mean())
        st["bss"] = round(1 - out["brier"] / ref_b, 4) if ref_b > 0 else None
        st["ref_brier"] = round(ref_b, 5)
        by_m = diff.groupby(df["month"].values).mean()
        st["by_month"] = {k: round(float(v), 5) for k, v in by_m.items()}
        out[f"vs_{r}"] = st
    return out


# ---------------------------------------------------------------- IO
def run_dir(run: str) -> Path:
    d = OUT / f"job3_{run}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def done_keys(path: Path) -> set:
    if not path.exists():
        return set()
    s = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("parsed"):
            s.add((r["key"], r.get("sample", 0)))
    return s


def parse_prob(text: str | None, field: str) -> float | None:
    from backend.services.hyp_llm import parse_json  # noqa: PLC0415
    o = parse_json(text)
    if not isinstance(o, dict) or field not in o:
        return None
    try:
        v = float(o[field])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= v <= 1.0) or math.isnan(v):
        return None
    return v


# ---------------------------------------------------------------- stages
def stage_declare(run: str, n_q1: int, n_q2: int, n_sc: int, n_val: int) -> dict:
    from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
    titles = X2.load_titles()
    c = load_panel()
    test = sample_cells(c, "test", n_q1, SEED, titles)
    val = sample_cells(c, "val", n_val, SEED + 1, titles)
    q2pool = sample_cells(c, "test", 3 * n_q2, SEED + 2, titles)
    pairs = make_pairs(q2pool, n_q2, SEED + 3)
    pm = pair_numbers_model(c, SEED + 4)
    pairs["p_pairnum"] = pm(pairs["t2_diff"].values)
    d = run_dir(run)
    cols = ["key", "symbol", "entry_date", "week", "month", "split", "btext", "y", "event",
            "vol21_absx", "sd21_cc", "sd63_cc", "last_absx", "dv21", "n_docs", "n_sources", "pre_bell",
            "p_base", "p_LB1", "p_LT2", "T2_trailing_meta_tfidf"]
    test[cols].to_parquet(d / "items_test.parquet", index=False)
    val[cols].to_parquet(d / "items_val.parquet", index=False)
    q2pool[cols].to_parquet(d / "items_q2pool.parquet", index=False)
    pairs.to_parquet(d / "pairs_test.parquet", index=False)
    tr = c[c["split"] == "train"]
    decl = {
        "job": "hyp_llm_theories JOB3", "run": run, "licence": "PRODUCT_EXPERIMENT",
        "declared_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "before_any_model_call": True,
        "data": {"cells": str(CELLS.relative_to(ROOT)), "preds": str(PREDS.relative_to(ROOT)),
                 "post_cutoff": "test block 2026-05-15..2026-09-28; DeepSeek measured cutoff 2025-12 (X2 probe); "
                                "Qwen2.5-7B cutoff earlier. The val block (2026-01-16..04-30) is also post-cutoff "
                                "and is used ONLY to fit the stacking/Platt maps for arm (b)."},
        "sample": {"seed": SEED, "q1_test_cells": int(len(test)), "val_cells": int(len(val)),
                   "q2_pairs": int(len(pairs)), "self_consistency_cells": n_sc, "stratified_by": "week",
                   "filters": "ticker >= 3 letters, SEC title present, blinded text leak-free (X2.leaks) else dropped"},
        "event": "y > vol21_absx (|open-to-close minus SPY| > the name's trailing 21-session mean |abnormal move|)",
        "train_base_rate": round(float(tr["event"].mean()), 4),
        "test_sample_event_rate": round(float(test["event"].mean()), 4),
        "arms": {"q1_text": ["deepseek", "local"], "q1_num": ["deepseek", "local"],
                 "q2_text": ["deepseek", "local"], "q2_num": ["deepseek"],
                 "q1_text_selfconsistency": "deepseek k=5 at T=0.7 on the first n_sc test cells; plus DeepSeek+local mean",
                 "id_canary": ["deepseek", "local"], "temperature_single": 0.0},
        "baselines": {"p_base": "train base rate", "p_LB1": "logistic on trailing priors (vol prior), train",
                      "p_LT2": "logistic on trailing priors + news counts + T2 TF-IDF rel forecast, train",
                      "p_pairnum": "logistic on T2 difference, train-block pairs", "vol_a_higher": "heuristic"},
        "metrics": "Brier, BSS, AUC, ECE; paired per-row Brier difference (ref - arm) with SE over weekly blocks of "
                   "entry dates; MDE = 2.8 SE; by month",
        "verdict_rules": {
            "q1_text": "SKILL_OVER_VOL_PRIOR if Brier improvement vs p_LB1 > 0 with t >= 2; FAILED_VARIANT if mean <= 0 "
                       "and MDE <= 0.01; else CANNOT_DISTINGUISH. (vs p_base reported.)",
            "q1_num_b": "LLM_ADDS if stack(L_T2 logit, LLM logit) Platt-fitted on the val sample beats L_T2 "
                        "recalibrated on the same val sample, on test, t >= 2; FAILED_VARIANT if mean <= 0 and "
                        "MDE <= 0.005; else CANNOT_DISTINGUISH. Raw LLM-num vs p_LT2 also reported.",
            "q2": "SKILL if accuracy - 0.5 > 0 with t >= 2 AND Brier beats p_pairnum with t >= 2 for 'adds'; "
                  "otherwise as above.",
            "sc_c": "SC_HELPS if Brier(mean of k) < Brier(single sample 1) with t >= 2; else CANNOT_DISTINGUISH / FAILED_VARIANT.",
            "leak": "an arm whose identified share > 10% reports its metrics split by identified / not; a skill that "
                    "lives only in identified rows is not credited.",
            "scale_rule": "scale an arm beyond the first sample only if its point estimate beats its reference"},
        "cost_estimate_usd": "about 0.6-0.9 DeepSeek at peak list price; local $0; cap 2.40 via hyp_llm",
        "closed_not_repeated": ["AMNESIA-2 direction", "X2 blind direction/range", "world digest headline size buckets",
                                "ft_lab zero-shot size buckets vs vol prior"],
    }
    decl["sha256"] = hashlib.sha256(json.dumps(decl, sort_keys=True).encode()).hexdigest()
    p = OUT / f"job3_declaration_{run}.json"
    p.write_text(json.dumps(decl, indent=1), encoding="utf-8")
    return decl


def _user_q1(r, arm: str) -> str:
    u = f"News about Company X:\n{r.btext}"
    if arm == "num":
        u += "\n\nNumbers (known before the session opens):\n" + numbers_block(r)
    return u


def _user_q2(a, b, arm: str) -> str:
    u = f"Company A news:\n{a.btext}\n\nCompany B news:\n{b.btext}"
    if arm == "num":
        u += ("\n\nCompany A numbers:\n" + numbers_block(a).replace("Model probability that the move exceeds the typical move",
                                                                      "Model probability A exceeds its own typical move")
              + "\n\nCompany B numbers:\n" + numbers_block(b).replace("Model probability that the move exceeds the typical move",
                                                                      "Model probability B exceeds its own typical move"))
    return u


def stage_run(run: str, provider: str, q: str, arm: str, split: str, limit: int, k: int, temp: float,
              workers: int) -> dict:
    from backend.services import hyp_llm as H  # noqa: PLC0415
    d = run_dir(run)
    stop_file = d / "STOP"
    tag = f"{q}_{arm}_{provider}_{split}" + (f"_k{k}_t{temp}" if k > 1 else "")
    out_path = d / f"rows_{tag}.jsonl"
    done = done_keys(out_path)
    base = json.loads((OUT / f"job3_declaration_{run}.json").read_text())["train_base_rate"]
    jobs = []
    if q in ("q1", "id"):
        items = pd.read_parquet(d / f"items_{split}.parquet").head(limit)
        for r in items.itertuples():
            for s in range(k):
                if (r.key, s) not in done:
                    jobs.append((r, None, s))
    else:
        pairs = pd.read_parquet(d / f"pairs_{split}.parquet").head(limit)
        pool = pd.read_parquet(d / "items_q2pool.parquet").set_index("key", drop=False)
        for pr in pairs.itertuples():
            for s in range(k):
                if (pr.key, s) not in done:
                    jobs.append((pool.loc[pr.a], pool.loc[pr.b], s, pr.key))
    lock = threading.Lock()
    stats = {"calls": 0, "parsed": 0, "refused": 0}

    def one(job):
        if stop_file.exists():
            return None
        if q == "q1":
            r, _, s = job
            sysp = (SYS_Q1_TEXT if arm == "text" else SYS_Q1_NUM).format(base=base)
            user, key, field = _user_q1(r, arm), r.key, "p"
        elif q == "id":
            r, _, s = job
            sysp, user, key, field = SYS_ID, f"News:\n{r.btext}", r.key, None
        else:
            a, b, s, key = job
            sysp, user, field = (SYS_Q2_TEXT if arm == "text" else SYS_Q2_NUM), _user_q2(a, b, arm), "p_a"
        res = H.call(sysp, user, purpose="hyp_lab_job3_llm_theories", arm=tag, provider=provider,
                     max_tokens=60 if q != "id" else 80, temperature=temp, cap_usd=CAP_USD)
        if res.get("status") == "HYP_CAP_REFUSED":
            stats["refused"] += 1
            stop_file.write_text("cap")
            return None
        txt = res.get("text")
        if q == "id":
            ans = H.parse_json(txt)
            val, parsed = (ans if isinstance(ans, dict) else None), isinstance(ans, dict)
        else:
            val = parse_prob(txt, field)
            parsed = val is not None
        row = {"key": key, "sample": s, "provider": provider, "q": q, "arm": arm, "parsed": parsed,
               "value": val, "served_model": res.get("served_model"), "status": res.get("status"),
               "raw": None if parsed else (txt or "")[:200],
               "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with lock:
            stats["calls"] += 1
            stats["parsed"] += int(parsed)
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            if stats["calls"] in (5, 50) or stats["calls"] % 200 == 0:
                print(f"[{tag}] {stats['calls']}/{len(jobs)} parsed {stats['parsed']} "
                      f"spent {H.spent()['binding_usd']:.4f}", flush=True)
                if stats["calls"] == 5 and stats["parsed"] == 0:
                    stop_file.write_text("first five unparsed")
        return row

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(as_completed([ex.submit(one, j) for j in jobs]))
    res = {"tag": tag, "jobs": len(jobs), **stats, "wall_s": round(time.time() - t0, 1),
           "spent_night": H.spent()}
    with open(d / "run_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(res, default=str) + "\n")
    print(json.dumps(res, default=str))
    return res


def load_rows(d: Path, tag: str) -> pd.DataFrame:
    p = d / f"rows_{tag}.jsonl"
    if not p.exists():
        return pd.DataFrame()
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    df = pd.DataFrame(rows)
    df = df[df["parsed"]]
    return df.drop_duplicates(["key", "sample"], keep="first")


def platt_fit(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
    m = LogisticRegression(C=1e4, max_iter=1000).fit(X, y)
    return lambda Z: m.predict_proba(Z)[:, 1]


def _lg(p) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 0.01, 0.99)
    return np.log(p / (1 - p))


def stage_analyze(run: str) -> dict:
    d = run_dir(run)
    test = pd.read_parquet(d / "items_test.parquet")
    val = pd.read_parquet(d / "items_val.parquet")
    refs = ["p_base", "p_LB1", "p_LT2"]
    res = {"run": run, "analyzed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "q1": {}, "q2": {},
           "b_numbers": {}, "c_selfconsistency": {}, "leak": {}}
    ids = {}
    for prov in ("deepseek", "local"):
        r = load_rows(d, f"id_text_{prov}_test")
        if len(r):
            from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
            titles = X2.load_titles()
            r["identified"] = [identified(v, k.split("|")[0], titles.get(k.split("|")[0]))
                               for v, k in zip(r["value"], r["key"])]
            ids[prov] = dict(zip(r["key"], r["identified"]))
            res["leak"][prov] = {"n": int(len(r)), "identified_share": round(float(r["identified"].mean()), 4),
                                 "identified_keys": r.loc[r["identified"], "key"].tolist()}
    for prov in ("deepseek", "local"):
        for arm in ("text", "num"):
            r = load_rows(d, f"q1_{arm}_{prov}_test")
            if r.empty:
                continue
            m = test.merge(r[r["sample"] == 0][["key", "value"]].rename(columns={"value": "p_llm"}), on="key")
            m["p_llm"] = m["p_llm"].astype(float)
            sc = score_binary(m, "p_llm", "event", refs)
            if prov in ids:
                m["ident"] = m["key"].map(ids[prov]).fillna(False)
                sc["identified_share"] = round(float(m["ident"].mean()), 4)
                nm = m[~m["ident"].astype(bool)]
                sc["not_identified_only"] = {"n": int(len(nm)),
                                             "brier_diff_vs_p_LB1": block_stats(
                                                 pd.Series(brier(nm["p_LB1"], nm["event"]) - brier(nm["p_llm"], nm["event"])),
                                                 nm["entry_date"])}
            res["q1"][f"{prov}_{arm}"] = sc
            # (b) stacking on the val sample
            rv = load_rows(d, f"q1_{arm}_{prov}_val")
            if len(rv) >= 50:
                mv = val.merge(rv[rv["sample"] == 0][["key", "value"]].rename(columns={"value": "p_llm"}), on="key")
                mv["p_llm"] = mv["p_llm"].astype(float)
                f_ref = platt_fit(_lg(mv["p_LT2"]).reshape(-1, 1), mv["event"].values)
                f_stk = platt_fit(np.c_[_lg(mv["p_LT2"]), _lg(mv["p_llm"])], mv["event"].values)
                m["p_ref_cal"] = f_ref(_lg(m["p_LT2"]).reshape(-1, 1))
                m["p_stack"] = f_stk(np.c_[_lg(m["p_LT2"]), _lg(m["p_llm"])])
                m["p_llm_cal"] = platt_fit(_lg(mv["p_llm"]).reshape(-1, 1), mv["event"].values)(_lg(m["p_llm"]).reshape(-1, 1))
                res["b_numbers"][f"{prov}_{arm}"] = {
                    "n_val_fit": int(len(mv)),
                    "stack_vs_LT2_recal": score_binary(m, "p_stack", "event", ["p_ref_cal"]),
                    "llm_platt_vs_LT2_recal": score_binary(m, "p_llm_cal", "event", ["p_ref_cal", "p_LB1"])}
    # (c) self-consistency
    rk = load_rows(d, "q1_text_deepseek_test_k5_t0.7")
    if len(rk):
        g = rk.groupby("key")["value"].agg(["mean", "count", "first", "std"]).reset_index()
        g = g[g["count"] >= 3]
        m = test.merge(g, on="key")
        m["p_one"], m["p_mean"] = m["first"].astype(float), m["mean"].astype(float)
        out = {"n": int(len(m)), "mean_within_item_sd": round(float(m["std"].mean()), 4),
               "mean_of_k": score_binary(m, "p_mean", "event", ["p_one", "p_LB1"]),
               "single_sample": score_binary(m, "p_one", "event", ["p_LB1"])}
        r0 = load_rows(d, "q1_text_local_test")
        if len(r0):
            m2 = m.merge(r0[r0["sample"] == 0][["key", "value"]].rename(columns={"value": "p_loc"}), on="key")
            m2["p_loc"] = m2["p_loc"].astype(float)
            m2["p_ens"] = (m2["p_mean"] + m2["p_loc"]) / 2
            out["deepseek_mean_plus_local"] = score_binary(m2, "p_ens", "event", ["p_mean", "p_LB1"])
        res["c_selfconsistency"] = out
    # Q2
    pairs = pd.read_parquet(d / "pairs_test.parquet")
    for prov in ("deepseek", "local"):
        for arm in ("text", "num"):
            r = load_rows(d, f"q2_{arm}_{prov}_test")
            if r.empty:
                continue
            m = pairs.merge(r[r["sample"] == 0][["key", "value"]].rename(columns={"value": "p_a"}), on="key")
            m["p_a"] = m["p_a"].astype(float)
            m["p_half"] = 0.5
            m["p_volheur"] = np.where(m["vol_a_higher"] == 1, 0.6, 0.4)
            sc = score_binary(m, "p_a", "a_more", ["p_half", "p_pairnum", "p_volheur"])
            hit = pd.Series(((m["p_a"] > 0.5) == (m["a_more"] == 1)).astype(float)
                            .where(m["p_a"] != 0.5, 0.5), index=m.index)
            sc["accuracy"] = block_stats(hit - 0.5, m["entry_date"])
            sc["accuracy"]["value"] = round(float(hit.mean()), 4)
            sc["accuracy_volheur"] = round(float((m["vol_a_higher"] == m["a_more"]).mean()), 4)
            sc["accuracy_pairnum"] = round(float(((m["p_pairnum"] > 0.5) == (m["a_more"] == 1)).mean()), 4)
            sc["acc_llm_minus_volheur"] = block_stats(hit - (m["vol_a_higher"] == m["a_more"]).astype(float),
                                                      m["entry_date"])
            sc["share_exact_half"] = round(float((m["p_a"] == 0.5).mean()), 4)
            res["q2"][f"{prov}_{arm}"] = sc
    (OUT / f"job3_analysis_{run}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["declare", "run", "analyze"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--q", default="q1", choices=["q1", "q2", "id"])
    ap.add_argument("--arm", default="text", choices=["text", "num"])
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=10 ** 6)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--n-q1", type=int, default=240)
    ap.add_argument("--n-q2", type=int, default=200)
    ap.add_argument("--n-sc", type=int, default=120)
    ap.add_argument("--n-val", type=int, default=240)
    a = ap.parse_args(argv)
    if a.stage == "declare":
        r = stage_declare(a.run, a.n_q1, a.n_q2, a.n_sc, a.n_val)
        print(json.dumps({k: r[k] for k in ("sample", "train_base_rate", "test_sample_event_rate", "sha256")}, indent=1))
    elif a.stage == "run":
        stage_run(a.run, a.provider, a.q, a.arm, a.split, a.limit, a.k, a.temp, a.workers)
    else:
        r = stage_analyze(a.run)
        print(json.dumps(r, indent=1, default=str)[:6000])
    return 0


# ================================================================ Q3 (amendment, declared before its calls)
# The first DeepSeek reads showed Q1 answers hugging the stated base rate (sd_p 0.0065): a
# forced single probability invites abstention. Q3 forces DISCRIMINATION without an anchor:
# eight blinded items from the SAME entry date in one prompt, each scored 0-100 for how likely
# its next-session move is to be large RELATIVE TO ITS OWN normal move ("surprise size").
# Graded by within-group Spearman against rel = log|move| - log(trailing typical move).
SYS_Q3 = (
    "You are given {n} short news items about {n} different US-listed companies, all published before the SAME "
    "trading session. Names and tickers are replaced by 'Company 1' ... 'Company {n}'. You have no tools. "
    "For each company, score 0-100 how likely its move from that session's open to its close (relative to the "
    "S&P 500, absolute value) is to be UNUSUALLY LARGE COMPARED WITH ITS OWN NORMAL DAILY MOVE. A volatile stock "
    "moving its usual amount is NOT unusual; a quiet stock with genuinely market-moving news is. Spread your "
    "scores: the most likely item should be well above the least likely. Reply with ONLY a JSON object mapping "
    "each number to its score, e.g. {{\"1\": 55, \"2\": 20, ...}}.")
SYS_Q3_NUM = SYS_Q3.replace("You have no tools. ", "You have no tools. Each item also lists its normal daily move and a "
                            "statistical model's probability that the move will exceed that normal move; you may "
                            "agree with the model or move away from it where the news justifies it. ")
GROUP = 8


def make_groups(s: pd.DataFrame, n_groups: int, seed: int, titles: dict) -> pd.DataFrame:
    """Groups of GROUP items with the same entry_date; each item blinded as 'Company k'.
    Groups are spread over dates (at most ceil(n_groups / n_dates) per date)."""
    rng = np.random.default_rng(seed)
    rows, gid = [], 0
    dates = [d for d, g in s.groupby("entry_date") if len(g) >= GROUP]
    rng.shuffle(dates)
    per_date = max(1, int(math.ceil(n_groups / max(1, len(dates)))))
    for d in dates:
        g = s[s["entry_date"] == d]
        g = g.iloc[rng.permutation(len(g))]
        used = 0
        for start in range(0, len(g) - GROUP + 1, GROUP):
            if used >= per_date or gid >= n_groups:
                break
            chunk = g.iloc[start:start + GROUP]
            if chunk["symbol"].nunique() < GROUP:
                continue
            texts = []
            for k, r in enumerate(chunk.itertuples(), 1):
                bt, lk = blind(r.text, r.symbol, titles.get(r.symbol), code=f"Company {k}")
                if lk:
                    texts = None
                    break
                texts.append(bt[:700])
            if texts is None:
                continue
            for k, (r, t) in enumerate(zip(chunk.itertuples(), texts), 1):
                rows.append({"gid": gid, "pos": k, "key": f"{r.symbol}|{r.entry_date}",
                             "symbol": r.symbol, "entry_date": r.entry_date, "week": r.week, "month": r.month,
                             "btext": t, "y": r.y, "rel": r.rel, "event": r.event, "vol21_absx": r.vol21_absx,
                             "last_absx": r.last_absx, "p_LT2": r.p_LT2, "p_LB1": r.p_LB1,
                             "T2": r.T2_trailing_meta_tfidf})
            gid += 1
            used += 1
        if gid >= n_groups:
            break
    return pd.DataFrame(rows)


BULK = ROOT / "ft_lab" / "data" / "bulk_events.jsonl"


def earnings_keys() -> set:
    """(symbol|entry_date) cells whose FIRST document the ft_lab student typed as earnings_report
    (a label of the text, known before the session; frozen adapter)."""
    keys = set()
    with open(BULK, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("source") == "panel_cell_first_doc" and r.get("valid") and r.get("event_type") == "earnings_report":
                keys.add(f"{r['symbol']}|{r['entry_date']}")
    return keys


def stage_q3_declare(run: str, n_test: int, n_val: int, only_earnings: bool = False,
                     graded_split: str = "test") -> dict:
    from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
    titles = X2.load_titles()
    c = load_panel()
    c = c[(c["symbol"].str.len() >= 3) & c["symbol"].map(lambda x: x in titles)]
    if only_earnings:
        ek = earnings_keys()
        c = c[(c["symbol"] + "|" + c["entry_date"]).isin(ek)]
    d = run_dir(run)
    gt = make_groups(c[c["split"] == graded_split], n_test, SEED + 10, titles)
    gv = make_groups(c[c["split"] == "val"], n_val, SEED + 11, titles)
    gt.to_parquet(d / "q3_groups_test.parquet", index=False)
    gv.to_parquet(d / "q3_groups_val.parquet", index=False)
    decl = {"job": "hyp_llm_theories JOB3 amendment Q3", "run": run,
            "declared_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "before_any_q3_call": True,
            "why": "Q1 DeepSeek text answers had sd_p 0.0065 (abstention around the stated base rate); Q3 forces a "
                   "within-date ranking without an anchor",
            "groups": {"test": int(gt["gid"].nunique()), "val": int(gv["gid"].nunique()), "items_per_group": GROUP,
                       "distinct_test_dates": int(gt["entry_date"].nunique())},
            "arms": {"q3_text": ["deepseek", "local if time"], "q3_num": ["deepseek"],
                     "q3_text_k3": "deepseek, 3 samples at T=0.7, mean score"},
            "target": "rel = log(|x_oc|+1e-4) - log(vol21_absx): move size relative to the name's own normal",
            "metric": "within-group Spearman(score, rel), mean over groups, SE over weekly blocks of entry date, MDE 2.8 SE; "
                      "paired increment vs p_LT2 ranks; fixed 50/50 average of within-group ranks (LLM, p_LT2) vs p_LT2 "
                      "(no fitting); by month",
            "verdict_rules": {"q3_text": "SKILL if IC > 0 with t >= 2; FAILED_VARIANT if IC <= 0 and MDE <= 0.05; else CANNOT_DISTINGUISH",
                              "q3_adds": "ADDS if rank-average(LLM, LT2) - LT2 > 0 with t >= 2; FAILED_VARIANT if <= 0 and MDE <= 0.03; else CANNOT_DISTINGUISH"},
            "cost_estimate_usd": "< 0.20 DeepSeek",
            "graded_split": graded_split + (" (post-cutoff 2026-01-16..04-30; a second fold, no fitting in Q3)" if graded_split == "val" else ""),
            "subset": "earnings_report cells only (ft_lab student label of the first document)" if only_earnings else "all news cells",
            "added_metric": "IC(score, log|move| - T2 forecast): does the LLM rank what the numbers + TF-IDF model "
                            "missed (declared with the r2 scale-up, before its calls)"}
    decl["sha256"] = hashlib.sha256(json.dumps(decl, sort_keys=True).encode()).hexdigest()
    (OUT / f"job3_declaration_q3_{run}.json").write_text(json.dumps(decl, indent=1), encoding="utf-8")
    return decl


def _q3_user(g: pd.DataFrame, arm: str) -> str:
    parts = []
    for r in g.sort_values("pos").itertuples():
        s = f"Company {r.pos}:\n{r.btext}"
        if arm == "num":
            s += (f"\n[normal daily move {r.vol21_absx * 100:.2f}%; last session {r.last_absx * 100:.2f}%; "
                  f"model probability of exceeding normal {r.p_LT2:.2f}]")
        parts.append(s)
    return "\n\n".join(parts)


def parse_scores(text: str | None, n: int = GROUP) -> dict | None:
    from backend.services.hyp_llm import parse_json  # noqa: PLC0415
    o = parse_json(text)
    if not isinstance(o, dict):
        return None
    out = {}
    for k in range(1, n + 1):
        v = o.get(str(k), o.get(f"Company {k}"))
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        out[k] = v
    return out


def stage_q3_run(run: str, provider: str, arm: str, split: str, k: int, temp: float, workers: int,
                 limit: int) -> dict:
    from backend.services import hyp_llm as H  # noqa: PLC0415
    d = run_dir(run)
    stop_file = d / "STOP"
    tag = f"q3_{arm}_{provider}_{split}" + (f"_k{k}_t{temp}" if k > 1 else "")
    out_path = d / f"rows_{tag}.jsonl"
    done = done_keys(out_path)
    groups = pd.read_parquet(d / f"q3_groups_{split}.parquet")
    jobs = [(gid, g, s) for gid, g in groups.groupby("gid") if gid < limit for s in range(k)
            if (str(gid), s) not in done]
    lock = threading.Lock()
    st = {"calls": 0, "parsed": 0}

    def one(job):
        gid, g, s = job
        if stop_file.exists():
            return None
        res = H.call((SYS_Q3 if arm == "text" else SYS_Q3_NUM).format(n=GROUP), _q3_user(g, arm),
                     purpose="hyp_lab_job3_llm_theories", arm=tag, provider=provider, max_tokens=120,
                     temperature=temp, cap_usd=CAP_USD)
        if res.get("status") == "HYP_CAP_REFUSED":
            stop_file.write_text("cap")
            return None
        sc = parse_scores(res.get("text"))
        row = {"key": str(gid), "sample": s, "parsed": sc is not None, "value": sc, "provider": provider,
               "served_model": res.get("served_model"), "raw": None if sc else (res.get("text") or "")[:200]}
        with lock:
            st["calls"] += 1
            st["parsed"] += int(sc is not None)
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        return row

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(as_completed([ex.submit(one, j) for j in jobs]))
    res = {"tag": tag, "jobs": len(jobs), **st, "wall_s": round(time.time() - t0, 1), "spent_night": H.spent()}
    with open(d / "run_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(res, default=str) + "\n")
    print(json.dumps(res, default=str))
    return res


def stage_q3_id(run: str, provider: str, max_gid: int, workers: int) -> dict:
    """Leak canary on the Q3 items themselves: each item's blinded text (its 'Company k' code
    rewritten to 'Company X') is shown alone and the model is asked to name the company."""
    from backend.services import hyp_llm as H  # noqa: PLC0415
    d = run_dir(run)
    stop_file = d / "STOP"
    tag = f"q3id_text_{provider}_test"
    out_path = d / f"rows_{tag}.jsonl"
    done = done_keys(out_path)
    g = pd.read_parquet(d / "q3_groups_test.parquet")
    g = g[g["gid"] < max_gid]
    jobs = [r for r in g.itertuples() if (f"{r.gid}:{r.pos}", 0) not in done]
    lock = threading.Lock()

    def one(r):
        if stop_file.exists():
            return None
        txt = r.btext.replace(f"Company {r.pos}", CODE)
        res = H.call(SYS_ID, f"News:\n{txt}", purpose="hyp_lab_job3_llm_theories", arm=tag, provider=provider,
                     max_tokens=80, temperature=0.0, cap_usd=CAP_USD)
        if res.get("status") == "HYP_CAP_REFUSED":
            stop_file.write_text("cap")
            return None
        ans = H.parse_json(res.get("text"))
        row = {"key": f"{r.gid}:{r.pos}", "sample": 0, "parsed": isinstance(ans, dict),
               "value": ans if isinstance(ans, dict) else None, "symbol": r.symbol, "provider": provider}
        with lock:
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        return row

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(as_completed([ex.submit(one, j) for j in jobs]))
    return {"tag": tag, "jobs": len(jobs), "spent_night": H.spent()}


def q3_identified(d: Path, provider: str = "deepseek") -> dict:
    r = load_rows(d, f"q3id_text_{provider}_test")
    if r.empty:
        return {}
    from scripts import exp_llm_blind_gap_2026_09_28 as X2  # noqa: PLC0415
    titles = X2.load_titles()
    return {tuple(int(x) for x in k.split(":")): identified(v, s, titles.get(s))
            for k, v, s in zip(r["key"], r["value"], r["symbol"])}


def q3_scores(d: Path, tag: str, groups: pd.DataFrame) -> pd.DataFrame | None:
    r = load_rows(d, tag)
    if r.empty:
        return None
    recs = []
    for x in r.itertuples():
        for pos, v in x.value.items():
            recs.append({"gid": int(x.key), "pos": int(pos), "sample": x.sample, "score": v})
    s = pd.DataFrame(recs).groupby(["gid", "pos"])["score"].mean().reset_index()
    return groups.merge(s, on=["gid", "pos"], how="inner")


def group_ic(m: pd.DataFrame, col: str, target: str = "rel") -> pd.DataFrame:
    from scipy.stats import spearmanr  # noqa: PLC0415
    out = []
    for gid, g in m.groupby("gid"):
        if len(g) < 5 or g[col].nunique() < 2:
            continue
        out.append({"gid": gid, "entry_date": g["entry_date"].iloc[0], "month": g["month"].iloc[0],
                    "ic": spearmanr(g[col], g[target]).statistic})
    return pd.DataFrame(out)


def stage_q3_analyze(run: str) -> dict:
    d = run_dir(run)
    gt = pd.read_parquet(d / "q3_groups_test.parquet")
    res = {}
    for tag in sorted(p.stem.replace("rows_", "") for p in d.glob("rows_q3_*_test*.jsonl")):
        m = q3_scores(d, tag, gt)
        if m is None or m.empty:
            continue
        m["resid"] = np.log(m["y"] + 1e-4) - m["T2"]        # what the numbers + TF-IDF model missed
        m["r_llm"] = m.groupby("gid")["score"].rank(pct=True)
        m["r_lt2"] = m.groupby("gid")["p_LT2"].rank(pct=True)
        m["avg"] = (m["r_llm"] + m["r_lt2"]) / 2
        out = {"n_groups": int(m["gid"].nunique()),
               "share_groups_all_equal": round(float(m.groupby("gid")["score"].nunique().eq(1).mean()), 4)}
        for col, lab in (("score", "llm"), ("p_LT2", "lt2"), ("p_LB1", "lb1"), ("avg", "avg_llm_lt2"), ("T2", "t2")):
            for target in ("rel", "y", "resid"):
                gi = group_ic(m, col, target)
                bs = block_stats(gi["ic"], gi["entry_date"])
                bs["by_month"] = {k: round(float(v), 4) for k, v in gi.groupby("month")["ic"].mean().items()}
                out[f"ic_{lab}_{target}"] = bs
        b = group_ic(m, "p_LT2", "rel")
        for col, lab in (("avg", "inc_avg_minus_lt2_rel"), ("score", "llm_minus_lt2_rel")):
            a = group_ic(m, col, "rel")
            j = a.merge(b, on=["gid", "entry_date", "month"], suffixes=("_a", "_b"))
            out[lab] = block_stats(j["ic_a"] - j["ic_b"], j["entry_date"])
        ident = q3_identified(d)
        if ident:
            m["checked"] = [(g, p) in ident for g, p in zip(m["gid"], m["pos"])]
            m["ident"] = [ident.get((g, p), False) for g, p in zip(m["gid"], m["pos"])]
            chk = m[m["gid"].isin(m.loc[m["checked"], "gid"].unique())]
            clean = chk[~chk["ident"]]
            leak = {"n_items_checked": int(m["checked"].sum()),
                    "identified_share": round(float(m.loc[m["checked"], "ident"].mean()), 4)}
            for lab, frame in (("checked_groups_all_items", chk), ("checked_groups_identified_dropped", clean)):
                gi = group_ic(frame, "score", "rel")
                gr = group_ic(frame, "score", "resid")
                leak[lab] = {"ic_llm_rel": block_stats(gi["ic"], gi["entry_date"]),
                             "ic_llm_resid": block_stats(gr["ic"], gr["entry_date"])}
            out["leak"] = leak
        res[tag] = out
    (OUT / f"job3_analysis_q3_{run}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def verdict(mean, t, mde, mde_bar: float) -> str:
    """The declared three-way rule: positive with t >= 2 is a pass; a non-positive mean with an MDE at or
    below the bar is FAILED_VARIANT; anything else is CANNOT_DISTINGUISH."""
    if mean is None or t is None:
        return "NOT_RUN"
    if mean > 0 and t >= 2:
        return "PASS"
    if mean <= 0 and mde is not None and mde <= mde_bar:
        return "FAILED_VARIANT"
    return "CANNOT_DISTINGUISH"


def main_q3(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["declare", "run", "analyze", "id"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--arm", default="text", choices=["text", "num"])
    ap.add_argument("--split", default="test")
    ap.add_argument("--max-gid", type=int, default=200)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=10 ** 6)
    ap.add_argument("--n-test", type=int, default=80)
    ap.add_argument("--n-val", type=int, default=40)
    ap.add_argument("--only-earnings", action="store_true")
    ap.add_argument("--graded-split", default="test", choices=["test", "val"])
    a = ap.parse_args(argv)
    if a.stage == "declare":
        print(json.dumps(stage_q3_declare(a.run, a.n_test, a.n_val, a.only_earnings, a.graded_split), indent=1))
    elif a.stage == "run":
        stage_q3_run(a.run, a.provider, a.arm, a.split, a.k, a.temp, a.workers, a.limit)
    elif a.stage == "id":
        print(json.dumps(stage_q3_id(a.run, a.provider, a.max_gid, a.workers), default=str))
    else:
        print(json.dumps(stage_q3_analyze(a.run), indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "q3":
        raise SystemExit(main_q3(sys.argv[2:]))
    raise SystemExit(main())
