"""Comparar dos versiones del código (Bloque 4): qué funciones son nuevas, cuáles se
eliminaron y cuáles cambiaron, con su diagrama de flujo de antes y de después.

- Una función se reconoce por su archivo y su nombre completo (`Clase.metodo`); si hay
  varias con el mismo nombre (sobrecargas), por su orden en el archivo. Un archivo
  renombrado cuenta como funciones eliminadas y nuevas.
- "Cambió" quiere decir que cambió su texto, sin contar espacios al final ni líneas
  vacías: moverla de lugar no es un cambio; un comentario nuevo sí.
- La versión anterior puede ser otra carpeta o un commit de git (`git archive`, que se
  extrae en una carpeta temporal sin seguir enlaces). El código nunca se ejecuta.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from desglosa.scan import decode_bytes

FUNC_KINDS = ("function", "method")


class CompareError(Exception):
    """Algo impide comparar (no es un repositorio git, el commit no existe…)."""


@dataclass
class FuncChange:
    status: str  # "nueva" | "eliminada" | "cambiada"
    file: str
    qualname: str
    before: str | None  # id del símbolo en la versión anterior
    after: str | None  # id en la versión nueva
    lines_before: int | None = None
    lines_after: int | None = None
    cc_before: int | None = None
    cc_after: int | None = None


@dataclass
class Comparison:
    before_label: str
    after_label: str
    changes: list[FuncChange] = field(default_factory=list)
    files_added: list[str] = field(default_factory=list)
    files_removed: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)

    def of(self, status: str) -> list[FuncChange]:
        return [c for c in self.changes if c.status == status]


# --------------------------------------------------------------------------- git


def export_commit(repo: Path, ref: str) -> tuple[Path, Path]:
    """Extrae `ref` en una carpeta temporal. Devuelve (carpeta temporal, la misma ruta que
    `repo` dentro de ella). Quien llama borra la carpeta temporal."""
    if not ref or ref.startswith("-"):
        raise CompareError(f"referencia de git no válida: {ref!r}")
    top = _git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if not top:
        raise CompareError(f"{repo} no está dentro de un repositorio git")
    inside = Path(repo).resolve().relative_to(Path(top).resolve())
    data = _git(Path(top), "archive", "--format=tar", ref)
    tmp = Path(tempfile.mkdtemp(prefix="desglosa-antes-"))
    try:
        _extract(data, tmp)
    except (tarfile.TarError, OSError) as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CompareError(f"no se pudo extraer {ref}: {exc}") from exc
    return tmp, tmp.joinpath(*inside.parts)


def _git(cwd: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=False)
    except OSError as exc:
        raise CompareError("no se encontró git en este equipo") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise CompareError(msg[-1] if msg else f"git {args[0]} falló")
    return proc.stdout


def _extract(data: bytes, dest: Path) -> None:
    """Solo archivos y carpetas, dentro de `dest`: nada de enlaces ni rutas con `..`."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or member.name.startswith("/") or ".." in parts:
                continue
            target = dest.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                if src is not None:
                    target.write_bytes(src.read())


# --------------------------------------------------------------------------- comparar


def _functions(analysis) -> dict[tuple[str, str, int], object]:
    """(archivo, nombre completo, n.º de repetición) → símbolo."""
    out = {}
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for s in sorted(analysis.project.symbols, key=lambda s: (s.file, s.line_start, s.id)):
        if s.kind not in FUNC_KINDS:
            continue
        n = seen[(s.file, s.qualname)]
        seen[(s.file, s.qualname)] += 1
        out[(s.file, s.qualname, n)] = s
    return out


class _Texts:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache: dict[str, list[str]] = {}

    def body(self, sym) -> str:
        lines = self.cache.get(sym.file)
        if lines is None:
            try:
                text = decode_bytes((self.root / sym.file).read_bytes())[0]
            except OSError:
                text = ""
            lines = self.cache[sym.file] = text.splitlines()
        chunk = lines[sym.line_start - 1:sym.line_end]
        return "\n".join(ln.rstrip() for ln in chunk if ln.strip())


def compare(before, after, before_label: str, after_label: str) -> Comparison:
    """Las diferencias entre dos análisis (de la misma carpeta en dos momentos)."""
    from desglosa.flows_stage import cyclomatic

    files_b = {f.path: f.sha1 for f in before.project.files if f.skipped_reason is None}
    files_a = {f.path: f.sha1 for f in after.project.files if f.skipped_reason is None}
    out = Comparison(
        before_label,
        after_label,
        files_added=sorted(set(files_a) - set(files_b)),
        files_removed=sorted(set(files_b) - set(files_a)),
        files_changed=sorted(p for p in set(files_a) & set(files_b) if files_a[p] != files_b[p]),
    )
    fb, fa = _functions(before), _functions(after)
    tb, ta = _Texts(Path(before.scan.root)), _Texts(Path(after.scan.root))

    def cc(analysis, sym) -> int | None:
        flow = analysis.flows.get(sym.id) if sym is not None else None
        return cyclomatic(flow.graph) if flow is not None and flow.graph.nodes else None

    def size(sym) -> int:
        return sym.line_end - sym.line_start + 1

    for key in sorted(set(fb) | set(fa)):
        sb, sa = fb.get(key), fa.get(key)
        file, qualname, _ = key
        if sb is None:
            out.changes.append(FuncChange("nueva", file, qualname, None, sa.id,
                                          lines_after=size(sa), cc_after=cc(after, sa)))
        elif sa is None:
            out.changes.append(FuncChange("eliminada", file, qualname, sb.id, None,
                                          lines_before=size(sb), cc_before=cc(before, sb)))
        elif files_a[file] != files_b[file] and tb.body(sb) != ta.body(sa):
            out.changes.append(FuncChange("cambiada", file, qualname, sb.id, sa.id,
                                          size(sb), size(sa), cc(before, sb), cc(after, sa)))
    return out


def files_needing_flows(comparison: Comparison, before) -> list[str]:
    """Archivos de la versión anterior con funciones cambiadas o eliminadas: solo de
    esos hace falta dibujar el flujo de antes."""
    by_id = {s.id: s for s in before.project.symbols}
    return sorted({by_id[c.before].file for c in comparison.changes
                   if c.before is not None and c.before in by_id})


def payload(comparison: Comparison, before) -> tuple[dict, dict[str, dict]]:
    """(índice para el visor, paquetes "@antes/<archivo>" con los flujos de antes)."""
    packs: dict[str, dict] = defaultdict(dict)
    by_id = {s.id: s for s in before.project.symbols}
    rows = []
    for c in comparison.changes:
        if c.before is not None and c.before in before.flows:
            packs[by_id[c.before].file][c.before] = before.flows[c.before].payload()
        rows.append([c.status, c.file, c.qualname, c.before, c.after, c.lines_before,
                     c.lines_after, c.cc_before, c.cc_after])
    index = {
        "antes": comparison.before_label,
        "despues": comparison.after_label,
        "funciones": rows,
        "archivos": {"nuevos": comparison.files_added, "eliminados": comparison.files_removed,
                     "cambiados": comparison.files_changed},
    }
    return index, {f"@antes/{f}": {"flows": v} for f, v in sorted(packs.items())}
