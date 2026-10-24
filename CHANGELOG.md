# Cambios

## [Sin publicar]

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
