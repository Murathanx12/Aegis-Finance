"""U1/U2/U3 -- event archetypes -> typed hypotheses -> graded, on the real tape.

    python -m scripts.u_archetypes_run --embedder hash --quick     # offline
    python -m scripts.u_archetypes_run --embedder nim              # full run

WHAT IT DOES, IN ORDER (and the order is the point)
===================================================
  U3 FIRST. `--mode u3` plants a synthetic event family with a drift computed
     as a declared multiple of the tape's own MDE, and a NULL family with no
     drift, into the REAL frame, then runs the whole pipeline over it. The
     planted family must be clustered, emitted and recovered; the null must
     read noise. Nothing in the real run is believable before this passes.
  U1 archetypes: embed the canonical event titles, cluster, report silhouette,
     sizes and reseed/resample stability.
  LABEL each cluster ONCE with a FREE model (NVIDIA NIM via
     `backend.services.free_inference`; $0.00). The label is a DESCRIPTION.
     The members are the evidence, and nothing downstream reads the label.
  U2 emit typed hypotheses and route them through
     `research_gym.scope.corpse_check` -- the mechanistic comparator -- against
     a corpse register DERIVED from `backend/data/signal_registry.yaml` (so it
     cannot drift from the registry).
  GRADE the first ten, family = 10, beta printed first, one observation per
     DATE BLOCK, three eras never pooled, MDE and the power check BEFORE the
     confirmation, BH-FDR to screen and Holm to export.

WHAT THE TAPE ACTUALLY SUPPORTS, STATED UP FRONT
================================================
`event_table_v1.parquet` holds 993,005 rows, but the rows that carry BOTH a
headline (the thing an embedder can read) and a CRSP permno (the thing a return
can be computed for) number about 21.8k, across ~91 names, concentrated in
2015-2018. That is the corpus. It is mega-cap-tech-heavy by construction
(the terminal repo's 156-symbol news corpus), so ANY positive result here is a
regime finding about those names in those years until the E-lane backfill
widens the tape. This is a stated limit, not a thing to hide.

LICENCE: PRODUCT_EXPERIMENT. Places nothing, recommends nothing, sizes nothing.
LLM SPEND: $0.00 -- the embedder and the labeller are both free endpoints, and
the DeepSeek balance is deliberately untouched.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services import archetypes as AR
from backend.services import receipt_provenance as RP
from backend.services.research_gym import scope as SC

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "backend/data/optimus/events/event_table_v1.parquet"
WRDS = ROOT / "backend/data/optimus/wrds"
BETA = ROOT / "backend/data/optimus/learner/beta_panel.parquet"
FF = ROOT / "backend/data/ff_daily_pinned.csv.gz"
REGISTRY = ROOT / "backend/data/signal_registry.yaml"
OUT_DIR = ROOT / "backend/data/optimus/archetypes"

# ── DECLARED BEFORE ANY RESULT IS SEEN ─────────────────────────────────────
K_GRID = (6, 8, 10, 12, 16, 20, 24)
PRIMARY_HORIZON_DAYS = 5          # one horizon for all ten: no horizon search
SECONDARY_HORIZONS = (1, 21)      # EXPLORATORY, screened separately, not in the family
FAMILY_SIZE = 10
RANK_RULE = "archetype size, descending"
ERAS = {
    "E1_2015H1-2016H1": ("2015-01", "2016-06"),
    "E2_2016H2-2017H1": ("2016-07", "2017-06"),
    "E3_2017H2-2018H2": ("2017-07", "2018-12"),
}
PLANT_MULTIPLE_OF_MDE = 3.0
PLANT_N = 400
SEED = 20260908

# The plant is REALISTIC HEADLINES from two semantically distinct event
# families, not two piles of rare words. Run 1 (2026-09-08, receipt
# `U_archetypes_nim_run01_RARE_TOKEN_PLANT_FAILED.json`) used rare-token
# vocabularies and `nemotron-3-embed-1b` put BOTH families in ONE cluster of
# exactly 800 at purity 0.50 -- it had separated register ("not a financial
# headline") and was blind to WHICH nonsense a row was. A semantic embedder
# needs a semantic plant.
_PLANTED_TEMPLATES = (
    "{co} issues a voluntary recall of {n} units after a safety review",
    "{co} halts shipments pending a product safety investigation",
    "{co} expands its recall to additional production lots citing a defect rate",
    "Regulators open an inquiry into defect reports at {co}",
    "{co} says recall and remediation costs will be absorbed this quarter",
    "{co} pauses one production line while a defect is traced",
)
_NULL_TEMPLATES = (
    "{co} appoints a new chief operating officer effective next quarter",
    "{co} names an interim finance chief while the search continues",
    "{co} board elects a new independent director",
    "{co} promotes its head of operations to president",
    "{co} announces a leadership transition as an executive retires",
    "{co} adds two members to its senior management team",
)
_PLANTED_VOCAB = ("thermionic", "lattice", "recalibration", "quadrature",
                  "isomorph", "bezel", "wavefront", "kestrel", "obsidian",
                  "sublimation")
_NULL_VOCAB = ("ferrous", "palindromic", "hexagonal", "trellis", "vellum",
               "cadence", "marmoset", "chromatic", "silica", "tundra")


# ── corpse register, DERIVED from the signal registry ──────────────────────
#
# Hand-copying a corpse list is how it goes stale. This derives it, and the
# only hand-written part is the map from a signal id to the FEATURE its rule
# keys on -- which is the shared vocabulary that lets the mechanistic
# comparator collide at all.

CORPSE_FEATURE: dict[str, str] = {
    "analyst_target_upside_xs": "analyst_target_upside",
    "value_btm": "accounting_value_rank",
    "accruals": "accounting_accrual_rank",
    "issuance_payout": "accounting_issuance_rank",
    "momentum_12_1": "trailing_return_rank",
    "momentum_spillover": "linked_name_trailing_return_rank",
    "reversal_dip": "trailing_return_rank",
    "trailing_stop_rule": "drawdown_from_entry",
    "inst_ownership_level_13f": "inst_ownership_change",
    "short_interest_level": "short_interest_level",
    "earnings_surprise_monthly": "earnings_surprise_sue",
    "fda_approval_monthly": "regulatory_event_flag",
    "options_ranking_raw": "options_surface_stat",
    "llm_stock_selection": "llm_ordering",
}

#: An execution rule is not a cross-sectional picker and must not share its
#: action pair, or every stock-picking hypothesis would inherit the stop rule
#: as its parent.
CORPSE_ACTIONS: dict[str, tuple[str, str]] = {
    "trailing_stop_rule": ("trailing_stop_exit", "hold_to_horizon"),
}

#: REJECTED / PERVERSE are POWERED evidence against the rule -> they CLOSE.
#: SHELF is "IC clears, the book does not" -- absence of a demonstrated book,
#: not powered evidence against the mechanism -> it blocks nothing and is
#: reported in `corpses_that_block_nothing`.
GRADE_TO_VERDICT = {
    "REJECTED": SC.REFUTED_IN_SCOPE,
    "PERVERSE": SC.REFUTED_IN_SCOPE,
    "SHELF": SC.NOT_DETECTABLE_IN_SCOPE,
}


def load_corpses(path: Path = REGISTRY) -> tuple[list[SC.Corpse], dict]:
    import yaml
    TRACKER.opened(path, note="the corpse register is derived from this")
    reg = yaml.safe_load(io.open(path, encoding="utf-8"))
    out, skipped = [], []
    for s in sorted(reg["signals"], key=lambda r: str(r.get("signal_id"))):
        if s.get("research_status") != "CLOSED":
            continue
        sid = str(s.get("signal_id"))
        feat = CORPSE_FEATURE.get(sid)
        if feat is None:
            skipped.append(sid)
            continue
        verdict = GRADE_TO_VERDICT.get(str(s.get("evidence_grade")),
                                       SC.NOT_DETECTABLE_IN_SCOPE)
        act = CORPSE_ACTIONS.get(sid, ("long_top_quintile_equal_weight",
                                       "hold_market"))
        out.append(SC.Corpse(
            mechanism_id=sid,
            precursor={"all": [
                {"feature": feat, "op": ">=", "value": "top_quintile"},
                {"feature": "rebalance_frequency", "op": "==",
                 "value": "monthly"}]},
            proposed_action=act[0], default_action=act[1],
            verdict=verdict, scope=SC.AFFECTED))
    meta = {"source": str(path.relative_to(ROOT)),
            "n_closed_signals_in_registry":
                sum(1 for s in reg["signals"]
                    if s.get("research_status") == "CLOSED"),
            "n_corpses_built": len(out),
            "n_blocking": sum(1 for c in out if c.blocks_anything),
            "closed_signals_without_a_feature_map": sorted(skipped),
            "grade_to_verdict": {k: v for k, v in GRADE_TO_VERDICT.items()}}
    return out, meta


# ── data ───────────────────────────────────────────────────────────────────

TRACKER = RP.InputTracker()


def load_events(quick: bool = False) -> pd.DataFrame:
    """News rows with a headline AND a permno. Those two together are the
    corpus; everything else in the event table is untestable by this route and
    the receipt says so."""
    TRACKER.opened(EVENTS, note="the event table")
    df = pd.read_parquet(EVENTS, columns=[
        "permno", "symbol", "event_type", "observed_at_utc",
        "observed_at_precision", "source", "title", "year"])
    n_all = len(df)
    df = df[df["title"].notna() & df["permno"].notna()].copy()
    df["permno"] = df["permno"].astype("int64")
    df["observed_date"] = pd.to_datetime(
        df["observed_at_utc"], utc=True).dt.tz_convert("UTC").dt.normalize()
    df = df[(df["observed_date"] >= "2015-01-01")
            & (df["observed_date"] <= "2024-11-01")]
    df = df.sort_values("observed_at_utc").reset_index(drop=True)
    df["event_id"] = ["EV-%06d" % i for i in range(len(df))]
    if quick:
        df = df.iloc[:: max(1, len(df) // 3000)].reset_index(drop=True)
    df.attrs["n_all_rows_in_event_table"] = n_all
    return df


def load_dsf(years: list[int], permnos: set[int]) -> pd.DataFrame:
    frames = []
    for y in years:
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            continue
        TRACKER.opened(p, note="CRSP daily stock file")
        d = pd.read_parquet(p, columns=["permno", "date", "ret", "prc",
                                        "shrout"])
        d = d[d["permno"].isin(permnos)]
        frames.append(d)
    if not frames:
        raise SystemExit("REFUSED: no crsp_dsf_*.parquet covering the corpus")
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d["mcap"] = (d["prc"].abs() * d["shrout"]).astype("float64")
    return d.sort_values(["permno", "date"]).reset_index(drop=True)


def load_market() -> pd.Series:
    TRACKER.opened(FF, note="Ken French daily factors, pinned vintage")
    ff = pd.read_csv(FF)
    ff["Date"] = pd.to_datetime(ff["Date"])
    m = (ff["Mkt-RF"].astype("float64") + ff["RF"].astype("float64"))
    return pd.Series(m.to_numpy(), index=ff["Date"]).dropna()


def build_frame(ev: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Attach the forward h-day return, the market leg, the pre-event beta and
    the market cap to every event.

    PIT: entry is the CLOSE of the first trading day STRICTLY AFTER the day the
    row became available (`observed_at_utc`). That is deliberately conservative
    -- a headline stamped 09:00 could have been traded the same session -- and
    the conservative side is the only side a PRODUCT_EXPERIMENT may err on.
    """
    permnos = set(ev["permno"].unique().tolist())
    yrs = sorted({int(y) for y in ev["observed_date"].dt.year.unique()})
    yrs = sorted(set(yrs + [y + 1 for y in yrs]))
    dsf = load_dsf(yrs, permnos)
    mkt = load_market()

    # Per-permno forward compounded return over the next `horizon` sessions.
    # A missing CRSP daily return (~1.2% of rows: halts, no trade) must NOT be
    # allowed into a cumsum -- one NaN poisons every later day for that permno
    # and the events silently vanish. It is treated as a zero-return day and
    # the count is REPORTED, because a silent drop is the house failure mode.
    dsf = dsf.copy()
    dsf["ret"] = dsf["ret"].astype("float64")
    n_nan_ret = int(dsf["ret"].isna().sum())
    logr = np.log1p(dsf["ret"].clip(lower=-0.99)).fillna(0.0)
    dsf["cum"] = logr.groupby(dsf["permno"], sort=False).cumsum()
    dsf["fwd"] = np.expm1(
        dsf.groupby("permno", sort=False)["cum"].shift(-horizon) - dsf["cum"])

    mlog = np.log1p(mkt.clip(lower=-0.99)).cumsum()
    mfwd = np.expm1(mlog.shift(-horizon) - mlog)

    TRACKER.opened(BETA, note="pre-event beta panel")
    beta = pd.read_parquet(BETA)
    beta["date"] = pd.to_datetime(beta["date"])
    beta = beta.sort_values(["permno", "date"])

    rows = []
    drops = {"no_permno_in_dsf": 0, "entry_past_end_of_tape": 0,
             "forward_return_not_finite": 0, "market_date_missing": 0,
             "market_forward_not_finite": 0}
    dsf_idx = {p: d.reset_index(drop=True)
               for p, d in dsf.groupby("permno", sort=False)}
    beta_idx = {p: d.reset_index(drop=True)
                for p, d in beta.groupby("permno", sort=False)}
    mkt_dates = mfwd.index.to_numpy()
    for r in ev.itertuples(index=False):
        d = dsf_idx.get(int(r.permno))
        if d is None:
            drops["no_permno_in_dsf"] += 1
            continue
        pos = int(np.searchsorted(d["date"].to_numpy(),
                                  np.datetime64(r.observed_date.tz_localize(None)),
                                  side="right"))
        if pos >= len(d):
            drops["entry_past_end_of_tape"] += 1
            continue
        entry = d["date"].iloc[pos]
        fwd_i = d["fwd"].iloc[pos]
        if not np.isfinite(fwd_i):
            drops["forward_return_not_finite"] += 1
            continue
        mp = int(np.searchsorted(mkt_dates, np.datetime64(entry), side="left"))
        if mp >= len(mkt_dates) or mkt_dates[mp] != np.datetime64(entry):
            drops["market_date_missing"] += 1
            continue
        fwd_m = float(mfwd.iloc[mp])
        if not np.isfinite(fwd_m):
            drops["market_forward_not_finite"] += 1
            continue
        b = beta_idx.get(int(r.permno))
        bv = np.nan
        if b is not None:
            bp = int(np.searchsorted(b["date"].to_numpy(),
                                     np.datetime64(entry), side="right")) - 1
            if bp >= 0:
                bv = float(b["beta_pre"].iloc[bp])
        rows.append((r.event_id, int(r.permno), r.symbol, r.title,
                     entry, float(fwd_i), fwd_m,
                     (1.0 if not np.isfinite(bv) else bv),
                     float(d["mcap"].iloc[pos]) if np.isfinite(
                         d["mcap"].iloc[pos]) else np.nan))
    out = pd.DataFrame(rows, columns=["event_id", "permno", "symbol", "title",
                                      "entry_date", "raw", "mkt", "beta",
                                      "mcap"])
    out["ar"] = out["raw"] - out["beta"] * out["mkt"]
    out["block"] = out["entry_date"].dt.strftime("%Y-%m")
    out.attrs["drops"] = drops
    out.attrs["n_nan_daily_ret_in_dsf"] = n_nan_ret
    out.attrs["n_events_in"] = int(len(ev))
    return out


def matched_control(frame: pd.DataFrame, dsf_years: list[int],
                    horizon: int, seed: int = SEED) -> pd.DataFrame:
    """Same NAME, same MONTH, a session with no event of any kind in the
    window. The informative unit is winner vs matched loser, never a gallery of
    survivors -- and the cheapest version of that here is 'this name in this
    month WITHOUT the event'.
    """
    rng = np.random.default_rng(seed)
    permnos = set(frame["permno"].unique().tolist())
    dsf = load_dsf(dsf_years, permnos)
    logr = np.log1p(dsf["ret"].astype("float64").clip(lower=-0.99))
    dsf["cum"] = logr.groupby(dsf["permno"], sort=False).cumsum()
    dsf["fwd"] = np.expm1(
        dsf.groupby("permno", sort=False)["cum"].shift(-horizon) - dsf["cum"])
    dsf["block"] = dsf["date"].dt.strftime("%Y-%m")
    mkt = load_market()
    mlog = np.log1p(mkt.clip(lower=-0.99)).cumsum()
    mfwd = np.expm1(mlog.shift(-horizon) - mlog)

    used = {(int(p), pd.Timestamp(d))
            for p, d in zip(frame["permno"], frame["entry_date"])}
    beta_by = frame.groupby("permno")["beta"].median().to_dict()
    rows = []
    for (p, blk), grp in frame.groupby(["permno", "block"]):
        pool = dsf[(dsf["permno"] == p) & (dsf["block"] == blk)]
        cand = [d for d in pool["date"].tolist() if (int(p), d) not in used]
        if not cand:
            continue
        for _ in range(len(grp)):
            d = cand[int(rng.integers(len(cand)))]
            row = pool[pool["date"] == d]
            f = float(row["fwd"].iloc[0])
            if not np.isfinite(f):
                continue
            if d not in mfwd.index:
                continue
            fm = float(mfwd.loc[d])
            b = float(beta_by.get(p, 1.0))
            rows.append((int(p), blk, f, fm, b, f - b * fm))
    return pd.DataFrame(rows, columns=["permno", "block", "raw", "mkt",
                                       "beta", "ar"])


# ── embedders ──────────────────────────────────────────────────────────────

def nim_embed_factory(batch: int = 48, timeout_s: float = 60.0,
                      max_retries: int = 3):
    """`nvidia/nemotron-3-embed-1b` -- FREE, 2048-dim, batch of ~50.

    A failed batch is REFUSED loudly and the run stops. Silently falling back
    to the hashing embedder would make the receipt a claim about a model that
    never ran.
    """
    import requests
    import backend.config  # noqa: F401  side effect: gated dotenv load
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise SystemExit("REFUSED: NVIDIA_API_KEY absent; --embedder nim needs it")
    base = os.environ.get("NVIDIA_BASE_URL",
                          "https://integrate.api.nvidia.com/v1").rstrip("/")
    state = {"calls": 0, "seconds": 0.0, "retries": 0}

    def embed(texts):
        vecs = []
        for i in range(0, len(texts), batch):
            chunk = [(t or "")[:512] for t in texts[i:i + batch]]
            for attempt in range(max_retries):
                t0 = time.time()
                r = requests.post(
                    base + "/embeddings",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"input": chunk, "model": "nvidia/nemotron-3-embed-1b",
                          "input_type": "passage"},
                    timeout=timeout_s)
                state["seconds"] += time.time() - t0
                state["calls"] += 1
                if r.status_code == 200:
                    break
                state["retries"] += 1
                if attempt == max_retries - 1:
                    raise SystemExit(
                        f"REFUSED: NIM embeddings HTTP {r.status_code} on batch "
                        f"{i}: {r.text[:200]}")
                time.sleep(1.5 * (attempt + 1))
            vecs.extend([d["embedding"] for d in r.json()["data"]])
            if (i // batch) % 25 == 0:
                print(f"  embedded {min(i + batch, len(texts))}/{len(texts)}",
                      flush=True)
        return AR.l2_normalise(np.asarray(vecs, dtype="float64"))

    embed.state = state                                        # type: ignore
    return embed


# ── labelling (free model, once per cluster) ───────────────────────────────

def parse_label_reply(txt: str) -> dict:
    """Pull (label, direction) out of a free model's reply.

    THE FREE MODELS EMIT THEIR CHAIN OF THOUGHT. Measured 2026-09-08:
    `openai/gpt-oss-20b` and `nvidia/nemotron-3.5-lightning-30b-a3b` both begin
    with "Here's a thinking process: ..." and reach the requested three lines
    only near the end, so reading `lines[0]` returns the word "Here's". The
    parser therefore anchors on the DIRECTION token -- the last line that is
    exactly LONG, SHORT or UNCLEAR -- and takes the label from the line above
    it. An unparseable reply returns `None`, which is a refusal the receipt
    records, never a label that looks fine and says nothing.
    """
    lines = [l.strip() for l in (txt or "").splitlines()]
    idx = [i for i, l in enumerate(lines)
           if l.strip("*_ .:-").upper() in ("LONG", "SHORT", "UNCLEAR")]
    if not idx:
        return {"label": None, "direction": "TWO_SIDED",
                "parse": "NO_DIRECTION_TOKEN"}
    i = idx[-1]
    direction = lines[i].strip("*_ .:-").upper()
    label = None
    for j in range(i - 1, -1, -1):
        cand = lines[j].strip("*_# ")
        if cand and not cand.lower().startswith(("line 1", "line 2", "line 3")):
            label = cand[:120]
            break
    return {"label": label,
            "direction": "TWO_SIDED" if direction == "UNCLEAR" else direction,
            "parse": "OK" if label else "NO_LABEL_LINE"}


def label_clusters(clusters: dict, sample_titles: dict,
                   model: str = "nvidia/nemotron-3.5-lightning-30b-a3b") -> dict:
    """ONE call per cluster, on a FREE backend. The label is a DESCRIPTION.

    If the free backend refuses or is unreachable, the mechanical top-terms
    label stands and `label_source` says so. A missing label never stops the
    pipeline, because the label is never evidence and nothing downstream reads
    it -- the grading sees only the MEMBERS.
    """
    out = {}
    try:
        from backend.services import free_inference as FI
    except Exception as exc:                                   # noqa: BLE001
        return {c: {"label": None, "direction": "TWO_SIDED",
                    "source": f"UNAVAILABLE: {exc}"} for c in clusters}
    for c, terms in clusters.items():
        titles = sample_titles.get(c, [])[:12]
        prompt = (
            "You are naming a cluster of financial news headlines. Reply in "
            "English.\n"
            "Line 1: a short noun phrase of at most eight words naming what "
            "these headlines have in common.\n"
            "Line 2: exactly one of LONG, SHORT, UNCLEAR -- the direction you "
            "would expect the stock to drift over the next week.\n"
            "Line 3: one sentence saying why.\n"
            "Do not name any specific company.\n\n"
            "Over-represented terms: " + ", ".join(terms)
            + "\n\nHeadlines:\n"
            + "\n".join("- " + t[:160] for t in titles))
        try:
            res = FI.complete("nvidia_nim", prompt, model=model,
                              max_tokens=1500, timeout=150)
            parsed = parse_label_reply(res.text)
            out[c] = {**parsed,
                      "source": f"nvidia_nim/{res.model} (free, "
                                f"${res.cost_usd:.2f}, parse={parsed['parse']})",
                      "raw_tail": (res.text or "")[-400:]}
            print(f"  labelled cluster {c}: {parsed['label']!r} "
                  f"[{parsed['direction']}]", flush=True)
        except Exception as exc:                               # noqa: BLE001
            out[c] = {"label": None, "direction": "TWO_SIDED",
                      "source": f"REFUSED: {type(exc).__name__}: {exc}"[:200]}
    return out


# ── the run ────────────────────────────────────────────────────────────────

def run(args) -> dict:
    t_start = time.time()
    rec: dict = {
        "job": "U_archetypes", "lane": "U1/U2/U3", "licence": AR.LICENCE,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "llm_spend_usd": 0.0,
        "declared_before_any_result": {
            "k_grid": list(K_GRID), "primary_horizon_days": PRIMARY_HORIZON_DAYS,
            "secondary_horizons_exploratory": list(SECONDARY_HORIZONS),
            "family_size": FAMILY_SIZE, "rank_rule": RANK_RULE,
            "eras": {k: list(v) for k, v in ERAS.items()},
            "plant_multiple_of_mde": PLANT_MULTIPLE_OF_MDE,
            "plant_n": PLANT_N, "seed": SEED},
    }

    ev = load_events(quick=args.quick)
    rec["corpus"] = {
        "event_table_rows": int(ev.attrs["n_all_rows_in_event_table"]),
        "rows_with_title_and_permno_2015_2024": int(len(ev)),
        "distinct_permnos": int(ev["permno"].nunique()),
        "distinct_symbols": int(ev["symbol"].nunique()),
        "year_counts": {str(k): int(v) for k, v in
                        ev["observed_date"].dt.year.value_counts()
                        .sort_index().items()},
        "limit": ("only rows with BOTH a headline and a CRSP permno are "
                  "testable by this route; the corpus is the terminal repo's "
                  "156-symbol news pull, so it is mega-cap-tech-heavy and any "
                  "positive result is a REGIME finding until the E-lane "
                  "backfill widens it"),
    }
    print(f"[corpus] {len(ev)} events, {ev['permno'].nunique()} permnos",
          flush=True)

    frame = build_frame(ev, PRIMARY_HORIZON_DAYS)
    rec["frame"] = {
        "n_events_with_forward_return": int(len(frame)),
        "horizon_days": PRIMARY_HORIZON_DAYS,
        "entry_convention": ("close of the first trading day STRICTLY AFTER "
                             "observed_at_utc"),
        "abnormal_return": "raw - beta_pre * market (market model, alpha 0)",
        "market": "Ken French daily Mkt-RF + RF (pinned vintage 2026-07-29)",
        "beta": "learner/beta_panel.parquet beta_pre, last value <= entry",
        "blocks": "calendar month of entry",
        "block_range": [frame["block"].min(), frame["block"].max()],
        "n_blocks": int(frame["block"].nunique()),
        "events_dropped_by_reason": frame.attrs["drops"],
        "n_events_offered": frame.attrs["n_events_in"],
        "n_nan_daily_returns_in_dsf_treated_as_zero":
            frame.attrs["n_nan_daily_ret_in_dsf"],
        "silent_drop_note": ("every dropped event is counted by reason; a "
                             "silent drop is the house failure mode"),
    }
    print(f"[frame] {len(frame)} events with returns, "
          f"{frame['block'].nunique()} blocks", flush=True)

    # embedder
    if args.embedder == "nim":
        raw_embed = nim_embed_factory()
        emb_name = "nvidia/nemotron-3-embed-1b (NIM, free, 2048-dim)"
    else:
        raw_embed = lambda ts: AR.hash_embed(ts, dim=384, seed=SEED)  # noqa: E731
        emb_name = "hash_embed (deterministic, offline, 384-dim)"
    rec["embedder"] = emb_name

    # ONE vector per distinct string, ever. U3 embeds the corpus plus 800
    # planted rows and U1 embeds the corpus again; without this the paid-in-time
    # (free-in-money) endpoint would be called three times for the same text.
    _cache: dict[str, np.ndarray] = {}
    # OUTSIDE the repo on purpose: 17k x 2048 float32 is ~140 MB and a cache is
    # not a receipt. `AEGIS_ARCHETYPE_CACHE` overrides the location.
    cache_dir = Path(os.environ.get("AEGIS_ARCHETYPE_CACHE",
                                    Path(tempfile.gettempdir())
                                    / "aegis_archetypes"))
    cache_path = cache_dir / f"embed_cache_{args.embedder}.npz"
    if args.cache and cache_path.exists():
        z = np.load(cache_path, allow_pickle=True)
        keys = z["keys"].tolist()
        vals = z["vals"]
        _cache = {k: vals[i] for i, k in enumerate(keys)}
        print(f"[embed] cache hit: {len(_cache)} vectors from {cache_path.name}",
              flush=True)

    def embed(texts):
        want = [t for t in dict.fromkeys(texts) if t not in _cache]
        if want:
            V = raw_embed(want)
            for t, v in zip(want, V):
                _cache[t] = v
            if args.cache:
                cache_dir.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(
                    cache_path, keys=np.array(list(_cache), dtype=object),
                    vals=np.asarray(list(_cache.values()), dtype="float32"))
        return AR.l2_normalise(np.asarray([_cache[t] for t in texts],
                                          dtype="float64"))

    # ---------------------------------------------------------------- U3
    block_labels = sorted(frame["block"].unique().tolist())
    bm = frame.groupby("block")["ar"].mean()
    sd_block = float(bm.std(ddof=1))
    # Sized against the PLANTED CLUSTER'S own MDE, not the corpus's: the plant
    # has PLANT_N events spread over the same blocks, so its block sd is much
    # larger than the corpus's and the corpus MDE is the wrong denominator.
    plan = AR.plant_drift(float(frame["ar"].std(ddof=1)), PLANT_N,
                          multiple=PLANT_MULTIPLE_OF_MDE)
    drift = plan["drift"]
    # THE PLANT MUST MATCH THE EMBEDDER'S NOTION OF SIMILARITY. A language
    # model sees meaning, so it gets realistic headlines from two distinct
    # event families; the hashing embedder sees tokens, so it gets two rare
    # vocabularies. Planting tokens against a semantic embedder is what failed
    # in run 01. The mode that ran is stamped on the receipt.
    plant_mode = args.plant or ("templates" if args.embedder == "nim"
                                else "tokens")
    tpl_p = _PLANTED_TEMPLATES if plant_mode == "templates" else ()
    tpl_n = _NULL_TEMPLATES if plant_mode == "templates" else ()
    planted = AR.plant_family(
        AR.PlantedFamily("PLANTED", _PLANTED_VOCAB, PLANT_N, drift, SEED,
                         templates=tpl_p),
        block_labels=block_labels)
    null = AR.plant_family(
        AR.PlantedFamily("NULLFAM", _NULL_VOCAB, PLANT_N, 0.0, SEED + 1,
                         templates=tpl_n),
        block_labels=block_labels)
    # k IS CHOSEN ON THE REAL CORPUS FIRST, and the gate then runs at that k.
    # A family of 400 in a corpus of 22,641 cannot reach 80% purity if k is so
    # coarse that no cluster of about 400 exists, so testing the gate at an
    # arbitrary k would measure the grid rather than the pipeline. The k
    # selection never sees the plant, so nothing leaks.
    titles = frame["title"].tolist()
    X = embed(titles)
    rec["U1_k_selection"] = AR.choose_k(X, K_GRID, seed=SEED)
    k = args.k or rec["U1_k_selection"]["best_k"] or 12
    rec["U1_chosen_k"] = int(k)
    print(f"[U1] k chosen on the real corpus (plant unseen): {k}", flush=True)
    k_u3 = k
    print(f"[U3] planting drift {drift*100:.3f}pp "
          f"({PLANT_MULTIPLE_OF_MDE}x MDE on sd_block {sd_block*100:.3f}pp, "
          f"{len(block_labels)} blocks)", flush=True)
    u3 = AR.known_answer(
        embed=embed, planted=planted, null=null,
        background_titles=frame["title"].tolist(),
        background_blocks=frame["block"].tolist(),
        background_ar=frame["ar"].tolist(),
        k=k_u3, seed=SEED, horizon_days=PRIMARY_HORIZON_DAYS,
        declared_family_size=FAMILY_SIZE)
    u3["sd_block_corpus"] = sd_block
    u3["plant_sizing"] = plan
    rec["U3_known_answer"] = u3
    print(f"[U3] passed={u3['passed']} checks={u3['checks']}", flush=True)
    if not u3["passed"] and not args.continue_on_u3_fail:
        rec["stopped"] = ("U3 did not pass. Nothing downstream is believable, "
                          "so the real archetypes were not graded. Re-run with "
                          "--continue-on-u3-fail only to diagnose.")
        return rec

    # ---------------------------------------------------------------- U1
    if args.embedder == "nim":
        rec["embedder_calls"] = dict(raw_embed.state)          # type: ignore
    rec["embedder_distinct_texts_cached"] = len(_cache)
    lab, _ = AR.kmeans(X, k, seed=SEED)
    frame["cluster"] = lab
    rec["U1_stability"] = AR.stability(X, k)
    sizes = frame["cluster"].value_counts().sort_index()
    rec["U1_cluster_sizes"] = {str(c): int(n) for c, n in sizes.items()}
    rec["U1_silhouette_at_chosen_k"] = AR.silhouette(X, lab, seed=SEED)
    print(f"[U1] k={k} silhouette={rec['U1_silhouette_at_chosen_k']} "
          f"ARI={rec['U1_stability']['ari_mean']}", flush=True)

    terms = {int(c): AR.top_terms(np.where(lab == c)[0].tolist(), titles)
             for c in np.unique(lab)}
    samples = {int(c): frame[frame["cluster"] == c]["title"].head(12).tolist()
               for c in np.unique(lab)}
    labels = ({int(c): {"label": None, "direction": "TWO_SIDED",
                        "source": "SKIPPED (--no-label)"} for c in np.unique(lab)}
              if args.no_label else label_clusters(terms, samples))
    rec["U1_labels"] = {str(c): {"top_terms": terms[int(c)], **labels[int(c)]}
                        for c in np.unique(lab)}

    # ---------------------------------------------------------------- U2
    corpses, corpse_meta = load_corpses()
    rec["U2_corpse_register"] = corpse_meta
    order = sizes.sort_values(ascending=False).index.tolist()
    hyps, routes = [], {}
    for c in order:
        c = int(c)
        sub = frame[frame["cluster"] == c]
        lb = labels[c]
        h = AR.emit_hypothesis(
            archetype_id=f"A{c:02d}", texts=sub["title"].tolist(),
            member_ids=sub["event_id"].tolist(),
            horizon_days=PRIMARY_HORIZON_DAYS,
            label=lb.get("label") or ("/".join(terms[c][:4])),
            label_source=lb.get("source", "mechanical top-terms"),
            terms=terms[c],
            direction=lb.get("direction", "TWO_SIDED"),
            direction_source=("free model, from member titles only -- it never "
                              "saw a return"))
        r = AR.route_through_corpses(h, corpses)
        routes[h.hypothesis_id] = r
        if r["admitted"]:
            hyps.append(h)
    rec["U2_hypotheses_emitted"] = [h.to_dict() for h in hyps]
    rec["U2_corpse_routes"] = routes
    rec["U2_n_refused_by_corpse_check"] = sum(
        1 for r in routes.values() if not r["admitted"])

    # ---------------------------------------------------------------- grade
    graded, ps, ps_raw = {}, {}, {}
    ten = hyps[:FAMILY_SIZE]
    ctrl = matched_control(frame, sorted({int(y) for y in
                                          frame["entry_date"].dt.year.unique()}
                                         | {int(y) + 1 for y in
                                            frame["entry_date"].dt.year.unique()}),
                           PRIMARY_HORIZON_DAYS)
    for h in ten:
        c = int(h.archetype_id[1:])
        sub = frame[frame["cluster"] == c]
        g = AR.block_grade(blocks=sub["block"].tolist(), ar=sub["ar"].tolist(),
                           raw=sub["raw"].tolist(), mkt=sub["mkt"].tolist(),
                           beta=sub["beta"].tolist(),
                           weight=sub["mcap"].tolist(),
                           horizon_days=PRIMARY_HORIZON_DAYS)
        g["tail"] = AR.tail_diagnostics(sub["ar"].tolist(), sub["block"].tolist())
        g["eras"] = AR.era_table(eras=ERAS, blocks=sub["block"].tolist(),
                                 ar=sub["ar"].tolist())
        cs = ctrl[ctrl["permno"].isin(set(sub["permno"].unique().tolist()))]
        if len(cs):
            g["matched_control"] = AR.block_grade(
                blocks=cs["block"].tolist(), ar=cs["ar"].tolist(),
                raw=cs["raw"].tolist(), mkt=cs["mkt"].tolist(),
                beta=cs["beta"].tolist(), horizon_days=PRIMARY_HORIZON_DAYS)
            g["event_minus_control"] = AR.paired_block_difference(
                blocks_a=sub["block"].tolist(), a=sub["ar"].tolist(),
                blocks_b=cs["block"].tolist(), b=cs["ar"].tolist())
            # ROBUSTNESS: the same paired difference on RAW returns. Both arms
            # are the same names in the same months, so the market leg largely
            # cancels; if the AR result survives without the beta adjustment it
            # is not an artefact of a beta mismatch between the arms.
            g["event_minus_control_raw"] = AR.paired_block_difference(
                blocks_a=sub["block"].tolist(), a=sub["raw"].tolist(),
                blocks_b=cs["block"].tolist(), b=cs["raw"].tolist())
            g["control_beta_mean"] = float(np.nanmean(cs["beta"].to_numpy()))
        else:
            g["matched_control"] = {"verdict": "NO_CONTROL_ROWS"}
            g["event_minus_control"] = {"verdict": "NO_CONTROL_ROWS"}
        # The direction was declared by the free model from titles alone,
        # before any return existed. The TEST is two-sided regardless -- the
        # declaration buys no multiplicity relief -- but whether the realised
        # sign agreed with it is a fact about the labeller worth keeping.
        g["direction_declared"] = h.direction
        g["direction_source"] = h.direction_source
        g["realised_sign"] = ("POSITIVE" if (g.get("ar_mean_pp") or 0) > 0
                              else "NEGATIVE")
        g["direction_agreed"] = (
            None if h.direction == "TWO_SIDED"
            else bool((h.direction == "LONG") == (g["realised_sign"] == "POSITIVE")))
        g["family"] = h.family
        g["label"] = h.label
        g["top_terms"] = list(h.top_terms)
        graded[h.hypothesis_id] = g
        # PRIMARY STATISTIC, declared here rather than chosen later: the paired
        # EVENT-minus-MATCHED-CONTROL difference. The raw abnormal return of an
        # equal-weighted basket of 91 mega-caps is a statement about the names
        # and the era; the paired difference is a statement about the event.
        ps[h.hypothesis_id] = (g["event_minus_control"].get("p_two_sided")
                               if isinstance(g.get("event_minus_control"), dict)
                               else None)
        ps_raw[h.hypothesis_id] = g.get("p_two_sided")
    # THE ONE FACT BEHIND THE TEN. Every archetype is a subset of the same
    # corpus measured against the same control pool, so ten negative
    # differences are not ten findings -- they are one corpus-level fact seen
    # ten times, and the family correction over ten treats them as far more
    # independent than they are. The corpus-level number is therefore reported
    # BESIDE the ten, and the doc must read them together.
    rec["corpus_level_event_minus_control"] = {
        "ar": AR.paired_block_difference(
            blocks_a=frame["block"].tolist(), a=frame["ar"].tolist(),
            blocks_b=ctrl["block"].tolist(), b=ctrl["ar"].tolist()),
        "raw": AR.paired_block_difference(
            blocks_a=frame["block"].tolist(), a=frame["raw"].tolist(),
            blocks_b=ctrl["block"].tolist(), b=ctrl["raw"].tolist()),
        "event_beta_mean": float(np.nanmean(frame["beta"].to_numpy())),
        "control_beta_mean": float(np.nanmean(ctrl["beta"].to_numpy())),
        "event_mkt_mean_pp": float(frame["mkt"].mean()) * 100.0,
        "control_mkt_mean_pp": float(ctrl["mkt"].mean()) * 100.0,
        "reading": ("if this is non-zero, every archetype inherits it and the "
                    "ten per-archetype differences are increments on top of "
                    "it, not independent effects"),
    }
    # The cluster assignment, so a reader can audit any archetype's members
    # rather than the 25 the receipt has room to print.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame[["event_id", "permno", "symbol", "entry_date", "block", "cluster",
           "title"]].to_csv(OUT_DIR / "U_archetypes_assignment.csv",
                            index=False)
    rec["cluster_assignment_csv"] = "U_archetypes_assignment.csv"
    rec["grades"] = graded
    rec["primary_statistic"] = (
        "paired block difference, EVENT minus matched control (same name, same "
        "month, no event) -- declared before the results were read")
    rec["family_correction"] = AR.family_correction(ps, family_size=FAMILY_SIZE)
    rec["family_correction_secondary_raw_ar"] = AR.family_correction(
        ps_raw, family_size=FAMILY_SIZE)
    rec["n_hypotheses_graded"] = len(ten)
    rec["elapsed_s"] = round(time.time() - t_start, 1)
    RP.attach(rec, sys.argv,
              RP.resolve_config(args, {"embedder": "hash", "k": None,
                                       "quick": False, "no_label": False,
                                       "cache": False, "plant": None,
                                       "continue_on_u3_fail": False,
                                       "out": None}, argv=sys.argv),
              TRACKER)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embedder", choices=("nim", "hash"), default="hash")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-label", action="store_true")
    ap.add_argument("--plant", choices=("templates", "tokens"), default=None,
                    help="plant mode; defaults to templates for nim, tokens "
                         "for hash -- the plant must match how the embedder "
                         "measures similarity")
    ap.add_argument("--cache", action="store_true",
                    help="persist the embedding cache to disk so a re-run is free")
    ap.add_argument("--continue-on-u3-fail", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rec = run(args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (
        OUT_DIR / f"U_archetypes_{args.embedder}"
                  f"{'_quick' if args.quick else ''}.json")
    out.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(f"[receipt] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
