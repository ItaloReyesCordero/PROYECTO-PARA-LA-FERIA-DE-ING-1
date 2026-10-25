from __future__ import annotations

import re
from pathlib import Path

import pytest

from desglosa.cli import EXIT_OK, EXIT_USAGE, build_parser, main
from desglosa.skill import SkillExistsError, default_skills_dir, install, skill_text

ROOT = Path(__file__).resolve().parent.parent


def test_skill_has_frontmatter():
    text = skill_text()
    head = text.split("---")[1]
    assert re.search(r"^name: desglosa$", head, re.M)
    assert re.search(r"^description: .{50,}", head, re.M)


def test_skill_only_mentions_real_commands():
    commands = set(build_parser()._subparsers._group_actions[0].choices)
    used = set(re.findall(r"`desglosa ([a-z][a-z-]*)", skill_text()))
    assert used <= commands
    assert {"explain", "path", "buscar", "analyze", "setup"} <= used


def test_install_creates_then_reports_no_changes(tmp_path):
    target, state = install(tmp_path)
    assert state == "creada"
    assert target == tmp_path / "desglosa" / "SKILL.md"
    assert target.read_text(encoding="utf-8") == skill_text()
    assert install(tmp_path) == (target, "sin cambios")


def test_install_does_not_overwrite_user_changes_without_force(tmp_path):
    target, _ = install(tmp_path)
    target.write_text("mis cambios", encoding="utf-8")
    with pytest.raises(SkillExistsError):
        install(tmp_path)
    assert target.read_text(encoding="utf-8") == "mis cambios"
    assert install(tmp_path, force=True) == (target, "actualizada")
    assert target.read_text(encoding="utf-8") == skill_text()


def test_default_dirs(tmp_path):
    assert default_skills_dir(False, home=tmp_path) == tmp_path / ".claude" / "skills"
    assert default_skills_dir(True, cwd=tmp_path) == tmp_path / ".claude" / "skills"


def test_cli_install_and_conflict(tmp_path, capsys):
    assert main(["skill", "install", "--dir", str(tmp_path)]) == EXIT_OK
    assert "Skill creada" in capsys.readouterr().out
    (tmp_path / "desglosa" / "SKILL.md").write_text("otro", encoding="utf-8")
    assert main(["skill", "install", "--dir", str(tmp_path)]) == EXIT_USAGE
    assert "--force" in capsys.readouterr().err
    assert main(["skill", "install", "--dir", str(tmp_path), "--force"]) == EXIT_OK


def test_cli_show_and_bare_skill(capsys):
    assert main(["skill", "show"]) == EXIT_OK
    assert capsys.readouterr().out == skill_text()
    assert main(["skill"]) == EXIT_USAGE


def test_cli_project_and_dir_are_exclusive(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["skill", "install", "--project", "--dir", str(tmp_path)])
    assert exc.value.code == EXIT_USAGE


def test_action_never_interpolates_inside_run_scripts():
    """Las entradas de la Action pasan por `env:`; un `${{ }}` dentro de `run:` permitiría
    inyectar comandos con un valor como `$(curl …)`."""
    lines = (ROOT / "action.yml").read_text(encoding="utf-8").splitlines()
    in_run, run_indent = False, 0
    for line in lines:
        indent = len(line) - len(line.lstrip())
        if in_run and line.strip() and indent <= run_indent:
            in_run = False
        stripped = line.strip()
        if stripped.startswith("run:"):
            assert "${{" not in stripped, line
            in_run, run_indent = True, indent
        elif in_run:
            assert "${{" not in line, line
