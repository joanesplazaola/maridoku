from __future__ import annotations

from typing import Any

from .solvers.registry import get_solver


def explain_puzzle(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded CP-SAT explanation without enumerating the solution universe."""
    solver = get_solver("ortools")
    active: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for card in puzzle["cards"]:
        for statement in card["statements"]:
            active.append(statement)
            result = solver.solve(puzzle, limit=2, base_statements=tuple(active))
            steps.append({
                "statement_id": statement["id"],
                "character": card["character"],
                "text": statement["text"],
                "solution_count_cap2": len(result.solutions),
                "unique": result.unique,
            })

    final = steps[-1] if steps else {"solution_count_cap2": 0, "unique": False}
    score = min(100, len(steps) * 4 + puzzle["board"]["rows"] * 3)
    label = "easy" if score < 40 else "medium" if score < 60 else "hard" if score < 80 else "expert"
    return {
        "puzzle_id": puzzle["id"],
        "available": True,
        "method": "incremental_cp_sat",
        "steps": steps,
        "step_count": len(steps),
        "final_solution_count_cap2": final["solution_count_cap2"],
        "unique": final["unique"],
        "difficulty": {
            "label": label,
            "score": score,
            "calibration": "technical_estimate_not_human_calibrated",
        },
    }
