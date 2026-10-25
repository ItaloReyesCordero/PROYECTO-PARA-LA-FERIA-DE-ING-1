using System;

namespace Facturacion
{
    public interface IMedioPago
    {
        bool Cobrar(double monto, string tipo);
    }

    public class PagoService : IMedioPago
    {
        /// <summary>Cobra el monto con el tipo de pago indicado.</summary>
        public bool Cobrar(double monto, string tipo)
        {
            if (monto <= 0)
            {
                throw new ArgumentException("monto inválido");
            }
            Console.WriteLine("Cobrando " + monto + " con " + tipo);
            return true;
        }
    }
}
