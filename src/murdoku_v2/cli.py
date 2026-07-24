from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .benchmark import run_benchmark, run_benchmark_suite
from .clue_catalog import catalog_json
from .engine import generate
from .human_solver import analyze_puzzle
from .object_catalog import catalog_json as object_catalog_json
from .render import render_file
from .scaling import generate_scaling_case, run_scaling_benchmark
from .solvers.registry import availability, get_solver
from .targeted import generate_targeted


console = Console()


def _json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _validate_with_solver(puzzle_path: Path, solution_path: Path, solver_name: str) -> dict:
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    expected = json.loads(solution_path.read_text(encoding="utf-8"))
    result = get_solver(solver_name).solve(puzzle, limit=2)
    expected_positions = {
        character: (position["row"], position["column"])
        for character, position in expected["positions"].items()
    }
    matches = bool(result.unique and result.solutions[0] == expected_positions)
    murderer_matches = False
    if matches:
        room_at = {
            tuple(cell): room["id"]
            for room in puzzle["board"]["rooms"]
            for cell in room["cells"]
        }
        victim = puzzle["victim"]
        victim_room = room_at[result.solutions[0][victim]]
        companions = [
            character for character, position in result.solutions[0].items()
            if character != victim and room_at[position] == victim_room
        ]
        murderer_matches = companions == [expected["murderer"]]
    return {
        **result.to_dict(include_solutions=False),
        "matches_generated_solution": matches,
        "murderer_matches": murderer_matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador local Murdoku V2-beta")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Genera un caso JSON")
    generate_parser.add_argument("--board", type=Path, default=Path("boards/board_two_houses.json"))
    generate_parser.add_argument("--seed", type=int, default=12345)
    generate_parser.add_argument("--output", type=Path, default=Path("generated"))
    generate_parser.add_argument("--difficulty", choices=["any", "easy", "medium", "hard", "expert"], default="any")
    generate_parser.add_argument("--max-attempts", type=int, default=16)
    generate_parser.add_argument("--strict", action="store_true")
    generate_parser.add_argument("--target-attempts", type=int, default=24)
    generate_parser.add_argument("--cpsat-selector", action="store_true")

    generate_scale_parser = subparsers.add_parser("generate-scale", help="Genera un caso escalable CP-SAT")
    generate_scale_parser.add_argument("--size", type=int, default=10)
    generate_scale_parser.add_argument("--seed", type=int, default=12345)
    generate_scale_parser.add_argument("--output", type=Path, default=Path("generated_scale"))

    validate_parser = subparsers.add_parser("validate", help="Valida un caso con el motor elegido")
    validate_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    validate_parser.add_argument("--solution", type=Path, default=Path("generated/solution.json"))
    validate_parser.add_argument("--solver", choices=["auto", "ortools", "z3"], default="auto")

    explain_parser = subparsers.add_parser("explain", help="Regenera la explicación deductiva")
    explain_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    explain_parser.add_argument("--output", type=Path, default=Path("generated/explanation.json"))

    render_parser = subparsers.add_parser("render", help="Renderiza un puzle a HTML imprimible")
    render_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    render_parser.add_argument("--output", type=Path, default=Path("generated/puzzle.html"))

    benchmark_parser = subparsers.add_parser("benchmark", help="Genera muchos casos")
    benchmark_parser.add_argument("--board", type=Path, default=Path("boards/board_two_houses.json"))
    benchmark_parser.add_argument("--start-seed", type=int, default=100)
    benchmark_parser.add_argument("--count", type=int, default=10)
    benchmark_parser.add_argument("--output", type=Path, default=Path("benchmark"))
    benchmark_parser.add_argument("--difficulty", choices=["any", "easy", "medium", "hard", "expert"], default="any")
    benchmark_parser.add_argument("--max-attempts", type=int, default=12)
    benchmark_parser.add_argument("--target-attempts", type=int, default=16)

    suite_parser = subparsers.add_parser("benchmark-suite", help="Benchmark en todos los tableros")
    suite_parser.add_argument("--boards", type=Path, default=Path("boards"))
    suite_parser.add_argument("--start-seed", type=int, default=1000)
    suite_parser.add_argument("--count-per-board", type=int, default=5)
    suite_parser.add_argument("--output", type=Path, default=Path("benchmark_suite"))
    suite_parser.add_argument("--difficulty", choices=["any", "easy", "medium", "hard", "expert"], default="any")
    suite_parser.add_argument("--max-attempts", type=int, default=12)
    suite_parser.add_argument("--target-attempts", type=int, default=16)

    scale_parser = subparsers.add_parser("scale-benchmark", help="Prueba 6×6, 8×8, 10×10 y 12×12")
    scale_parser.add_argument("--sizes", nargs="+", type=int, default=[6, 8, 10, 12])
    scale_parser.add_argument("--solver", choices=["ortools", "z3"], default="ortools")
    scale_parser.add_argument("--repetitions", type=int, default=3)
    scale_parser.add_argument("--output", type=Path, default=Path("scaling_benchmark.json"))

    subparsers.add_parser("solvers", help="Muestra motores y librerías disponibles")
    subparsers.add_parser("catalog", help="Muestra el catálogo formal de pistas")
    subparsers.add_parser("object-catalog", help="Muestra el catálogo de objetos y huellas")

    args = parser.parse_args()
    if args.command == "generate":
        if args.difficulty == "any":
            result = generate(
                args.board,
                args.seed,
                args.output,
                max_target_attempts=args.target_attempts,
                use_cpsat_selector=args.cpsat_selector,
            )
        else:
            result = generate_targeted(
                args.board, args.seed, args.output, difficulty=args.difficulty,
                max_attempts=args.max_attempts, require_exact=args.strict,
            )
        diagnostics = result["diagnostics"]
        _json({
            "puzzle": result["puzzle"]["id"],
            "seed": result["puzzle"]["seed"],
            "victim": result["solution"]["victim_name"],
            "murderer": result["solution"]["murderer_name"],
            "final_solutions": diagnostics["final_solution_count"],
            "difficulty": diagnostics["human_difficulty"]["label"],
            "exact": diagnostics["exact_validation"],
        })
    elif args.command == "generate-scale":
        result = generate_scaling_case(args.size, args.seed, args.output)
        _json({
            "puzzle": result["puzzle"]["id"],
            "seed": result["puzzle"]["seed"],
            "size": args.size,
            "victim": result["solution"]["victim_name"],
            "murderer": result["solution"]["murderer_name"],
            "exact": result["diagnostics"]["exact_validation"],
        })
    elif args.command == "validate":
        _json(_validate_with_solver(args.puzzle, args.solution, args.solver))
    elif args.command == "explain":
        puzzle = json.loads(args.puzzle.read_text(encoding="utf-8"))
        explanation = analyze_puzzle(puzzle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(explanation, ensure_ascii=False, indent=2), encoding="utf-8")
        _json({"puzzle": explanation["puzzle_id"], "difficulty": explanation["difficulty"], "steps": explanation["step_count"]})
    elif args.command == "render":
        render_file(args.puzzle, args.output)
        _json({"puzzle": str(args.puzzle), "html": str(args.output)})
    elif args.command == "benchmark":
        report = run_benchmark(
            args.board, args.start_seed, args.count, args.output,
            difficulty=args.difficulty, max_attempts=args.max_attempts,
            target_attempts=args.target_attempts,
        )
        _json(report["summary"])
    elif args.command == "benchmark-suite":
        report = run_benchmark_suite(
            args.boards, args.start_seed, args.count_per_board, args.output,
            difficulty=args.difficulty, max_attempts=args.max_attempts,
            target_attempts=args.target_attempts,
        )
        _json(report["summary"])
    elif args.command == "scale-benchmark":
        report = run_scaling_benchmark(
            args.sizes, solver_name=args.solver, repetitions=args.repetitions, output=args.output,
        )
        _json(report)
    elif args.command == "solvers":
        table = Table(title="Motores disponibles")
        table.add_column("Motor")
        table.add_column("Disponible")
        table.add_column("Papel")
        for item in availability():
            table.add_row(item["name"], "sí" if item["available"] else "no", item["role"])
        console.print(table)
        console.print("CP-SAT viene instalado por defecto; Z3 es opcional con [bold]uv sync --extra solvers[/bold]")
    elif args.command == "object-catalog":
        _json(object_catalog_json())
    else:
        _json(catalog_json())


if __name__ == "__main__":
    main()
