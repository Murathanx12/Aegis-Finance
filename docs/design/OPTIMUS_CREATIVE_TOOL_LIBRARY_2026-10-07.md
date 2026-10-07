# Optimus Brain creative / tool library (2026-10-07)

Licence: not applicable (`N/A` — this is a design reference and a visual spec, not a
strategy, signal, or claim; nothing here touches data, cost, or capital). Scope: owner's
brief of 2026-10-07 — preserve design references for reuse (personal portfolio + the
`/brain` page), fix the "constantly moving" force graph, and raise the GitHub repo's
presentation to match the system underneath it. No machine details (no portfolio sizing,
no signal names). Every URL below was fetched before being written down; every reference
with no fetchable source is marked `OWNER_REFERENCE` and not claimed as reproduced.

Read against: `frontend/src/app/brain/page.tsx`, `frontend/src/app/dev/page.tsx`,
`docs/research_notes/2026-10-06/opportunity_explorer_2026-10-06.md` §"showcase bugs",
`backend/data/optimus/world_state/beliefs.json` + `scenarios.json` (as of digest
`20261006T223002Z`), `backend/data/optimus/digest/world_state_20261006T223002Z.json`,
`backend/data/optimus/world_state/belief_updates_2026-10.jsonl`, `README.md`,
`docs/AEGIS_V1_BETA_2026-10-07.md` §2, `frontend/next.config.ts`,
`backend/services/regret_ledger.py`.

---

## 0. The state this spec is built against, in one paragraph

`/brain` (this repo) is a health/decision dashboard, not a graph — four grouped cards of
probe rows (`GROUPS` in `brain/page.tsx`, lines 50-78), a decision-ledger card, a
learning-digest card. It links out to `optimus-brain-alpha.vercel.app`, a **separate**
Vercel deploy built by `showcase/build.py` in the **optimus** repo — a force-directed
node graph. That graph is the thing the owner dislikes ("constantly moves because nodes
push each other"), has its legend overlapping the drag/zoom hint, has bubbles clipped at
the canvas edge, and was last built 2026-07-12 (168 nodes against ~395 pages today) —
all three confirmed in `opportunity_explorer_2026-10-06.md` point 3, not re-litigated
here. **That repo and that page are not touched by this document.** What follows is a
spec for a *different*, state-driven visual — usable on this repo's `/brain` page and
reusable, undressed of receipts, as a personal-portfolio piece — built against data this
repo already writes: `world_state/beliefs.json` (16 live beliefs, schema `v2`) and
`world_state/scenarios.json` (8 scenarios, all `DECLARED_PRIOR`).

---

## 1. Reference register

### 1.1 p5.js

| | |
|---|---|
| Repo / site | [p5js.org](https://p5js.org/) · [github.com/processing/p5.js](https://github.com/processing/p5.js) |
| Version (fetched 2026-10-07) | **2.3.3** — [download page](https://p5js.org/download/) |
| Licence | **LGPL-2.1** |
| CDN | `https://cdn.jsdelivr.net/npm/p5@2.3.3/lib/p5.min.js` (pin the version; `@2` floats) |
| Measured size | **990,372 bytes** minified, **285,201 bytes** gzipped — downloaded and measured directly from the jsDelivr CDN on 2026-10-07, not a quoted figure |
| React/Next pattern | p5 needs `window`; Next SSRs by default. The working pattern is a **client component** (`"use client"`) that creates `new p5(sketch, container)` in a `useEffect` with cleanup calling `.remove()`, or `next/dynamic` with `ssr: false` wrapping a `react-p5` instance-mode component. `react-p5` exists ([CDN entry](https://cdn.jsdelivr.net/npm/react-p5@1.3.27/README.md)) but is a thin wrapper over the same instance-mode pattern and adds a dependency for little. |
| Static desktop export | **Compatible as-is.** `frontend/next.config.ts` builds `output: "export"` under `AEGIS_DESKTOP_BUILD=1` — a pure static HTML/JS bundle FastAPI serves with no Node runtime. p5.js runs entirely client-side (canvas + requestAnimationFrame), so a client-only component with no server dependency exports cleanly; nothing in the export path needs p5 at build time. |
| Instance mode | Required discipline here regardless of React: global mode pollutes `window` with `setup`/`draw`/etc. and breaks if the page ever hosts two sketches (e.g., Brain page + a portfolio showcase embed). Always `new p5((p) => { p.setup = ...; p.draw = ...; }, el)`. |

### 1.2 p5.brush

| | |
|---|---|
| Repo | [github.com/acamposuribe/p5.brush](https://github.com/acamposuribe/p5.brush) (older fork path `1123in/p5.brush` resolves to the same project) |
| Site | [p5-brush.cargo.site](https://p5-brush.cargo.site/) |
| Licence | **MIT** |
| CDN | `https://cdn.jsdelivr.net/npm/p5.brush@latest` (pin a version in production; measured unminified size on 2026-10-07: **72,065 bytes**, **27,245 bytes** gzipped) |
| What it does | Adds natural media to p5: pencils/charcoal/marker/spray brushes, a watercolor fill system with bleed/diffusion, hatch-pattern fills (`brush.hatchArray()` can compute hatch geometry as data, without drawing — useful if the hatching itself is ever wanted as an SVG layer rather than canvas pixels), and **vector/flow fields** (built-ins: hand, curved, zigzag, waves, seabed, spiral, columns, plus a custom-field authoring path) that bend strokes organically — this is the "organic flow field / network trails" primitive the brief asks for. |
| Instance mode | **Supported.** Call `brush.instance(p)` inside the sketch before `setup`/`draw`; after that every `brush.*` call works without a `p.` prefix. |
| Performance caveat (from the repo's own docs) | `brush.scaleBrushes()` is described as "usually not optional in practice" — built-in brushes are tuned to a reference canvas size and render wrong-scaled without it. The library's own install note also states a **p5.js 2.x + WEBGL canvas mode** expectation for full feature support — confirm WEBGL vs 2D compatibility before using it inside an existing 2D-canvas sketch (e.g. if combined with a plain p5 2D data layer, the brush layer likely needs its own WEBGL canvas, not a shared one). |
| Fit for this brief | **Background/identity use, not data encoding.** It is a generative-art library — organic trails, a sense of a living surface — not a charting library. Correct placement (see §2.3, Option C): a generative backdrop *behind* an SVG/DOM data layer that carries the actual state, never *as* the data layer itself, because brush strokes carry no semantic binding to a belief's confidence or direction on their own. |

### 1.3 "Thinking orb" / reasoning-orb concepts

Three public examples found, fetched and verified; the owner's Instagram references are
recorded separately below as `OWNER_REFERENCE` because no URL exists for them yet.

| Name | URL | Licence | What it is |
|---|---|---|---|
| Thinking Orbs (yogesharc) | [github.com/yogesharc/thinking-orbs](https://github.com/yogesharc/thinking-orbs) | MIT | React component library; canvas-rendered; 8 states (including `reasoning`, `searching`, `compacting`), 15 variants, 5 shapes, 8 render styles. Install: `npm i @yogesharc/thinking-orbs`, or copy via the shadcn registry for full customisation. Also listed on [21st.dev](https://21st.dev/@yogesharc/components/thinking-orbs). |
| thinking-orbs (Jakub Antalik) | [github.com/Jakubantalik/thinking-orbs](https://github.com/Jakubantalik/thinking-orbs) | MIT | A **different** project, same concept name. Plain 2D canvas (no WebGL, no filters — cross-browser identical). Nine hand-tuned states: working, searching, solving, listening, connecting, weaving, composing, breathing, shaping. Two fixed sizes (64px chat-avatar scale, 20px inline-text scale) rather than one scaled asset. Props: state, size, speed multiplier, pause, theme (auto/dark/light). |
| AI orb animation (Robin Holesinsky) | [me.muz.li/rholesinsky/ai-or-animation](https://me.muz.li/rholesinsky/ai-or-animation) | — (showcase write-up, not a library) | A design-process writeup of a glowing orb used to visualise an AI agent's "thinking" state, minimal surrounding chrome so the orb carries the whole affordance. Useful as a motion reference, not as code. |

None of the three ship a belief-confidence/evidence-strength mapping — they are generic
"the agent is doing something" indicators. If reused for Optimus, the *state machine*
(which named state → which visual) has to be authored fresh against §2's field mapping;
the orb rendering primitives (canvas dot-sphere, state-to-animation dispatch) are the
reusable part.

**`OWNER_REFERENCE: Instagram/GitHub thinking-orb and reasoning-orb design clips`** — the
owner described collecting these from Instagram and GitHub; no specific post URL was
supplied and none is fabricated here. When the owner has the saved posts, this row should
be filled with: post URL, creator handle, and the one visual idea worth keeping (a
loading sphere is not itself a finding — the *mapping from sphere property to meaning* is
what this document borrows, per the owner's own channel list in his brief).

### 1.4 Motion-design principles for data (not decoration)

| Source | Core point used here | Fetched |
|---|---|---|
| Toptal — *Compelling and Moving: A Guide to Motion Design Principles* | "Motion isn't ornamentation, it is behavior, and behaviors can only help or hinder the user experience." Four mechanisms that convey state specifically: **easing** (mimics real acceleration, avoids jarring instant changes), **offset/delay** (staggering creates hierarchy and signals relationship between elements), **parenting**, **transformation**. | [toptal.com/designers/ux/motion-design-principles](https://www.toptal.com/designers/ux/motion-design-principles) |
| Microsoft Fluent 2 — Motion | Motion is "applied with purpose and intent to serve the functionality of an experience." Duration scales with element size/distance; ease-in/out for organic movement, linear reserved for rotation. Mandates a **reduced/no-motion setting per WCAG**, short durations, and no motion that could trigger seizures; where motion itself carries information, an ARIA live region (or, here, a text delta) must carry the same information for a user who has motion off. | [fluent2.microsoft.design/motion](https://fluent2.microsoft.design/motion) |

Applied to §2: a belief orb's animation must (a) run once per state change, not
continuously, (b) use ease-out for an orb "arriving" at a new confidence size and ease-in
for one "settling" after a contradiction resolves, and (c) have a `prefers-reduced-motion`
fallback that is the *same information as a line of text*, not a degraded version of the
same animation — because Fluent's rule and the owner's rule ("motion must mean something")
are the same rule from two directions.

### 1.5 Viral Opus 5.5 videos and prompts

**`OWNER_REFERENCE: viral Opus 5.5–generated videos, reasoning-orb/network motion
clips`** — the owner mentioned collecting these but no URLs or prompts were supplied in
this task. Table below is a template to fill in, not a finding:

| Clip URL | Platform | Prompt (verbatim, if saved) | Visual idea worth borrowing | Licence/reuse note |
|---|---|---|---|---|
| *(paste here)* | | | | check platform ToS before reuse in a public repo asset |

---

## 2. The Brain visual spec

No code in this section — layout, data mapping, and motion rules only.

### 2.1 Why a force simulation is wrong for this data, in one sentence

A force-directed graph invents a **geometry** (attraction/repulsion, settling position)
that does not exist in `beliefs.json` — nothing in the schema says belief A should sit
physically near belief B, so the simulation manufactures a spatial relationship from
nothing, and because the manufactured relationship has no fixed point, *every* re-layout
drifts. The owner's complaint ("constantly moves because nodes push each other") is
therefore not a tuning problem (lower repulsion, add damping) — it is the simulation doing
exactly what it is told, correctly, to a dataset that never asked for an x/y position.

### 2.2 Layout: rings, not physics

**Fixed positions, computed once from a declared taxonomy, never from force.** The exact
pattern already exists in this codebase at `frontend/src/app/brain/page.tsx` lines 50-78
(`GROUPS`: a declared array of `{title, match}` that buckets probe rows into cards) — the
same idea, applied to belief topics instead of health probes:

- **A `TOPIC_CLUSTERS` table, declared in code, not derived from data at render time.**
  `beliefs.json`'s `affected_entities.sectors` *does* exist per-belief (e.g. `ai_demand` →
  `["hardware", "internet", "semiconductors", "software"]`), but a belief can carry
  *several* sectors at once — it is not a partition, so it cannot drive a single ring
  position by itself. Declare three or four fixed rings instead (example only, the owner
  picks the real taxonomy): an inner **macro** ring (`rates`, `inflation`, `credit`,
  `dollar`, `liquidity`), a middle **sector/theme** ring (`ai_demand`,
  `semiconductor_capex`, `grid_power_demand`, `commodity_shortages`, `energy_security`),
  an outer **geopolitical/regulatory** ring (`china_policy`, `geopolitical_risk`,
  `defense_procurement`, `biotech_regulatory`), with a belief's *secondary* sectors drawn
  as thin cross-ring edges rather than relocating the node.
- **Angle within a ring is a stable hash of the topic id**, not a layout pass — the same
  topic always lands at the same angle, every render, every day. Nothing moves unless the
  taxonomy itself changes (a new topic is added — rare, declared, reviewed).
- **This means the whole canvas is deterministic from `beliefs.json` alone** — no
  simulation step, no "settle" animation on load, no two renders of the same data ever
  disagree.

### 2.3 Visual channel → exact field (and what is NOT in the data yet)

| Owner's channel | Field in `beliefs.json` / `scenarios.json` | Notes |
|---|---|---|
| Orb = belief | one entry per key in `beliefs.beliefs` (16 today) | `topic`, `meaning` give the label and the one-line gloss already written for humans |
| Size = confidence | `confidence` (0.0–1.0, e.g. `ai_demand` 0.41, `dollar` 0.277) | direct, no transform needed beyond a min-radius floor so a 0-confidence belief is still clickable |
| Pulse = fresh event (within N hours) | `evidence_this_cycle` (bool) + `last_updated`; precise recency from `belief_updates_<month>.jsonl`'s `hours_since_prior` | the per-cycle digest only has a boolean "something happened this cycle"; the **hour-level age** needed for an "N hours" threshold lives in the append log, not the snapshot — read both |
| Brightness = evidence strength | `n_root_events_this_cycle` / `n_new_root_events_this_cycle`, or `mass_up + mass_down` (total evidential mass before direction is netted) | `evidence_basis` is a prose string ("3 new vote(s) from 34 new root event(s) of 250") written for a human, not a number — don't re-parse it; use the numeric fields it was built from |
| Colour / state = bullish / bearish / uncertain / contradicted | `direction` ∈ `{up, down, mixed, none}` today (not literally "bullish/bearish" — these are **macro-belief** directions, e.g. `ai_demand: up` means demand strengthening, not "stock goes up"); `contradictions` (list) → **contradicted** state exists in the schema but is **empty on every one of the 16 live beliefs** as of this digest — the state is real, just unobserved today, so do not hardcode it out | map `up→warm colour, down→cool colour, mixed→a third neutral-but-not-grey colour (distinct from "no data"), none→grey (literally no signal, confidence 0)`; `none` and low-confidence `mixed` are different things and must not share a colour |
| Connections = causal/evidence links | `co_mention_edges[]`: `{to, sign, lag_sessions, support, example_theme}` | this *is* a real edge list, already directional and signed |
| Connection thickness = marginal contribution | **Not available at the belief-graph level.** The nearest real "marginal contribution" number in this codebase is in `backend/services/regret_ledger.py` (`TRUST_AT_63` label, gated at `TRUST_SESSIONS = 63` graded sessions — a book/decision-level attribution number, not a belief-co-mention number) and `services/attribution.py`'s MCTR (portfolio risk attribution, also unrelated to beliefs). The honest proxy today is `co_mention_edges[].support` (how many corroborating observations back that edge) — **label it "co-mention support", not "marginal contribution"**, until a belief-level attribution number exists |
| Dashed = contradiction | would read `contradictions[]` non-empty, or a `sign` mismatch between two edges pointing the same direction pair | same caveat as above: build the rendering path now, verify it against a live contradiction once one appears (none has, in this snapshot) |
| Clusters = sectors/themes/regimes | `affected_entities.sectors[]` (per belief, many-to-many) feeds the ring assignment in §2.2; `scenarios.json`'s `beneficiary_sectors` / `loser_sectors` per scenario is a second, scenario-level clustering that could drive an optional "scenario overlay" toggle, not the default layout | |
| Movement = changing world state | **Animate once, on a detected change, then stop.** A change is: `direction != prior_direction` (flip — the `belief_updates` log carries `prior_direction` directly), `|belief_change|` above a small floor (drift), or a brand-new `contradiction` field in the update row. No change → no motion, ever, including no idle "breathing" loop — that idle loop is exactly the "constantly moving" complaint restated | |
| "What changed since yesterday" mode | `belief_updates_2026-10.jsonl`, filtered to rows with `t` ≥ yesterday's digest's `as_of`; each row already carries `belief_change`, `new_up`, `new_down`, `contradiction`, `hours_since_prior` | this is a **second, explicit view** (a toggle or a date-diff control), not a permanent overlay — render the ring at rest, then replay only the rows in that filtered window as one-shot pulses in chronological order |

**Legend:** fixed panel outside the canvas bounding box (below or beside, never
overlaid on the data), state-driven (lists only the colours/sizes actually present in the
current snapshot, not every theoretical state — so an unused `contradicted` state does not
clutter the legend until it is observed), and never animated itself.

**Accessibility:** every motion-driven affordance (the pulse, the one-shot flip animation)
must have a `prefers-reduced-motion: reduce` fallback that is a **static visual delta**
carrying the same fact (e.g. a small "changed" badge with the same colour swap, no
animation) — per Fluent 2's rule in §1.4, not a slowed-down version of the same motion.

### 2.4 Three implementation options

| | A — SVG/CSS in React | B — p5.js instance (client component) | C — p5.brush generative background + SVG data layer |
|---|---|---|---|
| New dependency | **None** | p5.js (~970 KB min / ~278 KB gz, see §1.1) | p5.js + p5.brush (~70 KB more) |
| Rendering | DOM `<svg>` circles/lines/`<text>`, CSS transitions for the one-shot state-change animation, CSS custom properties for colour tokens (reuses the app's existing light/dark theme machinery) | Canvas, imperative draw loop, manual hit-testing for click/hover | p5.brush paints an ambient organic backdrop on its own canvas (WEBGL); the actual belief orbs/edges are a separate SVG layer stacked on top, so data stays inspectable (DOM, testable) while the backdrop stays purely decorative |
| Fits "state-driven, not simulated" | Natural fit — SVG elements are plain positioned elements with CSS transitions, which only fire on a value change, by construction | Fit, but you re-implement what CSS transitions give for free (debouncing when nothing changed, respecting reduced-motion) | Same as A for the data layer; the backdrop needs its own discipline to stay inert when nothing changed, since p5's draw loop runs every frame by default (must gate on a changed-flag) |
| Testability / "every orb traces to a receipt field" | Easiest — a snapshot test can assert the rendered SVG attributes equal the field values, same style as the repo's existing `test_opportunities_router.py` shape tests | Harder — values live in canvas draw calls, not inspectable DOM | Data layer: same as A. Backdrop: not testable and not meant to be — it carries no claim |
| Static desktop export (`AEGIS_DESKTOP_BUILD=1`) | Trivially compatible — pure React/CSS | Compatible (client-only component, see §1.1) | Compatible, same reasoning, slightly heavier bundle |
| Best for | **The `/brain` page** — it has to carry a receipt-traceable claim, match the rest of the app's component system (`Card`, `Badge`, theme tokens already in `brain/page.tsx`), and be cheap to keep honest over time | A dedicated full-canvas showcase where imperative control over many small moving parts earns its keep | **The personal-portfolio piece** — no receipt obligation, the generative backdrop *is* the point, and p5.brush's organic trails give the "network trails / generative identity" look the owner referenced without pretending the trails mean anything in the data |

**Recommendation:** **Option A for `/brain`**, **Option C for the portfolio piece.** The
brain page's job is to be checkable against a receipt; a canvas-only render makes that
harder for no visual gain the owner asked for (the ask was "motion must mean something,"
not "must use canvas"). The portfolio piece has no such obligation and is exactly where
p5.brush's generative identity work (flow-field trails suggesting "a system that is always
sensing") belongs.

---

## 3. GitHub identity plan

### 3.1 README audit, as it stands today

**Already strong, keep:** the badge row (live-app, test count, stack, licence); the
rung-by-rung "skim → read ladder" (§ "Start here") that tells a reader exactly how much to
read; the three-licence table; the evidence-badge legend (🟢🟡⚪🔵🟣🔴🔶) used consistently;
the V1 Beta scoreboard printing `RESULT IMPROVEMENT: NONE` up front and naming a receipt
beside every number; the two Mermaid flowcharts (the corpse-check gauntlet, and "the brain
in one picture"); the "what it does / does NOT do" split; the honest 44-of-277 historical
result stated as "not demonstrated" rather than rounded up.

**What reads "more vanilla than the system" (the owner's own phrase), concretely:**

- **No hero visual.** The README opens straight into badges and prose; there is no single
  image that tells a 5-second scanner what this *is* before they read a word. Every other
  signal in the README (scoreboard, charts) assumes the reader already decided to read.
- **No OG/social-preview image** — confirmed by listing `docs/assets/` (17 files, all
  chart PNGs from `tools/readme_charts.py`) and the repo root: nothing sized for a link
  unfurl exists. A link to this repo on Discord/Twitter/Slack renders as plain text or
  GitHub's generic placeholder today.
- **`frontend/public/logo.png` is never surfaced in the README** — it exists and is used
  inside the app's own chrome, but a GitHub visitor never sees it; the repo's public face
  and the product's in-app identity are disconnected.
- **The architecture is communicated twice, in two different registers** — the ASCII tree
  under "Architecture" and the Mermaid flowchart under "The brain, in one picture" — both
  good content, both rendered as plain GitHub-Mermaid, which is legible but generic; every
  other finance/ML OSS repo on GitHub renders Mermaid the same way.
- **No screenshots of the actual product.** The README describes `/opportunities`,
  `/brain`, the paper lanes, the track record — all real, running pages — but a reader
  never sees one. The chart PNGs are analysis outputs, not product screenshots.
- **Typography and colour are whatever GitHub's default Markdown theme gives**, which is
  the same experience as every other repo; nothing in the README is visually distinct to
  the project the way the scoreboard's *content* already is.

### 3.2 Concrete list

| Item | What | Who does it |
|---|---|---|
| **Logo/icon system** | The owner has `Aegis Finance white only logo.PNG` and `Aegis Finance resize.png` in Downloads — **record as assets to review, not copied into the repo by this document.** Candidate system: one mark that works at favicon size (16×16 monochrome), one lock-up (mark + wordmark) for the README hero and OG image, reusing `frontend/public/logo.png` as the in-app version if it already matches, or reconciling the two if they differ | **Owner** picks/approves the mark; Sonnet can produce SVG variants and size exports once a source mark is chosen |
| **Typography** | Pick one display face for the README hero / OG image (does not have to be, and should not be, a webfont dependency inside the app — this is a static-image concern only) and keep body copy as GitHub-default Markdown, which already reads well given the content quality | **Sonnet** can propose 2-3 pairings and render samples; **owner** picks |
| **README hero section outline** | A single banner image (not a chart) at the very top, above the badge row: mark + "Aegis Finance" + a one-line tagline already in the README's first paragraph ("a self-improving investment intelligence system that measures itself in public and tells you when it is wrong"), plus 3-4 numerals pulled from the existing scoreboard (books priced, forward-record start date, test count) rendered as a visual strip, not prose | **Sonnet** can draft the layout and copy; **owner/designer** for the final static asset |
| **Architecture visual** | The pipeline Mermaid in `docs/AEGIS_V1_BETA_2026-10-07.md` §2 (`flowchart LR`, 8 stages: Sensors → Evidence → Forecasts → Decision → Paper execution → Outcomes → Attribution → Learning, with the feedback edge back to Decision) is the right diagram to promote — it is already accurate and current (named modules + receipts per the state-on-2026-10-07 table). Render it as a **static branded SVG** (not GitHub's default Mermaid renderer) using the chosen colour tokens and the logo mark on the feedback loop, and commit it to `docs/assets/architecture_pipeline.svg`; the README's existing Mermaid block can stay underneath as the "see it live-rendered" fallback | **Sonnet** can author the SVG from the Mermaid source (it's a straight re-skin of an already-correct diagram, not new content); **owner** reviews before it is called canonical |
| **Screenshots list** | `/opportunities` (Opportunity Explorer table with a badge/flag row visible), `/arena` or the current equivalent (Decision Story graphic once C11's live decision story exists — it does not yet, per `AEGIS_V1_BETA_2026-10-07.md` §2 row "Attribution"), `/brain` (once §2's state-driven version ships), `/dev` or `/health` (the health-probe grid) — four screenshots, each captioned with the one sentence the README already uses to describe that surface | **Sonnet** can capture these with Playwright against a running dev build once each page is stable; recapture after any visual change, don't let them go stale the way `funnel_night10.json` did |
| **OG/social-preview asset** | 1200×630 PNG, GitHub's own spec; mark + wordmark + the tagline, no scoreboard numbers (they go stale and an OG image is cached by platforms for a long time) — set via repo Settings → Social preview, and duplicate the same file to `docs/assets/og_preview.png` so it's versioned | **Sonnet** can produce the layout once the mark is chosen; **owner** uploads to repo settings (not something Sonnet has access to) |
| **Asset location** | `docs/assets/` already exists and already holds every chart PNG this README cites, generated only by `tools/readme_charts.py` ("never hand-edited," per the repo map). The new identity assets (hero, architecture SVG, OG image, screenshots) are **hand-authored**, so they should NOT live in that same folder under that same "generated, never hand-edited" convention — propose `docs/assets/identity/` as a sibling folder, hand-authored and explicitly exempted from the "never hand-edited" rule | **Sonnet** can create the folder and first assets; **owner** names the convention |
| **Small animations** | Scope to places a static image can't carry the information cheaply: a 2-3 second looped GIF/WebM of the `/opportunities` sort interaction, or the Brain page's one-shot belief-flip animation (§2.3) captured once it exists. Not a hero-image animation — that fights the "serious technical product" tone the owner also asked for | **Sonnet** can capture once the underlying page exists; keep each clip under ~2 MB so the README stays fast |

**What needs the owner or a designer, not Sonnet:** final mark selection (reconciling the
two Downloads logo files or commissioning a new one), typography license/purchase if a
paid font is chosen, the actual repo-settings OG upload, and any claim about what the
visual identity "means" that isn't already a sentence in the existing README — Sonnet can
produce assets and layouts, not brand decisions.

---

## 4. What would make the Brain page honest

- **Every orb must trace to a receipt field.** Concretely: a belief orb's size must equal
  `beliefs.json[topic].confidence` at render time, not a designer's eyeballed radius: if
  the field is 0, the orb is the minimum-visible floor, never a "looks about right"
  guess. The same discipline the README already applies to numbers ("a headline number
  belongs in a receipt," `CLAUDE.md`) applies to every pixel of this visual, because a
  visual is a number rendered, and an unsourced pixel is an unsourced number with a nicer
  font.
- **No decorative nodes.** If a ring position, a connecting line, or a pulse exists on
  the canvas and there is no field in §2.3's table backing it, it does not ship — including
  "it looks empty otherwise." An empty ring is the honest rendering of zero beliefs in that
  cluster today; a placeholder orb invented to fill the space is the exact failure mode
  `docs/research_notes/.../opportunity_explorer_2026-10-06.md` was written to stop (a 404
  rendered as zeros, rather than as the fact that it is a 404).
- **Why a force graph misrepresents a belief table, in one sentence (expanded from
  §2.1):** `beliefs.json` has no "distance" field between two beliefs — it has a signed,
  lagged, supported **edge** (`co_mention_edges`), which is a *directed claim about the
  world* ("ai_demand leads grid_power_demand by 5 sessions, support 2"), and a force layout
  converts that directed claim into an *undirected spatial attraction*, discarding the
  sign and the lag and inventing a settling position neither field asked for. The result
  looks like a living network because the simulation is alive — the data, read honestly,
  is a table of sixteen rows with timestamps and confidence scores that changes a few
  times a day. Rendering it as something that visibly moves every second is not a
  stylistic choice; it is a visual claim ("this is turbulent, causally entangled, always
  in motion") that the underlying evidence does not make.

---

## Recommendation summary (for the one-line report)

- **Brain page:** Option A (SVG/CSS in React, zero new dependency, state-driven rings,
  receipt-traceable).
- **Portfolio piece:** Option C (p5.brush generative backdrop + SVG data layer).
- **Three best public references, with URLs:**
  [p5.brush](https://github.com/acamposuribe/p5.brush) (MIT, flow fields/hatching/
  watercolor, instance mode confirmed) ·
  [thinking-orbs (Jakub Antalik)](https://github.com/Jakubantalik/thinking-orbs) (MIT,
  9 states, 2D canvas, cross-browser, two fixed sizes) ·
  [Fluent 2 Motion](https://fluent2.microsoft.design/motion) (duration/easing tokens +
  mandatory reduced-motion rule, directly reusable for the one-shot state-change
  animation rule in §2.3).
- **GitHub identity checklist, one line each:** logo/icon system (owner picks from two
  Downloads assets, Sonnet renders variants) · typography for the hero/OG image only
  (Sonnet proposes, owner picks) · README hero section (Sonnet drafts layout+copy from
  existing scoreboard numbers) · architecture visual as a branded static SVG of the
  already-accurate pipeline Mermaid (Sonnet authors, owner approves) · four product
  screenshots captioned from existing README sentences (Sonnet captures via Playwright
  once each page is stable) · 1200×630 OG asset (Sonnet produces, owner uploads to repo
  settings) · identity assets in a new `docs/assets/identity/` folder, kept separate from
  the generated-chart convention · small animations scoped to real interactions, not a
  hero flourish.
