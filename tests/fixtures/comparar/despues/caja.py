def imprimir(total):
    print("Total:", total)


def total(precios):
    suma = 0
    for p in precios:
        if p < 0:
            continue
        suma += p
    return suma


def igv(total):
    return total * 0.18
