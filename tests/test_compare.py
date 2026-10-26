"""Comparar dos versiones (Bloque 4): `desglosa comparar`.

`fixtures/comparar/antes` y `despues` tienen una función que cambia (`total`, con un `if`
nuevo), una nueva (`igv`), una eliminada (`descuento`) y una que solo se movió de lugar
(`imprimir`), que no cuenta como cambio.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.compare import CompareError, _extract, compare, export_commit
from desglosa.pipeline import AnalyzeOptions, analyze
from desglosa.scan import ScanOptions

FIXTURES = Path(__file__).parent / "fixtures" / "comparar"


def _analysis(path: Path):
    return analyze(path, AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=None))


def test_changes_between_two_folders():
    result = compare(_analysis(FIXTURES / "antes"), _analysis(FIXTURES / "despues"), "a", "b")
    found = {(c.status, c.qualname) for c in result.changes}
    assert found == {("cambiada", "total"), ("nueva", "igv"), ("eliminada", "descuento")}
    total = next(c for c in result.changes if c.qualname == "total")
    assert (total.cc_before, total.cc_after) == (2, 3)  # el `if` nuevo
    assert (total.lines_before, total.lines_after) == (5, 7)
    assert result.files_changed == ["caja.py"] and not result.files_added


def test_cli_json(capsys):
    code = cli.main(["comparar", str(FIXTURES / "antes"), str(FIXTURES / "despues"),
                     "--json", "--no-cache"])
    data = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert [(f["estado"], f["nombre"], f["complejidad"]) for f in data["funciones"]] == [
        ("eliminada", "descuento", [1, None]),
        ("nueva", "igv", [None, 1]),
        ("cambiada", "total", [2, 3]),
    ]


def test_html_carries_the_flows_of_before(tmp_path):
    out = tmp_path / "c.html"
    assert cli.main(["comparar", str(FIXTURES / "antes"), str(FIXTURES / "despues"),
                     "-o", str(out), "--no-cache"]) == cli.EXIT_OK
    from desglosa.render.packs import unpack
    from tests.test_html import _raw

    raw = _raw(out.read_text(encoding="utf-8"))
    index = unpack(raw["index"])
    assert raw["meta"]["start"] == "#/cambios"
    rows = index["compare"]["funciones"]
    assert [r[0] for r in rows] == ["eliminada", "nueva", "cambiada"]
    before = unpack(raw["packs"]["@antes/caja.py"])["flows"]
    # Flujos de antes: el de la eliminada y el de la cambiada (no el de la movida).
    assert set(before) == {rows[0][3], rows[2][3]}
    assert all(f["layout"]["nodes"] for f in before.values())


def test_wrong_arguments(capsys):
    assert cli.main(["comparar", str(FIXTURES / "antes")]) == cli.EXIT_USAGE
    assert "dos carpetas" in capsys.readouterr().err


def test_extract_only_regular_files_inside(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        def add(name: str, data: bytes = b"x", kind=tarfile.REGTYPE, link: str = ""):
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = link
            info.size = len(data) if kind == tarfile.REGTYPE else 0
            tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)

        add("ok/a.py", b"print(1)")
        add("../fuera.py")
        add("/absoluto.py")
        add("enlace", kind=tarfile.SYMTYPE, link="/etc/passwd")
    dest = tmp_path / "dest"
    dest.mkdir()
    _extract(buf.getvalue(), dest)
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == ["ok/a.py"]
    assert not (tmp_path / "fuera.py").exists()


def test_rejects_refs_that_look_like_options(tmp_path):
    with pytest.raises(CompareError):
        export_commit(tmp_path, "--output=x")


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git")
def test_compare_with_a_git_commit(tmp_path, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "antes", repo)

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=Prueba", "-c", "user.email=p@ejemplo.test",
                        "-c", "commit.gpgsign=false", *args], cwd=repo, check=True,
                       capture_output=True)

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "antes")
    shutil.copy(FIXTURES / "despues" / "caja.py", repo / "caja.py")
    code = cli.main(["comparar", str(repo), "--desde", "HEAD", "--json", "--no-cache"])
    data = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK and data["antes"] == "HEAD"
    assert {f["nombre"] for f in data["funciones"]} == {"descuento", "igv", "total"}
    # La carpeta temporal del commit se borra al terminar.
    assert not list(Path(tmp_path).glob("desglosa-antes-*"))
    assert cli.main(["comparar", str(repo), "--desde", "no-existe"]) == cli.EXIT_USAGE
