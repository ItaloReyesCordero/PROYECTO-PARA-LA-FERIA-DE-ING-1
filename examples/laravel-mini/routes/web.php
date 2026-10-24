<?php

use App\Http\Controllers\FacturaController;
use Illuminate\Support\Facades\Route;

Route::get('/facturas', [FacturaController::class, 'index']);
Route::post('/facturas', [FacturaController::class, 'store']);
Route::get('/facturas/{id}', [FacturaController::class, 'show']);
