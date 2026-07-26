from __future__ import annotations

from typing import Any




def _object_cells(obj: dict[str, Any]) -> list[tuple[int, int]]:
    if "cells" in obj:
        return [(int(row), int(column)) for row, column in obj["cells"]]
    return [(int(obj["row"]), int(obj["column"]))]


def _room_lookup(board: dict[str, Any]) -> dict[tuple[int, int], str]:
    return {
        tuple(cell): room["id"]
        for room in board["rooms"]
        for cell in room["cells"]
    }


def _room_groups(board: dict[str, Any]) -> dict[str, set[str]]:
    return {group["id"]: set(group["rooms"]) for group in board.get("room_groups", [])}


def _walls(board: dict[str, Any], row: int, column: int) -> dict[str, bool]:
    room_at = _room_lookup(board)
    room = room_at[(row, column)]
    rows, columns = board["rows"], board["columns"]
    return {
        "north": row == 0 or room_at[(row - 1, column)] != room,
        "south": row == rows - 1 or room_at[(row + 1, column)] != room,
        "west": column == 0 or room_at[(row, column - 1)] != room,
        "east": column == columns - 1 or room_at[(row, column + 1)] != room,
    }


def matches_statement(
    statement: dict[str, Any],
    positions: dict[str, tuple[int, int]],
    puzzle: dict[str, Any],
) -> bool:
    statement_type = statement["type"]
    args = statement["args"]
    board = puzzle["board"]
    room_at = _room_lookup(board)
    groups = _room_groups(board)
    characters = {character["id"]: character for character in puzzle["characters"]}
    character_id = args["character"]
    row, column = positions[character_id]
    own_room = room_at[(row, column)]

    if statement_type == "victim_rule":
        return sum(room_at[position] == own_room for position in positions.values()) == 2
    if statement_type == "room":
        return own_room == args["room"]
    if statement_type == "exact_row":
        return row == args["row"]
    if statement_type == "exact_column":
        return column == args["column"]
    if statement_type == "room_population":
        return sum(room_at[position] == own_room for position in positions.values()) == args["count"]
    if statement_type == "alone_in_room":
        return own_room == args["room"] and sum(room_at[position] == own_room for position in positions.values()) == 1
    if statement_type == "room_gender_count":
        return sum(
            room_at[positions[other_id]] == own_room and data["gender"] == args["gender"]
            for other_id, data in characters.items()
        ) == args["count"]
    if statement_type == "companion_gender_count":
        return sum(
            other_id != character_id
            and room_at[positions[other_id]] == own_room
            and data["gender"] == args["gender"]
            for other_id, data in characters.items()
        ) == args["count"]
    if statement_type == "alone_with_gender":
        companions = [
            other_id for other_id, position in positions.items()
            if other_id != character_id and room_at[position] == own_room
        ]
        return len(companions) == 1 and characters[companions[0]]["gender"] == args["gender"]
    if statement_type == "not_adjacent_to_wall":
        return not any(_walls(board, row, column).values())
    if statement_type == "in_room_corner":
        walls = _walls(board, row, column)
        return (walls["north"] or walls["south"]) and (walls["west"] or walls["east"])
    if statement_type == "in_room_group":
        return own_room in groups[args["group"]]
    if statement_type == "room_disjunction":
        return own_room in args["rooms"]
    if statement_type == "unique_on_object":
        object_cells = {
            cell
            for obj in board.get("objects", [])
            if obj["type"] == args["object_type"] and obj.get("occupiable", False)
            for cell in _object_cells(obj)
        }
        return positions[character_id] in object_cells and sum(
            position in object_cells for position in positions.values()
        ) == 1
    if statement_type in {"object_same_row_in_room", "object_same_column_in_room"}:
        objects = [obj for obj in board.get("objects", []) if obj["type"] == args["object_type"]]
        if statement_type == "object_same_row_in_room":
            return any(
                cell_row == row and room_at[(cell_row, cell_column)] == own_room
                for obj in objects for cell_row, cell_column in _object_cells(obj)
            )
        return any(
            cell_column == column and room_at[(cell_row, cell_column)] == own_room
            for obj in objects for cell_row, cell_column in _object_cells(obj)
        )
    if statement_type in {"adjacent_object", "unique_adjacent_object"}:
        adjacent = {
            position
            for position in positions.values()
            if any(
                obj["type"] == args["object_type"]
                and abs(position[0] - cell_row) + abs(position[1] - cell_column) == 1
                and room_at[(cell_row, cell_column)] == room_at[position]
                for obj in board.get("objects", [])
                for cell_row, cell_column in _object_cells(obj)
            )
        }
        own_adjacent = (row, column) in adjacent
        if statement_type == "unique_adjacent_object":
            return own_adjacent and len(adjacent) == 1
        return own_adjacent
    if statement_type == "relative_row_order":
        reference_row, _ = positions[args["reference"]]
        return row < reference_row if args["relation"] == "north" else row > reference_row
    if statement_type == "relative_column_order":
        _, reference_column = positions[args["reference"]]
        return column < reference_column if args["relation"] == "west" else column > reference_column
    if statement_type == "relative_row_distance":
        reference_row, _ = positions[args["reference"]]
        return row - reference_row == args["delta"]
    if statement_type == "relative_column_distance":
        _, reference_column = positions[args["reference"]]
        return column - reference_column == args["delta"]
    if statement_type == "same_diagonal":
        reference_row, reference_column = positions[args["reference"]]
        return abs(row - reference_row) == abs(column - reference_column)
    if statement_type in {"same_room", "different_room"}:
        same = own_room == room_at[positions[args["reference"]]]
        return same if statement_type == "same_room" else not same
    raise ValueError(f"Tipo desconocido: {statement_type}")
