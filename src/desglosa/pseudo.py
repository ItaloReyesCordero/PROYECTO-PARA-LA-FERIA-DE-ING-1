"""Pseudocódigo estilo PSeInt de una función (Bloque 4).

Se escribe con la misma estructura que dibuja el diagrama de flujo (`SSeq`, `SIf`,
`SLoop`…) y con el código completo de cada sentencia, no con el texto recortado de las
cajas. `FlowBuilder` llama a `statement` al crear cada nodo y a `render` al terminar.

Lo que PSeInt no tiene (retornar a mitad de una función, `break`, `continue`, `try`,
excepciones, objetos) se escribe como comentario `//`: así el `.psc` se sigue abriendo en
PSeInt y nada del código original se pierde.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING

from tree_sitter import Node

if TYPE_CHECKING:  # pragma: no cover
    from desglosa.flow import FlowBuilder

INDENT = "    "
_STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`")
_IDENT = re.compile(r"\$?[A-Za-z_]\w*")

# Tipos del código → tipos de PSeInt (solo los que tienen equivalente).
PS_TYPES = {
    **dict.fromkeys(
        ("int", "long", "short", "byte", "size_t", "Integer", "Long", "Short", "Byte", "Int",
         "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64",
         "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "isize", "usize", "Int32",
         "Int64", "UInt", "integer"),
        "Entero",
    ),
    **dict.fromkeys(
        ("float", "double", "Float", "Double", "decimal", "float32", "float64", "f32", "f64",
         "number", "Number", "real"),
        "Real",
    ),
    **dict.fromkeys(
        ("char", "string", "String", "str", "&str", "Character", "rune", "wchar_t"),
        "Caracter",
    ),
    **dict.fromkeys(("bool", "boolean", "Boolean", "Bool"), "Logico"),
}
_TYPE_WORDS = re.compile(r"\b(const|static|final|volatile|register|unsigned|signed|mut)\b")
# Objetos que solo preparan la lectura del teclado: en PSeInt basta con `Leer`.
_INPUT_SETUP = re.compile(r"new\s+(Scanner|BufferedReader|InputStreamReader)\b|bufio\.NewReader")


# --------------------------------------------------------------------------- expresiones


def _mask(text: str) -> str:
    """El texto con el interior de las cadenas tapado (mismas posiciones)."""
    return _STRING.sub(lambda m: m.group(0)[0] + "x" * (len(m.group(0)) - 2) + m.group(0)[-1],
                       text)


def _outside_strings(text: str, fn) -> str:
    out, pos = [], 0
    for m in _STRING.finditer(text):
        out.append(fn(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(text[pos:]))
    return "".join(out)


_MATH = (
    (re.compile(r"\b(?:Math\.|math\.|std::)?sqrt\s*\("), "raiz("),
    (re.compile(r"\b(?:Math\.|math\.|std::)?f?abs\s*\("), "abs("),
    (re.compile(r"\b(?:Math\.|math\.)?round\s*\("), "redon("),
    (re.compile(r"\b(?:Math\.|math\.|std::)?(?:floor|trunc)\s*\("), "trunc("),
)


def _code(s: str, lang: str) -> str:
    if lang == "php":
        s = s.replace("->", ".").replace("$", "")
        s = re.sub(r"\s\.\s", " + ", s)  # concatenación
    elif lang in ("c", "cpp"):
        s = s.replace("->", ".")
    s = s.replace("std::", "").replace("::", ".")
    for pattern, repl in _MATH:
        s = pattern.sub(repl, s)
    if lang == "python":
        s = re.sub(r"([\w.\]]+)\s*//\s*([\w.]+)", r"trunc(\1 / \2)", s)
    s = re.sub(r"!==|!=", " <> ", s)
    s = re.sub(r"===|==", " = ", s)
    s = s.replace("&&", " Y ").replace("||", " O ")
    s = re.sub(r"(?<![\w)\]])!(?!=)", " NO ", s)
    s = re.sub(r"\band\b", " Y ", s)
    s = re.sub(r"\bor\b", " O ", s)
    s = re.sub(r"\bnot\b", " NO ", s)
    s = s.replace("**", "^").replace("%", " MOD ")
    s = re.sub(r"\b(?:true|True|TRUE)\b", "Verdadero", s)
    s = re.sub(r"\b(?:false|False|FALSE)\b", "Falso", s)
    return re.sub(r"\s+", " ", s)


def expr(text: str, lang: str) -> str:
    """Una expresión del código con los operadores de PSeInt (`=`, `<>`, `Y`, `MOD`…)."""
    return _outside_strings(text.strip(), lambda s: _code(s, lang)).strip()


def _split_top(text: str, sep: str) -> list[str]:
    """Separa por `sep` fuera de cadenas y de (), [] y {}."""
    masked = _mask(text)
    out, depth, start, i = [], 0, 0, 0
    while i < len(masked):
        ch = masked[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and masked.startswith(sep, i):
            out.append(text[start:i])
            i += len(sep)
            start = i
            continue
        i += 1
    out.append(text[start:])
    return out


def _split_assign(text: str) -> tuple[str, str] | None:
    """`a = b` → ("a", "b"); no confunde `==`, `<=`, `=>` ni `+=`."""
    masked = _mask(text)
    depth = 0
    for i, ch in enumerate(masked):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == "=" and depth == 0:
            prev = masked[i - 1] if i else ""
            nxt = masked[i + 1] if i + 1 < len(masked) else ""
            if prev in "=!<>+-*/%&|^:.?" or nxt in "=>":
                continue
            return text[:i].strip(), text[i + 1:].strip()
    return None


def _unwrap_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for i, ch in enumerate(_mask(text)):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(text) - 1:
                return text
        text = text[1:-1].strip()
    return text


def condition(text: str, lang: str) -> str:
    return expr(_unwrap_parens(text), lang) or "Verdadero"


_INVERSE = {"=": "<>", "<>": "=", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}
_COMPARISON = re.compile(r"^(.+?)\s*(<>|<=|>=|=|<|>)\s*(.+)$")


def negate(cond: str) -> str:
    """`a < b` → `a >= b`; si hay más de una comparación, `NO (…)`."""
    masked = _mask(cond)
    ops = re.findall(r"<>|<=|>=|=|<|>", masked)
    words = re.search(r"\b(Y|O|NO)\b", masked)
    m = _COMPARISON.match(cond)
    if len(ops) == 1 and not words and m and "(" not in masked:
        return f"{m.group(1)} {_INVERSE[m.group(2)]} {m.group(3)}"
    if cond.startswith("NO (") and cond.endswith(")"):
        return cond[4:-1]
    if cond.startswith("NO ") and " " not in _mask(cond[3:]).strip():
        return cond[3:]
    if " " not in _mask(cond):
        return f"NO {cond}"
    return f"NO ({cond})"


def _minus_one(bound: str) -> str:
    bound = bound.strip()
    if re.fullmatch(r"-?\d+", bound):
        return str(int(bound) - 1)
    m = re.fullmatch(r"(.+?)\s*\+\s*1", bound)
    return m.group(1) if m else f"{bound} - 1"


def _plus_one(bound: str) -> str:
    bound = bound.strip()
    if re.fullmatch(r"-?\d+", bound):
        return str(int(bound) + 1)
    m = re.fullmatch(r"(.+?)\s*-\s*1", bound)
    return m.group(1) if m else f"{bound} + 1"


# --------------------------------------------------------------------------- textos de E/S


def _literal(text: str) -> tuple[str, str, str] | None:
    """(prefijo, comilla, contenido) si `text` es una sola cadena (`f"…"`, `$"…"`, `'…'`)."""
    m = re.fullmatch(r"([A-Za-z$@]{0,3})(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)",
                     text.strip(), re.S)
    if m is None:
        return None
    lit = m.group(2)
    return m.group(1), lit[0], lit[1:-1]


def _clean(body: str) -> str:
    body = body.replace("\\n", "").replace("\\r", "").replace("\\t", " ")
    return body.replace('\\"', "'").replace("\\'", "'").replace("\\\\", "\\")


def _quoted(body: str) -> str | None:
    text = _clean(body)
    if not text:
        return None
    return f"'{text}'" if '"' in text else f'"{text}"'


_INTERP = {
    "python": re.compile(r"\{\{|\}\}|\{([^{}]+)\}"),
    "csharp": re.compile(r"\{\{|\}\}|\{([^{}]+)\}"),
    "javascript": re.compile(r"\$\{([^}]+)\}"),
    "typescript": re.compile(r"\$\{([^}]+)\}"),
    "kotlin": re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_]\w*)"),
    "swift": re.compile(r"\\\(([^)]*)\)"),
    "ruby": re.compile(r"#\{([^}]+)\}"),
    "php": re.compile(r"\{\$([^}]+)\}|\$\{(\w+)\}|\$(\w+(?:->\w+)?)"),
}


def _interpolated(prefix: str, quote: str, lang: str) -> bool:
    if lang == "python":
        return "f" in prefix.lower()
    if lang == "csharp":
        return "$" in prefix
    if lang in ("javascript", "typescript"):
        return quote == "`"
    if lang in ("kotlin", "swift"):
        return quote == '"'
    if lang in ("ruby", "php"):
        return quote == '"'
    return False


def _string_parts(prefix: str, quote: str, body: str, lang: str) -> list[str]:
    if not _interpolated(prefix, quote, lang):
        q = _quoted(body)
        return [q] if q else []
    parts: list[str] = []
    pos = 0
    pattern = _INTERP[lang]
    literal = ""
    for m in pattern.finditer(body):
        literal += body[pos:m.start()]
        pos = m.end()
        inner = next((g for g in m.groups() if g), None)
        if inner is None:  # `{{` o `}}`
            literal += m.group(0)[0]
            continue
        q = _quoted(literal)
        if q:
            parts.append(q)
        literal = ""
        if lang in ("python", "csharp"):
            inner = re.split(r"(?<![=!<>]):(?!:)|!r$|!s$", inner)[0]
        parts.append(expr(inner, lang))
    literal += body[pos:]
    q = _quoted(literal)
    if q:
        parts.append(q)
    return parts


def _concat_split(text: str, lang: str) -> list[str]:
    if lang == "php":
        masked = _mask(text)
        cuts = [i for i, ch in enumerate(masked)
                if ch == "." and not (i and masked[i - 1].isdigit()
                                      and i + 1 < len(masked) and masked[i + 1].isdigit())]
        if not cuts:
            return [text]
        out, start = [], 0
        depth = 0
        for i, ch in enumerate(masked):
            depth += ch in "([{"
            depth -= ch in ")]}"
            if i in cuts and depth == 0:
                out.append(text[start:i])
                start = i + 1
        out.append(text[start:])
        return out
    return _split_top(text, "+")


def output_parts(arg: str, lang: str) -> list[str]:
    """Lo que se muestra, en partes para `Escribir a, b, c` (cadenas e interpolaciones)."""
    arg = arg.strip()
    lit = _literal(arg)
    if lit is not None:
        return _string_parts(*lit, lang)
    pieces = [p for p in _concat_split(arg, lang) if p.strip()]
    if len(pieces) > 1 and any(_literal(p) for p in pieces):
        return [x for p in pieces for x in output_parts(p, lang)]
    return [expr(arg, lang)] if arg else []


_FMT = re.compile(
    r"%%|%[-+ #0]*(?:\d+|\*)?(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t|q)?[diouxXeEfFgGcspnvTqb]"
)


def format_parts(fmt: str, args: list[str], lang: str) -> tuple[list[str], bool]:
    """`printf("Total: %d\\n", t)` → (['"Total: "', 't'], salta de línea)."""
    lit = _literal(fmt)
    if lit is None:
        return [x for a in [fmt, *args] for x in output_parts(a, lang)], True
    _, _, body = lit
    newline = body.endswith("\\n")
    parts: list[str] = []
    pos, i = 0, 0
    literal = ""
    for m in _FMT.finditer(body):
        literal += body[pos:m.start()]
        pos = m.end()
        if m.group(0) == "%%":
            literal += "%"
            continue
        q = _quoted(literal)
        if q:
            parts.append(q)
        literal = ""
        parts.append(expr(args[i], lang) if i < len(args) else "?")
        i += 1
    q = _quoted(literal + body[pos:])
    if q:
        parts.append(q)
    return parts, newline


def rust_format_parts(fmt: str, args: list[str]) -> list[str]:
    lit = _literal(fmt)
    if lit is None:
        return [expr(a, "rust") for a in [fmt, *args]]
    body = lit[2]
    parts: list[str] = []
    pos, i = 0, 0
    literal = ""
    for m in re.finditer(r"\{\{|\}\}|\{([^{}]*)\}", body):
        literal += body[pos:m.start()]
        pos = m.end()
        if m.group(0) in ("{{", "}}"):
            literal += m.group(0)[0]
            continue
        q = _quoted(literal)
        if q:
            parts.append(q)
        literal = ""
        name = m.group(1).split(":")[0].strip()
        if name.isdigit() and int(name) < len(args):
            parts.append(expr(args[int(name)], "rust"))
        elif name:
            parts.append(expr(name, "rust"))
        else:
            parts.append(expr(args[i], "rust") if i < len(args) else "?")
            i += 1
    q = _quoted(literal + body[pos:])
    if q:
        parts.append(q)
    return parts


def _merge(parts: list[str]) -> list[str]:
    """Une cadenas seguidas: `"a", " ", b` → `"a ", b`."""
    out: list[str] = []
    for part in parts:
        if out and part.startswith('"') and out[-1].startswith('"') and '"' not in part[1:-1]:
            out[-1] = out[-1][:-1] + part[1:]
        else:
            out.append(part)
    return out


def _spaced(groups: list[list[str]]) -> list[str]:
    """`print(a, b)` separa con un espacio; `Escribir a, b` no: se agrega `" "`."""
    out: list[str] = []
    for i, group in enumerate(g for g in groups if g):
        if i:
            out.append('" "')
        out.extend(group)
    return _merge(out)


def write_line(parts: list[str], newline: bool = True) -> str:
    verb = "Escribir" if newline else "Escribir Sin Saltar"
    return f"{verb} {', '.join(parts) if parts else chr(34) * 2}"


# --------------------------------------------------------------------------- sentencias

_NO_NEWLINE = {"print", "Print", "Write", "write", "putchar", "fputs", "putc", "printf",
               "Printf", "fprintf", "Fprintf", "print!", "eprint!"}
_PRINTF = {"printf", "fprintf", "Printf", "Fprintf", "format", "Sprintf", "sprintf"}
_SCANF = {"scanf": 1, "fscanf": 2, "Scan": 0, "Scanln": 0, "Scanf": 1, "Fscan": 1,
          "Fscanln": 1, "Fscanf": 2}


def _call_name(callee: str) -> str:
    return re.split(r"[.:>]", callee)[-1]


def _io_call(b: FlowBuilder, st: Node):
    for n, _cid, info, callee in b._calls_in(st):
        if info is not None and info.io_kind in ("pantalla", "teclado"):
            if n.type == "macro_invocation":  # Rust: los argumentos van en un token_tree
                tree = next((c for c in n.named_children if c.type == "token_tree"), None)
                inner = b.text(tree).strip()[1:-1] if tree is not None else ""
                return info.io_kind, callee, [a.strip() for a in _split_top(inner, ",")
                                               if a.strip()]
            parts = b.hooks.call_parts(n, b.src)
            return info.io_kind, callee, list(parts.args) if parts is not None else []
    return None


def _target(b: FlowBuilder, st: Node) -> str | None:
    target = b._assign_target(st)
    if target is None:
        return None
    if target.strip() in ("val", "var", "let", "const"):
        m = re.match(r"\s*(?:val|var|let|const)\s+(?:mut\s+)?([A-Za-z_]\w*)", b.text(st))
        target = m.group(1) if m else None
        if target is None:
            return None
    target = re.sub(r"^(?:let|const|var|val|mut|auto)\s+", "", target.strip())
    target = target.split(":")[0].strip()
    return expr(target, b.lang) or None


def _stream_io(raw: str, lang: str) -> list[str] | None:
    """`cout << a << b << endl` y `cin >> a >> b` (C++)."""
    if lang != "cpp":
        return None
    text = raw.strip().rstrip(";")
    for op, verb in (("<<", "Escribir"), (">>", "Leer")):
        pieces = [p.strip() for p in _split_top(text, op)]
        head = pieces[0].replace("std::", "") if pieces else ""
        if len(pieces) < 2:
            continue
        if verb == "Escribir" and head in ("cout", "cerr", "clog"):
            rest = pieces[1:]
            newline = False
            if rest and rest[-1].replace("std::", "") in ("endl", '"\\n"', "'\\n'"):
                newline = True
                rest = rest[:-1]
            elif rest and (lit := _literal(rest[-1])) and lit[2].endswith("\\n"):
                newline = True
            parts = [x for p in rest for x in output_parts(p, lang)]
            return [write_line(parts, newline)]
        if verb == "Leer" and head == "cin":
            return ["Leer " + ", ".join(expr(p, lang) for p in pieces[1:])]
    return None


def _echo(raw: str, lang: str) -> list[str] | None:
    """`echo "a", $b . "c";` (PHP)."""
    if lang != "php":
        return None
    m = re.match(r"^(echo|print)\b\s*(.*?);?\s*$", raw.strip(), re.S)
    if m is None:
        return None
    content = m.group(2)
    args = _split_top(content, ",")
    newline = "PHP_EOL" in content or content.rstrip().rstrip(")").endswith('\\n"')
    parts = [x for a in args for x in output_parts(a, lang) if x != "PHP_EOL"]
    return [write_line(parts, newline)]


def io_lines(b: FlowBuilder, st: Node, kind: str) -> list[str] | None:
    lang = b.lang
    raw = b.text(st)
    found = _io_call(b, st)
    if found is None:
        if kind == "pantalla":
            return _stream_io(raw, lang) or _echo(raw, lang)
        if kind == "teclado":
            stream = _stream_io(raw, lang)
            if stream:
                return stream
            target = _target(b, st)
            return [f"Leer {target}"] if target else ["Esperar Tecla"]
        return None
    io_kind, callee, args = found
    name = _call_name(callee)
    if io_kind == "teclado":
        if name in _SCANF:
            names = [expr(a.strip().lstrip("&"), lang) for a in args[_SCANF[name]:]]
            if names:
                return ["Leer " + ", ".join(names)]
        lines = []
        prompt = next((a for a in args if _literal(a)), None)
        if prompt is not None:
            parts = output_parts(prompt, lang)
            if parts:
                lines.append(write_line(parts, newline=False))
        if _INPUT_SETUP.search(b.text(st)):
            return []  # `bufio.NewReader(os.Stdin)`: solo prepara la lectura
        target = _target(b, st)
        if target is None:
            refs = [a.replace("&mut ", "").lstrip("&").strip() for a in args]
            refs = [r for r in refs if _IDENT.fullmatch(r)]
            target = ", ".join(expr(r, lang) for r in refs) or None
        lines.append(f"Leer {target}" if target else "Esperar Tecla")
        ps_type = _declared_type(b, st)
        if target and ps_type:
            lines.insert(0, f"Definir {target} Como {ps_type}")
        return lines
    # pantalla
    if lang == "python":
        newline = True
        shown = []
        end_text: list[str] = []
        for a in args:
            key = re.match(r"^\s*(\w+)\s*=(?!=)", a)
            if key is None:
                shown.append(a)
            elif key.group(1) == "end":
                value = a[key.end():].strip()
                newline = "\\n" in value
                lit = _literal(value)
                if lit is not None and (q := _quoted(lit[2])):
                    end_text = [q]  # `end=" "` también se muestra
        parts = _spaced([output_parts(a, lang) for a in shown])
        return [write_line(_merge(parts + end_text), newline)]
    if lang == "rust" and name.rstrip("!") in ("println", "print", "eprintln", "eprint"):
        parts = rust_format_parts(args[0], args[1:]) if args else []
        return [write_line(parts, name.rstrip("!") in ("println", "eprintln"))]
    if name in _PRINTF and args:
        if name in ("fprintf", "Fprintf"):
            args = args[1:]
        if args:
            parts, newline = format_parts(args[0], args[1:], lang)
            return [write_line(parts, newline)]
    if lang in ("swift",) and name == "print":
        newline = not any(re.match(r"\s*terminator\s*:", a) for a in args)
        args = [a for a in args if not re.match(r"\s*(terminator|separator)\s*:", a)]
        return [write_line([x for a in args for x in output_parts(a, lang)], newline)]
    if lang in ("javascript", "typescript") and name in ("log", "info", "warn", "error"):
        return [write_line(_spaced([output_parts(a, lang) for a in args]))]
    newline = name not in _NO_NEWLINE
    if name == "putchar" and args and args[0].strip() in ("'\\n'", "10"):
        return ['Escribir ""']
    parts = [x for a in args for x in output_parts(a, lang)]
    return [write_line(parts, newline)]


# Declaraciones con tipo (C, C++, Java, C#): `int a = 1, v[10];`.
_DECL_TYPES = {"declaration", "local_variable_declaration", "local_declaration_statement",
               "variable_declaration"}


def _ps_type(type_text: str) -> str | None:
    t = _TYPE_WORDS.sub("", type_text).replace("std::", "").strip()
    t = re.sub(r"\s+", " ", t).replace("[]", "").rstrip("*&? ").strip()
    if t.startswith("long"):
        t = "long"
    return PS_TYPES.get(t)


def _declarator(b: FlowBuilder, d: Node) -> tuple[str, list[str], Node | None]:
    value = d.child_by_field_name("value")
    if d.type == "variable_declarator":
        name = d.child_by_field_name("name")
        if name is None:
            return b.text(d), [], value
        if value is None:  # C#: el valor va sin campo
            rest = [c for c in d.named_children if c.id != name.id]
            value = rest[-1] if rest else None
        return b.text(name), [], value
    inner: Node | None = d.child_by_field_name("declarator") if d.type == "init_declarator" else d
    sizes: list[str] = []
    while inner is not None and inner.type in ("array_declarator", "pointer_declarator",
                                               "reference_declarator", "parenthesized_declarator"):
        if inner.type == "array_declarator":
            size = inner.child_by_field_name("size")
            sizes.insert(0, b.text(size) if size is not None else "")
        nxt = inner.child_by_field_name("declarator")
        if nxt is None:
            nxt = next((c for c in inner.named_children), None)
        inner = nxt
    return (b.text(inner) if inner is not None else b.text(d)), sizes, value


def _declared_type(b: FlowBuilder, st: Node) -> str | None:
    if b.lang not in ("c", "cpp", "java", "csharp") or st.type not in _DECL_TYPES:
        return None
    node = st
    if node.type == "local_declaration_statement":
        node = next((c for c in node.named_children if c.type == "variable_declaration"), node)
    type_node = node.child_by_field_name("type")
    return _ps_type(b.text(type_node)) if type_node is not None else None


def typed_declaration(b: FlowBuilder, st: Node) -> list[str] | None:
    lang = b.lang
    if lang not in ("c", "cpp", "java", "csharp") or st.type not in _DECL_TYPES:
        return None
    node = st
    if node.type == "local_declaration_statement":
        node = next((c for c in node.named_children if c.type == "variable_declaration"), node)
    type_node = node.child_by_field_name("type")
    if type_node is None:
        return None
    type_text = b.text(type_node)
    ps_type = _ps_type(type_text)
    decls = node.children_by_field_name("declarator") or [
        c for c in node.named_children if c.type == "variable_declarator"]
    if not decls:
        return None
    names, dims, sets = [], [], []
    for d in decls:
        name, sizes, value = _declarator(b, d)
        name = name.strip()
        value_text = b.text(value).strip() if value is not None else ""
        if value_text and _INPUT_SETUP.search(value_text):
            continue
        names.append(name)
        new_array = re.match(r"new\s+[\w.]+\s*((?:\[[^\]]+\])+)", value_text)
        if new_array:
            sizes = re.findall(r"\[([^\]]+)\]", new_array.group(1))
            value_text = ""
        if "[]" in type_text and not sizes and value_text.startswith("{"):
            sizes = [""]
        if sizes:
            items = []
            if value_text.startswith("{") and value_text.endswith("}"):
                items = [x.strip() for x in _split_top(value_text[1:-1], ",") if x.strip()]
                value_text = ""
            count = sizes[0] or (str(len(items)) if items else "")
            if count:
                dims.append(f"Dimension {name}[{', '.join([count, *sizes[1:]])}]")
            if len(items) <= 12:
                sets += [f"{name}[{i}] <- {expr(x, lang)}" for i, x in enumerate(items)]
            else:
                sets.append(f"// {name} <- {{{', '.join(expr(x, lang) for x in items[:3])}, …}}")
            continue
        if value_text:
            sets.append(f"{expr(name, lang)} <- {expr(value_text, lang)}")
    lines = []
    if ps_type and names:
        lines.append(f"Definir {', '.join(expr(n, lang) for n in names)} Como {ps_type}")
    return lines + dims + sets


_DECL_KW = re.compile(r"^(?:(?:let|const|var|val|auto|mut|my|local|final|static|readonly)\s+)+")
_UPDATE = re.compile(r"(\+\+|--)?\s*([$@\w][\w.\[\]$>-]*?)\s*(\+\+|--)?")
_AUG = re.compile(r"^(.+?)\s*(\*\*|//|<<|>>|[-+*/%.])=\s*(.+)$", re.S)
_READ_METHOD = re.compile(r"^[\w.]+\.(?:ReadString|ReadLine|ReadRune|Text)\(")
_GO_VAR = re.compile(r"^var\s+(\w+)(?:\s+([\w.\[\]*]+))?(?:\s*=\s*(.+))?$", re.S)


def simple(raw: str, lang: str) -> list[str]:
    """Una sentencia sin estructura: asignación, incremento, declaración o llamada."""
    text = raw.strip().rstrip(";").strip()
    if not text or text in ("pass", "...", "{}"):
        return []
    if lang == "go":
        m = _GO_VAR.match(text)
        if m:
            name, typ, value = m.groups()
            lines = []
            if typ and PS_TYPES.get(typ):
                lines.append(f"Definir {name} Como {PS_TYPES[typ]}")
            if value:
                lines.append(f"{name} <- {expr(value, lang)}")
            return lines
        parts = _split_top(text, ":=")
        if len(parts) == 2:
            if _READ_METHOD.search(parts[1].strip()):  # `s, _ := lector.ReadString('\n')`
                names = [n.strip() for n in _split_top(parts[0], ",") if n.strip() != "_"]
                return [f"Leer {', '.join(names)}"]
            return [f"{expr(parts[0], lang)} <- {expr(parts[1], lang)}"]
    text = _DECL_KW.sub("", text)
    m = _UPDATE.fullmatch(text)
    if m and bool(m.group(1)) != bool(m.group(3)):
        op = "+" if "++" in (m.group(1) or m.group(3)) else "-"
        var = expr(m.group(2), lang)
        return [f"{var} <- {var} {op} 1"]
    m = _AUG.match(text)
    if m and _split_assign(text) is None:
        left, op, right = expr(m.group(1), lang), m.group(2), expr(m.group(3), lang)
        op = {"%": "MOD", ".": "+", "**": "^"}.get(op, op)
        if op == "//":
            return [f"{left} <- trunc({left} / ({right}))"]
        wrapped = _unwrap_parens(right) != right
        if op != "+" and not wrapped and re.search(r"[-+*/^]| MOD ", _mask(right)):
            right = f"({right})"
        return [f"{left} <- {left} {op} {right}"]
    pair = _split_assign(text)
    if lang == "go" and pair is None and ":=" in text:
        pair = tuple(x.strip() for x in text.split(":=", 1))
    if pair is not None and _READ_METHOD.search(pair[1]):
        names = [n.strip() for n in _split_top(pair[0], ",") if n.strip() not in ("_", "")]
        return [f"Leer {', '.join(expr(n, lang) for n in names)}"] if names else []
    if pair is not None:
        left, right = pair
        left = re.sub(r"^([\w$@.]+)\s*:\s*.+$", r"\1", left, flags=re.S)  # `x: int = 5`
        return [f"{expr(left, lang)} <- {expr(right, lang)}"]
    m = re.fullmatch(r"([A-Za-z_]\w*)\s*:\s*([\w.<>\[\]?&]+)", text)  # `let x: number`
    if m:
        ps_type = PS_TYPES.get(m.group(2).rstrip("?"))
        return [f"Definir {m.group(1)} Como {ps_type}"] if ps_type else []
    return [expr(text, lang)]


def statement(b: FlowBuilder, st: Node) -> list[str]:
    """Las líneas de PSeInt de una sentencia del código."""
    info = b.info(st)
    kind = info.kind
    if kind not in ("pantalla", "teclado"):
        # `printf("%c", letra(p))`: el diagrama la marca como subproceso por `letra`, pero
        # la sentencia es una salida.
        calls = b._calls_in(st)
        outer = calls[0][2] if calls else None
        if outer is not None and outer.io_kind in ("pantalla", "teclado"):
            kind = outer.io_kind
    if kind in ("pantalla", "teclado"):
        lines = io_lines(b, st, kind)
        if lines is not None:
            return lines
    name = b._is_definition(st)
    if name:
        return [f"// define {name}"]
    typed = typed_declaration(b, st)
    if typed is not None:
        return typed
    return simple(b.text(st), b.lang)


# --------------------------------------------------------------------------- bucles


def _range(var: str, coll: str, lang: str) -> tuple[str, str, str, str] | None:
    """`for i in range(n)`, `0 until n`, `0..n`, `0..<n`… → (var, desde, hasta, paso)."""
    var, coll = var.strip(), coll.strip()
    if not _IDENT.fullmatch(var):
        return None
    if lang == "python":
        m = re.fullmatch(r"range\((.*)\)", coll, re.S)
        if m is None:
            return None
        args = [a.strip() for a in _split_top(m.group(1), ",") if a.strip()]
        if len(args) == 1:
            return var, "0", _minus_one(args[0]), "1"
        if len(args) == 2:
            return var, args[0], _minus_one(args[1]), "1"
        if len(args) == 3:
            down = args[2].startswith("-")
            end = _plus_one(args[1]) if down else _minus_one(args[1])
            return var, args[0], end, args[2]
        return None
    step = "1"
    m = re.fullmatch(r"(.+?)\s+step\s+(.+)", coll)
    if lang == "kotlin" and m:
        coll, step = m.group(1), m.group(2)
    patterns = {
        "kotlin": ((r"(.+?)\s+until\s+(.+)", "excl"), (r"(.+?)\s+downTo\s+(.+)", "down"),
                   (r"(.+?)\.\.<(.+)", "excl"), (r"(.+?)\.\.(.+)", "incl")),
        "rust": ((r"(.+?)\.\.=(.+)", "incl"), (r"(.+?)\.\.(.+)", "excl")),
        "swift": ((r"(.+?)\.\.<(.+)", "excl"), (r"(.+?)\.\.\.(.+)", "incl")),
        "ruby": ((r"\(?(.+?)\.\.\.(.+?)\)?", "excl"), (r"\(?(.+?)\.\.(.+?)\)?", "incl")),
    }
    for pattern, mode in patterns.get(lang, ()):
        m = re.fullmatch(pattern, coll)
        if m:
            a, z = m.group(1).strip(), m.group(2).strip()
            if mode == "excl":
                return var, a, _minus_one(z), step
            if mode == "down":
                return var, a, z, f"-{step}"
            return var, a, z, step
    return None


def counting_for(init: str, cond: str, update: str, lang: str):
    """`for (int i = 0; i < n; i++)` → (var, desde, hasta, paso) si cuenta de a pasos fijos."""
    init = init.strip().rstrip(";").replace(":=", "=")
    mi = re.fullmatch(r"(?:[\w:<>]+\s+)*?\$?([A-Za-z_]\w*)\s*=\s*([^,]+)", init)
    mc = re.fullmatch(r"\$?([A-Za-z_]\w*)\s*(<=|<|>=|>)\s*(.+)", _unwrap_parens(cond).strip())
    if mi is None or mc is None or mi.group(1) != mc.group(1):
        return None
    var = mi.group(1)
    up = update.strip().rstrip(";")
    step = None
    if re.fullmatch(rf"\$?{var}\s*\+\+|\+\+\s*\$?{var}", up):
        step = "1"
    elif re.fullmatch(rf"\$?{var}\s*--|--\s*\$?{var}", up):
        step = "-1"
    else:
        m = re.fullmatch(rf"\$?{var}\s*(\+|-)=\s*(.+)", up) or re.fullmatch(
            rf"\$?{var}\s*=\s*\$?{var}\s*(\+|-)\s*(.+)", up)
        if m:
            step = m.group(2).strip() if m.group(1) == "+" else f"-{m.group(2).strip()}"
    if step is None:
        return None
    down = step.startswith("-")
    op, bound = mc.group(2), mc.group(3).strip()
    if down != (op in (">", ">=")):
        return None
    end = {"<": _minus_one, ">": _plus_one}.get(op, lambda x: x)(bound)
    return var, mi.group(2).strip(), end, step


# --------------------------------------------------------------------------- escritura


def _ps_name(name: str) -> str:
    name = re.sub(r"\W", "_", name).strip("_") or "funcion"
    return f"f_{name}" if name[0].isdigit() else name


_LITERALS = {"true", "false", "True", "False", "TRUE", "FALSE", "null", "None", "nil",
             "NULL", "nullptr", "undefined", "this", "self", "NaN"}


def is_main(name: str) -> bool:
    return name in ("main", "Main")


def render(b: FlowBuilder, struct, name: str | None = None) -> str:
    """El pseudocódigo completo de la función que construyó `b`."""
    from desglosa.flow import SDoWhile, SIf, SJump, SLoop, SNode, SSeq, SSwitch, STry

    lang = b.lang
    sym = b.symbol
    nodes = {n.id: n for n in b.nodes}
    returns = b.ps_returns
    main = is_main(sym.name)
    values = [v.strip() for v in returns.values() if v.strip()]
    result = None
    if values and not main:
        distinct = set(values)
        only = distinct.pop() if len(distinct) == 1 else ""
        plain = _IDENT.fullmatch(only) and only.lstrip("$") not in _LITERALS
        result = expr(only, lang) if plain else "resultado"
    params = b.ps_params
    if main:
        stem = posixpath.splitext(posixpath.basename(b.path))[0]
        title = _ps_name(name or stem)
        out = [f"Algoritmo {title}"]
        footer = "FinAlgoritmo"
    else:
        title = _ps_name(name or sym.name)
        head = f"{result} <- {title}" if result else title
        out = [f"Funcion {head}({params})"]
        footer = "FinFuncion"
    kinds: dict[int, str] = {}

    def emit(line: str, depth: int) -> None:
        out.append(INDENT * depth + line)

    def node_lines(nid: str) -> list[str]:
        lines = b.ps.get(nid)
        if lines is not None:
            return lines
        node = nodes.get(nid)
        if node is None:
            return []
        return [x for t in node.text_tech.split("\n") for x in simple(t, lang)]

    def ret(nid: str, early: bool, depth: int) -> None:
        value = returns[nid].strip()
        tail = "  // y termina la función" if early else ""
        if main:
            if early:
                emit("// termina el algoritmo", depth)
            return
        if value:
            v = expr(value, lang)
            if v == result and not early:
                return
            emit(f"{result} <- {v}{tail}", depth)
        elif early:
            emit("// termina la función", depth)

    def walk(seq, depth: int) -> None:
        items = seq.items
        for i, it in enumerate(items):
            nxt = items[i + 1] if i + 1 < len(items) else None
            if isinstance(it, SNode):
                node = nodes.get(it.node_id)
                if it.stop or node is None or node.kind == "terminal":
                    continue
                if it.node_id in returns:
                    ret(it.node_id, isinstance(nxt, SNode) and nxt.stop, depth)
                    continue
                for line in node_lines(it.node_id):
                    emit(line, depth)
            elif isinstance(it, SIf):
                meta = b.ps_meta.get(it.dec, {})
                cond = condition(meta.get("cond") or nodes[it.dec].text_tech, lang)
                if meta.get("negated"):
                    cond = negate(cond)
                emit(f"Si {cond} Entonces", depth)
                walk(it.yes, depth + 1)
                if it.no is not None and it.no.items:
                    emit("SiNo", depth)
                    walk(it.no, depth + 1)
                emit("FinSi", depth)
            elif isinstance(it, SLoop):
                kinds[it.sid] = "bucle"
                loop(it, depth)
            elif isinstance(it, SDoWhile):
                kinds[it.sid] = "bucle"
                meta = b.ps_meta.get(it.dec, {})
                cond = condition(meta.get("cond") or nodes[it.dec].text_tech, lang)
                emit("Repetir", depth)
                walk(it.body, depth + 1)
                emit(f"Hasta Que {cond if meta.get('negated') else negate(cond)}", depth)
            elif isinstance(it, SSwitch):
                kinds[it.sid] = "Segun"
                meta = b.ps_meta.get(it.dec, {})
                emit(f"Segun {expr(meta.get('subject', ''), lang)} Hacer", depth)
                values_of = meta.get("cases", [])
                for k, case in enumerate(it.cases):
                    vals = values_of[k] if k < len(values_of) else [None]
                    if None in vals:
                        last = k == len(it.cases) - 1
                        if not case.body.items and meta.get("auto_default") and last:
                            continue  # el «otro» que agrega el diagrama, sin código
                        emit("De Otro Modo:", depth + 1)
                    else:
                        emit(", ".join(expr(v, lang) for v in vals) + ":", depth + 1)
                    walk(case.body, depth + 2)
                    if case.falls_through:
                        emit("// sigue con el caso siguiente (no hay break)", depth + 2)
                emit("FinSegun", depth)
            elif isinstance(it, STry):
                emit("// Intentar (try):", depth)
                walk(it.body, depth + 1)
                for label, seq_c in it.catches:
                    emit(f"// Si ocurre un error ({label}):", depth)
                    walk(seq_c, depth + 1)
                if it.final is not None:
                    emit("// Al final, siempre (finally):", depth)
                    walk(it.final, depth + 1)
                emit("// Fin del intentar", depth)
            elif isinstance(it, SJump):
                if it.kind == "continue":
                    emit("// pasa a la siguiente vuelta (continue)", depth)
                elif it.kind == "break":
                    where = kinds.get(it.target, "bucle")
                    emit(f"// sale del {where} (break)", depth)
            elif isinstance(it, SSeq):
                walk(it, depth)

    def loop(it, depth: int) -> None:
        meta = b.ps_meta.get(it.dec, {})
        kind = meta.get("loop", it.kind)
        if kind == "foreach":
            var, coll = meta.get("var", ""), meta.get("coll", "")
            rng = _range(var, coll, lang)
            if rng:
                emit(_para(rng, lang), depth)
            else:
                target = expr(var, lang) if var else "elemento"
                emit(f"Para Cada {target} de {expr(coll, lang)} Hacer", depth)
            walk(it.body, depth + 1)
            emit("FinPara", depth)
            return
        if kind == "for":
            rng = counting_for(meta.get("init", ""), meta.get("cond", ""),
                               meta.get("update", ""), lang)
            if rng:
                emit(_para(rng, lang), depth)
                walk(it.body, depth + 1)
                emit("FinPara", depth)
                return
            if it.init:
                for line in node_lines(it.init):
                    emit(line, depth)
        cond = condition(meta.get("cond", ""), lang)
        if meta.get("negated"):
            cond = negate(cond)
        emit(f"Mientras {cond} Hacer", depth)
        walk(it.body, depth + 1)
        if it.update:
            for line in node_lines(it.update):
                emit(line, depth + 1)
        emit("FinMientras", depth)

    walk(struct, 1)
    out.append(footer)
    return "\n".join(out) + "\n"


def _para(rng: tuple[str, str, str, str], lang: str) -> str:
    var, start, end, step = rng
    paso = "" if step.strip() == "1" else f" Con Paso {expr(step, lang)}"
    return f"Para {expr(var, lang)} <- {expr(start, lang)} Hasta {expr(end, lang)}{paso} Hacer"
