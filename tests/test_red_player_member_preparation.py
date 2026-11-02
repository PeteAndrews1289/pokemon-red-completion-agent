from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_party_preparation import enemies, team
from test_player_option_preparation import facts
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.party_preparation import (
    PreparationPurpose,
    build_preparation_plan,
    next_preparation_decision,
)
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_player_member_preparation import (
    member_preparation_plans,
    preparation_venue_rank,
    preparation_venue_within_party_band,
)
from pokemon_red_completion.red_player_story_menu import (
    NativeStoryBranchInventory,
    plural_preparation_bindings,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def roster():
    return tuple(
        replace(
            m,
            observation=replace(m.observation, experience=m.observation.level**3),
            purpose=PreparationPurpose.COMBAT if i == 0 else PreparationPurpose.UNDECIDED,
        )
        for i, m in enumerate(team(17, 7, 5, 7))
    )


def test_preparation_band_prefers_productive_grass_not_just_nearest_route():
    nearby = preparation_venue_rank((12, 14, 15, 16), 3)
    productive = preparation_venue_rank((24, 26, 28, 30), 80)
    assert productive < nearby
    assert preparation_venue_rank((24, 26), 2) < preparation_venue_rank((24, 26), 20)
    assert preparation_venue_rank((20, 30), 2) == preparation_venue_rank((25, 25), 2)


def test_fresh_venue_band_does_not_suggest_late_grass_to_level_six_party():
    assert preparation_venue_within_party_band((2,3,4,5), (6,))
    assert not preparation_venue_within_party_band((18,20,22), (6,))
    assert preparation_venue_within_party_band((18,20,22), (52,34,30,25,29,33))
    assert preparation_venue_within_party_band((8,10), (9,))


@pytest.mark.parametrize("levels", [(), [6], (True,), (0,), (101,)])
def test_venue_band_rejects_unknown_or_invalid_party_levels(levels):
    with pytest.raises(ValueError,match="party levels"):
        preparation_venue_within_party_band((3,4),levels)


@pytest.mark.parametrize("levels,cost", (
    ((), 1), ([10], 1), ((True,), 1), ((0,), 1), ((101,), 1),
    ((10,), True), ((10,), -1), ((10,), float("inf")), ((10,), float("nan")),
))
def test_venue_rank_requires_decoded_finite_supported_values(levels, cost):
    with pytest.raises(ValueError, match="actual levels"):
        preparation_venue_rank(levels, cost)


def test_retained_league_loss_exposes_short_member_doses_not_full_roster_predictions():
    members = tuple(
        replace(m, observation=replace(m.observation, experience=m.observation.level**3),
                purpose=PreparationPurpose.COMBAT if i == 0 else PreparationPurpose.UNDECIDED)
        for i, m in enumerate(team(55, 47, 38, 38, 41, 40))
    )
    plan = build_preparation_plan(members, enemies(58))
    cartridge = SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)
    )
    choices = member_preparation_plans(
        plan, members, opponent_levels=(58,), forecast_ref="observed-loss",
        cartridge=cartridge, evolutions={}, maximum_level_gain=3,
    )
    assert len(choices) == 6
    assert tuple(intent.targets[0][1] for intent, _ in choices) == (58, 50, 41, 41, 44, 43)
    assert tuple(intent.targets[0][0] for intent, _ in choices) == tuple(
        member.specimen_ref for member in members
    )
    # An unseen level62 Dragonite and fixed lowest-member preference are not inserted.
    assert all(intent.opposition_level == 58 for intent, _ in choices)
    assert tuple(member.purpose for member in plan.roster) == (
        PreparationPurpose.COMBAT, *(PreparationPurpose.UNDECIDED for _ in range(5))
    )


def offers(members):
    plan = build_preparation_plan(members, enemies(18, 21))
    cartridge = SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)
    )
    return plan, member_preparation_plans(
        plan,
        members,
        opponent_levels=(18, 21),
        forecast_ref="private:forecast",
        cartridge=cartridge,
        evolutions={1: 36, 2: 20, 3: 18, 4: 10},
    )


def test_each_offer_targets_exact_member_without_mutating_persistent_roles():
    members = roster()
    before = tuple(members)
    original, choices = offers(members)
    assert len(choices) == 4
    assert members == before and original.roster == members
    for index, (plan, descriptor) in enumerate(choices):
        ref, target = plan.targets[0]
        assert len(plan.targets) == 1 and ref == members[index].specimen_ref
        assert next_preparation_decision(plan, plan.roster).target_slot == index + 1
        assert target == members[index].observation.level + 3
        assert descriptor.undecided_intent == (index != 0)
        assert descriptor.remaining_xp == target**3 - members[index].observation.level ** 3
        assert all(
            a == b for a, b in zip(plan.roster, members, strict=True) if a.specimen_ref != ref
        )
    assert choices[3][1].vector()[-1] == 1.0


def test_strongest_preview_adds_above_median_member_without_forcing_it():
    members = tuple(
        replace(m, observation=replace(m.observation, experience=m.observation.level**3))
        for m in team(20, 18, 7)
    )
    plan = build_preparation_plan(members, enemies(18, 21))
    arguments = dict(
        opponent_levels=(18, 21), forecast_ref="known-opposition",
        cartridge=SimpleNamespace(
            species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)),
        evolutions={}, maximum_level_gain=3,
    )
    legacy = member_preparation_plans(plan, members, **arguments)
    strongest = member_preparation_plans(plan, members, **arguments, reference_mode="strongest")
    assert members[0].specimen_ref not in {intent.targets[0][0] for intent, _ in legacy}
    assert strongest[0][0].targets == ((members[0].specimen_ref, 21),)
    assert strongest[0][1].remaining_xp == 21**3 - 20**3
    assert all(intent.opposition_level == 21 for intent, _ in strongest)
    assert plan.opposition_level == 20
    assert plan.roster == members


def test_strongest_quote_still_excludes_collection_and_caps_each_dose():
    members = tuple(
        replace(m, observation=replace(m.observation, experience=m.observation.level**3))
        for m in team(21, 18, 7)
    )
    members = (*members[:2], replace(members[2], purpose=PreparationPurpose.COLLECTION))
    plan = build_preparation_plan(members, enemies(18, 21))
    choices = member_preparation_plans(
        plan, members, opponent_levels=(18, 21), forecast_ref="known-opposition",
        cartridge=SimpleNamespace(
            species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)),
        evolutions={}, maximum_level_gain=1, reference_mode="strongest",
    )
    assert len(choices) == 1
    assert choices[0][0].targets == ((members[1].specimen_ref, 19),)


def test_invalid_opposition_reference_is_not_silently_median():
    members = roster()
    plan, _ = offers(members)
    with pytest.raises(ValueError, match="reference"):
        member_preparation_plans(
            plan, members, opponent_levels=(18, 21), forecast_ref="known-opposition",
            cartridge=SimpleNamespace(), evolutions={}, reference_mode="unknown",
        )


@pytest.mark.parametrize("gain", [1, 3])
def test_post_defeat_doses_include_carry_above_real_opposition_without_invented_levels(gain):
    from test_post_battle_strategy import aftermath

    members = tuple(
        replace(m, observation=replace(m.observation, experience=m.observation.level**3))
        for m in team(62, 28, 32)
    )
    plan = build_preparation_plan(members, enemies(54, 56))
    arguments = dict(
        opponent_levels=(54, 56), forecast_ref="actual-cartridge-opposition",
        cartridge=SimpleNamespace(
            species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)),
        evolutions={}, maximum_level_gain=gain, reference_mode="strongest",
    )
    legacy = member_preparation_plans(plan, members, **arguments)
    assert members[0].specimen_ref not in {intent.targets[0][0] for intent, _ in legacy}
    choices = member_preparation_plans(plan, members, **arguments,
        allow_above_reference=True, observed_defeat=aftermath())
    assert len(choices) == 3
    assert choices[0][0].targets == ((members[0].specimen_ref, 62+gain),)
    assert all(intent.opposition_level == 56 for intent, _ in choices)
    assert choices[0][1].remaining_xp == (62+gain)**3-62**3
    assert plan.roster == members
    with pytest.raises(ValueError, match="target level"):
        replace(choices[0][0], targets=((members[0].specimen_ref, 62+gain+1),))


@pytest.mark.parametrize("defeat", [None, "invented", "won"])
def test_above_reference_options_require_typed_actual_loss(defeat):
    from test_post_battle_strategy import aftermath

    from pokemon_red_completion.post_battle_strategy import BattleResult

    members = roster()
    plan, _ = offers(members)
    battle = (aftermath(result=BattleResult.WON, opponents_defeated=2,
                        terminal_fainted_count=0, terminal_hp_fraction=1.0)
              if defeat == "won" else defeat)
    with pytest.raises(ValueError, match="observed defeat"):
        member_preparation_plans(plan, members, opponent_levels=(18, 21), forecast_ref="preview",
            cartridge=SimpleNamespace(), evolutions={}, allow_above_reference=True,
            observed_defeat=battle)


@pytest.mark.parametrize("partition", [None, "development", "train"])
def test_native_above_reference_refuses_untyped_or_non_development_scope(partition):
    from pokemon_red_completion.red_player_member_preparation import member_preparation_options

    with pytest.raises(ValueError, match="DEVELOPMENT"):
        member_preparation_options(None, None, plan=None, opponent_levels=(54,),
            forecast_ref="preview", home_map=174, route=None,
            battler=SimpleNamespace(source_partition=partition), allow_above_reference=True)


def test_post_defeat_options_do_not_train_level100_or_field_collection_roles():
    from test_post_battle_strategy import aftermath

    members = tuple(
        replace(m, observation=replace(m.observation, experience=m.observation.level**3))
        for m in team(100, 99, 30, 30)
    )
    members = (*members[:2], replace(members[2], purpose=PreparationPurpose.FIELD_UTILITY),
               replace(members[3], purpose=PreparationPurpose.COLLECTION))
    plan = build_preparation_plan(members, enemies(54, 56))
    choices = member_preparation_plans(plan, members, opponent_levels=(54, 56),
        forecast_ref="preview", cartridge=SimpleNamespace(
            species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)),
        evolutions={}, allow_above_reference=True, observed_defeat=aftermath())
    assert len(choices) == 1 and choices[0][0].targets == ((members[1].specimen_ref, 100),)


def test_utility_collection_and_unknown_xp_not_automatically_trained():
    members = list(roster())
    members[1] = replace(members[1], purpose=PreparationPurpose.FIELD_UTILITY)
    members[2] = replace(members[2], purpose=PreparationPurpose.COLLECTION)
    members[3] = replace(members[3], observation=replace(members[3].observation, experience=None))
    _, choices = offers(tuple(members))
    assert len(choices) == 1 and choices[0][0].targets[0][0] == members[0].specimen_ref


def mixed(branches, descriptors):
    ordinary, extra = plural_preparation_bindings(_ordinary_bindings([]), branches, _situation())
    return build_red_live_option_set(
        situation=_situation(),
        binding_set=ordinary,
        supplements=extra,
        model_feature_version=7,
        ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(427, ()),
        target_cash=0,
        preparations=descriptors,
    )


def test_member_menu_survives_neutral_ordering_and_dispatches_exact_executor():
    calls = []
    branches = tuple(
        _binding(GoalKind.DEVELOP_TEAM, binding_ref=f"private:{i}", calls=calls) for i in range(2)
    )
    descriptors = {b.binding_ref: facts(remaining_xp=100 + i * 500) for i, b in enumerate(branches)}
    first = mixed(branches, descriptors)
    second = mixed(tuple(reversed(branches)), descriptors)
    def vectors(menu):
        return sorted(menu.menu.candidate_vector(i, feature_version=7)
                      for i in menu.menu.available_indices)
    assert vectors(first) == vectors(second)
    train = [(i, b) for i, b in enumerate(first.bindings) if b.kind is GoalKind.DEVELOP_TEAM]
    assert len(train) == 2
    assert len({first.menu.candidate_vector(i, feature_version=7) for i, _ in train}) == 2
    for i, binding in train:
        assert first.menu.candidates[i].preparation == descriptors[binding.binding_ref]
        binding.execute()
        assert calls[-1] == binding.binding_ref
    assert "private:" not in str(first.menu.policy_dict())


def test_inventory_retains_descriptor_identity_and_rejects_stale_boundary():
    state = [b"initial"]
    runtime = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: state[0]))
    branches = tuple(
        _binding(GoalKind.DEVELOP_TEAM, binding_ref=f"private:{i}", calls=[]) for i in range(2)
    )
    pairs = tuple((b, facts()) for b in branches)
    inventory = NativeStoryBranchInventory(
        lambda *_: _ordinary_bindings([]),
        lambda *_: (),
        enumerate_preparation=lambda *_: pairs,
    )
    observation = SimpleNamespace(situation=_situation())
    ordinary = inventory.enumerate(runtime, None, observation)
    extras = inventory.supplements(runtime, None, observation, ordinary)
    boundary = SimpleNamespace(state=b"initial")
    assert inventory.preparations(runtime, ordinary, extras, boundary) == dict(pairs_by_ref(pairs))
    state[0] = b"changed"
    with pytest.raises(ValueError, match="stale"):
        inventory.preparations(runtime, ordinary, extras, boundary)


def pairs_by_ref(pairs):
    return ((b.binding_ref, descriptor) for b, descriptor in pairs)


def test_adapter_passes_single_member_plan_to_existing_routed_executor(monkeypatch):
    import pokemon_red_completion.red_player_member_preparation as module
    from pokemon_red_completion.red_party_preparation import preparation_trainee

    members = roster()
    plan, _ = offers(members)
    monkeypatch.setattr(module, "observe_preparation_members", lambda *_: members)
    monkeypatch.setattr(module, "internal_to_dex", lambda _: {i: i for i in range(1, 5)})
    monkeypatch.setattr(module, "evolution_graph", lambda _: {})
    monkeypatch.setattr(module, "RedPracticeCartridge", lambda _: SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda n: n**3)))
    passed, executed = [], []

    def route(runtime, actions, **kwargs):
        intent = kwargs["plan"]
        passed.append(intent)
        trainee = preparation_trainee(intent, intent.roster)
        binding = _binding(GoalKind.DEVELOP_TEAM, binding_ref="same-origin-home", calls=[])

        def execute():
            executed.append((trainee.specimen_ref, dict(intent.targets)[trainee.specimen_ref]))
            return binding.execute()

        return replace(binding, execute=execute)

    monkeypatch.setattr(module, "routed_preparation_binding", route)
    result = module.member_preparation_options(
        SimpleNamespace(emulator=object()), object(), plan=plan,
        opponent_levels=(18, 21), forecast_ref="preview", home_map=41,
        route=SimpleNamespace(rom=b"not-a-cartridge"),
        maximum_level_gain=1,
    )
    assert len(result) == 4 and len({b.binding_ref for b, _ in result}) == 4
    assert all(f.target_level == f.current_level + 1 for _, f in result)
    assert not executed
    for index in (2, 0, 3, 1):
        result[index][0].execute()
        assert executed[-1] == passed[index].targets[0]
    assert plan.roster == members


def test_compulsory_recovery_never_enumerates_optional_member_intents():
    recovery = _binding(GoalKind.RECOVER_CONTROL, binding_ref="recover", calls=[])
    base = _ordinary_bindings([])
    masked = next(o for o in base.opportunities if o.kind is GoalKind.EXPLORE)
    base = replace(base, bindings=(recovery,), opportunities=(recovery.opportunity, masked))
    runtime = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"state"))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: pytest.fail("recovery must exclude story"),
        enumerate_preparation=lambda *_: pytest.fail("recovery must exclude training"),
    )
    assert inventory.enumerate(runtime, None, SimpleNamespace(situation=_situation())) is base
