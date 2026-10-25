# Una factura con ítems y un tipo de pago.
class Factura
  attr_reader :cliente, :items, :tipo_pago

  def initialize(cliente, items, tipo_pago)
    @cliente = cliente
    @items = items
    @tipo_pago = tipo_pago
  end

  def agregar_item(item)
    @items << item
  end
end
