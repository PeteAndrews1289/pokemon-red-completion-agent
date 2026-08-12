from dataclasses import replace

from pokemon_red_completion.cinnabar import (
    DUX_MOVES_AFTER,
    DUX_MOVES_BEFORE,
    DUX_PP_AFTER,
    DUX_PP_BEFORE,
)
from pokemon_red_completion.fly_resource import (
    CENTER_TO_ROUTE_16_TREE,
    FLY_RESOURCE_CHECKPOINT_COUNT,
    FlyResourceCheckpoint,
    FlyResourceReport,
)
from pokemon_red_completion.observation import ItemId, MapId, RawGameState


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=4,
        battle_state=0,
        party_species_ids=(28, 64, 59, 132),
        first_party_level=40,
        first_party_hp=125,
        first_party_max_hp=125,
        first_party_status=0,
        first_party_moves=(44, 39, 61, 55),
        first_party_pp=(25, 30, 20, 25),
    )


def _report() -> FlyResourceReport:
    raw = _raw()
    initial_bag = ((4, 1), (15, 7))
    return FlyResourceReport(
        records=tuple(
            FlyResourceCheckpoint(str(index), str(index), raw)
            for index in range(FLY_RESOURCE_CHECKPOINT_COUNT)
        ),
        initial_raw=raw,
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=tuple(sorted((*initial_bag, (int(ItemId.HM02_FLY), 1)))),
        hm02_item_before_event=True,
        got_hm02=True,
        dux_moves_before=DUX_MOVES_BEFORE,
        dux_moves_after=DUX_MOVES_AFTER,
        dux_pp_before=DUX_PP_BEFORE,
        dux_pp_after=DUX_PP_AFTER,
        wild_battles=1,
        fly_landings=((int(MapId.CELADON_CITY), 48),),
        party_hp_before=(125, 53, 37, 140),
        party_hp_after=(125, 53, 37, 140),
        party_max_hp=(125, 53, 37, 140),
        party_status=(0, 0, 0, 0),
        frames_executed=100_000,
        actions_executed=500,
        controller_released=True,
    )


def test_fly_resource_report_proves_reusable_return_without_objective_label() -> None:
    report = _report()

    assert report.passed
    assert report.public_dict()["resource"] == "fly"
    assert report.public_dict()["objective_added"] is False
    assert report.public_dict()["returned_to_celadon_center"] is True
    assert len(CENTER_TO_ROUTE_16_TREE) == 60


def test_fly_resource_report_rejects_mutated_contract_fields() -> None:
    report = _report()
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, got_hm02=False),
        replace(report, dux_moves_after=DUX_MOVES_BEFORE),
        replace(report, fly_landings=()),
        replace(report, party_hp_after=(124, 53, 37, 140)),
        replace(report, controller_released=False),
    )

    assert all(not candidate.passed for candidate in invalid)
