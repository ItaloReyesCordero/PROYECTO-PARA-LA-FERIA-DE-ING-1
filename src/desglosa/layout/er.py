"""Layout del diagrama entidad-relación (SPEC §9): tablas como cajas de columnas.

Usa el layout por capas (§10). Cada relación sale de la fila de la columna FK y llega a
la fila de la columna referenciada (PK), con la etiqueta "N:1".
"""

from __future__ import annotations

from desglosa.ir import ForeignKey, Table
from desglosa.layout.layered import LEdge, LNode, layout_layered
from desglosa.layout.text import CHAR_W, LINE_H

HEADER = 24
PAD = 8


def column_text(col, fk_cols: set[str]) -> str:
    prefix = "PK " if col.primary_key else ""
    if col.name in fk_cols:
        prefix += "FK "
    suffix = " NOT NULL" if col.not_null and not col.primary_key else ""
    return f"{prefix}{col.name} {col.type}{suffix}".strip()


def layout_er(tables: list[Table], fks: list[ForeignKey]) -> dict:
    by_name = {t.name.lower(): t for t in tables}
    fk_cols: dict[str, set[str]] = {}
    for fk in fks:
        fk_cols.setdefault(fk.table.lower(), set()).update(fk.columns)
    texts: dict[str, list[str]] = {}
    nodes = []
    for t in tables:
        cols = [column_text(c, fk_cols.get(t.name.lower(), set())) for c in t.columns]
        texts[t.id] = cols
        w = max([len(t.name) + 2, *(len(c) for c in cols)]) * CHAR_W + 2 * PAD + 8
        h = HEADER + max(1, len(cols)) * LINE_H + PAD
        nodes.append(LNode(t.id, float(int(w + 1) // 2 * 2), float(h), t.name.lower()))
    edges = []
    meta: dict[tuple[str, str], ForeignKey] = {}
    for fk in fks:
        src = by_name.get(fk.table.lower())
        dst = by_name.get(fk.ref_table.lower())
        if src is None or dst is None or src.id == dst.id:
            continue
        if (src.id, dst.id) in meta:
            continue
        meta[(src.id, dst.id)] = fk
        edges.append(LEdge(src.id, dst.id, "N:1"))
    lay = layout_layered(nodes, edges)

    def row_y(table: Table, column: str, top: float) -> float | None:
        for i, c in enumerate(table.columns):
            if c.name == column:
                return top + HEADER + i * LINE_H + LINE_H / 2 + 2
        return None

    by_id = {t.id: t for t in tables}
    edges_out = []
    for e in lay.edges:
        fk = meta[(e.src, e.dst)]
        pts = [list(p) for p in e.points]
        src_box, dst_box = lay.nodes[e.src], lay.nodes[e.dst]
        # Mover los extremos a la fila de la columna FK y de la columna referenciada.
        ys = row_y(by_id[e.src], fk.columns[0], src_box.y) if fk.columns else None
        yd = row_y(by_id[e.dst], fk.ref_columns[0], dst_box.y) if fk.ref_columns else None
        if ys is None:
            ys = next(
                (row_y(by_id[e.src], c.name, src_box.y) for c in by_id[e.src].columns
                 if c.primary_key), None,
            )
        if yd is None:
            pk = next((c.name for c in by_id[e.dst].columns if c.primary_key), None)
            yd = row_y(by_id[e.dst], pk, dst_box.y) if pk else None
        rebuilt = False
        if len(pts) >= 4:
            if ys is not None:
                pts[0][1] = pts[1][1] = round(ys, 1)
            if yd is not None:
                pts[-1][1] = pts[-2][1] = round(yd, 1)
        elif ys is not None and yd is not None:
            # Tablas en capas vecinas: la línea venía de centro a centro. Se rehace en
            # ángulo recto: fila FK → mitad del hueco → fila referenciada.
            if src_box.x + src_box.w <= dst_box.x:
                x0, x3 = src_box.x + src_box.w, dst_box.x
            elif dst_box.x + dst_box.w <= src_box.x:
                x0, x3 = src_box.x, dst_box.x + dst_box.w
            else:
                x0 = x3 = None
            if x0 is not None and x3 is not None:
                y0, y3 = round(ys, 1), round(yd, 1)
                xm = round((x0 + x3) / 2, 1)
                if abs(y0 - y3) < 0.5:
                    pts = [[x0, y0], [x3, y0]]
                else:
                    pts = [[x0, y0], [xm, y0], [xm, y3], [x3, y3]]
                    rebuilt = True
        flat: list[float] = []
        for x, y in pts:
            flat.extend((x, y))
        box = e.label_box or (0, 0, 0, 0)
        if e.label_box:
            # Re-centrar la etiqueta en el tramo que cruza el hueco más ancho (o, si la
            # línea se rehízo en ángulo recto, en el tramo que llega a la tabla destino).
            a, b = (pts[2], pts[3]) if rebuilt else max(
                zip(pts, pts[1:], strict=False), key=lambda s: abs(s[1][0] - s[0][0])
            )
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            box = (round(mx - box[2] / 2, 1), round(my - box[3] / 2, 1), box[2], box[3])
        edges_out.append([flat, e.label, box[0], box[1], box[2], box[3]])
    tables_out = []
    for t in tables:
        p = lay.nodes[t.id]
        tables_out.append([t.id, p.x, p.y, p.w, p.h, t.name, texts[t.id]])
    return {"w": lay.width, "h": lay.height, "tables": tables_out, "edges": edges_out}
