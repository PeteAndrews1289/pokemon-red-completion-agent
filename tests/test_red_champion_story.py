from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _supply_transition_profile
from test_red_goal_skills import _adapter, _raw, _Reader

import pokemon_red_completion.red_champion_story as module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_champion_script import ChampionScriptBinding
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.observation import CurrentMapBlocks, FinalLeagueScene
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import bind_cartridge_trainer_story_profile
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT
from pokemon_red_completion.route_plan import RouteStep


def test_champion_profile_has_only_its_declared_skill_no_legacy_fallback():
    original = _supply_transition_profile()
    changed = bind_cartridge_trainer_story_profile(original, objective_id="defeat_champion")
    assert original.providers[0].parameters == {}
    assert changed.providers[1:] == original.providers[1:]
    runtime = SimpleNamespace(trainer_story_world=None, observer=object())
    provider = _build_provider(runtime, changed.providers[0], CountingExecutor(object()))
    skill = provider.skills.get("defeat_champion")
    assert isinstance(skill, module.RedCartridgeChampionSkill)
    assert provider.skills.get("defeat_lance") is None
    assert not skill.availability(GameState(GameMode.OVERWORLD, frozenset(), "lance")).executable


def fixture(monkeypatch, fault=None):
    raw = replace(
        _raw(),
        map_id=113,
        player_y=2,
        player_x=6,
        player_money=23983,
        badge_bits=255,
        event_flags=bytes(319),
        battle_result=0,
    )
    reader = _Reader(raw=raw, ready=True)
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(reader.raw.map_id, ((1,),))
    scene = {"stage": 1, "queue": 0, "won": False, "entry": 0, "battle_calls": 0}
    reader.read_final_league_scene = lambda: FinalLeagueScene(
        reader.raw.map_id,
        scene["stage"],
        153,
        scene["queue"],
        False,
    )
    reader.read_active_trainer_identity = lambda: (243, 43, 1 if fault == "identity" else 2)
    reader.read_pending_trainer_battle_identity = lambda: None
    adapter = _adapter(reader)

    def observe():
        facts = {"league:lance_defeated"}
        if scene["won"] and fault != "missing_champion":
            facts.add(CHAMPION_DEFEATED_FACT)
        if reader.raw.map_id == 118:
            facts.add(HALL_OF_FAME_FACT)
        mode = GameMode.HALL_OF_FAME if reader.raw.map_id == 118 else GameMode.OVERWORLD
        return replace(adapter.observe(), game_state=GameState(mode, frozenset(facts), "final"))

    inputs = []
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())

    def execute(action):
        inputs.append(action)
        emulator.frame_count += action.repeat if action.kind is MacroActionKind.WAIT else 24
        if action.kind is MacroActionKind.MOVE:
            assert reader.raw.map_id == 113 and (reader.raw.player_y, reader.raw.player_x) == (0, 5)
            scene["entry"] += 1
            reader.raw = replace(reader.raw, map_id=120, player_y=7, player_x=3)
            scene["queue"] = 5
        elif action.kind is MacroActionKind.WAIT:
            if scene["won"]:
                reader.raw = replace(reader.raw, map_id=118)
                scene["stage"] = 0
                if fault == "held_terminal":
                    emulator.pressed_buttons = frozenset({"a"})
            elif reader.raw.map_id == 120 and not reader.raw.battle_state:
                scene["queue"] = 0
                scene["stage"] = 2
                reader.dialogue = True
        elif action.kind is MacroActionKind.CONFIRM:
            assert action.repeat == 1, "confirm batches can overshoot a scene boundary"
            assert scene["queue"] == 0
            if fault != "intro_stuck":
                reader.raw = replace(reader.raw, battle_state=2)
                scene["stage"] = 3
                reader.dialogue = False

    actions = CountingExecutor(SimpleNamespace(execute=execute))
    runtime = SimpleNamespace(
        reader=reader, adapter=SimpleNamespace(observe=observe), emulator=emulator
    )
    script = ChampionScriptBinding(243, 43, 2, 2305, (), (), ())
    quote = TrainerPartyQuote(243, 2, (TrainerPartyMember(22, 130, 54),), 100, 5400)

    def quote_for(_rom, opponent, selected):
        assert opponent == 243 and selected == 2  # not normalized class43 or assumed starter
        return quote

    monkeypatch.setattr(module, "trainer_party_quote", quote_for)
    monkeypatch.setattr(module, "champion_script_binding", lambda *_: script)
    monkeypatch.setattr(module, "prepare_trainer_lead", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "Gen1TrainerSightProjector", lambda *_a, **_k: object())
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *_: object())
    world = SimpleNamespace(rom=b"qualified-by-test", replanner=lambda: object())
    approach = SimpleNamespace(terminal_at=(0, 5))

    def route(plan, _actions, _traversal, **_kwargs):
        assert plan is approach
        reader.raw = replace(reader.raw, player_y=0, player_x=5)
        return SimpleNamespace(passed=fault != "route")

    monkeypatch.setattr(module, "execute_route", route)

    class Controller:
        maximum_switches = 6
        switches = []
        moves_selected = 6

        def __init__(self, actual_reader, actual_emulator):
            assert actual_reader is reader and actual_emulator is emulator

        def run(self, actual_reader, _actions, _policy, **kwargs):
            scene["battle_calls"] += 1
            assert actual_reader is reader and kwargs["consume_battle_start_schedule"] is False
            assert kwargs["expected_map"] == 120
            kwargs["move_decision_guard"](reader.raw)
            reader.raw = replace(
                reader.raw,
                battle_state=0,
                battle_result=1 if fault == "defeat" else 0,
                player_money=29382 if fault == "payout" else 29383,
            )
            if fault == "bag":
                reader.raw = replace(reader.raw, bag_items=((4, 1),))
            kwargs["battle_exit_guard"](reader.raw)
            scene["won"] = True
            reader.ready = False  # epilogue is not ordinary input-ready field
            return reader.raw

    monkeypatch.setattr(module, "RedTrainerPartyController", Controller)
    skill = module.RedCartridgeChampionSkill(runtime, actions, world)
    skill._prepared_budget = 0
    entry = RouteStep(113, (0, 5), "up", 120, (7, 3), "warp", MacroActionKind.MOVE, "land", "land")
    skill._prepared = module._Prepared(
        observe(), script, object(), reader.read_current_map_blocks(), world, approach, entry,
        reader.read_final_league_scene(),
    )
    return skill, reader, inputs, scene


def test_owned_entry_single_taps_and_cartridge_epilogue_reach_concurrent_referee(monkeypatch):
    skill, reader, inputs, scene = fixture(monkeypatch)
    result = skill.execute()
    assert scene["entry"] == scene["battle_calls"] == 1
    assert reader.raw.map_id == 118 and not reader.ready
    assert result.evidence["concurrent_champion_and_hall_of_fame"] is True
    assert result.evidence["learned_battle_authority"] is False
    assert result.evidence["scene_movement_authority"] == "cartridge"
    assert [action.kind for action in inputs].count(MacroActionKind.MOVE) == 1
    assert all(action.repeat == 1 for action in inputs if action.kind is MacroActionKind.CONFIRM)
    count = len(inputs)
    with pytest.raises(module.RedChampionStoryError, match="unconsumed"):
        skill.execute()
    assert len(inputs) == count


@pytest.mark.parametrize("spent", [0, 1, 2])
@pytest.mark.parametrize("fault", [None, "unclaimed_spend", "epilogue_spend"])
def test_champion_budget_preserves_exact_bag_through_exit_and_epilogue(monkeypatch, spent, fault):
    skill, reader, inputs, scene = fixture(monkeypatch)
    reader.raw = replace(reader.raw, bag_items=((16, 3), (4, 8)))
    skill.maximum_full_restores = skill._prepared_budget = 2
    skill._prepared = replace(skill._prepared, before=skill.runtime.adapter.observe())
    ordinary = module.RedTrainerPartyController

    class Controller(module.RedTrainerSurvivalController):
        def run(self, actual_reader, actions, policy, **kwargs):
            assert kwargs['intent'].require_move_between_switches is False
            guard = kwargs['move_decision_guard']
            guard(reader.raw)
            self.heals_claimed = spent
            actual_spent = spent + (fault == 'unclaimed_spend')
            reader.raw = replace(reader.raw, bag_items=((16, 3 - actual_spent), (4, 8)))
            guard(reader.raw)
            return ordinary(reader, skill.runtime.emulator).run(
                actual_reader, actions, policy, **kwargs,
            )

    monkeypatch.setattr(module, 'RedTrainerSurvivalController', Controller)
    execute = skill.actions.delegate.execute
    def epilogue(action):
        execute(action)
        if fault == 'epilogue_spend' and scene['won']:
            reader.raw = replace(reader.raw, bag_items=((16, 3 - spent), (4, 7)))
    skill.actions.delegate.execute = epilogue
    if fault:
        with pytest.raises(module.RedChampionStoryError, match='bag|protected'):
            skill.execute()
    else:
        result = skill.execute()
        assert result.evidence['concurrent_champion_and_hall_of_fame'] is True
        assert result.evidence['bag_items_spent'] == spent
        assert result.evidence['maximum_full_restores'] == 2
        assert reader.raw.bag_items == ((16, 3 - spent), (4, 8))


@pytest.mark.parametrize(
    "fault",
    [
        "identity",
        "route",
        "defeat",
        "bag",
        "payout",
        "missing_champion",
        "held_terminal",
        "intro_stuck",
    ],
)
def test_failure_preserves_consumption_and_does_not_retry_entry(monkeypatch, fault):
    skill, _, inputs, scene = fixture(monkeypatch, fault)
    with pytest.raises(module.RedChampionStoryError):
        skill.execute()
    assert scene["entry"] <= 1
    assert len(inputs) <= 321
    count = len(inputs)
    with pytest.raises(module.RedChampionStoryError, match="unconsumed"):
        skill.execute()
    assert len(inputs) == count
    if fault in {"identity", "route", "intro_stuck"}:
        assert scene["battle_calls"] == 0


@pytest.mark.parametrize("fault", ["money", "stage", "dialogue", "readiness", "pending"])
def test_changed_origin_refuses_before_preparation_or_entry(monkeypatch, fault):
    skill, reader, inputs, scene = fixture(monkeypatch)
    if fault == "money":
        reader.raw = replace(reader.raw, player_money=23982)
    elif fault == "stage":
        scene["stage"] = 9
    elif fault == "dialogue":
        reader.dialogue = True
    elif fault == "pending":
        reader.read_pending_trainer_battle_identity = lambda: (247, 1)
    else:
        reader.ready = False
    with pytest.raises(module.RedChampionStoryError, match="origin"):
        skill.execute()
    assert not inputs and scene["entry"] == 0
