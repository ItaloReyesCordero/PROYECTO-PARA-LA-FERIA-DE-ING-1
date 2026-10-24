package facturacion;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Scanner;

public class FacturacionService {
    private final MedioPago pago;

    public FacturacionService(MedioPago pago) {
        this.pago = pago;
    }

    /** Calcula el total, cobra y guarda la factura. */
    public boolean emitir(Factura factura) throws IOException {
        if (factura.items.isEmpty()) {
            System.out.println("Factura vacía");
            return false;
        }
        double total = 0;
        for (double[] item : factura.items) {
            if (item[0] < 0) {
                continue;
            }
            if (item[1] == 0) {
                break;
            }
            total += item[0] * item[1];
        }
        double descuento;
        switch (factura.tipoPago) {
            case "efectivo":
                descuento = 0.05;
                break;
            case "tarjeta":
                descuento = 0;
                break;
            default:
                descuento = 0;
        }
        total = total * (1 - descuento);
        int intentos = 0;
        boolean cobrado = false;
        while (intentos < 3 && !cobrado) {
            intentos++;
            try {
                cobrado = pago.cobrar(total, factura.tipoPago);
            } catch (IllegalArgumentException e) {
                System.out.println("Error al cobrar: " + e.getMessage());
            }
        }
        if (!cobrado) {
            return false;
        }
        Files.writeString(Path.of("facturas.txt"), factura.cliente + ";" + total + "\n",
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        return true;
    }

    public static void main(String[] args) throws IOException {
        Scanner sc = new Scanner(System.in);
        String cliente = sc.nextLine();
        Factura factura = new Factura(cliente, List.of(new double[] {10, 2}), "efectivo");
        FacturacionService servicio = new FacturacionService(new PagoService());
        if (servicio.emitir(factura)) {
            System.out.println("Factura emitida");
        } else {
            System.out.println("No se pudo emitir");
        }
    }
}
