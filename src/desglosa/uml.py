"""Diagrama de clases UML (Bloque 4).

- Cada clase o interfaz con sus **atributos** y **métodos**: visibilidad (`+ - # ~`), tipo,
  parámetros y tipo de retorno; lo estático va subrayado y lo abstracto en cursiva.
- Relaciones: **herencia** (triángulo hueco, línea sólida), **implementación** (triángulo
  hueco, línea punteada) y **asociación** (flecha abierta con el nombre del atributo
  cuyo tipo es otra clase del proyecto).
- Un diagrama por carpeta (un "paquete" UML): sus clases y, en gris, las clases de otras
  carpetas con las que se relacionan. Así un proyecto grande no queda en un solo dibujo
  ilegible.

Los atributos, la visibilidad y los tipos los extraen los ganchos de
`desglosa/langs/members.py`. Una base cuyo nombre no es una clase única del proyecto
(una librería, o un nombre repetido) no se dibuja: no se adivina.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field

from desglosa.ir import MethodInfo
from desglosa.langs.spec import normalize_type
from desglosa.layout.layered import LEdge, LNode, layout_directed
from desglosa.layout.text import CHAR_W, LINE_H

MAX_CLASSES = 60  # por diagrama; más clases en una carpeta → las más relacionadas
MAX_ATTRS = 12
MAX_METHODS = 16
LAYER_GAP = 70.0
HEAD_H = 34.0  # alto del encabezado (estereotipo + nombre)
PAD = 8.0
RECEIVERS = {"self", "&self", "&mut self", "mut self", "cls", "this"}
_COLLECTION = re.compile(r"\[\]|\b(list|array|vec|set|collection|iterable|sequence|map|dict)\b",
                         re.I)


@dataclass
class UMethod:
    visibility: str | None
    name: str
    params: str
    returns: str | None
    static: bool
    abstract: bool
    line: int


@dataclass
class UClass:
    id: str
    name: str
    kind: str  # class | interface
    abstract: bool
    file: str
    line: int
    attributes: list = field(default_factory=list)  # Member
    methods: list[UMethod] = field(default_factory=list)

    @property
    def folder(self) -> str:
        return posixpath.dirname(self.file)


@dataclass(frozen=True)
class URel:
    src: str  # la subclase, la que implementa o la dueña del atributo
    dst: str  # la base, la interfaz o el tipo del atributo
    kind: str  # hereda | implementa | asociacion
    label: str | None = None


def _params(signature: str, lang: str) -> str:
    """`public double area(int x)` → `int x`; quita `self`, `this` y el receptor de Go."""
    text = signature
    if lang == "go" and text.startswith("func ("):
        close = text.find(")")
        text = text[close + 1:]
    start = text.find("(")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                inner = text[start + 1:i]
                break
    else:
        inner = text[start + 1:]
    parts = [p.strip() for p in _split_top(inner)]
    parts = [p for p in parts if p and p not in RECEIVERS and not p.startswith(("self:", "self,"))]
    return ", ".join(_uml_param(p, lang) for p in parts)


TYPE_FIRST = {"java", "csharp", "c", "cpp", "php", "go"}  # lenguajes que no usan `nombre: Tipo`
_PARAM_MODS = {"final", "const", "ref", "out", "in", "params", "this", "readonly", "scoped",
               "public", "private", "protected"}  # PHP 8: `private Repo $r` en el constructor
_ANNOTATION = re.compile(r"@[\w.]+(\([^)]*\))?\s*|\[[^\]]*\]\s*")


def _uml_param(param: str, lang: str) -> str:
    """Un parámetro en notación UML: `String nombre` → `nombre: String`, `$x` → `x`.

    Solo cambia los lenguajes que escriben el tipo delante; el resto ya usa `nombre: Tipo`
    o no tiene tipos. Si el parámetro no tiene la forma esperada se deja como está.
    """
    if lang not in TYPE_FIRST:
        return param
    head, eq, default = param.partition("=")
    head = head.strip()
    if lang == "csharp" or lang == "java":
        head = _ANNOTATION.sub("", head)
    tokens = [t for t in head.split() if t not in _PARAM_MODS]
    if not tokens or any(ch in head for ch in "{("):
        return param
    if len(tokens) == 1:
        name, typ = tokens[0], ""
    elif lang == "go":
        name, typ = tokens[0], " ".join(tokens[1:])
    else:
        name, typ = tokens[-1], " ".join(tokens[:-1])
        while name[:1] in "*&":  # C/C++: `int *p` → p: int*
            typ, name = typ + name[0], name[1:]
    name = name.lstrip("$")
    if not name:
        return param
    out = f"{name}: {typ}" if typ else name
    return out + (f" = {default.strip()}" if eq else "")


def _split_top(text: str) -> list[str]:
    """Separa por comas que no están dentro de <>, (), [] ni {}."""
    out, cur, depth = [], [], 0
    for ch in text:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return out


def build_class_model(analysis) -> tuple[dict[str, UClass], list[URel]]:
    """Clases con sus miembros y las relaciones entre ellas."""
    project = analysis.project
    members, infos, abstract, declared = {}, {}, set(), {}
    bases: dict[str, list[str]] = defaultdict(list)
    for r in analysis.results:
        members.update(r.members)
        infos.update(r.method_info)
        abstract.update(r.abstract_classes)
        declared.update(r.declared)
        for cid, names in r.class_bases.items():
            bases[cid].extend(names)
    lang_of = {f.path: f.lang for f in project.files}
    classes: dict[str, UClass] = {}
    for s in project.symbols:
        if s.kind in ("class", "interface"):
            classes[s.id] = UClass(s.id, s.name, s.kind, s.id in abstract, s.file, s.line_start,
                                   list(members.get(s.id, [])))
    by_name: dict[str, list[UClass]] = defaultdict(list)
    for c in classes.values():
        by_name[c.name].append(c)
    # `impl Trait for Tipo` (Rust) declara la herencia fuera de la clase.
    for r in analysis.results:
        for type_name, base in r.extra_bases:
            for c in by_name.get(type_name, []):
                if c.file == r.file.path and base not in bases[c.id]:
                    bases[c.id].append(base)
    for s in sorted(project.symbols, key=lambda s: (s.file, s.line_start, s.id)):
        owner = classes.get(s.parent_id or "")
        if s.kind != "method" or owner is None:
            continue
        info = infos.get(s.id) or MethodInfo(None, False, False, None)
        owner.methods.append(UMethod(
            info.visibility, s.name.lstrip("#"), _params(s.signature, s.lang), info.returns,
            info.static, info.abstract or owner.kind == "interface", s.line_start,
        ))
    for cid, decls in declared.items():
        owner = classes.get(cid)
        if owner is None:
            continue
        have = {m.name for m in owner.methods}
        for d in decls:
            if d.name not in have:
                i = d.info
                owner.methods.append(UMethod(i.visibility, d.name,
                                             _params(d.params, lang_of.get(owner.file, "")),
                                             i.returns, i.static, i.abstract, d.line))
    for c in classes.values():
        c.methods.sort(key=lambda m: m.line)

    def resolve(name: str, near: UClass) -> UClass | None:
        """Una clase del proyecto con ese nombre: la de la misma carpeta o la única."""
        cands = by_name.get(normalize_type(name) or name, [])
        same = [c for c in cands if c.folder == near.folder and c.id != near.id]
        if len(same) == 1:
            return same[0]
        others = [c for c in cands if c.id != near.id]
        return others[0] if len(others) == 1 else None

    rels: set[URel] = set()
    for cid, names in bases.items():
        child = classes.get(cid)
        if child is None:
            continue
        for name in names:
            base = resolve(name, child)
            if base is not None:
                kind = "implementa" if base.kind == "interface" and child.kind != "interface" else (
                    "hereda"
                )
                rels.add(URel(child.id, base.id, kind))
    assoc: dict[tuple[str, str], list[str]] = defaultdict(list)
    for c in sorted(classes.values(), key=lambda c: c.id):
        for m in c.attributes:
            if not m.type:
                continue
            for word in re.findall(r"[A-Za-z_]\w*", m.type):
                target = resolve(word, c) if word[:1].isupper() else None
                if target is not None:
                    many = bool(_COLLECTION.search(m.type))
                    assoc[(c.id, target.id)].append(f"{m.name}{' *' if many else ''}")
                    break
    # Varios atributos hacia la misma clase van en una sola flecha: "origen, destino".
    for (src, dst), labels in assoc.items():
        rels.add(URel(src, dst, "asociacion", ", ".join(labels)))
    return classes, sorted(rels, key=lambda r: (r.src, r.dst, r.kind, r.label or ""))


# --------------------------------------------------------------------------- textos


def attr_text(m) -> str:
    vis = m.visibility or " "
    return f"{vis} {m.name}" + (f": {m.type}" if m.type else "")


PARAMS_MAX = 48  # caracteres de parámetros que caben en la caja


def method_text(m: UMethod) -> str:
    vis = m.visibility or " "
    params = m.params if len(m.params) <= PARAMS_MAX else m.params[:PARAMS_MAX - 1] + "…"
    return f"{vis} {m.name}({params})" + (f": {m.returns}" if m.returns else "")


def _class_lines(c: UClass) -> tuple[list, list]:
    attrs = [[attr_text(m), "s" if m.static else ""] for m in c.attributes[:MAX_ATTRS]]
    if len(c.attributes) > MAX_ATTRS:
        attrs.append([f"… y {len(c.attributes) - MAX_ATTRS} atributos más", ""])
    methods = [
        [method_text(m), ("s" if m.static else "") + ("a" if m.abstract else "")]
        for m in c.methods[:MAX_METHODS]
    ]
    if len(c.methods) > MAX_METHODS:
        methods.append([f"… y {len(c.methods) - MAX_METHODS} métodos más", ""])
    return attrs, methods


def stereotype(c: UClass) -> str | None:
    if c.kind == "interface":
        return "«interfaz»"
    if c.abstract:
        return "«abstracta»"
    return None


# --------------------------------------------------------------------------- diagramas


def _box_size(c: UClass, ghost: bool) -> tuple[float, float, list, list]:
    if ghost:
        return max(110.0, len(c.name) * CHAR_W + 28), 40.0, [], []
    attrs, methods = _class_lines(c)
    texts = [c.name, stereotype(c) or ""] + [a[0] for a in attrs] + [m[0] for m in methods]
    w = max(140.0, max(len(t) for t in texts) * CHAR_W + 2 * PAD + 6)
    h = HEAD_H + (max(1, len(attrs)) + max(1, len(methods))) * LINE_H + 2 * PAD + 6
    return float(int(w + 1) // 2 * 2), float(int(h + 1) // 2 * 2), attrs, methods


def build_diagram(classes: dict[str, UClass], rels: list[URel], folder: str,
                  links: dict[str, str] | None = None) -> dict | None:
    """El diagrama de una carpeta: sus clases y, como fantasmas, las de otras carpetas."""
    own = [c for c in classes.values() if c.folder == folder]
    if not own:
        return None
    own_ids = {c.id for c in own}
    degree: dict[str, int] = defaultdict(int)
    for r in rels:
        degree[r.src] += 1
        degree[r.dst] += 1
    hidden = 0
    if len(own) > MAX_CLASSES:
        keep = sorted(own, key=lambda c: (-degree[c.id], c.name, c.id))[:MAX_CLASSES]
        hidden = len(own) - MAX_CLASSES
        own_ids = {c.id for c in keep}
        own = keep
    shown = [r for r in rels if r.src in own_ids or r.dst in own_ids]
    ghosts = sorted({x for r in shown for x in (r.src, r.dst) if x not in own_ids})
    ids = sorted(own_ids, key=lambda i: (classes[i].file, classes[i].line, i)) + ghosts
    sizes = {i: _box_size(classes[i], i not in own_ids) for i in ids}
    lnodes = [LNode(i, sizes[i][0], sizes[i][1], f"{n:05d}") for n, i in enumerate(ids)]
    # La base va arriba: la arista de la capa sale de la base hacia la subclase.
    ledges = []
    for r in shown:
        if r.kind == "asociacion":
            ledges.append(LEdge(r.src, r.dst, r.label))
        else:
            ledges.append(LEdge(r.dst, r.src))
    lay = layout_directed(lnodes, ledges, True, LAYER_GAP)
    out_classes = []
    for i in ids:
        c, p = classes[i], lay.nodes[i]
        w, h, attrs, methods = sizes[i]
        ghost = i not in own_ids
        link = (links or {}).get(i)
        out_classes.append([i, c.kind, p.x, p.y, w, h, stereotype(c), c.name, attrs, methods,
                            ghost, c.folder if ghost else None, link, c.abstract,
                            f"{c.file}:{c.line}"])
    placed = {(e.src, e.dst): e for e in lay.edges}
    out_edges = []
    for r in shown:
        key = (r.src, r.dst) if r.kind == "asociacion" else (r.dst, r.src)
        e = placed.get(key)
        if e is None:
            continue
        pts = list(e.points)
        if r.kind != "asociacion":
            pts.reverse()  # la flecha termina en la base (triángulo hueco)
        flat = [round(v, 1) for xy in pts for v in xy]
        box = list(e.label_box) if e.label_box else [0, 0, 0, 0]
        out_edges.append([r.src, r.dst, flat, r.kind, r.label, *box])
    return {
        "folder": folder,
        "w": lay.width,
        "h": lay.height,
        "classes": out_classes,
        "edges": out_edges,
        "hidden": hidden,
        "mermaid": to_mermaid(classes, shown, ids, folder or "(raíz)", own_ids),
    }


# --------------------------------------------------------------------------- Mermaid

_MM_ID = re.compile(r"[^A-Za-z0-9_]")


def _mm_type(text: str | None) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", "", text)
    if "," in t:  # Mermaid no admite genéricos con coma: se deja solo el tipo base
        t = re.sub(r"<.*>", "", t)
    t = t.replace("<", "~").replace(">", "~")
    return re.sub(r"[^\w~\[\].?*&:]", "", t)


def _param_name(param: str) -> str:
    """Solo el nombre de un parámetro: `String nombre`, `nombre: str`, `$x = 3` → nombre."""
    p = param.split("=")[0].strip()
    p = p.split(":")[0].strip() if ":" in p else (p.split()[-1] if p.split() else p)
    return _MM_ID.sub("_", p.lstrip("$&*")) or "arg"


def to_mermaid(classes: dict[str, UClass], rels: list[URel], ids: list[str], title: str,
               own: set[str] | None = None) -> str:
    """classDiagram de Mermaid. Las clases fuera de `own` (de otra carpeta) van sin miembros."""
    alias: dict[str, str] = {}
    used: set[str] = set()
    for i in ids:
        base = _MM_ID.sub("_", classes[i].name) or "Clase"
        name, n = base, 2
        while name in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name)
        alias[i] = name
    out = ["---", f'title: "Clases de {title}"', "---", "classDiagram"]
    for i in ids:
        c = classes[i]
        if own is not None and i not in own:
            out.append(f"    class {alias[i]}")
            if c.kind == "interface":
                out.append(f"    <<interface>> {alias[i]}")
            continue
        out.append(f"    class {alias[i]} {{")
        if c.kind == "interface":
            out.append("        <<interface>>")
        elif c.abstract:
            out.append("        <<abstract>>")
        for m in c.attributes[:MAX_ATTRS]:
            typ = _mm_type(m.type)
            out.append(f"        {m.visibility or ''}{typ + ' ' if typ else ''}"
                       f"{_MM_ID.sub('_', m.name)}{'$' if m.static else ''}")
        for m in c.methods[:MAX_METHODS]:
            params = ", ".join(_param_name(p) for p in _split_top(m.params) if p.strip())
            ret = _mm_type(m.returns)
            flags = ("*" if m.abstract else "") + ("$" if m.static else "")
            out.append(f"        {m.visibility or ''}{_MM_ID.sub('_', m.name)}({params})"
                       f"{flags}{' ' + ret if ret else ''}")
        out.append("    }")
    arrow = {"hereda": "<|--", "implementa": "<|..", "asociacion": "-->"}
    for r in rels:
        if r.kind == "asociacion":
            label = re.sub(r"[^\w, *]", "_", r.label or "").strip() or "usa"
            out.append(f"    {alias[r.src]} --> {alias[r.dst]} : {label}")
        else:
            out.append(f"    {alias[r.dst]} {arrow[r.kind]} {alias[r.src]}")
    return "\n".join(out) + "\n"


def build_uml(analysis, links: dict[str, str] | None = None) -> tuple[dict, dict[str, dict]]:
    """(índice: carpeta → nº de clases, diagramas por carpeta). Vacío si no hay clases."""
    classes, rels = build_class_model(analysis)
    if not classes:
        return {}, {}
    folders: dict[str, int] = defaultdict(int)
    for c in classes.values():
        folders[c.folder] += 1
    diagrams = {}
    for folder in sorted(folders):
        d = build_diagram(classes, rels, folder, links)
        if d is not None:
            diagrams[folder] = d
    index = {f: {"clases": n, "relaciones": sum(
        1 for r in rels if classes[r.src].folder == f or classes[r.dst].folder == f)}
        for f, n in sorted(folders.items())}
    return index, diagrams
