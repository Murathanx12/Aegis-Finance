"""The learning loop: FREEZE -> GRADE -> TRUST -> ENSEMBLE (review 2026-09-29 item 8).

What changed, and why. Until 2026-09-29 a night retrained the network from scratch on
new seeds and "promoted" it if it beat the incumbent on the validation block both had
early-stopped on -- at that block size, a coin flip (review F5). Nothing a night learned
reached the next night. This module replaces that with the only mechanism that can
improve honestly from night to night:

  a. FREEZE   every night, every model of a FIXED roster (the network, LightGBM, ridge,
              12-1 momentum and the zero; trailing vol, a ridge on |y| and the network's
              width for the size of the move) writes its predictions for the newest
              decision date to its OWN immutable file. The file's sha256 goes to an
              append-only ledger. A file is created exclusively and never rewritten.
  b. GRADE    every night, every frozen file whose horizon has elapsed is graded against
              what happened -- after its sha256 is checked against the ledger. A name
              that delisted during the hold exits at its last close (its delisting
              return is unknown on disk); a name is never dropped.
  c. TRUST    each model's trust is the POSTERIOR MEAN of its rank IC, prior N(0, 0.03^2),
              data = its OWN graded FORWARD blocks only (a block = max(h, 21) sessions, so
              blocks share almost no forward window), block noise sd 0.10. Prior strength
              k = (0.10/0.03)^2 = 11 blocks: 1 block earns 8% of its mean, 11 blocks 50%.
              The shrink is per model: a model with more graded blocks moves further from 0.
              The walk-forward record is PRINTED beside it and never enters it (amended
              2026-09-29: it had seeded every weight, so weights were backtest IC ratios).
  d. ENSEMBLE weight_m = max(0, trust_m) / TRUST_FULL_IC, never renormalised to 1 (that
              cancelled the shrink); the remainder is the neutral no-view sleeve. With no
              forward grade every weight is 0 and the ensemble IS the zero.
  e. IN CHARGE the model with the highest trust; it changes only on a night that added
              forward grades, and only by IN_CHARGE_MARGIN. A validation block never
              decides it.
  f. The ledgers only grow: frozen_ledger.jsonl, forward_grades.jsonl, trust.jsonl.

Size of the move (item 9): a first-class output. The SIMPLEST magnitude model whose
posterior improvement over trailing volatility is at least half the best one's is used;
its intervals are widened by a conformal factor from graded rows (walk-forward rows until
CONFORMAL_MIN_ROWS forward rows exist). It says nothing about direction.

PRODUCT_EXPERIMENT. No broker authority. Nothing in the live path imports this.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from nn_lab import config as C

H = C.HORIZONS
Z50, Z90 = 0.6745, 1.6449
SQRT_2_PI = math.sqrt(2.0 / math.pi)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_jsonl(p: Path) -> list[dict]:
    out = []
    if Path(p).exists():
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _append_jsonl(p: Path, rows: list[dict]) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


# ─────────────────────────────── a. FREEZE ───────────────────────────────────

VALUE_COLS = ("score", "prob", "pred_abs", "q05", "q25", "q50", "q75", "q95")


def row_hash(rec: dict) -> str:
    """Hash of a row INCLUDING its values (review F7: the old id hashed only the key,
    so a rewritten file graded under the same ids)."""
    parts = [str(rec.get(k)) for k in ("decision_date", "symbol", "horizon", "model", "model_version")]
    for c in VALUE_COLS:
        v = rec.get(c)
        parts.append("" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{float(v):.9g}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def frozen_path(decision_date, model: str, frozen_dir: Path | None = None) -> Path:
    return Path(frozen_dir or C.FROZEN_DIR) / str(pd.Timestamp(decision_date).date()) / f"{model}.parquet"


def ledger_index(ledger: Path | None = None) -> dict[tuple[str, str], dict]:
    """(decision_date, model) -> its FIRST ledger row (later rows can never replace it)."""
    out: dict[tuple[str, str], dict] = {}
    for r in _read_jsonl(Path(ledger or C.FROZEN_LEDGER)):
        out.setdefault((r["decision_date"], r["model"]), r)
    return out


def freeze(df: pd.DataFrame, *, model: str, model_version: str, decision_date, run_id: str,
           kind: str, frozen_dir: Path | None = None, ledger: Path | None = None,
           extra: dict | None = None, written_utc: str | None = None) -> dict:
    """Write ONE immutable file for (decision_date, model). If it exists: verify, never rewrite.

    `df` has columns symbol, horizon and any of VALUE_COLS."""
    dd = str(pd.Timestamp(decision_date).date())
    path = frozen_path(dd, model, frozen_dir)
    led = Path(ledger or C.FROZEN_LEDGER)
    idx = ledger_index(led)
    if path.exists():
        row = idx.get((dd, model))
        sha = sha256_file(path)
        return {"status": "ALREADY_FROZEN", "model": model, "decision_date": dd, "file": str(path),
                "sha256": sha, "verified": bool(row and row["sha256"] == sha)}
    out = df.copy()
    out.insert(0, "decision_date", dd)
    out["model"] = model
    out["model_version"] = model_version
    out["kind"] = kind
    out["written_utc"] = written_utc or _now()   # the entry rule keys on this moment
    out["run_id"] = run_id
    out["entry_rule"] = "first session after decision_date whose 13:30 UTC open is after written_utc"
    for c in VALUE_COLS:
        if c not in out.columns:
            out[c] = np.nan
        out[c] = out[c].astype("float64")
    out["row_hash"] = [row_hash(r) for r in out.to_dict("records")]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    with open(tmp, "rb") as src, open(path, "xb") as dst:     # "x": exclusive create, never overwrite
        dst.write(src.read())
    tmp.unlink(missing_ok=True)
    sha = sha256_file(path)
    entry = {"decision_date": dd, "model": model, "model_version": model_version, "kind": kind,
             "file": str(path.relative_to(C.REPO)) if str(path).startswith(str(C.REPO)) else str(path),
             "sha256": sha, "rows": int(len(out)), "names": int(out["symbol"].nunique()),
             "horizons": sorted(int(h) for h in out["horizon"].unique()),
             "written_utc": out["written_utc"].iloc[0], "run_id": run_id, **(extra or {})}
    _append_jsonl(led, [entry])
    return {"status": "FROZEN", **entry}


def _resolve(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else Path(C.REPO) / q


def verify(entry: dict) -> str:
    """'OK', 'MISSING' or 'TAMPERED' for a ledger row."""
    p = _resolve(entry["file"])
    if not p.exists():
        return "MISSING"
    return "OK" if sha256_file(p) == entry["sha256"] else "TAMPERED"


# ─────────────────────────────── b. GRADE ────────────────────────────────────

def entry_session(decision_date, written_utc, cal: pd.DatetimeIndex):
    """First session AFTER the decision date whose open (13:30 UTC, conservative) is after
    the moment the prediction was written. None if not yet in the calendar."""
    w = pd.Timestamp(written_utc)
    w = w.tz_convert(None) if w.tzinfo else w
    for d in cal[cal > pd.Timestamp(decision_date)]:
        if d + pd.Timedelta(hours=13, minutes=30) > w:
            return d
    return None


def realised(decision_date, written_utc, h: int, symbols, bars: pd.DataFrame,
             cal: pd.DatetimeIndex) -> pd.DataFrame | None:
    """Realised return open(entry) -> open(entry + h) per symbol, minus the median over ALL
    symbols of that decision date. None until the exit session is in the calendar.

    Nobody is dropped. A symbol with no bar at the exit session exits at its LAST CLOSE on
    or before it (`delist_exit`: its true delisting return is not on disk). A symbol with no
    bar at the entry session enters at its last close before it; one with no bar after the
    decision date at all has return 0 (`no_bar_after_decision`)."""
    ent = entry_session(decision_date, written_utc, cal)
    if ent is None:
        return None
    pos = int(np.searchsorted(cal.values, np.datetime64(ent)))
    if pos + int(h) >= len(cal):
        return None
    ex = cal[pos + int(h)]
    syms = pd.Index(pd.unique(pd.Series(list(symbols))))
    b = bars[bars["symbol"].isin(syms)]
    op = b.pivot_table(index="date", columns="symbol", values="open", aggfunc="first")
    cl = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="first")
    op = op.reindex(columns=syms)
    cl = cl.reindex(columns=syms)

    def last_close_on_or_before(d):
        c = cl[cl.index <= d]
        return c.ffill().iloc[-1] if len(c) else pd.Series(np.nan, index=syms)

    o0 = op.loc[ent] if ent in op.index else pd.Series(np.nan, index=syms)
    o1 = op.loc[ex] if ex in op.index else pd.Series(np.nan, index=syms)
    lc_ent, lc_ex = last_close_on_or_before(ent), last_close_on_or_before(ex)
    last_bar = b.groupby("symbol")["date"].max().reindex(syms)
    after = b[b["date"] > pd.Timestamp(decision_date)].groupby("symbol").size().reindex(syms).fillna(0)
    p0 = o0.where(o0.notna(), lc_ent)
    delist = o1.isna() & (last_bar < ex)
    p1 = o1.where(o1.notna(), lc_ex)
    r = p1 / p0 - 1.0
    none_after = after.values == 0
    r[none_after] = 0.0
    r = r.where(np.isfinite(r), 0.0)
    med = float(np.median(r.values))
    return pd.DataFrame({"symbol": syms, "raw_return": r.values, "excess": r.values - med,
                         "delist_exit": delist.fillna(False).values & ~none_after,
                         "no_bar_after_decision": none_after,
                         "entry_session": str(ent.date()), "exit_session": str(ex.date())})


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 20 or np.nanstd(a[m]) == 0:
        return float("nan")
    return float(pd.Series(a[m]).rank().corr(pd.Series(b[m]).rank()))


def grade_one(frozen: pd.DataFrame, out: pd.DataFrame, h: int, *, top_k: int = C.TOP_K) -> dict:
    """One (model, decision date, horizon) grade: direction IC and top-k, magnitude IC and
    interval coverage, as the frozen file supports."""
    f = frozen[frozen["horizon"] == h].merge(out, on="symbol", how="left")
    res = {"n": int(len(f)), "n_delist_exit": int(f["delist_exit"].fillna(False).sum()),
           "n_no_bar": int(f["no_bar_after_decision"].fillna(False).sum())}
    x = f["excess"].to_numpy(dtype="float64")
    s = f["score"].to_numpy(dtype="float64")
    if np.isfinite(s).any():
        res["rank_ic"] = _spearman(s, x)
        if np.isfinite(s).sum() >= 5 * top_k and np.nanstd(s) > 0:
            top = f.loc[np.argsort(-np.nan_to_num(s, nan=-np.inf))[:top_k]]
            res["topk_minus_median"] = float(top["excess"].mean())
        if f["prob"].notna().any():
            p = f["prob"].to_numpy(dtype="float64")
            ok = np.isfinite(p) & np.isfinite(x)
            res["brier"] = float(np.mean((p[ok] - (x[ok] > 0)) ** 2)) if ok.any() else None
    a = f["pred_abs"].to_numpy(dtype="float64")
    if np.isfinite(a).any():
        res["abs_ic"] = _spearman(a, np.abs(x))
    if f["q05"].notna().any():
        res["cov50"] = float(((x >= f["q25"]) & (x <= f["q75"])).mean())
        res["cov90"] = float(((x >= f["q05"]) & (x <= f["q95"])).mean())
    return {k: (round(v, 6) if isinstance(v, float) and np.isfinite(v) else v) for k, v in res.items()}


def step_grade(bars: pd.DataFrame, cal: pd.DatetimeIndex, *, ledger: Path | None = None,
               grades: Path | None = None, outcomes_dir: Path | None = None) -> dict:
    """Grade every ledger row whose horizon has elapsed and that is not graded yet."""
    led = _read_jsonl(Path(ledger or C.FROZEN_LEDGER))
    gp = Path(grades or C.FORWARD_GRADES)
    done = {(g["model"], g["decision_date"], int(g["horizon"]), g["sha256"]) for g in _read_jsonl(gp)}
    od = Path(outcomes_dir or C.OUTCOMES_DIR)
    new, refused, pending = [], [], 0
    cache: dict[tuple[str, int], pd.DataFrame | None] = {}
    seen = set()
    for e in led:
        key0 = (e["decision_date"], e["model"])
        if key0 in seen:          # only the FIRST ledger row of a (date, model) counts
            continue
        seen.add(key0)
        todo = [h for h in e.get("horizons", H) if (e["model"], e["decision_date"], int(h), e["sha256"]) not in done]
        if not todo:
            continue
        st = verify(e)
        if st != "OK":
            refused.append({"decision_date": e["decision_date"], "model": e["model"], "status": st})
            continue
        fz = pd.read_parquet(_resolve(e["file"]))
        if "score" not in fz.columns and "mean" in fz.columns:          # the legacy v0 file
            fz = fz.rename(columns={"mean": "score"})
        for c in VALUE_COLS:
            if c not in fz.columns:
                fz[c] = np.nan
        if fz["pred_abs"].isna().all() and fz["q95"].notna().any():
            fz["pred_abs"] = (fz["q95"] - fz["q05"]) / 3.29 * SQRT_2_PI
        wu = fz["written_utc"].iloc[0]
        for h in todo:
            ck = (e["decision_date"], int(h))
            if ck not in cache:
                p = od / f"{e['decision_date']}_h{h}.parquet"
                if p.exists():
                    cache[ck] = pd.read_parquet(p)
                else:
                    o = realised(e["decision_date"], wu, int(h), fz["symbol"].unique(), bars, cal)
                    if o is not None:
                        od.mkdir(parents=True, exist_ok=True)
                        with open(p, "xb") as fh:           # an outcome is written once
                            o.to_parquet(fh, index=False)
                    cache[ck] = o
            o = cache[ck]
            if o is None:
                pending += 1
                continue
            g = grade_one(fz, o, int(h))
            new.append({"model": e["model"], "model_version": e.get("model_version"),
                        "kind": e.get("kind"), "decision_date": e["decision_date"], "horizon": int(h),
                        "sha256": e["sha256"], "entry_session": o["entry_session"].iloc[0],
                        "exit_session": o["exit_session"].iloc[0], **g, "graded_utc": _now()})
    _append_jsonl(gp, new)
    n_dir = sum(1 for g in new if g["model"] in C.DIRECTION_ROSTER and g["model"] != "zero")
    return {"graded_now": len(new), "graded_now_direction_roster": n_dir, "pending_horizons": pending,
            "refused_unverified": refused, "graded_total": len(_read_jsonl(gp))}


# ─────────────────────────────── c. TRUST ────────────────────────────────────

def blocks(dates, values, cal: pd.DatetimeIndex, h: int) -> np.ndarray:
    """Per-block means of per-date values; a block is max(h, 21) sessions."""
    s = pd.Series(np.asarray(values, dtype="float64"), index=pd.DatetimeIndex(pd.to_datetime(list(dates))))
    s = s[np.isfinite(s.values)]
    if s.empty:
        return np.array([])
    pos = np.searchsorted(cal.values, s.index.values)
    return s.groupby(pos // max(h, 21)).mean().to_numpy()


def posterior(fwd_blocks: np.ndarray, *, wf_mean: float | None = None, wf_blocks: float = 0.0,
              prior_sd: float = C.TRUST_PRIOR_SD, block_sd: float = C.TRUST_BLOCK_SD,
              wf_weight: float = C.WF_BLOCK_WEIGHT) -> dict:
    """Normal-normal posterior of a mean IC, prior N(0, prior_sd^2). Forward blocks count 1;
    walk-forward blocks count wf_weight, fading to 0 as forward blocks reach k."""
    k = (block_sd / prior_sd) ** 2
    n_f = float(len(fwd_blocks))
    m_f = float(np.mean(fwd_blocks)) if n_f else 0.0
    fade = max(0.0, 1.0 - n_f / k)
    n_w = (wf_weight * fade * float(wf_blocks)) if (wf_mean is not None and np.isfinite(wf_mean)) else 0.0
    m_w = float(wf_mean) if n_w else 0.0
    n = n_f + n_w
    mean = (n_f * m_f + n_w * m_w) / (n + k)
    src = ("forward" if n_f and not n_w else "forward+walk_forward" if n_f and n_w
           else "walk_forward_only" if n_w else "prior_only")
    return {"trust": round(mean, 6), "n_forward_blocks": int(n_f), "forward_mean_ic": round(m_f, 6) if n_f else None,
            "n_walk_forward_blocks_effective": round(n_w, 3), "walk_forward_mean_ic": round(m_w, 6) if n_w else None,
            "shrink": round(n / (n + k), 4), "prior_strength_blocks": round(k, 2), "source": src}


def trust_table(grades: list[dict], cal: pd.DatetimeIndex, wf: dict, *,
                models=C.DIRECTION_ROSTER + ("ensemble",), horizons=H) -> dict:
    """model -> horizon -> posterior dict (direction: rank IC).

    FORWARD grades only. `wf` (the walk-forward receipt) is reported on the row as
    `walk_forward_mean_ic_reported` and does not change the trust: a backtest file alone
    never moves a weight."""
    g = pd.DataFrame(grades)
    out: dict = {}
    for m in models:
        for h in horizons:
            if len(g) and "rank_ic" in g.columns:
                gg = g[(g["model"] == m) & (g["horizon"] == h)]
                bl = blocks(gg["decision_date"], gg["rank_ic"], cal, h) if len(gg) else np.array([])
                n_dates = int(gg["rank_ic"].notna().sum()) if len(gg) else 0
            else:
                bl, n_dates = np.array([]), 0
            w = (wf.get(m) or {}).get(f"h{h}") or {}
            post = posterior(bl)                          # forward blocks only
            post["walk_forward_mean_ic_reported"] = w.get("mean")
            post["walk_forward_used"] = False
            if m == "zero":
                post = {**post, "trust": 0.0, "source": "definition: the zero"}
            out.setdefault(m, {})[f"h{h}"] = {"graded_dates": n_dates, **post}
    return out


def magnitude_table(grades: list[dict], cal: pd.DatetimeIndex, wf: dict, *,
                    horizons=C.MAGNITUDE_HORIZONS) -> dict:
    """Magnitude models: posterior of (abs IC minus trailing vol's abs IC) per block,
    prior N(0, 0.01^2), block sd 0.015 (walk-forward: NN width minus vol SE 0.0015 x sqrt(80))."""
    g = pd.DataFrame(grades)
    out: dict = {}
    for h in horizons:
        base = None
        if len(g) and "abs_ic" in g.columns:
            base = g[(g["model"] == "trailing_vol") & (g["horizon"] == h)].set_index("decision_date")["abs_ic"]
        for m in C.MAGNITUDE_ROSTER:
            if m == "trailing_vol":
                out.setdefault(m, {})[f"h{h}"] = {"improvement_over_vol": 0.0, "source": "definition: the baseline"}
                continue
            bl = np.array([])
            if base is not None and len(base):
                mm = g[(g["model"] == m) & (g["horizon"] == h)].set_index("decision_date")["abs_ic"]
                d = (mm - base).dropna()
                bl = blocks(d.index, d.values, cal, h)
            w = (wf.get(m) or {}).get(f"h{h}") or {}
            post = posterior(bl, wf_mean=w.get("mean"), wf_blocks=w.get("n_blocks") or 0,
                             prior_sd=0.01, block_sd=0.015)
            post["improvement_over_vol"] = post.pop("trust")
            out.setdefault(m, {})[f"h{h}"] = post
    return out


def choose_magnitude(mag: dict, h: int) -> tuple[str, str]:
    """The SIMPLEST magnitude model whose posterior improvement over trailing vol is at
    least half the best one's (and positive); trailing vol when none improves."""
    imp = {m: (mag.get(m, {}).get(f"h{h}", {}).get("improvement_over_vol") or 0.0) for m in C.MAGNITUDE_ROSTER}
    best = max(imp.values())
    if best <= 0:
        return "trailing_vol", "no model improves on trailing vol yet"
    for m in C.MAGNITUDE_ROSTER:
        if m != "trailing_vol" and imp[m] >= 0.5 * best:
            return m, (f"simplest with >= half the best posterior improvement over vol "
                       f"({imp[m]:+.4f} vs best {best:+.4f})")
    return "trailing_vol", "fallback"


def decide_in_charge(prev: dict | None, trust: dict, *, forward_added: bool, horizon: str = "h21",
                     margin: float = C.IN_CHARGE_MARGIN) -> dict:
    """The model in charge changes ONLY on a night that added forward grades, and only a
    model with POSITIVE forward trust can be in charge; otherwise the zero is. A demotion to
    the zero when the in-charge model has no positive trust is always allowed (it is not a
    promotion): the 2026-09-28 'lgbm' was chosen on walk-forward trust alone."""
    cands = {m: v[horizon]["trust"] for m, v in trust.items()
             if m not in ("ensemble", "zero") and horizon in v and (v[horizon]["trust"] or 0) > 0}
    best = max(cands, key=lambda m: cands[m]) if cands else "zero"
    now = _now()
    if prev is None:
        return {"model": best, "since": now, "why": ("first night: highest positive forward trust"
                                                     if cands else "no model has positive forward trust"),
                "history": []}
    cur = prev["model"]
    if cur != "zero" and cur not in cands:
        hist = prev.get("history", []) + [{"from": cur, "to": "zero", "at": now, "trust_from":
                                           ((trust.get(cur) or {}).get(horizon) or {}).get("trust"),
                                           "trust_to": 0.0}]
        return {"model": "zero", "since": now, "history": hist,
                "why": f"{cur} has no positive FORWARD trust: the zero is in charge"}
    if not forward_added:
        return {**prev, "why_kept": "no forward grade was added tonight: in-charge cannot change"}
    if best != cur and cands.get(best, 0) > cands.get(cur, 0) + margin:
        hist = prev.get("history", []) + [{"from": cur, "to": best, "at": now,
                                           "trust_from": cands.get(cur), "trust_to": cands.get(best)}]
        return {"model": best, "since": now, "why": f"{best} trust {cands[best]:+.4f} > {cur} "
                f"{cands.get(cur, 0):+.4f} + margin {margin}", "history": hist}
    return {**prev, "why_kept": f"{cur} kept: no rival exceeds it by the margin {margin}"}


# ─────────────────────────────── d. ENSEMBLE ─────────────────────────────────

def ensemble_weights(trust: dict, h: int, models, *, full_ic: float = C.TRUST_FULL_IC) -> dict:
    """{model: weight, ..., "neutral": remainder}. weight = max(0, trust) / full_ic: the
    posterior's shrink is kept (never renormalised to 1). Only if the weights would sum
    above 1 are they scaled down to 1, and the result says so."""
    w = {m: max(0.0, float(((trust.get(m) or {}).get(f"h{h}") or {}).get("trust") or 0.0)) / full_ic
         for m in models if m not in ("zero", "neutral")}
    tot = sum(w.values())
    scaled = tot > 1.0
    if scaled:
        w = {m: v / tot for m, v in w.items()}
    out: dict = {m: round(v, 6) for m, v in w.items()}
    out["neutral"] = round(max(0.0, 1.0 - sum(w.values())), 6)
    out["_scaled_down_to_1"] = scaled
    return out


def ensemble_scores(scores: dict[str, np.ndarray], trust: dict, h: int) -> tuple[np.ndarray, dict]:
    """Trust-SCALED sum of each model's cross-sectional rank in [-1, 1]; the neutral sleeve
    contributes 0. Negative or zero trust weighs nothing; with no forward grade every weight
    is 0 and the ensemble is the zero."""
    w = ensemble_weights(trust, h, list(scores))
    n = len(next(iter(scores.values())))
    acc = np.zeros(n)
    for m, s in scores.items():
        if m == "zero" or not w.get(m):
            continue
        r = pd.Series(s).rank(pct=True).to_numpy()
        acc += w[m] * np.nan_to_num((r - 0.5) * 2.0, nan=0.0)
    return acc, w


def weight_report(trust: dict, prev_trust: dict | None, models, horizons=H) -> dict:
    """Per horizon, per model: forward graded blocks, weight today and yesterday, and what
    moved it. Only a forward grade can move a weight; the line says which."""
    out: dict = {}
    for h in horizons:
        now = ensemble_weights(trust, h, models)
        was = ensemble_weights(prev_trust, h, models) if prev_trust else None
        rows = {}
        for m in models:
            if m == "zero":
                continue
            v = (trust.get(m) or {}).get(f"h{h}") or {}
            pv = ((prev_trust or {}).get(m) or {}).get(f"h{h}") or {}
            wt = now.get(m, 0.0)
            wy = was.get(m) if was is not None else None
            nb, pnb = v.get("n_forward_blocks", 0), pv.get("n_forward_blocks")
            if was is None:
                why = "no previous row"
            elif wt == wy:
                why = "unchanged"
            elif nb != pnb or v.get("forward_mean_ic") != pv.get("forward_mean_ic"):
                why = (f"forward blocks {pnb} -> {nb}, forward mean IC {pv.get('forward_mean_ic')} -> "
                       f"{v.get('forward_mean_ic')}")
            elif pv.get("walk_forward_used", True):
                why = "the previous row used walk-forward trust (retired 2026-09-29); forward-only now"
            else:
                why = "another model's weight crossed the sum-to-1 cap (scaled)"
            rows[m] = {"forward_blocks": nb, "graded_dates": v.get("graded_dates"), "trust": v.get("trust"),
                       "weight": wt, "weight_yesterday": wy, "moved_by": why,
                       "walk_forward_mean_ic_reported_not_used": v.get("walk_forward_mean_ic_reported")}
        out[f"h{h}"] = {"models": rows, "neutral": now["neutral"], "scaled_down_to_1": now["_scaled_down_to_1"]}
    return out


# ─────────────────────────────── size of the move ────────────────────────────

def conformal_factors(pred_abs: np.ndarray, realised_excess: np.ndarray) -> dict:
    """c such that |excess| <= c * pred_abs on 50% / 90% of the calibration rows."""
    a = np.asarray(pred_abs, dtype="float64")
    x = np.abs(np.asarray(realised_excess, dtype="float64"))
    m = np.isfinite(a) & np.isfinite(x) & (a > 0)
    if m.sum() < 50:
        return {"c50": None, "c90": None, "n": int(m.sum())}
    r = x[m] / a[m]
    return {"c50": round(float(np.quantile(r, 0.5)), 4), "c90": round(float(np.quantile(r, 0.9)), 4),
            "n": int(m.sum())}
