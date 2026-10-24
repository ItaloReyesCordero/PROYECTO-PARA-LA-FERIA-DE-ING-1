"""Recorrido de carpetas, detección de lenguaje y lectura robusta de archivos (SPEC §6.1)."""

from __future__ import annotations

from pathlib import Path

# Extensión → lenguaje (nombre lógico; coincide con el nombre de gramática salvo .tsx).
EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".sql": "sql",
}


def detect_language(path: Path | str, h_as: str = "c") -> str | None:
    """Lenguaje lógico de un archivo según su extensión, o None si no se soporta."""
    p = Path(path)
    name = p.name.lower()
    if name.endswith(".blade.php"):
        return None
    suffix = p.suffix.lower()
    if suffix == ".h":
        return h_as
    return EXTENSIONS.get(suffix)


def grammar_for(path: Path | str, lang: str) -> str:
    """Gramática tree-sitter para un archivo: .tsx usa la gramática `tsx`."""
    if lang == "typescript" and Path(path).suffix.lower() == ".tsx":
        return "tsx"
    return lang
