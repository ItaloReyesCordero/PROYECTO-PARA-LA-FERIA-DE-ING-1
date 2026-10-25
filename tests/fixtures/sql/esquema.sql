-- Fixture SQL: las tres formas de clave foránea (SPEC §9).
/* Un comentario con un punto y coma; que no debe cortar la sentencia */

CREATE TABLE autores (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    bio TEXT DEFAULT 'sin; datos'
);

CREATE TABLE editoriales (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL
);

-- Forma 1: REFERENCES en la columna
CREATE TABLE libros (
    id INTEGER PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    autor_id INTEGER NOT NULL REFERENCES autores(id),
    editorial_id INTEGER
);

-- Forma 2: FOREIGN KEY a nivel de tabla
CREATE TABLE prestamos (
    id INTEGER,
    libro_id INTEGER NOT NULL,
    fecha DATE,
    PRIMARY KEY (id),
    FOREIGN KEY (libro_id) REFERENCES libros (id)
);

-- Forma 3: ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY
ALTER TABLE libros ADD CONSTRAINT fk_libro_editorial FOREIGN KEY (editorial_id) REFERENCES editoriales (id);

-- Sentencia propia de PostgreSQL (prueba el reintento con otro dialecto)
CREATE TABLE etiquetas (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL
);

-- Sentencia rota: debe generar una advertencia y no detener el análisis
CREATE TABLE ;
