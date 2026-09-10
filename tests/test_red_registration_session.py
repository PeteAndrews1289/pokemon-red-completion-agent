from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_private_artifacts import _make_store
from test_registered_learning_bridge import observations

from pokemon_red_completion.red_player_checkpoint import REGISTERED_PLAYER_CHECKPOINT_SCHEMA
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registration_session import (
    load_registration_policy,
    observe_registration,
    publish_registration_session,
    read_registration_state,
    validate_terminal_registration,
)
from pokemon_red_completion.registration_memory import RegistrationMemory


def session(tmp_path):
    _, before, _, _ = observations(tmp_path / "fixture")
    row = observe_registration(
        before,
        seen=frozenset(range(1, 152)),
        run_id="red-test",
        rom_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        sequence=0,
    )
    _, _, store = _make_store(tmp_path)
    ledger_path = tmp_path / "ledger.sqlite3"
    document = publish_registration_session(
        store,
        name="test",
        ledger_path=ledger_path,
        observation=before,
        row=row,
        anchor_episode_id="actual-parent",
        anchor_checkpoint_sha256="c" * 64,
    )
    return before, row, document, ledger_path


def test_runtime_adapter_and_planner_share_the_same_registered_observation(tmp_path):
    import run_paired_red_bounded_player as runner
    runtime, _, _, policy = observations(tmp_path)
    bound = runner._registered_runtime(SimpleNamespace(registration_policy=policy), runtime)
    fresh = bound.adapter.observe()
    assert fresh.registered_checkpoint is not None
    assert runner._training_observation(bound).public_dict() == fresh.public_dict()
    assert runtime.adapter.observe().registered_checkpoint is None


def test_direct_missing_evolved_capture_is_not_masked_by_future_evolution(tmp_path):
    from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
    from pokemon_red_completion.red_collection import red_species_ref
    _, before, _, policy = observations(tmp_path)
    source, target = red_species_ref(77), red_species_ref(78)
    catalog = replace(RED_ACQUISITION_CATALOG, remaining_demand=True,
                      registered_species=policy.registered(before.collection_observation))
    counts = catalog.alternative_capture_holdings(before.collection_observation, (source, target))
    assert counts[source] == 1  # existing precursor is enough, no duplicate demand
    assert counts[target] == 1  # immediate new registration remains a legal alternative


def test_session_roundtrip_actual_party_reserves_and_idempotent_durable_import(tmp_path):
    before, row, document, ledger_path = session(tmp_path)
    policy = load_registration_policy(document)
    assert policy.initial_collection == before.collection_observation
    assert sum(policy.protected_counts.values()) == 6
    assert policy.sha256 == document["policy_sha256"]
    ledger = RegistrationMemory(ledger_path)
    original = ledger.snapshot().sha256
    ledger.record(row)
    assert RegistrationMemory(ledger_path).snapshot().sha256 == original
    assert ledger.snapshot().latest("red-test") == row
    damaged = deepcopy(document)
    damaged["policy"]["protected_counts"] = {}
    with pytest.raises(ValueError, match="policy differs"):
        load_registration_policy(damaged)


@pytest.mark.parametrize("damage", [None, "state", "binding", "inventory", "sequence"])
def test_terminal_row_joins_actual_checkpoint_before_ledger_commit(tmp_path, damage):
    before, row, document, _ = session(tmp_path)
    policy = load_registration_policy(document)
    checkpoint = project_registered_observation(before, policy).registered_checkpoint.public_dict()
    terminal = {
        "schema": REGISTERED_PLAYER_CHECKPOINT_SCHEMA,
        "collection": checkpoint,
        "state_sha256": "d" * 64,
        "registration_observation": replace(row, sequence=1, snapshot_sha256="d" * 64).document(),
    }
    if damage == "state":
        terminal["state_sha256"] = "e" * 64
    elif damage == "binding":
        terminal["collection"]["binding_sha256"] = "f" * 64
    elif damage == "inventory":
        terminal["registration_observation"]["physical_counts"][0][1] += 1
    elif damage == "sequence":
        terminal["registration_observation"]["sequence"] = 2
    if damage:
        with pytest.raises(ValueError):
            validate_terminal_registration(terminal, policy, sequence=1, rom_sha256="a" * 64)
    else:
        assert (
            validate_terminal_registration(
                terminal,
                policy,
                sequence=1,
                rom_sha256="a" * 64,
            ).snapshot_sha256
            == "d" * 64
        )


@pytest.mark.parametrize("advance", [False, True])
def test_registration_sampling_is_action_free(tmp_path, advance):
    runtime, before, _, _ = observations(tmp_path)
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: b"state")

    def observe():
        emulator.frame_count += int(advance)
        return before

    runtime = replace(runtime, adapter=SimpleNamespace(observe=observe))
    if advance:
        with pytest.raises(ValueError, match="action-free"):
            read_registration_state(emulator, runtime)
    else:
        assert read_registration_state(emulator, runtime)[0] == before


@pytest.mark.parametrize("failed", [False, True])
def test_registered_regional_choice_reconstructs_real_versioned_target(
    tmp_path, monkeypatch, failed
):
    from test_red_regional_choice_learning import _recorded

    from pokemon_red_completion.red_regional_choice_learning import load_red_regional_choice_example
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    _, before, _, policy = observations(tmp_path / "fixture")
    specimen = before.collection_observation.specimens[-1]
    after = replace(before, capture_item_count=before.capture_item_count - 1)
    if not failed:
        after = replace(
            after,
            collection_observation=replace(
                after.collection_observation,
                specimens=(
                    *after.collection_observation.specimens,
                    replace(specimen, slot_index=1),
                ),
            ),
        )
    pair = tuple(project_registered_observation(o, policy) for o in (before, after))
    # Fixture isolates the new regional label path; separate bridge tests reject
    # a missing authenticated continuation with the real admission function.
    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_dataset._require_continuation_origin",
        lambda *_: None,
    )
    directory = tmp_path / "episode"
    directory.mkdir()
    store, item, expected = _recorded(directory, failed=failed, registered_pair=pair)
    actual = load_red_regional_choice_example(store, item, objective=REGISTERED_OBJECTIVE)
    assert actual.public_dict() == expected.public_dict()
    assert actual.outcome.completion_gain == 0  # duplicate, not novelty
    assert actual.outcome.verified_success is not failed
    with pytest.raises(ValueError):
        load_red_regional_choice_example(store, item)
