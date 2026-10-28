"""Pure prospective machine-parent contracts; no fits, scores, ROM or native inputs."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_machine_consequence_v10 import machine_documents
from test_red_post_battle_strategy import episode

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.player_challenge_consequence import consequence_contract
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_option_matchup import OptionMatchup
from pokemon_red_completion.provenance import canonical_sha256
import pokemon_red_completion.red_challenge_consequence as recording
from pokemon_red_completion.red_consequence_choice import condition_consequence_candidate


def owned_parent_documents(tmp_path, monkeypatch):
    plan, phases, menu = machine_documents(tmp_path, monkeypatch)
    machine = replace(menu.candidates[0], challenge=OptionChallenge(False, False, 0., 0., 0.))
    parent = replace(menu.candidates[1],
        features=replace(menu.candidates[1].features, kind=LivingDexOptionKind.UNLOCK_ACCESS),
        binding_ref='observed-combat-parent', preparation=None, level_workload=None,
        move_change=None, challenge=OptionChallenge.from_levels(
            combat_levels=(20,), opponent_levels=(39, 44)),
        matchup=OptionMatchup((0.,) * 27))
    menu = replace(menu, candidates=(machine, parent))
    spec = replace(recording.ChallengeConsequenceSpec.from_document(plan['spec']), feedback_version=2)
    plan.update(schema='pokemon.red.challenge-consequence-plan.v8', feature_version=15,
        consequence_schema=consequence_contract(2)[0], spec=spec.document(), menu=menu.policy_dict())
    phases[-1]['challenge_episode'] = episode()
    dose = SimpleNamespace(kind=GoalKind.DEVELOP_TEAM, binding_ref=machine.binding_ref,
        story_objective_ref=None, story_approach_only=False)
    binding = SimpleNamespace(kind=GoalKind.ADVANCE_STORY, binding_ref=parent.binding_ref,
        story_objective_ref='observed-combat-objective', story_approach_only=False)
    options = SimpleNamespace(menu=menu, bindings=(dose, binding))
    recorder = object.__new__(recording.NativeConsequenceRecorder)
    recorder.session = SimpleNamespace(source=deepcopy(plan['source']), model_feature_version=15)
    recorder.spec_document = spec.document()
    recorder.plan = None
    recorder.phases = []
    recorder.active = None
    recorder.done = False
    recorder.preparation_parent_witness = None
    recorder.capture = lambda: deepcopy(plan['before'])
    return plan, phases, menu, recorder, options, dose, binding


def declared_machine_plan(tmp_path, monkeypatch):
    plan, phases, menu, recorder, options, dose, parent = owned_parent_documents(tmp_path, monkeypatch)
    witness = recorder.declare_preparation_parent(options, dose, parent)
    plan.update(schema='pokemon.red.challenge-consequence-plan.v9', preparation_parent_witness=witness)
    return plan, phases, menu, recorder, options, dose, parent


def test_conditioned_machine_row_equals_runtime_input_without_changing_raw_menu_or_payoff(tmp_path, monkeypatch):
    plan, phases, menu, recorder, options, dose, parent = declared_machine_plan(tmp_path, monkeypatch)
    original = deepcopy(plan)
    raw = menu.policy_dict()
    candidate = condition_consequence_candidate(menu.candidates[0], menu.candidates[1])
    expected_menu = replace(menu, candidates=(candidate, menu.candidates[1]))
    expected = expected_menu.candidate_vector(0, feature_version=15)
    row = recording.project_consequence(plan, phases)
    atomic = deepcopy(plan)
    atomic.pop('preparation_parent_witness')
    atomic['schema'] = 'pokemon.red.challenge-consequence-plan.v8'
    unconditioned = recording.project_consequence(atomic, phases)
    assert row.features == expected
    assert row.features != unconditioned.features
    assert row.outcome == unconditioned.outcome
    assert row.outcome.actions == 120 and row.outcome.frames == 7000
    assert row.outcome.attempted and not row.outcome.completed
    assert menu.policy_dict() == raw == plan['menu']
    assert plan == original
    assert menu.candidates[0].challenge.combat_required is False
    assert menu.candidates[0].challenge.opposition_known is False
    assert expected_menu.candidates[0].challenge == menu.candidates[1].challenge
    assert expected_menu.candidates[0].move_change == menu.candidates[0].move_change
    assert expected_menu.candidates[0].matchup is menu.candidates[0].matchup
    assert row.declaration_sha256 == canonical_sha256(plan)


def test_declaration_keeps_public_signature_exact_source_and_machine_copy_before_inputs(tmp_path, monkeypatch):
    plan, _, menu, recorder, options, dose, parent = owned_parent_documents(tmp_path, monkeypatch)
    raw = deepcopy(menu.policy_dict())
    witness = recorder.declare_preparation_parent(options, dose, parent)
    assert witness['schema'] == 'pokemon.red.consequence-preparation-parent.v2'
    assert witness['machine_lesson'] == plan['spec']['machine_lesson']
    assert witness['preparation_target'] is None
    assert witness['model_queries'] == 0
    assert witness['menu_sha256'] == canonical_sha256(raw)
    assert witness['source_state_sha256'] == plan['before']['state_sha256']
    assert witness['selected_dose_ref'] == dose.binding_ref
    assert witness['parent_binding_ref'] == parent.binding_ref
    witness['machine_lesson']['lesson']['move_id'] = 1
    assert recorder.preparation_parent_witness['machine_lesson'] == plan['spec']['machine_lesson']
    assert menu.policy_dict() == raw and recorder.plan is None and recorder.phases == []


@pytest.mark.parametrize('fault', [
    'legacy_machine_schema', 'source', 'menu', 'parent_ref', 'dose_ref',
    'dose_index', 'parent_index', 'queries_bool', 'authority', 'target',
    'foreign_target_rehashed', 'unowned', 'recipient_pp', 'approach_parent',
    'unknown_parent', 'noncombat_parent', 'missing', 'extra_field', 'development',
])
def test_machine_parent_witness_fails_closed_without_relaxing_native_guards(tmp_path, monkeypatch, fault):
    plan, _, menu, _, _, _, _ = declared_machine_plan(tmp_path, monkeypatch)
    witness = plan['preparation_parent_witness']
    if fault == 'legacy_machine_schema':
        witness['schema'] = 'pokemon.red.consequence-preparation-parent.v1'
        witness.pop('machine_lesson')
    elif fault == 'source': witness['source_state_sha256'] = 'f' * 64
    elif fault == 'menu': witness['menu_sha256'] = 'f' * 64
    elif fault == 'parent_ref': witness['parent_binding_ref'] = 'foreign-parent'
    elif fault == 'dose_ref': witness['selected_dose_ref'] = 'foreign-dose'
    elif fault == 'dose_index': witness['selected_dose_index'] = 1
    elif fault == 'parent_index': witness['parent_index'] = 0
    elif fault == 'queries_bool': witness['model_queries'] = False
    elif fault == 'authority': witness['authority'] = 'model_selected'
    elif fault == 'target': witness['machine_lesson']['lesson']['move_id'] = 1
    elif fault == 'foreign_target_rehashed':
        witness['machine_lesson']['lesson']['replace_slot'] = 1
        plan['spec']['machine_lesson'] = deepcopy(witness['machine_lesson'])
    elif fault == 'unowned': plan['before']['economy']['inventory'] = []
    elif fault == 'recipient_pp': plan['before']['lesson']['party'][0]['moves'][3][1] -= 1
    elif fault == 'approach_parent': witness['bindings'][1]['story_approach_only'] = True
    elif fault == 'missing': plan['preparation_parent_witness'] = None
    elif fault == 'extra_field': witness['invented'] = True
    elif fault == 'development': plan['source']['partition'] = 'development'
    else:
        parent = menu.candidates[1]
        challenge = OptionChallenge(True, False, 0., 0., 0.) if fault == 'unknown_parent' else OptionChallenge(False, False, 0., 0., 0.)
        menu = replace(menu, candidates=(menu.candidates[0], replace(parent, challenge=challenge, matchup=None if fault == 'noncombat_parent' else parent.matchup)))
        plan['menu'] = menu.policy_dict()
        witness['menu_sha256'] = canonical_sha256(plan['menu'])
    with pytest.raises((ValueError, KeyError)):
        recording._conditioned_consequence_menu(plan, menu, 0)


def test_machine_validation_precedes_any_conditioning(tmp_path, monkeypatch):
    plan, _, menu, _, _, _, _ = declared_machine_plan(tmp_path, monkeypatch)
    plan['before']['economy']['inventory'] = []
    monkeypatch.setattr(recording, 'condition_consequence_candidate',
        lambda *_: pytest.fail('unowned machine reached conditioning'))
    with pytest.raises(ValueError): recording._conditioned_consequence_menu(plan, menu, 0)


def test_machine_parent_cannot_be_declared_after_leading_input(tmp_path, monkeypatch):
    plan, _, _, recorder, options, dose, parent = owned_parent_documents(tmp_path, monkeypatch)
    before = deepcopy(plan['before'])
    before['actions'] = 1
    recorder.capture = lambda: deepcopy(before)
    with pytest.raises(ValueError, match='leading costs'):
        recorder.declare_preparation_parent(options, dose, parent)
    assert recorder.preparation_parent_witness is None


def test_machine_v2_does_not_replace_legacy_level_v1(tmp_path, monkeypatch):
    from test_parent_conditioning import prepared
    _, _, recorder, options, dose, parent = prepared(tmp_path, monkeypatch)
    witness = recorder.consequence.declare_preparation_parent(options, dose, parent)
    assert witness['schema'] == 'pokemon.red.consequence-preparation-parent.v1'
    assert 'machine_lesson' not in witness
    plan = recorder.consequence.begin(options, dose, preflight_only=True)
    plan = deepcopy(plan)
    plan['preparation_parent_witness']['schema'] = 'pokemon.red.consequence-preparation-parent.v2'
    plan['preparation_parent_witness']['machine_lesson'] = None
    with pytest.raises(ValueError):
        recording._conditioned_consequence_menu(plan, options.menu, options.bindings.index(dose))
