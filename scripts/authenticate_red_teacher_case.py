"""Shared closeout adapter for the existing native/root/Windows receipt chain."""

import argparse
import fcntl
import hashlib
import json
import pwd
import runpy
import shutil
from datetime import UTC, datetime
from pathlib import Path


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify_partial_teacher_outcome(outcome):
    """Read the recorder's public target-array schema without inventing fields."""
    import math

    names = [
        "verified_success",
        "completion_gain",
        "dependency_unlock_gain",
        "action_cost",
        "frame_cost",
        "resource_cost",
        "party_cost",
        "storage_cost",
        "irreversible_loss",
    ]
    assert outcome["schema"] == "pokemon.core.living-dex-observed-outcome.v1"
    assert outcome["status"] == "settled" and outcome["censor_reason"] is None
    assert outcome["target_names"] == names
    values = outcome["target_values"]
    assert type(values) is list and len(values) == len(names)
    assert all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values)
    assert values[:3] == [1.0, 0.0, 0.0]


def verify_venue_teacher_outcome(plan, result, document, decision, setup=None):
    """Authenticate one measured TRAIN arm; a pair still needs separate admission."""
    high_level = plan["schema"] == "pokemon.red.native-venue-workload-TRAIN-case.v2"
    assert high_level or plan["schema"] == "pokemon.red.native-venue-geometry-TRAIN-case.v1"
    assert result["teacher_selected"] is True
    model_mode = plan.get("sources", [{}])[0].get("venue_mode", "teacher") == "model"
    partition = plan.get("sources", [{}])[0].get("execution_partition", "train")
    admission = not model_mode and partition == "train" and not plan.get("validation_role")
    assert result["training_admission"] is admission
    assert result["new_fits"] == result["new_weights"] == 0
    assert result["copy_back"] is False and result["campaign_progress"] is False
    assert document["fit_eligible"] is admission and document["actual_progress"] is False
    assert document["settled_native_attempt"] is True
    assert document["controller_costs_are_full_native_totals"] is True
    assert document["frames"] == result["frames"] and document["actions"] == result["actions"]
    assert document["terminal_state_sha256"] == result["terminal_sha256"]
    assert document["prospective_binding"] == decision["binding"]
    assert document["candidate_set"] == decision["candidate_set"]
    assert (
        decision["teacher_forced_venue"] is (not model_mode)
        and decision["outcomes_not_opened"] is True
    )
    assert document["assigned_index"] == decision["assigned_index"]
    if model_mode:
        assert plan["validation_role"] == document["validation_role"]
        assert plan["validation_role"] in {
            "exposed-TRAIN-component-no-admission",
            "exposed-TRAIN-component-comparison-only",
        }
        if plan["validation_role"] == "exposed-TRAIN-component-comparison-only":
            assert plan["fit_allowed"] is False and plan["diagnostic_only"] is True
            assert plan["party_venue_fit_eligible"] is False
        assert document["model_selected_venue"] is True
        assert high_level or plan["sources"][0]["xp_condition"] == "original"
        events = result["native_outcome"]["venue_choice_events"]
        assert len(events) == 1
        event = events[0]["payload"]
        assert event["actor"] == "learned_venue_model" and event["model_selected"] is True
        assert event["model_sha256"] == decision["model_sha256"] == plan["venue_model_sha256"]
        assert event["selected_index"] == decision["assigned_index"]
        assert event["candidate_count"] == len(decision["candidate_set"]["candidates"])
        assert event["candidate_count"] == (
            3 if high_level or plan.get("ordinary_full_venue_menu") else 2
        )
        # The existing live selector leaves optional geometry unknown. This
        # candidate freezes those rows at zero; require every other covariate.
        actual_menu = event["candidate_set"]
        quoted_menu = decision["candidate_set"]
        for actual, quoted in zip(
            actual_menu["candidates"], quoted_menu["candidates"], strict=True
        ):
            assert actual["candidate_index"] == quoted["candidate_index"]
            assert actual["feature_schema_id"] == quoted["feature_schema_id"]
            af, qf = actual["features"], quoted["features"]
            assert set(af) == set(qf)
            assert all(
                af[name] == qf[name]
                for name in af
                if not name.startswith(("venue.travel_steps", "venue.recovery_steps"))
            )
    assert decision["binding"]["partition"] == partition
    if partition == "development":
        assert plan["source_kind"] == "exposed_historical_development"
        assert plan["validation_role"] == "related-DEV-matched-component-no-admission"
        assert plan["sources"][0]["xp_condition"] == "original"
    expected = plan["source_sha256"]
    if plan.get("sources", [{}])[0].get("xp_condition", "original") != "original":
        assert setup is not None
        assert setup["partition"] == setup["evaluation_partition"] == "train"
        assert setup["teacher_only"] is True
        if high_level:
            assert setup["xp_condition"] == "fixture_level"
            assert setup["current_level"] == plan["sources"][0]["fixture_level"]
            assert setup["non_target_party_fields_unchanged"] is True
            assert setup["native_protected_party_fields_unchanged"] is False
            assert setup["writes"] and plan["allow_direct_evolution"] is True
        else:
            assert setup["xp_condition"] == "near_next_level"
        assert setup["original_state_sha256"] == plan["source_sha256"]
        assert setup["frames"] == setup["inputs"] == 0
        if not high_level:
            assert setup["native_protected_party_fields_unchanged"] is True
        if high_level:
            # The witness reader reconciles the ordinary nursing prefix against
            # sealed inputs. Setup and prospective-menu states are distinct.
            prefix = decision["common_prefix_inputs"]
            frames = decision["common_prefix_frames"]
            assert type(prefix) is int and 0 <= prefix <= result["actions"]
            assert type(frames) is int and 0 <= frames <= result["frames"]
            assert decision["all_common_prefix_costs_included"] is True
            if prefix == 0:
                assert frames == 0 and setup["state_sha256"] == decision["state_sha256"]
        else:
            assert setup["state_sha256"] == decision["state_sha256"]
        expected = setup["state_sha256"]
    assert decision["binding"]["initial_state_sha256"] == expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--spec-sha256", required=True)
    args = parser.parse_args(argv)
    if sha(args.spec) != args.spec_sha256:
        raise ValueError("launch specification differs")
    spec = read(args.spec)
    phase = spec["phase"]
    case = Path(spec["case"]).resolve()
    if case.parent != Path(spec["capacity_root"]).resolve() or phase not in ("preflight", "direct"):
        raise ValueError("case scope differs")
    D = case / "preflight" if phase == "preflight" else case
    W = Path(spec["windows_receipt_directory_linux"])
    plan = read(spec["plan"])
    with (Path(spec["source_lock"])).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        claim = read(Path(spec["source_claim"]))
        assert (
            claim["source_writer_mission"] == spec["mission"]
            and claim.get("active_probe") == str(D)
            and not claim["actual_running"]
        )
        for k in [
            "worker",
            "plan",
            "package",
            "supervisor",
            "resource_plan",
            "guard",
            "process_chain",
            "closeout",
        ]:
            assert sha(spec[k]) == spec[k + "_sha256"]
        for p, h in spec["additional_pins"].items():
            assert sha(p) == h
        early = read(D / "EARLY-LINUX-IDENTITY.json")
        assert (
            early["plan_sha256"] == spec["plan_sha256"]
            and early["worker_sha256"] == spec["worker_sha256"]
        )
        sameboot = Path("/proc/sys/kernel/random/boot_id").read_text().strip() == early["boot_id"]
        for row in [*early["processes"], early["supervisor"]]:
            p = Path("/proc") / str(row["pid"])
            if sameboot and p.exists():
                assert (
                    int((p / "stat").read_text().split(") ", 1)[1].split()[19])
                    != row["start_ticks"]
                )
        launch_id = spec["identity"]
        win = read(W / (launch_id + ".windows-current.json"))
        launch = read(W / (launch_id + ".windows-launch.json"))
        root = read(D / "ROOT-EXIT-RECEIPT.json")
        setup = read(D / "ROOT-RESOURCE-RECEIPT.json")
        assert (
            root["plan_sha256"] == spec["resource_plan_sha256"]
            and setup["plan_sha256"] == spec["resource_plan_sha256"]
        )
        assert not root["remaining_pids"]
        group = Path(root["group"]) / "cgroup.procs"
        assert not group.exists() or not group.read_text().strip()
        resource = read(spec["resource_plan"])
        chain = runpy.run_path(spec["process_chain"])["validate_chain"](
            spec,
            resource,
            early,
            setup,
            root,
            launch,
            win,
            pokemon_uid=pwd.getpwnam("pokemon").pw_uid,
            now=datetime.now(UTC),
        )
        result = read(D / "RESULT.json")
        passed = result["passed"] and root["native_exit_code"] == 0 and not root["timed_out"]
        native = phase != "preflight"
        closeout = runpy.run_path(spec["closeout"])["classify_closed_phase"](
            result,
            phase=phase,
            processes_absent=True,
            cgroup_empty=True,
            terminal_sha256=sha(D / "terminal.state") if (D / "terminal.state").exists() else None,
        )
        controls = closeout["controls_released"]
        auth = dict(
            schema="pokemon.red.machine-value-terminal.v1",
            observed_at_utc=datetime.now(UTC).isoformat(),
            phase=phase,
            passed=passed,
            plan_sha256=spec["plan_sha256"],
            package_sha256=spec["package_sha256"],
            worker_sha256=spec["worker_sha256"],
            all_original_processes_absent=True,
            controls_released=controls,
            supervisor_cgroup_empty=True,
            windows_parents_absent=True,
            native_exit_code=root["native_exit_code"],
            timed_out=root["timed_out"],
            root_seconds=root["seconds"],
            full_hold_seconds=resource["outer_seconds"],
            error=result.get("error"),
            error_type=result.get("error_type"),
            traceback=result.get("traceback"),
            actual_credit=0,
            fits=0,
            new_weights=0,
        )
        auth["exact_parent_chain"] = chain
        auth["closed_phase_classification"] = closeout
        auth["worker_result_sha256"] = sha(D / "RESULT.json")
        auth["authentication_adapter_sha256"] = sha(Path(__file__))
        auth["finish_error"] = result.get("finish_error")
        auth["finish_traceback"] = result.get("finish_traceback")
        if native:
            if passed:
                pp = read(D / "LIVE-PP-PREINPUT-GATE.json")
                assert (
                    pp["passed"] and pp["source_bytes_exact"] and pp["inputs"] == pp["frames"] == 0
                )
                noncombat = plan.get("teacher_case", {}).get("schema") in {
                    "pokemon.red.noncombat-story-unit-teacher-case.v1",
                    "pokemon.red.noncombat-story-unit-teacher-case.v2",
                    "pokemon.red.noncombat-story-unit-teacher-case.v3",
                }
                if noncombat:
                    assert (
                        result["goal_attempts"]
                        == (1 if plan["teacher_case"]["schema"].endswith(".v3") else 2)
                        and result["story_battles"] == 0
                    )
                    assert result["teacher_selected"] is True
                    row = result["row"]
                    assert row["feature_version"] == 16 and row["features"][-4:] == [
                        1.0,
                        0.0,
                        1.0,
                        1.0,
                    ]
                    outcome = row["outcome"]
                    verify_partial_teacher_outcome(outcome)
                    assert result["training_admission"] is True
                    assert result["copy_back"] is False and result["campaign_progress"] is False
                elif plan.get("schema") in {
                    "pokemon.red.native-venue-geometry-TRAIN-case.v1",
                    "pokemon.red.native-venue-workload-TRAIN-case.v2",
                }:
                    verify_venue_teacher_outcome(
                        plan,
                        result,
                        read(D / "PARTY-VENUE-OUTCOME.json"),
                        read(D / "PROSPECTIVE-VENUE-DECISION.json"),
                        setup=read(D / "SETUP-RECEIPT.json"),
                    )
                else:
                    assert result["goal_attempts"] == 1 and result["story_battles"] == 1
                auth["live_pp_preinput_gate_sha256"] = sha(D / "LIVE-PP-PREINPUT-GATE.json")
            physical = closeout["physical_emulator_accounting"]
            pre = (
                read(D / "PREINPUT-QUALIFICATION.json")
                if (D / "PREINPUT-QUALIFICATION.json").exists()
                else None
            )
            if passed:
                assert (
                    pre
                    and pre["passed"]
                    and pre["source_bytes_exact"]
                    and pre["source_state_sha256"] == plan["source_sha256"]
                    and physical
                    == dict(
                        construction_attempts=1,
                        emulators_constructed=1,
                        load_attempts=1,
                        state_loads=1,
                    )
                )
            row = result.get("row")
            auth.update(
                terminal_sha256=result.get("terminal_sha256"),
                source_state_sha256=plan["source_sha256"],
                original_TRAIN_state_sha256=plan["original_TRAIN_state_sha256"],
                shared_origin_id=plan["shared_origin_id"],
                preinput_verified=bool(pre and pre["passed"]),
                physical_emulator_accounting=physical,
                admitted=result.get("admitted", False),
                row=row,
                training_admission=result.get("training_admission", False),
                native_costs=closeout["native_costs"],
                field_ready=result.get("field_ready"),
                separate_acquisition_cost=plan["separate_acquisition_cost"],
                sealed_row_reloaded_by_worker=bool(row and passed),
            )
            if row:
                assert row["partition"] == "train" if "partition" in row else True
        else:
            auth.update(
                zero_emulator_preflight=True,
                qualification_sha256=sha(D / "QUALIFICATION.json")
                if (D / "QUALIFICATION.json").exists()
                else None,
            )
        for kind in ["launch", "current"]:
            shutil.copyfile(
                W / (launch_id + ".windows-" + kind + ".json"), D / ("WINDOWS-" + kind + ".json")
            )
        with (D / "TERMINAL-AUTHENTICATION.json").open("x") as f:
            json.dump(auth, f, indent=2, sort_keys=True)
            f.write("\n")
        claim = read(Path(spec["source_claim"]))
        claim.update(active_probe=None, all_native_workers_stopped=True)
        (Path(spec["source_claim"])).write_text(json.dumps(claim, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in auth.items()
                    if k not in ["row", "traceback", "separate_acquisition_cost"]
                }
            )
        )
        if native and row:
            print(
                json.dumps(dict(outcome=row.get("outcome"), censor_reason=row.get("censor_reason")))
            )


if __name__ == "__main__":
    main()
