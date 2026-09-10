# Search memory: foundation complete, learner update remains

## Verdict

Opportunity-specific effort can now be recorded, observed and persisted in a versioned terminal
checkpoint. The current **32-example model is unchanged** and is explicitly prevented from
silently ignoring history-bearing input. This is maintenance for the next memory-aware learning
lesson, not a new learned-gameplay result. [Qualification](../evidence/red-search-memory-qualification-2026-09-06.json).

## Implemented and tested

- Private lookup keys combine the adapter's source binding with the collection-objective digest.
  The chooser sees only attempt/exhaustion/action/frame counts, never these keys or raw identities.
- Memory records actually metered successful searches or verified exhaustion. Zero-input,
  unverified failure and interrupted outcomes are not fabricated settled searches.
- The player refreshes the observation after recording memory. It does not change availability,
  force a different action, globally blacklist acquisition, or remove the anti-loop guard.
- Goal-input v3 carries explicit history; v1/v2 remain unchanged. Checkpoint v3 carries memory;
  v1/v2 remain readable and do **not** claim that missing past history means no prior searches.
- Durable publication recovery and subsequent restoration preserve separate source histories.
  A child continuation may not drop or reduce authenticated history. Reordering, resource/party
  changes and a separately versioned collection objective are tested distinctly.
- The old goal scorer rejects v3 history input before selection. There is deliberately no CLI
  switch that presents the current scorer as history-trained. Existing history-free play remains
  available; the next learner version must explicitly consume the new observations.

20 memory tests passed, including actual bounded-executor metering, observer projection,
checkpoint publication recovery and a child losing history. The broader player-contract run
passed 162 checks before the final added memory test; 145 focus/registry checks also passed.
These overlap and are not additive. Full configured type checking passed for 399 source files;
lint and source-registry checks passed. No external auditor or subagent was invoked.

## Real saved-state inspection

The previous terminal was reopened read-only: exact saved bytes and fresh ledger matched, with
zero input/frames. It still contains 14 living species, 19 registered species, 17 specimens and
106 requirements remaining. Evolution/storage are unavailable; local development is offered but
not demonstrated useful for the current 63/55-level party. No new rollout, fitting or catch occurred.

Do not backfill prior searches from coarse terminal summaries: they lack a fully authenticated
source-specific history contract. The new history's scope is explicitly since tracking began.
The whole collection-objective digest scopes records conservatively; a changed digest gives a
different context, not proof that an encounter source itself has become more fruitful.

## GitHub regression correction

The actual prior gameplay source passed CI 34059268008. The subsequent documentation publication
failed CI 34060207406 because a dashboard test asserted the older 29-to-31 fixture against the
new live 31-to-32 reference. It did not lose or invalidate the model/save. That test now explicitly
uses its historical fixture; a separate test checks the 31-to-32 negative-search evidence.
The focus suite passes locally. New-head hosted CI is not claimed green before it finishes.

## Next meaningful milestone: 40% of a declared checklist

The stage is **a memory-aware learner choosing a useful alternative after unsuccessful search,
then learning from the result in continued play**. It is not "Red 40% complete" or a time estimate.

1. Saved-state collect/fit/continue loop: complete.
2. Tested persisted search-history contract: complete.
3. Versioned model consumes history and retains old data honestly: unfinished.
4. Two useful collection alternatives actually executable: unfinished.
5. Sampled lesson plus productive post-fit behavior: unfinished.

Two of five equally weighted acceptance items = **40%**, up from 20% at session start. The last
three may cost more time than the first two; this percentage must not imply otherwise.

## Next session

Implement the history-aware successor representation and fit path. Old examples have **unknown
history**, not invented zero-effort histories; retain their outcomes with an explicit missingness
representation or a separately retained legacy head. Do not overwrite the existing 32-row corpus.
Use the new counts as observed context, not a manually imposed penalty called learned judgment.

Then qualify a genuinely useful second collection action: another eligible encounter source or
required-precursor storage/evolution. Existing local development availability alone is not enough.
Only then declare a short sampled lesson and bounded follow-up. No full replay, sealed Red,
ROM-modification or Crystal execution. Reorient if this becomes another acquisition-only loop.
