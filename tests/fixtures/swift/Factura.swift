struct Item {
    let precio: Double
    let cantidad: Int
}

/// Una factura con ítems y un tipo de pago.
class Factura {
    let cliente: String
    var items: [Item]
    let tipoPago: String

    init(cliente: String, items: [Item], tipoPago: String) {
        self.cliente = cliente
        self.items = items
        self.tipoPago = tipoPago
    }

    func agregarItem(_ item: Item) {
        items.append(item)
    }
}
