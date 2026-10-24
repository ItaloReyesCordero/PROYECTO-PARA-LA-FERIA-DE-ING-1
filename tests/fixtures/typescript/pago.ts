export interface MedioPago {
  cobrar(monto: number, tipo: string): boolean;
}

export class PagoService implements MedioPago {
  /** Cobra el monto con el tipo de pago indicado. */
  cobrar(monto: number, tipo: string): boolean {
    if (monto <= 0) {
      throw new Error("monto inválido");
    }
    console.log(`Cobrando ${monto} con ${tipo}`);
    return true;
  }
}
