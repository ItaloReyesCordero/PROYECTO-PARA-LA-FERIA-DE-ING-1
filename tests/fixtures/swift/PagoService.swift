enum ErrorPago: Error {
    case montoInvalido
}

class PagoService {
    /// Cobra el monto con el tipo de pago indicado.
    func cobrar(monto: Double, tipo: String) throws -> Bool {
        guard monto > 0 else {
            throw ErrorPago.montoInvalido
        }
        print("Cobrando \(monto) con \(tipo)")
        return true
    }
}
