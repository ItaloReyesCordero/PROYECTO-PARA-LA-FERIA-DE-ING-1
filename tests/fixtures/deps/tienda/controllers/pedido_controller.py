"""Entrada: recibe los pedidos."""

from tienda.repositories.pedido_repository import PedidoRepository
from tienda.services.pedido_service import PedidoService


class PedidoController:
    def __init__(self):
        self.servicio = PedidoService()
        self.repo = PedidoRepository()

    def crear(self, datos):
        return self.servicio.crear(datos)

    def listar(self):
        # Se salta el servicio: va directo al repositorio.
        return self.repo.todos()
