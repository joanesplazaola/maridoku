from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from .base import SolverResult, SolverStats
from .common import BINARY_TYPES, SolverContext, build_context, exact_solution_matches, possible_cells, room_of


class BacktrackingSolver:
    """CSP solver with MRV, degree tie-breaking, forward checking and room bounds."""

    name = "backtracking"

    @classmethod
    def is_available(cls) -> bool:
        return True

    def solve(
        self,
        puzzle: dict[str, Any],
        *,
        limit: int = 2,
        exclude_card_id: str | None = None,
        exclude_statement_id: str | None = None,
    ) -> SolverResult:
        started = time.perf_counter()
        ctx = build_context(puzzle, exclude_card_id, exclude_statement_id)
        stats = SolverStats(solver=self.name)
        domains = self._initial_domains(ctx)
        if any(not values for values in domains.values()):
            stats.elapsed_ms = (time.perf_counter() - started) * 1000
            return SolverResult([], stats)

        statements_by_character: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for statement in ctx.statements:
            for character in {statement["args"].get("character"), statement["args"].get("reference")} - {None}:
                statements_by_character[character].append(statement)

        solutions: list[dict[str, tuple[int, int]]] = []
        assigned: dict[str, int] = {}

        def search(depth: int) -> None:
            if len(solutions) >= limit:
                return
            stats.max_depth = max(stats.max_depth, depth)
            if len(assigned) == len(ctx.character_ids):
                stats.constraint_checks += len(ctx.statements)
                if exact_solution_matches(ctx, assigned):
                    solutions.append(ctx.to_positions(assigned))
                else:
                    stats.pruned += 1
                return

            candidates_by_character: dict[str, list[int]] = {}
            for character in ctx.character_ids:
                if character in assigned:
                    continue
                candidates = [
                    cell for cell in sorted(possible_cells(ctx, character, domains, assigned))
                    if self._candidate_has_support(ctx, domains, assigned, character, cell, statements_by_character)
                ]
                if not candidates:
                    stats.pruned += 1
                    return
                candidates_by_character[character] = candidates

            character = min(
                candidates_by_character,
                key=lambda item: (
                    len(candidates_by_character[item]),
                    -ctx.graph.degree(item),
                    -ctx.graph.nodes[item].get("unary_weight", 0),
                    ctx.character_ids.index(item),
                ),
            )
            ordered_cells = sorted(
                candidates_by_character[character],
                key=lambda cell: self._lcv_cost(ctx, domains, assigned, character, cell),
            )

            before = len(solutions)
            for cell in ordered_cells:
                if len(solutions) >= limit:
                    break
                stats.nodes += 1
                assigned[character] = cell
                if self._partial_consistent(ctx, domains, assigned):
                    search(depth + 1)
                else:
                    stats.pruned += 1
                assigned.pop(character)
            if len(solutions) == before:
                stats.backtracks += 1

        search(0)
        stats.elapsed_ms = (time.perf_counter() - started) * 1000
        stats.metadata = {
            "initial_domain_sizes": {character: len(values) for character, values in domains.items()},
            "constraint_graph_edges": ctx.graph.number_of_edges(),
            "constraint_graph_density": round(float(__import__("networkx").density(ctx.graph)), 4),
            "limit": limit,
        }
        return SolverResult(solutions, stats)

    def _initial_domains(self, ctx: SolverContext) -> dict[str, set[int]]:
        domains = {character: set(ctx.all_cells) for character in ctx.character_ids}
        for statement in ctx.statements:
            typ = statement["type"]
            args = statement["args"]
            character = args["character"]
            if typ == "room":
                domains[character] &= ctx.room_cells[args["room"]]
            elif typ == "exact_row":
                domains[character] = {cell for cell in domains[character] if cell // ctx.n == args["row"]}
            elif typ == "exact_column":
                domains[character] = {cell for cell in domains[character] if cell % ctx.n == args["column"]}
            elif typ == "alone_in_room":
                domains[character] &= ctx.room_cells[args["room"]]
            elif typ == "not_adjacent_to_wall":
                domains[character] = {
                    cell for cell in domains[character] if not any(ctx.geometry[cell].values())
                }
            elif typ == "in_room_corner":
                domains[character] = {
                    cell for cell in domains[character]
                    if (ctx.geometry[cell]["north"] or ctx.geometry[cell]["south"])
                    and (ctx.geometry[cell]["west"] or ctx.geometry[cell]["east"])
                }
            elif typ == "in_room_group":
                allowed_rooms = ctx.groups[args["group"]]
                domains[character] = {
                    cell for cell in domains[character] if room_of(ctx, cell) in allowed_rooms
                }
            elif typ == "room_disjunction":
                allowed_rooms = set(args["rooms"])
                domains[character] = {
                    cell for cell in domains[character] if room_of(ctx, cell) in allowed_rooms
                }
            elif typ == "unique_on_object":
                domains[character] &= ctx.occupiable_cells_by_type.get(args["object_type"], set())
            elif typ in {"object_same_row_in_room", "object_same_column_in_room"}:
                object_cells = ctx.object_cells_by_type.get(args["object_type"], set())
                if typ == "object_same_row_in_room":
                    valid = {
                        cell for cell in domains[character]
                        if any(
                            cell // ctx.n == obj_cell // ctx.n and room_of(ctx, cell) == room_of(ctx, obj_cell)
                            for obj_cell in object_cells
                        )
                    }
                else:
                    valid = {
                        cell for cell in domains[character]
                        if any(
                            cell % ctx.n == obj_cell % ctx.n and room_of(ctx, cell) == room_of(ctx, obj_cell)
                            for obj_cell in object_cells
                        )
                    }
                domains[character] &= valid
            elif typ == "adjacent_object":
                object_cells = ctx.object_cells_by_type.get(args["object_type"], set())
                domains[character] = {
                    cell for cell in domains[character]
                    if any(
                        abs(cell // ctx.n - obj // ctx.n) + abs(cell % ctx.n - obj % ctx.n) == 1
                        for obj in object_cells
                    )
                }
        return domains

    def _candidate_has_support(
        self,
        ctx: SolverContext,
        domains: dict[str, set[int]],
        assigned: dict[str, int],
        character: str,
        cell: int,
        statements_by_character: dict[str, list[dict[str, Any]]],
    ) -> bool:
        trial = dict(assigned)
        trial[character] = cell
        for statement in statements_by_character[character]:
            if statement["type"] not in BINARY_TYPES:
                continue
            args = statement["args"]
            subject, reference = args["character"], args["reference"]
            other = reference if character == subject else subject
            if other in trial:
                if not self._binary_matches(ctx, statement, trial[subject], trial[reference]):
                    return False
            else:
                if not any(
                    self._binary_matches(
                        ctx,
                        statement,
                        cell if subject == character else other_cell,
                        other_cell if reference == other else cell,
                    )
                    for other_cell in possible_cells(ctx, other, domains, trial)
                ):
                    return False
        return True

    def _binary_matches(self, ctx: SolverContext, statement: dict[str, Any], subject_cell: int, reference_cell: int) -> bool:
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
        if typ == "same_room":
            return room_of(ctx, subject_cell) == room_of(ctx, reference_cell)
        if typ == "different_room":
            return room_of(ctx, subject_cell) != room_of(ctx, reference_cell)
        return True

    def _partial_consistent(
        self,
        ctx: SolverContext,
        domains: dict[str, set[int]],
        assigned: dict[str, int],
    ) -> bool:
        # All-different rows and columns are guaranteed by candidate generation, but keep an assertion-like guard.
        rows = [cell // ctx.n for cell in assigned.values()]
        columns = [cell % ctx.n for cell in assigned.values()]
        if len(rows) != len(set(rows)) or len(columns) != len(set(columns)):
            return False

        # Hall-style necessary condition for remaining rows and columns.
        remaining = [character for character in ctx.character_ids if character not in assigned]
        if remaining:
            available = {character: possible_cells(ctx, character, domains, assigned) for character in remaining}
            if any(not cells for cells in available.values()):
                return False
            if len({cell // ctx.n for cells in available.values() for cell in cells}) < len(remaining):
                return False
            if len({cell % ctx.n for cells in available.values() for cell in cells}) < len(remaining):
                return False

        for statement in ctx.statements:
            if not self._statement_possible(ctx, domains, assigned, statement):
                return False
        return True

    def _statement_possible(
        self,
        ctx: SolverContext,
        domains: dict[str, set[int]],
        assigned: dict[str, int],
        statement: dict[str, Any],
    ) -> bool:
        typ = statement["type"]
        args = statement["args"]
        subject = args["character"]
        if typ in BINARY_TYPES:
            reference = args["reference"]
            if subject in assigned and reference in assigned:
                return self._binary_matches(ctx, statement, assigned[subject], assigned[reference])
            return True
        if typ in {
            "room", "exact_row", "exact_column", "not_adjacent_to_wall", "in_room_corner",
            "in_room_group", "room_disjunction", "object_same_row_in_room",
            "object_same_column_in_room", "adjacent_object",
        }:
            return True  # Already encoded into the initial domain.

        if typ == "unique_on_object":
            allowed = ctx.occupiable_cells_by_type.get(args["object_type"], set())
            if subject in assigned and assigned[subject] not in allowed:
                return False
            return not any(
                character != subject and cell in allowed for character, cell in assigned.items()
            )

        if subject not in assigned:
            return True
        subject_room = room_of(ctx, assigned[subject])
        assigned_in_room = [character for character, cell in assigned.items() if room_of(ctx, cell) == subject_room]
        possible_in_room = [
            character for character in ctx.character_ids
            if character not in assigned
            and any(room_of(ctx, cell) == subject_room for cell in possible_cells(ctx, character, domains, assigned))
        ]

        if typ == "victim_rule":
            current = len(assigned_in_room)
            return current <= 2 and current + len(possible_in_room) >= 2
        if typ == "room_population":
            target = int(args["count"])
            current = len(assigned_in_room)
            return current <= target and current + len(possible_in_room) >= target
        if typ == "alone_in_room":
            return len(assigned_in_room) == 1
        if typ == "room_gender_count":
            gender = args["gender"]
            target = int(args["count"])
            current = sum(ctx.characters[character]["gender"] == gender for character in assigned_in_room)
            possible = sum(ctx.characters[character]["gender"] == gender for character in possible_in_room)
            return current <= target and current + possible >= target
        if typ == "companion_gender_count":
            gender = args["gender"]
            target = int(args["count"])
            current = sum(
                character != subject and ctx.characters[character]["gender"] == gender
                for character in assigned_in_room
            )
            possible = sum(ctx.characters[character]["gender"] == gender for character in possible_in_room)
            return current <= target and current + possible >= target
        if typ == "alone_with_gender":
            companions = [character for character in assigned_in_room if character != subject]
            if len(companions) > 1:
                return False
            if companions and ctx.characters[companions[0]]["gender"] != args["gender"]:
                return False
            if companions:
                return True
            return any(ctx.characters[character]["gender"] == args["gender"] for character in possible_in_room)
        return True

    def _lcv_cost(
        self,
        ctx: SolverContext,
        domains: dict[str, set[int]],
        assigned: dict[str, int],
        character: str,
        cell: int,
    ) -> tuple[int, int]:
        row, column = divmod(cell, ctx.n)
        eliminated = 0
        for other in ctx.character_ids:
            if other == character or other in assigned:
                continue
            eliminated += sum(
                candidate // ctx.n == row or candidate % ctx.n == column
                for candidate in domains[other]
            )
        return eliminated, cell
