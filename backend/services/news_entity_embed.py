"""CH-46 -- news ENTITY and THEME tagging by sentence embeddings, trained on the free precise labels.

WHY
===
The ticker hub (`ticker_hub.py`, CH-22) tags news by rules in two tiers. Measured on the S69
sample: title matches and SEC filings by CIK were right every time; article-body name matches
27 %, the world digest's tickers 25 %; 82 % of collected rows name no listed company. So the
body-text tags stay in `mentions`. This module asks whether a classifier can lift some of
them to `about` at a declared precision, and leaves the rest as an `uncertain` middle that an
LLM could read later (not in this module: it makes no LLM call).

HOW
===
1. COMPANY INDEX -- one reference text per issuer-table symbol (name, aliases, sector from
   the potential universe), embedded once.
2. ROWS -- every row the hub reads (corpus jsonl + reader article pages), with the hub's own
   rule tags computed by `ticker_hub` itself (read-only import; its behaviour is unchanged).
   The title text is REMOVED from the body before anything is embedded or counted, so a
   label taken from the title cannot leak into the features.
3. LABELS -- only the precise ones: the hub's `about` tier (the title names the company, or
   an SEC filing by CIK). Negatives are the other candidates of the SAME labelled row. A row
   with no precise label is never a training row; it is the population a promotion would act
   on.
4. CANDIDATES -- top-k companies by cosine to the reference vectors, top-n by a point-in-time
   nearest-neighbour vote over earlier labelled rows, every rule mention in the body, every
   provider ticker and every digest ticker.
5. FEATURES -- cosine and its rank, the kNN vote (neighbours strictly EARLIER than the row),
   mention count and first position in the body, explicit-symbol and strict-body flags,
   provider and digest flags, the source family, body length, the row's candidate count.
6. SPLIT -- labelled rows ordered by time: train, validation, test, with an embargo after each
   boundary. Never random. Thresholds are chosen on validation; precision is reported on test.
7. DECISION -- `about` at or above the validation threshold for the declared precision,
   `reject` below the threshold that keeps 95 % of validation positives, `uncertain` between.
8. THEMES -- nearest centroid over potential-universe sectors (coverage only, no precision
   claim).

SIDECAR (how the hub would read it; NOT wired in this chunk)
=============================================================
`<out>/news_entity_embed_sidecar.jsonl`, one line per (row, candidate):
``{"schema", "row_id", "source", "eff_utc", "ticker", "score", "decision", "rule_tier",
"split", "model", "classifier"}`` -- ids, tickers and numbers only, no text. `row_id` is the
hub's own `ticker_hub.row_id`. A hub that reads it would PROMOTE a `mentions` tag to `about`
only when the line's decision is `about` AND the receipt beside it (`eval_receipt.json`)
reports a held-out `about` precision of at least `NEWS_EMBED_TARGET_PRECISION`; it would never
demote a rule `about` tag and never add a ticker the rules did not tag without a separate
review.

Licensed text (the collected corpus) is read locally and written only under `--out`, which
must be a local work folder outside any git checkout (`check_out_dir` refuses otherwise).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Protocol, Sequence

import numpy as np

from backend import config as C
from backend.services import discovery_autopsy as DA
from backend.services import event_nodes as EN
from backend.services import news_entities as NE
from backend.services import ticker_hub as TH

SCHEMA = "news-entity-embed/1"

# refusal codes (each a red, non-zero exit in the CLI)
CORPUS_MISSING = "CORPUS_MISSING"
ISSUERS_MISSING = "ISSUERS_MISSING"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
INDEX_MISSING = "INDEX_MISSING"
TOO_FEW_LABELS = "TOO_FEW_LABELS"
OUT_INSIDE_REPO = "OUT_INSIDE_REPO"

ROWS_NAME = "rows.jsonl"
ROW_EMB_NAME = "row_emb.npy"
COMPANY_NAME = "companies.json"
COMPANY_EMB_NAME = "company_emb.npy"
PAIRS_NAME = "pairs.npz"
MODEL_NAME = "classifier.json"

DECISIONS = ("about", "uncertain", "reject")

#: source family -> categorical code (fixed order: the classifier sees the code)
FAMILIES = ("benzinga", "yfinance", "sec_ex99", "sec_atom", "dj_reader", "reader_page",
            "google_news", "dj_rss", "gdelt", "social_rss", "nikkei", "other")

FEATURES = ("cos", "cos_rank_log", "cos_gap", "knn_share", "knn_max", "knn_n",
            "n_mentions", "first_pos", "mention_share", "explicit_symbol", "strict_body",
            "provider", "digest", "family", "text_len_log", "n_candidates", "n_named_in_body",
            "from_cosine", "from_knn", "from_rules")


class EmbedTagRefused(RuntimeError):
    """A stage that cannot run (missing input, no model, no labels, output inside the repo)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


# ─────────────────────────────────────────────── small helpers

def _iso(d: Optional[datetime]) -> Optional[str]:
    return None if d is None else d.astimezone(timezone.utc).isoformat(timespec="seconds")


def family_of(source: str) -> str:
    s = source or ""
    if s.startswith("alpaca_benzinga"):
        return "benzinga"
    if s.startswith("yfinance"):
        return "yfinance"
    if s.startswith("sec_edgar_8k_ex99"):
        return "sec_ex99"
    if s.startswith("sec_") or s == "reader:sec":
        return "sec_atom"
    if s.startswith("dj_reader_"):
        return "dj_reader"
    if s.startswith("reader:"):
        return "reader_page"
    if s.startswith("google_news_rss_"):
        return "google_news"
    if s.startswith(("wsj_", "mw_", "barrons_")):
        return "dj_rss"
    if s.startswith("gdelt"):
        return "gdelt"
    if s.startswith(("reddit_", "quantocracy")):
        return "social_rss"
    if s.startswith("nikkei"):
        return "nikkei"
    return "other"


def mask_title(body: str, title: str) -> str:
    """The body with every occurrence of the title (and of its first 40 characters at the
    start, a reader page's headline anchor) removed, whitespace normalised."""
    b = " ".join((body or "").split())
    t = " ".join((title or "").split())
    if not b or len(t) < 8:
        return b
    low, tl = b.casefold(), t.casefold()
    if len(low) != len(b):                      # casefold changed lengths: fall back to lower()
        low, tl = b.lower(), t.lower()
    parts, i = [], 0
    while True:
        j = low.find(tl, i)
        if j < 0:
            parts.append(b[i:])
            break
        parts.append(b[i:j])
        i = j + len(tl)
    b = " ".join("".join(parts).split())
    head = tl[:40]
    if len(head) >= 20 and b.lower().startswith(head):
        b = b[len(head):].lstrip()
    return b


def count_mentions(text: str, rule: str) -> tuple[int, float]:
    """How often the rule's key occurs in `text`, and the first occurrence's relative
    position (1.0 when absent), counted the way `ticker_hub.Tagger.body_tags` counts."""
    kind, _, key = (rule or "").partition(":")
    if not key or not text:
        return 0, 1.0
    if kind == "cased_alias":
        rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])")
        hay = text
    elif kind == "foreign_alias":
        rx = re.compile(re.escape(key))
        hay = text
    else:
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(key.lower()) + r"(?![a-z0-9])")
        hay = text.lower()
    pos = [m.start() for m in rx.finditer(hay)]
    if not pos:
        return 0, 1.0
    return len(pos), round(pos[0] / max(len(text), 1), 4)


def wilson(k: int, n: int, z: float = 1.96) -> list:
    """95 % Wilson interval for k successes in n trials ([None, None] when n == 0)."""
    if n <= 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def peak_rss_mb() -> Optional[float]:
    """This process's peak resident memory, MB (Windows PeakWorkingSetSize; POSIX ru_maxrss)."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            k32 = ctypes.WinDLL("kernel32")
            psapi = ctypes.WinDLL("psapi")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return round(pmc.PeakWorkingSetSize / 2 ** 20, 1)
            return None
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:                                                  # noqa: BLE001
        return None


def check_out_dir(out: Path) -> Path:
    """`--out` must not be inside a git checkout: rows.jsonl holds licensed text."""
    o = Path(out).resolve()
    for p in [o, *o.parents]:
        if (p / ".git").exists():
            raise EmbedTagRefused(OUT_INSIDE_REPO, f"{o} is inside the git checkout {p}; the work "
                                                   "folder holds licensed text and must be local")
    o.mkdir(parents=True, exist_ok=True)
    return o


def default_paths(data_root: Path) -> dict:
    """The hub's own input paths (same corpus, digest, CIK map and issuer table)."""
    return TH.default_paths(Path(data_root))


def check_inputs(paths: dict) -> None:
    corpus = Path(paths["corpus"])
    if not corpus.is_dir():
        raise EmbedTagRefused(CORPUS_MISSING, f"no news corpus at {corpus}")
    if not Path(paths["issuers"]).is_file():
        raise EmbedTagRefused(ISSUERS_MISSING, f"no issuer table at {paths['issuers']}")


# ─────────────────────────────────────────────── embedders

class Embedder(Protocol):
    info: dict

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class HashEmbedder:
    """A deterministic bag-of-words embedder for tests (no model, no network)."""

    def __init__(self, dim: int = 64):
        self.dim = int(dim)
        self.info = {"model_id": "hash-bow", "revision": f"dim{dim}", "licence": "n/a",
                     "device": "cpu", "pooling": "sum", "max_length": None}

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", (t or "").lower()):
                h = int(hashlib.md5(w.encode()).hexdigest()[:8], 16)
                out[i, h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return out / n


def resolve_model_dir(model_id: str, revision: str, allow_download: bool = False) -> Path:
    """The local snapshot directory of `model_id@revision` (HF cache), or a directory path."""
    p = Path(model_id)
    if p.is_dir():
        return p
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise EmbedTagRefused(MODEL_UNAVAILABLE, f"huggingface_hub not importable: {exc}") from exc
    try:
        return Path(snapshot_download(repo_id=model_id, revision=revision,
                                      local_files_only=not allow_download))
    except Exception as exc:                                           # noqa: BLE001
        raise EmbedTagRefused(MODEL_UNAVAILABLE, f"{model_id}@{revision} not in the local cache "
                                                 f"({type(exc).__name__}); pass --allow-download") from exc


class HFEmbedder:
    """A sentence encoder through plain `transformers` (CLS or mean pooling, L2-normalised)."""

    def __init__(self, model_id: str = "", revision: str = "", *, device: str = "auto",
                 threads: Optional[int] = None, batch: Optional[int] = None,
                 max_length: Optional[int] = None, pooling: Optional[str] = None,
                 allow_download: bool = False):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise EmbedTagRefused(MODEL_UNAVAILABLE, f"torch/transformers not importable: {exc}") from exc
        self.model_id = model_id or str(C.NEWS_EMBED_MODEL_ID)
        self.revision = revision or str(C.NEWS_EMBED_MODEL_REVISION)
        self.pooling = pooling or str(C.NEWS_EMBED_POOLING)
        self.max_length = int(max_length or C.NEWS_EMBED_MAX_LENGTH)
        self.batch = int(batch or C.NEWS_EMBED_BATCH)
        torch.set_num_threads(int(threads or C.NEWS_EMBED_THREADS))
        d = resolve_model_dir(self.model_id, self.revision, allow_download)
        self._torch = torch
        self.tok = AutoTokenizer.from_pretrained(str(d))
        self.model = AutoModel.from_pretrained(str(d))
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model = self.model.to(device).eval()
        if device == "cuda":
            self.model = self.model.half()
        self.info = {"model_id": self.model_id, "revision": self.revision,
                     "licence": str(C.NEWS_EMBED_MODEL_LICENCE), "device": device,
                     "pooling": self.pooling, "max_length": self.max_length,
                     "snapshot_dir": str(d), "torch": torch.__version__}

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        torch = self._torch
        outs = []
        with torch.inference_mode():
            for i in range(0, len(texts), self.batch):
                chunk = [t or " " for t in texts[i:i + self.batch]]
                b = self.tok(chunk, padding=True, truncation=True, max_length=self.max_length,
                             return_tensors="pt").to(self.device)
                h = self.model(**b).last_hidden_state
                if self.pooling == "mean":
                    m = b["attention_mask"].unsqueeze(-1).to(h.dtype)
                    v = (h * m).sum(1) / m.sum(1).clamp(min=1)
                else:
                    v = h[:, 0]
                v = torch.nn.functional.normalize(v.float(), dim=-1)
                outs.append(v.cpu().numpy().astype(np.float32))
        return np.concatenate(outs) if outs else np.zeros((0, 1), dtype=np.float32)


# ─────────────────────────────────────────────── 1. company index

def company_records(issuers: Path, universe: Optional[dict] = None) -> list[dict]:
    """One record per issuer-table symbol: name, aliases, sector (potential universe)."""
    uni = universe or {}
    out = []
    with Path(issuers).open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            s = DA.norm_ticker(row.get("symbol"))
            if not s:
                continue
            aliases = [a.strip() for a in (row.get("aliases") or "").split("|")
                       if a.strip() and a.strip().upper() != s]
            sec = (uni.get(s) or {}).get("sector")
            out.append({"symbol": s, "name": (row.get("primary_name") or "").strip(),
                        "aliases": aliases, "sector": sec if sec and sec != "N/A" else None})
    return out


def company_text(rec: dict) -> str:
    parts = [rec.get("name") or rec["symbol"]]
    al = [a for a in rec.get("aliases") or [] if a.lower() != (rec.get("name") or "").lower()]
    if al:
        parts.append("Also known as " + ", ".join(al[:4]))
    parts.append(f"Ticker {rec['symbol']}")
    if rec.get("sector"):
        parts.append(f"{rec['sector']} company")
    return ". ".join(parts) + "."


def build_company_index(out: Path, embedder: Embedder, issuers: Path,
                        universe: Optional[dict] = None) -> dict:
    recs = company_records(issuers, universe)
    if not recs:
        raise EmbedTagRefused(ISSUERS_MISSING, f"issuer table {issuers} holds no symbols")
    emb = embedder.encode([company_text(r) for r in recs]).astype(np.float32)
    np.save(Path(out) / COMPANY_EMB_NAME, emb)
    meta = {"schema": SCHEMA, "model": embedder.info, "n": len(recs), "dim": int(emb.shape[1]),
            "records": recs}
    (Path(out) / COMPANY_NAME).write_text(json.dumps(meta, ensure_ascii=True), encoding="utf-8")
    return {"companies": len(recs), "with_sector": sum(1 for r in recs if r["sector"]),
            "dim": int(emb.shape[1])}


def load_company_index(out: Path) -> tuple[list[dict], np.ndarray, dict]:
    mp, ep = Path(out) / COMPANY_NAME, Path(out) / COMPANY_EMB_NAME
    if not mp.is_file() or not ep.is_file():
        raise EmbedTagRefused(INDEX_MISSING, f"no company index in {out}: run build-index first")
    meta = json.loads(mp.read_text(encoding="utf-8"))
    return meta["records"], np.load(ep).astype(np.float32), meta


# ─────────────────────────────────────────────── 2. rows (the hub's own rules, read-only)

def _tagger_for(P: dict, cutoff_day: str, stats: Counter) -> Any:
    """A `ticker_hub.Tagger` built the way a FIRST hub build builds it over the window."""
    tbl = NE.tables(issuers=Path(P["issuers"]))
    try:
        cik_map = DA.load_cik_map(Path(P["cik_map"]))
    except Exception:                                                  # noqa: BLE001
        cik_map = {}
        stats["cik_map_unavailable"] += 1
    low, cap = Counter(), Counter()
    for src, f in TH._corpus_files(Path(P["corpus"]), cutoff_day):
        if EN.kind_of(src) == "filing":
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    _p, _r, title, _b = EN.publisher_region(src, str(o.get("title") or ""), "")
                    TH._bump_common(low, cap, title, tbl)
    common = TH.common_from_counters(low, cap)
    for k in C.EVENT_NODES_COMMON_WORD_NAMES:
        common.setdefault(str(k).lower(), {"lower": None, "capitalised": None, "listed": True})
    return TH.Tagger(tbl, cik_map, common)


def _features_from_body(tagger: Any, masked: str, src: str) -> dict:
    """Body-only evidence (title removed): lenient mentions with counts and first position,
    strict body tags, explicit symbol tokens."""
    lenient = tagger.text_tags(masked, "body") if masked else []
    ment: dict[str, list] = {}
    tok: list[str] = []
    for t in lenient:
        if t["m"] == "text_token":
            tok.append(t["t"])
            n, pos = 1, 0.0
        else:
            n, pos = count_mentions(masked, str(t.get("rule") or ""))
            n = max(n, 1)
        ment[t["t"]] = [n, pos]
    strict = sorted({t["t"] for t in tagger.body_tags(masked, src)}) if masked else []
    return {"ment": ment, "tok": sorted(set(tok)), "strict": strict}


def _row_record(src: str, kind: str, rid: str, eff: Optional[datetime], title: str, body: str,
                hub_tags: list[dict], provider: Iterable[str], digest: Iterable[str],
                tagger: Any) -> dict:
    masked = mask_title(body, title)[:int(C.TICKER_HUB_BODY_CHARS)]
    ev = _features_from_body(tagger, masked, src)
    pos = sorted({t["t"] for t in hub_tags if t.get("tier") == "about"})
    return {"id": rid, "src": src, "fam": family_of(src), "kind": kind, "eff": _iso(eff),
            "ep": int(eff.timestamp()) if eff else 0, "story": TH._sha16(TH.norm_title(title)),
            "title": title[:300], "text": masked[:int(C.NEWS_EMBED_TEXT_CHARS)], "tlen": len(masked),
            "pos": pos,
            "hub": [[t["t"], t["m"], t.get("tier"), t.get("where")] for t in hub_tags],
            "prov": sorted({DA.norm_ticker(p) for p in provider if p and tagger.known(p)}),
            "dig": sorted({DA.norm_ticker(p) for p in digest if p and tagger.known(p)}),
            **ev}


def iter_rows(P: dict, now: datetime, index_days: int, stats: Counter) -> Iterator[dict]:
    """Every row the hub reads in the window, tagged by the hub's own functions, plus the
    body-only evidence. Corpus jsonl first, then reader ARTICLE pages (front/search pages
    are headline links with no body)."""
    cutoff_day = (now - timedelta(days=index_days)).date().isoformat()
    tagger = _tagger_for(P, cutoff_day, stats)
    typed: dict = {}
    TH._update_typed(Path(P["digest"]), {}, typed, stats)
    corpus = Path(P["corpus"])
    not_news = set(getattr(C, "AUTOPSY_NOT_NEWS_TAGS", ()))
    for src, f in TH._corpus_files(corpus, cutoff_day):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    stats["bad_json_lines"] += 1
                    continue
                if not isinstance(o, dict):
                    continue
                entity = [str(t) for t in TH._as_list(o.get("entity_tags"))]
                if any(t in not_news for t in entity):
                    stats["dropped_not_news"] += 1
                    continue
                fs = DA._utc(o.get("first_seen_utc"))
                pub = DA.timed_utc(o.get("published_utc"))
                known = fs or pub
                if known is None or known > now:
                    stats["dropped_undated_or_future"] += 1
                    continue
                url = str(o.get("url") or o.get("index_url") or "")
                _publisher, _region, title, _basis = EN.publisher_region(src, str(o.get("title") or ""), url)
                if TH.is_quote_chip(title) or title.strip() == "read_next":
                    stats["dropped_chip_or_read_next"] += 1
                    continue
                hub_row = TH._corpus_row(src, o, tagger, typed, now, Counter())
                reader_row = src.startswith("dj_reader_") or str(o.get("fetcher") or "") in TH._READER_FETCHERS
                raw = str(o.get("body") or o.get("text") or "")
                if src.startswith("google_news_rss_"):
                    raw = TH._GN_STORY_LINK.sub(" ", raw)
                raw_body = EN.clean_text(raw)
                body = (TH._article_body(raw_body, title) if reader_row else raw_body)[:int(C.TICKER_HUB_BODY_CHARS)]
                rid = hub_row["id"] if hub_row else TH.row_id(src, title, url, _iso(pub))
                eff = TH.effective_utc(known, pub)
                uk = TH.url_key(url)
                ty = typed.get(uk) if uk else None
                generic = [o.get("ticker")] if o.get("ticker") else []
                prov = [str(t) for t in TH._as_list(o.get("tickers")) + generic]
                if reader_row:
                    prov = []                         # the reader's `tickers` is the lane it browsed
                stats[f"rows:{family_of(src)}"] += 1
                yield _row_record(src, EN.kind_of(src), rid, eff, title, body,
                                  hub_row["tags"] if hub_row else [], prov,
                                  (ty or {}).get("tickers") or [], tagger)
    dj = corpus / "dowjones"
    if not dj.is_dir():
        return
    for pub_dir in sorted(p for p in dj.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for day in sorted(p for p in pub_dir.iterdir() if p.is_dir() and TH._DAY.match(p.name)):
            if day.name < cutoff_day:
                continue
            for name in sorted(n for n in os.listdir(day) if n.endswith(".json")):
                try:
                    page = json.loads((day / name).read_text(encoding="utf-8", errors="replace"))
                except (OSError, ValueError):
                    stats["reader_pages_unreadable"] += 1
                    continue
                if not isinstance(page, dict) or str(page.get("page_kind") or "") != "article":
                    continue
                if str(page.get("page_class") or "OK") != "OK":
                    continue
                fs = DA._utc(page.get("first_seen_utc"))
                pub = DA.timed_utc(page.get("published_utc"))
                known = fs or pub
                if known is None or known > now:
                    stats["dropped_undated_or_future"] += 1
                    continue
                src = f"reader:{pub_dir.name}"
                title = TH._strip_publisher_suffix(str(page.get("title") or ""))
                if TH.is_quote_chip(title):
                    continue
                url = str(page.get("url") or "")
                text = TH._article_body(EN.clean_text(str(page.get("text") or "")), title)[:int(C.TICKER_HUB_BODY_CHARS)]
                hub_rows = TH._reader_rows(pub_dir.name, page, tagger, now, Counter())
                hub_tags = hub_rows[0]["tags"] if hub_rows else []
                rid = hub_rows[0]["id"] if hub_rows else TH.row_id(src, title, url, _iso(pub))
                stats[f"rows:{family_of(src)}"] += 1
                yield _row_record(src, "article", rid, TH.effective_utc(known, pub), title, text,
                                  hub_tags, [], [], tagger)


def extract_rows(P: dict, out: Path, now: datetime, index_days: int) -> dict:
    """Stream every row to `<out>/rows.jsonl` (rows without enough body are counted, not
    written). Returns the extraction receipt (counts only)."""
    check_inputs(P)
    stats: Counter = Counter()
    n = n_short = n_lab = n_hub = 0
    tmp = Path(out) / (ROWS_NAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in iter_rows(P, now, index_days, stats):
            n += 1
            if r["hub"]:
                n_hub += 1
            if r["tlen"] < int(C.NEWS_EMBED_MIN_TEXT_CHARS):
                n_short += 1
                stats[f"short:{r['fam']}"] += 1
                if r["pos"]:
                    stats[f"short_labelled:{r['fam']}"] += 1
                continue
            if r["pos"]:
                n_lab += 1
            fh.write(json.dumps(r, ensure_ascii=True, separators=(",", ":")) + "\n")
    os.replace(tmp, Path(out) / ROWS_NAME)
    return {"rows_read": n, "rows_hub_tagged": n_hub, "rows_too_short": n_short,
            "rows_written": n - n_short, "rows_labelled_written": n_lab,
            "index_days": index_days, "now": _iso(now), "counts": dict(sorted(stats.items()))}


def iter_row_file(out: Path) -> Iterator[dict]:
    p = Path(out) / ROWS_NAME
    if not p.is_file():
        raise EmbedTagRefused(INDEX_MISSING, f"no {ROWS_NAME} in {out}: run build-index first")
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def embed_rows(out: Path, embedder: Embedder, chunk: int = 4096) -> dict:
    """`rows.jsonl` -> `row_emb.npy` (float16, same order), streamed in chunks."""
    n = sum(1 for _ in iter_row_file(out))
    dim = int(embedder.encode(["probe"]).shape[1])
    tmp = Path(out) / ("tmp_" + ROW_EMB_NAME)
    mm = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.float16, shape=(max(n, 1), dim))
    buf: list[str] = []
    i = 0
    for r in iter_row_file(out):
        buf.append(r["text"])
        if len(buf) >= chunk:
            mm[i:i + len(buf)] = embedder.encode(buf).astype(np.float16)
            i += len(buf)
            buf = []
    if buf:
        mm[i:i + len(buf)] = embedder.encode(buf).astype(np.float16)
        i += len(buf)
    mm.flush()
    del mm
    os.replace(tmp, Path(out) / ROW_EMB_NAME)
    return {"rows_embedded": i, "dim": dim}


# ─────────────────────────────────────────────── 3-5. candidates and features

def knn_votes(E: np.ndarray, ep: np.ndarray, bank_idx: np.ndarray, bank_pos: list[list[int]],
              k: int, chunk: int = 512) -> list[dict]:
    """For every row, a similarity-weighted vote over its k nearest LABELLED rows that are
    strictly EARLIER (point in time; so never itself). Per row {company: [share, max, n]}."""
    out: list[dict] = [dict() for _ in range(len(E))]
    if len(bank_idx) == 0:
        return out
    order = np.argsort(ep[bank_idx], kind="stable")
    bank_idx = bank_idx[order]
    bank_ep = ep[bank_idx]
    B = np.asarray(E[bank_idx], dtype=np.float32)
    pos_sorted = [bank_pos[j] for j in order]
    q_order = np.argsort(ep, kind="stable")
    for s in range(0, len(q_order), chunk):
        qi = q_order[s:s + chunk]
        hi = int(np.searchsorted(bank_ep, ep[qi].max(), side="left"))
        if hi == 0:
            continue
        sims = np.asarray(E[qi], dtype=np.float32) @ B[:hi].T
        sims[bank_ep[None, :hi] >= ep[qi][:, None]] = -np.inf
        kk = min(k, hi)
        top = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
        for r, row in enumerate(qi):
            votes: dict[int, list] = {}
            tot = 0.0
            for j in top[r]:
                sv = float(sims[r, j])
                if not np.isfinite(sv):
                    continue
                w = max(sv, 0.0)
                tot += w
                for c in pos_sorted[j]:
                    v = votes.setdefault(c, [0.0, 0.0, 0])
                    v[0] += w
                    v[1] = max(v[1], sv)
                    v[2] += 1
            if tot > 0:
                out[int(row)] = {c: [v[0] / tot, v[1], v[2]] for c, v in votes.items()}
    return out


def build_pairs(rows: list[dict], E: np.ndarray, comp_syms: list[str], CE: np.ndarray,
                *, topk: Optional[int] = None, knn_k: Optional[int] = None,
                knn_cands: Optional[int] = None) -> dict:
    """One feature row per (row, candidate company). Labels only on labelled rows
    (1 = the hub's precise `about` tag; 0 = another candidate of the same row; -1 = no label)."""
    topk = int(topk or C.NEWS_EMBED_TOPK_COMPANIES)
    knn_k = int(knn_k or C.NEWS_EMBED_KNN_K)
    knn_cands = int(knn_cands or C.NEWS_EMBED_KNN_CANDIDATES)
    sym_ix = {s: i for i, s in enumerate(comp_syms)}
    ep = np.array([r["ep"] for r in rows], dtype=np.int64)
    lab = np.array([i for i, r in enumerate(rows) if r["pos"]], dtype=np.int64)
    bank_pos = [[sym_ix[s] for s in rows[i]["pos"] if s in sym_ix] for i in lab]
    votes = knn_votes(E, ep, lab, bank_pos, knn_k)
    fam_code = {f: i for i, f in enumerate(FAMILIES)}
    X_parts: list[np.ndarray] = []
    M_parts: list[np.ndarray] = []
    n_pos_total = n_pos_covered = 0
    nc = len(comp_syms)
    for s in range(0, len(rows), 2048):
        # per chunk: python lists for one chunk only, then a float32 block (bounded memory)
        X: list[list[float]] = []
        meta: list[tuple[int, int, int]] = []       # (row index, company index, label)
        S = np.asarray(E[s:s + 2048], dtype=np.float32) @ CE.T
        ranks = np.argsort(-S, axis=1)
        for r in range(len(S)):
            i = s + r
            row = rows[i]
            sims = S[r]
            rank_of = np.empty(nc, dtype=np.int32)
            rank_of[ranks[r]] = np.arange(1, nc + 1)
            cand: dict[int, set] = defaultdict(set)
            for c in ranks[r][:topk]:
                cand[int(c)].add("cos")
            v = votes[i]
            for c, _ in sorted(v.items(), key=lambda kv: -kv[1][0])[:knn_cands]:
                cand[int(c)].add("knn")
            ment = row.get("ment") or {}
            for sym in list(ment) + row.get("prov", []) + row.get("dig", []) + row.get("strict", []):
                if sym in sym_ix:
                    cand[sym_ix[sym]].add("rules")
            pos = {sym_ix[p] for p in row["pos"] if p in sym_ix}
            if pos:
                n_pos_total += len(pos)
                n_pos_covered += len(pos & set(cand))
            tot_m = sum(m[0] for m in ment.values())
            cl = sorted(cand)
            cs = sims[cl]
            for jc, c in enumerate(cl):
                sym = comp_syms[c]
                m = ment.get(sym) or [0, 1.0]
                best_other = float(np.max(np.delete(cs, jc))) if len(cl) > 1 else 0.0
                kv = v.get(c) or [0.0, 0.0, 0]
                X.append([float(sims[c]), math.log1p(int(rank_of[c])), float(sims[c]) - best_other,
                          float(kv[0]), float(kv[1]), float(kv[2]),
                          float(m[0]), float(m[1]), float(m[0] / tot_m) if tot_m else 0.0,
                          1.0 if sym in row.get("tok", []) else 0.0,
                          1.0 if sym in row.get("strict", []) else 0.0,
                          1.0 if sym in row.get("prov", []) else 0.0,
                          1.0 if sym in row.get("dig", []) else 0.0,
                          float(fam_code.get(row["fam"], fam_code["other"])),
                          math.log1p(int(row.get("tlen") or 0)), float(len(cl)), float(len(ment)),
                          1.0 if "cos" in cand[c] else 0.0, 1.0 if "knn" in cand[c] else 0.0,
                          1.0 if "rules" in cand[c] else 0.0])
                meta.append((i, c, (1 if c in pos else 0) if row["pos"] else -1))
        X_parts.append(np.asarray(X, dtype=np.float32).reshape(-1, len(FEATURES)))
        M_parts.append(np.asarray(meta, dtype=np.int64).reshape(-1, 3))
    Xa = np.concatenate(X_parts) if X_parts else np.zeros((0, len(FEATURES)), dtype=np.float32)
    Ma = np.concatenate(M_parts) if M_parts else np.zeros((0, 3), dtype=np.int64)
    return {"X": Xa, "row": Ma[:, 0], "comp": Ma[:, 1], "y": Ma[:, 2],
            "candidate_recall": {"precise_positives": n_pos_total, "in_candidates": n_pos_covered,
                                 "share": round(n_pos_covered / n_pos_total, 4) if n_pos_total else None}}


# ─────────────────────────────────────────────── 6. time split

def time_split(rows: list[dict], fractions: Optional[Sequence[float]] = None,
               embargo_hours: Optional[float] = None) -> tuple[np.ndarray, dict]:
    """Per row: 0 train, 1 validation, 2 test, -1 unlabelled, -2 embargoed. Labelled rows are
    ordered by time; never shuffled."""
    fr = tuple(fractions or C.NEWS_EMBED_SPLIT)
    emb = float(C.NEWS_EMBED_EMBARGO_HOURS if embargo_hours is None else embargo_hours) * 3600
    part = np.full(len(rows), -1, dtype=np.int8)
    lab = [i for i, r in enumerate(rows) if r["pos"]]
    if len(lab) < 30:
        raise EmbedTagRefused(TOO_FEW_LABELS, f"{len(lab)} labelled rows; a split needs at least 30")
    eps = np.array(sorted(rows[i]["ep"] for i in lab))
    b1 = int(eps[int(len(eps) * fr[0])])
    b2 = int(eps[int(len(eps) * (fr[0] + fr[1]))])
    for i in lab:
        e = rows[i]["ep"]
        if e < b1:
            part[i] = 0
        elif e < b2:
            part[i] = 1 if e >= b1 + emb else -2
        else:
            part[i] = 2 if e >= b2 + emb else -2
    info = {"boundary_val_utc": _iso(datetime.fromtimestamp(b1, timezone.utc)),
            "boundary_test_utc": _iso(datetime.fromtimestamp(b2, timezone.utc)),
            "embargo_hours": emb / 3600, "fractions": list(fr),
            "rows": {k: int((part == v).sum()) for k, v in
                     (("train", 0), ("validation", 1), ("test", 2), ("embargoed", -2), ("unlabelled", -1))}}
    return part, info


# ─────────────────────────────────────────────── 7. classifier and thresholds

def fit_classifier(X: np.ndarray, y: np.ndarray, seed: Optional[int] = None) -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier
    fam = FEATURES.index("family")
    clf = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31,
                                         l2_regularization=1.0, min_samples_leaf=40,
                                         categorical_features=[fam],
                                         random_state=int(C.NEWS_EMBED_SEED if seed is None else seed))
    clf.fit(X, y)
    return clf


def choose_thresholds(scores: np.ndarray, y: np.ndarray, target: Optional[float] = None,
                      reject_pos_share: Optional[float] = None, min_n: Optional[int] = None) -> dict:
    """`about`: the lowest score whose pairs at or above it reach the target precision (with at
    least `min_n` of them). `reject`: the score below which at most `reject_pos_share` of the
    positives lie. Both chosen on VALIDATION pairs only."""
    target = float(C.NEWS_EMBED_TARGET_PRECISION if target is None else target)
    share = float(C.NEWS_EMBED_REJECT_POS_SHARE if reject_pos_share is None else reject_pos_share)
    min_n = int(C.NEWS_EMBED_MIN_ABOUT_N if min_n is None else min_n)
    o = np.argsort(-scores, kind="stable")
    ys, ss = y[o], scores[o]
    cum = np.cumsum(ys)
    prec = cum / np.arange(1, len(ys) + 1)
    t_about, k_at = None, None
    for j in range(len(ss) - 1, -1, -1):
        if j + 1 >= min_n and prec[j] >= target and (j == len(ss) - 1 or ss[j] != ss[j + 1]):
            t_about, k_at = float(ss[j]), j + 1
            break
    pos_scores = np.sort(scores[y == 1])
    t_rej = float(pos_scores[int(len(pos_scores) * share)]) if len(pos_scores) else 0.5
    if t_about is not None and t_rej > t_about:
        t_rej = t_about
    return {"about": t_about, "reject": t_rej, "target_precision": target,
            "reject_positive_share": share, "validation_pairs": int(len(y)),
            "validation_about_n": k_at,
            "validation_about_precision": round(float(prec[k_at - 1]), 4) if k_at else None,
            "status": "OK" if t_about is not None else "TARGET_UNREACHABLE"}


def thresholds_by_family(scores: np.ndarray, y: np.ndarray, fams: np.ndarray, fallback: dict) -> dict:
    """Variant 2: one validation threshold pair per source family; a family whose validation
    pairs cannot reach the target with `NEWS_EMBED_MIN_ABOUT_N` pairs keeps the global pair."""
    out = {}
    for f in sorted(set(fams.tolist())):
        m = fams == f
        th = choose_thresholds(scores[m], y[m]) if int((y[m] == 1).sum()) else {"status": "NO_POSITIVES"}
        out[f] = th if th.get("status") == "OK" else {**fallback, "status": f"GLOBAL_FALLBACK:{th.get('status')}"}
    return out


def decide_by_family(scores: np.ndarray, fams: np.ndarray, by: dict, fallback: dict) -> np.ndarray:
    out = np.full(len(scores), "reject", dtype=object)
    for f in sorted(set(fams.tolist())):
        m = fams == f
        out[m] = decide(scores[m], by.get(f, fallback))
    return out


def decide(scores: np.ndarray, th: dict) -> np.ndarray:
    out = np.full(len(scores), "reject", dtype=object)
    out[scores >= th["reject"]] = "uncertain"
    if th.get("about") is not None:
        out[scores >= th["about"]] = "about"
    return out


def prec_rec(dec: np.ndarray, y: np.ndarray, n_pos_total: int) -> dict:
    a = dec == "about"
    tp = int((a & (y == 1)).sum())
    n = int(a.sum())
    return {"about_n": n, "about_tp": tp, "precision": round(tp / n, 4) if n else None,
            "precision_ci95": wilson(tp, n), "positives": int(n_pos_total),
            "recall": round(tp / n_pos_total, 4) if n_pos_total else None,
            "uncertain_n": int((dec == "uncertain").sum()), "reject_n": int((dec == "reject").sum())}


# ─────────────────────────────────────────────── 8. themes

def theme_centroids(records: list[dict], CE: np.ndarray,
                    min_companies: Optional[int] = None) -> tuple[list[str], np.ndarray]:
    m = int(min_companies or C.NEWS_EMBED_THEME_MIN_COMPANIES)
    by: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        if r.get("sector"):
            by[r["sector"]].append(i)
    names = sorted(k for k, v in by.items() if len(v) >= m)
    if not names:
        return [], np.zeros((0, CE.shape[1]), dtype=np.float32)
    cent = np.stack([CE[by[k]].mean(0) for k in names]).astype(np.float32)
    cent /= np.linalg.norm(cent, axis=1, keepdims=True).clip(min=1e-9)
    return names, cent


def assign_themes(E: np.ndarray, names: list[str], cent: np.ndarray,
                  margin: Optional[float] = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(best theme index, best cosine, margin over the second) per row; -1 when not covered."""
    mg = float(C.NEWS_EMBED_THEME_MARGIN if margin is None else margin)
    if len(names) < 2:
        return np.full(len(E), -1), np.zeros(len(E)), np.zeros(len(E))
    best, cos, gap = [], [], []
    for s in range(0, len(E), 4096):
        S = np.asarray(E[s:s + 4096], dtype=np.float32) @ cent.T
        o = np.argsort(-S, axis=1)[:, :2]
        b = S[np.arange(len(S)), o[:, 0]]
        g = b - S[np.arange(len(S)), o[:, 1]]
        best.append(np.where(g >= mg, o[:, 0], -1))
        cos.append(b)
        gap.append(g)
    return np.concatenate(best), np.concatenate(cos), np.concatenate(gap)


# ─────────────────────────────────────────────── the `tag` stage

def _group_table(rows: list[dict], P: dict, part: np.ndarray, dec: np.ndarray, key) -> dict:
    """Held-out (test) precision/recall per group (source family or month)."""
    groups: dict[str, dict] = defaultdict(lambda: {"about_n": 0, "about_tp": 0, "positives_in_candidates": 0,
                                                   "uncertain_n": 0, "pairs": 0})
    test = part[P["row"]] == 2
    for j in np.nonzero(test)[0]:
        g = groups[key(rows[int(P["row"][j])])]
        g["pairs"] += 1
        if P["y"][j] == 1:
            g["positives_in_candidates"] += 1
        if dec[j] == "about":
            g["about_n"] += 1
            g["about_tp"] += int(P["y"][j] == 1)
        elif dec[j] == "uncertain":
            g["uncertain_n"] += 1
    out = {}
    for k, g in sorted(groups.items()):
        out[k] = {**g, "precision": round(g["about_tp"] / g["about_n"], 4) if g["about_n"] else None,
                  "precision_ci95": wilson(g["about_tp"], g["about_n"]),
                  "recall_in_candidates": (round(g["about_tp"] / g["positives_in_candidates"], 4)
                                           if g["positives_in_candidates"] else None)}
    return out


def _dedup_mask(rows: list[dict], P: dict, sel: np.ndarray) -> np.ndarray:
    """The first pair per (story, ticker) among `sel` (the same headline in several feeds or
    editions counts once)."""
    keep = np.zeros(len(sel), dtype=bool)
    seen: set = set()
    for j in np.nonzero(sel)[0]:
        k = (rows[int(P["row"][j])].get("story"), int(P["comp"][j]))
        if k not in seen:
            seen.add(k)
            keep[j] = True
    return keep


def tag(out: Path) -> dict:
    """Features, classifier, thresholds, decisions, sidecars and the metric part of the receipt."""
    t0 = time.time()
    out = Path(out)
    records, CE, cmeta = load_company_index(out)
    comp_syms = [r["symbol"] for r in records]
    ep_path = out / ROW_EMB_NAME
    if not ep_path.is_file():
        raise EmbedTagRefused(INDEX_MISSING, f"no {ROW_EMB_NAME} in {out}: run build-index first")
    rows = []
    for r in iter_row_file(out):
        r.pop("text", None)
        r.pop("title", None)
        rows.append(r)
    E = np.load(ep_path, mmap_mode="r")
    if len(E) != len(rows):
        raise EmbedTagRefused(INDEX_MISSING, f"{len(E)} embeddings for {len(rows)} rows: re-run build-index")
    part, split = time_split(rows)
    P = build_pairs(rows, E, comp_syms, CE)
    rp = part[P["row"]]
    tr, va, te = (rp == 0), (rp == 1), (rp == 2)
    if int(P["y"][tr].sum()) == 0 or int((P["y"][tr] == 0).sum()) == 0:
        raise EmbedTagRefused(TOO_FEW_LABELS, "the training pairs hold one class only")
    clf = fit_classifier(P["X"][tr], P["y"][tr])
    scores = clf.predict_proba(P["X"])[:, 1].astype(np.float32)
    th = choose_thresholds(scores[va], P["y"][va])
    dec = decide(scores, th)
    # recall counts the precise positives the candidate generator never offered, too
    n_pos_test = sum(len(r["pos"]) for i, r in enumerate(rows) if part[i] == 2)
    held = prec_rec(dec[te], P["y"][te], n_pos_test)
    held["positives_in_candidates"] = int((P["y"][te] == 1).sum())
    dd = _dedup_mask(rows, P, te)
    held_dedup = prec_rec(dec[dd], P["y"][dd], int((P["y"][dd] == 1).sum()))
    held_dedup["note"] = "first pair per (story, ticker); recall here is within candidates"
    no_sec = te & ~np.isin(np.array([rows[int(i)]["fam"] for i in P["row"]]), ("sec_ex99", "sec_atom"))
    va_no_sec = va & ~np.isin(np.array([rows[int(i)]["fam"] for i in P["row"]]), ("sec_ex99", "sec_atom"))
    held_news = prec_rec(dec[no_sec], P["y"][no_sec], int((P["y"][no_sec] == 1).sum()))
    held_news["note"] = "test pairs without SEC filings; recall here is within candidates"
    held_val = prec_rec(dec[va], P["y"][va], sum(len(r["pos"]) for i, r in enumerate(rows) if part[i] == 1))
    # variant 2 (per-family thresholds, chosen on validation). DISCLOSED: added after variant 1's
    # held-out by-source table was seen, so its test number is not an untouched held-out number.
    pair_fam = np.array([rows[int(i)]["fam"] for i in P["row"]], dtype=object)
    th_fam = thresholds_by_family(scores[va], P["y"][va], pair_fam[va], th)
    dec2 = decide_by_family(scores, pair_fam, th_fam, th)
    v2 = {"thresholds_by_family": th_fam,
          "held_out_test": prec_rec(dec2[te], P["y"][te], n_pos_test),
          "held_out_test_without_sec": prec_rec(dec2[no_sec], P["y"][no_sec], int((P["y"][no_sec] == 1).sum())),
          "held_out_by_source": _group_table(rows, P, part, dec2, lambda r: r["fam"]),
          "decisions_all_pairs": dict(Counter(dec2.tolist())),
          "uncertain_rows": len({int(P["row"][j]) for j in np.nonzero(dec2 == "uncertain")[0]}),
          "caveat": "chosen after the variant-1 held-out by-source table was seen; not a clean held-out number"}
    # rule-tier agreement over every pair (labelled or not)
    rule: dict[str, Counter] = defaultdict(Counter)
    rule_unl: dict[str, Counter] = defaultdict(Counter)
    for j in range(len(dec)):
        row = rows[int(P["row"][j])]
        sym = comp_syms[int(P["comp"][j])]
        h = {x[0]: x for x in row["hub"]}.get(sym)
        if h is None:
            k = "no_rule_tag"
        elif h[2] == "about":
            k = "rule_about"
        elif h[1] == "digest_typed":
            k = "rule_mentions_digest"
        elif h[3] == "body":
            k = "rule_mentions_body"
        else:
            k = f"rule_mentions_{h[1]}"
        rule[k][dec[j]] += 1
        if rp[j] == -1:
            rule_unl[k][dec[j]] += 1
    agree = {k: {**dict(v), "pairs": sum(v.values())} for k, v in sorted(rule.items())}
    agree_unl = {k: {**dict(v), "pairs": sum(v.values())} for k, v in sorted(rule_unl.items())}
    # sidecars (ids, tickers, numbers; no text)
    clf_sha = hashlib.sha256(json.dumps({"th": th, "n": int(tr.sum()), "feat": list(FEATURES)},
                                        sort_keys=True).encode()).hexdigest()[:16]
    model_tag = f"{cmeta['model'].get('model_id')}@{str(cmeta['model'].get('revision'))[:12]}"
    sc = out / str(C.NEWS_EMBED_SIDECAR_NAME)
    with open(str(sc) + ".tmp", "w", encoding="utf-8") as fh:
        for j in range(len(dec)):
            row = rows[int(P["row"][j])]
            sym = comp_syms[int(P["comp"][j])]
            h = {x[0]: x for x in row["hub"]}.get(sym)
            fh.write(json.dumps({"schema": SCHEMA, "row_id": row["id"], "source": row["src"],
                                 "eff_utc": row["eff"], "ticker": sym, "score": round(float(scores[j]), 4),
                                 "decision": str(dec[j]), "decision_v2": str(dec2[j]),
                                 "rule_tier": h[2] if h else None,
                                 "split": int(rp[j]), "model": model_tag, "classifier": clf_sha},
                                separators=(",", ":")) + "\n")
    os.replace(str(sc) + ".tmp", sc)
    names, cent = theme_centroids(records, CE)
    best, bcos, gap = assign_themes(E, names, cent)
    tc = out / str(C.NEWS_EMBED_THEME_SIDECAR_NAME)
    cov, tot = Counter(), Counter()
    with open(str(tc) + ".tmp", "w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            tot[r["fam"]] += 1
            if best[i] >= 0:
                cov[r["fam"]] += 1
            fh.write(json.dumps({"row_id": r["id"], "theme": names[int(best[i])] if best[i] >= 0 else None,
                                 "cos": round(float(bcos[i]), 4), "margin": round(float(gap[i]), 4)},
                                separators=(",", ":")) + "\n")
    os.replace(str(tc) + ".tmp", tc)
    # the uncertain middle = the LLM budget question (no call is made here)
    unc_rows = {int(P["row"][j]) for j in np.nonzero(dec == "uncertain")[0]}
    unc_rows_unl = {int(P["row"][j]) for j in np.nonzero((dec == "uncertain") & (rp == -1))[0]}
    # distinct calendar days that carry rows inside the collection window (a row whose source
    # stamps a years-old published time is still a row collected in the window; it must not
    # stretch the denominator)
    ep_max = max(r["ep"] for r in rows)
    lo = ep_max - int(C.TICKER_HUB_INDEX_DAYS) * 86400
    days = float(max(1, len({(r["eff"] or "")[:10] for r in rows if r.get("eff") and r["ep"] >= lo})))
    n_old = sum(1 for r in rows if r["ep"] < lo)
    price = dict((getattr(C, "LLM_PRICE_PER_MTOK", {}) or {}).get(str(C.NEWS_EMBED_LLM_PRICE_MODEL)) or {})
    tin, tout = int(C.NEWS_EMBED_LLM_IN_TOKENS_PER_ROW), int(C.NEWS_EMBED_LLM_OUT_TOKENS_PER_ROW)

    def _usd(n: int) -> Optional[float]:
        if not price:
            return None
        return round(n * (tin * float(price.get("in", 0)) + tout * float(price.get("out", 0))) / 1e6, 4)

    np.savez_compressed(out / PAIRS_NAME, X=P["X"], row=P["row"], comp=P["comp"], y=P["y"],
                        score=scores, part=part)
    imp = _feature_importance(clf, P["X"][va], P["y"][va])
    model_json = {"schema": SCHEMA, "thresholds": th, "classifier_sha": clf_sha, "features": list(FEATURES),
                  "families": list(FAMILIES), "model": cmeta["model"], "train_pairs": int(tr.sum()),
                  "permutation_importance_validation": imp}
    (out / MODEL_NAME).write_text(json.dumps(model_json, indent=1), encoding="utf-8")
    return {
        "rows_classified": len(rows), "pairs": int(len(dec)),
        "pairs_by_part": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum()),
                          "unlabelled": int((rp == -1).sum()), "embargoed": int((rp == -2).sum())},
        "positives_by_part": {"train": int(P["y"][tr].sum()), "validation": int(P["y"][va].sum()),
                              "test": int(P["y"][te].sum())},
        "split": split, "candidate_recall_all_labelled": P["candidate_recall"],
        "thresholds": th, "validation": held_val, "held_out_test": held,
        "held_out_test_dedup_stories": held_dedup, "held_out_test_without_sec": held_news,
        "validation_without_sec": prec_rec(dec[va_no_sec], P["y"][va_no_sec], int((P["y"][va_no_sec] == 1).sum())),
        "variant_2_per_family_thresholds": v2,
        "variants_tried": 2,
        "held_out_by_source": _group_table(rows, P, part, dec, lambda r: r["fam"]),
        "held_out_by_month": _group_table(rows, P, part, dec, lambda r: (r["eff"] or "")[:7]),
        "decisions_all_pairs": dict(Counter(dec.tolist())),
        "agreement_with_rule_tiers_all_pairs": agree,
        "agreement_with_rule_tiers_unlabelled_rows": agree_unl,
        "uncertain_middle": {"pairs": int((dec == "uncertain").sum()), "rows": len(unc_rows),
                             "rows_unlabelled_only": len(unc_rows_unl),
                             "window_days": round(days, 1), "rows_per_day": round(len(unc_rows) / days, 1),
                             "rows_dated_before_window": n_old,
                             "est_in_tokens_per_row": tin, "est_out_tokens_per_row": tout,
                             "price_model": str(C.NEWS_EMBED_LLM_PRICE_MODEL), "price_per_mtok": price,
                             "est_usd_whole_window": _usd(len(unc_rows)),
                             "est_usd_per_day": (round(_usd(len(unc_rows)) / days, 4)
                                                 if price else None)},
        "themes": {"declared": names, "n_themes": len(names),
                   "covered_rows": int((best >= 0).sum()), "rows": len(rows),
                   "coverage": round(float((best >= 0).mean()), 4) if len(rows) else None,
                   "coverage_by_source": {k: round(cov[k] / tot[k], 4) for k in sorted(tot)},
                   "margin": float(C.NEWS_EMBED_THEME_MARGIN), "precision_claim": "none"},
        "feature_importance_validation": imp,
        "tag_elapsed_s": round(time.time() - t0, 1),
    }


def _feature_importance(clf: Any, X: np.ndarray, y: np.ndarray) -> dict:
    """Permutation importance on validation (average-precision drop), capped sample."""
    try:
        from sklearn.inspection import permutation_importance
        n = min(len(y), 20000)
        rng = np.random.default_rng(int(C.NEWS_EMBED_SEED))
        idx = rng.choice(len(y), n, replace=False) if len(y) > n else np.arange(len(y))
        r = permutation_importance(clf, X[idx], y[idx], scoring="average_precision", n_repeats=3,
                                   random_state=int(C.NEWS_EMBED_SEED))
        return {f: round(float(m), 4) for f, m in sorted(zip(FEATURES, r.importances_mean), key=lambda t: -t[1])}
    except Exception as exc:                                           # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}


# ─────────────────────────────────────────────── evaluation sheets and the self-audit

def _load_scored(out: Path) -> tuple[dict, dict, list[str], dict]:
    out = Path(out)
    d = dict(np.load(out / PAIRS_NAME))
    th = json.loads((out / MODEL_NAME).read_text(encoding="utf-8"))["thresholds"]
    records, _CE, _m = load_company_index(out)
    return d, th, [r["symbol"] for r in records], {r["symbol"]: r["name"] for r in records}


def _row_texts(out: Path, want: set) -> dict[int, dict]:
    got = {}
    for i, r in enumerate(iter_row_file(out)):
        if i in want:
            got[i] = {"id": r["id"], "src": r["src"], "fam": r["fam"], "eff": r["eff"],
                      "title": r["title"], "text": r["text"], "hub": r["hub"]}
    return got


def labelling_sheet(out: Path, n: int = 300, seed: Optional[int] = None) -> dict:
    """A stratified sample of (row, ticker) pairs from rows NOT used in training (validation,
    test, unlabelled), a third per decision band, spread over source families. Written with
    the row text for LOCAL reading under `out` only."""
    d, th, comp_syms, names = _load_scored(out)
    part, rowix, comp, score = d["part"], d["row"], d["comp"], d["score"]
    dec = decide(score, th)
    elig = np.nonzero(np.isin(part[rowix], (1, 2, -1)))[0]
    fam = [r["fam"] for r in iter_row_file(out)]
    rng = np.random.default_rng(int(C.NEWS_EMBED_SEED if seed is None else seed))
    picked: list[int] = []
    for band in DECISIONS:
        by: dict[str, list[int]] = defaultdict(list)
        for j in elig[dec[elig] == band]:
            by[fam[int(rowix[j])]].append(int(j))
        take: list[int] = []
        while len(take) < n // 3 and any(by.values()):
            for f in sorted(by):
                if by[f] and len(take) < n // 3:
                    take.append(by[f].pop(int(rng.integers(len(by[f])))))
        picked += take
    texts = _row_texts(out, {int(rowix[j]) for j in picked})
    path = Path(out) / "labelling_sheet_300.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair", "row_id", "source", "eff_utc", "ticker", "company", "score", "decision",
                    "split", "title", "text", "label_about_1_0"])
        for j in picked:
            i = int(rowix[j])
            t = texts[i]
            sym = comp_syms[int(comp[j])]
            w.writerow([j, t["id"], t["src"], t["eff"], sym, names.get(sym), round(float(score[j]), 4),
                        dec[j], int(part[i]), t["title"], t["text"][:600], ""])
    return {"path": str(path), "pairs": len(picked),
            "by_decision": dict(Counter(dec[picked].tolist())),
            "by_source": dict(Counter(fam[int(rowix[j])] for j in picked)),
            "labelled": "awaits an independent labeller"}


def audit_sheet(out: Path, n_each: int = 30, seed: Optional[int] = None) -> dict:
    """Disagreements with the rule tagger, on UNLABELLED rows only (never trained on, and the
    population a promotion would act on):
    PROMOTE = classifier `about` where the rules gave `mentions` or nothing;
    DEMOTE  = classifier `reject` where the rules gave a body-match or digest `mentions` tag."""
    d, th, comp_syms, names = _load_scored(out)
    part, rowix, comp, score = d["part"], d["row"], d["comp"], d["score"]
    dec = decide(score, th)
    hub_by_row = {i: {h[0]: h for h in r["hub"]} for i, r in enumerate(iter_row_file(out))}
    promote, demote = [], []
    for j in range(len(dec)):
        i = int(rowix[j])
        if part[i] != -1:
            continue
        h = hub_by_row[i].get(comp_syms[int(comp[j])])
        if dec[j] == "about" and (h is None or h[2] != "about"):
            promote.append(j)
        elif dec[j] == "reject" and h is not None and h[2] == "mentions" and (h[3] == "body" or h[1] == "digest_typed"):
            demote.append(j)
    rng = np.random.default_rng(int(C.NEWS_EMBED_SEED if seed is None else seed) + 1)
    pp = sorted(rng.choice(promote, min(n_each, len(promote)), replace=False).tolist()) if promote else []
    dd = sorted(rng.choice(demote, min(n_each, len(demote)), replace=False).tolist()) if demote else []
    texts = _row_texts(out, {int(rowix[j]) for j in pp + dd})
    path = Path(out) / "self_audit_sheet.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair", "kind", "row_id", "source", "ticker", "company", "score", "rule_tag",
                    "title", "text"])
        for kind, js in (("PROMOTE", pp), ("DEMOTE", dd)):
            for j in js:
                i = int(rowix[j])
                sym = comp_syms[int(comp[j])]
                h = hub_by_row[i].get(sym)
                w.writerow([j, kind, texts[i]["id"], texts[i]["src"], sym, names.get(sym),
                            round(float(score[j]), 4), "/".join(str(x) for x in h) if h else "",
                            texts[i]["title"], texts[i]["text"][:700]])
    return {"path": str(path), "promote_pool": len(promote), "demote_pool": len(demote),
            "promote_sampled": len(pp), "demote_sampled": len(dd),
            "promote_pool_rows": len({int(rowix[j]) for j in promote})}


def read_self_audit(out: Path) -> Optional[dict]:
    """`<out>/self_audit_labels.csv` (pair, kind, label 1/0): the BUILDER's own labels.
    PROMOTE label 1 = the row IS about the ticker (promotion right); DEMOTE label 1 = the row
    IS about the ticker (the classifier's reject was wrong)."""
    p = Path(out) / "self_audit_labels.csv"
    if not p.is_file():
        return None
    res: dict[str, Counter] = defaultdict(Counter)
    with open(p, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            lab = str(row.get("label") or "").strip()
            if lab in ("0", "1"):
                res[row["kind"]][lab] += 1
    out_d: dict[str, Any] = {}
    for kind, c in sorted(res.items()):
        n = c["0"] + c["1"]
        out_d[kind] = {"n": n, "about_true": c["1"], "about_false": c["0"],
                       "share_about_true": round(c["1"] / n, 4) if n else None,
                       "ci95": wilson(c["1"], n)}
    out_d["labeller"] = "the builder (an AI agent) -- not an independent labeller"
    return out_d
