"""Caché incremental: mismo resultado, menos trabajo, y nunca código ejecutable."""

from __future__ import annotations

import shutil
from pathlib import Path

from desglosa import cli
from desglosa.cache import Cache, from_jsonable
from desglosa.extract import FileResult
from desglosa.ir import SourceFile, Symbol, to_jsonable
from desglosa.layout.flow import FlowLayout
from desglosa.pipeline import AnalyzeOptions, analyze
from tests.conftest import FIXTURES, needs_grammars

ROOT = Path(__file__).resolve().parent.parent
LARAVEL = ROOT / "examples" / "laravel-mini"


def test_from_jsonable_roundtrip():
    sym = Symbol("a1", "method", "f", "C.f", "x.py", 1, 3, "c1", None, "python", "def f()")
    assert from_jsonable(Symbol, to_jsonable(sym)) == sym
    fr = FileResult(
        file=SourceFile("x.py", "python", "s", 3, True, 0),
        symbols=[sym],
        class_bases={"c1": ("Base",)},
        extra_bases=[("T", "B")],
    )
    back = from_jsonable(FileResult, to_jsonable(fr))
    assert back == fr
    assert isinstance(back.class_bases["c1"], tuple)
    assert back.extra_bases == [("T", "B")]


@needs_grammars
def test_layout_roundtrip_is_exact():
    a = analyze(ROOT / "examples" / "gps-c")
    for out in a.flows.values():
        assert from_jsonable(FlowLayout, to_jsonable(out.layout)) == out.layout


def _html(tmp_path: Path, name: str, *extra: str) -> bytes:
    out = tmp_path / name
    assert cli.main(["analyze", str(LARAVEL), "-o", str(out), *extra]) == cli.EXIT_OK
    return out.read_bytes()


@needs_grammars
def test_cached_run_gives_identical_html(tmp_path, capsys):
    cache = tmp_path / "cache"
    base = _html(tmp_path, "sin.html", "--no-cache")
    cold = _html(tmp_path, "frio.html", "--cache-dir", str(cache))
    warm = _html(tmp_path, "tibio.html", "--cache-dir", str(cache))
    assert base == cold == warm
    out = capsys.readouterr().out
    assert "Caché: 0 de 9 archivos sin cambios, 0 de 6 con flujos ya dibujados" in out
    assert "Caché: 9 de 9 archivos sin cambios, 6 de 6 con flujos ya dibujados" in out


@needs_grammars
def test_changed_file_is_reanalyzed(tmp_path):
    project = tmp_path / "proyecto"
    shutil.copytree(FIXTURES / "python", project)
    opts = AnalyzeOptions(cache_dir=tmp_path / "cache")
    first = analyze(project, opts)
    target = sorted(project.glob("*.py"))[0]
    target.write_text(target.read_text("utf-8") + "\n\ndef nueva():\n    return 1\n", "utf-8")
    second = analyze(project, opts)
    assert "nueva" not in {s.name for s in first.project.symbols}
    assert "nueva" in {s.name for s in second.project.symbols}
    n = len(first.scan.entries)
    assert second.cache_info.startswith(f"{n - 1} de {n} archivos sin cambios")
    fresh = analyze(project)  # sin caché
    assert fresh.project == second.project


@needs_grammars
def test_damaged_cache_is_ignored(tmp_path):
    cache_dir = tmp_path / "cache"
    opts = AnalyzeOptions(cache_dir=cache_dir)
    good = analyze(LARAVEL, opts)
    for f in cache_dir.rglob("*.json.z"):
        f.write_bytes(b"esto no es zlib")
    again = analyze(LARAVEL, opts)
    assert again.project == good.project
    assert again.cache_info.startswith("0 de")


@needs_grammars
def test_unused_entries_are_pruned(tmp_path):
    project = tmp_path / "p"
    shutil.copytree(FIXTURES / "python", project)
    cache_dir = tmp_path / "cache"
    analyze(project, AnalyzeOptions(cache_dir=cache_dir))
    before = sorted(cache_dir.rglob("*.json.z"))
    for f in project.glob("*.py"):
        f.write_text(f.read_text("utf-8") + "\n# cambio\n", "utf-8")
    analyze(project, AnalyzeOptions(cache_dir=cache_dir))
    after = sorted(cache_dir.rglob("*.json.z"))
    assert len(after) == len(before)
    assert not set(before) & set(after)


def test_cache_dir_per_project(tmp_path):
    a = Cache(tmp_path, tmp_path / "uno")
    b = Cache(tmp_path, tmp_path / "dos")
    assert a.dir != b.dir and a.dir.parent == b.dir.parent == tmp_path
