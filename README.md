# DamDays

**Once a week, DamDays texts a farmer how full each farm dam is and at least how many days it has before it drops below a third, for every farm dam big enough for the satellites to see (about 0.5 to 5 ha of water), worked out from satellite pictures and rainfall, with nothing to install.**

**Live app: <https://shaugato.github.io/damdays/app/>** (on a phone or a computer; nothing to install)

## The weekly text

This is the real text our code wrote for Fri 2 Oct 2026 for a demo farm near Mudgee (Farm E). Its 5 dams and their forecasts are real; the homestead point is made up, and no farmer receives this text yet. Farm E is every dam the satellites can see within 3 km of that point. The circle (2,827 ha) is bigger than a typical target farm and may take in neighbours' dams, and two of the five serve an irrigated paddock and a vineyard. So Farm E shows the method on real farm dams, not one grazier's farm; a typical target farm would see 1 or 2 of its dams in the text.

```
Fri 2 Oct (dams seen 13 Sep)
Dam 1 ~80% full: at least 68 days before it drops below 1/3
Dam 3: no water seen
Other 2 dams: 3 months+
Reply MAP for 1 more dam
```

| the text says | what it means |
|---|---|
| Fri 2 Oct (dams seen 13 Sep) | The day of the text, and the day of the satellites' last clear look at these dams. The satellite data in this build ends on 14 Sep 2026, so the newest look is 19 days old; a running service would start from each dam's latest clear look. |
| Dam 1 ~80% full | At that look, 80% of Dam 1's usual full water surface was wet. "%" only ever means how full; it is not depth. Usual full is the wet area the dam reached or beat in 1 of every 10 clear looks before 2016, so after rain a dam can read above 100% (the text then says "full"). Dam 1 is the dam closest to the homestead. |
| at least 68 days before it drops below 1/3 | Our cautious count, from the day of the text. It is built to hold 9 times in 10: "held" means the dam really stayed above a third for at least that many days, and in 9 of every 10 past cases it did, most lasting well beyond the number. So Dam 1 will most likely last longer. |
| Dam 3: no water seen | The satellites saw no water in Dam 3 at its last clear look. One look can miss a small pool or muddy water, so we never call a dam dry. |
| Other 2 dams: 3 months+ | Dam 5 (at least 98 days) and Dam 2 (6 months or more) each have at least 3 months. |
| Reply MAP for 1 more dam | Dam 4 (~33% full) gets no forecast. DamDays counts days only for a dam that has been back to 60% full in the last six months, a starting rule written down before the build; without it, one long dry spell would count as many separate drops ([docs/DATA.md](docs/DATA.md), "Arming"). Dam 4 has not, so it waits until it refills. MAP replies are not built yet; for now the longer version in the app names Dam 4. |

**Words we use.** A *grazier* raises sheep or cattle on pasture. A *paddock* is a fenced field. The *water run* is the drive around a farm's dams and troughs to check them. *Carting water* is trucking it in when a dam runs low. *Fodder* is bought feed. *Agistment* (to *agist*) is paying to graze stock on someone else's land. The *homestead* is the farmhouse; a *bore* is a well that pumps groundwater. A hectare (*ha*) is 100 m by 100 m. Times are Sydney time: AEST until 02:00 on Sun 4 Oct 2026, AEDT after, when the clocks went forward an hour.

**Who it is for.** Family sheep and cattle farms in south-eastern Australia, mostly 300 to 1,500 ha and run by one or two people, whose stock drink from at least one farm dam big enough for the satellites to see (about 0.5 to 5 ha of water). The profile, from public farm surveys: [docs/TARGET_FARMER.md](docs/TARGET_FARMER.md).

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** (helping farmers adapt to a changing climate)

**On this page:** [The problem](#the-problem) · [What farmers get](#what-farmers-get) · [COP31 fit](#cop31-fit) · [How it works](#how-it-works-in-5-steps) · [How we tested it](#how-we-tested-it-and-why-you-can-trust-it) · [Questions](#questions-people-ask) · [What it does not do yet](#limits) · [For technical readers](#for-technical-readers) · [Team](#team)

## The problem

> **In one sentence:** in a drought, graziers whose stock drink from farm dams must decide when to move stock, cart water, buy feed or sell, but have no easy way to know how many days of water each dam has left.

- **Today they work it out by hand.** Someone drives the water run (every day in a dry summer), measures each dam and does the sums. Agriculture Victoria's own example: 420,000 litres at 8,000 litres a day is 52 days.
- **Drought is expensive, and feed is the big bill.** Carting water is a daily job, and feed costs more: in the 2019-20 drought, NSW sheep-and-cattle farms spent about $114,000 each on fodder on average, against $10,000 to $20,000 a year in 2022-23 to 2024-25 (ABARES; every source is in [docs/TARGET_FARMER.md](docs/TARGET_FARMER.md)).
- **It is happening now.** At the latest satellite looks (to 14 Sep 2026), 272 of the 894 dam-sized waterbodies we track in NSW Central West, mostly farm dams, were already below a third full: about 3 in 10, the most for a September since 2019 (a typical September since 1988 is about 1 in 4; in the 2018-19 drought it was over 6 in 10).

## What farmers get

- **One text a week, per farm.** A mentor told us farmers read a weekly text but rarely open apps or emails, so the text is the product (we have not yet tried it with farmers: [limits](#limits)). A farm is a homestead point plus every dam the satellites can see within 3 km (the data has no property boundaries). Every text fits one SMS. This week's texts for 9 demo farms: [outbox/2026-10-02.json](outbox/2026-10-02.json). The rules, line by line: [notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md).
- **An app to look closer**, in four places:

| place | what is there |
|---|---|
| [My farm](https://shaugato.github.io/damdays/app/#farm) | This week's text as it arrives, the farm from above with its numbered dams, and a card for each dam: how full, at least how many days, the chance it drops below a third by a date (Dam 1: 1 in 10 by 12 Dec, 90 days after its 13 Sep look), the next six months, how full it has been since 1988, and our record on it. **Change** picks another demo farm, or sets your own homestead point and circle size. |
| [Proof](https://shaugato.github.io/damdays/app/#proof) | How we know it works, as pictures ([below](#pictures-not-statistics)). |
| [Questions](https://shaugato.github.io/damdays/app/#questions) | The questions people ask, each with a short answer, the numbers and where to check them. |
| [More](https://shaugato.github.io/damdays/app/#more) | Runway (named for the days of water ahead of each dam: a map of every dam-sized waterbody we track in NSW Central West, coloured by its chance of dropping below a third within 90 days), About, the Area outlook (a season-ahead outlook for 2 km areas, built and tested, then set aside to keep the focus on farmers), and how to put DamDays on your home screen. |

- **On a computer**, the app's first page also tells the story in order: what DamDays is, and the real text in a phone frame.
- **A way to judge us on their own dams.** Each dam's card says how often our days-left number held on that dam over the last 10 years ([below](#a-record-on-every-dam)).
- **Nothing to install and no sign-up.** No sensor on the dam and no tape measure. A homestead point you set in the app stays on your phone.

## COP31 fit

- **Track: Awareness Across All Areas.** Its 2035 goal, from the Participant Guide: "climate-resilient farming and climate education reaching all of society by 2035". DamDays helps farmers adapt to drier, more variable years by turning free satellite and climate data into one line per dam they can act on early: move stock, cart water, buy feed, agist or sell, while there are still choices.
- **Climate education reaching all of society.** One plain SMS needs no app, no data plan and no sign-up, so it reaches farmers who read texts but rarely open apps or emails. Each dam's own record shows them, in plain numbers, how far to trust a forecast, and the app's Proof and Questions explain the climate data behind it.
- **The Global Goal on Adaptation.** Its framework (the UAE Framework for Global Climate Resilience) includes targets on climate-driven water scarcity and on climate-resilient food and farming. DamDays measures water security dam by dam and farm by farm, from public data, and can be refreshed with each clear satellite look (by hand today).
- **Less waste, as a second benefit.** Acting earlier could mean fewer stock losses, less wasted feed and better use of the water already on the farm. We have not measured this yet.
- **Built for 2035.** The same satellite record covers all of Australia and the whole pipeline runs on a laptop, so it can grow region by region, each new region tested before it gets texts. In NSW, Victoria and South Australia, where it was built, ABARES counts about 22,300 beef, sheep and sheep-beef farms (2024-25, our sum, including big western properties; [docs/TARGET_FARMER.md](docs/TARGET_FARMER.md)). Not every one has a dam big enough for the satellites to see.

## How it works, in 5 steps

Think of a car. The fuel gauge shows how full the tank is; the "km to empty" figure tells you how far you can go, from how fast you have been using fuel. Satellite maps of farm dams are a fuel gauge. DamDays adds the second number for every farm dam big enough for the satellites to see, with two differences: it counts the days to a reserve line (a third full), not to empty, and it is cautious on purpose.

1. **The satellites look.** Landsat satellites photograph every farm every week or two, whenever there is no cloud. Geoscience Australia turns each picture into how much of each waterbody is wet (DEA Waterbodies, from Digital Earth Australia). We use 38 years of these looks.
2. **We pick the dams.** We keep waterbodies of about 0.5 to 5 ha that are compact and usually hold water: dam-sized waterbodies, mostly farm dams (894 in NSW Central West, 789 in western Victoria and south-east South Australia).
3. **We read each dam's habits.** How full it is now, how fast it has been dropping, how fast it usually drops in summer, its past dry spells, how the dams around it are doing, and its last two years of water and rain. Each forecast uses only what was known on its day.
4. **We forecast.** Models that learned from past years turn those facts into three answers: the chance the dam drops below a third within 90 days, the chance by each date out to six months, and the cautious count, "at least N days before it drops below a third", built to hold 9 times in 10. Each dam's chance also gets a nudge from its own record ("runs wetter than similar dams").
5. **We write the text.** For each farm, the dams with the fewest days left come first, the rest are summed up, and it all fits one SMS. The app shows the longer version and every dam's card.

More in plain words, with one diagram: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## How we tested it, and why you can trust it

A forecast is only worth acting on if you can see how often it was right. We checked DamDays three ways: on the practice years used to build it, on ten years it never trained on, and on the unseen exam (a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check). We wrote the rules down first.

### The rules came first

The test rules and pass marks were pre-registered: written down and committed (saved with a timestamp) at 09:12 AEST on Fri 2 Oct, and pushed to GitHub (published) at 09:15, before the build began ([PREREG.md](PREREG.md)). They have never been edited. Changes are allowed only as new, dated addenda (additions, each with its date), filed before the unseen exam is opened. [Addendum 1](PREREG_ADDENDUM_1.md) froze the model at 20:21 AEST that evening, before the frozen model was scored on the test years. [Addendum 2](PREREG_ADDENDUM_2.md) (Sun 4 Oct, AEDT) moved the opening of the unseen exam to Sunday and changed nothing else.

### Ten years it never trained on

The model learned only from data before July 2016. We made its forecasts for July 2016 to June 2026, ten years it never trained on, checked each one against what the dam really did, and scored them once, on Fri 2 Oct (20:36 AEST).

- **Nearly a quarter less error than the usual guess.** The usual guess is how often dams in that region fell below a third in that month in earlier years. Error here is how far each chance was from what happened (counting 1 if the dam dropped below a third within 90 days and 0 if not). The pass mark, written down first, was a tenth less error; DamDays got nearly a quarter less. It had less error in every one of the ten years, dry and wet: from a fifth less (2020-21) to a quarter less (2025-26).
- **Also less error than each dam's own record,** a much tougher rule to beat: about a seventh less (the pass mark was a twentieth).
- **The cautious days held 9 times in 10:** 900 times in 1,000, over 729,749 checked forecasts, as designed. (The chances were scored on the 142,938 forecasts made from October to March, when dams run down; the cautious days on every forecast, all year round.) Year by year it ranged from 872 in 1,000 (July 2023 to June 2024, a little short of its mark) to 927 (2020-21).
- **Its chances mean what they say.** Of the 17,013 forecasts that said "3 in 10", 4,864 were followed by a drop below a third within 90 days: about 3 in 10. The same held at every level, to the nearest 1 in 10.
- **One honest caveat.** We had looked at these years in research before the event, so they may flatter the model slightly. That is why the unseen exam (below) exists.

### A record on every dam

Mentors asked for a way for farmers to judge our accuracy themselves. So each dam's card in the app shows how often our days-left number held on that dam in those ten years, using forecasts made only from data before July 2016:

| dams | our days-left number held |
|---|---|
| Farm E, all 5 dams | 1,640 of 1,767 times (about 9 in 10) |
| Farm E, Dam 1 (the dam in the text) | 380 of 428 times |
| Farm E, Dam 4 (its weakest record) | 212 of 246 times |
| The typical dam, of the 929 with at least 5 checked forecasts (of the 941 dams the app shows: all 894 dam-sized waterbodies in NSW Central West, mostly farm dams, plus 47 on the demo farms in western Victoria and south-east South Australia) | 912 times in 1,000 |
| Those that held less than 8 times in 10 | 101 of the 929, shown as they are |

Records can be uneven, and the card shows it season by season: Dam 1 held every time in five of the ten seasons, but only 17 of 32 times in 2020-21 and 32 of 48 in 2025-26. Every number: [artifacts/track_record.md](artifacts/track_record.md).

### Pictures, not statistics

In the app's [Proof](https://shaugato.github.io/damdays/app/#proof), each claim is a picture with its numbers one tap away:

1. **What we said against what happened**, grouped by the chance we gave.
2. **Year after year**, through the dry and wet years since 2016.
3. **Rewind: the 2018-19 drought.** Pick a date, see the forecasts as they were made that day, then reveal what happened.
4. **Dam by dam.** Farm E's dams through that drought. On three dates they got 9 forecasts. Add up the chances we gave (for example 1 in 10 plus 2 in 10, and so on) and they come to about 2 expected drops below a third (1.57); 2 dams did drop.

### The unseen exam

The clean test is **a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check.** We call it the unseen exam. It is Southern Downs, Granite Belt and New England, either side of the Queensland and NSW border: the satellite records of 4,711 waterbodies.

- **Fingerprinted.** Each file's fingerprint (a code that changes if even one byte of the file changes) was published in our very first commit: [SEALED_HASHES.csv](SEALED_HASHES.csv).
- **Opened once.** The opening script checks every file against its fingerprint, and refuses to run unless the models are the frozen ones and everything is committed and pushed. It scores once, on camera: the screen recording of the opening, sped up 30 times, is [docs/media/unseen_exam_opening_x30.mp4](docs/media/unseen_exam_opening_x30.mp4) (the run took 56 minutes, Sun 4 Oct 2026, 09:20 to 10:16 AEDT).
- **Published whatever it shows.** A second script copies the numbers into this page, the pitch and the app, changing nothing but the rounding.
- **When.** It was pre-registered to open at 17:30 AEST on Sat 3 Oct. We moved the opening to Sun 4 Oct (AEDT), after the app build, in a dated addendum that says why ([PREREG_ADDENDUM_2.md](PREREG_ADDENDUM_2.md)). The original time passed on Saturday while the mentor follow-ups, the aerial-photo check of the demo farms and the app redesign were still under way; the addendum was filed on Sunday, after that time but before any opening. The sealed files stayed unopened in the meantime, and the runner re-checks all 4,711 fingerprints before it reads anything.

**Latest status:** <!-- SEALED:START status -->The sealed region was opened and scored once on Sun 4 Oct 2026, 10:16 AEDT; its results were added below on Sun 4 Oct 2026, 10:17 AEDT.<!-- SEALED:END -->

| exam | what it is | result |
|---|---|---|
| **Practice**, 2009 to 2015 | Design choices were made on these years (two were also informed by earlier looks at the test years: [below](#what-these-numbers-do-and-do-not-show)). | All pass marks met. |
| **Ten years it never trained on**, July 2016 to June 2026 | Scored once, on Fri 2 Oct ([artifacts/test_results.md](artifacts/test_results.md)). | **All pass marks met.** |
| **The unseen exam**, the same ten years in the third region | Opened once, on camera, and scored once. | <!-- SEALED:START cell -->**All pass marks met.** [Details below](#sealed-region-opened-sat-3-oct-2026-1730-aest).<!-- SEALED:END --> |

The four pass marks, written down before the build began: at least a tenth less error than the usual guess (on the ten years: nearly a quarter less); at least a twentieth less error than each dam's own record (about a seventh less); chances neither too bold nor too timid (a calibration slope of 0.8 to 1.2; got 1.09); and an Area outlook that ranks 2 km patches better than rainfall alone, by at least 0.05 on a ranking score where 0.5 is a coin toss (got 0.29 better). The exact scores, and the unseen exam's full result, are in [For technical readers](#for-technical-readers).

## Questions people ask

Mentors asked us these during the event. Short answers here; the app's [Questions](https://shaugato.github.io/damdays/app/#questions) page has many more, each with its numbers and where to check them.

**How can a satellite tell how much water is in a dam, when dams differ in depth?**
It can't, and we don't claim to. The pictures show how much of a dam's outline is wet, and "% full" compares that with the same dam's own usual full water surface, so every dam is measured against itself. A deep dam and a shallow dam shrink at different speeds, and each dam's 38-year record shows its own speed, which the forecast reads. What we cannot do is turn days into litres: in a bowl-shaped dam, a third of the surface holds well under a third of the water, so treat "below a third" as a warning light, not a safe level.

**Why not just fit a dam sensor?**
A sensor reads one dam's exact level right now, better than we can. But it has to be bought and fitted to each dam (hundreds of dollars a device, some with a monthly fee), and none of the sensor products we checked advertised a forecast. DamDays needs nothing installed, covers every farm dam big enough for the satellites to see, and looks ahead. The two could work together: a sensor reading could anchor the forecast (not built).

**Which farms is it for?**
Family sheep and cattle farms in south-eastern Australia's dam country, mostly 300 to 1,500 ha, run by one or two people, whose stock drink from at least one farm dam big enough for the satellites to see (about 0.5 to 5 ha). Not bore-watered stations, irrigators, or hobby blocks whose dams are too small to see. A typical target farm sees 1 or 2 of its dams in the text.

**Is it Australia only?**
For now, yes. It runs on Australian public data and has been tested only in south-eastern Australia: NSW Central West, western Victoria and south-east South Australia, and the unseen exam's region. Similar satellite water records exist elsewhere (Digital Earth Africa Waterbodies, and JRC Global Surface Water for the whole world), so other countries are a possible later path. None is built, and each new place would need its own test first.

**What already exists, and what is new?**
A lot exists: dam sensors (today's level), NSW's monthly farm dam maps from the same satellite record (by parish, no forecast), Victorian tools that work out days or months of water from the farmer's own measurements, and in Africa, USGS FEWS NET's 30-day forecast for livestock water points. Forecasting stock water is not our invention. What we did not find is the combination: a forecast for each farm dam big enough for the satellites to see, with nothing to install or measure, tested in public against rules written before the build, with a record on every dam, sent as one weekly text. The full comparison: [docs/WHAT_EXISTS.md](docs/WHAT_EXISTS.md).

**Who else could use dam forecasts?**
Ideas, not built: added up by district, never farm by farm, the same forecasts could show drought support teams and fire agencies where water is running short soonest. We also built and tested a season-ahead Area outlook for 2 km areas with lenders in mind (a farm's water security matters to whoever lends against it); it is in the app under More, but set aside, because our one audience is farmers.

**Will it keep up as the climate shifts?**
We don't assume the past repeats: each forecast starts from the dam's latest look and how fast it is dropping. A model that learned only from data before July 2016 still had less error than the usual guess in every one of the next ten years, dry and wet, and Proof shows where the weather pushed it off (in the wetter years its chances ran high). In use it is refit on the newest satellite looks; today we do that by hand.

<a id="limits" name="limits"></a>

## What it does not do yet

- **Small dams.** It sees only dams with about 0.5 ha of water or more: the satellite needs at least 6 of its 30 m pixels (about 5,400 m²). The average Australian farm dam is about 0.27 ha, so most farm dams are not covered.
- **Bores, tanks, troughs and rivers.** It sees surface water in dams only.
- **Depth and litres.** It sees how much of a dam is wet, not how deep it is. "Below a third" is our plain rounding of below 30% of the dam's usual full wet area, confirmed by a second clear look.
- **Old looks.** A forecast starts from the dam's last clear look, which can be weeks old when there is cloud. The satellite data in this build ends on 14 Sep 2026.
- **No days number for dams already low.** This week 318 of the 894 dam-sized waterbodies in NSW Central West get no days number: 272 are already below a third, 44 have not been back to 60% full in the last six months, and 2 have had no clear look in 60 days. The text names them, but on a farm with many dams those lines are the first cut to fit one SMS (the dams with no forecast first); the text then ends "Reply MAP for N more dams", and the app lists every dam.
- **"No water seen" is not "dry".** One look can miss a small pool, or muddy or green water. At the latest looks (to 14 Sep 2026), 148 of the 272 dam-sized waterbodies below a third in NSW Central West read 0%.
- **Not every dam-sized waterbody is a farm dam.** The filter picks waterbodies by size, shape and water history, not land use, so it also catches some town and industrial ponds and short stretches of river. On Sat 3 Oct we checked every demo farm's 3 km circle against aerial photos (dam by dam for five of them). Farm E's 5 dams are all farm dams: a ring tank in an irrigated paddock, a vineyard dam, two paddock dams and a dam on a creek. The Dubbo demo farm (Farm D) was set aside: none of its 7 waterbodies was clearly a farm dam (three cells of a treatment-pond complex, a racecourse pond, a town-edge pond and a stretch of the Macquarie River). The circles of Farms C, G, H, I and J also take in mine, wetland, town or treatment-works waterbodies, so they stay in the app as examples of what the filter picks, not as checked farms. The 894 and 789 dam-sized waterbodies of the two regions, mostly farm dams, have not been checked one by one.
- **Stock numbers.** It does not know head counts, pumping or carting. A heavier draw shows up only once new looks see the dam dropping faster.
- **Which dams, more than which year.** It is good at "which dams run low this summer" and weak at "will this dam run low this year or next".
- **Very wet and very dry years.** In the wet 2010-12 years its chances ran too high on average, and the cautious days fell a little short of their mark in 2023-24 (872 in 1,000).
- **Two numbers, two models.** The days-left count and the chance by a date come from different models, so on one dam they can differ a little; the app marks the DamDays day (the date the days-left count runs out: 9 Dec for Dam 1) on the six-month chart so both can be read together.
- **Tested only in south-eastern Australia.** Other climates, such as the tropical north or Western Australia, are untested.
- **Not tested with farmers.** The weekly text rests on a mentor's advice; we have not yet tried it with graziers, or checked mobile coverage on farms.
- **Not yet a running service.** No text has been sent to a real farmer. Opt-in and the MAP and STOP replies are not built, and the refit on new satellite looks is run by hand. The sender runs only with your own SMS account's keys.
- **Not advice.** Use it alongside your own eyes on the dam and your local knowledge.

---

## For technical readers

Everything below is for readers who want the methods, the exact scores and how to rebuild them. Here the jargon is used, and explained once.

| term | meaning |
|---|---|
| **Skill** (Brier skill score) | The share of a simple rule's squared error that the forecast removes. +0.235 means it removes 0.235 of that error ("nearly a quarter less error"); 0 means no better than the rule. |
| **B0**, "the usual rate" | The simple rule: how often dams fell below a third within 90 days, for that region and calendar month. |
| **B2**, "the dam's own record" | A tougher rule: how often this dam's own past forecasts were followed by a fall below a third. |
| **AUC** | Ranking: shown one dam that fell below a third and one that did not, how often the forecast gave the first the higher chance. 0.5 is a coin toss; 1.0 is perfect. |
| **Calibration slope** | Whether the chances are as spread out as the outcomes. 1.0 is ideal; above 1 means the chances could be bolder. |
| **95-in-100 range** (brackets) | Found by re-drawing the dams at random 500 times and scoring again. A range above zero means the result is unlikely to be luck. |
| **R30**, **D0** | R30: below 30% of the dam's usual full wet area ("below a third"), confirmed by a second clear look. D0: no water seen (~0% full). |
| **The DamDays floor** | "At least N days above a third, 9 times in 10": the cautious days-left count. |
| **Tidemark**, **L0 to L3** | The forecasting engine, in the four pre-registered versions of the fallback ladder. L3 (full Tidemark) was frozen. |
| **G2** | Our own pre-registered benchmark: the decision-tree model alone, without the neural nets, the per-dam correction or the water balance (rung L0). |

### The unseen exam, in full

- **The region.** Southern Downs, Granite Belt and New England (lat -31.5 to -26.0, lon 150.5 to 152.6). One DEA Waterbodies file per waterbody, 4,711 in all, downloaded before the event; their SHA-256 fingerprints were committed in the first commit, Fri 2 Oct 09:12 AEST ([SEALED_HASHES.csv](SEALED_HASHES.csv)).
- **The test.** Models fitted on the two development regions, on answers known before 1 July 2016, score every sealed forecast from July 2016 to June 2026 (season ratings 2016 to 2025). The sealed region's own history before July 2016 sets only its local averages and baselines ([PREREG.md](PREREG.md), "Sealed region protocol").
- **The opening.** [`scripts/20_open_sealed_region.py`](scripts/20_open_sealed_region.py) (runbook: [docs/SEALED_OPENING.md](docs/SEALED_OPENING.md)) refuses to start unless the unlock switch is on, git is clean and pushed, every sealed file's SHA-256 matches [SEALED_HASHES.csv](SEALED_HASHES.csv), the models match their committed fingerprints ([artifacts/sealed_models_manifest.json](artifacts/sealed_models_manifest.json)) and the freeze addendum is committed. It then builds the region from raw files with the development code ([`damdays/sealed/`](damdays/sealed/)), forecasts it with the frozen models and scores it once.
- **Publishing.** [`scripts/21_publish_sealed.py`](scripts/21_publish_sealed.py) copies the numbers from the raw results into the marked blocks of this page, [docs/PITCH.md](docs/PITCH.md), [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md) and the app's unseen-exam panel. It rounds, never recomputes, and refuses a dry run. The block below is its output; before the opening it shows what we said to expect.

<a id="sealed-region-opened-sat-3-oct-2026-1730-aest" name="sealed-region-opened-sat-3-oct-2026-1730-aest"></a>

### The unseen exam: the result

<!-- SEALED:START -->
**All 4 pre-registered pass marks met.** The frozen model (Tidemark L3) was scored once on the sealed region (Southern Downs, Granite Belt and New England), a region it never learned from: 4,711 waterbodies, every forecast issued from July 2016 to June 2026. Scored Sun 4 Oct 2026, 10:16 AEDT. Every number below is copied from [`artifacts/sealed/sealed_results.json`](artifacts/sealed/sealed_results.json) by `scripts/21_publish_sealed.py` (Sun 4 Oct 2026, 10:17 AEDT) and only rounded; the full results page, unedited, is [`artifacts/sealed/SEALED_RESULTS.md`](artifacts/sealed/SEALED_RESULTS.md).

**In plain words**

- **Farmer forecast** (will this dam fall below a third in the next 90 days?): 18.3% less error than guessing the usual rate for the region and month (development test years: 23.5% less), and 12.3% less than the dam's own track record. Shown a dam that fell below a third and one that did not, it gave the right one the higher chance 8 times in 10 (AUC 0.81). Average chance given 0.16; share that fell below a third 0.15. 166,194 forecasts made October to March for 1,990 dam-sized waterbodies that look and behave like farm dams; 25,130 fell below a third.
- **Against our own benchmark G2** (the decision-tree model alone), on exactly the same forecasts: ahead by +0.012 (95% range +0.008 to +0.014). We expected +0.01 to +0.03: inside that range.
- **The DamDays floor, the cautious days** ("at least N days above a third, 9 times in 10"): held for 88.2% of 820,516 forecasts, on target (the target is 90%, and 88% to 92% counts as on target; development test years: 90.0%). Worst year: July 2018 to June 2019, 84.3%.
- **Area outlook**, the pre-registered lender rating, set aside (will every dam the satellites can see in a 2 km patch fall to no water seen, ~0% full, between October and March?): shown a patch whose dams did and one whose dams did not, it picked the right one 8 times in 10 (AUC 0.81), against 5 in 10 for rainfall alone (0.54; a coin toss is 5 in 10); development test years 0.81 against 0.53. 16,373 patch-seasons rated on 1 July 2016 to 2025; in 1,834, every dam fell to ~0% full. Gain over rainfall-only +0.269 (95% range +0.248 to +0.288): pass mark met; kill rule not triggered. Within a single season: 0.81 against 0.51 for rainfall. The dam-by-dam rating's gain over rainfall-only: +0.250 [+0.233, +0.268], met.
- **Season band** (how far a very wet or very dry year can move a forecast): covered 10 of 10 July-June years in the region, an independent check here (the single-block band, reported alongside as pre-registered: 8 of 10).
- **Runway curve** (chance of falling below a third within 30, 60, 90 and 180 days), skill against each horizon's usual rate: +0.088 at 30 days, +0.145 at 60 days, +0.176 at 90 days, +0.197 at 180 days; none went down as the days went up.
- **Harder cases, reported whatever they show** (skill against the usual rate): persistent dams +0.170 (G2 +0.157); fully dry (D0) +0.173 (G2 +0.149); gradual dry-out (D0g) +0.168 (G2 +0.142); all months +0.204 (G2 +0.177); without the 3-look rule +0.182 (G2 +0.170).
- **How it was opened:** 4,711 of 4,711 sealed files matched their published fingerprints before anything was read. Code fingerprint of the run: `7d466291008d`, the frozen one (quoted in [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md)).

**Pass marks** (written before the build began: [PREREG.md](PREREG.md), "Pass bars"):

| pass mark | bar | DamDays (Tidemark) | benchmark G2 |
|---|---|---|---|
| Farmer forecast: skill against the usual rate for the region and month (Brier skill score vs B0) | +0.10 or more, 95% range above 0 | +0.183 [+0.171, +0.197] **PASS** | +0.172 **PASS** |
| Farmer forecast: skill against the dam's own track record (vs B2) | +0.05 or more | +0.123 [+0.115, +0.131] **PASS** | +0.110 **PASS** |
| Farmer forecast: calibration slope (1.0 = chances exactly as spread out as the outcomes) | 0.8 to 1.2 | 1.02 **PASS** | 1.10 **PASS** |
| Area outlook (the pre-registered lender rating): ranking gain over rainfall-only (AUC, 2 km patches) | +0.05 or more, 95% range above 0 | +0.269 [+0.248, +0.288] **PASS** | (G2 has no Area outlook) |
| Kill rule: rainfall-only within 0.02 of the rating | must not trigger | not triggered | |

**What we said to expect, before opening** (forecasts, not pass marks: [PREREG.md](PREREG.md), "Pre-declared expectations"). 6 of 6 results came out inside the ranges we declared before opening.

| expectation | declared before opening | got [95% range] | |
|---|---|---|---|
| Skill against the usual rate | +0.15 to +0.23 (central +0.19) | +0.183 [+0.171, +0.197] | inside |
| Skill against the dam's own record | +0.08 to +0.15 | +0.123 [+0.115, +0.131] | inside |
| Calibration slope | 0.90 to 1.25 | 1.02 [0.99, 1.05] | inside |
| Calibration-in-the-large (0 = right on average) | -0.30 to +0.30 | -0.07 [-0.11, -0.03] | inside |
| Gain over the benchmark G2 | +0.01 to +0.03 | +0.012 [+0.008, +0.014] | inside |
| Area outlook: gain over rainfall-only (AUC) | +0.15 to +0.30 | +0.269 [+0.248, +0.288] | inside |

<!-- SEALED:END -->

### Practice and test years: the scores

The model was frozen on Fri 2 Oct 2026 at 20:21 AEST: rung L3, code fingerprint `7d466291008d` ([PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md)). The test years were scored once, at 20:36 AEST the same evening ([artifacts/test_results.md](artifacts/test_results.md)). Validation (2009-15) is the practice exam on which design choices were made (two were also informed by earlier looks at the test years; see below).

**For the farmer: will this dam fall below a third of full in the next 90 days?** Forecasts made from October to March (when dams run down), for waterbodies that look and behave like farm dams. Test: 142,938 forecasts, 29,415 of which fell below a third.

| what we measured | validation 2009-15 | test 2016-26 | what it means (test) |
|---|---|---|---|
| Skill against the usual rate for that region and month (B0) | +0.180 [+0.165, +0.197] | **+0.235** [+0.224, +0.248] | nearly a quarter less error than guessing the usual rate |
| Skill against the dam's own record (B2) | +0.110 | +0.155 | about a seventh less error than the dam's own record, a much tougher rule to beat |
| Ranking (AUC) | 0.79 | 0.82 | the right way round 8 times in 10 (a coin toss is 5 in 10) |
| Gain over our own benchmark G2, on exactly the same forecasts | +0.010 [+0.007, +0.014] | +0.014 [+0.011, +0.018] | small, but reliably above zero |
| Calibration slope (pass mark 0.8 to 1.2) | 1.06 | 1.09 | the chances are about right, if a little cautious |
| **The DamDays floor**, "at least N days above a third, 9 times in 10" | held 900 times in 1,000, of 304,611 [897 to 903] | held **900 times in 1,000**, of 729,749 [898 to 902] | held 9 times in 10, as designed; the typical N was 60 days |

The **six-month chance** (of falling below a third within 30, 60, 90 and 180 days) beats each horizon's own usual rate on the test years by +0.105, +0.178, +0.223 and +0.253. No curve ever went down as the days went up (0 of 147,196 checked).

**The Area outlook (built with lenders in mind, set aside): will every dam the satellites can see in this 2 km patch fall to ~0% full this summer?** Rated each 1 July, before the season. A patch counts when every dam DamDays tracks in it fell to ~0% full (no water seen at a clear look) between October and March. Test: 14,331 ratings over 10 seasons (2016-17 to 2025-26), 2,316 of which did.

| what we measured | validation (7 seasons) | test (10 seasons) | what it means (test) |
|---|---|---|---|
| Ranking (AUC), DamDays rating | 0.79 [0.77, 0.80] | **0.81** [0.80, 0.82] | shown a patch whose dams fell to ~0% and one whose dams did not, it picks the right one 8 times in 10 |
| Ranking (AUC), rainfall-only score (the kind most drought tools use today) | 0.54 | 0.53 | close to a coin toss |
| Ranking within a single season: DamDays against rainfall-only | 0.79 against 0.47 | 0.81 against 0.49 | in a given summer, rainfall alone cannot tell which farms' dams will fall to ~0% |
| Gain over rainfall-only (pass mark +0.05; the "kill rule" drops the lender claim if the gain is under 0.02) | +0.25 [+0.23, +0.27] | **+0.29** [+0.27, +0.30] | passed by a wide margin; kill rule not triggered |
| Gain over the dam's own dry-season record alone | +0.014 | +0.029 | most of the rating's power comes from that record; the model adds a little |

### What these numbers do and do not show

- **Every pre-registered pass mark was met**, on validation and on test. On test, our own simpler benchmark G2 met the three farmer-forecast marks too ([artifacts/test_results.md](artifacts/test_results.md), "PREREG pass bars").
- **The test years are not a perfectly clean test.** Some design choices were informed by earlier scores on these years, so they may flatter the model slightly (the pre-registration estimates by about 0.005 to 0.01 of skill). The reasons are listed at the top of the results page and in [DISCLOSURE.md](DISCLOSURE.md). **The clean test is the sealed region.**
- **Worst year for the floor:** July 2023 to June 2024, when it held 872 times in 1,000, a little below the target range of 880 to 920. In the other nine years it held between 884 and 927 times in 1,000.
- **Spring looks:** across all dams the floor held 9 times in 10; for forecasts made from spring looks it held a little less often, which is why the app and the longer version of the text say so. That count comes from a check we ran outside the published scripts, so it is not yet in this repository's results files.
- **Season band** (how far a very wet or very dry year can move a forecast): it covered all 20 test region-years, but its design was partly chosen after seeing these years, so this is not an independent check. The earlier single-block band covered 17 of 20; every miss was a year drier than it allowed.
- **Track record and Proof are counts, not new tests.** [`scripts/17_proof_data.py`](scripts/17_proof_data.py) and [`scripts/18_track_record.py`](scripts/18_track_record.py) count the same saved test forecasts by chance level, year and dam; each refuses to write unless its totals equal the test results. The track record judges the number as the app and the text show it (whole days, with "6 months+" judged at 180 days); counted that way, the test years held 909 times in 1,000 (of 730,449), against 900 for the floor itself. The results page reports both.

### Where the key logic lives

Read in this order. Each file starts with a plain-English explanation.

| file | what it does |
|---|---|
| [`damdays/models/tidemark.py`](damdays/models/tidemark.py) | The whole forecasting engine in one place: `fit_tidemark` learns only from answers known before a cutoff date, `predict_tidemark` makes every forecast (90-day chances, the six-month curve, the "at least N days" floor, the season band, the area rating). The same two calls run every version of the model on the pre-registered ladder (L0 = the benchmark G2, L1 = + per-dam correction, L2 = + neural nets, L3 = + water balance), and every version returns the same columns. |
| [`damdays/features/spec.py`](damdays/features/spec.py) | Every number a model is allowed to see, each with the reason it cannot see the future. [`tests/test_no_lookahead.py`](tests/test_no_lookahead.py) proves it: delete the future, rebuild, and every past input must be identical. |
| [`damdays/models/frailty.py`](damdays/models/frailty.py) | The per-dam correction ("this dam runs drier than similar dams"), learned from the dam's own past forecasts, but only once their answer was known. |
| [`damdays/models/hazard.py`](damdays/models/hazard.py) | The six-month curve: the chance of falling below a third within 30, 60, 90 and 180 days, built so it can never go down as the days go up. |
| [`damdays/models/nets.py`](damdays/models/nets.py) | The two small neural nets (rung L2): one reads the dam's last 24 complete months of water and rain ([`damdays/features/sequences.py`](damdays/features/sequences.py)), the other its current facts. Each answers all three questions at once, is trained with 3 seeds, and learns only from answers known before the cutoff. |
| [`damdays/models/physics.py`](damdays/models/physics.py) | The water-balance outlook (rung L3): a simple bucket model of each dam (rain in, evaporation and stock use out), kept on track by the satellite looks, run over the rain of the 20 previous years. Gives two extra inputs to the learning model and the six-month curve. |
| [`damdays/models/uncertainty.py`](damdays/models/uncertainty.py) | The DamDays floor ("at least N days, 9 times in 10") and the season band. |
| [`damdays/models/season_rating.py`](damdays/models/season_rating.py) | The Area outlook (first built as a lender rating): will a patch's dams fall to ~0% full this summer? It starts from each dam's own dry-season record and is tested against rainfall-only scores. |
| [`damdays/evaluation/scorecard.py`](damdays/evaluation/scorecard.py) | The one scorecard every model is judged by, with confidence ranges and a ledger that allows each model only one look at the test years ([docs/SCORECARD.md](docs/SCORECARD.md)). |
| [`scripts/12_ladder_val.py`](scripts/12_ladder_val.py) | The pre-registered fallback ladder: fits L0 to L3 through `fit_tidemark`, compares each with the pre-event research value, and reads the look-ahead test, so the version to freeze follows mechanically from the rule ([artifacts/ladder_val.md](artifacts/ladder_val.md)). |
| [`scripts/13_fit_test_setting.py`](scripts/13_fit_test_setting.py) | Fits the frozen models on answers known before 1 July 2016 and saves their forecasts for the test years. It scores nothing. |
| [`scripts/15_score_test.py`](scripts/15_score_test.py) | The test years' one look: reads step 13's saved forecasts (fingerprints checked) and scores them once through the ledger. Writes [artifacts/test_results.md](artifacts/test_results.md). |
| [`scripts/17_proof_data.py`](scripts/17_proof_data.py) | The data behind the app's Proof view: the same saved test forecasts, drawn, not scored again (its totals must equal the test results). |
| [`scripts/18_track_record.py`](scripts/18_track_record.py) | Each dam's record: the same saved test forecasts counted dam by dam, "our days-left number held N of M times on this dam"; added up over every dam they must equal the test results. |
| [`scripts/20_open_sealed_region.py`](scripts/20_open_sealed_region.py) | The sealed-region opening, run once ([above](#the-unseen-exam-in-full)). `--dry-run` rehearses the whole pipeline on a development region treated as unseen, on a separate ledger. |
| [`scripts/21_publish_sealed.py`](scripts/21_publish_sealed.py) | Publishes the sealed results with one command: the marked blocks of this page, the pitch and the video script, and the app's unseen-exam panel (through scripts/11's own panel code, with the floor block and its frozen on-target flag copied from the results). It rebuilds the app's data parts and checks they carry the panel. |
| [`damdays/export/`](damdays/export/) | Turns forecasts into the app's data files: [`live_model.py`](damdays/export/live_model.py) refits Tidemark on every answer known by the last satellite look for today's forecasts (shown, never scored), and [`app_data.py`](damdays/export/app_data.py) writes the JSON files the app reads, copying every score from the evaluation outputs. Run with [`scripts/11_export_app.py`](scripts/11_export_app.py); its `--panel-only` mode fills the unseen-exam panel alone. |
| [`notify/`](notify/) | The weekly text ([notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md)): finds a farm's dams (every dam within 3 km of a homestead point, Dam 1 the closest), writes the SMS and its longer app/email version from the live forecasts, and keeps each text to one SMS. It only reads the forecasts; it does not import or change the frozen model. Run with [`scripts/16_weekly_texts.py`](scripts/16_weekly_texts.py); checked by [`tests/test_weekly_text.py`](tests/test_weekly_text.py). |
| [`app/`](app/) | The app: plain HTML, CSS and JavaScript, no build step ([app/README.md](app/README.md)). [`app/js/text.js`](app/js/text.js) is a line-for-line JavaScript copy of the weekly text, checked against the Python by [`app/tools/check_text_port.js`](app/tools/check_text_port.js). [`app/tools/build_bundle.py`](app/tools/build_bundle.py) packs the JSON files into content-hashed data parts (listed in `app/data/real/parts.js`) and stamps the offline copy (`app/sw-version.js`). |

### Reproduce

Everything runs on a laptop CPU (built on Windows 11 with Python 3.12, 8 cores and 32 GB RAM). Steps 01 to 18 rebuild every number on this page from the raw public data, in about 5 to 7 hours, most of it model fitting.

**1. Set up** (once, from the repo folder; Python 3.12):

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

On macOS or Linux, use `.venv/bin/python` wherever this page says `.venv/Scripts/python.exe`. If pip finds no `torch==2.14.1+cpu` for your computer (macOS has no `+cpu` build), change that line of [requirements.txt](requirements.txt) to `torch==2.14.1`.

**Quick check from a fresh clone** (about 5 minutes, no data download). The raw data and `data_cache/` (everything steps 01-13 compute) are not in git, but these run on the committed files alone:

```
.venv/Scripts/python.exe -m pytest tests -rs
.venv/Scripts/python.exe scripts/14_config_hash.py
node app/tools/check_text_port.js
python -m http.server 8000 --directory app
```

- **The tests** take about 4 minutes. The tests on the real data skip, each saying what it needs: the git-ignored `data_cache/` (rebuilt from the raw data by steps 01-02 below) or the raw data itself. Everything else runs. A fresh clone with no data, checked on Sun 4 Oct 2026 (AEDT) on the files of the commit that added this line: 426 passed, 81 skipped. Without Node.js, the text-port tests skip too.
- **The code fingerprint** printed must be `7d466291008d`, the one frozen in [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md). (It rewrites the date in `artifacts/config_hash.json`; `git checkout artifacts/config_hash.json` undoes that.)
- **The weekly text** in the app is written by JavaScript; `check_text_port.js` (Node.js) prints `same` for every text the Python wrote.
- **The app**: open http://localhost:8000 (or double-click `app/index.html`). It reads only the committed files in `app/data/real/`: `parts.js` and the content-hashed part files it lists (`bundle.js` is the old one-file copy, kept for the tests and `?data=mock`). The background maps need internet.

**The live app** is served by GitHub Pages from the `main` branch (root folder), live since Sun 4 Oct (about 07:40 AEDT): every push to `main` updates <https://shaugato.github.io/damdays/app/> in 1 to 2 minutes. Each place has its own link (`#farm`, `#farm/dam-1`, `#proof`, `#proof/rewind`, `#questions`, `#more`, `#runway`, `#about`, `#outlook`; old links `#rewind`, `#map`, `#rating` and `#faq` still work). How the data is split, the offline copy and the checks: [app/DEPLOY.md](app/DEPLOY.md).

**2. Raw data** (public, CC BY 4.0; not in the repo because of its size). Point the environment variable `DAMDAYS_RAW` at a folder holding `dea_dev/ts/` (one DEA Waterbodies CSV per waterbody), `dea_dev/manifest.csv`, `dea_polygons/wb.zip` (the DEA Waterbodies v3 outlines) and `silo/` (SILO monthly rainfall, one file per year). The sources and every cleaning step are in [docs/DATA.md](docs/DATA.md); the default location is set in [`damdays/config.py`](damdays/config.py). The sealed folder `dea_sealed/` is only ever read by step 20.

**3. Run the steps in order** (each script's first lines say what it does; `--quick` skips the confidence ranges where a script offers it):

| step | command | what it does | time |
|---|---|---|---|
| 01 | `.venv/Scripts/python.exe scripts/01_build_data.py` | clean satellite history, dam shapes, events where a dam fell below a third or to ~0% full, rainfall | about 1 min |
| 02 | `.venv/Scripts/python.exe scripts/02_build_features.py` | the facts each forecast may use (only what was known that day) | 5-8 min |
| 03 | `.venv/Scripts/python.exe scripts/03_baselines_and_g2.py` | the simple rules and the benchmark G2, on validation | about 25 min |
| 04 | `.venv/Scripts/python.exe scripts/04_tidemark_l1.py` | the decision trees and the per-dam correction | about 30 min |
| 05 | `.venv/Scripts/python.exe scripts/05_season_rating.py` | the Area outlook (once the lender rating), on validation | about 2 min |
| 06 | `.venv/Scripts/python.exe scripts/06_hazard_curve.py` | the six-month curve | about 35 min |
| 07 | `.venv/Scripts/python.exe scripts/07_uncertainty.py` | the DamDays floor ("at least N days") and the season band | about 5 min |
| 08 | `.venv/Scripts/python.exe scripts/08_tidemark_val.py` | version L1 end to end, on validation | about 15 min |
| 09 | `.venv/Scripts/python.exe scripts/09_nets_val.py` | the two neural nets (version L2) | 30-40 min |
| 10 | `.venv/Scripts/python.exe scripts/10_physics_val.py` | the water-balance outlook (version L3) | 30-50 min |
| 11 | `.venv/Scripts/python.exe scripts/11_export_app.py --rung L3 --season 2018 --refit-live` | the app's data files, as shipped (frozen L3; Rewind and the Area outlook on 2018-19). **Run it after step 15**: a test season is shown only after the one-time scoring. With no options it makes a validation-season export at rung L1 instead (options in its first lines) | about 25 min |
| 12 | `.venv/Scripts/python.exe scripts/12_ladder_val.py` | all four versions side by side: decides which may be frozen | 60-75 min |
| 13 | `.venv/Scripts/python.exe scripts/13_fit_test_setting.py` | fits the frozen models on answers known before 1 July 2016 and saves the test forecasts; scores nothing | 45-75 min |
| 14 | `.venv/Scripts/python.exe scripts/14_config_hash.py` | the code fingerprint; for the frozen code it prints `7d466291008d` | seconds |
| 15 | `.venv/Scripts/python.exe scripts/15_score_test.py --check`, then `.venv/Scripts/python.exe scripts/15_score_test.py` | `--check` builds and checks every table and scores nothing; the second command is the test years' one look | 15-30 min |
| 16 | `.venv/Scripts/python.exe scripts/16_weekly_texts.py --date 2026-10-02` | the weekly texts for the 9 demo farms, as shown at the top of this page. Farm D (near Dubbo) is set aside by default, with its reason in `farms.json` (`--set-aside ""` keeps it). Without `--date` the texts are dated today, so the days change. Needs step 11's live fit; `--regions nsw_cw` needs only the app's published file | seconds |
| 17 | `.venv/Scripts/python.exe scripts/17_proof_data.py` | the app's Proof view (`app/data/real/proof.json`): what we said vs what happened, year by year, dam by dam (Farm E), from step 13's saved test forecasts. Scores nothing; refuses to write if its totals differ from step 15's results. Run after step 16 | about a minute |
| 18 | `.venv/Scripts/python.exe scripts/18_track_record.py` | each dam's record (`app/data/real/track_record.json`, and `artifacts/track_record.md`). Scores nothing; refuses to write unless its counts over every dam equal step 15's results and step 17's groups. Run after step 17 | seconds |

Steps 11, 16, 17 and 18 each rebuild the app's data parts and restamp `app/sw-version.js` themselves (through `app/tools/build_bundle.py`), so commit `app/data/real/` and `app/sw-version.js` together. Then the tests: `.venv/Scripts/python.exe -m pytest tests` (with `data_cache/` built, the tests on the real data run instead of skipping).

**Steps 20 and 21 are not part of the rebuild.** `scripts/20_open_sealed_region.py --open` opens the sealed region once, on camera (runbook: [docs/SEALED_OPENING.md](docs/SEALED_OPENING.md)); `scripts/21_publish_sealed.py` then publishes its results (`--check` previews and writes nothing).

Two things to know when re-running:

- **The test ledger** ([artifacts/test_ledger.csv](artifacts/test_ledger.csv)) records this build's one look at the test years. Re-running step 15 on the same saved forecasts only adds "same predictions" rows; forecasts that differ in any digit are refused, by design. To score a fresh rebuild, start from an empty ledger.
- **Re-running step 13** writes new model files. Their fingerprints can differ from the ones committed with the freeze ([artifacts/sealed_models_manifest.json](artifacts/sealed_models_manifest.json)), and step 20 refuses models whose fingerprints differ.

### Honesty notes

- **Before the event.** Pre-event research and the data download were confirmed as allowed by a hackathon mentor and are disclosed in [DISCLOSURE.md](DISCLOSURE.md). No research code is in this repository: all code here was written during the event, and the commit history is the evidence.
- **Since the freeze.** The code that makes and scores forecasts (`damdays/`) and the sealed-opening script (`scripts/20_open_sealed_region.py`) are unchanged since the freeze commit `c95d5db` (Fri 2 Oct, 20:21 AEST): `git diff c95d5db -- damdays/ scripts/20_open_sealed_region.py` prints nothing. Later commits added the one-time scoring of the test years (scripts/15) and the weekly texts (scripts/16 and `notify/`), and changed how results are shown or published: the app export and its unseen-exam panel (scripts/11), the Proof data (scripts/17), the track record (scripts/18), the publishing script (scripts/21), the weekly text's wording, the app and the docs.
- **A search near the sealed files.** On Sat 3 Oct at about 09:30 AEST, an AI agent ran a text search over the research folder that also holds the sealed files. It was stopped after about 2 minutes and printed no matches; no sealed contents were seen. A search does not change files, and the opening script re-checks every file's fingerprint before it reads anything ([BUILD_LOG.md](BUILD_LOG.md)).
- **The opening moved.** It was pre-registered for 17:30 AEST on Sat 3 Oct and moved to after the app build, on Sun 4 Oct (AEDT), by a dated addendum filed before the opening ([PREREG_ADDENDUM_2.md](PREREG_ADDENDUM_2.md)); the sealed data stayed unopened ([BUILD_LOG.md](BUILD_LOG.md)).
- **The demo farm changed.** Our first demo farm, near Dubbo, turned out on aerial photos to be treatment ponds, a racecourse pond, a town-edge pond and a river (Sat 3 Oct, about 15:20 AEST). It was set aside, and Farm E near Mudgee, whose 5 dams are all farm dams on the photos, became the demo farm.
- **What mentors changed.** Mentor sessions on Fri 2 and Sat 3 Oct changed the product and the story, not the model: the weekly text became the product, "%" now means only how full a dam is, chances read "N in 10", and the app gained Proof (pictures instead of scores) and each dam's own record.

### Documents

| document | what it is |
|---|---|
| [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) | How it works in plain words: one diagram, what each part adds, the final numbers |
| [docs/TARGET_FARMER.md](docs/TARGET_FARMER.md) | Who it is for, from public farm surveys, with sources |
| [docs/WHAT_EXISTS.md](docs/WHAT_EXISTS.md) | What already exists, and what is new |
| [docs/ONE_PAGER.md](docs/ONE_PAGER.md) | DamDays on one page |
| [docs/PITCH.md](docs/PITCH.md), [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md) | The submission pitch and the video script |
| [docs/DATA.md](docs/DATA.md), [docs/FEATURES.md](docs/FEATURES.md), [docs/SCORECARD.md](docs/SCORECARD.md) | The data and its cleaning, every model input, how every score is computed |
| [docs/SEALED_OPENING.md](docs/SEALED_OPENING.md) | The runbook for opening the unseen exam |
| [notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md) | The weekly text, rule by rule, with worked examples |
| [app/README.md](app/README.md), [app/DEPLOY.md](app/DEPLOY.md), [app/DATA_CONTRACT.md](app/DATA_CONTRACT.md) | The app, putting it online, and its data files |
| [BUILD_LOG.md](BUILD_LOG.md) | A timestamped record of the build |

---

## Data credits

- **DEA Waterbodies v3**, Geoscience Australia (CC BY 4.0).
- **SILO climate data**, Queensland Government (CC BY 4.0).
- In the app: street maps © OpenStreetMap contributors (ODbL), drawn with Leaflet 1.9.4 (BSD-2-Clause); type: Atkinson Hyperlegible Next, Braille Institute (SIL Open Font License).

## Disclosure

What was done before the event, the datasets, and every tool used, including the AI coding assistant and AI research agents: [DISCLOSURE.md](DISCLOSURE.md).

## Team

**Skyrend Systems**: Shaugato (team lead), Ishanee and Long.

## Licence

Copyright (c) 2026, the DamDays team. All rights reserved. The source is public so the hackathon judges can review it; no licence to reuse it is granted. The data keeps its own licences (above).
