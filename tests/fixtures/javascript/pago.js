export class PagoService {
  /** Cobra el monto con el tipo de pago indicado. */
  cobrar(monto, tipo) {
    if (monto <= 0) {
      throw new Error("monto inválido");
    }
    console.log(`Cobrando ${monto} con ${tipo}`);
    return true;
  }
}
