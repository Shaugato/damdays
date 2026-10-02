# DamDays: pitch and submission fields (draft)

Draft text for the Junction submission form, one section per form field, in the form's order. Copy each section into its field.

- **Numbers** come from [`artifacts/test_results.md`](../artifacts/test_results.md) (the test years, scored once) and the app's data files, unless marked otherwise. The sealed region's numbers are added after it is opened on Sat 3 Oct 2026, 17:30 AEST.
- **The sample text** is the real one made on Fri 2 Oct 2026 for a demo farm near Dubbo ([`outbox/2026-10-02.json`](../outbox/2026-10-02.json), `farm-d`). Its 7 dams and their forecasts are real; the homestead point is not a real one.
- **Fill-ins** are in [square brackets]. Replace every one before submitting (checklist at the end).
- **Writing rules** (from mentor feedback): lead with the weekly text, because that is what farmers get. "%" means only how full a dam is. Chances are written "3 in 10". The farmer's headline is days of water left. Say "the unseen exam", not statistics terms.

---

## 1. Project name

**DamDays**

## 2. One-sentence summary

DamDays writes each farm one text a week saying how many days of water each farm dam has left, from 38 years of free satellite data, and tests its forecasts on years and a region the model never saw.

*If the field is short:* A weekly text: days of water left in each farm dam, from satellite data.

## 3. Selected challenge and track

- **Challenge:** Build for 2035.
- **Track (COP31 priority):** Awareness Across All Areas.
- **The track's 2035 goal, word for word from the Participant Guide:** "climate-resilient farming and climate education reaching all of society by 2035".
- **How DamDays meets both halves of the track:**
  - **Farmers and land managers adapting to a changing climate.** Graziers feel drought directly, through their dams. Each week DamDays texts them how many days of water each dam has left, so they can decide while there are still choices: cart water, move or sell stock, or fix a leaking dam.
  - **Climate information made easy for everyone to use.** The data already exists and is free: Geoscience Australia has mapped the water surface of every visible waterbody since the 1980s. DamDays turns it into one plain line per dam, sent where farmers already look ("Dam 2 ~67% full: at least 29 days before it drops below 1/3"), instead of a map of rainfall figures.
- **Wider COP31 link.** The Global Goal on Adaptation (the UAE Framework for Global Climate Resilience) includes targets on reducing climate-driven water scarcity and on climate-resilient food and farming. DamDays measures water security farm by farm, and can be refreshed with every satellite pass: the kind of measure those targets need.

## 4. Team nationality

[Australia: confirm on the form.]

## 5. Team members and roles

[Copy from [DISCLOSURE.md](../DISCLOSURE.md), "Team", once the names are filled in.] Shaugato Paroi built DamDays end to end (data, models, weekly text, app, validation).

## 6. Problem and target users

**The problem.** In a dry spell, the question on a grazing farm is not "how full is the dam?" (you can see that) but "how long will it last?" The answer decides when to cart water, move stock to agistment, sell, or fix a dam, and waiting usually narrows the choices. Today that call is made by eye and memory. The drought tools that do exist mostly look at rainfall, and rainfall cannot say which farm's dam will fail first: in our test years, a rainfall-only score picked the farms whose dams ran dry about as well as a coin toss.

**Right now.** At the latest satellite looks (to 14 September 2026), 272 of the 894 farm dams we track in NSW Central West were already below a third full: the most for a September since the 2019 drought.

**Target users.**
- **Primary: livestock and mixed farmers** who rely on farm dams for stock water, starting in south-eastern Australia's grazing country. They need one plain number, sent where they already look: a text message.
- **Secondary: rural lenders, valuers and drought-support workers**, who need to know which properties are exposed before a season starts. Today they see rainfall, not the water a farm actually holds.

**What we learned from talking to people.** During the event we showed DamDays to a mentor who grew up on farms. Each point changed what we built:
- **The need is real.** They told us that in a drought, knowing how long the water will last would be "super useful".
- **Farmers don't open apps or emails; a weekly text is what they'd use.** So the weekly text became the product. The app became the place to set up a farm and look closer.
- **"%" reads as how full.** The mentor read a percent as how full a dam is, not as a chance. So in DamDays "%" means only how full a dam is, and chances are written "6 in 10". How full says how much water there is; days left says what that means, so days are the headline.
- **The proof needed plainer words.** Our first explanation of the locked region was too technical. Now it is "the unseen exam", shown next to a replay of the 2018-19 drought.

## 7. Solution and intended impact

**What farmers get: one text a week.** For each farm, one SMS: the dams that matter most, how full each one is, and how many days of water it has before it drops below a third, counted from the day of the text. This is the real text made on Fri 2 Oct 2026 for a demo farm near Dubbo (7 farm dams within 3 km of the homestead):

```
Fri 2 Oct (satellite 13 Sep)
Dam 2 ~67% full: at least 29 days before it drops below 1/3
Dam 1 looks dry
Other 5 dams: at least 52 days
Reply MAP
```

Dam 1 is the dam closest to the homestead. The days are cautious: on ten test years, a dam stayed above a third at least that long 9 times in 10. Each text fits one SMS (160 places, plain characters only). This week's texts for 10 demo farms in two regions are in [`outbox/2026-10-02.json`](../outbox/2026-10-02.json); the rules, with 10 worked examples, are in [`notify/MESSAGE_SPEC.md`](../notify/MESSAGE_SPEC.md).

**The rest of what we built** (working now: [github.com/Shaugato/damdays](https://github.com/Shaugato/damdays); the app opens from `app/index.html`):
- **The app, for a closer look.** It opens on **My farm**: click your homestead on the map, and see your dams (Dam 1 is the closest) and this week's text on a phone, made in the browser by the same rules as the real texts. For each dam, a card: the days, the chance of falling below a third in the next 90 days (written "3 in 10"), and a curve out to six months that shows how far a wetter or drier season could move it.
- **Rewind, for trust.** Go back to a past season, see the forecasts as they were made that day, then reveal what really happened.
- **DamDays Rating, for lenders.** Each 1 July, the chance that the dams in each 2 km patch of farmland all run dry before the end of March, shown side by side with a rainfall-only score.
- **The engine** learns how each dam behaves (how fast it drops in summer, how it refills after rain, whether it runs drier than its neighbours) from 38 years of satellite looks (DEA Waterbodies, Geoscience Australia) and rainfall (SILO, Queensland Government).

**How we know it works.** We wrote the exam before the code: the pass marks and the test years were committed at 09:12 on the first morning and pushed to the public repository three minutes later ([PREREG.md](../PREREG.md)).
- **The unseen exam.** We locked away a whole farming region's satellite data (Southern Downs, Granite Belt, New England: 4,711 waterbodies), published its fingerprint at the start, and opened it once, on camera, on Sat 3 Oct 17:30 AEST. Whatever score came out, we published it. <!-- SEALED:START sentence -->[Sealed result, one sentence: opens Sat 3 Oct 17:30 AEST.]<!-- SEALED:END -->
- **The 2018-19 drought, replayed.** Forecasts made on 1 Nov 2018, 1 Jan 2019 and 1 Mar 2019 for farm dams in NSW Central West, by a model that learned only from data before July 2016. Across 782 forecasts they expected about 248 dams to fall below a third within 90 days; 244 did. Date by date it was less exact: on 1 Nov 2018 they expected about 95 and 76 fell (too high); on 1 Jan 2019, about 97 and 106 fell; on 1 Mar 2019, about 57 and 62 fell. (In the app: Rewind.)
- **Ten years the model never trained on** (July 2016 to June 2026), scored once: the "at least N days" promise held 9 times in 10 across 729,749 forecasts; the forecasts had nearly a quarter less error than "the usual rate for this region and month"; and shown one dam that fell below a third and one that did not, they gave the right one the higher chance 8 times in 10. Every pass mark met. (These years were also looked at before the event, so they may flatter the model slightly; the unseen exam is the clean test.)
- **The lender rating**, shown one 2 km patch of farmland whose dams all ran dry and one whose dams did not, picked the right one 8 times in 10; rainfall alone did little better than a coin toss.

**Intended impact by 2035.**
- Farmers get each dam's days of water in a weekly text, and can act earlier, while there are more choices.
- Lenders and valuers can measure drought exposure property by property, from the water a farm actually holds. Because the rating follows each dam's own record, improvements to a farm's water supply show up as that record builds.
- It can scale on public data: the same satellite record covers all of Australia, and the whole pipeline runs on a laptop. So far it has been tested only in south-eastern Australia; each new climate needs its own test.

**Next.** What a real text service still needs: farmers opting in when they set up their farm, the MAP and STOP replies, and a sender name (Australia's Spam Act 2003 asks commercial messages to name the sender and offer a working unsubscribe). Sending through an SMS provider is already built, but it only ever runs with your own account's keys. Then more regions, and trials with farmers of how they act on the number.

## 8. Written pitch (about 470 words with the text and the sealed sentence)

Friday morning near Dubbo, a grazier's phone buzzes:

> Fri 2 Oct (satellite 13 Sep)
> Dam 2 ~67% full: at least 29 days before it drops below 1/3
> Dam 1 looks dry
> Other 5 dams: at least 52 days
> Reply MAP

That's DamDays: one text a week, with the days of water each farm dam has left. (The farm is a demo, but its seven dams and their forecasts are real.)

Any grazier can see how full a dam is. How long it will last is the hard question, and it decides when to cart water, move stock, sell, or fix a leaking dam. Leave it late and the choices shrink. At the latest satellite looks, to 14 September 2026, 272 of the 894 farm dams we track in NSW Central West were already below a third full: the most for a September since the 2019 drought.

Satellites have mapped the water in every visible Australian waterbody since the 1980s, and Geoscience Australia publishes the record free. DamDays reads 38 years of it per dam and learns how each one behaves: how fast it drops in summer, how it refills after rain, whether it runs drier than its neighbours. The text gives each dam's cautious days of water; the app adds the chance (written "3 in 10") and a six-month runway.

We built it around what a mentor who grew up on farms told us: farmers don't open apps or emails, but they read a weekly text. And a percent reads as how full, so in DamDays that is all "%" ever means.

Why trust the number? We set it an unseen exam: a whole farming region's satellite data, locked away with a published fingerprint at the start and opened once, on camera. <!-- SEALED:START sentence -->[Sealed result, one sentence: opens Sat 3 Oct 17:30 AEST.]<!-- SEALED:END --> We replayed the 2018-19 drought with a model that learned only from data before mid-2016: on three dates that season it expected about 248 dams to fall below a third, and 244 did. Over ten test years it never trained on, the cautious days held 9 times in 10, across 729,749 forecasts, and it met every pass mark we wrote before writing any code.

The same record helps those who finance farms. Lenders and valuers see rainfall, but not the water a farm has stored. Each July, the DamDays Rating gives each 2 km patch of farmland the chance its dams all run dry by March. Shown one patch that ran dry and one that did not, it picked the right one 8 times in 10; rainfall alone, about a coin toss.

That's COP31's Awareness priority made practical: farmers adapting earlier, with climate information they can actually use. By 2035, every farm dam the satellites can see could text its farmer before it runs dry.

## 9. Evidence at a glance (for "Any supporting material")

| claim | number | where to check |
|---|---|---|
| The weekly text fits one SMS | all 10 demo farms' texts this week: 144 to 160 of 160 places; 55 tests check every rule | [outbox/2026-10-02.json](../outbox/2026-10-02.json), [tests/test_weekly_text.py](../tests/test_weekly_text.py), [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md) |
| "At least N days, 9 times in 10" holds | held for 0.900 of 729,749 forecasts, 9 times in 10 (typical N: 60 days) | [artifacts/test_results.md](../artifacts/test_results.md) |
| The 2018-19 drought, replayed | 782 forecasts on 3 dates: about 248 expected to fall below a third, 244 did (by date, expected and fell: 1 Nov 2018 about 95 and 76; 1 Jan 2019 about 97 and 106; 1 Mar 2019 about 57 and 62) | the app's Rewind view; `app/data/real/meta.json`, `rewind.tallies`; why this season: [app/data/real/README.md](../app/data/real/README.md) |
| Below-a-third forecasts beat the usual rate for the region and month | skill +0.235 (95% range +0.224 to +0.248), test years 2016-2026 | [artifacts/test_results.md](../artifacts/test_results.md) |
| ... and beat the dam's own track record | skill +0.155 | same |
| ... and beat our own strong benchmark on the same forecasts | +0.014 (range +0.011 to +0.018) | same |
| Lender rating against rainfall-only | ranking accuracy 0.81 against 0.53 (a coin toss is 0.50) | same |
| Pass marks written before any code | committed Fri 2 Oct 2026, 09:12 AEST | [PREREG.md](../PREREG.md) and its commit time on GitHub |
| Model frozen before the test years were scored | Fri 2 Oct 2026, 20:21 AEST, code fingerprint 7d466291008d | [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md) |
| The unseen exam | <!-- SEALED:START evidence -->[opens Sat 3 Oct 17:30 AEST]<!-- SEALED:END --> | `artifacts/sealed/SEALED_RESULTS.md` (after Sat 17:30) |

<!-- SEALED:START -->
[The unseen exam in numbers: opens Sat 3 Oct 17:30 AEST. After the opening, `scripts/21_publish_sealed.py` writes them here.]

<!-- SEALED:END -->

One honest note for judges: the test years informed a few design choices, so they may flatter the model slightly; the sealed region is the clean exam. Details: [artifacts/test_results.md](../artifacts/test_results.md) (top of the page) and [DISCLOSURE.md](../DISCLOSURE.md).

## 10. Links

- Repository: https://github.com/Shaugato/damdays
- App: [GitHub Pages link once published; until then, open `app/index.html` from the repository]
- Demo video: [link]
- The weekly text, line by line: [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)
- Plain-language explainer: [docs/HOW_IT_WORKS.md](HOW_IT_WORKS.md)

## 11. Tools used and disclosures

See [DISCLOSURE.md](../DISCLOSURE.md): datasets (DEA Waterbodies v3, Geoscience Australia; SILO, Queensland Government; both CC BY 4.0), Python libraries, front-end libraries (Leaflet, OpenStreetMap tiles) and AI tools (Claude Code during the event; Claude research agents before it). [Add the video editing tool, and the SMS provider if a real text is sent for the video.]

---

## Before submitting: checklist

- [ ] Replace every [square bracket] in sections 3 to 11.
- [ ] Sealed result: one honest sentence, whichever way it went (templates in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "The sealed-result line").
- [x] My farm is in the app (it opens first), so section 7 names it. Checked Fri 2 Oct, 23:58 AEST.
- [x] The app writes chances as "3 in 10", as sections 7 and 8 say: the dam card, the map tips, Rewind's tables, the Rating maps and the About page. Checked in the browser Fri 2 Oct, 23:58 AEST; re-check if the app changes.
- [ ] The sample text matches `outbox/2026-10-02.json` (`farm-d`) word for word (it did on Fri 2 Oct, 23:58 AEST). If the texts are made again, use `--date 2026-10-02`, or update the text and its numbers everywhere.
- [ ] Re-check the live fact (272 of 894) if the app data is exported again (command in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "Where each number comes from").
- [ ] "What we learned from talking to people": no names, and nothing that identifies the mentor.
- [ ] Track wording: check it against the Junction form. If the form words the goal differently from the Participant Guide, use the form's words.
- [ ] Every link opens without asking for access (the Participant Guide's quality check).
- [ ] No pricing and no customer or company names: the repository is public.
- [ ] [DISCLOSURE.md](../DISCLOSURE.md): fill in the screenshot link, the team roles and the video tool.
