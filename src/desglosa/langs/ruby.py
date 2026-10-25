"""Ruby (gramática `ruby`). Lenguaje orientado a expresiones.

Verificado con debug-ast: `x.each do |item| … end` es una llamada con bloque (se dibuja como
"Para cada"); `raise` es una llamada (se dibuja como lanzamiento); `next` es el continue;
existen `if_modifier`/`unless_modifier` (`return false unless ok`) y `unless`/`until`
(sus ramas llevan las etiquetas sí/no invertidas). `X.new(...)` construye un objeto.
"""

from __future__ import annotations

import re

from tree_sitter import Node

from desglosa.langs.spec import (
    AltInfo,
    Binding,
    CallParts,
    CaseInfo,
    IfInfo,
    ImportParts,
    LangHooks,
    LangSpec,
    LoopInfo,
    Src,
    TryInfo,
    one_line,
)

SPEC = LangSpec(
    name="ruby",
    grammar="ruby",
    class_nodes=("class", "module"),
    function_nodes=("method", "singleton_method"),
    call_nodes=("call",),
    if_nodes=("if", "unless", "if_modifier", "unless_modifier"),
    elif_nodes=("elsif",),
    else_nodes=("else",),
    loop_nodes=("while", "until", "for", "while_modifier", "until_modifier"),
    switch_nodes=("case",),
    case_nodes=("when",),
    try_nodes=("begin",),
    catch_nodes=("rescue",),
    finally_nodes=("ensure",),
    return_nodes=("return",),
    break_nodes=("break",),
    continue_nodes=("next",),
    block_nodes=("body_statement", "then", "do", "block_body", "else", "ensure"),
    comment_nodes=("comment",),
    self_names=("self",),
    parent_names=("super",),
    implicit_this=True,
    constructor_names=("initialize",),
    expression_oriented=True,
)

ITERATORS = frozenset(
    {
        "each",
        "each_with_index",
        "each_with_object",
        "each_char",
        "each_line",
        "each_pair",
        "each_key",
        "each_value",
        "each_slice",
        "map",
        "collect",
        "select",
        "filter",
        "reject",
        "times",
        "upto",
        "downto",
        "step",
        "loop",
    }
)
RETURN_TYPES = frozenset(
    {
        "true",
        "false",
        "nil",
        "identifier",
        "instance_variable",
        "integer",
        "float",
        "string",
        "simple_symbol",
        "array",
        "hash",
        "binary",
        "self",
        "constant",
        "parenthesized_statements",
    }
)
_MAIN_GUARD = re.compile(r"__FILE__\s*==\s*\$(0|PROGRAM_NAME)|\$(0|PROGRAM_NAME)\s*==\s*__FILE__")


def _block_of(call: Node) -> Node | None:
    return call.child_by_field_name("block")


class Hooks(LangHooks):
    # ---------------------------------------------------------------- símbolos

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        sup = node.child_by_field_name("superclass")
        if sup is None:
            return ()
        return tuple(src.text(c).rsplit("::", 1)[-1] for c in sup.named_children)

    def is_main_guard(self, node: Node, src: Src) -> bool:
        if node.type not in ("if", "if_modifier"):
            return False
        cond = node.child_by_field_name("condition")
        return cond is not None and bool(_MAIN_GUARD.search(src.text(cond)))

    def signature(self, node: Node, src: Src) -> str:
        return one_line(src.text(node).split("\n", 1)[0], 120)

    # ---------------------------------------------------------------- llamadas, imports, tipos

    def call_args(self, node: Node, src: Src) -> tuple[str, ...]:
        args = node.child_by_field_name("arguments")
        if args is None:
            return ()
        return tuple(one_line(src.text(a), 60) for a in args.named_children)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        method = node.child_by_field_name("method")
        if method is None:
            return None
        receiver = node.child_by_field_name("receiver")
        args = self.call_args(node, src)
        name = src.text(method)
        if (
            name == "new"
            and receiver is not None
            and receiver.type in ("constant", "scope_resolution")
        ):
            return CallParts(src.text(receiver).rsplit("::", 1)[-1], None, True, args)
        if receiver is None:
            return CallParts(name, None, False, args)
        return CallParts(name, one_line(src.text(receiver), 80), False, args)

    def call_import(self, node: Node, src: Src) -> ImportParts | None:
        method = node.child_by_field_name("method")
        if method is None or node.child_by_field_name("receiver") is not None:
            return None
        if src.text(method) not in ("require", "require_relative", "load"):
            return None
        args = node.child_by_field_name("arguments")
        strings = [a for a in args.named_children if a.type == "string"] if args else []
        if len(strings) != 1:
            return None
        content = "".join(
            src.text(c) for c in strings[0].named_children if c.type == "string_content"
        )
        return ImportParts(content, None, None)

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t in ("assignment", "optional_parameter"):
            left = node.child_by_field_name("left") or node.child_by_field_name("name")
            right = node.child_by_field_name("right") or node.child_by_field_name("value")
            if left is None or right is None:
                return []
            typ = None
            if right.type == "call":
                parts = self.call_parts(right, src)
                if parts is not None and parts.is_new:
                    typ = parts.callee
            elif right.type == "identifier":
                typ = "@var:" + src.text(right)
            if not typ:
                return []
            if left.type == "instance_variable":
                return [Binding(src.text(left).lstrip("@"), typ, "field")]
            if left.type == "identifier":
                return [Binding(src.text(left), typ, "local")]
        return []

    # ---------------------------------------------------------------- flujo

    def flow_kind(self, st: Node, src: Src) -> str | None:
        if st.type == "call":
            method = st.child_by_field_name("method")
            name = src.text(method) if method is not None else ""
            if st.child_by_field_name("receiver") is None and name in ("raise", "fail"):
                return "throw"
            if _block_of(st) is not None and name in ITERATORS:
                return "loop"
            return None
        if st.type == "begin" and not any(c.type == "rescue" for c in st.named_children):
            return "block"
        return super().flow_kind(st, src)

    def body_statements(self, node: Node | None) -> list[Node]:
        if node is not None and node.type == "begin":
            return [
                c
                for c in node.named_children
                if c.type not in ("rescue", "else", "ensure")
                and c.type not in self.spec.comment_nodes
            ]
        return super().body_statements(node)

    def if_info(self, node: Node, src: Src) -> IfInfo:
        cond = node.child_by_field_name("condition")
        cond_text = one_line(src.text(cond), 200) if cond is not None else ""
        negated = node.type in ("unless", "unless_modifier")
        if node.type in ("if_modifier", "unless_modifier"):
            body = node.child_by_field_name("body")
            return IfInfo(cond, cond_text, [body] if body is not None else [], [], negated)
        then = self.body_statements(node.child_by_field_name("consequence"))
        alts = [
            c for i, c in enumerate(node.children) if node.field_name_for_child(i) == "alternative"
        ]
        return IfInfo(cond, cond_text, then, alts, negated)

    def alt_info(self, alt: Node, src: Src) -> AltInfo:
        if alt.type == "elsif":
            return AltInfo("elif", alt, self.if_info(alt, src))
        return AltInfo("else", alt, body=self.body_statements(alt))

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        if node.type == "call":
            method = src.text(node.child_by_field_name("method"))
            receiver = node.child_by_field_name("receiver")
            block = _block_of(node)
            params = block.child_by_field_name("parameters") if block is not None else None
            body = self.body_statements(block.child_by_field_name("body")) if block else []
            var = src.text(params).strip("|") if params is not None else ""
            header = one_line(src.text(node).split("\n", 1)[0], 120)
            if method == "loop":
                return LoopInfo("while", body, header=header)
            coll = src.text(receiver) if receiver is not None else ""
            if method == "times":
                coll = f"{coll} veces"
            elif method not in ("each", "map", "collect", "select", "filter", "reject"):
                coll = f"{coll}.{method}"
            return LoopInfo(
                "foreach", body, var_text=var, coll_node=receiver, coll_text=coll, header=header
            )
        negated = node.type in ("until", "until_modifier")
        cond = node.child_by_field_name("condition")
        cond_text = one_line(src.text(cond), 200) if cond is not None else ""
        if node.type in ("while_modifier", "until_modifier"):
            body = node.child_by_field_name("body")
            return LoopInfo("while", [body] if body else [], cond, cond_text, negated=negated)
        if node.type == "for":
            pattern = node.child_by_field_name("pattern")
            value = node.child_by_field_name("value")
            coll = (
                value.named_children[0] if value is not None and value.named_child_count else value
            )
            return LoopInfo(
                "foreach",
                self.body_statements(node.child_by_field_name("body")),
                var_text=src.text(pattern),
                coll_node=coll,
                coll_text=src.text(coll),
                header=one_line(src.text(node).split("\n", 1)[0], 120),
            )
        return LoopInfo(
            "while",
            self.body_statements(node.child_by_field_name("body")),
            cond,
            cond_text,
            negated=negated,
        )

    def case_value(self, node: Node, src: Src) -> str | None:
        patterns = [
            src.text(p)
            for i, p in enumerate(node.children)
            if node.field_name_for_child(i) == "pattern"
        ]
        return one_line(", ".join(patterns), 60) if patterns else None

    def statement_io(self, st: Node, src: Src) -> tuple[str, str] | None:
        """`gets` (y `STDIN.gets`) sin paréntesis no es un nodo llamada: se detecta aquí."""
        stack = [st]
        while stack:
            n = stack.pop()
            if n.type == "identifier" and src.text(n) in ("gets", "readline"):
                target = None
                if st.type == "assignment":
                    left = st.child_by_field_name("left")
                    target = src.text(left) if left is not None else None
                return "teclado", "Lee del teclado" + (f" → {target}" if target else "")
            stack.extend(n.named_children)
        return None

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        value = node.child_by_field_name("value")
        subject = src.text(value) if value is not None else "verdadero"
        cases: list[CaseInfo] = []
        for c in node.named_children:
            if c.type == "when":
                patterns = [
                    src.text(p)
                    for i, p in enumerate(c.children)
                    if c.field_name_for_child(i) == "pattern"
                ]
                body = self.body_statements(c.child_by_field_name("body"))
                cases.append(CaseInfo(one_line(", ".join(patterns), 60), body, False))
            elif c.type == "else":
                cases.append(CaseInfo(None, self.body_statements(c), False))
        return subject, one_line(f"case {subject}", 80), cases

    def try_info(self, node: Node, src: Src) -> TryInfo:
        catches = []
        else_body = None
        final = None
        for c in node.named_children:
            if c.type == "rescue":
                exc = c.child_by_field_name("exceptions")
                label = one_line(src.text(exc), 60) if exc is not None else "StandardError"
                catches.append((label, self.body_statements(c.child_by_field_name("body"))))
            elif c.type == "else":
                else_body = self.body_statements(c)
            elif c.type == "ensure":
                final = self.body_statements(c)
        return TryInfo(self.body_statements(node), catches, else_body, final)

    def jump_values(self, node: Node) -> list[Node]:
        if node.type == "call":  # raise X, "msg"
            args = node.child_by_field_name("arguments")
            return list(args.named_children) if args is not None else []
        values = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
        if len(values) == 1 and values[0].type == "argument_list":
            return list(values[0].named_children)
        return values

    def implicit_return(self, st: Node, src: Src) -> bool:
        return st.type in RETURN_TYPES


HOOKS = Hooks(SPEC)
