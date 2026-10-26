/// Algo que se puede dibujar.
pub trait Dibujable {
    fn dibujar(&self);
}

/// Una posición.
pub struct Punto {
    pub x: i32,
    pub y: i32,
}

/// Una figura redonda.
pub struct Circulo {
    pub nombre: String,
    radio: f64,
    pub centro: Punto,
}

impl Circulo {
    pub fn area(&self) -> f64 {
        3.14159 * self.radio * self.radio
    }

    fn es_valido(&self) -> bool {
        self.radio > 0.0
    }
}

impl Dibujable for Circulo {
    fn dibujar(&self) {
        println!("Circulo {}", self.nombre);
    }
}
