"""Layout estructurado del diagrama de flujo (SPEC §7.4).

No es un algoritmo genérico de grafos: cada construcción (secuencia, if, bucle, switch,
try) devuelve una caja con un eje vertical común; la entrada está arriba y la salida abajo,
sobre el mismo eje. Así las secuencias quedan en línea recta, la rama "sí" va hacia abajo
y la "no" hacia la derecha, y el retorno de los bucles usa un carril lateral izquierdo.

Los saltos (`break`, `continue`, `throw` hacia su `catch`) se enrutan al final, ya con las
posiciones absolutas: se busca un camino ortogonal hasta el carril destino que no atraviese
ningún nodo; si no existe, se dibuja un par de conectores con la misma letra.

Si el diagrama supera `max_height`, la secuencia de nivel superior se corta en columnas
unidas por conectores numerados ("1", "2"…), como en los diagramas hechos a mano.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desglosa.flow import SDoWhile, SIf, SJump, SLoop, SNode, SSeq, SSwitch, STry
from desglosa.ir import FlowGraph, FlowNode
from desglosa.layout.text import (
    LINE_H,
    WRAP_EASY,
    WRAP_TECH,
    label_size,
    text_height,
    text_width,
    wrap,
)

GAP = 30  # separación vertical entre bloques
GAP_X = 40  # separación horizontal entre ramas
LANE = 26  # ancho de los carriles laterales de los bucles
CONN_R = 11  # radio de los conectores
CONN_SPACE = 2 * CONN_R + 10
COL_GAP = 90
MARGIN = 24
LABEL_SPACE = 28
PAD_X = 12
PAD_Y = 8
MIN_W = 96
MIN_H = 34


@dataclass(frozen=True)
class NodeBox:
    id: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    lines_easy: tuple[str, ...]
    lines_tech: tuple[str, ...]


@dataclass(frozen=True)
class Line:
    points: tuple[tuple[float, float], ...]
    kind: str = "normal"  # normal | retorno_bucle | excepcion | salto
    arrow: bool = True


@dataclass(frozen=True)
class Label:
    text: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Connector:
    label: str
    x: float  # centro
    y: float
    r: float


@dataclass(frozen=True)
class FlowLayout:
    symbol_id: str
    width: float
    height: float
    nodes: tuple[NodeBox, ...]
    lines: tuple[Line, ...]
    labels: tuple[Label, ...]
    connectors: tuple[Connector, ...]
    columns: int


# --------------------------------------------------------------------------- piezas internas


@dataclass
class _Esc:
    x: float
    y: float
    direction: str  # down | left | right
    kind: str
    sid: int
    idx: int


@dataclass
class _Target:
    x: float
    y1: float
    y2: float
    tail: tuple[tuple[float, float], ...] = ()
    tail_arrow: bool = False
    conn_x: float = 0.0
    conn_y: float = 0.0
    side: int = 1  # -1: el conector de reserva va a la izquierda del carril


@dataclass
class _Block:
    w: float = 0.0
    h: float = 0.0
    ax: float = 0.0
    entry_node: bool = True
    exits: bool = True
    empty: bool = False
    pure_jump: SJump | None = None
    nodes: list[NodeBox] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    connectors: list[Connector] = field(default_factory=list)
    escapes: list[_Esc] = field(default_factory=list)
    targets: dict[tuple[str, int, int], _Target] = field(default_factory=dict)
    entry_id: str | None = None  # nodo de entrada/salida si el bloque es una hoja
    exit_id: str | None = None

    def place(self, child: _Block, dx: float, dy: float) -> None:
        for n in child.nodes:
            self.nodes.append(
                NodeBox(n.id, n.kind, n.x + dx, n.y + dy, n.w, n.h, n.lines_easy, n.lines_tech)
            )
        for ln in child.lines:
            self.lines.append(
                Line(tuple((x + dx, y + dy) for x, y in ln.points), ln.kind, ln.arrow)
            )
        for lb in child.labels:
            self.labels.append(Label(lb.text, lb.x + dx, lb.y + dy, lb.w, lb.h))
        for c in child.connectors:
            self.connectors.append(Connector(c.label, c.x + dx, c.y + dy, c.r))
        for e in child.escapes:
            self.escapes.append(_Esc(e.x + dx, e.y + dy, e.direction, e.kind, e.sid, e.idx))
        for key, t in child.targets.items():
            self.targets[key] = _Target(
                t.x + dx,
                t.y1 + dy,
                t.y2 + dy,
                tuple((x + dx, y + dy) for x, y in t.tail),
                t.tail_arrow,
                t.conn_x + dx,
                t.conn_y + dy,
                t.side,
            )

    def line(
        self, pts: list[tuple[float, float]], kind: str = "normal", arrow: bool = True
    ) -> None:
        clean: list[tuple[float, float]] = []
        for p in pts:
            if not clean or clean[-1] != p:
                clean.append(p)
        if len(clean) >= 2:
            self.lines.append(Line(tuple(clean), kind, arrow))

    def label(self, text: str, x: float, y: float, where: str) -> None:
        """where: below-start | above-start | above-end."""
        w, h = label_size(text)
        if where == "below-start":
            box = (x + 3, y + 2)
        elif where == "above-start":
            box = (x + 3, y - h - 2)
        else:  # above-end
            box = (x - w - 3, y - h - 2)
        self.labels.append(Label(text, box[0], box[1], w, h))


def _escapes_of(block: _Block, kind: str, sid: int) -> bool:
    return any(e.kind == kind and e.sid == sid for e in block.escapes)


# --------------------------------------------------------------------------- tamaños


def node_size(node: FlowNode) -> tuple[float, float, list[str], list[str]]:
    easy = wrap(node.text_easy, WRAP_EASY)
    tech = wrap(node.text_tech, WRAP_TECH)
    tw = max(text_width(easy), text_width(tech))
    th = max(text_height(easy), text_height(tech))
    kind = node.kind
    if kind == "decision":
        h = th + 2 * PAD_Y + 28
        w = tw / (1 - th / h) + 24
        w, h = max(w, 120), max(h, 60)
    else:
        w = tw + 2 * PAD_X
        h = th + 2 * PAD_Y
        if kind == "terminal":
            w += h * 0.5
        elif kind == "subproceso":
            w += 16
        elif kind == "es":
            w += 24
        elif kind == "pantalla":
            w += 30
        elif kind in ("teclado", "documento"):
            h += 10
        w, h = max(w, MIN_W), max(h, MIN_H)
    # Enteros pares: el eje queda en un píxel exacto.
    w = float(int(w + 1) // 2 * 2)
    h = float(int(h + 1) // 2 * 2)
    return w, h, easy, tech


# --------------------------------------------------------------------------- layout


class _Layout:
    def __init__(self, graph: FlowGraph) -> None:
        self.sizes = {n.id: node_size(n) for n in graph.nodes}
        self.kinds = {n.id: n.kind for n in graph.nodes}
        self.edge_kind = {(e.src, e.dst): e.kind for e in graph.edges}

    def box(self, nid: str, x: float, y: float) -> NodeBox:
        w, h, easy, tech = self.sizes[nid]
        return NodeBox(nid, self.kinds[nid], x, y, w, h, tuple(easy), tuple(tech))

    # ---------------------------------------------------------------- piezas

    def leaf(self, nid: str, stop: bool = False) -> _Block:
        w, h, _, _ = self.sizes[nid]
        b = _Block(w=w, h=h, ax=w / 2, entry_node=True, exits=not stop)
        b.nodes.append(self.box(nid, 0, 0))
        b.entry_id = b.exit_id = nid
        return b

    def any(self, item) -> _Block:
        if isinstance(item, SNode):
            return self.leaf(item.node_id, item.stop)
        if isinstance(item, SSeq):
            return self.seq(item)
        if isinstance(item, SIf):
            return self.if_(item)
        if isinstance(item, SLoop):
            return self.loop(item)
        if isinstance(item, SDoWhile):
            return self.do_while(item)
        if isinstance(item, SSwitch):
            return self.switch(item)
        if isinstance(item, STry):
            return self.try_(item)
        raise TypeError(f"estructura desconocida: {type(item).__name__}")

    def seq(self, seq: SSeq | None) -> _Block:
        items = seq.items if seq is not None else []
        if not items:
            return _Block(empty=True, entry_node=False)
        if len(items) == 1 and isinstance(items[0], SJump):
            return _Block(empty=True, exits=False, entry_node=False, pure_jump=items[0])
        parts = [it if isinstance(it, SJump) else self.any(it) for it in items]
        return self.stack(parts)

    def stack(self, parts: list) -> _Block:
        """Apila bloques sobre un eje común y los une con líneas verticales."""
        blocks = [p for p in parts if isinstance(p, _Block)]
        left = max((b.ax for b in blocks), default=0.0)
        right = max((b.w - b.ax for b in blocks), default=0.0)
        out = _Block(w=left + right, ax=left)
        y = 0.0
        prev_exit: float | None = 0.0
        prev_id: str | None = None
        started = False
        for p in parts:
            if isinstance(p, SJump):
                if prev_exit is not None:
                    out.escapes.append(
                        _Esc(left, prev_exit, "down", p.kind, p.target, p.catch_index)
                    )
                prev_exit = None
                continue
            if started:
                y += GAP
            out.place(p, left - p.ax, y)
            if started and prev_exit is not None:
                kind = "normal"
                if prev_id and self.edge_kind.get((prev_id, p.entry_id)) == "excepcion":
                    kind = "excepcion"
                out.line([(left, prev_exit), (left, y)], kind=kind, arrow=p.entry_node)
            if not started:
                out.entry_node = p.entry_node
                out.entry_id = p.entry_id
                started = True
            prev_exit = y + p.h if p.exits else None
            prev_id = p.exit_id
            y += p.h
        out.h = y
        out.exits = prev_exit is not None
        return out

    # ---------------------------------------------------------------- if

    @staticmethod
    def _chain(s: SIf) -> tuple[list[tuple[str, SSeq]], SSeq | None] | None:
        """if / else if / else if … → [(decisión, rama sí)], rama final (o None)."""
        steps = [(s.dec, s.yes)]
        cur = s.no
        while cur is not None and len(cur.items) == 1 and isinstance(cur.items[0], SIf):
            nxt = cur.items[0]
            steps.append((nxt.dec, nxt.yes))
            cur = nxt.no
        if len(steps) < 2:
            return None
        return steps, cur

    def ladder(self, steps: list[tuple[str, SSeq]], final: SSeq | None) -> _Block:
        """Escalera: rombos apilados por el "no" y cada rama "sí" a la derecha."""
        decs = [(dec, self.sizes[dec][0], self.sizes[dec][1]) for dec, _ in steps]
        branches = [self.seq(yes) for _, yes in steps]
        fin = self.seq(final) if final is not None else None
        fin_solid = fin is not None and not fin.empty
        half = max(dw / 2 for _, dw, _ in decs)
        x = max(half, fin.ax if fin_solid else 0.0)
        cont_left = any(
            b.pure_jump is not None and b.pure_jump.kind == "continue" for b in branches
        )
        if cont_left:
            x = max(x, half + LABEL_SPACE)
        col_x0 = x + half + GAP_X
        col_right = max(
            [col_x0 + (b.w if not b.empty else 24.0) for b in branches] + [x + half + LABEL_SPACE]
        )
        x_lane = col_right + LANE / 2
        out = _Block(ax=x, entry_node=True)
        y = 0.0
        lane_top: float | None = None
        any_exit = False
        bottoms: list[float] = []
        for i, ((dec, dw, dh), b) in enumerate(zip(decs, branches, strict=True)):
            out.nodes.append(self.box(dec, x - dw / 2, y))
            yc = y + dh / 2
            branch_bottom = y + dh
            if not b.empty:
                axis = col_x0 + b.ax
                top = yc + GAP / 2
                out.line([(x + dw / 2, yc), (axis, yc), (axis, top)], arrow=b.entry_node)
                out.label("sí", x + dw / 2, yc, "above-start")
                out.place(b, axis - b.ax, top)
                branch_bottom = top + b.h
                if b.exits:
                    ye = branch_bottom + GAP / 3
                    out.line([(axis, branch_bottom), (axis, ye), (x_lane, ye)], arrow=False)
                    lane_top = ye if lane_top is None else min(lane_top, ye)
                    any_exit = True
            elif b.pure_jump is not None:
                j = b.pure_jump
                if j.kind == "continue":
                    out.escapes.append(
                        _Esc(x - dw / 2, yc, "left", j.kind, j.target, j.catch_index)
                    )
                    out.label("sí", x - dw / 2, yc, "above-end")
                else:
                    out.escapes.append(
                        _Esc(x + dw / 2, yc, "right", j.kind, j.target, j.catch_index)
                    )
                    out.label("sí", x + dw / 2, yc, "above-start")
            else:
                out.line([(x + dw / 2, yc), (x_lane, yc)], arrow=False)
                out.label("sí", x + dw / 2, yc, "above-start")
                lane_top = yc if lane_top is None else min(lane_top, yc)
                any_exit = True
            bottoms.append(branch_bottom)
            out.label("no", x, y + dh, "below-start")
            if i < len(decs) - 1:
                y_next = max(y + dh + GAP, branch_bottom + GAP)
                out.line([(x, y + dh), (x, y_next)], arrow=True)
                y = y_next
            else:
                y = y + dh
        last_bottom = y
        no_exit = True
        no_bottom = last_bottom
        if fin_solid:
            top = last_bottom + GAP
            out.line([(x, last_bottom), (x, top)], arrow=fin.entry_node)
            out.place(fin, x - fin.ax, top)
            no_bottom = top + fin.h
            no_exit = fin.exits
        elif fin is not None and fin.pure_jump is not None:
            j = fin.pure_jump
            out.escapes.append(_Esc(x, last_bottom, "down", j.kind, j.target, j.catch_index))
            no_exit = False
        if any_exit or no_exit:
            y_join = max([*bottoms, no_bottom]) + GAP / 2
            if no_exit:
                out.line([(x, no_bottom), (x, y_join)], arrow=False)
            if any_exit and lane_top is not None:
                out.line([(x_lane, lane_top), (x_lane, y_join), (x, y_join)], arrow=False)
            out.h = y_join
            out.exits = True
        else:
            out.h = max([*bottoms, no_bottom])
            out.exits = False
        out.w = x_lane + 6
        return out

    def if_(self, s: SIf) -> _Block:
        chain = self._chain(s)
        if chain is not None:
            return self.ladder(*chain)
        dw, dh = self.sizes[s.dec][0], self.sizes[s.dec][1]
        yes = self.seq(s.yes)
        no = self.seq(s.no) if s.no is not None else None
        flipped = False
        if (
            yes.pure_jump is not None
            and not (no is not None and no.pure_jump is not None)
            or not yes.exits
            and not yes.empty
            and (no is None or no.empty or no.exits)
        ):
            flipped = True
        if flipped:
            down, down_label, side, side_label = no, "no", yes, "sí"
        else:
            down, down_label, side, side_label = yes, "sí", no, "no"

        down_block = down if down is not None and not down.empty else None
        down_jump = down.pure_jump if down is not None else None
        side_block = side if side is not None and not side.empty else None
        side_jump = side.pure_jump if side is not None else None
        side_left = side_jump is not None and side_jump.kind == "continue"

        left = max(dw / 2, down_block.ax if down_block else 0.0)
        if side_left:
            left = max(left, dw / 2 + LABEL_SPACE)
        x = left
        out = _Block(ax=x, entry_node=True)
        out.nodes.append(self.box(s.dec, x - dw / 2, 0))
        y_top = dh + GAP
        right_down = max(dw / 2, (down_block.w - down_block.ax) if down_block else 0.0)

        out.label(down_label, x, dh, "below-start")
        d_bottom = dh
        d_exit = True
        if down_block:
            out.place(down_block, x - down_block.ax, y_top)
            out.line([(x, dh), (x, y_top)], arrow=down_block.entry_node)
            d_bottom = y_top + down_block.h
            d_exit = down_block.exits
        elif down_jump is not None:
            out.escapes.append(
                _Esc(x, dh, "down", down_jump.kind, down_jump.target, down_jump.catch_index)
            )
            d_exit = False

        right = right_down
        s_exit = False
        s_bottom = 0.0
        xs = x
        side_open = False
        if side_block:
            xs = x + right_down + GAP_X + side_block.ax
            out.line([(x + dw / 2, dh / 2), (xs, dh / 2), (xs, y_top)], arrow=side_block.entry_node)
            out.label(side_label, x + dw / 2, dh / 2, "above-start")
            out.place(side_block, xs - side_block.ax, y_top)
            s_bottom = y_top + side_block.h
            s_exit = side_block.exits
            right = xs - x + (side_block.w - side_block.ax)
        elif side_jump is not None:
            if side_left:
                out.escapes.append(
                    _Esc(
                        x - dw / 2,
                        dh / 2,
                        "left",
                        side_jump.kind,
                        side_jump.target,
                        side_jump.catch_index,
                    )
                )
                out.label(side_label, x - dw / 2, dh / 2, "above-end")
            else:
                out.escapes.append(
                    _Esc(
                        x + dw / 2,
                        dh / 2,
                        "right",
                        side_jump.kind,
                        side_jump.target,
                        side_jump.catch_index,
                    )
                )
                out.label(side_label, x + dw / 2, dh / 2, "above-start")
                right = max(right, dw / 2 + LABEL_SPACE)
        else:
            xs = x + right_down + GAP_X / 2
            side_open = True
            s_exit = True
            s_bottom = dh / 2
            out.label(side_label, x + dw / 2, dh / 2, "above-start")
            right = max(right, xs - x + 6, dw / 2 + LABEL_SPACE)

        if d_exit or s_exit:
            y_join = max(d_bottom, s_bottom, dh) + GAP / 2
            if d_exit:
                out.line([(x, d_bottom), (x, y_join)], arrow=False)
            if s_exit and side_open:
                out.line(
                    [(x + dw / 2, dh / 2), (xs, dh / 2), (xs, y_join), (x, y_join)], arrow=False
                )
            elif s_exit:
                out.line([(xs, s_bottom), (xs, y_join), (x, y_join)], arrow=False)
            out.h = y_join
            out.exits = True
        else:
            out.h = max(d_bottom, s_bottom)
            out.exits = False
        out.w = x + right
        return out

    # ---------------------------------------------------------------- bucles

    def loop(self, s: SLoop) -> _Block:
        dw, dh = self.sizes[s.dec][0], self.sizes[s.dec][1]
        body = self.seq(s.body)
        init = self.sizes[s.init] if s.init else None
        upd = self.sizes[s.update] if s.update else None
        breaks = _escapes_of(body, "break", s.sid)
        conts = _escapes_of(body, "continue", s.sid)
        bb = body if not body.empty else None

        left = max(
            dw / 2, bb.ax if bb else 0.0, init[0] / 2 if init else 0.0, upd[0] / 2 if upd else 0.0
        )
        right = max(
            dw / 2 + LABEL_SPACE,
            (bb.w - bb.ax) if bb else 0.0,
            init[0] / 2 if init else 0.0,
            upd[0] / 2 if upd else 0.0,
        )
        conn_left = CONN_SPACE if conts else 0.0
        inner = LANE / 2 if (conts and upd) else 0.0
        x_lane_l = conn_left + 4
        x_lane_c = x_lane_l + LANE / 2
        x = x_lane_l + LANE + inner + left
        x_lane_r = x + right + LANE

        out = _Block(ax=x)
        if init:
            out.nodes.append(self.box(s.init, x - init[0] / 2, 0))
            out.entry_node = True
            seg_start = init[1]
        else:
            out.entry_node = False
            seg_start = 0.0
        y_c = seg_start + GAP
        y_m = seg_start + GAP / 2
        out.line([(x, seg_start), (x, y_c)], arrow=True)
        out.nodes.append(self.box(s.dec, x - dw / 2, y_c))
        y_b = y_c + dh + GAP
        out.label("sí", x, y_c + dh, "below-start")
        if bb:
            out.line([(x, y_c + dh), (x, y_b)], arrow=bb.entry_node)
            out.place(bb, x - bb.ax, y_b)
            body_exit = y_b + bb.h if bb.exits else None
            y_after = y_b + bb.h
        else:
            y_after = y_c + dh
            body_exit = None
            if body.pure_jump is not None:
                j = body.pure_jump
                out.escapes.append(_Esc(x, y_c + dh, "down", j.kind, j.target, j.catch_index))
            else:
                body_exit = y_c + dh

        y_mid_bu = y_after + GAP / 2
        y_u = y_after + GAP
        back_from = body_exit
        if upd:
            if body_exit is not None:
                out.line([(x, body_exit), (x, y_u)], arrow=True)
            out.nodes.append(self.box(s.update, x - upd[0] / 2, y_u))
            y_after = y_u + upd[1]
            back_from = y_after if (body_exit is not None or conts) else None
        y_back = y_after + GAP / 2
        if back_from is not None:
            out.line(
                [(x, back_from), (x, y_back), (x_lane_l, y_back), (x_lane_l, y_m), (x, y_m)],
                kind="retorno_bucle",
                arrow=False,
            )
        elif conts:
            out.line(
                [(x_lane_l, y_back), (x_lane_l, y_m), (x, y_m)], kind="retorno_bucle", arrow=False
            )
        y_exit = y_back + GAP / 2
        out.line(
            [(x + dw / 2, y_c + dh / 2), (x_lane_r, y_c + dh / 2), (x_lane_r, y_exit), (x, y_exit)],
            arrow=False,
        )
        out.label("no", x + dw / 2, y_c + dh / 2, "above-start")
        out.h = y_exit
        out.exits = True
        out.targets[("break", s.sid, 0)] = _Target(
            x_lane_r,
            y_c + dh / 2,
            y_exit,
            conn_x=x_lane_r + 6 + CONN_R,
            conn_y=y_c + dh / 2 + CONN_R + 8,
            side=1,
        )
        if upd:
            tail = ((x, y_mid_bu),) + (((x, y_u),) if body_exit is None else ())
            out.targets[("continue", s.sid, 0)] = _Target(
                x_lane_c,
                y_b,
                y_mid_bu,
                tail,
                body_exit is None,
                conn_x=x_lane_l - 6 - CONN_R,
                conn_y=y_b + CONN_R + 4,
                side=-1,
            )
        else:
            out.targets[("continue", s.sid, 0)] = _Target(
                x_lane_l,
                y_m,
                y_back,
                conn_x=x_lane_l - 6 - CONN_R,
                conn_y=y_m + CONN_R + 6,
                side=-1,
            )
        out.w = x_lane_r + (CONN_SPACE + 6 if breaks else 6)
        return out

    def do_while(self, s: SDoWhile) -> _Block:
        dw, dh = self.sizes[s.dec][0], self.sizes[s.dec][1]
        body = self.seq(s.body)
        breaks = _escapes_of(body, "break", s.sid)
        conts = _escapes_of(body, "continue", s.sid)
        bb = body if not body.empty else None
        left = max(dw / 2, bb.ax if bb else 0.0)
        right = max(dw / 2, (bb.w - bb.ax) if bb else 0.0)
        conn_left = CONN_SPACE if conts else 0.0
        inner = LANE / 2 if conts else 0.0
        x_lane_l = conn_left + 4
        x_lane_c = x_lane_l + LANE / 2
        x = x_lane_l + LANE + inner + left
        out = _Block(ax=x, entry_node=False)
        y_m = GAP / 2
        y_b = GAP
        if bb:
            out.line([(x, 0), (x, y_b)], arrow=bb.entry_node)
            out.place(bb, x - bb.ax, y_b)
            body_exit = y_b + bb.h if bb.exits else None
            y_after = y_b + bb.h
        else:
            body_exit = 0.0
            y_after = y_b
            if body.pure_jump is not None:
                j = body.pure_jump
                out.escapes.append(_Esc(x, y_b, "down", j.kind, j.target, j.catch_index))
                body_exit = None
        y_c = y_after + GAP
        y_mid = y_after + GAP / 2
        if body_exit is not None:
            out.line([(x, body_exit), (x, y_c)], arrow=True)
        out.nodes.append(self.box(s.dec, x - dw / 2, y_c))
        out.line(
            [(x - dw / 2, y_c + dh / 2), (x_lane_l, y_c + dh / 2), (x_lane_l, y_m), (x, y_m)],
            kind="retorno_bucle",
            arrow=False,
        )
        out.label("sí", x - dw / 2, y_c + dh / 2, "above-end")
        y_exit = y_c + dh + GAP / 2
        out.line([(x, y_c + dh), (x, y_exit)], arrow=False)
        out.label("no", x, y_c + dh, "below-start")
        out.h = y_exit
        out.exits = True
        x_lane_r = x + right + LANE
        out.targets[("break", s.sid, 0)] = _Target(
            x_lane_r,
            y_b,
            y_exit,
            ((x, y_exit),),
            False,
            conn_x=x_lane_r + 6 + CONN_R,
            conn_y=y_b + CONN_R + 4,
            side=1,
        )
        tail = ((x, y_mid),) + (((x, y_c),) if body_exit is None else ())
        out.targets[("continue", s.sid, 0)] = _Target(
            x_lane_c,
            y_b,
            y_mid,
            tail,
            body_exit is None,
            conn_x=x_lane_l - 6 - CONN_R,
            conn_y=y_b + CONN_R + 4,
            side=-1,
        )
        out.w = (x_lane_r + CONN_SPACE + 6) if breaks else (x + right + 6)
        return out

    # ---------------------------------------------------------------- switch

    def switch(self, s: SSwitch) -> _Block:
        dw, dh = self.sizes[s.dec][0], self.sizes[s.dec][1]
        cols = []
        breaks = False
        for case in s.cases:
            b = self.seq(case.body)
            breaks = breaks or _escapes_of(b, "break", s.sid)
            solid = not b.empty
            cw = b.w if solid else 24.0
            ax = b.ax if solid else 12.0
            cols.append((case, b, solid, cw, ax, label_size(case.label)[0]))
        x = max(dw / 2, cols[0][4] if cols else 0.0)
        axes: list[float] = []
        prev_right = 0.0
        for i, (_, _, _, cw, ax, _) in enumerate(cols):
            if i == 0:
                xi = x
            else:
                xi = max(prev_right + GAP_X / 2 + ax, axes[i - 1] + cols[i - 1][5] + 10)
            axes.append(xi)
            prev_right = xi - ax + cw
        y_bus = dh + GAP / 2
        y_top = y_bus + 26
        out = _Block(ax=x, entry_node=True)
        out.nodes.append(self.box(s.dec, x - dw / 2, 0))
        out.line([(x, dh), (x, y_bus)], arrow=False)
        if len(axes) > 1:
            out.line([(x, y_bus), (axes[-1], y_bus)], arrow=False)
        bottoms: list[float] = []
        exits: list[bool] = []
        for i, (case, b, solid, _, _, _) in enumerate(cols):
            xi = axes[i]
            out.label(case.label, xi, y_bus, "below-start")
            if solid:
                out.line([(xi, y_bus), (xi, y_top)], arrow=b.entry_node)
                out.place(b, xi - b.ax, y_top)
                bottoms.append(y_top + b.h)
                exits.append(b.exits)
            elif b.pure_jump is not None:
                out.line([(xi, y_bus), (xi, y_top)], arrow=False)
                j = b.pure_jump
                out.escapes.append(_Esc(xi, y_top, "down", j.kind, j.target, j.catch_index))
                bottoms.append(y_top)
                exits.append(False)
            else:
                bottoms.append(y_bus)
                exits.append(True)
        y_join = max([*bottoms, y_top]) + GAP / 2
        exiting = [i for i in range(len(cols)) if exits[i] and not cols[i][0].falls_through]
        for i in exiting:
            out.line([(axes[i], bottoms[i]), (axes[i], y_join)], arrow=False)
        right_edge = max((axes[i] - cols[i][4] + cols[i][3] for i in range(len(cols))), default=x)
        right_edge = max(right_edge, x + dw / 2)
        if exiting or breaks:
            far = max([axes[i] for i in exiting], default=x)
            if far > x:
                out.line([(x, y_join), (far, y_join)], arrow=False)
        for i in range(len(cols) - 1):
            if cols[i][0].falls_through and exits[i]:
                xi, xn = axes[i], axes[i + 1]
                col_right = xi - cols[i][4] + cols[i][3]
                next_left = xn - cols[i + 1][4]
                x_gap = (col_right + next_left) / 2
                y_mid = (y_bus + y_top) / 2 + 4
                yb = bottoms[i] + 8
                out.line(
                    [(xi, bottoms[i]), (xi, yb), (x_gap, yb), (x_gap, y_mid), (xn, y_mid)],
                    arrow=False,
                )
        out.h = y_join if (exiting or breaks) else max(bottoms, default=y_top)
        out.exits = bool(exiting or breaks)
        if breaks:
            x_r = right_edge + LANE
            out.targets[("break", s.sid, 0)] = _Target(
                x_r,
                y_top,
                y_join,
                ((x, y_join),),
                False,
                conn_x=x_r + 6 + CONN_R,
                conn_y=y_top + CONN_R + 4,
                side=1,
            )
            out.w = x_r + CONN_SPACE + 6
        else:
            out.w = right_edge
        return out

    # ---------------------------------------------------------------- try

    def try_(self, s: STry) -> _Block:
        tw, th = self.sizes[s.node][0], self.sizes[s.node][1]
        body = self.seq(s.body)
        bb = body if not body.empty else None
        x = max(tw / 2, bb.ax if bb else 0.0)
        core = _Block(ax=x, entry_node=True)
        core.nodes.append(self.box(s.node, x - tw / 2, 0))
        y_top = th + GAP
        if bb:
            core.line([(x, th), (x, y_top)], arrow=bb.entry_node)
            core.place(bb, x - bb.ax, y_top)
            b_bottom = y_top + bb.h
            b_exit = bb.exits
        else:
            b_bottom = th
            b_exit = True
        right_body = max(tw / 2, (bb.w - bb.ax) if bb else 0.0)
        catches = []
        for label, seq in s.catches:
            cb = self.seq(seq)
            solid = not cb.empty
            text = f"excepción: {label}"
            catches.append(
                (
                    text,
                    cb,
                    solid,
                    cb.w if solid else 24.0,
                    cb.ax if solid else 12.0,
                    label_size(text)[0],
                )
            )
        axes: list[float] = []
        prev_right = x + right_body
        for i, (_, _, _, cw, ax, _) in enumerate(catches):
            if i == 0:
                xi = max(x + right_body + GAP_X + ax, x + tw / 2 + 20)
            else:
                xi = max(prev_right + GAP_X / 2 + ax, axes[i - 1] + catches[i - 1][5] + 10)
            axes.append(xi)
            prev_right = xi - ax + cw
        if axes:
            core.line([(x + tw / 2, th / 2), (axes[-1], th / 2)], kind="excepcion", arrow=False)
        bottoms = [b_bottom]
        exits = [b_exit]
        xs = [x]
        for i, (text, cb, solid, _, _, _) in enumerate(catches):
            xi = axes[i]
            core.label(text, xi, th / 2, "below-start")
            if solid:
                core.line([(xi, th / 2), (xi, y_top)], kind="excepcion", arrow=cb.entry_node)
                core.place(cb, xi - cb.ax, y_top)
                bottoms.append(y_top + cb.h)
                exits.append(cb.exits)
            else:
                core.line([(xi, th / 2), (xi, y_top)], kind="excepcion", arrow=False)
                bottoms.append(y_top)
                exits.append(cb.pure_jump is None)
            xs.append(xi)
            core.targets[("throw", s.sid, i)] = _Target(
                xi,
                th / 2 + 4,
                y_top,
                conn_x=xi - CONN_R - 6,
                conn_y=(th / 2 + y_top) / 2 + 6,
                side=-1,
            )
        y_join = max(bottoms) + GAP / 2
        far = x
        for xi, bottom, ex in zip(xs, bottoms, exits, strict=True):
            if ex:
                core.line([(xi, bottom), (xi, y_join)], arrow=False)
                far = max(far, xi)
        if far > x:
            core.line([(x, y_join), (far, y_join)], arrow=False)
        core.exits = any(exits)
        core.h = y_join if core.exits else max(bottoms)
        core.w = max(prev_right, x + right_body)
        if s.final is not None and s.final.items:
            return self.stack([core, self.seq(s.final)])
        return core

    # ---------------------------------------------------------------- columnas

    def connector_block(self, label: str) -> _Block:
        b = _Block(w=2 * CONN_R, h=2 * CONN_R, ax=CONN_R, entry_node=True, exits=True)
        b.entry_id = b.exit_id = f"conector-{label}"
        b.connectors.append(Connector(label, CONN_R, CONN_R, CONN_R))
        return b


def _seg_hits(seg: tuple[tuple[float, float], tuple[float, float]], r) -> bool:
    (x1, y1), (x2, y2) = seg
    rx1, ry1, rx2, ry2 = r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1
    if x1 == x2:
        lo, hi = min(y1, y2), max(y1, y2)
        return rx1 < x1 < rx2 and lo < ry2 and hi > ry1
    if y1 == y2:
        lo, hi = min(x1, x2), max(x1, x2)
        return ry1 < y1 < ry2 and lo < rx2 and hi > rx1
    return False


def _path_clear(points: list[tuple[float, float]], rects: list[tuple]) -> bool:
    for a, b in zip(points, points[1:], strict=False):
        for r in rects:
            if _seg_hits((a, b), r):
                return False
    return True


class _Router:
    """Enruta los saltos (break/continue/throw) ya con coordenadas absolutas."""

    def __init__(self, block: _Block) -> None:
        self.block = block
        self.rects = [(n.x, n.y, n.x + n.w, n.y + n.h) for n in block.nodes]
        self.rects += [(c.x - c.r, c.y - c.r, c.x + c.r, c.y + c.r) for c in block.connectors]
        self.next_letter = 0
        self.stacked: dict[tuple, int] = {}

    def route_all(self) -> None:
        escapes = sorted(self.block.escapes, key=lambda e: (e.y, e.x, e.kind, e.sid, e.idx))
        for esc in escapes:
            target = self.block.targets.get((esc.kind, esc.sid, esc.idx))
            if target is None:
                continue
            kind = "excepcion" if esc.kind == "throw" else "salto"
            path = self._try_route(esc, target)
            if path is not None:
                pts = path + self._tail(target)
                self.block.line(pts, kind=kind, arrow=target.tail_arrow)
            else:
                self._connectors(esc, target, kind)

    def _try_route(self, esc: _Esc, t: _Target) -> list[tuple[float, float]] | None:
        ox, oy = esc.x, esc.y
        toward = 1 if t.x > ox else -1
        if esc.direction == "right" and toward < 0:
            return None
        if esc.direction == "left" and toward > 0:
            return None
        lo, hi = min(t.y1, t.y2), max(t.y1, t.y2)
        x_lo, x_hi = min(ox, t.x), max(ox, t.x)
        ys = {oy}
        for r in self.rects:
            if r[3] > oy and r[2] > x_lo and r[0] < x_hi:
                ys.add(r[3] + 8)
        ys.add(lo + 6)
        for cy in sorted(ys):
            if cy < oy or cy <= lo + 1 or cy >= hi - 1:
                continue
            if esc.direction == "down" or cy == oy:
                pts = [(ox, oy)] if cy == oy else [(ox, oy), (ox, cy)]
            else:
                stub = ox + toward * 12
                pts = [(ox, oy), (stub, oy), (stub, cy)]
            pts.append((t.x, cy))
            if _path_clear(pts, self.rects):
                return pts
        return None

    def _connectors(self, esc: _Esc, t: _Target, kind: str) -> None:
        letter = chr(ord("A") + self.next_letter % 26) + (
            str(self.next_letter // 26) if self.next_letter >= 26 else ""
        )
        self.next_letter += 1
        r = CONN_R
        order = {
            "down": ["down", "right", "left"],
            "right": ["right", "down"],
            "left": ["left", "down"],
        }[esc.direction]
        center = None
        for d in order:
            dx, dy = {"down": (0, 1), "right": (1, 0), "left": (-1, 0)}[d]
            cx = esc.x + dx * (14 + r)
            cy = esc.y + dy * (14 + r)
            rect = (cx - r, cy - r, cx + r, cy + r)
            stub_end = (esc.x + dx * 14, esc.y + dy * 14)
            if not any(_rects_overlap(rect, o) for o in self.rects) and _path_clear(
                [(esc.x, esc.y), stub_end], self.rects
            ):
                center = (cx, cy, stub_end)
                break
        if center is None:
            dx, dy = (0, 1)
            center = (esc.x, esc.y + 14 + r, (esc.x, esc.y + 14))
        cx, cy, stub_end = center
        self.block.line([(esc.x, esc.y), stub_end], kind=kind, arrow=True)
        self.block.connectors.append(Connector(letter, cx, cy, r))
        self.rects.append((cx - r, cy - r, cx + r, cy + r))
        key = (t.x, t.y1)
        k = self.stacked.get(key, 0)
        self.stacked[key] = k + 1
        tx, ty = t.conn_x, t.conn_y + k * (2 * r + 6)
        self.block.connectors.append(Connector(letter, tx, ty, r))
        self.rects.append((tx - r, ty - r, tx + r, ty + r))
        edge_x = tx - r if t.side > 0 else tx + r
        self.block.line([(edge_x, ty), (t.x, ty), *self._tail(t)], kind=kind, arrow=t.tail_arrow)

    @staticmethod
    def _tail(t: _Target) -> list[tuple[float, float]]:
        """Tras unirse al carril: bajar por él hasta y2 y seguir la cola (si la hay)."""
        if not t.tail:
            return []
        return [(t.x, t.y2), *t.tail]


def _rects_overlap(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _round(v: float) -> float:
    return round(v, 1)


def _split_columns(blocks: list[_Block], max_height: float) -> list[list[_Block]]:
    """Corta la secuencia de nivel superior en columnas de alto parejo (≤ max_height)."""
    reserve = GAP + 2 * CONN_R
    total = sum(b.h for b in blocks) + GAP * max(0, len(blocks) - 1)
    if total <= max_height or len(blocks) < 2:
        return [blocks]
    n = -(-int(total + reserve) // int(max_height))  # techo
    target = (total + reserve * (n - 1)) / n
    columns: list[list[_Block]] = [[]]
    height = 0.0
    for i, b in enumerate(blocks):
        add = (GAP if columns[-1] else 0.0) + b.h
        remaining = len(blocks) - i
        over_target = height + add / 2 > target and len(columns) < n
        over_max = height + add + reserve > max_height
        if columns[-1] and remaining >= 1 and (over_target or over_max):
            columns.append([b])
            height = reserve + b.h
        else:
            columns[-1].append(b)
            height += add
    return columns


def layout_flow(graph: FlowGraph, struct: SSeq, max_height: float = 1600) -> FlowLayout:
    lay = _Layout(graph)
    items = list(struct.items)
    blocks = [lay.any(it) for it in items if not isinstance(it, SJump)]
    columns = _split_columns(blocks, max_height)
    root = _Block(entry_node=True)
    x = float(MARGIN)
    max_h = 0.0
    for k, col in enumerate(columns):
        parts: list[_Block] = []
        if k > 0:
            parts.append(lay.connector_block(str(k)))
        parts.extend(col)
        if k < len(columns) - 1 and col and col[-1].exits:
            parts.append(lay.connector_block(str(k + 1)))
        col_block = lay.stack(parts)
        root.place(col_block, x, MARGIN)
        x += col_block.w + COL_GAP
        max_h = max(max_h, col_block.h)
    _Router(root).route_all()
    width = x - COL_GAP + MARGIN
    height = max_h + 2 * MARGIN
    # Ampliar el lienzo si un conector de reserva quedó fuera.
    for c in root.connectors:
        width = max(width, c.x + c.r + MARGIN)
        height = max(height, c.y + c.r + MARGIN)
    for lb in root.labels:
        width = max(width, lb.x + lb.w + MARGIN)
    nodes = tuple(
        NodeBox(n.id, n.kind, _round(n.x), _round(n.y), n.w, n.h, n.lines_easy, n.lines_tech)
        for n in sorted(root.nodes, key=lambda n: int(n.id[1:]))
    )
    lines = tuple(
        Line(tuple((_round(px), _round(py)) for px, py in ln.points), ln.kind, ln.arrow)
        for ln in root.lines
    )
    labels = tuple(
        Label(lb.text, _round(lb.x), _round(lb.y), _round(lb.w), _round(lb.h)) for lb in root.labels
    )
    connectors = tuple(Connector(c.label, _round(c.x), _round(c.y), c.r) for c in root.connectors)
    return FlowLayout(
        symbol_id=graph.symbol_id,
        width=_round(width),
        height=_round(height),
        nodes=nodes,
        lines=lines,
        labels=labels,
        connectors=connectors,
        columns=len(columns),
    )


__all__ = ["FlowLayout", "LINE_H", "layout_flow", "node_size"]
