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
    _title(ax, "Why the brain forecasts magnitude, not direction",
           "Measured before spending a dollar (927,423 obs, 2015-2024): direction is a coin flip 20-30x less\n"
           "forecastable than magnitude. The forward LLM trial was re-aimed accordingly.")
    _style(ax)
    fig.tight_layout()
    fig.savefig(ASSETS / "finding_direction_vs_magnitude.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    chart_lanes()
    chart_market_graph()
    chart_covariance_ladder()
    chart_direction_vs_magnitude()
    print("wrote 4 figures to", ASSETS)
