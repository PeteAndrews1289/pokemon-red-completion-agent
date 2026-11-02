"""Compile admitted TRAIN returns for the current composed battle actor.

The legacy all-head fitter predates the frozen damage/status shortlist. This
adapter compiles only switch/control rows, keeping the same concrete child
proposals as live play. It neither fits weights nor authenticates native logs;
callers must first admit each measured target through the existing event audit.
"""

from statistics import fmean

from .battle_scenario_capture import OBSERVATION_SCHEMA_V2
from .red_battle_catalog import PokemonRedBattleCatalog
from .red_status_battle_features import project_for_head, status_choice_slots
from .red_trainer_practice_fit import (
    TrainerPracticeFitError,
    _append_examples,
    _legacy_batch,
    _observed_returns,
    _soft_return_target,
    _tied_values,
)
from .red_trainer_practice_head import TrainerHeadExample
from .red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA, proposed_control


def _inventory(refs):
    if not isinstance(refs, list) or len(refs) < 2 or any(type(r) is not str for r in refs):
        raise TrainerPracticeFitError("control choice inventory differs")
    if len(set(refs)) != len(refs):
        raise TrainerPracticeFitError("control choice inventory repeats")
    moves, switches, decline = [], [], False
    for ref in refs:
        if ref == "pokemon.core:battle:decline-switch":
            decline = True
            continue
        parts = ref.rsplit(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise TrainerPracticeFitError("unsupported control action reference")
        slot = int(parts[1])
        if parts[0] == "pokemon.core:battle:move" and 1 <= slot <= 4:
            moves.append(slot)
        elif parts[0] == "pokemon.core:battle:switch" and 1 <= slot <= 6:
            switches.append(slot)
        else:
            raise TrainerPracticeFitError("unsupported control action reference")
        if parts[1] != str(slot):
            raise TrainerPracticeFitError("noncanonical control action reference")
    if not switches or (not moves and not decline) or (moves and decline):
        raise TrainerPracticeFitError("control needs attack-or-decline versus switch")
    return tuple(moves), tuple(switches), decline


def build_switch_control_examples(targets, model, *, catalog=None):
    """Keep measured return units; never substitute a hand-chosen action label.

    Only declared TRAIN roots of the frozen model may supply rows. This is a
    compiler, not a source-provenance or episode-completeness admission gate.
    The supplied target inventories must already be authenticated legal choices.
    """
    if model.control.schema_id != PROPOSED_CONTROL_SCHEMA:
        raise TrainerPracticeFitError("composed proposed-action control is required")
    if model.control_target_mode != "fitted_components":
        raise TrainerPracticeFitError("fitted-component return semantics are required")
    records = tuple(targets)
    if not records:
        raise TrainerPracticeFitError("empty switch/control TRAIN corpus")
    catalog = catalog or PokemonRedBattleCatalog()
    rows = {"switch": [], "control": []}
    seen = set()
    for target in records:
        if (
            not isinstance(target, dict)
            or target.get("schema") != "pokemon.red.trainer-practice-three-head-targets.v1"
            or target.get("partition") != "train"
            or type(target.get("scenario_count")) is not int
            or target["scenario_count"] != 1
            or target.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or target.get("root_lineage_id") not in model.train_root_ids
            or type(target.get("capture_id")) is not str
            or not target["capture_id"]
            or target["capture_id"] in seen
        ):
            raise TrainerPracticeFitError("switch/control target lacks unique TRAIN identity")
        seen.add(target["capture_id"])
        heads = target.get("heads")
        if not isinstance(heads, dict):
            raise TrainerPracticeFitError("switch/control target heads differ")
        if "switch" in heads:
            _append_examples(rows, {**target, "heads": {"switch": heads["switch"]}}, catalog)
        head = heads.get("control")
        if head is None:
            continue
        if not isinstance(head, dict) or not isinstance(target.get("observation"), dict):
            raise TrainerPracticeFitError("control target observation or head differs")
        refs = head.get("choice_refs")
        moves, switches, decline = _inventory(refs)
        returns = head.get("returns")
        if not isinstance(returns, list) or len(returns) != len(refs):
            raise TrainerPracticeFitError("control return inventory differs")
        observed = _observed_returns("control", refs, returns, head.get("timing_returns"))
        observation = target["observation"]
        base = _legacy_batch(target.get("legacy_model_input"))
        if moves:
            if base is None:
                raise TrainerPracticeFitError("control move input is missing")
            legal = {
                slot + 1
                for slot, allowed in zip(base.slot_indices, base.legal_mask, strict=True)
                if allowed
            }
            if not set(moves) <= legal:
                raise TrainerPracticeFitError("control offered an illegal retained move")
            projected = project_for_head(observation, base, model.move)
            if any(slot not in projected.candidate_slots for slot in moves):
                raise TrainerPracticeFitError("control move inventory is not observed")
            if model.damage_reference is not None:
                moves = status_choice_slots(projected, moves, model.damage_reference)
        proposal = proposed_control(
            observation,
            catalog=catalog,
            move_head=model.move,
            switch_head=model.switch,
            move_batch=None if decline else base,
            move_slots=moves,
            switch_slots=switches,
        )
        chosen_refs = (
            "pokemon.core:battle:decline-switch"
            if decline
            else f"pokemon.core:battle:move:{proposal.move_slot}",
            f"pokemon.core:battle:switch:{proposal.switch_slot}",
        )
        means = tuple(fmean(row[refs.index(ref)] for row in observed) for ref in chosen_refs)
        rows["control"].append(
            TrainerHeadExample(
                proposal.candidate_vectors,
                _tied_values(means),
                _soft_return_target((means,)),
                means,
            )
        )
    if not any(rows.values()):
        raise TrainerPracticeFitError("corpus has no measured switch/control choices")
    return rows
