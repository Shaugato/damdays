# DamDays: pitch and submission fields (draft)

Draft text for the Junction submission form, one section per form field, in the form's order. Copy each section into its field.

- **Numbers** come from [`artifacts/test_results.md`](../artifacts/test_results.md) (the test years, scored once) unless marked otherwise. The sealed region's numbers are added after it is opened on Sat 3 Oct 2026, 17:30 AEST.
- **Fill-ins** are in [square brackets]. Replace every one before submitting (checklist at the end).
- **Writing rules** (from mentor feedback): "%" means only how full a dam is. Chances are written as "3 in 10". The farmer's headline is days of water left. Say "the unseen exam" or "a locked region", not statistics terms.

---

## 1. Project name

**DamDays**

## 2. One-sentence summary

DamDays tells farmers how many days of water their farm dam has left, using 38 years of free satellite data, and tests its forecasts on years and a region the model never saw.

*If the field is short:* Days of water left in a farm dam, from 38 years of satellite data.

## 3. Selected challenge and track

- **Challenge:** Build for 2035.
- **Track (COP31 priority):** Awareness Across All Areas.
- **The track's 2035 goal, word for word from the Participant Guide:** "climate-resilient farming and climate education reaching all of society by 2035".
- **How DamDays meets both halves of the track:**
  - **Farmers and land managers adapting to a changing climate.** Graziers feel drought directly, through their dams. DamDays gives each farm dam the satellites can see a runway in days, to help the farmer decide while there are still choices: cart water, move or sell stock, or fix a leaking dam.
  - **Climate information made easy for everyone to use.** The data already exists and is free: Geoscience Australia has mapped the water surface of every visible waterbody since the 1980s. DamDays turns it into one plain number per dam ("at least 60 days of water above a third, 9 times in 10") instead of a map of rainfall figures.
- **Wider COP31 link.** The Global Goal on Adaptation (the UAE Framework for Global Climate Resilience) includes targets on reducing climate-driven water scarcity and on climate-resilient food and farming. DamDays measures water security farm by farm, and can be refreshed with every satellite pass: the kind of measure those targets need.

## 4. Team nationality

[Australia: confirm on the form.]

## 5. Team members and roles

[Copy from [DISCLOSURE.md](../DISCLOSURE.md), "Team", once the names are filled in.] Shaugato Paroi built DamDays end to end (data, models, app, validation).

## 6. Problem and target users

**The problem.** In a dry spell, the question on a grazing farm is not "how full is the dam?" (you can see that) but "how long will it last?" The answer decides when to cart water, move stock to agistment, sell, or fix a dam, and waiting usually narrows the choices. Today that call is made by eye and memory. The drought tools that do exist mostly look at rainfall, and rainfall cannot say which farm's dam will fail first: in our test years, a rainfall-only score picked the farms whose dams ran dry about as well as a coin toss.

**Right now.** On 14 September 2026, 272 of the 894 farm dams we track in NSW Central West were already below a third full: the most for a September since the 2019 drought.

**Target users.**
- **Primary: livestock and mixed farmers** who rely on farm dams for stock water, starting in south-eastern Australia's grazing country. They need one plain number, delivered where they already look.
- **Secondary: rural lenders, valuers and drought-support workers**, who need to know which properties are exposed before a season starts. Today they see rainfall, not the water a farm actually holds.

## 7. Solution and intended impact

**What we built** (working now: [github.com/Shaugato/damdays](https://github.com/Shaugato/damdays); the app opens from `app/index.html`):
- **DamDays Runway, for farmers.** For each farm dam the headline is days: "at least N days of water above a third, 9 times in 10". Behind it: the chance of falling below a third in the next 90 days (written as "3 in 10"), and a curve out to six months that shows how far a wetter or drier season could move it.
- **Rewind, for trust.** Go back to a past season, see the forecasts as they were made that day, then reveal what really happened.
- **DamDays Rating, for lenders.** Each 1 July, the chance that the dams in each 2 km patch of farmland all run dry before the end of March, shown side by side with a rainfall-only score.
- **The engine** learns how each dam behaves (how fast it drops in summer, how it refills after rain, whether it runs drier than its neighbours) from 38 years of satellite looks (DEA Waterbodies, Geoscience Australia) and rainfall (SILO, Queensland Government).

**How we know it works.** We wrote the exam before the code: the pass marks and the test years were committed at 09:12 on the first morning and pushed to the public repository three minutes later ([PREREG.md](../PREREG.md)).
- **Ten years the model never trained on** (July 2016 to June 2026, including the 2018-19 drought), scored once: forecasts with nearly a quarter less error than "the usual rate for this region and month"; shown one dam that fell below a third and one that did not, it gave the right one the higher chance 8 times in 10; and the "at least N days" promise held 9 times in 10 across 729,749 forecasts. Every pass mark met.
- **The lender rating**, shown one 2 km patch of farmland whose dams all ran dry and one whose dams did not, picked the right one 8 times in 10; rainfall alone did little better than a coin toss.
- **The unseen exam:** a third region (Southern Downs, Granite Belt, New England), locked away with public fingerprints before the event and opened once, on camera, on Sat 3 Oct 17:30 AEST: [one-sentence sealed result; templates in VIDEO_SCRIPT.md].

**Intended impact by 2035.**
- Farmers get a forecast of each dam's dry-out, counted in days, and can act earlier, while there are more choices.
- Lenders and valuers can measure drought exposure property by property, from the water a farm actually holds. Because the rating follows each dam's own record, improvements to a farm's water supply show up as that record builds.
- It can scale on public data: the same satellite record covers all of Australia, and the whole pipeline runs on a laptop. So far it has been tested only in south-eastern Australia; each new climate needs its own test.

**Next.** A weekly text message with each farmer's days of water left, sent only when it matters, because a weekly text reaches farmers better than an app or email (mentor feedback) [move into "What we built" if it is built by submission]; more regions; and trials with farmers of how they act on the number.

## 8. Written pitch (about 400 words once the sealed sentence is in)

Ask a grazier in a dry spring how full their dam is and they'll tell you at a glance. Ask how long it will last and you'll get a guess. That guess decides when to cart water, move stock, sell, or fix a leaking dam. Leave it late and the choices shrink.

On 14 September 2026, 272 of the 894 farm dams we track in NSW Central West were already below a third full: the most for a September since the 2019 drought. Each of those farms faces that question now.

DamDays answers it. Satellites have mapped the water in every visible Australian waterbody since the 1980s, and Geoscience Australia publishes the record free. DamDays reads 38 years of it per dam and learns how each one behaves: how fast it drops in summer, how it refills after rain, whether it runs drier than its neighbours. Then it gives the farmer one number: at least N days of water above a third, 9 times in 10. Behind it: the chance of falling below a third within three months, written as "3 in 10", and a six-month curve.

The same record helps those who finance farms. Each July, the DamDays Rating gives each 2 km patch with farm dams the chance that its dams all run dry by March. Rainfall-only scores, which most drought tools rely on today, cannot tell neighbouring farms apart.

We wrote the exam before the code, and the pass marks were public from the first hour. The frozen model then faced ten years it never trained on, 2016 to 2026, including the 2018-19 drought, scored once. Its forecasts had nearly a quarter less error than guessing the usual rate, and the "at least N days" promise held 9 times in 10, across 729,749 forecasts. Shown one 2 km patch of farmland whose dams all ran dry and one whose did not, the lender rating picked right 8 times in 10; rainfall alone, barely better than a coin toss. Then came the real exam: a third region, locked away with public fingerprints before the event, opened once, on camera. [Sealed result, one sentence.]

That's COP31's Awareness priority made practical: farmers adapting earlier, with public climate data made usable. By 2035, every farm dam the satellites can see could have a tested forecast of its water runway before it runs dry.

## 9. Evidence at a glance (for "Any supporting material")

| claim | number | where to check |
|---|---|---|
| Below-a-third forecasts beat the usual rate for the region and month | skill +0.235 (95% range +0.224 to +0.248), test years 2016-2026 | [artifacts/test_results.md](../artifacts/test_results.md) |
| ... and beat the dam's own track record | skill +0.155 | same |
| ... and beat our own strong benchmark on the same forecasts | +0.014 (range +0.011 to +0.018) | same |
| "At least N days, 9 times in 10" holds | 90.0% of 729,749 forecasts (typical N: 60 days) | same |
| Lender rating against rainfall-only | ranking accuracy 0.81 against 0.53 (a coin toss is 0.50) | same |
| Pass marks written before any code | committed Fri 2 Oct 2026, 09:12 AEST | [PREREG.md](../PREREG.md) and its commit time on GitHub |
| Model frozen before the test years were scored | Fri 2 Oct 2026, 20:21 AEST, code fingerprint 7d466291008d | [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md) |
| The unseen exam | [sealed numbers] | `artifacts/sealed/SEALED_RESULTS.md` (after Sat 17:30) |

One honest note for judges: the test years informed a few design choices, so they may flatter the model slightly; the sealed region is the clean exam. Details: [artifacts/test_results.md](../artifacts/test_results.md) (top of the page) and [DISCLOSURE.md](../DISCLOSURE.md).

## 10. Links

- Repository: https://github.com/Shaugato/damdays
- App: [GitHub Pages link once published; until then, open `app/index.html` from the repository]
- Demo video: [link]
- Plain-language explainer: [docs/HOW_IT_WORKS.md](HOW_IT_WORKS.md)

## 11. Tools used and disclosures

See [DISCLOSURE.md](../DISCLOSURE.md): datasets (DEA Waterbodies v3, Geoscience Australia; SILO, Queensland Government; both CC BY 4.0), Python libraries, front-end libraries (Leaflet, OpenStreetMap tiles) and AI tools (Claude Code during the event; Claude research agents before it). [Add the video editing tool.]

---

## Before submitting: checklist

- [ ] Replace every [square bracket] in sections 3 to 11.
- [ ] Sealed result: one honest sentence, whichever way it went (templates in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "The sealed-result line").
- [ ] Re-check the live fact (272 of 894) if the app data is exported again (command in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), "Where each number comes from").
- [ ] Track wording: check it against the Junction form. If the form words the goal differently from the Participant Guide, use the form's words.
- [ ] Every link opens without asking for access (the Participant Guide's quality check).
- [ ] No pricing and no customer or company names: the repository is public.
- [ ] [DISCLOSURE.md](../DISCLOSURE.md): fill in the screenshot link, the team roles and the video tool.
