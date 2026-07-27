from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from murdoku_v2.clue_catalog import CLUE_SPECS, catalog_json
from murdoku_v2.object_catalog import OBJECT_CATALOG, catalog_json as object_catalog_json, footprint_kind


PROJECT = Path(__file__).resolve().parents[1]


def test_catalogs_define_the_public_contract() -> None:
    from murdoku_v2.text_catalog import text_catalog

    assert len(CLUE_SPECS) == len(catalog_json()) == 28
    assert len(OBJECT_CATALOG) == len(object_catalog_json()) == 12
    assert OBJECT_CATALOG["table"].footprints == ("1x1", "1x2")
    assert OBJECT_CATALOG["dining_table"].footprints == ("1x2",)
    assert OBJECT_CATALOG["bed"].footprints == ("1x2",)
    assert OBJECT_CATALOG["counter"].footprints == ("1x2", "L3")
    assert OBJECT_CATALOG["flag"].occupiable
    assert footprint_kind([(0, 0), (0, 1), (1, 0)]) == "L3"
    assert footprint_kind([(0, 0), (0, 2)]) == "custom"
    assert set(text_catalog("es")) == set(text_catalog("en"))


def test_visual_assets_have_tracked_provenance() -> None:
    manifest = json.loads((PROJECT / "docs/assets-manifest.json").read_text(encoding="utf-8"))
    tracked = {entry["path"]: entry for entry in manifest}
    actual = {
        str(path.relative_to(PROJECT))
        for path in (PROJECT / "src/murdoku_v2/assets").rglob("*.webp")
    }
    assert set(tracked) == actual
    for relative_path, entry in tracked.items():
        assert hashlib.sha256((PROJECT / relative_path).read_bytes()).hexdigest() == entry["sha256"]
        assert entry["origin_commit"]
        assert entry["source"]


def test_versioned_catalog_passes_the_release_contract() -> None:
    from murdoku_v2.editorial import audit_puzzle
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    manifests = sorted((PROJECT / "catalog/candidates").glob("*/manifest.json"))
    assert len(manifests) == 13
    statuses = []
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        statuses.append(manifest["editorial_status"])
        puzzle_path = manifest_path.parent / manifest["public_puzzle"]["path"]
        solution_path = manifest_path.parent / manifest["private_solution"]["path"]
        puzzle = load_puzzle(puzzle_path)
        solution = json.loads(solution_path.read_text(encoding="utf-8"))
        expected = {
            character: (position["row"], position["column"])
            for character, position in solution["positions"].items()
        }
        assert hashlib.sha256(puzzle_path.read_bytes()).hexdigest() == manifest["public_puzzle"]["sha256"]
        assert hashlib.sha256(solution_path.read_bytes()).hexdigest() == manifest["private_solution"]["sha256"]
        assert audit_puzzle(puzzle)["warnings"] == []
        assert ORToolsSolver().solve(puzzle, limit=2).solutions == [expected]
        assert solve_human(puzzle)["positions"] == expected
    assert statuses.count("approved") == 12
    assert statuses.count("retired") == 1


def test_ortools_matches_all_reference_cases() -> None:
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    paths = [
        *sorted((PROJECT / "examples").glob("*/puzzle.json")),
        *sorted((PROJECT / "examples").glob("*/case.json")),
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


def test_engine_and_renderer_cover_sizes_five_to_sixteen() -> None:
    from murdoku_v2.render import render_html
    from murdoku_v2.scaling import expected_scaling_solution, make_scaling_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    for size in range(5, 17):
        puzzle = make_scaling_puzzle(size)
        result = ORToolsSolver().solve(puzzle, limit=2)
        assert result.unique
        assert result.solutions == [expected_scaling_solution(size)]
        assert f"--cols:{size};--rows:{size}" in render_html(puzzle)


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
    generated_types = {
        statement["type"] for pool in pools.values() for statement in pool
    }
    assert {"not_adjacent_to_wall", "in_room_corner", "room_disjunction"} <= generated_types
    assert all(
        len(pool) == len({
            (statement["type"], json.dumps(statement["args"], sort_keys=True))
            for statement in pool
        })
        for pool in pools.values()
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
    assert any(family.startswith("room_") for family in selection["families"])
    assert any(family in {"room_relation", "relative_diagonal", "relative_distance", "relative_order"} for family in selection["families"])
    assert sum(statement["family"].startswith(("object_", "room_")) for statement in statements) >= 4
    assert max(
        sum(candidate["type"] == statement["type"] for candidate in statements)
        for statement in statements
    ) <= 2
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
    assert result["difficulty"]["label"] == "easy"
    assert result["difficulty"]["calibration"] == "technical_estimate_not_human_calibrated"
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
    unsupported["cards"][0]["statements"][0]["type"] = "diagonal"
    assert solve_human(unsupported)["reason"] == "unsupported_clues"


def test_human_propagates_room_count_clues() -> None:
    import copy

    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.clue_catalog import CLUE_SPECS
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    variants = (
        ("room_population", {"count": 2}),
        ("room_gender_count", {"gender": "man", "count": 1}),
        ("companion_gender_count", {"gender": "man", "count": 1}),
        ("alone_with_gender", {"gender": "man"}),
    )

    alicia_types = {
        statement["type"]
        for statement in candidate_pools(puzzle, expected)["alicia"]
    }
    assert {type_ for type_, _ in variants} <= alicia_types

    for type_, args in variants:
        candidate = copy.deepcopy(puzzle)
        card = next(card for card in candidate["cards"] if card["character"] == "alicia")
        card["statements"].append({
            "id": f"test-{type_}",
            "type": type_,
            "family": CLUE_SPECS[type_].family,
            "args": {"character": "alicia", **args},
            "text": "",
        })
        result = solve_human(candidate)
        assert result["solved"] and result["positions"] == expected
        assert result["complexity"]["technique_counts"]["room_count"] >= 1


def test_unique_adjacent_object_is_generated_and_solved_end_to_end() -> None:
    import copy

    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_hotel/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    statement = next(
        statement
        for statement in candidate_pools(puzzle, expected)["sergio"]
        if statement["type"] == "unique_adjacent_object"
        and statement["args"]["object_type"] == "bed"
    )
    candidate = copy.deepcopy(puzzle)
    card = next(card for card in candidate["cards"] if card["character"] == "sergio")
    statement["id"] = card["statements"][0]["id"]
    card["statements"] = [statement]

    exact = ORToolsSolver().solve(candidate, limit=2)
    human = solve_human(candidate)
    assert exact.unique and exact.solutions == [expected]
    assert human["solved"] and human["positions"] == expected
    assert "unique_object" in human["techniques"]


def test_same_diagonal_is_generated_and_solved_end_to_end() -> None:
    import copy

    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    statement = next(
        statement
        for statement in candidate_pools(puzzle, expected)["alicia"]
        if statement["type"] == "same_diagonal"
        and statement["args"]["reference"] == "carla"
    )
    candidate = copy.deepcopy(puzzle)
    card = next(card for card in candidate["cards"] if card["character"] == "alicia")
    statement["id"] = card["statements"][0]["id"]
    card["statements"] = [statement]

    exact = ORToolsSolver().solve(candidate, limit=2)
    human = solve_human(candidate)
    assert exact.unique and exact.solutions == [expected]
    assert human["solved"] and human["positions"] == expected
    assert "binary_relation" in human["techniques"]


def test_global_room_count_is_solved_and_rendered_end_to_end() -> None:
    import copy

    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle, validate_puzzle
    from murdoku_v2.render import render_html
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    puzzle["general_clues"] = [{
        "id": "general-dining",
        "type": "room_population_at_least",
        "family": "global_room",
        "args": {"room": "dining", "count": 2},
        "text": "Había al menos 2 personas en el comedor.",
    }]

    validate_puzzle(puzzle)
    exact = ORToolsSolver().solve(puzzle, limit=2)
    human = solve_human(puzzle)
    html = render_html(puzzle)
    assert exact.unique and exact.solutions == [expected]
    assert human["solved"] and human["positions"] == expected
    assert human["complexity"]["technique_counts"]["global_room_count"] >= 1
    assert 'class="general-clues"' in html
    assert "Había al menos 2 personas en el comedor." in html

    invalid = copy.deepcopy(puzzle)
    invalid["general_clues"][0]["args"]["character"] = "alicia"
    with pytest.raises(ValidationError):
        validate_puzzle(invalid)


def test_selector_can_require_a_necessary_global_clue() -> None:
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.selection import apply_clues, select_clues
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    puzzle["selection_profile"] = "global_room"
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }

    selection = select_clues(puzzle, expected)
    selected = apply_clues(puzzle, selection["statements"])
    assert len(selection["statements"]) == len(puzzle["characters"])
    assert selection["families"]["global_room"] == 1
    assert len(selected["general_clues"]) == 1
    assert selection["human_complexity"]["technique_counts"]["global_room_count"] >= 1

    solver = ORToolsSolver()
    exact = solver.solve(selected, limit=2)
    assert exact.unique and exact.solutions == [expected]
    assert all(
        len(solver.solve(
            selected,
            limit=2,
            exclude_statement_id=statement["id"],
        ).solutions) > 1
        for statement in (
            *selected["general_clues"],
            *(statement for card in selected["cards"] if card["role"] == "suspect" for statement in card["statements"]),
        )
    )


def test_negative_object_adjacency_is_solved_end_to_end() -> None:
    import copy

    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import load_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    case_path = PROJECT / "examples/board_restaurant/case.json"
    puzzle = load_puzzle(case_path)
    solution = json.loads((case_path.parent / "solution.json").read_text(encoding="utf-8"))
    expected = {
        character: (position["row"], position["column"])
        for character, position in solution["positions"].items()
    }
    statement = next(
        statement
        for statement in candidate_pools(puzzle, expected)["elena"]
        if statement["type"] == "not_adjacent_object"
        and statement["args"]["object_type"] == "plant"
    )
    candidate = copy.deepcopy(puzzle)
    card = next(card for card in candidate["cards"] if card["character"] == "elena")
    statement["id"] = card["statements"][0]["id"]
    card["statements"] = [statement]

    exact = ORToolsSolver().solve(candidate, limit=2)
    human = solve_human(candidate)
    assert exact.unique and exact.solutions == [expected]
    assert human["solved"] and human["positions"] == expected
    assert "clue_anchor" in human["techniques"]


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
    assert result["solution"]["murderer"] in {
        character["id"] for character in base["characters"] if character["role"] == "suspect"
    }
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


def test_second_scene_generation_is_varied_and_scene_independent() -> None:
    from murdoku_v2.generation import generate_variant
    from murdoku_v2.models import load_puzzle

    base = load_puzzle(PROJECT / "examples/board_hotel/case.json")
    result = generate_variant(base, 1)
    statements = [
        card["statements"][0]
        for card in result["puzzle"]["cards"]
        if card["role"] == "suspect"
    ]
    families = {statement["family"] for statement in statements}

    assert result["puzzle"]["board"] == base["board"]
    assert result["diagnostics"]["exact_unique"]
    assert result["diagnostics"]["human_complexity"]["branching_points"] == 0
    assert sum(statement["family"].startswith("object_") for statement in statements) <= 4
    assert any(family.startswith("room_") for family in families)
    assert any(family in {"room_relation", "relative_diagonal", "relative_distance", "relative_order"} for family in families)
    assert all(
        "única persona" in statement["text"]
        for statement in statements
        if statement["type"] == "unique_on_object"
    )
    assert max(
        sum(candidate["type"] == statement["type"] for candidate in statements)
        for statement in statements
    ) <= 2


def test_difficulty_uses_the_human_deduction_route() -> None:
    from murdoku_v2.explainer import explain_puzzle
    from murdoku_v2.models import load_puzzle

    restaurant = explain_puzzle(load_puzzle(PROJECT / "examples/board_restaurant/case.json"))
    hotel = explain_puzzle(load_puzzle(PROJECT / "examples/board_hotel/case.json"))
    golf = explain_puzzle(load_puzzle(PROJECT / "examples/board_golf/case.json"))
    assert restaurant["method"] == hotel["method"] == "human_propagation"
    assert restaurant["difficulty"]["label"] == "easy"
    assert hotel["difficulty"]["label"] == "medium"
    assert golf["difficulty"]["label"] == "hard"
    assert restaurant["step_count"] < hotel["step_count"]
    assert hotel["step_count"] < golf["step_count"]
    assert any(
        statement["type"] == "next_to_sequence_item"
        for card in load_puzzle(PROJECT / "examples/board_golf/case.json")["cards"]
        for statement in card["statements"]
    )


def test_generate_writes_a_fixed_scene_draft(tmp_path: Path) -> None:
    from murdoku_v2.generation import generate_case
    from murdoku_v2.models import load_puzzle

    source = PROJECT / "examples/board_restaurant/case.json"
    result = generate_case(source, 20260726, tmp_path)
    assert result["puzzle"]["board"] == load_puzzle(source)["board"]
    assert result["diagnostics"]["exact_unique"]
    assert result["explanation"]["unique"]
    assert result["manifest"]["editorial_status"] == "draft"
    assert result["manifest"]["generator"] == "fixed_scene"
    assert result["manifest"]["text_locale"] == "es"
    assert result["manifest"]["text_version"] == 1
    assert all((tmp_path / f"{name}.json").exists() for name in (
        "puzzle", "solution", "diagnostics", "explanation", "generation_report", "manifest"
    ))


def test_editorial_manifest_can_be_approved_then_retired(tmp_path: Path) -> None:
    from murdoku_v2.generation import generate_case
    from murdoku_v2.publication import set_editorial_status

    generate_case(PROJECT / "examples/board_restaurant/case.json", 1, tmp_path)
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
    assert "unique_adjacent_object" in html
    assert "data:image/webp;base64," in html
    assert 'class="furniture-layer"' in html
    assert "--object-width:2" in html
    assert "footprint-1x2" in html
    assert ">1.1<" not in html
    assert "Alicia estaba en el comedor" not in html
    assert "Estaba en el comedor." in html

    render_file(PROJECT / "examples/board_hotel/case.json", output)
    assert "--object-rotation:180deg" in output.read_text(encoding="utf-8")


def test_site_builder_publishes_only_reference_cases_without_solutions(tmp_path: Path) -> None:
    from murdoku_v2.site_builder import build_site

    result = build_site(tmp_path)
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    level = (tmp_path / "levels/001.html").read_text(encoding="utf-8")
    assert result["levels"] == 15
    assert "Dificultad" in index
    assert "Fácil" in index
    assert "Último servicio" in index
    assert "Hotel de medianoche" in index
    assert "La última ronda" in index
    assert "Después del cierre" in index
    assert "El último putt" in index
    assert "Medio" in index
    assert "Difícil" in index
    assert "Experto" in index
    assert "La línea decisiva" in index
    assert "la-ultima-ronda-8303" not in index
    assert "V · VÍCTIMA" in level
    assert 'data-tool="cross"' in level
    assert 'data-tool="candidate"' in level
    assert 'data-tool="erase"' in level
    assert (tmp_path / "levels/001.html").exists()
    assert (tmp_path / "levels/003.html").exists()
    assert not list(tmp_path.rglob("solution.json"))


def test_playtest_report_requires_unique_blind_sessions(tmp_path: Path) -> None:
    from murdoku_v2.playtest import analyze_sessions

    labels = ("easy", "medium", "hard", "expert")
    catalog = [
        {
            "puzzle_id": label,
            "difficulty": label,
            "rows": 8,
            "columns": 8,
        }
        for label in labels
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for label_index, label in enumerate(labels):
        for index in range(10):
            report = {
                "schemaVersion": 2,
                "sessionId": f"00000000-0000-4000-8000-{label_index:02d}{index:010d}",
                "puzzleId": label,
                "size": 8,
                "durationSeconds": 100 + label_index * 100 + index,
                "checks": 1,
                "errors": 0,
                "completed": True,
            }
            (sessions / f"{label}-{index}-session.json").write_text(
                json.dumps(report), encoding="utf-8",
            )

    result = analyze_sessions(catalog_path, [sessions])
    assert result["gate"]["ready_for_editorial_calibration"]
    duplicate = sessions / "duplicate.json"
    duplicate.write_text(
        (sessions / "easy-0-session.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicadas"):
        analyze_sessions(catalog_path, [sessions])


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

    wrong_rotation = copy.deepcopy(puzzle)
    wrong_rotation["board"]["objects"][0]["rotation"] = 45
    with pytest.raises(ValidationError):
        validate_puzzle(wrong_rotation)


def test_rectangular_board_is_solved_and_rendered() -> None:
    from murdoku_v2.candidates import candidate_pools
    from murdoku_v2.human import solve_human
    from murdoku_v2.models import validate_puzzle
    from murdoku_v2.render import render_html
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    puzzle = {
        "schema_version": 8,
        "id": "rectangular-contract",
        "seed": 1,
        "board": {
            "id": "rectangular-board",
            "name": "Rectangular",
            "rows": 2,
            "columns": 3,
            "rooms": [{
                "id": "hall",
                "name": "Hall",
                "cells": [[row, column] for row in range(2) for column in range(3)],
            }],
            "zones": [{
                "id": "water",
                "name": "Agua",
                "clue_label": "el agua",
                "cells": [[0, 1], [0, 2]],
            }],
            "sequences": [{
                "id": "holes",
                "name": "Hoyos",
                "item_label": "Hoyo",
                "cells": [[0, 0], [0, 1], [0, 2]],
            }],
            "objects": [],
        },
        "characters": [
            {"id": "ana", "name": "Ana", "gender": "woman", "role": "suspect"},
            {"id": "victor", "name": "Víctor", "gender": "man", "role": "victim"},
        ],
        "victim": "victor",
        "cards": [
            {
                "id": "card-ana",
                "character": "ana",
                "role": "suspect",
                "statements": [
                    {
                        "id": "ana-water",
                        "type": "beside_not_in_zone",
                        "family": "zone_relation",
                        "args": {"character": "ana", "zone": "water"},
                    },
                    {
                        "id": "ana-hole",
                        "type": "next_to_sequence_item",
                        "family": "sequence_relation",
                        "args": {"character": "ana", "sequence": "holes", "item": 1},
                    },
                ],
            },
            {
                "id": "card-victor",
                "character": "victor",
                "role": "victim",
                "statements": [
                    {"id": "victim-rule", "type": "victim_rule", "family": "murder_rule", "args": {"character": "victor"}},
                    {"id": "victor-column", "type": "exact_column", "family": "coordinate", "args": {"character": "victor", "column": 2}},
                ],
            },
        ],
    }
    expected = {"ana": (0, 0), "victor": (1, 2)}

    validate_puzzle(puzzle)
    exact = ORToolsSolver().solve(puzzle, limit=2)
    human = solve_human(puzzle)
    html = render_html(puzzle)
    assert exact.unique and exact.solutions == [expected]
    assert human["solved"] and human["positions"] == expected
    assert "--cols:3;--rows:2" in html
    assert "zone-cell zone-0" in html
    assert "Hoyo 1" in html
    assert any(
        statement["type"] == "next_to_sequence_item"
        for statement in candidate_pools(puzzle, expected)["ana"]
    )


def test_solver_registry_uses_cpsat() -> None:
    from murdoku_v2.solvers.registry import get_solver

    assert get_solver("auto").name == "ortools-cp-sat"
    assert get_solver("ortools").name == "ortools-cp-sat"
    with pytest.raises(ValueError, match="Solucionador desconocido"):
        get_solver("z3")
