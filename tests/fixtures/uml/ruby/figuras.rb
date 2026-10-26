# Una figura con nombre.
class Figura
  attr_reader :nombre
  @@contador = 0

  def initialize(nombre)
    @nombre = nombre
    @@contador += 1
  end

  def area
    0
  end

  def self.total
    @@contador
  end
end

# Una figura redonda.
class Circulo < Figura
  attr_accessor :centro

  def initialize(nombre, radio)
    super(nombre)
    @radio = radio
    @centro = Punto.new
  end

  def area
    3.14159 * @radio * @radio
  end

  private

  def es_valido
    @radio > 0
  end
end

class Punto
  attr_accessor :x, :y
end
