"""Recorrido de carpetas, detección de lenguaje y lectura robusta de archivos (SPEC §6.1)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from desglosa.ir import SourceFile

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

# Carpetas que se ignoran siempre (por nombre) y rutas relativas concretas.
IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "build",
        "dist",
        "out",
        "target",
        "bin",
        "obj",
        ".venv",
        "venv",
        "__pycache__",
        ".idea",
        ".vscode",
        "storage",
    }
)
IGNORED_DIR_PATHS = ("bootstrap/cache", "public/build")
ALWAYS_IGNORED_FILES = pathspec.GitIgnoreSpec.from_lines(["*.min.*", "*.map", "*.lock"])

MINIFIED_AVG_LINE = 200
MINIFIED_MAX_LINE = 2000


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


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Texto (con saltos `\\n`) y codificación usada: utf-8-sig → utf-8 → cp1252 → latin-1."""
    candidates = (
        ("utf-8-sig", "utf-8", "cp1252")
        if data.startswith(b"\xef\xbb\xbf")
        else (
            "utf-8",
            "cp1252",
        )
    )
    for enc in candidates:
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        enc = "latin-1"
        text = data.decode(enc)
    return text.replace("\r\n", "\n").replace("\r", "\n"), enc


def count_lines(text: str) -> int:
    # No usar splitlines(): también corta en U+2028, \x0c, etc. y no coincidiría con tree-sitter.
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def looks_minified(text: str) -> bool:
    lines = text.split("\n")
    if not lines:
        return False
    if any(len(line) > MINIFIED_MAX_LINE for line in lines):
        return True
    return len(text) / max(1, len(lines)) > MINIFIED_AVG_LINE


@dataclass(frozen=True)
class ScanOptions:
    ignore: tuple[str, ...] = ()
    max_file_kb: int = 1024
    h_as: str = "c"
    langs: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ScanEntry:
    path: str  # POSIX relativo
    abs_path: Path
    lang: str


@dataclass
class ScanResult:
    root: Path
    root_name: str
    entries: list[ScanEntry] = field(default_factory=list)
    skipped: list[SourceFile] = field(default_factory=list)


def _read_ignore_file(path: Path) -> list[str]:
    try:
        text, _ = decode_bytes(path.read_bytes())
    except OSError:
        return []
    return text.splitlines()


class _Ignorer:
    """Combina .gitignore (de cualquier nivel), .desglosaignore y --ignore."""

    def __init__(self, root: Path, extra: tuple[str, ...]) -> None:
        self.root = root
        self.specs: list[tuple[str, pathspec.GitIgnoreSpec]] = []
        top = _read_ignore_file(root / ".desglosaignore") + list(extra)
        if top:
            self.specs.append(("", pathspec.GitIgnoreSpec.from_lines(top)))

    def add_gitignore(self, rel_dir: str, path: Path) -> None:
        lines = _read_ignore_file(path)
        if lines:
            self.specs.append((rel_dir, pathspec.GitIgnoreSpec.from_lines(lines)))

    def ignored(self, rel: str, is_dir: bool) -> bool:
        for base, spec in self.specs:
            if base:
                if not rel.startswith(base + "/"):
                    continue
                sub = rel[len(base) + 1 :]
            else:
                sub = rel
            if spec.match_file(sub + "/" if is_dir else sub):
                return True
        return False


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _make_skipped(rel: str, lang: str, data: bytes, reason: str, lines: int = 0) -> SourceFile:
    return SourceFile(
        path=rel,
        lang=lang,
        sha1=hashlib.sha1(data).hexdigest(),
        lines=lines,
        parsed_ok=False,
        errors=0,
        skipped_reason=reason,
    )


def _consider_file(
    abs_path: Path, rel: str, root: Path, options: ScanOptions, result: ScanResult
) -> None:
    lang = detect_language(abs_path, options.h_as)
    if lang is None:
        return
    if options.langs is not None and lang not in options.langs:
        return
    if ALWAYS_IGNORED_FILES.match_file(abs_path.name):
        return
    if abs_path.is_symlink() and not _inside(abs_path, root):
        result.skipped.append(_make_skipped(rel, lang, b"", "enlace simbólico fuera de la raíz"))
        return
    try:
        size = abs_path.stat().st_size
    except OSError as exc:
        result.skipped.append(_make_skipped(rel, lang, b"", f"no se pudo leer: {exc.strerror}"))
        return
    if size > options.max_file_kb * 1024:
        reason = f"demasiado grande ({size // 1024} KB > {options.max_file_kb} KB)"
        result.skipped.append(_make_skipped(rel, lang, b"", reason))
        return
    data = abs_path.read_bytes()
    if b"\x00" in data[:8192]:
        result.skipped.append(_make_skipped(rel, lang, data, "binario"))
        return
    if lang != "sql":
        text, _ = decode_bytes(data)
        if looks_minified(text):
            result.skipped.append(
                _make_skipped(rel, lang, data, "minificado", lines=count_lines(text))
            )
            return
    result.entries.append(ScanEntry(rel, abs_path, lang))


def scan(target: Path, options: ScanOptions | None = None) -> ScanResult:
    """Recorre `target` (carpeta o archivo) en orden alfabético de ruta POSIX relativa."""
    options = options or ScanOptions()
    target = Path(target)
    if target.is_file():
        root = target.parent
        result = ScanResult(root=root, root_name=root.resolve().name or "raiz")
        _consider_file(target, target.name, root, options, result)
        return result

    root = target
    result = ScanResult(root=root, root_name=root.resolve().name or "raiz")
    ignorer = _Ignorer(root, options.ignore)
    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        if (current / ".gitignore").is_file():
            ignorer.add_gitignore(rel_dir, current / ".gitignore")
        keep = []
        for d in sorted(dirnames):
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if d in IGNORED_DIR_NAMES or rel in IGNORED_DIR_PATHS:
                continue
            if ignorer.ignored(rel, is_dir=True):
                continue
            if (current / d).is_symlink():
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            rel = f"{rel_dir}/{f}" if rel_dir else f
            if ignorer.ignored(rel, is_dir=False):
                continue
            found.append((rel, current / f))
    for rel, abs_path in sorted(found, key=lambda item: item[0]):
        _consider_file(abs_path, rel, root, options, result)
    result.skipped.sort(key=lambda s: s.path)
    return result
