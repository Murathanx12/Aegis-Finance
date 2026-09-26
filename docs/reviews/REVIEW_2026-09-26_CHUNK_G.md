# REVIEW — chunk G (model routing), commit `cbe19f70` — 2026-09-26

Reviewer: Opus, read-only. Nothing in code, config or `~/.openclaw` was touched.
Inputs: the session order (rule 7), the brief §G, Murat's original 13:30 words,
`model_routing.py`, `telegram_agent.py`, `llm_analyzer.call_named`,
`llama_server.ensure` and its watchdog, `OPENCLAW_2026-09-26_LOCAL_SERVICE.md`,
`test_model_routing.py`, and the receipts cited at the end. Every number here
was read or measured today. No paid provider was called.

## RESULTS SCOREBOARD (for this chunk)

| line | value |
|---|---|
| terminal wealth moved | **NONE**: no order path, no new selector, no ranked output |
| gradeable outputs produced | **0**. `backend/data/optimus/model_routing/` does not exist, and `predictions.jsonl` holds **0** `compare:*` rows |
| `/research` outputs saved as a card or row | **0, by design**. `research()` parses the quest and throws it away (no `build_card`, no forecast row) |
| cost per provider measured | **not measured** (n = 0). Local is permanently `UNPRICED` because `"local"` is not in `LLM_PRICE_PER_MTOK` |
| RAM | a real win, but **conditional**: nothing starts llama-server at boot once the lab has been restarted (see item 3) |
| LLM spend | $0.00 |

**RESULT IMPROVEMENT: NONE.** The chunk cleans things up: RAM/VRAM, a provenance
footer on every reply, and no silent fallback between providers. It also installs
a surface for measuring. It does not yet produce a measurement. The two commands
meant to turn "use all of the files we have" into money (`/research`,
`/compare`) are built in a way that stops them doing it.

## VERDICT

Gradeability: **the plumbing exists, but it has produced no readings.**
Terminal wealth: **no.** The merge can stay (nothing unsafe, nothing changes a
book). The five items below decide whether the phone tap is ever worth making.

---

## FIVE "YOU ARE WRONG" ITEMS

### 1. `/research` withholds the files Murat told it to use, then throws the result away

**What the builder did.** `research()` calls `TC.engine_side(t, asof=...)` with
**no inputs**, "so a phone command must not load the 1.3M-row bars panel".
Every `engine_*` key is therefore `None`, and
`engine_unavailable = [bars, fundamentals, revisions, news, catalysts, predictions]`.
`quest_prompt` then prints *"WHAT THE ENGINE ALREADY KNOWS (do not re-derive;
fill the gaps)"* followed by a JSON object full of nulls. The quest's docstring
quotes Murat's "use all of the files we have", and the call site does the
opposite. It also passes no `prior_card` and no `open_promises`.

When the quest returns, the twelve answers, the X reads, the dated claims and
the promises are parsed and **discarded**. The phone gets
`bull/bear/falsifier[:400]` and a verdict word, which is exactly "just writing
comments". It also breaks session rule 6 ("every OpenClaw result = structured
evidence + timestamp + forecast + future grade").

**Why the trade is wrong, measured today:**

| step | cost |
|---|---|
| filtered read of one ticker + SPY from `prices_2025_26/bars.parquet` | **0.06 s** (860 rows) |
| filtered read of one ticker from `analyst/target_revisions.parquet` | **0.02 s** (983 rows) |
| the OpenClaw quest it wraps (84 thesis cards on disk) | **median 212.6 s, max 459.7 s** |
| DeepSeek synthesis on those cards | median **$0.00067** |

Keeping the command "light" saves 0.08 s against a 213 s quest. `build_packet`,
in the same file, already does the filtered parquet read. The builder's reason
is wrong by three orders of magnitude.

**Alternative.**
1. Load the inputs with `thesis_cards.load_inputs(asof, [T])`, filtered to T.
2. Set `prior_card` to the latest card for T and `open_promises` from the promise ledger.
3. Run the quest, then `build_card`.
4. Append the card and its forecast row through the same path `scripts/thesis_cards.py` writes.
5. Reply with the 600-character money view below.

Synthesis runs on DeepSeek (see item 5 and the deletion).

**The 600 characters worth money.** This is a template. The numbers are
illustrative, but every field already exists on disk:

```
NVDA  2026-09-26  [card c1a2.. frozen, graded 10-03]
HELD: pc_book, llm_b3 · entry +4.1% vs SPY +0.8%
RANK 37/2,861 · decile OOS net +0.9%/21d (realised, not a model)
REVISIONS 90d: 11 raises / 2 cuts, last 09-24 MS PT 210->235
NEXT DATE: earnings 11-19 (primary, IR) · 1σ/day 2.3% -> -2σ stop $171
CHANGED since 09-19 card: +2 primary claims (dated), 0 X-only
FORECAST p(|move|>1σ, h=5)=0.41 (investigator, magnitude-calibrated)
FALSIFIER: DC capex guide cut at MSFT 10-28
ACTION CLASS: HOLD-REVIEW (never an order)
```

It carries holdings, the rank decile's realised return, revision momentum, the
next dated catalyst, a stop quoted in sigma, what changed, a frozen forecast id
and a falsifier. Nine lines, no adjectives. That is what a phone should get for
a four-minute wait.

**Observation that settles it:** over the next 20 `/research` taps, count the
cards written and the engine inputs present.
- Builder's version: 0 cards, 0 of 6 inputs present.
- Alternative: 20 cards, at least 4 of 6 inputs present, and 20 forecast rows that grade.

### 2. `/compare` measures the wrong thing, on the wrong packet, at a sample size that never produces a result

**What the builder did.** One packet goes to three providers with the question
*"P(5-day return > SPY's)"*. Each answer is frozen as a `beats_benchmark` row at
h=5 with the raw probability, and Brier is scored by provider.

**Three separate defects.**

a. **This system's skill is not in direction.** From the 26 Sep audit
adjudication, row 2: the investigator's skill is in **magnitude (+5.6% at h=1)**.
On direction (`return_sign` at h=5) the same arms score **−8.7% held out**. A
direction question asked of three models only measures which is least bad at a
task none has shown skill at. The winner of a noise contest is picked by noise.

b. **The packet contains only prices.** `build_packet` sends six numbers per
name: `ret_5d`, `ret_21d`, `ret_63d`, `vol_21d_daily`, last close, for the stock
and for SPY. §59 already closed "price/volume cannot rank at 21d". Three models
turning six numbers into a probability does not test *where DeepSeek is worth
paying for*. DeepSeek's value in this programme is **reading text into typed,
dated fields** (typed events, cards, the investigator process), and none of that
is in the packet.

The packet is also stale. It is dated `asof=today`, but the bars panel's last
bar is **2026-09-21**, five sessions earlier. The model only learns this from a
`last_bar` field.

c. **Power.** For a binary beats-SPY question at h=5, every provider's Brier is
about 0.25. A difference worth paying for is about 0.002–0.005. With a paired
per-row SD of about 0.05, that needs roughly 400 **independent** pairs. Rows from
the same week share SPY's move, so the independent unit is the week. One phone
tap adds 3 rows for one ticker in one week. At Murat's tap rate this takes years
to read out.

Two smaller problems:
- There is no dedupe. Tapping `/compare NVDA` twice freezes six rows on the same `packet_hash`, which double-weights that ticker.
- `graded_by_provider` is recomputed **only when another `/compare` is written**. Nothing else refreshes it.

**Alternative.** Split the question in two (the next section has the exact
design):
- (i) **Extraction accuracy**, graded against mechanical truth. It reads out the same day.
- (ii) A forward **magnitude** arm (`abs_move_exceeds` at h=1 and h=5) on the daily forecast names, run as a batch rather than tapped.

**Observation that settles it:** run (i) once. If field-level accuracy differs
by at least 5 pp between providers with non-overlapping bootstrap CIs, the
routing question is answered in an afternoon for about $0.10. In that time the
direction `/compare` would not have produced a single graded row.

### 3. The idle watchdog lives in the wrong process, and the lab that is still running bypasses it today

**What the builder did.** `ensure()` starts the server with `bind=True`, which
uses a Windows job object so the server dies with the process that started it.
It also arms a daemon-thread watchdog in that process. `idle_check` stops the
server only when `owning_instance().is_me`.

**What happens in each case:**

| scenario | result |
|---|---|
| The Telegram bot starts the server, then the bot restarts or crashes | The job object kills the server. That is good (no orphan), **but any lab or factory generation running on it dies mid-batch**, and the next caller pays a cold start of up to 240 s |
| **The running lab starts the server.** It is PID 95400, started 09-25, and `lab_status.json` shows `lab_starts_model_server: True` right now | The lab uses `start(bind=False)` and **never stops** the server, by design. The ownership note says `owner_pid=95400`. `ensure()` touches the note, and every other process's `idle_check` returns "not the starting process". The server is **resident indefinitely**, so "not permanently resident" fails for as long as this old-config lab lives. It has already started the server once today (`model_server_starts_today: 1`) |
| The lab is restarted with the new config | `LAB_STARTS_MODEL_SERVER = MODEL_ROUTING_START_AT_BOOT = False`, so `ensure_model_server` refuses with `LAB_STARTS_MODEL_SERVER_DISABLED`. `l2_typing` (reader `local`, 50,076 rows on disk), `idle_gpu_queue` and the NN lab's model half go back to **PENDING_MODEL all day, the state the 2026-09-18 fix was written to end**. No lab loop calls `ensure()`: its only caller in the repo is `llm_analyzer.call_named`. The callers the commit comment names ("the factory's local pairing, the distillation") do not exist |
| `llama_server ensure` run from the CLI | `bind=False, watchdog=False`: an orphan with no reaper, by construction |
| A lab loop is between requests when the bot's watchdog fires | `busy()` is false between requests, so the server is stopped mid-batch. Lab loops never call `touch()` |
| OpenClaw's `localService` (idleStopMs 900000) races `ensure` for port 8080 | Whichever wins, the other sees "foreign" and never stops it. This is fine today only because OpenClaw never selects `aegis-local` (the doc says "configured, not exercised") |

**Alternative.** The ownership note already serves as the PID file. Make stopping
independent of which process started the server:
- **One reaper**: a Scheduled Task every 2 minutes running `python -m backend.services.llama_server reap`.
- It stops an **Aegis-started** server (never a foreign one) when `now − last_used_ts > 900 s` and `/slots` shows no request in flight.
- It stops **by the PID in the note**, checked against the listening socket's PID so a recycled PID is refused.
- Every client (Telegram, lab loops, factory) calls `ensure()` and `touch()`.
- Every start uses `bind=False`, so one client's restart cannot kill another client's work.
- The lab keeps `LAB_STARTS_MODEL_SERVER=True`, but starts through `ensure()`: start, run the batch, touch, and let the reaper stop it.

**Observation that settles it.**
- Restart the lab with the new config and read `lab_status.json` after 24 h. With the builder's design, `l2_typing` types 0 rows and shows PENDING_MODEL.
- Kill the bot while a lab batch is running. With the builder's design, the lab batch errors.
- With the reaper design, both runs finish cleanly.

### 4. Pricing NVIDIA at $0.00 is correct accounting, but the call is misconfigured, and a temperature-0 DeepSeek twin is not a second opinion

**What the repo says.** The web-search budget was used up this session, so these
facts were not re-checked online.
- **Pricing is right.** `nvidia/nemotron-3-super-120b-a12b` served this account on 2026-09-07 (1.8 s first reply, `BUILD_2026-09-07b_L_FREE_INFERENCE.md`). It sits in `LLM_PRICE_PER_MTOK` at zeros, so `LISTED $0.00` is correct.
- **Rate limits.** The free tier is reported at **about 40 requests/minute**, with credit caps reportedly removed (`research_notes/2026-09-13/research_cloud_llm_readers.md`, lines 64–67). This account got **HTTP 429 in 2 of 5 runs** (same BUILD doc, §9). That is fine for a phone and **unfit for a batch adjudicator** without a rate limiter. `call_named` has none for NVIDIA; DeepSeek has `_acquire_call_budget`, NVIDIA has nothing.
- **It is a reasoning model** (Nemotron 3 family, with thinking that can be switched off). The same BUILD doc measured what goes wrong: *"a small budget on a reasoning model reads as a dead model"*. `gpt-oss-20b` at 400 tokens returned empty content on 4 of 6 documents.
- **The resulting defect.** Chunk G sends `max_tokens=700`. When `content` is empty it **falls back to `reasoning_content`**, and a test pins that behaviour (`test_a_reasoning_models_answer_in_reasoning_content_is_not_lost`). `parse_probability` takes the **last** `P_BEATS_SPY_5D:` match in whatever text it gets. A truncated chain of thought ("if momentum holds, P_BEATS_SPY_5D: 0.6 ... but") can therefore be frozen as a forecast row. A thought is not an answer.
- **Finance fit is unmeasured.** The catalogue's one finance model (`palmyra-fin-70b`) returns 404 for this account. `kimi-k3`, `gemma-4-31b` and `nemotron-3-ultra-550b` also serve for free. The adjudicator was picked, not measured.

**On a second DeepSeek sample at temperature 0.** It is cheaper (about
$0.0004/call) but **close to worthless as a second opinion**. At T=0, the same
model on the same packet returns nearly the same tokens. At any temperature, a
second sample makes the *same model's* errors. An adjudicator is worth its
**error decorrelation × its accuracy**. A different model family (NVIDIA) is the
right *kind* of second opinion; whether it is a *good* one is what the first
experiment below measures. For a cheap DeepSeek-only second view, use a
**different prompt role** (the falsifier/devil's-advocate prompt at T=0.7), not a
resample.

**Fix before any measurement:**
- For NVIDIA, send thinking off (as the model's chat template allows) or set `max_tokens ≥ 2000`.
- Parse **only `content`**. When content is empty, record `status=REASONING_ONLY` and write no row.
- Add a 30 RPM token bucket for NVIDIA.

**Observation that settles it:** in the extraction run below, measure NVIDIA's
disagreement rate with DeepSeek and how often NVIDIA is right *on those
disagreements*. If it is right on fewer than 50% of them, it is a coin flip, not
an adjudicator.

### 5. At these prices, cost per provider barely matters. What binds is RAM, latency and accuracy

At the price table's DeepSeek flash rates (input $0.169/Mtok, output
$1.285/Mtok):
- A `/compare` call (about 500 tokens in, 200 out) costs about **$0.00034**.
- A card synthesis costs about **$0.00067** (measured median).
- 10,000 compare calls cost about **$3.4**.

The local route, by contrast, loads a 4.7 GB Qwen2.5-7B Q4 model (up to 240 s,
`ENSURE_WAIT_S`) on a machine that had about 5 GB free today. It also puts the
**weakest model on the judgment step** of `/research`. Using the local model to
save $0.00067 per research call loses on every axis except privacy.

Two accounting issues:
- `cost_status` comes from the **requested** model string. DeepSeek has answered with `usage.model=deepseek-flash` since 09-14. The price is the same today, so no harm yet, but the receipt should record `usage.model`, not the request.
- Local is permanently `UNPRICED`, which stamps every compare total "LOWER BOUND" forever. Give `local` a zero-price row (electricity is not in any other line either) and add `gpu_seconds`.

**Alternative:** route by *what is scarce*.
- DeepSeek for anything that needs judgment or reading; it is effectively free.
- Local only for **bulk offline typing**, where the 40 RPM limit or cloud latency binds and privacy matters.
- NVIDIA as the measured second model family.

Decide this with the experiment below, not by assertion.

**Observation:** after the experiment, build a per-provider table of accuracy
per dollar and per second. If DeepSeek's accuracy is at least 5 pp above
local's, local leaves every interactive route.

---

## THE EXPERIMENT MURAT ASKED FOR (question 5): "cost and incremental accuracy for every provider"

### E-G1: extraction accuracy (reads out the same day)

**Packets: N = 240** dated news items already in the corpus that report an
analyst action (upgrade, downgrade, price-target change). Each is matched
mechanically to a row in `analyst/target_revisions.parquet` (392k dated
revisions with firm, action, from→to, `event_date`, `pit_safe`). That row is the
gold label. The items are split into four strata of 60:
- US mega/large caps
- mid/small caps
- non-US listings (`.T`, `.KS`, `.HK`), Asia first
- items with **no** matching revision (to test for invented facts)

**Four arms, same packet hash per item:**
- local Qwen2.5-7B
- DeepSeek at T=0.3, as shipped
- NVIDIA Nemotron-3-Super, thinking off, content only
- DeepSeek with the devil's-advocate prompt (the cheap second view)

**Grades:**
- field-level exact match on {ticker, firm, action, old_pt, new_pt, date}
- **invented-fact rate** on the 60 no-match items (any asserted firm or price target counts as an error)
- refusal and parse-failure rate
- latency
- `cost_usd`, priced from `usage.model`
- **incremental accuracy**: the accuracy of "DeepSeek, with NVIDIA adjudicating where they disagree" minus DeepSeek alone, with a bootstrap CI over items

**Cost:**
- DeepSeek: 480 calls, about **$0.15**
- NVIDIA: 240 calls at 30 RPM, about 8 minutes, $0
- local: 240 calls at about 8 s each, about 32 minutes of GPU, $0

**It reads out the same afternoon.**

**Decision rule, declared now:**
- A provider enters an interactive route only if its field accuracy is within 3 pp of the best **and** its invented-fact rate is no more than 2 pp above the best.
- NVIDIA stays as adjudicator only if incremental accuracy exceeds +2 pp with a CI that excludes 0.

### E-G2: forward magnitude (reads out on day 15)

- **Names:** the daily forecast pass's 25 names per day, sent to all 3 providers.
- **Packet:** the full engine side plus the card, not six price numbers.
- **Observable:** `abs_move_exceeds` (1σ) at h=1 and h=5.
- **Schedule:** a nightly batch, not phone taps. 10 sessions give 750 rows per provider per horizon.
- **Grade:** paired Brier against the investigator's magnitude row and against the base rate, **blocked by date** (the session is the independent unit).
- **Reads out 2026-10-16**, when the h=5 rows from the 10th session resolve.
- **Cost:** about 25 × 10 × $0.0006 ≈ **$0.15** of DeepSeek.
- **Decision rule:** pay for a provider on this route only if its paired Brier improvement over the cheapest provider is at least 0.003, with a date-block bootstrap CI that excludes 0.

Give the `compare:*` rows their own `mechanism_id`, and keep them out of the §64
overall-skill grade until E-G2 reads out. A routing experiment should not move
the ledger's headline number.

---

## (6) SAFETY

- **No order path is added.** `route()` dispatches a fixed table, there is no shell verb, and the bot still answers only the owner chat. Good.
- **Error text goes to a third party.** `call_named` puts `str(e)[:300]` into `error`, and `/ask`, `/deep` and `/compare` send it to Telegram. `poll` also sends any handler exception's text. OpenAI-SDK 401 bodies usually mask keys down to the last 4 characters, but that is the provider's courtesy, not our control. Add one redaction pass (`sk-…`, `nvapi-…`, `Bearer …`, `APCA…`) over everything `send()` transmits.
- **The real exposure is `/research`, not the bot.** A phone tap launches an OpenClaw agent **whose browser is logged into Murat's X account**, and that agent reads arbitrary web and X content. "read, never post, like or follow" is only a sentence in a prompt, and a page with injected instructions can override it. Before `/research` runs unattended, confirm that OpenClaw's tool policy blocks post, like, follow and DM at the gateway rather than in the prompt. Otherwise, run quests in a browser profile that cannot write to X.
- **The bot blocks.** `poll()` runs handlers synchronously. `/research` (about 213 s of quest plus up to 240 s of model load) and `/compare` (three calls with a 180 s timeout each, plus the load) freeze the bot for minutes. **A `/sim stop` sent in that window waits behind them.** Run model routes in a worker thread and reply "queued" immediately.
- **`/nav` quietly changed meaning**, from broker truth to a receipt. `/broker` now has the old behaviour, while `/brief` still calls the broker. Either say so on the first line of `/help`, or keep `/nav` as the broker call.

---

## ONE THING TO DELETE

**Delete the local-model synthesis step in `/research`** (`_local` inside
`research()`). It saves **$0.00067** per call. In exchange it costs a 4.7 GB
load and up to 240 s, and it puts the weakest model on the one step that needs
judgment, right after a DeepSeek-browsed quest that already cost more.
Synthesize on DeepSeek, which is what `thesis_card.synthesize` already does by
default. `/ask` stays local, as Murat asked, and becomes the *only* interactive
local route.

---

## THREE IDEAS, WITH COST

1. **Make `/research` return a card, a forecast row and the 9-line money view** (item 1). About 1 builder hour: reuse `thesis_cards.load_inputs`, `engine_for`, `build_card` and the card writer, plus the promise ledger. It adds about 0.1 s at runtime. Every tap becomes a graded row, and its dated X reads and claims feed chunk B's source reliability.
2. **Run the E-G1 extraction bake-off** (above). About 2 builder hours, **$0.15** and 40 minutes of GPU. It answers "where is DeepSeek worth paying for" the same day, and shows whether NVIDIA has a measured reason to be in the loop at all.
3. **Build one reaper, use `bind=False` everywhere, and start the lab through `ensure()`** (item 3). About 1 builder hour plus one Scheduled Task. The lab's local typing of the 50k-row corpus comes back without the server becoming resident, and idle-stop no longer depends on which process happens to be alive.

---

## MY ROUTING TABLE

| command | route | why |
|---|---|---|
| `/nav` | broker truth (`pc_broker`); fall back to the receipt, labelled with its age | money comes from the broker, not a paraphrase of a file |
| `/books` `/forecasts` `/status` | receipts, no model; print each receipt's **age** and go red after 36 h | a date that cannot go red is decoration |
| `/ask <q>` | local, on demand; when the question names a ticker, **inject** that ticker's card and ranking | Murat asked for the local model to answer; the context makes it more than chat |
| `/research <T>` | OpenClaw quest (DeepSeek) **given the engine side** → card → forecast row → **DeepSeek** synthesis → 9-line money view | the only route that turns files plus web into a graded object |
| `/deep <q>` | DeepSeek, with ledger and card context for any ticker in the question; keep `--nvidia` | it costs about $0.0005; the context is where the value is |
| `/compare <T>` | **read-only**: show T's latest E-G2 rows across providers and the E-G1 table | the measurement runs as a batch; the phone only reads it |
| batch typing / extraction | local (through `ensure` and the reaper); NVIDIA as a throttled second family, called only on disagreements | this is where rate limits and privacy bind, not dollars |

---

*Receipts cited:*
- `backend/data/optimus/lab_status.json`: utc 2026-09-26T08:31Z, pid 95400, `lab_starts_model_server: True`, `model_server_starts_today: 1`, `l2_typing.rows_on_disk: 50076`.
- 84 cards under `backend/data/optimus/thesis_cards/`: quest median 212.6 s, synthesis median $0.00067; verdicts neutral 57, supports 21, against 6.
- The filtered-read timings, run during this review: 0.06 s for bars, 0.02 s for revisions.
- `predictions.jsonl`: 30 MB, 0 `compare:*` rows.
- `docs/reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md`, row 2.
- `docs/BUILD_2026-09-07b_L_FREE_INFERENCE.md`, §1 and §9.
- `docs/research_notes/2026-09-13/research_cloud_llm_readers.md`, lines 64–67.
