from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from typing import Any, Iterable

from .base import SolverResult, SolverStats
from .common import active_statements
from ..models import validate_puzzle


@dataclass(slots=True)
class _CpSatContext:
    model: Any
    cp_model: Any
    character_ids: list[str]
    cell: dict[str, Any]
    row: dict[str, Any]
    column: dict[str, Any]
    room: dict[str, Any]
    room_ids: list[str]
    room_index: dict[str, int]
    room_at_cell: list[int]
    allowed_cells: list[int]
    n: int
    puzzle: dict[str, Any]


class ORToolsSolver:
    """Exact Google OR-Tools CP-SAT backend for the public puzzle contract.

    The model uses one cell, row, column and room variable per character.
    It deliberately compiles the public clue semantics directly.
    """

    name = "ortools-cp-sat"

    def __init__(self, *, num_search_workers: int = 1, max_time_seconds: float | None = None):
        self.num_search_workers = num_search_workers
        self.max_time_seconds = max_time_seconds

    @classmethod
    def is_available(cls) -> bool:
        try:
            return importlib.util.find_spec("ortools.sat.python.cp_model") is not None
        except ModuleNotFoundError:
            return False

    def solve(
        self,
        puzzle: dict[str, Any],
        *,
        limit: int = 2,
        exclude_card_id: str | None = None,
        exclude_statement_id: str | None = None,
        extra_statements: tuple[dict[str, Any], ...] = (),
        base_statements: tuple[dict[str, Any], ...] | None = None,
    ) -> SolverResult:
        started = time.perf_counter()
        stats = SolverStats(solver=self.name)
        if limit < 1:
            raise ValueError("limit debe ser al menos 1")
        if not self.is_available():
            stats.elapsed_ms = (time.perf_counter() - started) * 1000
            return SolverResult(
                [],
                stats,
                available=False,
                message="OR-Tools no está instalado. Instala `ortools>=9.15`.",
            )

        from ortools.sat.python import cp_model

        build_started = time.perf_counter()
        ctx = self._build_model(
            puzzle,
            cp_model,
            exclude_card_id=exclude_card_id,
            exclude_statement_id=exclude_statement_id,
            extra_statements=extra_statements,
            base_statements=base_statements,
        )
        build_ms = (time.perf_counter() - build_started) * 1000

        solutions: list[dict[str, tuple[int, int]]] = []
        solve_times_ms: list[float] = []
        statuses: list[str] = []
        total_branches = 0
        total_conflicts = 0
        solver_wall_seconds = 0.0

        for solution_index in range(limit):
            solver = cp_model.CpSolver()
            solver.parameters.num_search_workers = self.num_search_workers
            solver.parameters.random_seed = int(puzzle.get("seed", 0)) & 0x7FFFFFFF
            # These settings make benchmark runs repeatable. CP-SAT may still
            # evolve between library versions, so the version is recorded.
            solver.parameters.randomize_search = False
            if self.max_time_seconds is not None:
                solver.parameters.max_time_in_seconds = self.max_time_seconds

            call_started = time.perf_counter()
            status = solver.solve(ctx.model)
            call_ms = (time.perf_counter() - call_started) * 1000
            solve_times_ms.append(call_ms)
            statuses.append(self._status_name(solver, status))
            total_branches += self._numeric_stat(solver, "num_branches")
            total_conflicts += self._numeric_stat(solver, "num_conflicts")
            solver_wall_seconds += self._float_stat(solver, "wall_time")

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break

            cell_values = {
                character: int(solver.value(ctx.cell[character]))
                for character in ctx.character_ids
            }
            solutions.append({
                character: divmod(cell_value, ctx.n)
                for character, cell_value in cell_values.items()
            })
            self._exclude_exact_solution(ctx, cell_values, solution_index)

        stats.nodes = total_branches
        stats.backtracks = total_conflicts
        stats.constraint_checks = len(active_statements(
            puzzle, exclude_card_id, exclude_statement_id, extra_statements, base_statements
        ))
        stats.elapsed_ms = (time.perf_counter() - started) * 1000
        stats.metadata = {
            "backend": "Google OR-Tools CP-SAT",
            "ortools_version": self._ortools_version(),
            "model_build_ms": build_ms,
            "solve_calls_ms": solve_times_ms,
            "first_solution_ms": solve_times_ms[0] if solve_times_ms else None,
            "uniqueness_check_ms": solve_times_ms[1] if len(solve_times_ms) > 1 else None,
            "statuses": statuses,
            "num_search_workers": self.num_search_workers,
            "solver_wall_seconds": solver_wall_seconds,
            "variable_count": len(ctx.model.proto.variables),
            "constraint_count": len(ctx.model.proto.constraints),
        }
        return SolverResult(solutions, stats)


    @staticmethod
    def _status_name(solver: Any, status: Any) -> str:
        """Compatibility across the CP-SAT Python wrapper variants.

        OR-Tools 9.15 changed the status object and has a documented wrapper
        regression around ``status_name()``. Prefer the enum name and only
        fall back to the solver helper.
        """
        name = getattr(status, "name", None)
        if name:
            return str(name)
        helper = getattr(solver, "status_name", None)
        if helper is None:
            return str(status)
        if callable(helper):
            for args in ((status,), ()):  # Old and new wrapper shapes.
                try:
                    return str(helper(*args))
                except TypeError:
                    continue
        return str(helper)

    @staticmethod
    def _ortools_version() -> str | None:
        try:
            import ortools
            return getattr(ortools, "__version__", None)
        except Exception:
            return None

    @staticmethod
    def _numeric_stat(solver: Any, name: str) -> int:
        value = getattr(solver, name, 0)
        try:
            return int(value() if callable(value) else value)
        except Exception:
            return 0

    @staticmethod
    def _float_stat(solver: Any, name: str) -> float:
        value = getattr(solver, name, 0.0)
        try:
            return float(value() if callable(value) else value)
        except Exception:
            return 0.0

    def _build_model(
        self,
        puzzle: dict[str, Any],
        cp_model: Any,
        *,
        exclude_card_id: str | None,
        exclude_statement_id: str | None,
        extra_statements: tuple[dict[str, Any], ...],
        base_statements: tuple[dict[str, Any], ...] | None,
    ) -> _CpSatContext:
        validate_puzzle(puzzle)
        board = puzzle["board"]
        n = int(board["rows"])
        character_ids = [character["id"] for character in puzzle["characters"]]
        room_ids = [room["id"] for room in board["rooms"]]
        room_index = {room_id: index for index, room_id in enumerate(room_ids)}
        room_at_tuple = {
            tuple(cell): room["id"]
            for room in board["rooms"]
            for cell in room["cells"]
        }
        room_at_cell = [
            room_index[room_at_tuple[divmod(cell_value, n)]]
            for cell_value in range(n * n)
        ]
        blocked = {
            int(row) * n + int(column)
            for obj in board.get("objects", [])
            if obj.get("blocks_character", False)
            for row, column in self._object_cells(obj)
        }
        allowed_cells = [cell_value for cell_value in range(n * n) if cell_value not in blocked]
        if len(allowed_cells) < n:
            raise ValueError("No hay suficientes casillas transitables para todos los personajes.")

        model = cp_model.CpModel()
        cell_domain = cp_model.Domain.from_values(allowed_cells)
        cell: dict[str, Any] = {}
        row: dict[str, Any] = {}
        column: dict[str, Any] = {}
        room: dict[str, Any] = {}

        for character in character_ids:
            cell[character] = model.new_int_var_from_domain(cell_domain, f"cell_{character}")
            row[character] = model.new_int_var(0, n - 1, f"row_{character}")
            column[character] = model.new_int_var(0, n - 1, f"column_{character}")
            room[character] = model.new_int_var(0, len(room_ids) - 1, f"room_{character}")
            model.add_division_equality(row[character], cell[character], n)
            model.add_modulo_equality(column[character], cell[character], n)
            model.add_element(cell[character], room_at_cell, room[character])

        model.add_all_different(list(row.values()))
        model.add_all_different(list(column.values()))

        ctx = _CpSatContext(
            model=model,
            cp_model=cp_model,
            character_ids=character_ids,
            cell=cell,
            row=row,
            column=column,
            room=room,
            room_ids=room_ids,
            room_index=room_index,
            room_at_cell=room_at_cell,
            allowed_cells=allowed_cells,
            n=n,
            puzzle=puzzle,
        )
        for statement in active_statements(puzzle, exclude_card_id, exclude_statement_id, extra_statements, base_statements):
            self._add_statement(ctx, statement)
        return ctx

    def _add_statement(self, ctx: _CpSatContext, statement: dict[str, Any]) -> None:
        model = ctx.model
        typ = statement["type"]
        args = statement["args"]
        subject = args["character"]

        if typ == "victim_rule":
            same = [self._same_room_bool(ctx, subject, other, statement["id"]) for other in ctx.character_ids if other != subject]
            model.add(sum(same) == 1)
            return
        if typ == "room":
            model.add(ctx.room[subject] == ctx.room_index[args["room"]])
            return
        if typ == "exact_row":
            model.add(ctx.row[subject] == int(args["row"]))
            return
        if typ == "exact_column":
            model.add(ctx.column[subject] == int(args["column"]))
            return
        if typ == "room_population":
            same = [self._same_room_bool(ctx, subject, other, statement["id"]) for other in ctx.character_ids if other != subject]
            model.add(sum(same) + 1 == int(args["count"]))
            return
        if typ == "alone_in_room":
            model.add(ctx.room[subject] == ctx.room_index[args["room"]])
            same = [self._same_room_bool(ctx, subject, other, statement["id"]) for other in ctx.character_ids if other != subject]
            model.add(sum(same) == 0)
            return
        if typ == "room_gender_count":
            gender = args["gender"]
            character_data = {character["id"]: character for character in ctx.puzzle["characters"]}
            terms: list[Any] = []
            for other in ctx.character_ids:
                if character_data[other]["gender"] != gender:
                    continue
                terms.append(1 if other == subject else self._same_room_bool(ctx, subject, other, statement["id"]))
            model.add(sum(terms) == int(args["count"]))
            return
        if typ == "companion_gender_count":
            gender = args["gender"]
            character_data = {character["id"]: character for character in ctx.puzzle["characters"]}
            terms = [
                self._same_room_bool(ctx, subject, other, statement["id"])
                for other in ctx.character_ids
                if other != subject and character_data[other]["gender"] == gender
            ]
            model.add(sum(terms) == int(args["count"]))
            return
        if typ == "alone_with_gender":
            gender = args["gender"]
            character_data = {character["id"]: character for character in ctx.puzzle["characters"]}
            all_companions = [
                self._same_room_bool(ctx, subject, other, statement["id"])
                for other in ctx.character_ids if other != subject
            ]
            gender_companions = [
                self._same_room_bool(ctx, subject, other, statement["id"] + "_gender")
                for other in ctx.character_ids
                if other != subject and character_data[other]["gender"] == gender
            ]
            model.add(sum(all_companions) == 1)
            model.add(sum(gender_companions) == 1)
            return
        if typ == "not_adjacent_to_wall":
            self._restrict_subject_cells(ctx, subject, self._cells_not_adjacent_to_wall(ctx.puzzle), statement["id"])
            return
        if typ == "in_room_corner":
            self._restrict_subject_cells(ctx, subject, self._room_corner_cells(ctx.puzzle), statement["id"])
            return
        if typ == "in_room_group":
            groups = {group["id"]: set(group["rooms"]) for group in ctx.puzzle["board"].get("room_groups", [])}
            allowed_rooms = [ctx.room_index[room_id] for room_id in groups[args["group"]]]
            self._restrict_int_values(ctx, ctx.room[subject], allowed_rooms, statement["id"])
            return
        if typ == "room_disjunction":
            allowed_rooms = [ctx.room_index[room_id] for room_id in args["rooms"]]
            self._restrict_int_values(ctx, ctx.room[subject], allowed_rooms, statement["id"])
            return
        if typ == "unique_on_object":
            object_cells = self._object_cells_of_type(ctx.puzzle, args["object_type"], occupiable_only=True)
            self._restrict_subject_cells(ctx, subject, object_cells, statement["id"] + "_subject")
            outside = set(ctx.allowed_cells) - object_cells
            for other in ctx.character_ids:
                if other != subject:
                    self._restrict_subject_cells(ctx, other, outside, statement["id"] + "_other")
            return
        if typ == "object_same_row_in_room":
            valid = self._object_line_cells(ctx.puzzle, args["object_type"], same_row=True)
            self._restrict_subject_cells(ctx, subject, valid, statement["id"])
            return
        if typ == "object_same_column_in_room":
            valid = self._object_line_cells(ctx.puzzle, args["object_type"], same_row=False)
            self._restrict_subject_cells(ctx, subject, valid, statement["id"])
            return
        if typ == "adjacent_object":
            valid = self._adjacent_object_cells(ctx.puzzle, args["object_type"])
            self._restrict_subject_cells(ctx, subject, valid, statement["id"])
            return
        if typ == "relative_row_order":
            reference = args["reference"]
            if args["relation"] == "north":
                model.add(ctx.row[subject] < ctx.row[reference])
            else:
                model.add(ctx.row[subject] > ctx.row[reference])
            return
        if typ == "relative_column_order":
            reference = args["reference"]
            if args["relation"] == "west":
                model.add(ctx.column[subject] < ctx.column[reference])
            else:
                model.add(ctx.column[subject] > ctx.column[reference])
            return
        if typ == "relative_row_distance":
            model.add(ctx.row[subject] - ctx.row[args["reference"]] == int(args["delta"]))
            return
        if typ == "relative_column_distance":
            model.add(ctx.column[subject] - ctx.column[args["reference"]] == int(args["delta"]))
            return
        if typ == "same_room":
            model.add(ctx.room[subject] == ctx.room[args["reference"]])
            return
        if typ == "different_room":
            model.add(ctx.room[subject] != ctx.room[args["reference"]])
            return
        raise ValueError(f"Tipo de pista CP-SAT no implementado: {typ}")

    def _same_room_bool(self, ctx: _CpSatContext, first: str, second: str, label: str) -> Any:
        literal = ctx.model.new_bool_var(f"same_room_{label}_{first}_{second}_{len(ctx.model.proto.variables)}")
        ctx.model.add(ctx.room[first] == ctx.room[second]).only_enforce_if(literal)
        ctx.model.add(ctx.room[first] != ctx.room[second]).only_enforce_if(literal.Not())
        return literal

    def _restrict_subject_cells(self, ctx: _CpSatContext, subject: str, values: Iterable[int], label: str) -> None:
        allowed = sorted(set(int(value) for value in values) & set(ctx.allowed_cells))
        if not allowed:
            ctx.model.add_bool_or([])  # Force an infeasible model.
            return
        self._restrict_int_values(ctx, ctx.cell[subject], allowed, label)

    @staticmethod
    def _restrict_int_values(ctx: _CpSatContext, variable: Any, values: Iterable[int], label: str) -> None:
        allowed = sorted(set(int(value) for value in values))
        if not allowed:
            ctx.model.add_bool_or([])
            return
        ctx.model.add_allowed_assignments([variable], [[value] for value in allowed])

    @staticmethod
    def _exclude_exact_solution(ctx: _CpSatContext, values: dict[str, int], index: int) -> None:
        equals: list[Any] = []
        for character, value in values.items():
            literal = ctx.model.new_bool_var(f"nogood_{index}_{character}")
            ctx.model.add(ctx.cell[character] == value).only_enforce_if(literal)
            ctx.model.add(ctx.cell[character] != value).only_enforce_if(literal.Not())
            equals.append(literal)
        ctx.model.add(sum(equals) <= len(equals) - 1)

    @staticmethod
    def _object_cells(obj: dict[str, Any]) -> list[tuple[int, int]]:
        if obj.get("cells"):
            return [(int(row), int(column)) for row, column in obj["cells"]]
        return [(int(obj["row"]), int(obj["column"]))]

    def _object_cells_of_type(self, puzzle: dict[str, Any], object_type: str, *, occupiable_only: bool = False) -> set[int]:
        n = int(puzzle["board"]["rows"])
        return {
            row * n + column
            for obj in puzzle["board"].get("objects", [])
            if obj["type"] == object_type and (not occupiable_only or obj.get("occupiable", False))
            for row, column in self._object_cells(obj)
        }

    @staticmethod
    def _room_at(puzzle: dict[str, Any]) -> dict[tuple[int, int], str]:
        return {
            tuple(cell): room["id"]
            for room in puzzle["board"]["rooms"]
            for cell in room["cells"]
        }

    def _walls(self, puzzle: dict[str, Any], row: int, column: int) -> dict[str, bool]:
        room_at = self._room_at(puzzle)
        own_room = room_at[(row, column)]
        rows = int(puzzle["board"]["rows"])
        columns = int(puzzle["board"]["columns"])
        return {
            "north": row == 0 or room_at[(row - 1, column)] != own_room,
            "south": row == rows - 1 or room_at[(row + 1, column)] != own_room,
            "west": column == 0 or room_at[(row, column - 1)] != own_room,
            "east": column == columns - 1 or room_at[(row, column + 1)] != own_room,
        }

    def _cells_not_adjacent_to_wall(self, puzzle: dict[str, Any]) -> set[int]:
        n = int(puzzle["board"]["rows"])
        return {
            row * n + column
            for row in range(n)
            for column in range(n)
            if not any(self._walls(puzzle, row, column).values())
        }

    def _room_corner_cells(self, puzzle: dict[str, Any]) -> set[int]:
        n = int(puzzle["board"]["rows"])
        result: set[int] = set()
        for row in range(n):
            for column in range(n):
                walls = self._walls(puzzle, row, column)
                if (walls["north"] or walls["south"]) and (walls["west"] or walls["east"]):
                    result.add(row * n + column)
        return result

    def _object_line_cells(self, puzzle: dict[str, Any], object_type: str, *, same_row: bool) -> set[int]:
        n = int(puzzle["board"]["rows"])
        room_at = self._room_at(puzzle)
        object_cells = [
            cell
            for obj in puzzle["board"].get("objects", [])
            if obj["type"] == object_type
            for cell in self._object_cells(obj)
        ]
        result: set[int] = set()
        for row in range(n):
            for column in range(n):
                own_room = room_at[(row, column)]
                if any(
                    room_at[(object_row, object_column)] == own_room
                    and ((object_row == row) if same_row else (object_column == column))
                    for object_row, object_column in object_cells
                ):
                    result.add(row * n + column)
        return result

    def _adjacent_object_cells(self, puzzle: dict[str, Any], object_type: str) -> set[int]:
        n = int(puzzle["board"]["rows"])
        object_cells = [
            cell
            for obj in puzzle["board"].get("objects", [])
            if obj["type"] == object_type
            for cell in self._object_cells(obj)
        ]
        return {
            row * n + column
            for row in range(n)
            for column in range(n)
            if any(abs(row - object_row) + abs(column - object_column) == 1 for object_row, object_column in object_cells)
        }
