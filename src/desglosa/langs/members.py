"""Atributos y datos de métodos para el diagrama de clases (Bloque 4).

Un *mixin* por lenguaje: cada `Hooks` lo agrega a su herencia (`class Hooks(JavaMembers,
LangHooks)`). Los nombres de nodo salen de `desglosa debug-ast` sobre
`tests/fixtures/uml/<lenguaje>/` (ver docs/ADDING_A_LANGUAGE.md).

Visibilidad UML: `+` público, `-` privado, `#` protegido, `~` paquete o interno. Cuando
el lenguaje no la escribe se usa la de su regla: Java sin modificador es de paquete, en C#
es privado, en Python se deduce del nombre (`_x`, `__x`), en Go de la mayúscula inicial.
"""

from __future__ import annotations

from tree_sitter import Node

from desglosa.ir import DeclaredMethod, Member, MethodInfo
from desglosa.langs.spec import (
    Src,
    modifier_words,
    name_visibility,
    type_text,
    visibility_of,
)


def _line(node: Node) -> int:
    return node.start_point[0] + 1


def _first(node: Node | None, *types: str) -> Node | None:
    if node is None:
        return None
    return next((c for c in node.named_children if c.type in types), None)


def _walk_body(node: Node | None, stop: tuple[str, ...]):
    """Nodos de un cuerpo de función sin entrar a funciones o clases anidadas."""
    if node is None:
        return
    stack = list(reversed(node.named_children))
    while stack:
        cur = stack.pop()
        yield cur
        if cur.type in stop:
            continue
        stack.extend(reversed(cur.named_children))


# --------------------------------------------------------------------------- Java


class JavaMembers:
    default_visibility = "~"  # sin modificador: visible en el paquete

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        iface = node.type == "interface_declaration"
        out = []
        for c in body.named_children:
            if c.type not in ("field_declaration", "constant_declaration"):
                continue
            words = modifier_words(c, src)
            typ = type_text(c.child_by_field_name("type"), src)
            vis = visibility_of(words, "+" if iface else "~")
            for d in c.children_by_field_name("declarator"):
                name = d.child_by_field_name("name")
                if name is not None:
                    out.append(Member(src.text(name), typ, vis, "static" in words or iface,
                                      _line(c)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        info = super().method_info(node, src)  # type: ignore[misc]
        if node.parent is not None and node.parent.type == "interface_body":
            # En una interfaz todo es público; sin cuerpo, abstracto.
            vis = info.visibility if info.visibility != "~" else "+"
            return MethodInfo(vis, info.static, info.abstract or not self.has_body(node),  # type: ignore[attr-defined]
                              info.returns)
        return info


# --------------------------------------------------------------------------- C#


class CSharpMembers:
    default_visibility = "-"  # sin modificador, un miembro de clase es privado

    def _in_interface(self, node: Node) -> bool:
        body = node.parent
        return body is not None and body.parent is not None and (
            body.parent.type == "interface_declaration"
        )

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        default = "+" if node.type == "interface_declaration" else "-"
        out = []
        for c in body.named_children:
            words = modifier_words(c, src)
            static = "static" in words or "const" in words
            if c.type == "field_declaration":
                decl = _first(c, "variable_declaration")
                if decl is None:
                    continue
                typ = type_text(decl.child_by_field_name("type"), src)
                for v in decl.named_children:
                    is_var = v.type == "variable_declarator"
                    name = v.child_by_field_name("name") if is_var else None
                    if name is not None:
                        out.append(Member(src.text(name), typ, visibility_of(words, default),
                                          static, _line(c)))
            elif c.type == "property_declaration":
                name = c.child_by_field_name("name")
                if name is not None:
                    out.append(Member(src.text(name), type_text(c.child_by_field_name("type"), src),
                                      visibility_of(words, default), static, _line(c)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        info = super().method_info(node, src)  # type: ignore[misc]
        if self._in_interface(node):
            vis = info.visibility if "private" not in modifier_words(node, src) else "-"
            return MethodInfo(vis if vis != "-" else "+", info.static, True, info.returns)
        return info


# --------------------------------------------------------------------------- PHP


class PhpMembers:
    default_visibility = "+"

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        out = []
        for c in body.named_children:
            if c.type == "method_declaration":
                out.extend(self._promoted(c, src))
                continue
            if c.type != "property_declaration":
                continue
            words = modifier_words(c, src)
            typ = type_text(c.child_by_field_name("type"), src)
            for el in c.named_children:
                if el.type != "property_element":
                    continue
                name = el.child_by_field_name("name")
                if name is not None:
                    out.append(Member(src.text(name).lstrip("$"), typ, visibility_of(words, "+"),
                                      "static" in words, _line(c)))
        return out

    @staticmethod
    def _promoted(method: Node, src: Src) -> list[Member]:
        """`__construct(private Servicio $s)` declara el atributo `s` (PHP 8)."""
        name = method.child_by_field_name("name")
        params = method.child_by_field_name("parameters")
        if name is None or src.text(name) != "__construct" or params is None:
            return []
        out = []
        for p in params.named_children:
            pname = p.child_by_field_name("name")
            if p.type != "property_promotion_parameter" or pname is None:
                continue
            out.append(Member(src.text(pname).lstrip("$"),
                              type_text(p.child_by_field_name("type"), src),
                              visibility_of(modifier_words(p, src), "+"), False, _line(p)))
        return out


# ----------------------------------------------------------------- JavaScript y TypeScript


_TS_PROMOTE = {"public", "private", "protected", "readonly"}


class JsMembers:
    default_visibility = "+"

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        out = []
        for c in body.named_children:
            if c.type == "method_definition":
                out.extend(self._promoted(c, src))
                continue
            if c.type not in ("field_definition", "public_field_definition"):
                continue
            name_node = c.child_by_field_name("name") or c.child_by_field_name("property")
            if name_node is None:
                continue
            name = src.text(name_node)
            words = modifier_words(c, src)
            vis = "-" if name.startswith("#") else visibility_of(words, "+")
            typ = type_text(c.child_by_field_name("type"), src) or self._new_type(
                c.child_by_field_name("value"), src
            )
            out.append(Member(name.lstrip("#"), typ, vis, "static" in words, _line(c)))
        return out

    @staticmethod
    def _promoted(method: Node, src: Src) -> list[Member]:
        """`constructor(private s: Servicio)` declara el atributo `s` (TypeScript)."""
        name = method.child_by_field_name("name")
        params = method.child_by_field_name("parameters")
        if name is None or src.text(name) != "constructor" or params is None:
            return []
        out = []
        for p in params.named_children:
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            words = modifier_words(p, src)
            pname = p.child_by_field_name("pattern")
            if pname is None or pname.type != "identifier" or not words & _TS_PROMOTE:
                continue
            out.append(Member(src.text(pname), type_text(p.child_by_field_name("type"), src),
                              visibility_of(words, "+"), False, _line(p)))
        return out

    def _new_type(self, value: Node | None, src: Src) -> str | None:
        if value is not None and value.type == "new_expression":
            ctor = value.child_by_field_name("constructor")
            return src.text(ctor) if ctor is not None else None
        return None

    def assigned_members(self, node: Node, src: Src) -> list[Member]:
        out = []
        stop = ("function_declaration", "function_expression", "function", "class",
                "class_declaration", "method_definition")
        for n in _walk_body(self.function_body(node), stop):  # type: ignore[attr-defined]
            if n.type != "assignment_expression":
                continue
            left = n.child_by_field_name("left")
            if left is None or left.type != "member_expression":
                continue
            obj = left.child_by_field_name("object")
            prop = left.child_by_field_name("property")
            if obj is None or prop is None or src.text(obj) != "this":
                continue
            name = src.text(prop)
            vis = "-" if name.startswith("#") else "+"
            out.append(Member(name.lstrip("#"), self._new_type(n.child_by_field_name("right"), src),
                              vis, False, _line(n)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        info = super().method_info(node, src)  # type: ignore[misc]
        name = node.child_by_field_name("name")
        vis = "-" if name is not None and name.type == "private_property_identifier" else (
            info.visibility
        )
        abstract = info.abstract or node.type in ("abstract_method_signature", "method_signature")
        return MethodInfo(vis, info.static, abstract, info.returns)


# --------------------------------------------------------------------------- Python


class PythonMembers:
    default_visibility = "+"

    @staticmethod
    def _decorators(node: Node, src: Src) -> list[str]:
        parent = node.parent
        if parent is None or parent.type != "decorated_definition":
            return []
        return [src.text(d).lstrip("@") for d in parent.named_children if d.type == "decorator"]

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        dataclass_like = any("dataclass" in d for d in self._decorators(node, src))
        out = []
        for st in body.named_children:
            if st.type == "expression_statement" and st.named_child_count == 1:
                st = st.named_children[0]
            if st.type != "assignment":
                continue
            left = st.child_by_field_name("left")
            if left is None or left.type != "identifier":
                continue
            name = src.text(left)
            has_value = st.child_by_field_name("right") is not None
            out.append(Member(name, type_text(st.child_by_field_name("type"), src),
                              name_visibility(name), has_value and not dataclass_like, _line(st)))
        return out

    def assigned_members(self, node: Node, src: Src) -> list[Member]:
        out = []
        stop = ("function_definition", "class_definition", "lambda")
        for n in _walk_body(node.child_by_field_name("body"), stop):
            if n.type != "assignment":
                continue
            left = n.child_by_field_name("left")
            if left is None or left.type != "attribute":
                continue
            obj = left.child_by_field_name("object")
            attr = left.child_by_field_name("attribute")
            if obj is None or attr is None or src.text(obj) not in ("self", "cls"):
                continue
            name = src.text(attr)
            typ = type_text(n.child_by_field_name("type"), src)
            if typ is None:  # self.centro = Punto() → Punto
                right = n.child_by_field_name("right")
                fn = right.child_by_field_name("function") if right is not None and (
                    right.type == "call") else None
                if fn is not None and fn.type == "identifier" and src.text(fn)[:1].isupper():
                    typ = src.text(fn)
            out.append(Member(name, typ.strip("'\"") if typ else None, name_visibility(name),
                              src.text(obj) == "cls", _line(n)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        decos = self._decorators(node, src)
        name = node.child_by_field_name("name")
        return MethodInfo(
            name_visibility(src.text(name)) if name is not None else "+",
            any(d in ("staticmethod", "classmethod") for d in decos),
            any("abstractmethod" in d for d in decos),
            type_text(node.child_by_field_name("return_type"), src),
        )

    def class_is_abstract(self, node: Node, src: Src) -> bool:
        sup = node.child_by_field_name("superclasses")
        if sup is not None and any(w in src.text(sup) for w in ("ABC", "ABCMeta")):
            return True
        body = node.child_by_field_name("body")
        for c in body.named_children if body is not None else ():
            if c.type == "decorated_definition" and any(
                "abstractmethod" in src.text(d) for d in c.named_children if d.type == "decorator"
            ):
                return True
        return False


# --------------------------------------------------------------------------- Kotlin

_KOTLIN_TYPES = ("user_type", "nullable_type", "function_type", "parenthesized_type")


class KotlinMembers:
    default_visibility = "+"

    def _props(self, body: Node, src: Src, static: bool, out: list[Member]) -> None:
        for x in body.named_children:
            if x.type == "property_declaration":
                decl = _first(x, "variable_declaration")
                name = _first(decl, "simple_identifier")
                if name is not None:
                    out.append(Member(src.text(name), type_text(_first(decl, *_KOTLIN_TYPES), src),
                                      visibility_of(modifier_words(x, src), "+"), static,
                                      _line(x)))
            elif x.type == "companion_object":
                inner = _first(x, "class_body")
                if inner is not None:
                    self._props(inner, src, True, out)

    def class_members(self, node: Node, src: Src) -> list[Member]:
        out: list[Member] = []
        for c in node.named_children:
            if c.type == "primary_constructor":
                for p in c.named_children:
                    if p.type != "class_parameter" or _first(p, "binding_pattern_kind") is None:
                        continue  # sin val/var es solo un parámetro
                    name = _first(p, "simple_identifier")
                    if name is not None:
                        out.append(Member(src.text(name), type_text(_first(p, *_KOTLIN_TYPES), src),
                                          visibility_of(modifier_words(p, src), "+"), False,
                                          _line(p)))
            elif c.type == "class_body":
                self._props(c, src, False, out)
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        words = modifier_words(node, src)
        ret = None
        seen_params = False
        for c in node.named_children:
            if c.type == "function_value_parameters":
                seen_params = True
            elif seen_params and c.type in _KOTLIN_TYPES:
                ret = c
                break
        body = node.parent
        static = body is not None and body.parent is not None and (
            body.parent.type == "companion_object"
        )
        return MethodInfo(visibility_of(words, "+"), static, "abstract" in words,
                          type_text(ret, src))


# --------------------------------------------------------------------------- Swift


class SwiftMembers:
    default_visibility = "~"  # sin modificador: `internal`

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        out = []
        for c in body.named_children:
            if c.type != "property_declaration":
                continue
            words = modifier_words(c, src)
            pat = c.child_by_field_name("name")
            bound = pat.child_by_field_name("bound_identifier") if pat is not None else None
            if pat is None:
                continue
            ann = _first(c, "type_annotation")
            typ = type_text(ann.child_by_field_name("name") if ann is not None else None, src)
            value = c.child_by_field_name("value")
            if typ is None and value is not None and value.type == "call_expression":
                ctor = _first(value, "simple_identifier")
                if ctor is not None and src.text(ctor)[:1].isupper():
                    typ = src.text(ctor)  # `let centro = Punto()` → Punto
            out.append(Member(src.text(bound or pat), typ, visibility_of(words, "~"),
                              "static" in words or "class" in words, _line(c)))
        return out


# --------------------------------------------------------------------------- Go


def _go_visibility(name: str) -> str:
    return "+" if name[:1].isupper() else "~"


class GoMembers:
    default_visibility = "~"

    def class_members(self, node: Node, src: Src) -> list[Member]:
        struct = node.child_by_field_name("type")
        fields = _first(struct, "field_declaration_list") if struct is not None else None
        if fields is None:
            return []
        out = []
        for f in fields.named_children:
            if f.type != "field_declaration":
                continue
            typ = type_text(f.child_by_field_name("type"), src)
            for name in f.children_by_field_name("name"):
                text = src.text(name)
                out.append(Member(text, typ, _go_visibility(text), False, _line(f)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        name = node.child_by_field_name("name")
        return MethodInfo(_go_visibility(src.text(name)) if name is not None else "~", False,
                          False, type_text(node.child_by_field_name("result"), src))


# --------------------------------------------------------------------------- Rust


class RustMembers:
    default_visibility = "-"  # sin `pub`, privado al módulo

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None or body.type != "field_declaration_list":
            return []
        out = []
        for f in body.named_children:
            name = f.child_by_field_name("name") if f.type == "field_declaration" else None
            if name is not None:
                out.append(Member(src.text(name), type_text(f.child_by_field_name("type"), src),
                                  visibility_of(modifier_words(f, src), "-"), False, _line(f)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        params = node.child_by_field_name("parameters")
        has_self = params is not None and _first(params, "self_parameter") is not None
        block = node.parent.parent if node.parent is not None else None
        # Los métodos de un `trait` y de un `impl Trait for Tipo` son tan públicos como el trait.
        in_trait = block is not None and (
            block.type == "trait_item"
            or (block.type == "impl_item" and block.child_by_field_name("trait") is not None)
        )
        return MethodInfo(
            visibility_of(modifier_words(node, src), "+" if in_trait else "-"),
            not has_self,  # sin `self`: función asociada (como un método estático)
            node.type == "function_signature_item",
            type_text(node.child_by_field_name("return_type"), src),
        )


# --------------------------------------------------------------------------- Ruby

_RUBY_ATTRS = ("attr_reader", "attr_writer", "attr_accessor")


class RubyMembers:
    default_visibility = "+"

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        out = []
        for c in body.named_children if body is not None else ():
            if c.type == "call":
                method = c.child_by_field_name("method")
                args = c.child_by_field_name("arguments")
                if method is not None and src.text(method) in _RUBY_ATTRS and args is not None:
                    for a in args.named_children:
                        if a.type == "simple_symbol":
                            out.append(Member(src.text(a).lstrip(":"), None, "+", False, _line(c)))
            elif c.type == "assignment":
                left = c.child_by_field_name("left")
                if left is not None and left.type == "class_variable":
                    out.append(Member(src.text(left).lstrip("@"), None, "-", True, _line(c)))
        return out

    def assigned_members(self, node: Node, src: Src) -> list[Member]:
        out = []
        for n in _walk_body(node, ("method", "singleton_method", "class", "module")):
            if n.type in ("assignment", "operator_assignment"):
                left = n.child_by_field_name("left")
                if left is not None and left.type in ("instance_variable", "class_variable"):
                    static = left.type == "class_variable"
                    typ = self._new_type(n.child_by_field_name("right"), src)
                    out.append(Member(src.text(left).lstrip("@"), typ, "-", static, _line(n)))
        return out

    @staticmethod
    def _new_type(value: Node | None, src: Src) -> str | None:
        """`Punto.new(…)` → `Punto`: el único tipo que Ruby deja ver sin ejecutar."""
        if value is None or value.type != "call":
            return None
        method = value.child_by_field_name("method")
        receiver = value.child_by_field_name("receiver")
        if method is None or receiver is None or src.text(method) != "new":
            return None
        if receiver.type not in ("constant", "scope_resolution"):
            return None
        return src.text(receiver)

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        # `private` / `protected` sueltos cambian la visibilidad de lo que sigue.
        vis = "+"
        prev = node.prev_named_sibling
        while prev is not None:
            word = src.text(prev).strip()
            if prev.type in ("identifier", "call") and word in ("private", "protected", "public"):
                vis = {"private": "-", "protected": "#", "public": "+"}[word]
                break
            prev = prev.prev_named_sibling
        return MethodInfo(vis, node.type == "singleton_method", False, None)


# --------------------------------------------------------------------------- C++


def _cpp_name(decl: Node | None, src: Src) -> str | None:
    """Nombre de un atributo aunque esté envuelto (`*p`, `a[10]`, `&r`)."""
    while decl is not None:
        if decl.type in ("field_identifier", "identifier"):
            return src.text(decl)
        if decl.type == "function_declarator":
            return None  # es un método declarado, no un atributo
        decl = decl.child_by_field_name("declarator") or _first(
            decl, "field_identifier", "identifier", "pointer_declarator", "array_declarator",
            "reference_declarator",
        )
    return None


class CppMembers:
    default_visibility = None

    @staticmethod
    def _access_before(node: Node, src: Src, default: str) -> str:
        prev = node.prev_named_sibling
        while prev is not None:
            if prev.type == "access_specifier":
                return {"public": "+", "private": "-", "protected": "#"}.get(
                    src.text(prev).strip().rstrip(":").strip(), default
                )
            prev = prev.prev_named_sibling
        return default

    def class_members(self, node: Node, src: Src) -> list[Member]:
        body = node.child_by_field_name("body")
        if body is None:
            return []
        default = "+" if node.type == "struct_specifier" else "-"
        out = []
        for c in body.named_children:
            if c.type != "field_declaration":
                continue
            words = modifier_words(c, src)
            typ = type_text(c.child_by_field_name("type"), src)
            vis = self._access_before(c, src, default)
            for d in c.children_by_field_name("declarator"):
                name = _cpp_name(d, src)
                if name:
                    out.append(Member(name, typ, vis, "static" in words, _line(c)))
        return out

    @staticmethod
    def _prototypes(node: Node):
        body = node.child_by_field_name("body")
        for c in body.named_children if body is not None else ():
            decl = c.child_by_field_name("declarator") if c.type == "field_declaration" else None
            if decl is not None and decl.type == "function_declarator":
                yield c, decl

    def class_is_abstract(self, node: Node, src: Src) -> bool:
        return any(src.text(c).rstrip(" ;").endswith("= 0") for c, _ in self._prototypes(node))

    def declared_methods(self, node: Node, src: Src) -> list[DeclaredMethod]:
        """Prototipos dentro de la clase (`virtual double area() const = 0;`)."""
        default = "+" if node.type == "struct_specifier" else "-"
        out = []
        for c, decl in self._prototypes(node):
            name = decl.child_by_field_name("declarator")
            params = decl.child_by_field_name("parameters")
            if name is None:
                continue
            words = modifier_words(c, src)
            info = MethodInfo(self._access_before(c, src, default), "static" in words,
                              src.text(c).rstrip(" ;").endswith("= 0"),
                              type_text(c.child_by_field_name("type"), src))
            out.append(DeclaredMethod(src.text(name), src.text(params) if params else "()",
                                      info, _line(c)))
        return out

    def method_info(self, node: Node, src: Src) -> MethodInfo:
        info = super().method_info(node, src)  # type: ignore[misc]
        parent = node.parent
        if parent is not None and parent.type == "field_declaration_list":
            owner = parent.parent
            default = "+" if owner is not None and owner.type == "struct_specifier" else "-"
            return MethodInfo(self._access_before(node, src, default), info.static,
                              info.abstract, info.returns)
        return MethodInfo(None, info.static, info.abstract, info.returns)
