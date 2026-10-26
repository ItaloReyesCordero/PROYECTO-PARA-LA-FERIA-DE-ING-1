# Cambios

## [Sin publicar]

### Bloque 3 — Explicar y presentar: arquitectura, rutas, recorrido, Mermaid y estilos
- **Mapa de arquitectura**: capas (Rutas → Entrada → Lógica → Datos → Base de datos →
  Servicios externos) por convenciones de nombre y carpeta, con el motivo de cada una;
  servicios externos por sus imports (MySQL, PostgreSQL, SQLite, MongoDB, Redis, SQL/ORM,
  correo, HTTP, colas, nube, pagos, puerto serie). Las pruebas no son una capa. También
  en el reporte.
- **Trazar una ruta** en el visor: el camino de llamadas más corto hasta otra función,
  una tabla o «cualquier tabla», paso a paso y con la línea de cada llamada.
- **Recorrido animado del flujo** (`R`): prueba de escritorio nodo por nodo, eligiendo
  «sí»/«no» o en automático.
- **Modo presentación** (`P`, `#/mapa?presentar=auto`): visita guiada que avanza sola y
  se repite.
- **Mermaid**: `desglosa mermaid` y botón en el visor (flujo, secuencia, mapa,
  arquitectura); `desglosa dibujar` dibuja un flowchart de Mermaid con el estilo de
  Desglosa. Ejemplo `examples/dibujo/cajero.mmd`.
- **Estilos** moderno, clásico, pizarra y alto contraste (`S`); **minimapa** (`N`);
  exportar SVG/PNG del diagrama completo con título y **PDF** en páginas sin cortar cajas.
- Títulos de los README como notas de cada carpeta en el mapa (pendiente del Bloque 2).
- Layout por capas: columnas fijas para la arquitectura y cajas centradas con quienes las
  llaman.
- Corregido: `explain` y `mermaid` dibujaban el archivo pedido sin los símbolos de los
  demás (una llamada a otro archivo no salía como subproceso).

### Bloque 2 — Preguntarle al código, galaxia y distribución
- Mapa: cada flecha agrupada lleva la confianza de la **mayoría** de sus llamadas; al
  pasar el mouse se ve el desglose (exactas, probables, ambiguas).
- Consultas sin IA: `explain` (qué es, quién la llama, a quién llama, complejidad, notas,
  tablas, ruta), `path` (camino de llamadas más corto) y `buscar` (por palabras, con
  `camelCase`, `snake_case` y raíces comunes). Todas con `--json` y códigos de salida 3
  (nombre ambiguo) y 4 (no encontrado).
- Notas `TODO`, `FIXME`, `HACK`, `XXX`, `BUG`, `NOTE` y `WHY`: en el panel de cada función
  y en una sección del reporte.
- Vista **galaxia**: todos los archivos agrupados en subsistemas (Louvain propio,
  determinista) y los archivos centrales marcados; el reporte añade "Subsistemas",
  "Archivos centrales" y "Conexiones entre subsistemas".
- Lenguaje nuevo: **C#** (14 en total).
- **GitHub Action** (`uses: ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1@main`),
  probada en el CI con Windows y Linux.
- **Skill para asistentes de IA**: `desglosa skill install [--project | --dir]` y
  `desglosa skill show`.
- Listo para PyPI: metadatos, enlaces del README absolutos (PyPI no abre los relativos) y
  CI también con Python 3.10, la versión mínima declarada.

### Bloque 1 — Proyectos grandes
- Probado con proyectos reales: Laravel (581 000 líneas, 72 s), Django (530 000 líneas,
  90 s), Express y Spring Petclinic.
- HTML con índice y paquetes por archivo comprimidos; el visor los abre bajo demanda
  (Django abre en 1,8 s y cada función en ~50 ms).
- Caché incremental en JSON (`--no-cache`, `--cache-dir`).
- Llamadas con más de 4 destinos posibles no se cuentan ni se dibujan (el reporte decía
  que `Facade.expects` era la función más llamada de Laravel).
- JavaScript sin clases: `this.metodo()` se une a la función del mismo archivo.
- Mapa: grupos "Otros" alfabéticos y parejos (antes, cadenas de 14 "Otros") y esqueleto
  de relaciones más fuertes en niveles muy conectados.
- Más rápido: resolvedor, `to_jsonable`, layout de secuencias y del mapa.

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
