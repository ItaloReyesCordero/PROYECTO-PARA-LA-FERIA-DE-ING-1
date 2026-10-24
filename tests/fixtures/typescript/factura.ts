export interface Item {
  precio: number;
  cantidad: number;
}

/** Una factura con ítems y un tipo de pago. */
export class Factura {
  constructor(
    public cliente: string,
    public items: Item[],
    public tipoPago: string,
  ) {}

  agregarItem(item: Item): void {
    this.items.push(item);
  }
}
