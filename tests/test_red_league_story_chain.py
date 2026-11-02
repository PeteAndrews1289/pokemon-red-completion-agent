import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_faint_recovery import raw_party
from test_red_trainer_practice_fit import _target

from pokemon_red_completion import red_league_story_chain as chain
from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.red_lorelei_story import (
    FrozenEarnedLeagueChainController,
    story_league_controller,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "stage-465"
    root.mkdir()
    (root / "final.state").write_bytes(b"root")
    (root / "final.envelope.json").write_bytes(b"envelope")
    monkeypatch.setattr(chain, "LEAGUE_CHAIN_ROOT_SHA256", sha256(b"root").hexdigest())
    monkeypatch.setattr(chain, "LEAGUE_CHAIN_ENVELOPE_SHA256", sha256(b"envelope").hexdigest())
    source = chain.LEAGUE_CHAIN_ROOT_SHA256
    for i in range(4):
        stage = tmp_path / f"stage-{466 + i}"
        stage.mkdir()
        data = f"terminal-{i}".encode()
        terminal = sha256(data).hexdigest()
        (stage / "final.state").write_bytes(data)
        for name, value in {
            "claim": dict(
                chain_index=i,
                chain_root_sha256=chain.LEAGUE_CHAIN_ROOT_SHA256,
                source_sha256=source,
                model_sha256=learned.AGATHA_STORY_SHA256,
                admission_sha256=chain.LEAGUE_CHAIN_ADMISSION_SHA256,
                campaign_execution=True,
            ),
            "final": dict(sha256=terminal, error=None, safe=True),
            "battle-completion": dict(
                outcome="won",
                field_ready=True,
                episode=dict(battle_won=True),
                final_map=chain.LEAGUE_CHAIN_TARGETS[i][2],
            ),
        }.items():
            (stage / (name + ".json")).write_text(json.dumps(value))
        source = terminal
    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=1, require_corpus_floor=False
    )
    monkeypatch.setattr(
        learned, "AGATHA_STORY_MODEL_SHA256", learned.canonical_sha256(model.to_dict())
    )
    admission = (
        Path(__file__).parents[1] / "docs/evidence/red-league-rechallenge-admission-2026-09-25.json"
    ).read_bytes()

    def build(index):
        source = sha256((tmp_path / f"stage-{465 + index}/final.state").read_bytes()).hexdigest()
        battler = learned.FrozenTrainerBattler(
            None,
            model,
            tmp_path / f"stage-{466 + index}",
            "a" * 40,
            "root",
            source,
            {},
            model_sha256=learned.AGATHA_STORY_SHA256,
            qualification_sha256=chain.LEAGUE_CHAIN_ADMISSION_SHA256,
            story_chain_scope=chain.EarnedLeagueStepScope(tmp_path, index),
        )
        return battler, StoryTrainerContract(*chain.LEAGUE_CHAIN_TARGETS[index]), admission

    return build, tmp_path


@pytest.mark.parametrize("index", range(5))
def test_all_rooms_require_ordered_source_chain_and_rematch(setup, index):
    build, _ = setup
    ctl = FrozenEarnedLeagueChainController(*build(index))
    assert sha256(ctl.admission).hexdigest() == chain.LEAGUE_CHAIN_ADMISSION_SHA256
    runtime = NS(league_story_battle_controller=ctl)
    assert story_league_controller(runtime, ctl.contract.objective_id, rematch=True) is ctl
    assert (
        learned.qualified_party_limit(ctl.battler.model_sha256, ctl.battler.qualification_sha256)
        == 0
    )
    with pytest.raises(ValueError):
        story_league_controller(runtime, ctl.contract.objective_id, rematch=False)
    with pytest.raises(ValueError):
        story_league_controller(runtime, "ordinary-funding", rematch=True)


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "model",
        "weights",
        "receipt",
        "output",
        "scope",
        "contract",
        "calls",
        "claimed",
        "bound",
        "root",
        "envelope",
    ],
)
def test_substitution_and_replay_fail_before_inputs(setup, fault):
    build, directory = setup
    battler, contract, admission = build(4)
    if fault == "source":
        battler.source_state_sha256 = "0" * 64
    if fault == "model":
        battler.model_sha256 = learned.DAMAGE_STORY_SHA256
    if fault == "weights":
        battler.model = None
    if fault == "receipt":
        admission += b" "
    if fault == "output":
        battler.output = directory / "other"
    if fault == "scope":
        battler.story_chain_scope = None
    if fault == "contract":
        contract = replace(contract, victory_money=1)
    if fault == "calls":
        battler.calls = 1
    if fault == "claimed":
        (battler.output / "battle-0001").mkdir(parents=True)
    if fault == "root":
        (directory / "stage-465/final.state").write_bytes(b"changed")
    if fault == "envelope":
        (directory / "stage-465/final.envelope.json").write_bytes(b"changed")
    with pytest.raises(ValueError):
        FrozenEarnedLeagueChainController(
            battler, contract, admission, maximum_decisions=81 if fault == "bound" else 80
        )


@pytest.mark.parametrize(
    "file,key,value",
    [
        ("claim", "source_sha256", "0" * 64),
        ("claim", "chain_index", 3),
        ("claim", "campaign_execution", False),
        ("claim", "admission_sha256", "0" * 64),
        ("final", "error", "failed"),
        ("final", "safe", False),
        ("final", "sha256", "0" * 64),
        ("battle-completion", "outcome", "lost"),
        ("battle-completion", "field_ready", False),
        ("battle-completion", "final_map", 9),
    ],
)
def test_failed_or_changed_predecessor_cannot_unlock_next_room(setup, file, key, value):
    build, directory = setup
    path = directory / f"stage-467/{file}.json"
    record = json.loads(path.read_text())
    record[key] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        FrozenEarnedLeagueChainController(*build(4))


def live(index):
    flags = bytearray(320)
    for target in chain.LEAGUE_CHAIN_TARGETS[:index]:
        flags[target[4] // 8] |= 1 << (target[4] % 8)
    if index == 4:
        bit = int(EventFlag.BEAT_LANCE)
        flags[bit // 8] |= 1 << (bit % 8)
    return replace(raw_party(), event_flags=bytes(flags))


@pytest.mark.parametrize("index", range(5))
def test_live_defeat_flags_not_historical_story_counter(index):
    chain.require_chain_live_boundary(live(index), index)
    with pytest.raises(ValueError):
        chain.require_chain_live_boundary(live((index + 1) % 5), index)
    with pytest.raises(ValueError):
        chain.require_chain_live_boundary(replace(live(index), battle_state=2), index)


@pytest.mark.parametrize("index", [True, -1, 5, None])
def test_invalid_live_room_index(index):
    with pytest.raises(ValueError):
        chain.require_chain_live_boundary(live(0), index)


def test_owned_supply_accounting_rejects_substitution_and_overspend():
    initial = ((20, 7), (18, 3), (53, 4), (52, 1), (4, 8))
    raw = raw_party(bag=((20, 5), (18, 3), (53, 3), (52, 1), (4, 8)))
    chain.require_owned_chain_stock(raw, initial, {20: 2, 53: 1})
    for spent in ({20: 8}, {20: True}, {1: 1}, {20: 1, 53: 1}, {20: 2, 53: 0}):
        with pytest.raises(ValueError):
            chain.require_owned_chain_stock(raw, initial, spent)
    with pytest.raises(ValueError):
        chain.require_owned_chain_stock(
            replace(raw, bag_items=raw.bag_items + ((1, 1),)), initial, {20: 2, 53: 1}
        )


def test_restricted_preparation_does_not_spend_other_owned_status_items():
    from pokemon_red_completion.observation import ItemId
    from pokemon_red_completion.red_faint_recovery import plan_faint_aware_recovery

    raw = raw_party(hp=(100, 101), status=(0x40, 0), bag=((15, 5), (52, 1)))
    assert plan_faint_aware_recovery(raw).item == ItemId.PARLYZ_HEAL
    allowed = frozenset({ItemId.FULL_HEAL})
    choice = plan_faint_aware_recovery(raw, allowed_items=allowed)
    assert choice.item == ItemId.FULL_HEAL and choice.expected_status == 0
    assert plan_faint_aware_recovery(raw, allowed_items=frozenset()) is None
    with pytest.raises(ValueError):
        plan_faint_aware_recovery(raw, allowed_items={52})
