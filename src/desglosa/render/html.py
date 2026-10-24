"""Ensambla el HTML único y autocontenido (SPEC §11.1).

- CSS y JS en línea, cero URLs externas.
- Datos en `<script type="application/json">`, serializados de forma determinista y
  escapados: `<`, `>`, `&`, U+2028, U+2029 y `/` se escriben como secuencias `\\uXXXX`
  o `\\/`. Así ningún texto del código analizado (p. ej. `</script>` o una URL en un
  comentario) aparece literal en el HTML.
"""

from __future__ import annotations

import html
import json
from importlib import resources
from typing import Any

from desglosa.ir import FlowGraph
from desglosa.layout.flow import FlowLayout


def safe_json(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
        .replace("/", "\\/")
    )


def _asset(name: str) -> str:
    return resources.files("desglosa.render").joinpath(name).read_text(encoding="utf-8")


def render_html(payload: dict, title: str) -> str:
    template = _asset("template.html")
    page = template.replace("{{TITLE}}", html.escape(title, quote=True))
    page = page.replace("/*{{STYLE}}*/", _asset("style.css"))
    page = page.replace("/*{{APP}}*/", _asset("app.js"))
    # Los datos van al final para que ningún reemplazo posterior pueda tocarlos.
    head, sep, tail = page.partition("{{DATA}}")
    if not sep:
        raise RuntimeError("la plantilla no tiene el marcador {{DATA}}")
    return head + safe_json(payload) + tail


def _flat(points: tuple[tuple[float, float], ...]) -> list[float]:
    out: list[float] = []
    for x, y in points:
        out.extend((x, y))
    return out


def flow_payload(graph: FlowGraph, layout: FlowLayout) -> dict:
    nodes = {
        n.id: {
            "kind": n.kind,
            "easy": n.text_easy,
            "tech": n.text_tech,
            "a": n.line_start,
            "b": n.line_end,
            "call": n.call_id,
            "target": n.target_symbol,
        }
        for n in graph.nodes
    }
    lay = {
        "w": layout.width,
        "h": layout.height,
        "columns": layout.columns,
        "nodes": [
            [b.id, b.x, b.y, b.w, b.h, list(b.lines_easy), list(b.lines_tech)] for b in layout.nodes
        ],
        "lines": [[_flat(ln.points), ln.kind, ln.arrow] for ln in layout.lines],
        "labels": [[lb.text, lb.x, lb.y, lb.w, lb.h] for lb in layout.labels],
        "connectors": [[c.label, c.x, c.y, c.r] for c in layout.connectors],
    }
    return {"truncated": graph.truncated, "nodes": nodes, "layout": lay}
