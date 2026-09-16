# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Model136 fishing choice stopped safely; failure trained Model137

From the exact post-Marowak **96/124** save, read-only qualification found
**five distinct choices** (four fishing, one evolution), with no actions,
frames or model queries. Model136 chose fishing acquisition, index 4, without
a teacher label. Traversal stopped at the Safari Zone gate: an `up` step
expected map 156 at (2,3) but observed (3,4). The runner failed closed after
**735 actions / 22,944 frames**, before fishing or capture. Its safe terminal
preserves **96/124**, all 74 specimens and 198 cash; save SHA
`27694933e9f647140608807803e1c750d750507ff9e325ed1884beee2bb93054`.

That *one new* measured failure was admitted and fitted once. **Model137 has
137 examples / 92 successes / 58 economy-qualified**, model SHA
`810ca703200831154804e89dcb5f5de4045a658ef2cb12223f8bbd7106a3e76e`.
No replay, teacher target, independent evaluation or authority promotion.
Fresh Red acceptance remains **0/5**; no GitHub push.
[Evidence](docs/evidence/red-model137-fishing-route-drift-2026-09-16.json).

Read-only route reconstruction identified **four Safari fishing offers, all
for #147**, each crossing the scripted admission gate. Cash was **198** versus
the **500** admission cost. Both northbound admission lanes were unguarded
in the static walking graph; the general story-routing adapter now requires
an explicit paid-admission capability on both. It does not grant that
capability to ordinary walking. The same read-only inventory now finds **zero
Safari fishing offers** from the pre-attempt save. From the exact failed
terminal, the mixed menu fails closed because fewer than two executable
options remain; **no new model choice or game action** was made. The precise
receptionist script response was not replayed. Targeted ROM-free checks:
**161 passed**, including autonomous collection, Safari, documentation and
roadmap tests.

The dashboard's audited `registered_train_examples` projection still reads
135 from its prior receipt. The new Model137 count above is verified in the
private fit artifact and linked evidence; the dashboard projection has not
yet been advanced, and its older number is not a second model state.

## Next bounded work

The immediate barrier is no longer a route-step retry: fund the missing
**302 cash** legitimately and make the already-present, metered Safari
admission/acquisition skill model-selectable, or qualify another genuinely
distinct non-Safari acquisition. Confirm at least two executable options
from the exact safe **96/124** terminal before asking Model137 to choose.
Do not replay this consumed fishing choice, hand-pick a species, pretend an
unpaid gate is ordinary walking, or relax route verification. The existing
Safari skill is not yet integrated into this autonomous menu. Keep fresh-start
Red acceptance separate.

Recommended next setting: **Sol High, Fast off**, about **45–60 minutes**.
Fresh Red acceptance remains **0/5**; ROM hack and Crystal remain closed.
