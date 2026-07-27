from __future__ import annotations

import json
from pathlib import Path
from statistics import median, quantiles
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal[2]
    sessionId: UUID
    puzzleId: str = Field(min_length=1)
    size: int = Field(gt=0)
    durationSeconds: int = Field(ge=0, le=604_800)
    checks: int = Field(ge=0)
    errors: int = Field(ge=0)
    completed: bool

    @model_validator(mode="after")
    def validate_counts(self) -> "Session":
        if self.errors > self.checks:
            raise ValueError("errors no puede superar checks")
        return self


def _summary(sessions: list[Session]) -> dict[str, Any]:
    completed = [session for session in sessions if session.completed]
    durations = [session.durationSeconds for session in completed]
    return {
        "sessions": len(sessions),
        "completed": len(completed),
        "completion_rate": round(len(completed) / len(sessions), 3) if sessions else 0,
        "median_duration_seconds": median(durations) if durations else None,
        "median_checks": median([session.checks for session in completed]) if completed else None,
        "median_errors": median([session.errors for session in completed]) if completed else None,
    }


def analyze_sessions(
    catalog_path: Path,
    session_paths: list[Path],
    *,
    min_completed: int = 10,
) -> dict[str, Any]:
    if min_completed < 1:
        raise ValueError("min_completed debe ser al menos 1")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    puzzles = {
        entry["puzzle_id"]: {
            "difficulty": entry["difficulty"],
            "size": entry["rows"],
        }
        for entry in catalog
    }
    if len(puzzles) != len(catalog):
        raise ValueError("El catálogo contiene identificadores de puzle repetidos")

    files = sorted({
        file
        for path in session_paths
        for file in (path.rglob("*.json") if path.is_dir() else [path])
    })
    sessions = [Session.model_validate_json(path.read_text(encoding="utf-8")) for path in files]
    session_ids = [session.sessionId for session in sessions]
    if len(set(session_ids)) != len(session_ids):
        raise ValueError("Hay sesiones duplicadas")
    for session in sessions:
        if session.puzzleId not in puzzles:
            raise ValueError(f"Sesión de un puzle no publicado: {session.puzzleId}")
        if session.size != puzzles[session.puzzleId]["size"]:
            raise ValueError(f"Tamaño incorrecto para {session.puzzleId}")

    by_puzzle = {
        puzzle_id: [session for session in sessions if session.puzzleId == puzzle_id]
        for puzzle_id in puzzles
    }
    puzzle_report = {
        puzzle_id: {
            "difficulty": puzzles[puzzle_id]["difficulty"],
            **_summary(puzzle_sessions),
        }
        for puzzle_id, puzzle_sessions in by_puzzle.items()
    }
    labels = ("easy", "medium", "hard", "expert")
    difficulty_report = {}
    for label in labels:
        grouped = [
            session
            for session in sessions
            if puzzles[session.puzzleId]["difficulty"] == label
        ]
        summary = _summary(grouped)
        durations = [session.durationSeconds for session in grouped if session.completed]
        summary["duration_iqr_seconds"] = (
            [round(value, 1) for value in quantiles(durations, n=4, method="inclusive")[::2]]
            if len(durations) >= 2
            else None
        )
        difficulty_report[label] = summary

    missing_difficulties = [
        label for label in labels
        if not any(entry["difficulty"] == label for entry in puzzles.values())
    ]
    under_sampled = [
        puzzle_id for puzzle_id, summary in puzzle_report.items()
        if summary["completed"] < min_completed
    ]
    ranges = [difficulty_report[label]["duration_iqr_seconds"] for label in labels]
    ordered_ranges = not missing_difficulties and all(ranges) and all(
        left[1] < right[0]
        for left, right in zip(ranges, ranges[1:])
    )
    return {
        "schema_version": 1,
        "catalog": str(catalog_path),
        "minimum_completed_per_puzzle": min_completed,
        "puzzles": puzzle_report,
        "difficulties": difficulty_report,
        "gate": {
            "ready_for_editorial_calibration": not under_sampled and ordered_ranges,
            "missing_difficulties": missing_difficulties,
            "under_sampled_puzzles": under_sampled,
            "ordered_non_overlapping_duration_iqrs": ordered_ranges,
        },
    }
