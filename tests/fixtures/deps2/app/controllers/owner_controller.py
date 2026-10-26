"""Entrada que usa el repositorio directo: aquí no hay un servicio que lo use."""

from app.repositories.owner_repository import OwnerRepository


class OwnerController:
    def __init__(self):
        self.repo = OwnerRepository()

    def ver(self, owner_id):
        return self.repo.buscar(owner_id)
