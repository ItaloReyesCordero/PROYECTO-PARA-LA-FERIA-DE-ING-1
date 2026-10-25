"""Orquesta las etapas: scan → parse/extract → resolve → Project (SPEC §4)."""

from __future__ import annotations

import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

from desglosa import grammars, langs
from desglosa.extract import FileResult, extract_file
from desglosa.flows_stage import FlowOutput, make_tasks, run_tasks
from desglosa.ir import CONFIDENCES, Project, SourceFile
from desglosa.resolve import resolve
from desglosa.routes import Route, find_routes, is_route_file
from desglosa.scan import ScanOptions, ScanResult, decode_bytes, grammar_for, scan
from desglosa.sqlmodel import merge, parse_sql, table_access

# Con pocos archivos, arrancar procesos (spawn en Windows) cuesta más de lo que ahorra.
PARALLEL_MIN_FILES = 40


@dataclass(frozen=True)
class AnalyzeOptions:
    scan: ScanOptions = field(default_factory=ScanOptions)
    jobs: int | None = None
    max_flow_nodes: int = 120
    flow_max_height: float = 1600
    flows: bool = True
    dialect: str | None = None


@dataclass
class Analysis:
    project: Project
    scan: ScanResult
    results: list[FileResult]
    seconds: float
    flows: dict[str, FlowOutput] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)

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


def _jobs_for(n_files: int, jobs: int | None) -> int:
    if jobs is not None:
        return max(1, jobs)
    if n_files < PARALLEL_MIN_FILES:
        return 1
    return max(1, min(os.cpu_count() or 1, 8))


def extract_all(result: ScanResult, jobs: int | None = None) -> list[FileResult]:
    root = str(result.root)
    entries = result.entries
    n_jobs = _jobs_for(len(entries), jobs)
    if n_jobs <= 1 or len(entries) < 2:
        out = [_safe_extract(root, e.path, e.lang) for e in entries]
    else:
        with ProcessPoolExecutor(max_workers=n_jobs) as pool:
            out = list(
                pool.map(
                    _safe_extract,
                    [root] * len(entries),
                    [e.path for e in entries],
                    [e.lang for e in entries],
                    chunksize=max(1, len(entries) // (n_jobs * 4)),
                )
            )
    return sorted(out, key=lambda r: r.file.path)


def analyze(target: Path | str, options: AnalyzeOptions | None = None) -> Analysis:
    options = options or AnalyzeOptions()
    start = time.perf_counter()
    scanned = scan(Path(target), options.scan)
    grammars.ensure_offline_available(required_grammars(scanned))
    results = extract_all(scanned, options.jobs)
    symbols, calls = resolve(results)
    imports = sorted(
        (imp for r in results for imp in r.imports),
        key=lambda i: (i.file, i.line, i.module_text, i.name or ""),
    )
    files = sorted([r.file for r in results] + scanned.skipped, key=lambda f: f.path)
    warnings = [w for r in results for w in r.warnings]
    warnings += [f"{s.path}: saltado ({s.skipped_reason})" for s in scanned.skipped]
    flows: dict[str, FlowOutput] = {}
    if options.flows:
        tasks = make_tasks(
            str(scanned.root), symbols, calls, options.max_flow_nodes, options.flow_max_height
        )
        for out in run_tasks(tasks, _jobs_for(len(tasks), options.jobs)):
            flows[out.graph.symbol_id] = out
            warnings.extend(out.warnings)
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
    )
    return Analysis(project, scanned, results, time.perf_counter() - start, flows, routes)


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
    lines.append(f"  Tiempo: {analysis.seconds:.2f} s")
    return "\n".join(lines)
