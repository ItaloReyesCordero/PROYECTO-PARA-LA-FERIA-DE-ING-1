# Diseño visual

Reglas del visor. La fuente de verdad es `src/desglosa/render/style.css`; aquí se explica
el porqué.

## Principios

1. **Un color = un significado** dentro de cada vista. El color nunca es la única pista:
   la **forma** del nodo también cambia según su tipo (accesible para daltonismo).
2. **Lo seguro se ve sólido, lo dudoso se ve punteado.** La confianza de cada relación
   tiene su propio estilo de línea.
3. **Nada se superpone.** Las coordenadas se calculan en Python y hay tests que
   comprueban que ningún nodo pisa a otro y que ninguna línea cruza un nodo ajeno.
4. **La leyenda solo muestra lo que hay** en la vista actual (calculada en Python).
5. **Contraste de texto ≥ 4,5:1** en los dos temas.

## Tokens de color

Definidos en `:root` (tema oscuro, el predeterminado) y `[data-tema="claro"]`.

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--fondo` | `#0b1120` | `#f8fafc` | fondo del lienzo |
| `--rejilla` | `#1e293b` | `#e2e8f0` | cuadrícula de 40 px |
| `--superficie` | `#0f172a` | `#ffffff` | barras, panel, máscara de etiquetas |
| `--superficie-2` | `#111c33` | `#f1f5f9` | botones, código |
| `--borde` | `#1f2a44` | `#cbd5e1` | bordes de la interfaz |
| `--texto` | `#e5e7eb` | `#0f172a` | texto principal |
| `--texto-suave` | `#94a3b8` | `#475569` | texto secundario, etiquetas |
| `--acento` | `#60a5fa` | `#2563eb` | enlaces, botón activo |
| `--foco` | `#fbbf24` | `#b45309` | foco del teclado, nodo enfocado |

### Color semántico por tipo de nodo

Relleno = el mismo color al 18 % (oscuro) o 14 % (claro); borde = color sólido.

| Tipo | Oscuro | Claro | Vista |
|---|---|---|---|
| terminal (Inicio/Fin) | `#34d399` | `#059669` | flujo |
| proceso | `#60a5fa` | `#2563eb` | flujo |
| subproceso | `#a78bfa` | `#7c3aed` | flujo |
| decisión | `#fbbf24` | `#b45309` | flujo |
| entrada/salida, teclado | `#22d3ee` | `#0891b2` | flujo |
| pantalla, documento | `#f472b6` | `#db2777` | flujo |
| excepción (aristas) | `#fb7185` | `#e11d48` | flujo |
| externo, conector | `#94a3b8` | `#64748b` | flujo, secuencia |
| módulo / carpeta | `#818cf8` | `#4f46e5` | mapa |
| clase / archivo | `#60a5fa` | `#2563eb` | mapa |
| función | `#a78bfa` | `#7c3aed` | mapa |
| punto de entrada | `#34d399` | `#059669` | mapa, secuencia |
| tabla | `#fb923c` | `#c2410c` | ER |

## Símbolos del diagrama de flujo

Norma clásica de diagramas de flujo (la que se enseña en los cursos de algoritmos):

| `kind` | Forma | Cuándo |
|---|---|---|
| `terminal` | píldora (rectángulo muy redondeado) | Inicio / Fin |
| `proceso` | rectángulo | asignaciones, operaciones |
| `subproceso` | rectángulo con doble línea a cada lado | llamada a una función del proyecto (clic: abre su flujo) |
| `decision` | rombo | `if`, condición de un bucle, `switch` |
| `es` | paralelogramo | entrada/salida genérica, lectura de archivo |
| `pantalla` | "display": punta a la izquierda, curva a la derecha | `print`, `echo`, `console.log` |
| `teclado` | trapecio con el lado superior inclinado | `input`, `scanf`, `readline` |
| `documento` | rectángulo con borde inferior ondulado | escritura de archivo |
| `conector` | círculo con número | la línea sigue en otra columna |
| `conector_pagina` | pentágono hacia abajo | la línea sigue en otra página (impresión) |
| `externo` | rectángulo gris de borde punteado | llamada que no es del proyecto |

Reglas del layout del flujo: se lee **de arriba hacia abajo**; en un `if` la rama "sí"
baja y la rama "no" va a la derecha; el retorno de un bucle usa un carril a la izquierda;
si el diagrama es muy alto se parte en columnas unidas por conectores numerados.

## Líneas según la confianza

| Confianza | Estilo | Significa |
|---|---|---|
| exacta | sólida, 1,8 px | se sabe con certeza a qué función llama |
| probable | guiones 6-4 | casi seguro (por tipo o nombre único) |
| ambigua | puntos 2-4 | hay varias candidatas |
| externa | gris fina, puntos 1-3 | fuera del proyecto (librería, sistema) |
| excepción | rojo, guiones 5-4 | camino de un `throw`/`catch` |
| retorno (secuencia) | guiones 5-4 | respuesta de una llamada |

En el mapa, una flecha agrupa muchas llamadas y toma el estilo de **la mayoría** (en
empate, la menos segura). Encima va un trazo invisible de 12 px para que sea fácil pasar
el mouse y leer el desglose ("221 exactas · 82 probables · 364 ambiguas").

## Tipografía y medidas

- Interfaz: fuente del sistema (`system-ui`, Segoe UI en Windows), 14 px.
- Diagramas y código: monoespaciada (`Cascadia Mono`, `Consolas`…), 12 px en nodos y
  11 px en etiquetas. Al ser monoespaciada, el ancho del texto se puede calcular en Python
  sin navegador: `caracteres × 0,6 × tamaño`.
- Ajuste de línea: 28 caracteres en modo fácil, 40 en modo técnico.
- Mapa: cada nodo mide el ancho de su etiqueta + 32 px (mínimo 120 px); 120 px entre
  capas (espacio para la etiqueta "N llamadas") y 26 px entre nodos de una misma capa.
- Flujo: 30 px entre bloques, 40 px entre ramas, carriles de 26 px para los bucles.
- Secuencia: filas de 36 px y columnas de al menos 140 px.

## Interacción

- Foco visible (contorno ámbar) en todo lo que se puede usar con teclado.
- Enfocar un elemento del mapa (Alt+clic o tecla `E`) resalta en ámbar lo que usa y lo que
  lo usa; el resto queda al 25 % de opacidad.
- La ayuda (`?`) es un `<dialog>` nativo: atrapa el foco y se cierra con `Esc`.
- Impresión: se ocultan barras y paneles; solo queda el diagrama sobre fondo blanco. El
  botón PDF arma páginas A4 que no cortan las cajas.
- Recorrido del flujo y trazar ruta: el paso actual lleva el borde ámbar de foco y late
  (se desactiva con `prefers-reduced-motion`); los pasos ya visitados quedan con el borde
  ámbar al 55 %. La leyenda se oculta mientras dura el recorrido para no tapar el cuadro de
  pasos.
- Minimapa: esquina inferior derecha, solo si el diagrama no entra en pantalla; el
  rectángulo ámbar es lo que se ve.

## Estilos visuales

Cada estilo redefine **todos** los tokens de color (un test lo comprueba); las formas no
cambian, así que el tipo de nodo se reconoce siempre por la forma.

| Estilo | Para qué | Fondo | Nodos |
|---|---|---|---|
| Moderno | uso diario, con tema oscuro o claro | `#0b1120` / `#f8fafc` | colores del mapa semántico |
| Clásico | imprimir, entregar en un informe, el profesor | blanco, sin rejilla | negro, sin relleno |
| Pizarra | proyectar en la feria | verde pizarra `#1d3a2f` | tonos de tiza |
| Alto contraste | baja visión, proyectores con poco brillo | negro | colores puros y trazos de 2,4 px |

En el mapa de arquitectura, los componentes usan los colores de clase, interfaz y punto
de entrada; la base de datos, el de las tablas (`--c-tabla`); los servicios externos, el
de lo externo con borde punteado. Las columnas son franjas de `--superficie-2`.
