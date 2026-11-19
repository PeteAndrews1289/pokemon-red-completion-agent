# Four completed same-seed Pokémon Red runs

Every save reached the Champion, the Hall of Fame and all 124 route registrations. The four were independent starts on seed `202611161702301`. Their rosters recorded 14, 12, 10 and 15 external continuations respectively, including technical and host interruptions. Run 2 was the fastest on the campaign clock. Run 3 used the fewest recorded frames.

## How long they took

| Run | Campaign split | Real time from dispatch to exit | Cartridge clock | Reported frames | Normal-speed frame equivalent | Effective speed during the campaign split |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 9:34:10 | 12:31:13 | 255:00:00 | 105,248,561 | 489:29:06 | 51.15× |
| 2 | 8:12:59 | 10:52:12 | 255:00:00 | 95,143,772 | 442:29:24 | 53.85× |
| 3 | 10:32:44 | 13:52:21 | 255:00:00 | 94,487,629 | 439:26:19 | 41.67× |
| 4 | 9:42:46 | 12:41:08 | 255:00:00 | 99,366,634 | 462:07:46 | 47.58× |

Times use hours, minutes and seconds. The campaign split sums the opening and the recorded active segment wall times. The dispatch-to-exit clock includes downtime between workers. The native cartridge clock stops at 255 hours. An input-free read of each final save found the cap flag set and the stored minutes, seconds and frames all at zero. The exact uncapped cartridge play time is therefore unavailable. The frame equivalent divides recorded frames by the original hardware rate, roughly 59.73 frames per second. It can include periods when the cartridge clock was paused. [Cartridge clock implementation](https://github.com/pret/pokered/blob/master/engine/play_time.asm) · [Symbol addresses](https://raw.githubusercontent.com/pret/pokered/symbols/pokered.sym) · [Game Boy frame timing](https://gbdev.io/pandocs/Rendering.html)

The frame column ends at the first combined completion split. Run 3 recorded 22 more actions and 1,584 frames before its verified terminal, about 26.5 seconds at normal speed. The other three recorded no further frames.

## Largest differences

- **The first three stayed together through the League.** Runs 1–3 entered the Hall of Fame within 25 seconds of one another, at about 2h 57m. Run 3 reached it 16 seconds before Run 2, then finished the full 124 about 2h 20m later. Run 4 entered the Hall of Fame at 5h 06m.
- **Time outside the campaign split.** Dispatch to physical exit added 2h 57m, 2h 39m, 3h 20m and 2h 58m to Runs 1–4 respectively. That gap includes repair pauses and work outside the timed game segments. It is a separate opportunity from making better in-game choices.
- **Run 4, four to eight badges.** It took 209.4 minutes compared with 53.8 in Run 2. Its 921 closed decisions consumed 160.9 minutes in menu and boundary observation. Run 2 made 297 decisions and spent 35.6 minutes there. This accounts for about 125 minutes of the difference. The Silph rival records already showed 19 losses for Run 4 before its eventual win. Runs 1–3 won after five or six losses. Run 4 obtained Surf at 232.8 minutes from power-on. The other three obtained it around minute 51.
- **Run 3, registrations 75 to 100.** It took 164.9 minutes compared with 74.5 in Run 2. Run 3 made 328 decisions in closed chunks against Run 2’s 110. The menu and boundary observation component was 104.4 versus 26.8 minutes. Individual action records show 149 acquisition attempts and 142 team restorations for Run 3, compared with 39 and 31 for Run 2. The timing includes constructing and observing menus as well as repeated selections.
- **Run 1, Hall of Fame to 50.** It spent 134.8 minutes in that phase versus 59.2 for Run 2. Run 1 made 81 resupply attempts and spent 19.8 minutes executing them. Run 2 made 25 and spent 1.1 minutes. Across all four, the time after the Hall of Fame was 6:37:15, 5:15:39, 7:35:40, 4:36:57 respectively. Together that accounts for 63.3% of the campaign splits.
- **All four, Dragonair to Dragonite.** Target-specific receipts show 1,302–1,518 completed training battles, 57–115 healing trips and 174,074–174,284 XP awarded to Dragonair per run. Those attempts cost 16.6–19.5 minutes of measured execution each. A faster venue or battle strategy would need a matched comparison that includes travel, healing and actual trainee XP.

## Time between milestones

Each row is a nonoverlapping phase, in minutes.

| Phase | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---:|---:|---:|---:|
| Start → badge 4 | 24.7 | 24.7 | 24.7 | 30.7 |
| Badge 4 → badge 8 | 59.4 | 53.8 | 53.7 | 209.4 |
| Badge 8 → Victory Road crossed | 48.8 | 44.2 | 44.0 | 7.2 |
| Victory Road → Hall of Fame | 44.1 | 54.6 | 54.6 | 58.5 |
| Hall of Fame → 50 | 134.8 | 59.2 | 66.2 | 50.2 |
| 50 → 75 registrations | 74.3 | 87.5 | 109.6 | 55.8 |
| 75 → 100 registrations | 90.4 | 74.5 | 164.9 | 58.4 |
| 100 → 124 registrations | 97.8 | 94.6 | 115.0 | 112.5 |

## All 40 cumulative splits

Each entry is the first recorded observation satisfying that milestone, in campaign hours, minutes and seconds. Two milestones can share a receipt. Badge counts and the named leader wins appear separately to make differences in badge order visible.

| Milestone | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---:|---:|---:|---:|
| Badge 1 earned | 0:01:51 | 0:01:52 | 0:01:52 | 0:01:50 |
| Badge 2 earned | 0:05:07 | 0:05:10 | 0:05:08 | 0:05:07 |
| Badge 3 earned | 0:14:30 | 0:14:32 | 0:14:29 | 0:20:18 |
| Badge 4 earned | 0:24:40 | 0:24:44 | 0:24:42 | 0:30:44 |
| Badge 5 earned | 1:09:52 | 1:10:47 | 1:10:40 | 3:46:44 |
| Badge 6 earned | 1:13:38 | 1:12:18 | 1:12:11 | 3:55:19 |
| Badge 7 earned | 1:21:47 | 1:16:50 | 1:16:43 | 3:58:23 |
| Badge 8 earned | 1:24:06 | 1:18:33 | 1:18:26 | 4:00:05 |
| Starter chosen | 0:00:03 | 0:00:03 | 0:00:04 | 0:00:04 |
| Pokédex received | 0:00:22 | 0:00:23 | 0:00:24 | 0:00:23 |
| Brock · Boulder Badge | 0:01:51 | 0:01:52 | 0:01:52 | 0:01:50 |
| Bill helped · SS Ticket | 0:09:24 | 0:09:29 | 0:09:28 | 0:09:45 |
| Misty · Cascade Badge | 0:05:07 | 0:05:10 | 0:05:08 | 0:05:07 |
| Cut obtained | 0:10:56 | 0:10:59 | 0:10:57 | 0:11:47 |
| Lt. Surge · Thunder Badge | 0:14:30 | 0:14:32 | 0:14:29 | 0:20:18 |
| Rocket Hideout cleared | 0:27:55 | 0:27:59 | 0:27:56 | 0:33:20 |
| Silph Scope obtained | 0:28:29 | 0:28:33 | 0:28:30 | 0:33:22 |
| Erika · Rainbow Badge | 0:24:40 | 0:24:44 | 0:24:42 | 0:30:44 |
| Fuji rescued · Poké Flute | 0:36:38 | 0:36:40 | 0:36:38 | 0:44:39 |
| Surf obtained | 0:50:43 | 0:50:47 | 0:50:42 | 3:52:50 |
| Koga · Soul Badge | 1:09:52 | 1:12:18 | 1:12:11 | 3:55:19 |
| Strength obtained | 0:50:51 | 0:50:55 | 0:50:50 | 3:52:57 |
| Silph liberated | 1:17:24 | 1:10:16 | 1:10:09 | 3:44:57 |
| Sabrina · Marsh Badge | 1:21:47 | 1:10:47 | 1:10:40 | 3:46:44 |
| Secret Key obtained | 1:10:55 | 1:13:33 | 1:13:26 | 3:56:47 |
| Blaine · Volcano Badge | 1:13:38 | 1:16:50 | 1:16:43 | 3:58:23 |
| Giovanni · Earth Badge | 1:24:06 | 1:18:33 | 1:18:26 | 4:00:05 |
| Victory Road crossed | 2:12:51 | 2:02:43 | 2:02:28 | 4:07:16 |
| Lorelei defeated | 2:14:15 | 2:18:47 | 2:18:33 | 4:11:09 |
| Bruno defeated | 2:14:21 | 2:19:53 | 2:19:38 | 4:11:37 |
| Agatha defeated | 2:34:05 | 2:25:00 | 2:24:46 | 4:46:15 |
| Lance defeated | 2:40:31 | 2:37:03 | 2:36:47 | 5:05:26 |
| Champion defeated | 2:56:55 | 2:57:20 | 2:57:04 | 5:05:49 |
| Hall of Fame | 2:56:55 | 2:57:20 | 2:57:04 | 5:05:49 |
| 25 route registrations | 3:13:14 | 3:04:21 | 3:04:04 | 5:11:06 |
| 50 route registrations | 5:11:42 | 3:56:29 | 4:03:14 | 5:55:58 |
| 75 route registrations | 6:26:00 | 5:23:57 | 5:52:53 | 6:51:49 |
| 100 route registrations | 7:56:22 | 6:38:26 | 8:37:46 | 7:50:13 |
| 124 route registrations | 9:34:10 | 8:12:59 | 10:32:44 | 9:42:46 |
| Champion / Hall of Fame + route 124 | 9:34:10 | 8:12:59 | 10:32:44 | 9:42:46 |

The [public split and cost records](../evidence/red-campaign-comparison-2026-11-19.json) include all 40 milestone timings per run. All four used the same seed on one PC. Host contention and repairs affected wall time. Each cartridge retained its own progress.
