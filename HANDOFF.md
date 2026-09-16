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

The dashboard's audited `registered_train_examples` projection still reads
135 from its prior receipt. The new Model137 count above is verified in the
private fit artifact and linked evidence; the dashboard projection has not
yet been advanced, and its older number is not a second model state.

## Next bounded work

Isolate whether the Safari-gate route diverged because the planner assumed a
wrong indoor step, the gate script changed position, or movement acknowledgment
was premature. The result only proves the observed mismatch, not its cause.
Use a minimal ROM-free route/observation test and an authenticated read-only
gate inspection if needed; fix a general cause or exclude that path if it is
not executable. Then inspect a fresh menu from the exact **96/124** safe
terminal for Model137. Never replay this consumed choice, hand-pick another
species, or relax the safe route check. Keep fresh-start Red separate.

Recommended next setting: **Sol High, Fast off**, about **45–60 minutes**.
Fresh Red acceptance remains **0/5**; ROM hack and Crystal remain closed.
