<?php

require __DIR__ . '/src/Factura.php';
require __DIR__ . '/src/PagoService.php';
require __DIR__ . '/src/FacturacionService.php';

use App\Factura;
use App\FacturacionService;
use App\PagoService;

function main(): void
{
    $cliente = trim(fgets(STDIN));
    $factura = new Factura($cliente, [['precio' => 10, 'cantidad' => 2]], 'efectivo');
    $servicio = new FacturacionService(new PagoService());
    if ($servicio->emitir($factura)) {
        echo "Factura emitida\n";
    } else {
        echo "No se pudo emitir\n";
    }
}

main();
