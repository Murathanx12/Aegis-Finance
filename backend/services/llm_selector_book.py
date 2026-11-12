"""The LLM selector book: one LLM book the CH-11 ruler can grade from day one.

    python -m scripts.llm_selector_book --dry-run --out <dir>    # read-only, no call
    python -m scripts.llm_selector_book --decide --out <dir>     # ONE decision (flag on)

WHY THIS EXISTS (CH-17 "Human+AI" mandate + CH-11 matched twins, 2026-11-12)
============================================================================
Every LLM book the programme holds (`llm_portfolio/books.jsonl`: the Fable
"human_ai_thematic" drafts, the DeepSeek `pers_*`/`comp_*` personas, the
thesis-card book, the Opus reviewer) is ONE portfolio decided once on
2026-09-25 and frozen since. Each was chosen from a different candidate set
(a 160-name evidence pack, the card population plus human edits, ...), so the
ruler can only say "this frozen list sat in the bottom tail of its band twins";
it cannot say whether the LLM chose WELL FROM WHAT IT WAS OFFERED.

This book is built so that question has an answer:

* the LLM chooses from the SAME candidate set the ranker book sees that day
  (the opportunity funnel's final list, ranker order; plus the CH-14a
  `added_by_source` block exactly when `FUNNEL_NEWS_SOURCE_ENABLED` is on);
* it sees a frozen information packet per name in which EVERY fact carries a
  stamp and is admitted only when the stamp is strictly before the decision
  time (a fact without a stamp is a refusal, never a default);
* it returns k names, each with a stated direction and a one-line reason;
* its two twins are frozen beside it on the same date: (i) the SELECTION twin,
  k names drawn by `np.random.default_rng(seed)` from the same candidate set,
  and (ii) the INCUMBENT, the ranker's own top-k. Beating (i) means the LLM's
  choice added something over chance within the offered set; beating (ii)
  means it added something over the machinery we already have.

The book engine is `llm_portfolio` (freeze -> grade, entry at the first
session strictly after the decision date, band costs charged on entry). This
module does not grade and does not hold positions; it freezes three books.

AUTHORITY: NONE. Licence PRODUCT_EXPERIMENT, internal simulation only. Nothing
here sends an order, calls a broker or sizes real capital; the LLM's output is
a list of tickers that becomes a paper book record.

PROVIDER: DeepSeek through `model_provider.complete("deepseek", ...)`, which
reserves every call against `provider_budget` (`guarded_send`) and applies the
central language pin and the non-English refusal. `llm_analyzer._call_llm` is
NOT used because it returns `None` on a budget refusal, and a budget refusal
here must be a red non-zero exit, distinguishable from a provider outage.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend import config as C

SCHEMA = "llm_selector_book/1"
BOOK_NAME = "llm_selector_v0"
NY = ZoneInfo("America/New_York")

#: The frozen contract lives with the code (NOT under backend/data/optimus,
#: which release clones junction into the live data folder).
CONTRACT_PATH = (Path(__file__).resolve().parents[1] / "strategy" / "contracts"
                 / "CONTRACT_LLM_SELECTOR_v0.json")

# ── refusal codes -> exit codes ─────────────────────────────────────────────
FLAG_OFF = "FLAG_OFF"
INPUT_MISSING = "INPUT_MISSING"
CANDIDATES_STALE = "CANDIDATES_STALE"
CANDIDATES_UNDATEABLE = "CANDIDATES_UNDATEABLE"
CANDIDATES_EMPTY = "CANDIDATES_EMPTY"
UNSTAMPED_FIELD = "UNSTAMPED_FIELD"
BAD_REPLY = "BAD_REPLY"
OUT_OF_SET = "OUT_OF_SET"
WRONG_K = "WRONG_K"
DUPLICATE_PICK = "DUPLICATE_PICK"
BAD_DIRECTION = "BAD_DIRECTION"
MISSING_REASON = "MISSING_REASON"
BAD_SHAPE = "BAD_SHAPE"
BAD_REASON = "BAD_REASON"
REASON_NOT_ENGLISH = "REASON_NOT_ENGLISH"
TOO_FEW_CANDIDATES = "TOO_FEW_CANDIDATES"
ALREADY_DECIDED = "ALREADY_DECIDED"
ALREADY_REGISTERED = "ALREADY_REGISTERED"
NOTHING_TO_REGISTER = "NOTHING_TO_REGISTER"
NOW_NOT_ALLOWED = "NOW_NOT_ALLOWED"
BACKDATED = "BACKDATED"
BUDGET_REFUSED = "BUDGET_REFUSED"
PROVIDER_REFUSED = "PROVIDER_REFUSED"
CONTRACT_DRIFT = "CONTRACT_DRIFT"

#: Reply defects: the whole decision is refused, the reply is KEPT on the
#: refusal row (its tokens were paid for) and counted. Never repaired.
REPLY_DEFECTS = (BAD_REPLY, BAD_SHAPE, OUT_OF_SET, WRONG_K, DUPLICATE_PICK, BAD_DIRECTION,
                 MISSING_REASON, BAD_REASON, REASON_NOT_ENGLISH)

#: Bumped whenever the packet CODE changes (stamping, a fact's computation, a
#: source's admission rule). It is hashed into the contract, so a code change
#: that a prompt/parameter hash would not see is still a new contract.
PACKET_SCHEMA_VERSION = "llm_selector_packet/2"


def event_packet_on() -> bool:
    """CH-35 slice 2: the event-node block in each packet (default OFF)."""
    return bool(C.EVENT_NODES_SELECTOR_PACKET_ENABLED)


def packet_schema_version() -> str:
    """The packet schema in force: bumped ONLY when the event block is on, so the
    contract hash with the flag off is exactly main's."""
    return str(C.EVENT_NODES_SELECTOR_PACKET_SCHEMA) if event_packet_on() else PACKET_SCHEMA_VERSION

#: The funnel fields copied into a packet (hashed into the contract).
FUNNEL_FIELDS: tuple = ("sector", "market_cap", "quality", "mom_12_1", "vol_annual",
                        "median_dollar_vol", "analyst_upside", "n_analysts", "insider_score",
                        "price", "score", "stage")

#: A decision instant further than this from the wall clock is BACKDATED.
MAX_CLOCK_SKEW_S = 120

#: The ONE entry rule (prompt and contract say the same sentence).
ENTRY_RULE = ("entered at the open of the first trading session strictly after the New York "
              "calendar date of the decision time, so a decision made before the open on day D "
              "enters at the open of the next session after D, not at D's open")


def wall_clock() -> datetime:
    """The wall clock (a function so a test can pin it)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def flag_on() -> bool:
    """The flag: the config literal OR the env var `AEGIS_LLM_SELECTOR_BOOK`
    (read at call time), so one run can be enabled without editing a file."""
    import os
    env = os.getenv("AEGIS_LLM_SELECTOR_BOOK", "").strip().lower()
    return bool(C.LLM_SELECTOR_BOOK_ENABLED) or env in ("1", "true", "yes", "on")

EXIT_CODES = {FLAG_OFF: 4, BUDGET_REFUSED: 3}
EXIT_REFUSED = 2


class SelectorRefused(RuntimeError):
    """A refusal of the selector book. `code` is one of the constants above;
    `exit_code` is the CLI's non-zero exit for it."""

    def __init__(self, code: str, detail: str = "", **extra: Any) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.extra = extra

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.code, EXIT_REFUSED)


# ── hashing / stamps ────────────────────────────────────────────────────────

def sha16(obj: Any) -> str:
    raw = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_stamp(ts: Any) -> Optional[datetime]:
    """A zoned UTC instant, or None. A date-only value (or an exact midnight)
    is NOT a time: it is read as knowable at the END of that UTC day, the
    conservative reading (an analyst action dated D may be from D's afternoon)."""
    if ts is None or (isinstance(ts, float) and math.isnan(ts)):
        return None
    try:
        t = pd.Timestamp(ts)
    except (ValueError, TypeError):
        return None
    if t is pd.NaT or pd.isna(t):
        return None
    date_only = isinstance(ts, (str,)) and len(str(ts).strip()) <= 10
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert("UTC")
    if date_only or (t.hour == 0 and t.minute == 0 and t.second == 0 and t.microsecond == 0):
        t = t.normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59)
    return t.to_pydatetime()


def iso(t: Optional[datetime]) -> Optional[str]:
    return None if t is None else t.astimezone(timezone.utc).isoformat(timespec="seconds")


def bar_stamp(d: Any) -> datetime:
    """When a daily bar dated `d` is knowable: 21:00 UTC that day, which is at
    or after the regular close in both EST (21:00Z) and EDT (20:00Z)."""
    day = pd.Timestamp(d).date()
    return datetime.combine(day, time(21, 0), tzinfo=timezone.utc)


def decision_date(decision_time: datetime) -> date:
    """The book's `asof`: the New York date of the decision instant. The book
    engine enters at the first session STRICTLY after it, at the open."""
    return decision_time.astimezone(NY).date()


def _language_pin() -> str:
    from backend.services import llm_language as L
    return L.LANGUAGE_PIN


def pinned_system(system: str) -> str:
    """The system prompt exactly as `model_provider.complete` sends it."""
    from backend.services import llm_language as L
    return L.pin(system)


# ── the contract ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are the selector of an internal SIMULATED paper book. You have no "
    "authority over money and no orders are sent. You will be given a list of "
    "candidate US stocks and, for each, a packet of facts. Every fact carries "
    "the time it became knowable; nothing after the decision time is included. "
    "Use ONLY the facts given; do not use anything you remember about these "
    "companies after the decision time, and do not invent prices, targets or "
    "events. Choose exactly {k} names from the candidate list for a holding "
    "period of {hold} trading sessions, equal weight, {entry_rule}, and charged "
    "the round-trip cost shown per name. Your book "
    "will be compared against {k} names drawn at random from the same list and "
    "against the first {k} names of the ranker's own order. Answer with JSON "
    "only, no prose before or after."
)

USER_TEMPLATE = (
    "Decision time (UTC): {decision_time}\n"
    "Allowed directions: {directions}\n"
    "Return exactly this JSON shape:\n"
    "{{\"picks\": [{{\"ticker\": \"<a ticker from the list>\", "
    "\"direction\": \"<one of the allowed directions>\", "
    "\"reason\": \"<one line, citing a fact in its packet>\"}}]}}\n"
    "with exactly {k} picks, no ticker twice, every ticker taken from the "
    "candidate list.\n\n"
    "Candidate list in the ranker's order ({n} names):\n{tickers}\n\n"
    "Packets (one per name; `facts` = [field, value, knowable_at, source]):\n{packets}\n"
)

#: Which packet fields exist and where each comes from. Part of the contract:
#: adding a field changes the contract hash.
PACKET_FIELDS: dict[str, str] = {
    "funnel.*": "the candidate's own funnel fields, stamped at the funnel's generated_at",
    "price.close/ret_5d/ret_21d/ret_63d/vol_63_annual/vs_52w_high/median_dollar_vol_63/liquidity_band/cost_bps_round_trip/n_bars":
        "daily bars dated before the decision, each bar stamped 21:00 UTC of its date",
    "revisions.revisions_Nd/net_raises_Nd/median_target_change_Nd":
        "analyst/target_revisions.parquet rows knowable before the decision: the LATER of event_date "
        "and the pull stamp (first_seen_utc, else pulled_at); date-only = end of day",
    "digest.theme": "world-digest themes naming the ticker (discovery_autopsy.digest_names), stamped by the digest file",
    "knowable.item": "news/filing corpus rows naming the ticker (discovery_autopsy.Corpus), stamped by the "
                     "LATER of first_seen_utc and a timed published_utc",
    "language": "digest themes and corpus titles above llm_language.NON_LATIN_BAR non-Latin script are left out",
    "source.added_by": "the CH-14a news/filing source that added the name (added_by_source block only)",
}


def contract_body() -> dict:
    """Everything that defines the book. Any change here changes the hash."""
    from backend.services import investment_committee as IC
    k = int(C.LLM_SELECTOR_K)
    body = {
        "name": BOOK_NAME, "schema": SCHEMA,
        "licence": "PRODUCT_EXPERIMENT",
        "authority": ("none: internal simulation book; the LLM has no authority over real "
                      "capital and none over order sending; nothing here calls a broker"),
        "provider": "deepseek", "call_path": "model_provider.complete -> provider_budget.guarded_send",
        "request_model": str(C.LLM_SELECTOR_MODEL),
        "max_tokens": int(C.LLM_SELECTOR_MAX_TOKENS),
        "temperature": float(C.LLM_SELECTOR_TEMPERATURE),
        "purpose": str(C.LLM_SELECTOR_PURPOSE),
        "k": k, "directions": list(C.LLM_SELECTOR_DIRECTIONS),
        "hold_sessions": int(C.LLM_SELECTOR_HOLD_SESSIONS),
        "cadence_sessions": int(C.LLM_SELECTOR_CADENCE_SESSIONS),
        "weights": "equal weight over the k picks, fully invested, CASH 0 declared",
        "candidate_set": {
            "source": "opportunity funnel final list (IC_FUNNEL_PATH `candidates`, ranker order)",
            "added_by_source": "the CH-14a `added_by_source` block, included iff FUNNEL_NEWS_SOURCE_ENABLED",
            "stale_limit_days": int(IC.FUNNEL_STALE_DAYS),
            "undateable": "refused",
        },
        "packet": {
            "fields": PACKET_FIELDS,
            "admission": "a fact is admitted iff its stamp is strictly before the decision time; "
                         "a fact without a parseable stamp refuses the packet",
            "revision_lookback_days": int(C.LLM_SELECTOR_REVISION_LOOKBACK_DAYS),
            "digest_lookback_days": int(C.LLM_SELECTOR_DIGEST_LOOKBACK_DAYS),
            "knowable_lookback_days": int(C.LLM_SELECTOR_KNOWABLE_LOOKBACK_DAYS),
            "max_items_per_name": int(C.LLM_SELECTOR_MAX_ITEMS_PER_NAME),
            "price_lookback_days": int(C.LLM_SELECTOR_PRICE_LOOKBACK_DAYS),
        },
        "packet_schema_version": packet_schema_version(),
        "funnel_fields": list(FUNNEL_FIELDS),
        "entry_rule": ENTRY_RULE,
        "prompts": {"system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE},
        "prompt_template_hash": sha16(SYSTEM_PROMPT + "\n" + USER_TEMPLATE),
        "language_pin_hash": sha16(_language_pin()),
        "prompt_hashes": ("prompt_hash = sha16(system AS SENT, i.e. with the central language pin, "
                          "+ newline + user); prompt_hash_rendered = the same without the pin"),
        "reply_contract": ("STRICT: the whole reply is exactly one JSON object {\"picks\": [...]} with no "
                           "prose or code fence; each pick has exactly the keys ticker, direction, "
                           "reason (strings); the ticker matches a candidate exactly after upper-casing "
                           "only (no trimming); the direction is exactly an allowed one; the reason is "
                           "one non-empty line of at most 300 characters, at most NON_LATIN_BAR "
                           "non-Latin script; any defect is a counted refusal of its class"),
        "min_candidates": "the candidate set must hold MORE than k names, else refused before the call",
        "one_decision_per_date": "a second decision for a decision_date already in decisions.jsonl is refused before the call",
        "reply_rule": ("exactly k picks, each ticker in the candidate set, no duplicate, an allowed "
                       "direction and a non-empty reason; any defect refuses the WHOLE decision, "
                       "the reply is kept on the refusal row and counted; never repaired"),
        "twins": {
            "selection": ("k names drawn without replacement from the same candidate set by "
                          "np.random.default_rng(seed), seed = LLM_SELECTOR_SEED_BASE + the decision "
                          "date's ordinal; seed and draw recorded"),
            "incumbent": "the ranker's own top-k: the first k names of the funnel candidate list",
        },
        "seed_base": int(C.LLM_SELECTOR_SEED_BASE),
        "costs": "llm_portfolio.grade charges xs_ranker.round_trip_bps by liquidity band on entry",
        "fill": "llm_portfolio.entry_session: " + ENTRY_RULE,
        "objective": ("terminal wealth over hold_sessions under the BALANCED personality, read as "
                      "excess over (i) the selection twin and (ii) the incumbent; the CH-11 ruler "
                      "(band twins, rank p with Holm, block t at every origin) grades the book"),
        "claims": "none: a PRODUCT_EXPERIMENT; no skill claim from this book's results",
    }
    if event_packet_on():
        body["packet"]["event_nodes"] = {
            "source": "event_nodes.nodes_known_at(store, decision_time): the latest version of each "
                      "node BUILT at or before the decision, retired nodes removed",
            "top_k": int(C.EVENT_NODES_SELECTOR_TOP_K),
            "max_age_hours": float(C.EVENT_NODES_CONSUMER_MAX_AGE_HOURS),
            "rank": "importance decayed to the decision time, highest first",
            "fields": ["event_id", "primary", "role", "link", "age_h", "importance", "n_publishers",
                       "dated_facts"],
            "no_text": "no title, body or URL (licensed text) is in the event block",
            "stamp": "the version's built_now_utc; admitted iff strictly before the decision",
        }
    return body


def contract_hash(body: Optional[dict] = None) -> str:
    return sha16(body if body is not None else contract_body())


def contract() -> dict:
    body = contract_body()
    return {**body, "contract_hash": contract_hash(body)}


def check_frozen(path: Optional[Path] = None) -> dict:
    """The committed contract must match the code. A prompt or parameter
    changed without re-freezing is CONTRACT_DRIFT, never a silent new policy."""
    p = Path(path) if path else CONTRACT_PATH
    if not p.is_file():
        raise SelectorRefused(INPUT_MISSING, f"no frozen contract at {p}")
    frozen = json.loads(p.read_text(encoding="utf-8"))
    live = contract_hash()
    if frozen.get("contract_hash") != live:
        raise SelectorRefused(CONTRACT_DRIFT, f"frozen {frozen.get('contract_hash')} != code {live}; "
                              "a changed prompt or parameter is a NEW contract (v1), not an edit")
    return frozen


# ── the candidate set ───────────────────────────────────────────────────────

def candidate_set(funnel: dict, *, now: datetime, include_added: Optional[bool] = None,
                  limit_days: Optional[int] = None) -> dict:
    """The ranker's final list (order kept) + optionally the added block.
    Refuses an undateable, stale or empty snapshot (never used silently)."""
    from backend.services import investment_committee as IC
    lim = int(IC.FUNNEL_STALE_DAYS if limit_days is None else limit_days)
    gen = parse_stamp(funnel.get("generated_at"))
    if gen is None or len(str(funnel.get("generated_at") or "")) <= 10:
        raise SelectorRefused(CANDIDATES_UNDATEABLE,
                              f"funnel generated_at {funnel.get('generated_at')!r} is not a time")
    age_days = (now - gen).total_seconds() / 86400.0
    if age_days > lim:
        raise SelectorRefused(CANDIDATES_STALE, f"funnel generated {iso(gen)} is {age_days:.1f} days "
                              f"old at {iso(now)}; limit {lim} days", age_days=round(age_days, 2))
    if gen >= now:
        raise SelectorRefused(CANDIDATES_UNDATEABLE, f"funnel generated {iso(gen)} is not before {iso(now)}")
    ranked = []
    for c in funnel.get("candidates") or []:
        t = str(c.get("ticker") or "").strip().upper()
        if t and t not in {r["ticker"] for r in ranked}:
            ranked.append({"ticker": t, "row": c, "origin": "ranker"})
    if not ranked:
        raise SelectorRefused(CANDIDATES_EMPTY, "funnel snapshot carries no candidates")
    inc = bool(C.FUNNEL_NEWS_SOURCE_ENABLED if include_added is None else include_added)
    added = []
    if inc:
        blk = funnel.get("added_by_source")
        rows = blk.get("added") if isinstance(blk, dict) else blk
        seen = {r["ticker"] for r in ranked}
        for a in rows or []:
            t = str(a.get("ticker") or "").strip().upper()
            if t and t not in seen:
                seen.add(t)
                added.append({"ticker": t, "row": a, "origin": "added_by_source"})
    members = ranked + added
    tickers = [m["ticker"] for m in members]
    return {"generated_at": iso(gen), "generated_dt": gen, "age_days": round(age_days, 3),
            "limit_days": lim, "n_ranked": len(ranked), "n_added": len(added),
            "added_by_source_included": inc, "tickers": tickers,
            "ranked": [m["ticker"] for m in ranked], "members": members,
            "candidate_set_hash": sha16({"generated_at": iso(gen), "tickers": tickers})}


# ── facts and packets ───────────────────────────────────────────────────────

def fact(field: str, value: Any, stamp: Any, source: str) -> dict:
    return {"field": field, "value": value, "stamp": stamp, "source": source}


def _num(v: Any, nd: int = 4) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, nd)


def admit(facts: Iterable[dict], decision_time: datetime) -> tuple[list[dict], int]:
    """(admitted, n_excluded_at_or_after). A fact with no parseable stamp
    REFUSES -- an unstamped value cannot be shown to precede the decision."""
    keep, n_future = [], 0
    for f in facts:
        st = parse_stamp(f.get("stamp"))
        if st is None:
            raise SelectorRefused(UNSTAMPED_FIELD, f"field {f.get('field')!r} from {f.get('source')!r} "
                                  f"has no usable stamp ({f.get('stamp')!r})")
        if st >= decision_time:
            n_future += 1
            continue
        keep.append({**f, "stamp": iso(st)})
    return keep, n_future


def funnel_facts(member: dict, generated_at: str) -> list[dict]:
    row = member["row"]
    out = []
    for k in FUNNEL_FIELDS:
        v = row.get(k)
        if v is None:
            continue
        out.append(fact(f"funnel.{k}", v if isinstance(v, str) else _num(v), generated_at, "funnel"))
    if member["origin"] == "added_by_source":
        for s in row.get("sources") or []:
            out.append(fact("source.added_by", str(s), row.get("first_seen_utc") or row.get("as_of")
                            or generated_at, "funnel.added_by_source"))
        if row.get("net_direction"):
            out.append(fact("source.net_direction", str(row["net_direction"]),
                            row.get("first_seen_utc") or row.get("as_of") or generated_at,
                            "funnel.added_by_source"))
    return out


def price_facts(bars: pd.DataFrame, ticker: str, decision_time: datetime) -> list[dict]:
    """Facts from bars knowable before the decision (each bar stamped at its close)."""
    from backend.services import xs_ranker as XR
    if bars is None or bars.empty:
        return []
    g = bars[bars["symbol"] == ticker]
    if g.empty:
        return []
    g = g.sort_values("date")
    stamps = g["date"].map(bar_stamp)
    g = g[stamps < decision_time]
    if g.empty:
        return []
    c = g["close"].astype(float).to_numpy()
    v = g["volume"].astype(float).to_numpy()
    st = iso(bar_stamp(g["date"].iloc[-1]))
    mdv = float(np.median((c * v)[-63:])) if len(c) else None

    def ret(n: int) -> Optional[float]:
        return _num(c[-1] / c[-1 - n] - 1.0) if len(c) > n and c[-1 - n] > 0 else None

    lr = np.diff(np.log(c[-64:])) if len(c) >= 22 else np.array([])
    vol = _num(float(np.std(lr, ddof=1)) * math.sqrt(252)) if lr.size >= 20 else None
    hi = float(np.max(c[-252:]))
    out = [fact("price.close", _num(c[-1], 2), st, "bars"),
           fact("price.n_bars", int(len(c)), st, "bars"),
           fact("price.ret_5d", ret(5), st, "bars"),
           fact("price.ret_21d", ret(21), st, "bars"),
           fact("price.ret_63d", ret(63), st, "bars"),
           fact("price.vol_63_annual", vol, st, "bars"),
           fact("price.vs_52w_high", _num(c[-1] / hi - 1.0) if hi > 0 else None, st, "bars")]
    if mdv is not None and np.isfinite(mdv):
        out += [fact("price.median_dollar_vol_63", _num(mdv / 1e6, 2), st, "bars"),
                fact("price.liquidity_band", XR.liquidity_band(mdv), st, "bars"),
                fact("price.cost_bps_round_trip", round(float(XR.round_trip_bps(mdv)), 1), st, "bars")]
    return out


def revision_facts(rev: Optional[pd.DataFrame], ticker: str, decision_time: datetime,
                   lookback_days: int) -> list[dict]:
    """Analyst target revisions dated before the decision. Each aggregate is
    stamped with the latest event it uses."""
    if rev is None or rev.empty:
        return []
    d = rev[rev["ticker"].astype(str).str.upper() == ticker]
    if d.empty:
        return []
    ev = d["event_date"].map(parse_stamp)
    pull_col = next((c for c in ("first_seen_utc", "pulled_at") if c in d.columns), None)
    if pull_col is not None:
        pulled = d[pull_col].map(parse_stamp)
        if pull_col == "first_seen_utc" and "pulled_at" in d.columns:
            pulled = [a if a is not None else parse_stamp(b)
                      for a, b in zip(pulled, d["pulled_at"])]
        st = [max(a, b) if (a is not None and b is not None) else a
              for a, b in zip(ev, pulled)]
    else:
        st = list(ev)
    d = d.assign(_st=st)
    d = d[d["_st"].notna()]
    d = d[(d["_st"] < decision_time) & (d["_st"] >= decision_time - timedelta(days=lookback_days))]
    if d.empty:
        return []
    ta = d["target_action"].astype(str).str.lower()
    stamp = iso(max(d["_st"]))
    n = int(lookback_days)
    med = d["target_change"].median() if "target_change" in d.columns else None
    return [fact(f"revisions.revisions_{n}d", int(len(d)), stamp, "analyst/target_revisions"),
            fact(f"revisions.net_raises_{n}d", int((ta == "raises").sum() - (ta == "lowers").sum()),
                 stamp, "analyst/target_revisions"),
            fact(f"revisions.median_target_change_{n}d", _num(med), stamp, "analyst/target_revisions")]


def latin_only(text: str) -> bool:
    """A non-English title in the packet invites a non-English reply, which the
    central language contract then refuses (a paid, wasted call). Such titles
    are left out of the packet, by the same bar the reply is judged by."""
    from backend.services import llm_language as L
    return L.non_latin_share(text) <= L.NON_LATIN_BAR


def digest_facts(by_ticker: dict, ticker: str, max_items: int) -> list[dict]:
    rows = [r for r in by_ticker.get(ticker, []) if latin_only(str(r.get("theme") or ""))]
    rows = sorted(rows, key=lambda r: str(r.get("stamp")))[-max_items:]
    return [fact("digest.theme", str(r.get("theme") or "")[:160], r.get("stamp"), "world_digest")
            for r in rows]


def knowable_stamp(r: dict) -> Any:
    """The LATER of the corpus row's first-seen and (timed) publication stamps."""
    cands = [parse_stamp(r.get("first_seen_utc_raw")), parse_stamp(r.get("known_at"))]
    pub = r.get("published_at")
    if pub is not None:
        cands.append(parse_stamp(pub))
    cands = [c for c in cands if c is not None]
    return max(cands) if cands else None


def knowable_facts(by_ticker: dict, ticker: str, max_items: int) -> list[dict]:
    rows = [r for r in by_ticker.get(ticker, []) if latin_only(str(r.get("title") or ""))]
    rows = sorted(rows, key=lambda r: str(knowable_stamp(r)))[-max_items:]
    return [fact("knowable.item", f"[{r.get('source')}] {str(r.get('title') or '')[:200]}",
                 knowable_stamp(r), "news_corpus") for r in rows]


def event_facts(by_ticker: dict, ticker: str) -> list[dict]:
    """The top-K event nodes for `ticker` (event_nodes.events_for, already ranked by
    importance decayed to the decision). Ids, roles, counts and stamps only."""
    out = []
    for b in (by_ticker.get(ticker) or [])[:int(C.EVENT_NODES_SELECTOR_TOP_K)]:
        out.append(fact("event_node", {"event_id": b["event_id"], "primary": b["primary_ticker"],
                                       "role": b["role"], "link": b["link"], "age_h": b["age_hours"],
                                       "importance": b["importance_at"], "n_publishers": b["n_publishers"],
                                       "dated_facts": b["dated_facts_filled"]},
                        b["version_built_utc"], "event_nodes"))
    return out


def build_packet(ticker: str, facts: list[dict], decision_time: datetime) -> dict:
    kept, n_future = admit(facts, decision_time)
    kept = sorted(kept, key=lambda f: (f["field"], f["stamp"], str(f["value"])))
    body = {"ticker": ticker, "decision_time": iso(decision_time),
            "facts": [[f["field"], f["value"], f["stamp"], f["source"]] for f in kept]}
    return {**body, "n_excluded_at_or_after_decision": n_future, "packet_hash": sha16(body)}


def packets_hash(packets: list[dict]) -> str:
    return sha16([p["packet_hash"] for p in packets])


# ── the prompt, the reply, the twins ────────────────────────────────────────

def render(cset: dict, packets: list[dict], decision_time: datetime) -> tuple[str, str]:
    k, hold = int(C.LLM_SELECTOR_K), int(C.LLM_SELECTOR_HOLD_SESSIONS)
    system = SYSTEM_PROMPT.format(k=k, hold=hold, entry_rule=ENTRY_RULE)
    compact = [{"ticker": p["ticker"], "facts": p["facts"]} for p in packets]
    user = USER_TEMPLATE.format(
        decision_time=iso(decision_time), directions=", ".join(C.LLM_SELECTOR_DIRECTIONS),
        k=k, n=len(cset["tickers"]), tickers=", ".join(cset["tickers"]),
        packets="\n".join(json.dumps(c, separators=(",", ":"), default=str) for c in compact))
    return system, user


def parse_reply(text: str, *, tickers: list[str], k: int, directions: Iterable[str]) -> list[dict]:
    """STRICT validation (see the contract's `reply_contract`). Nothing is
    repaired: any defect refuses the whole decision with its class."""
    from backend.services import llm_language as L
    raw = text if isinstance(text, str) else ""
    body = raw.strip()
    if not (body.startswith("{") and body.endswith("}")):
        raise SelectorRefused(BAD_REPLY, "reply is not exactly one JSON object (prose or a code fence around it)")
    try:
        obj = json.loads(body)
    except ValueError as exc:
        raise SelectorRefused(BAD_REPLY, f"reply is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict) or set(obj) != {"picks"} or not isinstance(obj["picks"], list):
        raise SelectorRefused(BAD_SHAPE, f"top level must be exactly {{'picks': [...]}}; got keys "
                              f"{sorted(obj) if isinstance(obj, dict) else type(obj).__name__}")
    allowed = set(directions)
    universe = set(tickers)
    clean, seen, outside = [], set(), []
    for p in obj["picks"]:
        if not isinstance(p, dict) or set(p) != {"ticker", "direction", "reason"}:
            raise SelectorRefused(BAD_SHAPE, f"a pick must have exactly ticker, direction, reason: {p!r}"[:300])
        if not all(isinstance(p[x], str) for x in ("ticker", "direction", "reason")):
            raise SelectorRefused(BAD_SHAPE, f"pick fields must be strings: {p!r}"[:300])
        t = p["ticker"].upper()
        if t not in universe:
            outside.append(p["ticker"])
            continue
        if t in seen:
            raise SelectorRefused(DUPLICATE_PICK, f"{t} picked twice")
        seen.add(t)
        if p["direction"] not in allowed:
            raise SelectorRefused(BAD_DIRECTION, f"{t} direction {p['direction']!r} not in {sorted(allowed)}")
        reason = p["reason"]
        if not reason.strip():
            raise SelectorRefused(MISSING_REASON, f"{t} has no reason")
        if "\n" in reason or "\r" in reason or len(reason) > 300:
            raise SelectorRefused(BAD_REASON, f"{t} reason is not one line of <= 300 characters")
        if L.non_latin_share(reason) > L.NON_LATIN_BAR:
            raise SelectorRefused(REASON_NOT_ENGLISH,
                                  f"{t} reason is {L.non_latin_share(reason):.0%} non-Latin script")
        clean.append({"ticker": t, "direction": p["direction"], "reason": reason})
    if outside:
        raise SelectorRefused(OUT_OF_SET, f"{len(outside)} pick(s) outside the candidate set: {outside[:10]}",
                              outside=outside)
    if len(clean) != k:
        raise SelectorRefused(WRONG_K, f"{len(clean)} picks, contract k = {k}")
    return clean


def entry_session(decision_time: datetime) -> str:
    """The session the book enters at (its open), by the engine's own rule."""
    from backend.services import llm_portfolio as LP
    return str(LP.entry_session(str(decision_date(decision_time))).date())


def selection_seed(day: date) -> int:
    return int(C.LLM_SELECTOR_SEED_BASE) + day.toordinal()


def selection_twin(tickers: list[str], k: int, seed: int) -> list[str]:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(tickers), size=min(k, len(tickers)), replace=False)
    return [tickers[int(i)] for i in idx]


def incumbent_twin(ranked: list[str], k: int) -> list[str]:
    return list(ranked[:k])


# ── one decision ────────────────────────────────────────────────────────────

Complete = Callable[[str, str], Any]


def _default_complete(system: str, user: str) -> Any:
    from backend.services import model_provider as MP
    return MP.complete("deepseek", user, system=system, model=str(C.LLM_SELECTOR_MODEL),
                       max_tokens=int(C.LLM_SELECTOR_MAX_TOKENS),
                       temperature=float(C.LLM_SELECTOR_TEMPERATURE),
                       purpose=str(C.LLM_SELECTOR_PURPOSE))


def _call(complete: Complete, system: str, user: str) -> Any:
    from backend.services import model_provider as MP
    try:
        return complete(system, user)
    except MP.BudgetRefusal as exc:
        raise SelectorRefused(BUDGET_REFUSED, str(exc)) from exc
    except MP.LanguageRefused as exc:
        raise SelectorRefused(PROVIDER_REFUSED, str(exc),
                              response=getattr(getattr(exc, "reply", None), "text", None)) from exc
    except MP.ProviderRefusal as exc:
        raise SelectorRefused(PROVIDER_REFUSED, str(exc)) from exc


def decision_context(cset: dict, packets: list[dict], decision_time: datetime) -> dict:
    return {"schema": SCHEMA, "book": BOOK_NAME, "contract_hash": contract_hash(),
            "decision_time": iso(decision_time), "decision_date": str(decision_date(decision_time)),
            "candidate_set_hash": cset["candidate_set_hash"], "packet_hash": packets_hash(packets),
            "request_model": str(C.LLM_SELECTOR_MODEL)}


def decide(cset: dict, packets: list[dict], decision_time: datetime, *,
           complete: Optional[Complete] = None) -> dict:
    """One LLM decision -> the decision row (raises SelectorRefused on any
    defect; every refusal carries the decision context in `.extra`)."""
    k = int(C.LLM_SELECTOR_K)
    system, user = render(cset, packets, decision_time)
    base = {**decision_context(cset, packets, decision_time),
            "prompt_hash": sha16(pinned_system(system) + "\n" + user),
            "prompt_hash_rendered": sha16(system + "\n" + user)}
    try:
        if len(cset["tickers"]) <= k:
            raise SelectorRefused(TOO_FEW_CANDIDATES, f"{len(cset['tickers'])} candidates; the contract "
                                  f"needs more than k = {k} (a selection from k names is no selection)")
        reply = _call(complete or _default_complete, system, user)
        text = getattr(reply, "text", reply)
        acct = getattr(reply, "budget_accounting", None) or {}
        served = {"reply_model_label": getattr(reply, "model", None),
                  "served_model": getattr(reply, "served_model", None),
                  "reservation_id": acct.get("reservation_id"),
                  "billing_status": acct.get("billing_status")}
        try:
            picks = parse_reply(text, tickers=cset["tickers"], k=k, directions=C.LLM_SELECTOR_DIRECTIONS)
        except SelectorRefused as exc:
            exc.extra.update({**served, "response": text, "cost_usd": acct.get("cost_usd")})
            raise
    except SelectorRefused as exc:
        exc.extra = {**base, **exc.extra}
        raise
    day = decision_date(decision_time)
    seed = selection_seed(day)
    return {**base, **served, "model_id": served["served_model"] or "SERVED_MODEL_NOT_REPORTED",
            "response": text, "picks": picks, "entry_session": entry_session(decision_time),
            "entry_rule": ENTRY_RULE,
            "candidate_set": {"generated_at": cset["generated_at"], "age_days": cset["age_days"],
                              "n_ranked": cset["n_ranked"], "n_added": cset["n_added"],
                              "added_by_source_included": cset["added_by_source_included"],
                              "tickers": cset["tickers"]},
            "packet_hashes": {p["ticker"]: p["packet_hash"] for p in packets},
            "twins": {"selection": {"seed": seed, "rng": "numpy.random.default_rng",
                                    "tickers": selection_twin(cset["tickers"], k, seed)},
                      "incumbent": {"tickers": incumbent_twin(cset["ranked"], k)}},
            "tokens": {"prompt": getattr(reply, "prompt_tokens", None),
                       "completion": getattr(reply, "completion_tokens", None)},
            "cost_usd": acct.get("cost_usd")}


def freeze_books(row: dict) -> list[dict]:
    """The LLM book and its two twins, frozen by the existing book engine."""
    from backend.services import llm_portfolio as LP
    day = row["decision_date"]
    k = len(row["picks"])
    falsifier = (f"trails the selection twin and the incumbent over "
                 f"{int(C.LLM_SELECTOR_HOLD_SESSIONS)} sessions")
    common = {"objective": "terminal wealth vs the selection twin and the ranker incumbent (balanced)",
              "horizon_days": [int(C.LLM_SELECTOR_HOLD_SESSIONS)], "benchmark": "SPY"}
    parent = LP.freeze({
        **common, "name": f"{BOOK_NAME}_{day}", "kind": "personal", "model": row["model_id"],
        "strategy": f"LLM selector over the funnel candidate set {row['candidate_set_hash']}; "
                    f"contract {row['contract_hash']}",
        "source": "llm_selector_book", "prompt_hash": row["prompt_hash"],
        "evidence_hash": row["packet_hash"],
        "positions": [{"ticker": p["ticker"], "weight": 1.0 / k, "thesis": p["reason"],
                       "falsifier": falsifier} for p in row["picks"]]
                     + [{"ticker": "CASH", "weight": 0.0, "thesis": "fully invested",
                         "falsifier": "n/a"}]}, today=day)
    out = [parent]
    for twin, names in (("selection_random_same_set", row["twins"]["selection"]["tickers"]),
                        ("incumbent_ranker_top_k", row["twins"]["incumbent"]["tickers"])):
        n = len(names)
        out.append(LP.freeze({
            **common, "name": f"{parent['name']}__{twin}", "kind": "twin", "twin": twin,
            "model": "twin", "parent_book_id": parent["book_id"], "parent_kind": "personal",
            "strategy": f"{twin} twin of {parent['book_id']}",
            "positions": [{"ticker": t, "weight": 1.0 / n, "thesis": twin} for t in names]},
            today=day))
    return out


# ── the ledger (written only with the flag on) ──────────────────────────────

def default_out_dir() -> Path:
    return Path(C.OPTIMUS_LEDGER_DIR) / "llm_selector"


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def refusal_counts(out_dir: Path) -> dict:
    p = Path(out_dir) / "refusals.jsonl"
    counts: dict[str, int] = {}
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line).get("code")
            except ValueError:
                continue
            counts[c] = counts.get(c, 0) + 1
    return counts


def record_refusal(out_dir: Path, exc: SelectorRefused, now: datetime) -> dict:
    row = {"schema": SCHEMA, "row_type": "refusal", "code": exc.code, "detail": exc.detail,
           "at": iso(now), **{k: v for k, v in exc.extra.items()},
           "written_utc": iso(wall_clock())}
    _append(Path(out_dir) / "refusals.jsonl", row)
    row["counts_after"] = refusal_counts(out_dir)
    return row


def decided_dates(out_dir: Path) -> set:
    p = Path(out_dir) / "decisions.jsonl"
    out: set = set()
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.add(json.loads(line).get("decision_date"))
            except ValueError:
                continue
    return out


def run_decision(*, cset: dict, packets: list[dict], decision_time: datetime, out_dir: Path,
                 complete: Optional[Complete] = None, enabled: Optional[bool] = None) -> dict:
    """Flag off -> refuse before anything is written. Flag on -> one decision
    row + three frozen books, or one counted refusal row. The decision instant
    must be the wall clock (a back-dated decision is not forward evidence), and
    one decision per decision_date (a second call would be a paid re-roll)."""
    on = flag_on() if enabled is None else bool(enabled)
    if not on:
        raise SelectorRefused(FLAG_OFF, "LLM_SELECTOR_BOOK_ENABLED / AEGIS_LLM_SELECTOR_BOOK are off; "
                              "nothing called, nothing written")
    check_frozen()
    wall = wall_clock()
    skew = abs((wall - decision_time).total_seconds())
    if skew > MAX_CLOCK_SKEW_S:
        raise SelectorRefused(BACKDATED, f"decision time {iso(decision_time)} is {skew:.0f} s from the "
                              f"wall clock {iso(wall)}; a decision is made NOW or not at all")
    day = str(decision_date(decision_time))
    if day in decided_dates(out_dir):
        exc = SelectorRefused(ALREADY_DECIDED, f"decisions.jsonl already holds decision_date {day}; "
                              "a second decision for the same date would be a paid re-roll",
                              **decision_context(cset, packets, decision_time))
        record_refusal(out_dir, exc, decision_time)
        raise exc
    try:
        row = decide(cset, packets, decision_time, complete=complete)
    except SelectorRefused as exc:
        if exc.code in REPLY_DEFECTS + (BUDGET_REFUSED, PROVIDER_REFUSED, TOO_FEW_CANDIDATES):
            record_refusal(out_dir, exc, decision_time)
        raise
    books = freeze_books(row)
    row["book_ids"] = {"llm": books[0]["book_id"], "selection": books[1]["book_id"],
                       "incumbent": books[2]["book_id"]}
    row["written_utc"] = iso(wall_clock())
    _append(Path(out_dir) / "decisions.jsonl", row)
    for b in books:
        _append(Path(out_dir) / "books.jsonl", b)
    return {"row": row, "books": books}


def register(*, selector_dir: Path, target: Path, decision_date_: str, dry_run: bool) -> dict:
    """Put one decision's three frozen books on the CH-11 ruler by appending
    them to `llm_portfolio/books.jsonl` (`target`). Idempotent: a book_id
    already in the target refuses (nothing written). `dry_run` prints only."""
    src = Path(selector_dir) / "books.jsonl"
    dec = [json.loads(x) for x in (Path(selector_dir) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
           if x.strip()] if (Path(selector_dir) / "decisions.jsonl").is_file() else []
    row = next((d for d in dec if d.get("decision_date") == decision_date_), None)
    if row is None or not src.is_file():
        raise SelectorRefused(NOTHING_TO_REGISTER, f"no decision for {decision_date_} in {selector_dir}")
    ids = set(row["book_ids"].values())
    books = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [b for b in books if b.get("book_id") in ids]
    if len(rows) != 3:
        raise SelectorRefused(NOTHING_TO_REGISTER, f"expected 3 books for {decision_date_}, found {len(rows)}")
    have = set()
    if Path(target).is_file():
        for line in Path(target).read_text(encoding="utf-8").splitlines():
            try:
                have.add(json.loads(line).get("book_id"))
            except ValueError:
                continue
    dup = sorted(ids & have)
    if dup:
        raise SelectorRefused(ALREADY_REGISTERED, f"{dup} already in {target}; nothing appended")
    lines = [json.dumps(b, default=str) for b in rows]
    if not dry_run:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        with Path(target).open("a", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(ln + "\n")
    return {"target": str(target), "dry_run": dry_run, "lines": lines, "book_ids": sorted(ids)}


# ── reading the live inputs (read-only) ─────────────────────────────────────

def paths(data_root: Path) -> dict:
    dr = Path(data_root)
    return {"funnel": dr.parent / "funnel_night10.json",
            "bars": dr / "prices_2025_26" / "bars.parquet",
            "revisions": dr / "analyst" / "target_revisions.parquet",
            "digest": dr / "digest", "corpus": dr / "news_corpus",
            "cik_map": dr / "official" / "company_tickers.json"}


def load_inputs(data_root: Path, decision_time: datetime, *,
                include_added: Optional[bool] = None, event_store: Optional[Path] = None) -> dict:
    """Read the funnel, bars (filtered to the candidates), revisions, digest
    and corpus. A missing funnel or bars panel is a refusal."""
    from backend.services import discovery_autopsy as DA
    p = paths(data_root)
    for key in ("funnel", "bars"):
        if not p[key].is_file():
            raise SelectorRefused(INPUT_MISSING, f"{key} missing at {p[key]}")
    funnel = json.loads(p["funnel"].read_text(encoding="utf-8"))
    cset = candidate_set(funnel, now=decision_time, include_added=include_added)
    lo = pd.Timestamp(decision_time.date() - timedelta(days=int(C.LLM_SELECTOR_PRICE_LOOKBACK_DAYS)))
    bars = pd.read_parquet(p["bars"], columns=["symbol", "date", "close", "volume"],
                           filters=[("symbol", "in", sorted(cset["tickers"])), ("date", ">=", lo)])
    bars["date"] = pd.to_datetime(bars["date"])
    rev = None
    if p["revisions"].is_file():
        rev = pd.read_parquet(p["revisions"], columns=["ticker", "event_date", "target_action", "target_change"],
                              filters=[("ticker", "in", sorted(cset["tickers"]))])
    dig = DA.digest_names(p["digest"], decision_time,
                          lookback_days=int(C.LLM_SELECTOR_DIGEST_LOOKBACK_DAYS))
    corpus = DA.Corpus(p["corpus"], cik_map=DA.load_cik_map(p["cik_map"]) if p["cik_map"].is_file() else {})
    win = corpus.window(decision_time - timedelta(days=int(C.LLM_SELECTOR_KNOWABLE_LOOKBACK_DAYS)), decision_time)
    out = {"paths": {k: str(v) for k, v in p.items()}, "cset": cset, "bars": bars, "rev": rev,
           "digest_by_ticker": dig["by_ticker"], "digests_used": dig["digests_used"],
           "corpus_by_ticker": win["by_ticker"], "corpus_rows": win["n_rows"],
           "sizes": {"bars_rows": int(len(bars)), "revision_rows": 0 if rev is None else int(len(rev)),
                     "digests_used": len(dig["digests_used"]), "corpus_rows": int(win["n_rows"])}}
    if event_packet_on():
        from backend.services import event_nodes as EN
        st = Path(event_store) if event_store else Path(data_root) / str(C.EVENT_NODES_DIRNAME) / EN.STORE_NAME
        if not st.is_file():
            raise SelectorRefused(INPUT_MISSING, f"event_nodes store missing at {st} "
                                                 f"(EVENT_NODES_SELECTOR_PACKET_ENABLED is on)")
        known = EN.nodes_known_at(st, decision_time)
        out["event_by_ticker"] = EN.events_for(cset["tickers"], known["nodes"], decision_time)
        out["paths"]["event_nodes"] = str(st)
        out["sizes"].update({"event_nodes_known": len(known["nodes"]),
                             "event_versions_after_decision_skipped": known["n_versions_after_t_skipped"]})
    return out


def all_packets(inputs: dict, decision_time: datetime) -> list[dict]:
    cset = inputs["cset"]
    mx = int(C.LLM_SELECTOR_MAX_ITEMS_PER_NAME)
    out = []
    for m in cset["members"]:
        t = m["ticker"]
        facts = (funnel_facts(m, cset["generated_at"])
                 + price_facts(inputs["bars"], t, decision_time)
                 + revision_facts(inputs["rev"], t, decision_time, int(C.LLM_SELECTOR_REVISION_LOOKBACK_DAYS))
                 + digest_facts(inputs["digest_by_ticker"], t, mx)
                 + knowable_facts(inputs["corpus_by_ticker"], t, mx))
        if event_packet_on():
            facts += event_facts(inputs.get("event_by_ticker") or {}, t)
        out.append(build_packet(t, facts, decision_time))
    return out


def cost_projection(system: str, user: str) -> dict:
    """Token estimate and cost per decision / month from config prices.
    No call is made."""
    from backend.services import provider_budget as PB
    model = str(C.LLM_SELECTOR_MODEL)
    max_out = int(C.LLM_SELECTOR_MAX_TOKENS)
    est_in = int(math.ceil(len((system + user).encode("utf-8")) / 4.0)) + 16
    est_out = max_out
    per_month = 21.0 / float(C.LLM_SELECTOR_CADENCE_SESSIONS)
    rows = {}
    for label, mdl in (("request_model_list_price", model), ("served_deepseek_flash_calibrated", "deepseek-flash")):
        pr = C.LLM_PRICE_PER_MTOK.get(mdl)
        if not pr:
            continue
        usd = (est_in * pr["in"] + est_out * pr["out"]) / 1e6
        rows[label] = {"model": mdl, "usd_per_decision": round(usd, 6),
                       "usd_per_month": round(usd * per_month, 4),
                       "usd_per_month_if_daily": round(usd * 21.0, 4)}
    q = PB.quote(system, user, max_out, model=model)
    return {"est_input_tokens_chars_div_4": est_in, "max_output_tokens": est_out,
            "decisions_per_month": round(per_month, 2),
            "by_price_row": rows,
            "budget_reservation_bound": {"input_bound_bytes_plus_overhead": q["input_bound"],
                                         "output_bound": q["output_bound"],
                                         "reserved_usd": q["reserved_units"] / PB.SCALE},
            "monthly_cap_usd": PB.monthly_cap_usd() if hasattr(PB, "monthly_cap_usd") else None}
