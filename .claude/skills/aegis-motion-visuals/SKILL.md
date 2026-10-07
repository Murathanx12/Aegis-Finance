---
name: aegis-motion-visuals
description: Make or change a public visual (README hero, architecture diagram, results panel, social card, landing page, brain map) in the owner's chosen language — style C "orbit" for front pages, style A "blackline" for explanation pages — as animated SVG/HTML generated from data, never PNG. Use when asked for visuals, diagrams, a hero, a showcase page, "make it look better", or a page for Optimus or another project.
---

# Aegis motion visuals

The owner picked two styles on 2026-10-07 after seeing four side by side. The full record —
tokens, motion timings, why each choice was made, and the tools that could replace these —
is `docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md`. Read §0 and §1 before drawing anything.

## Which style

| the page must say | style | canvas |
|---|---|---|
| "this is the system, and this part is running" (front page, README hero, landing, social card) | **C — orbit**: stages on a dotted ring, a blue wave that dwells at each stage, the stage bubble grows, learning as faint orange inner orbits | pure black |
| "this is how data moves" (architecture, explanation pages, how the brain works) | **A — blackline**: 3x3 serpentine HUD cards, corner brackets, mono labels, blue current in the wires, orange loops | pure black + 7% dot grid |
| anything else | ask; never a white canvas (rejected: "too bright"), never glass cards (rejected for this project) | |

## Procedure

1. **Data first.** Every element traces to a field: a stage table whose module paths are
   tested to exist, numbers read from a pinned receipt run id. No decorative nodes, no
   invented positions (rings and declared grids, never a force simulation).
2. **Generate, don't draw.** A stdlib Python generator writes the SVG (and the HTML twin)
   deterministically; a test reproduces the committed bytes. Pattern:
   `scripts/render_public_assets.py` + `backend/tests/test_public_assets.py`.
3. **Colour by meaning.** Blue = forward flow and gains (`#4a8dff`, gains `#6fb0ff`);
   orange = learning only (`#ff8a1f`); white = structure and the benchmark (SPY dashed);
   no red, no green, no navy background.
4. **Motion with meaning.** C: 0.8 s travel + 1.2 s dwell per stage, easeInOutCubic, the
   reached bubble x1.5, title + underline lit, centre readout names the stage. A: dashed
   current in the wires, one card lit at a time. Charts draw once. Always a
   `prefers-reduced-motion` frame that is complete on its own.
5. **GitHub-safe SVG.** No script, no `foreignObject`, no `use`, no external font or image,
   only `#fragment` hrefs; system font stacks; CSS keyframes + SMIL only.
6. **Results, honestly.** Lead with the result (the owner: "say this is our result", not "we
   have no edge"), and print beside it what makes it honest: the evidence label
   (`OBSERVED(n)`), the benchmark over the same window, the matched control when one exists,
   and the selection rule with its denominator.
7. **Verify by looking.** Headless Chromium (Playwright; in the cloud box pass
   `executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"`), the SVG inside an
   `<img>` as GitHub shows it: three moments of the cycle, plus one frame with the font forced
   to DejaVu Sans to prove nothing overflows. Show the owner a gallery before committing a new
   style.
8. **No PNG in git.** The social preview PNG GitHub's settings need is exported locally and
   uploaded, never committed.
