"""REPORT-ONLY data-rights audit: public route x data source x public_display.

    python -m scripts.data_rights_audit --out <dir>            # always exit 0
    python -m scripts.data_rights_audit --out <dir> --strict   # exit 1 on a `no`

Static analysis only (no imports of the app, no network, no LLM). For every
route the hosted site serves -- the FastAPI routers plus `@app.<verb>` routes
in backend/main.py, EXCLUDING routers/routes guarded by `check_local_request`
(the desktop-only control plane) -- it walks the handler's call graph, by name,
at most `--depth` levels (default 2: the handler, what it calls, what those
call), and asks of each function body and its module's top-level constants
whether it matches a register source (`detect.patterns` regexes or one of its
`hosts`). Hostnames found in code that belong to NO register source are
reported as UNLISTED.

HONEST LIMITS (also written into the receipt)
  * `partial` = at least one call into repo code could not be resolved.
    `depth_limited` (reported separately, true for most routes) = the walk
    stopped at `--depth` with callees left unread; what lies beyond is unseen.
  * Resolution is by name: direct calls, names passed as arguments, imported
    modules/classes. A method called on an object held in a variable is not
    followed. Where the handler or a traced function makes a call into repo
    code that cannot be resolved, or the walk is cut by the depth limit, the
    route is marked `partial` -- "could not trace" -- and is listed apart.
  * A regex match shows a source CAN be reached, not that every response
    carries it. Module-level constants of a traced module are scanned, so a
    module that mentions a source in a constant attributes it to every traced
    function in it. Over-listing is the safe error here; under-listing is
    possible only through the untraced cases above.
  * The register's flags are as honest as its `date_read`s. UNVERIFIED means
    "do not show publicly" until read.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services import data_rights  # noqa: E402

VERBS = {"get", "post", "put", "delete", "patch"}
GUARD = "check_local_request"
#: router-level guard that applies check_local_request to POST/PUT/PATCH/DELETE
#: only: GET routes on such a router are NOT local-only (reads are served)
UNSAFE_GUARD = "guard_unsafe_methods"
#: `backend.routers.control.control_plane_router(**kw)`: the gated constructor and its
#: default prefix (a test pins both against the real function)
PLANE_ROUTER = "control_plane_router"
PLANE_PREFIX = "/api/control"
#: hosts that are not data sources (schemas, code hosting, our own deploys, loopback)
IGNORED_HOSTS = {
    "www.w3.org", "purl.org", "json-schema.org", "github.com", "doi.org", "127.0.0.1",
    "localhost", "aegis.local", "api.telegram.org", "aegis-finance-production.up.railway.app", "aegis-finance-six.vercel.app",
    "seal-authority-production.up.railway.app", "www.youtube.com", "www.googleapis.com",
    "papers.ssrn.com", "export.arxiv.org", "www.nber.org", "www.acr.org",
    "router.huggingface.co", "integrate.api.nvidia.com", "api.openai.com",
    "api.featherless.ai", "www.composer.trade",
}
#: module-level constants of these name every vendor in the system (config), so
#: scanning them would attribute everything to every route
NO_CONST_SCAN = {"backend.config"}
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


# ------------------------------ module index ------------------------------

class Module:
    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.src = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            self.tree: ast.Module | None = ast.parse(self.src)
        except SyntaxError:
            self.tree = None
        self.defs: dict[str, ast.AST] = {}
        self.classes: dict[str, dict[str, ast.AST]] = {}
        self.imports: dict[str, tuple[str, str | None]] = {}
        self.const_text = ""
        if self.tree is not None:
            self._index()

    def _index(self) -> None:
        assert self.tree is not None
        consts: list[str] = []
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = {
                    n.name: n for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                seg = ast.get_source_segment(self.src, node)
                if seg:
                    consts.append(seg)
        self.const_text = "\n".join(consts)


class Index:
    def __init__(self, root: Path):
        self.root = root
        self.mods: dict[str, Module] = {}

    def modname(self, path: Path) -> str:
        rel = path.relative_to(self.root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def path_for(self, mod: str) -> Path | None:
        p = self.root.joinpath(*mod.split("."))
        if p.with_suffix(".py").is_file():
            return p.with_suffix(".py")
        if (p / "__init__.py").is_file():
            return p / "__init__.py"
        return None

    def get(self, mod: str) -> Module | None:
        if mod in self.mods:
            return self.mods[mod]
        if not (mod == "backend" or mod.startswith("backend.")):
            return None
        p = self.path_for(mod)
        if p is None:
            return None
        m = Module(mod, p)
        self.mods[mod] = m
        self._imports(m)
        return m

    def _imports(self, m: Module) -> None:
        if m.tree is None:
            return
        pkg = m.name if m.path.name == "__init__.py" else m.name.rpartition(".")[0]
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    m.imports[(a.asname or a.name).split(".")[0] if not a.asname else a.asname] = (
                        a.name if a.asname else a.name.split(".")[0], None)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    up = pkg.split(".")
                    up = up[: len(up) - (node.level - 1)] if node.level > 1 else up
                    base = ".".join(up + ([base] if base else []))
                for a in node.names:
                    sub = f"{base}.{a.name}"
                    if self.path_for(sub) is not None:
                        m.imports[a.asname or a.name] = (sub, None)
                    else:
                        m.imports[a.asname or a.name] = (base, a.name)


# ------------------------------ routes ------------------------------

def _const(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _mentions(node: ast.AST, name: str) -> bool:
    return any((isinstance(n, ast.Name) and n.id == name)
               or (isinstance(n, ast.Attribute) and n.attr == name) for n in ast.walk(node))


def _mentions_guard(node: ast.AST) -> bool:
    return _mentions(node, GUARD)


def find_routes(m: Module) -> list[dict[str, Any]]:
    if m.tree is None:
        return []
    routers: dict[str, dict[str, Any]] = {}
    for node in m.tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if fname == PLANE_ROUTER and node.targets and isinstance(node.targets[0], ast.Name):
                # #155: the control plane's one constructor. Every route on such a router is
                # behind `control_plane_gate` (404 off the desktop, loopback-only on it).
                prefix = PLANE_PREFIX
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and _const(kw.value) is not None:
                        prefix = _const(kw.value)
                routers[node.targets[0].id] = {"prefix": prefix, "guarded": True, "unsafe_guarded": False}
            if fname == "APIRouter" and node.targets and isinstance(node.targets[0], ast.Name):
                prefix = ""
                for kw in node.value.keywords:
                    if kw.arg == "prefix":
                        prefix = _const(kw.value) or ""
                routers[node.targets[0].id] = {
                    "prefix": prefix,
                    "guarded": any(kw.arg == "dependencies" and _mentions_guard(kw.value)
                                   for kw in node.value.keywords),
                    "unsafe_guarded": any(kw.arg == "dependencies" and _mentions(kw.value, UNSAFE_GUARD)
                                          for kw in node.value.keywords)}
    out = []
    for fn in ast.walk(m.tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in fn.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in VERBS and isinstance(dec.func.value, ast.Name)):
                continue
            owner = dec.func.value.id
            if owner == "app":
                info = {"prefix": "", "guarded": False, "unsafe_guarded": False}
            elif owner in routers:
                info = routers[owner]
            else:
                continue
            path = _const(dec.args[0]) if dec.args else ""
            guarded = (info["guarded"] or _mentions_guard(dec) or _mentions_guard(fn.args)
                       or (info.get("unsafe_guarded") and dec.func.attr != "get"))
            out.append({"method": dec.func.attr.upper(), "path": (info["prefix"] or "") + (path or ""),
                        "module": m.name, "handler": fn.name, "node": fn, "local_only": guarded})
    return out


# ------------------------------ tracing ------------------------------

def compile_sources(rows: list[dict[str, Any]]):
    comp = []
    for r in rows:
        pats = [re.compile(p, re.I) for p in (r.get("detect") or {}).get("patterns", [])]
        comp.append((r["id"], pats, set(r.get("hosts") or [])))
    return comp


def scan_text(text: str, comp, hosts_known: set[str]) -> tuple[set[str], set[str]]:
    hit: set[str] = set()
    unlisted: set[str] = set()
    for sid, pats, hosts in comp:
        if any(p.search(text) for p in pats):
            hit.add(sid)
    for h in URL_RE.findall(text):
        h = h.lower().rstrip(".")
        owner = next((sid for sid, _, hosts in comp
                      if h in hosts or any(h.endswith("." + x) for x in hosts)), None)
        if owner:
            hit.add(owner)
        elif h not in IGNORED_HOSTS and not any(h.endswith("." + x) for x in IGNORED_HOSTS):
            unlisted.add(h)
    return hit, unlisted


def edges(idx: Index, m: Module, fn: ast.AST) -> tuple[list[tuple[Module, str, ast.AST]], list[str]]:
    """Repo functions `fn` references by name, plus calls into repo code left unresolved."""
    out: list[tuple[Module, str, ast.AST]] = []
    unresolved: list[str] = []
    called: set[int] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            called.add(id(n.func))

    def add_class(mod: Module, cname: str) -> bool:
        if cname in mod.classes:
            for mname, mnode in mod.classes[cname].items():
                out.append((mod, f"{cname}.{mname}", mnode))
            return True
        return False

    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            name = n.id
            if name in m.defs and m.defs[name] is not fn:
                out.append((m, name, m.defs[name]))
            elif add_class(m, name):
                pass
            elif name in m.imports:
                mod, attr = m.imports[name]
                tm = idx.get(mod)
                if tm is None or attr is None:
                    continue
                if attr in tm.defs:
                    out.append((tm, attr, tm.defs[attr]))
                elif not add_class(tm, attr) and id(n) in called and tm.tree is not None:
                    unresolved.append(f"{mod}.{attr}")
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            base, attr = n.value.id, n.attr
            if base in m.imports:
                mod, a0 = m.imports[base]
                tm = idx.get(mod if a0 is None else mod)
                if tm is None:
                    continue
                if a0 is None:  # module alias
                    if attr in tm.defs:
                        out.append((tm, attr, tm.defs[attr]))
                    elif not add_class(tm, attr) and id(n) in called:
                        unresolved.append(f"{mod}.{attr}")
                else:  # imported name used as base (class or object)
                    if a0 in tm.classes and attr in tm.classes[a0]:
                        out.append((tm, f"{a0}.{attr}", tm.classes[a0][attr]))
            elif base in m.classes and attr in m.classes[base]:
                out.append((m, f"{base}.{attr}", m.classes[base][attr]))
    return out, unresolved


def trace(idx: Index, m: Module, fn: ast.AST, comp, depth: int) -> dict[str, Any]:
    sources: dict[str, str] = {}
    unlisted: dict[str, str] = {}
    unresolved: set[str] = set()
    depth_cut = False
    seen: set[tuple[str, int]] = set()
    q: deque = deque([(m, getattr(fn, "name", "?"), fn, 0, getattr(fn, "name", "?"))])
    visited_modules: set[str] = set()
    while q:
        mod, qn, node, d, chain = q.popleft()
        key = (mod.name + ":" + qn, 0)
        if key in seen:
            continue
        seen.add(key)
        text = ast.get_source_segment(mod.src, node) or ""
        if mod.name not in visited_modules and mod.name not in NO_CONST_SCAN:
            text += "\n" + mod.const_text
            visited_modules.add(mod.name)
        hit, unl = scan_text(text, comp, set())
        for s in hit:
            sources.setdefault(s, f"{chain} [{mod.name}]")
        for h in unl:
            unlisted.setdefault(h, f"{chain} [{mod.name}]")
        nxt, unres = edges(idx, mod, node)
        if d >= depth:
            if nxt:
                depth_cut = True
            continue
        unresolved.update(unres)
        for tm, tq, tn in nxt:
            q.append((tm, tq, tn, d + 1, f"{chain} -> {tq}"))
    return {"sources": sources, "unlisted_hosts": unlisted,
            "unresolved": sorted(unresolved), "depth_limited": depth_cut}


# ------------------------------ main ------------------------------

def audit(root: Path, depth: int = 2) -> dict[str, Any]:
    rows = data_rights.load()
    reg = {r["id"]: r for r in rows}
    comp = compile_sources(rows)
    idx = Index(root)
    files = sorted((root / "backend" / "routers").glob("*.py")) + [root / "backend" / "main.py"]
    public, excluded = [], []
    for f in files:
        m = idx.get(idx.modname(f))
        if m is None:
            continue
        for r in find_routes(m):
            fn = r.pop("node")
            if r["local_only"]:
                excluded.append({k: r[k] for k in ("method", "path", "module", "handler")})
                continue
            t = trace(idx, m, fn, comp, depth)
            srcs = sorted(t["sources"])
            flags = {s: reg[s]["public_display"] for s in srcs}
            partial = bool(t["unresolved"])
            bad = sorted(s for s, v in flags.items() if v != "yes")
            r.pop("local_only")
            public.append({**r, "sources": srcs,
                           "public_display": flags, "evidence": t["sources"],
                           "unlisted_hosts": sorted(t["unlisted_hosts"]),
                           "unlisted_evidence": t["unlisted_hosts"],
                           "trace": "partial" if partial else "traced",
                           "unresolved": t["unresolved"], "depth_limited": t["depth_limited"],
                           "blocking_sources": bad})
    no_routes = [p for p in public if any(v == "no" for v in p["public_display"].values())]
    flagged = [p for p in public if p["blocking_sources"] or p["unlisted_hosts"]]
    untraced = [p for p in public if p["trace"] == "partial"]
    return {
        "schema": "data_rights_audit/1",
        "depth": depth,
        "sources_total": len(rows),
        "sources_by_flag": data_rights.flag_counts(rows),
        "owner_confirm_ids": sorted(r["id"] for r in rows if r["owner_confirm"]),
        "public_routes": len(public),
        "excluded_local_only_routes": len(excluded),
        "routes_with_no_source_found": sum(1 for p in public if not p["sources"]),
        "routes": public,
        "flagged_routes": [{"route": f"{p['method']} {p['path']}", "handler": f"{p['module']}:{p['handler']}",
                            "blocking_sources": p["blocking_sources"],
                            "unlisted_hosts": p["unlisted_hosts"], "trace": p["trace"]} for p in flagged],
        "routes_on_a_no_source": [f"{p['method']} {p['path']}" for p in no_routes],
        "partial_trace_routes": [f"{p['method']} {p['path']}" for p in untraced],
        "control_plane_routes_served_publicly": [f"{p['method']} {p['path']}" for p in public
                                                 if p["path"].startswith("/api/control")],
        "depth_limited_routes": sum(1 for p in public if p["depth_limited"]),
        "excluded": excluded,
        "limits": __doc__.split("HONEST LIMITS")[1].strip(),
    }


def render_md(rep: dict[str, Any]) -> str:
    L = ["# Data-rights audit (report only)", "",
         f"sources: {rep['sources_total']}; public routes: {rep['public_routes']}; "
         f"local-only routes excluded: {rep['excluded_local_only_routes']}; depth {rep['depth']}", "",
         "## Sources by flag", "", "| flag | yes | no | UNVERIFIED |", "|---|---|---|---|"]
    for f, c in rep["sources_by_flag"].items():
        L.append(f"| {f} | {c['yes']} | {c['no']} | {c['UNVERIFIED']} |")
    L += ["", "## Public routes x sources", "", "| route | sources (public_display) | trace |", "|---|---|---|"]
    for p in rep["routes"]:
        s = ", ".join(f"{k}={v}" for k, v in p["public_display"].items()) or "-"
        u = f" UNLISTED:{','.join(p['unlisted_hosts'])}" if p["unlisted_hosts"] else ""
        L.append(f"| {p['method']} {p['path']} | {s}{u} | {p['trace']} |")
    L += ["", "## Public routes drawing on a no / UNVERIFIED / unlisted source", ""]
    for p in rep["flagged_routes"]:
        L.append(f"- {p['route']}: {', '.join(p['blocking_sources']) or '-'}"
                 f"{' ; unlisted ' + ','.join(p['unlisted_hosts']) if p['unlisted_hosts'] else ''}"
                 f" ({p['trace']})")
    L += ["", "## Could not trace (partial)", ""] + [f"- {r}" for r in rep["partial_trace_routes"]]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="directory for the receipt")
    ap.add_argument("--root", default=str(ROOT), help="repo checkout to audit")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any public route draws on a source flagged `no`")
    a = ap.parse_args(argv)
    rep = audit(Path(a.root), a.depth)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data_rights_audit.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    (out / "data_rights_audit.md").write_text(render_md(rep), encoding="utf-8")
    print(f"sources={rep['sources_total']} public_routes={rep['public_routes']} "
          f"excluded_local={rep['excluded_local_only_routes']} flagged={len(rep['flagged_routes'])} "
          f"on_no_source={len(rep['routes_on_a_no_source'])} partial={len(rep['partial_trace_routes'])} "
          f"depth_limited={rep['depth_limited_routes']}")
    print("by flag:", json.dumps(rep["sources_by_flag"]))
    for p in rep["flagged_routes"]:
        print(" FLAG", p["route"], p["blocking_sources"], p["unlisted_hosts"], p["trace"])
    if a.strict and rep["routes_on_a_no_source"]:
        print("STRICT: public routes on a `no` source:", rep["routes_on_a_no_source"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
