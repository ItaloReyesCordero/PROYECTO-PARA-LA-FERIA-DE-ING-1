"""Mermaid (Bloque 3): exportar flujos y secuencias, y dibujar diagramas desde texto."""

from __future__ import annotations

from pathlib import Path

import pytest

from desglosa import cli
from desglosa.mermaid import (
    MermaidError,
    drawing_payload,
    escape,
    flow_to_mermaid,
    parse_mermaid,
    sequence_to_mermaid,
)
from tests.conftest import FIXTURES, needs_grammars

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("python", "javascript", "typescript", "php", "java", "csharp", "c", "cpp", "go",
         "ruby", "rust", "kotlin", "swift")


def test_escape_is_single_pass():
    # Reemplazar uno por uno rompía los códigos ya puestos (el ";" de "#gt;").
    assert escape('a->b; c#d "x" |y|') == "a-#gt;b#59; c#35;d #quot;x#quot; #124;y#124;"
    assert escape("  dos\n  líneas ") == "dos líneas"


# --------------------------------------------------------------------------- exportar


@pytest.fixture(scope="module")
def laravel():
    from desglosa.pipeline import analyze

    return analyze(ROOT / "examples" / "laravel-mini")


@needs_grammars
def test_flow_export_golden(laravel, golden):
    by = {s.qualname: s for s in laravel.project.symbols}
    graph = laravel.flows[by["FacturacionService.emitir"].id].graph
    golden("mermaid/emitir.mmd", flow_to_mermaid(graph, title="FacturacionService.emitir"))


@needs_grammars
def test_sequence_export_golden(laravel, golden):
    from desglosa.sequence import build_sequence

    by = {s.qualname: s for s in laravel.project.symbols}
    routes = {r.symbol_id: f"{r.verb} {r.path}" for r in laravel.routes if r.symbol_id}
    diagram = build_sequence(
        laravel.project, {k: v.graph for k, v in laravel.flows.items()},
        by["FacturaController.store"].id, routes=routes, new_calls=laravel.new_calls,
    )
    text = sequence_to_mermaid(diagram, title="Secuencia de FacturaController.store")
    golden("mermaid/secuencia_store.mmd", text)
    # if sin else → opt; try/catch → alt … else; bloques balanceados.
    assert "opt count($items) === 0" in text
    assert "else excepción PDOException" in text
    opened = sum(text.count(f"\n{' ' * k}{w} ") for k in range(4, 20, 4)
                 for w in ("alt", "opt", "loop"))
    assert opened == text.count("end\n")


@needs_grammars
@pytest.mark.parametrize("lang", LANGS)
def test_round_trip_keeps_every_flow(lang):
    """Exportar a Mermaid y volver a leerlo da los mismos nodos, tipos, textos y flechas."""
    from desglosa.pipeline import analyze

    a = analyze(FIXTURES / lang)
    for flow in a.flows.values():
        graph = flow.graph
        if not graph.nodes:
            continue
        drawing = parse_mermaid(flow_to_mermaid(graph))
        got = {n.id: (n.kind, n.text) for n in drawing.nodes}
        want = {
            n.id: (n.kind if n.kind in _KNOWN else "proceso", " ".join(n.text_easy.split()))
            for n in graph.nodes
        }
        assert got == want, graph.symbol_id
        assert [(e.src, e.dst, e.label) for e in drawing.edges] == [
            (e.src, e.dst, e.label) for e in graph.edges
        ]


_KNOWN = {"terminal", "proceso", "subproceso", "decision", "es", "teclado", "pantalla",
          "documento", "conector"}


# --------------------------------------------------------------------------- leer


def test_parse_shapes_links_and_labels():
    text = """
---
title: Prueba
---
%% comentario
graph TD
    A([Inicio]) --> B[Proceso]; B --> C{"¿x #lt; 3?"}
    C -- sí --> D[[Sub]]
    C -->|no| E[/Lee/]
    E -.-> F[/Teclado\\]
    E ==> G>Pantalla]
    G --- H[\\Doc\\]
    H & D --> I((1))
    I --> J@{ shape: doc, label: "Informe" }
    J --> K@{ shape: manual-input, label: "PIN" }
    K --> L(Fin)
    classDef x fill:#fff
    subgraph S
      L --> M
    end
"""
    d = parse_mermaid(text)
    kinds = {n.id: n.kind for n in d.nodes}
    assert kinds == {
        "A": "terminal", "B": "proceso", "C": "decision", "D": "subproceso", "E": "es",
        "F": "teclado", "G": "pantalla", "H": "documento", "I": "conector", "J": "documento",
        "K": "teclado", "L": "terminal", "M": "proceso",
    }
    texts = {n.id: n.text for n in d.nodes}
    assert texts["C"] == "¿x < 3?" and texts["M"] == "M" and texts["J"] == "Informe"
    edges = {(e.src, e.dst): (e.label, e.style, e.arrow) for e in d.edges}
    assert edges[("C", "D")] == ("sí", "normal", True)
    assert edges[("C", "E")] == ("no", "normal", True)
    assert edges[("E", "F")] == (None, "punteada", True)
    assert edges[("E", "G")] == (None, "gruesa", True)
    assert edges[("G", "H")] == (None, "normal", False)
    assert ("H", "I") in edges and ("D", "I") in edges  # A & B --> C
    assert d.title == "Prueba" and d.direction == "TD"
    assert any("subgrafos" in w for w in d.warnings)
    assert any("classdef" in w for w in d.warnings)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("sequenceDiagram\n A->>B: hola", "no «sequenceDiagram»"),
        ("", "vacío"),
        ("flowchart TD\n A[sin cerrar", "falta cerrar"),
        ("flowchart TD\n A ~~> B", "no entiendo la flecha"),
        ("flowchart TD\n %% nada", "no tiene nodos"),
    ],
)
def test_parse_errors(text, message):
    with pytest.raises(MermaidError, match=message):
        parse_mermaid(text)


def test_direction_and_self_loop():
    d = parse_mermaid("flowchart RL\n A --> A\n A --> B")
    assert d.direction == "LR"
    assert [(e.src, e.dst) for e in d.edges] == [("A", "B")]
    assert len(d.warnings) == 2  # RL dibujado como LR, y la flecha a sí mismo


def _boxes_and_segments(payload):
    boxes = {n[0]: (n[2], n[3], n[2] + n[4], n[3] + n[5]) for n in payload["nodes"]}
    segments = []
    for e in payload["edges"]:
        pts = list(zip(e[2][::2], e[2][1::2], strict=True))
        segments += [(e[0], e[1], p, q) for p, q in zip(pts, pts[1:], strict=False)]
    return boxes, segments


@pytest.mark.parametrize("direction", ["TD", "LR"])
def test_drawing_layout_is_clean(direction):
    text = (ROOT / "examples" / "dibujo" / "cajero.mmd").read_text(encoding="utf-8")
    text = text.replace("flowchart TD", f"flowchart {direction}")
    payload = drawing_payload(parse_mermaid(text), text)
    boxes, segments = _boxes_and_segments(payload)
    items = sorted(boxes.items())
    for i, (a, ra) in enumerate(items):
        for b, rb in items[i + 1 :]:
            assert not (ra[0] < rb[2] and ra[2] > rb[0] and ra[1] < rb[3] and ra[3] > rb[1]), (a, b)
    for src, dst, p, q in segments:
        assert p[0] == q[0] or p[1] == q[1], "tramo diagonal"  # ángulos rectos
        for nid, r in boxes.items():
            if nid in (src, dst):
                continue
            x1, x2 = sorted((p[0], q[0]))
            y1, y2 = sorted((p[1], q[1]))
            inside = x1 < r[2] - 1 and x2 > r[0] + 1 and y1 < r[3] - 1 and y2 > r[1] + 1
            assert not inside, f"{src}->{dst} cruza {nid}"
    assert payload["legend"][0] == "terminal"
    assert payload == drawing_payload(parse_mermaid(text), text)  # determinista


# --------------------------------------------------------------------------- CLI


@needs_grammars
def test_cli_mermaid_flow_and_sequence(capsys):
    target = str(ROOT / "examples" / "laravel-mini")
    assert cli.main(["mermaid", target, "FacturaController.store"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("---\ntitle: \"FacturaController.store\"")
    assert '[["Llama a emitir() → factura"]]' in out  # subproceso aunque esté en otro archivo
    assert cli.main(["mermaid", target, "FacturaController.store", "--secuencia"]) == 0
    assert "sequenceDiagram" in capsys.readouterr().out
    assert cli.main(["mermaid", target, "noexiste"]) == cli.EXIT_NOT_FOUND


def test_cli_draw(tmp_path, capsys):
    out = tmp_path / "c.html"
    src = ROOT / "examples" / "dibujo" / "cajero.mmd"
    assert cli.main(["dibujar", str(src), "-o", str(out)]) == cli.EXIT_OK
    page = out.read_text(encoding="utf-8")
    assert "<title>Cajero automático — Desglosa</title>" in page
    assert '"start":"#\\/dibujo"' in page
    assert "14 nodos, 16 flechas" in capsys.readouterr().out
    bad = tmp_path / "malo.mmd"
    bad.write_text("pie title Mascotas\n", encoding="utf-8")
    assert cli.main(["dibujar", str(bad), "-o", str(tmp_path / "x.html")]) == cli.EXIT_USAGE
    assert "No pude leer el diagrama" in capsys.readouterr().err
