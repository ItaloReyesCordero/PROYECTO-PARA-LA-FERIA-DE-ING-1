# SPEC — Desglosa

> Especificación maestra. Claude Code: este archivo es la fuente de verdad del proyecto.
> Léelo completo antes de escribir código. Si algo aquí es ambiguo o contradictorio, PREGUNTA; no inventes.

- **Nombre:** Desglosa (comando `desglosa`, paquete Python `desglosa`)
- **Título corto (GitHub):** Desglosa — mapas, diagramas de flujo y de secuencia interactivos a partir de tu código, sin IA.
- **Título formal (feria / universidad):** Desglosa: herramienta de ingeniería inversa para la generación automática y navegable de diagramas de flujo y de secuencia a partir de código fuente multilenguaje.
- **Autor:** Italo Reyes Cordero — Ingeniería de Sistemas e Informática, Universidad Continental (Huancayo, Perú).
- **Licencia:** MIT.
- **Sistema del autor:** Windows + PowerShell. Todo debe funcionar en Windows primero (y también en Linux/macOS).

---

## 0. Qué es, en una frase

Una herramienta de línea de comandos en Python que lee una carpeta de código, **sin IA, sin tokens y sin internet**, y genera **un solo archivo `.html`** que se abre con doble clic, donde puedes navegar así:

```
Mapa del proyecto → clic en un módulo → clic en una clase/archivo → clic en una función
   → diagrama de flujo de esa función (rombos sí/no, bucles, etc.)
      → clic en una llamada (subproceso) → diagrama de flujo de la función llamada → …
```

Además ofrece una vista **secuencial** (UML, técnica) y un **diagrama entidad-relación** cuando hay SQL.

Inspiración conceptual (NO se copia código de ninguno): Graphify (código → grafo, Apache-2.0) y Archify (JSON → HTML interactivo, MIT). Desglosa une ambas ideas y agrega lo que ninguna tiene: **niveles + layout automático + desglose hasta el diagrama de flujo de cada función.**

---

## 1. Reglas no negociables

1. **Código propio desde cero.** Prohibido copiar, vendorizar o importar código de Graphify o Archify. Prohibido instalarlos como dependencia.
2. **Librerías de terceros permitidas (y solo estas en runtime):** `tree-sitter`, `tree-sitter-language-pack` (solo `get_parser`/`get_language`/`download`/`downloaded_languages`; **NO** usar sus APIs de alto nivel `process`, `SymbolInfo`, `get_tags_query`, etc.: el motor de extracción es nuestro), `sqlglot`, `pathspec`. CLI con `argparse` (stdlib). Dev: `pytest`, `ruff`. Cualquier otra dependencia: preguntar antes.
3. **Cero IA, cero red en `analyze`.** Ningún SDK de IA, ninguna petición HTTP. El HTML generado no carga nada externo (sin CDN, sin fuentes web).
4. **Las gramáticas sí necesitan red UNA vez.** Verificado: `tree-sitter-language-pack` 1.22.1 descarga las gramáticas la primera vez (~59 MB en `~/.cache/tree-sitter-language-pack`). Por eso existe `desglosa setup` (descarga explícita de los 13 lenguajes). `analyze` **nunca** descarga: antes de llamar a `get_parser` comprueba `downloaded_languages()`; si falta alguno, aborta con: `Falta la gramática X. Ejecuta una vez: desglosa setup`.
5. **Nunca ejecutar el código analizado.** Solo leerlo.
6. **Determinista:** misma entrada → mismo HTML byte a byte.
7. **No inventar relaciones.** Lo que no se puede resolver se muestra como "externo" o "ambiguo", nunca se adivina.
8. **Idioma de la interfaz y documentación: español.** Código e identificadores: inglés.

---

## 2. Stack verificado (probado el 24/10/2026)

| Paquete | Versión probada | Rango en `pyproject.toml` |
|---|---|---|
| Python | 3.12 / 3.13 | `>=3.10` |
| tree-sitter | 0.26.0 | `>=0.25,<0.27` |
| tree-sitter-language-pack | 1.22.1 | `>=1.22,<2` |
| sqlglot | 30.24.0 | `>=30,<31` |
| pathspec | 1.1.1 | `>=0.12` |

Nombres de gramática verificados que parsean sin error: `python`, `javascript`, `typescript`, `php`, `ruby`, `rust`, `go`, `java`, `c`, `cpp`, `swift`, `kotlin`, `sql`. (TSX: usar `tsx` si existe; verificar con `doctor`.)

Scaffold: **`uv init --package desglosa`** (con `--package`; `uv init` a secas NO crea `src/` ni entry point). Entry point: `desglosa = "desglosa.cli:main"`.

---

## 3. Vistas

| Vista | Para quién | Responde | Prioridad |
|---|---|---|---|
| **Mapa** (macro, por niveles) | todos; puerta de entrada | ¿Qué partes tiene y cómo se hablan? | M |
| **Flujo** (por función) | explicar fácil (feria, profesor) | ¿Qué hace esta función paso a paso? | M |
| **Secuencia** (UML) | técnico | ¿Quién llama a quién y en qué orden? | S |
| **ER** (SQL) | datos | ¿Qué tablas hay y cómo se relacionan? | S |

El flujo tiene dos modos (S): **Fácil** (textos por plantilla en español: "Si total > 0", "Repite mientras …", "Para cada factura en facturas", "Llama a cobrar()"; agrupa asignaciones triviales; muestra el docstring/comentario de la función arriba) y **Técnico** (código literal + `archivo:línea`). Sin IA el modo fácil solo reformula la sintaxis; no "entiende" la intención. Documentarlo así.

---

## 4. Arquitectura

```
carpeta ─► scan ─► parse ─► extract ─► resolve ─► analyze ─► layout ─► render ─► un .html
```

```
desglosa/
├─ pyproject.toml
├─ README.md  LICENSE  NOTICE.md  CHANGELOG.md  CLAUDE.md  SPEC.md
├─ src/desglosa/
│  ├─ __init__.py  __main__.py
│  ├─ cli.py               # argparse: setup, doctor, analyze, flow, sequence, sql, export-ir, debug-ast
│  ├─ grammars.py          # LANGS, setup(), ensure_offline_available()
│  ├─ scan.py              # recorrer, ignorar, detectar lenguaje, leer con encoding robusto
│  ├─ ir.py                # dataclasses del modelo intermedio + ids estables
│  ├─ langs/
│  │  ├─ spec.py           # dataclass LangSpec
│  │  ├─ python.py javascript.py typescript.py php.py java.py c.py cpp.py
│  │  ├─ go.py ruby.py rust.py kotlin.py swift.py
│  │  ├─ builtins.py       # funciones de E/S y builtins por lenguaje
│  │  └─ sql.py            # sqlglot
│  ├─ extract.py           # AST → símbolos, imports, llamadas (+ contexto de control)
│  ├─ resolve.py           # llamada → definición + confianza
│  ├─ flow.py              # AST de función → FlowGraph
│  ├─ sequence.py          # recorrido de llamadas → SequenceDiagram
│  ├─ macro.py             # niveles, agregación de aristas, puntos de entrada, métricas
│  ├─ sqlmodel.py          # tablas, columnas, PK/FK; enlace función→tabla
│  ├─ layout/
│  │  ├─ text.py           # medición de texto (fuente monoespaciada) y ajuste de líneas
│  │  ├─ flow.py           # layout estructurado + partición en columnas con conectores
│  │  ├─ layered.py        # Sugiyama simplificado (mapa y ER)
│  │  └─ sequence.py       # rejilla columnas × filas
│  ├─ render/
│  │  ├─ html.py           # ensambla el HTML único
│  │  ├─ template.html  app.js  style.css
│  └─ report.py            # reporte .md
├─ tests/
│  ├─ fixtures/<lenguaje>/ # mismo mini-programa en cada lenguaje (ver §12)
│  ├─ golden/              # salidas esperadas (IR JSON)
│  └─ test_*.py
├─ examples/               # proyectos demo + HTML ya generados
├─ docs/                   # ARCHITECTURE.md, ADDING_A_LANGUAGE.md, IR.md, LIMITES.md, DISENO.md
└─ .github/workflows/ci.yml
```

---

## 5. Modelo intermedio (IR) — `ir.py`

Todas son `@dataclass(frozen=True, slots=True)` serializables a JSON con orden estable.

```python
SourceFile: path(posix relativo), lang, sha1, lines:int, parsed_ok:bool, errors:int, skipped_reason:str|None
Symbol:     id, kind("module"|"class"|"interface"|"function"|"method"), name, qualname,
            file, line_start, line_end, parent_id|None, doc:str|None, lang, signature:str,
            is_entry:bool
Import:     file, module_text, alias|None, line
Call:       id, caller_id, callee_text, receiver_text|None, line, col,
            context: tuple[ControlCtx,...]   # pila de estructuras de control que la envuelven
            resolved_id|None, candidates: tuple[str,...], confidence("exacta"|"probable"|"ambigua"|"externa"),
            io_kind: None|"pantalla"|"teclado"|"archivo_lee"|"archivo_escribe"
ControlCtx: kind("if"|"else"|"loop"|"switch_case"|"try"|"catch"), line, label:str
FlowNode:   id, kind(ver §7.3), text_easy, text_tech, line_start, line_end, call_id|None, target_symbol|None
FlowEdge:   src, dst, label:str|None, kind("normal"|"retorno_bucle"|"excepcion"|"salto")
FlowGraph:  symbol_id, nodes, edges, truncated:bool
Table/Column/ForeignKey: para SQL (ver §9)
Project:    root_name, files, symbols, imports, calls, flows, tables, fks, table_access, warnings
```

**Ids estables:** `sha1(f"{lang}|{path}|{qualname}|{line_start}")[:12]`. Nunca `id()` de Python, nunca contadores dependientes del orden de procesos.

---

## 6. Etapas

### 6.1 `scan.py`
- Recorre en **orden alfabético de ruta POSIX relativa**.
- Respeta `.gitignore` (pathspec) y `.desglosaignore` si existe; `--ignore PATRON` repetible.
- Ignora siempre: `.git, node_modules, vendor, build, dist, out, target, bin, obj, .venv, venv, __pycache__, .idea, .vscode, storage, bootstrap/cache, public/build`, archivos `*.min.*`, `*.map`, `*.lock`.
- Detecta minificado: promedio de línea > 200 caracteres o alguna línea > 2000 → se salta y se anota.
- Tope por archivo: 1 MB (`--max-file-kb`).
- No sigue symlinks que salgan de la raíz.
- Extensiones → lenguaje: `.py`; `.js .mjs .cjs .jsx`; `.ts .tsx`; `.php`; `.rb`; `.rs`; `.go`; `.java`; `.c .h`; `.cpp .cc .cxx .hpp .hh`; `.swift`; `.kt .kts`; `.sql`. `.h` → C por defecto; `--h-as cpp` lo cambia. `.blade.php` → se ignora por defecto (plantillas).
- Lectura robusta: bytes → `utf-8-sig` → `utf-8` → `cp1252` (Windows) → `latin-1`. Guardar texto con `\n` para mostrar; tree-sitter recibe los bytes originales.

### 6.2 `extract.py` + `langs/*.py`
Un **motor genérico** recorre el AST guiado por un `LangSpec` por lenguaje:

```python
@dataclass(frozen=True)
class LangSpec:
    name: str; grammar: str
    module_nodes: tuple; class_nodes: tuple; interface_nodes: tuple; function_nodes: tuple; method_nodes: tuple
    name_field: str = "name"                # campo del nombre; override por lenguaje si hace falta
    import_nodes: tuple; call_nodes: tuple
    if_nodes: tuple; else_nodes: tuple; elif_nodes: tuple
    loop_nodes: tuple; do_while_nodes: tuple; switch_nodes: tuple; case_nodes: tuple
    try_nodes: tuple; catch_nodes: tuple; finally_nodes: tuple
    return_nodes: tuple; break_nodes: tuple; continue_nodes: tuple; throw_nodes: tuple
    block_nodes: tuple; comment_nodes: tuple
    self_names: tuple                       # ("self",) ("this",) ("$this","self","static") …
    expression_oriented: bool = False       # Ruby, Rust, Kotlin
```

Tabla de partida (verificada con snippets pequeños; **confírmala con `desglosa debug-ast` sobre los fixtures y corrígela donde no coincida**):

| Lenguaje | Función/método | if | Bucles | Switch | Try | Llamada |
|---|---|---|---|---|---|---|
| Python | function_definition | if_statement (elif_clause, else_clause) | for_statement, while_statement | match_statement | try_statement | call |
| JS / TS | function_declaration, method_definition, arrow_function, function_expression | if_statement | for_statement, for_in_statement, while_statement, do_statement | switch_statement | try_statement | call_expression, new_expression |
| PHP | function_definition, method_declaration | if_statement (else_if_clause, else_clause) | for_statement, foreach_statement, while_statement, do_statement | switch_statement | try_statement | function_call_expression, member_call_expression, scoped_call_expression, object_creation_expression |
| Java | method_declaration, constructor_declaration | if_statement | for_statement, enhanced_for_statement, while_statement, do_statement | switch_expression | try_statement | method_invocation, object_creation_expression |
| Go | function_declaration, method_declaration | if_statement | for_statement | expression_switch_statement, type_switch_statement | — | call_expression |
| C / C++ | function_definition | if_statement | for_statement, while_statement, do_statement, for_range_loop | switch_statement | try_statement (C++) | call_expression |
| Swift | function_declaration | if_statement, guard_statement | for_statement, while_statement, repeat_while_statement | switch_statement | do_statement + catch_block | call_expression |
| Ruby | method, singleton_method | if, unless (elsif) | while, until, for, bloques `.each do` | case | begin + rescue | call |
| Rust | function_item | if_expression | for_expression, while_expression, loop_expression | match_expression | — | call_expression, macro_invocation |
| Kotlin | function_declaration | if_expression | for_statement, while_statement, do_while_statement | when_expression | try_expression | call_expression |

Por cada archivo se extrae:
- **Símbolos** con rango de líneas, firma (primera línea de la declaración, recortada a 120 caracteres) y doc (docstring de Python; comentario `/** */`, `//`, `#` inmediatamente anterior en los demás).
- **Imports** (`import`, `from … import`, `use`, `require`, `include`, `#include "…"`).
- **Llamadas** con `receiver_text` (lo que va antes de `.`, `->`, `::`), línea, y **pila de contexto de control** (para alt/loop en la secuencia).
- **io_kind** según `langs/builtins.py`:
  - `pantalla`: `print`, `echo`, `print_r`, `var_dump`, `printf`, `puts`, `cout <<` (como expresión), `console.log`, `System.out.println`, `fmt.Println/Printf`, `println!`, `println`.
  - `teclado`: `input`, `scanf`, `gets`, `fgets(...stdin)`, `readline`, `Scanner.next*`, `bufio.NewReader(os.Stdin)`, `readLine`, `STDIN`, `prompt`, `cin >>`.
  - `archivo_lee`/`archivo_escribe`: `open(...,'r'|'w')`, `fopen`, `file_get_contents`/`file_put_contents`, `fs.readFile`/`writeFile`, `Files.read*`/`write*`, `os.ReadFile`/`WriteFile`.
- Archivos con nodos `ERROR`: se procesan igual; se cuentan errores y se reporta. Nunca abortar todo el análisis por un archivo.
- Paralelismo: `ProcessPoolExecutor` por archivo con funciones de nivel módulo (picklables; Windows usa `spawn`). Resultados **ordenados por ruta** antes de unir.

### 6.3 `resolve.py` — confianza
Para cada `Call` busca candidatos y asigna:
- **exacta:** `self/this/$this/static/self::/parent::` + método existente en la clase (o padre conocido); `Clase::metodo` / `new Clase` / `Clase.metodo` con clase conocida; función del mismo archivo; símbolo importado explícitamente con nombre único.
- **probable:** tipo del receptor deducido de una anotación/type hint, parámetro tipado o `x = new Clase()` en la misma función; o nombre único en todo el proyecto con receptor desconocido.
- **ambigua:** varios candidatos → guardar `candidates`.
- **externa:** sin candidatos (librería, builtin). No se dibuja como nodo propio en el mapa (sí como nodo gris "externo" en flujo/secuencia).
- **Interfaces / inyección de dependencias:** si el destino es un método de interfaz/abstracto, se agregan como candidatos las implementaciones conocidas (por `implements`/`extends`), confianza `probable`, etiqueta "posible implementación".

### 6.4 `macro.py` — niveles del mapa
- Niveles: **Proyecto → Módulo (carpeta / namespace / paquete) → Archivo o Clase → Función/Método**.
- Colapsar cadenas de carpetas con un solo hijo (`src/app/Http` → un nodo).
- Aristas agregadas por nivel con conteo (`12 llamadas`) y la confianza **de la mayoría** de sus llamadas (en empate, la menos segura); al pasar el mouse se ve el desglose (exactas, probables, ambiguas). *Cambio decidido por Italo el 2026-10-25: con "la peor confianza", en proyectos grandes casi todas las flechas salían punteadas.* Una llamada con más de 4 destinos posibles no se cuenta.
- Si un nivel tiene más de **15** hijos: mostrar los 14 con más conexiones + un nodo "Otros (N)" que se puede abrir. Si lo que sobra no cabe en un solo grupo, se reparte en grupos alfabéticos parejos ("Otros: a… – c… (27)"). En un nivel muy denso (más de 1,5 relaciones por elemento) se dibuja el esqueleto de relaciones más fuertes y se avisa cuántas se ocultan.
- **Puntos de entrada** (`is_entry`): `main`, bloque `if __name__ == "__main__"`, `public static void main`, `func main`, `fn main`, clases `*Controller` y funciones referenciadas en `routes/*.php` (Laravel: `Route::get('/x', [XController::class, 'metodo'])`).
- Métricas por función: complejidad ciclomática (decisiones + 1), nº de llamadas entrantes/salientes, líneas.

---

## 7. Diagrama de flujo — `flow.py`

### 7.1 Algoritmo (salidas abiertas)
`build(nodo_ast, salidas) -> salidas` donde `salidas` es una lista de pares `(id_nodo, etiqueta)` pendientes de conectar.

- **Inicio** y **Fin** (terminales) siempre existen. Inicio muestra el nombre y parámetros: `Inicio: emitir(factura)`.
- **Sentencias simples** consecutivas → un solo nodo **proceso** (máx. 4 líneas de texto; si hay más, nuevo nodo).
- Sentencia con llamada **resuelta** → nodo **subproceso** propio (clicable; abre el flujo del destino).
- Sentencia con `io_kind` → nodo **pantalla**, **teclado**, **documento** (escritura de archivo) o **E/S** (lectura de archivo).
- `return` → nodo proceso "Retorna …" conectado a Fin; `salidas=[]`.
- `throw/raise` → arista `excepcion` al `catch` que lo envuelve; si no hay, a Fin con etiqueta "excepción".
- **if/elif/else:** rombo con la condición. Rama verdadera con etiqueta **"sí"**, falsa con **"no"**; `elif` = `if` anidado en la rama "no"; sin `else`, la salida "no" queda abierta. Salidas = unión.
- **while/for/foreach:** rombo cabecera ("¿i < n?" / "¿Quedan elementos en facturas?"). Cuerpo por "sí"; el final del cuerpo vuelve a la cabecera con arista `retorno_bucle`. Salida por "no" + todos los `break`. `continue` → arista a la cabecera.
- **do-while:** cuerpo primero, rombo al final, "sí" vuelve al inicio del cuerpo.
- **switch/match/when/case:** rombo con una arista por caso (`caso 1`, `caso "A"`, `otro`). En C/C++/JS/Java/PHP un caso sin `break` cae al siguiente (fallthrough): conectar sus salidas a la entrada del caso siguiente.
- **try/catch/finally:** nodo proceso "Intentar"; cuerpo normal; desde "Intentar" una arista `excepcion` (punteada) a cada catch ("excepción: TipoError"); todas las salidas pasan por `finally` si existe.
- **guard (Swift):** rombo; la rama "no" debe terminar (return/throw).
- **Lenguajes orientados a expresiones** (Ruby, Rust, Kotlin): `if/match/when` como sentencia → igual que arriba; dentro de una asignación (`let x = if …`) → texto del proceso. Bloques `.each do |x|` → bucle "Para cada x en …".
- **goto (C):** nodo proceso "goto etiqueta (no soportado)" y advertencia.
- **Límite:** `--max-flow-nodes` (por defecto 120). Si se supera, los bloques más profundos se colapsan en un nodo "Bloque (L12–L40)" que al clic muestra el código. `truncated=True`.

### 7.2 Textos
- Modo técnico: código literal de la sentencia/condición (una línea, recortada a 80 caracteres; completo en tooltip y panel de código).
- Modo fácil: plantillas en español (`Si …`, `Mientras …`, `Para cada x en xs`, `Llama a cobrar()`, `Muestra en pantalla: …`, `Lee del teclado: …`, `Retorna …`). Operadores traducidos: `&&/and` → "y", `||/or` → "o", `!/not` → "no", `==` → "=", `!=` → "≠", `<=` → "≤", `>=` → "≥".

### 7.3 Símbolos (norma clásica de diagramas de flujo)

| Tipo de nodo (`kind`) | Símbolo | Uso |
|---|---|---|
| `terminal` | rectángulo de esquinas redondeadas (píldora) | Inicio / Fin |
| `proceso` | rectángulo | asignaciones, operaciones |
| `subproceso` | rectángulo con doble línea vertical a cada lado | llamada a función del proyecto (clicable) |
| `decision` | rombo | if, bucles, switch |
| `es` | paralelogramo | entrada/salida genérica, lectura de archivo |
| `pantalla` | forma "display" (punta a la izquierda, curva a la derecha) | print/echo/console.log |
| `teclado` | trapecio con lado superior inclinado ("entrada manual") | input/scanf/readline |
| `documento` | rectángulo con borde inferior ondulado ("impresora/documento") | escritura de archivo/reporte |
| `conector` | círculo con número | continuación en la misma página (columnas) |
| `conector_pagina` | pentágono apuntando abajo | continuación en otra página (solo export imprimible) |
| `externo` | rectángulo gris de borde punteado | llamada no resuelta (no clicable) |

### 7.4 Layout del flujo — `layout/flow.py`
Layout **estructurado** (no un algoritmo de grafos genérico): cada construcción devuelve una caja `(ancho, alto, x_entrada, salidas)`.
- Secuencia: cajas apiladas verticalmente, alineadas por el eje de entrada. Flujo **de arriba hacia abajo**.
- if: rombo arriba; rama **"sí" hacia abajo**, rama **"no" hacia la derecha** (como en los diagramas hechos a mano); unión debajo de la rama más alta.
- Bucle: la arista de retorno usa un **canal lateral izquierdo** reservado (no cruza nodos).
- switch: casos lado a lado debajo del rombo.
- Medición de texto: fuente monoespaciada; ancho ≈ `caracteres × 0.6 × tamaño_fuente`; ajuste de línea a 28 caracteres por línea (modo fácil) / 40 (técnico).
- **Columnas con conectores:** si el alto total supera `--flow-max-height` (por defecto 1600 px), cortar en un límite de la secuencia de nivel superior, poner un `conector` numerado ("1") al pie de la columna y el mismo al inicio de la siguiente columna (exactamente como los diagramas hechos a mano).
- Garantías (con test automático): ningún nodo se superpone con otro; ninguna arista atraviesa un nodo que no sea su origen o destino; las etiquetas "sí/no" no se superponen con nodos.

---

## 8. Secuencia — `sequence.py`
- Desde una función de entrada (`--entry Clase.metodo` o la elegida en el visor), DFS sobre llamadas **resueltas** en orden de línea, hasta `--depth` (por defecto 4).
- Participantes: clase (o archivo, para funciones sueltas), en orden de primera aparición. Actor inicial: "Usuario" si la entrada es un controlador/main.
- Mensajes numerados `1, 1.1, 1.2…` con flechas sólidas (llamada) y punteadas (retorno, solo si la función retorna algo).
- Fragmentos combinados a partir de `Call.context`: `loop [condición]`, `alt [condición] / else`, `opt`.
- Recursión o ciclo → mensaje "(recursivo)" sin expandir. Interfaces → `alt` "posible implementación: X / Y".
- Llamadas `externa` → participante gris "Externo" agrupado (opcional ocultar con un toggle).
- Layout: rejilla; columnas de ancho = máx(nombre, 140 px); filas de 36 px.

## 9. SQL — `sqlmodel.py`
- `sqlglot.parse(texto, read=dialecto)`; `--dialect` (mysql, postgres, sqlite, tsql…). Si falla una sentencia: reintentar con `mysql`, `postgres`, `sqlite`, `tsql`; si nada funciona, registrar advertencia y seguir.
- Extraer tablas, columnas (tipo, NOT NULL), PK y FK en sus **tres formas**: `REFERENCES` en línea, `FOREIGN KEY (…) REFERENCES …` a nivel de tabla, y `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY`. Usar `find_all(exp.ForeignKey)` y también revisar `exp.Reference` en restricciones de columna. El fixture con las tres formas debe dar 3 FKs.
- **Enlace función → tabla (S):** en literales de cadena del código, regex sobre `FROM|JOIN <tabla>` (lee) e `INSERT INTO|UPDATE|DELETE FROM <tabla>` (escribe). Confianza `probable`. ORMs fuera de la v1.
- Layout ER: layered (§10) con tablas como cajas de columnas; FK → línea de la columna FK a la PK destino con etiqueta `N:1`.

## 10. Layout del mapa y ER — `layout/layered.py`
Sugiyama simplificado: (1) romper ciclos invirtiendo aristas de retroceso de un DFS determinista; (2) capas por longest-path; (3) orden dentro de la capa por baricentro, 4 barridos arriba-abajo/abajo-arriba, desempate por nombre; (4) coordenadas: separación horizontal mínima = ancho de etiqueta + 32 px; (5) aristas poligonales con puntos intermedios virtuales; etiqueta con máscara opaca. Dirección: **izquierda → derecha** en el mapa.

---

## 11. Visor HTML — `render/`

### 11.1 Archivo único
- Un solo `.html` con CSS y JS en línea. Cero URLs externas (test: el HTML no contiene `http://` ni `https://` salvo en `xmlns`).
- Datos en `<script type="application/json" id="desglosa-data">` serializados con `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` y luego reemplazando `<` → `<`, `>` → `>`, `&` → `&`, U+2028/U+2029 escapados (` `, ` `). Se lee con `JSON.parse(el.textContent)`.
  *(Nota: en la versión pegada originalmente los escapes `<` etc. se habían perdido; esta es la forma correcta.)*
- **Todo** texto proveniente del código se pinta con `textContent` / `createElementNS`. Prohibido `innerHTML` con datos analizados.
- El código fuente se incluye una vez por archivo (solo archivos con símbolos). `--no-source` lo omite. Aviso si el HTML pasa de 20 MB.
- Escritura en UTF-8 con `newline="\n"`. Sin timestamps (salvo `--stamp`).

### 11.2 Navegación
- Rutas en el hash (funcionan con `file://`): `#/mapa`, `#/mapa/<id_grupo>`, `#/flujo/<id_funcion>`, `#/secuencia/<id_funcion>`, `#/er`. Parámetros: `?focus=<id>`, `&modo=facil|tecnico`, `&tema=claro|oscuro`. Botón atrás del navegador funciona.
- **Migas de pan** arriba: `Proyecto › Facturacion › FacturaService › emitir()`.
- Clic en grupo → entra. Clic en función → abre su flujo. Clic en subproceso dentro de un flujo → abre el flujo de la función llamada (y la miga crece). Doble clic / tecla `Esc` → sube un nivel.
- Pestañas en la vista de función: **Flujo | Secuencia | Código**.
- Panel lateral: código fuente con números de línea, resaltando el rango del nodo seleccionado; `archivo:línea`; métricas; llamadas entrantes y salientes (clicables).
- Buscador (`/`): busca funciones, clases, tablas; Enter navega.
- Teclado: `/` buscar, `Esc` subir, `t` tema, `m` modo fácil/técnico, `+`/`-`/`0` zoom, `f` encuadrar. Navegable con Tab y foco visible.
- Pan con arrastre, zoom con rueda (centrado en el cursor).
- **Focus en el mapa (S):** clic en un nodo resalta lo que llama (aguas abajo) y lo que lo llama (aguas arriba); el resto se atenúa. Restaurable con `?focus=<id>`.

### 11.3 Diseño visual (adaptado de los requerimientos RF-D/RF-I del amigo; ver §11.4)
Tokens CSS en `:root` y `[data-tema="claro"]`:

| Token | Oscuro | Claro |
|---|---|---|
| `--fondo` | `#0b1120` | `#f8fafc` |
| `--rejilla` | `#1e293b` (líneas 0.5 px cada 40 px) | `#e2e8f0` |
| `--superficie` (máscara de etiquetas y nodos) | `#0f172a` | `#ffffff` |
| `--texto` | `#e5e7eb` | `#0f172a` |
| `--texto-suave` | `#94a3b8` | `#475569` |

Color semántico **por tipo de nodo** (un color = un significado dentro de cada vista; relleno = mismo color al 15–20 % de opacidad; borde = color sólido; en claro el borde se oscurece):

| Tipo | Oscuro (borde) | Claro (borde) |
|---|---|---|
| terminal | `#34d399` | `#059669` |
| proceso | `#60a5fa` | `#2563eb` |
| subproceso | `#a78bfa` | `#7c3aed` |
| decision | `#fbbf24` | `#b45309` |
| es / teclado | `#22d3ee` | `#0891b2` |
| pantalla / documento | `#f472b6` | `#db2777` |
| excepción (aristas) | `#fb7185` | `#e11d48` |
| externo | `#94a3b8` | `#64748b` |
| mapa: módulo | `#818cf8` | `#4f46e5` |
| mapa: clase/archivo | `#60a5fa` | `#2563eb` |
| mapa: función | `#a78bfa` | `#7c3aed` |
| mapa: punto de entrada | `#34d399` | `#059669` |
| ER: tabla | `#fb923c` | `#c2410c` |

Confianza de aristas: **exacta** sólida · **probable** guiones (6 4) · **ambigua** puntos (2 4) · **externa** gris fina punteada.
La forma del nodo también cambia según el tipo (nunca solo el color). Contraste de texto ≥ 4.5:1.

### 11.4 Requerimientos del amigo: decisión
| Req. amigo | Decisión | Motivo |
|---|---|---|
| RF-D01 colores semánticos | **Adaptado** | Sus 7 tipos (frontend, backend, database…) son de diagramas de arquitectura (vienen de Archify), no de código. Se mantiene la regla "un color = un significado, fuera del mapa falla el test" con nuestros tipos. |
| RF-D02 tema claro/oscuro | **Adoptado** | Tokens propios, misma regla de relleno 15–20 % y borde oscurecido. |
| RF-D03 fondo, rejilla 40 px, máscara opaca | **Adoptado** | La máscara evita que las líneas tapen el texto. |
| RF-D04 flujo izq→der, máx. 12 nodos | **Adaptado** | Un diagrama de flujo va de arriba hacia abajo y una función puede tener 60 nodos. Mapa: máx. 15 por nivel + "Otros". Flujo: columnas con conectores. |
| RF-D05 etiquetas y rutas que no crucen nodos | **Adoptado** | Test automático. Etiquetas: sí/no/caso en flujo; conteo en mapa. |
| RF-D06 leyenda solo con tipos presentes | **Adoptado** | Test automático. |
| RF-I01 focus + upstream/downstream | **Adoptado sin animación** | La animación de recorrido se descarta por tiempo. |
| RF-I02 búsqueda + estado en URL | **Adoptado** | Con nuestras rutas de hash. |
| RF-I03 export sin estado temporal | **Adoptado (SVG/PNG)** | WebM descartado. |

### 11.5 Export (S)
- Botón "Exportar": SVG de la vista actual (sin estados de focus/hover, con estilos en línea y fondo) y PNG (canvas desde el SVG, escala 2×).
- CSS de impresión: oculta paneles, imprime el diagrama; el flujo partido en columnas usa `conector_pagina` entre páginas.

---

## 12. CLI — `cli.py`

```
desglosa setup                         # descarga las 13 gramáticas (única vez que usa red)
desglosa doctor                        # versión, Python, gramáticas disponibles OK/FALTA
desglosa analyze <ruta> [-o desglosa.html] [--lang php,python] [--ignore PATRON]...
                 [--no-source] [--dialect mysql] [--max-flow-nodes 120]
                 [--flow-max-height 1600] [--report reporte.md] [--h-as c|cpp] [--jobs N]
desglosa flow <ruta> <archivo>:<funcion> [-o flujo.html]   # un flujo suelto
desglosa sequence <ruta> --entry Clase.metodo [--depth 4] [-o secuencia.html]
desglosa sql <ruta> [--dialect …] [-o er.html]
desglosa export-ir <ruta> [-o ir.json]                      # modelo intermedio
desglosa debug-ast <archivo> [--depth 6]                   # imprime el AST (para ajustar LangSpec)
```
Salida de consola en español: resumen (archivos por lenguaje, símbolos, llamadas por confianza, saltados, tiempo). Código de salida: 0 ok, 1 error de uso, 2 faltan gramáticas.

---

## 13. Requerimientos

M = imprescindible · S = debería · C = opcional

| ID | Pri. | Requerimiento | Criterio de aceptación |
|---|---|---|---|
| RF-01 | M | Recibe carpeta o archivo y genera un único `.html` autocontenido. | Se abre con doble clic sin internet; test sin `http(s)://`. |
| RF-02 | M | Extrae clases, funciones, métodos, imports y llamadas de los 12 lenguajes. | Golden de IR por fixture. |
| RF-03 | M | Ignora vendor/minificados/build y respeta `.gitignore`. | Test con fixture que incluye `vendor/` y `x.min.js`. |
| RF-04 | M | Mapa por niveles con aristas agregadas, clic para entrar, migas para subir. | Prueba manual + test de estructura de datos de niveles. |
| RF-05 | M | Flujo por función con los símbolos de §7.3 y todas las construcciones de §7.1. | Golden de FlowGraph por fixture; test de no superposición. |
| RF-06 | M | Subproceso clicable abre el flujo de la función llamada. | `target_symbol` presente para llamadas resueltas. |
| RF-07 | M | Panel con código fuente y `archivo:línea` del elemento seleccionado. | Prueba manual. |
| RF-08 | M | Cada relación muestra su confianza con estilo distinto. | Test de clases CSS por confianza. |
| RF-09 | S | Secuencia con alt/opt/loop, profundidad y ciclos cortados. | Golden por fixture. |
| RF-10 | S | Modo fácil / técnico. | Los dos textos existen en cada FlowNode. |
| RF-11 | S | ER de SQL con PK/FK (3 formas) y `--dialect`. | Fixture SQL da 3 FKs. |
| RF-12 | S | Enlace función → tabla (lee/escribe). | Fixture PHP con SQL en cadenas. |
| RF-13 | S | Buscador, zoom/pan, tema claro/oscuro, leyenda solo con tipos presentes. | Test de leyenda. |
| RF-14 | S | Export SVG/PNG y CSS de impresión. | Prueba manual. |
| RF-15 | S | Reporte `.md`: archivos por lenguaje, funciones más llamadas, funciones nunca llamadas, ciclos, archivos no parseados, complejidad más alta. | Test de secciones. |
| RF-16 | S | Rutas de Laravel como puntos de entrada. | Fixture `routes/web.php`. |
| RF-17 | C | `export-ir` JSON. | Golden. |
| RF-18 | C | Export de un flujo/secuencia a Mermaid. | — |
| RNF-01 | M | Cero IA y cero red en `analyze`. | Test que reemplaza `socket.socket` por uno que lanza excepción durante `analyze`. |
| RNF-02 | M | Determinista. | Dos ejecuciones → mismo SHA-256 del HTML. |
| RNF-03 | M | Tolerante a errores de sintaxis y codificación. | Fixture roto no tumba el análisis. |
| RNF-04 | M | Seguro: no ejecuta código, escapa todo, no sigue symlinks externos. | Fixture con `</script><script>alert(1)</script>` en una cadena: el HTML no ejecuta nada. |
| RNF-05 | S | Rendimiento: 1 000 archivos < 2 min con `--jobs`. | Medir y documentar el resultado real. |
| RNF-06 | M | Instalable con `uv tool install .` o `pipx install .`; funciona en Windows. | CI en `windows-latest` y `ubuntu-latest`. |
| RNF-07 | S | Extensible: agregar un lenguaje = un `LangSpec` + fixture + test. | `docs/ADDING_A_LANGUAGE.md`. |
| RNF-08 | M | Probado con pytest + ruff en CI. | CI verde. |
| RNF-09 | S | Accesible: teclado, foco visible, contraste ≥ 4.5:1, forma + color. | Revisión manual. |
| RNF-10 | S | Diagramas legibles: sin superposición de nodos, sin aristas que crucen nodos ajenos, colores solo del mapa semántico. | Tests automáticos de layout. |

---

## 14. Fixtures y pruebas

- **Mismo mini-programa en cada lenguaje** (`tests/fixtures/<lang>/`), ~60–100 líneas, 2–3 archivos: un "sistema de facturación" con: una clase/estructura `Factura`, un servicio `FacturacionService.emitir()` que hace `if/else`, un `for` sobre ítems, un `while`, un `switch` por tipo de pago, un `try/catch`, `return` temprano, `break`/`continue`, una llamada a `PagoService.cobrar()` en otro archivo, un `print`, una lectura de teclado y una escritura de archivo. Donde el lenguaje no tenga una construcción (Go sin try), omitirla.
- **Fixture GPS en C** (`examples/gps-c/gps.c`): reproduce la lógica de un diagrama de flujo clásico de lectura de GPS por puerto serie: inicializa variables y el puerto; bucle que lee caracteres hasta encontrar `'$'`; contador `k` que al llegar a 1000 cierra la comunicación y termina; otro bucle copia caracteres a `Buffer[i]` contando tramas (`cont < 6`); luego recorre `j < 512 && cont1 < 6` buscando las tramas `GPRMC`, `GPGGA`, `GPGSA`, `PGRME`, `PGRMV`, `GPVTG` (comparando `Buffer[j]` y `Buffer[j-1]`) y llama a `DesglosaGPRMC()`, `DesglosaGPGGA()`, etc. (funciones definidas en el mismo archivo). Es la demo estrella: el flujo generado debe parecerse a uno hecho a mano, con columnas y conector "1".
- **Fixture PHP/Laravel mínimo** (`examples/laravel-mini/`): `routes/web.php`, un controlador, un servicio, una interfaz de repositorio con implementación MySQL y SQL en cadenas.
- **Fixture SQL** con las 3 formas de FK.
- **Fixture roto** (sintaxis inválida + archivo en cp1252).
- Tests: golden de IR, golden de FlowGraph, determinismo, sin red, sin `http`, escape de `</script>`, layout (superposición/cruces), leyenda, colores ∈ mapa semántico.
- Actualizar goldens solo con `pytest --update-golden` (flag propio) y revisando el diff.

---

## 15. Fases (con puerta de control)

Cada fase termina en algo que **funciona y se puede demostrar**. Al terminar cada fase: correr `uv run pytest` y `uv run ruff check`, hacer `git commit`, y **reportar al usuario** (qué se hizo, qué falló, qué decisión tomaste, cómo probarlo con un comando). Luego esperar "continúa".

| Fase | Contenido | Puerta (cómo se prueba) |
|---|---|---|
| **F0** Esqueleto | `uv init --package`, deps, `grammars.py`, `setup`, `doctor`, `debug-ast`, `git init`, `.gitignore`, ruff, pytest, CI básico. | `uv run desglosa doctor` muestra 13 OK. |
| **F1** Extracción | `scan`, `ir`, `LangSpec` + extracción de **Python, JS, TS, PHP, Java, C, C++**; `resolve`; `export-ir`; fixtures de esos 7. | `uv run desglosa export-ir tests/fixtures/php` coincide con golden. |
| **F2** Flujo | `flow.py`, `layout/flow.py`, render SVG de un flujo, comando `flow`. Fixture GPS en C. | `uv run desglosa flow examples/gps-c gps.c:main -o gps.html` se ve como un diagrama hecho a mano. |
| **F3** Visor completo = **MVP para la feria** | `macro.py`, `layout/layered.py`, app HTML: mapa por niveles, migas, panel de código, hash routing, clic en subproceso → flujo, buscador, temas, leyenda, zoom/pan. | `uv run desglosa analyze examples/laravel-mini -o demo.html`: cadena completa mapa → flujo → subproceso → flujo. |
| **F4** Resto de lenguajes | Go, Ruby, Rust, Kotlin, Swift (extracción + flujo "mejor esfuerzo"). | Goldens de los 5. |
| **F5** Secuencia + SQL | `sequence.py`, `sqlmodel.py`, ER, enlace función→tabla, rutas Laravel. | Golden de secuencia y fixture SQL con 3 FKs. |
| **F6** Pulido y publicación | Modo fácil/técnico, focus upstream/downstream, export SVG/PNG, reporte `.md`, README en español con capturas, `docs/`, `examples/` con HTML generados, CI en Windows + Linux, tag `v0.1.0`. | CI verde, README completo. |

**Si el tiempo no alcanza, recortar en este orden:** (1) Mermaid y PNG, (2) enlace función→tabla, (3) focus upstream/downstream, (4) modo fácil, (5) secuencia, (6) flujo de Ruby/Rust/Kotlin/Swift. **Nunca recortar F0–F3** (RF-04, RF-05, RF-06): son la diferencia del proyecto.

---

## 16. Entregables del repositorio
- `README.md` (español): qué es, captura/GIF, instalación en Windows (uv), `desglosa setup`, uso, ejemplos, lenguajes y nivel de soporte (tabla honesta: completo / mejor esfuerzo), límites, licencia, créditos.
- `NOTICE.md`: "Inspirado conceptualmente en Graphify (Apache-2.0) y Archify (MIT). No contiene código de ninguno de los dos. No está afiliado a Graphify Labs ni a Archify."
- `docs/ARCHITECTURE.md` (con diagrama del pipeline), `docs/IR.md`, `docs/ADDING_A_LANGUAGE.md`, `docs/LIMITES.md`, `docs/DISENO.md` (tokens y símbolos).
- `examples/` con `gps-c`, `laravel-mini` y sus `.html` generados.
- `LICENSE` MIT con el nombre del autor y año 2026.

## 17. Límites conocidos (documentar, no esconder)
Análisis estático: no ejecuta nada. Inyección de dependencias (se muestran "posibles implementaciones"). Llamadas dinámicas (`$obj->$m()`, reflexión, callbacks, metaprogramación de Ruby) → externa/ambigua. Macros y `#ifdef` de C/C++/Rust no se expanden. Control de flujo dentro de expresiones (ternarios, `&&/||`, lambdas, comprensiones) queda dentro del texto. Funciones gigantes se colapsan. `goto` no soportado. El modo fácil reformula, no explica. Ruby/Rust/Kotlin/Swift: flujo menos fino.
