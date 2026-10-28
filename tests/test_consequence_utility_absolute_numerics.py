"""Synthetic numerical fixtures only; no native data, models or runtime imports."""
import numpy as np
import pytest
import scipy.optimize
import pokemon_red_completion.player_challenge_consequence as h
U=np.asarray((0.,1.,-.1,-.1,-.25,0.,-.05,-.5,.25))

def data():
 z=np.asarray([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]])
 y=np.asarray([[1.,0.,.2,.2,1.,0.,.25,0.,.2],
               [1.,1.,.1,.1,0.,.3,0.,0.,1.],
               [1.,0.,.3,.3,1.,0.,.5,0.,.1],
               [1.,1.,.2,.2,0.,.5,.25,0.,.9]])
 return z,y,((1,0),(3,2))

def public(v):
 v=np.maximum(v,0.);v[:,:2]=np.clip(v[:,:2],0.,1.)
 v[:,1]=np.minimum(v[:,0],v[:,1]);v[:,7:]=np.clip(v[:,7:],0.,1.);return v


def test_true_reduces_absolute_utility_error_with_same_means_margins_and_bounds():
 z,y,pairs=data();before,bm=h._fit_order_retained(z,y,pairs,U)
 after,am=h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)
 bp=z@before+bm;ap=z@after+am
 assert np.array_equal(bm.view(np.uint64),am.view(np.uint64))
 assert np.mean(np.abs((ap-y)@U))<np.mean(np.abs((bp-y)@U))-1e-6
 assert np.max(np.abs(ap-public(ap.copy())))<=1e-8
 for winner,loser in pairs:
  observed=float((y[winner]-y[loser])@U)
  assert (public(ap.copy())[winner]-public(ap.copy())[loser])@U>=min(.01,.1*observed)-1e-8
 def combined(c,p):return float(np.sum((p-y)**2)+np.sum(c*c)+np.sum(np.abs((p-y)@U)))
 assert combined(after,ap)<=combined(before,bp)+1e-6

def test_epigraph_gradient_is_unit_linear_and_ridge_excludes_slacks(monkeypatch):
 z,y,pairs=data();real=scipy.optimize.minimize;calls=[]
 def checked(fun,x0,**kwargs):
  n=len(z);base=np.asarray(x0);gradient=kwargs['jac'](base)
  assert np.array_equal(gradient[-n:],np.ones(n))
  for i in range(n):
   one=base.copy();one[-n+i]+=1.;two=base.copy();two[-n+i]+=2.
   assert abs(fun(one)-fun(base)-1.)<1e-10
   assert abs(fun(two)-2.*fun(one)+fun(base))<1e-10
  calls.append(1);return real(fun,x0,**kwargs)
 monkeypatch.setattr(scipy.optimize,'minimize',checked)
 h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)
 assert calls==[1]

def test_loose_epigraph_false_success_is_rejected(monkeypatch):
 z,y,pairs=data();real=scipy.optimize.minimize
 def dishonest(fun,x0,**kwargs):
  result=real(fun,x0,**kwargs);assert result.success
  result.x[-len(z):]+=.5;result.fun=fun(result.x);return result
 monkeypatch.setattr(scipy.optimize,'minimize',dishonest)
 with pytest.raises(ValueError,match='not tight'):
  h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)

def test_epigraph_infeasible_false_success_is_rejected(monkeypatch):
 z,y,pairs=data();real=scipy.optimize.minimize
 def dishonest(fun,x0,**kwargs):
  result=real(fun,x0,**kwargs);assert result.success
  result.x[-len(z):]=-1.;result.fun=fun(result.x);return result
 monkeypatch.setattr(scipy.optimize,'minimize',dishonest)
 with pytest.raises(ValueError,match='violates|infeasible'):
  h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)

def test_true_missing_nonpair_label_rejected_before_optimizer(monkeypatch):
 z,y,_=data();y[0,5]=np.nan
 monkeypatch.setattr(scipy.optimize,'minimize',lambda *a,**kw:pytest.fail('no optimizer'))
 with pytest.raises(ValueError,match='complete nine-channel'):
  h._fit_order_retained(z,y,((3,2),),U,utility_absolute_loss=True)

@pytest.mark.parametrize('flag',[None,0,1,'true',np.bool_(True)])
def test_nonboolean_loss_scope_rejected_before_optimizer(monkeypatch,flag):
 z,y,pairs=data()
 monkeypatch.setattr(scipy.optimize,'minimize',lambda *a,**kw:pytest.fail('no optimizer'))
 with pytest.raises(ValueError,match='explicit boolean'):
  h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=flag)


def test_true_solver_failure_and_time_limit_still_fail_closed(monkeypatch):
 from types import SimpleNamespace
 z,y,pairs=data()
 monkeypatch.setattr(scipy.optimize,'minimize',lambda fun,x0,**kw:
                     SimpleNamespace(success=False,x=x0,fun=fun(x0)))
 with pytest.raises(ValueError,match='did not converge'):
  h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)
 times=iter((0.,61.));monkeypatch.setattr(h.time,'monotonic',lambda:next(times))
 with pytest.raises(TimeoutError,match='60 numerical seconds'):
  h._fit_order_retained(z,y,pairs,U,utility_absolute_loss=True)
