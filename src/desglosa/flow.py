"""AST de una función → diagrama de flujo (SPEC §7).

Además del `FlowGraph` (nodos y aristas del IR) se construye un árbol de estructura
(`SSeq`, `SIf`, `SLoop`...) que el layout estructurado (`layout/flow.py`) usa para dibujar
el diagrama "como hecho a mano". Los ids de nodo (`n0`, `n1`...) dependen solo del AST,
así que son deterministas.

Algoritmo de "salidas abiertas" (§7.1): cada construcción recibe la lista de salidas
pendientes `(nodo, etiqueta, tipo_arista)` y devuelve las suyas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tree_sitter import Node

from desglosa.extract import call_id
from desglosa.ir import FlowEdge, FlowGraph, FlowNode, Symbol
from desglosa.langs.spec import LangHooks, LangSpec, Src, one_line, strip_parens

Exit = tuple[str, "str | None", str]  # (nodo origen, etiqueta, tipo de arista)

FALLTHROUGH_LANGS = frozenset({"c", "cpp", "javascript", "typescript", "php", "java"})
ASSIGN_TYPES = frozenset(
    {
        "assignment",
        "augmented_assignment",
        "assignment_expression",
        "augmented_assignment_expression",
        "variable_declarator",
        "init_declarator",
    }
)
DECLARATION_TYPES = frozenset(
    {"lexical_declaration", "variable_declaration", "local_variable_declaration", "declaration"}
)
IO_NODE_KIND = {
    "pantalla": "pantalla",
    "teclado": "teclado",
    "archivo_escribe": "documento",
    "archivo_lee": "es",
}
TECH_LIMIT = 80


# --------------------------------------------------------------------------- estructura


@dataclass
class SNode:
    node_id: str
    stop: bool = False  # terminal "Fin" local: no tiene salida


@dataclass
class SJump:
    kind: str  # "break" | "continue" | "throw"
    target: int  # id de la estructura destino
    catch_index: int = 0


@dataclass
class SSeq:
    items: list = field(default_factory=list)


@dataclass
class SIf:
    dec: str
    yes: SSeq
    no: SSeq | None


@dataclass
class SLoop:
    kind: str  # "while" | "for" | "foreach"
    dec: str
    body: SSeq
    init: str | None
    update: str | None
    sid: int


@dataclass
class SDoWhile:
    dec: str
    body: SSeq
    sid: int


@dataclass
class SCase:
    label: str
    body: SSeq
    falls_through: bool = False


@dataclass
class SSwitch:
    dec: str
    cases: list[SCase]
    sid: int


@dataclass
class STry:
    node: str
    body: SSeq
    catches: list[tuple[str, SSeq]]
    final: SSeq | None
    sid: int


@dataclass
class CallInfo:
    """Lo que el diagrama necesita saber de una llamada ya resuelta."""

    callee: str
    confidence: str
    io_kind: str | None
    target: str | None  # función/método a abrir al hacer clic (None si no es clicable)


@dataclass
class FlowResult:
    graph: FlowGraph
    struct: SSeq
    warnings: list[str]


# --------------------------------------------------------------------------- textos


_STRINGS = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`")


def easy_expr(text: str, lang: str) -> str:
    """Traduce operadores al español fuera de las cadenas (SPEC §7.2)."""
    out: list[str] = []
    pos = 0
    for m in _STRINGS.finditer(text):
        out.append(_easy_code(text[pos : m.start()], lang))
        out.append(m.group(0).replace("\\n", "").replace("\\t", " ").replace("\\r", ""))
        pos = m.end()
    out.append(_easy_code(text[pos:], lang))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _easy_code(s: str, lang: str) -> str:
    s = s.replace("->", ".")
    s = re.sub(r"!==|!=", " ≠ ", s)
    s = re.sub(r"===|==", " = ", s)
    s = s.replace("<=", " ≤ ").replace(">=", " ≥ ")
    s = s.replace("&&", " y ").replace("||", " o ")
    s = re.sub(r"!(?![=])", " no ", s)
    s = re.sub(r"\band\b", "y", s)
    s = re.sub(r"\bor\b", "o", s)
    s = re.sub(r"\bnot\b", "no", s)
    if lang == "php":
        s = s.replace("$", "")
    return s


def _tech(text: str) -> str:
    return one_line(text.rstrip().rstrip(";"), TECH_LIMIT)


def _string_literal(args: tuple[str, ...]) -> str | None:
    for a in args:
        a = a.strip()
        if len(a) >= 2 and a[0] in "\"'`" and a[-1] == a[0]:
            return a
    return None


# --------------------------------------------------------------------------- constructor


class _Ctx:
    __slots__ = ("kind", "sid", "breaks", "continues", "throws", "catch_labels")

    def __init__(self, kind: str, sid: int, catch_labels: list[str] | None = None) -> None:
        self.kind = kind
        self.sid = sid
        self.breaks: list[Exit] = []
        self.continues: list[Exit] = []
        self.throws: list[tuple[Exit, int]] = []
        self.catch_labels = catch_labels or []


@dataclass
class _StmtInfo:
    kind: str
    easy: str
    tech: str
    call_id: str | None = None
    target: str | None = None


class FlowBuilder:
    def __init__(
        self,
        spec: LangSpec,
        hooks: LangHooks,
        src: Src,
        path: str,
        symbol: Symbol,
        calls: dict[str, CallInfo],
        depth_limit: int | None = None,
    ) -> None:
        self.spec = spec
        self.hooks = hooks
        self.src = src
        self.path = path
        self.lang = symbol.lang
        self.symbol = symbol
        self.calls = calls
        self.depth_limit = depth_limit
        self.nodes: list[FlowNode] = []
        self.edges: list[FlowEdge] = []
        self.stack: list[_Ctx] = []
        self.depth = 0
        self.max_depth = 0
        self.next_sid = 0
        self.collapsed = False
        self.warnings: list[str] = []
        self.stream_vars: dict[str, str] = {}
        s = spec
        self.control_types = (
            set(s.if_nodes)
            | set(s.loop_nodes)
            | set(s.do_while_nodes)
            | set(s.switch_nodes)
            | set(s.try_nodes)
        )
        self.definition_types = (
            set(s.class_nodes)
            | set(s.interface_nodes)
            | set(s.function_nodes)
            | set(s.method_nodes)
        )
        self._info_cache: dict[int, _StmtInfo] = {}

    # ------------------------------------------------------------------ grafo

    def node(
        self,
        kind: str,
        easy: str,
        tech: str,
        start: Node | int,
        end: Node | int | None = None,
        call_id: str | None = None,
        target: str | None = None,
    ) -> str:
        line_start = start if isinstance(start, int) else start.start_point[0] + 1
        if end is None:
            line_end = line_start if isinstance(start, int) else start.end_point[0] + 1
        else:
            line_end = end if isinstance(end, int) else end.end_point[0] + 1
        nid = f"n{len(self.nodes)}"
        self.nodes.append(
            FlowNode(
                id=nid,
                kind=kind,
                text_easy=easy,
                text_tech=tech,
                line_start=line_start,
                line_end=line_end,
                call_id=call_id,
                target_symbol=target,
            )
        )
        return nid

    def edge(self, src: str, dst: str, label: str | None = None, kind: str = "normal") -> None:
        self.edges.append(FlowEdge(src=src, dst=dst, label=label, kind=kind))

    def link(self, exits: list[Exit], dst: str, kind: str | None = None) -> None:
        for src, label, k in exits:
            self.edge(src, dst, label, kind or k)

    def _sid(self) -> int:
        self.next_sid += 1
        return self.next_sid

    # ------------------------------------------------------------------ utilidades AST

    def text(self, node: Node | None) -> str:
        return self.src.text(node)

    def _is_block(self, node: Node) -> bool:
        return node.type in self.spec.block_nodes or node.type in (
            "block",
            "statement_block",
            "compound_statement",
            "constructor_body",
        )

    def statements(self, node: Node | None) -> list[Node]:
        if node is None:
            return []
        if self._is_block(node):
            out = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
            return [c for c in out if c.type not in ("pass_statement", "empty_statement")]
        return [node]

    def _body_of(self, node: Node) -> Node | None:
        body = node.child_by_field_name("body") or node.child_by_field_name("consequence")
        if body is not None:
            return body
        named = [c for c in node.named_children if c.type not in self.spec.comment_nodes]
        return named[-1] if named else None

    def _is_definition(self, st: Node) -> str | None:
        """Nombre si la sentencia define una función/clase anidada."""
        target = st
        if st.type == "decorated_definition":
            target = st.child_by_field_name("definition") or st
        if target.type in self.definition_types:
            name = self.hooks.symbol_name(target, self.src)
            if name:
                return name
        if st.type in DECLARATION_TYPES:
            for d in st.named_children:
                value = d.child_by_field_name("value")
                if value is not None and value.type in self.definition_types:
                    name = self.hooks.symbol_name(value, self.src)
                    if name:
                        return name
        return None

    def _calls_in(self, node: Node) -> list[tuple[Node, str, CallInfo | None, str]]:
        """Llamadas dentro de `node` (sin entrar a funciones/clases con nombre)."""
        found: list[tuple[Node, str, CallInfo | None, str]] = []
        call_types = set(self.spec.call_nodes)
        stack = [node]
        while stack:
            n = stack.pop()
            if (
                n is not node
                and n.type in self.definition_types
                and self.hooks.symbol_name(n, self.src)
            ):
                continue
            if n.type in call_types:
                parts = self.hooks.call_parts(n, self.src)
                if parts is not None and parts.callee:
                    cid = call_id(
                        self.lang,
                        self.path,
                        self.symbol.qualname,
                        parts.callee,
                        n.start_point[0] + 1,
                        n.start_point[1] + 1,
                    )
                    found.append((n, cid, self.calls.get(cid), parts.callee))
            stack.extend(reversed(n.named_children))
        found.sort(key=lambda item: (item[0].start_byte, -item[0].end_byte))
        return found

    def _assign_target(self, st: Node) -> str | None:
        stack = [(st, 0)]
        while stack:
            n, depth = stack.pop(0)
            if n.type in ASSIGN_TYPES:
                left = (
                    n.child_by_field_name("left")
                    or n.child_by_field_name("name")
                    or n.child_by_field_name("declarator")
                )
                if left is not None:
                    return one_line(self.text(left), 30)
            if depth < 3:
                stack.extend((c, depth + 1) for c in n.named_children)
        return None

    # ------------------------------------------------------------------ clasificación

    def info(self, st: Node) -> _StmtInfo:
        cached = self._info_cache.get(st.id)
        if cached is None:
            cached = self._compute_info(st)
            self._info_cache[st.id] = cached
        return cached

    def _compute_info(self, st: Node) -> _StmtInfo:
        tech = _tech(self.text(st))
        lang = self.lang
        name = self._is_definition(st)
        if name:
            return _StmtInfo(
                "proceso", f"Define {name}", one_line(self.text(st).split("\n")[0], 80)
            )
        calls = self._calls_in(st)
        resolved = [c for c in calls if c[2] is not None and c[2].target]
        if resolved:
            _, cid, info, callee = resolved[0]
            target_var = self._assign_target(st)
            easy = f"Llama a {callee}()" + (
                f" → {easy_expr(target_var, lang)}" if target_var else ""
            )
            return _StmtInfo("subproceso", easy, tech, cid, info.target)
        io_calls = [c for c in calls if c[2] is not None and c[2].io_kind]
        if io_calls:
            n, cid, info, callee = io_calls[0]
            parts = self.hooks.call_parts(n, self.src)
            args = parts.args if parts is not None else ()
            easy = self._io_easy(info.io_kind, callee, args, st)
            return _StmtInfo(IO_NODE_KIND[info.io_kind], easy, tech, cid, None)
        stmt_io = self._statement_io(st)
        if stmt_io is not None:
            io_kind, easy = stmt_io
            return _StmtInfo(IO_NODE_KIND[io_kind], easy, tech)
        if calls and self._is_pure_call(st, calls[0][0]):
            _, cid, _, callee = calls[0]
            return _StmtInfo("externo", f"Llama a {callee}()", tech, cid, None)
        return _StmtInfo("proceso", easy_expr(tech, lang), tech)

    def _is_pure_call(self, st: Node, call: Node) -> bool:
        if st.id == call.id:
            return True
        inner = st
        while inner.named_child_count == 1 and inner.type in (
            "expression_statement",
            "await_expression",
            "parenthesized_expression",
        ):
            inner = inner.named_children[0]
        return inner.id == call.id

    def _io_easy(self, io_kind: str, callee: str, args: tuple[str, ...], st: Node) -> str:
        lang = self.lang
        target = self._assign_target(st)
        if io_kind == "pantalla":
            content = ", ".join(args) if args else ""
            return f"Muestra: {easy_expr(content, lang)}" if content else "Muestra en pantalla"
        if io_kind == "teclado":
            if target:
                return f"Lee del teclado → {easy_expr(target, lang)}"
            rest = args[1:] if callee in ("scanf", "fscanf") else args
            rest = tuple(a.lstrip("&") for a in rest if a.strip() not in ("stdin", "STDIN"))
            return "Lee del teclado" + (f" → {', '.join(rest)}" if rest else "")
        fname = _string_literal(args)
        opening = callee in ("open", "fopen", "Open", "Create")
        if io_kind == "archivo_escribe":
            if opening:
                return f"Abre {fname or 'archivo'} para escribir"
            return f"Escribe en archivo: {fname}" if fname else "Escribe en archivo"
        if opening:
            return f"Abre {fname or 'archivo'} para leer"
        return "Lee del archivo" + (f" → {easy_expr(target, lang)}" if target else "")

    def _statement_io(self, st: Node) -> tuple[str, str] | None:
        """E/S que no es una llamada: `echo` (PHP), `cout <<` / `cin >>` y fstream (C++)."""
        lang = self.lang
        if lang == "php":
            inner = (
                st.named_children[0]
                if st.type == "expression_statement" and st.named_child_count
                else st
            )
            if inner.type in ("echo_statement", "print_intrinsic"):
                content = self.text(inner)
                content = re.sub(r"^(echo|print)\s*", "", content).rstrip(";")
                return "pantalla", f"Muestra: {easy_expr(one_line(content, 60), lang)}"
            return None
        if lang != "cpp":
            return None
        if st.type == "declaration":
            typ = self.text(st.child_by_field_name("type"))
            for kind_txt, io_kind, verb in (
                ("ofstream", "archivo_escribe", "escribir"),
                ("ifstream", "archivo_lee", "leer"),
            ):
                if kind_txt in typ:
                    decl = st.child_by_field_name("declarator")
                    name_node = decl.child_by_field_name("declarator") if decl is not None else None
                    var = self.text(name_node or decl)
                    self.stream_vars[var] = io_kind
                    fname = re.search(r"\"[^\"]*\"", self.text(st))
                    return io_kind, f"Abre {fname.group(0) if fname else 'archivo'} para {verb}"
            return None
        if st.type != "expression_statement" or st.named_child_count != 1:
            return None
        expr = st.named_children[0]
        if expr.type != "binary_expression":
            return None
        operands: list[str] = []
        op = None
        cur = expr
        while cur.type == "binary_expression":
            operator = cur.child_by_field_name("operator")
            op = self.text(operator) if operator is not None else op
            operands.insert(0, self.text(cur.child_by_field_name("right")))
            cur = cur.child_by_field_name("left")
        head = self.text(cur).replace("std::", "")
        rest = [o for o in operands if o.replace("std::", "") not in ("endl", "flush")]
        content = " ".join(rest)
        if op == "<<" and head in ("cout", "cerr", "clog"):
            return "pantalla", f"Muestra: {easy_expr(one_line(content, 60), lang)}"
        if op == ">>" and head == "cin":
            return "teclado", f"Lee del teclado → {content}"
        if head in self.stream_vars:
            kind = self.stream_vars[head]
            if kind == "archivo_escribe":
                return kind, "Escribe en archivo: " + easy_expr(one_line(content, 50), lang)
            return kind, "Lee del archivo → " + content
        return None

    def _is_simple(self, st: Node) -> bool:
        t = st.type
        s = self.spec
        if (
            t in self.control_types
            or t in s.return_nodes
            or t in s.break_nodes
            or t in s.continue_nodes
            or t in s.goto_nodes
            or t in s.label_nodes
            or t in s.block_nodes
            or t == "with_statement"
            or self._is_throw(st)
        ):
            return False
        return self.info(st).kind == "proceso"

    def _is_throw(self, st: Node) -> bool:
        if st.type in self.spec.throw_nodes:
            return True
        if st.type == "expression_statement" and st.named_child_count == 1:
            return st.named_children[0].type in self.spec.throw_nodes
        return False

    # ------------------------------------------------------------------ construcción

    def build(self, func: Node) -> FlowResult:
        sym = self.symbol
        params_easy, params_tech = self._params(func)
        start = self.node(
            "terminal",
            f"Inicio: {sym.name}({params_easy})",
            f"Inicio: {sym.name}{params_tech}",
            sym.line_start,
        )
        body = self.hooks.function_body(func)
        stmts = self.statements(body) if body is not None and self._is_block(body) else []
        if body is not None and not self._is_block(body):
            # Cuerpo de expresión (arrow function `x => x + 1`): un solo "Retorna".
            nid = self.node(
                "proceso",
                f"Retorna {easy_expr(_tech(self.text(body)), self.lang)}",
                f"return {_tech(self.text(body))}",
                body,
            )
            self.edge(start, nid)
            end = self.node("terminal", "Fin", "Fin", sym.line_end)
            self.edge(nid, end)
            struct = SSeq([SNode(start), SNode(nid), SNode(end)])
            return self._result(struct)
        if self.lang == "python" and stmts and stmts[0].type in ("string", "expression_statement"):
            first = stmts[0]
            inner = (
                first.named_children[0]
                if first.type == "expression_statement" and first.named_child_count
                else first
            )
            if inner.type == "string":
                stmts = stmts[1:]
        seq, exits = self.block(stmts, [(start, None, "normal")], top=True)
        if (
            not exits
            and self.nodes
            and any(n.kind == "terminal" and n.text_tech.startswith("Fin") for n in self.nodes)
        ):
            # Todos los caminos terminan en un "Fin" local: no hace falta otro al final.
            return self._result(SSeq([SNode(start), *seq.items]))
        end = self.node("terminal", "Fin", "Fin", sym.line_end)
        self.link(exits, end)
        struct = SSeq([SNode(start), *seq.items, SNode(end)])
        return self._result(struct)

    def _result(self, struct: SSeq) -> FlowResult:
        edges: dict[tuple[str, str, str], FlowEdge] = {}
        for e in self.edges:
            key = (e.src, e.dst, e.kind)
            prev = edges.get(key)
            if prev is None:
                edges[key] = e
            elif e.label and prev.label != e.label:
                label = " / ".join(x for x in (prev.label, e.label) if x)
                edges[key] = FlowEdge(e.src, e.dst, label, e.kind)
        graph = FlowGraph(
            symbol_id=self.symbol.id,
            nodes=tuple(self.nodes),
            edges=tuple(edges.values()),
            truncated=self.collapsed,
        )
        return FlowResult(graph, struct, self.warnings)

    def _params(self, func: Node) -> tuple[str, str]:
        params = func.child_by_field_name("parameters")
        if params is None:
            decl = func.child_by_field_name("declarator")
            while decl is not None and params is None:
                params = decl.child_by_field_name("parameters")
                decl = decl.child_by_field_name("declarator")
        if params is None:
            return "", "()"
        tech = one_line(self.text(params), 70)
        if not tech.startswith("("):
            tech = f"({tech})"
        names: list[str] = []
        for p in params.named_children:
            if p.type in self.spec.comment_nodes:
                continue
            name = self._param_name(p)
            if name and name not in ("self", "cls", "void"):
                names.append(name.lstrip("$&*"))
        return ", ".join(names), tech

    def _param_name(self, p: Node) -> str | None:
        if p.type in ("identifier", "variable_name", "simple_identifier"):
            return self.text(p)
        for fname in ("name", "pattern", "declarator"):
            child = p.child_by_field_name(fname)
            if child is not None:
                return self._param_name(child) or self.text(child)
        for c in p.named_children:
            if c.type in ("identifier", "variable_name"):
                return self.text(c)
        return None

    def block(
        self, stmts: list[Node], exits: list[Exit], top: bool = False
    ) -> tuple[SSeq, list[Exit]]:
        items: list = []
        pending: list[Node] = []

        def flush() -> None:
            nonlocal exits
            for i in range(0, len(pending), 4):
                chunk = pending[i : i + 4]
                easy = "\n".join(self.info(s).easy for s in chunk)
                tech = "\n".join(self.info(s).tech for s in chunk)
                nid = self.node("proceso", easy, tech, chunk[0], chunk[-1])
                self.link(exits, nid)
                exits = [(nid, None, "normal")]
                items.append(SNode(nid))
            pending.clear()

        for i, st in enumerate(stmts):
            if st.type in self.spec.comment_nodes:
                continue
            if self._is_simple(st):
                pending.append(st)
                continue
            flush()
            top_last = top and i == len(stmts) - 1
            struct, exits = self.stmt(st, exits, top_last)
            if isinstance(struct, SSeq):
                items.extend(struct.items)
            else:
                items.append(struct)
        flush()
        return SSeq(items), exits

    def stmt(self, st: Node, exits: list[Exit], top_last: bool = False):
        t = st.type
        s = self.spec
        if (
            t in self.control_types
            and self.depth_limit is not None
            and self.depth >= self.depth_limit
        ):
            return self._collapse(st, exits)
        if t in s.if_nodes:
            return self.if_(st, exits)
        if t in s.loop_nodes:
            return self.loop(st, exits)
        if t in s.do_while_nodes:
            return self.do_while(st, exits)
        if t in s.switch_nodes:
            return self.switch(st, exits)
        if t in s.try_nodes:
            return self.try_(st, exits)
        if t in s.return_nodes:
            return self.return_(st, exits, top_last)
        if t in s.break_nodes:
            return self.jump("break", st, exits)
        if t in s.continue_nodes:
            return self.jump("continue", st, exits)
        if self._is_throw(st):
            return self.throw(st, exits)
        if t in s.goto_nodes:
            label = self.text(st.child_by_field_name("label"))
            self.warnings.append(f"{self.path}:{st.start_point[0] + 1}: goto no soportado")
            nid = self.node("proceso", f"goto {label} (no soportado)", _tech(self.text(st)), st)
            self.link(exits, nid)
            return SSeq([SNode(nid)]), [(nid, None, "normal")]
        if t in s.label_nodes:
            inner = [c for c in st.named_children if c.type != "statement_identifier"]
            return self.block(inner, exits, top=top_last)
        if t in s.block_nodes:
            return self.block(self.statements(st), exits)
        if t == "with_statement":
            return self.with_(st, exits)
        info = self.info(st)
        nid = self.node(
            info.kind, info.easy, info.tech, st, call_id=info.call_id, target=info.target
        )
        self.link(exits, nid)
        return SSeq([SNode(nid)]), [(nid, None, "normal")]

    def _collapse(self, st: Node, exits: list[Exit]):
        self.collapsed = True
        a, b = st.start_point[0] + 1, st.end_point[0] + 1
        nid = self.node("proceso", f"Bloque (L{a}–L{b})", f"Bloque (L{a}–L{b})", st)
        self.link(exits, nid)
        return SSeq([SNode(nid)]), [(nid, None, "normal")]

    def _enter(self) -> None:
        self.depth += 1
        self.max_depth = max(self.max_depth, self.depth)

    def _leave(self) -> None:
        self.depth -= 1

    def _decision_call(self, node: Node | None) -> tuple[str | None, str | None]:
        if node is None:
            return None, None
        for _, cid, info, _ in self._calls_in(node):
            if info is not None and info.target:
                return cid, info.target
        return None, None

    # ------------------------------------------------------------------ if

    def if_(self, st: Node, exits: list[Exit]):
        cond_text = self.hooks.condition(st, self.src)
        cond_node = self.hooks.condition_node(st)
        cid, target = self._decision_call(cond_node)
        dec = self.node(
            "decision",
            f"¿{easy_expr(cond_text, self.lang)}?",
            one_line(cond_text, TECH_LIMIT),
            st,
            cond_node if cond_node is not None else st.start_point[0] + 1,
            cid,
            target,
        )
        self.link(exits, dec)
        self._enter()
        yes_seq, yes_exits = self.block(
            self.statements(self._consequence(st)), [(dec, "sí", "normal")]
        )
        alts = [c for i, c in enumerate(st.children) if st.field_name_for_child(i) == "alternative"]
        no_seq, no_exits = self._alternatives(alts, [(dec, "no", "normal")])
        self._leave()
        return SIf(dec, yes_seq, no_seq), yes_exits + no_exits

    def _consequence(self, st: Node) -> Node | None:
        return st.child_by_field_name("consequence") or st.child_by_field_name("body")

    def _alternatives(self, alts: list[Node], exits: list[Exit]) -> tuple[SSeq | None, list[Exit]]:
        if not alts:
            return None, exits
        first = alts[0]
        s = self.spec
        if first.type in s.elif_nodes:
            cond_text = self.hooks.condition(first, self.src)
            cond_node = self.hooks.condition_node(first)
            cid, target = self._decision_call(cond_node)
            dec = self.node(
                "decision",
                f"¿{easy_expr(cond_text, self.lang)}?",
                one_line(cond_text, TECH_LIMIT),
                first,
                cond_node if cond_node is not None else first.start_point[0] + 1,
                cid,
                target,
            )
            self.link(exits, dec)
            yes_seq, yes_exits = self.block(
                self.statements(self._consequence(first)), [(dec, "sí", "normal")]
            )
            no_seq, no_exits = self._alternatives(alts[1:], [(dec, "no", "normal")])
            return SSeq([SIf(dec, yes_seq, no_seq)]), yes_exits + no_exits
        if first.type in s.else_nodes:
            body = first.child_by_field_name("body")
            if body is None:
                named = [c for c in first.named_children if c.type not in s.comment_nodes]
                body = named[0] if named else None
            if body is not None and body.type in s.if_nodes:
                struct, ex = self.if_(body, exits)
                return SSeq([struct]), ex
            return self.block(self.statements(body), exits)
        if first.type in s.if_nodes:
            struct, ex = self.if_(first, exits)
            return SSeq([struct]), ex
        return self.block(self.statements(first), exits)

    # ------------------------------------------------------------------ bucles

    def _loop_kind(self, st: Node) -> str:
        if st.type in ("foreach_statement", "enhanced_for_statement", "for_range_loop"):
            return "foreach"
        if (
            st.child_by_field_name("left") is not None
            and st.child_by_field_name("right") is not None
        ):
            return "foreach"
        if any(
            st.child_by_field_name(f) is not None
            for f in ("initializer", "init", "initialize", "update", "increment")
        ) or (st.type == "for_statement" and self.lang != "python"):
            return "for"
        return "while"

    def _foreach_parts(self, st: Node) -> tuple[str, str]:
        if st.type == "foreach_statement":
            named = [c for c in st.named_children if c.type not in self.spec.comment_nodes]
            coll = self.text(named[0]) if named else ""
            var = self.text(named[1]) if len(named) > 2 else ""
            return var, coll
        var_node = (
            st.child_by_field_name("left")
            or st.child_by_field_name("name")
            or st.child_by_field_name("declarator")
        )
        coll_node = st.child_by_field_name("right") or st.child_by_field_name("value")
        return self.text(var_node), self.text(coll_node)

    def loop(self, st: Node, exits: list[Exit]):
        kind = self._loop_kind(st)
        sid = self._sid()
        lang = self.lang
        init_id = None
        update_node = None
        if kind == "for":
            init = next(
                (
                    st.child_by_field_name(f)
                    for f in ("initializer", "init", "initialize")
                    if st.child_by_field_name(f) is not None
                ),
                None,
            )
            update_node = next(
                (
                    st.child_by_field_name(f)
                    for f in ("update", "increment")
                    if st.child_by_field_name(f) is not None
                ),
                None,
            )
            if init is not None:
                text = _tech(self.text(init))
                init_id = self.node("proceso", easy_expr(text, lang), text, init)
                self.link(exits, init_id)
                exits = [(init_id, None, "normal")]
            cond_node = st.child_by_field_name("condition")
            cond = strip_parens(self.text(cond_node)) if cond_node is not None else ""
            cond = one_line(cond, TECH_LIMIT)
            easy = f"¿{easy_expr(cond, lang)}?" if cond else "Repetir siempre"
            tech = cond or "(sin condición)"
        elif kind == "foreach":
            var, coll = self._foreach_parts(st)
            cond_node = st.child_by_field_name("right") or st.child_by_field_name("value")
            var_easy = easy_expr(one_line(var, 30), lang)
            easy = f"Para cada {var_easy} en {easy_expr(one_line(coll, 40), lang)}"
            tech = one_line(self.hooks.loop_label(st, self.src), TECH_LIMIT)
        else:
            cond_node = self.hooks.condition_node(st)
            cond = one_line(self.hooks.condition(st, self.src), TECH_LIMIT)
            easy = f"¿{easy_expr(cond, lang)}?"
            tech = cond
        cid, target = self._decision_call(cond_node)
        dec = self.node(
            "decision",
            easy,
            tech,
            st,
            cond_node if cond_node is not None else st.start_point[0] + 1,
            cid,
            target,
        )
        self.link(exits, dec)
        ctx = _Ctx("loop", sid)
        self.stack.append(ctx)
        self._enter()
        body = st.child_by_field_name("body")
        body_seq, body_exits = self.block(self.statements(body), [(dec, "sí", "normal")])
        self._leave()
        self.stack.pop()
        update_id = None
        if update_node is not None:
            text = _tech(self.text(update_node))
            update_id = self.node("proceso", easy_expr(text, lang), text, update_node)
            self.link(body_exits, update_id)
            self.link(ctx.continues, update_id)
            if body_exits or ctx.continues:
                self.edge(update_id, dec, None, "retorno_bucle")
        else:
            self.link(body_exits, dec, "retorno_bucle")
            self.link(ctx.continues, dec)
        struct = SLoop(kind, dec, body_seq, init_id, update_id, sid)
        return struct, [(dec, "no", "normal"), *ctx.breaks]

    def do_while(self, st: Node, exits: list[Exit]):
        sid = self._sid()
        ctx = _Ctx("loop", sid)
        first_index = len(self.nodes)
        self.stack.append(ctx)
        self._enter()
        body_seq, body_exits = self.block(self.statements(st.child_by_field_name("body")), exits)
        self._leave()
        self.stack.pop()
        cond_node = self.hooks.condition_node(st)
        cond = one_line(self.hooks.condition(st, self.src), TECH_LIMIT)
        cid, target = self._decision_call(cond_node)
        dec = self.node(
            "decision",
            f"¿{easy_expr(cond, self.lang)}?",
            cond,
            cond_node if cond_node is not None else st,
            None,
            cid,
            target,
        )
        self.link(body_exits, dec)
        self.link(ctx.continues, dec)
        entry = self.nodes[first_index].id if len(self.nodes) - 1 > first_index else dec
        self.edge(dec, entry, "sí", "retorno_bucle")
        return SDoWhile(dec, body_seq, sid), [(dec, "no", "normal"), *ctx.breaks]

    # ------------------------------------------------------------------ switch

    def _case_statements(self, case: Node) -> list[Node]:
        out: list[Node] = []
        for i, ch in enumerate(case.children):
            if not ch.is_named:
                continue
            fname = case.field_name_for_child(i)
            if fname == "value" or ch.type in ("switch_label", "case_pattern"):
                continue
            if ch.type in self.spec.comment_nodes:
                continue
            if fname == "consequence" and ch.type in self.spec.block_nodes:
                out.extend(self.statements(ch))
            else:
                out.append(ch)
        return out

    def switch(self, st: Node, exits: list[Exit]):
        lang = self.lang
        subject = self.hooks.condition(st, self.src)
        body = st.child_by_field_name("body")
        header_end = body.start_byte if body is not None else st.end_byte
        tech = one_line(self.src.between(st.start_byte, header_end).rstrip(" {:"), TECH_LIMIT)
        dec = self.node(
            "decision",
            f"Según {easy_expr(one_line(subject, 40), lang)}",
            tech,
            st,
            st.start_point[0] + 1,
        )
        self.link(exits, dec)
        sid = self._sid()
        ctx = _Ctx("switch", sid)
        self.stack.append(ctx)
        self._enter()
        cases = [
            c
            for c in (body.named_children if body is not None else [])
            if c.type in self.spec.case_nodes
        ]
        struct_cases: list[SCase] = []
        pending: list[str] = []
        fall: list[Exit] = []
        total: list[Exit] = []
        has_default = False
        for case in cases:
            value = self.hooks.case_value(case, self.src)
            label = f"caso {value}" if value is not None else "otro"
            has_default = has_default or value is None
            stmts = self._case_statements(case)
            falls = lang in FALLTHROUGH_LANGS and case.type != "switch_rule"
            final_break = bool(stmts) and stmts[-1].type in self.spec.break_nodes
            if final_break:
                stmts = stmts[:-1]
            if not stmts and falls and not final_break:
                pending.append(label)
                continue
            full_label = " / ".join([*pending, label])
            pending = []
            seq, case_exits = self.block(stmts, [(dec, full_label, "normal"), *fall])
            if falls and not final_break and case_exits:
                fall = case_exits
                struct_cases.append(SCase(full_label, seq, falls_through=True))
            else:
                total.extend(case_exits)
                fall = []
                struct_cases.append(SCase(full_label, seq))
        if pending:
            label = " / ".join(pending)
            total.append((dec, label, "normal"))
            struct_cases.append(SCase(label, SSeq([])))
        if fall:
            total.extend(fall)
            if struct_cases:
                struct_cases[-1].falls_through = False
        if not has_default:
            total.append((dec, "otro", "normal"))
            struct_cases.append(SCase("otro", SSeq([])))
        self._leave()
        self.stack.pop()
        return SSwitch(dec, struct_cases, sid), total + ctx.breaks

    # ------------------------------------------------------------------ try

    def try_(self, st: Node, exits: list[Exit]):
        s = self.spec
        nid = self.node("proceso", "Intentar", "try", st, st.start_point[0] + 1)
        self.link(exits, nid)
        catches = [c for c in st.named_children if c.type in s.catch_nodes]
        final = next((c for c in st.named_children if c.type in s.finally_nodes), None)
        else_clause = next((c for c in st.named_children if c.type in s.else_nodes), None)
        labels = [self.hooks.catch_label(c, self.src) or "excepción" for c in catches]
        sid = self._sid()
        ctx = _Ctx("try", sid, labels)
        self.stack.append(ctx)
        self._enter()
        body_seq, body_exits = self.block(
            self.statements(st.child_by_field_name("body")), [(nid, None, "normal")]
        )
        self.stack.pop()
        if else_clause is not None:
            else_seq, body_exits = self.block(
                self.statements(self._body_of(else_clause)), body_exits
            )
            body_seq.items.extend(else_seq.items)
        catch_structs: list[tuple[str, SSeq]] = []
        all_exits = list(body_exits)
        for i, c in enumerate(catches):
            entry: list[Exit] = [(nid, f"excepción: {labels[i]}", "excepcion")]
            entry += [ex for ex, idx in ctx.throws if idx == i]
            seq, ex = self.block(self.statements(self._body_of(c)), entry)
            catch_structs.append((labels[i], seq))
            all_exits.extend(ex)
        final_seq = None
        if final is not None:
            final_seq, all_exits = self.block(self.statements(self._body_of(final)), all_exits)
        self._leave()
        return STry(nid, body_seq, catch_structs, final_seq, sid), all_exits

    # ------------------------------------------------------------------ saltos

    def return_(self, st: Node, exits: list[Exit], top_last: bool):
        lang = self.lang
        value_nodes = [c for c in st.named_children if c.type not in self.spec.comment_nodes]
        value = _tech(" ".join(self.text(v) for v in value_nodes)) if value_nodes else ""
        info = self.info(st) if value_nodes else _StmtInfo("proceso", "", "")
        easy = f"Retorna {easy_expr(value, lang)}" if value else "Retorna"
        kind = (
            info.kind
            if info.kind in ("subproceso", "pantalla", "teclado", "documento", "es")
            else "proceso"
        )
        if kind == "subproceso":
            easy = f"Retorna el resultado de {info.easy.removeprefix('Llama a ')}"
        nid = self.node(
            kind, easy, _tech(self.text(st)), st, call_id=info.call_id, target=info.target
        )
        self.link(exits, nid)
        if top_last:
            return SSeq([SNode(nid)]), [(nid, None, "normal")]
        end = self.node("terminal", "Fin", "Fin", st)
        self.edge(nid, end)
        return SSeq([SNode(nid), SNode(end, stop=True)]), []

    def _innermost(self, kinds: tuple[str, ...]) -> _Ctx | None:
        for ctx in reversed(self.stack):
            if ctx.kind in kinds:
                return ctx
        return None

    def jump(self, kind: str, st: Node, exits: list[Exit]):
        ctx = self._innermost(("loop", "switch") if kind == "break" else ("loop",))
        if ctx is None:
            nid = self.node("proceso", kind, kind, st)
            self.link(exits, nid)
            return SSeq([SNode(nid)]), [(nid, None, "normal")]
        retagged = [(src, label, "salto") for src, label, _ in exits]
        if kind == "break":
            ctx.breaks.extend(retagged)
        else:
            ctx.continues.extend(retagged)
        return SSeq([SJump(kind, ctx.sid)]), []

    def throw(self, st: Node, exits: list[Exit]):
        lang = self.lang
        value_nodes = [c for c in st.named_children if c.type not in self.spec.comment_nodes]
        if st.type == "expression_statement" and value_nodes:
            value_nodes = [c for c in value_nodes[0].named_children]
        value = _tech(" ".join(self.text(v) for v in value_nodes))
        shown = re.sub(r"^new\s+", "", value)
        nid = self.node(
            "proceso", f"Lanza excepción: {easy_expr(shown, lang)}", _tech(self.text(st)), st
        )
        self.link(exits, nid)
        ctx = self._innermost(("try",))
        if ctx is not None and ctx.catch_labels:
            idx = 0
            for i, label in enumerate(ctx.catch_labels):
                base = (
                    re.split(r"[\s(]", shown, maxsplit=1)[0].rsplit(".", 1)[-1].rsplit("\\", 1)[-1]
                )
                if base and base in label:
                    idx = i
                    break
            ctx.throws.append(((nid, "excepción", "excepcion"), idx))
            return SSeq([SNode(nid), SJump("throw", ctx.sid, idx)]), []
        end = self.node("terminal", "Fin (excepción)", "Fin (excepción)", st)
        self.edge(nid, end, "excepción", "excepcion")
        return SSeq([SNode(nid), SNode(end, stop=True)]), []

    # ------------------------------------------------------------------ with (Python)

    def with_(self, st: Node, exits: list[Exit]):
        clause = next((c for c in st.named_children if c.type == "with_clause"), None)
        header = clause if clause is not None else st
        info = self._compute_info(header)
        tech = "with " + _tech(self.text(header))
        if info.kind == "proceso":
            nid = self.node(
                "proceso",
                f"Con {easy_expr(_tech(self.text(header)), self.lang)}",
                tech,
                st,
                st.start_point[0] + 1,
            )
        else:
            nid = self.node(
                info.kind, info.easy, tech, st, st.start_point[0] + 1, info.call_id, info.target
            )
        self.link(exits, nid)
        seq, ex = self.block(
            self.statements(st.child_by_field_name("body")), [(nid, None, "normal")]
        )
        return SSeq([SNode(nid), *seq.items]), ex


def build_flow(
    spec: LangSpec,
    hooks: LangHooks,
    src: Src,
    path: str,
    symbol: Symbol,
    func: Node,
    calls: dict[str, CallInfo],
    max_nodes: int = 120,
) -> FlowResult:
    """Construye el flujo; si supera `max_nodes`, colapsa los bloques más profundos."""
    builder = FlowBuilder(spec, hooks, src, path, symbol, calls)
    result = builder.build(func)
    if len(result.graph.nodes) <= max_nodes:
        return result
    for limit in range(builder.max_depth - 1, -1, -1):
        b = FlowBuilder(spec, hooks, src, path, symbol, calls, depth_limit=limit)
        result = b.build(func)
        if len(result.graph.nodes) <= max_nodes:
            break
    graph = result.graph
    result.graph = FlowGraph(graph.symbol_id, graph.nodes, graph.edges, truncated=True)
    return result
