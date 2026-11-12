"""Event nodes from the corpus (ROADMAP CH-35, slice 1). See `backend/services/event_nodes.py`.

    python -m scripts.event_nodes build --data-root <optimus dir> [--out DIR]
                                        [--since ISO] [--now ISO] [--top 10]
    python -m scripts.event_nodes fill  --data-root <optimus dir> --dry-run [--top N]
                                        [--since ISO] [--now ISO] [--show-prompt]
    python -m scripts.event_nodes verify --out DIR
    python -m scripts.event_nodes daily --data-root <optimus dir> [--out DIR] [--now ISO]
                                        [--window-hours 36] [--full-receipt]
    python -m scripts.event_nodes repair-tail --out DIR [--dry-run]

`build` reads the corpus READ-ONLY, appends new node versions to
`<out>/event_nodes.jsonl` (hash-chained) and writes one receipt
`<out>/receipts/<build_id>.json` + `.md` (titles, publishers, stamps and URLs;
never article bodies). `--out` defaults to `<data-root>/<EVENT_NODES_DIRNAME>`,
which WRITES INTO the data root: pass `--out` to keep it elsewhere.

`daily` (CH-35 slice 2) builds the trailing EVENT_NODES_DAILY_WINDOW_HOURS into the
default store (`<data-root>/<EVENT_NODES_DIRNAME>/`, or --out) and appends only what
changed; safe every 30-60 minutes, under the store's OS lock (a second instance prints
`EVENT_NODES_DAILY SKIP STORE_LOCKED` and exits 0). It prints ONE summary line, rewrites
`daily_latest.json` (counts, changed ids, top-N; a few KB) and appends one line to
`daily_runs.jsonl`; `--full-receipt` also writes the full dump. rc 2 when every source is
empty, when --now is in the future, or when the store has a torn tail (STORE_TORN_TAIL:
`repair-tail --dry-run` shows the incomplete last line; `repair-tail` backs the store up
beside itself, truncates only that line and re-verifies the chain).

Exit codes: 0 ok (or a window with no corpus rows, which is printed as such);
2 a refused input / window / chain, or rows read and no event built; 3 a fill
refusal (budget, provider, non-JSON). `fill` without `--dry-run` makes ONE capped
DeepSeek call per event (provider_budget) and appends a `fill` row; the brain
session runs the first real one.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import config as C
from backend.services import event_nodes as EN


def _parse(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise SystemExit(f"--now/--since must carry a zone: {s}")
    return d.astimezone(timezone.utc)


def _window(a: argparse.Namespace) -> tuple[datetime, datetime]:
    now = _parse(a.now) if a.now else datetime.now(timezone.utc).replace(microsecond=0)
    since = _parse(a.since) if a.since else now - timedelta(hours=float(C.EVENT_NODES_DEFAULT_LOOKBACK_HOURS))
    return since, now


def _components(n: dict) -> str:
    c = n["importance"]["contributions"]
    return " ".join(f"{k}={v:g}" for k, v in c.items())


def table(res: dict, top: int, now: datetime) -> list[str]:
    r = res["read"]
    lines = [f"BUILD {res['build_id']}  window {res['since']} .. {res['now']}",
             f"rows read {r['rows_read']} in {r['files']} files -> {r['items']} evidence items; "
             f"dropped: after-now {r['dropped_after_now']}, published-after-now "
             f"{r['dropped_published_after_now']}, undated {r['dropped_undated']}, not-news "
             f"{r['dropped_not_news']}; rows naming no issuer {r['rows_unresolved']}; bad JSON lines "
             f"{r['bad_json_lines']}; filing rows without first_seen {r['filing_rows_without_first_seen']}; "
             f"date-only publications {r['rows_date_only_publication']}; alias map import failed: "
             f"{r.get('alias_map_import_failed')}",
             f"OLD_CONTEXT items (published before since - gap; listed, never joined): "
             f"{r.get('items_old_context')}; refused name matches {r.get('n_refused_name_matches')}: "
             f"{dict(list((r.get('refused_name_matches') or {}).items())[:15])}",
             "rows per source (newest known-at stamp):"]
    for s in sorted(r["per_source"]):
        lines.append(f"  {s:32s} {r['per_source'][s]:5d}  {r['newest_per_source'].get(s)}")
    cl = res["clustering"]
    lines.append(f"events {len(res['nodes'])} (items without a title issuer, not clustered: "
                 f"{cl['n_unclustered_no_title_issuer']}); join gap {cl['join_gap_hours']}h, "
                 f"min similarity {cl['join_threshold']}")
    lines.append(f"graph {res['graph']}; bars last session {res['bars_last_session']}; "
                 f"calendar {res['calendar']}; positions {res['positions']}")
    idn = res["identity"]
    lines.append(f"identity: {idn['n_stored_latest']} stored latest nodes, {idn['n_versions']} new versions, "
                 f"{len(idn['retire'])} retirements; parents {len(res['parents'])}; "
                 f"person-bigram joins {cl.get('bigram_joins')}")
    lines.append(f"TOP {top} by importance_0 (importance_now decays, half-life "
                 f"{C.EVENT_NODES_HALF_LIFE_HOURS}h):")
    for n in res["nodes"][:top]:
        lines.append(f"  #{n['rank_at_build']:<3d} {n['primary_ticker']:6s} imp0 "
                     f"{n['importance']['importance_0']:.3f} now {EN.importance_now(n, now):.3f} "
                     f"n_ev {n['n_evidence']:3d} old {n['n_old_context']:2d} pubs "
                     f"{n['importance']['facts']['n_publishers']} | {_components(n)} | observed_after z "
                     f"{n['observed_after']['price_reaction'].get('z')} | {n['timeline'][0]['title'][:70]}")
    return lines


def _md(res: dict, top: int, now: datetime, store: dict) -> str:
    out = ["# Event nodes build " + res["build_id"], "", "```"] + table(res, top, now) + ["```", "",
                                                                                         f"store: {store}", ""]
    for n in res["nodes"][:top]:
        out.append(f"## #{n['rank_at_build']} {n['primary_ticker']} -- {n['event_id']}")
        out.append(f"first seen {n['first_seen_utc']}; importance_0 {n['importance']['importance_0']}; "
                   f"components {json.dumps(n['importance']['components'])}")
        out.append("")
        for t in n["timeline"]:
            e = n["evidence"][t["i"]]
            out.append(f"- [{t['i']}] {t['t']} ({t['clock']}) {e['publisher']} "
                       f"{'/'.join(e['regions'])} {e['kind']}: {e['title'][:140]}  <{e['url']}>")
        cm = ", ".join(f"{r['ticker']}({r['n_items']};{'/'.join(r['rules'])})"
                       for r in n["connected_names"]["co_mention"][:15])
        gr = ", ".join(f"{g['ticker']}({g['link']}:{g['weight']})" for g in n["connected_names"]["graph"][:20])
        out += ["", f"co-mention: {cm or '-'}", f"graph: {gr or '-'}",
                f"next dates: {json.dumps(n['next_dates'][:8])}", ""]
    return "\n".join(out) + "\n"


def _strip(res: dict) -> dict:
    return {k: v for k, v in res.items() if k not in ("items",)}


def cmd_build(a: argparse.Namespace) -> int:
    since, now = _window(a)
    data_root = Path(a.data_root)
    out = Path(a.out) if a.out else data_root / C.EVENT_NODES_DIRNAME
    EN.check_inputs(EN.default_paths(data_root))       # refuse before anything is created
    with EN.store_lock(out / EN.STORE_NAME):
        return _build_locked(a, data_root, out, since, now)


def _build_locked(a: argparse.Namespace, data_root: Path, out: Path, since: datetime, now: datetime) -> int:
    res = EN.build(data_root, since=since, now=now, store_path=out / EN.STORE_NAME)
    for line in table(res, a.top, now):
        print(line)
    if res["read"]["rows_read"] == 0:
        # zero rows across EVERY source is a dead collector until shown otherwise
        raise EN.EventNodesRefused(EN.NO_CORPUS_ROWS, f"no corpus or filing row in {res['since']} .. "
                                                      f"{res['now']} across all sources; nothing built")
    if not res["nodes"]:
        raise EN.EventNodesRefused(EN.NO_EVENTS_FROM_ROWS,
                                   f"{res['read']['rows_read']} rows read and no event built")
    store = EN.append_rows(out / EN.STORE_NAME, res["nodes"], retire=res["retire"], parents=res["parents"],
                           at=res["now"])
    rec_dir = out / "receipts"
    rec_dir.mkdir(parents=True, exist_ok=True)
    rec = _strip(res)
    rec["store"] = store
    rec["chain"] = EN.verify_chain(out / EN.STORE_NAME)
    (rec_dir / f"{res['build_id']}.json").write_text(json.dumps(rec, indent=1, sort_keys=True, default=str),
                                                      encoding="utf-8")
    (rec_dir / f"{res['build_id']}.md").write_text(_md(res, a.top, now, store), encoding="utf-8")
    print(f"store {store}; chain {rec['chain']}")
    print(f"receipt {rec_dir / (res['build_id'] + '.json')}")
    return 0


def cmd_fill(a: argparse.Namespace) -> int:
    since, now = _window(a)
    out_dir = Path(a.out) if a.out else Path(a.data_root) / C.EVENT_NODES_DIRNAME
    res = EN.build(Path(a.data_root), since=since, now=now, store_path=out_dir / EN.STORE_NAME)
    by_key = {i.key: i for i in res["items"]}
    top = res["nodes"][:a.top]
    if not a.dry_run:
        out = out_dir
        for n in top:
            fill = EN.fill_event(n, EN.evidence_texts(n, by_key))
            EN.append_fill(out / EN.STORE_NAME, fill)
            print(f"{n['event_id']}: {fill['status']} accepted {fill['n_accepted']} refused {fill['refused']}")
        return 0
    total = 0.0
    total_bound = 0.0
    for n in top:
        d = EN.dry_run_cost(n, EN.evidence_texts(n, by_key))
        total += d["projected_usd_at_max_output"]
        total_bound += d["reservation_bound_usd"]
        print(f"#{n['rank_at_build']} {n['primary_ticker']:6s} {d['event_id']}: prompt {d['prompt_chars']} chars, "
              f"~{d['est_tokens_in']} tokens in + {d['max_tokens_out']} out max; projected "
              f"${d['projected_usd_at_max_output']:.5f} ({d['price_model']}), reservation bound "
              f"${d['reservation_bound_usd']:.5f}")
        if a.show_prompt:
            print("SYSTEM:", d["system"])
            user = d["user"]
            if not a.show_bodies:
                user = "\n".join(ln for ln in user.splitlines()
                                 if ln.startswith(("EVENT", "CONNECTED", "EVIDENCE", "[")))
                user += "\n[article body excerpts not printed: licensed content]"
            print("USER:", user)
    print(f"TOTAL top {len(top)}: projected ${total:.5f}, reservation bound ${total_bound:.5f}; "
          f"no call was made (dry run)")
    return 0


def daily_receipt(r: dict, top: int) -> dict:
    """The SMALL per-run receipt: counts, the ids that changed, the top-N summary
    (ids, tickers, importance; never a title). The full dump is `--full-receipt`."""
    res, st = r["res"], r["store"]
    rd = res["read"]
    return {"schema": "event-nodes-daily/1", "build_id": res["build_id"], "since": res["since"], "now": res["now"],
            "window_hours": r["window_hours"], "summary": r["summary"],
            "read": {k: rd.get(k) for k in ("rows_read", "files", "items", "dropped_after_now",
                                            "dropped_not_news", "rows_unresolved", "bad_json_lines")},
            "n_events": len(res["nodes"]), "n_new_ids": r["new_ids"],
            "appended_versions": st["appended_nodes"], "unchanged": st["unchanged"],
            "retired": st["retired"], "appended_parents": st["appended_parents"],
            "appended_event_ids": st.get("appended_ids", []), "retired_event_ids": st.get("retired_ids", []),
            "rows_before": r["rows_before"], "chain": r["chain"],
            "graph": {k: (res.get("graph") or {}).get(k) for k in ("status", "build_id", "as_of")},
            "calendar": {k: (res.get("calendar") or {}).get(k) for k in ("status", "file", "written_utc")},
            "catalyst_calendar": {k: (res.get("catalyst_calendar") or {}).get(k)
                                  for k in ("status", "file", "written_utc")},
            "top": [{"rank": n["rank_at_build"], "event_id": n["event_id"], "ticker": n["primary_ticker"],
                     "importance_0": n["importance"]["importance_0"],
                     "importance_now": EN.importance_now(n, EN._utc(res["now"])), "n_evidence": n["n_evidence"],
                     "n_publishers": n["importance"]["facts"]["n_publishers"]} for n in res["nodes"][:top]]}


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if tmp.read_text(encoding="utf-8") != text:
        raise OSError(f"read-back mismatch writing {tmp}")
    tmp.replace(path)


def cmd_daily(a: argparse.Namespace) -> int:
    now = _parse(a.now) if a.now else datetime.now(timezone.utc).replace(microsecond=0)
    data_root = Path(a.data_root)
    out = Path(a.out) if a.out else data_root / C.EVENT_NODES_DIRNAME
    try:
        r = EN.daily(data_root, now=now, out=out, window_hours=a.window_hours)
    except EN.EventNodesRefused as exc:
        if exc.code == EN.STORE_LOCKED:
            print(f"EVENT_NODES_DAILY SKIP {exc.code}: another build holds the store ({exc.detail})")
            return 0
        raise
    small = daily_receipt(r, int(C.EVENT_NODES_DAILY_TOP_N))
    body = json.dumps(small, indent=1, sort_keys=True, default=str)
    _atomic(out / "daily_latest.json", body)
    line = {k: small[k] for k in ("build_id", "now", "n_events", "n_new_ids", "appended_versions", "unchanged",
                                  "retired", "appended_parents", "rows_before")}
    line.update({"chain_ok": r["chain"]["ok"], "chain_n": r["chain"]["n"], "receipt_bytes": len(body.encode())})
    with (out / "daily_runs.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, sort_keys=True) + "\n")
    if a.full_receipt:
        rec_dir = out / "receipts"
        rec_dir.mkdir(parents=True, exist_ok=True)
        rec = _strip(r["res"])
        rec.update({"store": r["store"], "chain": r["chain"], "daily": True, "summary": r["summary"]})
        (rec_dir / f"{r['res']['build_id']}.json").write_text(json.dumps(rec, indent=1, sort_keys=True,
                                                                         default=str), encoding="utf-8")
    print(r["summary"] + f" receipt_bytes={len(body.encode())}")
    return 0 if r["chain"]["ok"] else 2


def cmd_repair_tail(a: argparse.Namespace) -> int:
    store = Path(a.out) / EN.STORE_NAME
    with EN.store_lock(store):
        r = EN.repair_tail(store, dry_run=a.dry_run)
    print(json.dumps(r, ensure_ascii=False, default=str))
    return 0 if r["status"] in ("NO_TORN_TAIL", "DRY_RUN") or (r.get("chain") or {}).get("ok") else 2


def cmd_verify(a: argparse.Namespace) -> int:
    v = EN.verify_chain(Path(a.out) / EN.STORE_NAME)
    print(json.dumps(v))
    return 0 if v["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.event_nodes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "fill"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", required=True)
        p.add_argument("--out")
        p.add_argument("--since")
        p.add_argument("--now")
        p.add_argument("--top", type=int, default=10 if name == "build" else int(C.EVENT_NODES_FILL_TOP_N))
        if name == "fill":
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--show-prompt", action="store_true")
            p.add_argument("--show-bodies", action="store_true")
    p = sub.add_parser("daily")
    p.add_argument("--data-root", required=True)
    p.add_argument("--out")
    p.add_argument("--now")
    p.add_argument("--window-hours", type=float, default=None)
    p.add_argument("--full-receipt", action="store_true",
                   help="also write the full build dump to receipts/ (attended runs only; ~5 MB)")
    p = sub.add_parser("verify")
    p.add_argument("--out", required=True)
    p = sub.add_parser("repair-tail")
    p.add_argument("--out", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        return {"build": cmd_build, "fill": cmd_fill, "verify": cmd_verify,
                "daily": cmd_daily, "repair-tail": cmd_repair_tail}[a.cmd](a)
    except EN.EventFillRefused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}")
        return 3
    except EN.EventNodesRefused as exc:
        print(f"EVENT_NODES_{a.cmd.upper()} REFUSED {exc.code}: {exc.detail}" if a.cmd == "daily"
              else f"REFUSED {exc.code}: {exc.detail}")
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
