interface Notificador {
  enviar(msg: string): void;
}

class Correo implements Notificador {
  enviar(msg: string): void {
    console.log("correo:", msg);
  }
}

class Sms implements Notificador {
  enviar(msg: string): void {
    console.log("sms:", msg);
  }
}

export class Servicio {
  constructor(private notif: Notificador) {}

  /** Avisa n veces y vuelve a empezar con un aviso menos. */
  avisar(n: number): void {
    for (let i = 0; i < n; i++) {
      this.notif.enviar("hola");
    }
    if (n > 3) {
      this.avisar(n - 1);
    } else {
      this.fin();
    }
  }

  fin(): void {
    console.log("fin");
  }
}

export function factorial(n: number): number {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}
