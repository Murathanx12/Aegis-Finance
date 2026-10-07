"""Render the two public SVG assets: the V1 Beta pipeline diagram and the social-preview card.

    python -m scripts.render_public_assets            # (re)write both SVGs
    python -m scripts.render_public_assets --check    # exit 1 if a committed SVG differs

Writes
    docs/assets/architecture_pipeline.svg   1200 x 860   the README hero
    docs/assets/og_preview.svg              1200 x 630   the social-preview card (PNG export:
                                                         docs/assets/README.md)

WHY A GENERATOR AND NOT A DRAWING
=================================
The diagram prints module paths. A hand-drawn picture of the code goes stale silently the
first time a module is renamed; here every path lives in one table (`STAGES`), and
`backend/tests/test_public_assets.py` fails when a printed path stops existing, a printed
function stops being defined, or a committed SVG no longer matches what this file renders.

The pipeline is `docs/AEGIS_V1_BETA_2026-10-07.md` §2 (its Mermaid diagram and stage table),
with that diagram's EVIDENCE box split into EVIDENCE and WORLD STATE / THEORY. The footer's
state line is §9 of the same document, dated. Nothing here is a performance claim: both assets
print RESULT IMPROVEMENT: NONE.

Stdlib only and deterministic -- no clock, no randomness, integer coordinates, LF line ends --
so the same bytes come out on every run. The social card embeds `docs/assets/logo.png` as a
data URI (an SVG shown through <img> on GitHub cannot load a second file).
"""
from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "docs" / "assets"
PIPELINE_SVG = ASSETS / "architecture_pipeline.svg"
OG_SVG = ASSETS / "og_preview.svg"
LOGO_PNG = ASSETS / "logo.png"

SOURCE_DOC = "docs/AEGIS_V1_BETA_2026-10-07.md"
STATE_DATE = "2026-10-07"
#: §9 of SOURCE_DOC, "Tally: 1 clause met, 7 partially, 3 not yet." (pinned by the test)
V1_TALLY = (1, 7, 3)
LIVE_URL = "https://aegis-finance-six.vercel.app"
REPO_URL = "github.com/Murathanx12/Aegis-Finance"

#: SOURCE_DOC §1, first sentence, verbatim (the test checks it is still there).
PRODUCT_SENTENCE = ("Aegis is an open-source investment research system that writes down what it "
                    "believes before an outcome exists, grades every belief against what then "
                    "happens, and lets only graded beliefs change how paper capital is sized.")
#: docs/FUNDING_EVIDENCE_PACK_2026-10-07.md §1, the positioning line.
TAGLINE = "Auditable AI investment intelligence"
HONEST_HEAD = "RESULT IMPROVEMENT: NONE"
HONEST_TAIL = "the loop runs, grades itself, and freezes its alternatives"

#: Layout budgets. SVG text does not wrap and a viewer's font is unknown, so every string is
#: kept inside a width measured for the widest common fallback (DejaVu Sans / Sans Mono).
MAX_MODULE_CHARS = 40
MAX_ABOUT_CHARS = 44
MAX_TITLE_CHARS = 26


@dataclass(frozen=True)
class Module:
    """A repo-relative file that must exist, and names that must be defined in it."""
    path: str
    symbols: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.path + "".join(f" · {s}" for s in self.symbols)


@dataclass(frozen=True)
class Stage:
    n: int
    title: str
    about: tuple[str, str]
    modules: tuple[Module, ...]


M = Module
STAGES: tuple[Stage, ...] = (
    Stage(1, "WORLD SENSORS",
          ("Whole-market news, analyst revisions and",
           "public flows (USAspending, lobbying, crypto)"),
          (M("scripts/news_pull.py"), M("backend/services/web_reader.py"),
           M("scripts/pull_analyst_targets.py"), M("backend/services/public_flow_common.py"))),
    Stage(2, "EVIDENCE",
          ("A language model reads what was stored and",
           "proposes; deterministic code weighs it"),
          (M("backend/services/world_digest.py"), M("backend/services/analyst_reputation.py"),
           M("backend/services/data_catalog.py"))),
    Stage(3, "WORLD STATE / THEORY",
          ("Persistent beliefs, scenarios, regime rows;",
           "a theory: mechanism, precursor, falsifier"),
          (M("backend/services/world_state.py"), M("scripts/hyp_theory_cells.py"))),
    Stage(4, "FORECASTS",
          ("Frozen before the outcome exists; graded",
           "at h = 1 / 5 / 21 / 63 sessions"),
          (M("scripts/sim_run.py", ("u_forecast",)), M("backend/services/belief_state.py"),
           M("nn_lab/nightly.py"))),
    Stage(5, "OPPORTUNITY / DECISION",
          ("Direction and magnitude kept apart; risk",
           "priced on the names it would actually buy"),
          (M("backend/services/opportunity_funnel.py"), M("scripts/sim_run.py", ("u_rank", "u_plan")),
           M("backend/services/decision_contract.py"), M("backend/services/opportunities.py"))),
    Stage(6, "PAPER ACTION OR ABSTENTION",
          ("Paper only, and a HOLD is a decision too;",
           "no LLM has authority over real capital"),
          (M("scripts/task_keeper.py", ("AegisSimOwner",)), M("backend/services/sim_session.py"),
           M("backend/services/pc_broker.py"))),
    Stage(7, "OUTCOME",
          ("A daily pass grades what came due and",
           "reports refusals instead of hiding them"),
          (M("scripts/daily_pass.py"), M("backend/services/forecast_grader.py"),
           M("scripts/sim_run.py", ("u_grade",)))),
    Stage(8, "REGRET / ATTRIBUTION",
          ("Which input did it, and when did we know?",
           "Regret as signed differences, null-tested"),
          (M("backend/services/book_dna.py"), M("backend/services/decision_story.py"),
           M("backend/services/regret_ledger.py"))),
    Stage(9, "LEARNING",
          ("Only graded outcomes change weights and",
           "preferences; gates only shrink"),
          (M("backend/services/expected_return.py"), M("backend/services/policy_state.py"),
           M("backend/services/hyp_lab.py"))),
)

#: The two feedback arrows. The first is SOURCE_DOC's own dotted edge (LEARNING -> DECISION);
#: the second is `hyp_lab.family_budget`: the family posterior sets each family's share of the
#: next generation round of hypotheses ("a shrink, never a kill").
LOOP_TO_DECISION = "weights + preferences, next cycle · gates only shrink"
LOOP_TO_THEORY = "family posterior → next round's hypothesis quota · never a kill"

FOOTER = (
    f"State on {STATE_DATE} ({SOURCE_DOC} §9): V1 Beta not reached; "
    f"{V1_TALLY[0]} of {sum(V1_TALLY)} acceptance clauses met, {V1_TALLY[1]} partially, "
    f"{V1_TALLY[2]} not yet.",
    "Not yet closed: no live decision story exists (dry run only), and policy_state is written "
    "but not yet read by a plan (§2).",
    "Solid arrows: one cycle. Dashed: what the next cycle inherits. Every path is repo-relative "
    "and checked by backend/tests/test_public_assets.py.",
)

# ------------------------------------------------------------------ palette (dark panel)
# An explicit panel instead of prefers-color-scheme: it reads the same on GitHub's light and
# dark themes. Text contrast against CARD: TITLE 15.5, TEXT 9.5, DIR 5.3, ARROW 4.6 (WCAG).
BG = "#0b1220"
PANEL_STROKE = "#2b3b57"
CARD = "#111b2c"
CARD_STROKE = "#2a3a55"
TITLE = "#eef3f9"
TEXT = "#b4c2d4"
MUTED = "#8a9bb2"
DIR = "#7d90a8"
FILE = "#93dcff"
SYM = "#c4b5fd"
CYAN = "#38bdf8"
AMBER = "#f5b942"
AMBER_BG = "#2a2111"
ARROW = "#6b86a8"

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

# ------------------------------------------------------------------ pipeline geometry
W, H = 1200, 860
CW, CH = 344, 176                      # card
COL_X = (36, 420, 804)                 # 40 px between columns, 52 px right margin for a loop
ROW_Y = (128, 360, 592)                # 56 px between rows
#: serpentine: row 1 left to right, row 2 right to left, row 3 left to right
GRID = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 2), 5: (1, 1), 6: (1, 0),
        7: (2, 0), 8: (2, 1), 9: (2, 2)}


def _t(s: str) -> str:
    return escape(s)


def _xml_head(w: int, h: int, title: str, desc: str, *, xlink: bool = False) -> list[str]:
    ns = ' xmlns:xlink="http://www.w3.org/1999/xlink"' if xlink else ""
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg"{ns} width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{_t(title)}</title>',
        f'<desc id="desc">{_t(desc)}</desc>',
    ]


def _style(rules: list[str]) -> list[str]:
    return ["<style>", f".s{{font-family:{SANS}}}", f".m{{font-family:{MONO}}}", *rules, "</style>"]


def _markers() -> list[str]:
    def one(mid: str, fill: str) -> str:
        return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" '
                f'markerHeight="9" markerUnits="userSpaceOnUse" orient="auto">'
                f'<path d="M0 0L10 5L0 10z" fill="{fill}"/></marker>')
    return ["<defs>", one("ah", ARROW), one("al", AMBER), "</defs>"]


def _card_xy(n: int) -> tuple[int, int]:
    r, c = GRID[n]
    return COL_X[c], ROW_Y[r]


def _module_text(m: Module) -> str:
    head, _, tail = m.path.rpartition("/")
    out = f'<tspan class="dir">{_t(head + "/")}</tspan><tspan class="file">{_t(tail)}</tspan>'
    return out + "".join(f'<tspan class="sym"> · {_t(s)}</tspan>' for s in m.symbols)


def _card(st: Stage) -> list[str]:
    x, y = _card_xy(st.n)
    out = [
        f'<g id="stage-{st.n}">',
        f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" rx="12" fill="{CARD}" '
        f'stroke="{CARD_STROKE}" stroke-width="1.2"/>',
        f'<circle cx="{x}" cy="{y + 27}" r="13" fill="{BG}" stroke="{CYAN}" stroke-width="1.5"/>',
        f'<text class="s num" x="{x}" y="{y + 32}" text-anchor="middle">{st.n}</text>',
        f'<text class="s st" x="{x + 24}" y="{y + 33}">{_t(st.title)}</text>',
        f'<text class="s ab" x="{x + 16}" y="{y + 57}">{_t(st.about[0])}</text>',
        f'<text class="s ab" x="{x + 16}" y="{y + 74}">{_t(st.about[1])}</text>',
        f'<path d="M{x + 16} {y + 87}H{x + CW - 16}" stroke="{CARD_STROKE}" stroke-width="1"/>',
    ]
    for i, m in enumerate(st.modules):
        out.append(f'<text class="m mod" x="{x + 16}" y="{y + 107 + 19 * i}">{_module_text(m)}</text>')
    out.append("</g>")
    return out


def _flow_arrows() -> list[str]:
    """The forward pipeline, 1 -> 9, as straight arrows between neighbouring cards."""
    out = []
    for a in range(1, 9):
        (ra, ca), (rb, cb) = GRID[a], GRID[a + 1]
        xa, ya = _card_xy(a)
        if ra == rb:                                   # same row: horizontal
            ym = ya + CH // 2
            if cb > ca:
                x0, x1 = xa + CW + 4, COL_X[cb] - 3
            else:
                x0, x1 = xa - 4, COL_X[cb] + CW + 3
            d = f"M{x0} {ym}H{x1}"
        else:                                          # same column: down
            xm = xa + CW // 2
            d = f"M{xm} {ya + CH + 4}V{ROW_Y[rb] - 3}"
        out.append(f'<path d="{d}" stroke="{ARROW}" stroke-width="2" fill="none" marker-end="url(#ah)"/>')
    return out


def _loops() -> list[str]:
    """LEARNING feeds the next cycle: into DECISION (weights and preferences) and, through the
    right margin, into THEORY (the hyp_lab family posterior)."""
    x9, y9 = _card_xy(9)
    x5, y5 = _card_xy(5)
    x3, y3 = _card_xy(3)
    dash = f'stroke="{AMBER}" stroke-width="2" stroke-dasharray="7 5" fill="none" marker-end="url(#al)"'
    # 9 -> 5 through the gap between rows 2 and 3
    xa, xb, yl = x9 + CW - 48, x5 + 56, y5 + CH + 30
    to_decision = (f"M{xa} {y9 - 3}V{yl + 12}Q{xa} {yl} {xa - 12} {yl}"
                   f"H{xb + 12}Q{xb} {yl} {xb} {yl - 12}V{y5 + CH + 3}")
    # 9 -> 3 through the right margin
    xr, ym9, ym3 = x3 + CW + 28, y9 + CH // 2, y3 + CH // 2
    to_theory = (f"M{x9 + CW + 3} {ym9}H{xr - 12}Q{xr} {ym9} {xr} {ym9 - 12}"
                 f"V{ym3 + 12}Q{xr} {ym3} {xr - 12} {ym3}H{x3 + CW + 4}")
    return [
        f'<path d="{to_decision}" {dash}/>',
        f'<text class="s loop" x="{(xa + xb) // 2}" y="{yl - 9}" text-anchor="middle">{_t(LOOP_TO_DECISION)}</text>',
        f'<path d="{to_theory}" {dash}/>',
        f'<text class="s loop" transform="translate({xr + 15} {(ym9 + ym3) // 2}) rotate(-90)" '
        f'text-anchor="middle">{_t(LOOP_TO_THEORY)}</text>',
    ]


def render_pipeline() -> str:
    lines = _xml_head(
        W, H, "The Aegis V1 Beta pipeline",
        "Nine stages in one loop: world sensors, evidence, world state and theory, forecasts, "
        "opportunity and decision, paper action or abstention, outcome, regret and attribution, "
        "learning; learning feeds the next cycle's decisions and theory. Each stage names the "
        f"repository modules that run it. State on {STATE_DATE}: V1 Beta not reached; "
        f"{HONEST_HEAD}. Source: {SOURCE_DOC}.")
    lines += _style([
        f".eb{{font-size:12.5px;font-weight:700;letter-spacing:2px;fill:{CYAN}}}",
        f".h1{{font-size:25px;font-weight:700;fill:{TITLE}}}",
        f".sub{{font-size:14px;fill:{TEXT}}}",
        f".chip{{font-size:13px;font-weight:700;letter-spacing:1.2px;fill:{AMBER}}}",
        f".tail{{font-size:13px;fill:{TEXT}}}",
        f".num{{font-size:13px;font-weight:700;fill:{TITLE}}}",
        f".st{{font-size:15.5px;font-weight:700;letter-spacing:.5px;fill:{TITLE}}}",
        f".ab{{font-size:13px;fill:{TEXT}}}",
        ".mod{font-size:12.5px}",
        f".dir{{fill:{DIR}}}",
        f".file{{fill:{FILE}}}",
        f".sym{{fill:{SYM}}}",
        f".loop{{font-size:12px;font-style:italic;fill:{AMBER}}}",
        f".ft{{font-size:12.5px;fill:{TEXT}}}",
        f".ft2{{font-size:12px;fill:{MUTED}}}",
    ])
    lines += _markers()
    lines += [
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20" fill="{BG}" '
        f'stroke="{PANEL_STROKE}" stroke-width="2"/>',
        '<text class="s eb" x="36" y="46">AEGIS FINANCE · THE V1 BETA LOOP</text>',
        '<text class="s h1" x="36" y="79">Every box names the module that runs it</text>',
        '<text class="s sub" x="36" y="106">Language models read the world and propose; deterministic '
        'code ranks, sizes, stops and exits. Paper only.</text>',
        f'<rect x="856" y="30" width="292" height="30" rx="15" fill="{AMBER_BG}" stroke="{AMBER}" '
        'stroke-width="1.2"/>',
        f'<text class="s chip" x="1002" y="50" text-anchor="middle">{_t(HONEST_HEAD)}</text>',
        f'<text class="s tail" x="1148" y="82" text-anchor="end">{_t(HONEST_TAIL)}</text>',
    ]
    lines += _flow_arrows()
    lines += _loops()
    for st in STAGES:
        lines += _card(st)
    y0 = ROW_Y[2] + CH
    lines += [
        f'<path d="M36 {y0 + 16}H1148" stroke="{CARD_STROKE}" stroke-width="1"/>',
        f'<text class="s ft" x="36" y="{y0 + 36}">{_t(FOOTER[0])}</text>',
        f'<text class="s ft" x="36" y="{y0 + 55}">{_t(FOOTER[1])}</text>',
        f'<text class="s ft2" x="36" y="{y0 + 74}">{_t(FOOTER[2])}</text>',
        "</svg>",
    ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ social-preview card
OG_W, OG_H = 1200, 630
OG_DESC_LINES = 5
OG_DESC_CHARS = 47


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


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)


def _logo_href() -> str:
    if not LOGO_PNG.is_file():
        raise SystemExit(f"REFUSED: {_rel(LOGO_PNG)} is missing; the card embeds the project's "
                         "own logo and will not draw a substitute.")
    return "data:image/png;base64," + base64.b64encode(LOGO_PNG.read_bytes()).decode("ascii")


def render_og() -> str:
    desc = wrap(PRODUCT_SENTENCE, OG_DESC_CHARS)
    if len(desc) > OG_DESC_LINES:
        raise ValueError(f"the product sentence wraps to {len(desc)} lines; the card holds {OG_DESC_LINES}")
    lines = _xml_head(
        OG_W, OG_H, "AEGIS Finance",
        f"AEGIS Finance. {PRODUCT_SENTENCE} {HONEST_HEAD} - {HONEST_TAIL}. {LIVE_URL}",
        xlink=True)
    lines += _style([
        f".t{{font-size:58px;font-weight:700;fill:{TITLE}}}",
        f".tag{{font-size:22px;font-weight:600;fill:{CYAN}}}",
        ".d{font-size:26px;fill:#d5deea}",
        f".hh{{font-size:26px;font-weight:700;letter-spacing:1px;fill:{AMBER}}}",
        f".ht{{font-size:20px;fill:{TEXT}}}",
        f".url{{font-size:24px;fill:{CYAN}}}",
        f".meta{{font-size:16px;fill:{MUTED}}}",
        f".eb{{font-size:12.5px;font-weight:700;letter-spacing:2px;fill:{CYAN}}}",
        f".num{{font-size:12px;font-weight:700;fill:{TITLE}}}",
        f".sn{{font-size:13px;font-weight:700;letter-spacing:.4px;fill:{TITLE}}}",
    ])
    lines += _markers()
    lines += [
        f'<rect width="{OG_W}" height="{OG_H}" fill="{BG}"/>',
        f'<rect width="{OG_W}" height="5" fill="{CYAN}"/>',
        f'<image x="72" y="64" width="96" height="96" xlink:href="{_logo_href()}"/>',
        '<text class="s t" x="192" y="126">AEGIS Finance</text>',
        f'<text class="s tag" x="194" y="160">{_t(TAGLINE)}</text>',
    ]
    for i, ln in enumerate(desc):
        lines.append(f'<text class="s d" x="72" y="{236 + 37 * i}">{_t(ln)}</text>')
    lines += [
        f'<rect x="72" y="418" width="5" height="76" fill="{AMBER}"/>',
        f'<text class="s hh" x="96" y="448">{_t(HONEST_HEAD)}</text>',
        f'<text class="s ht" x="96" y="482">— {_t(HONEST_TAIL)}</text>',
        f'<text class="m url" x="72" y="562">{_t(LIVE_URL)}</text>',
        f'<text class="s meta" x="72" y="596">open source (MIT) · paper only · {_t(REPO_URL)}</text>',
    ]
    # the loop, in miniature: the nine stage names, and LEARNING's edge back to DECISION
    px, py, pw, ph = 820, 48, 332, 534
    cx = px + 42
    lines += [
        f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="16" fill="{CARD}" '
        f'stroke="{CARD_STROKE}" stroke-width="1.2"/>',
        f'<text class="s eb" x="{px + 26}" y="{py + 36}">THE V1 BETA LOOP</text>',
    ]
    ys = [py + 76 + 50 * i for i in range(len(STAGES))]
    for i in range(len(STAGES) - 1):
        lines.append(f'<path d="M{cx} {ys[i] + 12}V{ys[i + 1] - 13}" stroke="{ARROW}" '
                     'stroke-width="1.5" marker-end="url(#ah)"/>')
    y9, y5 = ys[8], ys[4]
    lines.append(f'<path d="M{cx - 12} {y9}H{cx - 24}Q{cx - 30} {y9} {cx - 30} {y9 - 6}'
                 f'V{y5 + 6}Q{cx - 30} {y5} {cx - 24} {y5}H{cx - 14}" stroke="{AMBER}" '
                 'stroke-width="1.5" stroke-dasharray="5 4" fill="none" marker-end="url(#al)"/>')
    for st, y in zip(STAGES, ys):
        lines += [
            f'<circle cx="{cx}" cy="{y}" r="12" fill="{BG}" stroke="{CYAN}" stroke-width="1.5"/>',
            f'<text class="s num" x="{cx}" y="{y + 4}" text-anchor="middle">{st.n}</text>',
            f'<text class="s sn" x="{cx + 24}" y="{y + 5}">{_t(st.title)}</text>',
        ]
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ cli
def check_budgets() -> list[str]:
    """Strings that would overflow their box in the widest common fallback font."""
    bad = []
    for st in STAGES:
        if len(st.title) > MAX_TITLE_CHARS:
            bad.append(f"stage {st.n} title: {st.title!r}")
        bad += [f"stage {st.n} about: {a!r}" for a in st.about if len(a) > MAX_ABOUT_CHARS]
        bad += [f"stage {st.n} module: {m.label!r}" for m in st.modules if len(m.label) > MAX_MODULE_CHARS]
        if len(st.modules) > 4:
            bad.append(f"stage {st.n}: {len(st.modules)} modules; a card holds 4")
    return bad


def outputs() -> dict[Path, str]:
    return {PIPELINE_SVG: render_pipeline(), OG_SVG: render_og()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 when a committed SVG differs from a fresh render")
    a = ap.parse_args(argv)
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
