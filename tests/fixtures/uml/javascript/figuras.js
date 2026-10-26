/** Una figura con nombre. */
export class Figura {
  static contador = 0;
  #secreto = 1;

  constructor(nombre) {
    this.nombre = nombre;
    Figura.contador++;
  }

  area() {
    return 0;
  }

  static total() {
    return Figura.contador;
  }
}

export class Circulo extends Figura {
  constructor(nombre, radio) {
    super(nombre);
    this.radio = radio;
    this.centro = new Punto();
  }

  area() {
    return Math.PI * this.radio * this.radio;
  }

  #esValido() {
    return this.radio > 0;
  }
}

export class Punto {
  x = 0;
  y = 0;
}
