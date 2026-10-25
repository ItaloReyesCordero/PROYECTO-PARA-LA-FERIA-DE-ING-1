# Progreso por fases

Reporte de cada fase (SPEC §15): qué se hizo, qué falló, qué se decidió y cómo probarlo.

---

## Fase 0 — Esqueleto ✅

**Qué se hizo**
- Proyecto con `uv init --package` en la raíz del repo (junto a `SPEC.md` y `CLAUDE.md`).
- Dependencias exactas de la SPEC: tree-sitter 0.26.0, tree-sitter-language-pack 1.22.1,
  sqlglot 30.24.0, pathspec 1.1.1; dev: pytest, ruff.
- `grammars.py`: lista de 13 lenguajes, `setup()` (única función con red),
  `ensure_offline_available()` y `get_parser()` que **nunca** descarga.
- Comandos `setup`, `doctor`, `debug-ast`. Códigos de salida 0/1/2 como pide la SPEC.
- CI en GitHub Actions (Windows + Ubuntu, Python 3.12 y 3.13).

**Qué falló**
- uv no pudo usar el Python 3.13 que descargó (enlace roto por el sandbox de la app).
  Se usa el **Python 3.14** que ya tienes instalado; funciona con todas las dependencias.

**Decisiones**
- `requires-python = ">=3.10"` (como la SPEC); `.python-version` = 3.14 en tu PC.
- `tsx` se descarga como gramática extra (para archivos `.tsx`); `doctor` la muestra aparte
  y sigue contando "13/13 lenguajes".
- `.gitattributes` con `eol=lf`: tu git convierte a CRLF y eso cambiaría el `sha1` de los
  archivos entre Windows y Linux (rompería el determinismo y los goldens).
- En SPEC §11.1 se habían perdido los escapes `<` etc. al pegar; se corrigió el texto.

**Probar**
```powershell
uv run desglosa doctor
```

---

## Fase 1 — Extracción ✅

**Qué se hizo**
- `scan.py`: recorrido en orden alfabético, `.gitignore` (de cualquier nivel),
  `.desglosaignore`, `--ignore`, carpetas siempre ignoradas, `*.min.*`/`*.map`/`*.lock`,
  minificados, binarios, tope de tamaño, symlinks fuera de la raíz, lectura
  utf-8-sig → utf-8 → cp1252 → latin-1.
- `ir.py`: todas las dataclasses del modelo intermedio, ids estables, JSON determinista.
- Motor genérico `extract.py` + `LangSpec`/`LangHooks` para **Python, JS, TS, PHP, Java,
  C y C++**: símbolos (con firma, doc y punto de entrada), imports, llamadas con receptor,
  pila de contexto de control (`if/else/loop/switch_case/try/catch`) e `io_kind`.
- `resolve.py`: confianza exacta / probable / ambigua / externa, herencia, interfaces
  ("posible implementación"), tipos deducidos de type hints, parámetros tipados,
  `x = new Clase()` y atributos (`self.x`, `$this->x`, `this.x`).
- Extracción en paralelo con `ProcessPoolExecutor` (automático a partir de 40 archivos).
- Comando `export-ir`. Fixtures de facturación en los 7 lenguajes + fixture roto.
- 57 tests: goldens de IR, determinismo, paralelo = serie, **sin red** (socket bloqueado),
  gramática faltante, fixture roto, scan.

**Qué falló / encontré**
- La tabla de nodos de la SPEC no coincidía en varios puntos (PHP usa `body` en el `if`,
  Java no tiene `else_clause`, etc.). Todo anotado en `docs/ADDING_A_LANGUAGE.md`.
- La recuperación de errores de tree-sitter puede "tragarse" todo el código que sigue a un
  paréntesis sin cerrar. No es un bug nuestro; se documentará en `LIMITES.md`.

**Decisiones (revísalas)**
1. **`Import.name`** (campo nuevo en el IR): el nombre importado (`from m import NOMBRE`).
   El IR de la SPEC solo tenía `module_text` y `alias`, y sin esto no se puede aplicar la
   regla "símbolo importado explícitamente → exacta".
2. **Un símbolo `module` por archivo**: es el padre de las clases/funciones de nivel
   superior y el "llamador" de las llamadas sueltas (p. ej. `main()` al final de un script).
3. **Funciones anónimas** (callbacks, lambdas) no crean símbolo: sus llamadas cuentan para la
   función que las contiene. Las arrow functions con nombre (`const f = () => …`) sí.
4. Los **namespaces** no forman parte del `qualname` (`FacturacionService.emitir`); el mapa
   agrupará por carpeta.
5. `candidates` queda vacío cuando hay un solo destino; se llena en llamadas **ambiguas** y
   en **posible implementación** (interfaz). Si la interfaz tiene una sola implementación,
   la llamada apunta directo a ella (probable).
6. **C/C++**: si `a.c` incluye `"pago.h"` y la función está en `pago.c`, la llamada es
   **exacta** (la SPEC no lo cubría; es el equivalente a un import explícito).
7. `new Clase()` sin constructor declarado apunta al símbolo de la clase.
8. Lista de receptores globales (`console`, `System`, `Math`, `std`…) para que
   `console.log` no se resuelva por error a un método `log` del proyecto.

**Probar**
```powershell
uv run desglosa export-ir tests/fixtures/php -o ir.json
uv run pytest -q
```

---

## Fase 2 — Diagrama de flujo ✅

**Qué se hizo**
- `flow.py`: AST de una función → `FlowGraph` con el algoritmo de "salidas abiertas"
  (§7.1): secuencias agrupadas (máx. 4 sentencias por proceso), subprocesos clicables,
  E/S (pantalla, teclado, documento, E/S), if/elif/else, while, for clásico (con nodos de
  inicialización e incremento), for-each, do-while, switch/match con fallthrough,
  try/catch/finally, return, break, continue, throw, goto (marcado como no soportado),
  límite `--max-flow-nodes` que colapsa los bloques más profundos.
- `layout/flow.py`: layout estructurado propio (§7.4). Eje vertical común, "sí" abajo y
  "no" a la derecha, carril izquierdo para el retorno de bucles, salida por la derecha,
  `break`/`continue` enrutados sin cruzar nodos (o con conectores A, B… si no hay camino),
  columnas con conectores numerados cuando el alto pasa de `--flow-max-height`.
- Visor HTML (`render/`): un único archivo con CSS y JS en línea, datos JSON escapados,
  modo fácil/técnico, tema claro/oscuro, zoom con rueda, arrastre, leyenda solo con los
  tipos presentes, panel con el código y la línea resaltada, export SVG/PNG.
- Comando `desglosa flow <ruta> <archivo>:<funcion>`. Fixture GPS en `examples/gps-c/`.
- Tests (85 en total): golden del FlowGraph de `emitir` en los 7 lenguajes y de
  `gps.c:main`; todos los nodos alcanzables; **ningún nodo superpuesto, ninguna línea que
  atraviese un nodo, ninguna etiqueta tapando un nodo** (en todos los flujos de los
  fixtures); HTML sin `http(s)://`, `</script>` escapado, determinista (mismo SHA-256).

**Qué falló / encontré**
- Las cadenas `if / else if` en diagonal hacían el diagrama GPS muy ancho → ahora se
  dibujan como **escalera** (rombos apilados por el "no", ramas "sí" a la derecha).
- Las columnas quedaban desbalanceadas (una con 3 nodos) → reparto de alto parejo.
- `str.splitlines()` corta en U+2028 y desfasaba el conteo de líneas → se cuenta `\n`.

**Decisiones (revísalas)**
1. **Varios "Fin"**: cada `return` dentro de un if/bucle lleva su propio terminal "Fin"
   justo debajo (como en los diagramas a mano) en vez de una línea larga hasta el final.
   Un `throw` sin `catch` termina en "Fin (excepción)".
2. **Cláusula de guarda**: si la rama "sí" termina (return/throw/break), se dibuja al
   costado y el camino principal sigue recto hacia abajo.
3. **Modo fácil**: las decisiones son preguntas (`¿total > 0?`), los for-each dicen
   `Para cada x en xs` y el switch `Según x`. Los operadores se traducen (§7.2).
4. Una sentencia que es **solo una llamada no resuelta** (`archivo.write(…)`) es un nodo
   "externo" gris punteado; si la llamada está dentro de una asignación, queda en el proceso.
5. Los **rombos cuya condición llama a una función del proyecto** también son clicables
   (`¿emitir(factura)?` abre el flujo de `emitir`).
6. **E/S que no son llamadas**: `echo` (PHP), `cout <<`, `cin >>` y `ofstream` (C++).
7. El layout se calcula en Python (determinista); el navegador solo dibuja. Un mismo layout
   sirve para los dos modos (cada caja mide lo que el texto más largo de los dos), así al
   cambiar de modo los nodos no se mueven.
8. Además de `<`, `>`, `&`, U+2028/2029, el JSON escapa `/` como `\/`: así una URL que
   aparezca en un comentario del código no rompe la regla "el HTML no contiene http://".

**Probar**
```powershell
uv run desglosa flow examples/gps-c gps.c:main -o gps.html
start gps.html
```

---

## Fase 3 — Visor completo (MVP para la feria) ✅

**Qué se hizo**
- `macro.py`: mapa por niveles Proyecto → carpeta → archivo/clase → función. Colapsa
  cadenas de carpetas (`Http/Controllers`), muestra un archivo de una sola clase como esa
  clase, agrega llamadas por nivel (conteo + peor confianza) y aplica el tope de 15 hijos
  con "Otros (N)".
- `layout/layered.py`: Sugiyama simplificado (ciclos, capas, baricentro, nodos virtuales),
  izquierda → derecha; los nodos sin conexiones van en una grilla.
- Comando `desglosa analyze <ruta> -o demo.html` con el visor completo: mapa clicable,
  migas de pan que crecen al entrar a subprocesos, pestañas Flujo/Secuencia/Código, panel
  con código y llamadas entrantes/salientes, buscador (`/`), `Esc` para subir, temas,
  modo fácil/técnico, zoom/arrastre, leyenda solo con los tipos presentes.
- Ejemplo `examples/laravel-mini/` (rutas, controlador, servicio, interfaz de repositorio
  con implementación MySQL y SQL en cadenas, esquema SQL con las 3 formas de FK).
- Tests (105): niveles del mapa, agregación de aristas, "Otros (N)", leyenda, layout por
  capas (también con 25 grafos aleatorios: sin superposiciones, sin aristas que crucen
  cajas, sin etiquetas sobre nodos), colores del CSS = tabla de §11.3 en los dos temas,
  comando `analyze` determinista y con `--no-source`.

**Qué falló / encontré**
- Los grafos aleatorios encontraron etiquetas que tapaban nodos cuando un nodo era más
  angosto que su columna → ahora cada arista recorre su fila hasta el borde de la columna.
- La clase base `Controller` salía como punto de entrada → solo `XxxController`.
- Las migas heredaban el recorrido anterior al usar el buscador → se reinician.

**Decisiones (revísalas)**
1. **Clic = entrar** (como dice §11.2). El "focus" aguas arriba/abajo (§11.2, S) se activa
   con **Alt+clic** o Mayús+clic sobre un nodo del mapa, o con `?focus=<id>` en la URL.
2. El mapa agrupa por **carpetas**, no por namespaces (funciona igual en los 12 lenguajes).
3. Una arista solo se dibuja entre hermanos del nivel actual: una llamada entre dos
   carpetas aparece en el nivel donde esas carpetas se ven lado a lado.
4. La leyenda se calcula en Python (así se puede testear) y el visor solo la dibuja.
5. La rejilla usa líneas de **1 px**: las de 0,5 px de la SPEC no se ven en pantallas 1x
   (proyectores de la feria).

**Probar**
```powershell
uv run desglosa analyze examples/laravel-mini -o demo.html
start demo.html
```
Recorrido: `app` → `Http/Controllers` → `FacturaController` → `store()` → clic en
"Llama a emitir()" → flujo de `FacturacionService.emitir`.

---

## Fase 4 — Resto de lenguajes ✅

**Qué se hizo**
- Extracción y diagrama de flujo de **Go, Ruby, Rust, Kotlin y Swift** (fixtures de
  facturación en los 5, con golden de IR y de FlowGraph).
- **Refactor**: `flow.py` ya no conoce la forma del AST de ningún lenguaje; la pide a
  `LangHooks` (`flow_kind`, `if_info`, `loop_info`, `switch_info`, `try_info`…). Los
  goldens de los 7 lenguajes anteriores **no cambiaron** con el refactor.
- Soporte nuevo: `unless`/`until` (ramas con sí/no invertidos), `guard` de Swift,
  bucles `.each do |x|` de Ruby como "Para cada", retorno implícito (Ruby, Rust, Kotlin
  `= expr`), `fallthrough` explícito (Go, Swift), métodos atados por receptor (Go) o por
  `impl` (Rust) o `extension` (Swift), `impl Trait for Tipo` como herencia, `panic(...)`
  de Go y `raise` de Ruby como lanzamiento de excepción.
- El resolvedor entiende receptores como `s.pago` (variable con tipo conocido → su campo)
  y `@pago` (Ruby).
- 130 tests: los 12 lenguajes pasan los mismos tests (cobrar se resuelve desde emitir,
  E/S detectada, punto de entrada `main`) y las garantías de layout.

**Qué falló / encontré**
- Kotlin y Swift casi no usan campos con nombre; `return/break/continue/throw` comparten
  un solo tipo de nodo. Todo anotado en `docs/ADDING_A_LANGUAGE.md`.
- En Rust `format!(` salía como "format no (" en modo fácil (el `!` de una macro no es
  negación) y en Kotlin `->` se convertía en `.`; corregido.

**Decisiones (revísalas)**
1. Go no declara qué interfaz implementa un tipo (es estructural), así que en Go no hay
   "posible implementación": la llamada por interfaz queda como probable por nombre único.
2. En Ruby las lecturas de atributos (`factura.items`) también son llamadas para el
   parser; quedan como externas (no ensucian el mapa, que no dibuja externas).
3. Una `extension` de Swift no crea una clase nueva: sus métodos se suman a la clase
   extendida.

**Probar**
```powershell
uv run desglosa flow tests/fixtures/ruby facturacion.rb:emitir -o ruby.html
uv run desglosa analyze tests/fixtures/kotlin -o kotlin.html
```

## Fase 5 — Secuencia, SQL/ER y rutas ✅

**Qué se hizo**
- **SQL → ER** (`sqlmodel.py`, con `sqlglot`): tablas, columnas, PK y las **3 formas de
  clave foránea** (`REFERENCES` en la columna, `FOREIGN KEY` de tabla y
  `ALTER TABLE … ADD CONSTRAINT`). El SQL se corta en sentencias respetando comillas y
  comentarios; cada sentencia se intenta con el dialecto pedido (`--dialect`) y luego con
  mysql, postgres, sqlite y tsql. Una sentencia ilegible da un aviso con archivo:línea y
  el análisis sigue.
- **Función → tabla** (confianza "probable"): se buscan cadenas con SQL dentro de cada
  función (`FROM`/`JOIN` = lee; `INSERT INTO`/`UPDATE`/`DELETE FROM` = escribe).
- **Rutas de Laravel** (`routes.py`): `Route::get/post/…` con `[X::class, 'm']`,
  `'X@m'` o controlador invocable, y `Route::resource/apiResource`. El método destino se
  marca como punto de entrada y la ruta aparece en el panel y en la secuencia.
- **Diagrama de secuencia** (`sequence.py` + `layout/sequence.py`): actor "Usuario" si la
  entrada es un punto de entrada, mensajes numerados 1, 1.1, 1.2…, retorno punteado solo
  si la función devuelve algo, fragmentos `loop`/`alt`/`opt`/`try`, recursión
  "(recursivo)" sin expandir, interfaz → `alt` "posible implementación", `new X()`.
  Las llamadas externas van a un participante gris "Externo" y se ocultan por defecto
  (botón "Mostrar llamadas externas"; al ocultarlas se renumera sin huecos).
- **Visor**: pestañas Secuencia y ER, panel de tabla (relaciones, leída por / escrita
  por), panel de función con "Ruta" y "Tablas (probable)".
- **CLI**: `desglosa sequence <ruta> --entry Clase.metodo [--depth N]` y
  `desglosa sql <ruta>` (sale con 1 si no hay tablas).
- 155 tests. Gate de la fase: fixture `tests/fixtures/sql/esquema.sql` con las 3 FKs y
  goldens de secuencia en `tests/golden/sequence/` (Laravel `store`, con y sin externos;
  TypeScript con interfaz de 2 implementaciones y recursión).

**Qué falló / encontré**
- `throw new DomainException()` salía como `DomainException()`: la IR del proyecto no
  guarda qué llamadas son `new`. Ahora `Analysis.new_calls` lo junta desde la extracción.
- En la vista ER el panel lateral tapaba el diagrama: el panel se dibuja antes de
  calcular el encuadre.

**Decisiones (revísalas)**
1. Función → tabla se detecta **solo con SQL escrito en cadenas**. Un ORM
   (`Factura::where(...)`, `session.query(...)`) no se detecta: haría falta adivinar el
   nombre de la tabla y la regla es no inventar.
2. Si el proyecto tiene esquema `.sql`, solo cuentan las tablas conocidas (evita falsos
   positivos como "from casa" en un texto normal).
3. En la secuencia, lo que hace una función llamada dentro de un `try` o un `for` se
   dibuja dentro de ese mismo fragmento (así se ve que todo ocurre "dentro del try").
4. En el `alt` de interfaz se dibuja la llamada a cada implementación pero no se expande
   su interior (si no, el diagrama se duplica). Se abre con clic en el mensaje.

**Probar**
```powershell
uv run desglosa sequence examples/laravel-mini --entry FacturaController.store -o secuencia.html
uv run desglosa sql examples/laravel-mini -o er.html
```

## Fase 6 — Pulido y publicación ✅

**Qué se hizo**
- **Reporte `.md`** (`analyze --report reporte.md`): resumen, archivos por lenguaje,
  funciones más llamadas, nunca llamadas (sin contar declaraciones de interfaz, puntos de
  entrada ni constructores), ciclos de llamadas (Tarjan iterativo), archivos no
  parseados, complejidad más alta y tablas SQL. Sin fechas: es determinista.
- **Visor**: ayuda de atajos (`?`, un `<dialog>` nativo), enfoque con teclado (`E`),
  aviso "Enfocado: X" con botón "Quitar enfoque", `Esc` quita el enfoque antes de subir.
- **Mapa**: las rutas de Laravel se dibujan como aristas (`routes/ → app/`, "3 rutas");
  antes `routes/` aparecía suelto.
- **ER**: las relaciones salen de la fila de la FK y llegan a la fila de la PK, en ángulo
  recto (antes iban de centro a centro de las cajas).
- **Rendimiento** (medido con un proyecto sintético y con 1 600 archivos Python reales,
  perfilando con `cProfile`): ver la sección "Rendimiento" del README.
- **Docs**: README completo con capturas, `ARCHITECTURE.md`, `IR.md`, `DISENO.md`, y los
  ejemplos con su HTML generado.

**Qué falló / encontré**
- Con varios procesos el análisis era **más lento** que con uno (14,6 s contra 8,7 s en
  1 000 archivos pequeños): en Windows cada proceso arranca de cero. Ahora hay un solo
  grupo de procesos y solo se usa con 2 MB de código o más.
- La etapa de **secuencias era cuadrática**: cada diagrama reindexaba todas las llamadas.
  En 400 archivos reales pasó de 163 s a 8 s con un índice compartido.
- El **resolvedor** recorría todos los archivos por cada import: de 7,3 s a 0,5 s.
- Al medir apareció un **error real**: con clases del mismo nombre en dos carpetas, el
  resolvedor usaba un índice antes de crearlo. Ningún fixture repetía nombres; ahora hay
  un test que sí.
- Con muchas clases homónimas, una llamada ambigua generaba un `alt` con 30 ramas y el
  HTML llegaba a 40 MB. Ahora se resume en un mensaje "N posibles".

**Decisiones (revísalas)**
1. Más de 4 destinos posibles → un mensaje "Varios posibles" (honesto y legible).
2. Varios procesos solo con ≥ 2 MB de código: es el punto donde, medido, empieza a ganar.
3. El HTML sigue pesando ~10× el código porque lleva todo precalculado. Calcular el
   layout en el navegador lo achicaría, pero rompería las garantías de "nada se
   superpone" que hoy se prueban en Python. Queda documentado como límite.
4. RF-18 (exportar a Mermaid, prioridad C) no se hizo: es lo primero que la SPEC permite
   recortar.

**Probar**
```powershell
uv run desglosa analyze examples/laravel-mini -o demo.html --report reporte.md
```
Abre `demo.html`, pulsa `?` para ver la ayuda y Alt+clic sobre una carpeta para enfocarla.

## Bloque 1 — Proyectos grandes ✅

**Qué se hizo**
- **Pruebas con proyectos reales** (descargados de GitHub, solo leídos):

  | Proyecto | Líneas | Análisis | Total | HTML | Abre |
  |---|---|---|---|---|---|
  | Spring Petclinic | 4 300 | 1 s | 3 s | 0,3 MB | al instante |
  | Express | 22 000 | 4 s | 5 s | 0,3 MB | al instante |
  | Laravel | 581 000 | 32 s | 72 s | 52 MB | 1,4 s |
  | Django | 530 000 | 35 s | 90 s | 69 MB | 1,8 s |

- **HTML comprimido por partes**: índice y un paquete por archivo (zlib + base64). El
  visor abre cada paquete al entrar a una función (~50 ms en Django).
- **Caché incremental** en JSON (nunca `pickle`), escrita en paralelo por los procesos
  de trabajo. Con un archivo cambiado en 200 000 líneas: de 13 s a ~6 s.
- **Instalación de una línea** desde GitHub en el README (`uv tool install git+…` o
  `uvx --from git+…`).

**Qué falló / encontré (y se corrigió)**
- El reporte de Laravel decía que la función más llamada era `Facade.expects` (3 543
  llamadas): las llamadas ambiguas (`->with()` existe en 20 clases) se contaban como
  llamada a cada candidata. Ahora, con más de 4 destinos posibles, no cuentan para
  ninguno (regla compartida por reporte, mapa y secuencia).
- En el mapa de Django, 17 carpetas con 145 flechas quedaban al 8 % de tamaño:
  ilegible. Ahora en niveles densos se dibuja el esqueleto de relaciones más fuertes
  (árbol de expansión máximo + las siguientes), con aviso de cuántas se ocultan.
- Las 220 carpetas de `tests/` de Django quedaban en una cadena de 14 "Otros" dentro de
  "Otros". Ahora se agrupan alfabéticamente en grupos parejos (2 niveles).
- En Express, 105 llamadas `this.set()` quedaban como externas (JS sin clases). Ahora se
  unen a la función del mismo archivo como "probable" (49 resueltas).
- La primera caché era **más lenta** que analizar de nuevo (leer anotaciones de tipo
  por cada objeto); ahora usa decodificadores armados una vez y guarda los flujos ya en
  formato HTML.
- Quitar los ".0" de los números ahorraba solo 2 % una vez comprimido y costaba 44 s en
  Django: ya no se hace dentro de los paquetes.
- Repartir las secuencias entre 8 procesos fue **2× más lento** (enviar 58 MB a cada
  proceso): se dejó en un solo proceso y quedó documentado.

**Decisiones (revísalas)**
1. Más de 4 destinos posibles = la llamada no se cuenta ni se dibuja (honesto: no dice
   a dónde va).
2. Mapa denso → esqueleto de relaciones más fuertes (1,5 por elemento).
3. La SPEC decía que una flecha agrupada lleva la *peor* confianza. En proyectos grandes
   eso deja casi todas las flechas punteadas (basta una llamada dudosa entre 744).
   Opciones: (a) mantener la regla, (b) usar la confianza de la mayoría y mostrar el
   desglose al pasar el mouse. **Decidido por Italo (2026-10-25): (b)**, hecho al inicio
   del Bloque 2.

**Probar**
```powershell
uv run desglosa analyze C:\ruta\a\un\proyecto\grande -o grande.html
```

## Bloque 2 — Preguntarle al código, galaxia y distribución ✅

**Qué se hizo**
- **Flechas del mapa con la confianza de la mayoría** (tu decisión del Bloque 1) y
  desglose al pasar el mouse: "12 exactas · 3 probables · 1 ambigua".
- **Consultas sin IA** desde la consola, en texto o `--json`:
  - `explain`: dónde está, firma, descripción, quién la llama y a quién llama (en el
    orden del código), complejidad, notas, tablas y ruta web.
  - `path`: el camino de llamadas más corto entre dos funciones; si no hay, avisa si
    existe al revés.
  - `buscar`: por palabras, separando `camelCase`/`snake_case` y con raíces comunes
    ("factura" encuentra `FacturacionService`).
  - Códigos de salida nuevos: 3 = nombre ambiguo (lista los candidatos), 4 = no
    encontrado.
- **Notas del código** (`TODO`, `FIXME`, `HACK`, `XXX`, `BUG`, `NOTE`, `WHY`): en el
  panel de cada función y en una sección del reporte.
- **Vista galaxia**: todos los archivos en una vista, agrupados en subsistemas con un
  Louvain propio (sin dependencias nuevas) y con los 10 archivos más conectados
  marcados. El reporte añade subsistemas, archivos centrales y conexiones entre
  subsistemas.
- **C#** (14 lenguajes): clases, structs, records, interfaces, constructores, `using`,
  `switch`, `foreach`, `try/catch/finally`, `Main` como punto de entrada.
- **Distribución**:
  - **GitHub Action** (`action.yml`): instala con `uvx`, descarga las gramáticas y
    ejecuta `analyze`. El CI la prueba en Windows y Linux con `examples/laravel-mini`
    y guarda el HTML como artefacto.
  - **Skill para asistentes de IA**: `desglosa skill install` copia un `SKILL.md` que
    enseña a usar `explain`, `path` y `buscar --json` y a distinguir una llamada
    `exacta` de una `probable`.
  - **PyPI**: metadatos completos, enlaces absolutos en el README y CI con Python 3.10
    (la mínima declarada). `uv build` genera el wheel con todo lo necesario (verificado:
    incluye `SKILL.md`, `app.js` y `style.css`).

**Qué falló / encontré (y se corrigió)**
- Una llamada ambigua con 2 destinos en la misma carpeta se contaba dos veces en la
  misma flecha. Ahora cada llamada cuenta una vez por flecha.
- `path` analiza sin flujos, y al terminar la caché borraba los flujos guardados por
  `analyze`. Ahora la limpieza solo toca lo que se consultó en esa ejecución (con test).
- La galaxia fallaba (`KeyError`) con llamadas desde código suelto fuera de funciones.
- El primer layout de la galaxia (fuerzas) dejaba 7 archivos en un lienzo de 1411×3616.
  Se cambió por un empaquetado codicioso: cada racimo se pega al que más llama.
- Nombres de subsistema poco útiles (".") y leyenda partida en dos columnas.
- El panel de código movía la línea marcada fuera de la vista al hacer scroll.
- Dos commits salieron con errores de ruff (una regex larga); se corrigieron en el
  siguiente. Desde entonces hago commit solo con ruff **y** pytest en verde.
- El docstring de `galaxy.py` seguía describiendo el layout de fuerzas; ya está
  corregido.
- Al probar la Action, un argumento malicioso (`$(touch PWNED)`) llegó como texto y no
  se ejecutó: las entradas van por variables de entorno. Un test lo vigila.

**Decisiones (revísalas)**
1. Cada consulta vuelve a cargar el proyecto con la caché (1–2 s normal, ~17 s en
   Django), sin servidor ni índice permanente: más simple y sin estado escondido.
2. `buscar` compara palabras, no significados (regla "sin IA"): "cobrar" no encuentra
   `pagar`.
3. Louvain implementado aquí y no con `networkx` (las dependencias están cerradas).
4. `skill install` no reemplaza un `SKILL.md` distinto sin `--force`, porque podría
   tener cambios tuyos. Por defecto va a `~/.claude/skills/`; con `--project`, al
   proyecto.
5. **PyPI no está publicado**: necesita tu cuenta y un token. El nombre `desglosa`
   estaba libre el 2026-10-25. Pasos en el README (`uv build`, `uv publish`).
6. La Action apunta a `@main`; cuando haya una versión estable conviene crear la etiqueta
   `v0.2.0` y recomendar `@v0.2.0`, para que un cambio en `main` no rompa a nadie.

**Probar**
```powershell
uv run desglosa explain examples/laravel-mini FacturacionService.emitir
uv run desglosa path examples/laravel-mini FacturaController.store MySqlFacturaRepository.guardar
uv run desglosa buscar examples/laravel-mini "calcular impuestos"
uv run desglosa skill install --dir $env:TEMP\skills-prueba
uv run desglosa analyze examples/laravel-mini -o demo.html   # pestaña Galaxia
```
