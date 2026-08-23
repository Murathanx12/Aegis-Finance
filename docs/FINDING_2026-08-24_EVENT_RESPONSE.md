# FINDING — 2026-08-24: post-earnings drift is real, tiny, and we cannot say which events have it

**Trial** `EVENT-RESPONSE-1` · **licence** PRODUCT_EXPERIMENT (SCREEN)
**spec_hash** `9a54b0c3da4cfe56` — frozen before the first number existed
**Receipt** `backend/data/optimus/event_response/event_response_receipt.json`
**50,910 events · 168 event months · n_effective = 168 MONTHS** (CANON §58)

## Verdict: **STOP.** The daily, options-blind version of this question is not licensed.

---

## 1. The question, and why it is the right one

Roadmap P1.1. Stocks trade on surprise, and by the time we could act, the obvious
part of an earnings surprise is already in the opening gap. So the tradable
question is never "was it a beat" — it is:

> given the event **and the market's first reaction to it**, is the rest of the
> move continuation or reversal?

`drift_k = sign(gap) × excess return over the k sessions strictly after the
event session.` Positive means the first move continued.

---

## 2. The machinery validated itself: PEAD is there

Before asking whether we can *rank* events, the receipt reports whether there is
anything to rank — the unconditional drift, which is a known effect and
therefore a check on the pipeline:

| horizon | mean of monthly means | SE | t |
|---|---|---|---|
| +1 session | **+0.00066** | 0.00025 | **+2.66** |
| +2 sessions | **+0.00084** | 0.00033 | **+2.58** |
| +5 sessions | +0.00044 | 0.00044 | +1.01 |

Post-earnings-announcement drift shows up at the right **sign**, a plausible
**magnitude** (~7–8 bps), and the right **decay** — gone by five sessions. A
pipeline that reproduces a known effect is not a broken pipeline, so the null
below is about the question, not the plumbing.

It is also **economically trivial**: 7 bps before any cost, on a signal that
requires trading every earnings event in the market.

---

## 3. And no model can say WHICH events drift

Out-of-sample rank IC within each event month, expanding-window by year
(train < Y, test = Y), 96 test months per arm:

| arm | IC | t | p | MDE₈₀ | BH-FDR |
|---|---|---|---|---|---|
| `surprise_only@1d` | +0.0043 | 0.50 | 0.62 | 0.024 | ✗ |
| `ridge@1d` | +0.0114 | 1.25 | 0.22 | 0.026 | ✗ |
| **`lightgbm@1d`** | **+0.0185** | 1.93 | 0.057 | 0.027 | ✗ |
| `surprise_only@2d` | −0.0018 | −0.22 | 0.83 | 0.024 | ✗ |
| `ridge@2d` | −0.0014 | −0.14 | 0.89 | 0.029 | ✗ |
| **`lightgbm@2d`** | **+0.0193** | 1.78 | 0.078 | 0.030 | ✗ |
| `surprise_only@5d` | +0.0071 | 0.75 | 0.46 | 0.027 | ✗ |
| `ridge@5d` | −0.0029 | −0.32 | 0.75 | 0.025 | ✗ |
| `lightgbm@5d` | +0.0128 | 1.22 | 0.22 | 0.029 | ✗ |

**Nothing survives BH-FDR across the nine arms.** LightGBM at 1 and 2 days is
suggestive (p ≈ 0.06, 0.08) and that is exactly the kind of number that becomes
a finding if you run nine arms and report the best one.

The published PEAD prior — scaled surprise alone — is **flat** (+0.004, −0.002,
+0.007). Whatever drift exists is not ranked by surprise size.

### Trees over linear: suggestive, and only at one horizon

| paired | diff | SE | t |
|---|---|---|---|
| `lightgbm − ridge @2d` | +0.0207 | 0.0135 | +1.53 |
| `lightgbm − ridge @5d` | +0.0156 | 0.0128 | +1.22 |
| `lightgbm − ridge @1d` | +0.0071 | 0.0107 | +0.66 |
| `ridge − surprise_only @1d` | +0.0071 | 0.0141 | +0.51 |

The declared rule required an arm to clear BH-FDR **and** beat ridge. `@2d`
clears the ridge half and fails the first, so the rule returns STOP — correctly.
A relationship that only appears in the arm that also failed significance is not
a relationship.

---

## 4. The null owes a second test, and here it is

CANON: a null owes MDE as well as significance. Every arm's MDE₈₀ is **0.024–
0.030** while the best observed IC is **0.019**. So this run had roughly 50–60%
power against the effect it actually saw.

**What can honestly be said:** no cross-sectional ranking of post-earnings drift
of size ≥ ~0.025 IC exists in these features, at this horizon, on this sample.

**What cannot:** that there is no effect. A 0.015 effect would have been missed
about half the time.

---

## 5. What is missing, named rather than quietly absent

Three fields are `None` or `UNKNOWN` through the entire corpus, and the first is
the one that matters:

* **`options_implied_move` — absent throughout.** This is the market's own
  forecast of the move size. Without it, "surprise" is measured against analyst
  consensus only, and the actual tradable quantity is
  `surprise − what was already priced`. This screen could not compute that. It
  is the single most likely reason a conditional signal did not appear.
* **Intraday.** The roadmap named 30m as a horizon. TAQ is pulled but not
  extracted, so v1 is daily. The reaction path within the first hour is where
  the roadmap expected the information, and it remains untested rather than
  answered.
* **`guidance_state` — UNKNOWN throughout** (`ibes.det_guidance` is not
  entitled). Guidance is frequently the part of an earnings release that moves
  the stock.

---

## 6. What this changes

**Do not build an earnings-response selector on daily bars without options
data.** That is the whole content of the STOP, and it is worth an evening.

`EVENT_RESPONSE` is **not** closed as an idea. What is closed is this
specification. The successor is one experiment, not a programme:

> extract the single-name option surface around these 50,910 events and re-ask
> the question with `surprise − implied move` as the central feature.

That has a named consumer now, which is the rule for un-deferring an
OptionMetrics pull (§4 of the roadmap): `stdopd` is the source, 1996 is already
on disk, and `opprcd`'s 4.31B rows are still not needed.

**Method note.** The first version of this script measured `fwd` from the event
session, which is close-to-close in CRSP and therefore *contains the overnight
gap*. Signing by that same gap would have made |gap| contribute positively to
the target by construction — a guaranteed "continuation" result that is pure
arithmetic. Caught by reading the code before running it; the window now starts
strictly at t+1, with entry at the event day's close.
