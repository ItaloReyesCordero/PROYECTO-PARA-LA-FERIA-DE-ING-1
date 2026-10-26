"""Java (gramática `java`).

Verificado con debug-ast: no existe `else_clause`; el `else` cuelga del campo
`alternative` del `if_statement` (un `if_statement` para `else if`, o un `block`).
El `switch` clásico también se llama `switch_expression`.
"""

from __future__ import annotations

from tree_sitter import Node

from desglosa.langs.members import JavaMembers
from desglosa.langs.spec import (
    Binding,
    CallParts,
    ImportParts,
    LangHooks,
    LangSpec,
    Src,
    one_line,
)

SPEC = LangSpec(
    name="java",
    grammar="java",
    class_nodes=("class_declaration", "enum_declaration", "record_declaration"),
    interface_nodes=("interface_declaration",),
    method_nodes=("method_declaration", "constructor_declaration"),
    import_nodes=("import_declaration",),
    call_nodes=("method_invocation", "object_creation_expression"),
    if_nodes=("if_statement",),
    loop_nodes=("for_statement", "enhanced_for_statement", "while_statement"),
    do_while_nodes=("do_statement",),
    switch_nodes=("switch_expression", "switch_statement"),
    case_nodes=("switch_block_statement_group", "switch_rule"),
    try_nodes=("try_statement", "try_with_resources_statement"),
    catch_nodes=("catch_clause",),
    finally_nodes=("finally_clause",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    throw_nodes=("throw_statement",),
    block_nodes=("block", "constructor_body"),
    comment_nodes=("line_comment", "block_comment"),
    self_names=("this",),
    parent_names=("super",),
    implicit_this=True,
)


def _type_text(node: Node | None, src: Src) -> str:
    return src.text(node) if node is not None else ""


class Hooks(JavaMembers, LangHooks):
    fallthrough = True

    def is_static(self, node: Node, src: Src) -> bool:
        mods = next((c for c in node.named_children if c.type == "modifiers"), None)
        return mods is not None and "static" in src.text(mods).split()

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        out: list[str] = []
        for child in node.named_children:
            if child.type in ("superclass", "super_interfaces", "extends_interfaces"):
                stack = list(child.named_children)
                while stack:
                    n = stack.pop(0)
                    if n.type in ("type_identifier", "scoped_type_identifier"):
                        out.append(src.text(n).rsplit(".", 1)[-1])
                    elif n.type in ("type_list", "generic_type"):
                        stack[0:0] = [c for c in n.named_children if c.type != "type_arguments"]
        return tuple(out)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        args = self.call_args(node, src)
        if node.type == "object_creation_expression":
            typ = node.child_by_field_name("type")
            if typ is None:
                return None
            name = src.text(typ).split("<", 1)[0].rsplit(".", 1)[-1]
            return CallParts(name, None, True, args)
        name = node.child_by_field_name("name")
        if name is None:
            return None
        obj = node.child_by_field_name("object")
        receiver = one_line(src.text(obj), 80) if obj is not None else None
        return CallParts(src.text(name), receiver, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        target = next(
            (c for c in node.named_children if c.type in ("scoped_identifier", "identifier")),
            None,
        )
        if target is None:
            return []
        full = src.text(target)
        if any(c.type == "asterisk" for c in node.named_children):
            return [ImportParts(full, "*", None)]
        return [ImportParts(full, full.rsplit(".", 1)[-1], None)]

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t in ("formal_parameter", "spread_parameter"):
            typ = node.child_by_field_name("type")
            name = node.child_by_field_name("name")
            if typ is not None and name is not None:
                return [Binding(src.text(name), _type_text(typ, src), "local")]
        elif t in ("local_variable_declaration", "field_declaration"):
            typ = node.child_by_field_name("type")
            if typ is None:
                return []
            scope = "field" if t == "field_declaration" else "local"
            out = []
            for i, child in enumerate(node.children):
                if node.field_name_for_child(i) != "declarator":
                    continue
                name = child.child_by_field_name("name")
                if name is None:
                    continue
                type_text = src.text(typ)
                if type_text == "var":
                    value = child.child_by_field_name("value")
                    if value is None or value.type != "object_creation_expression":
                        continue
                    type_text = _type_text(value.child_by_field_name("type"), src)
                out.append(Binding(src.text(name), type_text, scope))
            return out
        elif t == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None or left.type != "field_access":
                return []
            obj = left.child_by_field_name("object")
            field = left.child_by_field_name("field")
            if obj is None or field is None or src.text(obj) != "this":
                return []
            if right.type == "object_creation_expression":
                typ = right.child_by_field_name("type")
                return [Binding(src.text(field), _type_text(typ, src), "field")]
            if right.type == "identifier":
                return [Binding(src.text(field), "@var:" + src.text(right), "field")]
        return []

    def case_value(self, node: Node, src: Src) -> str | None:
        label = next((c for c in node.named_children if c.type == "switch_label"), None)
        if label is None:
            return None
        text = src.text(label).strip().rstrip(":").strip()
        if text == "default":
            return None
        if text.startswith("case "):
            text = text[5:]
        return one_line(text, 60)

    def catch_label(self, node: Node, src: Src) -> str:
        param = next((c for c in node.named_children if c.type == "catch_formal_parameter"), None)
        if param is None:
            return ""
        typ = next((c for c in param.named_children if c.type == "catch_type"), None)
        return one_line(src.text(typ), 60) if typ is not None else ""


HOOKS = Hooks(SPEC)
