---
name: desglosa
description: Analiza la estructura de un proyecto de código con Desglosa (análisis estático, sin IA y sin internet). Úsala para saber qué hace una función o clase, quién la llama y a quién llama, cómo se llega de una función a otra o dónde está implementada una idea ("¿dónde se calcula el total?"), y cuando el usuario pida un mapa o un diagrama de flujo, de secuencia o entidad-relación de su proyecto.
---

# Desglosa: entender un proyecto sin leerlo entero

Desglosa lee el código con tree-sitter y responde preguntas sobre su estructura.
**Nunca ejecuta el código analizado** y solo usa internet en `desglosa setup`.

Lenguajes: Python, JavaScript, TypeScript, PHP, Java, C, C++, C#, Go, Ruby, Rust,
Kotlin, Swift y SQL.

## Preparación (una sola vez)

1. Ejecuta `desglosa --version`. Si el comando no existe, pide permiso al usuario
   e instálalo con:
   `uv tool install git+https://github.com/ItaloReyesCordero/PROYECTO-PARA-LA-FERIA-DE-ING-1`
2. Si un comando termina con código **2**, faltan las gramáticas: pide permiso y
   ejecuta `desglosa setup` (es el único paso que usa internet).

## Qué comando usar

`RUTA` es la carpeta del proyecto (normalmente `.`). Añade siempre `--json`: el
resultado sale por la salida estándar y los avisos por la de errores.

| Necesitas saber…                             | Comando                                                    |
|----------------------------------------------|------------------------------------------------------------|
| Qué hace `X`, quién la llama y a quién llama | `desglosa explain RUTA X --json`                           |
| Cómo se llega de `A` a `B`                   | `desglosa path RUTA A B --json`                            |
| Dónde se hace algo descrito con palabras     | `desglosa buscar RUTA "calcular total" --json`             |
| Un diagrama para mostrar en tu respuesta     | `desglosa mermaid RUTA X` (o `--secuencia`)                |
| Un HTML interactivo para el usuario          | `desglosa analyze RUTA -o desglosa.html`                   |
| Un resumen en Markdown                       | `desglosa analyze RUTA -o desglosa.html --report reporte.md` |

`X`, `A` y `B` pueden ser `funcion`, `Clase.metodo` o `archivo:Clase.metodo`
(por ejemplo `app/Services/Pago.php:Pago.cobrar`).

Flujo recomendado para una pregunta abierta:

1. `buscar` para encontrar las funciones candidatas.
2. `explain` de la mejor candidata.
3. `path` si hay que conectar dos puntos.
4. Abre solo los archivos y líneas que indica el campo `at` para confirmar detalles.
5. Si un diagrama ayuda a explicar, pega la salida de `desglosa mermaid` en un bloque
   ```` ```mermaid ````: es el diagrama de flujo (o de secuencia) de la función, con los
   símbolos clásicos.

## Códigos de salida

- **0**: bien.
- **1**: error de uso (ruta que no existe, argumento inválido).
- **2**: faltan gramáticas → `desglosa setup`.
- **3**: el nombre corresponde a varios símbolos. Los candidatos salen por la
  salida de errores como `archivo:Clase.metodo`; repite con uno de ellos.
- **4**: no se encontró el símbolo, el camino o ningún resultado. Si falló
  `explain`, prueba con `buscar`. Si falló `path`, el aviso dice si el camino
  existe al revés.

## Cómo leer la salida

- `explain`: `calls` (en el orden del código) y `called_by`, cada uno con
  `qualname`, `file`, `line`, `at` (archivo:línea de la llamada) y `confidence`.
  Además `signature`, `doc`, `complexity`, `external` (llamadas a librerías) y
  `ambiguous` (llamadas con más de 4 destinos posibles, que no se resuelven); cuando
  existen, también `route` (ruta web), `tables` (tablas SQL
  que usa), `notes` (TODO, FIXME…), `members` y `bases` (en clases).
- `path`: lista de pasos `{from, to, at, confidence}`.
- `buscar`: lista ordenada por `score`; `why` explica por qué coincide.

Significado de `confidence`:

- `exacta`: el destino es seguro (misma clase, import explícito…).
- `probable`: deducido por tipo o por nombre (por ejemplo, una interfaz con una
  sola implementación). Preséntalo como probable, no como seguro.
- `ambigua`: hay varios candidatos; no elijas uno sin leer el código.

## Límites que debes decir cuando apliquen

- Es análisis estático: las llamadas dinámicas (reflexión, `getattr`, callbacks
  por nombre, inyección de dependencias por configuración, eventos) pueden no
  aparecer. Si `called_by` está vacío, di "Desglosa no encontró quién la llama",
  no "nadie la llama".
- En proyectos de cientos de miles de líneas la primera consulta tarda decenas de
  segundos; las siguientes son más rápidas porque reutilizan la caché.
