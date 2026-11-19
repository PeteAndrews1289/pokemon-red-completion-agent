"""Versioned TRAIN sampling keeps old teacher guards and unknown labels."""

import copy
from inspect import signature

import pytest
from test_red_teacher_case import fixture

from pokemon_red_completion.red_native_player import NativePlayerSession
from pokemon_red_completion.red_teacher_case import (
    SEQUENCE_SCHEMA,
    TeacherTrainCaseSpec,
    build_teacher_session_kwargs,
    validate_plan_case,
    validate_retained_menu,
)


def setup():
    data = fixture("047")
    case = data["case"]
    case.update(schema=SEQUENCE_SCHEMA, sequence_horizon=2)
    case["session"]["model_feature_version"] = 16
    case["native_limits"]["decisions"] = 4
    plan = data["plan"]
    plan["teacher_case"] = case
    plan["native_limits"] = copy.deepcopy(case["native_limits"])
    plan["caps"]["goals"] = 4
    return data


def test_current_teacher_sampling_is_explicit_and_not_a_hidden_consequence_override():
    data = setup()
    spec = validate_plan_case(data["plan"], data["source_row"])
    assert spec.sequence_mode
    kw = build_teacher_session_kwargs(
        spec,
        store=None,
        emulator=None,
        runtime_factory=None,
        source=dict(partition="train", state_sha256=data["case"]["source_sha256"]),
        execution=None,
        output=None,
        battle_observer=lambda: None,
        teacher_receipt_sha256="a" * 64,
        callbacks={},
    )
    signature(NativePlayerSession).bind(**kw)
    assert kw["model_feature_version"] == 16 and kw["consequence_spec"] is None
    assert kw["limits"].decisions == 4 and not kw["greedy_selection"]
    out = validate_retained_menu(
        spec, data["prior"], data["observed"], data["bindings"], data["pp"]
    )
    assert out["passed"] and not out["teacher_selected_action"]
    assert not out["historical_V10_menu_parity_claim"]


@pytest.mark.parametrize(
    "fault", ["horizon", "version", "greedy", "steps", "extra", "partition", "caps"]
)
def test_bad_sampled_teacher_declarations_fail_before_native_authority(fault):
    data = setup()
    c = data["case"]
    if fault == "horizon":
        c["sequence_horizon"] = True
    if fault == "version":
        c["session"]["model_feature_version"] = 10
    if fault == "greedy":
        c["session"]["greedy_selection"] = True
    if fault == "steps":
        c["native_limits"]["decisions"] = 5
    if fault == "extra":
        c["ignored"] = True
    if fault == "partition":
        c["partition"] = "development"
    if fault == "caps":
        data["plan"]["caps"]["goals"] = 1
    with pytest.raises(ValueError):
        validate_plan_case(data["plan"], data["source_row"])


def test_v1_does_not_silently_accept_current_sequence_fields():
    c = setup()["case"]
    c["schema"] = "pokemon.red.single-direct-teacher-case.v1"
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec.from_dict(c)


@pytest.mark.parametrize("fault", [None, "rom", "event", "map", "battle", "cash", "frame", "bytes"])
def test_scoped_trainer_native_reader_leaves_wholequests_and_losses_unknown(
    tmp_path, monkeypatch, fault
):
    from hashlib import sha256
    from types import SimpleNamespace as NS

    from test_red_sequence_state_audit import Emulator, events

    import pokemon_red_completion.red_sequence_state_audit as m

    em = Emulator()
    raw = NS(map_id=45, battle_state=0, player_money=1505, event_flags=events(86))
    monkeypatch.setattr(m, "trainer_headers", lambda *a, **k: (NS(event_flag=86),))
    monkeypatch.setattr(m, "PokemonRedStateReader", lambda e: NS(read=lambda: raw))
    if fault in ("rom", "event"):
        with pytest.raises(ValueError):
            m.ScopedTrainerSequenceStateReader(
                em,
                rom=b"rom",
                expected_rom_sha256="a" * 64 if fault == "rom" else sha256(b"rom").hexdigest(),
                maps=(41, 45),
                events=(87,) if fault == "event" else (86,),
            )
        return
    reader = m.ScopedTrainerSequenceStateReader(
        em, rom=b"rom", expected_rom_sha256=sha256(b"rom").hexdigest(), maps=(41, 45), events=(86,)
    )
    if fault == "map":
        raw.map_id = 46
    if fault == "battle":
        raw.battle_state = 1
    if fault == "cash":
        raw.player_money = True
    if fault == "frame":
        original = em.load_state_bytes

        def load(s):
            original(s)
            em.frame_count += 1

        em.load_state_bytes = load
    p = tmp_path / "state"
    p.write_bytes(b"state")
    if fault:
        with pytest.raises(ValueError):
            reader.read(p, "f" * 64 if fault == "bytes" else sha256(b"state").hexdigest())
    else:
        result = reader.read(p, sha256(b"state").hexdigest())
        assert result.progress == ("event:86",) and result.quests == () and em.frame_count == 0
        assert (
            "completed_quests" not in reader.target_channels
            and "blackouts" not in reader.target_channels
        )


@pytest.mark.parametrize(
    "fault",
    [None, "settled_failure", "unsafe_failure", "failed_with_error", "execution", "projection", "verification", "unexpected_stop", "unfinished", "unsafe"],
)
def test_safe_terminal_alone_cannot_qualify_a_failed_collection(tmp_path, monkeypatch, fault):
    import json
    from types import SimpleNamespace as NS

    from test_red_sequence_state_audit import events

    import pokemon_red_completion.red_teacher_sampled_sequence as m

    output = tmp_path / "native"
    (output / "episode/sequence").mkdir(parents=True)
    (output / "episode/sequence/result.json").write_text(
        json.dumps(dict(projection_error={} if fault == "projection" else None))
    )
    state = [False]
    finalized = []
    collector = NS(finished=fault != "unfinished")
    monkeypatch.setattr(m, "SequenceTraceCollector", lambda **kw: collector)

    def run(**kw):
        state[0] = True
        return dict(
            model_decisions=1,
            stop_reason="execution_failed"
            if fault == "unexpected_stop"
            else "declared_consequence_complete",
            outcomes=[
                dict(verification="succeeded", error_type=None),
                dict(
                    error_type="ValueError" if fault in {"execution", "failed_with_error"} else None,
                    verification="failed" if fault in {"verification", "settled_failure", "unsafe_failure", "failed_with_error"} else "succeeded",
                    ordinary_setback=fault in {"settled_failure", "unsafe_failure", "failed_with_error"},
                    safe_terminal=fault != "unsafe_failure",
                )
            ],
        )

    monkeypatch.setattr(m, "run_autonomous_options", run)
    monkeypatch.setattr(m, "finalize_native_player_session", lambda *a, **k: finalized.append(True))
    session = NS(
        output=output,
        consequence=None,
        runtime=NS(reader=NS(read=lambda: NS(event_flags=events(86) if state[0] else events()))),
        snapshot=lambda: NS(safe=fault != "unsafe"),
        observe=None,
        finish_decision=lambda: None,
        limits=NS(decisions=4, seconds=240, cash_debits=None),
    )
    result = m.run_sampled_teacher_sequence(
        session,
        NS(feature_version=16),
        source=dict(partition="train", state_sha256="a" * 64),
        spec=NS(sequence_mode=True, document=lambda: dict(sequence_horizon=2)),
        seed=1,
        contract=NS(defeated_event=86),
        write=lambda *a: None,
        output=tmp_path,
    )
    assert result["passed"] is (fault in {None, "settled_failure"}) and not result["training_admission"]
    assert finalized == [True] and not result["teacher_selected"]
