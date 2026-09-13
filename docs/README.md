# Documentation map

This repository separates live product truth from dated research history. A document can remain
valuable evidence without remaining an instruction.

## Read these first

1. [Mission](../MISSION.md) — the end product: a transferable Pokémon player and one shared,
   verified registered Pokédex.
2. [North star](../NORTH_STAR.md) — anti-drift rules, evidence boundaries and session closeout.
3. [Active product state](../ACTIVE_PRODUCT_STATE.md) — the one current lane, counters and stop
   condition.
4. [Model-first roadmap](model-first-roadmap.md) — the current route from Red play to modified Red,
   Blue/shared memory, Crystal and later titles.
5. [Handoff](../HANDOFF.md) — exact restart state and immediate engineering boundary.

As of the latest measured session, Model114 has 114 settled training-only examples. Its durable Red
checkpoint contains 84 registered species, 64 living species and 68 physical specimens. Model113's
frozen fishing choice added one registration in 513 actions / 30,804 frames and became row114 with
zero teacher labels. From the resulting checkpoint, Model114 selected resupply/income from six
choices across three goal families. That choice is frozen but unexecuted. This is bounded
development, not independent full-game competence.

## Reader-facing summaries

- [Architecture](architecture.md) explains the learned-planner/deterministic-skill hierarchy.
- [Portfolio brief](portfolio-brief.md) is the short public explanation.
- [AI Systems Specialist handoff](ai-systems-specialist-interview-handoff.md) is the detailed,
  interview-safe account of capabilities and limitations.
- [Project narrative](project-narrative.md) and
  [video outline](youtube-video-narrative.md) tell the development story without promoting planned
  features to completed ones.
- [Development infographic](development-roadmap.md) is the generated visual checklist.

## Evidence and history

Files under `docs/evidence/`, `docs/work-sessions/`, `docs/audits/`, and `docs/history/` are dated
records. Their metrics and next steps are frozen to the event they describe. The large
[roadmap](roadmap.md), [story archive](story.md), and
[Red-to-Crystal roadmap](red-to-crystal-readiness-roadmap.md) are retained as historical reasoning;
they do not override the active product state.

When documents disagree, follow the authority order in the North Star. Do not rewrite historical
receipts to match newer goals or counters.
