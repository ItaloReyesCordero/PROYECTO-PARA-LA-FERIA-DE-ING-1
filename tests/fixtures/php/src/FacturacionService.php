<?php

namespace App;

class FacturacionService
{
    public function __construct(private PagoService $pago)
    {
    }

    /** Calcula el total, cobra y guarda la factura. */
    public function emitir(Factura $factura): bool
    {
        if (count($factura->items) === 0) {
            echo "Factura vacía\n";
            return false;
        }
        $total = 0;
        foreach ($factura->items as $item) {
            if ($item['precio'] < 0) {
                continue;
            }
            if ($item['cantidad'] === 0) {
                break;
            }
            $total += $item['precio'] * $item['cantidad'];
        }
        switch ($factura->tipoPago) {
            case 'efectivo':
                $descuento = 0.05;
                break;
            case 'tarjeta':
                $descuento = 0;
                break;
            default:
                $descuento = 0;
        }
        $total = $total * (1 - $descuento);
        $intentos = 0;
        $cobrado = false;
        while ($intentos < 3 && !$cobrado) {
            $intentos++;
            try {
                $cobrado = $this->pago->cobrar($total, $factura->tipoPago);
            } catch (\InvalidArgumentException $e) {
                echo "Error al cobrar: " . $e->getMessage() . "\n";
            }
        }
        if (!$cobrado) {
            return false;
        }
        file_put_contents('facturas.txt', "{$factura->cliente};{$total}\n", FILE_APPEND);
        return true;
    }
}
