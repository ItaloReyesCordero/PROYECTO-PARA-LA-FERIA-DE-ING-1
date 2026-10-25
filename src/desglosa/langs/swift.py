"""Swift (gramática `swift`).

Verificado con debug-ast: `class_declaration` sirve para class/struct/enum/extension (la
palabra va en `declaration_kind`); los métodos de una `extension` se atan al tipo
extendido; `return/throw/break/continue` son `control_transfer_statement`; los parámetros
cuelgan directo de la función (sin nodo contenedor); el `else` de un `if` es un token
seguido de `statements` o de otro `if_statement`; `guard cond else { … }` es un if cuya
rama "no" debe terminar.
"""

from __future__ import annotations

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
    strip_parens,
)

SPEC = LangSpec(
    name="swift",
    grammar="swift",
    class_nodes=("class_declaration", "protocol_declaration"),
    interface_nodes=("protocol_declaration",),
    function_nodes=("function_declaration", "init_declaration", "deinit_declaration"),
    method_nodes=("protocol_function_declaration",),
    import_nodes=("import_declaration",),
    call_nodes=("call_expression",),
    if_nodes=("if_statement", "guard_statement"),
    loop_nodes=("for_statement", "while_statement"),
    do_while_nodes=("repeat_while_statement",),
    switch_nodes=("switch_statement",),
    case_nodes=("switch_entry",),
    try_nodes=("do_statement",),
    catch_nodes=("catch_block",),
    block_nodes=("statements", "function_body"),
    comment_nodes=("comment", "multiline_comment"),
    self_names=("self",),
    parent_names=("super",),
    implicit_this=True,
    constructor_names=("init",),
)

JUMPS = {
    "return": "return",
    "throw_keyword": "throw",
    "throw": "throw",
    "break": "break",
    "continue": "continue",
}


def _first(node: Node | None, *types: str) -> Node | None:
    if node is None:
        return None
    return next((c for c in node.named_children if c.type in types), None)


def _kind_word(node: Node, src: Src) -> str:
    kind = node.child_by_field_name("declaration_kind")
    return src.text(kind) if kind is not None else ""


def _type_text(node: Node | None, src: Src) -> str:
    if node is None:
        return ""
    return src.text(node).rstrip("?!").split("<", 1)[0].rsplit(".", 1)[-1]


class Hooks(LangHooks):
    flatten_blocks = ("statements",)

    # ---------------------------------------------------------------- símbolos

    def symbol_name(self, node: Node, src: Src) -> str | None:
        if node.type == "init_declaration":
            return "init"
        if node.type == "deinit_declaration":
            return "deinit"
        name = node.child_by_field_name("name")
        return src.text(name) if name is not None else None

    def class_kind(self, node: Node, src: Src) -> str | None:
        if node.type == "protocol_declaration":
            return "interface"
        return None if _kind_word(node, src) == "extension" else "class"

    def symbol_qualifier(self, node: Node, src: Src) -> str | None:
        cur = node.parent
        while cur is not None and cur.type not in ("source_file", "function_declaration"):
            if cur.type == "class_declaration":
                if _kind_word(cur, src) == "extension":
                    return _type_text(cur.child_by_field_name("name"), src)
                return None
            cur = cur.parent
        return None

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        out = []
        for spec in node.named_children:
            if spec.type == "inheritance_specifier":
                target = spec.child_by_field_name("inherits_from") or _first(spec, "user_type")
                if target is not None:
                    out.append(_type_text(target, src))
        return tuple(out)

    def parameter_list(self, node: Node, src: Src) -> tuple[list[Node], str] | None:
        params = [c for c in node.named_children if c.type == "parameter"]
        return params, "(" + ", ".join(src.text(p) for p in params) + ")"

    def signature(self, node: Node, src: Src) -> str:
        body = node.child_by_field_name("body")
        end = body.start_byte if body is not None else node.end_byte
        return one_line(src.between(node.start_byte, end).rstrip(" {"), 120)

    # ---------------------------------------------------------------- llamadas, imports, tipos

    def call_args(self, node: Node, src: Src) -> tuple[str, ...]:
        args = _first(_first(node, "call_suffix"), "value_arguments")
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
        if callee.type == "navigation_expression":
            target = callee.child_by_field_name("target")
            suffix = callee.child_by_field_name("suffix")
            name = suffix.child_by_field_name("suffix") if suffix is not None else None
            if target is not None and name is not None:
                return CallParts(src.text(name), one_line(src.text(target), 80), False, args)
        return CallParts(one_line(src.text(callee), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        ident = _first(node, "identifier")
        return [ImportParts(src.text(ident), None, None)] if ident is not None else []

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "parameter":
            name = _first(node, "simple_identifier")
            typ = _first(node, "user_type", "optional_type")
            if name is not None and typ is not None:
                return [Binding(src.text(name), _type_text(typ, src), "local")]
        elif t == "property_declaration":
            pattern = node.child_by_field_name("name")
            ident = pattern.child_by_field_name("bound_identifier") if pattern is not None else None
            if ident is None:
                return []
            annot = _first(node, "type_annotation")
            if annot is not None:
                typ = annot.child_by_field_name("name") or _first(annot, "user_type")
                return [Binding(src.text(ident), _type_text(typ, src), "local")]
            value = node.child_by_field_name("value")
            if value is not None and value.type == "call_expression" and value.named_child_count:
                callee = value.named_children[0]
                text = src.text(callee)
                if callee.type == "simple_identifier" and text[:1].isupper():
                    return [Binding(src.text(ident), text, "local")]
        return []

    # ---------------------------------------------------------------- flujo

    def control_kind(self, node: Node) -> str | None:
        if node.type == "control_transfer_statement":
            keyword = node.children[0].type if node.child_count else ""
            return JUMPS.get(keyword)
        return super().control_kind(node)

    def condition(self, node: Node, src: Src) -> str:
        conds = [
            c for i, c in enumerate(node.children) if node.field_name_for_child(i) == "condition"
        ]
        return one_line(", ".join(strip_parens(src.text(c)) for c in conds), 200)

    def if_branch(self, node: Node, index: int, field_name: str | None, child: Node) -> str:
        if field_name == "condition":
            return "cond"
        if node.type == "guard_statement":
            return "else"
        if any(not c.is_named and c.type == "else" for c in node.children[:index]):
            return "else"
        return "then"

    def case_value(self, node: Node, src: Src) -> str | None:
        patterns = [src.text(p) for p in node.named_children if p.type == "switch_pattern"]
        return one_line(", ".join(patterns), 60) if patterns else None

    def if_info(self, node: Node, src: Src) -> IfInfo:
        cond = self.condition_node(node)
        if node.type == "guard_statement":
            orelse = _first(node, "statements")
            return IfInfo(cond, self.condition(node, src), [], [orelse] if orelse else [])
        then = None
        alts: list[Node] = []
        seen_else = False
        for c in node.children:
            if not c.is_named:
                seen_else = seen_else or c.type == "else"
                continue
            if c.type in ("statements", "if_statement"):
                if seen_else:
                    alts.append(c)
                elif then is None and c.type == "statements":
                    then = c
        return IfInfo(cond, self.condition(node, src), self.body_statements(then), alts)

    def alt_info(self, alt: Node, src: Src) -> AltInfo:
        if alt.type == "if_statement":
            return AltInfo("if", alt)
        return AltInfo("else", alt, body=self.body_statements(alt))

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        body = self.body_statements(_first(node, "statements"))
        if node.type == "for_statement":
            item = node.child_by_field_name("item")
            coll = node.child_by_field_name("collection")
            return LoopInfo(
                "foreach",
                body,
                var_text=src.text(item),
                coll_node=coll,
                coll_text=src.text(coll),
                header=one_line(src.text(node).split("{", 1)[0], 120),
            )
        return LoopInfo("while", body, self.condition_node(node), self.condition(node, src))

    def do_while_info(self, node: Node, src: Src) -> LoopInfo:
        return LoopInfo(
            "do",
            self.body_statements(_first(node, "statements")),
            self.condition_node(node),
            self.condition(node, src),
        )

    def switch_info(self, node: Node, src: Src) -> tuple[str, str, list[CaseInfo]]:
        expr = node.child_by_field_name("expr")
        subject = src.text(expr) if expr is not None else ""
        cases: list[CaseInfo] = []
        for entry in node.named_children:
            if entry.type != "switch_entry":
                continue
            patterns = [src.text(p) for p in entry.named_children if p.type == "switch_pattern"]
            stmts = self.body_statements(_first(entry, "statements"))
            falls = (
                bool(stmts)
                and stmts[-1].type == "control_transfer_statement"
                and (src.text(stmts[-1]).strip() == "fallthrough")
            )
            if falls:
                stmts = stmts[:-1]
            label = one_line(", ".join(patterns), 60) if patterns else None
            cases.append(CaseInfo(label, stmts, falls))
        return subject, one_line(f"switch {subject}", 80), cases

    def try_info(self, node: Node, src: Src) -> TryInfo:
        catches = []
        for c in node.named_children:
            if c.type == "catch_block":
                pattern = next(
                    (p for p in c.named_children if p.type not in ("statements", "catch_keyword")),
                    None,
                )
                label = one_line(src.text(pattern), 60) if pattern is not None else "error"
                catches.append((label, self.body_statements(_first(c, "statements"))))
        return TryInfo(self.body_statements(_first(node, "statements")), catches, None, None)

    def jump_values(self, node: Node) -> list[Node]:
        node = self.unwrap(node)
        result = node.child_by_field_name("result")
        if result is not None:
            return [result]
        return [c for c in node.named_children if c.type != "throw_keyword"]


HOOKS = Hooks(SPEC)
