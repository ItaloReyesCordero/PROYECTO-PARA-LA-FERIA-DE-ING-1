"""HTML generado: autocontenido, determinista y seguro (RF-01, RNF-02, RNF-04)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.render.html import safe_json
from desglosa.render.packs import FORMAT, pack, unpack, unpacked
from tests.conftest import FIXTURES, needs_grammars

pytestmark = needs_grammars

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "src" / "desglosa" / "render" / "app.js"
SVG_NS = "http://www.w3.org/2000/svg"


def _flow_html(tmp_path: Path, target: Path, func: str, name: str = "f.html") -> str:
    out = tmp_path / name
    assert cli.main(["flow", str(target), func, "-o", str(out)]) == cli.EXIT_OK
    return out.read_text(encoding="utf-8")


def _raw(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="desglosa-data">(.*?)</script>', page, re.S)
    assert m, "no está el bloque de datos"
    return json.loads(m.group(1))


def _data(page: str) -> dict:
    """Los datos con los paquetes por archivo ya abiertos."""
    return unpacked(_raw(page))


def test_no_external_urls(tmp_path):
    page = _flow_html(tmp_path, FIXTURES / "xss", "app.py:saludar")
    rest = page.replace(SVG_NS, "")
    assert "http://" not in rest
    assert "https://" not in rest
    assert "example.com" in _data(page)["sources"]["app.py"]  # la URL sigue en los datos


def test_script_injection_is_escaped(tmp_path):
    page = _flow_html(tmp_path, FIXTURES / "xss", "app.py:saludar")
    assert page.count("<script") == 2  # datos + visor; nada inyectado
    assert "alert(1)</script>" not in page
    assert " " not in page and " " not in page
    data = _data(page)
    assert "</script><script>alert(1)</script>" in data["sources"]["app.py"]
    assert "{{DATA}}" in data["sources"]["app.py"]


def test_safe_json_roundtrip():
    value = {"a": "</script>&<>  /ñ"}
    text = safe_json(value)
    for bad in ("<", ">", "&", " ", " ", "/"):
        assert bad not in text.replace("\\/", "")
    assert json.loads(text) == value


def test_app_never_uses_innerhtml():
    js = APP_JS.read_text(encoding="utf-8")
    assert "innerHTML" not in js
    assert "outerHTML" not in js
    assert "insertAdjacentHTML" not in js
    assert "eval(" not in js


def test_html_deterministic(tmp_path):
    a = _flow_html(tmp_path, ROOT / "examples" / "gps-c", "gps.c:main", "a.html")
    b = _flow_html(tmp_path, ROOT / "examples" / "gps-c", "gps.c:main", "b.html")
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def test_flow_command_includes_reachable_flows(tmp_path):
    page = _flow_html(tmp_path, ROOT / "examples" / "gps-c", "gps.c:main")
    data = _data(page)
    names = {data["symbols"][sid]["name"] for sid in data["flows"]}
    assert {"main", "DesglosaGPRMC", "imprimir_campos"} <= names
    assert data["meta"]["start"].startswith("#/flujo/")


def test_analyze_command(tmp_path, capsys):
    out = tmp_path / "demo.html"
    target = ROOT / "examples" / "laravel-mini"
    assert cli.main(["analyze", str(target), "-o", str(out)]) == cli.EXIT_OK
    page = out.read_text(encoding="utf-8")
    data = _data(page)
    assert data["meta"]["start"] == "#/mapa"
    assert data["map"]["root"] in data["map"]["groups"]
    assert len(data["flows"]) >= 10
    assert "app/Http/Controllers/FacturaController.php" in data["sources"]
    # "Trazar ruta" necesita la línea de cada llamada: [destino, confianza, línea].
    by_name = {s["qualname"]: sid for sid, s in data["symbols"].items()}
    store, emitir = by_name["FacturaController.store"], by_name["FacturacionService.emitir"]
    assert [emitir, "probable", 33] in data["calls_out"][store]
    assert [store, "probable", 33] in data["calls_in"][emitir]
    assert data["arch"]["columns"][0][0] == "Rutas"
    assert "HTML escrito" in capsys.readouterr().out
    again = tmp_path / "otra.html"
    assert cli.main(["analyze", str(target), "-o", str(again)]) == cli.EXIT_OK
    assert again.read_bytes() == out.read_bytes()


def test_analyze_no_source(tmp_path):
    out = tmp_path / "demo.html"
    target = ROOT / "examples" / "laravel-mini"
    assert cli.main(["analyze", str(target), "-o", str(out), "--no-source"]) == cli.EXIT_OK
    assert _data(out.read_text(encoding="utf-8"))["sources"] == {}


def test_flow_legend_lists_only_present_kinds(tmp_path):
    page = _flow_html(tmp_path, ROOT / "examples" / "gps-c", "gps.c:main")
    for flow in _data(page)["flows"].values():
        kinds = {n["kind"] for n in flow["nodes"].values()}
        lay = flow["layout"]
        if lay["connectors"]:
            kinds.add("conector")
        if any(line[1] == "excepcion" for line in lay["lines"]):
            kinds.add("excepcion")
        assert set(lay["legend"]) == kinds


def test_flow_payload_has_graph_edges_for_the_walk(tmp_path):
    """El recorrido animado sigue las aristas del grafo, no las líneas dibujadas."""
    page = _flow_html(tmp_path, ROOT / "examples" / "gps-c", "gps.c:main")
    flows = _data(page)["flows"]
    main = max(flows.values(), key=lambda f: len(f["nodes"]))  # main es el flujo más grande
    ids = set(main["nodes"])
    assert main["edges"] and all(e[0] in ids and e[1] in ids for e in main["edges"])
    labels = {e[2] for e in main["edges"]}
    assert {"sí", "no"} <= labels
    assert any(e[3] == "retorno_bucle" for e in main["edges"])


@pytest.mark.parametrize("spec", ["gps.c:no_existe", "nada"])
def test_flow_command_unknown_function(tmp_path, spec):
    out = tmp_path / "x.html"
    assert cli.main(["flow", str(ROOT / "examples" / "gps-c"), spec, "-o", str(out)]) == 1


def test_pack_roundtrip_and_alphabet():
    value = {"b": [1.0, 2.5, "ñ</script>"], "a": {"x": None}}
    text = pack(value)
    assert set(text) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
    assert unpack(text) == {"a": {"x": None}, "b": [1, 2.5, "ñ</script>"]}
    assert pack(value) == text  # determinista


def test_diagrams_travel_in_compressed_packs(tmp_path):
    out = tmp_path / "demo.html"
    target = ROOT / "examples" / "laravel-mini"
    assert cli.main(["analyze", str(target), "-o", str(out)]) == cli.EXIT_OK
    page = out.read_text(encoding="utf-8")
    raw = _raw(page)
    assert raw["meta"]["format"] == FORMAT
    assert set(raw) == {"meta", "index", "packs"}  # todo lo demás va comprimido
    # Solo las rutas de archivo (nombres de los paquetes) quedan legibles; ni los nombres de
    # funciones ni el código aparecen sin comprimir.
    assert "FacturacionService.emitir" not in page
    assert "function emitir" not in page
    index = unpack(raw["index"])
    data = unpacked(raw)
    for sid, sym in index["symbols"].items():
        assert sym["flow"] == (sid in data["flows"])
    assert set(index["seq_ids"]) == set(data["sequence"])
    # Cada paquete tiene solo funciones de su archivo.
    for path, text in raw["packs"].items():
        assert all(index["symbols"][sid]["file"] == path for sid in unpack(text)["flows"])
