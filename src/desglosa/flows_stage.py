"""Etapa de diagramas de flujo: vuelve a parsear cada archivo y construye un flujo por función.

Se ejecuta después de `resolve`, porque el diagrama necesita saber qué llamadas son del
proyecto (subproceso clicable) y cuáles no. Las funciones de trabajo son de nivel módulo
para poder ejecutarse en otros procesos (Windows usa `spawn`).
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from desglosa import grammars, langs
from desglosa.flow import CallInfo, SSeq, build_flow
from desglosa.ir import Call, FlowGraph, Symbol
from desglosa.langs.spec import Src
from desglosa.layout.flow import FlowLayout, layout_flow
from desglosa.scan import decode_bytes, grammar_for


@dataclass(frozen=True)
class FlowTask:
    root: str
    path: str
    lang: str
    symbols: tuple[Symbol, ...]  # funciones/métodos de este archivo
    calls: tuple[tuple[str, CallInfo], ...]
    max_nodes: int = 120
    max_height: float = 1600


@dataclass
class FlowOutput:
    graph: FlowGraph
    layout: FlowLayout
    warnings: list[str] = field(default_factory=list)
    struct: SSeq | None = None


def _function_nodes(root: Node, types: set[str]) -> dict[tuple[int, int], list[Node]]:
    found: dict[tuple[int, int], list[Node]] = {}
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type in types:
            found.setdefault((n.start_point[0] + 1, n.end_point[0] + 1), []).append(n)
        stack.extend(n.named_children)
    return found


def build_file_flows(task: FlowTask) -> list[FlowOutput]:
    """Función de trabajo (nivel módulo): flujos + layouts de un archivo."""
    registry = langs.get(task.lang)
    if registry is None or not task.symbols:
        return []
    spec, hooks = registry
    data = (Path(task.root) / task.path).read_bytes()
    _, encoding = decode_bytes(data)
    tree = grammars.get_parser(grammar_for(task.path, task.lang)).parse(data)
    src = Src(data, encoding)
    nodes = _function_nodes(tree.root_node, set(spec.function_nodes) | set(spec.method_nodes))
    calls = dict(task.calls)
    out: list[FlowOutput] = []
    for sym in task.symbols:
        candidates = nodes.get((sym.line_start, sym.line_end), [])
        func = next((n for n in candidates if hooks.symbol_name(n, src) == sym.name), None)
        if func is None or hooks.function_body(func) is None:
            continue
        try:
            result = build_flow(spec, hooks, src, task.path, sym, func, calls, task.max_nodes)
            layout = layout_flow(result.graph, result.struct, task.max_height)
        except RecursionError:
            out_warn = (
                f"{task.path}:{sym.line_start}: {sym.qualname} demasiado anidada para dibujar"
            )
            out.append(
                FlowOutput(FlowGraph(sym.id, (), (), True), _empty_layout(sym.id), [out_warn])
            )
            continue
        out.append(FlowOutput(result.graph, layout, result.warnings, result.struct))
    return out


def _empty_layout(symbol_id: str) -> FlowLayout:
    return FlowLayout(symbol_id, 0, 0, (), (), (), (), 1)


def make_tasks(
    root: str,
    symbols: list[Symbol],
    calls: list[Call],
    max_nodes: int,
    max_height: float,
) -> list[FlowTask]:
    by_id = {s.id: s for s in symbols}
    funcs_by_file: dict[str, list[Symbol]] = defaultdict(list)
    for s in symbols:
        if s.kind in ("function", "method"):
            funcs_by_file[s.file].append(s)
    calls_by_file: dict[str, list[tuple[str, CallInfo]]] = defaultdict(list)
    for c in calls:
        caller = by_id.get(c.caller_id)
        if caller is None:
            continue
        target = None
        if (
            c.resolved_id
            and by_id.get(c.resolved_id)
            and by_id[c.resolved_id].kind
            in (
                "function",
                "method",
            )
        ):
            target = c.resolved_id
        calls_by_file[caller.file].append(
            (c.id, CallInfo(c.callee_text, c.confidence, c.io_kind, target))
        )
    tasks = []
    for path in sorted(funcs_by_file):
        syms = funcs_by_file[path]
        tasks.append(
            FlowTask(
                root,
                path,
                syms[0].lang,
                tuple(syms),
                tuple(sorted(calls_by_file.get(path, []), key=lambda kv: kv[0])),
                max_nodes,
                max_height,
            )
        )
    return tasks


def run_tasks(tasks: list[FlowTask], jobs: int) -> list[FlowOutput]:
    if jobs <= 1 or len(tasks) < 2:
        groups = [build_file_flows(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            groups = list(
                pool.map(build_file_flows, tasks, chunksize=max(1, len(tasks) // (jobs * 4)))
            )
    return [o for g in groups for o in g]


def cyclomatic(graph: FlowGraph) -> int:
    """Complejidad ciclomática = decisiones + 1 (un switch de n casos aporta n-1)."""
    kinds = {n.id: n.kind for n in graph.nodes}
    out_degree: dict[str, int] = defaultdict(int)
    for e in graph.edges:
        if kinds.get(e.src) == "decision":
            out_degree[e.src] += 1
    return 1 + sum(max(0, d - 1) for d in out_degree.values())
