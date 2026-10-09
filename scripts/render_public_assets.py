"""Render the public visual assets in the owner's chosen language (2026-10-07).

    python -m scripts.render_public_assets            # (re)write every asset
    python -m scripts.render_public_assets --check    # exit 1 if a committed asset differs

Writes
    docs/assets/aegis_loop.svg              1200 x 1000  the front-page hero (style C, the orbit)
    docs/assets/paper_results_live.svg      1200 x 480   best paper accounts, live (style C)
    docs/assets/architecture_pipeline.svg   1200 x 1060  how it works, module by module (style A)
    docs/assets/og_preview.svg              1200 x 630   the social-preview card (style C, static)
    docs/assets/gauntlet.svg                1200 x 666   every idea's gauntlet (style A)
    docs/design/aegis_front_page.html       the HTML motion page: the hero, counting results

THE STYLE
=========
`docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md` is the design record: four styles were shown,
the owner chose C (the orbit) for front pages and A (the blackline HUD) for explanation pages,
and gave the motion notes implemented here -- a dotted orbit whose dots swell and turn blue as a
wave passes, a wave that DWELLS at each stage while that stage's bubble grows, the learning loop
as faint orange inner orbits that spiral into the next cycle, gains in bright blue, no PNGs.

WHY A GENERATOR AND NOT A DRAWING
=================================
The pictures print module paths and live numbers. A hand-drawn picture goes stale silently; here
every path lives in one table (`STAGES`) and every number is read from a PINNED receipt run id
(`RESULTS_RUN_ID`). `backend/tests/test_public_assets.py` fails when a printed path stops
existing, a printed function stops being defined, a printed number differs from its receipt, or
a committed asset is not what this file renders. Refreshing the results is: bump the pin,
re-render, commit.

Stdlib only and deterministic -- no clock, no randomness, LF line ends -- so the same bytes
come out on every run. Everything GitHub shows through <img> is self-contained: CSS keyframes and
SMIL, system font stacks, no script, no external file, no image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "docs" / "assets"
DESIGN = REPO / "docs" / "design"
HERO_SVG = ASSETS / "aegis_loop.svg"
RESULTS_SVG = ASSETS / "paper_results_live.svg"
PIPELINE_SVG = ASSETS / "architecture_pipeline.svg"
OG_SVG = ASSETS / "og_preview.svg"
GAUNTLET_SVG = ASSETS / "gauntlet.svg"
FRONT_HTML = DESIGN / "aegis_front_page.html"
PAPER_DIR = Path(os.getenv("AEGIS_REPO_ROOT", str(REPO))) / "backend" / "data" / "optimus" / "paper_accounts"
REFRESH_DIR = REPO / "backend" / "data" / "optimus" / "paper_accounts"
README = REPO / "README.md"
#: The README's results panel (<img alt=...> + its receipt-citing caption) is generated
#: too (2026-10-07 chunk): `update_readme_results_block` rewrites everything between these
#: two HTML comments and nothing outside them.
RESULTS_BLOCK_START = "<!-- results-panel:start -->"
RESULTS_BLOCK_END = "<!-- results-panel:end -->"

SOURCE_DOC = "docs/AEGIS_V1_BETA_2026-10-07.md"
LIVE_URL = "https://aegis-finance-six.vercel.app"
REPO_URL = "github.com/Murathanx12/Aegis-Finance"
#: SOURCE_DOC §1, first sentence, verbatim (the test checks it is still there).
PRODUCT_SENTENCE = ("Aegis is an open-source investment research system that writes down what it "
                    "believes before an outcome exists, grades every belief against what then "
                    "happens, and lets only graded beliefs change how paper capital is sized.")
#: docs/FUNDING_EVIDENCE_PACK_2026-10-07.md §1, the positioning line.
TAGLINE = "Auditable AI investment intelligence"

#: Layout budgets. SVG text does not wrap and a viewer's font is unknown, so every string is
#: kept inside a width measured for the widest common fallback (DejaVu Sans / Sans Mono).
MAX_TITLE_CHARS = 22
MAX_ABOUT_CHARS = 40
MAX_MODULE_CHARS = 40
MAX_MODULES = 4


# ================================================================== the stage table
@dataclass(frozen=True)
class Module:
    """A repo-relative file that must exist, and names that must be defined in it."""
    path: str
    symbols: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.path + "".join(f" · {s}" for s in self.symbols)

    @property
    def stem(self) -> str:
        return self.path.rsplit("/", 1)[-1].removesuffix(".py")


@dataclass(frozen=True)
class Stage:
    n: int
    title: str                    # what both pictures print
    doc_name: str                 # the stage's name in SOURCE_DOC §2 (carried in <desc>)
    about: tuple[str, str]
    modules: tuple[Module, ...]   # the first two are the orbit's one-line module caption

    @property
    def caption(self) -> str:
        return " · ".join(m.stem for m in self.modules[:2])


M = Module
STAGES: tuple[Stage, ...] = (
    Stage(1, "WORLD SENSORS", "Sensors",
          ("Whole-market news, analyst revisions,", "public flows: spending, lobbying, crypto"),
          (M("scripts/news_pull.py"), M("backend/services/web_reader.py"),
           M("scripts/pull_analyst_targets.py"), M("backend/services/public_flow_common.py"))),
    Stage(2, "EVIDENCE", "Evidence",
          ("An LLM reads what was stored and", "proposes; deterministic code weighs it"),
          (M("backend/services/world_digest.py"), M("backend/services/data_catalog.py"),
           M("backend/services/analyst_reputation.py"))),
    Stage(3, "WORLD STATE / THEORY", "Evidence (world state beliefs) and the theory cells",
          ("Beliefs, scenarios, regimes; every", "theory: mechanism, precursor, falsifier"),
          (M("backend/services/world_state.py"), M("scripts/hyp_theory_cells.py"))),
    Stage(4, "FORECASTS", "Forecasts",
          ("Frozen before the outcome exists,", "graded at 1 / 5 / 21 / 63 sessions"),
          (M("backend/services/belief_state.py"), M("backend/services/forecast_ledger.py"),
           M("scripts/sim_run.py", ("u_forecast",)), M("nn_lab/nightly.py"))),
    Stage(5, "DECISION", "Decision",
          ("Direction and magnitude kept apart;", "risk priced on what it would buy"),
          (M("backend/services/opportunity_funnel.py"), M("backend/services/decision_contract.py"),
           M("scripts/sim_run.py", ("u_rank", "u_plan")), M("backend/services/opportunities.py"))),
    Stage(6, "PAPER ACTION", "Paper execution (a HOLD is an action too)",
          ("Paper only, and a HOLD is a decision.", "No LLM has authority over real capital"),
          (M("backend/services/sim_session.py"), M("scripts/task_keeper.py", ("AegisSimOwner",)),
           M("backend/services/pc_broker.py"))),
    Stage(7, "OUTCOME", "Outcomes",
          ("A daily pass grades what came due", "and reports refusals, never hides them"),
          (M("scripts/daily_pass.py"), M("backend/services/forecast_grader.py"),
           M("scripts/sim_run.py", ("u_grade",)))),
    Stage(8, "ATTRIBUTION", "Attribution (regret)",
          ("Which input did it, and when did we", "know? Regret as signed differences"),
          (M("backend/services/book_dna.py"), M("backend/services/regret_ledger.py"),
           M("backend/services/decision_story.py"))),
    Stage(9, "LEARNING", "Learning",
          ("Only graded outcomes change weights", "and preferences; gates only shrink"),
          (M("backend/services/policy_state.py"), M("backend/services/hyp_lab.py"),
           M("backend/services/expected_return.py"))),
)

#: The two feedback paths. The first is SOURCE_DOC's own dotted edge (LEARNING -> DECISION);
#: the second is `hyp_lab.family_budget`: the family posterior sets each family's share of the
#: next generation round of hypotheses ("a shrink, never a kill").
LOOP_TO_DECISION = "weights + preferences → next cycle"
LOOP_TO_THEORY = "family posterior → next hypothesis round"

# ================================================================== the design tokens
BG = "#000000"
BLUE, BLUE_HI, ORANGE, ORANGE_HI = "#4a8dff", "#6fb0ff", "#ff8a1f", "#ffb36b"
INK2, INK3 = "rgba(255,255,255,.66)", "rgba(255,255,255,.45)"
SANS = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def _t(s: str) -> str:
    return escape(s)


def _num(v: float) -> str:
    """Signed, two decimals, with a true minus sign."""
    return f"{v:+.2f}".replace("-", "−")


def _head(w: int, h: int, title: str, desc: str, css: str, defs: str = "") -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="title desc">',
        f'<title id="title">{_t(title)}</title>',
        f'<desc id="desc">{_t(desc)}</desc>',
        f"<style>{css}{REDUCED}</style>",
        f"<defs>{defs}</defs>",
    ]


def _chips(right: int, y: int, labels: tuple[tuple[str, bool], ...], *, round_: bool) -> list[str]:
    out, x = [], right
    for label, live in reversed(labels):
        w = 26 + len(label) * 8 + (14 if live else 0)
        x -= w
        rx = ' rx="13"' if round_ else ""
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="26"{rx} fill="none" '
                   f'stroke="rgba(255,255,255,.3)"/>')
        tx = x + 13
        if live:
            out.append(f'<circle cx="{x + 15}" cy="{y + 13}" r="4" class="live"/>')
            tx += 14
        out.append(f'<text x="{tx}" y="{y + 17}" class="chip">{label}</text>')
        x -= 10
    return out


# ================================================================== style C: the orbit hero
HERO_W, HERO_H = 1200, 1000
CX, CY, R = 600, 560, 232
TH1 = -50.0                 # stage 1's angle; LEARNING (9) sits at the crown, -90
P, TRAVEL = 2.0, 0.8        # seconds per stage, of which moving (the rest is the dwell)
CYCLE = 9 * P
N_DOTS = 120


def theta(n: int) -> float:
    return TH1 + (n - 1) * 40.0


def _ease(x: float) -> float:                      # easeInOutCubic
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def _inv_ease(y: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _ease(mid) < y else (lo, mid)
    return (lo + hi) / 2


def arrival(n: int) -> float:
    """Seconds into the cycle at which the wave reaches stage n (it leaves LEARNING at 0)."""
    return round(((n - 1) * P + TRAVEL) % CYCLE, 3)


def wave_time(angle: float) -> float:
    """When the wave front passes `angle`: it eases from stage to stage, then dwells."""
    a = (angle - theta(9)) % 360.0
    k = int(a // 40.0)
    return round((k * P + TRAVEL * _inv_ease((a - k * 40.0) / 40.0)) % CYCLE, 3)


def _pos(n: int, r: float = R) -> tuple[float, float]:
    t = math.radians(theta(n))
    return CX + r * math.cos(t), CY + r * math.sin(t)


def _pct(t: float) -> str:
    return f"{100.0 * t / CYCLE:.2f}%"


def _arc(r: float, a0: float, a1: float) -> str:
    """Clockwise arc from angle a0 to a1 (degrees) at radius r."""
    x0, y0 = CX + r * math.cos(math.radians(a0)), CY + r * math.sin(math.radians(a0))
    x1, y1 = CX + r * math.cos(math.radians(a1)), CY + r * math.sin(math.radians(a1))
    large = 1 if ((a1 - a0) % 360) > 180 else 0
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 1 {x1:.1f},{y1:.1f}"


def _hero_css() -> str:
    hold, rel = P - TRAVEL, P - TRAVEL + 0.55
    w = "rgba(255,255,255,.30)"
    return (
        f".bg{{fill:{BG}}}"
        f".kicker{{font:400 12px {MONO};letter-spacing:3.5px;fill:rgba(255,255,255,.55)}}"
        f".lede{{font:400 17px {SANS};fill:rgba(255,255,255,.72)}}"
        f".brand{{font:200 50px {SANS};letter-spacing:16px;fill:#fff}}"
        f".sub{{font:500 11px {MONO};letter-spacing:2px;fill:rgba(255,255,255,.5)}}"
        f".chip{{font:500 11px {MONO};letter-spacing:2px;fill:#fff}}"
        f".live{{fill:{BLUE};animation:live 1.8s ease-out infinite}}"
        "@keyframes live{0%{opacity:1}100%{opacity:.15}}"
        f".sec{{font:700 12px {MONO};letter-spacing:3px;fill:#fff}}"
        ".rule{stroke:rgba(255,255,255,.14)}"
        ".ring0{fill:none;stroke:rgba(255,255,255,.06)}"
        f".dot{{fill:{w};transform-box:fill-box;transform-origin:center;"
        f"animation:swell {CYCLE:g}s linear infinite}}"
        f"@keyframes swell{{0%{{transform:scale(1);fill:{w}}}1.2%{{transform:scale(2.7);fill:{BLUE_HI}}}"
        f"5.5%{{transform:scale(1.25);fill:rgba(74,141,255,.55)}}11%{{transform:scale(1);fill:{w}}}"
        f"100%{{transform:scale(1);fill:{w}}}}}"
        ".node{fill:#000;stroke:rgba(255,255,255,.75);stroke-width:1.5;transform-box:fill-box;"
        f"transform-origin:center;animation:grow {CYCLE:g}s infinite}}"
        ".node.o{animation-name:growo}"
        + "".join(
            f"@keyframes {name}{{0%{{transform:scale(1);fill:#000;stroke:rgba(255,255,255,.75)}}"
            f"2.4%{{transform:scale(1.5);fill:{fill};stroke:{hi}}}"
            f"{_pct(hold - 0.11)}{{transform:scale(1.42);fill:{fill};stroke:{hi}}}"
            f"{_pct(rel)}{{transform:scale(1);fill:#000;stroke:rgba(255,255,255,.75)}}"
            f"100%{{transform:scale(1);fill:#000;stroke:rgba(255,255,255,.75)}}}}"
            for name, fill, hi in (("grow", BLUE, BLUE_HI), ("growo", ORANGE, ORANGE_HI)))
        + f".halo{{fill:none;stroke:{BLUE};stroke-width:1.2;opacity:0;transform-box:fill-box;"
        f"transform-origin:center;animation:halo {CYCLE:g}s ease-out infinite}}"
        f".halo.o{{stroke:{ORANGE}}}"
        "@keyframes halo{0%{opacity:.9;transform:scale(1)}6%{opacity:0;transform:scale(2.6)}"
        "100%{opacity:0;transform:scale(2.6)}}"
        f".nn{{font:600 11px {MONO};fill:#fff}}"
        f".stt{{font:600 14px {SANS};letter-spacing:1.6px;fill:rgba(255,255,255,.88);"
        f"animation:lit {CYCLE:g}s infinite}}"
        ".stt.o{animation-name:lito}"
        + "".join(
            f"@keyframes {name}{{0%{{fill:rgba(255,255,255,.88)}}2.4%{{fill:{hi}}}"
            f"{_pct(hold + 0.18)}{{fill:{hi}}}{_pct(hold + 0.72)}{{fill:rgba(255,255,255,.88)}}"
            f"100%{{fill:rgba(255,255,255,.88)}}}}"
            for name, hi in (("lit", BLUE_HI), ("lito", ORANGE_HI)))
        + f".sd{{font:400 13px {SANS};fill:rgba(255,255,255,.62)}}"
        f".mod{{font:400 11px {MONO};fill:{BLUE}}}"
        f".bar{{fill:{BLUE};transform-box:fill-box;transform-origin:left center;transform:scaleX(0);"
        f"animation:bar {CYCLE:g}s infinite}}"
        ".bar.end{transform-origin:right center}.bar.mid{transform-origin:center}"
        f".bar.o{{fill:{ORANGE}}}"
        f"@keyframes bar{{0%{{transform:scaleX(0)}}3%{{transform:scaleX(1)}}{_pct(hold + 0.18)}"
        f"{{transform:scaleX(1)}}{_pct(hold + 0.72)}{{transform:scaleX(0)}}100%{{transform:scaleX(0)}}}}"
        f".orbit{{fill:none;stroke:{ORANGE};stroke-width:1.3;stroke-dasharray:2 6;opacity:.38}}"
        f".spoke{{fill:none;stroke:{ORANGE};stroke-width:1.3;opacity:.38}}"
        f".olab{{font:500 10.5px {MONO};letter-spacing:1.5px;fill:{ORANGE};opacity:.75}}"
        f".readout{{font:600 12px {MONO};letter-spacing:2.5px;opacity:0;animation:ro {CYCLE:g}s infinite}}"
        f"@keyframes ro{{0%{{opacity:0}}1.5%{{opacity:1}}{_pct(P - 0.18)}{{opacity:1}}{_pct(P)}{{opacity:0}}"
        "100%{opacity:0}}"
        f".foot{{font:400 11px {MONO};letter-spacing:1.5px;fill:rgba(255,255,255,.4)}}"
        "@media (prefers-reduced-motion: reduce){.readout.r1{opacity:1}}"
    )


def _orbit_layers(*, animated: bool, r: float = R) -> list[str]:
    """The inner orbits (learning), the dotted ring, the comets. Shared by the hero and the card."""
    out = []
    r3, r5 = r - 46, r - 76
    t9 = theta(9)
    for rr, n, pid in ((r3, 3, "orb3"), (r5, 5, "orb5")):
        out.append(f'<path id="{pid}" d="{_arc(rr, t9, theta(n) + 360)}" class="orbit"/>')
        x9a, y9a = _pos(9, r - 16)
        x9b, y9b = _pos(9, rr)
        out.append(f'<path d="M{x9a:.1f},{y9a:.1f} L{x9b:.1f},{y9b:.1f}" class="spoke"/>')
        xa, ya = _pos(n, rr)
        xb, yb = _pos(n, r - 17)
        out.append(f'<path d="M{xa:.1f},{ya:.1f} L{xb:.1f},{yb:.1f}" class="spoke" marker-end="url(#ao)"/>')
    out.append('<text class="olab"><textPath href="#orb3" startOffset="9%">NEXT HYPOTHESIS ROUND'
               '</textPath></text>')
    out.append('<text class="olab" dy="-6"><textPath href="#orb5" startOffset="12%">'
               'WEIGHTS + PREFERENCES → NEXT CYCLE</textPath></text>')
    if animated:
        a9 = arrival(9)
        for rr, n, dur in ((r3, 3, 2.2), (r5, 5, 3.0)):
            x9a, y9a = _pos(9, r - 16)
            x9b, y9b = _pos(9, rr)
            xb, yb = _pos(n, r - 17)
            arc = _arc(rr, t9, theta(n) + 360)
            path = f"M{x9a:.1f},{y9a:.1f} L{x9b:.1f},{y9b:.1f} {arc[arc.index('A'):]} L{xb:.1f},{yb:.1f}"
            k1 = dur / CYCLE
            out.append(
                f'<circle r="3.6" fill="{ORANGE}" opacity="0"><animateMotion dur="{CYCLE:g}s" '
                f'begin="{a9:g}s" repeatCount="indefinite" calcMode="linear" keyPoints="0;1;1" '
                f'keyTimes="0;{k1:.4f};1" path="{path}"/><animate attributeName="opacity" '
                f'dur="{CYCLE:g}s" begin="{a9:g}s" repeatCount="indefinite" values="1;1;0;0" '
                f'keyTimes="0;{k1 * .92:.4f};{k1:.4f};1"/></circle>')
    for i in range(N_DOTS):
        a = theta(9) + i * 360.0 / N_DOTS
        if any(abs(((a - theta(n) + 180) % 360) - 180) < 4.5 for n in range(1, 10)):
            continue                                   # room for the stage bubbles
        x, y = CX + r * math.cos(math.radians(a)), CY + r * math.sin(math.radians(a))
        delay = f' style="animation-delay:{wave_time(a):g}s"' if animated else ""
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" class="dot"{delay}/>')
    return out


def render_hero() -> str:
    desc = ("The Aegis loop, nine stages on a ring: "
            + "; ".join(f"{s.n} {s.title.lower()} ({s.caption})" for s in STAGES)
            + ". A wave travels the ring and dwells at each stage while it lights; learning feeds "
              "the next cycle's theory and decision through two inner orbits.")
    defs = (f'<radialGradient id="core" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#0d1a33" '
            f'stop-opacity=".95"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
            f'<marker id="ao" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="{ORANGE}" opacity=".8"/></marker>')
    o = _head(HERO_W, HERO_H, "Aegis: one loop, every belief graded", desc, _hero_css(), defs)
    o.append(f'<rect width="{HERO_W}" height="{HERO_H}" class="bg"/>')
    o.append(f'<text x="40" y="62" class="kicker">{_t(TAGLINE.upper())}</text>')
    o.append('<text x="40" y="100" class="lede">Writes down what it believes before the outcome exists, '
             'grades every belief,</text>')
    o.append('<text x="40" y="124" class="lede">and lets only graded beliefs change how paper capital '
             'is sized.</text>')
    o += _chips(1160, 48, (("LOOP RUNNING", True), ("PAPER ONLY", False), ("OPEN SOURCE", False)),
                round_=True)
    o.append('<text x="40" y="180" class="sec">HOW IT WORKS</text>')
    o.append('<line x1="170" y1="176" x2="1160" y2="176" class="rule"/>')
    o.append(f'<circle cx="{CX}" cy="{CY}" r="{R - 18}" fill="url(#core)"/>')
    o.append(f'<circle cx="{CX}" cy="{CY}" r="{R + 30}" class="ring0"/>')
    o += _orbit_layers(animated=True)
    o.append(f'<text x="{CX + 8}" y="{CY - 6}" class="brand" text-anchor="middle">AEGIS</text>')
    o.append(f'<text x="{CX}" y="{CY + 22}" class="sub" text-anchor="middle">ONE LOOP · EVERY BELIEF '
             f'GRADED</text>')
    for st in STAGES:
        col = ORANGE if st.n == 9 else BLUE_HI
        cls = "readout r1" if st.n == 1 else "readout"
        o.append(f'<text x="{CX}" y="{CY + 58}" class="{cls}" text-anchor="middle" fill="{col}" '
                 f'style="animation-delay:{arrival(st.n):g}s">▸ {st.n:02d}  {_t(st.title)}</text>')
    for st in STAGES:
        x, y = _pos(st.n)
        oc = " o" if st.n == 9 else ""
        dl = f"animation-delay:{arrival(st.n):g}s"
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" class="halo{oc}" style="{dl}"/>')
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" class="node{oc}" style="{dl}"/>')
        o.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" class="nn" text-anchor="middle">{st.n:02d}</text>')
        c = math.cos(math.radians(theta(st.n)))
        if st.n == 9:
            tx, ty, anc = x, y - 96, "middle"
        elif abs(c) < 0.5:
            tx, ty, anc = x + (24 if c > 0 else -24), y + 44, ("start" if c > 0 else "end")
        else:
            tx, ty, anc = x + (32 if c > 0 else -32), y - 26, ("start" if c > 0 else "end")
        o.append(f'<text x="{tx:.1f}" y="{ty:.1f}" class="stt{oc}" text-anchor="{anc}" style="{dl}">'
                 f'{_t(st.title)}</text>')
        tw = len(st.title) * 9.6
        bx = tx if anc == "start" else tx - tw if anc == "end" else tx - tw / 2
        bcls = "bar" + ("" if anc == "start" else " end" if anc == "end" else " mid") + oc
        o.append(f'<rect x="{bx:.1f}" y="{ty + 6:.1f}" width="{tw:.0f}" height="1.6" class="{bcls}" '
                 f'style="{dl}"/>')
        o.append(f'<text x="{tx:.1f}" y="{ty + 25:.1f}" class="sd" text-anchor="{anc}">{_t(st.about[0])}</text>')
        o.append(f'<text x="{tx:.1f}" y="{ty + 42:.1f}" class="sd" text-anchor="{anc}">{_t(st.about[1])}</text>')
        o.append(f'<text x="{tx:.1f}" y="{ty + 61:.1f}" class="mod" text-anchor="{anc}">{_t(st.caption)}</text>')
    o.append(f'<text x="40" y="{HERO_H - 28}" class="foot">{_t(REPO_URL.upper())}</text>')
    o.append(f'<text x="1160" y="{HERO_H - 28}" class="foot" text-anchor="end">EVERY STAGE NAMES THE CODE '
             f'THAT RUNS IT</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ================================================================== the live results
#: The receipt every number on the results panel comes from. Refresh = bump, re-render, commit.
RESULTS_RUN_ID = "2026-10-06T235345Z"
_RESULTS_OVERRIDE: dict | None = None


def snapshot_path(run_id: str) -> Path:
    return ASSETS / f"public_results_{run_id}.json"


def _public_snapshot(d: dict, run_id: str) -> dict:
    """Freeze only reviewed display fields; raw paper receipts remain outside publication."""
    from backend.services.legibility_sanitise import scrub_str  # noqa: PLC0415
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}Z", run_id):
        raise SystemExit("REFUSED: invalid public results run id")

    def string(value: object, limit: int = 160) -> str:
        if (not isinstance(value, str) or len(value) > limit or scrub_str(value) != value or
                "@" in value or any(ord(c) < 32 for c in value)):
            raise SystemExit("REFUSED: public results contain an unsafe or oversized string")
        return value

    def number(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise SystemExit("REFUSED: public results contain a non-finite number")
        return float(value)

    fields = ("family", "account", "name", "kind", "capital", "since", "label")
    numeric = ("roi", "spy", "excess")
    featured = []
    for row in d["featured"]:
        if len(featured) >= len(FEATURED_FAMILIES):
            raise SystemExit("REFUSED: too many featured accounts")
        f = {k: string(row[k]) for k in fields}
        f.update({k: number(row[k]) for k in numeric})
        if not isinstance(row["sessions"], int) or row["sessions"] < 0:
            raise SystemExit("REFUSED: invalid public session count")
        f["sessions"] = row["sessions"]
        tickers = row["tickers"]
        if not isinstance(tickers, list) or len(tickers) > 100:
            raise SystemExit("REFUSED: too many public holdings")
        f["tickers"] = [string(t, 16) for t in tickers]
        f["shares_names_with"] = (string(row["shares_names_with"])
                                  if row["shares_names_with"] is not None else None)
        featured.append(f)
    chart = None
    if d["chart"] is not None:
        raw = d["chart"]
        dates = raw["dates"]
        if not isinstance(dates, list) or len(dates) > 370:
            raise SystemExit("REFUSED: public chart exceeds 370 marks")
        chart = {"account": string(raw["account"]), "twin": string(raw["twin"]),
                 "dates": [string(x, 32) for x in dates]}
        for key in ("acct", "spy", "twin_vals"):
            values = raw[key]
            if not isinstance(values, list) or len(values) != len(dates):
                raise SystemExit("REFUSED: public chart series length mismatch")
            chart[key] = [number(x) for x in values]
    source_paths = [PAPER_DIR / f"roi_{run_id}.json", PAPER_DIR / f"book_dna_{run_id}.json"]
    source_paths += sorted(PAPER_DIR.glob("roi_2026-*.json"))
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dict.fromkeys(source_paths)}
    if not isinstance(d["priced"], int) or d["priced"] < 0:
        raise SystemExit("REFUSED: invalid priced account count")
    display = {"run_id": run_id, "as_of": string(d["as_of"], 32),
               "receipt": f"docs/assets/public_results_{run_id}.json",
               "featured": featured, "chart": chart, "priced": d["priced"]}
    return {"schema": "public_results_render/1", "display": display, "source_sha256": sources}


def _snapshot_display(run_id: str) -> dict | None:
    path = snapshot_path(run_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or set(payload) != {"schema", "display", "source_sha256"} or
            payload.get("schema") != "public_results_render/1" or
            not isinstance(payload.get("display"), dict) or payload["display"].get("run_id") != run_id):
        raise SystemExit("REFUSED: invalid public results snapshot")
    # Apply the same strict public field validation on a clean checkout.
    sources = payload.get("source_sha256")
    if (not isinstance(sources, dict) or
            f"roi_{run_id}.json" not in sources or f"book_dna_{run_id}.json" not in sources or
            any(not re.fullmatch(
                    r"(?:roi_2026-[0-9TZ-]+(?:\.nobroker)?|book_dna_2026-[0-9TZ-]+)\.json",
                    name) or
                not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
                for name, sha in sources.items())):
        raise SystemExit("REFUSED: invalid public snapshot provenance")
    d = payload["display"]
    return _public_display_only(d, run_id)


def _public_display_only(d: dict, run_id: str) -> dict:
    """Validate a committed snapshot without reading or hashing runtime inputs."""
    from backend.services.legibility_sanitise import scrub_str  # noqa: PLC0415
    if not isinstance(d, dict) or set(d) != {"run_id", "as_of", "receipt", "featured", "chart", "priced"}:
        raise SystemExit("REFUSED: public snapshot display keys mismatch")
    if d.get("receipt") != f"docs/assets/public_results_{run_id}.json":
        raise SystemExit("REFUSED: public snapshot receipt mismatch")
    if not isinstance(d.get("featured"), list) or len(d["featured"]) != len(FEATURED_FAMILIES):
        raise SystemExit("REFUSED: public snapshot featured set mismatch")
    def safe(v: object) -> bool:
        if isinstance(v, str):
            return (len(v) <= 160 and v == scrub_str(v) and "@" not in v and
                    not any(ord(c) < 32 for c in v))
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return math.isfinite(v)
        if v is None:
            return True
        if isinstance(v, list):
            return len(v) <= 370 and all(safe(x) for x in v)
        if isinstance(v, dict):
            return all(isinstance(k, str) and safe(k) and safe(x) for k, x in v.items())
        return False
    featured_keys = {"family", "account", "name", "kind", "capital", "since", "label", "roi", "spy",
                     "excess", "sessions", "tickers", "shares_names_with"}
    chart_keys = {"account", "twin", "dates", "acct", "spy", "twin_vals"}
    bad_featured = any(not isinstance(f, dict) or set(f) != featured_keys or
                       not isinstance(f["tickers"], list) or len(f["tickers"]) > 100
                       for f in d["featured"])
    chart = d["chart"]
    bad_chart = chart is not None and (not isinstance(chart, dict) or set(chart) != chart_keys or
                                       any(len(chart[k]) != len(chart["dates"])
                                           for k in ("acct", "spy", "twin_vals")))
    if (not safe(d) or bad_featured or bad_chart or
            not isinstance(d["priced"], int) or d["priced"] < 0 or
            any(not isinstance(f["sessions"], int) or f["sessions"] < 0 for f in d["featured"]) or
            {f["family"] for f in d["featured"]} != {fam for fam, _ in FEATURED_FAMILIES}):
        raise SystemExit("REFUSED: invalid public snapshot display fields")
    return d
#: (family in the receipt, what the panel calls it). The panel shows the BEST STRATEGY account of
#: each, by excess over SPY over its own window; the denominator is printed under it.
FEATURED_FAMILIES: tuple[tuple[str, str], ...] = (
    ("llm_portfolio:personal", "frozen LLM book"),
    ("night_books", "night book"),
    ("alpaca_fleet", "Alpaca paper broker"),
)
#: A name carrying one of these is a control, never a featured result: the random twin of a book,
#: a declared comparator, an equal-weight or sector twin (`__ew`, `__sector_etf`, ...).
CONTROL_MARKERS = ("_random_twin", "comparato", "__")


def _receipt(name: str) -> dict:
    p = PAPER_DIR / name
    if not p.is_file():
        raise SystemExit(f"REFUSED: {_rel(p)} is missing; the results panel "
                         "prints only numbers a committed receipt holds.")
    return json.loads(p.read_text(encoding="utf-8"))


def _money(v: float) -> str:
    return f"${v / 1e6:g}M" if v >= 1e6 else f"${v / 1e3:g}k"


def _series(account: str, upto_utc: str) -> dict[str, tuple[float, float]]:
    """{mark date: (account return %, SPY same-window %)} from every dated roi receipt up to the
    pinned one; when two receipts mark the same date, the later-generated one stands."""
    best: dict[str, tuple[str, float, float]] = {}
    try:
        cutoff_raw = datetime.fromisoformat(upto_utc.replace("Z", "+00:00"))
        if cutoff_raw.tzinfo is None:
            raise ValueError("missing timezone")
        cutoff = cutoff_raw.astimezone(timezone.utc)
    except ValueError:
        raise SystemExit("REFUSED: pinned ROI has an invalid generated_utc") from None
    for p in sorted(PAPER_DIR.glob("roi_2026-*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        gen = str(r.get("generated_utc") or "")
        try:
            raw_instant = datetime.fromisoformat(gen.replace("Z", "+00:00"))
            if raw_instant.tzinfo is None:
                raise ValueError("missing timezone")
            instant = raw_instant.astimezone(timezone.utc)
        except ValueError:
            continue
        if instant > cutoff:
            continue
        for row in r.get("rows") or []:
            if row.get("account") != account or row.get("roi_pct") is None:
                continue
            d = str(row.get("last_mark"))
            stamp = instant.isoformat()
            if d not in best or stamp > best[d][0]:
                best[d] = (stamp, float(row["roi_pct"]), float(row["spy_same_window_pct"]))
    return {d: (v[1], v[2]) for d, v in sorted(best.items())}


def results_data() -> dict:
    if _RESULTS_OVERRIDE is not None:
        return _RESULTS_OVERRIDE
    snapshot = _snapshot_display(RESULTS_RUN_ID)
    if snapshot is not None:
        return snapshot
    roi = _receipt(f"roi_{RESULTS_RUN_ID}.json")
    dna = _receipt(f"book_dna_{RESULTS_RUN_ID}.json")
    dna_by = {b["account"]: b for b in dna.get("books") or []}
    rows = roi["rows"]

    def control(r: dict) -> bool:
        b = dna_by.get(r["account"], {})
        return bool(b.get("twin_of")) or any(m in r["account"] for m in CONTROL_MARKERS)

    featured = []
    for fam, kind in FEATURED_FAMILIES:
        cands = [r for r in rows if r.get("family") == fam and r.get("status") == "LIVE"
                 and r.get("vs_spy_pp") is not None and not control(r)]
        if not cands:
            raise SystemExit(f"REFUSED: no live strategy account in family {fam!r} in roi_{RESULTS_RUN_ID}")
        best = max(cands, key=lambda r: (r["vs_spy_pp"], r["account"]))
        b = dna_by.get(best["account"], {})
        name = (f"night book {str(best.get('book_id', ''))[5:13]}" if fam == "night_books"
                else best["account"])
        featured.append({
            "family": fam, "account": best["account"], "name": name, "kind": kind,
            "capital": _money(float(best["start_capital"])), "since": best["inception"],
            "roi": float(best["roi_pct"]), "spy": float(best["spy_same_window_pct"]),
            "excess": float(best["vs_spy_pp"]),
            "sessions": int(b.get("sessions_graded") or 0),
            "label": str((b.get("evidence") or {}).get("label") or "NOT LABELLED"),
            "tickers": sorted(b.get("tickers") or []),
        })
    # the same names held twice is one bet, not two: say so on the second one
    for i, f in enumerate(featured):
        f["shares_names_with"] = next((g["name"] for g in featured[:i]
                                       if f["tickers"] and g["tickers"] == f["tickers"]), None)
    lead = featured[0]
    twin_name = f"{lead['account']}_random_twin"
    twin_row = next((r for r in rows if r["account"] == twin_name), None)
    chart = None
    if twin_row is not None:
        a = _series(lead["account"], roi["generated_utc"])
        t = _series(twin_name, roi["generated_utc"])
        dates = [d for d in a if d in t]
        chart = {"account": lead["account"], "twin": twin_name, "dates": dates,
                 "acct": [a[d][0] for d in dates], "spy": [a[d][1] for d in dates],
                 "twin_vals": [t[d][0] for d in dates]}
    priced = sum(1 for r in rows if r.get("vs_spy_pp") is not None)
    return {"run_id": RESULTS_RUN_ID, "as_of": str(roi["generated_utc"])[:10],
            "receipt": f"backend/data/optimus/paper_accounts/roi_{RESULTS_RUN_ID}.json",
            "featured": featured, "chart": chart, "priced": priced}


def selection_line(d: dict) -> str:
    return (f"Best strategy account in each of {len(d['featured'])} families (control twins excluded), "
            f"picked after the fact from {d['priced']} priced paper accounts. Paper only; each return "
            f"is over the account's own window, SPY compounded over the same days.")


def _selection_lines(d: dict) -> tuple[str, str]:
    """The selection sentence in two lines of at most ~110 characters (SVG text does not wrap)."""
    head, _, tail = selection_line(d).partition(" Paper only; ")
    return head, "Paper only; " + tail


def _meta(f: dict) -> str:
    return f"{f['kind']} · {f['capital']} paper"


def _meta2(f: dict) -> str:
    return f"since {f['since'][5:]} · {f['sessions']} sessions"


def _shared(f: dict) -> str:
    """The same holdings shown twice are one bet: the second card says whose names it holds."""
    return f"holds the same {len(f['tickers'])} names as {f['shares_names_with']}" if f["shares_names_with"] else ""


RES_W, RES_H = 1200, 470


def _results_css() -> str:
    return (
        f".bg{{fill:{BG}}}"
        f".sec{{font:700 12px {MONO};letter-spacing:3px;fill:#fff}}"
        f".secr{{font:400 11px {MONO};letter-spacing:1.5px;fill:{INK3}}}"
        ".rule{stroke:rgba(255,255,255,.14)}"
        f".live{{fill:{BLUE};animation:live 1.8s ease-out infinite}}"
        "@keyframes live{0%{opacity:1}100%{opacity:.15}}"
        f".excess{{font:300 34px {SANS};fill:{BLUE_HI}}}"
        f".exlab{{font:500 10px {MONO};letter-spacing:1.5px;fill:{BLUE}}}"
        f".acct{{font:600 15px {MONO};fill:#fff}}"
        f".meta{{font:400 12px {SANS};fill:rgba(255,255,255,.58)}}"
        f".badge{{font:500 10px {MONO};letter-spacing:1.5px;fill:{INK3}}}"
        ".track{fill:rgba(255,255,255,.06)}"
        f".bar-acct{{fill:{BLUE}}}.bar-spy{{fill:rgba(255,255,255,.55)}}"
        f".val{{font:600 12px {MONO};fill:#fff}}"
        f".valspy{{font:400 11px {MONO};fill:rgba(255,255,255,.58)}}"
        ".grid{stroke:rgba(255,255,255,.08)}"
        f".zero{{stroke:{INK3};stroke-dasharray:2 3}}"
        f".tick{{font:400 10px {MONO};fill:{INK3}}}"
        f".ln-acct{{fill:none;stroke:{BLUE};stroke-width:2.4;stroke-linejoin:round}}"
        ".ln-spy{fill:none;stroke:#fff;stroke-width:1.4;stroke-dasharray:5 4}"
        f".ln-twin{{fill:none;stroke:{INK3};stroke-width:1.4}}"
        f".pt{{fill:{BG};stroke:{BLUE};stroke-width:1.6}}"
        f".pulse{{fill:none;stroke:{BLUE_HI};stroke-width:1.5}}.pulse-core{{fill:{BLUE_HI}}}"
        f".lab-acct{{font:600 13px {MONO};fill:{BLUE_HI}}}"
        f".lab-spy{{font:400 11px {MONO};fill:#fff}}"
        f".lab-twin{{font:400 11px {MONO};fill:{INK3}}}"
        f".ctitle{{font:600 14px {MONO};fill:#fff}}"
        f".fine{{font:400 11px {SANS};fill:{INK3}}}"
    )


def _chart(d: dict, cx0: float, top: float, cw: float) -> list[str]:
    """The lead account against its matched random twin and SPY, revealed left to right."""
    o: list[str] = []
    c = d["chart"]
    if not c or len(c["dates"]) < 2:
        return o
    lead = d["featured"][0]
    ch, cy0 = 200, top + 22
    o.append(f'<text x="{cx0}" y="{top + 2}" class="ctitle">{_t(lead["name"])} vs its matched random '
             f'twin</text>')
    vals = c["acct"] + c["spy"] + c["twin_vals"]
    ymin = math.floor(min(vals) / 2) * 2
    ymax = math.ceil(max(vals) / 2) * 2
    n = len(c["dates"])

    def X(i: int) -> float:
        return cx0 + 8 + i * (cw - 110) / (n - 1)

    def Y(v: float) -> float:
        return cy0 + 16 + (ymax - v) / (ymax - ymin) * (ch - 16)

    for g in range(ymin, ymax + 1, 2):
        o.append(f'<line x1="{cx0}" y1="{Y(g):.1f}" x2="{cx0 + cw - 96}" y2="{Y(g):.1f}" '
                 f'class="{"zero" if g == 0 else "grid"}"/>')
        lab = "0%" if g == 0 else f"{g:+d}%".replace("-", "−")
        o.append(f'<text x="{cx0 - 8}" y="{Y(g) + 4:.1f}" class="tick" text-anchor="end">{lab}</text>')
    for i, dt in enumerate(c["dates"]):
        o.append(f'<text x="{X(i):.1f}" y="{cy0 + ch + 20}" class="tick" text-anchor="middle">'
                 f'{dt[5:]}</text>')
    o.append(f'<clipPath id="reveal"><rect x="{cx0 - 4}" y="{cy0 - 10}" width="{cw}" height="{ch + 30}">'
             f'<animate attributeName="width" from="0" to="{cw}" dur="2.6s" begin="0s" fill="freeze" '
             f'calcMode="spline" keyTimes="0;1" keySplines="0.25 0.6 0.2 1"/></rect></clipPath>')
    o.append('<g clip-path="url(#reveal)">')
    for cls, vs in (("ln-spy", c["spy"]), ("ln-twin", c["twin_vals"]), ("ln-acct", c["acct"])):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vs))
        o.append(f'<polyline points="{pts}" class="{cls}"/>')
    for i, v in enumerate(c["acct"]):
        o.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" class="pt"/>')
    o.append("</g>")
    lx = X(n - 1)
    a_last, s_last, t_last = c["acct"][-1], c["spy"][-1], c["twin_vals"][-1]
    o.append(f'<circle cx="{lx:.1f}" cy="{Y(a_last):.1f}" r="4" class="pulse">'
             f'<animate attributeName="r" values="4;16" dur="2s" begin="2.6s" repeatCount="indefinite"/>'
             f'<animate attributeName="opacity" values="0.9;0" dur="2s" begin="2.6s" '
             f'repeatCount="indefinite"/></circle>')
    o.append(f'<circle cx="{lx:.1f}" cy="{Y(a_last):.1f}" r="4" class="pulse-core"/>')
    o.append(f'<text x="{lx + 12:.1f}" y="{Y(a_last) + 5:.1f}" class="lab-acct">{_num(a_last)}%</text>')
    o.append(f'<text x="{lx + 12:.1f}" y="{Y(s_last) + 5:.1f}" class="lab-spy">SPY {_num(s_last)}%</text>')
    o.append(f'<text x="{lx + 12:.1f}" y="{Y(t_last) + 9:.1f}" class="lab-twin">twin {_num(t_last)}%</text>')
    ly, lxx = cy0 + ch + 44, cx0
    for cls, lab in (("ln-acct", "account"), ("ln-twin", "matched random twin"),
                     ("ln-spy", "SPY, same window")):
        o.append(f'<line x1="{lxx}" y1="{ly - 4}" x2="{lxx + 22}" y2="{ly - 4}" class="{cls}"/>')
        o.append(f'<text x="{lxx + 30}" y="{ly}" class="meta">{_t(lab)}</text>')
        lxx += 44 + len(lab) * 7
    return o


def render_results() -> str:
    d = results_data()
    desc = (f"Best paper accounts as of {d['as_of']} (receipt {d['receipt']}): "
            + "; ".join(f"{f['name']} {_num(f['roi'])}% vs SPY {_num(f['spy'])}% over its own window, "
                        f"{_num(f['excess'])} pp, {f['label']}" for f in d["featured"])
            + f". {selection_line(d)}")
    o = _head(RES_W, RES_H, "Aegis: best paper accounts, live", desc, _results_css())
    o.append(f'<rect width="{RES_W}" height="{RES_H}" class="bg"/>')
    x, w = 40, 1120
    o.append(f'<circle cx="{x + 5}" cy="40" r="4" class="live"/>')
    o.append(f'<text x="{x + 18}" y="44" class="sec">BEST PAPER ACCOUNTS · LIVE</text>')
    o.append(f'<text x="{x + w}" y="44" class="secr" text-anchor="end">AS OF {d["as_of"]} CLOSE · RECEIPT '
             f'{Path(d["receipt"]).stem}</text>')
    o.append(f'<line x1="{x}" y1="58" x2="{x + w}" y2="58" class="rule"/>')
    top, lw, scale, bx = 88, 600, 200 / 8.0, x + 400
    for i, f in enumerate(d["featured"]):
        ry = top + i * 108
        o.append(f'<text x="{x}" y="{ry + 30}" class="excess">{_num(f["excess"])}</text>')
        o.append(f'<text x="{x + 2}" y="{ry + 50}" class="exlab">PP VS SPY</text>')
        o.append(f'<text x="{x + 120}" y="{ry + 16}" class="acct">{_t(f["name"])}</text>')
        o.append(f'<text x="{x + 120}" y="{ry + 36}" class="meta">{_t(_meta(f))}</text>')
        o.append(f'<text x="{x + 120}" y="{ry + 54}" class="meta">{_t(_meta2(f))}</text>')
        o.append(f'<text x="{x + 120}" y="{ry + 72}" class="badge">{_t(f["label"])}</text>')
        if _shared(f):
            o.append(f'<text x="{x + 120}" y="{ry + 90}" class="meta">{_t(_shared(f))}</text>')
        wa, ws = max(2, round(f["roi"] * scale)), max(2, round(f["spy"] * scale))
        for yy, ww, cls in ((ry + 8, wa, "bar-acct"), (ry + 34, ws, "bar-spy")):
            o.append(f'<rect x="{bx}" y="{yy}" width="{round(8 * scale)}" height="8" class="track" rx="4"/>')
            o.append(f'<rect x="{bx}" y="{yy}" width="{ww}" height="8" class="{cls}" rx="4">'
                     f'<animate attributeName="width" from="0" to="{ww}" dur="1.4s" '
                     f'begin="{0.2 + i * 0.25:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" '
                     f'keySplines="0.2 0.8 0.2 1"/></rect>')
        o.append(f'<text x="{bx + wa + 8}" y="{ry + 16}" class="val">{_num(f["roi"])}%</text>')
        o.append(f'<text x="{bx + ws + 8}" y="{ry + 42}" class="valspy">SPY {_num(f["spy"])}%</text>')
    o += _chart(d, x + lw + 50, top, w - lw - 50)
    l1, l2 = _selection_lines(d)
    o.append(f'<text x="{x}" y="{RES_H - 44}" class="fine">{_t(l1)}</text>')
    o.append(f'<text x="{x}" y="{RES_H - 26}" class="fine">{_t(l2)}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ================================================================== style A: the blackline pipeline
PIPE_W, PIPE_H = 1200, 1060
CW, CH = 350, 216
COLS, ROWS = (40, 425, 810), (214, 480, 746)
GRID = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 2), 5: (1, 1), 6: (1, 0), 7: (2, 0), 8: (2, 1), 9: (2, 2)}
A_CYCLE = 9.0


def _card_xy(n: int) -> tuple[int, int]:
    r, c = GRID[n]
    return COLS[c], ROWS[r]


def _pipeline_css() -> str:
    return (
        f".bg{{fill:{BG}}}"
        f".kicker{{font:400 12px {MONO};letter-spacing:3.5px;fill:rgba(255,255,255,.55)}}"
        f".h1{{font:200 38px {SANS};letter-spacing:6px;fill:#fff}}"
        f".lede{{font:400 15px {SANS};fill:rgba(255,255,255,.7)}}"
        f".chip{{font:500 11px {MONO};letter-spacing:2px;fill:#fff}}"
        f".live{{fill:{BLUE};animation:live 1.8s ease-out infinite}}"
        "@keyframes live{0%{opacity:1}100%{opacity:.15}}"
        f".num{{font:200 34px {SANS};fill:rgba(255,255,255,.28)}}"
        f".stt{{font:600 15px {SANS};letter-spacing:1.8px;fill:#fff}}"
        f".sd{{font:400 14px {SANS};fill:rgba(255,255,255,.7)}}"
        f".mod{{font:400 12px {MONO}}}"
        f".dir{{fill:rgba(255,255,255,.38)}}.file{{fill:{BLUE}}}.sym{{fill:rgba(255,255,255,.72)}}"
        ".frame{fill:rgba(255,255,255,.015);stroke:rgba(255,255,255,.16);stroke-width:1}"
        ".brk{fill:none;stroke:rgba(255,255,255,.75);stroke-width:1.5}"
        f".hl{{fill:none;stroke-width:1.5;opacity:0;animation:hl {A_CYCLE:g}s linear infinite}}"
        f".hl.b{{stroke:{BLUE}}}.hl.o{{stroke:{ORANGE}}}"
        "@keyframes hl{0%{opacity:0}2%{opacity:1}10%{opacity:1}15%{opacity:0}100%{opacity:0}}"
        ".wire{fill:none;stroke:rgba(255,255,255,.22);stroke-width:1}"
        f".flow{{fill:none;stroke:{BLUE};stroke-width:1.6;stroke-dasharray:3 9;"
        "animation:flow 1s linear infinite}"
        "@keyframes flow{to{stroke-dashoffset:-12}}"
        f".loop{{fill:none;stroke:{ORANGE};stroke-width:1.6;stroke-dasharray:6 6;"
        "animation:flow2 1.4s linear infinite}"
        "@keyframes flow2{to{stroke-dashoffset:-24}}"
        f".looplab{{font:500 11px {MONO};letter-spacing:1px;fill:{ORANGE}}}"
        ".rule{stroke:rgba(255,255,255,.18)}"
        f".sec{{font:600 12px {MONO};letter-spacing:3px;fill:#fff}}"
        f".foot{{font:400 11px {MONO};letter-spacing:1.2px;fill:rgba(255,255,255,.45)}}"
    )


def _module_text(m: Module) -> str:
    head, _, tail = m.path.rpartition("/")
    out = f'<tspan class="dir">{_t(head + "/")}</tspan><tspan class="file">{_t(tail)}</tspan>'
    return out + "".join(f'<tspan class="sym"> · {_t(s)}</tspan>' for s in m.symbols)


def render_pipeline() -> str:
    desc = ("How Aegis works, module by module: "
            + "; ".join(f"{s.n} {s.title.lower()} ({s.doc_name} in {SOURCE_DOC} §2): "
                        + ", ".join(m.label for m in s.modules) for s in STAGES)
            + f". Learning feeds the next cycle: {LOOP_TO_DECISION}; {LOOP_TO_THEORY}.")
    defs = ('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
            '<circle cx="1" cy="1" r="1" fill="rgba(255,255,255,.07)"/></pattern>'
            + "".join(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                      f'markerHeight="7" orient="auto"><path d="M0,1 L9,5 L0,9" fill="none" '
                      f'stroke="{col}" stroke-width="1.6"/></marker>'
                      for mid, col in (("ab", BLUE), ("ao", ORANGE))))
    o = _head(PIPE_W, PIPE_H, "How Aegis works, module by module", desc, _pipeline_css(), defs)
    o.append(f'<rect width="{PIPE_W}" height="{PIPE_H}" class="bg"/>'
             f'<rect width="{PIPE_W}" height="{PIPE_H}" fill="url(#dots)"/>')
    for cx_, cy_, dx, dy in ((16, 16, 1, 1), (PIPE_W - 16, 16, -1, 1), (16, PIPE_H - 16, 1, -1),
                             (PIPE_W - 16, PIPE_H - 16, -1, -1)):
        o.append(f'<path d="M{cx_},{cy_ + 14 * dy} L{cx_},{cy_} L{cx_ + 14 * dx},{cy_}" class="brk" '
                 f'style="stroke:rgba(255,255,255,.35)"/>')
    o.append('<text x="40" y="60" class="kicker">AEGIS FINANCE · THE LOOP, MODULE BY MODULE</text>')
    o.append('<text x="36" y="108" class="h1">HOW IT WORKS</text>')
    o.append('<text x="40" y="142" class="lede">Language models read the world and propose; deterministic '
             'code ranks, sizes, stops and exits. Paper only.</text>')
    o += _chips(1160, 40, (("ONE CYCLE PER SESSION", True), ("9 STAGES", False)), round_=False)
    o.append('<line x1="40" y1="176" x2="1160" y2="176" class="rule"/>')
    # wires first (under the cards)
    for a in range(1, 9):
        (ax, ay), (bx, by) = _card_xy(a), _card_xy(a + 1)
        if ay == by:
            x1, x2 = (ax + CW, bx) if bx > ax else (ax, bx + CW)
            y1 = y2 = ay + CH // 2
        else:
            x1 = x2 = ax + CW // 2
            y1, y2 = ay + CH, by
        o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="wire"/>')
        ex = x2 - (6 if x2 > x1 else -6 if x2 < x1 else 0)
        ey = y2 - (6 if y2 > y1 else 0)
        o.append(f'<line x1="{x1}" y1="{y1}" x2="{ex}" y2="{ey}" class="flow" marker-end="url(#ab)"/>')
    for st in STAGES:
        x, y = _card_xy(st.n)
        o.append(f'<g id="stage-{st.n}">')
        o.append(f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" class="frame"/>')
        for bx_, by_, dx, dy in ((x, y, 1, 1), (x + CW, y, -1, 1), (x, y + CH, 1, -1), (x + CW, y + CH, -1, -1)):
            o.append(f'<path d="M{bx_},{by_ + 12 * dy} L{bx_},{by_} L{bx_ + 12 * dx},{by_}" class="brk"/>')
        o.append(f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" class="hl {"o" if st.n == 9 else "b"}" '
                 f'style="animation-delay:{st.n - 1}s"/>')
        o.append(f'<text x="{x + 20}" y="{y + 46}" class="num">{st.n:02d}</text>')
        o.append(f'<text x="{x + 76}" y="{y + 41}" class="stt">{_t(st.title)}</text>')
        o.append(f'<text x="{x + 20}" y="{y + 78}" class="sd">{_t(st.about[0])}</text>')
        o.append(f'<text x="{x + 20}" y="{y + 99}" class="sd">{_t(st.about[1])}</text>')
        o.append(f'<line x1="{x + 20}" y1="{y + 117}" x2="{x + CW - 20}" y2="{y + 117}" '
                 f'stroke="rgba(255,255,255,.08)"/>')
        for i, m in enumerate(st.modules):
            o.append(f'<text x="{x + 20}" y="{y + 140 + 19 * i}" class="mod">{_module_text(m)}</text>')
        o.append("</g>")
    x9, y9 = _card_xy(9)
    x5, y5 = _card_xy(5)
    x3, y3 = _card_xy(3)
    gy = y5 + CH + 25
    to5 = f"M{x9 + 60},{y9} L{x9 + 60},{gy} L{x5 + CW - 60},{gy} L{x5 + CW - 60},{y5 + CH + 4}"
    o.append(f'<path d="{to5}" class="loop" marker-end="url(#ao)"/>')
    o.append(f'<text x="{x5 + CW - 48}" y="{gy - 6}" class="looplab">{_t(LOOP_TO_DECISION)}</text>')
    o.append(f'<path d="M{x9 + CW},{y9 + 40} L{x9 + CW + 22},{y9 + 40} L{x9 + CW + 22},{y3 + 40} '
             f'L{x3 + CW + 4},{y3 + 40}" class="loop" marker-end="url(#ao)"/>')
    o.append(f'<text x="{x3 + CW - 8}" y="{y3 - 10}" class="looplab" text-anchor="end">↺ '
             f'{_t(LOOP_TO_THEORY)}</text>')
    o.append(f'<circle r="3.5" fill="{ORANGE}"><animateMotion dur="3s" repeatCount="indefinite" '
             f'path="M{x9 + 60},{y9} L{x9 + 60},{gy} L{x5 + CW - 60},{gy} L{x5 + CW - 60},{y5 + CH}"/></circle>')
    fy = ROWS[2] + CH + 40
    o.append(f'<line x1="40" y1="{fy - 18}" x2="1160" y2="{fy - 18}" class="rule"/>')
    o.append(f'<text x="40" y="{fy + 4}" class="foot">BLUE: ONE CYCLE, STAGE TO STAGE · ORANGE: WHAT THE '
             f'NEXT CYCLE INHERITS · EVERY PATH IS CHECKED BY backend/tests/test_public_assets.py</text>')
    o.append(f'<text x="40" y="{fy + 26}" class="foot">STAGE NAMES AND MODULES: {SOURCE_DOC} §2 · '
             f'{_t(REPO_URL.upper())}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ================================================================== style A: the gauntlet
GAUNT_W, GAUNT_H = 1200, 666
#: The README's own flowchart, node for node and word for word ("Every idea walks the same
#: gauntlet"); the count of prior trials is the README's. Re-skinned, not re-argued.
PRIOR_TRIALS = "335+"
GAUNTLET_NODES = {
    "IDEA": ("IDEA", ()),
    "PREREG": ("PRE-REGISTRATION", ("frozen in a commit", "BEFORE any data")),
    "RUN": ("RUN", ("every arm prints its", "own 80%-power MDE")),
    "FWD": ("FORWARD PAPER LANE", ("reality decides,", "24-month clock")),
    "DEAD": ("REFUSED", ("it already has", "a corpse")),
    "VOID": ("VOID", ("disclosed with its", "numbers, never deleted")),
    "NR": ("NEGATIVE_RESULTS.md", ("NOT_DETECTABLE",)),
}
GAUNTLET_GATES = {
    "CORPSE": (("CORPSE", "CHECK"), f"vs {PRIOR_TRIALS} prior trials"),
    "PLACEBO": (("PLACEBOS", "CLEAN?"), ""),
    "BAR": (("CLEARS", "OWN MDE?"), ""),
}
GAUNTLET_EDGES = (("CORPSE", "DEAD", "match found"), ("CORPSE", "PREREG", "pass"),
                  ("PLACEBO", "VOID", "no"), ("PLACEBO", "BAR", "yes"),
                  ("BAR", "NR", "no"), ("BAR", "FWD", "yes"))
GAUNTLET_LOOP = "every refusal, void and null is a record the next corpse check reads"


def render_gauntlet() -> str:
    css = _pipeline_css() + (
        f".gt{{font:600 12px {MONO};letter-spacing:1.6px;fill:#fff}}"
        f".gt.dim{{fill:rgba(255,255,255,.6)}}.gt.go{{fill:{BLUE_HI}}}"
        f".gd{{font:400 13px {SANS};fill:rgba(255,255,255,.68)}}"
        f".gd.dim{{fill:rgba(255,255,255,.48)}}"
        f".gate{{font:600 10.5px {MONO};letter-spacing:1.2px;fill:#fff}}"
        f".cap{{font:400 11px {MONO};fill:rgba(255,255,255,.5)}}"
        f".elab{{font:500 10px {MONO};letter-spacing:1px;fill:rgba(255,255,255,.55)}}"
        ".dead{fill:rgba(255,255,255,.01);stroke:rgba(255,255,255,.12);stroke-width:1}"
        f".go-frame{{fill:rgba(74,141,255,.06);stroke:{BLUE};stroke-width:1.5}}"
        ".diamond{fill:#000;stroke:rgba(255,255,255,.75);stroke-width:1.5}"
        ".ideap{fill:#000;stroke:rgba(255,255,255,.75);stroke-width:1.5}")
    defs = ('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
            '<circle cx="1" cy="1" r="1" fill="rgba(255,255,255,.07)"/></pattern>'
            + "".join(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                      f'markerHeight="7" orient="auto"><path d="M0,1 L9,5 L0,9" fill="none" '
                      f'stroke="{col}" stroke-width="1.6"/></marker>'
                      for mid, col in (("ab", BLUE), ("aw", "rgba(255,255,255,.5)"), ("ao", ORANGE))))
    desc = ("Every idea walks the same gauntlet: " + "; ".join(
        f"{a.lower()} to {b.lower()}" + (f" ({lab})" if lab else "") for a, b, lab in GAUNTLET_EDGES)
        + f". The corpse check compares against {PRIOR_TRIALS} prior trials; {GAUNTLET_LOOP}.")
    o = _head(GAUNT_W, GAUNT_H, "Every idea walks the same gauntlet", desc, css, defs)
    o.append(f'<rect width="{GAUNT_W}" height="{GAUNT_H}" class="bg"/>'
             f'<rect width="{GAUNT_W}" height="{GAUNT_H}" fill="url(#dots)"/>')
    for cx_, cy_, dx, dy in ((16, 16, 1, 1), (GAUNT_W - 16, 16, -1, 1), (16, GAUNT_H - 16, 1, -1),
                             (GAUNT_W - 16, GAUNT_H - 16, -1, -1)):
        o.append(f'<path d="M{cx_},{cy_ + 14 * dy} L{cx_},{cy_} L{cx_ + 14 * dx},{cy_}" class="brk" '
                 f'style="stroke:rgba(255,255,255,.35)"/>')
    o.append('<text x="40" y="60" class="kicker">AEGIS FINANCE · THE HONESTY MACHINE</text>')
    o.append('<text x="36" y="104" class="h1" style="font-size:32px">EVERY IDEA WALKS THE SAME GAUNTLET</text>')
    o.append('<text x="40" y="136" class="lede">Most die, cheaply and on the record. Only what survives every '
             'gate reaches a forward paper lane.</text>')
    o.append('<line x1="40" y1="166" x2="1160" y2="166" class="rule"/>')
    cy = 290                                     # the spine
    box_h = 104
    spine = {"IDEA": (40, 120), "CORPSE": (150, 270), "PREREG": (300, 460), "RUN": (490, 650),
             "PLACEBO": (680, 790), "BAR": (820, 930), "FWD": (960, 1160)}
    low = {"DEAD": (115, 305), "VOID": (590, 770), "NR": (800, 1010)}
    ly = 446                                     # top of the dead-end row
    # wires first
    order = ["IDEA", "CORPSE", "PREREG", "RUN", "PLACEBO", "BAR", "FWD"]
    for a, b in zip(order, order[1:]):
        x1, x2 = spine[a][1], spine[b][0]
        o.append(f'<line x1="{x1}" y1="{cy}" x2="{x2}" y2="{cy}" class="wire"/>')
        o.append(f'<line x1="{x1}" y1="{cy}" x2="{x2 - 6}" y2="{cy}" class="flow" marker-end="url(#ab)"/>')
    labels = {(a, b): lab for a, b, lab in GAUNTLET_EDGES}
    for (a, b), lab in labels.items():
        if b in spine:
            x1, x2 = spine[a][1], spine[b][0]
            o.append(f'<text x="{(x1 + x2) / 2:.0f}" y="{cy - 10}" class="elab" text-anchor="middle">{_t(lab)}</text>')
        else:
            gx = (spine[a][0] + spine[a][1]) / 2
            bx = (low[b][0] + low[b][1]) / 2
            half = (spine[a][1] - spine[a][0]) / 2
            y1 = cy + half
            mid = (y1 + ly) / 2
            d = (f"M{gx:.0f},{y1:.0f} L{gx:.0f},{mid:.0f} L{bx:.0f},{mid:.0f} L{bx:.0f},{ly - 6}"
                 if abs(gx - bx) > 1 else f"M{gx:.0f},{y1:.0f} L{gx:.0f},{ly - 6}")
            o.append(f'<path d="{d}" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.2" '
                     f'stroke-dasharray="3 5" marker-end="url(#aw)"/>')
            o.append(f'<text x="{gx + 8:.0f}" y="{y1 + 20:.0f}" class="elab">{_t(lab)}</text>')
    # the idea
    x0, x1 = spine["IDEA"]
    o.append(f'<rect x="{x0}" y="{cy - 26}" width="{x1 - x0}" height="52" rx="26" class="ideap"/>')
    o.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{cy + 4}" class="gt" text-anchor="middle">IDEA</text>')
    # gates (diamonds)
    for g, (lines, cap) in GAUNTLET_GATES.items():
        gx0, gx1 = spine[g]
        gx, h = (gx0 + gx1) / 2, (gx1 - gx0) / 2
        o.append(f'<path d="M{gx:.0f},{cy - h:.0f} L{gx1},{cy} L{gx:.0f},{cy + h:.0f} L{gx0},{cy} Z" '
                 f'class="diamond"/>')
        o.append(f'<text x="{gx:.0f}" y="{cy - 3}" class="gate" text-anchor="middle">{_t(lines[0])}</text>')
        o.append(f'<text x="{gx:.0f}" y="{cy + 11}" class="gate" text-anchor="middle">{_t(lines[1])}</text>')
        if cap:
            o.append(f'<text x="{gx:.0f}" y="{cy - h - 12:.0f}" class="cap" text-anchor="middle">{_t(cap)}</text>')

    def box(key: str, x0: int, x1: int, y0: int, kind: str) -> None:
        title, lines = GAUNTLET_NODES[key]
        frame = {"go": "go-frame", "dead": "dead", "step": "frame"}[kind]
        o.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{box_h}" class="{frame}"/>')
        if kind != "dead":
            for bx_, by_, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y0 + box_h, 1, -1),
                                     (x1, y0 + box_h, -1, -1)):
                o.append(f'<path d="M{bx_},{by_ + 12 * dy} L{bx_},{by_} L{bx_ + 12 * dx},{by_}" class="brk"'
                         + (f' style="stroke:{BLUE_HI}"' if kind == "go" else "") + "/>")
        tcls = {"go": "gt go", "dead": "gt dim", "step": "gt"}[kind]
        dcls = "gd dim" if kind == "dead" else "gd"
        o.append(f'<text x="{x0 + 16}" y="{y0 + 30}" class="{tcls}">{_t(title)}</text>')
        for i, ln in enumerate(lines):
            o.append(f'<text x="{x0 + 16}" y="{y0 + 56 + 19 * i}" class="{dcls}">{_t(ln)}</text>')

    for key, kind in (("PREREG", "step"), ("RUN", "step"), ("FWD", "go")):
        x0_, x1_ = spine[key]
        box(key, x0_, x1_, cy - box_h // 2, kind)
    for key, (x0_, x1_) in low.items():
        box(key, x0_, x1_, ly, "dead")
    # the learning loop: the record feeds the next corpse check
    by = ly + box_h + 30
    dx_ = (low["DEAD"][0] + low["DEAD"][1]) / 2
    loop = (f"M{(low['NR'][0] + low['NR'][1]) / 2:.0f},{ly + box_h} L{(low['NR'][0] + low['NR'][1]) / 2:.0f},{by} "
            f"L{40 + 20},{by} L{40 + 20},{ly - 40} L{spine['CORPSE'][0] - 6},{ly - 40} "
            f"L{spine['CORPSE'][0] + 30},{cy + 34}")
    o.append(f'<path d="{loop}" class="loop" marker-end="url(#ao)"/>')
    for key in ("VOID", "DEAD"):
        x = (low[key][0] + low[key][1]) / 2
        o.append(f'<path d="M{x:.0f},{ly + box_h} L{x:.0f},{by}" class="loop"/>')
    o.append(f'<text x="{dx_ + 120:.0f}" y="{by + 20}" class="looplab">↺ {_t(GAUNTLET_LOOP)}</text>')
    o.append(f'<circle r="3.5" fill="{ORANGE}"><animateMotion dur="6s" repeatCount="indefinite" '
             f'path="{loop}"/></circle>')
    o.append(f'<text x="40" y="{GAUNT_H - 28}" class="foot">PRE-REGISTRATION: docs/TRIALS/ · THE RECORD: '
             f'NEGATIVE_RESULTS.md · NOTHING IS DELETED</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ================================================================== the social card (static)
OG_W, OG_H = 1200, 630
OG_DESC_LINES = 5
OG_DESC_CHARS = 48


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap (no hyphenation); a word longer than `width` gets its own line."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


def render_og() -> str:
    desc = wrap(PRODUCT_SENTENCE, OG_DESC_CHARS)
    if len(desc) > OG_DESC_LINES:
        raise ValueError(f"the product sentence wraps to {len(desc)} lines; the card holds {OG_DESC_LINES}")
    css = (f".bg{{fill:{BG}}}"
           f".kicker{{font:400 13px {MONO};letter-spacing:3.5px;fill:rgba(255,255,255,.6)}}"
           f".brand{{font:200 84px {SANS};letter-spacing:24px;fill:#fff}}"
           f".fin{{font:500 15px {MONO};letter-spacing:9px;fill:{BLUE_HI}}}"
           f".d{{font:400 22px {SANS};fill:rgba(255,255,255,.78)}}"
           f".url{{font:500 19px {MONO};fill:{BLUE_HI}}}"
           f".meta{{font:400 13px {MONO};letter-spacing:2px;fill:rgba(255,255,255,.5)}}"
           ".dot{fill:rgba(255,255,255,.34)}"
           ".node{fill:#000;stroke:rgba(255,255,255,.8);stroke-width:1.5}"
           f".node.o{{stroke:{ORANGE}}}.node.a{{fill:{BLUE};stroke:{BLUE_HI}}}"
           f".nn{{font:600 10px {MONO};fill:#fff}}"
           f".orbit{{fill:none;stroke:{ORANGE};stroke-width:1.2;stroke-dasharray:2 5;opacity:.45}}"
           f".core{{font:200 22px {SANS};letter-spacing:7px;fill:#fff}}"
           f".csub{{font:500 9px {MONO};letter-spacing:2px;fill:rgba(255,255,255,.55)}}")
    o = _head(OG_W, OG_H, "AEGIS Finance",
              f"AEGIS Finance. {TAGLINE}. {PRODUCT_SENTENCE} {LIVE_URL}", css)
    o.append(f'<rect width="{OG_W}" height="{OG_H}" class="bg"/>')
    o.append(f'<text x="72" y="96" class="kicker">{_t(TAGLINE.upper())}</text>')
    o.append('<text x="64" y="196" class="brand">AEGIS</text>')
    o.append('<text x="74" y="232" class="fin">FINANCE</text>')
    for i, ln in enumerate(desc):
        lines_y = 296 + 34 * i
        o.append(f'<text x="72" y="{lines_y}" class="d">{_t(ln)}</text>')
    o.append(f'<text x="72" y="{OG_H - 70}" class="url">{_t(LIVE_URL)}</text>')
    o.append(f'<text x="72" y="{OG_H - 40}" class="meta">OPEN SOURCE (MIT) · PAPER ONLY · '
             f'{_t(REPO_URL.upper())}</text>')
    # the orbit, in miniature and still: nine stages, LEARNING at the crown, its inner orbits
    ox, oy, orr = 930, 320, 180

    def p(n: int, r: float) -> tuple[float, float]:
        t = math.radians(theta(n))
        return ox + r * math.cos(t), oy + r * math.sin(t)

    for rr, n in ((orr - 38, 3), (orr - 62, 5)):
        a0, a1 = theta(9), theta(n) + 360
        x0, y0 = ox + rr * math.cos(math.radians(a0)), oy + rr * math.sin(math.radians(a0))
        x1, y1 = ox + rr * math.cos(math.radians(a1)), oy + rr * math.sin(math.radians(a1))
        large = 1 if ((a1 - a0) % 360) > 180 else 0
        o.append(f'<path d="M{x0:.1f},{y0:.1f} A{rr},{rr} 0 {large} 1 {x1:.1f},{y1:.1f}" class="orbit"/>')
    for i in range(96):
        a = theta(9) + i * 3.75
        if any(abs(((a - theta(n) + 180) % 360) - 180) < 5.5 for n in range(1, 10)):
            continue
        x, y = ox + orr * math.cos(math.radians(a)), oy + orr * math.sin(math.radians(a))
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" class="dot"/>')
    for st in STAGES:
        x, y = p(st.n, orr)
        cls = "node o" if st.n == 9 else "node a" if st.n == 5 else "node"
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" class="{cls}"/>')
        o.append(f'<text x="{x:.1f}" y="{y + 3.5:.1f}" class="nn" text-anchor="middle">{st.n:02d}</text>')
    o.append(f'<text x="{ox + 4}" y="{oy + 4}" class="core" text-anchor="middle">LOOP</text>')
    o.append(f'<text x="{ox}" y="{oy + 24}" class="csub" text-anchor="middle">EVERY BELIEF GRADED</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ================================================================== the HTML motion page
CHART_W, CHART_H = 640, 300


def render_chart() -> str:
    """The results chart alone (the HTML page draws its cards natively)."""
    d = results_data()
    o = _head(CHART_W, CHART_H, f"{d['featured'][0]['name']} vs its matched random twin",
              f"Daily marks from the dated receipts up to roi_{d['run_id']}.", _results_css())
    o.append(f'<rect width="{CHART_W}" height="{CHART_H}" class="bg"/>')
    o += _chart(d, 48, 24, CHART_W - 48)
    o.append("</svg>")
    return "\n".join(o) + "\n"


def _inline(svg: str, prefix: str) -> str:
    """An SVG for inline use in a page that holds two: its fixed size dropped (CSS sizes it to
    the column) and every id prefixed, with every reference to one, so no two collide."""
    import re
    svg = re.sub(r'<svg ([^>]*?)width="\d+" height="\d+" ', r"<svg \1", svg, count=1)
    ids = re.findall(r'\sid="([^"]+)"', svg)
    for i in sorted(set(ids), key=len, reverse=True):
        svg = (svg.replace(f'id="{i}"', f'id="{prefix}{i}"').replace(f"url(#{i})", f"url(#{prefix}{i})")
               .replace(f'href="#{i}"', f'href="#{prefix}{i}"'))
    return svg.replace('aria-labelledby="title desc"', f'aria-labelledby="{prefix}title {prefix}desc"', 1)


def render_front_html() -> str:
    d = results_data()
    hero = _inline(render_hero(), "h-")
    cards = []
    for f in d["featured"]:
        width_a = min(100.0, max(1.0, f["roi"] / 8.0 * 100))
        width_s = min(100.0, max(1.0, f["spy"] / 8.0 * 100))
        cards.append(
            f'<article class="fp-card"><div class="fp-ex" data-to="{f["excess"]:.2f}">{_num(f["excess"])}</div>'
            f'<div class="fp-exl">pp vs SPY</div><h3>{_t(f["name"])}</h3>'
            f'<p class="fp-meta">{_t(_meta(f))}<br>{_t(_meta2(f))}'
            + (f'<br>{_t(_shared(f))}' if _shared(f) else "") + '</p>'
            f'<div class="fp-bars"><div class="fp-bar"><span class="a" style="--w:{width_a:.1f}%"></span>'
            f'<b>{_num(f["roi"])}%</b></div><div class="fp-bar"><span class="s" style="--w:{width_s:.1f}%">'
            f'</span><b>SPY {_num(f["spy"])}%</b></div></div><p class="fp-badge">{_t(f["label"])}</p></article>')
    chart_svg = _inline(render_chart(), "c-")
    css = f"""
:root{{--bg:#000;--ink:#fff;--ink2:rgba(255,255,255,.7);--ink3:rgba(255,255,255,.45);
--line:rgba(255,255,255,.14);--blue:{BLUE};--blue-hi:{BLUE_HI};--orange:{ORANGE}}}
*{{box-sizing:border-box;margin:0}}
html,body{{background:var(--bg);color:var(--ink)}}
body{{font:16px/1.55 {SANS};padding:0 16px 80px}}
main{{max-width:1200px;margin:0 auto}}
.fp-hero svg,.fp-chart svg{{display:block;width:100%;height:auto}}
.fp-k{{font:600 12px {MONO};letter-spacing:3px;text-transform:uppercase;color:var(--ink);
display:flex;align-items:center;gap:10px;margin:48px 0 18px}}
.fp-k i{{width:8px;height:8px;border-radius:50%;background:var(--blue);animation:fp-live 1.8s ease-out infinite}}
.fp-k span{{flex:1;height:1px;background:var(--line)}}
.fp-k em{{font:400 11px {MONO};letter-spacing:1.5px;color:var(--ink3);font-style:normal;text-transform:none}}
@keyframes fp-live{{0%{{opacity:1}}100%{{opacity:.15}}}}
.fp-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
@media (max-width:820px){{.fp-grid{{grid-template-columns:1fr}}}}
.fp-card{{position:relative;border:1px solid var(--line);padding:22px 22px 18px;
background:rgba(255,255,255,.015)}}
.fp-card::before,.fp-card::after{{content:"";position:absolute;width:12px;height:12px;
border-color:rgba(255,255,255,.75);border-style:solid}}
.fp-card::before{{left:-1px;top:-1px;border-width:1.5px 0 0 1.5px}}
.fp-card::after{{right:-1px;bottom:-1px;border-width:0 1.5px 1.5px 0}}
.fp-ex{{font:300 44px/1 {SANS};color:var(--blue-hi);font-variant-numeric:tabular-nums}}
.fp-exl{{font:500 10px {MONO};letter-spacing:1.5px;text-transform:uppercase;color:var(--blue);margin:6px 0 14px}}
.fp-card h3{{font:600 15px {MONO};margin-bottom:4px}}
.fp-meta{{font-size:13px;color:var(--ink2)}}
.fp-bars{{margin:14px 0 10px;display:grid;gap:8px}}
.fp-bar{{display:flex;align-items:center;gap:10px;font:12px {MONO};color:var(--ink2)}}
.fp-bar span{{height:8px;border-radius:4px;width:0;transition:width 1.4s cubic-bezier(.2,.8,.2,1)}}
.fp-bar span.a{{background:var(--blue)}}.fp-bar span.s{{background:rgba(255,255,255,.55)}}
.fp-on .fp-bar span{{width:calc(var(--w) * .6)}}
.fp-badge{{font:500 10px {MONO};letter-spacing:1.5px;color:var(--ink3)}}
.fp-fine{{font-size:12px;color:var(--ink3);margin-top:14px}}
.fp-chart{{margin-top:22px;max-width:760px}}
@media (prefers-reduced-motion: reduce){{*{{animation:none!important;transition:none!important}}}}
"""
    js = """
(function(){
  var root=document.documentElement;
  var still=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function fmt(v){return (v<0?'\\u2212':'+')+Math.abs(v).toFixed(2);}
  function run(){
    root.classList.add('fp-on');
    if(still){return;}
    var els=document.querySelectorAll('[data-to]');
    var t0=null,D=1400;
    function step(t){
      if(t0===null){t0=t;}
      var k=Math.min(1,(t-t0)/D),e=1-Math.pow(1-k,3);
      for(var i=0;i<els.length;i++){els[i].textContent=fmt(parseFloat(els[i].getAttribute('data-to'))*e);}
      if(k<1){requestAnimationFrame(step);}
    }
    requestAnimationFrame(step);
  }
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',run);}else{run();}
})();
"""
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Aegis — one loop, every belief graded</title>\n"
        f"<meta name=\"description\" content=\"{_t(PRODUCT_SENTENCE)}\">\n"
        f"<style>{css}</style>\n</head>\n<body>\n<main>\n"
        f"<section class=\"fp-hero\" aria-label=\"How it works\">\n{hero}</section>\n"
        f"<section aria-label=\"Best paper accounts, live\">\n"
        f"<h2 class=\"fp-k\"><i></i>Best paper accounts · live<span></span>"
        f"<em>as of {d['as_of']} close · receipt roi_{d['run_id']}</em></h2>\n"
        f"<div class=\"fp-grid\">{''.join(cards)}</div>\n"
        f"<p class=\"fp-fine\">{_t(selection_line(d))}</p>\n"
        f"<div class=\"fp-chart\">{chart_svg}</div>\n</section>\n"
        f"</main>\n<script>{js}</script>\n</body>\n</html>\n"
    )


# ================================================================== the pin bump
#: `python -m scripts.render_public_assets --bump-pin [RUN_ID]` (2026-10-07 chunk): pick the
#: newest roi/book_dna receipt pair, rewrite RESULTS_RUN_ID in THIS file, re-render every
#: asset + the README results block, and write a refresh receipt. Refuses (exit 2, nothing
#: written) when the newest pair is not strictly newer than the pinned one, a featured family
#: has no LIVE strategy account, or a text budget fails.
PIN_RE = re.compile(r'(?m)^RESULTS_RUN_ID = "([^"]*)"$')


def _generated_utc_of(run_id: str) -> str:
    """The roi receipt's own `generated_utc`, or "" when it cannot be read (never a file stamp)."""
    p = PAPER_DIR / f"roi_{run_id}.json"
    if not p.is_file():
        return ""
    try:
        raw = str(json.loads(p.read_text(encoding="utf-8")).get("generated_utc") or "")
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc).isoformat() if stamp.tzinfo else ""
    except (OSError, ValueError):
        return ""


def _candidate_run_ids() -> list[str]:
    """Every run id with BOTH roi_<id>.json and book_dna_<id>.json and a readable
    `generated_utc`, oldest to newest by that stamp (never by file mtime)."""
    out: list[tuple[str, str]] = []
    for p in sorted(PAPER_DIR.glob("roi_*.json")):
        run_id = p.name[len("roi_"):-len(".json")]
        if not (PAPER_DIR / f"book_dna_{run_id}.json").is_file():
            continue
        gen = _generated_utc_of(run_id)
        if gen:
            out.append((gen, run_id))
    out.sort()
    return [run_id for _, run_id in out]


def choose_new_run_id(explicit: str | None = None) -> str:
    """The id `--bump-pin` should move to: `explicit` if given (validated), else the newest
    candidate. Raises SystemExit("REFUSED: ...") when nothing qualifies."""
    if explicit:
        roi_p, dna_p = PAPER_DIR / f"roi_{explicit}.json", PAPER_DIR / f"book_dna_{explicit}.json"
        if not roi_p.is_file():
            raise SystemExit(f"REFUSED: {_rel(roi_p)} does not exist")
        if not dna_p.is_file():
            raise SystemExit(f"REFUSED: {_rel(dna_p)} does not exist")
        if not _generated_utc_of(explicit):
            raise SystemExit(f"REFUSED: {_rel(roi_p)} has no generated_utc")
        return explicit
    cands = _candidate_run_ids()
    if not cands:
        raise SystemExit("REFUSED: no run id has both roi_<id>.json and book_dna_<id>.json with a "
                         "readable generated_utc")
    return cands[-1]


def _rewrite_pin_line(new_id: str, *, path: Path | None = None) -> str:
    """Rewrite the `RESULTS_RUN_ID = "..."` line IN PLACE (one regex, one line) in `path`
    (default: this file's own source). Refuses unless the pattern matches exactly once.
    Returns the id that was pinned before the rewrite."""
    src_path = Path(path) if path is not None else Path(__file__).resolve()
    text = src_path.read_text(encoding="utf-8")
    matches = PIN_RE.findall(text)
    if len(matches) != 1:
        raise SystemExit(f"REFUSED: expected exactly one RESULTS_RUN_ID line in {src_path.name}, "
                         f"found {len(matches)}")
    old_id = matches[0]
    new_text, n = PIN_RE.subn(f'RESULTS_RUN_ID = "{new_id}"', text, count=1)
    if n != 1:
        raise SystemExit("REFUSED: the pin rewrite did not apply exactly once")
    src_path.write_text(new_text, encoding="utf-8")
    return old_id


def _pin_text_for(new_id: str, old_id: str, path: Path) -> str:
    """Validate the on-disk pin and prepare its replacement without writing it."""
    source = path.read_text(encoding="utf-8")
    matches = PIN_RE.findall(source)
    if len(matches) != 1:
        raise SystemExit(f"REFUSED: expected exactly one RESULTS_RUN_ID line in {path.name}, "
                         f"found {len(matches)}")
    if matches[0] != old_id:
        raise SystemExit(f"REFUSED: the on-disk pin was {matches[0]!r}, expected {old_id!r}; "
                         "another process changed it -- rerun the bump")
    return PIN_RE.sub(lambda _m: f'RESULTS_RUN_ID = "{new_id}"', source, count=1)


def _readme_entry(f: dict, d: dict) -> str:
    """One featured account's clause in the README alt text / caption: name, what it is,
    its numbers over its own window, and (lead only) the matched twin / (shared only) whose
    names it holds."""
    bits = [f["kind"], f"{f['capital']} paper"]
    out = (f"{f['name']} ({', '.join(bits)}) {f['roi']:+.2f}% vs SPY {f['spy']:+.2f}% "
          f"since {f['since']}, {f['excess']:+.2f} pp")
    if f is d["featured"][0] and d["chart"]:
        out += f", its matched random twin {d['chart']['twin_vals'][-1]:+.2f}%"
    if f["shares_names_with"]:
        out += f", holds the same {len(f['tickers'])} names as {f['shares_names_with']}"
    return out


def readme_alt_text(d: dict) -> str:
    """The `<img alt=...>` text for `docs/assets/paper_results_live.svg`: every number the
    SVG shows, in words, read straight from `results_data()` -- regenerated on every bump so
    the alt text can never go stale independently of the picture."""
    entries = "; ".join(_readme_entry(f, d) for f in d["featured"])
    labels = ", ".join(f["label"] for f in d["featured"])
    return f"Best paper accounts, live, as of the {d['as_of']} close: {entries}. Labels {labels}."


def readme_sub_caption(d: dict) -> str:
    return (f'Every number on both pictures is read from a committed receipt '
           f'(<code>{d["receipt"]}</code>) and every stage names the code that runs it; '
           f'<code>backend/tests/test_public_assets.py</code> fails if either stops being true. '
           f'The motion version is <a href="docs/design/aegis_front_page.html">'
           f'<code>docs/design/aegis_front_page.html</code></a>; the design record is '
           f'<a href="docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md">'
           f'<code>docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md</code></a>.')


def readme_results_block(d: dict) -> str:
    """The exact text `update_readme_results_block` writes between the two markers."""
    alt = escape(readme_alt_text(d), {'"': "&quot;"})
    return (f'{RESULTS_BLOCK_START}\n'
           f'<p align="center">\n'
           f'  <img src="docs/assets/paper_results_live.svg" width="100%" alt="{alt}">\n'
           f'</p>\n'
           f'<p align="center"><sub>{readme_sub_caption(d)}</sub></p>\n'
           f'{RESULTS_BLOCK_END}')


def update_readme_results_block(d: dict, *, path: Path | None = None) -> bool:
    """Rewrite the README's results-panel block in place; True iff the bytes changed.
    Refuses if the markers are not found (never writes outside them)."""
    p = Path(path) if path is not None else README
    text = p.read_text(encoding="utf-8")
    new_text = _readme_text_for(d, text, p)
    if new_text != text:
        p.write_text(new_text, encoding="utf-8")
    return new_text != text


def _readme_text_for(d: dict, text: str, path: Path) -> str:
    pattern = re.compile(re.escape(RESULTS_BLOCK_START) + r".*?" + re.escape(RESULTS_BLOCK_END), re.S)
    if len(pattern.findall(text)) != 1 or text.count(RESULTS_BLOCK_START) != 1 or text.count(RESULTS_BLOCK_END) != 1:
        raise SystemExit(f"REFUSED: expected exactly one results block in {_rel(path)}")
    return pattern.sub(lambda _m: readme_results_block(d), text, count=1)


def bump_pin(run_id: str | None = None, *, pin_path: Path | None = None,
            readme_path: Path | None = None) -> int:
    """`--bump-pin [RUN_ID]`. Returns the process exit code; never raises (any REFUSED is
    printed and turned into 2, with RESULTS_RUN_ID restored)."""
    global RESULTS_RUN_ID, _RESULTS_OVERRIDE
    old_id = RESULTS_RUN_ID
    try:
        return _bump_pin_inner(run_id, old_id, pin_path=pin_path, readme_path=readme_path)
    except (SystemExit, OSError, ValueError, KeyError, TypeError) as exc:
        RESULTS_RUN_ID = old_id
        _RESULTS_OVERRIDE = None
        print(str(exc))
        return 2


def _bump_pin_inner(run_id: str | None, old_id: str, *, pin_path: Path | None,
                    readme_path: Path | None) -> int:
    global RESULTS_RUN_ID, _RESULTS_OVERRIDE
    new_id = choose_new_run_id(run_id)
    old_gen, new_gen = _generated_utc_of(old_id), _generated_utc_of(new_id)
    if (new_gen, new_id) <= (old_gen, old_id):
        raise SystemExit(f"REFUSED: the newest available pin {new_id!r} ({new_gen or 'undated'}) is "
                         f"not newer than the pinned {old_id!r} ({old_gen or 'undated'}); nothing written")
    bad = check_budgets()
    if bad:
        raise SystemExit("REFUSED: text would overflow its box:\n  " + "\n  ".join(bad))
    source_path = Path(pin_path) if pin_path is not None else Path(__file__).resolve()
    rp = Path(readme_path) if readme_path is not None else README
    # Complete all validation and rendering before changing any public file.
    source_bytes = _pin_text_for(new_id, old_id, source_path).encode("utf-8")
    RESULTS_RUN_ID = new_id
    d = results_data()                      # REFUSED if a family has no LIVE account
    snapshot = _public_snapshot(d, new_id)
    d = snapshot["display"]
    _RESULTS_OVERRIDE = d
    rendered = {path: text.encode("utf-8") for path, text in outputs().items()}
    readme_before = rp.read_text(encoding="utf-8")
    readme_after = _readme_text_for(d, readme_before, rp).encode("utf-8")
    written = {_rel(path): hashlib.sha256(data).hexdigest() for path, data in rendered.items()}
    snap_path = snapshot_path(new_id)
    snap_bytes = json.dumps(snapshot, indent=1, allow_nan=False).encode("utf-8")
    written[_rel(snap_path)] = hashlib.sha256(snap_bytes).hexdigest()
    if readme_after != readme_before.encode("utf-8"):
        written[_rel(rp)] = hashlib.sha256(readme_after).hexdigest()
    featured = [{"family": f["family"], "account": f["account"], "name": f["name"]} for f in d["featured"]]
    receipt = {"schema": "public_assets_refresh/1",
              "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "old_run_id": old_id, "run_id": new_id, "assets": written, "featured": featured}
    receipt_path = REFRESH_DIR / f"public_assets_refresh_{new_id}.json"
    receipt_bytes = json.dumps(receipt, indent=1, default=str).encode("utf-8")
    # Source pin is the final promotion marker. A write failure cannot advance it first.
    changes = {**rendered, snap_path: snap_bytes, rp: readme_after,
               receipt_path: receipt_bytes, source_path: source_bytes}
    previous = {path: path.read_bytes() if path.exists() else None for path in changes}
    changed: list[Path] = []
    try:
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            changed.append(path)
            path.write_bytes(data)
    except OSError as exc:
        rollback_errors = []
        for path in reversed(changed):
            before = previous[path]
            try:
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(before)
            except OSError as restore_exc:
                rollback_errors.append(f"{_rel(path)}: {restore_exc}")
        if rollback_errors:
            raise SystemExit(f"INCOMPLETE ROLLBACK after {exc}: {'; '.join(rollback_errors)}") from exc
        raise
    _RESULTS_OVERRIDE = None
    written[_rel(receipt_path)] = hashlib.sha256(receipt_bytes).hexdigest()
    try:
        from backend.services import public_assets_staleness as _PAS   # noqa: PLC0415
        prev_age = _PAS.pin_age(datetime.now(timezone.utc), run_id=old_id)
        age_note = (f" (the previous pin was {prev_age['age_s'] / 86400:.1f} d old)"
                   if prev_age.get("age_s") is not None else "")
    except Exception:                                                  # noqa: BLE001 -- cosmetic only
        age_note = ""
    print(f"bumped RESULTS_RUN_ID {old_id!r} -> {new_id!r}{age_note}")
    for rel, sha in sorted(written.items()):
        print(f"wrote {rel} sha256={sha[:12]}")
    return 0


# ================================================================== cli
def check_budgets() -> list[str]:
    """Strings that would overflow their box in the widest common fallback font."""
    bad = []
    for st in STAGES:
        if len(st.title) > MAX_TITLE_CHARS:
            bad.append(f"stage {st.n} title: {st.title!r}")
        bad += [f"stage {st.n} about: {a!r}" for a in st.about if len(a) > MAX_ABOUT_CHARS]
        bad += [f"stage {st.n} module: {m.label!r}" for m in st.modules if len(m.label) > MAX_MODULE_CHARS]
        if len(st.modules) > MAX_MODULES:
            bad.append(f"stage {st.n}: {len(st.modules)} modules; a card holds {MAX_MODULES}")
    return bad


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)


def outputs() -> dict[Path, str]:
    return {HERO_SVG: render_hero(), RESULTS_SVG: render_results(), PIPELINE_SVG: render_pipeline(),
            GAUNTLET_SVG: render_gauntlet(), OG_SVG: render_og(), FRONT_HTML: render_front_html()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 when a committed asset differs from a fresh render")
    ap.add_argument("--bump-pin", nargs="?", const="", default=None, metavar="RUN_ID",
                    help="pin RUN_ID (or the newest available receipt pair), re-render every "
                         "asset + the README results block, and write a refresh receipt")
    a = ap.parse_args(argv)
    if a.bump_pin is not None:
        return bump_pin(a.bump_pin or None)
    bad = check_budgets()
    if bad:
        print("REFUSED: text would overflow its box:\n  " + "\n  ".join(bad))
        return 2
    stale = 0
    for path, text in outputs().items():
        rel = _rel(path)
        data = text.encode("utf-8")
        if a.check:
            on_disk = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else b""
            ok = on_disk == data
            stale += not ok
            print(f"{'ok   ' if ok else 'STALE'} {rel}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"wrote {rel} ({len(data):,} bytes)")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
