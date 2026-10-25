class PagoService
  # Cobra el monto con el tipo de pago indicado.
  def cobrar(monto, tipo)
    raise ArgumentError, "monto inválido" if monto <= 0

    puts "Cobrando #{monto} con #{tipo}"
    true
  end
end
