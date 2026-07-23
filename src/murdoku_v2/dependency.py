from __future__ import annotations

import math
from typing import Any


def _gain(before: int, after: int) -> float:
    if before <= 0 or after <= 0:
        return 0.0
    return math.log2(before / after)


def analyze_card_dependencies(
    card_masks: dict[str, int],
    all_bits: int,
    metadata: dict[str, dict[str, Any]],
    first_card_id: str | None = None,
    threshold_bits: float = 0.05,
) -> dict[str, Any]:
    """Build an empirical dependency DAG between whole cards.

    A -> B means B becomes more informative after A is already known. The graph is tied to
    an explicit deterministic application order, so it remains acyclic and inspectable.
    It is not claimed to be a perfect cognitive model; it is a stable structural metric.
    """

    remaining = list(card_masks)
    order: list[str] = []
    current = all_bits
    if first_card_id and first_card_id in remaining:
        order.append(first_card_id)
        current &= card_masks[first_card_id]
        remaining.remove(first_card_id)
    while remaining:
        # Most constraining next card; deterministic tie break by id.
        card_id = min(
            remaining,
            key=lambda item: ((current & card_masks[item]).bit_count(), item),
        )
        order.append(card_id)
        current &= card_masks[card_id]
        remaining.remove(card_id)

    edges: list[dict[str, Any]] = []
    depths: dict[str, int] = {}
    prefix_cards: list[str] = []
    for card_id in order:
        prefix_mask = all_bits
        for previous in prefix_cards:
            prefix_mask &= card_masks[previous]
        before = prefix_mask.bit_count()
        after = (prefix_mask & card_masks[card_id]).bit_count()
        gain_with_context = _gain(before, after)
        parents: list[str] = []
        for source in prefix_cards:
            without_source = all_bits
            for previous in prefix_cards:
                if previous != source:
                    without_source &= card_masks[previous]
            before_without = without_source.bit_count()
            after_without = (without_source & card_masks[card_id]).bit_count()
            gain_without_source = _gain(before_without, after_without)
            strength = gain_with_context - gain_without_source
            if strength > threshold_bits:
                parents.append(source)
                edges.append({
                    "from": source,
                    "to": card_id,
                    "strength_bits": round(strength, 3),
                    "target_gain_with_context_bits": round(gain_with_context, 3),
                    "target_gain_without_source_bits": round(gain_without_source, 3),
                })
        depths[card_id] = 1 + max((depths[parent] for parent in parents), default=0)
        prefix_cards.append(card_id)

    nodes = []
    total = all_bits.bit_count()
    for index, card_id in enumerate(order):
        mask_count = card_masks[card_id].bit_count()
        nodes.append({
            "id": card_id,
            "order": index + 1,
            "role": metadata.get(card_id, {}).get("role"),
            "character": metadata.get(card_id, {}).get("character"),
            "families": metadata.get(card_id, {}).get("families", []),
            "standalone_solutions": mask_count,
            "standalone_information_bits": round(_gain(total, mask_count), 3),
            "dependency_depth": depths[card_id],
        })
    return {
        "definition": "A→B cuando B gana información marginal al conocer previamente A.",
        "application_order": order,
        "nodes": nodes,
        "edges": edges,
        "edge_count": len(edges),
        "max_dependency_depth": max(depths.values(), default=0),
        "cards_with_dependencies": sum(any(edge["to"] == node for edge in edges) for node in order),
    }
