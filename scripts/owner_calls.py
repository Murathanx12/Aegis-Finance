"""Owner calls (ROADMAP CH-01). See `backend/services/owner_calls.py`.

    python -m scripts.owner_calls status   [--data-root D] [--days 14]
    python -m scripts.owner_calls contract [--data-root D] [--out FILE]
    python -m scripts.owner_calls log      --who owner --question A-NVDA-CLUSTER --p 0.6
    python -m scripts.owner_calls log      --who owner --long NVDA --short SPY --horizon 5
                                           --claim below --p 0.55 --text "..."
    python -m scripts.owner_calls rule     --question A-NVDA-CLUSTER [--log]
    python -m scripts.owner_calls record   [--data-root D] [--out DIR]
    python -m scripts.owner_calls grade    [--data-root D] [--out DIR]
    python -m scripts.owner_calls list     [--out DIR]
    python -m scripts.owner_calls register

`status` and `contract` print and write nothing (`contract --out FILE` writes
that one file). `log` and `grade` append under `--out`, default
`<data-root>/owner_calls`: with the default data root that is the live data
folder, which is where the owner's ledger belongs. `--p` is the probability
that the question's claim, as worded, is TRUE; an owner who expects the
opposite gives a number below 0.5. A call is refused once its window has
started and is never revised. `rule --log` appends the frozen rule's answer as
a direction-only call (no probability), and only when the rule says YES.
`record` pins every ended forward day once in `states.jsonl` (state plus the
SHA-256 of each source file); run it daily, because a forward event counts at
a formal read only when its trigger day was pinned on or before its entry
date. `register` writes three rows to the trial registry and is attended: run
it after the owner signs the trial documents.

Nothing here sends an order, calls an LLM or touches the network. Exit 2 on a
refusal, a broken chain, or a call that cannot be graded.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from backend.services import owner_calls as OC                       # noqa: E402


def _out(a: argparse.Namespace) -> Path:
    return Path(a.out) if a.out else Path(a.data_root) / "owner_calls"


def _status(a: argparse.Namespace, now: datetime) -> int:
    root = Path(a.data_root)
    if not (root / "news_corpus").is_dir():
        print(f"REFUSED: no news_corpus under {root}")
        return 2
    last = (now.date() - timedelta(days=1)).isoformat()
    first = (now.date() - timedelta(days=a.days)).isoformat()
    print(f"inception {OC.INCEPTION}  min titles {OC.MIN_TITLES}  sources {len(OC.SOURCES)}")
    print("day         titles  " + "  ".join(f"{t:>22}" for t in OC.THEMES))
    for d in OC._days(first, last):
        c = OC.daily_counts(root, d)
        cells = []
        for t in OC.THEMES:
            s = OC.theme_state(c, t)
            cells.append(f"{s['hits']:3} {100 * s['share']:5.2f}% {s['state']:<8}")
        mark = "" if d >= OC.INCEPTION else "  (seen before freeze)"
        print(f"{d}  {c['n_titles']:6}  " + "  ".join(f"{x:>22}" for x in cells) + mark)
    for t in OC.THEMES:
        res = OC.theme_events(root, t, now=now)
        print(f"\n{t}  contract {res['contract_sha256'][:16]}  bars through {res['bars_last']}  "
              f"{json.dumps(res['counts'], sort_keys=True)}")
        for e in res["events"]:
            tail = (f"outcome {100 * e['outcome']:+.2f}% claim_true {e['claim_true']}"
                    if e["status"] == "GRADED" else e["status"])
            if e["evidence"] == "FORWARD":
                tail += ("  pinned " + e["pinned_utc"][:16] if e["counts_at_read"] else
                         "  NOT COUNTED (" + ("pinned late" if e["pinned_utc"] else "unpinned") + ")")
            print(f"  {e['evidence']:<19} trigger {e['trigger_day']} ({e['hits']}/{e['n_titles']}) "
                  f"{e['entry_date']} -> {e['exit_date']}  {tail}")
    for q in OC.QUESTIONS:
        r = OC.rule_answer(root, q, now=now)
        print(f"question {q}: rule answer {r['answer']}")
    return 0


def _contract(a: argparse.Namespace, now: datetime) -> int:
    root = Path(a.data_root)
    before = date.fromisoformat(OC.INCEPTION)
    doc: dict = {"schema": "owner-calls-contract/1", "version": OC.VERSION,
                 "computed_utc": now.isoformat(timespec="seconds"), "themes": {}, "questions": {}}
    red = False
    for t, spec in OC.THEMES.items():
        px = OC.load_px(root, OC.symbols_of(spec["long"], spec["short"]), deep=True)
        br = OC.base_rate(px, spec["long"], spec["short"], spec["horizon"], spec["claim"],
                          spec["threshold"], before=before)
        red |= br is None
        doc["themes"][t] = {"contract_sha256": OC.contract_sha256(t), "contract": OC.contract(t),
                            "twin_base_rate": br}
    for q, spec in OC.QUESTIONS.items():
        px = OC.load_px(root, OC.symbols_of(spec["long"], spec["short"]), deep=True)
        br = OC.base_rate(px, spec["long"], spec["short"], spec["horizon"], spec["claim"],
                          spec["threshold"], before=before)
        red |= br is None
        doc["questions"][q] = {"text": spec["text"], "twin_base_rate": br}
    text = json.dumps(doc, indent=1, sort_keys=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"-> {a.out}")
    else:
        print(text)
    if red:
        print("RED: a base rate could not be computed (bars missing)", file=sys.stderr)
    return 2 if red else 0


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")          # type: ignore[union-attr]
        except Exception:                                            # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="owner_calls")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "contract", "log", "rule", "record", "grade", "list", "register"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=str(_cfg.OPTIMUS_LEDGER_DIR))
        p.add_argument("--out", default=None)
        if name == "status":
            p.add_argument("--days", type=int, default=14)
        if name in ("log", "rule"):
            p.add_argument("--question", choices=sorted(OC.QUESTIONS), default=None)
        if name == "rule":
            p.add_argument("--log", action="store_true")
        if name == "log":
            p.add_argument("--who", required=True)
            p.add_argument("--p", type=float, default=None)
            p.add_argument("--text", default="")
            p.add_argument("--long", nargs="+", default=None)
            p.add_argument("--short", default=None)
            p.add_argument("--horizon", type=int, default=None)
            p.add_argument("--claim", choices=OC.CLAIMS, default=None)
            p.add_argument("--threshold", type=float, default=0.0)
            p.add_argument("--entry-date", default=None)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if a.cmd == "status":
        return _status(a, now)
    if a.cmd == "contract":
        return _contract(a, now)
    if a.cmd == "register":
        print(json.dumps(OC.ensure_owner_call_trials(), indent=1))
        return 0
    if a.cmd == "record":
        res = OC.record_states(_out(a), data_root=Path(a.data_root), now=now)
        print(json.dumps(res, indent=1))
        return 0 if res["chain"]["ok"] else 2
    if a.cmd == "list":
        path = _out(a) / "calls.jsonl"
        for r in OC._jsonl(path):
            p = "direction only" if r["probability"] is None else f"p {r['probability']:.2f}"
            print(f"{r['written_utc'][:16]}  {r['who']:<8} {r.get('question') or '-':<16} {p:<14} "
                  f"twin {r['twin']['p']:.3f} (n {r['twin']['n_blocks']})  {r['text'][:70]}")
        chain = OC.verify_chain(path)
        print(f"chain: {json.dumps(chain)}")
        return 0 if chain["ok"] else 2
    if a.cmd == "grade":
        res = OC.grade_calls(_out(a), data_root=Path(a.data_root), now=now)
        print(json.dumps({k: v for k, v in res.items() if k != "new_grades"}, indent=1))
        for g in res["new_grades"]:
            print(f"{g['who']:<8} {g.get('question') or '-':<16} {g['entry_date']}->{g['exit_date']} "
                  f"outcome {100 * g['outcome']:+.2f}% true {g['claim_true']} "
                  f"brier {g['brier']} twin {g['twin_brier']}")
        c = res["counts"]
        bad = c["cannot_grade"] + c["frozen_late"] + c["seal_mismatch"]
        return 2 if bad or not res["chain"]["ok"] else 0
    if a.cmd == "rule":
        if not a.question:
            print("REFUSED: --question is required")
            return 2
        r = OC.rule_answer(Path(a.data_root), a.question, now=now)
        print(json.dumps(r, indent=1))
        if not (a.log and r["answer"] == "YES"):
            return 0
        a.who, a.p, a.text = "rule", None, ""
        a.long = a.short = a.horizon = a.claim = a.entry_date = None
        a.threshold = 0.0
    try:
        row = OC.log_call(_out(a), data_root=Path(a.data_root), who=a.who, probability=a.p,
                          question=a.question, text=a.text, long=a.long, short=a.short,
                          horizon=a.horizon, claim=a.claim, threshold=a.threshold,
                          entry_date=a.entry_date)
    except OC.CallRefused as e:
        print(f"REFUSED: {e}")
        return 2
    print(f"logged {row['call_id']}  twin p {row['twin']['p']} over {row['twin']['n_blocks']} blocks"
          f"  -> {_out(a) / 'calls.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
