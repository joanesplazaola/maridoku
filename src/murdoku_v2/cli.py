from __future__ import annotations

import argparse
import json
from pathlib import Path

from .clue_catalog import catalog_json
from .explainer import explain_puzzle
from .generation import generate_case
from .models import load_puzzle
from .object_catalog import catalog_json as object_catalog_json
from .publication import set_editorial_status
from .render import render_file
from .scaling import (
    run_scaling_benchmark,
    run_scaling_generation_regression,
)
from .site_builder import build_site
from .solvers.registry import availability, get_solver


def _json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _generation_summary(result: dict) -> dict:
    return {
        "puzzle": result["puzzle"]["id"],
        "seed": result["puzzle"]["seed"],
        "size": [
            result["puzzle"]["board"]["rows"],
            result["puzzle"]["board"]["columns"],
        ],
        "victim": result["solution"]["victim_name"],
        "murderer": result["solution"]["murderer_name"],
        "unique": result["diagnostics"]["exact_unique"],
    }


def _validate_with_solver(puzzle_path: Path, solution_path: Path, solver_name: str) -> dict:
    puzzle = load_puzzle(puzzle_path)
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
    parser = argparse.ArgumentParser(description="Generador local de Murdoku")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Genera una variante sobre una escena fija")
    generate_parser.add_argument(
        "--case",
        type=Path,
        default=Path("examples/board_restaurant/case.json"),
    )
    generate_parser.add_argument("--seed", type=int, default=12345)
    generate_parser.add_argument("--output", type=Path, default=Path("generated"))

    validate_parser = subparsers.add_parser("validate", help="Valida un caso con el motor elegido")
    validate_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    validate_parser.add_argument("--solution", type=Path, default=Path("generated/solution.json"))
    validate_parser.add_argument("--solver", choices=["auto", "ortools"], default="auto")

    explain_parser = subparsers.add_parser("explain", help="Regenera la explicación deductiva")
    explain_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    explain_parser.add_argument("--output", type=Path, default=Path("generated/explanation.json"))

    render_parser = subparsers.add_parser("render", help="Renderiza un puzle a HTML imprimible")
    render_parser.add_argument("--puzzle", type=Path, default=Path("generated/puzzle.json"))
    render_parser.add_argument("--output", type=Path, default=Path("generated/puzzle.html"))

    scale_parser = subparsers.add_parser("scale-benchmark", help="Prueba el motor entre 5×5 y 16×16")
    scale_parser.add_argument("--sizes", nargs="+", type=int, default=[5, 8, 12, 16])
    scale_parser.add_argument("--solver", choices=["ortools"], default="ortools")
    scale_parser.add_argument("--repetitions", type=int, default=3)
    scale_parser.add_argument("--output", type=Path, default=Path("scaling_benchmark.json"))

    regression_parser = subparsers.add_parser("scale-regression", help="Valida generación escalable por seeds")
    regression_parser.add_argument("--sizes", nargs="+", type=int, default=[6, 8, 10])
    regression_parser.add_argument("--start-seed", type=int, default=0)
    regression_parser.add_argument("--count-per-size", type=int, default=100)
    regression_parser.add_argument("--budget-seconds", type=float, default=30.0)
    regression_parser.add_argument("--output", type=Path, default=Path("scaling_regression.json"))

    editorial_parser = subparsers.add_parser("editorial-status", help="Aprueba o retira un puzle")
    editorial_parser.add_argument("--manifest", type=Path, required=True)
    editorial_parser.add_argument("--status", choices=["approved", "retired"], required=True)

    site_parser = subparsers.add_parser("build-site", help="Construye el catálogo web")
    site_parser.add_argument("--output", type=Path, default=Path("_site"))

    subparsers.add_parser("solvers", help="Muestra motores y librerías disponibles")
    subparsers.add_parser("catalog", help="Muestra el catálogo formal de pistas")
    subparsers.add_parser("object-catalog", help="Muestra el catálogo de objetos y huellas")

    args = parser.parse_args()
    if args.command == "generate":
        result = generate_case(args.case, args.seed, args.output)
        _json(_generation_summary(result))
    elif args.command == "validate":
        _json(_validate_with_solver(args.puzzle, args.solution, args.solver))
    elif args.command == "explain":
        puzzle = load_puzzle(args.puzzle)
        explanation = explain_puzzle(puzzle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(explanation, ensure_ascii=False, indent=2), encoding="utf-8")
        _json({"puzzle": explanation["puzzle_id"], "difficulty": explanation["difficulty"]["label"], "steps": explanation["step_count"]})
    elif args.command == "render":
        render_file(args.puzzle, args.output)
        _json({"puzzle": str(args.puzzle), "html": str(args.output)})
    elif args.command == "scale-benchmark":
        report = run_scaling_benchmark(
            args.sizes, solver_name=args.solver, repetitions=args.repetitions, output=args.output,
        )
        _json(report)
    elif args.command == "scale-regression":
        report = run_scaling_generation_regression(
            args.sizes,
            start_seed=args.start_seed,
            count_per_size=args.count_per_size,
            budget_seconds=args.budget_seconds,
            output=args.output,
        )
        _json(report["summary"])
    elif args.command == "editorial-status":
        _json(set_editorial_status(args.manifest, args.status))
    elif args.command == "build-site":
        _json(build_site(args.output))
    elif args.command == "solvers":
        _json(availability())
    elif args.command == "object-catalog":
        _json(object_catalog_json())
    else:
        _json(catalog_json())


if __name__ == "__main__":
    main()
