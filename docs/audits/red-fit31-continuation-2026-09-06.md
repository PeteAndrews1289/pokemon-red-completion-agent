# Saved-state continuation audit and reorientation

## Verdict

The thin continuation consumer works: it authenticated the completed parent, preserved its train
lineage, restored the actual game and verified fresh semantics before input. The one declared
episode then **failed** after 215 actions / 8,244 frames. No fit, new learning example, learned
choice, collection gain or independent evaluation was demonstrated. The model remains at 31 rows.
See the [path-free result](../evidence/red-fit31-continuation-result-2026-09-06.json) and
[prospective plan](../work-sessions/2026-09-06-fit31-continuation.md).

## What actually happened

The player travelled from the shop to the declared Mansion capture source. Its only learned-menu
option was acquisition; healing was also executable but is deterministic safety, not a model-ranked
competitor. Read-only replay of the recorded input with the exact model reproduces the selected
index and `deterministic_unsupported` mode. This is not a newly earned model decision.

It entered three wild battles but captured nothing before the 64-leg search bound expired. Of 105
move actions, 97 changed the observed position/map and eight did not. The latter include possible
battle/transition effects and are not automatically wall collisions. The trace does not support
describing this failure as a stuck-at-a-wall navigation bug. A one-direction corridor leg is one
tile here; 64 legs is not a guarantee of seeing the desired species.

The capture exception became a durable failed goal outcome. The fresh recovery question differed
after travel, so the unchanged-context stop did not apply. The authority chose acquisition again;
the different-goal guard correctly prevented that input, but raised a fatal exception. Consequently
the run did not produce a structured bounded-player terminal result or a new terminal save.
The failed manifest, 51 snapshots and all 215 actions authenticate. The final observed party and
resources equal the initial values: money 649, capture items 19. The original parent save remains
intact. A complete fresh terminal collection ledger was not retained; do not invent that evidence.

## Engineering qualification

- 87 focused tests passed, including actual private-store checkpoint chains, wrong partition/hash/
  parent rejection, read-only semantic/effect checks, and refusal before controller access.
- Lint, 398-source type checking, documentation/focus and public-artifact checks passed.
- The inherited strategic registry source digest was stale and was regenerated; no assignments
  were run, reauthorized or counted. The core source bundle and unused collection roster are unchanged.
- The broad local suite was still running at launch, not represented as green. Current source was
  clean, locally qualified and published; no duplicate hosted-CI wait preceded this short run.
- No external reviewer or subagent was invoked. The exact failed identity is closed; no replay.

The broad suite finished: **7,102 passed, one failed, one skipped, three integration cases
deselected, one expected failure**, in 1,947 seconds. The failure was the strategic registry's
old hard-coded fingerprint after its source binding was regenerated. A structural comparison
confirmed that only source-bundle and derived execution hashes changed; assignment roster and
decision contract did not. The three fixed golden expectations were updated, retaining the exact
identity assertions rather than replacing them with self-comparisons. This is test/source-binding
bookkeeping, not another gameplay repair or a claimed second full-suite pass.
After that expectation-only correction, **161 registry, continuation and product-focus tests
passed**, with clean lint/docs checks. No emulator was restarted and no functional player code
changed after the failed attempt.

## Next session: ordinary unsuccessful searches must not break continued play

1. Treat bounded search exhaustion as an explicit no-acquisition outcome, distinct from a broken
   controller or unsafe state. Preserve its costs and negative outcome; never relabel it as a catch.
2. When recovery has no acceptable alternative, return a typed stop rather than losing the settled
   result through an exception. Retain a fresh ledger and safe checkpoint when input readiness and
   outcome agreement permit. Do not remove the anti-loop guard or silently retry the failed choice.
3. Give the actor a useful alternative through an existing development/evolution/storage mechanic
   where fresh state supports it. Inspect the current menu first; do not create another teacher
   factory or count forced acquisition as learning.
4. Qualify a new short continuation prospectively, preserving this failed attempt and the original
   lineage. Separate normal continued search from replay of a consumed diagnostic. Include no-find
   outcomes in a future declared learning curriculum, not retroactively in this greedy diagnostic.

Do not simply enlarge the search limit until a favorable catch appears. The reusable ability is
deciding whether to keep searching, switch tasks or stop safely with progress retained. That matters
for rare encounters in Red, modifications and later titles alike. ROM modification and Crystal
support remain deferred; the long-term living-collection goal is unchanged.
