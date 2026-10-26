"""C++ (gramática `cpp`). Reutiliza la lógica de C y añade clases, try/catch y `new`.

Verificado con debug-ast: un método definido fuera de la clase (`bool A::m()`) tiene
`declarator: qualified_identifier(scope, name)`; `std::cout << x` es una
`binary_expression`, no una llamada (se trata en el diagrama de flujo).
"""

from __future__ import annotations

from dataclasses import replace

from tree_sitter import Node

from desglosa.langs import c
from desglosa.langs.members import CppMembers
from desglosa.langs.spec import Src, one_line

SPEC = replace(
    c.SPEC,
    name="cpp",
    grammar="cpp",
    module_nodes=("namespace_definition",),
    class_nodes=("class_specifier", "struct_specifier", "union_specifier"),
    call_nodes=("call_expression", "new_expression"),
    loop_nodes=c.SPEC.loop_nodes + ("for_range_loop",),
    try_nodes=("try_statement",),
    catch_nodes=("catch_clause",),
    throw_nodes=("throw_statement",),
    self_names=("this",),
    implicit_this=True,
)


class Hooks(CppMembers, c.Hooks):
    def catch_label(self, node: Node, src: Src) -> str:
        params = node.child_by_field_name("parameters")
        if params is None:
            return ""
        decl = next(
            (ch for ch in params.named_children if ch.type == "parameter_declaration"), None
        )
        if decl is None:
            return "cualquier excepción" if "..." in src.text(params) else ""
        typ = decl.child_by_field_name("type")
        return one_line(src.text(typ), 60) if typ is not None else ""

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        clause = next((ch for ch in node.named_children if ch.type == "base_class_clause"), None)
        if clause is None:
            return ()
        return tuple(
            src.text(ch).split("<", 1)[0].rsplit("::", 1)[-1]
            for ch in clause.named_children
            if ch.type in ("type_identifier", "qualified_identifier", "template_type")
        )


HOOKS = Hooks(SPEC)
