# The academic lane, built and run once live (Q12, 2026-10-07)

**Role: Sonnet builder.** Implements the decision table and receipt schema
`docs/research_notes/2026-10-07/research_instruments_2026-10-07.md` already
designed, at $0, keyless, with nothing written into any research-intake card.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE.** This is lane infrastructure, not a strategy result. |
| New module | `backend/services/research_instruments.py` -- OpenAlex, CrossRef, NBER RSS (adopt now, $0, keyless); Semantic Scholar/arXiv gated behind an owner-declared key/opt-in (`InstrumentKeyRequired`, measured 429 keyless on 2026-10-07). |
| New caller | `python -m scripts.research_lane --card/--list/--due`; `python -m backend.services.query_planner --academic --card <slug>` (thin alias); `python -m scripts.task_keeper research` (weekly, additive, `daily_pass.py` untouched). |
| Cards instrumented | All 5 research-intake cards gained an optional `## Needs evidence` section (1-3 open questions each); `docs/research_intake/README.md`'s template carries the field. |
| Tests | 21 new (`test_research_instruments.py`) + 1 guard-contract case, all green; `test_query_planner.py` / `test_signal_reachability.py` / `test_guard_missing_input_contract.py` unaffected (216 passed total, see below). |
| Live run | ONE card, real network, real result below -- two real findings (one on-mechanism, one a precision caveat). |

## Files changed

- `backend/services/research_instruments.py` (new) -- fetchers, normalisers, the decision table (`probe_question`), the per-card lane (`probe_card`), card parsing (`card_verdicts`/`card_needs_evidence`/`card_seed_citations`), novelty (`is_novel`), the `InstrumentKeyRequired` guard.
- `scripts/research_lane.py` (new) -- the CLI caller (`--card`, `--list`, `--due`).
- `backend/config.py` -- `RESEARCH_INSTRUMENTS_*` block (enabled flag, day cap `QUERY_PLANNER_ACADEMIC_QUERIES_DAY=12`, default/extended budgets, stop coverage, min verified, mailto, Semantic Scholar key slot, arXiv opt-in, HTTP timeout) and `RESEARCH_LANE_EVERY_DAYS`/`RESEARCH_LANE_TIMEOUT_MIN` for the weekly job.
- `backend/services/query_planner.py` -- `academic_budget()` and a `--academic --card <slug>` CLI alias; `SEED_LANES`/`classify_url`/the admission pipeline are **untouched** (a citation is not a URL for the reader to admit, so it does not belong in that pipeline).
- `scripts/task_keeper.py` -- `TASK_RESEARCH` / `research_lane_due()` / `run_research_lane()`, the `research` job, and a weekly Sunday 11:00 HKT scheduler line in `owner_registration_ps()`. `daily_pass.py` not touched.
- `docs/research_intake/README.md` -- the card template gains an optional `## Needs evidence` field, documented.
- `docs/research_intake/cards/*.md` (all 5) -- each gained a `## Needs evidence` section: `lou-polk-skouras-2019-overnight-intraday` (3), `analyst-revision-momentum` (2), `markowitz-1952-portfolio-selection` (2), `monday-turnaround-effect` (2), `post-earnings-announcement-drift` (1 -- kept for a future RESURRECTION even though its `ALREADY_CLOSED`-only verdict means the lane refuses to run on it unattended).
- `backend/tests/test_research_instruments.py` (new, 21 tests) -- normalisation (real OpenAlex/CrossRef fixtures + synthetic NBER/arXiv XML), the keyless-refusal guard, novelty detection, card parsing, the lane's own day cap (including a cap already spent by an earlier run), and every named zero.
- `backend/tests/fixtures/research_instruments/openalex_lou_polk_skouras.json`, `crossref_lou_polk_skouras.json` -- fetched ONCE live this session for the Lou-Polk-Skouras query (not synthesised).
- `backend/tests/test_guard_missing_input_contract.py` -- `_case_research_instruments` added and enrolled in `CASES`.

## Design notes that matter

1. **The academic lane is deliberately NOT folded into `query_planner`'s `SEED_LANES`.** That pipeline's whole machinery (`classify_url`, admitted/quarantined/refused, the reader's queue) exists to decide whether a URL is safe to hand to the browser. A citation is not a URL for the reader to admit -- it is bibliographic metadata the lane writes straight to an evidence file. Reusing the SAME *shape* (own per-day cap in config, a declared-provider-style gate for the two unreliable instruments, named zeros on every receipt) without reusing the same *code path* keeps the web-search admission logic's own tests (`test_query_planner.py`, untouched) meaningful.
2. **`RESEARCH_INSTRUMENTS_MAILTO` defaults to `None`, not the owner's email.** OpenAlex/CrossRef's "polite pool" `mailto` param is sent to an external service on every call; both instruments were measured working keyless (no 429) on 2026-10-07, so the polite pool is a speed upgrade an owner can opt into later, never a default.
3. **Semantic Scholar and arXiv raise `InstrumentKeyRequired`, never silently skip.** This is the module's own guard (enrolled in `test_guard_missing_input_contract.CASES`), and the lane's orchestration (`_try_instrument`) catches it and turns it into a named-zero attempt (`KEY_REQUIRED_OR_RATE_LIMITED`) rather than letting it propagate -- a per-question failure of one instrument never aborts the whole probe.
4. **A bug the live run exposed and the test suite now pins**: `_fetch()` was passing raw HTTP bytes straight to `normalize_openalex`/`normalize_crossref`/`normalize_semantic_scholar`, which expect parsed JSON (only the XML parsers, NBER RSS and arXiv, want raw bytes). Every JSON-based probe reported `TOOL_FIRED_BUT_UNAVAILABLE` until `_fetch(..., json_body=True)` added the `json.loads` step. `test_probe_card_writes_evidence_and_a_named_zero_free_receipt` and `test_named_zero_when_every_instrument_returns_nothing` both caught this before the live run, which is the fixture-plus-pipeline test earning its keep.
5. **A verdict-token regex bug, also caught before the live run**: `**ALREADY_CLOSED.**` (a trailing period before the closing bold marker, as written in `post-earnings-announcement-drift.md` and `markowitz`'s split verdicts) did not match `\*\*([A-Z_]+)\*\*`, so `card_verdicts()` silently returned `[]` for that card instead of `["ALREADY_CLOSED"]`. The net `card_qualifies()` answer was accidentally still correct (no qualifying token either way), but the diagnostic `card_verdicts` list -- which the refusal message quotes verbatim -- was wrong. Fixed to `\*\*([A-Z_]+)\.?\*\*`; `test_a_card_with_only_already_closed_does_not_qualify` pins it.

## Live run: `lou-polk-skouras-2019-overnight-intraday`, real network, 2026-10-07

Run id `20261007T051710Z-0ec4f6`. Receipt: `backend/data/optimus/research_instruments/probe_20261007T051710Z-0ec4f6.json`. Evidence: `docs/research_intake/evidence/lou-polk-skouras-2019-overnight-intraday_20261007T051710Z-0ec4f6.json`.

**Coverage / novelty / latency per instrument** (3 needs-evidence questions, 10 queries issued, day cap 12):

| instrument | queries | rows | verified (DOI) | novel vs. card's own citation | avg latency (s) | named zeros |
|---|---|---|---|---|---|---|
| OpenAlex | 3 | 10 | 6 | 10 | 1.719 | `TOOL_FIRED_BUT_UNAVAILABLE` x1 (one live HTTP 500 from OpenAlex mid-run -- reported, not retried, not fatal) |
| CrossRef | 3 | 15 | 15 | 14 | 1.614 | none |
| Semantic Scholar | 2 | 0 | 0 | 0 | N/A | `KEY_REQUIRED_OR_RATE_LIMITED` x2 (no key declared, by design) |
| arXiv | 0 | 0 | 0 | 0 | N/A | `NOT_ATTEMPTED` (not in the topic class's instrument order -- classical asset-pricing, not quant/ML preprint) |
| NBER RSS | 2 | 36 | 0 | 36 | 2.539 | none (NBER working papers carry no DOI, so 0 of 36 are "verified" by this module's definition even though they are real, named papers) |

Overall: `zero_kind: YIELDING`, `status: OK`. Question 1 (post-2019 citing literature) stopped at `min_verified_and_full_coverage` after OpenAlex + CrossRef alone -- the card's own seed citation (the primary paper itself) was found by both, plus 9 verified novel DOIs. Questions 2 and 3 escalated to the extended tier (`extended_tier_cap_reached`) since their coverage of the card's seed set stayed at 0.0 (expected: those questions ask about FOLLOW-ON work, which by definition isn't the card's own seed citation).

**Two real findings, read from the evidence file, not assumed:**

1. **On-mechanism novelty, genuinely new to this card**: CrossRef's "The Tug of War" (2017, `10.5040/9781682660485`) and OpenAlex's "The nexus of overnight trend and asset prices in China" (2024, `10.1016/j.jedc.2024.104997`) and a CrossRef hit on "Overnight-daytime return reversals and future return: evidence from the Thai stock market" (2025 thesis, `10.58837/chula.the.2025.665`) are plausible, on-topic extensions the card did not previously name. These are candidates for a human/Sonnet to read and possibly promote into the card -- this lane does not promote them itself.
2. **A precision caveat, same shape as the research-instruments note's own CrossRef caveat ("unconstrained free text")**: a meaningful share of OpenAlex's "novel" rows are keyword-overlap false positives on the long, natural-language `## Needs evidence` question text -- e.g. "Abnormal Finding in an Overnight Sleep Study" (a 2000 chest-medicine case report matching on "overnight") and a legal drama titled "The Tug of War" (`10.1200/acon.17.00208`, an oncology-society bulletin). **The `novel` flag means "not already in the card's citation list," not "on-mechanism."** A human/Sonnet promoting a citation must still read it; this is stated in `docs/research_intake/README.md`'s own rule ("a human/Sonnet promotes a citation into the card by hand") and is now also a measured fact about this specific instrument combination, not just a stated policy.

## Test run

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_research_instruments.py backend/tests/test_query_planner.py backend/tests/test_signal_reachability.py backend/tests/test_guard_missing_input_contract.py -q
```

**216 passed** (21 new + 195 pre-existing across the other three files, none of which needed changes beyond the one `CASES` entry).

## What refused, and why that is correct

- Semantic Scholar and arXiv refused every call this session (`InstrumentKeyRequired` / `KEY_REQUIRED_OR_RATE_LIMITED`) because no key is declared and arXiv's opt-in flag is off -- matching the 2026-10-07 research-instruments note's own measurement (both 429'd keyless) and the project's declared-provider pattern (`QUERY_PLANNER_SEARCH_PROVIDER`-style: a `None` config value refuses loudly rather than silently doing nothing).
- `post-earnings-announcement-drift`'s card would refuse the lane outright (`NOT_A_QUALIFYING_VERDICT`) if probed, since its only verdict token is `ALREADY_CLOSED`; its `## Needs evidence` entry is kept for a future RESURRECTION, not for this lane to act on unattended.
- No paid instrument (Perplexity, Consensus beyond its free quota, Brave, Bigdata.com, any patent API) was implemented or called -- each remains an owner decision per the research-instruments note, never an automatic escalation.
