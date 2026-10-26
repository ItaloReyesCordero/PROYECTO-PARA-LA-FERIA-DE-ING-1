# Desglosa

**Convierte tu código en un mapa interactivo, con diagramas de flujo, de secuencia y
entidad-relación. Sin IA y sin internet.**

[![CI](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/actions/workflows/ci.yml/badge.svg)](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/actions/workflows/ci.yml)

![Diagrama de flujo generado del programa GPS en C](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/flujo-detalle.png)

Le das una carpeta con código y Desglosa genera **un solo archivo `.html`** que se abre
con doble clic, sin servidor y sin conexión. Dentro puedes ir del panorama general al
detalle:

1. **Mapa por niveles**: carpetas → archivos y clases → funciones, con flechas que dicen
   quién llama a quién (y cuántas veces).
2. **Diagrama de flujo** de cada función, con los símbolos clásicos (inicio/fin,
   proceso, decisión, entrada/salida, subproceso). Haz clic en un subproceso y se abre el
   flujo de esa función.
3. **Diagrama de secuencia** (UML) desde cualquier función: quién llama a quién y en qué
   orden, con bucles, condiciones y `try/catch`.
4. **Diagrama entidad-relación** de los archivos `.sql`, y qué funciones leen o escriben
   cada tabla.
5. **Galaxia**: todos los archivos del proyecto en una sola vista, agrupados en
   *subsistemas* que se detectan solos (archivos que se llaman mucho entre sí), con los
   archivos centrales marcados por su nombre.
6. **Arquitectura**: las capas del programa (rutas → controladores → servicios → datos →
   base de datos) y lo que usa de afuera (MySQL, Redis, correo, APIs…), detectado por
   nombres, carpetas e imports.

Y para explicarlo:

- **Recorrer un diagrama de flujo** paso a paso, como una prueba de escritorio: en cada
  rombo eliges «sí» o «no», o lo dejas en automático.
- **Trazar una ruta**: «¿cómo llega este botón a la base de datos?», resaltada paso a paso.
- **Modo presentación**: una visita guiada del proyecto que puede avanzar sola (ideal para
  un stand de feria).
- **Mermaid de ida y vuelta**: exporta cualquier diagrama a Mermaid, o dibuja tu propio
  diagrama de flujo escrito en Mermaid con el estilo de Desglosa.
- **Estilos** moderno, clásico (blanco y negro, como en un libro), pizarra y alto
  contraste; minimapa; exportar a SVG, PNG o PDF.

Además puedes **preguntarle al código** desde la consola (`explain`, `path`, `buscar`), ver
las notas `TODO`/`FIXME` de cada función, usarlo en GitHub Actions o dárselo a tu asistente
de IA como skill.

Todo sale de **análisis estático**: Desglosa lee el código con
[tree-sitter](https://tree-sitter.github.io/), nunca lo ejecuta.

## Capturas

| Mapa (tema oscuro) | Secuencia de `FacturaController.store()` |
|---|---|
| ![Mapa por niveles](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/mapa.png) | ![Diagrama de secuencia](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/secuencia.png) |

| Diagrama entidad-relación | Flujo completo de `main()` en columnas |
|---|---|
| ![Diagrama entidad-relación](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/er.png) | ![Flujo del GPS](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/flujo-gps.png) |

| Galaxia: subsistemas y archivos centrales | Arquitectura de Spring Petclinic |
|---|---|
| ![Vista galaxia](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/galaxia.png) | ![Mapa de arquitectura](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/arquitectura.png) |

| Recorrido paso a paso del `main()` del GPS | «¿Cómo llega `store()` a la base de datos?» |
|---|---|
| ![Recorrido animado del flujo](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/recorrido.png) | ![Ruta hasta la base de datos](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/ruta.png) |

| Diagrama escrito en Mermaid, dibujado en estilo clásico |
|---|
| ![Cajero automático dibujado desde Mermaid](https://raw.githubusercontent.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/main/docs/img/dibujo-clasico.png) |

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/) (en Windows: `winget install astral-sh.uv`).
uv descarga Python si hace falta.

**Opción 1: instalar el comando `desglosa`** (recomendado):

```powershell
uv tool install git+https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1
desglosa setup                      # descarga las gramáticas UNA vez (único paso con internet)
desglosa analyze C:\ruta\a\tu\proyecto -o mapa.html
```

**Opción 2: usarlo sin instalar nada**, directo desde GitHub:

```powershell
uvx --from git+https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1 desglosa setup
uvx --from git+https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1 desglosa analyze . -o mapa.html
```

**Opción 3: para desarrollar** (clonar el repositorio):

```powershell
git clone https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1.git desglosa
cd desglosa
uv sync
uv run desglosa setup
uv run desglosa doctor    # debe mostrar 14/14 lenguajes listos
```

Funciona en Windows, Linux y macOS con Python 3.10 o más nuevo (el CI prueba Windows y
Linux con 3.12 y 3.13, y Linux con 3.10).

### En GitHub Actions

Genera el HTML en cada push y guárdalo como artefacto descargable:

```yaml
# .github/workflows/desglosa.yml
name: Mapa del código
on: [push]
jobs:
  desglosa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1@main
        with:
          path: .                  # carpeta a analizar
          output: desglosa.html
          report: reporte.md       # opcional
      - uses: actions/upload-artifact@v4
        with:
          name: mapa-del-codigo
          path: |
            desglosa.html
            reporte.md
```

Entradas: `path`, `output`, `report`, `args` (opciones extra de `analyze`, p. ej.
`--lang php`), `check` y `python-version`. Con `check: true` la Action también ejecuta
`desglosa check` y falla si aparece un **ciclo de dependencias nuevo** (para que el HTML
se suba igual, pon `if: always()` en el paso de `upload-artifact`). Los ciclos que ya
existen se aceptan una vez con `desglosa check . --aceptar`, que escribe
`.desglosa-check.json`; súbelo al repositorio. Las entradas pasan al comando como variables de entorno,
nunca pegadas dentro del script, así que un valor malicioso no puede ejecutar comandos.

### Como skill de tu asistente de IA

```powershell
desglosa skill install            # en tu usuario: ~/.claude/skills/desglosa/SKILL.md
desglosa skill install --project  # solo en este proyecto: .claude/skills/desglosa/
desglosa skill show               # imprime el SKILL.md para copiarlo en otro asistente
```

Con la skill, Claude Code (u otro asistente compatible) usa `explain`, `path` y `buscar
--json` para responder preguntas sobre tu proyecto sin leer todos los archivos, y sabe
distinguir una llamada `exacta` de una `probable`. Si ya existe una versión distinta, no
la pisa salvo con `--force`.

## Uso

```powershell
# Todo el proyecto: mapa → flujos → secuencias → ER, más un reporte en Markdown
uv run desglosa analyze examples/laravel-mini -o demo.html --report reporte.md

# El diagrama de flujo de una sola función
uv run desglosa flow examples/gps-c gps.c:main -o gps.html

# Diagrama de secuencia desde un punto de entrada
uv run desglosa sequence examples/laravel-mini --entry FacturaController.store -o secuencia.html

# Solo el diagrama entidad-relación
uv run desglosa sql examples/laravel-mini -o er.html

# El flujo de una función en Mermaid (para un README, Notion o mermaid.live)
uv run desglosa mermaid examples/laravel-mini FacturacionService.emitir

# Qué funciones cambiaron desde un commit (o entre dos carpetas), con su flujo de antes y después
uv run desglosa comparar . --desde HEAD~5 -o cambios.html

# ¿Hay ciclos entre carpetas o capas que se saltan? (sale con código 5 si hay ciclos nuevos)
uv run desglosa check examples/laravel-mini

# Pseudocódigo estilo PSeInt de una función o de un archivo entero (.psc)
uv run desglosa pseudo examples/gps-c gps.c -o gps.psc

# Diagrama de clases UML de una carpeta (o en Mermaid con --mermaid)
uv run desglosa clases examples/laravel-mini --carpeta app/Services -o clases.html

# Dibujar con el estilo de Desglosa un diagrama de flujo escrito a mano en Mermaid
uv run desglosa dibujar examples/dibujo/cajero.mmd -o cajero.html
```

| Comando | Qué hace |
|---|---|
| `setup` | descarga las gramáticas (la única vez que se usa internet) |
| `doctor` | muestra versiones y qué gramáticas están disponibles |
| `analyze <ruta>` | genera el HTML completo; `--report archivo.md` añade el reporte |
| `flow <ruta> <archivo>:<función>` | el flujo de una función |
| `sequence <ruta> --entry Clase.metodo` | la secuencia desde una función (`--depth`, 4 por defecto) |
| `sql <ruta>` | el diagrama entidad-relación (`--dialect mysql\|postgres\|sqlite\|tsql`) |
| `explain <ruta> <nombre>` | todo sobre una función o clase: dónde está, quién la llama, a quién llama, complejidad |
| `path <ruta> <desde> <hasta>` | el camino de llamadas más corto entre dos funciones |
| `buscar <ruta> "texto"` | busca funciones y clases por palabras (nombre, descripción, archivo) |
| `mermaid <ruta> <nombre>` | el flujo (o con `--secuencia`, la secuencia) de una función en Mermaid |
| `comparar <antes> <después>` | funciones nuevas, eliminadas y cambiadas entre dos carpetas; o `comparar <ruta> --desde COMMIT [--hasta COMMIT]` con git (`--json`) |
| `check <ruta>` | ciclos entre carpetas o archivos y capas que se saltan; falla (código 5) con ciclos nuevos (`--aceptar`, `--capas`, `--json`) |
| `pseudo <ruta> <nombre>` | pseudocódigo estilo PSeInt de una función, o de todo un archivo (`gps.c`) |
| `clases <ruta>` | diagrama de clases UML de una carpeta (`--carpeta`, `--mermaid`) |
| `dibujar <archivo.mmd>` | dibuja un diagrama de flujo de Mermaid con el estilo de Desglosa (ver abajo) |
| `export-ir <ruta>` | el modelo intermedio en JSON (ver [docs/IR.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/IR.md)) |
| `skill install` / `skill show` | instala o muestra la skill para asistentes de IA |
| `debug-ast <archivo>` | imprime el árbol sintáctico (para agregar lenguajes) |

Opciones comunes: `--lang php,python` (solo esos lenguajes), `--ignore PATRON`
(repetible), `--no-source` (no incluir el código en el HTML), `--jobs N` (procesos en
paralelo), `--h-as cpp` (tratar `.h` como C++), `--no-cache` (analizar todo desde cero),
`--cache-dir CARPETA` (dónde guardar la caché).

**Caché:** la segunda vez que analizas un proyecto, solo se vuelven a procesar los
archivos que cambiaron. Se guarda en la carpeta de caché del usuario
(`%LOCALAPPDATA%\desglosa` en Windows), en JSON; nunca dentro de tu proyecto. Si Desglosa
se actualiza, la caché vieja deja de usarse sola.

Desglosa respeta `.gitignore`, `.desglosaignore` y salta `vendor/`, `node_modules/`,
archivos minificados, binarios y archivos de más de 1 MB.

### Preguntarle al código (sin IA)

```powershell
desglosa explain . FacturacionService.emitir     # ¿qué es, quién la usa, qué usa?
desglosa path . FacturaController.store MySqlFacturaRepository.guardar
desglosa buscar . "calcular impuestos"
```

```
Camino más corto (2 pasos):
  FacturaController.store
    --llama [probable]--> FacturacionService.emitir
    --llama [probable]--> MySqlFacturaRepository.guardar
```

Con `--json` la respuesta sale en JSON, para scripts o para un asistente de IA. Si un
nombre corresponde a varias funciones, Desglosa no elige: las lista y sale con código
`3`; usa `archivo:Nombre` para precisar. En un proyecto normal cada consulta tarda 1–2 s;
en uno de medio millón de líneas (Django), ~17 s con la caché llena.

Códigos de salida: `0` bien, `1` error de uso, `2` faltan gramáticas (ejecuta `setup`),
`3` nombre ambiguo, `4` no encontrado, `5` `check` encontró un ciclo nuevo.

### Dibujar un diagrama de flujo escrito a mano

Escribe tu algoritmo en [Mermaid](https://mermaid.js.org/) y Desglosa lo dibuja con los
símbolos clásicos, en ángulo recto y de arriba hacia abajo:

```
flowchart TD
    A([Inicio]) --> B[/Leer la tarjeta/]
    B --> C@{ shape: manual-input, label: "Ingresar el PIN" }
    C --> D{"¿PIN correcto?"}
    D -- no --> C
    D -- sí --> E@{ shape: display, label: "Bienvenido" }
    E --> F([Fin])
```

Formas: `([…])` inicio/fin, `[…]` proceso, `[[…]]` subproceso, `{…}` decisión, `[/…/]`
entrada/salida, `((…))` conector y, con la sintaxis de Mermaid 11.3, `manual-input`
(teclado), `display` (pantalla) y `doc` (documento). Flechas `-->`, `-- texto -->`,
`-->|texto|`, `-.->`, `==>` y `A & B --> C`. Los estilos (`classDef`, `style`) se
ignoran: el estilo lo pone Desglosa. Ejemplo completo en `examples/dibujo/cajero.mmd`.

## Cómo se usa el visor

- **Clic** en un elemento del mapa para entrar; las **migas** de arriba sirven para volver.
- **Alt+clic** (o la tecla `E`) **enfoca** un elemento: resalta lo que usa y lo que lo usa.
- En un flujo, el **clic en un subproceso** (rectángulo con doble línea) abre esa función.
- **Modo fácil / técnico** (`M`): textos en español ("¿total > 0?", "Para cada item en
  items") o el código literal.
- `/` buscar · `Esc` subir · `+` `−` `0` zoom · `F` encuadrar · `T` tema · `S` estilo ·
  `N` minimapa · `?` ayuda.
- Cada función tiene las pestañas **Flujo · Secuencia · Pseudocódigo · Código**. El
  pseudocódigo está escrito como en PSeInt (`Si … Entonces`, `Mientras … Hacer`,
  `Para i <- 0 Hasta n - 1`, `Escribir`, `Leer`) y se copia o descarga como `.psc`.
- El HTML de `comparar` abre en **Cambios**: las funciones nuevas, eliminadas y cambiadas
  por archivo; en una cambiada, su diagrama de flujo de antes y de después lado a lado, con
  los pasos nuevos en verde y los quitados en rojo.
- Pestañas **Mapa · Arquitectura · Clases · Dependencias · Galaxia · Entidad-relación**.
  «Dependencias» lista los ciclos (con la llamada que sostiene cada paso, que abre su
  flujo) y las llamadas que se saltan una capa, que en Arquitectura salen punteadas. En «Clases», el
  diagrama UML de cada carpeta; el clic en una clase gris lleva a la carpeta donde está. En la arquitectura, pasa
  el mouse por un componente para ver *por qué* está en esa capa. En la galaxia, el clic
  en un subsistema de la leyenda lo resalta; el clic en un archivo abre su lugar en el
  mapa y Alt+clic lo enfoca con sus conexiones.
- **▶ Recorrer** (`R`) en un flujo: avanza nodo por nodo y resalta la línea de código. En
  cada rombo eliges «sí» o «no», o lo dejas en automático: en un bucle entra una vez y
  sale; en un «si» sigue el camino principal. `←` `→` y espacio controlan el recorrido.
- **Trazar ruta…** y **¿Cómo llega a la base de datos?** en el panel de una función: el
  camino de llamadas más corto hasta otra función o una tabla, paso a paso.
- **Presentar** (`P`): una visita guiada (portada, mapa, arquitectura, galaxia, el flujo
  de un punto de entrada recorrido solo, su secuencia, su ruta a la base de datos y el
  ER), con un texto sencillo en cada paso. Abre el HTML con `#/mapa?presentar=auto` y
  avanza sola y se repite: lista para dejarla en un stand.
- Panel lateral con el código fuente, las líneas del nodo seleccionado resaltadas, las
  llamadas entrantes y salientes, la complejidad, las notas del código (`TODO`, `FIXME`,
  `HACK`, `XXX`, `BUG`, `NOTE`, `WHY`) y, si existen, la ruta HTTP y las tablas.
- **Estilos**: moderno (tema claro u oscuro), clásico (blanco y negro, como en un libro),
  pizarra y alto contraste. El **minimapa** aparece cuando el diagrama no entra en pantalla.
- Exportar: **SVG** y **PNG** del diagrama completo (también los muy largos), **PDF**
  (partido en páginas sin cortar las cajas; elige «Guardar como PDF» en el diálogo de
  impresión) y **Mermaid**.
- En las carpetas con un `README`, su título y primera frase aparecen como nota en el mapa.

Las líneas sólidas son relaciones seguras; las punteadas, probables o ambiguas; las grises,
llamadas fuera del proyecto. Así nunca se presenta una suposición como un hecho.

## Ejemplos incluidos

| Carpeta | Qué muestra | HTML ya generado |
|---|---|---|
| [`examples/gps-c/`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/tree/main/examples/gps-c/) | lectura de un GPS por puerto serie en C: bucles, decisiones, tramas NMEA; el flujo se parte en columnas con conectores | [`desglosa.html`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/examples/gps-c/desglosa.html) |
| [`examples/laravel-mini/`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/tree/main/examples/laravel-mini/) | un mini sistema de facturación en Laravel: rutas, controlador, servicio, interfaz de repositorio con implementación MySQL y esquema SQL | [`desglosa.html`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/examples/laravel-mini/desglosa.html) · [`reporte.md`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/examples/laravel-mini/reporte.md) |
| [`examples/dibujo/`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/tree/main/examples/dibujo/) | un cajero automático escrito a mano en Mermaid (`cajero.mmd`) y dibujado por Desglosa | [`cajero.html`](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/examples/dibujo/cajero.html) |

Descarga el `.html` y ábrelo con doble clic.

## Lenguajes

| Lenguaje | Mapa y llamadas | Diagrama de flujo | Nivel |
|---|---|---|---|
| Python | ✔ | ✔ | completo |
| JavaScript | ✔ | ✔ | completo |
| TypeScript (y TSX) | ✔ | ✔ | completo |
| PHP (con rutas de Laravel) | ✔ | ✔ | completo |
| Java | ✔ | ✔ | completo |
| C# | ✔ | ✔ | completo (nuevo) |
| C | ✔ | ✔ | completo |
| C++ | ✔ | ✔ | completo |
| Go | ✔ | ✔ | mejor esfuerzo |
| Ruby | ✔ | ✔ | mejor esfuerzo |
| Rust | ✔ | ✔ | mejor esfuerzo |
| Kotlin | ✔ | ✔ | mejor esfuerzo |
| Swift | ✔ | ✔ | mejor esfuerzo |
| SQL | tablas, PK y FK | — | completo |

"Mejor esfuerzo" quiere decir que pasan los mismos tests que los demás, pero sus
construcciones menos comunes (macros, bloques, metaprogramación) se dibujan de forma más
simple. Detalles por lenguaje en [docs/ADDING_A_LANGUAGE.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/ADDING_A_LANGUAGE.md).

## Rendimiento

Probado con proyectos reales de GitHub, en un portátil con Windows 11 y 8 núcleos
(Python 3.14), comando `analyze` completo y sin caché (medido el 2026-10-26, con todas las
vistas del Bloque 3):

| Proyecto | Líneas | Análisis | Total | HTML | Abre en el navegador |
|---|---|---|---|---|---|
| `examples/laravel-mini` | 260 | 0,1 s | 2 s | 0,2 MB | al instante |
| [Spring Petclinic](https://github.com/spring-projects/spring-petclinic) (Java) | 4 300 | 1 s | 3 s | 0,4 MB | al instante |
| [Express](https://github.com/expressjs/express) (JavaScript) | 22 000 | 4 s | 6 s | 0,5 MB | al instante |
| [Laravel](https://github.com/laravel/framework) (PHP) | 581 000 | 30 s | 82 s | 55 MB | 1,1 s |
| [Django](https://github.com/django/django) (Python) | 530 000 | 34 s | 106 s | 74 MB | 1,4 s |

"Análisis" es lo que imprime la consola; "Total" incluye generar el HTML. La SPEC pedía
1 000 archivos en menos de 2 minutos: Laravel tiene 3 030 y Django 2 968. El visor en sí
ocupa unos 140 KB de cada HTML; el resto son los datos del proyecto. Lo que más tarda al
generar el HTML son las secuencias (Laravel tiene 23 000).

- **Con caché**, si cambias un archivo de un proyecto de 200 000 líneas, el análisis baja
  de 13 s a unos 6 s.
- **El HTML abre rápido aunque pese mucho:** cada archivo de código va comprimido aparte
  y el navegador descomprime solo lo que abres (una función se abre en ~50 ms, incluso en
  Django). Funciona sin internet, con doble clic.
- Varios procesos solo se usan cuando el código suma 2 MB o más: por debajo, arrancar
  procesos en Windows cuesta más de lo que ahorra (medido). Con `--jobs N` se fuerza.
- En los niveles del mapa muy conectados (en Django, 17 carpetas con 145 relaciones) se
  dibujan solo las relaciones más fuertes, y el visor avisa cuántas se ocultaron.

## Límites

Es análisis estático, con límites que conviene conocer (y explicar):

- La **inyección de dependencias** y las interfaces no dicen qué clase llega en
  ejecución: se muestran las *posibles implementaciones*.
- Las **llamadas dinámicas** (`$obj->$metodo()`, reflexión, callbacks) quedan como
  externas o ambiguas. Nunca se adivina.
- Las **macros y `#ifdef`** no se expanden; los ternarios y lambdas quedan dentro del
  texto del nodo; `goto` no se sigue.
- El **modo fácil reformula, no explica**: traduce la sintaxis a español, no entiende la
  intención del código.
- La relación función → tabla solo ve **SQL escrito en cadenas**, no consultas de un ORM.
- En frameworks grandes muchas llamadas son **ambiguas** (`->with()` existe en 20 clases
  de Laravel). Si una llamada tiene más de 4 destinos posibles, no se cuenta ni se dibuja
  como llamada a ninguno.

Lista completa en [docs/LIMITES.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/LIMITES.md).

## Cómo funciona

```
carpeta → escaneo → árbol sintáctico (tree-sitter) → símbolos y llamadas
        → resolución (exacta / probable / ambigua / externa)
        → diagramas y coordenadas → un solo HTML
```

Un único motor sirve a los 14 lenguajes: cada lenguaje solo describe la forma de su árbol
sintáctico (`LangSpec`) y unos pocos ganchos (`LangHooks`). El resultado es determinista:
el mismo código produce exactamente el mismo HTML.

- [docs/ARCHITECTURE.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/ARCHITECTURE.md): etapas, módulos y decisiones.
- [docs/IR.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/IR.md): el modelo intermedio.
- [docs/DISENO.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/DISENO.md): colores, símbolos y reglas visuales.
- [docs/ADDING_A_LANGUAGE.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/ADDING_A_LANGUAGE.md): cómo agregar un lenguaje.
- [docs/PROGRESO.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/docs/PROGRESO.md): bitácora de las fases del proyecto.

## Desarrollo

```powershell
uv sync
uv run desglosa setup
uv run pytest -q                    # tests
uv run ruff check .                 # estilo
uv run pytest --update-golden       # regenerar salidas esperadas (revisa el diff)
```

Para regenerar los ejemplos:

```powershell
uv run desglosa analyze examples/gps-c -o examples/gps-c/desglosa.html
uv run desglosa analyze examples/laravel-mini -o examples/laravel-mini/desglosa.html --report examples/laravel-mini/reporte.md
```

Publicar una versión en PyPI (lo hace el mantenedor con su cuenta y un token de PyPI):

```powershell
uv build                  # crea dist/desglosa-X.Y.Z.tar.gz y el .whl
uv publish                # pide el token; después: uv tool install desglosa
```

Seguridad: el código analizado nunca se ejecuta, el visor no usa `innerHTML` con datos del
código y el JSON incrustado escapa `<`, `>`, `&` y los separadores de línea Unicode (hay
un test con `</script><script>alert(1)</script>` dentro de una cadena).

## Licencia y créditos

MIT © 2026 Italo Reyes Cordero. Ver [LICENSE](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/LICENSE).

Proyecto para la Feria de Ingeniería de la Universidad Continental. Inspirado
conceptualmente en Graphify y Archify, sin código de ninguno de los dos; dependencias y
licencias en [NOTICE.md](https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1/blob/main/NOTICE.md).
