"""Dependencias entre módulos (Bloque 4): ciclos y capas que se saltan.

- **Grafo**: archivo A depende de B si una función de A llama a una de B (llamada exacta
  o probable), si una clase de A hereda o implementa una de B, o si tiene un atributo cuyo
  tipo es una clase de B. Las pruebas no cuentan.
- **Ciclos**: componentes fuertemente conexos (Tarjan) entre archivos y entre carpetas.
  De cada uno se muestra el camino cerrado más corto y la llamada que sostiene cada paso.
- **Capas que se saltan** (con las capas de `architecture.py`): Entrada que llama directo
  al acceso a datos (Repository, DAO…) cuando existe una capa de Lógica, o que usa la base
  de datos cuando hay acceso a datos. Los modelos (Active Record) no cuentan: usarlos desde
  un controlador es lo normal en Laravel o Django.

`desglosa check` falla cuando aparece un ciclo que no está en el archivo base.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from desglosa.architecture import LAYER_NAMES, analyze_architecture, is_test, words
from desglosa.scan import decode_bytes

BASE_FILE = ".desglosa-check.json"
DATA_ACCESS = frozenset({
    "repository", "repositories", "repo", "repos", "dao", "daos", "mapper", "store",
    "gateway", "repositorio", "repositorios", "persistence", "persistencia",
})


@dataclass(frozen=True)
class Step:
    """Un paso de una dependencia: por qué `src` depende de `dst`."""

    src: str
    dst: str
    why: str  # "FacturaController.store llama a FacturacionService.emitir"
    at: str  # "app/Http/Controllers/FacturaController.php:21"
    sid: str | None = None  # la función o clase que hace la llamada (el visor la abre)


@dataclass
class Cycle:
    level: str  # "carpeta" | "archivo"
    members: tuple[str, ...]  # todo el nudo (ordenado)
    path: tuple[str, ...]  # un camino cerrado concreto: a → b → … → a
    steps: list[Step]

    @property
    def key(self) -> str:
        return f"{self.level}:" + "|".join(self.members)


@dataclass
class Skip:
    src: str  # componente (clase o archivo)
    dst: str
    src_layer: str
    dst_layer: str
    skipped: str  # la capa que no se usa
    step: Step
    via: str | None = None  # el componente de esa capa que sí usa el destino
    ids: tuple[str, str] = ("", "")  # componentes de la arquitectura (origen, destino)

    @property
    def key(self) -> str:
        return f"capa:{self.src}->{self.dst}"


@dataclass
class DepReport:
    file_cycles: list[Cycle] = field(default_factory=list)
    folder_cycles: list[Cycle] = field(default_factory=list)
    skips: list[Skip] = field(default_factory=list)
    n_files: int = 0
    n_edges: int = 0

    @property
    def cycles(self) -> list[Cycle]:
        return self.folder_cycles + self.file_cycles


# --------------------------------------------------------------------------- grafo


def _excluded(path: str) -> bool:
    stem = posixpath.splitext(posixpath.basename(path))[0]
    return is_test(stem, path)


def file_edges(analysis) -> dict[tuple[str, str], Step]:
    """(archivo, archivo) → el primer motivo (determinista) de esa dependencia."""
    project = analysis.project
    by_id = {s.id: s for s in project.symbols}
    trusted = _Trust(analysis, by_id)
    # (rango, paso): se muestra primero una llamada a un método; crear el objeto o heredar
    # explica menos.
    found: dict[tuple[str, str], list[tuple[int, Step]]] = defaultdict(list)

    def add(a: str, b: str, why: str, at: str, rank: int, sid: str) -> None:
        if a != b and not _excluded(a) and not _excluded(b):
            found[(a, b)].append((rank, Step(a, b, why, at, sid)))

    for c in project.calls:
        if not trusted(c):
            continue
        caller, callee = by_id[c.caller_id], by_id[c.resolved_id]
        add(caller.file, callee.file, f"{caller.qualname} llama a {callee.qualname}",
            f"{caller.file}:{c.line}", _rank(callee), caller.id)
    from desglosa.uml import build_class_model

    classes, rels = build_class_model(analysis)
    verbs = {"hereda": "hereda de", "implementa": "implementa", "asociacion": "tiene un"}
    for r in rels:
        a, b = classes[r.src], classes[r.dst]
        detail = f" ({r.label})" if r.kind == "asociacion" and r.label else ""
        add(a.file, b.file, f"{a.name} {verbs[r.kind]} {b.name}{detail}", f"{a.file}:{a.line}",
            2, a.id)
    return {k: min(v, key=lambda rs: (rs[0], rs[1].at.rsplit(":", 1)[0], _line(rs[1].at),
                                      rs[1].why))[1]
            for k, v in sorted(found.items())}


_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


class _Trust:
    """¿Esta llamada sirve como dependencia? Exacta, sí. Probable: si va a una función
    suelta, o a un método cuya clase el archivo que llama nombra en algún lado (su tipo,
    un `new`, un import). Así no cuenta `match.groups()` adivinado por el nombre."""

    def __init__(self, analysis, by_id) -> None:
        self.root = Path(analysis.scan.root)
        self.by_id = by_id
        self.words: dict[str, frozenset[str]] = {}

    def names_in(self, path: str) -> frozenset[str]:
        """Los identificadores que aparecen en un archivo (se lee una sola vez)."""
        found = self.words.get(path)
        if found is None:
            try:
                text = decode_bytes((self.root / path).read_bytes())[0]
            except OSError:
                text = ""
            found = self.words[path] = frozenset(_IDENT_RE.findall(text))
        return found

    def __call__(self, c) -> bool:
        if not c.resolved_id or c.confidence not in ("exacta", "probable"):
            return False
        caller, callee = self.by_id.get(c.caller_id), self.by_id.get(c.resolved_id)
        if caller is None or callee is None:
            return False
        if c.confidence == "exacta" or caller.file == callee.file:
            return True
        owner = self.by_id.get(callee.parent_id) if callee.parent_id else None
        if owner is None or owner.kind not in ("class", "interface"):
            return True
        return owner.name in self.names_in(caller.file)


CONSTRUCTORS = frozenset({"__init__", "constructor", "__construct", "new", "init", "initialize"})


def _rank(callee) -> int:
    """0 = un método o función; 1 = crear un objeto (constructor o la clase misma)."""
    if callee.kind in ("function", "method") and callee.name not in CONSTRUCTORS:
        return 0
    return 1


def _line(at: str) -> int:
    tail = at.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def folder_edges(edges: dict[tuple[str, str], Step]) -> dict[tuple[str, str], Step]:
    out: dict[tuple[str, str], Step] = {}
    for (a, b), step in sorted(edges.items()):
        fa, fb = posixpath.dirname(a), posixpath.dirname(b)
        if fa != fb and (fa, fb) not in out:
            out[(fa, fb)] = step
    return out


def strongly_connected(nodes: list[str], adj: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan sin recursión (un proyecto grande pasa el límite de Python)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on_stack.add(v)
            children = adj.get(v, [])
            for j in range(i, len(children)):
                w = children[j]
                if w not in index:
                    work.append((v, j + 1))
                    work.append((w, 0))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    out.append(sorted(comp))
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
    return out


def _shortest_cycle(start: str, members: set[str], adj: dict[str, list[str]]) -> list[str]:
    """El camino cerrado más corto que sale de `start` y vuelve, dentro del nudo."""
    prev: dict[str, str] = {}
    queue = deque([start])
    seen = {start}
    while queue:
        v = queue.popleft()
        for w in adj.get(v, []):
            if w not in members:
                continue
            if w == start:
                path = [v]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return list(reversed(path)) + [start]
            if w not in seen:
                seen.add(w)
                prev[w] = v
                queue.append(w)
    return [start, start]


def find_cycles(edges: dict[tuple[str, str], Step], level: str) -> list[Cycle]:
    adj: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for a, b in sorted(edges):
        adj[a].append(b)
        nodes.update((a, b))
    cycles = []
    for comp in strongly_connected(sorted(nodes), adj):
        if len(comp) < 2:
            continue
        path = _shortest_cycle(comp[0], set(comp), adj)
        steps = [edges[(a, b)] for a, b in zip(path, path[1:], strict=False)]
        cycles.append(Cycle(level, tuple(comp), tuple(path), steps))
    return sorted(cycles, key=lambda c: (len(c.members), c.members))


# --------------------------------------------------------------------------- capas


def _data_access(name: str, path: str) -> bool:
    ws = words(name)
    if ws and (ws[-1] in DATA_ACCESS or (ws[0] in DATA_ACCESS)):
        return True
    return any(p.lower() in DATA_ACCESS for p in path.split("/")[:-1])


def skipped_layers(analysis) -> list[Skip]:
    routes = [(r.file, r.symbol_id) for r in analysis.routes if r.symbol_id]
    model = analyze_architecture(analysis.project, routes)
    comps = model.components
    by_id = {s.id: s for s in analysis.project.symbols}
    layers_present = {c.layer for c in comps.values() if c.layer and not c.is_test}
    access = {cid for cid, c in comps.items()
              if c.layer == "datos" and _data_access(c.name, c.file)}
    out: list[Skip] = []
    if "logica" in layers_present and access:
        # Solo llamadas exactas o probables: una ambigua no basta para acusar a nadie.
        evidence = _call_evidence(analysis, by_id)
        # Se salta la capa solo si existe el camino correcto: un servicio que ya usa ese
        # repositorio. Sin servicio (Petclinic), el controlador no se salta nada.
        served: dict[str, list[str]] = defaultdict(list)
        for (a, b) in evidence:
            ca = comps.get(a)
            if ca is not None and ca.layer == "logica" and not ca.is_test:
                served[b].append(ca.name)
        for (a, b), step in sorted(evidence.items()):
            ca, cb = comps.get(a), comps.get(b)
            if ca is None or cb is None or ca.is_test or cb.is_test:
                continue
            if ca.layer == "entrada" and b in access and served.get(b):
                out.append(Skip(ca.name, cb.name, "entrada", "datos", "logica", step,
                                via=sorted(served[b])[0], ids=(a, b)))
    # Entrada que lee o escribe una tabla que ya maneja un repositorio.
    owner: dict[str, str] = {}
    for cid in sorted(access):
        for ts in model.tables.get(cid, {}).values():
            for t in ts:
                owner.setdefault(t, comps[cid].name)
    for cid, modes in sorted(model.tables.items()):
        c = comps.get(cid)
        if c is None or c.layer != "entrada" or c.is_test:
            continue
        tables = sorted({t for ts in modes.values() for t in ts if t in owner})
        if tables:
            step = Step(c.file, c.file, f"{c.name} usa la tabla {tables[0]} con SQL propio",
                        c.file)
            out.append(Skip(c.name, "base de datos", "entrada", "bd", "datos", step,
                            via=owner[tables[0]], ids=(cid, "")))
    return out


def _call_evidence(analysis, by_id) -> dict[tuple[str, str], Step]:
    """(componente, componente) → la primera llamada entre ellos."""
    from desglosa.architecture import _component_index

    _, comp_of = _component_index(analysis.project)
    trusted = _Trust(analysis, by_id)
    best: dict[tuple[str, str], tuple] = {}
    for c in analysis.project.calls:
        if not trusted(c):
            continue
        a, b = comp_of.get(c.caller_id), comp_of.get(c.resolved_id)
        caller, callee = by_id.get(c.caller_id), by_id.get(c.resolved_id)
        if not (a and b and a != b and caller and callee):
            continue
        rank = (_rank(callee), caller.file, c.line, caller.qualname, callee.qualname)
        if (a, b) not in best or rank < best[(a, b)][0]:
            best[(a, b)] = (rank, Step(caller.file, callee.file,
                                       f"{caller.qualname} llama a {callee.qualname}",
                                       f"{caller.file}:{c.line}", caller.id))
    return {k: v[1] for k, v in sorted(best.items())}


# --------------------------------------------------------------------------- todo junto


def dependency_report(analysis) -> DepReport:
    edges = file_edges(analysis)
    files = {x for pair in edges for x in pair}
    return DepReport(
        file_cycles=find_cycles(edges, "archivo"),
        folder_cycles=find_cycles(folder_edges(edges), "carpeta"),
        skips=skipped_layers(analysis),
        n_files=len(files),
        n_edges=len(edges),
    )


def cycle_text(c: Cycle, arrow: str = "→") -> str:
    names = [p or "(raíz)" for p in c.path]
    return f" {arrow} ".join(names)


def skip_text(s: Skip, arrow: str = "→") -> str:
    layer = LAYER_NAMES[s.skipped]
    through = f"{s.via} ({layer})" if s.via else layer
    return (f"{s.src} ({LAYER_NAMES[s.src_layer]}) {arrow} {s.dst} "
            f"({LAYER_NAMES[s.dst_layer]}) sin pasar por {through}")


def load_base(path) -> set[str]:
    """Las claves aceptadas (`desglosa check --aceptar`), o vacío si no hay archivo."""
    import json

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(data.get("ciclos", [])) | set(data.get("capas", []))


def save_base(path, report: DepReport) -> None:
    import json

    data = {
        "version": 1,
        "nota": "Ciclos y capas saltadas aceptados; desglosa check solo falla con otros nuevos.",
        "ciclos": sorted(c.key for c in report.cycles),
        "capas": sorted(s.key for s in report.skips),
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")


def payload(report: DepReport, limit: int = 200) -> dict:
    """Lo que necesita el visor (pestaña «Dependencias»)."""
    def cyc(c: Cycle) -> dict:
        return {"nivel": c.level, "camino": list(c.path), "nudo": len(c.members),
                "pasos": [[s.why, s.at, s.sid] for s in c.steps]}

    return {
        "ciclos": [cyc(c) for c in report.cycles[:limit]],
        "n_ciclos": len(report.cycles),
        "capas": [[skip_text(s), s.step.why, s.step.at, s.step.sid, s.ids[0], s.ids[1]]
                  for s in report.skips[:limit]],
        "n_capas": len(report.skips),
        "archivos": report.n_files,
        "relaciones": report.n_edges,
    }
