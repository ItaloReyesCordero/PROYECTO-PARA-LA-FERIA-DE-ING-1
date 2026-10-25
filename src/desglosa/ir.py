"""Modelo intermedio (IR) de Desglosa (SPEC §5).

Todas las clases son inmutables y se serializan a JSON con orden estable.
Los ids se calculan con un hash estable, nunca con `id()` ni contadores.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# Valores permitidos (documentación viva; los tests los usan).
SYMBOL_KINDS = ("module", "class", "interface", "function", "method")
CONFIDENCES = ("exacta", "probable", "ambigua", "externa")
IO_KINDS = ("pantalla", "teclado", "archivo_lee", "archivo_escribe")
CTX_KINDS = ("if", "else", "loop", "switch_case", "try", "catch")
FLOW_NODE_KINDS = (
    "terminal",
    "proceso",
    "subproceso",
    "decision",
    "es",
    "pantalla",
    "teclado",
    "documento",
    "conector",
    "conector_pagina",
    "externo",
)
FLOW_EDGE_KINDS = ("normal", "retorno_bucle", "excepcion", "salto")

# Orden de "peor confianza" (para agregar aristas en el mapa).
CONFIDENCE_RANK = {c: i for i, c in enumerate(CONFIDENCES)}

# Con más destinos posibles que esto, una llamada no informa a cuál va (p. ej. `->with()`
# en Laravel existe en 20 clases): no se dibuja ni se cuenta como llamada a ninguno.
MAX_ALTERNATIVES = 4


def stable_id(lang: str, path: str, qualname: str, line_start: int) -> str:
    """Id estable: sha1("lang|path|qualname|line")[:12] (SPEC §5)."""
    raw = f"{lang}|{path}|{qualname}|{line_start}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str  # POSIX relativo a la raíz analizada
    lang: str
    sha1: str
    lines: int
    parsed_ok: bool
    errors: int
    skipped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Symbol:
    id: str
    kind: str
    name: str
    qualname: str
    file: str
    line_start: int
    line_end: int
    parent_id: str | None
    doc: str | None
    lang: str
    signature: str
    is_entry: bool = False


@dataclass(frozen=True, slots=True)
class Import:
    file: str
    module_text: str  # módulo o ruta tal como está escrito
    alias: str | None
    line: int
    # Extensión a la SPEC: nombre importado (`from m import NOMBRE`, `import {NOMBRE}`).
    # None cuando se importa el módulo completo.
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ControlCtx:
    kind: str
    line: int
    label: str


@dataclass(frozen=True, slots=True)
class Call:
    id: str
    caller_id: str
    callee_text: str
    receiver_text: str | None
    line: int
    col: int
    context: tuple[ControlCtx, ...] = ()
    resolved_id: str | None = None
    candidates: tuple[str, ...] = ()
    confidence: str = "externa"
    io_kind: str | None = None


def call_targets(call: Call) -> tuple[str, ...]:
    """Destinos con los que se puede contar: el resuelto, o hasta MAX_ALTERNATIVES
    candidatos (interfaz o nombre repetido). Con más, ninguno."""
    if call.resolved_id:
        return (call.resolved_id,)
    if len(call.candidates) <= MAX_ALTERNATIVES:
        return call.candidates
    return ()


@dataclass(frozen=True, slots=True)
class FlowNode:
    id: str
    kind: str
    text_easy: str
    text_tech: str
    line_start: int
    line_end: int
    call_id: str | None = None
    target_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class FlowEdge:
    src: str
    dst: str
    label: str | None = None
    kind: str = "normal"


@dataclass(frozen=True, slots=True)
class FlowGraph:
    symbol_id: str
    nodes: tuple[FlowNode, ...]
    edges: tuple[FlowEdge, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str
    not_null: bool = False
    primary_key: bool = False


@dataclass(frozen=True, slots=True)
class Table:
    id: str
    name: str
    file: str
    line: int
    columns: tuple[Column, ...] = ()


@dataclass(frozen=True, slots=True)
class ForeignKey:
    id: str
    table: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    file: str
    line: int
    form: str  # "en_linea" | "tabla" | "alter"


@dataclass(frozen=True, slots=True)
class TableAccess:
    symbol_id: str
    table: str
    mode: str  # "lee" | "escribe"
    line: int
    confidence: str = "probable"


@dataclass(frozen=True, slots=True)
class Note:
    """Comentario marcado (TODO, FIXME, NOTE…): decisiones y pendientes escritos en el código."""

    file: str
    line: int
    tag: str  # TODO | FIXME | HACK | XXX | BUG | NOTE | WHY
    text: str
    symbol_id: str | None = None  # función o clase que la contiene


@dataclass(frozen=True, slots=True)
class Project:
    root_name: str
    files: tuple[SourceFile, ...] = ()
    symbols: tuple[Symbol, ...] = ()
    imports: tuple[Import, ...] = ()
    calls: tuple[Call, ...] = ()
    flows: tuple[FlowGraph, ...] = ()
    tables: tuple[Table, ...] = ()
    fks: tuple[ForeignKey, ...] = ()
    table_access: tuple[TableAccess, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[Note, ...] = ()


# --------------------------------------------------------------------------- serialización


_SIMPLE = (str, int, float, bool, type(None))
_FIELD_NAMES: dict[type, tuple[str, ...]] = {}


def to_jsonable(obj: Any) -> Any:
    """Convierte dataclasses/tuplas a estructuras JSON (dict/list) con orden estable."""
    if type(obj) in _SIMPLE:
        return obj
    cls = type(obj)
    names = _FIELD_NAMES.get(cls)
    if names is None and dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        names = _FIELD_NAMES[cls] = tuple(f.name for f in dataclasses.fields(obj))
    if names is not None:
        return {name: to_jsonable(getattr(obj, name)) for name in names}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    return obj


def dumps(obj: Any, indent: int | None = 2) -> str:
    """JSON determinista (claves ordenadas, sin escapar acentos)."""
    if indent is None:
        return json.dumps(
            to_jsonable(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    return json.dumps(to_jsonable(obj), sort_keys=True, ensure_ascii=False, indent=indent) + "\n"
