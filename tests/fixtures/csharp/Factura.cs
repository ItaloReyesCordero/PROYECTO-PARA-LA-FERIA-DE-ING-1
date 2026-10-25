using System.Collections.Generic;

namespace Facturacion
{
    /// <summary>Una factura con ítems y un tipo de pago.</summary>
    public class Factura
    {
        public string Cliente;
        public List<double[]> Items;
        public string TipoPago;

        public Factura(string cliente, List<double[]> items, string tipoPago)
        {
            this.Cliente = cliente;
            this.Items = items;
            this.TipoPago = tipoPago;
        }

        public void AgregarItem(double[] item)
        {
            this.Items.Add(item);
        }
    }
}
