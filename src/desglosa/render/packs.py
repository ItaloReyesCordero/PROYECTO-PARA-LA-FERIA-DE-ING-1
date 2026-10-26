"""Paquetes comprimidos del HTML: cada archivo de código con sus diagramas va aparte.

Por qué: un proyecto de 100 000 líneas genera decenas de MB de diagramas. Si todo va en
un solo JSON, el navegador tiene que leerlo entero al abrir la página. Con paquetes, al
abrir el HTML solo se lee el índice (símbolos, mapa) y cada paquete se descomprime cuando
se abre una función de ese archivo.

Formato de un paquete: JSON compacto → zlib (nivel 9) → base64 "url-safe". El visor lo
abre con `DecompressionStream("deflate")`, que traen los navegadores actuales, sin
librerías ni red. El base64 url-safe no usa `/`, así que el escape del JSON no lo infla.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

from desglosa.render.html import _compact

FORMAT = 2  # versión del formato del payload (1 = todo en un solo JSON)


def pack(obj: Any) -> str:
    # Sin `_compact`: con zlib, quitar los ".0" ahorra solo un 2 % (medido con 200 000
    # líneas) y en Django costaba 44 s. zlib ya comprime lo repetido.
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def pack_compact(obj: Any) -> str:
    """Como `pack`, compactando antes los números (para el índice, que es pequeño)."""
    return pack(_compact(obj))


def unpack(text: str) -> Any:
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(text)).decode("utf-8"))


INDEX_KEYS = (
    "symbols", "files", "calls_out", "calls_in", "impl", "map", "routes", "tables_of",
    "seq_ids", "er", "notes_of", "galaxy", "arch", "uml", "deps",
)


def pack_index(payload: dict) -> dict:
    """Comprime también el índice (símbolos, mapa…): queda `meta`, `index` y `packs`."""
    out = {k: v for k, v in payload.items() if k not in INDEX_KEYS}
    out["index"] = pack_compact({k: payload[k] for k in INDEX_KEYS if k in payload})
    return out


def unpacked(payload: dict) -> dict:
    """El payload con todo abierto: el índice y `flows`, `sequence` y `sources` juntos.

    Útil para tests y herramientas; el visor abre los paquetes de a uno.
    """
    out = {k: v for k, v in payload.items() if k not in ("packs", "index")}
    if payload.get("index"):
        out.update(unpack(payload["index"]))
    flows: dict = {}
    sequence: dict = {}
    sources: dict = {}
    for path, text in sorted((payload.get("packs") or {}).items()):
        data = unpack(text)
        flows.update(data.get("flows") or {})
        sequence.update(data.get("sequence") or {})
        if data.get("source") is not None:
            sources[path] = data["source"]
    out.update(flows=flows, sequence=sequence, sources=sources)
    return out
