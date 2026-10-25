from __future__ import annotations

from pathlib import Path

import pytest

from desglosa.architecture import (
    MAX_PER_LAYER,
    analyze_architecture,
    build_architecture,
    classify,
    is_test,
    words,
)
from desglosa.ir import Call, Import, Project, SourceFile, Symbol
from desglosa.macro import build_map
from tests.conftest import needs_grammars

ROOT = Path(__file__).resolve().parent.parent


def test_words():
    assert words("MySqlFacturaRepository") == ["my", "sql", "factura", "repository"]
    assert words("factura_service") == ["factura", "service"]
    assert words("HTTPClient2") == ["http", "client", "2"]


@pytest.mark.parametrize(
    ("name", "path", "entry", "layer"),
    [
        ("FacturaController", "app/X.php", False, "entrada"),
        ("pago_service", "pago_service.py", False, "logica"),
        ("CrearPedidoUseCase", "x/CrearPedidoUseCase.java", False, "logica"),
        ("MySqlFacturaRepository", "a/b.php", False, "datos"),
        ("ServicioPago", "ServicioPago.cs", False, "logica"),
        ("RepositorioCliente", "RepositorioCliente.java", False, "datos"),
        ("views", "blog/views.py", False, "entrada"),
        ("models", "blog/models.py", False, "datos"),
        ("Factura", "app/Models/Factura.php", False, "datos"),  # por la carpeta
        ("Helper", "src/services/helpers/Helper.ts", False, "logica"),  # carpeta más cercana
        ("gps", "gps.c", True, "entrada"),  # tiene main
    ],
)
def test_classify(name, path, entry, layer):
    found = classify(name, path, entry)
    assert found is not None and found[0] == layer
    assert found[1]  # siempre con motivo


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        ("DatabaseEloquentModelTest", "tests/Database/X.php", True),
        ("FacturaTest", "src/FacturaTest.java", True),
        ("test_pago", "test_pago.py", True),
        ("pago_spec", "src/pago.spec.ts", True),
        ("Helper", "app/__tests__/helper.js", True),
        ("Testing", "src/Illuminate/Testing/Testing.php", False),
        ("Contest", "app/Contest.php", False),
        ("FacturaController", "app/Http/FacturaController.php", False),
    ],
)
def test_is_test(name, path, expected):
    assert is_test(name, path) is expected


def test_classify_unknown():
    assert classify("Factura", "src/factura.py") is None
    assert classify("utils", "lib/utils.js") is None


def test_reason_keeps_original_spelling():
    assert classify("FacturaController", "x.php") == (
        "entrada", "el nombre termina en «Controller»"
    )
    assert classify("Factura", "app/Models/Factura.php")[1] == "está en la carpeta Models/"


@needs_grammars
def test_laravel_mini_layers_and_edges():
    from desglosa.pipeline import analyze

    a = analyze(ROOT / "examples" / "laravel-mini")
    routes = [(r.file, r.symbol_id) for r in a.routes if r.symbol_id]
    model = analyze_architecture(a.project, routes)
    layers = {c.name: c.layer for c in model.components.values()}
    assert layers["FacturaController"] == "entrada"
    assert layers["FacturacionService"] == "logica"
    assert layers["MySqlFacturaRepository"] == "datos"
    assert layers["Factura"] == "datos"
    arch = build_architecture(a.project, routes, build_map(a.project, routes))
    assert [c[0] for c in arch["columns"]] == [
        "Rutas", "Entrada", "Lógica", "Datos", "Base de datos"
    ]
    names = {n[0]: n[6] for n in arch["nodes"]}
    assert "Controller" not in names.values()  # clase base vacía y sin relaciones
    assert list(names.values()).count("web.php") == 1  # solo como "Rutas"
    edges = {(names[e[0]], names[e[1]]): e for e in arch["edges"]}
    assert edges[("FacturaController", "FacturacionService")][3] == "probable"
    assert edges[("web.php", "FacturaController")][11] == "3 rutas"
    assert edges[("MySqlFacturaRepository", "Tablas SQL")][11] == "lee y escribe"
    assert ("MySqlFacturaRepository", "Base de datos SQL") in edges  # importa PDO
    # Las columnas van de izquierda a derecha en el orden de las capas.
    xs = [c[1] for c in arch["columns"]]
    assert xs == sorted(xs)
    assert arch == build_architecture(a.project, routes, build_map(a.project, routes))


@needs_grammars
def test_single_layer_project_has_no_architecture():
    from desglosa.pipeline import analyze

    a = analyze(ROOT / "examples" / "gps-c")
    assert build_architecture(a.project) is None


def _sym(sid, kind, name, file, parent=None, line=1):
    return Symbol(sid, kind, name, name, file, line, line + 5, parent, None, "php", name)


def test_crowded_layer_goes_to_otros():
    symbols, calls, files = [], [], []
    n = MAX_PER_LAYER + 6
    files.append(SourceFile("app/Services/PagoService.php", "php", "0", 10, True, 0))
    symbols += [
        _sym("svc", "class", "PagoService", "app/Services/PagoService.php"),
        _sym("svc.m", "method", "cobrar", "app/Services/PagoService.php", "svc", 2),
    ]
    for i in range(n):
        path = f"app/Http/C{i:02d}Controller.php"
        files.append(SourceFile(path, "php", "0", 10, True, 0))
        symbols += [
            _sym(f"c{i}", "class", f"C{i:02d}Controller", path),
            _sym(f"c{i}.m", "method", "store", path, f"c{i}", 2),
        ]
        for k in range(i + 1):  # los últimos llaman más: quedan a la vista
            calls.append(Call(f"k{i}_{k}", f"c{i}.m", "cobrar", None, 3 + k, 1,
                              resolved_id="svc.m", confidence="exacta"))
    p = Project("p", tuple(files), tuple(symbols), (Import(files[0].path, "redis", None, 1),),
                tuple(calls))
    arch = build_architecture(p)
    entrada = [nd for nd in arch["nodes"] if nd[0].startswith("c") or nd[0] == "o:entrada"]
    assert len(entrada) == MAX_PER_LAYER
    otros = next(nd for nd in arch["nodes"] if nd[0] == "o:entrada")
    assert otros[6] == f"Otros ({n - MAX_PER_LAYER + 1})"
    edge = next(e for e in arch["edges"] if e[0] == "o:entrada")
    assert edge[11] == f"{sum(range(1, n - MAX_PER_LAYER + 2))} llamadas"
    assert any(nd[6] == "Redis" for nd in arch["nodes"])


@needs_grammars
def test_report_architecture_section():
    from desglosa.pipeline import analyze
    from desglosa.report import build_report

    text = build_report(analyze(ROOT / "examples" / "laravel-mini"))
    section = text.split("## Arquitectura", 1)[1].split("\n## ", 1)[0]
    assert "| Entrada | FacturaController |" in section
    assert "| Base de datos SQL | `app/Repositories/MySqlFacturaRepository.php` |" in section
    assert "## Arquitectura" not in build_report(analyze(ROOT / "examples" / "gps-c"))


def test_drawn_labels_never_overlap():
    symbols, calls, files = [], [], []
    for i in range(6):  # 6 controladores que llaman a 2 servicios: etiquetas en el mismo hueco
        path = f"app/Http/C{i}Controller.php"
        files.append(SourceFile(path, "php", "0", 10, True, 0))
        symbols += [_sym(f"c{i}", "class", f"C{i}Controller", path),
                    _sym(f"c{i}.m", "method", "store", path, f"c{i}", 2)]
    for j in range(2):
        path = f"app/Services/S{j}Service.php"
        files.append(SourceFile(path, "php", "0", 10, True, 0))
        symbols += [_sym(f"s{j}", "class", f"S{j}Service", path),
                    _sym(f"s{j}.m", "method", "run", path, f"s{j}", 2)]
        for i in range(6):
            calls.append(Call(f"k{i}{j}", f"c{i}.m", "run", None, 3, j, resolved_id=f"s{j}.m",
                              confidence="exacta"))
    arch = build_architecture(Project("p", tuple(files), tuple(symbols), (), tuple(calls)))
    boxes = [e[5:9] for e in arch["edges"] if e[4]]
    for i, (x, y, w, h) in enumerate(boxes):
        for px, py, pw, ph in boxes[i + 1:]:
            assert x + w <= px or px + pw <= x or y + h <= py or py + ph <= y
    assert all(e[11] for e in arch["edges"])  # el texto completo siempre está (tooltip)
