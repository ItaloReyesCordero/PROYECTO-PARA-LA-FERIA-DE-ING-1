"""Diagrama de secuencia a partir de las llamadas resueltas (SPEC §8).

- DFS desde una función de entrada sobre sus llamadas en orden de línea, hasta `depth`.
- Participantes: la clase dueña de cada función (o su archivo, si es una función suelta),
  en orden de primera aparición. Si la entrada es un punto de entrada (controlador, main,
  ruta) el primer participante es el actor "Usuario".
- Mensajes numerados 1, 1.1, 1.2…; retorno punteado solo si la función devuelve algo.
- Fragmentos combinados desde `Call.context`: loop, alt/opt (if/else), alt por caso de un
  switch, try/catch. Recursión → "(recursivo)" sin expandir. Interfaces → alt
  "posible implementación". Llamadas externas → participante gris "Externo".
"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass, replace

from desglosa.ir import Call, ControlCtx, FlowGraph, Project, Symbol

FUNC_KINDS = ("function", "method")
ACTOR = "actor"
EXTERNAL = "externo"
CONSTRUCTORS = frozenset({"__construct", "__init__", "constructor", "init", "initialize"})


@dataclass(frozen=True)
class Participant:
    id: str
    label: str
    kind: str  # actor | entrada | clase | modulo | externo


@dataclass(frozen=True)
class Fragment:
    id: str
    kind: str  # loop | if | else | caso | try | catch | impl
    label: str
    parent: str | None


@dataclass(frozen=True)
class Message:
    number: str
    src: str
    dst: str
    label: str
    kind: str  # llamada | retorno | recursivo | crear
    target: str | None
    confidence: str
    fragments: tuple[str, ...]  # de afuera hacia adentro
    external: bool = False


@dataclass(frozen=True)
class SequenceDiagram:
    entry: str
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    fragments: tuple[Fragment, ...]
    truncated: bool = False


def _returns_value(flow: FlowGraph | None) -> bool:
    if flow is None:
        return False
    return any(
        n.text_tech.startswith("return ")
        or (n.text_easy.startswith("Retorna ") and n.kind != "terminal")
        for n in flow.nodes
    )


class SequenceBuilder:
    def __init__(
        self,
        project: Project,
        flows: dict[str, FlowGraph],
        routes: dict[str, str] | None = None,
        depth: int = 4,
        max_messages: int = 200,
        new_calls: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self.new_calls = new_calls  # ids de llamadas `new X()` (para dibujar "crear")
        self.by_id: dict[str, Symbol] = {s.id: s for s in project.symbols}
        self.flows = flows
        self.routes = routes or {}
        self.depth = depth
        self.max_messages = max_messages
        self.calls: dict[str, list[Call]] = defaultdict(list)
        for c in project.calls:
            self.calls[c.caller_id].append(c)
        for lst in self.calls.values():
            # Misma posición (`f()->g()`): primero la llamada interna (receptor más corto).
            lst.sort(key=lambda c: (c.line, c.col, len(c.receiver_text or ""), c.callee_text))
        self.participants: dict[str, Participant] = {}
        self.order: list[str] = []
        self.messages: list[Message] = []
        self.fragments: dict[str, Fragment] = {}
        self.truncated = False

    # ------------------------------------------------------------------ participantes

    def _owner(self, sym: Symbol) -> Symbol | None:
        cur = self.by_id.get(sym.parent_id) if sym.parent_id else None
        while cur is not None:
            if cur.kind in ("class", "interface"):
                return cur
            cur = self.by_id.get(cur.parent_id) if cur.parent_id else None
        return None

    def participant_of(self, sym: Symbol) -> str:
        owner = sym if sym.kind in ("class", "interface") else self._owner(sym)
        if owner is not None:
            pid, label = owner.id, owner.name
            kind = "entrada" if owner.is_entry else "clase"
        else:
            pid, label, kind = f"file:{sym.file}", posixpath.basename(sym.file), "modulo"
        self._add_participant(Participant(pid, label, kind))
        return pid

    def _add_participant(self, p: Participant) -> None:
        if p.id not in self.participants:
            self.participants[p.id] = p
            self.order.append(p.id)

    # ------------------------------------------------------------------ fragmentos

    def _fragments_for(self, caller: Symbol, ctx: tuple[ControlCtx, ...], parent: tuple[str, ...]):
        chain = list(parent)
        for c in ctx:
            parent_id = chain[-1] if chain else None
            fid = f"{caller.id}:{c.kind}:{c.line}:{c.label}:{parent_id}"
            if fid not in self.fragments:
                kind = {"switch_case": "caso"}.get(c.kind, c.kind)
                self.fragments[fid] = Fragment(fid, kind, c.label, parent_id)
            chain.append(fid)
        return tuple(chain)

    # ------------------------------------------------------------------ recorrido

    def build(self, entry_id: str) -> SequenceDiagram:
        entry = self.by_id[entry_id]
        prefix = ""
        start_frags: tuple[str, ...] = ()
        if entry.is_entry:
            self._add_participant(Participant(ACTOR, "Usuario", "actor"))
            dst = self.participant_of(entry)
            route = self.routes.get(entry.id)
            label = f"{route} → {entry.name}()" if route else f"{entry.name}()"
            self._emit(Message("1", ACTOR, dst, label, "llamada", entry.id, "exacta", ()))
            prefix = "1"
            self._visit(entry, prefix, self.depth, [entry.id], start_frags)
            if _returns_value(self.flows.get(entry.id)):
                self._emit(Message("", dst, ACTOR, "retorna", "retorno", None, "exacta", ()))
        else:
            self.participant_of(entry)
            self._visit(entry, prefix, self.depth, [entry.id], start_frags)
        ordered = [self.participants[p] for p in self.order]
        externals = [p for p in ordered if p.id == EXTERNAL]
        ordered = [p for p in ordered if p.id != EXTERNAL] + externals
        return SequenceDiagram(
            entry=entry_id,
            participants=tuple(ordered),
            messages=tuple(self.messages),
            fragments=tuple(sorted(self.fragments.values(), key=lambda f: f.id)),
            truncated=self.truncated,
        )

    def _emit(self, msg: Message) -> bool:
        if len(self.messages) >= self.max_messages:
            self.truncated = True
            return False
        self.messages.append(msg)
        return True

    def _visit(
        self, sym: Symbol, prefix: str, depth: int, stack: list[str], frags: tuple[str, ...]
    ) -> None:
        src = self.participant_of(sym)
        for n, call in enumerate(self.calls.get(sym.id, []), start=1):
            number = f"{prefix}.{n}" if prefix else str(n)
            chain = self._fragments_for(sym, call.context, frags)
            if not self._message_for(sym, src, call, number, depth, stack, chain):
                return

    def _message_for(
        self,
        caller: Symbol,
        src: str,
        call: Call,
        number: str,
        depth: int,
        stack: list[str],
        chain: tuple[str, ...],
    ) -> bool:
        target = self.by_id.get(call.resolved_id) if call.resolved_id else None
        label = f"{call.callee_text}()"
        # Interfaz con varias implementaciones: alt "posible implementación".
        if call.candidates and (target is None or len(call.candidates) > 1):
            impls = [self.by_id[c] for c in call.candidates if c in self.by_id]
            if call.confidence == "ambigua" or len(impls) > 1:
                title = "ambigua" if call.confidence == "ambigua" else "posible implementación"
                for i, impl in enumerate(impls):
                    fid = f"{caller.id}:impl:{call.id}:{i}"
                    parent = chain[-1] if chain else None
                    if fid not in self.fragments:
                        owner = self._owner(impl)
                        name = owner.name if owner else posixpath.basename(impl.file)
                        self.fragments[fid] = Fragment(fid, "impl", f"{title}: {name}", parent)
                    dst = self.participant_of(impl)
                    ok = self._emit(
                        Message(f"{number}{chr(97 + i)}", src, dst, label, "llamada", impl.id,
                                call.confidence, (*chain, fid))
                    )
                    if not ok:
                        return False
                return True
        if target is None:
            self._add_participant(Participant(EXTERNAL, "Externo", "externo"))
            kind = "llamada"
            if call.id in self.new_calls:
                label, kind = f"new {call.callee_text}()", "crear"
            return self._emit(
                Message(number, src, EXTERNAL, label, kind, None, call.confidence, chain, True)
            )
        if target.kind in ("class", "interface"):
            dst = self.participant_of(target)
            label = f"new {target.name}()"
            return self._emit(
                Message(number, src, dst, label, "crear", None, call.confidence, chain)
            )
        dst = self.participant_of(target)
        owner = self._owner(target)
        if owner is not None and (target.name in CONSTRUCTORS or target.name == owner.name):
            label = f"new {owner.name}()"
        if target.id in stack:
            return self._emit(
                Message(number, src, dst, f"{label} (recursivo)", "recursivo", target.id,
                        call.confidence, chain)
            )
        if not self._emit(
            Message(number, src, dst, label, "llamada", target.id, call.confidence, chain)
        ):
            return False
        if depth > 1:
            self._visit(target, number, depth - 1, [*stack, target.id], chain)
        if _returns_value(self.flows.get(target.id)):
            return self._emit(Message("", dst, src, "retorna", "retorno", None, "exacta", chain))
        return True


def _renumber(messages: list[Message]) -> tuple[Message, ...]:
    """Vuelve a numerar 1, 1.1, 1.2… sin huecos (al quitar mensajes externos)."""
    new_of: dict[str, str] = {"": ""}
    counters: dict[str, int] = {}
    out: list[Message] = []
    for m in messages:
        if not m.number:
            out.append(m)
            continue
        base = m.number.rstrip("abcdefghijklmnopqrstuvwxyz")
        suffix = m.number[len(base) :]
        parent_old = base.rsplit(".", 1)[0] if "." in base else ""
        parent_new = new_of.get(parent_old, parent_old)
        if base in new_of and suffix:
            number = new_of[base]  # otra alternativa de la misma llamada (1.2a, 1.2b)
        else:
            counters[parent_new] = counters.get(parent_new, 0) + 1
            count = counters[parent_new]
            number = f"{parent_new}.{count}" if parent_new else str(count)
            new_of[base] = number
        out.append(replace(m, number=number + suffix))
    return tuple(out)


def without_externals(diagram: SequenceDiagram) -> SequenceDiagram:
    """La misma secuencia sin las llamadas externas (para el botón del visor)."""
    messages = _renumber([m for m in diagram.messages if not m.external])
    used = {m.src for m in messages} | {m.dst for m in messages}
    used_frags = {f for m in messages for f in m.fragments}
    return SequenceDiagram(
        entry=diagram.entry,
        participants=tuple(p for p in diagram.participants if p.id in used),
        messages=messages,
        fragments=tuple(f for f in diagram.fragments if f.id in used_frags),
        truncated=diagram.truncated,
    )


def has_project_calls(project: Project, symbol_id: str) -> bool:
    by_id = {s.id: s for s in project.symbols}
    for c in project.calls:
        if c.caller_id != symbol_id:
            continue
        if c.resolved_id and by_id.get(c.resolved_id) and by_id[c.resolved_id].kind in FUNC_KINDS:
            return True
        if c.candidates:
            return True
    return False


def build_sequence(
    project: Project,
    flows: dict[str, FlowGraph],
    entry_id: str,
    depth: int = 4,
    routes: dict[str, str] | None = None,
    new_calls: set[str] | frozenset[str] = frozenset(),
) -> SequenceDiagram:
    return SequenceBuilder(project, flows, routes, depth, new_calls=new_calls).build(entry_id)
