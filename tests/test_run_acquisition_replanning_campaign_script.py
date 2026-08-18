from __future__ import annotations

import hashlib
import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_acquisition_replanning_campaign.py"),
    run_name="acquisition_replanning_campaign_script_test",
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


class _Store:
    def inspect_episode_state(self, episode_id: str) -> SimpleNamespace:
        assert len(episode_id) <= 80
        return SimpleNamespace(status="absent")


def _fixture(tmp_path: Path) -> tuple[SimpleNamespace, dict[str, object], list[object]]:
    entries = []
    lineage_rows = []
    roots = []
    assignments = {}
    for index in range(4):
        slot_id = f"red-goal-v1-{index + 1:02d}-train"
        state = tmp_path / f"{slot_id}.state"
        envelope = tmp_path / f"{slot_id}.state.json"
        profile = tmp_path / f"{slot_id}.profile.json"
        state.write_bytes(f"state:{index}".encode())
        envelope.write_bytes(f"envelope:{index}".encode())
        profile.write_bytes(f"profile:{index}".encode())
        entry = SimpleNamespace(
            slot_id=slot_id,
            state=state,
            envelope=envelope,
            profile=profile,
        )
        entries.append(entry)
        digest = f"{index + 1:x}" * 64
        assignment = SimpleNamespace(
            assignment_id=digest,
            root_lineage_id=f"red-goal-root-{digest}",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            partition="train",
        )
        assignments[slot_id] = assignment
        roots.append(
            SimpleNamespace(
                assignment=assignment,
                capture=SimpleNamespace(
                    capture_id=slot_id,
                    state_sha256=digest,
                    envelope_sha256=digest,
                ),
                entry_index=index,
                state_file_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),
                envelope_file_sha256=hashlib.sha256(envelope.read_bytes()).hexdigest(),
                profile_file_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
                question_sha256=digest,
                policy_context_sha256=digest,
                available_menu_sha256=digest,
                binding_manifest_sha256=digest,
                available_goal_kinds=(
                    GoalKind.ACQUIRE_SPECIES.value,
                    GoalKind.DEVELOP_TEAM.value,
                    GoalKind.EXPLORE.value,
                ),
            )
        )
        lineage_rows.append(
            {
                "envelope_file_sha256": hashlib.sha256(envelope.read_bytes()).hexdigest(),
                "output_profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest(),
                "slot_id": slot_id,
                "source_profile_sha256": digest,
                "state_file_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
                "transformed": True,
            }
        )

    class Registry:
        registry_sha256 = "a" * 64

        def assignment(self, slot_id: str) -> object:
            return assignments[slot_id]

    candidate = SimpleNamespace(
        catalog=SimpleNamespace(catalog_sha256="b" * 64),
        fit_summary_sha256="c" * 64,
        plan=SimpleNamespace(
            model_canonical_sha256="d" * 64,
            model_file_sha256="e" * 64,
            plan_sha256="f" * 64,
        ),
        registry=Registry(),
    )
    readiness = SimpleNamespace(
        entries=tuple(entries),
        candidate=candidate,
        context_plan_sha256="1" * 64,
        runner_sha256="2" * 64,
        numpy_runtime_sha256="3" * 64,
        runtime=SimpleNamespace(sha256="4" * 64),
        skill_manifest_sha256="5" * 64,
        source_bundle_sha256="6" * 64,
        source=SimpleNamespace(git_commit="7" * 40),
        rom_path=tmp_path / "red.gb",
        rom=SimpleNamespace(sha256="8" * 64),
    )
    lineage = {
        "builder_runner_sha256": "9" * 64,
        "builder_source_bundle_sha256": "a" * 64,
        "builder_source_commit": "b" * 40,
        "context_catalog_sha256": "b" * 64,
        "entries": lineage_rows,
        "output_plan_sha256": "1" * 64,
        "paired_plan_sha256": "c" * 64,
        "prior_campaign_sha256": ["d" * 64],
        "schema": SCRIPT["PROFILE_LINEAGE_SCHEMA"],
        "source_profile_manifest_sha256": "e" * 64,
        "source_plan_sha256": "f" * 64,
    }
    return readiness, lineage, roots


def test_parser_separates_freeze_preflight_execution_and_admission() -> None:
    parser = SCRIPT["_parser"]()
    mode = next(action for action in parser._actions if action.dest == "mode")
    assert mode.choices == ("freeze", "preflight", "execute", "admit")
    options = {option for action in parser._actions for option in action.option_strings}
    assert {
        "--profile-lineage",
        "--expected-profile-lineage-sha256",
        "--expected-development-runner-sha256",
        "--expected-campaign-sha256",
    } <= options


def test_freeze_builds_exact_four_by_four_assigned_intervention_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness, lineage, roots = _fixture(tmp_path)
    runtime = SCRIPT["_freeze"].__globals__
    base = runtime["development_runner"]
    monkeypatch.setattr(base, "_new_external_file", lambda path, **_kwargs: path)
    monkeypatch.setattr(
        base,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (_Store(), "a" * 64),
    )
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setattr(base, "_historical_root_is_open", lambda *_args: True)
    monkeypatch.setattr(
        base,
        "_inspect_root",
        lambda _readiness, _entry, *, entry_index: roots[entry_index],
    )
    monkeypatch.setattr(base, "_trial_claim_is_available", lambda *_args: True)
    destination = tmp_path / "campaign.json"
    args = SimpleNamespace(
        campaign_plan=destination,
        private_root=tmp_path / "private",
        expected_campaign_sha256=None,
        expected_profile_lineage_sha256="b" * 64,
    )

    result = SCRIPT["_freeze"](
        args,
        readiness,
        "c" * 64,
        lineage,
    )
    plan = SCRIPT["_canonical_document"](
        destination.read_bytes(), subject="campaign"
    )
    SCRIPT["_validate_campaign"](
        plan,
        readiness=readiness,
        runner_sha256="c" * 64,
        expected_profile_lineage_sha256="b" * 64,
        expected_private_root_identity_sha256="a" * 64,
    )

    assert result["status"] == "campaign_frozen_without_prediction_or_action"
    assert result["planned_trials"] == result["available_trials"] == 16
    assert len(plan["roots"]) == 4
    assert [row["assigned_intervention"] for row in plan["trials"]] == [
        "acquire_species",
        "acquire_species",
        "develop_team",
        "explore",
    ] * 4
    assert all(row["maximum_decisions"] == 2 for row in plan["trials"])
    assert max(len(row["episode_id"]) for row in plan["trials"]) <= 80
    assert result["profile_lineage_manifest_sha256"] == "b" * 64
    assert result["context_catalog_sha256"] == "b" * 64
    assert result["campaign_identity_available"] is True


def test_campaign_rejects_post_hoc_intervention_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness, lineage, roots = _fixture(tmp_path)
    runtime = SCRIPT["_freeze"].__globals__
    base = runtime["development_runner"]
    monkeypatch.setattr(base, "_new_external_file", lambda path, **_kwargs: path)
    monkeypatch.setattr(
        base,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (_Store(), "a" * 64),
    )
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setattr(base, "_historical_root_is_open", lambda *_args: True)
    monkeypatch.setattr(
        base,
        "_inspect_root",
        lambda _readiness, _entry, *, entry_index: roots[entry_index],
    )
    monkeypatch.setattr(base, "_trial_claim_is_available", lambda *_args: True)
    destination = tmp_path / "campaign.json"
    args = SimpleNamespace(
        campaign_plan=destination,
        private_root=tmp_path / "private",
        expected_campaign_sha256=None,
        expected_profile_lineage_sha256="b" * 64,
    )
    SCRIPT["_freeze"](args, readiness, "c" * 64, lineage)
    plan = json.loads(destination.read_text())
    plan["trials"][0]["assigned_intervention"] = "explore"

    with pytest.raises(
        SCRIPT["AcquisitionReplanningRunError"], match="campaign_authentication"
    ):
        SCRIPT["_validate_campaign"](
            plan,
            readiness=readiness,
            runner_sha256="c" * 64,
            expected_profile_lineage_sha256="b" * 64,
            expected_private_root_identity_sha256="a" * 64,
        )


def test_root_inventory_requires_three_genuine_goal_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness, lineage, roots = _fixture(tmp_path)
    roots[0].available_goal_kinds = (
        GoalKind.ACQUIRE_SPECIES.value,
        GoalKind.EXPLORE.value,
    )
    base = SCRIPT["_inspect_declared_roots"].__globals__["development_runner"]
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setattr(base, "_historical_root_is_open", lambda *_args: True)
    monkeypatch.setattr(
        base,
        "_inspect_root",
        lambda _readiness, _entry, *, entry_index: roots[entry_index],
    )

    with pytest.raises(
        SCRIPT["AcquisitionReplanningRunError"], match="action_free_root_inventory"
    ):
        SCRIPT["_inspect_declared_roots"](readiness, lineage)


def test_root_inventory_rejects_profile_lineage_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness, lineage, roots = _fixture(tmp_path)
    roots[0].profile_file_sha256 = "f" * 64
    base = SCRIPT["_inspect_declared_roots"].__globals__["development_runner"]
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setattr(base, "_historical_root_is_open", lambda *_args: True)
    monkeypatch.setattr(
        base,
        "_inspect_root",
        lambda _readiness, _entry, *, entry_index: roots[entry_index],
    )

    with pytest.raises(
        SCRIPT["AcquisitionReplanningRunError"],
        match="profile_lineage_root_drift",
    ):
        SCRIPT["_inspect_declared_roots"](readiness, lineage)


def test_failure_receipt_does_not_claim_protected_inputs_were_absent() -> None:
    result = SCRIPT["_failure"]("development_readiness", mode="preflight")

    assert result["protected_access_status"] == "not_attested"
    assert "sealed_red_accesses" not in result
    assert "crystal_accesses" not in result
    assert result["controller_actions"] == 0


def test_execution_failure_does_not_fabricate_zero_actions_or_predictions() -> None:
    result = SCRIPT["_failure"]("acquisition_replanning_runtime", mode="execute")

    assert result["status"] == "execution_failed_effects_not_attested"
    assert "controller_actions" not in result
    assert "model_predictions" not in result


def test_admission_failure_does_not_fabricate_zero_offline_replays() -> None:
    result = SCRIPT["_failure"]("terminal_result_differs", mode="admit")

    assert result["status"] == "admission_failed_offline_replay_not_attested"
    assert result["offline_policy_replays"] == "not_attested"
    assert "model_predictions" not in result


def test_main_admission_uses_immutable_admission_readiness(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = SCRIPT["main"].__globals__
    campaign = (Path("campaign.json"), "a" * 64, {"schema": "campaign"})
    readiness = SimpleNamespace()
    monkeypatch.setitem(
        runtime,
        "_readiness",
        lambda _args: (_ for _ in ()).throw(AssertionError("live readiness used")),
    )
    monkeypatch.setitem(
        runtime,
        "_admission_readiness",
        lambda _args: (readiness, "b" * 64, campaign),
    )
    monkeypatch.setitem(
        runtime,
        "_admit",
        lambda _args, actual, _runner, *, authenticated_campaign: {
            "schema": "admission",
            "readiness_is_exact": actual is readiness,
            "campaign_is_exact": authenticated_campaign is campaign,
        },
    )
    base = runtime["development_runner"]
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setattr(
        base,
        "fixed_account_claim_registry_lease",
        lambda *_args, **_kwargs: nullcontext(),
    )
    digest = "c" * 64
    argv = [
        "--mode",
        "admit",
        "--context-plan",
        "missing-spent-context-plan.json",
        "--profile-lineage",
        "missing-spent-lineage.json",
        "--context-catalog",
        "catalog.json",
        "--model",
        "model.json",
        "--fit-summary",
        "fit.json",
        "--expected-source-commit",
        "d" * 40,
        "--expected-source-bundle-sha256",
        digest,
        "--expected-runner-sha256",
        digest,
        "--expected-development-runner-sha256",
        digest,
        "--expected-runtime-sha256",
        digest,
        "--expected-numpy-runtime-sha256",
        digest,
        "--expected-skill-manifest-sha256",
        digest,
        "--expected-context-plan-sha256",
        digest,
        "--expected-profile-lineage-sha256",
        digest,
        "--campaign-plan",
        "campaign.json",
        "--expected-campaign-sha256",
        digest,
        "--private-root",
        "private",
    ]

    assert SCRIPT["main"](argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["readiness_is_exact"] is True
    assert result["campaign_is_exact"] is True


def test_main_sanitizes_foreign_readiness_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        runtime,
        "_readiness",
        lambda _args: (_ for _ in ()).throw(OSError("/private/root/leak")),
    )
    digest = "a" * 64
    argv = [
        "--mode",
        "preflight",
        "--context-plan",
        "plan.json",
        "--profile-lineage",
        "lineage.json",
        "--context-catalog",
        "catalog.json",
        "--model",
        "model.json",
        "--fit-summary",
        "fit.json",
        "--expected-source-commit",
        "b" * 40,
        "--expected-source-bundle-sha256",
        digest,
        "--expected-runner-sha256",
        digest,
        "--expected-development-runner-sha256",
        digest,
        "--expected-runtime-sha256",
        digest,
        "--expected-numpy-runtime-sha256",
        digest,
        "--expected-skill-manifest-sha256",
        digest,
        "--expected-context-plan-sha256",
        digest,
        "--expected-profile-lineage-sha256",
        digest,
        "--campaign-plan",
        "campaign.json",
        "--expected-campaign-sha256",
        digest,
        "--private-root",
        "private",
    ]

    assert SCRIPT["main"](argv) == 1
    output = capsys.readouterr().out
    assert "/private/" not in output
    assert '"failed_stage":"unexpected_failure"' in output


def test_campaign_reserves_all_four_standard_roots_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = tuple(
        {
            "state_sha256": f"{index + 1:x}" * 64,
            "envelope_sha256": f"{index + 5:x}" * 64,
        }
        for index in range(4)
    )
    runtime = SCRIPT["_ensure_campaign_root_reservations"].__globals__
    claims: dict[str, dict[str, str]] = {}

    def identity(*, state_sha256: str, envelope_sha256: str) -> str:
        return hashlib.sha256(f"{state_sha256}:{envelope_sha256}".encode()).hexdigest()

    def write(
        _registry: Path,
        *,
        root_consumption_sha256: str,
        execution_identity_sha256: str,
        source_commit: str,
        runner_sha256: str,
    ) -> None:
        assert root_consumption_sha256 not in claims
        claims[root_consumption_sha256] = {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            "root_consumption_sha256": root_consumption_sha256,
            "execution_identity_sha256": execution_identity_sha256,
            "source_commit": source_commit,
            "runner_sha256": runner_sha256,
        }

    monkeypatch.setitem(runtime, "root_consumption_sha256", identity)
    monkeypatch.setitem(
        runtime,
        "root_claim_is_available",
        lambda _registry, root_id: root_id not in claims,
    )
    monkeypatch.setitem(runtime, "write_root_claim", write)
    monkeypatch.setitem(
        runtime,
        "read_root_claim",
        lambda _registry, root_id: claims[root_id],
    )

    SCRIPT["_ensure_campaign_root_reservations"](
        tmp_path,
        roots,
        campaign_id="a" * 64,
        source_commit="b" * 40,
        runner_sha256="c" * 64,
    )
    SCRIPT["_ensure_campaign_root_reservations"](
        tmp_path,
        roots,
        campaign_id="a" * 64,
        source_commit="b" * 40,
        runner_sha256="c" * 64,
    )

    assert len(claims) == 4
    assert {row["execution_identity_sha256"] for row in claims.values()} == {
        "a" * 64
    }


def test_foreign_campaign_cannot_reuse_reserved_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = {"state_sha256": "1" * 64, "envelope_sha256": "2" * 64}
    runtime = SCRIPT["_root_is_available_or_reserved"].__globals__
    monkeypatch.setitem(runtime, "root_consumption_sha256", lambda **_kwargs: "3" * 64)
    monkeypatch.setitem(runtime, "root_claim_is_available", lambda *_args: False)
    monkeypatch.setitem(
        runtime,
        "read_root_claim",
        lambda *_args: {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            "root_consumption_sha256": "3" * 64,
            "execution_identity_sha256": "f" * 64,
            "source_commit": "b" * 40,
            "runner_sha256": "c" * 64,
        },
    )

    assert (
        SCRIPT["_root_is_available_or_reserved"](
            tmp_path,
            root,
            campaign_id="a" * 64,
            source_commit="b" * 40,
            runner_sha256="c" * 64,
        )
        is False
    )


def test_execute_reserves_campaign_root_and_trial_before_private_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    claims: dict[str, dict[str, object]] = {}
    campaign_id = "a" * 64
    campaign_claim = "b" * 64
    trial_claim = "c" * 64
    execution_identity = "d" * 64
    root_record = {
        "entry_index": 0,
        "root_lineage_id": "red-goal-root-" + "e" * 64,
        "state_sha256": "1" * 64,
        "envelope_sha256": "2" * 64,
    }
    trial = {
        "assigned_intervention": "acquire_species",
        "episode_id": f"red-acq-{campaign_id}-00",
        "execution_identity_sha256": execution_identity,
        "maximum_decisions": 2,
        "root_index": 0,
        "seed": 20_000,
        "trial_claim_sha256": trial_claim,
        "trial_index": 0,
    }
    plan = {
        "campaign_id": campaign_id,
        "campaign_claim_sha256": campaign_claim,
        "roots": [root_record],
        "trials": [trial],
    }
    entry = SimpleNamespace(
        slot_id="red-goal-v1-01-train",
        state=tmp_path / "state",
        envelope=tmp_path / "envelope",
        profile=tmp_path / "profile",
    )
    readiness = SimpleNamespace(
        entries=(entry,),
        source=SimpleNamespace(git_commit="f" * 40),
        rom_path=tmp_path / "red.gb",
        context_plan_path=tmp_path / "plan.json",
        context_catalog_path=tmp_path / "catalog.json",
        model_path=tmp_path / "model.json",
        fit_summary_path=tmp_path / "fit.json",
    )
    root = SimpleNamespace(
        assignment=SimpleNamespace(
            assignment_id="e" * 64,
            root_lineage_id="red-goal-root-" + "e" * 64,
        ),
        capture=SimpleNamespace(state_bytes=b"state"),
        profile=object(),
    )

    class Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            return SimpleNamespace(status="absent")

        def begin_episode(self, _episode_id: str) -> object:
            events.append("begin_private_writer")
            raise RuntimeError("stop after claim boundary")

    runtime = SCRIPT["_execute"].__globals__
    base = runtime["development_runner"]
    monkeypatch.setattr(
        base,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (Store(), "9" * 64),
    )
    monkeypatch.setitem(
        runtime,
        "_authenticated_campaign",
        lambda *_args, **_kwargs: (tmp_path / "campaign.json", "8" * 64, plan),
    )
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setitem(runtime, "_root_is_available_or_reserved", lambda *_a, **_k: True)
    monkeypatch.setattr(base, "_open_frozen_root", lambda *_a, **_k: root)
    monkeypatch.setattr(
        base,
        "_trial_claim_is_available",
        lambda _registry, claim: claim not in claims,
    )
    monkeypatch.setattr(base, "_protected_digests", lambda _paths: ())
    monkeypatch.setattr(base, "rom_adjacent_artifacts", lambda _path: ())
    monkeypatch.setitem(
        runtime,
        "_ensure_campaign_root_reservations",
        lambda *_a, **_k: events.append("reserve_roots"),
    )

    def write_claim(
        _registry: Path,
        *,
        trial_claim_sha256: str,
        execution_identity_sha256: str,
        source_commit: str,
        runner_sha256: str,
    ) -> None:
        events.append(
            "claim_campaign" if trial_claim_sha256 == campaign_claim else "claim_trial"
        )
        claims[trial_claim_sha256] = {
            "execution_identity_sha256": execution_identity_sha256,
            "runner_sha256": runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": source_commit,
            "trial_claim_sha256": trial_claim_sha256,
        }

    monkeypatch.setattr(base, "_write_trial_claim", write_claim)
    monkeypatch.setattr(
        base,
        "_read_trial_claim",
        lambda _registry, claim: claims[claim],
    )
    args = SimpleNamespace(
        expected_campaign_sha256="8" * 64,
        expected_execution_identity_sha256=execution_identity,
        expected_profile_lineage_sha256="7" * 64,
        trial_index=0,
        private_root=tmp_path / "private",
        profile_lineage=tmp_path / "lineage.json",
        campaign_plan=tmp_path / "campaign.json",
        watch=False,
        speed=None,
    )
    lineage = {
        "entries": [
            {"slot_id": entry.slot_id, "transformed": True},
        ]
    }

    with pytest.raises(RuntimeError, match="stop after claim boundary"):
        SCRIPT["_execute"](
            args,
            readiness,
            "6" * 64,
            lineage,
        )

    assert events == [
        "reserve_roots",
        "claim_campaign",
        "claim_trial",
        "begin_private_writer",
    ]


@pytest.mark.parametrize(
    ("primary_succeeds", "expected_gate"),
    ((True, True), (False, False)),
)
def test_admission_uses_all_sixteen_but_controls_cannot_rescue_primary_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    primary_succeeds: bool,
    expected_gate: bool,
) -> None:
    campaign_id = "a" * 64
    campaign_claim = "b" * 64
    runner_sha = "c" * 64
    source_commit = "d" * 40
    roots = [
        {
            "entry_index": index,
            "capture_id": f"slot-{index}",
            "root_lineage_id": f"red-goal-root-{index + 1:064x}",
            "binding_manifest_sha256": "e" * 64,
            "state_sha256": f"{index + 1:x}" * 64,
            "envelope_sha256": f"{index + 5:x}" * 64,
            "question_sha256": f"{index + 9:x}" * 64,
            "policy_context_sha256": f"{index + 10:x}" * 64,
            "available_menu_sha256": f"{index + 11:x}" * 64,
        }
        for index in range(4)
    ]
    schedule = ("acquire_species", "acquire_species", "develop_team", "explore")
    trials = []
    for index in range(16):
        trials.append(
            {
                "assigned_intervention": schedule[index % 4],
                "episode_id": f"red-acq-{campaign_id}-{index:02d}",
                "execution_identity_sha256": f"{index + 1:064x}",
                "root_index": index // 4,
                "seed": 20_000 + (index // 4) * 100 + index % 4,
                "trial_claim_sha256": f"{index + 17:064x}",
                "trial_index": index,
            }
        )
    plan = {
        "campaign_id": campaign_id,
        "campaign_claim_sha256": campaign_claim,
        "roots": roots,
        "trials": trials,
    }

    class Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            return SimpleNamespace(status="complete")

        def open_episode(self, episode_id: str) -> str:
            return episode_id

    entries = tuple(
        SimpleNamespace(slot_id=f"slot-{index}") for index in range(4)
    )
    readiness = SimpleNamespace(
        entries=entries,
        source=SimpleNamespace(git_commit=source_commit),
        rom_path=tmp_path / "red.gb",
        candidate=SimpleNamespace(
            catalog=SimpleNamespace(
                catalog_sha256="f" * 64,
                entry=lambda slot_id: SimpleNamespace(context_id=f"context:{slot_id}"),
            ),
            model=object(),
        ),
    )
    runtime = SCRIPT["_admit"].__globals__
    base = runtime["development_runner"]
    monkeypatch.setattr(
        base,
        "_open_bound_private_root",
        lambda *_a, **_k: (Store(), "1" * 64),
    )
    monkeypatch.setitem(
        runtime,
        "_authenticated_campaign",
        lambda *_a, **_k: (tmp_path / "campaign", "2" * 64, plan),
    )
    monkeypatch.setattr(base, "open_fixed_account_claim_registry", lambda: tmp_path)
    monkeypatch.setitem(
        runtime,
        "_require_campaign_root_reservations",
        lambda *_a, **_k: None,
    )

    def claim_record(_registry: Path, claim: str) -> dict[str, object]:
        if claim == campaign_claim:
            execution = campaign_id
        else:
            execution = next(
                row["execution_identity_sha256"]
                for row in trials
                if row["trial_claim_sha256"] == claim
            )
        return {
            "execution_identity_sha256": execution,
            "runner_sha256": runner_sha,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": source_commit,
            "trial_claim_sha256": claim,
        }

    monkeypatch.setattr(base, "_read_trial_claim", claim_record)

    def admitted(reader: str, **kwargs) -> SimpleNamespace:
        index = int(reader.rsplit("-", 1)[1])
        assigned = kwargs["expected_assigned_intervention"]
        primary = assigned is GoalKind.ACQUIRE_SPECIES
        first = SimpleNamespace(
            outcome_status=GoalDecisionOutcome.SUCCEEDED,
            selected_kind=assigned,
            question=SimpleNamespace(
                policy_context_sha256="3" * 64,
                available_menu_sha256="4" * 64,
            ),
        )
        second = SimpleNamespace(
            outcome_status=(
                GoalDecisionOutcome.SUCCEEDED
                if primary_succeeds or not primary
                else GoalDecisionOutcome.FAILED
            ),
            selected_kind=GoalKind.DEVELOP_TEAM,
            question=SimpleNamespace(
                policy_context_sha256="5" * 64,
                available_menu_sha256="6" * 64,
            ),
        )
        return SimpleNamespace(
            dataset=SimpleNamespace(
                manifest_sha256=f"{index + 33:064x}",
                examples=(first, second),
            ),
            targets=(object(),),
        )

    monkeypatch.setitem(runtime, "load_acquisition_replanning_episode", admitted)
    args = SimpleNamespace(
        expected_campaign_sha256="2" * 64,
        expected_execution_identity_sha256=None,
        trial_index=None,
        private_root=tmp_path / "private",
        campaign_plan=tmp_path / "campaign",
        expected_profile_lineage_sha256="7" * 64,
    )

    result = SCRIPT["_admit"](args, readiness, runner_sha)

    assert result["planned_trials"] == 16
    assert result["complete_episodes"] == 16
    assert result["diagnostic_control_complete_episodes"] == 8
    assert result["diagnostic_controls_can_rescue_primary_gate"] is False
    assert result["feasibility_gate_passed"] is expected_gate
