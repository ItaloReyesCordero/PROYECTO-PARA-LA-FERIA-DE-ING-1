"""Rutas de Laravel como puntos de entrada (SPEC §6.4, RF-16).

Se leen los archivos `routes/*.php` con expresiones regulares (no se ejecuta nada):

    Route::get('/facturas', [FacturaController::class, 'index']);
    Route::post('/facturas', 'FacturaController@store');
    Route::resource('facturas', FacturaController::class);
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from desglosa.ir import Symbol

VERBS = "get|post|put|patch|delete|options|any|match"
_ROUTE = re.compile(
    r"Route::(?P<verb>" + VERBS + r")\s*\(\s*(?:\[[^\]]*\]\s*,\s*)?"
    r"(?P<q>['\"])(?P<path>[^'\"]*)(?P=q)\s*,\s*(?P<handler>\[[^\]]*\]|['\"][^'\"]*['\"]|[\w\\]+::class)",
    re.S,
)
_RESOURCE = re.compile(
    r"Route::(?P<kind>apiResource|resource)\s*\(\s*(?P<q>['\"])(?P<path>[^'\"]*)(?P=q)\s*,\s*"
    r"(?P<cls>[\w\\]+)::class",
    re.S,
)
_ARRAY = re.compile(r"\[\s*([\w\\]+)::class\s*,\s*['\"](\w+)['\"]\s*\]")
_AT = re.compile(r"['\"]([\w\\]+)@(\w+)['\"]")
_INVOKABLE = re.compile(r"([\w\\]+)::class")

# Acciones de Route::resource: (método, verbo, sufijo de la ruta).
RESOURCE_ACTIONS = (
    ("index", "GET", ""),
    ("create", "GET", "/create"),
    ("store", "POST", ""),
    ("show", "GET", "/{id}"),
    ("edit", "GET", "/{id}/edit"),
    ("update", "PUT", "/{id}"),
    ("destroy", "DELETE", "/{id}"),
)


@dataclass(frozen=True)
class Route:
    verb: str
    path: str
    target: str  # "Clase@metodo"
    symbol_id: str | None
    file: str
    line: int


def is_route_file(path: str) -> bool:
    parts = path.split("/")
    return path.endswith(".php") and "routes" in parts[:-1]


def _last(name: str) -> str:
    return name.rsplit("\\", 1)[-1]


def _method_index(symbols: list[Symbol]) -> dict[tuple[str, str], str]:
    by_id = {s.id: s for s in symbols}
    out: dict[tuple[str, str], str] = {}
    for s in symbols:
        if s.kind != "method" or not s.parent_id:
            continue
        owner = by_id.get(s.parent_id)
        if owner is not None and owner.kind == "class":
            out.setdefault((owner.name, s.name), s.id)
    return out


def find_routes(files: dict[str, str], symbols: list[Symbol]) -> list[Route]:
    index = _method_index(symbols)
    out: list[Route] = []
    for path in sorted(files):
        text = files[path]
        for m in _ROUTE.finditer(text):
            handler = m.group("handler")
            cls = method = None
            if (a := _ARRAY.search(handler)) or (a := _AT.search(handler)):
                cls, method = _last(a.group(1)), a.group(2)
            elif a := _INVOKABLE.search(handler):
                cls, method = _last(a.group(1)), "__invoke"
            if not cls:
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(
                Route(
                    m.group("verb").upper(),
                    "/" + m.group("path").lstrip("/"),
                    f"{cls}@{method}",
                    index.get((cls, method)),
                    path,
                    line,
                )
            )
        for m in _RESOURCE.finditer(text):
            cls = _last(m.group("cls"))
            base = "/" + m.group("path").strip("/")
            line = text.count("\n", 0, m.start()) + 1
            for method, verb, suffix in RESOURCE_ACTIONS:
                if m.group("kind") == "apiResource" and method in ("create", "edit"):
                    continue
                sid = index.get((cls, method))
                if sid is None:
                    continue  # en un resource solo cuentan las acciones que existen
                out.append(Route(verb, base + suffix, f"{cls}@{method}", sid, path, line))
    return sorted(out, key=lambda r: (r.file, r.line, r.verb, r.path))
