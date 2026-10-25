"""C (gramática `c`).

Verificado con debug-ast: el nombre de una función está en
`declarator: function_declarator > declarator: identifier`; el `default` de un switch es
un `case_statement` sin campo `value`; `goto_statement` y `labeled_statement` existen.
"""

from __future__ import annotations

from tree_sitter import Node

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
    name="c",
    grammar="c",
    class_nodes=("struct_specifier", "union_specifier"),
    function_nodes=("function_definition",),
    import_nodes=("preproc_include",),
    call_nodes=("call_expression",),
    if_nodes=("if_statement",),
    else_nodes=("else_clause",),
    loop_nodes=("for_statement", "while_statement"),
    do_while_nodes=("do_statement",),
    switch_nodes=("switch_statement",),
    case_nodes=("case_statement",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    block_nodes=("compound_statement",),
    comment_nodes=("comment",),
    goto_nodes=("goto_statement",),
    label_nodes=("labeled_statement",),
)

_WRAPPERS = (
    "pointer_declarator",
    "reference_declarator",
    "parenthesized_declarator",
    "attributed_declarator",
    "array_declarator",
    "init_declarator",
)


def function_declarator(node: Node) -> Node | None:
    d = node.child_by_field_name("declarator")
    while d is not None and d.type != "function_declarator":
        if d.type not in _WRAPPERS:
            return None
        nxt = d.child_by_field_name("declarator")
        if nxt is None:
            nxt = next((c for c in d.named_children if c.type.endswith("declarator")), None)
        d = nxt
    return d


def declarator_name(node: Node | None) -> Node | None:
    """Identificador más interno de un declarator (`*p`, `&r`, `a[3]`, `x = 1`)."""
    d = node
    while d is not None and d.type in _WRAPPERS:
        nxt = d.child_by_field_name("declarator")
        if nxt is None:
            nxt = next(
                (
                    c
                    for c in d.named_children
                    if c.type.endswith("declarator") or c.type in ("identifier", "field_identifier")
                ),
                None,
            )
        d = nxt
    return d


class Hooks(LangHooks):
    fallthrough = True

    def _name_node(self, node: Node) -> Node | None:
        fd = function_declarator(node)
        return fd.child_by_field_name("declarator") if fd is not None else None

    def symbol_name(self, node: Node, src: Src) -> str | None:
        if node.type in self.spec.class_nodes:
            name = node.child_by_field_name("name")
            if name is not None:
                return src.text(name)
            parent = node.parent
            if parent is not None and parent.type == "type_definition":
                decl = parent.child_by_field_name("declarator")
                return src.text(decl) if decl is not None else None
            return None
        target = self._name_node(node)
        if target is None:
            return None
        if target.type == "qualified_identifier":
            inner = target
            while inner.type == "qualified_identifier":
                nxt = inner.child_by_field_name("name")
                if nxt is None:
                    break
                inner = nxt
            if inner.type == "template_function":
                inner = inner.child_by_field_name("name") or inner
            return src.text(inner)
        if target.type == "template_function":
            name = target.child_by_field_name("name")
            return src.text(name) if name is not None else src.text(target)
        return src.text(target)

    def symbol_qualifier(self, node: Node, src: Src) -> str | None:
        target = self._name_node(node)
        if target is None or target.type != "qualified_identifier":
            return None
        scope = target.child_by_field_name("scope")
        if scope is None:
            return None
        return src.text(scope).rsplit("::", 1)[-1].split("<", 1)[0]

    def is_definition(self, node: Node) -> bool:
        if node.type in self.spec.class_nodes:
            return node.child_by_field_name("body") is not None
        return True

    def signature(self, node: Node, src: Src) -> str:
        if node.type in self.spec.class_nodes:
            body = node.child_by_field_name("body")
            end = body.start_byte if body is not None else node.end_byte
            return one_line(src.between(node.start_byte, end), 120)
        return super().signature(node, src)

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        args = self.call_args(node, src)
        if node.type == "new_expression":
            typ = node.child_by_field_name("type")
            if typ is None:
                return None
            return CallParts(src.text(typ).split("<", 1)[0].rsplit("::", 1)[-1], None, True, args)
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type == "identifier":
            return CallParts(src.text(fn), None, False, args)
        if fn.type == "field_expression":
            obj = fn.child_by_field_name("argument")
            field = fn.child_by_field_name("field")
            if obj is not None and field is not None:
                return CallParts(src.text(field), one_line(src.text(obj), 80), False, args)
        if fn.type == "qualified_identifier":
            text = src.text(fn)
            scope, _, name = text.rpartition("::")
            name = name.split("<", 1)[0]
            return CallParts(name, scope or None, False, args)
        if fn.type == "template_function":
            name = fn.child_by_field_name("name")
            return CallParts(src.text(name) if name else src.text(fn), None, False, args)
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        path = node.child_by_field_name("path")
        if path is None:
            return []
        if path.type == "string_literal":
            content = "".join(src.text(c) for c in path.named_children)
            return [ImportParts(content or src.text(path).strip('"'), None, None)]
        return [ImportParts(src.text(path), None, None)]

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t not in ("parameter_declaration", "declaration", "field_declaration"):
            return []
        typ = node.child_by_field_name("type")
        if typ is None:
            return []
        type_text = src.text(typ)
        scope = "field" if t == "field_declaration" else "local"
        out = []
        for i, child in enumerate(node.children):
            if node.field_name_for_child(i) != "declarator":
                continue
            if child.type == "function_declarator":
                continue
            name = declarator_name(child)
            if name is None or name.type not in ("identifier", "field_identifier"):
                continue
            this_type = type_text
            if type_text in ("auto", "auto*") and child.type == "init_declarator":
                value = child.child_by_field_name("value")
                if value is not None and value.type == "new_expression":
                    vt = value.child_by_field_name("type")
                    this_type = src.text(vt) if vt is not None else type_text
            out.append(Binding(src.text(name), this_type, scope))
        return out

    def case_value(self, node: Node, src: Src) -> str | None:
        value = node.child_by_field_name("value")
        return one_line(src.text(value), 60) if value is not None else None


HOOKS = Hooks(SPEC)
