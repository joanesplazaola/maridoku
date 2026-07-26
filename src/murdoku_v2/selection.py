from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from ortools.sat.python import cp_model

from .candidates import candidate_pools, global_candidate_pool
from .human import solve_human
from .solvers.registry import get_solver
from .validator import matches_statement


DIRECTION_FAMILIES = {"coordinate", "relative_diagonal", "relative_distance", "relative_order"}
RELATION_FAMILIES = {"room_relation", "relative_diagonal", "relative_distance", "relative_order"}
FAMILY_PENALTY = {
    "object_occupancy": 0,
    "object_adjacency": 1,
    "object_line": 2,
    "object_negative": 28,
    "room_exact": 3,
    "room_group": 4,
    "room_population": 5,
    "room_composition": 6,
    "room_companion": 7,
    "room_relation": 8,
    "relative_diagonal": 22,
    "relative_distance": 20,
    "relative_order": 24,
    "coordinate": 30,
}


def apply_clues(
    puzzle: dict[str, Any],
    statements: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = copy.deepcopy(puzzle)
    by_character: dict[str, list[dict[str, Any]]] = {}
    for statement in statements:
        if "character" in statement["args"]:
            by_character.setdefault(statement["args"]["character"], []).append(statement)
    for card in selected["cards"]:
        if card["role"] == "victim":
            continue
        card["statements"] = []
        for index, candidate in enumerate(by_character[card["character"]], start=1):
            statement = copy.deepcopy(candidate)
            statement["id"] = f"{card['id']}-statement-{index}"
            card["statements"].append(statement)
    selected["general_clues"] = [
        {
            **copy.deepcopy(statement),
            "id": f"general-clue-{index}",
        }
        for index, statement in enumerate(
            (statement for statement in statements if "character" not in statement["args"]),
            start=1,
        )
    ]
    return selected


def _choose(
    pools: dict[str, list[dict[str, Any]]],
    witnesses: list[dict[str, tuple[int, int]]],
    forbidden: list[set[str]],
    puzzle: dict[str, Any],
    global_pool: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    model = cp_model.CpModel()
    variables = {
        statement["id"]: model.new_bool_var(statement["id"])
        for pool in (*pools.values(), global_pool)
        for statement in pool
    }
    ordered = [statement for pool in (*pools.values(), global_pool) for statement in pool]
    special_sequence = puzzle.get("selection_profile") == "special_sequence"
    for pool in pools.values():
        selected_count = sum(variables[statement["id"]] for statement in pool)
        if special_sequence:
            model.add(selected_count >= 1)
            model.add(selected_count <= 2)
        else:
            model.add(selected_count == 1)
    if special_sequence:
        model.add(sum(
            variables[statement["id"]]
            for pool in pools.values()
            for statement in pool
        ) == len(pools) + 2)
    if global_pool:
        model.add_exactly_one(variables[statement["id"]] for statement in global_pool)

    families: dict[str, list[Any]] = {}
    for pool in (*pools.values(), global_pool):
        for statement in pool:
            families.setdefault(statement["family"], []).append(variables[statement["id"]])
    family_used = {
        family: model.new_bool_var(f"family_{family}")
        for family in families
    }
    for family, family_variables in families.items():
        model.add(sum(family_variables) >= family_used[family])
        for variable in family_variables:
            model.add(variable <= family_used[family])
    model.add(sum(family_used.values()) >= min(4, len(pools)))
    model.add(sum(
        variables[statement["id"]]
        for statement in ordered
        if statement["family"] in DIRECTION_FAMILIES
    ) <= 1)
    model.add(sum(
        variables[statement["id"]]
        for statement in ordered
        if statement["family"].startswith("room_")
    ) >= 1)
    model.add(sum(
        variables[statement["id"]]
        for statement in ordered
        if statement["family"] in RELATION_FAMILIES
    ) >= 1)
    model.add(sum(
        variables[statement["id"]]
        for statement in ordered
        if statement["family"].startswith("object_")
    ) <= (len(pools) + 1) // 2)
    if special_sequence:
        model.add(sum(
            variables[statement["id"]]
            for statement in ordered
            if statement["family"] == "sequence_relation"
        ) >= 1)
    for type_ in {statement["type"] for statement in ordered}:
        model.add(sum(
            variables[statement["id"]]
            for statement in ordered
            if statement["type"] == type_
        ) <= 2)
    object_patterns: dict[tuple[str, str], list[Any]] = {}
    for statement in ordered:
        object_type = statement["args"].get("object_type")
        if object_type:
            object_patterns.setdefault(
                (statement["type"], object_type), []
            ).append(variables[statement["id"]])
    for pattern_variables in object_patterns.values():
        model.add(sum(pattern_variables) <= 1)

    for witness in witnesses:
        eliminated_by = [
            variables[statement["id"]]
            for statement in ordered
            if not matches_statement(statement, witness, puzzle)
        ]
        model.add(sum(eliminated_by) >= 1)
    for selection in forbidden:
        model.add(sum(variables[statement_id] for statement_id in selection) <= len(selection) - 1)

    model.minimize(sum(
        (FAMILY_PENALTY.get(statement["family"], 40) * 1000 + index)
        * variables[statement["id"]]
        for index, statement in enumerate(ordered)
    ))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.randomize_search = False
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No existe una selección que cumpla el contrato editorial.")
    return [
        statement
        for statement in ordered
        if solver.value(variables[statement["id"]])
    ]


def select_clues(
    puzzle: dict[str, Any],
    target: dict[str, tuple[int, int]],
    *,
    max_iterations: int = 200,
) -> dict[str, Any]:
    """Select one necessary clue per suspect through bounded counterexamples."""
    if max_iterations < 1:
        raise ValueError("max_iterations debe ser al menos 1.")
    pools = candidate_pools(puzzle, target)
    global_pool = (
        global_candidate_pool(puzzle, target)
        if puzzle.get("selection_profile") == "global_room"
        else []
    )
    if puzzle.get("selection_profile") == "global_room" and not global_pool:
        raise RuntimeError("La escena no produce ninguna pista global de habitación.")
    victim_statements = [
        statement
        for card in puzzle["cards"]
        if card["role"] == "victim"
        for statement in card["statements"]
    ]
    if (
        len(victim_statements) != 1
        or victim_statements[0]["type"] != "victim_rule"
        or not matches_statement(victim_statements[0], target, puzzle)
    ):
        raise ValueError("El caso debe tener una regla de víctima verdadera.")
    witnesses: list[dict[str, tuple[int, int]]] = []
    forbidden: list[set[str]] = []
    exact = get_solver("ortools")

    for iteration in range(1, max_iterations + 1):
        selected = _choose(pools, witnesses, forbidden, puzzle, global_pool)
        active = (*victim_statements, *selected)
        result = exact.solve(puzzle, limit=2, base_statements=active)
        alternatives = [solution for solution in result.solutions if solution != target]
        if alternatives:
            witnesses.extend(alternatives)
            continue
        if not result.unique or result.solutions != [target]:
            raise RuntimeError("El oráculo exacto no pudo demostrar la solución objetivo.")

        necessary = all(
            len(exact.solve(
                puzzle,
                limit=2,
                base_statements=tuple(statement for statement in active if statement["id"] != candidate["id"]),
            ).solutions) > 1
            for candidate in selected
        )
        if necessary:
            human = solve_human(apply_clues(puzzle, selected))
            if not human["solved"]:
                forbidden.append({statement["id"] for statement in selected})
                continue
            families = Counter(statement["family"] for statement in selected)
            return {
                "statements": selected,
                "iterations": iteration,
                "witnesses": len(witnesses),
                "families": dict(families),
                "directional": sum(
                    statement["family"] in DIRECTION_FAMILIES
                    for statement in selected
                ),
                "human_steps": human["step_count"],
                "human_techniques": human["techniques"],
                "human_complexity": human["complexity"],
            }
        forbidden.append({statement["id"] for statement in selected})

    raise RuntimeError(f"No se encontró una selección en {max_iterations} iteraciones.")
