def total(precios):
    suma = 0
    for p in precios:
        suma += p
    return suma


def descuento(total):
    return total * 0.1


def imprimir(total):
    print("Total:", total)
