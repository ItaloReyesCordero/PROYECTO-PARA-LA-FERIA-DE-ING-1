"""Go (gramática `go`).

Verificado con debug-ast: el cuerpo de una función es `block > statement_list`; el `for`
lleva su condición sin nombre de campo (o dentro de `range_clause` / `for_clause`); los
métodos se atan a su tipo por el receptor (`func (s *Servicio) Metodo()`); los casos de un
switch contienen un `statement_list`; `fallthrough_statement` hace que un caso caiga al
siguiente; `panic(...)` se dibuja como un lanzamiento de excepción.
"""

from __future__ import annotations

from tree_sitter import Node

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
    name="go",
    grammar="go",
    class_nodes=("type_spec",),
    function_nodes=("function_declaration",),
    method_nodes=("method_declaration", "method_elem", "method_spec"),
    import_nodes=("import_spec",),
    call_nodes=("call_expression", "composite_literal"),
    if_nodes=("if_statement",),
    loop_nodes=("for_statement",),
    switch_nodes=("expression_switch_statement", "type_switch_statement", "select_statement"),
    case_nodes=("expression_case", "type_case", "default_case", "communication_case"),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    block_nodes=("block", "statement_list"),
    comment_nodes=("comment",),
    goto_nodes=("goto_statement",),
    label_nodes=("labeled_statement",),
)


def _type_name(node: Node | None, src: Src) -> str:
    if node is None:
        return ""
    return src.text(node).lstrip("*&[]").split("[", 1)[0].rsplit(".", 1)[-1]


class Hooks(LangHooks):
    flatten_blocks = ("statement_list",)
    wrapper_nodes = ("type_declaration",)

    # ---------------------------------------------------------------- símbolos

    def class_kind(self, node: Node, src: Src) -> str | None:
        typ = node.child_by_field_name("type")
        if typ is None:
            return None
        if typ.type == "struct_type":
            return "class"
        if typ.type == "interface_type":
            return "interface"
        return None

    def symbol_qualifier(self, node: Node, src: Src) -> str | None:
        if node.type != "method_declaration":
            return None
        receiver = node.child_by_field_name("receiver")
        if receiver is None:
            return None
        param = next(
            (c for c in receiver.named_children if c.type == "parameter_declaration"), None
        )
        return _type_name(param.child_by_field_name("type"), src) if param is not None else None

    def has_body(self, node: Node) -> bool:
        return node.child_by_field_name("body") is not None

    def signature(self, node: Node, src: Src) -> str:
        if node.type == "type_spec":
            return one_line("type " + src.text(node).split("{", 1)[0], 120)
        return super().signature(node, src)

    # ---------------------------------------------------------------- llamadas, imports, tipos

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        if node.type == "composite_literal":
            typ = node.child_by_field_name("type")
            name = _type_name(typ, src)
            if not name or not name[0].isupper():
                return None
            return CallParts(name, None, True, ())
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        args = self.call_args(node, src)
        if fn.type == "identifier":
            return CallParts(src.text(fn), None, False, args)
        if fn.type == "selector_expression":
            operand = fn.child_by_field_name("operand")
            field = fn.child_by_field_name("field")
            if operand is not None and field is not None:
                return CallParts(src.text(field), one_line(src.text(operand), 80), False, args)
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        path = node.child_by_field_name("path")
        if path is None:
            return []
        module = src.text(path).strip('"`')
        alias = node.child_by_field_name("name")
        return [ImportParts(module, None, src.text(alias) if alias is not None else None)]

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "parameter_declaration":
            typ = node.child_by_field_name("type")
            names = [c for c in node.named_children if c.type == "identifier"]
            return [Binding(src.text(n), _type_name(typ, src), "local") for n in names if typ]
        if t == "field_declaration":
            typ = node.child_by_field_name("type")
            names = [c for c in node.named_children if c.type == "field_identifier"]
            return [Binding(src.text(n), _type_name(typ, src), "field") for n in names if typ]
        if t == "var_spec":
            typ = node.child_by_field_name("type")
            names = [c for c in node.named_children if c.type == "identifier"]
            return [Binding(src.text(n), _type_name(typ, src), "local") for n in names if typ]
        if t == "short_var_declaration":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                return []
            out = []
            for name, value in zip(left.named_children, right.named_children, strict=False):
                if value.type == "unary_expression":
                    value = value.child_by_field_name("operand") or value
                if value.type == "composite_literal":
                    typ = _type_name(value.child_by_field_name("type"), src)
                    if typ:
                        out.append(Binding(src.text(name), typ, "local"))
            return out
        return []

    # ---------------------------------------------------------------- flujo

    def flow_kind(self, st: Node, src: Src) -> str | None:
        if st.type == "expression_statement" and st.named_child_count == 1:
            call = st.named_children[0]
            if call.type == "call_expression":
                fn = call.child_by_field_name("function")
                if fn is not None and src.text(fn) == "panic":
                    return "throw"
        return super().flow_kind(st, src)

    def jump_values(self, node: Node) -> list[Node]:
        if node.type == "expression_statement":  # panic(...)
            call = node.named_children[0]
            args = call.child_by_field_name("arguments")
            return list(args.named_children) if args is not None else []
        values = super().jump_values(node)
        if len(values) == 1 and values[0].type == "expression_list":
            return list(values[0].named_children)
        return values

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(node.child_by_field_name("body"))
        header = one_line(src.text(node).split("{", 1)[0], 120)
        clause = next(
            (c for c in node.named_children if c.type in ("range_clause", "for_clause")), None
        )
        if clause is not None and clause.type == "range_clause":
            left = clause.child_by_field_name("left")
            names = [c for c in left.named_children if src.text(c) != "_"] if left else []
            coll = clause.child_by_field_name("right")
            return LoopInfo(
                "foreach",
                body,
                var_text=", ".join(src.text(n) for n in names),
                coll_node=coll,
                coll_text=src.text(coll),
                header=header,
            )
        if clause is not None:
            cond = clause.child_by_field_name("condition")
            return LoopInfo(
                "for",
                body,
                cond_node=cond,
                cond_text=src.text(cond) if cond is not None else "",
                init=clause.child_by_field_name("initializer"),
                update=clause.child_by_field_name("update"),
            )
        cond = next(
            (
                c
                for i, c in enumerate(node.children)
                if c.is_named
                and node.field_name_for_child(i) is None
                and c.type not in self.spec.comment_nodes
            ),
            None,
        )
        return LoopInfo(
            "while",
            body,
            cond_node=cond,
            cond_text=strip_parens(src.text(cond)) if cond is not None else "",
        )

    def condition_node(self, node: Node) -> Node | None:
        if node.type in self.spec.switch_nodes:
            return node.child_by_field_name("value")
        return node.child_by_field_name("condition")

    def case_value(self, node: Node, src: Src) -> str | None:
        label = node.child_by_field_name("value") or node.child_by_field_name("type")
        return one_line(src.text(label), 60) if label is not None else None

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        value = node.child_by_field_name("value")
        subject = src.text(value) if value is not None else "verdadero"
        tech = one_line(src.text(node).split("{", 1)[0], 80)
        cases: list[CaseInfo] = []
        for c in node.named_children:
            if c.type not in self.spec.case_nodes:
                continue
            label_node = c.child_by_field_name("value") or c.child_by_field_name("type")
            if c.type == "communication_case":
                label_node = c.child_by_field_name("communication")
            label = one_line(src.text(label_node), 60) if label_node is not None else None
            stmts = [
                s
                for s in self.body_statements(
                    next((x for x in c.named_children if x.type == "statement_list"), None)
                )
            ]
            falls = bool(stmts) and stmts[-1].type == "fallthrough_statement"
            if falls:
                stmts = stmts[:-1]
            cases.append(CaseInfo(label, stmts, falls))
        return subject, tech, cases


HOOKS = Hooks(SPEC)
