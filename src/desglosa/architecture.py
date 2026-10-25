"""Mapa de arquitectura (Bloque 3): capas y servicios externos, sin IA.

Columnas, de izquierda a derecha:

    Rutas → Entrada → Lógica → Datos → Base de datos → Servicios externos

- **Componentes**: cada clase de primer nivel y cada archivo con funciones sueltas.
- **Capa de un componente**: por convenciones de nombre y carpeta, en este orden: el
  nombre (`FacturaController`, `pago_service.py`, `RepositorioCliente`), la carpeta más
  cercana (`controllers/`, `services/`, `models/`) y, si tiene `main`, Entrada. Cada
  componente guarda el motivo para mostrarlo; los que no encajan no se dibujan (se
  cuentan). Es una convención, no una certeza: por eso se dice "por el nombre".
- **Base de datos y servicios externos**: salen de los imports (ver `services.py`) y de
  las tablas SQL que el código lee o escribe.
- Las llamadas entre componentes se agregan como en el mapa (una por flecha, confianza
  de la mayoría). Las de una misma capa no se dibujan.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field

from desglosa.ir import CONFIDENCES, Project, Symbol, call_targets
from desglosa.layout.layered import LEdge, LNode, layout_layered
from desglosa.layout.text import CHAR_W
from desglosa.macro import _backbone, _majority, _plural
from desglosa.services import BY_KEY, detect_services, services_by_file

LAYERS: tuple[tuple[str, str], ...] = (
    ("rutas", "Rutas"),
    ("entrada", "Entrada"),
    ("logica", "Lógica"),
    ("datos", "Datos"),
    ("bd", "Base de datos"),
    ("externo", "Servicios externos"),
)
LAYER_NAMES = dict(LAYERS)
LAYER_INDEX = {key: i for i, (key, _) in enumerate(LAYERS)}
MAX_PER_LAYER = 12  # más componentes en una columna van a "Otros (N)"
HEADER_H = 46.0  # espacio arriba para el título de cada columna
FUNC_KINDS = ("function", "method")

# Última palabra del nombre (inglés). "usecase" también se busca uniendo las dos últimas.
NAME_WORDS: dict[str, frozenset[str]] = {
    "entrada": frozenset({
        "controller", "controllers", "handler", "handlers", "endpoint", "endpoints",
        "router", "routes", "route", "view", "views", "viewset", "command", "commands",
        "middleware", "resolver", "servlet", "activity", "urls",
    }),
    "logica": frozenset({
        "service", "services", "usecase", "usecases", "interactor", "manager", "processor",
        "engine", "policy", "validator", "calculator", "workflow",
    }),
    "datos": frozenset({
        "repository", "repositories", "repo", "repos", "dao", "daos", "model", "models",
        "entity", "entities", "mapper", "store", "record", "dto", "migration", "migrations",
    }),
}
# En español la palabra suele ir primero (`ServicioPago`) o al final (`PagoServicio`).
NAME_WORDS_ES: dict[str, frozenset[str]] = {
    "entrada": frozenset({"controlador", "controladores", "vista", "vistas", "ruta", "rutas"}),
    "logica": frozenset({
        "servicio", "servicios", "gestor", "calculadora", "validador", "procesador",
        "logica", "negocio",
    }),
    "datos": frozenset({
        "repositorio", "repositorios", "modelo", "modelos", "entidad", "entidades", "datos",
    }),
}
FOLDER_WORDS: dict[str, frozenset[str]] = {
    "entrada": frozenset({
        "controllers", "controller", "handlers", "routes", "routers", "router", "views",
        "endpoints", "api", "http", "cli", "commands", "cmd", "console", "middleware",
        "controladores", "vistas", "rutas",
    }),
    "logica": frozenset({
        "services", "service", "usecases", "use_cases", "usecase", "domain", "application",
        "logic", "business", "managers", "servicios", "logica", "negocio", "dominio",
    }),
    "datos": frozenset({
        "repositories", "repository", "repos", "models", "model", "entities", "entity",
        "dao", "persistence", "database", "db", "data", "migrations", "datos", "modelos",
        "repositorios", "entidades",
    }),
}

_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def words(name: str) -> list[str]:
    """`MySqlFacturaRepository` → my, sql, factura, repository (en minúsculas)."""
    return [w.lower() for w in _WORD.findall(name)]


TEST_WORDS = frozenset({"test", "tests", "spec", "specs"})
TEST_FOLDERS = frozenset({"test", "tests", "__tests__", "spec", "specs"})


def is_test(name: str, path: str) -> bool:
    """Las pruebas no son una capa de la arquitectura: `FacturaTest`, `test_pago.py`,
    `pago.spec.ts` o cualquier cosa dentro de `tests/`."""
    ws = words(name)
    if ws and (ws[-1] in TEST_WORDS or ws[0] == "test"):
        return True
    return any(part.lower() in TEST_FOLDERS for part in path.split("/")[:-1])


def classify(name: str, path: str, is_entry: bool = False) -> tuple[str, str] | None:
    """(capa, motivo) de un componente, o None si no sigue ninguna convención conocida."""
    ws = words(name)
    if ws:
        last, last2 = ws[-1], "".join(ws[-2:])
        for layer in ("entrada", "logica", "datos"):
            for w in (last, last2):
                if w in NAME_WORDS[layer]:
                    return layer, f"el nombre termina en «{_original(name, w)}»"
            for w in (ws[0], last):
                if w in NAME_WORDS_ES[layer]:
                    return layer, f"el nombre incluye «{w}»"
    for folder in reversed(path.split("/")[:-1]):
        low = folder.lower()
        for layer in ("entrada", "logica", "datos"):
            if low in FOLDER_WORDS[layer]:
                return layer, f"está en la carpeta {folder}/"
    if is_entry:
        return "entrada", "tiene un punto de entrada (main)"
    return None


def _original(name: str, word: str) -> str:
    """La terminación tal como está escrita (`Controller`, `_service`)."""
    plain = re.sub(r"[^A-Za-z0-9]", "", name)
    if plain.lower().endswith(word):
        return plain[-len(word):]
    return word


# --------------------------------------------------------------------------- modelo


@dataclass
class Component:
    id: str
    name: str
    kind: str  # clase | interfaz | archivo
    file: str
    symbol_id: str | None
    n_funcs: int = 0
    is_entry: bool = False
    is_test: bool = False
    layer: str | None = None
    reason: str = ""


@dataclass
class ArchModel:
    components: dict[str, Component]
    calls: dict[tuple[str, str], dict[str, int]]  # (origen, destino) → {confianza: n}
    routes: dict[str, dict[str, int]]  # archivo de rutas → componente → n rutas
    tables: dict[str, dict[str, set[str]]]  # componente → modo (lee/escribe) → tablas
    services: dict[str, dict[str, list[tuple[str, str]]]]  # comp. → servicio → (archivo, import)
    n_tables: int = 0
    unclassified: list[str] = field(default_factory=list)
    hidden: set[str] = field(default_factory=set)  # con capa, pero no aportan (ver abajo)
    tests: list[str] = field(default_factory=list)  # pruebas: no son una capa

    def shown(self) -> list[Component]:
        """Componentes con capa que se muestran, ordenados por id."""
        return [
            c for cid, c in sorted(self.components.items())
            if c.layer is not None and cid not in self.hidden
        ]


def _component_index(project: Project) -> tuple[dict[str, Component], dict[str, str]]:
    """Componentes y, para cada símbolo, el componente al que pertenece."""
    by_id = {s.id: s for s in project.symbols}
    comps: dict[str, Component] = {}
    comp_of: dict[str, str] = {}

    def top_class(sym: Symbol) -> Symbol | None:
        found = None
        cur: Symbol | None = sym
        while cur is not None:
            if cur.kind in ("class", "interface"):
                found = cur
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        return found

    for sym in sorted(project.symbols, key=lambda s: (s.file, s.line_start, s.id)):
        cls = top_class(sym)
        if cls is not None:
            cid = cls.id
            if cid not in comps:
                kind = "interfaz" if cls.kind == "interface" else "clase"
                comps[cid] = Component(cid, cls.name, kind, cls.file, cls.id)
        else:
            cid = "f:" + sym.file
            if cid not in comps:
                comps[cid] = Component(cid, posixpath.basename(sym.file), "archivo", sym.file, None)
        comp_of[sym.id] = cid
        c = comps[cid]
        if sym.kind in FUNC_KINDS:
            c.n_funcs += 1
        if sym.is_entry:
            c.is_entry = True
    # Un archivo sin funciones sueltas (solo clases) no es componente: su módulo pasa a
    # la primera clase del archivo, para que las llamadas de nivel módulo no se pierdan.
    first_class: dict[str, str] = {}
    for cid, c in comps.items():
        if c.kind != "archivo":
            first_class.setdefault(c.file, cid)
    for sid, cid in list(comp_of.items()):
        c = comps[cid]
        if c.kind == "archivo" and c.n_funcs == 0 and c.file in first_class:
            comp_of[sid] = first_class[c.file]
            if c.is_entry:
                comps[first_class[c.file]].is_entry = True
    used = set(comp_of.values())
    comps = {cid: c for cid, c in comps.items() if cid in used}
    for c in comps.values():
        stem = posixpath.splitext(c.name)[0] if c.kind == "archivo" else c.name
        # `pago.spec.ts` → `pago.spec`: la última parte cuenta para saber si es prueba.
        if is_test(stem.replace(".", "_"), c.file):
            c.is_test = True
            continue
        found = classify(stem, c.file, c.is_entry)
        if found:
            c.layer, c.reason = found
    return comps, comp_of


def analyze_architecture(
    project: Project, routes: list[tuple[str, str]] | None = None
) -> ArchModel:
    comps, comp_of = _component_index(project)
    calls: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for c in project.calls:
        if c.confidence == "externa":
            continue
        a = comp_of.get(c.caller_id)
        if a is None:
            continue
        hits = {comp_of[t] for t in call_targets(c) if t in comp_of} - {a}
        for b in sorted(hits):
            mix = calls[(a, b)]
            mix[c.confidence] = mix.get(c.confidence, 0) + 1
    route_edges: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path, target in routes or []:
        b = comp_of.get(target)
        if b is not None:
            route_edges[path][b] += 1
    tables: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for acc in project.table_access:
        cid = comp_of.get(acc.symbol_id)
        if cid is not None:
            tables[cid][acc.mode].add(acc.table)
    by_file = services_by_file(detect_services(project))
    comps_in_file: dict[str, list[str]] = defaultdict(list)
    for cid in sorted(comps):
        comps_in_file[comps[cid].file].append(cid)
    services: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for path, found in by_file.items():
        for cid in comps_in_file.get(path, []):
            for key, mods in found.items():
                services[cid][key].extend((path, m) for m in mods)
    unclassified = sorted(cid for cid, c in comps.items() if c.layer is None and not c.is_test)
    tests = sorted(cid for cid, c in comps.items() if c.is_test)
    # No se muestran: el archivo de rutas (ya es la columna "Rutas") y las clases sin
    # métodos ni relaciones (p. ej. una base abstracta vacía).
    linked = {x for pair in calls for x in pair} | set(tables) | set(services)
    for targets in route_edges.values():
        linked.update(targets)
    hidden = {
        cid for cid, c in comps.items()
        if (c.kind == "archivo" and c.file in route_edges)
        or (c.n_funcs == 0 and cid not in linked)
    }
    return ArchModel(
        comps,
        dict(calls),
        {p: dict(v) for p, v in route_edges.items()},
        {k: dict(v) for k, v in tables.items()},
        {k: dict(v) for k, v in services.items()},
        n_tables=len(project.tables),
        unclassified=unclassified,
        hidden=hidden,
        tests=tests,
    )


# --------------------------------------------------------------------------- diagrama


@dataclass
class _Node:
    id: str
    layer: str
    kind: str  # tipo visual (colores del mapa): clase, interfaz, entrada, bd, externo, otros
    label: str
    sub: str
    link: str | None
    tip: str
    rank: str  # orden dentro de la columna


def _tip_files(pairs: list[tuple[str, str]], limit: int = 6) -> str:
    seen: list[str] = []
    for path, mod in pairs:
        item = f"{path} ({mod})"
        if item not in seen:
            seen.append(item)
    extra = len(seen) - limit
    text = "\n".join(seen[:limit])
    return text + (f"\n… y {extra} más" if extra > 0 else "")


def build_architecture(
    project: Project,
    routes: list[tuple[str, str]] | None = None,
    map_data: dict | None = None,
) -> dict | None:
    """Datos del mapa de arquitectura para el visor, o None si no se reconocen al menos
    dos capas (entre Entrada, Lógica, Datos, Base de datos y Servicios externos)."""
    model = analyze_architecture(project, routes)
    groups = (map_data or {}).get("groups", {})
    files_link = (map_data or {}).get("files", {})
    nodes: dict[str, _Node] = {}
    # (a, b) → [cantidad, {confianza: n}, tipo, modos]; tipo: llamadas | rutas | tablas |
    # servicio. La etiqueta se arma al final (ver `_edge_text`), después de agrupar.
    weights: dict[tuple[str, str], list] = {}

    def comp_link(c: Component) -> str | None:
        if c.symbol_id and c.symbol_id in groups:
            return f"#/mapa/{c.symbol_id}"
        el = files_link.get(c.file)
        return f"#/mapa/{el}" if el else None

    for c in model.shown():
        cid = c.id
        unit = "método" if c.kind != "archivo" else "función"
        units = "métodos" if c.kind != "archivo" else "funciones"
        kind = "entrada" if c.is_entry else ("interfaz" if c.kind == "interfaz" else "clase")
        tip = (
            f"{c.name}\nCapa: {LAYER_NAMES[c.layer]} ({c.reason})\n{c.file}\n"
            f"{_plural(c.n_funcs, unit, units)}"
        )
        nodes[cid] = _Node(cid, c.layer, kind, c.name, _plural(c.n_funcs, unit, units),
                           comp_link(c), tip, c.name.lower())
    for (a, b), mix in model.calls.items():
        if a in nodes and b in nodes:
            weights[(a, b)] = [sum(mix.values()), dict(mix), "llamadas", set()]
    for path, targets in model.routes.items():
        total = sum(targets.values())
        rid = "r:" + path
        el = files_link.get(path)
        nodes[rid] = _Node(rid, "rutas", "entrada", posixpath.basename(path),
                           _plural(total, "ruta", "rutas"), f"#/mapa/{el}" if el else None,
                           f"{path}\n{_plural(total, 'ruta', 'rutas')} hacia los controladores",
                           path)
        for b, n in targets.items():
            if b in nodes:
                weights[(rid, b)] = [n, {}, "rutas", set()]
    if model.tables:
        tid = "t:sql"
        n = model.n_tables
        nodes[tid] = _Node(tid, "bd", "bd", "Tablas SQL",
                           _plural(n, "tabla", "tablas") if n else "en cadenas SQL",
                           "#/er" if n else None,
                           "Tablas que el código lee o escribe con SQL en cadenas (probable)",
                           "0")
        for cid, modes in model.tables.items():
            if cid not in nodes:
                continue
            weights[(cid, tid)] = [1, {}, "tablas", {m for m in modes if modes[m]}]
    used_services: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cid, found in model.services.items():
        if cid not in nodes:
            continue
        for key, pairs in found.items():
            used_services[key].extend(pairs)
            weights[(cid, "s:" + key)] = [1, {}, "servicio", set()]
    for key, pairs in sorted(used_services.items()):
        svc = BY_KEY[key]
        n_files = len({p for p, _ in pairs})
        nodes["s:" + key] = _Node(
            "s:" + key, svc.group, "bd" if svc.group == "bd" else "externo", svc.name,
            "importado en " + _plural(n_files, "archivo", "archivos"), None,
            f"{svc.name}\nImportado en:\n{_tip_files(sorted(pairs))}", svc.name.lower(),
        )
    shown = {n.layer for n in nodes.values()} - {"rutas"}
    layer_of = {nid: n.layer for nid, n in nodes.items()}
    if len(shown) < 2 or not any(layer_of[a] != layer_of[b] for a, b in weights):
        return None  # una capa sola, o capas sin ninguna relación entre ellas
    nodes, weights = _limit(nodes, weights)
    # Igual que en el mapa: en un diagrama muy conectado, solo el esqueleto más fuerte.
    crossing = {k: v for k, v in weights.items() if nodes[k[0]].layer != nodes[k[1]].layer}
    kept = _backbone({k: [v[0], v[1], 0] for k, v in crossing.items()}, len(nodes))
    hidden_edges = len(crossing) - len(kept)
    same_layer = len(weights) - len(crossing)
    weights = {k: v for k, v in weights.items() if k in kept}

    # Columnas presentes, sin huecos.
    present = [key for key, _ in LAYERS if any(n.layer == key for n in nodes.values())]
    col = {key: i for i, key in enumerate(present)}
    lnodes, fixed = [], {}
    for nid in sorted(nodes, key=lambda i: (LAYER_INDEX[nodes[i].layer], nodes[i].rank, i)):
        n = nodes[nid]
        w = max(len(n.label), len(n.sub)) * CHAR_W + 32
        lnodes.append(LNode(nid, max(120.0, float(int(w + 1) // 2 * 2)), 52.0, n.rank))
        fixed[nid] = col[n.layer]
    ledges = [LEdge(a, b, _edge_text(w)[0]) for (a, b), w in sorted(weights.items())]
    lay = layout_layered(lnodes, ledges, fixed)
    out_nodes = []
    centers: dict[str, list[float]] = defaultdict(list)
    for nid in sorted(nodes, key=lambda i: (fixed[i], nodes[i].rank, i)):
        n, p = nodes[nid], lay.nodes[nid]
        out_nodes.append([nid, n.kind, p.x, p.y + HEADER_H, p.w, p.h, n.label, n.sub, n.link,
                          n.tip])
        centers[n.layer].append(p.x + p.w / 2)
    # Etiquetas encimadas: se dibuja la de la flecha más fuerte; la otra queda en el tooltip.
    placed: list[tuple[float, float, float, float]] = []
    drawn: set[tuple[str, str]] = set()
    for e in sorted(lay.edges, key=lambda e: (-weights[(e.src, e.dst)][0], e.src, e.dst)):
        if not e.label_box:
            continue
        x, y, bw, bh = e.label_box
        if all(x + bw <= px or px + pw <= x or y + bh <= py or py + ph <= y
               for px, py, pw, ph in placed):
            placed.append(e.label_box)
            drawn.add((e.src, e.dst))
    out_edges = []
    for e in lay.edges:
        flat: list[float] = []
        for x, y in e.points:
            flat.extend((x, y + HEADER_H))
        w = weights[(e.src, e.dst)]
        show = (e.src, e.dst) in drawn
        box = e.label_box if show else (0, 0, 0, 0)
        breakdown = {c: w[1][c] for c in CONFIDENCES if w[1].get(c)}
        back = fixed[e.src] > fixed[e.dst]
        # Campos: …, etiqueta dibujada (o None), caja, desglose, ¿hacia atrás?, texto completo.
        out_edges.append([
            e.src, e.dst, flat, _edge_text(w)[1], e.label if show else None, box[0],
            box[1] + HEADER_H if show else 0, box[2], box[3], breakdown, back, e.label,
        ])
    columns = []
    for key in present:
        n_in = sum(1 for n in nodes.values() if n.layer == key)
        columns.append([LAYER_NAMES[key], round(sum(centers[key]) / len(centers[key]), 1),
                        _plural(n_in, "elemento", "elementos")])
    kinds = {n[1] for n in out_nodes}
    confs = {e[3] for e in out_edges}
    order = ("entrada", "clase", "interfaz", "bd", "externo", "otros",
             "exacta", "probable", "ambigua")
    return {
        "w": lay.width,
        "h": lay.height + HEADER_H,
        "columns": columns,
        "nodes": out_nodes,
        "edges": out_edges,
        "legend": [k for k in order if k in kinds or k in confs],
        "unclassified": len(model.unclassified),
        "tests": len(model.tests),
        "same_layer": same_layer,
        "hidden": hidden_edges,  # relaciones débiles no dibujadas
    }


def _limit(nodes: dict[str, _Node], weights: dict[tuple[str, str], list]):
    """Más de MAX_PER_LAYER elementos en una columna: los más conectados quedan y el resto
    se junta en "Otros (N)" de esa columna, sumando sus flechas."""
    degree: dict[str, int] = defaultdict(int)
    for (a, b), (count, *_rest) in weights.items():
        degree[a] += count
        degree[b] += count
    merged: dict[str, str] = {}
    for layer, _ in LAYERS:
        members = [nid for nid, n in nodes.items() if n.layer == layer]
        if len(members) <= MAX_PER_LAYER:
            continue
        ranked = sorted(members, key=lambda i: (-degree[i], nodes[i].rank, i))
        rest = ranked[MAX_PER_LAYER - 1:]
        oid = "o:" + layer
        nodes[oid] = _Node(oid, layer, "otros", f"Otros ({len(rest)})",
                           "menos conectados", None,
                           "Agrupa: " + ", ".join(sorted(nodes[i].label for i in rest)[:20])
                           + ("…" if len(rest) > 20 else ""), "~")
        for nid in rest:
            merged[nid] = oid
            del nodes[nid]
    if not merged:
        return nodes, weights
    out: dict[tuple[str, str], list] = {}
    for (a, b), (count, mix, kind, modes) in sorted(weights.items()):
        a2, b2 = merged.get(a, a), merged.get(b, b)
        if a2 == b2:
            continue
        cur = out.get((a2, b2))
        if cur is None:
            out[(a2, b2)] = [count, dict(mix), kind, set(modes)]
            continue
        cur[0] += count
        for k, v in mix.items():
            cur[1][k] = cur[1].get(k, 0) + v
        cur[3] |= modes
        if cur[2] != kind:  # p. ej. llamadas y rutas hacia el mismo "Otros"
            cur[2] = "llamadas" if "llamadas" in (cur[2], kind) else cur[2]
    return nodes, out


def _edge_text(w: list) -> tuple[str | None, str]:
    """(etiqueta, confianza) de una flecha según su tipo."""
    count, mix, kind, modes = w
    if kind == "llamadas":
        return _plural(count, "llamada", "llamadas"), _majority(mix)
    if kind == "rutas":
        return _plural(count, "ruta", "rutas"), "exacta"
    if kind == "tablas":  # el enlace función → tabla es "probable" (SPEC §9)
        return " y ".join(m for m in ("lee", "escribe") if m in modes) or None, "probable"
    return None, "exacta"  # servicio: el import existe
