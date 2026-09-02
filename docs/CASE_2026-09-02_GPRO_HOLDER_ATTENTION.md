# CASE 2026-09-02 — GPRO / HOLDER ATTENTION

**Status: CASE FILE + IDEA CAPTURE. Nothing pre-registered, nothing traded,
no order placed, no lane seeded.** §4 is a *draft* typed hypothesis; it becomes
a trial only through `.claude/skills/pre-register-trial`, and only after the
data inventory in §4.6 is actually built.

**Licence sought:** `PRODUCT_EXPERIMENT` for the lane in §4 (paper only).
**Licence NOT sought:** `RESEARCH_CLAIM`. Nothing here is alpha yet. n = 1.

**Miss type (accepted upstream, not re-derived here): NOT OBSERVED.**
AEGIS never had an opinion on GPRO. The universe is configured watchlists plus
the top ~400 liquid names from an archived CRSP snapshot, and
`alpha/sources/sec.py` watches 8-K Item 2.02 only — not 13D/13G. This is not a
wrong rejection. The engine was never asked the question.

One correction to the natural follow-on assumption, because it matters for the
fix: **the liquidity floor did not exclude GPRO.** Pre-event dollar ADV was
~6.5M shares × ~$0.61 ≈ **$4.0m/day** (11 sessions, 14–28 Aug), which clears the
$3.0m/day universe floor and sits far above the $25k/day `OBSERVE_ONLY`
threshold in `universe.execution_authority`. GPRO was excluded by **universe
construction**, not by any risk gate. That is a cheaper fix than it looked.

Sibling document: `docs/IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md`
(H1–H7). This case is the first concrete instance of that idea's §3 row
"who bought / what percentage / when".

## THE VERDICT, BEFORE THE EVIDENCE

**RESULT IMPROVEMENT: NONE.** No position, no lane, no claim. What this document
produces is one dataset row, one collector specification, and one falsifiable
design.

**GPRO is NOT ACTIONABLE NOW.** The deal is public, the stock has repriced to
**$1.23** against a stated **$1.14** cash leg, the merger agreement is **not on
file**, and the implied close probability at a plausible stub value is
**85%** — which is the market price, not an edge. Reward:risk **0.17**
(+8.9% up, **−51.2%** down to the undisturbed $0.600). Correct action:
**OBSERVE + backfill the missed-signal dataset.**

**The window that was missed was real and it was seven sessions long.** The 13G
was free, structured and public on EDGAR from **2026-08-20**, and over the next
five sessions GPRO returned **−1.63%** on **1.03× normal volume**. It took a
Bloomberg newsletter on **2026-08-30** to move it +46%.

**But the analogue evidence does not support a book.** Across six individual-filer
stake disclosures (2012–2024), the **median 63-session return is −4.1%, with 4 of
6 negative**; stripping the single outlier (GME/Cohen 2020) makes the 63-session
mean **−11.2%** and the 126-session mean **−4.4%**. Two of six filers fully
exited; one company went to zero after the filer had made ~$59m. **The one case
that structurally resembles GPRO — Jay-Z's 11.4% SC 13G on Perfumania, 2012-05-04,
a $128m company with a genuinely muted reaction — lost at every horizon
(−8.2% D63, −34.8% D126, −30.3% D252).** And **§4's own precursor fires on none
of the six**, which is either correct exclusion or proof that the target
population is invisible to web search. Only the EDGAR sweep can tell them apart.

**One live bug found on the way (§4.6b).** The `ACTIVIST_13D` copy-lab lane is
**ACTIVE**, seeded 2026-08-14, and has recorded **`events_considered: 0`** for
its entire life — while its sibling `CORPORATE_INSIDER_CLUSTER`, on the same
engine in the same run, recorded **92**. `ineligible_reasons` is `{}`: not
refused, **never presented**. The lane is also 13D-only by design (a 13G is out
of scope) and carries `min_price: 5.0`, which would have deleted a $0.615 stock
regardless. That is the repair, and it is cheaper than anything else in this
document.

---

## §1. THE FACTS

### 1.1 The Schedule 13G — primary source, read directly

SEC EDGAR, GoPro Inc. (CIK 0001500435), accession **0001630759-26-000003**,
form **SCHEDULE 13G**, filed **2026-08-20**
([primary_doc.xml](https://www.sec.gov/Archives/edgar/data/1500435/000163075926000003/primary_doc.xml)).
Every field below is quoted from that XML, not from press coverage.

| XBRL/XML field | Value |
|---|---|
| `reportingPersonName` | **Fischbach Mark Edward** (Markiplier) |
| `typeOfReportingPerson` | **`IN`** — natural person |
| `designateRulePursuantThisScheduleFiled` | **Rule 13d-1(c)** — passive investor |
| `securitiesClassTitle` | Class A Common Stock |
| `issuerCusipNumber` | 38268T103 |
| `eventDateRequiresFilingThisStatement` | **2026-07-13** |
| Signature date | 2026-08-20 |
| `soleVotingPower` / `soleDispositivePower` | **13,500,000 / 13,500,000** |
| `sharedVotingPower` / `sharedDispositivePower` | 0 / 0 |
| `classPercent` | **8.5** |
| Item 3 (source of funds) | Not applicable (13G) |
| Item 10 certification | Present — "not acquired … for the purpose of … changing or influencing the control of the issuer" |
| Address | c/o Jaffe and Associates, Inc., 16255 Ventura Blvd Suite 1240, Encino, CA 91436 |

Four things in that table are *machine-readable precursors*, available free on
the day of filing, and none of them require reading a news story:

1. **`typeOfReportingPerson = IN`.** A natural person, not `HC`/`IA`/`FI`/`CO`.
   This one enum value is the entire filter for "is this a person or an
   institution". It is a required field on the structured 13G schema.
2. **Rule 13d-1(c)**, i.e. a passive filer who is nonetheless above 5%.
3. **Filing lag = 38 calendar days / ~24 business days.** Under the amendments
   effective 2024-09-30, a Rule 13d-1(c) passive filer must file within **five
   business days** of crossing 5% ([Skadden,
   2024-09](https://www.skadden.com/insights/publications/2024/09/new-schedule-13g-accelerated-filing-deadlines)).
   Event date 2026-07-13 ⇒ due ~2026-07-20; filed 2026-08-20. The filing appears
   **late**. Flagged as *apparent* — I cannot rule out an alternative reading of
   the event date from the face of the filing alone. But the lag itself is a
   field, it is free, and §4 turns it into a feature rather than a curiosity.

   **And it is not a one-off.** Every individual-filer case in §2 for which we
   have both dates filed late against the deadline in force at the time:
   **Carter/Perfumania** (event 2012-04-18, filed 2012-05-04, 10-calendar-day
   rule), **Musk/Twitter** (~11 days late — the SEC sued him over it in Jan
   2025), **Fischbach/GoPro** (event 2026-07-13, filed 2026-08-20, 5-business-day
   rule). **Three for three.** Institutions have compliance departments;
   individuals have business managers. That is a mechanism, not a coincidence,
   and it is why the stale-but-unpriced window exists at all.
4. **Filer address is a business-management firm in Encino, CA** — the
   entertainment-industry business-manager pattern, not a fund address. A
   weaker, softer signal than the enum, but it is text on the cover page.

**Ownership arithmetic.** Class A outstanding at 2026-08-07:
**158,245,863**; Class B: **26,258,546**; total **184,504,409**
(10-Q cover, filed 2026-08-10, XBRL `dei:EntityCommonStockSharesOutstanding`).

- 13,500,000 / 158,245,863 = **8.53% of Class A** ✔ matches the filed 8.5%.
- 13,500,000 / 184,504,409 = **7.32% of total equity**.
- Class B carries super-voting rights and is Woodman-controlled, so
  Fischbach's **voting** power is roughly 13.5M / (158.2M + 262.6M) ≈ **3.2%**.
  "GoPro's largest shareholder" is true of the Class A register and materially
  overstates his control. The press framing and the governance reality differ,
  and the engine should record the second one.

**Stake value.** At the 2026-08-20 close of $0.6150 the stake was worth
**$8.30m**; at the 2026-09-01 close of $1.23, **$16.61m**. Cost basis is
**not disclosed** — a 13G under 13d-1(c) has no Item 3 source-of-funds
requirement. Every press figure of "roughly $9 million" is a mark, not a cost.

### 1.2 The price path — the part that matters

Daily closes, Yahoo Finance GPRO history (unadjusted; no splits or dividends
in the window). The third column is the return measured from the close on the
13G filing date.

| Date | Close | vs 2026-08-20 | Volume | Note |
|---|---|---|---|---|
| 2026-08-14 | $0.5950 | — | 6.88m | |
| 2026-08-17 | $0.6140 | — | 5.76m | |
| 2026-08-18 | $0.5920 | — | 5.98m | |
| 2026-08-19 | $0.6350 | — | 6.64m | |
| **2026-08-20** | **$0.6150** | **0.00%** | **5.18m** | **13G filed on EDGAR** |
| 2026-08-21 | $0.6300 | +2.44% | 6.49m | t+1 |
| 2026-08-24 | $0.6000 | −2.44% | 4.90m | t+2 |
| 2026-08-25 | $0.6080 | −1.14% | 5.87m | t+3 |
| 2026-08-26 | $0.5970 | −2.93% | 8.10m | t+4 |
| 2026-08-27 | $0.6050 | **−1.63%** | 7.07m | **t+5** |
| 2026-08-28 | $0.6000 | −2.44% | 8.96m | t+6 — last undisturbed close |
| 2026-08-31 | $0.8760 | +42.44% | **220.0m** | t+7 — Bloomberg story |
| 2026-09-01 | $1.2300 | **+100.00%** | **497.4m** | t+8 — merger announced 09:20 ET |

**The single most important number in this document is `−1.63%`.**

The filing was public, structured and free on EDGAR from 2026-08-20. Over the
next five sessions the stock returned **−1.63%** and traded **6.5m
shares/day against a 6.3m pre-filing average — a volume ratio of 1.03x.**
The market did not react to the filing at all. It reacted to a *Bloomberg
newsletter* published **2026-08-30 22:15 UTC** (Sunday evening ET),
[*"YouTube Star Markiplier Is Now GoPro's Largest
Shareholder"*](https://www.bloomberg.com/news/newsletters/2026-08-30/youtube-star-markiplier-is-now-gopro-s-largest-shareholder),
which produced **+46.0%** on Monday 2026-08-31.

So: the observable window was **seven trading sessions long**, and it was closed
by a media outlet rather than by the filing. That is a detectability claim, and
it is the whole reason this case is interesting rather than a hindsight story.

**2026-09-01 intraday.** Open $1.35, high $1.64, low $1.16, close $1.23
(+40.38% on the day; previous close $0.8762). Headline percentages in circulation
(+77.5%, "above $1.50", "+140%") are **intraday marks or multi-day cumulatives,
not closes**. The tape **faded 25.0% from the $1.64 high into the $1.23 close**,
and the overnight print on Blue Ocean ATS at 2026-09-02 00:23 ET was **$1.20**.
The market moved *toward* the deal consideration through the afternoon, not away
from it. Market cap at the close: **$226.94m**. 52-week range **$0.57–$3.05**.

**Drawdown.** All-time high **$98.47 intraday, 2014-10-07**. At the 2026-08-20
close of $0.6150 the drawdown is **−99.38%**. At the 2026-09-01 close, −98.75%.

**Short interest.** ~**24.88m shares short = 16.46% of float** at the
2026-08-14 settlement date, days-to-cover ~3.3 (Benzinga / Fintel, as reported
2026-09-01). Fischbach's 13.5m shares are **54% of the short interest** and were
removed from the effective float. Whatever else this is, it is also a short-squeeze
setup, and §4 must control for that or the lane will simply rediscover
short interest.

### 1.3 The catalyst was already public — the control nobody wants to run

This is the fact that most damages the romantic version of the story, so it goes
in the body and not a footnote.

- **2026-04-13** — GoPro engages Oliver Wyman for defense/aerospace expansion;
  subsequently receives "several unsolicited inbound strategic inquiries".
- **2026-05-11** — Board **announces a review of strategic alternatives**,
  explicitly including a sale or merger ([GoPro
  IR](https://investor.gopro.com/press-releases/press-release-details/2026/GoPro-Board-of-Directors-Announces-Review-of-Strategic-Alternatives/default.aspx)).
- **2026-05-13** — **Houlihan Lokey retained** as financial advisor ([GoPro
  IR](https://investor.gopro.com/press-releases/press-release-details/2026/GoPro-Retains-Investment-Bank-Houlihan-Lokey-to-Pursue-Strategic-Alternatives/default.aspx)).
- **2026-08-11** — Q2 2026: revenue **$104.9m (−31% y/y)**, hardware **$76.0m
  (−40%)**, units **~291k (−38%)**, GAAP net loss **$51m**, EPS **$(0.30)**,
  **cash $27.3m**, no guidance. CEO Woodman: the sale process is in **"the later
  stages"**
  ([CineD, 2026-08-11](https://www.cined.com/gopro-says-its-sale-process-is-in-the-later-stages-camera-sales-fall-38-cash-down-to-27-million/)).

A publicly announced, banker-run, **late-stage** sale process was live for
**102 days** before the 13G was filed. The honest reading is therefore:

> The 13G plausibly contributed **nothing** to the fundamental outcome. The deal
> was in the pipeline and would have been announced regardless. What the 13G
> plus the Bloomberg story added was a **+46% attention repricing** on 2026-08-31,
> one session before the deal.

GoPro's own CEO says as much, in a filed document. From the employee email in the
DEFA14A soliciting material filed 2026-09-01 (accession 0001628280-26-059846):

> "This transaction is a major milestone in **the strategic review process we
> announced in May**." — Nicholas Woodman

Which is exactly the shape of "what observation would separate this from ordinary
factor beta?" — here the confound is not beta, it is a **pending-M&A catalyst
that was in the public record**. §4 handles this by *requiring* the catalyst as
part of the conjunction rather than pretending the holder was the cause. See
§4.3.

### 1.4 The transaction announced 2026-09-01

Primary source: 8-K filed 2026-09-01, accession 0001628280-26-059839
([8-K](https://www.sec.gov/Archives/edgar/data/1500435/000162828026059839/gpro-20260901.htm),
[Ex-99.1 press
release](https://www.sec.gov/Archives/edgar/data/1500435/000162828026059839/gpro2026-09x01exhibit991.htm)),
released 09:20 ET.

| Term | As disclosed |
|---|---|
| Structure | Agreement and Plan of Merger. **Parent = Action Acquisitions LLC** (DE LLC); **Merger Sub = Starman Optical, Inc.** (DE, wholly owned by Parent). Merger Sub merges into GoPro; **GoPro survives as a subsidiary of Parent** |
| Cash consideration | **$285,000,000 aggregate, "or $1.14 per share"** |
| Adjustment | "**subject to potential adjustment based on GoPro's net working capital at closing**" |
| Retained equity | GoPro shareholders "**maintain ownership of approximately 10% of the outstanding shares of the Company**" |
| Debt | ~**$92m repaid in full at closing** |
| Listing | Remains publicly listed on Nasdaq |
| Timing | Expected close **by year-end 2026** |
| Conditions | Regulatory approvals; **GoPro stockholder approval**; other customary conditions |
| Board | Approved by both boards |
| Advisors | **Houlihan Lokey** (financial advisor to GoPro; **fairness opinion delivered**); Fenwick & West (legal) |
| Starman | Privately held US optical-photonics company, a Starman Holding company; CEO **Charles Tebele**; "Starman New Photonics" transceiver business |
| Strategic pitch | US-onshore optical transceivers into AI data centre, defense, government, robotics, aerospace; GoPro's 2,500+ US patents |

**Three disclosure gaps, each material, each verifiable from the filing itself:**

1. **The merger agreement was NOT filed.** The 8-K carries **Item 8.01 (Other
   Events) only** — not Item 1.01 (Entry into a Material Definitive Agreement) —
   and its exhibit list is **99.1 (press release) and 104 (cover-page XBRL)**.
   There is therefore **no public termination fee, no outside date, no go-shop
   or no-shop language, no financing condition, no voting/support agreement, and
   no MAE definition** as of 2026-09-02. The agreement exists — the DEFA14A
   filed the same day (accession 0001628280-26-059846) names it as "the
   Agreement and Plan of Merger by and among GoPro, Action Acquisitions LLC and
   Merger Sub, **dated September 1, 2026**" — it simply has not been made public.
2. **The per-share arithmetic does not reconcile to the current share count.**
   $285.0m ÷ $1.14 implies a denominator of **250.0m shares**. Shares outstanding
   at 2026-08-07 were **184.5m**. That is **65.5m shares (+35.5%) of assumed
   dilution** between now and closing, unexplained in the release. GoPro has a
   live Yorkville equity-line resale prospectus (424B3 supplements filed
   2026-08-10 and again 2026-09-01) and $34.7m of derivative liabilities at
   2026-06-30. **On the current 184.5m shares, $285m is $1.5447/share.** Which
   denominator applies is the single highest-value unknown in the whole case
   (see §3.2), and it is not answerable from public filings today.
3. **Financing is undisclosed.** $285m of cash to holders plus ~$92m of debt
   repayment is **~$377m of cash** required by a **privately held** acquirer,
   against a target with **$27.3m of cash**. No commitment letter, no equity
   backstop, no lender is named anywhere in the public record.

---

## §2. WHAT CREATOR / CELEBRITY HOLDERS NORMALLY DO

### 2.0 How to read this section, and against what

**"Better than what?"** The comparison for a celebrity/creator stake disclosure
is **not zero**. The institutional baseline is Brav, Jiang, Partnoy & Thomas,
*The Returns to Hedge Fund Activism* / *Hedge Fund Activism, Corporate
Governance, and Firm Performance* (Journal of Finance, 2008; hand-collected
2001–2006 sample): **abnormal announcement return ≈ +7%, with no reversal over
the following year**
([SSRN 948907](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=948907)).

So an ordinary **13D by a professional activist already earns ~+5–7%** around
the filing. **A routine institutional 13G earns close to nothing** — a passive
5% crossing by an index or mutual fund is rebalancing, not news, and the
literature treats the 13G→13D *reclassification* as the event, because the
change in intent is the entire signal.

That split is the right frame, and it cuts **in favour** of §4 rather than
against it: Fischbach filed a **13G**, whose baseline is ≈0, and the market duly
delivered **−1.63% over five sessions**. The hypothesis is therefore not "beat
+7%" — it is *"the ≈0 baseline is correct for institutions and wrong for a
specific, machine-identifiable subclass of filers."* Any analogue below that
shows "+X% on announcement" and stops there has told us nothing the
institutional base rate does not already explain; what matters is the
**21–63 session** column and the **eventual outcome** column.

**Three warnings about everything in this section.** They are not hedging; they
are the reason §2 informs §4's *design* and cannot license a trade:

1. **The sample is media-selected.** Cases become findable *because* they moved.
   Non-events by non-famous individuals are, by construction, unsearchable on
   the open web. The measured base rate here is an **upper bound**, biased
   upward by an unknown amount, and §4.4's Control D exists precisely because
   only a systematic EDGAR sweep can fix that.
2. **n is tiny and the outcomes are fat-tailed.** Per
   [[feedback-check-the-tail-before-the-mean]], read the **median** case, not
   the mean, and read the losers first.
3. **Announcement pops and holding returns are different questions.** Several
   cases below have a large day-1 move and a negative 63-day and a bankrupt
   ending. Terminal wealth is the objective, not the pop.

### 2.1 The analogue table

**Return provenance.** All D1/D5/D21/D63/D126 returns below are computed **from
our own CRSP daily file** (`backend/data/optimus/wrds/crsp_dsf_<year>.parquet`),
split-adjusted via `cfacpr`, based off the **close before** the filing became
public. Delisted names (BBBY, TWTR) are in CRSP and are *not* available from the
public price APIs — this is exactly the survivorship hole the house has been
bitten by before, and using CRSP closes it. Market caps are CRSP
`|prc| × shrout`. Drawdowns are measured against the maximum split-adjusted
close **inside the loaded CRSP window** and are therefore **conservative**
(window-limited) — the true drawdown from an older all-time high is larger.
Filing dates, forms and stake sizes are from EDGAR and contemporaneous press.

| # | Target | Filer (form, date public) | Stake | Cap at t−1 | DD at t−1 | D1 | D5 | D21 | **D63** | D126 | Eventual outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A0** | **PERF** (Perfumania Holdings) | **Shawn Corey Carter (Jay-Z)** — **SC 13G**, filed 2012-05-04 (event 2012-04-18) | 1,919,784 sh, **11.4%** — but only **300,000 real shares**; the rest are warrants | **$128m** | −73.4% | **−4.6%** | −2.0% | −7.9% | **−8.2%** | −34.8% | **−30.3% at D252.** Thinnest name in the set (**ADV20 $0.24m/day**). CRSP coverage ends 2017-08; Perfumania restructured out of the public market |
| A1 | **GME** | Ryan Cohen / RC Ventures — **SC 13D**, 2020-08-31 (event 08-28) | 5.8m sh, **9.0%** | **$349m** | −83.9% | **+23.9%** | +41.9% | +92.0% | **+198.3%** | +2,092.6% | Chairman Jan 2021; ~100× at the Jan-2021 peak; later CEO; **still holds**. Extreme winner |
| A2 | **BBBY** | Ryan Cohen / RC Ventures — **SC 13D**, 2022-03-06 (Sun) | 7.78m sh + 1.67m opt, **9.8%** | $1,326m | −69.4% | **+34.2%** | +23.5% | +41.0% | **−49.9%** | −46.7% | **Cohen exits 16–18 Aug 2022 (~+$59m). Chapter 11 2023-04-23; equity cancelled. Last CRSP close 2023-05-02 $0.0751 = −99.5%** |
| A3 | **TWTR** | Elon Musk — **SC 13G**, 2022-04-04 (**~11 days late**; 13D next day) | 73.49m sh, **9.2%** | $31,473m | −49.4% | **+27.1%** | +17.6% | +24.3% | **−2.4%** | +8.2% | Musk *himself* acquires at **$54.20**; last close 2022-10-27 $53.70 = **+36.6%**. SEC sues him in Jan 2025 over the late filing |
| A4 | **CHWY** | Keith Gill ("Roaring Kitty") — **SC 13G**, 2024-07-01 (event 06-24) | 9.1m sh, **6.6%** (~$245m) | $3,733m | −77.0% | **−6.6%** | −9.0% | −8.9% | **+10.0%** | +25.1% | **+20% premarket → closed −6.6% the same session.** Gill later filed a 13G/A reporting **0 shares** |
| A5 | **GME** | Keith Gill — **SC 13D**, filed 2024-06-24 after close | 9,001,000 sh | $7,241m | −72.8% | **+5.4%** | −1.4% | +1.5% | **−5.7%** | +26.1% | Nothing. The most famous retail investor alive, on the most famous meme stock, and 63 sessions later the stock was **down 5.7%** |

*(A5 stake percentage as filed is not restated here — GME's share count was moving
on ATM issuance through 2024 and I did not verify the exact denominator. Marked
**NOT VERIFIED** rather than guessed.)*

### 2.2 The base rate, read the way the house requires

| Horizon | Mean | **Median** | Mean **excluding A1** | Negative |
|---|---|---|---|---|
| D1 | +13.2% | **+14.7%** | +11.1% | 2 of 6 |
| D5 | +11.8% | +8.1% | +5.7% | 3 of 6 |
| D21 | +23.7% | +12.9% | +10.0% | 2 of 6 |
| **D63** | **+23.7%** | **−4.1%** | **−11.2%** | **4 of 6** |
| D126 | +345.1% | +16.7% | **−4.4%** | 2 of 6 |

Four readings, in the order that matters:

1. **The announcement pop is real, and it is not obviously bigger than the
   institutional base rate.** Median D1 **+14.7%** across six individual-filer
   disclosures. BJPT's professional-activist 13D baseline is +5–7%, and four of
   the six were filed on names that already carried heavy retail attention.
   Nothing here separates "famous filer" from "13D on a heavily-shorted small
   cap".
2. **The pop does not survive to 63 sessions, and by then most cases are
   losing.** Median D63 **−4.1%**, with **4 of 6 negative**. The +23.7% mean is
   **one name**: strip A1 (GME/Cohen 2020) and D63 becomes **−11.2%** and D126
   becomes **−4.4%**. This is [[feedback-check-the-tail-before-the-mean]]
   arriving on schedule — *the mean is a single observation wearing a
   distribution's clothes*, and a book cannot pre-identify which of six will be
   the 100×.
3. **The filer's outcome and the follower's outcome are different variables.**
   A2 is the case that should be printed on the wall. Cohen bought BBBY at an
   average of **$15.34**, sold into 16–18 Aug 2022 at **$18.68–$29.22**, and
   made **~$59m**. The company filed Chapter 11 eight months later and the
   equity went to **zero**. The stock fell **−19.6% on 2022-08-18** and
   **−40.5% on 2022-08-19** as the exit became known. *He won. Everyone who
   copied him and held lost 100%.* In A4, Gill likewise exited to **0 shares**.
   **Two of six filers fully exited**, and in both cases the market learned
   afterwards.
4. **The closest analogue to GPRO is A0, and it lost money at every horizon.**
   Shawn Carter's Perfumania 13G is the *only* individual-celebrity SC 13G on a
   sub-$1B distressed company found in EDGAR before Fischbach's — fourteen years
   of searching produced exactly one prior instance. It has GPRO's shape: `IN`
   filer, 11.4%, $128m market cap, deeply drawn down, **and a genuinely muted
   reaction (D1 −4.6%, D5 −2.0%, volume 1.22× normal)**. The market ignored it
   *correctly*: **−8.2% at D63, −34.8% at D126, −30.3% at D252**, and the issuer
   left the public market by 2017. **The single case that most resembles GPRO
   is a loser.** It is also the case that would have been unbuyable —
   ADV20 **$0.24m/day** — which is condition (6) doing its job.

   Two design lessons fall straight out of A0's cover page. First, **only
   300,000 of the 1,919,784 "beneficially owned" shares were actual shares**;
   84% was warrants. `classPercent` is a beneficial-ownership construct that
   includes derivatives, so §4 must record `shares_outright` separately or it
   will treat an option position as a share position. Second, Carter's filing
   was also **late** (event 2012-04-18, filed 2012-05-04, against a
   then-10-calendar-day deadline).

**And a fourth reading, which is the one that generalises:** A3 (Musk/TWTR) is
the SEC's own statement of the §4 mechanism. The complaint's theory is that the
**late filing** let Musk buy 6m+ additional shares "at artificially low prices"
and cost other holders "at least **$150 million**". That is a regulator asserting,
in a filed complaint, that *an individual's undisclosed accumulation is worth
real money to the person who knows about it before the market does*. GPRO's
filing was also apparently late (§1.1). The mechanism has an official endorsement;
what it does not have is a tested, cost-surviving, ex-ante rule.

### 2.3 Scoring the analogues against §4.2's precursor — the uncomfortable result

| Case | (1) natural person | (2) no 13F | (3) >5% | (4) DD ≥80% | (5) cap <$1B | (6) ADV ≥$1m | (7) muted 5d | **Fires?** |
|---|---|---|---|---|---|---|---|---|
| **A0 PERF/Carter 2012** | ✔ | ✔ | ✔ (11.4%) | **✘ (−73.4%)** | ✔ ($128m) | **✘ ($0.24m/day)** | **✔ (−2.0%, 1.22×)** | **NO** |
| A1 GME/Cohen 2020 | ✔* | ✔ | ✔ | ✔ (−83.9%) | ✔ ($349m) | ✔ | **✘ (+23.9% D1)** | **NO** |
| A2 BBBY/Cohen 2022 | ✔* | ✔ | ✔ | ✘ (−69.4%) | ✘ ($1.33bn) | ✔ | ✘ (+34.2%) | **NO** |
| A3 TWTR/Musk 2022 | ✔ | ✔ | ✔ | ✘ (−49.4%) | ✘ ($31.5bn) | ✔ | ✘ (+27.1%) | **NO** |
| A4 CHWY/Gill 2024 | ✔ | ✔ | ✔ | ✘ (−77.0%) | ✘ ($3.73bn) | ✔ | ✘ (volume) | **NO** |
| A5 GME/Gill 2024 | ✔ | ✔ | n/v | ✘ (−72.8%) | ✘ ($7.24bn) | ✔ | ~✔ | **NO** |
| — GPRO/Fischbach 2026 | ✔ | ✔ | ✔ | ✔ (−99.4%) | ✔ ($113m) | ✔ | ✔ (−1.63%, 1.03×) | **YES** |

\* RC Ventures LLC and Ryan Cohen filed **jointly**. Condition (1) must
therefore be *"any reporting person on the filing has
`typeOfReportingPerson == IN`"*, not *"the filing has exactly one `IN` filer"* —
a real implementation detail that would silently drop A1 and A2 if written naively.

**The precursor fires on ZERO of six analogues.** Four things follow, and the
last is the one that decides what to build:

- **The exclusions are mostly correct.** A2, A3, A4 and A5 were large or
  moderately-drawn-down companies; the conjunction is not supposed to fire on a
  $31bn or $7bn company, and it did not.
- **A0 is the informative exclusion, and it is a two-sided lesson.** Perfumania
  passed the filer test, the size test and — uniquely — the **muted-reaction**
  test, and still lost at every horizon. It was vetoed by **(4)** drawdown
  (−73.4% against an 80% bar) and **(6)** liquidity ($0.24m/day against a $1m
  floor). If those two conditions are the only thing standing between §4 and a
  −34.8% D126, then **the drawdown bar and the ADV floor are carrying the whole
  hypothesis**, and their exact values must be set before the sweep and never
  after. GPRO clears both comfortably (−99.4%, $4.0m/day); Perfumania did not.
  That is either the design working, or it is two free parameters fitted to one
  name. **Only the sweep can tell those apart**, and §4.7's SCREEN must vary
  both.
- **The one genuine near-miss is the best case in the set.** A1 satisfied
  six of seven and failed only **(7)** — the market noticed Cohen immediately
  (+23.9% on day 1) and the stock then went up **198% in 63 sessions and 21× in
  126**. Condition (7) would have vetoed the single largest winner available.
  **(7) is therefore a real bet, not a free filter**, and §4 must run the sweep
  **with and without it** as a declared SCREEN, never assume it.
- **This analogue set cannot test the hypothesis, by construction.** Cases are
  findable on the open web *because they moved*, and a case that moved fails
  (7) by definition. **The population §4 targets — an individual's >5% stake in
  a sub-$1B, 80%-drawn-down name that nobody wrote about — is invisible to web
  search and can only be enumerated from EDGAR.** That is the argument for
  building §4.6's collector, and simultaneously the argument for believing
  nothing until it exists.

### 2.4 The celebrity-SPAC lane is NOT this hypothesis, and must not be pooled with it

A parallel sweep of the obvious celebrity cases — Shaquille O'Neal, Alex
Rodriguez, Colin Kaepernick, Serena Williams, Ciara, Kevin Durant, Ken Griffey Jr.
— returned a structural result that is more useful than any return number:

> **EDGAR full-text search over `SC 13D` and `SC 13G` returns no filings naming
> any of them.** Their exposure ran through **Form 3/4 director status and
> sponsor LLCs**, where the 13G (if any) names the LLC, not the person. Several
> filed Form 3s reporting **zero securities owned** — A-Rod at Slam Corp,
> Kaepernick at Mission Advancement, Durant at Infinite Acquisition. Shaq's
> Forest Road role was "strategic advisor" with, per the S-1, no written
> agreement — **no filing of any kind**.

Two consequences, and the first is a scope ruling:

1. **The celebrity-SPAC lane is structurally non-analogous and is excluded from
   §2's base rate.** There is no disclosure event to measure against: the
   celebrity association was in the S-1 from the start, and pre-close prices are
   pegged to trust value. The losses in that lane are **sponsor economics and
   warrant expiry**, not a stake-disclosure pop that round-trips. Pooling them
   with A0–A5 would be measuring a different mechanism under the same name.
   *(The SEC published a **"Celebrity Involvement with SPACs" Investor Alert on
   2021-03-10** whose key line is: "It is never a good idea to invest in a SPAC
   just because someone famous sponsors or invests in it." Directionally
   supportive, about a different instrument.)*
2. **It is a hard power warning for §4.7.** Search the seven most famous
   celebrity investors of the last decade and the count of qualifying personal
   13D/13G filings is **zero**. Add the two we did find — Carter 2012 and
   Fischbach 2026 — and the *entire* known population of celebrity individual
   13Gs on distressed small-caps is **two filings in fourteen years**. If §4.7's
   count-first step returns a number of that order, the honest declaration is
   `NOT_ANSWERABLE_AT_N` and the lane closes before a return is computed. The
   escape hatch is **Control D** (§4.4): drop "famous" entirely and sweep *all*
   `IN` filers, which is a population orders of magnitude larger and a better
   hypothesis anyway.

**Base-rate verdict for §2:** on the media-visible population, the individual
stake disclosure delivers a **+14.7% median day-one pop that is gone by 63
sessions (median −4.1%, 4 of 6 negative, and −11.2% mean once the one outlier is
removed)**, with a **2-in-6 rate of the filer quietly exiting** and a **1-in-6
rate of the company going to zero**. The one case that structurally resembles
GPRO — Carter/Perfumania 2012 — **lost at every horizon**. And the famous-name
population barely exists in EDGAR at all. Nothing in that justifies a book. It
justifies exactly one thing: **build the sweep and look at the population nobody
wrote about.**

---

## §3. THE ENGINE'S CURRENT VIEW OF GPRO

**The situation has changed type.** Before 2026-09-01 GPRO was a
*distressed-equity-with-a-new-holder* question. Since 09:20 ET on 2026-09-01 it
is an **event/deal** question, and the only honest framework is merger
arithmetic: consideration, spread, conditions, financing, break price. The
holder story is now a historical fact about how the price got here, not an input
to the forward decision.

Clock note: as of writing (2026-09-02, ~00:40 ET) **the last completed session
is 2026-09-01**. Every number below is struck at that close, with the
$1.20 overnight ATS print noted where it changes the reading.

### 3.1 What a disciplined event-driven assessment requires

| Input | Status as of 2026-09-02 | Consequence |
|---|---|---|
| Per-share cash | **AMBIGUOUS.** "$285m, **or** $1.14/share" ⇒ 250.0m-share denominator; 184.5m are outstanding | Unresolvable. This is the trade, see §3.2 |
| Adjustment mechanism | Net-working-capital adjustment at closing, **uncapped and unquantified** | Cash leg is a *range*, not a number |
| Retained stub | "~10% of the outstanding shares" of the combined co | Unvalued — no Starman financials exist publicly |
| Termination fee | **NOT DISCLOSED** (merger agreement not filed) | Cannot price the downside protection |
| Outside date | **NOT DISCLOSED** | "By year-end 2026" is an expectation, not a covenant |
| Financing | **NOT DISCLOSED.** ~$377m cash need ($285m + $92m debt) by a private acquirer | The dominant close risk |
| Go-shop / no-shop | **NOT DISCLOSED** | Cannot price a topping bid |
| Voting / support agreements | **NOT DISCLOSED**; Woodman holds super-voting Class B | Vote outcome is probably not the binding risk, but this is unconfirmed |
| Regulatory | HSR presumed; the defense/aerospace framing raises a plausible **CFIUS/DoD** angle not addressed in the release | Unquantified timing risk |
| Fairness opinion | **Delivered** (Houlihan Lokey) | Weak positive: a board and a banker signed |
| Break price | Last undisturbed close **$0.600** (2026-08-28) | Arguably lower: $27.3m cash, $92m debt, units −38%, no guidance |

**Nine of thirteen inputs are unavailable.** A merger-arb position taken without
the merger agreement is not arbitrage; it is a directional bet with an
arbitrage-shaped story attached.

### 3.2 The spread, priced properly

Let `P` = price, `C` = cash per share at close, `S` = value of the retained ~10%
stub per share, `B` = break price. Implied close probability
`p = (P − B) / (C + S − B)`.

At **P = $1.23** and **B = $0.600**:

| Stub `S` | Case A: `C = $1.14` (250.0m denominator) | Case B: `C = $1.5447` (184.5m denominator) |
|---|---|---|
| $0.00 | **>100% — arithmetically impossible** | 66.7% |
| $0.10 | 98.4% | 60.3% |
| $0.20 | **85.1%** | 55.0% |
| $0.30 | 75.0% | 50.6% |
| $0.40 | 67.0% | 46.9% |

Read the first row of Case A carefully: **at $1.23 the stock trades 7.3% ABOVE
the stated cash consideration.** The price is only rational if the stub is worth
something material, or if the market is pricing a topping bid, or if the market
believes the 184.5m denominator.

Reward and risk under the most plausible reading (Case A, `S = $0.20`):

- **Upside if it closes:** $1.34 vs $1.23 = **+8.9%** over ~4 months
  (~28%/yr gross), **before** costs. At the house 25bps round trip, +8.4% net.
- **Downside if it breaks:** $0.60 vs $1.23 = **−51.2%**.
- **Reward : risk = 0.17.** Breakeven close probability **85.1%** — which is
  exactly where the market already is. There is **no edge in the spread itself.**

The only version with an attractive shape is Case B (+41.8% up, −51.2% down,
R:R 0.82), and Case B is **entirely a bet on the share-count denominator** — a
number that will be printed in a proxy statement within weeks and that we
cannot currently derive. Guessing it is not analysis.

**Worst case in dollars, per the session-start protocol.** At the tracker's
10% per-name notional, a break to $0.600 costs **−5.12% of equity on this one
name**. And **no stop survives it**: a merger break gaps overnight, and the
2026-09-01 tape already printed a **41% intraday range** ($1.16–$1.64). The
number to print here is the **modelled gap (−51%)**, not the stop
(cf. S30: report BOTH worst cases).

### 3.3 Verdict: NOT ACTIONABLE NOW. OBSERVE + BACKFILL.

**There is nothing actionable in GPRO today under paper-trading rules.** Five
independent reasons, any one of which is sufficient:

1. **The spread carries no edge.** Breakeven p = 85% is the market price. We
   have no differentiated view on the denominator, the financing, or a topping
   bid — and we would be pretending if we claimed one.
2. **Nine of thirteen deal inputs are undisclosed.** The merger agreement is not
   on file. `PRODUCT_EXPERIMENT` relaxes the significance gate; it does not
   relax "costs are never omitted" or the requirement that a frozen contract
   name its inputs. We cannot name them.
3. **Buying here is hindsight-chasing.** The +100% from 2026-08-20 was the
   attention repricing plus the deal. Paying for it after the fact is precisely
   what the house rule forbids.
4. **The worst case is a −51% modelled gap with no stop that binds.** Under any
   of the four personalities, an unstoppable −5.1%-of-equity tail for a +8.4%
   net upside fails the utility comparison. Name the objective: this fails under
   preservation, balanced, and aggressive; only "extreme growth" would look at
   it, and it still fails on reward:risk of 0.17.
5. **It is not in the universe.** Adding a single name reactively, on the day
   it is in the news, is exactly the ad-hoc universe mutation the invariants
   forbid. The fix is the collector (§4.6), not a manual add.

**What to do instead — OBSERVE, and backfill the missed-signal dataset.** This
is real work with a real deliverable, not a euphemism for doing nothing:

- **Record GPRO as a MISSED-SIGNAL case row**, typed `NOT_OBSERVED`, with the
  full §1 field set. This is row 1 of the dataset §4 needs.
- **Repair the collector that already exists** (§4.6b — found while writing this
  document). An **ACTIVE** `ACTIVIST_13D` copy-lab lane has been seeded since
  2026-08-14 and has seen **`events_considered: 0`** for its entire life, while
  its sibling on the same engine and the same run saw **92**. It is also
  13D-only, and its `min_price: 5.0` floor would have deleted GPRO regardless.
  This is the actual repair for the miss, it is free and PIT, and it is a live
  silent-fragility bug rather than new construction.
- **Track GPRO as an observation-only watchlist entry** with a
  `not_actionable_event_pending` flag, so the milestones below are graded
  prospectively rather than reconstructed later.

**Dated, falsifiable milestones to grade against** (each resolves one row of
the §3.1 table):

| Milestone | What it resolves | Expected |
|---|---|---|
| PREM14A / DEFM14A proxy, with merger agreement | Denominator, termination fee, outside date, no-shop, financing, voting agreements | ~30–60 days |
| 8-K Item 1.01 or 8-K/A filing the agreement | Same, sooner | Any day |
| Further 424B3 / Yorkville equity-line draws | **Directly moves the denominator** | Ongoing |
| HSR expiry; any CFIUS/DoD filing | Regulatory timing | 30–90 days |
| Fischbach 13G/A (2 bd on a ≥5% change; also on crossing 10%) or a switch to **13D** | Whether "passive" holds; whether he sells into the deal | Any day |
| Insider Form 4s | Alignment | Ongoing |
| Any competing proposal | Release risk factor (iii) explicitly contemplates it | Through close |

**Pre-committed re-entry condition, declared now, before the outcome exists:**
if the definitive proxy discloses (a) a **fixed** per-share cash number, (b) a
**financing commitment or escrow**, and (c) the stock then trades **≥12% below
the present value of the cash leg alone**, a `PRODUCT_EXPERIMENT` merger-arb
paper position is reconsidered at **≤5% notional**, with the modelled-gap worst
case printed in the decision doc. Absent all three, no.

**And the thing worth saying plainly:** the trade AEGIS missed was not this one.
It was **2026-08-20 to 2026-08-28 at $0.60–$0.615**, when a structured 13G by a
natural person sat on EDGAR beside a publicly announced late-stage sale process,
and the market moved **−1.6% on 1.03x volume.** That window is gone. Section 4
is about whether it recurs.

---

## §4. HOLDER-ATTENTION-1 — DRAFT TYPED HYPOTHESIS

**Status: DRAFT, NOT PRE-REGISTERED.** This becomes a trial only via
`.claude/skills/pre-register-trial`, after §4.6's data inventory exists and
after the §4.7 power count is run **mean-masked**. Licence sought:
`PRODUCT_EXPERIMENT`. **GPRO is the parent and is BARRED from every confirmation
slice** — the mechanism is tested on foreign slices with its parent excluded.

### 4.1 The question

> When a **natural person with no institutional history** discloses a **>5%
> passive stake** in a **deeply drawn-down small-cap**, and the market **does
> not react within five sessions**, is there a positive, cost-surviving,
> harvestable return over the following 21–63 sessions, *relative to the same
> disclosure made by an ordinary institution on a matched name in the same
> month*?

Note the shape. The hypothesis is **not** "famous person buys, stock goes up".
It is: *the market's ownership-monitoring pipeline is built for institutions,
and a person who is invisible to that pipeline produces a stale, unpriced,
freely observable fact.* The muted five-day reaction is not incidental — it is
the **evidence that the pipeline missed it**, and it is a required condition,
not a nice-to-have.

### 4.2 The precursor — executable, PIT, observable BEFOREHAND

Evaluated from the structured filing plus daily prices. Every field is known at
or before the decision timestamp. **Entry at the close of t+5**, which is the
first moment condition (7) is observable — no leakage.

Let t = 0 be the **filing date** (not the event date; the event date is not
public until the filing).

| # | Condition | Field / source | Known at |
|---|---|---|---|
| 1 | Filer is a **natural person** | **any** reporting person on the filing has `typeOfReportingPerson == "IN"` | t=0 |
| 2 | **No prior 13F record** for the filer CIK | EDGAR 13F filer index | t=0 |
| 3 | Stake **> 5%** of the class | `classPercent` | t=0 |
| 4 | Target **drawdown ≥ 80%** from its 5-year high | CRSP / price store | t=0 |
| 5 | Target **market cap < $1B** | shares out × price | t=0 |
| 6 | Dollar **ADV(20d) ≥ $1m** — declared tradeability floor | price store | t=0 |
| 7 | **Muted reaction**: \|ret(t=0 → t+5)\| ≤ 5% **and** volume(5d post) / volume(20d pre) ≤ 1.5× | price store | **t+5** |

GPRO scores: (1) `IN` ✔ · (2) no 13F ✔ · (3) 8.5% ✔ · (4) −99.4% ✔ ·
(5) $113.5m ✔ · (6) ~$4.0m/day ✔ · (7) −1.63% on 1.03× ✔ — **7/7**, with
every value taken from §1 and none of it requiring a news feed.

**The drawdown window is a real design decision and it flips this case.** From
the all-time high ($98.47, 2014-10-07) GPRO is **−99.4%** and clears the 80%
bar comfortably. From the **52-week** high ($3.05) it is **−79.8%** — and
**fails**. Condition (4) must name its lookback *before* the sweep runs, or the
lane will be tuned on this one name. Declared here: **5-year high**, chosen
because it is long enough to survive a multi-year decline and short enough that
a 2014 peak does not make every 2026 microcap "distressed". Any later change to
that window is an amendment, recorded as one. (Compare
[[feedback-a-filter-on-a-moving-quantity-deletes-the-tail]].)

Two implementation notes that §2.3 paid for, not guesses:

- **Condition (1) must be "any reporting person", not "the reporting person".**
  Joint filings by an individual alongside his own LLC (Cohen + RC Ventures)
  are the common form. Written naively, condition (1) silently drops the two
  largest analogues in §2.1.
- **Condition (7) is a BET, not a free filter.** In §2.3 it is the *only* thing
  that vetoes A1 (GME/Cohen 2020) — six of seven conditions satisfied, day-one
  +23.9%, then **+198% by D63 and +2,093% by D126**. Condition (7) therefore
  costs the single largest winner in the visible set. It is retained because the
  *mechanism* is "the pipeline missed it", and a +24% day-one move is proof the
  pipeline did not. But the sweep must be run **with and without (7)**, declared
  as a SCREEN cell before the run, and both reported. Assuming (7) is free is
  how a design gets tuned on one name.

**Three fields §2 proved we must record, none of them in the trigger:**
`shares_outright` separately from `classPercent` (A0's 11.4% was **84%
warrants**, and an option position is not a share position);
`filing_lag_days = filing_date − event_date` (three of three individual filers
were late — §1.1 — so the lag is a candidate feature, not trivia); and
`adv20_usd` in dollars, because A0 would have been unbuyable at **$0.24m/day**.

**Two conditioners that are NOT in the trigger and must be measured anyway**,
because §4.4 needs them as controls, not as filters: `short_interest_pct_float`
at t=0, and `pending_strategic_review` (has the target publicly announced a
sale/strategic-alternatives process in the prior 12 months?). GPRO: **16.46%**
and **YES (2026-05-11)**. If either turns out to be the real mechanism, the
lane is renamed, not defended.

**Objective and horizon.** Terminal wealth under the declared personality.
Primary readout is the **paired treated − control** return at **t+5 → t+26**
(21 sessions), with t+5 → t+68 (63 sessions) reported. Per S17/18: **rank on
terminal wealth, not the mean** — the mean-optimal concentration was a
0.1× terminal-wealth decision, and this population is more skewed than that one.

### 4.3 The falsifier — what would kill it

Five kill conditions, each with a named cut. Any of F1–F3 firing means the
mechanism is misnamed and the lane is retired or renamed; F4 or F5 firing means
it is real and unharvestable, which is the same thing as dead for a book.

- **F1 — the `IN` flag carries no information.** Individual-filer and
  institution-filer events, matched on drawdown / size / ADV / short-interest /
  month, have indistinguishable t+5 → t+26 returns. **Kill.**
- **F2 — it is short interest.** Adding `short_interest_pct_float` as a control
  removes the individual-filer coefficient. Then the mechanism is *squeeze
  mechanics*, the 13G is a float shock, and the lane is renamed
  `FLOAT-SHOCK-1`. **This is the most likely single explanation** given GPRO's
  16.46% and the fact that Fischbach's 13.5m shares are 54% of the short
  interest. **Run this cut FIRST.**
- **F3 — it is the pending M&A catalyst.** Restricted to targets with **no**
  publicly announced strategic review at t=0, the effect vanishes. Then the
  filer is decoration and the real signal is "distressed name in a public sale
  process". **Run this cut SECOND** — it is the GPRO-specific confound and §1.3
  says it is live.
- **F4 — the tail is the result and we cannot pre-identify it.** The positive
  mean is carried by <5% of events (a media-coverage lottery) and the **median
  is ≤ 0**. Report the median and the top-5%-excluded mean *beside* every mean,
  always ([[feedback-check-the-tail-before-the-mean]]: 35 rows of 46,361 once
  carried 81% of a result here). **Kill for a book**, keep as a study.
- **F5 — costs eat it.** The effect is smaller than the round-trip quoted spread
  in the band where it lives. Sub-$1, sub-$1B names have wide spreads. **Quote
  the cost rate or don't quote the count.** Kill.
- **F6 — the filer's return is not the follower's return.** §2.2 measured a
  **2-in-6 full-exit rate**, disclosed only afterwards, and in the worst case
  (BBBY) the filer booked ~+$59m while the follower who held went to **−99.5%**
  and then to zero. If the treated−control advantage disappears once the sample
  is extended past the filer's own (later-disclosed) exit, then the mechanism is
  *front-running a person who will front-run you*, and a 21–63 session hold does
  not capture it. **Test:** grade every treated event to 252 sessions and
  separately from the exit-disclosure date. A positive D63 with a negative D252
  is not a book; it is a trade with a fuse, and the fuse length is unobservable
  at entry. **Kill for a hold; keep only if a declared exit rule exists.**

### 4.4 The matched-control design

For each treated event, draw up to **3 controls** from **SC 13G filings in the
same calendar month by ordinary institutions** (`typeOfReportingPerson` in
{`HC`,`IA`,`IV`,`FI`,`BD`,`CO`,`PN`,`EP`,`SC`}), nearest-neighbour matched on:

- drawdown-from-5y-high decile (±1)
- market-cap decile (±1)
- dollar-ADV decile (±1)
- short-interest-%-of-float tercile
- **same calendar month** (the date block)

Sampled without replacement. Deciding number is the **paired difference**
(treated − matched control). Inference by **date-block bootstrap on MONTH
blocks** — `n_effective` counts date blocks, never rows (canon §58). A file of
40,000 filings spanning eleven calendar quarters has an `n_effective` of eleven,
not 40,000 ([[feedback-count-the-days-before-reading-the-columns]]).

**Two controls we would not have chosen, and therefore must run**
([[feedback-run-the-control-you-would-not-have-chosen]] — this has now cost us
twice in one day, once on 13F and once on the +400% band):

- **Control C — individual `IN` filers on NON-distressed targets**
  (drawdown < 40%). If those work too, the drawdown conjunction is decoration
  and condition (4) is deleted.
- **Control D — ALL `IN` filers, unfiltered by recognisability.** This is the
  honest null and the one that most threatens the romantic story. If ordinary,
  unknown individuals' 13Gs perform just as well, then "creator reach" is not
  the mechanism, and the real hypothesis is the **larger and better** one:
  *insider-adjacent individual accumulation is unpriced*. Either answer is a
  win; only never running it is a loss.

**On "fame".** Recognisability is **not machine-readable from EDGAR** and must
never be hand-coded after returns are seen — that is the single easiest way to
manufacture this result. Two admissible PIT proxies, and they are declared
ex-ante or fame is dropped from the design entirely:

1. Wikipedia article existence + trailing-30-day pageviews for the filer name,
   as of the **month before** filing (Wikimedia REST API; free; dated dumps ⇒
   genuinely PIT).
2. Count of pre-filing news items naming the filer, from a dated corpus.

Both are noisy. Both are honest. Neither is "I recognised the name".

### 4.5 The GPRO instance, scored honestly

Recorded so the case cannot later be quietly reinterpreted:

| Element | GPRO value | Verdict |
|---|---|---|
| Precursor 1–7 | 7/7 | Fires |
| Return t+5 → t+8 (truncated by the deal) | $0.605 → $1.23 = **+103.3%** | Spectacular and **uninformative at n=1** |
| F2 exposure (short interest) | 16.46% of float; stake = 54% of SI | **HIGH** — cannot separate |
| F3 exposure (pending M&A) | Sale process public since 2026-05-11, "later stages" 2026-08-11 | **HIGH** — cannot separate |
| F4 exposure (media lottery) | Move triggered by one Bloomberg newsletter, 2026-08-30 22:15 UTC | **HIGH** — cannot separate |
| Attributable to the holder? | **UNDETERMINED, and probably mostly not** | See §1.3 |

n = 1, three uncontrolled confounds, and the parent is barred from confirmation.
**GPRO generated the hypothesis. It cannot support it.**

### 4.6 Data needed — all free, all PIT

| # | Dataset | Source | Cost | Notes |
|---|---|---|---|---|
| 1 | All SC 13D / SC 13G filings + amendments, 1994→present, with **filing date** | EDGAR quarterly `full-index/form.idx` | free | Filing date is the PIT timestamp |
| 2 | **Structured 13D/13G XML** (`typeOfReportingPerson`, `classPercent`, `eventDateRequiresFilingThisStatement`) | `.../primary_doc.xml` | free | Schema era only |
| 3 | Pre-schema cover-page parse: "TYPE OF REPORTING PERSON", percent of class, date of event, **and Item 4(a)'s share/warrant breakdown** | filing text | free | Small closed vocabulary; mechanical. A0 (2012) parsed cleanly by hand, so the era is reachable |
| 4 | 13F filer index (for "no prior 13F record") | EDGAR | free | |
| 5 | Daily prices / volume / shares out | CRSP 1993–2024 (held) + live store for 2025–26 | held | The 2025–26 gap is real; fill it or the recent era is unusable |
| 6 | Short interest, bi-monthly | FINRA / Nasdaq / exchange files | free | Required for F2 |
| 7 | `pending_strategic_review` flag | 8-K + press-release text search, 12m lookback | free | Required for F3 |
| 8 | Fame proxy (optional, declared ex-ante) | Wikimedia REST pageviews | free | Or dropped |

**A coverage break that must not be pooled silently.** The structured schema
(dataset 2) begins with the 2024 amendments; the clean structured era is roughly
**two years long**, and the parsed era (dataset 3) is thirty. Report the two
eras **separately** and declare the pooling rule before looking. A `column` is
not `data` [[reference-crsp-replayable-window]], and an era break silently
pooled is how a 267,802-row scoreboard turned out to span two calendar days.

### 4.6b THE COLLECTOR PARTLY EXISTS — AND IT IS SILENT

This was found while writing §4.6 and it changes the work item from "build a
13D/13G collector" to "repair one that is already seeded and empty."

`backend/data/copy_lab/copy_lab_lanes_v1.yaml` defines an **ACTIVE** lane
**`ACTIVIST_13D`** — `source: sec_13d`, `PRODUCT_EXPERIMENT`, paper only,
seeded **2026-08-14**, `holding_days: 252`, entry at `public_at` filled at the
next session's open. It is a real, config-hashed, running paper lane. Three
things are wrong with it for our purposes, and the second is a live bug:

**1. It is 13D-only, by design.** Its own thesis reads:

> "A >5% crossing with **declared control intent**. **Economically different
> from passive ownership** …"

Fischbach filed a **13G** under Rule 13d-1(c) with the explicit non-control
certification. **The lane's stated thesis excludes the exact event this case is
about.** HOLDER-ATTENTION-1 is precisely the claim that "passive vs activist" is
the wrong cut for one subclass of filer, and that **`typeOfReportingPerson`, not
the form number, is the informative field.** That is the lane's own assumption
under test, and it is a good thing that it is written down.

**2. `events_considered: 0` — for its entire life.** The two receipts on disk
(`run_20260814T124650Z` and `run_20260827T195120Z`) and all 10 NAV rows show the
lane flat at **$100,000.00, zero positions, zero fills**. Compare its sibling on
**the same engine, the same run, the same second**:

| Lane | source | `events_considered` | `signals_new` | fills |
|---|---|---|---|---|
| `CORPORATE_INSIDER_CLUSTER` | `sec_form4` | **92** | 9 | 0 (all pre-inception, correctly refused) |
| **`ACTIVIST_13D`** | `sec_13d` | **0** | 0 | 0 |

The Form 4 adapter saw 92 events and refused 9 for a stated, correct reason.
The 13D adapter saw **nothing at all**, over 13 calendar days in which EDGAR
received many SC 13D filings. `ineligible_reasons` is `{}` — **not "refused",
but "never presented"**. That is the house's own signature failure mode: *code
that runs green and silently does nothing.* Silence is not evidence
[[feedback-silence-is-not-evidence]]; a refusal is a finding and an empty dict
is not a refusal. **Cheapest possible check: assert `events_considered > 0` for
any active lane over any 10-session window, or emit `CANNOT DETERMINE`.**
Run `silent-fragility-audit` on `services/copy_lab` + the `sec_13d` adapter.

*(Also: the newest receipt is `run_at 2026-08-27T19:51:20Z`. As of 2026-09-02
neither lane has run for six days. Whether that is intended is a separate
question, but a flat NAV is currently indistinguishable from a stopped loop.)*

**3. Its own filters would have deleted GPRO even if the event had arrived.**
The lane defaults are `min_price: 5.0` and `min_dollar_volume_20d: 5,000,000`.
GPRO on 2026-08-20 was **$0.615** and **~$4.0m/day**. It fails **both**. And per
[[feedback-test-reachability-not-stage-correctness]], a threshold like that
does not mark a name unbuyable — **it deletes it, so we never form an opinion at
all.** A `min_price: 5.0` filter is, in effect, a rule that *this lane may never
observe a distressed micro-cap* — which is the entire population §4 targets.

**So the §3.3 work item is now specific, cheap, and testable:**

1. Fix or replace the `sec_13d` adapter so `events_considered > 0`; add the
   assertion above so it can never be silently zero again.
2. Extend it to **SC 13G**, carrying `typeOfReportingPerson`, `classPercent`,
   `eventDateRequiresFilingThisStatement` and the filing lag through to the
   event record. Nothing downstream can test §4 without those fields.
3. Do **not** loosen `ACTIVIST_13D`'s `min_price` / `min_dollar_volume_20d` —
   that lane's contract is frozen and it is measuring something else. §4 arrives
   as its **own** book with its own declared floors (§4.2 condition 6), per
   THE BOTTLENECK.
4. Enrol the new module in `signal_reachability` so an unreachable collector is
   a red suite, not a discovery three weeks later.

### 4.7 Power, before anything is run (canon §64)

The binding constraint is the count of treated events, and **we do not know it
yet**. The order is fixed and it is not negotiable:

1. **COUNT FIRST.** Enumerate SC 13G/13D with `typeOfReportingPerson == IN`
   per year; then apply conditions 2–6; then report `n_treated` and
   `n_effective` (month blocks).
2. **MDE SECOND**, mean-masked, on the exact primary.
3. **DECLARE THIRD** which verdicts are ANSWERABLE_AT_N and which are
   NOT_ANSWERABLE_AT_N — *before* a single return is seen.

If the conjunction leaves low-hundreds of events per decade, the honest
prospective declaration may be `NOT_ANSWERABLE_AT_N` for everything but a large
effect. That is a finding, declared in advance, not a disappointment discovered
afterwards. **The bar never shrinks.**

**There is already a rarity warning on the table, and it is severe.** §2.3
assembled six individual-filer stake disclosures spanning 2012–2024 and the
precursor fired on **none of them**. Worse, §2.4 found that EDGAR full-text
search returns **zero** SC 13D/13G filings naming any of the seven most famous
celebrity investors of the last decade — their exposure was all Form 3/4 and
sponsor LLCs, several reporting **zero shares owned**. The entire known
population of celebrity individual 13Gs on distressed small-caps is **two
filings in fourteen years** (Carter 2012, Fischbach 2026). If step 1 returns a
number of that order, the lane closes on `NOT_ANSWERABLE_AT_N` — and the
survivable version is **Control D**, all `IN` filers with fame dropped. That is partly correct behaviour (the conjunction is
supposed to exclude a $31bn company) and partly a **selection artefact**: cases
are web-findable *because* they moved, and a case that moved fails condition (7)
by construction. Either way it means the target population is **rare and
unobserved**, and step 1 above is not a formality — it is the step most likely
to end this lane before a single return is computed.

### 4.8 Verdicts, committed in advance

- **HOLDER_ATTENTION_REAL** — paired treated−control ≥ the economic bar, and
  surviving F2, F3, F4 and F5.
- **CONTROL_NONINFERIOR** — the individual-filer advantage is bounded below the
  bar (one-sided).
- **NOT_ESTABLISHED**.

Economic bar declared at signature; it must **exceed the round-trip quoted
spread** in the sub-$1B, sub-$5m/day band, which is not a small number.
Renaming outcomes are separate and explicit: F2 firing ⇒ `FLOAT-SHOCK-1`;
F3 firing ⇒ `PENDING-SALE-1`; Control D winning ⇒ `INDIVIDUAL-ACCUMULATION-1`.
Per **EXPLORE DIRTY, PROMOTE CLEAN**, a failure here is
`FAILED_VARIANT` / `DEPRIORITIZED` — **`MECHANISM_REJECTED` is not available**
to a single implementation of a single conjunction.

### 4.9 What this hypothesis is NOT

- **NOT "down 99% is a signal."** A stock down 99% can fall 99% again. Condition
  (4) is a **conditioner on a conjunction**, never a trigger. If §4 is ever cited
  as licence for a drawdown screen, it has been misread.
- **NOT "a famous person bought it, so buy it."** n=1, three uncontrolled
  confounds, and the parent barred.
- **NOT a claim about GPRO.** §3 says GPRO is not actionable and this section
  does not reopen it.
- **NOT a weight in `arena_composite`.** Per THE BOTTLENECK: if it survives, it
  arrives as its **own** `PRODUCT_EXPERIMENT` book. Folding it into the
  composite would hide the only thing being tested — whether its errors are
  *different* errors.

---

## §5. SOURCES AND RECEIPTS

Every headline number in this document traces to one of these. Primary
documents first; press is used only where no filing exists.

**SEC EDGAR primary documents (all retrieved 2026-09-02)**

| Document | Accession | Date | Used for |
|---|---|---|---|
| GoPro SC 13G (Fischbach) — [`primary_doc.xml`](https://www.sec.gov/Archives/edgar/data/1500435/000163075926000003/primary_doc.xml) | 0001630759-26-000003 | 2026-08-20 | Every field in §1.1 |
| GoPro 8-K (Item 8.01) — [`gpro-20260901.htm`](https://www.sec.gov/Archives/edgar/data/1500435/000162828026059839/gpro-20260901.htm) | 0001628280-26-059839 | 2026-09-01 | Structure; Parent = Action Acquisitions LLC; exhibit list (gap 1) |
| GoPro Ex-99.1 press release — [`gpro2026-09x01exhibit991.htm`](https://www.sec.gov/Archives/edgar/data/1500435/000162828026059839/gpro2026-09x01exhibit991.htm) | 0001628280-26-059839 | 2026-09-01 09:20 ET | All deal terms in §1.4 |
| GoPro DEFA14A (employee / partner emails) | 0001628280-26-059846 | 2026-09-01 | Merger agreement dated 2026-09-01; Woodman "the strategic review process we announced in May" |
| GoPro 10-Q Q2 2026 — cover page XBRL | 0001500435-26-000036 | 2026-08-10 | 158,245,863 Class A + 26,258,546 Class B @ 2026-08-07; $27.3m cash; $34.7m derivative liabilities |
| GoPro 424B3 (Yorkville) prospectus supplements | 0001628280-26-055366 / -059917 / -059918 | 2026-08-10, 2026-09-01 | Live equity line ⇒ the denominator is moving |
| GoPro 8-K (Item 5.02, CFO promotion) | 0001628280-26-057639 | 2026-08-18 | Filing-index completeness check |

**Local data receipts**

| Number | Source |
|---|---|
| GPRO daily closes/volumes 2026-08-14 → 2026-09-01 | Yahoo Finance GPRO history (CRSP ends 2024) |
| GPRO quote, market cap $226.94m, 52w $0.57–$3.05, overnight $1.20 | Yahoo Finance GPRO, 2026-09-01 16:00:01 ET close / 2026-09-02 00:23 ET ATS |
| **All analogue returns (§2.1)** | `backend/data/optimus/wrds/crsp_dsf_{2016..2024}.parquet`, split-adjusted via `cfacpr`; permnos resolved from `backend/data/optimus/crsp_pit/crsp_pit_monthly_v1.parquet` (GME 89301, BBBY 77659, TWTR 14295, CHWY 18727, GPRO 14694) |
| Spread / implied-probability tables (§3.2) | Computed from the §1.4 terms and the 2026-09-01 close; arithmetic reproducible from `P=1.23, B=0.60, C∈{1.14, 285e6/184504409}` |
| **§4.6b silent-lane finding** | `backend/data/copy_lab/copy_lab_lanes_v1.yaml` (lane defs, `min_price: 5.0`, `min_dollar_volume_20d: 5e6`); `backend/data/optimus/copy_lab/ACTIVIST_13D/receipts/run_20260814T124650+0000.json` and `run_20260827T195120+0000.json` (`events_considered: 0`, `ineligible_reasons: {}`); `.../CORPORATE_INSIDER_CLUSTER/receipts/run_20260827T195120+0000.json` (`events_considered: 92`); both `nav.jsonl` files (10 rows, NAV flat $100,000.00) |

**Analogue primary documents (retrieved 2026-09-02)**

| Document | Accession | Date | Used for |
|---|---|---|---|
| [Shawn Corey Carter SC 13G on Perfumania Holdings](https://www.sec.gov/Archives/edgar/data/880460/000154921112000003/scc13g.txt) | 0001549211-12-000003 | filed 2012-05-04, event 2012-04-18 | A0: `TYPE OF REPORTING PERSON: IN`, 1,919,784 sh = 11.4% of 15,285,046, **300,000 shares + warrants on 1,619,784**, Item 10 non-control certification, c/o S. Carter Enterprises LLC |
| Perfumania Holdings EDGAR filing index (CIK 880460) | — | — | Confirms the 13G filing date and the 2014-02-28 SC 13G/A |
| Ryan Cohen / RC Ventures SC 13D on GameStop | 0001013594-20-000670 | 2020-08-31 | A1 |

**Press and third-party, with dates**

- [Bloomberg, 2026-08-30 22:15 UTC](https://www.bloomberg.com/news/newsletters/2026-08-30/youtube-star-markiplier-is-now-gopro-s-largest-shareholder) — the story that moved the stock; establishes the seven-session window
- [GoPro IR, 2026-05-11](https://investor.gopro.com/press-releases/press-release-details/2026/GoPro-Board-of-Directors-Announces-Review-of-Strategic-Alternatives/default.aspx) — strategic alternatives review announced
- [GoPro IR, 2026-05-13](https://investor.gopro.com/press-releases/press-release-details/2026/GoPro-Retains-Investment-Bank-Houlihan-Lokey-to-Pursue-Strategic-Alternatives/default.aspx) — Houlihan Lokey retained
- [CineD, 2026-08-11](https://www.cined.com/gopro-says-its-sale-process-is-in-the-later-stages-camera-sales-fall-38-cash-down-to-27-million/) — Q2 numbers; "later stages"
- [TechCrunch, 2026-09-01 08:57 PDT](https://techcrunch.com/2026/09/01/gopro-to-be-acquired-for-285m-will-remain-a-public-company/) — deal summary
- Benzinga / Fintel, 2026-09-01 — GPRO short interest 24.88m shares, 16.46% of float at the 2026-08-14 settlement, days-to-cover 3.3
- [Skadden, 2024-09](https://www.skadden.com/insights/publications/2024/09/new-schedule-13g-accelerated-filing-deadlines) — Rule 13d-1(c) five-business-day deadline effective 2024-09-30
- [Brav, Jiang, Partnoy & Thomas, *Hedge Fund Activism, Corporate Governance, and Firm Performance*, J. Finance 2008](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=948907) — the ~+7% activist-13D baseline
- CNBC, 2022-08-17 / 2022-08-18 — Cohen's BBBY exit and the −40.5% session
- CNBC, 2024-07-01 — Gill's CHWY 13G, +20% premarket → −6.6% close
- Variety / SEC complaint coverage, 2025-01 — SEC v. Musk over the late Twitter 13G; alleged ≥$150m of harm to selling holders
- [SEC OIEA Investor Alert, 2021-03-10](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/celebrity-involvement-spacs-investor-alert) — "Celebrity Involvement with SPACs": *"It is never a good idea to invest in a SPAC just because someone famous sponsors or invests in it."* Cited in §2.4 as directionally supportive about a **different instrument**
- EDGAR full-text search (`efts.sec.gov`, `forms=SC 13D,SC 13G`) over O'Neal, Rodriguez, Kaepernick, S. Williams, Wilson, Durant, Griffey — **zero hits**; the §2.4 structural finding

**What is explicitly NOT VERIFIED in this document**

1. The **denominator** behind "$285m, or $1.14 per share". Unresolvable from
   public filings as of 2026-09-02.
2. Whether the 13G was legally late. The **lag is a fact** (event 2026-07-13,
   filed 2026-08-20); the **conclusion** is flagged as apparent.
3. A5's stake percentage as filed (GME / Gill 2024).
4. Starman Optical's financials, ownership and financing capacity. No public
   record exists.
5. Any 2025–2026 analogue returns — our CRSP file ends in 2024, and the gap
   must be filled before §4 can be run on the recent era.
6. Perfumania's terminal outcome. CRSP coverage of PERF ends 2017-08 and the
   monthly PIT panel's last row is 2017-08-31, which is consistent with a
   delisting; the **restructuring is not confirmed from a primary source here**,
   and the A0 row says only what the data shows. D252 (−30.3%) is measured; the
   ending is not.
7. The celebrity-SPAC return figures reported by the parallel sweep (Beachbody,
   Velo3D, Slam Corp, etc.). §2.4 uses only that sweep's **structural** finding
   — that no personal 13D/13G exists — which was independently checkable. Its
   percentage returns are **not restated here** and were not verified against
   CRSP; one of its tickers (VELO) resolves in our own PIT panel to a different
   issuer than the one described, which is reason enough not to quote them.
