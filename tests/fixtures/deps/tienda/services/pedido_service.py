"""Lógica: reglas de los pedidos."""

from tienda.repositories.pedido_repository import PedidoRepository
from tienda.utils.correo import avisar


class PedidoService:
    def __init__(self):
        self.repo = PedidoRepository()

    def crear(self, datos):
        pedido = self.repo.guardar(datos)
        avisar(pedido)
        return pedido

    def es_valido(self, pedido):
        return bool(pedido)
