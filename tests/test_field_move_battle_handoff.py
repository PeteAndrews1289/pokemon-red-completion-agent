from dataclasses import replace
import pytest
from pokemon_red_completion.actions import MacroAction,MacroActionKind
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort,Gen1FieldMoveError
from test_gen1_field_moves import MenuWorld,surf_state

@pytest.mark.parametrize("battle",[1,2])
@pytest.mark.parametrize("trigger",[MacroActionKind.MOVE,MacroActionKind.OPEN_MENU,MacroActionKind.CONFIRM])
def test_field_move_yields_before_any_further_menu_input(battle,trigger):
    class InterruptedMenu(MenuWorld):
        interrupted_at=None
        def execute(self,action):
            result=super().execute(action)
            if self.interrupted_at is None and action.kind is trigger:
                self.raw=replace(self.raw,battle_state=battle)
                self.interrupted_at=len(self.actions)
            return result
    world=InterruptedMenu()
    port=Gen1FieldMovePort(world,world,world)
    with pytest.raises(Gen1FieldMoveError):
        port.execute(MacroAction(MacroActionKind.FIELD_MOVE,'surf:right'))
    assert world.interrupted_at is not None
    assert len(world.actions)==world.interrupted_at
    assert port.receipts==[]

def test_cursor_does_not_accept_stale_matching_cursor_during_battle():
    world=MenuWorld(raw=replace(surf_state(),battle_state=1),stage='party',cursor=1)
    with pytest.raises(Gen1FieldMoveError):
        Gen1FieldMovePort(world,world,world)._select_cursor(1,'party holder')
    assert world.actions==[]

@pytest.mark.parametrize("live_kind",['wild_battle','trainer_battle',None])
@pytest.mark.parametrize("with_handler",[True,False])
def test_route_requires_live_confirmation_and_handler_for_compound_yield(live_kind,with_handler):
    from pokemon_red_completion.route_executor import RouteActionInterrupted,RouteExecutionError,InterruptionReceipt,execute_route
    from pokemon_red_completion.route_plan import plan_route
    from pokemon_red_completion.global_router import MacroGraph
    from pokemon_red_completion.local_router import LocalGraph,LocalEdge
    from test_route_executor import FakeWorld
    class World(FakeWorld):
        first=True
        def execute(self,action):
            if self.first and action.kind is MacroActionKind.MOVE:
                self.first=False;self.actions.append(action);self.interruption=live_kind
                raise RouteActionInterrupted('wild_battle')
            return super().execute(action)
    world=World(transitions={(1,(0,0),'right'):(1,(0,1))})
    class Handler:
        calls=0
        handled_interruption_kinds=frozenset({'wild_battle'})
        def handle(self,observation):
            self.calls+=1;world.interruption=None
            return InterruptionReceipt('wild_battle',1,(0,0))
    handler=Handler()
    plan=plan_route(MacroGraph({1:()}),{1:LocalGraph({(0,0):(LocalEdge((0,1),'right'),),(0,1):()})},1,(0,0),1,goal_at=(0,1))
    if live_kind=='wild_battle' and with_handler:
        report=execute_route(plan,world,world,interruption_handler=handler)
        assert report.passed and handler.calls==1 and world.at==(0,1)
        assert sum(a.kind is MacroActionKind.MOVE for a in world.actions)==2
    else:
        with pytest.raises(RouteExecutionError):execute_route(plan,world,world,interruption_handler=handler if with_handler else None)
        assert handler.calls==0
