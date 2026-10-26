/// Algo que se puede dibujar.
protocol Dibujable {
    func dibujar()
}

/// Una figura con nombre.
class Figura {
    var nombre: String
    private static var contador = 0

    init(nombre: String) {
        self.nombre = nombre
        Figura.contador += 1
    }

    func area() -> Double {
        return 0
    }

    static func total() -> Int {
        return contador
    }
}

class Circulo: Figura, Dibujable {
    private var radio: Double
    let centro = Punto()

    init(nombre: String, radio: Double) {
        self.radio = radio
        super.init(nombre: nombre)
    }

    override func area() -> Double {
        return 3.14159 * radio * radio
    }

    func dibujar() {
        print("Circulo \(nombre)")
    }

    private func esValido() -> Bool {
        return radio > 0
    }
}

struct Punto {
    var x = 0
    var y = 0
}
