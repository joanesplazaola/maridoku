from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from murdoku_v2.solvers.backtracking import BacktrackingSolver
from murdoku_v2.solvers.ortools_solver import ORToolsSolver


def canonical(solution: dict[str, tuple[int, int]]) -> tuple[tuple[str, tuple[int, int]], ...]:
    return tuple(sorted((key, tuple(value)) for key, value in solution.items()))


def load_examples() -> list[tuple[str, dict[str, Any]]]:
    examples: list[tuple[str, dict[str, Any]]] = []
    for puzzle_path in sorted((ROOT / "examples").glob("*/puzzle.json")):
        examples.append((puzzle_path.parent.name, json.loads(puzzle_path.read_text(encoding="utf-8"))))
    if not examples:
        raise RuntimeError("No se encontraron puzzles de ejemplo.")
    return examples


def timed_runs(solver: Any, puzzle: dict[str, Any], repeats: int) -> tuple[Any, list[float]]:
    result = solver.solve(puzzle, limit=2)
    elapsed: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        current = solver.solve(puzzle, limit=2)
        elapsed.append((time.perf_counter() - started) * 1000)
        if {canonical(item) for item in current.solutions} != {canonical(item) for item in result.solutions}:
            raise AssertionError("El solver no devolvió soluciones reproducibles.")
    return result, elapsed


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara CP-SAT y backtracking sobre los casos reales.")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "cpsat_benchmark")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    cpsat = ORToolsSolver(num_search_workers=1)
    if not cpsat.is_available():
        payload = {
            "status": "blocked",
            "reason": "OR-Tools no está instalado en este entorno.",
            "install_command": "python -m pip install ortools==9.15.6755",
        }
        (args.output / "benchmark_blocked.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    rows: list[dict[str, Any]] = []
    for board_name, puzzle in load_examples():
        backtracking_result, backtracking_times = timed_runs(BacktrackingSolver(), puzzle, args.repeats)
        cpsat_result, cpsat_times = timed_runs(cpsat, puzzle, args.repeats)

        backtracking_solutions = {canonical(item) for item in backtracking_result.solutions}
        cpsat_solutions = {canonical(item) for item in cpsat_result.solutions}
        if backtracking_solutions != cpsat_solutions:
            raise AssertionError(f"CP-SAT y backtracking discrepan en {board_name}.")

        metadata = cpsat_result.stats.metadata
        row = {
            "board": board_name,
            "solutions": len(cpsat_result.solutions),
            "unique": cpsat_result.unique,
            "match": True,
            "backtracking_mean_ms": statistics.mean(backtracking_times),
            "backtracking_p50_ms": statistics.median(backtracking_times),
            "backtracking_p95_ms": percentile(backtracking_times, 0.95),
            "cpsat_total_mean_ms": statistics.mean(cpsat_times),
            "cpsat_total_p50_ms": statistics.median(cpsat_times),
            "cpsat_total_p95_ms": percentile(cpsat_times, 0.95),
            "cpsat_model_build_ms": metadata.get("model_build_ms"),
            "cpsat_first_solution_ms": metadata.get("first_solution_ms"),
            "cpsat_uniqueness_check_ms": metadata.get("uniqueness_check_ms"),
            "cpsat_variables": metadata.get("variable_count"),
            "cpsat_constraints": metadata.get("constraint_count"),
            "cpsat_branches": cpsat_result.stats.nodes,
            "cpsat_conflicts": cpsat_result.stats.backtracks,
            "ortools_version": metadata.get("ortools_version"),
        }
        row["cpsat_vs_backtracking_ratio"] = row["cpsat_total_mean_ms"] / row["backtracking_mean_ms"]
        rows.append(row)
        print(
            f"{board_name}: BT={row['backtracking_mean_ms']:.3f} ms, "
            f"CP-SAT={row['cpsat_total_mean_ms']:.3f} ms, "
            f"ratio={row['cpsat_vs_backtracking_ratio']:.2f}x"
        )

    summary = {
        "status": "completed",
        "repeats_per_board": args.repeats,
        "boards": len(rows),
        "all_solution_sets_match": all(row["match"] for row in rows),
        "backtracking_mean_ms": statistics.mean(row["backtracking_mean_ms"] for row in rows),
        "cpsat_total_mean_ms": statistics.mean(row["cpsat_total_mean_ms"] for row in rows),
        "cpsat_model_build_mean_ms": statistics.mean(row["cpsat_model_build_ms"] for row in rows),
        "cpsat_first_solution_mean_ms": statistics.mean(row["cpsat_first_solution_ms"] for row in rows),
        "cpsat_uniqueness_mean_ms": statistics.mean(row["cpsat_uniqueness_check_ms"] for row in rows),
        "rows": rows,
    }
    summary["cpsat_vs_backtracking_ratio"] = summary["cpsat_total_mean_ms"] / summary["backtracking_mean_ms"]

    json_path = args.output / "cpsat_vs_backtracking.json"
    csv_path = args.output / "cpsat_vs_backtracking.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
