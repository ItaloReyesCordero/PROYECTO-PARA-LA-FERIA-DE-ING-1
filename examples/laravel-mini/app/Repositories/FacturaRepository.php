<?php

namespace App\Repositories;

use App\Models\Factura;

interface FacturaRepository
{
    public function guardar(Factura $factura): void;

    public function porCliente(string $cliente): array;

    public function buscar(int $id): ?Factura;
}
