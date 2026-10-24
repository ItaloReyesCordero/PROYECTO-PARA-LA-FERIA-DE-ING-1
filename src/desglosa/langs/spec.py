"""Descripción declarativa de un lenguaje (LangSpec) y su comportamiento (LangHooks).

`LangSpec` contiene solo datos: qué tipos de nodo del AST son funciones, ifs, bucles...
`LangHooks` contiene la lógica que no se puede expresar con tablas (dónde está el
nombre de una función en C, cómo se escribe un receptor en PHP, etc.). La clase base
implementa un comportamiento genérico; cada lenguaje sobrescribe solo lo necesario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

from tree_sitter import Node


@dataclass(frozen=True)
class LangSpec:
    name: str
    grammar: str
    module_nodes: tuple[str, ...] = ()
    class_nodes: tuple[str, ...] = ()
    interface_nodes: tuple[str, ...] = ()
    function_nodes: tuple[str, ...] = ()
    method_nodes: tuple[str, ...] = ()
    name_field: str = "name"
    import_nodes: tuple[str, ...] = ()
    call_nodes: tuple[str, ...] = ()
    if_nodes: tuple[str, ...] = ()
    else_nodes: tuple[str, ...] = ()
    elif_nodes: tuple[str, ...] = ()
    loop_nodes: tuple[str, ...] = ()
    do_while_nodes: tuple[str, ...] = ()
    switch_nodes: tuple[str, ...] = ()
    case_nodes: tuple[str, ...] = ()
    try_nodes: tuple[str, ...] = ()
    catch_nodes: tuple[str, ...] = ()
    finally_nodes: tuple[str, ...] = ()
    return_nodes: tuple[str, ...] = ()
    break_nodes: tuple[str, ...] = ()
    continue_nodes: tuple[str, ...] = ()
    throw_nodes: tuple[str, ...] = ()
    block_nodes: tuple[str, ...] = ()
    comment_nodes: tuple[str, ...] = ()
    self_names: tuple[str, ...] = ()
    expression_oriented: bool = False
    # Extensiones (documentadas en docs/ADDING_A_LANGUAGE.md):
    parent_names: tuple[str, ...] = ()  # "super", "parent"
    implicit_this: bool = False  # Java/C++: `metodo()` dentro de una clase llama a this.metodo()
    constructor_names: tuple[str, ...] = ()  # "__init__", "constructor", "__construct"
    goto_nodes: tuple[str, ...] = ()
    label_nodes: tuple[str, ...] = ()


class Src:
    """Bytes de un archivo + su codificación, para sacar texto de los nodos."""

    __slots__ = ("data", "encoding")

    def __init__(self, data: bytes, encoding: str) -> None:
        self.data = data
        self.encoding = encoding

    def text(self, node: Node | None) -> str:
        if node is None:
            return ""
        return self.data[node.start_byte : node.end_byte].decode(self.encoding, errors="replace")

    def between(self, start: int, end: int) -> str:
        return self.data[start:end].decode(self.encoding, errors="replace")


class CallParts(NamedTuple):
    callee: str
    receiver: str | None
    is_new: bool = False
    args: tuple[str, ...] = ()


class ImportParts(NamedTuple):
    module: str
    name: str | None
    alias: str | None


class Binding(NamedTuple):
    """Asociación nombre → tipo, para deducir el tipo de un receptor.

    scope: "local" (variable o parámetro de la función actual) o "field" (atributo de la clase).
    """

    name: str
    type: str
    scope: str


_WS = re.compile(r"\s+")


def one_line(text: str, limit: int = 80) -> str:
    """Colapsa espacios y recorta con "…"."""
    text = _WS.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


_GENERIC = re.compile(r"<[^<>]*>")
_TYPE_NOISE = re.compile(r"\b(const|volatile|final|readonly|mut|struct|class|enum|unsigned)\b")


def normalize_type(text: str) -> str:
    """'const std::vector<Item>&' → 'vector'; '?\\App\\Pago' → 'Pago'; 'Pago[]' → 'Pago'."""
    t = text.strip()
    for _ in range(4):
        t2 = _GENERIC.sub("", t)
        if t2 == t:
            break
        t = t2
    t = _TYPE_NOISE.sub(" ", t)
    t = t.replace("&", " ").replace("*", " ").replace("?", " ").replace("[]", " ")
    t = t.replace("[", " ").replace("]", " ")
    t = t.strip()
    if not t:
        return ""
    t = t.split()[-1] if " " in t else t
    for sep in ("::", "\\", "."):
        if sep in t:
            t = t.rsplit(sep, 1)[-1]
    return t.strip()


def strip_parens(text: str) -> str:
    """'(a && (b))' → 'a && (b)'; deja igual '(a) && (b)'."""
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        inner = text[1:-1]
        depth = 0
        for ch in inner:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return text
        if depth != 0:
            return text
        text = inner.strip()
    return text


def strip_comment_markers(text: str) -> str:
    """Quita /** */, //, #, * iniciales de un comentario de documentación."""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        for prefix in ("/**", "/*!", "/*", "///", "//!", "//", "#"):
            if line.startswith(prefix):
                line = line[len(prefix) :]
                break
        if line.endswith("*/"):
            line = line[:-2]
        line = line.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        lines.append(line)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


class LangHooks:
    """Comportamiento genérico (sirve para la mayoría de lenguajes tipo C)."""

    spec: LangSpec

    # Envolturas que pueden preceder a una declaración (para buscar su comentario).
    wrapper_nodes: tuple[str, ...] = (
        "export_statement",
        "decorated_definition",
        "template_declaration",
    )

    def __init__(self, spec: LangSpec) -> None:
        self.spec = spec

    # ---------------------------------------------------------------- símbolos

    def symbol_name(self, node: Node, src: Src) -> str | None:
        name = node.child_by_field_name(self.spec.name_field)
        if name is not None:
            return src.text(name)
        return None

    def symbol_qualifier(self, node: Node, src: Src) -> str | None:
        """Clase dueña de un método definido fuera de ella (C++ `A::m`)."""
        return None

    def is_definition(self, node: Node) -> bool:
        """False para nodos que son solo referencias (p. ej. `struct X *p` en C)."""
        return True

    def function_body(self, node: Node) -> Node | None:
        return node.child_by_field_name("body")

    def has_body(self, node: Node) -> bool:
        return self.function_body(node) is not None

    def is_static(self, node: Node, src: Src) -> bool:
        return False

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        return ()

    def signature(self, node: Node, src: Src) -> str:
        body = self.function_body(node)
        if body is None:
            body = node.child_by_field_name("body")
        end = body.start_byte if body is not None else node.end_byte
        header = src.between(node.start_byte, end)
        header = re.sub(r"^\s*(@[\w.]+(\([^)]*\))?\s*)+", "", header)
        return one_line(header.rstrip(" {:\n\t"), 120)

    def doc(self, node: Node, src: Src) -> str | None:
        target = node
        while target.parent is not None and target.parent.type in self.wrapper_nodes:
            target = target.parent
        comments: list[Node] = []
        expected_line = target.start_point[0]
        prev = target.prev_named_sibling
        while prev is not None and prev.type in self.spec.comment_nodes:
            if prev.end_point[0] < expected_line - 1:
                break
            comments.append(prev)
            expected_line = prev.start_point[0]
            prev = prev.prev_named_sibling
        if not comments:
            return None
        comments.reverse()
        text = "\n".join(strip_comment_markers(src.text(c)) for c in comments)
        return text.strip() or None

    def is_main_guard(self, node: Node, src: Src) -> bool:
        return False

    # ---------------------------------------------------------------- llamadas e imports

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        args = self.call_args(node, src)
        if fn.type in ("identifier", "name"):
            return CallParts(src.text(fn), None, False, args)
        obj = fn.child_by_field_name("object") or fn.child_by_field_name("argument")
        prop = (
            fn.child_by_field_name("property")
            or fn.child_by_field_name("field")
            or fn.child_by_field_name("attribute")
        )
        if obj is not None and prop is not None:
            return CallParts(src.text(prop), one_line(src.text(obj), 80), False, args)
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def call_args(self, node: Node, src: Src) -> tuple[str, ...]:
        args = node.child_by_field_name("arguments")
        if args is None:
            return ()
        return tuple(one_line(src.text(a), 60) for a in args.named_children)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        return []

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        return []

    # ---------------------------------------------------------------- textos de control

    def condition_node(self, node: Node) -> Node | None:
        return node.child_by_field_name("condition")

    def condition(self, node: Node, src: Src) -> str:
        cond = self.condition_node(node)
        if cond is None:
            return ""
        return one_line(strip_parens(src.text(cond)), 200)

    def loop_label(self, node: Node, src: Src) -> str:
        body = node.child_by_field_name("body")
        end = body.start_byte if body is not None else node.end_byte
        return one_line(src.between(node.start_byte, end).rstrip(" {:"), 120)

    def case_value(self, node: Node, src: Src) -> str | None:
        """Texto del valor de un `case`, o None si es el caso por defecto."""
        value = node.child_by_field_name("value")
        if value is None:
            return None
        return one_line(src.text(value), 60)

    def catch_label(self, node: Node, src: Src) -> str:
        param = node.child_by_field_name("parameter") or node.child_by_field_name("parameters")
        if param is None:
            return ""
        return one_line(src.text(param).strip("() "), 60)
