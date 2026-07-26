from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from murdoku_v2.clue_catalog import CLUE_SPECS, catalog_json
from murdoku_v2.object_catalog import OBJECT_CATALOG, catalog_json as object_catalog_json, footprint_kind


PROJECT = Path(__file__).resolve().parents[1]


def test_catalogs_define_the_public_contract() -> None:
    from murdoku_v2.text_catalog import text_catalog

    assert len(CLUE_SPECS) == len(catalog_json()) == 22
    assert len(OBJECT_CATALOG) == len(object_catalog_json()) == 11
    assert OBJECT_CATALOG["table"].footprints == ("1x1", "1x2")
    assert OBJECT_CATALOG["bed"].footprints == ("1x2",)
    assert OBJECT_CATALOG["counter"].footprints == ("1x2", "L3")
    assert footprint_kind([(0, 0), (0, 1), (1, 0)]) == "L3"
    assert footprint_kind([(0, 0), (0, 2)]) == "custom"
    assert set(text_catalog("es")) == set(text_catalog("en"))


def test_ortools_matches_all_reference_cases() -> None:
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    paths = [
        *sorted((PROJECT / "examples").glob("*/puzzle.json")),
        PROJECT / "examples/board_restaurant/case.json",
    ]
    for puzzle_path in paths:
        puzzle = load_puzzle(puzzle_path)
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
    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.scaling import make_scaling_puzzle, make_scaling_target
    from murdoku_v2.validator import matches_statement

    puzzle = make_scaling_puzzle(8, seed=91)
    target = make_scaling_target(8, seed=91)
    pools = candidate_pools(puzzle, target)
    assert all(len(pool) >= 11 for pool in pools.values())
    assert all(
        matches_statement(statement, target, puzzle)
        for pool in pools.values()
        for statement in pool
    )
    assert {"coordinate", "room_exact", "relative_distance", "relative_order"} <= {
        statement["family"] for pool in pools.values() for statement in pool
    }


def test_reference_case_generates_reproducible_true_candidates() -> None:
    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.validator import matches_statement

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    target = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    pools = candidate_pools(puzzle, target)

    assert pools == candidate_pools(puzzle, target)
    assert set(pools) == {
        character["id"] for character in puzzle["characters"] if character["role"] == "suspect"
    }
    assert all(
        matches_statement(statement, target, puzzle)
        for pool in pools.values()
        for statement in pool
    )
    assert {"object_line", "room_exact", "room_relation", "relative_distance"} <= {
        statement["family"] for pool in pools.values() for statement in pool
    }
    for card in puzzle["cards"]:
        if card["role"] == "victim":
            continue
        authored = card["statements"][0]
        assert any(
            candidate["type"] == authored["type"] and candidate["args"] == authored["args"]
            for candidate in pools[card["character"]]
        )

    invalid = dict(target)
    invalid.pop(puzzle["victim"])
    with pytest.raises(ValueError, match="exactamente los personajes"):
        candidate_pools(puzzle, invalid)


def test_reference_case_selects_an_editorial_clue_set() -> None:
    import copy

    from murdoku_v2.editorial import audit_puzzle
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.selection import select_clues
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    target = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    selection = select_clues(puzzle, target)
    statements = selection["statements"]

    assert selection == select_clues(puzzle, target)
    assert len(statements) == len(puzzle["characters"]) - 1
    assert selection["iterations"] <= 40
    assert selection["witnesses"] <= 50
    assert selection["human_steps"] > 0
    assert {"clue_anchor", "row_matching", "column_matching"} <= set(selection["human_techniques"])
    assert selection["human_complexity"]["branching_points"] == 0
    assert not selection["human_complexity"]["calibrated"]
    assert len(selection["families"]) >= 4
    assert selection["directional"] <= 1
    assert sum(statement["family"].startswith(("object_", "room_")) for statement in statements) >= 4
    assert all(statement["family"] != "coordinate" for statement in statements)
    assert all("otra altura" not in statement["text"] and "otro lado" not in statement["text"] for statement in statements)
    published = {
        card["character"]: card["statements"][0]
        for card in puzzle["cards"]
        if card["role"] == "suspect"
    }
    assert all(
        {
            "type": statement["type"],
            "args": statement["args"],
            "text": statement["text"],
        } == {
            "type": published[statement["args"]["character"]]["type"],
            "args": published[statement["args"]["character"]]["args"],
            "text": published[statement["args"]["character"]]["text"],
        }
        for statement in statements
    )

    victim_statement = next(card for card in puzzle["cards"] if card["role"] == "victim")["statements"][0]
    active = (victim_statement, *statements)
    solver = ORToolsSolver()
    exact = solver.solve(puzzle, limit=2, base_statements=active)
    assert exact.unique and exact.solutions == [target]
    assert all(
        len(solver.solve(
            puzzle,
            limit=2,
            base_statements=tuple(item for item in active if item["id"] != statement["id"]),
        ).solutions) > 1
        for statement in statements
    )

    selected_puzzle = copy.deepcopy(puzzle)
    by_character = {statement["args"]["character"]: statement for statement in statements}
    for card in selected_puzzle["cards"]:
        if card["role"] == "suspect":
            card["statements"] = [by_character[card["character"]]]
    assert audit_puzzle(selected_puzzle)["warnings"] == []


def test_reference_case_has_a_human_deduction_route() -> None:
    import copy

    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    result = solve_human(puzzle)

    assert result["solved"]
    assert result["positions"] == expected
    assert result["difficulty"] == "unrated"
    assert {"clue_anchor", "binary_relation", "victim_companion"} <= set(result["techniques"])
    complexity = result["complexity"]
    assert complexity["deduction_steps"] == result["step_count"]
    assert complexity["propagation_rounds"] >= 1
    assert complexity["branching_points"] == 0
    assert complexity["hardest_technique"] in result["techniques"]
    assert complexity["hardest_level"] == 3
    assert sum(complexity["technique_counts"].values()) == result["step_count"]
    assert not complexity["calibrated"]

    unsupported = copy.deepcopy(puzzle)
    unsupported["cards"][0]["statements"][0]["type"] = "room_population"
    assert solve_human(unsupported)["reason"] == "unsupported_clues"


def test_reference_scene_generates_a_complete_variant_without_a_solution_input() -> None:
    from murdoku_v2.generation import generate_variant
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    base = load_puzzle(case_path)
    published_solution = json.loads(
        (case_path.parent / "solution.json").read_text(encoding="utf-8")
    )
    result = generate_variant(base, 20260726)
    generated = result["puzzle"]
    target = {
        character: (position["row"], position["column"])
        for character, position in result["solution"]["positions"].items()
    }

    assert result == generate_variant(base, 20260726)
    assert generated["board"] == base["board"]
    assert target != {
        character: (position["row"], position["column"])
        for character, position in published_solution["positions"].items()
    }
    assert result["solution"]["murderer"] == "diego"
    assert result["diagnostics"]["target_attempt"] <= 20
    assert result["diagnostics"]["selector_iterations"] <= 40
    assert result["diagnostics"]["directional"] <= 1
    assert len(result["diagnostics"]["families"]) >= 4
    assert result["diagnostics"]["human_steps"] > 0
    assert result["diagnostics"]["human_complexity"]["branching_points"] == 0

    solver = ORToolsSolver()
    exact = solver.solve(generated, limit=2)
    assert exact.unique and exact.solutions == [target]
    assert all(
        len(solver.solve(
            generated,
            limit=2,
            exclude_statement_id=statement["id"],
        ).solutions) > 1
        for card in generated["cards"]
        if card["role"] == "suspect"
        for statement in card["statements"]
    )


def test_reference_scene_generation_smoke() -> None:
    from murdoku_v2.generation import generate_variant
    from murdoku_v2.models import load_puzzle

    base = load_puzzle(PROJECT / "examples/board_restaurant/case.json")
    variants = [generate_variant(base, seed) for seed in (1, 2, 3)]
    targets = [
        tuple(
            (character, position["row"], position["column"])
            for character, position in variant["solution"]["positions"].items()
        )
        for variant in variants
    ]

    assert len(set(targets)) == len(variants)
    assert all(variant["puzzle"]["board"] == base["board"] for variant in variants)
    assert all(variant["diagnostics"]["exact_unique"] for variant in variants)
    assert all(variant["diagnostics"]["target_attempt"] <= 50 for variant in variants)
    assert all(
        variant["diagnostics"]["human_complexity"]["propagation_rounds"] >= 1
        for variant in variants
    )


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
    assert result["manifest"]["text_locale"] == "es"
    assert result["manifest"]["text_version"] == 1
    families = {
        statement["family"]
        for card in result["puzzle"]["cards"]
        for statement in card["statements"]
        if card["role"] == "suspect"
    }
    assert {"coordinate", "relative_distance", "relative_order"} <= families
    assert len(families) >= 4
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
    render_file(PROJECT / "examples/board_restaurant/case.json", output)
    html = output.read_text(encoding="utf-8")
    assert 'class="sheet"' in html
    assert '<table aria-label="Tablero" style="--cols:' in html
    assert 'class="game-toolbar"' in html
    assert 'data-tool="candidate"' in html
    assert "candidate-notes" in html
    assert 'id="puzzle-data"' in html
    assert "localStorage.setItem" in html
    assert "durationSeconds" in html
    assert "data:image/webp;base64," in html
    assert 'class="furniture-layer"' in html
    assert "--object-width:2" in html
    assert ">1.1<" not in html
    assert "Alicia estaba en el comedor" not in html
    assert "Estaba en el comedor." in html


def test_site_builder_publishes_only_reference_cases_without_solutions(tmp_path: Path) -> None:
    from murdoku_v2.site_builder import build_site

    result = build_site(tmp_path)
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    level = (tmp_path / "levels/001.html").read_text(encoding="utf-8")
    assert result["levels"] == 1
    assert "Dificultad" in index
    assert "Fácil" in index
    assert "Último servicio" in index
    assert "V · VÍCTIMA" in level
    assert 'data-tool="cross"' in level
    assert 'data-tool="candidate"' in level
    assert 'data-tool="erase"' in level
    assert (tmp_path / "levels/001.html").exists()
    assert not list(tmp_path.rglob("solution.json"))


def test_reference_case_meets_editorial_acceptance() -> None:
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    puzzle = load_puzzle(PROJECT / "examples/board_restaurant/case.json")
    solution = json.loads((PROJECT / "examples/board_restaurant/solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    suspect_statements = [
        statement
        for card in puzzle["cards"]
        if card["role"] == "suspect"
        for statement in card["statements"]
    ]
    direction_families = {"relative_order", "relative_distance", "coordinate"}
    families = {statement["family"] for statement in suspect_statements}
    solver = ORToolsSolver()

    result = solver.solve(puzzle, limit=2)
    assert result.unique and result.solutions == [expected]
    assert all(room["id"] != "crime_room" for room in puzzle["board"]["rooms"])
    assert all(len(card["statements"]) == 1 for card in puzzle["cards"])
    assert sum(statement["family"] in direction_families for statement in suspect_statements) <= 1
    assert len(families) >= 4
    assert all(
        len(solver.solve(puzzle, limit=2, exclude_statement_id=statement["id"]).solutions) > 1
        for statement in suspect_statements
    )


def test_reference_case_composes_a_fixed_scene() -> None:
    from murdoku_v2.models import load_puzzle

    case_path = PROJECT / "examples/board_restaurant/case.json"
    source = json.loads(case_path.read_text(encoding="utf-8"))
    scene = json.loads((case_path.parent / source["scene"]).read_text(encoding="utf-8"))
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    solution["positions"]["alicia"]["row"] = 0

    assert "board" not in source
    assert load_puzzle(case_path)["board"] == scene
    assert "board" not in solution


def test_pydantic_contract_rejects_invalid_content() -> None:
    import copy

    from murdoku_v2.models import load_puzzle, validate_puzzle

    puzzle = load_puzzle(PROJECT / "examples/board_restaurant/case.json")
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
