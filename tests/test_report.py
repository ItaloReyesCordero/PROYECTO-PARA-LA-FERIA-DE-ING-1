"""Reporte Markdown (SPEC RF-15)."""

from __future__ import annotations

from pathlib import Path

from desglosa import cli
from desglosa.pipeline import analyze
from desglosa.report import SECTIONS, _cell, _cycles, build_report
from tests.conftest import FIXTURES, needs_grammars

ROOT = Path(__file__).resolve().parent.parent


def _section(text: str, title: str) -> str:
    start = text.index(f"## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end >= 0 else len(text)]


@needs_grammars
def test_report_has_all_sections():
    text = build_report(analyze(ROOT / "examples" / "laravel-mini"))
    for title in SECTIONS:
        assert f"\n## {title}\n" in text, title
    assert "## Tablas SQL" in text


@needs_grammars
def test_report_content_laravel():
    text = build_report(analyze(ROOT / "examples" / "laravel-mini"))
    assert "| php | 8 |" in _section(text, "Archivos por lenguaje")
    # La interfaz es una declaración: no es "nunca llamada" (se llama su implementación).
    never = _section(text, "Funciones nunca llamadas")
    assert "FacturaRepository.guardar" not in never.replace("MySqlFacturaRepository", "")
    assert "FacturaController.store" not in never  # punto de entrada (ruta)
    top = _section(text, "Complejidad más alta")
    assert top.index("FacturacionService.emitir") < top.index("FacturaController.store")
    tables = _section(text, "Tablas SQL")
    assert "| `facturas` | 4 |" in tables and "MySqlFacturaRepository.guardar" in tables


@needs_grammars
def test_report_recursion_and_broken_files():
    text = build_report(analyze(FIXTURES / "secuencia"))
    cycles = _section(text, "Ciclos de llamadas")
    assert "Recursión directa: `factorial`" in cycles
    assert "Recursión directa: `Servicio.avisar`" in cycles
    broken = build_report(analyze(FIXTURES / "roto"))
    assert "de sintaxis (se analizó igual)" in _section(broken, "Archivos no parseados")


@needs_grammars
def test_report_is_deterministic():
    a = build_report(analyze(FIXTURES / "python"))
    b = build_report(analyze(FIXTURES / "python"))
    assert a == b
    assert "Tiempo" not in a  # sin tiempos ni fechas


def test_cycles_between_functions():
    edges = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"d"}, "e": {"a"}}
    found = sorted(sorted(c) for c in _cycles(edges))
    assert found == [["a", "b", "c"], ["d"]]


def test_cycles_deep_chain_without_recursion_limit():
    edges = {str(i): {str(i + 1)} for i in range(5000)}
    assert _cycles(edges) == []


def test_cell_escapes_table_syntax():
    assert _cell("a|b\nc") == "a\\|b c"


@needs_grammars
def test_report_option(tmp_path, capsys):
    out = tmp_path / "x.html"
    rep = tmp_path / "r.md"
    code = cli.main(["analyze", str(FIXTURES / "python"), "-o", str(out), "--report", str(rep)])
    assert code == cli.EXIT_OK
    assert rep.read_text(encoding="utf-8").startswith("# Reporte de Desglosa: python")
    assert "Reporte escrito en" in capsys.readouterr().out
