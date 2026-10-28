"""Strict single-direct TRAIN declarations and shared native session configuration.

This is a teacher-data collector contract, not policy-selection authority. Source
custody, package authentication, admission, and process closeout remain separate.
"""
from dataclasses import dataclass
from copy import deepcopy
import json
import math
import re

SCHEMA = "pokemon.red.single-direct-teacher-case.v1"
SESSION = {
    "model_feature_version": 10,
    "include_live_pp_readiness": True,
    "force_resource_safety": True,
    "allow_collection_restoration": True,
    "continue_safe_route_failures": False,
    "greedy_selection": False,
    "allow_greedy_branch_recovery": False,
    "refine_preparation": False,
}
FIELDS = {
    "schema", "mode", "partition", "role", "initial_kind", "seed",
    "opening_idle_frames", "initial_history", "source_sha256",
    "source_origin_sha256", "original_train_state_sha256", "combat_specimen_refs",
    "exact_contract", "challenge_target", "session", "native_limits",
    "restoration_home_map", "expected_menu",
}
CONTRACT_FIELDS = {
    "battle_plan_id", "defeated_event", "map_id", "objective_id",
    "trainer_identity", "victory_badge_bits", "victory_items", "victory_money",
}
MENU_FIELDS = {"candidate_count", "selected_index", "selected_binding", "challenge",
               "private_binding_parity", "prior_pp", "prior_seconds_may_differ"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _exact(actual, expected, label):
    require(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), label)


@dataclass(frozen=True)
class TeacherTrainCaseSpec:
    """Canonical immutable JSON; callers receive copies, never mutable backing data."""
    _json: str

    @classmethod
    def from_dict(cls, value):
        return cls(cls._canonical_document(value))

    def __post_init__(self):
        require(type(self._json) is str, "canonical teacher case JSON required")
        require(self._json == self._canonical_document(json.loads(self._json)), "noncanonical teacher case JSON")

    @staticmethod
    def _canonical_document(value):
        require(isinstance(value, dict) and set(value) == FIELDS, "teacher case fields differ")
        require(value["schema"] == SCHEMA, "teacher case schema differs")
        require(value["mode"] in ("observed_story_obstruction", "blaine_leader"), "unsupported direct case mode")
        require((value["partition"], value["role"], value["initial_kind"]) ==
                ("train", "train_sampling", "advance_story"), "only original direct TRAIN supported")
        require(type(value["seed"]) is int and value["seed"] >= 0, "explicit seed required")
        require(type(value["opening_idle_frames"]) is int and value["opening_idle_frames"] == 0,
                "only offset zero supported")
        require(value["initial_history"] == "observed_none", "postloss/history cases excluded")
        for key in ("source_sha256", "source_origin_sha256", "original_train_state_sha256"):
            require(isinstance(value[key], str) and re.fullmatch(r"[0-9a-f]{64}", value[key]), key)
        refs = value["combat_specimen_refs"]
        require(isinstance(refs, list) and all(isinstance(ref, str) and ref.startswith("red-preparation:") for ref in refs)
                and len(refs) == len(set(refs)) == 6,
                "exact six combat roles required")
        _exact(value["session"], SESSION, "explicit live-equivalent session settings differ")
        limits = value["native_limits"]
        require(isinstance(limits, dict) and set(limits) ==
                {"decisions", "actions", "frames", "heals", "cash_debits", "seconds"}, "limits fields differ")
        require(type(limits["decisions"]) is int and limits["decisions"] == 1, "one direct phase only")
        for key in ("actions", "frames", "heals"):
            require(type(limits[key]) is int and limits[key] > 0, "finite native limit required: " + key)
        require(type(limits["seconds"]) in (int, float) and math.isfinite(limits["seconds"])
                and limits["seconds"] > 0, "finite native seconds required")
        require(limits["cash_debits"] is None or
                (type(limits["cash_debits"]) is int and limits["cash_debits"] >= 0), "cash cap invalid")
        contract = value["exact_contract"]
        require(isinstance(contract, dict) and set(contract) == CONTRACT_FIELDS, "exact contract fields differ")
        from .observation import EVENT_FLAG_BYTES
        from .red_story_battle import StoryTrainerContract
        for key in ("objective_id", "battle_plan_id"):
            require(type(contract[key]) is str and bool(contract[key].strip()), "native contract text invalid: " + key)
        require(type(contract["map_id"]) is int and 0 <= contract["map_id"] <= 255, "native map byte invalid")
        require(type(contract["defeated_event"]) is int and 0 <= contract["defeated_event"] < EVENT_FLAG_BYTES * 8,
                "native event index invalid")
        require(isinstance(contract["trainer_identity"], list) and len(contract["trainer_identity"]) == 3 and
                all(type(x) is int and 0 <= x <= 255 for x in contract["trainer_identity"]), "trainer identity invalid")
        require(type(contract["victory_money"]) is int and 0 < contract["victory_money"] <= 999999, "native money invalid")
        require(type(contract["victory_badge_bits"]) is int and 0 <= contract["victory_badge_bits"] <= 255, "native badge byte invalid")
        items = contract["victory_items"]
        require(isinstance(items, list) and all(isinstance(pair, list) and len(pair) == 2 and
                type(pair[0]) is int and 1 <= pair[0] <= 255 and type(pair[1]) is int and 1 <= pair[1] <= 99 for pair in items),
                "native item reward pairs invalid")
        require(len({pair[0] for pair in items}) == len(items), "duplicate native item reward")
        # Reuse existing trainer-class/offset/set constraints instead of inventing
        # a second trainer identity interpretation.
        StoryTrainerContract(**dict(contract, trainer_identity=tuple(contract["trainer_identity"]),
                                   victory_items=tuple(tuple(pair) for pair in items)))
        _exact(value["challenge_target"], dict(kind="events", map_id=contract["map_id"],
               events=[contract["defeated_event"]]), "target must be exact declared native contract")
        require(type(value["restoration_home_map"]) is int and 0 <= value["restoration_home_map"] <= 255,
                "restoration home map byte required")
        if value["mode"] == "observed_story_obstruction":
            require(contract["battle_plan_id"] == "observed-story-obstruction" and
                    contract["victory_badge_bits"] == 0 and contract["victory_items"] == [],
                    "obstruction cannot inherit a leader reward")
        else:
            require(contract["battle_plan_id"] == contract["objective_id"] == "defeat_blaine" and
                    contract["trainer_identity"] == [239, 39, 1] and contract["defeated_event"] == 665 and
                    contract["map_id"] == 166 and contract["victory_badge_bits"] == 64 and
                    contract["victory_items"] == [[238, 1]], "Blaine reward contract differs")
        menu = value["expected_menu"]
        require(isinstance(menu, dict) and set(menu) == MENU_FIELDS, "expected menu fields differ")
        require(type(menu["candidate_count"]) is int and menu["candidate_count"] > 1 and
                type(menu["selected_index"]) is int and 0 <= menu["selected_index"] < menu["candidate_count"],
                "full menu size/selection invalid")
        require(isinstance(menu["selected_binding"], str) and menu["selected_binding"].startswith("pokemon.red:story-battle:"),
                "retained exact direct binding required")
        require(type(menu["private_binding_parity"]) is bool and menu["prior_pp"] in ("unknown", "observed_full")
                and menu["prior_seconds_may_differ"] is True, "menu comparison scope invalid")
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def document(self):
        return json.loads(self._json)

    @property
    def mode(self):
        return self.document()["mode"]


def validate_plan_case(plan, source_row):
    spec = TeacherTrainCaseSpec.from_dict(plan["teacher_case"])
    data = spec.document()
    aliases = {"source_sha256": "source_sha256", "original_TRAIN_state_sha256": "original_train_state_sha256",
               "expected_combat_specimen_refs": "combat_specimen_refs", "exact_contract": "exact_contract",
               "challenge_target": "challenge_target", "native_limits": "native_limits", "seed": "seed",
               "initial_kind": "initial_kind", "opening_idle_frames": "opening_idle_frames", "role": "role"}
    for old, new in aliases.items():
        _exact(plan[old], data[new], "plan/spec disagreement: " + old)
    require(plan.get("include_live_pp_readiness") is True and plan.get("source_prior_battle_history", "missing") is None,
            "explicit plan PP/history required")
    require(plan["arm"] == "direct" and plan["caps"]["new_fits"] == 0 and
            plan["caps"]["emulators"] == plan["caps"]["state_loads"] == plan["caps"]["goals"] == 1,
            "one-load direct collector scope differs")
    require(plan["copy_back"] is False and plan["campaign_writes"] is False, "teacher copy is not campaign progress")
    require(source_row["source_partition"] == "train" and source_row["role"] == "train_sampling" and
            source_row["state_sha256"] == data["original_train_state_sha256"] and
            source_row["source_origin_sha256"] == data["source_origin_sha256"], "TRAIN ancestry differs")
    return spec


def build_teacher_session_kwargs(spec, *, store, emulator, runtime_factory, source,
                                 execution, output, battle_observer, teacher_receipt_sha256, callbacks):
    """Preflight and execution call this same constructor, including PP and history."""
    from .red_native_player import NativePlayerLimits
    from .red_challenge_consequence import ChallengeConsequenceSpec
    from .goal_manager import GoalKind
    data = spec.document()
    require(source["partition"] == "train" and source["state_sha256"] == data["source_sha256"], "session source differs")
    require(callable(battle_observer), "live history provider required")
    require(set(callbacks) <= {"enumerate_bindings", "enumerate_supplements", "observe_challenges", "observe_preparations"},
            "callbacks cannot override session authority")
    require(isinstance(teacher_receipt_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", teacher_receipt_sha256),
            "explicit teacher setup receipt required")
    return dict(store=store, emulator=emulator, runtime_factory=runtime_factory, source=source,
                execution=execution, output=output, limits=NativePlayerLimits(**data["native_limits"]),
                combat_specimen_refs=tuple(data["combat_specimen_refs"]), battle_observer=battle_observer,
                target_cash=0, collection_teacher_setup_receipt=teacher_receipt_sha256,
                consequence_spec=ChallengeConsequenceSpec(GoalKind.ADVANCE_STORY, data["challenge_target"],
                    maximum_phases=1, feedback_version=2, include_challenge_arrival=True, machine_lesson=None),
                **data["session"], **callbacks)


def validate_source_boundary(spec, observed, emit):
    """Retain the named observation before raising; do not reinterpret x/y tuples."""
    emit(deepcopy(observed))
    data = spec.document()
    require(observed["source_sha256"] == data["source_sha256"], "loaded bytes differ")
    require(observed["combat_specimen_refs"] == data["combat_specimen_refs"], "combat role order differs")
    require(observed["map_id"] == data["exact_contract"]["map_id"], "source native map differs")
    require(observed["inputs"] == observed["frames"] == 0 and observed["pressed_buttons"] == [], "source changed before observation")


def story_binding_settings(spec, leader_reward):
    """Preserve the two existing executor semantics, including absence of reward."""
    if spec.mode == "blaine_leader":
        require(leader_reward.objective_id == "defeat_blaine", "leader reward identity differs")
        return dict(completes_objective=True, reward=leader_reward)
    return dict(completes_objective=False, reward=None)


def validate_retained_menu(spec, prior, menu, bindings, pp):
    """Only prospective PP observation and new marginal elapsed budget may differ."""
    expected = spec.document()["expected_menu"]
    count, selected = expected["candidate_count"], expected["selected_index"]
    require(len(prior["menu"]["candidates"]) == len(menu["candidates"]) == len(bindings) == count, "full menu size differs")
    require(len({row["binding_ref"] for row in bindings}) == count, "ambiguous binding refs")
    require(bindings[selected] == dict(binding_ref=expected["selected_binding"], kind="advance_story") and
            [i for i, row in enumerate(bindings) if row["kind"] == "advance_story"] == [selected], "exact direct choice differs")
    if expected["private_binding_parity"]:
        _exact(prior["bindings"], bindings, "retained private binding order differs")
    slots = [slot for member in pp["party_slots"] for slot in member if slot[1] > 0]
    require(len(pp["party_slots"]) == 6 and slots and all(a == b for a, b in slots), "observed PP is not full")
    left, right = deepcopy(prior["menu"]), deepcopy(menu)
    changes = []
    for index, (a, b) in enumerate(zip(left["candidates"], right["candidates"], strict=True)):
        x, y = a["readiness"], b["readiness"]
        require(x["schema"] == y["schema"] == "pokemon.core.player-readiness-no-history.v1"
                and x["names"] == y["names"], "history/readiness schema differs")
        for name, old, new in zip(x["names"], x["values"], y["values"], strict=True):
            if name in ("current.pp_known", "current.pp_fraction"):
                require(old == (0 if expected["prior_pp"] == "unknown" else 1) and new == 1, "live PP contract differs")
                changes.append(dict(index=index, feature=name, before=old, after=new))
            elif name == "budget.seconds":
                require(type(new) in (int, float) and math.isfinite(new) and 0 < new <= 1, "marginal time invalid")
                changes.append(dict(index=index, feature=name, before=old, after=new))
            else:
                _exact(old, new, "unexpected readiness change: " + name)
        y["values"] = list(x["values"])
    _exact(left, right, "unexpected non-readiness menu change")
    _exact(menu["candidates"][selected]["challenge"], expected["challenge"], "exact observed challenge differs")
    return dict(passed=True, changes=changes, all_other_public_menu_fields_exact=True,
                selected_direct_binding_exact=True, private_all_binding_parity_claim=expected["private_binding_parity"],
                history="observed none", raw_pp=pp, challenge=expected["challenge"])
