# ROADMAP 2026-09-10 — the model swap, the news loop, and the event net

**Licence:** `PRODUCT_EXPERIMENT` throughout. Nothing here promotes anything.
**Answers:** Murat's three additions of 2026-09-10, in his words:

> "there is a qwen 3.8 27b uncensored-fps... maybe it can analyze the news and
> stocks daily better and cheaper" · "there can be a system that automatically
> pulls news without need of LLM but LLMs can analyze it separately and can come
> to a decision with the LLM and the engine all working together" · "I want to
> build a semi LLM decoder encoder maybe that can dissect news and build a NN
> that learns from events itself and gets better... tokenization is hard so find
> a cheap and reliable system we can build."

---

## 0. RESULTS SCOREBOARD (unchanged by this document — it is a plan)

| | |
|---|---|
| RESULT IMPROVEMENT | **NONE from this file.** It plans three lanes; two are running as of writing. |
| what changed today | the night factory can survive a reboot and no longer replays itself (§1 of the day's work), and the .exe has a model-server it can stop by PID |
| LLM spend | **$0.00** — every lane here is local |

---

## 1. THE MODEL — it is **Qwen3-30B-A3B**, and the trade is real

**What Murat was told about.** "qwen 3.8 27b uncensored-fps" is
**Qwen3-30B-A3B**: 30.5B total parameters of which **~3.3B activate per token**
(a Mixture-of-Experts). That is the "fps" — 30B-model knowledge at roughly 3B-model
compute. "Uncensored" is an *abliterated* fine-tune; the ones on the Hub are
`huihui-ai/Qwen3-30B-A3B-abliterated` and `mlabonne/Qwen3-30B-A3B-abliterated`,
both re-quantised to GGUF by `mradermacher` and others.

**The hardware, measured 2026-09-10.** 31.4 GB RAM · RTX 5060 Laptop with
**8,151 MiB** of VRAM · Intel Ultra 7 255HX, 20 cores. The current model,
Qwen2.5-7B-Instruct-Q4_K_M, is 4.68 GB and sits entirely on the GPU: measured
5,861 MiB resident, 43.5 tok/s.

**Q4_K_M of Qwen3-30B-A3B is ~18.6 GB. It does not fit in 8 GB of VRAM.** It
fits in the 31 GB of system RAM. The way to run it is llama.cpp's
`--n-cpu-moe`: keep the attention stack on the GPU and put the MoE expert
tensors in system RAM. Because only ~3.3B parameters activate per token, the
CPU side stays tractable. `backend/services/llama_server.py` already carries the
knob as `LLAMA_N_CPU_MOE` (env `AEGIS_LLAMA_N_CPU_MOE`), defaulting to 0, which
is right for a dense 7B and wrong for this model.

**Three things to say plainly before anyone swaps it in.**

1. **A model swap is a NEW ARM, not an upgrade.** R2 — the programme's only
   live lane, +16.19%/yr over its shuffled-digest control, t 3.92 — was measured
   with Qwen2.5-7B. Its pre-registration (`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`,
   filed today) freezes the model file's sha256 for exactly this reason. Running
   R2 on Qwen3 does not update R2's number; it opens R2-Qwen3 beside it, and the
   two are compared on the same blocks with the same control.
2. **"Uncensored" is probably the wrong variant for this job.** Abliteration is
   a directional ablation of refusal behaviour and it measurably costs benchmark
   performance. The refusals it removes are the ones we do not hit — we are not
   asking the model for anything it would decline. The one real argument for it
   is that instruct models sometimes refuse to "give financial advice", which is
   a genuine friction in a decision prompt. **So measure it**: run the plain
   `Qwen3-30B-A3B-Instruct` and one abliterated build over the same digests and
   count the refusal rate. If plain refuses ~0% of R2's prompts, take the plain
   one and keep the benchmark points.
3. **Cheaper is not obvious.** Both are $0 — they are local. The cost is
   wall-clock and heat. A 30B-A3B with experts in RAM will be meaningfully slower
   than 43.5 tok/s. Whether that is worth it is decided by R2's own metric, not
   by a benchmark table.

**Status:** `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` is downloading to
`~/llama/models/`. The test, when it lands, is: load it with `--n-cpu-moe`
tuned until it fits, measure tok/s and VRAM, then run R2's frozen prompt over
the SAME 112 blocks and compare against the registered Qwen2.5-7B numbers with
the shuffled-digest control re-run underneath both.

---

## 2. THE NEWS LOOP — the pull already exists and needs no LLM

Murat's instinct is right and the good news is that most of it is built.

**What exists.** The collector runs in the OTHER repo — `aegis-alpha-terminal`,
on Railway — and writes `state/corpus/observations/*.jsonl`. It uses no LLM: it
is an Alpaca/Benzinga wire pull. E1 read **408,218** news rows from it on
2026-09-09 and joined **339,657** of them to the Alpaca bar of the first session
whose open is strictly after publication, twice-labelled minus SPY, in **39
seconds at $0**. That parquet is `backend/data/optimus/text_return_panel/news_returns_2025_26.parquet`
and it is the single highest-value data asset the programme has.

**What is missing** is smaller than it sounds:

- the join is a one-shot script, not a nightly job that appends and resumes;
- the historical backfill stalled at 83.6% with no cursor, so the dense corpus
  is 2025-26 while CRSP ends 2024-12 — which is why every text lane is stuck in
  a 21-month window;
- nothing schedules either.

**The design Murat describes — "LLMs analyse it separately and come to a
decision with the LLM and the engine all working together" — is right in shape
and premature in timing.** CLAUDE.md's bottleneck section is explicit: a new
mechanism arrives as its OWN book, never as a weight in a composite, and a
learned router comes *after* several independent selectors exist. There is
currently **one** independent selector with evidence. Combining the LLM's read
with the engine's score today would hide the only thing worth measuring —
**whether their errors are different errors.**

So the order is: run them as two books over the same universe and the same
dates, log both decisions per name-day, and measure the correlation of their
errors. If the errors are correlated, combining them buys nothing and we have
saved the work. If they are not, the combination is earned and the router has
something to route. That measurement is cheap and it is the precondition, not
an extra step.

---

## 3. THE EVENT NET — what is closed, and the one design that is not

Murat: *"a semi LLM decoder encoder that can dissect news and build a NN that
learns from events itself... tokenization is hard so find a cheap and reliable
system."*

He is right that tokenization is the hard part, and the correct conclusion is
**not to do it**. Two corpses say so, and both are ours:

| corpse | date | what it closed |
|---|---|---|
| a from-scratch encoder on 528k headlines | 2026-09-08 (S45) | **it loses to TF-IDF in every era.** Training a text representation from scratch on this much data is not enough data. |
| the made-up-news curriculum (C2) | 2026-09-09 | BASELINE +30.6%/yr t 1.78 > CONTROL +19.5 > TRANSFER +15.0. The net **did** learn the curriculum (61.5% vs 48.4% shuffled) and **the representation then discarded return-relevant information.** Pre-training on a proxy task and transferring made things worse. |

Neither closes "a neural net that learns from events". They close two specific
routes: *learn the representation yourself*, and *learn it on a proxy*.

**What survives both is cheap, reliable, and laptop-sized: a FROZEN pretrained
encoder plus a small head learned on the return directly.**

- No tokenizer is written — the encoder ships with one.
- No representation is learned — it is frozen, so it cannot discard anything
  the way C2's did.
- Only the head is trained, on the label we actually care about.
- A 33M-parameter sentence encoder (e.g. `BAAI/bge-small-en-v1.5`, 384-dim)
  embeds 339,657 documents on the 5060 in minutes, once, cached to disk. $0.
- It "gets better" honestly: as the panel grows nightly, the head is refit. The
  representation stays fixed, which is the point — a moving representation is
  what made the last two attempts unfalsifiable.

**Three controls, non-negotiable, on identical splits:**

1. **TF-IDF + the same head** — the bar, because it beat the from-scratch encoder.
2. **Shuffled text** — headlines randomly reassigned to (symbol, date). If the
   arm does not beat this, the "signal" is the calendar and the universe.
3. **No text at all** — the head on dollar volume and momentum alone.

Walk-forward temporal splits, purged with an embargo, **reported per era**. A
pooled number would hide that the whole effect can be one quarter — which is
what `feedback_the_learner_edge_was_six_rebound_months` records at 96.2%.

**If the frozen embedding does not beat TF-IDF, that is the result and it is
worth more than a positive one that turns out to be the calendar.** The prior is
on TF-IDF; S45 put it there.

This is running now as `scripts/night_n3_frozen_embedding_head.py`.

---

## 4. WHAT MUST NOT REGRESS (added to the 09-09 and 09-10 lists)

9. **A model swap opens a new arm; it never updates an existing lane's number.**
   R2's pre-registration freezes the model sha256 so this cannot happen quietly.
10. **The representation is frozen or the experiment is unfalsifiable.** C2 is
    the receipt: a representation that moves during training can discard the
    label and still report a learning curve.
11. **Three controls or no claim** for any text lane: TF-IDF, shuffled text,
    no-text. The first is the bar, the second catches the calendar, the third
    catches the universe.
