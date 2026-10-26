"""Figuras para probar el diagrama de clases."""

from abc import ABC, abstractmethod
import math


class Dibujable(ABC):
    """Algo que se puede dibujar."""

    @abstractmethod
    def dibujar(self) -> None: ...


class Figura(ABC):
    """Una figura con nombre."""

    contador: int = 0

    def __init__(self, nombre: str):
        self._nombre = nombre
        Figura.contador += 1

    @abstractmethod
    def area(self) -> float: ...

    @staticmethod
    def total() -> int:
        return Figura.contador


class Circulo(Figura, Dibujable):
    def __init__(self, nombre: str, radio: float):
        super().__init__(nombre)
        self.__radio = radio
        self.centro: "Punto" = Punto()

    def area(self) -> float:
        return math.pi * self.__radio ** 2

    def dibujar(self) -> None:
        print("Circulo", self._nombre)

    def __es_valido(self) -> bool:
        return self.__radio > 0


class Punto:
    def __init__(self):
        self.x = 0
        self.y = 0
