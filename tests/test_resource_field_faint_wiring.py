"""ROM-free caller regression;existing native poison certificate tests cover its strict proof."""
from dataclasses import replace
import pytest
from test_red_resource_goal_router import fixture
from pokemon_red_completion.red_routed_recovery import RecoveryRouteInterruptionHandler

@pytest.mark.parametrize("enabled",[False,True])
def test_native_resource_route_retains_field_faint_detector_without_controller_input(fixture,enabled):
 f=fixture
 f.router.runtime.resource_wild_faint_recovery=enabled
 captured=[]
 router=replace(f.router,routed_recovery=True,interruption_handler_wrapper=lambda handler,spec:captured.append(handler)or handler)
 before=f.actions.actions_executed
 bindings=router.enumerate(f.adapter.observe())
 assert bindings.bindings and len(captured)==1
 handler=captured[0]
 assert isinstance(handler,RecoveryRouteInterruptionHandler)
 assert f.actions.actions_executed==before
 if not enabled:
  assert handler._field_faint is None
  return
 assert handler._field_faint is not None,"Native resource route drops the existing strict field-faint recovery capability"
 raw=f.reader.read()
 assert raw.party_hp and any(raw.party_hp)
 slot=next(i for i,hp in enumerate(raw.party_hp)if hp>0)
 hp=list(raw.party_hp);hp[slot]=0
 assert handler._field_faint.has_new_field_faint(replace(raw,party_hp=tuple(hp)))
 assert f.actions.actions_executed==before
