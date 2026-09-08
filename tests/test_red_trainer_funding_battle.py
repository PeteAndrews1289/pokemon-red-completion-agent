from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_trainer_funding_battle as funding_battle
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.observation import InputReadiness, RawGameState
from pokemon_red_completion.red_trainer_funding import TrainerFundingCandidate
from pokemon_red_completion.red_trainer_funding_battle import (
    TrainerFundingBattleError,
    TrainerFundingBattleReceipt,
    run_prepared_trainer_funding,
)


@dataclass
class ScriptedEnvironment:
    state: RawGameState
    dialogue: bool = False
    ready: bool = True
    facing: str = "up"
    battle_identity: tuple[int, int, int, int] = (201, 1, 201, 9)
    pending_identity: tuple[int, int] | None = None
    trainer_number: int = 9

    def __post_init__(self) -> None:
        self.actions: list[MacroAction] = []
        self.transitions: list[tuple[RawGameState, bool, bool]] = []

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is not MacroActionKind.WAIT and self.transitions:
            self.state, self.dialogue, self.ready = self.transitions.pop(0)

    def read(self) -> RawGameState:
        return self.state

    def read_battle_menu_state(self, raw: RawGameState):
        return SimpleNamespace(phase=funding_battle.BattleMenuPhase.MAIN)

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)

    def read_player_facing(self) -> str:
        return self.facing

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.dialogue

    def read_trainer_battle_identity(self) -> tuple[int, int, int, int]:
        return self.battle_identity

    def read_active_trainer_identity(self) -> tuple[int, int, int]:
        return (*self.battle_identity[:2], self.trainer_number)

    def read_pending_trainer_battle_identity(self) -> tuple[int, int] | None:
        return self.pending_identity if self.state.battle_state == 0 else None


def make_flag_bytes(bit: int) -> bytes:
    flags = bytearray(b"\x00" * 200)
    flags[bit // 8] |= 1 << (bit % 8)
    return bytes(flags)


def make_candidate(
    *,
    tc: int = 201,
    ts: int = 9,
    flag: int = 1139,
    defn: bool = False,
    at: tuple[int, int] = (3, 4),
    face: TrainerFacing = TrainerFacing.UP,
    qc: int | None = None,
    qs: int | None = None,
    pay: int = 315,
    party: tuple[TrainerPartyMember, ...] | None = None,
) -> TrainerFundingCandidate:
    trainer = TrainerSightZone(22, 3, tc, ts, (2, 4), TrainerFacing.DOWN, 3, flag, defn, True)
    members = party if party is not None else (TrainerPartyMember(108, 23, 21),)
    quote = TrainerPartyQuote(qc or tc, qs or ts, members, 15, pay)
    return TrainerFundingCandidate(trainer, quote, SimpleNamespace(terminal_at=at), face)


def make_state(
    *,
    map_id: int = 22,
    yx: tuple[int, int] = (3, 4),
    battle_state: int = 0,
    battle_result: int = 0,
    flags: bytes = b"\x00" * 200,
    sp: tuple[int, ...] = (25, 1),
    hp: tuple[int, ...] = (50, 40),
    money: int = 500,
    bag: tuple[tuple[int, int], ...] = ((1, 5),),
    moves: tuple[int, ...] | None = (33, 40),
    pp: tuple[int, ...] | None = (35, 30),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=yx[1],
        player_y=yx[0],
        party_count=len(sp),
        battle_state=battle_state,
        battle_result=battle_result,
        event_flags=flags,
        party_species_ids=sp,
        party_hp=hp,
        bag_items=bag,
        player_money=money,
        active_party_moves=moves,
        active_party_pp=pp,
    )


TIMING = BattleRuntimeTiming(dialogue_wait_frames=5)


@pytest.mark.parametrize("bag,allowed", [
    (((16, 3), (53, 3)), True), (((16, 2), (53, 3)), True),
    (((16, 1), (53, 3)), False), (((16, 3), (53, 2)), False),
])
def test_explicit_recovery_item_budget_survives_outer_victory_verification(bag, allowed):
    env = ScriptedEnvironment(make_state(battle_state=2, bag=((16, 4), (53, 3))))
    def finish(reader, _executor, _policy, **kwargs):
        env.state = replace(reader.read(), bag_items=bag)
        kwargs["move_decision_guard"](env.state)
        env.state = replace(env.state, battle_state=0, player_money=815,
                            event_flags=make_flag_bytes(1139))
        return env.state
    def execute():
        return run_prepared_trainer_funding(
            env, env, target=make_candidate(), validate_target=lambda: None,
            move_slot_policy=lambda _: 1, timing=TIMING, resume_active_battle=True,
            battle_runner_override=finish, maximum_full_restores=2,
        )
    if allowed:
        assert execute().final_state.bag_items == bag
    else:
        with pytest.raises(TrainerFundingBattleError, match="budget"):
            execute()
    assert not env.actions


def test_ordinary_battle_cannot_inherit_a_recovery_item_budget():
    env = ScriptedEnvironment(make_state(bag=((16, 4),)))
    with pytest.raises(ValueError, match="explicit active-battle"):
        run_prepared_trainer_funding(
            env, env, target=make_candidate(), validate_target=lambda: None,
            move_slot_policy=lambda _: 1, timing=TIMING, maximum_full_restores=2,
        )
    assert not env.actions


@pytest.mark.parametrize("already_pending", [False, True])
def test_armed_intro_waits_without_reinteracting_or_confirming(monkeypatch, already_pending):
    class PendingEnvironment(ScriptedEnvironment):
        def execute(self, action):
            self.actions.append(action)
            if action.kind is MacroActionKind.INTERACT:
                assert self.pending_identity is None
                self.dialogue = True
            elif action.kind is MacroActionKind.CONFIRM:
                assert self.pending_identity is None and self.dialogue
                self.dialogue = False
                self.pending_identity = (201, 9)
                self.pending_waits = 0
            elif action.kind is MacroActionKind.WAIT and self.pending_identity:
                self.pending_waits += 1
                if self.pending_waits == 2:
                    self.state = replace(self.state, battle_state=2)
                    self.pending_identity = None

    env = PendingEnvironment(make_state(), pending_identity=(201, 9) if already_pending else None)
    env.pending_waits = 0

    def finish(reader, *_args, **kwargs):
        assert reader.read().battle_state == 2
        kwargs["move_decision_guard"](reader.read())
        env.state = replace(
            env.state, battle_state=0, player_money=815, event_flags=make_flag_bytes(1139)
        )
        return env.state

    monkeypatch.setattr(funding_battle, "battle_runner", finish)
    receipt = run_prepared_trainer_funding(
        env,
        env,
        target=make_candidate(),
        validate_target=lambda: None,
        move_slot_policy=lambda _: 1,
        timing=TIMING,
    )
    assert receipt.payout == 315
    buttons = [a.kind for a in env.actions if a.kind is not MacroActionKind.WAIT]
    assert buttons == (
        [] if already_pending else [MacroActionKind.INTERACT, MacroActionKind.CONFIRM]
    )


@pytest.mark.parametrize("already_pending", [False, True])
def test_armed_transition_with_visible_dialogue_requires_confirmation(monkeypatch, already_pending):
    class PendingDialogueEnvironment(ScriptedEnvironment):
        def execute(self, action):
            self.actions.append(action)
            if action.kind is MacroActionKind.INTERACT:
                assert self.pending_identity is None
                self.pending_identity = (201, 9)
                self.dialogue = True
            elif action.kind is MacroActionKind.CONFIRM:
                assert self.pending_identity == (201, 9) and self.dialogue
                self.dialogue = False
            elif (
                action.kind is MacroActionKind.WAIT and self.pending_identity and not self.dialogue
            ):
                self.state = replace(self.state, battle_state=2)
                self.pending_identity = None

    env = PendingDialogueEnvironment(make_state(), dialogue=already_pending,
                                    pending_identity=(201, 9) if already_pending else None)

    def finish(reader, *_args, **kwargs):
        assert reader.read().battle_state == 2
        kwargs["move_decision_guard"](reader.read())
        env.state = replace(env.state, battle_state=0, player_money=815,
                            event_flags=make_flag_bytes(1139))
        return env.state

    monkeypatch.setattr(funding_battle, "battle_runner", finish)
    result = run_prepared_trainer_funding(env, env, target=make_candidate(),
        validate_target=lambda: None, move_slot_policy=lambda _: 1, timing=TIMING)
    assert result.payout == 315
    buttons = [a.kind for a in env.actions if a.kind is not MacroActionKind.WAIT]
    assert buttons == ([MacroActionKind.CONFIRM] if already_pending else
                       [MacroActionKind.INTERACT, MacroActionKind.CONFIRM])


def test_wrong_pending_dialogue_identity_cannot_be_confirmed():
    env = ScriptedEnvironment(make_state(), dialogue=True, pending_identity=(201, 10))
    with pytest.raises(TrainerFundingBattleError, match="pending trainer identity"):
        run_prepared_trainer_funding(env, env, target=make_candidate(),
            validate_target=lambda: None, move_slot_policy=lambda _: 1, timing=TIMING)
    assert env.actions == []


def test_stuck_pending_transition_consumes_only_exact_bounded_waits():
    env = ScriptedEnvironment(make_state(), pending_identity=(201, 9))
    with pytest.raises(TrainerFundingBattleError, match="exhausted intro"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda _: 1,
            timing=TIMING,
            maximum_intro_pulses=3,
        )
    assert env.actions == [MacroAction(MacroActionKind.WAIT, repeat=5)] * 3


def test_wrong_pending_identity_rejects_before_any_input():
    env = ScriptedEnvironment(make_state(), pending_identity=(201, 10))
    with pytest.raises(TrainerFundingBattleError, match="pending trainer identity"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda _: 1,
            timing=TIMING,
        )
    assert not env.actions


@pytest.mark.parametrize("wrong_number", [False, True])
def test_active_battle_recovery_checks_stable_number_not_enemy_stat_union(
    monkeypatch, wrong_number
):
    env = ScriptedEnvironment(
        make_state(battle_state=2),
        battle_identity=(201, 1, 19, 7),
        trainer_number=10 if wrong_number else 9,
    )

    def finish(reader, executor, policy, **kwargs):
        kwargs["move_decision_guard"](reader.read())
        assert policy(reader.read()) == 1
        env.battle_identity = (201, 1, 40, 6)
        kwargs["move_decision_guard"](reader.read())
        env.state = replace(
            env.state, battle_state=0, player_money=815, event_flags=make_flag_bytes(1139)
        )
        return env.state

    monkeypatch.setattr(funding_battle, "battle_runner", finish)

    def run():
        return run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda _: 1,
            timing=TIMING,
            resume_active_battle=True,
        )

    if wrong_number:
        with pytest.raises(TrainerFundingBattleError, match="active battle identity"):
            run()
    else:
        assert run().payout == 315
    assert not env.actions


def test_prepared_trainer_funding_success(monkeypatch: pytest.MonkeyPatch) -> None:
    init = make_state(money=500)
    battle = make_state(battle_state=2, money=500)
    post_dialogue = make_state(battle_state=0, money=815, flags=make_flag_bytes(1139))
    settled = make_state(battle_state=0, money=815, flags=make_flag_bytes(1139))

    env = ScriptedEnvironment(init, dialogue=False, ready=True)
    # INTERACT -> intro dialogue; CONFIRM -> battle; CONFIRM postbattle -> settled
    env.transitions = [
        (init, True, False),
        (battle, False, True),
        (settled, False, True),
    ]

    def fake_battle_runner(r, e, pol, **kw):
        kw["move_decision_guard"](r.read())
        assert pol(r.read()) == 1
        env.state, env.dialogue, env.ready = post_dialogue, True, False
        return post_dialogue

    monkeypatch.setattr(funding_battle, "battle_runner", fake_battle_runner)
    receipt = run_prepared_trainer_funding(
        env,
        env,
        target=make_candidate(),
        validate_target=lambda: None,
        move_slot_policy=lambda r: 1,
        timing=TIMING,
    )
    assert isinstance(receipt, TrainerFundingBattleReceipt)
    assert (receipt.initial_money, receipt.final_money, receipt.payout) == (500, 815, 315)
    assert MacroAction(MacroActionKind.INTERACT) in env.actions


def test_initial_stale_target_callback_fails_closed() -> None:
    env = ScriptedEnvironment(make_state())

    def stale_validate():
        raise RuntimeError("stale target binding")

    with pytest.raises(RuntimeError, match="stale target"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=stale_validate,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )
    assert not env.actions


def test_target_quote_identity_mismatch_raises() -> None:
    env = ScriptedEnvironment(make_state())
    with pytest.raises(ValueError, match="target quote identity"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(qc=202),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_defeated_flag_already_set_raises() -> None:
    env1 = ScriptedEnvironment(make_state())
    with pytest.raises(TrainerFundingBattleError, match="already marked defeated"):
        run_prepared_trainer_funding(
            env1,
            env1,
            target=make_candidate(defn=True),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )
    env2 = ScriptedEnvironment(make_state(flags=make_flag_bytes(1139)))
    with pytest.raises(TrainerFundingBattleError, match="already set"):
        run_prepared_trainer_funding(
            env2,
            env2,
            target=make_candidate(flag=1139),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


@pytest.mark.parametrize(
    "env_kw,state_kw,match",
    [
        ({"facing": "down"}, {}, "player facing"),
        ({}, {"yx": (5, 5)}, "player position"),
        ({}, {"map_id": 10}, "initial map"),
        ({"ready": False}, {}, "initial input readiness"),
        ({"dialogue": True}, {}, "dialogue box is visible"),
    ],
)
def test_wrong_facing_location_or_readiness_raises(env_kw, state_kw, match) -> None:
    env = ScriptedEnvironment(make_state(**state_kw), **env_kw)
    with pytest.raises(TrainerFundingBattleError, match=match):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_wild_intrusion_and_identity_mismatch_raises() -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=1), False, True)]
    with pytest.raises(TrainerFundingBattleError, match="wild battle"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )

    env_id = ScriptedEnvironment(make_state(), battle_identity=(205, 5, 205, 1))
    env_id.transitions = [(make_state(battle_state=2), False, True)]
    with pytest.raises(TrainerFundingBattleError, match="identity"):
        run_prepared_trainer_funding(
            env_id,
            env_id,
            target=make_candidate(tc=201, ts=9),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


@pytest.mark.parametrize(
    "key,val,match",
    [
        ("party_species_ids", None, "party_species_ids"),
        ("party_hp", None, "party_hp"),
        ("party_count", None, "party_count"),
        ("player_money", None, "player_money"),
        ("bag_items", None, "bag_items"),
    ],
)
def test_missing_party_or_money_raises(key, val, match) -> None:
    init = make_state()
    object.__setattr__(init, key, val)
    env = ScriptedEnvironment(init)
    with pytest.raises(TrainerFundingBattleError, match=match):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_party_faint_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state(hp=(0, 40)))
    with pytest.raises(TrainerFundingBattleError, match="fainted"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )

    env_battle = ScriptedEnvironment(make_state())
    env_battle.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: kw["move_decision_guard"](make_state(battle_state=2, hp=(0, 40))),
    )
    with pytest.raises(TrainerFundingBattleError, match="fainted"):
        run_prepared_trainer_funding(
            env_battle,
            env_battle,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


@pytest.mark.parametrize(
    "runner_fn,match",
    [
        (
            lambda r, e, p, **kw: make_state(bag=((2, 1),), flags=make_flag_bytes(1139), money=815),
            "bag items mutated",
        ),
        (lambda r, e, p, **kw: make_state(money=600, flags=make_flag_bytes(1139)), "player money"),
        (
            lambda r, e, p, **kw: make_state(
                battle_result=1, money=815, flags=make_flag_bytes(1139)
            ),
            "victory",
        ),
        (
            lambda r, e, p, **kw: make_state(battle_result=0, money=815, flags=b"\x00" * 200),
            "event flag",
        ),
    ],
)
def test_postbattle_outcomes_rejected(monkeypatch: pytest.MonkeyPatch, runner_fn, match) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(funding_battle, "battle_runner", runner_fn)
    with pytest.raises(TrainerFundingBattleError, match=match):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_avoid_confirm_spam_in_ready_dialogue_free_intro() -> None:
    env = ScriptedEnvironment(make_state(), dialogue=False, ready=True)
    # INTERACT executes, but state remains overworld with no dialogue and ready input
    with pytest.raises(TrainerFundingBattleError, match="no dialogue or battle"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )
    assert env.actions == [
        MacroAction(MacroActionKind.INTERACT),
        MacroAction(MacroActionKind.WAIT, repeat=TIMING.dialogue_wait_frames),
    ]


def test_bounded_intro_and_settle_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    env_intro = ScriptedEnvironment(make_state())
    # INTERACT -> dialogue True, but CONFIRMs never enter battle
    env_intro.transitions = [(make_state(), True, False) for _ in range(5)]
    with pytest.raises(TrainerFundingBattleError, match="exhausted intro pulses"):
        run_prepared_trainer_funding(
            env_intro,
            env_intro,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
            maximum_intro_pulses=2,
        )

    env_settle = ScriptedEnvironment(make_state())
    env_settle.transitions = [(make_state(battle_state=2), False, True)]
    post_overworld = make_state(battle_state=0, money=815, flags=make_flag_bytes(1139))

    def fake_runner(r, e, p, **kw):
        env_settle.state, env_settle.dialogue, env_settle.ready = post_overworld, True, False
        return post_overworld

    monkeypatch.setattr(funding_battle, "battle_runner", fake_runner)
    with pytest.raises(TrainerFundingBattleError, match="exhausted settle pulses"):
        run_prepared_trainer_funding(
            env_settle,
            env_settle,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
            maximum_settle_pulses=2,
        )


def test_multi_pokemon_trainer_identity_remains_same(monkeypatch: pytest.MonkeyPatch) -> None:
    party = (
        TrainerPartyMember(108, 23, 21),
        TrainerPartyMember(109, 24, 21),
        TrainerPartyMember(110, 25, 22),
    )
    candidate = make_candidate(party=party, pay=660)
    init = make_state(money=100)
    battle = make_state(battle_state=2, money=100)
    post = make_state(battle_state=0, money=760, flags=make_flag_bytes(1139))

    env = ScriptedEnvironment(init)
    env.transitions = [(battle, False, True)]

    def multi_turn_runner(r, e, pol, **kw):
        guard = kw["move_decision_guard"]
        for opponent in (108, 109, 110):
            env.state = replace(env.state, enemy_species_id=opponent)
            guard(r.read())
            assert r.read_trainer_battle_identity() == (201, 1, 201, 9)
            assert pol(r.read()) == 1
        env.state, env.dialogue, env.ready = post, False, True
        return post

    monkeypatch.setattr(funding_battle, "battle_runner", multi_turn_runner)
    receipt = run_prepared_trainer_funding(
        env,
        env,
        target=candidate,
        validate_target=lambda: None,
        move_slot_policy=lambda r: 1,
        timing=TIMING,
    )
    assert receipt.payout == 660


def test_identity_change_between_moves_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]

    def changing_runner(r, e, pol, **kw):
        kw["move_decision_guard"](r.read())
        env.battle_identity = (205, 5, 205, 1)
        kw["move_decision_guard"](r.read())

    monkeypatch.setattr(funding_battle, "battle_runner", changing_runner)
    with pytest.raises(TrainerFundingBattleError, match="identity"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_short_or_empty_hp_arrays_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state(sp=(25, 1), hp=(50,)))  # 1 HP for 2 mon
    with pytest.raises(TrainerFundingBattleError, match="party_hp"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )

    env2 = ScriptedEnvironment(make_state())
    env2.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: kw["move_decision_guard"](
            make_state(battle_state=2, sp=(25, 1), hp=(50,))
        ),
    )
    with pytest.raises(TrainerFundingBattleError, match="party HP"):
        run_prepared_trainer_funding(
            env2,
            env2,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_unreadable_moves_or_pp_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: pol(make_state(battle_state=2, moves=None)),
    )
    with pytest.raises(TrainerFundingBattleError, match="moves unreadable"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )

    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: pol(make_state(battle_state=2, pp=None)),
    )
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    with pytest.raises(TrainerFundingBattleError, match="PP unreadable"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


@pytest.mark.parametrize("invalid_slot", [0, 3, True, False, "1"])
def test_invalid_or_boolean_policy_slot_raises(
    monkeypatch: pytest.MonkeyPatch, invalid_slot
) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: pol(make_state(battle_state=2, moves=(33, 40))),
    )
    with pytest.raises(TrainerFundingBattleError, match="invalid slot"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: invalid_slot,
            timing=TIMING,
        )


def test_guard_rejects_battle_state_not_2(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: kw["move_decision_guard"](make_state(battle_state=0)),
    )
    with pytest.raises(TrainerFundingBattleError, match="must be 2"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_pay_day_move_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ScriptedEnvironment(make_state())
    env.transitions = [(make_state(battle_state=2), False, True)]
    monkeypatch.setattr(
        funding_battle,
        "battle_runner",
        lambda r, e, pol, **kw: pol(make_state(battle_state=2, moves=(6, 33))),
    )
    with pytest.raises(TrainerFundingBattleError, match="Pay Day"):
        run_prepared_trainer_funding(
            env,
            env,
            target=make_candidate(),
            validate_target=lambda: None,
            move_slot_policy=lambda r: 1,
            timing=TIMING,
        )


def test_capped_money_999999(monkeypatch: pytest.MonkeyPatch) -> None:
    init = make_state(money=999900)
    battle = make_state(battle_state=2, money=999900)
    final = make_state(battle_state=0, money=999999, flags=make_flag_bytes(1139))
    env = ScriptedEnvironment(init)
    env.transitions = [(battle, False, True)]

    def fake_runner(r, e, pol, **kw):
        env.state, env.dialogue, env.ready = final, False, True
        return final

    monkeypatch.setattr(funding_battle, "battle_runner", fake_runner)
    receipt = run_prepared_trainer_funding(
        env,
        env,
        target=make_candidate(pay=315),
        validate_target=lambda: None,
        move_slot_policy=lambda r: 1,
        timing=TIMING,
    )
    assert receipt.initial_money == 999900
    assert receipt.final_money == 999999
    assert receipt.payout == 99


@pytest.mark.parametrize("bad_pulse", [0, -1, True, False, "5"])
def test_invalid_pulse_parameters_rejected(bad_pulse) -> None:
    for param in ("maximum_intro_pulses", "maximum_settle_pulses"):
        with pytest.raises((ValueError, TypeError)):
            run_prepared_trainer_funding(
                ScriptedEnvironment(make_state()),
                ScriptedEnvironment(make_state()),
                target=make_candidate(),
                validate_target=lambda: None,
                move_slot_policy=lambda r: 1,
                timing=TIMING,
                **{param: bad_pulse},
            )
