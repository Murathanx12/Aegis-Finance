"""Thesis cards for every chosen stock: engine side + one OpenClaw quest + one
DeepSeek synthesis per ticker.

    python -m scripts.thesis_cards run --dry-run
    python -m scripts.thesis_cards run --max-quests 40 --cap-usd 5 --parallel 2 \
        --model deepseek/deepseek-flash
    python -m scripts.thesis_cards run --universe my_tickers.txt
    python -m scripts.thesis_cards validate [--date YYYY-MM-DD]
    python -m scripts.thesis_cards digest [--date YYYY-MM-DD]
    python -m scripts.thesis_cards forecast [--date YYYY-MM-DD]   # backfill ledger rows
    python -m scripts.thesis_cards run --trigger --dry-run   # who would be re-carded, and why
    python -m scripts.thesis_cards run --trigger --max-quests 5   # re-card them (daily cap binds)

TRIGGERS (`--trigger`, 2026-09-26): a name is re-carded when (a) it entered a
personal / competition frozen book or the funnel shortlist after its last card
(strategy-library `lib_*` books are excluded: 190 rule-picked names would eat
the quest cap; `--include-library` opts them in), (b) >= 3 firms revised
it in 10 days, (c) an earnings / catalyst date is within 5 sessions, (d) its
|1d move| > 2 sigma_63 with no typed event, or (e) its card is > 30 days old.
The reason is written on the card (`trigger`). Every non-refused card also
writes its dated claims (claims ledger + `web_events`) and its management
promises (`promises/promises.jsonl` + `promise:v1` forecast rows).

Every card written by `run` also becomes forecast rows (`thesis_card:v1`,
`beats_benchmark` vs SPY at h=20 and h=120; `TC.write_forecasts`), idempotent
per card hash. `forecast` writes the rows for a day's cards that lack them.

Universe (default), in priority order, de-duplicated, `kind` per source:
  1. backend/data/murat_book.yaml positions                       -> holding
  2. docs/research_notes/2026-09-25/book_human_ai_thematic_v0.draft.json -> personal
  3. research_pharma.md "Suggested candidate list" (bucketed names) -> personal
  4. research_global_candidates.md Books A/B/C (Bloomberg -> Yahoo) -> competition

Resumable per date: a ticker with ANY card in `<ledger>/thesis_cards/<date>/`
(including a Sonnet seed card) is skipped; `--retry-refused` re-asks REFUSED_*.
DIGEST.md is rewritten after every card. The cap is read from the telemetry
ledger the calls write (both purposes, today UTC) before every quest, with
`THESIS_CARD_EST_QUEST_USD` reserved per in-flight quest; an UNKNOWN spend
refuses the run.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                           # noqa: E402
from backend.services import thesis_card as TC               # noqa: E402

NOTES = REPO / "docs" / "research_notes" / "2026-09-25"
MURAT_BOOK = REPO / "backend" / "data" / "murat_book.yaml"
DRAFT = NOTES / "book_human_ai_thematic_v0.draft.json"
PHARMA = NOTES / "research_pharma.md"
GLOBAL = NOTES / "research_global_candidates.md"

#: Bloomberg exchange code -> Yahoo suffix.
BBG_TO_YAHOO = {"KS": ".KS", "KQ": ".KQ", "TT": ".TW", "JP": ".T", "GY": ".DE",
                "NA": ".AS", "DC": ".CO", "SS": ".ST", "NO": ".OL", "AU": ".AX",
                "IM": ".MI", "LI": ".IL", "LN": ".L", "HK": ".HK", "FP": ".PA",
                "SW": ".SW", "CN": ".TO", "IN": ".NS", "CH": ".SS", "US": ""}


# ─────────────────────────────── universe ───────────────────────────────────

def bbg_to_yahoo(s: str) -> str | None:
    """'000660 KS' -> '000660.KS'; 'NOVO B DC' -> 'NOVO-B.CO'; 'ARGX' -> 'ARGX'."""
    parts = s.strip().split()
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0].upper() if re.fullmatch(r"[A-Za-z.]{1,6}", parts[0]) else None
    code = parts[-1].upper()
    if code not in BBG_TO_YAHOO:
        return None
    base = "-".join(parts[:-1]).upper()
    return base + BBG_TO_YAHOO[code]


def _murat(path: Path) -> list[str]:
    import yaml
    try:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return []
    return [str(x["ticker"]).upper() for x in (d.get("positions") or [])
            if isinstance(x, dict) and x.get("ticker")]


def _draft(path: Path) -> list[str]:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(p["ticker"]).upper() for p in (d.get("positions") or [])
            if isinstance(p, dict) and p.get("ticker")]


def _pharma(path: Path) -> list[str]:
    """Named bucket picks with a weight ('VRTX 4%'), excluding the parenthetical
    alternates ('(TMO 2%, CATX 1% if ...)') and rejected names."""
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(r"## Suggested candidate list.*?\n(.*?)(?:\n---|\n## |\Z)", txt, re.S)
    if not m:
        return []
    sec = re.sub(r"\([^)]*\)", "", m.group(1), flags=re.S)
    out = []
    for ln in sec.splitlines():
        if not ln.strip().startswith("**Bucket"):
            continue
        out += re.findall(r"\b([A-Z]{2,5})\s+\d+(?:\.\d+)?%", ln)
    return out


def _global(path: Path) -> list[str]:
    """Tickers from the '### Book X' tables, Bloomberg codes -> Yahoo."""
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for blk in re.split(r"\n### ", "\n" + txt)[1:]:
        if not blk.startswith("Book"):
            continue
        for ln in blk.splitlines():
            m = re.match(r"\|\s*\d+\s*\|\s*([^|(]+?)\s*(?:\([^)]*\))?\s*\|", ln)
            if m:
                y = bbg_to_yahoo(m.group(1))
                if y:
                    out.append(y)
    return out


def default_universe(*, murat_book: Path = MURAT_BOOK, draft: Path = DRAFT,
                     pharma: Path = PHARMA, global_notes: Path = GLOBAL) -> list[dict]:
    order = (("murat_book", "holding", _murat(murat_book)),
             ("thematic_v0_draft", "personal", _draft(draft)),
             ("research_pharma", "personal", _pharma(pharma)),
             ("research_global_books", "competition", _global(global_notes)))
    seen: dict[str, dict] = {}
    for src, kind, names in order:
        for t in names:
            t = t.upper()
            if t in ("CASH", "$CASH") or t in seen:
                continue
            seen[t] = {"ticker": t, "kind": kind, "source": src}
    return list(seen.values())


def universe_from_file(path: Path) -> list[dict]:
    """One ticker per line; optional `,kind`. `#` comments allowed."""
    out, seen = [], set()
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        ln = ln.split("#")[0].strip()
        if not ln:
            continue
        parts = [p.strip() for p in re.split(r"[,\s]+", ln) if p.strip()]
        t = parts[0].upper()
        kind = parts[1].lower() if len(parts) > 1 and parts[1].lower() in TC.KINDS else "personal"
        if t not in seen:
            seen.add(t)
            out.append({"ticker": t, "kind": kind, "source": str(path)})
    return out


# ─────────────────────────────── inputs ─────────────────────────────────────

def _load_catalysts() -> list[dict]:
    import yaml
    rows: list[dict] = []
    d = Path(_cfg.OPTIMUS_LEDGER_DIR) / "pm_catalysts"
    for p in sorted(d.glob("*.yaml")) if d.exists() else []:
        try:
            y = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = y if isinstance(y, list) else (
            (y or {}).get("catalysts") or (y or {}).get("events") or [])
        for r in items:
            if isinstance(r, dict) and r.get("ticker") and r.get("date"):
                rows.append({**r, "date": str(r["date"])[:10]})
    try:
        b = yaml.safe_load(MURAT_BOOK.read_text(encoding="utf-8")) or {}
        for pos in b.get("positions") or []:
            for c in (pos or {}).get("catalysts") or []:
                if isinstance(c, dict) and c.get("date"):
                    rows.append({"ticker": pos["ticker"], "date": str(c["date"])[:10],
                                 "kind": c.get("kind", "manual"), "what": c.get("what", ""),
                                 "source_url": c.get("source_url", ""),
                                 "verified_from": c.get("verified_from", "human-entered")})
    except (OSError, ValueError):
        pass
    return rows


def _load_news(asof: date, tickers: set[str]) -> list[dict]:
    root = Path(_cfg.OPTIMUS_LEDGER_DIR) / "news_corpus"
    out = []
    lo = asof - timedelta(days=TC.NEWS_DAYS + 2)
    for src in root.iterdir() if root.exists() else []:
        if not src.is_dir() or src.name.startswith("_"):
            continue
        for f in src.glob("*.jsonl"):
            try:
                d = date.fromisoformat(f.stem[:10])
            except ValueError:
                continue
            if d < lo or d > asof + timedelta(days=1):
                continue
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if set(r.get("tickers") or []) & tickers:
                    out.append({k: r.get(k) for k in ("source", "published_utc",
                                                       "first_seen_utc", "title",
                                                       "url", "tickers")})
    return out


def _load_fundamentals(asof: date) -> dict:
    """The latest SEC quarter FILED on or before `asof`, with the same
    inflection flag `llm_portfolio.build_briefing` uses (INF.detect)."""
    try:
        import pandas as pd
        from backend.services import inflection as INF
        q = INF.add_features(INF.quarterly_panel())
        q = q[pd.to_datetime(q["filed"]) <= pd.Timestamp(asof)]
        q = q[q["sequential_ok"]].sort_values("filed").drop_duplicates("ticker", keep="last")
        fires = set(INF.detect(q, min_acceleration=-9.99)["ticker"])
        return {r.ticker: {"rev_qoq": r.rev_qoq, "gross_margin": r.gm,
                           "gross_margin_chg": r.gm_chg,
                           "inflection_flag": r.ticker in fires,
                           "last_filed": str(r.filed)[:10]}
                for r in q.itertuples()}
    except Exception as exc:                                       # noqa: BLE001
        print(f"  fundamentals UNAVAILABLE: {type(exc).__name__}: {str(exc)[:100]}")
        return {}


def load_inputs(asof: date, tickers: list[str]) -> dict:
    """Everything the engine side reads, loaded once and filtered to `tickers`.
    Each load that fails is None (UNAVAILABLE on every card), printed here."""
    import pandas as pd
    tset = set(tickers)
    inp: dict[str, Any] = {}
    t0 = time.time()
    try:
        from backend.services import xs_ranker as XR
        b = XR.load_bars(XR.survivorship_free_paths())
        b = b[b["symbol"].isin(tset)]
        gp = Path(_cfg.OPTIMUS_LEDGER_DIR) / "llm_portfolio" / "global_bars.parquet"
        if gp.exists():          # O2's non-US cache, read-only; never pulled here
            try:
                g = pd.read_parquet(gp)
                if {"symbol", "date", "close"} <= set(g.columns):
                    g = g[g["symbol"].isin(tset - set(b["symbol"]))]
                    g["date"] = pd.to_datetime(g["date"])
                    b = pd.concat([b, g], ignore_index=True)
            except Exception as exc:                               # noqa: BLE001
                print(f"  global_bars unreadable: {exc}")
        inp["bars"] = b
    except Exception as exc:                                       # noqa: BLE001
        print(f"  bars UNAVAILABLE: {type(exc).__name__}: {str(exc)[:100]}")
        inp["bars"] = None
    p = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
    try:
        r = pd.read_parquet(p)
        inp["revisions"] = r[r["ticker"].isin(tset)]
    except Exception as exc:                                       # noqa: BLE001
        print(f"  revisions UNAVAILABLE: {exc}")
        inp["revisions"] = None
    try:
        inp["news_rows"] = _load_news(asof, tset)
    except OSError as exc:
        print(f"  news UNAVAILABLE: {exc}")
        inp["news_rows"] = None
    inp["catalysts"] = _load_catalysts()
    try:
        from backend.services import belief_state as B
        inp["predictions"] = [x for x in B.read_predictions() if x.get("ticker") in tset]
    except Exception as exc:                                       # noqa: BLE001
        print(f"  predictions UNAVAILABLE: {exc}")
        inp["predictions"] = None
    inp["fundamentals"] = _load_fundamentals(asof)
    n_b = 0 if inp["bars"] is None else inp["bars"]["symbol"].nunique()
    print(f"  inputs loaded in {time.time() - t0:.0f}s: bars for {n_b}/{len(tset)} "
          f"names, {0 if inp['revisions'] is None else len(inp['revisions'])} revision "
          f"rows, {len(inp['news_rows'] or [])} news rows, {len(inp['catalysts'])} "
          f"catalysts, {len(inp['predictions'] or [])} forecasts, "
          f"{len(inp['fundamentals'])} fundamentals", flush=True)
    return inp


def engine_for(ticker: str, asof: date, inputs: dict) -> dict:
    return TC.engine_side(ticker, asof=asof, bars=inputs.get("bars"),
                          revisions=inputs.get("revisions"),
                          news_rows=inputs.get("news_rows"),
                          catalysts=inputs.get("catalysts"),
                          predictions=inputs.get("predictions"),
                          fundamentals=(inputs.get("fundamentals") or {}).get(ticker))


# ─────────────────────────────── the calls ──────────────────────────────────

def openclaw_quest(ticker: str, prompt: str, *, model: str, timeout: float,
                   log_dir: Path) -> dict:
    """One `openclaw agent` turn. Elapsed and the log are recorded HERE, not
    borrowed from the client's telemetry (which may or may not exist)."""
    from backend.services import openclaw_client as OC
    log_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", ticker)
    log = log_dir / f"{safe}.openclaw.log"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(prompt)
        msg = fh.name
    kw: dict[str, Any] = {"model": model, "timeout": timeout}
    params = inspect.signature(OC.agent).parameters
    if "purpose" in params:
        kw["purpose"] = TC.QUEST_PURPOSE
    t0 = time.time()
    try:
        res = OC.agent(msg, **kw)
    except (OSError, subprocess.SubprocessError) as exc:
        res = {"status": "ERROR", "reply": "", "stderr": f"{type(exc).__name__}: {exc}"}
    finally:
        Path(msg).unlink(missing_ok=True)
    elapsed = round(time.time() - t0, 1)
    reply = res.get("reply") or ""
    log.write_text(reply, encoding="utf-8")
    if res.get("stderr"):
        log.with_suffix(".err").write_text(str(res["stderr"]), encoding="utf-8")
    status = res.get("status") or ("OK" if res.get("rc") == 0 else "RC_NONZERO")
    if not reply.strip():
        status = "EMPTY_LOG"
    return {"status": status, "reply": reply, "elapsed_s": elapsed,
            "log_path": str(log), "cost_usd": res.get("openclaw_cost_usd"),
            "usage": res.get("usage"), "rc": res.get("rc")}


def ledger_spend(day: str) -> float | None:
    """Today's spend on both thesis-card purposes, from the telemetry ledger the
    calls write. None = UNKNOWN (no ledger, or a lower-bound total)."""
    from backend.services import llm_telemetry as LT
    tot = 0.0
    for purpose in (TC.QUEST_PURPOSE, TC.SYNTH_PURPOSE):
        s = LT.spend(since=day, purpose=purpose)
        if not s or s.get("total_is_lower_bound"):
            return None
        tot += float(s.get("total_cost_usd") or 0.0)
    return tot


# ─────────────────────────────── the run ────────────────────────────────────

def run(*, universe: list[dict], asof: Any = None, root: Path | None = None,
        max_quests: int | None = None, cap_usd: float | None = None,
        parallel: int | None = None, model: str | None = None,
        inputs: dict | None = None, quest_fn: Callable | None = None,
        synth_fn: Callable | None = None,
        spend_fn: Callable[[str], float | None] | None = None,
        dry_run: bool = False, retry_refused: bool = False,
        timeout: float | None = None, forecast_path: Path | None = None) -> dict:
    asof_d = TC._asof_date(asof or datetime.now(timezone.utc).date())
    day = asof_d.isoformat()
    # A run against a non-default root (a test's tmp_path) must never append to
    # the real forecast ledger: its rows go beside its cards unless told otherwise.
    sidecar = root is not None
    if forecast_path is None and root is not None:
        forecast_path = Path(root) / "_predictions.jsonl"
    events_path = Path(root) / "_web_events.jsonl" if sidecar else None
    claims_file = Path(root) / "_claims.jsonl" if sidecar else None
    promises_file = Path(root) / "_promises.jsonl" if sidecar else None
    root = Path(root) if root is not None else TC.cards_root()
    max_quests = int(max_quests if max_quests is not None else _cfg.THESIS_CARD_MAX_QUESTS)
    cap_usd = float(cap_usd if cap_usd is not None else _cfg.THESIS_CARD_CAP_USD)
    parallel = max(1, int(parallel or _cfg.THESIS_CARD_PARALLEL))
    model = model or _cfg.THESIS_CARD_MODEL
    timeout = float(timeout or _cfg.THESIS_CARD_QUEST_TIMEOUT_S)
    est = float(getattr(_cfg, "THESIS_CARD_EST_QUEST_USD", 0.05))
    quest_fn = quest_fn or openclaw_quest
    synth_fn = synth_fn or (lambda e, w, *, model: TC.synthesize(e, w, model=model))
    measure_synth = spend_fn is None      # real ledger -> real per-call cost
    spend_fn = spend_fn or ledger_spend
    day_dir = root / day
    log_dir = day_dir / "logs"

    existing = {}
    for c in TC.read_cards(day, root=root):
        if c.get("ticker"):
            existing[str(c["ticker"]).upper()] = c
    todo, skipped = [], []
    for u in universe:
        c = existing.get(u["ticker"].upper())
        if c is not None and not (retry_refused
                                  and str(c.get("verdict", "")).startswith("REFUSED_")):
            skipped.append(u["ticker"])
            continue
        todo.append(u)
    todo_cut = todo[max_quests:]
    todo = todo[:max_quests]
    res: dict[str, Any] = {"receipt": "thesis_cards_run", "day": day, "model": model,
                           "cap_usd": cap_usd, "max_quests": max_quests,
                           "parallel": parallel, "n_universe": len(universe),
                           "n_skipped_existing": len(skipped),
                           "n_todo": len(todo), "cut_by_max_quests": [u["ticker"] for u in todo_cut],
                           "done": [], "refused": [], "state": "RUNNING",
                           "forecast_rows_written": 0, "evidence": {}, "promises": {}}
    print(f"thesis cards {day}: universe {len(universe)}, {len(skipped)} already "
          f"carded, {len(todo)} to do (max {max_quests}), cap ${cap_usd:.2f}, "
          f"parallel {parallel}, model {model}", flush=True)

    if inputs is None:
        inputs = load_inputs(asof_d, [u["ticker"] for u in todo] or ["SPY"])

    if dry_run:
        if not todo:
            print("DRY RUN: nothing to do")
            res["state"] = "DRY_RUN"
            return res
        u = todo[0]
        e = engine_for(u["ticker"], asof_d, inputs)
        qp = TC.quest_prompt(u["ticker"], e,
                             prior_card=TC.previous_card(u["ticker"], asof_d, root=root),
                             open_promises=TC.open_promises(u["ticker"], path=promises_file))
        print(f"\n===== ENGINE SIDE {u['ticker']} ({u['kind']}, {u['source']}) =====")
        print(json.dumps(e, indent=1, default=str))
        print(f"\n===== OPENCLAW QUEST PROMPT ({len(qp)} chars) =====")
        print(qp)
        print("\n===== SYNTHESIS SYSTEM PROMPT =====")
        print(TC.SYNTH_SYSTEM)
        print("\n===== SYNTHESIS USER (web side empty in a dry run) =====")
        print(TC.synth_user(e, TC._empty_web()))
        print(f"\nDRY RUN: nothing called. Would ask {len(todo)}: "
              + ", ".join(x["ticker"] for x in todo))
        res["state"] = "DRY_RUN"
        return res

    lock = threading.Lock()
    synth_lock = threading.Lock()
    inflight = {"n": 0}
    stop = {"why": None}

    def admit() -> bool:
        with lock:
            if stop["why"]:
                return False
            s = spend_fn(day)
            if s is None:
                stop["why"] = ("today's thesis-card spend is UNKNOWN (no telemetry "
                               "ledger, or a lower-bound total); a cap that cannot "
                               "read cannot bind")
                return False
            if s + est * (inflight["n"] + 1) > cap_usd:
                stop["why"] = (f"spent ${s:.4f} + ${est:.2f} x {inflight['n'] + 1} "
                               f"reserved would exceed cap ${cap_usd:.2f}")
                return False
            res["spent_usd_before_last_admit"] = round(s, 6)
            inflight["n"] += 1
            return True

    def one(u: dict) -> None:
        t, kind = u["ticker"], u["kind"]
        if not admit():
            return
        try:
            e = engine_for(t, asof_d, inputs)
            prompt = TC.quest_prompt(t, e,
                                     prior_card=TC.previous_card(t, asof_d, root=root),
                                     open_promises=TC.open_promises(t, path=promises_file))
            q = quest_fn(t, prompt, model=model, timeout=timeout, log_dir=log_dir)
            meta = {"openclaw_log_path": q.get("log_path"),
                    "openclaw_elapsed_s": q.get("elapsed_s"),
                    "openclaw_status": q.get("status"),
                    "openclaw_cost_usd": q.get("cost_usd"),
                    "quest_model": model, "source": u.get("source"),
                    "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            if u.get("trigger"):
                meta["trigger"] = u["trigger"]
            status = q.get("status")
            reply = q.get("reply") or ""
            card = None
            if status == "EMPTY_LOG" or not reply.strip():
                card = TC.refusal_card(t, kind=kind, asof=asof_d, engine=e,
                                       verdict="REFUSED_EMPTY_LOG",
                                       why=f"openclaw returned an empty log (status {status})",
                                       meta=meta)
            elif status not in ("OK", None):
                card = TC.refusal_card(t, kind=kind, asof=asof_d, engine=e,
                                       verdict=f"REFUSED_{str(status).upper()}",
                                       why=f"openclaw status {status}", meta=meta)
            else:
                web = TC.parse_reply(reply)
                if web.get("parse") == "refused":
                    card = TC.refusal_card(t, kind=kind, asof=asof_d, engine=e,
                                           verdict="REFUSED_UNPARSEABLE_WEB",
                                           why=str(web.get("parse_error")), meta=meta)
            synth_cost = None
            if card is None:
                # Serialised so the ledger delta on the SYNTH purpose is this
                # call's cost and no other thread's.
                with synth_lock:
                    s0 = _purpose_spend(day, TC.SYNTH_PURPOSE) if measure_synth else None
                    syn = synth_fn(e, web, model=model)
                    if s0 is not None:
                        s1 = _purpose_spend(day, TC.SYNTH_PURPOSE)
                        synth_cost = None if s1 is None else round(max(0.0, s1 - s0), 6)
                meta["deepseek_cost_usd"] = synth_cost
                card = TC.build_card(t, kind=kind, asof=asof_d, engine=e, web=web,
                                     synth=syn, meta=meta)
            with lock:
                TC.write_card(card, root=root)
                TC.write_digest(day, root=root)
                try:
                    fw = TC.write_forecasts([card], today=datetime.now(timezone.utc).date(),
                                            path=forecast_path)
                    res["forecast_rows_written"] += fw["n_rows_written"]
                except Exception as exc:                           # noqa: BLE001
                    # The card is on disk; `forecast --date` writes its rows later.
                    res.setdefault("forecast_errors", []).append(
                        {"ticker": t, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
                if not str(card.get("verdict", "")).startswith("REFUSED_"):
                    # Rule 6: the card's dated claims and promises become
                    # evidence rows and forecast rows. A failure is recorded and
                    # the card stands; `evidence --date` re-derives both.
                    try:
                        res["evidence"][t] = TC.write_evidence(
                            card, events_path=events_path, claims_file=claims_file)
                        res["evidence"][t]["untyped_claims"] = backfill_claim_events(
                            day, claims_file=claims_file, events_path=events_path)["web_events"]
                    except Exception as exc:                       # noqa: BLE001
                        res.setdefault("evidence_errors", []).append(
                            {"ticker": t, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
                    try:
                        res["promises"][t] = TC.write_promises(
                            card, today=datetime.now(timezone.utc).date(),
                            path=promises_file, forecast_path=forecast_path)
                    except Exception as exc:                       # noqa: BLE001
                        res.setdefault("promise_errors", []).append(
                            {"ticker": t, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
                (res["refused"] if str(card.get("verdict", "")).startswith("REFUSED_")
                 else res["done"]).append(t)
            print(f"  {t:<11} {str(card.get('verdict')):<24} conf "
                  f"{str(card.get('confidence')):<5} quest {q.get('elapsed_s')}s "
                  f"oc ${q.get('cost_usd')} synth ${synth_cost} web "
                  f"{card.get('web_parse')}", flush=True)
        except Exception as exc:                                   # noqa: BLE001
            # One ticker's crash is that ticker's row, not the run's end.
            with lock:
                res["refused"].append(t)
                res.setdefault("errors", []).append(
                    {"ticker": t, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            print(f"  {t:<11} ERROR {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        finally:
            with lock:
                inflight["n"] -= 1

    if parallel == 1:
        for u in todo:
            one(u)
            if stop["why"]:
                break
    else:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            list(ex.map(one, todo))

    if stop["why"]:
        res["state"] = "REFUSED_CAP"
        res["why"] = stop["why"]
    else:
        res["state"] = "DONE"
    try:
        s = spend_fn(day)
    except Exception:                                              # noqa: BLE001
        s = None
    res["spent_usd_today"] = s
    TC.write_digest(day, root=root)
    res["digest"] = str(day_dir / "DIGEST.md")
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "_run_receipt.json").write_text(json.dumps(res, indent=1, default=str),
                                               encoding="utf-8")
    print(f"{res['state']}: {len(res['done'])} carded, {len(res['refused'])} refused, "
          f"{res['forecast_rows_written']} forecast rows, "
          f"spent today ${s}; {res.get('why') or ''}", flush=True)
    return res


def _purpose_spend(day: str, purpose: str) -> float | None:
    from backend.services import llm_telemetry as LT
    s = LT.spend(since=day, purpose=purpose)
    if not s or s.get("total_is_lower_bound"):
        return None
    return float(s.get("total_cost_usd") or 0.0)


# ─────────────────────────────── triggers ───────────────────────────────────

BOOKS = Path(_cfg.OPTIMUS_LEDGER_DIR) / "llm_portfolio" / "books.jsonl"
FUNNEL = REPO / "backend" / "data" / "funnel_night10.json"
FUNNEL_HISTORY = REPO / "backend" / "data" / "funnel_history"


def is_library_book(b: dict) -> bool:
    """A strategy-library rule book (`lib_*`, model `rule:strategy_library:*`)."""
    return (str(b.get("name") or "").startswith("lib_")
            or str(b.get("model") or "").startswith("rule:strategy_library:"))


def book_members(path: Path = BOOKS, *, include_library: bool = False
                 ) -> dict[str, tuple[str, str]]:
    """ticker -> (first frozen_utc, "book:<name>") over every NON-twin frozen
    book. A twin is a control, not a chosen name.

    Trigger (a) is for names a PERSON or the competition chose: the strategy
    library's rule books (adjudication 2026-09-26 row 9: 190 names that would
    eat the daily quest cap) are left out unless `include_library`."""
    out: dict[str, tuple[str, str]] = {}
    if not Path(path).exists():
        return out
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            b = json.loads(ln)
        except ValueError:
            continue
        # A twin is a control, not a chosen name -- including one whose
        # `kind` says personal but whose name or parent says twin.
        if (b.get("kind") == "twin" or b.get("twin") or b.get("parent_book_id")
                or "twin" in str(b.get("name") or "").lower() or not b.get("frozen_utc")):
            continue
        if not include_library and is_library_book(b):
            continue
        for pos in b.get("positions") or []:
            t = str((pos or {}).get("ticker") or "").upper()
            if not t or t in ("CASH", "$CASH"):
                continue
            f = str(b["frozen_utc"])
            if t not in out or f < out[t][0]:
                out[t] = (f, f"book:{b.get('name')}")
    return out


def funnel_members(current: Path = FUNNEL, history: Path = FUNNEL_HISTORY
                   ) -> dict[str, tuple[str, str]]:
    """ticker -> (generated_at of the earliest snapshot of its CURRENT unbroken
    run in the shortlist, "funnel"). A name that left and came back entered again."""
    snaps = []
    for f in sorted(Path(history).glob("*.json")) if Path(history).exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            snaps.append((str(d.get("generated_at")), {str(c.get("ticker")).upper()
                                                       for c in d.get("candidates") or []}))
        except (OSError, ValueError):
            continue
    try:
        d = json.loads(Path(current).read_text(encoding="utf-8"))
        cur = (str(d.get("generated_at")), {str(c.get("ticker")).upper()
                                            for c in d.get("candidates") or []})
    except (OSError, ValueError):
        return {}
    snaps = sorted({s[0]: s for s in snaps + [cur]}.values())
    out = {}
    for t in cur[1]:
        since = cur[0]
        for g, names in reversed(snaps):
            if g > cur[0]:
                continue
            if t in names:
                since = g
            else:
                break
        out[t] = (since, "funnel")
    return out


def _typed_event_dates(asof: date, tickers: set[str], revisions) -> dict[str, set]:
    """ticker -> dates with a TYPED event: typed_events rows (not no_event),
    web_events rows, and dated analyst revisions, over the last 10 days."""
    out: dict[str, set] = {}
    lo = asof - timedelta(days=10)
    root = Path(_cfg.OPTIMUS_LEDGER_DIR) / "typed_events"
    for f in sorted(root.glob("20*.jsonl")) if root.exists() else []:
        try:
            if date.fromisoformat(f.stem[:10]) < lo:
                continue
        except ValueError:
            continue
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("event_type") in (None, "no_event"):
                continue
            d = str(r.get("document_date") or r.get("first_seen_utc") or "")[:10]
            for t in r.get("tickers") or []:
                if str(t).upper() in tickers:
                    out.setdefault(str(t).upper(), set()).add(d)
    try:
        from backend.services import web_events as WE
        for e in WE.read_all(limit_days=15):
            t = str(e.get("ticker") or "").upper()
            if t in tickers and e.get("event_type") != "no_event_found":
                out.setdefault(t, set()).add(str(e.get("evidence_date"))[:10])
    except Exception:                                              # noqa: BLE001
        pass
    if revisions is not None and len(revisions):
        import pandas as pd
        r = revisions[pd.to_datetime(revisions["event_date"], errors="coerce", utc=True)
                      >= pd.Timestamp(lo, tz="UTC")]
        for t, d in zip(r["ticker"].astype(str).str.upper(), r["event_date"].astype(str)):
            if t in tickers:
                out.setdefault(t, set()).add(d[:10])
    return out


def trigger_list(asof: Any, *, root: Path | None = None, verbose: bool = True,
                 include_library: bool = False) -> dict:
    """Load what the five triggers read and return {"triggered": [...], ...}.
    Trigger (a) reads personal/competition books only unless `include_library`."""
    import pandas as pd
    asof_d = TC._asof_date(asof)
    uni = {u["ticker"]: u for u in default_universe()}
    books = book_members(include_library=include_library)
    funnel = funnel_members()
    last = TC.last_card_index(root=root)
    member_since: dict[str, tuple[str, str]] = {}
    for t, v in list(books.items()) + list(funnel.items()):
        if t not in member_since or v[0] < member_since[t][0]:
            member_since[t] = v
    cands = sorted(set(uni) | set(books) | set(funnel) | set(last))
    tset = set(cands)
    # (b) revision cluster, via revision_flow on PIT-safe rows only
    n_firms: dict[str, float] = {}
    revisions = None
    rp = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
    try:
        from backend.services import revision_flow as RF
        revisions = pd.read_parquet(rp)
        revisions = revisions[revisions["ticker"].astype(str).str.upper().isin(tset)]
        safe = revisions[revisions["pit_safe"].astype("boolean").fillna(False).astype(bool)]
        n_unsafe = len(revisions) - len(safe)
        if n_unsafe and verbose:
            print(f"  revisions: {n_unsafe} non-PIT-safe rows excluded from the cluster check")
        revisions = safe
        flow = RF.compute(safe, asof=pd.Timestamp(asof_d) + pd.Timedelta(days=1),
                          window_days=TC.TRIGGER_CLUSTER_DAYS)
        n_firms = flow["n_firms"].to_dict()
    except Exception as exc:                                       # noqa: BLE001
        print(f"  revision cluster UNAVAILABLE: {type(exc).__name__}: {str(exc)[:120]}")
    # (c) catalysts: the YAML + murat_book + each name's latest card's upcoming dates
    dated: dict[str, list[str]] = {}
    for c in _load_catalysts():
        t = str(c.get("ticker")).upper()
        dated.setdefault(t, []).append(f"{c['date']} | {c.get('kind', '')} | {c.get('what', '')}")
    for t, d in last.items():
        for c in TC.read_cards(d, root=root):
            if str(c.get("ticker")).upper() == t:
                dated.setdefault(t, []).extend(
                    x for x in (c.get("upcoming_dates") or []) if isinstance(x, str))
    # (d) bars
    bars = None
    try:
        from backend.services import xs_ranker as XR
        b = XR.load_bars(XR.survivorship_free_paths())
        b = b[b["symbol"].isin(tset)]
        b = b[pd.to_datetime(b["date"]) >= pd.Timestamp(asof_d) - pd.Timedelta(days=140)]
        bars = b[["symbol", "date", "close"]].copy()
    except Exception as exc:                                       # noqa: BLE001
        print(f"  bars UNAVAILABLE: {type(exc).__name__}: {str(exc)[:120]}")
    typed = _typed_event_dates(asof_d, tset, revisions)
    trig = TC.compute_triggers(cands, asof=asof_d, last_cards=last,
                               member_since=member_since, n_firms_recent=n_firms,
                               dated_events=dated, bars=bars, typed_events=typed)
    for x in trig:
        u = uni.get(x["ticker"])
        x["kind"] = u["kind"] if u else ("competition" if "competition" in
                                         str(member_since.get(x["ticker"], ("", ""))[1])
                                         else "personal")
        x["source"] = "trigger"
    res = {"asof": asof_d.isoformat(), "n_candidates": len(cands),
           "n_books_names": len(books), "n_funnel_names": len(funnel),
           "library_books": "included" if include_library else "excluded (--include-library)",
           "n_carded_names": len(last), "n_triggered": len(trig), "triggered": trig,
           "bars_names": 0 if bars is None else int(bars["symbol"].nunique()),
           "n_revision_cluster_names": sum(1 for v in n_firms.values()
                                           if v >= TC.TRIGGER_CLUSTER_FIRMS)}
    if bars is not None and len(bars):
        last_bar = pd.to_datetime(bars["date"]).max().date()
        res["bars_last_date"] = last_bar.isoformat()
        if (asof_d - last_bar).days > TC.TRIGGER_MOVE_MAX_AGE_DAYS:
            res["sigma_move_check"] = (
                f"CANNOT FIRE: bars end {last_bar}, more than "
                f"{TC.TRIGGER_MOVE_MAX_AGE_DAYS}d before {asof_d} -- (d) did not run, "
                f"which is not the same as no big moves")
    else:
        res["sigma_move_check"] = "CANNOT FIRE: no bars"
    if verbose:
        if res.get("sigma_move_check"):
            print(f"  (d) {res['sigma_move_check']}")
        print(f"triggers {res['asof']}: {len(cands)} candidates ({len(books)} book names, "
              f"{len(funnel)} funnel, {len(last)} carded; bars for {res['bars_names']}) "
              f"-> {len(trig)} triggered")
        by = {}
        for x in trig:
            for r in x["reasons"]:
                by[r[:3]] = by.get(r[:3], 0) + 1
        print("  by reason: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        for x in trig:
            print(f"  {x['ticker']:<11} last card {x['last_card'] or '-':<10} "
                  + " ; ".join(x["reasons"]))
    return res


def _claim_source_type(url: str) -> str:
    dom = TC._domain(url)
    if dom in ("x.com", "twitter.com"):
        return "x"
    if dom.endswith("sec.gov"):
        return "sec"
    return "news"


def _claim_confidence(st: str, url: str, source_list: str | None) -> str:
    dom = TC._domain(url)
    if st == "sec":
        return "REGULATOR"
    if source_list in ("x_company_posts", "x_ceo_posts"):
        return "DIRECT_COMPANY_STATEMENT"
    if st == "x":
        return "FORUM_CLAIM"
    if any(w in dom for w in getattr(TC, "_WIRES", ())):
        return "MAJOR_WIRE"
    return "AGGREGATOR"


def backfill_claim_events(day: str, *, claims_file: Path | None = None,
                          events_path: Path | None = None) -> dict:
    """Claims-ledger rows of `day` that got NO web_events row -> a generic
    `claim` web event carrying `source_id` (adjudication 2026-09-26 row 9).

    A row belongs to `day` by its card's `card_asof` or its `first_seen_utc`.
    Only rows with `web_event_refused` are read, so a claim that already has a
    typed event is never duplicated as a generic one. Idempotent: web_events
    dedupes by event_id. The claims ledger is append-only and is not edited."""
    cf = Path(claims_file) if claims_file is not None else TC.claims_path()
    rows = [r for r in TC._read_jsonl(cf)
            if r.get("web_event_refused")
            and (str(r.get("card_asof") or "")[:10] == day
                 or str(r.get("first_seen_utc") or "")[:10] == day)]
    by_day: dict[str, list[dict]] = {}
    for r in rows:
        url = str(r.get("source_url") or "")
        st = _claim_source_type(url)
        seen = str(r.get("first_seen_utc") or f"{day}T00:00:00+00:00")
        by_day.setdefault(seen[:10], []).append({
            "ticker": r.get("ticker"), "entity": r.get("source_id") or "",
            "source_type": st, "source_url": url, "event_type": "claim",
            "claim": r.get("text"), "evidence_date": r.get("claim_utc"),
            "observed_at": seen, "retrieved_by": r.get("source_id") or "openclaw:unknown",
            "source_id": r.get("source_id"),
            "confidence_source": _claim_confidence(st, url, r.get("list"))})
    tot = {"accepted": 0, "written": 0, "duplicates": 0, "refused": 0, "refusals": []}
    for d, wrows in sorted(by_day.items()):
        if events_path is None:
            from backend.services import web_events as WE
            res = WE.append(wrows, day=d)
        else:
            res = TC._local_web_events_append(wrows, Path(events_path))
        for k in ("accepted", "written", "duplicates", "refused"):
            tot[k] += int(res.get(k) or 0)
        tot["refusals"] += res.get("refusals") or []
    return {"day": day, "claims_path": str(cf), "n_candidates": len(rows), "web_events": tot}


def evidence(day: str, *, root: Path | None = None) -> dict:
    """Backfill: a day's cards -> claims + web_events + promises. $0, no LLM.
    Untyped claims then become generic `claim` web events (`backfill_claim_events`)."""
    out = {"day": day, "evidence": {}, "promises": {}}
    for c in TC.read_cards(day, root=root):
        if c.get("_unreadable") or str(c.get("verdict", "")).startswith("REFUSED_"):
            continue
        t = c["ticker"]
        out["evidence"][t] = TC.write_evidence(c)
        out["promises"][t] = TC.write_promises(c, today=datetime.now(timezone.utc).date())
    out["untyped_claims"] = backfill_claim_events(day)
    print(json.dumps(out, indent=1, default=str)[:4000])
    return out


# ─────────────────────────────── CLI ────────────────────────────────────────

def _validate(day: str, root: Path | None = None) -> int:
    cards = TC.read_cards(day, root=root)
    bad = 0
    for c in cards:
        probs = (["unreadable: " + str(c.get("_error"))] if c.get("_unreadable")
                 else TC.validate_card(c))
        name = c.get("ticker") or Path(str(c.get("_unreadable"))).stem
        if probs:
            bad += 1
            print(f"DRIFT {name}: " + "; ".join(probs))
        else:
            print(f"ok    {name}")
    print(f"{len(cards)} cards, {bad} with drift (reported, not rewritten)")
    return 0 if bad == 0 else 1


def forecast(day: str, *, root: Path | None = None, path: Path | None = None,
             today: Any = None) -> dict:
    """Backfill: every card of `day` that has no ledger rows gets them. $0, no LLM.
    Prints the ledger's row count before and after."""
    from backend.services import belief_state as B
    ledger = Path(path) if path is not None else B.PREDICTIONS
    def _n() -> int:
        if not ledger.exists():
            return 0
        with ledger.open("rb") as fh:
            return sum(1 for ln in fh if ln.strip())
    before = _n()
    cards = TC.read_cards(day, root=root)
    res = TC.write_forecasts(cards, today=today or datetime.now(timezone.utc).date(),
                             path=path)
    after = _n()
    res.update({"day": day, "ledger": str(ledger), "ledger_rows_before": before,
                "ledger_rows_after": after})
    print(f"thesis-card forecasts {day}: {res['n_cards']} cards, "
          f"{res['n_rows_written']} rows written, {res['n_already_written']} already in "
          f"the ledger, {res['n_not_a_forecast']} not a forecast "
          f"{res['not_a_forecast'][:10]}")
    print(f"ledger {ledger}: {before} rows before, {after} after")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--universe", default="default")
    r.add_argument("--max-quests", type=int, default=_cfg.THESIS_CARD_MAX_QUESTS)
    r.add_argument("--cap-usd", type=float, default=_cfg.THESIS_CARD_CAP_USD)
    r.add_argument("--parallel", type=int, default=_cfg.THESIS_CARD_PARALLEL)
    r.add_argument("--model", default=_cfg.THESIS_CARD_MODEL)
    r.add_argument("--timeout", type=float, default=_cfg.THESIS_CARD_QUEST_TIMEOUT_S)
    r.add_argument("--date", default=None, help="asof (default: today UTC)")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--retry-refused", action="store_true")
    r.add_argument("--only", default=None, help="comma list: restrict the universe")
    r.add_argument("--trigger", action="store_true",
                   help="universe = names whose card is due (a)-(e); reason on the card")
    r.add_argument("--include-library", action="store_true",
                   help="trigger (a) also reads strategy-library lib_* books (default: excluded)")
    for name in ("validate", "digest", "forecast", "evidence"):
        s = sub.add_parser(name)
        s.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    day = a.date or datetime.now(timezone.utc).date().isoformat()

    if a.cmd == "validate":
        return _validate(day)
    if a.cmd == "digest":
        print(TC.write_digest(day))
        return 0
    if a.cmd == "forecast":
        res = forecast(day)
        return 0 if res["ledger_rows_after"] - res["ledger_rows_before"] == res["n_rows_written"] else 1
    if a.cmd == "evidence":
        evidence(day)
        return 0

    if a.trigger:
        tl = trigger_list(day, include_library=a.include_library)
        uni = [{"ticker": x["ticker"], "kind": x["kind"], "source": "trigger",
                "trigger": "; ".join(x["reasons"])} for x in tl["triggered"]]
        if a.dry_run and not a.only:
            return 0
    else:
        uni = (default_universe() if a.universe == "default"
               else universe_from_file(Path(a.universe)))
    if a.only:
        want = [x.strip().upper() for x in a.only.split(",") if x.strip()]
        by = {u["ticker"]: u for u in uni}
        if a.trigger:
            missing = [t for t in want if t not in by]
            if missing:
                print(f"REFUSED_NOT_TRIGGERED: {missing} have no trigger today")
            uni = [by[t] for t in want if t in by]
        else:
            uni = [by.get(t, {"ticker": t, "kind": "personal", "source": "--only"})
                   for t in want]
    if not a.dry_run:
        from backend.services import openclaw_client as OC
        h = OC.health()
        if not h.ok:
            print(f"REFUSED_UNHEALTHY: {h.as_dict()}")
            return 2
    res = run(universe=uni, asof=day, max_quests=a.max_quests, cap_usd=a.cap_usd,
              parallel=a.parallel, model=a.model, dry_run=a.dry_run,
              retry_refused=a.retry_refused, timeout=a.timeout)
    return 0 if res["state"] in ("DONE", "DRY_RUN") else 2


if __name__ == "__main__":
    raise SystemExit(main())
