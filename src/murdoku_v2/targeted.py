from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .engine import generate

DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2, "expert": 3}
TARGET_SCORE = {"easy": 23, "medium": 43, "hard": 64, "expert": 86}


def _difficulty_distance(requested: str, observed: dict[str, Any]) -> float:
    label = observed["label"]
    label_distance = abs(DIFFICULTY_ORDER[requested] - DIFFICULTY_ORDER[label])
    score_distance = abs(TARGET_SCORE[requested] - int(observed["score"])) / 25.0
    hypothesis = bool(observed["requires_hypothesis"])
    hypothesis_penalty = 0.0
    if requested != "expert" and hypothesis:
        hypothesis_penalty = 2.5
    if requested == "expert" and not hypothesis and int(observed["score"]) < 76:
        hypothesis_penalty = 1.5
    return label_distance * 5.0 + score_distance + hypothesis_penalty


def _matches(requested: str, observed: dict[str, Any]) -> bool:
    if observed["label"] != requested:
        return False
    if requested != "expert" and observed["requires_hypothesis"]:
        return False
    return True


def _rewrite_case_metadata(
    result: dict[str, Any],
    requested_seed: int,
    generation_seed: int,
    requested_difficulty: str,
    attempts_used: int,
    exact_match: bool,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    case_id = f"case-{requested_seed}-{requested_difficulty}"
    result["puzzle"]["id"] = case_id
    result["puzzle"]["seed"] = requested_seed
    result["puzzle"]["generation_seed"] = generation_seed
    result["puzzle"]["requested_difficulty"] = requested_difficulty
    result["puzzle"]["difficulty_match"] = exact_match

    result["solution"]["puzzle_id"] = case_id
    result["diagnostics"]["puzzle_id"] = case_id
    result["diagnostics"]["requested_seed"] = requested_seed
    result["diagnostics"]["generation_seed"] = generation_seed
    result["diagnostics"]["requested_difficulty"] = requested_difficulty
    result["diagnostics"]["difficulty_match"] = exact_match
    result["diagnostics"]["generation_attempts"] = attempts_used
    result["diagnostics"]["difficulty_candidates"] = candidates
    result["explanation"]["puzzle_id"] = case_id
    return result


def generate_targeted(
    board_path: Path,
    seed: int,
    output_dir: Path,
    difficulty: str,
    max_attempts: int = 16,
    require_exact: bool = False,
) -> dict[str, Any]:
    difficulty = difficulty.lower()
    if difficulty not in DIFFICULTY_ORDER:
        raise ValueError(f"Dificultad desconocida: {difficulty}")
    if max_attempts < 1:
        raise ValueError("max_attempts debe ser al menos 1")

    candidates: list[dict[str, Any]] = []
    best: tuple[float, int, dict[str, Any], Path] | None = None

    with tempfile.TemporaryDirectory(prefix=f"murdoku-{difficulty}-") as temp_root:
        temp_root_path = Path(temp_root)
        for attempt in range(max_attempts):
            generation_seed = seed + attempt
            candidate_dir = temp_root_path / f"attempt-{attempt + 1}"
            started = time.perf_counter()
            try:
                result = generate(
                    board_path,
                    generation_seed,
                    candidate_dir,
                    selection_profile=difficulty,
                    max_target_attempts=16,
                )
            except Exception as exc:
                candidates.append({
                    "attempt": attempt + 1,
                    "generation_seed": generation_seed,
                    "status": "generation_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue

            observed = result["diagnostics"]["human_difficulty"]
            distance = _difficulty_distance(difficulty, observed)
            exact = _matches(difficulty, observed)
            candidate_summary = {
                "attempt": attempt + 1,
                "generation_seed": generation_seed,
                "status": "exact" if exact else "near",
                "observed_difficulty": observed["label"],
                "score": observed["score"],
                "requires_hypothesis": observed["requires_hypothesis"],
                "distance": round(distance, 3),
                "generation_seconds": round(time.perf_counter() - started, 4),
                "families": result["diagnostics"]["family_distribution"],
                "double_cards": result["diagnostics"]["double_card_count"],
            }
            candidates.append(candidate_summary)

            if best is None or distance < best[0]:
                best = (distance, generation_seed, result, candidate_dir)
            if exact:
                best = (distance, generation_seed, result, candidate_dir)
                break

        if best is None:
            raise RuntimeError(
                f"No se pudo generar ningún candidato válido para {difficulty} en {max_attempts} intentos."
            )

        _, generation_seed, result, candidate_dir = best
        exact_match = _matches(difficulty, result["diagnostics"]["human_difficulty"])
        if require_exact and not exact_match:
            observed = result["diagnostics"]["human_difficulty"]
            raise RuntimeError(
                f"No se encontró un caso {difficulty} exacto en {max_attempts} intentos; "
                f"el más cercano fue {observed['label']} ({observed['score']}/100)."
            )

        result = _rewrite_case_metadata(
            result,
            requested_seed=seed,
            generation_seed=generation_seed,
            requested_difficulty=difficulty,
            attempts_used=len(candidates),
            exact_match=exact_match,
            candidates=candidates,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        # Copy any future supplementary outputs, then overwrite JSON with rewritten metadata.
        for path in candidate_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, output_dir / path.name)
        for name in ("puzzle", "solution", "diagnostics", "explanation"):
            (output_dir / f"{name}.json").write_text(
                json.dumps(result[name], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return result
