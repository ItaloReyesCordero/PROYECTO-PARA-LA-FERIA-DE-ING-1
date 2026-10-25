"""Resolución de llamadas: llamada → definición + confianza (SPEC §6.3).

Regla de oro: no inventar. Si no hay forma de saber a qué se llama, la llamada queda
como "externa" (sin candidatos) o "ambigua" (varios candidatos posibles).
"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass, replace

from desglosa import langs
from desglosa.extract import FileResult
from desglosa.ir import Call, Import, Symbol

# Receptores globales conocidos: nunca son objetos del proyecto.
GLOBAL_RECEIVERS: dict[str, frozenset[str]] = {
    "javascript": frozenset(
        {
            "console",
            "Math",
            "JSON",
            "Object",
            "Array",
            "Promise",
            "window",
            "document",
            "process",
            "Number",
            "String",
            "Date",
            "Reflect",
            "localStorage",
            "sessionStorage",
        }
    ),
    "java": frozenset(
        {
            "System",
            "Math",
            "String",
            "Integer",
            "Long",
            "Double",
            "Boolean",
            "List",
            "Map",
            "Set",
            "Arrays",
            "Collections",
            "Objects",
            "Files",
            "Path",
            "Paths",
            "Optional",
        }
    ),
    "python": frozenset({"os", "sys", "json", "re", "math", "str", "dict", "list"}),
    "cpp": frozenset({"std"}),
}
GLOBAL_RECEIVERS["typescript"] = GLOBAL_RECEIVERS["javascript"]

_JS_EXTS = ("", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", "/index.js", "/index.ts")


@dataclass(frozen=True)
class _Res:
    resolved: str | None
    candidates: tuple[str, ...]
    confidence: str


_EXTERNAL = _Res(None, (), "externa")


def _sort_key(s: Symbol) -> tuple:
    return (s.file, s.kind != "module", s.line_start, s.qualname, s.id)


class Resolver:
    def __init__(self, results: list[FileResult]) -> None:
        self.results = results
        self.lang_of: dict[str, str] = {r.file.path: r.file.lang for r in results}
        self.files = set(self.lang_of)
        self.new_calls: set[str] = set()
        self.abstract: set[str] = set()
        self.var_types: dict[str, dict[str, str]] = {}
        self.field_types: dict[str, dict[str, str]] = {}
        raw_bases: dict[str, tuple[str, ...]] = {}
        qualifiers: dict[str, str] = {}
        symbols: list[Symbol] = []
        self.imports_by_file: dict[str, list[Import]] = defaultdict(list)
        for r in results:
            symbols.extend(r.symbols)
            self.new_calls.update(r.new_calls)
            self.abstract.update(r.abstract)
            self.var_types.update(r.var_types)
            self.field_types.update(r.field_types)
            raw_bases.update(r.class_bases)
            qualifiers.update(r.qualifiers)
            self.imports_by_file[r.file.path].extend(r.imports)
        # Índices de nombres de archivo: se calculan una vez, antes de cualquier `_narrow`
        # (antes se recorría `files` completo en cada import: archivos × imports).
        self._stems = {posixpath.splitext(f)[0] for f in self.files}
        self._stem_suffixes: set[str] = set()
        for stem in self._stems:
            parts = stem.split("/")
            self._stem_suffixes.update("/".join(parts[i:]) for i in range(len(parts)))
        self._base_stems = {posixpath.splitext(posixpath.basename(f))[0] for f in self.files}
        self._basenames = {posixpath.basename(f) for f in self.files}
        self._import_keys_cache: dict[str, tuple[set[str], set[str]]] = {}

        self.classes_by_name: dict[str, list[Symbol]] = defaultdict(list)
        for s in symbols:
            if s.kind in ("class", "interface"):
                self.classes_by_name[s.name].append(s)
        # Herencia declarada fuera de la clase (Rust `impl Trait for Tipo`).
        for r in results:
            for type_name, base in r.extra_bases:
                for cls in self._narrow(self.classes_by_name.get(type_name, []), r.file.path):
                    current = raw_bases.get(cls.id, ())
                    if base not in current:
                        raw_bases[cls.id] = (*current, base)
        # Métodos definidos fuera de su clase (C++ `A::m`): enlazar con la clase.
        fixed: list[Symbol] = []
        for s in symbols:
            owner = qualifiers.get(s.id)
            if owner:
                cands = self._narrow(self.classes_by_name.get(owner, []), s.file)
                if len(cands) == 1:
                    s = replace(s, parent_id=cands[0].id)
            fixed.append(s)
        self.symbols: list[Symbol] = sorted(fixed, key=_sort_key)
        self.by_id: dict[str, Symbol] = {s.id: s for s in self.symbols}

        self.members: dict[str, dict[str, list[Symbol]]] = defaultdict(lambda: defaultdict(list))
        self.funcs_by_file: dict[str, dict[str, list[Symbol]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.funcs_by_name: dict[str, list[Symbol]] = defaultdict(list)
        self.methods_by_name: dict[str, list[Symbol]] = defaultdict(list)
        for s in self.symbols:
            parent = self.by_id.get(s.parent_id) if s.parent_id else None
            if s.kind == "method" and parent is not None and parent.kind in ("class", "interface"):
                self.members[parent.id][s.name].append(s)
                self.methods_by_name[s.name].append(s)
            elif s.kind == "method":
                self.methods_by_name[s.name].append(s)
            elif s.kind == "function":
                self.funcs_by_file[s.file][s.name].append(s)
                self.funcs_by_name[s.name].append(s)

        # Herencia: nombres de bases → ids de clases conocidas.
        self.bases: dict[str, list[str]] = {}
        self.unknown_bases: set[str] = set()
        for cid, names in sorted(raw_bases.items()):
            cls = self.by_id.get(cid)
            if cls is None:
                continue
            ids: list[str] = []
            for name in names:
                cands = [
                    c
                    for c in self._narrow(self.classes_by_name.get(name, []), cls.file)
                    if c.id != cid
                ]
                if len(cands) == 1:
                    ids.append(cands[0].id)
                else:
                    self.unknown_bases.add(cid)
            self.bases[cid] = ids
        children: dict[str, list[str]] = defaultdict(list)
        for cid, ids in self.bases.items():
            for b in ids:
                children[b].append(cid)
        self.subclasses: dict[str, list[str]] = {}
        for cid in self.bases.keys() | children.keys():
            seen: list[str] = []
            stack = sorted(children.get(cid, []))
            while stack:
                cur = stack.pop(0)
                if cur in seen or cur == cid:
                    continue
                seen.append(cur)
                stack.extend(sorted(children.get(cur, [])))
            self.subclasses[cid] = seen

        self._project_module_cache: dict[tuple[str, str], bool] = {}

    # ------------------------------------------------------------------ utilidades

    def _narrow(self, cands: list[Symbol], file: str) -> list[Symbol]:
        """Reduce candidatos homónimos: mismo archivo > importado > misma carpeta."""
        if len(cands) <= 1:
            return list(cands)
        same = [c for c in cands if c.file == file]
        if same:
            return same
        imported = [c for c in cands if self._is_imported_in(c, file)]
        if imported:
            return imported
        folder = posixpath.dirname(file)
        near = [c for c in cands if posixpath.dirname(c.file) == folder]
        return near or list(cands)

    def _import_keys(self, file: str) -> tuple[set[str], set[str]]:
        """Nombres importados en `file` y nombres base de los módulos que importa."""
        cached = self._import_keys_cache.get(file)
        if cached is not None:
            return cached
        names: set[str] = set()
        stems: set[str] = set()
        for imp in self.imports_by_file.get(file, []):
            if imp.name:
                names.add(imp.name)
            if imp.alias:
                names.add(imp.alias)
            mod = imp.module_text.replace("\\", "/").rstrip("/")
            last = mod.rsplit("/", 1)[-1].rsplit(".", 1)
            stems.update((posixpath.splitext(posixpath.basename(mod))[0], last[-1], last[0]))
        self._import_keys_cache[file] = (names, stems)
        return names, stems

    def _is_imported_in(self, sym: Symbol, file: str) -> bool:
        names, stems = self._import_keys(file)
        if sym.name in names:
            return True
        return posixpath.splitext(posixpath.basename(sym.file))[0] in stems

    def enclosing_class(self, sym: Symbol | None) -> Symbol | None:
        cur = self.by_id.get(sym.parent_id) if sym is not None and sym.parent_id else None
        while cur is not None:
            if cur.kind in ("class", "interface"):
                return cur
            cur = self.by_id.get(cur.parent_id) if cur.parent_id else None
        return None

    def lookup_method(self, class_id: str, name: str, include_self: bool = True) -> list[Symbol]:
        """Métodos `name` en la clase o en sus bases conocidas (el nivel más cercano)."""
        level = [class_id] if include_self else list(self.bases.get(class_id, []))
        seen: set[str] = set()
        while level:
            found: list[Symbol] = []
            nxt: list[str] = []
            for cid in level:
                if cid in seen:
                    continue
                seen.add(cid)
                found.extend(self.members.get(cid, {}).get(name, []))
                nxt.extend(self.bases.get(cid, []))
            if found:
                return sorted(found, key=_sort_key)
            level = nxt
        return []

    def _has_unknown_ancestry(self, class_id: str) -> bool:
        stack, seen = [class_id], set()
        while stack:
            cid = stack.pop()
            if cid in seen:
                continue
            seen.add(cid)
            if cid in self.unknown_bases:
                return True
            stack.extend(self.bases.get(cid, []))
        return False

    def _field_type(self, class_id: str, field_name: str) -> str | None:
        stack, seen = [class_id], set()
        while stack:
            cid = stack.pop(0)
            if cid in seen:
                continue
            seen.add(cid)
            typ = self.field_types.get(cid, {}).get(field_name)
            if typ:
                return typ
            stack.extend(self.bases.get(cid, []))
        return None

    def _imported_names(self, file: str) -> dict[str, Import]:
        out: dict[str, Import] = {}
        for imp in self.imports_by_file.get(file, []):
            local = imp.alias or imp.name
            if local in (None, "*", "default"):
                local = imp.alias or imp.module_text.replace("\\", "/").rsplit("/", 1)[-1]
                local = local.split(".")[0] if imp.name is None else local
            if local:
                out.setdefault(local, imp)
        return out

    def is_project_module(self, file: str, imp: Import) -> bool:
        key = (file, imp.module_text)
        cached = self._project_module_cache.get(key)
        if cached is not None:
            return cached
        result = self._compute_project_module(file, imp)
        self._project_module_cache[key] = result
        return result

    def _compute_project_module(self, file: str, imp: Import) -> bool:
        lang = self.lang_of.get(file, "")
        mod = imp.module_text
        if lang in ("javascript", "typescript"):
            if not mod.startswith("."):
                return False
            base = posixpath.normpath(posixpath.join(posixpath.dirname(file), mod))
            return (
                any(base + ext in self.files for ext in _JS_EXTS)
                or posixpath.splitext(base)[0] in self._stems
            )
        if lang == "python":
            dotted = mod.lstrip(".")
            if not dotted:
                return True
            rel = dotted.replace(".", "/")
            # `rel` coincide con una carpeta/archivo completo del final de la ruta.
            if rel in self._stem_suffixes or rel + "/__init__" in self._stem_suffixes:
                return True
            if imp.name:
                return self._is_project_module_name(rel + "/" + imp.name)
            return False
        if lang in ("php", "java"):
            last = mod.replace("\\", ".").rstrip(".").rsplit(".", 1)[-1]
            if last in self.classes_by_name:
                return True
            stem = posixpath.splitext(posixpath.basename(mod.strip("'\"")))[0]
            return stem in self._base_stems
        if lang in ("c", "cpp"):
            if mod.startswith("<"):
                return False
            return posixpath.basename(mod) in self._basenames
        return False

    def _is_project_module_name(self, rel: str) -> bool:
        return rel in self._stem_suffixes

    def _included_stems(self, file: str) -> set[str]:
        stems = set()
        for imp in self.imports_by_file.get(file, []):
            if not imp.module_text.startswith("<"):
                stems.add(posixpath.splitext(posixpath.basename(imp.module_text))[0])
        return stems

    # ------------------------------------------------------------------ resultados

    @staticmethod
    def _pick(cands: list[Symbol], confidence: str) -> _Res:
        cands = sorted(cands, key=_sort_key)
        if not cands:
            return _EXTERNAL
        if len(cands) == 1:
            return _Res(cands[0].id, (), confidence)
        return _Res(None, tuple(c.id for c in cands), "ambigua")

    def _expand_interface(self, res: _Res) -> _Res:
        """Método abstracto o de interfaz → implementaciones conocidas (posible implementación)."""
        if res.resolved is None:
            return res
        target = self.by_id[res.resolved]
        owner = self.by_id.get(target.parent_id) if target.parent_id else None
        if target.id not in self.abstract and (owner is None or owner.kind != "interface"):
            return res
        if owner is None:
            return res
        impls: list[Symbol] = []
        for sub in self.subclasses.get(owner.id, []):
            impls.extend(
                m
                for m in self.members.get(sub, {}).get(target.name, [])
                if m.id not in self.abstract
            )
        impls = sorted(impls, key=_sort_key)
        if not impls:
            return res
        if len(impls) == 1:
            return _Res(impls[0].id, (impls[0].id,), "probable")
        return _Res(target.id, tuple(m.id for m in impls), "probable")

    def _constructor(self, classes: list[Symbol], confidence: str) -> _Res:
        if not classes:
            return _EXTERNAL
        if len(classes) > 1:
            return _Res(None, tuple(c.id for c in sorted(classes, key=_sort_key)), "ambigua")
        cls = classes[0]
        lang = cls.lang
        reg = langs.get(lang)
        names = set(reg[0].constructor_names) if reg else set()
        names.add(cls.name)
        for name in sorted(names):
            ctors = self.members.get(cls.id, {}).get(name, [])
            if ctors:
                ctor = sorted(ctors, key=_sort_key)[0]
                return _Res(ctor.id, (), confidence)
        return _Res(cls.id, (), confidence)

    # ------------------------------------------------------------------ resolución

    def resolve_call(self, call: Call) -> _Res:
        caller = self.by_id.get(call.caller_id)
        if caller is None:
            return _EXTERNAL
        file = caller.file
        lang = caller.lang
        reg = langs.get(lang)
        if reg is None:
            return _EXTERNAL
        spec = reg[0]
        name = call.callee_text
        recv = call.receiver_text
        cls = self.enclosing_class(caller)

        if call.id in self.new_calls:
            return self._constructor(
                self._narrow(self.classes_by_name.get(name, []), file), "exacta"
            )

        if recv is None:
            if name in ("super",) and cls is not None:
                for base in self.bases.get(cls.id, []):
                    return self._constructor([self.by_id[base]], "exacta")
                return _EXTERNAL
            if spec.implicit_this and cls is not None:
                found = self.lookup_method(cls.id, name)
                if found:
                    return self._expand_interface(self._pick(found, "exacta"))
            local = self.funcs_by_file.get(file, {}).get(name, [])
            if local:
                return self._pick(local, "exacta")
            classes = self._narrow(self.classes_by_name.get(name, []), file)
            if classes and lang not in ("c",):
                return self._constructor(classes, "exacta")
            imported = self._imported_names(file).get(name)
            if imported is not None and self.is_project_module(file, imported):
                cands = self._narrow(self.funcs_by_name.get(imported.name or name, []), file)
                if len(cands) == 1:
                    return self._pick(cands, "exacta")
            if lang in ("c", "cpp"):
                stems = self._included_stems(file)
                paired = [
                    f
                    for f in self.funcs_by_name.get(name, [])
                    if posixpath.splitext(posixpath.basename(f.file))[0] in stems
                ]
                if len(paired) == 1:
                    return self._pick(paired, "exacta")
            if call.io_kind is not None:
                return _EXTERNAL
            return self._pick(self.funcs_by_name.get(name, []), "probable")

        r = recv.strip()
        if r in spec.self_names:
            if cls is None:
                return _EXTERNAL
            found = self.lookup_method(cls.id, name)
            if found:
                return self._expand_interface(self._pick(found, "exacta"))
            return _EXTERNAL
        if r in spec.parent_names or r == "super()":
            if cls is None:
                return _EXTERNAL
            found = self.lookup_method(cls.id, name, include_self=False)
            return self._pick(found, "exacta") if found else _EXTERNAL

        if call.io_kind is not None:
            return _EXTERNAL
        if r in GLOBAL_RECEIVERS.get(lang, frozenset()):
            return _EXTERNAL
        imported = self._imported_names(file).get(r.lstrip("$"))
        if imported is not None and not self.is_project_module(file, imported):
            return _EXTERNAL

        # Llamada estática: Clase::metodo / Clase.metodo
        simple = r.lstrip("\\").replace("\\", "::").rsplit("::", 1)[-1]
        local_vars = self.var_types.get(caller.id, {})
        if simple.isidentifier() and simple not in local_vars:
            classes = self._narrow(self.classes_by_name.get(simple, []), file)
            if classes:
                found: list[Symbol] = []
                for c in classes:
                    found.extend(self.lookup_method(c.id, name))
                if found:
                    return self._expand_interface(self._pick(found, "exacta"))
                return _EXTERNAL

        typ = self._receiver_type(r, caller, cls, spec)
        if typ is not None:
            classes = self._narrow(self.classes_by_name.get(typ, []), file)
            if not classes:
                return _EXTERNAL
            found = []
            for c in classes:
                found.extend(self.lookup_method(c.id, name))
            if not found:
                return _EXTERNAL
            return self._expand_interface(self._pick(found, "probable"))

        return self._pick(self.methods_by_name.get(name, []), "probable")

    def _receiver_type(self, r: str, caller: Symbol, cls: Symbol | None, spec) -> str | None:
        for self_name in spec.self_names:
            for sep in (".", "->"):
                prefix = self_name + sep
                if r.startswith(prefix):
                    field_name = r[len(prefix) :]
                    if cls is not None and field_name.isidentifier():
                        return self._field_type(cls.id, field_name)
                    return None
        if r.startswith("@") and cls is not None and r[1:].isidentifier():  # Ruby: @campo
            return self._field_type(cls.id, r[1:])
        name = r.lstrip("$")
        if name.isidentifier():
            typ = self.var_types.get(caller.id, {}).get(name)
            if typ:
                return typ
            if spec.implicit_this and cls is not None:
                return self._field_type(cls.id, name)
            return None
        # `var.campo` / `$var->campo`: tipo de la variable → tipo del campo en esa clase.
        for sep in (".", "->"):
            base, dot, field_name = name.partition(sep)
            if dot and base.isidentifier() and field_name.isidentifier():
                base_type = self.var_types.get(caller.id, {}).get(base)
                if base_type is None and spec.implicit_this and cls is not None:
                    base_type = self._field_type(cls.id, base)
                if base_type is None:
                    return None
                owners = self._narrow(self.classes_by_name.get(base_type, []), caller.file)
                if len(owners) == 1:
                    return self._field_type(owners[0].id, field_name)
                return None
        return None

    # ------------------------------------------------------------------ todo junto

    def run(self) -> tuple[list[Symbol], list[Call]]:
        calls: list[Call] = []
        for r in self.results:
            for call in r.calls:
                res = self.resolve_call(call)
                calls.append(
                    replace(
                        call,
                        resolved_id=res.resolved,
                        candidates=res.candidates,
                        confidence=res.confidence,
                    )
                )
        calls.sort(key=lambda c: (self.by_id[c.caller_id].file, c.line, c.col, c.callee_text))
        return self.symbols, calls


def resolve(results: list[FileResult]) -> tuple[list[Symbol], list[Call]]:
    return Resolver(results).run()
