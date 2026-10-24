"""TypeScript (gramáticas `typescript` y `tsx`). Reutiliza la lógica de JavaScript."""

from __future__ import annotations

from dataclasses import replace

from desglosa.langs import javascript

SPEC = replace(
    javascript.SPEC,
    name="typescript",
    grammar="typescript",
    class_nodes=javascript.SPEC.class_nodes + ("abstract_class_declaration",),
    interface_nodes=("interface_declaration",),
    method_nodes=javascript.SPEC.method_nodes + ("method_signature", "abstract_method_signature"),
)


class Hooks(javascript.Hooks):
    pass


HOOKS = Hooks(SPEC)
