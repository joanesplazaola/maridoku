from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .candidates import candidate_pools
from .editorial import audit_puzzle
from .explainer import explain_puzzle
from .object_catalog import OBJECT_CATALOG
from .solvers.registry import get_solver
from .text_catalog import clue_text, text_catalog


NAMES = [
    "Alicia", "Bruno", "Carla", "Diego", "Elena", "Fabio",
    "Gabriela", "Hugo", "Irene", "Javier", "Katia", "Lucas",
    "Marta", "Nicolás", "Olga", "Pablo",
]


ROOM_NAMES = [
    ("library", "Biblioteca"),
    ("lounge", "Salón"),
    ("study", "Despacho"),
    ("gallery", "Galería"),
    ("dining", "Comedor"),
    ("winter_garden", "Invernadero"),
    ("service", "Office"),
    ("music_room", "Sala de música"),
]


def _object(
    type_: str, cells: set[tuple[int, int]], suffix: str, *, occupiable: bool | None = None,
) -> dict[str, Any]:
    spec = OBJECT_CATALOG[type_]
    occupiable = spec.occupiable if occupiable is None else occupiable
    row, column = min(cells)
    return {
        "id": f"{type_}-{suffix}",
        "type": type_,
        "name": spec.name,
        "cells": [list(cell) for cell in sorted(cells)],
        "row": row,
        "column": column,
        "layer": spec.layer,
        "occupiable": occupiable,
        "blocks_character": not occupiable,
    }


def _place_footprint(
    shapes: list[set[tuple[int, int]]],
    size: int,
    room_at: dict[tuple[int, int], str],
    occupied: set[tuple[int, int]],
    *,
    room_id: str | None = None,
    predicate: Any = lambda cells: True,
) -> set[tuple[int, int]]:
    for shape in shapes:
        for row in range(size):
            for column in range(size):
                cells = {(row + dr, column + dc) for dr, dc in shape}
                if any(cell not in room_at for cell in cells) or cells & occupied:
                    continue
                rooms = {room_at[cell] for cell in cells}
                if len(rooms) == 1 and (room_id is None or rooms == {room_id}) and predicate(cells):
                    return cells
    raise RuntimeError("No hay espacio para colocar la huella editorial.")


def _neighbors(row: int, column: int, size: int) -> list[tuple[int, int]]:
    return [
        (next_row, next_column)
        for next_row, next_column in (
            (row, column + 1),
            (row + 1, column),
            (row, column - 1),
            (row - 1, column),
        )
        if 0 <= next_row < size and 0 <= next_column < size
    ]


def _crime_path(size: int, start: tuple[int, int], end: tuple[int, int], blocked: set[tuple[int, int]]) -> set[tuple[int, int]]:
    queue = [start]
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    for cell in queue:
        if cell == end:
            break
        for neighbor in _neighbors(*cell, size):
            if neighbor in previous or (neighbor in blocked and neighbor != end):
                continue
            previous[neighbor] = cell
            queue.append(neighbor)
    if end not in previous:
        return {start, end}

    path = {end}
    current = end
    while previous[current] is not None:
        current = previous[current]
        path.add(current)
    return path


def _zone(row: int, column: int, size: int) -> int:
    return int(row >= size // 2) * 2 + int(column >= size // 2)


def _components(cells: set[tuple[int, int]], size: int) -> list[list[tuple[int, int]]]:
    remaining = set(cells)
    result: list[list[tuple[int, int]]] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        remaining.remove(start)
        component = [start]
        while stack:
            cell = stack.pop()
            for neighbor in _neighbors(*cell, size):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
                    component.append(neighbor)
        result.append(sorted(component))
    return result


def _scaling_rooms(size: int, crime_cells: set[tuple[int, int]]) -> list[dict[str, Any]]:
    rooms: list[dict[str, Any]] = [{
        "id": "crime_room",
        "name": "Sala del crimen",
        "label_anchor": list(min(crime_cells)),
        "cells": sorted(crime_cells),
    }]
    by_zone: dict[int, set[tuple[int, int]]] = {}
    for row in range(size):
        for column in range(size):
            cell = (row, column)
            if cell not in crime_cells:
                by_zone.setdefault(_zone(row, column, size), set()).add(cell)

    room_index = 0
    for zone_cells in by_zone.values():
        for component in _components(zone_cells, size):
            room_id, name = ROOM_NAMES[room_index % len(ROOM_NAMES)]
            suffix = "" if room_index < len(ROOM_NAMES) else f"_{room_index}"
            rooms.append({
                "id": f"{room_id}{suffix}",
                "name": name,
                "label_anchor": list(component[len(component) // 2]),
                "cells": component,
            })
            room_index += 1
    return rooms


def _room_at(rooms: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {
        tuple(cell): room["id"]
        for room in rooms
        for cell in room["cells"]
    }


def make_scaling_characters(size: int) -> list[dict[str, Any]]:
    if size < 5 or size > len(NAMES):
        raise ValueError(f"El benchmark admite tamaños entre 5 y {len(NAMES)}.")
    return [
        {
            "id": f"person_{index + 1:02d}",
            "name": NAMES[index],
            "gender": "woman" if index % 2 == 0 else "man",
            "role": "victim" if index == 0 else "suspect",
        }
        for index in range(size)
    ]


def make_scaling_target(size: int, seed: int = 0) -> dict[str, tuple[int, int]]:
    characters = make_scaling_characters(size)
    rng = random.Random(seed)
    rows = list(range(size))
    columns = list(range(size))
    rng.shuffle(rows)
    rng.shuffle(columns)
    return {
        character["id"]: (rows[index], columns[index])
        for index, character in enumerate(characters)
    }


def make_scaling_board(size: int, seed: int = 0) -> dict[str, Any]:
    """Create deterministic rooms and furniture around the scalable target."""
    target = make_scaling_target(size, seed)
    row_perm = [row for row, _ in target.values()]
    column_perm = [column for _, column in target.values()]
    murderer_index = 1

    solution_cells = {
        (row_perm[index], column_perm[index])
        for index in range(size)
    }
    crime_cells = {
        (row_perm[0], column_perm[0]),
        (row_perm[murderer_index], column_perm[murderer_index]),
    }
    crime_room_cells = _crime_path(
        size,
        (row_perm[0], column_perm[0]),
        (row_perm[1], column_perm[1]),
        solution_cells - crime_cells,
    )
    rooms = _scaling_rooms(size, crime_room_cells)
    room_at = _room_at(rooms)
    plant_cell = (row_perm[3 % size], column_perm[3 % size])
    label_cells = {tuple(room["label_anchor"]) for room in rooms}
    blocked_for_objects = set(solution_cells) | crime_room_cells | label_cells
    table_cells = _place_footprint(
        [{(0, 0)}],
        size,
        room_at,
        blocked_for_objects,
        room_id=room_at[(row_perm[4 % size], column_perm[4 % size])],
        predicate=lambda cells: any(row == row_perm[4 % size] for row, _ in cells),
    )
    rug_cells = _place_footprint(
        [
            {(0, 0), (0, 1), (1, 0)},
            {(0, 0), (0, 1), (1, 0), (1, 1)},
            {(0, 0), (0, 1)},
            {(0, 0)},
        ],
        size,
        room_at,
        (blocked_for_objects - {(row_perm[5 % size], column_perm[5 % size])}) | table_cells,
        room_id=room_at[(row_perm[5 % size], column_perm[5 % size])],
        predicate=lambda cells: any(column == column_perm[5 % size] for _, column in cells),
    )
    sofa_cells = _place_footprint(
        [{(0, 0), (0, 1)}, {(0, 0), (1, 0)}, {(0, 0)}],
        size,
        room_at,
        blocked_for_objects | table_cells | rug_cells,
        predicate=lambda cells: any(
            abs(row_perm[6 % size] - row) + abs(column_perm[6 % size] - column) == 1
            for row, column in cells
        ),
    )
    bed_cells = _place_footprint(
        [{(0, 0), (1, 0)}, {(0, 0), (0, 1)}, {(0, 0)}],
        size,
        room_at,
        blocked_for_objects | table_cells | rug_cells | sofa_cells,
    )
    object_cells = {
        "plant": {plant_cell},
        "table": table_cells,
        "rug": rug_cells,
        "sofa": sofa_cells,
        "bed": bed_cells,
    }
    occupied = blocked_for_objects | table_cells | rug_cells | sofa_cells | bed_cells
    if size >= 8:
        for type_, shapes in (
            ("dining_table", [{(0, 0), (1, 0)}, {(0, 0), (0, 1)}]),
            ("bookshelf", [{(0, 0), (0, 1)}, {(0, 0), (1, 0)}]),
            ("wardrobe", [{(0, 0), (1, 0)}, {(0, 0), (0, 1)}]),
            (
                "counter",
                [
                    {(0, 0), (0, 1), (1, 0)},
                    {(0, 0), (0, 1), (1, 1)},
                    {(0, 0), (1, 0), (1, 1)},
                    {(0, 1), (1, 0), (1, 1)},
                ],
            ),
        ):
            room_ids = sorted(
                (room["id"] for room in rooms if room["id"] != "crime_room"),
                key=lambda room_id: sum(room_at[cell] == room_id for cell in occupied),
            )
            for room_id in room_ids:
                try:
                    cells = _place_footprint(shapes, size, room_at, occupied, room_id=room_id)
                    break
                except RuntimeError:
                    continue
            else:
                raise RuntimeError(f"No hay espacio para colocar {type_}.")
            object_cells[type_] = cells
            occupied |= cells
    objects = [
        _object("plant", object_cells["plant"], "gallery", occupiable=True),
        _object("table", object_cells["table"], "study"),
        _object("rug", object_cells["rug"], "lounge", occupiable=True),
        _object("sofa", object_cells["sofa"], "lounge", occupiable=True),
        _object("bed", object_cells["bed"], "bedroom"),
    ]
    objects.extend(
        _object(type_, cells, "editorial")
        for type_, cells in object_cells.items()
        if type_ in {"dining_table", "bookshelf", "wardrobe", "counter"}
    )
    board = {
        "id": f"scale_{size}x{size}",
        "name": "Murdoku",
        "rows": size,
        "columns": size,
        "room_groups": [{
            "id": "investigation_area",
            "name": "Zona de investigación",
            "rooms": [room["id"] for room in rooms if room["id"] != "crime_room"],
        }],
        "rooms": rooms,
        "objects": objects,
    }
    return board


def make_scaling_puzzle(size: int, seed: int = 0) -> dict[str, Any]:
    """Create a deterministic, unique synthetic puzzle for solver scalability tests.

    It deliberately uses only public clue types. The last suspect anchors the chain with
    exact row/column clues; every preceding suspect is fixed relative to the next. The
    victim is fixed by the remaining row/column plus the victim-room rule.
    """
    characters = make_scaling_characters(size)
    target = make_scaling_target(size, seed)
    row_perm = [target[character["id"]][0] for character in characters]
    column_perm = [target[character["id"]][1] for character in characters]
    board = make_scaling_board(size, seed)

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
            "text": clue_text("victim_rule", name=victim["name"]),
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
                    "args": {"character": character["id"], "row": row_perm[index]},
                    "text": f"{character['name']} estaba en la {row_perm[index] + 1}.ª fila.",
                },
                {
                    "id": f"card-{character['id']}-statement-2",
                    "type": "exact_column",
                    "family": "coordinate",
                    "args": {"character": character["id"], "column": column_perm[index]},
                    "text": f"{character['name']} estaba en la {column_perm[index] + 1}.ª columna.",
                },
            ]
        else:
            reference = characters[index + 1]
            row_delta = row_perm[index] - row_perm[index + 1]
            column_delta = column_perm[index] - column_perm[index + 1]
            statements = [
                {
                    "id": f"card-{character['id']}-statement-1",
                    "type": "relative_row_distance",
                    "family": "relative_distance",
                    "args": {"character": character["id"], "reference": reference["id"], "delta": row_delta},
                    "text": (
                        f"{character['name']} estaba {abs(row_delta)} fila"
                        f"{'s' if abs(row_delta) != 1 else ''} "
                        f"{'al sur' if row_delta > 0 else 'al norte'} de {reference['name']}."
                    ),
                },
                {
                    "id": f"card-{character['id']}-statement-2",
                    "type": "relative_column_distance",
                    "family": "relative_distance",
                    "args": {"character": character["id"], "reference": reference["id"], "delta": column_delta},
                    "text": (
                        f"{character['name']} estaba {abs(column_delta)} columna"
                        f"{'s' if abs(column_delta) != 1 else ''} "
                        f"{'al este' if column_delta > 0 else 'al oeste'} de {reference['name']}."
                    ),
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


def expected_scaling_solution(size: int, seed: int = 0) -> dict[str, tuple[int, int]]:
    return make_scaling_target(size, seed)


def _make_editorial_cards(
    puzzle: dict[str, Any],
    target: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    characters = {character["id"]: character for character in puzzle["characters"]}
    victim_id = puzzle["victim"]
    statements: dict[str, list[dict[str, Any]]] = {
        character_id: []
        for character_id in characters
        if character_id != victim_id
    }
    coordinate_anchors: set[str] = set()
    for dimension, coordinate_type, order_type, directions in (
        (0, "exact_row", "relative_row_order", ("north", "south")),
        (1, "exact_column", "relative_column_order", ("west", "east")),
    ):
        order = sorted(target, key=lambda character_id: target[character_id][dimension])
        endpoints = [character_id for character_id in (order[0], order[-1]) if character_id != victim_id]
        anchor = next(
            (character_id for character_id in endpoints if character_id not in coordinate_anchors),
            endpoints[0],
        )
        coordinate_anchors.add(anchor)
        victim_index = order.index(victim_id)
        for index, character_id in enumerate(order):
            if character_id == victim_id:
                continue
            reference = order[index + 1] if index < victim_index else order[index - 1]
            value = target[character_id][dimension]
            reference_value = target[reference][dimension]
            relation = directions[int(value > reference_value)]
            direction_text = {
                "north": "al norte",
                "south": "al sur",
                "west": "al oeste",
                "east": "al este",
            }[relation]
            if character_id == anchor:
                statement_type = coordinate_type
                family = "coordinate"
                args = {"character": character_id, coordinate_type.removeprefix("exact_"): value}
                text = clue_text(
                    "exact_edge",
                    name=characters[character_id]["name"],
                    edge={
                        (0, 0): "borde norte",
                        (0, len(order) - 1): "borde sur",
                        (1, 0): "borde oeste",
                        (1, len(order) - 1): "borde este",
                    }[(dimension, value)],
                )
            elif index % 2:
                statement_type = order_type.replace("_order", "_distance")
                family = "relative_distance"
                args = {
                    "character": character_id,
                    "reference": reference,
                    "delta": value - reference_value,
                }
                text = clue_text(
                    "relative_distance",
                    name=characters[character_id]["name"],
                    direction=direction_text,
                    reference=characters[reference]["name"],
                )
            else:
                statement_type = order_type
                family = "relative_order"
                args = {
                    "character": character_id,
                    "reference": reference,
                    "relation": relation,
                }
                text = clue_text(
                    "relative_order",
                    name=characters[character_id]["name"],
                    direction=direction_text,
                    reference=characters[reference]["name"],
                )
            statements[character_id].append({
                "id": "",
                "type": statement_type,
                "family": family,
                "args": args,
                "text": text,
            })

    victim_card = next(card for card in puzzle["cards"] if card["role"] == "victim")
    cards = [victim_card]
    for character_id, character_statements in statements.items():
        card_id = f"card-{character_id}"
        for index, statement in enumerate(character_statements, start=1):
            statement["id"] = f"{card_id}-statement-{index}"
        cards.append({
            "id": card_id,
            "character": character_id,
            "character_name": characters[character_id]["name"],
            "role": "suspect",
            "statements": character_statements,
        })
    return cards


def _suspect_clues_are_necessary(
    puzzle: dict[str, Any],
    expected: dict[str, tuple[int, int]],
) -> bool:
    probes: list[dict[str, str]] = []
    for card in puzzle["cards"]:
        if card["role"] == "victim":
            continue
        probes.append({"exclude_card_id": card["id"]})
        for statement in card["statements"]:
            probes.append({"exclude_statement_id": statement["id"]})

    def has_alternative(probe: dict[str, str]) -> bool:
        result = get_solver("ortools").solve(puzzle, limit=2, **probe)
        return len(result.solutions) > 1

    with ThreadPoolExecutor(max_workers=min(4, len(probes))) as executor:
        return all(executor.map(has_alternative, probes))


def _prune_implied_clues(
    puzzle: dict[str, Any],
    expected: dict[str, tuple[int, int]],
) -> list[str]:
    solver = get_solver("ortools")
    removed: list[str] = []
    changed = True
    while changed:
        changed = False
        for card in puzzle["cards"]:
            if card["role"] == "victim" or len(card["statements"]) <= 1:
                continue
            for index in range(len(card["statements"]) - 1, -1, -1):
                if len(card["statements"]) <= 1:
                    break
                statement = card["statements"].pop(index)
                result = solver.solve(puzzle, limit=2)
                if result.unique and result.solutions[0] == expected:
                    removed.append(statement["id"])
                    changed = True
                else:
                    card["statements"].insert(index, statement)
    return removed


def _substitute_editorial_clues(
    puzzle: dict[str, Any],
    expected: dict[str, tuple[int, int]],
    *,
    max_substitutions: int = 3,
    max_probes: int = 40,
) -> list[str]:
    pools = candidate_pools(puzzle, expected)
    solver = get_solver("ortools")
    priorities = {
        family: index
        for index, family in enumerate((
            "object_adjacency",
            "object_occupancy",
            "object_line",
            "room_composition",
            "room_population",
            "room_relation",
            "room_group",
            "room_exact",
        ))
    }
    changed: set[str] = set()
    selected: list[str] = []
    probes = 0
    for _ in range(max_substitutions):
        accepted = False
        for card in puzzle["cards"]:
            if card["role"] == "victim":
                continue
            candidates = sorted(
                (
                    candidate
                    for candidate in pools[card["character"]]
                    if candidate["family"] in priorities
                ),
                key=lambda candidate: priorities[candidate["family"]],
            )
            for index, original in enumerate(card["statements"]):
                if original["id"] in changed:
                    continue
                for candidate in candidates:
                    probes += 1
                    replacement = {**candidate, "id": original["id"]}
                    card["statements"][index] = replacement
                    result = solver.solve(puzzle, limit=2)
                    if (
                        result.unique
                        and result.solutions[0] == expected
                        and _suspect_clues_are_necessary(puzzle, expected)
                    ):
                        changed.add(original["id"])
                        selected.append(f"{original['id']}:{candidate['family']}")
                        accepted = True
                        break
                    card["statements"][index] = original
                    if probes >= max_probes:
                        return selected
                if accepted:
                    break
            if accepted:
                break
        if not accepted:
            break
    return selected


def generate_scaling_case(
    size: int,
    seed: int,
    output: Path,
    *,
    max_target_attempts: int = 16,
) -> dict[str, Any]:
    if max_target_attempts < 1:
        raise ValueError("max_target_attempts debe ser al menos 1")
    generation_started = time.perf_counter()
    editorial_clues: list[str] = []
    solver = get_solver("ortools")
    rejected_targets: list[int] = []
    for target_attempt in range(max_target_attempts):
        effective_seed = seed + target_attempt
        try:
            puzzle = make_scaling_puzzle(size, effective_seed)
        except RuntimeError:
            rejected_targets.append(effective_seed)
            continue
        expected = expected_scaling_solution(size, effective_seed)
        puzzle["cards"] = _make_editorial_cards(puzzle, expected)
        removed_clues = _prune_implied_clues(puzzle, expected)
        editorial_clues = _substitute_editorial_clues(puzzle, expected)
        result = solver.solve(puzzle, limit=2)
        if (
            result.available
            and result.unique
            and result.solutions[0] == expected
            and _suspect_clues_are_necessary(puzzle, expected)
        ):
            break
        rejected_targets.append(effective_seed)
    else:
        raise RuntimeError("No se encontró una base escalable única y necesaria.")
    elapsed_ms = (time.perf_counter() - generation_started) * 1000

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
    editorial_audit = audit_puzzle(puzzle)
    if not editorial_audit["accepted"]:
        raise RuntimeError(f"El audit editorial rechazó el puzle: {editorial_audit['errors']}")
    diagnostics = {
        "puzzle_id": puzzle["id"],
        "generator": "scaling_editorial",
        "size": size,
        "requested_seed": seed,
        "effective_seed": effective_seed,
        "target_attempts": target_attempt + 1,
        "rejected_target_seeds": rejected_targets,
        "editorial_clues": editorial_clues,
        "exact_validation": {
            "unique": result.unique,
            "matches_solution": True,
            "stats": result.stats.to_dict(),
        },
        "generation_ms": round(elapsed_ms, 3),
        "exact_explanation_available": True,
        "editorial_audit": editorial_audit,
        "all_suspect_clues_necessary": True,
        "removed_implied_clues": removed_clues,
    }
    explanation = explain_puzzle(puzzle)
    generation_report = {
        "puzzle_id": puzzle["id"],
        "summary": {
            "accepted": True,
            "method": "scaling_editorial",
            "size": size,
            "solver": result.stats.solver,
            "editorial_clues": editorial_clues,
        },
    }
    artifacts = {
        "puzzle": puzzle,
        "solution": solution,
        "diagnostics": diagnostics,
        "explanation": explanation,
        "generation_report": generation_report,
    }
    encoded = {
        name: json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        for name, data in artifacts.items()
    }
    manifest = {
        "schema_version": 1,
        "puzzle_id": puzzle["id"],
        "puzzle_schema_version": puzzle["schema_version"],
        "generator": "scaling_editorial",
        "generator_commit": os.environ.get("MURDOKU_COMMIT", "local"),
        "text_locale": "es",
        "text_version": text_catalog()["version"],
        "requested_seed": seed,
        "effective_seed": effective_seed,
        "editorial_status": "draft",
        "private_solution": {
            "path": "solution.json",
            "sha256": hashlib.sha256(encoded["solution"]).hexdigest(),
        },
        "public_puzzle": {
            "path": "puzzle.json",
            "sha256": hashlib.sha256(encoded["puzzle"]).hexdigest(),
        },
        "metrics": {
            "size": size,
            "generation_ms": diagnostics["generation_ms"],
            "unique": True,
            "all_suspect_clues_necessary": True,
            "families": sorted({
                statement["family"]
                for card in puzzle["cards"]
                for statement in card["statements"]
            }),
            "editorial_audit": editorial_audit,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, data in encoded.items():
        (output / f"{name}.json").write_bytes(data)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        **artifacts,
        "manifest": manifest,
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


def run_scaling_generation_regression(
    sizes: list[int],
    *,
    start_seed: int,
    count_per_size: int,
    budget_seconds: float,
    output: Path | None = None,
) -> dict[str, Any]:
    if count_per_size < 1:
        raise ValueError("count_per_size debe ser al menos 1")
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="murdoku-scale-regression-") as temp_root:
        root = Path(temp_root)
        for size in sizes:
            for offset in range(count_per_size):
                seed = start_seed + offset
                started = time.perf_counter()
                try:
                    result = generate_scaling_case(size, seed, root / f"{size}-{seed}")
                    error = None
                except Exception as exc:
                    result = None
                    error = f"{type(exc).__name__}: {exc}"
                elapsed = time.perf_counter() - started
                diagnostics = result["diagnostics"] if result else {}
                rows.append({
                    "size": size,
                    "seed": seed,
                    "success": result is not None,
                    "elapsed_seconds": round(elapsed, 3),
                    "within_budget": elapsed <= budget_seconds,
                    "unique": diagnostics.get("exact_validation", {}).get("unique", False),
                    "necessary": diagnostics.get("all_suspect_clues_necessary", False),
                    "target_attempts": diagnostics.get("target_attempts"),
                    "error": error,
                })
    report = {
        "sizes": sizes,
        "start_seed": start_seed,
        "count_per_size": count_per_size,
        "budget_seconds": budget_seconds,
        "cases": rows,
        "summary": {
            "total": len(rows),
            "successful": sum(row["success"] for row in rows),
            "all_unique": all(row["unique"] for row in rows),
            "all_necessary": all(row["necessary"] for row in rows),
            "all_within_budget": all(row["within_budget"] for row in rows),
        },
    }
    report["summary"]["accepted"] = all(
        report["summary"][key]
        for key in ("all_unique", "all_necessary", "all_within_budget")
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
