from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_party import memory_with
from test_registered_learning_bridge import observations

from pokemon_red_completion import red_collection_teacher_learning as module
from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_player import NativeExecutionIdentity
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_player_lesson_runtime import native_action_record_id
from pokemon_red_completion.red_registered_observation import project_registered_observation


def lesson(tmp_path):
    _, before, after, policy = observations(tmp_path)
    before, after = (
        project_registered_observation(o, policy).public_dict() for o in (before, after)
    )
    menu = LivingDexOptionMenu(
        LivingDexOptionContext(*([0.5] * 7)),
        tuple(
            LivingDexOptionCandidate(
                str(i),
                LivingDexOptionFeatures(kind, 1.0, 0.0, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0),
                LivingDexOptionAvailability.AVAILABLE,
            )
            for i, kind in enumerate((LivingDexOptionKind.EVOLVE, LivingDexOptionKind.ACQUIRE))
        ),
    )
    plan = dict(
        schema=module.COLLECTION_TEACHER_SCHEMA,
        source=dict(partition="train", state_sha256="a" * 64),
        before=before,
        before_sha256="a" * 64,
        menu=menu.policy_dict(),
        selected_index=0,
        selected_kind="evolve_species",
        feature_version=7,
        maximum_actions=100,
        maximum_frames=1000,
    )
    result = dict(
        declaration_sha256=canonical_sha256(plan),
        source_sha256="a" * 64,
        succeeded=True,
        field_ready=True,
        buttons_released=True,
        after=after,
        actions=2,
        frames=200,
    )
    trace = [
        dict(ordinal=0, before_frame=0, after_frame=100, succeeded=True),
        dict(ordinal=1, before_frame=100, after_frame=200, succeeded=True),
    ]
    return plan, result, trace


def test_observed_evolution_becomes_one_unit_weight_outcome_not_alternative_labels(tmp_path):
    plan, result, trace = lesson(tmp_path)
    row = module.collection_teacher_example(plan, result, trace)
    assert row.partition == "train" and len(row.features) == 356
    assert row.outcome.verified_success and row.outcome.completion_gain == pytest.approx(1 / 124)
    assert row.outcome.action_cost == pytest.approx(2 / 30000)
    assert row.outcome.frame_cost == pytest.approx(200 / 3000000)
    assert row.public_dict()["regression_weight"] == 1
    assert row.public_dict()["comparative_choice"] is False


def test_readable_partial_work_remains_a_failed_lesson_not_a_success(tmp_path):
    plan, result, trace = lesson(tmp_path)
    result.update(after=plan["before"], succeeded=False)
    row = module.collection_teacher_example(plan, result, trace)
    assert not row.outcome.verified_success and row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0


def recovery_lesson(tmp_path, *, pp_only=False):
    from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu

    plan, result, trace = lesson(tmp_path)
    menu = restore_living_dex_policy_menu(plan["menu"])
    first = replace(
        menu.candidates[0],
        features=replace(menu.candidates[0].features, kind=LivingDexOptionKind.RESTORE),
    )
    plan.update(
        menu=replace(menu, candidates=(first, menu.candidates[1])).policy_dict(),
        selected_kind="restore_team",
    )
    diagnostics = dict(
        schema="pokemon.red.player-diagnostic-state.v1",
        diagnostic_only=True,
        party_species_ids=[165],
        party_levels=[19],
        party_hp=[40 if pp_only else 12],
        party_max_hp=[40],
        party_status=[0],
        party_moves=[[33, 39, 98, 158]],
        party_pp_current=[[1, 2, 3, 4]],
        party_pp_maximum=[[35, 30, 30, 15]],
    )
    plan["before_diagnostics"] = diagnostics
    result["after_diagnostics"] = deepcopy(diagnostics)
    result["after_diagnostics"].update(party_hp=[40], party_pp_current=[[35, 30, 30, 15]])
    # Nursing cannot invent a new registration or evolved specimen.
    result["after"] = deepcopy(plan["before"])
    result["declaration_sha256"] = canonical_sha256(plan)
    return plan, result, trace


@pytest.mark.parametrize("pp_only", [False, True])
def test_actual_recovery_uses_existing_unit_outcome_and_retains_zero_registration(
    tmp_path, pp_only
):
    plan, result, trace = recovery_lesson(tmp_path, pp_only=pp_only)
    row = module.collection_teacher_example(plan, result, trace)
    assert row.partition == "train" and row.outcome.verified_success
    assert row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0 and row.public_dict()["regression_weight"] == 1
    assert row.public_dict()["comparative_choice"] is False


def test_failed_settled_recovery_keeps_costs_without_claiming_restoration(tmp_path):
    plan, result, trace = recovery_lesson(tmp_path)
    result.update(succeeded=False, after_diagnostics=deepcopy(plan["before_diagnostics"]))
    row = module.collection_teacher_example(plan, result, trace)
    assert not row.outcome.verified_success and row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0


@pytest.mark.parametrize(
    "fault",
    [
        "before_missing",
        "after_missing",
        "unknown_hp",
        "unknown_pp",
        "party_change",
        "level_change",
        "pp_capacity",
        "still_fainted",
        "status_remains",
        "pp_not_restored",
        "already_healthy",
        "invalid_hp",
        "invalid_pp",
        "short_pp",
        "party_size",
    ],
)
def test_recovery_rejects_unknown_incomplete_or_unearned_success(tmp_path, fault):
    plan, result, trace = recovery_lesson(tmp_path)
    before, after = plan["before_diagnostics"], result["after_diagnostics"]
    if fault == "before_missing":
        del plan["before_diagnostics"]
    elif fault == "after_missing":
        del result["after_diagnostics"]
    elif fault == "unknown_hp":
        after["party_hp"] = None
    elif fault == "unknown_pp":
        after["party_pp_current"] = None
    elif fault == "party_change":
        after["party_species_ids"] = [177]
    elif fault == "level_change":
        after["party_levels"] = [20]
    elif fault == "pp_capacity":
        after["party_pp_maximum"][0][0] = 36
    elif fault == "still_fainted":
        after["party_hp"] = [0]
    elif fault == "status_remains":
        after["party_status"] = [64]
    elif fault == "pp_not_restored":
        after["party_pp_current"][0][0] = 34
    elif fault == "already_healthy":
        plan["before_diagnostics"] = deepcopy(after)
    elif fault == "invalid_hp":
        after["party_hp"] = [41]
    elif fault == "invalid_pp":
        after["party_pp_current"][0][0] = -1
    elif fault == "short_pp":
        after["party_pp_current"][0].pop()
    elif fault == "party_size":
        before["party_status"].append(0)
        after["party_status"].append(0)
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError, match="recovery"):
        module.collection_teacher_example(plan, result, trace)


@pytest.mark.parametrize(
    "fault",
    [
        "development",
        "plan",
        "state",
        "battle",
        "held_button",
        "cost",
        "frames",
        "gap",
        "uncompleted",
        "ordinal",
        "wrong_kind",
        "unexecuted_success",
        "executor_bug",
    ],
)
def test_lesson_refuses_unverified_training_targets(tmp_path, fault):
    plan, result, trace = lesson(tmp_path)
    if fault == "development":
        plan["source"]["partition"] = "development"
    elif fault == "plan":
        result["declaration_sha256"] = "b" * 64
    elif fault == "state":
        result["source_sha256"] = "b" * 64
    elif fault == "battle":
        result["field_ready"] = False
    elif fault == "held_button":
        result["buttons_released"] = False
    elif fault == "cost":
        result["actions"] = 1
    elif fault == "frames":
        result["frames"] = 199
    elif fault == "gap":
        trace[1]["before_frame"] = 101
    elif fault == "uncompleted":
        trace[0]["succeeded"] = False
    elif fault == "ordinal":
        trace[0]["ordinal"] = 1
    elif fault == "wrong_kind":
        plan["selected_kind"] = "acquire_species"
    elif fault == "unexecuted_success":
        result["after"] = plan["before"]
    elif fault == "executor_bug":
        result["error_type"] = "ValueError"
    if fault in {"development", "wrong_kind"}:
        result["declaration_sha256"] = canonical_sha256(plan)
    expected = GoalManagerCompositionError if fault == "unexecuted_success" else ValueError
    with pytest.raises(expected):
        module.collection_teacher_example(plan, result, trace)


def memory():
    mem = memory_with(dict(species_id=165, level=19, hp=40, max_hp=40, experience=6859))
    mem.write_u8 = lambda address, value: mem.values.__setitem__(address, value)
    return mem


def test_teacher_xp_setup_changes_only_xp_and_projects_native_level_progress():
    mem = memory()
    original = mem.values.copy()
    cartridge = N(species=lambda _: N(experience_at_level=lambda level: level**3))
    writes = module.set_isolated_training_experience(
        mem,
        partition="train",
        isolated_training_setup=True,
        party_index=0,
        experience=7995,
        cartridge=cartridge,
    )
    party = PokemonRedPartyReader(mem).read_with_level_progress(cartridge)
    assert len(writes) == 3 and party.members[0].level == 19
    assert party.members[0].level_progress == pytest.approx((7995 - 6859) / (8000 - 6859))
    addresses = {w["address"] for w in writes}
    assert all(mem.values[a] == v for a, v in original.items() if a not in addresses)


@pytest.mark.parametrize(
    "partition,isolated,xp",
    [
        ("development", True, 7995),
        ("train", False, 7995),
        ("train", True, 8000),
        ("train", True, 6858),
    ],
)
def test_teacher_xp_setup_refuses_evaluation_or_level_changes(partition, isolated, xp):
    mem = memory()
    original = mem.values.copy()
    with pytest.raises(ValueError):
        module.set_isolated_training_experience(
            mem,
            partition=partition,
            isolated_training_setup=isolated,
            party_index=0,
            experience=xp,
            cartridge=N(species=lambda _: N(experience_at_level=lambda level: level**3)),
        )
    assert mem.values == original


def test_teacher_declaration_refuses_development_before_observing():
    with pytest.raises(ValueError, match="TRAIN"):
        module.declare_collection_teacher_lesson(
            N(source=dict(partition="development")), None, 0, setup_receipt_sha256="a" * 64
        )


class Store:
    def __init__(self):
        self.records = {}

    def publish_sealed_record(self, identifier, *, kind, record):
        self.records[identifier] = (kind, record)

    def find_sealed_record(self, identifier, expected_kind=None):
        if identifier not in self.records:
            return None
        kind, value = self.records[identifier]
        if expected_kind is not None and kind != expected_kind:
            raise ValueError("kind")
        return N(read=lambda: value)


def sealed(tmp_path):
    plan, result, trace = lesson(tmp_path)
    plan["execution"] = dict(run_id="unit-fixture", arm_id="evolve")
    result.update(declaration_sha256=canonical_sha256(plan), trace=trace)
    identity = NativeExecutionIdentity("unit-fixture", "evolve", "c" * 64, 1)
    native = dict(
        schema="pokemon.red.native-continuous-player.v2",
        source=plan["source"],
        execution=dict(
            run_id=identity.run_id,
            arm_id=identity.arm_id,
            model_sha256=identity.model_sha256,
            seed=identity.seed,
        ),
        limits=dict(actions=100, frames=1000),
    )
    store = Store()
    store.publish_sealed_record(
        identity.claim_id, kind="red_native_player_execution", record=native
    )
    store.publish_sealed_record(
        "rct-plan-" + canonical_sha256(plan), kind="red_collection_teacher_declaration", record=plan
    )
    for i, row in enumerate(trace):
        store.publish_sealed_record(
            native_action_record_id("trace", canonical_sha256(native), i),
            kind="red_native_lesson_trace",
            record=dict(row),
        )
        store.publish_sealed_record(
            native_action_record_id("action", canonical_sha256(native), i),
            kind="red_native_lesson_action",
            record=dict(ordinal=i, before_frame=row["before_frame"]),
        )
    return store, plan, result, identity, native


def test_sealed_lesson_roundtrip_reauthenticates_inputs_and_future_retention(tmp_path):
    store, plan, result, identity, _ = sealed(tmp_path)
    item = module.publish_collection_teacher_outcome(
        store, plan, result, native_execution_claim_id=identity.claim_id
    )
    original = module.load_collection_teacher_lesson(store, item)
    items, rows = module.retained_collection_teacher_lessons(
        store, dict(collection_teacher_lessons=[item.public_dict()])
    )
    assert items == (item,) and rows == (original,)
    with pytest.raises(ValueError, match="repeats"):
        module.retained_collection_teacher_lessons(
            store, dict(collection_teacher_lessons=[item.public_dict()]), (item,)
        )


@pytest.mark.parametrize("fault", ["missing_action", "trace", "action", "claim", "development"])
def test_sealed_lesson_rejects_forged_journal_or_native_identity(tmp_path, fault):
    store, plan, result, identity, native = sealed(tmp_path)
    item = module.publish_collection_teacher_outcome(
        store, plan, result, native_execution_claim_id=identity.claim_id
    )
    if fault == "missing_action":
        del store.records[native_action_record_id("action", canonical_sha256(native), 1)]
    elif fault == "trace":
        key = native_action_record_id("trace", canonical_sha256(native), 1)
        store.records[key] = (store.records[key][0], dict(store.records[key][1], after_frame=201))
    elif fault == "action":
        key = native_action_record_id("action", canonical_sha256(native), 1)
        store.records[key] = (store.records[key][0], dict(store.records[key][1], ordinal=0))
    elif fault == "claim":
        native["execution"]["seed"] = 2
    elif fault == "development":
        native["source"] = dict(native["source"], partition="development")
    with pytest.raises(ValueError):
        module.load_collection_teacher_lesson(store, item)
