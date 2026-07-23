from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .engine import (
    AtomicClue,
    CHARACTERS,
    atomic_mask,
    board_geometry,
    build_board_arrays,
    enumerate_base_solutions,
)


FAMILY_COMPLEXITY = {
    "coordinate": 0.8,
    "room_exact": 0.9,
    "object_adjacency": 1.0,
    "object_occupancy": 1.15,
    "room_geometry": 1.15,
    "room_group": 1.2,
    "room_choice": 1.3,
    "relative_order": 1.25,
    "relative_distance": 1.4,
    "object_line": 1.45,
    "room_population": 1.5,
    "room_companion": 1.65,
    "room_composition": 1.75,
    "murder_rule": 1.7,
    "all_different": 1.35,
}


@dataclass(frozen=True)
class Constraint:
    id: str
    card_id: str | None
    character: str | None
    text: str
    type: str
    family: str
    mask: np.ndarray
    scope: tuple[int, ...]
    complexity: float


@dataclass
class SolveStats:
    propagation_steps: int = 0
    candidate_removals: int = 0
    cross_character_steps: int = 0
    repeated_constraint_uses: int = 0
    branch_count: int = 0
    rejected_hypotheses: int = 0
    max_branch_depth: int = 0
    first_forced_step: int | None = None


def _statement_scope(statement: dict[str, Any], index_by_id: dict[str, int], n: int) -> tuple[int, ...]:
    statement_type = statement["type"]
    args = statement["args"]
    subject = index_by_id[args["character"]]
    all_indexes = tuple(range(n))

    if statement_type in {
        "victim_rule",
        "room_population",
        "alone_in_room",
        "room_gender_count",
        "companion_gender_count",
        "alone_with_gender",
        "unique_on_object",
    }:
        return all_indexes
    if statement_type in {
        "relative_row_order",
        "relative_column_order",
        "relative_row_distance",
        "relative_column_distance",
        "same_room",
        "different_room",
    }:
        return (subject, index_by_id[args["reference"]])
    return (subject,)


def _build_constraints(puzzle: dict[str, Any], base: np.ndarray) -> list[Constraint]:
    board = puzzle["board"]
    room_flat, _, _, room_index, group_room_indexes = build_board_arrays(board)
    geometry = board_geometry(board, room_flat)
    index_by_id = {character["id"]: index for index, character in enumerate(puzzle["characters"])}
    victim_index = index_by_id[puzzle["victim"]]
    n = len(index_by_id)

    constraints: list[Constraint] = [
        Constraint(
            id="rule-all-different",
            card_id=None,
            character=None,
            text="Ninguna pareja de personajes puede compartir fila ni columna.",
            type="all_different",
            family="all_different",
            mask=np.ones(len(base), dtype=bool),
            scope=tuple(range(n)),
            complexity=FAMILY_COMPLEXITY["all_different"],
        )
    ]

    for card in puzzle["cards"]:
        for statement in card["statements"]:
            if statement["type"] == "victim_rule":
                solution_rooms = room_flat[base]
                victim_rooms = solution_rooms[:, [victim_index]]
                mask = np.sum(solution_rooms == victim_rooms, axis=1) == 2
            else:
                clue = AtomicClue(
                    subject=statement["args"]["character"],
                    type=statement["type"],
                    family=statement["family"],
                    args=statement["args"],
                    text=statement["text"],
                )
                mask = atomic_mask(
                    clue,
                    base,
                    board,
                    room_flat,
                    room_index,
                    group_room_indexes,
                    geometry,
                    CHARACTERS,
                )
            constraints.append(
                Constraint(
                    id=statement["id"],
                    card_id=card["id"],
                    character=card["character"],
                    text=statement["text"],
                    type=statement["type"],
                    family=statement["family"],
                    mask=mask,
                    scope=_statement_scope(statement, index_by_id, n),
                    complexity=FAMILY_COMPLEXITY.get(statement["family"], 1.5),
                )
            )

    # Easier/direct constraints are considered before global or highly relational ones.
    return sorted(constraints, key=lambda item: (item.complexity, item.id))


def _domain_support_mask(base: np.ndarray, domains: list[set[int]], scope: tuple[int, ...]) -> np.ndarray:
    compatible = np.ones(len(base), dtype=bool)
    for index in scope:
        compatible &= np.isin(base[:, index], list(domains[index]))
    return compatible


def _cell_label(cell: int, n: int) -> str:
    return f"F{cell // n + 1}C{cell % n + 1}"


def _domains_json(domains: list[set[int]], ids: list[str], n: int) -> dict[str, list[dict[str, int]]]:
    return {
        char_id: [
            {"row": cell // n, "column": cell % n}
            for cell in sorted(domains[index])
        ]
        for index, char_id in enumerate(ids)
    }


def _forced_positions(domains: list[set[int]], ids: list[str], n: int) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for index, domain in enumerate(domains):
        if len(domain) == 1:
            cell = next(iter(domain))
            result[ids[index]] = {"row": cell // n, "column": cell % n}
    return result


def _propagate(
    base: np.ndarray,
    constraints: list[Constraint],
    domains: list[set[int]],
    ids: list[str],
    names: dict[str, str],
    n: int,
    stats: SolveStats,
    trace: list[dict[str, Any]],
    depth: int = 0,
) -> bool:
    use_counts: dict[str, int] = {}
    changed = True
    while changed:
        changed = False
        candidates: list[tuple[float, Constraint, dict[int, set[int]], int]] = []
        for constraint in constraints:
            compatible = constraint.mask & _domain_support_mask(base, domains, constraint.scope)
            if not np.any(compatible):
                return False
            reductions: dict[int, set[int]] = {}
            total_removed = 0
            for index in constraint.scope:
                supported = set(int(value) for value in np.unique(base[compatible, index]))
                new_domain = domains[index] & supported
                if not new_domain:
                    return False
                removed = domains[index] - new_domain
                if removed:
                    reductions[index] = removed
                    total_removed += len(removed)
            if reductions:
                forced = sum(len(domains[index]) > 1 and len(domains[index] - removed) == 1 for index, removed in reductions.items())
                cross = sum(index != next((i for i, char_id in enumerate(ids) if char_id == constraint.character), -1) for index in reductions)
                # Prefer understandable deductions, then those that force a position.
                priority = (forced * 12 + total_removed + cross * 1.5) / max(0.6, constraint.complexity)
                candidates.append((priority, constraint, reductions, total_removed))

        if not candidates:
            break
        candidates.sort(key=lambda item: (item[0], item[3]), reverse=True)
        _, constraint, reductions, total_removed = candidates[0]
        before_forced = set(_forced_positions(domains, ids, n))
        before_total = sum(len(domain) for domain in domains)
        removed_json: dict[str, list[str]] = {}
        affected_ids: list[str] = []
        for index, removed in reductions.items():
            domains[index] -= removed
            removed_json[ids[index]] = [_cell_label(cell, n) for cell in sorted(removed)]
            affected_ids.append(ids[index])
        after_forced_map = _forced_positions(domains, ids, n)
        newly_forced = {
            char_id: position
            for char_id, position in after_forced_map.items()
            if char_id not in before_forced
        }

        use_counts[constraint.id] = use_counts.get(constraint.id, 0) + 1
        if use_counts[constraint.id] > 1:
            stats.repeated_constraint_uses += 1
        stats.propagation_steps += 1
        stats.candidate_removals += total_removed
        owner_index = next((i for i, char_id in enumerate(ids) if char_id == constraint.character), None)
        if owner_index is None or any(index != owner_index for index in reductions):
            stats.cross_character_steps += 1
        if newly_forced and stats.first_forced_step is None:
            stats.first_forced_step = stats.propagation_steps

        forced_text = ""
        if newly_forced:
            labels = [
                f"{names[char_id]} queda en F{position['row'] + 1}C{position['column'] + 1}"
                for char_id, position in newly_forced.items()
            ]
            forced_text = " " + "; ".join(labels) + "."
        prefix = "Al volver a cruzar" if use_counts[constraint.id] > 1 else "Al aplicar"
        explanation = (
            f"{prefix} «{constraint.text}» se descartan {total_removed} posibilidades"
            f" entre {len(affected_ids)} personaje{'s' if len(affected_ids) != 1 else ''}.{forced_text}"
        )
        trace.append({
            "index": len(trace) + 1,
            "kind": "propagation",
            "depth": depth,
            "constraint_id": constraint.id,
            "card_id": constraint.card_id,
            "character": constraint.character,
            "type": constraint.type,
            "family": constraint.family,
            "clue_text": constraint.text,
            "explanation": explanation,
            "candidate_count_before": before_total,
            "candidate_count_after": sum(len(domain) for domain in domains),
            "removed": removed_json,
            "newly_forced": newly_forced,
            "domains_after": _domains_json(domains, ids, n),
        })
        changed = True
    return True


def _is_complete(domains: list[set[int]]) -> bool:
    return all(len(domain) == 1 for domain in domains)


def _search(
    base: np.ndarray,
    constraints: list[Constraint],
    domains: list[set[int]],
    ids: list[str],
    names: dict[str, str],
    n: int,
    stats: SolveStats,
    trace: list[dict[str, Any]],
    depth: int = 0,
) -> list[set[int]] | None:
    stats.max_branch_depth = max(stats.max_branch_depth, depth)
    if not _propagate(base, constraints, domains, ids, names, n, stats, trace, depth):
        return None
    if _is_complete(domains):
        return domains

    index = min((i for i, domain in enumerate(domains) if len(domain) > 1), key=lambda i: len(domains[i]))
    character_id = ids[index]
    candidates = sorted(domains[index])
    stats.branch_count += 1

    for cell in candidates:
        trial_domains = [set(domain) for domain in domains]
        trial_domains[index] = {cell}
        branch_trace: list[dict[str, Any]] = []
        trace.append({
            "index": len(trace) + 1,
            "kind": "assumption",
            "depth": depth + 1,
            "character": character_id,
            "explanation": f"Hipótesis: {names[character_id]} está en {_cell_label(cell, n)}.",
            "position": {"row": cell // n, "column": cell % n},
            "domains_after": _domains_json(trial_domains, ids, n),
        })
        solved = _search(base, constraints, trial_domains, ids, names, n, stats, branch_trace, depth + 1)
        if solved is not None:
            trace.extend(branch_trace)
            return solved
        stats.rejected_hypotheses += 1
        trace.append({
            "index": len(trace) + 1,
            "kind": "rejection",
            "depth": depth + 1,
            "character": character_id,
            "explanation": f"La hipótesis {_cell_label(cell, n)} provoca una contradicción y se descarta.",
            "position": {"row": cell // n, "column": cell % n},
            "domains_after": _domains_json(domains, ids, n),
        })
        domains[index].discard(cell)
        if not domains[index]:
            return None
        if not _propagate(base, constraints, domains, ids, names, n, stats, trace, depth):
            return None
        if _is_complete(domains):
            return domains
    return None


def _difficulty(stats: SolveStats, puzzle: dict[str, Any]) -> dict[str, Any]:
    direct_count = sum(
        statement["family"] in {"coordinate", "room_exact"}
        for card in puzzle["cards"]
        for statement in card["statements"]
    )
    double_cards = sum(len(card["statements"]) == 2 for card in puzzle["cards"] if card["role"] == "suspect")
    first_forced = stats.first_forced_step or stats.propagation_steps + 2
    score = (
        8
        + stats.propagation_steps * 2.0
        + stats.cross_character_steps * 2.7
        + stats.repeated_constraint_uses * 1.8
        + min(first_forced, 10) * 1.2
        + double_cards * 4.0
        + stats.rejected_hypotheses * 12.0
        + stats.max_branch_depth * 8.0
        - direct_count * 2.0
    )
    score = max(1, min(100, round(score)))
    if stats.branch_count > 0 or score >= 76:
        label = "expert"
    elif score >= 54:
        label = "hard"
    elif score >= 34:
        label = "medium"
    else:
        label = "easy"
    return {
        "label": label,
        "score": score,
        "requires_hypothesis": stats.branch_count > 0,
        "propagation_steps": stats.propagation_steps,
        "candidate_removals": stats.candidate_removals,
        "cross_character_steps": stats.cross_character_steps,
        "repeated_constraint_uses": stats.repeated_constraint_uses,
        "branch_count": stats.branch_count,
        "rejected_hypotheses": stats.rejected_hypotheses,
        "max_branch_depth": stats.max_branch_depth,
        "first_forced_step": stats.first_forced_step,
        "direct_clue_count": direct_count,
        "double_card_count": double_cards,
        "method": "generalized_constraint_propagation_with_optional_hypotheses",
        "calibration_status": "provisional",
    }


def analyze_puzzle(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Produce an approximate human-style deductive trace without reading solution.json."""
    board = puzzle["board"]
    base = enumerate_base_solutions(board)
    constraints = _build_constraints(puzzle, base)
    n = board["rows"]
    ids = [character["id"] for character in puzzle["characters"]]
    names = {character["id"]: character["name"] for character in puzzle["characters"]}
    domains = [set(range(n * n)) for _ in ids]
    trace: list[dict[str, Any]] = []
    stats = SolveStats()
    solved = _search(base, constraints, domains, ids, names, n, stats, trace)
    if solved is None or not _is_complete(solved):
        raise RuntimeError("El solucionador deductivo no pudo resolver el puzle.")

    positions = {
        ids[index]: {
            "row": next(iter(domain)) // n,
            "column": next(iter(domain)) % n,
        }
        for index, domain in enumerate(solved)
    }
    return {
        "puzzle_id": puzzle["id"],
        "solver_kind": "approximate_human_deduction",
        "note": (
            "La dificultad es provisional. El motor aplica consistencia de restricciones y propagación global; "
            "puede realizar deducciones más sistemáticas que una persona."
        ),
        "difficulty": _difficulty(stats, puzzle),
        "step_count": len(trace),
        "steps": trace,
        "final_positions": positions,
    }
