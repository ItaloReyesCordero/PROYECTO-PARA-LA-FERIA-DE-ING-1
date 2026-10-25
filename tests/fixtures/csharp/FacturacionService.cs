using System;
using System.Collections.Generic;
using System.IO;

namespace Facturacion
{
    public class FacturacionService
    {
        private readonly IMedioPago pago;

        public FacturacionService(IMedioPago pago)
        {
            this.pago = pago;
        }

        /// <summary>Calcula el total, cobra y guarda la factura.</summary>
        public bool Emitir(Factura factura)
        {
            if (factura.Items.Count == 0)
            {
                Console.WriteLine("Factura vacía");
                return false;
            }
            double total = 0;
            foreach (double[] item in factura.Items)
            {
                if (item[0] < 0)
                {
                    continue;
                }
                if (item[1] == 0)
                {
                    break;
                }
                total += item[0] * item[1];
            }
            double descuento;
            switch (factura.TipoPago)
            {
                case "efectivo":
                    descuento = 0.05;
                    break;
                case "tarjeta":
                    descuento = 0;
                    break;
                default:
                    descuento = 0;
                    break;
            }
            total = total * (1 - descuento);
            int intentos = 0;
            bool cobrado = false;
            while (intentos < 3 && !cobrado)
            {
                intentos++;
                try
                {
                    cobrado = pago.Cobrar(total, factura.TipoPago);
                }
                catch (ArgumentException e)
                {
                    Console.WriteLine("Error al cobrar: " + e.Message);
                }
            }
            if (!cobrado)
            {
                return false;
            }
            File.AppendAllText("facturas.txt", factura.Cliente + ";" + total + "\n");
            return true;
        }

        public static void Main(string[] args)
        {
            string cliente = Console.ReadLine();
            var factura = new Factura(cliente, new List<double[]> { new double[] { 10, 2 } }, "efectivo");
            var servicio = new FacturacionService(new PagoService());
            if (servicio.Emitir(factura))
            {
                Console.WriteLine("Factura emitida");
            }
            else
            {
                Console.WriteLine("No se pudo emitir");
            }
        }
    }
}
