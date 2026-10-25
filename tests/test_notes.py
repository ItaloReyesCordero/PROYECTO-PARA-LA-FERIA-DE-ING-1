"""Notas en comentarios: TODO, FIXME, NOTE… (Bloque 2)."""

from __future__ import annotations

from desglosa.ir import Symbol
from desglosa.notes import attach_symbols, find_notes
from desglosa.pipeline import analyze
from desglosa.report import build_report
from tests.conftest import needs_grammars


def test_find_notes_in_comments_only():
    text = (
        "# TODO: validar el RUC\n"
        "x = 'TODO no es nota porque está en una cadena'\n"
        "// FIXME(italo) se cae con listas vacías\n"
        "/* NOTE - usamos redondeo bancario */\n"
        " * WHY: el SUNAT exige 2 decimales\n"
        "-- HACK temporal\n"
        "# Note: con mayúscula inicial no es etiqueta\n"
        "# TODOS los casos (palabra distinta)\n"
    )
    notes = find_notes("a.py", text)
    assert [(n.line, n.tag, n.text) for n in notes] == [
        (1, "TODO", "validar el RUC"),
        (3, "FIXME", "se cae con listas vacías"),
        (4, "NOTE", "usamos redondeo bancario"),
        (5, "WHY", "el SUNAT exige 2 decimales"),
        (6, "HACK", "temporal"),
    ]


def test_notes_attach_to_innermost_symbol():
    def sym(sid, kind, a, b):
        return Symbol(sid, kind, sid, sid, "a.py", a, b, None, None, "python", "")

    notes = find_notes("a.py", "\n\n# TODO: dentro\n\n\n# TODO: afuera\n")
    attached = attach_symbols(notes, [sym("cls", "class", 1, 4), sym("fn", "method", 2, 4)])
    assert [n.symbol_id for n in attached] == ["fn", None]


@needs_grammars
def test_notes_in_project_and_report(tmp_path):
    (tmp_path / "pago.py").write_text(
        "def cobrar(monto):\n"
        "    # FIXME: no valida montos negativos\n"
        "    return monto\n",
        encoding="utf-8",
    )
    a = analyze(tmp_path)
    [note] = a.project.notes
    assert note.tag == "FIXME" and note.line == 2
    assert {s.id: s.name for s in a.project.symbols}[note.symbol_id] == "cobrar"
    text = build_report(a)
    assert "## Notas en el código" in text and "no valida montos negativos" in text
