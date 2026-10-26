"""PHP (gramática `php`, que exige la etiqueta `<?php`).

Verificado con debug-ast: `if_statement` usa el campo `body` (no `consequence`) y
`else_if_clause` / `else_clause` son hermanos dentro del `if`, no anidados.
"""

from __future__ import annotations

from tree_sitter import Node

from desglosa.langs.members import PhpMembers
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
    name="php",
    grammar="php",
    module_nodes=("namespace_definition",),
    class_nodes=("class_declaration", "trait_declaration", "enum_declaration"),
    interface_nodes=("interface_declaration",),
    function_nodes=("function_definition",),
    method_nodes=("method_declaration",),
    import_nodes=(
        "namespace_use_declaration",
        "require_expression",
        "require_once_expression",
        "include_expression",
        "include_once_expression",
    ),
    call_nodes=(
        "function_call_expression",
        "member_call_expression",
        "nullsafe_member_call_expression",
        "scoped_call_expression",
        "object_creation_expression",
    ),
    if_nodes=("if_statement",),
    elif_nodes=("else_if_clause",),
    else_nodes=("else_clause",),
    loop_nodes=("for_statement", "foreach_statement", "while_statement"),
    do_while_nodes=("do_statement",),
    switch_nodes=("switch_statement",),
    case_nodes=("case_statement", "default_statement"),
    try_nodes=("try_statement",),
    catch_nodes=("catch_clause",),
    finally_nodes=("finally_clause",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    throw_nodes=("throw_expression",),
    block_nodes=("compound_statement",),
    comment_nodes=("comment",),
    self_names=("$this", "self", "static"),
    parent_names=("parent",),
    constructor_names=("__construct",),
)

_NAME_TYPES = ("name", "qualified_name", "relative_name")


def _last_segment(text: str) -> str:
    return text.strip().lstrip("\\").rsplit("\\", 1)[-1]


def _var(text: str) -> str:
    return text.lstrip("$")


class Hooks(PhpMembers, LangHooks):
    fallthrough = True

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        out: list[str] = []
        for child in node.named_children:
            if child.type in ("base_clause", "class_interface_clause"):
                out.extend(
                    _last_segment(src.text(c))
                    for c in child.named_children
                    if c.type in _NAME_TYPES
                )
        return tuple(out)

    def call_args(self, node: Node, src: Src) -> tuple[str, ...]:
        args = node.child_by_field_name("arguments")
        if args is None:
            args = next((c for c in node.named_children if c.type == "arguments"), None)
        if args is None:
            return ()
        return tuple(one_line(src.text(a), 60) for a in args.named_children)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        t = node.type
        args = self.call_args(node, src)
        if t == "function_call_expression":
            fn = node.child_by_field_name("function")
            if fn is None:
                return None
            if fn.type in _NAME_TYPES:
                return CallParts(_last_segment(src.text(fn)), None, False, args)
            return CallParts(one_line(src.text(fn), 60), None, False, args)
        if t in ("member_call_expression", "nullsafe_member_call_expression"):
            obj = node.child_by_field_name("object")
            name = node.child_by_field_name("name")
            if obj is None or name is None:
                return None
            return CallParts(src.text(name), one_line(src.text(obj), 80), False, args)
        if t == "scoped_call_expression":
            scope = node.child_by_field_name("scope")
            name = node.child_by_field_name("name")
            if scope is None or name is None:
                return None
            return CallParts(src.text(name), _last_segment(src.text(scope)), False, args)
        if t == "object_creation_expression":
            cls = next((c for c in node.named_children if c.type in _NAME_TYPES), None)
            if cls is None:
                return None
            return CallParts(_last_segment(src.text(cls)), None, True, args)
        return None

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        if node.type == "namespace_use_declaration":
            out: list[ImportParts] = []
            for clause in node.named_children:
                if clause.type != "namespace_use_clause":
                    continue
                target = next((c for c in clause.named_children if c.type in _NAME_TYPES), None)
                if target is None:
                    continue
                alias = clause.child_by_field_name("alias")
                full = src.text(target).lstrip("\\")
                out.append(
                    ImportParts(full, _last_segment(full), src.text(alias) if alias else None)
                )
            return out
        # require / include: guardamos la expresión de la ruta tal cual.
        arg = node.named_children[-1] if node.named_child_count else None
        return [ImportParts(one_line(src.text(arg), 120), None, None)] if arg else []

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t in ("simple_parameter", "property_promotion_parameter"):
            typ = node.child_by_field_name("type")
            name = node.child_by_field_name("name")
            if typ is None or name is None:
                return []
            out = [Binding(_var(src.text(name)), src.text(typ), "local")]
            if t == "property_promotion_parameter":
                out.append(Binding(_var(src.text(name)), src.text(typ), "field"))
            return out
        if t == "property_declaration":
            typ = node.child_by_field_name("type")
            if typ is None:
                return []
            out = []
            for el in node.named_children:
                if el.type == "property_element":
                    name = el.child_by_field_name("name")
                    if name is not None:
                        out.append(Binding(_var(src.text(name)), src.text(typ), "field"))
            return out
        if t == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                return []
            typ = None
            if right.type == "object_creation_expression":
                cls = next((c for c in right.named_children if c.type in _NAME_TYPES), None)
                typ = _last_segment(src.text(cls)) if cls is not None else None
            elif right.type == "variable_name":
                typ = "@var:" + _var(src.text(right))
            if not typ:
                return []
            if left.type == "variable_name":
                return [Binding(_var(src.text(left)), typ, "local")]
            if left.type == "member_access_expression":
                obj = left.child_by_field_name("object")
                name = left.child_by_field_name("name")
                if obj is not None and name is not None and src.text(obj) == "$this":
                    return [Binding(src.text(name), typ, "field")]
        return []

    def case_value(self, node: Node, src: Src) -> str | None:
        if node.type == "default_statement":
            return None
        return super().case_value(node, src)

    def catch_label(self, node: Node, src: Src) -> str:
        typ = node.child_by_field_name("type")
        if typ is None:
            return ""
        return one_line(" | ".join(_last_segment(p) for p in src.text(typ).split("|")), 60)


HOOKS = Hooks(SPEC)
