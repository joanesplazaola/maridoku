from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from murdoku_v2.clue_catalog import AtomicClue, CLUE_SPECS, atomic_mask, catalog_json
from murdoku_v2.engine import (
    CHARACTERS,
    apply_victim_rule,
    board_geometry,
    build_board_arrays,
    enumerate_base_solutions,
    generate,
    generate_atomic_candidates,
    probe_candidates_with_cpsat,
    probe_candidate_with_cpsat,
    load_board,
)
from murdoku_v2.validator import validate_files


PROJECT = Path(__file__).resolve().parents[1]


def test_formal_catalog_has_one_exact_semantics_for_every_generated_type() -> None:
    examples = {}
    for board_path in sorted((PROJECT / "boards").glob("*.json")):
        board = load_board(board_path)
        room_flat, room_ids, room_names, room_index, group_room_indexes = build_board_arrays(board)
        geometry = board_geometry(board, room_flat)
        base = enumerate_base_solutions(board)
        victim_index = 0
        valid = apply_victim_rule(base, victim_index, room_flat)
        for target_index in range(min(900, len(valid))):
            target = valid[target_index]
            pools, _ = generate_atomic_candidates(
                target, board, room_flat, room_ids, room_names, room_index,
                group_room_indexes, geometry, victim_index,
            )
            for candidates in pools.values():
                for clue in candidates:
                    examples.setdefault(
                        clue.type,
                        (clue, target.copy(), board, room_flat, room_index, group_room_indexes, geometry, valid),
                    )
            if set(examples) == set(CLUE_SPECS):
                break
        if set(examples) == set(CLUE_SPECS):
            break

    assert set(examples) == set(CLUE_SPECS)
    rng = np.random.default_rng(1234)
    for clue_type, data in examples.items():
        clue, target, board, room_flat, room_index, group_room_indexes, geometry, valid = data
        sample_indexes = rng.choice(len(valid), size=min(1200, len(valid)), replace=False)
        solutions = np.vstack([target, valid[sample_indexes]])
        mask = atomic_mask(
            clue, solutions, board, room_flat, room_index,
            group_room_indexes, geometry, CHARACTERS,
        )
        assert clue_type in CLUE_SPECS
        assert clue.family == CLUE_SPECS[clue_type].family
        assert bool(mask[0])
        assert bool(np.any(~mask))
    assert len(catalog_json()) == len(CLUE_SPECS) == 22


def test_same_engine_generates_valid_cases_on_five_manual_boards(tmp_path: Path) -> None:
    boards = sorted((PROJECT / "boards").glob("*.json"))
    assert len(boards) == 5
    for offset, board_path in enumerate(boards):
        output = tmp_path / board_path.stem
        result = generate(board_path, 100 + offset, output, selection_profile="any")
        diagnostics = result["diagnostics"]
        assert result["puzzle"]["schema_version"] == 8
        assert diagnostics["final_solution_count"] == 1
        assert diagnostics["cpsat_selector_enabled"] is False
        assert diagnostics["all_cards_necessary"] is True
        assert diagnostics["all_suspect_statements_necessary"] is True
        assert diagnostics["human_solver_matches_solution"] is True
        assert diagnostics["exact_validation"]["unique"] is True
        assert diagnostics["exact_validation"]["matches_solution"] is True
        assert diagnostics["cpsat_card_set_validation"] == {
            "unique": True,
            "target_valid": True,
            "solution_count": 1,
            "statement_count": diagnostics["total_statement_count"],
        }
        probe = diagnostics["cpsat_candidate_probe_sample"]
        assert probe["tested"] == 5
        assert all(
            item["target_valid"] is True
            and item["cpsat_solution_count_cap2"] == item["numpy_solution_count_cap2"]
            for items in probe["by_subject"].values()
            for item in items
        )
        assert diagnostics["formal_clue_catalog_size"] == 22
        assert diagnostics["global_selector"]["method"].startswith("global_")
        assert (output / "generation_report.json").exists()
        assert validate_files(output / "puzzle.json", output / "solution.json") == {
            "solution_count_up_to_two": 1,
            "unique": True,
            "matches_generated_solution": True,
            "murderer_matches": True,
        }


def test_global_selector_returns_complete_nonredundant_cards(tmp_path: Path) -> None:
    result = generate(
        PROJECT / "boards/board_mansion.json", 102, tmp_path, selection_profile="any"
    )
    puzzle = result["puzzle"]
    diagnostics = result["diagnostics"]
    suspect_cards = [card for card in puzzle["cards"] if card["role"] == "suspect"]
    assert len(suspect_cards) == 5
    assert all(1 <= len(card["statements"]) <= 2 for card in suspect_cards)
    assert all(item["necessary"] for item in diagnostics["card_necessity"])
    assert all(item["necessary"] for item in diagnostics["statement_necessity"])
    selector = diagnostics["global_selector"]
    assert selector["complete_sets_checked"] >= 1
    assert selector["accepted_score"] is not None
    assert sum(selector["selected_families"].values()) == sum(
        len(card["statements"]) for card in suspect_cards
    )


def test_cpsat_candidate_probe_keeps_the_target_solution(tmp_path: Path) -> None:
    result = generate(
        PROJECT / "boards/board_restaurant.json", 6201, tmp_path, selection_profile="any"
    )
    puzzle = result["puzzle"]
    expected = {
        character: (position["row"], position["column"])
        for character, position in result["solution"]["positions"].items()
    }
    card, statement = next(
        (card, statement)
        for card in puzzle["cards"]
        if card["role"] == "suspect"
        for statement in card["statements"]
    )
    candidate = AtomicClue(card["character"], statement["type"], statement["family"], statement["args"], statement["text"])
    probe = probe_candidate_with_cpsat(puzzle, candidate, expected)
    assert probe["available"] is True
    assert probe["target_valid"] is True
    assert probe["solution_count"] >= 1


def test_cpsat_candidate_probe_matches_numpy_mask_count() -> None:
    board = load_board(PROJECT / "boards/board_restaurant.json")
    room_flat, room_ids, room_names, room_index, group_room_indexes = build_board_arrays(board)
    geometry = board_geometry(board, room_flat)
    base = enumerate_base_solutions(board)
    victim_index = 0
    valid = apply_victim_rule(base, victim_index, room_flat)
    target = valid[0]
    pools, _ = generate_atomic_candidates(
        target, board, room_flat, room_ids, room_names, room_index,
        group_room_indexes, geometry, victim_index,
    )
    candidate = pools["bruno"][0]
    mask = atomic_mask(
        candidate, valid, board, room_flat, room_index,
        group_room_indexes, geometry, CHARACTERS,
    )
    puzzle = {
        "schema_version": 8,
        "id": "candidate-probe",
        "seed": 1,
        "board": board,
        "characters": [
            {**character, "role": "victim" if index == victim_index else "suspect"}
            for index, character in enumerate(CHARACTERS)
        ],
        "victim": CHARACTERS[victim_index]["id"],
        "cards": [
            {
                "id": f"card-{character['id']}",
                "character": character["id"],
                "role": "victim" if index == victim_index else "suspect",
                "statements": [{
                    "id": f"card-{character['id']}-statement-1",
                    "type": "victim_rule" if index == victim_index else "room",
                    "family": "murder_rule" if index == victim_index else "room_exact",
                    "args": (
                        {"character": character["id"]}
                        if index == victim_index
                        else {"character": character["id"], "room": board["rooms"][0]["id"]}
                    ),
                    "text": "",
                }],
            }
            for index, character in enumerate(CHARACTERS)
        ],
    }
    expected = {
        character["id"]: divmod(int(target[index]), board["rows"])
        for index, character in enumerate(CHARACTERS)
    }
    victim_statement = puzzle["cards"][victim_index]["statements"][0]
    probe = probe_candidate_with_cpsat(
        puzzle,
        candidate,
        expected,
        limit=2,
        base_statements=(victim_statement,),
    )
    assert probe["target_valid"] is True
    assert probe["solution_count"] == min(2, int(np.count_nonzero(mask)))


def test_cpsat_candidate_set_probe_matches_numpy_intersection() -> None:
    board = load_board(PROJECT / "boards/board_restaurant.json")
    room_flat, room_ids, room_names, room_index, group_room_indexes = build_board_arrays(board)
    geometry = board_geometry(board, room_flat)
    base = enumerate_base_solutions(board)
    victim_index = 0
    valid = apply_victim_rule(base, victim_index, room_flat)
    target = valid[0]
    pools, _ = generate_atomic_candidates(
        target, board, room_flat, room_ids, room_names, room_index,
        group_room_indexes, geometry, victim_index,
    )
    candidates = pools["bruno"][:2]
    mask = np.ones(len(valid), dtype=bool)
    for candidate in candidates:
        mask &= atomic_mask(
            candidate, valid, board, room_flat, room_index,
            group_room_indexes, geometry, CHARACTERS,
        )
    puzzle = {
        "schema_version": 8,
        "id": "candidate-set-probe",
        "seed": 1,
        "board": board,
        "characters": [
            {**character, "role": "victim" if index == victim_index else "suspect"}
            for index, character in enumerate(CHARACTERS)
        ],
        "victim": CHARACTERS[victim_index]["id"],
        "cards": [
            {
                "id": f"card-{character['id']}",
                "character": character["id"],
                "role": "victim" if index == victim_index else "suspect",
                "statements": [{
                    "id": f"card-{character['id']}-statement-1",
                    "type": "victim_rule" if index == victim_index else "room",
                    "family": "murder_rule" if index == victim_index else "room_exact",
                    "args": (
                        {"character": character["id"]}
                        if index == victim_index
                        else {"character": character["id"], "room": board["rooms"][0]["id"]}
                    ),
                    "text": "",
                }],
            }
            for index, character in enumerate(CHARACTERS)
        ],
    }
    expected = {
        character["id"]: divmod(int(target[index]), board["rows"])
        for index, character in enumerate(CHARACTERS)
    }
    victim_statement = puzzle["cards"][victim_index]["statements"][0]
    probe = probe_candidates_with_cpsat(
        puzzle,
        candidates,
        expected,
        limit=2,
        base_statements=(victim_statement,),
    )
    assert probe["target_valid"] is True
    assert probe["solution_count"] == min(2, int(np.count_nonzero(mask)))


def test_generation_report_explains_acceptance_and_rejections(tmp_path: Path) -> None:
    result = generate(
        PROJECT / "boards/board_mansion.json", 102, tmp_path, selection_profile="any"
    )
    report = result["generation_report"]
    assert report["summary"]["accepted"] is True
    assert report["summary"]["targets_attempted"] >= 1
    assert report["targets"][-1]["status"] == "accepted"
    assert report["targets"][-1]["selector"]["method"].startswith("global_")
    # The JSON on disk is part of the public diagnostic contract.
    disk = json.loads((tmp_path / "generation_report.json").read_text(encoding="utf-8"))
    assert disk == report


def test_room_phrases_use_basic_spanish_articles() -> None:
    from murdoku_v2.engine import _room_phrase

    assert _room_phrase("Entrada") == "la entrada"
    assert _room_phrase("Despensa") == "la despensa"
    assert _room_phrase("Habitación 101") == "la habitación 101"
    assert _room_phrase("Aseos") == "los aseos"
    assert _room_phrase("Salón común") == "el salón común"


def test_global_selector_can_require_a_real_double_card() -> None:
    from murdoku_v2.clue_catalog import AtomicClue
    from murdoku_v2.selector import global_select_cards

    size = 16  # Four independent Boolean dimensions.
    all_bits = (1 << size) - 1

    def zero_mask(bit_position: int) -> int:
        result = 0
        for solution in range(size):
            if ((solution >> bit_position) & 1) == 0:
                result |= 1 << solution
        return result

    a1 = AtomicClue("a", "object_same_row_in_room", "object_line", {"character": "a"}, "A1")
    a2 = AtomicClue("a", "room_disjunction", "room_choice", {"character": "a"}, "A2")
    b1 = AtomicClue("b", "relative_row_order", "relative_order", {"character": "b"}, "B1")
    c1 = AtomicClue("c", "room_population", "room_population", {"character": "c"}, "C1")
    pools = {"a": [a1, a2], "b": [b1], "c": [c1]}
    masks = {
        a1.key: zero_mask(0),
        a2.key: zero_mask(1),
        b1.key: zero_mask(2),
        c1.key: zero_mask(3),
    }
    cards, report = global_select_cards(
        pools, masks, target_index=0, size=size,
        rng=random.Random(1), profile="any", beam_width=80, order_attempts=4,
    )
    assert cards is not None
    assert report["method"] == "global_beam_search_with_double_cards"
    assert len(cards["a"]) == 2
    assert len(cards["b"]) == 1
    assert len(cards["c"]) == 1


def test_ortools_matches_generated_solutions_on_all_reference_cases() -> None:
    import json

    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    for puzzle_path in sorted((PROJECT / "examples").glob("*/puzzle.json")):
        puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
        solution = json.loads((puzzle_path.parent / "solution.json").read_text(encoding="utf-8"))
        expected = {
            character: (position["row"], position["column"])
            for character, position in solution["positions"].items()
        }
        ortools = ORToolsSolver().solve(puzzle, limit=2)
        assert ortools.available is True
        assert ortools.unique is True
        assert ortools.solutions == [expected]


def test_ortools_scales_to_twelve_characters() -> None:
    from murdoku_v2.scaling import expected_scaling_solution, make_scaling_puzzle
    from murdoku_v2.solvers.ortools_solver import ORToolsSolver

    solver = ORToolsSolver()
    for size in (6, 8, 10, 12):
        result = solver.solve(make_scaling_puzzle(size), limit=2)
        assert result.available is True
        assert result.unique is True
        assert result.solutions[0] == expected_scaling_solution(size)


def test_generate_scale_writes_a_valid_large_case(tmp_path: Path) -> None:
    from murdoku_v2.scaling import generate_scaling_case

    result = generate_scaling_case(10, 9001, tmp_path)
    assert result["puzzle"]["board"]["rows"] == 10
    assert result["diagnostics"]["exact_validation"]["unique"] is True
    assert result["solution"]["murderer"] == "person_02"
    assert (tmp_path / "puzzle.json").exists()
    assert (tmp_path / "generation_report.json").exists()


def test_render_writes_printable_html(tmp_path: Path) -> None:
    from murdoku_v2.render import render_file

    output = tmp_path / "puzzle.html"
    render_file(PROJECT / "examples/board_restaurant/puzzle.json", output)
    html = output.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "<main>" in html
    assert "case-board_restaurant" in html


def test_scaling_generator_depends_on_seed() -> None:
    from murdoku_v2.scaling import expected_scaling_solution

    assert expected_scaling_solution(10, 1) != expected_scaling_solution(10, 2)


def test_pydantic_contract_rejects_a_card_with_the_wrong_subject() -> None:
    import copy
    import json

    import pytest
    from pydantic import ValidationError

    from murdoku_v2.models import validate_puzzle

    puzzle = json.loads((PROJECT / "examples/board_restaurant/puzzle.json").read_text(encoding="utf-8"))
    malformed = copy.deepcopy(puzzle)
    malformed["cards"][0]["statements"][0]["args"]["character"] = malformed["cards"][1]["character"]
    with pytest.raises(ValidationError):
        validate_puzzle(malformed)


def test_optional_solver_adapters_fail_explicitly_when_not_installed() -> None:
    import json

    from murdoku_v2.solvers.registry import get_solver

    puzzle = json.loads((PROJECT / "examples/board_restaurant/puzzle.json").read_text(encoding="utf-8"))
    for name in ("z3", "ortools"):
        solver = get_solver(name)
        result = solver.solve(puzzle)
        if not solver.is_available():
            assert result.available is False
            assert result.message
