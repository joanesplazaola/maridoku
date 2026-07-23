from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


@dataclass(frozen=True)
class ClueSpec:
    """Formal contract for one atomic clue type.

    The engine may generate text in several languages, but the logical meaning lives here.
    Every clue type has exactly one evaluator and stable metadata used by tests, diagnostics,
    selection and future human-style propagation.
    """

    type: str
    family: str
    summary: str
    subject_centred: bool = True
    supports_partial_propagation: bool = True


@dataclass(frozen=True)
class AtomicClue:
    subject: str
    type: str
    family: str
    args: dict[str, Any]
    text: str
    complexity: float = 1.0
    directness: float = 0.0

    @property
    def key(self) -> str:
        ordered = ",".join(f"{key}={self.args[key]}" for key in sorted(self.args))
        return f"{self.subject}:{self.type}:{ordered}"

    def to_json(self, statement_id: str) -> dict[str, Any]:
        return {
            "id": statement_id,
            "type": self.type,
            "family": self.family,
            "args": self.args,
            "text": self.text,
        }


SPECS: tuple[ClueSpec, ...] = (
    ClueSpec("room", "room_exact", "El personaje está en una habitación concreta."),
    ClueSpec("exact_row", "coordinate", "El personaje está en una fila concreta."),
    ClueSpec("exact_column", "coordinate", "El personaje está en una columna concreta."),
    ClueSpec("room_population", "room_population", "Cantidad total de personas en su habitación."),
    ClueSpec("alone_in_room", "room_population", "Está solo en una habitación concreta."),
    ClueSpec("room_gender_count", "room_composition", "Cantidad de un género en su habitación, incluyéndole."),
    ClueSpec("companion_gender_count", "room_companion", "Cantidad de acompañantes de un género, excluyéndole."),
    ClueSpec("alone_with_gender", "room_companion", "Está únicamente con una persona de un género."),
    ClueSpec("not_adjacent_to_wall", "room_geometry", "No toca ninguna pared de su habitación."),
    ClueSpec("in_room_corner", "room_geometry", "Está en una esquina de su habitación."),
    ClueSpec("in_room_group", "room_group", "Está en una habitación de un grupo jerárquico."),
    ClueSpec("room_disjunction", "room_choice", "Está en una de dos habitaciones."),
    ClueSpec("unique_on_object", "object_occupancy", "Es la única persona situada sobre un tipo de objeto."),
    ClueSpec("object_same_row_in_room", "object_line", "Comparte fila y habitación con un tipo de objeto."),
    ClueSpec("object_same_column_in_room", "object_line", "Comparte columna y habitación con un tipo de objeto."),
    ClueSpec("adjacent_object", "object_adjacency", "Está ortogonalmente junto a un tipo de objeto."),
    ClueSpec("relative_row_order", "relative_order", "Está al norte o al sur de otra persona."),
    ClueSpec("relative_column_order", "relative_order", "Está al este o al oeste de otra persona."),
    ClueSpec("relative_row_distance", "relative_distance", "Distancia vertical exacta respecto a otra persona."),
    ClueSpec("relative_column_distance", "relative_distance", "Distancia horizontal exacta respecto a otra persona."),
    ClueSpec("same_room", "room_relation", "Está en la misma habitación que otra persona."),
    ClueSpec("different_room", "room_relation", "Está en una habitación distinta de otra persona."),
)

CLUE_SPECS: dict[str, ClueSpec] = {spec.type: spec for spec in SPECS}
if len(CLUE_SPECS) != len(SPECS):
    raise RuntimeError("El catálogo contiene tipos de pista duplicados.")


def _object_cells(obj: dict[str, Any]) -> list[tuple[int, int]]:
    if "cells" in obj:
        return [(int(row), int(column)) for row, column in obj["cells"]]
    return [(int(obj["row"]), int(obj["column"]))]


def _character_index(characters: list[dict[str, Any]]) -> dict[str, int]:
    return {character["id"]: index for index, character in enumerate(characters)}


def atomic_mask(
    clue: AtomicClue,
    solutions: np.ndarray,
    board: dict[str, Any],
    room_flat: np.ndarray,
    room_index: dict[str, int],
    group_room_indexes: dict[str, set[int]],
    geometry: dict[str, Any],
    characters: list[dict[str, Any]],
) -> np.ndarray:
    """Evaluate one formal clue over complete candidate assignments.

    This is the sole exact semantics used by generation. Validators deliberately keep a
    separate implementation so the generator cannot certify itself accidentally.
    """

    if clue.type not in CLUE_SPECS:
        raise ValueError(f"Tipo de pista no registrado: {clue.type}")
    n = int(board["rows"])
    character_index = _character_index(characters)
    rows = solutions // n
    columns = solutions % n
    solution_rooms = room_flat[solutions]
    args = clue.args
    char = character_index[args["character"]]

    if clue.type == "room":
        return solution_rooms[:, char] == room_index[args["room"]]
    if clue.type == "exact_row":
        return rows[:, char] == args["row"]
    if clue.type == "exact_column":
        return columns[:, char] == args["column"]
    if clue.type == "room_population":
        own_room = solution_rooms[:, [char]]
        return np.sum(solution_rooms == own_room, axis=1) == args["count"]
    if clue.type == "alone_in_room":
        own_room = room_index[args["room"]]
        return (solution_rooms[:, char] == own_room) & (np.sum(solution_rooms == own_room, axis=1) == 1)
    if clue.type == "room_gender_count":
        own_room = solution_rooms[:, [char]]
        indexes = [
            index for index, character in enumerate(characters)
            if character["gender"] == args["gender"]
        ]
        return np.sum(solution_rooms[:, indexes] == own_room, axis=1) == args["count"]
    if clue.type == "companion_gender_count":
        own_room = solution_rooms[:, [char]]
        indexes = [
            index for index, character in enumerate(characters)
            if character["gender"] == args["gender"] and index != char
        ]
        return np.sum(solution_rooms[:, indexes] == own_room, axis=1) == args["count"]
    if clue.type == "alone_with_gender":
        own_room = solution_rooms[:, [char]]
        room_count = np.sum(solution_rooms == own_room, axis=1)
        indexes = [
            index for index, character in enumerate(characters)
            if character["gender"] == args["gender"] and index != char
        ]
        companion_gender_count = np.sum(solution_rooms[:, indexes] == own_room, axis=1)
        return (room_count == 2) & (companion_gender_count == 1)
    if clue.type == "not_adjacent_to_wall":
        return np.isin(solutions[:, char], list(geometry["no_wall_cells"]))
    if clue.type == "in_room_corner":
        return np.isin(solutions[:, char], list(geometry["corner_cells"]))
    if clue.type == "in_room_group":
        return np.isin(solution_rooms[:, char], list(group_room_indexes[args["group"]]))
    if clue.type == "room_disjunction":
        room_indexes = [room_index[room_id] for room_id in args["rooms"]]
        return np.isin(solution_rooms[:, char], room_indexes)
    if clue.type == "unique_on_object":
        occupiable_cells = [
            row * n + column
            for obj in board.get("objects", [])
            if obj["type"] == args["object_type"] and obj.get("occupiable", False)
            for row, column in _object_cells(obj)
        ]
        on_type = np.isin(solutions, occupiable_cells)
        return on_type[:, char] & (np.sum(on_type, axis=1) == 1)
    if clue.type in {"object_same_row_in_room", "object_same_column_in_room"}:
        mask = np.zeros(len(solutions), dtype=bool)
        for obj in board.get("objects", []):
            if obj["type"] != args["object_type"]:
                continue
            cells = _object_cells(obj)
            object_room = int(room_flat[cells[0][0] * n + cells[0][1]])
            if clue.type == "object_same_row_in_room":
                for cell_row, _ in cells:
                    mask |= (rows[:, char] == cell_row) & (solution_rooms[:, char] == object_room)
            else:
                for _, cell_column in cells:
                    mask |= (columns[:, char] == cell_column) & (solution_rooms[:, char] == object_room)
        return mask
    if clue.type == "adjacent_object":
        mask = np.zeros(len(solutions), dtype=bool)
        for obj in board.get("objects", []):
            if obj["type"] != args["object_type"]:
                continue
            for cell_row, cell_column in _object_cells(obj):
                mask |= (
                    np.abs(rows[:, char].astype(np.int16) - int(cell_row))
                    + np.abs(columns[:, char].astype(np.int16) - int(cell_column))
                    == 1
                )
        return mask
    if clue.type == "relative_row_order":
        reference = character_index[args["reference"]]
        return rows[:, char] < rows[:, reference] if args["relation"] == "north" else rows[:, char] > rows[:, reference]
    if clue.type == "relative_column_order":
        reference = character_index[args["reference"]]
        return columns[:, char] < columns[:, reference] if args["relation"] == "west" else columns[:, char] > columns[:, reference]
    if clue.type == "relative_row_distance":
        reference = character_index[args["reference"]]
        return rows[:, char].astype(np.int16) - rows[:, reference].astype(np.int16) == args["delta"]
    if clue.type == "relative_column_distance":
        reference = character_index[args["reference"]]
        return columns[:, char].astype(np.int16) - columns[:, reference].astype(np.int16) == args["delta"]
    if clue.type in {"same_room", "different_room"}:
        reference = character_index[args["reference"]]
        same = solution_rooms[:, char] == solution_rooms[:, reference]
        return same if clue.type == "same_room" else ~same
    raise AssertionError(f"Catálogo sin implementación: {clue.type}")


def catalog_json() -> list[dict[str, Any]]:
    return [
        {
            "type": spec.type,
            "family": spec.family,
            "summary": spec.summary,
            "subject_centred": spec.subject_centred,
            "supports_partial_propagation": spec.supports_partial_propagation,
        }
        for spec in SPECS
    ]
