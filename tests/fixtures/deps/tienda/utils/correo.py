"""Utilidades: avisa por correo (y, mal hecho, vuelve a validar con el servicio)."""

from tienda.services.pedido_service import PedidoService


def avisar(pedido):
    if PedidoService().es_valido(pedido):
        print("Pedido registrado")
