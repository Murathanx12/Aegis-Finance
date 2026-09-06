"""N5.1 -- EVENT COMPRESSION: canonical events out of syndicated news (Night Lab 2026-09-07).

WHAT THIS IS
============
`docs/NIGHT_LAB_2026-09-07_OPUS_PROMPT.md` lane N5 item 1: cluster the news
corpus (+ whatever backfill exists) into CANONICAL events -- i.e. dedupe
syndication so a thousand copies of one story become one event -- and build
three features per canonical event:

    independent_source_count    how many distinct outlets carried it
    novelty_vs_company_history  how unlike this company's own recent stories
                                 the event's text is (causal: only STRICTLY
                                 earlier canonical events for the same name)
    dissemination_speed         how fast independent copies piled up

CORPUS LOCATIONS (read-only; this script owns nothing under either path)
==========================================================================
* `aegis-alpha-terminal/state/corpus/observations/*.jsonl` (the OTHER repo,
  `alpha/sources/corpus.py`'s append-only store -- see
  `docs/CORPUS_2026-08-29_MEMORY_AND_DIARY.md` there). One JSON row per
  observation: kind, tense, title, source, independence_group, observed_at,
  effective_at, symbols, body, uid. THIS IS A MOVING TARGET -- another lane's
  backfill job can be appending to it while this script reads it. A snapshot
  read is taken once and its row counts are stamped with the read time; no
  claim is made about what the file holds a second later.
* `backend/data/optimus/edgar_8k/eightk_rows.jsonl` (this repo) -- SEC 8-K
  filings, ALREADY canonical by construction (one row per accession number;
  a filer cannot re-file the same accession). Included for completeness
  ("whatever backfill exists") with a trivial compression ratio, not
  clustered.
* `backend/data/optimus/events/event_table_v1.parquet` (this repo, built by
  the N4 lane in this same night, `scripts/n4_event_table.py` -- NOT owned by
  this file, read-only) -- if present, THIS is what the novelty feature is
  tested against, per the task's own instruction. N4's table already carries
  a PIT-resolved `permno` (via `crsp_stocknames_interval`) and
  `observed_at_utc`, and is scoped to 2015-2016 (the only years its own
  backward corpus pull covered when it ran). If it is absent or empty, the
  novelty test falls back to the corpus's own forward returns via a permno
  crosswalk this script builds from `crsp__stocknames_v2.parquet`, and the
  receipt says explicitly which path ran.

WHY TF-IDF, NOT THE NIM EMBEDDER, IS THE PRODUCTION PATH
==========================================================
`backend/data/optimus/labor_day_lab_2026-09-07/D1_connection_check_finance.json`
recorded NVIDIA NIM as CANNOT_DETERMINE (30.2s, no answer) two days before this
ran. A live reachability probe run manually before writing this file found the
embeddings endpoint (`nvidia/nemotron-3-embed-1b`, batch of 50, 2048-dim)
answering in ~1.1-1.5s -- so the earlier CANNOT_DETERMINE was a transient
network condition, not a dead key. `probe_nemotron()` re-checks this at
receipt-build time and the result is stamped either way.

Even so, TF-IDF stays the PRODUCTION clustering path, not a consolation prize:
it is deterministic, needs no network (so it is the only path this repo's
CI-on-Linux/no-network test file can exercise), costs nothing, and the task
names it "the expected path". The NIM probe is recorded as a validated
reachability fact, not built into the committed clustering run -- burning a
few thousand embedding calls against a corpus another lane is actively
appending to, for a result nothing downstream depends on tonight, fails the
lab's own "value of decision improved minus cost" test. TF-IDF's known
failure mode is stated plainly in the receipt: it catches EXACT-reformatted
duplicate headlines (which syndication mostly is) and MISSES same-event
stories that share no vocabulary (a Trump tweet reported as four differently
-worded headlines) -- so the compression ratio it reports is a LOWER BOUND
on the true one, not a point estimate.

THE NULL FOR THE NOVELTY TEST
==============================
A shuffled-DATE null does not control for the date (S24,
`feedback_a_shuffled_date_null_does_not_control_for_the_date.md`: +6.01%
p=0.0005 collapsed to +2.10% once the day was held fixed). The permutation
here shuffles `novelty` WITHIN each calendar month across canonical events,
holding the month -- and therefore whatever the month itself contributed to
the forward return -- fixed. `learner/nullbar.py` supplies the >=64-draw floor
and the percentile/p-value arithmetic; this file does not reimplement either.

LICENCE: PRODUCT_EXPERIMENT. Places nothing, recommends nothing.

    python -m scripts.n5_event_compression                  # full run
    python -m scripts.n5_event_compression --quick           # smoke-sized
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sklearn.feature_extraction.text import TfidfVectorizer             # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity                  # noqa: E402
from scipy.stats import spearmanr                                       # noqa: E402

from backend.services import receipt_provenance as PROV                 # noqa: E402
from learner import nullbar as NB                                       # noqa: E402
from learner import dataset as D                                        # noqa: E402
from scripts.w3_neural_floored import free_gb                           # noqa: E402

RECEIPT = (REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
           / "N5_event_compression.json")

#: Candidate locations for the terminal repo's corpus store. Env override
#: first (`AAT_STATE_DIR`, the same variable `alpha/sources/corpus.py` reads),
#: then a sibling checkout, then the path this machine is known to use. None
#: of these being present is an expected, SKIPPED outcome on Linux CI.
def find_corpus_dir() -> Path | None:
    env = os.environ.get("AAT_STATE_DIR")
    candidates = []
    if env:
        candidates.append(Path(env) / "corpus" / "observations")
    candidates.append(REPO.parent / "aegis-alpha-terminal" / "state" / "corpus" / "observations")
    candidates.append(Path(r"C:\Users\mrthn\aegis-alpha-terminal\state\corpus\observations"))
    for c in candidates:
        try:
            if c.is_dir() and any(c.glob("*.jsonl")):
                return c
        except OSError:
            continue
    return None


EIGHTK_ROWS = REPO / "backend" / "data" / "optimus" / "edgar_8k" / "eightk_rows.jsonl"
EVENT_TABLE_V1 = REPO / "backend" / "data" / "optimus" / "events" / "event_table_v1.parquet"
STOCKNAMES = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__stocknames_v2.parquet"

#: The three named house eras (`learner/long_panel.py:ERAS`). Quoted for
#: comparability, but this corpus does not fill them -- see the era note in
#: the receipt.
HOUSE_ERAS = (("1999-2007", 1999, 2007), ("2008-2015", 2008, 2015), ("2016-2024", 2016, 2024))

DEFAULT_SEED = 20260907
MIN_FREE_GB = 2.0


def log(*a):
    print(*a, flush=True)


def _mem_guard(note: str) -> dict:
    g = free_gb()
    if g is not None and g < MIN_FREE_GB:
        raise MemoryError(f"REFUSED before {note}: {g} GB free < {MIN_FREE_GB} GB floor")
    return {"free_gb_before_" + note.replace(" ", "_"): g}


# ------------------------------------------------------------- corpus loading

def load_news_rows(corpus_dir: Path, tracker: PROV.InputTracker | None = None,
                   max_files: int | None = None) -> pd.DataFrame:
    """One row per (news observation, primary symbol). A moving-target snapshot.

    `symbols[0]` is taken as the row's company -- a multi-symbol wire item is
    attributed to the first-listed name only, so counts here are a (small)
    undercount of true cross-symbol syndication, never an overcount.
    """
    files = sorted(glob.glob(str(corpus_dir / "*.jsonl")))
    if max_files:
        files = files[:max_files]
    recs = []
    for fp in files:
        if tracker is not None:
            tracker.opened(fp, note="corpus observation shard")
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get("kind") != "news":
                        continue
                    syms = r.get("symbols") or []
                    if not syms:
                        continue
                    recs.append({
                        "symbol": syms[0],
                        "title": r.get("title") or "",
                        "body": (r.get("body") or "")[:600],
                        "source": r.get("source"),
                        "independence_group": r.get("independence_group") or r.get("source"),
                        "observed_at": r.get("observed_at"),
                        "effective_at": r.get("effective_at"),
                        "uid": r.get("uid"),
                    })
        except OSError:
            continue
    if not recs:
        return pd.DataFrame(columns=["symbol", "title", "body", "source",
                                     "independence_group", "observed_at",
                                     "effective_at", "uid", "text"])
    df = pd.DataFrame.from_records(recs)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["observed_at"]).reset_index(drop=True)
    df["text"] = (df["title"].fillna("") + " " + df["body"].fillna("")).str.strip()
    df = df[df["text"].str.len() > 0].reset_index(drop=True)
    return df


def eightk_secondary_summary(tracker: PROV.InputTracker | None = None) -> dict:
    """8-K filings: already canonical by construction. No clustering needed."""
    if not EIGHTK_ROWS.is_file():
        return {"status": "ABSENT", "path": str(EIGHTK_ROWS)}
    if tracker is not None:
        tracker.opened(EIGHTK_ROWS, note="8-K filings, one row per accession")
    n = 0
    accessions = set()
    tickers = set()
    with open(EIGHTK_ROWS, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            acc = r.get("accession")
            if acc:
                accessions.add(acc)
            t = r.get("ticker")
            if t:
                tickers.add(t)
    return {
        "status": "OK",
        "rows": n,
        "distinct_accessions": len(accessions),
        "distinct_tickers": len(tickers),
        "compression_ratio": round(n / len(accessions), 4) if accessions else None,
        "note": ("one accession number IS one filing event; SEC EDGAR cannot "
                 "assign the same accession twice, so this pool is canonical "
                 "already and clustering it would find nothing. Included for "
                 "'whatever backfill exists' completeness, not compressed."),
    }


# ---------------------------------------------------------------- clustering

def build_tfidf(text: pd.Series, max_features: int = 4000):
    vec = TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=1,
                          stop_words="english", sublinear_tf=True)
    mat = vec.fit_transform(text.tolist())
    return vec, mat


def cluster_events(df: pd.DataFrame, mat, *, sim_threshold: float = 0.45,
                   window_hours: float = 72.0, novelty_lookback: int = 100) -> pd.DataFrame:
    """Greedy, time-windowed, per-symbol nearest-centroid clustering.

    For each symbol, rows are visited in `observed_at` order. A row joins the
    most similar OPEN event (last member within `window_hours`) if cosine
    similarity to that event's running centroid clears `sim_threshold`, else
    it opens a new event. Events fall out of the "open" pool once their most
    recent member ages past the window, bounding the per-row cost to the
    number of concurrently live stories rather than a name's whole history.

    Returns one row per CANONICAL EVENT: symbol, n_members, member_uids,
    independent_source_count, first_observed_at, last_observed_at,
    dissemination_speed, novelty_vs_company_history, first_for_company.

    Novelty is computed in a SECOND pass, per symbol, comparing each event's
    centroid only to that symbol's OWN prior events (causal: strictly earlier
    `first_observed_at`), capped to the most recent `novelty_lookback` of them
    so a company with thousands of canonical events does not cost O(k^2).
    """
    # TfidfVectorizer defaults to L2-normalised rows, so cosine similarity
    # between a raw row and a normalised centroid is a plain dot product.
    # Per-symbol arrays (positions, centroids, member-index lists) are
    # preallocated with numpy rather than grown as a list of per-event dicts
    # with pandas `.loc` lookups on every row -- profiled on the corpus's
    # densest symbol (SPY, 16,564 rows): the dict-of-lists version cost 84s,
    # 38s of it inside `numpy.linalg.norm`/`numpy.vstack` called once PER ROW
    # and 13s inside repeated `df.loc[list_of_labels]` calls at the end. This
    # version does both jobs with array slicing and a single `.to_numpy()`
    # extraction per symbol, matters at this corpus's scale (one symbol can
    # carry >15,000 raw rows).
    window = pd.Timedelta(hours=window_hours).to_timedelta64()
    has_uid = "uid" in df.columns
    has_permno = "permno" in df.columns
    out_rows = []
    for symbol, g in df.groupby("symbol", sort=False):
        order = g.sort_values("observed_at").index.to_numpy()
        n_rows = len(order)
        sub_dense = np.asarray(mat[order].todense())          # ONE conversion per symbol
        # tz-aware -> naive UTC datetime64[ns]: numpy has no tz dtype, and a
        # `.to_numpy()` straight off a tz-aware Series yields an object array
        # of Timestamps, which defeats every vectorised comparison below.
        times = (pd.DatetimeIndex(df.loc[order, "observed_at"])
                .tz_convert("UTC").tz_localize(None).to_numpy())
        ig_arr = df.loc[order, "independence_group"].to_numpy()
        uid_arr = df.loc[order, "uid"].to_numpy() if has_uid else None
        permno_arr = df.loc[order, "permno"].to_numpy() if has_permno else None

        d = sub_dense.shape[1]
        sum_vecs = np.zeros((n_rows, d), dtype=sub_dense.dtype)   # worst case: every row its own event
        counts = np.zeros(n_rows, dtype=np.int64)
        firsts = np.empty(n_rows, dtype="datetime64[ns]")
        lasts = np.empty(n_rows, dtype="datetime64[ns]")
        member_lists: list[list[int]] = [None] * n_rows          # local (within-symbol) positions
        n_events = 0
        open_idx: list[int] = []

        for li in range(n_rows):
            t = times[li]
            if open_idx:
                open_idx = [i for i in open_idx if (t - lasts[i]) <= window]
            v = sub_dense[li]
            best_i, best_sim = None, 0.0
            if open_idx:
                oi = np.asarray(open_idx)
                cent = sum_vecs[oi] / counts[oi, None]
                norms = np.linalg.norm(cent, axis=1) + 1e-12
                sims = (cent @ v) / norms
                j = int(np.argmax(sims))
                best_i, best_sim = int(oi[j]), float(sims[j])
            if best_i is not None and best_sim >= sim_threshold:
                sum_vecs[best_i] += v
                counts[best_i] += 1
                lasts[best_i] = t
                member_lists[best_i].append(li)
            else:
                sum_vecs[n_events] = v
                counts[n_events] = 1
                firsts[n_events] = t
                lasts[n_events] = t
                member_lists[n_events] = [li]
                open_idx.append(n_events)
                n_events += 1

        sum_vecs = sum_vecs[:n_events]
        counts = counts[:n_events]
        firsts, lasts = firsts[:n_events], lasts[:n_events]
        member_lists = member_lists[:n_events]
        centroids = sum_vecs / counts[:, None]
        cent_norms = np.linalg.norm(centroids, axis=1) + 1e-12
        centroids_normed = centroids / cent_norms[:, None]

        for i in range(n_events):
            lo = max(0, i - novelty_lookback)
            if i == 0:
                novelty, first_for_company = 1.0, True
            else:
                sims = centroids_normed[lo:i] @ centroids_normed[i]
                novelty, first_for_company = float(1.0 - sims.max()), False
            n = int(counts[i])
            first_ts, last_ts = pd.Timestamp(firsts[i]), pd.Timestamp(lasts[i])
            elapsed_h = (last_ts - first_ts).total_seconds() / 3600.0
            speed = (n - 1) / elapsed_h if n > 1 and elapsed_h > 0 else (np.nan if n == 1 else None)
            members_local = member_lists[i]
            permno_val = None
            if has_permno:
                p = permno_arr[members_local]
                p = p[pd.notna(p)]
                if len(p):
                    vals, cts = np.unique(p, return_counts=True)
                    permno_val = vals[int(np.argmax(cts))]
            out_rows.append({
                "symbol": symbol,
                "n_members": n,
                "member_uids": uid_arr[members_local].tolist() if has_uid else None,
                "independent_source_count": int(len(set(ig_arr[members_local].tolist()))),
                "first_observed_at": first_ts,
                "last_observed_at": last_ts,
                "dissemination_speed_sources_per_hour": (
                    None if speed is None else (None if (isinstance(speed, float) and np.isnan(speed))
                                                else round(float(speed), 4))),
                "novelty_vs_company_history": round(novelty, 6),
                "first_for_company": first_for_company,
                "permno": permno_val,
            })
    return pd.DataFrame(out_rows)


# --------------------------------------------------------- the permno bridge

def build_ticker_permno_crosswalk(tracker: PROV.InputTracker | None = None) -> pd.DataFrame | None:
    """PIT ticker -> permno intervals from `crsp__stocknames_v2.parquet`.

    Only used on the FALLBACK path (event_table_v1 absent/empty): N4's table
    already carries a resolved `permno` per row and this crosswalk is not
    needed when it is present. Returns None, not an empty frame, when the
    source file is missing -- the caller must be able to tell "no crosswalk
    exists" from "the crosswalk resolved nothing".
    """
    if not STOCKNAMES.is_file():
        return None
    if tracker is not None:
        tracker.opened(STOCKNAMES, note="CRSP ticker/permno name-history intervals")
    sn = pd.read_parquet(STOCKNAMES, columns=["permno", "ticker", "namedt", "nameenddt"])
    sn["namedt"] = pd.to_datetime(sn["namedt"], errors="coerce")
    sn["nameenddt"] = pd.to_datetime(sn["nameenddt"], errors="coerce")
    return sn


def permno_as_of(crosswalk: pd.DataFrame, ticker: str, as_of) -> int | None:
    if crosswalk is None:
        return None
    rows = crosswalk[crosswalk["ticker"] == ticker]
    if rows.empty:
        return None
    as_of = pd.Timestamp(as_of)
    hit = rows[(rows["namedt"] <= as_of)
              & (rows["nameenddt"].isna() | (rows["nameenddt"] >= as_of))]
    if hit.empty:
        return None
    return int(hit.iloc[0]["permno"])


# ------------------------------------------------------- the novelty test

def load_event_table_v1_news(tracker: PROV.InputTracker | None = None) -> pd.DataFrame:
    """N4's event table, news rows only, reshaped to this file's column names.

    `event_table_v1.parquet` carries no body text (by its own design, see its
    manifest) -- only `title` -- so clustering on it is title-only TF-IDF,
    coarser than the full-corpus pass above. `permno` is ALREADY resolved
    (`permno_link_method`); rows where it is unresolved keep permno=NaN and
    fall out of the forward-return join later, not out of the clustering.
    """
    if not EVENT_TABLE_V1.is_file():
        return pd.DataFrame()
    if tracker is not None:
        tracker.opened(EVENT_TABLE_V1, note="N4 event table (news rows for the novelty test)")
    ev = pd.read_parquet(EVENT_TABLE_V1,
                         columns=["permno", "symbol", "event_type", "observed_at_utc",
                                 "title", "independence_group", "year"])
    news = ev[ev["event_type"] == "news"].copy()
    if news.empty:
        return news
    news = news.rename(columns={"symbol": "symbol", "title": "title",
                               "observed_at_utc": "observed_at"})
    news["body"] = ""
    news["source"] = "event_table_v1"
    news["uid"] = news.index.astype(str)
    news["observed_at"] = pd.to_datetime(news["observed_at"], utc=True, errors="coerce")
    news = news.dropna(subset=["observed_at"])
    news["text"] = news["title"].fillna("")
    news = news[news["text"].str.len() > 0].reset_index(drop=True)
    return news


def monthly_permutation_null(events: pd.DataFrame, *, n_draws: int, seed: int) -> dict:
    """IC(novelty, fwd_excess) under WITHIN-MONTH shuffles of novelty.

    Holds the calendar month fixed on every draw (S24: a shuffled-date null
    that does not hold the day/month fixed measures the calendar, not the
    feature) -- only which event within a month owns which novelty value
    moves. Requires `MIN_DRAWS` (learner/nullbar.py) usable draws or refuses
    via `NB.CANNOT_DETERMINE`.
    """
    sub = events.dropna(subset=["novelty_vs_company_history", "fwd_excess_vw_1m", "month"]).copy()
    if len(sub) < 10:
        return {"verdict": NB.CANNOT_DETERMINE, "why": f"only {len(sub)} matched rows"}
    obs_ic, obs_p = spearmanr(sub["novelty_vs_company_history"], sub["fwd_excess_vw_1m"])
    rng = np.random.default_rng(seed)
    months = sub["month"].to_numpy()
    novelty = sub["novelty_vs_company_history"].to_numpy()
    target = sub["fwd_excess_vw_1m"].to_numpy()
    pos_by_month = {}
    for i, m in enumerate(months):
        pos_by_month.setdefault(m, []).append(i)
    draws = []
    for _ in range(n_draws):
        shuffled = novelty.copy()
        for idxs in pos_by_month.values():
            if len(idxs) > 1:
                shuffled[idxs] = rng.permutation(novelty[idxs])
        ic, _ = spearmanr(shuffled, target)
        draws.append(float(ic) if ic == ic else np.nan)
    arr = np.asarray([d for d in draws if d == d], dtype="float64")
    result = {
        "n_matched_events": int(len(sub)),
        "observed_ic": round(float(obs_ic), 6) if obs_ic == obs_ic else None,
        "observed_p_naive": round(float(obs_p), 6) if obs_p == obs_p else None,
        "n_draws_requested": int(n_draws),
        "n_draws_usable": int(arr.size),
        "null_bar": NB.MODEL_NULL_BAR if arr.size >= NB.MIN_DRAWS else NB.CANNOT_DETERMINE,
    }
    if arr.size < NB.MIN_DRAWS or obs_ic != obs_ic:
        result["verdict"] = (f"{NB.CANNOT_DETERMINE} (usable draws {arr.size} < "
                             f"{NB.MIN_DRAWS}, or observed IC undefined)")
        return result
    result["null_summary"] = NB.summarise_null(arr)
    result["percentile_of_observed"] = round(NB.percentile_of(float(obs_ic), arr), 4)
    result["p_one_sided"] = round(NB.p_one_sided(float(obs_ic), arr), 4)
    result["verdict"] = "CLEARS_MODEL_NULL" if result["p_one_sided"] <= 0.05 else "WITHIN_MODEL_NULL"
    return result


def year_table(events: pd.DataFrame) -> dict:
    """IC by calendar year -- the era table this corpus can actually fill.

    The house's three named eras (`learner/long_panel.ERAS`) are 1999-2007 /
    2008-2015 / 2016-2024. This corpus's usable (forward-return-matured)
    window is 2015-2016 only, so it touches exactly TWO of the three named
    eras (one year each) and the third (1999-2007) is empty by construction --
    forcing the standard table would silently report an empty era as a zero
    rather than as absent. Reported here by calendar YEAR instead, which is
    the honest substitute available, plus a note mapping each year to its
    house era for a reader who wants the standard names.
    """
    sub = events.dropna(subset=["novelty_vs_company_history", "fwd_excess_vw_1m", "month"])
    out = {}
    for yr, g in sub.groupby(sub["month"].str.slice(0, 4)):
        if len(g) < 8:
            out[yr] = {"n": int(len(g)), "ic": None, "note": "fewer than 8 matched events"}
            continue
        ic, p = spearmanr(g["novelty_vs_company_history"], g["fwd_excess_vw_1m"])
        out[yr] = {"n": int(len(g)), "ic": round(float(ic), 6) if ic == ic else None,
                  "p_naive": round(float(p), 6) if p == p else None}
    house_era_map = {}
    for yr in out:
        for name, lo, hi in HOUSE_ERAS:
            if lo <= int(yr) <= hi:
                house_era_map[yr] = name
    signs = [1 if (v.get("ic") or 0) > 0 else (-1 if (v.get("ic") or 0) < 0 else 0)
            for v in out.values() if v.get("ic") is not None]
    return {
        "by_year": out,
        "house_era_of_each_year": house_era_map,
        "note": ("the standard three-era table (1999-2007/2008-2015/2016-2024) cannot be "
                "filled: this corpus's forward-return-matured window is 2015-2016 only, "
                "touching one year each of the last two named eras and none of the first. "
                "Reported by calendar year; era-consistency (>=2 of 3 same sign) is NOT "
                "assessable on 1-2 usable years and is not claimed."),
        "eras_measured": len(signs),
        "same_sign_years": len(signs) >= 2 and len(set(signs)) == 1,
    }


# --------------------------------------------------------------- NIM probe

def probe_nemotron(timeout_s: float = 10.0, batch: int = 3) -> dict:
    """One small, bounded reachability check of the NIM embeddings endpoint.

    Not part of the production clustering path (see the module docstring).
    Returns a structured result and NEVER raises -- a probe that can crash the
    receipt build is worse than one that reports CANNOT_DETERMINE. Requires
    `NVIDIA_API_KEY`; absent key is reported, never guessed at.
    """
    import os as _os
    try:
        import backend.config  # noqa: F401  side effect only: gated dotenv load
    except Exception:                                                  # noqa: BLE001
        pass
    key = _os.environ.get("NVIDIA_API_KEY")
    if not key:
        return {"status": "ABSENT", "why": "NVIDIA_API_KEY not set"}
    base = _os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    try:
        import requests
        texts = [f"probe text {i} for reachability only" for i in range(batch)]
        payload = {"input": texts, "model": "nvidia/nemotron-3-embed-1b", "input_type": "query"}
        t0 = time.time()
        r = requests.post(base.rstrip("/") + "/embeddings",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json=payload, timeout=timeout_s)
        ms = round((time.time() - t0) * 1000, 1)
        if r.status_code != 200:
            return {"status": "FAIL", "http_code": r.status_code, "latency_ms": ms,
                    "detail": r.text[:200]}
        data = r.json().get("data") or []
        dim = len(data[0]["embedding"]) if data else None
        return {"status": "OK", "latency_ms": ms, "n_embeddings": len(data), "dim": dim,
                "model": "nvidia/nemotron-3-embed-1b", "batch_requested": batch}
    except Exception as exc:                                          # noqa: BLE001
        return {"status": "CANNOT_DETERMINE", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}


# ------------------------------------------------------------------- main

def main() -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(RECEIPT))
    ap.add_argument("--sim-threshold", type=float, default=0.45)
    ap.add_argument("--window-hours", type=float, default=72.0)
    ap.add_argument("--novelty-lookback", type=int, default=100)
    ap.add_argument("--max-features", type=int, default=4000)
    ap.add_argument("--n-null-draws", type=int, default=200)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--quick", action="store_true", help="smoke-sized run: fewer files, fewer draws")
    ap.add_argument("--skip-nim-probe", action="store_true")
    args = ap.parse_args()

    t_start = time.time()
    tracker = PROV.InputTracker()
    mem_before = _mem_guard("event compression run")
    log(f"[N5.1] free_gb={mem_before}")

    receipt: dict = {
        "job": "N5_event_compression",
        "lane": "N5.1",
        "licence": "PRODUCT_EXPERIMENT",
        "snapshot_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {"sim_threshold": args.sim_threshold, "window_hours": args.window_hours,
                  "novelty_lookback": args.novelty_lookback, "max_features": args.max_features,
                  "n_null_draws": args.n_null_draws, "seed": args.seed},
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
    }

    # -------------------------------------------------- corpus discovery
    corpus_dir = find_corpus_dir()
    receipt["corpus_dir_found"] = str(corpus_dir) if corpus_dir else None
    if corpus_dir is None:
        receipt["status"] = "SKIPPED_NO_CORPUS"
        receipt["why"] = ("no terminal-repo corpus directory found under AAT_STATE_DIR, the "
                          "sibling checkout, or the known machine path. Expected on Linux CI "
                          "and on any machine without the aegis-alpha-terminal checkout.")
        receipt["eightk_secondary"] = eightk_secondary_summary(tracker)
        receipt["nemotron_probe"] = ({"status": "SKIPPED"} if args.skip_nim_probe
                                     else probe_nemotron())
        PROV.attach(receipt, sys.argv, vars(args), tracker)
        _write(receipt, args.out)
        return receipt

    max_files = 6 if args.quick else None
    news = load_news_rows(corpus_dir, tracker, max_files=max_files)
    receipt["corpus_snapshot"] = {
        "files_read": max_files or len(list(corpus_dir.glob("*.jsonl"))),
        "news_rows_read": int(len(news)),
        "distinct_symbols": int(news["symbol"].nunique()) if len(news) else 0,
        "observed_at_min": str(news["observed_at"].min()) if len(news) else None,
        "observed_at_max": str(news["observed_at"].max()) if len(news) else None,
    }
    if news.empty:
        receipt["status"] = "SKIPPED_EMPTY_CORPUS"
        receipt["eightk_secondary"] = eightk_secondary_summary(tracker)
        PROV.attach(receipt, sys.argv, vars(args), tracker)
        _write(receipt, args.out)
        return receipt

    # -------------------------------------------------- production clustering
    log(f"[N5.1] clustering {len(news)} news rows over "
        f"{news['symbol'].nunique()} symbols")
    vec, mat = build_tfidf(news["text"], max_features=args.max_features)
    events = cluster_events(news, mat, sim_threshold=args.sim_threshold,
                            window_hours=args.window_hours,
                            novelty_lookback=args.novelty_lookback)
    n_raw, n_events = len(news), len(events)
    per_symbol = (news.groupby("symbol").size().rename("raw_rows")
                 .to_frame().join(events.groupby("symbol").size().rename("n_events"))
                 .assign(compression_ratio=lambda d: (d["raw_rows"] / d["n_events"]).round(3))
                 .sort_values("raw_rows", ascending=False))
    receipt["compression"] = {
        "raw_news_rows": n_raw,
        "n_canonical_events": n_events,
        "compression_ratio": round(n_raw / n_events, 4) if n_events else None,
        "note": ("TF-IDF title+body (600 chars), per-symbol time-windowed greedy nearest-"
                "centroid clustering (sim_threshold={:.2f}, window={:.0f}h). Catches exact-"
                "reformatted duplicate headlines; MISSES same-event stories with no shared "
                "vocabulary -- this ratio is a LOWER BOUND on true syndication compression, "
                "not a point estimate.").format(args.sim_threshold, args.window_hours),
        "top_symbols_by_raw_rows": {
            str(k): {"raw_rows": int(v["raw_rows"]), "n_events": int(v["n_events"]),
                    "compression_ratio": float(v["compression_ratio"])}
            for k, v in per_symbol.head(10).to_dict("index").items()
        },
        "independent_source_count_summary": {
            "mean": round(float(events["independent_source_count"].mean()), 3),
            "share_multi_source": round(
                float((events["independent_source_count"] > 1).mean()), 4),
        },
        "dissemination_speed_summary": {
            "n_with_speed": int(events["dissemination_speed_sources_per_hour"].notna().sum()),
            "median_sources_per_hour": (
                round(float(events["dissemination_speed_sources_per_hour"].dropna().median()), 4)
                if events["dissemination_speed_sources_per_hour"].notna().any() else None),
        },
    }
    receipt["eightk_secondary"] = eightk_secondary_summary(tracker)

    # -------------------------------------------------- the novelty test
    ev_table_news = load_event_table_v1_news(tracker)
    novelty_source = None
    test_events = pd.DataFrame()
    if not ev_table_news.empty:
        novelty_source = "event_table_v1 (N4 lane; permno pre-resolved via crsp_stocknames_interval)"
        log(f"[N5.1] novelty test: clustering {len(ev_table_news)} event_table_v1 news rows")
        vec2, mat2 = build_tfidf(ev_table_news["text"], max_features=args.max_features)
        test_events = cluster_events(ev_table_news, mat2, sim_threshold=args.sim_threshold,
                                     window_hours=args.window_hours,
                                     novelty_lookback=args.novelty_lookback)
    else:
        novelty_source = "FALLBACK: corpus's own forward returns (event_table_v1 absent/empty)"
        log("[N5.1] event_table_v1 absent or has no news rows -- falling back to the corpus's "
            "own forward returns, per the task's explicit fallback instruction")
        test_events = events.copy()
        crosswalk = build_ticker_permno_crosswalk(tracker)
        if crosswalk is not None:
            test_events["permno"] = [
                permno_as_of(crosswalk, sym, ts)
                for sym, ts in zip(test_events["symbol"], test_events["first_observed_at"])
            ]
        else:
            novelty_source += " (no permno crosswalk found either -- permno stays whatever clustering set)"

    if test_events.empty or "permno" not in test_events.columns:
        receipt["novelty_test"] = {"status": "CANNOT_DETERMINE", "why": "no test events / no permno column",
                                   "novelty_source": novelty_source}
    else:
        test_events = test_events.dropna(subset=["permno"]).copy()
        test_events["permno"] = test_events["permno"].astype("int64", errors="ignore")
        test_events["month"] = pd.to_datetime(test_events["first_observed_at"]).dt.strftime("%Y-%m")
        mem_chk = _mem_guard("train_table read")
        log(f"[N5.1] {mem_chk}")
        tt = pd.read_parquet(D.TRAIN_TABLE, columns=["permno", "month", "excess_vw_1m"])
        tracker.opened(D.TRAIN_TABLE, note="monthly forward-excess-return target (through 2024-12)")
        tt = tt.rename(columns={"excess_vw_1m": "fwd_excess_vw_1m"})
        try:
            test_events["permno"] = pd.to_numeric(test_events["permno"], errors="coerce")
            tt["permno"] = pd.to_numeric(tt["permno"], errors="coerce")
        except Exception:                                             # noqa: BLE001
            pass
        merged = test_events.merge(tt, on=["permno", "month"], how="left")
        n_draws = 64 if args.quick else args.n_null_draws
        null_result = monthly_permutation_null(merged, n_draws=n_draws, seed=args.seed)
        yr_table = year_table(merged)
        receipt["novelty_test"] = {
            "novelty_source": novelty_source,
            "n_canonical_test_events": int(len(test_events)),
            "n_with_permno": int(test_events["permno"].notna().sum()),
            "n_matched_to_forward_return": int(merged["fwd_excess_vw_1m"].notna().sum()),
            "forward_return_ceiling_note": ("train_table.parquet ends 2024-12; only the "
                "corpus's 2015-2016 vintage has a matured forward return in-house. The "
                "2025-2026 majority of the corpus is untestable against this target until "
                "a later panel pull exists."),
            "family_id": "n5-event-compression-novelty",
            "family_size": 1,
            "null_test": null_result,
            "era_table": yr_table,
            "verdict": null_result.get("verdict", NB.CANNOT_DETERMINE),
            "verdict_note": ("this is a single-feature screen against one target, not a book: "
                "DSR/PBO/SPA (which deflate a SHARPE) do not apply. The bar here is the "
                "model-null percentile from learner/nullbar.py. Per house convention a "
                "screen never reaches NOVEL regardless of p-value."),
        }

    # -------------------------------------------------- NIM reachability
    receipt["nemotron_probe"] = ({"status": "SKIPPED"} if args.skip_nim_probe
                                 else probe_nemotron())

    receipt["status"] = "OK"
    receipt["runtime_seconds"] = round(time.time() - t_start, 1)
    receipt["memory"] = {**mem_before, "free_gb_after": free_gb()}
    PROV.attach(receipt, sys.argv, vars(args), tracker)
    _write(receipt, args.out)
    return receipt


def _write(receipt: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return str(o)

    with open(p, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, default=_default)
    log(f"[N5.1] wrote {p}")


if __name__ == "__main__":
    main()
