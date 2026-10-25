from __future__ import annotations

import pytest

from desglosa import cli, grammars


def test_no_command_is_usage_error(capsys):
    assert cli.main([]) == cli.EXIT_USAGE


def test_bad_option_is_usage_error():
    with pytest.raises(SystemExit) as info:
        cli.main(["doctor", "--no-existe"])
    assert info.value.code == cli.EXIT_USAGE


def test_doctor_reports_missing(monkeypatch, capsys):
    monkeypatch.setattr(grammars, "downloaded", lambda: {"python", "c"})
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_GRAMMARS
    assert "python       OK" in out
    assert "php          FALTA" in out
    assert "2/14 lenguajes listos." in out


def test_doctor_all_ok(monkeypatch, capsys):
    monkeypatch.setattr(grammars, "downloaded", lambda: set(grammars.ALL_GRAMMARS))
    assert cli.main(["doctor"]) == cli.EXIT_OK
    assert "14/14 lenguajes listos." in capsys.readouterr().out


def test_debug_ast_python(tmp_path, capsys):
    if "python" not in grammars.downloaded():
        pytest.skip("falta la gramática python")
    src = tmp_path / "a.py"
    src.write_text("def suma(a, b):\n    return a + b\n", encoding="utf-8")
    assert cli.main(["debug-ast", str(src)]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "function_definition L1-L2" in out
    assert 'name: identifier L1  "suma"' in out


def test_export_ir_matches_golden(tmp_path, capsys):
    from tests.conftest import FIXTURES, GOLDEN, have_grammars

    if not have_grammars("php"):
        pytest.skip("falta la gramática php")
    out = tmp_path / "ir.json"
    assert cli.main(["export-ir", str(FIXTURES / "php"), "-o", str(out)]) == cli.EXIT_OK
    assert out.read_text(encoding="utf-8") == (GOLDEN / "ir" / "php.json").read_text(
        encoding="utf-8"
    )
    assert "Llamadas:" in capsys.readouterr().out


def test_export_ir_missing_path():
    assert cli.main(["export-ir", "no/existe/nada"]) == cli.EXIT_USAGE


def test_debug_ast_unknown_extension(tmp_path):
    src = tmp_path / "a.xyz"
    src.write_text("hola", encoding="utf-8")
    assert cli.main(["debug-ast", str(src)]) == cli.EXIT_USAGE
