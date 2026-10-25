"""SQL: tablas, columnas, PK y FK; enlace función → tabla (SPEC §9).

- Cada sentencia se separa con su línea y se lee con sqlglot en el dialecto pedido; si
  falla, se reintenta con mysql, postgres, sqlite y tsql. Si nada funciona, se registra una
  advertencia y se sigue.
- Las FK se reconocen en sus tres formas: `REFERENCES` en la columna, `FOREIGN KEY (…)
  REFERENCES …` en la tabla y `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY`.
- El enlace función → tabla busca SQL dentro de las cadenas del código: `FROM`/`JOIN`
  (lee) e `INSERT INTO`/`UPDATE`/`DELETE FROM` (escribe). Confianza "probable".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from desglosa.ir import Column, ForeignKey, Symbol, Table, TableAccess, stable_id

FALLBACK_DIALECTS = ("mysql", "postgres", "sqlite", "tsql")


@dataclass
class SqlModel:
    tables: list[Table] = field(default_factory=list)
    fks: list[ForeignKey] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- separar sentencias


def split_statements(text: str) -> list[tuple[str, int]]:
    """Sentencias separadas por `;` (respetando comillas y comentarios) con su línea."""
    out: list[tuple[str, int]] = []
    i, n = 0, len(text)
    start = 0
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == quote:
                if i + 1 < n and text[i + 1] == quote:  # comilla escapada ('')
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote != "`":
                i += 1
        elif ch in ("'", '"', "`"):
            quote = ch
        elif (ch == "-" and text.startswith("--", i)) or (
            ch == "#" and (i == 0 or text[i - 1] == "\n")
        ):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif ch == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        elif ch == ";":
            _push(text, start, i, out)
            start = i + 1
        i += 1
    _push(text, start, n, out)
    return out


def _push(text: str, start: int, end: int, out: list[tuple[str, int]]) -> None:
    chunk = text[start:end]
    body = _strip_comments(chunk).strip()
    if not body:
        return
    offset = start + (len(chunk) - len(chunk.lstrip()))
    # Saltar comentarios iniciales para que la línea apunte a la sentencia.
    m = re.match(r"(\s*(--[^\n]*\n|/\*.*?\*/|#[^\n]*\n))*\s*", text[offset:end], re.S)
    if m:
        offset += m.end()
    out.append((chunk, text.count("\n", 0, offset) + 1))


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _parse_one(sql: str, dialect: str | None) -> exp.Expression | None:
    tried: list[str] = []
    for d in ([dialect] if dialect else []) + list(FALLBACK_DIALECTS):
        if d in tried:
            continue
        tried.append(d)
        try:
            parsed = [e for e in sqlglot.parse(sql, read=d) if e is not None]
        except Exception:  # sqlglot lanza varios tipos de error de parseo
            continue
        if parsed:
            return parsed[0]
    return None


# --------------------------------------------------------------------------- tablas


def _name(node: exp.Expression | None) -> str:
    if node is None:
        return ""
    if isinstance(node, exp.Schema):
        node = node.this
    if isinstance(node, exp.Table):
        return node.name
    return getattr(node, "name", "") or node.sql()


def _ref_parts(ref: exp.Reference) -> tuple[str, tuple[str, ...]]:
    target = ref.this
    if isinstance(target, exp.Schema):
        cols = tuple(_name(c) for c in target.expressions)
        return _name(target.this), cols
    return _name(target), ()


def parse_sql(path: str, text: str, dialect: str | None = None) -> SqlModel:
    model = SqlModel()
    for sql, line in split_statements(text):
        stmt = _parse_one(sql, dialect)
        if stmt is None:
            model.warnings.append(f"{path}:{line}: no se pudo leer la sentencia SQL")
            continue
        if isinstance(stmt, exp.Create) and str(stmt.args.get("kind", "")).upper() == "TABLE":
            _create_table(path, line, stmt, model)
        elif isinstance(stmt, exp.Alter):
            table = _name(stmt.this)
            for fk in stmt.find_all(exp.ForeignKey):
                _add_fk(path, line, table, fk, "alter", model)
    return model


def _create_table(path: str, line: int, stmt: exp.Create, model: SqlModel) -> None:
    schema = stmt.this
    if not isinstance(schema, exp.Schema):
        return
    table_name = _name(schema.this)
    pk_cols: set[str] = set()
    for e in schema.expressions:
        if isinstance(e, exp.PrimaryKey):
            pk_cols.update(_name(c) for c in e.expressions)
    columns: list[Column] = []
    for e in schema.expressions:
        if isinstance(e, exp.ColumnDef):
            kinds = [c.args.get("kind") for c in e.args.get("constraints") or []]
            not_null = any(isinstance(k, exp.NotNullColumnConstraint) for k in kinds)
            is_pk = e.name in pk_cols or any(
                isinstance(k, exp.PrimaryKeyColumnConstraint) for k in kinds
            )
            kind = e.args.get("kind")
            columns.append(Column(e.name, kind.sql() if kind is not None else "", not_null, is_pk))
            for k in kinds:
                if isinstance(k, exp.Reference):
                    ref_table, ref_cols = _ref_parts(k)
                    model.fks.append(
                        ForeignKey(
                            id=stable_id(
                                "sql", path, f"fk:{table_name}:{e.name}->{ref_table}", line
                            ),
                            table=table_name,
                            columns=(e.name,),
                            ref_table=ref_table,
                            ref_columns=ref_cols,
                            file=path,
                            line=line,
                            form="en_linea",
                        )
                    )
        elif isinstance(e, exp.ForeignKey):
            _add_fk(path, line, table_name, e, "tabla", model)
    model.tables.append(
        Table(
            id=stable_id("sql", path, table_name, line),
            name=table_name,
            file=path,
            line=line,
            columns=tuple(columns),
        )
    )


def _add_fk(
    path: str, line: int, table: str, fk: exp.ForeignKey, form: str, model: SqlModel
) -> None:
    cols = tuple(_name(c) for c in fk.expressions)
    ref = fk.args.get("reference")
    if ref is None:
        return
    ref_table, ref_cols = _ref_parts(ref)
    model.fks.append(
        ForeignKey(
            id=stable_id("sql", path, f"fk:{table}:{','.join(cols)}->{ref_table}", line),
            table=table,
            columns=cols,
            ref_table=ref_table,
            ref_columns=ref_cols,
            file=path,
            line=line,
            form=form,
        )
    )


def merge(models: list[SqlModel]) -> SqlModel:
    """Une varios archivos: la primera definición de cada tabla gana; FK sin duplicados."""
    out = SqlModel()
    seen_tables: set[str] = set()
    seen_fks: set[tuple] = set()
    for m in models:
        for t in m.tables:
            if t.name.lower() not in seen_tables:
                seen_tables.add(t.name.lower())
                out.tables.append(t)
        for fk in m.fks:
            key = (fk.table.lower(), fk.columns, fk.ref_table.lower())
            if key not in seen_fks:
                seen_fks.add(key)
                out.fks.append(fk)
        out.warnings.extend(m.warnings)
    out.tables.sort(key=lambda t: (t.name.lower(), t.file, t.line))
    out.fks.sort(key=lambda f: (f.table.lower(), f.columns, f.ref_table.lower(), f.line))
    return out


# --------------------------------------------------------------------------- función → tabla

_STRING = re.compile(
    r'"""(.*?)"""|\'\'\'(.*?)\'\'\'|"((?:\\.|[^"\\\n])*)"|\'((?:\\.|[^\'\\\n])*)\'|`([^`]*)`',
    re.S,
)
_LOOKS_SQL = re.compile(r"\b(select|insert|update|delete)\b", re.I)
_IDENT = r"[`\"\[]?([A-Za-z_][\w.]*)[`\"\]]?"
_WRITES = re.compile(
    r"\binsert\s+(?:ignore\s+)?into\s+" + _IDENT
    + r"|\bupdate\s+" + _IDENT
    + r"|\bdelete\s+from\s+" + _IDENT,
    re.I,
)
_READS = re.compile(r"(?<!delete\s)\bfrom\s+" + _IDENT + r"|\bjoin\s+" + _IDENT, re.I)


def table_access(
    symbols: list[Symbol], sources: dict[str, str], known_tables: list[str]
) -> list[TableAccess]:
    """Tablas leídas/escritas por cada función según el SQL que aparece en sus cadenas."""
    known = {t.lower(): t for t in known_tables}
    out: dict[tuple[str, str, str], TableAccess] = {}
    for sym in symbols:
        if sym.kind not in ("function", "method"):
            continue
        text = sources.get(sym.file)
        if not text:
            continue
        lines = text.split("\n")
        body = "\n".join(lines[sym.line_start - 1 : sym.line_end])
        for m in _STRING.finditer(body):
            content = next(g for g in m.groups() if g is not None)
            if not _LOOKS_SQL.search(content):
                continue
            line = sym.line_start + body.count("\n", 0, m.start())
            for mode, regex in (("escribe", _WRITES), ("lee", _READS)):
                for hit in regex.finditer(content):
                    raw = next(g for g in hit.groups() if g is not None)
                    name = raw.rsplit(".", 1)[-1]
                    if known and name.lower() not in known:
                        continue
                    table = known.get(name.lower(), name)
                    key = (sym.id, table, mode)
                    if key not in out:
                        out[key] = TableAccess(sym.id, table, mode, line, "probable")
    return sorted(out.values(), key=lambda a: (a.symbol_id, a.table, a.mode))
