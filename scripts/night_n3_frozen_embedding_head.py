"""N3 -- a FROZEN pretrained encoder plus a small head, against three controls.

WHY THIS SHAPE AND NOT ANOTHER (two corpses define the design; neither is re-run)

1. `S45` 2026-09-08: a from-scratch text encoder trained on 528k headlines LOSES
   TO TF-IDF in every era. So nothing here trains a representation and no
   tokenizer is written. TF-IDF is not a straw man in this file -- it is THE BAR,
   and it gets the identical head, the identical splits and the identical book.
2. `C2` 2026-09-09: pre-training a representation on a made-up-news proxy task
   and transferring it was REJECTED -- BASELINE +30.6%/yr > CONTROL +19.5 >
   TRANSFER +15.0. The net learned the proxy (61.5% vs 48.4% shuffled) and the
   representation then discarded return-relevant information. So no proxy task
   is learned here either.

What survives both is the cheapest thing that was never tried: a small frozen
sentence encoder that somebody else already paid to train, run ONCE over the
corpus and cached, with a ridge head learned on the return label directly. The
representation costs $0 and never moves; only the head is fit, and it is fit on
`x_oc` and nothing else.

THE EXPERIMENT IS THE CONTROLS. Four arms share one head, one split schedule,
one book and one cost model, and differ only in the feature matrix:

  EMBED   384-d frozen bge-small-en-v1.5 vector of the day's headlines
  TFIDF   TF-IDF -> 384-d SVD of the same text, FIT ON TRAIN ROWS ONLY, per fold
  SHUFFLE the EMBED vectors globally permuted across (symbol, entry_date) cells
  NOTEXT  three price/liquidity columns and no text at all

SHUFFLE is the one that decides whether there is anything here at all: it keeps
the panel's calendar, its universe and its labels and destroys only the link
between a cell and its text. An arm that does not beat SHUFFLE has found the
calendar. NOTEXT says how much of any margin is liquidity and momentum wearing
a language model's clothes.

PIT. The panel is PIT by construction -- `entry_date` is the first regular
session whose OPEN is strictly after publication, and `x_oc` is that session's
open-to-close minus SPY's. This file re-verifies that on every row it uses
(`_assert_pit`) rather than trusting the sentence above, and REFUSES to run if
any row's entry open is at or before its publication timestamp.

ONE PIT DEFECT FOUND IN THE PANEL AND ROUTED AROUND. `news_returns_2025_26.parquet`
carries `dollar_vol` = the ENTRY SESSION's own close x volume, which is not
knowable at that session's open. It is therefore never used here, as a feature
or as a filter. Liquidity comes from `pit_dv_21` -- the 21-session median dollar
volume ending at t-1 -- recomputed from bars.

COSTS. Every book number is charged on REALISED turnover, sum|dw| x COST_BPS,
with the turnover printed beside it. A flat per-date charge is the C2 defect and
is banned. `COST_BPS` is imported from `night_g3_evolve_v2`, not retyped.

Licence: PRODUCT_EXPERIMENT. No claim of alpha is made or permitted from this
file; it exists to tell us whether a free frozen representation carries anything
TF-IDF does not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_checkpoint import Checkpoint, atomic_write_json   # noqa: E402
from scripts.night_g3_evolve_v2 import COST_BPS                      # noqa: E402
from learner.evaluate import TRADABLE_DOLLAR_VOL                     # noqa: E402

# ---------------------------------------------------------------------------
# constants -- all of them, so the receipt can carry the configuration verbatim
# ---------------------------------------------------------------------------
JOB = "N3_frozen_embedding_head"
LICENCE = "PRODUCT_EXPERIMENT"

MODEL_ID = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"   # pinned; not "main"
EMBED_DIM = 384
MAX_TOKENS = 192
ENCODE_BATCH = 256
CHUNK_TEXTS = 20_000            # one checkpoint per chunk

PANEL = REPO / "backend" / "data" / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet"
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
EMB_DIR = REPO / "backend" / "data" / "optimus" / "text_return_panel" / "emb_bge_small_en_v1_5"

RUN_DATE = os.getenv("NIGHT_RUN_DATE", "2026-09-10")
OUT_DIR = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"

SEED = 20260910
MIN_TRAIN_MONTHS = 6            # first test month is the 7th month of the panel
EMBARGO_SESSIONS = 5            # label is same-session open->close; 5 is slack
MIN_NAMES_IC = 10               # a cross-sectional IC needs a cross-section
MIN_NAMES_BOOK = 20             # a decile of 2 names is not a decile
DECILE = 0.10
ALPHAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)
TFIDF_MAX_FEATURES = 60_000
TFIDF_MIN_DF = 5
SVD_COMPONENTS = 384
WINSOR = 0.01
ARMS = ("EMBED", "TFIDF", "SHUFFLE", "NOTEXT")
CONTROLS = ("TFIDF", "SHUFFLE", "NOTEXT")
TRADING_DAYS = 252


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------
def _build_text(df: pd.DataFrame) -> pd.Series:
    title = df["title"].fillna("").astype(str).str.strip()
    body = df["body"].fillna("").astype(str).str.strip()
    return (title + " | " + body).str.strip(" |").str.replace(r"\s+", " ", regex=True)


def _assert_pit(df: pd.DataFrame) -> dict:
    """REFUSE if any label could have been observed at or before publication.

    `entry_date`'s open is 09:30 America/New_York. A row is PIT iff publication
    is strictly earlier than that instant. This is a check, not a belief: the
    panel's own docstring says it holds, and a check that did not run is not a
    check that passed.
    """
    pub = pd.to_datetime(df["published_utc"], utc=True, errors="coerce")
    entry_open = (pd.to_datetime(df["entry_date"]).dt.tz_localize("America/New_York")
                  + pd.Timedelta(hours=9, minutes=30)).dt.tz_convert("UTC")
    known = pub.notna()
    bad_mask = (known & (pub >= entry_open)).to_numpy()
    bad = int(bad_mask.sum())
    if bad:
        worst = df.loc[bad_mask, ["symbol", "published_utc", "entry_date"]].head(5)
        raise SystemExit(
            f"REFUSED: {bad} of {len(df)} rows have an entry open at or before publication. "
            f"The panel is not PIT and nothing downstream of it means anything.\n{worst}")
    lag_h = ((entry_open - pub).dt.total_seconds() / 3600.0)[known]
    return {
        "rows_checked": int(len(df)),
        "rows_with_publication_timestamp": int(known.sum()),
        "rows_violating_pit": 0,
        "hours_publication_to_entry_open": {
            "min": round(float(lag_h.min()), 3),
            "p05": round(float(lag_h.quantile(0.05)), 3),
            "median": round(float(lag_h.median()), 3),
            "max": round(float(lag_h.max()), 3),
        },
    }


def _price_features(symbols: set) -> pd.DataFrame:
    """PIT liquidity and momentum: everything ends at t-1, nothing touches t.

    The panel's own `dollar_vol` column is the entry session's close x volume and
    is therefore unusable both as a feature and as a filter. This replaces it.
    """
    b = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    b = b[b["symbol"].isin(symbols)].copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b.sort_values(["symbol", "date"]).reset_index(drop=True)
    g = b.groupby("symbol", sort=False)
    dv = (b["close"] * b["volume"]).groupby(b["symbol"], sort=False).shift(1)
    prev_close = g["close"].shift(1)
    med = dv.groupby(b["symbol"], sort=False).rolling(21, min_periods=10).median()
    med = med.reset_index(level=0, drop=True)
    return pd.DataFrame({
        "symbol": b["symbol"].to_numpy(),
        "entry_date": b["date"].to_numpy(),
        "pit_dv_21": med.to_numpy(),
        "mom_21": (prev_close / g["close"].shift(22) - 1.0).to_numpy(),
        "mom_5": (prev_close / g["close"].shift(6) - 1.0).to_numpy(),
    })


def load_cells(smoke: bool = False):
    """One row per (symbol, entry_date) cell, plus the deduplicated text corpus.

    A cell, not a headline, is the unit: the label is a property of the session,
    so one row per headline would count the same return several times and inflate
    every n in the file.
    """
    df = pd.read_parquet(PANEL)
    if smoke:
        keep = sorted(df["symbol"].unique())[:120]
        df = df[df["symbol"].isin(keep)].copy()
    df = df[np.isfinite(df["x_oc"].to_numpy(dtype=float))].copy()
    pit = _assert_pit(df)

    df["text"] = _build_text(df)
    df = df[df["text"].str.len() > 0].copy()
    df["text_sha1"] = [_sha1(t) for t in df["text"]]

    corpus = (df[["text_sha1", "text"]].drop_duplicates("text_sha1")
                .sort_values("text_sha1").reset_index(drop=True))
    corpus["row"] = np.arange(len(corpus), dtype=np.int64)
    df = df.merge(corpus[["text_sha1", "row"]], on="text_sha1", how="left")

    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.normalize()

    cells = (df.groupby(["symbol", "entry_date"], sort=False)
               .agg(x_oc=("x_oc", "first"),
                    n_news=("row", "size"),
                    rows=("row", lambda s: tuple(sorted(set(int(v) for v in s)))))
               .reset_index())
    text_by_row = corpus["text"].to_numpy()
    cells["text"] = [" ".join(text_by_row[list(r)]) for r in cells["rows"]]

    px = _price_features(set(cells["symbol"].unique()))
    cells = cells.merge(px, on=["symbol", "entry_date"], how="left")
    before = len(cells)
    cells = cells[np.isfinite(cells["mom_21"].to_numpy(dtype=float))
                  & np.isfinite(cells["mom_5"].to_numpy(dtype=float))
                  & np.isfinite(cells["pit_dv_21"].to_numpy(dtype=float))].copy()
    cells = cells.sort_values(["entry_date", "symbol"]).reset_index(drop=True)

    meta = {
        "pit_check": pit,
        "panel_rows_used": int(len(df)),
        "unique_texts": int(len(corpus)),
        "cells_before_price_join": int(before),
        "cells": int(len(cells)),
        "symbols": int(cells["symbol"].nunique()),
        "date_range": [str(cells["entry_date"].min().date()), str(cells["entry_date"].max().date())],
        "dollar_vol_column_of_panel": "IGNORED -- it is the entry session's own close x volume (not PIT)",
    }
    return cells, list(corpus["text"]), meta


# ---------------------------------------------------------------------------
# the frozen encoder -- run ONCE over the corpus, checkpointed, cached
# ---------------------------------------------------------------------------
def embed_corpus(texts, resume: bool = True, verbose: bool = True):
    """Embed every distinct headline once. A pass that dies at 80% resumes.

    Cached to `EMB_DIR` keyed by (model, revision, max_tokens, corpus digest), so
    the second run of this experiment costs zero GPU seconds. Nothing is trained:
    the weights are downloaded, frozen, put in inference mode and never see a label.
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    digest = _sha1(f"{len(texts)}|" + _sha1("\x00".join(texts[::997])))
    config = {"model_id": MODEL_ID, "revision": MODEL_REVISION, "max_tokens": MAX_TOKENS,
              "n_texts": len(texts), "corpus_digest": digest, "chunk": CHUNK_TEXTS}
    # One cache directory PER CORPUS. `Checkpoint` rightly refuses to resume when
    # the configuration moved, and a single shared directory turns that correct
    # refusal into a crash the first time a --smoke corpus (11k texts) is followed
    # by the real one (162k) -- which is exactly what happened on the first
    # attempt. Keying the directory by the corpus lets the two coexist, and the
    # refusal goes back to meaning what it is for: the same corpus, changed.
    cache = EMB_DIR / f"n{len(texts)}_{digest[:12]}"
    cache.mkdir(parents=True, exist_ok=True)
    ck = Checkpoint(cache / "embed_checkpoint.json", config)

    n_chunks = (len(texts) + CHUNK_TEXTS - 1) // CHUNK_TEXTS
    done = 0
    prior_s = 0.0
    if resume and ck.exists():
        state = ck.load()
        done = int(state.get("chunks_done") or 0)
        # GPU seconds spent by EARLIER sessions on this same corpus. Without this
        # a resumed run reports the seconds it personally spent, which for a fully
        # cached corpus is 0.0 -- a true statement about this process and a
        # misleading one about the experiment.
        prior_s = float(state.get("elapsed_s_total") or state.get("elapsed_s") or 0.0)
        if verbose:
            print(f"[embed] resuming: {done}/{n_chunks} chunks already on disk "
                  f"({prior_s:.0f}s of encoding already paid)", flush=True)

    t0 = time.time()
    if done < n_chunks:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
        model = AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
        model = (model.half() if device == "cuda" else model.float()).to(device)
        model.train(False)
        for p in model.parameters():
            p.requires_grad_(False)
        for ci in range(done, n_chunks):
            lo, hi = ci * CHUNK_TEXTS, min((ci + 1) * CHUNK_TEXTS, len(texts))
            vecs = np.empty((hi - lo, EMBED_DIM), dtype=np.float32)
            with torch.inference_mode():
                for i in range(lo, hi, ENCODE_BATCH):
                    j = min(i + ENCODE_BATCH, hi)
                    enc = tok(texts[i:j], padding=True, truncation=True,
                              max_length=MAX_TOKENS, return_tensors="pt").to(device)
                    h = model(**enc).last_hidden_state[:, 0]      # bge uses the CLS token
                    v = torch.nn.functional.normalize(h.float(), dim=-1)
                    vecs[i - lo:j - lo] = v.cpu().numpy()
            np.save(cache / f"chunk_{ci:05d}.npy", vecs.astype(np.float16))
            ck.save({"chunks_done": ci + 1, "n_chunks": n_chunks, "texts_done": hi,
                     "elapsed_s": round(time.time() - t0, 1),
                     "elapsed_s_total": round(prior_s + time.time() - t0, 1)})
            if verbose:
                print(f"[embed] chunk {ci + 1}/{n_chunks}  {hi}/{len(texts)} texts  "
                      f"{time.time() - t0:.0f}s", flush=True)
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
    wall = time.time() - t0

    parts = [np.load(cache / f"chunk_{ci:05d}.npy") for ci in range(n_chunks)]
    emb = np.concatenate(parts, axis=0).astype(np.float32)
    if emb.shape != (len(texts), EMBED_DIM):
        raise SystemExit(f"REFUSED: embedding cache is {emb.shape}, corpus is {len(texts)} x {EMBED_DIM}")
    info = {"model_id": MODEL_ID, "revision": MODEL_REVISION, "dim": EMBED_DIM,
            "pooling": "CLS + L2 normalise (the bge convention)", "max_tokens": MAX_TOKENS,
            "dtype": "fp16 forward, fp16 cache, fp32 in memory", "params_millions": 33.36,
            "rows_embedded": int(len(texts)), "chunks": n_chunks,
            "encode_wall_clock_s": round(wall, 1),
            "encode_wall_clock_s_note": "this process only; 0 when every chunk was already cached",
            "encode_wall_clock_s_all_sessions": round(prior_s + wall, 1),
            "encode_texts_per_second": (round(len(texts) / (prior_s + wall), 1)
                                        if (prior_s + wall) > 0 else None),
            "cost_usd": 0.0, "cache_dir": str(cache), "corpus_digest": digest}
    return emb, info


def cell_vectors(cells: pd.DataFrame, emb: np.ndarray) -> np.ndarray:
    """A cell's vector is the mean of its headlines', renormalised to the sphere."""
    out = np.zeros((len(cells), EMBED_DIM), dtype=np.float32)
    for i, rows in enumerate(cells["rows"].to_numpy()):
        out[i] = emb[list(rows)].mean(axis=0)
    n = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(n, 1e-9)


# ---------------------------------------------------------------------------
# the head -- one head, four feature matrices
# ---------------------------------------------------------------------------
def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    d = float(np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


class _RidgePath:
    """Every alpha in the grid from ONE pass over the data.

    `sklearn.linear_model.Ridge` refits from scratch per alpha, which means the
    n x d product is paid five times per arm per fold. With d = 384 the Gram
    matrix is tiny, so the whole regularisation path comes out of a single
    eigendecomposition of `Xc.T @ Xc` -- exactly the same estimator, ~15x less
    wall clock. Checked against `Ridge(fit_intercept=True)` in
    `backend/tests/test_n3_frozen_embedding_head.py`, because a hand-rolled
    solver that silently disagrees with the library is worse than a slow one.
    """

    def __init__(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.xbar = X.mean(axis=0)
        self.ybar = float(y.mean())
        Xc = X - self.xbar
        yc = y - self.ybar
        G = Xc.T @ Xc
        self.c = Xc.T @ yc
        s, V = np.linalg.eigh(G)                       # G is symmetric PSD
        self.s = np.maximum(s, 0.0)
        self.V = V
        self.Vtc = V.T @ self.c

    def coef(self, alpha: float) -> np.ndarray:
        return self.V @ (self.Vtc / (self.s + float(alpha)))

    def predict(self, X: np.ndarray, alpha: float) -> np.ndarray:
        w = self.coef(alpha)
        return (np.asarray(X, dtype=np.float64) - self.xbar) @ w + self.ybar


def _fit_ridge(Xtr, ytr, Xte, dates_tr, alphas=ALPHAS):
    """Standardise on train, pick alpha on an INNER temporal split, refit, predict.

    The inner split is the last 20% of the training MONTHS. No test row is seen
    at any point, including by the alpha choice -- an alpha tuned on the test
    fold is the test fold's t-statistic wearing a hyper-parameter's name.
    """
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    Xtr = (Xtr - mu) / sd
    Xte = (Xte - mu) / sd

    lo, hi = np.quantile(ytr, [WINSOR, 1 - WINSOR])
    ytr = np.clip(ytr, lo, hi)
    ym, ys = float(ytr.mean()), float(ytr.std() or 1.0)
    ytr_z = (ytr - ym) / ys

    months = pd.Series(dates_tr).dt.to_period("M").astype(str).to_numpy()
    uniq = sorted(set(months))
    best_alpha, best_ic = float(alphas[0]), -np.inf
    if len(uniq) >= 3:
        cut = uniq[int(len(uniq) * 0.8)]
        inner_tr = months < cut
        inner_va = ~inner_tr
        if inner_tr.sum() > 50 and inner_va.sum() > 50:
            dva = pd.Series(dates_tr).to_numpy()[inner_va]
            yva = ytr_z[inner_va]
            Xva = Xtr[inner_va]
            groups = [dva == d for d in np.unique(dva)]
            path = _RidgePath(Xtr[inner_tr], ytr_z[inner_tr])
            for a in alphas:
                p = path.predict(Xva, a)
                ics = [_spearman(p[g], yva[g]) for g in groups]
                ics = [v for v in ics if np.isfinite(v)]
                ic = float(np.mean(ics)) if ics else -np.inf
                if ic > best_ic:
                    best_ic, best_alpha = ic, float(a)
    return _RidgePath(Xtr, ytr_z).predict(Xte, best_alpha), best_alpha


def _tfidf_svd(train_text, test_text, seed: int):
    """The BAR. Vocabulary, idf weights and SVD basis are fit on TRAIN ONLY.

    Fitting the vectoriser on the pooled corpus would let the test fold's
    vocabulary and document frequencies into the representation, which is the
    quiet way a TF-IDF baseline gets made to look worse than it is.
    """
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(min_df=TFIDF_MIN_DF, max_features=TFIDF_MAX_FEATURES,
                          ngram_range=(1, 2), sublinear_tf=True,
                          strip_accents="unicode", lowercase=True)
    Xtr = vec.fit_transform(train_text)
    Xte = vec.transform(test_text)
    k = int(min(SVD_COMPONENTS, max(2, min(Xtr.shape) - 1)))
    svd = TruncatedSVD(n_components=k, algorithm="randomized", n_iter=4, random_state=seed)
    Ztr = svd.fit_transform(Xtr)
    Zte = svd.transform(Xte)
    return (Ztr.astype(np.float32), Zte.astype(np.float32),
            {"vocab": int(len(vec.vocabulary_)), "svd_components": k,
             "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4)})


# ---------------------------------------------------------------------------
# the book -- realised turnover, always
# ---------------------------------------------------------------------------
def _book_day(pred, y, symbols, tradable):
    """Decile long-short, EW, gross exposure 1.0, over the tradable names only."""
    if int(tradable.sum()) < MIN_NAMES_BOOK:
        return float("nan"), {}
    p, yy, ss = pred[tradable], y[tradable], symbols[tradable]
    n = len(p)
    k = max(1, int(round(n * DECILE)))
    order = np.argsort(-p)
    lg, sh = order[:k], order[-k:]
    gross = float(yy[lg].mean() - yy[sh].mean())
    w = {}
    for i in lg:
        w[ss[i]] = w.get(ss[i], 0.0) + 0.5 / k
    for i in sh:
        w[ss[i]] = w.get(ss[i], 0.0) - 0.5 / k
    return gross, w


def _turnover(prev, cur):
    keys = set(prev) | set(cur)
    return float(sum(abs(cur.get(s, 0.0) - prev.get(s, 0.0)) for s in keys))


# ---------------------------------------------------------------------------
# walk-forward
# ---------------------------------------------------------------------------
def run_folds(cells: pd.DataFrame, feats: dict, verbose: bool = True):
    """Expanding walk-forward by month, purged with a 5-session embargo.

    Never k-fold: a random fold puts next quarter's news in this quarter's
    training set and the whole file becomes a look-ahead with a t-statistic.
    """
    dates = cells["entry_date"].to_numpy()
    months = cells["entry_date"].dt.to_period("M").astype(str).to_numpy()
    y = cells["x_oc"].to_numpy(dtype=float)
    syms = cells["symbol"].to_numpy()
    texts = cells["text"].to_numpy()
    tradable_all = cells["pit_dv_21"].to_numpy(dtype=float) >= TRADABLE_DOLLAR_VOL
    sessions = np.array(sorted(pd.unique(dates)))
    uniq_months = sorted(set(months))

    daily = []
    fold_log = []
    for mi in range(MIN_TRAIN_MONTHS, len(uniq_months)):
        mo = uniq_months[mi]
        te = months == mo
        if te.sum() < MIN_NAMES_IC:
            continue
        first_test = dates[te].min()
        cut_i = int(np.searchsorted(sessions, first_test)) - EMBARGO_SESSIONS
        if cut_i <= 0:
            continue
        tr = dates < sessions[cut_i]
        if tr.sum() < 500:
            continue

        preds, alphas, tf_info = {}, {}, {}
        for arm in ARMS:
            if arm == "TFIDF":
                Xtr, Xte, tf_info = _tfidf_svd(list(texts[tr]), list(texts[te]), SEED + mi)
            else:
                F = feats[arm]
                Xtr, Xte = F[tr], F[te]
            preds[arm], alphas[arm] = _fit_ridge(Xtr, y[tr], Xte, pd.Series(dates[tr]))

        d_te, y_te, s_te, t_te = dates[te], y[te], syms[te], tradable_all[te]
        for d in np.unique(d_te):
            k = d_te == d
            if k.sum() < MIN_NAMES_IC:
                continue
            row = {"date": pd.Timestamp(d), "month": mo, "n": int(k.sum()),
                   "n_tradable": int(t_te[k].sum())}
            for arm in ARMS:
                row[f"ic_{arm}"] = _spearman(preds[arm][k], y_te[k])
                g, w = _book_day(preds[arm][k], y_te[k], s_te[k], t_te[k])
                row[f"gross_{arm}"] = g
                row[f"w_{arm}"] = w
            daily.append(row)

        fold_log.append({"test_month": mo, "n_train": int(tr.sum()), "n_test": int(te.sum()),
                         "train_cut_session": str(pd.Timestamp(sessions[cut_i]).date()),
                         "alphas": alphas, "tfidf": tf_info})
        if verbose:
            print(f"[fold] {mo}  train {int(tr.sum()):>7}  test {int(te.sum()):>6}  "
                  + "  ".join(f"{a} a={alphas[a]:g}" for a in ARMS), flush=True)

    if not daily:
        return pd.DataFrame(), fold_log
    dd = pd.DataFrame(daily).sort_values("date").reset_index(drop=True)
    for arm in ARMS:
        prev = {}
        to, net = [], []
        for w, g in zip(dd[f"w_{arm}"].to_numpy(), dd[f"gross_{arm}"].to_numpy()):
            if not w:
                # An UNGRADABLE date (too few tradable names) is not a liquidation.
                # Charging `sum|w_prev - 0|` here would bill a full round trip the
                # book never did, and would put that phantom into the mean turnover
                # while leaving the net return NaN -- so the printed turnover would
                # no longer be the turnover the printed net was charged on.
                to.append(float("nan"))
                net.append(float("nan"))
                continue
            t = _turnover(prev, w)
            to.append(t)
            net.append(g - t * COST_BPS / 1e4 if np.isfinite(g) else float("nan"))
            prev = w
        dd[f"turnover_{arm}"] = to
        dd[f"net_{arm}"] = net
        dd.drop(columns=[f"w_{arm}"], inplace=True)
    return dd, fold_log


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------
def _t_and_p(x: np.ndarray):
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan"), n
    sd = float(x.std(ddof=1))
    if sd <= 0:
        return float("nan"), float("nan"), n
    t = float(x.mean() / (sd / np.sqrt(n)))
    try:
        from scipy import stats
        p = float(2 * stats.t.sf(abs(t), df=n - 1))
    except Exception:                                                # noqa: BLE001
        p = float("nan")
    return t, p, n


def _cell(x: np.ndarray, ann: bool) -> dict:
    t, p, n = _t_and_p(x)
    v = x[np.isfinite(x)]
    mean = float(v.mean()) if len(v) else float("nan")
    out = {"mean": round(mean, 6), "t": round(t, 3) if np.isfinite(t) else None,
           "p": round(p, 4) if np.isfinite(p) else None, "n_date_blocks": n}
    if ann:
        out["ann_pct"] = round(mean * TRADING_DAYS * 100, 3)
    return out


def grade(dd: pd.DataFrame) -> dict:
    """Per era, never pooled-only: a single pooled number hides one good quarter."""
    dd = dd.copy()
    dd["era"] = dd["date"].dt.to_period("Q").astype(str)
    eras = ["ALL"] + sorted(dd["era"].unique())
    out = {"eras": {}}
    for era in eras:
        sl = dd if era == "ALL" else dd[dd["era"] == era]
        cell = {"n_dates": int(len(sl)),
                "dates": [str(sl["date"].min().date()), str(sl["date"].max().date())],
                "median_names_per_date": int(sl["n"].median()),
                "median_tradable_per_date": int(sl["n_tradable"].median()),
                "arms": {}, "vs_controls": {}}
        for arm in ARMS:
            cell["arms"][arm] = {
                "ic": _cell(sl[f"ic_{arm}"].to_numpy(dtype=float), False),
                "gross": _cell(sl[f"gross_{arm}"].to_numpy(dtype=float), True),
                "net": _cell(sl[f"net_{arm}"].to_numpy(dtype=float), True),
                "mean_daily_turnover": round(float(np.nanmean(sl[f"turnover_{arm}"].to_numpy(dtype=float))), 4),
                "cost_bps_per_unit_turnover": COST_BPS,
            }
        for c in CONTROLS:
            cell["vs_controls"][f"EMBED_minus_{c}"] = {
                "ic": _cell((sl["ic_EMBED"] - sl[f"ic_{c}"]).to_numpy(dtype=float), False),
                "net": _cell((sl["net_EMBED"] - sl[f"net_{c}"]).to_numpy(dtype=float), True),
            }
        out["eras"][era] = cell

    ps = [(k, v["ic"]["p"]) for k, v in out["eras"]["ALL"]["vs_controls"].items()
          if v["ic"]["p"] is not None]
    ps.sort(key=lambda kv: kv[1])
    holm, mx = {}, None
    for i, (k, p) in enumerate(ps):
        adj = min(1.0, p * (len(ps) - i))
        adj = max(adj, max(list(holm.values()) or [0.0]))
        holm[k] = round(adj, 4)
        mx = adj if mx is None else max(mx, adj)
    out["holm_adjusted_p_all_era_ic"] = holm
    out["family_max_p"] = round(float(mx), 4) if mx is not None else None
    return out


def verdict(g: dict):
    a = g["eras"]["ALL"]
    d = a["vs_controls"]["EMBED_minus_TFIDF"]["ic"]
    s = a["vs_controls"]["EMBED_minus_SHUFFLE"]["ic"]
    e = a["arms"]["EMBED"]["ic"]
    tf = a["arms"]["TFIDF"]["ic"]
    eras = [k for k in g["eras"] if k != "ALL"]
    beat = sum(1 for k in eras
               if (g["eras"][k]["vs_controls"]["EMBED_minus_TFIDF"]["ic"]["mean"] or 0) > 0)

    head = (f"frozen {MODEL_ID} + ridge: IC {e['mean']:+.4f} (t {e['t']}) vs TF-IDF+SVD "
            f"IC {tf['mean']:+.4f} (t {tf['t']}); difference {d['mean']:+.4f} t {d['t']} "
            f"p {d['p']} over {d['n_date_blocks']} date blocks; beats TF-IDF in "
            f"{beat}/{len(eras)} eras; vs shuffled text {s['mean']:+.4f} t {s['t']}")

    beats_tfidf = (d["t"] is not None and d["t"] > 2.0 and (d["mean"] or 0) > 0)
    beats_shuffle = (s["t"] is not None and s["t"] > 2.0 and (s["mean"] or 0) > 0)
    if not beats_shuffle:
        v = ("FAILED_VARIANT: the frozen-embedding arm does not beat the SHUFFLED-TEXT control, "
             "so whatever it earns is the panel's calendar and universe, not the text.")
    elif not beats_tfidf:
        v = ("FAILED_VARIANT: the frozen embedding carries signal (it beats shuffled text) but "
             "does NOT beat TF-IDF, which is the bar the from-scratch encoder also failed. "
             "The prior stands: on this corpus, a free frozen sentence encoder buys nothing "
             "over a bag of words.")
    else:
        v = ("PRODUCT_PROMISING (CONDITIONAL): the frozen embedding beats both the shuffled-text "
             "control and TF-IDF on identical splits and an identical head. 20 months, one "
             "regime, no forward evidence: this is a hypothesis, not a book.")
    return head, v


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="N3 frozen embedding + small head, vs three controls")
    ap.add_argument("--out", default=None, help="receipt path (default: the night_factory dir)")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="120 symbols, quick end-to-end check")
    ap.add_argument("--no-resume", action="store_true", help="ignore the embedding checkpoint")
    args = ap.parse_args(argv)

    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (OUT_DIR / f"{JOB}_run{args.run:02d}.json")

    receipt = {
        "job": JOB, "licence": LICENCE, "run": args.run, "smoke": bool(args.smoke),
        "llm_spend_usd": 0.0,
        "question": ("Does a FROZEN pretrained sentence encoder plus a small head learned on the "
                     "return label beat TF-IDF, shuffled text, and no text at all, on identical "
                     "walk-forward splits?"),
        "design": {
            "encoder": "frozen, never fine-tuned, never shown a label",
            "head": "ridge on standardised features, alpha chosen on an inner temporal split",
            "unit": "(symbol, entry_date) cell -- one label per session, not one per headline",
            "target": "x_oc (SPY-excess open-to-close on the first session opening after publication)",
            "splits": (f"expanding walk-forward by month, {EMBARGO_SESSIONS}-session embargo, "
                       f"first test month is month {MIN_TRAIN_MONTHS + 1}"),
            "arms": {"EMBED": f"{EMBED_DIM}-d frozen {MODEL_ID}",
                     "TFIDF": f"TF-IDF(1-2gram) -> {SVD_COMPONENTS}-d SVD, fit on TRAIN rows only, per fold",
                     "SHUFFLE": "the EMBED vectors globally permuted across cells (seed pinned)",
                     "NOTEXT": "log10 PIT 21-session median dollar volume, mom_21, mom_5"},
            "book": (f"decile long-short, EW, gross exposure 1.0, {TRADABLE_DOLLAR_VOL:,.0f} PIT "
                     f"dollar-volume floor, charged on REALISED turnover sum|dw| x {COST_BPS} bps"),
            "cost_bps_per_side": COST_BPS,
            "cost_source": "scripts.night_g3_evolve_v2.COST_BPS (imported, not retyped)",
            "tradable_floor_usd": TRADABLE_DOLLAR_VOL,
            "seed": SEED,
        },
        "status": "running", "written_utc": _now(),
    }
    atomic_write_json(out, receipt, indent=1)

    print("[n3] loading the panel", flush=True)
    cells, corpus, meta = load_cells(smoke=args.smoke)
    receipt["panel"] = meta
    receipt["written_utc"] = _now()
    atomic_write_json(out, receipt, indent=1)
    print(f"[n3] {meta['cells']:,} cells, {meta['symbols']:,} symbols, "
          f"{meta['unique_texts']:,} distinct texts", flush=True)

    emb, enc_info = embed_corpus(corpus, resume=not args.no_resume)
    receipt["encoder"] = enc_info
    receipt["written_utc"] = _now()
    atomic_write_json(out, receipt, indent=1)

    V = cell_vectors(cells, emb)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(cells))
    feats = {
        "EMBED": V,
        "SHUFFLE": V[perm],
        "NOTEXT": np.column_stack([
            np.log10(np.maximum(cells["pit_dv_21"].to_numpy(dtype=float), 1.0)),
            cells["mom_21"].to_numpy(dtype=float),
            cells["mom_5"].to_numpy(dtype=float),
        ]).astype(np.float32),
        "TFIDF": None,
    }
    receipt["shuffle_control"] = {
        "kind": "global permutation of cell vectors across (symbol, entry_date)",
        "seed": SEED,
        "fixed_points": int((perm == np.arange(len(cells))).sum()),
        "note": "labels, dates, universe and construction are identical; only the text link is cut",
    }

    print("[n3] walk-forward", flush=True)
    dd, folds = run_folds(cells, feats)
    if dd.empty:
        receipt["status"] = "REFUSED"
        receipt["verdict"] = ("REFUSED: no gradable test date -- the panel is too short for the "
                              "split schedule")
        receipt["written_utc"] = _now()
        atomic_write_json(out, receipt, indent=1)
        print(receipt["verdict"])
        return 2

    g = grade(dd)
    head, v = verdict(g)
    daily_path = out.with_name(out.stem + "_daily.csv")
    dd.to_csv(daily_path, index=False)

    receipt["folds"] = folds
    receipt["results"] = g
    receipt["family_max_p"] = g["family_max_p"]
    receipt["headline"] = head
    receipt["verdict"] = v
    receipt["daily_csv"] = str(daily_path)
    receipt["status"] = "done"
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = _now()
    atomic_write_json(out, receipt, indent=1)

    print("\n" + head)
    print(v)
    print(f"receipt: {out}")
    return 0


def N3_frozen_embedding_head(smoke: bool = False, run: int = 1) -> dict:
    """Adapter for `scripts.night_factory_jobs.JOBS`, which wants a payload back.

    Registering N3 in the night factory needs exactly one line there:

        "N3_frozen_embedding_head": _lazy("scripts.night_n3_frozen_embedding_head",
                                          "N3_frozen_embedding_head"),

    The factory writes whatever a job returns to its own receipt path, so this
    runs the experiment against THAT path -- which keeps the incremental,
    crash-safe writes -- and hands the finished payload back for the final write.
    """
    out = OUT_DIR / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    argv = ["--run", str(run), "--out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
