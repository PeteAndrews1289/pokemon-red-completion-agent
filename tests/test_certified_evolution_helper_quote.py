"""Exercise the real XP-omitting adapter and native producer, with no game port."""
from dataclasses import replace
from types import SimpleNamespace as N
import pytest

from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_evolution_helper_xp as xp
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import MapId, ItemId
from pokemon_red_completion.red_party import PokemonRedPartyReader, party_observation_from_raw
from pokemon_red_completion.red_collection import red_internal_species_number
from test_red_native_boxed_evolution import runtime_fixture
from test_red_goal_context import _ActionDelegate
from test_red_party import memory_with


def producer(tmp_path, monkeypatch, *, enabled=True, mismatch=None, exp_all=False, unknown=False, current_case=None):
    source, target, evolution, count, level = (
        (43, 44, 21, 1, 13) if current_case == "boxed" else
        (17, 18, 36, 0, 33) if current_case == "active" else (14, 15, 10, 0, 8))
    runtime, reader, _ = runtime_fixture(
        tmp_path, source=source, target=target, evolution_level=evolution, count=count, level=level)
    ids, levels = (113, 165, 150, 179, 5, 108), (8, 20, 22, 25, 15, 13)
    hp = (25, 42, 60, 66, 42, 36)
    experience = (691, 9003, 8367, 11833, 3567, 2337)
    if current_case is not None:
        ids, levels = (165, 150, 5, 114, 108, 179), (20, 33, 15, 10, 21, 27)
        hp, experience = (42, 91, 42, 33, 54, 72), (9003, 31851, 3567, 1015, 10295, 15792)
    moves, pp = ((33, 0, 0, 0),) * 6, ((20, 0, 0, 0),) * 6
    reader.raw = replace(reader.raw, map_id=MapId.CERULEAN_POKECENTER,
        party_species_ids=ids, party_levels=levels, party_hp=hp, party_max_hp=hp,
        party_status=(0,) * 6, party_moves=moves, party_pp=pp,
        bag_items=((int(ItemId.EXP_ALL), 1),) if exp_all else ())
    owned = frozenset({*(red_internal_species_number(species) for species in ids), source})
    reader.read_pokedex_state = lambda: N(seen_species=owned, owned_species=owned)
    specs = [dict(species_id=s, level=l, hp=h, max_hp=h, moves=m, pp=p, experience=e)
             for s, l, h, m, p, e in zip(ids, levels, hp, moves, pp, experience)]
    if mismatch:
        specs[3][mismatch] = specs[3][mismatch] + 1
        if mismatch == "hp":
            specs[3]["max_hp"] += 1
    if unknown:
        for spec in specs:
            spec["experience"] = 0
    memory = memory_with(*specs)
    memory.frame_count, memory.pressed_buttons = 0, frozenset()
    def deny(*args):
        pytest.fail("producer quote attempted native input")
    memory.press = memory.release = memory.tick = deny
    # Synthetic pure cartridge floor fixture, not a qualification of this ROM.
    def floors(s):
        return tuple(max(0, 6 * level ** 3 // 5 - 15 * level ** 2 + 100 * level - 140)
                     if s in {150, 179, 185} else level ** 3 for level in range(1, 101))
    edges = ((113,114,10),(165,166,20),(150,151,36),(179,28,36),(5,35,20),(108,45,22),(185,186,21))
    excluded = frozenset(s for s, target, level in edges)
    guard = xp.EvolutionHelperXPGuard(tuple((s, l, floors(s)) for s, t, l in edges),
        frozenset((*ids, 113, 114, 166, 151, 28, 35, 45, 185, 186)), excluded, xp._QUALIFIED_ROM)
    monkeypatch.setattr(xp.EvolutionHelperXPGuard, "from_rom",
        classmethod(lambda cls, rom, actual: guard if actual == excluded else pytest.fail("scope drift")))
    monkeypatch.setattr(native, "level_evolution_edges", lambda rom: edges)
    venue = replace(native.context.ROUTE_11_TRAINING_VENUE,
        is_in_center=lambda raw: raw.map_id == MapId.CERULEAN_POKECENTER)
    monkeypatch.setattr(native, "wild_tables", lambda rom: {venue.map_id: ((17,165),)})
    from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
    from pokemon_red_completion.registration_memory import RegistrationSnapshot
    from pokemon_red_completion.registration_memory import observation_from_collection
    from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID, red_species_ref
    collection = runtime.adapter.observe().collection_observation
    row = observation_from_collection(collection, seen_species=collection.owned_species,
        national_ids={red_species_ref(i): i for i in range(1, 152)}, run_id="current",
        game_id=RED_COLLECTION_GAME_ID, adapter_id="red-v1", cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64, sequence=0)
    policy = RedRegistrationPolicy(RegistrationSnapshot((row,)), "current", "b" * 64,
                                   collection, {})
    runtime = replace(runtime, emulator=memory, registration_policy=policy,
                      certified_evolution_helper_xp=enabled)
    observation = runtime.adapter.observe()
    assert observation.party == party_observation_from_raw(reader.raw)
    assert all(member.experience is None for member in observation.party.members)
    assert PokemonRedPartyReader(memory).read().members[3].experience == (
        0 if unknown else experience[3])
    bound = native.bind_native_boxed_evolution(
        runtime, N(rom=b"synthetic-producer-fixture"), training_venues=(venue,),
        allow_direct_evolution=False)
    actions = CountingExecutor(_ActionDelegate())
    offer = bound.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
    assert actions.actions_executed == memory.frame_count == 0
    assert not memory.pressed_buttons
    assert all(member.experience is None for member in observation.party.members)
    return offer


@pytest.mark.parametrize("enabled,expected", [(False,False),(True,True)])
def test_real_goal_adapter_reaches_native_evolution_offer_without_policy_xp(
    tmp_path, monkeypatch, enabled, expected
):
    assert (producer(tmp_path, monkeypatch, enabled=enabled).binding is not None) is expected


@pytest.mark.parametrize("mismatch", ["hp", "level", "species_id"])
def test_rich_party_drift_from_coherent_snapshot_does_not_admit(
    tmp_path, monkeypatch, mismatch
):
    assert producer(tmp_path, monkeypatch, mismatch=mismatch).binding is None


def test_exp_all_still_declines_complete_producer(tmp_path, monkeypatch):
    assert producer(tmp_path, monkeypatch, exp_all=True).binding is None


def test_unknown_rich_xp_still_declines_complete_producer(tmp_path, monkeypatch):
    assert producer(tmp_path, monkeypatch, unknown=True).binding is None

@pytest.mark.parametrize("current_case,expected", [("boxed",False),("active",True)])
def test_actual_postloan_quote_does_not_credit_deposited_wartortle(
    tmp_path, monkeypatch, current_case, expected
):
    assert (producer(tmp_path, monkeypatch, current_case=current_case).binding is not None) is expected
