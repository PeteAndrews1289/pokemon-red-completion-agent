"""Hash-pinned historical test evidence, independent of private Git history.

Only original historical revisions are supplied from this public fixture.
Current committed source, loaded-source comparison, closure and waiver checks
continue through the unmodified production implementation.
"""

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion import red_cave_venue_prior as cave
from pokemon_red_completion import red_party_development_venue_priors as prior

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "route11-historical-source.json"
FIXTURE_SHA256 = "76e1892c663dfc18695f2fe30cffdc1b31e09cb0cba3bbd60bdc3629f271e7fe"
REVIEWED_TRAINING_COMMIT = "ba9d32c9b84a1eefedce438023e9637b6d77f868"


def historical_document():
    payload = FIXTURE_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256:
        raise AssertionError("historical venue fixture bytes differ")
    document = json.loads(payload)
    assert document["schema"] == "pokemon.tests.route11-historical-source-fixture.v1"
    observed = document["observed"]
    assert observed["source_commit"] == prior.RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT
    assert observed["source_bundle_sha256"] == (
        prior.RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256
    )
    assert [row["element_id"] for row in observed["elements"]] == [
        spec.element_id for spec in prior._ROUTE_11_SOURCE_ELEMENTS
    ]
    assert document["cave"]["source_commit"] == cave.RED_CAVE_MEASUREMENT_SOURCE_COMMIT
    assert document["cave"]["source_bundle_sha256"] == (
        cave.RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256
    )
    return document


def reviewed_balancer_source():
    reviewed = historical_document()["reviewed_balancer"]
    assert reviewed["source_commit"] == REVIEWED_TRAINING_COMMIT
    source = reviewed["function_source"].encode("utf-8")
    assert hashlib.sha256(source).hexdigest() == reviewed["function_source_sha256"]
    assert (
        prior._committed_element_ast_sha256(source, qualname="run_red_team_balancing")
        == reviewed["function_ast_sha256"]
        == (prior._ROUTE_11_REVIEWED_PREDECESSOR_AST_SHA256["red.run-team-balancing"])
    )
    return source


@pytest.fixture(autouse=True)
def historical_venue_source(monkeypatch):
    """Supply frozen historical bytes; retain the production AST reader."""
    historical_document()
    original_bundle = prior.committed_source_bundle_sha256
    original_blob = prior.committed_executable_source_blob
    original_cave_rows = cave._committed_runtime_rows
    observed_commit = prior.RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT

    def source_bundle(root, *, revision):
        if revision == observed_commit:
            return historical_document()["observed"]["source_bundle_sha256"]
        return original_bundle(root, revision=revision)

    def source_blob(root, *, revision, relative_path):
        if revision != observed_commit:
            return original_blob(root, revision=revision, relative_path=relative_path)
        rows = historical_document()["observed"]["source_files"]
        matched = [row for row in rows if row["relative_path"] == relative_path]
        assert len(matched) == 1
        source = matched[0]["projection_source"].encode("utf-8")
        assert hashlib.sha256(source).hexdigest() == matched[0]["projection_sha256"]
        return source

    def cave_rows(root, *, revision):
        if revision == cave.RED_CAVE_MEASUREMENT_SOURCE_COMMIT:
            return tuple(historical_document()["cave"]["runtime_rows"])
        return original_cave_rows(root, revision=revision)

    monkeypatch.setattr(prior, "committed_source_bundle_sha256", source_bundle)
    monkeypatch.setattr(prior, "committed_executable_source_blob", source_blob)
    monkeypatch.setattr(cave, "_committed_runtime_rows", cave_rows)
    # The production parser must reconstruct every original row. Later negative
    # tests still mutate this blob-read seam and must be rejected by attestation.
    assert prior._committed_source_element_rows(
        Path(__file__).resolve().parents[1], revision=observed_commit
    ) == tuple(historical_document()["observed"]["elements"])
