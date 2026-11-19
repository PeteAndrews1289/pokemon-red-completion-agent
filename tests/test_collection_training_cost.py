import json
from dataclasses import asdict, dataclass, replace
from types import SimpleNamespace

import pytest
from test_living_dex_option_value import _menu

from pokemon_red_completion.collection_training_cost import (
    CollectionTrainingCost, level_cost_context, measured_training_cost, menu_with_collection_costs,
    replay_collection_cost_step,
)
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_internal_species_id


TRANSITION = ("pokemon:national:077", "pokemon:national:078")
PHASES = ("menu_and_boundary_observation", "selection_and_receipt", "selection_diagnostics",
          "execution", "verification", "terminal_observation", "outcome_diagnostics")


@dataclass
class Options:
    bindings: tuple
    menu: object


def example():
    base = _menu()
    first, *others = base.candidates
    first = replace(first, features=replace(first.features, kind=LivingDexOptionKind.EVOLVE),
                    level_workload=OptionLevelWorkload(32, 40, 1000))
    menu = replace(base, candidates=(first, *others))
    bindings = tuple(SimpleNamespace(binding_ref=c.binding_ref, level_evolution_transition=TRANSITION if i == 0 else None,
                                     level_evolution_boxed_ref="boxed-1" if i == 0 else None,
                                     level_evolution_initial_xp=5000 if i == 0 else None)
                     for i, c in enumerate(menu.candidates))
    return Options(bindings, menu), dict(diagnostics=dict(map_id=88), player_lesson=dict(party=[
        dict(specimen_ref="escort", species_id=red_internal_species_id(22))]))


def closed(facts, xp, frames):
    return dict(before={**facts, "owned_species":[]}, after={"owned_species":[]}, choice={"selected_candidate_index":0},
                before_state_sha256="1"*64, terminal_state_sha256="2"*64, selected_kind="evolve_species", safe_terminal=True,
                ordinary_setback=True, verification="failed", observed_cost={"frames":frames},
                phase_seconds={k:1 for k in PHASES}, evidence=dict(
                    retained_active_roster_restored=True, evolution_partial=True, source_species_ref=TRANSITION[0],
                    target_species_ref=TRANSITION[1], trainee_initial_xp=5000, trainee_terminal_xp=5000+xp,
                    trainee_xp_gained=xp, escort_xp_gained=99999, healing_trips=3))


def test_measurement_restores_target_only_and_includes_failed_attempt_costs():
    options, facts = example()
    binding = options.bindings[0]
    history = GoalSearchMemory()
    empty = history.private_dict()
    assert "collection_training" not in empty
    no_history, quotes, contexts = menu_with_collection_costs(options, history, facts, 2000)
    assert no_history is options and not quotes
    key = contexts[binding.binding_ref]["key"]
    first = measured_training_cost(closed(facts, 0, 400), TRANSITION)
    history.record_collection_training_cost(key, first)
    zero, quotes, _ = menu_with_collection_costs(options, history, facts, 2000)
    assert zero.menu == options.menu and quotes[0]["estimated_seconds"] is None
    old = GoalSearchMemory.from_private_dict(json.loads(json.dumps(history.private_dict())))
    new = measured_training_cost(closed(facts, 100, 600), TRANSITION)
    history.record_collection_training_cost(key, new)
    history.require_extension(old)
    with pytest.raises(ValueError):
        old.require_extension(history)
    projected, (quote,), _ = menu_with_collection_costs(options, history, facts, 2000)
    assert quote["observed"] == asdict(CollectionTrainingCost(2, 1, 100, 1000, 14000000, 6))
    assert (quote["estimated_frames"], quote["estimated_seconds"], quote["quoted_effort"]) == (10000, 140, 10000/12000)
    assert projected.menu.candidates[1:] == options.menu.candidates[1:]
    assert projected.bindings == options.bindings
    assert level_cost_context(binding, options.menu.candidates[0], {**facts,"diagnostics":{"map_id":89}})["key"] != key
    binding.level_evolution_boxed_ref = "boxed-2"
    assert level_cost_context(binding, options.menu.candidates[0], facts)["key"] != key
    binding.level_evolution_boxed_ref = None
    assert level_cost_context(binding, options.menu.candidates[0], facts) is None


@pytest.mark.parametrize("change", ("unsafe","helper_only","wrong_species","no_custody","missing_frames","missing_phase","no_evolution"))
def test_uncertified_cost_or_helper_xp_cannot_be_counted(change):
    _, facts = example()
    row = closed(facts, 5, 30)
    if change == "unsafe": row["safe_terminal"] = False
    if change == "helper_only": row["evidence"]["trainee_terminal_xp"] = 5000
    if change == "wrong_species": row["evidence"]["target_species_ref"] = TRANSITION[0]
    if change == "no_custody": row["evidence"]["retained_active_roster_restored"] = False
    if change == "missing_frames": row["observed_cost"] = {}
    if change == "missing_phase": row["phase_seconds"].pop("verification")
    if change == "no_evolution": row["verification"] = "succeeded"
    assert measured_training_cost(row, TRANSITION) is None


def test_cost_receipts_independently_replay_and_detect_tampering(tmp_path):
    options, facts = example()
    memory = GoalSearchMemory()
    outcome = closed(facts, 100, 700)
    key = level_cost_context(options.bindings[0], options.menu.candidates[0], facts)["key"]
    memory.record_collection_training_cost(key, measured_training_cost(closed(facts, 25, 300), TRANSITION))
    frozen = memory.private_dict()
    projected, quotes, contexts = menu_with_collection_costs(options, memory, facts, 1000)
    intent = dict(menu=dict(schema="options", menu=projected.menu.policy_dict()), private_selection_authority=dict(
        live_bindings=[dict(binding_ref=b.binding_ref, policy=dict(kind="evolve_species" if i==0 else "acquire_species"))
                       for i,b in enumerate(options.bindings)]))
    prior = dict(state_sha256=outcome["before_state_sha256"], original_menu_sha256=options.menu.policy_sha256,
                 frame_horizon=1000, quotes=quotes, contexts=contexts)
    (tmp_path/"collection-cost-before.json").write_text(json.dumps(prior))
    after = dict(state_sha256=outcome["terminal_state_sha256"], context_sha256=key,
                 observed=asdict(measured_training_cost(outcome, TRANSITION)), outcome_sha256=canonical_sha256(outcome))
    (tmp_path/"collection-cost-after.json").write_text(json.dumps(after))
    replay_collection_cost_step(tmp_path, outcome, intent, memory, 1000)
    assert memory.collection_training_cost(key).target_xp == 125
    prior["quotes"][0]["observed"]["target_xp"] = 9999
    (tmp_path/"collection-cost-before.json").write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="quote"):
        replay_collection_cost_step(tmp_path, outcome, intent, GoalSearchMemory.from_private_dict(frozen), 1000)


def test_changed_trainee_and_mismatched_starting_xp_cannot_enter_private_history():
    options, facts = example()
    context = level_cost_context(options.bindings[0], options.menu.candidates[0], facts)
    outcome = closed(facts,0,400)
    outcome["evidence"]["zero_progress_trainee_ref"] = "another-individual"
    assert measured_training_cost(outcome, TRANSITION, context=context) is None
    del outcome["evidence"]["zero_progress_trainee_ref"]
    assert measured_training_cost(outcome, TRANSITION, context={**context, "initial_xp": 4999}) is None
