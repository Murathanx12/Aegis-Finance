"""Private, create-only owner view of the canonical registry and explicit receipts."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

from scripts import beta_v2_atlas_view as atlas
from scripts import beta_v2_registry as registry_api

EVIDENCE_ROOT = Path.home() / "aegis-recovery-evidence"


class CockpitRefused(ValueError):
    """Missing, changed or unsupported view inputs; no operational action."""


def require(ok, reason):
    if not ok:
        raise CockpitRefused(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(spec, as_of):
    require(
        isinstance(spec, dict) and all(spec.get(k) for k in ("path", "sha256", "captured_at")),
        "explicit_path_hash_capture_clock_required",
    )
    captured = atlas.clock(spec["captured_at"])
    require(captured <= as_of, "capture_after_view_as_of")
    path = Path(spec["path"]).resolve(strict=True)
    require(
        path.is_file() and path.stat().st_size <= atlas.LIMIT_BYTES, "bounded_input_file_required"
    )
    raw = path.read_bytes()
    require(len(raw) <= atlas.LIMIT_BYTES and digest(raw) == spec["sha256"], "input_hash_mismatch")
    require(digest(path.read_bytes()) == digest(raw), "input_changed_during_read")
    return raw, {
        "path": str(path),
        "sha256": digest(raw),
        "bytes": len(raw),
        "captured_at": spec["captured_at"],
        "read_at": datetime.now(timezone.utc).isoformat(),
    }


def project(manifest, manifest_ref):
    """Reuse canonical identity/baseline rules and typed direct-task evidence queries."""
    require(manifest.get("schema") == "owner_cockpit_inputs/1", "explicit_input_manifest_required")
    current_read = manifest["as_of"] == "now"
    as_of = datetime.now(timezone.utc) if current_read else atlas.clock(manifest["as_of"])
    root = Path(manifest["registry_root"]).resolve(strict=True)
    raw, ref = read_bound(manifest["registry"], as_of)
    value = registry_api.strict_json(raw)
    baseline_raw, baseline_ref = read_bound(manifest["baseline"], as_of)
    require(
        baseline_ref["sha256"] == registry_api.SOURCE_BASELINE_SHA256,
        "independent_source_baseline_pin_mismatch",
    )
    require(
        Path(baseline_ref["path"]) == (registry_api.ROOT / registry_api.SOURCE_BASELINE).resolve(),
        "use_existing_code_pinned_baseline",
    )
    baseline = registry_api.strict_json(baseline_raw)
    for group, ids in (
        ("tasks", registry_api.TASK_IDS),
        ("requests", registry_api.REQUEST_IDS),
        ("hypotheses", registry_api.HYPOTHESIS_IDS),
    ):
        rows = value.get(group, [])
        require(
            len(rows) == len(ids) and {r["id"] for r in rows} == set(ids),
            "full_canonical_denominator_required_" + group,
        )
    evidence = manifest.get("evidence")
    require(
        isinstance(evidence, list) and len(evidence) <= 15, "explicit_evidence_list_required_max_15"
    )
    docs = [{"kind": "registry", "value": value, "ref": ref}]
    for item in evidence:
        require(item.get("kind") == "receipt", "only_explicit_opaque_receipts_supported")
        _, evidence_ref = read_bound(item, as_of)
        docs.append({"kind": "receipt", "value": None, "ref": evidence_ref})
    require(len({d["ref"]["path"] for d in docs}) == len(docs), "duplicate_input_path")

    # validate() can follow evidence/routing references. Never let it read a file
    # which the operator did not explicitly supply, even for structural checks.
    supplied = {d["ref"]["path"] for d in docs}
    references = []
    for group in ("tasks", "requests", "hypotheses"):
        for row in value[group]:
            references.extend(row.get("evidence", []))
            if row.get("routing_override"):
                references.append(row["routing_override"]["evidence"])
    missing = sorted({str((root / e["path"]).resolve()) for e in references} - supplied)
    validation = {"status": "NOT_RUN_UNSUPPLIED_REFERENCES", "errors": [], "missing_paths": missing}
    if not missing:
        errors = registry_api.validate(value, root=root)
        validation.update(
            status="STRUCTURAL_ERRORS" if errors else "STRUCTURAL_CHECK_PASSED", errors=errors
        )
    original_requests = {r["id"]: r for r in baseline["binding"]["requests"]}
    original_tasks = {r["id"]: r for r in baseline["binding"]["tasks"]}
    for row in value["requests"]:
        require(
            row["source_task_id"] == original_requests[row["id"]]["task_id"],
            "original_request_ownership_mismatch",
        )
    as_of = datetime.now(timezone.utc) if current_read else as_of
    require(
        all(atlas.clock(d["ref"]["read_at"]) <= as_of for d in docs),
        "current_registry_read_cannot_replay_earlier_as_of",
    )
    typed = atlas.Projection(docs, as_of.isoformat(), root).build()
    rows_by_id = {r["id"]: r for r in value["tasks"]}
    task_evidence = {}
    for row in value["tasks"]:
        task_evidence[row["id"]] = atlas.query(typed, "operational:task:" + row["id"], "evidence")

    def display(row, group):
        result = dict(row)
        parent = row["id"] if group == "tasks" else row["task_id"]
        require(parent in rows_by_id, "unknown_parent_task")
        deps = list(row.get("dependencies", []))
        if group == "tasks":
            deps += original_tasks[parent]["dependencies"]
        elif group == "requests":
            for task in {parent, row["source_task_id"]}:
                deps += original_tasks[task]["dependencies"] + rows_by_id[task]["dependencies"]
        else:
            deps += list(registry_api.HYPOTHESIS_PREREQUISITES)
        result["effective_dependencies"] = sorted(set(deps))
        result["open_dependencies"] = [
            d
            for d in result["effective_dependencies"]
            if rows_by_id.get(d, {}).get("status") != "completed"
        ]
        if group == "tasks":
            result["task_evidence"] = task_evidence[parent]
        key = (
            "operational:"
            + {"tasks": "task", "requests": "request", "hypotheses": "hypothesis"}[group]
            + ":"
            + row["id"]
        )
        direct = [
            e for e in typed["edges"] if e["from"] == key and e["relation"] == "registered_evidence"
        ]
        result["evidence_state"] = (
            "Direct receipt linked" if direct else "No verified direct receipt supplied"
        )
        result["gaps"] = [
            g["reason"] for g in typed["unresolved"] + typed["excluded"] if g["owner"] == key
        ]
        return result

    return {
        "schema": "owner_cockpit_view/1",
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "planning_date": value["as_of"],
        "tasks": [display(r, "tasks") for r in value["tasks"]],
        "requests": [display(r, "requests") for r in value["requests"]],
        "hypotheses": [display(r, "hypotheses") for r in value["hypotheses"]],
        "slices": value.get("execution_slices", []),
        "validation": validation,
        "source_refs": [manifest_ref, baseline_ref] + [d["ref"] for d in docs],
        "source_attestation": "Not performed; structural validation is not original archive attestation",
        "atlas_summary": {k: len(typed[k]) for k in ("nodes", "edges", "unresolved", "excluded")},
    }


def text(value):
    return escape(str(value if value is not None else "Not supplied"), quote=True)


def links(ids):
    return (
        ", ".join('<a href="#task-' + text(i) + '">' + text(i) + "</a>" for i in ids)
        or "None declared"
    )


def detail(row, group):
    parent = row.get("task_id", row["id"])
    acceptance = "".join("<li>" + text(a["description"]) + "</li>" for a in row["acceptance"])
    evidence = (
        "".join(
            "<li>"
            + text(e.get("summary"))
            + "<br><code>"
            + text(e.get("path"))
            + "</code><br>Verified at "
            + text(e.get("verified_at"))
            + " / "
            + text(e.get("sha256"))
            + "</li>"
            for e in row.get("evidence", [])
        )
        or "<li>No evidence registered for this item.</li>"
    )
    return (
        '<details class="item" data-group="'
        + group
        + '" data-id="'
        + text(row["id"])
        + '"><summary><span class="key">'
        + text(row["id"])
        + "</span><span>"
        + text(row["title"])
        + "</span><small>"
        + text(row["status"])
        + '</small></summary><div class="detail"><p>'
        + text(row.get("summary", row.get("deliverable", row.get("first_comparison"))))
        + "</p><p>Owner: "
        + text(row["owner"])
        + " / Task: "
        + links([parent])
        + " / Priority: "
        + text(row.get("priority"))
        + "</p><p>Prerequisites: "
        + links(row["effective_dependencies"])
        + '</p><p class="notice">Open prerequisites: '
        + links(row["open_dependencies"])
        + ".</p><h4>What would demonstrate this</h4><ul>"
        + acceptance
        + "</ul><h4>Evidence</h4><p>"
        + text(row["evidence_state"])
        + ". A linked receipt is not completion certification.</p><ul>"
        + evidence
        + "</ul><p>Unresolved: "
        + text(", ".join(row["gaps"]) or "No additional typed join gaps")
        + "</p><h4>Next review</h4><p>"
        + text(row["revisit"])
        + "</p><p>Source: "
        + text(json.dumps(row["source"], sort_keys=True))
        + " / Previous state: "
        + text(row["legacy_resolution"])
        + "</p></div></details>"
    )


CSS = """
:root{color-scheme:light;--ink:#111;--paper:#fff;--wash:#f3f3f3;--line:#ccc;--muted:#505050;--mono:Consolas,'Courier New',monospace}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.55 'Segoe UI',Arial,Helvetica,sans-serif}
main{max-width:1520px;margin:auto;padding:0 36px 64px}header{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,340px);gap:48px;align-items:end;background:#000;color:#fff;margin:0 -36px 28px;padding:42px 36px 34px;border-bottom:4px solid #111}
header>div{min-width:0}header p{color:#d1d1d1}h1{font-size:clamp(38px,4.6vw,68px);line-height:1.04;letter-spacing:-.045em;margin:22px 0 20px;font-weight:700;max-width:14ch}
h2{font-size:27px;line-height:1.2;letter-spacing:-.025em;margin:0 0 16px;padding-top:15px;border-top:3px solid #111}h3{font-size:19px;margin:24px 0 10px}h4{margin:18px 0 5px;font-size:16px}
p{max-width:80ch;margin:8px 0}a{color:inherit;text-underline-offset:4px;text-decoration-thickness:1px}a:hover{text-decoration-thickness:2px}
a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,button:focus-visible{outline:3px solid currentColor;outline-offset:4px}header a:focus-visible{outline-color:#fff}
button:focus-visible{outline-color:var(--ink)}
.edition{font:12px/1.6 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:#d1d1d1;border-bottom:1px solid #666;padding-bottom:16px;margin-top:0}
.ledger{border-left:1px solid #777;padding:4px 0 4px 26px;font-size:16px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.ledger strong{font-size:36px;line-height:1.2;letter-spacing:-.035em;font-weight:650}.ledger .dates{font:12px/1.8 var(--mono);color:#ccc;margin-top:20px}
.notice{color:#222;background:#fff;border-left:4px solid #111;padding:14px 18px;max-width:none;font-size:15px}
section{position:relative;min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:0;margin:28px 0;padding:26px}
section::before,section::after{content:'';position:absolute;width:16px;height:16px;pointer-events:none;border-color:#111;border-style:solid}
section::before{top:-1px;left:-1px;border-width:3px 0 0 3px}section::after{bottom:-1px;right:-1px;border-width:0 3px 3px 0}
.filters{display:grid;grid-template-columns:minmax(200px,2fr) repeat(3,minmax(130px,1fr)) auto;gap:16px;align-items:end}.filters label{display:grid;min-width:0;gap:8px;font:12px/1.5 var(--mono);letter-spacing:.035em}
input,select,button{font:15px/1.45 'Segoe UI',Arial,sans-serif;border:1px solid #666;border-radius:0;padding:11px 10px;background:#fff;color:var(--ink);min-width:0;max-width:100%;min-height:46px}button{cursor:pointer;background:#111;color:#fff;border-color:#111;font-weight:600}button:hover{background:#333}
.result-count{font:14px/1.6 var(--mono);font-variant-numeric:tabular-nums;color:#111;margin:20px 0 2px}
.table-scroll{overflow:auto;max-width:100%;overscroll-behavior-inline:contain}table{width:100%;min-width:1100px;border-collapse:collapse;font-size:14px;line-height:1.55;text-align:left;table-layout:fixed}
caption{text-align:left;color:var(--muted);margin:0 0 14px;font-size:14px}th{font:12px/1.5 var(--mono);font-weight:700;letter-spacing:.015em;background:#111;color:#fff}
th,td{padding:14px 13px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th:first-child{width:31%}th:nth-child(2){width:13%}th:nth-child(3){width:15%}th:nth-child(4){width:22%}th:nth-child(5){width:19%}td:first-child strong{font-size:15px}td p{margin:6px 0;max-width:40ch}tbody tr:nth-child(even){background:#f5f5f5}tbody tr:hover{background:#ebebeb}
small,.muted{color:var(--muted)}code{font:13px/1.6 var(--mono);overflow-wrap:anywhere}pre{font:13px/1.6 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%;padding:16px;background:var(--wash);border-left:2px solid #111}
.item{border-top:1px solid var(--line)}summary{display:flex;gap:16px;align-items:baseline;cursor:pointer;padding:17px 4px;list-style:revert}summary:hover{background:#f5f5f5}.key{font:700 13px/1.6 var(--mono);color:#111;min-width:52px}summary>span:nth-child(2){flex:1;min-width:0;overflow-wrap:anywhere}summary small{min-width:120px;font-size:13px}
details[open]{border-top:2px solid #111}details[open]>summary{background:#f3f3f3}.detail{padding:6px 18px 24px 72px;max-width:105ch;overflow-wrap:anywhere}.detail li{margin:7px 0;overflow-wrap:anywhere}.detail ul{padding-left:22px}
.sources li{margin:20px 0}.sources code{display:block}.dates{font-size:13px;color:var(--muted);overflow-wrap:anywhere}[hidden]{display:none!important}nav{display:flex;gap:12px 24px;flex-wrap:wrap;margin-top:24px}nav a{padding:5px 0;font-size:14px;color:#fff}.empty{padding:20px;background:var(--wash)}footer{border-top:1px solid #111;padding-top:18px;color:var(--muted);font-size:13px}
section,tr{scroll-margin-top:20px}
@media(max-width:1100px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}.filters label:first-child{grid-column:1/-1}.filters button{justify-self:start;min-width:140px}header{gap:28px;grid-template-columns:minmax(0,1fr) minmax(240px,300px)}}
@media(max-width:760px){main{padding:0 16px 40px}header{grid-template-columns:1fr;gap:28px;margin:0 -16px 22px;padding:30px 20px}h1{font-size:44px}.edition{font-size:11px;letter-spacing:.12em}.ledger{border-left:0;border-top:1px solid #777;padding:20px 0 0;max-width:100%}.ledger strong{font-size:32px}.ledger .dates{margin-top:12px}section{margin:22px 0;padding:20px 16px}h2{font-size:24px}.filters{gap:16px 12px}.filters label{letter-spacing:0}summary{flex-wrap:wrap;gap:7px 12px}summary>.key{min-width:52px}summary>span:nth-child(2){flex-basis:calc(100% - 68px)}summary small{margin-left:64px;min-width:0}.detail{padding:12px 4px 22px}.sources{padding-left:22px}.notice{padding:12px 14px}nav{gap:10px 22px}}
@media(max-width:380px){.filters{grid-template-columns:minmax(0,1fr)}.filters label:first-child{grid-column:auto}h1{font-size:38px}}
@media(max-width:760px){caption{width:calc(100vw - 66px);max-width:calc(100vw - 66px)}}
/* Phone task ledger: retain native table/header semantics and stack all five cells. */
@media screen and (max-width:760px){
.table-scroll{overflow:visible}
table{display:block;min-width:0;table-layout:auto}
caption{display:block;width:100%;max-width:100%}
thead{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);clip-path:inset(50%);white-space:nowrap}
tbody{display:block}
tbody tr{display:block;border-top:3px solid var(--ink);margin-top:18px}
tbody td{display:block;width:100%;padding:12px 13px}
tbody td::before{display:block;margin-bottom:6px;font:700 12px/1.5 var(--mono);letter-spacing:.015em;color:var(--ink)}
tbody td:nth-child(1)::before{content:"Task and deliverable"}
tbody td:nth-child(2)::before{content:"Owner / recorded state"}
tbody td:nth-child(3)::before{content:"Prerequisites"}
tbody td:nth-child(4)::before{content:"Direct task evidence"}
tbody td:nth-child(5)::before{content:"Next review / receipt dates"}
}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
@media print{.filters,button{display:none}body{background:#fff}main{max-width:none;padding:0}header{margin:0;padding:26px;print-color-adjust:exact;-webkit-print-color-adjust:exact}section{break-inside:auto;padding:18px}details{break-inside:avoid}table{min-width:0;table-layout:auto;font-size:10px}th{print-color-adjust:exact;-webkit-print-color-adjust:exact}th,td{padding:6px}.table-scroll{overflow:visible}}
"""

JS = """
(()=>{'use strict';
const model=JSON.parse(document.getElementById('cockpit-data').textContent);
function matches(row,filters){
 const {task_evidence,...searchable}=row;
 const haystack=JSON.stringify(searchable).toLocaleLowerCase();
 return (!filters.q||haystack.includes(filters.q.toLocaleLowerCase()))&&
 (!filters.task||(row.task_id||row.id)===filters.task)&&
 (!filters.status||row.status===filters.status)&&
 (!filters.evidence||row.evidence_state===filters.evidence);
}
globalThis.ownerCockpit={model,matches};
document.addEventListener('DOMContentLoaded',()=>{
 const $=id=>document.getElementById(id);
 const controls=['q','task','status','evidence'].map($);
 function options(id,values){for(const value of values)$(id).add(new Option(value,value));}
 options('task',model.tasks.map(r=>r.id));
 options('status',[...new Set([...model.tasks,...model.requests,...model.hypotheses].map(r=>r.status))].sort());
 options('evidence',[...new Set(model.requests.map(r=>r.evidence_state))].sort());
 function update(){
  const filters=Object.fromEntries(controls.map(c=>[c.id,c.value.trim()]));
  const visible=new Set(model.requests.filter(r=>matches(r,filters)).map(r=>r.id));
  for(const node of document.querySelectorAll('[data-group="requests"]'))node.hidden=!visible.has(node.dataset.id);
  const tasks=model.tasks.filter(r=>matches(r,filters));
  for(const node of document.querySelectorAll('[data-group="tasks"]'))node.hidden=!tasks.some(r=>r.id===node.dataset.id);
  for(const node of document.querySelectorAll('[data-group="hypotheses"]'))node.hidden=!matches(model.hypotheses.find(r=>r.id===node.dataset.id),filters);
  $('request-count').textContent=visible.size+' of '+model.requests.length+' requests shown';
  $('task-count').textContent=tasks.length+' of '+model.tasks.length+' tasks shown';
  $('empty').hidden=visible.size!==0;
 }
 for(const c of controls)c.addEventListener(c.id==='q'?'input':'change',update);
 $('reset').addEventListener('click',()=>{for(const c of controls)c.value='';update();});
 document.addEventListener('click',event=>{
  if(event.target.closest&&event.target.closest('a[href^="#task-"]')){
   for(const c of controls)c.value='';update();
  }
 });
 update();
});})();
"""


def render(model):
    task_rows = []
    for row in model["tasks"]:
        count = sum(r["task_id"] == row["id"] for r in model["requests"])
        proof = row["task_evidence"]
        task_rows.append(
            '<tr id="task-'
            + text(row["id"])
            + '" data-group="tasks" data-id="'
            + text(row["id"])
            + '"><td><strong>'
            + text(row["id"])
            + " / "
            + text(row["title"])
            + "</strong><p>"
            + text(row["deliverable"])
            + "</p><small>"
            + str(count)
            + " mapped requests</small></td><td>"
            + text(row["owner"])
            + "<p>"
            + text(row["status"])
            + "</p></td><td>"
            + links(row["effective_dependencies"])
            + "<p>Open: "
            + links(row["open_dependencies"])
            + "</p></td><td>"
            + text(row["evidence_state"])
            + "<p>"
            + str(len(proof["paths"]))
            + " direct; "
            + str(len(proof["dependency_paths"]))
            + " prerequisite paths</p><small>Prerequisite receipts do not fulfill this task.</small></td><td>"
            + text(row["revisit"])
            + '<p class="dates">Receipt dates: '
            + text(", ".join(e["verified_at"] for e in row["evidence"]) or "Not supplied")
            + "</p></td></tr>"
        )
    sources = "".join(
        "<li><code>"
        + text(r["path"])
        + "</code><code>SHA-256 "
        + text(r["sha256"])
        + '</code><span class="dates">Capture assertion: '
        + text(r.get("captured_at"))
        + " / Read: "
        + text(r["read_at"])
        + " / "
        + str(r["bytes"])
        + " bytes</span></li>"
        for r in model["source_refs"]
    )
    data = (
        json.dumps(model, ensure_ascii=True, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    script_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'sha256-"
        + script_hash
        + "'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'\">"
        "<title>Aegis / Private owner desk</title><style>"
        + CSS
        + '</style><body><main><header><div><p class="edition">Aegis Beta V2 / Private planning snapshot</p>'
        "<h1>What needs proof next.</h1><p>One view of the existing registry: who owns the work, what it depends on, and which receipts are actually linked.</p>"
        '<nav><a href="#tasks">Tasks</a><a href="#requests">Requests</a><a href="#hypotheses">Hypotheses</a><a href="#sources">Sources and dates</a></nav></div>'
        '<div class="ledger"><strong>146 requests</strong><br>17 tasks / 28 hypotheses<p class="dates">Planning date: '
        + text(model["planning_date"])
        + "<br>View as of: "
        + text(model["as_of"])
        + "<br>Generated: "
        + text(model["generated_at"])
        + "</p></div></header>"
        '<p class="notice">Recorded planning states and receipt links are shown separately. Missing proof stays visible. This page does not establish current runtime health, completed work or investment acceptance.</p>'
        '<section aria-label="Filters"><div class="filters"><label>Search requests, owners or proof<input id="q" type="search" placeholder="Try funnel, C10 or a source name"></label>'
        '<label>Task<select id="task"><option value="">All tasks</option></select></label><label>Recorded status<select id="status"><option value="">All statuses</option></select></label>'
        '<label>Direct evidence<select id="evidence"><option value="">All evidence states</option></select></label><button id="reset" type="button">Reset filters</button></div>'
        '<p class="result-count" id="request-count" role="status" aria-live="polite">146 of 146 requests shown</p>'
        '<p id="empty" class="empty" hidden>No requests match these filters. Reset filters to return to all 146.</p><noscript>All records are visible. Enable local JavaScript to filter; no network is used.</noscript></section>'
        '<section id="tasks"><h2>Tasks and prerequisites</h2><p id="task-count">17 of 17 tasks shown</p><div class="table-scroll"><table><caption>Recorded status is not a live completion verdict. Dates refer to retained receipts.</caption>'
        '<thead><tr><th scope="col">Task and deliverable</th><th scope="col">Owner / recorded state</th><th scope="col">Prerequisites</th><th scope="col">Direct task evidence</th><th scope="col">Next review / receipt dates</th></tr></thead><tbody>'
        + "".join(task_rows)
        + '</tbody></table></div></section><section id="requests"><h2>Every request, with its proof conditions</h2>'
        + "".join(detail(r, "requests") for r in model["requests"])
        + '</section><section id="hypotheses"><h2>Research hypotheses</h2>'
        "<p>These 28 registry entries are administrative research plans. They are not registered experiments or measured results.</p>"
        + "".join(detail(r, "hypotheses") for r in model["hypotheses"])
        + '</section><section id="sources"><h2>Sources and dates</h2><p>'
        + text(model["source_attestation"])
        + ".</p><p>Structural check: "
        + text(model["validation"]["status"])
        + ". Input capture clocks are operator assertions; read clocks are generated by this build. Neither is a missing receipt verification date.</p><pre>"
        + text(json.dumps(model["validation"], indent=2))
        + '</pre><ol class="sources">'
        + sources
        + "</ol></section><footer>Private derived view. The canonical registry remains authoritative. No action buttons, dispatch, database, live service connection or served-model claim.</footer></main>"
        '<script id="cockpit-data" type="application/json">'
        + data
        + "</script><script>"
        + JS
        + "</script></body></html>"
    )
    return page


def build(manifest=None, *, manifest_sha256=None, output_dir=None):
    require(
        manifest is not None and manifest_sha256 and output_dir is not None,
        "explicit_manifest_hash_output_required",
    )
    path = Path(manifest).resolve(strict=True)
    require(path.stat().st_size <= atlas.LIMIT_BYTES, "bounded_manifest_required")
    raw = path.read_bytes()
    require(digest(raw) == manifest_sha256, "manifest_hash_mismatch")
    ref = {
        "path": str(path),
        "sha256": digest(raw),
        "bytes": len(raw),
        "captured_at": None,
        "read_at": datetime.now(timezone.utc).isoformat(),
    }
    model = project(registry_api.strict_json(raw), ref)
    output = Path(output_dir).absolute()
    require(
        not output.exists()
        and output.resolve().is_relative_to(EVIDENCE_ROOT.resolve())
        and not output.resolve().is_relative_to(registry_api.ROOT.resolve()),
        "new_private_evidence_directory_required",
    )
    require(
        not any(
            p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
            for p in (output, *output.parents)
        ),
        "output_alias_refused",
    )
    page = render(model).encode()
    require(len(page) <= 5 * 1024**2, "bounded_output_required")
    for source in model["source_refs"]:
        require(
            digest(Path(source["path"]).read_bytes()) == source["sha256"],
            "source_changed_during_projection",
        )
    output.mkdir()
    with (output / "index.html").open("xb") as handle:
        handle.write(page)
    receipt = {
        "schema": "owner_cockpit_build/1",
        "generated_at": model["generated_at"],
        "html_sha256": digest(page),
        "requests": len(model["requests"]),
        "tasks": len(model["tasks"]),
        "hypotheses": len(model["hypotheses"]),
        "source_refs": model["source_refs"],
        "native_writes": 0,
        "scope": "PRIVATE_SAVED_PLANNING_VIEW",
    }
    with (output / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        receipt = build(
            args.manifest, manifest_sha256=args.manifest_sha256, output_dir=args.output_dir
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, "Owner view refused: " + str(exc) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
