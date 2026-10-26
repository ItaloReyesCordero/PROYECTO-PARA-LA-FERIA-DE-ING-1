"""Kotlin (gramática `kotlin`).

Verificado con debug-ast: casi ningún nodo tiene campos con nombre (el nombre de una
función es su primer `simple_identifier`); `return`, `throw`, `break` y `continue` son
todos `jump_expression` (se distinguen por la palabra clave); una interfaz es un
`class_declaration` con la palabra `interface`; los cuerpos son
`control_structure_body > statements`; `Clase(args)` construye un objeto (sin `new`).
"""

from __future__ import annotations

from tree_sitter import Node

from desglosa.langs.members import KotlinMembers
from desglosa.langs.spec import (
    Binding,
    CallParts,
    CaseInfo,
    ImportParts,
    LangHooks,
    LangSpec,
    LoopInfo,
    Src,
    TryInfo,
    one_line,
    strip_parens,
)

SPEC = LangSpec(
    name="kotlin",
    grammar="kotlin",
    class_nodes=("class_declaration", "object_declaration"),
    function_nodes=("function_declaration", "secondary_constructor"),
    import_nodes=("import_header",),
    call_nodes=("call_expression",),
    if_nodes=("if_expression",),
    loop_nodes=("for_statement", "while_statement"),
    do_while_nodes=("do_while_statement",),
    switch_nodes=("when_expression",),
    case_nodes=("when_entry",),
    try_nodes=("try_expression",),
    catch_nodes=("catch_block",),
    finally_nodes=("finally_block",),
    block_nodes=("statements", "control_structure_body", "function_body", "block"),
    comment_nodes=("line_comment", "multiline_comment"),
    self_names=("this",),
    parent_names=("super",),
    implicit_this=True,
    expression_oriented=True,
)

JUMPS = {"return": "return", "throw": "throw", "break": "break", "continue": "continue"}


def _first(node: Node, *types: str) -> Node | None:
    return next((c for c in node.named_children if c.type in types), None)


def _type_text(node: Node | None, src: Src) -> str:
    if node is None:
        return ""
    return src.text(node).rstrip("?").split("<", 1)[0].rsplit(".", 1)[-1]


class Hooks(KotlinMembers, LangHooks):
    flatten_blocks = ("statements", "control_structure_body")

    # ---------------------------------------------------------------- símbolos

    def symbol_name(self, node: Node, src: Src) -> str | None:
        if node.type in ("class_declaration", "object_declaration"):
            name = _first(node, "type_identifier", "simple_identifier")
        elif node.type == "secondary_constructor":
            return "constructor"
        else:
            name = _first(node, "simple_identifier")
        return src.text(name) if name is not None else None

    def class_kind(self, node: Node, src: Src) -> str | None:
        if any(not c.is_named and c.type == "interface" for c in node.children):
            return "interface"
        return "class"

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        out = []
        for spec in node.named_children:
            if spec.type != "delegation_specifier":
                continue
            target = _first(spec, "user_type", "constructor_invocation")
            if target is not None and target.type == "constructor_invocation":
                target = _first(target, "user_type")
            if target is not None:
                out.append(_type_text(target, src))
        return tuple(out)

    def function_body(self, node: Node) -> Node | None:
        return _first(node, "function_body", "block")

    def parameters_node(self, node: Node) -> Node | None:
        return _first(node, "function_value_parameters")

    def signature(self, node: Node, src: Src) -> str:
        body = _first(node, "function_body", "class_body")
        end = body.start_byte if body is not None else node.end_byte
        return one_line(src.between(node.start_byte, end).rstrip(" {=:"), 120)

    # ---------------------------------------------------------------- llamadas, imports, tipos

    def call_args(self, node: Node, src: Src) -> tuple[str, ...]:
        suffix = _first(node, "call_suffix")
        args = _first(suffix, "value_arguments") if suffix is not None else None
        if args is None:
            return ()
        return tuple(one_line(src.text(a), 60) for a in args.named_children)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        callee = node.named_children[0] if node.named_child_count else None
        if callee is None:
            return None
        args = self.call_args(node, src)
        if callee.type == "simple_identifier":
            return CallParts(src.text(callee), None, False, args)
        if callee.type == "navigation_expression" and callee.named_child_count >= 2:
            suffix = callee.named_children[-1]
            name = _first(suffix, "simple_identifier")
            receiver = callee.named_children[0]
            if name is not None:
                return CallParts(src.text(name), one_line(src.text(receiver), 80), False, args)
        return CallParts(one_line(src.text(callee), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        ident = _first(node, "identifier")
        if ident is None:
            return []
        full = src.text(ident)
        alias_node = _first(node, "import_alias")
        alias = src.text(_first(alias_node, "type_identifier")) if alias_node is not None else None
        if any(c.type == "wildcard_import" for c in node.named_children):
            return [ImportParts(full, "*", None)]
        return [ImportParts(full, full.rsplit(".", 1)[-1], alias)]

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t in ("parameter", "class_parameter"):
            name = _first(node, "simple_identifier")
            typ = _first(node, "user_type", "nullable_type")
            if name is None or typ is None:
                return []
            out = [Binding(src.text(name), _type_text(typ, src), "local")]
            if t == "class_parameter" and _first(node, "binding_pattern_kind") is not None:
                out.append(Binding(src.text(name), _type_text(typ, src), "field"))
            return out
        if t == "property_declaration":
            decl = _first(node, "variable_declaration")
            if decl is None:
                return []
            name = _first(decl, "simple_identifier")
            typ = _first(decl, "user_type", "nullable_type")
            if name is None:
                return []
            if typ is not None:
                return [Binding(src.text(name), _type_text(typ, src), "local")]
            value = _first(node, "call_expression")
            if value is not None and value.named_child_count:
                callee = value.named_children[0]
                text = src.text(callee)
                if callee.type == "simple_identifier" and text[:1].isupper():
                    return [Binding(src.text(name), text, "local")]
        return []

    # ---------------------------------------------------------------- flujo

    def control_kind(self, node: Node) -> str | None:
        if node.type == "jump_expression":
            keyword = node.children[0].type if node.child_count else ""
            for word, kind in JUMPS.items():
                if keyword.startswith(word):
                    return kind
            return None
        return super().control_kind(node)

    def case_value(self, node: Node, src: Src) -> str | None:
        conds = [src.text(c) for c in node.named_children if c.type == "when_condition"]
        return one_line(", ".join(conds), 60) if conds else None

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(_first(node, "control_structure_body"))
        if node.type == "for_statement":
            var = _first(node, "variable_declaration", "multi_variable_declaration")
            coll = next(
                (
                    c
                    for c in node.named_children
                    if c.type
                    not in (
                        "variable_declaration",
                        "multi_variable_declaration",
                        "control_structure_body",
                        "annotation",
                    )
                ),
                None,
            )
            return LoopInfo(
                "foreach",
                body,
                var_text=src.text(var),
                coll_node=coll,
                coll_text=src.text(coll),
                header=one_line(src.text(node).split("{", 1)[0], 120),
            )
        cond = next((c for c in node.named_children if c.type != "control_structure_body"), None)
        return LoopInfo("while", body, cond, strip_parens(src.text(cond)) if cond else "")

    def do_while_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(_first(node, "control_structure_body"))
        cond = next((c for c in node.named_children if c.type != "control_structure_body"), None)
        return LoopInfo("do", body, cond, strip_parens(src.text(cond)) if cond else "")

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        subject_node = _first(node, "when_subject")
        subject = strip_parens(src.text(subject_node)) if subject_node is not None else ""
        cases: list[CaseInfo] = []
        for entry in node.named_children:
            if entry.type != "when_entry":
                continue
            conds = [src.text(c) for c in entry.named_children if c.type == "when_condition"]
            body = self.body_statements(_first(entry, "control_structure_body"))
            label = one_line(", ".join(conds), 60) if conds else None
            cases.append(CaseInfo(label, body, False))
        tech = one_line(f"when ({subject})" if subject else "when", 80)
        return subject or "condiciones", tech, cases

    def try_info(self, node: Node, src: Src) -> TryInfo:
        body = self.body_statements(_first(node, "statements", "block"))
        catches = []
        final = None
        for c in node.named_children:
            if c.type == "catch_block":
                typ = _first(c, "user_type")
                label = _type_text(typ, src) if typ is not None else "excepción"
                catches.append((label, self.body_statements(_first(c, "statements", "block"))))
            elif c.type == "finally_block":
                final = self.body_statements(_first(c, "statements", "block"))
        return TryInfo(body, catches, None, final)

    def jump_values(self, node: Node) -> list[Node]:
        node = self.unwrap(node)
        return [
            c for c in node.named_children if c.type not in ("label",) + self.spec.comment_nodes
        ]

    def implicit_return(self, st: Node, src: Src) -> bool:
        parent = st.parent
        if parent is None or parent.type != "function_body":
            return False
        return any(not c.is_named and c.type == "=" for c in parent.children)


HOOKS = Hooks(SPEC)
