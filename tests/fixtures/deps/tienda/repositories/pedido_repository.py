"""Datos: guarda los pedidos."""


class PedidoRepository:
    def guardar(self, datos):
        return dict(datos)

    def todos(self):
        return []
