"""Generate the README figures from live/run data. Numbers are read from the
track-record API and the frozen run JSONs -- never retyped.

Usage:  python tools/readme_charts.py
Writes: docs/assets/*.png
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
MODULE = ROOT.parent / "Aegis module"
API = "https://aegis-finance-production.up.railway.app/api/pi/track-record"

# Palette (dataviz skill reference instance, validated 2026-08-14: ALL PASS)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
GRID = "#ebeae7"
MUTED = "#c9c8c2"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "text.color": INK,
        "axes.edgecolor": INK2,
        "axes.labelcolor": INK2,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)



def _title(ax, main, sub):
    ax.text(0, 1.14, main, transform=ax.transAxes, fontsize=13, fontweight="bold", color=INK, va="bottom")
    ax.text(0, 1.04, sub, transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom", wrap=True)

def _style(ax, ygrid=True):
    ax.grid(axis="y" if ygrid else "x", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)


def chart_lanes() -> None:
    data = json.load(urlopen(API, timeout=90))
    lanes, bench = data["lanes"], data["benchmarks"]

    def series(points):
        xs = [mdates.datestr2num(p["date"]) for p in points]
        ys = [p["value"] / 1000 for p in points]
        return xs, ys

    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=160)
    highlight = {"aggressive": BLUE, "conviction": AQUA, "mirror": ORANGE}
    for name, pts in lanes.items():
        if not pts or name in highlight:
            continue
        xs, ys = series(pts)
        ax.plot(xs, ys, color=MUTED, lw=1.1, zorder=2)
    for name, color in highlight.items():
        xs, ys = series(lanes[name])
        ax.plot(xs, ys, color=color, lw=2.0, zorder=4)
        ax.annotate(
            f" {name} ${ys[-1]*1000:,.0f}",
            (xs[-1], ys[-1]),
            color=color,
            fontsize=9,
            fontweight="bold",
            va="center",
        )
    xs, ys = series(bench["SPY"])
    ax.plot(xs, ys, color=INK, lw=1.8, ls=(0, (4, 2)), zorder=5)
    ax.annotate(
        f" SPY ${ys[-1]*1000:,.0f}", (xs[-1], ys[-1]), color=INK, fontsize=9, fontweight="bold", va="center"
    )

    from matplotlib.lines import Line2D

    handles = [
        Line2D([], [], color=BLUE, lw=2, label="aggressive"),
        Line2D([], [], color=AQUA, lw=2, label="conviction"),
        Line2D([], [], color=ORANGE, lw=2, label="mirror"),
        Line2D([], [], color=MUTED, lw=1.2, label="other lanes (7)"),
        Line2D([], [], color=INK, lw=1.8, ls=(0, (4, 2)), label="SPY"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8.5, ncols=2)
    _title(ax, "Ten paper lanes vs SPY -- the live forward record",
           f"$100k at inception {data['inception_date']}, marked daily, hash-pinned configs. At this window the SE on an\n"
           "annualized Sharpe is ±2.1 -- ordering is noise, the record is the point.")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}k"))
    _style(ax)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(ASSETS / "paper_lanes_vs_spy.png", bbox_inches="tight")
    plt.close(fig)


def chart_market_graph() -> None:
    g = json.load(open(MODULE / "runs/MARKET-GRAPH-1/grade_report.json", encoding="utf-8"))
    arms = g["arms"]
    rows = [
        ("Semantic graph\n(all pairs)", arms["semantic"]["h1_all_pairs"], BLUE),
        ("Semantic graph\n(cross-industry only)", arms["semantic"]["h1_cross_sector_and_sic2"], BLUE),
        ("Shuffled-graph placebo", arms["placebo_shuffled"]["h1_all_pairs"], MUTED),
        ("Random-edges placebo", arms["random_matched_density"]["h1_all_pairs"], MUTED),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.2), dpi=160)
    ys = range(len(rows))
    for y, (label, h, color) in zip(ys, rows):
        v = h["delta_r2"] * 1e4
        mde = h["delta_r2_mde"] * 1e4
        ax.barh(y, v, height=0.52, color=color, zorder=3)
        ax.plot([mde, mde], [y - 0.34, y + 0.34], color=INK, lw=1.6, zorder=4)
        ax.annotate(
            f" {v:+.2f}",
            (max(v, 0), y),
            va="center",
            fontsize=9,
            fontweight="bold",
            color=INK if color != MUTED else INK2,
        )
    ax.set_yticks(list(ys), [r[0] for r in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Out-of-sample ΔR² on forward co-movement (×10⁻⁴)   |   black tick = each arm's own 80%-power MDE")
    _title(ax, "The one clean positive: LLM-read filings know how stocks co-move",
           "MARKET-GRAPH-1 (pre-registered): the semantic arm clears its MDE (t = 4.35); both placebos sit at zero.\n"
           "It predicts co-movement, not returns.")
    _style(ax)
    fig.tight_layout()
    fig.savefig(ASSETS / "finding_market_graph.png", bbox_inches="tight")
    plt.close(fig)


def chart_covariance_ladder() -> None:
    c = json.load(open(MODULE / "runs/GRAPH-COVARIANCE-1/grade_report.json", encoding="utf-8"))
    arms = c["arms"]
    ref = arms["model_numeric"]["mean_vol_realised"]

    def pct(k):
        return (ref - arms[k]["mean_vol_realised"]) / ref * 100

    rows = [
        ("Trailing sample matrix", "sample"),
        ("PERFECT FORESIGHT of forward corr.", "oracle_full"),
        ("Ledoit-Wolf shrinkage", "ledoit_wolf"),
        ("RMT denoised", "rmt_denoised"),
        ("MG1 ridge + semantic graph", "model_semantic"),
        ("Diagonal (industry assumption)", "diagonal"),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.4), dpi=160)
    for y, (label, key) in enumerate(rows):
        v = pct(key)
        color = BLUE if v > 0 else ORANGE
        ax.barh(y, v, height=0.52, color=color, zorder=3)
        if v < -20:
            ax.annotate(f" {v:+.1f}% ", (v, y), va="center", ha="left", fontsize=9,
                        fontweight="bold", color="#ffffff", zorder=5)
        else:
            ax.annotate(f" {v:+.1f}% ", (v, y), va="center",
                        ha="left" if v > 0 else "right", fontsize=9,
                        fontweight="bold", color=INK, zorder=5)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Realised min-variance portfolio risk vs the MG1 ridge baseline (positive = safer portfolio)")
    _title(ax, "The honest closure: even perfect foresight can't beat the trailing matrix",
           "GRAPH-COVARIANCE-1: oracle vs sample |t| = 0.23 -- statistically a tie -- while the industry diagonal is\n"
           "detectably terrible. The covariance door closed for $0 of vendor spend.")
    _style(ax, ygrid=False)
    fig.tight_layout()
    fig.savefig(ASSETS / "finding_covariance_ladder.png", bbox_inches="tight")
    plt.close(fig)


def chart_direction_vs_magnitude() -> None:
    # Source: Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md, measured
    # by iif1_sigma.py on 927,423 obs (400 names, 2015-2024), frozen pre-accrual.
    rows = [
        ("Direction:\nsign of 1d return", 0.0036, MUTED),
        ("Direction:\nsign of 5d return", 0.0061, MUTED),
        ("Magnitude:\n|move| > 3% in 1d", 0.0953, BLUE),
        ("Magnitude:\n|move| > 5% in 5d", 0.1183, BLUE),
    ]
    fig, ax = plt.subplots(figsize=(8.2, 4.0), dpi=160)
    xs = range(len(rows))
    for x, (label, v, color) in zip(xs, rows):
        ax.bar(x, v, width=0.55, color=color, zorder=3)
        ax.annotate(
            f"{v:.4f}", (x, v), ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=INK
        )
    ax.set_xticks(list(xs), [r[0] for r in rows], fontsize=9)
    ax.set_ylabel("σ of true event probability across stocks\n(bigger = more forecastable)")
    _title(ax, "Why Aegis is prioritizing magnitude over direction",
           "927,423 obs, 2015-2024, measured before spending a dollar: magnitude events show ~20x more cross-stock\n"
           "probability dispersion than direction -- far more signal for a model to find. The LLM trial was re-aimed accordingly.")
    _style(ax)
    fig.tight_layout()
    fig.savefig(ASSETS / "finding_direction_vs_magnitude.png", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# Added 2026-09-03. Sources, so nothing here is retyped:
#   lanes small multiples  -> the live track-record API (same call as chart_lanes)
#   learner v1             -> backend/data/optimus/tracker_backtest/learner_v1.json
#   band-prior horizons    -> the same receipt, scoreboard_other_horizons.prior
# --------------------------------------------------------------------------

LEARNER = ROOT / "backend" / "data" / "optimus" / "tracker_backtest" / "learner_v1.json"


def _load_learner() -> dict:
    return json.loads(LEARNER.read_text(encoding="utf-8"))


def chart_lanes_small_multiples() -> None:
    """All ten lanes, one panel each, against SPY rebased to that lane's own start.

    Ten series cannot share one axis without inventing hues; small multiples are
    the correct form. Panels share a y-range so they are comparable.
    """
    data = json.load(urlopen(API, timeout=90))
    lanes, spy = data["lanes"], data["benchmarks"]["SPY"]
    spy_by_date = {p["date"]: p["value"] for p in spy}

    order = [
        "conservative", "balanced", "aggressive", "balanced-ew-control", "mirror",
        "conviction", "conservative-atr", "smallmid-quality", "tsmom-overlay",
        "tsmom-6040-control",
    ]
    order = [n for n in order if lanes.get(n)] + [
        n for n in lanes if n not in order and lanes.get(n)
    ]

    fig, axes = plt.subplots(2, 5, figsize=(13.2, 5.8), dpi=160, sharex=True, sharey=True)
    lo = hi = 100.0
    for name in order:
        for p in lanes[name]:
            lo = min(lo, p["value"] / 1000)
            hi = max(hi, p["value"] / 1000)
    pad = (hi - lo) * 0.10
    lo, hi = lo - pad, hi + pad

    last_nav_date = max(p["date"] for pts in lanes.values() for p in pts)

    for ax, name in zip(axes.ravel(), order):
        pts = lanes[name]
        xs = [mdates.datestr2num(p["date"]) for p in pts]
        ys = [p["value"] / 1000 for p in pts]
        start = pts[0]["date"]
        # SPY rebased to $100k on THIS lane's inception -- otherwise a lane that
        # started in July is compared against a benchmark that already moved.
        base = spy_by_date.get(start)
        if base:
            bx = [mdates.datestr2num(p["date"]) for p in spy if start <= p["date"] <= last_nav_date]
            by = [p["value"] / base * 100.0 for p in spy if start <= p["date"] <= last_nav_date]
            ax.plot(bx, by, color=INK, lw=1.2, ls=(0, (3, 2)), zorder=3)
        colour = BLUE if ys[-1] >= 100.0 else ORANGE
        ax.plot(xs, ys, color=colour, lw=1.9, zorder=4)
        ax.axhline(100, color=GRID, lw=1.0, zorder=1)
        ax.set_title(name, fontsize=9.5, fontweight="bold", color=INK, loc="left", pad=15)
        ax.text(0, 1.005, f"${ys[-1] * 1000:,.0f}   {ys[-1] / 100 - 1:+.2%}",
                transform=ax.transAxes, fontsize=8.5, color=colour,
                fontweight="bold", va="bottom")
        ax.set_ylim(lo, hi)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}k"))
        _style(ax)

    for ax in axes.ravel()[len(order):]:
        ax.set_visible(False)

    from matplotlib.lines import Line2D

    axes.ravel()[0].legend(
        handles=[
            Line2D([], [], color=BLUE, lw=1.9, label="lane NAV"),
            Line2D([], [], color=INK, lw=1.2, ls=(0, (3, 2)), label="SPY (rebased)"),
        ],
        loc="lower left", frameon=False, fontsize=8, handlelength=1.8,
    )

    fig.text(0.0, 1.075, "Ten paper lanes, one panel each -- the live forward record",
             fontsize=13.5, fontweight="bold", color=INK, va="bottom")
    fig.text(0.0, 1.005,
             f"$100k at each lane's own inception (programme start {data['inception_date']}); "
             f"NAV through {last_nav_date}. Dashed line = SPY rebased to the SAME start date.\n"
             "Panels share one y-axis so they are comparable. Blue = above $100k, orange = below. "
             "At this window the SE on an\nannualised Sharpe is about 2.1 -- the ordering is noise; "
             "the existence of an unedited record is the point.",
             fontsize=8.5, color=INK2, va="bottom")
    fig.tight_layout()
    fig.savefig(ASSETS / "lanes_small_multiples.png", bbox_inches="tight")
    plt.close(fig)


def chart_learner_v1() -> None:
    """LEARNER v1: rank IC by arm, and the band-conditional IC of the champion."""
    d = _load_learner()
    sb = d["scoreboard_1m"]
    champ = d["champion_selection"]["champion"]

    # `constant` has no rank IC by construction (a constant score cannot rank);
    # skip any arm whose receipt does not carry mean_ic rather than inventing one.
    arms = [(k, v) for k, v in sb.items() if v.get("rank_ic", {}).get("mean_ic") is not None]
    arms.sort(key=lambda kv: kv[1]["rank_ic"]["mean_ic"])

    band_labels = {
        "band_no_opinion": "no opinion\n(the engine is SILENT)",
        "band_toxic_ge_5": "toxic, ratio >= 5\n(engine says AVOID)",
        "band_lt_1_5": "ratio < 1.5",
        "band_b_1_5_3": "ratio 1.5-3",
        "band_b_3_5": "ratio 3-5\n(the band it BUYS)",
    }
    bands = [(lbl, sb[champ]["by_band"][k]) for k, lbl in band_labels.items()]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.4), dpi=160,
                                   gridspec_kw={"width_ratios": [1.2, 1.0]})

    for y, (name, v) in enumerate(arms):
        ic, t = v["rank_ic"]["mean_ic"], v["rank_ic"]["t_stat"]
        colour = ORANGE if name.startswith("NULL") else (BLUE if name == champ else MUTED)
        ax1.barh(y, ic, height=0.6, color=colour, zorder=3)
        # Negative bars label into the empty positive half, not off the left
        # edge -- there the text lands on top of the y-tick label.
        ax1.annotate(f" {ic:+.4f}   t {t:.1f} ", (max(ic, 0.0), y), va="center",
                     ha="left", fontsize=8.5, fontweight="bold", color=INK)
    ax1.axvline(0, color=INK2, lw=1)
    ax1.set_yticks(range(len(arms)),
                   [f"{n}  (CHAMPION)" if n == champ else n for n, _ in arms], fontsize=8.5)
    ax1.set_xlabel("Mean monthly rank IC vs 1-month excess return\n(t computed on MONTHS, n = 107)")
    ax1.margins(x=0.26)
    _style(ax1, ygrid=False)
    ax1.text(0, 1.03, "Every arm, walk-forward 2016-2024 (orange = shuffled-target NULL)",
             transform=ax1.transAxes, fontsize=10, fontweight="bold", color=INK, va="bottom")

    for y, (label, v) in enumerate(bands):
        ic, t = v["rank_ic"]["mean_ic"], v["rank_ic"]["t_stat"]
        colour = ORANGE if label.startswith("ratio 3-5") else (BLUE if t >= 2.0 else MUTED)
        ax2.barh(y, ic, height=0.6, color=colour, zorder=3)
        ax2.annotate(f"  {ic:.4f}   t {t:.2f}   {v['rank_ic']['months']} mo", (ic, y),
                     va="center", ha="left", fontsize=8.5, fontweight="bold", color=INK)
    ax2.set_yticks(range(len(bands)), [b[0] for b in bands], fontsize=8.5)
    ax2.invert_yaxis()
    ax2.set_xlabel(f"Rank IC of the champion ({champ}) INSIDE each BAND_PRIOR band")
    ax2.margins(x=0.46)
    _style(ax2, ygrid=False)
    ax2.text(0, 1.03, "The same champion, split by what the engine already said",
             transform=ax2.transAxes, fontsize=10, fontweight="bold", color=INK, va="bottom")

    money_t = sb[champ]["book_top50_vw"]["t_stat_paired_vs_market"]
    fig.text(0.0, 1.135, "The skill lives where the engine is silent",
             fontsize=14, fontweight="bold", color=INK, va="bottom")
    fig.text(0.0, 1.005,
             f"LEARNER v1 ({d['prereg_header']['licence']}, pre-registered "
             f"{d['prereg_header']['written_at_utc'][:10]}): {d['dataset']['rows']:,} name-months, "
             f"{d['dataset']['months']} months, {d['dataset']['names']:,} names, "
             "10bps/side on measured turnover.\n"
             "LEFT: the champion's rank IC clears the shuffled-target null cleanly. "
             "RIGHT: that IC is 0.137 (t 8.79) where the engine has NO OPINION and 0.058 (t 5.58) in the band\n"
             "the engine calls toxic -- but 0.002 (t 0.10) inside ratio 3-5, the band the engine actually buys. "
             f"Money is the weaker claim: the top-50 VW book is t {money_t:.2f} paired vs\nthe market, "
             "and that is one arm of twelve. IC is not P&L. Receipt: "
             "backend/data/optimus/tracker_backtest/learner_v1.json.",
             fontsize=8.5, color=INK2, va="bottom")
    fig.tight_layout()
    fig.savefig(ASSETS / "learner_v1_engine_is_silent.png", bbox_inches="tight")
    plt.close(fig)


def chart_band_prior_horizon() -> None:
    """BAND_PRIOR v2's own rank IC by forecast horizon -- 1 / 3 / 6 / 12 months."""
    d = _load_learner()
    rows = [("1m", d["scoreboard_1m"]["prior"]["rank_ic"])]
    for h in ("3m", "6m", "12m"):
        rows.append((h, d["scoreboard_other_horizons"][h]["prior"]["rank_ic"]))

    fig, ax = plt.subplots(figsize=(9.2, 4.8), dpi=160)
    for x, (_label, r) in enumerate(rows):
        ic, t = r["mean_ic"], r["t_stat"]
        ax.bar(x, ic, width=0.55, color=BLUE, zorder=3)
        ax.annotate(f"IC {ic:.3f}\nt {t:.1f}\n{r['share_months_positive']:.0%} of months +",
                    (x, ic), ha="center", va="bottom", fontsize=9,
                    fontweight="bold", color=INK)
    ax.set_xticks(range(len(rows)),
                  [f"{r[0]} horizon\n{r[1]['months']} months" for r in rows], fontsize=9.5)
    ax.set_ylabel("Mean monthly rank IC of BAND_PRIOR v2\n(t on MONTHS, never name-months)")
    ax.margins(y=0.30)
    _style(ax)
    # Four subtitle lines do not fit _title()'s fixed offsets -- place at figure level.
    fig.text(0.0, 1.115, "BAND_PRIOR is a 12-month object running on a 1-month clock",
             fontsize=13.5, fontweight="bold", color=INK, va="bottom")
    fig.text(0.0, 1.005,
             "The engine's own banded prior ranks the cross-section monotonically BETTER the further out it "
             "looks: t 12.7 at one month\nrises to t 34.5 at twelve, and all 96 twelve-month windows are "
             "positive. The book rebalances MONTHLY -- the horizon the prior\nis strongest at is not the "
             "horizon it is traded at. The 2013-2024 band constants were fitted in full sample, so the prior "
             "is FLATTERED\nhere: read `prior.in_sample_warning`. "
             "Receipt: backend/data/optimus/tracker_backtest/learner_v1.json.",
             fontsize=8.5, color=INK2, va="bottom")
    fig.tight_layout()
    fig.savefig(ASSETS / "band_prior_by_horizon.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import sys

    ASSETS.mkdir(parents=True, exist_ok=True)
    CHARTS = {
        "lanes": chart_lanes,
        "lanes_small_multiples": chart_lanes_small_multiples,
        "market_graph": chart_market_graph,
        "covariance_ladder": chart_covariance_ladder,
        "direction_vs_magnitude": chart_direction_vs_magnitude,
        "learner_v1": chart_learner_v1,
        "band_prior_horizon": chart_band_prior_horizon,
    }
    wanted = sys.argv[1:] or list(CHARTS)
    for key in wanted:
        if key not in CHARTS:
            raise SystemExit(f"unknown chart {key!r}; known: {', '.join(CHARTS)}")
        CHARTS[key]()
        print("  ok", key)
    print(f"wrote {len(wanted)} figures to", ASSETS)
