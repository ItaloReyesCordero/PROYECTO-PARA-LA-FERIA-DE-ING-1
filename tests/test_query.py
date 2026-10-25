"""Consultas sin IA: explain, path y buscar (Bloque 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.pipeline import analyze
from desglosa.query import CallIndex, _words, explain, find_symbols, search, shortest_path
from tests.conftest import needs_grammars

pytestmark = needs_grammars

ROOT = Path(__file__).resolve().parent.parent
LARAVEL = ROOT / "examples" / "laravel-mini"


@pytest.fixture(scope="module")
def laravel():
    return analyze(LARAVEL)


def test_find_symbols_prefers_exact_qualname(laravel):
    assert [s.qualname for s in find_symbols(laravel.project, "Factura")] == ["Factura"]
    assert len(find_symbols(laravel.project, "buscar")) == 3
    one = find_symbols(laravel.project, "app/Services/FacturacionService.php:buscar")
    assert [s.qualname for s in one] == ["FacturacionService.buscar"]


def test_explain_function(laravel):
    [sym] = find_symbols(laravel.project, "FacturacionService.emitir")
    info = explain(laravel, sym)
    assert info["doc"].startswith("Calcula el total")
    assert [c["qualname"] for c in info["called_by"]] == ["FacturaController.store"]
    # En el orden en que aparecen en el código.
    assert [c["qualname"] for c in info["calls"]] == [
        "CalculadoraImpuestos.aplicar",
        "Factura.__construct",
        "MySqlFacturaRepository.guardar",
    ]
    assert "count" in info["external"]


def test_explain_class_lists_members(laravel):
    [sym] = find_symbols(laravel.project, "MySqlFacturaRepository")
    info = explain(laravel, sym)
    assert {m["qualname"] for m in info["members"]} >= {"MySqlFacturaRepository.guardar"}
    assert info["bases"] == ["FacturaRepository"]


def test_shortest_path(laravel):
    idx = CallIndex.of(laravel.project)
    [a] = find_symbols(laravel.project, "FacturaController.store")
    [b] = find_symbols(laravel.project, "MySqlFacturaRepository.guardar")
    steps = shortest_path(idx, a.id, b.id)
    names = [idx.by_id[x].qualname for x, _, _ in steps] + [idx.by_id[steps[-1][1]].qualname]
    assert names == [
        "FacturaController.store",
        "FacturacionService.emitir",
        "MySqlFacturaRepository.guardar",
    ]
    assert shortest_path(idx, b.id, a.id) is None  # al revés no hay camino


def test_search_uses_word_roots(laravel):
    hits = search(laravel.project, "calcular impuestos")
    assert hits[0].symbol.qualname == "CalculadoraImpuestos"
    assert "parecida" in hits[0].why
    assert search(laravel.project, "zzz nada") == []


def test_words_split_camel_and_snake():
    assert _words("calcularTotal_conIVA") == ["calcular", "total", "con", "iva"]


def test_cli_exit_codes_and_json(tmp_path, capsys):
    assert cli.main(["explain", str(LARAVEL), "buscar"]) == cli.EXIT_AMBIGUOUS
    assert cli.main(["explain", str(LARAVEL), "NoExiste"]) == cli.EXIT_NOT_FOUND
    capsys.readouterr()
    assert cli.main(["explain", str(LARAVEL), "FacturacionService.emitir", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["qualname"] == "FacturacionService.emitir" and data["complexity"] == 4
    code = cli.main([
        "path", str(LARAVEL), "FacturaController.store", "MySqlFacturaRepository.guardar",
        "--json",
    ])
    assert code == 0
    assert [s["to"] for s in json.loads(capsys.readouterr().out)] == [
        "FacturacionService.emitir",
        "MySqlFacturaRepository.guardar",
    ]
    assert cli.main(["buscar", str(LARAVEL), "zzz"]) == cli.EXIT_NOT_FOUND
    assert "Sin resultados." in capsys.readouterr().out
    assert cli.main(["search", str(LARAVEL), "factura", "--limit", "2", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
