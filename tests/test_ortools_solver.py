from __future__ import annotations

import json
from pathlib import Path

import pytest

from murdoku_v2.solvers.backtracking import BacktrackingSolver
from murdoku_v2.solvers.ortools_solver import ORToolsSolver

ROOT = Path(__file__).resolve().parents[1]


def canonical(solutions):
    return {tuple(sorted((character, tuple(position)) for character, position in solution.items())) for solution in solutions}


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
@pytest.mark.parametrize("puzzle_path", sorted((ROOT / "examples").glob("*/puzzle.json")))
def test_cpsat_matches_backtracking(puzzle_path: Path):
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    expected = BacktrackingSolver().solve(puzzle, limit=2)
    actual = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=2)
    assert actual.available
    assert canonical(actual.solutions) == canonical(expected.solutions)


@pytest.mark.skipif(not ORToolsSolver.is_available(), reason="OR-Tools no está instalado")
def test_cpsat_card_and_statement_exclusions_match_backtracking():
    puzzle = json.loads((ROOT / "examples" / "board_restaurant" / "puzzle.json").read_text(encoding="utf-8"))
    limit = 200
    for card in puzzle["cards"]:
        card_id = card["id"]
        expected = BacktrackingSolver().solve(puzzle, limit=limit, exclude_card_id=card_id)
        actual = ORToolsSolver(num_search_workers=1).solve(puzzle, limit=limit, exclude_card_id=card_id)
        assert canonical(actual.solutions) == canonical(expected.solutions)
        for statement in card["statements"]:
            statement_id = statement["id"]
            expected_statement = BacktrackingSolver().solve(puzzle, limit=limit, exclude_statement_id=statement_id)
            actual_statement = ORToolsSolver(num_search_workers=1).solve(
                puzzle, limit=limit, exclude_statement_id=statement_id
            )
            assert canonical(actual_statement.solutions) == canonical(expected_statement.solutions)
