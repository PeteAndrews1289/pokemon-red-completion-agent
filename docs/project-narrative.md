# Project story: from finishing Red to learning useful choices

Latest overnight result: AW healed the team; AX earned145, bought one GreatBall, then chose Route21 from seven destinations. A paralyzed Tangela escaped the only throw; no new registration. The actual failed destination outcome was audited and fitted:69 to70examples. Current Route21 save:113money,no balls,64registrations/54specimens. [Report](work-sessions/2026-09-11-funded-collection-overnight.md).

## The question

The [resource-choice core](work-sessions/2026-09-11-resource-variant-core.md) addresses
another difference between a working script and useful learning: an affordable
single ball should not hide the option of earning a practical reserve. Flash drafted
the representation; Codex repaired and tested execution/replay. The first actual test still exposed only a purchase. That spending is retained;
no new learning is claimed. Declared-Mart departure is the next access gap.

Can a model learn to play Pokémon well enough to finish its story, seek out missing species and carry useful knowledge into another game?

Red is a manageable first environment, but a fixed walkthrough is not the desired product. The long-term objective is one verified registered Pokédex across games, with explicit version, trade and event dependencies.

## What changed during development

**A reliable teacher was necessary, but not sufficient.** Scripted completion showed that observation, controls and story verification could work. It did not prove the model could plan. Overpowered battles and single-option decisions offered little meaningful choice.

**The project moved to short, saved-state lessons.** Rather than repeatedly replaying the whole game to investigate a local failure, the system chooses a bounded goal, executes it, checks the result and retains the terminal state. Failed attempts and spending remain visible.

**Learning moved into actual goal and destination choices.** The active model ranks useful acquisition, evolution and resource tasks. Mechanics are still deterministic. This hybrid boundary makes the current capability smaller than “AI plays Pokémon,” but it is something concrete to test.

**Collection became registration-first.** Pete removed the level-100 and simultaneous-living-form requirements. Once a species is legitimately registered, later runs should not repeat its evolution solely to earn the same global credit. Global registration, local owned flags and physical inventory remain separate.

## Results we can show

- Checkpoint-based story integration reached the Champion and Hall of Fame with disclosed deterministic battle execution. The final episode contained two learned recovery choices and a forced boss continuation—not an autonomous fresh-game win. [Story audit](audits/red-phase4-closeout-2026-09-09.md).
- The preceding collection batch caught Onix, reaching59 registered species and 51 physical specimens.
- Three of four goals succeeded. Both actual destination outcomes—one failed search and one successful capture—were fitted; two safety-driven resupply steps were excluded. The model grew from 54 to 56 examples. [Collection report](work-sessions/2026-09-10-post-merge-collection.md).

A subsequent [four-goal batch](work-sessions/2026-09-10-preparation-collection.md) added three outcomes—successful model-selected recovery and two failed destination searches—bringing the model to 59 examples, but added no registrations. A small preparation repair measured44.8→28.3 seconds on the same saved input. The search failures exposed another practical constraint: a64-leg patrol produced only two/four destination encounters. Faster infrastructure and more examples do not by themselves mean better collection.

These are related development experiences, not an independent success rate or evidence of cross-game transfer.

The next [bounded continuation](work-sessions/2026-09-10-search-budget.md) caught Paras during travel to a model-selected destination:60 registrations and 60 examples. The overall goal still failed because the arrival report omitted required diagnostic fields. The catch and failure were both retained; fixing the report did not retroactively turn that run into success. This also does not prove the larger search allowance caused the catch—it occurred during travel.

## What the failures taught us

The [next session](work-sessions/2026-09-10-owned-evolution-access.md) exposed an empty goal menu: newly proposed evolutions had lost their transport settings. Restoring existing Fly/indoor access let the system retrieve and train Paras8→Parasect24, reaching61registrations. The model stayed at 60 examples because this was the only available goal. That distinction matters: extending usable mechanics can unlock future learning without being learning itself. The next bottleneck is access/resources, not more searches in already-cleared areas.

Navigation could propose an apparently connected route that was blocked by actual game state. Capture verification could misinterpret the way a new boxed Pokémon shifts existing slots. Resource recovery could be necessary even when its action should not be counted as learned judgment.

The engineering lesson is to verify the consequence, preserve the failed trace and repair a reusable boundary—not conceal a failed attempt with a reset or claim every successful action as model progress.

## Human and AI contributions

Pete defines the objective, observes gameplay, challenges priorities and directs acceptance decisions. Codex performs much of the implementation and integration; Claude and Antigravity provide selected drafts and reviews. This is AI-assisted engineering with human product direction, not an ambiguous claim of sole manual authorship.

Pete also challenged the repository's presentation: thousands of lines of accumulated status reports made the work difficult to understand. In September2026, public summaries were rewritten and detailed reports moved to historical archives. Documentation repair is not a learning milestone.

The [Cut-access session](work-sessions/2026-09-10-cut-collection-access.md) turned an unavailable area into a successful Doduo capture: 62 registrations, but still 60 examples. The engineering worked; only one goal was available. The audit also found that primitive inputs survived while the higher-level field receipt did not. Next expose real alternatives and preserve that diagnostic detail, rather than call every new registration a smarter model.

## What comes next

The [next access session](work-sessions/2026-09-10-surf-collection-access.md) found that eleven unnamed encounter maps had silently disappeared from the inventory. Restoring those names and explicit Surf access was not enough: the capture helper was injured. Legitimate recovery during Doduo's evolution unlocked seven real destinations. The policy selected Power Plant, arrived and spent its last two balls without a catch. The save retained 63 registrations; the failed choice brought the model to 61 examples. The new bottleneck was affordable resupply from an interior. This is the distinction between opening choices, executing them reliably and demonstrating better judgment.

The [supply session](work-sessions/2026-09-10-supply-transport.md) completed that journey and verified a clean exhaustion stop. The model then chose healing, and a separate destination choice caught Shellder on the way to Seafoam B3F and resumed travel. The remaining ball failed against Seel. Model examples rose from 61 to 63 and registrations from 63 to 64. A preliminary reading of the destination-only zero-capture summary missed Shellder; reconciling the exact save, travel trace and fitted gain corrected that before publication. The destination still failed: useful partial progress is not a reason to rewrite its outcome. Capture-support endurance and adequate supplies remain the next bottlenecks.

The [income audit](work-sessions/2026-09-10-renewable-funding.md) found a deeper gap: working funding routines would not teach economics because the model did not observe cash gains or distinguish earning from buying. Pete proposed League income or Pay Day. In the [delegated follow-up](work-sessions/2026-09-10-economy-agent-integration.md), Flash drafted the cross-file economy extension, Claude identified the need for supply-derived cash budgets, and Codex corrected the implementation and verified258targeted tests. Cash metadata still needs an explicit learning objective and runtime connection; no new example, income or registration occurred. This is the difference between logging a resource and teaching a decision. Blue, modified Red and Crystal remain later stages.

The [next economy session](work-sessions/2026-09-11-economy-objective-loop.md) made that distinction testable: changing only observed earnings changes the model's cash prediction and native goal probabilities, while missing historical observations stay unknown. Flash drafted the component; Codex corrected invalid fixtures and an unnecessary compatibility change.183focused tests passed. This is working learning math, not a new live income result:65examples and64registrations remain unchanged. Delegation moved drafting onto another subscription, but the substantial review burden prevents an honest claim of measured net savings.

The unresolved question is not whether code can finish Red. It is how much useful decision-making the model has learned—and whether that knowledge survives a different situation.

[Roadmap](model-first-roadmap.md) · [Full historical narrative](history/project-narrative-through-2026-09-10.md)

The [recovery session](work-sessions/2026-09-10-dig-recovery.md) connected existing Dig mechanics to collection recovery. The learner first sampled exploration, failed, and fitted that outcome; its next sampled choice escaped Seafoam and healed at Fuchsia Center. Examples rose from 63 to 65 while registrations stayed at 64. This is useful feedback and successful composition, not independent proof of smarter play. The next bottleneck is leaving the healed Center for legitimate income: zero balls and 593 money still prevent collection.
