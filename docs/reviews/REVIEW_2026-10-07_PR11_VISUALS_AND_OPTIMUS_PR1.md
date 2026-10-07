# Review 2026-10-07: Aegis PR #11 (visuals/docs only) and Optimus PR #1

Scope: docs/visual surface only. PR11's backend code (forecast ledger split,
evidence population, system_health, etc.) is covered by a separate reviewer
and is NOT assessed here. Both PR branches were read and tested in their
existing detached worktrees (`C:\Users\mrthn\aegis-finance-pr11` @ `904ba019`,
`C:\Users\mrthn\optimus-pr1` @ `2a201e3`); neither worktree nor the manager's
checkouts (`aegis-finance` @ `wip/2026-10-07-day`, `optimus`) were switched,
stashed or reset. Nothing was pushed or committed to either PR branch.

---

## Verdicts

| PR | Verdict |
|---|---|
| **Aegis #11** (visuals/docs) | **MERGE AFTER FIXES** — one real finding (F1: committed PNGs contradict the PR's own "no PNG in git" policy, stated twice in files this PR adds). Everything else checked (tests, SVG safety, number provenance, citations) is clean. |
| **Optimus #1** | **MERGE** — all tests pass, the privacy boundary is enforced in code and pinned by a test, skill lookup priority is correct and tested. One unresolved observation (F6, an intermittent unprompted scroll on the showcase page) is reported but not reproducible cleanly enough to block merge; recommend a quick manual check in a real (non-headless) browser before or shortly after merge. |

---

## Part 1 — Aegis PR #11 (visuals/docs)

### Commands run

| command | exit |
|---|---|
| `python -m scripts.render_public_assets --check` | **0** — all 6 outputs OK (`aegis_loop.svg`, `paper_results_live.svg`, `architecture_pipeline.svg`, `gauntlet.svg`, `og_preview.svg`, `aegis_front_page.html`) |
| `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 python -m pytest -q -p no:cacheprovider backend/tests/test_public_assets.py` | **0** — 31 passed in 5.28s |
| `python -m scripts.research_intake_check --check-index` | **0** — 10/10 cards valid, 0 errors, 0 warnings, `INDEX.md` current |

### (a)/(c) Generator, tests, numbers

All green. Cross-checked the README results panel against the receipts it cites:

- `revision_flow_v0` +7.14% vs SPY +1.40%, +5.74pp, `OBSERVED(7)`
- night book `b109c886` +6.08% vs SPY +2.19%, +3.90pp, `OBSERVED(17)`
- `hack2` +2.31% vs SPY +1.29%, +1.02pp, `OBSERVED(27)`

These numbers are identical across `paper_results_live.svg`, `aegis_front_page.html`,
the README's alt text and prose (`README.md:25,95-96,107`), and the source receipts
`backend/data/optimus/paper_accounts/roi_2026-10-06T235345Z.json` and
`book_dna_2026-10-06T235345Z.json` — verified by direct inspection of the JSON, not
just by the passing test.

**RESULTS_RUN_ID is a manually bumped constant** (`scripts/render_public_assets.py:417`,
`"2026-10-06T235345Z"`). I found no scheduled caller anywhere in the diff — the
`docs/assets/README.md` table itself documents the refresh as a manual two-step
("bump `RESULTS_RUN_ID`, then `python -m scripts.render_public_assets`"), and
`backend/tests/test_public_assets.py` only checks that the committed SVG/HTML bytes
match a fresh render of the PINNED id — there is no check on how OLD that pinned
receipt is (no analogue of `investment_committee.FUNNEL_STALE_DAYS`). **Recommendation**
(not a blocker): add a staleness guard on `RESULTS_RUN_ID`'s age in days, and a
scheduled caller analogous to the funnel fix in CLAUDE.md's "THE REAL BOTTLENECK WAS
A STATIC FILE" section — attempt once per session, refuse-without-overwrite on
failure, and treat "ran but the id didn't move" as a reported failure, not a silent
success.

### (b) Visual inspection (Playwright, headless Chromium, served over `http://127.0.0.1`
since `file://` navigation is blocked by the MCP browser tool)

Screenshots saved under `docs/reviews/screenshots_2026-10-07/`:

- `pr11_aegis_loop_1200.png`, `pr11_aegis_loop_1200_t2.png` — two moments of the
  9-stage orbit; the wave dwells at a different stage in each, dot positions are
  otherwise static. No clipped or overlapping text.
- `pr11_paper_results_live_1200.png` — clean, legible, numbers match.
- `pr11_architecture_pipeline_1200_top.png` — 3x3 blackline grid, no overlap.
- `pr11_gauntlet_1200.png` — clean flowchart.
- `pr11_og_preview_1200.png` — static social card, confirmed no SMIL/CSS animation
  present in this file (see (c) below).
- `pr11_front_page_1200.png`, `pr11_front_page_1200_scroll1.png` — HTML motion page
  at 1200px, hero + results cards + chart, all legible.
- `pr11_front_page_390_top.png`, `pr11_front_page_390_chart.png` — mobile (390px):
  cards and chart reflow correctly; the embedded hero SVG scales down as a whole
  (same behavior a GitHub README gets on mobile), text stays sharp (vector), no
  horizontal scrollbar, no overflow.

**On the owner's "constantly moving" complaint about the old brain graph** (nodes
pushing each other): none of these five SVGs or the HTML page use a force
simulation. Every animated element's position is fixed in the markup; only
opacity/scale/stroke-dashoffset/motion-along-a-fixed-path change via CSS keyframes
or SMIL, matching `.claude/skills/aegis-motion-visuals/SKILL.md`'s own rule
("rings and declared grids, never a force simulation"). `aegis_loop.svg`'s wave
travels and dwells (0.8s travel / 1.2s dwell per the skill doc) rather than
looping continuously and chaotically. All five SVGs carry
`@media (prefers-reduced-motion: reduce){*{animation:none!important}}`.

### (c) SVG safety / GitHub `<img>` compatibility

```
grep -niE '<script|javascript:' docs/assets/*.svg        -> no matches
grep -niE 'xlink:href=.https?|href=.https?' docs/assets/*.svg  -> no matches
```

Confirmed also by `backend/tests/test_public_assets.py::test_each_svg_renders_through_an_img_tag_with_nothing_external_and_no_image`
(passing), which additionally forbids `foreignObject`, `iframe`, `use`, `image`.
Animation is CSS keyframes + SMIL (`<animate>`, `<animateMotion>`) only, both of
which GitHub's sanitizer preserves inside an `<img>`-embedded SVG. `og_preview.svg`
is the one static file (no `<animate*>` elements) — correct, matches its row in
`docs/assets/README.md`.

### (d) Design docs — accuracy and owner quotes

`docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md` and
`.claude/skills/aegis-motion-visuals/SKILL.md` are internally consistent with
what is actually built: spot-checked the "18s cycle, 9 stages, 2.0s/stage" claim
against `aegis_loop.svg`'s `@keyframes swell {... } animation: swell 18s linear
infinite` and the dot-wave screenshots (t1 at stage 2, t2 ~6s later at stage 1 of
the next pass) — consistent. I have no access to the original conversation with
the owner, so I cannot attest the quoted lines ("I really liked A...", "the blue
line should be little dots...") are verbatim; I can only say they are not
self-contradictory and track the shipped behavior. **One does contradict the
shipped repo state — see F1 below.**

### (e) The two PNGs

`docs/assets/logo.png` and `docs/assets/og_preview.png` are **not referenced**
anywhere in `README.md`, any `.html`/`.md`/`.tsx` file, except the one row in
`docs/assets/README.md:23` that documents them as superseded. (`frontend/public/logo.png`,
referenced in `frontend/src/app/layout.tsx:38-39` and
`frontend/src/components/sidebar.tsx:279,329`, is a different file — the in-app
favicon/sidebar logo — unrelated to these two.) See F1: despite being
"superseded" and unreferenced, they are newly committed by this PR.

### (f) `docs/research_intake/`

`python -m scripts.research_intake_check --check-index` → exit 0, 10/10 cards
valid, `INDEX.md` current (output above).

Spot-checked citations in 3 cards (7 papers total) against my own knowledge:

- `markowitz-1952-portfolio-selection.md`: Markowitz (1952) *J. Finance* 7(1):77-91
  — correct; DeMiguel, Garlappi & Uppal (2009) *RFS* 22(5):1915-1953 — correct.
- `post-earnings-announcement-drift.md`: Ball & Brown (1968) *J. Accounting
  Research* 6(2):159-178 — correct; Bernard & Thomas (1989) *J. Accounting
  Research* 27(Supplement):1-36 — correct.
- `monday-turnaround-effect.md`: Cross (1973) *Financial Analysts Journal*
  29(6):67-69 — correct; French (1980) *J. Financial Economics* 8(1):55-69 —
  correct; Lakonishok & Maberly (1990) *J. Finance* 45(1):231-243 — correct.

All seven check out (journal, volume, issue, pages match what I know of these
canonical papers). No fabrication found in this sample; the remaining 7 cards
were only checked structurally by the script, not spot-verified by me.

### Findings

**F1 (MEDIUM — fix before/at merge).** This PR commits two binary PNGs
(`docs/assets/logo.png`, `docs/assets/og_preview.png`, commit `d1fe4f4c`, still
tracked at HEAD `904ba019`) while two files this SAME PR adds assert the opposite
has already happened:

- `.claude/skills/aegis-motion-visuals/SKILL.md:48` — "**No PNG in git.** ... never
  committed."
- `docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md:41` — "'no PNGs' → every asset is
  SVG ...; nothing is rasterised into the repo."
- `docs/assets/README.md:23` itself says these two files are "superseded... the
  owner asked for no PNGs in git, and removing these two files is the owner's
  call" — i.e. the PR's own doc flags the inconsistency and defers the decision,
  but ships the inconsistency anyway.

Fix: either `git rm` the two PNGs in this PR (the row says they're dead weight —
unreferenced, superseded), or soften the two absolute claims above to acknowledge
two legacy files are still pending the owner's removal call. Either is a one-line
fix; I'd lean toward removing the files, since nothing on the branch uses them.

**F2 (LOW/INFO, recommendation only).** No staleness guard exists on
`RESULTS_RUN_ID`'s age — see (a)/(c) above.

### What I did not check (Part 1)

- PR11's backend code changes (forecast ledger split/migration, evidence
  population, system_health, query_planner, etc.) — explicitly out of scope,
  covered by a separate reviewer.
- The other 7 of 10 research-intake cards' citations beyond the script's
  structural pass (I spot-checked 3, as instructed).
- The live Vercel deployment (`aegis-finance-six.vercel.app`) — this review is
  of the worktree's files, not a deployed build.
- Screen-reader/accessibility behavior beyond the presence of `role="img"` +
  `aria-labelledby`/`<title>`/`<desc>` in each SVG (present in all five, confirmed
  by reading the files).

---

## Part 2 — Optimus PR #1

### Diff vs `main` (`git diff main...HEAD --stat`, 2 commits: `0abbe1a`, `2a201e3`)

```
.claude/skills/orbit-blackline-visuals/SKILL.md |  185 ++        (new)
mcp/server.py                                   |    9 +-
requirements.txt                                |    1 +
showcase/build.py                               | 1944 ++++++++++++++++-----
showcase/optimus-brain/index.html               | 2085 ++++++++++++++---------
tests/test_optimus_skills.py                    |  100 ++         (new)
tests/test_showcase.py                          |  195 +++         (new)
7 files changed, 3271 insertions(+), 1248 deletions(-)
```

`showcase/optimus-brain/brain.json` is **unchanged** by this PR (pre-existing from
`main`) — it's a small 20-page sample snapshot, not the production brain.

### Commands run

| command | exit |
|---|---|
| `python -c "import importlib.metadata as m; print(m.version('mcp'))"` | prints `1.27.0` — satisfies the new `mcp>=1.2,<2` pin (`requirements.txt`), so nothing needed to be skipped |
| `python -m pytest -q -p no:cacheprovider` (from `optimus-pr1` root) | **0** — 128 passed in 20.67s |

### `mcp/server.py` — new skill root and precedence

```diff
+OPTIMUS_SKILLS = _OPTIMUS_ROOT / ".claude" / "skills"
 SKILL_ROOTS: tuple[tuple[str, Path], ...] = (
     ("aegis", AEGIS_REPO / ".claude" / "skills"),
     ("terminal", ALPHA_TERMINAL_REPO / ".claude" / "skills"),
     ("user", USER_SKILLS),
+    ("optimus", OPTIMUS_SKILLS),
 )
```

`optimus` is deliberately LAST, so a same-named project skill wins. Pinned by
`tests/test_optimus_skills.py`:
- `test_optimus_root_is_this_repo_and_comes_last` — PASS
- `test_an_optimus_skill_is_served_by_root_and_by_bare_name` — PASS (bare-name
  lookup resolves; listing names the root)
- `test_a_project_skill_of_the_same_name_wins_and_the_clash_is_named` — PASS
  (verifies the override AND that the clash is surfaced in the listing, not
  silently shadowed)
- `test_every_optimus_skill_names_itself_and_says_when_to_use_it`,
  `test_every_path_a_skill_names_in_this_repo_exists` — PASS (the new
  `orbit-blackline-visuals/SKILL.md`'s frontmatter and the repo paths it names
  — `showcase/build.py`, `tests/test_showcase.py` — all exist)

### Privacy boundary (the cloud session's flagged concern)

`showcase/build.py` anonymizes every non-public project/page:
`anon_page.setdefault(r["id"], f"private-{len(anon_page) + 1}")` (line ~128),
`anon_proj` similarly for project names. `PUBLIC_PROJECTS = ("aegis-finance",
"aegis-quant-knowledge")` (line 49) — exactly 2. Retrieval-demo hits are built as:

```python
{"page_id": r["page_id"] if r.get("public") else None,
 "type": r["type"], "score": r["score"], "public": bool(r.get("public"))}
```

so a private hit's `page_id` is `None` by construction, never the real id — and
this is pinned by `tests/test_showcase.py::test_a_private_retrieval_hit_never_prints_its_id`,
which plants a fabricated private id/title (`"personal-diary-overview"`, `"Diary
— Overview"`) into a fake retrieval result and asserts neither string, nor
`"personal-diary"`, appears anywhere in the rendered HTML — only the literal
string "private page". **PASS.**

On "2 vs 14": the committed sample `brain.json`'s own stats show
`pages_by_project: {"private": 2, "aegis-finance": 4, "aegis-quant-knowledge": 2}`
(a 20-page toy snapshot, unrelated to this PR's diff). The more likely referent,
given `PUBLIC_PROJECTS` has exactly 2 entries, is "2 public projects vs. roughly
14 total projects in the real brain" — i.e. most of Optimus's corpus (robotics,
personal, coursework, etc.) is intentionally anonymized down to a neuron shape
and a `PRIVATE N` label, by design, and nothing in the demo-query path can
surface a real id for any of them. I did not run `showcase/build.py` against the
live production `index.db` (that would touch data outside this PR and the
reviewer's authorization); this conclusion is code- and test-level, not an
end-to-end dry run against the real corpus.

### Brain showcase screenshot and motion judgment

`showcase/optimus-brain/index.html` served locally, screenshotted at 1200px:
`optimus_brain_1200_t1.png`, `optimus_brain_1200_t2.png`. Layout is a declared
ring taxonomy (`MAP_RINGS`, never a physics simulation — confirmed in
`showcase/build.py`'s module docstring and by the fact neuron positions are
identical pixel-for-pixel between the two screenshots, only the orange
query-replay sweep and blue fact-pulses differ). This matches the "still neural
map" the commit title promises and does not reproduce the owner's "nodes push
each other" complaint — positions never move; only pulses travel along fixed,
already-drawn links, which the skill doc explicitly calls acceptable motion.

**F6 (unresolved, not blocking).** While testing, I observed `window.scrollY`
change with zero user interaction in 3 of 5 repeated page-load trials (to 133px,
1333px, and 2531px in different runs — the page's full height is ~3700px), while
2 of 5 clean trials (including one with `window.scrollTo` and
`Element.prototype.scrollIntoView` both monkey-patched to log every call, and a
separate one using a `PerformanceObserver` for `layout-shift`) showed **zero**
scroll events, **zero** logged scroll calls, and **zero** layout shifts. Reading
`showcase/build.py`, the only `scrollIntoView` call (line 1426) is inside a
`click` handler gated on `[data-demo]` buttons; the auto-advancing query-replay
timer (`tick()`/`setDemo()`) never calls it, and there is no `setInterval`,
simulated click, or `.focus()` anywhere else in the file that could trigger it
autonomously. I could not pin a reproducible cause in the page's own code, and
the inconsistent magnitude across runs is more consistent with an artifact of
reusing a Chromium tab/context across repeated MCP tool calls than with a page
defect — but I can't rule out a real bug from here. **Recommend**: before or
shortly after merge, open the page in a normal (non-headless, single fresh tab)
browser and watch the scroll position for ~10s after load with no input; if it
moves, that's the "page moves under you without asking" failure mode the owner's
original complaint was about, just via scroll instead of node physics.

### Findings

- No code-level findings beyond F6 (unconfirmed). Tests are comprehensive
  (`test_showcase.py` covers layout determinism, anonymization, and privacy;
  `test_optimus_skills.py` covers the new skill root's existence, precedence,
  and clash-naming) and all pass.

### What I did not check (Part 2)

- Did not run `showcase/build.py` against the real `optimus/brain/index.db` —
  all privacy-boundary verification is code + test level, plus inspection of
  the pre-existing (unchanged-by-this-PR) committed `brain.json` sample.
- Did not confirm the scroll anomaly (F6) in a real, non-headless browser —
  flagged for the author/owner to check directly.
- Did not review the live Vercel deployment of `optimus-brain-alpha.vercel.app`.
- Did not audit the other, pre-existing commits on the branch (`b0c0330`,
  `84108c4`, `fb59c6a`) — confirmed via `git log main..HEAD` that only `0abbe1a`
  and `2a201e3` are actually new relative to `main`; the rest are already merged.

---

## Screenshots

All under `C:\Users\mrthn\aegis-finance\docs\reviews\screenshots_2026-10-07\`:

- `pr11_aegis_loop_1200.png`, `pr11_aegis_loop_1200_t2.png`
- `pr11_paper_results_live_1200.png`
- `pr11_architecture_pipeline_1200_top.png`
- `pr11_gauntlet_1200.png`
- `pr11_og_preview_1200.png`
- `pr11_front_page_1200.png`, `pr11_front_page_1200_scroll1.png`
- `pr11_front_page_390_top.png`, `pr11_front_page_390_chart.png`
- `optimus_brain_1200_t1.png`, `optimus_brain_1200_t2.png`
