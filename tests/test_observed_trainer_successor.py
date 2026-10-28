from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
from pokemon_red_completion.route_executor import (
    InterruptionReceipt, RouteExecutionError, TraversalSnapshot,
    _pending_verified_interruption,
)


def handler_fixture(*, active=True, verified=True, fault=None):
    calls = []
    receipt = InterruptionReceipt(
        'wild_battle', 35, (22, 11), {'verified': verified},
    )
    if fault == 'different_claim':
        receipt.details['pending_interruption_kind'] = 'scripted_dialogue'
    raw = N(battle_state=2 if fault == 'battle' else 0,
            map_id=3 if fault == 'map' else 35,
            player_y=21 if fault == 'position' else 22, player_x=11)
    reader = N(read=lambda: raw)
    if fault != 'legacy_reader':
        reader.trainer_engagement_active = lambda: active
    inner = N(handle=lambda event: calls.append(event) or receipt)
    handler = EngagedStoryRouteHandler(
        inner, reader, lambda: pytest.fail('successor certification chose a binding'),
    )
    initial = TraversalSnapshot(35, (22, 11), False, 'wild_battle')
    return handler, initial, receipt, calls


@pytest.mark.parametrize('active', [True, False, 1, None])
def test_verified_successor_survives_the_existing_portable_route_guard(active):
    handler, initial, original, calls = handler_fixture(active=active)
    receipt = handler.handle(initial)
    successor = TraversalSnapshot(35, (22, 11), False, 'trainer_engagement')
    assert _pending_verified_interruption(receipt, successor) is (active is True)
    assert not _pending_verified_interruption(
        receipt, TraversalSnapshot(35, (22, 11), False, 'scripted_dialogue'),
    )
    assert calls == [initial]
    assert 'pending_interruption_kind' not in original.details


@pytest.mark.parametrize('fault', ['battle', 'map', 'position', 'different_claim'])
def test_native_successor_cannot_hide_divergent_boundaries_or_another_claim(fault):
    handler, initial, _, calls = handler_fixture(fault=fault)
    with pytest.raises(RouteExecutionError, match='successor'):
        handler.handle(initial)
    assert calls == [initial]


@pytest.mark.parametrize('verified', [False, 1, None])
def test_unverified_receipts_never_acquire_successor_authority(verified):
    handler, initial, original, _ = handler_fixture(verified=verified)
    assert handler.handle(initial) is original
    assert not _pending_verified_interruption(
        original, TraversalSnapshot(35, (22, 11), False, 'trainer_engagement'),
    )


def test_legacy_reader_keeps_its_original_receipt():
    handler, initial, original, calls = handler_fixture(fault='legacy_reader')
    assert handler.handle(initial) is original
    assert calls == [initial]

