"""Datos que se incrustan en el HTML para el visor (todo determinista)."""

from __future__ import annotations

from collections import defaultdict

from desglosa import __version__
from desglosa.flows_stage import cyclomatic
from desglosa.ir import CONFIDENCE_RANK, Symbol
from desglosa.layout.er import layout_er
from desglosa.layout.sequence import layout_sequence
from desglosa.pipeline import Analysis
from desglosa.render.html import flow_payload
from desglosa.scan import decode_bytes
from desglosa.sequence import SequenceIndex, build_sequence, without_externals

FUNC_KINDS = ("function", "method")


def call_maps(analysis: Analysis) -> tuple[dict, dict]:
    """Llamadas resueltas entre funciones: entrantes y salientes, con la peor confianza."""
    by_id = {s.id: s for s in analysis.project.symbols}
    out: dict[str, dict[str, str]] = defaultdict(dict)
    inc: dict[str, dict[str, str]] = defaultdict(dict)
    for c in analysis.project.calls:
        if not c.resolved_id:
            continue
        caller = by_id.get(c.caller_id)
        target = by_id.get(c.resolved_id)
        if caller is None or target is None or target.kind not in FUNC_KINDS:
            continue
        if caller.kind not in FUNC_KINDS:
            continue
        for table, a, b in ((out, caller.id, target.id), (inc, target.id, caller.id)):
            prev = table[a].get(b)
            if prev is None or CONFIDENCE_RANK[c.confidence] > CONFIDENCE_RANK[prev]:
                table[a][b] = c.confidence
    return out, inc


def implementations(analysis: Analysis) -> dict[str, list[str]]:
    """Método abstracto o de interfaz → métodos de las clases que lo implementan."""
    symbols = analysis.project.symbols
    by_id = {s.id: s for s in symbols}
    abstract = {a for r in analysis.results for a in r.abstract}
    bases_by_class = {cid: names for r in analysis.results for cid, names in r.class_bases.items()}
    classes_by_name: dict[str, list[str]] = defaultdict(list)
    for s in symbols:
        if s.kind in ("class", "interface"):
            classes_by_name[s.name].append(s.id)
    children: dict[str, set[str]] = defaultdict(set)
    for cid, names in bases_by_class.items():
        for name in names:
            for base in classes_by_name.get(name, []):
                if base != cid:
                    children[base].add(cid)
    methods_by_class: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for s in symbols:
        if s.kind == "method" and s.parent_id:
            methods_by_class[s.parent_id][s.name].append(s.id)
    out: dict[str, list[str]] = {}
    for s in symbols:
        if s.kind != "method" or not s.parent_id:
            continue
        owner = by_id.get(s.parent_id)
        if owner is None or (s.id not in abstract and owner.kind != "interface"):
            continue
        found: list[str] = []
        stack = sorted(children.get(owner.id, []))
        seen: set[str] = set()
        while stack:
            cur = stack.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            found.extend(m for m in methods_by_class[cur].get(s.name, []) if m not in abstract)
            stack.extend(sorted(children.get(cur, [])))
        if found:
            out[s.id] = sorted(set(found), key=lambda i: (by_id[i].file, by_id[i].line_start))
    return out


def reachable(analysis: Analysis, start: str, limit: int = 60) -> list[str]:
    """Funciones alcanzables desde `start` haciendo clic en subprocesos."""
    order = [start]
    seen = {start}
    i = 0
    while i < len(order) and len(order) < limit:
        flow = analysis.flows.get(order[i])
        i += 1
        if flow is None:
            continue
        for n in flow.graph.nodes:
            t = n.target_symbol
            if t and t not in seen:
                seen.add(t)
                order.append(t)
    return order


def symbol_payload(sym: Symbol, metrics: dict) -> dict:
    return {
        "kind": sym.kind,
        "name": sym.name,
        "qualname": sym.qualname,
        "file": sym.file,
        "line_start": sym.line_start,
        "line_end": sym.line_end,
        "parent_id": sym.parent_id,
        "doc": sym.doc,
        "signature": sym.signature,
        "is_entry": sym.is_entry,
        "lang": sym.lang,
        "metrics": metrics,
    }


def build_payload(
    analysis: Analysis,
    *,
    include_source: bool = True,
    only: list[str] | None = None,
    start: str | None = None,
    map_data: dict | None = None,
    extra: dict | None = None,
    depth: int = 4,
) -> dict:
    project = analysis.project
    outgoing, incoming = call_maps(analysis)
    impl = implementations(analysis)
    wanted = set(only) if only is not None else None
    symbols: dict[str, dict] = {}
    for sym in project.symbols:
        if wanted is not None and sym.id not in wanted:
            continue
        flow = analysis.flows.get(sym.id)
        metrics = {
            "cc": cyclomatic(flow.graph) if flow is not None else None,
            "calls_in": len(incoming.get(sym.id, {})),
            "calls_out": len(outgoing.get(sym.id, {})),
        }
        symbols[sym.id] = symbol_payload(sym, metrics)
    # En modo parcial (comando flow) también se incluyen los destinos mencionados.
    if wanted is not None:
        by_id = {s.id: s for s in project.symbols}
        for sid in list(symbols):
            for ref in (
                list(outgoing.get(sid, {})) + list(incoming.get(sid, {})) + impl.get(sid, [])
            ):
                if ref not in symbols and ref in by_id:
                    symbols[ref] = symbol_payload(
                        by_id[ref], {"cc": None, "calls_in": 0, "calls_out": 0}
                    )
    flows = {
        sid: flow_payload(f.graph, f.layout)
        for sid, f in analysis.flows.items()
        if (wanted is None or sid in wanted) and f.graph.nodes
    }
    sources: dict[str, str] = {}
    if include_source:
        files_with_symbols = {s["file"] for s in symbols.values() if s["kind"] != "module"}
        for path in sorted(files_with_symbols):
            data = (analysis.scan.root / path).read_bytes()
            sources[path] = decode_bytes(data)[0]
    files = {
        f.path: {"lang": f.lang, "lines": f.lines, "errors": f.errors, "skipped": f.skipped_reason}
        for f in project.files
    }

    def table(m: dict[str, dict[str, str]]) -> dict[str, list]:
        return {
            k: [[t, conf] for t, conf in sorted(v.items(), key=lambda kv: kv[0])]
            for k, v in sorted(m.items())
            if k in symbols
        }

    routes = {r.symbol_id: f"{r.verb} {r.path}" for r in analysis.routes if r.symbol_id}
    tables_of: dict[str, list[list[str]]] = defaultdict(list)
    for acc in project.table_access:
        if acc.symbol_id in symbols:
            tables_of[acc.symbol_id].append([acc.table, acc.mode])
    payload = {
        "meta": {
            "name": project.root_name,
            "version": __version__,
            "start": start or "#/mapa",
            "generator": "Desglosa",
        },
        "symbols": symbols,
        "files": files,
        "flows": flows,
        "calls_out": table(outgoing),
        "calls_in": table(incoming),
        "impl": {k: v for k, v in sorted(impl.items()) if k in symbols},
        "sources": sources,
        "map": map_data,
        "routes": {k: v for k, v in sorted(routes.items()) if k in symbols},
        "tables_of": dict(sorted(tables_of.items())),
        "sequence": sequence_payload(analysis, symbols, routes, depth),
        "er": er_payload(analysis),
    }
    if extra:
        payload.update(extra)
    return payload


def _sequence_layout(layout) -> dict:
    return {
        "w": layout.width,
        "h": layout.height,
        "participants": [list(p) for p in layout.participants],
        "lifelines": [list(x) for x in layout.lifelines],
        "messages": [list(m) for m in layout.messages],
        "fragments": [list(f) for f in layout.fragments],
        "confs": list(layout.confidences),
    }


def sequence_payload(
    analysis: Analysis, symbols: dict, routes: dict[str, str], depth: int = 4
) -> dict:
    """Diagrama de secuencia de cada función que llama a otras del proyecto."""
    project = analysis.project
    by_id = {s.id: s for s in project.symbols}
    callers: set[str] = set()
    for c in project.calls:
        target = by_id.get(c.resolved_id) if c.resolved_id else None
        if (target is not None and target.kind in FUNC_KINDS) or c.candidates:
            callers.add(c.caller_id)
    flows = {k: v.graph for k, v in analysis.flows.items()}
    new_calls = analysis.new_calls
    index = SequenceIndex.of(project)
    out: dict[str, dict] = {}
    for sid in sorted(callers):
        sym = by_id.get(sid)
        if sym is None or sym.kind not in FUNC_KINDS or sid not in symbols:
            continue
        diagram = build_sequence(
            project, flows, sid, depth=depth, routes=routes, new_calls=new_calls, index=index
        )
        entry = {"layout": _sequence_layout(layout_sequence(without_externals(diagram)))}
        if any(m.external for m in diagram.messages):
            entry["layout_all"] = _sequence_layout(layout_sequence(diagram))
        out[sid] = entry
    return out


def er_payload(analysis: Analysis) -> dict | None:
    project = analysis.project
    if not project.tables:
        return None
    readers: dict[str, dict[str, list[str]]] = {}
    for acc in project.table_access:
        readers.setdefault(acc.table, {"lee": [], "escribe": []})[acc.mode].append(acc.symbol_id)
    tables = [
        {
            "id": t.id,
            "name": t.name,
            "file": t.file,
            "line": t.line,
            "access": readers.get(t.name, {"lee": [], "escribe": []}),
        }
        for t in project.tables
    ]
    fks = [
        {
            "table": fk.table,
            "columns": list(fk.columns),
            "ref_table": fk.ref_table,
            "ref_columns": list(fk.ref_columns),
            "form": fk.form,
            "file": fk.file,
            "line": fk.line,
        }
        for fk in project.fks
    ]
    return {
        "tables": tables,
        "fks": fks,
        "layout": layout_er(list(project.tables), list(project.fks)),
    }
