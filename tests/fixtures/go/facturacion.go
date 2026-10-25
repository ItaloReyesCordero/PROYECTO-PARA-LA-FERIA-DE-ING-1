package main

import (
	"bufio"
	"fmt"
	"os"
)

// FacturacionService emite facturas.
type FacturacionService struct {
	pago *PagoService
}

// Emitir calcula el total, cobra y guarda la factura.
func (s *FacturacionService) Emitir(factura *Factura) bool {
	if len(factura.Items) == 0 {
		fmt.Println("Factura vacía")
		return false
	}
	total := 0.0
	for _, item := range factura.Items {
		if item.Precio < 0 {
			continue
		}
		if item.Cantidad == 0 {
			break
		}
		total += item.Precio * float64(item.Cantidad)
	}
	var descuento float64
	switch factura.TipoPago {
	case "efectivo":
		descuento = 0.05
	case "tarjeta":
		descuento = 0
	default:
		descuento = 0
	}
	total = total * (1 - descuento)
	intentos := 0
	cobrado := false
	for intentos < 3 && !cobrado {
		intentos++
		cobrado = s.pago.Cobrar(total, factura.TipoPago)
	}
	if !cobrado {
		return false
	}
	linea := fmt.Sprintf("%s;%.2f\n", factura.Cliente, total)
	os.WriteFile("facturas.txt", []byte(linea), 0644)
	return true
}

func main() {
	lector := bufio.NewReader(os.Stdin)
	cliente, _ := lector.ReadString('\n')
	factura := &Factura{Cliente: cliente, Items: []Item{{Precio: 10, Cantidad: 2}}, TipoPago: "efectivo"}
	servicio := &FacturacionService{pago: &PagoService{}}
	if servicio.Emitir(factura) {
		fmt.Println("Factura emitida")
	} else {
		fmt.Println("No se pudo emitir")
	}
}
