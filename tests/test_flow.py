"""Diagramas de flujo: estructura del FlowGraph y garantías del layout (SPEC §7)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from desglosa.ir import FLOW_EDGE_KINDS, FLOW_NODE_KINDS, dumps
from desglosa.layout.flow import layout_flow
from desglosa.pipeline import AnalyzeOptions, analyze
from tests.conftest import FIXTURES, needs_grammars

pytestmark = needs_grammars

ROOT = Path(__file__).resolve().parent.parent
FACTURACION = ("c", "cpp", "java", "javascript", "php", "python", "typescript")


@pytest.fixture(scope="module")
def analyses():
    out = {lang: analyze(FIXTURES / lang) for lang in FACTURACION}
    out["flujo"] = analyze(FIXTURES / "flujo")
    out["gps"] = analyze(ROOT / "examples" / "gps-c")
    return out


def _all_flows(analyses):
    for name, a in analyses.items():
        by_id = {s.id: s for s in a.project.symbols}
        for sid, f in a.flows.items():
            yield f"{name}:{by_id[sid].qualname}", f


@pytest.mark.parametrize("lang", FACTURACION)
def test_emitir_golden(lang, analyses, golden):
    a = analyses[lang]
    emitir = next(s for s in a.project.symbols if s.name == "emitir")
    golden(f"flow/{lang}_emitir.json", dumps(a.flows[emitir.id].graph))


def test_gps_main_golden(analyses, golden):
    a = analyses["gps"]
    main = next(s for s in a.project.symbols if s.name == "main")
    golden("flow/gps_main.json", dumps(a.flows[main.id].graph))


def test_graph_structure(analyses):
    for name, f in _all_flows(analyses):
        g = f.graph
        ids = [n.id for n in g.nodes]
        assert len(ids) == len(set(ids)), name
        assert g.nodes[0].kind == "terminal" and g.nodes[0].text_easy.startswith("Inicio"), name
        assert any(n.kind == "terminal" and n.text_tech.startswith("Fin") for n in g.nodes), name
        out = defaultdict(int)
        for e in g.edges:
            assert e.src in ids and e.dst in ids, name
            assert e.kind in FLOW_EDGE_KINDS, name
            out[e.src] += 1
        for n in g.nodes:
            assert n.kind in FLOW_NODE_KINDS, name
            assert n.text_easy and n.text_tech, f"{name}: {n.id} sin texto"  # RF-10
            if not n.text_tech.startswith("Fin"):
                assert out[n.id] >= 1, f"{name}: {n.id} ({n.text_tech}) sin salida"


def test_all_nodes_reachable(analyses):
    for name, f in _all_flows(analyses):
        g = f.graph
        nxt = defaultdict(list)
        for e in g.edges:
            nxt[e.src].append(e.dst)
        seen = {g.nodes[0].id}
        stack = [g.nodes[0].id]
        while stack:
            for d in nxt[stack.pop()]:
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        missing = [n.text_tech for n in g.nodes if n.id not in seen]
        assert not missing, f"{name}: inalcanzables {missing}"


def test_subprocess_targets(analyses):
    """RF-06: cada subproceso tiene destino; en emitir hay uno hacia cobrar()."""
    for name, f in _all_flows(analyses):
        for n in f.graph.nodes:
            if n.kind == "subproceso":
                assert n.target_symbol, f"{name}: subproceso sin destino"
    for lang in FACTURACION:
        a = analyses[lang]
        by_id = {s.id: s for s in a.project.symbols}
        emitir = next(s for s in a.project.symbols if s.name == "emitir")
        targets = [
            by_id[n.target_symbol].name for n in a.flows[emitir.id].graph.nodes if n.target_symbol
        ]
        assert "cobrar" in targets, lang


def test_constructs_present(analyses):
    a = analyses["python"]
    emitir = next(s for s in a.project.symbols if s.name == "emitir")
    g = a.flows[emitir.id].graph
    kinds = {n.kind for n in g.nodes}
    assert {"decision", "subproceso", "pantalla", "documento", "externo"} <= kinds
    edge_kinds = {e.kind for e in g.edges}
    assert {"retorno_bucle", "excepcion", "salto"} <= edge_kinds
    labels = {e.label for e in g.edges if e.label}
    assert {"sí", "no", 'caso "efectivo"', "otro", "excepción: ValueError"} <= labels


def test_fallthrough_and_goto(analyses):
    a = analyses["flujo"]
    menu = next(s for s in a.project.symbols if s.name == "menu")
    g = a.flows[menu.id].graph
    labels = {e.label for e in g.edges if e.label}
    assert "caso 0 / caso 1" in labels  # caso vacío que cae al siguiente
    assert any("goto fin" in n.text_easy for n in g.nodes)
    assert any(w.endswith("goto no soportado") for w in a.flows[menu.id].warnings)


def test_do_while_back_edge(analyses):
    a = analyses["flujo"]
    menu = next(s for s in a.project.symbols if s.name == "menu")
    g = a.flows[menu.id].graph
    back = [e for e in g.edges if e.kind == "retorno_bucle" and e.label == "sí"]
    assert len(back) == 1


def test_truncation():
    a = analyze(ROOT / "examples" / "gps-c", AnalyzeOptions(max_flow_nodes=15))
    main = next(s for s in a.project.symbols if s.name == "main")
    g = a.flows[main.id].graph
    assert g.truncated
    assert any(n.text_easy.startswith("Bloque (L") for n in g.nodes)
    assert len(g.nodes) <= 15


# --------------------------------------------------------------------------- layout


def _rect(n):
    return (n.x, n.y, n.x + n.w, n.y + n.h)


def _inside(r, shrink=1.0):
    return (r[0] + shrink, r[1] + shrink, r[2] - shrink, r[3] - shrink)


def _seg_hits(a, b, r):
    (x1, y1), (x2, y2) = a, b
    rx1, ry1, rx2, ry2 = r
    if x1 == x2:
        lo, hi = sorted((y1, y2))
        return rx1 < x1 < rx2 and lo < ry2 and hi > ry1
    lo, hi = sorted((x1, x2))
    return ry1 < y1 < ry2 and lo < rx2 and hi > rx1


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def test_layout_no_overlaps(analyses):
    for name, f in _all_flows(analyses):
        boxes = [(n.id, _rect(n)) for n in f.layout.nodes]
        boxes += [
            (f"c{c.label}", (c.x - c.r, c.y - c.r, c.x + c.r, c.y + c.r))
            for c in f.layout.connectors
        ]
        for i, (ia, ra) in enumerate(boxes):
            for ib, rb in boxes[i + 1 :]:
                assert not _overlap(_inside(ra), _inside(rb)), f"{name}: {ia} se superpone con {ib}"


def test_layout_lines_do_not_cross_nodes(analyses):
    for name, f in _all_flows(analyses):
        rects = [(n.id, _inside(_rect(n))) for n in f.layout.nodes]
        rects += [
            (f"c{c.label}", _inside((c.x - c.r, c.y - c.r, c.x + c.r, c.y + c.r)))
            for c in f.layout.connectors
        ]
        for line in f.layout.lines:
            pts = line.points
            for a, b in zip(pts, pts[1:], strict=False):
                assert a[0] == b[0] or a[1] == b[1], f"{name}: segmento no ortogonal"
                for nid, r in rects:
                    assert not _seg_hits(a, b, r), f"{name}: línea {pts} atraviesa {nid}"


def test_layout_labels_do_not_cover_nodes(analyses):
    for name, f in _all_flows(analyses):
        rects = [_inside(_rect(n)) for n in f.layout.nodes]
        for lb in f.layout.labels:
            box = (lb.x, lb.y, lb.x + lb.w, lb.y + lb.h)
            for r in rects:
                assert not _overlap(box, r), f"{name}: etiqueta {lb.text!r} tapa un nodo"


def test_layout_covers_every_node(analyses):
    for name, f in _all_flows(analyses):
        assert {n.id for n in f.layout.nodes} == {n.id for n in f.graph.nodes}, name
        for n in f.layout.nodes:
            assert n.x >= 0 and n.x + n.w <= f.layout.width + 0.5, name
            assert n.y >= 0 and n.y + n.h <= f.layout.height + 0.5, name


def test_columns_with_connectors(analyses):
    a = analyses["gps"]
    main = next(s for s in a.project.symbols if s.name == "main")
    lay = a.flows[main.id].layout
    assert lay.columns >= 2
    assert {"1"} <= {c.label for c in lay.connectors}
    out = a.flows[main.id]
    tall = layout_flow(out.graph, out.struct, max_height=100000)
    assert tall.columns == 1
    assert not any(c.label.isdigit() for c in tall.connectors)
