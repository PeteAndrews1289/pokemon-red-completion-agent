"""Prove the exact new callback is absent from the default historical path."""

import ast
import inspect
import textwrap

from pokemon_red_completion.red_party_development_venue_priors import _ast_node_sha256
from pokemon_red_completion.red_team_training import run_red_team_balancing


def test_disabled_reserve_callback_preserves_reviewed_team_balancing_ast():
    node = ast.parse(textwrap.dedent(inspect.getsource(run_red_team_balancing))).body[0]
    assert isinstance(node, ast.FunctionDef)

    # The separately authenticated TypedDict extension changes only the
    # construction spelling of these two optional dictionaries.
    class RemoveTypedSinkOptions(ast.NodeTransformer):
        calls = 0

        def visit_Call(self, current):
            if isinstance(current.func, ast.Name) and current.func.id == "_MoveDecisionSinkOptions":
                assert not current.args and len(current.keywords) in (0, 1)
                assert all(
                    value.arg == "move_decision_sink"
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "move_decision_sink"
                    for value in current.keywords
                )
                self.calls += 1
                return ast.copy_location(
                    ast.Dict(
                        keys=[ast.Constant(value.arg) for value in current.keywords],
                        values=[value.value for value in current.keywords],
                    ),
                    current,
                )
            return self.generic_visit(current)

    typed_sink = RemoveTypedSinkOptions()
    node = typed_sink.visit(node)
    assert typed_sink.calls == 2
    # Only these two default-None branches and their keyword are new. Erasing
    # them must reconstruct the exact immediate, already-reviewed predecessor.
    helper_index = [arg.arg for arg in node.args.kwonlyargs].index("collection_helper_xp_guard")
    assert isinstance(node.args.kw_defaults[helper_index], ast.Constant)
    assert node.args.kw_defaults[helper_index].value is None
    del node.args.kwonlyargs[helper_index]
    del node.args.kw_defaults[helper_index]

    class RemoveDisabledHelperXP(ast.NodeTransformer):
        branches = 0

        def visit_If(self, current):
            if ast.unparse(current.test) == "collection_helper_xp_guard is not None" or (
                isinstance(current.test, ast.BoolOp)
                and ast.unparse(current.test.values[0]) == "collection_helper_xp_guard is not None"
            ):
                assert not current.orelse
                self.branches += 1
                return None
            return self.generic_visit(current)

    helper = RemoveDisabledHelperXP()
    node = helper.visit(node)
    assert helper.branches == 3
    assert _ast_node_sha256(node, qualname="run_red_team_balancing") == (
        "b976dab52a263168650ab161be71a3c8da539e38acadc5a6addd8052a14e59ae"
    )
    index = [arg.arg for arg in node.args.kwonlyargs].index("evolution_stop_requested")
    assert isinstance(node.args.kw_defaults[index], ast.Constant)
    assert node.args.kw_defaults[index].value is None
    del node.args.kwonlyargs[index]
    del node.args.kw_defaults[index]

    class RemoveDisabledReserve(ast.NodeTransformer):
        branches = 0
        validations = 0

        def visit_If(self, current):
            if any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "evolution_reserve_requested"
                for n in ast.walk(current.test)
            ):
                assert isinstance(current.test, ast.BoolOp)
                assert isinstance(current.test.op, ast.And)
                assert ast.dump(current.test.values[0]) == ast.dump(
                    ast.parse("evolution_stop_requested is not None", mode="eval").body
                )
                self.branches += 1
                return None
            return self.generic_visit(current)

        def visit_BoolOp(self, current):
            expected = ast.dump(ast.parse("evolution_stop_requested is not None", mode="eval").body)
            kept = [value for value in current.values if ast.dump(value) != expected]
            if len(kept) != len(current.values):
                assert isinstance(current.op, ast.Or)
                self.validations += 1
                current.values = kept
            return self.generic_visit(current)

    remove = RemoveDisabledReserve()
    normalized = remove.visit(node)
    assert (remove.branches, remove.validations) == (1, 1)

    # Normalize only the two disclosed collection-mode additions. The entire
    # remaining historical function must still match the reviewed predecessor.
    class RemoveCollectionEfficiency(ast.NodeTransformer):
        venue_changes = 0
        observational_calls = 0

        def visit_Assign(self, current):
            if (
                len(current.targets) == 1
                and isinstance(current.targets[0], ast.Name)
                and current.targets[0].id == "target_band"
                and isinstance(current.value, ast.Call)
                and isinstance(current.value.func, ast.Name)
                and current.value.func.id == "max"
                and len(current.value.args) == 1
                and isinstance(current.value.args[0], ast.Name)
                and current.value.args[0].id == "supported"
            ):
                self.venue_changes += 1
                current.value.func.id = "min"
            return self.generic_visit(current)

        def visit_Expr(self, current):
            expected = ast.parse(
                "record_collection_training_experience(actions, reader, previous, matches[0])"
            ).body[0]
            if ast.dump(current) == ast.dump(expected):
                self.observational_calls += 1
                return None
            return self.generic_visit(current)

    collection = RemoveCollectionEfficiency()
    normalized = collection.visit(normalized)
    assert (collection.venue_changes, collection.observational_calls) == (1, 1)
    # Baseline is the existing Windows-qualified actor with helper exclusions;
    # this existing assertion was stale before the helper-XP change; independent
    # saved-baseline normalization establishes the corrected digest.
    assert _ast_node_sha256(normalized, qualname="run_red_team_balancing") == (
        "6d2a54013974b364957842d62af613a53d0ea1a8af88736050c632dc34f585a4"
    )
