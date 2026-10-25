"""Registro de lenguajes soportados: nombre lógico → (LangSpec, LangHooks)."""

from __future__ import annotations

from importlib import import_module

from desglosa.langs.spec import LangHooks, LangSpec

# Lenguajes con extractor implementado. SQL se procesa aparte con sqlglot (sqlmodel.py).
_MODULES = {
    "c": "desglosa.langs.c",
    "cpp": "desglosa.langs.cpp",
    "go": "desglosa.langs.go",
    "java": "desglosa.langs.java",
    "javascript": "desglosa.langs.javascript",
    "kotlin": "desglosa.langs.kotlin",
    "php": "desglosa.langs.php",
    "python": "desglosa.langs.python",
    "ruby": "desglosa.langs.ruby",
    "rust": "desglosa.langs.rust",
    "swift": "desglosa.langs.swift",
    "typescript": "desglosa.langs.typescript",
}

SUPPORTED = tuple(sorted(_MODULES))


def get(lang: str) -> tuple[LangSpec, LangHooks] | None:
    module_name = _MODULES.get(lang)
    if module_name is None:
        return None
    module = import_module(module_name)
    return module.SPEC, module.HOOKS
