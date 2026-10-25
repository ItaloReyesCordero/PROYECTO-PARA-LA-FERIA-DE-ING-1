"""Caché incremental: no volver a analizar lo que no cambió.

Se guardan dos cosas por archivo:
- lo extraído (`FileResult`), con clave = ruta + lenguaje + hash del contenido;
- sus diagramas de flujo, con clave = hash de todo lo que los define (las funciones del
  archivo, cómo se resolvió cada llamada, las opciones de dibujo y el contenido).

Decisiones:
- **JSON, nunca `pickle`**: un archivo de caché manipulado no puede ejecutar código; como
  mucho daría un diagrama equivocado, y un archivo dañado simplemente se ignora.
- Vive en la carpeta de caché del usuario (no dentro del proyecto analizado), una
  subcarpeta por proyecto.
- Toda clave incluye una huella del código de Desglosa: si Desglosa cambia, la caché vieja
  deja de servir sola. No hay que borrarla a mano.
- Al terminar un análisis se borran las entradas de ese proyecto que ya no se usaron.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import types
import typing
import zlib
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from desglosa import __version__
from desglosa.ir import to_jsonable

SCHEMA = 1
_FINGERPRINT: str | None = None


def default_dir() -> Path:
    """Carpeta de caché del usuario (o `DESGLOSA_CACHE_DIR` si está definida)."""
    env = os.environ.get("DESGLOSA_CACHE_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "desglosa" / "cache"


def code_fingerprint() -> str:
    """Hash del código Python de Desglosa: cambia con cualquier modificación."""
    global _FINGERPRINT
    if _FINGERPRINT is None:
        root = Path(__file__).resolve().parent
        h = hashlib.sha1(f"{__version__}|{SCHEMA}".encode())
        for path in sorted(root.rglob("*.py")):
            h.update(path.relative_to(root).as_posix().encode("utf-8"))
            h.update(path.read_bytes())
        _FINGERPRINT = h.hexdigest()
    return _FINGERPRINT


# --------------------------------------------------------------------------- JSON → objetos


_DECODERS: dict[Any, Any] = {}


def _identity(v: Any) -> Any:
    return v


def _decoder(tp: Any):
    """Función que convierte JSON en `tp`. Se arma una vez por tipo (leer las anotaciones
    con get_type_hints en cada objeto hacía la caché más lenta que analizar de nuevo)."""
    dec = _DECODERS.get(tp)
    if dec is not None:
        return dec
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        hints = get_type_hints(tp)
        parts = [(f.name, _decoder(hints[f.name])) for f in dataclasses.fields(tp)]

        def dec(v, tp=tp, parts=parts):
            return tp(**{name: d(v[name]) for name, d in parts if name in v})

    else:
        origin, args = get_origin(tp), get_args(tp)
        if origin in (typing.Union, types.UnionType):
            inner = [a for a in args if a is not type(None)]
            d_in = _decoder(inner[0]) if inner else _identity

            def dec(v, d_in=d_in):
                return None if v is None else d_in(v)

        elif origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            d_el = _decoder(args[0])
            dec = tuple if d_el is _identity else (lambda v, d=d_el: tuple(map(d, v)))
        elif origin is tuple:
            ds = [_decoder(a) for a in args]

            def dec(v, ds=ds):
                return tuple(d(x) for d, x in zip(ds, v, strict=True))

        elif origin is list:
            d_el = _decoder(args[0])
            dec = list if d_el is _identity else (lambda v, d=d_el: list(map(d, v)))
        elif origin is dict:
            d_val = _decoder(args[1])
            dec = dict if d_val is _identity else (
                lambda v, d=d_val: {k: d(x) for k, x in v.items()}
            )
        elif tp is float:

            def dec(v):
                return float(v) if isinstance(v, int) and not isinstance(v, bool) else v

        else:
            dec = _identity
    _DECODERS[tp] = dec
    return dec


def from_jsonable(tp: Any, value: Any) -> Any:
    """Reconstruye `tp` (dataclass, tuple, list, dict, Optional…) desde datos JSON."""
    if value is None:
        return None
    return _decoder(tp)(value)


def write_entry(path: str, data: Any, plain: bool = False) -> None:
    """Escribe una entrada de caché (nivel módulo: la usan también los otros procesos).

    Escritura atómica: primero a un .tmp y luego se reemplaza. Un error de disco se ignora
    (la caché solo acelera; nunca debe tumbar el análisis).
    """
    text = json.dumps(data if plain else to_jsonable(data), sort_keys=True, ensure_ascii=False)
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(zlib.compress(text.encode("utf-8"), 3))
        os.replace(tmp, target)
    except OSError:
        pass


def fingerprint(*parts: Any) -> str:
    h = hashlib.sha1(code_fingerprint().encode())
    for part in parts:
        text = part if isinstance(part, str) else json.dumps(
            to_jsonable(part), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        h.update(b"\x00")
        h.update(text.encode("utf-8"))
    return h.hexdigest()


class Cache:
    """Caché de un proyecto. Los errores de disco nunca detienen el análisis."""

    def __init__(self, base: Path, project_root: Path) -> None:
        root = os.path.normcase(str(Path(project_root).resolve()))
        self.dir = Path(base) / hashlib.sha1(root.encode("utf-8")).hexdigest()[:16]
        self.used: set[Path] = set()
        self.kinds: set[str] = set()  # tipos consultados en este análisis
        self.hits = 0
        self.misses = 0

    def _path(self, kind: str, key: str) -> Path:
        self.kinds.add(kind)
        return self.dir / kind / f"{key}.json.z"

    def get(self, kind: str, key: str) -> Any:
        """Los datos JSON guardados, o None si no hay (o el archivo está dañado)."""
        path = self._path(kind, key)
        try:
            data = json.loads(zlib.decompress(path.read_bytes()).decode("utf-8"))
        except (OSError, ValueError, zlib.error):
            self.misses += 1
            return None
        self.used.add(path)
        self.hits += 1
        return data

    def path_for(self, kind: str, key: str) -> str:
        """Ruta donde un proceso de trabajo puede guardar su entrada (ver `write_entry`)."""
        path = self._path(kind, key)
        self.used.add(path)
        return str(path)

    def put(self, kind: str, key: str, data: Any, plain: bool = False) -> None:
        """Guarda `data`; con `plain=True` ya es JSON puro (dict/list/str/números)."""
        write_entry(self.path_for(kind, key), data, plain)

    def prune(self) -> int:
        """Borra las entradas de este proyecto que no se usaron en este análisis.

        Solo dentro de los tipos que se consultaron: `desglosa path` no dibuja flujos, y no
        por eso debe borrar los flujos guardados (el siguiente `analyze` los necesita).
        """
        removed = 0
        if not self.dir.is_dir():
            return 0
        for kind in sorted(self.kinds):
            folder = self.dir / kind
            if not folder.is_dir():
                continue
            removed += self._prune_folder(folder)
        return removed

    def _prune_folder(self, folder: Path) -> int:
        removed = 0
        for path in folder.rglob("*"):
            if path.is_file() and path not in self.used:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
