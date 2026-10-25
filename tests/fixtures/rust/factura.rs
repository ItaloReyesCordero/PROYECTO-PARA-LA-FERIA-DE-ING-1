/// Una línea de la factura.
pub struct Item {
    pub precio: f64,
    pub cantidad: u32,
}

/// Una factura con ítems y un tipo de pago.
pub struct Factura {
    pub cliente: String,
    pub items: Vec<Item>,
    pub tipo_pago: String,
}

impl Factura {
    pub fn agregar_item(&mut self, item: Item) {
        self.items.push(item);
    }
}
