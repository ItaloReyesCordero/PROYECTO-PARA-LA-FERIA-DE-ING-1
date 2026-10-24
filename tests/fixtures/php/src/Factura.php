<?php

namespace App;

/** Una factura con ítems y un tipo de pago. */
class Factura
{
    public function __construct(
        public string $cliente,
        public array $items,
        public string $tipoPago,
    ) {
    }

    public function agregarItem(array $item): void
    {
        $this->items[] = $item;
    }
}
