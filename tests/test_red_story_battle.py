from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_trainer_battle_lifecycle import fixture

from pokemon_red_completion import red_story_battle as story
from pokemon_red_completion.red_learned_trainer import (
    ADDITIVE_STORY_ADMISSION_SHA256,
    ADDITIVE_STORY_SHA256,
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
    load_story_trainer_model,
    qualified_party_limit,
    story_party_limit,
)
from pokemon_red_completion.red_trainer_battle_lifecycle import TrainerBattleLifecycleError


def actor(tmp_path):
    return FrozenTrainerBattler(
        None,
        None,
        tmp_path,
        "a" * 40,
        "root",
        "b" * 64,
        {},
        model_sha256=FROZEN_K_SHA256,
        qualification_sha256=K_QUALIFICATION_SHA256,
    )


def contract(map_id=61):
    return story.StoryTrainerContract("story", "trainer-one", map_id, (230, 30, 4), 8, 480)


def test_preparation_review_failure_is_not_swallowed(monkeypatch, tmp_path):
    _, reader, _, actions = fixture("won")
    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(story, "continue_learned_trainer_battle", lambda *a, **k: object())

    def fail(result):
        raise RuntimeError("review unavailable")

    controller = story.FrozenStoryBattleController(
        actor(tmp_path), (contract(),), preparation_review=fail
    )
    with pytest.raises(RuntimeError, match="review unavailable"):
        controller.run(
            reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=61
        )


@pytest.mark.parametrize("outcome", ["won", "lost", "unresolved"])
def test_post_battle_review_runs_once_without_replacing_result(monkeypatch, tmp_path, outcome):
    _, reader, _, actions = fixture(outcome)
    result = NS(outcome=outcome)
    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(story, "continue_learned_trainer_battle", lambda *a, **k: result)
    seen = []
    controller = story.FrozenStoryBattleController(
        actor(tmp_path), (contract(),), preparation_review=seen.append
    )
    assert (
        controller.run(
            reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=61
        )
        is result
    )
    assert seen == [result]


@pytest.mark.parametrize("outcome", ["won", "lost", "unresolved"])
@pytest.mark.parametrize("map_id", [61, 210, 178])
def test_declared_story_boundary_reuses_exact_win_loss_preservation(
    monkeypatch,
    tmp_path,
    outcome,
    map_id,
):
    state, reader, fake, actions = fixture(outcome)
    state.raw = replace(state.raw, map_id=map_id)
    battler = actor(tmp_path)
    # Reuse the lifecycle fixture's checked native-state transitions.
    original = fake.continue_battle

    def play(reader, actions, **kwargs):
        assert kwargs.pop("story_authority") is True
        assert kwargs["maximum_decisions"] == 73
        # Its immutable fixture baseline has map61; only the outer contract's
        # varied-map match is under test in the other rows.
        if map_id != 61:
            return NS(battle_won=False, stop_reason="decision_budget")
        return original(reader, actions, **kwargs)

    battler.continue_battle = play
    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    controller = story.FrozenStoryBattleController(battler, (contract(map_id),), 73)
    result = controller.run(
        reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=map_id
    )
    assert result.outcome == (outcome if map_id == 61 else "unresolved")


@pytest.mark.parametrize(
    "fault",
    [
        "bag",
        "party",
        "money",
        "hp",
        "map",
        "status",
        "payout",
        "event",
        "blackout_map",
        "blackout_money",
    ],
)
def test_story_interface_preserves_lifecycle_failure_checks(monkeypatch, tmp_path, fault):
    _, reader, fake, actions = fixture("lost" if fault.startswith("blackout") else "won", fault)
    battler = actor(tmp_path)
    battler.continue_battle = fake.continue_battle
    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    with pytest.raises(TrainerBattleLifecycleError):
        story.FrozenStoryBattleController(battler, (contract(),)).run(
            reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=61
        )


@pytest.mark.parametrize(
    "fault", ["objective", "plan", "map", "identity", "event", "actor", "receipt"]
)
def test_wrong_scope_refuses_before_any_input_or_policy(monkeypatch, tmp_path, fault):
    state, reader, _, actions = fixture()
    battler = actor(tmp_path)
    if fault == "actor":
        battler.model_sha256 = "c" * 64
    if fault == "receipt":
        battler.qualification_sha256 = None
    if fault == "identity":
        reader.read_active_trainer_identity = lambda: (230, 30, 5)
    if fault == "event":
        state.raw = replace(state.raw, event_flags=bytes((0, 1, 0, 0)))
    monkeypatch.setattr(
        story,
        "advance_battle_to_policy_boundary",
        lambda *a, **k: pytest.fail("unowned entry input"),
    )
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(battler, (contract(),)).run(
            reader,
            actions,
            objective_id="wrong" if fault == "objective" else "story",
            battle_plan_id="wrong" if fault == "plan" else "trainer-one",
            expected_map=60 if fault == "map" else 61,
        )
    assert not state.actions


def test_intro_cannot_spend_resources_before_learning(monkeypatch, tmp_path):
    state, reader, _, actions = fixture()

    def advance(*a, **k):
        state.raw = replace(state.raw, player_money=0)

    monkeypatch.setattr(story, "advance_battle_to_policy_boundary", advance)
    with pytest.raises(ValueError, match="protected resources"):
        story.FrozenStoryBattleController(actor(tmp_path), (contract(),)).run(
            reader, actions, objective_id="story", battle_plan_id="trainer-one", expected_map=61
        )


@pytest.mark.parametrize(
    "change",
    [
        {"map_id": True},
        {"trainer_identity": (230, 29, 4)},
        {"trainer_identity": (230, 30, 0)},
        {"defeated_event": -1},
        {"victory_money": -1},
        {"objective_id": ""},
    ],
)
def test_invalid_contract_refuses(change):
    with pytest.raises(ValueError):
        replace(contract(), **change)


def test_authority_is_logged_as_story_and_requires_qualified_k(tmp_path, monkeypatch):
    battler = actor(tmp_path)
    seen = []
    monkeypatch.setattr(battler, "_play", lambda *a, **kw: seen.append(kw))
    kwargs = dict(
        expected_map=61,
        timing=None,
        decision_guard=lambda _: None,
        maximum_decisions=70,
        story_authority=True,
    )
    battler.continue_battle(None, None, **kwargs)
    assert seen[0]["authority"] == "frozen-k-story-development"
    assert seen[0]["maximum_decisions"] == 70 and not seen[0]["require_win"]
    battler.qualification_sha256 = None
    with pytest.raises(ValueError):
        battler.continue_battle(None, None, **kwargs)
    assert len(seen) == 1


def test_additive_admission_is_story_only_and_dispatches_explicitly(tmp_path, monkeypatch):
    battler = actor(tmp_path)
    battler.model_sha256 = ADDITIVE_STORY_SHA256
    battler.qualification_sha256 = ADDITIVE_STORY_ADMISSION_SHA256
    assert story_party_limit(battler.model_sha256, battler.qualification_sha256) == 6
    assert qualified_party_limit(battler.model_sha256, battler.qualification_sha256) == 0
    story.FrozenStoryBattleController(battler, (contract(),))
    calls = []
    monkeypatch.setattr(battler, "_play", lambda *a, **kw: calls.append(kw))
    battler.continue_battle(
        None,
        None,
        expected_map=61,
        timing=None,
        decision_guard=lambda _: None,
        story_authority=True,
    )
    assert calls[0]["authority"] == "frozen-additive-story-development"
    assert calls[0]["resume"] and not calls[0]["require_win"]
    battler.qualification_sha256 = K_QUALIFICATION_SHA256
    with pytest.raises(ValueError):
        story.FrozenStoryBattleController(battler, (contract(),))


def test_changed_story_checkpoint_or_admission_rejected():
    with pytest.raises(ValueError, match="exact checkpoint"):
        load_story_trainer_model(b"{}", b"{}")
    assert story_party_limit(ADDITIVE_STORY_SHA256, None) == 0
    assert story_party_limit(FROZEN_K_SHA256, ADDITIVE_STORY_ADMISSION_SHA256) == 0


def test_story_admission_receipt_is_exact_and_does_not_claim_screen_pass():
    import hashlib
    import json
    from pathlib import Path

    payload = (
        Path(__file__).parents[1] / "docs/evidence/red-additive-story-admission-2026-09-22.json"
    ).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == ADDITIVE_STORY_ADMISSION_SHA256
    receipt = json.loads(payload)
    assert receipt["model_sha256"] == ADDITIVE_STORY_SHA256
    assert receipt["original_screen_passed"] is False
    assert receipt["full_player_promoted"] is False


@pytest.mark.parametrize("count,defeated", [(1, False), (0, False), (2, False), (1, True)])
def test_cartridge_contract_requires_unique_undefeated_event(monkeypatch, count, defeated):
    zone = NS(event_flag=8, defeated=defeated, trainer_class=230, trainer_set=4)
    monkeypatch.setattr(story, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(story, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(story, "static_trainer_sight_zones", lambda *a: (zone,) * count)
    calls = []

    def quote(rom, opponent, trainer_set):
        calls.append((opponent, trainer_set))
        return NS(expected_victory_money=480)

    monkeypatch.setattr(story, "trainer_party_quote", quote)

    def derive():
        return story.StoryTrainerContract.from_cartridge(
            b"rom",
            NS(event_flags=bytes(4)),
            objective_id="story",
            battle_plan_id="trainer-one",
            map_id=61,
            defeated_event=8,
        )

    if count == 1 and not defeated:
        assert derive() == contract()
        assert calls == [(230, 4)]
    else:
        with pytest.raises(ValueError):
            derive()
        assert not calls
