"""HTML generado: autocontenido, determinista y seguro (RF-01, RNF-02, RNF-04)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.render.html import safe_json
from tests.conftest import FIXTURES, needs_grammars

pytestmark = needs_grammars

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "src" / "desglosa" / "render" / "app.js"
SVG_NS = "http://www.w3.org/2000/svg"


def _flow_html(tmp_path: Path, target: Path, func: str, name: str = "f.html") -> str:
    out = tmp_path / name
    assert cli.main(["flow", str(target), func, "-o", str(out)]) == cli.EXIT_OK
    return out.read_text(encoding="utf-8")


def _data(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="desglosa-data">(.*?)</script>', page, re.S)
    assert m, "no está el bloque de datos"
    return json.loads(m.group(1))


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


@pytest.mark.parametrize("spec", ["gps.c:no_existe", "nada"])
def test_flow_command_unknown_function(tmp_path, spec):
    out = tmp_path / "x.html"
    assert cli.main(["flow", str(ROOT / "examples" / "gps-c"), spec, "-o", str(out)]) == 1
