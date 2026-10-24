#pragma once
#include <string>

class PagoService {
public:
    bool cobrar(double monto, const std::string& tipo);
};
