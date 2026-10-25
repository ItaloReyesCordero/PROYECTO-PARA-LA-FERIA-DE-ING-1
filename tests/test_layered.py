"""Layout por capas (SPEC §10): sin superposiciones y sin aristas que crucen nodos."""

from __future__ import annotations

import random

from desglosa.layout.layered import LEdge, LNode, layout_layered


def _seg_rect(p, q, r) -> bool:
    """¿El segmento p-q entra al interior del rectángulo r (reducido 1 px)? (Liang–Barsky)."""
    x1, y1, x2, y2 = r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x1), (dx, x2 - p[0]), (-dy, p[1] - y1), (dy, y2 - p[1])):
        if pk == 0:
            if qk < 0:
                return False
        else:
            t = qk / pk
            if pk < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return t1 - t0 > 1e-9


def _check(nodes, edges, fixed=None):
    lay = layout_layered(nodes, edges, fixed)
    rects = {n: (p.x, p.y, p.x + p.w, p.y + p.h) for n, p in lay.nodes.items()}
    assert set(rects) == {n.id for n in nodes}
    items = sorted(rects.items())
    for i, (a, ra) in enumerate(items):
        assert ra[2] <= lay.width + 0.5 and ra[3] <= lay.height + 0.5
        for b, rb in items[i + 1 :]:
            overlap = ra[0] < rb[2] and ra[2] > rb[0] and ra[1] < rb[3] and ra[3] > rb[1]
            assert not overlap, f"{a} y {b} se superponen"
    for e in lay.edges:
        for p, q in zip(e.points, e.points[1:], strict=False):
            for nid, r in rects.items():
                if nid in (e.src, e.dst):
                    continue
                assert not _seg_rect(p, q, r), f"arista {e.src}->{e.dst} atraviesa {nid}"
        if e.label_box:
            lx, ly, lw, lh = e.label_box
            for nid, r in rects.items():
                hit = lx < r[2] - 1 and lx + lw > r[0] + 1 and ly < r[3] - 1 and ly + lh > r[1] + 1
                assert not hit, f"etiqueta de {e.src}->{e.dst} tapa {nid}"
    return lay


def test_chain_goes_left_to_right():
    nodes = [LNode(x, 120, 40, x) for x in "abc"]
    lay = _check(nodes, [LEdge("a", "b", "1 llamada"), LEdge("b", "c", "2 llamadas")])
    assert lay.nodes["a"].x < lay.nodes["b"].x < lay.nodes["c"].x


def test_cycle_and_long_edge():
    nodes = [LNode(x, 140, 52, x) for x in "abcde"]
    edges = [
        LEdge("a", "b"),
        LEdge("b", "c"),
        LEdge("c", "a"),
        LEdge("a", "d"),
        LEdge("d", "e"),
        LEdge("a", "e", "9 llamadas"),
    ]
    _check(nodes, edges)


def test_isolated_nodes_go_to_a_grid():
    nodes = [LNode(f"n{i}", 120, 36, f"{i:02d}") for i in range(10)]
    lay = _check(nodes, [])
    assert len({p.y for p in lay.nodes.values()}) >= 2


def test_random_graphs_are_clean():
    rnd = random.Random(7)
    for _ in range(25):
        n = rnd.randint(2, 14)
        nodes = [
            LNode(f"n{i}", rnd.choice([120, 160, 220]), rnd.choice([36, 52]), f"{i:02d}")
            for i in range(n)
        ]
        edges = []
        for _ in range(rnd.randint(0, n * 2)):
            a, b = rnd.randrange(n), rnd.randrange(n)
            edges.append(LEdge(f"n{a}", f"n{b}", f"{rnd.randint(1, 30)} llamadas"))
        _check(nodes, edges)


def test_deterministic():
    nodes = [LNode(x, 120, 40, x) for x in "dcba"]
    edges = [LEdge("a", "b"), LEdge("c", "d"), LEdge("a", "d")]
    assert layout_layered(nodes, edges) == layout_layered(list(reversed(nodes)), edges)


def test_fixed_layers_keep_columns_and_drop_same_column_edges():
    nodes = [LNode(x, 120, 40, x) for x in "abcde"]
    fixed = {"a": 0, "b": 1, "c": 1, "d": 2, "e": 0}
    edges = [LEdge("a", "b"), LEdge("b", "c"), LEdge("c", "d", "3 llamadas"), LEdge("d", "e")]
    lay = _check(nodes, edges, fixed)
    xs = {n: p.x + p.w / 2 for n, p in lay.nodes.items()}
    assert xs["a"] == xs["e"] < xs["b"] == xs["c"] < xs["d"]
    drawn = {(e.src, e.dst) for e in lay.edges}
    assert ("b", "c") not in drawn  # misma columna: se omite
    assert ("d", "e") in drawn  # hacia atrás: se dibuja (al revés)
    back = next(e for e in lay.edges if (e.src, e.dst) == ("d", "e"))
    assert back.points[0][0] > back.points[-1][0]  # sale de d (derecha) y llega a e


def test_fixed_layers_random_graphs_are_clean():
    rnd = random.Random(11)
    for _ in range(25):
        n = rnd.randint(2, 14)
        nodes = [LNode(f"n{i}", rnd.choice([120, 180]), 36, f"{i:02d}") for i in range(n)]
        fixed = {f"n{i}": rnd.randrange(4) for i in range(n)}
        edges = [
            LEdge(f"n{rnd.randrange(n)}", f"n{rnd.randrange(n)}", "1 llamada")
            for _ in range(rnd.randint(0, n * 2))
        ]
        _check(nodes, edges, fixed)
