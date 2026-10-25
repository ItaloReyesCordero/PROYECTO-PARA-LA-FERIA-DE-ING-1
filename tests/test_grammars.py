from __future__ import annotations

import pytest

from desglosa import grammars


def test_thirteen_languages():
    assert len(grammars.LANGS) == 14  # los 13 de la SPEC + C#
    assert "tsx" not in grammars.LANGS
    assert list(grammars.LANGS) == sorted(grammars.LANGS)


def test_missing_grammar_message(monkeypatch):
    monkeypatch.setattr(grammars, "downloaded", lambda: {"python"})
    with pytest.raises(grammars.MissingGrammarError) as info:
        grammars.ensure_offline_available(["python", "php"])
    assert str(info.value) == "Falta la gramática php. Ejecuta una vez: desglosa setup"


def test_get_parser_never_downloads(monkeypatch):
    """Si la gramática no está en caché, get_parser debe fallar y NO llamar al paquete."""
    grammars._parsers.pop("kotlin", None)
    monkeypatch.setattr(grammars, "downloaded", lambda: set())

    def boom(*_a, **_k):
        raise AssertionError("se intentó obtener el parser sin verificar la caché")

    monkeypatch.setattr(grammars._tslp, "get_parser", boom)
    with pytest.raises(grammars.MissingGrammarError):
        grammars.get_parser("kotlin")


def test_all_grammars_parse():
    missing = set(grammars.ALL_GRAMMARS) - grammars.downloaded()
    if missing:
        pytest.skip(f"faltan gramáticas (ejecuta desglosa setup): {sorted(missing)}")
    for name in grammars.ALL_GRAMMARS:
        tree = grammars.get_parser(name).parse(b"x")
        assert tree.root_node is not None
