from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..models import validate_puzzle
from ..validator import matches_statement


BINARY_TYPES = {
    "relative_row_order",
    "relative_column_order",
    "relative_row_distance",
    "relative_column_distance",
    "same_diagonal",
    "same_room",
    "different_room",
}


@dataclass(slots=True)
class SolverContext:
    puzzle: dict[str, Any]
    n: int
    character_ids: list[str]
    characters: dict[str, dict[str, Any]]
    statements: list[dict[str, Any]]
    room_at: dict[tuple[int, int], str]
    room_cells: dict[str, set[int]]
    groups: dict[str, set[str]]
    zones: dict[str, set[int]]
    sequences: dict[str, list[int]]
    blocked_cells: set[int]
    all_cells: set[int]
    object_cells_by_type: dict[str, set[int]]
    occupiable_cells_by_type: dict[str, set[int]]
    geometry: dict[int, dict[str, bool]]

    def to_positions(self, assigned: dict[str, int]) -> dict[str, tuple[int, int]]:
        return {character: divmod(cell, self.n) for character, cell in assigned.items()}


def active_statements(
    puzzle: dict[str, Any],
    exclude_card_id: str | None = None,
    exclude_statement_id: str | None = None,
    extra_statements: Iterable[dict[str, Any]] = (),
    base_statements: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if base_statements is None:
        statements = [
            statement
            for card in puzzle["cards"]
            if card["id"] != exclude_card_id
            for statement in card["statements"]
            if statement["id"] != exclude_statement_id
        ]
        statements.extend(
            statement
            for statement in puzzle.get("general_clues", [])
            if statement["id"] != exclude_statement_id
        )
    else:
        statements = list(base_statements)
    statements.extend(extra_statements)
    return statements


def build_context(
    puzzle: dict[str, Any],
    exclude_card_id: str | None = None,
    exclude_statement_id: str | None = None,
) -> SolverContext:
    validate_puzzle(puzzle)
    board = puzzle["board"]
    rows = int(board["rows"])
    n = int(board["columns"])
    room_at_tuple = {
        tuple(cell): room["id"]
        for room in board["rooms"]
        for cell in room["cells"]
    }
    room_cells: dict[str, set[int]] = {
        room["id"]: {row * n + column for row, column in room["cells"]}
        for room in board["rooms"]
    }
    groups = {group["id"]: set(group["rooms"]) for group in board.get("room_groups", [])}
    zones = {
        zone["id"]: {row * n + column for row, column in zone["cells"]}
        for zone in board.get("zones", [])
    }
    sequences = {
        sequence["id"]: [row * n + column for row, column in sequence["cells"]]
        for sequence in board.get("sequences", [])
    }
    blocked = {
        row * n + column
        for obj in board.get("objects", [])
        if obj.get("blocks_character", False)
        for row, column in obj.get("cells", [[obj.get("row"), obj.get("column")]])
    }
    object_cells_by_type: dict[str, set[int]] = {}
    occupiable_cells_by_type: dict[str, set[int]] = {}
    for obj in board.get("objects", []):
        cells = {
            int(row) * n + int(column)
            for row, column in obj.get("cells", [[obj.get("row"), obj.get("column")]])
        }
        object_cells_by_type.setdefault(obj["type"], set()).update(cells)
        if obj.get("occupiable", False):
            occupiable_cells_by_type.setdefault(obj["type"], set()).update(cells)

    geometry: dict[int, dict[str, bool]] = {}
    for row in range(rows):
        for column in range(n):
            own_room = room_at_tuple[(row, column)]
            geometry[row * n + column] = {
                "north": row == 0 or room_at_tuple[(row - 1, column)] != own_room,
                "south": row == rows - 1 or room_at_tuple[(row + 1, column)] != own_room,
                "west": column == 0 or room_at_tuple[(row, column - 1)] != own_room,
                "east": column == n - 1 or room_at_tuple[(row, column + 1)] != own_room,
            }

    statements = active_statements(puzzle, exclude_card_id, exclude_statement_id)
    character_ids = [character["id"] for character in puzzle["characters"]]

    return SolverContext(
        puzzle=puzzle,
        n=n,
        character_ids=character_ids,
        characters={character["id"]: character for character in puzzle["characters"]},
        statements=statements,
        room_at=room_at_tuple,
        room_cells=room_cells,
        groups=groups,
        zones=zones,
        sequences=sequences,
        blocked_cells=blocked,
        all_cells=set(range(rows * n)) - blocked,
        object_cells_by_type=object_cells_by_type,
        occupiable_cells_by_type=occupiable_cells_by_type,
        geometry=geometry,
    )


def exact_solution_matches(ctx: SolverContext, assigned: dict[str, int]) -> bool:
    if len(assigned) != len(ctx.character_ids):
        return False
    positions = ctx.to_positions(assigned)
    return all(matches_statement(statement, positions, ctx.puzzle) for statement in ctx.statements)


def room_of(ctx: SolverContext, cell: int) -> str:
    return ctx.room_at[divmod(cell, ctx.n)]


def possible_cells(
    ctx: SolverContext,
    character: str,
    domains: dict[str, set[int]],
    assigned: dict[str, int],
) -> set[int]:
    if character in assigned:
        return {assigned[character]}
    used_rows = {cell // ctx.n for cell in assigned.values()}
    used_columns = {cell % ctx.n for cell in assigned.values()}
    return {
        cell for cell in domains[character]
        if cell // ctx.n not in used_rows and cell % ctx.n not in used_columns
    }


def statement_characters(statement: dict[str, Any]) -> set[str]:
    args = statement["args"]
    result = {args["character"]}
    if "reference" in args:
        result.add(args["reference"])
    return result
