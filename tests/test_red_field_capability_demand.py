from dataclasses import dataclass,field
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_field_capability_demand as mod
from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@dataclass(frozen=True)
class World:
    mode:str='needs_cut'
    object_blockers:dict=field(default_factory=dict)
    local_graphs:dict=field(default_factory=dict)
    terrain:dict=field(default_factory=dict)
    rom:object=None
    calls:list=field(default_factory=list)
    def _graph_for_terrain(self,_):raise AssertionError('empty fixture')
    def with_current_observation(self,_):return self
    def plan_feasible_to_map(self,start,destination):
        self.calls.append((start.capabilities,destination))
        if self.mode=='blocked' or (self.mode!='already_reachable' and CUT_CAPABILITY not in start.capabilities):
            raise RoutePlanningError('observed route remains blocked')
        kind='walk'if self.mode in {'already_reachable','no_cut_step'}else'cut_mutation'
        return N(steps=(N(kind=kind,expected_map=destination,expected_at=(2,2)),))
    def plan_to_map(self,start,destination):return self.plan_feasible_to_map(start,destination)


@pytest.mark.parametrize('mode,expected',[('needs_cut',1),('already_reachable',0),('no_cut_step',0),('blocked',0)])
def test_only_a_real_conditional_cut_mutation_can_witness_demand(mode,expected):
    world=World(mode);start=TraversalSnapshot(map_id=5,at=(4,11),ready=True,capabilities=frozenset({'observed-other-capability'}))
    before=start
    witnesses=mod.quote_missing_cut_dependencies(world,start,(('unfamiliar-legal-objective',20),))
    assert len(witnesses)==expected and start==before
    assert all('observed-other-capability'in caps for caps,_ in world.calls)
    if witnesses:assert witnesses[0].cut_count==1 and witnesses[0].objective_ref=='unfamiliar-legal-objective'


def test_objective_permutations_change_private_witness_not_capability_claim():
    world=World();start=TraversalSnapshot(map_id=5,at=(4,11),ready=True)
    a=mod.quote_missing_cut_dependencies(world,start,(('alpha',20),))
    b=mod.quote_missing_cut_dependencies(world,start,(('different-title-objective',20),))
    assert a[0].route_sha256==b[0].route_sha256 and a[0].cut_count==b[0].cut_count


def test_closed_story_gate_is_not_erased_to_offer_a_carrier():
    world=World('blocked');start=TraversalSnapshot(map_id=5,at=(4,11),ready=True)
    assert mod.quote_missing_cut_dependencies(world,start,(('legal-but-still-gated',20),))==()


@pytest.mark.parametrize('fault',[None,'no_badge','no_hm','already_cut','no_legal_goal'])
def test_observed_permission_and_legal_destination_contract_is_read_only(monkeypatch,fault):
    raw=N(bag_items=() if fault=='no_hm' else ((196,1),),badge_bits=0 if fault=='no_badge' else 3,
          party_moves=((15,0,0,0),)if fault=='already_cut'else((33,0,0,0),))
    runtime=N(reader=N(read=lambda:raw),emulator=N(save_state_bytes=lambda:b'exact-native-state'),
        adapter=N(graph=N(available_objectives=lambda _:()if fault=='no_legal_goal'else(N(id='reach_lavender'),))))
    start=TraversalSnapshot(map_id=5,at=(4,11),ready=True)
    monkeypatch.setattr(mod,'Gen1TraversalObserver',lambda *a,**k:N(observe=lambda:start))
    monkeypatch.setattr(mod,'Gen1TrainerSightProjector',lambda *a,**k:None)
    monkeypatch.setattr(mod,'ground_route_capability_projector',lambda *a,**k:None)
    witnesses=mod.observed_cut_dependencies(runtime,N(game_state=None),route=N(route_world=World(),rom=b'rom'))
    assert bool(witnesses)is(fault is None)
    assert runtime.emulator.save_state_bytes()==b'exact-native-state'
