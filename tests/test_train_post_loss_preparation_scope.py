from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from test_party_preparation import enemies, team
from test_post_battle_strategy import aftermath
from pokemon_red_completion.party_preparation import PreparationPurpose, build_preparation_plan
from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.scenario_lab import ScenarioPartition
import pokemon_red_completion.red_player_member_preparation as subject


@dataclass(frozen=True)
class QuotedBinding:
    binding_ref: str


def setup_port(monkeypatch, levels=(36, 21, 22), purposes=None):
    members = tuple(replace(m, observation=replace(m.observation, experience=m.observation.level ** 3))
                    for m in team(*levels))
    if purposes:
        members = tuple(replace(m, purpose=p) for m, p in zip(members, purposes, strict=True))
    plan = build_preparation_plan(members, enemies(29))
    calls = []
    monkeypatch.setattr(subject, "observe_preparation_members", lambda *_: members)
    monkeypatch.setattr(subject, "internal_to_dex", lambda _: {i: i for i in range(1, 7)})
    monkeypatch.setattr(subject, "evolution_graph", lambda _: {})
    monkeypatch.setattr(subject, "RedPracticeCartridge", lambda _: SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda n: n ** 3)))
    def quote(runtime, actions, **kwargs):
        calls.append(kwargs)
        return QuotedBinding("test:existing-route")
    monkeypatch.setattr(subject, "routed_preparation_binding", quote)
    args = dict(plan=plan, opponent_levels=(29, 24, 29), forecast_ref="retained-observed-loss",
                home_map=134, route=SimpleNamespace(rom=b"test-only-no-cartridge"),
                reference_mode="strongest")
    return members, plan, calls, args


@pytest.mark.parametrize("partition", [ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT])
@pytest.mark.parametrize("gain", [1, 3])
def test_typed_learning_scopes_offer_each_eligible_post_loss_dose(monkeypatch, partition, gain):
    members, plan, calls, args = setup_port(monkeypatch)
    actor = SimpleNamespace(source_partition=partition)
    before = (plan, members)
    rows = subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args, battler=actor,
        maximum_level_gain=gain, allow_above_reference=True, observed_defeat=aftermath())
    assert len(rows) == len(calls) == 3
    assert [c["plan"].targets for c in calls] == [((m.specimen_ref, m.observation.level + gain),) for m in members]
    assert len({b.binding_ref for b, _ in rows}) == 3
    assert all(c["battler"] is actor and c["plan"].opposition_level == 29 for c in calls)
    assert all(descriptor.target_level - descriptor.current_level == gain for _, descriptor in rows)
    assert (plan, members) == before


@pytest.mark.parametrize("partition", [None, "train", "development", "test", "sealed", ScenarioPartition.TEST, object()])
def test_untyped_and_held_out_scopes_refuse_before_observation(monkeypatch, partition):
    def forbidden(*_, **__):
        pytest.fail("invalid partition reached the observation or native binding port")
    monkeypatch.setattr(subject, "observe_preparation_members", forbidden)
    monkeypatch.setattr(subject, "routed_preparation_binding", forbidden)
    with pytest.raises(ValueError, match="typed TRAIN or DEVELOPMENT"):
        subject.member_preparation_options(None, None, plan=None, opponent_levels=(29,),
            forecast_ref="loss", home_map=134, route=None,
            battler=SimpleNamespace(source_partition=partition), allow_above_reference=True)


@pytest.mark.parametrize("partition", [ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT])
@pytest.mark.parametrize("loss", [None, "lost", {"result": "lost"},
    aftermath(result=BattleResult.WON, opponents_defeated=2, terminal_fainted_count=0, terminal_hp_fraction=1.0),
    aftermath(result=BattleResult.UNRESOLVED)])
def test_admitted_partition_still_requires_typed_real_loss_before_binding(monkeypatch, partition, loss):
    _, _, calls, args = setup_port(monkeypatch)
    with pytest.raises(ValueError, match="observed defeat"):
        subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args,
            battler=SimpleNamespace(source_partition=partition), allow_above_reference=True,
            observed_defeat=loss)
    assert calls == []


@pytest.mark.parametrize("partition", [ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT])
def test_default_parity_ceiling_remains_without_opt_in(monkeypatch, partition):
    members, _, calls, args = setup_port(monkeypatch)
    rows = subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args,
        battler=SimpleNamespace(source_partition=partition), observed_defeat=aftermath())
    assert len(rows) == 2
    assert members[0].specimen_ref not in {c["plan"].targets[0][0] for c in calls}
    assert all(c["plan"].targets[0][1] <= 29 for c in calls)


def test_train_roles_level100_and_short_ceiling_survive_native_port(monkeypatch):
    purposes = (PreparationPurpose.COMBAT, PreparationPurpose.COMBAT,
                PreparationPurpose.FIELD_UTILITY, PreparationPurpose.COLLECTION)
    members, _, calls, args = setup_port(monkeypatch, (100, 99, 30, 30), purposes)
    rows = subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args,
        battler=SimpleNamespace(source_partition=ScenarioPartition.TRAIN),
        maximum_level_gain=3, allow_above_reference=True, observed_defeat=aftermath())
    assert len(rows) == 1 and calls[0]["plan"].targets == ((members[1].specimen_ref, 100),)
    calls.clear()
    with pytest.raises(ValueError, match="optional preparation level cap"):
        subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args,
            battler=SimpleNamespace(source_partition=ScenarioPartition.TRAIN),
            maximum_level_gain=4, allow_above_reference=True, observed_defeat=aftermath())
    assert calls == []


def test_loss_does_not_make_unreachable_native_binding_available(monkeypatch):
    _, _, _, args = setup_port(monkeypatch)
    monkeypatch.setattr(subject, "routed_preparation_binding", lambda *_, **__: None)
    assert subject.member_preparation_options(SimpleNamespace(emulator=object()), None, **args,
        battler=SimpleNamespace(source_partition=ScenarioPartition.TRAIN),
        allow_above_reference=True, observed_defeat=aftermath()) == ()
