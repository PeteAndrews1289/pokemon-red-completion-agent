"""No-controller tests for prospective production-matched TRAIN admission."""
import copy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as N
import unittest

from pokemon_red_completion.red_production_train_admission import (
    ADMISSION_SCHEMA, ProductionTrainAdmission, SOURCE_ORIGIN, SOURCE_STATES, SOURCE_PROVENANCE,
    STORY_CONTENT, STORY_MODEL, WILD_CONTENT, WILD_MODEL,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def admitted():
    state=sorted(SOURCE_STATES)[0]
    envelope,progress=SOURCE_PROVENANCE[state]
    initial=ProductionTrainAdmission(state,SOURCE_ORIGIN,"a"*40,"b"*64,envelope,progress)
    plan=json.dumps(dict(partition="train",production_train_components=initial.declaration()),sort_keys=True).encode()
    return replace(initial,work_order_sha256=sha256(plan).hexdigest())


def scope_and_actor(role="wild"):
    admission = admitted()
    scope = N(source_state_sha256=admission.source_state_sha256,
        root_lineage_id=admission.root_lineage_id, work_order_sha256=admission.work_order_sha256,
        model_sha256=WILD_MODEL if role=="wild" else STORY_MODEL,
        model_content_sha256=WILD_CONTENT if role=="wild" else STORY_CONTENT,
        map_id=15, contract=N(objective_id="defeat_misty",battle_plan_id="defeat_misty",
            map_id=65,trainer_identity=(235,35,1),defeated_event=191,victory_money=2079,
            victory_items=((211,1),),victory_badge_bits=2),
        gym_reward=N(objective_id="defeat_misty"),allow_learned_tactics=True,
        diagnostic_status_entry=True,screen_capped_status_moves=True,
        diagnostic_stay_when_productive=False,diagnostic_prompt_stay=False,
        diagnostic_status_release=False)
    actor=N(source_partition=ScenarioPartition.TRAIN,source_commit=admission.source_commit,
        source_state_sha256=admission.source_state_sha256,root_lineage_id=admission.root_lineage_id,
        pp_depleted_switch_screen=(role=="story"),mechanics_aware_tower_choices=False,
        diagnostic_tower_productive_stay=False)
    return admission,scope,actor


class TestProductionTrainAdmission(unittest.TestCase):
    def test_document_roundtrip_and_identity(self):
        a=admitted();b=ProductionTrainAdmission.from_document(a.document())
        self.assertEqual(a,b);self.assertEqual(a.identity,b.identity)
        self.assertEqual(a.root_lineage_id,"red-goal-root-"+SOURCE_ORIGIN)
        self.assertIs(a.document()["fit_admission"],False)

    def test_development_or_unknown_source_cannot_be_claimed(self):
        for state in ("360287cd0ab58c4e8a3dc27406ad5ec750af892fbfcacab9f3f74bcedd5f2138",
                      "5cea1a4932d6d5f40b9be07e9d46d9d5110ecc5d2569020d38a583bb1b40c6b3", "f"*64):
            with self.subTest(state=state),self.assertRaises(ValueError):
                replace(admitted(),source_state_sha256=state)

    def test_changed_model_or_extra_document_field_rejected(self):
        for field,value in (("wild_model_sha256","f"*64),("fit_admission",True),("extra",0)):
            d=admitted().document();d[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                ProductionTrainAdmission.from_document(d)

    def test_both_exact_production_scopes_are_accepted(self):
        for role in ("wild","story"):
            a,s,actor=scope_and_actor(role)
            a.require_scope(s,role);a.require_actor(actor,s,role)

    def test_wrong_source_scope_model_target_and_settings_rejected(self):
        mutations=[("source_state_sha256","f"*64),("root_lineage_id","foreign"),
            ("work_order_sha256","f"*64),("model_sha256","f"*64),
            ("model_content_sha256","f"*64)]
        for role in ("wild","story"):
            for field,value in mutations:
                a,s,actor=scope_and_actor(role);setattr(s,field,value)
                with self.subTest(role=role,field=field),self.assertRaises(ValueError):
                    a.require_actor(actor,s,role)
        a,s,actor=scope_and_actor();s.map_id=22
        with self.assertRaises(ValueError):a.require_actor(actor,s,"wild")
        for field,value in (("allow_learned_tactics",False),("diagnostic_status_entry",False),
            ("screen_capped_status_moves",False),("diagnostic_stay_when_productive",True),
            ("diagnostic_prompt_stay",True),("diagnostic_status_release",True)):
            a,s,actor=scope_and_actor("story");setattr(s,field,value)
            with self.subTest(field=field),self.assertRaises(ValueError):
                a.require_actor(actor,s,"story")

    def test_wrong_actor_partition_source_or_pp_configuration_rejected(self):
        for role in ("wild","story"):
            for field,value in (("source_partition",ScenarioPartition.DEVELOPMENT),
                ("source_commit","f"*40),("source_state_sha256","f"*64),
                ("root_lineage_id","foreign"),("pp_depleted_switch_screen",role!="story"),
                ("mechanics_aware_tower_choices",True),("diagnostic_tower_productive_stay",True)):
                a,s,actor=scope_and_actor(role);setattr(actor,field,value)
                with self.subTest(role=role,field=field),self.assertRaises(ValueError):
                    a.require_actor(actor,s,role)

    def test_unbound_or_wrong_observed_parent_rejected(self):
        for contract in (None, N(objective_id="defeat_erika")):
            a,s,actor=scope_and_actor("story");s.contract=contract
            with self.subTest(contract=contract),self.assertRaises(ValueError):
                a.require_scope(s,"story")

    def test_direct_constructor_cannot_authorize_development_or_missing_plan_scope(self):
        for document in ({"partition":"development"}, {"partition":"train"},
            {"partition":"development","production_train_components":admitted().declaration()}):
            payload=json.dumps(document,sort_keys=True).encode()
            a=replace(admitted(),work_order_sha256=sha256(payload).hexdigest())
            with self.subTest(document=document),self.assertRaises(ValueError):
                a.require_work_order(payload)

    def test_original_metadata_pair_is_required_even_for_direct_constructor(self):
        for field in ("envelope_sha256","progress_sha256"):
            with self.subTest(field=field),self.assertRaises(ValueError):
                replace(admitted(),**{field:"f"*64})

    def test_matching_train_plan_has_exact_witness(self):
        a=admitted()
        payload=json.dumps(dict(partition="train",production_train_components=a.declaration()),sort_keys=True).encode()
        a.require_work_order(payload)

    def test_changed_work_order_rejected_without_inputs(self):
        with self.assertRaises(ValueError):admitted().require_work_order(b"changed")


if __name__=="__main__":unittest.main()
