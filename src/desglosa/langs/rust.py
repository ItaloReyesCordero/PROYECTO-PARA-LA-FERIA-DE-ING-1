"""Rust (gramática `rust`). Lenguaje orientado a expresiones.

Verificado con debug-ast: las sentencias de control vienen envueltas en
`expression_statement` (`if_expression`, `for_expression`, `return_expression`…); los
métodos viven en `impl_item` separados del `struct` (se enlazan por nombre, como C++
`A::m`); `impl Trait for Tipo` declara la "herencia"; la última expresión de un bloque sin
`;` es su valor de retorno.
"""

from __future__ import annotations

from tree_sitter import Node

from desglosa.langs.members import RustMembers
from desglosa.langs.spec import (
    Binding,
    CallParts,
    CaseInfo,
    ImportParts,
    LangHooks,
    LangSpec,
    LoopInfo,
    Src,
    one_line,
    strip_parens,
)

SPEC = LangSpec(
    name="rust",
    grammar="rust",
    class_nodes=("struct_item", "enum_item", "union_item", "trait_item"),
    interface_nodes=("trait_item",),
    function_nodes=("function_item",),
    method_nodes=("function_signature_item",),
    import_nodes=("use_declaration",),
    call_nodes=("call_expression", "macro_invocation", "struct_expression"),
    if_nodes=("if_expression",),
    else_nodes=("else_clause",),
    loop_nodes=("for_expression", "while_expression", "loop_expression"),
    switch_nodes=("match_expression",),
    case_nodes=("match_arm",),
    return_nodes=("return_expression",),
    break_nodes=("break_expression",),
    continue_nodes=("continue_expression",),
    block_nodes=("block",),
    comment_nodes=("line_comment", "block_comment"),
    self_names=("self",),
    constructor_names=("new",),
    expression_oriented=True,
)

NOT_RETURN = frozenset(
    {
        "expression_statement",
        "let_declaration",
        "macro_invocation",
        "empty_statement",
        "function_item",
        "struct_item",
        "use_declaration",
        "const_item",
        "static_item",
        "line_comment",
        "block_comment",
    }
)


def _type_name(node: Node | None, src: Src) -> str:
    if node is None:
        return ""
    text = src.text(node).lstrip("&").replace("mut ", "").strip()
    return text.split("<", 1)[0].rsplit("::", 1)[-1]


def _impl_of(node: Node) -> Node | None:
    cur = node.parent
    while cur is not None:
        if cur.type == "impl_item":
            return cur
        if cur.type in ("function_item", "trait_item", "source_file"):
            return None
        cur = cur.parent
    return None


class Hooks(RustMembers, LangHooks):
    # ---------------------------------------------------------------- símbolos

    def symbol_qualifier(self, node: Node, src: Src) -> str | None:
        impl = _impl_of(node) if node.type == "function_item" else None
        if impl is None:
            return None
        return _type_name(impl.child_by_field_name("type"), src) or None

    def extra_bases(self, node: Node, src: Src) -> list[tuple[str, str]]:
        if node.type != "impl_item":
            return []
        trait = node.child_by_field_name("trait")
        typ = node.child_by_field_name("type")
        if trait is None or typ is None:
            return []
        return [(_type_name(typ, src), _type_name(trait, src))]

    def signature(self, node: Node, src: Src) -> str:
        if node.type in self.spec.class_nodes:
            return one_line(src.text(node).split("{", 1)[0], 120)
        return super().signature(node, src)

    # ---------------------------------------------------------------- llamadas, imports, tipos

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        t = node.type
        if t == "macro_invocation":
            macro = node.child_by_field_name("macro")
            if macro is None:
                return None
            tree = next((c for c in node.named_children if c.type == "token_tree"), None)
            args = (one_line(src.text(tree).strip("()[]{}"), 60),) if tree is not None else ()
            return CallParts(src.text(macro).rsplit("::", 1)[-1] + "!", None, False, args)
        if t == "struct_expression":
            name = node.child_by_field_name("name")
            return CallParts(_type_name(name, src), None, True, ()) if name is not None else None
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        args = self.call_args(node, src)
        if fn.type == "generic_function":
            fn = fn.child_by_field_name("function") or fn
        if fn.type == "identifier":
            return CallParts(src.text(fn), None, False, args)
        if fn.type == "field_expression":
            value = fn.child_by_field_name("value")
            field = fn.child_by_field_name("field")
            if value is not None and field is not None:
                return CallParts(src.text(field), one_line(src.text(value), 80), False, args)
        if fn.type == "scoped_identifier":
            path = fn.child_by_field_name("path")
            name = fn.child_by_field_name("name")
            if name is not None:
                receiver = src.text(path) if path is not None else None
                return CallParts(src.text(name), receiver, False, args)
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        arg = node.child_by_field_name("argument")
        out: list[ImportParts] = []

        def walk(n: Node | None, prefix: str) -> None:
            if n is None:
                return
            if n.type == "scoped_use_list":
                path = n.child_by_field_name("path")
                new_prefix = prefix + (src.text(path) + "::" if path is not None else "")
                walk(n.child_by_field_name("list"), new_prefix)
            elif n.type == "use_list":
                for c in n.named_children:
                    walk(c, prefix)
            elif n.type == "use_as_clause":
                path = n.child_by_field_name("path")
                alias = n.child_by_field_name("alias")
                full = prefix + src.text(path)
                out.append(ImportParts(full, full.rsplit("::", 1)[-1], src.text(alias)))
            else:
                full = prefix + src.text(n)
                out.append(ImportParts(full, full.rsplit("::", 1)[-1], None))

        walk(arg, "")
        return out

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "parameter":
            pattern = node.child_by_field_name("pattern")
            typ = node.child_by_field_name("type")
            if pattern is not None and typ is not None and pattern.type == "identifier":
                return [Binding(src.text(pattern), _type_name(typ, src), "local")]
        elif t == "field_declaration":
            name = node.child_by_field_name("name")
            typ = node.child_by_field_name("type")
            if name is not None and typ is not None:
                return [Binding(src.text(name), _type_name(typ, src), "field")]
        elif t == "let_declaration":
            pattern = node.child_by_field_name("pattern")
            if pattern is None or pattern.type != "identifier":
                return []
            typ = node.child_by_field_name("type")
            if typ is not None:
                return [Binding(src.text(pattern), _type_name(typ, src), "local")]
            value = node.child_by_field_name("value")
            if value is not None and value.type == "struct_expression":
                name = value.child_by_field_name("name")
                return [Binding(src.text(pattern), _type_name(name, src), "local")]
            if value is not None and value.type == "call_expression":
                fn = value.child_by_field_name("function")
                if fn is not None and fn.type == "scoped_identifier":
                    path = fn.child_by_field_name("path")
                    if path is not None:
                        return [Binding(src.text(pattern), _type_name(path, src), "local")]
        return []

    # ---------------------------------------------------------------- flujo

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(node.child_by_field_name("body"))
        if node.type == "for_expression":
            pattern = node.child_by_field_name("pattern")
            value = node.child_by_field_name("value")
            return LoopInfo(
                "foreach",
                body,
                var_text=src.text(pattern),
                coll_node=value,
                coll_text=src.text(value),
                header=one_line(src.text(node).split("{", 1)[0], 120),
            )
        if node.type == "loop_expression":
            return LoopInfo("while", body)
        cond = node.child_by_field_name("condition")
        return LoopInfo(
            "while",
            body,
            cond_node=cond,
            cond_text=strip_parens(src.text(cond)) if cond is not None else "",
        )

    def condition_node(self, node: Node) -> Node | None:
        if node.type == "match_expression":
            return node.child_by_field_name("value")
        return node.child_by_field_name("condition")

    def case_value(self, node: Node, src: Src) -> str | None:
        pattern = node.child_by_field_name("pattern")
        text = src.text(pattern).strip() if pattern is not None else "_"
        return None if text == "_" else one_line(text, 60)

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        value = node.child_by_field_name("value")
        subject = src.text(value) if value is not None else ""
        body = node.child_by_field_name("body")
        cases: list[CaseInfo] = []
        for arm in body.named_children if body is not None else []:
            if arm.type != "match_arm":
                continue
            pattern = arm.child_by_field_name("pattern")
            text = src.text(pattern).strip() if pattern is not None else "_"
            result = arm.child_by_field_name("value")
            stmts = self.body_statements(result) if result is not None else []
            cases.append(CaseInfo(None if text == "_" else one_line(text, 60), stmts, False))
        return subject, one_line(f"match {subject}", 80), cases

    def implicit_return(self, st: Node, src: Src) -> bool:
        if st.type in NOT_RETURN or self.control_kind(st) is not None:
            return False
        parent = st.parent
        return parent is not None and parent.type == "block"


HOOKS = Hooks(SPEC)
