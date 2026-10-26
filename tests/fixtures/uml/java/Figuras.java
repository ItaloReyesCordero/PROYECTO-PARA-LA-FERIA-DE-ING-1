package figuras;

/** Algo que se puede dibujar. */
interface Dibujable {
    void dibujar();
}

/** Una figura con nombre. */
abstract class Figura {
    protected String nombre;
    private static int contador = 0;

    public Figura(String nombre) {
        this.nombre = nombre;
        contador++;
    }

    public abstract double area();

    public static int total() {
        return contador;
    }
}

public class Circulo extends Figura implements Dibujable {
    private double radio;
    public final Punto centro = new Punto();

    public Circulo(String nombre, double radio) {
        super(nombre);
        this.radio = radio;
    }

    @Override
    public double area() {
        return Math.PI * radio * radio;
    }

    public void dibujar() {
        System.out.println("Circulo " + nombre);
    }

    private boolean esValido() {
        return radio > 0;
    }
}

class Punto {
    int x;
    int y;
}
