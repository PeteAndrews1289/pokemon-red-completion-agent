"""Known helper headroom exhaustion is a partial, never a generic error waiver."""

import ast
import inspect
import textwrap
from types import SimpleNamespace as N

import pytest
from test_certified_evolution_helper_xp import guard, member, raw

from pokemon_red_completion import red_evolution_helper_xp as xp
from pokemon_red_completion import red_native_boxed_evolution as native


def nested(name, **scope):
    root = ast.parse(textwrap.dedent(inspect.getsource(native.bind_native_boxed_evolution))).body[0]
    node = next(n for n in root.body if isinstance(n, ast.FunctionDef) and n.name == name)
    module = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            node,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = dict(vars(native))
    namespace.update(scope)
    exec(compile(module, "actual-native-" + name, "exec"), namespace)
    return namespace[name]


def test_only_known_valid_headroom_is_diagnosed_without_relaxing_execution():
    g = guard()
    party = N(members=(member(33, 36**3 - 8194),))
    assert g.exclusions(party, raw()) == frozenset({1})
    assert g.headroom_exhausted_species(party, raw()) == frozenset({1})
    assert g.exclusions(party, raw()) == frozenset({1})


@pytest.mark.parametrize(
    "party,environment",
    [
        (N(members=(member(experience=None),)), raw()),
        (N(members=(member(36, 36**3),)), raw()),
        (N(members=(member(33, 36**3 - 8194), member(experience=None))), raw()),
        (N(members=(member(33, 36**3 - 8194),)), raw(bag_items=None)),
        (N(members=(member(33, 36**3 - 8194),)), raw(battle_state=2)),
    ],
)
def test_unknown_overdue_and_unsupported_are_not_headroom_exhaustion(party, environment):
    assert guard().headroom_exhausted_species(party, environment) == frozenset()


@pytest.mark.parametrize(
    "reason", ["known", "no-prior", "no-counter", "no-blocked", "battle", "pressed", "no-xp"]
)
def test_actual_quantum_missing_venue_needs_exact_productive_safe_counterproof(reason):
    observation = N(
        raw=N(battle_state=1 if reason == "battle" else 0),
        input_ready=True,
        party=N(members=(N(species_id=185, hp=20),)),
    )
    runtime = N(
        adapter=N(observe=lambda: observation),
        emulator=N(pressed_buttons=frozenset({"a"}) if reason == "pressed" else frozenset()),
    )

    def exclusions(observation, *, diagnostic_headroom=False):
        return frozenset() if diagnostic_headroom or reason == "no-blocked" else frozenset({150})

    calls = []

    def venues(observation, *, diagnostic_headroom=False):
        calls.append(diagnostic_headroom)
        return (N(),) if diagnostic_headroom and reason != "no-counter" else ()

    function = nested(
        "train_quantum",
        runtime=runtime,
        helper_xp_guard=object(),
        check_settlement_reserve=lambda: None,
        prepare_native_training_center=lambda *a: None,
        restore_native_center_party=lambda *a: 1,
        supported_venues=venues,
        helper_exclusions=exclusions,
        world=N(),
        PokemonRedPartyReader=lambda _: N(
            read=lambda: N(
                members=(N(species_id=185, experience=100 if reason == "no-xp" else 150),)
            )
        ),
    )
    state = {"helper_xp_admission_seen": reason != "no-prior", "trainee_initial_xp": 100}
    expected = (
        xp.EvolutionHelperXPExhausted if reason == "known" else native.context.RedGoalContextError
    )
    with pytest.raises(expected) as caught:
        function(N(), 185, 186, state)
    if reason == "known":
        assert (caught.value.battles, caught.value.healing_trips) == (0, 1)
        assert caught.value.blocked_helpers == frozenset({150})
        assert calls == [False, True]


def test_actual_productive_aggregator_returns_once_with_all_prior_counts():
    experience = [100]

    def member_now():
        return N(species_id=185, experience=experience[0], hp=20)

    def observation():
        return N(
            game_state=None,
            party=N(members=(member_now(),)),
            collection_observation=N(specimens=(N(species_ref="pokemon:national:043"),)),
        )

    runtime = N(
        adapter=N(observe=observation, graph=N(completed_ids=lambda _: frozenset())),
        reader=N(read=lambda: N(battle_state=0), read_input_readiness=lambda: N(ready=True)),
        emulator=N(),
    )
    calls = []

    def quantum(*args):
        calls.append(True)
        if len(calls) == 1:
            experience[0] += 50
            return native.BoundedEvolutionTrainingResult(4, 2)
        raise xp.EvolutionHelperXPExhausted(0, 1, frozenset({150}))

    function = nested(
        "train",
        runtime=runtime,
        maximum_quanta=4,
        maximum_wall_seconds=60,
        check_settlement_reserve=lambda *a: None,
        allowed=lambda _: True,
        train_quantum=quantum,
        registration=None,
        retain_quantum=None,
        PokemonRedPartyReader=lambda _: N(read=lambda: N(members=(member_now(),))),
    )
    with pytest.raises(xp.EvolutionHelperXPExhausted) as caught:
        function(N(), 185, 186)
    assert len(calls) == 2
    assert (caught.value.battles, caught.value.healing_trips) == (4, 3)


def test_partial_schema_does_not_claim_no_wins_or_success():
    report = nested(
        "partial_report",
        spec=N(
            parameters={
                "source_species_ref": "pokemon:national:043",
                "target_species_ref": "pokemon:national:044",
            }
        ),
    )(xp.EvolutionHelperXPExhausted(56, 20, frozenset({150})))
    assert report.evidence["helper_xp_headroom_exhausted"] is True
    assert report.evidence["completed_training_battles"] == 56
    assert "no_verified_win" not in report.evidence
    assert "training_venue_exhausted" not in report.evidence


@pytest.mark.parametrize("after_xp,accepted", [(150, True), (100, False), (None, False)])
def test_actual_balancer_pause_catch_requires_paid_trainee_progress(after_xp, accepted):
    root = ast.parse(textwrap.dedent(inspect.getsource(native.bind_native_boxed_evolution))).body[0]
    quantum = next(
        node
        for node in root.body
        if isinstance(node, ast.FunctionDef) and node.name == "train_quantum"
    )
    handler = next(
        node
        for node in ast.walk(quantum)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "EvolutionHelperXPExhausted"
    )
    pending = xp.EvolutionHelperXPExhausted(4, 2, frozenset({150}))
    node = ast.Try(
        body=[ast.Raise(exc=ast.Name(id="pending", ctx=ast.Load()))],
        handlers=[handler],
        orelse=[],
        finalbody=[],
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(vars(native))
    namespace.update(
        pending=pending,
        initial_trainee_xp=100,
        initial_heals=1,
        source_id=185,
        runtime=N(emulator=N()),
        PokemonRedPartyReader=lambda _: N(
            read=lambda: N(members=(N(species_id=185, experience=after_xp),))
        ),
    )
    expected = xp.EvolutionHelperXPExhausted if accepted else native.context.RedGoalContextError
    with pytest.raises(expected) as caught:
        exec(compile(module, "actual-productive-headroom-catch", "exec"), namespace)
    if accepted:
        assert (caught.value.battles, caught.value.healing_trips) == (4, 3)
        assert caught.value.blocked_helpers == frozenset({150})
