"""Servicio de facturación."""

from factura import Factura
from pagos import PagoService


class FacturacionService:
    def __init__(self, pago: PagoService):
        self.pago = pago

    def emitir(self, factura: Factura):
        """Calcula el total, cobra y guarda la factura."""
        if not factura.items:
            print("Factura vacía")
            return False
        total = 0
        for item in factura.items:
            if item["precio"] < 0:
                continue
            if item["cantidad"] == 0:
                break
            total += item["precio"] * item["cantidad"]
        match factura.tipo_pago:
            case "efectivo":
                descuento = 0.05
            case "tarjeta":
                descuento = 0
            case _:
                descuento = 0
        total = total * (1 - descuento)
        intentos = 0
        cobrado = False
        while intentos < 3 and not cobrado:
            intentos += 1
            try:
                cobrado = self.pago.cobrar(total, factura.tipo_pago)
            except ValueError as error:
                print("Error al cobrar:", error)
        if not cobrado:
            return False
        with open("facturas.txt", "a", encoding="utf-8") as archivo:
            archivo.write(f"{factura.cliente};{total}\n")
        return True


def main():
    cliente = input("Cliente: ")
    factura = Factura(cliente, [{"precio": 10, "cantidad": 2}], "efectivo")
    servicio = FacturacionService(PagoService())
    if servicio.emitir(factura):
        print("Factura emitida")
    else:
        print("No se pudo emitir")


if __name__ == "__main__":
    main()
