"""Interfaz de línea de comandos de Desglosa (argparse, SPEC §12).

Códigos de salida: 0 ok, 1 error de uso, 2 faltan gramáticas; en las consultas
(`explain`, `path`, `buscar`) además 3 = nombre ambiguo y 4 = no encontrado.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from importlib import metadata
from pathlib import Path

from desglosa import __version__, grammars
from desglosa.scan import detect_language, grammar_for

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_GRAMMARS = 2
EXIT_AMBIGUOUS = 3  # consultas: el nombre corresponde a varios símbolos
EXIT_NOT_FOUND = 4  # consultas: no hay símbolo, camino ni resultado


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "no instalado"


# --------------------------------------------------------------------------- setup / doctor


def cmd_setup(args: argparse.Namespace) -> int:
    print("Descargando gramáticas tree-sitter (única vez que Desglosa usa internet)...")
    try:
        count = grammars.setup()
    except Exception as exc:  # errores de red del paquete externo
        print(f"Error al descargar las gramáticas: {exc}", file=sys.stderr)
        return EXIT_GRAMMARS
    missing = set(grammars.ALL_GRAMMARS) - grammars.downloaded()
    if missing:
        print(f"Quedaron sin descargar: {', '.join(sorted(missing))}", file=sys.stderr)
        return EXIT_GRAMMARS
    print(f"Listo: {count} gramáticas disponibles sin conexión.")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"Desglosa {__version__}")
    print(f"Python {platform.python_version()} ({sys.executable})")
    for pkg in ("tree-sitter", "tree-sitter-language-pack", "sqlglot", "pathspec"):
        print(f"  {pkg}: {_pkg_version(pkg)}")
    have = grammars.downloaded()
    print("Gramáticas:")
    ok = 0
    for name in grammars.LANGS:
        status = "OK" if name in have else "FALTA"
        ok += status == "OK"
        print(f"  {name:<12} {status}")
    for name in grammars.EXTRA_GRAMMARS:
        status = "OK" if name in have else "FALTA"
        print(f"  {name:<12} {status}   (extra: archivos .tsx)")
    total = len(grammars.LANGS)
    print(f"{ok}/{total} lenguajes listos.")
    if ok < total or not set(grammars.EXTRA_GRAMMARS) <= have:
        print("Ejecuta una vez: desglosa setup")
        return EXIT_GRAMMARS
    return EXIT_OK


# --------------------------------------------------------------------------- debug-ast


def _short_text(node, limit: int = 50) -> str:
    text = node.text.decode("utf-8", errors="replace") if node.text is not None else ""
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _print_ast(node, depth: int, max_depth: int, show_all: bool, field: str | None) -> None:
    indent = "  " * depth
    label = f"{field}: " if field else ""
    start, end = node.start_point[0] + 1, node.end_point[0] + 1
    lines = f"L{start}" if start == end else f"L{start}-L{end}"
    extra = ""
    if node.named_child_count == 0 or depth == max_depth:
        extra = f'  "{_short_text(node)}"'
    error = "  <ERROR>" if node.type == "ERROR" or node.is_missing else ""
    print(f"{indent}{label}{node.type} {lines}{extra}{error}")
    if depth >= max_depth:
        return
    for i, child in enumerate(node.children):
        if not show_all and not child.is_named:
            continue
        _print_ast(child, depth + 1, max_depth, show_all, node.field_name_for_child(i))


def cmd_debug_ast(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"No existe el archivo: {path}", file=sys.stderr)
        return EXIT_USAGE
    lang = args.lang or detect_language(path, h_as=args.h_as)
    if lang is None:
        print(f"No sé qué lenguaje es {path.name}. Usa --lang.", file=sys.stderr)
        return EXIT_USAGE
    grammar = grammar_for(path, lang)
    try:
        parser = grammars.get_parser(grammar)
    except grammars.MissingGrammarError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_GRAMMARS
    tree = parser.parse(path.read_bytes())
    print(f"# {path.name} — gramática: {grammar}")
    _print_ast(tree.root_node, 0, args.depth, args.all, None)
    return EXIT_OK


# --------------------------------------------------------------------------- análisis


def _analysis_options(args: argparse.Namespace, flows: bool = True):
    from desglosa.pipeline import AnalyzeOptions
    from desglosa.scan import ScanOptions

    langs_filter = None
    if getattr(args, "lang", None):
        langs_filter = tuple(sorted(x.strip() for x in args.lang.split(",") if x.strip()))
    scan_opts = ScanOptions(
        ignore=tuple(args.ignore or ()),
        max_file_kb=args.max_file_kb,
        h_as=args.h_as,
        langs=langs_filter,
    )
    from desglosa.cache import default_dir

    cache_dir = None
    if not getattr(args, "no_cache", False):
        cache_dir = Path(args.cache_dir) if getattr(args, "cache_dir", None) else default_dir()
    return AnalyzeOptions(
        scan=scan_opts,
        jobs=args.jobs,
        max_flow_nodes=getattr(args, "max_flow_nodes", 120),
        flow_max_height=getattr(args, "flow_max_height", 1600),
        dialect=getattr(args, "dialect", None),
        cache_dir=cache_dir,
        flows=flows,
    )


def _run_analysis(args: argparse.Namespace, flows: bool = True):
    """Ejecuta el pipeline; devuelve (Analysis, None) o (None, código de salida)."""
    from desglosa.pipeline import analyze

    target = Path(args.path)
    if not target.exists():
        print(f"No existe la ruta: {target}", file=sys.stderr)
        return None, EXIT_USAGE
    try:
        return analyze(target, _analysis_options(args, flows)), None
    except grammars.MissingGrammarError as exc:
        print(str(exc), file=sys.stderr)
        return None, EXIT_GRAMMARS


def _write_text(path: str, text: str) -> None:
    if path == "-":
        sys.stdout.write(text)
        return
    Path(path).write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- consultas


def _emit(args: argparse.Namespace, data, text: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


def _pick_one(analysis, name: str, kinds=None):
    """Un símbolo por nombre, o (None, código de salida) explicando el problema."""
    from desglosa.query import find_symbols

    cands = find_symbols(analysis.project, name, kinds)
    if not cands:
        print(f"No encontré {name!r}. Prueba: desglosa buscar <ruta> {name!r}", file=sys.stderr)
        return None, EXIT_NOT_FOUND
    if len(cands) > 1:
        print(f"{name!r} corresponde a {len(cands)} símbolos; usa archivo:Nombre:", file=sys.stderr)
        for s in cands[:20]:
            print(f"  {s.file}:{s.qualname}", file=sys.stderr)
        return None, EXIT_AMBIGUOUS
    return cands[0], EXIT_OK


def cmd_explain(args: argparse.Namespace) -> int:
    from desglosa.flows_stage import build_file_flows, make_tasks
    from desglosa.query import explain, format_explain

    # Sin flujos de todo el proyecto: solo se dibuja el archivo de la función pedida (para
    # su complejidad). En Django eso evita cargar 1 700 archivos de flujos.
    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    sym, code = _pick_one(analysis, args.name)
    if sym is None:
        return code
    if sym.kind in ("function", "method"):
        tasks = make_tasks(
            str(analysis.scan.root),
            [s for s in analysis.project.symbols if s.file == sym.file],
            list(analysis.project.calls),
            args.max_flow_nodes,
            args.flow_max_height,
        )
        for task in tasks:
            for out in build_file_flows(task):
                analysis.flows[out.graph.symbol_id] = out
    info = explain(analysis, sym)
    _emit(args, info, format_explain(info))
    return EXIT_OK


def cmd_path(args: argparse.Namespace) -> int:
    from desglosa.query import CallIndex, format_path, shortest_path

    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    a, code = _pick_one(analysis, args.source, ("function", "method"))
    if a is None:
        return code
    b, code = _pick_one(analysis, args.target, ("function", "method"))
    if b is None:
        return code
    index = CallIndex.of(analysis.project)
    steps = shortest_path(index, a.id, b.id)
    if steps is None:
        back = shortest_path(index, b.id, a.id)
        msg = f"No hay un camino de llamadas de {a.qualname} a {b.qualname}."
        if back is not None:
            msg += (
                f" Sí lo hay al revés ({len(back)} pasos): "
                f"desglosa path <ruta> {args.target} {args.source}"
            )
        print(msg, file=sys.stderr)
        return EXIT_NOT_FOUND
    data = [
        {"from": index.by_id[x].qualname, "to": index.by_id[y].qualname,
         "confidence": index.out[x][y][0], "at": f"{index.by_id[x].file}:{call.line}"}
        for x, y, call in steps
    ]
    _emit(args, data, format_path(index, steps))
    return EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    from desglosa.query import format_search, search

    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    hits = search(analysis.project, args.text, args.limit)
    data = [
        {"score": h.score, "qualname": h.symbol.qualname, "kind": h.symbol.kind,
         "file": h.symbol.file, "line": h.symbol.line_start, "why": h.why}
        for h in hits
    ]
    _emit(args, data, format_search(hits))
    return EXIT_OK if hits else EXIT_NOT_FOUND


# --------------------------------------------------------------------------- skill


def cmd_skill_install(args: argparse.Namespace) -> int:
    from desglosa.skill import SkillExistsError, default_skills_dir, install

    skills_dir = Path(args.dir) if args.dir else default_skills_dir(args.project)
    try:
        target, state = install(skills_dir, force=args.force)
    except SkillExistsError as exc:
        print(
            f"Ya existe otra versión de la skill en {exc}. "
            "Usa --force para reemplazarla (se perderán los cambios que tenga).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    except OSError as exc:
        print(f"No pude escribir la skill: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(f"Skill {state}: {target}")
    if state != "sin cambios":
        print("Abre una sesión nueva del asistente para que la cargue.")
    return EXIT_OK


def cmd_skill_show(args: argparse.Namespace) -> int:
    from desglosa.skill import skill_text

    sys.stdout.write(skill_text())
    return EXIT_OK


def cmd_export_ir(args: argparse.Namespace) -> int:
    from desglosa.ir import dumps
    from desglosa.pipeline import summary

    analysis, code = _run_analysis(args)
    if analysis is None:
        return code
    _write_text(args.output, dumps(analysis.project))
    if args.output != "-":
        print(summary(analysis))
        print(f"IR escrito en {args.output}")
    return EXIT_OK


def _find_symbol(analysis, spec: str):
    """`archivo:funcion` → símbolo (acepta nombre corto o calificado)."""
    file_part, sep, func = spec.rpartition(":")
    if not sep:
        file_part, func = "", spec
    file_part = file_part.replace("\\", "/").lstrip("./")
    cands = [
        s
        for s in analysis.project.symbols
        if s.kind in ("function", "method")
        and (not file_part or s.file == file_part or s.file.endswith("/" + file_part))
        and (s.qualname == func or s.name == func)
    ]
    return cands


def cmd_flow(args: argparse.Namespace) -> int:
    from desglosa.render.html import render_html
    from desglosa.render.payload import build_payload, reachable

    analysis, code = _run_analysis(args)
    if analysis is None:
        return code
    cands = _find_symbol(analysis, args.function)
    if not cands:
        print(f"No encontré la función {args.function!r}.", file=sys.stderr)
        sample = [
            f"{s.file}:{s.qualname}"
            for s in analysis.project.symbols
            if s.kind in ("function", "method")
        ][:15]
        if sample:
            print("Algunas disponibles:\n  " + "\n  ".join(sample), file=sys.stderr)
        return EXIT_USAGE
    if len(cands) > 1:
        print(f"{args.function!r} es ambiguo. Usa archivo:Clase.metodo:", file=sys.stderr)
        for s in cands:
            print(f"  {s.file}:{s.qualname}", file=sys.stderr)
        return EXIT_USAGE
    sym = cands[0]
    if sym.id not in analysis.flows:
        print(f"{sym.qualname} no tiene cuerpo para dibujar.", file=sys.stderr)
        return EXIT_USAGE
    only = reachable(analysis, sym.id)
    payload = build_payload(
        analysis, include_source=not args.no_source, only=only, start=f"#/flujo/{sym.id}"
    )
    title = f"{sym.qualname} — Desglosa"
    _write_text(args.output, render_html(payload, title))
    flow = analysis.flows[sym.id]
    print(
        f"Flujo de {sym.qualname} ({sym.file}:{sym.line_start}): "
        f"{len(flow.graph.nodes)} nodos, {flow.payload()['layout']['columns']} columna(s)."
    )
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


# Con los paquetes comprimidos, 200 000 líneas dan ~20 MB y abren en ~1 s.
MAX_HTML_MB = 100


def _write_app(args: argparse.Namespace, analysis, start: str, depth: int = 4) -> str:
    """HTML completo (mapa, flujos, secuencias, ER) que abre en `start`."""
    from desglosa.macro import build_map
    from desglosa.render.html import render_html
    from desglosa.render.payload import build_payload

    payload = build_payload(
        analysis,
        include_source=not args.no_source,
        start=start,
        map_data=build_map(
            analysis.project,
            [(r.file, r.symbol_id) for r in analysis.routes if r.symbol_id],
            analysis.readmes,
        ),
        depth=depth,
    )
    page = render_html(payload, f"{analysis.project.root_name} — Desglosa")
    _write_text(args.output, page)
    return page


def cmd_sequence(args: argparse.Namespace) -> int:
    analysis, code = _run_analysis(args)
    if analysis is None:
        return code
    cands = _find_symbol(analysis, args.entry)
    if not cands:
        print(f"No encontré la función {args.entry!r}.", file=sys.stderr)
        return EXIT_USAGE
    if len(cands) > 1:
        print(f"{args.entry!r} es ambiguo. Usa archivo:Clase.metodo:", file=sys.stderr)
        for s in cands:
            print(f"  {s.file}:{s.qualname}", file=sys.stderr)
        return EXIT_USAGE
    sym = cands[0]
    _write_app(args, analysis, f"#/secuencia/{sym.id}", args.depth)
    print(f"Secuencia de {sym.qualname} (profundidad {args.depth}).")
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


def cmd_sql(args: argparse.Namespace) -> int:
    analysis, code = _run_analysis(args)
    if analysis is None:
        return code
    p = analysis.project
    if not p.tables:
        print("No se encontraron tablas SQL (archivos .sql con CREATE TABLE).", file=sys.stderr)
        return EXIT_USAGE
    _write_app(args, analysis, "#/er")
    forms = {}
    for fk in p.fks:
        forms[fk.form] = forms.get(fk.form, 0) + 1
    detail = ", ".join(f"{k} {v}" for k, v in sorted(forms.items()))
    suffix = f" ({detail})" if detail else ""
    print(f"Tablas: {len(p.tables)} · relaciones: {len(p.fks)}{suffix}")
    for w in [w for w in p.warnings if ".sql:" in w][:10]:
        print(f"  Aviso: {w}")
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


def cmd_analyze(args: argparse.Namespace) -> int:
    from desglosa.pipeline import summary

    analysis, code = _run_analysis(args)
    if analysis is None:
        return code
    page = _write_app(args, analysis, "#/mapa")
    print(summary(analysis))
    size_mb = len(page.encode("utf-8")) / (1024 * 1024)
    print(f"HTML escrito en {args.output} ({size_mb:.1f} MB)")
    if args.report:
        from desglosa.report import build_report

        _write_text(args.report, build_report(analysis))
        print(f"Reporte escrito en {args.report}")
    if size_mb > MAX_HTML_MB:
        print(
            f"Aviso: el HTML pesa más de {MAX_HTML_MB} MB: abrirá lento y costará compartirlo. "
            "Analiza una parte del proyecto (una subcarpeta, --lang o --ignore).",
            file=sys.stderr,
        )
    return EXIT_OK


def _add_flow_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--max-flow-nodes", type=int, default=120, help="nodos máximos por flujo (def. 120)"
    )
    p.add_argument(
        "--flow-max-height",
        type=float,
        default=1600,
        help="alto máximo de una columna del flujo en px (def. 1600)",
    )
    p.add_argument("--no-source", action="store_true", help="no incluir el código fuente")


def _add_analysis_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", help="carpeta o archivo a analizar")
    p.add_argument("--lang", help="limitar a estos lenguajes (ej. php,python)")
    p.add_argument(
        "--ignore", action="append", metavar="PATRON", help="patrón extra a ignorar (repetible)"
    )
    p.add_argument("--h-as", choices=("c", "cpp"), default="c", help="lenguaje para archivos .h")
    p.add_argument("--jobs", type=int, help="procesos en paralelo (por defecto: automático)")
    p.add_argument(
        "--max-file-kb", type=int, default=1024, help="tamaño máximo por archivo (KB, def. 1024)"
    )
    p.add_argument(
        "--dialect", help="dialecto SQL: mysql, postgres, sqlite, tsql… (por defecto: probar)"
    )
    p.add_argument(
        "--no-cache", action="store_true", help="no usar la caché (analizar todo desde cero)"
    )
    p.add_argument(
        "--cache-dir", metavar="CARPETA", help="carpeta de la caché (por defecto: la del usuario)"
    )


# --------------------------------------------------------------------------- parser


class _Parser(argparse.ArgumentParser):
    """argparse sale con 2 en errores de uso; la SPEC reserva el 2 para gramáticas."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="desglosa",
        description="Convierte código fuente en un HTML interactivo (mapa, flujo, secuencia, ER). "
        "Sin IA y sin internet.",
    )
    parser.add_argument("--version", action="version", version=f"desglosa {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="comando")

    p = sub.add_parser("setup", help="descarga las gramáticas (única vez que usa internet)")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="verifica versiones y gramáticas disponibles")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("debug-ast", help="imprime el árbol sintáctico de un archivo")
    p.add_argument("file", help="archivo a analizar")
    p.add_argument("--depth", type=int, default=6, help="profundidad máxima (por defecto 6)")
    p.add_argument("--lang", help="forzar lenguaje (python, php, c, ...)")
    p.add_argument("--h-as", choices=("c", "cpp"), default="c", help="lenguaje para archivos .h")
    p.add_argument("--all", action="store_true", help="incluir nodos anónimos (puntuación)")
    p.set_defaults(func=cmd_debug_ast)

    p = sub.add_parser("analyze", help="analiza un proyecto y genera el HTML interactivo")
    _add_analysis_args(p)
    _add_flow_args(p)
    p.add_argument("-o", "--output", default="desglosa.html", help="archivo HTML de salida")
    p.add_argument("--report", metavar="reporte.md", help="escribir también un reporte Markdown")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("sequence", help="genera el diagrama de secuencia desde una función")
    _add_analysis_args(p)
    p.add_argument("--entry", required=True, metavar="Clase.metodo", help="función de entrada")
    p.add_argument("--depth", type=int, default=4, help="profundidad máxima (por defecto 4)")
    _add_flow_args(p)
    p.add_argument("-o", "--output", default="secuencia.html", help="archivo HTML de salida")
    p.set_defaults(func=cmd_sequence)

    p = sub.add_parser("sql", help="genera el diagrama entidad-relación de los .sql")
    _add_analysis_args(p)
    _add_flow_args(p)
    p.add_argument("-o", "--output", default="er.html", help="archivo HTML de salida")
    p.set_defaults(func=cmd_sql)

    p = sub.add_parser("export-ir", help="exporta el modelo intermedio en JSON")
    _add_analysis_args(p)
    p.add_argument("-o", "--output", default="ir.json", help="archivo de salida ('-' = pantalla)")
    p.set_defaults(func=cmd_export_ir)

    p = sub.add_parser(
        "explain", help="explica una función o clase: dónde está, quién la llama, a quién llama"
    )
    _add_analysis_args(p)
    p.add_argument("name", metavar="nombre", help="Clase.metodo, funcion o archivo:Nombre")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    _add_flow_args(p)
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("path", help="camino de llamadas más corto entre dos funciones")
    _add_analysis_args(p)
    p.add_argument("source", metavar="desde", help="función de inicio")
    p.add_argument("target", metavar="hasta", help="función de llegada")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    p.set_defaults(func=cmd_path)

    p = sub.add_parser(
        "buscar", aliases=["search"], help="busca funciones y clases por palabras"
    )
    _add_analysis_args(p)
    p.add_argument("text", metavar="texto", help='palabras a buscar, p. ej. "calcular total"')
    p.add_argument("--limit", type=int, default=15, help="máximo de resultados (def. 15)")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("flow", help="genera el diagrama de flujo de una función")
    _add_analysis_args(p)
    p.add_argument("function", metavar="archivo:funcion", help="p. ej. gps.c:main")
    _add_flow_args(p)
    p.add_argument("-o", "--output", default="flujo.html", help="archivo HTML de salida")
    p.set_defaults(func=cmd_flow)

    p = sub.add_parser("skill", help="skill para asistentes de IA (Claude Code y compatibles)")
    p.set_defaults(func=_help_of(p))
    skill = p.add_subparsers(dest="skill_command", metavar="acción")
    q = skill.add_parser("install", help="copia SKILL.md a la carpeta de skills")
    where = q.add_mutually_exclusive_group()
    where.add_argument(
        "--project", action="store_true", help="en este proyecto (.claude/skills), no en tu usuario"
    )
    where.add_argument("--dir", metavar="CARPETA", help="otra carpeta de skills de destino")
    q.add_argument("--force", action="store_true", help="reemplazar una versión distinta")
    q.set_defaults(func=cmd_skill_install)
    q = skill.add_parser("show", help="muestra el SKILL.md (para copiarlo en otro asistente)")
    q.set_defaults(func=cmd_skill_show)

    return parser


def _help_of(p: argparse.ArgumentParser):
    """Comando sin acción (p. ej. `desglosa skill`): muestra su ayuda."""

    def show(args: argparse.Namespace) -> int:
        p.print_help()
        return EXIT_USAGE

    return show


def _configure_console() -> None:
    # En consolas Windows con cp1252 evitamos que un carácter raro tumbe el programa.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
