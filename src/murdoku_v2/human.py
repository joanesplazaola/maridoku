from __future__ import annotations

from typing import Any

from .solvers.common import build_context
from .validator import matches_statement


UNARY_TYPES = {
    "room",
    "exact_row",
    "exact_column",
    "in_room_group",
    "unique_on_object",
    "object_same_row_in_room",
    "object_same_column_in_room",
    "adjacent_object",
    "not_adjacent_to_wall",
    "in_room_corner",
}
BINARY_TYPES = {
    "relative_row_order",
    "relative_column_order",
    "relative_row_distance",
    "relative_column_distance",
    "same_room",
    "different_room",
}
SUPPORTED_TYPES = {"victim_rule", *UNARY_TYPES, *BINARY_TYPES}


class _Contradiction(Exception):
    pass


def _perfect_matching_exists(
    values: dict[str, set[int]],
    fixed_character: str,
    fixed_value: int,
) -> bool:
    used = {fixed_value}
    pending = sorted(
        (character for character in values if character != fixed_character),
        key=lambda character: len(values[character]),
    )

    def visit(index: int) -> bool:
        if index == len(pending):
            return True
        character = pending[index]
        for value in sorted(values[character] - used):
            used.add(value)
            if visit(index + 1):
                return True
            used.remove(value)
        return False

    return visit(0)


def solve_human(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Propagate explicit human techniques without invoking an exact solver."""
    ctx = build_context(puzzle)
    unsupported = sorted({statement["type"] for statement in ctx.statements} - SUPPORTED_TYPES)
    if unsupported:
        return {
            "solved": False,
            "reason": "unsupported_clues",
            "unsupported_types": unsupported,
            "steps": [],
        }

    domains = {
        character: set(ctx.all_cells)
        for character in ctx.character_ids
    }
    steps: list[dict[str, Any]] = []

    def restrict(
        character: str,
        allowed: set[int],
        technique: str,
        statement_id: str | None = None,
    ) -> bool:
        before = domains[character]
        after = before & allowed
        if not after:
            raise _Contradiction
        if after == before:
            return False
        domains[character] = after
        steps.append({
            "technique": technique,
            "statement_id": statement_id,
            "character": character,
            "removed": len(before) - len(after),
            "remaining": len(after),
        })
        return True

    def unary_cells(statement: dict[str, Any]) -> set[int]:
        typ = statement["type"]
        args = statement["args"]
        if typ == "room":
            return set(ctx.room_cells[args["room"]])
        if typ == "exact_row":
            return {cell for cell in ctx.all_cells if cell // ctx.n == args["row"]}
        if typ == "exact_column":
            return {cell for cell in ctx.all_cells if cell % ctx.n == args["column"]}
        if typ == "in_room_group":
            return {
                cell for cell in ctx.all_cells
                if ctx.room_at[divmod(cell, ctx.n)] in ctx.groups[args["group"]]
            }
        if typ == "unique_on_object":
            return set(ctx.occupiable_cells_by_type.get(args["object_type"], set()))
        if typ == "not_adjacent_to_wall":
            return {cell for cell in ctx.all_cells if not any(ctx.geometry[cell].values())}
        if typ == "in_room_corner":
            return {
                cell for cell in ctx.all_cells
                if (ctx.geometry[cell]["north"] or ctx.geometry[cell]["south"])
                and (ctx.geometry[cell]["west"] or ctx.geometry[cell]["east"])
            }

        object_cells = ctx.object_cells_by_type.get(args["object_type"], set())
        result = set()
        for cell in ctx.all_cells:
            row, column = divmod(cell, ctx.n)
            room = ctx.room_at[(row, column)]
            if typ == "adjacent_object" and any(
                abs(row - object_cell // ctx.n) + abs(column - object_cell % ctx.n) == 1
                and ctx.room_at[divmod(object_cell, ctx.n)] == room
                for object_cell in object_cells
            ):
                result.add(cell)
            elif typ == "object_same_row_in_room" and any(
                object_cell // ctx.n == row
                and ctx.room_at[divmod(object_cell, ctx.n)] == room
                for object_cell in object_cells
            ):
                result.add(cell)
            elif typ == "object_same_column_in_room" and any(
                object_cell % ctx.n == column
                and ctx.room_at[divmod(object_cell, ctx.n)] == room
                for object_cell in object_cells
            ):
                result.add(cell)
        return result

    def binary_holds(statement: dict[str, Any], subject_cell: int, reference_cell: int) -> bool:
        typ = statement["type"]
        args = statement["args"]
        subject_row, subject_column = divmod(subject_cell, ctx.n)
        reference_row, reference_column = divmod(reference_cell, ctx.n)
        if typ == "relative_row_order":
            return subject_row < reference_row if args["relation"] == "north" else subject_row > reference_row
        if typ == "relative_column_order":
            return subject_column < reference_column if args["relation"] == "west" else subject_column > reference_column
        if typ == "relative_row_distance":
            return subject_row - reference_row == args["delta"]
        if typ == "relative_column_distance":
            return subject_column - reference_column == args["delta"]
        same_room = ctx.room_at[(subject_row, subject_column)] == ctx.room_at[(reference_row, reference_column)]
        return same_room if typ == "same_room" else not same_room

    try:
        for statement in ctx.statements:
            if statement["type"] not in UNARY_TYPES:
                continue
            subject = statement["args"]["character"]
            restrict(subject, unary_cells(statement), "clue_anchor", statement["id"])
            if statement["type"] == "unique_on_object":
                occupied = ctx.occupiable_cells_by_type.get(statement["args"]["object_type"], set())
                for other in ctx.character_ids:
                    if other != subject:
                        restrict(other, ctx.all_cells - occupied, "unique_object", statement["id"])

        for round_number in range(1, 101):
            changed = False
            for statement in ctx.statements:
                if statement["type"] not in BINARY_TYPES:
                    continue
                subject = statement["args"]["character"]
                reference = statement["args"]["reference"]
                subject_before = set(domains[subject])
                reference_before = set(domains[reference])
                changed |= restrict(
                    subject,
                    {
                        cell for cell in subject_before
                        if any(binary_holds(statement, cell, other) for other in reference_before)
                    },
                    "binary_relation",
                    statement["id"],
                )
                changed |= restrict(
                    reference,
                    {
                        cell for cell in reference_before
                        if any(binary_holds(statement, other, cell) for other in subject_before)
                    },
                    "binary_relation",
                    statement["id"],
                )

            victim_statements = [
                statement for statement in ctx.statements
                if statement["type"] == "victim_rule"
            ]
            if victim_statements:
                victim = victim_statements[0]["args"]["character"]

                def victim_feasible(victim_cell: int, fixed: tuple[str, int] | None = None) -> bool:
                    room = ctx.room_at[divmod(victim_cell, ctx.n)]
                    mandatory = 0
                    possible = 0
                    for other in ctx.character_ids:
                        if other == victim:
                            continue
                        other_domain = {fixed[1]} if fixed and fixed[0] == other else domains[other]
                        same_room = {
                            cell for cell in other_domain
                            if ctx.room_at[divmod(cell, ctx.n)] == room
                            and cell // ctx.n != victim_cell // ctx.n
                            and cell % ctx.n != victim_cell % ctx.n
                        }
                        mandatory += bool(same_room) and same_room == other_domain
                        possible += bool(same_room)
                    return mandatory <= 1 <= possible

                victim_before = set(domains[victim])
                changed |= restrict(
                    victim,
                    {cell for cell in victim_before if victim_feasible(cell)},
                    "victim_companion",
                    victim_statements[0]["id"],
                )
                for other in ctx.character_ids:
                    if other == victim:
                        continue
                    changed |= restrict(
                        other,
                        {
                            cell for cell in domains[other]
                            if any(victim_feasible(victim_cell, (other, cell)) for victim_cell in domains[victim])
                        },
                        "victim_companion",
                        victim_statements[0]["id"],
                    )

            for dimension, technique in ((0, "row_matching"), (1, "column_matching")):
                values = {
                    character: {
                        divmod(cell, ctx.n)[dimension]
                        for cell in domain
                    }
                    for character, domain in domains.items()
                }
                for character in ctx.character_ids:
                    supported = {
                        value for value in values[character]
                        if _perfect_matching_exists(values, character, value)
                    }
                    changed |= restrict(
                        character,
                        {
                            cell for cell in domains[character]
                            if divmod(cell, ctx.n)[dimension] in supported
                        },
                        technique,
                    )

            if not changed:
                break
        else:
            return {
                "solved": False,
                "reason": "iteration_limit",
                "unsupported_types": [],
                "steps": steps,
            }
    except _Contradiction:
        return {
            "solved": False,
            "reason": "contradiction",
            "unsupported_types": [],
            "steps": steps,
        }

    solved = all(len(domain) == 1 for domain in domains.values())
    positions = {
        character: divmod(next(iter(domain)), ctx.n)
        for character, domain in domains.items()
        if len(domain) == 1
    }
    if solved and not all(
        matches_statement(statement, positions, puzzle)
        for statement in ctx.statements
    ):
        solved = False
    return {
        "solved": solved,
        "reason": "solved" if solved else "stalled",
        "unsupported_types": [],
        "steps": steps,
        "step_count": len(steps),
        "techniques": sorted({step["technique"] for step in steps}),
        "positions": positions if solved else {},
        "domains": {
            character: [list(divmod(cell, ctx.n)) for cell in sorted(domain)]
            for character, domain in domains.items()
        },
        "difficulty": "unrated",
    }
