# docs/assets: the public asset registry

Every file in this folder is produced by the command in its row; none is hand-edited (the README's
repo map says the same of this folder). **Licence of every file here: MIT**, the repository
[`LICENSE`](../../LICENSE) (Copyright (c) 2026 Murathanx12).

The identity assets follow the visual language the owner chose on 2026-10-07
([`docs/design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md`](../design/AEGIS_VISUAL_LANGUAGE_2026-10-07.md)):
style C (the orbit) on the front page, style A (the blackline) for explanation diagrams, animated
SVG only. The live results panel is the one asset that carries numbers; each is read from a pinned
receipt and labelled with its evidence rung.

## Identity assets (2026-10-07, restyled the same day)

| file | source / generator | purpose | generated or manual | update command |
|---|---|---|---|---|
| `aegis_loop.svg` (1200 × 1000) | [`scripts/render_public_assets.py`](../../scripts/render_public_assets.py) `render_hero`, table `STAGES` | README hero (style C): the nine stages on a dotted orbit; a blue wave dwells at each stage while its bubble grows; learning feeds the next cycle through two orange inner orbits | generated; stdlib only, byte-for-byte deterministic | `python -m scripts.render_public_assets` |
| `paper_results_live.svg` (1200 × 470) | the same generator, `render_results`; numbers from `backend/data/optimus/paper_accounts/roi_<RESULTS_RUN_ID>.json` + `book_dna_<RESULTS_RUN_ID>.json`, the chart from every dated `roi_*.json` up to that run | README, under the badges: the best strategy account in each of three families against SPY over its own window, the lead account against its matched random twin, the selection rule and its denominator | generated; deterministic (receipts are tracked) | bump `RESULTS_RUN_ID`, then `python -m scripts.render_public_assets` |
| `architecture_pipeline.svg` (1200 × 1060) | the same generator, `render_pipeline` | README "The brain, in one picture" (style A): every stage card lists the modules that run it | generated; deterministic | `python -m scripts.render_public_assets` |
| `og_preview.svg` (1200 × 630) | the same generator, `render_og`; the sentence is §1 of [`docs/AEGIS_V1_BETA_2026-10-07.md`](../AEGIS_V1_BETA_2026-10-07.md), verbatim; the tagline is §1 of [`docs/FUNDING_EVIDENCE_PACK_2026-10-07.md`](../FUNDING_EVIDENCE_PACK_2026-10-07.md) | source of the social-preview card (style C, static: platforms rasterise it once); no embedded image | generated; deterministic | `python -m scripts.render_public_assets` |
| [`docs/design/aegis_front_page.html`](../design/aegis_front_page.html) | the same generator, `render_front_html` | the motion page: the hero inline, the results as cards whose numbers count up, the chart; self-contained, no network | generated; deterministic | `python -m scripts.render_public_assets` |
| `og_preview.png`, `logo.png` | the earlier identity pass (2026-10-07 morning) | **superseded**: no asset and no README line uses them any more; the owner asked for no PNGs in git, and removing these two files is his call | — | — |

**What keeps them honest.** [`backend/tests/test_public_assets.py`](../../backend/tests/test_public_assets.py)
fails when a committed file differs from a fresh render, when a module path printed in a diagram
stops existing or a function printed beside it (`u_plan`, `AegisSimOwner`, ...) stops being
defined, when a number on the results panel differs from its receipt, when the featured accounts
are not what the declared selection rule picks (recomputed independently), when the dot wave and
the stage bubbles fall out of step, when an SVG could load anything external or carries an image,
or when the README shows an asset that is not here. Without pytest:
`python -m scripts.render_public_assets --check` (exit 1 when a file is stale; writes nothing).

**Changing a picture.** Edit `STAGES` (or the loop constants) in the generator, re-render, and
commit the generator and every output together. Strings are kept inside fixed character budgets
(`MAX_*_CHARS`) measured for the widest common fallback fonts (DejaVu Sans / Sans Mono), because
SVG text does not wrap.

### The social preview

GitHub's social preview accepts PNG or JPG, not SVG, and a PNG is never committed here. Export
it locally and upload it (any Chrome or Chromium):

```bash
chrome --headless --hide-scrollbars --window-size=1200,630 \
  --screenshot="$HOME/og_preview.png" "file://$PWD/docs/assets/og_preview.svg"
```

Then GitHub → the repository → Settings → General → Social preview → Edit → Upload an image.

## README figures (generated from receipts)

| file | generator | data it reads | shown in | update command |
|---|---|---|---|---|
| `learner_v1_engine_is_silent.png` | [`tools/readme_charts.py`](../../tools/readme_charts.py) `chart_learner_v1` | `backend/data/optimus/tracker_backtest/learner_v1.json` | README "The newest results" §1; `docs/INDEX.md` | `python tools/readme_charts.py learner_v1` |
| `band_prior_by_horizon.png` | `tools/readme_charts.py` `chart_band_prior_horizon` | the same receipt | README "The newest results" §2; `docs/INDEX.md` | `python tools/readme_charts.py band_prior_horizon` |
| `lanes_small_multiples.png` | `tools/readme_charts.py` `chart_lanes_small_multiples` | the live track-record API (`/api/pi/track-record` on the Railway backend; needs network) | README "The newest results" §3 | `python tools/readme_charts.py lanes_small_multiples` |
| `paper_lanes_vs_spy.png` | `tools/readme_charts.py` `chart_lanes` | the same API | no document shows it at 92f147f | `python tools/readme_charts.py lanes` |
| `finding_market_graph.png` | `tools/readme_charts.py` `chart_market_graph` | `../Aegis module/runs/MARKET-GRAPH-1/grade_report.json` (the sibling `Aegis module` checkout, not this repo) | README "The findings, in pictures" | `python tools/readme_charts.py market_graph` |
| `finding_covariance_ladder.png` | `tools/readme_charts.py` `chart_covariance_ladder` | `../Aegis module/runs/GRAPH-COVARIANCE-1/grade_report.json` (sibling checkout) | README "The findings, in pictures" | `python tools/readme_charts.py covariance_ladder` |
| `finding_direction_vs_magnitude.png` | `tools/readme_charts.py` `chart_direction_vs_magnitude` | four values written in the function; its comment sources them to `Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md` | README "The findings, in pictures" | `python tools/readme_charts.py direction_vs_magnitude` |
| `paper_accounts_roi_latest.png` and the dated `paper_accounts_roi_<date>.png` (2026-09-26 to 2026-10-06) | [`scripts/paper_accounts_roi.py`](../../scripts/paper_accounts_roi.py) `render_chart` | its own receipt, `backend/data/optimus/paper_accounts/roi_<date>.json` (the live API plus read-only broker reads) | `latest`: README "The track record, precisely" and `docs/PAPER_ACCOUNTS.md`; the dated files are the archive | `python -m scripts.paper_accounts_roi` (the daily pass's `paper_accounts` step runs it) |

`python tools/readme_charts.py` with no argument redraws all seven figures; it needs the network and
the sibling `Aegis module` checkout.
