from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_silph as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalVerification


def setup(monkeypatch):
    raw = N(
        map_id=int(s.MapId.SAFFRON_POKECENTER),
        player_y=3,
        player_x=3,
        bag_items=((4, 7),),
        event_flags=b"",
        full=True,
        defeated=False,
    )
    state = [b"source"]
    lesson = {"completed_objectives": ["defeat_blaine"]}
    rt = N(
        emulator=N(frame_count=0, save_state_bytes=lambda: state[0]),
        reader=N(read=lambda: raw),
        adapter=N(graph=N(available_objectives=lambda _: (N(id="liberate_silph"),))),
    )
    actions = N(actions_executed=0)
    contract = object()
    checked = []
    actor = N(require_story_contract=checked.append, development_story_scope=object())
    route = N(rom=b"rom", allow_surf=True)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_raw_party_fully_restored", lambda raw: raw.full)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: raw.defeated)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (N(raw=raw, game_state=None), {k: list(v) for k, v in lesson.items()}),
    )
    monkeypatch.setattr(s, "silph_card_key_battle_contract", lambda rom, r: contract)
    monkeypatch.setattr(
        s,
        "FrozenStoryBattleController",
        lambda a, c, **kw: N(actor=a, contracts=c, rom=kw["evolution_rom"]),
    )

    def phase(em, reader, executor, *, rom, controller, record):
        assert controller.actor is actor and controller.contracts == (contract,)
        assert controller.rom == rom == b"rom"
        actions.actions_executed += 2
        em.frame_count += 8
        raw.bag_items += ((int(s.ItemId.CARD_KEY), 1),)
        raw.defeated = True
        state[0] = b"terminal"
        return dict(status="complete", card_key_acquired=True, chapter_complete=False)

    monkeypatch.setattr(s, "run_learned_silph_card_key_phase", phase)
    return rt, actions, route, actor, raw, lesson, state, contract, checked


@pytest.mark.parametrize(
    "guard", ["unavailable", "full_bag", "held", "defeated", "unready", "unrestored"]
)
def test_no_actor_or_input_before_native_phase_admission(monkeypatch, guard):
    rt, actions, route, actor, raw, lesson, state, contract, checked = setup(monkeypatch)
    if guard == "unavailable":
        rt.adapter.graph.available_objectives = lambda _: ()
    elif guard == "full_bag":
        raw.bag_items = tuple((n, 1) for n in range(1, 21))
    elif guard == "held":
        raw.bag_items = ((int(s.ItemId.CARD_KEY), 1),)
    elif guard == "defeated":
        raw.defeated = True
    elif guard == "unready":
        monkeypatch.setattr(s, "_field_ready", lambda _: False)
    else:
        raw.full = False
    assert s.silph_card_key_story_option(rt, actions, None, route=route, battler=actor) is None
    assert actions.actions_executed == 0 and not checked and state[0] == b"source"


@pytest.mark.parametrize("map_id", [19, 23, int(s.MapId.SAFFRON_POKECENTER)])
def test_missing_restoration_declines_silph_travel_without_forcing_recovery(monkeypatch, map_id):
    rt, actions, route, actor, raw, _, state, _, checked = setup(monkeypatch)
    raw.map_id, raw.player_y, raw.full = map_id, 7, False
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **k: pytest.fail("unusable travel"))
    assert s.silph_card_key_story_option(
        rt, actions, None, route=route, battler=actor, continuous_travel=True,
    ) is None
    assert actions.actions_executed == 0 and not checked and state[0] == b"source"


@pytest.mark.parametrize("center", [False, True])
def test_travel_is_existing_noncombat_quote_not_liberation(monkeypatch, center):
    rt, actions, route, actor, raw, *_ = setup(monkeypatch)
    raw.map_id = int(s.MapId.SAFFRON_POKECENTER) if center else int(s.MapId.CINNABAR_POKECENTER)
    raw.player_y = 7
    quoted = []
    binding = ExecutableGoalBinding(
        "travel",
        s.GoalKind.ADVANCE_STORY,
        0.1,
        0.1,
        lambda: pytest.fail("quote executed"),
        lambda _: GoalVerification.succeeded(),
    )
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **kw: quoted.append(kw) or binding)
    row = s.silph_card_key_story_option(
        rt, actions, None, route=route, battler=actor, continuous_travel=True, allow_surf=True
    )
    assert row[0] is binding and not row[1].combat_required
    assert quoted[0]["destination_at"] == ((3, 3) if center else None)
    assert quoted[0]["route_destination_at"] == (None if center else (3, 3))
    assert quoted[0]["objective_id"] == "liberate_silph" and quoted[0]["allow_surf"]
    assert actions.actions_executed == 0


def test_exact_actor_native_item_event_and_partial_chapter(monkeypatch):
    rt, actions, route, actor, raw, lesson, state, contract, checked = setup(monkeypatch)
    row = s.silph_card_key_story_option(
        rt,
        actions,
        None,
        route=route,
        battler=object(),
        battler_for_contract=lambda c: actor if c is contract else pytest.fail("wrong contract"),
    )
    assert actions.actions_executed == 0 and row[1].combat_required
    report = row[0].execute()
    assert report.actions_executed == 2 and report.frames_executed == 8
    assert report.evidence["objective_completed"] is report.evidence["chapter_complete"] is False
    assert report.evidence["phase"]["battle_authority"] == "development_scoped_frozen_model"
    assert row[0].verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson["completed_objectives"] == ["defeat_blaine"] and checked == [contract, contract]
    with pytest.raises(ValueError, match="consumed"):
        row[0].execute()


def test_blocked_full_route_can_quote_existing_verified_frontier(monkeypatch):
    rt, actions, route, actor, raw, *_ = setup(monkeypatch)
    raw.map_id = int(s.MapId.CINNABAR_POKECENTER)
    quotes = []
    binding = object()

    def quote(*args, **kw):
        quotes.append(kw)
        return binding if kw["frontier"] else None

    monkeypatch.setattr(s, "story_travel_binding", quote)
    row = s.silph_card_key_story_option(
        rt, actions, None, route=route, battler=actor, continuous_travel=True, allow_surf=True
    )
    assert row[0] is binding and not row[1].combat_required
    assert len(quotes) == 2 and quotes[1]["stop_at_map_boundary"] is True
    assert quotes[1]["allow_surf"] is True and actions.actions_executed == 0


@pytest.mark.parametrize("tamper", ["item", "event", "chapter", "state"])
def test_verifier_refuses_fake_success(monkeypatch, tamper):
    rt, actions, route, actor, raw, lesson, state, *_ = setup(monkeypatch)
    binding, _ = s.silph_card_key_story_option(rt, actions, None, route=route, battler=actor)
    report = binding.execute()
    if tamper == "item":
        raw.bag_items = ()
    elif tamper == "event":
        raw.defeated = False
    elif tamper == "chapter":
        lesson["completed_objectives"].append("liberate_silph")
    else:
        state[0] = b"changed"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_lost_is_resource_failure_not_fallback(monkeypatch):
    rt, actions, route, actor, *_ = setup(monkeypatch)
    monkeypatch.setattr(
        s,
        "run_learned_silph_card_key_phase",
        lambda *a, **kw: dict(status="lost", card_key_acquired=False),
    )
    binding, _ = s.silph_card_key_story_option(rt, actions, None, route=route, battler=actor)
    report = binding.execute()
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST


def test_changed_actor_and_stale_source_rejected_before_input(monkeypatch):
    rt, actions, route, actor, raw, lesson, state, *_ = setup(monkeypatch)
    selected = [actor]
    binding, _ = s.silph_card_key_story_option(
        rt, actions, None, route=route, battler=actor, battler_for_contract=lambda _: selected[0]
    )
    selected[0] = object()
    with pytest.raises(ValueError, match="actor changed"):
        binding.execute()
    state[0] = b"stale"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert actions.actions_executed == 0


def test_surf_flag_requires_matching_executor_before_observation():
    with pytest.raises(ValueError, match="Surf-enabled"):
        s.silph_card_key_story_option(
            None, None, None, route=N(allow_surf=False), battler=None, allow_surf=True
        )
