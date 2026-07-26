from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Any

from .editorial import audit_puzzle
from .human import solve_human
from .models import load_puzzle
from .solvers.registry import get_solver

TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"retired"},
    "retired": set(),
}


def set_editorial_status(manifest_path: Path, status: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = manifest.get("editorial_status")
    if status not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Transición editorial no permitida: {current} → {status}")
    if status == "approved":
        puzzle_path = manifest_path.parent / manifest["public_puzzle"]["path"]
        solution_path = manifest_path.parent / manifest["private_solution"]["path"]
        puzzle = load_puzzle(puzzle_path)
        solution = json.loads(solution_path.read_text(encoding="utf-8"))
        expected = {
            character: (position["row"], position["column"])
            for character, position in solution["positions"].items()
        }
        audit = audit_puzzle(puzzle)
        exact = get_solver("ortools").solve(puzzle, limit=2)
        human = solve_human(puzzle)
        if audit["errors"] or audit["warnings"]:
            raise ValueError(f"El draft no pasa la auditoría editorial: {audit}")
        if not exact.unique or exact.solutions != [expected]:
            raise ValueError("El draft no conserva una solución única verificada.")
        if not human["solved"] or human["positions"] != expected:
            raise ValueError("El draft no tiene una ruta humana completa.")
        manifest["public_puzzle"]["sha256"] = hashlib.sha256(puzzle_path.read_bytes()).hexdigest()
        manifest["private_solution"]["sha256"] = hashlib.sha256(solution_path.read_bytes()).hexdigest()
        manifest["review"] = {
            "exact_unique": True,
            "human_solved": True,
            "difficulty": human["difficulty"],
            "editorial_audit": audit,
        }
    manifest["editorial_status"] = status
    manifest["editorial_commit"] = os.environ.get("MURDOKU_COMMIT", "local")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
