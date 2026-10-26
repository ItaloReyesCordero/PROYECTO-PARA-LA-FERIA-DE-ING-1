package figuras

/** Algo que se puede dibujar. */
interface Dibujable {
    fun dibujar()
}

/** Una figura con nombre. */
abstract class Figura(protected val nombre: String) {
    abstract fun area(): Double

    companion object {
        private var contador = 0
        fun total(): Int = contador
    }
}

class Circulo(nombre: String, private val radio: Double) : Figura(nombre), Dibujable {
    val centro: Punto = Punto()

    override fun area(): Double {
        return Math.PI * radio * radio
    }

    override fun dibujar() {
        println("Circulo $nombre")
    }

    private fun esValido(): Boolean {
        return radio > 0
    }
}

class Punto {
    var x: Int = 0
    var y: Int = 0
}
