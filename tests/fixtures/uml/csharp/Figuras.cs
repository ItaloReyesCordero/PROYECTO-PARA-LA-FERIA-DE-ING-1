namespace Figuras
{
    /// <summary>Algo que se puede dibujar.</summary>
    public interface IDibujable
    {
        void Dibujar();
    }

    /// <summary>Una figura con nombre.</summary>
    public abstract class Figura
    {
        protected string Nombre;
        private static int contador = 0;

        public Figura(string nombre)
        {
            Nombre = nombre;
            contador++;
        }

        public abstract double Area();

        public static int Total()
        {
            return contador;
        }
    }

    public class Circulo : Figura, IDibujable
    {
        private double radio;
        public Punto Centro { get; set; }

        public Circulo(string nombre, double radio) : base(nombre)
        {
            this.radio = radio;
        }

        public override double Area()
        {
            return System.Math.PI * radio * radio;
        }

        public void Dibujar()
        {
            System.Console.WriteLine("Circulo " + Nombre);
        }

        private bool EsValido()
        {
            return radio > 0;
        }
    }

    public class Punto
    {
        public int X;
        public int Y;
    }
}
