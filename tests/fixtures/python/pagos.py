"""Servicio de pagos."""


class PagoService:
    def cobrar(self, monto, tipo):
        """Cobra el monto con el tipo de pago indicado."""
        if monto <= 0:
            raise ValueError("monto inválido")
        print(f"Cobrando {monto} con {tipo}")
        return True
