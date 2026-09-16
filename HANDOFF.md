# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Model133: retained evolution failure, safe Center

Model132 chose **evolution** over restoration from a verified two-way menu. After **106
actions / 6780 frames**, its item skill reached the Center nurse tile but unconditionally
called a healed-farewell routine despite the party being unhealed and no dialogue being open.
It stopped with `RedGoalSkillError`, safely and without purchase, evolution or registration.
The original choice was fitted once as a negative example: **Model133 has 133 settled examples
/ 90 successes / 54 economy-qualified**. Red remains **93/124**, **74 specimens**, **2298 cash**;
the retained state is `fb1dceea7cbc6f1f96452767b20e08569a5fe50a5242001a31b64299a99a76fe`.

The generic item-skill departure now invokes farewell handling only when there is actual
dialogue. It still refuses an active unhealed nurse interaction. **114 focused ROM-free tests**
passed; the repair has not been live validated. Source `17087c3f` was committed locally with
regenerated registry metadata. No replay of Model132 or teacher substitution occurred.

## Exact next bounded work

An action-free Model133 inspection of the earned Center state showed **restore** and **evolve**
(quoted spend **2100**, affordable at 2298 cash), zero inputs/frames/model queries. The
inspect-only plan is in the private workspace `work/` directory; its run output does not exist.
After re-verifying state/source, permit **one fresh Model133 choice** under 3000 actions,
300000 frames and 900 seconds. Retain and fit only its actual outcome. Stop if the Center
boundary fails again. Do not hand-select an evolution target or replay Model132. Battle turns,
evolution target and the fresh-start Red gate remain unlearned or unverified.

[Session evidence](docs/evidence/red-model133-item-evolution-departure-2026-09-16.json) preserves
the hashes and admission limits. No GitHub push. Next: **Sol / High / Fast off**, about
45–75 minutes.
