"""Diagrama de clases UML (Bloque 4): miembros, visibilidad y relaciones por lenguaje.

Cada fixture de `tests/fixtures/uml/<lenguaje>/` describe lo mismo: `Figura` (abstracta,
con un atributo protegido y un contador estático privado), `Circulo` (hereda de Figura,
implementa Dibujable, tiene un `Punto`), la interfaz `Dibujable` y `Punto`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from desglosa import cli
from desglosa.pipeline import analyze
from desglosa.uml import (
    _uml_param,
    attr_text,
    build_class_model,
    build_uml,
    method_text,
)

FIXTURES = Path(__file__).parent / "fixtures" / "uml"
GOLDEN = Path(__file__).parent / "golden"
LANGS = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())


def _model(lang: str):
    classes, rels = build_class_model(analyze(FIXTURES / lang))
    by_name = {c.name: c for c in classes.values()}
    names = {c.id: c.name for c in classes.values()}
    edges = {(names[r.src], r.kind, names[r.dst]) for r in rels}
    return by_name, edges, rels


def _attrs(c) -> dict[str, str]:
    return {m.name.lstrip("_"): attr_text(m) for m in c.attributes}


def _methods(c) -> dict[str, object]:
    return {m.name: m for m in c.methods}


def test_all_languages_have_fixture():
    assert LANGS == ["cpp", "csharp", "go", "java", "javascript", "kotlin", "php", "python",
                     "ruby", "rust", "swift", "typescript"]


@pytest.mark.parametrize("lang", LANGS)
def test_circle_has_a_point(lang):
    """En todos los lenguajes Circulo tiene un atributo de tipo Punto → asociación."""
    classes, edges, rels = _model(lang)
    assert {"Circulo", "Punto"} <= set(classes)
    assert ("Circulo", "asociacion", "Punto") in edges
    label = next(r.label for r in rels if r.kind == "asociacion")
    assert label.lower() == "centro"


# Herencia e implementación según lo que cada lenguaje permite escribir.
RELATIONS = {
    "java": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "Dibujable")},
    "csharp": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "IDibujable")},
    "typescript": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "Dibujable")},
    "php": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "Dibujable")},
    "kotlin": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "Dibujable")},
    "swift": {("Circulo", "hereda", "Figura"), ("Circulo", "implementa", "Dibujable")},
    # C++ y Python no distinguen interfaz: una clase abstracta pura se hereda.
    "cpp": {("Circulo", "hereda", "Figura"), ("Circulo", "hereda", "Dibujable")},
    "python": {("Circulo", "hereda", "Figura"), ("Circulo", "hereda", "Dibujable")},
    "javascript": {("Circulo", "hereda", "Figura")},
    "ruby": {("Circulo", "hereda", "Figura")},
    # `impl Dibujable for Circulo` se declara fuera del struct.
    "rust": {("Circulo", "implementa", "Dibujable")},
    "go": set(),  # Go no declara la implementación: no se adivina
}


@pytest.mark.parametrize("lang", LANGS)
def test_inheritance_and_implementation(lang):
    _, edges, _ = _model(lang)
    assert {e for e in edges if e[1] != "asociacion"} == RELATIONS[lang]


@pytest.mark.parametrize("lang", ["java", "csharp", "typescript", "php", "cpp", "python",
                                  "kotlin"])
def test_abstract_class_and_method(lang):
    classes, _, _ = _model(lang)
    figura = classes["Figura"]
    assert figura.abstract
    area = next(m for m in figura.methods if m.name.lower() == "area")
    assert area.abstract
    total = next(m for m in figura.methods if m.name.lower() == "total")
    assert total.static and not total.abstract


@pytest.mark.parametrize("lang", LANGS)
def test_interface_methods_are_abstract(lang):
    classes, _, _ = _model(lang)
    iface = classes.get("Dibujable") or classes.get("IDibujable")
    if iface is None:  # JavaScript y Ruby no tienen interfaces
        assert lang in ("javascript", "ruby")
        return
    assert iface.methods and all(m.abstract for m in iface.methods)


# Visibilidad de los atributos de Figura y Circulo: lo escrito o la regla del lenguaje.
VISIBILITY = {
    "java": {"nombre": "#", "contador": "-", "radio": "-", "centro": "+"},
    "csharp": {"Nombre": "#", "contador": "-", "radio": "-", "Centro": "+"},
    "typescript": {"nombre": "#", "contador": "-", "radio": "-", "centro": "+"},
    "php": {"nombre": "#", "contador": "-", "radio": "-", "centro": "+"},
    "cpp": {"nombre": "#", "contador": "-", "radio": "-", "centro": "+"},
    "kotlin": {"nombre": "#", "contador": "-", "radio": "-", "centro": "+"},
    "python": {"nombre": "#", "radio": "-", "centro": "+"},  # _x protegido, __x privado
    "swift": {"nombre": "~", "contador": "-", "radio": "-", "centro": "~"},  # internal
    "ruby": {"radio": "-", "centro": "+"},  # @x privado, attr_accessor público
    "javascript": {"secreto": "-", "centro": "+"},  # #secreto
    "go": {"radio": "~", "Centro": "+"},  # minúscula: del paquete
    "rust": {"radio": "-", "centro": "+"},  # sin `pub`: privado
}


@pytest.mark.parametrize("lang", LANGS)
def test_attribute_visibility(lang):
    classes, _, _ = _model(lang)
    members = {}
    for name in ("Figura", "Circulo"):
        if name in classes:
            members.update({m.name.lstrip("_"): m for m in classes[name].attributes})
    for name, vis in VISIBILITY[lang].items():
        assert members[name].visibility == vis, (lang, name)


@pytest.mark.parametrize("lang", ["java", "csharp", "typescript", "php", "cpp", "python",
                                  "kotlin", "swift", "ruby", "javascript"])
def test_static_counter(lang):
    classes, _, _ = _model(lang)
    contador = next(m for m in classes["Figura"].attributes if m.name.lower() == "contador")
    assert contador.static


def test_java_box_texts():
    classes, _, _ = _model("java")
    assert _attrs(classes["Figura"]) == {"nombre": "# nombre: String",
                                         "contador": "- contador: int"}
    texts = [method_text(m) for m in classes["Circulo"].methods]
    assert texts == ["+ Circulo(nombre: String, radio: double)", "+ area(): double",
                     "+ dibujar()", "- esValido(): boolean"]
    assert _attrs(classes["Punto"]) == {"x": "~ x: int", "y": "~ y: int"}  # sin modificador


def test_untyped_attribute_takes_type_from_constructor_call():
    """`self.centro = Punto()`, `@centro = Punto.new`, `this.centro = new Punto()`."""
    for lang in ("python", "ruby", "javascript", "swift"):
        classes, _, _ = _model(lang)
        centro = next(m for m in classes["Circulo"].attributes if m.name == "centro")
        assert centro.type == "Punto", lang


@pytest.mark.parametrize(("param", "lang", "expected"), [
    ("String nombre", "java", "nombre: String"),
    ("final @NotNull List<String> xs", "java", "xs: List<String>"),
    ("Map<String, Integer> m", "java", "m: Map<String, Integer>"),
    ("ref int n", "csharp", "n: int"),
    ("const std::string& s", "cpp", "s: std::string&"),
    ("int *p", "cpp", "p: int*"),
    ("?int $x = null", "php", "x: ?int = null"),
    ("$x", "php", "x"),
    ("private readonly Repo $r", "php", "r: Repo"),
    ("radio float64", "go", "radio: float64"),
    ("nombre: str", "python", "nombre: str"),  # ya está en notación UML
    ("{a, b}", "javascript", "{a, b}"),
])
def test_params_in_uml_notation(param, lang, expected):
    assert _uml_param(param, lang) == expected


def test_promoted_constructor_parameters_are_attributes():
    """PHP 8 y TypeScript declaran atributos en los parámetros del constructor."""
    root = Path(__file__).parent.parent / "examples" / "laravel-mini"
    classes, rels = build_class_model(analyze(root))
    by_name = {c.name: c for c in classes.values()}
    assert _attrs(by_name["FacturaController"]) == {
        "servicio": "- servicio: FacturacionService"}
    names = {c.id: c.name for c in classes.values()}
    assert ("FacturaController", "asociacion", "FacturacionService") in {
        (names[r.src], r.kind, names[r.dst]) for r in rels}


def test_diagram_per_folder_with_ghosts():
    root = Path(__file__).parent.parent / "examples" / "laravel-mini"
    index, diagrams = build_uml(analyze(root))
    assert set(index) == set(diagrams) == {
        "app/Http/Controllers", "app/Models", "app/Repositories", "app/Services"}
    d = diagrams["app/Services"]
    own = {c[7] for c in d["classes"] if not c[10]}
    ghosts = {c[7]: c[11] for c in d["classes"] if c[10]}
    assert own == {"FacturacionService", "CalculadoraImpuestos"}
    # Las clases de otras carpetas que se relacionan aparecen como fantasmas.
    assert ghosts == {"FacturaController": "app/Http/Controllers",
                      "FacturaRepository": "app/Repositories"}
    # Toda arista tiene puntos y termina dentro del lienzo.
    for edge in d["edges"]:
        pts = edge[2]
        assert len(pts) >= 4
        assert all(0 <= v <= max(d["w"], d["h"]) + 1 for v in pts)


def test_inheritance_arrow_ends_at_base():
    """La flecha de herencia termina en la base (ahí va el triángulo hueco)."""
    _, diagrams = build_uml(analyze(FIXTURES / "java"))
    d = diagrams[""]
    boxes = {c[0]: c for c in d["classes"]}
    for _src, dst, pts, kind, *_ in d["edges"]:
        if kind == "asociacion":
            continue
        base = boxes[dst]
        x, y = pts[-2], pts[-1]
        bx, by, bw, bh = base[2], base[3], base[4], base[5]
        assert bx - 1 <= x <= bx + bw + 1 and by - 1 <= y <= by + bh + 1


def test_mermaid_golden():
    _, diagrams = build_uml(analyze(FIXTURES / "java"))
    text = diagrams[""]["mermaid"]
    golden = GOLDEN / "uml" / "java.mmd"
    assert text == golden.read_text(encoding="utf-8")


def test_mermaid_ghosts_have_no_members():
    root = Path(__file__).parent.parent / "examples" / "laravel-mini"
    _, diagrams = build_uml(analyze(root))
    text = diagrams["app/Services"]["mermaid"]
    assert "    class FacturaRepository\n    <<interface>> FacturaRepository\n" in text
    assert "    class FacturaController\n" in text
    assert "+__construct(repositorio, impuestos)" in text  # sin cortar


def test_deterministic():
    a = build_uml(analyze(FIXTURES / "typescript"))
    b = build_uml(analyze(FIXTURES / "typescript"))
    assert a == b


def test_cli_classes(tmp_path, capsys):
    root = Path(__file__).parent.parent / "examples" / "laravel-mini"
    out = tmp_path / "c.mmd"
    code = cli.main(["clases", str(root), "--carpeta", "app/Services", "--mermaid",
                     "-o", str(out), "--no-cache"])
    assert code == cli.EXIT_OK
    assert out.read_text(encoding="utf-8").startswith('---\ntitle: "Clases de app/Services"')
    assert cli.main(["clases", str(root), "--carpeta", "nada", "--no-cache"]) == (
        cli.EXIT_NOT_FOUND)
    assert "app/Services (2)" in capsys.readouterr().err
    html = tmp_path / "c.html"
    assert cli.main(["clases", str(root), "-o", str(html), "--no-cache"]) == cli.EXIT_OK
    page = html.read_text(encoding="utf-8")
    assert '"start":"#\\/clases\\/app\\/Http\\/Controllers"' in page
