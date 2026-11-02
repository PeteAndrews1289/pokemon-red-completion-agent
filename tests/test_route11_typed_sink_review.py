"""Exact typing-only extension proof; synthetic source rows never grant runtime authority."""

import ast
import copy
from pathlib import Path

import pytest
from route11_historical_fixture import historical_venue_source as historical_venue_source

from pokemon_red_completion import red_party_development_venue_priors as prior
from pokemon_red_completion import red_team_training as training


def source_node(name):
    tree = ast.parse(Path(training.__file__).read_text())
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name
    )


def project_root():
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent, parent / "Code"):
            if (candidate / "src/pokemon_red_completion/red_team_training.py").is_file():
                return candidate
    raise AssertionError("project root missing")


def test_typed_sink_constructors_reconstruct_exact_reviewed_balancer():
    class Undo(ast.NodeTransformer):
        count = 0

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == "_MoveDecisionSinkOptions":
                assert not node.args
                assert len(node.keywords) in (0, 1)
                assert all(
                    k.arg == "move_decision_sink"
                    and isinstance(k.value, ast.Name)
                    and k.value.id == "move_decision_sink"
                    for k in node.keywords
                )
                self.count += 1
                return ast.copy_location(
                    ast.Dict(
                        keys=[ast.Constant(k.arg) for k in node.keywords],
                        values=[k.value for k in node.keywords],
                    ),
                    node,
                )
            return self.generic_visit(node)

    undo = Undo()
    restored = undo.visit(source_node("run_red_team_balancing"))
    assert undo.count == 2
    assert (
        prior._ast_node_sha256(restored, qualname="run_red_team_balancing")
        == prior._ROUTE_11_REVIEWED_PREDECESSOR_AST_SHA256[
            "red.run-team-balancing-before-typed-sink"
        ]
    )


def test_typed_sink_definition_and_runtime_dictionaries_are_exact():
    expected = ast.parse(
        "class _MoveDecisionSinkOptions(TypedDict, total=False):\n"
        "    move_decision_sink: MoveDecisionSink\n"
    ).body[0]
    assert ast.dump(source_node("_MoveDecisionSinkOptions")) == ast.dump(expected)
    events = []
    sink = events.append
    disabled = training._MoveDecisionSinkOptions()
    enabled = training._MoveDecisionSinkOptions(move_decision_sink=sink)
    assert type(disabled) is dict and disabled == {}
    assert type(enabled) is dict and tuple(enabled) == ("move_decision_sink",)
    assert enabled["move_decision_sink"] is sink and not events
    enabled["move_decision_sink"]({"phase": "synthetic"})
    assert events == [{"phase": "synthetic"}]


@pytest.mark.parametrize("mutation", [None, "constructor", "class"])
def test_source_authentication_requires_exact_typed_sink_and_balancer(monkeypatch, mutation):
    # The real historical source is read. A synthetic current commit lets this
    # test examine the production rejection gate before a candidate is committed.
    root = project_root()
    observed_commit = prior.RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT
    observed_rows = prior._committed_source_element_rows(root, revision=observed_commit)
    current_rows = prior._loaded_source_element_rows()
    if mutation is not None:
        name = "run_red_team_balancing" if mutation == "constructor" else "_MoveDecisionSinkOptions"
        node = copy.deepcopy(source_node(name))
        if mutation == "constructor":
            calls = [
                item
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "_MoveDecisionSinkOptions"
                and item.keywords
            ]
            assert len(calls) == 1
            calls[0].keywords[0].value = ast.Constant(None)
            element = "red.run-team-balancing"
        else:
            node.keywords[0].value = ast.Constant(True)
            element = "red.move-decision-sink-options"
        changed = prior._ast_node_sha256(node, qualname=name)
        current_rows = tuple(
            {**row, "ast_sha256": changed} if row["element_id"] == element else row
            for row in current_rows
        )
    monkeypatch.setattr(
        prior,
        "committed_source_bundle_sha256",
        lambda _root, *, revision: (
            prior.RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256
            if revision == observed_commit
            else "b" * 64
        ),
    )
    monkeypatch.setattr(
        prior,
        "_committed_source_element_rows",
        lambda _root, *, revision: observed_rows if revision == observed_commit else current_rows,
    )
    monkeypatch.setattr(prior, "_loaded_source_element_rows", lambda: current_rows)

    def authenticate():
        return prior.attest_red_route_11_source_compatibility(
            root, current_commit="c" * 40, current_source_bundle_sha256="b" * 64
        )

    if mutation is not None:
        with pytest.raises(
            prior.RedPartyDevelopmentVenuePriorError, match="unreviewed Route 11 source drift"
        ):
            authenticate()
    else:
        attestation = authenticate()
        assert "red.move-decision-sink-options" in attestation.waived_elements
        assert attestation.observed_commit == observed_commit
        assert (
            attestation.unchanged_elements_sha256
            == "6a5e45df1a9b79636ead10f94c287567bce3808d895a60b0cf4cd0c2113debfc"
        )
