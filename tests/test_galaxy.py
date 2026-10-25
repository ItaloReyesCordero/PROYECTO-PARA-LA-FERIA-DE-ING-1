"""Vista galaxia: subsistemas (Louvain), nombres sin IA y layout sin encimarse."""

from __future__ import annotations

import math
from pathlib import Path

from desglosa.galaxy import build_galaxy, community_label, louvain
from desglosa.pipeline import analyze
from tests.conftest import needs_grammars

ROOT = Path(__file__).resolve().parent.parent


def _clique(prefix: str, n: int) -> dict[tuple[str, str], float]:
    names = [f"{prefix}{i}" for i in range(n)]
    return {(a, b): 1.0 for i, a in enumerate(names) for b in names[i + 1 :]}


def test_louvain_separates_two_groups_joined_by_one_edge():
    weights = {**_clique("a", 5), **_clique("b", 5), ("a0", "b0"): 1.0}
    nodes = sorted({n for pair in weights for n in pair})
    comm = louvain(nodes, weights)
    assert len({comm[f"a{i}"] for i in range(5)}) == 1
    assert len({comm[f"b{i}"] for i in range(5)}) == 1
    assert comm["a0"] != comm["b0"]
    assert louvain(nodes, weights) == comm  # determinista


def test_community_labels_without_ai():
    assert community_label(["app/Models/A.php", "app/Models/B.php", "x/C.php"]) == "app/Models"
    assert community_label(  # ninguna carpeta llega a la mitad: se nombran las dos mayores
        ["tests/queries/a.py", "tests/queries/b.py", "tests/aggregation/c.py",
         "tests/aggregation/d.py", "tests/x/e.py"]
    ) == "tests/{aggregation, queries}"
    assert community_label(
        ["db/models/a.py", "db/models/b.py", "db/models/fields/c.py", "db/models/fields/d.py",
         "other/e.py"]
    ) == "db/models (+fields)"


@needs_grammars
def test_galaxy_of_real_project_has_no_overlapping_clusters():
    g = build_galaxy(analyze(ROOT / "src" / "desglosa").project)
    assert g is not None and g["nodes"] and g["communities"]
    comms = g["communities"]
    for i, (_, _, _, x1, y1, r1) in enumerate(comms):
        for _, _, _, x2, y2, r2 in comms[i + 1 :]:
            assert math.hypot(x1 - x2, y1 - y2) >= r1 + r2 - 0.5
    for _, x, y, r, *_ in g["nodes"]:
        assert x - r >= 0 and x + r <= g["w"] and y - r >= 0 and y + r <= g["h"]
    assert len(g["gods"]) <= 10


@needs_grammars
def test_galaxy_is_in_analyze_html_but_not_in_flow_html(tmp_path):
    from desglosa import cli
    from tests.test_html import _data

    out = tmp_path / "a.html"
    assert cli.main(["analyze", str(ROOT / "examples" / "laravel-mini"), "-o", str(out)]) == 0
    data = _data(out.read_text(encoding="utf-8"))
    nodes = {n[0]: n for n in data["galaxy"]["nodes"]}
    assert nodes["app/Services/FacturacionService.php"][7].startswith("#/mapa/")
    flow = tmp_path / "f.html"
    cli.main(["flow", str(ROOT / "examples" / "gps-c"), "gps.c:main", "-o", str(flow)])
    assert _data(flow.read_text(encoding="utf-8"))["galaxy"] is None


def test_tiny_project_has_no_galaxy():
    from desglosa.ir import Project

    assert build_galaxy(Project("p")) is None
