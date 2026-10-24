<?php

namespace App;

class PagoService
{
    /** Cobra el monto con el tipo de pago indicado. */
    public function cobrar(float $monto, string $tipo): bool
    {
        if ($monto <= 0) {
            throw new \InvalidArgumentException("monto inválido");
        }
        echo "Cobrando {$monto} con {$tipo}\n";
        return true;
    }
}
