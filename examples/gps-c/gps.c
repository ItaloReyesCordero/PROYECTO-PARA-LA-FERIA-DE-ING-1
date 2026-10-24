/*
 * Lectura de tramas NMEA de un GPS por puerto serie.
 * Ejemplo para Desglosa: reproduce la lógica de un diagrama de flujo clásico
 * hecho a mano (espera del '$', copia al buffer y desglose de cada trama).
 */
#include <stdio.h>
#include <string.h>

#define TAM_BUFFER 512
#define MAX_ESPERA 1000
#define NUM_TRAMAS 6

char Buffer[TAM_BUFFER];

/* Abre el puerto serie (en el equipo real configura el UART a 4800 baudios). */
int abrir_puerto(const char *nombre)
{
    printf("Abriendo %s a 4800 baudios\n", nombre);
    return 1;
}

/* Lee un carácter del puerto serie. */
char leer_caracter(void)
{
    int c = getchar();
    if (c == EOF) {
        return '\0';
    }
    return (char)c;
}

/* Cierra la comunicación con el GPS. */
void cerrar_puerto(void)
{
    printf("Comunicacion cerrada\n");
}

/* Muestra los campos separados por comas de una trama. */
void imprimir_campos(const char *nombre, int inicio)
{
    int campo = 0;
    int p = inicio;
    printf("%s:", nombre);
    while (p < TAM_BUFFER && Buffer[p] != '*' && Buffer[p] != '\n') {
        if (Buffer[p] == ',') {
            campo++;
            printf(" | ");
        } else {
            putchar(Buffer[p]);
        }
        p++;
    }
    printf("  (%d campos)\n", campo);
}

/* GPRMC: hora, estado, latitud, longitud, velocidad y fecha. */
void DesglosaGPRMC(int inicio)
{
    int p = inicio + 6;
    if (Buffer[p + 7] == 'V') {
        printf("GPRMC: datos no validos todavia\n");
        return;
    }
    imprimir_campos("GPRMC", inicio);
}

/* GPGGA: posición, calidad del fix y número de satélites. */
void DesglosaGPGGA(int inicio)
{
    imprimir_campos("GPGGA", inicio);
}

/* GPGSA: satélites activos y precisión (DOP). */
void DesglosaGPGSA(int inicio)
{
    imprimir_campos("GPGSA", inicio);
}

/* PGRME: error estimado de posición (propietaria Garmin). */
void DesglosaPGRME(int inicio)
{
    imprimir_campos("PGRME", inicio);
}

/* PGRMV: velocidad en 3D (propietaria Garmin). */
void DesglosaPGRMV(int inicio)
{
    imprimir_campos("PGRMV", inicio);
}

/* GPVTG: rumbo y velocidad sobre el suelo. */
void DesglosaGPVTG(int inicio)
{
    imprimir_campos("GPVTG", inicio);
}

/* Programa principal: lee el GPS y desglosa sus tramas NMEA. */
int main(void)
{
    char Dato;
    int i = 0;
    int j = 1;
    int k = 0;
    int cont = 0;
    int cont1 = 0;

    if (!abrir_puerto("COM3")) {
        printf("No se pudo abrir el puerto\n");
        return 1;
    }

    /* 1. Esperar el inicio de una trama */
    Dato = leer_caracter();
    while (Dato != '$') {
        k++;
        if (k == MAX_ESPERA) {
            cerrar_puerto();
            return 0;
        }
        Dato = leer_caracter();
    }

    /* 2. Copiar los caracteres al buffer contando tramas */
    while (cont < NUM_TRAMAS && i < TAM_BUFFER) {
        Buffer[i] = Dato;
        if (Dato == '$') {
            cont++;
        }
        i++;
        Dato = leer_caracter();
    }

    /* 3. Buscar cada trama y desglosarla */
    while (j < TAM_BUFFER && cont1 < NUM_TRAMAS) {
        if (Buffer[j - 1] == '$' && Buffer[j] == 'G') {
            if (strncmp(&Buffer[j], "GPRMC", 5) == 0) {
                DesglosaGPRMC(j);
            } else if (strncmp(&Buffer[j], "GPGGA", 5) == 0) {
                DesglosaGPGGA(j);
            } else if (strncmp(&Buffer[j], "GPGSA", 5) == 0) {
                DesglosaGPGSA(j);
            } else if (strncmp(&Buffer[j], "GPVTG", 5) == 0) {
                DesglosaGPVTG(j);
            }
            cont1++;
        } else if (Buffer[j - 1] == '$' && Buffer[j] == 'P') {
            if (strncmp(&Buffer[j], "PGRME", 5) == 0) {
                DesglosaPGRME(j);
            } else if (strncmp(&Buffer[j], "PGRMV", 5) == 0) {
                DesglosaPGRMV(j);
            }
            cont1++;
        }
        j++;
    }

    cerrar_puerto();
    return 0;
}
