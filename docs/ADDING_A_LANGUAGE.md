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

## Ganchos del diagrama de flujo (`LangHooks`)

`flow.py` no conoce la forma del AST de ningún lenguaje: se la pide a estos métodos. La
clase base implementa el caso "tipo C"; sobrescribe solo lo que cambie.

| Método | Devuelve |
|---|---|
| `body_statements(nodo)` | sentencias de un cuerpo (aplana contenedores como `statement_list`) |
| `flow_kind(sentencia)` | `"if"`, `"loop"`, `"do_while"`, `"switch"`, `"try"`, `"return"`, `"break"`, `"continue"`, `"throw"`, `"goto"`, `"label"`, `"block"` o `None` (simple) |
| `control_kind(nodo)` | lo mismo pero solo por tipo de nodo (Kotlin/Swift miran la palabra clave) |
| `if_info` / `alt_info` | condición, rama "sí", alternativas (`elif`, `else if`, `else`); `negated` para `unless` |
| `loop_info` / `do_while_info` | tipo (`while`, `for`, `foreach`), condición, init/update, variable y colección |
| `switch_info` | sujeto, texto técnico y casos (`CaseInfo`: valor, sentencias, ¿cae al siguiente?) |
| `try_info` | cuerpo, `catch` (etiqueta + sentencias), `else` y `finally` |
| `jump_values` | expresión de un `return` / `throw` |
| `implicit_return` | ¿la última expresión es el valor de retorno? (Ruby, Rust, Kotlin `= expr`) |
| `if_branch` | para el contexto de las llamadas: ¿el hijo es condición, rama "sí" o "else"? |
| `statement_io` | E/S que no es una llamada (`gets` en Ruby) |
| `class_kind` | `"class"`, `"interface"` o `None` (Go `type X int`, Swift `extension`) |
| `extra_bases` | herencia declarada fuera de la clase (Rust `impl Trait for Tipo`) |
| `parameter_list` | parámetros para "Inicio: f(a, b)" (Swift no tiene nodo contenedor) |

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
| Go | `function_declaration, method_declaration` | correcto; además el método se ata a su tipo por el **receptor** (`func (s *T) M()`), como C++ `T::M` |
| Go | `for_statement` | el `for` lleva su condición **sin nombre de campo**, o dentro de `range_clause` (for-each) / `for_clause` (clásico) |
| Go | — | el cuerpo es `block > statement_list`; los casos de un switch también traen un `statement_list` |
| Go | `expression_switch_statement, type_switch_statement` | correcto; `fallthrough_statement` hace caer al caso siguiente; `default_case` es el por defecto |
| Go | — | `type_spec` sirve para struct, interfaz o alias: se decide mirando su campo `type` |
| Ruby | `method, singleton_method` | correcto; `def` fuera de una clase es una función |
| Ruby | `if, unless (elsif)` | además `if_modifier` / `unless_modifier` (`x if cond`) con campos `body` y `condition` |
| Ruby | bloques `.each do` | es una `call` con campo `block` (`do_block` o `block`); se dibuja como "Para cada" |
| Ruby | `begin + rescue` | `rescue (exceptions, variable, body: then)`, `ensure`; `raise` es una **llamada** |
| Ruby | — | `next` es el continue; `X.new(...)` es una llamada con receptor `X` y método `new` |
| Rust | `function_item` | correcto; los métodos viven en `impl_item` (campo `type`, y `trait` si es `impl Trait for T`) |
| Rust | `if_expression`… | las sentencias de control vienen dentro de `expression_statement`; la última expresión sin `;` es el valor de retorno |
| Rust | `match_expression` | `body: match_block > match_arm (pattern, value)`; el `_` es el caso por defecto |
| Rust | `macro_invocation` | `println!` etc. son macros, no `call_expression` |
| Kotlin | `function_declaration` | sin campo `name`: el nombre es el primer `simple_identifier` |
| Kotlin | — | `return/throw/break/continue` son todos `jump_expression` (se distinguen por la palabra clave) |
| Kotlin | `when_expression` | `when_subject`, `when_entry (when_condition…, control_structure_body)`; sin `when_condition` = `else` |
| Kotlin | — | una interfaz es `class_declaration` con la palabra `interface`; la herencia está en `delegation_specifier` |
| Swift | `function_declaration` | correcto; los parámetros cuelgan directo de la función; `init_declaration` es el constructor |
| Swift | `if_statement, guard_statement` | el `else` es un token seguido de `statements` o de otro `if_statement` (sin campo) |
| Swift | `do_statement + catch_block` | correcto; `return/throw/break/continue` son `control_transfer_statement` |
| Swift | — | `class_declaration` sirve para class/struct/enum/**extension** (campo `declaration_kind`); los métodos de una extension se atan al tipo extendido |
