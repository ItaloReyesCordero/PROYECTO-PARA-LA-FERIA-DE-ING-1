package main

// Item es una línea de la factura.
type Item struct {
	Precio   float64
	Cantidad int
}

// Factura con ítems y un tipo de pago.
type Factura struct {
	Cliente  string
	Items    []Item
	TipoPago string
}

// AgregarItem añade un ítem a la factura.
func (f *Factura) AgregarItem(item Item) {
	f.Items = append(f.Items, item)
}
