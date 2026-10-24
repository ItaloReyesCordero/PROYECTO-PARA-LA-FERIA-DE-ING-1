package facturacion;

interface MedioPago {
    boolean cobrar(double monto, String tipo);
}

public class PagoService implements MedioPago {
    /** Cobra el monto con el tipo de pago indicado. */
    @Override
    public boolean cobrar(double monto, String tipo) {
        if (monto <= 0) {
            throw new IllegalArgumentException("monto inválido");
        }
        System.out.println("Cobrando " + monto + " con " + tipo);
        return true;
    }
}
