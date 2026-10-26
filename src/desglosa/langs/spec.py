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

from desglosa.ir import DeclaredMethod, Member, MethodInfo


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


# --------------------------------------------------------------------------- diagrama de clases

MODIFIER_NODES = frozenset({
    "modifiers", "modifier", "visibility_modifier", "accessibility_modifier",
    "static_modifier", "abstract_modifier", "final_modifier", "readonly_modifier",
    "storage_class_specifier", "property_modifier", "inheritance_modifier",
    "member_modifier", "class_modifier", "function_modifier",
})
# Palabras que algunas gramáticas dejan como nodos sin nombre (TS: `static`, `readonly`).
MODIFIER_WORDS = frozenset({
    "public", "private", "protected", "internal", "static", "abstract", "pub",
    "fileprivate", "open", "readonly", "final", "override", "virtual",
})
_WORD_RE = re.compile(r"[a-z]+(?:\([a-z]+\))?")
_VISIBILITY = (
    ("private", "-"), ("fileprivate", "-"), ("protected", "#"), ("internal", "~"),
    ("pub(crate)", "~"), ("pub(super)", "~"), ("public", "+"), ("pub", "+"), ("open", "+"),
)


def modifier_words(node: Node, src: Src) -> set[str]:
    """Modificadores de una declaración: {"public", "static", "abstract"…}."""
    words: set[str] = set()
    for c in node.children:
        if c.type in MODIFIER_NODES:
            words.update(_WORD_RE.findall(src.text(c)))
        elif not c.is_named and c.type in MODIFIER_WORDS:
            words.add(c.type)
    return words


def visibility_of(words: set[str], default: str | None = None) -> str | None:
    for word, symbol in _VISIBILITY:
        if word in words:
            return symbol
    return default


def type_text(node: Node | None, src: Src) -> str | None:
    """Texto de un tipo para el diagrama: `: string` → `string`; `void` → None."""
    if node is None:
        return None
    text = one_line(src.text(node).strip().lstrip(":").strip(), 40)
    return None if not text or text in ("void", "Unit", "()", "None") else text


def name_visibility(name: str) -> str:
    """Convención por nombre (Python): `__x` privado, `_x` protegido, el resto público."""
    if name.startswith("__") and not name.endswith("__"):
        return "-"
    if name.startswith("_") and not name.startswith("__"):
        return "#"
    return "+"


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

    def class_kind(self, node: Node, src: Src) -> str | None:
        """ "class", "interface" o None si el nodo no define un tipo (alias, referencia)."""
        if not self.is_definition(node):
            return None
        return "interface" if node.type in self.spec.interface_nodes else "class"

    def extra_bases(self, node: Node, src: Src) -> list[tuple[str, str]]:
        """Herencia declarada fuera de la clase: [(tipo, base)] (Rust `impl Trait for Tipo`)."""
        return []

    def function_body(self, node: Node) -> Node | None:
        return node.child_by_field_name("body")

    def parameters_node(self, node: Node) -> Node | None:
        params = node.child_by_field_name("parameters")
        decl = node.child_by_field_name("declarator")
        while params is None and decl is not None:
            params = decl.child_by_field_name("parameters")
            decl = decl.child_by_field_name("declarator")
        return params

    def parameter_list(self, node: Node, src: Src) -> tuple[list[Node], str] | None:
        """(nodos de los parámetros, texto técnico) para el terminal "Inicio"."""
        params = self.parameters_node(node)
        if params is None:
            return None
        return list(params.named_children), src.text(params)

    def has_body(self, node: Node) -> bool:
        return self.function_body(node) is not None

    def is_static(self, node: Node, src: Src) -> bool:
        return False

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        return ()

    # ---------------------------------------------------------------- diagrama de clases
    # Visibilidad cuando no se escribe ninguna (Java: paquete; C#: privado; Python: pública).
    default_visibility: str | None = "+"

    def class_members(self, node: Node, src: Src) -> list[Member]:
        """Atributos declarados en el cuerpo de la clase."""
        return []

    def assigned_members(self, node: Node, src: Src) -> list[Member]:
        """Atributos creados dentro de un método (`self.x = …`, `this.x = …`, `@x = …`)."""
        return []

    def declared_methods(self, node: Node, src: Src) -> list[DeclaredMethod]:
        """Métodos declarados sin cuerpo que no son símbolos (C++ `virtual f() = 0;`)."""
        return []

    def class_is_abstract(self, node: Node, src: Src) -> bool:
        return node.type.startswith("abstract") or "abstract" in modifier_words(node, src)

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        words = modifier_words(node, src)
        ret = None
        for field_name in ("return_type", "returns", "result", "type"):
            ret = node.child_by_field_name(field_name)
            if ret is not None:
                break
        return MethodInfo(
            visibility_of(words, self.default_visibility),
            "static" in words,
            "abstract" in words,
            type_text(ret, src),
        )

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

    # ---------------------------------------------------------------- forma del AST para el flujo
    # Comportamiento por defecto (lenguajes tipo C, Python, PHP, Java). Go, Ruby, Rust,
    # Kotlin y Swift sobrescriben lo que cambia.

    block_types: tuple[str, ...] = (
        "block",
        "statement_block",
        "compound_statement",
        "constructor_body",
    )

    def is_block(self, node: Node) -> bool:
        return node.type in self.spec.block_nodes or node.type in self.block_types

    def body_statements(self, node: Node | None) -> list[Node]:
        """Sentencias de un cuerpo; si `node` no es un bloque, es una sola sentencia."""
        if node is None:
            return []
        if self.is_block(node):
            out: list[Node] = []
            for c in node.named_children:
                if c.type in self.spec.comment_nodes:
                    continue
                if c.type in ("pass_statement", "empty_statement"):
                    continue
                if self.is_block(c) and c.type in self.flatten_blocks:
                    out.extend(self.body_statements(c))
                else:
                    out.append(c)
            return out
        return [node]

    # Bloques que son solo un contenedor de sentencias (se aplanan al leer un cuerpo).
    flatten_blocks: tuple[str, ...] = ()

    def unwrap(self, st: Node) -> Node:
        """`expression_statement` que envuelve un if/return/throw… → el nodo interno."""
        if st.type == "expression_statement" and st.named_child_count == 1:
            inner = st.named_children[0]
            if self.control_kind(inner) is not None:
                return inner
        return st

    def control_kind(self, node: Node) -> str | None:
        s = self.spec
        t = node.type
        if t in s.if_nodes:
            return "if"
        if t in s.loop_nodes:
            return "loop"
        if t in s.do_while_nodes:
            return "do_while"
        if t in s.switch_nodes:
            return "switch"
        if t in s.try_nodes:
            return "try"
        if t in s.return_nodes:
            return "return"
        if t in s.break_nodes:
            return "break"
        if t in s.continue_nodes:
            return "continue"
        if t in s.throw_nodes:
            return "throw"
        if t in s.goto_nodes:
            return "goto"
        if t in s.label_nodes:
            return "label"
        return None

    def flow_kind(self, st: Node, src: Src) -> str | None:
        """Qué construcción de control es la sentencia, o None si es simple."""
        kind = self.control_kind(self.unwrap(st))
        if kind is not None:
            return kind
        if self.is_block(st):
            return "block"
        if st.type == "with_statement":
            return "with"
        return None

    def if_info(self, node: Node, src: Src) -> IfInfo:
        then = node.child_by_field_name("consequence") or node.child_by_field_name("body")
        alts = [
            c for i, c in enumerate(node.children) if node.field_name_for_child(i) == "alternative"
        ]
        return IfInfo(
            self.condition_node(node), self.condition(node, src), self.body_statements(then), alts
        )

    def alt_info(self, alt: Node, src: Src) -> AltInfo:
        s = self.spec
        if alt.type in s.elif_nodes:
            return AltInfo("elif", alt, self.if_info(alt, src))
        if alt.type in s.else_nodes:
            body = alt.child_by_field_name("body")
            if body is None:
                named = [c for c in alt.named_children if c.type not in s.comment_nodes]
                body = named[0] if named else None
            if body is not None and body.type in s.if_nodes:
                return AltInfo("if", body)
            return AltInfo("else", alt, body=self.body_statements(body))
        if alt.type in s.if_nodes:
            return AltInfo("if", alt)
        return AltInfo("else", alt, body=self.body_statements(alt))

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(node.child_by_field_name("body"))
        if node.type in ("foreach_statement", "enhanced_for_statement", "for_range_loop") or (
            node.child_by_field_name("left") is not None
            and node.child_by_field_name("right") is not None
        ):
            if node.type == "foreach_statement":
                named = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
                coll_node = named[0] if named else None
                var = src.text(named[1]) if len(named) > 2 else ""
            else:
                var_node = (
                    node.child_by_field_name("left")
                    or node.child_by_field_name("name")
                    or node.child_by_field_name("declarator")
                )
                var = src.text(var_node)
                coll_node = node.child_by_field_name("right") or node.child_by_field_name("value")
            return LoopInfo(
                "foreach",
                body,
                var_text=var,
                coll_node=coll_node,
                coll_text=src.text(coll_node),
                header=self.loop_label(node, src),
            )
        init = next(
            (
                node.child_by_field_name(f)
                for f in ("initializer", "init", "initialize")
                if node.child_by_field_name(f) is not None
            ),
            None,
        )
        update = next(
            (
                node.child_by_field_name(f)
                for f in ("update", "increment")
                if node.child_by_field_name(f) is not None
            ),
            None,
        )
        if init is not None or update is not None or node.type == "for_statement":
            cond = node.child_by_field_name("condition")
            return LoopInfo(
                "for",
                body,
                cond_node=cond,
                cond_text=strip_parens(src.text(cond)) if cond is not None else "",
                init=init,
                update=update,
            )
        return LoopInfo(
            "while", body, cond_node=self.condition_node(node), cond_text=self.condition(node, src)
        )

    def do_while_info(self, node: Node, src: Src) -> LoopInfo:
        return LoopInfo(
            "do",
            self.body_statements(node.child_by_field_name("body")),
            cond_node=self.condition_node(node),
            cond_text=self.condition(node, src),
        )

    fallthrough: bool = False  # ¿un case sin break cae al siguiente? (C, JS, Java, PHP)

    def case_statements(self, case: Node) -> list[Node]:
        out: list[Node] = []
        for i, ch in enumerate(case.children):
            if not ch.is_named:
                continue
            fname = case.field_name_for_child(i)
            if fname == "value" or ch.type in ("switch_label", "case_pattern"):
                continue
            if ch.type in self.spec.comment_nodes:
                continue
            if fname == "consequence" and self.is_block(ch):
                out.extend(self.body_statements(ch))
            else:
                out.append(ch)
        return out

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        body = node.child_by_field_name("body")
        header_end = body.start_byte if body is not None else node.end_byte
        tech = one_line(src.between(node.start_byte, header_end).rstrip(" {:"), 80)
        cases = []
        for c in body.named_children if body is not None else []:
            if c.type not in self.spec.case_nodes:
                continue
            falls = self.fallthrough and c.type != "switch_rule"
            cases.append(CaseInfo(self.case_value(c, src), self.case_statements(c), falls))
        return self.condition(node, src), tech, cases

    def catch_body(self, node: Node) -> Node | None:
        body = node.child_by_field_name("body")
        if body is not None:
            return body
        named = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
        return named[-1] if named else None

    def try_info(self, node: Node, src: Src) -> TryInfo:
        s = self.spec
        catches = [c for c in node.named_children if c.type in s.catch_nodes]
        final = next((c for c in node.named_children if c.type in s.finally_nodes), None)
        els = next((c for c in node.named_children if c.type in s.else_nodes), None)
        return TryInfo(
            self.body_statements(node.child_by_field_name("body")),
            [
                (self.catch_label(c, src) or "excepción", self.body_statements(self.catch_body(c)))
                for c in catches
            ],
            self.body_statements(self.catch_body(els)) if els is not None else None,
            self.body_statements(self.catch_body(final)) if final is not None else None,
        )

    def jump_values(self, node: Node) -> list[Node]:
        """Expresión de un return/throw (sin la palabra clave)."""
        node = self.unwrap(node)
        values = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
        if node.type == "expression_statement" and values:
            values = list(values[0].named_children)
        return values

    def implicit_return(self, st: Node, src: Src) -> bool:
        """¿La última expresión de la función es su valor de retorno? (Ruby, Rust)."""
        return False

    def if_branch(self, node: Node, index: int, field_name: str | None, child: Node) -> str:
        """Para el contexto de las llamadas: "cond", "then" o "else" del hijo `index`."""
        cond = self.condition_node(node)
        if cond is not None and child.id == cond.id:
            return "cond"
        s = self.spec
        if child.type in s.else_nodes or child.type in s.elif_nodes or field_name == "alternative":
            return "else"
        return "then"

    def statement_io(self, st: Node, src: Src) -> tuple[str, str] | None:
        """E/S que no es una llamada (p. ej. `gets` en Ruby): (io_kind, texto fácil)."""
        return None


class IfInfo(NamedTuple):
    cond_node: Node | None
    cond_text: str
    then: list
    alternatives: list
    negated: bool = False  # `unless` (Ruby): la rama principal se ejecuta con "no"


class AltInfo(NamedTuple):
    kind: str  # "elif" | "if" | "else"
    node: Node
    info: IfInfo | None = None
    body: list | None = None


class LoopInfo(NamedTuple):
    kind: str  # "while" | "for" | "foreach" | "do"
    body: list
    cond_node: Node | None = None
    cond_text: str = ""
    init: Node | None = None
    update: Node | None = None
    var_text: str = ""
    coll_node: Node | None = None
    coll_text: str = ""
    header: str = ""
    negated: bool = False  # `until` (Ruby): el cuerpo se ejecuta con "no"


class CaseInfo(NamedTuple):
    value: str | None  # None = caso por defecto
    body: list
    falls: bool = False  # sin break, cae al siguiente caso


class TryInfo(NamedTuple):
    body: list
    catches: list  # [(etiqueta, sentencias)]
    else_body: list | None
    final: list | None
