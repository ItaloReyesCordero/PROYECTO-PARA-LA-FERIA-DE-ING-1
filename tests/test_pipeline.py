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
