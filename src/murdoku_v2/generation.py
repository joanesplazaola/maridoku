from __future__ import annotations

from typing import Any

from .candidates import candidate_pools
from .editorial import audit_puzzle
from .models import validate_puzzle
from .selection import apply_clues, select_clues
from .solvers.registry import get_solver


def generate_variant(
    puzzle: dict[str, Any],
    seed: int,
    *,
    max_target_attempts: int = 100,
) -> dict[str, Any]:
    """Generate positions and clues on an existing scene without a known solution."""
    if max_target_attempts < 1:
        raise ValueError("max_target_attempts debe ser al menos 1.")
    validate_puzzle(puzzle)

    board = puzzle["board"]
    characters = [character["id"] for character in puzzle["characters"]]
    character_data = {character["id"]: character for character in puzzle["characters"]}
    victim = puzzle["victim"]
    room_at = {
        tuple(cell): room["id"]
        for room in board["rooms"]
        for cell in room["cells"]
    }
    victim_statements = tuple(
        statement
        for card in puzzle["cards"]
        if card["role"] == "victim"
        for statement in card["statements"]
    )
    exact = get_solver("ortools")
    targets = exact.enumerate_solutions(
        {**puzzle, "seed": seed},
        limit=max_target_attempts,
        base_statements=victim_statements,
    ).solutions

    for attempt, target in enumerate(targets, start=1):
        victim_room = room_at[target[victim]]
        companions = [
            character
            for character, position in target.items()
            if character != victim and room_at[position] == victim_room
        ]
        if len(companions) != 1:
            continue

        pools = candidate_pools(puzzle, target)
        object_anchored = sum(
            any(statement["family"].startswith("object_") for statement in pool)
            for pool in pools.values()
        )
        if object_anchored < min(3, len(pools)):
            continue

        try:
            selection = select_clues(puzzle, target, max_iterations=80)
        except RuntimeError:
            continue

        generated = apply_clues(puzzle, selection["statements"])
        generated["id"] = f"{puzzle['id']}-{seed}"
        generated["seed"] = seed

        editorial = audit_puzzle(generated)
        if not editorial["accepted"] or editorial["warnings"]:
            continue
        exact_result = exact.solve(generated, limit=2)
        if not exact_result.unique or exact_result.solutions != [target]:
            continue

        murderer = companions[0]
        solution = {
            "puzzle_id": generated["id"],
            "victim": victim,
            "victim_name": character_data[victim]["name"],
            "positions": {
                character: {
                    "row": row,
                    "column": column,
                    "room": room_at[(row, column)],
                }
                for character, (row, column) in target.items()
            },
            "murderer": murderer,
            "murderer_name": character_data[murderer]["name"],
        }
        return {
            "puzzle": generated,
            "solution": solution,
            "diagnostics": {
                "seed": seed,
                "target_attempt": attempt,
                "selector_iterations": selection["iterations"],
                "selector_witnesses": selection["witnesses"],
                "families": selection["families"],
                "directional": selection["directional"],
                "human_steps": selection["human_steps"],
                "human_techniques": selection["human_techniques"],
                "human_complexity": selection["human_complexity"],
                "editorial_audit": editorial,
                "exact_unique": True,
            },
        }

    raise RuntimeError(
        f"No se encontró una variante publicable en {max_target_attempts} objetivos."
    )
