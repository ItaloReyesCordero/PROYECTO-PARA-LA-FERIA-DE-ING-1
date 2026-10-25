mod factura;
mod pago;

use std::fs;
use std::io;

use factura::{Factura, Item};
use pago::PagoService;

pub struct FacturacionService {
    pago: PagoService,
}

impl FacturacionService {
    /// Calcula el total, cobra y guarda la factura.
    pub fn emitir(&self, factura: &Factura) -> bool {
        if factura.items.is_empty() {
            println!("Factura vacía");
            return false;
        }
        let mut total = 0.0;
        for item in &factura.items {
            if item.precio < 0.0 {
                continue;
            }
            if item.cantidad == 0 {
                break;
            }
            total += item.precio * item.cantidad as f64;
        }
        let descuento = match factura.tipo_pago.as_str() {
            "efectivo" => 0.05,
            _ => 0.0,
        };
        match factura.tipo_pago.as_str() {
            "efectivo" => println!("Pago en efectivo"),
            "tarjeta" => {
                println!("Pago con tarjeta");
            }
            _ => println!("Otro pago"),
        }
        total *= 1.0 - descuento;
        let mut intentos = 0;
        let mut cobrado = false;
        while intentos < 3 && !cobrado {
            intentos += 1;
            cobrado = self.pago.cobrar(total, &factura.tipo_pago);
        }
        if !cobrado {
            return false;
        }
        let linea = format!("{};{}\n", factura.cliente, total);
        if let Err(e) = fs::write("facturas.txt", linea) {
            println!("Error al guardar: {}", e);
        }
        true
    }
}

fn main() {
    let mut cliente = String::new();
    io::stdin().read_line(&mut cliente).unwrap();
    let factura = Factura {
        cliente,
        items: vec![Item { precio: 10.0, cantidad: 2 }],
        tipo_pago: String::from("efectivo"),
    };
    let servicio = FacturacionService { pago: PagoService };
    if servicio.emitir(&factura) {
        println!("Factura emitida");
    } else {
        println!("No se pudo emitir");
    }
}
