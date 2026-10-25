"""Vista "galaxia": el proyecto entero de un vistazo (Bloque 2).

- Cada punto es un archivo de código; su tamaño crece con sus funciones.
- Dos archivos se unen si uno llama al otro (llamadas con destino claro).
- **Subsistemas**: grupos de archivos que se llaman mucho entre sí, detectados con el
  algoritmo de Louvain (modularidad), implementado aquí, sin dependencias.
- **Nodos centrales**: los archivos con más conexiones (por donde "pasa todo").
- Layout determinista en Python: cada subsistema es un racimo en espiral (ángulo de oro)
  con el archivo más conectado al centro; los racimos se acomodan con un algoritmo de
  fuerzas sencillo y luego se separan para que no se encimen.

Sin IA: los nombres de los subsistemas salen de la carpeta donde están sus archivos.
"""

from __future__ import annotations

import math
import posixpath
from collections import Counter, defaultdict

from desglosa.ir import Project, call_targets

FUNC_KINDS = ("function", "method")
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
SPACING = 16.0  # separación de los puntos dentro de un racimo
GAP = 60.0  # separación mínima entre racimos
MAX_EDGES = 4000  # más líneas que esto vuelve lento el SVG; se dibujan las más fuertes
GOD_NODES = 10
MIN_COMMUNITY = 3  # subsistemas más chicos se juntan en "grupos pequeños"


# --------------------------------------------------------------------------- Louvain


def louvain(nodes: list[str], weights: dict[tuple[str, str], float]) -> dict[str, int]:
    """Comunidades por modularidad (Blondel et al., 2008). Determinista: recorre los
    nodos en orden y desempata por el número de comunidad más bajo.

    `weights` es no dirigido: (a, b) con a < b.
    """
    # Estado de cada nivel: nodos (índices), vecinos con peso y pesos propios (lazos).
    index = {n: i for i, n in enumerate(sorted(nodes))}
    n = len(index)
    adj: list[dict[int, float]] = [defaultdict(float) for _ in range(n)]
    for (a, b), w in weights.items():
        if a == b or a not in index or b not in index:
            continue
        ia, ib = index[a], index[b]
        adj[ia][ib] += w
        adj[ib][ia] += w
    member = list(range(n))  # nodo original → nodo del nivel actual
    loops = [0.0] * n
    while True:
        comm, improved = _one_level(adj, loops)
        if not improved:
            break
        # Renumerar comunidades 0..k-1 en orden de aparición (determinista).
        renum: dict[int, int] = {}
        for c in comm:
            renum.setdefault(c, len(renum))
        comm = [renum[c] for c in comm]
        member = [comm[m] for m in member]
        k = len(renum)
        new_adj: list[dict[int, float]] = [defaultdict(float) for _ in range(k)]
        new_loops = [0.0] * k
        for i, nbrs in enumerate(adj):
            ci = comm[i]
            new_loops[ci] += loops[i]
            for j, w in nbrs.items():
                cj = comm[j]
                if ci == cj:
                    new_loops[ci] += w / 2  # cada arista interna se ve dos veces
                else:
                    new_adj[ci][cj] += w
        adj, loops = new_adj, new_loops
        if k == len(comm):
            break
    order = sorted(index, key=index.get)
    return {name: member[i] for i, name in enumerate(order)}


def _one_level(adj: list[dict[int, float]], loops: list[float]) -> tuple[list[int], bool]:
    n = len(adj)
    degree = [sum(nbrs.values()) + 2 * loops[i] for i, nbrs in enumerate(adj)]
    m2 = sum(degree)  # 2m
    if m2 == 0:
        return list(range(n)), False
    comm = list(range(n))
    tot = degree[:]  # suma de grados por comunidad
    improved = False
    moved = True
    while moved:
        moved = False
        for i in range(n):
            ci = comm[i]
            links: dict[int, float] = defaultdict(float)
            for j, w in adj[i].items():
                links[comm[j]] += w
            tot[ci] -= degree[i]
            best, best_gain = ci, links.get(ci, 0.0) - tot[ci] * degree[i] / m2
            for c in sorted(links):
                gain = links[c] - tot[c] * degree[i] / m2
                if gain > best_gain + 1e-12:
                    best, best_gain = c, gain
            tot[best] += degree[i]
            if best != ci:
                comm[i] = best
                moved = improved = True
    return comm, improved


# --------------------------------------------------------------------------- nombres


def community_label(files: list[str]) -> str:
    """Nombre de un subsistema sin IA, sacado de sus carpetas.

    La carpeta directa más común de sus archivos; si no reúne ni la mitad, las dos más
    comunes con su parte en común: `tests/{queries, aggregation}`.
    """
    parents = Counter(posixpath.dirname(f) or "(raíz)" for f in files)
    ranked = sorted(parents, key=lambda d: (-parents[d], d))
    first = ranked[0]
    if parents[first] * 2 >= len(files) or len(ranked) == 1:
        return first
    second = ranked[1]
    common = posixpath.commonpath([first, second]) if "(raíz)" not in (first, second) else ""
    if common:
        a, b = first[len(common) :].lstrip("/"), second[len(common) :].lstrip("/")
        if not a or not b:  # una es la carpeta común misma: "models (+fields)"
            return f"{common} (+{a or b})"
        return f"{common}/{{{a}, {b}}}"
    return f"{first}, {second}"


# --------------------------------------------------------------------------- layout


def _spiral(count: int) -> list[tuple[float, float]]:
    return [
        (SPACING * math.sqrt(k) * math.cos(k * GOLDEN_ANGLE),
         SPACING * math.sqrt(k) * math.sin(k * GOLDEN_ANGLE))
        for k in range(count)
    ]


def _place_clusters(
    radii: list[float], links: dict[tuple[int, int], float]
) -> list[tuple[float, float]]:
    """Empaquetado codicioso y determinista de los racimos (círculos).

    El primero (el más grande) va al centro. Cada siguiente se pega, sin encimarse, junto
    al racimo ya ubicado con el que más se conecta (o junto al centro si con ninguno),
    probando ángulos cada 10° y quedándose con el lugar más cerca del centro.
    """
    k = len(radii)
    if k == 0:
        return []
    weight: dict[int, dict[int, float]] = defaultdict(dict)
    for (i, j), w in links.items():
        weight[i][j] = w
        weight[j][i] = w
    pos: list[tuple[float, float]] = [(0.0, 0.0)]
    for i in range(1, k):
        placed = range(len(pos))
        anchor = max(placed, key=lambda j: (weight[i].get(j, 0.0), -j))
        if weight[i].get(anchor, 0.0) == 0:
            anchor = 0
        best = None
        for ring in range(1, 60):
            dist = radii[anchor] + radii[i] + GAP * ring
            for step in range(36):
                ang = step * math.pi / 18
                x = pos[anchor][0] + dist * math.cos(ang)
                y = pos[anchor][1] + dist * math.sin(ang)
                if all(
                    math.hypot(x - pos[j][0], y - pos[j][1]) >= radii[i] + radii[j] + GAP - 0.01
                    for j in placed
                ):
                    score = math.hypot(x, y)
                    if best is None or score < best[0] - 1e-9:
                        best = (score, x, y)
            if best is not None:
                break
        pos.append((best[1], best[2]) if best else (0.0, (k + i) * 1000.0))
    return pos


# --------------------------------------------------------------------------- galaxia


def build_galaxy(project: Project, links: dict[str, str] | None = None) -> dict | None:
    """Datos de la vista galaxia, o None si el proyecto tiene menos de 3 archivos.

    `links`: archivo → enlace del visor (por ejemplo su nivel en el mapa).
    """
    funcs = Counter(s.file for s in project.symbols if s.kind in FUNC_KINDS)
    files = sorted({s.file for s in project.symbols if s.kind != "module"})
    if len(files) < 3:
        return None
    by_id = {s.id: s for s in project.symbols}
    in_graph = set(files)
    weights: dict[tuple[str, str], float] = defaultdict(float)
    for c in project.calls:
        caller = by_id.get(c.caller_id)
        if caller is None or caller.file not in in_graph:
            continue
        for t in call_targets(c):
            target = by_id.get(t)
            if target is None or target.file == caller.file or target.file not in in_graph:
                continue
            a, b = sorted((caller.file, target.file))
            weights[(a, b)] += 1
    comm = louvain(files, weights)
    # Los archivos sin ninguna conexión van juntos a un grupo aparte.
    degree: Counter = Counter()
    for (a, b), w in weights.items():
        degree[a] += w
        degree[b] += w
    groups: dict[int, list[str]] = defaultdict(list)
    lonely = [f for f in files if degree[f] == 0]
    for f in files:
        if degree[f]:
            groups[comm[f]].append(f)
    # Los grupos de 1–2 archivos van juntos: cientos de racimos diminutos no dicen nada.
    big = [fs for fs in groups.values() if len(fs) >= MIN_COMMUNITY]
    small = sorted(f for fs in groups.values() if len(fs) < MIN_COMMUNITY for f in fs)
    ordered = sorted(big, key=lambda fs: (-len(fs), fs[0]))
    extra_labels = []
    if small:
        ordered.append(small)
        extra_labels.append("grupos pequeños")
    if lonely:
        ordered.append(lonely)
        extra_labels.append("sin conexiones")
    n_named = len(ordered) - len(extra_labels)
    cid = {f: i for i, fs in enumerate(ordered) for f in fs}

    # Layout: racimo en espiral por subsistema, el más conectado al centro.
    radii, local = [], []
    for fs in ordered:
        members = sorted(fs, key=lambda f: (-degree[f], f))
        spots = _spiral(len(members))
        local.append(dict(zip(members, spots, strict=True)))
        radii.append(SPACING * math.sqrt(len(members)) + 14)
    cl_links: dict[tuple[int, int], float] = defaultdict(float)
    for (a, b), w in weights.items():
        ca, cb = cid[a], cid[b]
        if ca != cb:
            cl_links[(min(ca, cb), max(ca, cb))] += w
    centers = _place_clusters(radii, cl_links)
    margin = 40.0
    min_x = min(c[0] - r for c, r in zip(centers, radii, strict=True)) - margin
    min_y = min(c[1] - r for c, r in zip(centers, radii, strict=True)) - margin
    max_x = max(c[0] + r for c, r in zip(centers, radii, strict=True)) + margin
    max_y = max(c[1] + r for c, r in zip(centers, radii, strict=True)) + margin

    def node_r(f: str) -> float:
        return round(min(14.0, 3.0 + 1.6 * math.sqrt(funcs.get(f, 0))), 1)

    index = {f: i for i, f in enumerate(files)}
    nodes = []
    for f in files:
        c = cid[f]
        lx, ly = local[c][f]
        cx, cy = centers[c]
        nodes.append([
            f,
            round(cx + lx - min_x, 1),
            round(cy + ly - min_y, 1),
            node_r(f),
            c,
            funcs.get(f, 0),
            int(degree[f]),
            (links or {}).get(f),
        ])
    strongest = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_EDGES]
    edges = [[index[a], index[b], int(w)] for (a, b), w in sorted(strongest)]
    gods = [
        index[f] for f in sorted(files, key=lambda f: (-degree[f], f))[:GOD_NODES] if degree[f]
    ]
    communities = []
    seen_labels: Counter = Counter()
    for i, fs in enumerate(ordered):
        label = community_label(fs) if i < n_named else extra_labels[i - n_named]
        seen_labels[label] += 1
        if seen_labels[label] > 1:  # dos subsistemas en la misma carpeta
            label = f"{label} ({seen_labels[label]})"
        cx, cy = centers[i]
        communities.append([
            i, label, len(fs), round(cx - min_x, 1), round(cy - min_y, 1), round(radii[i], 1)
        ])
    return {
        "w": round(max_x - min_x, 1),
        "h": round(max_y - min_y, 1),
        "nodes": nodes,
        "edges": edges,
        "hidden_edges": max(0, len(weights) - MAX_EDGES),
        "communities": communities,
        "gods": gods,
        # Todas las llamadas entre subsistemas (no solo las líneas dibujadas).
        "between": [[a, b, int(w)] for (a, b), w in sorted(cl_links.items())],
    }
