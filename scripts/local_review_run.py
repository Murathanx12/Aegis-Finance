"""Run the free-backend review pass, either on planted documents or on the store.

    python -m scripts.local_review_run --known-answer --backend local_gguf
    python -m scripts.local_review_run --source gdelt_v2 --limit 20 --backend nvidia_nim

TWO MODES, AND THE FIRST ONE IS NOT OPTIONAL
============================================
`--known-answer` runs the planted battery: documents whose correct extraction is
known in advance, INCLUDING a null document that must come back as a refusal.
A battery with no null in it cannot tell a working extractor from a confident
one -- every model scores well on documents that contain an answer.

`--source` runs the same pass over documents already in the scrape store. It
never fetches: parsing and reviewing are downstream of storage on purpose, so a
prompt change costs compute and not another pull.

The receipt records documents/hour, tokens, $0.00 and what the identical token
counts would have cost on DeepSeek at `config.LLM_PRICE_PER_MTOK`.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.services import local_review as lr
from backend.services.scrape_store import ROOT, ScrapeStore

RECEIPT_DIR = (Path(__file__).resolve().parents[1] / "backend" / "data" /
               "optimus" / "free_inference_2026-09-07")

#: The planted battery. Each row is (doc_id, text, expected_status,
#: expected_event_type). The last two are the NULLS and they are the point.
KNOWN: list[tuple[str, str, str, str | None]] = [
    ("plant_earnings",
     "SHANGHAI, Sept 3 (Reuters) - Zhongtai Semiconductor Ltd said on Tuesday "
     "that third-quarter revenue rose 34% to 2.1 billion yuan, beating the "
     "company's own guidance of 1.8 billion yuan, and that diluted earnings per "
     "share came in at 0.44 yuan against analysts' average estimate of 0.31 yuan. "
     "The chipmaker said demand from domestic data-centre customers drove the beat.",
     "OK", "EARNINGS"),
    ("plant_merger",
     "TOKYO, Sept 4 - Marubishi Heavy Industries agreed to acquire the robotics "
     "division of Sanwa Precision for 480 billion yen in cash, the two companies "
     "said in a joint statement. The boards of both companies have approved the "
     "transaction, which is expected to close in the first quarter of next year "
     "subject to regulatory approval in Japan and the European Union.",
     "OK", "MERGER_ACQUISITION"),
    ("plant_guidance_cut",
     "FRANKFURT, Sept 5 - Nordlicht Automotive AG cut its full-year operating "
     "margin guidance to between 3.5% and 4.0%, from a previous range of 6.0% to "
     "6.5%, blaming a shortfall in orders from two large European customers and "
     "higher warranty provisions. Shares of the supplier fell in early trade.",
     "OK", "GUIDANCE"),
    ("plant_management",
     "SEOUL, Sept 2 - Hanul Chemical said its chief executive, Park Jin-ho, will "
     "step down at the end of the month after eleven years in the role, and that "
     "the board has appointed chief operating officer Lee Seo-yeon as his "
     "successor, effective October 1.",
     "OK", "MANAGEMENT_CHANGE"),
    # ── THE NULLS. An extractor that answers these is inventing. ──────────
    ("plant_null_weather",
     "A band of heavy rain will move across the western coast tonight, with "
     "accumulations of 30 to 50 millimetres expected before dawn. Winds will "
     "gust to 60 kilometres per hour along exposed headlands. The system clears "
     "by mid-morning, leaving a bright and cool afternoon with highs near 17C.",
     "REFUSED_NO_EVENT", "NO_EVENT"),
    ("plant_null_recipe",
     "Warm the olive oil in a wide pan over a medium heat, add the sliced onion "
     "and a good pinch of salt, and cook gently for twelve minutes until soft and "
     "translucent. Stir in the garlic and the chilli flakes, cook for one minute "
     "more, then add the tomatoes and simmer for twenty minutes.",
     "REFUSED_NO_EVENT", "NO_EVENT"),
]


def known_answer(args) -> dict:
    docs = [(d, t) for d, t, _, _ in KNOWN]
    t0 = time.monotonic()
    rows, receipt = lr.review_batch(docs, backend=args.backend,
                                    model=args.model, max_tokens=args.max_tokens,
                                    purpose="local_review_known_answer")
    graded = []
    n_right = 0
    for (doc_id, _, want_status, want_type), row in zip(KNOWN, rows):
        # A null is graded on the REFUSAL, a positive on the event type. Grading
        # both the same way would let a model that refuses everything score 2/6
        # and a model that answers everything score 4/6, and neither number
        # would mean what it looks like.
        ok = (row.status == want_status if want_status != "OK"
              else (row.status == "OK" and row.event_type == want_type))
        n_right += bool(ok)
        graded.append({"doc_id": doc_id, "want_status": want_status,
                       "want_event_type": want_type, "got_status": row.status,
                       "got_event_type": row.event_type,
                       "entity": row.entity, "direction": row.direction,
                       "confidence": row.confidence,
                       "quote": (row.evidence_quote or "")[:90],
                       "correct": bool(ok)})
    n_null = sum(1 for _, _, s, _ in KNOWN if s != "OK")
    null_right = sum(1 for g in graded
                     if g["want_status"] != "OK" and g["correct"])
    # A PROVIDER failure is not a model failure. The first version of this
    # grader called four HTTP 429s "a planted NULL was answered, which is
    # invention" -- an accusation of the model for something the network did.
    # A verdict that cannot tell "it got it wrong" from "it never answered" is
    # the same error as a coverage receipt that keeps only successes.
    n_provider = sum(1 for g in graded if g["got_status"] == "REFUSED_PROVIDER")
    invented = [g for g in graded
                if g["want_status"] == "REFUSED_NO_EVENT"
                and g["got_status"] == "OK"]
    if invented:
        verdict = (f"FAIL -- {len(invented)} planted NULL(s) came back as an "
                   "extraction. That is invention, and it is the one failure "
                   "this battery exists to catch.")
    elif n_provider:
        verdict = (f"CANNOT DETERMINE -- {n_provider}/{len(KNOWN)} documents "
                   "never reached the model (REFUSED_PROVIDER; the NIM free "
                   "tier returns HTTP 429 under load). Not a model result.")
    elif n_right == len(KNOWN):
        verdict = "PASS"
    else:
        verdict = (f"PARTIAL -- {len(KNOWN) - n_right} wrong, but every null "
                   "was correctly refused")
    out = {
        "receipt": "L3_known_answer",
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": args.backend,
        "model": args.model or "(backend default)",
        "n_docs": len(KNOWN),
        "n_correct": n_right,
        "n_nulls": n_null,
        "n_nulls_correctly_refused": null_right,
        "graded": graded,
        "throughput": receipt,
        "n_provider_failures": n_provider,
        "wall_clock_s": round(time.monotonic() - t0, 2),
        "verdict": verdict,
    }
    return out


def from_store(args) -> dict:
    store = ScrapeStore(args.source, root=ROOT)
    docs = []
    for rec in store.records():
        if len(docs) >= args.limit:
            break
        if rec.get("http_status") != 200:
            continue
        try:
            body = store.read_body(rec)
        except Exception as exc:                                # noqa: BLE001
            # A row whose body cannot be read is REPORTED, not skipped: an
            # index that points at nothing is exactly the state a resume must
            # be able to see.
            docs.append((rec["doc_id"], ""))
            print(f"WARN unreadable body {rec['doc_id']}: {exc}")
            continue
        docs.append((rec["doc_id"], body.decode("utf-8", "replace")))
    rows, receipt = lr.review_batch(docs, backend=args.backend,
                                    model=args.model,
                                    max_tokens=args.max_tokens)
    return {"receipt": "L3_store_review", "source": args.source,
            "n_docs": len(docs), "throughput": receipt,
            "rows": [json.loads(x) for x in lr.rows_to_jsonl(rows).splitlines()]}


def main() -> int:
    import backend.config  # noqa: F401  gated dotenv load

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--known-answer", action="store_true")
    p.add_argument("--source", help="a scrape_store source name")
    p.add_argument("--backend", default="local_gguf",
                   choices=["local_gguf", "nvidia_nim", "deepseek"])
    p.add_argument("--model", default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--max-tokens", type=int, default=400)
    p.add_argument("--out", default=None, help="write the receipt here")
    a = p.parse_args()

    if a.backend == "deepseek":
        # A guard, not a comment. The lane exists because the balance is ~$9 and
        # Murat is preserving it; making the paid path require a second, explicit
        # env-gated act is what stops a default from spending it.
        import os
        if os.getenv("AEGIS_ALLOW_PAID_REVIEW") != "1":
            print("REFUSED: --backend deepseek would SPEND. The whole point of "
                  "this lane is that it does not. Set AEGIS_ALLOW_PAID_REVIEW=1 "
                  "if that is genuinely what you want.")
            return 2

    out = known_answer(a) if a.known_answer else from_store(a)
    print(json.dumps(out, indent=1)[:6000])
    dest = Path(a.out) if a.out else (
        RECEIPT_DIR / f"{out['receipt']}_{a.backend}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
