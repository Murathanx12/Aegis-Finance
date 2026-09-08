"""R7 -- LEARN A REPRESENTATION OF NEWS WITHOUT RETURNS, THEN ASK IT ABOUT RETURNS.

THE DESIGN, IN ONE PARAGRAPH
===========================
Return labels are scarce and noisy: on the panel this repo actually owns there
are ~10k labelled (permno, month) cells that carry any news at all, and one
number of forward excess return each. There are 524,210 unlabelled news
documents. So the labelled signal is spent on a SMALL head, and the unlabelled
text pays for the REPRESENTATION: a small transformer encoder is pre-trained
from scratch on headlines with two self-supervised objectives that never see a
return -- masked-token reconstruction, and a same-company/different-company
contrastive pair. Then a small ridge head is fitted on forward returns,
walk-forward, purged, with an embargo.

WHAT MAKES THE COMPARISON DECIDE ANYTHING
=========================================
The pre-trained representation must beat, on the SAME folds, the SAME target and
the SAME head:

  (a) the identical encoder with RANDOM frozen weights (no pre-training);
  (b) TF-IDF over the identical aggregated text;
  (c) coverage alone (the document count), which is the thing Murat keeps
      warning about: a name with more news is not a name with more signal.

If it does not beat TF-IDF, that is the result and it is reported as the result.

THE LEAK GATE
=============
Two different leaks, two different gates, because they are not the same failure:

  1. MY OWN ENCODER can see the future through the corpus. A pre-train over
     2015-2026 text, evaluated on a 2018 fold, has read 2019-2026 headlines.
     So two encoders are trained: `pit` (text strictly before the evaluation
     window) and `full` (all text). The difference between them IS the leak,
     measured rather than assumed.
  2. THE 7B has a real training cutoff. Qwen2.5 was trained to ~2023; the
     Gao-Jiang-Yan test asks whether accuracy DROPS after the cutoff, which is
     the signature of memory rather than skill. Plus a canary: a separate call
     must not be able to name the company or the year from the masked text.
     AMNESIA-1 measured that telling a model to forget does nothing, so memory
     is measured here and never instructed away.

    python -m scripts.r7_news_representation --build-docs
    python -m scripts.r7_news_representation --build-panel
    python -m scripts.r7_news_representation --pretrain pit|full
    python -m scripts.r7_news_representation --evaluate
    python -m scripts.r7_news_representation --leak-gate
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP  # noqa: E402

TERMINAL_REPO = Path(r"C:\Users\mrthn\aegis-alpha-terminal")  # READ ONLY
CORPUS_OBS_DIR = TERMINAL_REPO / "state" / "corpus" / "observations"
STOCKNAMES = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__stocknames_v2.parquet"
TRAIN_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"

OUT_DIR = REPO / "backend" / "data" / "optimus" / "r7_news_representation"
DOCS_PARQUET = OUT_DIR / "docs.parquet"
PANEL_PARQUET = OUT_DIR / "panel.parquet"

TARGET = "excess_vw_1m"

# The label panel's own ceiling. train_table.parquet ends 2024-12; 2025-2026 news
# is therefore PRE-TRAINING ONLY and can never be scored. Stated, not discovered.
LABEL_LAST_MONTH = "2024-12"


# --------------------------------------------------------------- refusals

class R7Refusal(RuntimeError):
    """A missing input is a refusal that names what is missing, never a silent skip."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------ text handling

_TOKEN_RE = re.compile(r"[a-z0-9$%\.\-']+")
_HTML_ENT = re.compile(r"&#?\w+;")
_TAG = re.compile(r"<[^>]+>")


def normalise_text(title: str | None, body: str | None, *, body_chars: int = 300) -> str:
    """Title plus a bounded slice of body. 61% of documents carry NO body at all
    (measured: 319,896 of 524,210), so this is headline-level modelling and the
    receipt says so rather than implying full-article text exists."""
    t = (title or "").strip()
    b = (body or "").strip()
    if b:
        b = _TAG.sub(" ", b)
        b = _HTML_ENT.sub(" ", b)
        b = b[:body_chars]
    joined = (t + " . " + b).strip() if b else t
    joined = _HTML_ENT.sub(" ", _TAG.sub(" ", joined))
    return re.sub(r"\s+", " ", joined).strip()


def tokenise(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# --------------------------------------------------------------- build docs

def build_docs(*, limit_files: int | None = None) -> dict:
    """One row per news document. NO returns are read by this function."""
    if not CORPUS_OBS_DIR.is_dir():
        raise R7Refusal(
            f"news corpus absent: {CORPUS_OBS_DIR}. It lives in the TERMINAL repo and is "
            "read-only from here; run the puller there (scripts/news_backfill.py)."
        )
    tracker = RP.InputTracker()
    shards = sorted(CORPUS_OBS_DIR.glob("*.jsonl"))
    if limit_files:
        shards = shards[:limit_files]
    if not shards:
        raise R7Refusal(f"no .jsonl shards under {CORPUS_OBS_DIR}")

    rows: list[tuple] = []
    n_lines = n_torn = 0
    for p in shards:
        tracker.opened(p, note="news corpus shard (terminal repo, read-only)")
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n_lines += 1
                try:
                    d = json.loads(line)
                except Exception:
                    n_torn += 1
                    continue
                if d.get("kind") != "news" or d.get("tense") != "past":
                    continue
                syms = d.get("symbols") or []
                if not syms:
                    continue
                text = normalise_text(d.get("title"), d.get("body"))
                if len(text) < 8:
                    continue
                oa = d.get("observed_at") or ""
                rows.append((
                    d.get("uid") or "",
                    oa,
                    "|".join(str(s).upper() for s in syms[:8]),
                    str(d.get("source") or ""),
                    str(d.get("independence_group") or ""),
                    text,
                    1 if (d.get("body") or "").strip() else 0,
                ))

    df = pd.DataFrame(rows, columns=["uid", "observed_at", "symbols", "source",
                                     "independence_group", "text", "has_body"])
    df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce", utc=True)
    df = df[df["observed_at"].notna()].copy()
    df["month"] = df["observed_at"].dt.tz_convert("UTC").dt.strftime("%Y-%m")
    df = df.drop_duplicates(subset=["uid"]).reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DOCS_PARQUET, index=False)

    by_year = df["month"].str[:4].value_counts().sort_index().to_dict()
    receipt = {
        "job": "r7_build_docs",
        "at": _now(),
        "shards": len(shards),
        "lines_read": n_lines,
        "torn_lines_skipped": n_torn,
        "documents": int(len(df)),
        "documents_with_body": int(df["has_body"].sum()),
        "documents_title_only": int((1 - df["has_body"]).sum()),
        "body_share": round(float(df["has_body"].mean()), 4),
        "by_year": {k: int(v) for k, v in by_year.items()},
        "distinct_first_symbols": int(df["symbols"].str.split("|").str[0].nunique()),
        "median_chars": int(df["text"].str.len().median()),
        "out": str(DOCS_PARQUET),
        "note": ("61% of documents carry no body. This is HEADLINE-level modelling. "
                 "No return is read by this step."),
    }
    RP.attach(receipt, sys.argv, {"shards": len(shards), "body_chars": 300}, tracker)
    _write_json(OUT_DIR / "R7_docs_receipt.json", receipt)
    return receipt


# --------------------------------------------------------------- the panel

def _crosswalk() -> pd.DataFrame:
    if not STOCKNAMES.is_file():
        raise R7Refusal(f"CRSP stocknames absent: {STOCKNAMES}")
    sn = pd.read_parquet(STOCKNAMES, columns=["permno", "ticker", "namedt", "nameenddt"])
    sn["namedt"] = pd.to_datetime(sn["namedt"], errors="coerce")
    sn["nameenddt"] = pd.to_datetime(sn["nameenddt"], errors="coerce")
    sn = sn[sn["ticker"].notna()].copy()
    sn["ticker"] = sn["ticker"].astype(str).str.upper().str.strip()
    return sn


def resolve_permnos(df: pd.DataFrame, sn: pd.DataFrame) -> pd.DataFrame:
    """PIT interval join ticker -> permno on the document's OWN observation date.

    A ticker reused by a different company later must not inherit the earlier
    permno; the interval bound is what stops it.
    """
    d = df.copy()
    d["ticker"] = d["symbols"].str.split("|").str[0]
    d["obs_naive"] = d["observed_at"].dt.tz_localize(None)
    merged = d.merge(sn, on="ticker", how="left")
    ok = (merged["namedt"] <= merged["obs_naive"]) & (
        merged["nameenddt"].isna() | (merged["nameenddt"] >= merged["obs_naive"]))
    merged = merged[ok | merged["permno"].isna()]
    merged = merged.sort_values(["uid", "permno"]).drop_duplicates(subset=["uid"], keep="first")
    return merged


def build_panel() -> dict:
    if not DOCS_PARQUET.is_file():
        raise R7Refusal(f"docs table absent: {DOCS_PARQUET}. Run --build-docs first.")
    if not TRAIN_TABLE.is_file():
        raise R7Refusal(f"label panel absent: {TRAIN_TABLE}")
    tracker = RP.InputTracker()
    tracker.opened(DOCS_PARQUET, note="news documents (built by --build-docs)")
    tracker.opened(STOCKNAMES, note="CRSP ticker->permno PIT intervals")
    tracker.opened(TRAIN_TABLE, note=f"monthly forward excess return target ({TARGET})")

    docs = pd.read_parquet(DOCS_PARQUET, columns=["uid", "observed_at", "symbols", "month",
                                                  "independence_group"])
    sn = _crosswalk()
    linked = resolve_permnos(docs, sn)
    linked["permno"] = pd.to_numeric(linked["permno"], errors="coerce")

    tt = pd.read_parquet(TRAIN_TABLE, columns=["permno", "month", TARGET])
    tt["month"] = pd.to_datetime(tt["month"], errors="coerce")
    tt["month_str"] = tt["month"].dt.strftime("%Y-%m")
    tt["permno"] = pd.to_numeric(tt["permno"], errors="coerce")

    cnt = (linked[linked["permno"].notna()]
           .groupby(["permno", "month"], as_index=False)
           .agg(n_docs=("uid", "size"),
                n_groups=("independence_group", "nunique")))
    cnt["permno"] = cnt["permno"].astype(float)

    panel = cnt.merge(tt[["permno", "month_str", TARGET]],
                      left_on=["permno", "month"], right_on=["permno", "month_str"],
                      how="inner")
    panel = panel.drop(columns=["month_str"])
    panel = panel[panel[TARGET].notna()].reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(PANEL_PARQUET, index=False)

    linkable = linked["permno"].notna().mean()
    receipt = {
        "job": "r7_build_panel",
        "at": _now(),
        "documents": int(len(docs)),
        "documents_permno_linked": int(linked["permno"].notna().sum()),
        "permno_link_share": round(float(linkable), 4),
        "labelled_cells": int(len(panel)),
        "distinct_permnos": int(panel["permno"].nunique()),
        "distinct_months": int(panel["month"].nunique()),
        "month_span": [panel["month"].min(), panel["month"].max()] if len(panel) else None,
        "docs_per_cell_median": float(panel["n_docs"].median()) if len(panel) else None,
        "target": TARGET,
        "label_ceiling": LABEL_LAST_MONTH,
        "out": str(PANEL_PARQUET),
        "note": ("train_table.parquet ends 2024-12, so every 2025/2026 document is "
                 "PRE-TRAINING-ONLY and can never be scored. That is the whole point of "
                 "the design: 524k unlabelled documents, ~10k labelled cells."),
    }
    RP.attach(receipt, sys.argv, {"target": TARGET, "label_ceiling": LABEL_LAST_MONTH}, tracker)
    _write_json(OUT_DIR / "R7_panel_receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-docs", action="store_true")
    ap.add_argument("--build-panel", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--pretrain", default=None,
                    help="pit2018 | pit2021 | pit2023 | full | all")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--steps", type=int, default=None,
                    help="fixed optimisation budget shared by every slice")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--limit-files", type=int, default=None)
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--leak-gate", action="store_true")
    ap.add_argument("--match-battery", action="store_true")
    ap.add_argument("--n-canary", type=int, default=120)
    ap.add_argument("--n-memory", type=int, default=120)
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)
    if args.build_docs:
        r = build_docs(limit_files=args.limit_files)
        print(json.dumps({k: v for k, v in r.items() if k != "_provenance"}, indent=1, default=str))
    if args.build_panel:
        r = build_panel()
        print(json.dumps({k: v for k, v in r.items() if k != "_provenance"}, indent=1, default=str))
    if args.prepare:
        prepare_masked(force=True)
    if args.pretrain:
        names = (["pit2018", "pit2021", "pit2023", "full"]
                 if args.pretrain == "all" else [args.pretrain])
        for nm in names:
            r = run_pretrain(nm, epochs=args.epochs, seed=args.seed, device=args.device,
                             total_steps=args.steps)
            print(json.dumps({k: v for k, v in r.items() if k != "log"}, indent=1, default=str))
    if args.evaluate:
        r = run_evaluate(seed=args.seed)
        print(json.dumps(r["arms"], indent=1, default=str))
    if args.match_battery:
        r = run_match_battery(seed=args.seed)
        print(json.dumps(r["rows"], indent=1, default=str))
    if args.leak_gate:
        r = leak_gate(n_canary=args.n_canary, n_memory=args.n_memory,
                      backend=args.backend, model=args.model, seed=args.seed)
        print(json.dumps({k: v for k, v in r.items() if k != "_provenance"},
                         indent=1, default=str))
    return 0



# ═══════════════════════════════════════════════ COMPANY-IDENTITY MASKING
#
# Every arm sees company-masked text. Two reasons, and both are load-bearing:
#
#   1. It removes the trivial shortcut. A representation that encodes "this is
#      Apple" would let a returns head learn a per-company constant -- a fixed
#      effect dressed as a news signal. Masking makes the model infer identity
#      from BUSINESS CONTENT, which is the thing we claim to be learning.
#   2. It is the canary's condition. If a separate model can still name the
#      company from the masked text, the mask leaks and every downstream number
#      is contaminated.

_GENERIC_NAME_TOKENS = {
    "inc", "corp", "corporation", "co", "company", "ltd", "limited", "plc",
    "group", "holdings", "holding", "the", "and", "of", "international",
    "industries", "systems", "technologies", "technology", "solutions",
    "services", "enterprises", "partners", "trust", "reit", "class", "com",
    "s.a", "n.v", "ag", "sa", "nv", "lp", "llc", "new", "cl",
}
CO_TOKEN = "[co]"


def company_name_map(tracker: RP.InputTracker | None = None) -> dict[str, set[str]]:
    """ticker -> the distinctive tokens of its issuer name(s), from CRSP.

    Union across name intervals rather than PIT: masking MORE is conservative
    for a leak test. Under-masking is the failure that matters.
    """
    if not STOCKNAMES.is_file():
        raise R7Refusal(f"CRSP stocknames absent: {STOCKNAMES}")
    if tracker is not None:
        tracker.opened(STOCKNAMES, note="issuer names, for company-identity masking")
    sn = pd.read_parquet(STOCKNAMES, columns=["ticker", "issuernm"])
    sn = sn[sn["ticker"].notna() & sn["issuernm"].notna()]
    out: dict[str, set[str]] = defaultdict(set)
    for tic, nm in zip(sn["ticker"].astype(str).str.upper(), sn["issuernm"].astype(str)):
        toks = {t for t in tokenise(nm) if len(t) > 2 and t not in _GENERIC_NAME_TOKENS}
        if toks:
            out[tic.strip()] |= toks
    return dict(out)


def mask_company(tokens: list[str], ticker: str, name_tokens: set[str]) -> list[str]:
    tic = ticker.lower()
    bad = {tic} | {t.lower() for t in name_tokens}
    return [CO_TOKEN if t in bad else t for t in tokens]


# ═══════════════════════════════════════════════════════ THE ENCODER
#
# Trained FROM SCRATCH. There is no pretrained-LM download here: the whole
# claim of this lane is that the unlabelled corpus itself pays for the
# representation, and a downloaded encoder would smuggle in a training cutoff
# and an unknown corpus, which is the leak this lane is built to measure.

PAD, UNK, MASK, CLS = 0, 1, 2, 3
SPECIALS = ["[pad]", "[unk]", "[mask]", "[cls]"]
SEQ_LEN = 48
D_MODEL = 192
N_LAYERS = 4
N_HEADS = 4
D_FF = 512


def build_vocab(token_lists, max_vocab: int = 24000, min_count: int = 5) -> dict[str, int]:
    c = Counter()
    for toks in token_lists:
        c.update(toks)
    vocab = {t: i for i, t in enumerate(SPECIALS)}
    for tok, n in c.most_common():
        if n < min_count or len(vocab) >= max_vocab:
            break
        if tok in vocab:
            continue
        vocab[tok] = len(vocab)
    return vocab


def encode_ids(tokens: list[str], vocab: dict[str, int], seq_len: int = SEQ_LEN) -> list[int]:
    ids = [CLS] + [vocab.get(t, UNK) for t in tokens[: seq_len - 1]]
    return ids + [PAD] * (seq_len - len(ids))


def _torch():
    try:
        import torch  # noqa: F401
        return torch
    except Exception as exc:  # pragma: no cover - environment probe
        raise R7Refusal(f"torch is required for --pretrain: {type(exc).__name__}: {exc}")


def make_model(vocab_size: int, seed: int):
    torch = _torch()
    import torch.nn as nn

    class TinyEncoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.emb = nn.Embedding(vocab_size, D_MODEL, padding_idx=PAD)
            self.pos = nn.Embedding(SEQ_LEN, D_MODEL)
            layer = nn.TransformerEncoderLayer(
                d_model=D_MODEL, nhead=N_HEADS, dim_feedforward=D_FF,
                dropout=0.1, batch_first=True, norm_first=True, activation="gelu")
            self.enc = nn.TransformerEncoder(layer, num_layers=N_LAYERS)
            self.ln = nn.LayerNorm(D_MODEL)
            self.mlm = nn.Linear(D_MODEL, vocab_size, bias=True)
            self.mlm.weight = self.emb.weight            # tied: the cheap half of a 24k softmax
            self.proj = nn.Sequential(nn.Linear(D_MODEL, D_MODEL), nn.GELU(),
                                      nn.Linear(D_MODEL, 128))
            # BERT-style init. torch's nn.Embedding default is N(0,1), which with a
            # TIED 192-dim output head produces logits of sd ~14 and an MLM loss of
            # 27 against a chance floor of ln(V)=8.5 -- the model spends its whole
            # budget undoing its own initialisation. Measured, then fixed.
            for mod in self.modules():
                if isinstance(mod, (nn.Linear, nn.Embedding)):
                    nn.init.normal_(mod.weight, mean=0.0, std=0.02)
                if isinstance(mod, nn.Linear) and mod.bias is not None:
                    nn.init.zeros_(mod.bias)
            with torch.no_grad():
                self.emb.weight[PAD].zero_()

        def hidden(self, ids):
            pos = torch.arange(ids.shape[1], device=ids.device).unsqueeze(0)
            h = self.emb(ids) + self.pos(pos)
            return self.ln(self.enc(h, src_key_padding_mask=(ids == PAD)))

        def forward(self, ids):
            h = self.hidden(ids)
            return h, h[:, 0]                            # [CLS] is the sentence vector

    torch.manual_seed(seed)
    return TinyEncoder()


def pretrain(slice_name: str, *, docs: pd.DataFrame, vocab: dict[str, int],
             ids: "np.ndarray", company_id: "np.ndarray", day: "np.ndarray",
             epochs: int = 3, batch: int = 256, seed: int = 0,
             device: str = "cuda", lr: float = 3e-4, total_steps: int | None = None) -> dict:
    """Masked-token reconstruction + same-company contrastive. NO RETURN IS READ.

    The contrastive positive is a second document about the SAME company within
    +/-45 days. Because the text is company-masked, the only way to match them is
    to recognise the business -- which is the representation we want.
    """
    torch = _torch()
    import torch.nn.functional as F

    dev = torch.device(device if (device == "cpu" or torch.cuda.is_available()) else "cpu")
    model = make_model(len(vocab), seed).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    n = ids.shape[0]
    # positive-pair index: for each doc, another doc of the same company within 45 days
    order = np.lexsort((day, company_id))
    partner = np.full(n, -1, dtype=np.int64)
    cid_s, day_s = company_id[order], day[order]
    for a in range(n):
        b = a + 1
        if b < n and cid_s[b] == cid_s[a] and abs(int(day_s[b]) - int(day_s[a])) <= 45:
            partner[order[a]] = order[b]
        elif a > 0 and cid_s[a - 1] == cid_s[a] and abs(int(day_s[a]) - int(day_s[a - 1])) <= 45:
            partner[order[a]] = order[a - 1]
    has_partner = np.flatnonzero(partner >= 0)

    ids_t = torch.from_numpy(ids)
    rng = np.random.default_rng(seed)
    steps_per_epoch = max(1, n // batch)
    if total_steps:
        # EVERY slice gets the SAME optimisation budget, so a difference between
        # encoders is a difference in DATA and never in how long each was trained.
        epochs = max(1, int(math.ceil(total_steps / steps_per_epoch)))
        steps_per_epoch = max(1, total_steps // epochs)
    warmup = max(1, int(0.06 * epochs * steps_per_epoch))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda k: min(1.0, (k + 1) / warmup))
    log: list[dict] = []
    t0 = time.time()
    model.train()
    for ep in range(epochs):
        perm = rng.permutation(n)
        run_mlm = run_con = run_acc = 0.0
        for s in range(steps_per_epoch):
            sel = perm[s * batch:(s + 1) * batch]
            x = ids_t[sel].to(dev, non_blocking=True)

            # ---- masked-token reconstruction (15%, never on PAD or [CLS])
            maskable = (x != PAD) & (x != CLS)
            draw = torch.rand(x.shape, device=dev) < 0.15
            m = maskable & draw
            if m.sum() == 0:
                m = maskable & (torch.rand(x.shape, device=dev) < 0.5)
            xin = x.clone()
            xin[m] = MASK
            h, _ = model(xin)
            logits = model.mlm(h[m])
            loss_mlm = F.cross_entropy(logits, x[m])

            # ---- same-company contrastive (InfoNCE, in-batch negatives)
            psel = rng.choice(has_partner, size=min(batch, len(has_partner)), replace=False)
            xa = ids_t[psel].to(dev)
            xb = ids_t[partner[psel]].to(dev)
            _, ca = model(xa)
            _, cb = model(xb)
            za = F.normalize(model.proj(ca), dim=-1)
            zb = F.normalize(model.proj(cb), dim=-1)
            sim = za @ zb.T / 0.07
            tgt = torch.arange(sim.shape[0], device=dev)
            loss_con = 0.5 * (F.cross_entropy(sim, tgt) + F.cross_entropy(sim.T, tgt))
            acc = (sim.argmax(1) == tgt).float().mean()

            loss = loss_mlm + loss_con
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            run_mlm += float(loss_mlm); run_con += float(loss_con); run_acc += float(acc)
        log.append({"epoch": ep, "mlm_loss": round(run_mlm / steps_per_epoch, 4),
                    "contrastive_loss": round(run_con / steps_per_epoch, 4),
                    "contrastive_acc": round(run_acc / steps_per_epoch, 4),
                    "elapsed_s": round(time.time() - t0, 1)})
        print(f"  [{slice_name}] {log[-1]}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = OUT_DIR / f"encoder_{slice_name}.pt"
    torch.save({"state_dict": model.state_dict(), "vocab_size": len(vocab), "seed": seed}, ckpt)
    return {"slice": slice_name, "documents": int(n), "vocab": len(vocab),
            "epochs": epochs, "steps": epochs * steps_per_epoch,
            "batch": batch, "device": str(dev),
            "params": int(sum(p.numel() for p in model.parameters())),
            "docs_with_a_positive_partner": int(len(has_partner)),
            "log": log, "wall_clock_s": round(time.time() - t0, 1),
            "docs_per_hour": round(n * epochs / max(1e-9, (time.time() - t0)) * 3600, 0),
            "checkpoint": str(ckpt)}


def embed_all(slice_name: str, ids: "np.ndarray", vocab_size: int, *,
              random_init: bool = False, seed: int = 0, batch: int = 512,
              device: str = "cuda") -> "np.ndarray":
    """[CLS] vectors for every document under one encoder. Frozen, no grad."""
    torch = _torch()
    dev = torch.device(device if (device == "cpu" or torch.cuda.is_available()) else "cpu")
    model = make_model(vocab_size, seed).to(dev)
    if not random_init:
        ck = OUT_DIR / f"encoder_{slice_name}.pt"
        if not ck.is_file():
            raise R7Refusal(f"encoder checkpoint absent: {ck}. Run --pretrain {slice_name} first.")
        model.load_state_dict(torch.load(ck, map_location=dev)["state_dict"])
    model.eval()
    out = np.empty((ids.shape[0], D_MODEL), dtype=np.float32)
    ids_t = torch.from_numpy(ids)
    with torch.no_grad():
        for s in range(0, ids.shape[0], batch):
            x = ids_t[s:s + batch].to(dev)
            _, cls = model(x)
            out[s:s + batch] = cls.float().cpu().numpy()
    return out


# ═══════════════════════════════════════════════════ SLICES AND PREPARATION
#
# Three PIT slices and one deliberately-leaky FULL slice. A PIT encoder sees
# ONLY text observed strictly before its era's first test month -- vocabulary
# included, because a vocabulary fitted on future text is itself a leak and a
# quiet one.

ERAS = [
    {"era": "E1", "test_start": "2018-01", "test_end": "2020-12", "pit_slice": "pit2018"},
    {"era": "E2", "test_start": "2021-01", "test_end": "2022-12", "pit_slice": "pit2021"},
    {"era": "E3", "test_start": "2023-01", "test_end": "2024-11", "pit_slice": "pit2023"},
]
PIT_CUTOFF = {"pit2018": "2018-01", "pit2021": "2021-01", "pit2023": "2023-01",
              "full": "2099-01"}
MASKED_PARQUET = OUT_DIR / "docs_masked.parquet"


def prepare_masked(force: bool = False) -> pd.DataFrame:
    """Tokenise once, company-mask once, cache. Returns the doc frame."""
    if MASKED_PARQUET.is_file() and not force:
        return pd.read_parquet(MASKED_PARQUET)
    if not DOCS_PARQUET.is_file():
        raise R7Refusal(f"docs table absent: {DOCS_PARQUET}. Run --build-docs first.")
    tracker = RP.InputTracker()
    tracker.opened(DOCS_PARQUET, note="news documents")
    docs = pd.read_parquet(DOCS_PARQUET,
                           columns=["uid", "observed_at", "symbols", "month", "text",
                                    "independence_group"])
    names = company_name_map(tracker)
    tick = docs["symbols"].str.split("|").str[0].astype(str)
    masked, n_masked_tokens, n_tokens = [], 0, 0
    for text, t in zip(docs["text"].tolist(), tick.tolist()):
        toks = tokenise(text)
        mt = mask_company(toks, t, names.get(t, set()))
        n_tokens += len(toks)
        n_masked_tokens += sum(1 for x in mt if x == CO_TOKEN)
        masked.append(" ".join(mt))
    docs["masked"] = masked
    docs["ticker"] = tick
    docs["company_id"] = pd.factorize(tick)[0].astype(np.int32)
    docs["day"] = (docs["observed_at"].astype("int64") // 86_400_000_000_000).astype(np.int64)
    docs = docs.sort_values("observed_at").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docs.drop(columns=["text"]).to_parquet(MASKED_PARQUET, index=False)
    rec = {"job": "r7_prepare_masked", "at": _now(), "documents": int(len(docs)),
           "tokens": int(n_tokens), "company_tokens_masked": int(n_masked_tokens),
           "mask_rate": round(n_masked_tokens / max(1, n_tokens), 5),
           "docs_with_any_mask": int(sum(1 for m in masked if CO_TOKEN in m)),
           "out": str(MASKED_PARQUET)}
    RP.attach(rec, sys.argv, {"co_token": CO_TOKEN}, tracker)
    _write_json(OUT_DIR / "R7_masking_receipt.json", rec)
    print(json.dumps({k: v for k, v in rec.items() if k != "_provenance"}, indent=1))
    return docs


def slice_docs(docs: pd.DataFrame, slice_name: str) -> pd.DataFrame:
    cutoff = PIT_CUTOFF[slice_name]
    return docs[docs["month"] < cutoff] if slice_name != "full" else docs


def ids_for(docs_slice: pd.DataFrame, vocab: dict[str, int]) -> "np.ndarray":
    arr = np.zeros((len(docs_slice), SEQ_LEN), dtype=np.int64)
    for i, m in enumerate(docs_slice["masked"].tolist()):
        arr[i] = encode_ids(m.split(), vocab)
    return arr


def run_pretrain(slice_name: str, epochs: int, seed: int, device: str,
                 total_steps: int | None = None) -> dict:
    docs = prepare_masked()
    sl = slice_docs(docs, slice_name).reset_index(drop=True)
    if len(sl) < 1000:
        raise R7Refusal(f"slice {slice_name} has only {len(sl)} documents -- refusing to "
                        "pretrain on a sample that cannot support a vocabulary")
    vocab = build_vocab((m.split() for m in sl["masked"]))
    (OUT_DIR / f"vocab_{slice_name}.json").write_text(json.dumps(vocab), encoding="utf-8")
    ids = ids_for(sl, vocab)
    unk = float((ids == UNK).sum() / max(1, (ids != PAD).sum()))
    out = pretrain(slice_name, docs=sl, vocab=vocab, ids=ids,
                   company_id=sl["company_id"].to_numpy(),
                   day=sl["day"].to_numpy(), epochs=epochs, seed=seed, device=device,
                   total_steps=total_steps)
    out.update({"cutoff_month_exclusive": PIT_CUTOFF[slice_name],
                "unk_rate": round(unk, 4),
                "objectives": ["masked_token_reconstruction_15pct",
                               "same_company_contrastive_infonce_45d"],
                "returns_read": False})
    _write_json(OUT_DIR / f"R7_pretrain_{slice_name}.json", out)
    return out


# ═══════════════════════════════════════════════════════════ EVALUATION
#
# Walk-forward, annual refit, ONE embargo month between the last training month
# and the first test month. The target is the forward 1-month excess return, so
# a training cell at month m already carries the return over m+1; dropping
# December of the prior year puts a clear month between the two target windows.
# Never a random k-fold: the panel is a time series and the folds are calendar.

TEST_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
ERA_OF_YEAR = {2018: "E1", 2019: "E1", 2020: "E1",
               2021: "E2", 2022: "E2",
               2023: "E3", 2024: "E3"}
PIT_FOR_ERA = {"E1": "pit2018", "E2": "pit2021", "E3": "pit2023"}
ONE_WAY_BPS_HOUSE = 6.0     # config.py: slippage 5 + commission 1, one-way
ONE_WAY_BPS_STRESS = 25.0   # the construction-tax stress (S38, 2026-09-07)
MIN_NAMES_PER_MONTH = 20


def _labelled_docs() -> pd.DataFrame:
    """Documents that fall inside a labelled (permno, month) cell. Read-only join."""
    docs = prepare_masked()
    sn = _crosswalk()
    docs = docs.rename(columns={"ticker": "tic"})
    docs["ticker"] = docs["tic"]
    linked = resolve_permnos(docs.assign(symbols=docs["ticker"]), sn)
    linked["permno"] = pd.to_numeric(linked["permno"], errors="coerce")
    linked = linked[linked["permno"].notna()]
    panel = pd.read_parquet(PANEL_PARQUET)
    keep = set(zip(panel["permno"].astype(float), panel["month"]))
    m = linked[[tuple(x) in keep for x in
                zip(linked["permno"].astype(float), linked["month"])]].copy()
    return m.reset_index(drop=True)


def _pool(emb: "np.ndarray", keys: "np.ndarray", normalise: bool) -> tuple:
    """Sum or mean of the document vectors in each cell.

    MEAN is the coverage-NORMALISED feature (Murat's standing instruction: a name
    with more news is not a name with more signal). SUM is the same feature left
    UN-normalised and scales with the document count, which is what happens if
    nobody thinks about it. Both are carried so the difference can be printed.
    """
    uk, inv = np.unique(keys, return_inverse=True)
    acc = np.zeros((len(uk), emb.shape[1]), dtype=np.float64)
    cnt = np.zeros(len(uk), dtype=np.float64)
    np.add.at(acc, inv, emb)
    np.add.at(cnt, inv, 1.0)
    if normalise:
        acc = acc / cnt[:, None]
    return uk, acc, cnt


def _ridge_fit_predict(Xtr, ytr, Xte, alphas=(1.0, 10.0, 100.0, 1000.0),
                       inner_frac: float = 0.25, seed: int = 0):
    """Ridge with alpha picked on the LAST slice of the training window.

    The inner validation is the tail of the training period, never a random
    split: a random split lets the model see the future of its own fold.
    """
    from sklearn.linear_model import Ridge
    n = Xtr.shape[0]
    cut = max(1, int(n * (1 - inner_frac)))
    best, best_a = -np.inf, alphas[0]
    for a in alphas:
        r = Ridge(alpha=a).fit(Xtr[:cut], ytr[:cut])
        p = r.predict(Xtr[cut:])
        if len(p) < 5 or np.std(p) == 0:
            score = -np.inf
        else:
            score = float(np.corrcoef(p, ytr[cut:])[0, 1])
            if not np.isfinite(score):
                score = -np.inf
        if score > best:
            best, best_a = score, a
    model = Ridge(alpha=best_a).fit(Xtr, ytr)
    return model.predict(Xte), best_a


def _monthly_metrics(pred: pd.DataFrame) -> pd.DataFrame:
    """One row per test MONTH. n_effective counts these rows, never name-months."""
    from scipy.stats import spearmanr
    rows = []
    for month, g in pred.groupby("month"):
        if len(g) < MIN_NAMES_PER_MONTH:
            continue
        ic = spearmanr(g["pred"], g[TARGET]).statistic
        q = max(1, len(g) // 5)
        s = g.sort_values("pred")
        lo, hi = s.head(q), s.tail(q)
        rows.append({
            "month": month, "n_names": len(g), "ic": float(ic),
            "ls_gross": float(hi[TARGET].mean() - lo[TARGET].mean()),
            "long_excess": float(hi[TARGET].mean()),
            "long_raw": float(hi["ret_1m"].mean()) if "ret_1m" in hi else np.nan,
            "mkt": float(g["mkt_vw_1m"].iloc[0]) if "mkt_vw_1m" in g else np.nan,
            "top_names": "|".join(str(int(p)) for p in hi["permno"].head(8)),
            "bot_names": "|".join(str(int(p)) for p in lo["permno"].head(8)),
        })
    return pd.DataFrame(rows)


def _turnover_cost(pred: pd.DataFrame, bps: float) -> pd.Series:
    """Actual name-level turnover of the quintile book, month over month."""
    prev_hi: set = set()
    prev_lo: set = set()
    out = {}
    for month, g in pred.groupby("month"):
        if len(g) < MIN_NAMES_PER_MONTH:
            continue
        q = max(1, len(g) // 5)
        s = g.sort_values("pred")
        hi = set(s.tail(q)["permno"]); lo = set(s.head(q)["permno"])
        t_hi = len(hi ^ prev_hi) / max(1, len(hi))
        t_lo = len(lo ^ prev_lo) / max(1, len(lo))
        out[month] = (t_hi + t_lo) * bps / 1e4
        prev_hi, prev_lo = hi, lo
    return pd.Series(out)


def _tstat(x: "np.ndarray") -> tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3 or np.std(x, ddof=1) == 0:
        return float("nan"), float("nan"), n
    t = float(np.mean(x) / (np.std(x, ddof=1) / math.sqrt(n)))
    from scipy import stats
    p = float(2 * (1 - stats.t.cdf(abs(t), df=n - 1)))
    return t, p, n


def _beta(book: "np.ndarray", mkt: "np.ndarray") -> tuple[float, float]:
    ok = np.isfinite(book) & np.isfinite(mkt)
    if ok.sum() < 5 or np.std(mkt[ok]) == 0:
        return float("nan"), float("nan")
    b, a = np.polyfit(mkt[ok], book[ok], 1)
    resid = book[ok] - (a + b * mkt[ok])
    return float(b), float(np.mean(resid))


def build_cell_features() -> dict:
    """Every arm's features for every labelled cell, built once.

    ARMS
    ----
      pit_mean     the PIT-pretrained encoder, coverage-NORMALISED (mean pool)
      pit_sum      the same encoder, NOT coverage-normalised (sum pool)
      full_mean    the encoder pretrained on ALL text including the future -- the
                   deliberately LEAKY comparator, so the leak can be priced
      rand_mean    the identical architecture with RANDOM frozen weights: the
                   no-pretraining control (a) the brief demands
      tfidf_svd    TF-IDF -> SVD to the SAME 192 dimensions: baseline (b), matched
      tfidf_raw    TF-IDF, ridge straight onto the sparse matrix
      coverage     the document count alone: baseline (c), Murat's warning
    """
    docs = _labelled_docs()
    panel = pd.read_parquet(PANEL_PARQUET)
    tt = pd.read_parquet(TRAIN_TABLE, columns=["permno", "month", TARGET,
                                               "ret_1m", "mkt_vw_1m"])
    tt["month"] = pd.to_datetime(tt["month"]).dt.strftime("%Y-%m")
    panel = panel.merge(tt.drop(columns=[TARGET]), on=["permno", "month"], how="left")

    docs["cell"] = docs["permno"].astype(np.int64).astype(str) + "_" + docs["month"]
    panel["cell"] = panel["permno"].astype(np.int64).astype(str) + "_" + panel["month"]

    out: dict = {"docs": docs, "panel": panel, "features": {}}
    vocabs = {}
    for slice_name in ["pit2018", "pit2021", "pit2023", "full"]:
        vp = OUT_DIR / f"vocab_{slice_name}.json"
        if not vp.is_file():
            raise R7Refusal(f"vocab absent: {vp}. Run --pretrain {slice_name}.")
        vocabs[slice_name] = json.loads(vp.read_text(encoding="utf-8"))

    for slice_name in ["pit2018", "pit2021", "pit2023", "full"]:
        v = vocabs[slice_name]
        ids = ids_for(docs, v)
        emb = embed_all(slice_name, ids, len(v))
        for norm, tag in ((True, "mean"), (False, "sum")):
            uk, mat, cnt = _pool(emb, docs["cell"].to_numpy(), norm)
            out["features"][slice_name + "_" + tag] = (uk, mat)
        if slice_name == "pit2018":
            # the no-pretraining control shares the architecture, the vocabulary
            # and the tokenisation -- ONLY the pre-training is removed
            embr = embed_all(slice_name, ids, len(v), random_init=True, seed=1234)
            uk, mat, _ = _pool(embr, docs["cell"].to_numpy(), True)
            out["features"]["rand_mean"] = (uk, mat)

    cnt_map = docs.groupby("cell").size()
    grp_map = docs.groupby("cell")["independence_group"].nunique()
    uk = np.array(sorted(cnt_map.index))
    cov = np.column_stack([cnt_map.reindex(uk).to_numpy(float),
                           np.log1p(cnt_map.reindex(uk).to_numpy(float)),
                           grp_map.reindex(uk).to_numpy(float)])
    out["features"]["coverage"] = (uk, cov)
    out["cell_text"] = docs.groupby("cell")["masked"].apply(lambda s: " ".join(s))
    return out


ARMS = ["pit_mean", "pit_sum", "full_mean", "rand_mean",
        "tfidf_svd", "tfidf_raw", "coverage"]

#: DIAGNOSTIC arms. They are NOT hypotheses and are NOT in the multiplicity
#: family; they are the known-answer battery for the harness itself. A null owes
#: two tests: that the effect is absent, and that the machine could have SEEN it.
#: `planted_signal` is a deliberate leak and must score a large positive IC;
#: `pure_noise` must score ~0. If either misbehaves, no other row means anything.
DIAGNOSTIC_ARMS = ["planted_signal", "pure_noise"]


def evaluate(seed: int = 0) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD

    built = build_cell_features()
    panel, feats, cell_text = built["panel"], built["features"], built["cell_text"]
    panel = panel[panel[TARGET].notna()].sort_values(["month", "permno"]).reset_index(drop=True)

    arm_rows: list[dict] = []
    per_month: dict[str, pd.DataFrame] = {}

    def arm_features(arm: str, era: str):
        if arm in ("pit_mean", "pit_sum"):
            sl = PIT_FOR_ERA[era]
            return feats[sl + ("_mean" if arm == "pit_mean" else "_sum")]
        if arm == "full_mean":
            return feats["full_mean"]
        if arm == "rand_mean":
            return feats["rand_mean"]
        if arm == "coverage":
            return feats["coverage"]
        raise R7Refusal("unknown arm " + arm)

    rng_diag = np.random.default_rng(seed)
    for arm in ARMS + DIAGNOSTIC_ARMS:
        preds: list[pd.DataFrame] = []
        alphas_used: list[float] = []
        for Y in TEST_YEARS:
            era = ERA_OF_YEAR[Y]
            train = panel[panel["month"] <= str(Y - 1) + "-11"]
            test = panel[(panel["month"] >= str(Y) + "-01")
                         & (panel["month"] <= str(Y) + "-12")]
            if len(train) < 200 or len(test) < MIN_NAMES_PER_MONTH:
                continue
            if arm in DIAGNOSTIC_ARMS:
                # built from the fold's own frames, so the harness is exercised
                # end to end: same ridge, same standardisation, same metrics
                def _diag(df):
                    z = rng_diag.normal(size=(len(df), 4))
                    if arm == "planted_signal":
                        z[:, 0] = (df.groupby("month")[TARGET].rank(pct=True).to_numpy()
                                   - 0.5 + rng_diag.normal(scale=0.15, size=len(df)))
                    return z
                Xtr, Xte = _diag(train), _diag(test)
            elif arm in ("tfidf_svd", "tfidf_raw"):
                tr_txt = cell_text.reindex(train["cell"]).fillna("")
                te_txt = cell_text.reindex(test["cell"]).fillna("")
                vec = TfidfVectorizer(max_features=20000, min_df=3, sublinear_tf=True)
                Xtr = vec.fit_transform(tr_txt)      # FIT ON TRAINING MONTHS ONLY
                Xte = vec.transform(te_txt)
                if arm == "tfidf_svd":
                    svd = TruncatedSVD(n_components=D_MODEL, random_state=seed)
                    Xtr = svd.fit_transform(Xtr)
                    Xte = svd.transform(Xte)
            else:
                uk, mat = arm_features(arm, era)
                idx = {k: i for i, k in enumerate(uk)}
                tr_i = np.array([idx.get(c, -1) for c in train["cell"]])
                te_i = np.array([idx.get(c, -1) for c in test["cell"]])
                train = train[tr_i >= 0]
                test = test[te_i >= 0]
                Xtr = mat[tr_i[tr_i >= 0]]
                Xte = mat[te_i[te_i >= 0]]
            if not hasattr(Xtr, "toarray"):
                mu = Xtr.mean(0)
                sd = Xtr.std(0)
                sd[sd == 0] = 1.0
                Xtr = (Xtr - mu) / sd
                Xte = (Xte - mu) / sd
            # target: cross-sectional rank within each TRAINING month, so one
            # crash month cannot dominate the fit
            ytr = train.groupby("month")[TARGET].rank(pct=True).to_numpy() - 0.5
            p, a = _ridge_fit_predict(Xtr, ytr, Xte, seed=seed)
            alphas_used.append(a)
            d = test[["permno", "month", TARGET, "ret_1m", "mkt_vw_1m"]].copy()
            d["pred"] = p
            preds.append(d)
        if not preds:
            continue
        pred = pd.concat(preds, ignore_index=True)
        mm = _monthly_metrics(pred)
        if mm.empty:
            continue
        mm["era"] = mm["month"].str[:4].astype(int).map(ERA_OF_YEAR)
        for bps, tag in ((ONE_WAY_BPS_HOUSE, "house"), (ONE_WAY_BPS_STRESS, "stress")):
            c = _turnover_cost(pred, bps)
            mm["cost_" + tag] = mm["month"].map(c).fillna(0.0)
            mm["ls_net_" + tag] = mm["ls_gross"] - mm["cost_" + tag]
        per_month[arm] = mm
        for era in ["E1", "E2", "E3", "ALL"]:
            g = mm if era == "ALL" else mm[mm["era"] == era]
            if len(g) < 3:
                continue
            t_ic, p_ic, n = _tstat(g["ic"].to_numpy())
            t_ls, p_ls, _ = _tstat(g["ls_net_house"].to_numpy())
            b, _a = _beta(g["ls_net_house"].to_numpy(), g["mkt"].to_numpy())
            b_long, _al = _beta(g["long_excess"].to_numpy(), g["mkt"].to_numpy())
            arm_rows.append({
                "arm": arm, "era": era, "n_months": int(n),
                "n_names_median": float(g["n_names"].median()),
                "beta_ls_on_mkt": round(b, 4), "beta_longonly_on_mkt": round(b_long, 4),
                "mean_ic": round(float(g["ic"].mean()), 5),
                "t_ic": round(t_ic, 3), "p_ic": round(p_ic, 5),
                "ls_gross_mean_pct": round(float(g["ls_gross"].mean()) * 100, 4),
                "ls_net_house_pct": round(float(g["ls_net_house"].mean()) * 100, 4),
                "ls_net_stress_pct": round(float(g["ls_net_stress"].mean()) * 100, 4),
                "t_ls_net_house": round(t_ls, 3), "p_ls_net_house": round(p_ls, 5),
                "sharpe_ann_net_house": round(float(
                    g["ls_net_house"].mean() / (g["ls_net_house"].std(ddof=1) + 1e-12)
                    * math.sqrt(12)), 3),
                "mean_cost_house_pct": round(float(g["cost_house"].mean()) * 100, 4),
                "alphas": sorted(set(float(x) for x in alphas_used)),
            })
    return {"rows": arm_rows, "per_month": per_month, "panel_rows": int(len(panel))}


# ═══════════════════════════════════════════════ WHAT THE ENCODER LEARNED
#
# "It learned business structure" is a claim and needs a number that is not a
# return. The number is HELD-OUT same-company retrieval: given a company-masked
# document the encoder never saw, can it pick, out of 256 candidates, the other
# document about the same company? Chance is 1/256 = 0.39%.

def retrieval_probe(slice_name: str, *, n_batches: int = 40, batch: int = 256,
                    seed: int = 0, random_init: bool = False) -> dict:
    docs = prepare_masked()
    cutoff = PIT_CUTOFF[slice_name]
    held = docs[docs["month"] >= cutoff] if slice_name != "full" else docs
    if len(held) < batch * 4:
        return {"slice": slice_name, "status": "CANNOT_DETERMINE",
                "reason": f"only {len(held)} held-out documents"}
    vocab = json.loads((OUT_DIR / f"vocab_{slice_name}.json").read_text(encoding="utf-8"))
    held = held.sort_values(["company_id", "day"]).reset_index(drop=True)
    cid = held["company_id"].to_numpy()
    day = held["day"].to_numpy()
    pair_a, pair_b = [], []
    for i in range(len(held) - 1):
        if cid[i] == cid[i + 1] and abs(int(day[i + 1]) - int(day[i])) <= 45:
            pair_a.append(i)
            pair_b.append(i + 1)
    if len(pair_a) < batch * 2:
        return {"slice": slice_name, "status": "CANNOT_DETERMINE",
                "reason": f"only {len(pair_a)} held-out same-company pairs"}
    rng = np.random.default_rng(seed)
    pair_a = np.array(pair_a)
    pair_b = np.array(pair_b)
    n_pairs_total = len(pair_a)
    # A uniform sample of pairs is an unbiased estimate of the same accuracy and
    # costs one embedding pass over 30k documents instead of half a million.
    if len(pair_a) > 30000:
        keep = rng.choice(len(pair_a), size=30000, replace=False)
        pair_a, pair_b = pair_a[keep], pair_b[keep]
    idx_all = np.unique(np.concatenate([pair_a, pair_b]))
    sub = held.iloc[idx_all]
    ids = ids_for(sub, vocab)
    emb = embed_all(slice_name, ids, len(vocab), random_init=random_init, seed=1234)
    emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
    pos = {v: i for i, v in enumerate(idx_all)}
    hits = 0
    trials = 0
    for _ in range(n_batches):
        sel = rng.choice(len(pair_a), size=batch, replace=False)
        A = emb[[pos[i] for i in pair_a[sel]]]
        B = emb[[pos[i] for i in pair_b[sel]]]
        # a candidate is only a distractor if it is a DIFFERENT company; the same
        # company appearing twice in the batch would be graded as a miss when it
        # is in fact a hit, which understates the probe
        comp = cid[pair_b[sel]]
        sim = A @ B.T
        same = comp[None, :] == comp[:, None]
        np.fill_diagonal(same, False)
        sim[same] = -np.inf
        hits += int((sim.argmax(1) == np.arange(batch)).sum())
        trials += batch
    return {"slice": slice_name, "status": "OK", "random_init": random_init,
            "held_out_documents": int(len(held)),
            "held_out_pairs": int(n_pairs_total),
            "pairs_sampled": int(len(pair_a)),
            "candidates_per_trial": batch, "trials": trials,
            "top1_accuracy": round(hits / trials, 5),
            "chance": round(1.0 / batch, 5),
            "cutoff_month_exclusive": cutoff}


# ═══════════════════════════════════════════════════════════ THE LEAK GATE
#
# Qwen2.5 has a real training cutoff. Two questions, and they are not the same:
#
#   CANARY   -- can a separate call name the company, or the year, from the
#               COMPANY-MASKED text? If yes the mask leaks and every arm above
#               is contaminated.
#   MEMORY   -- Gao-Jiang-Yan: does the model's up/down accuracy DROP after its
#               training cutoff? A drop is memory, not skill, and the feature is
#               refused. AMNESIA-1 already measured that telling a model to
#               forget changes nothing (15.8% vs 15.8%), so nothing here is
#               instructed away; it is measured.

QWEN_CUTOFF_MONTH = "2023-10"   # Qwen2.5's published data cutoff, stated not inferred
CANARY_SYSTEM = ("You are a precise research assistant. Answer with the requested "
                 "token only. Respond in English.")


def _ask(prompt: str, *, backend: str, model: str | None, max_tokens: int) -> tuple[str, dict]:
    from backend.services import free_inference as FI
    try:
        rep = FI.complete(backend, prompt, system=CANARY_SYSTEM, model=model,
                          purpose="r7_leak_gate", max_tokens=max_tokens,
                          temperature=0.0, timeout=120)
        return rep.text.strip(), {"tokens_in": rep.tokens_in, "tokens_out": rep.tokens_out,
                                  "cost_usd": rep.cost_usd, "ok": True}
    except Exception as exc:
        return "", {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def leak_gate(*, n_canary: int = 120, n_memory: int = 120, backend: str = "local_gguf",
              model: str | None = None, seed: int = 0) -> dict:
    docs = prepare_masked()
    lab = _labelled_docs()
    rng = np.random.default_rng(seed)
    t0 = time.time()
    spend = 0.0
    tok_in = tok_out = 0
    failures = 0

    # ---------------------------------------------------------------- canary
    pool = lab[lab["month"] <= "2024-11"]
    sel = pool.iloc[rng.choice(len(pool), size=min(n_canary, len(pool)), replace=False)]
    co_hits = co_asked = yr_hits = yr_asked = 0
    guesses: Counter = Counter()
    for _, r in sel.iterrows():
        q = ("A financial news headline has had the subject company's own name and "
             "ticker replaced by [co]. Name the company's stock ticker. "
             "Reply with the ticker only, or UNKNOWN.\n\nHEADLINE: " + r["masked"][:600])
        txt, meta = _ask(q, backend=backend, model=model, max_tokens=12)
        if not meta.get("ok"):
            failures += 1
            continue
        tok_in += meta.get("tokens_in", 0); tok_out += meta.get("tokens_out", 0)
        spend += float(meta.get("cost_usd") or 0.0)
        cand = _TICKER_RE.findall(txt.upper())
        guess = cand[0] if cand else "UNKNOWN"
        guesses[guess] += 1
        co_asked += 1
        co_hits += int(guess == str(r["ticker"]).upper())

        q2 = ("In which calendar year was this financial news headline published? "
              "Reply with a 4-digit year only.\n\nHEADLINE: " + r["masked"][:600])
        txt2, meta2 = _ask(q2, backend=backend, model=model, max_tokens=8)
        if not meta2.get("ok"):
            failures += 1
            continue
        tok_in += meta2.get("tokens_in", 0); tok_out += meta2.get("tokens_out", 0)
        spend += float(meta2.get("cost_usd") or 0.0)
        m = _YEAR_RE.search(txt2)
        yr_asked += 1
        yr_hits += int(bool(m) and m.group(0) == r["month"][:4])

    from scipy import stats as _st
    p_co = (float(_st.binomtest(co_hits, co_asked, 1 / 135, alternative="greater").pvalue)
            if co_asked else float("nan"))
    p_yr = (float(_st.binomtest(yr_hits, yr_asked, 0.1, alternative="greater").pvalue)
            if yr_asked else float("nan"))
    canary = {
        "n_asked_company": co_asked, "company_hits": co_hits,
        "company_top1": round(co_hits / max(1, co_asked), 4),
        "company_chance_uniform_over_labelled_universe": round(1 / 135, 4),
        "company_exact_binomial_p_greater": round(p_co, 5),
        "company_mde_80pct_above_chance_pp": round(
            100 * mde_for_mean(math.sqrt((1 / 135) * (1 - 1 / 135)), max(1, co_asked)), 3),
        "most_common_guess": guesses.most_common(3),
        "n_asked_year": yr_asked, "year_hits": yr_hits,
        "year_exact": round(yr_hits / max(1, yr_asked), 4),
        "year_chance_uniform_over_10_years": 0.1,
        "year_exact_binomial_p_greater": round(p_yr, 8),
        "provider_failures": failures,
        "reading": ("the COMPANY line is the mask's own audit -- if a separate model "
                    "can name the issuer from masked text, every arm above is "
                    "contaminated. The YEAR line is a different leak and is reported "
                    "beside it because a representation that knows the era knows the "
                    "regime, which is not the same thing as knowing the business."),
    }

    # ------------------------------------------- Gao-Jiang-Yan pre/post cutoff
    # The memory-MAXIMAL condition: the model is handed the ticker AND the date,
    # unmasked, which is exactly what it would need to recall the outcome.
    panel = pd.read_parquet(PANEL_PARQUET)
    tt = pd.read_parquet(TRAIN_TABLE, columns=["permno", "month", TARGET])
    tt["month"] = pd.to_datetime(tt["month"]).dt.strftime("%Y-%m")
    raw = pd.read_parquet(DOCS_PARQUET, columns=["uid", "symbols", "month", "text"])
    raw["ticker"] = raw["symbols"].str.split("|").str[0]
    key = lab[["uid", "permno", "month", "ticker"]].merge(
        tt, on=["permno", "month"], how="inner")
    key = key[key[TARGET].notna()].merge(raw[["uid", "text"]], on="uid", how="inner")

    def _battery(sub: pd.DataFrame, tag: str) -> dict:
        nonlocal spend, tok_in, tok_out, failures
        n_ok = n_up = 0
        correct = 0
        for _, r in sub.iterrows():
            q = (f"HEADLINE ({r['month']}), about {r['ticker']}: {str(r['text'])[:600]}\n\n"
                 "Over the MONTH AFTER this headline, did this stock beat the US "
                 "market or lag it? Answer with exactly one word: BEAT or LAG.")
            txt, meta = _ask(q, backend=backend, model=model, max_tokens=6)
            if not meta.get("ok"):
                failures += 1
                continue
            tok_in += meta.get("tokens_in", 0); tok_out += meta.get("tokens_out", 0)
            spend += float(meta.get("cost_usd") or 0.0)
            u = txt.upper()
            if "BEAT" in u:
                pred = 1
            elif "LAG" in u:
                pred = 0
            else:
                failures += 1
                continue
            n_ok += 1
            n_up += pred
            correct += int(pred == int(r[TARGET] > 0))
        base = float((sub[TARGET] > 0).mean())
        return {"window": tag, "n_graded": n_ok, "accuracy": round(correct / max(1, n_ok), 4),
                "share_answered_BEAT": round(n_up / max(1, n_ok), 4),
                "base_rate_actually_positive": round(base, 4),
                "note": ("a model that always says BEAT scores the base rate; the "
                         "share it answers BEAT is printed so accuracy cannot be "
                         "read without it")}

    pre = key[key["month"] <= QWEN_CUTOFF_MONTH]
    post = key[key["month"] >= "2024-01"]
    half = max(10, n_memory // 2)
    pre_s = pre.iloc[rng.choice(len(pre), size=min(half, len(pre)), replace=False)] \
        if len(pre) else pre
    post_s = post.iloc[rng.choice(len(post), size=min(half, len(post)), replace=False)] \
        if len(post) else post
    mem_pre = _battery(pre_s, f"PRE-cutoff (<= {QWEN_CUTOFF_MONTH})")
    mem_post = _battery(post_s, "POST-cutoff (2024-01 .. 2024-11)")

    drop = (mem_pre["accuracy"] - mem_post["accuracy"]
            if mem_pre["n_graded"] and mem_post["n_graded"] else None)
    n1, n2 = mem_pre["n_graded"], mem_post["n_graded"]
    mde_drop = (Z80_TWO_SIDED * math.sqrt(0.25 / max(1, n1) + 0.25 / max(1, n2))
                if n1 and n2 else float("nan"))
    if drop is None:
        verdict = "CANNOT_DETERMINE -- one of the two windows returned no graded answer"
    elif mem_pre["n_graded"] < 30 or mem_post["n_graded"] < 30:
        verdict = "CANNOT_DETERMINE -- fewer than 30 graded answers in a window"
    elif drop > 0.10:
        verdict = ("MEMORY SUSPECTED -- accuracy falls by more than 10pp at the "
                   "cutoff. Any feature built on this model's direction call is REFUSED.")
    else:
        verdict = ("NO MEMORY DROP DETECTED at this sample size -- which is not the "
                   "same as no memory; see the MDE.")

    rec = {"job": "r7_leak_gate", "at": _now(), "backend": backend,
           "model": model, "qwen_cutoff_month": QWEN_CUTOFF_MONTH,
           "canary": canary, "memory_pre": mem_pre, "memory_post": mem_post,
           "accuracy_drop_at_cutoff": None if drop is None else round(drop, 4),
           "mde_accuracy_drop_80pct_pp": round(100 * mde_drop, 2),
           "mde_reading": ("with this many graded answers only a drop LARGER than "
                           "this could have been detected at 80% power; a smaller "
                           "observed drop is NOT evidence of no memory"),
           "verdict": verdict, "provider_failures": failures,
           "tokens_in": tok_in, "tokens_out": tok_out,
           "spend_usd": round(spend, 6), "wall_clock_s": round(time.time() - t0, 1)}
    _write_json(OUT_DIR / "R7_leak_gate.json", rec)
    return rec


# ═══════════════════════════════════════════════════════════ ADJUDICATION
#
# Family size is DECLARED here and not counted afterwards: seven arms x three
# eras = 21 tests on the primary metric. SCREEN = BH-FDR, EXPORT = Holm
# (CANON section 63). n_effective counts DATE BLOCKS -- test months -- never
# name-months. MDE and the power check come BEFORE the confirmation, so a null
# can be read as "no effect this big" rather than as "no effect".

Z80_TWO_SIDED = 2.802   # z(0.975) + z(0.80): the ncp needed for 80% power


def mde_for_mean(sd: float, n: int, *, ncp: float = Z80_TWO_SIDED) -> float:
    """The smallest mean this many periods could have detected at 80% power."""
    if n < 2 or not np.isfinite(sd) or sd <= 0:
        return float("nan")
    return float(ncp * sd / math.sqrt(n))


def adjudicate(ev: dict) -> dict:
    from backend.strategy import verdict as V
    from learner import inference as INF

    rows = ev["rows"]
    per_month = ev["per_month"]
    by_era = [r for r in rows if r["era"] != "ALL" and r["arm"] not in DIAGNOSTIC_ARMS]
    family = {f"{r['arm']}|{r['era']}": r["p_ic"] for r in by_era
              if np.isfinite(r["p_ic"])}
    ste = V.screen_then_export(family)

    power: list[dict] = []
    for r in by_era:
        mm = per_month[r["arm"]]
        g = mm[mm["era"] == r["era"]]
        ic = g["ic"].to_numpy()
        ls = g["ls_net_house"].to_numpy()
        nb = V.n_effective_date_blocks(g["month"].tolist())
        power.append({
            "arm": r["arm"], "era": r["era"],
            "n_effective_date_blocks": nb.get("n_effective", len(g)),
            "n_name_months_DO_NOT_USE_AS_N": int(g["n_names"].sum()),
            "ic_sd": round(float(np.std(ic, ddof=1)), 4),
            "mde_mean_ic_80pct": round(mde_for_mean(float(np.std(ic, ddof=1)), len(ic)), 4),
            "observed_mean_ic": r["mean_ic"],
            "mde_ls_monthly_pct_80pct": round(
                mde_for_mean(float(np.std(ls, ddof=1)), len(ls)) * 100, 4),
            "observed_ls_net_house_pct": r["ls_net_house_pct"],
            "power_note": INF.power_note(ls.tolist(), periods_per_year=12),
        })

    dsr: list[dict] = []
    for arm, mm in per_month.items():
        if arm in DIAGNOSTIC_ARMS:
            continue
        d = INF.deflated_sharpe(mm["ls_net_house"].tolist(), n_trials=len(family))
        d["arm"] = arm
        d["n_trials_declared"] = len(family)
        dsr.append(d)

    return {"family_size": len(family), "family_max_p": (max(family.values())
                                                         if family else None),
            "family_min_p": (min(family.values()) if family else None),
            "screen_then_export": ste, "power": power, "deflated_sharpe": dsr}


def run_evaluate(seed: int = 0) -> dict:
    tracker = RP.InputTracker()
    for p in (PANEL_PARQUET, MASKED_PARQUET, TRAIN_TABLE, STOCKNAMES):
        tracker.opened(p, note="R7 evaluation input")
    t0 = time.time()
    ev = evaluate(seed=seed)
    adj = adjudicate(ev)
    probes = []
    for sl in ["pit2018", "pit2021", "pit2023"]:
        probes.append(retrieval_probe(sl))
    probes.append(retrieval_probe("pit2018", random_init=True))

    rec = {
        "job": "r7_evaluate", "at": _now(),
        "design": {
            "unit": "(permno, month) cell with at least one news document",
            "target": TARGET,
            "walk_forward": "annual refit; train months <= (Y-1)-11, EMBARGO (Y-1)-12, test year Y",
            "purge_rationale": ("the target at month m is the return over m+1, so one "
                                "embargo month puts a clear month between the last "
                                "training target window and the first test one"),
            "cv": "walk-forward calendar folds only. NEVER random k-fold.",
            "eras": ERAS,
            "test_years": TEST_YEARS,
            "min_names_per_month": MIN_NAMES_PER_MONTH,
            "costs_one_way_bps": {"house": ONE_WAY_BPS_HOUSE, "stress": ONE_WAY_BPS_STRESS},
            "cost_note": ("turnover is measured name by name from the actual quintile "
                          "membership, month over month; costs are never omitted"),
            "n_effective": "TEST MONTHS (date blocks). Name-months are printed and labelled DO NOT USE.",
        },
        "arms": [r for r in ev["rows"] if r["arm"] not in DIAGNOSTIC_ARMS],
        "harness_known_answer_battery": [r for r in ev["rows"]
                                         if r["arm"] in DIAGNOSTIC_ARMS],
        "adjudication": adj,
        "held_out_retrieval_probe": probes,
        "panel_rows": ev["panel_rows"],
        "wall_clock_s": round(time.time() - t0, 1),
    }
    RP.attach(rec, sys.argv, {"seed": seed, "target": TARGET}, tracker)
    _write_json(OUT_DIR / "R7_evaluate.json", rec)
    for arm, mm in ev["per_month"].items():
        mm.to_csv(OUT_DIR / f"per_month_{arm}.csv", index=False)
    return rec


def _heldout_pairs(slice_name: str, seed: int = 0, cap: int = 30000):
    """The pair sample every scorer shares, so the comparison is level."""
    docs = prepare_masked()
    cutoff = PIT_CUTOFF[slice_name]
    held = docs[docs["month"] >= cutoff] if slice_name != "full" else docs
    held = held.sort_values(["company_id", "day"]).reset_index(drop=True)
    cid = held["company_id"].to_numpy()
    day = held["day"].to_numpy()
    a, b = [], []
    for i in range(len(held) - 1):
        if cid[i] == cid[i + 1] and abs(int(day[i + 1]) - int(day[i])) <= 45:
            a.append(i)
            b.append(i + 1)
    if len(a) < 2000:
        return None
    rng = np.random.default_rng(seed)
    a, b = np.array(a), np.array(b)
    total = len(a)
    if total > cap:
        k = rng.choice(total, size=cap, replace=False)
        a, b = a[k], b[k]
    return held, a, b, total, cid


def _score_match(vec, a, b, cid, idx_all, *, n_batches=40, batch=256, seed=0):
    """Top-1 accuracy at picking the same company's other document out of 256."""
    v = vec / (np.linalg.norm(vec, axis=1, keepdims=True) + 1e-9)
    pos = {x: i for i, x in enumerate(idx_all)}
    rng = np.random.default_rng(seed)
    hits = trials = 0
    for _ in range(n_batches):
        sel = rng.choice(len(a), size=batch, replace=False)
        A = v[[pos[i] for i in a[sel]]]
        B = v[[pos[i] for i in b[sel]]]
        comp = cid[b[sel]]
        sim = A @ B.T
        same = comp[None, :] == comp[:, None]
        np.fill_diagonal(same, False)
        sim[same] = -np.inf
        hits += int((sim.argmax(1) == np.arange(batch)).sum())
        trials += batch
    return hits, trials


def match_battery(slice_name: str, seed: int = 0) -> list[dict]:
    """THE COMPARISON THAT DECIDES "did it learn business structure?"

    Three scorers on the IDENTICAL held-out pairs:
      trained      the pre-trained encoder;
      random_init  the same architecture frozen at random init. A random
                   projection of a token bag is already a locality-sensitive
                   hash, so this is NOT a floor of zero and must be measured --
                   "18x chance" means nothing if the control is 15x chance;
      tfidf_svd192 cosine over TF-IDF at the same 192 dimensions.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    got = _heldout_pairs(slice_name, seed=seed)
    if got is None:
        return [{"slice": slice_name, "status": "CANNOT_DETERMINE",
                 "reason": "too few held-out same-company pairs"}]
    held, a, b, total, cid = got
    idx_all = np.unique(np.concatenate([a, b]))
    sub = held.iloc[idx_all]
    vocab = json.loads((OUT_DIR / ("vocab_" + slice_name + ".json")).read_text(encoding="utf-8"))
    ids = ids_for(sub, vocab)

    out = []
    for tag, kw in (("trained", {}), ("random_init", {"random_init": True, "seed": 1234})):
        emb = embed_all(slice_name, ids, len(vocab), **kw)
        h, t = _score_match(emb, a, b, cid, idx_all, seed=seed)
        out.append({"slice": slice_name, "scorer": tag, "status": "OK",
                    "held_out_pairs_total": int(total), "pairs_sampled": int(len(a)),
                    "candidates_per_trial": 256, "trials": t, "hits": h,
                    "top1_accuracy": round(h / t, 5), "chance": round(1 / 256, 5),
                    "cutoff_month_exclusive": PIT_CUTOFF[slice_name]})
    vec = TfidfVectorizer(max_features=20000, min_df=2, sublinear_tf=True)
    X = vec.fit_transform(sub["masked"].tolist())
    Xd = TruncatedSVD(n_components=D_MODEL, random_state=seed).fit_transform(X)
    h, t = _score_match(Xd, a, b, cid, idx_all, seed=seed)
    out.append({"slice": slice_name, "scorer": "tfidf_svd192", "status": "OK",
                "held_out_pairs_total": int(total), "pairs_sampled": int(len(a)),
                "candidates_per_trial": 256, "trials": t, "hits": h,
                "top1_accuracy": round(h / t, 5), "chance": round(1 / 256, 5),
                "cutoff_month_exclusive": PIT_CUTOFF[slice_name]})

    base = out[0]
    for r in out[1:]:
        p1, p2, n = base["top1_accuracy"], r["top1_accuracy"], base["trials"]
        se = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
        r["z_trained_minus_this"] = round((p1 - p2) / se, 3) if se > 0 else None
        r["trained_over_this"] = round(p1 / p2, 3) if p2 > 0 else None
    return out


def run_match_battery(seed: int = 0) -> dict:
    rows = []
    for sl in ["pit2018", "pit2021", "pit2023"]:
        rows.extend(match_battery(sl, seed=seed))
    rec = {"job": "r7_match_battery", "at": _now(), "rows": rows,
           "reading": ("top-1 against 255 distractors from COMPANY-MASKED text the "
                       "encoder never saw. The random-init row is the control that "
                       "matters: a random projection of a token bag already retrieves "
                       "far above chance, so the claim is never 'N times chance', it "
                       "is 'N times the random control'.")}
    _write_json(OUT_DIR / "R7_match_battery.json", rec)
    return rec

if __name__ == "__main__":
    raise SystemExit(main())
