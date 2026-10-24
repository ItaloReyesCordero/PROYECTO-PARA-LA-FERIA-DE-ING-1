-- Esquema de la mini aplicación de facturación (MySQL).

CREATE TABLE clientes (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nombre VARCHAR(120) NOT NULL,
    ruc CHAR(11)
);

CREATE TABLE productos (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nombre VARCHAR(120) NOT NULL,
    precio DECIMAL(10, 2) NOT NULL
);

CREATE TABLE facturas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    cliente_id INT NOT NULL REFERENCES clientes(id),
    total DECIMAL(10, 2) NOT NULL,
    creada DATETIME
);

CREATE TABLE factura_items (
    factura_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (factura_id, producto_id),
    FOREIGN KEY (factura_id) REFERENCES facturas(id)
);

ALTER TABLE factura_items
    ADD CONSTRAINT fk_items_producto FOREIGN KEY (producto_id) REFERENCES productos(id);
