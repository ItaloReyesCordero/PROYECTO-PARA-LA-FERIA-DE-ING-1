"""Python (gramática `python`).

Nota verificada con debug-ast: esta versión de la gramática NO envuelve las sentencias
en `expression_statement`; `assignment`, `call` o `string` aparecen directamente en `block`.
"""

from __future__ import annotations

import re

from tree_sitter import Node

from desglosa.langs.members import PythonMembers
from desglosa.langs.spec import Binding, ImportParts, LangHooks, LangSpec, Src, one_line

SPEC = LangSpec(
    name="python",
    grammar="python",
    class_nodes=("class_definition",),
    function_nodes=("function_definition",),
    import_nodes=("import_statement", "import_from_statement"),
    call_nodes=("call",),
    if_nodes=("if_statement",),
    elif_nodes=("elif_clause",),
    else_nodes=("else_clause",),
    loop_nodes=("for_statement", "while_statement"),
    switch_nodes=("match_statement",),
    case_nodes=("case_clause",),
    try_nodes=("try_statement",),
    catch_nodes=("except_clause", "except_group_clause"),
    finally_nodes=("finally_clause",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    throw_nodes=("raise_statement",),
    block_nodes=("block",),
    comment_nodes=("comment",),
    self_names=("self", "cls"),
    parent_names=("super()", "super"),
    constructor_names=("__init__",),
)

_MAIN_GUARD = re.compile(
    r"""^__name__\s*==\s*['"]__main__['"]$|^['"]__main__['"]\s*==\s*__name__$"""
)


def _docstring_node(block: Node | None) -> Node | None:
    if block is None or block.named_child_count == 0:
        return None
    first = block.named_children[0]
    if first.type == "expression_statement" and first.named_child_count == 1:
        first = first.named_children[0]
    return first if first.type == "string" else None


def _string_literal_value(node: Node, src: Src) -> str:
    parts = [src.text(c) for c in node.named_children if c.type == "string_content"]
    if parts:
        return "".join(parts)
    text = src.text(node)
    return text.strip("\"'rbuRBUfF")


class Hooks(PythonMembers, LangHooks):
    def doc(self, node: Node, src: Src) -> str | None:
        target = node.child_by_field_name("body") if node.type != "module" else node
        string = _docstring_node(target)
        if string is None:
            return super().doc(node, src)
        lines = [ln.strip() for ln in _string_literal_value(string, src).strip().splitlines()]
        return "\n".join(lines).strip() or None

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        sup = node.child_by_field_name("superclasses")
        if sup is None:
            return ()
        return tuple(
            src.text(c).rsplit(".", 1)[-1]
            for c in sup.named_children
            if c.type in ("identifier", "attribute")
        )

    def is_main_guard(self, node: Node, src: Src) -> bool:
        if node.type != "if_statement":
            return False
        return bool(_MAIN_GUARD.match(self.condition(node, src)))

    def condition_node(self, node: Node) -> Node | None:
        if node.type == "match_statement":
            return node.child_by_field_name("subject")
        return node.child_by_field_name("condition")

    def case_value(self, node: Node, src: Src) -> str | None:
        pattern = next((c for c in node.named_children if c.type == "case_pattern"), None)
        text = src.text(pattern).strip() if pattern is not None else ""
        return None if text in ("", "_") else one_line(text, 60)

    def catch_label(self, node: Node, src: Src) -> str:
        value = node.child_by_field_name("value")
        if value is None:
            value = next((c for c in node.named_children if c.type != "block"), None)
        text = src.text(value) if value is not None else ""
        return one_line(text.split(" as ")[0], 60)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        out: list[ImportParts] = []
        if node.type == "import_statement":
            for i, child in enumerate(node.children):
                if node.field_name_for_child(i) != "name":
                    continue
                if child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    out.append(ImportParts(src.text(name), None, src.text(alias)))
                else:
                    out.append(ImportParts(src.text(child), None, None))
            return out
        module = node.child_by_field_name("module_name")
        mod_text = src.text(module)
        for i, child in enumerate(node.children):
            if child.type == "wildcard_import":
                out.append(ImportParts(mod_text, "*", None))
            elif node.field_name_for_child(i) == "name":
                if child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    out.append(ImportParts(mod_text, src.text(name), src.text(alias)))
                else:
                    out.append(ImportParts(mod_text, src.text(child), None))
        return out

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "typed_parameter":
            name = next((c for c in node.named_children if c.type == "identifier"), None)
            typ = node.child_by_field_name("type")
            if name is not None and typ is not None:
                return [Binding(src.text(name), src.text(typ), "local")]
        elif t == "typed_default_parameter":
            name = node.child_by_field_name("name")
            typ = node.child_by_field_name("type")
            if name is not None and typ is not None:
                return [Binding(src.text(name), src.text(typ), "local")]
        elif t == "assignment":
            return self._assignment(node, src)
        return []

    def _assignment(self, node: Node, src: Src) -> list[Binding]:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        typ_node = node.child_by_field_name("type")
        if left is None:
            return []
        typ: str | None = None
        if typ_node is not None:
            typ = src.text(typ_node)
        elif right is not None and right.type == "call":
            fn = right.child_by_field_name("function")
            if fn is not None and fn.type in ("identifier", "attribute"):
                typ = src.text(fn).rsplit(".", 1)[-1]
        elif right is not None and right.type == "identifier":
            typ = "@var:" + src.text(right)
        if not typ:
            return []
        if left.type == "identifier":
            return [Binding(src.text(left), typ, "local")]
        if left.type == "attribute":
            obj = left.child_by_field_name("object")
            attr = left.child_by_field_name("attribute")
            if obj is not None and attr is not None and src.text(obj) in ("self", "cls"):
                return [Binding(src.text(attr), typ, "field")]
        return []


HOOKS = Hooks(SPEC)
