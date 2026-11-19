"""A shorter actor window must stay bound throughout the native target join."""
import json
from dataclasses import asdict, replace
from hashlib import sha256

import pytest
import test_red_sequence_native_audit as trace_fixture
from test_red_sequence_verified_targets import setup

import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


@pytest.mark.parametrize('fault', [None, 'missing', 'tampered', 'later', 'caps'])
def test_native_target_join_authenticates_soft_window(tmp_path, monkeypatch, fault):
    original_setup = trace_fixture.setup
    original_run = native.run_autonomous_options
    order = tmp_path / 'prospective-work-order.json'

    def configured_setup(*args, **kwargs):
        configured, executed = original_setup(*args, **kwargs)
        configured['limits'] = replace(configured['limits'], seconds=30, actions=3, decisions=3)
        caps = asdict(configured['limits'])
        if fault == 'caps':
            caps['actions'] += 1
        order.write_text(json.dumps(dict(admission_seconds=31 if fault == 'later' else 10,
                                        native_limits=caps)))
        configured['source'] = dict(configured['source'],
                                    experiment_sha256=sha256(order.read_bytes()).hexdigest())
        return configured, executed

    def earlier_admission(**kwargs):
        kwargs['maximum_seconds'] = 10
        return original_run(**kwargs)

    monkeypatch.setattr(trace_fixture, 'setup', configured_setup)
    monkeypatch.setattr(native, 'run_autonomous_options', earlier_admission)
    root, args, executed = setup(tmp_path, monkeypatch)
    if fault == 'tampered':
        order.write_text(order.read_text() + ' ')
    if fault != 'missing':
        args['actor_work_order'] = order
    if fault is not None:
        with pytest.raises(ValueError):
            verify_sequence_target_channels(root, **args)
    else:
        complete, partial = verify_sequence_target_channels(root, **args)
        assert complete.targets.known == (True, True, True, True, True, True, False)
        assert not any(partial.targets.known)
        assert not complete.training_eligible and not partial.training_eligible
    assert executed == [2, 4, 6]
    assert args['reader'].emulator.frame_count == 0
