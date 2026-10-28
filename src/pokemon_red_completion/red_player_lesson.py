"""Prospective native story/development/recovery lesson evidence.

Private objective/specimen identities verify executed outcomes; they never enter
the policy projection. This supplements, rather than rewrites, registered V1
observations. It is not an intervention API or a claim of independent data supply.
"""

import math
from collections.abc import Mapping
from dataclasses import replace

from .goal_manager import GoalKind
from .goal_manager_state import party_safety_satisfaction
from .party import MoveObservation, PartyMemberObservation, PartyObservation, StatusCondition
from .red_party import PokemonRedPartyReader
from .red_player_economy import semantic_facts

SNAPSHOT_SCHEMA = "pokemon.red.player-lesson-snapshot.v1"
LESSON_KINDS = frozenset({
    GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM,
})


def capture_player_lesson_snapshot(runtime):
    """Read a coherent boundary without input, rejecting ambiguous specimen keys.

    The existing Red party adapter supplies XP and session-local OT/DV keys.
    Closed lessons forbid membership changes; these keys are not global identity.
    """
    frame = runtime.emulator.frame_count
    observation = runtime.adapter.observe()
    reader = PokemonRedPartyReader(runtime.emulator)
    party, refs = reader.read(), reader.preparation_specimen_refs()
    if type(observation.raw.battle_state) is not int:
        raise ValueError("player lesson battle state is unavailable")
    if tuple(replace(m, experience=None) for m in party.members) != observation.party.members:
        raise ValueError("player lesson party is not the observed boundary")
    document = {
        "schema": SNAPSHOT_SCHEMA,
        "completed_objectives": sorted(runtime.adapter.graph.completed_ids(observation.game_state)),
        "objective_catalog": sorted(o.id for o in runtime.adapter.graph.objectives),
        "in_battle": bool(observation.raw.battle_state),
        "party": [
            dict(
                specimen_ref=ref, species_id=m.species_id, level=m.level,
                experience=m.experience, hp=m.hp, max_hp=m.max_hp, status=m.status.value,
                moves=[[move.move_id, move.current_pp] for move in m.moves],
            )
            for ref, m in zip(refs, party.members, strict=True)
        ],
    }
    if runtime.emulator.frame_count != frame:
        raise ValueError("player lesson observation advanced the game")
    validate_snapshot(document, observation.public_dict())
    return observation, document


def _names(value):
    if (not isinstance(value, list)
            or any(not isinstance(x, str) or not x or not x.isascii() for x in value)
            or value != sorted(set(value))):
        raise ValueError("player lesson objective set differs")
    return set(value)


def validate_snapshot(document, observation):
    """Rebuild typed party facts and bind them to the registered observation."""
    if (not isinstance(document, Mapping)
            or set(document) != {"schema", "completed_objectives", "objective_catalog",
                                 "in_battle", "party"}
            or document["schema"] != SNAPSHOT_SCHEMA
            or type(document["in_battle"]) is not bool
            or not isinstance(document["party"], list)
            or not 1 <= len(document["party"]) <= 6):
        raise ValueError("player lesson snapshot scope differs")
    completed = _names(document["completed_objectives"])
    catalog = _names(document["objective_catalog"])
    facts = semantic_facts(observation)
    story = facts.get("story")
    if (not completed <= catalog or not isinstance(story, Mapping)
            or type(story.get("completed")) is not int
            or type(story.get("target")) is not int
            or story != {"completed": len(completed), "target": len(catalog)}
            or type(facts.get("party_size")) is not int
            or facts["party_size"] != len(document["party"])
            or type(facts.get("input_ready")) is not bool):
        raise ValueError("player lesson snapshot differs from semantic observation")
    members = {}
    for slot, entry in enumerate(document["party"], 1):
        if (not isinstance(entry, Mapping)
                or set(entry) != {"specimen_ref", "species_id", "level", "experience",
                                  "hp", "max_hp", "status", "moves"}
                or not isinstance(entry["specimen_ref"], str)
                or not entry["specimen_ref"].startswith("red-preparation:")
                or len(entry["specimen_ref"]) != len("red-preparation:") + 64
                or any(c not in "0123456789abcdef" for c in entry["specimen_ref"].split(":")[1])
                or entry["specimen_ref"] in members
                or type(entry["experience"]) is not int
                or not 0 <= entry["experience"] <= 0xFFFFFF
                or not isinstance(entry["moves"], list)
                or len(entry["moves"]) != 4):
            raise ValueError("player lesson specimen evidence differs")
        moves = []
        for pair in entry["moves"]:
            if (not isinstance(pair, list) or len(pair) != 2
                    or type(pair[0]) is not int or not 0 <= pair[0] <= 165
                    or type(pair[1]) is not int or not 0 <= pair[1] <= 63
                    or (pair[0] == 0 and pair[1] != 0)):
                raise ValueError("player lesson move evidence differs")
            moves.append(MoveObservation(pair[0], pair[1]))
        member = PartyMemberObservation(
            slot=slot, species_id=entry["species_id"], level=entry["level"],
            hp=entry["hp"], max_hp=entry["max_hp"], status=StatusCondition(entry["status"]),
            experience=entry["experience"], moves=tuple(moves),
        )
        members[entry["specimen_ref"]] = member
    pressures = facts.get("situation", {}).get("need_pressures", {})
    expected = 1.0 - party_safety_satisfaction(PartyObservation(tuple(members.values())))
    if (type(pressures.get("safety")) not in (int, float)
            or not math.isclose(pressures["safety"], expected, rel_tol=0, abs_tol=1e-12)):
        raise ValueError("player lesson party safety differs from semantic observation")
    return members


def validate_player_lesson(lesson, before, kind):
    if (kind not in LESSON_KINDS or not isinstance(lesson, Mapping)
            or set(lesson) != {"before", "target"}):
        raise ValueError("player lesson declaration scope differs")
    members = validate_snapshot(lesson["before"], before)
    target = lesson["target"]
    if not isinstance(target, Mapping):
        raise ValueError("player lesson target differs")
    if kind is GoalKind.ADVANCE_STORY:
        if (set(target) != {"objective"}
                or not isinstance(target["objective"], str)
                or target["objective"] not in lesson["before"]["objective_catalog"]
                or target["objective"] in lesson["before"]["completed_objectives"]):
            raise ValueError("player lesson story target is absent or already complete")
    elif kind is GoalKind.DEVELOP_TEAM:
        if (set(target) != {"specimen_ref", "level"}
                or not isinstance(target["specimen_ref"], str)
                or target["specimen_ref"] not in members
                or type(target["level"]) is not int
                or not members[target["specimen_ref"]].level < target["level"] <= 100):
            raise ValueError("player lesson development target differs")
    elif target != {"restoration": "improve_without_regression"}:
        raise ValueError("player lesson restoration target differs")
    return members



def capture_preparation_pp_evidence(raw, lesson, source_state_sha256):
    """Retain exact packed PP through the existing semantic adapter boundary."""
    from .player_challenge_consequence import require_digest
    require_digest(source_state_sha256)
    party = lesson["party"]
    if (type(raw.party_count) is not int or raw.party_count != len(party)
            or raw.party_moves is None or raw.party_pp is None
            or len(raw.party_moves) != len(party) or len(raw.party_pp) != len(party)):
        raise ValueError("preparation PP requires complete same-boundary party evidence")
    document = dict(schema="pokemon.red.preparation-pp-evidence.v1",
        source_state_sha256=source_state_sha256,
        party=[dict(specimen_ref=m["specimen_ref"], packed_pp=list(packed))
               for m, moves, packed in zip(party, raw.party_moves, raw.party_pp, strict=True)])
    if any(list(moves) != [move[0] for move in member["moves"]]
           for member, moves in zip(party, raw.party_moves, strict=True)):
        raise ValueError("preparation PP move identity differs from the source lesson")
    _preparation_pp_ratios(document, lesson, source_state_sha256)
    return document


def _preparation_pp_ratios(document, lesson, source_state_sha256):
    from .player_challenge_consequence import require_digest
    from .red_party_pp import decode_red_party_pp
    require_digest(source_state_sha256)
    if (not isinstance(document, Mapping)
            or set(document) != {"schema", "source_state_sha256", "party"}
            or document["schema"] != "pokemon.red.preparation-pp-evidence.v1"
            or document["source_state_sha256"] != source_state_sha256
            or not isinstance(document["party"], list)
            or len(document["party"]) != len(lesson["party"])):
        raise ValueError("preparation PP evidence is not the exact source")
    ratios = {}
    for evidence, member in zip(document["party"], lesson["party"], strict=True):
        if (not isinstance(evidence, Mapping)
                or set(evidence) != {"specimen_ref", "packed_pp"}
                or evidence["specimen_ref"] != member["specimen_ref"]
                or type(evidence["packed_pp"]) is not list):
            raise ValueError("preparation PP evidence differs from ordered source members")
        ids = tuple(move[0] for move in member["moves"])
        decoded = decode_red_party_pp(ids, tuple(evidence["packed_pp"])).moves
        if [move.current_pp for move in decoded] != [move[1] for move in member["moves"]]:
            raise ValueError("preparation PP quantity differs from source lesson")
        known = tuple(move for move in decoded if move.move_id != 0)
        ratios[member["specimen_ref"]] = (
            sum(move.current_pp for move in known) / max(1, sum(move.maximum_pp for move in known))
            if known else None)
    return ratios

def validate_preparation_lesson(plan, kind, *, pp_evidence=None, source_state_sha256=None):
    """Bind portable preparation facts to the selected atomic training intent.

    Remaining XP/evolution are prospective cartridge quotes supplied by the
    trusted observation callback, not independently inferred from a level alone.
    This contract admits no downstream battle result or new reward semantics.
    """
    from .player_option_preparation import OptionPreparation

    members = validate_player_lesson(plan["player_lesson"], plan["before"], kind)
    document = plan["preparation"]
    if kind is not GoalKind.DEVELOP_TEAM:
        if document is not None:
            raise ValueError("nondevelopment lesson cannot claim preparation facts")
        return None
    facts = OptionPreparation.from_public(document)
    target = plan["player_lesson"]["target"]
    member = members[target["specimen_ref"]]
    expected_pp = None
    if pp_evidence is not None:
        expected_pp = _preparation_pp_ratios(
            pp_evidence, plan["player_lesson"]["before"], source_state_sha256)[target["specimen_ref"]]
    if (facts.current_level != member.level or facts.target_level != target["level"]
            or not math.isclose(facts.hp_fraction, member.hp_ratio, rel_tol=0, abs_tol=1e-12)
            # Legacy V1 snapshots still never authorize an invented PP ratio.
            or (facts.pp_fraction is None) != (expected_pp is None)
            or (expected_pp is not None and not math.isclose(
                facts.pp_fraction, expected_pp, rel_tol=0, abs_tol=1e-12))):
        raise ValueError("preparation facts differ from selected member/target snapshot")
    return facts


def verify_player_lesson(lesson, terminal, before, after, kind, succeeded, *, level_evolutions=()):
    """Reject unsupported success claims; preserve readable partial/failed attempts.

    Story requires the exact new objective. Development requires the declared
    retained specimen's level and actual XP gain, not a changed party average.
    Recovery requires observed HP/PP/status improvement without trading away
    another resource or claiming an already healthy party was restored.
    """
    from .red_trainer_evolution import level_evolution_matches

    old = validate_player_lesson(lesson, before, kind)
    new = validate_snapshot(terminal, after)
    opening = lesson["before"]
    if (opening["objective_catalog"] != terminal["objective_catalog"]
            or not set(opening["completed_objectives"]) <= set(terminal["completed_objectives"])
            or old.keys() != new.keys()
            or any((old[k].species_id != new[k].species_id
                    and not (kind is GoalKind.DEVELOP_TEAM
                             and level_evolution_matches(old[k], new[k], level_evolutions)))
                   or old[k].level > new[k].level
                   or old[k].experience > new[k].experience for k in old)):
        raise ValueError("player lesson lost or substituted its declared evidence")
    if type(succeeded) is not bool:
        raise ValueError("player lesson success must be boolean")
    if not succeeded:
        return
    if terminal["in_battle"] or not semantic_facts(after)["input_ready"]:
        raise ValueError("player lesson success lacks a settled field boundary")
    target = lesson["target"]
    if kind is GoalKind.ADVANCE_STORY:
        verified = target["objective"] in terminal["completed_objectives"]
    elif kind is GoalKind.DEVELOP_TEAM:
        key = target["specimen_ref"]
        verified = (new[key].level >= target["level"]
                    and new[key].experience > old[key].experience)
    else:
        verified = _restored(old, new)
    if not verified:
        raise ValueError("player lesson success lacks selected-goal progress")


def _restored(old, new):
    improved = False
    for key, a in old.items():
        b = new[key]
        if (a.level != b.level or a.experience != b.experience or a.max_hp != b.max_hp
                or tuple(m.move_id for m in a.moves) != tuple(m.move_id for m in b.moves)
                or b.hp < a.hp
                or any(n.current_pp < m.current_pp for m, n in zip(a.moves, b.moves, strict=True))
                or b.status not in {a.status, StatusCondition.HEALTHY}):
            return False
        improved |= (b.hp > a.hp or b.total_pp > a.total_pp or b.status != a.status)
    return improved
