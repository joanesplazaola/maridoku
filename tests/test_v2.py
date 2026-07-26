from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from murdoku_v2.clue_catalog import CLUE_SPECS, catalog_json
from murdoku_v2.object_catalog import OBJECT_CATALOG, catalog_json as object_catalog_json, footprint_kind


PROJECT = Path(__file__).resolve().parents[1]


def test_catalogs_define_the_public_contract() -> None:
    assert len(CLUE_SPECS) == len(catalog_json()) == 22
    assert len(OBJECT_CATALOG) == len(object_catalog_json()) == 11
    assert OBJECT_CATALOG["table"].footprints == ("1x1", "1x2")
    assert OBJECT_CATALOG["bed"].footprints == ("1x2",)
    assert OBJECT_CATALOG["counter"].footprints == ("1x2", "L3")
    assert footprint_kind([(0, 0), (0, 1), (1, 0)]) == "L3"
    assert footprint_kind([(0, 0), (0, 2)]) == "custom"


def test_ortools_matches_all_reference_cases() -> None:
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    for puzzle_path in sorted((PROJECT / "examples").glob("*/puzzle.json")):
        puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
        solution = json.loads((puzzle_path.parent / "solution.json").read_text(encoding="utf-8"))
        expected = {
            character: (position["row"], position["column"])
            for character, position in solution["positions"].items()
        }
        result = ORToolsSolver().solve(puzzle, limit=2)
        assert result.available and result.unique
        assert result.solutions == [expected]


def test_ortools_scales_to_twelve_characters() -> None:
    from murdoku_v2.scaling import expected_scaling_solution, make_scaling_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    result = ORToolsSolver().solve(make_scaling_puzzle(12), limit=2)
    assert result.unique
    assert result.solutions == [expected_scaling_solution(12)]


def test_scaling_board_and_target_are_parameterized() -> None:
    from murdoku_v2.scaling import make_scaling_board, make_scaling_characters, make_scaling_target

    for size in (6, 8, 10):
        characters = make_scaling_characters(size)
        target = make_scaling_target(size, seed=73)
        assert len(characters) == len(target) == size
        assert {row for row, _ in target.values()} == set(range(size))
        assert {column for _, column in target.values()} == set(range(size))
        board = make_scaling_board(size, seed=73)
        assert board["rows"] == board["columns"] == size
        assert sum(len(room["cells"]) for room in board["rooms"]) == size * size
        assert board == make_scaling_board(size, seed=73)


def test_scaling_candidate_pools_are_true_and_diverse() -> None:
    from murdoku_v2.scaling import make_scaling_candidate_pools, make_scaling_puzzle, make_scaling_target
    from murdoku_v2.validator import _matches_statement

    puzzle = make_scaling_puzzle(8, seed=91)
    target = make_scaling_target(8, seed=91)
    pools = make_scaling_candidate_pools(puzzle, target)
    assert all(len(pool) >= 11 for pool in pools.values())
    assert all(
        _matches_statement(statement, target, puzzle)
        for pool in pools.values()
        for statement in pool
    )
    assert {"coordinate", "room_exact", "relative_distance", "relative_order"} <= {
        statement["family"] for pool in pools.values() for statement in pool
    }


def test_generate_scale_writes_a_valid_large_case(tmp_path: Path) -> None:
    from murdoku_v2.scaling import generate_scaling_case

    result = generate_scaling_case(10, 9001, tmp_path)
    objects = {obj["type"]: obj for obj in result["puzzle"]["board"]["objects"]}
    assert len(objects) >= 9
    assert len(objects["rug"]["cells"]) == 3
    assert len(objects["bed"]["cells"]) == 2
    assert len(objects["counter"]["cells"]) == 3
    assert result["diagnostics"]["exact_validation"]["unique"]
    assert result["diagnostics"]["all_suspect_clues_necessary"]
    assert result["diagnostics"]["editorial_audit"]["accepted"]
    assert result["diagnostics"]["editorial_audit"]["warnings"] == []
    assert result["explanation"]["method"] == "incremental_cp_sat"
    assert result["explanation"]["unique"]
    assert result["manifest"]["editorial_status"] == "draft"
    assert {
        statement["family"]
        for card in result["puzzle"]["cards"]
        for statement in card["statements"]
        if card["role"] == "suspect"
    } == {"coordinate", "relative_distance", "relative_order"}
    assert all((tmp_path / f"{name}.json").exists() for name in (
        "puzzle", "solution", "diagnostics", "explanation", "generation_report", "manifest"
    ))


def test_scaling_generator_retries_unplaceable_furniture(tmp_path: Path) -> None:
    from murdoku_v2.scaling import generate_scaling_case

    result = generate_scaling_case(6, 7, tmp_path)
    assert result["diagnostics"]["effective_seed"] > 7
    assert 7 in result["diagnostics"]["rejected_target_seeds"]


def test_scaling_regression_reports_acceptance(tmp_path: Path) -> None:
    from murdoku_v2.scaling import run_scaling_generation_regression

    report = run_scaling_generation_regression(
        [6], start_seed=1, count_per_size=1, budget_seconds=30,
        output=tmp_path / "report.json",
    )
    assert report["summary"]["accepted"]


def test_editorial_manifest_can_be_approved_then_retired(tmp_path: Path) -> None:
    from murdoku_v2.publication import set_editorial_status
    from murdoku_v2.scaling import generate_scaling_case

    generate_scaling_case(6, 1, tmp_path)
    manifest_path = tmp_path / "manifest.json"
    assert set_editorial_status(manifest_path, "approved")["editorial_status"] == "approved"
    assert set_editorial_status(manifest_path, "retired")["editorial_status"] == "retired"
    with pytest.raises(ValueError):
        set_editorial_status(manifest_path, "approved")


def test_render_writes_an_interactive_printable_html(tmp_path: Path) -> None:
    from murdoku_v2.render import render_file

    output = tmp_path / "puzzle.html"
    render_file(PROJECT / "examples/board_restaurant/puzzle.json", output)
    html = output.read_text(encoding="utf-8")
    assert 'class="sheet"' in html
    assert '<table aria-label="Tablero" style="--cols:' in html
    assert 'class="game-toolbar"' in html
    assert 'id="puzzle-data"' in html
    assert "localStorage.setItem" in html
    assert "data:image/webp;base64," in html
    assert 'class="furniture-layer"' in html
    assert "--object-width:2" in html
    assert ">1.1<" not in html
    assert "Alicia estaba 1 columna" not in html
    assert "Estaba 1 columna al este de Elena." in html


def test_pydantic_contract_rejects_invalid_content() -> None:
    import copy

    from murdoku_v2.models import validate_puzzle

    puzzle = json.loads((PROJECT / "examples/board_restaurant/puzzle.json").read_text(encoding="utf-8"))
    wrong_subject = copy.deepcopy(puzzle)
    wrong_subject["cards"][0]["statements"][0]["args"]["character"] = wrong_subject["cards"][1]["character"]
    with pytest.raises(ValidationError):
        validate_puzzle(wrong_subject)

    wrong_footprint = copy.deepcopy(puzzle)
    wrong_footprint["board"]["objects"][0]["cells"] = [[0, 0], [0, 2]]
    with pytest.raises(ValidationError):
        validate_puzzle(wrong_footprint)


def test_solver_registry_uses_cpsat() -> None:
    from murdoku_v2.solvers.registry import get_solver

    assert get_solver("auto").name == "ortools-cp-sat"
    assert get_solver("ortools").name == "ortools-cp-sat"
    with pytest.raises(ValueError, match="Solucionador desconocido"):
        get_solver("z3")
