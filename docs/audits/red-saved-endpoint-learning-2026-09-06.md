# Saved-endpoint learning: working fit, unchanged gameplay choice

## Verdict

The goal-value learner was genuinely updated **31 to 32 examples**, retaining every prior row.
One newly sampled unsuccessful search supplies a verified negative target and actual costs.
The next greedy continuation still searched unsuccessfully: this session does **not** establish
better sustained play, a new collection gain, independent evaluation, or full-game competence.
See the [machine-readable result](../evidence/red-saved-endpoint-learning-result-2026-09-06.json).

## Actual execution

| Attempt | Actions | Frames | Outcome | New fitting rows |
| --- | ---: | ---: | --- | ---: |
| Initial learning launch | 0 | 0 | Development could not see its hard limiter through the observation wrapper | 0 |
| Corrected sampled learning | 330 | 21,804 | Acquisition search exhausted; repeated recovery stopped safely | 1 |
| Post-fit greedy continuation | 198 | 8,700 | Acquisition search exhausted; unchanged context stopped safely | 0 |

The first launch remains in the fit inventory as a zero-input exclusion. The correction retained
the same seed, parent, profile and dose; no controller-started attempt was retried. Negative
evidence was not relabeled as a success. The diagnostic's greedy choices were not fitted.

Both old and new models rank acquisition first on the new row's recorded menu. This is an
in-sample score replay, not a controlled gameplay comparison. The actual follow-up started from
changed state and is not an independent root. Its shorter duration is not an efficiency claim.

The final endpoint was independently reopened through an action-disabled controller. Fresh
semantics and collection ledger matched; save bytes were unchanged, with zero actions/frames
and no held buttons. It retains **14 living species, 19 registered species, 17 specimens and
106 required specimens remaining**, with zero undeclared losses. Money is 649; party levels
remain 63/55/55/55/55/55. No arbitrary grinding occurred.

## Engineering audit

- The original checkpoint/profile is verified before the explicitly declared expanded skill
  profile is used. A subsequent checkpoint binds that expanded profile explicitly.
- Continuation training preserves the original train root. Its versioned plan binds the actual
  saved bytes, origin bytes, parent archive/checkpoint and restore/execution profiles.
- Admission replays the declared sampling probabilities and joins actual controller traces to
  the settled outcome. Failed sampled searches can teach costs; zero-input failures cannot.
- The wrapper repair restores a concrete per-offer limiter without removing the original total
  episode limiter or the action-free observation gate. Tests exercise all three together.
- The fitter retains all previous row fingerprints and inventories older native episodes using
  their own behavior models. Historical v2 plans remain supported. No old diagnostic is fitted.
- The newly available local-development option was **not successfully exercised**. Its wrapper
  qualification is not gameplay proof of that mechanic or a captured capture/development contrast.

Qualification: 79 focused checks and 186 player/registry/focus checks passed before the wrapper
repair; another 51 wrapper/continuation/training checks passed after it. The 399-file type check
passed before that script-only repair, followed by its script type check. These overlapping
counts must not be summed into a unique-test count. Prior source CI 34057347920 passed; execution
source bdc9a4cd has CI 34059268008 pending at audit drafting. No external auditor was invoked.

## Reorientation and next session

The useful result is a working **continue, collect, fit, continue** path. The disappointing result
is that another negative row did not change the next choice. Do not spend the next session
repeating this exhausted local search or merely adding receipts.

1. Add bounded, title-neutral search-history state that survives saved continuations. Distinguish
   no target found from unsafe control. Expose recent effort/no-progress to the goal chooser,
   without raw map/species IDs in learned features or a route-specific forced next action.
2. Falsify it first with a ROM-free interrupted/resumed example: the same exhausted opportunity
   must not appear fresh, and a genuinely changed opportunity must not be globally blacklisted.
   Preserve the anti-loop guard. Version any feature schema; never rewrite old training rows.
3. Expose one genuinely useful collection alternative using existing prerequisite information:
   another eligible encounter source, or storage/required-precursor evolution where executable.
   Do not substitute arbitrary leveling of the already established party.
4. Declare a short changed-state sampled lesson with both alternatives actually executable;
   collect outcomes and refit only if it adds distinct evidence. Stop if the alternative is still
   unavailable rather than running another acquisition-only loop.

Time box: one session, at most four hours, with a reorientation after 90 minutes if no useful
alternative can be shown. No full replay, sealed Red, ROM-modification or Crystal execution.
The product remains learned Red story/collection competence, then measured adaptation to a
compatible unfamiliar Red modification, followed by Crystal and cross-title living collections.
