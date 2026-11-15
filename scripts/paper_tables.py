"""The two candidate tables for the one paper question (council 2, items 7/8).

    python -m scripts.paper_tables --out <report dir> [--table 1|2|both] [--asof <UTC time>]

Offline, $0 LLM, no network, read-only on every input (the live forecast ledger
is STREAMED line by line, never copied). Deterministic: every random draw comes
from `np.random.default_rng(PAPER_TABLES_SEED)`.

TABLE 1 -- does an evidence PROCESS forecast better than a thematic PERSONA?
==========================================================================
Prior art: `NEGATIVE_RESULTS.md` §64 (2026-09-24) -- `investigator:*` +4.38% raw
(+8.97% at a 0.65 shrink) Brier skill held out vs nine thematic personas
-27.98%, weight 0. That split was "later half of each arm by made_at" and the
climatology was each group's own base rate. This table re-asks it with:

1. **The classification is fixed before grading.** `classify_forecasters` sees
   ONLY the declared fields (specialist, model) and REFUSES a frame carrying
   any outcome column; the rule reads the registered system prompts in
   `llm_swarm.SPECIALISTS` / `optimus_specialists.SPECIALISTS`. Ambiguous arms
   are excluded and counted, never assigned.
2. **Pre-window only.** A row frozen after the close of its entry bar (16:00
   New York on the first session >= `belief_state.resolution_start_date`) could
   see part of its own window; it is dropped and counted.
3. **One reference per event stratum** (observable, horizon, threshold): the
   base rate of every scored row of both kinds in the frame -- the same events.
4. **Uncertainty clustered two ways**: date blocks (`forecast_reputation.
   date_blocks` semantics: a new block when >= h business days have passed;
   n_effective = blocks) and ticker. Both printed; MDE = 2.8 x SE.
5. **Time split.** P1 = made on/before PAPER_TABLES_CUT_DAY (the §64 era), P2 =
   made after (a genuinely new holdout). P1 rows RESOLVED after the cut are
   new outcomes on old forecasts and are shown separately.

TABLE 2 -- how often do the evidence labels fire on books with no edge?
======================================================================
No-edge books = random equal-weight portfolios drawn from the survivorship-
corrected deep panel (living + delisted) over real windows, at the window
lengths the live books carry. Each gets a random same-band twin drawn the way
`llm_portfolio.twins` draws one (one-for-one, same liquidity band, from
`llm_portfolio._live_pool`, bands from `llm_portfolio.liquidity_bands`), is
NAV'd from the next session's open net of HALF the `xs_ranker.COST_BPS_BY_BAND`
round trip (the `llm_portfolio.grade` convention: charged once, at entry), and is
labelled by the REAL `book_dna.evidence_label` with `book_dna.subwindows` and
`book_dna.params()`. The share reaching each label is how often the label fires
on a book nobody selected.

The headline interval resamples START QUARTERS, not books: every book in one
window is one draw of the market, so a Wilson interval over books is far too
narrow. The rate in a single window is printed as a spread (min, 10th to 90th
percentile, max), and random books are NOT a zero-mean null against SPY, so the
share with positive excess, the median excess and the rate for an exactly
symmetric zero-edge book are printed beside it.

REFUSALS (non-zero exit): `--out` inside the data root (2); the deep panel
cannot be loaded split-stitched, SPY is missing, or no calendar exists (3).
Receipts carry the code commit, the `--asof` cap and a hash of the ledger bytes.

Nothing here is a skill claim. Results are OBSERVED or CANNOT_DISTINGUISH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_MAX_THREADS"):
    os.environ.setdefault(_v, "4")

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

CUT_DAY: str = str(getattr(_config, "PAPER_TABLES_CUT_DAY", "2026-09-24"))
SHRINK: float = float(getattr(_config, "PAPER_TABLES_SHRINK_FROM_S64", 0.65))
N_BOOT: int = int(getattr(_config, "PAPER_TABLES_N_BOOT", 1000))
SEED: int = int(getattr(_config, "PAPER_TABLES_SEED", 20261115))
WINDOWS: tuple = tuple(getattr(_config, "PAPER_TABLES_WINDOWS", (21, 35, 45, 55, 78, 111)))
KS: tuple = tuple(getattr(_config, "PAPER_TABLES_KS", (5, 10, 20, 30, 75)))
BOOKS_PER_CELL: int = int(getattr(_config, "PAPER_TABLES_BOOKS_PER_CELL", 300))
MDE_Z: float = float(getattr(_config, "BOOK_DNA_MDE_Z", 2.8))
#: Below this many clusters a cluster-bootstrap interval is printed but NOT read:
#: three resampled blocks give an interval that is an artefact of three numbers.
MIN_CLUSTERS_FOR_VERDICT: int = int(getattr(_config, "PAPER_TABLES_MIN_CLUSTERS_FOR_VERDICT", 10))
TIME_BLOCK_FREQ: str = str(getattr(_config, "PAPER_TABLES_TIME_BLOCK_FREQ", "Q"))
ZERO_EDGE_DRAWS: int = int(getattr(_config, "PAPER_TABLES_ZERO_EDGE_DRAWS", 20000))
ZERO_EDGE_DAILY_SD: float = float(getattr(_config, "PAPER_TABLES_ZERO_EDGE_DAILY_SD", 0.01))
RC_REFUSED_OUT, RC_REFUSED_INPUT = 2, 3


class Refusal(RuntimeError):
    """An input this script will not work around. `main` turns it into a non-zero exit."""

PROCESS, PERSONA = "PROCESS", "PERSONA"
EX_NOT_LLM, EX_THIRD_PARTY, EX_AMBIGUOUS = ("EXCLUDED_NOT_LLM", "EXCLUDED_THIRD_PARTY",
                                            "EXCLUDED_AMBIGUOUS")
NOT_LLM_MODELS = frozenset({"deterministic", "engine", "twin",
                            "AEGIS_declared_hypothesis_no_model_call"})
#: Columns a classifier may never see. A rule that could read these could be
#: informed by results, which is the failure this table exists to rule out.
OUTCOME_COLUMNS = frozenset({"outcome", "y", "brier", "resolved_at", "resolution_detail",
                             "realised_return", "calibration_bucket", "vs_benchmark"})
DECLARED_FIELDS = ("prediction_id", "specialist", "model", "ticker", "observable",
                   "horizon_days", "probability", "raw_probability", "shrink_basis",
                   "threshold", "benchmark", "made_at", "resolves_after", "mechanism_id",
                   "void_reason")
LIVE_LEDGER = Path(_config.OPTIMUS_LEDGER_DIR) / "predictions.jsonl"
ROLE_OPENERS = ("You are a ", "You are an ", "You are the ")


# ═════════════════════════════ TABLE 1 ═══════════════════════════════════════
def persona_registry() -> dict[str, str]:
    """{specialist: registered system prompt} for every declared persona bench."""
    from backend.services import llm_swarm, optimus_specialists
    reg: dict[str, str] = {}
    for name, prompt in optimus_specialists.SPECIALISTS.items():
        reg[str(name)] = str(prompt)
    for name, spec in llm_swarm.SPECIALISTS.items():
        reg[str(name)] = str(spec.system)
    return reg


def classify_one(specialist: str, model: str | None, registry: dict[str, str]) -> tuple[str, str]:
    """(kind, reason) from DECLARED fields only. Order: process, not-LLM,
    third-party, persona, ambiguous; the first match wins."""
    s, m = str(specialist or ""), str(model or "")
    if s.startswith("investigator:"):
        return PROCESS, "investigator:* (microtask chain / evidence packet, no persona)"
    if m in NOT_LLM_MODELS or m.startswith("rule:"):
        return EX_NOT_LLM, f"model {m!r} is not an LLM call"
    if s.startswith("source:"):
        return EX_THIRD_PARTY, "claim transcribed from a third-party source"
    prompt = registry.get(s)
    if prompt is not None and prompt.lstrip().startswith(ROLE_OPENERS):
        return PERSONA, "registered system prompt opens with a role identity"
    return EX_AMBIGUOUS, "LLM arm that is neither a registered persona nor an investigator process"


def process_subtype(specialist: str) -> str | None:
    s = str(specialist)
    if not s.startswith("investigator:"):
        return None
    arm = s.split(":", 1)[1]
    if arm.startswith("evidence_"):
        return "packet"
    return "no_tools" if arm == "A_snapshot" else "tools"


def classify_forecasters(declared: pd.DataFrame,
                         registry: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per (specialist, model): kind, reason, subtype. REFUSES outcomes."""
    leak = sorted(OUTCOME_COLUMNS & set(declared.columns))
    if leak:
        raise ValueError(f"REFUSED: the classifier was handed outcome columns {leak}; "
                         "classification must be fixed before grading")
    reg = persona_registry() if registry is None else registry
    pairs = declared[["specialist", "model"]].astype(str).drop_duplicates()
    rows = []
    for s, m in pairs.itertuples(index=False):
        kind, why = classify_one(s, m, reg)
        rows.append({"specialist": s, "model": m, "kind": kind, "reason": why,
                     "subtype": process_subtype(s)})
    return pd.DataFrame(rows, columns=["specialist", "model", "kind", "reason", "subtype"])


def class_map_hash(cm: pd.DataFrame) -> str:
    blob = json.dumps(sorted(cm[["specialist", "model", "kind"]].itertuples(index=False)),
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def stream_ledger(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(declared, outcomes, stats) -- two frames joined only by prediction_id."""
    dec, out = [], []
    stats = Counter()
    seen: dict[str, int] = {}
    digest, n_bytes = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for line in fh:
            digest.update(line)
            n_bytes += len(line)
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                stats["unparseable"] += 1
                continue
            pid = str(r.get("prediction_id"))
            if pid in seen:
                stats["duplicate_id_later_line_kept"] += 1
            seen[pid] = len(dec)
            d = {k: r.get(k) for k in DECLARED_FIELDS}
            d["entry_after_utc"] = (r.get("inputs_used") or {}).get("entry_after_utc") \
                if isinstance(r.get("inputs_used"), dict) else None
            dec.append(d)
            out.append({"prediction_id": pid, "outcome": r.get("outcome"),
                        "resolved_at": r.get("resolved_at")})
            stats["lines"] += 1
    D = pd.DataFrame(dec).drop_duplicates("prediction_id", keep="last")
    O = pd.DataFrame(out).drop_duplicates("prediction_id", keep="last")
    stats["unique_ids"] = int(len(D))
    return D, O, {**dict(stats), "bytes_read": n_bytes, "sha256_of_bytes_read": digest.hexdigest()}


def apply_asof(D: pd.DataFrame, O: pd.DataFrame, asof: Any) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The `--asof` cap: a forecast MADE after it is ignored, and an outcome
    RESOLVED after it is treated as not graded yet. Both counted."""
    cap = pd.Timestamp(asof)
    cap = cap.tz_localize("UTC") if cap.tzinfo is None else cap.tz_convert("UTC")
    made = pd.to_datetime(D["made_at"], utc=True, errors="coerce", format="ISO8601")
    late = (made > cap).to_numpy()
    D2 = D[~late].copy()
    O2 = O[O["prediction_id"].isin(set(D2["prediction_id"].astype(str)))].copy()
    res = pd.to_datetime(O2["resolved_at"], utc=True, errors="coerce", format="ISO8601")
    late_o = (res > cap).to_numpy()
    O2["outcome"] = O2["outcome"].astype(object)
    O2["resolved_at"] = O2["resolved_at"].astype(object)
    O2.loc[late_o, ["outcome", "resolved_at"]] = None
    return D2, O2, {"asof_utc": cap.isoformat(timespec="seconds"),
                    "rows_made_after_asof_ignored": int(late.sum()),
                    "outcomes_resolved_after_asof_treated_as_ungraded": int(late_o.sum())}


def entry_close_utc(start_days: pd.Series, sessions: np.ndarray) -> pd.Series:
    """16:00 America/New_York on the first session >= each start day, in UTC.
    NaT when no session on/after the start day exists in the calendar."""
    sd = pd.to_datetime(start_days, errors="coerce").values.astype("datetime64[D]")
    ses = np.asarray(sessions).astype("datetime64[D]")
    idx = np.searchsorted(ses, sd, side="left")
    ok = (idx < len(ses)) & ~np.isnat(sd)
    ent = np.full(len(sd), np.datetime64("NaT"), dtype="datetime64[D]")
    ent[ok] = ses[idx[ok]]
    naive = pd.to_datetime(ent) + pd.Timedelta(hours=16)
    loc = pd.DatetimeIndex(naive).tz_localize("America/New_York", ambiguous="NaT",
                                              nonexistent="NaT")
    return pd.Series(loc.tz_convert("UTC"), index=start_days.index)


def start_day_of(row_made: str, mechanism: Any, entry_after: Any) -> str | None:
    """`belief_state.resolution_start_date` without raising."""
    from backend.services import belief_state as B
    rec = {"made_at": row_made, "mechanism_id": mechanism,
           "inputs_used": {"entry_after_utc": entry_after}}
    try:
        return B.resolution_start_date(rec)
    except (ValueError, TypeError, KeyError):
        return None


def prewindow_mask(made_at: pd.Series, start_days: pd.Series,
                   sessions: np.ndarray) -> tuple[pd.Series, pd.Series]:
    """(pre_window, entry_close_utc): True iff frozen strictly before the entry close."""
    m = pd.to_datetime(made_at, utc=True, errors="coerce", format="ISO8601")
    close = entry_close_utc(start_days, sessions)
    pre = (m.notna() & close.notna() & (m < close))
    return pre, close


def premature_hold_mask(ids: pd.Series) -> pd.Series:
    from backend.services import forecast_reputation as FR
    H = FR._PREMATURE_ID_HASHES
    return ids.astype(str).map(lambda s: hashlib.blake2b(s.encode(), digest_size=16).digest() in H)


def outcome01(v: Any) -> float | None:
    from backend.services import forecast_reputation as FR
    return FR._outcome01(v)


def date_block_ids(days: Iterable[str], h: int) -> dict[str, int]:
    """{day: block id} with `forecast_reputation.date_blocks` semantics."""
    ds = sorted({str(d) for d in days if d})
    out: dict[str, int] = {}
    if not ds:
        return out
    b, start = 0, ds[0]
    for d in ds:
        if h > 1:
            if int(np.busday_count(start, d)) >= h:
                b += 1
                start = d
        elif d != start:
            b += 1
            start = d
        out[d] = b
    return out


def assign_date_blocks(df: pd.DataFrame, h_col: str = "h", day_col: str = "made_day",
                       h_override: int | None = None) -> pd.Series:
    """Cluster key per row: (h, block). `h_override` uses one block length for
    every row (pooled tables)."""
    keys = pd.Series(index=df.index, dtype=object)
    groups = [(h_override, df)] if h_override is not None else list(df.groupby(h_col))
    for h, sub in groups:
        ids = date_block_ids(sub[day_col], int(h))
        keys.loc[sub.index] = [f"{int(h)}|{ids[d]}" for d in sub[day_col]]
    return keys


def _ls(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    q = np.clip(p, 0.01, 0.99)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def add_reference(df: pd.DataFrame) -> pd.DataFrame:
    """Stratum base rate over every row in the frame (both kinds: same events)."""
    d = df.copy()
    d["stratum"] = (d["observable"].astype(str) + "|h" + d["h"].astype(str) + "|"
                    + d["threshold"].astype(str))
    d["base"] = d.groupby("stratum")["y"].transform("mean")
    d["bs"] = (d["p"] - d["y"]) ** 2
    d["bs_ref"] = (d["base"] - d["y"]) ** 2
    d["ls"] = _ls(d["p"].to_numpy(float), d["y"].to_numpy(float))
    d["ls_ref"] = _ls(d["base"].to_numpy(float), d["y"].to_numpy(float))
    return d


def skill_of(d: pd.DataFrame) -> dict:
    bs, br = float(d["bs"].sum()), float(d["bs_ref"].sum())
    ls, lr = float(d["ls"].sum()), float(d["ls_ref"].sum())
    return {"n": int(len(d)), "brier": bs / max(len(d), 1), "brier_ref": br / max(len(d), 1),
            "bss": (1 - bs / br) if br > 0 else None,
            "log_skill": (1 - ls / lr) if lr > 0 else None,
            "base_rate": float(d["y"].mean()) if len(d) else None,
            "calib_gap": float(d["p"].mean() - d["y"].mean()) if len(d) else None}


def cluster_bootstrap(d: pd.DataFrame, cluster: str, n_boot: int,
                      rng: np.random.Generator, by: str | None = None,
                      order: tuple | None = None) -> dict:
    """SE / 95% interval of BSS (and of the BSS difference between the two
    values of `by`, `order[0] - order[1]`, default sorted order) by resampling
    whole clusters. The stratum reference is held fixed."""
    if d.empty:
        return {"n_clusters": 0}
    groups = (list(order) if order else sorted(d[by].unique())) if by else [None]
    agg = []
    for g in groups:
        sub = d if g is None else d[d[by] == g]
        a = sub.groupby(cluster)[["bs", "bs_ref"]].sum()
        agg.append(a)
    allc = sorted(set().union(*[set(a.index) for a in agg]))
    cidx = {c: i for i, c in enumerate(allc)}
    mats = []
    for a in agg:
        m = np.zeros((len(allc), 2))
        for c, row in a.iterrows():
            m[cidx[c]] = row.to_numpy(float)
        mats.append(m)
    nc = len(allc)
    draws = rng.integers(0, nc, size=(n_boot, nc))
    counts = np.zeros((n_boot, nc))
    for i in range(n_boot):
        counts[i] = np.bincount(draws[i], minlength=nc)
    sk = []
    for m in mats:
        num, den = counts @ m[:, 0], counts @ m[:, 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            sk.append(np.where(den > 0, 1 - num / den, np.nan))
    out = {"n_clusters": nc, "n_boot": n_boot}
    for g, s in zip(groups, sk):
        key = "all" if g is None else str(g)
        out[key] = {"se": float(np.nanstd(s)), "lo": float(np.nanpercentile(s, 2.5)),
                    "hi": float(np.nanpercentile(s, 97.5))}
    if by and len(groups) == 2:
        diff = sk[0] - sk[1]
        out["diff"] = {"of": f"{groups[0]} - {groups[1]}", "se": float(np.nanstd(diff)),
                       "lo": float(np.nanpercentile(diff, 2.5)),
                       "hi": float(np.nanpercentile(diff, 97.5))}
    return out


def verdict_of(est: float | None, lo: float | None, hi: float | None, se: float | None) -> str:
    if est is None or lo is None or hi is None:
        return "CANNOT_DETERMINE"
    mde = None if se is None else MDE_Z * se
    if lo > 0 or hi < 0:
        return f"OBSERVED ({'positive' if lo > 0 else 'negative'}; MDE {mde:.3f})"
    return f"CANNOT_DISTINGUISH from 0 (MDE {mde:.3f})"


def build_graded(D: pd.DataFrame, O: pd.DataFrame, cm: pd.DataFrame,
                 sessions: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Join the FROZEN class map to the declared rows, then (only then) attach
    outcomes, then apply the drop rules in a fixed order, counting each."""
    flow: dict[str, Any] = {"ledger_rows": int(len(D))}
    x = D.assign(specialist=D["specialist"].astype(str), model=D["model"].astype(str))
    x = x.merge(cm[["specialist", "model", "kind", "subtype"]], on=["specialist", "model"],
                how="left")
    flow["by_kind_all_rows"] = {str(k): int(v) for k, v in x["kind"].value_counts().items()}
    x = x[x["kind"].isin([PROCESS, PERSONA])].copy()
    flow["persona_or_process_rows"] = int(len(x))
    x = x.merge(O, on="prediction_id", how="left")
    x["y"] = x["outcome"].map(outcome01)
    x["p"] = pd.to_numeric(x["probability"], errors="coerce")
    drops: dict[str, dict] = {}

    def drop(mask: pd.Series, why: str) -> None:
        nonlocal x
        drops[why] = {str(k): int(v) for k, v in x.loc[mask, "kind"].value_counts().items()}
        x = x[~mask].copy()

    drop(x["void_reason"].notna() & (x["void_reason"].astype(str) != ""), "voided")
    drop(x["y"].isna(), "not_graded_yet_or_outcome_unreadable")
    drop(~x["p"].between(0.0, 1.0), "probability_outside_0_1")
    drop(premature_hold_mask(x["prediction_id"]), "premature_resolution_hold_2026_10_14")
    x["start_day"] = [start_day_of(m, me, ea) for m, me, ea in
                      zip(x["made_at"], x["mechanism_id"], x["entry_after_utc"])]
    pre, close = prewindow_mask(x["made_at"], pd.Series(x["start_day"], index=x.index), sessions)
    x["entry_close_utc"] = close
    drop(~pre, "frozen_at_or_after_entry_close")
    x["made_ts"] = pd.to_datetime(x["made_at"], utc=True, errors="coerce", format="ISO8601")
    x["made_day"] = x["made_ts"].dt.strftime("%Y-%m-%d")
    x["made_month"] = x["made_ts"].dt.strftime("%Y-%m")
    x["h"] = pd.to_numeric(x["horizon_days"], errors="coerce").astype("Int64")
    drop(x["h"].isna(), "horizon_unreadable")
    x["h"] = x["h"].astype(int)
    x["threshold"] = x["threshold"].astype(str)
    x["ticker"] = x["ticker"].astype(str)
    rday = pd.to_datetime(x["resolved_at"], utc=True, errors="coerce", format="ISO8601")
    x["resolved_day"] = rday.dt.strftime("%Y-%m-%d")
    cut_end = pd.Timestamp(CUT_DAY, tz="UTC") + pd.Timedelta(days=1)
    x["period"] = np.where(x["made_ts"] < cut_end, "P1", "P2")
    x["resolved_after_cut"] = (rday >= cut_end).fillna(False).to_numpy()
    flow["drops"] = drops
    flow["graded_prewindow"] = {str(k): int(v) for k, v in x["kind"].value_counts().items()}
    return x, flow


def table_rows(d: pd.DataFrame, group_cols: list[str], n_boot: int, rng: np.random.Generator,
               min_n: int = 30) -> list[dict]:
    """One row per group: skill, log skill, date-block and ticker intervals."""
    out = []
    for key, sub in d.groupby(group_cols, sort=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(group_cols, [str(k) for k in key]))
        r.update(skill_of(sub))
        if sub["h"].nunique() > 1:
            # mixed horizons: one block length for the group, the LONGEST (conservative)
            sub = sub.assign(block=assign_date_blocks(sub, h_override=int(sub["h"].max())))
            r["block_h"] = int(sub["h"].max())
        r["n_days"] = int(sub["made_day"].nunique())
        r["n_date_blocks"] = int(sub["block"].nunique())
        r["n_tickers"] = int(sub["ticker"].nunique())
        if len(sub) >= min_n and r["n_date_blocks"] >= 2:
            bd = cluster_bootstrap(sub, "block", n_boot, rng)["all"]
            bt = cluster_bootstrap(sub, "ticker", n_boot, rng)["all"]
            r["ci_date_blocks"] = [bd["lo"], bd["hi"]]
            r["se_date_blocks"] = bd["se"]
            r["ci_ticker"] = [bt["lo"], bt["hi"]]
            r["se_ticker"] = bt["se"]
            r["mde_date_blocks"] = MDE_Z * bd["se"]
            r["verdict"] = (verdict_of(r["bss"], bd["lo"], bd["hi"], bd["se"])
                            if r["n_date_blocks"] >= MIN_CLUSTERS_FOR_VERDICT else
                            f"CANNOT_DETERMINE ({r['n_date_blocks']} date blocks < "
                            f"{MIN_CLUSTERS_FOR_VERDICT}; interval printed, not read)")
        else:
            r["verdict"] = f"CANNOT_DETERMINE (n {len(sub)}, date blocks {r['n_date_blocks']})"
        out.append(r)
    return out


def contrast(d: pd.DataFrame, n_boot: int, rng: np.random.Generator) -> dict:
    """PROCESS - PERSONA skill difference, clustered by date block and by ticker."""
    if d["kind"].nunique() < 2:
        return {"status": "CANNOT_DETERMINE", "why": "only one kind in this frame",
                "kinds": sorted(d["kind"].unique().tolist())}
    s = {k: skill_of(sub) for k, sub in d.groupby("kind")}
    est = (s[PROCESS]["bss"] or 0) - (s[PERSONA]["bss"] or 0)
    # the same, against each kind's OWN base rate per stratum (§64's convention): a
    # kind that forecast in a different week faced a different base rate, and the
    # pooled reference charges it for the week, not for the forecasts
    own = {}
    for k, sub in d.groupby("kind"):
        b = sub.groupby("stratum")["y"].transform("mean")
        ref = float(((b - sub["y"]) ** 2).sum())
        own[k] = (1 - float(sub["bs"].sum()) / ref) if ref > 0 else None
    blocks = {k: int(sub["block"].nunique()) for k, sub in d.groupby("kind")}
    days = {k: int(sub["made_day"].nunique()) for k, sub in d.groupby("kind")}
    bd = cluster_bootstrap(d, "block", n_boot, rng, by="kind", order=(PROCESS, PERSONA))
    bt = cluster_bootstrap(d, "ticker", n_boot, rng, by="kind", order=(PROCESS, PERSONA))
    vb = (verdict_of(est, bd["diff"]["lo"], bd["diff"]["hi"], bd["diff"]["se"])
          if min(blocks.values()) >= MIN_CLUSTERS_FOR_VERDICT else
          f"CANNOT_DETERMINE: date blocks per kind {blocks} (< {MIN_CLUSTERS_FOR_VERDICT} for "
          "a kind) -- a kind with one block has no date-level replication at all")
    return {"process_minus_persona_bss": est, "skill": s, "skill_own_base": own,
            "date_blocks_per_kind": blocks, "decision_days_per_kind": days,
            "date_blocks": {"n": bd["n_clusters"], **bd["diff"]},
            "ticker": {"n": bt["n_clusters"], **bt["diff"]},
            "verdict_date_blocks": vb,
            "verdict_ticker": verdict_of(est, bt["diff"]["lo"], bt["diff"]["hi"],
                                         bt["diff"]["se"]) + " [assumes tickers independent "
                                                             "within a decision day]"}


def matched_pairs(d: pd.DataFrame, tol_bdays: int) -> dict:
    """Same ticker, observable, horizon and threshold, made within `tol_bdays`
    business days of each other. Paired Brier difference on the SAME events."""
    key = ["ticker", "observable", "h", "threshold"]
    a = d[d["kind"] == PROCESS][key + ["made_day", "bs", "bs_ref", "y", "resolved_day"]]
    b = d[d["kind"] == PERSONA][key + ["made_day", "bs", "bs_ref"]]
    m = a.merge(b, on=key, suffixes=("_proc", "_pers"))
    if m.empty:
        return {"tol_bdays": tol_bdays, "n_pairs": 0, "n_keys": 0}
    gap = np.abs(np.busday_count(m["made_day_proc"].to_numpy("datetime64[D]"),
                                 m["made_day_pers"].to_numpy("datetime64[D]")))
    m = m[gap <= tol_bdays]
    if m.empty:
        return {"tol_bdays": tol_bdays, "n_pairs": 0, "n_keys": 0,
                "nearest_gap_bdays": int(gap.min())}
    diff = (m["bs_pers"] - m["bs_proc"]).to_numpy(float)
    return {"tol_bdays": tol_bdays, "n_pairs": int(len(m)),
            "n_keys": int(m[key].drop_duplicates().shape[0]),
            "mean_brier_persona_minus_process": float(diff.mean()),
            "share_process_better": float((diff > 0).mean())}


def reproduce_s64(x: pd.DataFrame) -> dict:
    """§64's own convention on the §64 data (made and resolved by the cut)."""
    from backend.services import forecast_reputation as FR
    cut_end = pd.Timestamp(CUT_DAY, tz="UTC") + pd.Timedelta(days=1)
    s = x[(x["period"] == "P1") & ~x["resolved_after_cut"]]
    g = pd.DataFrame({"arm": s["specialist"].astype(str), "p": s["p"], "y": s["y"],
                      "made_at": s["made_ts"]})
    out = {"convention": "later half of each arm by made_at, pooled per family, "
                         "family's own base rate (forecast_reputation._pooled_heldout_skill)",
           "frame": f"kind in (PROCESS, PERSONA), made and resolved before {cut_end.date()}, "
                    "pre-window rows only"}
    for kind in (PROCESS, PERSONA):
        sub = g[s["kind"] == kind]
        out[kind] = {"n_rows": int(len(sub)),
                     "heldout_skill": FR._f(FR._pooled_heldout_skill(sub)) if len(sub) else None}
    return out


def holdout_shrink(d: pd.DataFrame) -> dict:
    """P2 PROCESS rows: raw as written, and with §64's 0.65 shrink toward 0.5
    applied ex ante to rows the writer did not already shrink."""
    sub = d[(d["period"] == "P2") & (d["kind"] == PROCESS)].copy()
    if sub.empty:
        return {"status": "CANNOT_DETERMINE", "why": "no P2 process rows"}
    already = sub["shrink_basis"].astype(str).str.contains("magnitude", case=False, na=False)
    # the base rate KNOWN at the cut: P1 process rows resolved by then, per stratum
    p1 = d[(d["period"] == "P1") & (d["kind"] == PROCESS) & ~d["resolved_after_cut"]]
    b1 = p1.groupby("stratum")["y"].mean()
    out = {"n": int(len(sub)), "n_already_shrunk_by_writer": int(already.sum()),
           "raw": skill_of(sub), "strata_with_exante_base": int(sub["stratum"].isin(b1.index).sum())}
    for name, target in (("shrunk_toward_0_5", pd.Series(0.5, index=sub.index)),
                         ("shrunk_toward_exante_base", sub["stratum"].map(b1).fillna(0.5))):
        p2 = sub["p"].where(already, target + SHRINK * (sub["p"] - target))
        shr = sub.assign(p=p2)
        shr["bs"] = (shr["p"] - shr["y"]) ** 2
        shr["ls"] = _ls(shr["p"].to_numpy(float), shr["y"].to_numpy(float))
        out[name] = skill_of(shr)
        out[name + "_by_obs_h"] = {f"{o}|h{h}": skill_of(g) for (o, h), g in
                                   shr.groupby(["observable", "h"])}
    out["raw_by_obs_h"] = {f"{o}|h{h}": skill_of(g) for (o, h), g in sub.groupby(["observable", "h"])}
    return out


def vol_verdict(n_blocks: int, lo: float | None, hi: float | None) -> str:
    """The script's own block rule applied to LLM minus vol prior. Below
    MIN_CLUSTERS_FOR_VERDICT date blocks the interval is printed and NOT read."""
    if n_blocks < MIN_CLUSTERS_FOR_VERDICT:
        return (f"CANNOT_DISTINGUISH (too few blocks: {n_blocks} date "
                f"block{'' if n_blocks == 1 else 's'} < "
                f"{MIN_CLUSTERS_FOR_VERDICT}; interval printed, not read)")
    if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)):
        return "CANNOT_DETERMINE (no interval)"
    if lo > 0:
        return "OBSERVED (LLM above the vol prior)"
    if hi < 0:
        return "OBSERVED (vol prior above the LLM)"
    return "CANNOT_DISTINGUISH (interval spans 0)"


def arm_mean_frame(g: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One LLM forecast per (ticker, made day, horizon, threshold): the MEAN of the
    arms that forecast it. The formula makes one forecast per ticker-day, so this
    is the like-for-like unit; scoring five arms as five rows counts each event
    five times for the LLM's sampling noise and once for the formula's."""
    key = ["ticker", "made_day", "h", "threshold"]
    grp = g.groupby(key, sort=True)
    m = grp.agg(p=("p", "mean"), p_vol=("p_vol", "first"), y=("y", "first"),
                y_n=("y", "nunique"), base=("base", "first"), block=("block", "first"),
                period=("period", "first"), made_month=("made_month", "first"),
                n_arms=("specialist", "nunique")).reset_index()
    bad = m["y_n"] > 1
    info = {"ticker_days": int(len(m)), "dropped_arms_disagree_on_outcome": int(bad.sum()),
            "arms_per_ticker_day": {str(k): int(v) for k, v in
                                    m["n_arms"].value_counts().sort_index().items()},
            "arms": sorted(g["specialist"].astype(str).unique().tolist())}
    return m[~bad].drop(columns=["y_n"]), info


def _vol_cell(sub: pd.DataFrame, n_boot: int, rng: np.random.Generator) -> dict:
    """LLM vs the vol prior on one frame (columns p, p_vol, y, base, block, made_day)."""
    ref = (sub["base"] - sub["y"]) ** 2
    llm = pd.DataFrame({"block": sub["block"], "bs": (sub["p"] - sub["y"]) ** 2, "bs_ref": ref,
                        "kind": "LLM"})
    vol = pd.DataFrame({"block": sub["block"], "bs": (sub["p_vol"] - sub["y"]) ** 2,
                        "bs_ref": ref, "kind": "VOL"})
    den = float(ref.sum())
    bl = (1 - float(llm["bs"].sum()) / den) if den > 0 else None
    bv = (1 - float(vol["bs"].sum()) / den) if den > 0 else None
    nb = int(sub["block"].nunique())
    r: dict[str, Any] = {
        "n": int(len(sub)), "n_date_blocks": nb, "n_days": int(sub["made_day"].nunique()),
        "bss_llm": bl, "bss_vol_prior": bv,
        "llm_minus_vol": None if bl is None or bv is None else bl - bv,
        "days_vol_prior_wins": int(sum(
            float(((d["p_vol"] - d["y"]) ** 2).mean()) < float(((d["p"] - d["y"]) ** 2).mean())
            for _, d in sub.groupby("made_day")))}
    lo = hi = None
    if nb >= 2 and den > 0:
        bd = cluster_bootstrap(pd.concat([llm, vol]), "block", n_boot, rng, by="kind",
                               order=("LLM", "VOL"))["diff"]
        lo, hi = bd["lo"], bd["hi"]
        r["llm_minus_vol_ci_date_blocks"] = [lo, hi]
        r["llm_minus_vol_se_date_blocks"] = bd["se"]
        r["interval_excludes_zero"] = bool(lo > 0 or hi < 0)
    else:
        r["llm_minus_vol_ci_date_blocks"] = None
        r["interval_excludes_zero"] = False
    r["interval_read"] = bool(nb >= MIN_CLUSTERS_FOR_VERDICT)
    r["verdict"] = vol_verdict(nb, lo, hi)
    return r


def vol_prior_rows(x: pd.DataFrame, bars: Path | pd.DataFrame | None, n_boot: int,
                   rng: np.random.Generator) -> list[dict]:
    """PROCESS magnitude rows vs the $0 trailing-vol prior on the SAME events
    (`forecast_reputation._trailing_sigma` / `_abs_move_p`), same stratum reference.

    Two units per cell. `arm_rows`: every arm's forecast is a row (the formula is
    repeated beside each). `arm_mean`: the arms averaged into ONE forecast per
    ticker-day, beside the formula's one. Cells: period (P1, P2, ALL) x horizon,
    and made month x horizon. Every cell carries a verdict under the block rule
    and its OWN count of rows that had no sigma."""
    from backend.services import forecast_reputation as FR
    g = x[(x["kind"] == PROCESS) & (x["observable"] == "abs_move_exceeds")].copy()
    if g.empty or bars is None or (not isinstance(bars, pd.DataFrame) and not Path(bars).exists()):
        return [{"status": "CANNOT_DETERMINE", "why": "no magnitude rows or no bars panel"}]
    if not isinstance(bars, pd.DataFrame):
        bars = pd.read_parquet(bars, columns=["symbol", "date", "close"],
                               filters=[("symbol", "in", sorted(set(g["ticker"].str.upper())))])
    sig = FR._trailing_sigma(g.assign(made_at=g["made_ts"]), bars)
    thr = pd.to_numeric(g["threshold"], errors="coerce")
    g["has_sigma"] = (sig.notna() & thr.notna() & (sig > 0)).to_numpy()
    g["p_vol"] = np.nan
    for h, idx in g[g["has_sigma"]].groupby("h").groups.items():
        g.loc[idx, "p_vol"] = FR._abs_move_p(thr[idx].to_numpy(float), sig[idx].to_numpy(float),
                                             float(h))
    ok = g[g["has_sigma"]]
    if ok.empty:
        return [{"status": "CANNOT_DETERMINE", "why": "no magnitude row has a trailing sigma",
                 "n_rows_without_sigma": int(len(g))}]
    mean_all, info = arm_mean_frame(ok)
    td = ["ticker", "made_day", "h", "threshold"]
    out: list[dict] = []
    cells: list[tuple[str, str, str, int]] = []
    for per in ("P1", "P2", "ALL"):
        cells += [("period", "period", per, int(h)) for h in sorted(ok["h"].unique())]
    for mo in sorted(ok["made_month"].unique()):
        cells += [("month", "made_month", str(mo), int(h)) for h in sorted(ok["h"].unique())]

    def pick(d: pd.DataFrame, col: str, val: str, h: int) -> pd.DataFrame:
        d = d[d["h"] == h]
        return d if val == "ALL" else d[d[col] == val]

    for split, col, val, h in cells:
        raw, rows, mean = pick(g, col, val, h), pick(ok, col, val, h), pick(mean_all, col, val, h)
        if rows.empty:
            continue
        no_sig = raw[~raw["has_sigma"]]
        for unit, sub, miss in (("arm_rows", rows, int(len(no_sig))),
                                ("arm_mean", mean, int(len(no_sig[td].drop_duplicates())))):
            if sub.empty:
                continue
            r = {"split": split, col: val, "h": h, "unit": unit, "n_rows_without_sigma": miss}
            r.update(_vol_cell(sub, n_boot, rng))
            if unit == "arm_mean":
                r["arms_per_ticker_day_min"] = int(sub["n_arms"].min())
                r["arms_per_ticker_day_max"] = int(sub["n_arms"].max())
            out.append(r)
    out.append({"split": "meta", "unit_arm_mean": info,
                "sigma_window_sessions": int(FR.VOL_PRIOR_WINDOW),
                "block_rule": f"a verdict reads the interval only at >= {MIN_CLUSTERS_FOR_VERDICT} "
                              "date blocks",
                "scope": "abs_move_exceeds rows of investigator:* arms only; direction "
                         "forecasts have no such comparator"})
    return out


def persona_made_census(D: pd.DataFrame, cm: pd.DataFrame) -> dict:
    """When the persona forecasts were MADE, on every ledger row (voided and
    ungraded included; declared fields only)."""
    k = D.assign(specialist=D["specialist"].astype(str), model=D["model"].astype(str)).merge(
        cm[["specialist", "model", "kind"]], on=["specialist", "model"], how="left")
    out: dict[str, Any] = {}
    for kind in (PERSONA, PROCESS):
        ts = pd.to_datetime(k.loc[k["kind"] == kind, "made_at"], utc=True, errors="coerce",
                            format="ISO8601").dropna()
        days = ts.dt.strftime("%Y-%m-%d").value_counts().sort_index()
        hours = ts.dt.strftime("%Y-%m-%dT%H").value_counts()
        out[kind] = {"n_rows": int(len(ts)), "n_made_days": int(len(days)),
                     "first_day": str(days.index[0]) if len(days) else None,
                     "last_day": str(days.index[-1]) if len(days) else None,
                     "rows_by_day": ({str(d): int(n) for d, n in days.items()}
                                     if len(days) <= 5 else "more than 5 days"),
                     "busiest_utc_hour": str(hours.index[0]) if len(hours) else None,
                     "share_in_busiest_utc_hour": (float(hours.iloc[0] / len(ts))
                                                   if len(ts) else None)}
    return out


def run_table1(ledger: Path, sessions: np.ndarray, n_boot: int, seed: int,
               bars_path: Path | None = None, asof: Any = None) -> dict:
    t0 = time.time()
    D, O, stats = stream_ledger(ledger)
    asof_info: dict = {"asof_utc": None}
    if asof is not None:
        D, O, asof_info = apply_asof(D, O, asof)
    cm = classify_forecasters(D[["specialist", "model"]])
    cm_hash = class_map_hash(cm)
    classified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    x, flow = build_graded(D, O, cm, sessions)
    rng = np.random.default_rng(seed)
    x = add_reference(x)
    x["block"] = assign_date_blocks(x)
    res: dict[str, Any] = {
        "ledger": str(ledger), "ledger_stream_stats": stats, "asof": asof_info, "flow": flow,
        "persona_made_census": persona_made_census(D, cm),
        "classification": {"classified_at_run_utc": classified_at,
                           "classified_at_run_utc_is": (
                               "the time THIS process built the map, before it joined outcomes. "
                               "It is a run time, not evidence of a freeze before grading; that "
                               "evidence is the rule text and its time in notes.txt and the map "
                               "hash below, which depends only on declared fields"),
                           "sha256": cm_hash,
                           "counts_rows": flow["by_kind_all_rows"],
                           "map": cm.sort_values(["kind", "specialist"]).to_dict("records")},
        "cut_day": CUT_DAY, "n_boot": n_boot, "seed": seed}
    splits = 0
    # headline: kind x observable x horizon, all periods
    res["by_kind_observable_horizon"] = table_rows(x, ["kind", "observable", "h"], n_boot, rng)
    splits += len(res["by_kind_observable_horizon"])
    res["by_kind_period_observable_horizon"] = table_rows(
        x, ["kind", "period", "observable", "h"], n_boot, rng)
    splits += len(res["by_kind_period_observable_horizon"])
    p1 = x[x["period"] == "P1"].copy()
    p1["resolved_after_cut"] = p1["resolved_after_cut"].map({True: "resolved_after_cut",
                                                             False: "resolved_by_cut"})
    res["p1_by_resolution"] = table_rows(p1, ["kind", "resolved_after_cut", "observable", "h"],
                                         n_boot, rng)
    splits += len(res["p1_by_resolution"])
    res["by_subtype_period"] = table_rows(x[x["kind"] == PROCESS],
                                          ["subtype", "period", "observable", "h"], n_boot, rng)
    splits += len(res["by_subtype_period"])
    # contrast on the cells BOTH kinds forecast (same observable and horizon),
    # on every row and on P1 only (the era the personas were written in)
    res["contrast"] = {}
    for (obs, h), sub in x.groupby(["observable", "h"]):
        if sub["kind"].nunique() < 2 or sub.groupby("kind").size().min() < 30:
            continue
        for per in ("ALL", "P1"):
            s3 = sub if per == "ALL" else sub[sub["period"] == "P1"]
            both = s3.groupby("stratum")["kind"].nunique()
            shared = both[both == 2].index
            s3 = add_reference(s3[s3["stratum"].isin(shared)].drop(
                columns=["stratum", "base", "bs", "bs_ref", "ls", "ls_ref"]))
            c = contrast(s3, n_boot, rng)
            nk = s3.groupby("kind").size()
            if len(nk) == 2 and int(nk.min()) < 30 and "verdict_date_blocks" in c:
                c["verdict_date_blocks"] = c["verdict_ticker"] = (
                    f"CANNOT_DETERMINE: {int(nk.min())} rows for one kind in the shared strata")
            c["shared_strata"] = [str(z) for z in shared]
            c["rows_dropped_unshared_stratum"] = int(len(sub if per == "ALL" else
                                                         sub[sub["period"] == "P1"]) - len(s3))
            res["contrast"][f"{obs}|h{h}|{per}"] = c
            splits += 1
    # by month (made month), per kind and observable
    bm = []
    for (k, obs, mo), sub in x.groupby(["kind", "observable", "made_month"]):
        hmax = int(sub["h"].max())
        r = {"kind": k, "observable": obs, "made_month": mo, **skill_of(sub),
             "horizons": sorted(int(v) for v in sub["h"].unique()),
             "n_days": int(sub["made_day"].nunique()),
             "n_date_blocks": int(assign_date_blocks(sub, h_override=hmax).nunique()),
             "block_h": hmax, "n_tickers": int(sub["ticker"].nunique())}
        bm.append(r)
    res["by_month"] = bm
    splits += len(bm)
    res["matched"] = [matched_pairs(x, t) for t in (0, 5, 10)]
    splits += 3
    res["reproduce_s64"] = reproduce_s64(x)
    res["holdout_shrink"] = holdout_shrink(x)
    res["vol_prior"] = vol_prior_rows(x, bars_path, n_boot, rng)
    splits += sum(1 for r in res["vol_prior"] if r.get("unit"))
    res["splits_looked_at"] = splits
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ═════════════════════════════ TABLE 2 ═══════════════════════════════════════
class Panel:
    """Wide open/close matrices over the survivorship-corrected deep panel."""

    def __init__(self, bars: pd.DataFrame):
        b = bars[["symbol", "date", "open", "close", "volume"]]
        self.long = b.sort_values("date", kind="stable").reset_index(drop=True)
        self.long_dates = self.long["date"].to_numpy("datetime64[ns]")
        self.close = b.pivot_table(index="date", columns="symbol", values="close",
                                   aggfunc="first").sort_index().astype("float32")
        self.open = b.pivot_table(index="date", columns="symbol", values="open",
                                  aggfunc="first").reindex(index=self.close.index,
                                                           columns=self.close.columns
                                                           ).astype("float32")
        self.dates = self.close.index.to_numpy("datetime64[ns]")
        self.sym = list(self.close.columns)
        self.col = {s: i for i, s in enumerate(self.sym)}
        self.C = self.close.to_numpy()
        self.Cf = self.close.ffill().to_numpy()
        self.O = self.open.to_numpy()

    def recent(self, asof: np.datetime64, days: int = 150) -> pd.DataFrame:
        lo = np.searchsorted(self.long_dates, asof - np.timedelta64(days, "D"), side="left")
        hi = np.searchsorted(self.long_dates, asof, side="right")
        return self.long.iloc[lo:hi]


def bands_and_pool(panel: Panel, asof: np.datetime64) -> tuple[dict, dict]:
    """The REAL llm_portfolio band and live-pool functions on a recent slice."""
    from backend.services import llm_portfolio as LP
    rb = panel.recent(asof)
    bands = LP.liquidity_bands(rb, asof=pd.Timestamp(asof))
    pool = LP._live_pool(rb, pd.Timestamp(asof), set())
    by_band: dict[str, list[str]] = {}
    for s in pool:
        if s in panel.col:
            by_band.setdefault(bands.get(s, "small"), []).append(s)
    return bands, by_band


def twin_of(names: list[str], bands: dict, by_band: dict, rng: np.random.Generator) -> list[str]:
    """`llm_portfolio.twins` random_same_band draw: one-for-one, same band,
    excluding the parent's names and earlier picks, falling back to the pool."""
    parent = set(names)
    # production's fallback pool is `_live_pool`, alphabetical; a band-grouped order
    # here would map the same random integer to a different name
    pool = sorted(s for v in by_band.values() for s in v if s not in parent)
    chosen: set = set()
    out = []
    for t in sorted(names):
        cands = [s for s in by_band.get(bands.get(t, ""), []) if s not in chosen and s not in parent]
        if not cands:
            cands = [s for s in pool if s not in chosen]
        pick = str(cands[int(rng.integers(len(cands)))])
        chosen.add(pick)
        out.append(pick)
    return out


ENTRY_COST_CONVENTION = (
    "half of the xs_ranker.COST_BPS_BY_BAND round trip, charged once at entry and subtracted "
    "from the NAV (net = gross - round_trip/2), as llm_portfolio.grade does (entry_cost_bps = "
    "cost_bps / 2). Until this fix round the script charged the FULL round trip at entry, "
    "3 to 17.5 bps more per book depending on band (mega 6, large 10, mid 18, small 35 bps "
    "round trip). Not matched: production takes each name's band from the 63 sessions before "
    "ITS entry bar; here the band is the one drawn for the twin, as of the session before entry. "
    "SPY pays no cost in either.")


def entry_cost_fraction(tickers: Iterable[str], bands: dict) -> float:
    """Equal-weight entry cost as a fraction of NAV: HALF the band round trip
    (`llm_portfolio.grade`: "charged once, on entry ... half of a round trip,
    because the book has not sold yet")."""
    from backend.services import xs_ranker as XR
    bps = [XR.COST_BPS_BY_BAND.get(bands.get(t, "small"), XR.COST_BPS_BY_BAND["small"])
           for t in tickers]
    return float(np.mean(bps)) / 2.0 / 1e4 if bps else 0.0


def book_path(panel: Panel, names: list[str], i0: int, L: int, bands: dict) -> np.ndarray | None:
    """Equal-weight buy-and-hold NAV, entry at the OPEN of session i0, net of the
    entry cost (`entry_cost_fraction`); L period returns (open->close, then
    close->close). A name with no entry open is excluded and its weight re-spread
    (grade v1)."""
    idx = [panel.col[s] for s in names if s in panel.col]
    if not idx:
        return None
    o = panel.O[i0, idx]
    ok = np.isfinite(o) & (o > 0)
    if not ok.any():
        return None
    idx = [j for j, k in zip(idx, ok) if k]
    o = o[ok]
    cl = panel.Cf[i0:i0 + L, idx] / o
    cl = np.where(np.isfinite(cl), cl, 1.0)
    nav = cl.mean(axis=1) - entry_cost_fraction([panel.sym[j] for j in idx], bands)
    prev = np.concatenate([[1.0], nav[:-1]])
    return nav / prev - 1.0


def spy_path(panel: Panel, i0: int, L: int) -> np.ndarray:
    if "SPY" not in panel.col:
        raise Refusal("the panel has no SPY bars: every label is an excess over SPY, so "
                      "there is nothing to label against")
    j = panel.col["SPY"]
    c = panel.Cf[i0:i0 + L, j]
    prev = np.concatenate([[panel.O[i0, j]], c[:-1]])
    return c / prev - 1.0


def label_book(dates: list[str], b: np.ndarray, s: np.ndarray, twin_total: float | None,
               L: int, p: dict, replicated_by: str | None = None) -> dict:
    """The REAL book_dna machinery on one series."""
    from backend.services import book_dna as BD
    series = [(d, float(x), float(y)) for d, x, y in zip(dates, b, s)]
    excess = 100.0 * (float(np.prod(1 + b)) - float(np.prod(1 + s)))
    sub = BD.subwindows(series, L)
    fair = None if twin_total is None else 100.0 * (float(np.prod(1 + b)) - twin_total)
    lab = BD.evidence_label(sessions=L, excess_pp=excess, sub=sub, fair_twin_excess_pp=fair,
                            replicated_by=replicated_by, p=p)
    beta = BD.beta_of(series, p["min_beta_obs"])
    bv = beta.get("value")
    if not isinstance(bv, (int, float)):
        bv = beta.get("beta_same_day")
    return {"label": lab["label"].split("(")[0], "excess_pp": excess, "fair_pp": fair,
            "beta": bv if isinstance(bv, (int, float)) else None,
            "n_sub_pos": sub.get("n_positive")}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return [max(0.0, c - h), min(1.0, c + h)]


def simulate(panel: Panel, windows: Iterable[int], ks: Iterable[int], bands_list: Iterable[str],
             books_per_cell: int, seed: int, n_starts: int = 60,
             era_from: str | None = None) -> pd.DataFrame:
    from backend.services import book_dna as BD
    p = BD.params()
    rng = np.random.default_rng(seed)
    nd = len(panel.dates)
    lo_i = 64
    if era_from:
        lo_i = max(lo_i, int(np.searchsorted(panel.dates, np.datetime64(era_from), side="left")))
    rows = []
    cache: dict[int, tuple[dict, dict]] = {}
    for L in windows:
        hi_i = nd - L
        if hi_i <= lo_i:
            continue
        starts = np.sort(rng.choice(np.arange(lo_i, hi_i), size=min(n_starts, hi_i - lo_i),
                                    replace=False))
        for i0 in starts:
            asof_i = int(i0) - 1
            if asof_i not in cache:
                cache[asof_i] = bands_and_pool(panel, panel.dates[asof_i])
            bands, by_band = cache[asof_i]
            dates = [str(pd.Timestamp(d).date()) for d in panel.dates[i0:i0 + L]]
            tblock = str(pd.Timestamp(dates[0]).to_period(TIME_BLOCK_FREQ))
            spy = spy_path(panel, int(i0), L)
            per = max(1, books_per_cell // len(starts))
            for k in ks:
                for band in bands_list:
                    src = ([s for v in by_band.values() for s in v] if band == "mixed"
                           else by_band.get(band, []))
                    src = [s for s in src if s != "SPY"]
                    if len(src) < 2 * k:
                        continue
                    for _ in range(per):
                        names = [str(s) for s in rng.choice(src, size=k, replace=False)]
                        sib = [str(s) for s in rng.choice(src, size=k, replace=False)]
                        tw = twin_of(names, bands, by_band, rng)
                        b = book_path(panel, names, int(i0), L, bands)
                        t = book_path(panel, tw, int(i0), L, bands)
                        sb = book_path(panel, sib, int(i0), L, bands)
                        if b is None or t is None or sb is None:
                            continue
                        ttot = float(np.prod(1 + t))
                        base = label_book(dates, b, spy, None, L, p)
                        twin_r = label_book(dates, b, spy, ttot, L, p)
                        sib_l = label_book(dates, sb, spy, None, L, p)
                        any_r = label_book(dates, b, spy, ttot, L, p,
                                           replicated_by=("sibling" if sib_l["label"] == "EARLY_EVIDENCE"
                                                          else None))
                        rows.append({"L": L, "k": k, "band": band, "start": dates[0],
                                     "year": dates[0][:4], "time_block": tblock,
                                     "excess_pp": base["excess_pp"],
                                     "beta": base["beta"], "n_sub_pos": base["n_sub_pos"],
                                     "early": base["label"] == "EARLY_EVIDENCE",
                                     "replicated_twin_route": twin_r["label"] == "REPLICATED",
                                     "replicated_any_route": any_r["label"] == "REPLICATED",
                                     "label_twin_route": twin_r["label"]})
    return pd.DataFrame(rows)


RATE_COLS = (("early", "early_or_higher"), ("replicated_twin_route", "replicated_twin"),
             ("replicated_any_route", "replicated_twin_or_sibling_upper_bound"))
SIBLING_ROUTE_NOTE = (
    "replicated_twin_or_sibling_upper_bound is an UPPER BOUND on the REPLICATED rate. The "
    "simulation gives every book an independent random book as its sibling; production accepts "
    "only another STRATEGY book of the same rule as a sibling (book_dna replicated_by), and "
    "most production books have none. Production fair twins exist only for llm_portfolio books, "
    "so replicated_twin applies to books that have a random twin.")
TIME_BLOCK_NOTE = (
    "Books in one window share one market draw, and windows overlap. The interval resamples "
    "whole START periods (PAPER_TABLES_TIME_BLOCK_FREQ, calendar quarter). A long window "
    "reaches into the next quarter, so neighbouring blocks still share days and the interval "
    "is, if anything, too narrow. Below PAPER_TABLES_MIN_CLUSTERS_FOR_VERDICT blocks the "
    "interval is printed and flagged not read. The Wilson interval over books treats books as "
    "independent; it is kept in the receipt for comparison and is not the headline.")


def time_block_interval(k: np.ndarray, n: np.ndarray, n_boot: int,
                        rng: np.random.Generator) -> dict:
    """95% interval of sum(k)/sum(n) by resampling whole time blocks."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    nb = len(k)
    if nb < 2:
        return {"n_time_blocks": int(nb), "se": None, "ci95": None, "read": False}
    draws = rng.integers(0, nb, size=(n_boot, nb))
    r = k[draws].sum(axis=1) / n[draws].sum(axis=1)
    return {"n_time_blocks": int(nb), "se": float(r.std()),
            "ci95": [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))],
            "read": bool(nb >= MIN_CLUSTERS_FOR_VERDICT)}


def label_rates(sim: pd.DataFrame, by: list[str], n_boot: int = N_BOOT,
                rng: np.random.Generator | None = None) -> list[dict]:
    """Per group: the rate of each label, its time-block interval, the spread of
    the rate across single windows, and how the books did against SPY.
    A window is one (length, start) pair."""
    out = []
    if sim.empty:
        return out
    rng = np.random.default_rng(SEED + 2) if rng is None else rng
    has_block = "time_block" in sim.columns
    for key, sub in sim.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        n = len(sub)
        r = dict(zip(by, [k if not isinstance(k, (np.integer,)) else int(k) for k in key]))
        r["n_books"] = int(n)
        win = sub.groupby(["L", "start"])
        r["n_windows"] = int(win.ngroups)
        for col, name in RATE_COLS:
            k_ = int(sub[col].sum())
            r[name] = k_ / n
            if has_block:
                g = sub.groupby("time_block")[col].agg(["sum", "count"])
                tb = time_block_interval(g["sum"].to_numpy(), g["count"].to_numpy(), n_boot, rng)
                r["n_time_blocks"] = tb["n_time_blocks"]
                r[name + "_time_block_ci95"] = tb["ci95"]
                r[name + "_time_block_se"] = tb["se"]
                r["time_block_interval_read"] = tb["read"]
            r[name + "_wilson95_books_as_independent"] = wilson(k_, n)
            wr = win[col].mean().to_numpy(float)
            r[name + "_by_window"] = {"min": float(wr.min()), "p10": float(np.percentile(wr, 10)),
                                      "median": float(np.median(wr)),
                                      "p90": float(np.percentile(wr, 90)), "max": float(wr.max())}
        r["share_positive_excess_vs_spy"] = float((sub["excess_pp"] > 0).mean())
        r["median_excess_pp"] = float(sub["excess_pp"].median())
        out.append(r)
    return out


def zero_edge_rate(windows: Iterable[int], n_draws: int, seed: int,
                   daily_sd: float = ZERO_EDGE_DAILY_SD) -> dict:
    """How often the REAL label fires on a book with exactly zero edge: iid
    symmetric log returns for the book and, independently, for the benchmark, so
    P(excess > 0) is one half by construction. Random names against SPY are not
    this null (they sat slightly behind SPY in 2016-2026)."""
    from backend.services import book_dna as BD
    p = BD.params()
    rng = np.random.default_rng(seed)
    ws = [int(w) for w in windows]
    per = max(1, n_draws // max(len(ws), 1))
    by_L, tot_k, tot_n = {}, 0, 0
    for L in ws:
        dates = [f"d{i:04d}" for i in range(L)]
        k = 0
        for _ in range(per):
            b = np.expm1(rng.normal(0.0, daily_sd, L))
            sp = np.expm1(rng.normal(0.0, daily_sd, L))
            k += int(label_book(dates, b, sp, None, L, p)["label"] == "EARLY_EVIDENCE")
        by_L[str(L)] = k / per
        tot_k, tot_n = tot_k + k, tot_n + per
    return {"early_or_higher": tot_k / tot_n if tot_n else None, "n_books": tot_n,
            "by_L": by_L, "daily_sd": daily_sd, "seed": seed,
            "what": "iid symmetric log returns, book and benchmark independent; real "
                    "book_dna.evidence_label and subwindows; no twin, no cost"}


def live_twins(book_dna_path: Path) -> dict:
    """Labels the live pipeline gave its own random twins (stored, not recomputed),
    plus a recompute of each through evidence_label to show the call agrees."""
    from backend.services import book_dna as BD
    d = json.loads(Path(book_dna_path).read_text(encoding="utf-8"))
    p = d.get("params") or BD.params()
    rnd = {"random_same_band", "matched_random", "random_sleeve", "selection_random_same_set",
           "matched_twin21"}
    rows, agree = [], 0
    for b in d.get("books") or []:
        if b.get("category") != "twin" or b.get("twin_kind") not in rnd:
            continue
        stored = str((b.get("evidence") or {}).get("label", "")).split("(")[0]
        re_ = BD.evidence_label(sessions=b.get("sessions_graded"), excess_pp=b.get("excess_pp"),
                                sub=b.get("subwindows") or {},
                                fair_twin_excess_pp=(b.get("fair_twin") or {}).get("excess_over_twin_pp"),
                                replicated_by=None, p=p)["label"].split("(")[0]
        agree += int(re_ == stored)
        rows.append({"account": b.get("account"), "twin_kind": b.get("twin_kind"),
                     "sessions": b.get("sessions_graded"), "inception": b.get("inception"),
                     "excess_pp": b.get("excess_pp"), "label": stored})
    df = pd.DataFrame(rows)
    out = {"receipt": str(book_dna_path), "generated_utc": d.get("generated_utc"),
           "n_random_twins": int(len(df)), "recompute_agrees": int(agree)}
    if df.empty:
        return out
    tab = []
    for (kind,), sub in df.groupby(["twin_kind"]):
        k_ = int((sub["label"] != "OBSERVED").sum())
        tab.append({"twin_kind": kind, "n": int(len(sub)), "early_or_higher": k_ / len(sub),
                    "wilson95": wilson(k_, len(sub)),
                    "n_distinct_inceptions": int(sub["inception"].nunique()),
                    "sessions": sorted({int(s) for s in sub["sessions"].dropna()})})
    k_all = int((df["label"] != "OBSERVED").sum())
    out["by_kind"] = tab
    out["all"] = {"n": int(len(df)), "early_or_higher": k_all / len(df),
                  "wilson95": wilson(k_all, len(df)),
                  "n_distinct_inceptions": int(df["inception"].nunique())}
    out["by_inception"] = [{"inception": str(i), "n": int(len(s)),
                            "early_or_higher": float((s["label"] != "OBSERVED").mean())}
                           for i, s in df.groupby("inception")]
    return out


def load_deep_bars(paths: list[Path], asof: Any = None) -> tuple[pd.DataFrame, str]:
    """The split-stitched deep panel, or a REFUSAL. An unstitched concatenation
    would put a reused ticker's two companies in one series and its jump into
    book returns, so there is no fallback."""
    from backend.services import xs_ranker as XR
    try:
        b = XR.load_bars(paths, split_stitched=True)
    except Exception as e:                                   # noqa: BLE001 - refused by name
        raise Refusal(f"the deep panel could not be loaded split-stitched "
                      f"({type(e).__name__}: {str(e)[:200]}); an unstitched concat is not a "
                      f"substitute, so Table 2 does not run") from e
    how = "xs_ranker.load_bars(deep + delisted, split_stitched=True)"
    b = b[["symbol", "date", "open", "close", "volume"]].copy()
    if asof is not None:
        cap = pd.Timestamp(asof)
        cap = (cap.tz_convert("UTC").tz_localize(None) if cap.tzinfo is not None else cap)
        b = b[pd.to_datetime(b["date"]) <= cap.normalize()]
        how += f", bars dated <= {cap.date()} (--asof)"
    if b.empty:
        raise Refusal("the deep panel is empty after the --asof cap")
    if not (b["symbol"] == "SPY").any():
        raise Refusal("the deep panel has no SPY bars: every label is an excess over SPY")
    return b, how


def run_table2(bar_paths: list[Path], book_dna_path: Path | None, seed: int,
               books_per_cell: int, windows=WINDOWS, ks=KS, n_boot: int = N_BOOT,
               asof: Any = None) -> dict:
    t0 = time.time()
    bars, how = load_deep_bars(bar_paths, asof)
    panel = Panel(bars)
    n_sym = int(bars["symbol"].nunique())
    last_day = bars.groupby("symbol")["date"].max()
    end = bars["date"].max()
    dead = int((last_day < end - pd.Timedelta(days=31)).sum())
    del bars
    bands_list = ("mega", "large", "mid", "small", "mixed")
    sim = simulate(panel, windows, ks, bands_list, books_per_cell, seed)
    sim25 = simulate(panel, windows, (20,), ("mixed",), books_per_cell, seed + 1,
                     era_from="2025-01-01")
    sim["beta_bucket"] = pd.cut(sim["beta"].astype(float), [-9, 0.6, 0.9, 1.1, 1.4, 9],
                                labels=["<0.6", "0.6-0.9", "0.9-1.1", "1.1-1.4", ">1.4"])
    rng_ci = np.random.default_rng(seed + 2)      # its own stream: the draws above do not move

    def rates(frame: pd.DataFrame, by: list[str]) -> list[dict]:
        return label_rates(frame, by, n_boot, rng_ci)

    res = {"bars": how, "panel_symbols": n_sym, "panel_symbols_stopped_trading_31d_before_end": dead,
           "panel_end": str(end.date()), "n_books": int(len(sim)), "seed": seed,
           "sim_start_first": str(sim["start"].min()) if len(sim) else None,
           "sim_start_last": str(sim["start"].max()) if len(sim) else None,
           "windows": list(windows), "ks": list(ks), "bands": list(bands_list),
           "label_function": "backend.services.book_dna.evidence_label (real, with BD.params())",
           "entry_cost_convention": ENTRY_COST_CONVENTION,
           "interval_method": TIME_BLOCK_NOTE, "time_block_freq": TIME_BLOCK_FREQ,
           "replicated_routes": SIBLING_ROUTE_NOTE, "n_boot": n_boot,
           "all": rates(sim.assign(_all="all"), ["_all"]),
           "zero_edge_symmetric": zero_edge_rate(windows, ZERO_EDGE_DRAWS, seed + 3),
           "by_L": rates(sim, ["L"]),
           "by_k": rates(sim, ["k"]),
           "by_band": rates(sim, ["band"]),
           "by_beta_bucket": rates(sim.dropna(subset=["beta_bucket"]), ["beta_bucket"]),
           "by_L_k": rates(sim, ["L", "k"]),
           "by_year": rates(sim, ["year"]),
           "era_2025_26_k20_mixed_by_L": rates(sim25, ["L"])}
    if book_dna_path is not None and Path(book_dna_path).exists():
        res["live_random_twins"] = live_twins(book_dna_path)
    res["seconds"] = round(time.time() - t0, 1)
    return res, sim


def sessions_from(bar_paths: list[Path], asof: Any = None) -> np.ndarray:
    frames = [pd.read_parquet(p, columns=["date"], filters=[("symbol", "==", "SPY")])
              for p in bar_paths if Path(p).exists()]
    d = pd.concat(frames)["date"] if frames else pd.Series([], dtype="datetime64[ns]")
    ses = np.sort(pd.to_datetime(d).unique()).astype("datetime64[D]")
    if asof is not None:
        cap = pd.Timestamp(asof)
        cap = (cap.tz_convert("UTC").tz_localize(None) if cap.tzinfo is not None else cap)
        ses = ses[ses <= np.datetime64(cap.date(), "D")]
    if len(ses) == 0:
        raise Refusal(f"no SPY session found in {[str(p) for p in bar_paths]}: there is no "
                      "calendar to place a forecast's entry close or a book's window on")
    return ses


def _count_files(root: Path) -> dict:
    """Files in each live folder this script READS (BUILDER_RULES: print before/after)."""
    out = {}
    for sub in ("", "paper_accounts", "prices_deep", "prices_2025_26"):
        f = root / sub if sub else root
        out[sub or "."] = (sum(1 for x in f.iterdir() if x.is_file()) if f.exists() else -1)
    return out


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                           timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def run_meta(asof: Any, run_utc: str) -> dict:
    """What a reader needs to re-run this receipt: the code, the cap, the clock."""
    here = Path(__file__).resolve()
    head = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain", "--", "scripts/paper_tables.py", "backend/config.py",
                 "backend/services")
    return {"code_commit": head or "CANNOT_DETERMINE (git not available from this checkout)",
            "code_dirty_paths": (None if dirty is None else
                                 [ln.strip() for ln in dirty.splitlines() if ln.strip()]),
            "code_commit_describes_the_code": bool(head) and dirty == "",
            "script_sha256": hashlib.sha256(here.read_bytes()).hexdigest(),
            "run_utc": run_utc, "asof_utc": str(asof),
            "asof_is": "rows made after it are ignored, outcomes resolved after it count as "
                       "ungraded, bars dated after its day are dropped; default = the run start"}


# ═════════════════════════════ MARKDOWN ══════════════════════════════════════
#: The three headline sentences as the adversarial review (2026-11-15) corrected them. The
#: markdown prints each sentence rebuilt from THIS run's receipt and says whether it still
#: reads the same; when a number moved, both are printed.
REVIEW_HEADLINES = {
    "a": ("On random equal-weight books (counted per book, 2016-2026) the production "
          "EARLY_EVIDENCE rule fired on about 35% on average, with a time-clustered 95% interval "
          "of about 30-41%; the rate in a single window ranged from 1% to 97%. These books were "
          "slightly behind SPY; an exactly zero-edge symmetric book gets the label about 42% of "
          "the time. REPLICATED fired on about 25% of books that have a random twin, and up to "
          "31% if each book also had an independent sibling, which production books mostly do "
          "not."),
    "b": ("Persona vs process cannot be tested: effectively all persona forecasts were made in "
          "one run on 08-11/12."),
    "c": ("On magnitude questions only, a $0 trailing-63-day-volatility formula cannot be "
          "distinguished from the LLM process: level with the mean of the five arms; above the "
          "average single arm significantly only in August (8 days, below the 10-block rule). "
          "Direction forecasts have no such comparator."),
}
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


def _pct(v: float | None) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{round(100 * float(v)):d}"


def headline_a(r2: dict) -> str:
    a = r2["all"][0]
    lo, hi = a["early_or_higher_time_block_ci95"] or (None, None)
    w = a["early_or_higher_by_window"]
    side = "behind" if a["median_excess_pp"] < 0 else "ahead of"
    y0, y1 = str(r2["sim_start_first"])[:4], str(r2["panel_end"])[:4]
    return (f"On random equal-weight books (counted per book, {y0}-{y1}) the production "
            f"EARLY_EVIDENCE rule fired on about {_pct(a['early_or_higher'])}% on average, with a "
            f"time-clustered 95% interval of about {_pct(lo)}-{_pct(hi)}%; the rate in a single "
            f"window ranged from {_pct(w['min'])}% to {_pct(w['max'])}%. These books were slightly "
            f"{side} SPY; an exactly zero-edge symmetric book gets the label about "
            f"{_pct(r2['zero_edge_symmetric']['early_or_higher'])}% of the time. REPLICATED fired "
            f"on about {_pct(a['replicated_twin'])}% of books that have a random twin, and up to "
            f"{_pct(a['replicated_twin_or_sibling_upper_bound'])}% if each book also had an "
            f"independent sibling, which production books mostly do not.")


def headline_b(r1: dict) -> str:
    c = r1["persona_made_census"][PERSONA]
    if c["n_rows"] and c["n_made_days"] <= 2 and (c["share_in_busiest_utc_hour"] or 0) >= 0.99:
        first, last = str(c["first_day"]), str(c["last_day"])
        days = first[5:] if first == last else f"{first[5:]}/{last[8:]}"
        return ("Persona vs process cannot be tested: effectively all persona forecasts were "
                f"made in one run on {days}.")
    return (f"Persona forecasts were made on {c['n_made_days']} days ({c['first_day']} to "
            f"{c['last_day']}; {_pct(c['share_in_busiest_utc_hour'])}% in the busiest UTC hour); "
            "whether persona vs process can be tested is read from the date blocks per kind in "
            "the contrast cells, not asserted here.")


def headline_c(r1: dict) -> str:
    rows = [r for r in r1["vol_prior"] if r.get("unit")]
    meta = next((r for r in r1["vol_prior"] if r.get("split") == "meta"), None)
    if not rows or meta is None:
        return "The volatility-formula comparison could not be computed in this run."
    win = meta["sigma_window_sessions"]
    n_arms = len(meta["unit_arm_mean"]["arms"])
    arms = _WORDS.get(n_arms, str(n_arms))
    mean_all = [r for r in rows if r["split"] == "period" and r.get("period") == "ALL"
                and r["unit"] == "arm_mean"]
    observed = [r for r in rows if r["verdict"].startswith("OBSERVED")]
    # the month clause reads the SHORTEST horizon, where every decision day is its own
    # date block; a longer horizon has at most ~4 blocks in a month. Any other cell whose
    # unread interval excludes zero is listed under the headline by `unread_exclusions`.
    h_min = min(r["h"] for r in rows)
    sig_months = [r for r in rows if r["split"] == "month" and r["unit"] == "arm_rows"
                  and r["h"] == h_min
                  and r["interval_excludes_zero"] and (r["llm_minus_vol"] or 0) < 0]
    months = sorted({r["made_month"] for r in sig_months})
    level = bool(mean_all) and all(r["verdict"].startswith("CANNOT_DISTINGUISH") for r in mean_all)
    head = (f"On magnitude questions only, a $0 trailing-{win}-day-volatility formula cannot be "
            f"distinguished from the LLM process: level with the mean of the {arms} arms; ")
    tail = " Direction forecasts have no such comparator."
    if level and not observed and len(months) == 1:
        name = pd.Timestamp(months[0] + "-01").strftime("%B")
        days = max(r["n_days"] for r in sig_months)
        return (head + f"above the average single arm significantly only in {name} ({days} days, "
                f"below the {MIN_CLUSTERS_FOR_VERDICT}-block rule)." + tail)
    if level and not observed and not months:
        return head + "not significantly above the average single arm in any month." + tail
    cells = "; ".join(
        f"{r.get('period') or r.get('made_month')} h{r['h']} {r['unit']}: {r['verdict']}"
        for r in observed) or "none"
    return (f"On magnitude questions only, the $0 trailing-{win}-day-volatility formula and the "
            f"LLM process do not read as level in this run. Cells with an interval that is read "
            f"and excludes zero: {cells}. Months where the formula is above the average single "
            f"arm with an interval excluding zero: {', '.join(months) or 'none'}." + tail)


def unread_exclusions(r1: dict) -> list[str]:
    """Every vol-prior cell whose interval excludes zero on too few date blocks to
    be read. Printed under headline (c) so the sentence cannot hide one."""
    out = []
    for r in r1["vol_prior"]:
        if r.get("unit") and r["interval_excludes_zero"] and not r["interval_read"]:
            ci = r["llm_minus_vol_ci_date_blocks"]
            out.append(f"{r.get('period') or r.get('made_month')} h={r['h']} {r['unit']} "
                       f"({r['n_date_blocks']} date blocks, LLM minus formula "
                       f"{100 * r['llm_minus_vol']:+.1f} pp [{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}])")
    return out


def _f1(v: float | None) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{100 * float(v):+.1f}"


def _ci(ci: list | None, signed: bool = True) -> str:
    if not ci:
        return "none"
    return (f"[{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}]" if signed
            else f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]")


def render_markdown(r1: dict | None, r2: dict | None, meta: dict, files: dict) -> str:
    """The report a reader opens first: three headline sentences, then the cells
    behind each. Every number is read from the receipts written by this run."""
    L = ["# Paper tables", "",
         f"Code `scripts/paper_tables.py` at commit `{meta['code_commit']}`"
         + ("" if meta["code_commit_describes_the_code"] else
            " (the working tree differed from that commit: see `code_dirty_paths` and "
            "`script_sha256` in the receipt)") + f". Run {meta['run_utc']}, as-of cap "
         f"{meta['asof_utc']}. Receipts: " + ", ".join(f"`{v}`" for v in files.values()) + ".",
         "No LLM spend, no network, inputs read only. These are observations; nothing here "
         "claims skill.", "", "## Headlines", ""]
    heads = []
    if r2 is not None:
        heads.append(("a", headline_a(r2)))
    if r1 is not None:
        heads += [("b", headline_b(r1)), ("c", headline_c(r1))]
    for key, text in heads:
        L.append(f"**({key})** {text}")
        if text != REVIEW_HEADLINES[key]:
            L.append("")
            L.append(f"  This differs from the sentence the 2026-11-15 review wrote, because the "
                     f"numbers in this run differ. The review's sentence: \"{REVIEW_HEADLINES[key]}\"")
        if key == "c":
            ex = unread_exclusions(r1)
            L.append("")
            L.append(f"  Cells where the interval excludes zero on fewer than "
                     f"{MIN_CLUSTERS_FOR_VERDICT} date blocks (printed, not read; the month "
                     f"clause above reads the 1-day horizon, where each day is a block): "
                     + ("; ".join(ex) if ex else "none") + ".")
        L.append("")
    if r2 is not None:
        a = r2["all"][0]
        z = r2["zero_edge_symmetric"]
        L += ["## Table 2: label rates on random books", "",
              f"{r2['n_books']:,} books in {a['n_windows']} windows (a window is one length and "
              f"start), {a['n_time_blocks']} start quarters, panel to {r2['panel_end']} "
              f"({r2['panel_symbols']:,} symbols, {r2['panel_symbols_stopped_trading_31d_before_end']:,} "
              "stopped trading). Intervals resample start quarters; an interval on fewer than "
              f"{MIN_CLUSTERS_FOR_VERDICT} quarters is not read.", "",
              "| window | books | windows | quarters | EARLY_EVIDENCE or higher, % [95%] | "
              "REPLICATED via twin, % [95%] | via twin or sibling (upper bound), % | "
              "EARLY in one window: min / p10 / median / p90 / max, % |",
              "|---:|---:|---:|---:|---|---|---:|---|"]
        for r in r2["by_L"] + [dict(a, L="all")]:
            w = r["early_or_higher_by_window"]
            L.append(
                f"| {r['L']} | {r['n_books']:,} | {r['n_windows']} | {r['n_time_blocks']} | "
                f"{100 * r['early_or_higher']:.1f} {_ci(r['early_or_higher_time_block_ci95'], False)} | "
                f"{100 * r['replicated_twin']:.1f} {_ci(r['replicated_twin_time_block_ci95'], False)} | "
                f"{100 * r['replicated_twin_or_sibling_upper_bound']:.1f} | "
                f"{100 * w['min']:.0f} / {100 * w['p10']:.0f} / {100 * w['median']:.0f} / "
                f"{100 * w['p90']:.0f} / {100 * w['max']:.0f} |")
        yrs = sorted(r2["by_year"], key=lambda r: r["early_or_higher"])
        L += ["",
              f"- The null is not zero-mean. {100 * a['share_positive_excess_vs_spy']:.1f}% of "
              f"these books had positive excess over SPY; the median excess was "
              f"{a['median_excess_pp']:+.2f} pp. A book with exactly zero edge (symmetric, "
              f"{z['n_books']:,} draws through the same label function) gets EARLY_EVIDENCE "
              f"{100 * z['early_or_higher']:.1f}% of the time.",
              f"- By start year the EARLY rate ran from {100 * yrs[0]['early_or_higher']:.0f}% "
              f"({yrs[0]['year']}) to {100 * yrs[-1]['early_or_higher']:.0f}% ({yrs[-1]['year']}). "
              "All live books share one window, so the fleet's rate in any one period is one "
              "draw from the window spread above, not the average.",
              "- " + SIBLING_ROUTE_NOTE,
              "- Entry cost: " + ENTRY_COST_CONVENTION,
              "- Delisted names are held at their last close (the panel has no delisting "
              "return), which raises random-book returns, most in the small band.", ""]
    if r1 is not None:
        c = r1["persona_made_census"]
        L += ["## Table 1: persona vs process", "",
              f"Persona forecasts: {c[PERSONA]['n_rows']:,} rows on {c[PERSONA]['n_made_days']} "
              f"made days ("
              + (", ".join(f"{n:,} on {d}" for d, n in c[PERSONA]["rows_by_day"].items())
                 if isinstance(c[PERSONA]["rows_by_day"], dict) else
                 f"{c[PERSONA]['first_day']} to {c[PERSONA]['last_day']}") + "), "
              f"{100 * (c[PERSONA]['share_in_busiest_utc_hour'] or 0):.1f}% of them in one UTC hour "
              f"({c[PERSONA]['busiest_utc_hour']}). Process forecasts: {c[PROCESS]['n_rows']:,} rows "
              f"on {c[PROCESS]['n_made_days']} made days, {c[PROCESS]['first_day']} to "
              f"{c[PROCESS]['last_day']}. Voided and ungraded rows are included in these counts. "
              "Every per-cell skill number and contrast is in the receipt.", "",
              "### The volatility formula beside the LLM process (magnitude rows only)", "",
              "`arm_rows` scores every arm's forecast as its own row; `arm_mean` averages the arms "
              "into one forecast per ticker-day, which is what the formula makes. Skill is the "
              "Brier skill score in %, differences in percentage points.", "",
              "| cell | h | unit | n | days | date blocks | LLM | formula | LLM minus formula "
              "[95%, date blocks] | no sigma | read |",
              "|---|---:|---|---:|---:|---:|---:|---:|---|---:|---|"]
        for r in r1["vol_prior"]:
            if not r.get("unit"):
                continue
            L.append(
                f"| {r.get('period') or r.get('made_month')} | {r['h']} | {r['unit']} | {r['n']:,} | "
                f"{r['n_days']} | {r['n_date_blocks']} | {_f1(r['bss_llm'])} | "
                f"{_f1(r['bss_vol_prior'])} | {_f1(r['llm_minus_vol'])} "
                f"{_ci(r['llm_minus_vol_ci_date_blocks'])} | {r['n_rows_without_sigma']} | "
                f"{r['verdict']} |")
        L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="report directory (never the live data folder)")
    ap.add_argument("--ledger", default=None, help="default <data-root>/predictions.jsonl")
    ap.add_argument("--data-root", default=str(_config.OPTIMUS_LEDGER_DIR))
    ap.add_argument("--book-dna", default=None)
    ap.add_argument("--table", choices=("1", "2", "both"), default="both")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--books-per-cell", type=int, default=BOOKS_PER_CELL)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--asof", default=None,
                    help="UTC cap, e.g. 2026-11-15T05:00:00Z: rows made after it are ignored "
                         "(default: the run start)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    root = Path(a.data_root)
    if out.resolve().is_relative_to(root.resolve()):
        print(f"REFUSED: --out {out} is inside the live data folder {root}")
        return RC_REFUSED_OUT
    now = datetime.now(timezone.utc)
    try:
        asof = pd.Timestamp(a.asof) if a.asof else pd.Timestamp(now)
        asof = asof.tz_localize("UTC") if asof.tzinfo is None else asof.tz_convert("UTC")
    except (ValueError, TypeError) as e:
        print(f"REFUSED: --asof {a.asof!r} is not a time ({e})")
        return RC_REFUSED_INPUT
    out.mkdir(parents=True, exist_ok=True)
    n_before = _count_files(root)
    deep = [root / "prices_deep" / "bars.parquet", root / "prices_deep" / "bars_delisted.parquet"]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    meta = run_meta(asof.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"))
    r1 = r2 = None
    files: dict[str, str] = {}
    try:
        sessions = sessions_from(deep + [root / "prices_2025_26" / "bars.parquet"], asof)
        print(f"calendar: {len(sessions)} SPY sessions {sessions[0]}..{sessions[-1]}", flush=True)
        if a.table in ("1", "both"):
            ledger = Path(a.ledger) if a.ledger else root / LIVE_LEDGER.name
            if not ledger.is_file():
                raise Refusal(f"no forecast ledger at {ledger}")
            from backend.services import forecast_ledger as _FL
            _be = _FL.backend_for(ledger)
            if _be.kind != "legacy":
                raise Refusal(f"{ledger} is answered by the monthly streams ({_be.reason}); this "
                              f"script hashes and reads the single legacy file and would read a frozen copy")
            r1 = run_table1(ledger, sessions, a.n_boot, a.seed,
                            bars_path=root / "prices_2025_26" / "bars.parquet", asof=asof)
            r1["meta"] = meta
            p1 = out / f"table1_{stamp}.json"
            p1.write_text(json.dumps(r1, indent=1, default=str), encoding="utf-8")
            files["table1"] = p1.name
            print(f"table 1 -> {p1} ({r1['seconds']}s, {r1['splits_looked_at']} splits)", flush=True)
        if a.table in ("2", "both"):
            bd = Path(a.book_dna) if a.book_dna else None
            if bd is None:
                c = sorted((root / "paper_accounts").glob("book_dna_*.json"))
                bd = c[-1] if c else None
            r2, sim = run_table2(deep, bd, a.seed, a.books_per_cell, n_boot=a.n_boot, asof=asof)
            r2["meta"] = meta
            p2 = out / f"table2_{stamp}.json"
            p2.write_text(json.dumps(r2, indent=1, default=str), encoding="utf-8")
            sim.to_csv(out / f"table2_books_{stamp}.csv", index=False)
            files["table2"] = p2.name
            print(f"table 2 -> {p2} ({r2['seconds']}s, {r2['n_books']} books)", flush=True)
    except Refusal as e:
        print(f"REFUSED: {e}", flush=True)
        print(f"live data folder file count before {n_before} after {_count_files(root)}",
              flush=True)
        return RC_REFUSED_INPUT
    md = out / f"PAPER_TABLES_{stamp}.md"
    md.write_text(render_markdown(r1, r2, meta, files), encoding="utf-8")
    print(f"markdown -> {md}", flush=True)
    n_after = _count_files(root)
    print(f"live data folder file count before {n_before} after {n_after}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
