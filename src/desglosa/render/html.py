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

_ATOMS = (str, int, bool, type(None))


def _compact(obj: Any) -> Any:
    """`184.0` → `184`: las coordenadas enteras ocupan menos en el HTML.

    Los valores simples se resuelven en línea, sin una llamada por valor: con 200 000
    líneas de código hay ~9 millones de números y la versión recursiva tardaba 9 s.
    """
    t = type(obj)
    if t is float:
        return int(obj) if obj.is_integer() else obj
    if t is dict:
        return {
            k: (int(v) if v.is_integer() else v) if type(v) is float
            else v if type(v) in _ATOMS else _compact(v)
            for k, v in obj.items()
        }
    if t is list or t is tuple:
        return [
            (int(v) if v.is_integer() else v) if type(v) is float
            else v if type(v) in _ATOMS else _compact(v)
            for v in obj
        ]
    if isinstance(obj, float):  # subclases raras
        return int(obj) if obj.is_integer() else obj
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_compact(v) for v in obj]
    return obj


def safe_json(data: Any) -> str:
    text = json.dumps(_compact(data), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
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


FLOW_LEGEND_ORDER = (
    "terminal",
    "proceso",
    "subproceso",
    "decision",
    "es",
    "teclado",
    "pantalla",
    "documento",
    "externo",
    "conector",
    "excepcion",
)


def flow_legend(graph: FlowGraph, layout: FlowLayout) -> list[str]:
    """Leyenda con SOLO los tipos presentes en el diagrama (RF-D06)."""
    present = {n.kind for n in graph.nodes}
    if layout.connectors:
        present.add("conector")
    if any(ln.kind == "excepcion" for ln in layout.lines):
        present.add("excepcion")
    return [k for k in FLOW_LEGEND_ORDER if k in present]


def flow_payload(graph: FlowGraph, layout: FlowLayout) -> dict:
    # El texto fácil ya va en `layout.nodes` (partido en líneas); aquí solo lo que usa el
    # visor para el tooltip y el clic.
    nodes = {
        n.id: {
            "kind": n.kind,
            "tech": n.text_tech,
            "a": n.line_start,
            "b": n.line_end,
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
        "legend": flow_legend(graph, layout),
    }
    return {"truncated": graph.truncated, "nodes": nodes, "layout": lay}
