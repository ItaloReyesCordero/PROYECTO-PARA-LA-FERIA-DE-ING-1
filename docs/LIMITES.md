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

## Errores de sintaxis
- Los archivos con errores se analizan igual y se cuenta cuántos errores tienen.
- La recuperación de errores de tree-sitter puede "tragarse" el código que sigue a un
  paréntesis o llave sin cerrar; esas funciones pueden no aparecer.

## Escaneo
- Las reglas de `.gitignore` de subcarpetas se aplican, pero una negación (`!archivo`)
  en un `.gitignore` no deshace una regla de otro `.gitignore` distinto.
- La detección de minificados (línea promedio > 200 o alguna línea > 2000 caracteres)
  no se aplica a archivos `.sql` (los volcados de datos suelen tener líneas largas).
