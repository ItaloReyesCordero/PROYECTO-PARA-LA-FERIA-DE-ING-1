<?php

namespace Figuras;

/** Algo que se puede dibujar. */
interface Dibujable
{
    public function dibujar(): void;
}

/** Una figura con nombre. */
abstract class Figura
{
    protected string $nombre;
    private static int $contador = 0;

    public function __construct(string $nombre)
    {
        $this->nombre = $nombre;
        self::$contador++;
    }

    abstract public function area(): float;

    public static function total(): int
    {
        return self::$contador;
    }
}

class Circulo extends Figura implements Dibujable
{
    private float $radio;
    public Punto $centro;

    public function __construct(string $nombre, float $radio)
    {
        parent::__construct($nombre);
        $this->radio = $radio;
        $this->centro = new Punto();
    }

    public function area(): float
    {
        return M_PI * $this->radio * $this->radio;
    }

    public function dibujar(): void
    {
        echo "Circulo " . $this->nombre;
    }

    private function esValido(): bool
    {
        return $this->radio > 0;
    }
}

class Punto
{
    public $x = 0;
    public $y = 0;
}
