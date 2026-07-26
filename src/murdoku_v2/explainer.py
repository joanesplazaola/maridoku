from __future__ import annotations

from typing import Any

from .human import solve_human
from .solvers.registry import get_solver


def explain_puzzle(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Explain the human deduction route and verify its result exactly."""
    human = solve_human(puzzle)
    exact = get_solver("ortools").solve(puzzle, limit=2)
    return {
        "puzzle_id": puzzle["id"],
        "available": exact.available,
        "method": "human_propagation",
        "solved_without_guessing": human["solved"],
        "steps": human["steps"],
        "step_count": human.get("step_count", len(human["steps"])),
        "techniques": human.get("techniques", []),
        "complexity": human.get("complexity"),
        "unique": exact.unique,
        "difficulty": human.get("difficulty", {"label": "unrated", "score": None}),
    }
