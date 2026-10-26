"""Diseño visual (SPEC §11.3): un color = un significado, en ambos temas."""

from __future__ import annotations

import re
from pathlib import Path

from desglosa.ir import FLOW_NODE_KINDS

CSS = (
    Path(__file__).resolve().parent.parent / "src" / "desglosa" / "render" / "style.css"
).read_text(encoding="utf-8")

DARK = {
    "--c-terminal": "#34d399",
    "--c-proceso": "#60a5fa",
    "--c-subproceso": "#a78bfa",
    "--c-decision": "#fbbf24",
    "--c-es": "#22d3ee",
    "--c-teclado": "#22d3ee",
    "--c-pantalla": "#f472b6",
    "--c-documento": "#f472b6",
    "--c-excepcion": "#fb7185",
    "--c-externo": "#94a3b8",
    "--c-modulo": "#818cf8",
    "--c-clase": "#60a5fa",
    "--c-funcion": "#a78bfa",
    "--c-entrada": "#34d399",
    "--c-tabla": "#fb923c",
    "--fondo": "#0b1120",
    "--rejilla": "#1e293b",
    "--superficie": "#0f172a",
    "--texto": "#e5e7eb",
    "--texto-suave": "#94a3b8",
}
LIGHT = {
    "--c-terminal": "#059669",
    "--c-proceso": "#2563eb",
    "--c-subproceso": "#7c3aed",
    "--c-decision": "#b45309",
    "--c-es": "#0891b2",
    "--c-teclado": "#0891b2",
    "--c-pantalla": "#db2777",
    "--c-documento": "#db2777",
    "--c-excepcion": "#e11d48",
    "--c-externo": "#64748b",
    "--c-modulo": "#4f46e5",
    "--c-clase": "#2563eb",
    "--c-funcion": "#7c3aed",
    "--c-entrada": "#059669",
    "--c-tabla": "#c2410c",
    "--fondo": "#f8fafc",
    "--rejilla": "#e2e8f0",
    "--superficie": "#ffffff",
    "--texto": "#0f172a",
    "--texto-suave": "#475569",
}


def _block(selector: str) -> dict[str, str]:
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert m, f"no está el bloque {selector}"
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1)))


def test_dark_tokens_match_spec():
    tokens = _block(":root")
    for name, value in DARK.items():
        assert tokens[name].strip().lower() == value, name


def test_light_tokens_match_spec():
    tokens = _block('[data-tema="claro"]')
    for name, value in LIGHT.items():
        assert tokens[name].strip().lower() == value, name


def test_every_flow_kind_has_a_class():
    for kind in FLOW_NODE_KINDS:
        if kind == "conector_pagina":
            continue
        assert f".k-{kind}" in CSS, kind


def test_confidence_styles_are_distinct():
    styles = {}
    for conf in ("exacta", "probable", "ambigua", "externa"):
        m = re.search(r"\.arista\.c-" + conf + r"\s*\{([^}]*)\}", CSS)
        assert m, conf
        styles[conf] = m.group(1).strip()
    assert len(set(styles.values())) == 4
    assert "6 4" in styles["probable"] and "2 4" in styles["ambigua"]


def test_only_semantic_colors_in_svg_rules():
    """Ningún color "suelto" en las reglas de nodos y aristas: solo variables del mapa."""
    rules = re.findall(r"\n(\.(?:nodo|arista|k-|punta|etiqueta)[^{]*)\{([^}]*)\}", CSS)
    for selector, body in rules:
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", body), f"color fijo en {selector.strip()}"


def test_every_visual_style_defines_all_tokens():
    """Clásico, pizarra y alto contraste redefinen todos los colores: si faltara uno, ese
    tipo de nodo heredaría el color de otro estilo y se perdería su significado."""
    for style in ("clasico", "pizarra", "contraste"):
        tokens = _block(f'[data-estilo="{style}"]')
        missing = set(DARK) - set(tokens)
        assert not missing, (style, missing)
        assert "--relleno" in tokens
    # En clásico todo es blanco y negro: el tipo se reconoce por la forma.
    clasico = _block('[data-estilo="clasico"]')
    assert {clasico[k].strip() for k in DARK if k.startswith("--c-") and k != "--c-externo"} == {
        "#111111"
    }
