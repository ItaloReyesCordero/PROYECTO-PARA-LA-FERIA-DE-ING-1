/** Una factura con ítems y un tipo de pago. */
export class Factura {
  constructor(cliente, items, tipoPago) {
    this.cliente = cliente;
    this.items = items;
    this.tipoPago = tipoPago;
  }

  agregarItem(item) {
    this.items.push(item);
  }
}
