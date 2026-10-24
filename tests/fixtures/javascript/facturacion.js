import fs from "fs";
import { Factura } from "./factura.js";
import { PagoService } from "./pago.js";

export class FacturacionService {
  constructor() {
    this.pago = new PagoService();
  }

  /** Calcula el total, cobra y guarda la factura. */
  emitir(factura) {
    if (factura.items.length === 0) {
      console.log("Factura vacía");
      return false;
    }
    let total = 0;
    for (const item of factura.items) {
      if (item.precio < 0) {
        continue;
      }
      if (item.cantidad === 0) {
        break;
      }
      total += item.precio * item.cantidad;
    }
    let descuento;
    switch (factura.tipoPago) {
      case "efectivo":
        descuento = 0.05;
        break;
      case "tarjeta":
        descuento = 0;
        break;
      default:
        descuento = 0;
    }
    total = total * (1 - descuento);
    let intentos = 0;
    let cobrado = false;
    while (intentos < 3 && !cobrado) {
      intentos++;
      try {
        cobrado = this.pago.cobrar(total, factura.tipoPago);
      } catch (error) {
        console.log("Error al cobrar:", error.message);
      }
    }
    if (!cobrado) {
      return false;
    }
    fs.appendFileSync("facturas.txt", `${factura.cliente};${total}\n`);
    return true;
  }
}

export function main() {
  const cliente = prompt("Cliente: ");
  const factura = new Factura(cliente, [{ precio: 10, cantidad: 2 }], "efectivo");
  const servicio = new FacturacionService();
  if (servicio.emitir(factura)) {
    console.log("Factura emitida");
  } else {
    console.log("No se pudo emitir");
  }
}

main();
