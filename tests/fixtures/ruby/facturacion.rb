require_relative "factura"
require_relative "pago"

class FacturacionService
  def initialize(pago = PagoService.new)
    @pago = pago
  end

  # Calcula el total, cobra y guarda la factura.
  def emitir(factura)
    if factura.items.empty?
      puts "Factura vacía"
      return false
    end
    total = 0
    factura.items.each do |item|
      next if item[:precio] < 0
      break if item[:cantidad] == 0

      total += item[:precio] * item[:cantidad]
    end
    descuento = case factura.tipo_pago
                when "efectivo" then 0.05
                else 0
                end
    case factura.tipo_pago
    when "efectivo"
      puts "Pago en efectivo"
    when "tarjeta"
      puts "Pago con tarjeta"
    else
      puts "Otro pago"
    end
    total *= (1 - descuento)
    intentos = 0
    cobrado = false
    while intentos < 3 && !cobrado
      intentos += 1
      begin
        cobrado = @pago.cobrar(total, factura.tipo_pago)
      rescue ArgumentError => e
        puts "Error al cobrar: #{e.message}"
      end
    end
    return false unless cobrado

    File.write("facturas.txt", "#{factura.cliente};#{total}\n", mode: "a")
    true
  end
end

def main
  cliente = gets.chomp
  factura = Factura.new(cliente, [{ precio: 10, cantidad: 2 }], "efectivo")
  servicio = FacturacionService.new
  if servicio.emitir(factura)
    puts "Factura emitida"
  else
    puts "No se pudo emitir"
  end
end

main if __FILE__ == $PROGRAM_NAME
