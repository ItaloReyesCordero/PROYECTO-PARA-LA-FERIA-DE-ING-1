<?php

namespace App\Repositories;

use App\Models\Factura;
use PDO;
use PDOException;

class MySqlFacturaRepository implements FacturaRepository
{
    public function __construct(private PDO $db)
    {
    }

    /** Guarda la factura y sus ítems en una transacción. */
    public function guardar(Factura $factura): void
    {
        $this->db->beginTransaction();
        try {
            $stmt = $this->db->prepare('INSERT INTO facturas (cliente_id, total) VALUES (?, ?)');
            $stmt->execute([$factura->clienteId, $factura->total]);
            $id = (int) $this->db->lastInsertId();
            foreach ($factura->items as $item) {
                $linea = $this->db->prepare(
                    'INSERT INTO factura_items (factura_id, producto_id, cantidad, precio) VALUES (?, ?, ?, ?)'
                );
                $linea->execute([$id, $item['producto_id'], $item['cantidad'], $item['precio']]);
            }
            $this->db->commit();
        } catch (PDOException $e) {
            $this->db->rollBack();
            throw $e;
        }
    }

    /** Facturas de un cliente, de la más nueva a la más antigua. */
    public function porCliente(string $cliente): array
    {
        $stmt = $this->db->prepare(
            'SELECT f.* FROM facturas f JOIN clientes c ON c.id = f.cliente_id WHERE c.nombre = ? ORDER BY f.id DESC'
        );
        $stmt->execute([$cliente]);
        $facturas = [];
        while ($fila = $stmt->fetch()) {
            $facturas[] = Factura::desdeFila($fila);
        }
        return $facturas;
    }

    /** Busca una factura por su número. */
    public function buscar(int $id): ?Factura
    {
        $stmt = $this->db->prepare('SELECT * FROM facturas WHERE id = ?');
        $stmt->execute([$id]);
        $fila = $stmt->fetch();
        if ($fila === false) {
            return null;
        }
        return Factura::desdeFila($fila);
    }
}
