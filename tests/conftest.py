"""Configuración compartida de pytest."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES = TESTS_DIR / "fixtures"
GOLDEN = TESTS_DIR / "golden"

_CACHE_DIR: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    # Los tests del CLI usan la caché: que sea una carpeta temporal, no la del usuario.
    global _CACHE_DIR
    _CACHE_DIR = tempfile.mkdtemp(prefix="desglosa-cache-")
    os.environ["DESGLOSA_CACHE_DIR"] = _CACHE_DIR


def pytest_unconfigure(config: pytest.Config) -> None:
    if _CACHE_DIR:
        shutil.rmtree(_CACHE_DIR, ignore_errors=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="reescribe los archivos golden con la salida actual (revisa el diff después)",
    )


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-golden"))


@pytest.fixture
def golden(update_golden: bool):
    """Compara `text` con tests/golden/<name>; con --update-golden lo reescribe."""

    def check(name: str, text: str) -> None:
        path = GOLDEN / name
        if update_golden or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            if not update_golden:
                pytest.fail(f"golden nuevo creado: {path.name}; revísalo y vuelve a correr")
            return
        expected = path.read_text(encoding="utf-8")
        assert text == expected, f"la salida difiere de {path.name} (usa --update-golden)"

    return check


def have_grammars(*names: str) -> bool:
    from desglosa import grammars

    return set(names) <= grammars.downloaded()


needs_grammars = pytest.mark.skipif(
    not have_grammars(
        "python",
        "javascript",
        "typescript",
        "php",
        "java",
        "c",
        "cpp",
        "go",
        "ruby",
        "rust",
        "kotlin",
        "swift",
        "csharp",
    ),
    reason="faltan gramáticas: ejecuta `desglosa setup`",
)
