package facturacion

interface MedioPago {
    fun cobrar(monto: Double, tipo: String): Boolean
}

class PagoService : MedioPago {
    /** Cobra el monto con el tipo de pago indicado. */
    override fun cobrar(monto: Double, tipo: String): Boolean {
        if (monto <= 0) {
            throw IllegalArgumentException("monto inválido")
        }
        println("Cobrando $monto con $tipo")
        return true
    }
}
