from .base import SolverResult, SolverStats
from .backtracking import BacktrackingSolver
from .exhaustive import ExhaustiveSolver
from .registry import availability, get_solver

__all__ = [
    "SolverResult",
    "SolverStats",
    "BacktrackingSolver",
    "ExhaustiveSolver",
    "availability",
    "get_solver",
]
