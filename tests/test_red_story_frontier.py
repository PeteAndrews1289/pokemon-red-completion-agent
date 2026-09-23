from dataclasses import dataclass, replace

import pytest
from test_red_goal_manager import _Observer, _Reader

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillExecution,
    ObjectiveSkillRegistry,
)
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    EventFlag,
    ItemId,
    MapId,
)
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalOpportunityEnumerator,
    RedStoryGoalBindingProvider,
)
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_story_frontier import (
    admit_red_story_resources,
    build_red_story_frontier,
)
from pokemon_red_completion.route import COMPLETION_QUEST


@pytest.fixture
def live():
    reader, observer = _Reader(), _Observer()
    reader.raw = replace(
        reader.raw, map_id=MapId.CELADON_POKECENTER, player_x=3, player_y=3,
        party_count=3, party_species_ids=(0x1C, 0x40, 0x3B), party_levels=(36, 19, 22),
        party_hp=(98, 51, 37), party_max_hp=(98, 51, 37), party_status=(0, 0, 0),
        party_moves=((44, 39, 61, 55), (64, 28, 15, 31), (10, 45, 91, 0)),
        party_pp=((25, 30, 20, 25), (35, 15, 30, 20), (35, 40, 10, 0)),
        first_party_moves=(44, 39, 61, 55), first_party_pp=(25, 30, 20, 25),
        player_money=12992, badge_bits=7, event_flags=bytes(320), status_flags_1=0,
        bag_items=((int(ItemId.SUPER_POTION), 11), (int(ItemId.SILPH_SCOPE), 1)),
    )
    completed = (
        "power_on", "begin_adventure", "choose_starter", "receive_pokedex", "reach_pewter",
        "defeat_brock", "reach_cerulean", "help_bill", "defeat_misty", "reach_vermilion",
        "obtain_cut", "defeat_surge", "reach_lavender", "reach_celadon",
        "clear_rocket_hideout", "obtain_silph_scope",
    )
    observer.state = GameState(GameMode.OVERWORLD, frozenset().union(*(
        COMPLETION_QUEST.objective(name).completion_facts for name in completed
    )), "celadon_pokecenter")
    return PokemonRedGoalStateAdapter(reader, observer, COMPLETION_QUEST).observe()


@pytest.mark.parametrize("objective,cost", [
    ("defeat_erika", 2200), ("rescue_fuji", 0), ("reach_saffron", 2300),
])
def test_native_entry_resource_plans(live, objective, cost):
    plan = admit_red_story_resources(live, objective)
    assert plan.executable and plan.planned_spend == cost
    if cost:
        poor = replace(live, raw=replace(live.raw, player_money=cost - 1))
        assert admit_red_story_resources(poor, objective).reason == "insufficient_cash"
        exact = replace(live, raw=replace(live.raw, player_money=cost))
        assert admit_red_story_resources(exact, objective).executable


def silph_live(live, *, cash=12950):
    events = bytearray(live.raw.event_flags)
    events[int(EventFlag.GOT_TM13) // 8] |= 1 << (int(EventFlag.GOT_TM13) % 8)
    return replace(live, raw=replace(live.raw, map_id=MapId.SAFFRON_POKECENTER,
        first_party_moves=(44, 39, 58, 55), first_party_pp=(25, 30, 10, 25),
        player_money=cash, event_flags=bytes(events),
        status_flags_1=SAFFRON_GUARD_ACCESS_MASK,
        bag_items=((int(ItemId.X_SPECIAL), 1), (int(ItemId.X_ACCURACY), 2))))


def test_silph_resource_admission_requires_native_gift_and_exact_missing_stock(live):
    ready = silph_live(live)
    assert not admit_red_story_resources(ready, "liberate_silph").executable
    plan = admit_red_story_resources(ready, "liberate_silph", silph_gift_received=False)
    assert plan.executable and plan.planned_spend == 11550
    assert "no_sale_stock_top_up" in plan.scripted_support
    poor = silph_live(live, cash=11549)
    assert not admit_red_story_resources(
        poor, "liberate_silph", silph_gift_received=False).executable
    stocked = replace(ready, raw=replace(ready.raw,
        bag_items=ready.raw.bag_items + ((int(ItemId.HYPER_POTION), 9),)))
    assert admit_red_story_resources(stocked, "liberate_silph",
                                    silph_gift_received=False).planned_spend == 1050


@pytest.mark.parametrize("field,value", [("status_flags_1", 0), ("event_flags", b""),
    ("first_party_pp", (25, 30, 9, 25)), ("map_id", MapId.LAVENDER_POKECENTER)])
def test_silph_rejects_unqualified_entry(live, field, value):
    ready = silph_live(live)
    changed = replace(ready, raw=replace(ready.raw, **{field: value}))
    assert not admit_red_story_resources(
        changed, "liberate_silph", silph_gift_received=False).executable


@pytest.mark.parametrize("field,value", [
    ("party_hp", (90, 51, 37)), ("party_status", (0, 1, 0)), ("player_money", None),
    ("bag_items", None), ("party_moves", None), ("party_pp", None),
    ("party_count", 6), ("party_hp", (98,)), ("battle_state", 1), ("player_x", 4),
])
def test_missing_or_unsafe_resources_reject_every_branch(live, field, value):
    changed = replace(live, raw=replace(live.raw, **{field: value}))
    for name in ("defeat_erika", "rescue_fuji", "reach_saffron"):
        assert not admit_red_story_resources(changed, name).executable


@pytest.mark.parametrize("special,accuracy,cost", [(0, 0, 2200), (2, 1, 550), (3, 1, 200)])
def test_erika_quotes_only_missing_stock(live, special, accuracy, cost):
    bag = (*live.raw.bag_items, (int(ItemId.X_SPECIAL), special),
           (int(ItemId.X_ACCURACY), accuracy))
    plan = admit_red_story_resources(replace(live, raw=replace(live.raw, bag_items=bag)),
                                    "defeat_erika")
    assert plan.executable and plan.planned_spend == cost


@pytest.mark.parametrize("event", [EventFlag.BEAT_ERIKA, EventFlag.GOT_TM13, EventFlag.GOT_TM21])
def test_erika_rejects_changed_one_shot_events(live, event):
    events = bytearray(live.raw.event_flags)
    events[int(event) // 8] |= 1 << (int(event) % 8)
    changed = replace(live, raw=replace(live.raw, event_flags=bytes(events)))
    assert not admit_red_story_resources(changed, "defeat_erika").executable


@pytest.mark.parametrize("field,value", [
    ("first_party_pp", (25, 30, 19, 25)), ("badge_bits", 0), ("event_flags", None),
    ("event_flags", b""), ("bag_items", ((int(ItemId.X_SPECIAL), 4),)),
    ("bag_items", ((int(ItemId.FRESH_WATER), 1),)),
])
def test_erika_refuses_incompatible_preparation(live, field, value):
    changed = replace(live, raw=replace(live.raw, **{field: value}))
    assert not admit_red_story_resources(changed, "defeat_erika").executable


def test_tower_stock_and_move_are_real_requirements(live):
    for raw in (replace(live.raw, first_party_pp=(25, 30, 0, 25)),
                replace(live.raw, first_party_moves=(44, 39, 55, 55)),
                replace(live.raw, bag_items=((int(ItemId.SILPH_SCOPE), 1),)),
                replace(live.raw, bag_items=((int(ItemId.SUPER_POTION), 11),))):
        assert not admit_red_story_resources(replace(live, raw=raw), "rescue_fuji").executable


def test_saffron_support_tracks_actual_gate_party_and_inventory(live):
    open_gate = replace(live, raw=replace(live.raw, status_flags_1=SAFFRON_GUARD_ACCESS_MASK))
    assert admit_red_story_resources(open_gate, "reach_saffron").planned_spend == 0
    # The adapter uses the actual chapter constants, not a species ID policy feature.
    from pokemon_red_completion.saffron import EEVEE
    eevee = replace(live, raw=replace(live.raw, party_species_ids=(0xB3, 0x40, EEVEE)))
    assert admit_red_story_resources(eevee, "reach_saffron").planned_spend == 200
    for raw in (replace(live.raw, status_flags_1=None),
                replace(live.raw, bag_items=((int(ItemId.THUNDER_STONE), 1),)),
                replace(live.raw, bag_items=((int(ItemId.SODA_POP), 1),))):
        assert not admit_red_story_resources(replace(live, raw=raw), "reach_saffron").executable


@dataclass
class Skill:
    objective_id: str
    calls: int = 0
    max_actions: int = 100
    max_frames: int = 10000
    additional_effect_facts: frozenset = frozenset()

    @property
    def specialist(self):
        return COMPLETION_QUEST.objective(self.objective_id).specialist

    @property
    def expected_facts(self):
        return COMPLETION_QUEST.objective(self.objective_id).completion_facts

    def availability(self, state):
        return ObjectiveSkillAvailability(True, "test boundary")

    def execute(self):
        self.calls += 1
        return ObjectiveSkillExecution(1, 16)


def frontier(live, observe=None, reverse=False, ordinary=None):
    skills = tuple(Skill(name) for name in ("defeat_erika", "rescue_fuji", "reach_saffron"))
    observer = _Observer()
    observer.state = live.game_state
    provider = RedStoryGoalBindingProvider(COMPLETION_QUEST,
        ObjectiveSkillRegistry(skills[::-1] if reverse else skills), observer)
    empty = ordinary or RedGoalOpportunityEnumerator(()).enumerate(live)
    result = build_red_story_frontier(observation=live, provider=provider,
        ordinary_bindings=empty, observe=observe or (lambda: live))
    return result, skills, empty


def test_frontier_composes_costs_and_executes_only_selected_binding(live):
    current = [live]
    result, skills, empty = frontier(live, lambda: current[0])
    assert len(result.supplements) == 3 and result.required_cash == 2300
    assert sum(s.calls for s in skills) == 0
    menu = build_red_live_option_set(situation=live.situation, binding_set=empty,
        supplements=result.supplements, model_feature_version=4, ordering_seed_sha256="a" * 64,
        economy_snapshot=live.economy_snapshot(), target_cash=result.required_cash)
    assert len({menu.menu.candidate_vector(i) for i in menu.menu.available_indices}) == 3
    selected = result.supplements[1]
    execution = selected.binding.execute()
    assert sum(s.calls for s in skills) == 1
    assert execution.evidence['story_resources']['planned_spend'] == (
        selected.candidate.economy_offer.planned_spend)
    current[0] = replace(live, raw=replace(live.raw, player_money=1))
    with pytest.raises(ValueError, match="changed before execution"):
        result.supplements[0].binding.execute()
    assert sum(s.calls for s in skills) == 1
    reversed_result, _, _ = frontier(live, reverse=True)
    assert [s.candidate for s in result.supplements] == [
        s.candidate for s in reversed_result.supplements]


def test_frontier_preserves_recovery_binding_and_masks_unaffordable_goals(live):
    empty = RedGoalOpportunityEnumerator(()).enumerate(live)
    recovery = ExecutableGoalBinding("recover", GoalKind.RESTORE_TEAM, 0.1, 0.0,
                                    lambda: None, lambda _: None)
    ordinary = GoalBindingSet(tuple(recovery.opportunity if o.kind is recovery.kind else o
                                  for o in empty.opportunities), (recovery,))
    result, _, _ = frontier(live, ordinary=ordinary)
    assert len(result.supplements) == 3
    poor = replace(live, raw=replace(live.raw, player_money=0))
    result, _, _ = frontier(poor)
    assert len(result.supplements) == 1 and result.required_cash == 0
    assert result.supplements[0].binding.binding_ref.endswith(":rescue_fuji")
    assert admit_red_story_resources(live, "unknown").reason == "unsupported_resource_contract"


def test_frontier_rejects_legacy_story_and_unversioned_costs(live):
    _, skills, empty = frontier(live)
    provider = RedStoryGoalBindingProvider(COMPLETION_QUEST, ObjectiveSkillRegistry(skills),
                                          _Observer())
    for version in (3, 4.0, True):
        with pytest.raises(ValueError, match="version 4"):
            build_red_story_frontier(observation=live, provider=provider,
                ordinary_bindings=empty, observe=lambda: live, model_feature_version=version)
    legacy = provider.offer(live).binding
    ordinary = GoalBindingSet(tuple(legacy.opportunity if o.kind is legacy.kind else o
                                    for o in empty.opportunities), (legacy,))
    with pytest.raises(ValueError, match="legacy single-target"):
        build_red_story_frontier(observation=live, provider=provider,
                                  ordinary_bindings=ordinary, observe=lambda: live)


def test_partial_event_buffer_never_means_unspent_reward(live):
    truncated = bytes(max(int(e) for e in (
        EventFlag.BEAT_ERIKA, EventFlag.GOT_TM21, EventFlag.GOT_TM13,
    )) // 8)
    changed = replace(live, raw=replace(live.raw, event_flags=truncated))
    assert not admit_red_story_resources(changed, "defeat_erika").executable


def test_preparation_terminal_core_is_checked_before_spending(live):
    wartortle = replace(live, raw=replace(live.raw, party_species_ids=(0xB3, 0x40, 0x3B)))
    assert (admit_red_story_resources(wartortle, "reach_saffron").reason
            == "unsupported_jolteon_terminal_core")
    result, skills, _ = frontier(wartortle)
    assert len(result.supplements) == 2
    assert all(not s.binding.binding_ref.endswith(":reach_saffron") for s in result.supplements)
    assert sum(s.calls for s in skills) == 0
    # Existing Jolteon means no preparation branch and no repeated 2100 purchase.
    from pokemon_red_completion.saffron import JOLTEON
    retained = replace(wartortle, raw=replace(wartortle.raw,
        party_species_ids=(*wartortle.raw.party_species_ids, JOLTEON), party_count=4,
        party_hp=(*wartortle.raw.party_hp, 68), party_max_hp=(*wartortle.raw.party_max_hp, 68),
        party_status=(0, 0, 0, 0), party_moves=(*wartortle.raw.party_moves, (33, 28, 0, 0)),
        party_pp=(*wartortle.raw.party_pp, (35, 15, 0, 0))))
    plan = admit_red_story_resources(retained, "reach_saffron")
    assert plan.executable and plan.planned_spend == 200
    assert "eevee_gift" not in plan.scripted_support
