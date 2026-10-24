"""Layout por capas (Sugiyama simplificado) para el mapa y el diagrama ER (SPEC §10).

1. Romper ciclos invirtiendo las aristas de retroceso de un DFS determinista.
2. Capas por camino más largo.
3. Orden dentro de cada capa por baricentro (4 barridos ida y vuelta), desempate por nombre.
4. Coordenadas: dirección izquierda → derecha; separación mínima entre capas y nodos.
5. Aristas poligonales que pasan por nodos virtuales; así solo cruzan los huecos entre capas
   y nunca atraviesan una caja. Etiqueta en el tramo más largo, con máscara opaca.

Los nodos sin ninguna arista se colocan en una grilla debajo del grafo.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from desglosa.layout.text import label_size

LAYER_GAP = 120
NODE_GAP = 26
GRID_GAP = 24
MARGIN = 24
VIRTUAL_H = 10


@dataclass(frozen=True)
class LNode:
    id: str
    w: float
    h: float
    key: str  # para desempatar de forma determinista


@dataclass(frozen=True)
class LEdge:
    src: str
    dst: str
    label: str | None = None


@dataclass(frozen=True)
class Placed:
    id: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class PlacedEdge:
    src: str
    dst: str
    points: tuple[tuple[float, float], ...]
    label: str | None
    label_box: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class LayeredLayout:
    width: float
    height: float
    nodes: dict[str, Placed]
    edges: tuple[PlacedEdge, ...]


def _break_cycles(order: list[str], succ: dict[str, list[str]]) -> set[tuple[str, str]]:
    reversed_edges: set[tuple[str, str]] = set()
    state: dict[str, int] = {}  # 1 = en la pila, 2 = terminado
    for root in order:
        if root in state:
            continue
        stack = [(root, iter(succ[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                continue
            st = state.get(nxt)
            if st == 1:
                reversed_edges.add((node, nxt))
            elif st is None:
                state[nxt] = 1
                stack.append((nxt, iter(succ[nxt])))
    return reversed_edges


def _layers(order: list[str], dag: dict[str, list[str]]) -> dict[str, int]:
    indeg = {n: 0 for n in order}
    for n in order:
        for m in dag[n]:
            indeg[m] += 1
    pos = {n: i for i, n in enumerate(order)}
    ready = sorted((n for n in order if indeg[n] == 0), key=pos.__getitem__)
    layer = {n: 0 for n in order}
    while ready:
        n = ready.pop(0)
        for m in dag[n]:
            layer[m] = max(layer[m], layer[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
                ready.sort(key=pos.__getitem__)
    return layer


def layout_layered(nodes: list[LNode], edges: list[LEdge]) -> LayeredLayout:
    nodes = sorted(nodes, key=lambda n: (n.key, n.id))
    by_id = {n.id: n for n in nodes}
    order = [n.id for n in nodes]
    clean: list[LEdge] = []
    seen_pairs: set[tuple[str, str]] = set()
    for e in sorted(edges, key=lambda e: (by_id[e.src].key, by_id[e.dst].key, e.src, e.dst)):
        if e.src == e.dst or e.src not in by_id or e.dst not in by_id:
            continue
        if (e.src, e.dst) in seen_pairs:
            continue
        seen_pairs.add((e.src, e.dst))
        clean.append(e)
    connected = {e.src for e in clean} | {e.dst for e in clean}
    graph_ids = [n for n in order if n in connected]
    isolated = [n for n in order if n not in connected]

    succ: dict[str, list[str]] = defaultdict(list)
    for e in clean:
        succ[e.src].append(e.dst)
    for n in graph_ids:
        succ[n].sort(key=lambda m: (by_id[m].key, m))
    rev = _break_cycles(graph_ids, succ)
    dag: dict[str, list[str]] = defaultdict(list)
    oriented: list[tuple[LEdge, str, str]] = []
    for e in clean:
        a, b = (e.dst, e.src) if (e.src, e.dst) in rev else (e.src, e.dst)
        dag[a].append(b)
        oriented.append((e, a, b))
    layer = _layers(graph_ids, dag)

    # Nodos virtuales para aristas que saltan varias capas.
    sizes: dict[str, tuple[float, float]] = {n: (by_id[n].w, by_id[n].h) for n in graph_ids}
    keys: dict[str, str] = {n: by_id[n].key for n in graph_ids}
    chains: list[tuple[LEdge, list[str], bool]] = []
    for i, (e, a, b) in enumerate(oriented):
        chain = [a]
        for k, lay in enumerate(range(layer[a] + 1, layer[b])):
            vid = f"~v{i}_{k}"
            layer[vid] = lay
            sizes[vid] = (0.0, VIRTUAL_H)
            keys[vid] = keys[a]
            chain.append(vid)
        chain.append(b)
        chains.append((e, chain, (e.src, e.dst) in rev))

    n_layers = max(layer.values(), default=-1) + 1
    layers: list[list[str]] = [[] for _ in range(n_layers)]
    for n in sorted(layer, key=lambda n: (keys[n], n)):
        layers[layer[n]].append(n)
    up: dict[str, list[str]] = defaultdict(list)
    down: dict[str, list[str]] = defaultdict(list)
    for _, chain, _ in chains:
        for u, v in zip(chain, chain[1:], strict=False):
            down[u].append(v)
            up[v].append(u)

    def sweep(rows: list[list[str]], neighbors: dict[str, list[str]], indices: range) -> None:
        for li in indices:
            ref_pos = {n: i for i, n in enumerate(rows[li - 1 if neighbors is up else li + 1])}
            current = {n: i for i, n in enumerate(rows[li])}

            def bary(n: str, ref_pos=ref_pos, current=current) -> tuple[float, str, str]:
                ns = [ref_pos[m] for m in neighbors[n] if m in ref_pos]
                value = sum(ns) / len(ns) if ns else float(current[n])
                return (value, keys[n], n)

            rows[li].sort(key=bary)

    for _ in range(4):
        sweep(layers, up, range(1, n_layers))
        sweep(layers, down, range(n_layers - 2, -1, -1))

    # Coordenadas: x por capa; y apilando y acercando cada nodo a sus vecinos.
    col_w = [max((sizes[n][0] for n in row), default=0.0) for row in layers]
    xs: list[float] = []
    x = float(MARGIN)
    for w in col_w:
        xs.append(x)
        x += w + LAYER_GAP
    pos_y: dict[str, float] = {}
    for li, row in enumerate(layers):
        y = float(MARGIN)
        for n in row:
            h = sizes[n][1]
            desired = y
            if li > 0:
                ns = [pos_y[m] + sizes[m][1] / 2 for m in up[n] if m in pos_y]
                if ns:
                    desired = max(y, sum(ns) / len(ns) - h / 2)
            pos_y[n] = desired
            y = desired + h + NODE_GAP

    placed: dict[str, Placed] = {}
    for li, row in enumerate(layers):
        for n in row:
            if n.startswith("~v"):
                continue
            w, h = sizes[n]
            px = xs[li] + (col_w[li] - w) / 2
            placed[n] = Placed(n, round(px, 1), round(pos_y[n], 1), w, h)

    graph_w = (x - LAYER_GAP + MARGIN) if layers else 0.0
    graph_h = max((p.y + p.h for p in placed.values()), default=0.0) + MARGIN

    out_edges: list[PlacedEdge] = []
    for e, chain, was_rev in chains:
        # Cada tramo diagonal va de un borde de columna al siguiente (solo cruza huecos).
        first, last = chain[0], chain[-1]
        pa, pb = placed[first], placed[last]
        la, lb = layer[first], layer[last]
        cya, cyb = pa.y + pa.h / 2, pb.y + pb.h / 2
        pts: list[tuple[float, float]] = [(pa.x + pa.w, cya), (xs[la] + col_w[la], cya)]
        gaps: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for v in chain[1:-1]:
            li = layer[v]
            cy = pos_y[v] + VIRTUAL_H / 2
            gaps.append((pts[-1], (xs[li], cy)))
            pts.append((xs[li], cy))
            pts.append((xs[li] + col_w[li], cy))
        gaps.append((pts[-1], (xs[lb], cyb)))
        pts.append((xs[lb], cyb))
        pts.append((pb.x, cyb))
        if was_rev:
            pts.reverse()
        dedup: list[tuple[float, float]] = []
        for px, py in pts:
            p = (round(px, 1), round(py, 1))
            if not dedup or dedup[-1] != p:
                dedup.append(p)
        pts = dedup
        box = None
        if e.label:
            lw, lh = label_size(e.label)
            best = max(
                gaps,
                key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]),
            )
            mx = (best[0][0] + best[1][0]) / 2
            my = (best[0][1] + best[1][1]) / 2
            box = (round(mx - lw / 2, 1), round(my - lh / 2, 1), round(lw, 1), round(lh, 1))
        out_edges.append(PlacedEdge(e.src, e.dst, tuple(pts), e.label, box))

    # Grilla para los nodos aislados, debajo del grafo.
    width = max(graph_w, MARGIN * 2)
    height = graph_h if graph_ids else float(MARGIN)
    if isolated:
        cell_w = max(by_id[n].w for n in isolated) + GRID_GAP
        cell_h = max(by_id[n].h for n in isolated) + GRID_GAP
        target_w = max(graph_w, 640.0)
        cols = max(1, min(len(isolated), int((target_w - MARGIN) // cell_w) or 1))
        if not graph_ids:
            cols = max(1, min(len(isolated), math.ceil(math.sqrt(len(isolated) * 2))))
        top = height + (GRID_GAP if graph_ids else 0.0)
        for i, n in enumerate(isolated):
            r, c = divmod(i, cols)
            node = by_id[n]
            px = MARGIN + c * cell_w + (cell_w - GRID_GAP - node.w) / 2
            py = top + r * cell_h
            placed[n] = Placed(n, round(px, 1), round(py, 1), node.w, node.h)
        rows = math.ceil(len(isolated) / cols)
        width = max(width, MARGIN * 2 + cols * cell_w - GRID_GAP)
        height = top + rows * cell_h - GRID_GAP + MARGIN
    return LayeredLayout(round(width, 1), round(height, 1), placed, tuple(out_edges))
