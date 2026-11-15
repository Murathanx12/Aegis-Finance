"""CH-46 -- news entity and theme tagging by embeddings (`backend/services/news_entity_embed.py`).

    python -m scripts.news_entity_embed build-index --out DIR [--data-root <optimus dir>] [--now ISO]
                                                    [--index-days N] [--device auto|cpu|cuda]
                                                    [--threads 4] [--batch 64] [--allow-download]
                                                    [--skip-extract]
    python -m scripts.news_entity_embed tag  --out DIR
    python -m scripts.news_entity_embed eval --out DIR [--resample-audit]

`build-index` reads the data root (the hub's corpus, reader page store, world digest, CIK map,
issuer table, potential universe) and writes ONLY under `--out`, which must be a local folder
outside any git checkout (the rows file holds licensed text). It counts the files of the live
folders it reads before and after and prints both. `tag` trains on the precise labels with a
time-ordered split and writes the sidecars; `eval` writes the 300-row labelling sheet, the
60-row self-audit sheet and `eval_receipt.json` (it merges `self_audit_labels.csv` when present).

Exit codes: 0 ok; 2 a refusal (missing input or model, too few labels, `--out` inside a repo,
no threshold reaches the target precision, a live folder that LOST files during the run).
No LLM call, no scheduled caller.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from backend import config as C  # noqa: E402
from backend.services import news_entity_embed as NEE  # noqa: E402
from backend.services import news_entities as NE  # noqa: E402
from backend.services import ticker_hub as TH  # noqa: E402

BUILD_RECEIPT = "build_receipt.json"
TAG_RECEIPT = "tag_receipt.json"
EVAL_RECEIPT = "eval_receipt.json"


def _parse(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise SystemExit(f"--now must carry a zone: {s}")
    return d.astimezone(timezone.utc)


def _count_files(root: Path) -> int:
    n = 0
    for _dp, _dn, fn in os.walk(root):
        n += len(fn)
    return n


def _write(p: Path, obj: dict) -> None:
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)


def _embedder(a: argparse.Namespace):
    if getattr(a, "fake_embedder", False):
        return NEE.HashEmbedder()
    return NEE.HFEmbedder(device=a.device, threads=a.threads, batch=a.batch,
                          allow_download=a.allow_download)


def cmd_build_index(a: argparse.Namespace) -> int:
    t0 = time.time()
    out = NEE.check_out_dir(Path(a.out))
    root = Path(a.data_root) if a.data_root else TH.default_data_root()
    P = NEE.default_paths(root)
    NEE.check_inputs(P)
    now = _parse(a.now) if a.now else datetime.now(timezone.utc).replace(microsecond=0)
    watched = {"corpus": Path(P["corpus"])}
    hub = TH.hub_dir(root)
    if hub.is_dir():
        watched["ticker_hub"] = hub
    before = {k: _count_files(v) for k, v in watched.items()}
    print(f"live folders, files before: {before}")
    emb = _embedder(a)
    print(f"model: {emb.info}")
    tbl = NE.tables(issuers=Path(P["issuers"]))
    uni = TH.load_universe(P, tbl)
    comp = NEE.build_company_index(out, emb, Path(P["issuers"]), uni)
    print(f"company index: {comp}")
    ext = None
    if not a.skip_extract:
        ext = NEE.extract_rows(P, out, now, int(a.index_days or C.TICKER_HUB_INDEX_DAYS))
        print(f"rows: read {ext['rows_read']}, hub-tagged {ext['rows_hub_tagged']}, too short "
              f"{ext['rows_too_short']}, written {ext['rows_written']}, labelled {ext['rows_labelled_written']}")
    t1 = time.time()
    er = NEE.embed_rows(out, emb)
    t_emb = time.time() - t1
    print(f"embedded {er['rows_embedded']} rows in {t_emb:.1f}s")
    after = {k: _count_files(v) for k, v in watched.items()}
    print(f"live folders, files after:  {after}")
    rec = {"schema": NEE.SCHEMA, "stage": "build-index", "built_utc": NEE._iso(now), "data_root": str(root),
           "model": emb.info, "company_index": comp, "extract": ext, "embed": er,
           "embed_seconds": round(t_emb, 1), "elapsed_s": round(time.time() - t0, 1),
           "peak_rss_mb": NEE.peak_rss_mb(), "live_files_before": before, "live_files_after": after,
           "threads": a.threads}
    _write(out / BUILD_RECEIPT, rec)
    moved = {k: after[k] - before[k] for k in before if after[k] != before[k]}
    if moved:
        # the collectors keep writing into the corpus; growth is printed, a SHRINK refuses
        print(f"note: live file counts moved during the run (collectors are writing): {moved}")
        if any(v < 0 for v in moved.values()):
            print("REFUSED: a live folder LOST files during the run", file=sys.stderr)
            return 2
    return 0


def cmd_tag(a: argparse.Namespace) -> int:
    out = NEE.check_out_dir(Path(a.out))
    t0 = time.time()
    rec = NEE.tag(out)
    rec.update({"schema": NEE.SCHEMA, "stage": "tag", "elapsed_s": round(time.time() - t0, 1),
                "peak_rss_mb": NEE.peak_rss_mb()})
    _write(out / TAG_RECEIPT, rec)
    h = rec["held_out_test"]
    print(f"thresholds: {rec['thresholds']}")
    print(f"held-out test: about n={h['about_n']} precision={h['precision']} ci95={h['precision_ci95']} "
          f"recall={h['recall']} (of {h['positives']} precise positives)")
    print(f"uncertain middle: {rec['uncertain_middle']}")
    if rec["thresholds"].get("status") != "OK":
        print("REFUSED: no validation threshold reaches the target precision", file=sys.stderr)
        return 2
    return 0


def cmd_evaluate(a: argparse.Namespace) -> int:
    out = NEE.check_out_dir(Path(a.out))
    for name in (BUILD_RECEIPT, TAG_RECEIPT):
        if not (out / name).is_file():
            raise NEE.EmbedTagRefused(NEE.INDEX_MISSING, f"no {name} in {out}: run build-index and tag first")
    b = json.loads((out / BUILD_RECEIPT).read_text(encoding="utf-8"))
    t = json.loads((out / TAG_RECEIPT).read_text(encoding="utf-8"))
    sheet = NEE.labelling_sheet(out)
    audit_path = out / "self_audit_sheet.csv"
    audit = (NEE.audit_sheet(out) if a.resample_audit or not audit_path.is_file()
             else {"path": str(audit_path), "kept": "existing sheet (pass --resample-audit to redraw)"})
    labels = NEE.read_self_audit(out)
    h = t["held_out_test"]
    um = t["uncertain_middle"]
    target = t["thresholds"]["target_precision"]
    rec = {
        "schema": NEE.SCHEMA, "stage": "eval", "written_utc": NEE._iso(datetime.now(timezone.utc)),
        "model": {k: b["model"].get(k) for k in ("model_id", "revision", "licence", "device", "pooling",
                                                 "max_length", "torch")},
        "rows_embedded": b["embed"]["rows_embedded"], "companies_embedded": b["company_index"]["companies"],
        "runtime": {"build_index_s": b["elapsed_s"], "embed_s": b["embed_seconds"], "tag_s": t["elapsed_s"],
                    "peak_rss_mb_build": b["peak_rss_mb"], "peak_rss_mb_tag": t["peak_rss_mb"]},
        "extract": {k: v for k, v in (b.get("extract") or {}).items() if k != "counts"},
        "split": t["split"],
        "headline": {
            "about_precision_held_out": h["precision"], "about_precision_ci95": h["precision_ci95"],
            "about_n_held_out": h["about_n"], "target": target,
            "meets_target_point": h["precision"] is not None and h["precision"] >= target,
            "meets_target_lower_ci": h["precision_ci95"][0] is not None and h["precision_ci95"][0] >= target,
            "recall_vs_rule_about_tier": h["recall"],
            "uncertain_rows": um["rows"], "uncertain_rows_unlabelled": um["rows_unlabelled_only"],
            "uncertain_est_usd_whole_window": um["est_usd_whole_window"],
            "uncertain_est_usd_per_day": um["est_usd_per_day"]},
        "what_the_precision_is_measured_on": (
            "held-out TEST pairs (the latest labelled rows by time, after an embargo), labels = the hub's "
            "precise about tier (the title names the company, or an SEC filing by CIK). Features never see "
            "the title. These are rows whose title names a company, an easier population than the "
            "mentions-only rows a promotion would act on; the self-audit samples that population."),
        "tag": t, "labelling_sheet": sheet, "self_audit_sheet": audit,
        "self_audit_result": labels or "NOT YET LABELLED",
    }
    _write(out / EVAL_RECEIPT, rec)
    print(json.dumps(rec["headline"], indent=1))
    print(f"labelling sheet: {sheet['pairs']} pairs {sheet['by_decision']}")
    print(f"self-audit: {labels or 'not labelled yet'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="news_entity_embed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-index")
    b.add_argument("--out", required=True)
    b.add_argument("--data-root")
    b.add_argument("--now")
    b.add_argument("--index-days", type=int)
    b.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    b.add_argument("--threads", type=int, default=int(C.NEWS_EMBED_THREADS))
    b.add_argument("--batch", type=int, default=int(C.NEWS_EMBED_BATCH))
    b.add_argument("--allow-download", action="store_true")
    b.add_argument("--skip-extract", action="store_true")
    b.add_argument("--fake-embedder", action="store_true", help=argparse.SUPPRESS)
    t = sub.add_parser("tag")
    t.add_argument("--out", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--out", required=True)
    e.add_argument("--resample-audit", action="store_true")
    a = ap.parse_args(argv)
    handlers = {"build-index": cmd_build_index, "tag": cmd_tag, "eval": cmd_evaluate}
    try:
        return handlers[a.cmd](a)
    except NEE.EmbedTagRefused as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
