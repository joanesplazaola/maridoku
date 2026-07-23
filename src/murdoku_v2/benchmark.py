from __future__ import annotations

import csv
import json
import math
import statistics
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .engine import generate
from .targeted import generate_targeted


def run_benchmark(
    board_path: Path,
    start_seed: int,
    count: int,
    output_dir: Path,
    difficulty: str = "any",
    max_attempts: int = 12,
    target_attempts: int = 16,
) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count debe ser al menos 1")

    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="murdoku-benchmark-") as temp_root:
        temp_root_path = Path(temp_root)
        for offset in range(count):
            seed = start_seed + offset
            case_dir = temp_root_path / str(seed)
            started = time.perf_counter()
            try:
                result = (
                    generate(board_path, seed, case_dir, max_target_attempts=target_attempts)
                    if difficulty == "any"
                    else generate_targeted(
                        board_path, seed, case_dir, difficulty, max_attempts=max_attempts
                    )
                )
            except Exception as exc:  # benchmark must record generator failures rather than aborting.
                failures.append({"seed": seed, "error": f"{type(exc).__name__}: {exc}"})
                continue
            elapsed = time.perf_counter() - started
            diagnostics = result["diagnostics"]
            human_difficulty = diagnostics["human_difficulty"]
            cases.append({
                "seed": seed,
                "generation_seconds": round(elapsed, 4),
                "difficulty": human_difficulty["label"],
                "difficulty_score": human_difficulty["score"],
                "requires_hypothesis": human_difficulty["requires_hypothesis"],
                "propagation_steps": human_difficulty["propagation_steps"],
                "candidate_removals": human_difficulty["candidate_removals"],
                "cross_character_steps": human_difficulty["cross_character_steps"],
                "repeated_constraint_uses": human_difficulty["repeated_constraint_uses"],
                "branch_count": human_difficulty["branch_count"],
                "first_forced_step": human_difficulty["first_forced_step"],
                "double_card_count": diagnostics["double_card_count"],
                "total_statement_count": diagnostics["total_statement_count"],
                "family_distribution": diagnostics["family_distribution"],
                "type_distribution": diagnostics["type_distribution"],
                "all_cards_necessary": diagnostics["all_cards_necessary"],
                "human_solver_matches_solution": diagnostics["human_solver_matches_solution"],
                "requested_difficulty": diagnostics.get("requested_difficulty", "any"),
                "difficulty_match": diagnostics.get("difficulty_match", True),
                "generation_attempts": diagnostics.get("generation_attempts", 1),
                "generation_targets_attempted": diagnostics.get("generation_targets_attempted", 1),
                "generation_rejection_summary": diagnostics.get("generation_rejection_summary", {}),
                "selector_method": diagnostics.get("global_selector", {}).get("method", "unknown"),
                "dependency_depth": diagnostics.get("card_dependency_graph", {}).get("max_dependency_depth", 0),
                "dependency_edges": diagnostics.get("card_dependency_graph", {}).get("edge_count", 0),
                "exact_unique": diagnostics.get("exact_validation", {}).get("unique", False),
                "exact_matches_solution": diagnostics.get("exact_validation", {}).get("matches_solution", False),
                "exact_elapsed_ms": diagnostics.get("exact_validation", {}).get("stats", {}).get("elapsed_ms"),
            })

    labels = Counter(case["difficulty"] for case in cases)
    family_totals: Counter[str] = Counter()
    type_totals: Counter[str] = Counter()
    for case in cases:
        family_totals.update(case["family_distribution"])
        type_totals.update(case["type_distribution"])

    times = [case["generation_seconds"] for case in cases]
    scores = [case["difficulty_score"] for case in cases]
    summary = {
        "requested_cases": count,
        "successful_cases": len(cases),
        "failed_cases": len(failures),
        "success_rate": round(len(cases) / count, 4),
        "start_seed": start_seed,
        "end_seed": start_seed + count - 1,
        "requested_difficulty": difficulty,
        "difficulty_match_cases": sum(bool(case["difficulty_match"]) for case in cases),
        "generation_seconds": {
            "mean": round(statistics.mean(times), 4) if times else None,
            "median": round(statistics.median(times), 4) if times else None,
            "min": min(times) if times else None,
            "max": max(times) if times else None,
        },
        "difficulty_score": {
            "mean": round(statistics.mean(scores), 2) if scores else None,
            "median": round(statistics.median(scores), 2) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "difficulty_distribution": dict(sorted(labels.items())),
        "hypothesis_required_cases": sum(bool(case["requires_hypothesis"]) for case in cases),
        "double_card_cases": sum(case["double_card_count"] > 0 for case in cases),
        "all_cards_necessary_cases": sum(bool(case["all_cards_necessary"]) for case in cases),
        "human_solver_match_cases": sum(bool(case["human_solver_matches_solution"]) for case in cases),
        "exact_unique_cases": sum(bool(case["exact_unique"]) for case in cases),
        "exact_match_cases": sum(bool(case["exact_matches_solution"]) for case in cases),
        "exact_elapsed_ms": {
            "mean": round(statistics.mean(case["exact_elapsed_ms"] for case in cases), 3) if cases else None,
            "max": round(max(case["exact_elapsed_ms"] for case in cases), 3) if cases else None,
        },
        "family_totals": dict(family_totals.most_common()),
        "type_totals": dict(type_totals.most_common()),
        "calibration_status": "provisional_manual_review_required",
    }
    report = {"summary": summary, "cases": cases, "failures": failures}

    (output_dir / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fieldnames = [
        "seed", "generation_seconds", "difficulty", "difficulty_score",
        "requires_hypothesis", "propagation_steps", "candidate_removals",
        "cross_character_steps", "repeated_constraint_uses", "branch_count",
        "first_forced_step", "double_card_count", "total_statement_count",
        "all_cards_necessary", "human_solver_matches_solution",
        "requested_difficulty", "difficulty_match", "generation_attempts",
    ]
    with (output_dir / "benchmark.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            writer.writerow({key: case[key] for key in fieldnames})
    return report


def run_benchmark_suite(
    boards_dir: Path,
    start_seed: int,
    count_per_board: int,
    output_dir: Path,
    difficulty: str = "any",
    max_attempts: int = 12,
    target_attempts: int = 16,
) -> dict[str, Any]:
    """Run the same generator against every board without board-specific code."""
    board_paths = sorted(boards_dir.glob("*.json"))
    if not board_paths:
        raise ValueError(f"No hay tableros JSON en {boards_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    board_reports: list[dict[str, Any]] = []
    combined_cases: list[dict[str, Any]] = []
    combined_failures: list[dict[str, Any]] = []
    for board_offset, board_path in enumerate(board_paths):
        board_output = output_dir / board_path.stem
        report = run_benchmark(
            board_path,
            start_seed + board_offset * count_per_board,
            count_per_board,
            board_output,
            difficulty=difficulty,
            max_attempts=max_attempts, target_attempts=target_attempts,
        )
        board_reports.append({"board": board_path.stem, **report["summary"]})
        for case in report["cases"]:
            combined_cases.append({"board": board_path.stem, **case})
        for failure in report["failures"]:
            combined_failures.append({"board": board_path.stem, **failure})

    times = [case["generation_seconds"] for case in combined_cases]
    scores = [case["difficulty_score"] for case in combined_cases]
    labels = Counter(case["difficulty"] for case in combined_cases)
    family_totals: Counter[str] = Counter()
    type_totals: Counter[str] = Counter()
    rejection_totals: Counter[str] = Counter()
    selector_methods: Counter[str] = Counter()
    for case in combined_cases:
        family_totals.update(case["family_distribution"])
        type_totals.update(case["type_distribution"])
        rejection_totals.update(case.get("generation_rejection_summary", {}))
        selector_methods.update([case.get("selector_method", "unknown")])

    sorted_times = sorted(times)
    p95_index = max(0, min(len(sorted_times) - 1, math.ceil(len(sorted_times) * 0.95) - 1)) if sorted_times else 0
    summary = {
        "board_count": len(board_paths),
        "boards": [path.stem for path in board_paths],
        "count_per_board": count_per_board,
        "requested_cases": len(board_paths) * count_per_board,
        "successful_cases": len(combined_cases),
        "failed_cases": len(combined_failures),
        "success_rate": round(len(combined_cases) / (len(board_paths) * count_per_board), 4),
        "generation_seconds": {
            "mean": round(statistics.mean(times), 4) if times else None,
            "median": round(statistics.median(times), 4) if times else None,
            "p95": sorted_times[p95_index] if sorted_times else None,
            "min": min(times) if times else None,
            "max": max(times) if times else None,
        },
        "difficulty_score": {
            "mean": round(statistics.mean(scores), 2) if scores else None,
            "median": round(statistics.median(scores), 2) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "difficulty_distribution": dict(sorted(labels.items())),
        "all_cards_necessary_cases": sum(bool(case["all_cards_necessary"]) for case in combined_cases),
        "dependency_depth": {
            "mean": round(statistics.mean(case["dependency_depth"] for case in combined_cases), 2) if combined_cases else None,
            "max": max((case["dependency_depth"] for case in combined_cases), default=None),
        },
        "dependency_edges": {
            "mean": round(statistics.mean(case["dependency_edges"] for case in combined_cases), 2) if combined_cases else None,
            "max": max((case["dependency_edges"] for case in combined_cases), default=None),
        },
        "human_solver_match_cases": sum(bool(case["human_solver_matches_solution"]) for case in combined_cases),
        "exact_unique_cases": sum(bool(case["exact_unique"]) for case in combined_cases),
        "exact_match_cases": sum(bool(case["exact_matches_solution"]) for case in combined_cases),
        "exact_elapsed_ms": {
            "mean": round(statistics.mean(case["exact_elapsed_ms"] for case in combined_cases), 3) if combined_cases else None,
            "p95": sorted(case["exact_elapsed_ms"] for case in combined_cases)[p95_index] if combined_cases else None,
            "max": round(max(case["exact_elapsed_ms"] for case in combined_cases), 3) if combined_cases else None,
        },
        "family_totals": dict(family_totals.most_common()),
        "type_totals": dict(type_totals.most_common()),
        "generation_rejection_totals": dict(rejection_totals.most_common()),
        "selector_methods": dict(selector_methods),
        "status": "engine_smoke_benchmark_not_human_calibration",
    }
    result = {
        "summary": summary,
        "boards": board_reports,
        "cases": combined_cases,
        "failures": combined_failures,
    }
    (output_dir / "benchmark_suite.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = [
        "board", "seed", "generation_seconds", "difficulty", "difficulty_score",
        "requires_hypothesis", "double_card_count", "total_statement_count",
        "all_cards_necessary", "human_solver_matches_solution", "selector_method",
        "generation_targets_attempted", "dependency_depth", "dependency_edges",
    ]
    with (output_dir / "benchmark_suite.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in combined_cases:
            writer.writerow({field: case.get(field) for field in fields})
    return result
