package main

import "fmt"

// PagoService cobra las facturas.
type PagoService struct{}

// Cobrar cobra el monto con el tipo de pago indicado.
func (p *PagoService) Cobrar(monto float64, tipo string) bool {
	if monto <= 0 {
		return false
	}
	fmt.Printf("Cobrando %.2f con %s\n", monto, tipo)
	return true
}
