# Teaching a local model to play Pokémon

Editorial treatment updated October30,2026. Show successful local actions beside their failed overall payoff. All runs are closed; autonomous acceptance remains unproved.
[Current status](../ACTIVE_PRODUCT_STATE.md) · [Handoff](../HANDOFF.md).

## October30: a wrong observation, then a costly training venue

The exact Forest comparison changed the local model's choice without new weights.
It chose and beat the trainer. From the same origin Brock took18choices instead
of89and6heals instead of43; collection side benefits differed, so this is a local
story improvement, not a fivefold whole-game speedup.

The next original midgame copy gained six registrations but stopped after26native
minutes. Ponyta had made real XP progress; a productive venue stop was incorrectly
classified as fatal. We retained that failure, repaired the narrow consumer and
qualified a short continuation from its exact terminal. The copied continuation
ends77/124. It does not erase the failure or qualify endurance.

The logs expose why training dragged: frequent recovery made the Mansion much
less productive than the earlier Cave dose. Recorded costs do not feed the current
menu priors, and the venue model has zero weights on those11cost/prior inputs;
wiring alone cannot fix the preference. Why those weights are zero remains open. Late play has a separate missing
partial-interaction learning signal. Repeated cash-only fitting would not fix it.
All current gates and fresh autonomous completion remain unproved. No new weights
or actual-save registrations were added this block; all runs are closed.
[Evidence and limits](work-sessions/2026-10-30-forest-decision.md).

## The opening

“We got software to finish Pokémon Red. Then we had to ask a harder question:
could a model decide what to do, recover when it went wrong, and finish without
us repairing the run along the way?”

Open on a victory screen, then show a later faint or failed run with its retained
record. Put the assistance class and run identity on screen. Never combine
different saves into a single apparently uninterrupted success.
[Supported completion](evidence/red-assisted-development-124-2026-10-22.json).

This document is an editing plan. A proposed scene is not a claim that a usable
video recording exists. Use retained recordings when available; otherwise show
clearly labelled screenshots, receipt excerpts or newly drawn explanatory cards.
Do not present a reconstruction or diagnostic replay as original live footage.

## The story arc

### 1. Decide what “playing Pokémon” means

Explain the target before showing the engineering: a fresh model-directed Red
run, Champion and Hall of Fame verified, and all 124 registrations on the declared
legitimate route earned in that same save. Later reliability needs at least eight
successes in ten preregistered held-out clean starts. Neither has been proved.
[Mission](../MISSION.md) · [Completion contract](completion-contract.md).

Show the decision pipeline: semantic observations → local goal and battle models
→ declared execution skills → native outcomes. This is not pixel-only play.
Coding assistants help develop the system; the intended player makes no runtime
LLM calls. Movement, menus and other supplied mechanics need explicit credit.
[Architecture](architecture.md) · [Assistance policy](assistance-policy.md).

### 2. Build a teacher, then separate the student's credit

Show why a reliable teacher was useful: it supplied controls, game knowledge and
reproducible situations in which a student could learn. Then label the boundaries.
Teachers may manipulate isolated TRAIN fixtures; the final actor has no cheat
action. Diagnostic XP, money or Pokémon never enter the actual campaign.
[Development contract](../NORTH_STAR.md).

Earlier supported development saves reach Champion/Hall of Fame and 124/124.
Show their real achievements alongside their repairs, restoration and assistance.
Keep each ancestry separate. In-game levels are gameplay; a fitted parameter
change is model learning. A successful supported save does not establish an
unchanged fresh autonomous completion.
[October 14 record](work-sessions/2026-10-14-league-and-collection-continuation.md) ·
[October 22 assessment](evidence/red-assisted-development-124-2026-10-22.json).

### 3. Let the failed runs explain the difficult part

Use a short sequence of representative stops, rather than a montage of every
patch. Separate an execution boundary failure, an ordinary in-game loss, and a
legal but wasteful model choice. Keeping these distinct explains why “the emulator
can finish the route” and “the learner can play reliably” are different milestones.
[Research retrospective](research-retrospective.md) ·
[Chronicle and source index](chronicle/SOURCE_INDEX.md).

Show the Windows qualification as infrastructure: at most two bounded development
workers qualify for the tested configuration. That creates diagnostic capacity;
it does not prove twice the useful output or teach the model anything by itself.
Do not imply that a diagnostic copy resumes an actual campaign.
[Capacity evidence](evidence/red-audit-readiness-2026-10-25.json).


### 4. Show the current experiment and its limits

Use the October 30 Forest comparison above to show how an observation correction
changes a local choice without fitting new weights. Then show the midgame stop
and the measured training costs. Preserve the failed run beside its short repaired
tail; neither establishes an unchanged autonomous completion.

The [historical edit](history/2026-11-02-before-ci-cleanup-youtube-video-narrative.md)
retains the detailed October 26–29 preparation, switching and stopping scenes,
with their distinct candidates, evidence and editing limits.

## Footage and evidence checklist

| Proposed scene or card | What it establishes | Evidence and editing limit |
| --- | --- | --- |
| Supported victory screen with its run label | Broad execution coverage and a real completed save | [Assisted completion](evidence/red-assisted-development-124-2026-10-22.json); retain restoration/support disclosure. |
| Before/after preparation timeline | Useful completed preparation with much less local work | [Current evidence](evidence/red-masked-native-validation-2026-10-26.json); include travel/healing/losses and the one-source scope. |
| Learner parameter and constraint cards | Actual offline fitting, separate from in-game levelling | [Session](work-sessions/2026-10-26-masked-native-validation.md); counts have different parents and are not additive. |
| Side-by-side native switch decisions | Better local survival and fewer frames | [Current evidence](evidence/red-masked-native-validation-2026-10-26.json); label related TRAIN/exposed DEV copies and zero independent-origin credit. |
| Psyduck before and after the current lesson | Useful training can take longer while preserving the trainee | [Current lesson](evidence/red-current-control-lesson-2026-10-26.json); show 0 → 149 trainee XP, 1 → 0 faints, and 3,348 → 5,592 frames. TRAIN-related copy, not campaign footage. |
| Evolution/Misty retention card | Earlier complete-sequence payoff survives the new switch head | [Current evidence](evidence/red-masked-native-validation-2026-10-26.json); both use 1,282 actions/94,428 frames/3 restores/2 faints and earn 1,993 full-sequence trainee XP. No new speed gain. |
| Six-trainer result and causal follow-up | Numerical retention does not establish whole-trajectory safety | [Current lesson](evidence/red-current-control-lesson-2026-10-26.json); five wins/one loss each, two lower candidate returns, four higher frame counts; four fixed-continuation arms separate a worse opening from worse later play. |
| Paused campaign dashboard | The actual campaign remains separate from copied diagnostics | [Handoff](../HANDOFF.md); a stale dashboard party is not evidence of current live progress. |

## Wording for narration and titles

Working title: **Teaching an AI to Play Pokémon—and Checking What It Learned**.
Describe the latest result as a local learned improvement in a hybrid player.
Do not claim pixel-only play, zero assistance, a fresh autonomous 124/124 finish,
general battle mastery, demonstrated Crystal transfer, or a new whole-game speedup.
Give Pete credit for directing the project and coding assistants credit for
engineering/review; neither should be confused with the runtime student.
[Mission and ownership](../MISSION.md) · [Assistance policy](assistance-policy.md).

## Preserved earlier edit and sources

The [October 14 editorial plan](history/2026-10-26-video-narrative-before-windows-learning-refresh.md)
retains its League, collection, Victory Road, gym, Safari and recovery footage
instructions and source references. Use it for those earlier chapters, with the
original lineage and assistance labels intact. The [chronicle](chronicle/README.md),
[source index](chronicle/SOURCE_INDEX.md) and dated work-session reports preserve
the longer history. Research claims require their own evidence and evaluation;
this video treatment is not a replication result or publication claim.


For the earlier long-form record, retain the [September 22 video script](chronicle/video-script-through-2026-09-22.md)
and [pre-chronicle editorial narrative](history/video-narrative-before-chronicle-2026-09-22.md).
