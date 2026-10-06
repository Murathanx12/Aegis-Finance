"""Stock lists v3.x (2026-09-27) builder: fills `doc` and `stats` for scripts/stock_lists_pdf.py.

Render (offline, $0):
    python -m scripts.stock_lists_pdf --parts scripts/stock_lists_v3_build.py         --pdf C:/Users/mrthn/Downloads/AEGIS_stock_lists_2026-09-27_v3.pdf         --md docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md --title "AEGIS stock lists v3.2 2026-09-27"

Inputs it needs beside the repo's own ledgers (built by scripts/stock_lists_v3_inputs.py into WORK):
    WORK/v3_facts.json        sigma63 / predicted move / fundamentals proxy / EDGAR earnings estimate per name
    WORK/yf_analyst_v3.json   yfinance analyst count + strong-buy/buy/hold/sell mix per name
WORK = backend/data/optimus/stock_lists/<ASOF>/ (override with STOCK_LISTS_WORK).
For v4: copy this file, change ASOF / SHORT / the prose, rebuild the inputs, render.
"""
import json, glob, re, math, sys, os
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd, numpy as np, yaml

REPO = Path(r"C:\Users\mrthn\aegis-finance")
SCR = Path(os.environ.get("STOCK_LISTS_WORK") or (REPO / "backend/data/optimus/stock_lists" / "2026-09-27"))
ASOF = "2026-09-27"
OPT = REPO / "backend/data/optimus"
P_V2 = REPO / "docs/research_notes/2026-09-26/stock_lists_2026-09-26.md"
P_NOTE = REPO / "docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md"
SHORT = ("VRT,GEV,MU,TSM,HOOD,NVT,AVGO,CLS,BE,MP,VRTX,NOVT,WST,COGT,VKTX,DKNG,LEU,CCJ,AGIO,IONQ,RGEN,BBIO,PRAX,"
         "NVEC,MAN,RHI,ACI,PEGA,IRDM,HELE,SMPL,PRGS,AGYS,QUBT,AARD,BHVN,SLDP,AAPL,AMGN,BA,BN,BSP,CRM,HWM,LNG,NOW,"
         "NVO,PSNL,SNOW,TEM,VG,WDAY,NVDA,INCY,SNDR,META,AVPT,AMZN,GOOGL,JAZZ,"
         "ABSI,HUBS,KYTX,NTLA,PRCH,SOC,AMSC,ENS,TER").split(",")
SHORT_SRC = {}
for grp, names in [("v2 book", "VRT,GEV,MU,TSM,HOOD,NVT,AVGO,CLS,BE,MP,VRTX,NOVT,WST,COGT,VKTX,DKNG,LEU,CCJ,AGIO,IONQ,RGEN,BBIO,PRAX"),
                   ("rehearsal", "NVEC,MAN,RHI,ACI,PEGA,IRDM,HELE,SMPL,PRGS,AGYS"),
                   ("Murat", "DKNG,QUBT,AARD,BHVN,SLDP"),
                   ("DJ forecast", "AAPL,AMGN,BA,BN,BSP,CRM,HWM,LEU,LNG,NOW,NVO,PSNL,SNOW,TEM,VG,WDAY"),
                   ("PROBE", "NVDA,INCY,AAPL,SNDR,META,AVPT,AMZN,GOOGL,JAZZ"),
                   ("Murat (other)", "ABSI,HUBS,KYTX,NTLA,PRCH,SOC,AMSC"),
                   ("v1 book", "ENS,TER")]:
    for t in names.split(","):
        SHORT_SRC.setdefault(t, []).append(grp)


def trunc(s, n):
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def isnum(x):
    return x is not None and not (isinstance(x, float) and not np.isfinite(x))


def pct(x, d=0):
    return f"{x*100:.{d}f}%" if isnum(x) else ""


def num(x, d=2):
    return f"{x:,.{d}f}" if isnum(x) else ""


doc, stats = [], {}
def H(level, t): doc.append((f"h{level}", t))
def P(t): doc.append(("p", t))
def T(headers, rows, widths, compact=False): doc.append(("table", (headers, rows, widths, compact)))
def PB(): doc.append(("pb", None))


# ───────── inputs ─────────
FACTS = json.load(open(SCR / "v3_facts.json"))
F = FACTS["names"]
recs = [json.loads(l) for l in open(OPT / "llm_portfolio/books.jsonl", encoding="utf-8") if l.strip()]
voids = {r.get("book_id") for r in recs if r.get("kind") == "void"} | {r.get("voided_book_id") for r in recs if r.get("kind") == "void"}
books = {r["name"]: r for r in recs if r.get("kind") not in ("twin", "void")}
twins_of = defaultdict(list)
for r in recs:
    if r.get("kind") == "twin":
        twins_of[r.get("parent_book_id")].append(r)
ROI = json.load(open(OPT / "paper_accounts/roi_2026-09-27.json"))
roi_by = {r["account"]: r for r in ROI["rows"]}


REFUSED_CARDS = {}


def load_cards(day):
    out = {}
    for f in sorted(glob.glob(str(OPT / f"thesis_cards/{day}/*.json"))):
        if Path(f).name.startswith("_"):
            continue
        c = json.load(open(f, encoding="utf-8"))
        if not isinstance(c, dict) or "ticker" not in c:
            continue
        if str(c.get("verdict", "")).startswith("REFUSED"):
            if day == ASOF:
                REFUSED_CARDS[c["ticker"]] = c.get("verdict")
            continue
        out[c["ticker"]] = c
    return out


C3 = load_cards(ASOF)
C25 = load_cards("2026-09-25")
C26 = load_cards("2026-09-26")
CARD_RECEIPT = {}
try:
    CARD_RECEIPT = json.load(open(OPT / f"thesis_cards/{ASOF}/_run_receipt.json"))
except Exception:
    pass

snap = pd.read_parquet(OPT / "analyst/target_snapshots.parquet")
snap["d"] = snap["observed_at"].astype(str).str[:10]
L = snap.sort_values("observed_at").groupby("ticker").tail(1).set_index("ticker")
YF = json.load(open(SCR / "yf_analyst_v3.json")) if (SCR / "yf_analyst_v3.json").exists() else {}
MW = {}
for l in open(OPT / "news_corpus/dowjones/_structured/mw_analyst_snapshot.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); MW[r["ticker"]] = r


def recmix(t):
    y = YF.get(t) or {}
    c = y.get("counts") or {}
    if not c and y.get("n") is None:
        return "", None
    s = (f"SB {c.get('strongBuy', 0)} / B {c.get('buy', 0)} / H {c.get('hold', 0)} / S {c.get('sell', 0) + c.get('strongSell', 0)}"
         if c else "") + (f" ({y.get('key')})" if y.get("key") else "")
    return s.strip(), y.get("n")


# the dated next event per card
def card_next_event(c):
    if not c:
        return ""
    best = None
    for u in c.get("upcoming_dates") or []:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(u))
        if m and m.group(1) >= ASOF:
            if best is None or m.group(1) < best[0]:
                best = (m.group(1), u)
    if best:
        parts = [p.strip() for p in best[1].split("|")]
        return trunc(" | ".join(parts[:3]), 110)
    ud = c.get("upcoming_dates") or []
    return trunc(ud[0], 110) if ud else ""


def next_event_date(t):
    """next earnings print, by source priority: the card's dated 'earnings' row (v3, else the previous card),
    then the EDGAR 2.02 + 91d estimate, then the MarketWatch snapshot."""
    c = C3.get(t) or C25.get(t) or C26.get(t)
    ds = []
    for u in (c or {}).get("upcoming_dates") or []:
        parts = [p.strip() for p in str(u).split("|")]
        m = re.match(r"(\d{4}-\d{2}-\d{2})", parts[0])
        if m and len(parts) > 1 and "earn" in parts[1].lower() and m.group(1) >= ASOF:
            ds.append(m.group(1))
    if ds:
        return (min(ds), "card")
    f = F.get(t) or {}
    if f.get("earn_status") == "IN_WINDOW" and f.get("earn_est"):
        return (f["earn_est"], "EDGAR+91d")
    mw = MW.get(t)
    if mw and mw.get("next_earnings_date"):
        try:
            d = str(pd.Timestamp(mw["next_earnings_date"]).date())
            if d >= ASOF:
                return (d, "MW")
        except Exception:
            pass
    return None


SESS5_END = str(pd.bdate_range("2026-09-28", periods=5)[-1].date())   # 2026-10-02


# research note (optional)
NOTE = P_NOTE.read_text(encoding="utf-8") if P_NOTE.exists() else None
stats["note_present"] = NOTE is not None


# ════════════════════ research note ════════════════════

# Parse the Sonnet research note (docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md) when present.
NOTE_TABLES, NOTE_TOP, NOTE_DROP, NOTE_NEW, NOTE_CROWD, NOTE_VETO = [], {}, {}, {}, set(), {}


def _clean(s):
    return re.sub(r"\*\*|`", "", s).strip()


def _section(lines, start_pat, end_pat):
    out, on = [], False
    for ln in lines:
        if re.match(start_pat, ln):
            on = True
            continue
        if on and re.match(end_pat, ln):
            break
        if on:
            out.append(ln)
    return out


def _bullets(sec):
    items, cur = [], None
    for ln in sec:
        if ln.startswith("- "):
            if cur:
                items.append(cur)
            cur = ln[2:].strip()
        elif cur is not None and ln.startswith("  "):
            cur += " " + ln.strip()
    if cur:
        items.append(cur)
    rows = []
    for it in items:
        m = re.match(r"\*\*([^*]+)\*\*\s*(?:\(([^)]*)\))?\s*[—:-]+\s*(.*)", it)
        if m:
            rows.append([_clean(m.group(1)), trunc(_clean((("(" + m.group(2) + ") ") if m.group(2) else "") + m.group(3)), 330)])
        else:
            rows.append(["", trunc(_clean(it), 330)])
    return rows


if NOTE:
    _ln = NOTE.splitlines()
    secA = _section(_ln, r"^# \(A\)", r"^# \(B\)")
    tab = [ln for ln in secA if ln.startswith("|")]
    if tab:
        hdr = [_clean(x) for x in tab[0].strip().strip("|").split("|")]
        body = []
        for ln in tab[2:]:
            cells = [_clean(x) for x in ln.strip().strip("|").split("|")]
            body.append([trunc(c, 200) for c in cells])
            try:
                NOTE_TOP[cells[1]] = int(cells[0])
            except Exception:
                pass
        NOTE_TABLES.append(("(A) The note's ROI-maxing top 15 (its own ranking: mechanism + falsifier; every crowd flag reads 'n/a - not checked')", (hdr, body)))
    after = [ln for ln in secA if ln.startswith("**Just outside")]
    for r in _bullets(_section(_ln, r"^# \(B\)", r"^# \(C\)")):
        NOTE_DROP[r[0]] = r[1]
    NOTE_TABLES.append(("(B) Names the note drops or trims from v2", (["Ticker", "Reason (the note's words, trimmed)"], [[k, v] for k, v in NOTE_DROP.items()])))
    for r in _bullets(_section(_ln, r"^# \(C\)", r"^# \(D\)")):
        NOTE_NEW[r[0]] = r[1]
    NOTE_TABLES.append(("(C) New candidates the note found", (["Ticker", "Why / source (the note's words, trimmed)"], [[k, v] for k, v in NOTE_NEW.items()])))
    dch = _bullets(_section(_ln, r"^# \(D\)", r"^---|^## Appendix"))
    NOTE_TABLES.append(("(D) What the note found changed since 2026-09-26", (["Item", "Change (the note's words, trimmed)"], dch)))
    # crowd flags: the note's only clean, dated crowd reads are NVEC (thin, no pump), DKNG (bullish retail narrative,
    # older WSB hype) and QUBT (essentially no substantive discussion). DKNG is the one read as retail-crowded.
    NOTE_CROWD = {"DKNG"}
    # the note's explicit exclusions: a Tier-1 profile whose "ROI read" says Exclude / Excluded
    for _sec in re.split(r"\n### ", NOTE)[1:]:
        _tk = _sec.split()[0]
        _m = re.search(r"\*\*ROI read:\*\*(.*)", _sec)
        if _m and re.search(r"exclud", _m.group(1), re.I):
            NOTE_VETO[_tk] = trunc(_clean(_m.group(1)), 260)
stats["note_top15"] = list(NOTE_TOP)
stats["note_drops"] = list(NOTE_DROP)
stats["note_veto"] = list(NOTE_VETO)


# ════════════════════ part2_books.py ════════════════════


# ═════════ 0. COVER ═════════
H(1, "AEGIS - stock lists v3.2, 2026-09-27")
P("Prepared 2026-09-27 (HKT) for Murat from the Aegis-Finance repo. v2 was 2026-09-26 (`docs/research_notes/2026-09-26/stock_lists_2026-09-26.md`). "
  "Every table is parsed from a named file; the Appendix lists every path and run id. The only LLM spend behind this document is the thesis-card run of section 2 (Appendix). "
  "<b>v3.2</b> (same day): the ROI list (section 3) is gated - a name needs n analysts >= 5 and must not be vetoed by the 09-27 research note; the excluded names are printed with their raw scores. "
  "<b>v3.1</b>: +10 cards (JAZZ, BBIO, ABSI, HUBS, KYTX, NTLA, PRCH, SOC, ENS, TER) added to section 2 and scored in section 3; spend restated at the provider-calibrated price ($2.37); the 09-27 books' entry corrected to Monday 09-28. "
  "Licence of every list here: PRODUCT_EXPERIMENT - nothing in this document is a claim of alpha and none of it is an order.")
H(2, "0. What changed since v2, and why it changes how to read every list below")
T(["#", "What the review loop found (2026-09-26 to 09-27)", "How to read the lists because of it"], [
    ["1", "Broker identity is a coin flip: 320,809 directional analyst claims hit 50.1% at 5 days, 50.2% at 21 days; a firm's skill in the first half predicts its second half at rho -0.11.",
     "An analyst's NAME adds nothing. Section 5 prints counts and mixes, not who said it."],
    ["2", "First-mover target raises were look-ahead: point-in-time first-minus-follower -0.06% at 21d (t -0.26); the +1.34% (t 8.7) version knew the followers were coming.",
     "A fresh raise is not a reason on its own. The 'net raises 90d' column is context, not a signal."],
    ["3", "The analyst-skill filter (skill_mom) is 2025: ex-2025 it is -18.1 pp vs unskilled momentum; all of the gap is one year (+32.7 pp).",
     "Do not rank on 'skilled analysts like it'. ANALYST-SKILL-1 stays at trivial effect."],
    ["4", "'The momentum win is semis beta' was WITHDRAWN - not because it was false but because 32 blocks cannot tell (median alpha SE 0.88%/mo, MDE 2.46%/mo). All 30 of the 2024-26 top-30 rules are CANNOT_DISTINGUISH.",
     "No backtest in this repo can yet separate a 1%/month edge from zero. Every ranking below is a HYPOTHESIS list."],
    ["5", "A calendar defect: by-year / leave-one-year-out was keyed on the DECISION date, not the hold month; 29 LOO verdicts flip; a '2020' result was January 2021 (the meme squeeze).",
     "Year-by-year numbers quoted before 09-27 are superseded by the re-keyed receipts (`leaderboard_2026-09-26T164302Z.rekeyed.json`, then `T032801Z`)."],
    ["6", "The panel tilts small: random portfolios drawn from our own universe load 0.65-0.92 on IWM. Rules beating the benchmark in both windows: 69 of 288 vs SPY / 119 vs IWM / 139 vs the panel's random portfolio (`T032801Z`).",
     "'Beat SPY' overstates a small/mid list's skill when small caps rally and understates it when they lag. Section 3 prints each row's liquidity band."],
    ["7", "51 Dow Jones forecast rows are on the clock (48 WSJ Heard on the Street, 3 Barron's picks), made 2026-09-26, graded from Monday by the existing grader.",
     "Section 6 is new. Every column there has n graded = 0 today: attention, not evidence, until the rows resolve."],
    ["8", "The liquidity-weighted momentum book was VOIDED before entry (97.5% in MU + SNDK, rho 0.90, MU prints 09-30).",
     "Concentration and an earnings print inside 5 sessions are checked before a book is frozen (freeze_gate); section 3 prints both flags."],
], [0.03, 0.55, 0.42], compact=True)
agg = ROI["aggregate"]
P(f"<b>The books.</b> {agg['n_pending']} frozen books are PENDING their first session; the llm_portfolio grader enters each at the OPEN of the first session after its as-of date, i.e. <b>Monday 2026-09-28</b>. "
  f"That includes the two books frozen with as-of 2026-09-27 - the Bloomberg dress rehearsal and Murat's core-satellite: they also enter <b>Monday 2026-09-28</b> (v3 printed a 09-29 label from the ROI report; fixed in `3204eb4d`, `docs/PAPER_ACCOUNTS.md` re-rendered). "
  f"Of the {agg['all_priced']['n']} accounts already priced: <b>{agg['n_ahead_of_spy']} ahead of SPY, {agg['n_behind_spy']} behind</b>; all priced accounts together {agg['all_priced']['roi_pct']:+.2f}% (P&L ${agg['all_priced']['pnl']:,.0f}). First grades 09-29; the first 21-session read of the dress rehearsal is <b>2026-10-26</b> and it tests calibration and declared exposure, not the return.")
P("<b>The honest benchmark sentence.</b> Our universe tilts small (random controls' IWM beta 0.65-0.92), so a list built from it looks good against SPY in a small-cap rally for reasons that are not skill. The dress rehearsal declares it: SPY beta 0.89, IWM-SPY 0.94, and an unplanned MTUM-SPY of -0.73 (anti-momentum). Read every 'vs SPY' here beside 'vs IWM'.")
P("<b>What v3 learned from v2 (three changes of method).</b> (1) The ROI list is a declared formula bounded by each name's own volatility, instead of a union of research tables; (2) every name carries its sigma63-predicted move - the one input with measured skill (+10.0% held out at h=1 vs the LLM's +5.5%) - so an 'upside' can be read against what the stock normally moves; (3) the news columns are forecasts with an id and a grading date, not prose.")
P("<b>Standing caveat (§17).</b> Analyst target-LEVEL upside is a PERVERSE cross-sectional signal in this repo's data: high-upside names underperformed by -90 bps/month in large/mid caps (t -3.62) and -199 bps/month in small caps (t -7.21). Sections 3 and 5 use it because Murat asked for it - as a list to research, with the falsifier beside it, never as a buy list.")
P("Contents: 1. CHOSEN - the frozen books · 2. THESIS CARDS v3 · 3. ROI-MAXING HYPOTHESIS LIST · 4. Murat's holdings · 5. ANALYST UPSIDE · 6. NEWS-FORECAST STOCKS (new) · 7. Appendix.")
PB()

# ═════════ 1. CHOSEN ═════════
H(1, "1. CHOSEN - the frozen books: holdings, exposure, stops, paper status")
P("Source: `backend/data/optimus/llm_portfolio/books.jsonl` (last record per name; twins and void rows listed separately). Weights are fractions of a $1,000,000 paper book. "
  "Status: `backend/data/optimus/paper_accounts/roi_2026-09-27.json` (generated 2026-09-27T00:02Z). The last column is the sigma63-predicted |move| over 21 sessions (section 2 defines it).")
KEY = [("bloomberg_rehearsal_2026-09-27", "NEW 09-27. The Bloomberg dress rehearsal (competition, benchmark URTH as the WLS proxy). Declared: sigma 8.31%/21 sessions absolute, 8.39% vs SPY; E[rel] 0 +/- 8.4%; betas SPY 0.89+/-0.21, IWM-SPY 0.94+/-0.22, SMH-SPY -0.03+/-0.17, MTUM-SPY -0.73+/-0.24. Stop: act only if z = cumulative relative P&L / (1.83% x sqrt(t)) < -2 (-3.7% at session 1, -8.2% at 5, -11.6% at 10, -16.8% at 21); no per-name stop. Worst case: one name to zero -$100k; a 3-sigma book day -$54k. 10-26 checks: move-size rank rho >= 0.3; realised exposure within +/-0.3; fills vs plan."),
       ("murat_core_satellite_2026-09-27", "NEW 09-27. Murat's money as a book: 80% SPY core (never stops) + 10 x 2% fundamentals-proxy sleeve. TE 4.09%/yr; book beta 0.95; sleeve beta 0.76. Stop: satellite minus its random-sleeve twin, z < -2 at the 126-session check only (about -5.8% of the book); never on 21 days. Worst case: one name to zero -$20k; sleeve to zero -$200k."),
       ("human_ai_thematic_v2", "v2 personal book (unchanged since 09-25). Benchmark SPY, 126 sessions. No price stop declared: each name carries a dated falsifier. Largest name to zero: VRT 12% = -$120k."),
       ("human_ai_thematic_v1", "v1 = the un-reviewed control of v2. No price stop declared. Largest name to zero: VRT 12% = -$120k."),
       ("reviewer_opus_2026-09-25", "The adversarial reviewer's own book. 60% non-USD, graded in local currency until the FX leg exists. Worst case stated by the reviewer: about -$220k on a -35% AI/power drawdown."),
       ("cards_supports_2026-09-25", "Pure-evidence arm: every 09-25 'supports' card, equal weight, no human override. No stop declared."),
       ("probe_equal_2026-09-26", "The PROBE names, equal weight (one of three weighting twins - equal / inverse-vol / big-move tilt - read against USMV on 10-26). No stop declared.")]
for name, note in KEY:
    b = books.get(name)
    if not b:
        continue
    roi = roi_by.get(name, {})
    H(2, f"{name} - book_id {b['book_id']}")
    P(f"kind {b.get('kind')} · frozen {b.get('frozen_utc')} · as-of {b.get('asof')} · {b.get('n_positions')} positions · max weight {pct(b.get('max_weight'), 1)} · benchmark {b.get('benchmark')} · "
      f"paper status <b>{roi.get('status', 'n/a')}</b> (grader entry: first session after {b.get('asof')} = 2026-09-28 open)<br/>"
      f"<b>Objective:</b> {trunc(b.get('objective'), 300)}<br/><b>Exposure / stop / worst case:</b> {note}")
    tw = twins_of.get(b["book_id"], [])
    if tw:
        P("<b>Twins (graded beside it):</b> " + "; ".join(
            f"{t.get('twin')} `{t['book_id']}`" + (f" ({', '.join(p['ticker'] for p in t['positions'][:11])})" if t.get('twin') in ('next_k', 'random_same_band', 'random_sleeve') else "")
            for t in tw))
    rows = []
    for p in sorted(b["positions"], key=lambda p: -p["weight"]):
        f = F.get(p["ticker"], {})
        rows.append([p["ticker"], pct(p["weight"], 1), p.get("theme") or "", trunc(p.get("thesis"), 150), trunc(p.get("falsifier"), 150),
                     pct(f.get("move21"), 1)])
    cash = b.get("cash_weight")
    if cash and not any(r[0] == "CASH" for r in rows):
        rows.append(["CASH", pct(cash, 1), "", "declared", "", ""])
    T(["Ticker", "Weight", "Theme", "Thesis", "Falsifier", "σ63 move 21s"], rows, [0.08, 0.05, 0.08, 0.37, 0.36, 0.06], compact=True)

H(2, "Every other frozen book (compact): top holdings, freeze gate, status")
other = [n for n in books if n not in {k for k, _ in KEY}]
rows = []
for n in sorted(other):
    b = books[n]
    st = "VOIDED" if b["book_id"] in voids else roi_by.get(n, {}).get("status", "")
    top = ", ".join(f"{p['ticker']} {p['weight']*100:.0f}" for p in sorted(b["positions"], key=lambda p: -p["weight"])[:6])
    fgd = b.get("freeze_gate") or {}
    fg = fgd.get("verdict") or fgd.get("verdict_construction_timing") or ("CONTROL" if n.endswith("__control") else "")
    rows.append([n, b["book_id"], b.get("kind"), str(b.get("n_positions")), pct(b.get("max_weight"), 0), top, trunc(fg, 40), st])
T(["Book", "book_id", "Kind", "n", "Max w", "Top holdings (weight %)", "Freeze gate", "Status"], rows, [0.24, 0.1, 0.07, 0.03, 0.04, 0.35, 0.08, 0.09], compact=True)
stats["n_books_nontwin"] = len(books)
stats["n_twins"] = sum(len(v) for v in twins_of.values())
P(f"{len(books)} non-twin books and {stats['n_twins']} twins (ew / sector_etf / spy / random_same_band / next_k / iwm / random_sleeve comparators) are in the ledger; one book is VOIDED "
  "(`lib_mom_12_1_liqw_sealed_2026-09-26`: MU 60.3% + SNDK 37.2% = 97.5%, rho 0.90, MU prints 09-30 inside the first 5 sessions). "
  "The library books (lib_*) failed the freeze gate's TIMING check on 09-26 (09-21 bars for a 09-26 decision); they trade Monday as declared and are labelled CONTROL in docs/BRIDGE.md until re-frozen on fresh bars.")

H(2, "Paper accounts already priced (roi_2026-09-27.json)")
rows = []
for r in ROI["rows"]:
    if r["status"] in ("LIVE", "CREDENTIAL_INVALID", "UNGRADED") and r["family"] not in ("night_books_twin",):
        rows.append([trunc(r["account"], 50), r["family"], r.get("inception") or "", r.get("status"), num(r.get("roi_pct"), 2), num(r.get("spy_same_window_pct"), 2), num(r.get("vs_spy_pp"), 2), r.get("last_mark") or "", trunc(r.get("note"), 90)])
T(["Account", "Family", "Since", "Status", "ROI %", "SPY same window %", "vs SPY pp", "Last mark", "Note"], rows, [0.2, 0.08, 0.07, 0.08, 0.05, 0.07, 0.06, 0.07, 0.32], compact=True)
bf = agg["by_family"]
P("By family (ROI over each account's own window): " + "; ".join(f"{k} {v.get('roi_pct', 0):+.2f}% (n priced {v.get('n_priced')})" for k, v in bf.items() if v.get("n_priced")) +
  ". The priced night-book twins are omitted from the table. Website-lane NAVs were last marked 2026-09-18 (the Railway backend sleeps when idle; an attended fix is owed).")
PB()


# ════════════════════ part3_cards_roi.py ════════════════════


# ═════════ 2. THESIS CARDS v3 ═════════
def vc(c):
    return f"{c.get('verdict')}/{c.get('confidence')}" if c else ""


def prev_card(t):
    return C26.get(t) or C25.get(t)


H(1, "2. THESIS CARDS v3 - the shortlist re-carded on 2026-09-27")
rc = CARD_RECEIPT
P(f"Runs on {ASOF} (all `python -m scripts.thesis_cards run --only ... --date {ASOF}`; OpenClaw managed browser profile `muratclaw` for the web pass + DeepSeek `deepseek-flash` for the synthesis): "
  "(a) the v3 shortlist of 60 - the v2 book's 23 + the dress rehearsal's 10 + Murat's DKNG/QUBT/AARD/BHVN/SLDP + the 16 Dow Jones forecast tickers + the 9 distinct PROBE names (GOOG = GOOGL): 58 carded, TEM and JAZZ refused; "
  "(b) a spend test that carded JAZZ and BBIO again; (c) the price-calibration batch that carded ABSI, HUBS, KYTX, NTLA, PRCH, SOC (Murat's other holdings) and ENS, TER (v1 book). "
  f"v3.1 therefore prints {len(C3)} cards. Still refused: " + ", ".join(f"{t} ({v})" for t, v in sorted(REFUSED_CARDS.items())) + " - no v3 card for those. "
  "Spend: $2.37 for the day at the provider-calibrated price (Appendix).")
P("Columns. <b>σ63 move 21s</b> = the sigma63-predicted |move| over 21 sessions = σ63 x sqrt(21) x sqrt(2/π), σ63 = the daily log-return s.d. over the 63 sessions to the 2026-09-25 bars (`rehearsal_book.predicted_abs_move`; the vol prior with measured skill). "
  "<b>Fund.</b> = the five-ratio fundamentals PROXY (percentile-rank mean of gp_at+, ope_be+, ni_be+, at_gr1-, debt_at-, SEC filed+2d, >= 3 legs) ranked within the 2,890-name eligible universe - NOT the LightGBM that measured +39 bps/month (its panel ends 2024-12); blank = fewer than 3 legs (foreign filers, recent IPOs). "
  "<b>Upside</b> = the 2026-09-27 analyst snapshot's mean-target implied upside (§17: perverse). <b>vs 09-25</b> = the change from the previous card (09-26 for MU).")
order = {"supports": 0, "neutral": 1, "against": 2}
rows = []
vcount = Counter()
changes = Counter()
for t in sorted(SHORT, key=lambda t: (order.get((C3.get(t) or {}).get("verdict"), 3), t)):
    c = C3.get(t)
    pc = prev_card(t)
    f = F.get(t, {})
    up = L["implied_upside"].get(t) if t in L.index else None
    if c:
        vcount[c.get("verdict")] += 1
        if pc:
            ch = "same" if vc(c) == vc(pc) else f"{vc(pc)} -> {vc(c)}"
            if (pc.get("verdict") != c.get("verdict")):
                changes["verdict changed"] += 1
            elif pc.get("confidence") != c.get("confidence"):
                changes["confidence changed"] += 1
            else:
                changes["same"] += 1
        else:
            ch = "new (no 09-25 card)"
            changes["new"] += 1
    else:
        ch = f"{REFUSED_CARDS.get(t, 'NOT CARDED')} on {ASOF}" + (f" (09-25: {vc(pc)})" if pc else "")
    rows.append([t, "/".join(SHORT_SRC.get(t, [])), vc(c) if c else "-", card_next_event(c or pc), trunc((c or {}).get("falsifier"), 170),
                 pct(f.get("move21"), 1), num(f.get("fund"), 2), pct(up, 0), ch])
T(["Ticker", "From", "Verdict / conf", "Next dated catalyst (card)", "Falsifier (v3 card)", "σ63 move 21s", "Fund.", "Upside", "vs 09-25"], rows,
  [0.05, 0.07, 0.07, 0.2, 0.33, 0.05, 0.04, 0.05, 0.14], compact=True)
stats["cards_v3"] = len(C3)
stats["verdicts_v3"] = dict(vcount)
stats["card_changes"] = dict(changes)
P(f"Verdicts on {len(C3)} v3 cards: " + ", ".join(f"{k} {v}" for k, v in vcount.most_common()) + ". Against the previous card: " + ", ".join(f"{k} {v}" for k, v in changes.most_common()) +
  ". A verdict is about the EVIDENCE (supports / neutral / against the bull case), not a price call; 'high' confidence needs dated primary-source evidence (the card prompt's rule).")
PB()

# ═════════ 3. ROI-MAXING HYPOTHESIS LIST ═════════
CONV = {("supports", "high"): 1.0, ("supports", "med"): 0.75, ("supports", "low"): 0.5,
        ("neutral", "high"): 0.25, ("neutral", "med"): 0.25, ("neutral", "low"): 0.25}
CROWD_V2 = {"MU", "GME", "ORCL", "GOOGL", "GOOG", "NVDA", "BYND", "DNUT", "GPRO", "RKLB", "NBIS", "BB", "SNDK", "AMD", "PLTR"}
NOTE_CROWD = globals().get("NOTE_CROWD", set())
crowd_set = (NOTE_CROWD or set()) | CROWD_V2
H(1, "3. ROI-MAXING LIST - a declared, reproducible HYPOTHESIS ranking")
P("<b>Formula (printed so it can be re-run):</b> score = clip(U, -B, +B) x K x (0.5 if crowded else 1), where "
  "U = the analyst mean-target implied upside from the 2026-09-27 snapshot (`target_snapshots.parquet`, observed 2026-09-26T17:14Z); "
  "B = 2 x σ63 x sqrt(126) = the two-sigma 6-month move of the name's own recent volatility - no name is credited with more upside than two standard deviations of what it moves in 126 sessions; "
  "K = card conviction: supports/high 1.0, supports/med 0.75, supports/low 0.5, neutral 0.25, against 0 (an against card removes the name); "
  "crowded = on the v2 retail-crowding list (research_social.md §3: " + ", ".join(sorted(CROWD_V2)) + ")" + (" or read as retail-crowded in the 09-27 research note's clean crowd reads (" + ", ".join(sorted(NOTE_CROWD)) + "; the note's other crowd reads are 'n/a - not checked')" if NOTE_CROWD else "") + ". "
  "Universe = the shortlist names (v3.1: the 60 plus ABSI, HUBS, KYTX, NTLA, PRCH, SOC, AMSC, ENS, TER) with a v3 card, a σ63 and a snapshot upside (a name with no analyst mean target, e.g. NVEC, cannot be scored and is listed below the table); ranked by score. The score is an expected-upside PROXY, not a forecast.")
P("<b>Eligibility (v3.2, applied before ranking):</b> a name enters the ranked list only if (1) it has a v3 thesis card, (2) <b>n analysts >= 5</b> - the same rule that separates section 5a/5b from 5c; a mean target from 1-4 analysts is a thin-coverage number (yfinance numberOfAnalystOpinions, 2026-09-27; the MarketWatch count where yfinance has none) - and (3) it is <b>not vetoed by the 09-27 research note</b>, whose Tier-1 profiles explicitly exclude " + (", ".join(sorted(NOTE_VETO)) if NOTE_VETO else "none") + " as known traps (stale or thin-coverage targets, a falsifier that already fired, a prior veto). "
  "Every name that fails (2) or (3) is printed with its raw score in the EXCLUDED table directly under the ranked list, so nothing is hidden.")
P("<b>Why this is a HYPOTHESIS list.</b> U is target-level upside, which §17 measured as perverse (-90 / -199 bps/month). The card conviction is an LLM verdict about evidence, and LLM DIRECTION measured -7.9% skill (n = 780). The σ63 bound is the one term with measured skill, and it is a MAGNITUDE term, not a direction. "
  "So each row carries its falsifier and its 2026-10-26 check: at 21 sessions the realised |move| should rank with the predicted |move| (Spearman >= 0.3 over the list), and a row whose card falsifier fires by then is removed. The list is graded against the same names' SPY and IWM legs, not only SPY.")
rows_roi = []
for t in SHORT:
    c = C3.get(t)
    f = F.get(t, {})
    if not c or t not in L.index or f.get("sigma63") is None or not isnum(L.loc[t, "implied_upside"]):
        continue
    k = CONV.get((c.get("verdict"), c.get("confidence")), 0.0)
    U = float(L.loc[t, "implied_upside"])
    B = f["two_sigma126"]
    cred = max(-B, min(B, U))
    crowd = t in crowd_set
    score = cred * k * (0.5 if crowd else 1.0)
    ne = next_event_date(t)
    e5 = bool(ne and ne[0] <= SESS5_END)
    _mix, n_an = recmix(t)
    if n_an is None and MW.get(t, {}).get("n_analysts") is not None:
        n_an = int(MW[t]["n_analysts"])
    why = []
    if n_an is None or n_an < 5:
        why.append(f"n < 5 (n {n_an if n_an is not None else '?'})")
    if t in NOTE_VETO:
        why.append("research-note veto: " + NOTE_VETO[t])
    rows_roi.append(dict(t=t, U=U, B=B, cred=cred, k=k, crowd=crowd, score=score, verdict=vc(c), f=f, ne=ne, e5=e5, c=c, n=n_an, why=why))
rows_roi.sort(key=lambda r: -r["score"])
excluded = [r for r in rows_roi if r["why"]]
rows_roi = [r for r in rows_roi if not r["why"]]
stats["roi_rows"] = len(rows_roi)
stats["roi_excluded"] = [(r["t"], round(r["score"] * 100, 1), "; ".join(r["why"])[:80]) for r in excluded]
# 2026-10-06 (C4): the ranked rows as JSON beside the inputs, so the Opportunity
# Explorer (`scripts/opportunities_build.py`) reads the ranking instead of
# re-parsing the rendered Markdown. Written temp -> verify -> replace.
_roi_out = SCR / "roi_list_v3.json"
_roi_blob = {"schema": "stock_lists_roi/1", "asof": ASOF, "builder": "scripts/stock_lists_v3_build.py section 3",
             "formula": "score = clip(U, -B, +B) x K x (0.5 if crowded else 1); U = analyst mean-target upside, "
                        "B = 2 x sigma63 x sqrt(126), K = card conviction",
             "ranked": [{"rank": i, "ticker": r["t"], "score": r["score"], "U": r["U"], "B": r["B"], "K": r["k"],
                         "crowded": r["crowd"], "card": r["verdict"], "n": r["n"]} for i, r in enumerate(rows_roi, 1)],
             "excluded": [{"ticker": r["t"], "score": r["score"], "U": r["U"], "B": r["B"], "K": r["k"],
                           "card": r["verdict"], "n": r["n"], "why": " | ".join(r["why"])} for r in excluded]}
_tmp = _roi_out.with_suffix(".tmp")
_tmp.write_text(json.dumps(_roi_blob, indent=1, default=str), encoding="utf-8")
json.loads(_tmp.read_text(encoding="utf-8"))
_tmp.replace(_roi_out)
rows = []
for i, r in enumerate(rows_roi, 1):
    f = r["f"]
    ne = r["ne"]
    rows.append([str(i), r["t"] + f" (n {r['n']})", f"{r['score']*100:+.1f}%", pct(r["U"], 0), pct(r["B"], 0) + (" (binds)" if abs(r["U"]) > r["B"] else ""), r["verdict"], f"{r['k']:.2f}",
                 "yes" if r["crowd"] else "", f.get("band") or "", pct(f.get("move21"), 1), num(f.get("fund"), 2),
                 (f"{ne[0]} ({ne[1]})" if ne else "unknown") + (" <=5 SESS" if r["e5"] else ""), trunc(r["c"].get("falsifier"), 130),
                 (f"top-15 #{NOTE_TOP[r['t']]}" if r["t"] in NOTE_TOP else "") + (" DROP/TRIM" if r["t"] in NOTE_DROP else "")])
T(["#", "Ticker", "Score", "U (analyst)", "B = 2σ 126s", "Card", "K", "Crowd", "Band", "σ63 move 21s", "Fund.", "Next print (source)", "Falsifier", "Research note"], rows,
  [0.025, 0.06, 0.05, 0.05, 0.07, 0.07, 0.03, 0.035, 0.04, 0.05, 0.035, 0.1, 0.315, 0.06], compact=True)
H(2, f"EXCLUDED FROM THE ROI LIST - {len(excluded)} names (scored, then removed by the eligibility rule)")
T(["Ticker", "Raw score", "U (analyst)", "n analysts", "Card", "Band", "Reason"],
  [[r["t"], f"{r['score']*100:+.1f}%", pct(r["U"], 0), str(r["n"]) if r["n"] is not None else "?", r["verdict"], r["f"].get("band") or "", " | ".join(r["why"])] for r in excluded],
  [0.05, 0.06, 0.06, 0.06, 0.08, 0.05, 0.64], compact=True)
unscored = [t for t in SHORT if t not in {r["t"] for r in rows_roi} | {r["t"] for r in excluded}]
P("Not scored (no v3 card, no σ63, or no analyst mean target in the 09-27 snapshot): " + ", ".join(
    f"{t} ({'card ' + REFUSED_CARDS[t] if t in REFUSED_CARDS else ('no card' if t not in C3 else ('no σ63' if F.get(t, {}).get('sigma63') is None else 'no target'))}" + (", against" if (C3.get(t) or {}).get('verdict') == 'against' else '') + ")" for t in unscored))
TOP10 = [r["t"] for r in rows_roi if r["score"] > 0][:10]
stats["roi_top10"] = [(r["t"], round(r["score"] * 100, 1)) for r in rows_roi[:10]]
globals()["TOP10"] = TOP10
P("<b>Construction checks on the top 10 as an equal-weight 10% book</b> (the freeze gate's construction rules, `scripts/night_backtest_factory.freeze_gate`, run on the 2026-09-25 bars): see the gate line below. "
  "Rows marked '<=5 SESS' print inside the first five sessions after entry (by 2026-10-02): at >10% weight the gate would refuse them; at 10% they pass but the first week is a coin flip on the print (the voided liqw book's lesson).")


# ════════════════════ part4_rest.py ════════════════════


# the freeze gate's construction + timing checks on the top 10 as a 10 x 10% book (run here, on the bars)
_earn = {}
for _t in TOP10:
    _ne = next_event_date(_t)
    _earn[_t] = ({"status": "DUE", "why": f"next print {_ne[0]} ({_ne[1]}) <= {SESS5_END}"} if _ne and _ne[0] <= SESS5_END
                 else ({"status": "NOT_DUE", "why": f"next print {_ne[0]} ({_ne[1]})"} if _ne else {"status": "UNKNOWN", "why": "no dated print (card / EDGAR+91d / MW)"}))
from scripts.bloomberg_rehearsal_book import load_bars as _load_bars
from scripts.night_backtest_factory import freeze_gate as _freeze_gate
_bars = _load_bars()
_g = _freeze_gate(None, {t: 0.10 for t in TOP10}, _bars, pd.DatetimeIndex(sorted(_bars["date"].unique())),
                  decision_date=ASOF, earnings=_earn)
del _bars
con, det = _g["construction"], _g.get("detail", {})
P("<b>Gate result:</b> " + "; ".join(f"{k} = {v}" for k, v in con.items()) + f"; timing: {_g.get('timing')}; "
  f"effective N {det.get('effective_n')}, largest name to zero ${det.get('largest_name_to_zero_usd', 0):,.0f}, max rho>0.8 cluster {det.get('max_cluster')} ({det.get('max_cluster_share')}). "
  "Earnings passed to the gate: " + "; ".join(f"{t} {v['status']}" for t, v in _earn.items()) + ".")
stats["gate"] = con

if NOTE:
    H(2, "3b. The research note's top-15 and drops (attributed: Sonnet research note, 2026-09-27)")
    P("Source: `docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md` - demand / how the company feeds it / CEO / competition / profitability / street / crowd / ROI read per name. "
      "Its rows are copied as written; the 'In the formula list' column says where the same name ranks in section 3 (blank = not carded or no snapshot upside).")
    for title, tab in NOTE_TABLES:
        H(3, title)
        hdr, body = tab
        rank_of = {r["t"]: i for i, r in enumerate(rows_roi, 1)}
        tcol = next((i for i, h in enumerate(hdr) if h.strip().lower() in ("ticker", "name", "symbol")), 0)
        hdr2 = hdr + ["In the formula list"]
        body2 = []
        for row in body:
            tk = re.sub(r"[^A-Z.]", "", row[tcol].split()[0].upper()) if row[tcol].strip() else ""
            body2.append(row + [f"#{rank_of[tk]}" if tk in rank_of else ""])
        n = len(hdr2)
        T(hdr2, body2, [1.0 / n] * n, compact=True)
else:
    P("<b>3b. Research note pending.</b> The Sonnet research note (`docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md`: demand / CEO / competition / profitability / street / crowd per name, a top-15 and drops) had not landed when this version was rendered; its crowd/pump flags therefore do not enter the formula - only the v2 retail-crowding list does.")
PB()

# ═════════ 4. MURAT'S HOLDINGS ═════════
H(1, "4. Murat's holdings vs the v3 verdicts")
mb = yaml.safe_load(open(REPO / "backend/data/murat_book.yaml", encoding="utf-8"))
ml = roi_by.get("murat_live", {})
P(f"Source: `backend/data/murat_book.yaml` (reconciled 2026-08-11; confirmed: False; cash unrecoverable). The recorded share counts are {ml.get('roi_pct', float('nan')):+.2f}% since 2026-08-11 vs SPY {ml.get('spy_same_window_pct', float('nan')):+.2f}% "
  f"({ml.get('vs_spy_pp', float('nan')):+.2f} pp; `roi_2026-09-27.json`, AARD unpriced - absent from the bars panel). All twelve are carded on {ASOF} except AMSC (card refused, REFUSED_EMPTY_LOG) and AARD (no bars: no σ63), which keep their 09-25 card where one exists. MW = the MarketWatch analyst snapshot read 2026-09-26 (Dow Jones bundle).")
rows = []
FOCUS = ["DKNG", "QUBT", "AARD", "BHVN", "SLDP"]
for p in sorted(mb["positions"], key=lambda p: (p["ticker"] not in FOCUS, p["ticker"])):
    t = p["ticker"]
    c = C3.get(t)
    pc = prev_card(t)
    f = F.get(t, {})
    mw = MW.get(t, {})
    mws = (f"{mw.get('consensus_rating')}, n {mw.get('n_analysts')}, mean {num(mw.get('target_mean'))} (lo {num(mw.get('target_low'))} / hi {num(mw.get('target_high'))}) vs px {num(mw.get('current_price'))}; next EPS {mw.get('next_earnings_date')}"
           if mw else "")
    if c:
        ch = "same" if pc and vc(pc) == vc(c) else (f"{vc(pc)} -> {vc(c)}" if pc else "new")
    else:
        ch = "(not re-carded)"
    rows.append([t, str(p.get("shares")), str(p.get("cost_basis", "missing")), vc(c or pc), ch, pct(f.get("move21"), 1), num(f.get("fund"), 2), mws,
                 trunc((c or pc or {}).get("falsifier"), 150), trunc(p.get("kill_condition"), 90)])
T(["Ticker", "Shares", "Cost", "Card (v3, else 09-25)", "Changed", "σ63 move 21s", "Fund.", "MW analyst snapshot", "Card falsifier", "Kill condition (logged)"], rows,
  [0.045, 0.04, 0.035, 0.07, 0.08, 0.045, 0.035, 0.2, 0.28, 0.17], compact=True)
P("Reading: an 'against' card is a statement about the evidence for the bull case, not an instruction to sell; the kill condition is Murat's own logged exit condition (auto-adopted defaults for ABSI, AMSC, HUBS, KYTX, SLDP), never an armed order.")
PB()

# ═════════ 5. ANALYST UPSIDE ═════════
H(1, "5. ANALYST-IMPLIED UPSIDE >= 50% and >= 100% (from the 2026-09-27 pull)")
P("<b>CAVEAT (§17):</b> target-LEVEL upside is a perverse cross-sectional signal in this repo's data: -90 bps/mo large/mid (t -3.62), -199 bps/mo small (t -7.21). High implied upside most often means the price fell and the targets have not caught up. Every row is a name to research, not a buy.")
v2band = {}
v2up = {}
txt = P_V2.read_text(encoding="utf-8").splitlines()
sec = None
for ln in txt:
    if ln.startswith("## 4a."):
        sec = "A"
    elif ln.startswith("## 4b."):
        sec = "B"
    elif ln.startswith("## 4c."):
        sec = "C"
    elif ln.startswith("# 5."):
        sec = None
    elif sec in ("A", "B") and ln.startswith("| ") and not ln.startswith("| Ticker"):
        cells = [x.strip() for x in ln.strip("|").split("|")]
        v2band[cells[0]] = sec
        try:
            v2up[cells[0]] = float(cells[4].rstrip("%")) / 100
        except Exception:
            pass
    elif sec == "C" and ln and not ln.startswith("#") and "(n " in ln:
        for m in re.finditer(r"([A-Z][A-Z0-9.\-]*) (\d+)% \(n ", ln):
            v2band[m.group(1)] = "C"
            v2up[m.group(1)] = int(m.group(2)) / 100
scr = L[(L["implied_upside"] >= 0.5) & (L["price"] >= 2)].copy()
obs = sorted(set(scr["observed_at"].astype(str).str[:16]))
P(f"Source: `backend/data/optimus/analyst/target_snapshots.parquet` (latest row per ticker; this pull observed {obs[0]}Z - {obs[-1]}Z = 2026-09-27 ~01:14 HKT; `analyst_pull_2026-09-27.json`: 3,096 snapshots, 0 failed). "
  f"Screen: implied_upside >= 0.50 and price >= $2 -> <b>{len(scr)}</b> names ({int((scr.implied_upside >= 1).sum())} at >= 100%). "
  "Analyst count and strong-buy/buy/hold/sell mix: yfinance Ticker.info numberOfAnalystOpinions + Ticker.recommendations (current month), fetched 2026-09-27 for this version (v2 fetched 2026-09-25). "
  "Band = median 63-session dollar volume on the bars panel (mega >= $1B, large >= $100M, mid >= $20M, else small). 'vs v2' = the band this name had in v2 (A = >= 100%, B = 50-100%, C = < 5 analysts) and v2's upside.")


def band_of(u, n):
    if n is None or n < 5:
        return "C"
    return "A" if u >= 1.0 else "B"


v3band = {}
tabs = {"A": [], "B": [], "C": []}
nocount = 0
for t, r in scr.sort_values("implied_upside", ascending=False).iterrows():
    mix, n = recmix(t)
    if n is None:
        nocount += 1
    b = band_of(r.implied_upside, n)
    v3band[t] = b
    f = F.get(t, {})
    was = v2band.get(t)
    chg = "NEW" if was is None else ("same band" if was == b else f"{was} -> {b}")
    if was is not None and t in v2up:
        chg += f" (v2 {v2up[t]*100:.0f}%)"
    tabs[b].append((t, r, mix, n, f, chg))
for code, title in [("A", "5a. Implied upside >= 100% with n >= 5 analysts"), ("B", "5b. Implied upside 50-100% with n >= 5 analysts")]:
    H(2, f"{title} - {len(tabs[code])} names")
    rows = []
    for t, r, mix, n, f, chg in (sorted(tabs[code], key=lambda x: (-(x[3] or 0), -x[1].implied_upside))):
        rows.append([t, num(r.price), num(r.target_mean), f"{num(r.target_median)} / {num(r.target_high)}", pct(r.implied_upside, 0), str(n), mix,
                     f"{f.get('band') or ''}" + (f" (${f['mdv63']/1e6:,.1f}M)" if f.get("mdv63") else ""), pct(f.get("move21"), 0), chg])
    T(["Ticker", "Price", "Mean target", "Median / high", "Upside", "n", "Mix SB/B/H/S (key)", "Band (med $vol)", "σ63 move 21s", "vs v2"], rows,
      [0.06, 0.06, 0.07, 0.1, 0.06, 0.04, 0.2, 0.13, 0.07, 0.21], compact=True)
H(2, f"5c. Passed the screen but fewer than 5 analysts or no count - {len(tabs['C'])} names")
P("; ".join(f"{t} {r.implied_upside*100:.0f}% (n {n if n is not None else '?'})" for t, r, mix, n, f, chg in tabs["C"]))
entered = sorted(t for t in v3band if t not in v2band)
left = sorted(t for t in v2band if t not in v3band)
moved = sorted((t, v2band[t], v3band[t]) for t in v3band if t in v2band and v2band[t] != v3band[t])
stats["analyst"] = {"n_screen": len(scr), "A": len(tabs["A"]), "B": len(tabs["B"]), "C": len(tabs["C"]), "entered": len(entered), "left": len(left), "moved": len(moved), "nocount": nocount,
                    "v2": {"A": sum(1 for v in v2band.values() if v == "A"), "B": sum(1 for v in v2band.values() if v == "B"), "C": sum(1 for v in v2band.values() if v == "C")}}
H(2, "5d. What moved vs v2")
P(f"v2 (snapshot 2026-09-24, counts 2026-09-25): A {stats['analyst']['v2']['A']} / B {stats['analyst']['v2']['B']} / C {stats['analyst']['v2']['C']} = {len(v2band)} names. "
  f"v3 (snapshot 2026-09-27, counts 2026-09-27): A {len(tabs['A'])} / B {len(tabs['B'])} / C {len(tabs['C'])} = {len(v3band)} names. "
  f"<b>Entered the screen: {len(entered)}</b>; <b>left it: {len(left)}</b>; <b>changed band: {len(moved)}</b>. Names without a count this pass: {nocount}. "
  "A name leaves when its price rose toward the target or the target was cut below +50%; it enters when the price fell or a target was raised. The price moves dominate over 3 days - that is the §17 mechanism in miniature.")
T(["Change", "Names"], [
    [f"entered ({len(entered)})", ", ".join(f"{t} {L.loc[t, 'implied_upside']*100:.0f}%" for t in entered)],
    [f"left ({len(left)})", ", ".join(f"{t} (v2 {v2up.get(t, float('nan'))*100:.0f}%" + (f", now {L.loc[t, 'implied_upside']*100:.0f}%" if t in L.index else ", no snapshot") + (", price now < $2" if t in L.index and L.loc[t, 'price'] < 2 else "") + ")" for t in left)],
    [f"band changed ({len(moved)})", ", ".join(f"{t} {a}->{b}" for t, a, b in moved)],
], [0.12, 0.88], compact=True)
PB()


# ════════════════════ part5_news.py ════════════════════


# ═════════ 6. NEWS-FORECAST STOCKS ═════════
H(1, "6. NEWS-FORECAST STOCKS (new in v3) - what the Dow Jones columns forecast")
DJ = OPT / "news_corpus/dowjones"
arts = {}
for fpath in glob.glob(str(DJ / "*/2026-09-26/*.json")):
    a = json.load(open(fpath, encoding="utf-8"))
    arts[a["sha"]] = a
claims = [json.loads(l) for l in open(DJ / "_claims/2026-09-26.jsonl", encoding="utf-8") if l.strip()]
preds = defaultdict(list)
for l in open(OPT / "predictions.jsonl", encoding="utf-8"):
    if "wsj_heard" in l or "barrons_stock" in l:
        r = json.loads(l)
        preds[(r["inputs_used"].get("claim_hash"), r["ticker"])].append(r)
src_claims = {}
for l in open(OPT / "sources/claims.jsonl", encoding="utf-8"):
    if "wsj_heard" in l or "barrons" in l:
        r = json.loads(l)
        src_claims[(r["post_url"], r["ticker"])] = r
n_rows = sum(len(v) for v in preds.values())
stats["dj_forecast_rows"] = n_rows
P(f"Sources: the Dow Jones corpus `backend/data/optimus/news_corpus/dowjones/` ({len(arts)} stored articles read 2026-09-26 in Murat's MuratClaw window at human pace: WSJ Heard on the Street, Barron's stock picks, the Barron's Big Money poll, and MarketWatch analyst pages), "
  f"the claims extracted from them (`_claims/2026-09-26.jsonl`, {len(claims)} claims) and the forecast rows written from those claims into `backend/data/optimus/predictions.jsonl` "
  f"(<b>{n_rows} rows</b>: specialist `source:wsj_heard_on_the_street` / `source:barrons_stock_picks`, observable beats_benchmark vs SPY at 1 / 5 / 20 sessions, p 0.60 for 'up' and 0.40 for 'down' - a fixed 0.5 +/- 0.10 by stated direction; the column earns its weight only through `forecast_reputation`). "
  "Licence: personal research reads; headlines, metadata and our own one-line claims are stored, no full-text redistribution - so a 'reason' below is our paraphrase with at most a short quote.")
P("<b>Reliability so far: n graded = 0 for every column</b> (made 2026-09-26; the first 1-session rows resolve after the 09-28/29 sessions, the 20-session rows around 2026-10-26). "
  "<b>PIT caveat:</b> every row is pit_grade 'first_seen_only' - the forecast is stamped when WE read the article, and the articles were published 1 to 24 days earlier, so part of any move the column 'predicted' may already be in the price. The grader scores from made_at, which is the honest clock for us, not for the columnist.")


def stated_target(a, ticker):
    """A sentence in the stored article text that states a price target, if any (<= 30 words)."""
    if not a:
        return ""
    txt = a.get("text") or ""
    for s in re.split(r"(?<=[.!?])\s+", txt):
        if re.search(r"target", s, re.I) and re.search(r"\$\s?\d", s):
            w = s.split()
            return " ".join(w[:30]) + ("…" if len(w) > 30 else "")
    return ""


rows = []
seen = set()
for c in claims:
    t = c["ticker"]
    a = arts.get(c["article_sha"])
    pr = preds.get((src_claims.get((c["url"], t), {}).get("claim_hash"), t), [])
    if not pr:   # fall back: any forecast row for this ticker from this article url
        pr = [r for k, v in preds.items() for r in v if r["ticker"] == t and r.get("next_observable") == c["url"]]
    f = F.get(t, {})
    hs = c.get("horizon_days_stated")
    mv = (f["sigma63"] * math.sqrt(hs) * math.sqrt(2 / math.pi)) if (f.get("sigma63") and hs) else None
    tgt = stated_target(a, t)
    up = L["implied_upside"].get(t) if t in L.index else None
    mix, n = recmix(t)
    mw = MW.get(t)
    street = (f"MW {mw.get('consensus_rating')} n {mw.get('n_analysts')} mean {num(mw.get('target_mean'))} (lo {num(mw.get('target_low'))} / hi {num(mw.get('target_high'))}); next EPS {mw.get('next_earnings_date')}" if mw
              else (f"yf n {n}, {mix}; mean tgt {num(L.loc[t, 'target_mean'])} (lo {num(L.loc[t, 'target_low'])} / hi {num(L.loc[t, 'target_high'])}) = {pct(up, 0)}" if t in L.index else "no snapshot"))
    if pr:
        hz = "/".join(str(x) for x in sorted({r["horizon_days"] for r in pr}))
        status = f"{len(pr)} rows, p {pr[0]['probability']:.2f}, made {pr[0]['made_at'][:10]}"
    else:
        hz = ""
        status = ("NOT a forecast: direction none" if c.get("direction") in (None, "none") else
                  ("NOT a forecast: archive article (published " + c["published_utc"][:10] + ", > 30 days before first seen)" if c["published_utc"][:10] < "2026-08-27" else "NOT a forecast row (claim only)"))
    col = "WSJ HOTS" if c["source_id"].startswith("wsj") else ("Barron's pick" if "pick" in (a or {}).get("column", "") or c["source_id"] == "barrons_stock_picks" else "Barron's Big Money poll")
    potential = (f"stated: {tgt}" if tgt else "") or (f"no stated target; σ63-predicted |move| over the stated {hs}d = {mv*100:.0f}% (the bound we credit)" if mv else "no stated target; no σ63 (not in the bars panel)")
    rows.append([t, col, c.get("direction") or "none", trunc(c["paraphrase"], 140), f"{c['published_utc'][:10]} / {hs}d stated" + (f" / rows {hz}" if hz else ""),
                 trunc(potential, 170), street, status, vc(C3.get(t)) or (REFUSED_CARDS.get(t) and "refused") or "-", "n 0 / hit -"])
    seen.add(t)
rows.sort(key=lambda r: (r[7].startswith("NOT"), r[1], r[0]))
T(["Ticker", "Column", "Dir.", "Reason (our paraphrase of the article)", "Published / horizon", "Potential upside", "Street snapshot", "Forecast rows", "Our v3 card", "Column record"], rows,
  [0.04, 0.065, 0.035, 0.2, 0.085, 0.19, 0.17, 0.1, 0.065, 0.05], compact=True)
stats["dj_table_rows"] = len(rows)
stats["dj_tickers_forecast"] = len({k[1] for k in preds})
H(2, "The Big Money poll (index level) and the MarketWatch analyst pages")
bm = [json.loads(l) for l in open(DJ / "_structured/barrons_big_money_poll.jsonl", encoding="utf-8") if l.strip()]
T(["Index", "Direction", "Bullish %", "Bearish %", "Neutral %", "Horizon", "Published", "First seen by us", "Note"],
  [[r.get("index"), r.get("direction"), str(r.get("bullish_pct")), str(r.get("bearish_pct")), str(r.get("neutral_pct")), r.get("horizon_label") or "unstated",
    r.get("published_utc", "")[:10], r.get("first_seen_utc", "")[:10], "ARCHIVE: published ~11 months before we read it; context only, not a forecast row"] for r in bm],
  [0.06, 0.07, 0.06, 0.06, 0.06, 0.08, 0.08, 0.09, 0.44], compact=True)
P("A second Big Money poll article (published 2026-04-27) is stored without a structured row. The same 2025-10 poll produced three stock claims - NVDA up, PLTR down, TSLA down ('the market's most overvalued stock') - which were NOT turned into forecast rows because the article is an archive by the corpus PIT rule (published > 30 days before first seen).")
mwrows = []
for t, mw in sorted(MW.items()):
    up_mw = (mw["target_mean"] / mw["current_price"] - 1) if mw.get("target_mean") and mw.get("current_price") else None
    mwrows.append([t, mw.get("consensus_rating"), str(mw.get("n_analysts")), num(mw.get("current_price")), num(mw.get("target_mean")), num(mw.get("target_low")), num(mw.get("target_high")), pct(up_mw, 0),
                   mw.get("next_earnings_date") or "", num(mw.get("eps_current_year_est")), mw.get("first_seen_utc", "")[:16]])
T(["Ticker", "MW consensus", "n", "Price", "Mean tgt", "Low", "High", "Mean upside", "Next earnings", "EPS FY est", "Read (UTC)"], mwrows,
  [0.07, 0.1, 0.05, 0.08, 0.08, 0.08, 0.08, 0.08, 0.12, 0.09, 0.17], compact=True)
stats["mw_rows"] = len(mwrows)
PB()

# ═════════ 7. APPENDIX ═════════
H(1, "7. APPENDIX - where every number came from")
T(["Item", "File / source", "Date / run id"], [
    ["Frozen books, twins, void", "backend/data/optimus/llm_portfolio/books.jsonl", f"{len(recs)} records; rehearsal 4d0cebfeb8867fb8, core-satellite 5517aa50a29bc95b frozen 2026-09-26T19:59:52Z"],
    ["Paper-account status", "backend/data/optimus/paper_accounts/roi_2026-09-27.json", ROI["generated_utc"]],
    ["Dress rehearsal design", "docs/BOOK_2026-09-27_BLOOMBERG_DRESS_REHEARSAL.md; backend/data/optimus/rehearsal/rehearsal_2026-09-27.json", "2026-09-27"],
    ["Review verdicts", "docs/HANDOFF_2026-09-26_WAVE2_THE_REVIEW_LOOP_CLOSED_FOUR_IDEAS.md §§1-16; docs/reviews/ADJUDICATION_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md", "2026-09-26/27"],
    ["Factory receipt of record", "backend/data/optimus/strategy_library/leaderboard_2026-09-26T164302Z(.rekeyed).json; T032801Z", "69/119/139 of 288"],
    ["Thesis cards v3", f"backend/data/optimus/thesis_cards/{ASOF}/*.json + _run_receipt.json + DIGEST.md", f"{len(C3)} cards (three runs); model deepseek/deepseek-flash + OpenClaw muratclaw"],
    ["Thesis cards v2 (previous)", "backend/data/optimus/thesis_cards/2026-09-25/*.json (MU: 2026-09-26)", "2026-09-25"],
    ["σ63, predicted move, fundamentals proxy, EDGAR earnings estimate", "backend/services/rehearsal_book.py (sigma63, predicted_abs_move, fundamentals_composite, earnings_estimates) over prices_2025_26/bars.parquet, fundamentals_sec/sec_facts_history.parquet, edgar_8k/eightk_items.parquet",
     f"bars through {FACTS['meta']['bars_last']}; universe {FACTS['meta']['n_universe']}"],
    ["Freeze-gate construction check", "scripts/night_backtest_factory.py freeze_gate (construction + timing)", "on the section-3 top 10"],
    ["Analyst targets", "backend/data/optimus/analyst/target_snapshots.parquet (+ target_revisions.parquet)", "pull 2026-09-27 (observed 2026-09-26T17:14Z); analyst_pull_2026-09-27.json"],
    ["Analyst counts + mix", "yfinance Ticker.info / Ticker.recommendations", "fetched 2026-09-27 (v2: 2026-09-25)"],
    ["Dow Jones corpus + claims", "backend/data/optimus/news_corpus/dowjones/ (wsj, barrons, marketwatch, _claims, _structured)", "read 2026-09-26"],
    ["News forecast rows", "backend/data/optimus/predictions.jsonl (specialist source:wsj_heard_on_the_street / source:barrons_stock_picks)", f"{n_rows} rows, made 2026-09-26"],
    ["Source claims", "backend/data/optimus/sources/claims.jsonl", "2026-09-26"],
    ["Murat's holdings", "backend/data/murat_book.yaml", "reconciled 2026-08-11"],
    ["Research note", "docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md", "landed" if NOTE else "PENDING at render"],
], [0.2, 0.55, 0.25], compact=True)
P("<b>LLM spend (the day's thesis cards, all three runs): $2.37 at the provider-calibrated price</b> (`backend/data/optimus/llm_price/calibration_2026-09-27.json`, commit `201b8402`: deepseek-flash priced from the provider's own balance delta, k = 0.615 [0.590, 0.639] vs the old price table; "
  "the run receipt's `spend_repriced_usd` 2.368 from `thesis_cards/2026-09-27/spend_repriced.json`). The two figures v3 printed over-state the provider: the old price table read $3.82 (1.61x) and OpenClaw's own per-quest figure $4.89 (2.01x); v3's $3.38 / $4.33 were partial sums of those rulers. Everything else in this document: $0.")
H(2, "Standing findings (updated)")
P("1. <b>§17 - target LEVEL is perverse:</b> high analyst-implied upside underperformed, -90 bps/mo large/mid (t -3.62), -199 bps/mo small (t -7.21). Sections 3 and 5 are research lists for that reason; section 3 bounds the upside by 2σ and weights it by the card, which does not make it a signal.")
P("2. <b>What forecasts:</b> the free σ63 vol prior on MAGNITUDE (+10.0% held out at h=1 vs the LLM investigator's +5.5%); LLM DIRECTION does not (-7.9%, n = 780); broker identity is a coin flip (50.1%); first-mover raises were look-ahead; the analyst-skill filter is 2025 only. A process forecasts, a persona does not (§64).")
P("3. <b>Nothing is distinguishable yet:</b> no rule survives multiplicity (best DSR 0.617 at the honest denominator vs 0.95) and the 32-block window's MDE is 2.46%/month; the panel tilts small (IWM beta 0.65-0.92), so 69 / 119 / 139 of 288 rules beat SPY / IWM / the random panel in both windows. The first forward read that can say something is 2026-10-26, and it reads calibration and exposure, not return.")
