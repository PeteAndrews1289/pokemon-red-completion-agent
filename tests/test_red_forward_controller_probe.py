"""A controller-return probe must rejoin its entire real authenticated batch."""

from copy import deepcopy

import pytest
from test_red_forward_controller_batch import batch, load

from pokemon_red_completion.forward_goal_learning import fit_forward_goal
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_forward_controller_batch import CONTROLLER_RETURN_CONTRACT
from pokemon_red_completion.red_forward_probe import (
    load_red_forward_controller_probe,
    load_red_forward_probe,
)


def fitted(tmp_path, *, mutate=None):
    items = batch(tmp_path)
    store, good, _, batch_sha = items
    admitted = load(items)
    result = fit_forward_goal(admitted.outcomes)
    rows = sorted(admitted.outcomes, key=lambda row: row.choice.decision_sha256)
    doc = {
        "schema": "pokemon.red.forward-controller-shadow-fit.v1",
        "return_contract": CONTROLLER_RETURN_CONTRACT,
        "authority": "unqualified-shadow",
        "player_model_changed": False,
        "independent_evaluation": False,
        "in_game_loss_inferred": False,
        "behavior_model_sha256": good.model.model_sha256,
        "model": result.model.public_dict(),
        "model_sha256": result.model.sha256,
        "batch_record_id": "controller-batch",
        "batch_record_sha256": batch_sha,
        "outcomes": [row.public_dict() for row in rows],
        "episodes": sorted(admitted.episode_requests, key=lambda row: row["episode_id"]),
        "cancelled_episode_ids": list(admitted.cancelled_episode_ids),
        "failed_controller_stops": admitted.failed_stops,
    }
    if mutate:
        mutate(doc)
    identity = "red-ctrl-fit-" + canonical_sha256(doc)
    saved = store.publish_sealed_record(
        identity, kind="red_forward_controller_shadow_fit", record=doc
    )
    return store, good, result.model, identity, saved.summary.record_sha256


def probe(items, **changes):
    store, good, model, identity, sha = items
    return load_red_forward_controller_probe(
        store,
        **{
            "record_id": identity,
            "expected_record_sha256": sha,
            "expected_model_sha256": model.sha256,
            "behavior_model": good.model,
            "tail_seed": 41,
            **changes,
        },
    )


def test_controller_probe_requires_explicit_loader_and_preserves_authority_boundary(tmp_path):
    items = fitted(tmp_path)
    spec = probe(items)
    assert spec.model.sha256 == items[2].sha256
    assert spec.tail_model_sha256 == items[1].model.model_sha256
    assert spec.fit_contract == CONTROLLER_RETURN_CONTRACT
    assert spec.header()["authority"] == "bounded-training-probe-not-production"
    assert spec.header()["fit_contract"] == CONTROLLER_RETURN_CONTRACT
    assert not spec.header()["calibrated_probabilities"]
    assert not spec.header()["recursive_forward_control"]
    with pytest.raises((ValueError, PrivateArtifactError)):
        load_red_forward_probe(
            items[0],
            record_id=items[3],
            expected_record_sha256=items[4],
            expected_model_sha256=items[2].sha256,
            tail_seed=41,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(authority="production"),
        lambda d: d.update(return_contract="ideal-player"),
        lambda d: d.update(independent_evaluation=True),
        lambda d: d.update(in_game_loss_inferred=True),
        lambda d: d.update(player_model_changed=True),
        lambda d: d.update(behavior_model_sha256="f" * 64),
        lambda d: d.update(model_sha256="f" * 64),
        lambda d: d.update(batch_record_sha256="f" * 64),
        lambda d: d["outcomes"].pop(),
        lambda d: d["outcomes"].append(deepcopy(d["outcomes"][0])),
        lambda d: d["episodes"].pop(),
        lambda d: d.update(cancelled_episode_ids=[]),
        lambda d: d.update(failed_controller_stops=0),
        lambda d: d.update(failed_controller_stops=True),
    ],
)
def test_rehashed_fit_cannot_change_authority_or_hide_admitted_evidence(tmp_path, mutation):
    with pytest.raises((ValueError, PrivateArtifactError)):
        probe(fitted(tmp_path, mutate=mutation))


@pytest.mark.parametrize(
    "key,value",
    [
        ("expected_record_sha256", "f" * 64),
        ("expected_model_sha256", "f" * 64),
        ("tail_seed", -1),
        ("tail_seed", True),
    ],
)
def test_exact_probe_identity_and_tail_seed_required(tmp_path, key, value):
    with pytest.raises(ValueError):
        probe(fitted(tmp_path), **{key: value})
