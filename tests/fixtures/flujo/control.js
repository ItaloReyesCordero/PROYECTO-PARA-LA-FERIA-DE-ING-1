function validar(dato) {
  if (dato === null) {
    throw new TypeError("dato nulo");
  }
  return dato.length > 0;
}

function procesar(lista) {
  let ok = 0;
  try {
    for (const item of lista) {
      if (!validar(item)) {
        throw new RangeError("vacío");
      }
      ok++;
    }
  } catch (e) {
    console.log("error", e);
  } finally {
    console.log("fin", ok);
  }
  let n = 3;
  do {
    n--;
    if (n === 1) {
      continue;
    }
    console.log(n);
  } while (n > 0);
  return ok;
}

const doble = (x) => x * 2;

function clasificar(x) {
  if (x < 0) {
    return "negativo";
  } else if (x === 0) {
    return "cero";
  } else if (x < 10) {
    return "chico";
  } else {
    return "grande";
  }
}
