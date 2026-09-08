# BUILD 2026-09-07b — LANE L: FREE INFERENCE · SCRAPE-AND-STORE · LOCAL REVIEW

**Mandate (Murat, verbatim):** *"I have 9 dollars on deepseek left so I wish to do
a webscrape pull and store all the data and run a local model (free or nvidia
free models) to review them."*

**RESULT: DeepSeek spend this lane = $0.00.** Two free inference backends are
live and tested, a resumable raw store is proven by killing it and restarting
it, and a 7B model on the laptop's own GPU scores **6/6 on the known-answer
battery including both planted nulls** — better than the free NVIDIA endpoint on
the same six documents, at 18× the throughput.

Roadmap rows advanced: **E4** (GDELT, the whole-market Asia-first layer), **E1**
(the resumable-puller pattern the news backfill lacked), and the free-inference
substrate **R** and **U** need before they can run at all.

---

## SCOREBOARD

| | |
|---|---|
| Best free backend for extraction | **`local_gguf` (Qwen2.5-7B-Instruct-Q4_K_M on the RTX 5060)** — 6/6, 1,437 docs/hr |
| Second free backend | `nvidia_nim` (`openai/gpt-oss-20b`) — best observed 5/6, rate-limited under load |
| DeepSeek spend | **$0.00**. Balance untouched. |
| DeepSeek counterfactual for the batches run | $0.0010 + $0.0032 + $0.0055 + $0.0050 + $0.0004 = **$0.0151** |
| Documents stored | 55 GDELT files, 49,015,304 bytes, 100% HTTP 200 |
| Resume proof | killed at 15 docs → restarted → skipped 2, added 40, finished at cursor `20260907080000` |
| New tests | **56** (all offline, network-blocked) |
| RESULT IMPROVEMENT | **NONE on any book.** This lane moves no P&L. It removes a cost floor and unblocks R/U. Say so plainly. |

---

## 1. WHAT THE NVIDIA KEY ACTUALLY REACHES

Asked the endpoint; assumed nothing. Receipt:
`backend/data/optimus/free_inference_2026-09-07/L1_nim_probe.json`.

`GET https://integrate.api.nvidia.com/v1/models` → **HTTP 200 in 578 ms, 81 models listed.**

**The catalogue is not the grant.** Of the 81 listed, a chat completion was
attempted against 47. **Twelve served this account:**

| model | first-reply latency | note |
|---|---|---|
| `nvidia/ising-calibration-1.5-31b` | 0.6 s | |
| `minimaxai/minimax-m3` | 0.7 s | rate-limits fast (see below) |
| `nvidia/nemotron-3.5-content-safety` | 0.8 s | classifier, not a chat model |
| `meta/muse-glimmer-30b` | 0.9 s | |
| `poolside/laguna-xs-2.1` | 0.9 s | HTTP 503 on attempt 1, 200 on attempt 2 |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 1.0 s | |
| `nvidia/nemotron-3-super-120b-a12b` | 1.8 s | |
| **`openai/gpt-oss-20b`** | **2.6 s** | the declared default; REASONING model |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 3.8 s | |
| `moonshotai/kimi-k3` | 33.8 s | cold start |
| `nvidia/nemotron-3-ultra-550b-a55b` | 41.7 s | cold start; timed out at 60 s, answered at 200 s |
| `google/gemma-4-31b-it` | 51.7 s | cold start |

**Thirty-two returned HTTP 404 `"Not found for account"`** — visible in the
catalogue, not provisioned. Among them: every Llama, every Mistral, every Gemma
below 4, `writer/palmyra-fin-70b-32k`, `nvidia/llama-3.1-nemotron-70b-instruct`,
`moonshotai/kimi-k2.6`, `nvidia/nemotron-4-340b-instruct`.

**Three are CANNOT DETERMINE**, not dead: `deepseek-ai/deepseek-v4-flash-0731`
and `deepseek-ai/deepseek-v4-pro-0813` read-timed-out at 60 s *and* at 200 s;
`mistralai/mistral-nemotron` returned HTTP 500 with an empty body after 98.7 s.
(A free DeepSeek via NIM would have been the best outcome available. It is not
reachable, and "we could not tell" is the honest verdict, not "it does not work".)

### This falsifies a note in the repo

`scripts/connection_check.py` (2026-09-05) records `moonshotai/kimi-k3`,
`minimaxai/minimax-m3` and `google/gemma-4-31b-it` as unreachable and concludes
an **ENTITLEMENT** failure — "the credential is LIVE and no completion is
provisioned." **All three answer on 2026-09-07.** Two of the three had simply
cold-started past that probe's 30 s timeout. The comment block at
`model_provider.PROVIDERS["nvidia"]` carries the same stale conclusion. Neither
is edited here (another lane owns `connection_check`); the correction is
recorded in the probe receipt and in `free_inference.BACKENDS`.

### Two operational facts that cost real time

1. **`openai/gpt-oss-20b` is a reasoning model.** It spends its token budget
   *thinking* before it writes `content`. At `max_tokens=400` four of six
   extraction documents came back with `content` empty → `REFUSED_UNPARSEABLE`.
   At 1,500 the same prompt scored 5/6. **A small budget on a reasoning model
   reads as a dead model.**
2. **The free tier rate-limits.** `minimaxai/minimax-m3` returned HTTP 429
   `"Too Many Requests"` on 4 of 6 sequential documents; a later `gpt-oss-20b`
   run hit 429 on 2 of 6. This is the reason `local_gguf` is the right default
   for a batch of any size, and NIM is the second opinion.

---

## 2. `local_gguf` — WORKING, AND IT IS THE FASTER PATH

**It works.** The toolchain was already on the box from 2026-08-27 and had never
been wired to anything.

| | |
|---|---|
| Model | **Qwen2.5-7B-Instruct** |
| Quantisation | **Q4_K_M** |
| File | `C:\Users\mrthn\llama\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf`, **4,683,074,240 bytes (4.36 GiB)** |
| Runtime | llama.cpp **b10645**, **CUDA 13.3** Windows x64 build, `llama-server.exe` |
| GPU | NVIDIA GeForce RTX 5060 Laptop, 8,151 MiB, driver 595.97 |
| Launch | `-ngl 99 -c 8192 --host 127.0.0.1 --port 8080 --no-webui` (all layers on GPU) |
| **VRAM footprint** | **5,642 MiB of 8,151 MiB** (69%), leaving ~2.3 GiB headroom |
| Cold start to first serve | **~10 s** |
| **Throughput** | **43.5 output tok/s** single-shot; **31.3 tok/s** across the 6-document batch; the pre-existing `server.log` records 57 tok/s on shorter generations |
| Cost per token | **$0.00** |

Start it with `C:\Users\mrthn\llama\llama-start.cmd`; stop it before gaming
(`llama-stop.cmd`) — it holds ~5.5 GB. The capability table's `probed_on` for
this backend means *"a human saw it answer that day"*, **not** *"it is up now"*;
only `model_provider.status(probe=True)` can say the second thing.

**Use the CUDA 13.x build.** The CUDA 12.4 build does not see this GPU
(Blackwell, sm_120) and falls back to CPU *silently* — fast enough to look like
it worked.

Time-box: not needed. The 45-minute budget was spent connecting an existing
server rather than building one.

---

## 3. THE PROVIDER LAYER (Part 1 — the one that had to land)

`backend/services/free_inference.py` — the policy layer.
`backend/services/model_provider.py` — the transport, extended.

Three named backends, each a **row of data**, not a client:

| backend | transport | cost class | default model | key |
|---|---|---|---|---|
| **`nvidia_nim`** | `nvidia` | **free** | `openai/gpt-oss-20b` | `NVIDIA_API_KEY` |
| **`local_gguf`** | `local` | **free** | `local` | none (keyless) |
| `deepseek` | `deepseek` | **paid** | `deepseek-chat` | `DEEPSEEK_API_KEY` |

`DEFAULT_BACKEND = "nvidia_nim"`. **DeepSeek is never the default and a caller
must name it**, pinned by `test_the_default_backend_is_free_and_is_never_the_paid_one`.
`scripts/local_review_run.py --backend deepseek` additionally refuses unless
`AEGIS_ALLOW_PAID_REVIEW=1`.

### One price table

Twelve NVIDIA models + `local` are now rows of **zeros** in
`config.LLM_PRICE_PER_MTOK`. Not a second "free models" list — `free_inference.
is_free_model()` **derives** freeness from the zeros, so the two facts cannot
disagree (roadmap X7's complaint). Consequences, each pinned by a test:

- a free call is priced at **0.0, not `None`** (`None` means *unpriced* and
  makes every total a lower bound);
- it still emits a **token count** and goes through `llm_telemetry.record_call`;
- `usage()` emits **a line per declared backend including ones with no calls** —
  `"$0.00"`. An absent line and a zero line read identically in a summary and
  mean opposite things;
- an **undeclared model is refused before the wire**, naming both tables to add
  it to.

### The language contract — and a hole it had

The pin was **imported, not restated**. `model_provider` carried its own
`_LANGUAGE_PIN = " Respond in English."` — one word different from
`llm_language.LANGUAGE_PIN`, and a second definition of the one contract that
exists *because* the same text was once written twice. It now imports it, and
`complete()` applies the **response half** (`>10%` non-Latin → refused, counted
per backend) that it did not have at all.

**Why nobody had caught it:** `test_llm_language_contract.py` walks the AST for
`chat.completions.create` — the OpenAI **SDK** call. `model_provider` speaks raw
`urllib`, so it was in no enumeration. `test_free_inference.py` adds the
**raw-HTTP arm** of that enumeration, and it immediately found a second,
live, paid call site:

> **`backend/services/llm_research.py` posted to DeepSeek with NO system message
> at all** — precisely the condition under which `deepseek-chat` code-switches to
> Chinese — and passed the reply straight through, unguarded, for its whole life.

Both are fixed. A refused reply is **discarded, not repaired and not retried**,
and the tokens it burned are **still recorded** (`LanguageRefused` carries the
`Reply`), because a refusal rate needs a denominator.

### A live network leak in the fast suite, fixed

`llm_research.available()` called `load_dotenv()` **unconditionally**, defeating
`AEGIS_IGNORE_DOTENV`. Under the fast suite it therefore reloaded `.env`, found
a real key, reported the provider available — and `ask()` opened a socket in a
**non-slow** test. It now honours the env var. (`.env` was never moved.)

The six `test_arena_brain.py` failures had the same root: those tests stub
`llm_research` with `monkeypatch.setitem(sys.modules, ...)` only, and
`beliefs.py` does `from backend.services import llm_research`, which CPython
resolves via `getattr(backend.services, "llm_research")` once the attribute
exists. Pytest **imports every test module at collection**, so the newly added
`test_one_price_table.py` set that attribute and silently bypassed the stub in
six tests. All three stub sites now set the **package attribute as well**. Not
marked slow; fixed.

---

## 4. THE SCRAPE STORE (Part 2) — SCHEMA, CURSOR, AND THE RESUME PROOF

`backend/services/scrape_store.py` + `scripts/gdelt_pull.py`.

### Schema

`backend/data/scrape/<source>/`

| file | contents |
|---|---|
| `bodies/<aa>/<bb>/<doc_id>.gz` | the **RAW** body, gzipped, exactly as it came off the wire; sharded 2 levels (65,536 leaves) so a million docs never crowd one NTFS directory |
| `index.jsonl` | one `DocRecord` per line |
| `cursor.json` | **named** cursors |
| `pull.log` | append-only, one line per event |
| `pull.pid` | pid + argv + previous run's pid |
| `coverage.json` | the receipt, rewritten **every N documents** |

`DocRecord`: `doc_id` (sha256 of `source|url`, 24 hex) · `source` · `url` ·
`fetched_at` (UTC ISO) · `http_status` · `sha256` of the body · `n_bytes` ·
`path` · `cursor` · `meta`.

Write order is **body → index → cursor**, always. The reverse gives an index row
pointing at a file that does not exist, and a resume that trusts its index then
reports coverage it does not have.

**Non-200s are stored**, body and all. A store that keeps only successes cannot
tell *"we looked and it was not there"* from *"we never looked"* — the WRDS pull's
exact failure.

### Cursor format, and a bug I wrote and then fixed

```json
{"schema_version": 1, "source": "gdelt_v2", "cursors": {
   "tail":                                 {"cursor": "20260907104500", ...},
   "window:20260907040000-20260907080000": {"cursor": "20260907080000", ...}}}
```

Cursors are **named per traversal**. The first version had one cursor per source:
a rolling "last hour" run left it at 09:45, then a backfill of 04:00–08:00
fast-forwarded *itself* to 10:00, **fetched zero stamps and reported success.**
A cursor that skips work while reporting success is the exact failure this store
exists to prevent, wearing a resume's clothes. Pinned by
`test_cursors_are_NAMED_so_a_backfill_cannot_ride_a_tail_cursor`.

### Resume proof (GDELT, 2026-09-07)

Robots: `data.gdeltproject.org/robots.txt` → **HTTP 404**. No file means nothing
is disallowed — *a different fact from "we did not check"*, and the log records
which of the two happened. User-Agent is descriptive and contactable; requests
are spaced by `--sleep` (default 1.0 s).

```
run 1   python -m scripts.gdelt_pull --start 20260907040000 --end 20260907080000 \
                --streams export,mentions,gkg --sleep 0.2 --receipt-every 3
        pull.pid  ->  {"pid": 6288, ...}          <- PID WRITTEN DOWN
        taskkill /PID 6288 /F                      <- KILLED BY PID, never by image name
        at kill: 15 documents on disk
                 cursor window:...  = 20260907043000   (the last COMPLETE stamp)
                 coverage.json      = 13 docs, note "in flight"   <- receipt existed MID-RUN
                 pull.pid           = STILL PRESENT               <- the crash evidence

run 2   ...the identical command...
        BEGIN  pid=116720  already_stored=15
        NOTE   previous run left pid=6288 -- if that process is gone this is a RESUME after a crash
        RESUME window:20260907040000-20260907080000 cursor=20260907043000 -> starting at 20260907044500
        PLAN   14 stamps x 3 streams [20260907044500 .. 20260907080000]
        END    docs=55 bytes=49015304   new=40 skipped=2 failed=0
```

It resumed **at the cursor, not from zero**: 14 stamps planned instead of 17,
and the 2 documents from the half-finished stamp were skipped by hash rather
than re-fetched. Final: **55 documents, 49,015,304 bytes, 100% HTTP 200.**

An independent check comes free: `lastupdate.txt` publishes GDELT's own MD5 per
file, so a truncated download is caught **at store time** and flagged
(`md5_mismatch`) rather than by a parser three weeks later.

**Not touched:** Alpaca and Finnhub news. Another lane owns E1/E2.

### Which paths are DATA and which are RECEIPTS

| path | kind | size | in git? |
|---|---|---|---|
| `backend/data/scrape/*/bodies/**` | **DATA** — raw article text, re-fetchable, grows without bound (GDELT's `gkg` alone is ~4.5 MB per 15-min stamp ≈ **430 MB/day**) | **47 MB** | **gitignored** |
| `backend/data/scrape/*/pull.pid` | machine-local | bytes | **gitignored** — a committed pid reads as a live process on somebody else's box |
| `backend/data/scrape/*/{index.jsonl,cursor.json,pull.log,coverage.json}` | **PROVENANCE** — what a resume reads, and the evidence a pull got where it says it got | **37 KB** | **tracked** |
| `backend/data/optimus/free_inference_2026-09-07/*.json` | **RECEIPTS** — the evidence behind every number in this doc | 10 KB | **tracked** |

The bodies live on disk, which is what Murat asked for; they do not belong in a
public repo. The provenance does: ignoring it too would leave the next session
unable to tell an *unfetched* window from an *unrecorded* one — which is exactly
what the 83.6% pull could not tell anyone.

---

## 5. THE REVIEW PASS (Part 3) — KNOWN ANSWER, AND THE NULLS

`backend/services/local_review.py` + `scripts/local_review_run.py`.

One `ReviewRow` per document, **always**. Closed vocabulary (12 event types
including an explicit `NO_EVENT` escape), six typed refusal statuses, and
`confidence` recorded as *the model's* number, explicitly not a probability
until something plots it against outcomes.

> **NO LLM OUTPUT REACHES A SIZE, A STOP OR AN ORDER. It reaches a row.**
> Enforced as a test that fails if any `ReviewRow` field name contains
> `weight/size/qty/notional/stop/target_price/order/allocation`.

### Known-answer battery: 4 planted events + **2 planted nulls**

The nulls (a weather forecast, a recipe) are the point. Every model scores well
on documents that contain an answer; the failure that matters is inventing one.

| backend / model | max_tokens | correct | **nulls refused** | verdict |
|---|---|---|---|---|
| **`local_gguf` / Qwen2.5-7B-Q4_K_M** | 400 | **6 / 6** | **2 / 2** | **PASS** |
| `nvidia_nim` / `openai/gpt-oss-20b` | 400 | 2 / 6 | 2 / 2 | PARTIAL — 4 × `REFUSED_UNPARSEABLE` (reasoning ate the budget) |
| `nvidia_nim` / `openai/gpt-oss-20b` | 1500 | 5 / 6 | 2 / 2 | PARTIAL — best NIM result observed |
| `nvidia_nim` / `openai/gpt-oss-20b` | 1500 (rerun) | 2 / 6 | 2 / 2 | **CANNOT DETERMINE** — 2 × HTTP 429; never reached the model |
| `nvidia_nim` / `minimaxai/minimax-m3` | 500 | 2 / 6 | 0 / 2 | **CANNOT DETERMINE** — 4 × HTTP 429 |

**No backend ever answered a planted null.** Zero inventions across five runs.

Local, per document: `plant_earnings → EARNINGS / Zhongtai Semiconductor / 0.9`,
`plant_merger → MERGER_ACQUISITION / Marubishi Heavy Industries / 0.9`,
`plant_guidance_cut → GUIDANCE / Nordlicht Automotive AG / 0.9`,
`plant_management → MANAGEMENT_CHANGE / Hanul Chemical / 0.8`, both nulls →
`REFUSED_NO_EVENT`.

**A grading bug I wrote and fixed:** the first verdict function reported the four
HTTP 429s as *"a planted NULL was answered, which is invention"* — an accusation
of the model for something the network did. A verdict that cannot tell *"it got
it wrong"* from *"it never answered"* is the same error as a coverage receipt
that keeps only successes. `REFUSED_PROVIDER` now yields **CANNOT DETERMINE**.

---

## 6. THROUGHPUT AND COST — WITH THE DEEPSEEK COUNTERFACTUAL

Six documents per batch, counterfactual priced from `config.LLM_PRICE_PER_MTOK`
(`deepseek-chat`: $0.169413/Mtok in, $1.284835/Mtok out) on the **same token
counts**.

| run | tok in | tok out | wall clock | s/doc | **docs/hr** | out tok/s | **actual $** | **DeepSeek would have cost** |
|---|---|---|---|---|---|---|---|---|
| **`local_gguf` (warm)** | 2,159 | 470 | **15.0 s** | 2.51 | **1,436.9** | 31.3 | **$0.00** | $0.0010 |
| `local_gguf` (cold start) | 2,159 | 470 | 43.0 s | 7.16 | 502.7 | 10.9 | $0.00 | $0.0010 |
| `nvidia_nim` gpt-oss @400 | 2,475 | 2,157 | 89.1 s | 14.85 | 242.4 | 24.2 | $0.00 | $0.0032 |
| `nvidia_nim` gpt-oss @1500 | 2,475 | 3,931 | 181.1 s | 30.18 | 119.3 | 21.7 | $0.00 | $0.0055 |
| `nvidia_nim` gpt-oss @1500 (rerun, 429s) | 1,643 | 3,686 | 277.3 s | 46.21 | 77.9 | 13.3 | $0.00 | $0.0050 |
| `nvidia_nim` minimax-m3 (429s) | 1,026 | 177 | 25.7 s | 4.29 | 839.8 | 6.9 | $0.00 | $0.0004 |

**Total DeepSeek spend avoided across this lane: $0.0151.** That number is small
because the batches are small; the point is the **rate**. At the warm local
figures, a 10,000-document pass costs **~7.0 hours of wall clock and $0.00**,
against **~$1.62** on `deepseek-chat` at these token counts. The R era replay's
own budget is 10,000 windows ≈ $6.40 with a $10 cap against a $9 balance — that
whole gate becomes optional if the arm can run locally.

**The real cost of the local path is wall clock, not dollars**, which is why the
receipt prints it beside the dollars and never instead of them.

---

## 7. PROPOSED `CLAUDE.md` REPLACEMENT PARAGRAPH — **NOT APPLIED**

The lead session should replace the heading and first paragraph of *"THE LLM
PROVIDER IS DEEPSEEK, AND IT IS THE ONLY ONE"* with the following. Everything
after it in that section (the `_get_provider` explanation, `_LANGUAGE_PIN`, the
dormant Claude branch) stands unchanged and is still correct.

> ## DEEPSEEK IS THE ONLY **PAID** PROVIDER — AND IT IS NO LONGER THE DEFAULT
>
> **There is no Anthropic key and no OpenAI key. Do not plan around one.**
> DeepSeek has been the live provider throughout and still is for anything that
> must be paid for. What changed on 2026-09-07 is that paying is now a
> **choice**: two FREE backends are wired, declared and tested, and a new caller
> that reaches for DeepSeek by default is a bug.
>
> `backend/services/free_inference.py` declares three backends —
> **`nvidia_nim`** (free; NVIDIA NIM, `NVIDIA_API_KEY`, 12 of 81 listed models
> actually served, default `openai/gpt-oss-20b`), **`local_gguf`** (free;
> llama.cpp on the RTX 5060 — Qwen2.5-7B-Instruct-Q4_K_M, 5.6 GB VRAM, ~43 out
> tok/s, start it with `C:\Users\mrthn\llama\llama-start.cmd`), and
> **`deepseek`** (PAID, DORMANT by default). `DEFAULT_BACKEND` is `nvidia_nim`
> and `test_free_inference.py` fails if it ever becomes the paid one.
>
> **The balance is ~$9 and Murat is preserving it for the era replay (roadmap R,
> cap $10).** Reserve DeepSeek for work that measurably needs it — causal
> reasoning arms, and anything a 7B cannot do — and name it explicitly at the
> call site. On the known-answer extraction battery the local 7B scored 6/6
> including both planted nulls, beating the free NVIDIA endpoint, at 18× the
> throughput. *A free model that is good enough is not a compromise; it is the
> removal of a budget gate.*
>
> **What follows and does NOT relax:** one price table
> (`config.LLM_PRICE_PER_MTOK`; a free model is a row of ZEROS in it, never a
> special case in code, so a free call still emits a token count and still
> reads $0.00 rather than being absent) · the language pin and the >10%
> non-Latin **refusal** are applied CENTRALLY in `llm_language` and reach every
> backend including the raw-`urllib` ones · an undeclared model is a refusal,
> not a call · **no LLM output reaches a size, a stop or an order — it reaches a
> row.**

---

## 8. TESTS

| file | tests | what it pins |
|---|---|---|
| `backend/tests/test_free_inference.py` | **20** | the capability declaration, one price table, free = zeros, default never paid, undeclared model refused before the wire, the non-Latin refusal counted **under the backend name**, and the **raw-HTTP arm** of the language contract |
| `backend/tests/test_scrape_store.py` | **16** | raw body byte-for-byte, provenance on every row, non-200 stored, idempotence, cursor survives the process, **named cursors**, corrupt cursor reads as none, torn index line skipped, pid left on crash / cleared on finish, receipt exists mid-run |
| `backend/tests/test_local_review.py` | **20** | typed rows, every refusal branch is a ROW, planted null → refusal, provider failure ≠ model failure, language refusal keeps its tokens, clamping, the $0.00-plus-counterfactual receipt, and the no-size/no-stop/no-order name check |
| **new total** | **56** | all offline; the fast suite blocks sockets and curl_cffi |

Also enrolled in the house contracts, as required:

- `guard_contract.CASES` gains `scrape_store` (a `None` body),
  `free_inference` (a model absent from the capability **and** price tables) and
  `local_review` (a throughput receipt over **zero** documents — `review_one`
  deliberately never raises, so the guard sits one level up; a docs/hour with no
  denominator is not a small number, it is not a number). Each is a real
  missing-input case that fails if the guard is removed.
- `signal_reachability`: all three classify automatically as **`tooling_only`**
  (reached from `scripts/`), `unclassified = 0`. No manual entry needed.

**Fast suite, whole repo, after every change in this lane:**

```
AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -q -m "not slow" -p no:randomly --timeout=300
7410 passed, 20 skipped, 124 deselected, 496 warnings in 663.69s (0:11:03)
```

**0 failed.** Before the fixes in §3 the same command gave `6 failed, 7348
passed` — the six `test_arena_brain.py` tests, one of which was reaching for a
live socket. They are fixed, not marked slow.

> **One unrelated failure appeared AFTER that run, at 13:26, and is not this
> lane's:** `test_signal_reachability::test_every_orphan_is_classified` names
> `backend.strategy.leak` — a module lane S created mid-session (roadmap S3).
> It needs a caller or a `CLASSIFIED` entry from its own author. Recorded here
> rather than fixed, because classifying somebody else's module is how a reason
> gets written by the person who does not know it.

---

## 9. WHAT DID NOT WORK

1. **No free DeepSeek via NIM.** Both `deepseek-v4-flash-0731` and
   `deepseek-v4-pro-0813` are listed and read-time-out at 60 s *and* 200 s.
   CANNOT DETERMINE, not disproven — worth one more probe on another day.
2. **`nvidia_nim` is not fit for a large batch.** HTTP 429 on the free tier bit
   in 2 of 5 runs. It is a second opinion and a fallback, not the workhorse.
3. **A reasoning model is the wrong default for strict-JSON extraction.**
   `gpt-oss-20b` burns 300–650 output tokens per document on thinking and still
   dropped one document at `max_tokens=1500`. A non-reasoning NIM model would be
   better, but the ones that served this account were the ones that rate-limited.
4. **`writer/palmyra-fin-70b-32k`** — the one finance-specific model in the
   catalogue — **404s for this account.**
5. **Two stale claims corrected, neither in a file this lane owns:**
   `scripts/connection_check.py`'s ENTITLEMENT verdict and the comment block in
   `model_provider.PROVIDERS["nvidia"]` both say models are unreachable that now
   answer. Left for the owning lane; recorded here and in the probe receipt.
6. **The known-answer battery is 6 documents.** It proves the plumbing and the
   null behaviour. It is **not** an accuracy estimate, and no claim about
   extraction quality should be made from it. The next step is the same battery
   at n ≈ 200 with a human-labelled sample.
7. **Nothing in this lane improves any book.** RESULT IMPROVEMENT: NONE.

---

## 10. FILES

**New (mine):**
`backend/services/free_inference.py` · `backend/services/scrape_store.py` ·
`backend/services/local_review.py` · `scripts/gdelt_pull.py` ·
`scripts/local_review_run.py` · `backend/tests/test_free_inference.py` ·
`backend/tests/test_scrape_store.py` · `backend/tests/test_local_review.py` ·
`backend/data/optimus/free_inference_2026-09-07/{L1_nim_probe,L3_known_answer_local_gguf,L3_known_answer_nvidia_nim}.json`

**Edited (minimal, additive):**
`backend/services/model_provider.py` (central pin imported; response guard added;
`purpose`/`provider_label`) · `backend/services/llm_research.py` (pin + guard on
the unguarded DeepSeek call site; `available()` honours `AEGIS_IGNORE_DOTENV`) ·
`backend/config.py` (13 zero-cost rows in `LLM_PRICE_PER_MTOK`) ·
`backend/tests/test_guard_missing_input_contract.py` (3 enrolments) ·
`backend/tests/test_arena_brain.py` (3 stub sites hardened) · `.gitignore`.

**No git state was changed by this lane. No orders, no deploys, no seals, no
pushes. DeepSeek spend: $0.00.**
