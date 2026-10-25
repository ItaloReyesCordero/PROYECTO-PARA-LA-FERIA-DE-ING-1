"""Reporte en Markdown del análisis (SPEC RF-15, opción `analyze --report`).

Secciones: resumen, archivos por lenguaje, funciones más llamadas, funciones nunca
llamadas, ciclos de llamadas, archivos no parseados, complejidad más alta y, si hay SQL,
tablas. Sin fechas ni tiempos: dos ejecuciones dan el mismo archivo.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from desglosa import __version__
from desglosa.architecture import LAYER_NAMES, analyze_architecture
from desglosa.flows_stage import cyclomatic
from desglosa.galaxy import build_galaxy
from desglosa.ir import CONFIDENCES, Symbol, call_targets
from desglosa.pipeline import Analysis
from desglosa.services import BY_KEY

FUNC_KINDS = ("function", "method")
# Nombres que el lenguaje o el framework llaman solos: no cuentan como "nunca llamadas".
IMPLICIT_NAMES = frozenset(
    {"main", "__construct", "__init__", "constructor", "init", "initialize", "__invoke"}
)
SECTIONS = (
    "Resumen",
    "Archivos por lenguaje",
    "Funciones más llamadas",
    "Funciones nunca llamadas",
    "Ciclos de llamadas",
    "Archivos no parseados",
    "Complejidad más alta",
    "Notas en el código",
)
# Orden de las notas en el reporte: primero lo que avisa de un problema.
NOTE_ORDER = {"FIXME": 0, "BUG": 1, "HACK": 2, "XXX": 3, "TODO": 4, "WHY": 5, "NOTE": 6}
MAX_NOTES = 40


def _cell(text: str) -> str:
    """Texto seguro dentro de una celda de tabla Markdown."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(text: str) -> str:
    return "`" + _cell(text).replace("`", "'") + "`"


def _where(sym: Symbol) -> str:
    return _code(f"{sym.file}:{sym.line_start}")


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return out


def _architecture_section(analysis: Analysis, limit: int = 8) -> list[str]:
    """Capas reconocidas por nombre y carpeta, y servicios externos por sus imports."""
    routes = [(r.file, r.symbol_id) for r in analysis.routes if r.symbol_id]
    model = analyze_architecture(analysis.project, routes)
    by_layer: dict[str, list[str]] = defaultdict(list)
    for c in model.shown():
        by_layer[c.layer].append(c.name)
    used: dict[str, set[str]] = defaultdict(set)
    for cid, found in model.services.items():
        if cid in model.hidden or model.components[cid].layer is None:
            continue
        for key, pairs in found.items():
            used[key].update(path for path, _ in pairs)
    present = set(by_layer) | {BY_KEY[k].group for k in used} | ({"bd"} if model.tables else set())
    if len(present) < 2:
        return []
    out = ["## Arquitectura", ""]
    out.append(
        "Capas reconocidas por convenciones de nombre y carpeta (`…Controller`, "
        "`services/`, `models/`): es una convención, no una certeza."
    )
    out.append("")
    rows = []
    for key in ("entrada", "logica", "datos"):
        names = sorted(by_layer.get(key, []), key=str.lower)
        if names:
            extra = f" y {len(names) - limit} más" if len(names) > limit else ""
            rows.append((LAYER_NAMES[key], _cell(", ".join(names[:limit]) + extra)))
    if rows:
        out += _table(("Capa", "Componentes"), rows)
        out.append("")
    extra = []
    if model.unclassified:
        extra.append(f"sin capa reconocible: {len(model.unclassified)} componentes")
    if model.tests:
        extra.append(f"pruebas (no son una capa): {len(model.tests)}")
    if extra:
        out.append("No se muestran: " + "; ".join(extra) + ".")
        out.append("")
    if used:
        out.append("Bases de datos y servicios externos (por sus imports):")
        out.append("")
        rows = []
        for key in sorted(used, key=lambda k: (BY_KEY[k].group, BY_KEY[k].name)):
            files = sorted(used[key])
            extra = f" y {len(files) - 5} más" if len(files) > 5 else ""
            rows.append((BY_KEY[key].name, ", ".join(_code(f) for f in files[:5]) + extra))
        out += _table(("Servicio", "Archivos que lo importan"), rows)
        out.append("")
    return out


def _call_graph(
    analysis: Analysis,
) -> tuple[dict[str, set[str]], Counter, dict[str, set[str]], set[str]]:
    """Aristas función → función, llamadas por destino, quién llama a quién y qué
    funciones *quizá* se llaman (destinos de llamadas demasiado ambiguas)."""
    by_id = {s.id: s for s in analysis.project.symbols}
    edges: dict[str, set[str]] = defaultdict(set)
    sites: Counter = Counter()
    callers: dict[str, set[str]] = defaultdict(set)
    maybe: set[str] = set()
    for c in analysis.project.calls:
        caller = by_id.get(c.caller_id)
        if caller is None or caller.kind not in FUNC_KINDS:
            continue
        maybe.update(c.candidates)
        for t in call_targets(c):
            target = by_id.get(t)
            if target is None or target.kind not in FUNC_KINDS:
                continue
            edges[caller.id].add(target.id)
            sites[target.id] += 1
            callers[target.id].add(caller.id)
    return edges, sites, callers, maybe


def _cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Componentes fuertemente conexos (Tarjan iterativo) con ciclo real."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    nodes = sorted(set(edges) | {t for ts in edges.values() for t in ts})
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(edges.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(sorted(edges.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    comp.append(top)
                    if top == node:
                        break
                if len(comp) > 1 or node in edges.get(node, ()):
                    found.append(comp)
    return found


def build_report(analysis: Analysis, top: int = 10) -> str:
    project = analysis.project
    by_id = {s.id: s for s in project.symbols}
    funcs = sorted(
        (s for s in project.symbols if s.kind in FUNC_KINDS),
        key=lambda s: (s.file, s.line_start, s.qualname),
    )
    edges, sites, callers, maybe = _call_graph(analysis)
    out = [f"# Reporte de Desglosa: {project.root_name}", ""]
    out.append(
        f"Generado por Desglosa {__version__} con análisis estático: el código no se ejecutó."
    )
    out.append("")

    # ------------------------------------------------------------------ resumen
    analyzed = [f for f in project.files if f.skipped_reason is None]
    kinds = Counter(s.kind for s in project.symbols if s.kind != "module")
    conf = Counter(c.confidence for c in project.calls)
    out += ["## Resumen", ""]
    out.append(f"- Archivos analizados: {len(analyzed)} ({sum(f.lines for f in analyzed)} líneas)")
    out.append(
        f"- Funciones y métodos: {kinds.get('function', 0) + kinds.get('method', 0)}"
        f" · clases: {kinds.get('class', 0)} · interfaces: {kinds.get('interface', 0)}"
    )
    out.append(
        f"- Llamadas: {len(project.calls)} ("
        + ", ".join(f"{c} {conf.get(c, 0)}" for c in CONFIDENCES)
        + ")"
    )
    entries = [s for s in funcs if s.is_entry]
    if entries:
        out.append(f"- Puntos de entrada: {', '.join(_code(s.qualname) for s in entries)}")
    if analysis.routes:
        out.append(f"- Rutas: {len(analysis.routes)}")
    if project.tables:
        out.append(f"- Tablas SQL: {len(project.tables)} ({len(project.fks)} relaciones)")
    out.append("")

    # ------------------------------------------------------------------ por lenguaje
    out += ["## Archivos por lenguaje", ""]
    per_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in analyzed:
        per_lang[f.lang][0] += 1
        per_lang[f.lang][1] += f.lines
    funcs_per_lang = Counter(s.lang for s in funcs)
    rows = [
        (lang, str(n), str(lines), str(funcs_per_lang.get(lang, 0)))
        for lang, (n, lines) in sorted(per_lang.items())
    ]
    out += _table(("Lenguaje", "Archivos", "Líneas", "Funciones"), rows) if rows else ["Ninguno."]
    out.append("")

    # ------------------------------------------------------------------ más llamadas
    out += ["## Funciones más llamadas", ""]
    ranked = sorted(sites, key=lambda i: (-sites[i], by_id[i].file, by_id[i].line_start))[:top]
    if ranked:
        rows = [
            (_code(by_id[i].qualname), _where(by_id[i]), str(sites[i]), str(len(callers[i])))
            for i in ranked
        ]
        out += _table(("Función", "Dónde", "Llamadas", "Desde (funciones)"), rows)
    else:
        out.append("No hay llamadas entre funciones del proyecto.")
    out.append("")

    # ------------------------------------------------------------------ nunca llamadas
    out += ["## Funciones nunca llamadas", ""]
    # Un método abstracto o de interfaz es solo una declaración: se llama su implementación.
    declarations = {a for r in analysis.results for a in r.abstract}
    declarations |= {
        s.id
        for s in funcs
        if s.parent_id and by_id.get(s.parent_id) and by_id[s.parent_id].kind == "interface"
    }
    never = [
        s
        for s in funcs
        if not sites.get(s.id)
        and s.id not in maybe
        and s.id not in declarations
        and not s.is_entry
        and s.name not in IMPLICIT_NAMES
        and not (s.name.startswith("__") and s.name.endswith("__"))
    ]
    if never:
        out.append(
            "Nadie las llama desde el código analizado. Pueden usarse de forma dinámica "
            "(callbacks, frameworks, reflexión): revísalas antes de borrarlas."
        )
        out.append("")
        out += _table(("Función", "Dónde"), [(_code(s.qualname), _where(s)) for s in never])
    else:
        out.append("Todas las funciones tienen al menos una llamada.")
    out.append("")

    # ------------------------------------------------------------------ ciclos
    out += ["## Ciclos de llamadas", ""]
    cycles = _cycles(edges)
    if cycles:
        described = []
        for comp in cycles:
            members = sorted(comp, key=lambda i: (by_id[i].file, by_id[i].line_start))
            names = [by_id[i].qualname for i in members]
            if len(members) == 1:
                described.append(f"- Recursión directa: {_code(names[0])} se llama a sí misma.")
            else:
                described.append(
                    f"- Recursión entre {len(members)} funciones: "
                    + " ⇄ ".join(_code(n) for n in names)
                )
        out += sorted(described)
    else:
        out.append("No se encontraron ciclos.")
    out.append("")

    # ------------------------------------------------------------------ no parseados
    out += ["## Archivos no parseados", ""]
    rows = []
    for f in sorted(project.files, key=lambda f: f.path):
        if f.skipped_reason is not None:
            rows.append((_code(f.path), _cell(f"saltado: {f.skipped_reason}")))
        elif f.errors:
            noun = "error" if f.errors == 1 else "errores"
            rows.append((_code(f.path), f"{f.errors} {noun} de sintaxis (se analizó igual)"))
    out += _table(("Archivo", "Motivo"), rows) if rows else ["Todos se leyeron sin errores."]
    out.append("")

    # ------------------------------------------------------------------ complejidad
    out += ["## Complejidad más alta", ""]
    scored = []
    for s in funcs:
        flow = analysis.flows.get(s.id)
        if flow is not None and flow.graph.nodes:
            scored.append((cyclomatic(flow.graph), s, flow.graph.truncated))
    scored.sort(key=lambda t: (-t[0], t[1].file, t[1].line_start))
    if scored:
        out.append(
            "Complejidad ciclomática = decisiones + 1. Más de 10 suele indicar una función "
            "difícil de probar."
        )
        out.append("")
        rows = [
            (
                _code(s.qualname),
                _where(s),
                str(cc) + (" (colapsada)" if truncated else ""),
                str(s.line_end - s.line_start + 1),
            )
            for cc, s, truncated in scored[:top]
        ]
        out += _table(("Función", "Dónde", "Complejidad", "Líneas"), rows)
    else:
        out.append("No hay funciones con cuerpo.")
    out.append("")

    # ------------------------------------------------------------------ subsistemas
    galaxy = build_galaxy(project)
    if galaxy and galaxy["communities"]:
        nodes, comms = galaxy["nodes"], galaxy["communities"]
        out += ["## Subsistemas", ""]
        out.append(
            "Grupos de archivos que se llaman mucho entre sí (algoritmo de Louvain, sin IA); "
            "el nombre sale de sus carpetas."
        )
        out.append("")
        rows = [(_cell(label), str(size)) for _, label, size, *_ in comms[:15]]
        out += _table(("Subsistema", "Archivos"), rows)
        out.append("")
        out += ["## Archivos centrales", ""]
        out.append("Los archivos con más llamadas hacia y desde otros archivos: por ahí pasa todo.")
        out.append("")
        rows = [
            (_code(nodes[i][0]), str(nodes[i][6]), _cell(comms[nodes[i][4]][1]))
            for i in galaxy["gods"]
        ]
        out += _table(("Archivo", "Llamadas con otros archivos", "Subsistema"), rows)
        out.append("")
        between = {(a, b): w for a, b, w in galaxy["between"]}
        if between:
            out += ["## Conexiones entre subsistemas", ""]
            out.append("Dónde una parte del proyecto depende de otra (las más fuertes).")
            out.append("")
            rows = [
                (_cell(comms[a][1]), _cell(comms[b][1]), str(w))
                for (a, b), w in sorted(between.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
            ]
            out += _table(("Subsistema", "Subsistema", "Llamadas"), rows)
            out.append("")

    # ------------------------------------------------------------------ arquitectura
    out += _architecture_section(analysis)

    # ------------------------------------------------------------------ notas
    out += ["## Notas en el código", ""]
    if project.notes:
        tags = Counter(n.tag for n in project.notes)
        out.append(
            "Comentarios marcados por el equipo: "
            + ", ".join(f"{t} {tags[t]}" for t in sorted(tags, key=lambda t: NOTE_ORDER[t]))
            + "."
        )
        out.append("")
        ordered = sorted(project.notes, key=lambda n: (NOTE_ORDER[n.tag], n.file, n.line))
        rows = [
            (
                n.tag,
                _code(f"{n.file}:{n.line}"),
                _code(by_id[n.symbol_id].qualname) if n.symbol_id in by_id else "–",
                _cell(n.text) or "–",
            )
            for n in ordered[:MAX_NOTES]
        ]
        out += _table(("Etiqueta", "Dónde", "En", "Texto"), rows)
        if len(ordered) > MAX_NOTES:
            out.append(f"\n… y {len(ordered) - MAX_NOTES} más.")
    else:
        out.append("No hay comentarios TODO, FIXME, HACK, XXX, BUG, NOTE ni WHY.")
    out.append("")

    # ------------------------------------------------------------------ tablas
    if project.tables:
        out += ["## Tablas SQL", ""]
        users: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {"lee": set(), "escribe": set()}
        )
        for acc in project.table_access:
            sym = by_id.get(acc.symbol_id)
            if sym is not None:
                users[acc.table][acc.mode].add(sym.qualname)
        rows = []
        for t in sorted(project.tables, key=lambda t: t.name):
            reads = ", ".join(sorted(users[t.name]["lee"])) or "–"
            writes = ", ".join(sorted(users[t.name]["escribe"])) or "–"
            rows.append((_code(t.name), str(len(t.columns)), _cell(reads), _cell(writes)))
        out += _table(("Tabla", "Columnas", "Leída por (probable)", "Escrita por (probable)"), rows)
        out.append("")

    if project.warnings:
        out += ["## Avisos", ""]
        out += [f"- {_cell(w)}" for w in project.warnings[:30]]
        if len(project.warnings) > 30:
            out.append(f"- … y {len(project.warnings) - 30} más")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
