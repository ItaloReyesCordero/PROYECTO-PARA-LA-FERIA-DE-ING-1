# CLAUDE.md — Desglosa

**Proyecto:** Desglosa, CLI en Python que convierte código fuente en un HTML único e interactivo (mapa por niveles → diagrama de flujo por función → secuencia → ER), sin IA y sin red.

La especificación completa está en `SPEC.md`. Es la fuente de verdad. Léela entera al empezar cada sesión.

## Cómo trabajar conmigo (Italo)

- Respóndeme en español. Código e identificadores en inglés; textos de la interfaz y docs en español.
- Soy estudiante: antes de cada paso importante dime en 1–3 líneas qué vas a hacer y por qué. Explica los comandos que ejecutes.
- No inventes ni supongas. Si `SPEC.md` es ambigua, contradictoria o algo no funciona como dice, pregunta y propone 2 opciones.
- Trabaja por fases (SPEC §15). Al cerrar una fase: `uv run pytest`, `uv run ruff check .`, `git commit -m "fase N: …"`, y reporta: qué hiciste, qué falló, qué decidiste, y un comando para que yo lo pruebe. Luego espera mi "continúa".
- Sé crítico y directo: si algo de la SPEC es mala idea, dilo con el motivo.

## Reglas duras

- Código propio. Prohibido copiar código de Graphify o Archify o instalarlos.
- Dependencias de runtime solo: `tree-sitter`, `tree-sitter-language-pack`, `sqlglot`, `pathspec`. Dev: `pytest`, `ruff`. Otra cosa → pregúntame.
- De `tree-sitter-language-pack` usa solo `get_parser`, `get_language`, `download`, `downloaded_languages`. El motor de extracción es nuestro.
- `analyze` no usa red jamás: comprueba `downloaded_languages()` antes de `get_parser` (ese paquete descarga gramáticas solo si no las tiene). La red solo se usa en `desglosa setup`.
- Nunca ejecutar el código analizado. Nunca `innerHTML` con datos del código. Escapar el JSON embebido (`<`, `>`, `&`, U+2028/2029).
- Determinismo: ordenar todo, ids por hash estable, `json.dumps(sort_keys=True)`, sin timestamps.
- Windows primero: rutas con `pathlib`, salida en POSIX relativo, `encoding="utf-8"`, `newline="\n"`, workers de multiproceso como funciones de nivel módulo.

## Comandos

```
uv sync                         # instalar dependencias
uv run desglosa setup           # descargar gramáticas (una vez)
uv run desglosa doctor          # verificar gramáticas
uv run pytest -q                # tests
uv run ruff check . --fix       # lint
uv run desglosa debug-ast <archivo>   # ver nombres de nodos para ajustar un LangSpec
uv run desglosa analyze <ruta> -o demo.html
```

## Cuando un nombre de nodo del AST no coincide

No adivines. Ejecuta `desglosa debug-ast` sobre el fixture, mira el nombre real y corrige la tabla del `LangSpec` correspondiente. Anota la corrección en `docs/ADDING_A_LANGUAGE.md`.
