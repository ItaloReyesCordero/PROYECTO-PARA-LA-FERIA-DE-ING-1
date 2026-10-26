package figuras

import "math"

// Dibujable es algo que se puede dibujar.
type Dibujable interface {
	Dibujar()
}

// Punto es una posición.
type Punto struct {
	X int
	Y int
}

// Circulo es una figura redonda.
type Circulo struct {
	Nombre string
	radio  float64
	Centro Punto
}

func (c *Circulo) Area() float64 {
	return math.Pi * c.radio * c.radio
}

func (c *Circulo) Dibujar() {
	println("Circulo", c.Nombre)
}

func (c *Circulo) esValido() bool {
	return c.radio > 0
}
