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
