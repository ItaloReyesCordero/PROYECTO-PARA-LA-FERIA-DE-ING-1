"""AST → símbolos, imports y llamadas con su contexto de control (SPEC §6.2).

Un único motor genérico recorre el árbol guiado por el `LangSpec` de cada lenguaje.
Las funciones de este módulo que se ejecutan en otros procesos son de nivel módulo
(Windows usa `spawn` y necesita poder importarlas).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from tree_sitter import Node

from desglosa import grammars, langs
from desglosa.ir import (
    Call,
    ControlCtx,
    DeclaredMethod,
    Import,
    Member,
    MethodInfo,
    Note,
    SourceFile,
    Symbol,
    stable_id,
)
from desglosa.langs.builtins import classify_io
from desglosa.langs.spec import (
    Binding,
    CallParts,
    LangHooks,
    LangSpec,
    Src,
    normalize_type,
    one_line,
)
from desglosa.notes import find_notes
from desglosa.scan import count_lines, decode_bytes, grammar_for

RECURSION_LIMIT = 20000


@dataclass
class FileResult:
    """Resultado de extraer un archivo. Además del IR guarda pistas internas para resolver."""

    file: SourceFile
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    new_calls: list[str] = field(default_factory=list)  # ids de llamadas `new X()`
    class_bases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    abstract: list[str] = field(default_factory=list)  # métodos sin cuerpo
    var_types: dict[str, dict[str, str]] = field(default_factory=dict)  # función → var → tipo
    field_types: dict[str, dict[str, str]] = field(default_factory=dict)  # clase → campo → tipo
    qualifiers: dict[str, str] = field(default_factory=dict)  # método C++ → clase dueña
    extra_bases: list[tuple[str, str]] = field(default_factory=list)  # (tipo, base) externos
    warnings: list[str] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)  # TODO, FIXME, NOTE… en comentarios
    # Diagrama de clases (Bloque 4): atributos de cada clase, datos de cada método y
    # clases abstractas. No son parte del IR exportado.
    members: dict[str, list[Member]] = field(default_factory=dict)
    method_info: dict[str, MethodInfo] = field(default_factory=dict)
    abstract_classes: list[str] = field(default_factory=list)
    declared: dict[str, list[DeclaredMethod]] = field(default_factory=dict)


class _Frame:
    __slots__ = ("symbol", "kind", "class_frame", "prefix", "var_types", "field_types")

    def __init__(self, symbol: Symbol, kind: str, class_frame: _Frame | None) -> None:
        self.symbol = symbol
        self.kind = kind
        self.class_frame = class_frame
        self.prefix = "" if kind == "module" else symbol.qualname + "."
        self.var_types: dict[str, str] = {}
        self.field_types: dict[str, str] = {}


def _is_controller(name: str) -> bool:
    """`FacturaController` sí; la clase base `Controller` (o `BaseController`) no."""
    return name.endswith("Controller") and name not in ("Controller", "BaseController")


def call_id(lang: str, path: str, caller_qualname: str, callee: str, line: int, col: int) -> str:
    """Id estable de una llamada (mismo esquema que los símbolos)."""
    return stable_id(lang, path, f"{caller_qualname}->{callee}@{col}", line)


def module_qualname(path: str) -> str:
    return path


class _Walker:
    def __init__(self, spec: LangSpec, hooks: LangHooks, path: str, lang: str, src: Src) -> None:
        self.spec = spec
        self.hooks = hooks
        self.path = path
        self.lang = lang
        self.src = src
        self.result: FileResult | None = None
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.new_calls: list[str] = []
        self.class_bases: dict[str, tuple[str, ...]] = {}
        self.abstract: list[str] = []
        self.qualifiers: dict[str, str] = {}
        self.extra_bases: list[tuple[str, str]] = []
        self.members: dict[str, list[Member]] = {}
        self.method_info: dict[str, MethodInfo] = {}
        self.abstract_classes: list[str] = []
        self.declared: dict[str, list[DeclaredMethod]] = {}
        self.frames: list[_Frame] = []
        self.used_ids: set[str] = set()
        self.module_entry = False
        s = spec
        self.class_types = set(s.class_nodes) | set(s.interface_nodes)
        self.function_types = set(s.function_nodes) | set(s.method_nodes)
        self.import_types = set(s.import_nodes)
        self.call_types = set(s.call_nodes)
        self.ifish = set(s.if_nodes) | set(s.elif_nodes)
        self.loops = set(s.loop_nodes) | set(s.do_while_nodes)

    # ------------------------------------------------------------------ símbolos

    def _new_id(self, qualname: str, line: int) -> str:
        sid = stable_id(self.lang, self.path, qualname, line)
        n = 2
        while sid in self.used_ids:
            sid = stable_id(self.lang, self.path, f"{qualname}#{n}", line)
            n += 1
        self.used_ids.add(sid)
        return sid

    def make_module(self, root: Node, lines: int) -> _Frame:
        qual = module_qualname(self.path)
        sym = Symbol(
            id=self._new_id(qual, 1),
            kind="module",
            name=Path(self.path).name,
            qualname=qual,
            file=self.path,
            line_start=1,
            line_end=max(1, lines),
            parent_id=None,
            doc=self.hooks.doc(root, self.src) if self.lang == "python" else None,
            lang=self.lang,
            signature=self.path,
        )
        self.symbols.append(sym)
        return _Frame(sym, "module", None)

    def add_symbol(
        self, node: Node, kind: str, name: str, frame: _Frame, qualifier: str | None = None
    ) -> Symbol:
        qualname = f"{qualifier}.{name}" if qualifier else frame.prefix + name
        line = node.start_point[0] + 1
        is_entry = False
        # `main` (C, Java, Python…) o `Main` (C#: `static void Main`).
        if (name == "main" or (name == "Main" and self.lang == "csharp")) and (
            frame.kind == "module" or (kind == "method" and self.hooks.is_static(node, self.src))
        ):
            is_entry = True
        if kind == "class" and _is_controller(name):
            is_entry = True
        if (
            kind == "method"
            and frame.kind == "class"
            and _is_controller(frame.symbol.name)
            and name not in self.spec.constructor_names
            and name != frame.symbol.name
        ):
            is_entry = True
        sym = Symbol(
            id=self._new_id(qualname, line),
            kind=kind,
            name=name,
            qualname=qualname,
            file=self.path,
            line_start=line,
            line_end=node.end_point[0] + 1,
            parent_id=frame.symbol.id,
            doc=self.hooks.doc(node, self.src),
            lang=self.lang,
            signature=self.hooks.signature(node, self.src),
            is_entry=is_entry,
        )
        self.symbols.append(sym)
        return sym

    def _merge_members(self, class_id: str, found: list[Member]) -> None:
        """Atributos creados en un método: solo los que la clase no declara ya.

        Si la clase ya lo declara sin tipo (`attr_accessor :centro`) y el método dice cuál
        es (`@centro = Punto.new`), se completa el tipo.
        """
        current = self.members[class_id]
        index = {m.name: i for i, m in enumerate(current)}
        for m in found:
            i = index.get(m.name)
            if i is None:
                index[m.name] = len(current)
                current.append(m)
            elif current[i].type is None and m.type is not None:
                current[i] = replace(current[i], type=m.type)

    # ------------------------------------------------------------------ recorrido

    def walk(self, node: Node, frame: _Frame, ctx: tuple[ControlCtx, ...]) -> None:
        t = node.type
        hooks, src = self.hooks, self.src

        kind = hooks.class_kind(node, src) if t in self.class_types else None
        if kind is not None:
            name = hooks.symbol_name(node, src)
            if name:
                sym = self.add_symbol(node, kind, name, frame)
                self.class_bases[sym.id] = hooks.class_bases(node, src)
                self.members[sym.id] = list(hooks.class_members(node, src))
                declared = hooks.declared_methods(node, src)
                if declared:
                    self.declared[sym.id] = declared
                if hooks.class_is_abstract(node, src):
                    self.abstract_classes.append(sym.id)
                inner = _Frame(sym, kind, None)
                inner.class_frame = inner
                self.frames.append(inner)
                for child in node.named_children:
                    self.walk(child, inner, ())
                return

        if t in self.function_types:
            name = hooks.symbol_name(node, src)
            if name:
                qualifier = hooks.symbol_qualifier(node, src)
                in_class = frame.kind in ("class", "interface")
                kind = (
                    "method"
                    if (in_class or qualifier or t in self.spec.method_nodes)
                    else "function"
                )
                sym = self.add_symbol(node, kind, name, frame, qualifier)
                if qualifier:
                    self.qualifiers[sym.id] = qualifier
                if not hooks.has_body(node):
                    self.abstract.append(sym.id)
                class_frame = frame if in_class else frame.class_frame
                if kind == "method":
                    self.method_info[sym.id] = hooks.method_info(node, src)
                    owner = class_frame.symbol.id if class_frame is not None else None
                    if owner in self.members:
                        self._merge_members(owner, hooks.assigned_members(node, src))
                inner = _Frame(sym, kind, class_frame)
                self.frames.append(inner)
                for child in node.named_children:
                    self.walk(child, inner, ())
                return

        if t in self.import_types:
            for parts in hooks.imports(node, src):
                self._add_import(node, parts.module, parts.name, parts.alias)
            return

        if t in self.call_types:
            imp = getattr(hooks, "call_import", None)
            parts_imp = imp(node, src) if imp is not None else None
            if parts_imp is not None:
                self._add_import(node, parts_imp.module, parts_imp.name, parts_imp.alias)
                return
            parts = hooks.call_parts(node, src)
            if parts is not None and parts.callee:
                self._add_call(node, parts, frame, ctx)

        for binding in hooks.bindings(node, src):
            self._add_binding(binding, frame)
        self.extra_bases.extend(hooks.extra_bases(node, src))

        if frame.kind == "module" and hooks.is_main_guard(node, src):
            self.module_entry = True

        for i, child in enumerate(node.children):
            if not child.is_named:
                continue
            field_name = node.field_name_for_child(i)
            self.walk(child, frame, self._child_ctx(node, child, field_name, ctx, i))

    def _child_ctx(
        self,
        node: Node,
        child: Node,
        field_name: str | None,
        ctx: tuple[ControlCtx, ...],
        index: int = 0,
    ) -> tuple[ControlCtx, ...]:
        t = node.type
        s = self.spec
        line = node.start_point[0] + 1
        if t in self.ifish:
            branch = self.hooks.if_branch(node, index, field_name, child)
            if branch == "cond":
                return ctx
            if branch == "else":
                return (*ctx, ControlCtx("else", child.start_point[0] + 1, "else"))
            label = one_line(self.hooks.condition(node, self.src), 60)
            return (*ctx, ControlCtx("if", line, label))
        if t in self.loops:
            return (*ctx, ControlCtx("loop", line, self._loop_label(node)))
        if t in s.case_nodes:
            if field_name == "value":
                return ctx
            value = self.hooks.case_value(node, self.src)
            label = f"caso {value}" if value is not None else "otro"
            return (*ctx, ControlCtx("switch_case", line, label))
        if t in s.try_nodes:
            if child.type in s.catch_nodes or child.type in s.finally_nodes:
                return ctx
            return (*ctx, ControlCtx("try", line, "intentar"))
        if t in s.catch_nodes:
            label = self.hooks.catch_label(node, self.src) or "excepción"
            return (*ctx, ControlCtx("catch", line, one_line(label, 60)))
        return ctx

    def _loop_label(self, node: Node) -> str:
        if node.type in self.spec.do_while_nodes:
            info = self.hooks.do_while_info(node, self.src)
        else:
            info = self.hooks.loop_info(node, self.src)
        if info.kind in ("while", "do") and info.cond_text:
            return one_line(info.cond_text, 60)
        if info.kind == "foreach" and info.header:
            return one_line(info.header, 60)
        if info.kind == "while":
            return "repetir"
        return one_line(self.hooks.loop_label(node, self.src), 60)

    # ------------------------------------------------------------------ registros

    def _add_import(self, node: Node, module: str, name: str | None, alias: str | None) -> None:
        if not module:
            return
        self.imports.append(
            Import(
                file=self.path,
                module_text=module,
                alias=alias,
                line=node.start_point[0] + 1,
                name=name,
            )
        )

    def _add_call(
        self, node: Node, parts: CallParts, frame: _Frame, ctx: tuple[ControlCtx, ...]
    ) -> None:
        line = node.start_point[0] + 1
        col = node.start_point[1] + 1
        cid = call_id(self.lang, self.path, frame.symbol.qualname, parts.callee, line, col)
        io = classify_io(self.lang, parts.callee, parts.receiver, parts.args, parts.is_new)
        self.calls.append(
            Call(
                id=cid,
                caller_id=frame.symbol.id,
                callee_text=parts.callee,
                receiver_text=parts.receiver,
                line=line,
                col=col,
                context=ctx,
                io_kind=io,
            )
        )
        if parts.is_new:
            self.new_calls.append(cid)

    def _add_binding(self, binding: Binding, frame: _Frame) -> None:
        typ = binding.type
        if typ.startswith("@var:"):
            found = frame.var_types.get(typ[5:])
            if not found:
                return
            typ = found
        typ = normalize_type(typ)
        if not typ:
            return
        if binding.scope == "local" and frame.kind in ("function", "method"):
            frame.var_types.setdefault(binding.name, typ)
        else:
            target = frame if frame.kind in ("class", "interface") else frame.class_frame
            if target is not None:
                target.field_types.setdefault(binding.name, typ)


def _count_errors(root: Node) -> int:
    if not root.has_error:
        return 0
    count = 0
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            count += 1
        if node.has_error:
            stack.extend(node.children)
    return count


def extract_bytes(path: str, lang: str, data: bytes) -> FileResult:
    """Extrae un archivo ya leído. `path` es la ruta POSIX relativa."""
    text, encoding = decode_bytes(data)
    lines = count_lines(text)
    sha1 = hashlib.sha1(data).hexdigest()
    registry = langs.get(lang)
    if registry is None:
        if lang == "sql":
            return FileResult(SourceFile(path, lang, sha1, lines, True, 0, None))
        reason = "extractor de este lenguaje pendiente"
        return FileResult(SourceFile(path, lang, sha1, lines, False, 0, reason))
    spec, hooks = registry
    parser = grammars.get_parser(grammar_for(path, lang))
    tree = parser.parse(data)
    errors = _count_errors(tree.root_node)
    walker = _Walker(spec, hooks, path, lang, Src(data, encoding))
    warnings: list[str] = []
    module_frame = walker.make_module(tree.root_node, lines)
    walker.frames.append(module_frame)
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, RECURSION_LIMIT))
    try:
        walker.walk(tree.root_node, module_frame, ())
    except RecursionError:
        warnings.append(f"{path}: archivo demasiado anidado; se extrajo solo una parte")
    finally:
        sys.setrecursionlimit(old_limit)
    if errors:
        warnings.append(f"{path}: {errors} error(es) de sintaxis; se analizó igual")

    symbols = walker.symbols
    if walker.module_entry:
        symbols[0] = replace(symbols[0], is_entry=True)
    var_types = {
        f.symbol.id: dict(sorted(f.var_types.items())) for f in walker.frames if f.var_types
    }
    field_types = {
        f.symbol.id: dict(sorted(f.field_types.items())) for f in walker.frames if f.field_types
    }
    return FileResult(
        file=SourceFile(path, lang, sha1, lines, errors == 0, errors, None),
        symbols=sorted(symbols, key=lambda s: (s.line_start, s.qualname, s.id)),
        imports=sorted(walker.imports, key=lambda i: (i.line, i.module_text, i.name or "")),
        calls=sorted(walker.calls, key=lambda c: (c.line, c.col, c.callee_text)),
        new_calls=sorted(walker.new_calls),
        class_bases=dict(sorted(walker.class_bases.items())),
        abstract=sorted(walker.abstract),
        var_types=dict(sorted(var_types.items())),
        field_types=dict(sorted(field_types.items())),
        qualifiers=dict(sorted(walker.qualifiers.items())),
        extra_bases=sorted(set(walker.extra_bases)),
        members={k: v for k, v in sorted(walker.members.items()) if v},
        method_info=dict(sorted(walker.method_info.items())),
        abstract_classes=sorted(walker.abstract_classes),
        declared=dict(sorted(walker.declared.items())),
        warnings=warnings,
        notes=find_notes(path, text),
    )


def extract_file(root: str, path: str, lang: str) -> FileResult:
    """Función de trabajo para procesos paralelos (nivel módulo, picklable)."""
    data = (Path(root) / path).read_bytes()
    return extract_bytes(path, lang, data)
