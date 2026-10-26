// tienda.py, escrito por Desglosa

Funcion resultado <- total_con_igv(precios, igv)
    total <- 0
    Para i <- 0 Hasta len(precios) - 1 Hacer
        total <- total + precios[i]
    FinPara
    resultado <- total * (1 + igv)
FinFuncion

Funcion cuenta_regresiva(n)
    Para k <- n Hasta 1 Con Paso -1 Hacer
        Escribir Sin Saltar k, " "
    FinPara
    Escribir ""
FinFuncion

Algoritmo tienda
    Escribir Sin Saltar "Cliente: "
    Leer nombre
    precios <- []
    Mientras Verdadero Hacer
        Escribir Sin Saltar "Precio (vacío para terminar): "
        Leer texto
        Si NO texto Entonces
            // sale del bucle (break)
        FinSi
        precios.append(float(texto))
    FinMientras
    total <- total_con_igv(precios)
    Escribir "Total de ", nombre, ": ", total, " soles"
    Si total > 100 Y nombre <> "" Entonces
        Escribir "Tiene descuento"
    SiNo
        Si total > 50 Entonces
            Escribir "Casi tiene descuento"
        SiNo
            Escribir "Sin descuento"
        FinSi
    FinSi
    cuenta_regresiva(3)
FinAlgoritmo
