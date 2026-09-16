# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Six real learned attacks, one inefficient victory

The new bounded battle adapter gave the frozen expected-utility-v2 move ranker
actual control in one natural Route 11 encounter from the earned post-Marowak
save. Teacher setup moved the predeclared party slot 6, Kingler level28, into
the lead. Against level15 Spearow, the model selected Guillotine five times
(zero damage), exhausted its5 PP, then selected Vicegrip and knocked out the
38-HP opponent. Kingler finished at59/76 HP in an input-ready field state.

All6 choices were saved before execution, had distinct observed-state hashes,
and matched exact physical-slot PP spends. No teacher attack fallback, hidden
switch, state edit, reset or model fit occurred. Total:149 actions/13,177
frames, including80 actions/6,840 frames of teacher encounter setup. The
original authenticated save remained unchanged; the actual terminal is retained.
[Evidence](docs/evidence/red-earned-learned-battle-2026-09-16.json).

This is a live authority integration result, not a good-policy or independence
claim. The existing battle model was not newly trained. Model137 remains at
137 examples/92 successes/58 economy-qualified; Red remains96/124,74 specimens
and198 cash. Fresh acceptance remains0/5. Ordinary collection battle control
is still fixed. Gameplay is stopped and nothing was pushed to GitHub.

## Next bounded work

Improve attack reliability/value through an actual training-and-test lesson.
The saved first observation already represents Guillotine accuracy0.30 and
its OHKO flag, yet the frozen ranker scored it above Vicegrip. Speed is absent
from current features, but this encounter alone does not prove that is the
cause. Audit supported-mechanics and training coverage before changing either.
Use separate permitted training scenarios and an untouched comparison set;
do not fit or replay this consumed development encounter or ban one move by name.
Retain old/new outcomes, HP and PP costs. No full run or broad promotion.

Target the next60–90-minute session at one reliability-focused learning cycle.
Sol High, Fast off suits the now-bounded implementation and comparison. Use
Astra again only if evidence calls for a broader battle representation redesign.

Flash3.8 High completed a read-only architecture review through Antigravity.
Its mapping, settling and faint/no-alternative guards were accepted; an
unnecessary counterfactual timing delay was not used. Quota refresh unavailable.
A second Flash review favored outcome training; its development-fit suggestion
and unverified corpus/linear-weight claims were rejected.
301 targeted ROM-free tests, changed-source type checks and local checks passed;
the full suite was not run. Private plans and terminals remain outside Git.
