from __future__ import annotations

from typing import Any

from .clue_catalog import CLUE_SPECS
from .models import validate_puzzle
from .validator import matches_statement


def _object_phrase(name: str) -> str:
    article = "el" if name.casefold() in {"sofá", "armario", "mostrador", "televisor"} else "la"
    return f"{article} {name.casefold()}"


def candidate_pools(
    puzzle: dict[str, Any],
    target: dict[str, tuple[int, int]],
) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic, target-true clue candidates for each suspect."""
    validate_puzzle(puzzle)
    characters = {character["id"]: character for character in puzzle["characters"]}
    if set(target) != set(characters):
        raise ValueError("La solución debe contener exactamente los personajes del caso.")

    board = puzzle["board"]
    room_at = {
        tuple(cell): room["id"]
        for room in board["rooms"]
        for cell in room["cells"]
    }
    blocked = {
        tuple(cell)
        for obj in board.get("objects", [])
        if obj.get("blocks_character", False)
        for cell in obj["cells"]
    }
    if (
        any(position not in room_at for position in target.values())
        or any(position in blocked for position in target.values())
        or len({row for row, _ in target.values()}) != len(target)
        or len({column for _, column in target.values()}) != len(target)
    ):
        raise ValueError("La solución debe usar una casilla transitable por fila y columna.")

    room_names = {room["id"]: room["name"] for room in board["rooms"]}
    groups = {group["id"]: group for group in board.get("room_groups", [])}
    suspects = [character for character in puzzle["characters"] if character["role"] == "suspect"]
    pools: dict[str, list[dict[str, Any]]] = {}

    for character in suspects:
        character_id = character["id"]
        name = character["name"]
        row, column = target[character_id]
        room_id = room_at[(row, column)]
        room_occupants = [
            other_id
            for other_id, position in target.items()
            if room_at[position] == room_id
        ]
        candidates: list[tuple[str, dict[str, Any], str]] = [
            ("exact_row", {"row": row}, f"{name} estaba en la fila {row + 1}."),
            ("exact_column", {"column": column}, f"{name} estaba en la columna {column + 1}."),
            ("room", {"room": room_id}, f"{name} estaba en {room_names[room_id]}."),
            (
                "room_population",
                {"count": len(room_occupants)},
                f"Había {len(room_occupants)} personas en la habitación de {name}.",
            ),
        ]

        for gender in ("woman", "man"):
            count = sum(
                other_id != character_id and characters[other_id]["gender"] == gender
                for other_id in room_occupants
            )
            noun = (
                "mujer" if count == 1 and gender == "woman"
                else "hombre" if count == 1
                else "mujeres" if gender == "woman"
                else "hombres"
            )
            candidates.append((
                "companion_gender_count",
                {"gender": gender, "count": count},
                f"{name} compartía habitación con {count} {noun}.",
            ))

        for group_id, group in groups.items():
            if room_id in group["rooms"]:
                label = group.get("clue_label") or group.get("name") or group_id.replace("_", " ")
                candidates.append((
                    "in_room_group",
                    {"group": group_id},
                    f"{name} estaba en {label}.",
                ))

        for reference in puzzle["characters"]:
            if reference["id"] == character_id:
                continue
            reference_row, reference_column = target[reference["id"]]
            candidates.extend((
                (
                    "relative_row_distance",
                    {"reference": reference["id"], "delta": row - reference_row},
                    f"{name} estaba a otra altura que {reference['name']}.",
                ),
                (
                    "relative_column_distance",
                    {"reference": reference["id"], "delta": column - reference_column},
                    f"{name} estaba a otro lado de {reference['name']}.",
                ),
                (
                    "same_room" if room_id == room_at[(reference_row, reference_column)] else "different_room",
                    {"reference": reference["id"]},
                    f"{name} estaba en una habitación "
                    f"{'igual' if room_id == room_at[(reference_row, reference_column)] else 'distinta'} "
                    f"a {reference['name']}.",
                ),
            ))
            if row != reference_row:
                relation = "north" if row < reference_row else "south"
                candidates.append((
                    "relative_row_order",
                    {"reference": reference["id"], "relation": relation},
                    f"{name} estaba {'al norte' if relation == 'north' else 'al sur'} de {reference['name']}.",
                ))
            if column != reference_column:
                relation = "west" if column < reference_column else "east"
                candidates.append((
                    "relative_column_order",
                    {"reference": reference["id"], "relation": relation},
                    f"{name} estaba {'al oeste' if relation == 'west' else 'al este'} de {reference['name']}.",
                ))

        for obj in board.get("objects", []):
            cells = {tuple(cell) for cell in obj["cells"]}
            phrase = _object_phrase(obj["name"])
            if (row, column) in cells and obj.get("occupiable", False):
                candidates.append((
                    "unique_on_object",
                    {"object_type": obj["type"]},
                    f"{name} estaba sobre {phrase}.",
                ))
            if any(
                abs(row - obj_row) + abs(column - obj_column) == 1
                and room_at[(obj_row, obj_column)] == room_id
                for obj_row, obj_column in cells
            ):
                candidates.append((
                    "adjacent_object",
                    {"object_type": obj["type"]},
                    f"{name} estaba al lado de {phrase}.",
                ))
            if any(obj_row == row and room_at[(obj_row, obj_column)] == room_id for obj_row, obj_column in cells):
                candidates.append((
                    "object_same_row_in_room",
                    {"object_type": obj["type"]},
                    f"{name} estaba en la misma fila y habitación que {phrase}.",
                ))
            if any(obj_column == column and room_at[(obj_row, obj_column)] == room_id for obj_row, obj_column in cells):
                candidates.append((
                    "object_same_column_in_room",
                    {"object_type": obj["type"]},
                    f"{name} estaba en la misma columna y habitación que {phrase}.",
                ))

        pool = []
        for index, (type_, args, text) in enumerate(candidates, start=1):
            statement = {
                "id": f"candidate-{character_id}-{index}",
                "type": type_,
                "family": CLUE_SPECS[type_].family,
                "args": {"character": character_id, **args},
                "text": text,
            }
            if matches_statement(statement, target, puzzle):
                pool.append(statement)
        pools[character_id] = pool

    return pools
