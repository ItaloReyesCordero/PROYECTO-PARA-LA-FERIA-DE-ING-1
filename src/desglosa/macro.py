"""Mapa por niveles: Proyecto → carpeta → archivo o clase → función (SPEC §6.4).

- Las cadenas de carpetas con un solo hijo se colapsan (`app/Http/Controllers`).
- Un archivo que solo contiene una clase se muestra directamente como esa clase.
- Las llamadas resueltas se agregan por nivel: en cada grupo se dibuja una arista entre
  los dos hijos que contienen a quien llama y a quien es llamado, con el número de
  llamadas, la confianza de la mayoría y el desglose. Las externas no se dibujan.
- Si un grupo tiene más de 15 hijos se muestran los más conectados y el resto va a
  grupos "Otros" que se pueden abrir (alfabéticos si son muchos).
- En un nivel muy denso se dibuja el esqueleto de relaciones más fuertes.
"""

from __future__ import annotations

import hashlib
import posixpath
from collections import defaultdict
from dataclasses import dataclass, field

from desglosa.ir import CONFIDENCE_RANK, CONFIDENCES, Project, Symbol, call_targets
from desglosa.layout.layered import LEdge, LNode, layout_layered
from desglosa.layout.text import CHAR_W

MAX_CHILDREN = 15
FUNC_KINDS = ("function", "method")
MAP_LEGEND_ORDER = (
    "modulo",
    "clase",
    "interfaz",
    "funcion",
    "entrada",
    "otros",
    "exacta",
    "probable",
    "ambigua",
)


@dataclass
class Group:
    id: str
    name: str
    kind: str  # proyecto | modulo | archivo | clase | interfaz | otros
    parent: str | None
    children: list[str] = field(default_factory=list)
    symbol_id: str | None = None
    path: str | None = None


def _hid(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"


class MapBuilder:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.symbols = {s.id: s for s in project.symbols}
        self.groups: dict[str, Group] = {}
        self.owner: dict[str, str] = {}  # elemento del mapa → grupo que lo contiene
        self.element_of: dict[str, str] = {}  # símbolo → elemento visible que lo representa
        self.file_element: dict[str, str] = {}  # archivo → elemento (archivo o clase)
        self.children_of: dict[str, list[Symbol]] = defaultdict(list)
        self.modules: dict[str, Symbol] = {}
        for s in project.symbols:
            if s.parent_id:
                self.children_of[s.parent_id].append(s)
            if s.kind == "module":
                self.modules[s.file] = s

    # ------------------------------------------------------------------ árbol

    def build_tree(self) -> None:
        root = Group("root", self.project.root_name, "proyecto", None)
        self.groups["root"] = root
        files = sorted(
            f.path for f in self.project.files if f.skipped_reason is None and f.lang != "sql"
        )
        # Árbol de carpetas.
        dir_children: dict[str, list[str]] = defaultdict(list)  # carpeta → hijos (rutas)
        for path in files:
            parts = path.split("/")
            for i in range(len(parts)):
                parent = "/".join(parts[:i])
                child = "/".join(parts[: i + 1])
                if child not in dir_children[parent]:
                    dir_children[parent].append(child)
        file_set = set(files)

        def add_dir(path: str, parent_gid: str, name: str) -> None:
            # Colapsar cadenas de carpetas con un solo hijo carpeta.
            while len(dir_children[path]) == 1 and dir_children[path][0] not in file_set:
                nxt = dir_children[path][0]
                name = f"{name}/{posixpath.basename(nxt)}"
                path = nxt
            gid = _hid("dir", path)
            self.groups[gid] = Group(gid, name, "modulo", parent_gid, path=path)
            self.groups[parent_gid].children.append(gid)
            self.owner[gid] = parent_gid
            self._fill_dir(path, gid, dir_children, file_set, add_dir)

        # La raíz salta carpetas únicas (p. ej. un solo `src/`).
        start = ""
        while len(dir_children[start]) == 1 and dir_children[start][0] not in file_set:
            start = dir_children[start][0]
        self._fill_dir(start, "root", dir_children, file_set, add_dir)

    def _fill_dir(self, path, gid, dir_children, file_set, add_dir) -> None:
        for child in sorted(dir_children[path], key=lambda c: (c in file_set, c.lower())):
            if child in file_set:
                self._add_file(child, gid)
            else:
                add_dir(child, gid, posixpath.basename(child))

    def _module_symbol(self, path: str) -> Symbol | None:
        return self.modules.get(path)

    def _add_file(self, path: str, parent_gid: str) -> None:
        module = self._module_symbol(path)
        top = [
            s
            for s in (self.children_of.get(module.id, []) if module else [])
            if s.kind in ("class", "interface", "function", "method")
        ]
        top.sort(key=lambda s: (s.line_start, s.qualname))
        classes = [s for s in top if s.kind in ("class", "interface")]
        if len(top) == 1 and classes:
            element = self._add_class(classes[0], parent_gid, file_hint=posixpath.basename(path))
            self.file_element[path] = element
            if module:
                self.element_of[module.id] = element
            return
        gid = _hid("file", path)
        self.groups[gid] = Group(gid, posixpath.basename(path), "archivo", parent_gid, path=path)
        self.groups[parent_gid].children.append(gid)
        self.owner[gid] = parent_gid
        self.file_element[path] = gid
        if module:
            self.element_of[module.id] = gid
        for s in top:
            if s.kind in ("class", "interface"):
                self._add_class(s, gid)
            else:
                self._add_function(s, gid)

    def _add_class(self, cls: Symbol, parent_gid: str, file_hint: str | None = None) -> str:
        kind = "interfaz" if cls.kind == "interface" else "clase"
        g = Group(cls.id, cls.name, kind, parent_gid, symbol_id=cls.id, path=file_hint)
        self.groups[cls.id] = g
        self.groups[parent_gid].children.append(cls.id)
        self.owner[cls.id] = parent_gid
        self.element_of[cls.id] = cls.id
        members = sorted(self.children_of.get(cls.id, []), key=lambda s: (s.line_start, s.qualname))
        for m in members:
            if m.kind in ("class", "interface"):
                self._add_class(m, cls.id)
            elif m.kind in FUNC_KINDS:
                self._add_function(m, cls.id)
        return cls.id

    def _add_function(self, fn: Symbol, parent_gid: str) -> None:
        self.groups[parent_gid].children.append(fn.id)
        self.owner[fn.id] = parent_gid
        self.element_of[fn.id] = fn.id
        # Funciones anidadas: se representan con la función que las contiene.
        stack = list(self.children_of.get(fn.id, []))
        while stack:
            inner = stack.pop()
            self.element_of.setdefault(inner.id, fn.id)
            stack.extend(self.children_of.get(inner.id, []))

    # ------------------------------------------------------------------ aristas

    def _element(self, sid: str) -> str | None:
        el = self.element_of.get(sid)
        if el is not None:
            return el
        sym = self.symbols.get(sid)
        if sym is None:
            return None
        return self.file_element.get(sym.file)

    def _path(self, element: str) -> list[str]:
        chain = [element]
        cur = self.owner.get(element)
        while cur is not None:
            chain.append(cur)
            cur = self.owner.get(cur)
        chain.reverse()
        return chain

    def aggregate(
        self, routes: list[tuple[str, str]] | None = None
    ) -> dict[str, dict[tuple[str, str], list]]:
        """Grupo → (hijo origen, hijo destino) → [llamadas, {confianza: n}, rutas].

        `routes` son pares (archivo de rutas, método destino): se dibujan como "N rutas".
        La flecha se dibuja con la confianza de la mayoría (ver `_majority`).
        """
        edges: dict[str, dict[tuple[str, str], list]] = defaultdict(dict)
        # Cada enlace: (origen, destinos posibles, confianza, ¿es ruta?).
        links: list[tuple[str | None, tuple[str, ...], str, int]] = []
        for c in self.project.calls:
            if c.confidence == "externa":
                continue
            # Una llamada con muchos destinos posibles no dice a cuál va: no se dibuja.
            targets = call_targets(c)
            if targets:
                links.append((self._element(c.caller_id), targets, c.confidence, 0))
        for path, target in routes or []:
            links.append((self.file_element.get(path), (target,), "exacta", 1))
        paths: dict[str, list[str]] = {}  # el camino de cada elemento se repite mucho

        def path_of(el: str) -> list[str]:
            p = paths.get(el)
            if p is None:
                p = paths[el] = self._path(el)
            return p

        for a, targets, conf, is_route in links:
            if a is None:
                continue
            # Una llamada cuenta UNA vez por flecha, aunque varias candidatas caigan en el
            # mismo destino (p. ej. dos clases de la misma carpeta).
            hits: set[tuple[str, tuple[str, str]]] = set()
            for t in targets:
                b = self._element(t)
                if b is None or a == b:
                    continue
                pa, pb = path_of(a), path_of(b)
                i = 0
                while i < min(len(pa), len(pb)) and pa[i] == pb[i]:
                    i += 1
                if i == 0 or i >= len(pa) or i >= len(pb):
                    continue
                hits.add((pa[i - 1], (pa[i], pb[i])))
            for group, key in sorted(hits):
                cur = edges[group].get(key)
                if cur is None:
                    cur = edges[group][key] = [0, {}, 0]
                if is_route:
                    cur[2] += 1
                else:
                    cur[0] += 1
                    cur[1][conf] = cur[1].get(conf, 0) + 1
        return edges

    # ------------------------------------------------------------------ "Otros (N)"

    def limit_children(self, edges: dict[str, dict[tuple[str, str], list]]) -> None:
        for gid in sorted(self.groups):
            self._limit(gid, edges)

    def _limit(self, gid: str, edges) -> None:
        """Más de MAX_CHILDREN hijos: los más conectados quedan a la vista y el resto se
        agrupa en "Otros".

        - Si lo que sobra cabe en un grupo: un solo "Otros (N)".
        - Si no: quedan los MAX_CHILDREN // 2 más conectados y el resto se reparte en
          grupos alfabéticos parejos ("Otros: admin… – auth… (27)"), que a su vez se
          parten igual. Así 220 carpetas quedan a 2–3 clics, no en una cadena de 14
          "Otros" dentro de "Otros".
        """
        g = self.groups[gid]
        if len(g.children) <= MAX_CHILDREN:
            return
        degree: dict[str, int] = defaultdict(int)
        for (a, b), (count, _, n_routes) in edges.get(gid, {}).items():
            degree[a] += count + n_routes
            degree[b] += count + n_routes
        ranked = sorted(g.children, key=lambda c: (-degree[c], self._name(c).lower(), c))
        if len(g.children) - (MAX_CHILDREN - 1) <= MAX_CHILDREN:
            keep = set(ranked[: MAX_CHILDREN - 1])
            rest = [c for c in g.children if c not in keep]
            buckets = [rest]
        else:
            n_keep = MAX_CHILDREN // 2
            keep = set(ranked[:n_keep])
            rest = sorted(
                (c for c in g.children if c not in keep),
                key=lambda c: (self._name(c).lower(), c),
            )
            n_buckets = MAX_CHILDREN - n_keep
            size, extra = divmod(len(rest), n_buckets)
            buckets, start = [], 0
            for i in range(n_buckets):
                end = start + size + (1 if i < extra else 0)
                buckets.append(rest[start:end])
                start = end
        container: dict[str, str] = {}
        new_ids: list[str] = []
        for i, members in enumerate(buckets):
            oid = f"{gid}-otros" if len(buckets) == 1 else f"{gid}-otros{i}"
            if len(buckets) == 1:
                name = f"Otros ({len(members)})"
            else:
                first, last = self._name(members[0]), self._name(members[-1])
                name = f"Otros: {_short(first)} – {_short(last)} ({len(members)})"
            self.groups[oid] = Group(oid, name, "otros", gid, children=list(members))
            self.owner[oid] = gid
            new_ids.append(oid)
            for c in members:
                container[c] = oid
                self.owner[c] = oid
                if c in self.groups:
                    self.groups[c].parent = oid
        g.children = [c for c in g.children if c in keep] + new_ids
        # Repartir las aristas: entre elementos de un mismo grupo quedan dentro de él;
        # el resto sube al padre, sumando las llamadas de cada confianza.
        parent_edges: dict[tuple[str, str], list] = {}
        inner: dict[str, dict[tuple[str, str], list]] = {oid: {} for oid in new_ids}
        for (a, b), (count, confs, n_routes) in edges.get(gid, {}).items():
            ca, cb = container.get(a, a), container.get(b, b)
            if ca == cb and ca in inner:
                target, key = inner[ca], (a, b)
            else:
                target, key = parent_edges, (ca, cb)
            cur = target.get(key)
            if cur is None:
                target[key] = [count, dict(confs), n_routes]
            else:
                cur[0] += count
                cur[2] += n_routes
                for conf, n in confs.items():
                    cur[1][conf] = cur[1].get(conf, 0) + n
        edges[gid] = parent_edges
        for oid in new_ids:
            edges[oid] = inner[oid]
            self._limit(oid, edges)

    # ------------------------------------------------------------------ salida

    def _name(self, element: str) -> str:
        if element in self.groups:
            return self.groups[element].name
        sym = self.symbols.get(element)
        return sym.name if sym else element

    def _count_functions(self, gid: str) -> int:
        total = 0
        for c in self.groups[gid].children:
            if c in self.groups:
                total += self._count_functions(c)
            else:
                total += 1
        return total

    def _describe(self, element: str) -> tuple[str, str, str, str | None]:
        """(tipo visual, etiqueta, subtítulo, enlace)."""
        if element in self.groups:
            g = self.groups[element]
            n = self._count_functions(element)
            if g.kind == "modulo":
                return "modulo", g.name + "/", _plural(n, "función", "funciones"), f"#/mapa/{g.id}"
            if g.kind == "archivo":
                return "clase", g.name, _plural(n, "función", "funciones"), f"#/mapa/{g.id}"
            if g.kind == "otros":
                return "otros", g.name, "clic para abrir", f"#/mapa/{g.id}"
            sym = self.symbols.get(g.symbol_id or "")
            kind = "interfaz" if g.kind == "interfaz" else "clase"
            if sym is not None and sym.is_entry:
                kind = "entrada"
            sub = _plural(n, "método", "métodos")
            return kind, g.name, sub, f"#/mapa/{g.id}"
        sym = self.symbols[element]
        kind = "entrada" if sym.is_entry else "funcion"
        return (
            kind,
            sym.name + "()",
            "punto de entrada" if sym.is_entry else "",
            f"#/flujo/{sym.id}",
        )

    def group_layout(self, gid: str, edges) -> dict:
        g = self.groups[gid]
        lnodes = []
        info: dict[str, tuple[str, str, str, str | None]] = {}
        for i, c in enumerate(g.children):
            kind, label, sub, link = self._describe(c)
            info[c] = (kind, label, sub, link)
            w = max(len(label), len(sub)) * CHAR_W + 32
            h = 52.0 if sub else 36.0
            # Los hijos ya vienen ordenados (carpetas por nombre, miembros por línea).
            lnodes.append(LNode(c, max(120.0, float(int(w + 1) // 2 * 2)), h, f"{i:05d}"))
        group_edges = edges.get(gid, {})
        kept = _backbone(group_edges, len(g.children))
        ledges = [
            LEdge(a, b, _edge_label(count, n_routes))
            for (a, b), (count, _, n_routes) in sorted(group_edges.items())
            if (a, b) in kept
        ]
        lay = layout_layered(lnodes, ledges)
        nodes_out = []
        for c in g.children:
            p = lay.nodes[c]
            kind, label, sub, link = info[c]
            nodes_out.append([c, kind, p.x, p.y, p.w, p.h, label, sub, link])
        edges_out = []
        for e in lay.edges:
            flat: list[float] = []
            for x, y in e.points:
                flat.extend((x, y))
            box = e.label_box or (0, 0, 0, 0)
            count, mix, n_routes = group_edges[(e.src, e.dst)]
            # Último campo: el desglose por confianza, para el tooltip de la flecha.
            breakdown = {c: mix[c] for c in CONFIDENCES if mix.get(c)}
            if n_routes:
                breakdown["rutas"] = n_routes
            edges_out.append(
                [e.src, e.dst, flat, _majority(mix), e.label, box[0], box[1], box[2], box[3],
                 breakdown]
            )
        kinds = {n[1] for n in nodes_out}
        confs = {e[3] for e in edges_out}
        legend = [k for k in MAP_LEGEND_ORDER if k in kinds or k in confs]
        return {
            "w": lay.width,
            "h": lay.height,
            "nodes": nodes_out,
            "edges": edges_out,
            "legend": legend,
            "hidden": len(group_edges) - len(kept),  # relaciones débiles no dibujadas
        }

    def summary(self, gid: str) -> str:
        g = self.groups[gid]
        kinds: dict[str, int] = defaultdict(int)
        for c in g.children:
            if c in self.groups:
                kinds[self.groups[c].kind] += 1
            else:
                kinds["función"] += 1
        names = {
            "modulo": ("carpeta", "carpetas"),
            "archivo": ("archivo", "archivos"),
            "clase": ("clase", "clases"),
            "interfaz": ("interfaz", "interfaces"),
            "otros": ("grupo", "grupos"),
            "función": ("función", "funciones"),
        }
        parts = [
            _plural(kinds[k], *names[k])
            for k in ("modulo", "archivo", "clase", "interfaz", "función", "otros")
            if kinds.get(k)
        ]
        return " · ".join(parts)


def _majority(mix: dict[str, int]) -> str:
    """Confianza con que se dibuja una flecha agrupada: la de la mayoría de sus llamadas.

    Decisión de Italo (2026-10-25), cambiando la SPEC §6.4 ("peor confianza"): en
    proyectos grandes una sola llamada dudosa entre cientos dejaba la flecha punteada.
    En empate gana la menos segura. Sin llamadas (solo rutas) es "exacta".
    """
    if not mix:
        return "exacta"
    return max(mix.items(), key=lambda kv: (kv[1], CONFIDENCE_RANK[kv[0]]))[0]


# Más relaciones que esto por elemento vuelve el nivel ilegible (en Django, 17 carpetas
# tenían 145 flechas y el diagrama quedaba al 8 % de tamaño): se dibuja el esqueleto.
MAX_EDGES_PER_NODE = 1.5


def _backbone(edges: dict[tuple[str, str], list], n_nodes: int) -> set[tuple[str, str]]:
    """Relaciones a dibujar en un nivel denso: las más fuertes que lo mantienen conectado.

    1. Árbol de expansión máximo (Kruskal): une todos los elementos usando primero las
       relaciones con más llamadas, sin cerrar ciclos.
    2. Luego, las siguientes más fuertes hasta MAX_EDGES_PER_NODE por elemento.
    Con pocas relaciones se dibujan todas.
    """
    limit = max(n_nodes, int(n_nodes * MAX_EDGES_PER_NODE))
    if len(edges) <= limit:
        return set(edges)

    def weight(key: tuple[str, str]) -> int:
        count, _, n_routes = edges[key]
        return count + n_routes

    order = sorted(edges, key=lambda k: (-weight(k), k))
    root: dict[str, str] = {}

    def find(x: str) -> str:
        while root.get(x, x) != x:
            root[x] = root.get(root[x], root[x])
            x = root[x]
        return x

    kept: list[tuple[str, str]] = []
    for a, b in order:
        ra, rb = find(a), find(b)
        if ra != rb:
            root[ra] = rb
            kept.append((a, b))
    chosen = set(kept)
    for key in order:
        if len(chosen) >= limit:
            break
        chosen.add(key)
    return chosen


def _short(name: str, limit: int = 12) -> str:
    """Nombre recortado para las etiquetas de los grupos "Otros"."""
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _edge_label(calls: int, routes: int) -> str:
    parts = []
    if routes:
        parts.append(_plural(routes, "ruta", "rutas"))
    if calls:
        parts.append(_plural(calls, "llamada", "llamadas"))
    return " · ".join(parts)


def build_map(project: Project, routes: list[tuple[str, str]] | None = None) -> dict:
    """Datos del mapa para el visor: grupos con su layout y dueño de cada elemento.

    `routes`: pares (archivo de rutas, método destino) que se dibujan como aristas.
    """
    mb = MapBuilder(project)
    mb.build_tree()
    edges = mb.aggregate(routes)
    mb.limit_children(edges)
    groups_out = {}
    for gid in sorted(mb.groups):
        g = mb.groups[gid]
        groups_out[gid] = {
            "name": g.name,
            "kind": g.kind,
            "parent": g.parent,
            "summary": mb.summary(gid),
            "layout": mb.group_layout(gid, edges),
        }
    owner = {el: gid for el, gid in sorted(mb.owner.items())}
    # Archivo → su nivel en el mapa (lo usa la galaxia para "clic: ver en el mapa").
    files = {
        path: el for path, el in sorted(mb.file_element.items()) if el in mb.groups
    }
    return {"root": "root", "groups": groups_out, "owner": owner, "files": files}
