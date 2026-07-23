from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .solvers.registry import get_solver


def compare_solvers(
    puzzle_paths: list[Path],
    solver_names: list[str],
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for puzzle_path in puzzle_paths:
        puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
        case_results = []
        canonical = None
        for solver_name in solver_names:
            result = get_solver(solver_name).solve(puzzle, limit=2)
            if result.available and result.unique:
                canonical = canonical or result.solutions[0]
            case_results.append({
                **result.to_dict(include_solutions=False),
                "matches_first_unique_solver": bool(
                    result.available and result.unique and canonical is not None and result.solutions[0] == canonical
                ),
            })
        cases.append({
            "puzzle": puzzle["id"],
            "path": str(puzzle_path),
            "results": case_results,
        })
    report = {"cases": cases}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
