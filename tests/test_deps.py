"""Dependencias entre módulos (Bloque 4): ciclos, capas que se saltan y `desglosa check`.

- `fixtures/deps/tienda`: un ciclo `services ↔ utils` (el correo vuelve a llamar al
  servicio) y un controlador que va directo al repositorio que ya usa el servicio.
- `fixtures/deps2`: casos que NO deben marcarse: un controlador sin servicio que use su
  repositorio (como Petclinic), un `x.groups()` que solo coincide por el nombre con un
  método del proyecto, y migraciones de Django que se llaman todas `Migration`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.deps import (
    BASE_FILE,
    dependency_report,
    find_cycles,
    payload,
    strongly_connected,
)
from desglosa.pipeline import AnalyzeOptions, analyze
from desglosa.scan import ScanOptions
from desglosa.uml import build_class_model

FIXTURES = Path(__file__).parent / "fixtures"


def _analysis(name: str):
    return analyze(FIXTURES / name, AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=None,
                                                   flows=False))


@pytest.fixture(scope="module")
def tienda():
    return dependency_report(_analysis("deps"))


def test_cycle_between_folders_and_files(tienda):
    folders = [c for c in tienda.folder_cycles]
    assert [c.path for c in folders] == [("tienda/services", "tienda/utils", "tienda/services")]
    steps = [(s.at, s.why) for s in folders[0].steps]
    assert steps == [
        ("tienda/services/pedido_service.py:13", "PedidoService.crear llama a avisar"),
        ("tienda/utils/correo.py:7", "avisar llama a PedidoService.es_valido"),
    ]
    assert [c.members for c in tienda.file_cycles] == [
        ("tienda/services/pedido_service.py", "tienda/utils/correo.py")]


def test_skipped_layer_names_the_service(tienda):
    assert len(tienda.skips) == 1
    s = tienda.skips[0]
    assert (s.src, s.dst, s.via) == ("PedidoController", "PedidoRepository", "PedidoService")
    # Se muestra la llamada a un método, no la creación del objeto en __init__.
    assert s.step.why == "PedidoController.listar llama a PedidoRepository.todos"
    assert s.step.at == "tienda/controllers/pedido_controller.py:17"


def test_no_false_positives():
    report = dependency_report(_analysis("deps2"))
    assert report.cycles == []  # `coincidencia.groups()` no cuenta como dependencia
    assert report.skips == []  # ningún servicio usa OwnerRepository: no se salta nada


def test_migrations_inherit_from_the_framework_class():
    """`class Migration(migrations.Migration)` no hereda de la migración vecina."""
    classes, rels = build_class_model(_analysis("deps2"))
    inherits = sorted((classes[r.src].file, classes[r.dst].file) for r in rels
                      if r.kind == "hereda")
    assert inherits == [("app/migrations/m0001.py", "db/migrations/migration.py"),
                        ("app/migrations/m0002.py", "db/migrations/migration.py")]


def test_no_cycles_in_the_laravel_example():
    report = dependency_report(analyze(Path("examples") / "laravel-mini",
                                       AnalyzeOptions(scan=ScanOptions(), flows=False)))
    assert report.cycles == [] and report.skips == [] and report.n_edges > 0


def test_tarjan_without_recursion_limit():
    n = 5000  # una cadena larga y un ciclo grande: sin recursión de Python
    adj = {str(i): [str(i + 1)] for i in range(n)}
    adj[str(n)] = ["0"]
    comps = strongly_connected(sorted(adj), adj)
    assert [len(c) for c in comps] == [n + 1]


def test_shortest_cycle_is_shown():
    from desglosa.deps import Step

    edges = {(a, b): Step(a, b, f"{a}->{b}", a) for a, b in [
        ("a", "b"), ("b", "c"), ("c", "a"), ("b", "a"), ("c", "d")]}
    (cycle,) = find_cycles(edges, "archivo")
    assert cycle.members == ("a", "b", "c")
    assert cycle.path == ("a", "b", "a")  # el más corto dentro del nudo


def test_payload_for_the_viewer(tienda):
    data = payload(tienda)
    assert data["n_ciclos"] == 2 and data["n_capas"] == 1
    assert data["ciclos"][0]["pasos"][0][2]  # id de la función que llama (enlace al flujo)
    text, why, at, sid, src, dst = data["capas"][0]
    assert "sin pasar por PedidoService" in text and src and dst


def test_check_fails_then_accepts(tmp_path, capsys):
    root = FIXTURES / "deps"
    base = tmp_path / BASE_FILE
    assert cli.main(["check", str(root), "--base", str(base)]) == cli.EXIT_CHECK
    out = capsys.readouterr().out
    assert "NUEVO [carpeta] tienda/services -> tienda/utils -> tienda/services" in out
    assert "Resultado: FALLA" in out
    assert cli.main(["check", str(root), "--base", str(base), "--aceptar"]) == cli.EXIT_OK
    saved = json.loads(base.read_text(encoding="utf-8"))
    assert saved["ciclos"] == ["archivo:tienda/services/pedido_service.py|tienda/utils/correo.py",
                               "carpeta:tienda/services|tienda/utils"]
    capsys.readouterr()
    assert cli.main(["check", str(root), "--base", str(base)]) == cli.EXIT_OK
    assert "2 ya aceptados" in capsys.readouterr().out
    # Las capas saltadas solo hacen fallar con --capas (y aquí ya están aceptadas).
    assert cli.main(["check", str(root), "--base", str(base), "--capas"]) == cli.EXIT_OK


def test_check_json_and_gone_entries(tmp_path, capsys):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"ciclos": ["carpeta:viejo|otro"], "capas": []}), encoding="utf-8")
    code = cli.main(["check", str(Path("examples") / "laravel-mini"), "--base", str(base),
                     "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK and data["ok"] is True
    assert data["ya_no_estan"] == ["carpeta:viejo|otro"]


def test_skipped_layers_fail_only_with_flag(tmp_path, capsys):
    root = FIXTURES / "deps"
    base = tmp_path / "b.json"
    base.write_text(json.dumps({"ciclos": [
        "archivo:tienda/services/pedido_service.py|tienda/utils/correo.py",
        "carpeta:tienda/services|tienda/utils"]}), encoding="utf-8")
    assert cli.main(["check", str(root), "--base", str(base)]) == cli.EXIT_OK
    assert cli.main(["check", str(root), "--base", str(base), "--capas"]) == cli.EXIT_CHECK
    assert "NUEVO PedidoController (Entrada) -> PedidoRepository" in capsys.readouterr().out


def test_report_and_html_include_dependencies(tmp_path):
    out, rep = tmp_path / "d.html", tmp_path / "d.md"
    assert cli.main(["analyze", str(FIXTURES / "deps"), "-o", str(out), "--report", str(rep),
                     "--no-cache"]) == cli.EXIT_OK
    text = rep.read_text(encoding="utf-8")
    assert "## Dependencias entre módulos" in text and "**Ciclos: 2**" in text
    from desglosa.render.packs import unpack
    from tests.test_html import _raw

    index = unpack(_raw(out.read_text(encoding="utf-8"))["index"])
    assert index["deps"]["n_ciclos"] == 2
