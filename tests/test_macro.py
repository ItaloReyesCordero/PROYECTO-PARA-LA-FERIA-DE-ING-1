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


def test_routes_become_map_edges(laravel):
    a, plain = laravel
    routes = [(r.file, r.symbol_id) for r in a.routes if r.symbol_id]
    m = build_map(a.project, routes)
    root = m["groups"][m["root"]]["layout"]
    by_id = {n[0]: n[6] for n in root["nodes"]}
    labels = {(by_id[e[0]], by_id[e[1]]): e[4] for e in root["edges"]}
    assert labels.get(("routes/", "app/")) == "3 rutas"
    # Sin pasar las rutas, el archivo de rutas queda suelto (no hace llamadas resueltas).
    assert plain["groups"][plain["root"]]["layout"]["edges"] == []


def test_map_skips_calls_with_too_many_candidates():
    from desglosa.ir import Call, Project, SourceFile, Symbol

    def fn(sid, file):
        return Symbol(sid, "function", "f" + sid, "f" + sid, file, 1, 3, None, None, "python", "")

    targets = [fn(f"t{i}", f"m{i}/a.py") for i in range(6)]
    caller = fn("c", "main/x.py")
    files = tuple(SourceFile(s.file, "python", "x", 3, True, 0) for s in [caller, *targets])
    many = Call("k", "c", "f", None, 2, 5, candidates=tuple(t.id for t in targets),
                confidence="ambigua")
    few = Call("k2", "c", "f", None, 3, 5, candidates=("t0", "t1"), confidence="ambigua")
    for calls, expected in (((many,), 0), ((few,), 2)):
        m = build_map(Project("p", files=files, symbols=(caller, *targets), calls=calls))
        assert len(m["groups"][m["root"]]["layout"]["edges"]) == expected


def test_many_children_are_bucketed_not_chained():
    """220 carpetas: grupos alfabéticos parejos, no una cadena de "Otros" dentro de "Otros"."""
    from desglosa.ir import Project, SourceFile, Symbol

    files, symbols = [], []
    for i in range(220):
        path = f"tests/d{i:03d}/a.py"
        files.append(SourceFile(path, "python", "x", 3, True, 0))
        mod = Symbol(f"m{i}", "module", "a", "a", path, 1, 3, None, None, "python", "")
        fn = Symbol(f"f{i}", "function", f"f{i}", f"f{i}", path, 1, 3, f"m{i}", None, "python", "")
        symbols += [mod, fn]
    m = build_map(Project("p", files=tuple(files), symbols=tuple(symbols)))
    groups = m["groups"]
    assert all(len(g["layout"]["nodes"]) <= MAX_CHILDREN for g in groups.values())
    depth_otros = []
    for i in range(220):
        el, n = m["owner"][f"f{i}"], 0
        while el is not None:
            n += groups[el]["kind"] == "otros"
            el = groups[el]["parent"]
        depth_otros.append(n)
    assert max(depth_otros) <= 3
    labels = [g["name"] for g in groups.values() if g["kind"] == "otros"]
    assert any(name.startswith("Otros: d0") for name in labels)
