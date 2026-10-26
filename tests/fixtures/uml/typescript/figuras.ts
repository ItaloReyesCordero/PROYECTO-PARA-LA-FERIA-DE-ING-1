/** Algo que se puede dibujar. */
export interface Dibujable {
  dibujar(): void;
}

/** Una figura con nombre. */
export abstract class Figura {
  protected nombre: string;
  private static contador = 0;

  constructor(nombre: string) {
    this.nombre = nombre;
    Figura.contador++;
  }

  abstract area(): number;

  static total(): number {
    return Figura.contador;
  }
}

export class Circulo extends Figura implements Dibujable {
  private radio: number;
  public readonly centro: Punto = new Punto();

  constructor(nombre: string, radio: number) {
    super(nombre);
    this.radio = radio;
  }

  area(): number {
    return Math.PI * this.radio * this.radio;
  }

  dibujar(): void {
    console.log("Circulo " + this.nombre);
  }

  private esValido(): boolean {
    return this.radio > 0;
  }
}

export class Punto {
  x = 0;
  y = 0;
}
