#include <iostream>
#include <stdexcept>
#include "pago.hpp"

// Cobra el monto con el tipo de pago indicado.
bool PagoService::cobrar(double monto, const std::string& tipo)
{
    if (monto <= 0) {
        throw std::invalid_argument("monto invalido");
    }
    std::cout << "Cobrando " << monto << " con " << tipo << std::endl;
    return true;
}
