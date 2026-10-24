# Cómo agregar un lenguaje

Agregar un lenguaje = **un `LangSpec` + un fixture + un test** (RNF-07).

## Pasos

1. **Gramática.** Agrega el nombre a `LANGS` en `src/desglosa/grammars.py` y la extensión a
   `EXTENSIONS` en `src/desglosa/scan.py`. Ejecuta `uv run desglosa setup`.
2. **Fixture.** Escribe el mini-programa de facturación en `tests/fixtures/<lenguaje>/`
   (ver SPEC §14): clase `Factura`, `FacturacionService.emitir()` con if/else, for, while,
   switch, try/catch, return temprano, break/continue, llamada a `PagoService.cobrar()` en
   otro archivo, un print, una lectura de teclado y una escritura de archivo.
3. **Mira el AST real. No adivines.**
   ```powershell
   uv run desglosa debug-ast tests/fixtures/<lenguaje>/archivo.ext --depth 8
   uv run desglosa debug-ast archivo.ext --all     # incluye la puntuación
   ```
   Cada línea muestra `campo: tipo_de_nodo Lx-Ly "texto"`. El `campo` es lo que se usa con
   `child_by_field_name`.
4. **LangSpec.** Crea `src/desglosa/langs/<lenguaje>.py` con `SPEC = LangSpec(...)`
   (qué nodos son clases, funciones, ifs, bucles, etc.) y `HOOKS = Hooks(SPEC)`.
   Regístralo en `src/desglosa/langs/__init__.py`.
5. **Hooks.** La clase base `LangHooks` (`langs/spec.py`) funciona para lenguajes tipo C.
   Sobrescribe solo lo que cambie:
   - `symbol_name` / `symbol_qualifier`: dónde está el nombre de una función o clase.
   - `call_parts`: nombre llamado, receptor (`obj.`, `$obj->`, `Clase::`) y si es `new`.
   - `imports`: módulo, nombre importado y alias.
   - `bindings`: tipos de parámetros, variables y atributos (para la confianza "probable").
   - `class_bases`: herencia e interfaces.
   - `condition_node`, `case_value`, `catch_label`, `loop_label`: textos de control.
6. **Test.** Agrega el lenguaje a los tests parametrizados (`tests/test_extract.py`) y genera
   su golden con `uv run pytest --update-golden`. **Revisa el diff** del golden antes de
   confirmarlo.

## Campos extra del LangSpec (además de la tabla de la SPEC)

| Campo | Para qué |
|---|---|
| `parent_names` | receptores que apuntan a la clase padre (`super`, `parent`) |
| `implicit_this` | `metodo()` dentro de una clase llama a `this.metodo()` (Java, C++) |
| `constructor_names` | nombres del constructor (`__init__`, `constructor`, `__construct`) |
| `goto_nodes`, `label_nodes` | `goto` y etiquetas (C) |

## Correcciones a la tabla de la SPEC §6.2 (verificadas con `debug-ast`, 24/10/2026)

Gramáticas de `tree-sitter-language-pack` 1.22.1.

| Lenguaje | Lo que decía / suponía | Lo que hay realmente |
|---|---|---|
| Python | sentencias dentro de `expression_statement` | esta versión **no** usa `expression_statement`: `assignment`, `call`, `string` aparecen directo en `block` |
| Python | — | el docstring es un `string` como primer hijo del `block` |
| Python | `match_statement` | casos: `match_statement > body: block > alternative: case_clause (case_pattern, consequence)` |
| JS/TS | — | casos: `switch_body > switch_case (value, body…)` y `switch_default`; `for…of` es `for_in_statement` |
| JS/TS | — | `try_statement` → `handler: catch_clause`, `finalizer: finally_clause` |
| TS | — | parámetro con `private`/`public` = `required_parameter` con hijo `accessibility_modifier` |
| PHP | `if_statement (else_if_clause, else_clause)` | el cuerpo del if es el campo **`body`** (no `consequence`); `else_if_clause` y `else_clause` son **hermanos** dentro del `if`, no anidados |
| PHP | — | `throw` es `throw_expression` (dentro de `expression_statement`); `echo_statement` y `print_intrinsic` no son llamadas |
| PHP | — | casos: `switch_block > case_statement (value)` / `default_statement` |
| PHP | — | `foreach_statement` no tiene campos con nombre para la colección ni la variable |
| Java | — | **no existe `else_clause`**: el else es el campo `alternative` (un `if_statement` para `else if`, un `block` para `else`) |
| Java | `switch_expression` | correcto también para el `switch` clásico; casos: `switch_block_statement_group` (con `switch_label`) o `switch_rule` (`->`) |
| C | — | el nombre de función está en `declarator: function_declarator > declarator: identifier` (puede haber `pointer_declarator` en medio) |
| C | — | el `default` del switch es un `case_statement` **sin** campo `value` |
| C++ | — | método fuera de la clase: `declarator: qualified_identifier (scope, name)`; `std::cout << x` es `binary_expression`, no llamada |
| C++ | — | la condición de `if`/`while` viene entre paréntesis (`condition_clause`); se quitan al generar etiquetas |
