"""Pinned, opt-in Red evolution evidence; no inputs or legacy record migration."""

from collections import Counter
from hashlib import sha256

from .generation_one import GENERATION_ONE_LEVEL_EVOLUTIONS
from .goal_manager import GoalKind
from .goal_manager_composition_runtime import GoalManagerCompositionError
from .red_collection import red_internal_species_id, red_internal_species_number, red_species_ref
from .red_player_lesson import validate_snapshot
from .red_safari_training_setup import RED_ROM_SHA256
from .red_trainer_evolution import level_evolution_edges, level_evolution_matches
from .registered_checkpoint import RegisteredCollectionCheckpoint


def _known_edges():
    return frozenset(
        (red_internal_species_id(a), red_internal_species_id(b), level)
        for a, b, level in GENERATION_ONE_LEVEL_EVOLUTIONS
    )


def evolution_lesson_contract(rom):
    """Bind the supported cartridge's actual table, not caller-supplied edges."""
    if not isinstance(rom, bytes) or sha256(rom).hexdigest() != RED_ROM_SHA256:
        raise ValueError("evolution lesson requires the pinned Red cartridge")
    edges = level_evolution_edges(rom)
    if edges != _known_edges():
        raise ValueError("cartridge level-evolution table differs from supported Red")
    return dict(
        schema="pokemon.red.evolution-lesson.v1",
        cartridge_sha256=RED_ROM_SHA256,
        level_edges=[list(edge) for edge in sorted(edges)],
    )


def validate_evolution_lesson_contract(document):
    expected = dict(
        schema="pokemon.red.evolution-lesson.v1",
        cartridge_sha256=RED_ROM_SHA256,
        level_edges=[list(edge) for edge in sorted(_known_edges())],
    )
    # Canonical identity also rejects bools masquerading as integers.
    from .provenance import canonical_sha256

    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError("evolution lesson contract differs")
    return _known_edges()


def verify_evolution_lesson_boundary(opening, terminal, before, after, kind, contract):
    """Same complete roster; exact legal transformations and registration deltas.

    Species reserves remain literal (e.g. a quest/trade precursor). The fixture
    must declare genuine reserves initially, not every species merely in the party.
    Stable private specimen keys protect the whole roster independently of those
    species reserves. No capture, trade, release or box mutation is permitted here.
    """
    edges = validate_evolution_lesson_contract(contract)
    old, new = validate_snapshot(opening, before), validate_snapshot(terminal, after)
    if (
        old.keys() != new.keys()
        or opening["objective_catalog"] != terminal["objective_catalog"]
        or not set(opening["completed_objectives"]) <= set(terminal["completed_objectives"])
        or any(new[k].level < old[k].level or new[k].experience < old[k].experience for k in old)
    ):
        raise ValueError("evolution lesson lost identity, XP or objectives")
    try:
        first = RegisteredCollectionCheckpoint.from_public(before["registration"])
        last = RegisteredCollectionCheckpoint.from_public(after["registration"])
    except GoalManagerCompositionError as error:
        raise ValueError("evolution lesson registered inventory is invalid") from error
    for name in (
        "binding_sha256",
        "completion_scope",
        "completion_contract_sha256",
        "target_species",
        "protected_counts",
        "allowed_evolutions",
    ):
        if getattr(first, name) != getattr(last, name):
            raise ValueError("evolution lesson changed registration binding or reserves")
    counts = Counter(dict(first.specimen_counts))
    destinations = set()
    for key, a in old.items():
        b = new[key]
        hms = {m.move_id for m in a.moves} & {15, 19, 57, 70, 148}
        if not hms <= {m.move_id for m in b.moves}:
            raise ValueError("evolution lesson lost a protected HM move")
        if a.species_id == b.species_id:
            continue
        if kind not in {
            GoalKind.DEVELOP_TEAM,
            GoalKind.ADVANCE_STORY,
        } or not level_evolution_matches(a, b, edges):
            raise ValueError("evolution lesson contains an unearned species change")
        source = red_species_ref(red_internal_species_number(a.species_id))
        target = red_species_ref(red_internal_species_number(b.species_id))
        counts[source] -= 1
        counts[target] += 1
        destinations.add(target)
    if (
        any(n < 0 for n in counts.values())
        or +counts != Counter(dict(last.specimen_counts))
        or set(last.local_species) != set(first.local_species) | destinations
        or set(last.global_species) != set(first.global_species) | destinations
    ):
        raise ValueError("evolution lesson physical stock or registration delta differs")
    # A party snapshot must be consistent with actual physical stock even when
    # there was no species change. Box specimens cannot stand in for lost party keys.
    for members, checkpoint in ((old, first), (new, last)):
        party = Counter(
            red_species_ref(red_internal_species_number(m.species_id)) for m in members.values()
        )
        if party - Counter(dict(checkpoint.specimen_counts)):
            raise ValueError("evolution lesson party lacks physical stock")
    return edges
