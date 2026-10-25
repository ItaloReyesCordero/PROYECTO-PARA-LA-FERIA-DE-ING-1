"""Consultas sobre un proyecto analizado: explicar, camino entre dos funciones y búsqueda.

Sin IA: todo sale del modelo intermedio (símbolos y llamadas resueltas). Las mismas
funciones sirven al CLI (`explain`, `path`, `buscar`), en texto o en JSON.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from desglosa.flows_stage import cyclomatic
from desglosa.ir import CONFIDENCE_RANK, Call, Project, Symbol, call_targets
from desglosa.pipeline import Analysis

FUNC_KINDS = ("function", "method")
KIND_NAMES = {
    "function": "función",
    "method": "método",
    "class": "clase",
    "interface": "interfaz",
    "module": "módulo",
}


# --------------------------------------------------------------------------- buscar por nombre


def find_symbols(project: Project, spec: str, kinds: tuple[str, ...] | None = None) -> list[Symbol]:
    """`archivo:Nombre`, `Clase.metodo` o `nombre` → símbolos que coinciden.

    Si alguno coincide con el nombre calificado exacto, solo se devuelven esos (así
    `Factura` no se confunde con `Factura.__construct`).
    """
    file_part, sep, name = spec.rpartition(":")
    if not sep or len(file_part) == 1:  # "C:\..." no es archivo:nombre
        file_part, name = "", spec
    file_part = file_part.replace("\\", "/").lstrip("./")
    pool = [
        s
        for s in project.symbols
        if s.kind != "module"
        and (kinds is None or s.kind in kinds)
        and (not file_part or s.file == file_part or s.file.endswith("/" + file_part))
    ]
    exact = [s for s in pool if s.qualname == name]
    if exact:
        return sorted(exact, key=_order)
    return sorted((s for s in pool if s.name == name), key=_order)


def _order(s: Symbol) -> tuple:
    return (s.file, s.line_start, s.qualname)


# --------------------------------------------------------------------------- índice de llamadas


@dataclass
class CallIndex:
    """Llamadas salientes y entrantes con la mejor confianza por par de funciones."""

    by_id: dict[str, Symbol]
    out: dict[str, dict[str, tuple[str, Call]]] = field(default_factory=dict)
    inc: dict[str, dict[str, tuple[str, Call]]] = field(default_factory=dict)
    external: dict[str, list[str]] = field(default_factory=dict)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)  # demasiados destinos

    @classmethod
    def of(cls, project: Project) -> CallIndex:
        by_id = {s.id: s for s in project.symbols}
        idx = cls(by_id, defaultdict(dict), defaultdict(dict), defaultdict(list),
                  defaultdict(list))
        for c in sorted(project.calls, key=lambda c: (c.caller_id, c.line, c.col, c.id)):
            targets = call_targets(c)
            if not targets:
                where = idx.external if c.confidence == "externa" else idx.ambiguous
                where[c.caller_id].append(c.callee_text)
            for t in targets:
                if t not in by_id or by_id[t].kind not in FUNC_KINDS:
                    continue
                for table, a, b in ((idx.out, c.caller_id, t), (idx.inc, t, c.caller_id)):
                    prev = table[a].get(b)
                    if prev is None or CONFIDENCE_RANK[c.confidence] < CONFIDENCE_RANK[prev[0]]:
                        table[a][b] = (c.confidence, c)
        return idx


# --------------------------------------------------------------------------- explain


def explain(analysis: Analysis, sym: Symbol, index: CallIndex | None = None) -> dict:
    """Todo lo que se sabe de un símbolo, como datos (el CLI lo imprime o lo da en JSON)."""
    project = analysis.project
    idx = index or CallIndex.of(project)
    by_id = idx.by_id
    flow = analysis.flows.get(sym.id)

    def ref(sid: str, conf: str | None = None, call: Call | None = None) -> dict:
        s = by_id[sid]
        out = {"qualname": s.qualname, "file": s.file, "line": s.line_start, "kind": s.kind}
        if conf:
            out["confidence"] = conf
        if call is not None:
            out["at"] = f"{by_id[call.caller_id].file}:{call.line}"
        return out

    info: dict = {
        "qualname": sym.qualname,
        "kind": sym.kind,
        "lang": sym.lang,
        "file": sym.file,
        "line_start": sym.line_start,
        "line_end": sym.line_end,
        "signature": sym.signature,
        "doc": sym.doc,
        "is_entry": sym.is_entry,
    }
    if sym.parent_id and sym.parent_id in by_id and by_id[sym.parent_id].kind != "module":
        info["parent"] = by_id[sym.parent_id].qualname
    if sym.kind in FUNC_KINDS:
        info["complexity"] = cyclomatic(flow.graph) if flow is not None else None
        info["called_by"] = [
            ref(c, conf, call) for c, (conf, call) in sorted(idx.inc.get(sym.id, {}).items(),
                                                            key=lambda kv: _order(by_id[kv[0]]))
        ]
        info["calls"] = [  # en el orden en que aparecen en el código
            ref(t, conf, call) for t, (conf, call) in sorted(
                idx.out.get(sym.id, {}).items(), key=lambda kv: (kv[1][1].line, kv[1][1].col)
            )
        ]
        info["external"] = sorted(set(idx.external.get(sym.id, [])))
        info["ambiguous"] = sorted(set(idx.ambiguous.get(sym.id, [])))
        route = next(
            (f"{r.verb} {r.path}" for r in analysis.routes if r.symbol_id == sym.id), None
        )
        if route:
            info["route"] = route
        tables = sorted(
            {(a.table, a.mode) for a in project.table_access if a.symbol_id == sym.id}
        )
        if tables:
            info["tables"] = [{"table": t, "mode": m} for t, m in tables]
    else:
        members = [s for s in project.symbols if s.parent_id == sym.id]
        info["members"] = [ref(s.id) for s in sorted(members, key=_order)]
        bases = sorted(
            {b for r in analysis.results for cid, names in r.class_bases.items()
             if cid == sym.id for b in names}
        )
        info["bases"] = bases
    return info


def format_explain(info: dict) -> str:
    kind = KIND_NAMES.get(info["kind"], info["kind"])
    lines = [f"{info['qualname']}  ({kind} · {info['lang']})"]
    lines.append(f"  Dónde:        {info['file']}:{info['line_start']}-{info['line_end']}")
    if info.get("signature"):
        lines.append(f"  Firma:        {info['signature']}")
    if info.get("doc"):
        lines.append(f"  Descripción:  {info['doc']}")
    if info.get("parent"):
        lines.append(f"  Pertenece a:  {info['parent']}")
    if info.get("is_entry"):
        lines.append("  Punto de entrada")
    if info.get("route"):
        lines.append(f"  Ruta HTTP:    {info['route']}")
    if info.get("complexity") is not None:
        n = info["line_end"] - info["line_start"] + 1
        lines.append(f"  Complejidad:  {info['complexity']} · {n} líneas")
    for key, title, arrow in (("called_by", "Llamado por", "<-"), ("calls", "Llama a", "->")):
        if key in info:
            items = info[key]
            lines.append(f"  {title} ({len(items)}):")
            for it in items[:30]:
                lines.append(f"    {arrow} {it['qualname']}  [{it['confidence']}]  {it['at']}")
            if len(items) > 30:
                lines.append(f"    … y {len(items) - 30} más")
    for key, title in (("ambiguous", "Ambiguas, sin destino claro"), ("external", "Externas")):
        names = info.get(key) or []
        if names:
            shown = ", ".join(names[:15]) + (f", … (+{len(names) - 15})" if len(names) > 15 else "")
            lines.append(f"  {title} ({len(names)}): {shown}")
    if info.get("tables"):
        lines.append("  Tablas (probable): " + ", ".join(
            f"{'lee' if t['mode'] == 'lee' else 'escribe'} {t['table']}" for t in info["tables"]
        ))
    if "members" in info:
        lines.append(f"  Miembros ({len(info['members'])}):")
        for m in info["members"][:40]:
            lines.append(f"    · {m['qualname']}  ({KIND_NAMES.get(m['kind'], m['kind'])}) "
                         f"línea {m['line']}")
    if info.get("bases"):
        lines.append("  Hereda de / implementa: " + ", ".join(info["bases"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- path


def shortest_path(index: CallIndex, src: str, dst: str) -> list[tuple[str, str, Call]] | None:
    """Camino de llamadas más corto de `src` a `dst` (BFS). Cada paso: (de, a, llamada).

    Entre caminos igual de cortos se prefiere el de mejor confianza y luego el orden
    alfabético, para que la respuesta sea siempre la misma.
    """
    if src == dst:
        return []
    prev: dict[str, tuple[str, str, Call]] = {}
    seen = {src}
    queue = deque([src])
    while queue:
        cur = queue.popleft()
        nexts = sorted(
            index.out.get(cur, {}).items(),
            key=lambda kv: (CONFIDENCE_RANK[kv[1][0]], _order(index.by_id[kv[0]])),
        )
        for nxt, (_conf, call) in nexts:
            if nxt in seen:
                continue
            seen.add(nxt)
            prev[nxt] = (cur, nxt, call)
            if nxt == dst:
                steps = []
                node = dst
                while node != src:
                    step = prev[node]
                    steps.append(step)
                    node = step[0]
                return list(reversed(steps))
            queue.append(nxt)
    return None


def format_path(index: CallIndex, steps: list[tuple[str, str, Call]]) -> str:
    by_id = index.by_id
    if not steps:
        return "Es la misma función."
    lines = [f"Camino más corto ({len(steps)} paso{'s' if len(steps) != 1 else ''}):"]
    lines.append(f"  {by_id[steps[0][0]].qualname}")
    for a, b, call in steps:
        conf = index.out[a][b][0]
        lines.append(
            f"    --llama [{conf}]--> {by_id[b].qualname}   ({by_id[a].file}:{call.line})"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- buscar


_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9]+")


def _words(text: str) -> list[str]:
    """Palabras en minúscula, separando camelCase y snake_case (`calcularTotal` → 2)."""
    out: list[str] = []
    for part in _WORD.findall(text or ""):
        pieces = re.findall(r"[A-ZÁÉÍÓÚÑ]?[a-záéíóúñ0-9]+|[A-ZÁÉÍÓÚÑ]+(?![a-z])", part) or [part]
        out.extend(p.lower() for p in pieces)
    return out


def _related(word: str, words: set[str]) -> bool:
    """¿Comparte raíz con alguna palabra? `calcular` ~ `calculadora` (5+ letras iguales)."""
    for w in words:
        n = 0
        for a, b in zip(word, w, strict=False):
            if a != b:
                break
            n += 1
        if n >= 5 or (n >= 4 and n == min(len(word), len(w))):
            return True
    return False


@dataclass(frozen=True)
class Hit:
    score: int
    symbol: Symbol
    why: str


def search(project: Project, text: str, limit: int = 15) -> list[Hit]:
    """Búsqueda por palabras: nombre (lo que más pesa), nombre calificado, documentación
    y ruta del archivo. Sin IA: solo coincidencias de palabras, explicadas."""
    query = [w for w in _words(text) if len(w) > 1]
    if not query:
        return []
    whole = text.strip().lower()
    hits: list[Hit] = []
    for s in project.symbols:
        if s.kind == "module":
            continue
        name_w, qual_w = set(_words(s.name)), set(_words(s.qualname))
        doc_w, file_w = set(_words(s.doc or "")), set(_words(s.file))
        score, why = 0, []
        if s.name.lower() == whole or s.qualname.lower() == whole:
            score += 100
            why.append("nombre exacto")
        for w in query:
            # Palabra exacta: puntaje completo; misma raíz (calcular ~ calculadora): menos.
            for words, pts, where in (
                (name_w, 10, "el nombre"),
                (qual_w, 6, "la clase"),
                (doc_w, 4, "la descripción"),
                (file_w, 2, "el archivo"),
            ):
                if w in words:
                    score += pts
                    why.append(f"«{w}» en {where}")
                    break
                if _related(w, words):
                    score += pts // 2
                    why.append(f"«{w}» (parecida) en {where}")
                    break
        if score:
            if s.kind in FUNC_KINDS and s.is_entry:
                score += 1
            hits.append(Hit(score, s, ", ".join(dict.fromkeys(why))))
    hits.sort(key=lambda h: (-h.score, _order(h.symbol)))
    return hits[:limit]


def format_search(hits: list[Hit]) -> str:
    if not hits:
        return "Sin resultados."
    lines = []
    for h in hits:
        s = h.symbol
        lines.append(f"{h.score:4d}  {s.qualname}  ({KIND_NAMES.get(s.kind, s.kind)})  "
                     f"{s.file}:{s.line_start}")
        lines.append(f"      {h.why}")
    return "\n".join(lines)
