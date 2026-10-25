# Cambios

## [0.1.0] — 2026-10-25

### Fase 6 — Pulido y publicación
- Reporte Markdown con `analyze --report`: archivos por lenguaje, funciones más llamadas,
  nunca llamadas, ciclos, archivos no parseados, complejidad y tablas.
- Visor: ayuda de atajos (`?`), enfoque con teclado (`E`), aviso de enfoque con botón
  para quitarlo, `Esc` quita el enfoque antes de subir de nivel.
- El mapa dibuja las rutas de Laravel (`routes/ → app/`, "3 rutas").
- ER: las relaciones salen de la fila de la columna FK y llegan a la de la PK, en ángulo
  recto.
- Rendimiento: el resolvedor ya no recorre todos los archivos por cada import, las
  secuencias comparten un índice (antes la etapa era cuadrática), un solo grupo de
  procesos para extracción y flujos, y varios procesos solo con 2 MB de código o más.
- Secuencia: una llamada con más de 4 destinos posibles se resume en un mensaje a
  "Varios posibles" en vez de un `alt` gigante.
- HTML más liviano: sin textos duplicados y con coordenadas enteras.
- README completo con capturas, `docs/ARCHITECTURE.md`, `docs/IR.md`, `docs/DISENO.md`
  y ejemplos con el HTML generado.

### Fase 5 — Secuencia, SQL/ER y rutas
- Diagrama de secuencia desde una función (fragmentos loop/alt/opt/try, recursión,
  "posible implementación", llamadas externas ocultables). Comando `sequence`.
- SQL → diagrama entidad-relación con las 3 formas de clave foránea y reintento con
  varios dialectos. Comando `sql` y opción `--dialect`.
- Enlace función → tabla (lee/escribe) desde el SQL escrito en cadenas.
- Rutas de Laravel como puntos de entrada.

### Fase 4 — Resto de lenguajes
- Go, Ruby, Rust, Kotlin y Swift: extracción, resolución y diagrama de flujo.
- `flow.py` independiente del lenguaje (la forma del AST la describe `LangHooks`).

### Fase 3 — Visor completo
- Mapa por niveles con aristas agregadas, "Otros (N)" y layout por capas.
- Comando `analyze`: HTML con mapa → flujo → subproceso → flujo, migas, buscador,
  panel de código, temas, modo fácil/técnico y leyenda.
- Ejemplo `examples/laravel-mini/`.

### Fase 2 — Diagrama de flujo
- Diagrama de flujo por función con los símbolos clásicos y todas las construcciones de
  control (if/else if, bucles, do-while, switch, try/catch/finally, saltos).
- Layout estructurado con carriles para bucles, escaleras para `else if`, columnas con
  conectores y enrutado de `break`/`continue` sin cruzar nodos.
- Visor HTML autocontenido (modo fácil/técnico, temas, zoom, leyenda, código, export).
- Comando `flow` y ejemplo GPS en C.

### Fase 1 — Extracción
- `scan`: recorrido ordenado, `.gitignore`/`.desglosaignore`/`--ignore`, minificados, binarios.
- Modelo intermedio (IR) con ids estables y JSON determinista.
- Extracción de Python, JavaScript, TypeScript, PHP, Java, C y C++.
- Resolución de llamadas con confianza exacta/probable/ambigua/externa.
- Comando `export-ir`.

### Fase 0 — Esqueleto
- Proyecto creado con `uv init --package`.
- Comandos `setup`, `doctor` y `debug-ast`.
- Verificación de gramáticas sin red antes de pedir un parser.
- Configuración de pytest, ruff y CI (Windows + Linux).
