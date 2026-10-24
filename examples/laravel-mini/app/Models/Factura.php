<?php

namespace App\Models;

class Factura
{
    public function __construct(
        public int $clienteId,
        public array $items,
        public float $total,
    ) {
    }

    /** Crea una factura a partir de una fila de la base de datos. */
    public static function desdeFila(array $fila): Factura
    {
        return new Factura((int) $fila['cliente_id'], [], (float) $fila['total']);
    }
}
