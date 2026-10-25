"""Títulos de los README como notas de su carpeta en el mapa (Bloque 2, punto 7)."""

from __future__ import annotations

from desglosa.macro import build_map
from desglosa.notes import project_dirs, readme_notes, readme_summary
from desglosa.pipeline import analyze
from tests.conftest import needs_grammars


def test_summary_skips_badges_html_and_code():
    text = (
        "# Desglosa\n\n"
        "[![CI](https://x/badge.svg)](https://x)\n"
        '<p align="center"><img src="logo.png"></p>\n\n'
        "```bash\npip install algo\n```\n\n"
        "**Convierte** tu código en un [mapa](https://x) interactivo.\n\n"
        "Más texto que no se usa.\n"
    )
    assert readme_summary(text) == "Desglosa: Convierte tu código en un mapa interactivo."


def test_summary_rst_plain_and_limits():
    assert readme_summary("Pagos\n=====\n\nCobra con tarjeta.\n") == "Pagos: Cobra con tarjeta."
    assert readme_summary("Utilidades para fechas.\n") == "Utilidades para fechas."
    assert readme_summary("# Solo título\n") == "Solo título"
    assert readme_summary("\n\n") is None
    long = readme_summary("# T\n\n" + "palabra " * 80)
    assert len(long) == 200 and long.endswith("…")


def test_summary_drops_linked_badges_and_keeps_first_sentence():
    text = (
        "# Spring PetClinic [![Build](https://x/b.svg)](https://x/ci)![Cov](https://x/c.svg)\n\n"
        "Petclinic is a Spring Boot application built using Maven. You can build a jar.\n"
    )
    assert readme_summary(text) == (
        "Spring PetClinic: Petclinic is a Spring Boot application built using Maven."
    )
    # Una primera frase muy corta no se corta (quedaría sin sentido).
    assert readme_summary("Hola. Esto sigue.\n") == "Hola. Esto sigue."


def test_project_dirs_includes_parents():
    assert project_dirs(["a/b/c.py", "d.py"]) == {"", "a", "a/b"}


def test_readme_notes_reads_each_folder(tmp_path):
    (tmp_path / "README.md").write_text("# Tienda\n\nVende cosas.\n", encoding="utf-8")
    (tmp_path / "pagos").mkdir()
    (tmp_path / "pagos" / "readme.md").write_text("Cobros y reembolsos.\n", encoding="utf-8")
    (tmp_path / "otro").mkdir()
    notes = readme_notes(tmp_path, ["", "pagos", "otro", "no-existe"])
    assert notes == {"": "Tienda: Vende cosas.", "pagos": "Cobros y reembolsos."}


@needs_grammars
def test_readme_becomes_note_of_its_map_folder(tmp_path):
    (tmp_path / "pagos").mkdir()
    (tmp_path / "pagos" / "README.md").write_text("# Pagos\n\nCobra.\n", encoding="utf-8")
    (tmp_path / "pagos" / "cobro.py").write_text("def cobrar():\n    return 1\n", encoding="utf-8")
    (tmp_path / "ventas").mkdir()
    (tmp_path / "ventas" / "venta.py").write_text(
        "from pagos.cobro import cobrar\n\n\ndef vender():\n    return cobrar()\n",
        encoding="utf-8",
    )
    a = analyze(tmp_path)
    assert a.readmes == {"pagos": "Pagos: Cobra."}
    m = build_map(a.project, None, a.readmes)
    docs = {g["name"]: g.get("doc") for g in m["groups"].values()}
    assert docs["pagos"] == "Pagos: Cobra."
    assert docs["ventas"] is None
