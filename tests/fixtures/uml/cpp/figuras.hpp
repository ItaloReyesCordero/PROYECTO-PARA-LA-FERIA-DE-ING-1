#include <string>

/** Algo que se puede dibujar. */
class Dibujable {
public:
    virtual void dibujar() = 0;
};

/** Una figura con nombre. */
class Figura {
protected:
    std::string nombre;
private:
    static int contador;
public:
    Figura(const std::string& nombre) : nombre(nombre) { contador++; }
    virtual double area() const = 0;
    static int total() { return contador; }
};

struct Punto {
    int x;
    int y;
};

class Circulo : public Figura, public Dibujable {
private:
    double radio;
public:
    Punto centro;
    Circulo(const std::string& nombre, double radio) : Figura(nombre), radio(radio) {}
    double area() const override { return 3.14159 * radio * radio; }
    void dibujar() override {}
private:
    bool esValido() const { return radio > 0; }
};
