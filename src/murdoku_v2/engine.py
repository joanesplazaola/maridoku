from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any

import numpy as np

from .clue_catalog import AtomicClue, CLUE_SPECS, atomic_mask, catalog_json
from .selector import global_select_cards
from .dependency import analyze_card_dependencies


CHARACTERS = [
    {"id": "alicia", "name": "Alicia", "gender": "woman"},
    {"id": "bruno", "name": "Bruno", "gender": "man"},
    {"id": "carla", "name": "Carla", "gender": "woman"},
    {"id": "diego", "name": "Diego", "gender": "man"},
    {"id": "elena", "name": "Elena", "gender": "woman"},
    {"id": "fabio", "name": "Fabio", "gender": "man"},
]

GENDER_NOUN = {"woman": "mujer", "man": "hombre"}
NUMBER_WORD = {0: "cero", 1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis"}
RICH_FAMILIES = {
    "object_occupancy",
    "object_line",
    "room_composition",
    "room_population",
    "room_companion",
    "room_geometry",
    "room_group",
    "room_choice",
}

GENERATION_PROFILES = {"any", "easy", "medium", "hard", "expert"}


def object_cells(obj: dict[str, Any]) -> list[tuple[int, int]]:
    """Return every board cell occupied by an object (V2-alpha supports footprints)."""
    if "cells" in obj:
        return [(int(row), int(column)) for row, column in obj["cells"]]
    return [(int(obj["row"]), int(obj["column"]))]


def object_flat_cells(obj: dict[str, Any], columns: int) -> list[int]:
    return [row * columns + column for row, column in object_cells(obj)]


def blocked_character_cells(board: dict[str, Any]) -> set[int]:
    columns = int(board["columns"])
    return {
        cell
        for obj in board.get("objects", [])
        if obj.get("blocks_character", False)
        for cell in object_flat_cells(obj, columns)
    }


def _normalise_profile(profile: str | None) -> str:
    value = (profile or "any").lower()
    if value not in GENERATION_PROFILES:
        raise ValueError(f"Perfil de generación desconocido: {profile}")
    return value


def _profile_limits(profile: str) -> dict[str, Any]:
    profile = _normalise_profile(profile)
    return {
        "any": {"min_families": 3, "max_coordinates": 1, "max_relatives": 3, "min_rich": 1},
        "easy": {"min_families": 3, "max_coordinates": 2, "max_relatives": 2, "min_rich": 1},
        "medium": {"min_families": 3, "max_coordinates": 1, "max_relatives": 3, "min_rich": 1},
        "hard": {"min_families": 4, "max_coordinates": 1, "max_relatives": 2, "min_rich": 3},
        "expert": {"min_families": 4, "max_coordinates": 0, "max_relatives": 2, "min_rich": 3},
    }[profile]



def load_board(path: Path) -> dict[str, Any]:
    board = json.loads(path.read_text(encoding="utf-8"))
    rows = int(board["rows"])
    columns = int(board["columns"])
    if rows != columns:
        raise ValueError("La V2-alpha exige un tablero cuadrado.")
    if rows != len(CHARACTERS):
        raise ValueError("La V2-alpha exige tantas filas y columnas como personajes.")

    occupied: set[tuple[int, int]] = set()
    room_ids: set[str] = set()
    room_by_cell: dict[tuple[int, int], str] = {}
    for room in board["rooms"]:
        if room["id"] in room_ids:
            raise ValueError(f"Habitación repetida: {room['id']}")
        room_ids.add(room["id"])
        for raw_cell in room["cells"]:
            cell = tuple(raw_cell)
            if cell in occupied:
                raise ValueError(f"Casilla repetida entre habitaciones: {cell}")
            occupied.add(cell)
            room_by_cell[cell] = room["id"]
    expected = {(row, column) for row in range(rows) for column in range(columns)}
    if occupied != expected:
        raise ValueError("Las habitaciones deben cubrir el tablero exactamente una vez.")

    grouped_rooms: set[str] = set()
    for group in board.get("room_groups", []):
        for room_id in group["rooms"]:
            if room_id not in room_ids:
                raise ValueError(f"El grupo {group['id']} referencia una habitación inexistente: {room_id}")
            if room_id in grouped_rooms:
                raise ValueError(f"La habitación {room_id} aparece en más de un grupo.")
            grouped_rooms.add(room_id)

    objects_by_cell: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for obj in board.get("objects", []):
        cells = object_cells(obj)
        if not cells or len(set(cells)) != len(cells):
            raise ValueError(f"Huella inválida en el objeto: {obj['id']}")
        if any(cell not in expected for cell in cells):
            raise ValueError(f"Objeto fuera del tablero: {obj['id']}")
        object_rooms = {room_by_cell[cell] for cell in cells}
        if len(object_rooms) != 1:
            raise ValueError(f"El objeto {obj['id']} atraviesa paredes o habitaciones.")
        obj["cells"] = [[row, column] for row, column in cells]
        obj["row"], obj["column"] = cells[0]  # compatibilidad con herramientas antiguas
        for cell in cells:
            objects_by_cell.setdefault(cell, []).append(obj)

    # V2-alpha deliberately uses a tiny, explicit compatibility matrix.
    for cell, objects in objects_by_cell.items():
        if len(objects) <= 1:
            continue
        types = sorted(obj["type"] for obj in objects)
        if types != ["chair", "rug"]:
            ids = ", ".join(obj["id"] for obj in objects)
            raise ValueError(f"Objetos incompatibles en {cell}: {ids}")

    occupied_object_cells = set(objects_by_cell)
    for room in board["rooms"]:
        anchor = tuple(room.get("label_anchor", room["cells"][0]))
        if anchor not in {tuple(cell) for cell in room["cells"]}:
            raise ValueError(f"El rótulo de {room['id']} no está dentro de la habitación.")
        if anchor in occupied_object_cells:
            raise ValueError(f"El rótulo de {room['id']} tapa un objeto en {anchor}.")
        room["label_anchor"] = list(anchor)
    return board


def build_board_arrays(
    board: dict[str, Any],
) -> tuple[np.ndarray, list[str], dict[str, str], dict[str, int], dict[str, set[int]]]:
    rows = board["rows"]
    columns = board["columns"]
    room_ids = [room["id"] for room in board["rooms"]]
    room_names = {room["id"]: room["name"] for room in board["rooms"]}
    room_index = {room_id: index for index, room_id in enumerate(room_ids)}
    room_flat = np.empty(rows * columns, dtype=np.uint8)
    for room in board["rooms"]:
        index = room_index[room["id"]]
        for row, column in room["cells"]:
            room_flat[row * columns + column] = index

    group_room_indexes = {
        group["id"]: {room_index[room_id] for room_id in group["rooms"]}
        for group in board.get("room_groups", [])
    }
    return room_flat, room_ids, room_names, room_index, group_room_indexes


def enumerate_base_solutions(board: dict[str, Any]) -> np.ndarray:
    """All assignments with one character per row/column and no character on blocked furniture."""
    n = board["rows"]
    perms = np.asarray(list(permutations(range(n))), dtype=np.uint8)
    row_assignments = np.repeat(perms, len(perms), axis=0)
    column_assignments = np.tile(perms, (len(perms), 1))
    assignments = row_assignments * n + column_assignments
    blocked = blocked_character_cells(board)
    if blocked:
        assignments = assignments[~np.any(np.isin(assignments, list(blocked)), axis=1)]
    return assignments


def apply_victim_rule(solutions: np.ndarray, victim_index: int, room_flat: np.ndarray) -> np.ndarray:
    solution_rooms = room_flat[solutions]
    victim_rooms = solution_rooms[:, [victim_index]]
    return solutions[np.sum(solution_rooms == victim_rooms, axis=1) == 2]


def board_geometry(board: dict[str, Any], room_flat: np.ndarray) -> dict[str, Any]:
    rows = board["rows"]
    columns = board["columns"]
    no_wall_cells: set[int] = set()
    corner_cells: set[int] = set()
    walls_by_cell: dict[int, dict[str, bool]] = {}

    for row in range(rows):
        for column in range(columns):
            cell = row * columns + column
            own_room = int(room_flat[cell])
            walls = {
                "north": row == 0 or int(room_flat[(row - 1) * columns + column]) != own_room,
                "south": row == rows - 1 or int(room_flat[(row + 1) * columns + column]) != own_room,
                "west": column == 0 or int(room_flat[row * columns + column - 1]) != own_room,
                "east": column == columns - 1 or int(room_flat[row * columns + column + 1]) != own_room,
            }
            walls_by_cell[cell] = walls
            if not any(walls.values()):
                no_wall_cells.add(cell)
            if (walls["north"] or walls["south"]) and (walls["west"] or walls["east"]):
                corner_cells.add(cell)

    return {
        "no_wall_cells": no_wall_cells,
        "corner_cells": corner_cells,
        "walls_by_cell": walls_by_cell,
    }


def _room_phrase(name: str) -> str:
    lowered = name[0].lower() + name[1:]
    first = lowered.split()[0].strip(".,:;")
    feminine = {
        "cocina", "habitación", "recepción", "zona", "terraza", "entrada",
        "despensa", "barra", "pradera", "cabaña", "biblioteca", "galería",
        "hoguera", "mansión", "planta", "sala", "estancia",
    }
    feminine_plural = {"zonas", "estancias"}
    masculine_plural = {"aseos", "jardines", "dormitorios", "salones"}
    if first in feminine_plural:
        article = "las"
    elif first in masculine_plural:
        article = "los"
    elif first in feminine:
        article = "la"
    else:
        article = "el"
    return f"{article} {lowered}"


def _gendered_alone(character: dict[str, Any]) -> str:
    return "sola" if character["gender"] == "woman" else "solo"


def _plural_gender(gender: str, count: int) -> str:
    if gender == "woman":
        return "mujer" if count == 1 else "mujeres"
    return "hombre" if count == 1 else "hombres"


def _object_article(object_type: str) -> str:
    return "un" if object_type in {"sofa"} else "una"


def _unique_object_text(character: dict[str, Any], object_type: str) -> str:
    name = character["name"]
    if object_type == "chair":
        ending = "sentada" if character["gender"] == "woman" else "sentado"
        article = "la única" if character["gender"] == "woman" else "el único"
        return f"{name} era {article} {ending} en una silla."
    if object_type == "bed":
        return f"{name} era la única persona en una cama."
    if object_type == "rug":
        return f"{name} era la única persona sobre una alfombra."
    if object_type == "sofa":
        return f"{name} era la única persona sentada en un sofá."
    return f"{name} era la única persona sobre un objeto de tipo {object_type}."


def _relative_order_text(subject: str, relation: str, reference: str) -> str:
    direction = {
        "north": "al norte de",
        "south": "al sur de",
        "east": "al este de",
        "west": "al oeste de",
    }[relation]
    return f"{subject} estaba {direction} {reference}."


def _relative_distance_text(subject: str, relation: str, distance: int, reference: str) -> str:
    unit = "fila" if relation in {"north", "south"} else "columna"
    plural = "s" if distance != 1 else ""
    direction = {
        "north": "al norte de",
        "south": "al sur de",
        "east": "al este de",
        "west": "al oeste de",
    }[relation]
    return f"{subject} estaba {distance} {unit}{plural} {direction} {reference}."


def generate_atomic_candidates(
    target: np.ndarray,
    board: dict[str, Any],
    room_flat: np.ndarray,
    room_ids: list[str],
    room_names: dict[str, str],
    room_index: dict[str, int],
    group_room_indexes: dict[str, set[int]],
    geometry: dict[str, Any],
    victim_index: int,
) -> tuple[dict[str, list[AtomicClue]], int]:
    n = board["rows"]
    target_rows = target // n
    target_columns = target % n
    target_rooms = room_flat[target]
    victim_room = int(target_rooms[victim_index])
    murderer_indexes = [
        index for index, room in enumerate(target_rooms)
        if int(room) == victim_room and index != victim_index
    ]
    if len(murderer_indexes) != 1:
        raise AssertionError("La solución objetivo no cumple la regla de la víctima.")
    murderer_index = murderer_indexes[0]

    objects_by_type: dict[str, list[dict[str, Any]]] = {}
    for obj in board.get("objects", []):
        object_copy = dict(obj)
        cells = object_cells(obj)
        object_copy["cells"] = cells
        object_copy["flat_cells"] = [row * n + column for row, column in cells]
        object_copy["room_index"] = int(room_flat[object_copy["flat_cells"][0]])
        objects_by_type.setdefault(obj["type"], []).append(object_copy)

    groups_by_room: dict[int, list[dict[str, Any]]] = {}
    for group in board.get("room_groups", []):
        for idx in group_room_indexes[group["id"]]:
            groups_by_room.setdefault(idx, []).append(group)

    gender_indexes = {
        gender: [index for index, character in enumerate(CHARACTERS) if character["gender"] == gender]
        for gender in GENDER_NOUN
    }

    by_subject: dict[str, list[AtomicClue]] = {}
    for char_index, character in enumerate(CHARACTERS):
        if char_index == victim_index:
            continue
        subject_id = character["id"]
        subject_name = character["name"]
        row = int(target_rows[char_index])
        column = int(target_columns[char_index])
        cell = int(target[char_index])
        room_idx = int(target_rooms[char_index])
        room_id = room_ids[room_idx]
        room_phrase = _room_phrase(room_names[room_id])
        candidates: list[AtomicClue] = []

        candidates.append(AtomicClue(
            subject_id,
            "room",
            "room_exact",
            {"character": subject_id, "room": room_id},
            f"{subject_name} estaba en {room_phrase}.",
            complexity=1.0,
            directness=1.55,
        ))
        candidates.append(AtomicClue(
            subject_id,
            "exact_row",
            "coordinate",
            {"character": subject_id, "row": row},
            f"{subject_name} estaba en la {row + 1}.ª fila.",
            complexity=0.9,
            directness=1.8,
        ))
        candidates.append(AtomicClue(
            subject_id,
            "exact_column",
            "coordinate",
            {"character": subject_id, "column": column},
            f"{subject_name} estaba en la {column + 1}.ª columna.",
            complexity=0.9,
            directness=1.8,
        ))

        room_count = int(np.sum(target_rooms == room_idx))
        candidates.append(AtomicClue(
            subject_id,
            "room_population",
            "room_population",
            {"character": subject_id, "count": room_count},
            f"En la habitación de {subject_name} había exactamente {room_count} persona{'s' if room_count != 1 else ''}.",
            complexity=1.35,
        ))
        if room_count == 1:
            candidates.append(AtomicClue(
                subject_id,
                "alone_in_room",
                "room_population",
                {"character": subject_id, "room": room_id},
                f"{subject_name} estaba {_gendered_alone(character)} en {room_phrase}.",
                complexity=1.15,
                directness=0.65,
            ))

        for gender, indexes in gender_indexes.items():
            total_count = sum(int(target_rooms[index]) == room_idx for index in indexes)
            if total_count > 0:
                noun = _plural_gender(gender, total_count)
                candidates.append(AtomicClue(
                    subject_id,
                    "room_gender_count",
                    "room_composition",
                    {"character": subject_id, "gender": gender, "count": total_count},
                    f"Había exactamente {NUMBER_WORD[total_count]} {noun} en la habitación de {subject_name}.",
                    complexity=1.45,
                ))
            companion_count = total_count - int(character["gender"] == gender)
            companion_noun = _plural_gender(gender, companion_count)
            if companion_count > 0:
                candidates.append(AtomicClue(
                    subject_id,
                    "companion_gender_count",
                    "room_companion",
                    {"character": subject_id, "gender": gender, "count": companion_count},
                    f"{subject_name} estaba con exactamente {NUMBER_WORD[companion_count]} {companion_noun}.",
                    complexity=1.5,
                ))

        if room_count == 2:
            companion_index = next(
                index for index, room in enumerate(target_rooms)
                if int(room) == room_idx and index != char_index
            )
            companion_gender = CHARACTERS[companion_index]["gender"]
            candidates.append(AtomicClue(
                subject_id,
                "alone_with_gender",
                "room_companion",
                {"character": subject_id, "gender": companion_gender},
                f"{subject_name} estaba a solas con {'una mujer' if companion_gender == 'woman' else 'un hombre'}.",
                complexity=1.45,
            ))

        if cell in geometry["no_wall_cells"]:
            candidates.append(AtomicClue(
                subject_id,
                "not_adjacent_to_wall",
                "room_geometry",
                {"character": subject_id},
                f"{subject_name} no estaba junto a ninguna pared.",
                complexity=1.25,
            ))
        if cell in geometry["corner_cells"]:
            candidates.append(AtomicClue(
                subject_id,
                "in_room_corner",
                "room_geometry",
                {"character": subject_id},
                f"{subject_name} estaba en una esquina de su habitación.",
                complexity=1.15,
            ))

        for group in groups_by_room.get(room_idx, []):
            candidates.append(AtomicClue(
                subject_id,
                "in_room_group",
                "room_group",
                {"character": subject_id, "group": group["id"]},
                f"{subject_name} estaba en {group['clue_label']}.",
                complexity=1.25,
                directness=0.35,
            ))

        # True disjunctions between the actual room and another room.
        other_room_ids = [candidate for candidate in room_ids if candidate != room_id]
        for alternative_room_id in other_room_ids:
            candidates.append(AtomicClue(
                subject_id,
                "room_disjunction",
                "room_choice",
                {"character": subject_id, "rooms": sorted([room_id, alternative_room_id])},
                f"{subject_name} estaba en {room_phrase} o en {_room_phrase(room_names[alternative_room_id])}.",
                complexity=1.35,
                directness=0.25,
            ))

        for object_type, objects in objects_by_type.items():
            object_name = objects[0]["name"].lower()
            occupiable_cells = {flat for obj in objects if obj.get("occupiable", False) for flat in obj["flat_cells"]}
            occupied_on_type = [index for index, position in enumerate(target) if int(position) in occupiable_cells]
            if cell in occupiable_cells and occupied_on_type == [char_index]:
                candidates.append(AtomicClue(
                    subject_id,
                    "unique_on_object",
                    "object_occupancy",
                    {"character": subject_id, "object_type": object_type},
                    _unique_object_text(character, object_type),
                    complexity=1.55,
                ))

            same_row_same_room = any(any(cell_row == row for cell_row, _ in obj["cells"]) and obj["room_index"] == room_idx for obj in objects)
            same_column_same_room = any(any(cell_column == column for _, cell_column in obj["cells"]) and obj["room_index"] == room_idx for obj in objects)
            if same_row_same_room:
                candidates.append(AtomicClue(
                    subject_id,
                    "object_same_row_in_room",
                    "object_line",
                    {"character": subject_id, "object_type": object_type},
                    f"Había {_object_article(object_type)} {object_name} en la misma fila que {subject_name}, dentro de su habitación.",
                    complexity=1.4,
                ))
            if same_column_same_room:
                candidates.append(AtomicClue(
                    subject_id,
                    "object_same_column_in_room",
                    "object_line",
                    {"character": subject_id, "object_type": object_type},
                    f"Había {_object_article(object_type)} {object_name} en la misma columna que {subject_name}, dentro de su habitación.",
                    complexity=1.4,
                ))

            if any(abs(row - cell_row) + abs(column - cell_column) == 1 for obj in objects for cell_row, cell_column in obj["cells"]):
                candidates.append(AtomicClue(
                    subject_id,
                    "adjacent_object",
                    "object_adjacency",
                    {"character": subject_id, "object_type": object_type},
                    f"{subject_name} estaba junto a {_object_article(object_type)} {object_name}.",
                    complexity=1.0,
                ))

        for reference_index, reference in enumerate(CHARACTERS):
            if reference_index == char_index:
                continue
            reference_name = reference["name"]
            row_delta = int(target_rows[char_index]) - int(target_rows[reference_index])
            column_delta = int(target_columns[char_index]) - int(target_columns[reference_index])

            row_relation = "north" if row_delta < 0 else "south"
            candidates.append(AtomicClue(
                subject_id,
                "relative_row_order",
                "relative_order",
                {"character": subject_id, "reference": reference["id"], "relation": row_relation},
                _relative_order_text(subject_name, row_relation, reference_name),
                complexity=1.0,
            ))
            if abs(row_delta) <= 3:
                candidates.append(AtomicClue(
                    subject_id,
                    "relative_row_distance",
                    "relative_distance",
                    {"character": subject_id, "reference": reference["id"], "delta": row_delta},
                    _relative_distance_text(subject_name, row_relation, abs(row_delta), reference_name),
                    complexity=1.25 + 0.08 * abs(row_delta),
                    directness=0.45,
                ))

            column_relation = "west" if column_delta < 0 else "east"
            candidates.append(AtomicClue(
                subject_id,
                "relative_column_order",
                "relative_order",
                {"character": subject_id, "reference": reference["id"], "relation": column_relation},
                _relative_order_text(subject_name, column_relation, reference_name),
                complexity=1.0,
            ))
            if abs(column_delta) <= 3:
                candidates.append(AtomicClue(
                    subject_id,
                    "relative_column_distance",
                    "relative_distance",
                    {"character": subject_id, "reference": reference["id"], "delta": column_delta},
                    _relative_distance_text(subject_name, column_relation, abs(column_delta), reference_name),
                    complexity=1.25 + 0.08 * abs(column_delta),
                    directness=0.45,
                ))

            same_room = int(target_rooms[char_index]) == int(target_rooms[reference_index])
            # Naming the victim's sole companion directly would reveal the murderer.
            if not (reference_index == victim_index and same_room):
                candidates.append(AtomicClue(
                    subject_id,
                    "same_room" if same_room else "different_room",
                    "room_relation",
                    {"character": subject_id, "reference": reference["id"]},
                    (
                        f"{subject_name} estaba en la misma habitación que {reference_name}."
                        if same_room
                        else f"{subject_name} estaba en una habitación diferente a {reference_name}."
                    ),
                    complexity=1.15,
                ))

        by_subject[subject_id] = candidates

    return by_subject, murderer_index


def _bool_mask_to_bits(mask: np.ndarray) -> int:
    packed = np.packbits(mask, bitorder="little")
    return int.from_bytes(packed.tobytes(), "little")


def _intersection_bits(cards: dict[str, list[AtomicClue]], bit_masks: dict[str, int], all_bits: int) -> int:
    result = all_bits
    for atoms in cards.values():
        for atom in atoms:
            result &= bit_masks[atom.key]
    return result


def _quality_ok(cards: dict[str, list[AtomicClue]], profile: str = "any") -> bool:
    profile = _normalise_profile(profile)
    limits = _profile_limits(profile)
    atoms = [atom for card in cards.values() for atom in card]
    families = [atom.family for atom in atoms]
    if len(set(families)) < limits["min_families"]:
        return False
    if sum(family in RICH_FAMILIES for family in families) < limits["min_rich"]:
        return False
    if sum(family == "coordinate" for family in families) > limits["max_coordinates"]:
        return False
    if sum(family in {"relative_order", "relative_distance"} for family in families) > limits["max_relatives"]:
        return False
    if any(families.count(family) > 3 for family in set(families)):
        return False

    direct_count = sum(atom.family in {"coordinate", "room_exact"} for atom in atoms)
    directness = sum(atom.directness for atom in atoms)
    average_complexity = sum(atom.complexity for atom in atoms) / max(1, len(atoms))
    double_count = sum(len(card) == 2 for card in cards.values())

    if profile == "easy":
        # Easy cases should expose at least two strong anchors and avoid double cards.
        return direct_count >= 2 and double_count == 0 and average_complexity <= 1.35
    if profile == "medium":
        return direct_count <= 2 and double_count <= 1
    if profile == "hard":
        return direct_count <= 1 and directness <= 4.5 and average_complexity >= 1.2
    if profile == "expert":
        return direct_count == 0 and directness <= 2.8 and average_complexity >= 1.3
    return True


def _atom_selection_score(
    atom: AtomicClue,
    before: int,
    after: int,
    family_counts: dict[str, int],
    profile: str,
) -> float:
    profile = _normalise_profile(profile)
    gain = math.log2(before / after)
    novelty = 1.45 if family_counts.get(atom.family, 0) == 0 else 0.76
    rich_bonus = 1.18 if atom.family in RICH_FAMILIES else 1.0
    overpowered_penalty = 1.0 + max(0.0, gain - 5.0) * 0.55

    if profile == "easy":
        anchor_bonus = 1.65 if atom.family in {"coordinate", "room_exact"} else 1.0
        simple_bonus = 1.25 if atom.family in {"object_adjacency", "room_population", "object_occupancy"} else 1.0
        return (gain ** 1.15) * novelty * anchor_bonus * simple_bonus / max(0.65, atom.complexity ** 1.25)
    if profile == "hard":
        moderate_gain = 1.25 if 1.0 <= gain <= 4.2 else 0.78
        return gain * novelty * rich_bonus * (atom.complexity ** 1.15) * moderate_gain / (1.0 + atom.directness * 2.0)
    if profile == "expert":
        subtle_gain = 1.3 if 0.5 <= gain <= 3.4 else 0.65
        cross_bonus = 1.2 if atom.family in {"room_composition", "room_companion", "object_line", "room_choice", "relative_order"} else 1.0
        return gain * novelty * rich_bonus * (atom.complexity ** 1.35) * subtle_gain * cross_bonus / (1.0 + atom.directness * 3.0)
    return gain * novelty * rich_bonus / (atom.complexity * (1.0 + atom.directness) * overpowered_penalty)


def _minimise_double_cards_bits(
    cards: dict[str, list[AtomicClue]],
    bit_masks: dict[str, int],
    all_bits: int,
    target_bit: int,
) -> dict[str, list[AtomicClue]]:
    cards = {subject: list(atoms) for subject, atoms in cards.items()}
    changed = True
    while changed:
        changed = False
        for subject, atoms in list(cards.items()):
            if len(atoms) != 2:
                continue
            for remove_index in range(2):
                trial = {key: list(value) for key, value in cards.items()}
                trial[subject].pop(remove_index)
                combined = _intersection_bits(trial, bit_masks, all_bits)
                if combined.bit_count() == 1 and combined & target_bit:
                    cards = trial
                    changed = True
                    break
            if changed:
                break
    return cards


def _necessity_metrics_bits(
    cards: dict[str, list[AtomicClue]],
    bit_masks: dict[str, int],
    all_bits: int,
    target_bit: int,
) -> tuple[bool, bool, dict[str, int], dict[str, int]]:
    card_without_counts: dict[str, int] = {}
    statement_without_counts: dict[str, int] = {}
    all_cards_necessary = True
    all_statements_necessary = True

    for subject in cards:
        trial = {key: list(value) for key, value in cards.items() if key != subject}
        combined = _intersection_bits(trial, bit_masks, all_bits)
        count = combined.bit_count()
        card_without_counts[subject] = count
        if count <= 1 or not (combined & target_bit):
            all_cards_necessary = False

    for subject, atoms in cards.items():
        for index, atom in enumerate(atoms):
            trial = {key: list(value) for key, value in cards.items()}
            trial[subject].pop(index)
            combined = _intersection_bits(trial, bit_masks, all_bits)
            count = combined.bit_count()
            statement_without_counts[atom.key] = count
            if count <= 1 or not (combined & target_bit):
                all_statements_necessary = False

    return all_cards_necessary, all_statements_necessary, card_without_counts, statement_without_counts


def _single_card_dfs(
    pools: dict[str, list[AtomicClue]],
    bit_masks: dict[str, int],
    all_bits: int,
    target_bit: int,
    rng: random.Random,
    profile: str = "any",
) -> dict[str, list[AtomicClue]] | None:
    subjects = list(pools)
    for _ in range(36):
        order = subjects[:]
        rng.shuffle(order)
        node_budget = 9000
        nodes = 0

        def dfs(
            depth: int,
            current: int,
            cards: dict[str, list[AtomicClue]],
            family_counts: dict[str, int],
        ) -> dict[str, list[AtomicClue]] | None:
            nonlocal nodes
            nodes += 1
            if nodes > node_budget:
                return None
            if depth == len(order):
                if current.bit_count() != 1 or not (current & target_bit):
                    return None
                if not _quality_ok(cards, profile):
                    return None
                all_cards, all_statements, _, _ = _necessity_metrics_bits(cards, bit_masks, all_bits, target_bit)
                return cards if all_cards and all_statements else None

            subject = order[depth]
            before = current.bit_count()
            remaining_subjects = len(order) - depth - 1
            scored: list[tuple[float, AtomicClue, int]] = []
            for atom in pools[subject]:
                combined = current & bit_masks[atom.key]
                after = combined.bit_count()
                if after == 0 or after == before or not (combined & target_bit):
                    continue
                if remaining_subjects > 0 and after == 1:
                    continue
                if atom.family == "coordinate" and family_counts.get("coordinate", 0) >= 1:
                    continue
                if atom.family in {"relative_order", "relative_distance"} and sum(
                    family_counts.get(family, 0) for family in {"relative_order", "relative_distance"}
                ) >= 3:
                    continue
                score = _atom_selection_score(atom, before, after, family_counts, profile)
                score *= rng.uniform(0.88, 1.12)
                scored.append((score, atom, combined))

            scored.sort(key=lambda item: item[0], reverse=True)
            for _, atom, combined in scored[:20]:
                next_cards = {key: list(value) for key, value in cards.items()}
                next_cards[subject] = [atom]
                next_counts = dict(family_counts)
                next_counts[atom.family] = next_counts.get(atom.family, 0) + 1
                found = dfs(depth + 1, combined, next_cards, next_counts)
                if found is not None:
                    return found
            return None

        found = dfs(0, all_bits, {}, {})
        if found is not None:
            return found
    return None


def _randomized_search_with_doubles(
    pools: dict[str, list[AtomicClue]],
    bit_masks: dict[str, int],
    all_bits: int,
    target_bit: int,
    rng: random.Random,
    profile: str = "any",
    attempts: int = 5000,
) -> dict[str, list[AtomicClue]] | None:
    subjects = list(pools)
    best: dict[str, list[AtomicClue]] | None = None
    best_score = math.inf

    for _ in range(attempts):
        order = subjects[:]
        rng.shuffle(order)
        current = all_bits
        cards: dict[str, list[AtomicClue]] = {}
        family_counts: dict[str, int] = {}
        failed = False

        for position, subject in enumerate(order):
            before = current.bit_count()
            remaining_subjects = len(order) - position - 1
            scored: list[tuple[float, AtomicClue, int]] = []
            for atom in pools[subject]:
                combined = current & bit_masks[atom.key]
                after = combined.bit_count()
                if after == 0 or after == before or not (combined & target_bit):
                    continue
                if remaining_subjects > 0 and after == 1:
                    continue
                if atom.family == "coordinate" and family_counts.get("coordinate", 0) >= 1:
                    continue
                score = _atom_selection_score(atom, before, after, family_counts, profile)
                score *= rng.uniform(0.8, 1.2)
                scored.append((score, atom, combined))
            if not scored:
                failed = True
                break
            scored.sort(key=lambda item: item[0], reverse=True)
            shortlist = scored[:10]
            weights = [max(0.001, item[0] - shortlist[-1][0] + 0.08) for item in shortlist]
            _, atom, current = rng.choices(shortlist, weights=weights, k=1)[0]
            cards[subject] = [atom]
            family_counts[atom.family] = family_counts.get(atom.family, 0) + 1

        if failed:
            continue

        while current.bit_count() > 1:
            before = current.bit_count()
            upgrades: list[tuple[float, str, AtomicClue, int]] = []
            for subject in subjects:
                if len(cards[subject]) == 2:
                    continue
                used = {atom.key for atom in cards[subject]}
                for atom in pools[subject]:
                    if atom.key in used:
                        continue
                    combined = current & bit_masks[atom.key]
                    after = combined.bit_count()
                    if after == 0 or after == before or not (combined & target_bit):
                        continue
                    score = _atom_selection_score(atom, before, after, family_counts, profile)
                    if atom.family not in {item.family for item in cards[subject]}:
                        score *= 1.2
                    score *= rng.uniform(0.85, 1.15)
                    upgrades.append((score, subject, atom, combined))
            if not upgrades:
                failed = True
                break
            upgrades.sort(key=lambda item: item[0], reverse=True)
            shortlist = upgrades[:12]
            weights = [max(0.001, item[0] - shortlist[-1][0] + 0.08) for item in shortlist]
            _, subject, atom, current = rng.choices(shortlist, weights=weights, k=1)[0]
            cards[subject].append(atom)

        if failed or current.bit_count() != 1:
            continue
        cards = _minimise_double_cards_bits(cards, bit_masks, all_bits, target_bit)
        if not _quality_ok(cards, profile):
            continue
        combined = _intersection_bits(cards, bit_masks, all_bits)
        if combined.bit_count() != 1 or not (combined & target_bit):
            continue
        all_cards, all_statements, card_counts, _ = _necessity_metrics_bits(cards, bit_masks, all_bits, target_bit)
        if not all_cards or not all_statements:
            continue

        atoms = [atom for values in cards.values() for atom in values]
        total_statements = len(atoms)
        double_count = sum(len(values) == 2 for values in cards.values())
        families = [atom.family for atom in atoms]
        repeated = len(families) - len(set(families))
        directness = sum(atom.directness for atom in atoms)
        imbalance_values = [math.log2(max(2, count)) for count in card_counts.values()]
        imbalance = max(imbalance_values) - min(imbalance_values)
        score = total_statements * 100 + double_count * 20 + repeated * 5 + directness * 10 + imbalance * 2
        if score < best_score:
            best_score = score
            best = {subject: list(values) for subject, values in cards.items()}
    return best


def search_card_set(
    pools: dict[str, list[AtomicClue]],
    bit_masks: dict[str, int],
    target_index: int,
    rng: random.Random,
    size: int,
    profile: str = "any",
) -> dict[str, list[AtomicClue]] | None:
    profile = _normalise_profile(profile)
    all_bits = (1 << size) - 1
    target_bit = 1 << target_index
    singles = _single_card_dfs(pools, bit_masks, all_bits, target_bit, rng, profile)
    if singles is not None:
        return singles
    if profile == "easy":
        return None
    return _randomized_search_with_doubles(pools, bit_masks, all_bits, target_bit, rng, profile)


def _card_mask(atoms: list[AtomicClue], masks: dict[str, np.ndarray], size: int) -> np.ndarray:
    result = np.ones(size, dtype=bool)
    for atom in atoms:
        result &= masks[atom.key]
    return result


def generate(
    board_path: Path, seed: int, output_dir: Path, selection_profile: str = "any",
    max_target_attempts: int = 24,
) -> dict[str, Any]:
    selection_profile = _normalise_profile(selection_profile)
    if max_target_attempts < 1:
        raise ValueError("max_target_attempts debe ser al menos 1")
    rng = random.Random(seed)
    board = load_board(board_path)
    room_flat, room_ids, room_names, room_index, group_room_indexes = build_board_arrays(board)
    geometry = board_geometry(board, room_flat)
    base_solutions = enumerate_base_solutions(board)

    victim_index = rng.randrange(len(CHARACTERS))
    victim = CHARACTERS[victim_index]
    valid_solutions = apply_victim_rule(base_solutions, victim_index, room_flat)
    if len(valid_solutions) == 0:
        raise RuntimeError("El tablero no admite ninguna solución con víctima válida.")

    chosen_cards: dict[str, list[AtomicClue]] | None = None
    chosen_target_index = -1
    chosen_masks: dict[str, np.ndarray] = {}
    chosen_bit_masks: dict[str, int] = {}
    murderer_index = -1
    chosen_victim_without_count = -1
    chosen_card_masks_over_base: dict[str, np.ndarray] = {}
    raw_candidate_count = 0
    chosen_selection_report: dict[str, Any] = {}
    attempt_reports: list[dict[str, Any]] = []
    atomic_mask_cache: dict[str, np.ndarray] = {}

    target_indexes = list(range(len(valid_solutions)))
    rng.shuffle(target_indexes)
    for target_attempt, target_index in enumerate(target_indexes[:max_target_attempts], start=1):
        target = valid_solutions[target_index]
        attempt_report: dict[str, Any] = {
            "attempt": target_attempt,
            "target_index": int(target_index),
            "status": "rejected",
            "reasons": [],
        }
        raw_pools, candidate_murderer = generate_atomic_candidates(
            target,
            board,
            room_flat,
            room_ids,
            room_names,
            room_index,
            group_room_indexes,
            geometry,
            victim_index,
        )
        masks: dict[str, np.ndarray] = {}
        pools: dict[str, list[AtomicClue]] = {}
        raw_candidate_count = sum(len(values) for values in raw_pools.values())
        attempt_report["raw_candidate_count"] = raw_candidate_count

        for subject, raw_candidates in raw_pools.items():
            unique_by_mask: dict[bytes, AtomicClue] = {}
            for candidate in raw_candidates:
                mask = atomic_mask_cache.get(candidate.key)
                if mask is None:
                    mask = atomic_mask(
                        candidate,
                        valid_solutions,
                        board,
                        room_flat,
                        room_index,
                        group_room_indexes,
                        geometry,
                        CHARACTERS,
                    )
                    atomic_mask_cache[candidate.key] = mask
                matches = int(np.count_nonzero(mask))
                if matches <= 0 or matches >= len(valid_solutions) or not bool(mask[target_index]):
                    continue
                packed = np.packbits(mask).tobytes()
                previous = unique_by_mask.get(packed)
                family_preference = 0 if candidate.family in RICH_FAMILIES else 1
                candidate_rank = (family_preference, candidate.directness, candidate.complexity)
                previous_rank = (
                    0 if previous and previous.family in RICH_FAMILIES else 1,
                    previous.directness if previous else math.inf,
                    previous.complexity if previous else math.inf,
                )
                if previous is None or candidate_rank < previous_rank:
                    unique_by_mask[packed] = candidate
                    masks[candidate.key] = mask

            candidates = list(unique_by_mask.values())
            candidates.sort(
                key=lambda atom: (
                    0 if atom.family in RICH_FAMILIES else 1,
                    atom.directness,
                    atom.complexity,
                    -math.log2(len(valid_solutions) / int(np.count_nonzero(masks[atom.key]))),
                )
            )
            pools[subject] = candidates[:58]

        attempt_report["deduplicated_candidates_per_subject"] = {
            subject: len(candidates) for subject, candidates in pools.items()
        }
        if any(not candidates for candidates in pools.values()):
            attempt_report["reasons"].append("subject_without_candidates")
            attempt_reports.append(attempt_report)
            continue

        bit_masks = {
            atom.key: _bool_mask_to_bits(masks[atom.key])
            for candidates in pools.values()
            for atom in candidates
        }
        cards, selection_report = global_select_cards(
            pools, bit_masks, target_index, len(valid_solutions), rng, selection_profile
        )
        attempt_report["selector"] = selection_report
        if cards is None:
            attempt_report["reasons"].append("no_global_card_set")
            attempt_reports.append(attempt_report)
            continue

        suspect_mask_over_base = np.ones(len(base_solutions), dtype=bool)
        card_masks_over_base: dict[str, np.ndarray] = {}
        for subject, atoms in cards.items():
            card_mask = np.ones(len(base_solutions), dtype=bool)
            for atom in atoms:
                card_mask &= atomic_mask(
                    atom, base_solutions, board, room_flat, room_index,
                    group_room_indexes, geometry, CHARACTERS,
                )
            card_masks_over_base[f"card-{subject}"] = card_mask
            suspect_mask_over_base &= card_mask
        victim_without_count = int(np.count_nonzero(suspect_mask_over_base))
        if victim_without_count <= 1:
            attempt_report["reasons"].append("victim_card_redundant")
            attempt_report["solutions_without_victim_card"] = victim_without_count
            attempt_reports.append(attempt_report)
            continue

        attempt_report["status"] = "accepted"
        attempt_report["solutions_without_victim_card"] = victim_without_count
        attempt_reports.append(attempt_report)
        chosen_cards = cards
        chosen_target_index = target_index
        chosen_masks = masks
        chosen_bit_masks = bit_masks
        chosen_selection_report = selection_report
        chosen_card_masks_over_base = card_masks_over_base
        murderer_index = candidate_murderer
        chosen_victim_without_count = victim_without_count
        break

    if chosen_cards is None:
        raise RuntimeError("No se encontró una combinación V2 válida de una tarjeta por personaje.")

    target = valid_solutions[chosen_target_index]
    target_rooms = room_flat[target]
    n = board["rows"]
    character_json = [
        {**character, "role": "victim" if index == victim_index else "suspect"}
        for index, character in enumerate(CHARACTERS)
    ]

    cards_json: list[dict[str, Any]] = []
    for character in character_json:
        subject = character["id"]
        card_id = f"card-{subject}"
        if character["role"] == "victim":
            statements = [{
                "id": f"{card_id}-statement-1",
                "type": "victim_rule",
                "family": "murder_rule",
                "args": {"character": subject},
                "text": f"{character['name']} estaba a solas con otra persona. Esa persona es el asesino.",
            }]
        else:
            statements = [
                atom.to_json(f"{card_id}-statement-{index + 1}")
                for index, atom in enumerate(chosen_cards[subject])
            ]
        cards_json.append({
            "id": card_id,
            "character": subject,
            "character_name": character["name"],
            "role": character["role"],
            "statements": statements,
        })

    base_rooms = room_flat[base_solutions]
    victim_room_values = base_rooms[:, [victim_index]]
    victim_mask_over_base = np.sum(base_rooms == victim_room_values, axis=1) == 2
    dependency_masks = {
        f"card-{victim['id']}": _bool_mask_to_bits(victim_mask_over_base),
        **{card_id: _bool_mask_to_bits(mask) for card_id, mask in chosen_card_masks_over_base.items()},
    }
    dependency_metadata = {
        card["id"]: {
            "role": card["role"],
            "character": card["character"],
            "families": [statement["family"] for statement in card["statements"]],
        }
        for card in cards_json
    }
    dependency_graph = analyze_card_dependencies(
        dependency_masks, (1 << len(base_solutions)) - 1, dependency_metadata,
        first_card_id=f"card-{victim['id']}",
    )

    puzzle = {
        "schema_version": 8,
        "id": f"case-{board['id']}-{seed}",
        "seed": seed,
        "selection_profile": selection_profile,
        "board": board,
        "characters": character_json,
        "victim": victim["id"],
        "rules": {
            "one_character_per_row": True,
            "one_character_per_column": True,
            "one_card_per_character": True,
            "statements_per_suspect_card": [1, 2],
            "murder_rule": "La víctima estaba a solas con otra persona; esa persona es el asesino.",
            "wall_definition": "Una pared es el borde exterior o el límite ortogonal entre dos habitaciones.",
            "corner_definition": "Una esquina toca una pared vertical y otra horizontal de la habitación.",
            "room_gender_count_includes_subject": True,
            "companion_gender_count_excludes_subject": True,
            "object_footprints": True,
            "blocked_furniture_cells_are_not_character_positions": True,
            "allowed_object_overlap": "Solo una silla puede compartir casilla con una alfombra.",
            "room_labels_never_overlap_objects": True,
            "formal_clue_catalog": True,
            "global_card_selection": True,
        },
        "cards": cards_json,
    }

    solution = {
        "puzzle_id": puzzle["id"],
        "victim": victim["id"],
        "victim_name": victim["name"],
        "positions": {
            character["id"]: {
                "row": int(target[index] // n),
                "column": int(target[index] % n),
                "room": room_ids[int(target_rooms[index])],
            }
            for index, character in enumerate(CHARACTERS)
        },
        "murderer": CHARACTERS[murderer_index]["id"],
        "murderer_name": CHARACTERS[murderer_index]["name"],
    }

    size = len(valid_solutions)
    current = np.ones(size, dtype=bool)
    progression = [{
        "card_id": f"card-{victim['id']}",
        "character": victim["id"],
        "role": "victim",
        "statements": 1,
        "solutions_before": int(len(base_solutions)),
        "solutions_after": int(len(valid_solutions)),
        "information_gain_bits": round(math.log2(len(base_solutions) / len(valid_solutions)), 3),
    }]
    remaining_subjects = list(chosen_cards)
    while remaining_subjects:
        subject = min(
            remaining_subjects,
            key=lambda item: int(np.count_nonzero(current & _card_mask(chosen_cards[item], chosen_masks, size))),
        )
        before = int(np.count_nonzero(current))
        current &= _card_mask(chosen_cards[subject], chosen_masks, size)
        after = int(np.count_nonzero(current))
        progression.append({
            "card_id": f"card-{subject}",
            "character": subject,
            "role": "suspect",
            "statements": len(chosen_cards[subject]),
            "solutions_before": before,
            "solutions_after": after,
            "information_gain_bits": round(math.log2(before / after), 3),
        })
        remaining_subjects.remove(subject)

    all_bits = (1 << size) - 1
    target_bit = 1 << chosen_target_index
    suspect_cards_necessary, suspect_statements_necessary, card_counts, statement_counts = _necessity_metrics_bits(
        chosen_cards, chosen_bit_masks, all_bits, target_bit
    )
    victim_without_count = chosen_victim_without_count
    victim_card_necessary = victim_without_count > 1

    card_necessity = [{
        "card_id": f"card-{victim['id']}",
        "character": victim["id"],
        "solutions_without_card": victim_without_count,
        "necessary": victim_card_necessary,
    }]
    for subject in chosen_cards:
        card_necessity.append({
            "card_id": f"card-{subject}",
            "character": subject,
            "solutions_without_card": card_counts[subject],
            "necessary": card_counts[subject] > 1,
        })

    statement_necessity: list[dict[str, Any]] = []
    for subject, atoms in chosen_cards.items():
        for index, atom in enumerate(atoms):
            statement_necessity.append({
                "statement_id": f"card-{subject}-statement-{index + 1}",
                "character": subject,
                "type": atom.type,
                "family": atom.family,
                "solutions_without_statement": statement_counts[atom.key],
                "necessary": statement_counts[atom.key] > 1,
            })

    selected_atoms = [atom for atoms in chosen_cards.values() for atom in atoms]
    family_distribution: dict[str, int] = {}
    type_distribution: dict[str, int] = {}
    for atom in selected_atoms:
        family_distribution[atom.family] = family_distribution.get(atom.family, 0) + 1
        type_distribution[atom.type] = type_distribution.get(atom.type, 0) + 1

    from .human_solver import analyze_puzzle

    human_analysis = analyze_puzzle(puzzle)
    expected_positions_for_human = {
        character_id: {"row": data["row"], "column": data["column"]}
        for character_id, data in solution["positions"].items()
    }
    human_solver_matches_solution = human_analysis["final_positions"] == expected_positions_for_human

    # V2-gamma: exact CP-SAT validation independent from the NumPy universe.
    from .solvers.ortools_solver import ORToolsSolver

    exact_result = ORToolsSolver().solve(puzzle, limit=2)
    expected_positions_for_exact = {
        character_id: (data["row"], data["column"])
        for character_id, data in solution["positions"].items()
    }
    exact_matches_solution = bool(
        exact_result.unique
        and exact_result.solutions[0] == expected_positions_for_exact
    )

    diagnostics = {
        "puzzle_id": puzzle["id"],
        "selection_profile": selection_profile,
        "base_assignment_count": int(len(base_solutions)),
        "valid_after_victim_card": int(len(valid_solutions)),
        "raw_candidate_count_for_selected_target": raw_candidate_count,
        "atomic_mask_cache_size": len(atomic_mask_cache),
        "room_count": len(board["rooms"]),
        "room_group_count": len(board.get("room_groups", [])),
        "interior_cells_not_adjacent_to_wall": len(geometry["no_wall_cells"]),
        "room_corner_cells": len(geometry["corner_cells"]),
        "card_count": len(cards_json),
        "total_statement_count": sum(len(card["statements"]) for card in cards_json),
        "double_card_count": sum(len(card["statements"]) == 2 for card in cards_json if card["role"] == "suspect"),
        "final_solution_count": int(np.count_nonzero(current)),
        "all_cards_necessary": bool(suspect_cards_necessary and victim_card_necessary),
        "all_suspect_statements_necessary": bool(suspect_statements_necessary),
        "family_distribution": family_distribution,
        "type_distribution": type_distribution,
        "card_progression": progression,
        "card_necessity": card_necessity,
        "statement_necessity": statement_necessity,
        "formal_clue_catalog_size": len(CLUE_SPECS),
        "formal_clue_catalog": catalog_json(),
        "global_selector": chosen_selection_report,
        "card_dependency_graph": dependency_graph,
        "generation_targets_attempted": len(attempt_reports),
        "generation_rejection_summary": dict(__import__("collections").Counter(
            reason for attempt in attempt_reports for reason in attempt.get("reasons", [])
        )),
        "human_difficulty": human_analysis["difficulty"],
        "human_solver_step_count": human_analysis["step_count"],
        "human_solver_matches_solution": human_solver_matches_solution,
        "exact_validation": {
            "unique": exact_result.unique,
            "matches_solution": exact_matches_solution,
            "stats": exact_result.stats.to_dict(),
        },
    }

    if not exact_matches_solution:
        raise RuntimeError("El solucionador CP-SAT no coincide con la solución generada.")

    if not human_solver_matches_solution:
        raise RuntimeError("El solucionador humano no coincide con la solución generada.")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "puzzle.json").write_text(json.dumps(puzzle, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "solution.json").write_text(json.dumps(solution, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "explanation.json").write_text(json.dumps(human_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    generation_report = {
        "puzzle_id": puzzle["id"],
        "board": board["id"],
        "seed": seed,
        "selection_profile": selection_profile,
        "max_target_attempts": max_target_attempts,
        "accepted_target_index": chosen_target_index,
        "targets": attempt_reports,
        "summary": {
            "targets_attempted": len(attempt_reports),
            "targets_rejected": sum(attempt["status"] == "rejected" for attempt in attempt_reports),
            "accepted": True,
            "rejection_reasons": diagnostics["generation_rejection_summary"],
            "selector": chosen_selection_report,
        },
    }
    (output_dir / "generation_report.json").write_text(
        json.dumps(generation_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "puzzle": puzzle, "solution": solution, "diagnostics": diagnostics,
        "explanation": human_analysis, "generation_report": generation_report,
    }
