"""ROM-free semantic and compatibility checks, not native learning evidence."""
import copy
from dataclasses import replace
import numpy as np
import pytest

from test_living_dex_option_value import _context, _features, _settled
from test_red_player_owned_machines import fixture
from test_red_live_option_menu import _ordinary_bindings, _situation
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES, LivingDexCurriculumOutcomeExample,
    LivingDexEconomyHead, LivingDexOptionAvailability, LivingDexOptionCandidate,
    LivingDexOptionKind, LivingDexOptionMenu, LivingDexOptionValueModel,
    curriculum_features, option_feature_names, upgrade_option_value_model_for_move_change,
)
from pokemon_red_completion.living_dex_policy_codec import (
    living_dex_private_menu_dict, restore_living_dex_private_menu,
    restore_living_dex_policy_menu,
)
from pokemon_red_completion.player_option_move_change import (
    OptionMoveChange, move_change_feature_names, move_change_vector,
)
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_player_owned_machines import owned_machine_options
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def change(old=55, **kwargs):
    removed = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(old)) if old else None
    proposed = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(58))
    facts = OptionMoveChange(proposed=proposed, removed=removed,
        proposed_current_pp=proposed.max_pp, proposed_maximum_pp=proposed.max_pp,
        removed_current_pp=removed.max_pp if removed else None,
        removed_maximum_pp=removed.max_pp if removed else None,
        removed_stab=bool(removed and removed.type_name == "water"), proposed_stab=False)
    return replace(facts, **kwargs)


def candidate(facts=None, binding="private-species-and-map"):
    return LivingDexOptionCandidate(binding,
        _features(LivingDexOptionKind.DEVELOP, completion=0, unlock=0, effort=.04),
        LivingDexOptionAvailability.AVAILABLE, move_change=facts)


def model(economy=False):
    width = len(option_feature_names(9))
    targets = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    rng = np.random.default_rng(1001)
    head = None
    if economy:
        ew = len(option_feature_names(4))
        head = LivingDexEconomyHead(np.zeros((ew, 2)), np.array([.1, .2]),
            np.zeros(ew), np.ones(ew), "b" * 64, 2, 1., 1.)
    return LivingDexOptionValueModel(rng.normal(0, .001, (width, targets)),
        np.full(targets, .5), np.zeros(width), np.ones(width), "a" * 64, 2, 0, 1., 1.,
        feature_version=9, economy_head=head)


def test_native_shaped_replacements_no_longer_alias_and_legacy_prefix_is_exact():
    context = _context()
    a, b = candidate(change(44)), candidate(change(55))
    legacy = replace(a, move_change=None).vector(context, feature_version=9)
    assert len(legacy) == 370
    assert a.vector(context, feature_version=10)[:370] == legacy
    assert b.vector(context, feature_version=10)[:370] == legacy
    assert a.vector(context, feature_version=10) != b.vector(context, feature_version=10)
    assert len(a.vector(context, feature_version=10)) == len(option_feature_names(10))
    assert len(change().vector()) == len(move_change_feature_names())
    assert all("id" not in name and "slot" not in name for name in move_change_feature_names())
    with pytest.raises(ValueError, match="legacy scorer"):
        a.vector(context, feature_version=9)


def test_unknown_stats_matchups_and_absent_descriptor_remain_distinct_from_observed_zero():
    facts = change()
    unknown = dict(zip(move_change_feature_names(), facts.vector(), strict=True))
    assert unknown["move_change.recipient_stats_known"] == 0
    assert unknown["move_change.proposed_matchup_known"] == 0
    immune = replace(facts, proposed_effectiveness=0.)
    known = dict(zip(move_change_feature_names(), immune.vector(), strict=True))
    assert known["move_change.proposed_matchup_known"] == 1
    assert known["move_change.proposed_effectiveness"] == 0
    assert facts.vector() != immune.vector()
    assert move_change_vector(None) == (0.,) * len(move_change_feature_names())
    assert change(0).vector() != move_change_vector(None)


@pytest.mark.parametrize("kwargs", [
    {"proposed_current_pp": True}, {"proposed_current_pp": -1},
    {"proposed_current_pp": 64}, {"removed_current_pp": None},
    {"removed_maximum_pp": 0}, {"recipient_attack": 100},
    {"recipient_attack": 0, "recipient_special_attack": 100},
    {"recipient_attack": True, "recipient_special_attack": 100},
    {"removed_effectiveness": float("nan")}, {"proposed_effectiveness": 5},
    {"proposed_stab": 1},
])
def test_incoherent_or_unobserved_facts_are_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        change(**kwargs)


def test_pp_up_adjusted_resources_are_observed_instead_of_inferred_from_base_pp():
    facts = change(55, removed_current_pp=35, removed_maximum_pp=40)
    values = dict(zip(move_change_feature_names(), facts.vector(), strict=True))
    assert values["move_change.removed.pp_fraction"] == 35 / 40
    assert values["move_change.removed.current_pp"] == 35 / 63
    assert values["move_change.removed.maximum_pp"] == 40 / 63
    unknown = replace(facts, removed_current_pp=None, removed_maximum_pp=None)
    assert unknown.vector() != facts.vector()


def test_strict_move_fact_and_menu_codecs_preserve_policy_only_semantics():
    facts = change(recipient_attack=100, recipient_special_attack=120,
                   removed_effectiveness=.5, proposed_effectiveness=2.)
    assert OptionMoveChange.from_public(facts.public_dict()) == facts
    menu = LivingDexOptionMenu(_context(), (candidate(facts), candidate(change(44), "second-private")))
    assert menu.feature_version == 10
    assert restore_living_dex_policy_menu(menu.policy_dict()).policy_dict() == menu.policy_dict()
    assert restore_living_dex_private_menu(living_dex_private_menu_dict(menu)) == menu
    assert "private-species-and-map" not in str(menu.policy_dict())
    for field in ("move_id", "species_id", "slot", "label"):
        bad = copy.deepcopy(facts.public_dict());bad["proposed"][field] = 58
        with pytest.raises(ValueError):OptionMoveChange.from_public(bad)


def test_move_change_is_not_an_implicit_feature_on_unrelated_options():
    c = candidate(change())
    with pytest.raises(ValueError, match="development"):
        replace(c, features=replace(c.features, kind=LivingDexOptionKind.ACQUIRE))


@pytest.mark.parametrize("economy", [False, True])
def test_zero_extension_preserves_old_predictions_data_identity_and_economy_head(economy):
    baseline = model(economy)
    migrated = upgrade_option_value_model_for_move_change(baseline)
    assert migrated.feature_version == 10
    assert migrated.train_dataset_sha256 == baseline.train_dataset_sha256
    assert migrated.settled_examples == baseline.settled_examples
    assert migrated.censored_examples == baseline.censored_examples
    assert np.array_equal(migrated.coefficients[:370], baseline.coefficients)
    assert not np.any(migrated.coefficients[370:])
    assert not np.shares_memory(migrated.coefficients, baseline.coefficients)
    assert upgrade_option_value_model_for_move_change(migrated) is migrated
    context = replace(_context(), economy_snapshot=EconomySnapshot(100, ()), target_cash=500)
    old = candidate()
    for new in (old, candidate(change()), candidate(change(44))):
        np.testing.assert_allclose(migrated.predict_candidate(context, new).vector(),
            baseline.predict_candidate(context, old).vector(), rtol=0, atol=1e-14)
        assert migrated.predict_economy_candidate(context, new) == baseline.predict_economy_candidate(context, old)
    assert LivingDexOptionValueModel.from_dict(migrated.to_dict()).to_dict() == migrated.to_dict()


def test_old_curriculum_keeps_its_identity_and_unknown_move_columns():
    row = LivingDexCurriculumOutcomeExample("f" * 64, "train", 9,
        candidate().vector(_context(), feature_version=9),
        _settled(success=True, completion=0, unlock=0, action_cost=.1))
    before = row.public_dict()
    projected = curriculum_features(row, 10)
    assert projected[:370] == row.features
    assert projected[370:] == (0.,) * len(move_change_feature_names())
    assert row.public_dict() == before


def test_owned_machine_facts_are_explicit_opt_in_readonly_and_cross_the_mixed_menu(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    old = owned_machine_options(rt, actions, rom=b"fixture")
    new = owned_machine_options(rt, actions, rom=b"fixture", include_move_change_facts=True)
    assert all(row.candidate.move_change is None for row in old)
    assert all(row.candidate.move_change is not None for row in new)
    assert [row.binding.binding_ref for row in new] == [row.binding.binding_ref for row in old]
    assert not seen and rt.emulator.state == b"source"
    options = build_red_live_option_set(situation=_situation(resources=.1),
        binding_set=_ordinary_bindings([]), supplements=new, model_feature_version=10,
        ordering_seed_sha256="a" * 64, economy_snapshot=EconomySnapshot(58, ()), target_cash=0,
        force_resource_safety=False)
    assert options.menu.feature_version == 10
    assert not seen and rt.emulator.state == b"source"


def test_v10_connector_preserves_original_executors_and_adds_no_input(monkeypatch):
    from types import SimpleNamespace
    from pokemon_red_completion.red_player_owned_machines import connect_move_change_inventory
    rt, actions, seen = fixture(monkeypatch)
    existing = owned_machine_options(rt, actions, rom=b"fixture")
    calls = []
    def prior(runtime, executor, observed):
        assert runtime is rt and executor is actions
        calls.append(observed)
        return existing
    menu = SimpleNamespace(enumerate_owned_machines=prior)
    connect_move_change_inventory(menu, rom=b"fixture")
    callback = menu.enumerate_owned_machines
    connect_move_change_inventory(menu, rom=b"fixture")
    assert menu.enumerate_owned_machines is callback
    rows = callback(rt, actions, "current-observation")
    assert calls == ["current-observation"] and not seen
    assert [row.binding for row in rows] == [row.binding for row in existing]
    assert all(row.candidate.move_change is not None for row in rows)
    assert rt.emulator.state == b"source"


def test_v10_connector_can_add_legal_lessons_to_an_empty_old_inventory(monkeypatch):
    from types import SimpleNamespace
    from pokemon_red_completion.red_player_owned_machines import connect_move_change_inventory
    rt, actions, seen = fixture(monkeypatch)
    menu = SimpleNamespace(enumerate_owned_machines=None)
    connect_move_change_inventory(menu, rom=b"fixture")
    rows = menu.enumerate_owned_machines(rt, actions, None)
    assert len(rows) == 2 and not seen
    assert all(row.candidate.move_change is not None for row in rows)


@pytest.mark.parametrize("version", [9, 10])
def test_configured_assembly_preserves_workload_and_gates_new_inventory(tmp_path, version):
    from types import SimpleNamespace
    from test_red_player_configuration import config
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    calls = []
    menu = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
    def assembly(*args, **kwargs):
        calls.append(kwargs)
        return b"unchanged", None, menu, {}, {"partition": "train"}
    rom = tmp_path / "synthetic-mechanics.dat"
    rom.write_bytes(b"not-an-emulator-ROM")
    backend = SimpleNamespace(assembly=assembly, c=SimpleNamespace(ROM=rom))
    payload, factory, newmenu, holder, source = assemble_configured_player(
        backend, config(), tmp_path, tmp_path, plan_path=tmp_path/"plan.json",
        model_feature_version=version)
    assert payload == b"unchanged" and newmenu is menu
    assert calls[0]["include_level_workload"] is True
    assert bool(getattr(menu.enumerate_owned_machines, "move_change_inventory", False)) == (version == 10)
