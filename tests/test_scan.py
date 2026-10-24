from __future__ import annotations

from pathlib import Path

from desglosa.scan import ScanOptions, decode_bytes, detect_language, grammar_for, scan


def _write(root: Path, rel: str, content: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def test_detect_language():
    assert detect_language("a/b.py") == "python"
    assert detect_language("x.TSX") == "typescript"
    assert detect_language("x.h") == "c"
    assert detect_language("x.h", h_as="cpp") == "cpp"
    assert detect_language("vista.blade.php") is None
    assert detect_language("x.txt") is None
    assert grammar_for("x.tsx", "typescript") == "tsx"
    assert grammar_for("x.ts", "typescript") == "typescript"


def test_decode_fallbacks():
    assert decode_bytes("año\r\n".encode()) == ("año\n", "utf-8")
    assert decode_bytes(b"\xef\xbb\xbfhola") == ("hola", "utf-8-sig")
    assert decode_bytes("año".encode("cp1252")) == ("año", "cp1252")


def test_scan_ignores_and_orders(tmp_path: Path):
    _write(tmp_path, "b.py", "x = 1\n")
    _write(tmp_path, "a/z.py", "x = 1\n")
    _write(tmp_path, "a/m.js", "let x = 1;\n")
    _write(tmp_path, "vendor/lib.php", "<?php echo 1;\n")
    _write(tmp_path, "node_modules/x/index.js", "x\n")
    _write(tmp_path, "app/x.min.js", "var a=1;\n")
    _write(tmp_path, "app/mapa.js.map", "{}\n")
    _write(tmp_path, "public/build/app.js", "x\n")
    _write(tmp_path, "secreto.py", "x = 1\n")
    _write(tmp_path, "gen/auto.py", "x = 1\n")
    _write(tmp_path, ".gitignore", "secreto.py\ngen/\n")
    _write(tmp_path, "docs/notas.txt", "no es código\n")
    _write(tmp_path, "vistas/home.blade.php", "<div></div>\n")
    _write(tmp_path, "app/largo.js", "var a = 1;" * 300 + "\n")
    result = scan(tmp_path)
    paths = [e.path for e in result.entries]
    assert paths == ["a/m.js", "a/z.py", "b.py"]
    assert [(s.path, s.skipped_reason) for s in result.skipped] == [("app/largo.js", "minificado")]


def test_scan_desglosaignore_and_cli_ignore(tmp_path: Path):
    _write(tmp_path, "a.py", "x = 1\n")
    _write(tmp_path, "b.py", "x = 1\n")
    _write(tmp_path, "c.py", "x = 1\n")
    _write(tmp_path, ".desglosaignore", "a.py\n")
    result = scan(tmp_path, ScanOptions(ignore=("c.py",)))
    assert [e.path for e in result.entries] == ["b.py"]


def test_scan_size_binary_and_lang_filter(tmp_path: Path):
    _write(tmp_path, "grande.py", "x = 1\n" * 400)
    _write(tmp_path, "bin.c", b"int x;\x00\x01")
    _write(tmp_path, "ok.php", "<?php echo 1;\n")
    result = scan(tmp_path, ScanOptions(max_file_kb=1))
    reasons = {s.path: s.skipped_reason for s in result.skipped}
    assert reasons["bin.c"] == "binario"
    assert reasons["grande.py"].startswith("demasiado grande")
    only_php = scan(tmp_path, ScanOptions(langs=("php",)))
    assert [e.path for e in only_php.entries] == ["ok.php"]


def test_scan_single_file(tmp_path: Path):
    _write(tmp_path, "uno.py", "x = 1\n")
    _write(tmp_path, "dos.py", "x = 1\n")
    result = scan(tmp_path / "uno.py")
    assert [e.path for e in result.entries] == ["uno.py"]
