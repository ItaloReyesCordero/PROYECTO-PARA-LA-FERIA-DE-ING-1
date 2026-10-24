<?php

namespace App\Http\Controllers;

use App\Services\FacturacionService;
use Illuminate\Http\Request;

class FacturaController extends Controller
{
    public function __construct(private FacturacionService $servicio)
    {
    }

    /** Lista las facturas de un cliente. */
    public function index(Request $request)
    {
        $cliente = $request->input('cliente');
        if ($cliente === null) {
            return response()->json(['error' => 'Falta el cliente'], 422);
        }
        return response()->json($this->servicio->listar($cliente));
    }

    /** Registra una factura nueva. */
    public function store(Request $request)
    {
        $datos = $request->validate([
            'cliente' => 'required|string',
            'items' => 'required|array',
            'tipo_pago' => 'required|in:efectivo,tarjeta',
        ]);
        try {
            $factura = $this->servicio->emitir($datos['cliente'], $datos['items'], $datos['tipo_pago']);
        } catch (\DomainException $e) {
            return response()->json(['error' => $e->getMessage()], 400);
        }
        return response()->json($factura, 201);
    }

    /** Muestra una factura por su número. */
    public function show(int $id)
    {
        $factura = $this->servicio->buscar($id);
        if ($factura === null) {
            abort(404);
        }
        return response()->json($factura);
    }
}
