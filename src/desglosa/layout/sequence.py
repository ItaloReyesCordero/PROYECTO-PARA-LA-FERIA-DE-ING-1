"""Layout del diagrama de secuencia: rejilla columnas × filas (SPEC §8).

Columnas de ancho = máx(nombre, 140 px); filas de 36 px. Cuando un mensaje abre un
fragmento (loop, alt…) se deja un poco más de aire para la etiqueta del fragmento. Un `if`
seguido inmediatamente por su `else` se dibuja como un solo "alt" con línea divisoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from desglosa.layout.text import CHAR_W, LABEL_CHAR_W
from desglosa.sequence import SequenceDiagram

ROW = 36
COL_MIN = 140
COL_GAP = 40
TOP = 20
HEAD_H = 38
FRAG_OPEN = 22
MARGIN = 24


@dataclass(frozen=True)
class SequenceLayout:
    width: float
    height: float
    participants: tuple  # (x, y, w, h, label, kind)
    lifelines: tuple  # (x, y1, y2)
    messages: tuple  # (x1, x2, y, texto, tipo, destino, confianza, externa)
    fragments: tuple  # (x, y, w, h, etiqueta, tipo, y_divisor | None)
    confidences: tuple


def _frag_label(kind: str, label: str) -> str:
    if kind == "loop":
        return f"loop [{label}]"
    if kind == "if":
        return f"opt [{label}]"
    if kind == "else":
        return "alt [else]"
    if kind == "caso":
        return f"alt [{label}]"
    if kind == "try":
        return "try"
    if kind == "catch":
        return f"catch [{label}]"
    if kind == "impl":
        return f"alt [{label}]"
    return label


def layout_sequence(diagram: SequenceDiagram) -> SequenceLayout:
    parts = list(diagram.participants)
    col_w = [max(COL_MIN, len(p.label) * CHAR_W + 28) for p in parts]
    centers: dict[str, float] = {}
    x = MARGIN + 50.0  # espacio a la izquierda para los fragmentos
    for p, w in zip(parts, col_w, strict=True):
        centers[p.id] = x + w / 2
        x += w + COL_GAP
    width_cols = x - COL_GAP + 50 + MARGIN

    frag_by_id = {f.id: f for f in diagram.fragments}
    depth: dict[str, int] = {}
    for f in diagram.fragments:
        d, cur = 0, f.parent
        while cur is not None and cur in frag_by_id:
            d += 1
            cur = frag_by_id[cur].parent
        depth[f.id] = d

    y = TOP + HEAD_H + 26.0
    rows: list[float] = []
    open_frags: tuple[str, ...] = ()
    for m in diagram.messages:
        new = [f for f in m.fragments if f not in open_frags]
        closed = [f for f in open_frags if f not in m.fragments]
        if rows:
            y += ROW
        y += FRAG_OPEN * len(new) + 8 * len(closed)
        rows.append(y)
        open_frags = m.fragments
    bottom = (rows[-1] if rows else y) + 30 + 8 * len(open_frags)

    msgs = []
    confs: set[str] = set()
    for m, ry in zip(diagram.messages, rows, strict=True):
        text = f"{m.number}: {m.label}" if m.number else m.label
        msgs.append(
            (
                round(centers[m.src], 1),
                round(centers[m.dst], 1),
                round(ry, 1),
                text,
                m.kind,
                m.target,
                m.confidence,
                m.external,
            )
        )
        if m.kind != "retorno":
            confs.add(m.confidence)

    # Extensión de cada fragmento: filas y columnas de sus mensajes.
    span: dict[str, list[float]] = {}
    for m, ry in zip(diagram.messages, rows, strict=True):
        xs = (centers[m.src], centers[m.dst])
        for fid in m.fragments:
            s = span.setdefault(fid, [ry, ry, min(xs), max(xs)])
            s[0], s[1] = min(s[0], ry), max(s[1], ry)
            s[2], s[3] = min(s[2], *xs), max(s[3], *xs)

    frags = []
    merged_else: set[str] = set()
    ordered = sorted(span, key=lambda f: (span[f][0], depth.get(f, 0), f))
    for fid in ordered:
        if fid in merged_else:
            continue
        f = frag_by_id[fid]
        top, last, x1, x2 = span[fid]
        divider = None
        label = _frag_label(f.kind, f.label)
        if f.kind == "if":
            # ¿Le sigue su else al mismo nivel? → un solo alt con divisor.
            sibling = next(
                (
                    o
                    for o in ordered
                    if o not in merged_else
                    and frag_by_id[o].kind == "else"
                    and frag_by_id[o].parent == f.parent
                    and span[o][0] > last
                    and span[o][0] - last <= ROW + FRAG_OPEN * 3 + 16
                ),
                None,
            )
            if sibling is not None:
                merged_else.add(sibling)
                divider = round((last + span[sibling][0]) / 2 - 4, 1)
                last = span[sibling][1]
                x1, x2 = min(x1, span[sibling][2]), max(x2, span[sibling][3])
                label = f"alt [{f.label}]"
        d = depth.get(fid, 0)
        pad = max(14.0, 46.0 - 8 * d)
        label_w = len(label) * LABEL_CHAR_W + 16
        fx1 = x1 - pad
        fx2 = max(x2 + pad, fx1 + label_w + 20)
        fy1 = top - 20 - FRAG_OPEN * 0.6 + 4 * d
        fy2 = last + 12 - 3 * d
        frags.append(
            (
                round(fx1, 1),
                round(fy1, 1),
                round(fx2 - fx1, 1),
                round(fy2 - fy1, 1),
                label,
                f.kind,
                divider,
            )
        )
    participants = []
    lifelines = []
    for p, w in zip(parts, col_w, strict=True):
        cx = centers[p.id]
        participants.append((round(cx - w / 2, 1), TOP, w, HEAD_H, p.label, p.kind))
        lifelines.append((round(cx, 1), TOP + HEAD_H, round(bottom, 1)))
    width = max(width_cols, max((f[0] + f[2] for f in frags), default=0) + MARGIN)
    return SequenceLayout(
        width=round(width, 1),
        height=round(bottom + MARGIN, 1),
        participants=tuple(participants),
        lifelines=tuple(lifelines),
        messages=tuple(msgs),
        fragments=tuple(frags),
        confidences=tuple(c for c in ("exacta", "probable", "ambigua", "externa") if c in confs),
    )
