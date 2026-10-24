<?php

namespace App\Services;

class CalculadoraImpuestos
{
    private const IGV = 0.18;

    /** Aplica el descuento por tipo de pago y el IGV. */
    public function aplicar(float $subtotal, string $tipoPago): float
    {
        switch ($tipoPago) {
            case 'efectivo':
                $descuento = 0.05;
                break;
            case 'tarjeta':
                $descuento = 0.0;
                break;
            default:
                throw new \DomainException("Tipo de pago no válido: {$tipoPago}");
        }
        $base = $subtotal * (1 - $descuento);
        return round($base * (1 + self::IGV), 2);
    }
}
