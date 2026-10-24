"""Modelo de factura."""


class Factura:
    """Una factura con ítems y un tipo de pago."""

    def __init__(self, cliente, items, tipo_pago):
        self.cliente = cliente
        self.items = items
        self.tipo_pago = tipo_pago

    def agregar_item(self, item):
        self.items.append(item)
