from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.red_player_curriculum import NativeResourceCurriculum


def test_regional_completion_requires_native_region_and_does_not_assert_later_story(monkeypatch):
    from pokemon_red_completion import red_player_curriculum as m

    monkeypatch.setattr(m, "_raw_party_fully_restored", lambda _: True)
    b = boundary()
    curriculum = m.NativeRegionalCurriculum(("pokedex",), (("starter", 8),), 14)
    b.observation.raw.map_id = 2
    assert curriculum.completion(b) is None
    b.observation.raw.map_id = 14
    assert curriculum.completion(b).public_dict()["full_game_completion"] is False


def test_completed_curriculum_stops_before_unrelated_menu_construction(monkeypatch):
    from pokemon_red_completion import red_player_curriculum as c
    from pokemon_red_completion import red_player_lesson_runtime as r

    b = boundary()
    rt = NS(
        emulator=NS(save_state_bytes=lambda: b.state, pressed_buttons=frozenset()),
        reader=NS(read_bottom_dialogue_box_visible=lambda: False),
    )
    monkeypatch.setattr(c, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(r, "observe_native_player_boundary", lambda *a, **k: b)
    result = r.observe_native_player_options(
        rt,
        None,
        battle=None,
        combat_specimen_refs=("starter",),
        remaining_budget=(1.0,) * 5,
        target_cash=0,
        ordering_seed_sha256="a" * 64,
        allow_support=True,
        enumerate_bindings=lambda *a: pytest.fail("completed packet must not query another menu"),
        curriculum=c.NativePlayerCurriculum(("pokedex",), (("starter", 8),)),
    )
    assert result.public_dict()["model_queries"] == 0


@pytest.mark.parametrize("dialogue,pressed", [(True, False), (False, True)])
def test_completion_does_not_preempt_unsettled_control_recovery(monkeypatch, dialogue, pressed):
    from pokemon_red_completion import red_player_curriculum as c
    from pokemon_red_completion import red_player_lesson_runtime as r

    b = boundary()
    rt = NS(
        emulator=NS(
            save_state_bytes=lambda: b.state,
            pressed_buttons=frozenset({"a"}) if pressed else frozenset(),
        ),
        reader=NS(read_bottom_dialogue_box_visible=lambda: dialogue),
    )
    monkeypatch.setattr(c, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(r, "observe_native_player_boundary", lambda *a, **k: b)

    def recovery(*args):
        raise RuntimeError("recovery menu reached")

    with pytest.raises(RuntimeError, match="recovery menu reached"):
        r.observe_native_player_options(
            rt,
            None,
            battle=None,
            combat_specimen_refs=("starter",),
            remaining_budget=(1.0,) * 5,
            target_cash=0,
            ordering_seed_sha256="a" * 64,
            allow_support=True,
            enumerate_bindings=recovery,
            curriculum=c.NativePlayerCurriculum(("pokedex",), (("starter", 8),)),
        )


def boundary():
    return NS(
        registered=NS(),
        state=b"native",
        lesson_snapshot={
            "completed_objectives": ["pokedex"],
            "in_battle": False,
            "party": [{"specimen_ref": "starter", "level": 8}],
        },
        observation=NS(
            input_ready=True,
            raw=NS(bag_items=((4, 3),)),
            collection_observation=NS(owned_species=("red-species-016",)),
        ),
    )


@pytest.mark.parametrize("fault", [None, "stock", "species", "unknown", "duplicate", "health"])
def test_resource_completion_requires_actual_stock_and_local_species(monkeypatch, fault):
    import pokemon_red_completion.red_player_curriculum as module

    monkeypatch.setattr(module, "_raw_party_fully_restored", lambda _: fault != "health")
    b = boundary()
    if fault == "stock":
        b.observation.raw.bag_items = ((4, 1),)
    if fault == "species":
        b.observation.collection_observation.owned_species = ()
    if fault == "unknown":
        b.observation.raw.bag_items = None
    if fault == "duplicate":
        b.observation.raw.bag_items = ((4, 3), (4, 3))
    curriculum = NativeResourceCurriculum(
        ("pokedex",), (("starter", 8),), ("red-species-016",), ((4, 2),)
    )
    assert (curriculum.completion(b) is not None) == (fault is None)


@pytest.mark.parametrize(
    "species,stock",
    [
        ((), ()),
        (("a", "a"), ()),
        ((), ((4, 0),)),
        ((), ((4, True),)),
        ((), ((4, 2), (4, 3))),
        ((), ((256, 1),)),
    ],
)
def test_invalid_resource_contract_rejected(species, stock):
    with pytest.raises(ValueError, match="resource curriculum"):
        NativeResourceCurriculum(("pokedex",), (("starter", 8),), species, stock)
