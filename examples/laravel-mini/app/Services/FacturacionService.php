<?php

namespace App\Services;

use App\Models\Factura;
use App\Repositories\FacturaRepository;

class FacturacionService
{
    public function __construct(
        private FacturaRepository $repositorio,
        private CalculadoraImpuestos $impuestos,
    ) {
    }

    /** Calcula el total con impuestos, valida y guarda la factura. */
    public function emitir(string $cliente, array $items, string $tipoPago): Factura
    {
        if (count($items) === 0) {
            throw new \DomainException('La factura no tiene ítems');
        }
        $subtotal = 0;
        foreach ($items as $item) {
            if ($item['cantidad'] <= 0) {
                continue;
            }
            $subtotal += $item['precio'] * $item['cantidad'];
        }
        $total = $this->impuestos->aplicar($subtotal, $tipoPago);
        $factura = new Factura($cliente, $items, $total);
        $this->repositorio->guardar($factura);
        return $factura;
    }

    /** Facturas de un cliente. */
    public function listar(string $cliente): array
    {
        return $this->repositorio->porCliente($cliente);
    }

    /** Busca una factura por su número. */
    public function buscar(int $id): ?Factura
    {
        return $this->repositorio->buscar($id);
    }
}
