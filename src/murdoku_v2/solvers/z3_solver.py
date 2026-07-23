from __future__ import annotations

import importlib.util
from typing import Any

from .base import SolverResult, SolverStats


class Z3Solver:
    """Optional adapter. Install the `solvers` extra to activate it."""

    name = "z3"

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("z3") is not None

    def solve(
        self,
        puzzle: dict[str, Any],
        *,
        limit: int = 2,
        exclude_card_id: str | None = None,
        exclude_statement_id: str | None = None,
    ) -> SolverResult:
        if not self.is_available():
            return SolverResult(
                [], SolverStats(solver=self.name), available=False,
                message="Z3 no está instalado. Usa: uv sync --extra solvers",
            )
        # Keep the adapter honest: until its complete clue encoding is enabled, do not silently delegate.
        return SolverResult(
            [], SolverStats(solver=self.name), available=False,
            message="El adaptador Z3 está detectado, pero la codificación completa de las 22 pistas queda desactivada hasta pasar la validación cruzada.",
        )
