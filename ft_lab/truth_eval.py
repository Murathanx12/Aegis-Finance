"""The typed-event student against TRUTH (a blind adjudicator), not against its teacher.

150 held-out TEST documents (never trained on), drawn from the 400 the student already
labelled, stratified 75 teacher-event / 75 teacher-no_event. For each document:
  * S  the student's label (ft_lab/data/gen_student_events_events_test.jsonl, already on disk)
  * D  a FRESH DeepSeek label with the production L2 prompt (event_extraction, variant A)
  * T  the 2026-09-13 DeepSeek teacher label (for reference)
  * J  a second DeepSeek pass as JUDGE: sees the document, an explicit rubric and the two
       candidate labels S and D in RANDOM order as "A" and "B", never who wrote which; for each
       of event_type / direction / magnitude it says A, B, both or neither (and gives its own).
The judge is DeepSeek, so the adjudication leans toward DeepSeek's way of reading: a student
win over D is the conservative direction. Every call goes through llm_analyzer.call_named
(central telemetry). Own dollar cap on max(ledger, peak list price).

Run with the PROJECT interpreter:  .venv/Scripts/python.exe -m ft_lab.truth_eval --cap 0.60
Writes ft_lab/data/truth_eval.jsonl (resumable) and receipts/truth_eval.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ft_lab import config as C
from ft_lab import prompts as P

OUT = C.WORK / "truth_eval.jsonl"
PURPOSE_LABEL = "ft_lab_truth_label"
PURPOSE_JUDGE = "ft_lab_truth_judge"

JUDGE_SYSTEM = """You are an expert adjudicator of financial-news event labels. You are given one news document about one named entity, and two candidate labels, A and B, produced by two different annotators. Decide, field by field, which label is CORRECT under this rubric:

event_type: the single discrete, dated, decision-relevant event about the NAMED entity that this document reports as NEW information. Use "no_event" for commentary, opinion, market wraps, stock lists, promotional content, price-move recaps without a cause, and for articles that only recap an event reported earlier. The event must be about the named entity (not a peer, not the market). Pick the most specific matching id from the list.
direction: +1 good, -1 bad, 0 neutral/unclear FOR THE NAMED ENTITY'S SHAREHOLDERS, judged from the document's literal facts (a beat and raise = +1; a downgrade = -1; a routine unchanged dividend = 0; no_event = 0).
magnitude: the typical absolute 1-2 session price reaction for an event of this type and this size for this company: NEGLIGIBLE <0.5%, SMALL 0.5-2%, MODERATE 2-5%, LARGE 5-10%, EXTREME >=10%. no_event is NEGLIGIBLE.

For each field answer "A" if only A is correct, "B" if only B is correct, "both" if both are correct (including when they are identical and right, or when the document is genuinely ambiguous between them), "neither" if both are wrong. When you answer "neither", give the correct value.
Also say whether a mistake by either annotator would MATERIALLY mislead an investor (wrong sign on a real event, a real event missed, or an event invented from commentary): "material_error_A" and "material_error_B" true/false.

Allowed event ids: """ + ", ".join(P.EVENT_IDS) + """

Reply with ONLY this JSON object:
{"event_type": "A|B|both|neither", "event_type_correct": "<id>", "direction": "A|B|both|neither", "direction_correct": -1|0|1, "magnitude": "A|B|both|neither", "magnitude_correct": "<bucket>", "material_error_A": true|false, "material_error_B": true|false, "reason": "<one short sentence>"}"""

JUDGE_USER = """Entity: {scope}
Document date: {date}
Title: {title}
Body: {body}

Label A: {a}
Label B: {b}"""


def _lbl(e, d, m) -> str:
    return json.dumps({"event_type": e, "direction": int(d) if d is not None else None, "magnitude": m})


def sample(n: int) -> pd.DataFrame:
    ext = pd.read_parquet(C.WORK / "extract.parquet")
    ext = ext[ext["split"] == "test"].set_index("panel_uid")
    st = pd.read_json(C.WORK / "gen_student_events_events_test.jsonl", lines=True)
    st = st[st["valid"]].set_index("key")
    df = ext.join(st[["event_type", "direction", "magnitude"]].add_prefix("s_"), how="inner")
    df = df.reset_index().rename(columns={"index": "panel_uid"})
    rng = np.random.default_rng(C.SEED + 23)
    ev = df[df["event_type"] != "no_event"]
    ne = df[df["event_type"] == "no_event"]
    half = n // 2
    pick = pd.concat([ev.iloc[rng.permutation(len(ev))[:half]], ne.iloc[rng.permutation(len(ne))[:n - half]]])
    return pick.reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--cap", type=float, default=0.60)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(C.REPO))
    from backend.services import event_extraction as EX  # noqa: PLC0415
    from backend.services import llm_analyzer as LA  # noqa: PLC0415

    docs = sample(a.n)
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["panel_uid"])
    todo = docs[~docs["panel_uid"].isin(done)]
    print(f"sample {len(docs)} (teacher events {int((docs['event_type'] != 'no_event').sum())}), todo {len(todo)}",
          flush=True)
    system = EX.system_with_schema("A")
    lock = threading.Lock()
    spend = {"ledger": 0.0, "own": 0.0, "calls": 0, "served": {}}
    stop = threading.Event()
    rng = np.random.default_rng(C.SEED + 29)
    flips = {u: bool(rng.integers(0, 2)) for u in docs["panel_uid"]}

    def bill(r):
        own = (r.get("tokens_in") or 0) * C.DEEPSEEK_PRICE_IN / 1e6 + (r.get("tokens_out") or 0) * C.DEEPSEEK_PRICE_OUT / 1e6
        with lock:
            spend["calls"] += 1
            spend["ledger"] += float(r.get("cost_usd") or 0)
            spend["own"] += own
            sm = str(r.get("served_model"))
            spend["served"][sm] = spend["served"].get(sm, 0) + 1
            if max(spend["ledger"], spend["own"]) >= a.cap:
                stop.set()

    def one(row):
        if stop.is_set():
            return None
        body = (row.body or "")[:EX.BODY_CHARS]
        user = EX.user_prompt(scope=row.scope, scope_kind=row.scope_kind or "ticker",
                              document_date=str(row.document_date), source_feed=str(row.source or "panel"),
                              title=row.title, body=body)
        r1 = LA.call_named("deepseek", system, user, purpose=PURPOSE_LABEL, max_tokens=400, temperature=0.0,
                           production_budget=False)
        bill(r1)
        parsed = EX.parse_reply(r1.get("text") or "", document=f"{row.title}\n{body}", provider="deepseek")
        d_ok = hasattr(parsed, "event_type")
        d = {"event_type": parsed.event_type, "direction": parsed.direction, "magnitude": parsed.magnitude_bucket} \
            if d_ok else None
        rec = {"panel_uid": row.panel_uid, "scope": row.scope, "document_date": str(row.document_date),
               "teacher": {"event_type": row.event_type, "direction": int(row.direction),
                           "magnitude": row.magnitude_bucket},
               "student": {"event_type": row.s_event_type, "direction": int(row.s_direction),
                           "magnitude": row.s_magnitude},
               "deepseek_fresh": d, "deepseek_refusal": None if d_ok else getattr(parsed, "reason", "?"),
               "served_model_label": r1.get("served_model")}
        if d_ok and not stop.is_set():
            flip = flips[row.panel_uid]
            s_l = _lbl(row.s_event_type, row.s_direction, row.s_magnitude)
            d_l = _lbl(d["event_type"], d["direction"], d["magnitude"])
            A, B = (d_l, s_l) if flip else (s_l, d_l)
            r2 = LA.call_named("deepseek", JUDGE_SYSTEM,
                               JUDGE_USER.format(scope=row.scope, date=row.document_date, title=row.title,
                                                 body=body[:1500], a=A, b=B),
                               purpose=PURPOSE_JUDGE, max_tokens=250, temperature=0.0, production_budget=False)
            bill(r2)
            j = P.parse_json(r2.get("text") or "")
            if j:
                def who(v):
                    v = str(v or "").lower()
                    if v in ("both", "neither"):
                        return v
                    if v not in ("a", "b"):
                        return None
                    return ("deepseek" if v == "a" else "student") if flip else ("student" if v == "a" else "deepseek")
                rec["judge"] = {"event_type": who(j.get("event_type")), "direction": who(j.get("direction")),
                                "magnitude": who(j.get("magnitude")),
                                "event_type_correct": j.get("event_type_correct"),
                                "direction_correct": j.get("direction_correct"),
                                "magnitude_correct": j.get("magnitude_correct"),
                                "material_error_student": bool(j.get("material_error_B" if flip else "material_error_A")),
                                "material_error_deepseek": bool(j.get("material_error_A" if flip else "material_error_B")),
                                "reason": str(j.get("reason") or "")[:300], "student_was": "B" if flip else "A"}
            else:
                rec["judge"] = None
                rec["judge_raw"] = (r2.get("text") or "")[:300]
        rec["called_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with lock:
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        return rec

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, r) for r in todo.itertuples()]
        for i, _ in enumerate(as_completed(futs)):
            if i in (4, 49, 99, 149):
                print(f"{i + 1} docs, calls {spend['calls']} ledger ${spend['ledger']:.4f} own ${spend['own']:.4f} "
                      f"served {spend['served']} {time.time() - t0:.0f}s", flush=True)
    run = {"job": "ft_lab.truth_eval", "calls": spend["calls"], "cost_usd_ledger": round(spend["ledger"], 4),
           "cost_usd_own_peak_estimate": round(spend["own"], 4), "served_models": spend["served"],
           "cap_usd": a.cap, "stopped_by_cap": stop.is_set(), "wall_s": round(time.time() - t0, 1),
           "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(C.RECEIPTS / "deepseek_arm_runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(run) + "\n")
    print(json.dumps(run), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def summarize() -> dict:
    """receipts/truth_eval.json from ft_lab/data/truth_eval.jsonl. An annotator is 'right' on a field
    when the judge names it or says 'both'. When S and D agree the judge almost always says 'both',
    so these are upper bounds for BOTH annotators; the informative rows are the disagreements."""
    R = [json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()]
    J = [r for r in R if r.get("judge")]

    def acc(who, f, rows):
        return round(sum(r["judge"][f] in (who, "both") for r in rows) / max(1, len(rows)), 3)

    def block(rows):
        return {"n": len(rows), **{f"{who}_{f}": acc(who, f, rows) for who in ("student", "deepseek")
                                   for f in ("event_type", "direction", "magnitude")},
                "material_error_student": sum(r["judge"]["material_error_student"] for r in rows),
                "material_error_deepseek": sum(r["judge"]["material_error_deepseek"] for r in rows)}

    dis = [r for r in J if r["student"]["event_type"] != r["deepseek_fresh"]["event_type"]]
    out = {"job": "ft_lab.truth_eval.summarize", "judge": "deepseek (blind A/B order), explicit rubric",
           "n_docs": len(R), "n_judged": len(J),
           "deepseek_fresh_refusals": sum(r["deepseek_fresh"] is None for r in R),
           "all": block(J),
           "teacher_event_docs": block([r for r in J if r["teacher"]["event_type"] != "no_event"]),
           "teacher_no_event_docs": block([r for r in J if r["teacher"]["event_type"] == "no_event"]),
           "event_type_disagreements": {"n": len(dis), "judge_verdicts": dict(
               pd.Series([r["judge"]["event_type"] for r in dis]).value_counts())},
           "fresh_deepseek_vs_0913_teacher_event_agreement": round(
               sum(r["teacher"]["event_type"] == (r["deepseek_fresh"] or {}).get("event_type") for r in R) / len(R), 3),
           "caveat": "the judge is DeepSeek; agreement rows are rarely overruled (0 of the S=D rows were "
                     "'neither'), so accuracy is an upper bound and the judge leans to DeepSeek's reading"}
    (C.RECEIPTS / "truth_eval.json").write_text(json.dumps(out, indent=1, default=int), encoding="utf-8")
    return out
