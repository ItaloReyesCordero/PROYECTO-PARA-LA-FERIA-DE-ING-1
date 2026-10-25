from __future__ import annotations

import socket

import pytest

from desglosa import grammars
from desglosa.ir import dumps
from desglosa.pipeline import analyze
from tests.conftest import FIXTURES, needs_grammars

pytestmark = needs_grammars


def test_deterministic():
    a = dumps(analyze(FIXTURES / "php").project)
    b = dumps(analyze(FIXTURES / "php").project)
    assert a == b


def test_parallel_equals_serial():
    from desglosa.pipeline import AnalyzeOptions

    serial = dumps(analyze(FIXTURES / "python", AnalyzeOptions(jobs=1)).project)
    parallel = dumps(analyze(FIXTURES / "python", AnalyzeOptions(jobs=2)).project)
    assert serial == parallel


def test_no_network_during_analyze(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("analyze intentó abrir un socket")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    project = analyze(FIXTURES / "java").project
    assert project.symbols


def test_missing_grammar_aborts(monkeypatch):
    monkeypatch.setattr(grammars, "downloaded", lambda: {"python"})
    with pytest.raises(grammars.MissingGrammarError, match="Falta la gramática php"):
        analyze(FIXTURES / "php")


def test_broken_fixture_does_not_crash():
    project = analyze(FIXTURES / "roto").project
    files = {f.path: f for f in project.files}
    assert files["malo.py"].errors > 0
    assert not files["malo.py"].parsed_ok
    names = {s.name for s in project.symbols}
    assert {"bien", "despues"} <= names  # lo que está bien se extrae igual
    acentos = files["acentos.c"]
    assert acentos.parsed_ok
    doc = next(s.doc for s in project.symbols if s.name == "anio_actual")
    assert doc == "Función con acentos: año, camión"
    assert any("malo.py" in w for w in project.warnings)


@needs_grammars
def test_duplicated_class_names_across_folders(tmp_path):
    """Las mismas clases en dos carpetas: el resolvedor no debe romperse ni adivinar."""
    import shutil

    for copy in ("a", "b"):
        for lang in ("python", "java", "php", "ruby", "kotlin"):
            shutil.copytree(FIXTURES / lang, tmp_path / copy / lang)
    result = analyze(tmp_path)
    single = analyze(tmp_path / "a")
    assert len(result.project.files) == 2 * len(single.project.files)
    assert len(result.project.symbols) == 2 * len(single.project.symbols)
    by_id = {s.id: s for s in result.project.symbols}
    for c in result.project.calls:
        if c.resolved_id and c.confidence == "exacta":
            # Una llamada exacta nunca cruza a la otra copia del proyecto.
            caller, target = by_id[c.caller_id], by_id[c.resolved_id]
            assert caller.file.split("/")[0] == target.file.split("/")[0]


@needs_grammars
def test_js_this_without_class_resolves_in_same_file(tmp_path):
    """Estilo Express: métodos asignados a un objeto y llamados con `this.`."""
    (tmp_path / "app.js").write_text(
        "var app = {};\n"
        "app.set = function set(k, v) { return v; };\n"
        "app.init = function init() {\n"
        "  this.set('a', 1);\n"
        "  this.emit('listo');\n"
        "};\n",
        encoding="utf-8",
    )
    a = analyze(tmp_path)
    by_id = {s.id: s for s in a.project.symbols}
    calls = {c.callee_text: c for c in a.project.calls}
    assert calls["set"].confidence == "probable"
    assert by_id[calls["set"].resolved_id].name == "set"
    assert calls["emit"].confidence == "externa"  # no está definido en el proyecto
