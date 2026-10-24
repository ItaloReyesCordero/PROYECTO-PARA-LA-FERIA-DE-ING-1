#include <stdio.h>

int sumar_pares(int n)
{
    int total = 0;
    for (int i = 0; i < n; i++) {
        if (i % 2 != 0) {
            continue;
        }
        total += i;
    }
    return total;
}

int menu(void)
{
    int opcion;
    do {
        printf("1) sumar 2) salir\n");
        scanf("%d", &opcion);
        switch (opcion) {
        case 0:
        case 1:
            printf("%d\n", sumar_pares(10));
        case 2:
            printf("caida\n");
            break;
        default:
            if (opcion < 0) {
                goto fin;
            }
            printf("opcion invalida\n");
        }
    } while (opcion != 2);
fin:
    return opcion;
}

int buscar(int *v, int n, int x)
{
    int i = 0;
    while (1) {
        if (i >= n) {
            break;
        }
        if (v[i] == x) {
            return i;
        }
        i++;
    }
    return -1;
}
