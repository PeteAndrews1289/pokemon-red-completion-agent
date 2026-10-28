# Frozen battler: Dig/Fly compatibility

## Prospective mission check

- Capability: correct learned battle choices around committed two-turn actions.
- Authority: baseline and candidate own complete battles; forced one-choice probes
  test execution only and never count as learner wins.
- Transfer: fresh species pairs excluded from prior damage and composition banks;
  reused authenticated TRAIN origins, not independent roots.
- Falsifier: selected charge/release with exact PP and no intervening policy call;
  compare complete frozen actors without fitting.
- Time box: one packet,64episodes maximum,20minutes native;45seconds/arm,
  5000controller actions/120000frames/80decisions per arm.
- Stop: unexpected execution failure stops dispatch and retains costs. Failed or
  unassessed coverage/behavior gates reject story admission, without refit/replay.

## Scope and frozen design

Twelve fresh matchups: four player-Dig, four player-Fly, two opponent-Dig and
two opponent-Fly. Player cases have one-member parties and neutral, low-accuracy,
low-HP and paralysis contexts. Enemy cases use neutral two-member parties so
replacement remains possible. Every move is teachable at its member's level.
Offsets0/12. Each player case gets one prescribed first-choice probe per offset,
then matched full admitted/candidate battles; enemy cases get only matched full
battles. All recipes and arm order freeze before native execution.

No scorer, weights, action mask or battle executor changes are planned. Add only
read-only adapter telemetry, absent from model observations, to expose native
charging/invulnerability at metered action boundaries. Controller sampling can
miss short transitions; do not claim unsampled phases. Check observations at
policy boundaries, choices, charged phases, release/interruption, PP and outcomes.
The existing damage scorer has no charge-duration feature; compatibility is not
optimal two-turn valuation. Report player decision counts, not fictional native
turn counts; frames measure the extra time directly.

Gates: zero illegal/uncounted actions; no model call during an observed active
player commitment; complete authentic traces and exact selected PP proof; both
Dig/Fly observed charging on player and enemy sides; candidate freely selects
both moves at least once. No candidate win decrease, loss/censor increase, and
at least one common win. On common wins, mean PP increase <=10% and mean frames
increase <=25%. Strict improvement is not required for this compatibility check.
Full-battle composition already supplies the distinct improvement evidence.
No perfect win rate, automatic new fit, story action or deployment is authorized.

The existing runtime waits for PP proof rather than inventing a second choice.
The disassembly confirms that charging bypasses the player menu and that PP is
decremented at release; interruption can cancel a charge.
[Battle core](https://github.com/pret/pokered/blob/master/engine/battle/core.asm) ·
[Flag definitions](https://github.com/pret/pokered/blob/master/constants/battle_constants.asm).

## Closed result

All64episodes completed:16prescribed execution probes and48complete learned
battles (24matched comparisons). Both actors won6/24 and lost18/24; zero censored
or illegal outcomes. All frozen behavior and coverage gates passed.

The candidate freely selected Dig11times and Fly40times. Telemetry observed
31candidate charge releases and3interruptions, both player and enemy Dig/Fly,
zero choices during player charging and zero decisions completed while charging.
The audit reconstructed264learned choices and16prescribed choices,5285events,
3937controller actions and339598frames. Native runtime was26.0seconds.
These are action-boundary observations, not a count of every native charge cycle.

On the6common wins, actual selected-move PP spending averaged3.333→2.667
(20%lower), and frames6662.3→5560 (16.5%lower). Overall candidate frames were
160130versus155960: not an across-the-board speed improvement. Both actors
incurred25party faints in the full battles. The low stress-bank win rate is
retained; this packet tests compatibility, not guaranteed story success.

## Accounting correction, without replay

Some reused TRAIN roots heal the party immediately after victory. That can clear
the active index and restore PP before the final decision endpoint is recorded.
The first audit exposed this; the corrected read-only auditor proves charge PP
from live in-battle telemetry rather than the healed endpoint. PLAN, native
source, models, actions and RESULT remain immutable; no arm was rerun.

The old metric named party_pp_spent measures positive endpoint depletion.
It remains in historical records. Future episode reports separately expose
selected_move_pp_spends, counting executor-proven attack expenditures. In these
supported domains each executed selection proves exactly one selected-slot PP.
Full-battle totals are87versus77actual spends, not81versus71endpoint depletion.
Both the original frozen gates and the supplementary actual-spend gates pass.

The same read-only recount authenticated all144previous composition episodes.
Its actual totals are730versus681; on17common wins the means are12.000→9.765,
an18.6%reduction. The previously reported20.3%describes endpoint depletion,
not actual PP spent. Wins38versus18 and19.4%fewer common-win turns are unchanged;
the conclusion still passes. The old artifacts are preserved, with this explicit
correction. Terminal HP likewise can include native healing and must not be
presented as pre-heal efficiency.

## Disposition and next work

Accept bounded Dig/Fly compatibility. The three planned checks—damage ranking,
complete-battle composition and two-turn execution—now pass for candidate4ea4cfde.
Do not add another broad battler refit. Next is narrow prospective story-trial
binding: authenticate the retained healed stage328, exact candidate and audit
receipts; preserve legal masks, recovery, action/frame/time caps and all costs.
Record that admission separately before any input. Allow45–90minutes for binding,
tests and one bounded attempt, reassessing at the first safe checkpoint or failure.

No story input, new fit, registration, production promotion or publication occurred.
Story stage328/a8a6ecbf, absentstage329, collectionbf603930, K/Model141 and canonical
remain unchanged. Gameplay is stopped. New-root transfer, optimal charge valuation,
profitable League income and final fresh-Red acceptance remain unproven.

Verification:571targeted ROM-free tests passed, including adapter, executor,
composition, episode reporting and documentation surfaces; not the full suite.
The audit source is separate from the pinned native source; hashes and measurements
are retained in the [path-free evidence](../evidence/red-two-turn-compatibility-2026-09-23.json).
No Flash/Claude worker was used and their quotas were not queried.
