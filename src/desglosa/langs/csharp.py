"""C# (gramática `csharp`). Agregado en el Bloque 2.

Verificado con debug-ast (ver docs/ADDING_A_LANGUAGE.md):
- llamadas: `invocation_expression` con campo `function`; el acceso a miembro es
  `member_access_expression` con campos `expression` y `name` (no `object`/`field`);
- `new X()`: `object_creation_expression` con campo `type`;
- `foreach (T x in xs)`: `foreach_statement` con campos `type`, `left` y `right`;
- `switch`: `switch_statement` con campo `value` y cuerpo `switch_body` de
  `switch_section`; el valor de un caso es un `constant_pattern` (sin campo) y
  `default:` no tiene patrón;
- `catch (Tipo e)`: `catch_clause` → `catch_declaration` (campos `type`, `name`);
- herencia e interfaces: `base_list`; modificadores: nodos `modifier`;
- comentarios: `comment` (los de documentación son `/// <summary>…</summary>`).
"""

from __future__ import annotations

import re

from tree_sitter import Node

from desglosa.langs.spec import (
    Binding,
    CallParts,
    ImportParts,
    LangHooks,
    LangSpec,
    LoopInfo,
    Src,
    one_line,
    strip_parens,
)

SPEC = LangSpec(
    name="csharp",
    grammar="csharp",
    class_nodes=(
        "class_declaration",
        "struct_declaration",
        "record_declaration",
        "enum_declaration",
    ),
    interface_nodes=("interface_declaration",),
    method_nodes=(
        "method_declaration",
        "constructor_declaration",
        "local_function_statement",
    ),
    import_nodes=("using_directive",),
    call_nodes=("invocation_expression", "object_creation_expression"),
    if_nodes=("if_statement",),
    loop_nodes=("for_statement", "foreach_statement", "while_statement"),
    do_while_nodes=("do_statement",),
    switch_nodes=("switch_statement",),
    case_nodes=("switch_section",),
    try_nodes=("try_statement",),
    catch_nodes=("catch_clause",),
    finally_nodes=("finally_clause",),
    return_nodes=("return_statement",),
    break_nodes=("break_statement",),
    continue_nodes=("continue_statement",),
    throw_nodes=("throw_statement",),
    block_nodes=("block",),
    comment_nodes=("comment",),
    self_names=("this",),
    parent_names=("base",),
    implicit_this=True,
    goto_nodes=("goto_statement",),
    label_nodes=("labeled_statement",),
)

_XML_TAG = re.compile(r"<[^>]+>")
_PATTERNS = ("constant_pattern", "declaration_pattern", "type_pattern", "recursive_pattern",
             "relational_pattern", "or_pattern", "and_pattern", "not_pattern", "var_pattern",
             "discard")


def _last_name(text: str) -> str:
    """`System.Collections.Generic.List<int>` → `List`."""
    return text.split("<", 1)[0].rsplit(".", 1)[-1].strip()


class Hooks(LangHooks):
    # En C# un `case` sin `break` es un error de compilación: no hay caída al siguiente.
    fallthrough = False

    def is_static(self, node: Node, src: Src) -> bool:
        return any(c.type == "modifier" and src.text(c) == "static" for c in node.children)

    def class_bases(self, node: Node, src: Src) -> tuple[str, ...]:
        bases = next((c for c in node.named_children if c.type == "base_list"), None)
        if bases is None:
            return ()
        out = []
        for child in bases.named_children:
            if child.type in ("identifier", "qualified_name", "generic_name"):
                out.append(_last_name(src.text(child)))
        return tuple(out)

    def doc(self, node: Node, src: Src) -> str | None:
        text = super().doc(node, src)
        if text is None:
            return None
        # `/// <summary>Calcula…</summary>` → "Calcula…"
        clean = "\n".join(
            line.strip() for line in _XML_TAG.sub("", text).splitlines() if line.strip()
        )
        return clean or None

    def call_parts(self, node: Node, src: Src) -> CallParts | None:
        args = self.call_args(node, src)
        if node.type == "object_creation_expression":
            typ = node.child_by_field_name("type")
            if typ is None:
                return None
            return CallParts(_last_name(src.text(typ)), None, True, args)
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type == "member_access_expression":
            name = fn.child_by_field_name("name")
            obj = fn.child_by_field_name("expression")
            if name is None:
                return None
            receiver = one_line(src.text(obj), 80) if obj is not None else None
            return CallParts(_last_name(src.text(name)), receiver, False, args)
        if fn.type in ("identifier", "generic_name"):
            return CallParts(_last_name(src.text(fn)), None, False, args)
        return CallParts(one_line(src.text(fn), 60), None, False, args)

    def imports(self, node: Node, src: Src) -> list[ImportParts]:
        # `using System.IO;` · `using Alias = Espacio.Clase;` · `using static X;`
        named = [c for c in node.named_children if c.type in ("identifier", "qualified_name")]
        if not named:
            return []
        alias = None
        name_field = node.child_by_field_name("name")
        if name_field is not None and len(named) > 1:
            alias = src.text(name_field)
            target = named[-1]
        else:
            target = named[0]
        full = src.text(target)
        return [ImportParts(full, None, alias)]

    def bindings(self, node: Node, src: Src) -> list[Binding]:
        t = node.type
        if t == "parameter":
            typ = node.child_by_field_name("type")
            name = node.child_by_field_name("name")
            if typ is not None and name is not None:
                return [Binding(src.text(name), _last_name(src.text(typ)), "local")]
        elif t == "variable_declaration":
            scope = "field" if node.parent is not None and node.parent.type == (
                "field_declaration"
            ) else "local"
            typ = node.child_by_field_name("type")
            if typ is None:
                return []
            out = []
            for decl in (c for c in node.named_children if c.type == "variable_declarator"):
                name = decl.child_by_field_name("name")
                if name is None:
                    continue
                type_text = src.text(typ)
                if typ.type == "implicit_type":  # var x = new Tipo();
                    value = next(
                        (c for c in decl.named_children if c.type == "object_creation_expression"),
                        None,
                    )
                    if value is None:
                        continue
                    type_text = src.text(value.child_by_field_name("type"))
                out.append(Binding(src.text(name), _last_name(type_text), scope))
            return out
        elif t == "property_declaration":
            typ = node.child_by_field_name("type")
            name = node.child_by_field_name("name")
            if typ is not None and name is not None:
                return [Binding(src.text(name), _last_name(src.text(typ)), "field")]
        elif t == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None or left.type != "member_access_expression":
                return []
            obj = left.child_by_field_name("expression")
            field = left.child_by_field_name("name")
            if obj is None or field is None or src.text(obj) != "this":
                return []
            if right.type == "object_creation_expression":
                typ = right.child_by_field_name("type")
                return [Binding(src.text(field), _last_name(src.text(typ)), "field")]
            if right.type == "identifier":
                return [Binding(src.text(field), "@var:" + src.text(right), "field")]
        return []

    # ---------------------------------------------------------------- forma del AST

    def condition_node(self, node: Node) -> Node | None:
        # El `switch` guarda su expresión en `value`.
        return node.child_by_field_name("condition") or node.child_by_field_name("value")

    def loop_info(self, node: Node, src: Src) -> LoopInfo:
        if node.type == "foreach_statement":
            var = node.child_by_field_name("left")
            coll = node.child_by_field_name("right")
            return LoopInfo(
                "foreach",
                self.body_statements(node.child_by_field_name("body")),
                var_text=src.text(var) if var is not None else "",
                coll_node=coll,
                coll_text=src.text(coll) if coll is not None else "",
                header=self.loop_label(node, src),
            )
        return super().loop_info(node, src)

    def case_value(self, node: Node, src: Src) -> str | None:
        pattern = next((c for c in node.named_children if c.type in _PATTERNS), None)
        if pattern is None:
            return None  # default:
        return one_line(strip_parens(src.text(pattern)), 60)

    def case_statements(self, case: Node) -> list[Node]:
        return [
            c
            for c in case.named_children
            if c.type not in _PATTERNS
            and c.type not in self.spec.comment_nodes
            and c.type != "when_clause"
        ]

    def catch_label(self, node: Node, src: Src) -> str:
        decl = next((c for c in node.named_children if c.type == "catch_declaration"), None)
        if decl is None:
            return ""
        typ = decl.child_by_field_name("type")
        return one_line(src.text(typ), 60) if typ is not None else ""


HOOKS = Hooks(SPEC)
