# Claude Handoff: Strategic Model Pre-Test Audit

## Authority and stop line

Audit the completed non-test collection and the first frozen destination ranker. Do not open,
materialize, inspect or execute any of the 12 test scenarios. Do not refit merely to improve the
reported validation number. If you find a defect, preserve the current model and evidence as a
failed development candidate, repair under a new source identity, and explain whether recollection
is actually required.

## State on handoff

- Branch: `agent/balanced-team-curriculum`.
- Counted data: 24 train + 12 validation, all complete, one decision each.
- Test: 0/12 opened.
- Historical collection source: `ed4d6726c615a49235cd1262fb8964937555f54f`.
- Collection source bundle: `a49612b82ff114f8ad06407b99fdec3619b51f515079665050d5ef7e0051376d`.
- Scenario registry: `d06ecc9c1bc9d4103b966c83df0ee6e49c2329ed7785c63751ada1e74c11cd71`.
- Frozen model canonical digest: `fbfb9a1eb4fad6c5e20222215fd0f1c9fb736149d90811131e166e5261ecf444`.
- Frozen private model file digest: `b64329d0d692754728b492348cf029263e57f0168c8dd291e230a8ade0c32e10`.
- Selected model: eight hidden units, L2 0.1, seed 20260813.
- Validation: 7/12 model, 4/12 cheapest-route baseline, paired wins/losses 3/0,
  exact two-sided p = 0.25.

Private ROMs, checkpoints, episodes and the model remain outside the repository. Obtain their
locations from the owner/session environment; never put those paths in a tracked or untracked file.

## Read first

1. `MISSION.md`
2. `AGENTS.md`
3. `AGENT_COORDINATION.md`
4. `src/pokemon_red_completion/strategic_navigation_model.py`
5. `scripts/fit_strategic_navigation_model.py`
6. `tests/test_strategic_navigation_model.py`
7. `docs/evidence/strategic-counted-collection-audit-2026-08-13.json`
8. `docs/evidence/strategic-navigation-model-development-2026-08-13.json`
9. `docs/evidence/strategic-navigation-model-mutation-audit-2026-08-13.json`

## Reproduction path

Run the complete ROM-free gate first. Then use the fit script with the private artifact root,
checkpoint root and an output path outside the repository. The script reconstructs the historical
counted assignments from the path-free collection receipt rather than pretending the post-model
source produced the old episodes. It must reproduce both model digests and report test opened
false.

## Adversarial audit targets

1. Mutate each partition guard. A test row must not enter development validation, a validation row
   must not enter fitting, and duplicate/missing counted scenarios must fail closed.
2. Permute every candidate row and repair only its ephemeral binding index/label. Scores and
   probabilities must permute exactly; accuracy must not change.
3. Inject map names, coordinates, destination references, objective IDs and binding indices into
   policy input. The existing canonical dataset parser should reject them before featurization.
4. Change the historical source, capture digest, scenario digest, collection slot or assignment ID
   in one episode header. Exact assigned loading must reject it.
5. Corrupt a model weight, feature name, feature order, file digest or array shape. Loading must
   reject it.
6. Flip relative-route ranks, minimum gaps, route-cost baseline direction and paired win/loss
   accounting. The tests should distinguish every mutation.
7. Verify the selection rule against all seven recorded trials. The chosen model must be the exact
   deterministic maximum under the declared ordering, not a hand-picked result.
8. Check the evidence language. Validation is development-selected and p = 0.25; no document may
   call it significant, autonomous, cross-game transfer or live model authority.

## Decision after audit

If clean, recommend freezing a one-shot test protocol around the exact model digest. That protocol
must predeclare how unavailable candidates, ties, failed routes and incomplete episodes score; it
must publish every result and forbid reruns after an unfavorable outcome. Only then should anyone
open the 12 sealed test scenarios.
