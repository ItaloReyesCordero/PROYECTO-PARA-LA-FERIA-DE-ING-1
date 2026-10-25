# Reporte de Desglosa: laravel-mini

Generado por Desglosa 0.1.0 con análisis estático: el código no se ejecutó.

## Resumen

- Archivos analizados: 9 (261 líneas)
- Funciones y métodos: 18 · clases: 6 · interfaces: 1
- Llamadas: 46 (exacta 4, probable 7, ambigua 0, externa 35)
- Puntos de entrada: `FacturaController.index`, `FacturaController.store`, `FacturaController.show`
- Rutas: 3
- Tablas SQL: 4 (3 relaciones)

## Archivos por lenguaje

| Lenguaje | Archivos | Líneas | Funciones |
|---|---|---|---|
| php | 8 | 229 | 18 |
| sql | 1 | 32 | 0 |

## Funciones más llamadas

| Función | Dónde | Llamadas | Desde (funciones) |
|---|---|---|---|
| `Factura.__construct` | `app/Models/Factura.php:7` | 2 | 2 |
| `Factura.desdeFila` | `app/Models/Factura.php:15` | 2 | 2 |
| `MySqlFacturaRepository.guardar` | `app/Repositories/MySqlFacturaRepository.php:16` | 1 | 1 |
| `MySqlFacturaRepository.porCliente` | `app/Repositories/MySqlFacturaRepository.php:37` | 1 | 1 |
| `MySqlFacturaRepository.buscar` | `app/Repositories/MySqlFacturaRepository.php:51` | 1 | 1 |
| `CalculadoraImpuestos.aplicar` | `app/Services/CalculadoraImpuestos.php:10` | 1 | 1 |
| `FacturacionService.emitir` | `app/Services/FacturacionService.php:17` | 1 | 1 |
| `FacturacionService.listar` | `app/Services/FacturacionService.php:36` | 1 | 1 |
| `FacturacionService.buscar` | `app/Services/FacturacionService.php:42` | 1 | 1 |

## Funciones nunca llamadas

Todas las funciones tienen al menos una llamada.

## Ciclos de llamadas

No se encontraron ciclos.

## Archivos no parseados

Todos se leyeron sin errores.

## Complejidad más alta

Complejidad ciclomática = decisiones + 1. Más de 10 suele indicar una función difícil de probar.

| Función | Dónde | Complejidad | Líneas |
|---|---|---|---|
| `FacturacionService.emitir` | `app/Services/FacturacionService.php:17` | 4 | 17 |
| `CalculadoraImpuestos.aplicar` | `app/Services/CalculadoraImpuestos.php:10` | 3 | 15 |
| `FacturaController.index` | `app/Http/Controllers/FacturaController.php:15` | 2 | 8 |
| `FacturaController.show` | `app/Http/Controllers/FacturaController.php:41` | 2 | 8 |
| `MySqlFacturaRepository.guardar` | `app/Repositories/MySqlFacturaRepository.php:16` | 2 | 19 |
| `MySqlFacturaRepository.porCliente` | `app/Repositories/MySqlFacturaRepository.php:37` | 2 | 12 |
| `MySqlFacturaRepository.buscar` | `app/Repositories/MySqlFacturaRepository.php:51` | 2 | 10 |
| `FacturaController.__construct` | `app/Http/Controllers/FacturaController.php:10` | 1 | 3 |
| `FacturaController.store` | `app/Http/Controllers/FacturaController.php:25` | 1 | 14 |
| `Factura.__construct` | `app/Models/Factura.php:7` | 1 | 6 |

## Subsistemas

Grupos de archivos que se llaman mucho entre sí (algoritmo de Louvain, sin IA); el nombre sale de sus carpetas.

| Subsistema | Archivos |
|---|---|
| app/Services | 3 |
| grupos pequeños | 2 |
| sin conexiones | 2 |

## Archivos centrales

Los archivos con más llamadas hacia y desde otros archivos: por ahí pasa todo.

| Archivo | Llamadas con otros archivos | Subsistema |
|---|---|---|
| `app/Services/FacturacionService.php` | 8 | app/Services |
| `app/Repositories/MySqlFacturaRepository.php` | 5 | grupos pequeños |
| `app/Http/Controllers/FacturaController.php` | 3 | app/Services |
| `app/Models/Factura.php` | 3 | grupos pequeños |
| `app/Services/CalculadoraImpuestos.php` | 1 | app/Services |

## Conexiones entre subsistemas

Dónde una parte del proyecto depende de otra (las más fuertes).

| Subsistema | Subsistema | Llamadas |
|---|---|---|
| app/Services | grupos pequeños | 4 |

## Arquitectura

Capas reconocidas por convenciones de nombre y carpeta (`…Controller`, `services/`, `models/`): es una convención, no una certeza.

| Capa | Componentes |
|---|---|
| Entrada | FacturaController |
| Lógica | CalculadoraImpuestos, FacturacionService |
| Datos | Factura, FacturaRepository, MySqlFacturaRepository |

Bases de datos y servicios externos (por sus imports):

| Servicio | Archivos que lo importan |
|---|---|
| Base de datos SQL | `app/Repositories/MySqlFacturaRepository.php` |

## Notas en el código

No hay comentarios TODO, FIXME, HACK, XXX, BUG, NOTE ni WHY.

## Tablas SQL

| Tabla | Columnas | Leída por (probable) | Escrita por (probable) |
|---|---|---|---|
| `clientes` | 3 | MySqlFacturaRepository.porCliente | – |
| `factura_items` | 4 | – | MySqlFacturaRepository.guardar |
| `facturas` | 4 | MySqlFacturaRepository.buscar, MySqlFacturaRepository.porCliente | MySqlFacturaRepository.guardar |
| `productos` | 3 | – | – |
