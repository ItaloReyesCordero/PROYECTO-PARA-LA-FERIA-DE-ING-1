"""Skill de Desglosa para asistentes de IA (Claude Code y compatibles).

`desglosa skill install` copia el SKILL.md empaquetado a una carpeta de skills.
No usa la red y solo escribe dentro de `<carpeta>/desglosa/`.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

SKILL_NAME = "desglosa"


def skill_text() -> str:
    """Contenido del SKILL.md que viene con esta versión de Desglosa."""
    return resources.files(__name__).joinpath("SKILL.md").read_text(encoding="utf-8")


def default_skills_dir(project: bool, cwd: Path | None = None, home: Path | None = None) -> Path:
    """Carpeta de skills de Claude Code: la del usuario o la del proyecto actual."""
    if project:
        return (cwd or Path.cwd()) / ".claude" / "skills"
    return (home or Path.home()) / ".claude" / "skills"


class SkillExistsError(FileExistsError):
    """Ya hay un SKILL.md distinto en el destino y no se pidió reemplazarlo."""


def install(skills_dir: Path, force: bool = False) -> tuple[Path, str]:
    """Escribe `<skills_dir>/desglosa/SKILL.md`.

    Devuelve la ruta y el estado: "creada", "actualizada" o "sin cambios". Sin
    `force` no reemplaza un SKILL.md distinto (podría tener cambios del usuario).
    """
    target = skills_dir / SKILL_NAME / "SKILL.md"
    text = skill_text()
    if target.exists():
        if target.read_text(encoding="utf-8") == text:
            return target, "sin cambios"
        if not force:
            raise SkillExistsError(str(target))
        state = "actualizada"
    else:
        state = "creada"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target, state
