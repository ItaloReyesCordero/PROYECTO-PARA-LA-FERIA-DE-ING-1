"""Mermaid (Bloque 3): exportar diagramas y dibujar diagramas escritos a mano.

- `flow_to_mermaid` y `sequence_to_mermaid` convierten un diagrama de Desglosa en texto
  Mermaid (RF-18), para pegarlo en un README, un issue o una respuesta de un asistente.
- `parse_mermaid` lee un diagrama de flujo escrito a mano en Mermaid (`flowchart` o
  `graph`) y `drawing_payload` lo dibuja con el estilo de Desglosa (comando `dibujar`).

Formas del diagrama de flujo clásico ↔ Mermaid. Las tres últimas no tienen forma clásica
en Mermaid y usan la sintaxis `@{ shape: … }` (Mermaid 11.3 o más nuevo):

    terminal   ([texto])      subproceso [[texto]]     decision  {texto}
    proceso    [texto]        es         [/texto/]     conector  ((texto))
    pantalla   curv-trap      teclado    sl-rect       documento doc

Los textos van entre comillas y se escapan con los códigos de Mermaid (`#quot;`,
`#35;`, `#59;`…), así que ningún texto del código analizado cambia la estructura del
diagrama.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from desglosa.ir import FlowGraph, FlowNode
from desglosa.layout.flow import node_size
from desglosa.layout.layered import LEdge, LNode, layout_layered
from desglosa.layout.text import label_size
from desglosa.sequence import SequenceDiagram

# --------------------------------------------------------------------------- exportar

CLASSIC = {  # tipo → (abre, cierra)
    "terminal": ('(["', '"])'),
    "proceso": ('["', '"]'),
    "subproceso": ('[["', '"]]'),
    "decision": ('{"', '"}'),
    "es": ('[/"', '"/]'),
    "conector": ('(("', '"))'),
    "externo": ('["', '"]'),
}
NEW_SHAPES = {"pantalla": "curv-trap", "teclado": "sl-rect", "documento": "doc"}
# Colores del tema claro (SPEC §11.3): borde sólido y relleno al 15 % (sufijo 26).
CLASS_COLORS = {
    "terminal": "#059669",
    "proceso": "#2563eb",
    "subproceso": "#7c3aed",
    "decision": "#b45309",
    "es": "#0891b2",
    "teclado": "#0891b2",
    "pantalla": "#db2777",
    "documento": "#db2777",
    "externo": "#64748b",
    "conector": "#64748b",
}


_ENTITIES = {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", ";": "#59;", "|": "#124;",
             "{": "#123;", "}": "#125;"}
_TO_ESCAPE = re.compile(r'[#"<>;|{}]')


def escape(text: str) -> str:
    """Texto seguro dentro de comillas de Mermaid, en una sola línea. Una sola pasada:
    reemplazar uno por uno rompería los códigos ya puestos (el `;` de `#gt;`)."""
    text = " ".join(str(text).split())
    return _TO_ESCAPE.sub(lambda m: _ENTITIES[m.group(0)], text)


def node_line(nid: str, kind: str, text: str) -> str:
    label = escape(text)
    if kind in NEW_SHAPES:
        return f'{nid}@{{ shape: {NEW_SHAPES[kind]}, label: "{label}" }}'
    opener, closer = CLASSIC.get(kind, CLASSIC["proceso"])
    return f"{nid}{opener}{label}{closer}"


def class_lines(kinds_of: dict[str, str]) -> list[str]:
    """`classDef` de los tipos usados y `class n1,n2 tipo` para colorear como Desglosa."""
    out = []
    by_kind: dict[str, list[str]] = {}
    for nid, kind in kinds_of.items():
        if kind in CLASS_COLORS:
            by_kind.setdefault(kind, []).append(nid)
    for kind in sorted(by_kind):
        color = CLASS_COLORS[kind]
        dash = ",stroke-dasharray:4 3" if kind == "externo" else ""
        out.append(f"    classDef {kind} fill:{color}26,stroke:{color},stroke-width:2px{dash}")
    for kind in sorted(by_kind):
        out.append(f"    class {','.join(by_kind[kind])} {kind}")
    return out


def flow_to_mermaid(graph: FlowGraph, technical: bool = False, title: str | None = None) -> str:
    """Diagrama de flujo de una función en Mermaid (de arriba hacia abajo)."""
    out = []
    if title:
        out += ["---", f'title: "{escape(title)}"', "---"]
    out.append("flowchart TD")
    kinds: dict[str, str] = {}
    for n in graph.nodes:
        kinds[n.id] = n.kind
        out.append("    " + node_line(n.id, n.kind, n.text_tech if technical else n.text_easy))
    for e in graph.edges:
        arrow = "-.->" if e.kind == "excepcion" else "-->"
        label = f'|"{escape(e.label)}"|' if e.label else ""
        out.append(f"    {e.src} {arrow}{label} {e.dst}")
    out += class_lines(kinds)
    return "\n".join(out) + "\n"


# Fragmentos de la secuencia → bloques de Mermaid. Un hermano que sigue a su pareja (if →
# else, try → catch, caso → caso, impl → impl) se escribe como `else` del mismo bloque.
_OPEN = {"loop": "loop", "if": "alt", "else": "alt", "caso": "alt", "try": "alt",
         "catch": "alt", "impl": "alt"}
_FOLLOWS = {"else": ("if",), "catch": ("try", "catch"), "caso": ("caso",), "impl": ("impl",)}


def _frag_text(kind: str, label: str) -> str:
    if kind == "else":
        return "si no"
    if kind == "try":
        return "intentar"
    if kind == "catch":
        return f"excepción {label}".strip()
    return label


def sequence_to_mermaid(diagram: SequenceDiagram, title: str | None = None) -> str:
    """Diagrama de secuencia en Mermaid, con sus bucles y alternativas."""
    out = []
    if title:
        out += ["---", f'title: "{escape(title)}"', "---"]
    out.append("sequenceDiagram")
    alias = {p.id: f"P{i}" for i, p in enumerate(diagram.participants)}
    for p in diagram.participants:
        word = "actor" if p.kind == "actor" else "participant"
        out.append(f"    {word} {alias[p.id]} as {escape(p.label)}")
    frags = {f.id: f for f in diagram.fragments}
    stack: list[str] = []
    opened: dict[str, int] = {}  # fragmento → línea donde se abrió
    merged_ifs: set[str] = set()  # `if` que siguió con su `else`

    def indent() -> str:
        return "    " * (len(stack) + 1)

    for m in diagram.messages:
        chain = [f for f in m.fragments if f in frags]
        k = 0
        while k < len(stack) and k < len(chain) and stack[k] == chain[k]:
            k += 1
        merged = False
        if k < len(stack) and k < len(chain):
            old, new = frags[stack[k]], frags[chain[k]]
            if old.parent == new.parent and old.kind in _FOLLOWS.get(new.kind, ()):
                # Cerrar lo de adentro y seguir en el mismo bloque con `else`.
                while len(stack) > k + 1:
                    stack.pop()
                    out.append(indent() + "end")
                merged_ifs.add(old.id)
                stack[k] = new.id
                out.append("    " * (k + 1) + "else " + escape(_frag_text(new.kind, new.label)))
                k += 1
                merged = True
        if not merged:
            while len(stack) > k:
                stack.pop()
                out.append(indent() + "end")
        for fid in chain[k:]:
            f = frags[fid]
            word = _OPEN.get(f.kind, "opt")
            opened[fid] = len(out)
            out.append(indent() + f"{word} {escape(_frag_text(f.kind, f.label))}")
            stack.append(fid)
        text = f"{m.number}: {m.label}" if m.number else m.label
        if m.confidence not in ("exacta", "externa") and m.kind != "retorno":
            text += f" [{m.confidence}]"
        arrow = "-->>" if m.kind == "retorno" else "->>"
        out.append(f"{indent()}{alias[m.src]}{arrow}{alias[m.dst]}: {escape(text)}")
    while stack:
        stack.pop()
        out.append(indent() + "end")
    # Un `if` sin su `else` es un bloque opcional.
    for fid, i in opened.items():
        if frags[fid].kind == "if" and fid not in merged_ifs:
            out[i] = out[i].replace("alt ", "opt ", 1)
    if diagram.truncated:
        out.append("    Note over " + alias[diagram.participants[0].id] + ": (diagrama recortado)")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- leer


class MermaidError(ValueError):
    """El texto no es un diagrama de flujo de Mermaid que Desglosa sepa dibujar."""


@dataclass(frozen=True)
class DNode:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class DEdge:
    src: str
    dst: str
    label: str | None
    style: str  # normal | punteada | gruesa
    arrow: bool


@dataclass
class Drawing:
    direction: str  # TD | LR
    nodes: list[DNode] = field(default_factory=list)
    edges: list[DEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title: str | None = None


# Formas clásicas: (abre, cierres posibles, tipo). Primero las de dos caracteres.
_SHAPES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("([", ("])",), "terminal"),
    ("[[", ("]]",), "subproceso"),
    ("[(", (")]",), "es"),  # cilindro: datos guardados
    ("((", ("))",), "conector"),
    ("{{", ("}}",), "proceso"),  # hexágono: preparación
    ("[/", ("/]", "\\]"), "es"),  # [/x\] es un trapecio: se ajusta abajo
    ("[\\", ("\\]", "/]"), "documento"),
    ("[", ("]",), "proceso"),
    ("(", (")",), "terminal"),  # rectángulo redondeado: Inicio / Fin
    ("{", ("}",), "decision"),
    (">", ("]",), "pantalla"),
)
# Nombres de la sintaxis nueva `@{ shape: … }` (con sus alias) → tipo de Desglosa.
_NEW_SHAPES = {
    **dict.fromkeys(("stadium", "pill", "terminal", "rounded", "event"), "terminal"),
    **dict.fromkeys(("rect", "proc", "process", "rectangle", "hex", "hexagon", "prepare"),
                    "proceso"),
    **dict.fromkeys(("fr-rect", "framed-rectangle", "subproc", "subprocess", "subroutine"),
                    "subproceso"),
    **dict.fromkeys(("diam", "diamond", "decision", "question"), "decision"),
    **dict.fromkeys(("lean-r", "lean-right", "in-out", "lean-l", "lean-left", "out-in", "cyl",
                     "cylinder", "database", "db"), "es"),
    **dict.fromkeys(("sl-rect", "manual-input", "sloped-rectangle"), "teclado"),
    **dict.fromkeys(("curv-trap", "curved-trapezoid", "display"), "pantalla"),
    **dict.fromkeys(("doc", "document", "docs", "documents", "lin-doc"), "documento"),
    **dict.fromkeys(("circle", "circ", "sm-circ", "small-circle", "start", "fr-circ", "stop"),
                    "conector"),
}
_ID = re.compile(r"[^\W][\w.]*", re.UNICODE)
_PLAIN_LINK = re.compile(r"<?(-{2,}>|-{3,}|={2,}>|={3,}|-\.+->|-\.+-|--[xo]|==[xo])")
_TEXT_LINK = (("--", ("-->", "---")), ("==", ("==>", "===")), ("-.", (".->", ".-")))
_PIPE = re.compile(r"\s*\|([^|]*)\|")
_ENTITY = re.compile(r"#(\d+|quot|amp|lt|gt|nbsp);")
_IGNORED = ("classdef", "class", "style", "linkstyle", "click", "direction", "acctitle",
            "accdescr")
MAX_NODES = 500


def _decode(text: str) -> str:
    def entity(m: re.Match) -> str:
        code = m.group(1)
        named = {"quot": '"', "amp": "&", "lt": "<", "gt": ">", "nbsp": " "}
        if code in named:
            return named[code]
        n = int(code)
        return chr(n) if 0 < n < 0x110000 else ""

    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = _ENTITY.sub(entity, text)
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "`":  # cadena "markdown" de Mermaid
        text = text[1:-1]
    return " ".join(text.split())


def _split_statements(line: str) -> list[str]:
    """Separa por `;` fuera de comillas y corchetes."""
    out, cur, depth, quote = [], [], 0, False
    for ch in line:
        if ch == '"':
            quote = not quote
        elif not quote and ch in "[({":
            depth += 1
        elif not quote and ch in "])}" and depth:
            depth -= 1
        if ch == ";" and not quote and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return [s for s in (x.strip() for x in out) if s]


class _Parser:
    def __init__(self, drawing: Drawing) -> None:
        self.d = drawing
        self.index: dict[str, int] = {}

    def node(self, nid: str, kind: str | None, text: str | None) -> None:
        if nid not in self.index:
            if len(self.index) >= MAX_NODES:
                raise MermaidError(f"El diagrama tiene más de {MAX_NODES} nodos.")
            self.index[nid] = len(self.d.nodes)
            self.d.nodes.append(DNode(nid, kind or "proceso", text if text is not None else nid))
        elif kind is not None or text is not None:
            old = self.d.nodes[self.index[nid]]
            self.d.nodes[self.index[nid]] = DNode(
                nid, kind or old.kind, text if text is not None else old.text
            )

    def statement(self, s: str, line_no: int) -> None:
        self.s, self.pos, self.line_no = s, 0, line_no
        group = self.node_group()
        while True:
            self.skip()
            if self.pos >= len(self.s):
                return
            style, arrow, label = self.link()
            nxt = self.node_group()
            for a in group:
                for b in nxt:
                    if a == b:
                        self.d.warnings.append(
                            f"Línea {line_no}: se omitió la flecha de {a} a sí mismo."
                        )
                        continue
                    self.d.edges.append(DEdge(a, b, label, style, arrow))
            group = nxt

    def fail(self, what: str) -> MermaidError:
        near = self.s[self.pos : self.pos + 25]
        return MermaidError(f"Línea {self.line_no}: {what} cerca de «{near}».")

    def skip(self) -> None:
        while self.pos < len(self.s) and self.s[self.pos].isspace():
            self.pos += 1

    def node_group(self) -> list[str]:
        ids = [self.one_node()]
        while True:
            self.skip()
            if self.pos < len(self.s) and self.s[self.pos] == "&":
                self.pos += 1
                ids.append(self.one_node())
            else:
                return ids

    def one_node(self) -> str:
        self.skip()
        m = _ID.match(self.s, self.pos)
        if not m:
            raise self.fail("falta el nombre de un nodo")
        nid = m.group(0)
        self.pos = m.end()
        if self.s.startswith("@{", self.pos):
            kind, text = self.new_shape()
            self.node(nid, kind, text)
            return nid
        for opener, closers, kind in _SHAPES:
            if self.s.startswith(opener, self.pos):
                text, closer = self.shape_text(opener, closers)
                if opener == "[/" and closer == "\\]":
                    kind = "teclado"  # trapecio: entrada manual
                self.node(nid, kind, text)
                return nid
        self.node(nid, None, None)
        return nid

    def shape_text(self, opener: str, closers: tuple[str, ...]) -> tuple[str, str]:
        start = self.pos + len(opener)
        rest = self.s[start:]
        stripped = rest.lstrip()
        if stripped.startswith('"'):
            q0 = start + len(rest) - len(stripped)
            q1 = self.s.find('"', q0 + 1)
            if q1 < 0:
                raise self.fail("faltan las comillas de cierre")
            text = self.s[q0 + 1 : q1]
            after = q1 + 1
            while after < len(self.s) and self.s[after].isspace():
                after += 1
            for closer in closers:
                if self.s.startswith(closer, after):
                    self.pos = after + len(closer)
                    return _decode(text), closer
            raise self.fail(f"falta cerrar «{opener}»")
        best = None
        for closer in closers:
            i = self.s.find(closer, start)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, closer)
        if best is None:
            raise self.fail(f"falta cerrar «{opener}»")
        self.pos = best[0] + len(best[1])
        return _decode(self.s[start : best[0]]), best[1]

    def new_shape(self) -> tuple[str | None, str | None]:
        end, quote = -1, False
        for i in range(self.pos + 2, len(self.s)):  # la llave de cierre, fuera de comillas
            if self.s[i] == '"':
                quote = not quote
            elif self.s[i] == "}" and not quote:
                end = i
                break
        if end < 0:
            raise self.fail("falta cerrar «@{»")
        body = self.s[self.pos + 2 : end]
        self.pos = end + 1
        props = {}
        for m in re.finditer(r'(\w+)\s*:\s*("([^"]*)"|[^,]*)', body):
            props[m.group(1).lower()] = m.group(3) if m.group(3) is not None else m.group(2).strip()
        shape = props.get("shape", "").lower()
        kind = _NEW_SHAPES.get(shape)
        if shape and kind is None:
            self.d.warnings.append(f"Línea {self.line_no}: forma «{shape}» dibujada como proceso.")
            kind = "proceso"
        text = _decode(props["label"]) if "label" in props else None
        return kind, text

    def link(self) -> tuple[str, bool, str | None]:
        self.skip()
        m = _PLAIN_LINK.match(self.s, self.pos)
        if m:
            token = m.group(0)
            self.pos = m.end()
            label = None
            p = _PIPE.match(self.s, self.pos)
            if p:
                label = _decode(p.group(1).strip().strip('"')) or None
                self.pos = p.end()
            return _style(token), token[-1] in ">xo", label
        for start, ends in _TEXT_LINK:
            if self.s.startswith(start, self.pos):
                body_start = self.pos + len(start)
                best = None
                for end in ends:
                    i = self.s.find(end, body_start)
                    if i >= 0 and (best is None or i < best[0]):
                        best = (i, end)
                if best is None:
                    break
                text = self.s[body_start : best[0]].strip()
                self.pos = best[0] + len(best[1])
                token = start + best[1]
                return _style(token), best[1][-1] in ">", _decode(text.strip('"')) or None
        raise self.fail("no entiendo la flecha")


def _style(token: str) -> str:
    if "=" in token:
        return "gruesa"
    if "." in token:
        return "punteada"
    return "normal"


def parse_mermaid(text: str) -> Drawing:
    """Lee un diagrama de flujo de Mermaid (subconjunto: nodos, formas, flechas, etiquetas)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = None
    # Encabezado YAML opcional (---\ntitle: …\n---).
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)  # tras líneas en blanco
    if first is not None and lines[first].strip() == "---":
        for i in range(first + 1, len(lines)):
            if lines[i].strip() == "---":
                for meta in lines[first + 1 : i]:
                    if meta.strip().lower().startswith("title:"):
                        title = _decode(meta.split(":", 1)[1].strip().strip('"'))
                lines = [""] * (i + 1) + lines[i + 1 :]
                break
    drawing: Drawing | None = None
    parser: _Parser | None = None
    ignored: set[str] = set()
    for line_no, raw in enumerate(lines, start=1):
        if raw.strip().startswith("%%"):
            continue
        for st in _split_statements(raw):
            low = st.lower()
            if drawing is None:
                m = re.fullmatch(r"(flowchart|graph)(?:\s+(TB|TD|BT|RL|LR))?", st, re.I)
                if not m:
                    kind = st.split()[0]
                    raise MermaidError(
                        f"Línea {line_no}: Desglosa dibuja diagramas de flujo de Mermaid "
                        f"(«flowchart TD» o «graph TD»), no «{kind}»."
                    )
                direction = (m.group(2) or "TD").upper()
                if direction in ("BT", "RL"):
                    drawing = Drawing("TD" if direction == "BT" else "LR", title=title)
                    drawing.warnings.append(f"La dirección {direction} se dibuja como "
                                            f"{drawing.direction}.")
                else:
                    drawing = Drawing("LR" if direction == "LR" else "TD", title=title)
                parser = _Parser(drawing)
                continue
            word = low.split()[0]
            if word in _IGNORED:
                ignored.add(word)
                continue
            if word in ("subgraph", "end"):
                ignored.add("subgraph")
                continue
            parser.statement(st, line_no)
    if drawing is None:
        raise MermaidError("El texto está vacío: empieza con «flowchart TD».")
    if not drawing.nodes:
        raise MermaidError("El diagrama no tiene nodos.")
    if "subgraph" in ignored:
        drawing.warnings.append("Los subgrafos se dibujan sin su recuadro.")
    others = sorted(ignored - {"subgraph"})
    if others:
        drawing.warnings.append("Se ignoró (estilos y clics): " + ", ".join(others) + ".")
    return drawing


# --------------------------------------------------------------------------- dibujar

DRAW_LEGEND_ORDER = ("terminal", "proceso", "subproceso", "decision", "es", "teclado",
                     "pantalla", "documento", "conector")
DRAW_LAYER_GAP = 64.0  # entre filas (o columnas): un diagrama de flujo va más junto que el mapa


def orthogonal(points: list[tuple[float, float]], td: bool) -> list[tuple[float, float]]:
    """Cambia cada tramo diagonal por tramos rectos que doblan a mitad de camino. Los
    tramos diagonales solo cruzan el hueco entre filas (o columnas), donde no hay cajas."""
    out = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        if x1 != x2 and y1 != y2:
            if td:
                mid = round((y1 + y2) / 2, 1)
                out += [(x1, mid), (x2, mid)]
            else:
                mid = round((x1 + x2) / 2, 1)
                out += [(mid, y1), (mid, y2)]
        out.append((x2, y2))
    return out


def drawing_payload(drawing: Drawing, source: str) -> dict:
    """Coordenadas del diagrama dibujado. De arriba hacia abajo (TD) se usa el layout por
    capas girado: las capas pasan a ser filas."""
    td = drawing.direction == "TD"
    sizes = {}
    for n in drawing.nodes:
        w, h, lines, _ = node_size(FlowNode(n.id, n.kind, n.text, n.text, 0, 0))
        if n.kind == "conector":
            w = h = max(w, h, 36.0)
        sizes[n.id] = (w, h, lines)
    order = {n.id: i for i, n in enumerate(drawing.nodes)}
    lnodes = [
        LNode(nid, h if td else w, w if td else h, f"{order[nid]:05d}")
        for nid, (w, h, _) in sizes.items()
    ]
    lay = layout_layered(
        lnodes, [LEdge(e.src, e.dst) for e in drawing.edges], layer_gap=DRAW_LAYER_GAP
    )

    def pt(x: float, y: float) -> tuple[float, float]:
        return (y, x) if td else (x, y)

    nodes_out = []
    for n in drawing.nodes:
        p = lay.nodes[n.id]
        w, h, lines = sizes[n.id]
        x, y = pt(p.x, p.y)
        nodes_out.append([n.id, n.kind, x, y, w, h, lines])
    placed = {(e.src, e.dst): e for e in lay.edges}
    edges_out = []
    for e in drawing.edges:
        pe = placed.get((e.src, e.dst))
        if pe is None:
            continue
        pts = orthogonal([pt(x, y) for x, y in pe.points], td)
        flat = [round(v, 1) for xy in pts for v in xy]
        box = [0, 0, 0, 0]
        if e.label:
            lw, lh = label_size(e.label)
            seg = max(zip(pts, pts[1:], strict=False),
                      key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
            mx, my = (seg[0][0] + seg[1][0]) / 2, (seg[0][1] + seg[1][1]) / 2
            box = [round(mx - lw / 2, 1), round(my - lh / 2, 1), round(lw, 1), round(lh, 1)]
        edges_out.append([e.src, e.dst, flat, e.style, e.arrow, e.label, *box])
    width, height = (lay.height, lay.width) if td else (lay.width, lay.height)
    kinds = {n.kind for n in drawing.nodes}
    return {
        "title": drawing.title,
        "direction": drawing.direction,
        "w": width,
        "h": height,
        "nodes": nodes_out,
        "edges": edges_out,
        "legend": [k for k in DRAW_LEGEND_ORDER if k in kinds],
        "warnings": drawing.warnings,
        "source": source,
    }
