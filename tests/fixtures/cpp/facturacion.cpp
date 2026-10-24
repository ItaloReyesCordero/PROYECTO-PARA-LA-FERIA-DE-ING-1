#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "pago.hpp"

struct Item {
    double precio;
    int cantidad;
};

class Factura {
public:
    std::string cliente;
    std::vector<Item> items;
    int tipoPago;
};

class FacturacionService {
public:
    explicit FacturacionService(PagoService& pago) : pago(pago) {}

    // Calcula el total, cobra y guarda la factura.
    bool emitir(const Factura& factura)
    {
        if (factura.items.empty()) {
            std::cout << "Factura vacia" << std::endl;
            return false;
        }
        double total = 0;
        for (const Item& item : factura.items) {
            if (item.precio < 0) {
                continue;
            }
            if (item.cantidad == 0) {
                break;
            }
            total += item.precio * item.cantidad;
        }
        double descuento;
        switch (factura.tipoPago) {
        case 1:
            descuento = 0.05;
            break;
        case 2:
            descuento = 0;
            break;
        default:
            descuento = 0;
        }
        total = total * (1 - descuento);
        int intentos = 0;
        bool cobrado = false;
        while (intentos < 3 && !cobrado) {
            intentos++;
            try {
                cobrado = pago.cobrar(total, "efectivo");
            } catch (const std::invalid_argument& e) {
                std::cout << "Error al cobrar: " << e.what() << std::endl;
            }
        }
        if (!cobrado) {
            return false;
        }
        std::ofstream archivo("facturas.txt", std::ios::app);
        archivo << factura.cliente << ";" << total << "\n";
        return true;
    }

private:
    PagoService& pago;
};

int main()
{
    Factura factura;
    std::cin >> factura.cliente;
    factura.items.push_back({10, 2});
    factura.tipoPago = 1;
    PagoService pago;
    FacturacionService servicio(pago);
    if (servicio.emitir(factura)) {
        std::cout << "Factura emitida" << std::endl;
    } else {
        std::cout << "No se pudo emitir" << std::endl;
    }
    return 0;
}
