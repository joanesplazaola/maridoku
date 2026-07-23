from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .solvers.registry import get_solver


NAMES = [
    "Alicia", "Bruno", "Carla", "Diego", "Elena", "Fabio",
    "Gabriela", "Hugo", "Irene", "Javier", "Katia", "Lucas",
    "Marta", "Nicolás", "Olga", "Pablo",
]


def make_scaling_puzzle(size: int, seed: int = 0) -> dict[str, Any]:
    """Create a deterministic, unique synthetic puzzle for solver scalability tests.

    It deliberately uses only public clue types. The last suspect anchors the chain with
    exact row/column clues; every preceding suspect is one step north/west of the next.
    The victim is fixed by the remaining row and column plus the victim-room rule.
    """
    if size < 4 or size > len(NAMES):
        raise ValueError(f"El benchmark sintético admite tamaños entre 4 y {len(NAMES)}.")
    characters = [
        {
            "id": f"person_{index + 1:02d}",
            "name": NAMES[index],
            "gender": "woman" if index % 2 == 0 else "man",
            "role": "victim" if index == 0 else "suspect",
        }
        for index in range(size)
    ]

    # A 2x2 crime room contains the target victim (0,0) and murderer (1,1).
    crime_cells = {(0, 0), (0, 1), (1, 0), (1, 1)}
    other_cells = {(row, column) for row in range(size) for column in range(size)} - crime_cells
    board = {
        "id": f"scale_{size}x{size}",
        "name": f"Benchmark sintético {size}×{size}",
        "rows": size,
        "columns": size,
        "room_groups": [],
        "rooms": [
            {"id": "crime_room", "name": "Sala del crimen", "cells": sorted(crime_cells)},
            {"id": "rest", "name": "Resto del edificio", "cells": sorted(other_cells)},
        ],
        "objects": [],
    }

    victim = characters[0]
    cards: list[dict[str, Any]] = [{
        "id": f"card-{victim['id']}",
        "character": victim["id"],
        "character_name": victim["name"],
        "role": "victim",
        "statements": [{
            "id": f"card-{victim['id']}-statement-1",
            "type": "victim_rule",
            "family": "murder_rule",
            "args": {"character": victim["id"]},
            "text": f"{victim['name']} estaba a solas con otra persona.",
        }],
    }]

    for index in range(1, size):
        character = characters[index]
        if index == size - 1:
            statements = [
                {
                    "id": f"card-{character['id']}-statement-1",
                    "type": "exact_row",
                    "family": "coordinate",
                    "args": {"character": character["id"], "row": size - 1},
                    "text": f"{character['name']} estaba en la {size}.ª fila.",
                },
                {
                    "id": f"card-{character['id']}-statement-2",
                    "type": "exact_column",
                    "family": "coordinate",
                    "args": {"character": character["id"], "column": size - 1},
                    "text": f"{character['name']} estaba en la {size}.ª columna.",
                },
            ]
        else:
            reference = characters[index + 1]
            statements = [
                {
                    "id": f"card-{character['id']}-statement-1",
                    "type": "relative_row_distance",
                    "family": "relative_distance",
                    "args": {"character": character["id"], "reference": reference["id"], "delta": -1},
                    "text": f"{character['name']} estaba una fila al norte de {reference['name']}.",
                },
                {
                    "id": f"card-{character['id']}-statement-2",
                    "type": "relative_column_distance",
                    "family": "relative_distance",
                    "args": {"character": character["id"], "reference": reference["id"], "delta": -1},
                    "text": f"{character['name']} estaba una columna al oeste de {reference['name']}.",
                },
            ]
        cards.append({
            "id": f"card-{character['id']}",
            "character": character["id"],
            "character_name": character["name"],
            "role": "suspect",
            "statements": statements,
        })

    return {
        "schema_version": 8,
        "id": f"scale-{size}-{seed}",
        "seed": seed,
        "selection_profile": "scaling",
        "board": board,
        "characters": characters,
        "victim": victim["id"],
        "rules": {
            "one_character_per_row": True,
            "one_character_per_column": True,
            "one_card_per_character": True,
        },
        "cards": cards,
    }


def expected_scaling_solution(size: int) -> dict[str, tuple[int, int]]:
    return {f"person_{index + 1:02d}": (index, index) for index in range(size)}


def generate_scaling_case(size: int, seed: int, output: Path) -> dict[str, Any]:
    puzzle = make_scaling_puzzle(size, seed)
    expected = expected_scaling_solution(size)
    solver = get_solver("ortools")
    started = time.perf_counter()
    result = solver.solve(puzzle, limit=2)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not result.available or not result.unique or result.solutions[0] != expected:
        raise RuntimeError("CP-SAT no validó el caso escalable generado.")

    room_at = {
        tuple(cell): room["id"]
        for room in puzzle["board"]["rooms"]
        for cell in room["cells"]
    }
    solution = {
        "puzzle_id": puzzle["id"],
        "victim": "person_01",
        "victim_name": puzzle["characters"][0]["name"],
        "positions": {
            character["id"]: {
                "row": row,
                "column": column,
                "room": room_at[(row, column)],
            }
            for character, (row, column) in zip(puzzle["characters"], expected.values(), strict=True)
        },
        "murderer": "person_02",
        "murderer_name": puzzle["characters"][1]["name"],
    }
    diagnostics = {
        "puzzle_id": puzzle["id"],
        "generator": "scaling_chain",
        "size": size,
        "exact_validation": {
            "unique": result.unique,
            "matches_solution": True,
            "stats": result.stats.to_dict(),
        },
        "generation_ms": round(elapsed_ms, 3),
        "human_solver_available": False,
    }
    explanation = {
        "puzzle_id": puzzle["id"],
        "available": False,
        "reason": "La explicación deductiva actual usa enumeración 6x6; este caso se valida con CP-SAT.",
    }
    generation_report = {
        "puzzle_id": puzzle["id"],
        "summary": {
            "accepted": True,
            "method": "scaling_chain",
            "size": size,
            "solver": result.stats.solver,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, data in {
        "puzzle": puzzle,
        "solution": solution,
        "diagnostics": diagnostics,
        "explanation": explanation,
        "generation_report": generation_report,
    }.items():
        (output / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "puzzle": puzzle,
        "solution": solution,
        "diagnostics": diagnostics,
        "explanation": explanation,
        "generation_report": generation_report,
    }


def run_scaling_benchmark(
    sizes: list[int],
    *,
    solver_name: str = "ortools",
    repetitions: int = 3,
    output: Path | None = None,
) -> dict[str, Any]:
    solver = get_solver(solver_name)
    rows: list[dict[str, Any]] = []
    for size in sizes:
        puzzle = make_scaling_puzzle(size)
        expected = expected_scaling_solution(size)
        timings: list[float] = []
        last = None
        for _ in range(repetitions):
            result = solver.solve(puzzle, limit=2)
            if not result.available:
                last = result
                break
            timings.append(result.stats.elapsed_ms)
            last = result
        assert last is not None
        rows.append({
            "size": size,
            "solver": solver_name,
            "available": last.available,
            "unique": last.unique,
            "matches_expected": bool(last.unique and last.solutions[0] == expected),
            "elapsed_ms_min": round(min(timings), 3) if timings else None,
            "elapsed_ms_mean": round(sum(timings) / len(timings), 3) if timings else None,
            "elapsed_ms_max": round(max(timings), 3) if timings else None,
            "nodes": last.stats.nodes,
            "backtracks": last.stats.backtracks,
            "pruned": last.stats.pruned,
            "message": last.message,
        })
    report = {
        "solver": solver_name,
        "repetitions": repetitions,
        "results": rows,
        "all_available_cases_unique": all(row["unique"] for row in rows if row["available"]),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
