package facturacion

import java.io.File

class FacturacionService(private val pago: MedioPago) {
    /** Calcula el total, cobra y guarda la factura. */
    fun emitir(factura: Factura): Boolean {
        if (factura.items.isEmpty()) {
            println("Factura vacía")
            return false
        }
        var total = 0.0
        for (item in factura.items) {
            if (item.precio < 0) {
                continue
            }
            if (item.cantidad == 0) {
                break
            }
            total += item.precio * item.cantidad
        }
        val descuento = when (factura.tipoPago) {
            "efectivo" -> 0.05
            else -> 0.0
        }
        when (factura.tipoPago) {
            "efectivo" -> println("Pago en efectivo")
            "tarjeta" -> {
                println("Pago con tarjeta")
            }
            else -> println("Otro pago")
        }
        total *= (1 - descuento)
        var intentos = 0
        var cobrado = false
        while (intentos < 3 && !cobrado) {
            intentos++
            try {
                cobrado = pago.cobrar(total, factura.tipoPago)
            } catch (e: IllegalArgumentException) {
                println("Error al cobrar: ${e.message}")
            }
        }
        if (!cobrado) {
            return false
        }
        File("facturas.txt").appendText("${factura.cliente};$total\n")
        return true
    }
}

fun main() {
    val cliente = readLine() ?: ""
    val factura = Factura(cliente, mutableListOf(Item(10.0, 2)), "efectivo")
    val servicio = FacturacionService(PagoService())
    if (servicio.emitir(factura)) {
        println("Factura emitida")
    } else {
        println("No se pudo emitir")
    }
}
