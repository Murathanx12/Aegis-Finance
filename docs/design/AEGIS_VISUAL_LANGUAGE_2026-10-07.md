# Aegis visual language: the orbit and the blackline (2026-10-07)

Licence: not applicable (a design system, not a strategy or a claim). Owner decisions of
2026-10-07, recorded so the next project starts from them instead of from a blank page.
The skill that applies this document is
[`.claude/skills/aegis-motion-visuals/SKILL.md`](../../.claude/skills/aegis-motion-visuals/SKILL.md);
Optimus serves it through `aegis_skills` and ingests this file through `tools/refresh_aegis.py`
(the `aegis-docs` source), so both reach every later session.

Read with: [`OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md`](OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md)
(the same day's spec: rings not physics, motion must mean something) and
`scripts/render_public_assets.py` (the generator that implements everything below).

---

## 0. What the owner chose, in the owner's words, and what it means

Four styles were shown side by side (scratch prototypes, same content in each):

| | style | verdict | where it lives now |
|---|---|---|---|
| **A** | **Blackline HUD**: pure black, white hairlines, corner brackets, monospace labels, blue current in the wires | "I really liked A, because of how the data is going through" | **the general project style**: explanation pages, architecture, how the brain works |
| B | Swiss White: white page, black type, vertical spine | "too bright, too white" | rejected |
| **C** | **Orbital**: the nine stages on a ring, because the system IS a loop | "stands out the most… so much better than the blocky structure everybody makes" | **the front page**: what the system is and what is running |
| D | Glass terminal: frosted cards, glow | "good but doesn't work with this project" | not used |

Owner feedback on C, each item mapped to what was built:

| feedback | built as |
|---|---|
| "the blue line should be little dots, getting bigger and blue as the movement happens, not constant" | the ring is 120 dots; a wave makes each dot swell (x2.7) and turn blue, then decay; it TRAVELS 0.8 s between stages and DWELLS 1.2 s at each one |
| "I can't see the spiral, only a blue line" | the dots ARE the ring now; the moving part is a wave on a visible orbit, not a spinning stroke |
| "the orange line through the edges breaks the spiral apart" | the learning loop is two faint inner orbits (38% opacity) that run clockwise from LEARNING into the next cycle's THEORY and DECISION: a spiral inward, never a chord across the ring |
| "a bit slower; when it reaches a bubble, the bubble grows and gets the attention" | 2.0 s per stage (an 18 s cycle, twice the first draft); the reached bubble scales x1.5 and fills blue, its title turns blue and gains an underline, and a centre readout names the active stage |
| "the up numbers should not look like alarms; maybe green, but too many colours, so bright blue" | gains are bright blue (`#6fb0ff` on black); red is never used; orange is reserved for learning |
| "rather than saying we have no profitable edge, say this is our result" | the front page leads with the best live paper accounts, each with its evidence label and its own-window SPY leg; the selection rule and its denominator are printed beside them (honest, and still a result) |
| "it should be an HTML design, motion design" | the same generator writes an HTML page (`docs/design/aegis_front_page.html`) next to the SVGs; GitHub's README cannot run HTML, so the README carries the animated SVGs |
| "no PNGs" | every asset is SVG (CSS keyframes + SMIL); nothing is rasterised into the repo |

---

## 1. Tokens

### 1.1 Colour (dark only; there is no light theme by decision)

| token | value | role |
|---|---|---|
| `bg` | `#000000` | the canvas. Pure black, never navy (the first draft's `#0b1220` was rejected as "blue background") |
| `ink` | `#ffffff` | titles, the wordmark, numbers that are facts |
| `ink-2` | `rgba(255,255,255,.62–.72)` | body text, stage descriptions |
| `ink-3` | `rgba(255,255,255,.40–.55)` | kickers, meta, ticks, footers |
| `hairline` | `rgba(255,255,255,.06–.22)` | rings, card frames, grid lines, wires |
| `blue` | `#4a8dff` | the forward flow: the active stage, the account line, module names |
| `blue-hi` | `#6fb0ff` | gains and the swelling wave (the brightest thing on the page is a result) |
| `orange` | `#ff8a1f` (`#ffb36b` highlight) | learning only: feedback paths, the LEARNING stage, comets |
| white dashed | `#ffffff`, dash 5 4 | the benchmark (SPY over the same window) |
| white 40% | | the control (matched random twin) |

Rules: one accent per meaning. Blue = what moves forward and what it earned; orange = what the
system learns; white = structure and the benchmark. Red is not used anywhere; a negative number
is printed in white with a true minus sign (`−`), never coloured as an alarm.

### 1.2 Type

| use | face | size / weight / tracking |
|---|---|---|
| wordmark | `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif` | 50–64 px, weight 200, tracking 16–22 px |
| stage titles | same sans | 14–15 px, 600, tracking 1.6 px, UPPERCASE |
| body | same sans | 13–17 px, 400 |
| kickers, labels, chips, ticks, module names | `ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace` | 10–12 px, 400–700, tracking 1.5–3.5 px, UPPERCASE for kickers |
| big numbers (results) | sans | 34 px, weight 300 |

No webfont is loaded: an SVG shown through GitHub's `<img>` cannot fetch one. Widths are budgeted
for the widest common fallback (DejaVu Sans): every layout is screenshotted once with the font
forced to DejaVu before it ships.

### 1.3 Geometry

- Canvas 1200 px wide (GitHub scales it to the README column, ~0.7x); nothing smaller than 10 px
  at full size.
- Orbit (C): radius 232, nine stages 40° apart, LEARNING at the crown (−90°), stage 1 at −50°,
  clockwise. Labels outside the ring: right side anchored start, left side anchored end, the two
  bottom stages below their bubble, the crown above. Inner orbits at R−46 and R−76.
- Blackline grid (A): 3x3 serpentine (row 1 left to right, row 2 right to left, row 3 left to
  right) so every arrow is short and the loop reads without crossing; cards 350 wide, corner
  brackets 12 px, 1.5 px strokes, a dot grid at 24 px and 7% white behind everything.

---

## 2. Motion

Motion is behaviour, not decoration: each animation says one fact.

| what moves | what it says | spec |
|---|---|---|
| the dot wave (C) | the loop runs, stage by stage | 2.0 s per stage = 0.8 s travel (easeInOutCubic) + 1.2 s dwell; 18 s per cycle; each dot's delay is the inverse of the wave's position function, so speed varies without JavaScript |
| bubble growth + title underline + readout (C) | which stage is working now | on arrival: scale 1 → 1.5 in 0.43 s, hold through the dwell, release over 0.6 s; the title fills blue (orange for LEARNING) and an underline grows `scaleX(0 → 1)` |
| comets on the inner orbits (C) | what learning hands to the next cycle | SMIL `animateMotion` with `keyPoints="0;1;1"` over the 18 s cycle, launched when the wave reaches LEARNING; hidden between launches by an opacity track on the same clock |
| current in the wires (A) | data flows forward | dash 3 9, offset −12 per second, linear (linear is reserved for continuous flow) |
| card highlight (A) | the stage being explained | blue frame on for 8% of a 9 s cycle per card, in order; LEARNING's frame is orange |
| bars and lines (results) | the number arriving | bars grow once (1.4 s, spline 0.2 0.8 0.2 1); the line chart is revealed left to right by a clip (2.6 s) so dashed lines keep their dashes; the latest point pulses (r 4 → 16, 2 s) |

`@media (prefers-reduced-motion: reduce)` turns every CSS animation off; the static frame is
complete on its own (all dots at rest, every label at full strength, the chart drawn, the first
readout shown). SMIL comets keep running there; they carry no text.

---

## 3. Components (all in `scripts/render_public_assets.py`)

- **Stage table** (`STAGES`): number, display title, the V1 Beta doc's name, two description
  lines of at most 40 characters, and the modules that run it. The test fails when a printed
  path stops existing or a printed function stops being defined, so the picture cannot drift
  from the code.
- **Orbit hero** (C), **blackline pipeline** (A), **blackline gauntlet** (A: the README's former
  Mermaid flowchart, node for node), **results panel** (C), **social card** (C), **HTML front
  page** (C, with counting numbers and the same data).
- **Results panel**: the excess over SPY (big, bright blue), the account, its meta line, its
  evidence label (`OBSERVED(n)`), two bars (account, SPY over the same days), and one line chart
  of the strongest account against its matched random twin and SPY. The SELECTION RULE is code
  (best strategy account in each named family, control twins excluded) and its denominator is
  printed under the panel. Inputs are a pinned receipt run id; refreshing is "bump the pin,
  re-render, commit", and the test reproduces the committed bytes.

---

## 4. How the work was done, and what else could have done it

**Used:** a stdlib-only Python generator (deterministic: integer-ish coordinates, no clock, no
randomness, LF), CSS keyframes and SMIL inside the SVG, headless Chromium through Playwright
(`executable_path=/opt/pw-browsers/...` in the cloud box) to screenshot each style at chosen
times in the cycle (t = 3.2 s, 9.3 s, 17.8 s) and once with DejaVu forced, and an HTML gallery
of four styles embedded as `data:` URIs so the owner compared them exactly as GitHub shows
them. Skills/tools in the session: Playwright, the repo's own test conventions
(`test_public_assets.py`), the artifact/file viewer for the gallery.

**Could have used** (available, and the right choice for a different job):

| tool | when it is the better choice |
|---|---|
| Figma MCP (`generate_diagram`, `use_figma`) | a designer wants to edit the layout by hand before it is coded; export SVG back into the generator's tokens |
| p5.js / p5.brush | a generative, always-sensing backdrop for a portfolio piece (see the creative tool library §1.1–1.2); never for a number |
| GSAP or Framer Motion | the website front page as a React component (scroll-linked reveals, hover states); not usable in a README |
| D3 (`d3-shape`, `d3-scale`) | live data on the website: real axes, transitions between snapshots |
| Lottie / Rive | a designer-authored animation that must play identically in the app and on mobile |
| Remotion | turning the orbit into a 15-second video for social posts |
| Canva / Gamma MCPs | slides and one-pagers for funders that reuse these tokens |

---

## 5. Reusing it on the next project

1. Copy the skill to the user-level skills folder so every project sees it:
   `cp -r .claude/skills/aegis-motion-visuals ~/.claude/skills/` (Optimus's `aegis_skills`
   already serves it from this repo).
2. Pick by purpose: **C** when the page must say "this is the system, and this part is
   running"; **A** when the page must explain how data moves; never a white canvas.
3. Start from the stage table and the receipt, not from the picture: the visual is a number
   rendered, so every element needs a field behind it.
4. Screenshot three moments of the cycle and one forced-fallback-font frame before showing
   anyone.
