pub struct PagoService;

impl PagoService {
    /// Cobra el monto con el tipo de pago indicado.
    pub fn cobrar(&self, monto: f64, tipo: &str) -> bool {
        if monto <= 0.0 {
            return false;
        }
        println!("Cobrando {} con {}", monto, tipo);
        true
    }
}
