"""Medición de texto con fuente monoespaciada y ajuste de líneas (SPEC §7.4).

Ancho aproximado = caracteres × 0.6 × tamaño de fuente. El visor usa la misma fuente
monoespaciada del sistema, así que las cajas calculadas aquí coinciden con lo dibujado.
"""

from __future__ import annotations

FONT_SIZE = 12
CHAR_W = 0.6 * FONT_SIZE
LINE_H = 16
WRAP_EASY = 28
WRAP_TECH = 40

LABEL_FONT_SIZE = 11
LABEL_CHAR_W = 0.6 * LABEL_FONT_SIZE
LABEL_H = 15


def wrap(text: str, width: int) -> list[str]:
    """Ajusta `text` a `width` caracteres por línea; respeta los saltos de línea existentes."""
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            while len(word) > width:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line = f"{line} {word}"
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


def text_width(lines: list[str], char_w: float = CHAR_W) -> float:
    return max((len(line) for line in lines), default=0) * char_w


def text_height(lines: list[str], line_h: float = LINE_H) -> float:
    return len(lines) * line_h


def label_size(text: str) -> tuple[float, float]:
    return len(text) * LABEL_CHAR_W + 8, LABEL_H
