from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


PositionMap = dict[str, tuple[int, int]]


@dataclass(slots=True)
class SolverStats:
    solver: str
    nodes: int = 0
    backtracks: int = 0
    pruned: int = 0
    constraint_checks: int = 0
    max_depth: int = 0
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SolverResult:
    solutions: list[PositionMap]
    stats: SolverStats
    available: bool = True
    message: str | None = None

    @property
    def unique(self) -> bool:
        return len(self.solutions) == 1

    def to_dict(self, include_solutions: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "solver": self.stats.solver,
            "available": self.available,
            "solution_count": len(self.solutions),
            "unique": self.unique,
            "stats": self.stats.to_dict(),
        }
        if self.message:
            data["message"] = self.message
        if include_solutions:
            data["solutions"] = self.solutions
        return data


class PuzzleSolver(Protocol):
    name: str

    @classmethod
    def is_available(cls) -> bool: ...

    def solve(
        self,
        puzzle: dict[str, Any],
        *,
        limit: int = 2,
        exclude_card_id: str | None = None,
        exclude_statement_id: str | None = None,
    ) -> SolverResult: ...
