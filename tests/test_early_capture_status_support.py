"""Early ordinary capture reuses status support without requiring a status move."""

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_red_capture_status_runtime import setup
from test_red_player_collection_options import collection_runtime, corridor

from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.party import MoveObservation
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_player_collection_options import bind_player_collection_capabilities
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor


def early_runtime():
    return bind_player_collection_capabilities(
        collection_runtime(), seed_corridor=corridor(), add_capture_preparation_support=False
    )


def test_status_only_profile_changes_no_other_capability_or_existing_parameter():
    original = early_runtime()
    current = configuration.connect_early_capture_status_support(original)
    assert current.registration_policy is original.registration_policy
    for old, new in zip(original.profile.providers, current.profile.providers, strict=True):
        if old.kind is GoalKind.ACQUIRE_SPECIES:
            assert dict(new.parameters) == dict(
                old.parameters, capture_status_support=True, capture_party_preparation=False
            )
            assert not new.parameters.get("capture_weakening_support", False)
        else:
            assert new == old
    assert not next(
        p for p in original.profile.providers if p.kind is GoalKind.ACQUIRE_SPECIES
    ).parameters.get("capture_status_support")


@pytest.mark.parametrize(
    "train,rewards,early",
    [
        (False, True, True),
        (False, False, True),
        (False, True, False),
        (True, True, True),
    ],
)
def test_actual_factory_prefix_enables_support_only_for_existing_ordinary_early_lane(
    train,
    rewards,
    early,
):
    tree = ast.parse(Path(configuration.__file__).read_text())
    assembly = next(
        x
        for x in tree.body
        if isinstance(x, ast.FunctionDef) and x.name == "assemble_configured_player"
    )
    factory = next(
        x for x in assembly.body if isinstance(x, ast.FunctionDef) and x.name == "factory"
    )
    # Execute the actual first three statements; stop before party/ROM assembly.
    factory.body = factory.body[:3] + [ast.Return(value=ast.Name(id="runtime", ctx=ast.Load()))]
    module = ast.Module(body=[factory], type_ignores=[])
    ast.fix_missing_locations(module)
    runtime = early_runtime()
    namespace = dict(
        factory0=lambda _: runtime,
        configuration=N(
            assembly_flags=dict(include_rewards=rewards, include_early_preparation=early)
        ),
        training_admission=object() if train else None,
        connect_early_capture_status_support=configuration.connect_early_capture_status_support,
    )
    exec(compile(module, "actual-configured-factory-prefix", "exec"), namespace)
    current = namespace["factory"](object())
    capture = next(p for p in current.profile.providers if p.kind is GoalKind.ACQUIRE_SPECIES)
    assert capture.parameters.get("capture_status_support", False) is (
        not train and rewards and early
    )


@pytest.mark.parametrize("caught", [False, True])
def test_no_status_helper_throws_without_lethal_legacy_attack(monkeypatch, caught):
    import pokemon_red_completion.surge as surge

    world, _ = setup(monkeypatch)
    world.party = replace(
        world.party,
        members=(
            replace(world.party.members[0], moves=(MoveObservation(33, 20),)),
            world.party.members[1],
        ),
    )
    before = world.raw
    calls = []

    def throw(*args, before_throw, **kwargs):
        assert before_throw()
        calls.append("ordinary_ball")
        return caught

    monkeypatch.setattr(surge, "_try_catch_wild", throw)
    for name in (
        "_wild_capture_policy",
        "_select_wild_capture_helper",
        "_weaken_wild_capture_once",
    ):
        monkeypatch.setattr(
            surge,
            name,
            lambda *args, **kwargs: pytest.fail("status-only capture reached legacy damage"),
        )
    live = LiveWildEncounterExecutor(
        object(),
        object(),
        world,
        DEFAULT_SURGE_TIMING,
        label="ordinary no-helper capture",
        capture_status_support=True,
        capture_weakening_support=False,
    )
    target = red_species_ref(red_internal_species_number(before.enemy_species_id))
    assert live.capture_encounter(target) is caught
    assert calls == ["ordinary_ball"]
    assert world.turns == 0 and world.raw.enemy_hp == before.enemy_hp
    assert live.capture_status_reports == [] and live.capture_weakening_reports == []
    assert len(live.capture_throw_preparations) == 1
