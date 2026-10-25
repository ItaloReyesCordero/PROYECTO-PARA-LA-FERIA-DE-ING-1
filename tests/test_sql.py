"""SQL: tablas, PK/FK en sus 3 formas, dialectos y enlace función → tabla (SPEC §9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from desglosa import cli
from desglosa.pipeline import analyze
from desglosa.sqlmodel import parse_sql, split_statements, table_access
from tests.conftest import FIXTURES, needs_grammars

ROOT = Path(__file__).resolve().parent.parent
SQL = (FIXTURES / "sql" / "esquema.sql").read_text(encoding="utf-8")


def test_split_respects_quotes_and_comments():
    stmts = split_statements(SQL)
    first, line = stmts[0]
    assert "CREATE TABLE autores" in first
    assert line == 4  # salta los comentarios iniciales
    assert "'sin; datos'" in first  # el ; dentro de comillas no corta
    assert len(stmts) == 7  # 4 CREATE + ALTER + etiquetas + la sentencia rota


def test_three_fk_forms():
    model = parse_sql("esquema.sql", SQL, "mysql")
    forms = {(fk.form, fk.table, fk.columns, fk.ref_table, fk.ref_columns) for fk in model.fks}
    assert forms == {
        ("en_linea", "libros", ("autor_id",), "autores", ("id",)),
        ("tabla", "prestamos", ("libro_id",), "libros", ("id",)),
        ("alter", "libros", ("editorial_id",), "editoriales", ("id",)),
    }
    assert len(model.fks) == 3


def test_columns_and_primary_keys():
    model = parse_sql("esquema.sql", SQL, "mysql")
    tables = {t.name: t for t in model.tables}
    assert set(tables) == {"autores", "editoriales", "libros", "prestamos", "etiquetas"}
    cols = {c.name: c for c in tables["libros"].columns}
    assert cols["id"].primary_key
    assert cols["titulo"].not_null and not cols["titulo"].primary_key
    assert {c.name for c in tables["prestamos"].columns if c.primary_key} == {"id"}
    assert tables["libros"].line == 16


def test_dialect_fallback_and_broken_statement():
    model = parse_sql("esquema.sql", SQL, "tsql")  # SERIAL no es T-SQL: se reintenta
    assert "etiquetas" in {t.name for t in model.tables}
    assert any("no se pudo leer la sentencia SQL" in w for w in model.warnings)
    assert all(w.startswith("esquema.sql:") for w in model.warnings)


def test_deterministic_ids():
    a = parse_sql("esquema.sql", SQL, None)
    b = parse_sql("esquema.sql", SQL, None)
    assert a.tables == b.tables and a.fks == b.fks


@needs_grammars
def test_table_access_in_laravel():
    a = analyze(ROOT / "examples" / "laravel-mini")
    by_id = {s.id: s.qualname for s in a.project.symbols}
    access = {(by_id[x.symbol_id], x.table, x.mode) for x in a.project.table_access}
    assert access == {
        ("MySqlFacturaRepository.guardar", "facturas", "escribe"),
        ("MySqlFacturaRepository.guardar", "factura_items", "escribe"),
        ("MySqlFacturaRepository.porCliente", "facturas", "lee"),
        ("MySqlFacturaRepository.porCliente", "clientes", "lee"),
        ("MySqlFacturaRepository.buscar", "facturas", "lee"),
    }
    assert all(x.confidence == "probable" for x in a.project.table_access)
    assert len(a.project.fks) == 3


def test_table_access_ignores_prose():
    from desglosa.ir import Symbol

    sym = Symbol("s1", "function", "f", "f", "a.py", 1, 3, None, None, "python", "def f()")
    code = 'def f():\n    print("viene from casa")\n    q = "SELECT * FROM pedidos"\n'
    found = table_access([sym], {"a.py": code}, [])
    assert [(x.table, x.mode, x.line) for x in found] == [("pedidos", "lee", 3)]


@needs_grammars
def test_sql_command(tmp_path, capsys):
    out = tmp_path / "er.html"
    assert cli.main(["sql", str(FIXTURES / "sql"), "-o", str(out)]) == cli.EXIT_OK
    text = capsys.readouterr().out
    assert "relaciones: 3" in text
    assert out.exists()


@needs_grammars
def test_sql_command_without_tables(tmp_path):
    out = tmp_path / "er.html"
    assert cli.main(["sql", str(FIXTURES / "python"), "-o", str(out)]) == cli.EXIT_USAGE


@pytest.mark.parametrize("dialect", ["mysql", "postgres", "sqlite"])
def test_laravel_schema_in_several_dialects(dialect):
    text = (ROOT / "examples" / "laravel-mini" / "database" / "schema.sql").read_text("utf-8")
    model = parse_sql("schema.sql", text, dialect)
    assert len(model.tables) == 4
    assert len(model.fks) == 3
