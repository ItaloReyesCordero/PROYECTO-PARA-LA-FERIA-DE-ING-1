# Cambios

## [Sin publicar]

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
