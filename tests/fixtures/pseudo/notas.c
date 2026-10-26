#include <stdio.h>

#define MAX 10

/* Promedio de n notas. */
float promedio(int notas[], int n) {
    int suma = 0;
    for (int i = 0; i < n; i++) {
        suma += notas[i];
    }
    if (n == 0) {
        return 0;
    }
    return (float)suma / n;
}

/* Letra de una nota. */
char letra(int nota) {
    switch (nota / 5) {
        case 4:
        case 3:
            return 'A';
        case 2:
            return 'B';
        default:
            return 'C';
    }
}

int main(void) {
    int notas[MAX];
    int n, opcion;
    char nombre[30];
    printf("Nombre: ");
    scanf("%s", nombre);
    do {
        printf("Cantidad de notas (1-%d): ", MAX);
        scanf("%d", &n);
    } while (n < 1 || n > MAX);
    for (int i = n - 1; i >= 0; i--) {
        scanf("%d", &notas[i]);
        if (notas[i] < 0) {
            break;
        }
    }
    float p = promedio(notas, n);
    printf("%s tiene promedio %.2f\n", nombre, p);
    opcion = 0;
    while (!opcion) {
        printf("Letra: %c\n", letra((int)p));
        opcion = 1;
    }
    return 0;
}
