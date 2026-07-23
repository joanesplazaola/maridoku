from __future__ import annotations

import time
from typing import Any

from .base import SolverResult, SolverStats
from ..validator import solve_puzzle


class ExhaustiveSolver:
    name = "exhaustive"

    @classmethod
    def is_available(cls) -> bool:
        return True

    def solve(
        self,
        puzzle: dict[str, Any],
        *,
        limit: int = 2,
        exclude_card_id: str | None = None,
        exclude_statement_id: str | None = None,
    ) -> SolverResult:
        started = time.perf_counter()
        n = puzzle["board"]["rows"]
        if n > 6:
            stats = SolverStats(solver=self.name, elapsed_ms=(time.perf_counter() - started) * 1000)
            return SolverResult(
                [], stats, available=False,
                message="El solucionador exhaustivo se limita deliberadamente a 6×6.",
            )
        solutions = solve_puzzle(
            puzzle,
            limit=limit,
            exclude_card_id=exclude_card_id,
            exclude_statement_id=exclude_statement_id,
        )
        stats = SolverStats(
            solver=self.name,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            metadata={"limit": limit, "enumeration": "row_permutations_x_column_permutations"},
        )
        return SolverResult(solutions, stats)
