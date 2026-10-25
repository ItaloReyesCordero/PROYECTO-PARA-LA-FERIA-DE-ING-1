# Modelo intermedio (IR)

El IR es lo que Desglosa "entiende" de un proyecto, antes de dibujar nada. Está en
`src/desglosa/ir.py` y se puede exportar a JSON:

```powershell
uv run desglosa export-ir tests/fixtures/python -o ir.json
```

Todas las clases son `@dataclass(frozen=True, slots=True)` (inmutables) y se serializan
con claves ordenadas: el mismo código produce exactamente el mismo JSON.

## Ids estables

```
id = sha1("lenguaje|ruta|qualname|línea_inicio")[:12]
```

Nunca se usan `id()` de Python ni contadores, que cambiarían según el orden en que
terminen los procesos.

## Clases

### `Project`
La raíz: `root_name`, `files`, `symbols`, `imports`, `calls`, `flows`, `tables`, `fks`,
`table_access`, `warnings`.

### `SourceFile`
Un archivo encontrado por el escaneo.

| Campo | Tipo | Significado |
|---|---|---|
| `path` | str | ruta POSIX relativa a la carpeta analizada |
| `lang` | str | `python`, `php`, `c`, … o `sql` |
| `sha1` | str | hash del contenido |
| `lines` | int | número de líneas |
| `parsed_ok` | bool | el árbol sintáctico no tiene errores |
| `errors` | int | cuántos nodos de error encontró tree-sitter |
| `skipped_reason` | str \| None | por qué se saltó (binario, minificado, demasiado grande…) |

### `Symbol`
Algo con nombre que se puede dibujar.

| Campo | Significado |
|---|---|
| `id` | id estable |
| `kind` | `module`, `class`, `interface`, `function` o `method` |
| `name` / `qualname` | `emitir` / `FacturacionService.emitir` |
| `file`, `line_start`, `line_end` | dónde está |
| `parent_id` | clase o módulo que lo contiene |
| `doc` | docstring o comentario de documentación |
| `lang`, `signature` | lenguaje y primera línea de la definición |
| `is_entry` | punto de entrada (`main`, controlador, destino de una ruta) |

### `Import`
`file`, `module_text` (tal como está escrito), `alias`, `line` y `name` (el nombre
importado en `from m import NOMBRE`; `None` si se importa el módulo entero).

### `Call` y `ControlCtx`
Una llamada encontrada en el código.

| Campo | Significado |
|---|---|
| `id` | hash de lenguaje, archivo, función que llama, nombre y posición |
| `caller_id` | función que hace la llamada |
| `callee_text`, `receiver_text` | `cobrar` y `this.pagos` en `this.pagos.cobrar()` |
| `line`, `col` | posición |
| `context` | pila de `ControlCtx(kind, line, label)` que la envuelven: `if`, `else`, `loop`, `switch_case`, `try`, `catch` (se usa para los fragmentos de la secuencia) |
| `resolved_id` | definición a la que apunta, si se sabe |
| `candidates` | posibles destinos (interfaces o nombres repetidos) |
| `confidence` | `exacta`, `probable`, `ambigua` o `externa` |
| `io_kind` | `pantalla`, `teclado`, `archivo_lee`, `archivo_escribe` o `None` |

**Confianza**

- `exacta`: no hay duda (función del mismo archivo, `self.metodo()`, import explícito).
- `probable`: por el tipo declarado de una variable o porque el nombre es único.
- `ambigua`: varias definiciones posibles y ninguna pista para elegir.
- `externa`: no está en el proyecto (librería, función del sistema).

### `FlowGraph`, `FlowNode`, `FlowEdge`
El diagrama de flujo de una función.

- `FlowNode`: `id`, `kind` (ver [DISENO.md](DISENO.md)), `text_easy` (español),
  `text_tech` (código), `line_start`, `line_end`, `call_id` y `target_symbol` (la función
  que se abre al hacer clic en un subproceso).
- `FlowEdge`: `src`, `dst`, `label` (`sí`, `no`, `caso 1`…) y `kind` (`normal`,
  `retorno_bucle`, `excepcion`, `salto`).
- `FlowGraph`: `symbol_id`, `nodes`, `edges` y `truncated` (si se colapsaron bloques por
  ser una función gigante).

### SQL: `Table`, `Column`, `ForeignKey`, `TableAccess`

- `Table`: `id`, `name`, `file`, `line`, `columns`.
- `Column`: `name`, `type`, `not_null`, `primary_key`.
- `ForeignKey`: `table`, `columns` → `ref_table`, `ref_columns`, con `form` = `en_linea`
  (`REFERENCES` en la columna), `tabla` (`FOREIGN KEY` de tabla) o `alter`
  (`ALTER TABLE … ADD CONSTRAINT`).
- `TableAccess`: `symbol_id` lee o escribe (`mode`) la tabla `table` en la línea `line`,
  siempre con confianza `probable` (sale de buscar SQL dentro de cadenas).

## Extensiones respecto a la SPEC

- `Import.name` (para distinguir `import m` de `from m import x`).
- `ForeignKey.form` (para el test de las tres formas de FK).
- `TableAccess` como clase propia del IR.
