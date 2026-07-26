from __future__ import annotations

from collections import Counter
from typing import Any

from .clue_catalog import CLUE_SPECS


PLAYER_TYPES = {"victim_rule", *CLUE_SPECS}


def audit_puzzle(puzzle: dict[str, Any]) -> dict[str, Any]:
    statements = [
        *puzzle.get("general_clues", []),
        *(statement for card in puzzle["cards"] for statement in card["statements"]),
    ]
    families = Counter(statement["family"] for statement in statements)
    types = Counter(statement["type"] for statement in statements)
    normalized = [statement["text"].strip().casefold() for statement in statements]
    duplicate_texts = sorted(text for text, count in Counter(normalized).items() if count > 1)
    unsupported = sorted({statement["type"] for statement in statements} - PLAYER_TYPES)
    dominant_family, dominant_count = families.most_common(1)[0]
    dominant_ratio = dominant_count / len(statements)
    errors = []
    if duplicate_texts:
        errors.append("duplicate_text")
    if unsupported:
        errors.append("unsupported_player_clue")
    warnings = []
    if dominant_ratio > 0.75:
        warnings.append("dominant_family")
    if types["exact_row"] + types["exact_column"] > len(statements) / 2:
        warnings.append("coordinate_heavy")
    return {
        "accepted": not errors,
        "errors": errors,
        "warnings": warnings,
        "duplicate_texts": duplicate_texts,
        "unsupported_player_types": unsupported,
        "family_distribution": dict(families),
        "type_distribution": dict(types),
        "dominant_family": dominant_family,
        "dominant_family_ratio": round(dominant_ratio, 3),
    }
