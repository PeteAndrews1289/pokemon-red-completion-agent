from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_party_preparation as prep
from pokemon_red_completion import red_story_funding as funding
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.party_preparation import (
    ObservedOpponent,
    PreparationMember,
    PreparationPurpose,
    build_preparation_plan,
)
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)


def setup():
    members = tuple(
        PreparationMember(
            str(i),
            PartyMemberObservation(
                i, i, level, 50, 50, moves=(MoveObservation(33, 20),), experience=1000
            ),
            PreparationPurpose.COMBAT,
            "retained combat",
        )
        for i, level in enumerate((45, 22, 25), 1)
    )
    return members, build_preparation_plan(members, (ObservedOpponent("seen", 1, 37),))


@pytest.mark.parametrize("level,allowed", [(13, False), (14, True), (22, True), (23, False)])
def test_near_level_training_is_separate_from_funding(monkeypatch, level, allowed):
    members, plan = setup()
    candidate = NS(
        trainer=NS(defeated=False),
        quote=NS(party=(NS(level=level),), expected_money_after=lambda cash: cash + 100),
    )
    monkeypatch.setattr(prep, "center_trainer_candidates", lambda *a: (candidate,))
    assert bool(prep.preparation_trainer_candidates(b"", None, None, plan, members)) == allowed
    monkeypatch.setattr(funding, "center_trainer_candidates", lambda *a: (candidate,))
    reader = NS(read=lambda: NS(first_party_level=22, player_money=100))
    assert not funding.story_funding_candidates(b"", reader, None)


def test_no_damaging_move_or_ready_member_cannot_train(monkeypatch):
    members, plan = setup()
    member = replace(
        members[1], observation=replace(members[1].observation, moves=(MoveObservation(28, 20),))
    )
    assert not prep.preparation_trainer_candidates(
        b"", None, None, plan, (members[0], member, members[2])
    )
    ready = tuple(replace(m, observation=replace(m.observation, level=45)) for m in members)
    with pytest.raises(ValueError, match="targets reached"):
        prep.preparation_trainee(plan, ready)


@pytest.mark.parametrize("fault", [None, "battle", "heal", "swap", "stale", "actor", "depleted"])
def test_excursion_preserves_all_party_xp_and_failure_costs(monkeypatch, tmp_path, fault):
    members, plan = setup()
    monkeypatch.setattr(prep, "_raw_party_fully_restored", lambda _: fault != "depleted")
    monkeypatch.setattr(prep.RedTrainerEvolutionGuard, "from_rom", lambda *a: "guard")
    live = [members]
    raw = NS(player_money=1000)
    reader = NS(read=lambda: NS() if fault == "stale" else raw)
    emulator = NS(pressed_buttons=())
    actor = FrozenTrainerBattler(
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
    if fault == "actor":
        actor.qualification_sha256 = None
    target = NS(trainer=NS(map_id=22, event_flag=1), quote=NS(party=(NS(level=18),)))
    # Only replace route construction; execution must still bind exact actor/target.
    from dataclasses import dataclass

    from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition

    @dataclass(frozen=True)
    class Route:
        full_event_offsets: bool = False
        observe_terrain: bool = False
        excluded_maps: frozenset = frozenset()

    monkeypatch.setattr(RedVermilionGroundTransition, "from_rom", lambda _: Route())
    monkeypatch.setattr(prep, "observe_preparation_members", lambda *a: live[0])
    monkeypatch.setattr(prep, "preparation_trainer_candidates", lambda *a: (target,))
    spent = [0, 0]

    def swap(*args, **kwargs):
        spent[:] = [10, 100]
        if fault == "swap":
            raise RuntimeError("swap interrupted")
        a, b, c = live[0]
        live[0] = (
            replace(b, observation=replace(b.observation, slot=1)),
            replace(a, observation=replace(a.observation, slot=2)),
            c,
        )

    monkeypatch.setattr(prep, "swap_field_party_slots", swap)

    def excursion(**kwargs):
        assert kwargs["battler"] is actor and kwargs["target"] is target
        assert live[0][0].specimen_ref == "2"
        spent[:] = [50, 500]
        live[0] = tuple(
            replace(
                m,
                observation=replace(
                    m.observation,
                    experience=m.observation.experience + (100 if m.specimen_ref == "2" else 20),
                ),
            )
            for m in live[0]
        )
        if fault == "battle":
            raise RuntimeError("battle interrupted")
        kwargs["record"]("healing-started", {})
        if fault == "heal":
            raise RuntimeError("healing interrupted")
        return {"net_income": 100}

    monkeypatch.setattr(prep, "_execute_admitted_trainer_excursion", excursion)
    records = {}
    args = dict(
        rom=b"",
        reader=reader,
        emulator=emulator,
        actions=None,
        battler=actor,
        adapter=None,
        target=target,
        source_raw=raw,
        plan=plan,
        attempts=(),
        record=lambda k, v: records.__setitem__(k, v),
        cost_snapshot=lambda: tuple(spent),
        hideout_timing=None,
    )
    if fault:
        with pytest.raises((RuntimeError, ValueError)):
            prep.execute_preparation_excursion(**args)
    else:
        assert prep.execute_preparation_excursion(**args)["learned_preparation"] is False
    if fault in {"stale", "actor", "depleted"}:
        assert not records and spent == [0, 0]
    else:
        attempt = records["preparation-attempt"]["attempt"]
        assert attempt["failed"] is (fault is not None)
        assert attempt["actions"] == spent[0] and attempt["frames"] == spent[1]
        assert attempt["xp_gained"] == (0 if fault == "swap" else 100)
        assert attempt["heals"] == (0 if fault in {"swap", "battle"} else 1)
        assert len(records["preparation-attempt"]["party"]) == 3
