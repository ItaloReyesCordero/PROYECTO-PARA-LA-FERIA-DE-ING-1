package facturacion

data class Item(val precio: Double, val cantidad: Int)

/** Una factura con ítems y un tipo de pago. */
class Factura(val cliente: String, val items: MutableList<Item>, val tipoPago: String) {
    fun agregarItem(item: Item) {
        items.add(item)
    }
}
