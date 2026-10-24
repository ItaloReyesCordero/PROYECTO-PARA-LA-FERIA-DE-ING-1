"""Orquesta las etapas: scan → parse/extract → resolve → Project (SPEC §4)."""

from __future__ import annotations

import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from desglosa import grammars, langs
from desglosa.extract import FileResult, extract_file
from desglosa.ir import CONFIDENCES, Project, SourceFile
from desglosa.resolve import resolve
from desglosa.scan import ScanOptions, ScanResult, grammar_for, scan

# Con pocos archivos, arrancar procesos (spawn en Windows) cuesta más de lo que ahorra.
PARALLEL_MIN_FILES = 40


@dataclass(frozen=True)
class AnalyzeOptions:
    scan: ScanOptions = field(default_factory=ScanOptions)
    jobs: int | None = None
    max_flow_nodes: int = 120


@dataclass
class Analysis:
    project: Project
    scan: ScanResult
    results: list[FileResult]
    seconds: float


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
    project = Project(
        root_name=scanned.root_name,
        files=tuple(files),
        symbols=tuple(symbols),
        imports=tuple(imports),
        calls=tuple(calls),
        warnings=tuple(sorted(warnings)),
    )
    return Analysis(project, scanned, results, time.perf_counter() - start)


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
    if skipped:
        lines.append(f"  Saltados: {len(skipped)}")
        for f in skipped[:10]:
            lines.append(f"    - {f.path}: {f.skipped_reason}")
    errors = [f for f in p.files if f.errors]
    if errors:
        lines.append(f"  Con errores de sintaxis: {len(errors)}")
    lines.append(f"  Tiempo: {analysis.seconds:.2f} s")
    return "\n".join(lines)
