"""Contest simulator: past earnings seasons, several RULES x three FILL assumptions.

    python -m scripts.contest_rotation_sim                  # all seasons on disk
    python -m scripts.contest_rotation_sim --draws 2000 --from-year 2019

Extended from the adversarial review's scratch `rotation_sim.py` (2026-09-28): same
zero-direction-skill convention (one random sign per DAY applied to every held name AND
the benchmark, so magnitudes and same-day dispersion survive while direction is a coin
flip), same 25-session contest-shaped windows, now global and with three fills:

  close      buy at the close before the report, sell at the close of the reaction session
  next_open  buy at the open of the session before the report, sell at the reaction session's open
  open_25    next_open with 25 bps per side

RULES
  ROT_ALL        rotation by past move size, every market
  ROT_ASIA       the same, restricted to Asian listings (the owner's daytime)
  ROT_US         the same, US only (the review's rule)
  ROT_RANDOM     rotation with a random rank (control: no magnitude signal)
  MOM_ROT        2025-winner-like daily momentum: the 5 liquid names with the largest
                 up-move on >= 2x volume today, held one session
  HIVOL_BH       buy and hold the 5 highest-sigma liquid names with a report in the window
  REHEARSAL_BH   rehearsal-shaped proxy: 10 x 10% US names by sigma with a report in the
                 window, held (the frozen book's fundamentals tilt and size band are NOT
                 reproduced; stated)

EVERY RULE HERE LOSES MORE OFTEN THAN IT WINS under zero skill: the median relative
result is negative. It is a choice of variance for rank. Seasons are reported one by
one; any pooled line says what it pools.

PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. No network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc   # noqa: E402
from scripts import contest_desk as desk     # noqa: E402

OUT = cc.CONTEST / "sim"
STARTS = {"Jan": (1, 19), "Apr": (4, 12), "Jul": (7, 12), "Oct": (10, 12)}
WINDOW_DAYS = 32              # calendar days: Oct 12 -> Nov 13
TARGETS = (0.20, 0.40, 1.00)
FILLS = ("close", "next_open", "open_25")
SEED = 20261012


def summarize(rel: np.ndarray) -> dict:
    rel = np.asarray(rel, dtype=float)
    d = {f"P>{t:+.0%}": float((rel > t).mean()) for t in TARGETS}
    d.update(median=float(np.median(rel)), p05=float(np.quantile(rel, .05)),
             p95=float(np.quantile(rel, .95)), mean=float(rel.mean()))
    return d


class Sim:
    def __init__(self, panel: desk.Panel, events: pd.DataFrame, vratio: Optional[np.ndarray],
                 draws: int = 4000, seed: int = SEED):
        self.p = panel
        self.ev = events[events.pre_i.notna() & events.react_i.notna() & events.r_c2c.notna()].copy()
        self.ev["pre_i"] = self.ev.pre_i.astype(int)
        self.ev["react_i"] = self.ev.react_i.astype(int)
        self.by_pre = {i: g for i, g in self.ev.groupby("pre_i")}
        self.vr = vratio
        self.draws = draws
        self.rng = np.random.default_rng(seed)
        b = "ACWI" if "ACWI" in panel.col else "SPY"
        self.bench_sym = b
        # carried across other markets' days, so a day the benchmark did not trade is 0
        bc = pd.Series(panel.close[:, panel.col[b]]).ffill()
        bo = pd.Series(panel.open[:, panel.col[b]]).ffill()
        self.b_c2c = (bc.shift(-1) / bc - 1).to_numpy()       # this row's close -> next row's close
        self.b_o2o = (bo.shift(-1) / bo - 1).to_numpy()
        # per-name returns on own sessions (0 on days the name did not trade)
        C = pd.DataFrame(panel.close)
        prev = C.ffill().shift(1)
        self.ret = (C / prev - 1).fillna(0.0).to_numpy(dtype="float32")
        self.liq = np.nan_to_num(panel.dv63) >= cc.LIQ_FLOOR_USD

    # ── rotation ──
    def rotation(self, days: np.ndarray, *, rank: str = "trail", markets: Optional[tuple] = None,
                 fill: str = "close", flip: bool = True) -> tuple[np.ndarray, float]:
        nd = self.draws if flip else 1
        nav = np.ones(nd)
        bench = np.ones(nd)
        ncand = []
        cost = 0.0025 if fill == "open_25" else 0.0
        col = "r_c2c" if fill == "close" else "r_o2o"
        for t in days:
            g = self.by_pre.get(int(t))
            r = np.array([])
            if g is not None:
                ok = (g.on_cadence.to_numpy() & g.trail_abs.notna().to_numpy()
                      & self.liq[t, g.ci.to_numpy()] & np.isfinite(g[col].to_numpy()))
                if markets is not None:
                    ok &= g.market.isin(markets).to_numpy()
                gg = g[ok]
                if len(gg):
                    key = gg.trail_abs.to_numpy() if rank == "trail" else self.rng.random(len(gg))
                    order = np.argsort(-key)
                    r = gg[col].to_numpy()[order][:desk.K_SLOTS]
                ncand.append(len(gg))
            else:
                ncand.append(0)
            s = self.rng.choice([-1.0, 1.0], size=nd) if flip else np.ones(nd)
            gross = r.sum() * desk.WEIGHT
            day = s * gross - 2 * cost * desk.WEIGHT * len(r)
            nav *= np.maximum(1 + day, 0.001)
            rb = self.b_c2c[t] if fill == "close" else self.b_o2o[t]
            bench *= 1 + s * np.nan_to_num(rb)
        return nav - bench, float(np.mean(ncand)) if ncand else 0.0

    # ── momentum rotation ──
    def momentum(self, days: np.ndarray, *, fill: str = "close", flip: bool = True) -> np.ndarray:
        nd = self.draws if flip else 1
        nav, bench = np.ones(nd), np.ones(nd)
        cost = 0.0025 if fill == "open_25" else 0.0
        P = self.p
        for t in days:
            traded = np.isfinite(P.close[t])
            ok = traded & self.liq[t] & (self.ret[t] > 0)
            if self.vr is not None:
                ok &= np.nan_to_num(self.vr[t]) >= 2.0
            idx = np.flatnonzero(ok)
            r = []
            if len(idx):
                pick = idx[np.argsort(-self.ret[t, idx])][:desk.K_SLOTS]
                for j in pick:
                    live = np.flatnonzero(np.isfinite(P.close[t + 1:, j]))
                    if len(live) < 2:
                        continue
                    n1, n2 = t + 1 + live[0], t + 1 + live[1]
                    if fill == "close":
                        x = P.close[n1, j] / P.close[t, j] - 1
                    else:
                        x = P.open[n2, j] / P.open[n1, j] - 1
                    if np.isfinite(x) and -0.8 < x < 2.0:
                        r.append(x)
            s = self.rng.choice([-1.0, 1.0], size=nd) if flip else np.ones(nd)
            day = s * desk.WEIGHT * float(np.sum(r)) - 2 * cost * desk.WEIGHT * len(r)
            nav *= np.maximum(1 + day, 0.001)
            rb = self.b_c2c[t] if fill == "close" else self.b_o2o[t]
            bench *= 1 + s * np.nan_to_num(rb)
        return nav - bench

    # ── buy and hold ──
    def buyhold(self, days: np.ndarray, *, k: int = 5, us_only: bool = False,
                flip: bool = True, fill: str = "close") -> tuple[np.ndarray, list]:
        t0, t1 = int(days[0]), int(days[-1])
        g = self.ev[(self.ev.react_i > t0) & (self.ev.react_i <= t1) & self.ev.on_cadence]
        ci = np.unique(g.ci.to_numpy())
        if us_only:
            ci = ci[self.p.market[ci] == "US"]
        ci = ci[self.liq[t0, ci] & np.isfinite(self.p.sig63[t0, ci])]
        ci = ci[np.argsort(-self.p.sig63[t0, ci])][:k]
        R = self.ret[t0 + 1: t1 + 1][:, ci]
        rb = np.nan_to_num(self.b_c2c[t0: t1])
        nd = self.draws if flip else 1
        S = self.rng.choice([-1.0, 1.0], size=(nd, len(rb))) if flip else np.ones((1, len(rb)))
        val = np.prod(np.maximum(1 + S[:, :, None] * R[None, :, :], 0.0), axis=1).mean(axis=1)
        bv = np.prod(1 + S * rb[None, :], axis=1)
        cost = 2 * 0.0025 if fill == "open_25" else 0.0
        return val - bv - cost, [str(self.p.syms[i]) for i in ci]


def windows(panel: desk.Panel, from_year: int) -> list[tuple[str, np.ndarray]]:
    out = []
    last = panel.dates[-1]
    for y in range(from_year, 2027):
        for nm, (m, d) in STARTS.items():
            st = pd.Timestamp(y, m, d)
            en = st + pd.Timedelta(days=WINDOW_DAYS)
            if en + pd.Timedelta(days=3) > last:
                continue
            idx = np.flatnonzero((panel.dates >= st) & (panel.dates <= en))
            if len(idx) > 10 and idx[0] > 300:
                out.append((f"{y}-{nm}", idx[:-1]))
    return out


def vratio_matrix(panel_long: pd.DataFrame, panel: desk.Panel) -> np.ndarray:
    V = panel_long.pivot(index="date", columns="symbol", values="volume").reindex(
        index=panel.dates, columns=panel.syms).astype("float32")
    out = np.full(V.shape, np.nan, dtype="float32")
    Vv = V.to_numpy()
    for j in range(V.shape[1]):
        m = np.isfinite(Vv[:, j])
        if m.sum() < 25:
            continue
        s = pd.Series(Vv[m, j])
        out[m, j] = (s / s.shift(1).rolling(20, min_periods=15).mean()).to_numpy()
    return out


def run(draws: int = 4000, from_year: int = 2017) -> dict:
    long = cc.load_bars_usd([m for m in cc.MARKETS if m != "US"], include_us=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long[long.date >= pd.Timestamp("2016-01-01")].drop_duplicates(["symbol", "date"])
    panel = desk.panel_from_long(long)
    vr = vratio_matrix(long, panel)
    del long
    raw = desk.raw_event_stamps()
    events = desk.build_events(panel, raw)
    print("panel", len(panel.dates), "days x", len(panel.syms), "symbols;", len(events), "events;",
          events.market.value_counts().to_dict(), flush=True)
    sim = Sim(panel, events, vr, draws=draws)
    rows = []
    for wname, days in windows(panel, from_year):
        row = {"window": wname, "start": str(panel.dates[days[0]].date()),
               "end": str(panel.dates[days[-1]].date()), "rules": {}}
        for fill in FILLS:
            for label, kw in (("ROT_ALL", {}), ("ROT_ASIA", {"markets": cc.ASIA}),
                              ("ROT_US", {"markets": ("US",)}), ("ROT_RANDOM", {"rank": "random"})):
                rel, nc = sim.rotation(days, fill=fill, **kw)
                hist, _ = sim.rotation(days, fill=fill, flip=False, **kw)
                row["rules"][f"{label}|{fill}"] = {"realised": float(hist[0]), "avg_candidates": nc,
                                                   **summarize(rel)}
            rel = sim.momentum(days, fill=fill)
            hist = sim.momentum(days, fill=fill, flip=False)
            row["rules"][f"MOM_ROT|{fill}"] = {"realised": float(hist[0]), **summarize(rel)}
            for label, kw in (("HIVOL_BH", {"k": 5}), ("REHEARSAL_BH", {"k": 10, "us_only": True})):
                rel, names = sim.buyhold(days, fill=fill, **kw)
                hist, _ = sim.buyhold(days, fill=fill, flip=False, **kw)
                row["rules"][f"{label}|{fill}"] = {"realised": float(hist[0]), "names": names,
                                                   **summarize(rel)}
        rows.append(row)
        r = row["rules"]
        print(wname, " ".join(f"{k}:{v['P>+40%']:.3f}/{v['median']:+.2f}" for k, v in r.items()
                              if k.endswith("|close")), flush=True)
    return {"benchmark": sim.bench_sym, "draws": draws, "windows": rows, "from_year": from_year,
            "stitched_cut": {m: a.get("cut_symbols", []) for m, a in cc.STITCH_AUDIT.items()},
            "n_events": int(len(events)), "events_by_market": events.market.value_counts().to_dict(),
            "licence": desk.LICENCE,
            "caveats": ["zero direction skill by construction (daily sign flip)",
                        "US report dates: SEC 8-K 2.02 acceptance times; elsewhere Yahoo earnings dates (vendor)",
                        "a report with no time stamp is held two sessions (both cases covered)",
                        "survivor-selected outside the US: today's listings only",
                        "WLS membership not applied (not on disk)",
                        "each rotation step is one day even when a hold spans two sessions",
                        "prices converted to USD with Yahoo daily FX closes"]}


def table(res: dict) -> str:
    """Per-rule, per-fill averages by era, plus the Oct seasons; no silent pooling."""
    recs = []
    for w in res["windows"]:
        y, s = w["window"].split("-")
        for k, v in w["rules"].items():
            rule, fill = k.split("|")
            recs.append({"window": w["window"], "year": int(y), "season": s, "rule": rule, "fill": fill,
                         **{kk: v[kk] for kk in ("P>+20%", "P>+40%", "P>+100%", "median", "p05", "realised")}})
    df = pd.DataFrame(recs)
    df["era"] = pd.cut(df.year, [2015, 2020, 2023, 2027], labels=["2016-20", "2021-23", "2024-26"])
    lines = []
    for title, sub in (("Oct seasons only (one per year)", df[df.season == "Oct"]),
                       ("2024-26, all four seasons", df[df.era == "2024-26"])):
        g = sub.groupby(["rule", "fill"]).agg(n=("window", "size"), p20=("P>+20%", "mean"),
                                              p40=("P>+40%", "mean"), p100=("P>+100%", "mean"),
                                              med=("median", "mean"), p05=("p05", "mean"),
                                              p40_min=("P>+40%", "min"), p40_max=("P>+40%", "max"),
                                              real_gt20=("realised", lambda s: int((s > 0.2).sum())))
        lines.append(f"### {title} (mean of per-season numbers; n = seasons)\n")
        lines.append("| rule | fill | n | P>+20% | P>+40% (range) | P>+100% | median | p05 | realised > +20% |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for (rule, fill), r in g.iterrows():
            lines.append(f"| {rule} | {fill} | {int(r.n)} | {r.p20:.1%} | {r.p40:.1%} ({r.p40_min:.1%}-{r.p40_max:.1%}) "
                         f"| {r.p100:.1%} | {r.med:+.1%} | {r.p05:+.1%} | {int(r.real_gt20)} of {int(r.n)} |")
        lines.append("")
    lines += season_table(df, "next_open")
    return "\n".join(lines)


def season_table(df: pd.DataFrame, fill: str) -> list[str]:
    """Every season on its own line: P(> +40% rel) / median, one fill. No pooling."""
    sub = df[df.fill == fill]
    rules = sorted(sub.rule.unique())
    out = [f"### Every season, fill = {fill}: P(> +40% relative) / median relative\n",
           "| season | " + " | ".join(rules) + " |", "|---|" + "---|" * len(rules)]
    for w, g in sub.groupby("window", sort=False):
        gi = g.set_index("rule")
        out.append(f"| {w} | " + " | ".join(
            f"{gi.at[r, 'P>+40%']:.1%} / {gi.at[r, 'median']:+.1%}" if r in gi.index else "n/a"
            for r in rules) + " |")
    out.append("")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--from-year", type=int, default=2017)
    a = ap.parse_args(argv)
    res = run(a.draws, a.from_year)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = cc.utc_stamp()
    cc.write_json(res, OUT / f"sim_{stamp}.json")
    md = table(res)
    (OUT / f"sim_{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    print("receipt:", OUT / f"sim_{stamp}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
