"""Pseudocódigo estilo PSeInt (Bloque 4).

Los goldens (`tests/golden/pseudo/*.psc`) son la salida de `desglosa pseudo` sobre los
programas de `tests/fixtures/pseudo/`; si un cambio los altera a propósito, se regeneran
con `uv run python tests/test_pseudo.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from desglosa import cli
from desglosa.pipeline import AnalyzeOptions, analyze
from desglosa.pseudo import (
    _range,
    condition,
    counting_for,
    expr,
    format_parts,
    negate,
    output_parts,
    rust_format_parts,
    simple,
)
from desglosa.scan import ScanOptions

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden" / "pseudo"
PROGRAMS = {"notas.c": "notas.psc", "tienda.py": "tienda.psc"}


def _cli_text(capsys, root: Path, name: str) -> str:
    assert cli.main(["pseudo", str(root), name, "--no-cache"]) == cli.EXIT_OK
    return capsys.readouterr().out


@pytest.mark.parametrize(("source", "golden"), sorted(PROGRAMS.items()))
def test_golden_programs(capsys, source, golden):
    text = _cli_text(capsys, FIXTURES / "pseudo", source)
    assert text == (GOLDEN / golden).read_text(encoding="utf-8")


def test_c_program_uses_pseint_structures(capsys):
    text = _cli_text(capsys, FIXTURES / "pseudo", "notas.c")
    assert "Algoritmo notas" in text and text.rstrip().endswith("FinAlgoritmo")
    assert "Para i <- 0 Hasta n - 1 Hacer" in text  # for (i = 0; i < n; i++)
    assert "Para i <- n - 1 Hasta 0 Con Paso -1 Hacer" in text  # cuenta hacia atrás
    assert "Hasta Que NO (n < 1 O n > MAX)" in text  # do { } while (…)
    assert "        4, 3:" in text  # casos que caen al siguiente
    assert "Definir n, opcion Como Entero" in text
    assert "Dimension notas[MAX]" in text
    assert 'Escribir nombre, " tiene promedio ", p' in text  # printf con formato
    assert 'Escribir Sin Saltar "Nombre: "' in text  # sin \n
    assert "Leer notas[i]" in text  # scanf("%d", &notas[i])
    assert 'Escribir "Letra: ", letra((int)p)' in text  # salida que llama a una función
    assert "// sale del bucle (break)" in text


def test_python_program(capsys):
    text = _cli_text(capsys, FIXTURES / "pseudo", "tienda.py")
    assert 'Escribir Sin Saltar "Cliente: "\n    Leer nombre' in text  # input("…")
    assert 'Escribir "Total de ", nombre, ": ", total, " soles"' in text  # f-string
    assert "Para k <- n Hasta 1 Con Paso -1 Hacer" in text  # range(n, 0, -1)
    assert "Mientras Verdadero Hacer" in text
    assert "Funcion resultado <- total_con_igv(precios, igv)" in text
    assert "SiNo\n        Si total > 50 Entonces" in text  # elif anidado: PSeInt no tiene


def test_return_variable_takes_the_returned_name(capsys):
    text = _cli_text(capsys, Path("examples") / "laravel-mini", "FacturacionService.emitir")
    assert "Funcion factura <- emitir(cliente, items, tipoPago)" in text
    assert "factura <- factura" not in text


# Las 12 versiones de FacturacionService.emitir (tests/fixtures/<lenguaje>/).
EMITIR = {
    "c": None, "cpp": "emitir", "csharp": "Emitir", "go": "Emitir", "java": "emitir",
    "javascript": "emitir", "kotlin": "emitir", "php": "emitir", "python": "emitir",
    "ruby": "emitir", "rust": "emitir", "swift": "emitir", "typescript": "emitir",
}


@pytest.mark.parametrize("lang", sorted(k for k, v in EMITIR.items() if v))
def test_every_language_translates_emitir(lang):
    a = analyze(FIXTURES / lang, AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=None))
    sym = next(s for s in a.project.symbols if s.name == EMITIR[lang] and s.kind == "method")
    text = a.flows[sym.id].pseudocode()
    assert text.startswith("Funcion resultado <- " + EMITIR[lang] + "(")
    assert text.rstrip().endswith("FinFuncion")
    assert 'Escribir "Factura vac' in text or "lanza un error" in text
    assert "Para Cada item de " in text or "Para " in text
    assert "Mientras intentos < 3 Y NO cobrado Hacer" in text or lang == "cpp"
    for word in ("&&", "||", "==", "!=", ";\n", "{\n"):
        assert word not in text, (lang, word)


def test_collapsed_flow_keeps_full_pseudocode():
    """Un flujo enorme se dibuja con bloques colapsados, pero el pseudocódigo va entero."""
    opts = AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=None, max_flow_nodes=8)
    a = analyze(FIXTURES / "pseudo", opts)
    main = next(s for s in a.project.symbols if s.name == "main" and s.file == "notas.c")
    flow = a.flows[main.id]
    assert flow.graph.truncated
    assert "Bloque" not in flow.pseudocode() and "Repetir" in flow.pseudocode()


def test_pseudocode_travels_in_the_flow_view(tmp_path):
    out = tmp_path / "p.html"
    assert cli.main(["analyze", str(FIXTURES / "pseudo"), "-o", str(out), "--no-cache"]) == 0
    a = analyze(FIXTURES / "pseudo", AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=None))
    views = [f.payload() for f in a.flows.values()]
    assert all(v["ps"].startswith(("Funcion", "Algoritmo")) for v in views)


def test_cache_keeps_pseudocode(tmp_path):
    opts = AnalyzeOptions(scan=ScanOptions(), jobs=1, cache_dir=tmp_path)
    first = analyze(FIXTURES / "pseudo", opts)
    second = analyze(FIXTURES / "pseudo", opts)  # sale de la caché
    assert {k: f.pseudocode() for k, f in first.flows.items()} == {
        k: f.pseudocode() for k, f in second.flows.items()}
    assert all(f.layout is None for f in second.flows.values())


# --------------------------------------------------------------------------- piezas


@pytest.mark.parametrize(("code", "lang", "expected"), [
    ("a == b && !c", "c", "a = b Y NO c"),
    ("x != 3 || y % 2 === 0", "javascript", "x <> 3 O y MOD 2 = 0"),
    ("not ok and n ** 2 > 4", "python", "NO ok Y n ^ 2 > 4"),
    ("a // b", "python", "trunc(a / b)"),
    ("$this->total + $iva", "php", "this.total + iva"),
    ("Math.sqrt(x) + abs(y)", "java", "raiz(x) + abs(y)"),
    ('s == "a && b"', "c", 's = "a && b"'),  # dentro de una cadena no se toca
    ("true", "kotlin", "Verdadero"),
])
def test_expressions(code, lang, expected):
    assert expr(code, lang) == expected


@pytest.mark.parametrize(("cond", "expected"), [
    ("a < b", "a >= b"),
    ("n = 0", "n <> 0"),
    ("ok", "NO ok"),
    ("NO ok", "ok"),
    ("a > 1 Y b > 2", "NO (a > 1 Y b > 2)"),
])
def test_negate(cond, expected):
    assert negate(cond) == expected


def test_condition_drops_outer_parens():
    assert condition("(x > 0)", "c") == "x > 0"
    assert condition("(a) + (b)", "c") == "(a) + (b)"
    assert condition("", "go") == "Verdadero"


@pytest.mark.parametrize(("init", "cond", "update", "expected"), [
    ("int i = 0", "i < n", "i++", ("i", "0", "n - 1", "1")),
    ("i = 1", "i <= 10", "i += 2", ("i", "1", "10", "2")),
    ("let i = n", "i > 0", "i--", ("i", "n", "1", "-1")),
    ("$i = 0", "$i < 5", "$i++", ("i", "0", "4", "1")),
    ("i := 0", "i < len(xs)", "i = i + 1", ("i", "0", "len(xs) - 1", "1")),
    ("i = 0", "i < n", "i *= 2", None),  # no cuenta de a pasos fijos
    ("i = 0", "j < n", "i++", None),  # otra variable
    ("i = 0", "i > n", "i++", None),  # nunca entraría: se deja como Mientras
])
def test_counting_for(init, cond, update, expected):
    assert counting_for(init, cond, update, "c") == expected


@pytest.mark.parametrize(("var", "coll", "lang", "expected"), [
    ("i", "range(5)", "python", ("i", "0", "4", "1")),
    ("i", "range(1, n + 1)", "python", ("i", "1", "n", "1")),
    ("i", "0 until n", "kotlin", ("i", "0", "n - 1", "1")),
    ("i", "10 downTo 1 step 2", "kotlin", ("i", "10", "1", "-2")),
    ("i", "1..=n", "rust", ("i", "1", "n", "1")),
    ("i", "0..<n", "swift", ("i", "0", "n - 1", "1")),
    ("i", "1..n", "ruby", ("i", "1", "n", "1")),
    ("x", "lista", "python", None),
])
def test_ranges(var, coll, lang, expected):
    assert _range(var, coll, lang) == expected


@pytest.mark.parametrize(("arg", "lang", "expected"), [
    ('f"Hola {nombre}, tienes {edad:d}"', "python", ['"Hola "', "nombre", '", tienes "', "edad"]),
    ("`Total: ${t}`", "javascript", ['"Total: "', "t"]),
    ('"Total: " + total + " soles"', "java", ['"Total: "', "total", '" soles"']),
    ('$"Hola {n}"', "csharp", ['"Hola "', "n"]),
    ('"Hola $nombre"', "kotlin", ['"Hola "', "nombre"]),
    ('"Hola \\(nombre)"', "swift", ['"Hola "', "nombre"]),
    ('"Hola #{nombre}"', "ruby", ['"Hola "', "nombre"]),
    ('"Total: " . $t', "php", ['"Total: "', "t"]),
    ("'Hola'", "python", ['"Hola"']),
])
def test_output_parts(arg, lang, expected):
    assert output_parts(arg, lang) == expected


def test_printf_and_rust_formats():
    assert format_parts('"%d de %s%%\\n"', ["a", "b"], "c") == (['a', '" de "', 'b', '"%"'], True)
    assert format_parts('"N: "', [], "c") == (['"N: "'], False)
    assert rust_format_parts('"{} y {x}"', ["a"]) == ["a", '" y "', "x"]


@pytest.mark.parametrize(("code", "lang", "expected"), [
    ("x++", "c", ["x <- x + 1"]),
    ("--n", "java", ["n <- n - 1"]),
    ("total += a * b", "python", ["total <- total + a * b"]),
    ("x *= (a - b)", "kotlin", ["x <- x * (a - b)"]),
    ("x *= a - b", "c", ["x <- x * (a - b)"]),
    ("const total = 0", "javascript", ["total <- 0"]),
    ("val x: Int = 5", "kotlin", ["x <- 5"]),
    ("var x int", "go", ["Definir x Como Entero"]),
    ("x := 3", "go", ["x <- 3"]),
    ("let x: number", "typescript", ["Definir x Como Real"]),
    ("$s .= 'a'", "php", ["s <- s + 'a'"]),
    ("pass", "python", []),
    ("procesar(datos)", "python", ["procesar(datos)"]),
])
def test_simple_statements(code, lang, expected):
    assert simple(code, lang) == expected


def _regenerate() -> None:  # pragma: no cover - herramienta para actualizar goldens
    import io
    from contextlib import redirect_stdout

    GOLDEN.mkdir(parents=True, exist_ok=True)
    for source, golden in PROGRAMS.items():
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["pseudo", str(FIXTURES / "pseudo"), source, "--no-cache"])
        (GOLDEN / golden).write_text(buf.getvalue(), encoding="utf-8", newline="\n")
        print("escrito", GOLDEN / golden, file=sys.stderr)


if __name__ == "__main__":
    _regenerate()
