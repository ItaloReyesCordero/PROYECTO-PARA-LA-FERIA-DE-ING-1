# Límites conocidos

Desglosa hace **análisis estático**: lee el código, nunca lo ejecuta. Eso trae límites
que conviene conocer (y explicar en la feria) en vez de esconder.

## Resolución de llamadas
- **Inyección de dependencias e interfaces**: si una variable es de tipo interfaz, no se
  sabe qué clase llegará en tiempo de ejecución. Se muestran las *posibles
  implementaciones* conocidas (confianza "probable").
- **Llamadas dinámicas** (`$obj->$metodo()`, reflexión, callbacks, metaprogramación de
  Ruby, `getattr`) quedan como "externa" o "ambigua". Nunca se adivina.
- El tipo de una variable solo se conoce si hay una pista en la misma función o clase:
  anotación de tipo, parámetro tipado, `x = new Clase()` o un atributo asignado así.
- En C/C++, una función se considera "importada" si el archivo incluye un `.h` con el
  mismo nombre base que el `.c` donde está definida (`pago.h` ↔ `pago.c`).

- **Llamadas con muchos destinos posibles**: en frameworks grandes un nombre como
  `with()` o `create()` existe en decenas de clases. Si una llamada tiene más de 4
  destinos posibles, no se cuenta como llamada a ninguno (ni en el reporte, ni en el
  mapa, ni en la secuencia, donde aparece como "N posibles"). Esas funciones tampoco se
  marcan como "nunca llamadas".
- **JavaScript sin clases** (estilo Express: `app.set = function set() {…}`): una llamada
  `this.set()` se une a la función `set` del mismo archivo con confianza "probable".

## Mapa
- En un nivel muy conectado (más de 1,5 relaciones por elemento) se dibuja solo el
  esqueleto de relaciones más fuertes, y el visor dice cuántas se ocultaron.
- Una flecha del mapa agrupa muchas llamadas y se dibuja con la confianza **de la
  mayoría** (en empate, la menos segura). Una flecha sólida puede incluir algunas
  llamadas dudosas: el desglose exacto se ve al pasar el mouse por la flecha.

## Galaxia
- Es una **vista de conjunto**, no un plano exacto: las líneas pueden cruzar por encima
  de otros puntos, y la posición de un racimo solo indica con quién se llama más.
- Dos archivos se unen solo por **llamadas con destino conocido**; un `import` sin
  llamadas no los une. Los archivos que no se llaman con ningún otro van juntos al grupo
  "sin conexiones". Con menos de 3 archivos no hay galaxia.
- Los subsistemas salen del algoritmo de Louvain: son deterministas, pero un cambio
  pequeño en el código puede pasar un archivo de un subsistema a otro. Los de menos de 3
  archivos se juntan en "grupos pequeños".
- Los nombres de los subsistemas salen de las carpetas de sus archivos; si están
  repartidos, el nombre muestra la carpeta común y las principales.
- Se dibujan como máximo las 4 000 conexiones más fuertes (más líneas vuelven lento el
  SVG).

## Consultas (`explain`, `path`, `buscar`)
- **`buscar` compara palabras, no significados**: encuentra "factura" en
  `FacturacionService` (raíz común de 5 letras o más) y separa `camelCase` y
  `snake_case`, pero "cobrar" no encuentra `pagar`.
- **`path`** da el camino con menos pasos siguiendo las llamadas resueltas; puede pasar
  por una llamada ambigua (de 2 a 4 destinos), y cada paso dice su confianza. No sigue
  llamadas dinámicas.
- Cada consulta vuelve a cargar el proyecto (con la caché): 1–2 s en un proyecto normal,
  ~17 s en Django.

## Notas del código
- Solo se reconocen `TODO`, `FIXME`, `HACK`, `XXX`, `BUG`, `NOTE` y `WHY` en
  **mayúsculas**, con un marcador de comentario antes en la misma línea (`#`, `//`, `/*`,
  `*`, `--`, `<!--`). Un `todo` en minúsculas o `x = "TODO"` no cuentan, pero una cadena
  que contenga `"// TODO"` sí se toma como nota (se busca por líneas, sin el árbol).
- Una nota se asigna a la función o clase más interna que la contiene. Las que están
  fuera de toda función o clase salen en el reporte, pero no en el panel del visor.

## GitHub Action y skill
- La Action descarga las gramáticas en cada ejecución (es el paso con red); no las guarda
  en la caché de GitHub.
- `desglosa skill install` escribe el formato de Claude Code (`SKILL.md` con nombre y
  descripción). Para otros asistentes, `desglosa skill show` imprime el texto para
  copiarlo donde corresponda.

## Diagramas de flujo
- **Macros y `#ifdef`** de C/C++/Rust no se expanden: se dibuja el código tal como está.
- **Control de flujo dentro de expresiones** (ternarios `a ? b : c`, `&&`/`||` en
  cortocircuito, lambdas, comprensiones de listas) queda dentro del texto del nodo.
- **`goto`** se dibuja como un nodo "goto etiqueta (no soportado)" y se emite una
  advertencia; el diagrama no sigue el salto.
- **Funciones gigantes**: si pasan de `--max-flow-nodes` (120), los bloques más profundos
  se colapsan en un nodo "Bloque (L12–L40)".
- **El modo fácil reformula, no explica**: traduce operadores y usa plantillas en español
  ("¿total > 0?", "Para cada item en items"), pero no entiende la intención del código.

## Diagrama de secuencia
- Sale de las llamadas **en el orden en que aparecen en el código**, no del orden real de
  ejecución (que depende de los datos).
- Se corta en `--depth` niveles (4 por defecto) y en 200 mensajes.
- Si una llamada tiene más de 4 destinos posibles (nombres repetidos en muchas carpetas),
  se dibuja un solo mensaje "nombre() — N posibles" hacia "Varios posibles".
- En una llamada por interfaz se dibuja el mensaje a cada implementación conocida, pero
  no se expande lo que hace cada una.

## SQL y entidad-relación
- Solo se leen archivos `.sql` con `CREATE TABLE` / `ALTER TABLE`. Las migraciones
  escritas en código (Laravel `Schema::create`, Django `models.py`) no se convierten en
  tablas.
- El enlace función → tabla solo ve **SQL escrito en cadenas** (`"SELECT … FROM x"`). Las
  consultas de un ORM (`Factura::where`, `session.query`) no se detectan.
- SQL armado por partes (`"SELECT * FROM " . $tabla`) solo se reconoce si el nombre de la
  tabla está escrito en la cadena.

## Rutas
- Solo rutas de Laravel en `routes/*.php`. Las rutas con closure
  (`Route::get('/x', function () {…})`) no apuntan a ningún método y se ignoran.

## Impresión y exportación
- El **PDF** lo hace el navegador («Guardar como PDF» en el diálogo de impresión): no hay
  librería de PDF. Las páginas se cortan en un hueco entre cajas; si una caja es más alta
  que la página, se corta igual. Entre páginas se escribe «continúa en la página N» en
  lugar del símbolo `conector_pagina` (pentágono) de la SPEC.
- Al imprimir se usa fondo blanco: el estilo moderno pasa al tema claro, y pizarra o alto
  contraste pasan a clásico.
- El **PNG** de un diagrama enorme baja su escala (de 2× hasta 0,1×) para no superar el
  límite de los navegadores (~16 000 px por lado): en Django un nivel muy grande puede
  quedar con letra chica.

## Mermaid
- La **exportación** usa las formas clásicas de Mermaid y, para pantalla, teclado y
  documento, las de Mermaid 11.3 (`curv-trap`, `sl-rect`, `doc`): un visor de Mermaid más
  antiguo no las dibuja. El diagrama lo acomoda Mermaid: no conserva las columnas ni los
  carriles de los bucles de Desglosa.
- En la secuencia, los números jerárquicos (1.2.1) van dentro del texto del mensaje, y
  una llamada a una interfaz se exporta como `alt` con cada implementación. El botón del
  visor arma el texto desde el dibujo: ahí un `catch` sale como un `alt` propio; con
  `desglosa mermaid --secuencia` sale como `else` de su `try`.
- **`dibujar`** entiende solo diagramas de flujo (`flowchart`/`graph`): nodos, formas,
  flechas con texto, `&`, punteadas y gruesas. Los subgrafos se dibujan sin su recuadro y
  `classDef`, `style`, `click` se ignoran (con aviso). Los nombres de nodo pueden tener
  letras, números, `_` y `.`, no guiones.
- El dibujo usa el layout por capas (no el de los flujos del código): las flechas que
  vuelven atrás (bucles) suben por el costado y pueden salir del mismo lado por el que
  entra otra flecha.

## Mapa de arquitectura
- Las **capas salen de convenciones de nombre y carpeta** (`…Controller`,
  `services/`, `models/`, también en español: `ServicioPago`, `repositorios/`). Un
  proyecto que no las sigue queda casi vacío; el visor dice cuántos componentes no se
  muestran. Es una convención, no una certeza: cada componente dice por qué está en su capa.
- Las **pruebas** (`…Test`, `test_…`, carpetas `tests/`, `spec/`) no son una capa y no se
  dibujan.
- Los **servicios externos** solo se detectan por los imports de una tabla conocida
  (MySQL, PostgreSQL, SQLite, MongoDB, Redis, SQL/ORM, correo, HTTP, colas, nube, pagos,
  puerto serie). Una conexión hecha sin importar nada (p. ej. una URL en un archivo de
  configuración) no aparece. Go `net/http` cuenta como HTTP aunque sea un servidor.
- Las llamadas dentro de una misma capa no se dibujan (el visor dice cuántas son). Con más
  de 12 componentes en una columna, el resto va a «Otros (N)»; en diagramas muy
  conectados se dibuja el esqueleto de relaciones más fuertes.

## Trazar una ruta
- Es el camino **más corto** por llamadas resueltas (exactas o probables, y de un método
  de interfaz a sus implementaciones). No sigue llamadas ambiguas ni dinámicas, así que
  «no hay camino» puede querer decir «no se ve estáticamente».
- «Cualquier tabla» llega a la primera función que lee o escribe una tabla con SQL en
  cadenas; las consultas de un ORM no cuentan (ver SQL y entidad-relación).

## Recorrido y presentación
- El recorrido del flujo **no ejecuta el código**: en modo automático sigue una regla
  fija (en un bucle entra una vez y sale; en un «si», la salida con más pasos por
  delante). No conoce los valores de las variables: es una prueba de escritorio guiada,
  no una simulación. Se detiene a los 400 pasos.
- La presentación elige el punto de entrada por reglas (rutas web primero, luego `main`;
  entre ellas, la que llega a la base de datos y tiene más decisiones y llamadas).

## Tamaño del HTML
- El HTML lleva todos los diagramas ya calculados, comprimidos: unos 52 MB para Laravel
  (581 000 líneas) y 69 MB para Django (530 000). Abre en 1–2 s porque cada archivo se
  descomprime solo al abrirlo, pero un archivo así cuesta compartirlo por correo.
  Desglosa avisa a partir de 100 MB.
- Necesita un navegador actual (Chrome, Edge, Firefox o Safari de los últimos años):
  usa `DecompressionStream`, que los navegadores muy antiguos no tienen.

## Errores de sintaxis
- Los archivos con errores se analizan igual y se cuenta cuántos errores tienen.
- La recuperación de errores de tree-sitter puede "tragarse" el código que sigue a un
  paréntesis o llave sin cerrar; esas funciones pueden no aparecer.

## Escaneo
- Las reglas de `.gitignore` de subcarpetas se aplican, pero una negación (`!archivo`)
  en un `.gitignore` no deshace una regla de otro `.gitignore` distinto.
- La detección de minificados (línea promedio > 200 o alguna línea > 2000 caracteres)
  no se aplica a archivos `.sql` (los volcados de datos suelen tener líneas largas).
