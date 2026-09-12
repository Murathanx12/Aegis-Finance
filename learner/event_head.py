"""E1 -- a TYPED-EVENT tabular head, and the honest statement of what types it has.

WHAT THIS IS AND IS NOT
-----------------------
The spec (`docs/research_notes/2026-09-12/spec_chunk9_heads.md` section 1) has
E1 consume **L2's** typed rows: 39 event types + `no_event`, each carrying
`event_type, direction, magnitude_bucket, confidence, scope, evidence_span`
from an LLM extraction over the daily corpus.

**L2 IS NOT BUILT.** So every typed event in this file comes from a PROXY, and
the proxy is named in every receipt it touches:

1. `entity_tags` the pull already writes -- `8-K:2.02` and the other item codes
   from `scripts/news_pull.py`, and `gdelt_query:*` -- mapped to vocabulary ids
   where the mapping is unambiguous. On the 2025-26 panel this path contributes
   **nothing**: that panel's 340,465 rows predate the tagged corpus, whose
   earliest file is 2026-09-11. The code path exists, is tested, and its
   coverage is REPORTED rather than assumed, so the day the corpus reaches back
   the receipt shows the number moving.
2. A **keyword proxy** over the vocabulary's own example headlines and
   definitions, which is what actually types the 2025-26 panel.

A keyword proxy is weaker than an LLM read in exactly the way that matters
here: it will type "Acme raises full-year guidance" and it will miss "we now
see the year landing at the low end", and its direction is a cue-word vote, not
a reading. That asymmetry is a REASON THE ARM CAN LOSE, and it is why the
verdict this file supports is about the proxy, not about typed events. If the
proxy beats SHUFFLE, typed events are worth L2's money. If it does not, the
question stays open at L2, and only the proxy is closed.

`backend/services/event_intel.py` already owns an 11-type vocabulary and an
LLM path. This file does NOT replace it and does not call it: event_intel types
one document on request, E1 needs 340,465 rows typed offline and deterministic,
and the 39-id vocabulary is the one L2 will emit. `_ALLOWED_EVENT_TYPES` maps
into these ids (`earnings -> earnings_report`, `ma -> mergers_acquisitions`,
...) so nothing has to be re-derived when L2 lands.

PIT
---
An event's date here is its **entry_date** -- the first session whose OPEN is
strictly after publication -- which is exactly the anchoring the panel already
enforces and re-checks. So a cell at date D may use every event with entry_date
<= D, INCLUDING D's own: that news was public before D's open by construction.
The window is `[D - w + 1, D]` in sessions and never reaches past D; the test
`test_no_feature_reaches_past_its_own_date` is what keeps it that way.

The embargo lives in the SPLIT, not in the feature window. The spec's section
1.8 item 3 asks for the feature builder to truncate at `entry_date - embargo`,
which would discard information that was genuinely public and would make the
arm worse for no leakage reason -- the embargo separates TRAIN from TEST, and
that is where `max(embargo, horizon)` is applied (`night_e1_event_head.py`).
Said out loud because a spec deviation that nobody writes down becomes a bug
report six weeks later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: `magnitude_bucket` as an ordinal. L2 emits one per instance; the proxy can
#: only emit the vocabulary's PRIOR for the type, and the receipt says so.
BUCKETS = ("NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME")

#: sessions since the most recent event of a type, when there has never been
#: one. A sentinel with a companion `_censored` flag, never 0 -- a 0 would
#: claim an event happened today, which is the opposite of the truth.
RECENCY_CENSOR = 252

#: trailing windows, in sessions, ending at (and including) the cell's own date
WINDOWS = (1, 5, 21)

#: a type occurring fewer times than this panel-wide is dropped, and the
#: dropped list goes in the receipt
MIN_OCCURRENCES = 30


@dataclass(frozen=True)
class EventType:
    """One row of the frozen vocabulary, plus the proxy's matching rules."""
    id: str
    magnitude_prior: str
    direction_prior: int                      # -1 / 0 / +1, 0 = ambiguous or neutral
    patterns: tuple[str, ...]
    up: tuple[str, ...] = ()
    down: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default=())  # entity_tags that imply this type

    def rx(self) -> re.Pattern:
        return re.compile("|".join(self.patterns), re.I)


def _t(i, mag, dirn, pats, up=(), down=(), tags=()):
    return EventType(i, mag, dirn, tuple(pats), tuple(up), tuple(down), tuple(tags))


_UP_GENERIC = ("beat", "beats", "tops", "above estimate", "exceeds", "raises", "raised",
               "upgrade", "upgrades", "record high", "better than expected")
_DOWN_GENERIC = ("miss", "misses", "below estimate", "shortfall", "cuts", "cut", "lowers",
                 "lowered", "downgrade", "downgrades", "warns", "worse than expected")

#: THE FROZEN VOCABULARY -- the 39 ids of
#: `docs/research_notes/2026-09-11/spec_events_and_calibration.md` section 1.2,
#: in its order, with the proxy's patterns drawn from that section's own
#: definitions and example headlines. The ids are the contract with L2; the
#: patterns are this file's and are replaced, not extended, when L2 lands.
VOCABULARY: tuple[EventType, ...] = (
    _t("earnings_report", "MODERATE", 0,
       (r"\bq[1-4]\b.{0,30}\b(eps|earnings|results|revenue)", r"\bearnings\b.{0,20}\breport",
        r"\breports?\b.{0,25}\b(eps|earnings|quarterly results)", r"\bquarterly results\b"),
       _UP_GENERIC, _DOWN_GENERIC, ("8-K:2.02",)),
    _t("earnings_preannouncement", "MODERATE", 0,
       (r"\bpre-?announce", r"\bprofit warning\b", r"\bwarns\b.{0,30}\b(revenue|quarter|results)",
        r"\bpreliminary (results|revenue)\b"), ("above", "raises"), ("warns", "miss", "shortfall")),
    _t("guidance_change", "MODERATE", 0,
       (r"\bguidance\b", r"\bforecast\b.{0,20}\b(raise|cut|lower|reaffirm)",
        r"\b(raises|cuts|lowers|reaffirms|withdraws)\b.{0,25}\b(outlook|forecast)"),
       ("raises", "raised", "boosts", "lifts", "upbeat"), ("cuts", "lowers", "withdraws", "slashes")),
    _t("mergers_acquisitions", "LARGE", 1,
       (r"\bto acquire\b", r"\bacquisition of\b", r"\bmerger\b", r"\bbuyout\b", r"\btakeover\b",
        r"\bacquires\b", r"\bto buy\b.{0,25}\bfor \$"), ("acquire", "acquires"), ("terminates",),
       ("8-K:2.01",)),
    _t("divestiture_asset_sale", "MODERATE", 0,
       (r"\bdivest", r"\bsells its\b", r"\bsale of its\b", r"\bunit sale\b"), (), (), ("8-K:2.01",)),
    _t("spinoff", "LARGE", 0, (r"\bspin-?off\b", r"\bto spin off\b", r"\bseparat(e|ion) into two\b")),
    _t("bankruptcy_or_going_concern", "EXTREME", -1,
       (r"\bchapter 11\b", r"\bchapter 7\b", r"\bbankrupt", r"\bgoing concern\b",
        r"\binsolven"), (), (), ("8-K:1.03",)),
    _t("delisting_or_listing_risk", "LARGE", -1,
       (r"\bdelist", r"\bnon-?compliance\b.{0,30}\blisting\b", r"\bminimum (bid|share) price\b"),
       (), (), ("8-K:3.01",)),
    _t("debt_issuance_or_obligation", "MODERATE", 0,
       (r"\bsenior notes\b", r"\bbond offering\b", r"\bterm loan\b", r"\bcredit facility\b",
        r"\bnotes due 20\d\d\b"), (), (), ("8-K:2.03",)),
    _t("debt_covenant_or_default_trigger", "LARGE", -1,
       (r"\bcovenant\b", r"\bcross-?default\b", r"\bdefault(s|ed)? on\b",
        r"\bacceleration of\b.{0,20}\bdebt\b"), (), (), ("8-K:2.04",)),
    _t("equity_issuance_dilution", "MODERATE", -1,
       (r"\bsecondary offering\b", r"\bpublic offering\b", r"\bprices \$?\d+.{0,20}offering\b",
        r"\bat-the-market offering\b", r"\bdilut"), (), (), ("8-K:3.02",)),
    _t("stock_buyback", "SMALL", 1,
       (r"\bbuyback\b", r"\bshare repurchase\b", r"\brepurchase program\b")),
    _t("dividend_increase", "SMALL", 1,
       (r"\b(raises|increases|hikes|boosts)\b.{0,20}\bdividend\b", r"\bdividend (hike|increase)\b")),
    _t("dividend_cut_or_suspension", "MODERATE", -1,
       (r"\b(cuts|slashes|suspends|eliminates|halts)\b.{0,20}\bdividend\b",
        r"\bdividend (cut|suspension)\b")),
    _t("special_dividend", "SMALL", 1, (r"\bspecial dividend\b",)),
    _t("regular_dividend_declaration", "NEGLIGIBLE", 0,
       (r"\bdeclares\b.{0,30}\bdividend\b", r"\bquarterly dividend\b", r"\bex-?dividend\b")),
    _t("stock_split", "SMALL", 0, (r"\bstock split\b", r"\b\d+-for-\d+ split\b")),
    _t("reverse_stock_split", "SMALL", -1, (r"\breverse (stock )?split\b",)),
    _t("credit_rating_change", "MODERATE", 0,
       (r"\b(moody's|s&p|fitch)\b", r"\bcredit rating\b", r"\boutlook (negative|positive|stable)\b"),
       ("upgrades", "raises", "positive"), ("downgrades", "cuts", "negative")),
    _t("new_contract_or_partnership", "SMALL", 1,
       (r"\bpartnership\b", r"\bsigns?\b.{0,25}\b(agreement|deal|contract)\b",
        r"\bawarded\b.{0,20}\bcontract\b", r"\bsupply agreement\b", r"\bcollaborat")),
    _t("contract_loss_or_termination", "SMALL", -1,
       (r"\bloses\b.{0,25}\bcontract\b", r"\bcontract (loss|termination)\b",
        r"\bterminates\b.{0,25}\b(agreement|contract)\b")),
    _t("product_launch_or_innovation", "SMALL", 0,
       (r"\blaunch", r"\bunveil", r"\bintroduces\b", r"\bnext-?generation\b", r"\bdebuts\b")),
    _t("product_recall_or_defect", "MODERATE", -1,
       (r"\brecall", r"\bdefect", r"\bsafety probe\b")),
    _t("clinical_trial_result", "LARGE", 0,
       (r"\bphase [123]\b", r"\bclinical trial\b", r"\bprimary endpoint\b", r"\btopline data\b"),
       ("met", "positive", "success"), ("failed", "missed", "halt")),
    _t("regulatory_approval", "LARGE", 1,
       (r"\bfda (approv|clear)", r"\bapproval for\b", r"\bceo?mark\b", r"\bgrants approval\b")),
    _t("regulatory_investigation_or_action", "MODERATE", -1,
       (r"\b(sec|doj|ftc|cftc)\b.{0,30}\b(probe|investigat|subpoena|charges)\b",
        r"\binvestigation into\b", r"\bantitrust\b")),
    _t("litigation_filed", "SMALL", -1,
       (r"\bclass[- ]action\b", r"\blawsuit\b", r"\bsues\b", r"\bfiles suit\b", r"\bcomplaint against\b")),
    _t("litigation_settlement", "SMALL", 0,
       (r"\bsettles?\b.{0,25}\b(suit|lawsuit|dispute|claims)\b", r"\bsettlement of\b")),
    _t("management_change_departure", "SMALL", -1,
       (r"\b(ceo|cfo|coo|president)\b.{0,30}\b(steps down|resigns|departs|to leave|ousted)\b",
        r"\bresignation of\b"), (), (), ("8-K:5.02",)),
    _t("management_change_appointment", "SMALL", 0,
       (r"\bnames?\b.{0,30}\b(ceo|cfo|coo|chief)\b", r"\bappoints?\b.{0,30}\b(ceo|cfo|chief|director)\b",
        r"\bnew chief\b"), (), (), ("8-K:5.02",)),
    _t("auditor_or_accounting_change", "MODERATE", -1,
       (r"\brestate", r"\bauditor\b", r"\bmaterial weakness\b", r"\bnon-?reliance\b"),
       (), (), ("8-K:4.01", "8-K:4.02")),
    _t("cybersecurity_incident", "MODERATE", -1,
       (r"\bransomware\b", r"\bdata breach\b", r"\bcyber ?attack\b", r"\bhack(ed|ers)\b"),
       (), (), ("8-K:1.05",)),
    _t("insider_or_institutional_ownership_change", "NEGLIGIBLE", 0,
       (r"\b10b5-1\b", r"\binsider (buy|sell|trad)", r"\bstake in\b", r"\b13[dfg]\b",
        r"\bshort interest\b")),
    _t("macro_rate_decision", "MODERATE", 0,
       (r"\bfed(eral reserve)?\b.{0,30}\brate", r"\bfomc\b", r"\brate (hike|cut|decision)\b",
        r"\bbasis points?\b.{0,20}\brate")),
    _t("macro_inflation_print", "SMALL", 0, (r"\bcpi\b", r"\binflation\b", r"\bppi\b")),
    _t("macro_labor_report", "SMALL", 0,
       (r"\bnonfarm\b", r"\bjobs report\b", r"\bunemployment rate\b", r"\bjobless claims\b")),
    _t("tariff_or_trade_policy", "MODERATE", -1,
       (r"\btariff", r"\btrade (war|policy|deal)\b", r"\bexport controls?\b")),
    _t("sanction", "MODERATE", -1, (r"\bsanction", r"\bentity list\b", r"\bblacklist")),
    _t("index_rebalance", "SMALL", 0,
       (r"\bs&p 500\b.{0,30}\b(join|add|replac)", r"\bindex (addition|rebalance|inclusion)\b",
        r"\bto join the\b.{0,20}\bindex\b")),
)

TYPE_IDS: tuple[str, ...] = tuple(t.id for t in VOCABULARY)
NO_EVENT = "no_event"

_COMPILED = {t.id: t.rx() for t in VOCABULARY}
_TAG_TO_TYPES: dict[str, list[str]] = {}
for _t_ in VOCABULARY:
    for _tag in _t_.tags:
        _TAG_TO_TYPES.setdefault(_tag, []).append(_t_.id)


def _direction(spec: EventType, text: str) -> int:
    """A cue-word vote, never a reading. Ties and silence give the type's prior."""
    low = text.lower()
    up = sum(1 for w in spec.up if w in low)
    dn = sum(1 for w in spec.down if w in low)
    if up > dn:
        return 1
    if dn > up:
        return -1
    return int(spec.direction_prior)


def type_text(text: str, entity_tags=None) -> list[dict]:
    """The proxy extraction for ONE document. Deterministic, no model, no network.

    Returns [] for a document nothing matches -- which is `no_event`, and is the
    majority of any real corpus. `no_event` is not emitted as a row because a
    row per non-event would be 340,465 rows saying nothing; its information is
    carried by the absence of every count.
    """
    text = text or ""
    out: list[dict] = []
    seen = set()
    for tag in (entity_tags or []):
        for tid in _TAG_TO_TYPES.get(str(tag), []):
            if tid in seen:
                continue
            seen.add(tid)
            spec = next(t for t in VOCABULARY if t.id == tid)
            out.append({"event_type": tid, "direction": _direction(spec, text),
                        "magnitude_bucket": spec.magnitude_prior,
                        "confidence": 0.9, "basis": "entity_tag"})
    for spec in VOCABULARY:
        if spec.id in seen:
            continue
        hits = _COMPILED[spec.id].findall(text)
        if not hits:
            continue
        seen.add(spec.id)
        out.append({"event_type": spec.id, "direction": _direction(spec, text),
                    "magnitude_bucket": spec.magnitude_prior,
                    # a cue count, capped -- a PROXY for L2's confidence, and the
                    # receipt calls it that. It is monotone in evidence and
                    # nothing more.
                    "confidence": round(min(1.0, 0.5 + 0.1 * len(hits)), 3),
                    "basis": "keyword_proxy"})
    return out


def extract_events(df: pd.DataFrame, text_col: str = "text",
                   tags_col: str | None = None) -> pd.DataFrame:
    """Type every row of a panel. One row in, zero or more event rows out."""
    recs = []
    tags = df[tags_col].to_numpy() if (tags_col and tags_col in df.columns) else None
    syms = df["symbol"].to_numpy()
    dates = df["entry_date"].to_numpy()
    texts = df[text_col].to_numpy()
    for i in range(len(df)):
        for e in type_text(str(texts[i]), tags[i] if tags is not None else None):
            recs.append({"symbol": syms[i], "entry_date": dates[i], **e})
    if not recs:
        return pd.DataFrame(columns=["symbol", "entry_date", "event_type", "direction",
                                     "magnitude_bucket", "confidence", "basis"])
    ev = pd.DataFrame(recs)
    ev["magnitude"] = ev["magnitude_bucket"].map({b: i for i, b in enumerate(BUCKETS)}).astype(float)
    return ev


# ---------------------------------------------------------------------------
# the feature table
# ---------------------------------------------------------------------------
def build_features(cells: pd.DataFrame, ev: pd.DataFrame,
                   windows: tuple[int, ...] = WINDOWS,
                   min_occurrences: int = MIN_OCCURRENCES) -> tuple[pd.DataFrame, dict]:
    """One row per cell: one-hot type x direction, counts, magnitude, confidence, recency.

    Sessions are the panel's own distinct entry dates. Everything is computed by
    `searchsorted` inside a symbol's sorted event dates, so no window can reach
    past the cell's own session -- the arithmetic makes the PIT property, rather
    than a filter applied afterwards and hoped for.
    """
    sessions = np.array(sorted(pd.unique(cells["entry_date"])))
    sidx = np.searchsorted(sessions, cells["entry_date"].to_numpy())
    cells_sym = cells["symbol"].to_numpy()

    counts = ev["event_type"].value_counts() if len(ev) else pd.Series(dtype=int)
    kept = [t for t in TYPE_IDS if int(counts.get(t, 0)) >= min_occurrences]
    dropped = [t for t in TYPE_IDS if t not in kept]

    n = len(cells)
    cols: dict[str, np.ndarray] = {}
    for t in kept:
        for d in (-1, 0, 1):
            cols[f"evt_{t}_d{d}"] = np.zeros(n, dtype=np.float32)
        for w in windows:
            cols[f"cnt_{t}_w{w}"] = np.zeros(n, dtype=np.float32)
        cols[f"mag_{t}"] = np.full(n, np.nan, dtype=np.float32)
        cols[f"conf_{t}"] = np.full(n, np.nan, dtype=np.float32)
        cols[f"rec_{t}"] = np.full(n, float(RECENCY_CENSOR), dtype=np.float32)
        cols[f"rec_{t}_censored"] = np.ones(n, dtype=np.float32)

    if len(ev):
        ev = ev[ev["event_type"].isin(kept)].copy()
        ev["sidx"] = np.searchsorted(sessions, ev["entry_date"].to_numpy())
        by_cell = {}
        for sym, grp in pd.DataFrame({"i": np.arange(n), "symbol": cells_sym,
                                      "sidx": sidx}).groupby("symbol", sort=False):
            by_cell[sym] = (grp["i"].to_numpy(), grp["sidx"].to_numpy())
        for (sym, t), grp in ev.groupby(["symbol", "event_type"], sort=False):
            target = by_cell.get(sym)
            if target is None:
                continue
            idx, csi = target
            g = grp.sort_values("sidx")
            es = g["sidx"].to_numpy()
            hi = np.searchsorted(es, csi, side="right")          # events with sidx <= cell date
            for w in windows:
                lo = np.searchsorted(es, csi - w + 1, side="left")
                cols[f"cnt_{t}_w{w}"][idx] = (hi - lo).astype(np.float32)
            same = hi - np.searchsorted(es, csi, side="left")     # the cell's own session
            has = same > 0
            if has.any():
                dirs = g["direction"].to_numpy()
                mags = g["magnitude"].to_numpy(dtype=float)
                confs = g["confidence"].to_numpy(dtype=float)
                for j in np.nonzero(has)[0]:
                    a = np.searchsorted(es, csi[j], side="left")
                    b = hi[j]
                    dd = dirs[a:b]
                    for d in (-1, 0, 1):
                        if (dd == d).any():
                            cols[f"evt_{t}_d{d}"][idx[j]] = 1.0
                    cols[f"mag_{t}"][idx[j]] = float(np.mean(mags[a:b]))
                    cols[f"conf_{t}"][idx[j]] = float(np.mean(confs[a:b]))
            prev = hi - 1
            seen_before = prev >= 0
            if seen_before.any():
                gap = csi[seen_before] - es[prev[seen_before]]
                cols[f"rec_{t}"][idx[seen_before]] = np.minimum(gap, RECENCY_CENSOR).astype(np.float32)
                cols[f"rec_{t}_censored"][idx[seen_before]] = 0.0

    X = pd.DataFrame(cols, index=cells.index)
    meta = {
        "kept_types": kept, "dropped_sparse_types": dropped,
        "min_occurrences": int(min_occurrences),
        "windows_sessions": list(windows),
        "n_event_rows": int(len(ev)),
        "n_feature_columns": int(X.shape[1]),
        "recency_censor_sessions": RECENCY_CENSOR,
        "proxy": ("typed by entity_tags where present and otherwise by a KEYWORD proxy over the "
                  "39-id vocabulary's own definitions and example headlines -- NOT by L2, which "
                  "is not built"),
    }
    return X, meta


def price_columns(cells: pd.DataFrame) -> pd.DataFrame:
    """N3's three PIT price features, same definitions, same shift-by-1."""
    return pd.DataFrame({
        "pit_dv_21_log10": np.log10(np.maximum(cells["pit_dv_21"].to_numpy(dtype=float), 1.0)),
        "mom_21": cells["mom_21"].to_numpy(dtype=float),
        "mom_5": cells["mom_5"].to_numpy(dtype=float),
    }, index=cells.index)


# ---------------------------------------------------------------------------
# the two models
# ---------------------------------------------------------------------------
def fit_predict_gbm(Xtr: pd.DataFrame, ytr: np.ndarray, Xte: pd.DataFrame,
                    seed: int = 20260910) -> tuple[np.ndarray, dict]:
    """THE MANDATORY CONTROL (Lane M item M5). NaN-native; nothing is imputed."""
    import lightgbm as lgb
    from learner.models import LGBM_PARAMS

    params = dict(LGBM_PARAMS)
    params["random_state"] = int(seed)
    m = lgb.LGBMRegressor(**params)
    m.fit(Xtr, ytr)
    return np.asarray(m.predict(Xte), dtype=float), {
        "model": "LightGBM", "n_estimators": params["n_estimators"],
        "num_leaves": params["num_leaves"], "params_source": "learner.models.LGBM_PARAMS"}


def stockmixer_available() -> bool:
    try:
        import torch                                             # noqa: F401
    except ImportError:
        return False
    return True


def fit_predict_stockmixer(Xtr: pd.DataFrame, ytr: np.ndarray, dates_tr: np.ndarray,
                           Xte: pd.DataFrame, dates_te: np.ndarray,
                           seed: int = 20260910, epochs: int = 12,
                           hidden: int = 96, dropout: float = 0.15,
                           min_names: int = 20) -> tuple[np.ndarray, dict]:
    """`StockMixer_T1` -- NOT the paper's StockMixer, and the name says so.

    Wang et al., "StockMixer: A Simple yet Strong MLP-Based Architecture for
    Stock Price Forecasting", AAAI 2024 (DOI 10.1609/aaai.v38i8.28681), mixes
    three ways over `X in R^(N x T x F)`: indicator (over F), time (over T),
    stock (over N). E1's table is cross-sectional per date, so **T = 1 and
    time-mixing DEGENERATES TO A NO-OP**. What is left is indicator-mixing (an
    MLP over features) plus stock-mixing (an MLP over the names present that
    date). That is a deliberate simplification, not an implementation of the
    paper, and any result from it is a result about the degenerate variant.

    Stock-mixing over a variable N is done as the paper's market-aware term
    rather than a fixed N x N matrix: each name sees the date's mean mixed
    representation. A fixed N x N matrix cannot exist here -- the cross-section
    is 200-800 names and changes every session.
    """
    import torch
    from torch import nn

    torch.manual_seed(int(seed))
    dev = "cpu"                       # the batch is one date; the GPU is for the encoder
    med = Xtr.median(numeric_only=True)
    mu = Xtr.fillna(med).mean()
    sd = Xtr.fillna(med).std().replace(0.0, 1.0)

    def prep(X):
        return torch.tensor(((X.fillna(med) - mu) / sd).to_numpy(dtype=np.float32))

    Ztr, Zte = prep(Xtr), prep(Xte)
    ytr_t = torch.tensor(np.asarray(ytr, dtype=np.float32))
    ys = float(ytr_t.std() or 1.0)
    ytr_t = ytr_t / ys
    F = Ztr.shape[1]

    class Mixer(nn.Module):
        def __init__(self):
            super().__init__()
            self.indicator = nn.Sequential(nn.Linear(F, hidden), nn.GELU(), nn.Dropout(dropout),
                                           nn.Linear(hidden, hidden), nn.GELU())
            self.stock = nn.Sequential(nn.Linear(hidden, hidden), nn.GELU())
            self.head = nn.Linear(2 * hidden, 1)

        def forward(self, x):
            h = self.indicator(x)                       # indicator mixing (over F)
            m = self.stock(h.mean(dim=0, keepdim=True)).expand_as(h)   # stock mixing (over N)
            return self.head(torch.cat([h, m], dim=1)).squeeze(-1)

    net = Mixer().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.MSELoss()

    d_tr = pd.Series(dates_tr)
    groups = [np.nonzero((d_tr == d).to_numpy())[0] for d in pd.unique(d_tr)]
    groups = [g for g in groups if len(g) >= min_names]
    rng = np.random.default_rng(seed)
    losses = []
    net.train(True)
    for _ in range(int(epochs)):
        order = rng.permutation(len(groups))
        tot = 0.0
        for gi in order:
            g = groups[gi]
            opt.zero_grad()
            out = net(Ztr[g])
            loss = lossf(out, ytr_t[g])
            loss.backward()
            opt.step()
            tot += float(loss.item())
        losses.append(round(tot / max(1, len(groups)), 6))

    net.train(False)
    preds = np.zeros(len(Zte), dtype=float)
    d_te = pd.Series(dates_te)
    with torch.no_grad():
        for d in pd.unique(d_te):
            g = np.nonzero((d_te == d).to_numpy())[0]
            preds[g] = net(Zte[g]).numpy().astype(float)
    return preds, {"model": "StockMixer_T1", "hidden": hidden, "dropout": dropout,
                   "epochs": int(epochs), "n_features": int(F),
                   "train_loss_by_epoch": losses,
                   "degeneracy": ("T=1, so the paper's time-mixing is a no-op; only "
                                  "indicator-mixing and a market-aware stock-mixing term run")}
