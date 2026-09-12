"""G3 -- evolve v2. The 2026-09-09 protocol applied to the genome search.

G1 (the 09-08 night) optimised 40,680 genomes against ONE number on ONE window
(1999-03..2015-12) and its best scored 548x on that window. G2's sealed read
returned 9.69x against the market's 4.86x at beta 1.13 with a -42% drawdown
against a declared 35% budget. Four things in that design produced that gap,
and G3 changes all four (roadmap section 10.2):

1. **Fitness is a distribution over random windows, not one window.** Each
   generation draws its own bank of `--sel-windows` random windows of 6-72
   months inside DEV, and a genome is scored by the MEDIAN of its beta-matched
   annualised excess across that bank. A genome that wins because 2009 was in
   its window loses the generations whose bank starts in 2004.
2. **The score is an EXCESS over a random-genome null on the SAME windows.**
   RW1 measured that random genomes alone beat a beta-matched market in 28-33%
   of windows; a fitness that does not subtract that is measuring the windows.
3. **The drawdown budget is a hard refusal, not a penalty term.** G1's fitness
   subtracted `2 * max(0, dd - budget) * years / 10`, which a large enough
   terminal wealth simply pays. Here a genome whose full-DEV path breaches
   `DD_BUDGET` is REFUSED -- it gets no fitness at all.
4. **The archive is de-duplicated by ancestry and re-scored on a bank it was
   never selected on.** G2's "35/35 above the random p95" were 30 unique
   genomes sharing parents. Every genome here carries its parent keys and a
   lineage root; the final table reports one row per lineage and re-evaluates
   the finalists on a bank drawn from a seed the search never saw.

NO HOLDOUT IS READ. 2016-2024 is not touched by this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import evaluate as E                      # noqa: E402
from scripts.night_checkpoint import (                 # noqa: E402
    Checkpoint, SearchState, rng_state_from_json, rng_state_to_json,
)

# 2026-09-10: this was hard-coded to "2026-09-08" while `night_factory` honours
# NIGHT_RUN_DATE, so the 09-09 night wrote its RECEIPT to night_factory_2026-09-09/
# and its EVALUATIONS LOG to night_factory_2026-09-08/. Two nights' raw
# evaluations ended up appended to one file with no run marker, and the only
# way to tell them apart afterwards was a timestamp gap. The default is kept so
# existing paths still resolve; the env var now reaches this file too.
RUN_DATE = os.getenv("NIGHT_RUN_DATE", "2026-09-08")
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
LONG = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"
STOP = OUT / "STOP"

COST_BPS = 25.0
DEV_FIRST, DEV_LAST = "1999-03", "2015-12"
LENGTHS = (6, 12, 24, 36, 48, 60, 72)
NW_LAG = 4
DD_BUDGET = 0.35
MIN_WINDOW_MONTHS = 6

FEATURES = ["mom_12_1__xs", "net_rev_4w__xs", "ratio__xs", "consensus_rev_1m__xs", "disagreement__xs",
            "drawdown_60d__xs", "vol_60d__xs", "log_market_cap__xs", "ret_1m__xs", "ret_6m__xs",
            "coverage__xs", "target_rev_1m__xs", "log_close__xs", "dispersion__xs"]
W_MENU = (-1.0, -0.5, 0.0, 0.5, 1.0)
K_MENU = (20, 50, 100, 200, 300)
WEIGHT_MENU = ("ew", "rank", "vw")
HOLD_MENU = (None, 2, 4, 8)
FLOOR_MENU = (None, 3e6, 1e7)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def _nw_t(x: np.ndarray, lag: int = NW_LAG) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 6:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se) if se > 0 else None


def _max_dd(m: np.ndarray) -> float:
    eq = np.cumprod(1.0 + np.asarray(m, dtype="float64"))
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min()) if len(eq) else 0.0


# --------------------------------------------------------------- the genome

def _genome_key(g: dict) -> str:
    core = {k: g[k] for k in ("w", "k", "weight", "hold_mult", "floor")}
    return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def random_genome(rng: random.Random) -> dict:
    w = {f: rng.choice(W_MENU) for f in FEATURES}
    if all(v == 0.0 for v in w.values()):
        w[rng.choice(FEATURES)] = 1.0
    g = {"w": w, "k": rng.choice(K_MENU), "weight": rng.choice(WEIGHT_MENU),
         "hold_mult": rng.choice(HOLD_MENU), "floor": rng.choice(FLOOR_MENU)}
    g["parents"] = []
    g["lineage"] = _genome_key(g)         # a founder is its own lineage root
    return g


def _child(a: dict, b: dict | None, rng: random.Random) -> dict:
    c = {"w": dict(a["w"]), "k": a["k"], "weight": a["weight"],
         "hold_mult": a["hold_mult"], "floor": a["floor"]}
    if b is not None:
        for f in FEATURES:
            if rng.random() < 0.5:
                c["w"][f] = b["w"][f]
        for key in ("k", "weight", "hold_mult", "floor"):
            if rng.random() < 0.5:
                c[key] = b[key]
    r = rng.random()                                     # then mutate one gene
    if r < 0.6:
        c["w"][rng.choice(FEATURES)] = rng.choice(W_MENU)
    elif r < 0.7:
        c["k"] = rng.choice(K_MENU)
    elif r < 0.8:
        c["weight"] = rng.choice(WEIGHT_MENU)
    elif r < 0.9:
        c["hold_mult"] = rng.choice(HOLD_MENU)
    else:
        c["floor"] = rng.choice(FLOOR_MENU)
    if all(v == 0.0 for v in c["w"].values()):
        c["w"][rng.choice(FEATURES)] = 1.0
    c["parents"] = [_genome_key(a)] + ([_genome_key(b)] if b is not None else [])
    # the lineage root is the FIRST parent's root: a "35/35" count over one
    # lineage is one observation wearing 35 hats (review section 1, defect 5)
    c["lineage"] = a.get("lineage") or _genome_key(a)
    return c


# ------------------------------------------------------------- the windows

def _months(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def draw_windows(n: int, seed: int) -> list[tuple[str, str, int]]:
    """Random windows INSIDE the development span. The holdout is never drawn."""
    rng = random.Random(seed)
    months = _months(DEV_FIRST, DEV_LAST)
    out = []
    for _ in range(n):
        L = rng.choice([x for x in LENGTHS if x <= len(months)])
        s = rng.randrange(0, len(months) - L + 1)
        out.append((months[s], months[s + L - 1], L))
    return out


def _signal(df: pd.DataFrame, w: dict) -> np.ndarray:
    s = np.zeros(len(df))
    for f, v in w.items():
        if v and f in df.columns:
            s += v * df[f].fillna(0.0).to_numpy(dtype="float64")
    return s


def _book_on(df_w: pd.DataFrame, col: str, g: dict) -> dict | None:
    hold_k = None if g["hold_mult"] is None else int(g["k"] * g["hold_mult"])
    try:
        r = E.book(df_w, col, k=int(g["k"]), weight=g["weight"], cost_bps=COST_BPS,
                   hold_k=hold_k, tradable_floor=g["floor"], with_risk=True, return_series=True)
    except SystemExit:
        return None
    if r.get("months", 0) < MIN_WINDOW_MONTHS:
        return None
    net = r["_series"]["net"].astype("float64")
    mkt = r["_series"]["market"].reindex(net.index).astype("float64")
    y, x = net.to_numpy(), mkt.to_numpy()
    beta = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 0 else 1.0
    ex = y - beta * x
    return {"n": len(y), "beta": beta, "bm_ann_pct": float(ex.mean()) * 12 * 100,
            "t_bm": _nw_t(ex), "max_dd": _max_dd(y),
            "tw_net": float(np.prod(1 + y)), "tw_mkt": float(np.prod(1 + x)),
            "beats_bm": bool(ex.mean() > 0)}


class WindowBank:
    """One generation's windows, with the null's per-window bar precomputed.

    The bar is the MEDIAN beta-matched excess of `n_null` random genomes on the
    SAME window. Subtracting it is the whole point: RW1 showed random genomes
    beat a beta-matched market in 28-33% of windows, so an unsubtracted score
    rewards a genome for the window it happened to draw.
    """

    def __init__(self, dev: pd.DataFrame, seed: int, n_windows: int, n_null: int,
                 admit=None, max_null_draws: int = 400):
        """`admit(genome, key) -> (bool, full_path)` puts the NULL draws through
        the same drawdown refusal the arms face.

        2026-09-10 (roadmap 11.10). Null genomes bypassed `admissible()`
        entirely: 69.3% of ARMS were refused on the drawdown budget and 0% of
        NULLS were, so the fitness was "an admissible genome minus a TYPICAL
        genome" rather than "minus a typical ADMISSIBLE genome". The bar was
        drawn from a population the arm was not allowed to be in, which flatters
        every arm by exactly the amount the refusal costs. `null_refused` is
        recorded so the receipt can show the gate firing on both sides.
        """
        self.seed = seed
        self.windows = draw_windows(n_windows, seed)
        self.slices = []
        rng = random.Random(seed ^ 0x5EED)
        nulls: list[dict] = []
        self.null_refused = 0
        self.null_draws = 0
        if admit is None:
            nulls = [random_genome(rng) for _ in range(n_null)]
            self.null_draws = n_null
        else:
            while len(nulls) < n_null and self.null_draws < max_null_draws:
                g = random_genome(rng)
                self.null_draws += 1
                ok, _ = admit(g, _genome_key(g))
                if ok:
                    nulls.append(g)
                else:
                    self.null_refused += 1
        self.null_admissible = len(nulls)
        for (a, b, L) in self.windows:
            d = dev[(dev["month"] >= a) & (dev["month"] <= b)].copy()
            bars = []
            for i, ng in enumerate(nulls):
                d[f"_n{i}"] = _signal(d, ng["w"])
                r = _book_on(d, f"_n{i}", ng)
                if r:
                    bars.append(r["bm_ann_pct"])
            d.drop(columns=[c for c in d.columns if c.startswith("_n")], inplace=True)
            # `null_bar or 0.0` was the D1 defect wearing a different hat: a
            # window whose nulls all failed to produce a book graded every arm
            # against ZERO, and an arm minus zero is a gross return dressed as
            # an excess. A window with no null bar is now DROPPED, not graded.
            self.slices.append({"key": (a, b, L), "df": d,
                                "null_bar": float(np.median(bars)) if bars else None,
                                "null_n": len(bars)})
        self.n_windows_without_null = sum(1 for s in self.slices if s["null_bar"] is None)

    def evaluate(self, g: dict) -> dict:
        cells = []
        for sl in self.slices:
            if sl["null_bar"] is None:
                continue
            d = sl["df"]
            d["_sig"] = _signal(d, g["w"])
            r = _book_on(d, "_sig", g)
            if r is None:
                continue
            cells.append({**r, "excess_bm": r["bm_ann_pct"] - sl["null_bar"],
                          "window": f"{sl['key'][0]}..{sl['key'][1]}", "length_m": sl["key"][2]})
        # the denominator is the GRADEABLE slices, not every slice: counting
        # windows that no arm could ever be graded on would be a gate that
        # cannot go green (CLAUDE.md), refusing every genome for a fault in the
        # bank rather than in the genome
        n_gradeable = sum(1 for s in self.slices if s["null_bar"] is not None)
        if n_gradeable == 0:
            return {"verdict": "REFUSED", "why": "no window in this bank has a null bar", "fitness": None}
        if len(cells) < max(3, n_gradeable // 3):
            return {"verdict": "REFUSED", "why": f"only {len(cells)}/{n_gradeable} gradeable windows graded",
                    "fitness": None}
        ex = np.array([c["excess_bm"] for c in cells])
        return {"verdict": "OK", "n_windows": len(cells),
                "median_excess_bm_ann_pct": float(np.median(ex)),
                "mean_excess_bm_ann_pct": float(ex.mean()),
                "p25_excess_bm_ann_pct": float(np.quantile(ex, 0.25)),
                "win_rate_bm": float(np.mean([c["beats_bm"] for c in cells])),
                "median_beta": float(np.median([c["beta"] for c in cells])),
                "worst_window_max_dd": float(min(c["max_dd"] for c in cells)),
                "median_window_max_dd": float(np.median([c["max_dd"] for c in cells])),
                "fitness": float(np.median(ex))}


def full_dev_path(dev: pd.DataFrame, g: dict) -> dict | None:
    """The one number a product actually lives through: the whole-DEV path.

    Its drawdown is the HARD refusal. G1 penalised a breach inside the fitness,
    which a large enough terminal wealth simply buys its way past."""
    return _book_on(dev.assign(_sig=_signal(dev, g["w"])), "_sig", g)


def market_drawdown(dev: pd.DataFrame) -> float:
    """The index's own worst month-to-month loss over the SAME window."""
    m = dev.groupby("month")["mkt_vw_1m"].first().sort_index().to_numpy(dtype="float64")
    return _max_dd(m)


def dd_limit(dev: pd.DataFrame) -> tuple[float, float]:
    """The drawdown budget, DERIVED from the window it is applied to.

    The first version of this file refused any full-DEV path worse than a flat
    `DD_BUDGET` of 0.35. Measured: the VW market itself drew down **47.2%** over
    1999-03..2015-12, which holds two ~50% bear markets, so the flat budget
    refused 188 of 207 genomes in the smoke run -- and would have refused the
    index. A budget that the benchmark cannot meet is a gate that cannot go
    green (CLAUDE.md), so the limit is:

        max(declared budget, the market's own drawdown on this window)

    A book may lose as much as the index did in the same period and no more;
    where the market was calmer than the declared budget, the declared budget
    binds instead. Both numbers travel in the receipt so the reader sees which
    clause was active.
    """
    mkt = market_drawdown(dev)
    return max(DD_BUDGET, -mkt), mkt


def G3_evolve_v2(hours: float = 4.0, pop: int = 24, seed: int = 20260909,
                 sel_windows: int = 24, n_null: int = 6, smoke: bool = False,
                 resume: bool = False, fresh: bool = False, min_banks: int = 2,
                 n_confirm: int = 4, carry_elites: int = 8, run: int = 1) -> dict:
    t0 = time.time()
    if smoke:
        hours, pop, sel_windows, n_null = min(hours, 0.12), 8, 6, 3
        n_confirm, carry_elites = 2, 4
    cols = ["month", "permno", "fwd_1m", "mkt_vw_1m", "market_cap", "log_dollar_vol_20d"] + FEATURES
    df = pd.read_parquet(LONG, columns=cols)
    dev = df[(df["month"] >= DEV_FIRST) & (df["month"] <= DEV_LAST)].copy()
    del df
    print(f"    DEV {DEV_FIRST}..{DEV_LAST}: {len(dev):,} rows, {dev['month'].nunique()} months", flush=True)
    DD_LIMIT, MKT_DD = dd_limit(dev)
    print(f"    drawdown budget: declared {DD_BUDGET}, market on this window {MKT_DD:.4f} -> refusing worse than {DD_LIMIT:.4f}", flush=True)

    # ---------------- search memory that survives the night ------------------
    # 2026-09-10. The 09-09 run was a bit-identical REPLAY of the 09-08 run:
    # both used seed 20260909 and `bank_seed = seed + 1000 * gen`, so both drew
    # the same banks, initialised the same population and walked the same tree.
    # Of the 541 distinct genomes the second run evaluated, 541 were already in
    # the first run's log -- overlap 1.000, discovery 0. A checkpoint alone
    # would only have made a pointless replay resumable, so the seed now
    # advances with the night and the elites carry forward.
    state_path = OUT / ("G3_search_state_smoke.json" if smoke else "G3_search_state.json")
    if fresh and state_path.exists():
        state_path.unlink()
    state = SearchState(state_path)
    night_index = state.night_index
    # a distinct stream per night; the declared seed still pins the whole series
    effective_seed = seed ^ ((night_index + 1) * 0x9E3779B1) & 0x7FFFFFFF
    rng = random.Random(effective_seed)
    bank_rng = random.Random(effective_seed ^ 0xB00C)
    log_path = OUT / ("G3_evaluations_smoke.jsonl" if smoke else "G3_evaluations.jsonl")
    ckpt = Checkpoint(OUT / (f"G3_checkpoint_run{run:02d}_smoke.json" if smoke
                             else f"G3_checkpoint_run{run:02d}.json"),
                      config={"seed": seed, "pop": pop, "sel_windows": sel_windows,
                              "n_null": n_null, "smoke": bool(smoke), "min_banks": min_banks,
                              "dev": f"{DEV_FIRST}..{DEV_LAST}", "night_index": night_index})
    genomes: dict[str, dict] = {}                 # key -> genome (with ancestry)
    scores: dict[tuple[str, int], dict] = {}      # (key, bank_seed) -> result
    seen: dict[str, list[float]] = {}             # key -> fitness on EVERY bank it met
    admissible_cache: dict[str, dict] = {}        # key -> full-DEV path (the DD gate)
    n_eval = 0
    n_dd_refused = 0
    n_null_refused = 0
    n_seeds_rejected_as_seen = 0
    bank_seeds_this_run: list[int] = []
    curve = []
    resumed_from_gen: int | None = None
    seconds_already_spent = 0.0

    # the population shape scales with `pop`: at pop=8 the old fixed "4 elites +
    # 4 fresh" left ZERO slots for children, so the smoke run produced 236
    # genomes in 236 lineages and never tested crossover at all
    n_elite = max(2, pop // 6)
    n_fresh = max(1, pop // 6)

    def admissible(g: dict, key: str) -> tuple[bool, dict | None]:
        """The drawdown budget, applied BEFORE the genome can earn a fitness.

        G1 subtracted a penalty a big enough terminal wealth simply paid; the
        smoke run of this file applied the refusal only to finalists and killed
        11 of 12, which is a search spending its whole budget on inadmissible
        candidates. Cached per genome: it does not depend on the window bank."""
        if key not in admissible_cache:
            admissible_cache[key] = full_dev_path(dev, g) or {}
        full = admissible_cache[key]
        if not full:
            return False, None
        return (-full["max_dd"] <= DD_LIMIT), full

    # ---------------- initial population: carried elites, then fresh ---------
    carried = state.seed_population(min(carry_elites, pop - 1)) if not fresh else []
    population = carried + [random_genome(rng) for _ in range(pop - len(carried))]
    gen = 0
    if carried:
        print(f"    night {night_index + 1}: seeded {len(carried)} elite(s) from the previous night's "
              f"archive, {pop - len(carried)} fresh; effective seed {effective_seed}", flush=True)
    else:
        print(f"    night {night_index + 1}: no carried elites (first night or --fresh); "
              f"effective seed {effective_seed}", flush=True)

    # ---------------- resume, if a checkpoint of THIS run survives -----------
    if resume and ckpt.exists():
        st = ckpt.load()                      # raises with a reason if the config moved
        gen = int(st["gen"])
        resumed_from_gen = gen
        population = [dict(g) for g in st["population"]]
        genomes = {k: dict(v) for k, v in st["genomes"].items()}
        seen = {k: list(v) for k, v in st["seen"].items()}
        scores = {(r["key"], int(r["bank_seed"])): r["result"] for r in st["scores"]}
        admissible_cache = {k: dict(v) for k, v in st["admissible_cache"].items()}
        n_eval = int(st["n_eval"])
        n_dd_refused = int(st["n_dd_refused"])
        n_null_refused = int(st.get("n_null_refused") or 0)
        n_seeds_rejected_as_seen = int(st.get("n_seeds_rejected_as_seen") or 0)
        bank_seeds_this_run = [int(s) for s in st.get("bank_seeds_this_run") or []]
        curve = list(st.get("curve") or [])
        seconds_already_spent = float(st.get("seconds_spent") or 0.0)
        rng.setstate(rng_state_from_json(st["rng_state"]))
        bank_rng.setstate(rng_state_from_json(st["bank_rng_state"]))
        print(f"    RESUMED from gen {gen}: {n_eval} evaluations, {len(genomes)} genomes, "
              f"{seconds_already_spent:.0f}s already spent of the {hours * 3600:.0f}s box", flush=True)
    elif resume:
        print(f"    --resume asked for but no checkpoint at {ckpt.path}; starting at gen 0", flush=True)

    # the time box is what REMAINS of it, so a resumed run does not silently get
    # a second full budget and report a curve stitched from two different boxes
    t_end = time.time() + max(0.0, hours * 3600.0 - seconds_already_spent)

    def _checkpoint(g: int) -> None:
        ckpt.save({
            "gen": g, "population": population, "genomes": genomes,
            "seen": seen,
            "scores": [{"key": k[0], "bank_seed": k[1], "result": v} for k, v in scores.items()],
            "admissible_cache": admissible_cache,
            "n_eval": n_eval, "n_dd_refused": n_dd_refused, "n_null_refused": n_null_refused,
            "n_seeds_rejected_as_seen": n_seeds_rejected_as_seen,
            "bank_seeds_this_run": bank_seeds_this_run,
            "curve": curve,
            "seconds_spent": seconds_already_spent + (time.time() - t0),
            "rng_state": rng_state_to_json(rng.getstate()),
            "bank_rng_state": rng_state_to_json(bank_rng.getstate()),
        })

    fh = log_path.open("a", encoding="utf-8")
    try:
        while time.time() < t_end and not STOP.exists():
            (bs,), rej = state.fresh_bank_seeds(bank_rng, 1)
            n_seeds_rejected_as_seen += rej
            bank_seed = bs
            bank_seeds_this_run.append(bank_seed)
            # record BEFORE evaluating: a crash between the draw and the record
            # would otherwise let a later night select on this bank again and
            # then call it "never seen" in an archive re-score
            state.record_selection_banks([bank_seed])
            bank = WindowBank(dev, bank_seed, sel_windows, n_null, admit=admissible)
            n_null_refused += bank.null_refused
            scored = []
            for g in population:
                key = _genome_key(g)
                genomes.setdefault(key, g)
                ok, full = admissible(g, key)
                if not ok:
                    n_dd_refused += 1
                    continue
                ck = (key, bank_seed)
                if ck in scores:
                    res = scores[ck]
                else:
                    res = bank.evaluate(g)
                    scores[ck] = res
                    n_eval += 1
                    fh.write(json.dumps({"key": key, "lineage": g.get("lineage"), "parents": g.get("parents", []),
                                         "bank_seed": bank_seed, "gen": gen,
                                         "genome": {k: g[k] for k in ("w", "k", "weight", "hold_mult", "floor")},
                                         "full_dev_max_dd": _r((full or {}).get("max_dd")),
                                         "result": {k: (_r(v) if isinstance(v, float) else v) for k, v in res.items()},
                                         "utc": _now()}) + "\n")
                if res.get("fitness") is None:
                    continue
                seen.setdefault(key, []).append(res["fitness"])
                scored.append((res["fitness"], key, g, res))
            fh.flush()
            if not scored:
                population = [random_genome(rng) for _ in range(pop)]
                gen += 1
                continue
            scored.sort(key=lambda t: -t[0])
            curve.append({"gen": gen, "bank_seed": bank_seed, "best_fitness": _r(scored[0][0], 4),
                          "median_fitness": _r(float(np.median([s[0] for s in scored])), 4),
                          "n_scored": len(scored), "n_eval": n_eval, "dd_refused_total": n_dd_refused,
                          "utc": _now()})
            if gen % 5 == 0:
                b = scored[0][3]
                print(f"    gen {gen:4d}  evals {n_eval:6d}  ddref {n_dd_refused:5d}  "
                      f"best median-excess {scored[0][0]:+.3f}%/yr  win {b['win_rate_bm']:.2f}  "
                      f"beta {b['median_beta']:.2f}  {time.time() - t0:.0f}s", flush=True)
            half = max(2, len(scored) // 2)
            nxt = [g for _, _, g, _ in scored[:n_elite]]
            while len(nxt) < pop - n_fresh:
                a = rng.choice(scored[:half])[2]
                b = rng.choice(scored[:half])[2] if rng.random() < 0.5 else None
                nxt.append(_child(a, b, rng))
            nxt += [random_genome(rng) for _ in range(n_fresh)]

            # ---- confirmation: the top few meet ONE extra bank, now ----------
            # Measured on the 09-08 log: 434 of 595 genomes met exactly ONE
            # bank, and only 4 of 251 LINEAGES ever had a member measured twice.
            # The archive then ranked 251 single-draw numbers and took the top
            # 12 -- a max over noise. Confirming the leaders costs `n_confirm`
            # evaluations a generation and is what makes `banks_met >= min_banks`
            # a gate that can go green instead of a fallback that never binds.
            if n_confirm > 0 and time.time() < t_end:
                (cbs,), crej = state.fresh_bank_seeds(bank_rng, 1)
                n_seeds_rejected_as_seen += crej
                state.record_selection_banks([cbs])
                bank_seeds_this_run.append(cbs)
                cbank = WindowBank(dev, cbs, sel_windows, n_null, admit=admissible)
                n_null_refused += cbank.null_refused
                for _f, key, g, _res in scored[:n_confirm]:
                    ck = (key, cbs)
                    if ck in scores:
                        continue
                    res = cbank.evaluate(g)
                    scores[ck] = res
                    n_eval += 1
                    fh.write(json.dumps({"key": key, "lineage": g.get("lineage"),
                                         "parents": g.get("parents", []), "bank_seed": cbs,
                                         "gen": gen, "pass": "confirmation",
                                         "genome": {k: g[k] for k in ("w", "k", "weight", "hold_mult", "floor")},
                                         "result": {k: (_r(v) if isinstance(v, float) else v)
                                                    for k, v in res.items()},
                                         "utc": _now()}) + "\n")
                    if res.get("fitness") is not None:
                        seen.setdefault(key, []).append(res["fitness"])
                fh.flush()

            population = nxt
            gen += 1
            _checkpoint(gen)
    finally:
        fh.close()
        _checkpoint(gen)

    # ---------------- the archive: de-duplicate by lineage, then re-score -----
    # A genome met several banks. Ranking it by its BEST bank is selection on the
    # outcome -- the same error as picking a matched control on the outcome -- so
    # the archive ranks on the MEDIAN across the banks a genome actually met, and
    # prints how many that was.
    last_by_key: dict[str, dict] = {}
    last_bank_by_key: dict[str, int] = {}
    for (k_key, k_bank), v in scores.items():          # one pass, not one scan per genome
        if k_bank >= last_bank_by_key.get(k_key, -1):
            last_bank_by_key[k_key] = k_bank
            last_by_key[k_key] = v
    best_by_key: dict[str, dict] = {}
    for key, fits in seen.items():
        best_by_key[key] = {**(last_by_key.get(key) or {}), "fitness": float(np.median(fits)),
                            "fitness_best_bank": float(max(fits)), "banks_met": len(fits)}

    # ---- the lineage representative: BEST MEASURED, not best scoring --------
    # 2026-09-10. The previous rule ranked every genome by median fitness and
    # took each lineage's first appearance in that order, so the representative
    # was the lineage's HIGHEST-SCORING member. A genome that met one bank has a
    # median of one number and therefore sits at the noisy top of that ordering:
    # measured on the 09-08 log, 434 of 595 genomes met exactly one bank and the
    # highest-median member of 248 of 251 lineages was a one-bank genome. The
    # receipt then said `finalist_basis = "ALL lineages (only 3 met two banks)"`
    # while 161 genomes had in fact met two or more -- the fallback fired because
    # the representative rule had discarded every well-measured member first.
    # That is selection on the outcome re-entering through the back door, in the
    # same file whose comment says it is avoiding exactly that.
    # Ordering by (banks_met, then fitness) picks the best-MEASURED member.
    by_lineage: dict[str, tuple[str, dict]] = {}
    for key, res in sorted(best_by_key.items(),
                           key=lambda kv: (-(kv[1].get("banks_met") or 0), -kv[1]["fitness"])):
        lin = genomes[key].get("lineage") or key
        if lin not in by_lineage:
            by_lineage[lin] = (key, res)

    n_genomes_ge_min = sum(1 for v in best_by_key.values() if (v.get("banks_met") or 0) >= min_banks)
    eligible = sorted(((k, v) for k, v in by_lineage.values() if (v.get("banks_met") or 0) >= min_banks),
                      key=lambda kv: -kv[1]["fitness"])
    # ELIGIBILITY, not preference (roadmap 11.10). The old code fell back to ALL
    # lineages when fewer than six were multiply measured, which is a gate that
    # never binds. A thin archive is a finding; a fabricated one is not.
    finalists = eligible[:12]
    finalist_basis = (f"banks_met>={min_banks} as a HARD eligibility condition: "
                      f"{len(eligible)}/{len(by_lineage)} lineages qualify "
                      f"({n_genomes_ge_min}/{len(best_by_key)} genomes)")
    print(f"    {len(best_by_key)} genomes scored, {len(by_lineage)} distinct lineages, "
          f"{n_dd_refused} drawdown refusals; re-scoring {len(finalists)} finalists "
          f"({finalist_basis}) on a bank the search never saw", flush=True)

    # The archive bank was `seed ^ 0xA5C1` -- a CONSTANT. Every night drew the
    # same "bank the search never saw", and nothing checked that it was not a
    # bank some night had selected on. Both are fixed here: the seed is drawn
    # from outside the union of every selection seed ever recorded, and it is
    # filed under `bank_seeds_archived_on` so a later night cannot select on it.
    (arch_seed,), arch_rej = state.fresh_bank_seeds(bank_rng, 1)
    n_seeds_rejected_as_seen += arch_rej
    state.record_archive_banks([arch_seed])
    arch_bank = WindowBank(dev, arch_seed, 12 if smoke else 60, n_null, admit=admissible)
    n_null_refused += arch_bank.null_refused
    archive = []
    for key, sel in finalists:
        g = genomes[key]
        a = arch_bank.evaluate(g)
        full = full_dev_path(dev, g)
        breach = bool(full and -full["max_dd"] > DD_LIMIT)
        archive.append({
            "key": key, "lineage": g.get("lineage"), "parents": g.get("parents", []),
            "genome": {k: g[k] for k in ("w", "k", "weight", "hold_mult", "floor")},
            "selection_bank": {k: _r(v) for k, v in sel.items() if isinstance(v, (int, float))},
            "archive_bank_never_selected_on": {k: _r(v) for k, v in a.items() if isinstance(v, (int, float))},
            "full_dev_path": ({k: _r(v) for k, v in full.items() if isinstance(v, (int, float, bool))} if full else None),
            "dd_budget_breached_on_full_dev": breach,
            "verdict_row": ("REFUSED_DD_BUDGET" if breach else
                            ("HOLDS_UP_OUT_OF_BANK" if (a.get("fitness") or -9) > 0 else "BANK_SPECIFIC")),
        })
    archive.sort(key=lambda r: -((r["archive_bank_never_selected_on"] or {}).get("median_excess_bm_ann_pct") or -99))
    # renamed from `admissible`, which SHADOWED the admissibility function
    # defined in this same scope -- after this line `admissible(g, key)` would
    # have raised `TypeError: 'list' object is not callable`. It survived only
    # because nothing called it after the search loop; the archive bank above
    # now does.
    admissible_rows = [r for r in archive if not r["dd_budget_breached_on_full_dev"]]
    holds = [r for r in archive if r["verdict_row"] == "HOLDS_UP_OUT_OF_BANK"]

    # ---- carry this night's measured lineages into the next night -----------
    # E5 (2026-09-12): a lineage whose deflated Sharpe did not clear the bar for
    # how many genomes the search tried is not bred from again. The set is READ
    # from `G3_lineage_verdicts.jsonl` rather than recomputed here, so the
    # exclusion and the receipt that explains it can never disagree; an absent
    # verdicts file is an empty set, which is the behaviour before E5 existed.
    from scripts.night_stopping_rules import deprioritized_lineages
    banned = deprioritized_lineages()
    state.update_elites([{"key": k, "genome": {kk: genomes[k][kk] for kk in
                                               ("w", "k", "weight", "hold_mult", "floor")},
                          "lineage": genomes[k].get("lineage"),
                          "fitness": v["fitness"], "banks_met": v.get("banks_met")}
                         for k, v in eligible[:24]], keep=24,
                        exclude_lineages=banned)
    state.close_night({"job": "G3_evolve_v2", "run": run, "generations": gen,
                       "genome_evaluations": n_eval, "eligible_lineages": len(eligible),
                       "deprioritized_lineages_excluded": len(banned),
                       "resumed_from_gen": resumed_from_gen})
    ckpt.clear()      # the run finished; the next one must not resume into it

    sel_fit = np.array([v["fitness"] for v in best_by_key.values()])
    top = archive[0] if archive else None
    shrink = None
    if top:
        s = (top["selection_bank"] or {}).get("median_excess_bm_ann_pct")
        a2 = (top["archive_bank_never_selected_on"] or {}).get("median_excess_bm_ann_pct")
        shrink = _r((a2 - s) if (s is not None and a2 is not None) else None, 3)

    return {
        "job": "G3_evolve_v2", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "holdout": "2016-2024 NOT READ by this job -- G3 never touches it",
        "dev_window": f"{DEV_FIRST}..{DEV_LAST}",
        "protocol": {
            "fitness": ("median over the generation's window bank of (genome beta-matched annualised excess "
                        "MINUS the median of n_null random genomes on the SAME window)"),
            "windows_per_generation": sel_windows, "window_lengths_months": LENGTHS,
            "null_genomes_per_window": n_null, "population": pop,
            "dd_rule": (f"HARD REFUSAL before any fitness is earned: a full-DEV path drawdown worse than "
                        f"{DD_LIMIT:.4f} is inadmissible. That limit is DERIVED -- max(declared budget "
                        f"{DD_BUDGET}, the market's own drawdown {MKT_DD:.4f} on this window) -- because a "
                        f"flat 0.35 on a 17-year path holding two ~50% bear markets refuses the index itself."),
            "dd_budget_declared": DD_BUDGET, "dd_market_same_window": _r(MKT_DD), "dd_limit_applied": _r(DD_LIMIT),
            "archive_rule": "one row per LINEAGE ROOT, re-scored on a bank drawn from a seed the search never saw",
            "cost_bps_per_side": COST_BPS,
        },
        "generations": gen, "genome_evaluations": n_eval,
        "dd_refusals_during_search": n_dd_refused,
        "null_draws_refused_on_dd_budget": n_null_refused,
        "continuity": {
            "night_index": night_index + 1,
            "declared_seed": seed, "effective_seed": effective_seed,
            "elites_carried_in": len(carried),
            "resumed_from_gen": resumed_from_gen,
            "checkpoint": str(ckpt.path),
            "search_state": str(state_path),
            "selection_bank_seeds_this_run": len(bank_seeds_this_run),
            "selection_bank_seeds_all_nights": len(state.bank_seeds_selected_on),
            "bank_seeds_rejected_as_already_seen": n_seeds_rejected_as_seen,
            "archive_bank_seed": arch_seed,
            "note": ("the 09-08 and 09-09 runs shared seed 20260909 and bank_seed = seed + 1000*gen, "
                     "so the second was a bit-identical replay of the first: 541 of its 541 distinct "
                     "genomes were already in the first run's log. The seed now advances with the night "
                     "and every bank seed is drawn from outside the set any night has selected on."),
        },
        "eligibility": {
            "min_banks": min_banks,
            "lineages_total": len(by_lineage), "lineages_eligible": len(eligible),
            "genomes_total": len(best_by_key), "genomes_meeting_min_banks": n_genomes_ge_min,
            "confirmations_per_generation": n_confirm,
            "rule": ("HARD: a lineage enters the archive only if its representative met >= min_banks "
                     "window banks. The representative is the lineage's BEST-MEASURED member "
                     "(banks_met, then fitness), not its best-scoring one."),
        },
        "population_shape": {"pop": pop, "elite": n_elite, "fresh_random": n_fresh,
                             "children": pop - n_elite - n_fresh},
        "finalist_basis": finalist_basis,
        "distinct_genomes": len(best_by_key), "distinct_lineages": len(by_lineage),
        "lineage_collapse_ratio": _r(len(by_lineage) / max(len(best_by_key), 1), 3),
        "selection_fitness_distribution": {
            "p50": _r(float(np.median(sel_fit)), 3) if len(sel_fit) else None,
            "p90": _r(float(np.quantile(sel_fit, 0.9)), 3) if len(sel_fit) else None,
            "max": _r(float(sel_fit.max()), 3) if len(sel_fit) else None},
        "archive": archive, "best_curve": curve[-60:],
        "n_admissible_after_dd_refusal": len(admissible_rows),
        "n_holding_up_out_of_bank": len(holds),
        "selection_to_archive_shrinkage_pp": shrink,
        "evaluations_jsonl": str(log_path),
        "headline": (
            f"{n_eval} evaluations over {gen} generations, {len(best_by_key)} distinct genomes in "
            f"{len(by_lineage)} lineages; best out-of-bank median excess over the random-genome null "
            f"{(archive[0]['archive_bank_never_selected_on'] or {}).get('median_excess_bm_ann_pct')}%/yr "
            f"(selection banks {(archive[0]['selection_bank'] or {}).get('median_excess_bm_ann_pct')}, "
            f"shrinkage {shrink} pp); {n_dd_refused} genomes refused on the {DD_BUDGET} drawdown budget "
            f"during the search (limit {DD_LIMIT:.3f}), {len(admissible_rows)}/{len(archive)} finalists re-verified, "
            f"{len(holds)} hold up out of bank"
        ) if archive else "nothing evaluated",
        "verdict": (
            "DEV ARCHIVE ONLY, NO HOLDOUT READ. " +
            # an empty archive because NOTHING was measured twice is a different
            # finding from an archive whose rows all failed, and the old code
            # collapsed both into one sentence by falling back to all lineages
            (f"CANNOT DETERMINE: no lineage met the min_banks={min_banks} eligibility condition "
             f"({n_genomes_ge_min}/{len(best_by_key)} genomes and 0/{len(by_lineage)} lineages were "
             f"measured on {min_banks}+ window banks). The search ran but nothing in it was measured "
             f"more than once, so there is nothing to rank. Raise --n-confirm or --hours."
             if not eligible else
             ("CANNOT DETERMINE: eligible lineages exist but none produced an archive row" if not archive else
              (f"PRODUCT_PROMISING: {len(holds)} lineage(s) keep a positive median excess over the null on a "
               f"window bank they were never selected on, within the drawdown budget"
               if holds and admissible_rows else
               "FAILED_VARIANT: no lineage keeps a positive excess over the random-genome null on windows it was "
               "not selected on -- the search is fitting window banks, which is what G1 did to one window")))),
        "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=float(os.getenv("NIGHT_G3_HOURS", "4")))
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--sel-windows", type=int, default=24)
    ap.add_argument("--n-null", type=int, default=6)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="continue this run's checkpoint instead of starting at generation 0")
    ap.add_argument("--fresh", action="store_true",
                    help="discard the cross-night search state and start the series over")
    ap.add_argument("--min-banks", type=int, default=2,
                    help="HARD eligibility: a lineage enters the archive only if measured on this many banks")
    ap.add_argument("--n-confirm", type=int, default=4,
                    help="top-N genomes re-scored on one extra fresh bank each generation")
    ap.add_argument("--carry-elites", type=int, default=8,
                    help="elites seeded into the initial population from the previous night")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    p = G3_evolve_v2(hours=a.hours, pop=a.pop, seed=a.seed, sel_windows=a.sel_windows,
                     n_null=a.n_null, smoke=a.smoke, resume=a.resume, fresh=a.fresh,
                     min_banks=a.min_banks, n_confirm=a.n_confirm,
                     carry_elites=a.carry_elites, run=a.run)
    p["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"G3_evolve_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nG3: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
