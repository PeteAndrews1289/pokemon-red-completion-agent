# Native sleep-prompt check: one verified cell, checker corrected

September24,2026. [Evidence](../evidence/red-sleep-prompt-native-check-2026-09-24.json).
Maintenance unblocking the [later-state lesson](2026-09-24-later-attrition-prompt-boundary.md).

## Result

The repair worked in one actual emulator scenario: a sleeping actor attempted
its prescribed opening move, the poisoned opponent fainted, and the executor
yielded the send-out prompt without spending move PP or answering for the model.
The frozen experimental actor declined, then continued the battle and won.
Twenty model choices followed the one prescribed opening;21total decisions,
two prompt declines,five voluntary switches,two forced replacements,two party faints.
No uncommanded in-battle switch or logged illegal choice was found.
This is one observed repaired boundary, not a general battle-quality result.

The four-cell qualification stopped after that first complete battle because
Codex's private checker incorrectly demanded decision index1 for the second
decision. Native logs are one-based:1attack,2prompt. This was a checker error,
not another native executor failure. The original failed result is retained.
No battle was replayed, no original result overwritten and no remaining cell played.

## Independent correction

A new ROM-free auditor checks contiguous one-based decision IDs, adjacent attack
and prompt, unchanged PP, same active member, opponent replacement, a still-asleep
semantic guard, model-owned legal selection and resource-preserving resolution.
Twenty regression tests cover valid accept/decline and reject malformed IDs,
spent moves,changed PP,awake actors,guard input,wrong targets and state gaps.

The stored event chain and all20model choices were independently reconstructed.
The first semantic guard occurred inside sleep recovery, at sleep count1.
The observer consumed zero inputs/frames and changed no state. The retained final
state was reobserved without advancement and matched the completed decision.
The read-only correction verifies the already-played cell only; it does not
retroactively pass the original four-cell packet.541focused tests pass,not fullsuite.

## Scope and costs

Two authenticated TRAIN teams were newly conditioned without controller inputs:
player sleep2,first opponent poison/HP1,otherwise existing team definitions.
Two timings per team were declared;shared roots/timing siblings are not independent
natural-game evidence. The teacher prescribed only the opening attack. No actor
memory writes or teacher fallback. The logs' zero teacher-intervention metric
does not erase the disclosed initial setup/prescribed action.

One native episode used284actions/24864frames in2.45seconds. Three foes fainted,
two own members fainted;endpoint PP depletion8versus9selected move spends.
Median model latency2.30ms,max12.73ms. Inherited TRAIN trainer postbattle healing
is not evidence of model recovery skill. No new label,fit,comparison,promotion,
story or registration. All41complete targets remain;only prior36have been fitted.

## Prepared next work

The proposed continuation runner admits ONLY the original three unplayed cells:
first team offset8;second team offsets0and8. It authenticates the failed result
and corrected saved-cell audit, preserves the original first result, uses the
20-test semantic auditor,and will stop on its first error. Prepared,not dispatched.

After the four distinct cells are verified, propose the five unused later-state
TRAIN recipes;never retry the missing or censored old contexts. Retain all41targets,
require the original8late-context/3perphase minimum and all retention gates,then
one declared fit/comparison. No automatic campaign input or deployment.

Campaign461,actual462unused,deployed4ea4cfde,parentb106108e unchanged.
No gameplay running,external agents,GitHub publication or iCloud synchronization.
Next estimate15–30minutes to finish the three remaining runtime checks,conditional
on no new failure. No new full-run readiness or whole-project percentage.
