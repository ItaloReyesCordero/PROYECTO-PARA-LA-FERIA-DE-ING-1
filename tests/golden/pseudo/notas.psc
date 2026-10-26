// notas.c, escrito por Desglosa

Funcion resultado <- promedio(notas, n)
    Definir suma Como Entero
    suma <- 0
    Para i <- 0 Hasta n - 1 Hacer
        suma <- suma + notas[i]
    FinPara
    Si n = 0 Entonces
        resultado <- 0  // y termina la función
    FinSi
    resultado <- (float)suma / n
FinFuncion

Funcion resultado <- letra(nota)
    Segun nota / 5 Hacer
        4, 3:
            resultado <- 'A'  // y termina la función
        2:
            resultado <- 'B'  // y termina la función
        De Otro Modo:
            resultado <- 'C'  // y termina la función
    FinSegun
FinFuncion

Algoritmo notas
    Definir notas Como Entero
    Dimension notas[MAX]
    Definir n, opcion Como Entero
    Definir nombre Como Caracter
    Dimension nombre[30]
    Escribir Sin Saltar "Nombre: "
    Leer nombre
    Repetir
        Escribir Sin Saltar "Cantidad de notas (1-", MAX, "): "
        Leer n
    Hasta Que NO (n < 1 O n > MAX)
    Para i <- n - 1 Hasta 0 Con Paso -1 Hacer
        Leer notas[i]
        Si notas[i] < 0 Entonces
            // sale del bucle (break)
        FinSi
    FinPara
    Definir p Como Real
    p <- promedio(notas, n)
    Escribir nombre, " tiene promedio ", p
    opcion <- 0
    Mientras NO opcion Hacer
        Escribir "Letra: ", letra((int)p)
        opcion <- 1
    FinMientras
FinAlgoritmo
