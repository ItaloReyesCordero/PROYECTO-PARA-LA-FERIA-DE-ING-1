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

from desglosa.ir import Note

TAGS = ("TODO", "FIXME", "HACK", "XXX", "BUG", "NOTE", "WHY")
_NOTE = re.compile(
    r"(?:#|//|/\*|^\s*\*|--|<!--)[^\n]*?\b(" + "|".join(TAGS) + r")\b\s*(?:\([^)]*\))?\s*[:\-]?\s*(.*)"
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
