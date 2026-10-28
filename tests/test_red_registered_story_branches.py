from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_player_story_menu import registered_story_branches


def setup(legal=("defeat_sabrina", "reach_fuchsia")):
    em = N(state=b"actual", frame_count=7, pressed_buttons=frozenset())
    em.save_state_bytes = lambda: em.state
    known = {name: N(id=name) for name in (*legal, "obtain_surf")}
    rt = N(
        emulator=em,
        adapter=N(
            observe=lambda: N(game_state=object()),
            graph=N(
                objective=known.__getitem__,
                available_objectives=lambda _: tuple(known[x] for x in legal),
            ),
        ),
    )
    return rt


def row(name, *, ref=None, kind=GoalKind.ADVANCE_STORY):
    return replace(
        _binding(kind, binding_ref=ref or name, calls=[]),
        story_objective_ref=name if kind is GoalKind.ADVANCE_STORY else None,
    ), OptionChallenge(False, False, 0.0, 0.0, 0.0)


def test_every_legal_capability_is_preserved_without_registry_priority():
    rt = setup()
    seen = []
    observers = {
        name: lambda *_, name=name: seen.append(name) or row(name)
        for name in ("reach_fuchsia", "obtain_surf", "defeat_sabrina")
    }
    first = registered_story_branches(rt, object(), observers=observers)
    assert seen == ["defeat_sabrina", "reach_fuchsia"]
    seen.clear()
    second = registered_story_branches(rt, object(), observers=dict(reversed(observers.items())))
    assert seen == ["defeat_sabrina", "reach_fuchsia"]
    assert [b.story_objective_ref for b, _ in first] == [b.story_objective_ref for b, _ in second]
    assert rt.emulator.state == b"actual" and rt.emulator.frame_count == 7


def test_missing_or_currently_unexecutable_capability_is_not_substituted():
    rt = setup()
    assert (
        registered_story_branches(rt, object(), observers={"defeat_sabrina": lambda *_: None}) == ()
    )
    assert registered_story_branches(rt, object(), observers={}) == ()


@pytest.mark.parametrize("bad", [None, [], {"": lambda *_: None}, {"defeat_sabrina": None}])
def test_registry_shape_is_explicit(bad):
    with pytest.raises(TypeError, match="objective-keyed"):
        registered_story_branches(setup(), object(), observers=bad)


def test_unknown_objective_fails_before_observer_dispatch():
    with pytest.raises(KeyError):
        registered_story_branches(
            setup(), object(), observers={"unknown": lambda *_: pytest.fail()}
        )


@pytest.mark.parametrize(
    "bad",
    [
        lambda: row("obtain_surf"),
        lambda: row("defeat_sabrina", kind=GoalKind.DEVELOP_TEAM),
        lambda: (row("defeat_sabrina")[0], None),
        lambda: [*row("defeat_sabrina")],
        lambda: (object(), row("defeat_sabrina")[1]),
        lambda: (
            replace(row("defeat_sabrina")[0], story_objective_ref=None),
            row("defeat_sabrina")[1],
        ),
    ],
)
def test_wrong_objective_or_untyped_binding_is_rejected(bad):
    with pytest.raises(ValueError, match="own typed"):
        registered_story_branches(setup(), object(), observers={"defeat_sabrina": lambda *_: bad()})


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", b"changed"),
        ("frame_count", 8),
        ("pressed_buttons", frozenset({"A"})),
    ],
)
@pytest.mark.parametrize("returns_none", [False, True])
def test_native_side_effect_even_from_unavailable_observer_is_rejected(field, value, returns_none):
    rt = setup()

    def observe(*_):
        setattr(rt.emulator, field, value)
        return None if returns_none else row("defeat_sabrina")

    with pytest.raises(ValueError, match="changed native"):
        registered_story_branches(rt, object(), observers={"defeat_sabrina": observe})


def test_duplicate_native_executor_is_rejected():
    with pytest.raises(ValueError, match="repeats"):
        registered_story_branches(
            setup(),
            object(),
            observers={
                name: lambda *_, name=name: row(name, ref="same")
                for name in ("defeat_sabrina", "reach_fuchsia")
            },
        )


def test_adapter_observation_itself_cannot_tick():
    rt = setup(())

    def observe():
        rt.emulator.frame_count += 1
        return N(game_state=object())

    rt.adapter.observe = observe
    with pytest.raises(ValueError, match="changed native"):
        registered_story_branches(rt, object(), observers={})
