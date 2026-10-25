"""Diagrama de secuencia y rutas de Laravel (SPEC §8, RF-16)."""

from __future__ import annotations

from pathlib import Path

from desglosa import cli
from desglosa.layout.sequence import layout_sequence
from desglosa.pipeline import analyze
from desglosa.routes import find_routes, is_route_file
from desglosa.sequence import SequenceDiagram, build_sequence, without_externals
from tests.conftest import FIXTURES, needs_grammars

ROOT = Path(__file__).resolve().parent.parent
LARAVEL = ROOT / "examples" / "laravel-mini"


def as_text(d: SequenceDiagram) -> str:
    """Forma legible y estable del diagrama para el golden."""
    names = {p.id: p.label for p in d.participants}
    frags = {f.id: f for f in d.fragments}
    lines = ["participantes: " + ", ".join(f"{p.label} ({p.kind})" for p in d.participants)]
    for m in d.messages:
        ctx = " / ".join(f"{frags[f].kind}:{frags[f].label}" for f in m.fragments)
        arrow = "-->" if m.kind == "retorno" else "->"
        head = f"{m.number or '·'} {names[m.src]} {arrow} {names[m.dst]}"
        line = f"{head}: {m.label} [{m.confidence}]"
        if m.external:
            line += " (externo)"
        if ctx:
            line += f"  {{{ctx}}}"
        lines.append(line)
    if d.truncated:
        lines.append("(truncado)")
    return "\n".join(lines) + "\n"


def _symbol(analysis, qualname: str) -> str:
    found = [s.id for s in analysis.project.symbols if s.qualname == qualname]
    assert len(found) == 1, qualname
    return found[0]


def _diagram(analysis, qualname: str, depth: int = 4) -> SequenceDiagram:
    routes = {r.symbol_id: f"{r.verb} {r.path}" for r in analysis.routes if r.symbol_id}
    flows = {k: v.graph for k, v in analysis.flows.items()}
    return build_sequence(
        analysis.project, flows, _symbol(analysis, qualname), depth, routes, analysis.new_calls
    )


@needs_grammars
def test_golden_laravel_store(golden):
    a = analyze(LARAVEL)
    d = _diagram(a, "FacturaController.store")
    golden("sequence/laravel_store.txt", as_text(d))
    golden("sequence/laravel_store_sin_externos.txt", as_text(without_externals(d)))


@needs_grammars
def test_golden_interface_and_recursion(golden):
    a = analyze(FIXTURES / "secuencia")
    golden("sequence/ts_avisar.txt", as_text(_diagram(a, "Servicio.avisar")))
    golden("sequence/ts_factorial.txt", as_text(_diagram(a, "factorial")))


@needs_grammars
def test_laravel_store_starts_with_user_and_route():
    a = analyze(LARAVEL)
    d = without_externals(_diagram(a, "FacturaController.store"))
    first = d.messages[0]
    assert d.participants[0].label == "Usuario"
    assert first.number == "1" and first.label == "POST /facturas → store()"
    numbers = [m.number for m in d.messages if m.number]
    assert numbers == sorted(numbers, key=lambda n: [int(x) for x in n.split(".")])
    assert any(m.label == "new Factura()" for m in d.messages)


@needs_grammars
def test_recursion_is_not_expanded():
    a = analyze(FIXTURES / "secuencia")
    d = _diagram(a, "factorial")
    rec = [m for m in d.messages if m.kind == "recursivo"]
    assert len(rec) == 1 and rec[0].label.endswith("(recursivo)")


@needs_grammars
def test_interface_call_becomes_alt_with_two_implementations():
    a = analyze(FIXTURES / "secuencia")
    d = _diagram(a, "Servicio.avisar")
    impl = [f for f in d.fragments if f.kind == "impl"]
    assert sorted(f.label for f in impl) == [
        "posible implementación: Correo",
        "posible implementación: Sms",
    ]
    loops = [f for f in d.fragments if f.kind == "loop"]
    assert loops and all(f.parent is None for f in loops)
    assert all(f.parent == loops[0].id for f in impl)  # la llamada está dentro del for


@needs_grammars
def test_depth_limits_the_tree():
    a = analyze(LARAVEL)
    shallow = _diagram(a, "FacturaController.store", depth=1)
    deep = _diagram(a, "FacturaController.store", depth=4)
    assert len(shallow.messages) < len(deep.messages)
    assert all(m.number.count(".") <= 1 for m in shallow.messages if m.number)


@needs_grammars
def test_sequence_layout_is_consistent():
    a = analyze(LARAVEL)
    lay = layout_sequence(_diagram(a, "FacturaController.store"))
    xs = {round(x) for x, _, _ in lay.lifelines}
    assert len(xs) == len(lay.participants)  # una línea de vida por participante
    ys = [m[2] for m in lay.messages]
    assert ys == sorted(ys) and len(set(ys)) == len(ys)  # mensajes de arriba hacia abajo
    for fx, fy, fw, fh, *_ in lay.fragments:
        assert fx >= 0 and fx + fw <= lay.width and fy + fh <= lay.height


@needs_grammars
def test_sequence_is_deterministic():
    a = analyze(LARAVEL)
    b = analyze(LARAVEL)
    assert as_text(_diagram(a, "FacturaController.store")) == as_text(
        _diagram(b, "FacturaController.store")
    )


@needs_grammars
def test_sequence_command(tmp_path):
    out = tmp_path / "s.html"
    code = cli.main(
        ["sequence", str(LARAVEL), "--entry", "FacturaController.store", "-o", str(out)]
    )
    assert code == cli.EXIT_OK
    # El JSON incrustado escapa "/" como "\/" (no puede cerrar el <script>).
    assert '"start":"#\\/secuencia\\/' in out.read_text(encoding="utf-8")


@needs_grammars
def test_sequence_command_unknown_entry(tmp_path):
    out = tmp_path / "s.html"
    code = cli.main(["sequence", str(LARAVEL), "--entry", "NoExiste.nada", "-o", str(out)])
    assert code == cli.EXIT_USAGE
    assert not out.exists()


# ---------------------------------------------------------------------- rutas


def test_route_file_detection():
    assert is_route_file("routes/web.php")
    assert is_route_file("app/routes/api.php")
    assert not is_route_file("routes.php")
    assert not is_route_file("routes/web.js")


def test_route_forms():
    from desglosa.ir import Symbol

    def sym(sid, kind, name, parent=None):
        return Symbol(sid, kind, name, name, "c.php", 1, 2, parent, None, "php", name)

    symbols = [
        sym("c", "class", "PagoController"),
        sym("m1", "method", "index", "c"),
        sym("m2", "method", "store", "c"),
        sym("m3", "method", "show", "c"),
        sym("m4", "method", "__invoke", "c"),
    ]
    text = (
        "<?php\n"
        "Route::get('/pagos', [PagoController::class, 'index']);\n"
        'Route::post("pagos", "App\\\\Http\\\\PagoController@store");\n'
        "Route::get('/raro', PagoController::class);\n"
        "Route::resource('cobros', PagoController::class);\n"
        "Route::get('/nada', function () { return 1; });\n"
    )
    found = [(r.verb, r.path, r.target, r.symbol_id, r.line) for r in find_routes(
        {"routes/web.php": text}, symbols)]
    assert found == [
        ("GET", "/pagos", "PagoController@index", "m1", 2),
        ("POST", "/pagos", "PagoController@store", "m2", 3),
        ("GET", "/raro", "PagoController@__invoke", "m4", 4),
        ("GET", "/cobros", "PagoController@index", "m1", 5),
        ("GET", "/cobros/{id}", "PagoController@show", "m3", 5),
        ("POST", "/cobros", "PagoController@store", "m2", 5),
    ]


@needs_grammars
def test_laravel_routes_mark_entry_points():
    a = analyze(LARAVEL)
    by_id = {s.id: s for s in a.project.symbols}
    routes = {(r.verb, r.path): by_id[r.symbol_id].qualname for r in a.routes}
    assert routes == {
        ("GET", "/facturas"): "FacturaController.index",
        ("POST", "/facturas"): "FacturaController.store",
        ("GET", "/facturas/{id}"): "FacturaController.show",
    }
    assert all(by_id[r.symbol_id].is_entry for r in a.routes)


def test_many_candidates_are_summarized():
    from desglosa.ir import Call, Project, Symbol
    from desglosa.sequence import MAX_ALTERNATIVES

    def fn(sid, name, file):
        return Symbol(sid, "function", name, name, file, 1, 3, None, None, "python", name)

    n = MAX_ALTERNATIVES + 2
    targets = [fn(f"t{i}", "emitir", f"m{i}/a.py") for i in range(n)]
    caller = fn("c", "main", "main.py")
    call = Call("k", "c", "emitir", None, 2, 5, candidates=tuple(t.id for t in targets),
                confidence="ambigua")
    project = Project("p", symbols=(caller, *targets), calls=(call,))
    d = build_sequence(project, {}, "c")
    assert [m.label for m in d.messages] == [f"emitir() — {n} posibles"]
    assert d.participants[-1].label == "Varios posibles"
    assert not d.fragments
