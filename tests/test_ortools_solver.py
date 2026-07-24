from __future__ import annotations

import json
from pathlib import Path

import pytest

from murdoku_v2.solvers.ortools_solver import ORToolsSolver
from murdoku_v2.validator import _matches_statement

ROOT = Path(__file__).resolve().parents[1]


def canonical(solutions):
    return {tuple(sorted((character, tuple(position)) for character, position in solution.items())) for solution in solutions}


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
@pytest.mark.parametrize("puzzle_path", sorted((ROOT / "examples").glob("*/puzzle.json")))
def test_cpsat_solves_reference_cases(puzzle_path: Path):
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    actual = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=2)
    assert actual.available
    assert actual.unique
    assert actual.stats.metadata["statuses"] == ["OPTIMAL", "INFEASIBLE"]


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
def test_cpsat_card_and_statement_exclusions_are_consistent():
    puzzle = json.loads((ROOT / "examples" / "board_restaurant" / "puzzle.json").read_text(encoding="utf-8"))
    baseline = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=2)
    assert baseline.unique
    baseline_solution = baseline.solutions[0]
    for card in puzzle["cards"]:
        card_id = card["id"]
        actual = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=2, exclude_card_id=card_id)
        assert actual.available
        assert actual.solutions
        assert all(
            _matches_statement(statement, baseline_solution, puzzle)
            for other_card in puzzle["cards"]
            if other_card["id"] != card_id
            for statement in other_card["statements"]
        )
        for statement in card["statements"]:
            statement_id = statement["id"]
            actual_statement = ORToolsSolver(num_search_workers=1).solve(
                puzzle, limit=2, exclude_statement_id=statement_id
            )
            assert actual_statement.available
            assert actual_statement.solutions
            assert all(
                _matches_statement(other_statement, baseline_solution, puzzle)
                for other_card in puzzle["cards"]
                for other_statement in other_card["statements"]
                if other_statement["id"] != statement_id
            )


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
def test_cpsat_accepts_candidate_statements_without_mutating_cards():
    puzzle = json.loads((ROOT / "examples" / "board_restaurant" / "puzzle.json").read_text(encoding="utf-8"))
    relaxed = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=2, exclude_card_id="card-fabio")
    assert not relaxed.unique

    candidate = puzzle["cards"][-1]["statements"][0]
    tightened = ORToolsSolver(num_search_workers=1).solve(
        puzzle,
        limit=2,
        exclude_card_id="card-fabio",
        extra_statements=(candidate,),
    )
    assert tightened.available
    assert tightened.stats.constraint_checks == relaxed.stats.constraint_checks + 1
    assert tightened.solutions


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
def test_cpsat_can_solve_from_explicit_statement_set():
    puzzle = json.loads((ROOT / "examples" / "board_restaurant" / "puzzle.json").read_text(encoding="utf-8"))
    victim_statement = puzzle["cards"][0]["statements"][0]
    result = ORToolsSolver(num_search_workers=1).solve(
        puzzle,
        limit=2,
        base_statements=(victim_statement,),
    )
    assert result.available
    assert len(result.solutions) == 2
    assert result.stats.constraint_checks == 1


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
def test_cpsat_bounded_enumeration_reuses_one_search():
    puzzle = json.loads((ROOT / "examples" / "board_restaurant" / "puzzle.json").read_text(encoding="utf-8"))
    victim_statement = puzzle["cards"][0]["statements"][0]
    result = ORToolsSolver().enumerate_solutions(
        puzzle,
        limit=12,
        base_statements=(victim_statement,),
    )

    assert len(result.solutions) == 12
    assert len(canonical(result.solutions)) == 12
    assert result.stats.constraint_checks == 1
    assert result.stats.metadata["mode"] == "bounded_enumeration"
