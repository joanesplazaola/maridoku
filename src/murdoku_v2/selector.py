from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .clue_catalog import AtomicClue

RICH_FAMILIES = {
    "object_occupancy", "object_line", "room_composition", "room_population",
    "room_companion", "room_geometry", "room_group", "room_choice",
}


@dataclass(frozen=True)
class CardOption:
    subject: str
    atoms: tuple[AtomicClue, ...]
    mask: int
    standalone_gain: float

    @property
    def key(self) -> tuple[str, ...]:
        return tuple(atom.key for atom in self.atoms)


@dataclass
class SelectionReport:
    method: str = "global_beam_search"
    subject_orders_tried: int = 0
    beam_width: int = 0
    states_expanded: int = 0
    complete_sets_checked: int = 0
    options_per_subject: dict[str, int] = field(default_factory=dict)
    rejected: Counter[str] = field(default_factory=Counter)
    accepted_score: float | None = None
    selected_families: dict[str, int] = field(default_factory=dict)
    selected_types: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "subject_orders_tried": self.subject_orders_tried,
            "beam_width": self.beam_width,
            "states_expanded": self.states_expanded,
            "complete_sets_checked": self.complete_sets_checked,
            "options_per_subject": self.options_per_subject,
            "rejected": dict(self.rejected),
            "accepted_score": self.accepted_score,
            "selected_families": self.selected_families,
            "selected_types": self.selected_types,
        }


@dataclass
class BeamState:
    current: int
    cards: dict[str, tuple[AtomicClue, ...]]
    family_counts: Counter[str]
    score: float
    double_count: int
    gains: tuple[float, ...]


def _profile_limits(profile: str) -> dict[str, Any]:
    return {
        "any": {"min_families": 3, "max_coordinates": 1, "max_relatives": 3, "min_rich": 1, "max_doubles": 2},
        "easy": {"min_families": 3, "max_coordinates": 2, "max_relatives": 2, "min_rich": 1, "max_doubles": 0},
        "medium": {"min_families": 3, "max_coordinates": 1, "max_relatives": 3, "min_rich": 1, "max_doubles": 1},
        "hard": {"min_families": 4, "max_coordinates": 1, "max_relatives": 2, "min_rich": 3, "max_doubles": 2},
        "expert": {"min_families": 4, "max_coordinates": 0, "max_relatives": 2, "min_rich": 3, "max_doubles": 2},
    }[profile]


def quality_reasons(cards: dict[str, tuple[AtomicClue, ...]], profile: str) -> list[str]:
    limits = _profile_limits(profile)
    atoms = [atom for card in cards.values() for atom in card]
    families = [atom.family for atom in atoms]
    reasons: list[str] = []
    if len(set(families)) < limits["min_families"]:
        reasons.append("too_few_families")
    if sum(family in RICH_FAMILIES for family in families) < limits["min_rich"]:
        reasons.append("too_few_rich_clues")
    if sum(family == "coordinate" for family in families) > limits["max_coordinates"]:
        reasons.append("too_many_coordinates")
    if sum(family in {"relative_order", "relative_distance"} for family in families) > limits["max_relatives"]:
        reasons.append("too_many_relative_clues")
    if any(families.count(family) > 3 for family in set(families)):
        reasons.append("family_overrepresented")

    direct_count = sum(atom.family in {"coordinate", "room_exact"} for atom in atoms)
    directness = sum(atom.directness for atom in atoms)
    average_complexity = sum(atom.complexity for atom in atoms) / max(1, len(atoms))
    double_count = sum(len(card) == 2 for card in cards.values())
    if double_count > limits["max_doubles"]:
        reasons.append("too_many_double_cards")
    if profile == "easy":
        if direct_count < 2:
            reasons.append("easy_needs_two_anchors")
        if average_complexity > 1.35:
            reasons.append("easy_too_complex")
    elif profile == "medium":
        if direct_count > 2:
            reasons.append("medium_too_direct")
    elif profile == "hard":
        if direct_count > 1 or directness > 4.5 or average_complexity < 1.2:
            reasons.append("hard_profile_mismatch")
    elif profile == "expert":
        if direct_count != 0 or directness > 2.8 or average_complexity < 1.3:
            reasons.append("expert_profile_mismatch")
    return reasons


def _intersection(cards: dict[str, tuple[AtomicClue, ...]], masks: dict[str, int], all_bits: int) -> int:
    current = all_bits
    for atoms in cards.values():
        for atom in atoms:
            current &= masks[atom.key]
    return current


def necessity_metrics(
    cards: dict[str, tuple[AtomicClue, ...]], masks: dict[str, int], all_bits: int, target_bit: int,
) -> tuple[bool, bool, dict[str, int], dict[str, int]]:
    card_counts: dict[str, int] = {}
    statement_counts: dict[str, int] = {}
    cards_ok = True
    statements_ok = True
    for subject in cards:
        trial = {key: value for key, value in cards.items() if key != subject}
        result = _intersection(trial, masks, all_bits)
        count = result.bit_count()
        card_counts[subject] = count
        if count <= 1 or not (result & target_bit):
            cards_ok = False
    for subject, atoms in cards.items():
        for index, atom in enumerate(atoms):
            trial = {key: tuple(value) for key, value in cards.items()}
            trial[subject] = tuple(value for pos, value in enumerate(atoms) if pos != index)
            result = _intersection(trial, masks, all_bits)
            count = result.bit_count()
            statement_counts[atom.key] = count
            if count <= 1 or not (result & target_bit):
                statements_ok = False
    return cards_ok, statements_ok, card_counts, statement_counts


def _option_cost(option: CardOption, family_counts: Counter[str], profile: str, before: int, after: int) -> float:
    atoms = option.atoms
    gain = math.log2(before / after)
    repeated = sum(family_counts[atom.family] for atom in atoms)
    directness = sum(atom.directness for atom in atoms)
    complexity = sum(atom.complexity for atom in atoms) / len(atoms)
    cost = len(atoms) * 20.0 + repeated * 4.0 + directness * 4.5
    # A global selector wants useful but not single-clue knockout information.
    cost += max(0.0, gain - 5.0) * 7.0
    cost += max(0.0, 0.35 - gain) * 8.0
    if len(atoms) == 2:
        cost += 8.0
        if atoms[0].family == atoms[1].family:
            cost += 7.0
    if profile == "easy":
        cost += complexity * 2.0
        if all(atom.family not in {"coordinate", "room_exact"} for atom in atoms):
            cost += 4.0
    elif profile in {"hard", "expert"}:
        cost -= complexity * 2.2
        cost += directness * (2.0 if profile == "hard" else 3.5)
    return cost


def _complete_score(
    cards: dict[str, tuple[AtomicClue, ...]], card_counts: dict[str, int], gains: tuple[float, ...], profile: str,
) -> float:
    atoms = [atom for values in cards.values() for atom in values]
    families = [atom.family for atom in atoms]
    total = len(atoms) * 100.0
    total += sum(len(values) == 2 for values in cards.values()) * 22.0
    total += (len(families) - len(set(families))) * 7.0
    total += sum(atom.directness for atom in atoms) * 12.0
    if gains:
        total += (max(gains) - min(gains)) * 5.0
    necessity_strength = [math.log2(max(2, value)) for value in card_counts.values()]
    if necessity_strength:
        total += (max(necessity_strength) - min(necessity_strength)) * 3.0
    # Reward richer hard/expert cases, but keep statement count dominant.
    if profile in {"hard", "expert"}:
        total -= sum(atom.complexity for atom in atoms) * 2.0
    return total


def _build_options(
    subject: str,
    pool: list[AtomicClue],
    masks: dict[str, int],
    all_bits: int,
    target_bit: int,
    profile: str,
) -> list[CardOption]:
    singles: list[CardOption] = []
    for atom in pool:
        mask = masks[atom.key]
        count = mask.bit_count()
        if count in {0, all_bits.bit_count()} or not (mask & target_bit):
            continue
        gain = math.log2(all_bits.bit_count() / count)
        singles.append(CardOption(subject, (atom,), mask, gain))
    singles.sort(key=lambda option: (
        option.atoms[0].directness,
        -int(option.atoms[0].family in RICH_FAMILIES),
        abs(option.standalone_gain - 2.5),
        option.atoms[0].complexity,
    ))
    singles = singles[:22]
    if profile == "easy":
        return singles

    pair_candidates: list[CardOption] = []
    basis = singles[:16]
    for i, left in enumerate(basis):
        for right in basis[i + 1:]:
            if left.atoms[0].key == right.atoms[0].key:
                continue
            combined = left.mask & right.mask
            count = combined.bit_count()
            if count == 0 or not (combined & target_bit):
                continue
            if combined == left.mask or combined == right.mask:
                continue  # one half is redundant even before considering other cards.
            gain = math.log2(all_bits.bit_count() / count)
            atoms = (left.atoms[0], right.atoms[0])
            pair_candidates.append(CardOption(subject, atoms, combined, gain))
    pair_candidates.sort(key=lambda option: (
        option.atoms[0].family == option.atoms[1].family,
        sum(atom.directness for atom in option.atoms),
        abs(option.standalone_gain - 3.3),
        -sum(atom.complexity for atom in option.atoms),
    ))
    return singles + pair_candidates[:24]


def _exact_single_card_search(
    pools: dict[str, list[AtomicClue]],
    masks: dict[str, int],
    all_bits: int,
    target_bit: int,
    rng: random.Random,
    profile: str,
    report: SelectionReport,
    order_attempts: int = 18,
    node_budget: int = 12000,
) -> dict[str, tuple[AtomicClue, ...]] | None:
    subjects = list(pools)
    orders: list[list[str]] = [sorted(subjects, key=lambda subject: len(pools[subject]))]
    max_orders = min(order_attempts, math.factorial(len(subjects)))
    shuffle_guard = 0
    while len(orders) < max_orders and shuffle_guard < max_orders * 20:
        shuffle_guard += 1
        order = subjects[:]
        rng.shuffle(order)
        if order not in orders:
            orders.append(order)
    limits = _profile_limits(profile)
    for order in orders:
        report.subject_orders_tried += 1
        nodes = 0

        def dfs(depth: int, current: int, cards: dict[str, tuple[AtomicClue, ...]], counts: Counter[str]):
            nonlocal nodes
            nodes += 1
            report.states_expanded += 1
            if nodes > node_budget:
                report.rejected["single_dfs_node_budget"] += 1
                return None
            if depth == len(order):
                report.complete_sets_checked += 1
                if current.bit_count() != 1 or not (current & target_bit):
                    report.rejected["not_unique"] += 1
                    return None
                reasons = quality_reasons(cards, profile)
                if reasons:
                    report.rejected.update(reasons)
                    return None
                cards_ok, statements_ok, _, _ = necessity_metrics(cards, masks, all_bits, target_bit)
                if not cards_ok:
                    report.rejected["redundant_card"] += 1
                    return None
                if not statements_ok:
                    report.rejected["redundant_statement"] += 1
                    return None
                return cards

            subject = order[depth]
            before = current.bit_count()
            remaining = len(order) - depth - 1
            scored = []
            for atom in pools[subject]:
                combined = current & masks[atom.key]
                after = combined.bit_count()
                if after == 0 or not (combined & target_bit):
                    continue
                if after == before:
                    continue
                if remaining > 0 and after == 1:
                    continue
                next_coordinate = counts["coordinate"] + int(atom.family == "coordinate")
                next_relative = counts["relative_order"] + counts["relative_distance"] + int(atom.family in {"relative_order", "relative_distance"})
                if next_coordinate > limits["max_coordinates"] or next_relative > limits["max_relatives"]:
                    continue
                gain = math.log2(before / after)
                novelty = 1.35 if counts[atom.family] == 0 else 0.78
                score = gain * novelty / max(0.55, atom.complexity * (1 + atom.directness))
                if profile == "easy" and atom.family in {"coordinate", "room_exact"}:
                    score *= 1.6
                if profile in {"hard", "expert"}:
                    score *= atom.complexity ** 1.2 / (1 + atom.directness * 2.0)
                scored.append((score * rng.uniform(0.94, 1.06), atom, combined))
            scored.sort(key=lambda item: item[0], reverse=True)
            for _, atom, combined in scored[:26]:
                next_cards = dict(cards); next_cards[subject] = (atom,)
                next_counts = Counter(counts); next_counts[atom.family] += 1
                found = dfs(depth + 1, combined, next_cards, next_counts)
                if found is not None:
                    return found
            return None

        found = dfs(0, all_bits, {}, Counter())
        if found is not None:
            return found
    return None


def global_select_cards(
    pools: dict[str, list[AtomicClue]],
    masks: dict[str, int],
    target_index: int,
    size: int,
    rng: random.Random,
    profile: str = "any",
    beam_width: int = 100,
    order_attempts: int = 4,
) -> tuple[dict[str, list[AtomicClue]] | None, dict[str, Any]]:
    """Search complete card sets rather than greedily appending atomic clues.

    A state always represents whole cards for the subjects already assigned. Single and
    double cards compete in the same global beam, so a locally attractive clue is rejected
    when it produces a worse complete set.
    """

    all_bits = (1 << size) - 1
    target_bit = 1 << target_index
    report = SelectionReport(beam_width=beam_width)
    singles = _exact_single_card_search(
        pools, masks, all_bits, target_bit, rng, profile, report
    )
    if singles is not None:
        report.method = "global_exact_single_card_dfs"
        atoms = [atom for values in singles.values() for atom in values]
        report.selected_families = dict(Counter(atom.family for atom in atoms))
        report.selected_types = dict(Counter(atom.type for atom in atoms))
        _, _, card_counts, _ = necessity_metrics(singles, masks, all_bits, target_bit)
        report.accepted_score = round(_complete_score(singles, card_counts, (), profile), 3)
        return {subject: list(values) for subject, values in singles.items()}, report.to_json()

    report.method = "global_beam_search_with_double_cards"
    options = {
        subject: _build_options(subject, pool, masks, all_bits, target_bit, profile)
        for subject, pool in pools.items()
    }
    report.options_per_subject = {subject: len(value) for subject, value in options.items()}
    if any(not value for value in options.values()):
        report.rejected["subject_without_card_options"] += 1
        return None, report.to_json()

    subjects = list(options)
    orders: list[list[str]] = [sorted(subjects, key=lambda subject: len(options[subject]))]
    max_orders = min(order_attempts, math.factorial(len(subjects)))
    shuffle_guard = 0
    while len(orders) < max_orders and shuffle_guard < max_orders * 20:
        shuffle_guard += 1
        order = subjects[:]
        rng.shuffle(order)
        if order not in orders:
            orders.append(order)
    best_cards: dict[str, tuple[AtomicClue, ...]] | None = None
    best_score = math.inf

    for order in orders:
        report.subject_orders_tried += 1
        beam = [BeamState(all_bits, {}, Counter(), 0.0, 0, ())]
        for depth, subject in enumerate(order):
            remaining = len(order) - depth - 1
            expanded: list[BeamState] = []
            for state in beam:
                before = state.current.bit_count()
                for option in options[subject]:
                    report.states_expanded += 1
                    after_bits = state.current & option.mask
                    after = after_bits.bit_count()
                    if after == 0 or not (after_bits & target_bit):
                        report.rejected["contradiction"] += 1
                        continue
                    if after == before:
                        report.rejected["card_no_information"] += 1
                        continue
                    if remaining > 0 and after == 1:
                        report.rejected["solved_before_all_cards"] += 1
                        continue
                    next_double = state.double_count + int(len(option.atoms) == 2)
                    if next_double > _profile_limits(profile)["max_doubles"]:
                        report.rejected["too_many_double_cards_partial"] += 1
                        continue
                    next_counts = Counter(state.family_counts)
                    next_counts.update(atom.family for atom in option.atoms)
                    if next_counts["coordinate"] > _profile_limits(profile)["max_coordinates"]:
                        report.rejected["too_many_coordinates_partial"] += 1
                        continue
                    relative_count = next_counts["relative_order"] + next_counts["relative_distance"]
                    if relative_count > _profile_limits(profile)["max_relatives"]:
                        report.rejected["too_many_relatives_partial"] += 1
                        continue
                    gain = math.log2(before / after)
                    next_cards = dict(state.cards)
                    next_cards[subject] = option.atoms
                    expanded.append(BeamState(
                        after_bits,
                        next_cards,
                        next_counts,
                        state.score + _option_cost(option, state.family_counts, profile, before, after),
                        next_double,
                        state.gains + (gain,),
                    ))
            if not expanded:
                beam = []
                break
            # Deduplicate logically identical partial states, preserving the best editorial form.
            dedup: dict[tuple[int, tuple[tuple[str, int], ...], int], BeamState] = {}
            for state in expanded:
                signature = (state.current, tuple(sorted(state.family_counts.items())), state.double_count)
                old = dedup.get(signature)
                if old is None or state.score < old.score:
                    dedup[signature] = state
            beam = sorted(dedup.values(), key=lambda state: (state.score, state.current.bit_count()))[:beam_width]

        for state in beam:
            report.complete_sets_checked += 1
            if state.current.bit_count() != 1 or not (state.current & target_bit):
                report.rejected["not_unique"] += 1
                continue
            reasons = quality_reasons(state.cards, profile)
            if reasons:
                report.rejected.update(reasons)
                continue
            cards_ok, statements_ok, card_counts, _ = necessity_metrics(state.cards, masks, all_bits, target_bit)
            if not cards_ok:
                report.rejected["redundant_card"] += 1
                continue
            if not statements_ok:
                report.rejected["redundant_statement"] += 1
                continue
            score = _complete_score(state.cards, card_counts, state.gains, profile)
            if score < best_score:
                best_score = score
                best_cards = state.cards

    if best_cards is None:
        return None, report.to_json()
    report.accepted_score = round(best_score, 3)
    atoms = [atom for values in best_cards.values() for atom in values]
    report.selected_families = dict(Counter(atom.family for atom in atoms))
    report.selected_types = dict(Counter(atom.type for atom in atoms))
    return {subject: list(atoms) for subject, atoms in best_cards.items()}, report.to_json()
