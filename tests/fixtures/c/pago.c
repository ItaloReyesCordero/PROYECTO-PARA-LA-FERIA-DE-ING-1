#include <stdio.h>
#include "pago.h"

/* Cobra el monto con el tipo de pago indicado. */
int cobrar(double monto, int tipo)
{
    if (monto <= 0) {
        return 0;
    }
    printf("Cobrando %.2f con tipo %d\n", monto, tipo);
    return 1;
}
