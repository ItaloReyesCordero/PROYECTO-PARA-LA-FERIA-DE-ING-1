"""Notas en comentarios: TODO, FIXME, HACK, XXX, BUG, NOTE y WHY.

Son decisiones y pendientes que el equipo dejó escritos. Se detectan línea por línea, de
forma rápida e igual para todos los lenguajes:

- la etiqueta va en MAYÚSCULAS y como palabra completa (`Note:` en un texto normal no
  cuenta);
- tiene que haber un marcador de comentario antes (`#`, `//`, `/*`, `*`, `--`, `<!--`), así
  que `x = "TODO"` en una cadena no es una nota.
"""

from __future__ import annotations

import re
from pathlib import Path

from desglosa.ir import Note
from desglosa.scan import decode_bytes

TAGS = ("TODO", "FIXME", "HACK", "XXX", "BUG", "NOTE", "WHY")
_NOTE = re.compile(
    r"(?:#|//|/\*|^\s*\*|--|<!--)[^\n]*?"  # un marcador de comentario antes
    r"\b(" + "|".join(TAGS) + r")\b"  # la etiqueta, en mayúsculas
    r"\s*(?:\([^)]*\))?\s*[:\-]?\s*(.*)"  # autor opcional "(italo)", ":" o "-", texto
)
MAX_TEXT = 160


def find_notes(path: str, text: str) -> list[Note]:
    out: list[Note] = []
    for n, line in enumerate(text.split("\n"), start=1):
        if not any(tag in line for tag in TAGS):  # filtro barato antes del regex
            continue
        m = _NOTE.search(line)
        if m is None:
            continue
        body = m.group(2).strip()
        for end in ("*/", "-->"):
            if body.endswith(end):
                body = body[: -len(end)].rstrip()
        if len(body) > MAX_TEXT:
            body = body[: MAX_TEXT - 1] + "…"
        out.append(Note(path, n, m.group(1), body))
    return out


def attach_symbols(notes: list[Note], symbols) -> list[Note]:
    """Cada nota queda unida a la función o clase más interna que la contiene."""
    by_file: dict[str, list] = {}
    for s in symbols:
        if s.kind != "module":
            by_file.setdefault(s.file, []).append(s)
    out = []
    for note in notes:
        inner = None
        for s in by_file.get(note.file, ()):
            if s.line_start <= note.line <= s.line_end and (
                inner is None or s.line_end - s.line_start < inner.line_end - inner.line_start
            ):
                inner = s
        out.append(Note(note.file, note.line, note.tag, note.text, inner.id if inner else None))
    return out


# --------------------------------------------------------------------------- README

README_NAMES = ("readme.md", "readme.markdown", "readme.rst", "readme.txt", "readme")
README_MAX_BYTES = 16384  # el título y el primer párrafo están al principio
README_MAX_TEXT = 200
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")  # ![alt](img): fuera (insignias, logos)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [texto](url): queda el texto
_SENTENCE = re.compile(r"(?<=[.!?])\s")
_TAG = re.compile(r"<[^>]+>")
_RULE = re.compile(r"[=\-~^#*_+ ]{3,}")
_SKIP_PREFIXES = ("<", "![", "[![", "|", "```", "~~~", ">", ".. ", "- ", "* ", "+ ", "[")


def _clean(text: str) -> str:
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _TAG.sub("", text)
    for mark in ("**", "__", "`"):
        text = text.replace(mark, "")
    return " ".join(text.split()).strip(" :")


def readme_summary(text: str) -> str | None:
    """"Título: primera frase" de un README (Markdown, reStructuredText o texto).

    Se saltan insignias, imágenes, HTML, tablas, listas, citas y bloques de código.
    """
    title: str | None = None
    desc: str | None = None
    lines = text.split("\n")
    in_code = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code or not line or _RULE.fullmatch(line):
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_heading = line.startswith("#") or (
            bool(_RULE.fullmatch(nxt)) and nxt[:1] in "=-~^" and len(nxt) >= 3
        )
        if is_heading:
            if title is None:
                title = _clean(line.lstrip("#")) or None
            continue
        if line.startswith(_SKIP_PREFIXES):
            continue
        cleaned = _clean(line)
        if cleaned and cleaned != title:
            # Solo la primera frase, si no queda demasiado corta.
            first = _SENTENCE.split(cleaned, maxsplit=1)[0]
            desc = first if len(first) >= 20 else cleaned
            break
    out = f"{title}: {desc}" if title and desc else title or desc
    if not out:
        return None
    return out if len(out) <= README_MAX_TEXT else out[: README_MAX_TEXT - 1] + "…"


def readme_notes(root: Path, dirs) -> dict[str, str]:
    """Carpeta (POSIX relativa, "" = raíz) → resumen de su README, si tiene uno."""
    out: dict[str, str] = {}
    for d in sorted(set(dirs)):
        folder = root / d if d else root
        try:
            found = {p.name.lower(): p for p in sorted(folder.iterdir()) if p.is_file()}
        except OSError:
            continue
        for name in README_NAMES:
            path = found.get(name)
            if path is None:
                continue
            try:
                with path.open("rb") as fh:
                    data = fh.read(README_MAX_BYTES)
            except OSError:
                break
            note = readme_summary(decode_bytes(data)[0])
            if note:
                out[d] = note
            break
    return out


def project_dirs(paths) -> set[str]:
    """Las carpetas que contienen los archivos analizados y todas sus carpetas padre."""
    dirs = {""}
    for p in paths:
        parts = p.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return dirs
