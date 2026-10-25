"""Orquesta las etapas: scan → parse/extract → resolve → Project (SPEC §4)."""

from __future__ import annotations

import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

from desglosa import grammars, langs
from desglosa.cache import Cache, fingerprint, from_jsonable, write_entry
from desglosa.extract import FileResult, extract_file
from desglosa.flows_stage import FlowOutput, FlowTask, make_tasks, run_task_groups
from desglosa.ir import CONFIDENCES, FlowGraph, Project, SourceFile
from desglosa.notes import attach_symbols, project_dirs, readme_notes
from desglosa.resolve import resolve
from desglosa.routes import Route, find_routes, is_route_file
from desglosa.scan import ScanOptions, ScanResult, decode_bytes, grammar_for, scan
from desglosa.sqlmodel import merge, parse_sql, table_access

# Arrancar procesos (spawn en Windows) cuesta ~0,4 s cada uno. Medido: con 1 000 archivos
# pequeños (0,8 MB) un proceso es más rápido que ocho; con 15 MB, ocho procesos ganan.
PARALLEL_MIN_FILES = 40
PARALLEL_MIN_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class AnalyzeOptions:
    scan: ScanOptions = field(default_factory=ScanOptions)
    jobs: int | None = None
    max_flow_nodes: int = 120
    flow_max_height: float = 1600
    flows: bool = True
    dialect: str | None = None
    cache_dir: Path | None = None  # None = sin caché (el CLI pasa la del usuario)


@dataclass
class Analysis:
    project: Project
    scan: ScanResult
    results: list[FileResult]
    seconds: float
    flows: dict[str, FlowOutput] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    cache_info: str | None = None  # p. ej. "798 de 800 archivos sin cambios"
    readmes: dict[str, str] = field(default_factory=dict)  # carpeta → resumen de su README

    @property
    def new_calls(self) -> set[str]:
        """Ids de las llamadas `new X()` de todo el proyecto."""
        return {c for r in self.results for c in r.new_calls}


def _read_text(root: Path, path: str) -> str:
    return decode_bytes((root / path).read_bytes())[0]


def required_grammars(result: ScanResult) -> set[str]:
    return {grammar_for(e.path, e.lang) for e in result.entries if e.lang in langs.SUPPORTED}


def _safe_extract(root: str, path: str, lang: str) -> FileResult:
    """Nunca abortar todo el análisis por un archivo."""
    try:
        return extract_file(root, path, lang)
    except grammars.MissingGrammarError:
        raise
    except Exception as exc:  # pragma: no cover - defensa ante gramáticas raras
        data = (Path(root) / path).read_bytes()
        import hashlib

        reason = f"error interno al analizar: {type(exc).__name__}"
        return FileResult(
            SourceFile(path, lang, hashlib.sha1(data).hexdigest(), 0, False, 0, reason),
            warnings=[f"{path}: {reason}"],
        )


def _jobs_for(n_files: int, jobs: int | None, total_bytes: int | None = None) -> int:
    if jobs is not None:
        return max(1, jobs)
    if n_files < PARALLEL_MIN_FILES:
        return 1
    if total_bytes is not None and total_bytes < PARALLEL_MIN_BYTES:
        return 1
    return max(1, min(os.cpu_count() or 1, 8))


def _extract_key(entry) -> str:
    return fingerprint("extract", entry.path, entry.lang, entry.sha1)


def _extract_job(root: str, path: str, lang: str, cache_file: str | None) -> FileResult:
    """Función de trabajo: extrae un archivo y, si se pide, guarda su entrada de caché."""
    result = _safe_extract(root, path, lang)
    if cache_file is not None:
        write_entry(cache_file, result)
    return result


def extract_all(
    result: ScanResult,
    jobs: int | None = None,
    pool: ProcessPoolExecutor | None = None,
    cache: Cache | None = None,
) -> list[FileResult]:
    root = str(result.root)
    out: list[FileResult] = []
    todo = []
    for e in result.entries:
        data = cache.get("extract", _extract_key(e)) if cache is not None and e.sha1 else None
        if data is not None:
            out.append(from_jsonable(FileResult, data))
        else:
            todo.append(e)
    files = [
        cache.path_for("extract", _extract_key(e)) if cache is not None and e.sha1 else None
        for e in todo
    ]
    # Varios procesos solo si lo pendiente lo amerita (o si se pidió con --jobs).
    n_jobs = _jobs_for(len(todo), jobs, sum(e.size for e in todo))
    if n_jobs <= 1 or len(todo) < 2:
        fresh = [_extract_job(root, e.path, e.lang, f) for e, f in zip(todo, files, strict=True)]
    else:
        own = pool is None
        executor = pool or ProcessPoolExecutor(max_workers=n_jobs)
        try:
            fresh = list(
                executor.map(
                    _extract_job,
                    [root] * len(todo),
                    [e.path for e in todo],
                    [e.lang for e in todo],
                    files,
                    chunksize=max(1, len(todo) // (n_jobs * 4)),
                )
            )
        finally:
            if own:
                executor.shutdown()
    out.extend(fresh)
    return sorted(out, key=lambda r: r.file.path)


def _flow_key(task: FlowTask, sha1: str) -> str:
    return fingerprint(
        "flows", task.path, task.lang, sha1, task.symbols, task.calls, task.max_nodes,
        task.max_height,
    )


def _flows_from_cache(data: dict) -> list[FlowOutput]:
    # Se guarda la vista ya lista para el HTML: reconstruir el layout objeto por objeto
    # para luego volver a convertirlo en JSON costaba la mitad del reanálisis.
    return [
        FlowOutput(
            from_jsonable(FlowGraph, item["graph"]),
            None,
            list(item["warnings"]),
            view=item["view"],
        )
        for item in data["items"]
    ]


def build_flows(
    tasks: list[FlowTask],
    sha_of: dict[str, str],
    size_of: dict[str, int],
    jobs: int | None,
    pool: ProcessPoolExecutor | None,
    cache: Cache | None,
) -> tuple[list[FlowOutput], int]:
    """Flujos de todos los archivos (los que no cambiaron salen de la caché)."""
    groups: dict[int, list[FlowOutput]] = {}
    keys = [_flow_key(t, sha_of.get(t.path, "")) for t in tasks] if cache is not None else []
    todo: list[int] = []
    for i in range(len(tasks)):
        data = cache.get("flows", keys[i]) if cache is not None else None
        if data is not None:
            groups[i] = _flows_from_cache(data)
        else:
            todo.append(i)
    pending = [tasks[i] for i in todo]
    n_jobs = _jobs_for(len(pending), jobs, sum(size_of.get(t.path, 0) for t in pending))
    files = [cache.path_for("flows", keys[i]) for i in todo] if cache is not None else None
    computed = run_task_groups(pending, n_jobs, pool if n_jobs > 1 else None, files)
    for i, group in zip(todo, computed, strict=True):
        groups[i] = group
    hits = len(tasks) - len(todo)
    return [o for i in range(len(tasks)) for o in groups[i]], hits


def analyze(target: Path | str, options: AnalyzeOptions | None = None) -> Analysis:
    options = options or AnalyzeOptions()
    start = time.perf_counter()
    scanned = scan(Path(target), options.scan)
    grammars.ensure_offline_available(required_grammars(scanned))
    n_jobs = _jobs_for(
        len(scanned.entries), options.jobs, sum(e.size for e in scanned.entries)
    )
    # Un solo grupo de procesos para extraer y para los flujos. Los procesos se arrancan
    # recién cuando hay trabajo, así que si todo sale de la caché no cuesta nada.
    pool = ProcessPoolExecutor(max_workers=n_jobs) if n_jobs > 1 else None
    cache = Cache(options.cache_dir, scanned.root) if options.cache_dir is not None else None
    try:
        analysis = _analyze(scanned, options, start, pool, cache)
    finally:
        if pool is not None:
            pool.shutdown()
    if cache is not None:
        cache.prune()
    return analysis


def _analyze(
    scanned: ScanResult,
    options: AnalyzeOptions,
    start: float,
    pool: ProcessPoolExecutor | None,
    cache: Cache | None,
) -> Analysis:
    jobs = options.jobs
    results = extract_all(scanned, jobs, pool, cache)
    extract_hits = cache.hits if cache is not None else 0
    symbols, calls = resolve(results)
    imports = sorted(
        (imp for r in results for imp in r.imports),
        key=lambda i: (i.file, i.line, i.module_text, i.name or ""),
    )
    files = sorted([r.file for r in results] + scanned.skipped, key=lambda f: f.path)
    warnings = [w for r in results for w in r.warnings]
    warnings += [f"{s.path}: saltado ({s.skipped_reason})" for s in scanned.skipped]
    flows: dict[str, FlowOutput] = {}
    flow_hits = n_tasks = 0
    if options.flows:
        tasks = make_tasks(
            str(scanned.root), symbols, calls, options.max_flow_nodes, options.flow_max_height
        )
        n_tasks = len(tasks)
        outputs, flow_hits = build_flows(
            tasks,
            {r.file.path: r.file.sha1 for r in results},
            {e.path: e.size for e in scanned.entries},
            jobs,
            pool,
            cache,
        )
        for out in outputs:
            flows[out.graph.symbol_id] = out
            warnings.extend(out.warnings)
    cache_info = None
    if cache is not None:
        cache_info = (
            f"{extract_hits} de {len(scanned.entries)} archivos sin cambios"
            + (f", {flow_hits} de {n_tasks} con flujos ya dibujados" if n_tasks else "")
        )
    # SQL: tablas y FK de los .sql; enlace función → tabla desde las cadenas del código.
    sql_models = [
        parse_sql(e.path, _read_text(scanned.root, e.path), options.dialect)
        for e in scanned.entries
        if e.lang == "sql"
    ]
    sql = merge(sql_models)
    warnings.extend(sql.warnings)
    code_files = sorted({s.file for s in symbols if s.kind in ("function", "method")})
    sources = {path: _read_text(scanned.root, path) for path in code_files}
    access = table_access(symbols, sources, [t.name for t in sql.tables])
    # Rutas de Laravel: los métodos referenciados son puntos de entrada.
    route_files = [e.path for e in scanned.entries if is_route_file(e.path)]
    routes = find_routes(
        {p: _read_text(scanned.root, p) for p in route_files}, symbols
    )
    if routes:
        entry_ids = {r.symbol_id for r in routes if r.symbol_id}
        symbols = [replace(s, is_entry=True) if s.id in entry_ids else s for s in symbols]
        warnings.extend(
            f"{r.file}:{r.line}: ruta {r.verb} {r.path} apunta a {r.target} (no encontrado)"
            for r in routes
            if not r.symbol_id
        )
    order = {s.id: i for i, s in enumerate(symbols)}
    project = Project(
        root_name=scanned.root_name,
        files=tuple(files),
        symbols=tuple(symbols),
        imports=tuple(imports),
        calls=tuple(calls),
        flows=tuple(
            f.graph for f in sorted(flows.values(), key=lambda f: order[f.graph.symbol_id])
        ),
        tables=tuple(sql.tables),
        fks=tuple(sql.fks),
        table_access=tuple(access),
        warnings=tuple(sorted(warnings)),
        notes=tuple(attach_symbols([n for r in results for n in r.notes], symbols)),
    )
    readmes = readme_notes(scanned.root, project_dirs(e.path for e in scanned.entries))
    return Analysis(
        project, scanned, results, time.perf_counter() - start, flows, routes, cache_info,
        readmes,
    )


def summary(analysis: Analysis) -> str:
    """Resumen en español para la consola."""
    p = analysis.project
    by_lang = Counter(f.lang for f in p.files if f.skipped_reason is None)
    skipped = [f for f in p.files if f.skipped_reason is not None]
    conf = Counter(c.confidence for c in p.calls)
    kinds = Counter(s.kind for s in p.symbols if s.kind != "module")
    lines = [f"Proyecto: {p.root_name}"]
    langs_txt = ", ".join(f"{lang} {n}" for lang, n in sorted(by_lang.items())) or "ninguno"
    lines.append(f"  Archivos analizados: {sum(by_lang.values())} ({langs_txt})")
    kinds_txt = ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) or "ninguno"
    lines.append(f"  Símbolos: {sum(kinds.values())} ({kinds_txt})")
    conf_txt = ", ".join(f"{c} {conf.get(c, 0)}" for c in CONFIDENCES)
    lines.append(f"  Llamadas: {len(p.calls)} ({conf_txt})")
    if p.tables:
        lines.append(f"  Tablas SQL: {len(p.tables)} ({len(p.fks)} relaciones)")
    if analysis.routes:
        lines.append(f"  Rutas: {len(analysis.routes)}")
    if skipped:
        lines.append(f"  Saltados: {len(skipped)}")
        for f in skipped[:10]:
            lines.append(f"    - {f.path}: {f.skipped_reason}")
    errors = [f for f in p.files if f.errors]
    if errors:
        lines.append(f"  Con errores de sintaxis: {len(errors)}")
    if analysis.cache_info:
        lines.append(f"  Caché: {analysis.cache_info}")
    lines.append(f"  Tiempo: {analysis.seconds:.2f} s")
    return "\n".join(lines)
