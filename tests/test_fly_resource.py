from dataclasses import replace

from pokemon_red_completion.cinnabar import (
    DUX_MOVES_AFTER,
    DUX_MOVES_BEFORE,
    DUX_PP_AFTER,
    DUX_PP_BEFORE,
)
from pokemon_red_completion.fly_resource import (
    CELADON_CENTER_TO_OUTDOORS,
    CENTER_TO_ROUTE_16_TREE,
    CINNABAR_CENTER_TO_OUTDOORS,
    FLY_RESOURCE_CHECKPOINT_COUNT,
    CinnabarFlyArrivalReport,
    FlyRelocationReport,
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


def _relocation_report() -> FlyRelocationReport:
    initial = replace(
        _raw(),
        map_id=MapId.CINNABAR_POKECENTER,
        first_party_moves=(44, 70, 61, 57),
        first_party_pp=(25, 15, 20, 15),
    )
    final = replace(initial, map_id=MapId.CELADON_POKECENTER)
    bag = ((4, 1), (15, 7), (int(ItemId.HM02_FLY), 1))
    return FlyRelocationReport(
        initial_raw=initial,
        final_raw=final,
        initial_bag=bag,
        final_bag=bag,
        dux_moves=DUX_MOVES_AFTER,
        dux_pp_before=DUX_PP_AFTER,
        dux_pp_after=DUX_PP_AFTER,
        fly_landings=((int(MapId.CELADON_CITY), 49),),
        party_hp_before=(125, 53, 37, 140),
        party_hp_after=(125, 53, 37, 140),
        party_max_hp_before=(125, 53, 37, 140),
        party_max_hp_after=(125, 53, 37, 140),
        party_status_before=(0, 0, 0, 0),
        party_status_after=(0, 0, 0, 0),
        frames_executed=10_000,
        actions_executed=100,
        controller_released=True,
    )


def test_fly_relocation_report_proves_story_neutral_celadon_return() -> None:
    report = _relocation_report()

    assert CINNABAR_CENTER_TO_OUTDOORS == ("down",) * 5
    assert report.passed
    assert report.public_dict()["relocation"] == "cinnabar_to_celadon_by_fly"
    assert report.public_dict()["objective_added"] is False


def test_fly_relocation_report_rejects_protected_state_drift() -> None:
    report = _relocation_report()
    invalid = (
        replace(report, final_bag=report.final_bag[:-1]),
        replace(report, dux_pp_after=(35, 15, 30, 14)),
        replace(report, fly_landings=()),
        replace(report, party_hp_after=(124, 53, 37, 140)),
        replace(report, controller_released=False),
    )

    assert all(not candidate.passed for candidate in invalid)


def test_cinnabar_fly_arrival_proves_story_neutral_island_relocation() -> None:
    initial = replace(
        _raw(),
        first_party_moves=(44, 70, 61, 57),
        first_party_pp=(25, 15, 20, 15),
    )
    final = replace(initial, map_id=MapId.CINNABAR_POKECENTER)
    bag = ((4, 1), (15, 7), (int(ItemId.HM02_FLY), 1))
    report = CinnabarFlyArrivalReport(
        initial, final, bag, bag, DUX_MOVES_AFTER, DUX_PP_AFTER, DUX_PP_AFTER,
        ((int(MapId.CINNABAR_ISLAND), 11),),
        (125, 53, 37, 140), (125, 53, 37, 140),
        (125, 53, 37, 140), (125, 53, 37, 140),
        (0, 0, 0, 0), (0, 0, 0, 0), 10_000, 100, True,
    )

    assert CELADON_CENTER_TO_OUTDOORS == ("down",) * 5
    assert report.passed
    assert replace(
        report,
        initial_raw=replace(
            report.initial_raw,
            map_id=MapId.CELADON_CITY,
            player_x=49,
            player_y=11,
        ),
    ).passed
    assert not replace(report, final_bag=report.final_bag[:-1]).passed
