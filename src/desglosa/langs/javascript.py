"""JavaScript (gramática `javascript`)."""

from __future__ import annotations

from tree_sitter import Node

from desglosa.langs.members import JsMembers
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
    name="javascript",
    grammar="javascript",
    class_nodes=("class_declaration", "class"),
    function_nodes=(
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "generator_function",
        "arrow_function",
    ),
    method_nodes=("method_definition",),
    import_nodes=("import_statement",),
    call_nodes=("call_expression", "new_expression"),
    if_nodes=("if_statement",),
    else_nodes=("else_clause",),
    loop_nodes=("for_statement", "for_in_statement", "while_statement"),
    do_while_nodes=("do_statement",),
    switch_nodes=("switch_statement",),
    case_nodes=("switch_case", "switch_default"),
    try_nodes=("try_statement",),
    catch_nodes=("catch_clause",),
    finally_nodes=("finally_clause",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    throw_nodes=("throw_statement",),
    block_nodes=("statement_block",),
    comment_nodes=("comment",),
    self_names=("this",),
    parent_names=("super",),
    constructor_names=("constructor",),
)


def _string_value(node: Node | None, src: Src) -> str:
    if node is None:
        return ""
    frag = [src.text(c) for c in node.named_children if c.type == "string_fragment"]
    return "".join(frag) if frag else src.text(node).strip("\"'`")


class Hooks(JsMembers, LangHooks):
    fallthrough = True

    def symbol_name(self, node: Node, src: Src) -> str | None:
        name = node.child_by_field_name("name")
        if name is not None:
            return src.text(name)
        parent = node.parent
        if parent is None:
            return None
        if parent.type == "variable_declarator":
            target = parent.child_by_field_name("name")
            return src.text(target) if target is not None and target.type == "identifier" else None
        if parent.type in ("assignment_expression", "augmented_assignment_expression"):
            left = parent.child_by_field_name("left")
            if left is None:
                return None
            if left.type == "member_expression":
                prop = left.child_by_field_name("property")
                return src.text(prop) if prop is not None else None
            return src.text(left) if left.type == "identifier" else None
        if parent.type == "pair":
            key = parent.child_by_field_name("key")
            return _string_value(key, src) if key is not None else None
        if parent.type in ("public_field_definition", "field_definition"):
            prop = parent.child_by_field_name("name") or parent.child_by_field_name("property")
            return src.text(prop) if prop is not None else None
        return None

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        heritage = next((c for c in node.named_children if c.type == "class_heritage"), None)
        if heritage is None:
            return ()
        names: list[str] = []

        def collect(n: Node) -> None:
            for c in n.named_children:
                if c.type in ("identifier", "type_identifier"):
                    names.append(src.text(c))
                elif c.type == "member_expression":
                    prop = c.child_by_field_name("property")
                    if prop is not None:
                        names.append(src.text(prop))
                elif c.type in ("extends_clause", "implements_clause", "generic_type"):
                    collect(c)

        collect(heritage)
        return tuple(names)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        args = self.call_args(node, src)
        if node.type == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor is None:
                return None
            if ctor.type == "member_expression":
                prop = ctor.child_by_field_name("property")
                obj = ctor.child_by_field_name("object")
                return CallParts(src.text(prop), one_line(src.text(obj), 80), True, args)
            return CallParts(src.text(ctor), None, True, args)
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type in ("identifier", "super"):
            return CallParts(src.text(fn), None, False, args)
        if fn.type == "member_expression":
            obj = fn.child_by_field_name("object")
            prop = fn.child_by_field_name("property")
            if obj is not None and prop is not None:
                return CallParts(src.text(prop), one_line(src.text(obj), 80), False, args)
        if fn.type == "import":
            return None
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def call_import(self, node: Node, src: Src) -> ImportParts | None:
        """`const fs = require("fs")` se registra como import, no como llamada."""
        if node.type != "call_expression":
            return None
        fn = node.child_by_field_name("function")
        args = node.child_by_field_name("arguments")
        if fn is None or src.text(fn) != "require" or args is None:
            return None
        strings = [a for a in args.named_children if a.type == "string"]
        if len(strings) != 1:
            return None
        alias = None
        parent = node.parent
        if parent is not None and parent.type == "variable_declarator":
            target = parent.child_by_field_name("name")
            if target is not None and target.type == "identifier":
                alias = src.text(target)
        return ImportParts(_string_value(strings[0], src), None, alias)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        module = _string_value(node.child_by_field_name("source"), src)
        clause = next((c for c in node.named_children if c.type == "import_clause"), None)
        if clause is None:
            return [ImportParts(module, None, None)]
        out: list[ImportParts] = []
        for child in clause.named_children:
            if child.type == "identifier":
                out.append(ImportParts(module, "default", src.text(child)))
            elif child.type == "namespace_import":
                ident = next((c for c in child.named_children if c.type == "identifier"), None)
                out.append(ImportParts(module, "*", src.text(ident) if ident else None))
            elif child.type == "named_imports":
                for spec in child.named_children:
                    if spec.type != "import_specifier":
                        continue
                    name = spec.child_by_field_name("name")
                    alias = spec.child_by_field_name("alias")
                    out.append(
                        ImportParts(module, src.text(name), src.text(alias) if alias else None)
                    )
        return out

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "variable_declarator":
            name = node.child_by_field_name("name")
            if name is None or name.type != "identifier":
                return []
            typ = node.child_by_field_name("type")
            if typ is not None:
                return [Binding(src.text(name), src.text(typ).lstrip(": "), "local")]
            value = node.child_by_field_name("value")
            ctor = self._ctor_name(value, src)
            if ctor:
                return [Binding(src.text(name), ctor, "local")]
        elif t == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None or left.type != "member_expression":
                return []
            obj = left.child_by_field_name("object")
            prop = left.child_by_field_name("property")
            if obj is None or prop is None or src.text(obj) != "this":
                return []
            ctor = self._ctor_name(right, src)
            if ctor:
                return [Binding(src.text(prop), ctor, "field")]
            if right.type == "identifier":
                return [Binding(src.text(prop), "@var:" + src.text(right), "field")]
        elif t in ("required_parameter", "optional_parameter"):
            pattern = node.child_by_field_name("pattern")
            typ = node.child_by_field_name("type")
            if pattern is None or typ is None or pattern.type != "identifier":
                return []
            type_text = src.text(typ).lstrip(": ")
            out = [Binding(src.text(pattern), type_text, "local")]
            if any(c.type == "accessibility_modifier" for c in node.named_children):
                out.append(Binding(src.text(pattern), type_text, "field"))
            return out
        elif t in ("public_field_definition", "field_definition"):
            name = node.child_by_field_name("name") or node.child_by_field_name("property")
            if name is None:
                return []
            typ = node.child_by_field_name("type")
            if typ is not None:
                return [Binding(src.text(name), src.text(typ).lstrip(": "), "field")]
            ctor = self._ctor_name(node.child_by_field_name("value"), src)
            if ctor:
                return [Binding(src.text(name), ctor, "field")]
        return []

    @staticmethod
    def _ctor_name(value: Node | None, src: Src) -> str | None:
        if value is None or value.type != "new_expression":
            return None
        ctor = value.child_by_field_name("constructor")
        if ctor is None:
            return None
        if ctor.type == "member_expression":
            prop = ctor.child_by_field_name("property")
            return src.text(prop) if prop is not None else None
        return src.text(ctor)

    def condition_node(self, node: Node) -> Node | None:
        if node.type == "switch_statement":
            return node.child_by_field_name("value")
        return node.child_by_field_name("condition")

    def catch_label(self, node: Node, src: Src) -> str:
        # `catch (e)` solo nombra la variable, no el tipo de excepción.
        return ""


HOOKS = Hooks(SPEC)
