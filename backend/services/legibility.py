"""The legibility pages' READ side (chunk C19, 2026-10-07; review fixes 2026-10-07).

Four website pages make the machine legible: Paper Arena, Forecast Lab, Theory Lab and
System Health. Each page renders receipts other chunks already write; this module picks
the newest receipt of each kind and reshapes it. Every receipt it uses is named
(repo-relative path + sha256 of the bytes read), dated by its OWN stamp and aged at serve
time against `config.LEGIBILITY_STALE_HOURS`.

Rules this module keeps (CLAUDE.md; roadmap 2026-10-06 section 7; REVIEW_2026-10-07_C19):

* Never the file mtime (mtime keys the parse cache only). Never a hard-coded date. An
  undateable receipt is UNKNOWN, never FRESH.
* A value with no receipt is `null` with its reason in `missing_because`.
* Labels are the receipts' own; nothing here upgrades one.
* The reader does not invent statistics. Two display derivations are declared where they
  are made: a Wilson interval from a bin's own (n, rate), and per-bin date counts from a
  reproduction of the reputation writer's own binning that must match the receipt's
  per-bin n exactly or is refused.
* What leaves the process is decided by `legibility_sanitise.sanitise` (deny by default,
  applied by the routers). This module additionally drops the owner's personal books and
  every dollar field at the source.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config as _config

SCHEMA = "legibility/2"

#: The evidence ladder (roadmap 2026-10-06 section 7). "Proven" appears nowhere.
EVIDENCE_LADDER = ("OBSERVED(n)", "EARLY_EVIDENCE", "REPLICATED", "VALIDATED_EDGE")

#: Theory states (C19 brief + review F4).
THEORY_STATES = ("HYPOTHESIS", "UNINFORMATIVE", "EARLY_SUPPORT", "CONDITIONAL_SUPPORT", "STRENGTHENING",
                 "REGIME_SPECIFIC", "WEAKENING", "FALSIFIED_VARIANT", "FALSIFIED", "RETIRED",
                 "INVALID_EXPERIMENT")

#: The map printed on the Theory Lab legend (review F4, verbatim order).
THEORY_STATE_MAP = (
    ("PROPOSED / NEEDS_CELL / DECLARED / RUN, no verdict", "HYPOTHESIS (untested)"),
    ("CANNOT_DISTINGUISH", "UNINFORMATIVE (tested; MDE printed)"),
    ("FAILED_VARIANT, powered False or unknown", "UNINFORMATIVE (negative, unpowered)"),
    ("FAILED_VARIANT, powered True", "FALSIFIED_VARIANT (this variant; the family stays open)"),
    ("MECHANISM_REJECTED", "FALSIFIED"),
    ("positive history -> latest non-positive, latest POWERED", "WEAKENING"),
    ("positive history -> latest non-positive, latest unpowered", "UNINFORMATIVE (after a positive)"),
    ("non-positive -> CANDIDATE / CONDITIONAL_POSITIVE", "STRENGTHENING"),
    ("CANDIDATE / CONDITIONAL_POSITIVE with a split primary mean <= 0", "REGIME_SPECIFIC"),
    ("CONDITIONAL_POSITIVE", "CONDITIONAL_SUPPORT"),
    ("CANDIDATE", "EARLY_SUPPORT"),
    ("REFUSED / DISCARDED_NO_REFUTATION", "INVALID_EXPERIMENT"),
    ("DUPLICATE_* / RETIRED_FROM_CURRENT_SEARCH", "RETIRED"),
)
NEGATIVE_STATES = ("FALSIFIED", "FALSIFIED_VARIANT", "WEAKENING")

#: Owner-personal books never reach these payloads (review F1): the owner's own brokerage
#: book family and any account named for the owner (its twins included).
PERSONAL_FAMILIES = ("murat_book",)
PERSONAL_ACCOUNT_PREFIXES = ("murat_",)

REPO = Path(__file__).resolve().parents[2]

# ───────────────────────────────────────────────────────────── helpers

_CACHE: dict = {}


def base_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR)


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$")


def parse_utc(v: Any) -> Optional[datetime]:
    """ISO (with or without zone), a bare date, or the compact `20261006T163850Z`."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    m = _COMPACT.match(s)
    if m:
        y, mo, d, h, mi, se = (int(x) for x in m.groups())
        return datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def rel(p: Path | str | None) -> Optional[str]:
    """A repo-relative path for the page (never an absolute machine path)."""
    if p is None:
        return None
    p = Path(p)
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except (ValueError, OSError):
        pass
    try:
        return "optimus/" + p.resolve().relative_to(base_dir().resolve()).as_posix()
    except (ValueError, OSError):
        return p.name


def _stat_key(p: Path) -> tuple:
    st = p.stat()
    return (str(p), st.st_size, st.st_mtime_ns)


def _bytes(p: Path) -> tuple[bytes, str]:
    """The file's bytes and their sha256, cached by (path, size, mtime) -- mtime keys the cache only."""
    key = ("bytes",) + _stat_key(p)
    hit = _CACHE.get(("bytes", str(p)))
    if hit and hit[0] == key:
        return hit[1], hit[2]
    b = p.read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    _CACHE[("bytes", str(p))] = (key, b, sha)
    return b, sha


def sha256_of(p: Optional[Path]) -> Optional[str]:
    if p is None or not p.is_file():
        return None
    return _bytes(p)[1]


def read_json(p: Path) -> Any:
    key = ("json",) + _stat_key(p)
    hit = _CACHE.get(("json", str(p)))
    if hit and hit[0] == key:
        return hit[1]
    blob = json.loads(_bytes(p)[0].decode("utf-8"))
    _CACHE[("json", str(p))] = (key, blob)
    return blob


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    key = ("jsonl",) + _stat_key(p)
    hit = _CACHE.get(("jsonl", str(p)))
    if hit and hit[0] == key:
        return hit[1]
    out: list[dict] = []
    for line in _bytes(p)[0].decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            out.append(r)
    _CACHE[("jsonl", str(p))] = (key, out)
    return out


def stale_limit_h(kind: str) -> float:
    return float((getattr(_config, "LEGIBILITY_STALE_HOURS", {}) or {}).get(kind, 48.0))


def freshness(kind: str, stamp: Any, now: Optional[datetime] = None) -> dict:
    """Age of a receipt from ITS OWN stamp; STALE past the config limit; UNKNOWN when undateable."""
    now = _now(now)
    limit = stale_limit_h(kind)
    dt = parse_utc(stamp)
    if dt is None:
        return {"stamp_utc": None, "age_hours": None, "stale_after_hours": limit, "status": "UNKNOWN",
                "line": f"{kind}: receipt has no readable stamp; freshness UNKNOWN"}
    age_h = round((now - dt).total_seconds() / 3600.0, 2)
    status = "STALE" if age_h > limit else "FRESH"
    return {"stamp_utc": dt.isoformat(timespec="seconds"), "age_hours": age_h, "stale_after_hours": limit,
            "status": status,
            "line": f"{kind}: {_fmt_h(age_h)} old (limit {_fmt_h(limit)})" + (" -- STALE" if status == "STALE" else "")}


def _fmt_h(h: float) -> str:
    if h < 1:
        return f"{h * 60:.0f} min"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} d"


def receipt_ref(kind: str, path: Optional[Path], stamp: Any, now: Optional[datetime] = None,
                missing_because: Optional[str] = None, role: Optional[str] = None) -> dict:
    """One row of a page's receipts strip: what was read (path + sha256 of the bytes read),
    when it was written, how old, and which card used it."""
    if path is None:
        return {"kind": kind, "file": None, "stamp_utc": None, "age_hours": None, "sha256": None,
                "stale_after_hours": stale_limit_h(kind), "status": "MISSING", "role": role,
                "line": f"{kind}: no receipt", "missing_because": missing_because or "no receipt on disk"}
    return {"kind": kind, "file": rel(path), "sha256": sha256_of(path), "role": role,
            **freshness(kind, stamp, now)}


def newest_by_name(folder: Path, rx: re.Pattern, key=lambda m: m.groups()) -> Optional[tuple[Path, re.Match]]:
    """Newest file in `folder` whose NAME matches `rx`, ordered by the stamp groups (never mtime)."""
    if not folder.is_dir():
        return None
    best = None
    for p in folder.iterdir():
        if not p.is_file():
            continue
        m = rx.match(p.name)
        if not m:
            continue
        k = key(m)
        if best is None or k > best[0]:
            best = (k, p, m)
    return (best[1], best[2]) if best else None


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _r(v: Any, nd: int) -> Optional[float]:
    """Display rounding of a receipt number (never a new statistic)."""
    x = _f(v)
    return None if x is None else round(x, nd)


def overall_status(receipts: list[dict]) -> str:
    st = [r.get("status") for r in receipts if r.get("status") != "MISSING"]
    if "STALE" in st:
        return "STALE"
    if "UNKNOWN" in st:
        return "UNKNOWN"
    return "FRESH"


def is_personal(account: Any, family: Any) -> bool:
    a, f = str(account or ""), str(family or "")
    return f in PERSONAL_FAMILIES or any(a.startswith(p) for p in PERSONAL_ACCOUNT_PREFIXES)


# ───────────────────────────────────────────────────────────── 1. Paper Arena

ROI_RE = re.compile(r"^roi_(\d{4}-\d{2}-\d{2})T(\d{6})Z(\.nobroker)?\.json$")
BOOK_DNA_RE = re.compile(r"^book_dna_(\d{4}-\d{2}-\d{2})T(\d{6})Z\.json$")


def _roi_candidates(folder: Path) -> list[tuple]:
    if not folder.is_dir():
        return []
    out = []
    for p in folder.iterdir():
        m = ROI_RE.match(p.name)
        if m:
            out.append((m.group(1), m.group(2), m.group(3) is not None, p))
    return out


def newest_roi(folder: Path) -> Optional[Path]:
    """The newest RUN-STAMPED ROI receipt (`roi_<date>T<hhmmss>Z[.nobroker].json`), broker read or
    not (review F9a: a failed broker read must not hide a newer receipt). The undated
    `roi_<date>.json` is a same-day copy and is skipped."""
    c = _roi_candidates(folder)
    return max(c, key=lambda x: (x[0], x[1]))[3] if c else None


def newest_broker_roi(folder: Path) -> Optional[Path]:
    c = [x for x in _roi_candidates(folder) if not x[2]]
    return max(c, key=lambda x: (x[0], x[1]))[3] if c else None


def _label_rung(label: Any) -> tuple[Optional[str], Optional[int]]:
    s = str(label or "")
    m = re.match(r"^OBSERVED\((\d+)\)$", s)
    if m:
        return "OBSERVED", int(m.group(1))
    for rung in EVIDENCE_LADDER[1:]:
        if s.startswith(rung):
            return rung, None
    return (None, None) if not s else (s, None)


def _book_row(b: Optional[dict], r: Optional[dict], loser: Optional[dict]) -> dict:
    """One Arena row from the book_dna book (b), the ROI row (r) and the loser decomposition.
    Percentages, sessions and labels only: no dollar field is copied."""
    b = b or {}
    r = r or {}
    mb: dict[str, str] = {}
    ev = b.get("evidence") or {}
    label = ev.get("label")
    rung, n_obs = _label_rung(label)
    if not label:
        mb["evidence_label"] = ("no book_dna row for this account" if not b
                                else "book_dna wrote no evidence label for this row")
    strategy = r.get("graded_against") or b.get("rule") or (f"twin of {b['twin_of']}" if b.get("twin_of") else None)
    if strategy is None:
        mb["strategy"] = "the receipts name no rule or graded_against for this account"
    beta = b.get("beta_vs_spy") or {}
    beta_v = _f(beta.get("value"))
    if beta_v is None and beta:
        mb["beta_vs_spy"] = str(beta.get("why") or beta.get("value"))
    cash = b.get("cash_fraction") or {}
    cash_v = _f(cash.get("value"))
    if cash_v is None and cash:
        mb["cash_fraction"] = str(cash.get("why") or cash.get("value"))
    sessions = b.get("sessions_graded")
    if sessions is None:
        mb["sessions_graded"] = "book_dna did not count sessions for this row" if b else "no book_dna row"
    tickers = list(b.get("tickers") or [])
    weights = b.get("weights") or {}
    hold = sorted(({"ticker": t, "weight": _f(weights.get(t))} for t in tickers),
                  key=lambda h: -(h["weight"] or 0.0))[:15]
    sub = b.get("subwindows") or {}
    vs = _f(b.get("excess_pp") if b else r.get("vs_spy_pp"))
    if vs is None:
        mb["vs_spy_pp"] = str(r.get("note") or r.get("broker_error") or "no own-window SPY leg in the ROI receipt")
    return {
        "account": b.get("account") or r.get("account"),
        "family": b.get("family") or r.get("family"),
        "category": b.get("category"),
        "twin_kind": b.get("twin_kind"),
        "twin_of": b.get("twin_of"),
        "strategy": strategy,
        "book_id": b.get("book_id") or r.get("book_id"),
        "status": b.get("status") or r.get("status"),
        "mark_status": r.get("mark_status"),
        "mark_age_days": r.get("mark_age_days"),
        "inception": b.get("inception") or r.get("inception"),
        "last_mark": b.get("last_mark") or r.get("last_mark"),
        "sessions_graded": sessions,
        "return_pct": _f(b.get("return_pct") if b else r.get("roi_pct")),
        "spy_same_window_pct": _f(b.get("spy_leg_pct") if b else r.get("spy_same_window_pct")),
        "vs_spy_pp": vs,
        "spy_base": r.get("spy_base"),
        "evidence_label": label, "evidence_rung": rung, "evidence_n": n_obs, "evidence_why": ev.get("why"),
        "n_holdings": b.get("n_holdings") if b else r.get("n_positions"),
        "holdings": hold,
        "holdings_source": b.get("holdings_source"),
        "beta_vs_spy": beta_v, "beta_n_obs": beta.get("n_obs"),
        "cash_fraction": cash_v,
        "one_name_why": b.get("one_name_why"),
        "subwindows_status": sub.get("status"), "subwindows_n_positive": sub.get("n_positive"),
        "subwindows": sub.get("windows"),
        "manager_last_run": b.get("manager_last_run"),
        "note": r.get("note") or None,
        "source": r.get("source"),
        "error_type": (loser or {}).get("error_type"),
        "error_why": (loser or {}).get("why"),
        "decomposition": (loser or {}).get("decomposition"),
        "missing_because": mb,
    }


def arena_payload(now: Optional[datetime] = None) -> Optional[dict]:
    """The Paper Arena. None when no ROI receipt exists (the router turns it into a 404)."""
    now = _now(now)
    folder = base_dir() / "paper_accounts"
    roi_p = newest_roi(folder)
    if roi_p is None:
        return None
    roi = read_json(roi_p)
    agg = roi.get("aggregate") or {}
    receipts = [receipt_ref("paper_accounts_roi", roi_p, roi.get("generated_utc"), now, role="every book row")]
    missing: dict[str, str] = {}

    is_nob = roi_p.name.endswith(".nobroker.json")
    choice = {"served": rel(roi_p), "served_is_nobroker": is_nob, "newest_broker_file": None,
              "newest_broker_age_hours": None,
              "line": "the newest ROI receipt is a broker read"}
    if is_nob:
        nb = newest_broker_roi(folder)
        if nb is not None:
            nbr = read_json(nb)
            fr = freshness("paper_accounts_roi", nbr.get("generated_utc"), now)
            choice.update(newest_broker_file=rel(nb), newest_broker_age_hours=fr["age_hours"])
        choice["line"] = ("the newest ROI receipt is a NO-BROKER pass: the broker accounts were not re-read; their rows "
                          "carry their last broker read" + (f" (newest broker read {choice['newest_broker_file']}, "
                                                            f"{fr['line']})" if nb is not None else
                                                            " (no broker-read receipt on disk)"))

    dna_p: Optional[Path] = None
    named = agg.get("book_dna_receipt")
    if named:
        cand = folder / Path(str(named).replace("\\", "/")).name
        if BOOK_DNA_RE.match(cand.name) and cand.is_file():
            dna_p = cand
        else:
            missing["book_dna"] = f"the ROI receipt names {Path(str(named)).name}, which is not on disk"
    else:
        missing["book_dna"] = ("the ROI receipt names no book_dna receipt (C3 runs with the ROI receipt; "
                               "this run predates it or book_dna refused)")
    dna = read_json(dna_p) if dna_p else None
    receipts.append(receipt_ref("book_dna", dna_p, (dna or {}).get("generated_utc"), now,
                                missing_because=missing.get("book_dna"),
                                role="labels, clusters, ex-ante bets, losers"))

    roi_rows = {str(r.get("account")): r for r in roi.get("rows") or []}
    losers = {str(x.get("account")): x for x in ((dna or {}).get("losers") or [])}
    rows: list[dict] = []
    if dna:
        seen = set()
        for b in dna.get("books") or []:
            a = str(b.get("account"))
            seen.add(a)
            rows.append(_book_row(b, roi_rows.get(a), losers.get(a)))
        for a, r in roi_rows.items():          # an account book_dna skipped is still listed
            if a not in seen:
                rows.append(_book_row(None, r, None))
    else:
        rows = [_book_row(None, r, None) for r in roi_rows.values()]
    n_personal = sum(1 for x in rows if is_personal(x["account"], x["family"]))
    rows = [x for x in rows if not is_personal(x["account"], x["family"])]
    cat_rank = {"strategy": 0, "control": 1, "twin": 2}
    rows.sort(key=lambda x: (cat_rank.get(x["category"] or "", 3), x["vs_spy_pp"] is None, -(x["vs_spy_pp"] or 0.0)))

    params = (dna or {}).get("params") or {}
    min_s = int(params.get("early_min_sessions") or 21)
    strat = [x for x in rows if x["category"] == "strategy" and x["vs_spy_pp"] is not None]
    ranked = [x for x in strat if (x["sessions_graded"] or 0) >= min_s]
    winners = sorted([x for x in ranked if (x["vs_spy_pp"] or 0) > 0], key=lambda x: -(x["vs_spy_pp"] or 0))
    short = sorted([x for x in strat if (x["sessions_graded"] or 0) < min_s and (x["vs_spy_pp"] or 0) > 0],
                   key=lambda x: -(x["vs_spy_pp"] or 0))[:15]
    loser_rows = sorted([x for x in rows if x["error_type"] is not None], key=lambda x: (x["vs_spy_pp"] or 0.0))

    clusters = []
    for c in (dna or {}).get("holdings_clusters") or []:
        members = [m for m in (c.get("members") or []) if not is_personal(m, None)]
        clusters.append({"cluster_id": c.get("cluster_id"), "n": c.get("n"), "members": members,
                         "families": [f for f in (c.get("families") or []) if f not in PERSONAL_FAMILIES],
                         "shared_basket": [s.get("ticker") for s in (c.get("shared_basket") or [])],
                         "excess_pp_mean": c.get("excess_pp_mean"), "excess_pp_median": c.get("excess_pp_median"),
                         "excess_pp_total": c.get("excess_pp_total"), "tied_for_largest": c.get("tied_for_largest")})
    exb = (dna or {}).get("exante_bets") or {}
    by_family = {f: {"n": v.get("n"), "n_priced": v.get("n_priced"), "roi_pct": v.get("roi_pct")}
                 for f, v in (agg.get("by_family") or {}).items() if f not in PERSONAL_FAMILIES}
    top = {
        "top_line": agg.get("top_line") or (dna or {}).get("summary", {}).get("top_line"),
        "collapse_line": agg.get("collapse_line") or (dna or {}).get("summary", {}).get("collapse_line"),
        "evidence_density_line": agg.get("evidence_density_line"),
        "honest_sentence": agg.get("honest_sentence"),
        "read_me_first": roi.get("read_me_first"),
        "book_dna_read_me_first": (dna or {}).get("read_me_first"),
        "label_ceiling": (dna or {}).get("label_ceiling"),
        "licence": roi.get("licence"),
    }
    for k in ("top_line", "collapse_line"):
        if not top[k]:
            missing[k] = "the ROI receipt and book_dna carry no such line (book_dna absent or refused)"
    if n_personal:
        missing["owner_personal_books"] = (f"{n_personal} owner-personal book(s) are not served on this page; "
                                           f"the receipt's own counts (top line, collapse line) include them")
    br = roi.get("broker_read") or {}
    return {
        "schema": SCHEMA, "page": "arena", "served_utc": now.isoformat(timespec="seconds"),
        "receipts": receipts, "status": overall_status(receipts),
        "receipt_choice": choice,
        "evidence_ladder": list(EVIDENCE_LADDER),
        "top": top,
        "numbers": {
            "n_rows": len(rows),
            "n_ahead_raw": agg.get("n_ahead_raw"), "n_behind_spy": agg.get("n_behind_spy"),
            "n_ahead_twins": agg.get("n_ahead_twins"), "n_ahead_controls": agg.get("n_ahead_controls"),
            "n_ahead_strategy": agg.get("n_ahead_strategy"),
            "n_holdings_clusters_ahead": agg.get("n_holdings_clusters_ahead"),
            "effective_bets_exante": agg.get("effective_bets_exante"),
            "effective_bets_exante_spy_residual": agg.get("effective_bets_exante_spy_residual"),
            "exante_window": agg.get("exante_window"), "exante_n_books": agg.get("exante_n_books"),
            "collapse_factor_twins_controls": agg.get("collapse_factor_twins_controls"),
            "collapse_factor_holdings_overlap": agg.get("collapse_factor_holdings_overlap"),
            "collapse_factor_exante": agg.get("collapse_factor_exante"),
            "n_ahead_dense": agg.get("n_ahead_dense"),
            "jaccard_threshold": agg.get("jaccard_threshold"),
            "cluster_count_sensitivity": agg.get("cluster_count_sensitivity"),
            "most_frequent_names": agg.get("most_frequent_names"),
            "tilt": agg.get("tilt"),
            "status_counts": agg.get("status_counts"),
            "mark_status_counts": roi.get("mark_status_counts"),
            "exante_construction": exb.get("construction"),
            "exante_top_eigen_share_raw": exb.get("top_eigen_share_raw"),
            "exante_median_pairwise_corr_raw": exb.get("median_pairwise_corr_raw"),
            "min_sessions_to_rank": min_s,
            "n_strategy_ge_min_sessions": len(ranked),
            "n_owner_personal_dropped": n_personal,
        },
        "by_family": by_family,
        "broker_read": {"performed": br.get("performed"), "n_accounts": br.get("n_accounts"),
                        "n_priced": br.get("n_priced"), "errors": br.get("errors"), "read_utc": br.get("read_utc")},
        "clusters": clusters,
        "winners": winners, "short_lived": short, "losers": loser_rows, "books": rows,
        "filters": {"families": dict(sorted(Counter(x["family"] for x in rows).items())),
                    "labels": dict(sorted(Counter(x["evidence_rung"] or "NO_LABEL" for x in rows).items())),
                    "categories": dict(sorted(Counter(x["category"] or "unknown" for x in rows).items()))},
        "links": {"opportunities": "/opportunities", "brain": "/brain", "theory_lab": "/theory-lab",
                  "forecast_lab": "/forecast-lab", "health": "/health"},
        "missing_because": missing,
    }


# ── decision stories (C11) + regret (h5 table)

STORIES_RE = re.compile(r"^stories_(\d{4}-\d{2})\.jsonl$")
REGRET_RE = re.compile(r"^regret_(.+)\.json$")


def stories_payload(limit: int = 200, ticker: Optional[str] = None,
                    now: Optional[datetime] = None) -> Optional[dict]:
    """The PC-PAPER plan's decision stories (newest month) and the newest regret receipt's
    h5 table. None when the decision_story folder holds no stories file."""
    now = _now(now)
    folder = base_dir() / "decision_story"
    hit = newest_by_name(folder, STORIES_RE)
    if hit is None:
        return None
    sp, m = hit
    rows = read_jsonl(sp)
    dec = [r for r in rows if r.get("kind") == "decision"]
    links = {str(r.get("decision_id")): r for r in rows if r.get("kind") == "order_link"}
    if ticker:
        dec = [r for r in dec if str(r.get("ticker", "")).upper() == ticker.upper()]
    dec.sort(key=lambda r: (str(r.get("session") or ""), str(r.get("built_utc") or "")), reverse=True)
    ap = folder / f"alternatives_{m.group(1)}.jsonl"
    alts_by: dict[str, list[dict]] = {}
    for a in read_jsonl(ap):
        alts_by.setdefault(str(a.get("decision_id")), []).append(
            {"alt": a.get("alt"), "target_weight": a.get("target_weight"), "status": a.get("status"),
             "why": a.get("why")})
    stamp = max((str(r.get("built_utc") or "") for r in dec), default=None) or None
    out_rows = []
    for r in dec[:max(1, int(limit))]:
        did = str(r.get("decision_id"))
        out_rows.append({
            "decision_id": did, "session": r.get("session"), "asof": r.get("asof"), "ticker": r.get("ticker"),
            "action": r.get("action"), "state": r.get("state"), "cohort": r.get("cohort"),
            "acting": r.get("acting"), "abstention": r.get("abstention"),
            "target_weight": r.get("target_weight"), "held_weight": r.get("held_weight"),
            "plan_full_weight": r.get("plan_full_weight"), "selector_rank": r.get("selector_rank"),
            "reason": r.get("reason"), "refused": r.get("refused"),
            "policy_version": r.get("policy_version"), "mode": r.get("mode"),
            "replay_matches_actual": r.get("replay_matches_actual"),
            "order_or_abstention_id": (r.get("chain") or {}).get("order_or_abstention_id"),
            "order_link": bool(links.get(did)),
            "alternatives": alts_by.get(did, []),
            "built_utc": r.get("built_utc"),
        })
    receipts = [receipt_ref("decision_story", sp, stamp, now, role="stories"),
                receipt_ref("decision_story", ap if ap.exists() else None, stamp, now, role="alternatives",
                            missing_because="no alternatives file for this month")]
    regret = None
    rh = newest_by_name(folder / "regret", REGRET_RE)
    if rh is not None:
        rp = rh[0]
        rec = read_json(rp)
        from backend.services import regret_ledger as RL                  # noqa: PLC0415
        try:
            h5 = RL.h_table(rec, 5)
        except (KeyError, TypeError) as exc:
            h5 = None
            regret_missing = f"regret receipt has no h5 cohort table ({type(exc).__name__})"
        else:
            regret_missing = None if h5 else "no cohort matured at h5 yet"
        regret = {"run_id": rec.get("run_id"), "asof": rec.get("asof"), "line": rec.get("line"),
                  "status": rec.get("status"), "h5_table": h5 or [], "missing_because": regret_missing}
        receipts.append(receipt_ref("regret", rp, rec.get("written_utc") or rec.get("generated_utc")
                                    or rec.get("asof"), now, role="h5 regret table"))
    else:
        receipts.append(receipt_ref("regret", None, None, now, role="h5 regret table",
                                    missing_because="no regret_<run>.json under decision_story/regret "
                                                    "(the daily pass's regret step grades at h5 once stories mature)"))
    return {"schema": SCHEMA, "page": "arena_stories", "served_utc": now.isoformat(timespec="seconds"),
            "receipts": receipts, "status": overall_status(receipts), "month": m.group(1),
            "n_decisions": len(dec), "stories": out_rows, "regret": regret,
            "scope": "decision stories are written for the PC-PAPER plan only (C11)",
            "missing_because": {}}


# ───────────────────────────────────────────────────────────── 2. Forecast Lab

REPUTATION_RE = re.compile(r"^reputation_(\d{4}-\d{2}-\d{2})\.json$")
REPORT_RE = re.compile(r"^report_(\d{4}-\d{2}-\d{2})\.json$")
GRADE_RE = re.compile(r"^grade_forecasts_(\d{4}-\d{2}-\d{2})\.json$")
NIGHT_DIR_RE = re.compile(r"^night_factory_(\d{4}-\d{2}-\d{2})$")
NN_NIGHTLY_RE = re.compile(r"^nightly_(\d{8}T\d{6}Z)\.json$")
NN_WF_RE = re.compile(r"^wf_(\d{8})(.*)\.json$")
WORLD_STATE_RE = re.compile(r"^world_state_(\d{8}T\d{6}Z)\.json$")
WORLD_DIGEST_RE = re.compile(r"^world_digest_(\d{8}T\d{6}Z)\.json$")
ANALYST_REP_RE = re.compile(r"^reputation_weights_(\d{4}-\d{2})\.json$")

#: The two climatologies on the Forecast Lab (review F6), named beside every skill number.
BASELINE_REPUTATION = "hindsight base rate of the scored (held-out) rows"
BASELINE_SIGMA_PRIOR = "training-half base rate (pooled rows; later half held out)"
WILSON_Z = 1.96
CALIB_THIN_ROWS = 30
CALIB_THIN_DATES = 5


def _newest_grade_forecasts(base: Path) -> Optional[Path]:
    best = None
    for d in base.iterdir() if base.is_dir() else []:
        if not (d.is_dir() and NIGHT_DIR_RE.match(d.name)):
            continue
        for p in d.iterdir():
            m = GRADE_RE.match(p.name)
            if m and (best is None or (m.group(1), d.name) > best[0]):
                best = ((m.group(1), d.name), p)
    return best[1] if best else None


def wilson(n: int, p: Optional[float], z: float = WILSON_Z) -> tuple[Optional[float], Optional[float]]:
    """Wilson score interval for a rate p over n rows (display; rows are not independent)."""
    if not n or p is None:
        return None, None
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


def _date_blocks(days: list[str], h: int) -> int:
    """Non-overlapping blocks of h business days covering the distinct decision days."""
    import numpy as np                                                 # noqa: PLC0415
    ds = sorted({d for d in days if d})
    if not ds:
        return 0
    if h <= 1:
        return len(ds)
    n, start = 1, ds[0]
    for d in ds[1:]:
        if int(np.busday_count(start, d)) >= h:
            n += 1
            start = d
    return n


def calibration_date_counts(rep: dict) -> tuple[dict, Optional[str]]:
    """Per-bin distinct decision dates and h-session date blocks, by REPRODUCING the reputation
    writer's own binning (`forecast_reputation.calibration_curve`) on the ledger cut at the
    receipt's `written_utc`. Served only when every bin's n matches the receipt exactly;
    otherwise refused with the reason."""
    from backend.services import forecast_reputation as FR             # noqa: PLC0415
    ledger = base_dir() / "predictions.jsonl"
    cut = str(rep.get("written_utc") or "")
    if not ledger.exists() or not cut:
        return {}, "no ledger or no written_utc on the reputation receipt"
    key = ("calib",) + _stat_key(ledger) + (cut,)
    hit = _CACHE.get("calib")
    if hit and hit[0] == key:
        return hit[1], hit[2]
    out: dict = {}
    why: Optional[str] = None
    try:
        rows = [r for r in read_jsonl(ledger) if r.get("resolved_at") and str(r["resolved_at"]) <= cut]
        g = FR.graded_frame_from_rows(rows)
        for hk, bins in (rep.get("calibration") or {}).items():
            h = int(str(hk).lstrip("h"))
            c = FR.calibration_curve(g, horizon=h)
            sub = g[g["arm"].astype(str).str.startswith("investigator:")
                    & (g["horizon_days"].apply(_f) == h)]
            mine = {(r.observable, int(r.bin)): int(r.n) for r in c.itertuples()}
            theirs = {(b.get("observable"), int(b.get("bin"))): int(b.get("n")) for b in bins}
            if mine != theirs:
                why = (f"reproduction of the writer's {hk} bins does not match the receipt's per-bin n "
                       f"(the ledger moved or the writer changed); date counts refused")
                out = {}
                break
            import pandas as pd                                         # noqa: PLC0415
            for (yr, obs), s2 in sub.assign(year=pd.to_datetime(sub["made_at"], utc=True).dt.year).groupby(
                    ["year", "observable"], sort=True):
                k = min(10, len(s2))
                if k < 2:
                    continue
                bb = pd.qcut(s2["p"], k, labels=False, duplicates="drop")
                for b, rows_b in s2.groupby(bb, sort=True):
                    days = list(rows_b["made_day"].astype(str))
                    out[(hk, obs, int(b))] = {"n_dates": len(set(days)), "n_date_blocks": _date_blocks(days, h)}
    except Exception as exc:                                            # noqa: BLE001
        out, why = {}, f"reproduction raised {type(exc).__name__}"
    _CACHE["calib"] = (key, out, why)
    return out, why


def _arm_cells(arms_by_obs: list[dict]) -> list[dict]:
    """Per kind x horizon: counts of arms and the best / worst arm's skill COPIED from the
    receipt. No pooled skill is computed here (review F6)."""
    acc: dict[tuple, list[dict]] = {}
    for r in arms_by_obs:
        acc.setdefault((str(r.get("kind")), _f(r.get("horizon_days"))), []).append(r)
    out = []
    for (kind, h), rs in sorted(acc.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        scored = [r for r in rs if _f(r.get("skill")) is not None and (_f(r.get("n")) or 0) > 0]
        best = max(scored, key=lambda r: _f(r["skill"])) if scored else None
        worst = min(scored, key=lambda r: _f(r["skill"])) if scored else None
        out.append({"kind": kind, "horizon_days": h, "n_arms": len(rs), "n_arms_scored": len(scored),
                    "n_arms_positive": sum(1 for r in scored if _f(r["skill"]) > 0),
                    "n_rows_heldout": int(sum(_f(r.get("n")) or 0 for r in scored)),
                    "best_arm": (best or {}).get("arm"), "best_skill": _f((best or {}).get("skill")),
                    "worst_arm": (worst or {}).get("arm"), "worst_skill": _f((worst or {}).get("skill"))})
    return out


def _wf_models(wf: Optional[dict]) -> list[dict]:
    out = []
    for model, hs in ((wf or {}).get("models") or {}).items():
        for h, v in (hs or {}).items():
            ric = v.get("rank_ic") or {}
            t20 = v.get("top20_minus_random_net") or {}
            out.append({"model": model, "horizon": h, "rank_ic": ric.get("mean"), "rank_ic_t": ric.get("t"),
                        "rank_ic_loyo_worst": v.get("rank_ic_loyo_worst"),
                        "top20_minus_random_net": t20.get("mean"), "top20_t": t20.get("t"),
                        "n_blocks": ric.get("n_blocks"), "verdict": v.get("verdict"),
                        "brier_skill": (v.get("probability") or {}).get("brier_skill")})
    return out


def _wf_magnitude(wf: Optional[dict]) -> list[dict]:
    mag = []
    for h, v in ((wf or {}).get("magnitude") or {}).items():
        for name, s in (v or {}).items():
            if isinstance(s, dict) and "mean" in s:
                mag.append({"horizon": h, "predictor": name, "ic_with_abs_y": s.get("mean"), "t": s.get("t"),
                            "n_blocks": s.get("n_blocks")})
    return mag


def forecast_lab_payload(now: Optional[datetime] = None) -> Optional[dict]:
    """Calibration, skill by arm x horizon split MAGNITUDE vs DIRECTION (each beside its named
    baseline), the sigma prior, trust per arm, regime rows, and the nn_lab tournament (one
    walk-forward run per card). None when NONE of the receipts exists."""
    now = _now(now)
    base = base_dir()
    receipts: list[dict] = []
    missing: dict[str, str] = {}
    found = 0

    rep_hit = newest_by_name(base / "reputation", REPUTATION_RE)
    rep = read_json(rep_hit[0]) if rep_hit else None
    receipts.append(receipt_ref("forecast_reputation", rep_hit[0] if rep_hit else None, (rep or {}).get("written_utc"),
                                now, missing_because="no reputation/reputation_<date>.json",
                                role="skill by arm, calibration"))
    found += rep is not None

    rpt_hit = newest_by_name(base / "learning_reports", REPORT_RE)
    rpt = read_json(rpt_hit[0]) if rpt_hit else None
    receipts.append(receipt_ref("learning_report", rpt_hit[0] if rpt_hit else None, (rpt or {}).get("generated_utc"),
                                now, missing_because="no learning_reports/report_<date>.json",
                                role="sigma prior, closing lines"))
    found += rpt is not None

    gp = _newest_grade_forecasts(base)
    gf = read_json(gp) if gp else None
    receipts.append(receipt_ref("grade_forecasts", gp, (gf or {}).get("written_utc"), now,
                                missing_because="no night_factory_<date>/grade_forecasts_<date>.json",
                                role="ledger headline"))
    found += gf is not None

    nn_dir = base / "nn_lab" / "receipts"
    nn_hit = newest_by_name(nn_dir, NN_NIGHTLY_RE)
    nn = read_json(nn_hit[0]) if nn_hit else None
    receipts.append(receipt_ref("nn_lab_nightly", nn_hit[0] if nn_hit else None, (nn or {}).get("written_utc"), now,
                                missing_because="no nn_lab/receipts/nightly_<stamp>.json",
                                role="tournament rule, trust"))
    found += nn is not None

    # the walk-forward the nightly CITES is the tournament's; a newer wf_* is a separate review rerun (F3)
    tw = ((nn or {}).get("tournament") or {}).get("walk_forward") or {}
    cited_name = Path(str(tw.get("receipt") or "")).name if tw.get("receipt") else None
    cited_p = nn_dir / cited_name if cited_name and (nn_dir / cited_name).is_file() else None
    cited = read_json(cited_p) if cited_p else None
    cited_ref = receipt_ref("nn_lab_walkforward", cited_p, (cited or {}).get("written_utc") or tw.get("written_utc"),
                                now, role="tournament table (the run the nightly cites)",
                                missing_because=(f"the nightly cites {cited_name}, not on disk" if cited_name
                                                 else "the nightly cites no walk-forward receipt"))
    receipts.append(cited_ref)
    review_p, review = None, None
    if nn_dir.is_dir():
        cands = []
        for p in nn_dir.iterdir():
            m = NN_WF_RE.match(p.name)
            if m and p != cited_p:
                b = read_json(p)
                cands.append(((m.group(1), str(b.get("written_utc") or "")), p, b))
        if cands:
            _, review_p, review = max(cands, key=lambda c: c[0])
            if cited and str(review.get("written_utc") or "") <= str(cited.get("written_utc") or ""):
                review_p, review = None, None              # only a NEWER rerun is shown beside the cited run
    if review_p is not None:
        receipts.append(receipt_ref("nn_lab_walkforward", review_p, review.get("written_utc"), now,
                                    role="review rerun (not the tournament's run)"))
    found += (nn is not None) or (cited is not None)

    ws_hit = newest_by_name(base / "digest", WORLD_STATE_RE)
    ws = read_json(ws_hit[0]) if ws_hit else None
    receipts.append(receipt_ref("world_state", ws_hit[0] if ws_hit else None, (ws or {}).get("as_of"), now,
                                missing_because="no digest/world_state_<stamp>.json", role="regime rows"))
    found += ws is not None
    wd_hit = newest_by_name(base / "digest", WORLD_DIGEST_RE)
    wd = read_json(wd_hit[0]) if wd_hit else None
    receipts.append(receipt_ref("world_state", wd_hit[0] if wd_hit else None,
                                (wd_hit[1].group(1) if wd_hit else None), now,
                                missing_because="no digest/world_digest_<stamp>.json", role="news-digest trust"))
    found += wd is not None

    ar_hit = newest_by_name(base / "analyst", ANALYST_REP_RE)
    ar = read_json(ar_hit[0]) if ar_hit else None
    receipts.append(receipt_ref("analyst_reputation", ar_hit[0] if ar_hit else None, (ar or {}).get("asof"), now,
                                missing_because="no analyst/reputation_weights_<month>.json",
                                role="analyst reputation"))
    found += ar is not None
    if not found:
        return None

    calibration = None
    calib_note = None
    skill = None
    if rep:
        counts, why = calibration_date_counts(rep)
        calibration = {}
        for hk, rows in (rep.get("calibration") or {}).items():
            out = []
            for c in rows:
                n = int(c.get("n") or 0)
                lo, hi = wilson(n, _f(c.get("base_rate")))
                dc = counts.get((hk, c.get("observable"), int(c.get("bin") or 0)))
                out.append({**{k: c.get(k) for k in ("arm_prefix", "horizon", "observable", "bin", "n", "p_mean",
                                                       "p_lo", "p_hi", "base_rate")},
                            "wilson_lo": lo, "wilson_hi": hi,
                            "n_dates": (dc or {}).get("n_dates"), "n_date_blocks": (dc or {}).get("n_date_blocks"),
                            "thin": bool(n < CALIB_THIN_ROWS or (dc is not None and dc["n_dates"] < CALIB_THIN_DATES)),
                            "blocks_missing_because": None if dc else (why or "bin not reproduced")})
            calibration[hk] = out
        calib_note = (f"Wilson 95% interval (z={WILSON_Z}) on ROWS: rows share "
                      f"dates and (at h5) overlapping windows, so it is narrower than the truth; read the date-block "
                      f"count. Grey = fewer than {CALIB_THIN_ROWS} rows or {CALIB_THIN_DATES} dates.")
        abo = rep.get("arms_by_observable") or []
        skill = {
            "split": rep.get("split"), "baseline": BASELINE_REPUTATION, "n_graded": rep.get("n_graded"),
            "n_ledger": rep.get("n_ledger"), "made_at_range": rep.get("made_at_range"),
            "by_kind_horizon": _arm_cells(abo),
            "arms_by_observable": [{k: r.get(k) for k in ("arm", "observable", "horizon_days", "kind", "n",
                                                          "n_total", "skill", "disc")} for r in abo],
            "arms": [{k: r.get(k) for k in ("arm", "family", "n", "n_total", "brier", "clim", "skill", "disc",
                                            "calib_gap", "weight")} for r in rep.get("arms") or []],
            "tuned": {k: (rep.get("tuned") or {}).get(k) for k in ("k_prior", "gamma", "kappa",
                                                                    "cv_skill_vs_climatology", "where")},
        }
    else:
        missing["calibration"] = missing["skill"] = "no forecast reputation receipt"

    sigma_prior = None
    closing = None
    if rpt:
        cl = rpt.get("closing") or {}
        vp = cl.get("vol_prior") or {}
        sigma_prior = [{"horizon": h, "baseline": BASELINE_SIGMA_PRIOR, **{k: v.get(k) for k in (
            "observable", "formula", "split", "status", "n_rows", "n_heldout", "heldout_from", "heldout_to",
            "climatology_base_rate", "skill_llm", "skill_prior", "skill_llm_own_prior", "winner",
            "days_prior_wins", "n_days")}} for h, v in sorted(vp.items(), key=lambda kv: float(kv[0]))]
        closing = {"works": cl.get("works"), "does_not": cl.get("does_not"), "next_experiment": cl.get("next_experiment")}
        if not sigma_prior:
            missing["sigma_prior"] = "the learning report carries no vol_prior block"
    else:
        missing["sigma_prior"] = "no learning report"

    grades = None
    if gf:
        h = gf.get("health") or {}
        grades = {"headline": gf.get("headline"), "date": gf.get("date"), "totals": gf.get("totals"),
                  "n_records": gf.get("n_records"), "graded_after_this_run": gf.get("graded_after_this_run"),
                  "newly_resolved": gf.get("newly_resolved"), "health_status": h.get("status"),
                  "problems": h.get("problems"), "n_overdue": h.get("n_overdue"),
                  "distinct_specialists": h.get("distinct_specialists")}

    min_dates = int(getattr(_config, "WORLD_DIGEST_TRUST_MIN_DATES", 3))
    trust_rule = (f"trust is exactly 0 until an arm has {min_dates} graded dates; after that it is "
                  f"clip(posterior mean / {getattr(_config, 'WORLD_DIGEST_TRUST_FULL', None)}, 0, "
                  f"{getattr(_config, 'WORLD_DIGEST_TRUST_MAX', None)}) of the per-date Brier improvement "
                  f"over the arm's own control, prior N(0, {getattr(_config, 'WORLD_DIGEST_TRUST_TAU', None)}^2)")
    trust_rows: list[dict] = []
    g = ((wd or {}).get("shadow") or {}).get("grade") or {}
    for arm in ("size", "direction"):
        t = g.get(arm)
        if isinstance(t, dict):
            trust_rows.append({"arm": f"news_digest:{arm}",
                               "control": ("sigma prior" if arm == "size" else "0.25 coin"),
                               "n_dates": t.get("n_dates"), "n_rows": t.get("n_rows"),
                               "mean_improvement": t.get("mean_improvement"), "se": t.get("se"),
                               "posterior_mean": t.get("posterior_mean"), "trust": t.get("trust"),
                               "below_min_dates": (t.get("n_dates") or 0) < min_dates})
    if not trust_rows:
        missing["news_trust"] = "no world_digest receipt with a shadow grade"
    nn_trust = []
    for model, hs in (((nn or {}).get("trust") or {}).get("trust") or {}).items():
        for h, t in (hs or {}).items():
            nn_trust.append({"arm": f"nn_lab:{model}", "horizon": h, "graded_dates": t.get("graded_dates"),
                             "trust": t.get("trust"), "source": t.get("source"),
                             "walk_forward_mean_ic_reported": t.get("walk_forward_mean_ic_reported")})

    regime = None
    if ws:
        rg = ws.get("regime_grade") or {}
        pooled = rg.get("pooled") or {}
        regime = {"note": rg.get("note"), "n_fields": rg.get("n_fields"),
                  "vs_persistence": pooled.get("vs_persistence"), "vs_base_rate": pooled.get("vs_base_rate"),
                  "trust": pooled.get("trust"), "pooled_note": pooled.get("note"), "fields": rg.get("fields"),
                  "regime_write": {k: (ws.get("regime") or {}).get(k) for k in ("state", "session_day", "n_rows")},
                  "baselines": ["persistence (yesterday's regime carries)", "base rate (the field's own history)"],
                  "news_tilt_line": ws.get("news_tilt_line")}
    else:
        missing["regime"] = "no world_state receipt"

    tournament = None
    if nn or cited:
        earned = sorted({r["arm"] for r in nn_trust if (_f(r.get("trust")) or 0) > 0})
        tour = (nn or {}).get("tournament") or {}
        tournament = {
            "rule": tour.get("rule"),
            "nightly_table": tw.get("by_horizon"),
            "nightly_table_receipt": tw.get("receipt"), "nightly_table_written_utc": tw.get("written_utc"),
            "nightly_table_note": tw.get("note"),
            "cited_run": (cited or {}).get("run_id"),
            "cited_missing_because": None if cited else cited_ref.get("missing_because"),
            "cited_models": _wf_models(cited), "cited_magnitude": _wf_magnitude(cited),
            "survivorship_caveat": (cited or {}).get("survivorship_caveat"),
            "per_model": (nn or {}).get("per_model"), "status": (nn or {}).get("status"),
            "earned_forward_weight": earned,
            "sentence": ("no model has earned forward weight: every nn_lab member's trust is 0 "
                         "(forward graded dates so far: "
                         f"{max((int(r.get('graded_dates') or 0) for r in nn_trust), default=0)})"
                         if nn_trust and not earned else
                         (f"{len(earned)} member(s) carry forward trust > 0: {', '.join(earned)}" if earned else None)),
        }
        if tournament["sentence"] is None:
            missing["tournament_sentence"] = "the nightly receipt carries no trust table"
    else:
        missing["tournament"] = "no nn_lab nightly or walk-forward receipt"
    review_block = ({"run_id": review.get("run_id"), "models": _wf_models(review),
                     "label": "review rerun: a NEWER walk-forward than the one the tournament cites; it is not the "
                              "tournament and earns nothing"} if review else None)

    analyst = None
    if ar:
        firms = ar.get("firms") or []
        analyst = {"asof": ar.get("asof"), "month": ar.get("month"), "constants": ar.get("constants"),
                   "limits": ar.get("limits"), "n_firms": len(firms), "n_sectors": len(ar.get("sectors") or []),
                   "pit": {k: (ar.get("pit") or {}).get(k) for k in ("claims_built", "claims_resolved_before_asof",
                                                                       "claim_rule")},
                   "top_firms_by_claims": sorted(
                       ({"firm": f.get("firm"), "n_claims": f.get("n_firm"), "weight_mean": f.get("weight_mean"),
                         "raw_edge": f.get("raw_firm")} for f in firms), key=lambda x: -(x["n_claims"] or 0))[:12]}

    return {
        "schema": SCHEMA, "page": "forecast_lab", "served_utc": now.isoformat(timespec="seconds"),
        "receipts": receipts, "status": overall_status(receipts),
        "house_finding": _house_finding(sigma_prior, skill, tournament),
        "calibration": calibration, "calibration_note": calib_note, "skill": skill, "sigma_prior": sigma_prior,
        "closing": closing, "grades": grades,
        "trust": {"rule": trust_rule, "min_graded_dates": min_dates, "news": trust_rows, "nn_lab": nn_trust},
        "regime": regime, "tournament": tournament, "review_rerun": review_block, "analyst_reputation": analyst,
        "missing_because": missing,
    }


def _house_finding(sigma_prior: Optional[list], skill: Optional[dict], tournament: Optional[dict]) -> dict:
    """The house finding -- size is forecastable, direction is not -- as lines COPIED from the
    receipts, each naming its baseline. The trailing-vol IC is the SAME mechanism as the sigma
    prior, so it rides on the prior's row as a sanity check, never as a second fact (F6)."""
    ev: list[dict] = []
    vol_ic = {m["horizon"]: m for m in (tournament or {}).get("cited_magnitude") or []
              if m.get("predictor") == "trailing_vol_ic_with_abs_y"}
    for v in sigma_prior or []:
        if v.get("skill_prior") is None:
            continue
        hk = f"h{v['horizon']}"
        ic = vol_ic.get(hk)
        ev.append({"what": f"MAGNITUDE: free sigma_63 prior, |move| at h={v['horizon']}",
                   "value": v.get("skill_prior"), "unit": "Brier skill", "baseline": BASELINE_SIGMA_PRIOR,
                   "n": v.get("n_heldout"), "receipt": "learning_report.closing.vol_prior",
                   "sanity_check": (f"same mechanism: trailing-vol rank IC with |return| {ic['ic_with_abs_y']} "
                                    f"(t {ic['t']}, {ic['n_blocks']} blocks) on the cited walk-forward" if ic else None)})
    for r in (skill or {}).get("by_kind_horizon") or []:
        if r.get("kind") == "direction" and r.get("n_arms_scored"):
            ev.append({"what": f"DIRECTION: LLM/process arms at h={r['horizon_days']:g}",
                       "value": None,
                       "unit": f"{r['n_arms_positive']} of {r['n_arms_scored']} scored arms have skill > 0 "
                               f"(best {r['best_arm']} {_r(r['best_skill'], 3)})",
                       "baseline": BASELINE_REPUTATION, "n": r.get("n_rows_heldout"),
                       "receipt": "forecast_reputation.arms_by_observable", "sanity_check": None})
    return {"claim": "size is forecastable, direction is not",
            "reading": ("the size half rests on the free sigma prior (one mechanism, with the volatility IC as its "
                        "sanity check); the direction half on the arms' held-out direction rows. The two use "
                        "DIFFERENT baselines, named on each row, and are not comparable number to number"),
            "evidence": ev}


# ───────────────────────────────────────────────────────────── 3. Theory Lab

THEORY_DECL_RE = re.compile(r"^theory_(.+)_DECLARATION_(.+)\.json$")
THEORY_RES_RE = re.compile(r"^theory_(.+)_RESULTS_(.+)\.json$")
TWIN_SUMMARY_RE = re.compile(r"^twin_board_SUMMARY_((FT|STK|TB)_(\d{4}-\d{2}-\d{2})_(\d+))\.json$")
TWIN_COLUMNS = ("pure_selection", "fair_twin_net", "net_minus_market", "twin_full_round_trip_UPPER_BOUND")
TWIN_WINDOWS = ("full", "design", "validate", "late")
SUPERSESSIONS_FILE = "board_supersessions.json"
BOARD_KINDS = {"sticky": "STK", "basket": "FT"}
_POS = ("CONDITIONAL_POSITIVE", "CANDIDATE")


def theory_state(h: dict, powered: Optional[bool], cell: Optional[dict] = None) -> tuple[str, str]:
    """hyp_lab status/verdict (+ `powered`) -> one theory state and the rule that fired
    (THEORY_STATE_MAP). A negative without power is UNINFORMATIVE: silence is not evidence."""
    status, verdict = h.get("status"), h.get("verdict")
    hist = [e.get("verdict") for e in (h.get("history") or []) if e.get("verdict")]
    if status == "DISCARDED_NO_REFUTATION":
        return "INVALID_EXPERIMENT", "status DISCARDED_NO_REFUTATION: no falsifier, not a hypothesis yet"
    if status in ("DUPLICATE_OF_CLOSED", "DUPLICATE_IN_LEDGER") and not verdict:
        return "RETIRED", f"status {status}: the question is already asked elsewhere"
    if verdict == "REFUSED":
        return "INVALID_EXPERIMENT", "verdict REFUSED: the cell could not run as declared"
    if verdict == "RETIRED_FROM_CURRENT_SEARCH":
        return "RETIRED", "verdict RETIRED_FROM_CURRENT_SEARCH"
    if verdict == "MECHANISM_REJECTED":
        return "FALSIFIED", "verdict MECHANISM_REJECTED (broad evidence against the mechanism)"
    had_positive = any(v in _POS for v in hist[:-1])
    if verdict not in _POS and verdict and had_positive:
        if powered is True:
            return "WEAKENING", f"latest verdict {verdict} (powered) after an earlier positive"
        return "UNINFORMATIVE", f"latest verdict {verdict} after a positive, but UNPOWERED: no direction"
    if verdict in _POS and len(hist) >= 2 and hist[-2] not in _POS:
        return "STRENGTHENING", f"latest verdict {verdict} after {hist[-2]}"
    if verdict in _POS:
        means = [float(m) for w in ("design", "validate", "late")
                 if (m := (((cell or {}).get("primary_stats") or {}).get(w) or {}).get("mean_monthly")) is not None]
        if means and min(means) <= 0:
            return "REGIME_SPECIFIC", f"verdict {verdict} but one split's primary mean is <= 0"
        if verdict == "CONDITIONAL_POSITIVE":
            return "CONDITIONAL_SUPPORT", "verdict CONDITIONAL_POSITIVE (holds under its declared condition)"
        return "EARLY_SUPPORT", "verdict CANDIDATE (one declared run; not replicated)"
    if verdict == "FAILED_VARIANT":
        if powered is True:
            return "FALSIFIED_VARIANT", "verdict FAILED_VARIANT and POWERED: this variant fails; the family stays open"
        return "UNINFORMATIVE", "verdict FAILED_VARIANT but power False or unknown: negative, unpowered"
    if verdict == "CANNOT_DISTINGUISH":
        return "UNINFORMATIVE", "verdict CANNOT_DISTINGUISH: tested, the cell could not see the effect either way"
    return "HYPOTHESIS", f"status {status or 'unknown'}, no verdict yet (untested)"


def _handoff_crsp_sentence() -> dict:
    """The honest sentence on CRSP alpha, quoted from the newest handoff that states one."""
    docs = REPO / "docs"
    files = sorted(docs.glob("HANDOFF_*.md"), key=lambda p: p.name, reverse=True) if docs.is_dir() else []
    for p in files:
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in txt.splitlines():
            if "CRSP" in line and "Honest sentence" in line:
                m = re.search(r"Honest sentence:\s*\*\*(.+?)\*\*", line)
                if m:
                    return {"sentence": m.group(1).strip(), "source": rel(p), "missing_because": None}
    return {"sentence": None, "source": None,
            "missing_because": "no docs/HANDOFF_*.md carries an 'Honest sentence' on CRSP alpha"}


def _twin_row(r: dict) -> dict:
    cols = {}
    for c in TWIN_COLUMNS:
        v = r.get(c) or {}
        cols[c] = {w: {"mean_monthly": _r((v.get(w) or {}).get("mean_monthly"), 6),
                       "t": _r((v.get(w) or {}).get("t_blocks"), 2),
                       "mde_monthly": _r((v.get(w) or {}).get("mde_monthly"), 6)} for w in TWIN_WINDOWS}
    return {"rule": r.get("rule"), "family": r.get("family"), "status": r.get("status"), "reason": r.get("reason"),
            "columns": cols, "turnover": _r(r.get("turnover"), 4), "rule_cost_bps": _r(r.get("rule_cost_bps"), 2),
            "twin_cost_bps": _r(r.get("twin_cost_bps"), 2),
            "sticky_turnover_ok": (r.get("sticky_turnover_check") or {}).get("ok"),
            "source_run": None, "superseded_in": None, "superseded_why": None}


def _twin_board(folder: Path, prefix: str, now: datetime, with_rows: bool) -> tuple[Optional[dict], list[dict]]:
    """The FULL board of one twin kind (SMOKE excluded; most rules wins, newest on a tie), with
    `board_supersessions.json` applied ROW BY ROW: a superseded rule shows the supplement's values
    and names its source run; a supplement row missing on disk is printed SUPERSEDED with no number."""
    kind = {"FT": "basket", "STK": "sticky"}.get(prefix, prefix)
    cands = []
    if folder.is_dir():
        for p in folder.iterdir():
            m = TWIN_SUMMARY_RE.match(p.name)
            if m and m.group(2) == prefix:
                s = read_json(p)
                n = int(((s.get("summary") or {}).get("n_rules")) or 0)
                cands.append(((n, m.group(3), int(m.group(4))), p, s, m.group(1)))
    if not cands:
        return None, [receipt_ref("twin_board", None, None, now, role=f"{kind} board",
                                  missing_because=f"no twin_board_SUMMARY_{prefix}_<date>_<n>.json ({kind} twin)")]
    _, sp, summ, run_id = max(cands, key=lambda c: c[0])
    refs = [receipt_ref("twin_board", sp, summ.get("written_utc"), now, role=f"{kind} board summary")]
    rows_p = folder / f"twin_board_{run_id}.jsonl"
    raw = read_jsonl(rows_p)
    if rows_p.exists():
        refs.append(receipt_ref("twin_board", rows_p, summ.get("written_utc"), now, role=f"{kind} board rows"))
    rows = [_twin_row(r) for r in raw]
    applied = []
    sup_p = folder / SUPERSESSIONS_FILE
    if sup_p.is_file():
        sup = read_json(sup_p)
        refs.append(receipt_ref("twin_board", sup_p, sup.get("written_utc"), now, role="row supersessions"))
        for s in sup.get("supersessions") or []:
            if run_id not in (s.get("supersedes_runs") or []):
                continue
            srun = str(s.get("supplement_run"))
            sfile = folder / f"twin_board_{srun}.jsonl"
            srows = {str(r.get("rule")): r for r in read_jsonl(sfile)}
            ssum = folder / f"twin_board_SUMMARY_{srun}.json"
            if ssum.is_file():
                refs.append(receipt_ref("twin_board", ssum, read_json(ssum).get("written_utc"), now,
                                        role=f"supplement {srun}"))
            for i, row in enumerate(rows):
                if row["rule"] not in (s.get("rules") or []):
                    continue
                if row["rule"] in srows:
                    new = _twin_row(srows[row["rule"]])
                    new.update(source_run=srun, superseded_in=run_id, superseded_why=s.get("why"))
                    rows[i] = new
                else:
                    blank = _twin_row({"rule": row["rule"], "family": row["family"]})
                    blank.update(status="SUPERSEDED", reason=f"superseded by {srun}; supplement row not on disk",
                                 superseded_in=run_id, superseded_why=s.get("why"))
                    rows[i] = blank
            applied.append({"supplement_run": srun, "rules": s.get("rules"), "why": s.get("why"),
                            "file": rel(sfile) if sfile.exists() else None})
    others = sorted(c[3] for c in cands if c[1] != sp)
    board = {"twin_kind": summ.get("twin_kind") or kind, "run_id": run_id, "summary_file": rel(sp),
             "rows_file": rel(rows_p) if rows_p.exists() else None,
             "summary": summ.get("summary"), "windows": summ.get("windows"),
             "cost_convention": summ.get("cost_convention"), "four_columns": summ.get("four_columns"),
             "sticky_declaration": summ.get("sticky_declaration"),
             "upper_bound_note": "the UPPER_BOUND column charges the twin a full round trip every month; it is "
                                 "never used in a verdict",
             "other_boards_not_served": others, "supersessions_applied": applied,
             "n_rows": len(rows), "rows_served": bool(with_rows), "rows": rows if with_rows else []}
    return board, refs


def theory_lab_payload(board: str = "sticky", now: Optional[datetime] = None) -> Optional[dict]:
    """Every hypothesis / theory with its state, family posteriors, declaration hashes, the
    four-column twin boards (rows for `board` only; the other's summary) and the CRSP sentence."""
    from backend.services import hyp_lab as H                         # noqa: PLC0415
    if board not in BOARD_KINDS:
        raise ValueError(f"board must be one of {sorted(BOARD_KINDS)}")
    now = _now(now)
    folder = base_dir() / "hyp_lab"
    ledger = folder / "ledger.jsonl"
    receipts: list[dict] = []
    missing: dict[str, str] = {}
    state = H.load_state(ledger) if ledger.exists() else {}
    last_utc = max((str(r.get("utc") or r.get("created_utc") or "") for r in read_jsonl(ledger)), default="") or None
    receipts.append(receipt_ref("hyp_lab_ledger", ledger if ledger.exists() else None, last_utc, now,
                                missing_because="no hyp_lab/ledger.jsonl", role="theories, family posteriors"))

    cells: dict[str, dict] = {}
    if folder.is_dir():
        for p in folder.iterdir():
            md = THEORY_DECL_RE.match(p.name)
            if md:
                d = read_json(p)
                c = cells.setdefault(f"{md.group(1)}|{md.group(2)}", {"cell": md.group(1), "run": md.group(2)})
                c.update({"hyp_id": d.get("hyp_id"), "family": d.get("family"), "title": d.get("title"),
                          "declaration_file": rel(p), "declaration_sha256": d.get("sha256"),
                          "declared_utc": d.get("written_utc"), "honesty": d.get("honesty"),
                          "refutation": d.get("refutation"), "primary": d.get("primary"), "splits": d.get("splits")})
            mr = THEORY_RES_RE.match(p.name)
            if mr:
                d = read_json(p)
                res = d.get("result") or {}
                c = cells.setdefault(f"{mr.group(1)}|{mr.group(2)}", {"cell": mr.group(1), "run": mr.group(2)})
                c.update({"results_file": rel(p), "result_utc": d.get("written_utc"),
                          "result_declaration_sha256": d.get("declaration_sha256"),
                          "verdict": res.get("verdict"), "reason": res.get("reason"),
                          "powered": res.get("powered"), "primary_stats": res.get("primary_stats")})
    cell_by_hyp = {c.get("hyp_id"): c for c in cells.values() if c.get("hyp_id")}

    rows = []
    for hid, h in state.items():
        powered = H.is_powered(h)
        cell = cell_by_hyp.get(hid)
        st, why = theory_state(h, powered, cell)
        s = h.get("last_summary") or {}
        conf = s.get("confirm") or {}
        rows.append({"hyp_id": hid, "title": h.get("title"), "family": H.canonical_family(h.get("family")),
                     "family_raw": h.get("family"), "target": h.get("target"), "status": h.get("status"),
                     "verdict": h.get("verdict"), "powered": powered, "state": st, "state_rule": why,
                     "confirm_mean": conf.get("mean"), "confirm_t": conf.get("t"), "confirm_mde": conf.get("mde"),
                     "reason": s.get("reason"), "reread_of": h.get("reread_of"),
                     "declaration_sha256": (cell or {}).get("declaration_sha256") or h.get("sha256"),
                     "run_id": (cell or {}).get("run"),
                     "receipts": [rel(REPO / x) if not Path(x).is_absolute() else rel(x)
                                  for x in (h.get("receipts") or [])][-3:],
                     "created_utc": h.get("created_utc"), "refutation": h.get("refutation"),
                     "mechanism": h.get("mechanism"), "precursor": h.get("precursor")})
    for c in cells.values():                 # theory cells not (yet) in the ledger still appear
        if c.get("hyp_id") in state:
            continue
        pseudo = {"status": "DECLARED" if not c.get("verdict") else "RUN", "verdict": c.get("verdict"), "history": []}
        powered = c.get("powered") if isinstance(c.get("powered"), bool) else None
        st, why = theory_state(pseudo, powered, c)
        rows.append({"hyp_id": c.get("hyp_id"), "title": c.get("title"),
                     "family": H.canonical_family(c.get("family")), "family_raw": c.get("family"),
                     "target": None, "status": pseudo["status"], "verdict": c.get("verdict"),
                     "powered": bool(powered), "state": st,
                     "state_rule": why + " (theory cell not in the hyp_lab ledger)",
                     "confirm_mean": None, "confirm_t": None, "confirm_mde": None, "reason": c.get("reason"),
                     "reread_of": None, "declaration_sha256": c.get("declaration_sha256"), "run_id": c.get("run"),
                     "receipts": [x for x in (c.get("declaration_file"), c.get("results_file")) if x],
                     "created_utc": c.get("declared_utc"), "refutation": c.get("refutation"),
                     "mechanism": None, "precursor": None})
    order = {s: i for i, s in enumerate(THEORY_STATES)}
    rows.sort(key=lambda r: (order.get(r["state"], 99), str(r.get("family")), str(r.get("title"))))

    fam = H.family_record(state, now) if state else {}
    families = [{"family": f, **{k: r.get(k) for k in ("n_rows", "CONDITIONAL_POSITIVE", "FAILED_VARIANT",
                                                         "CANNOT_DISTINGUISH", "REFUSED", "failed_powered",
                                                         "positive_weighted", "rereads", "p_positive")},
                 "budget_weight": H.family_weight(r.get("p_positive") or 0.0)}
                for f, r in sorted(fam.items(), key=lambda kv: -(kv[1].get("p_positive") or 0))]

    boards = {}
    for kind, prefix in BOARD_KINDS.items():
        b, refs = _twin_board(folder, prefix, now, with_rows=(kind == board))
        receipts.extend(refs)
        boards[kind] = b
        if b is None:
            missing[f"twin_board_{prefix}"] = refs[0]["missing_because"]

    if not state and not any(boards.values()):
        return None
    crsp = _handoff_crsp_sentence()
    if crsp.get("source"):
        md = re.search(r"(\d{4}-\d{2}-\d{2})", Path(crsp["source"]).name)
        receipts.append(receipt_ref("handoff_doc", REPO / crsp["source"], md.group(1) if md else None, now,
                                    role="CRSP sentence (dated by the handoff's name)"))
    sticky = boards.get("sticky") or {}
    ss = sticky.get("summary") or {}
    crsp["counts_from_board"] = ({"board": sticky.get("run_id"), "n_ok": ss.get("n_ok"),
                                  "fair_twin_t_ge_2": ss.get("fair_twin_t_ge_2"),
                                  "pure_selection_t_ge_2": ss.get("pure_selection_t_ge_2"),
                                  "net_minus_market_validate_t_ge_2": ss.get("net_minus_market_validate_t_ge_2"),
                                  "beats_fair_twin_and_market_validate": ss.get("beats_fair_twin_and_market_validate"),
                                  "note": "counts are the board WRITER's summary, before the row supersessions"}
                                 if ss else None)
    return {
        "schema": SCHEMA, "page": "theory_lab", "served_utc": now.isoformat(timespec="seconds"),
        "receipts": receipts, "status": overall_status(receipts),
        "states": list(THEORY_STATES),
        "state_map": [{"input": a, "state": b} for a, b in THEORY_STATE_MAP],
        "state_counts": dict(Counter(r["state"] for r in rows)),
        "powered_rule": ("power is hyp_lab.is_powered: explicit flag, or confirm t <= -2, or confirm MDE <= the "
                         "design effect; unknown counts as NOT powered"),
        "theories": rows,
        "n_negative": sum(1 for r in rows if r["state"] in NEGATIVE_STATES),
        "n_uninformative": sum(1 for r in rows if r["state"] == "UNINFORMATIVE"),
        "families": families, "family_prior": list(H.FAMILY_PRIOR),
        "theory_cells": sorted(cells.values(), key=lambda c: (str(c.get("run")), str(c.get("cell")))),
        "boards": boards, "board_served": board, "crsp": crsp,
        "links": {"brain": "/brain", "opportunities": "/opportunities", "arena": "/arena",
                  "negative_results_doc": "docs/NEGATIVE_RESULTS.md"},
        "missing_because": missing,
    }


# ───────────────────────────────────────────────────────────── 4. System Health

HEALTH_RE = re.compile(r"^health_(\d{8}T\d{6}Z)\.json$")


def health_line(receipt: dict) -> str:
    """Byte-identical to `scripts.daily_pass.step_health`'s headline for the same receipt."""
    rows = list(receipt.get("rows") or [])
    bad = [r for r in rows if r.get("verdict") != "ALIVE"]
    return (f"health rc {receipt.get('exit_code')}: {receipt.get('counts')}; "
            f"{len(bad)} of {len(rows)} subsystems not ALIVE")


def system_health_payload(now: Optional[datetime] = None) -> Optional[dict]:
    """The newest health probe receipt, rows grouped by verdict with fine states, ages from the
    receipt's own stamps, the process census, the task-owner table and the 'same output' rows."""
    now = _now(now)
    hit = newest_by_name(base_dir() / "health", HEALTH_RE)
    if hit is None:
        return None
    hp = hit[0]
    rec = read_json(hp)
    gen = parse_utc(rec.get("generated_utc")) or parse_utc(hit[1].group(1))
    receipts = [receipt_ref("system_health", hp, rec.get("generated_utc") or hit[1].group(1), now, role="every row")]
    rows = []
    for r in rec.get("rows") or []:
        ev = parse_utc(r.get("evidence_utc"))
        detail = r.get("detail")
        rows.append({"name": r.get("name"), "probe": r.get("probe"), "where": r.get("where"),
                     "verdict": r.get("verdict"), "state": r.get("state") or r.get("verdict"),
                     "cadence_s": r.get("cadence_s"), "evidence": r.get("evidence"),
                     "evidence_utc": r.get("evidence_utc"), "age_s_at_probe": r.get("age_s"),
                     "age_s_now": (round((now - ev).total_seconds(), 1) if ev else None),
                     "detail": detail, "proof": r.get("proof"),
                     "same_output": bool(detail and "same output for" in str(detail)),
                     "missing_because": (None if ev else "the probe found no stamp in the producer's evidence")})
    order = {"DEAD": 0, "STALE": 1, "REFUSED": 2, "UNKNOWN": 3, "STOPPED_BY_OPERATOR": 4, "ALIVE": 5}
    rows.sort(key=lambda x: (order.get(str(x["verdict"]), 9), str(x["name"])))
    groups = []
    for v in sorted({str(x["verdict"]) for x in rows}, key=lambda v: order.get(v, 9)):
        g = [x for x in rows if str(x["verdict"]) == v]
        groups.append({"verdict": v, "n": len(g), "states": dict(Counter(x["state"] for x in g)), "rows": g})
    census = [x for x in rows if x["probe"] == "process_census"]
    missing: dict[str, str] = {}
    if not census:
        missing["process_census"] = ("this health receipt has no process_census rows (it predates C14, "
                                     "or the probe ran without a process reader)")
    from backend.services import task_receipts as TR                  # noqa: PLC0415
    cad = getattr(_config, "HEALTH_TASK_CADENCE_H", {}) or {}
    by_name = {x["name"]: x for x in rows}
    owners = []
    for name, spec in TR.TASK_RECEIPT.items():
        r = by_name.get(f"task:{name}")
        owners.append({"task": name, "receipt": spec.receipt, "cadence_h": cad.get(name, 24.0),
                       "session_only": spec.session_only, "retired": spec.retired,
                       "registered_only": spec.registered_only, "hash_rule_off": spec.hash_off or None,
                       "state": (r or {}).get("state"), "verdict": (r or {}).get("verdict"),
                       "detail": (r or {}).get("detail"),
                       "missing_because": None if r else "no task:<name> row in this health receipt"})
    return {
        "schema": SCHEMA, "page": "system_health", "served_utc": now.isoformat(timespec="seconds"),
        "receipts": receipts, "status": receipts[0]["status"],
        "generated_utc": gen.isoformat(timespec="seconds") if gen else None,
        "health_line": health_line(rec), "exit_code": rec.get("exit_code"),
        "counts": rec.get("counts"), "state_counts": rec.get("state_counts"),
        "read_me_first": rec.get("read_me_first"), "source": rec.get("source"),
        "groups": groups, "process_census": census,
        "same_output_rows": [x for x in rows if x["same_output"]],
        "task_owners": owners,
        "same_output_rule": (f"a task whose receipt substance hash is unchanged for "
                             f"{getattr(_config, 'HEALTH_PROGRESS_SAME_HASH_PROBES', None)} consecutive probes is "
                             f"STALE ('same output for X h') unless it declares why the rule is off"),
        "missing_because": missing,
    }


__all__ = ["EVIDENCE_LADDER", "THEORY_STATES", "THEORY_STATE_MAP", "arena_payload", "forecast_lab_payload",
           "freshness", "health_line", "newest_roi", "parse_utc", "stories_payload", "system_health_payload",
           "theory_lab_payload", "theory_state", "wilson"]
