package facturacion;

import java.util.List;

/** Una factura con ítems y un tipo de pago. */
public class Factura {
    public String cliente;
    public List<double[]> items;
    public String tipoPago;

    public Factura(String cliente, List<double[]> items, String tipoPago) {
        this.cliente = cliente;
        this.items = items;
        this.tipoPago = tipoPago;
    }

    public void agregarItem(double[] item) {
        this.items.add(item);
    }
}
