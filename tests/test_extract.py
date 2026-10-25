from __future__ import annotations

import pytest

from desglosa.ir import dumps
from desglosa.pipeline import analyze
from tests.conftest import FIXTURES, needs_grammars

LANGS_F1 = (
    "c",
    "cpp",
    "csharp",
    "go",
    "java",
    "javascript",
    "kotlin",
    "php",
    "python",
    "ruby",
    "rust",
    "swift",
    "typescript",
)

pytestmark = needs_grammars


@pytest.fixture(scope="module")
def projects():
    return {lang: analyze(FIXTURES / lang).project for lang in LANGS_F1}


@pytest.mark.parametrize("lang", LANGS_F1)
def test_ir_golden(lang, projects, golden):
    golden(f"ir/{lang}.json", dumps(projects[lang]))


@pytest.mark.parametrize("lang", LANGS_F1)
def test_emitir_and_cobrar(lang, projects):
    p = projects[lang]
    by_id = {s.id: s for s in p.symbols}
    emitir = [s for s in p.symbols if s.name.lower() == "emitir"]
    assert len(emitir) == 1
    assert emitir[0].doc.lower().endswith("calcula el total, cobra y guarda la factura.")
    cobrar_calls = [c for c in p.calls if c.callee_text.lower() == "cobrar"]
    assert len(cobrar_calls) == 1
    call = cobrar_calls[0]
    assert call.caller_id == emitir[0].id
    assert call.resolved_id is not None, f"{lang}: cobrar no se resolvió"
    target = by_id[call.resolved_id]
    assert target.name.lower() == "cobrar"
    assert target.file != emitir[0].file  # está en otro archivo
    assert call.confidence in ("exacta", "probable")
    kinds = [ctx.kind for ctx in call.context]
    assert "loop" in kinds


@pytest.mark.parametrize("lang", LANGS_F1)
def test_io_kinds_present(lang, projects):
    io = {c.io_kind for c in projects[lang].calls if c.io_kind}
    assert "pantalla" in io or lang in ("php", "cpp")  # PHP usa echo y C++ cout (no son llamadas)
    # C++ lee con `cin >>` y escribe con ofstream; Ruby lee con `gets` (no son llamadas).
    if lang not in ("cpp", "ruby"):
        assert "teclado" in io
        assert "archivo_escribe" in io


@pytest.mark.parametrize("lang", LANGS_F1)
def test_entry_points(lang, projects):
    entries = [s.qualname for s in projects[lang].symbols if s.is_entry and s.kind != "module"]
    assert any(q.lower().endswith("main") for q in entries)  # C#: Main


def test_interface_possible_implementation(projects):
    for lang in ("java", "kotlin", "typescript"):
        p = projects[lang]
        by_id = {s.id: s for s in p.symbols}
        call = next(c for c in p.calls if c.callee_text == "cobrar")
        assert call.confidence == "probable"
        assert by_id[call.resolved_id].qualname == "PagoService.cobrar"
        assert call.candidates == (call.resolved_id,)


def test_csharp_interface_field_resolves_to_implementation(projects):
    p = projects["csharp"]
    by_id = {s.id: s for s in p.symbols}
    call = next(c for c in p.calls if c.callee_text == "Cobrar")
    assert call.confidence == "probable"
    assert by_id[call.resolved_id].qualname == "PagoService.Cobrar"
    emitir = next(s for s in p.symbols if s.name == "Emitir")
    assert emitir.doc == "Calcula el total, cobra y guarda la factura."  # sin <summary>


def test_c_header_pairing_is_exact(projects):
    call = next(c for c in projects["c"].calls if c.callee_text == "cobrar")
    assert call.confidence == "exacta"


def test_cpp_out_of_class_method_linked(projects):
    p = projects["cpp"]
    by_id = {s.id: s for s in p.symbols}
    cobrar = next(s for s in p.symbols if s.qualname == "PagoService.cobrar")
    assert by_id[cobrar.parent_id].kind == "class"
    assert by_id[cobrar.parent_id].file == "pago.hpp"


def test_python_main_guard(projects):
    module = next(s for s in projects["python"].symbols if s.qualname == "facturacion.py")
    assert module.is_entry


def test_external_calls_have_no_candidates(projects):
    for p in projects.values():
        for c in p.calls:
            if c.confidence == "externa":
                assert c.resolved_id is None and c.candidates == ()
            if c.confidence == "ambigua":
                assert c.resolved_id is None and len(c.candidates) > 1


def test_ids_unique(projects):
    for p in projects.values():
        ids = [s.id for s in p.symbols]
        assert len(ids) == len(set(ids))
        cids = [c.id for c in p.calls]
        assert len(cids) == len(set(cids))
