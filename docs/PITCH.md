# DamDays: pitch and submission fields (v2)

Draft text for the Junction submission form, one section per form field, in the form's order. Copy each section into its field.

- **One audience: the farmer.** Following mentor advice (Sat 3 Oct), the pitch is for family sheep and cattle farmers, our users. Our other customers (drought support programmes and agencies, fire agencies, and farm software platforms and dam-sensor companies as partners) are named in order in section 7, "Who will use it, and who will pay". The corporate agribusiness and lender case is set aside; it is only the last, "later" line of that list.
- **Numbers** come from [`artifacts/test_results.md`](../artifacts/test_results.md) (the test years, scored once), the app's data files (`app/data/real/`, including `proof.json` for the Proof pictures and `track_record.json` for each dam's record) and [TARGET_FARMER.md](TARGET_FARMER.md) (the farmer, from public farm surveys), unless marked otherwise. The unseen exam's numbers are added after it is opened once, on camera, on Sun 4 Oct 2026 (it was pre-registered for Sat 3 Oct 2026, 17:30 AEST, and moved to after the app build).
- **The sample text** is the real one made on Fri 2 Oct 2026 for a demo farm near Mudgee, Farm E ([`outbox/2026-10-02.json`](../outbox/2026-10-02.json), `farm-e`). Its 5 dams and their forecasts are real; the homestead point is not a real one. On aerial photos all 5 are farm dams. (Until Sat 3 Oct the sample was a demo farm near Dubbo; the photo check found its waterbodies were treatment ponds, a racecourse pond, a town-edge pond and a stretch of river, so it was set aside: see [BUILD_LOG.md](../BUILD_LOG.md).)
- **Fill-ins** are in [square brackets]. Replace every one before submitting (checklist at the end).
- **Writing rules** (from mentor feedback): lead with the weekly text, because that is what farmers get. Write "we"; the team is named once, in section 5. "%" means only how full a dam is. Chances are written "3 in 10". The farmer's headline is days of water left before a dam drops below a third ("at least N days before it drops below a third"), never a count to empty. "9 in 10" is only the days-left promise, a built-in safety margin, never a hit rate. A 0% reading is "no water seen", never "dry". Counted, the waterbodies are "dam-sized waterbodies, mostly farm dams". The record on a dam is in plain words ("our days-left number held 380 of 428 times over the last 10 years"), never "backtest". The test years are "ten years it never trained on". The sealed region is "the unseen exam": a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. Say "refit" for how the model keeps up (it does not learn by itself).

---

## 1. Project name

**DamDays**

## 2. One-sentence summary

DamDays texts family sheep and cattle farmers once a week with how many days of water each of their farm dams big enough for the satellites to see (about 0.5 to 5 ha) has left, from 38 years of free satellite data, and we test its forecasts in public: on ten years it never trained on, and on a third farming region we kept aside, never opened, for one final check.

*If the field is short:* A weekly text for graziers: days of water left in each big farm dam, from satellite data.

## 3. Selected challenge and track

- **Challenge:** Build for 2035.
- **Track (COP31 priority):** Awareness Across All Areas.
- **The track's 2035 goal, word for word from the Participant Guide:** "climate-resilient farming and climate education reaching all of society by 2035".
- **How DamDays meets both halves of the track:**
  - **Farmers and land managers adapting to a changing climate.** Graziers feel drought directly, through their dams. Each week DamDays texts them how many days of water each dam has left, so they can decide while there are still choices: move stock, cart water, buy feed, agist or sell.
  - **Climate information made easy for everyone to use.** The data already exists and is free: Geoscience Australia has mapped the water surface of every visible waterbody since the 1980s. DamDays turns it into one plain line per dam, sent where farmers already look ("Dam 1 ~80% full: at least 68 days before it drops below 1/3"), instead of a map of rainfall figures.
- **Wider COP31 link.** The Global Goal on Adaptation (the UAE Framework for Global Climate Resilience) includes targets on reducing climate-driven water scarcity and on climate-resilient food and farming. DamDays measures water security dam by dam and farm by farm, and can be refreshed with every satellite pass: the kind of farm-level measure those targets need.
- **A secondary benefit (less waste, as a mentor suggested under Green Industrialisation).** Acting earlier can mean fewer stock losses, less wasted feed and better use of the water already on the farm. We have not measured these yet.

## 4. Team nationality

Australia.

## 5. Team members and roles

**Skyrend Systems: Shaugato (team lead), Ishanee and Long.** Tools, including the AI coding assistant, are listed in [DISCLOSURE.md](../DISCLOSURE.md).

## 6. Problem and target user

**Problem statement.** Family graziers whose stock drink from farm dams have no reliable way to know how many days of water each dam has left, so the decisions a drought forces (move stock, cart water, buy feed, agist or sell) rest on guesswork, and when they are left late the choices shrink.

**The problem.** In a dry spell, the question on a grazing farm is not "how full is the dam?" (you can see that) but "how long will it last?" The answer decides when to move stock, cart water, buy feed, agist or sell, and waiting usually narrows the choices. Today it is worked out by driving the water run (every day in a dry summer) and doing the sums by hand: measure the dam, look up its volume, divide by what the stock drink. Agriculture Victoria's own worked example ends at "52 days of water". The drought tools that do exist mostly look at rainfall, and rainfall cannot say which farm's dams will fail first: in our test years, a rainfall-only score picked the 2 km areas where every dam fell to ~0% full (no water seen) about as well as a coin toss.

**What exists today, and what is new.** Farmers can measure a dam and do the sums by hand (the state agriculture departments teach the method); trough and tank sensors report water at one water point each (about $545 a device plus a monthly fee, in an Agriculture Victoria case study), not how long a dam will last; and drought tools mostly map rainfall. Forecasting stock water is not new in itself: Victoria's Small Farm Dams pilot forecasts one dam that the farmer draws and measures, and USGS FEWS NET forecasts waterholes in Africa. What DamDays adds is a forecast of days of water for each farm dam the satellites can see (about 0.5 to 5 ha), with nothing to install or measure, a track record on every dam, and its accuracy tested in public against pass marks written before the build began. The full comparison is in [WHAT_EXISTS.md](WHAT_EXISTS.md).

**Right now.** At the latest satellite looks (to 14 September 2026), 272 of the 894 dam-sized waterbodies we track in NSW Central West (mostly farm dams) were already below a third full: the most for a September since the 2019 drought.

**Who it is for: one farmer.** *DamDays is for family sheep and cattle farms, mostly 300 to 1,500 ha in south-eastern Australia's dam country, run by one or two people, whose stock drink from at least one dam big enough for the satellites to see.* The profile below uses ABARES farm-survey averages for 2022-23 to 2024-25 and our own data; every source is in [TARGET_FARMER.md](TARGET_FARMER.md).

| | the target farmer |
|---|---|
| **Enterprise** | A family beef, sheep or mixed sheep-and-cattle farm whose stock drink from farm dams. More than 95 in 100 broadacre and dairy farms are family owned and operated |
| **Where** | Dam-watered grazing country where DamDays has been tested: NSW Central West (slopes and central tablelands), western Victoria, south-east South Australia |
| **Land** | Most often about 300 to 1,500 ha (NSW averages run higher because they include big western properties) |
| **Stock** | Beef farms 263 to 408 cattle; sheep farms 1,603 to 3,135 sheep; mixed farms 249 to 431 cattle plus 1,711 to 2,931 sheep |
| **Turnover** | About $250,000 to $800,000 a year in cash receipts: mostly ABARES's "medium" group, roughly the top third of southern beef farms |
| **Who does the work** | The family: 63 to 107 work weeks a year in all (about 1.2 to 2 people full time), little hired labour; owner-manager aged 57 to 69 |
| **Remoteness** | Mostly Outer Regional Australia: of the 1,683 dams DamDays forecasts, 1,101 are Outer Regional, 397 Inner Regional and 185 Remote (ABS remoteness areas) |
| **Water DamDays can see** | At least one dam of 0.54 to 4.95 ha; usually 1 or 2 per farm. The average farm dam (about 0.27 ha) is too small, so this is the hard filter |
| **When a dam fails** | Cart water (a daily, labour-heavy job), buy fodder, agist or sell. In the 2019-20 drought, NSW sheep-beef farms spent $113,970 each on fodder, against $10,160 to $19,690 in recent years |
| **How to reach them** | One text a week, not an app or an email |

An illustrative family built from these numbers ("Meet Kath and Graeme", clearly made up) is in [TARGET_FARMER.md](TARGET_FARMER.md). **Not the target (yet):** bore-watered western Queensland, irrigators, hobby blocks whose dams are too small to see, large pastoral stations further west, and corporate agribusiness.

**One honest limit of the fit.** About 1 in 11 points across each test region has a dam DamDays can see within 2 km. The app's 9 demo farms sit on the densest clusters (5 to 30 such dams within 3 km; Farm E has 5), so they show the text at its best; a typical target farm will see 1 or 2 of its dams in the text. Dense clusters also attract waterbodies that are not farm dams, so we checked the demo farms against aerial photos: the Dubbo farm we first used was treatment ponds, a racecourse pond, a town-edge pond and a stretch of river, and was set aside; Farm E's 5 dams are all farm dams.

**What we learned from talking to people.** We showed DamDays to four mentors in four sessions (one on Fri 2 Oct in the evening, three on Sat 3 Oct between about 08:30 and 12:00 AEST). Each point changed what we built:
- **The need is real.** Mentors confirmed that in a drought, knowing how long the water will last matters.
- **Farmers don't open apps or emails; a weekly text is what they'd use.** So the weekly text became the product, and the app became the place to set up a farm and look closer.
- **"%" reads as how full.** So in DamDays "%" means only how full a dam is, chances are written "6 in 10", and days left is the headline.
- **Explain the testing plainly, with pictures.** We were asked to show accuracy on data the model was not trained on, as recent as possible; how it keeps up as the climate shifts; and that it works dam by dam, as pictures rather than scores. So we built the app's **Proof** view, and "sealed region" became "the unseen exam", described in plain words.
- **Pick one audience, and describe them precisely.** So the pitch is for one farmer, described from public farm surveys ([TARGET_FARMER.md](TARGET_FARMER.md)), and the corporate agribusiness case is set aside.
- **Say the problem in one sentence, name the COP31 priority and the farms, show what already exists and what is new, and let farmers judge the accuracy.** So we wrote a one-page brief ([ONE_PAGER.md](ONE_PAGER.md)), checked what already exists ([WHAT_EXISTS.md](WHAT_EXISTS.md)), and added our record to every dam's card.
- **Not every point was supportive.** One mentor doubted DamDays is different enough from dam sensors and existing apps, and thought the saving for one farm may be small. That is why [WHAT_EXISTS.md](WHAT_EXISTS.md) compares them side by side, and why the impact is marked "not yet measured".
- **Who else uses dams, and did we rule them out before choosing graziers?** So we checked the other users of dam water and now name our customers in order (section 7): farmers first, then drought support programmes and agencies, fire agencies, and farm software platforms and dam-sensor companies as partners.
- **How can a satellite tell how much water is in a dam when dams differ in depth?** Answered plainly in the app's **Questions** page, with the other questions we were asked (why not a dam sensor, which farms, Australia only?).

## 7. Solution and intended impact

**What farmers get: one text a week.** For each farm, one SMS: the dams that matter most, how full each one is, and how many days of water it has before it drops below a third, counted from the day of the text. This is the real text made on Fri 2 Oct 2026 for a demo farm near Mudgee (Farm E: 5 dams the satellites can see within 3 km of the homestead):

```
Fri 2 Oct (dams seen 13 Sep)
Dam 1 ~80% full: at least 68 days before it drops below 1/3
Dam 3: no water seen
Other 2 dams: 3 months+
Reply MAP for 1 more dam
```

- **Dam 1** is the dam closest to the homestead.
- **"~80% full"** is the share of the dam's usual full water surface that the satellite sees wet at its last clear look, not its depth or volume. Dams differ in size and depth, so each is measured against its own usual full surface.
- **"At least 68 days"** is cautious by design: it is built so the dam stays above a third at least that long 9 times in 10, and across all dams on ten test years it did (900 in every 1,000 forecasts; a little less often for spring looks). That is a safety margin, not a hit rate. The app gives Dam 1's chance of being below a third by 12 Dec as 1 in 10, so it will most likely last longer than 68 days.
- **"No water seen"** (Dam 3): the satellite saw no water at its last clear look. One look can be wrong (a small pool, or muddy or green water, can be missed), so the text says what was seen and never calls a dam dry.
- **"Other 2 dams: 3 months+"** are Dams 5 and 2. **"Reply MAP for 1 more dam"** is Dam 4 (~33% full, no forecast until it refills to 60% full), which the longer app/email version names.
- **"A third"** is DamDays's early-warning line, well before a dam is empty.
- **"Dams seen 13 Sep."** The first line names the day of the text and the date of the satellites' last clear look at the farm's dams; the days are counted from the day of the text. Clear looks come every week or two when there is no cloud, and this build's data runs to 14 Sep 2026.
- **One SMS** (160 places, plain characters only). This week's texts for 9 demo farms in two regions are in [`outbox/2026-10-02.json`](../outbox/2026-10-02.json); the rules, with 10 worked examples, are in [`notify/MESSAGE_SPEC.md`](../notify/MESSAGE_SPEC.md). Nothing is sent unless someone runs the sender with their own SMS account's keys, and the MAP and STOP replies are not built yet.

**The rest of what we built** (working now: the app is live at [shaugato.github.io/damdays/app](https://shaugato.github.io/damdays/app/); the code is at [github.com/Shaugato/damdays](https://github.com/Shaugato/damdays), where the app also opens from `app/index.html`):
- **On a phone, a clean app; on a computer, a short story** of what DamDays is and how a farmer sees it, with the real text in a phone frame. Four tabs: My farm, Proof, Questions and More.
- **Questions, in plain words.** The questions mentors and judges asked, each with a short answer, the numbers and where to check them: the problem in one sentence, which farms, Australia only, how a satellite can tell how much water is in a dam when dams differ in size and depth, why not a dam sensor, what already exists and what is new, who our customers are and who pays, and how a farmer can judge the accuracy.
- **My farm, for a closer look.** Pick a demo farm, or click your homestead on the map and set the circle size, and see your dams (Dam 1 is the closest) and this week's text on a phone, made in the browser by the same rules as the real texts, with its longer version. For each dam, a card: how full, the days, the chance of falling below a third by each date ("1 in 10 by 12 Dec"), the next six months with the DamDays day marked and how far a wetter or drier season could move it, how full it has been since 1988, what its own history says about it (Farm E's Dam 5: "Runs wetter than similar dams"), and our record on it, season by season.
- **Proof, for trust.** Pictures of the ten test years, for anyone who does not read statistics: what we said against what happened; how it held up year after year; and one farm's dams through the 2018-19 drought. The unseen exam's result appears at the top once it is opened.
- **Rewind: the 2018-19 drought** (inside Proof). Go back to a date in the drought, see the forecasts as they were made that day, then reveal what happened and the tally.
- **Runway, the map of the region** (under More): every dam-sized waterbody DamDays tracks in NSW Central West, coloured by its chance of dropping below a third within 90 days, with the highest chances listed.
- **The engine** learns how each dam behaves (how fast it drops in summer, how it refills after rain, whether it runs drier or wetter than similar dams) from the satellite record (DEA Waterbodies, Geoscience Australia, 1988 to 2026) and rainfall (SILO, Queensland Government). The whole pipeline runs on a laptop.

**How we know it works: three proofs.** We wrote the exam before the build began: the pass marks and the test years were committed at 09:12 on the first morning and pushed to GitHub at 09:15 ([PREREG.md](../PREREG.md)).

1. **What we said vs what happened (accuracy, up to June 2026).** On ten years the model never trained on (it learned only from data before July 2016), up to June 2026, 142,938 forecasts were scored once; 29,415 were followed by a fall below a third within 90 days. Grouped by the chance they gave, what happened matched what was said in all 10 groups, to the nearest 1 in 10: of the 17,013 forecasts that said "3 in 10", 4,864 fell. Overall the forecasts had nearly a quarter less error than guessing the usual rate for the region and month (the scores, for specialists, are in the evidence table below). Shown one dam that fell below a third and one that did not, they gave the right one the higher chance 8 times in 10. These years were looked at before the event, so they may flatter the model slightly; the unseen exam is the clean test. (In the app: Proof, part 1.)
2. **It held up as conditions changed (adaptability).** Frozen with data to mid-2016, the model had less error than the usual guess in every one of the next ten years: from a fifth less (2020-21) to a quarter less (2025-26), through the drier years of 2017-20 and 2023-26 and the wet years between. The "at least N days" promise held 872 to 927 times in 1,000 each year; it fell short of its 880 mark once, in 2023-24 (872). The weather did move it, and we show where: in the wet years its chances ran high (2020-21: an average chance of 223 in 1,000, and 138 in 1,000 fell; 2021-22: 191 against 152), and in some dry years a little low (2017-18: 233 against 261; 2025-26: 229 against 262). That is why it is refit rather than frozen in use. (In the app: Proof, part 2.)
   - **Built:** each dam's own correction keeps updating as each forecast's answer comes in ([`damdays/models/frailty.py`](../damdays/models/frailty.py)); today's forecasts come from a refit on every answer known by the last satellite look (14 Sep 2026; [`damdays/export/live_model.py`](../damdays/export/live_model.py), one command); and the water-balance outlook replays the rain of the previous 20 years, so it moves with the recent climate.
   - **A farmer can judge it on their own dam (built):** every dam's card shows our record on that dam over the last 10 years. We re-ran our forecasts for July 2016 to June 2026 using only data from before July 2016, then checked each one against what the dam really did. On Farm E's Dam 1 our days-left number "held 380 of 428 times"; over the farm's 5 dams, 1,640 of 1,767 (about 9 in 10). The typical dam held 912 times in 1,000; weak records are shown as they are ([artifacts/track_record.md](../artifacts/track_record.md)).
   - **Not built yet:** automatic weekly refits and a seasonal check of said-against-happened that would flag drift. Today the refit is run by hand. The model does not learn by itself.
3. **The unseen exam.** A third farming region (Southern Downs, Granite Belt, New England: 4,711 waterbodies) whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. Its fingerprints were committed at 09:12 AEST on Fri 2 Oct and pushed to GitHub at 09:15, and it was opened once, on camera, on Sun 4 Oct 2026, 09:20 to 10:16 AEDT (pre-registered for Sat 3 Oct, 17:30 AEST; moved to after the app build by a dated addendum, [PREREG_ADDENDUM_2.md](../PREREG_ADDENDUM_2.md); recording, sped up: [docs/media/unseen_exam_opening_x30.mp4](media/unseen_exam_opening_x30.mp4)). It covers forecasts from July 2016 to June 2026, made by models fitted on the other two regions before July 2016 (the region's own history before July 2016 sets only its local averages). Its score was published as it came out. <!-- SEALED:START sentence -->DamDays met all 4 pass marks we wrote before the build began: nearly a fifth less error than guessing the usual rate, and the Area outlook picked the right 2 km patch 8 times in 10, against 5 in 10 for rainfall alone.<!-- SEALED:END -->

**Dam by dam.** Every dam gets its own forecast and its own correction: Farm E's Dam 5 card says it "runs wetter than similar dams: it fell below a third less often than the model expected", so its chance is nudged down. On Farm E, across the three Rewind dates in the 2018-19 drought, its dams got 9 forecasts whose chances added up to about 2 falls below a third within 90 days, and 2 happened (Dam 1 after 1 Nov 2018, Dam 3 after 1 Jan 2019). A replay shows the same at scale: on three dates in the 2018-19 drought (1 Nov 2018, 1 Jan 2019, 1 Mar 2019), 782 forecasts for 366 dams in NSW Central West expected about 248 to come true, and 244 did (186 different dams fell below a third). Date by date it was less exact: about 95 expected and 76 fell on 1 Nov 2018, about 97 and 106 on 1 Jan 2019, about 57 and 62 on 1 Mar 2019. One limit: the model is better at saying which dams will fall this summer than at timing a single dam's next dry year.

**Intended impact by 2035.**
- Farmers get each dam's days of water in a weekly text, and act earlier, while there are more choices: fewer stock losses and less wasted feed are the aim (not yet measured).
- It can scale on public data: the same satellite record covers all of Australia, and the pipeline runs on a laptop. So far it has been tested only in south-eastern Australia; each new climate needs its own test.
- Australia first. Landsat, the satellite behind the record, covers the whole world, so farm dams in other countries are a later path; each would need its own waterbody record and its own test.

**Next.**
- **A real text service:** farmers opt in when they set up their farm; the MAP and STOP replies; a sender name (Australia's Spam Act 2003 asks commercial messages to name the sender and offer a working unsubscribe). Sending through an SMS provider is built, but it only ever runs with your own account's keys.
- **Keeping up automatically:** a weekly refit on the newest satellite looks, and a seasonal check of what it said against what happened, so drift shows early.
- **Fitting the farm:** set-up that shrinks the 3 km circle to the farm's own dams (most target farms are smaller than the circle's 2,827 ha); more regions; trials with farmers of how they act on the number.
- **Talking to customers:** farmers and two drought programmes first (the list below).

**Who will use it, and who will pay.** Our customers, in order:

1. **Farmers:** family sheep and cattle graziers whose stock drink from dams. They are the users, and they come first, as a mentor advised.
2. **Drought support programmes and agencies,** such as state drought teams and Local Land Services, Future Drought Fund programmes, regional drought resilience groups, and farm advisers who look after many farms. They could provide DamDays to the farmers in their region, and use the district view (Runway, in the app) to see where stock water runs short first.
3. **Fire agencies:** to know before fire season which farm dams crews and aircraft can still refill from.
4. **Farm software platforms and dam-sensor companies, as partners:** a sensor shows the level now; adding our forecast completes it.
5. **Later, rural lenders and insurers,** set aside for now on mentor advice. We built a season-ahead rating with lenders in mind, and it was one of our pre-registered tests, but it is not part of this pitch.

We have not set prices or approached these customers yet; the next step is to talk to farmers and two drought programmes.

## 8. Written pitch (about 510 words with the text)

Friday morning, a farmer's phone buzzes:

> Fri 2 Oct (dams seen 13 Sep)
> Dam 1 ~80% full: at least 68 days before it drops below 1/3
> Dam 3: no water seen
> Other 2 dams: 3 months+
> Reply MAP for 1 more dam

That's DamDays: one text a week, with the days of water each of the farm's dams has left. (The farm is a demo near Mudgee, but its five dams and their forecasts are real.)

It's for the family sheep and cattle farm in south-eastern Australia's dam country: mostly 300 to 1,500 hectares, a few hundred cattle or a few thousand sheep, one or two people doing the work, and stock that drink from dams. Anyone can see how full a dam is. How long it will last is the hard question, and today it's worked out by driving the water run and doing sums by hand. It decides when to move stock, cart water, buy feed, agist or sell; leave it late and the choices shrink. At the latest satellite looks, to 14 September 2026, 272 of the 894 dam-sized waterbodies we track in NSW Central West, mostly farm dams, were already below a third full: the most for a September since 2019.

Satellites have mapped every visible Australian waterbody since the 1980s, and Geoscience Australia publishes the record free. DamDays reads each dam's history with the rainfall and learns how it behaves: how fast it drops in summer, how it refills, whether it runs drier or wetter than similar dams. The text gives each dam's cautious days, built to hold 9 times in 10; the app adds the chance ("1 in 10 by 12 December" for Dam 1), the next six months, and our record on each dam. Farmers rarely open apps or emails, a mentor told us, but they do read a weekly text.

Why trust the number? Three pictures. **What we said vs what happened:** over ten years the model never trained on, up to June 2026, when it said 3 in 10, the dam fell below a third about 3 times in 10, and so at every level, with nearly a quarter less error than guessing the usual rate. **Year after year:** it beat the usual guess in every one of those years, dry and wet; where the weather pushed its chances too high or too low, we show it, and today's forecasts are refit on the newest satellite looks, with each dam corrected by its own record. **The unseen exam:** a third farming region whose satellite data we downloaded and fingerprinted before the event, then never opened or used, covering forecasts to June 2026, opened once, on camera. [After the opening: copy beat 8's sealed-result line from VIDEO_SCRIPT.md here.]

That's COP31's Awareness track in practice: helping farmers adapt, with climate information they can act on, aiming for fewer stock losses and less wasted feed and water. By 2035, every farm dam big enough for the satellites to see (about 0.5 to 5 ha) could text its farmer before it gets low.

## 9. Evidence at a glance (for "Any supporting material"; the numbers, for specialists)

| claim | number | where to check |
|---|---|---|
| The weekly text fits one SMS | all 9 demo farms' texts this week: 147 to 160 of 160 places; 66 tests check every rule | [outbox/2026-10-02.json](../outbox/2026-10-02.json), [tests/test_weekly_text.py](../tests/test_weekly_text.py), [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md) |
| What we said vs what happened | ten test years, 142,938 forecasts, 29,415 fell below a third; all 10 groups matched to the nearest 1 in 10; "3 in 10": 4,864 of 17,013 fell | the app's Proof view, part 1; `app/data/real/proof.json`, `calibration` |
| Below-a-third forecasts beat the usual rate for the region and month | skill +0.235 (range +0.224 to +0.248): "nearly a quarter less error" | [artifacts/test_results.md](../artifacts/test_results.md) |
| ... in every one of the ten years | skill +0.210 (2020-21, lowest) to +0.281 (2025-26, highest) | the app's Proof view, part 2; `proof.json`, `by_year` |
| ... and beat each dam's own track record | skill +0.155 | [artifacts/test_results.md](../artifacts/test_results.md) |
| ... and our own strong benchmark on the same forecasts | +0.014 (range +0.011 to +0.018) | same |
| Ranking: a dam that fell gets the higher chance | 8 times in 10 (AUC 0.818; a coin toss is 0.5) | same |
| Chances about right | calibration slope 1.09 (pass mark 0.8 to 1.2): a little cautious, low chances could be lower and high ones higher | same; `proof.json`, `calibration.lean` |
| "At least N days" promise | held for 0.900 of 729,749 forecasts (target 0.90; median N 60 days); by year 872 to 927 in 1,000, short of the 880 mark only in 2023-24 | same, "DamDays floor" |
| Where the weather moved it | wet years ran high (2020-21: average chance 0.223, 0.138 fell); some dry years a little low (2025-26: 0.229, 0.262 fell) | `proof.json`, `by_year.years[]`: `mean_chance`, `share_fell` |
| Today's forecasts are refit | on every answer known by the last satellite look (looks up to 14 Sep 2026; the data's cutoff, 15 Sep 2026, is the first day left out) | `app/data/real/meta.json`, `live`; [damdays/export/live_model.py](../damdays/export/live_model.py) |
| Our record on the demo farm's own dams | over the last 10 years our days-left number held 1,640 of 1,767 times on Farm E's 5 dams (about 9 in 10); Dam 1, 380 of 428; the typical dam 912 times in 1,000 (929 dams with a record); 101 dams below 8 in 10, shown as they are | the app's dam cards; `app/data/real/track_record.json`; [artifacts/track_record.md](../artifacts/track_record.md) |
| The demo farm's dams are farm dams | Farm E: 5 of 5 on aerial photos; the Dubbo demo farm set aside (treatment ponds, a racecourse pond, a town-edge pond, a stretch of river) | `app/data/real/farms.json`, `set_aside`; [BUILD_LOG.md](../BUILD_LOG.md), Sat ~15:20 |
| The 2018-19 drought, replayed | 782 forecasts for 366 dams on 3 dates: about 248 expected to fall below a third, 244 did (186 different dams); by date, expected and fell: 1 Nov 2018 about 95 and 76; 1 Jan 2019 about 97 and 106; 1 Mar 2019 about 57 and 62. On Farm E: 9 forecasts, about 2 falls expected, 2 happened | the app's Rewind view (inside Proof); `app/data/real/meta.json`, `rewind.tallies`; dams counted from `app/data/real/forecasts.json`; Farm E: `proof.json`, `dam_by_dam.all_dates_takeaway` |
| Pass marks written before the build began | committed Fri 2 Oct 2026, 09:12 AEST; pushed 09:15 | [PREREG.md](../PREREG.md) and its commit (e0e9b0b) on GitHub |
| Model frozen before it was scored on the test years | Fri 2 Oct 2026, 20:21 AEST, code fingerprint 7d466291008d | [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md) |
| The fourth pre-registered pass mark (a season-ahead rating, not part of this pitch) | ranking accuracy 0.81 against 0.53 for rainfall alone; gain +0.285 (mark +0.05): PASS | [artifacts/test_results.md](../artifacts/test_results.md), P2 |
| The unseen exam | <!-- SEALED:START evidence -->4 of 4 pass marks met; below-a-third skill +0.183 (range +0.171 to +0.197); gain over G2 +0.012; Area outlook 0.81 against rainfall-only 0.54<!-- SEALED:END --> | `artifacts/sealed/SEALED_RESULTS.md` (after the opening) |

<!-- SEALED:START -->
**The unseen exam in numbers** (the sealed region, scored once on Sun 4 Oct 2026, 10:16 AEDT; from `artifacts/sealed/SEALED_RESULTS.md`): **All 4 pre-registered pass marks met.**

- Below-a-third forecasts: nearly a fifth less error than guessing the usual rate (skill +0.183, range +0.171 to +0.197; we expected +0.15 to +0.23).
- Against our own benchmark model G2, on the same forecasts: ahead by +0.012 (range +0.008 to +0.014; we expected +0.01 to +0.03).
- "At least N days" held 882 times in 1,000 (target 900).
- Area outlook (the pre-registered lender rating): the right 2 km patch 8 times in 10, rainfall alone 5 in 10 (gain +0.269; mark +0.05; kill rule not triggered).
- Pass marks: beating the usual rate PASS; beating each dam's own record PASS; calibration PASS; Area outlook PASS.
- 6 of 6 results came out inside the ranges we declared before opening.

<!-- SEALED:END -->

`scripts/21_publish_sealed.py` reports every pre-registered pass mark here and in section 7, including the season rating's. Keep them all, as promised, even though the pitch is about farmers.

One honest note for judges: the test years informed a few design choices, so they may flatter the model slightly; the unseen exam is the clean test. Details: [artifacts/test_results.md](../artifacts/test_results.md) (top of the page) and [DISCLOSURE.md](../DISCLOSURE.md).

## 10. Links

- Repository: https://github.com/Shaugato/damdays
- App: https://shaugato.github.io/damdays/app/ (live on GitHub Pages; it also opens from `app/index.html` in the repository)
- One page: [docs/ONE_PAGER.md](ONE_PAGER.md)
- What already exists, and what is new: [docs/WHAT_EXISTS.md](WHAT_EXISTS.md)
- Demo video: [link]
- The target farmer, with sources: [docs/TARGET_FARMER.md](TARGET_FARMER.md)
- The weekly text, line by line: [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)
- Plain-language explainer: [docs/HOW_IT_WORKS.md](HOW_IT_WORKS.md)

## 11. Tools used and disclosures

See [DISCLOSURE.md](../DISCLOSURE.md): datasets (DEA Waterbodies v3, Geoscience Australia; SILO, Queensland Government; both CC BY 4.0), Python libraries, front-end libraries (Leaflet, OpenStreetMap tiles) and AI tools (Claude Code during the event; Claude research agents before it). The video's voice-over is AI-generated. The farmer profile draws on public sources listed in [TARGET_FARMER.md](TARGET_FARMER.md) (ABARES, ABS, MLA, Agriculture Victoria, NSW DPI).

---

## Before submitting: checklist

- [ ] Replace every [square bracket] in sections 3 to 11, including section 8's sealed-result line (copy beat 8's line from [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) after scripts/21 has written it).
- [ ] Sealed result: one honest sentence, whichever way it went (templates in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "The sealed-result line"). Read section 7's and section 9's sealed text against `artifacts/sealed/SEALED_RESULTS.md`.
- [ ] The app's Proof view shows what section 7 says (ten dots near the diagonal; ten bars above zero; the "Unseen exam" card filled after the opening). The app was redesigned on Sun 4 Oct (07:27 AEDT), so check it again in the browser at https://shaugato.github.io/damdays/app/ (hard reload).
- [ ] The app writes chances as "N in 10", as sections 7 and 8 say: the dam card, the map tips, Rewind's tables and the About page. A 0% dam reads "no water seen", never "dry".
- [ ] The sample text matches `outbox/2026-10-02.json` (`farm-e`) word for word, first line "Fri 2 Oct (dams seen 13 Sep)". If the texts are made again, use `--date 2026-10-02`, or update the text and its numbers everywhere.
- [ ] No Farm D (near Dubbo) anywhere as an example: it was set aside after the aerial-photo check.
- [ ] Re-check the live fact (272 of 894) if the app data is exported again (command in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "Where each number comes from").
- [ ] No lender, bank or agribusiness case beyond the one "Later" line of section 7's customer list and the pass-mark reporting: the row in section 9, and the sealed results scripts/21 writes into sections 7 and 9 (they name every pre-registered mark, the season rating's included; keep them as written).
- [ ] "What we learned from talking to people": no names, and nothing that identifies any mentor.
- [ ] "We" everywhere; the team is named once, in section 5 (first names only; no emails or Discord handles anywhere in the repository).
- [ ] Track wording: check it against the Junction form. If the form words the goal differently from the Participant Guide, use the form's words.
- [ ] Every link opens without asking for access (the Participant Guide's quality check).
- [ ] No DamDays pricing. Customers are named by kind (section 7's list), with agencies only as examples of a kind ("such as state drought teams"), never as committed buyers; no claim of interest, pilots, letters or revenue. The repository is public. (Other tools, with their public prices, are named in WHAT_EXISTS.md on purpose: a mentor asked what already exists.)
- [ ] [DISCLOSURE.md](../DISCLOSURE.md): its team line matches section 5; fill in the screenshot link and the video tool.
