"""Interfaz de línea de comandos de Desglosa (argparse, SPEC §12).

Códigos de salida: 0 ok, 1 error de uso, 2 faltan gramáticas; en las consultas
(`explain`, `path`, `buscar`) además 3 = nombre ambiguo y 4 = no encontrado; `check`
devuelve 5 cuando encuentra un ciclo nuevo.
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
EXIT_CHECK = 5  # check: hay un ciclo (o una capa saltada) nuevo


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


def _file_flows(analysis, sym, args: argparse.Namespace) -> None:
    """Dibuja solo los flujos del archivo de `sym` (no los de todo el proyecto): en Django
    eso evita cargar 1 700 archivos de flujos para una consulta."""
    _path_flows(analysis, sym.file, args)


def _path_flows(analysis, path: str, args: argparse.Namespace) -> None:
    from desglosa.flows_stage import build_file_flows, make_tasks

    # Todos los símbolos: una llamada a otro archivo tiene que verse como subproceso.
    # Armar las tareas es barato; lo caro (dibujar) se hace solo para este archivo.
    tasks = make_tasks(
        str(analysis.scan.root),
        list(analysis.project.symbols),
        list(analysis.project.calls),
        args.max_flow_nodes,
        args.flow_max_height,
    )
    for task in (t for t in tasks if t.path == path):
        for out in build_file_flows(task):
            analysis.flows[out.graph.symbol_id] = out


def cmd_explain(args: argparse.Namespace) -> int:
    from desglosa.query import explain, format_explain

    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    sym, code = _pick_one(analysis, args.name)
    if sym is None:
        return code
    if sym.kind in ("function", "method"):
        _file_flows(analysis, sym, args)  # para su complejidad
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


# --------------------------------------------------------------------------- Mermaid


def cmd_mermaid(args: argparse.Namespace) -> int:
    from desglosa.mermaid import flow_to_mermaid, sequence_to_mermaid
    from desglosa.sequence import build_sequence, without_externals

    # La secuencia necesita saber qué funciones devuelven algo: ahí sí van todos los flujos.
    analysis, code = _run_analysis(args, flows=args.secuencia)
    if analysis is None:
        return code
    sym, code = _pick_one(analysis, args.name, ("function", "method"))
    if sym is None:
        return code
    if args.secuencia:
        routes = {r.symbol_id: f"{r.verb} {r.path}" for r in analysis.routes if r.symbol_id}
        diagram = build_sequence(
            analysis.project, {k: v.graph for k, v in analysis.flows.items()}, sym.id,
            depth=args.depth, routes=routes, new_calls=analysis.new_calls,
        )
        if not args.externas:
            diagram = without_externals(diagram)
        text = sequence_to_mermaid(diagram, title=f"Secuencia de {sym.qualname}")
    else:
        _file_flows(analysis, sym, args)
        flow = analysis.flows.get(sym.id)
        if flow is None or not flow.graph.nodes:
            print(f"{sym.qualname} no tiene cuerpo para dibujar.", file=sys.stderr)
            return EXIT_NOT_FOUND
        text = flow_to_mermaid(flow.graph, technical=args.tecnico, title=sym.qualname)
    _write_text(args.output, text)
    if args.output != "-":
        print(f"Mermaid escrito en {args.output}")
    return EXIT_OK


def _project_file(analysis, name: str) -> str | None:
    """`gps.c` o `src/gps.c` → la ruta del archivo en el proyecto, si es uno solo."""
    wanted = name.replace("\\", "/").strip("/")
    paths = [f.path for f in analysis.project.files if f.skipped_reason is None]
    if wanted in paths:
        return wanted
    found = [p for p in paths if p.endswith("/" + wanted)]
    return found[0] if len(found) == 1 else None


def cmd_pseudo(args: argparse.Namespace) -> int:
    from desglosa.pseudo import is_main

    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    path = _project_file(analysis, args.name)
    if path is None:  # una función
        sym, code = _pick_one(analysis, args.name, ("function", "method"))
        if sym is None:
            return code
        _file_flows(analysis, sym, args)
        flow = analysis.flows.get(sym.id)
        text = flow.pseudocode() if flow is not None else None
        if not text:
            print(f"{sym.qualname} no tiene cuerpo para traducir.", file=sys.stderr)
            return EXIT_NOT_FOUND
        text = f"// {sym.qualname} ({sym.file}:{sym.line_start}), escrito por Desglosa\n" + text
    else:  # un archivo entero: sus funciones y, al final, main como Algoritmo
        _path_flows(analysis, path, args)
        syms = sorted((s for s in analysis.project.symbols
                       if s.file == path and s.kind in ("function", "method")),
                      key=lambda s: (is_main(s.name), s.line_start, s.id))
        counts: dict[str, int] = {}
        for s in syms:
            counts[s.name] = counts.get(s.name, 0) + 1
        blocks = []
        for s in syms:
            flow = analysis.flows.get(s.id)
            body = flow.pseudocode() if flow is not None else None
            if not body:
                continue
            if counts[s.name] > 1 and not is_main(s.name):  # `Circulo.area` y `Cuadrado.area`
                unique = s.qualname.replace(".", "_")
                body = body.replace(f"{s.name}(", f"{unique}(", 1)
            blocks.append(body)
        if not blocks:
            print(f"{path} no tiene funciones para traducir.", file=sys.stderr)
            return EXIT_NOT_FOUND
        text = f"// {path}, escrito por Desglosa\n\n" + "\n".join(blocks)
    _write_text(args.output, text)
    if args.output != "-":
        print(f"Pseudocódigo escrito en {args.output}")
    return EXIT_OK


def _analysis_at(args: argparse.Namespace, path: Path, flows: bool, cache: bool = True):
    """`_run_analysis` sobre otra carpeta con las mismas opciones."""
    saved = (args.path, args.no_cache)
    args.path, args.no_cache = str(path), args.no_cache or not cache
    try:
        return _run_analysis(args, flows=flows)
    finally:
        args.path, args.no_cache = saved


def cmd_compare(args: argparse.Namespace) -> int:
    import shutil

    from desglosa.compare import CompareError, compare, export_commit, files_needing_flows
    from desglosa.compare import payload as compare_payload

    temps: list[Path] = []
    try:
        if args.desde:
            if len(args.rutas) != 1:
                print("Con --desde va una sola ruta: la carpeta del repositorio.", file=sys.stderr)
                return EXIT_USAGE
            repo = Path(args.rutas[0])
            tmp, before_path = export_commit(repo, args.desde)
            temps.append(tmp)
            before_label = args.desde
            if args.hasta:
                tmp, after_path = export_commit(repo, args.hasta)
                temps.append(tmp)
                after_label = args.hasta
            else:
                after_path, after_label = repo, "copia de trabajo"
        else:
            if len(args.rutas) != 2:
                print("Indica dos carpetas (antes y después) o una ruta con --desde COMMIT.",
                      file=sys.stderr)
                return EXIT_USAGE
            before_path, after_path = Path(args.rutas[0]), Path(args.rutas[1])
            before_label, after_label = before_path.name or "antes", after_path.name or "después"
        # La versión exportada de git va sin caché: su carpeta temporal no se repite.
        before, code = _analysis_at(args, before_path, flows=False,
                                    cache=not args.desde)
        if before is None:
            return code
        after, code = _analysis_at(args, after_path, flows=not args.json,
                                   cache=not (args.desde and args.hasta))
        if after is None:
            return code
        result = compare(before, after, before_label, after_label)
        # Flujos de antes solo de los archivos que cambiaron (con --json, también los de
        # después, para la complejidad).
        for path in files_needing_flows(result, before):
            _path_flows(before, path, args)
        if args.json:
            for path in sorted({c.file for c in result.changes if c.after}):
                _path_flows(after, path, args)
        result = compare(before, after, before_label, after_label)
    except CompareError as exc:
        print(f"No se pudo comparar: {exc}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        for tmp in temps:
            shutil.rmtree(tmp, ignore_errors=True)
    if args.json:
        data = {
            "antes": before_label,
            "despues": after_label,
            "archivos": {"nuevos": result.files_added, "eliminados": result.files_removed,
                         "cambiados": result.files_changed},
            "funciones": [
                {"estado": c.status, "archivo": c.file, "nombre": c.qualname,
                 "lineas": [c.lines_before, c.lines_after],
                 "complejidad": [c.cc_before, c.cc_after]}
                for c in result.changes
            ],
        }
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        return EXIT_OK
    index, packs = compare_payload(result, before)
    args.output = args.output or "comparar.html"
    _write_app(args, after, "#/cambios", extra={"compare": index}, extra_packs=packs)
    nuevas, eliminadas, cambiadas = (len(result.of(s)) for s in
                                     ("nueva", "eliminada", "cambiada"))
    print(f"De {before_label} a {after_label}: {cambiadas} funciones cambiadas, "
          f"{nuevas} nuevas y {eliminadas} eliminadas "
          f"({len(result.files_changed)} archivos cambiados, {len(result.files_added)} nuevos, "
          f"{len(result.files_removed)} eliminados).")
    for c in result.changes[:args.limit]:
        mark = {"nueva": "+", "eliminada": "-", "cambiada": "~"}[c.status]
        delta = ""
        if c.status == "cambiada" and c.cc_before is not None and c.cc_after is not None \
                and c.cc_before != c.cc_after:
            delta = f"  (complejidad {c.cc_before} -> {c.cc_after})"
        print(f"  {mark} {c.file}: {c.qualname}{delta}")
    if len(result.changes) > args.limit:
        print(f"  ... y {len(result.changes) - args.limit} más")
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    from desglosa.deps import (
        BASE_FILE,
        cycle_text,
        dependency_report,
        load_base,
        save_base,
        skip_text,
    )

    analysis, code = _run_analysis(args, flows=False)
    if analysis is None:
        return code
    report = dependency_report(analysis)
    base = Path(args.base) if args.base else Path(args.path) / BASE_FILE
    if args.aceptar:
        save_base(base, report)
        print(f"Base guardada en {base}: {len(report.cycles)} ciclos y "
              f"{len(report.skips)} capas saltadas aceptados.")
        return EXIT_OK
    known = load_base(base)
    new_cycles = [c for c in report.cycles if c.key not in known]
    new_skips = [s for s in report.skips if s.key not in known]
    current = {c.key for c in report.cycles} | {s.key for s in report.skips}
    gone = sorted(k for k in known if k not in current)
    fails = bool(new_cycles) or (args.capas and bool(new_skips))
    if args.json:
        data = {
            "ok": not fails,
            "archivos": report.n_files,
            "relaciones": report.n_edges,
            "ciclos": [{"clave": c.key, "nivel": c.level, "camino": list(c.path),
                        "nuevo": c.key not in known,
                        "pasos": [{"motivo": s.why, "en": s.at} for s in c.steps]}
                       for c in report.cycles],
            "capas": [{"clave": s.key, "texto": skip_text(s), "motivo": s.step.why,
                       "en": s.step.at, "nuevo": s.key not in known} for s in report.skips],
            "ya_no_estan": gone,
        }
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        return EXIT_CHECK if fails else EXIT_OK
    print(f"Dependencias: {report.n_files} archivos, {report.n_edges} relaciones.")
    old = len(report.cycles) - len(new_cycles)
    print(f"Ciclos: {len(report.cycles)}" + (f" ({old} ya aceptados en {base.name})"
                                              if old else ""))
    for c in new_cycles[:args.limit]:
        print(f"  NUEVO [{c.level}] {cycle_text(c, '->')}"
              + (f"  (el nudo tiene {len(c.members)})" if len(c.members) > len(c.path) - 1
                 else ""))
        for s in c.steps:
            print(f"      {s.at}  {s.why}")
    if len(new_cycles) > args.limit:
        print(f"  ... y {len(new_cycles) - args.limit} ciclos nuevos más (usa --json)")
    print(f"Capas que se saltan: {len(report.skips)}")
    for s in new_skips[:args.limit]:
        print(f"  {'NUEVO ' if args.capas else ''}{skip_text(s, '->')}")
        print(f"      {s.step.at}  {s.step.why}")
    if gone:
        print(f"Ya no están ({len(gone)}): actualiza la base con --aceptar.")
    if fails:
        print("Resultado: FALLA. Rompe el ciclo o, si se acepta, ejecuta "
              "`desglosa check RUTA --aceptar` y sube la base.")
    else:
        print("Resultado: bien, no hay ciclos nuevos.")
    return EXIT_CHECK if fails else EXIT_OK


def cmd_classes(args: argparse.Namespace) -> int:
    from desglosa.uml import build_uml

    # El Mermaid solo necesita las clases; el HTML completo lleva también los flujos.
    analysis, code = _run_analysis(args, flows=not args.mermaid)
    if analysis is None:
        return code
    index, diagrams = build_uml(analysis)
    if not index:
        print("No se encontraron clases ni interfaces.", file=sys.stderr)
        return EXIT_NOT_FOUND
    if args.carpeta is None:
        folder = min(index, key=lambda f: (-index[f]["clases"], f))  # la de más clases
    else:
        folder = args.carpeta.strip().replace("\\", "/").strip("/")
        folder = "" if folder == "." else folder
        if folder not in index:
            print(f"La carpeta {args.carpeta!r} no tiene clases. Carpetas con clases:",
                  file=sys.stderr)
            for f in sorted(index):
                print(f"  {f or '.'} ({index[f]['clases']})", file=sys.stderr)
            return EXIT_NOT_FOUND
    if args.mermaid:
        _write_text(args.output or "-", diagrams[folder]["mermaid"])
        if args.output and args.output != "-":
            print(f"Mermaid escrito en {args.output}")
        return EXIT_OK
    args.output = args.output or "clases.html"
    _write_app(args, analysis, "#/clases/" + (folder or "."))
    total = sum(v["clases"] for v in index.values())
    print(f"Clases: {total} en {len(index)} carpeta{'s' if len(index) != 1 else ''}"
          f" · abre en {folder or '(raíz)'}")
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


def cmd_draw(args: argparse.Namespace) -> int:
    from desglosa.mermaid import MermaidError, drawing_payload, parse_mermaid
    from desglosa.render.html import render_html
    from desglosa.render.packs import FORMAT
    from desglosa.scan import decode_bytes

    if args.file == "-":
        text = sys.stdin.read()
        name = "dibujo"
    else:
        source = Path(args.file)
        if not source.is_file():
            print(f"No existe el archivo: {source}", file=sys.stderr)
            return EXIT_USAGE
        text = decode_bytes(source.read_bytes())[0]
        name = source.stem
    try:
        drawing = parse_mermaid(text)
    except MermaidError as exc:
        print(f"No pude leer el diagrama: {exc}", file=sys.stderr)
        return EXIT_USAGE
    title = args.titulo or drawing.title or name
    payload = {
        "meta": {"name": title, "version": __version__, "start": "#/dibujo",
                 "generator": "Desglosa", "format": FORMAT},
        "drawing": drawing_payload(drawing, text),
    }
    _write_text(args.output, render_html(payload, f"{title} — Desglosa"))
    for w in drawing.warnings:
        print(f"  Aviso: {w}")
    print(f"Diagrama: {len(drawing.nodes)} nodos, {len(drawing.edges)} flechas.")
    print(f"HTML escrito en {args.output}")
    return EXIT_OK


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


def _write_app(args: argparse.Namespace, analysis, start: str, depth: int = 4,
               extra: dict | None = None, extra_packs: dict | None = None) -> str:
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
        extra=extra,
        extra_packs=extra_packs,
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


def _add_analysis_args(p: argparse.ArgumentParser, with_path: bool = True) -> None:
    if with_path:
        p.add_argument("path", help="carpeta o archivo a analizar")
    else:
        p.set_defaults(path=None)
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

    p = sub.add_parser("mermaid", help="el flujo (o la secuencia) de una función en Mermaid")
    _add_analysis_args(p)
    p.add_argument("name", metavar="nombre", help="Clase.metodo, funcion o archivo:Nombre")
    p.add_argument("--secuencia", action="store_true", help="diagrama de secuencia")
    p.add_argument("--depth", type=int, default=4, help="profundidad de la secuencia (def. 4)")
    p.add_argument("--externas", action="store_true", help="incluir llamadas externas")
    p.add_argument("--tecnico", action="store_true", help="textos con el código literal")
    p.add_argument("-o", "--output", default="-", help="archivo .mmd ('-' = pantalla)")
    _add_flow_args(p)
    p.set_defaults(func=cmd_mermaid)

    p = sub.add_parser(
        "comparar", aliases=["compare"],
        help="qué funciones cambiaron entre dos versiones, con sus flujos de antes y después",
    )
    p.add_argument("rutas", nargs="+", metavar="ruta",
                   help="dos carpetas (antes y después), o una con --desde COMMIT")
    p.add_argument("--desde", help="commit, rama o etiqueta de git de la versión anterior")
    p.add_argument("--hasta", help="commit de la versión nueva (def. la copia de trabajo)")
    p.add_argument("-o", "--output", help="archivo HTML de salida (def. comparar.html)")
    p.add_argument("--limit", type=int, default=30, help="máximo de funciones a listar")
    p.add_argument("--json", action="store_true", help="salida en JSON (sin HTML)")
    _add_analysis_args(p, with_path=False)
    _add_flow_args(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser(
        "check", aliases=["revisar"],
        help="ciclos entre carpetas o archivos y capas que se saltan (para CI)",
    )
    _add_analysis_args(p)
    p.add_argument("--base", help="archivo de ciclos aceptados (def. RUTA/.desglosa-check.json)")
    p.add_argument("--aceptar", action="store_true",
                   help="guarda lo que hay hoy como aceptado (la base) y termina bien")
    p.add_argument("--capas", action="store_true",
                   help="falla también con capas que se saltan nuevas (no solo ciclos)")
    p.add_argument("--limit", type=int, default=20, help="máximo de casos a mostrar (def. 20)")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser(
        "pseudo", aliases=["pseudocodigo"],
        help="pseudocódigo estilo PSeInt de una función o de un archivo entero",
    )
    _add_analysis_args(p)
    p.add_argument("name", metavar="nombre",
                   help="Clase.metodo, funcion, archivo:Nombre o un archivo (p. ej. gps.c)")
    p.add_argument("-o", "--output", default="-", help="archivo .psc ('-' = pantalla)")
    _add_flow_args(p)
    p.set_defaults(func=cmd_pseudo)

    p = sub.add_parser(
        "clases", aliases=["classes"], help="diagrama de clases UML de una carpeta"
    )
    _add_analysis_args(p)
    p.add_argument("--carpeta", help="carpeta a dibujar ('.' = raíz; def. la de más clases)")
    p.add_argument("--mermaid", action="store_true", help="salida en Mermaid (classDiagram)")
    p.add_argument("-o", "--output",
                   help="archivo de salida (def. clases.html; con --mermaid, la pantalla)")
    _add_flow_args(p)
    p.set_defaults(func=cmd_classes)

    p = sub.add_parser(
        "dibujar", aliases=["draw"],
        help="dibuja un diagrama de flujo escrito en Mermaid con el estilo de Desglosa",
    )
    p.add_argument("file", metavar="archivo.mmd", help="texto Mermaid ('-' = entrada estándar)")
    p.add_argument("-o", "--output", default="dibujo.html", help="archivo HTML de salida")
    p.add_argument("--titulo", help="título del diagrama")
    p.set_defaults(func=cmd_draw)

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
