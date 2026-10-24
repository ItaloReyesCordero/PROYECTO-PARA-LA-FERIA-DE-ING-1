"""Mapa por niveles (SPEC §6.4, RF-04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from desglosa.macro import MAX_CHILDREN, build_map
from desglosa.pipeline import analyze
from tests.conftest import needs_grammars

pytestmark = needs_grammars

ROOT = Path(__file__).resolve().parent.parent
LARAVEL = ROOT / "examples" / "laravel-mini"


@pytest.fixture(scope="module")
def laravel():
    a = analyze(LARAVEL)
    return a, build_map(a.project)


def _children(m, gid):
    return [n[0] for n in m["groups"][gid]["layout"]["nodes"]]


def _by_name(m, gid, name):
    for n in m["groups"][gid]["layout"]["nodes"]:
        if n[6] == name:
            return n
    raise AssertionError(f"no hay {name!r} en {m['groups'][gid]['name']}")


def test_root_and_collapsed_folders(laravel):
    _, m = laravel
    root = m["groups"][m["root"]]
    assert root["parent"] is None
    labels = [n[6] for n in root["layout"]["nodes"]]
    assert labels == ["app/", "routes/"]
    app = _by_name(m, "root", "app/")[0]
    app_labels = [n[6] for n in m["groups"][app]["layout"]["nodes"]]
    assert app_labels == ["Http/Controllers/", "Models/", "Repositories/", "Services/"]


def test_file_with_one_class_shows_the_class(laravel):
    a, m = laravel
    app = _by_name(m, "root", "app/")[0]
    ctrl_dir = _by_name(m, app, "Http/Controllers/")[0]
    node = _by_name(m, ctrl_dir, "FacturaController")
    assert node[1] == "entrada"  # *Controller es punto de entrada
    base = _by_name(m, ctrl_dir, "Controller")
    assert base[1] == "clase"  # la clase base abstracta no
    methods = [n[6] for n in m["groups"][node[0]]["layout"]["nodes"]]
    assert methods == ["__construct()", "index()", "store()", "show()"]  # orden del código
    links = {n[6]: n[8] for n in m["groups"][node[0]]["layout"]["nodes"]}
    store = next(s for s in a.project.symbols if s.qualname == "FacturaController.store")
    assert links["store()"] == f"#/flujo/{store.id}"


def test_edges_are_aggregated_with_counts_and_worst_confidence(laravel):
    _, m = laravel
    app = _by_name(m, "root", "app/")[0]
    names = {n[0]: n[6] for n in m["groups"][app]["layout"]["nodes"]}
    edges = {(names[e[0]], names[e[1]]): (e[3], e[4]) for e in m["groups"][app]["layout"]["edges"]}
    assert edges[("Http/Controllers/", "Services/")] == ("probable", "3 llamadas")
    assert edges[("Services/", "Repositories/")] == ("probable", "3 llamadas")
    assert ("Services/", "Models/") in edges
    assert edges[("Services/", "Models/")][0] == "exacta"


def test_owner_of_every_function(laravel):
    a, m = laravel
    for s in a.project.symbols:
        if s.kind in ("function", "method"):
            assert s.id in m["owner"], s.qualname
            assert m["owner"][s.id] in m["groups"]


def test_legend_only_present_types(laravel):
    _, m = laravel
    for gid, g in m["groups"].items():
        lay = g["layout"]
        kinds = {n[1] for n in lay["nodes"]}
        confs = {e[3] for e in lay["edges"]}
        assert set(lay["legend"]) == kinds | confs, gid


def test_other_group_when_more_than_15_children(tmp_path):
    lines = [f"def f{i:02d}():\n    return f{(i + 1) % 20:02d}()\n\n" for i in range(20)]
    (tmp_path / "muchas.py").write_text("".join(lines), encoding="utf-8")
    (tmp_path / "otra.py").write_text("def g():\n    pass\n", encoding="utf-8")
    m = build_map(analyze(tmp_path).project)
    file_gid = next(gid for gid, g in m["groups"].items() if g["name"] == "muchas.py")
    kids = m["groups"][file_gid]["layout"]["nodes"]
    assert len(kids) == MAX_CHILDREN
    others = [n for n in kids if n[1] == "otros"]
    assert len(others) == 1 and others[0][6] == "Otros (6)"
    assert len(m["groups"][others[0][0]]["layout"]["nodes"]) == 6
    assert m["groups"][others[0][0]]["parent"] == file_gid


def test_map_is_deterministic():
    a = build_map(analyze(LARAVEL).project)
    b = build_map(analyze(LARAVEL).project)
    assert a == b
