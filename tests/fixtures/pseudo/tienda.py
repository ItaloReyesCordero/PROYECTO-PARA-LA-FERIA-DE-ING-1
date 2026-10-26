"""Una caja registradora de ejemplo."""


def total_con_igv(precios, igv=0.18):
    total = 0
    for i in range(len(precios)):
        total += precios[i]
    return total * (1 + igv)


def cuenta_regresiva(n):
    for k in range(n, 0, -1):
        print(k, end=" ")
    print()


def main():
    nombre = input("Cliente: ")
    precios = []
    while True:
        texto = input("Precio (vacío para terminar): ")
        if not texto:
            break
        precios.append(float(texto))
    total = total_con_igv(precios)
    print(f"Total de {nombre}: {total:.2f} soles")
    if total > 100 and nombre != "":
        print("Tiene descuento")
    elif total > 50:
        print("Casi tiene descuento")
    else:
        print("Sin descuento")
    cuenta_regresiva(3)
