"""Gestión de gramáticas tree-sitter.

Regla de la SPEC (§1.4): solo `desglosa setup` usa la red. Antes de pedir un parser
comprobamos `downloaded_languages()`, porque `get_parser` descargaría la gramática
silenciosamente si no estuviera en caché.

De `tree_sitter_language_pack` solo se usan: get_parser, get_language, download,
downloaded_languages.
"""

from __future__ import annotations

from collections.abc import Iterable

import tree_sitter_language_pack as _tslp
from tree_sitter import Language, Parser

# Los 13 lenguajes de la SPEC más C# (Bloque 2), por nombre de gramática.
LANGS: tuple[str, ...] = (
    "c",
    "cpp",
    "csharp",
    "go",
    "java",
    "javascript",
    "kotlin",
    "php",
    "python",
    "ruby",
    "rust",
    "sql",
    "swift",
    "typescript",
)

# Gramáticas extra que no son un lenguaje nuevo: `tsx` parsea los archivos .tsx de TypeScript.
EXTRA_GRAMMARS: tuple[str, ...] = ("tsx",)

ALL_GRAMMARS: tuple[str, ...] = tuple(sorted(LANGS + EXTRA_GRAMMARS))


class MissingGrammarError(RuntimeError):
    """Falta una gramática en la caché local; hay que ejecutar `desglosa setup`."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = tuple(sorted(missing))
        names = ", ".join(self.missing)
        noun = "la gramática" if len(self.missing) == 1 else "las gramáticas"
        super().__init__(f"Falta {noun} {names}. Ejecuta una vez: desglosa setup")


def downloaded() -> set[str]:
    """Gramáticas ya presentes en la caché local (no usa la red)."""
    return set(_tslp.downloaded_languages())


def setup(names: Iterable[str] = ALL_GRAMMARS) -> int:
    """Descarga las gramáticas indicadas. Es la ÚNICA función que usa la red."""
    return _tslp.download(sorted(set(names)))


def ensure_offline_available(names: Iterable[str]) -> None:
    """Lanza MissingGrammarError si alguna gramática no está descargada."""
    wanted = set(names)
    missing = wanted - downloaded()
    if missing:
        raise MissingGrammarError(missing)


_parsers: dict[str, Parser] = {}


def get_parser(grammar: str) -> Parser:
    """Parser para `grammar`, garantizando que no se descargue nada."""
    parser = _parsers.get(grammar)
    if parser is None:
        ensure_offline_available([grammar])
        parser = _tslp.get_parser(grammar)
        _parsers[grammar] = parser
    return parser


def get_language(grammar: str) -> Language:
    """Objeto Language para `grammar`, sin descargar nada."""
    ensure_offline_available([grammar])
    return _tslp.get_language(grammar)
