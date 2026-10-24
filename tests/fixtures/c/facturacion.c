#include <stdio.h>
#include "pago.h"

#define EFECTIVO 1
#define TARJETA 2

struct Factura {
    char cliente[64];
    double precios[10];
    int cantidades[10];
    int num_items;
    int tipo_pago;
};

/* Calcula el total, cobra y guarda la factura. */
int emitir(struct Factura *factura)
{
    if (factura->num_items == 0) {
        printf("Factura vacia\n");
        return 0;
    }
    double total = 0;
    for (int i = 0; i < factura->num_items; i++) {
        if (factura->precios[i] < 0) {
            continue;
        }
        if (factura->cantidades[i] == 0) {
            break;
        }
        total += factura->precios[i] * factura->cantidades[i];
    }
    double descuento;
    switch (factura->tipo_pago) {
    case EFECTIVO:
        descuento = 0.05;
        break;
    case TARJETA:
        descuento = 0;
        break;
    default:
        descuento = 0;
    }
    total = total * (1 - descuento);
    int intentos = 0;
    int cobrado = 0;
    while (intentos < 3 && !cobrado) {
        intentos++;
        cobrado = cobrar(total, factura->tipo_pago);
    }
    if (!cobrado) {
        return 0;
    }
    FILE *archivo = fopen("facturas.txt", "a");
    fprintf(archivo, "%s;%.2f\n", factura->cliente, total);
    fclose(archivo);
    return 1;
}

int main(void)
{
    struct Factura factura = {"", {10}, {2}, 1, EFECTIVO};
    scanf("%63s", factura.cliente);
    if (emitir(&factura)) {
        printf("Factura emitida\n");
    } else {
        printf("No se pudo emitir\n");
    }
    return 0;
}
