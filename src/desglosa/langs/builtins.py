"""Clasificación de llamadas de entrada/salida por lenguaje (SPEC §6.2, io_kind).

Las reglas comparan el nombre completo normalizado (`receptor.nombre`, con `->`, `::`
y `$` convertidos/quitados) o solo el nombre cuando es suficientemente distintivo.
"""

from __future__ import annotations

PANTALLA = "pantalla"
TECLADO = "teclado"
LEE = "archivo_lee"
ESCRIBE = "archivo_escribe"

# Nombre completo (receptor.nombre) → tipo
_FULL: dict[str, dict[str, str]] = {
    "csharp": {
        "Console.WriteLine": PANTALLA,
        "Console.Write": PANTALLA,
        "Console.Error.WriteLine": PANTALLA,
        "Console.ReadLine": TECLADO,
        "Console.Read": TECLADO,
        "Console.ReadKey": TECLADO,
        "File.ReadAllText": LEE,
        "File.ReadAllLines": LEE,
        "File.ReadAllBytes": LEE,
        "File.ReadLines": LEE,
        "File.WriteAllText": ESCRIBE,
        "File.WriteAllLines": ESCRIBE,
        "File.WriteAllBytes": ESCRIBE,
        "File.AppendAllText": ESCRIBE,
        "File.AppendAllLines": ESCRIBE,
    },
    "python": {
        "sys.stdout.write": PANTALLA,
        "sys.stdin.readline": TECLADO,
        "sys.stdin.read": TECLADO,
    },
    "javascript": {
        "console.log": PANTALLA,
        "console.info": PANTALLA,
        "console.warn": PANTALLA,
        "console.error": PANTALLA,
        "console.debug": PANTALLA,
        "console.table": PANTALLA,
        "process.stdout.write": PANTALLA,
        "document.write": PANTALLA,
        "readlineSync.question": TECLADO,
        "rl.question": TECLADO,
    },
    "java": {
        "System.out.println": PANTALLA,
        "System.out.print": PANTALLA,
        "System.out.printf": PANTALLA,
        "System.out.format": PANTALLA,
        "System.err.println": PANTALLA,
        "System.err.print": PANTALLA,
        "System.err.printf": PANTALLA,
        "System.in.read": TECLADO,
        "Files.readAllLines": LEE,
        "Files.readString": LEE,
        "Files.readAllBytes": LEE,
        "Files.lines": LEE,
        "Files.newBufferedReader": LEE,
        "Files.write": ESCRIBE,
        "Files.writeString": ESCRIBE,
        "Files.newBufferedWriter": ESCRIBE,
    },
    "go": {
        "fmt.Println": PANTALLA,
        "fmt.Printf": PANTALLA,
        "fmt.Print": PANTALLA,
        "fmt.Scan": TECLADO,
        "fmt.Scanln": TECLADO,
        "fmt.Scanf": TECLADO,
        "os.ReadFile": LEE,
        "ioutil.ReadFile": LEE,
        "os.Open": LEE,
        "os.WriteFile": ESCRIBE,
        "ioutil.WriteFile": ESCRIBE,
        "os.Create": ESCRIBE,
    },
    "rust": {
        "fs.read_to_string": LEE,
        "fs.read": LEE,
        "File.open": LEE,
        "fs.write": ESCRIBE,
        "File.create": ESCRIBE,
    },
    "ruby": {
        "STDIN.gets": TECLADO,
        "stdin.gets": TECLADO,
        "File.read": LEE,
        "File.readlines": LEE,
        "File.foreach": LEE,
        "File.write": ESCRIBE,
    },
}
_FULL["typescript"] = _FULL["javascript"]

# Solo el nombre → tipo. Sin prefijo: solo si se llama sin receptor (`print(x)`).
# Con prefijo ".": método, vale con cualquier receptor (`ruta.read_text()`).
_NAME: dict[str, dict[str, str]] = {
    "python": {
        "print": PANTALLA,
        "pprint": PANTALLA,
        "input": TECLADO,
        ".read_text": LEE,
        ".read_bytes": LEE,
        ".write_text": ESCRIBE,
        ".write_bytes": ESCRIBE,
    },
    "javascript": {
        "alert": PANTALLA,
        "prompt": TECLADO,
        ".readFile": LEE,
        ".readFileSync": LEE,
        ".createReadStream": LEE,
        ".writeFile": ESCRIBE,
        ".writeFileSync": ESCRIBE,
        ".appendFile": ESCRIBE,
        ".appendFileSync": ESCRIBE,
        ".createWriteStream": ESCRIBE,
    },
    "php": {
        "print_r": PANTALLA,
        "var_dump": PANTALLA,
        "printf": PANTALLA,
        "vprintf": PANTALLA,
        "readline": TECLADO,
        "file_get_contents": LEE,
        "file": LEE,
        "fread": LEE,
        "fgetcsv": LEE,
        "file_put_contents": ESCRIBE,
        "fwrite": ESCRIBE,
        "fputs": ESCRIBE,
        "fputcsv": ESCRIBE,
    },
    "java": {
        ".nextLine": TECLADO,
        ".nextInt": TECLADO,
        ".nextDouble": TECLADO,
        ".nextFloat": TECLADO,
        ".nextLong": TECLADO,
        ".nextBoolean": TECLADO,
        ".nextShort": TECLADO,
        ".nextByte": TECLADO,
        ".readLine": TECLADO,
    },
    "c": {
        "printf": PANTALLA,
        "puts": PANTALLA,
        "putchar": PANTALLA,
        "scanf": TECLADO,
        "gets": TECLADO,
        "getchar": TECLADO,
        "getch": TECLADO,
        "fprintf": ESCRIBE,
        "fputs": ESCRIBE,
        "fputc": ESCRIBE,
        "fwrite": ESCRIBE,
        "fscanf": LEE,
        "fgets": LEE,
        "fgetc": LEE,
        "fread": LEE,
    },
    "go": {"println": PANTALLA, "print": PANTALLA},
    "rust": {"println": PANTALLA, "print": PANTALLA, "eprintln": PANTALLA, "read_line": TECLADO},
    "kotlin": {
        "println": PANTALLA,
        "print": PANTALLA,
        "readLine": TECLADO,
        "readln": TECLADO,
        ".readText": LEE,
        ".readLines": LEE,
        ".readBytes": LEE,
        ".writeText": ESCRIBE,
        ".appendText": ESCRIBE,
        ".writeBytes": ESCRIBE,
    },
    "swift": {"print": PANTALLA, "debugPrint": PANTALLA, "readLine": TECLADO},
    "ruby": {"puts": PANTALLA, "print": PANTALLA, "p": PANTALLA, "pp": PANTALLA, "gets": TECLADO},
}
_NAME["typescript"] = _NAME["javascript"]
_NAME["cpp"] = dict(_NAME["c"])

# Constructores que implican E/S de archivo (Java, C#).
_NEW: dict[str, dict[str, str]] = {
    "csharp": {
        "StreamReader": LEE,
        "StreamWriter": ESCRIBE,
        "FileStream": LEE,
    },
    "java": {
        "FileReader": LEE,
        "FileInputStream": LEE,
        "FileWriter": ESCRIBE,
        "FileOutputStream": ESCRIBE,
        "PrintWriter": ESCRIBE,
    },
}

_STDIN = {"stdin", "STDIN", "std::cin", "cin", "os.Stdin", "System.in"}


def _norm(text: str) -> str:
    t = text.replace("->", ".").replace("?.", ".").replace("::", ".").replace("$", "")
    for prefix in ("std.", "this.", "self."):
        if t.startswith(prefix):
            t = t[len(prefix) :]
    return t


def _mode_writes(mode: str) -> bool:
    return any(ch in mode for ch in "wax+")


def _string_value(arg: str) -> str | None:
    arg = arg.strip()
    if len(arg) >= 2 and arg[0] in "\"'" and arg[-1] == arg[0]:
        return arg[1:-1]
    return None


def classify_io(
    lang: str, callee: str, receiver: str | None, args: tuple[str, ...], is_new: bool = False
) -> str | None:
    """Devuelve el io_kind de una llamada o None si no es de entrada/salida."""
    if is_new:
        return _NEW.get(lang, {}).get(callee)
    name = callee.rstrip("!")
    full = f"{_norm(receiver)}.{name}" if receiver else name

    # Casos que dependen de los argumentos.
    if name == "open" and lang == "python" and not receiver:
        mode = None
        for a in args[1:]:
            if a.startswith("mode="):
                mode = _string_value(a[5:])
                break
            if "=" not in a:
                mode = _string_value(a)
                break
        return ESCRIBE if mode and _mode_writes(mode) else LEE
    if name == "fopen" and lang in ("c", "cpp", "php"):
        mode = _string_value(args[1]) if len(args) > 1 else None
        return ESCRIBE if mode and _mode_writes(mode) else LEE
    if name in ("fgets", "fscanf", "fgetc", "getline", "stream_get_line") and lang in (
        "c",
        "cpp",
        "php",
    ):
        if any(a.strip() in _STDIN for a in args):
            return TECLADO
        if name == "getline":
            return None
    if lang == "go" and name == "NewReader" and any(a.strip() == "os.Stdin" for a in args):
        return TECLADO
    if lang == "rust" and name == "read_line":
        return TECLADO
    if lang == "swift" and name == "write" and any(a.startswith("toFile") for a in args):
        return ESCRIBE
    if lang == "swift" and name == "String" and any(a.startswith("contentsOfFile") for a in args):
        return LEE

    kind = _FULL.get(lang, {}).get(full)
    if kind:
        return kind
    if receiver and _norm(receiver) in ("console",) and lang in ("javascript", "typescript"):
        return PANTALLA
    table = _NAME.get(lang, {})
    kind = table.get("." + name)
    if kind:
        return kind
    if receiver is None:
        return table.get(name)
    return None
