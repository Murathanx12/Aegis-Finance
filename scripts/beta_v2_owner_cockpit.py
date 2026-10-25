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
:root{color-scheme:light;--ink:#172b43;--blue:#245b88;--paper:#fff;--wash:#f2f5f8;--line:#d5dfe8;--muted:#4f6071;--warn:#784212}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.55 'Segoe UI',Tahoma,sans-serif}
main{max-width:1420px;margin:auto;padding:36px 32px 70px}header{display:grid;grid-template-columns:1fr auto;gap:30px;align-items:end;padding-bottom:26px}
h1{font-size:clamp(30px,4vw,48px);line-height:1.12;letter-spacing:-.04em;margin:8px 0 16px;font-weight:650}h2{font-size:25px;letter-spacing:-.02em;margin:0 0 14px}h3{font-size:19px;margin:24px 0 10px}h4{margin:16px 0 4px}
p{max-width:80ch;margin:8px 0}a{color:var(--blue);text-underline-offset:3px}a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,button:focus-visible{outline:3px solid #b55b16;outline-offset:3px}
.edition{color:var(--muted)}.ledger{border-left:4px solid var(--blue);padding:6px 16px;min-width:235px;font-size:15px}.ledger strong{font-size:23px;font-weight:650}.notice{color:var(--warn);background:#fff7e9;border-left:3px solid #b87829;padding:12px 16px}
section{background:var(--paper);border:1px solid var(--line);border-radius:10px;margin:24px 0;padding:24px}.filters{display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:14px;align-items:end}.filters label{display:grid;gap:5px;font-size:14px;font-weight:600}
input,select,button{font:inherit;border:1px solid #aabac9;border-radius:5px;padding:10px;background:white;color:var(--ink);min-width:0}button{cursor:pointer;background:var(--blue);color:white;border-color:var(--blue)}.result-count{font-size:17px;color:var(--blue);margin:18px 0 6px}
.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;text-align:left}caption{text-align:left;color:var(--muted);margin:0 0 12px}th{font-weight:650;background:#eef3f7;color:#2a4660}th,td{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}td:first-child{min-width:230px}td p{margin:4px 0;max-width:40ch}small,.muted{color:var(--muted)}code{font:13px/1.5 Consolas,monospace;overflow-wrap:anywhere}
.item{border-top:1px solid var(--line)}summary{display:flex;gap:16px;align-items:baseline;cursor:pointer;padding:14px 4px;list-style:revert}.key{font-weight:650;color:var(--blue);min-width:46px}summary>span:nth-child(2){flex:1}summary small{min-width:120px}.detail{padding:0 10px 22px 66px;max-width:100ch}.detail li{margin:6px 0;overflow-wrap:anywhere}.sources li{margin:16px 0}.sources code{display:block}.dates{font-size:14px;color:var(--muted)}[hidden]{display:none!important}nav{display:flex;gap:20px;flex-wrap:wrap}.empty{padding:20px;background:var(--wash)}footer{color:var(--muted);font-size:14px}
@media(max-width:900px){header{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}main{padding:20px 14px}section{padding:18px}summary{flex-wrap:wrap;gap:8px}.detail{padding-left:12px}.ledger{max-width:380px}}@media print{.filters,button{display:none}body{background:white}main{max-width:none;padding:0}section{break-inside:auto}details{break-inside:avoid}}
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
