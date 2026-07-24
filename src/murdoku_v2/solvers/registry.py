from __future__ import annotations

from typing import Any

from .ortools_solver import ORToolsSolver


SOLVER_TYPES = {
    "ortools": ORToolsSolver,
}


def get_solver(name: str):
    if name == "auto":
        return ORToolsSolver()
    try:
        return SOLVER_TYPES[name]()
    except KeyError as exc:
        raise ValueError(f"Solucionador desconocido: {name}") from exc


def availability() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "available": solver_type.is_available(),
            "role": "motor exacto principal CP-SAT",
        }
        for name, solver_type in SOLVER_TYPES.items()
    ]
