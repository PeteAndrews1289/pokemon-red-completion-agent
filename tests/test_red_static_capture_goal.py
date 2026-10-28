from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import ItemId, RawGameState
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget
from pokemon_red_completion.red_static_capture_goal import RedStaticCaptureGoalProvider

TARGET = RedStaticCaptureTarget(145, 75, 50, 83, 9, 9, (9, 4), 1129)


def fixture(monkeypatch, tmp_path):
    import pokemon_red_completion.red_static_capture_goal as m

    raw = RawGameState(
        True,
        83,
        4,
        10,
        1,
        0,
        party_species_ids=(28,),
        bag_items=((1, 1), (3, 20)),
        player_money=30000,
        event_flags=bytes(320),
    )
    w = NS(
        raw=raw,
        owned=frozenset({9}),
        actions_executed=0,
        frame_count=0,
        pressed_buttons=frozenset(),
        visible=True,
    )
    w.read = lambda: w.raw
    w.observe = lambda: NS(raw=w.raw, input_ready=True)
    w.read_pokedex_state = lambda: NS(owned_species=w.owned)
    w.read_all_box_states = lambda: NS(boxes=(NS(species_ids=()),))
    w.read_current_map_objects = lambda: (NS(sprite_index=9, visible=True),) if w.visible else ()
    w.save_state_bytes = lambda: repr((w.raw, w.frame_count)).encode()
    monkeypatch.setattr(m, "red_static_capture_targets", lambda _: (TARGET,))
    monkeypatch.setattr(m, "require_static_capture_admission", lambda *a, **k: None)

    def capture(*args, budget, commit_throw, **kwargs):
        budget.throws_committed = 1
        commit_throw(budget)
        assert len(tuple((tmp_path / "capture").glob("*/receipt.json"))) == 2
        flags = bytearray(320)
        flags[1129 // 8] |= 1 << (1129 % 8)
        w.raw = replace(
            w.raw, party_species_ids=(28, 75), bag_items=((3, 20),), event_flags=bytes(flags)
        )
        w.actions_executed = 10
        w.frame_count = 120
        w.owned |= {145}
        w.visible = False
        return NS(captured=True, consumed_event=True, source_removed=True)

    monkeypatch.setattr(m, "execute_static_capture", capture)
    p = RedStaticCaptureGoalProvider(
        b"rom", TARGET, ItemId.MASTER_BALL, 1, w, w, w, w, tmp_path / "capture"
    )
    return w, p


def test_offer_is_read_only_and_execution_has_write_ahead_receipts(monkeypatch, tmp_path):
    w, p = fixture(monkeypatch, tmp_path)
    before = w.save_state_bytes()
    binding = p.offer(w.observe()).binding
    assert binding and not list(tmp_path.iterdir()) and w.save_state_bytes() == before
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert report.evidence["learned_ball_selection"] is False
    assert len(report.evidence["receipts"]) == 3
    assert (tmp_path / "capture/002-settled/receipt.json").exists()
    with pytest.raises(RuntimeError, match="already attempted"):
        binding.execute()


def test_declared_prepared_helper_changes_bound_configuration_without_discovery_input(monkeypatch,tmp_path):
    world,provider=fixture(monkeypatch,tmp_path)
    provider=replace(provider,require_status_success=True)
    prepared=replace(provider,minimum_prepared_helper_level=55)
    assert prepared.configuration_sha256!=provider.configuration_sha256
    assert prepared.offer(world.observe()).binding is not None and not list(tmp_path.iterdir())
    with pytest.raises(ValueError,match='prepared helper'):
        replace(prepared,require_status_success=False)
    with pytest.raises(ValueError,match='prepared helper'):
        replace(prepared,minimum_prepared_helper_level=0)


@pytest.mark.parametrize("fault", ["state", "frames", "actions", "observation"])
def test_changed_source_cannot_execute_stale_model_binding(monkeypatch, tmp_path, fault):
    w, p = fixture(monkeypatch, tmp_path)
    binding = p.offer(w.observe()).binding
    if fault == "state":
        w.raw = replace(w.raw, player_money=1)
    if fault == "frames":
        w.frame_count = 1
    if fault == "actions":
        w.actions_executed = 1
    if fault == "observation":
        w.observe = lambda: NS(raw=w.raw, input_ready=False)
    with pytest.raises(RuntimeError, match="source changed"):
        binding.execute()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault", ["object", "flag", "owned", "specimen", "bag", "money", "battle", "report"]
)
def test_independent_verifier_rejects_false_capture_claim(monkeypatch, tmp_path, fault):
    w, p = fixture(monkeypatch, tmp_path)
    binding = p.offer(w.observe()).binding
    report = binding.execute()
    if fault == "object":
        w.visible = True
    if fault == "flag":
        w.raw = replace(w.raw, event_flags=bytes(320))
    if fault == "owned":
        w.owned = frozenset({9})
    if fault == "specimen":
        w.raw = replace(w.raw, party_species_ids=(28,))
    if fault == "bag":
        w.raw = replace(w.raw, bag_items=((1, 1), (3, 20)))
    if fault == "money":
        w.raw = replace(w.raw, player_money=1)
    if fault == "battle":
        w.raw = replace(w.raw, battle_state=1)
    if fault == "report":
        report = replace(report)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_execution_failure_retains_paused_state_and_spent_intent(monkeypatch, tmp_path):
    import pokemon_red_completion.red_static_capture_goal as m

    w, p = fixture(monkeypatch, tmp_path)

    def fail(*a, budget, commit_throw, **k):
        budget.throws_committed = 1
        commit_throw(budget)
        raise RuntimeError("interrupted throw")

    monkeypatch.setattr(m, "execute_static_capture", fail)
    binding = p.offer(w.observe()).binding
    with pytest.raises(RuntimeError, match="interrupted throw"):
        binding.execute()
    import json

    receipt = json.loads((tmp_path / "capture/002-paused/receipt.json").read_bytes())
    assert receipt["budget"]["throws_committed"] == 1
    assert receipt["parent_receipt_sha256"]
    assert p.offer(w.observe()).binding is None


@pytest.mark.parametrize("status", [None, 0, 8, 16])
@pytest.mark.parametrize("weakening", [False, True])
def test_required_status_stops_before_ball_intent(monkeypatch, tmp_path, status, weakening):
    import json

    import pokemon_red_completion.red_static_capture_goal as m

    w, p = fixture(monkeypatch, tmp_path)
    p = replace(
        p,
        ball=ItemId.GREAT_BALL,
        max_throws=20,
        require_status_success=True,
        weaken_capture=weakening,
    )
    w.read_enemy_capture_status = lambda: status
    monkeypatch.setattr(m.RedCaptureStatusPreparer, "__call__", lambda _: True)

    def capture(*args, before_throw, prepare_encounter, **kwargs):
        if weakening:
            prepare_encounter()
        else:
            before_throw()
        pytest.fail("unprepared target reached ball execution")

    monkeypatch.setattr(m, "execute_static_capture", capture)
    with pytest.raises(m.OneOffCapturePaused, match="no ball spent"):
        p.offer(w.observe()).binding.execute()
    receipt = json.loads((tmp_path / "capture/001-paused/receipt.json").read_bytes())
    assert receipt["budget"]["throws_committed"] == 0


def test_required_status_is_explicit_and_configuration_bound(monkeypatch, tmp_path):
    _, p = fixture(monkeypatch, tmp_path)
    assert replace(p, require_status_success=True).configuration_sha256 != p.configuration_sha256
    with pytest.raises(ValueError, match="needs status"):
        replace(p, require_status_success=True, prepare_status=False)
    with pytest.raises(ValueError, match="explicit"):
        replace(p, require_status_success=1)
