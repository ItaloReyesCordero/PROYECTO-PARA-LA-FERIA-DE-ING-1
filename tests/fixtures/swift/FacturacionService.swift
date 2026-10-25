import Foundation

class FacturacionService {
    let pago: PagoService

    init(pago: PagoService) {
        self.pago = pago
    }

    /// Calcula el total, cobra y guarda la factura.
    func emitir(factura: Factura) -> Bool {
        if factura.items.isEmpty {
            print("Factura vacía")
            return false
        }
        var total = 0.0
        for item in factura.items {
            if item.precio < 0 {
                continue
            }
            if item.cantidad == 0 {
                break
            }
            total += item.precio * Double(item.cantidad)
        }
        var descuento = 0.0
        switch factura.tipoPago {
        case "efectivo":
            descuento = 0.05
        case "tarjeta":
            descuento = 0
        default:
            descuento = 0
        }
        total = total * (1 - descuento)
        var intentos = 0
        var cobrado = false
        while intentos < 3 && !cobrado {
            intentos += 1
            do {
                cobrado = try pago.cobrar(monto: total, tipo: factura.tipoPago)
            } catch {
                print("Error al cobrar: \(error)")
            }
        }
        if !cobrado {
            return false
        }
        let linea = "\(factura.cliente);\(total)\n"
        try? linea.write(toFile: "facturas.txt", atomically: true, encoding: .utf8)
        return true
    }
}

func main() {
    let cliente = readLine() ?? ""
    let factura = Factura(cliente: cliente, items: [Item(precio: 10, cantidad: 2)], tipoPago: "efectivo")
    let servicio = FacturacionService(pago: PagoService())
    if servicio.emitir(factura: factura) {
        print("Factura emitida")
    } else {
        print("No se pudo emitir")
    }
}

main()
